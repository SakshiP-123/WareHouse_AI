"""Outbound Parts collection KPI tool.

Registered KPIs:
  - fill_rate
  - otif
  - backorder_rate
  - top_backorder_skus
"""

import logging
from typing import Any, Optional

from app.tools.base import build_match, first_value, get_collection, pct, safe_run

logger = logging.getLogger(__name__)
COLLECTION = "outbound_parts"
DATE_FIELD = "order_date"


# ── Individual KPI computations ───────────────────────────────────────────────

def _fill_rate(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_shipped": {"$sum": "$qty_shipped"},
            "total_ordered": {"$sum": "$qty_ordered"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_ordered", 0]},
                    {"$divide": ["$total_shipped", "$total_ordered"]},
                    None,
                ]
            },
            "count": {"$sum": 1},
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "fill_rate",
        "name": "Fill Rate",
        "value": pct(first_value(rows)),
        "unit": "%",
    }


def _otif(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "otif_count": {"$sum": "$otif_flag"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total", 0]},
                    {"$divide": ["$otif_count", "$total"]},
                    None,
                ]
            },
            "count": "$total",
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "otif",
        "name": "OTIF %",
        "value": pct(first_value(rows)),
        "unit": "%",
        "record_count": rows[0].get("count") if rows else 0,
    }


def _backorder_rate(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_backorder": {"$sum": "$backorder_qty"},
            "total_ordered": {"$sum": "$qty_ordered"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_ordered", 0]},
                    {"$divide": ["$total_backorder", "$total_ordered"]},
                    None,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "backorder_rate",
        "name": "Backorder Rate",
        "value": pct(first_value(rows)),
        "unit": "%",
    }


def _top_backorder_skus(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$part_number",
            "total_backorder": {"$sum": "$backorder_qty"},
            "order_count": {"$sum": 1},
        }},
        {"$sort": {"total_backorder": -1}},
        {"$limit": 10},
        {"$project": {
            "_id": 0,
            "part_number": "$_id",
            "total_backorder": 1,
            "order_count": 1,
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "top_backorder_skus",
        "name": "Top 10 SKUs by Backorder",
        "value": rows,
        "unit": "list",
    }


# ── KPI dispatch ──────────────────────────────────────────────────────────────

_KPI_FN = {
    "fill_rate": _fill_rate,
    "otif": _otif,
    "backorder_rate": _backorder_rate,
    "top_backorder_skus": _top_backorder_skus,
}
ALL_KPIS = list(_KPI_FN.keys())


def compute_registered_kpis(
    kpi_names: Optional[list[str]] = None,
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    match = build_match(warehouse_id, start_date, end_date, DATE_FIELD)
    names = kpi_names if kpi_names else ALL_KPIS
    results = []
    for kpi in names:
        fn = _KPI_FN.get(kpi)
        if fn:
            result = fn(match)
            result["collection"] = COLLECTION
            result["filters"] = {
                "warehouse_id": warehouse_id,
                "start_date": start_date,
                "end_date": end_date,
            }
            results.append(result)
        else:
            logger.warning("Unknown outbound KPI: %s", kpi)
    return results


# ── General stats (analytical) ────────────────────────────────────────────────

def compute_general_stats(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Compute general statistics for outbound parts.
    
    If user_query is provided, uses LLM to generate MongoDB pipeline.
    """
    match = build_match(warehouse_id, start_date, end_date, DATE_FIELD)
    col = get_collection(COLLECTION)
    
    # ── LLM-based query generation ────────────────────────────────────────────
    if user_query:
        from app.tools.llm_query_generator import execute_llm_query
        
        llm_result = execute_llm_query(
            user_query=user_query,
            collection_name=COLLECTION,
            collection_obj=col,
            base_match={},  # Empty - let LLM do all filtering
        )
        
        if llm_result.get("results"):
            return {
                "collection": COLLECTION,
                "analysis_type": "llm_generated",
                "results": llm_result["results"],
                "count": llm_result["count"],
                "pipeline": llm_result["pipeline"],
                "query_used": "llm",
            }
        elif llm_result.get("error"):
            logger.warning(f"LLM query failed: {llm_result['error']}, falling back to standard stats")
    
    # ── Standard analytical stats (fallback) ───────────────────────────────────
    # For standard stats: use extracted filters
    match = build_match(warehouse_id, start_date, end_date, DATE_FIELD)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_orders": {"$sum": 1},
            "total_qty_ordered": {"$sum": "$qty_ordered"},
            "total_qty_shipped": {"$sum": "$qty_shipped"},
            "total_backorder": {"$sum": "$backorder_qty"},
            "total_otif": {"$sum": "$otif_flag"},
            "avg_fill_rate": {"$avg": "$fill_rate"},
        }},
        {"$project": {
            "_id": 0,
            "total_orders": 1,
            "total_qty_ordered": 1,
            "total_qty_shipped": 1,
            "total_backorder": 1,
            "fill_rate_pct": {"$round": [{"$multiply": [
                {"$divide": ["$total_qty_shipped", "$total_qty_ordered"]}, 100
            ]}, 2]},
            "otif_pct": {"$round": [{"$multiply": [
                {"$divide": ["$total_otif", "$total_orders"]}, 100
            ]}, 2]},
            "backorder_rate_pct": {"$round": [{"$multiply": [
                {"$divide": ["$total_backorder", "$total_qty_ordered"]}, 100
            ]}, 2]},
        }},
    ]
    summary = safe_run(pipeline, col)

    # Top customers by order volume
    cust_pipeline = [
        {"$match": match},
        {"$group": {"_id": "$customer_name", "orders": {"$sum": 1}}},
        {"$sort": {"orders": -1}},
        {"$limit": 5},
        {"$project": {"_id": 0, "customer": "$_id", "orders": 1}},
    ]
    top_customers = safe_run(cust_pipeline, col)

    # By warehouse
    wh_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$warehouse_id",
            "orders": {"$sum": 1},
            "avg_otif": {"$avg": "$otif_flag"},
        }},
        {"$project": {
            "_id": 0,
            "warehouse_id": "$_id",
            "orders": 1,
            "otif_pct": {"$round": [{"$multiply": ["$avg_otif", 100]}, 2]},
        }},
        {"$sort": {"warehouse_id": 1}},
    ]
    by_warehouse = safe_run(wh_pipeline, col)

    return {
        "collection": COLLECTION,
        "analysis_type": "general_stats",
        "summary": summary[0] if summary else {},
        "top_customers": top_customers,
        "by_warehouse": by_warehouse,
    }
