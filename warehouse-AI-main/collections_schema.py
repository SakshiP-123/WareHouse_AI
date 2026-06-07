INBOUND_SCHEMA = {
    "name": "inbound_parts",

    "description": "Represents inbound purchase orders received from suppliers into warehouses. Used to evaluate supplier performance, delivery timeliness, discrepancies, and lead time.",

    "grain": "One record per purchase order (po_number)",

    "columns": {

        "po_number": {
            "type": "string",
            "description": "Unique identifier for each purchase order",
            "field_to_query": "raw.po_number"
        },

        "supplier_id": {
            "type": "string",
            "description": "Unique identifier of the supplier",
            "field_to_query": "normalized.supplier.id"
        },

        "supplier_name": {
            "type": "string",
            "description": "Name of the supplier providing goods",
            "field_to_query": "normalized.supplier.name"
        },

        "part_number": {
            "type": "string",
            "description": "Product/SKU identifier",
            "field_to_query": "normalized.part_number"
        },

        "expected_date": {
            "type": "date",
            "description": "Expected delivery date from supplier",
            "field_to_query": "normalized.dates.expected"
        },

        "received_date": {
            "type": "date",
            "description": "Actual date when goods were received",
            "field_to_query": "normalized.dates.received"
        },

        "qty_ordered": {
            "type": "integer",
            "description": "Quantity ordered from supplier",
            "field_to_query": "normalized.quantities.ordered"
        },

        "qty_received": {
            "type": "integer",
            "description": "Quantity actually received",
            "field_to_query": "normalized.quantities.received"
        },

        "inbound_lead_time_days": {
            "type": "integer",
            "description": "Number of days between expected and received date (can be negative if early)",
            "field_to_query": "raw.inbound_lead_time_days"
        },

        "discrepancy_qty": {
            "type": "integer",
            "description": "Difference between ordered and received quantity (qty_ordered - qty_received)",
            "field_to_query": "raw.discrepancy_qty"
        },

        "warehouse_id": {
            "type": "string",
            "description": "Warehouse where goods are received (WH-01, WH-02, WH-03)",
            "field_to_query": "normalized.warehouse_id",
            "possible_values": ["WH-01", "WH-02", "WH-03"]
        }
    },

    "derived_fields": {
        "sku_family": {
            "description": "Derived from first two characters of part_number (e.g., ZX-9910 → ZX)",
            "field_to_query": "normalized.sku_family"
        }
    },

    "business_metrics": {
        "avg_lead_time": "average(inbound_lead_time_days)",
        "on_time_delivery_pct": "percentage of orders where received_date <= expected_date",
        "discrepancy_rate": "sum(discrepancy_qty) / sum(qty_ordered)"
    },

    "common_filters": [
        "expected_date",
        "received_date",
        "warehouse_id",
        "supplier_name",
        "part_number"
    ],

    "common_group_by": [
        "supplier_name",
        "warehouse_id",
        "part_number",
        "sku_family"
    ],

    "relationships": {
        "inventory": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to analyze how inbound supply impacts stock levels"
        },
        "outbound": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to compare supply vs demand"
        }
    },

    "use_cases": [
        "supplier performance analysis",
        "lead time tracking",
        "delivery delay analysis",
        "inbound discrepancy monitoring",
        "supply chain efficiency evaluation"
    ]
}

