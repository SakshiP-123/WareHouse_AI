"""Employee Productivity collection KPI tool.

Registered KPIs:
  - picks_per_hour
  - error_rate
  - overtime_pct
"""

import logging
from typing import Any, Optional

from app.tools.base import build_match, first_value, get_collection, pct, safe_run

logger = logging.getLogger(__name__)
COLLECTION = "employee_productivity"
DATE_FIELD = "date"


# ── Individual KPI computations ───────────────────────────────────────────────

def _picks_per_hour(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_picks": {"$sum": "$picks"},
            "total_hours": {"$sum": "$hours_worked"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_hours", 0]},
                    {"$round": [{"$divide": ["$total_picks", "$total_hours"]}, 2]},
                    None,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "picks_per_hour",
        "name": "Picks per Person per Hour",
        "value": first_value(rows),
        "unit": "picks/hr",
    }


def _error_rate(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_errors": {"$sum": "$errors"},
            "total_tasks": {"$sum": "$tasks_completed"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_tasks", 0]},
                    {"$divide": ["$total_errors", "$total_tasks"]},
                    None,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "error_rate",
        "name": "Error Rate",
        "value": pct(first_value(rows)),
        "unit": "%",
    }


def _overtime_pct(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_overtime": {"$sum": "$overtime_hours"},
            "total_regular": {"$sum": "$hours_worked"},
        }},
        {"$project": {
            "total_hours": {"$add": ["$total_overtime", "$total_regular"]},
            "total_overtime": 1,
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_hours", 0]},
                    {"$divide": ["$total_overtime", "$total_hours"]},
                    None,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "overtime_pct",
        "name": "Overtime %",
        "value": pct(first_value(rows)),
        "unit": "%",
    }


# ── KPI dispatch ──────────────────────────────────────────────────────────────

_KPI_FN = {
    "picks_per_hour": _picks_per_hour,
    "error_rate": _error_rate,
    "overtime_pct": _overtime_pct,
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
            logger.warning("Unknown employee KPI: %s", kpi)
    return results


# ── General stats (analytical) ────────────────────────────────────────────────

def compute_general_stats(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    employee_id: Optional[str] = None,
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Compute general statistics for employee productivity.
    
    If user_query is provided, uses LLM to generate MongoDB pipeline.
    Otherwise falls back to standard analytical stats.
    """
    col = get_collection(COLLECTION)
    
    # ── LLM-based query generation ────────────────────────────────────────────
    if user_query:
        from app.tools.llm_query_generator import execute_llm_query
        
        # For LLM mode: use EMPTY base_match to let LLM handle all filtering
        # The LLM will parse warehouse, dates, employee from the natural language query
        llm_result = execute_llm_query(
            user_query=user_query,
            collection_name=COLLECTION,
            collection_obj=col,
            base_match={},  # Empty - let LLM do all filtering
        )
        
        # If LLM query succeeded, return results
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
    match = build_match(warehouse_id, start_date, end_date, DATE_FIELD, employee_id=employee_id)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_records": {"$sum": 1},
            "unique_employees": {"$addToSet": "$employee_id"},
            "total_picks": {"$sum": "$picks"},
            "total_hours": {"$sum": "$hours_worked"},
            "total_errors": {"$sum": "$errors"},
            "total_tasks": {"$sum": "$tasks_completed"},
            "total_overtime": {"$sum": "$overtime_hours"},
        }},
        {"$project": {
            "_id": 0,
            "total_records": 1,
            "employee_count": {"$size": "$unique_employees"},
            "total_picks": 1,
            "total_hours": {"$round": ["$total_hours", 1]},
            "total_errors": 1,
            "total_tasks": 1,
            "total_overtime_hours": {"$round": ["$total_overtime", 1]},
            "picks_per_hour": {"$round": [
                {"$divide": ["$total_picks", "$total_hours"]}, 2
            ]},
            "error_rate_pct": {"$round": [{"$multiply": [
                {"$divide": ["$total_errors", "$total_tasks"]}, 100
            ]}, 2]},
            "overtime_pct": {"$round": [{"$multiply": [
                {"$divide": [
                    "$total_overtime",
                    {"$add": ["$total_hours", "$total_overtime"]}
                ]}, 100
            ]}, 2]},
        }},
    ]
    summary = safe_run(pipeline, col)

    # By role
    role_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$role",
            "count": {"$sum": 1},
            "avg_picks_per_hour": {"$avg": "$picks_per_hour"},
            "avg_errors": {"$avg": "$errors"},
        }},
        {"$project": {
            "_id": 0,
            "role": "$_id",
            "count": 1,
            "avg_picks_per_hour": {"$round": ["$avg_picks_per_hour", 2]},
            "avg_errors": {"$round": ["$avg_errors", 2]},
        }},
        {"$sort": {"count": -1}},
    ]
    by_role = safe_run(role_pipeline, col)

    # Top performers (by avg picks_per_hour)
    top_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$employee_id",
            "avg_picks_per_hour": {"$avg": "$picks_per_hour"},
            "total_errors": {"$sum": "$errors"},
        }},
        {"$sort": {"avg_picks_per_hour": -1}},
        {"$limit": 5},
        {"$project": {
            "_id": 0,
            "employee_id": "$_id",
            "avg_picks_per_hour": {"$round": ["$avg_picks_per_hour", 2]},
            "total_errors": 1,
        }},
    ]
    top_performers = safe_run(top_pipeline, col)

    return {
        "collection": COLLECTION,
        "analysis_type": "general_stats",
        "summary": summary[0] if summary else {},
        "by_role": by_role,
        "top_performers": top_performers,
    }
