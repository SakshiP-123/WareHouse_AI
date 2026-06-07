"""FastAPI wrapper for the Warehouse KPI Agent.

Exposes the LangGraph pipeline over HTTP on http://localhost:8000

Endpoints
---------
GET  /                      health check + welcome
GET  /health                liveness probe (checks MongoDB + Ollama)
GET  /kpis                  list all registered KPI keys with metadata
GET  /collections           list all available collection names
POST /query                 run a natural language query through the graph
POST /kpi                   directly invoke registered KPI calculation
POST /analytics/single      directly invoke analytical stats on one collection
POST /analytics/parallel    directly invoke analytical stats on all collections

Interactive docs: http://localhost:8000/docs
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import app.config.settings as _cfg  # noqa: F401 – triggers sys.path setup + .env load
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo import MongoClient

# Add repo root to path so data_ingestion is importable
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data_ingestion.pipeline import run_pipeline  # noqa: E402

from app.config.settings import MONGODB_DB, MONGODB_URI, OLLAMA_BASE_URL, LLM_MODEL
from app.config.memory import create_session_id, get_session_config
from app.graph.graph_builder import graph
from app.tools import ALL_COLLECTIONS, ALL_KPI_KEYS, KPI_TO_COLLECTION, TOOL_REGISTRY
from app.services.excel_exporter import generate_kpi_excel

# Pull in kpi_registry metadata (lives in workspace root, added to path by settings)
from kpi_registry import KPI_REGISTRY  # type: ignore

logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Warehouse KPI Agent",
    description=(
        "LangGraph-powered warehouse analytics API. "
        "Supports registered KPI calculation and general analytical queries "
        "across 5 MongoDB collections backed by Ollama (qwen2.5:7b)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language question for the agent")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation memory. If omitted, a new session is created."
    )


class QueryResponse(BaseModel):
    query: str
    session_id: str  # Session/thread ID used for this query
    classified_intent: str
    intent_confidence: Optional[float] = None
    entities_extracted: Optional[dict[str, Any]] = None
    target_collections: Optional[list[str]] = None
    result_count: int = 0
    execution_path: Optional[list[str]] = None
    tool_results: Optional[list[dict[str, Any]]] = None
    formatted_response: str
    error: Optional[str] = None
    elapsed_ms: float
    excel_export_path: Optional[str] = None   # set for registered_kpi responses


class KpiRequest(BaseModel):
    kpi_names: Optional[list[str]] = Field(
        default=None,
        description="Specific KPI keys to compute. Omit for all KPIs in the collection.",
    )
    collection: Optional[str] = Field(
        default=None,
        description="Target collection. Required when kpi_names targets a single collection.",
    )
    warehouse_id: Optional[str] = Field(default=None, description="e.g. WH-01")
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")


class AnalyticsRequest(BaseModel):
    collection: Optional[str] = Field(
        default=None,
        description="For single-collection analytics. Omit for parallel (all collections).",
    )
    warehouse_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_collection(raw: Optional[str]) -> Optional[str]:
    """Map a loose collection alias to its canonical name."""
    if not raw:
        return None
    _ALIASES = {
        "inbound": "inbound_parts",
        "outbound": "outbound_parts",
        "inventory": "inventory_snapshot",
        "warehouse": "warehouse_productivity",
        "employee": "employee_productivity",
    }
    key = raw.lower().strip().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(key, key if key in ALL_COLLECTIONS else None)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    """Welcome message and available endpoints."""
    return {
        "service": "Warehouse KPI Agent",
        "version": "1.0.0",
        "llm_model": LLM_MODEL,
        "endpoints": {
            "docs":               "/docs",
            "health":             "/health",
            "kpis":               "/kpis",
            "collections":        "/collections",
            "natural_query":      "POST /query",
            "registered_kpi":     "POST /kpi",
            "analytics_single":   "POST /analytics/single",
            "analytics_parallel": "POST /analytics/parallel",
        },
    }


@app.get("/health", tags=["Info"])
def health_check():
    """Liveness + readiness probe. Checks MongoDB connection."""
    status: dict[str, Any] = {"status": "ok", "checks": {}}

    # MongoDB
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2_000)
        client.admin.command("ping")
        collections_loaded = {
            col: client[MONGODB_DB][col].estimated_document_count()
            for col in ALL_COLLECTIONS
        }
        client.close()
        status["checks"]["mongodb"] = {"status": "ok", "collections": collections_loaded}
    except Exception as exc:
        status["status"] = "degraded"
        status["checks"]["mongodb"] = {"status": "error", "detail": str(exc)}

    status["checks"]["llm"] = {
        "status": "configured",
        "model": LLM_MODEL,
        "base_url": OLLAMA_BASE_URL,
    }

    code = 200 if status["status"] == "ok" else 503
    return JSONResponse(content=status, status_code=code)


@app.get("/kpis", tags=["Info"])
def list_kpis():
    """List all registered KPIs with their metadata from kpi_registry.py."""
    result = []
    for key in ALL_KPI_KEYS:
        meta = KPI_REGISTRY.get(key, {})
        result.append({
            "key":         key,
            "name":        meta.get("name", key),
            "area":        meta.get("area"),
            "type":        meta.get("type"),
            "description": meta.get("description"),
            "collection":  KPI_TO_COLLECTION.get(key),
        })
    return {"total": len(result), "kpis": result}


@app.get("/collections", tags=["Info"])
def list_collections():
    """List the 5 available MongoDB collections."""
    return {"collections": ALL_COLLECTIONS}


@app.post("/query", response_model=QueryResponse, tags=["Agent"])
def natural_query(req: QueryRequest):
    """
    Run a natural language query through the full LangGraph pipeline.

    The agent will:
    1. Classify intent (registered KPI / analytical single / analytical parallel / out-of-scope)
    2. Extract filters (warehouse_id, date range, kpi_name)
    3. Execute the appropriate MongoDB aggregations
    4. Return a formatted narrative response
    """
    t0 = time.perf_counter()
    
    # Create or use existing session for conversation memory
    session_id = req.session_id or create_session_id()
    config = get_session_config(session_id)
    
    try:
        final_state = graph.invoke({"user_query": req.query}, config)
    except Exception as exc:
        logger.exception("Graph invocation error for query: %s", req.query)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    errors: list[str] = final_state.get("errors") or []

    # ── Generate Excel for registered_kpi responses ────────────────────────────
    excel_path: Optional[str] = None
    json_path: Optional[str] = None
    html_path: Optional[str] = None
    if final_state.get("classified_intent") == "registered_kpi":
        try:
            db_results_for_excel = final_state.get("db_results") or []
            excel_file, json_file, html_file = generate_kpi_excel(
                db_results=db_results_for_excel,
                entities=final_state.get("entities_extracted"),
                query=req.query,
            )
            excel_path = str(excel_file) if excel_file else None
            json_path = str(json_file) if json_file else None
            html_path = str(html_file) if html_file else None
            logger.info("KPI Excel exported: %s", excel_path)
        except Exception as exc:
            logger.error("Excel export failed: %s", exc)

    return QueryResponse(
        query=req.query,
        session_id=session_id,
        classified_intent=final_state.get("classified_intent", "unknown"),
        intent_confidence=final_state.get("intent_confidence"),
        entities_extracted=final_state.get("entities_extracted"),
        target_collections=final_state.get("target_collections"),
        result_count=final_state.get("result_count", 0),
        execution_path=final_state.get("execution_path"),
        tool_results=final_state.get("db_results"),
        formatted_response=final_state.get("formatted_response", ""),
        error="; ".join(errors) if errors else None,
        elapsed_ms=elapsed,
        excel_export_path=excel_path,
    )


@app.post("/kpi", tags=["Direct Compute"])
def compute_kpi(req: KpiRequest):
    """
    Directly compute one or more registered KPIs without going through the LLM classifier.

    - Provide **kpi_names** to target specific KPIs (must all belong to the same collection).
    - Provide **collection** to run all KPIs for that collection.
    - Omit both to compute every KPI across all collections.
    """
    t0 = time.perf_counter()
    all_results: list[dict[str, Any]] = []

    if req.kpi_names:
        # Validate all requested KPIs belong to the same collection
        collections_needed = {KPI_TO_COLLECTION.get(k) for k in req.kpi_names}
        unknown = [k for k in req.kpi_names if k not in KPI_TO_COLLECTION]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown KPI keys: {unknown}. Valid keys: {ALL_KPI_KEYS}",
            )
        for col in collections_needed:
            if col:
                tool = TOOL_REGISTRY[col]
                kpis_for_col = [k for k in req.kpi_names if KPI_TO_COLLECTION.get(k) == col]
                all_results.extend(
                    tool.compute_registered_kpis(
                        kpi_names=kpis_for_col,
                        warehouse_id=req.warehouse_id,
                        start_date=req.start_date,
                        end_date=req.end_date,
                    )
                )
    elif req.collection:
        col = _resolve_collection(req.collection)
        if col not in TOOL_REGISTRY:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown collection '{req.collection}'. Valid: {ALL_COLLECTIONS}",
            )
        all_results = TOOL_REGISTRY[col].compute_registered_kpis(
            warehouse_id=req.warehouse_id,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    else:
        # All KPIs across all collections
        for col, tool in TOOL_REGISTRY.items():
            all_results.extend(
                tool.compute_registered_kpis(
                    warehouse_id=req.warehouse_id,
                    start_date=req.start_date,
                    end_date=req.end_date,
                )
            )

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "filters": {
            "warehouse_id": req.warehouse_id,
            "start_date": req.start_date,
            "end_date": req.end_date,
        },
        "result_count": len(all_results),
        "elapsed_ms": elapsed,
        "results": all_results,
    }


@app.post("/analytics/single", tags=["Direct Compute"])
def analytics_single(req: AnalyticsRequest):
    """
    Compute descriptive statistics on a single collection.

    **collection** is required. Use aliases like `inbound`, `outbound`,
    `inventory`, `warehouse`, `employee` or the full collection name.
    """
    col = _resolve_collection(req.collection)
    if not col or col not in TOOL_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown collection '{req.collection}'. "
                f"Valid values: {ALL_COLLECTIONS} or aliases "
                "inbound | outbound | inventory | warehouse | employee"
            ),
        )
    t0 = time.perf_counter()
    try:
        result = TOOL_REGISTRY[col].compute_general_stats(
            warehouse_id=req.warehouse_id,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return {"elapsed_ms": elapsed, **result}


@app.post("/analytics/parallel", tags=["Direct Compute"])
def analytics_parallel(req: AnalyticsRequest):
    """
    Compute descriptive statistics across ALL 5 collections concurrently.

    Optionally filter by **warehouse_id** and/or date range.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0 = time.perf_counter()
    all_results: list[dict[str, Any]] = []
    errors: list[str] = []

    def _fetch(col: str) -> dict:
        return TOOL_REGISTRY[col].compute_general_stats(
            warehouse_id=req.warehouse_id,
            start_date=req.start_date,
            end_date=req.end_date,
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch, col): col for col in TOOL_REGISTRY}
        for future in as_completed(futures):
            col = futures[future]
            try:
                all_results.append(future.result())
            except Exception as exc:
                errors.append(f"{col}: {exc}")

    all_results.sort(key=lambda r: r.get("collection", ""))
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "filters": {
            "warehouse_id": req.warehouse_id,
            "start_date": req.start_date,
            "end_date": req.end_date,
        },
        "collection_count": len(all_results),
        "elapsed_ms": elapsed,
        "errors": errors or None,
        "results": all_results,
    }


