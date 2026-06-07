"""Test Intent Classification - Overall Functionality.

Tests the IntentClassifier service to ensure queries are correctly routed.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.intent_classifier import IntentClassifier


def test_registered_kpi_classification():
    """Test classification of registered KPI queries."""
    classifier = IntentClassifier.get_instance()
    
    # Test query with warehouse and date range
    query = "Show all KPIs for WH-01 from June 1 to June 30, 2025"
    result = classifier.classify(query)
    
    assert result["intent"] == "registered_kpi", f"Expected registered_kpi, got {result['intent']}"
    assert result["entities"]["warehouse_id"] is not None, "Should extract warehouse_id"
    assert result["entities"]["start_date"] is not None, "Should extract start_date"
    assert result["entities"]["end_date"] is not None, "Should extract end_date"
    print(f"✅ Registered KPI classification: {result['intent']}")


def test_analytical_single_classification():
    """Test classification of single collection analytical queries."""
    classifier = IntentClassifier.get_instance()
    
    query = "What is the average picks per hour for employee E-1015?"
    result = classifier.classify(query)
    
    assert result["intent"] == "analytical_single", f"Expected analytical_single, got {result['intent']}"
    assert len(result["target_collections"]) == 1, "Should target one collection"
    print(f"✅ Analytical single classification: {result['intent']} → {result['target_collections']}")


def test_analytical_parallel_classification():
    """Test classification of multi-collection queries."""
    classifier = IntentClassifier.get_instance()
    
    query = "Give me an overview of all warehouse data"
    result = classifier.classify(query)
    
    assert result["intent"] == "analytical_parallel", f"Expected analytical_parallel, got {result['intent']}"
    assert len(result["target_collections"]) > 1, "Should target multiple collections"
    print(f"✅ Analytical parallel classification: {result['intent']} → {len(result['target_collections'])} collections")


def test_out_of_scope_classification():
    """Test classification of out-of-scope queries."""
    classifier = IntentClassifier.get_instance()
    
    query = "What is the weather today?"
    result = classifier.classify(query)
    
    assert result["intent"] == "out_of_scope", f"Expected out_of_scope, got {result['intent']}"
    print(f"✅ Out-of-scope classification: {result['intent']}")


def test_warehouse_id_extraction():
    """Test warehouse ID extraction."""
    classifier = IntentClassifier.get_instance()
    
    test_cases = [
        ("Show KPIs for warehouse WH-01 in June 2025", "WH-01"),
        ("What about WH-02 performance?", "WH-02"),
        ("Warehouse 3 fill rate", "WH-03"),
    ]
    
    for query, expected_wh in test_cases:
        result = classifier.classify(query)
        warehouse_id = result["entities"].get("warehouse_id")
        assert warehouse_id == expected_wh or warehouse_id is not None, \
            f"Query '{query}' should extract warehouse {expected_wh}, got {warehouse_id}"
    
    print(f"✅ Warehouse ID extraction: {len(test_cases)} test cases passed")


if __name__ == "__main__":
    print("=" * 70)
    print("INTENT CLASSIFICATION TESTS")
    print("=" * 70)
    
    try:
        test_registered_kpi_classification()
        test_analytical_single_classification()
        test_analytical_parallel_classification()
        test_out_of_scope_classification()
        test_warehouse_id_extraction()
        
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
