"""Tools package — exports collection tool modules, a unified registry,
and the AnalyticsDispatcher wrapper with two execution modes.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from app.tools import (
    employee_productivity_tool,
    inbound_tool,
    inventory_tool,
    outbound_tool,
    warehouse_productivity_tool,
)

logger = logging.getLogger(__name__)

# ── Collection → tool module registry ────────────────────────────────────────
TOOL_REGISTRY: dict = {
    "inbound_parts":          inbound_tool,
    "outbound_parts":         outbound_tool,
    "inventory_snapshot":     inventory_tool,
    "warehouse_productivity": warehouse_productivity_tool,
    "employee_productivity":  employee_productivity_tool,
}

# ── KPI key → collection name ─────────────────────────────────────────────────
KPI_TO_COLLECTION: dict[str, str] = {}
for _col, _mod in TOOL_REGISTRY.items():
    for _kpi in _mod.ALL_KPIS:
        KPI_TO_COLLECTION[_kpi] = _col

ALL_COLLECTIONS = list(TOOL_REGISTRY.keys())
ALL_KPI_KEYS = list(KPI_TO_COLLECTION.keys())

# ── Collection aliases ─────────────────────────────────────────────────────────
_COLLECTION_ALIASES: dict[str, str] = {
    "inbound":                "inbound_parts",
    "inbound_parts":          "inbound_parts",
    "outbound":               "outbound_parts",
    "outbound_parts":         "outbound_parts",
    "inventory":              "inventory_snapshot",
    "inventory_snapshot":     "inventory_snapshot",
    "stock":                  "inventory_snapshot",
    "warehouse":              "warehouse_productivity",
    "warehouse_productivity": "warehouse_productivity",
    "productivity":           "warehouse_productivity",
    "employee":               "employee_productivity",
    "employee_productivity":  "employee_productivity",
    "staff":                  "employee_productivity",
}


def resolve_collection(raw: Optional[str]) -> Optional[str]:
    """Resolve a loose alias or collection name to its canonical form."""
    if not raw:
        return None
    key = raw.lower().strip().replace("-", "_").replace(" ", "_")
    return _COLLECTION_ALIASES.get(key)


# ═══════════════════════════════════════════════════════════════════════════════
# AnalyticsDispatcher — unified wrapper with two execution modes
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyticsDispatcher:
    """Thin wrapper around all five collection tools.

    Two execution modes
    -------------------
    Type 1 – ``run_single(collection, ...)``
        Runs ``compute_general_stats`` on exactly ONE collection.
        Fast; used when the user targets a specific dataset.

    Type 2 – ``run_parallel(...)``
        Runs ``compute_general_stats`` concurrently on ALL collections
        using a ``ThreadPoolExecutor``.
        Used for overview / cross-collection analytical questions.

    Both methods accept the same optional filter triad:
        warehouse_id, start_date, end_date
    """

    _MAX_WORKERS: int = 5

    # ── Type 1: single collection ─────────────────────────────────────────────

    @staticmethod
    def run_single(
        collection: str,
        warehouse_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run analytical stats on ONE collection.

        Args:
            collection:  Canonical collection name or an alias
                         (e.g. ``"inbound"``, ``"employee"``).
            warehouse_id: Optional warehouse filter (e.g. ``"WH-01"``).
            start_date:   ISO date string lower bound (``"2025-01-01"``).
            end_date:     ISO date string upper bound (``"2025-03-31"``).

        Returns:
            A stats dict from the collection's ``compute_general_stats()``.

        Raises:
            ValueError: if the collection name cannot be resolved.
        """
        canonical = resolve_collection(collection) or collection
        tool = TOOL_REGISTRY.get(canonical)
        if tool is None:
            raise ValueError(
                f"Unknown collection '{collection}'. "
                f"Valid: {ALL_COLLECTIONS}"
            )
        logger.info(
            "dispatch[single] collection=%s wh=%s %s→%s",
            canonical, warehouse_id, start_date, end_date,
        )
        return tool.compute_general_stats(
            warehouse_id=warehouse_id,
            start_date=start_date,
            end_date=end_date,
        )

    # ── Type 2: parallel across all collections ───────────────────────────────

    @classmethod
    def run_parallel(
        cls,
        warehouse_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        collections: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Run analytical stats on ALL (or a subset of) collections concurrently.

        Args:
            warehouse_id: Optional warehouse filter.
            start_date:   ISO date string lower bound.
            end_date:     ISO date string upper bound.
            collections:  Explicit list of collections to query.
                          Defaults to all 5 when omitted.

        Returns:
            A dict with keys:
              ``results``      – list of per-collection stat dicts (sorted by name)
              ``errors``       – list of error strings (empty on full success)
              ``collection_count`` – number of successful results
              ``requested_collections`` – which collections were targeted
        """
        targets = collections if collections else ALL_COLLECTIONS
        # Resolve any aliases in the targets list
        resolved = [resolve_collection(c) or c for c in targets]

        logger.info(
            "dispatch[parallel] collections=%s wh=%s %s→%s",
            resolved, warehouse_id, start_date, end_date,
        )

        all_results: list[dict[str, Any]] = []
        errors: list[str] = []

        def _fetch(col: str) -> dict[str, Any]:
            tool = TOOL_REGISTRY.get(col)
            if tool is None:
                raise ValueError(f"Unknown collection '{col}'")
            return tool.compute_general_stats(
                warehouse_id=warehouse_id,
                start_date=start_date,
                end_date=end_date,
            )

        with ThreadPoolExecutor(max_workers=cls._MAX_WORKERS) as executor:
            futures = {executor.submit(_fetch, col): col for col in resolved}
            for future in as_completed(futures):
                col = futures[future]
                try:
                    all_results.append(future.result())
                except Exception as exc:
                    logger.error("parallel stats error [%s]: %s", col, exc)
                    errors.append(f"{col}: {exc}")

        all_results.sort(key=lambda r: r.get("collection", ""))

        return {
            "requested_collections": resolved,
            "collection_count": len(all_results),
            "errors": errors,
            "results": all_results,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
analytics = AnalyticsDispatcher()
