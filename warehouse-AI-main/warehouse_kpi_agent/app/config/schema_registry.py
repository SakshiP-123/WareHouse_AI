"""Schema Registry - Central access point for all collection schemas.

Provides schema information to:
  - Intent classifier (for better intent/collection detection)
  - Query tools (for dynamic query building)
  - Format response (for column-aware markdown generation)
  - Validation layers

Imports schemas from the parent collections_schema.py module.
"""

import logging
from typing import Any, Optional
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add parent directory to path to import collections_schema
parent_dir = Path(__file__).parent.parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import schemas from parent project folder
try:
    from collections_schema import (
        INBOUND_SCHEMA,
        OUTBOUND_SCHEMA,
        INVENTORY_SCHEMA,
        WAREHOUSE_PRODUCTIVITY_SCHEMA,
        EMPLOYEE_PRODUCTIVITY_SCHEMA,
    )
except ImportError as e:
    logger.warning(f"Could not import schemas from collections_schema.py: {e}")
    INBOUND_SCHEMA = {}
    OUTBOUND_SCHEMA = {}
    INVENTORY_SCHEMA = {}
    WAREHOUSE_PRODUCTIVITY_SCHEMA = {}
    EMPLOYEE_PRODUCTIVITY_SCHEMA = {}


# ── Schema Registry ────────────────────────────────────────────────────────────
SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {
    "inbound_parts": INBOUND_SCHEMA,
    "outbound_parts": OUTBOUND_SCHEMA,
    "inventory_snapshot": INVENTORY_SCHEMA,
    "warehouse_productivity": WAREHOUSE_PRODUCTIVITY_SCHEMA,
    "employee_productivity": EMPLOYEE_PRODUCTIVITY_SCHEMA,
}


def get_schema(collection_name: str) -> Optional[dict[str, Any]]:
    """Get schema for a collection by name."""
    return SCHEMA_REGISTRY.get(collection_name)


def get_all_schemas() -> dict[str, dict[str, Any]]:
    """Get all collection schemas."""
    return SCHEMA_REGISTRY


def get_columns(collection_name: str) -> dict[str, Any]:
    """Get column definitions for a collection."""
    schema = get_schema(collection_name)
    return schema.get("columns", {}) if schema else {}


def get_column_names(collection_name: str) -> list[str]:
    """Get list of column names for a collection."""
    return list(get_columns(collection_name).keys())


def get_column_values_map(collection_name: str) -> dict[str, list[str]]:
    """Return a mapping of column names to their possible values (for categorical fields).
    
    Args:
        collection_name: The collection name
        
    Returns:
        Dict mapping column names to list of possible values (only for fields with possible_values)
    """
    columns = get_columns(collection_name)
    value_map = {}
    
    for col_name, col_def in columns.items():
        if isinstance(col_def, dict) and "possible_values" in col_def:
            value_map[col_name] = col_def["possible_values"]
    
    return value_map


def get_all_column_values() -> dict[str, dict[str, list[str]]]:
    """Return column-to-values mapping for ALL collections.
    
    Returns:
        Dict mapping collection name -> column name -> possible values
    """
    all_values = {}
    for collection in SCHEMA_REGISTRY.keys():
        values = get_column_values_map(collection)
        if values:  # Only add if there are any categorical fields
            all_values[collection] = values
    return all_values


def get_business_metrics(collection_name: str) -> dict[str, str]:
    """Get business metrics for a collection."""
    schema = get_schema(collection_name)
    return schema.get("business_metrics", {}) if schema else {}


def get_common_filters(collection_name: str) -> list[str]:
    """Get common filter fields for a collection."""
    schema = get_schema(collection_name)
    return schema.get("common_filters", []) if schema else []


def get_relationships(collection_name: str) -> dict[str, Any]:
    """Get relationship information for a collection."""
    schema = get_schema(collection_name)
    return schema.get("relationships", {}) if schema else {}


