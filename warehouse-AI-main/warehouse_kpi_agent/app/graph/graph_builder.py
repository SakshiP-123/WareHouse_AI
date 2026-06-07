"""LangGraph graph builder — Reference architecture topology.

Wires all nodes and conditional edges together into a compiled StateGraph.

Graph topology
--------------

                         ┌──────────────────────┐
           START ───────►│   classify_intent     │  (LLM Call #1)
                         └──────────┬───────────┘
                                    │  route_after_classification
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                       ▼
   single_query_handler   parallel_query_handler     format_response
        (1 collection)      (N collections, async)   (out_of_scope)
              │                     │                       │
              │              join_results                   │
              │                     │                       │
              └─────────────────────┼───────────────────────┘
                                    ▼
                           format_response            (LLM Call #2)
                                    │
                                   END
"""

from langgraph.graph import END, START, StateGraph

from app.config.memory import get_checkpointer
from app.graph.conditions import route_after_classification
from app.graph.nodes.format_response import format_response_node
from app.graph.nodes.intent_classifier import classify_intent_node
from app.graph.nodes.join_results import join_results_node
from app.graph.nodes.analytical_parallel import parallel_query_handler_node
from app.graph.nodes.registered_kpi import registered_kpi_node
from app.graph.nodes.single_query_handler import single_query_handler_node
from app.graph.state import AgentState


def build_graph() -> StateGraph:
    """Construct and return the compiled LangGraph application with memory."""
    builder = StateGraph(AgentState)

    # ── Register nodes ─────────────────────────────────────────────────────────
    builder.add_node("classify_intent",        classify_intent_node)
    builder.add_node("single_query_handler",   single_query_handler_node)
    builder.add_node("parallel_query_handler", parallel_query_handler_node)
    builder.add_node("registered_kpi_handler", registered_kpi_node)
    builder.add_node("join_results",           join_results_node)
    builder.add_node("format_response",        format_response_node)

    # ── Entry edge ─────────────────────────────────────────────────────────────
    builder.add_edge(START, "classify_intent")

    # ── Conditional routing from classify_intent ───────────────────────────────
    builder.add_conditional_edges(
        "classify_intent",
        route_after_classification,
        {
            "registered_kpi":  "registered_kpi_handler",
            "single_query":    "single_query_handler",
            "parallel_query":  "parallel_query_handler",
            "format_response": "format_response",   # out_of_scope bypasses DB
        },
    )

    # ── Registered KPI path (always goes through join_results for multi-collection) ─
    builder.add_edge("registered_kpi_handler", "join_results")

    # ── Single-collection path ─────────────────────────────────────────────────
    builder.add_edge("single_query_handler", "format_response")

    # ── Multi-collection path ──────────────────────────────────────────────────
    builder.add_edge("parallel_query_handler", "join_results")
    builder.add_edge("join_results",           "format_response")

    # ── Terminal ───────────────────────────────────────────────────────────────
    builder.add_edge("format_response", END)

    # ── Compile with checkpointing for conversation memory ────────────────────
    checkpointer = get_checkpointer()
    return builder.compile(checkpointer=checkpointer)


# Module-level compiled graph — referenced by langgraph.json
graph = build_graph()

