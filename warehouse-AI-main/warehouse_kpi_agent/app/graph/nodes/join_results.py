"""Join Results Node.

Merges per-collection results from collection_results into a flat db_results list.
This mirrors the reference architecture's join_results step which merges
multi-collection query outputs on a common key.

For warehouse KPI data, "joining" means:
  - registered_kpi  : flatten all KPI result dicts from all collections
  - analytical      : keep each collection's stats dict tagged with collection name

Execution path entry: "join_results"
State writes: db_results, result_count, execution_path
"""

import logging
from typing import Any

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def join_results_node(state: AgentState) -> dict[str, Any]:
    """Merge all collection_results into a flat db_results list."""
    collection_results = state.get("collection_results") or {}
    execution_path     = list(state.get("execution_path") or [])
    execution_path.append("join_results")

    all_results: list[dict[str, Any]] = []

    # Process collections in sorted order for deterministic output
    for col_name, col_data in sorted(collection_results.items()):
        if not isinstance(col_data, dict):
            continue
        results: list = col_data.get("results") or []
        for r in results:
            if isinstance(r, dict):
                # Tag with collection and result type if not already present
                r.setdefault("collection", col_name)
                r.setdefault("result_type", col_data.get("type", "unknown"))
            all_results.append(r)

    logger.info(
        "join_results: merged %d results from %d collections",
        len(all_results), len(collection_results),
    )

    return {
        "db_results":      all_results,
        "result_count":    len(all_results),
        "execution_path":  execution_path,
    }