OUTBOUND_SCHEMA = {
    "name": "outbound_parts",
    "description": "Represents outbound customer orders and shipments from warehouses. Used to measure fulfillment performance, delivery timeliness, and backorders.",
    "grain": "One record per customer order (order_number)",

    "columns": {

        "order_number": {
            "type": "string",
            "description": "Unique identifier for each customer order",
            "field_to_query": "raw.order_number"
        },

        "customer_id": {
            "type": "string",
            "description": "Unique identifier of the customer",
            "field_to_query": "normalized.customer.id"
        },

        "customer_name": {
            "type": "string",
            "description": "Name of the customer placing the order",
            "field_to_query": "normalized.customer.name"
        },

        "part_number": {
            "type": "string",
            "description": "Product/SKU identifier",
            "field_to_query": "normalized.part_number"
        },

        "order_date": {
            "type": "date",
            "description": "Date when the customer placed the order",
            "field_to_query": "normalized.dates.order"
        },

        "promise_date": {
            "type": "date",
            "description": "Promised delivery date to the customer",
            "field_to_query": "normalized.dates.promise"
        },

        "shipped_date": {
            "type": "date",
            "description": "Actual date when the order was shipped",
            "field_to_query": "normalized.dates.shipped"
        },

        "qty_ordered": {
            "type": "integer",
            "description": "Quantity requested by the customer",
            "field_to_query": "normalized.quantities.ordered"
        },

        "qty_shipped": {
            "type": "integer",
            "description": "Quantity actually shipped",
            "field_to_query": "normalized.quantities.shipped"
        },

        "backorder_qty": {
            "type": "integer",
            "description": "Quantity not fulfilled due to insufficient stock",
            "field_to_query": "normalized.quantities.backorder"
        },

        "otif_flag": {
            "type": "integer",
            "description": "On-Time In-Full indicator (1 = delivered on time and in full, 0 = otherwise)",
            "field_to_query": "normalized.metrics.otif"
        },

        "fill_rate": {
            "type": "float",
            "description": "Ratio of shipped quantity to ordered quantity (qty_shipped / qty_ordered). Derived metric.",
            "field_to_query": "normalized.metrics.fill_rate"
        },

        "warehouse_id": {
            "type": "string",
            "description": "Warehouse fulfilling the order (WH-01, WH-02, WH-03)",
            "field_to_query": "raw.warehouse_id"
        }
    },

    "derived_fields": {
        "sku_family": {
            "description": "Derived from first two characters of part_number (e.g., ZX-9910 → ZX)",
            "field_to_query": "normalized.sku_family"
        }
    },

    "business_metrics": {
        "fill_rate": "sum(qty_shipped) / sum(qty_ordered)",
        "backorder_rate": "sum(backorder_qty) / sum(qty_ordered)",
        "otif": "average(otif_flag)"
    },

    "common_filters": [
        "order_date",
        "shipped_date",
        "warehouse_id",
        "part_number"
    ],

    "common_group_by": [
        "warehouse_id",
        "part_number",
        "sku_family",
        "customer_name"
    ],

    "relationships": {
        "inventory": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to check stock availability and stockouts"
        },
        "inbound": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to analyze supply vs demand"
        }
    },

    "use_cases": [
        "fill rate analysis",
        "OTIF performance tracking",
        "backorder analysis",
        "customer fulfillment efficiency",
        "warehouse performance comparison"
    ]
}


INVENTORY_SCHEMA = {
    "name": "inventory_snapshot",

    "description": "Represents detailed inventory levels for each product across warehouses at a given date. Used for stock monitoring, replenishment planning, and stockout analysis.",

    "grain": "One record per product (part_number) per warehouse (warehouse_id) per snapshot_date",

    "columns": {

        "snapshot_date": {
            "type": "date",
            "description": "Date when inventory snapshot was taken",
            "field_to_query": "normalized.snapshot_date"
        },

        "warehouse_id": {
            "type": "string",
            "description": "Warehouse identifier (WH-01, WH-02, WH-03)",
            "field_to_query": "normalized.warehouse_id"
        },

        "warehouse_name": {
            "type": "string",
            "description": "Human-readable name of the warehouse",
            "field_to_query": "normalized.warehouse_name"
        },

        "location": {
            "type": "string",
            "description": "Geographic location of the warehouse",
            "field_to_query": "normalized.location"
        },

        "part_number": {
            "type": "string",
            "description": "Product/SKU identifier",
            "field_to_query": "normalized.part_number"
        },

        "sku_family": {
            "type": "string",
            "description": "Product family derived from part_number (e.g., ZX, AX)",
            "field_to_query": "normalized.sku_family"
        },

        "on_hand_qty": {
            "type": "integer",
            "description": "Total physical inventory available in warehouse",
            "field_to_query": "normalized.stock.on_hand"
        },

        "available_qty": {
            "type": "integer",
            "description": "Inventory available for sale after reservations",
            "field_to_query": "normalized.stock.available"
        },

        "safety_stock": {
            "type": "integer",
            "description": "Minimum inventory threshold to prevent stockouts",
            "field_to_query": "raw.safety_stock"
        },

        "reorder_point": {
            "type": "integer",
            "description": "Inventory level at which replenishment should be triggered",
            "field_to_query": "raw.reorder_point"
        },

        "days_of_supply": {
            "type": "integer",
            "description": "Estimated number of days current stock will last based on demand",
            "field_to_query": "raw.days_of_supply"
        },

        "stockout_flag": {
            "type": "integer",
            "description": "Indicates stockout condition (1 = no stock available, 0 = stock available)",
            "field_to_query": "normalized.metrics.stockout_flag"
        },

        "age_days": {
            "type": "integer",
            "description": "Number of days inventory has been held (inventory aging)",
            "field_to_query": "normalized.metrics.age_days"
        }
    },

    "business_metrics": {

        "stockout_pct": "average(stockout_flag)",

        "low_stock_pct": "percentage where available_qty <= safety_stock",

        "inventory_health_score": "combination of stockout_flag, days_of_supply, and age_days",

        "excess_inventory": "percentage where days_of_supply is very high",

        "aging_inventory": "average(age_days)"
    },

    "common_filters": [
        "snapshot_date",
        "warehouse_id",
        "warehouse_name",
        "location",
        "part_number",
        "sku_family"
    ],

    "common_group_by": [
        "warehouse_id",
        "warehouse_name",
        "location",
        "part_number",
        "sku_family"
    ],

    "relationships": {

        "outbound_parts": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to analyze how stock levels impact order fulfillment and backorders"
        },

        "inbound_parts": {
            "join_keys": ["part_number", "warehouse_id"],
            "description": "Join to analyze how incoming supply affects inventory levels"
        }
    },

    "use_cases": [
        "stockout analysis",
        "inventory health monitoring",
        "replenishment planning",
        "warehouse comparison",
        "inventory aging analysis",
        "safety stock optimization",
        "supply-demand balancing"
    ]
}

