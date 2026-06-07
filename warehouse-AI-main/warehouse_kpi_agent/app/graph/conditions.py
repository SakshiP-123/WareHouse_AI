"""Conditional edge functions for the Warehouse KPI Agent router."""

from app.graph.state import AgentState


def route_after_classification(state: AgentState) -> str:
    """Route to the correct handler after intent classification.

    Returns:
        "registered_kpi"  – KPI registry queries (single or all KPIs)
        "single_query"    – one collection to query (analytical_single)
        "parallel_query"  – multiple/all collections (analytical_parallel)
        "format_response" – out_of_scope (skip DB queries)
    """
    intent = state.get("classified_intent", "out_of_scope")
    target_collections = state.get("target_collections") or []

    if intent == "out_of_scope":
        return "format_response"

    # registered_kpi always uses the dedicated KPI node
    if intent == "registered_kpi":
        return "registered_kpi"

    # analytical_parallel always fans out to all collections
    if intent == "analytical_parallel":
        return "parallel_query"

    # Multiple target collections → parallel handler
    if len(target_collections) > 1:
        return "parallel_query"

    # Single collection → single handler
    return "single_query"


# ── Backward-compat alias ──────────────────────────────────────────────────────
def route_from_intent(state: AgentState) -> str:
    """Alias kept for backward compatibility; delegates to route_after_classification."""
    return route_after_classification(state)
