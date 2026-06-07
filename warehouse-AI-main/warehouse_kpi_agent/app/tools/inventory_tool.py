"""Inventory Snapshot collection KPI tool.

Registered KPIs:
  - days_of_supply
  - stockout_pct
"""

import logging
from typing import Any, Optional

from app.tools.base import build_match, first_value, get_collection, pct, safe_run

logger = logging.getLogger(__name__)
COLLECTION = "inventory_snapshot"
DATE_FIELD = "snapshot_date"


# ── Individual KPI computations ───────────────────────────────────────────────

def _days_of_supply(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "value": {"$avg": "$days_of_supply"},
            "count": {"$sum": 1},
        }},
        {"$project": {"value": {"$round": ["$value", 2]}, "count": 1}},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "days_of_supply",
        "name": "Days of Supply",
        "value": first_value(rows),
        "unit": "days",
        "record_count": rows[0].get("count") if rows else 0,
    }


def _stockout_pct(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "stockouts": {"$sum": "$stockout_flag"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total", 0]},
                    {"$divide": ["$stockouts", "$total"]},
                    None,
                ]
            },
            "count": "$total",
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "stockout_pct",
        "name": "% Stock-out Days",
        "value": pct(first_value(rows)),
        "unit": "%",
        "record_count": rows[0].get("count") if rows else 0,
    }


# ── KPI dispatch ──────────────────────────────────────────────────────────────

_KPI_FN = {
    "days_of_supply": _days_of_supply,
    "stockout_pct": _stockout_pct,
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
            logger.warning("Unknown inventory KPI: %s", kpi)
    return results


# ── General stats (analytical) ────────────────────────────────────────────────

def compute_general_stats(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Compute general statistics for inventory snapshot.
    
    If user_query is provided, uses LLM to generate MongoDB pipeline.
    """
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
    # For standard stats: use extracted filters
    match = build_match(warehouse_id, start_date, end_date, DATE_FIELD)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_snapshots": {"$sum": 1},
            "avg_on_hand": {"$avg": "$on_hand_qty"},
            "avg_available": {"$avg": "$available_qty"},
            "avg_days_of_supply": {"$avg": "$days_of_supply"},
            "avg_age_days": {"$avg": "$age_days"},
            "stockout_count": {"$sum": "$stockout_flag"},
            "total_on_hand": {"$sum": "$on_hand_qty"},
        }},
        {"$project": {
            "_id": 0,
            "total_snapshots": 1,
            "avg_on_hand_qty": {"$round": ["$avg_on_hand", 0]},
            "avg_available_qty": {"$round": ["$avg_available", 0]},
            "avg_days_of_supply": {"$round": ["$avg_days_of_supply", 1]},
            "avg_age_days": {"$round": ["$avg_age_days", 1]},
            "total_on_hand_qty": 1,
            "stockout_pct": {"$round": [{"$multiply": [
                {"$divide": ["$stockout_count", "$total_snapshots"]}, 100
            ]}, 2]},
        }},
    ]
    summary = safe_run(pipeline, col)

    # Low-stock SKUs (available_qty <= safety_stock)
    low_stock_pipeline = [
        {"$match": {**match, "$expr": {"$lte": ["$available_qty", "$safety_stock"]}}},
        {"$group": {"_id": "$part_number", "wh_count": {"$sum": 1}}},
        {"$sort": {"wh_count": -1}},
        {"$limit": 10},
        {"$project": {"_id": 0, "part_number": "$_id", "low_stock_warehouses": "$wh_count"}},
    ]
    low_stock = safe_run(low_stock_pipeline, col)

    # By warehouse
    wh_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$warehouse_id",
            "sku_count": {"$sum": 1},
            "avg_dos": {"$avg": "$days_of_supply"},
            "stockouts": {"$sum": "$stockout_flag"},
        }},
        {"$project": {
            "_id": 0,
            "warehouse_id": "$_id",
            "sku_count": 1,
            "avg_days_of_supply": {"$round": ["$avg_dos", 1]},
            "stockout_count": "$stockouts",
        }},
        {"$sort": {"warehouse_id": 1}},
    ]
    by_warehouse = safe_run(wh_pipeline, col)

    return {
        "collection": COLLECTION,
        "analysis_type": "general_stats",
        "summary": summary[0] if summary else {},
        "low_stock_skus": low_stock,
        "by_warehouse": by_warehouse,
    }
