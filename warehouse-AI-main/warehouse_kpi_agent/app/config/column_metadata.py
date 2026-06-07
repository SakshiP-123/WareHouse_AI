"""Complete column-to-collection mapping with data types.

Maps every column name to:
- collection: which collection it belongs to
- type: "string", "numeric", "date", "boolean"
- values: possible values (for categorical fields)

This enables schema-aware, generalized querying without hardcoding.
"""

# Complete column mapping from CSV files
COLUMN_TO_COLLECTION_MAP = {
    # ── employee_productivity ─────────────────────────────────────────────────
    "date": {
        "collection": "employee_productivity",
        "type": "date",
        "description": "Date of the productivity record"
    },
    "employee_id": {
        "collection": "employee_productivity",
        "type": "string",
        "description": "Employee identifier (E-XXXX format)",
        "pattern": r"E-\d{4}"
    },
    "role": {
        "collection": "employee_productivity",
        "type": "categorical",
        "values": ["Picker", "Packer", "Supervisor"],
        "description": "Employee role/position"
    },
    "warehouse_id": {
        "collections": ["employee_productivity", "inbound_parts", "outbound_parts", "inventory_snapshot", "warehouse_productivity"],
        "type": "categorical",
        "values": ["WH-01", "WH-02", "WH-03"],
        "description": "Warehouse identifier"
    },
    "shift": {
        "collections": ["employee_productivity", "warehouse_productivity"],
        "type": "categorical",
        "values": ["Day", "Night"],
        "description": "Work shift"
    },
    "tasks_completed": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min", "count"],
        "description": "Number of tasks completed"
    },
    "picks": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min", "count"],
        "description": "Number of picks"
    },
    "hours_worked": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min"],
        "description": "Hours worked"
    },
    "picks_per_hour": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["avg", "max", "min"],
        "description": "Picks per hour rate"
    },
    "errors": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min", "count"],
        "description": "Number of errors"
    },
    "rework": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Rework count"
    },
    "overtime_hours": {
        "collection": "employee_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Overtime hours"
    },
    
    # ── inbound_parts ──────────────────────────────────────────────────────────
    "po_number": {
        "collection": "inbound_parts",
        "type": "string",
        "description": "Purchase order number"
    },
    "supplier_id": {
        "collection": "inbound_parts",
        "type": "string",
        "description": "Supplier identifier"
    },
    "supplier_name": {
        "collection": "inbound_parts",
        "type": "string",
        "description": "Supplier name"
    },
    "part_number": {
        "collections": ["inbound_parts", "outbound_parts", "inventory_snapshot"],
        "type": "string",
        "description": "Part/SKU number"
    },
    "expected_date": {
        "collection": "inbound_parts",
        "type": "date",
        "description": "Expected receipt date"
    },
    "received_date": {
        "collection": "inbound_parts",
        "type": "date",
        "description": "Actual receipt date"
    },
    "qty_ordered": {
        "collections": ["inbound_parts", "outbound_parts"],
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min", "count"],
        "description": "Quantity ordered"
    },
    "qty_received": {
        "collection": "inbound_parts",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min"],
        "description": "Quantity received"
    },
    "inbound_lead_time_days": {
        "collection": "inbound_parts",
        "type": "numeric",
        "aggregations": ["avg", "max", "min"],
        "description": "Lead time in days"
    },
    "discrepancy_qty": {
        "collection": "inbound_parts",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Discrepancy quantity"
    },
    
    # ── inventory_snapshot ─────────────────────────────────────────────────────
    "snapshot_date": {
        "collection": "inventory_snapshot",
        "type": "date",
        "description": "Date of inventory snapshot"
    },
    "warehouse_name": {
        "collection": "inventory_snapshot",
        "type": "string",
        "description": "Warehouse name"
    },
    "location": {
        "collection": "inventory_snapshot",
        "type": "string",
        "description": "Location within warehouse"
    },
    "sku_family": {
        "collection": "inventory_snapshot",
        "type": "categorical",
        "description": "SKU family/category"
    },
    "on_hand_qty": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "On-hand quantity"
    },
    "available_qty": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Available quantity"
    },
    "safety_stock": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["avg", "min"],
        "description": "Safety stock level"
    },
    "reorder_point": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["avg"],
        "description": "Reorder point"
    },
    "days_of_supply": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["avg", "min", "max"],
        "description": "Days of supply"
    },
    "stockout_flag": {
        "collection": "inventory_snapshot",
        "type": "boolean",
        "values": [True, False, 1, 0],
        "description": "Stockout flag"
    },
    "age_days": {
        "collection": "inventory_snapshot",
        "type": "numeric",
        "aggregations": ["avg", "max"],
        "description": "Inventory age in days"
    },
    
    # ── outbound_parts ─────────────────────────────────────────────────────────
    "order_number": {
        "collection": "outbound_parts",
        "type": "string",
        "description": "Order number"
    },
    "customer_id": {
        "collection": "outbound_parts",
        "type": "string",
        "description": "Customer identifier"
    },
    "customer_name": {
        "collection": "outbound_parts",
        "type": "categorical",
        "values": ["Customer X", "Customer Y", "Customer Z"],
        "description": "Customer name"
    },
    "order_date": {
        "collection": "outbound_parts",
        "type": "date",
        "description": "Order date"
    },
    "promise_date": {
        "collection": "outbound_parts",
        "type": "date",
        "description": "Promised delivery date"
    },
    "shipped_date": {
        "collection": "outbound_parts",
        "type": "date",
        "description": "Actual ship date"
    },
    "qty_shipped": {
        "collection": "outbound_parts",
        "type": "numeric",
        "aggregations": ["sum", "avg", "max", "min"],
        "description": "Quantity shipped"
    },
    "backorder_qty": {
        "collection": "outbound_parts",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Backorder quantity"
    },
    "otif_flag": {
        "collection": "outbound_parts",
        "type": "boolean",
        "values": [True, False, 1, 0],
        "description": "On-time in-full flag"
    },
    "fill_rate": {
        "collection": "outbound_parts",
        "type": "numeric",
        "aggregations": ["avg"],
        "description": "Fill rate percentage"
    },
    
    # ── warehouse_productivity ─────────────────────────────────────────────────
    "lines_picked": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Lines picked count"
    },
    "lines_packed": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Lines packed count"
    },
    "orders_processed": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Orders processed count"
    },
    "labor_hours": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["sum", "avg"],
        "description": "Labor hours"
    },
    "touches_per_order": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["avg"],
        "description": "Touches per order"
    },
    "equipment_utilization_pct": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["avg"],
        "description": "Equipment utilization percentage"
    },
    "sla_adherence_pct": {
        "collection": "warehouse_productivity",
        "type": "numeric",
        "aggregations": ["avg"],
        "description": "SLA adherence percentage"
    },
}


def get_numeric_columns(collection: str) -> list[str]:
    """Get all numeric columns for a collection."""
    return [
        col for col, info in COLUMN_TO_COLLECTION_MAP.items()
        if info.get("type") == "numeric" and (
            info.get("collection") == collection or
            collection in info.get("collections", [])
        )
    ]


def get_categorical_columns(collection: str) -> list[str]:
    """Get all categorical columns for a collection."""
    return [
        col for col, info in COLUMN_TO_COLLECTION_MAP.items()
        if info.get("type") == "categorical" and (
            info.get("collection") == collection or
            collection in info.get("collections", [])
        )
    ]


def get_categorical_values(column: str) -> list[str]:
    """Get possible values for a categorical column."""
    info = COLUMN_TO_COLLECTION_MAP.get(column, {})
    return info.get("values", [])


def is_numeric_column(column: str) -> bool:
    """Check if a column is numeric."""
    info = COLUMN_TO_COLLECTION_MAP.get(column, {})
    return info.get("type") == "numeric"


def is_categorical_column(column: str) -> bool:
    """Check if a column is categorical."""
    info = COLUMN_TO_COLLECTION_MAP.get(column, {})
    return info.get("type") in ("categorical", "boolean")