WAREHOUSE_PRODUCTIVITY_SCHEMA = {
    "name": "warehouse_productivity",

    "description": "Represents detailed warehouse operational performance across shifts. Used to analyze picking efficiency, packing efficiency, labor productivity, equipment utilization, and SLA adherence.",

    "grain": "One record per warehouse (warehouse_id) per date per shift",

    "columns": {

        "date": {
            "type": "date",
            "description": "Date of warehouse operation",
            "field_to_query": "normalized.date"
        },

        "warehouse_id": {
            "type": "string",
            "description": "Warehouse identifier (WH-01, WH-02, WH-03)",
            "field_to_query": "normalized.warehouse_id",
            "possible_values": ["WH-01", "WH-02", "WH-03"]
        },

        "shift": {
            "type": "string",
            "description": "Shift during which operations occurred (e.g. Day, Night)",
            "field_to_query": "normalized.shift",
            "possible_values": ["Day", "Night"]
        },

        "lines_picked": {
            "type": "integer",
            "description": "Total number of order lines picked",
            "field_to_query": "normalized.metrics.lines_picked"
        },

        "lines_packed": {
            "type": "integer",
            "description": "Total number of order lines packed",
            "field_to_query": "normalized.metrics.lines_packed"
        },

        "orders_processed": {
            "type": "integer",
            "description": "Total number of customer orders processed",
            "field_to_query": "normalized.metrics.orders_processed"
        },

        "labor_hours": {
            "type": "float",
            "description": "Total labor hours spent by warehouse staff",
            "field_to_query": "normalized.metrics.labor_hours"
        },

        "picks_per_hour": {
            "type": "float",
            "description": "Number of picks completed per labor hour (productivity metric)",
            "field_to_query": "raw.picks_per_hour"
        },

        "touches_per_order": {
            "type": "float",
            "description": "Average number of handling touches per order (efficiency indicator)",
            "field_to_query": "raw.touches_per_order"
        },

        "equipment_utilization_pct": {
            "type": "float",
            "description": "Percentage of time warehouse equipment was actively used",
            "field_to_query": "raw.equipment_utilization_pct"
        },

        "sla_adherence_pct": {
            "type": "float",
            "description": "Percentage of orders meeting SLA requirements",
            "field_to_query": "normalized.metrics.sla"
        }
    },

    "business_metrics": {

        "lines_per_hour": "sum(lines_picked) / sum(labor_hours)",

        "packing_efficiency": "sum(lines_packed) / sum(lines_picked)",

        "orders_per_hour": "sum(orders_processed) / sum(labor_hours)",

        "avg_touches_per_order": "average(touches_per_order)",

        "equipment_utilization": "average(equipment_utilization_pct)",

        "sla_compliance": "average(sla_adherence_pct)"
    },

    "common_filters": [
        "date",
        "warehouse_id",
        "shift"
    ],

    "common_group_by": [
        "warehouse_id",
        "shift",
        "date"
    ],

    "relationships": {

        "outbound_parts": {
            "join_keys": ["warehouse_id"],
            "description": "Join to analyze how outbound order volume impacts warehouse performance"
        },

        "inventory_snapshot": {
            "join_keys": ["warehouse_id"],
            "description": "Join to analyze how inventory levels affect warehouse workload"
        }
    },

    "use_cases": [
        "warehouse productivity analysis",
        "labor efficiency tracking",
        "shift-wise performance comparison",
        "SLA compliance monitoring",
        "equipment utilization analysis",
        "operational bottleneck identification"
    ],

    "storage_note": "Data is stored under normalized.* in MongoDB (e.g., normalized.lines_picked, normalized.labor_hours)"
}


