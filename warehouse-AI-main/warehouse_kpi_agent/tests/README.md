# Warehouse KPI Agent - Tests

Simple test suite for validating core functionality of the Warehouse KPI Agent.

## Test Files

### 1. `test_intent_classification.py`
Tests the intent classifier to ensure queries are correctly routed to the appropriate handler.

**Coverage:**
- Registered KPI classification
- Analytical single collection queries
- Analytical parallel (multi-collection) queries
- Out-of-scope queries
- Entity extraction (warehouse IDs, dates)

### 2. `test_kpi_calculations.py`
Tests registered KPI computation logic across different collections.

**Coverage:**
- Outbound KPIs (Fill Rate, OTIF, Backorder Rate)
- Inventory KPIs (Days of Supply, Stockout %)
- Warehouse Productivity KPIs
- No-data scenarios
- KPI structure validation

### 3. `test_graph_flow.py`
Tests end-to-end LangGraph execution for different query types.

**Coverage:**
- Registered KPI flow
- Analytical query flow
- Out-of-scope flow
- Conversation memory persistence
- Error handling
- Execution path tracking

## Running Tests

### Quick Start (Recommended)
```bash
# Using make command (works on Mac and Windows with make installed)
make test
```

### Run All Tests
```bash
python tests/run_tests.py
```

### Run Specific Test Suite
```bash
# Intent classification only
python tests/run_tests.py intent

# KPI calculations only
python tests/run_tests.py kpi

# Graph flow only
python tests/run_tests.py flow
```

### Run Individual Test File
```bash
python tests/test_intent_classification.py
python tests/test_kpi_calculations.py
python tests/test_graph_flow.py
```

## Prerequisites

1. **MongoDB Running**: Tests require MongoDB connection
   ```bash
   docker run -d -p 27017:27017 mongo:7.0
   ```

2. **Data Loaded**: Ensure CSV data is loaded into MongoDB
   ```bash
   python -m app.main --load-data
   ```

3. **Ollama Running**: LLM tests require Ollama
   ```bash
   # Check if Ollama is running
   curl http://localhost:11434/api/version
   ```

## Test Philosophy

These tests are designed to:
- ✅ Validate **overall functionality**, not deep unit testing
- ✅ Ensure **core features work** end-to-end
- ✅ Catch **major regressions** quickly
- ✅ Keep test suite **simple and maintainable**

## Expected Output

```
================================================================================
WAREHOUSE KPI AGENT - TEST SUITE
================================================================================

================================================================================
Running: test_intent_classification.py
================================================================================
✅ Registered KPI classification: registered_kpi
✅ Analytical single classification: analytical_single → ['employee_productivity']
✅ Analytical parallel classification: analytical_parallel → 5 collections
✅ Out-of-scope classification: out_of_scope
✅ Warehouse ID extraction: 3 test cases passed

================================================================================
✅ ALL TESTS PASSED
================================================================================

[... similar output for other test files ...]

================================================================================
TEST SUMMARY
================================================================================
✅ ALL 3 TEST SUITES PASSED
```

## Notes

- Tests use real LLM calls (not mocked) for realistic validation
- Tests create temporary session IDs for conversation memory
- Each test is independent and can run standalone
- Tests assume default configuration and data structure

## Future Enhancements

Potential additions (not implemented to keep tests simple):
- Mock LLM responses for faster execution
- Database fixtures for consistent test data
- Performance benchmarks
- Integration tests with FastAPI endpoints
- Excel/JSON/HTML export validation
