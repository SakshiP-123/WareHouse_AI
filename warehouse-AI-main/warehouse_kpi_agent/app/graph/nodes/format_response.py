"""Format Response Node.

LLM Call #2 in the pipeline (reference architecture pattern).

Uses qwen2.5:7b via Ollama to generate a clean Markdown response from
the query results stored in collection_results / db_results.

The markdown output is:
  - Rendered by Streamlit → st.markdown()
  - Returned raw by FastAPI → JSON field "formatted_response"
  - Printed in CLI → rich.markdown.Markdown()

For out_of_scope queries, returns a hardcoded message (no LLM call needed).

SCHEMA-AWARE: Injects schema information into LLM prompt so it knows
what columns exist in each collection for better response formatting.
"""

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langsmith import traceable

from app.config.settings import LLM_MODEL, OLLAMA_BASE_URL
from app.config.schema_registry import get_schema_summary
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

# ── LLM singleton ─────────────────────────────────────────────────────────────
_llm: ChatOllama | None = None


def _get_llm() -> ChatOllama:
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
    return _llm


# ── Prompts ────────────────────────────────────────────────────────────────────
_FORMAT_SYSTEM = """You are a precise, direct warehouse analytics assistant.
Your goal is to answer EXACTLY what the user asked - nothing more, nothing less.

🚨 CRITICAL RULES:

1. **ANSWER ONLY WHAT WAS ASKED**
   - If user asks "what is the part number for X?" → Give the part number. Period.
   - If user asks "how many employees?" → Give the count. Period.
   - If user asks "show me top 5 suppliers" → Show top 5 suppliers in a simple table.
   - DO NOT add summaries, insights, or extra context unless explicitly requested.

2. **BE DIRECT AND PRECISE**
   - User asks specific question → Give specific answer
   - User asks for overview/summary/analysis → Then provide detailed summary
   - User asks for comparison → Then show comparison
   - Match the response TYPE to the question TYPE

3. **USE EXACT VALUES FROM DATA**
   - Copy numbers EXACTLY from the JSON data provided
   - NO rounding, NO estimating, NO making up numbers
   - If JSON says "part_number": "SKU-17823", write "SKU-17823"

4. **IF DATA NOT FOUND**
   - Say clearly: "I don't have information about [specific request]."
   - DO NOT make up answers
   - DO NOT show general statistics when specific data was requested
   - Example: User asks "backorder for customer C-1234" but data has no customer filter
     → Say: "I don't have specific data for customer C-1234. The query returned general statistics instead."

5. **FORMATTING RULES**
   - Specific questions: Answer in 1-2 sentences or simple value
   - List questions (top N, show all): Use markdown table
   - Comparison questions: Use side-by-side table
   - Overview/summary questions: Use headers, tables, bullet points
   - Always use markdown format

6. **NO SCHEMA IN OUTPUT**
   - Schema information is provided as REFERENCE only
   - Never output schema fields - only format ACTUAL DATA

EXAMPLES:

❌ WRONG (user asked specific, you gave summary):
User: "part number for highest discrepancy?"
Response: "Summary of Inbound Parts Data... Total Records: 3,000... Top Suppliers... Insight: WH-03 has..."

✅ CORRECT (direct answer):
User: "part number for highest discrepancy?"
Response: "The part number with the highest discrepancy quantity is **SKU-7823** (discrepancy: 245 units)."

✅ CORRECT (for average calculations, show the value):
User: "part number for highest average discrepancy?"
Response: "The part number with the highest average discrepancy is **SKU-7823** (average discrepancy: 19.9 units)."

❌ WRONG (no data, but made up answer):
User: "backorder for customer ABC on May 10?"
Response: "Customer ABC has 150 backorders on May 10."
(But data only has totals, no customer filter)

✅ CORRECT (honest about missing data):
User: "backorder for customer ABC on May 10?"
Response: "I don't have specific data for customer ABC. The query returned general backorder statistics (total: 13,220 across all customers)."

❌ WRONG (showing wrong value):
User: "employee with highest picks?"
Data: {"employee_id": "E-1234", "total_picks": 567}
Response: "Employee E-1234 completed 500 picks" (WRONG - said 500 instead of 567)

✅ CORRECT (exact value):
User: "employee with highest picks?"
Data: {"employee_id": "E-1234", "total_picks": 567}
Response: "Employee **E-1234** completed **567** picks."

🚨 CRITICAL: When data contains calculated values (avg, sum, max, min), ALWAYS show that calculated value in your answer!
Example: If JSON has {"part_number": "SKU-123", "avg_discrepancy": 19.9}, you MUST mention "19.9" in your response.

Remember: Answer ONLY what was asked. Be direct. Be precise. Show exact values. No fluff."""

