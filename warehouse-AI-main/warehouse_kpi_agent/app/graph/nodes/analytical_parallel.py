"""Parallel Query Handler Node.

Fans out queries to MULTIPLE collections concurrently using ThreadPoolExecutor.

Dependency handling
-------------------
All current warehouse collections are independent read-only queries — no output
from one is an input to another. They are therefore safe to run fully in parallel.

If a future query type introduces a dependency (collection A's result must augment
the filter for collection B), set ``state["depends_on"]`` to an ordered list like:
    [("inbound_parts", "outbound_parts")]   # outbound depends on inbound result
In that case the dependent collection is run *after* its dependency resolves,
while all other independent collections still run in parallel.

Results are stored in collection_results keyed by collection name.
The join_results_node merges them into db_results.

Execution path entries: "query_<col>" for each collection queried.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langsmith import traceable

from app.graph.nodes.query_tools import query_collection
from app.graph.state import AgentState
from app.tools import ALL_COLLECTIONS

logger = logging.getLogger(__name__)
_MAX_WORKERS = 5


@traceable(name="parallel_query_handler_node", tags=["graph_node", "parallel_query"])
def parallel_query_handler_node(state: AgentState) -> dict[str, Any]:
    """Query multiple collections — parallel by default, sequential for dependents."""
    intent         = state.get("classified_intent")
    entities       = state.get("entities_extracted") or {}
    query_params   = state.get("query_params") or {}
    target_cols    = list(state.get("target_collections") or [])
    user_query     = state.get("user_query", "")
    execution_path = list(state.get("execution_path") or [])
    errors         = list(state.get("errors") or [])

    # analytical_parallel with no explicit targets → use all collections
    if not target_cols:
        target_cols = list(ALL_COLLECTIONS)

    # Build dependency map: {dependent_col: prerequisite_col}
    # Populated if state["depends_on"] = [("A", "B")] means B depends on A
    depends_on_pairs: list[tuple[str, str]] = state.get("depends_on") or []
    prereq_map: dict[str, str] = {dep: pre for pre, dep in depends_on_pairs}

    # Split into independent vs. dependent collections
    independent = [c for c in target_cols if c not in prereq_map]
    dependent   = [c for c in target_cols if c in prereq_map]

    logger.info(
        "parallel_query_handler: intent=%s  independent=%s  dependent=%s",
        intent, independent, dependent,
    )

    collection_results: dict[str, Any] = {}

    # ── Phase 1: run all independent collections in parallel ──────────────────
    def _fetch(col: str, extra_entities: dict | None = None) -> tuple[str, dict[str, Any]]:
        merged_entities = {**entities, **(extra_entities or {})}
        return col, query_collection(col, intent, merged_entities, query_params, user_query=user_query)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch, col): col for col in independent}
        for future in as_completed(futures):
            col = futures[future]
            try:
                col_name, result = future.result()
                collection_results[col_name] = result
                execution_path.append(f"query_{col_name}")
                if "error" in result:
                    errors.append(result["error"])
            except Exception as exc:
                err = f"{col}: {exc}"
                logger.error("parallel_query future exception: %s", err)
                errors.append(err)

    # ── Phase 2: run dependent collections sequentially after prerequisites ───
    for col in dependent:
        prereq = prereq_map[col]
        prereq_result = collection_results.get(prereq, {})
        # Pass prerequisite summary as extra context in entities
        extra = {"_prereq_result": prereq_result}
        try:
            col_name, result = _fetch(col, extra)
            collection_results[col_name] = result
            execution_path.append(f"query_{col_name}(after_{prereq})")
            if "error" in result:
                errors.append(result["error"])
        except Exception as exc:
            err = f"{col} (dependent): {exc}"
            logger.error("parallel_query dependent exception: %s", err)
            errors.append(err)

    return {
        "collection_results": collection_results,
        "execution_path":     execution_path,
        "errors":             errors,
    }


# ── Backward-compat export ─────────────────────────────────────────────────────
analytical_parallel_node = parallel_query_handler_node

