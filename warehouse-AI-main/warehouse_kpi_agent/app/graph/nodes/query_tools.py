"""Per-collection query functions.

These are the underlying workers called by both SingleQueryHandler and
ParallelQueryHandler nodes. Each call dispatches to the right tool
method based on the classified intent.

query_collection(collection, intent, entities, query_params)
  ├── intent == "registered_kpi"  → tool.compute_registered_kpis(...)
  └── intent == analytical_*      → tool.compute_general_stats(...)
"""

import logging
from typing import Any, Optional

from app.tools import ALL_COLLECTIONS, TOOL_REGISTRY

logger = logging.getLogger(__name__)


def query_collection(
    collection: str,
    intent: Optional[str],
    entities: Optional[dict[str, Any]],
    query_params: Optional[dict[str, Any]],
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Execute the appropriate query on a single collection.

    Args:
        collection:   Canonical collection name (must exist in TOOL_REGISTRY).
        intent:       Classified intent string from AgentState.
        entities:     Extracted entities dict (warehouse_id, start_date, end_date, …).
        query_params: Additional params dict (kpi_names, kpi_scope, …).
        user_query:   Original user question for dynamic query building.

    Returns:
        dict with keys:
            collection  – collection name
            type        – "registered_kpi" | "analytical" | "error"
            results     – list of result dicts
            count       – number of result items
            error       – (only on failure) error message string
    """
    tool = TOOL_REGISTRY.get(collection)
    if tool is None:
        err = f"Unknown collection '{collection}'. Valid: {ALL_COLLECTIONS}"
        logger.warning(err)
        return {"collection": collection, "type": "error", "results": [], "count": 0, "error": err}

    e = entities or {}
    p = query_params or {}
    warehouse_id = e.get("warehouse_id")
    start_date   = e.get("start_date")
    end_date     = e.get("end_date")
    employee_id  = e.get("employee_id")

    try:
        if intent == "registered_kpi":
            kpi_names = p.get("kpi_names") or None
            results = tool.compute_registered_kpis(
                kpi_names=kpi_names,
                warehouse_id=warehouse_id,
                start_date=start_date,
                end_date=end_date,
            )
            return {
                "collection": collection,
                "type": "registered_kpi",
                "results": results,
                "count": len(results),
            }
        else:
            # analytical_single or analytical_parallel
            # Pass employee_id and user_query for tools that support them
            import inspect
            sig = inspect.signature(tool.compute_general_stats)
            kwargs: dict = dict(
                warehouse_id=warehouse_id,
                start_date=start_date,
                end_date=end_date,
            )
            if "employee_id" in sig.parameters:
                kwargs["employee_id"] = employee_id
            if "user_query" in sig.parameters:
                kwargs["user_query"] = user_query
            stats = tool.compute_general_stats(**kwargs)
            return {
                "collection": collection,
                "type": "analytical",
                "results": [stats],
                "count": 1,
            }
    except Exception as exc:
        logger.error("query_collection error [%s]: %s", collection, exc)
        return {
            "collection": collection,
            "type": "error",
            "results": [],
            "count": 0,
            "error": str(exc),
        }
