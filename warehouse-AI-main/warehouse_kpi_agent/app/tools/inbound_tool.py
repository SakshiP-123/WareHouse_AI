"""Inbound Parts collection KPI tool.

Registered KPIs:
  - avg_inbound_lead_time
  - on_time_receipts_pct
  - qty_discrepancy_pct
  - top_delaying_suppliers
"""

import logging
from typing import Any, Optional

from app.tools.base import build_match, first_value, get_collection, pct, safe_run

logger = logging.getLogger(__name__)
COLLECTION = "inbound_parts"
DATE_FIELD = "expected_date"


# ── Individual KPI computations ───────────────────────────────────────────────

def _avg_inbound_lead_time(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "value": {"$avg": "$inbound_lead_time_days"},
            "count": {"$sum": 1},
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    val = first_value(rows)
    return {
        "kpi": "avg_inbound_lead_time",
        "name": "Avg Inbound Lead Time",
        "value": val,
        "unit": "days",
        "record_count": rows[0].get("count") if rows else 0,
    }


def _on_time_receipts_pct(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "on_time": {"$sum": {
                "$cond": [{"$lte": ["$inbound_lead_time_days", 0]}, 1, 0]
            }},
        }},
        {"$project": {
            "value": {"$divide": ["$on_time", "$total"]},
            "count": "$total",
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    val = pct(first_value(rows))
    return {
        "kpi": "on_time_receipts_pct",
        "name": "% Receipts On-Time",
        "value": val,
        "unit": "%",
        "record_count": rows[0].get("count") if rows else 0,
    }


def _qty_discrepancy_pct(match: dict) -> dict:
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total_discrepancy": {"$sum": "$discrepancy_qty"},
            "total_ordered": {"$sum": "$qty_ordered"},
        }},
        {"$project": {
            "value": {
                "$cond": [
                    {"$gt": ["$total_ordered", 0]},
                    {"$divide": ["$total_discrepancy", "$total_ordered"]},
                    0,
                ]
            }
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    val = pct(first_value(rows))
    return {
        "kpi": "qty_discrepancy_pct",
        "name": "% Qty Discrepancies",
        "value": val,
        "unit": "%",
    }


def _top_delaying_suppliers(match: dict) -> dict:
    late_match = {**match, "inbound_lead_time_days": {"$gt": 0}}
    pipeline = [
        {"$match": late_match},
        {"$group": {
            "_id": "$supplier_name",
            "late_count": {"$sum": 1},
            "avg_delay_days": {"$avg": "$inbound_lead_time_days"},
            "total_discrepancy": {"$sum": "$discrepancy_qty"},
        }},
        {"$sort": {"late_count": -1}},
        {"$limit": 5},
        {"$project": {
            "_id": 0,
            "supplier_name": "$_id",
            "late_count": 1,
            "avg_delay_days": {"$round": ["$avg_delay_days", 1]},
            "total_discrepancy": 1,
        }},
    ]
    rows = safe_run(pipeline, get_collection(COLLECTION))
    return {
        "kpi": "top_delaying_suppliers",
        "name": "Top 5 Delaying Suppliers",
        "value": rows,
        "unit": "list",
    }


# ── KPI dispatch ──────────────────────────────────────────────────────────────

_KPI_FN = {
    "avg_inbound_lead_time": _avg_inbound_lead_time,
    "on_time_receipts_pct": _on_time_receipts_pct,
    "qty_discrepancy_pct": _qty_discrepancy_pct,
    "top_delaying_suppliers": _top_delaying_suppliers,
}
ALL_KPIS = list(_KPI_FN.keys())


def compute_registered_kpis(
    kpi_names: Optional[list[str]] = None,
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Run one or all registered KPIs for the inbound_parts collection."""
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
            logger.warning("Unknown inbound KPI: %s", kpi)
    return results


# ── General stats (analytical) ────────────────────────────────────────────────

def compute_general_stats(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_query: Optional[str] = None,
) -> dict[str, Any]:
    """Compute descriptive statistics on the inbound_parts collection.
    
    If user_query is provided, uses LLM to generate MongoDB pipeline.
    """
    col = get_collection(COLLECTION)
    
    # ── LLM-based query generation ─────────────────────────────────────────────
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
            "total_records": {"$sum": 1},
            "avg_lead_time_days": {"$avg": "$inbound_lead_time_days"},
            "max_lead_time_days": {"$max": "$inbound_lead_time_days"},
            "min_lead_time_days": {"$min": "$inbound_lead_time_days"},
            "total_qty_ordered": {"$sum": "$qty_ordered"},
            "total_qty_received": {"$sum": "$qty_received"},
            "total_discrepancy": {"$sum": "$discrepancy_qty"},
            "on_time_count": {"$sum": {
                "$cond": [{"$lte": ["$inbound_lead_time_days", 0]}, 1, 0]
            }},
        }},
        {"$project": {
            "_id": 0,
            "total_records": 1,
            "avg_lead_time_days": {"$round": ["$avg_lead_time_days", 2]},
            "max_lead_time_days": 1,
            "min_lead_time_days": 1,
            "total_qty_ordered": 1,
            "total_qty_received": 1,
            "total_discrepancy": 1,
            "on_time_pct": {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$on_time_count", "$total_records"]},
                        100,
                    ]},
                    2,
                ]
            },
            "discrepancy_pct": {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$total_discrepancy", "$total_qty_ordered"]},
                        100,
                    ]},
                    2,
                ]
            },
        }},
    ]

    stats = safe_run(pipeline, col)
    summary = stats[0] if stats else {}

    # Top suppliers by PO count
    top_sup_pipeline = [
        {"$match": match},
        {"$group": {"_id": "$supplier_name", "po_count": {"$sum": 1}}},
        {"$sort": {"po_count": -1}},
        {"$limit": 5},
        {"$project": {"_id": 0, "supplier": "$_id", "po_count": 1}},
    ]
    top_suppliers = safe_run(top_sup_pipeline, col)

    # By warehouse breakdown
    wh_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$warehouse_id",
            "count": {"$sum": 1},
            "avg_lead": {"$avg": "$inbound_lead_time_days"},
        }},
        {"$project": {
            "_id": 0,
            "warehouse_id": "$_id",
            "record_count": "$count",
            "avg_lead_time_days": {"$round": ["$avg_lead", 2]},
        }},
        {"$sort": {"warehouse_id": 1}},
    ]
    by_warehouse = safe_run(wh_pipeline, col)

    return {
        "collection": COLLECTION,
        "analysis_type": "general_stats",
        "summary": summary,
        "top_suppliers": top_suppliers,
        "by_warehouse": by_warehouse,
    }