@app.post("/data/sync", tags=["Data Management"])
def data_sync():
    """
    Drop all existing data and re-load from the raw CSV files.

    Reads from ``data_ingestion/raw_data/``, prunes, saves to
    ``data_ingestion/pruned/`` and atomically rebuilds all 5 MongoDB
    collections in the ``warehouse_data`` database.

    Returns a per-collection document count and elapsed time.
    """
    t0 = time.perf_counter()
    try:
        run_pipeline()
    except SystemExit as exc:
        raise HTTPException(status_code=500, detail="Pipeline exited — check MongoDB connection") from exc
    except Exception as exc:
        logger.exception("data/sync pipeline error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    elapsed = round((time.perf_counter() - t0) * 1000, 1)

    # Report final counts from warehouse_data
    try:
        from data_ingestion.pipeline import MONGO_URI, MONGO_DB, FILE_TO_COLLECTION  # noqa: PLC0415
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3_000)
        _db = _client[MONGO_DB]
        counts = {
            cname: _db[cname].estimated_document_count()
            for cname in FILE_TO_COLLECTION.values()
        }
        _client.close()
    except Exception:
        counts = {}

    return {
        "status": "ok",
        "message": "Data sync complete — all collections rebuilt from raw CSV files.",
        "elapsed_ms": elapsed,
        "collection_counts": counts,
    }
