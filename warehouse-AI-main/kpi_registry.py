KPI_REGISTRY = {

    # ================= INBOUND ================= #
    "avg_inbound_lead_time": {
        "area": "inbound",
        "name": "Avg Inbound Lead Time (days)",
        "description": "Average days between expected and received dates",
        "formula": "AVG(DATEDIFF(day, expected_date, received_date))",
        "tables": ["inbound_parts"],
        "type": "metric",
        "owner": "Ops Analytics"
    },

    "on_time_receipts_pct": {
        "area": "inbound",
        "name": "% Receipts On-Time",
        "description": "On-time receipts divided by total receipts",
        "formula": "SUM(received_date <= expected_date) / COUNT(*)",
        "tables": ["inbound_parts"],
        "type": "metric",
        "owner": "Ops Analytics"
    },

    "qty_discrepancy_pct": {
        "area": "inbound",
        "name": "% Qty Discrepancies",
        "description": "Discrepancy quantity over total ordered quantity",
        "formula": "SUM(discrepancy_qty) / SUM(qty_ordered)",
        "tables": ["inbound_parts"],
        "type": "metric",
        "owner": "Quality"
    },

    "top_delaying_suppliers": {
        "area": "inbound",
        "name": "Top 5 Delaying Suppliers",
        "description": "Suppliers with highest delayed quantity",
        "formula": "GROUP BY supplier_name ORDER BY SUM(late_qty) DESC LIMIT 5",
        "tables": ["inbound_parts"],
        "type": "aggregation",
        "owner": "Purchasing"
    },

    # ================= OUTBOUND ================= #
    "fill_rate": {
        "area": "outbound",
        "name": "Fill Rate %",
        "description": "Shipped quantity divided by ordered quantity",
        "formula": "SUM(qty_shipped) / SUM(qty_ordered)",
        "tables": ["outbound_parts"],
        "type": "metric",
        "owner": "Customer Service"
    },

    "otif": {
        "area": "outbound",
        "name": "OTIF %",
        "description": "Orders shipped on time and in full",
        "formula": "SUM(otif_flag=1) / COUNT(order_number)",
        "tables": ["outbound_parts"],
        "type": "metric",
        "owner": "Logistics"
    },

    "backorder_rate": {
        "area": "outbound",
        "name": "Backorder Rate %",
        "description": "Backordered quantity over total ordered quantity",
        "formula": "SUM(backorder_qty) / SUM(qty_ordered)",
        "tables": ["outbound_parts"],
        "type": "metric",
        "owner": "Logistics"
    },

    "top_backorder_skus": {
        "area": "outbound",
        "name": "Top 10 SKUs by Backorder",
        "description": "SKUs with highest backorder quantity",
        "formula": "GROUP BY part_number ORDER BY SUM(backorder_qty) DESC LIMIT 10",
        "tables": ["outbound_parts"],
        "type": "aggregation",
        "owner": "Supply Planning"
    },

    # ================= INVENTORY ================= #
    "days_of_supply": {
        "area": "inventory",
        "name": "Days of Supply",
        "description": "On-hand inventory divided by average daily demand",
        "formula": "on_hand_qty / avg_daily_demand",
        "tables": ["inventory_snapshot", "outbound_parts"],
        "type": "derived",
        "owner": "Supply Planning"
    },

    "stockout_pct": {
        "area": "inventory",
        "name": "% Stock-out Days",
        "description": "Days with stockout divided by total days",
        "formula": "SUM(stockout_flag) / COUNT(*)",
        "tables": ["inventory_snapshot"],
        "type": "metric",
        "owner": "Supply Planning"
    },

    # "inventory_turns": {
    #     "area": "inventory",
    #     "name": "Inventory Turns",
    #     "description": "Annualized cost of goods sold divided by average inventory",
    #     "formula": "(12 * SUM(monthly_issues_value)) / AVG(month_end_inventory_value)",
    #     "tables": ["inventory_snapshot","finance"],
    #     "type": "derived",
    #     "owner": "Finance"
    # },

    # "aged_inventory_180": {
    #     "area": "inventory",
    #     "name": "Aged Inventory >180d",
    #     "description": "Value of inventory older than 180 days",
    #     "formula": "SUM(age_days > 180 * on_hand_qty)",
    #     "tables": ["inventory_snapshot","cost"],
    #     "type": "aggregation",
    #     "owner": "Finance"
    # },

    # ================= WAREHOUSE ================= #
    "lines_per_labor_hour": {
        "area": "warehouse",
        "name": "Lines Picked per Labor-Hour",
        "description": "Lines picked divided by labor hours",
        "formula": "SUM(lines_picked) / SUM(labor_hours)",
        "tables": ["warehouse_productivity"],
        "type": "metric",
        "owner": "Operations"
    },

    "orders_per_day": {
        "area": "warehouse",
        "name": "Orders per Day",
        "description": "Total number of orders processed",
        "formula": "SUM(orders_processed)",
        "tables": ["warehouse_productivity"],
        "type": "metric",
        "owner": "Operations"
    },

    "sla_adherence": {
        "area": "warehouse",
        "name": "SLA Adherence %",
        "description": "Percentage of orders meeting SLA",
        "formula": "AVG(sla_adherence_pct)",
        "tables": ["warehouse_productivity"],
        "type": "metric",
        "owner": "Operations"
    },

    # ================= EMPLOYEE ================= #
    "picks_per_hour": {
        "area": "employee",
        "name": "Picks per Person per Hour",
        "description": "Picks divided by hours worked",
        "formula": "SUM(picks) / SUM(hours_worked)",
        "tables": ["employee_productivity"],
        "type": "metric",
        "owner": "Operations"
    },

    "error_rate": {
        "area": "employee",
        "name": "Error Rate %",
        "description": "Errors divided by total tasks",
        "formula": "SUM(errors) / SUM(tasks_completed)",
        "tables": ["employee_productivity"],
        "type": "metric",
        "owner": "Quality"
    },

    "overtime_pct": {
        "area": "employee",
        "name": "Overtime %",
        "description": "Overtime hours divided by total working hours",
        "formula": "SUM(overtime_hours) / SUM(hours_worked + overtime_hours)",
        "tables": ["employee_productivity"],
        "type": "metric",
        "owner": "HR"
    }
}