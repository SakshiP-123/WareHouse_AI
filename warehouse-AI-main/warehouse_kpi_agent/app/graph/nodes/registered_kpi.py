"""Registered KPI Node.

Handles queries routed as "registered_kpi".

Two modes:
  kpi_scope = "single"  →  compute one specific KPI
  kpi_scope = "all"     →  compute all KPIs (optionally filtered by warehouse/date)

The node groups KPIs by their owning collection and calls each tool in turn.
Results are stored in state["tool_results"].
"""

import logging
from typing import Any, Optional

from langsmith import traceable

from app.graph.state import GraphState
from app.tools import KPI_TO_COLLECTION, TOOL_REGISTRY

logger = logging.getLogger(__name__)


def _run_kpis_for_collection(
    collection: str,
    kpi_names: Optional[list[str]],
    warehouse_id: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> list[dict[str, Any]]:
    """Call the compute_registered_kpis function for a single collection."""
    tool = TOOL_REGISTRY.get(collection)
    if tool is None:
        logger.warning("No tool found for collection: %s", collection)
        return []
    try:
        return tool.compute_registered_kpis(
            kpi_names=kpi_names,
            warehouse_id=warehouse_id,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        logger.error("Error computing KPIs for %s: %s", collection, exc)
        return [{"collection": collection, "error": str(exc)}]


@traceable(name="registered_kpi_node", tags=["graph_node", "kpi"])
def registered_kpi_node(state: GraphState) -> dict[str, Any]:
    """Compute registered KPIs based on the classified intent."""
    # ── Extract entities and query_params from correct state fields ────────────
    entities: dict[str, Any] = state.get("entities_extracted") or {}
    query_params: dict[str, Any] = state.get("query_params") or {}

    warehouse_id: Optional[str] = entities.get("warehouse_id")
    start_date:   Optional[str] = entities.get("start_date")
    end_date:     Optional[str] = entities.get("end_date")

    # kpi_names list wins over a single kpi_name entity
    kpi_names: list[str] = query_params.get("kpi_names") or []
    kpi_name:  Optional[str] = kpi_names[0] if kpi_names else entities.get("kpi_name")

    # If no specific KPI is named → always compute ALL KPIs
    kpi_scope: str = query_params.get("kpi_scope") or ("single" if kpi_name else "all")

    logger.info(
        "Registered KPI node: scope=%s kpi=%s wh=%s %s→%s",
        kpi_scope, kpi_name, warehouse_id, start_date, end_date,
    )

    all_results: list[dict[str, Any]] = []

    if kpi_scope == "single" and kpi_name:
        # Single KPI: look up its collection and call only that tool
        collection = KPI_TO_COLLECTION.get(kpi_name)
        if collection:
            all_results = _run_kpis_for_collection(
                collection, [kpi_name], warehouse_id, start_date, end_date
            )
        else:
            logger.warning("KPI '%s' not found in registry.", kpi_name)
            return {
                "collection_results": {},
                "db_results": [],
                "result_count": 0,
                "execution_path": list(state.get("execution_path") or []) + ["registered_kpi_handler"],
                "errors": [f"KPI '{kpi_name}' is not registered in the KPI registry."],
            }
    else:
        # All KPIs: iterate over every collection
        for collection, tool in TOOL_REGISTRY.items():
            results = _run_kpis_for_collection(
                collection, None, warehouse_id, start_date, end_date
            )
            all_results.extend(results)

    # ── Build collection_results keyed dict (expected by join_results / format_response) ──
    collection_results: dict[str, Any] = {}
    for item in all_results:
        col = item.get("collection", "unknown")
        if col not in collection_results:
            collection_results[col] = {"collection": col, "type": "registered_kpi", "results": []}
        collection_results[col]["results"].append(item)

    execution_path = list(state.get("execution_path") or [])
    execution_path.append("registered_kpi_handler")

    return {
        "collection_results": collection_results,
        "db_results": all_results,
        "result_count": len(all_results),
        "execution_path": execution_path,
        "errors": [],
    }
