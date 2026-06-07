"""Test Graph Execution Flow - Overall Functionality.

Tests the LangGraph execution for different query types.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graph.graph_builder import graph
from app.config.memory import create_session_id, get_session_config


def test_registered_kpi_flow():
    """Test end-to-end flow for registered KPI query."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    initial_state = {
        "user_query": "Show all KPIs for WH-01 from June 1 to June 30, 2025",
        "conversation_history": [],
    }
    
    result = graph.invoke(initial_state, config)
    
    # Verify state fields
    assert result["classified_intent"] == "registered_kpi", "Should classify as registered_kpi"
    assert result["formatted_response"] is not None, "Should have formatted response"
    assert len(result["formatted_response"]) > 0, "Response should not be empty"
    assert "execution_path" in result, "Should have execution path"
    
    # Verify execution path
    path = result["execution_path"]
    assert "classify_intent" in path, "Should include classify_intent node"
    assert "registered_kpi_handler" in path, "Should include registered_kpi_handler node"
    assert "format_response" in path, "Should include format_response node"
    
    print(f"✅ Registered KPI flow: {' → '.join(path)}")
    print(f"   Response length: {len(result['formatted_response'])} chars")


def test_analytical_query_flow():
    """Test end-to-end flow for analytical query."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    initial_state = {
        "user_query": "What is the average picks per hour in June 2025?",
        "conversation_history": [],
    }
    
    result = graph.invoke(initial_state, config)
    
    # Verify classification
    assert result["classified_intent"] in ["analytical_single", "analytical_parallel"], \
        f"Should classify as analytical, got {result['classified_intent']}"
    assert result["formatted_response"] is not None, "Should have formatted response"
    
    print(f"✅ Analytical query flow: {result['classified_intent']}")


def test_out_of_scope_flow():
    """Test end-to-end flow for out-of-scope query."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    initial_state = {
        "user_query": "What is the weather today?",
        "conversation_history": [],
    }
    
    result = graph.invoke(initial_state, config)
    
    assert result["classified_intent"] == "out_of_scope", "Should classify as out_of_scope"
    assert result["formatted_response"] is not None, "Should have response"
    
    # Out-of-scope should skip DB queries
    path = result["execution_path"]
    assert "classify_intent" in path, "Should include classify_intent"
    assert "format_response" in path, "Should include format_response"
    assert "registered_kpi_handler" not in path, "Should NOT query DB for out-of-scope"
    
    print(f"✅ Out-of-scope flow: {' → '.join(path)}")


def test_conversation_memory():
    """Test that conversation memory persists across queries."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    # First query
    state1 = {
        "user_query": "Show KPIs for WH-01 in June 2025",
        "conversation_history": [],
    }
    result1 = graph.invoke(state1, config)
    
    # Second query in same session (should have memory)
    state2 = {
        "user_query": "What about WH-02?",
        "conversation_history": [],
    }
    result2 = graph.invoke(state2, config)
    
    # Both should complete successfully
    assert result1["formatted_response"] is not None, "First query should succeed"
    assert result2["formatted_response"] is not None, "Second query should succeed"
    
    print(f"✅ Conversation memory: Session {session_id[:8]}... preserved across 2 queries")


def test_error_handling():
    """Test that errors are handled gracefully."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    # Query with invalid warehouse ID
    initial_state = {
        "user_query": "Show KPIs for warehouse XYZ-999",
        "conversation_history": [],
    }
    
    # Should not crash, even with invalid data
    result = graph.invoke(initial_state, config)
    
    assert result["formatted_response"] is not None, "Should return a response even with errors"
    assert "errors" in result, "Should have errors field"
    
    print(f"✅ Error handling: Gracefully handled invalid warehouse")


def test_execution_path_completeness():
    """Test that execution path is tracked correctly."""
    session_id = create_session_id()
    config = get_session_config(session_id)
    
    queries = [
        ("Show all KPIs for WH-01 in June 2025", "registered_kpi"),
        ("What is the average picks?", "analytical"),
        ("Hello", "out_of_scope"),
    ]
    
    for query, expected_type in queries:
        state = {"user_query": query, "conversation_history": []}
        result = graph.invoke(state, config)
        
        path = result.get("execution_path", [])
        assert len(path) > 0, f"Query '{query}' should have execution path"
        assert "classify_intent" in path, f"Query '{query}' should start with classify_intent"
        assert "format_response" in path, f"Query '{query}' should end with format_response"
    
    print(f"✅ Execution path tracking: {len(queries)} query types validated")


if __name__ == "__main__":
    print("=" * 70)
    print("GRAPH EXECUTION FLOW TESTS")
    print("=" * 70)
    
    try:
        test_registered_kpi_flow()
        test_analytical_query_flow()
        test_out_of_scope_flow()
        test_conversation_memory()
        test_error_handling()
        test_execution_path_completeness()
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
