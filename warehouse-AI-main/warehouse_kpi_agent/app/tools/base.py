"""Shared MongoDB utilities for all collection tools."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from dateutil import parser as _dateutil_parser
from dateutil.parser import ParserError
from pymongo import MongoClient
from pymongo.collection import Collection

from app.config.settings import MONGODB_DB, MONGODB_URI

logger = logging.getLogger(__name__)

# ── Singleton connection ───────────────────────────────────────────────────────
_client: Optional[MongoClient] = None


def get_collection(name: str) -> Collection:
    """Return a cached MongoDB collection handle."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5_000)
    return _client[MONGODB_DB][name]


# ── Date utilities ─────────────────────────────────────────────────────────────

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a user-provided date string in ANY format to a naive UTC datetime.

    MongoDB stores dates as BSON UTC datetimes. pymongo maps Python
    ``datetime`` objects without tzinfo as UTC, so we always strip tzinfo
    after converting to UTC.

    Handled formats (non-exhaustive):
        ISO 8601    : 2025-01-01, 2025-01-01T00:00:00Z, 2025-01-01T06:00:00+05:30
        US style    : 01/01/2025, 1/1/2025
        EU style    : 01-01-2025, 01.01.2025
        Natural     : Jan 1 2025, January 1 2025, 1 Jan 2025
        Partial     : 2025-01, Jan 2025  (treated as first of month)
    """
    if not date_str:
        return None
    date_str = str(date_str).strip()
    try:
        # dateutil.parser handles virtually every human & machine date format.
        # dayfirst=False  → prefer MM/DD/YYYY for ambiguous date strings.
        # ignoretz=False  → respect timezone info so we can convert to UTC.
        dt = _dateutil_parser.parse(date_str, dayfirst=False)
        # Convert to UTC-aware then strip tzinfo so pymongo treats it as UTC.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ParserError, OverflowError, ValueError, TypeError) as exc:
        logger.warning("parse_date: cannot parse %r — %s", date_str, exc)
        return None


def build_match(
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date_field: str = "date",
    employee_id: Optional[str] = None,
) -> dict:
    """Build a MongoDB $match filter from common parameters."""
    match: dict[str, Any] = {}

    if warehouse_id:
        match["warehouse_id"] = warehouse_id.upper()

    if employee_id:
        match["employee_id"] = employee_id

    start = parse_date(start_date)
    end = parse_date(end_date)
    if start or end:
        date_range: dict = {}
        if start:
            date_range["$gte"] = start
        if end:
            # Inclusive upper bound – move to end-of-day
            end = end.replace(hour=23, minute=59, second=59)
            date_range["$lte"] = end
        match[date_field] = date_range

    return match


def safe_run(pipeline: list, collection: Collection) -> list[dict]:
    """Execute an aggregation pipeline and return results as a list."""
    try:
        result = list(collection.aggregate(pipeline, allowDiskUse=True))
        logger.debug("Aggregation on '%s' returned %d results", collection.name, len(result))
        return result
    except Exception as exc:
        logger.error("Aggregation error on '%s': %s", collection.name, exc, exc_info=True)
        return []


def first_value(results: list[dict], field: str = "value") -> Optional[float]:
    """Extract first result value; return None on empty results."""
    if results:
        v = results[0].get(field)
        if v is not None:
            return round(float(v), 4)
    return None


def pct(value: Optional[float]) -> Optional[float]:
    """Convert a 0-1 ratio to a rounded percentage."""
    if value is None:
        return None
    return round(value * 100, 2)
