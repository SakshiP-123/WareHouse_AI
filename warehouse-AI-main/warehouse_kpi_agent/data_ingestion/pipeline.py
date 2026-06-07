#!/usr/bin/env python3
"""
Warehouse Data Ingestion Pipeline
==================================
raw_data/ ──► prune (type-safe + UTC dates) ──► pruned/ ──► MongoDB(warehouse_data)

Usage:
    python data_ingestion/pipeline.py
    python -m data_ingestion.pipeline
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dateutil import parser as _dateutil_parser
from dateutil.parser import ParserError
from pymongo import MongoClient
from pymongo.errors import BulkWriteError

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
RAW_DIR    = BASE_DIR / "raw_data"
PRUNED_DIR = BASE_DIR / "pruned"

# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB  = "warehouse_data"

# ── File → Collection mapping ──────────────────────────────────────────────────
FILE_TO_COLLECTION: dict[str, str] = {
    "employee_productivity.csv":          "employee_productivity",
    "inbound_parts_with_warehouse.csv":   "inbound_parts",
    "inventory_snapshot.csv":             "inventory_snapshot",
    "outbound_parts_with_warehouse.csv":  "outbound_parts",
    "warehouse_productivity.csv":         "warehouse_productivity",
}

# Public alias for import by server.py
_FILE_TO_COLLECTION = FILE_TO_COLLECTION

# ── Date columns per file ─────────────────────────────────────────────────────
# Any value in these columns will be parsed and stored as UTC datetime in MongoDB
# and as UTC ISO-8601 string in the pruned CSV.
DATE_COLS: dict[str, list[str]] = {
    "employee_productivity.csv": [
        "date",
    ],
    "inbound_parts_with_warehouse.csv": [
        "expected_date",
        "received_date",
    ],
    "inventory_snapshot.csv": [
        "snapshot_date",
    ],
    "outbound_parts_with_warehouse.csv": [
        "order_date",
        "promise_date",
        "shipped_date",
    ],
    "warehouse_productivity.csv": [
        "date",
    ],
}

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Type utilities
# ══════════════════════════════════════════════════════════════════════════════

def _is_null(value: Any) -> bool:
    """Return True for any representation of a missing value."""
    if value is None:
        return True
    if isinstance(value, float):
        import math
        return math.isnan(value)
    if isinstance(value, str):
        return value.strip().lower() in ("", "nan", "null", "none", "na", "n/a")
    return False


def _to_utc_datetime(value: Any) -> Optional[datetime]:
    """Parse any date string / object → naive UTC datetime (tzinfo=None).

    MongoDB's pymongo driver maps naive datetime as UTC BSON Date.
    """
    if _is_null(value):
        return None
    try:
        # Remove dayfirst=True to correctly parse ISO-8601 dates (YYYY-MM-DD)
        # ISO format like "2025-09-01" should be September 1st, not January 9th
        dt = _dateutil_parser.parse(str(value).strip())
        # If tz-aware, convert to UTC first, then strip tzinfo
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ParserError, OverflowError, ValueError, TypeError) as exc:
        logger.warning("  _to_utc_datetime: cannot parse %r — %s", value, exc)
        return None


def _to_utc_iso_str(value: Any) -> Optional[str]:
    """Convert any date value → 'YYYY-MM-DDTHH:MM:SSZ' string (for CSV storage)."""
    dt = _to_utc_datetime(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _cast(value: Any, dtype_name: str) -> Any:
    """Cast a scalar value to the Python type matching its pandas dtype.

    Rules:
        int*   → int   (str stays str, float stays float)
        float* → float
        object → str   (stripped)
    """
    if _is_null(value):
        return None
    if "int" in dtype_name:
        try:
            return int(float(value))   # float() handles "3.0" first
        except (ValueError, TypeError):
            return None
    if "float" in dtype_name:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    # object / string
    s = str(value).strip()
    return s if s else None


# ══════════════════════════════════════════════════════════════════════════════
# Document builder
# ══════════════════════════════════════════════════════════════════════════════

def _set_nested(doc: dict, dotted_key: str, value: Any) -> None:
    """Write *value* into *doc* at the path described by dot-notation *dotted_key*."""
    parts = dotted_key.split(".")
    d = doc
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _row_to_doc(
    row: dict[str, Any],
    date_cols: set[str],
    col_dtypes: dict[str, str],
) -> dict:
    """Convert a flat CSV row to a (possibly nested) MongoDB document.

    - Dot-notation column names   → nested subdocuments
    - Date columns                → naive UTC datetime objects
    - Other columns               → strict Python type (int | float | str)
    """
    doc: dict = {}
    for col, raw_val in row.items():
        if _is_null(raw_val):
            value = None
        elif col in date_cols:
            value = _to_utc_datetime(raw_val)
        else:
            value = _cast(raw_val, col_dtypes.get(col, "object"))

        if col == "_id":
            doc["_id"] = value
        else:
            _set_nested(doc, col, value)
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# Per-file processing
# ══════════════════════════════════════════════════════════════════════════════

def _prune(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """Prune a DataFrame:
        1. Drop exact duplicate rows
        2. Strip leading/trailing whitespace from all string columns
        3. Convert date columns → UTC ISO string (for CSV storage)
    """
    before = len(df)
    df = df.drop_duplicates()
    dropped = before - len(df)
    if dropped:
        logger.info("    Dropped %d duplicate rows", dropped)

    for col in df.columns:
        if col in date_cols:
            df[col] = df[col].apply(_to_utc_iso_str)
        elif df[col].dtype == object:
            df[col] = df[col].apply(lambda v: str(v).strip() if not _is_null(v) else v)

    return df


def ingest_file(
    csv_path: Path,
    collection_name: str,
    date_cols: list[str],
    db,
) -> None:
    """Full lifecycle for one CSV file: read → prune → save pruned CSV → insert to MongoDB."""
    logger.info("┌─ %s → collection: '%s'", csv_path.name, collection_name)

    # ── 1. Read ───────────────────────────────────────────────────────────────
    df = pd.read_csv(csv_path, dtype=str)          # read everything as str first
    # Re-parse numeric columns using original dtype detection
    df_typed = pd.read_csv(csv_path)               # pandas-inferred dtypes
    col_dtypes: dict[str, str] = {col: str(df_typed[col].dtype) for col in df_typed.columns}
    logger.info("│  Read %d rows × %d columns", len(df), len(df.columns))

    # ── 2. Prune ──────────────────────────────────────────────────────────────
    df_pruned = _prune(df, date_cols)
    logger.info("│  Rows after pruning: %d", len(df_pruned))

    # ── 3. Save pruned CSV ────────────────────────────────────────────────────
    PRUNED_DIR.mkdir(parents=True, exist_ok=True)
    pruned_path = PRUNED_DIR / csv_path.name
    df_pruned.to_csv(pruned_path, index=False, encoding="utf-8")
    logger.info("│  Saved pruned CSV  → %s", pruned_path.relative_to(BASE_DIR.parent))

    # ── 4. Build MongoDB documents ────────────────────────────────────────────
    date_col_set = set(date_cols)
    docs: list[dict] = []
    for _, row in df_pruned.iterrows():
        doc = _row_to_doc(row.to_dict(), date_col_set, col_dtypes)
        docs.append(doc)

    # ── 5. Load to MongoDB (drop + recreate → idempotent) ─────────────────────
    col = db[collection_name]
    col.drop()
    if docs:
        try:
            result = col.insert_many(docs, ordered=False)
            logger.info("│  Inserted %d documents", len(result.inserted_ids))
        except BulkWriteError as bwe:
            ok  = bwe.details.get("nInserted", 0)
            err = len(bwe.details.get("writeErrors", []))
            logger.error("│  BulkWriteError — inserted: %d  failed: %d", ok, err)

    logger.info("└─ Done: %s", collection_name)


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline() -> None:
    logger.info("=" * 65)
    logger.info("  Warehouse Data Ingestion Pipeline")
    logger.info("  Raw    : %s", RAW_DIR)
    logger.info("  Pruned : %s", PRUNED_DIR)
    logger.info("  DB     : %s  /  %s", MONGO_URI, MONGO_DB)
    logger.info("=" * 65)

    # ── Connect to MongoDB ────────────────────────────────────────────────────
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
    try:
        client.admin.command("ping")
        logger.info("MongoDB: connected OK")
    except Exception as exc:
        logger.error("MongoDB connection failed: %s", exc)
        sys.exit(1)

    db = client[MONGO_DB]

    # ── Process each file ─────────────────────────────────────────────────────
    for filename, collection_name in FILE_TO_COLLECTION.items():
        csv_path = RAW_DIR / filename
        if not csv_path.exists():
            logger.warning("File not found, skipping: %s", filename)
            continue
        date_cols = DATE_COLS.get(filename, [])
        ingest_file(csv_path, collection_name, date_cols, db)

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("=" * 65)
    logger.info("  Pipeline complete. DB: '%s'", MONGO_DB)
    logger.info("  %-40s  %s", "Collection", "Documents")
    logger.info("  " + "-" * 48)
    for cname in sorted(db.list_collection_names()):
        count = db[cname].estimated_document_count()
        logger.info("  %-40s  %d", cname, count)
    logger.info("=" * 65)
    client.close()


if __name__ == "__main__":
    run_pipeline()
