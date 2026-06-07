"""
CSV → MongoDB data loader.

Reads CSVs with dot-notation column headers (e.g. raw.po_number,
normalized.supplier.id) and reconstructs nested MongoDB documents.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dateutil import parser as _dateutil_parser
from dateutil.parser import ParserError
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import BulkWriteError

from app.config.settings import (
    COLLECTION_FILE_MAP,
    DATA_DIR,
    MONGODB_DB,
    MONGODB_URI,
)

logger = logging.getLogger(__name__)

# ── Date fields per collection ────────────────────────────────────────────────
_DATE_FIELDS: dict[str, list[str]] = {
    "inbound_parts": [
        "normalized.dates.expected",
        "normalized.dates.received",
    ],
    "outbound_parts": [
        "normalized.dates.order",
        "normalized.dates.promise",
        "normalized.dates.shipped",
    ],
    "inventory_snapshot": ["normalized.snapshot_date"],
    "warehouse_productivity": ["normalized.date"],
    "employee_productivity": ["normalized.date"],
}


# ── Value coercion ────────────────────────────────────────────────────────────

def _coerce(value: str, key: str, date_fields: list[str]) -> Any:
    """Coerce a raw string value to the appropriate Python type."""
    if value == "" or value is None:
        return None
    # Date conversion → always store as naive UTC datetime in MongoDB
    if key in date_fields:
        try:
            dt = _dateutil_parser.parse(str(value).strip(), dayfirst=False)
            # Convert to UTC then strip tzinfo; pymongo maps naive datetime as UTC
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except (ParserError, OverflowError, ValueError, TypeError):
            return value
    # Numeric conversion
    try:
        fv = float(value)
        return int(fv) if fv == int(fv) else round(fv, 6)
    except (ValueError, TypeError):
        return value


# ── Document builder ──────────────────────────────────────────────────────────

def _set_nested(doc: dict, dotted_key: str, value: Any) -> None:
    """Write *value* into *doc* at the path described by *dotted_key*."""
    parts = dotted_key.split(".")
    d = doc
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def _row_to_doc(row: dict, date_fields: list[str]) -> dict:
    """Convert a flat CSV row with dotted headers to a nested MongoDB doc."""
    doc: dict = {}
    for key, raw_val in row.items():
        if pd.isna(raw_val) if not isinstance(raw_val, str) else raw_val == "":
            value = None
        else:
            value = _coerce(str(raw_val).strip(), key, date_fields)

        if key == "_id":
            doc["_id"] = value
        else:
            _set_nested(doc, key, value)
    return doc


# ── Collection loader ─────────────────────────────────────────────────────────

def load_collection(
    client: MongoClient,
    collection_name: str,
    csv_path: Path,
    force_reload: bool = False,
) -> int:
    """Load a CSV file into a MongoDB collection.

    Args:
        client:          Active MongoClient.
        collection_name: Target collection name.
        csv_path:        Path to the CSV file.
        force_reload:    If True, drop and recreate the collection.

    Returns:
        Number of documents inserted.
    """
    db = client[MONGODB_DB]
    col = db[collection_name]

    if force_reload:
        col.drop()
        logger.info("Dropped collection '%s' for reload.", collection_name)

    if not force_reload and col.estimated_document_count() > 0:
        logger.info("Collection '%s' already populated – skipping.", collection_name)
        return 0

    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        return 0

    df = pd.read_csv(csv_path, dtype=str)
    date_fields = _DATE_FIELDS.get(collection_name, [])
    docs = [_row_to_doc(row, date_fields) for row in df.to_dict("records")]

    try:
        result = col.insert_many(docs, ordered=False)
        n = len(result.inserted_ids)
        logger.info("Inserted %d docs into '%s'.", n, collection_name)
        return n
    except BulkWriteError as exc:
        n_ok = exc.details.get("nInserted", 0)
        logger.warning(
            "Partial insert for '%s': %d inserted (duplicates skipped).",
            collection_name,
            n_ok,
        )
        return n_ok


# ── Convenience: load everything ──────────────────────────────────────────────

def load_all(force_reload: bool = False) -> None:
    """Load all 5 CSV files into MongoDB."""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5_000)
    try:
        # Verify connection
        client.admin.command("ping")
        logger.info("Connected to MongoDB at %s", MONGODB_URI)
    except Exception as exc:
        logger.error("Cannot reach MongoDB: %s", exc)
        raise

    try:
        for name, filename in COLLECTION_FILE_MAP.items():
            path = DATA_DIR / filename
            load_collection(client, name, path, force_reload)
        logger.info("All collections ready in database '%s'.", MONGODB_DB)
    finally:
        client.close()
