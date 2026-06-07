"""Classify Intent Node.

LangGraph node that wraps the IntentClassifier service.

Chain inside the service:
    ChatPromptTemplate | ChatOllama(format=json) | JsonOutputParser

State writes: classified_intent, intent_confidence, entities_extracted,
              target_collections, query_params, execution_path,
              and resets all downstream fields to None/empty.
"""

import logging
from typing import Any

from langsmith import traceable

from app.graph.state import AgentState
from app.services.intent_classifier import IntentClassifier

logger = logging.getLogger(__name__)


@traceable(name="classify_intent_node", tags=["graph_node", "intent"])
def classify_intent_node(state: AgentState) -> dict[str, Any]:
    """Classify user query using the IntentClassifier LangChain chain."""
    query = state["user_query"]
    conversation_history = state.get("conversation_history") or []
    
    logger.info("classify_intent_node: %s", query[:100])

    # ── LangChain chain invocation ─────────────────────────────────────────────
    # LLM Call #1 (intent classification with conversation context)
    classifier = IntentClassifier.get_instance()
    result     = classifier.classify(query, conversation_history=conversation_history)

    # ── Reset execution_path for NEW query (don't accumulate from previous sessions) ──
    # This is the FIRST node in the graph, so we start fresh
    execution_path = ["classify_intent"]

    logger.info(
        "Classified → intent=%s  confidence=%.2f  collections=%s",
        result["intent"], result["confidence"], result["target_collections"],
    )

    return {
        "classified_intent":  result["intent"],
        "intent_confidence":  result["confidence"],
        "entities_extracted": result["entities"],
        "target_collections": result["target_collections"],
        "query_params":       result["query_params"],
        "execution_path":     execution_path,
        # Reset downstream fields for a clean run
        "errors":             [],
        "collection_results": None,
        "db_results":         None,
        "result_count":       0,
        "formatted_response": None,
    }

# ── Backward-compat alias ──────────────────────────────────────────────────────
intent_classifier_node = classify_intent_node

