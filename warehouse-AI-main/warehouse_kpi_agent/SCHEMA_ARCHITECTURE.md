# Schema-Driven Architecture Documentation

## Overview

The Warehouse KPI Agent uses a **schema-driven architecture** to ensure all components have access to proper schema information. This eliminates hardcoded logic for specific questions and makes the system flexible, maintainable, and extensible.

## Architecture Principles

### 1. **Single Source of Truth**
- All collection schemas are defined in `collections_schema.py` (root level)
- Schema Registry (`app/config/schema_registry.py`) provides centralized access
- No duplication of column names or business logic across modules

### 2. **Schema-Aware Components**
All major components inject schema context into LLM prompts and query logic:

1. **Intent Classifier** (`app/services/intent_classifier.py`)
   - Receives compact schema reference with all collections, columns, and types
   - Uses schema to route queries to correct collection(s)
   - Column-aware routing: if query mentions `employee_id`, routes to `employee_productivity`

2. **Format Response** (`app/graph/nodes/format_response.py`)
   - Receives detailed schema for each collection being queried
   - LLM knows what columns exist and can format tables accordingly
   - Reduces hallucination - LLM won't invent columns that don't exist

3. **Query Tools** (`app/tools/*.py`)
   - Can reference schemas via `schema_registry.get_schema(collection_name)`
   - Business metrics formulas defined in schema, not hardcoded in tools

### 3. **Generic Query Handling**
The system does **not** customize logic for specific questions like:
- ❌ `if "how many warehouses" in query: return 3`
- ✅ Route to `warehouse_productivity` → run generic `distinct(warehouse_id)` aggregation

## Key Components

### Schema Registry (`app/config/schema_registry.py`)

Provides these functions:

```python
# Get full schema for a collection
schema = get_schema("inbound_parts")

# Get just column names
columns = get_column_names("outbound_parts")

# Get business metrics
metrics = get_business_metrics("inventory_snapshot")

# Generate compact schema summary for LLM prompts
summary = get_compact_schema_reference()

# Get detailed schema for one collection
detailed = get_schema_summary("warehouse_productivity")

# Reverse lookup: which collections have this column?
collections = get_collections_for_column("warehouse_id")
# → ["inbound_parts", "outbound_parts", "inventory_snapshot", 
#     "warehouse_productivity", "employee_productivity"]
```

### Intent Classifier (Schema-Aware)

Before:
```python
_SYSTEM_PROMPT = """You are an intent classifier.
Available collections: inbound_parts, outbound_parts, ...
"""
```

After:
```python
def _build_system_prompt() -> str:
    schema_ref = get_compact_schema_reference()  # inject all schemas
    return f"""You are an intent classifier.
    
{schema_ref}

Use the schema reference above to determine which collection(s) 
contain the mentioned columns/data.
"""
```

**Result:** LLM sees:
- All column names with types
- All business metrics
- Collection descriptions and grain
- Can make informed routing decisions

### Format Response (Schema-Aware)

```python
# Build schema context for queried collections
schema_context = ""
for collection_name in collections_queried:
    schema_context += get_schema_summary(collection_name) + "\n\n"

# Pass to LLM
prompt = f"""
User Question: {query}
Collections Queried: {collections}

{schema_context}

Data: {data_json}

Generate markdown using the schema information above.
"""
```

**Result:** LLM knows:
- What columns exist in the result data
- Column types and descriptions
- Business metrics available
- Can format results accurately without hallucinating

## Schema Structure

Each collection schema in `collections_schema.py` contains:

```python
{
    "name": "collection_name",
    "description": "What this collection represents",
    "grain": "One record per X per Y",
    
    "columns": {
        "column_name": {
            "type": "string | integer | float | date",
            "description": "What this column means",
            "field_to_query": "normalized.field.path"
        },
        # ... more columns
    },
    
    "derived_fields": {
        "field_name": {
            "description": "How this is derived"
        }
    },
    
    "business_metrics": {
        "metric_name": "formula or description",
        # e.g., "fill_rate": "sum(qty_shipped) / sum(qty_ordered)"
    },
    
    "common_filters": ["date", "warehouse_id", ...],
    "common_group_by": ["warehouse_id", "shift", ...],
    
    "relationships": {
        "other_collection": {
            "join_keys": ["shared_field"],
            "description": "Why you'd join these"
        }
    },
    
    "use_cases": [
        "brief description of common use case",
        # ...
    ]
}
```

## Collections

### 1. **inbound_parts**
- **Grain:** One record per purchase order (`po_number`)
- **Key Columns:** `supplier_name`, `part_number`, `qty_ordered`, `qty_received`, `expected_date`, `received_date`, `warehouse_id`
- **Key Metrics:** `avg_inbound_lead_time`, `on_time_receipts_pct`, `qty_discrepancy_pct`

### 2. **outbound_parts**
- **Grain:** One record per customer order (`order_number`)
- **Key Columns:** `customer_name`, `part_number`, `qty_ordered`, `qty_shipped`, `backorder_qty`, `otif_flag`, `order_date`, `shipped_date`, `warehouse_id`
- **Key Metrics:** `fill_rate`, `otif`, `backorder_rate`

### 3. **inventory_snapshot**
- **Grain:** One record per SKU per warehouse per date
- **Key Columns:** `part_number`, `warehouse_id`, `snapshot_date`, `on_hand_qty`, `available_qty`, `safety_stock`, `days_of_supply`, `stockout_flag`
- **Key Metrics:** `stockout_pct`, `days_of_supply`

