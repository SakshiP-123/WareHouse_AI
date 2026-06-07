"""AgentState — shared state threaded through every node in the Warehouse KPI Agent graph.

Follows the reference architecture pattern:
  user_query → classify_intent → (single_query | parallel_query) → join_results → format_response
"""

from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State dict threaded through every node in the LangGraph pipeline."""

    # ── Input ──────────────────────────────────────────────────────────────────
    user_query: str
    
    # ── Conversation History (for follow-up questions) ─────────────────────────
    # List of previous (query, response) pairs in this session
    # Format: [{"query": "...", "response": "..."}, ...]
    conversation_history: Optional[list[dict[str, str]]]

    # ── Classification (set by classify_intent_node) ───────────────────────────
    # One of: registered_kpi | analytical_single | analytical_parallel | out_of_scope
    classified_intent: Optional[str]
    intent_confidence: Optional[float]

    # Structured entities extracted from the query:
    #   {warehouse_id, start_date, end_date, kpi_name, ...}
    entities_extracted: Optional[dict[str, Any]]

    # Collections to query, e.g. ["outbound_parts"] or all five
    target_collections: Optional[list[str]]

    # Additional query params: {kpi_names: [...], kpi_scope: "single"|"all"}
    query_params: Optional[dict[str, Any]]

    # ── Per-collection query results ────────────────────────────────────────────
    # Keyed by collection name, each value is:
    #   {collection, type, results: [...], count} or {error}
    collection_results: Optional[dict[str, Any]]

    # ── Joined / aggregated results ─────────────────────────────────────────────
    db_results: Optional[list[dict[str, Any]]]
    result_count: int

    # ── Execution tracking ──────────────────────────────────────────────────────
    # Sequence of node/tool names visited, e.g.:
    #   ["classify_intent", "query_outbound_parts", "format_response"]
    # NOTE: This is RESET at the start of each query (not accumulated across session)
    execution_path: list[str]
    errors: list[str]

    # Optional dependency chain for parallel handler.
    # List of (prerequisite_col, dependent_col) tuples.
    # e.g. [("inbound_parts", "outbound_parts")] → outbound runs after inbound.
    # Leave empty/None for fully parallel execution (default).
    depends_on: Optional[list[tuple[str, str]]]

    # ── Final output ────────────────────────────────────────────────────────────
    formatted_response: Optional[str]


# Backward-compat alias so old imports (GraphState) still work
GraphState = AgentState
