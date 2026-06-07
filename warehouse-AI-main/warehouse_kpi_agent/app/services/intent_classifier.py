"""IntentClassifier service.

Uses a LangChain chain:
    ChatPromptTemplate | ChatOllama (JSON mode) | JsonOutputParser

Classifies a user query into one of four intents and extracts
structured entities (warehouse_id, dates, kpi_names, target_collections).

Reference architecture pattern:
    classifier.classify(query)  →  dict[str, Any]
        └── intent, confidence, entities, target_collections,
            join_on, query_params

SCHEMA-AWARE: Injects full schema information into LLM prompt for
better collection/column detection and intent classification.
"""

import logging
import re
from typing import Any, Optional

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_ollama import ChatOllama
from langsmith import traceable

from app.config.settings import LLM_MODEL, OLLAMA_BASE_URL
from app.config.schema_registry import get_compact_schema_reference
from app.tools import ALL_COLLECTIONS, ALL_KPI_KEYS

logger = logging.getLogger(__name__)

# ── Domain keyword signals (comprehensive, schema-based) ──────────────────────
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "warehouse_productivity": [
        # Core terms - IMPORTANT: include singular forms first
        "warehouse", "warehouses", "warehouse productivity", "warehouse performance", 
        "warehouse operations", "wh-", "how many warehouse",
        # Columns from schema
        "shift", "shifts", "lines picked", "lines_picked", "lines packed", "lines_packed",
        "orders processed", "orders_processed", "labor hours", "labor_hours", "labor",
        "picks per hour", "picks_per_hour", "touches per order", "touches_per_order",
        "equipment utilization", "equipment_utilization_pct", "sla adherence", "sla_adherence_pct",
        # Metrics
        "lines per hour", "packing efficiency", "throughput",
    ],
    "outbound_parts": [
        # Core terms
        "outbound", "shipment", "shipments", "delivery", "deliveries", "fulfillment",
        # Columns from schema
        "customer", "customers", "customer_id", "customer_name",
        "order", "orders", "order_number", "order_date",
        "promise date", "promise_date", "shipped date", "shipped_date",
        "qty ordered", "qty_ordered", "qty shipped", "qty_shipped",
        "backorder", "backorder_qty", "otif", "otif_flag",
        # Metrics
        "fill rate", "fill_rate", "backorder rate",
    ],
    "inbound_parts": [
        # Core terms
        "inbound", "receiving", "purchase order", "procurement", "receipt", "receipts",
        # Columns from schema
        "supplier", "suppliers", "vendor", "vendors", "supplier_id", "supplier_name",
        "po_number", "po number", "expected date", "expected_date",
        "received date", "received_date", "qty received", "qty_received",
        "inbound lead time", "inbound_lead_time_days", "discrepancy", "discrepancy_qty",
        # Metrics
        "lead time", "on time receipts", "on_time_receipts_pct", "qty discrepancy",
    ],
    "inventory_snapshot": [
        # Core terms
        "inventory", "stock", "sku", "skus", "parts", "product", "products",
        # Columns from schema
        "snapshot date", "snapshot_date", "part_number", "sku_family",
        "on hand", "on_hand_qty", "on-hand", "available qty", "available_qty",
        "safety stock", "safety_stock", "reorder point", "reorder_point",
        "days of supply", "days_of_supply", "stockout", "stockout_flag",
        "age days", "age_days", "inventory aging",
        # Metrics
        "low stock", "excess inventory",
    ],
    "employee_productivity": [
        # Core terms
        "employee", "employees", "worker", "workers", "staff", "personnel",
        "how many employee", "how many worker",
        # Columns from schema
        "employee_id", "role", "picker", "packer", "supervisor",
        "tasks completed", "tasks_completed", "picks", "hours worked", "hours_worked",
        "picks per hour", "picks_per_hour", "errors", "error rate", "error_rate",
        "rework", "overtime", "overtime_hours", "overtime_pct",
    ],
}