### 4. **warehouse_productivity**
- **Grain:** One record per warehouse per date per shift
- **Key Columns:** `warehouse_id`, `date`, `shift`, `lines_picked`, `lines_packed`, `orders_processed`, `labor_hours`, `picks_per_hour`, `equipment_utilization_pct`, `sla_adherence_pct`
- **Key Metrics:** `lines_per_labor_hour`, `orders_per_day`, `sla_adherence`

### 5. **employee_productivity**
- **Grain:** One record per employee per date
- **Key Columns:** `employee_id`, `role`, `warehouse_id`, `shift`, `date`, `picks`, `hours_worked`, `picks_per_hour`, `errors`, `overtime_hours`
- **Key Metrics:** `picks_per_hour`, `error_rate`, `overtime_pct`

## Query Flow (Schema-Aware)

```
User Query: "How many warehouses do we have?"
    ↓
Intent Classifier (with schema context)
    → Sees warehouse_id exists in warehouse_productivity
    → intent=analytical_single, collection=warehouse_productivity
    ↓
Single Query Handler
    → Calls warehouse_productivity_tool.compute_general_stats()
    ↓
Tool executes generic aggregation:
    → db.warehouse_productivity.distinct("warehouse_id")
    → Returns: ["WH-01", "WH-02", "WH-03"]
    → Adds warehouse_count=3 to results
    ↓
Format Response (with schema context for warehouse_productivity)
    → LLM sees schema says warehouse_id is available
    → Formats result: "We have 3 warehouses: WH-01, WH-02, WH-03"
```

**No hardcoding!** The system:
- Used schema to route to correct collection
- Used generic distinct() aggregation (not hardcoded for "warehouses")
- Used schema context to format response correctly

## Benefits

### 1. **Maintainability**
- Schema changes in ONE place → automatically reflected everywhere
- Add a new column → LLM sees it in next query
- Change a metric formula → no code changes needed

### 2. **Flexibility**
- Same query logic works for any collection
- "How many X?" works for warehouses, employees, suppliers, SKUs, etc.
- No special-case code

### 3. **Accuracy**
- LLM can't hallucinate columns that don't exist
- Schema provides type information → better formatting
- Business metrics defined formally, not guessed

### 4. **Extensibility**
- Add a new collection → add schema → works immediately
- Add a new KPI → update schema → LLM sees it
- No code changes in intent classifier or format response

## Adding a New Collection

1. **Add schema to `collections_schema.py`:**
   ```python
   NEW_COLLECTION_SCHEMA = {
       "name": "new_collection",
       "description": "...",
       "columns": { ... },
       "business_metrics": { ... },
       # ...
   }
   ```

2. **Register in `schema_registry.py`:**
   ```python
   SCHEMA_REGISTRY["new_collection"] = NEW_COLLECTION_SCHEMA
   ```

3. **Create tool in `app/tools/`:**
   ```python
   # Tool can reference schema:
   from app.config.schema_registry import get_schema
   
   COLLECTION = "new_collection"
   schema = get_schema(COLLECTION)
   columns = schema["columns"]
   # ...
   ```

4. **Done!** Intent classifier and format response automatically see the new schema.

## Column-Aware Routing

The schema registry builds a reverse index:

```python
COLUMN_TO_COLLECTIONS = {
    "warehouse_id": ["inbound_parts", "outbound_parts", "inventory_snapshot", 
                     "warehouse_productivity", "employee_productivity"],
    "employee_id": ["employee_productivity"],
    "customer_name": ["outbound_parts"],
    "supplier_name": ["inbound_parts"],
    # ...
}
```

Intent classifier uses this for column-based routing:
- Query mentions `employee_id` → route to `employee_productivity`
- Query mentions `customer_name` → route to `outbound_parts`
- Query mentions `warehouse_id` + `shift` → route to `warehouse_productivity` (both columns exist there)

## Best Practices

### DO:
✅ Define all column names in `collections_schema.py`  
✅ Use `schema_registry.getschema()` in tools  
✅ Inject schema context into LLM prompts  
✅ Write generic query logic that works for any collection  
✅ Add new columns to schema → no code changes  

### DON'T:
❌ Hardcode column names in prompts  
❌ Write special-case logic for specific questions  
❌ Duplicate schema information across files  
❌ Assume a column exists without checking schema  
❌ Add collection-specific routing logic in intent classifier  

## Testing Schema Awareness

Run the schema registry test:

```bash
cd warehouse_kpi_agent
python -m app.config.schema_registry
```

Output shows:
- Compact schema reference (what LLM sees)
- Column-to-collection mappings
- Available columns for each collection

## Future Enhancements

1. **Schema Validation**
   - Validate query results against schema
   - Warn if unexpected columns appear

2. **Dynamic Schema Updates**
   - Hot-reload schemas without restarting
   - Schema versioning

3. **Schema-Based Query Builder**
   - Auto-generate MongoDB aggregation pipelines from schema
   - Type-safe query construction

4. **Schema Documentation Generation**
   - Auto-generate API docs from schemas
   - Generate ER diagrams from relationships

## Summary

The schema-driven architecture ensures:
- **Single source of truth** for all collection metadata
- **Schema-aware LLM prompts** for accurate routing and formatting
- **Generic, reusable** query logic (no special cases)
- **Easy extensibility** - new collections/columns work immediately
- **Reduced hallucination** - LLM knows what's real vs what's not

This design follows the principle: **"Data about the data should be centralized and injected where needed, not scattered and duplicated."**
