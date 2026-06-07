"""Warehouse Productivity collection KPI tool.

Registered KPIs:
  - lines_per_labor_hour
  - orders_per_day
  - sla_adherence
"""

import logging
from typing import Any, Optional

from app.tools.base import build_match, first_value, get_collection, pct, safe_run

logger = logging.getLogger(__name__)
COLLECTION = "warehouse_productivity"
DATE_FIELD = "date"


# ── Individual KPI computations ───────────────────────────────────────────────

def _lines_per_labor_hour(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_lines": {"$sum": "$lines_picked"},
            "total_hours": {"$sum": "$labor_hours"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_hours", 0]},
                    {"$round": [{"$divide": ["$total_lines", "$total_hours"]}, 2]},
                    None,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "lines_per_labor_hour",
        "name": "Lines Picked per Labor-Hour",
        "value": first_value(rows),
        "unit": "lines/hr",
    }


def _orders_per_day(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "value": {"$sum": "$orders_processed"},
            "shift_count": {"$sum": 1},
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    total = first_value(rows)
    shifts = rows[0].get("shift_count", 1) if rows else 1
    return {
        "kpi": "orders_per_day",
        "name": "Orders per Day",
        "value": total,
        "unit": "orders",
        "shift_count": shifts,
    }


def _sla_adherence(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "value": {"$avg": "$sla_adherence_pct"},
            "count": {"$sum": 1},
        }},
        {"$project": {"value": {"$round": [{"$multiply": ["$value", 100]}, 2]}, "count": 1}},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "sla_adherence",
        "name": "SLA Adherence",
        "value": first_value(rows),
        "unit": "%",
        "record_count": rows[0].get("count") if rows else 0,
    }


# ── KPI dispatch ──────────────────────────────────────────────────────────────

_KPI_FN = {
    "lines_per_labor_hour": _lines_per_labor_hour,
    "orders_per_day": _orders_per_day,
    "sla_adherence": _sla_adherence,
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
            logger.warning("Unknown warehouse KPI: %s", kpi)
    return results


# ── General stats (analytical) ────────────────────────────────────────────────

def compute_general_stats(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Compute general statistics for warehouse productivity.
    
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
    
    logger.debug("compute_general_stats called with: warehouse_id=%s, start_date=%s, end_date=%s", 
                 warehouse_id, start_date, end_date)
    logger.debug("Match filter: %s", match)
    logger.debug("Collection: %s, total docs: %d", COLLECTION, col.count_documents({}))

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_records": {"$sum": 1},
            "total_lines_picked": {"$sum": "$lines_picked"},
            "total_orders": {"$sum": "$orders_processed"},
            "total_labor_hours": {"$sum": "$labor_hours"},
            "avg_sla": {"$avg": "$sla_adherence_pct"},
            "avg_picks_per_hour": {"$avg": "$picks_per_hour"},
            "avg_equipment_util": {"$avg": "$equipment_utilization_pct"},
        }},
        {"$project": {
            "_id": 0,
            "total_records": 1,
            "total_lines_picked": 1,
            "total_orders_processed": "$total_orders",
            "total_labor_hours": {"$round": ["$total_labor_hours", 1]},
            "avg_sla_pct": {"$round": [{"$multiply": ["$avg_sla", 100]}, 2]},
            "avg_picks_per_hour": {"$round": ["$avg_picks_per_hour", 2]},
            "avg_equipment_utilization_pct": {"$round": [{"$multiply": ["$avg_equipment_util", 100]}, 2]},
            "lines_per_labor_hour": {"$round": [
                {"$divide": ["$total_lines_picked", "$total_labor_hours"]}, 2
            ]},
        }},
    ]
    summary = safe_run(pipeline, col)

    # Shift breakdown
    shift_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$shift",
            "records": {"$sum": 1},
            "avg_sla": {"$avg": "$sla_adherence_pct"},
            "total_orders": {"$sum": "$orders_processed"},
        }},
        {"$project": {
            "_id": 0,
            "shift": "$_id",
            "records": 1,
            "total_orders": 1,
            "avg_sla_pct": {"$round": [{"$multiply": ["$avg_sla", 100]}, 2]},
        }},
    ]
    by_shift = safe_run(shift_pipeline, col)

    # By warehouse
    wh_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$warehouse_id",
            "total_orders": {"$sum": "$orders_processed"},
            "avg_sla": {"$avg": "$sla_adherence_pct"},
            "total_hours": {"$sum": "$labor_hours"},
        }},
        {"$project": {
            "_id": 0,
            "warehouse_id": "$_id",
            "total_orders": 1,
            "avg_sla_pct": {"$round": [{"$multiply": ["$avg_sla", 100]}, 2]},
            "total_labor_hours": {"$round": ["$total_hours", 1]},
        }},
        {"$sort": {"warehouse_id": 1}},
    ]
    by_warehouse = safe_run(wh_pipeline, col)

    # Warehouse count
    warehouse_count = len(by_warehouse)

    return {
        "collection": COLLECTION,
        "analysis_type": "general_stats",
        "warehouse_count": warehouse_count,
        "summary": summary[0] if summary else {},
        "by_shift": by_shift,
        "by_warehouse": by_warehouse,
    }