# ── System prompt (schema-aware)──────────────────────────────────────────────
def _build_system_prompt() -> str:
    """Build schema-aware system prompt with collection schemas injected."""
    schema_ref = get_compact_schema_reference()
    
    # Build domain keywords reference
    domain_keywords_ref = "## Domain-Specific Keywords for Collection Routing\n\n"
    for collection, keywords in _DOMAIN_KEYWORDS.items():
        domain_keywords_ref += f"**{collection}**: {', '.join(keywords[:15])}...\n"
    
    return f"""You are an intent classifier for a Warehouse KPI Analytics agent.

Analyze the user query and output ONLY valid JSON with these exact keys:

{{
  "intent": "<registered_kpi | analytical_single | analytical_parallel | out_of_scope>",
  "confidence": <float 0.0-1.0>,
  "entities": {{
    "warehouse_id": "<WH-01 | WH-02 | WH-03 | null>",
    "start_date": "<YYYY-MM-DD | null>",
    "end_date": "<YYYY-MM-DD | null>",
    "kpi_name": "<single kpi key | null>",
    "employee_id": "<employee ID string e.g. E-1033 | null>"
  }},
  "target_collections": [<list of collection names or empty list>],
  "join_on": "<common join field | null>",
  "query_params": {{
    "kpi_names": [<list of kpi keys or null>],
    "kpi_scope": "<single | all | null>"
  }},
  "reason": "<one sentence explanation>"
}}

{schema_ref}

{domain_keywords_ref}

Classification rules:
- "registered_kpi"         : user EXPLICITLY asks for KPI/metric reports OR requests analysis
                             over a DATE RANGE (2 different dates). RULES:
                               🚨 CRITICAL: registered_kpi is ONLY for:
                                 1. Explicit KPI terminology: "KPI report", "show ALL metrics",
                                    "performance dashboard", "calculate ALL KPIs", "show all KPIs"
                                 2. Date RANGE queries (start_date != end_date): "from Jan to Mar",
                                    "between May and June", "last quarter", "this month"
                                 3. General performance reports: "how is WH-02 performing overall"
                               🚨 DO NOT use registered_kpi for:
                                 • Questions asking for AVERAGE/SUM/COUNT/MAX/MIN of a SPECIFIC FIELD
                                   Examples: "average equipment utilization", "total discrepancy",
                                   "max lead time", "count of employees" → use analytical_single
                                 • SINGLE DATE queries like "on August 15th how many orders"
                                 • Specific data questions like "how many X on date Y"
                                 • Raw field value requests (part_number, customer_name, etc.)
                                 • Aggregations of specific columns (even if they have "rate", "pct", "percentage" in the name)
                               For single-date specific questions → use analytical_single instead!
                               For field aggregations (avg, sum, etc.) → use analytical_single instead!
                               
                               • If NO specific KPI is named → kpi_scope="all", kpi_names=[],
                                 target_collections=ALL 5 collections.
                                 Examples: "calculate ALL KPIs for WH-02", "show all metrics",
                                 "KPI report for WH-01 from Jan to Mar", "all KPIs this month",
                                 "performance report for WH-03 last quarter"
                               • If a SPECIFIC KPI is named → kpi_scope="single", kpi_names=[<key>],
                                 target_collections=[collection that owns it].
                                 Examples: "fill rate for WH-02", "what is the OTIF score",
                                 "show me error_rate for WH-01"
                             🚨 IMPORTANT: If the user asks for SPECIFIC COLUMN VALUES (not KPIs),
                             use analytical_single instead. Examples:
                               • "what is the part number" → analytical_single (asking for part_number field)
                               • "show me available quantity" → analytical_single (asking for available_qty field)
                               • "what is customer name" → analytical_single (asking for customer_name field)
                               • "what was the order number" → analytical_single (asking for order_number field)
                               • "average equipment utilization percentage" → analytical_single (avg of field)
                               • "total discrepancy quantity" → analytical_single (sum of field)
                             Only use registered_kpi when asking for CALCULATED METRICS, not raw field values or simple aggregations.
- "analytical_single"      : general statistical/analytical question on exactly ONE collection,
                             OR asking for specific column/field values from the database,
                             OR specific data questions on a SINGLE DATE,
                             OR aggregations (avg, sum, count, max, min) of specific fields.
                             Set target_collections to that one collection name only.
                             Use the schema reference and domain keywords above to determine which
                             collection contains the mentioned columns/data.
                             IMPORTANT: Questions like "how many employees", "list employees",
                             "count of workers", "employee count", "how many workers", "who works",
                             "how many suppliers", "how many orders", "how many SKUs",
                             "how many records", "how many warehouses", "average X", "total Y",
                             "maximum Z" all map to analytical_single.
                             Any count / distinct / summary / aggregation question about data in a known collection
                             is analytical_single, NOT out_of_scope or registered_kpi.
                             🚨 CRITICAL: Single-date queries with specific questions are analytical_single:
                             Examples: "how many orders on Aug 15", "orders processed on Sept 1st",
                             "picks on March 3rd for WH-02", "shipments on May 10th" → analytical_single.
                             Date range queries asking for KPIs → registered_kpi.
                             🚨 CRITICAL: Queries asking for raw data fields/column values (even with filters)
                             are analytical_single, NOT registered_kpi.
                             Examples: "part number in WH-03", "available quantity on Sept 1",
                             "customer name for order SO123", "employee name for E-1015" all use analytical_single.
                             ALSO: Queries about a specific employee (e.g. "E-1033", "employee E-1033",
                             "tasks by E-1033", "picks for employee E-1033") are analytical_single
                             on employee_productivity. Extract the employee ID into entities.employee_id.
                             A specific date mentioned → set start_date AND end_date to that same date.
- "analytical_parallel"    : question that touches MORE THAN ONE collection, OR asks for
                             a broad overview. Set target_collections to all relevant collections.
                             Use the schema reference and domain keywords to identify which collections
                             contain the mentioned columns and data points.
                             Examples:
                               "overview of all data"                   → all 5 collections
                               "compare all warehouses"                 → all 5 collections
                               "full report"                            → all 5 collections
                               "shifts and customer ids for WH-02"      → warehouse_productivity + outbound_parts
                               "supplier delays and stockout levels"     → inbound_parts + inventory_snapshot
                               "employee picks and outbound fill rate"   → employee_productivity + outbound_parts
                               "how many shifts AND linked customers"    → warehouse_productivity + outbound_parts
                             KEY RULE: if the query mentions data from 2 or more different
                             collections (check schema reference and domain keywords), use
                             analytical_parallel with those collections in target_collections.
- "out_of_scope"           : query has NOTHING to do with warehouse operations, logistics,
                             inventory, suppliers, orders, employees at a warehouse,
                             or any data in the 5 collections. Examples: weather, cooking,
                             sports, finance completely unrelated to a warehouse.
                             When in doubt, pick analytical_single or analytical_parallel —
                             NEVER out_of_scope for anything mentioning warehouses, shifts,
                             customers, suppliers, employees, inventory, or orders.

KPI → Collection mapping:
  inbound_parts         → avg_inbound_lead_time, on_time_receipts_pct, qty_discrepancy_pct, top_delaying_suppliers
  outbound_parts        → fill_rate, otif, backorder_rate, top_backorder_skus
  inventory_snapshot    → days_of_supply, stockout_pct
  warehouse_productivity→ lines_per_labor_hour, orders_per_day, sla_adherence
  employee_productivity → picks_per_hour, error_rate, overtime_pct

Available KPI keys: {", ".join(ALL_KPI_KEYS)}
Available collections: {", ".join(ALL_COLLECTIONS)}

Warehouse IDs in system: WH-01, WH-02, WH-03
"warehouse 1" / "first warehouse" → WH-01, "warehouse 2" → WH-02, "warehouse 3" → WH-03

COLUMN-AWARE ROUTING:
Use the schema reference and domain keywords above to identify which collection(s) contain
mentioned columns. Match query terms against the domain keywords to find the right collection.

Examples:
- "warehouse_id, shift, labor_hours" → warehouse_productivity (all three columns exist there)
- "customer_name, order_date" → outbound_parts
- "employee_id, picks, errors" → employee_productivity
- "part_number, on_hand_qty" → inventory_snapshot
- "supplier_name, qty_ordered" → inbound_parts

Output raw JSON ONLY. No markdown fences, no extra text outside the JSON.
"""


