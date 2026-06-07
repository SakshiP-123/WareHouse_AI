"""Single Query Handler Node.

Handles queries routed to a SINGLE collection:
  - registered_kpi  (single KPI or all KPIs for one collection)
  - analytical_single (general stats on one collection)

Execution path entry: "query_<collection_name>"
State writes: collection_results, db_results, result_count, execution_path, errors
"""

import logging
from typing import Any

from langsmith import traceable

from app.graph.nodes.query_tools import query_collection
from app.graph.state import AgentState
from app.tools import ALL_COLLECTIONS, KPI_TO_COLLECTION, resolve_collection

logger = logging.getLogger(__name__)


@traceable(name="single_query_handler_node", tags=["graph_node", "query"])
def single_query_handler_node(state: AgentState) -> dict[str, Any]:
    """Query a single collection and populate state with results."""
    intent          = state.get("classified_intent")
    entities        = state.get("entities_extracted") or {}
    query_params    = state.get("query_params") or {}
    target_cols     = state.get("target_collections") or []
    user_query      = state.get("user_query", "")
    execution_path  = list(state.get("execution_path") or [])
    errors          = list(state.get("errors") or [])

    # ── Resolve which collection to query ──────────────────────────────────────
    collection: str | None = None

    if target_cols:
        raw = target_cols[0]
        collection = resolve_collection(raw) or (raw if raw in ALL_COLLECTIONS else None)

    if not collection and intent == "registered_kpi":
        # Infer from KPI name in query_params or entities
        kpi_names = query_params.get("kpi_names") or []
        kpi_name  = (kpi_names[0] if kpi_names else None) or entities.get("kpi_name")
        if kpi_name:
            collection = KPI_TO_COLLECTION.get(kpi_name)

    if not collection:
        collection = entities.get("collection", "inbound_parts")
        logger.warning("Could not resolve collection — defaulting to %s", collection)

    logger.info("single_query_handler: collection=%s  intent=%s", collection, intent)
    execution_path.append(f"query_{collection}")

    # ── Execute query ──────────────────────────────────────────────────────────
    col_result = query_collection(collection, intent, entities, query_params, user_query=user_query)

    if "error" in col_result:
        errors.append(col_result["error"])

    db_results = col_result.get("results", [])

    return {
        "collection_results": {collection: col_result},
        "db_results":         db_results,
        "result_count":       col_result.get("count", len(db_results)),
        "execution_path":     execution_path,
        "errors":             errors,
    }