EMPLOYEE_PRODUCTIVITY_SCHEMA = {
    "name": "employee_productivity",

    "description": "Represents individual employee performance in warehouse operations. Used to evaluate productivity, efficiency, error rates, and workload distribution across roles, shifts, and warehouses.",

    "grain": "One record per employee (employee_id) per date",

    "columns": {

        "date": {
            "type": "date",
            "description": "Date of employee activity",
            "field_to_query": "normalized.date"
        },

        "employee_id": {
            "type": "string",
            "description": "Unique identifier for each employee",
            "field_to_query": "normalized.employee_id"
        },

        "role": {
            "type": "string",
            "description": "Job role of the employee (e.g., Picker, Packer, Supervisor)",
            "field_to_query": "raw.role",
            "possible_values": ["Picker", "Packer", "Supervisor"]
        },

        "warehouse_id": {
            "type": "string",
            "description": "Warehouse where the employee is working",
            "field_to_query": "normalized.warehouse_id",
            "possible_values": ["WH-01", "WH-02", "WH-03"]
        },

        "shift": {
            "type": "string",
            "description": "Shift during which the employee worked (morning, evening, night)",
            "field_to_query": "raw.shift",
            "possible_values": ["Day", "Night"]
        },

        "tasks_completed": {
            "type": "integer",
            "description": "Total number of tasks completed by the employee",
            "field_to_query": "raw.tasks_completed"
        },

        "picks": {
            "type": "integer",
            "description": "Total number of picking operations performed",
            "field_to_query": "normalized.metrics.picks"
        },

        "hours_worked": {
            "type": "float",
            "description": "Total working hours logged",
            "field_to_query": "normalized.metrics.hours"
        },

        "picks_per_hour": {
            "type": "float",
            "description": "Number of picks completed per hour (productivity metric)",
            "field_to_query": "raw.picks_per_hour"
        },

        "errors": {
            "type": "integer",
            "description": "Number of operational errors made by the employee",
            "field_to_query": "normalized.metrics.errors"
        },

        "rework": {
            "type": "integer",
            "description": "Number of rework tasks required due to errors",
            "field_to_query": "raw.rework"
        },

        "overtime_hours": {
            "type": "float",
            "description": "Number of overtime hours worked",
            "field_to_query": "normalized.metrics.overtime"
        }
    },

    "business_metrics": {

        "employee_productivity": "sum(picks) / sum(hours_worked)",

        "error_rate": "sum(errors) / sum(picks)",

        "rework_rate": "sum(rework) / sum(tasks_completed)",

        "overtime_pct": "sum(overtime_hours) / sum(hours_worked + overtime_hours)",

        "avg_tasks_per_employee": "average(tasks_completed)"
    },

    "common_filters": [
        "date",
        "employee_id",
        "role",
        "warehouse_id",
        "shift"
    ],

    "common_group_by": [
        "employee_id",
        "role",
        "warehouse_id",
        "shift",
        "date"
    ],

    "relationships": {

        "warehouse_productivity": {
            "join_keys": ["warehouse_id", "date", "shift"],
            "description": "Join to analyze how individual performance contributes to overall warehouse productivity"
        },

        "outbound_parts": {
            "join_keys": ["warehouse_id"],
            "description": "Join to analyze how employee performance impacts order fulfillment"
        },

        "inventory_snapshot": {
            "join_keys": ["warehouse_id"],
            "description": "Join to analyze how workload relates to stock levels"
        }
    },

    "use_cases": [
        "employee performance analysis",
        "productivity benchmarking",
        "error rate tracking",
        "overtime analysis",
        "shift-wise workforce efficiency",
        "role-based performance comparison"
    ],

    "storage_note": "Data is stored under normalized.* in MongoDB (e.g., normalized.picks, normalized.hours_worked)"
}