_SYSTEM_PROMPT = _build_system_prompt()


class IntentClassifier:
    """LangChain-based intent classifier.

    Chain: ChatPromptTemplate | ChatOllama(format=json) | JsonOutputParser

    Usage:
        classifier = IntentClassifier.get_instance()
        result = classifier.classify("What is the fill rate for WH-01?")
        # result["intent"] == "registered_kpi"
        # result["entities"]["warehouse_id"] == "WH-01"
    """

    _instance: "IntentClassifier | None" = None

    # ── Valid values ──────────────────────────────────────────────────────────
    _VALID_INTENTS = frozenset(
        {"registered_kpi", "analytical_single", "analytical_parallel", "out_of_scope"}
    )

    def __init__(self) -> None:
        self._llm = ChatOllama(
            model=LLM_MODEL,
            base_url=OLLAMA_BASE_URL,
            format="json",
            temperature=0,
        )
        self._parser = JsonOutputParser()
        self._prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessagePromptTemplate.from_template("{context}\nUser Query: {query}"),
            ]
        )
        # LangChain chain: prompt → LLM → parser
        self._chain = self._prompt | self._llm | self._parser
        logger.info("IntentClassifier initialised (model=%s)", LLM_MODEL)

    @classmethod
    def get_instance(cls) -> "IntentClassifier":
        """Return singleton instance, creating on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    @traceable(name="intent_classification", tags=["llm", "classification"])
    def classify(self, query: str, conversation_history: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
        """Classify a user query with optional conversation history for context.

        Args:
            query: Raw user question string.
            conversation_history: Optional list of previous Q&A pairs:
                [{"query": "...", "response": "..."}, ...]

        Returns:
            dict with keys:
              intent, confidence, entities, target_collections,
              join_on, query_params
        """
        logger.debug("IntentClassifier.classify: %s", query[:80])
        
        # Build context from conversation history if provided
        context_prompt = ""
        if conversation_history:
            context_lines = ["## Previous Conversation (for resolving references):\n"]
            for i, turn in enumerate(conversation_history[-3:], 1):  # Last 3 turns
                context_lines.append(f"**Q{i}:** {turn.get('query', '')}")
                # Include just summary of response, not full markdown
                response = turn.get('response', '')[:200]
                context_lines.append(f"**A{i}:** {response}...\n")
            context_prompt = "\n".join(context_lines)
            context_prompt += "\n**IMPORTANT:** Resolve references like 'same employee', 'that day', 'above', etc. using the previous conversation context.\n\n"
        
        try:
            # Always pass both query and context (empty string if no history)
            raw: Any = self._chain.invoke({
                "query": query,
                "context": context_prompt
            })
            return self._validate(raw, query)
        except Exception as exc:
            logger.error("IntentClassifier chain failed: %s", exc)
            return self._fallback(str(exc))

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _match_collections_by_keywords(query: str) -> list[str]:
        """Match query against domain keywords to find relevant collections.
        
        Returns list of collections where keywords match the query.
        
        IMPORTANT: Ignores keywords that appear in filter contexts (e.g., "warehouse WH-03", 
        "in warehouse", "for warehouse") to avoid false positives.
        """
        q_lower = query.lower()
        matched_collections = []
        
        # Filter context patterns - when these appear, ignore warehouse-related keywords
        warehouse_filter_patterns = [
            r'\bwarehouse\s+wh-\d+',  # "warehouse WH-03"
            r'\bin\s+warehouse\b',     # "in warehouse"
            r'\bfor\s+warehouse\b',    # "for warehouse"  
            r'\bat\s+warehouse\b',     # "at warehouse"
            r'\bfrom\s+warehouse\b',   # "from warehouse"
            r'\bwarehouse\s+id\b',     # "warehouse id"
            r'\bwh-\d+',              # Direct warehouse ID like "WH-03"
        ]
        
        # Check if query has warehouse references in filter context only
        has_warehouse_in_filter_context = any(
            re.search(pattern, q_lower) for pattern in warehouse_filter_patterns
        )
        
        # Track which collections matched with score (prefer longer/more specific phrases)
        collection_scores: dict[str, int] = {}
        
        for collection, keywords in _DOMAIN_KEYWORDS.items():
            # Special handling for warehouse_productivity
            if collection == "warehouse_productivity":
                # Skip if warehouse references appear ONLY as filters and query is about other data
                if has_warehouse_in_filter_context:
                    # Check if query contains indicators of warehouse productivity metrics
                    productivity_indicators = [
                        'productivity', 'performance', 'operations', 'efficiency',
                        'shift', 'picks per hour', 'lines picked', 'labor hours',
                        'sla', 'throughput', 'utilization', 'picks', 'packed', 'orders processed'
                    ]
                    if not any(ind in q_lower for ind in productivity_indicators):
                        # Query is asking "in warehouse WH-03 what is X" where X is not productivity data
                        # Skip warehouse_productivity collection
                        continue
            
            # Find matching keywords with scoring (longer phrases = higher score)
            matched_keywords = []
            if collection == "warehouse_productivity" and has_warehouse_in_filter_context:
                # Filter out wh- pattern if it appears as an ID filter
                filtered_keywords = [kw for kw in keywords if kw != "wh-"]
                matched_keywords = [kw for kw in filtered_keywords if kw.lower() in q_lower]
            else:
                matched_keywords = [kw for kw in keywords if kw.lower() in q_lower]
            
            if matched_keywords:
                # Score = sum of word count in each matched keyword
                # Multi-word phrases like "orders processed" get higher score than single words like "orders"
                score = sum(len(kw.split()) for kw in matched_keywords)
                collection_scores[collection] = score
        
        # If multiple collections matched, prefer the one(s) with highest score
        if collection_scores:
            max_score = max(collection_scores.values())
            # Only return collections with the highest score
            # This filters out collections that only matched on generic single words
            matched_collections = [
                coll for coll, score in collection_scores.items() 
                if score >= max_score
            ]
        
        return matched_collections

    @staticmethod
    def _nullify(v: Any) -> Any:
        """Convert null-like string values to Python None."""
        return None if str(v).lower().strip() in ("null", "none", "", "n/a", "na") else v

    def _validate(self, raw: Any, query: str = "") -> dict[str, Any]:
        """Validate and normalise the raw LLM output dict."""
        if not isinstance(raw, dict):
            return self._fallback(f"non-dict output: {type(raw)}")

        # Intent
        intent: str = raw.get("intent", "out_of_scope")
        if intent not in self._VALID_INTENTS:
            intent = "out_of_scope"

        # Entities
        entities: dict[str, Any] = raw.get("entities") or {}
        entities = {k: self._nullify(v) for k, v in entities.items()}

        # Target collections — validate against known collection names
        raw_cols: list = raw.get("target_collections") or []
        target_collections = [c for c in raw_cols if c in ALL_COLLECTIONS]
        # analytical_parallel with no explicit collections → query all 5
        if intent == "analytical_parallel" and not target_collections:
            target_collections = list(ALL_COLLECTIONS)
        # registered_kpi with kpi_scope="all" → always covers all 5 collections
        raw_kpi_scope_early = (raw.get("query_params") or {}).get("kpi_scope")
        if intent == "registered_kpi" and raw_kpi_scope_early in ("all", None, "null", ""):
            target_collections = list(ALL_COLLECTIONS)

        # ── Deterministic multi-domain guardrail ──────────────────────────────
        # Use domain keywords to validate and enhance collection routing.
        # If the LLM missed domains or misrouted, correct it using keyword matching.
        if query:
            keyword_matched_collections = self._match_collections_by_keywords(query)
            logger.debug("Keyword matching for query '%s': %s", query[:50], keyword_matched_collections)
            
            # ── PRIORITY GUARDRAIL: Specific employee query ────────────────────
            # If query mentions a specific employee ID (E-XXXX), force to analytical_single
            # on employee_productivity collection only
            employee_id_match = re.search(r'\bE-\d{4}\b', query, re.IGNORECASE)
            if employee_id_match:
                employee_id = employee_id_match.group(0).upper()
                logger.info(
                    "Guardrail PRIORITY: Specific employee query detected (%s) → analytical_single on employee_productivity",
                    employee_id
                )
                if intent not in ("registered_kpi",):  # Don't override registered_kpi
                    intent = "analytical_single"
                    target_collections = ["employee_productivity"]
                    # Ensure employee_id is in entities
                    if "employee_id" not in entities or not entities["employee_id"]:
                        entities["employee_id"] = employee_id
            
            # Case 1: LLM returned EMPTY collections (most critical - prevents default fallback)
            elif not target_collections and keyword_matched_collections:
                logger.info(
                    "Guardrail CRITICAL: empty collections → %s via keywords, intent=%s",
                    keyword_matched_collections, intent,
                )
                target_collections = keyword_matched_collections
                # Adjust intent based on number of matched collections
                if len(keyword_matched_collections) == 1:
                    if intent not in ("registered_kpi",):
                        intent = "analytical_single"
                elif len(keyword_matched_collections) > 1:
                    if intent not in ("registered_kpi",):
                        intent = "analytical_parallel"
            
            # Case 2: LLM said out_of_scope but keywords matched collections
            elif intent == "out_of_scope" and keyword_matched_collections:
                logger.info(
                    "Guardrail upgrade: out_of_scope → analytical_%s, cols=%s",
                    "parallel" if len(keyword_matched_collections) > 1 else "single",
                    keyword_matched_collections,
                )
                if len(keyword_matched_collections) == 1:
                    intent = "analytical_single"
                    target_collections = keyword_matched_collections
                else:
                    intent = "analytical_parallel"
                    target_collections = keyword_matched_collections
            
            # Case 3: LLM said analytical_single but keywords indicate multiple collections
            elif intent == "analytical_single" and len(keyword_matched_collections) >= 2:
                logger.info(
                    "Guardrail upgrade: analytical_single → analytical_parallel, cols=%s",
                    keyword_matched_collections,
                )
                intent = "analytical_parallel"
                # Merge LLM-detected and keyword-detected collections
                target_collections = list(
                    dict.fromkeys(target_collections + keyword_matched_collections)
                )
            
            # Case 4: LLM detected collection but missed others via keywords
            elif intent in ("analytical_single", "analytical_parallel") and keyword_matched_collections:
                # Merge keyword-detected collections with LLM-detected ones
                merged = list(dict.fromkeys(target_collections + keyword_matched_collections))
                if len(merged) > len(target_collections):
                    logger.info(
                        "Guardrail enhancement: added collections %s via keywords",
                        [c for c in merged if c not in target_collections],
                    )
                    target_collections = merged
                    # Upgrade to parallel if now multiple collections
                    if len(target_collections) > 1 and intent == "analytical_single":
                        intent = "analytical_parallel"
                        logger.info("Guardrail: upgraded to analytical_parallel due to merged collections")
            
            # Case 5: registered_kpi with kpi_scope="all" should always have all collections
            if intent == "registered_kpi" and raw_kpi_scope_early in ("all", None, "null", ""):
                if set(target_collections) != set(ALL_COLLECTIONS):
                    logger.info("Guardrail: registered_kpi kpi_scope=all → adding all collections")
                    target_collections = list(ALL_COLLECTIONS)
        # ─────────────────────────────────────────────────────────────────────

        # query_params
        query_params: dict[str, Any] = raw.get("query_params") or {}
        kpi_names: list = query_params.get("kpi_names") or []
        # Validate KPI names
        kpi_names = [k for k in kpi_names if k in ALL_KPI_KEYS]
        if not kpi_names:
            single = self._nullify(entities.get("kpi_name"))
            if single and single in ALL_KPI_KEYS:
                kpi_names = [single]
        query_params["kpi_names"] = kpi_names or None
        if "kpi_scope" in query_params:
            query_params["kpi_scope"] = self._nullify(query_params["kpi_scope"])

        return {
            "intent": intent,
            "confidence": float(raw.get("confidence", 0.5)),
            "entities": entities,
            "target_collections": target_collections,
            "join_on": self._nullify(raw.get("join_on")),
            "query_params": query_params,
        }

    @staticmethod
    def _fallback(reason: str) -> dict[str, Any]:
        logger.warning("IntentClassifier fallback triggered: %s", reason)
        return {
            "intent": "out_of_scope",
            "confidence": 0.0,
            "entities": {},
            "target_collections": [],
            "join_on": None,
            "query_params": {"kpi_names": None, "kpi_scope": None},
        }
