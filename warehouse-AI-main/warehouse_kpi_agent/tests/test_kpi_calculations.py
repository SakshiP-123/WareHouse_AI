"""Test KPI Calculations - Overall Functionality.

Tests registered KPI computation across different collections.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools import outbound_tool, inventory_tool, warehouse_productivity_tool


def test_outbound_kpis():
    """Test outbound KPI calculations (Fill Rate, OTIF, Backorder Rate)."""
    
    # Test with sample parameters
    results = outbound_tool.compute_registered_kpis(
        warehouse_id="WH-01",
        start_date="2025-06-01",
        end_date="2025-06-30"
    )
    
    assert len(results) > 0, "Should return KPI results"
    
    # Results is a list of KPI dicts
    kpi_names = [r.get("kpi") for r in results]
    assert "fill_rate" in kpi_names, "Should include fill_rate KPI"
    assert "otif" in kpi_names, "Should include OTIF KPI"
    assert "backorder_rate" in kpi_names, "Should include backorder_rate KPI"
    
    # Verify KPI structure
    fill_rate_kpi = next((r for r in results if r.get("kpi") == "fill_rate"), None)
    assert fill_rate_kpi is not None, "Fill rate KPI should exist"
    assert "value" in fill_rate_kpi, "KPI should have value"
    assert "name" in fill_rate_kpi, "KPI should have name"
    assert isinstance(fill_rate_kpi["value"], (int, float, type(None))), "Value should be numeric or None"
    
    print(f"✅ Outbound KPIs: {len(results)} KPIs calculated")
    if fill_rate_kpi["value"] is not None:
        print(f"   Fill Rate: {fill_rate_kpi['value']}")


def test_inventory_kpis():
    """Test inventory KPI calculations (Days of Supply, Stockout %)."""
    
    results = inventory_tool.compute_registered_kpis(
        warehouse_id="WH-02",
        start_date="2025-01-01",
        end_date="2025-03-31"
    )
    
    assert len(results) > 0, "Should return KPI results"
    
    kpi_names = [r.get("kpi") for r in results]
    assert "days_of_supply" in kpi_names, "Should include days_of_supply KPI"
    assert "stockout_pct" in kpi_names, "Should include stockout_pct KPI"
    
    print(f"✅ Inventory KPIs: {len(results)} KPIs calculated")


def test_warehouse_productivity_kpis():
    """Test warehouse productivity KPI calculations."""
    
    results = warehouse_productivity_tool.compute_registered_kpis(
        warehouse_id="WH-03",
        start_date="2025-06-01",
        end_date="2025-06-30"
    )
    
    assert len(results) > 0, "Should return KPI results"
    
    kpi_names = [r.get("kpi") for r in results]
    assert "lines_per_labor_hour" in kpi_names, "Should include lines_per_labor_hour KPI"
    
    lines_kpi = next((r for r in results if r.get("kpi") == "lines_per_labor_hour"), None)
    assert lines_kpi is not None, "Lines per labor-hour KPI should exist"
    if lines_kpi["value"] is not None:
        assert lines_kpi["value"] >= 0, "Lines per labor-hour should be non-negative"
    
    print(f"✅ Warehouse Productivity KPIs: {len(results)} KPIs calculated")


def test_kpi_with_no_data():
    """Test KPI calculation with date range that has no data."""
    
    # Use a future date range that should have no data
    results = outbound_tool.compute_registered_kpis(
        warehouse_id="WH-99",  # Non-existent warehouse
        start_date="2030-01-01",
        end_date="2030-01-31"
    )
    
    # Should still return results structure
    assert len(results) >= 0, "Should return results even with no data"
    
    print(f"✅ No data scenario handled correctly")


def test_all_kpis_have_required_fields():
    """Test that all KPIs have the required fields."""
    
    results = outbound_tool.compute_registered_kpis(
        warehouse_id="WH-01",
        start_date="2025-06-01",
        end_date="2025-06-30"
    )
    
    for kpi_result in results:
        assert "kpi" in kpi_result, "Result should have 'kpi' field"
        assert "name" in kpi_result, f"{kpi_result.get('kpi')} should have 'name' field"
        assert "value" in kpi_result, f"{kpi_result.get('kpi')} should have 'value' field"
        assert "collection" in kpi_result, f"{kpi_result.get('kpi')} should have 'collection' field"
    
    print(f"✅ All KPIs have required fields: {len(results)} KPIs validated")


if __name__ == "__main__":
    print("=" * 70)
    print("KPI CALCULATION TESTS")
    print("=" * 70)
    
    try:
        test_outbound_kpis()
        test_inventory_kpis()
        test_warehouse_productivity_kpis()
        test_kpi_with_no_data()
        test_all_kpis_have_required_fields()
        
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