_FORMAT_SYSTEM_KPI = """You are a concise, professional warehouse analytics assistant.
Given registered KPI data across warehouse collections, generate a structured markdown report.

🚨 CRITICAL RULE: You MUST use the EXACT numeric values from the JSON data provided.
DO NOT estimate, round differently, or make up ANY numbers. Copy values EXACTLY as shown.

CRITICAL: You will receive BOTH schema information AND actual KPI results in the data.
DO NOT output the schema - only output the KPI VALUES in a formatted report.

STRICT formatting rules for registered_kpi responses:
1. Start with a 1-2 sentence executive summary of overall warehouse health based on the KPI VALUES.

2. **MANDATORY**: Create a ## section for EVERY collection in the JSON data.
   Collections include: inbound_parts, outbound_parts, inventory_snapshot, warehouse_productivity, employee_productivity
   DO NOT skip any collections! If a collection has KPIs in the JSON, you MUST show them.

3. **CRITICAL**: Under each section, you MUST include ALL KPIs from that collection in the data.
   DO NOT cherry-pick or show only some KPIs - show EVERY SINGLE KPI provided in the JSON.
   
   Produce a markdown table with these EXACT columns:
   | KPI | Value | Unit | Status | Comment |
   Where:
   - KPI     = human-readable KPI name from the data
   - Value   = ACTUAL numeric result from the data (EXACT value from JSON - do NOT modify)
   - Unit    = unit of measure from the data
   - Status  = 🟢 GREEN / 🟡 AMBER / 🔴 RED based on warehouse industry benchmarks
   - Comment = ONE specific, actionable sentence about THIS KPI's ACTUAL value (not generic)
               Tailor the comment to the actual number — e.g. "At 87.8%, fill rate is
               7.2 points below the 95% target; review top backorder SKUs." NOT generic
               phrases like "monitor this metric."

4. For list-type KPIs (top suppliers, top SKUs), show them as a separate sub-table
   immediately below the main KPI table in that section.

5. End with a ## 🔍 Key Actions section listing the top 3 actionable items across ALL KPIs,
   each referencing the specific KPI name and ACTUAL value from the data.

6. Do NOT output schema descriptions or column definitions - only KPI results.
7. Do NOT add a single generic insight at the end — the Comment column replaces that.
8. Respond in markdown ONLY — no preamble, no code fences, just the markdown.

🚨 REMINDER: 
- Include ALL collections from the JSON data. Do not skip any. 
- Include ALL KPIs within each collection. Do not omit any.
- Use EXACT numbers. Zero tolerance for modifications."""

_FORMAT_HUMAN = """🎯 USER'S SPECIFIC QUESTION:
"{query}"

⚡ YOUR TASK: Answer ONLY this specific question. Do NOT provide summaries or extra context unless the question explicitly asks for it.

Query Metadata (for reference):
- Intent: {intent}
- Collections Queried: {collections}
- Total Result Items: {result_count}

{schema_context}

📊 ACTUAL DATA FROM DATABASE (JSON):
Use EXACT values from this JSON - do NOT modify numbers:

⚠️ IMPORTANT: The JSON below contains data organized by collection. 
{collections_note}

```json
{data_json}
```

INSTRUCTIONS:
1. Read the user's question: "{query}"
2. Determine what SPECIFIC information they want (a value? a list? a comparison? an overview?)
3. Extract that EXACT information from the JSON data
4. Answer DIRECTLY and CONCISELY
5. If the specific information is NOT in the JSON, say "I don't have information about [specific request]."
6. Do NOT generate summaries, insights, or extra tables unless the question asks for them

Examples:
- Q: "part number for highest discrepancy?" → A: "SKU-7823 (discrepancy: 245 units)"
- Q: "how many employees?" → A: "132 employees"
- Q: "top 3 suppliers by volume?" → A: [simple 3-row table]
- Q: "give me an overview of inbound" → A: [full summary with tables and insights]"""