def get_schema_summary(collection_name: str) -> str:
    """Generate a concise summary of a collection schema for LLM prompts.
    
    Returns a formatted string with:
    - Collection name and description
    - Available columns with types
    - Business metrics
    - Common filters
    """
    schema = get_schema(collection_name)
    if not schema:
        return f"[Schema not found for {collection_name}]"
    
    lines = [
        f"### {schema.get('name', collection_name)}",
        f"**Description:** {schema.get('description', 'N/A')}",
        f"**Grain:** {schema.get('grain', 'N/A')}",
        "",
        "**Columns:**"
    ]
    
    columns = schema.get("columns", {})
    for col_name, col_def in columns.items():
        col_type = col_def.get("type", "unknown")
        col_desc = col_def.get("description", "")
        lines.append(f"  - `{col_name}` ({col_type}): {col_desc}")
    
    derived = schema.get("derived_fields", {})
    if derived:
        lines.append("")
        lines.append("**Derived Fields:**")
        for field_name, field_def in derived.items():
            lines.append(f"  - `{field_name}`: {field_def.get('description', 'N/A')}")
    
    metrics = schema.get("business_metrics", {})
    if metrics:
        lines.append("")
        lines.append("**Business Metrics:**")
        for metric_name, formula in metrics.items():
            lines.append(f"  - `{metric_name}`: {formula}")
    
    filters = schema.get("common_filters", [])
    if filters:
        lines.append("")
        lines.append(f"**Common Filters:** {', '.join(filters)}")
    
    return "\n".join(lines)


def get_all_schemas_summary() -> str:
    """Generate a comprehensive summary of all schemas for LLM context.
    
    Returns a formatted markdown string with all collection schemas.
    """
    summaries = []
    for collection_name in sorted(SCHEMA_REGISTRY.keys()):
        summaries.append(get_schema_summary(collection_name))
        summaries.append("")  # blank line between schemas
    
    return "\n".join(summaries)


def get_compact_schema_reference() -> str:
    """Generate a compact schema reference for LLM prompts.
    
    Optimized for token efficiency - includes only essential info.
    """
    lines = ["## Collection Schemas Reference"]
    
    for collection_name in sorted(SCHEMA_REGISTRY.keys()):
        schema = get_schema(collection_name)
        if not schema:
            continue
        
        lines.append(f"\n**{schema.get('name')}**: {schema.get('description', 'N/A')}")
        
        # Columns (compact format)
        columns = schema.get("columns", {})
        col_list = [f"`{name}` ({defn.get('type', '?')})" for name, defn in columns.items()]
        lines.append(f"  Columns: {', '.join(col_list)}")
        
        # Key metrics
        metrics = schema.get("business_metrics", {})
        if metrics:
            metric_list = list(metrics.keys())
            lines.append(f"  Metrics: {', '.join(metric_list)}")
    
    return "\n".join(lines)


# ── Column-to-Collection Mapping ───────────────────────────────────────────────
def build_column_to_collection_map() -> dict[str, list[str]]:
    """Build a reverse mapping: column_name -> [collections that have it].
    
    Useful for intent classification when user mentions specific columns.
    """
    col_map: dict[str, list[str]] = {}
    
    for collection_name, schema in SCHEMA_REGISTRY.items():
        columns = schema.get("columns", {})
        for col_name in columns.keys():
            if col_name not in col_map:
                col_map[col_name] = []
            col_map[col_name].append(collection_name)
    
    return col_map


# Build the map on module load for fast lookup
COLUMN_TO_COLLECTIONS = build_column_to_collection_map()


def get_collections_for_column(column_name: str) -> list[str]:
    """Get list of collections that contain a specific column."""
    return COLUMN_TO_COLLECTIONS.get(column_name, [])


# ── KPI to Schema Mapping ──────────────────────────────────────────────────────
def get_kpi_schema_context(kpi_name: str, collection_name: str) -> dict[str, Any]:
    """Get schema context relevant to a specific KPI.
    
    Returns:
        dict with keys: kpi_name, collection, relevant_columns, formula
    """
    schema = get_schema(collection_name)
    if not schema:
        return {}
    
    metrics = schema.get("business_metrics", {})
    formula = metrics.get(kpi_name, "N/A")
    
    columns = schema.get("columns", {})
    
    return {
        "kpi_name": kpi_name,
        "collection": collection_name,
        "formula": formula,
        "available_columns": list(columns.keys()),
        "column_details": columns,
    }


if __name__ == "__main__":
    # Test the schema registry
    print("=== Schema Registry Test ===\n")
    print(get_compact_schema_reference())
    print("\n=== Column to Collections Map ===")
    print(f"warehouse_id appears in: {get_collections_for_column('warehouse_id')}")
    print(f"employee_id appears in: {get_collections_for_column('employee_id')}")
    print(f"part_number appears in: {get_collections_for_column('part_number')}")