_OUT_OF_SCOPE_MSG = """## ⚠️ Out of Scope

This question is outside the Warehouse KPI Agent's scope.

### What I can help with:

| Category | KPIs / Questions |
|----------|-----------------|
| 📦 **Inbound** | Lead time, on-time receipts, discrepancy rate, top delaying suppliers |
| 🚚 **Outbound** | Fill rate, OTIF %, backorder rate, top backorder SKUs |
| 📊 **Inventory** | Days of supply, stockout %, low-stock SKUs |
| 🏭 **Warehouse Productivity** | Lines/labour-hour, orders/day, SLA adherence |
| 👷 **Employee Productivity** | Picks/hour, error rate, overtime % |
| 📈 **General Analytics** | Statistical overview of any or all 5 collections |

**Try asking:** "What is the fill rate for WH-01?" or "Give me an overview of all collections"."""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_json(data: Any, max_chars: int = 8_000) -> str:
    text = json.dumps(data, indent=2, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    return text


def _fallback_markdown(query: str, results: list, count: int, errors: list) -> str:
    lines = [
        f"## Warehouse KPI Results\n",
        f"**Query:** {query}\n",
        f"**Results found:** {count}\n",
    ]
    if errors:
        lines.append("\n**⚠️ Warnings:**")
        for e in errors:
            lines.append(f"- {e}")
    if results:
        sample = results[:3]
        lines.append(f"\n**Sample Data (first {len(sample)} of {count}):**")
        lines.append(f"```json\n{json.dumps(sample, indent=2, default=str)}\n```")
    return "\n".join(lines)


# ── Main Node ─────────────────────────────────────────────────────────────────

@traceable(name="format_response", tags=["llm", "response_formatting"])
def format_response_node(state: AgentState) -> dict[str, Any]:
    """LLM Call #2 — generate a markdown response from query results."""
    intent             = state.get("classified_intent", "out_of_scope")
    db_results         = state.get("db_results") or []
    result_count       = state.get("result_count", 0)
    collection_results = state.get("collection_results") or {}
    errors             = state.get("errors") or []
    query              = state.get("user_query", "")

    execution_path = list(state.get("execution_path") or [])
    execution_path.append("format_response")

    # ── Out of scope ───────────────────────────────────────────────────────────
    if intent == "out_of_scope":
        return {
            "formatted_response": _OUT_OF_SCOPE_MSG,
            "execution_path":     execution_path,
        }

    # ── Hard error (no data at all) ────────────────────────────────────────────
    if errors and not db_results:
        err_md = "\n".join(f"- `{e}`" for e in errors)
        return {
            "formatted_response": f"## ❌ Error\n\nFailed to retrieve data:\n\n{err_md}",
            "execution_path":     execution_path,
        }

    # ── LLM markdown generation (LLM Call #2) ─────────────────────────────────
    # Use collection_results for rich context; fall back to flat db_results
    data_for_llm = collection_results if collection_results else {"results": db_results}
    collections_queried = sorted(collection_results.keys()) if collection_results else []

    # Build schema context for the collections being queried
    # SKIP schema context for registered_kpi to avoid confusing LLM (KPI results are structured)
    schema_context = ""
    if intent != "registered_kpi" and collections_queried:
        schema_context = "## Schemas for Collections Being Queried (REFERENCE ONLY)\n\n"
        for collection_name in collections_queried:
            schema_context += get_schema_summary(collection_name) + "\n\n"
    
    # Registered KPI uses a stricter prompt that demands per-KPI comments
    system_prompt = _FORMAT_SYSTEM_KPI if intent == "registered_kpi" else _FORMAT_SYSTEM
    
    # For registered_kpi, explicitly list collections to ensure LLM includes all
    collections_note = ""
    if intent == "registered_kpi" and collections_queried:
        collections_note = f"""🚨 MANDATORY INSTRUCTIONS:
1. You MUST create a ## section for EACH of these collections: {', '.join(collections_queried)}
2. Within EACH section, you MUST show ALL KPIs from the JSON data for that collection.
3. DO NOT cherry-pick or omit any KPIs - include EVERY single KPI provided in the data.
4. DO NOT summarize or skip KPIs - show the complete table with ALL rows."""

    prompt = _FORMAT_HUMAN.format(
        query=query,
        intent=intent,
        collections=", ".join(collections_queried) or "N/A",
        result_count=result_count,
        schema_context=schema_context,
        data_json=_to_json(data_for_llm),
        collections_note=collections_note,
    )

    try:
        llm = _get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        markdown = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.error("LLM format_response failed: %s", exc)
        markdown = _fallback_markdown(query, db_results, result_count, errors)

    # ── Update conversation history ────────────────────────────────────────────
    conversation_history = list(state.get("conversation_history") or [])
    conversation_history.append({
        "query": query,
        "response": markdown,
    })

    return {
        "formatted_response": markdown,
        "execution_path":     execution_path,
        "conversation_history": conversation_history,
    }

