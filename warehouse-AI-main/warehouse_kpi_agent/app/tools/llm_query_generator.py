"""LLM-based MongoDB Query Generator.

Replaces complex pattern matching with LLM that understands schemas.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langsmith import traceable
from pymongo.collection import Collection

from app.config.settings import LLM_MODEL, OLLAMA_BASE_URL
from app.config.schema_registry import get_schema
from app.config.column_metadata import COLUMN_TO_COLLECTION_MAP

logger = logging.getLogger(__name__)


def _convert_dates_in_pipeline(pipeline: list[dict]) -> list[dict]:
    """Convert date strings to datetime objects recursively.
    
    Handles two formats:
    1. {"$date": "ISO_STRING"} - MongoDB extended JSON
    2. Direct ISO strings in date operators ($gte, $lt, $lte, $gt, $eq)
    3. Direct ISO strings in $match fields (for date field names)
    """
    import re
    # Match dates like: 2025-05-14, 2025-05-14T00:00:00, 2025-05-14 00:00:00
    ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}')
    
    # Common date field names from all collections
    DATE_FIELDS = {
        'date', 'shipped_date', 'order_date', 'promise_date', 'expected_date',
        'received_date', 'snapshot_date'
    }
    
    def convert_value(val, parent_key=None, grandparent_key=None):
        if isinstance(val, dict):
            # Check for $date format
            if "$date" in val and isinstance(val["$date"], str):
                try:
                    return datetime.fromisoformat(val["$date"].replace('Z', '+00:00'))
                except Exception as e:
                    logger.warning(f"Failed to parse date {val['$date']}: {e}")
                    return val
            # Recursively process nested dicts
            return {k: convert_value(v, k, parent_key) for k, v in val.items()}
        elif isinstance(val, list):
            return [convert_value(item, parent_key, grandparent_key) for item in val]
        elif isinstance(val, str):
            # Convert ISO date strings in date comparison operators
            if parent_key in ('$gte', '$gt', '$lte', '$lt', '$eq'):
                if ISO_DATE_PATTERN.match(val):
                    try:
                        return datetime.fromisoformat(val.replace('Z', '+00:00'))
                    except Exception as e:
                        logger.warning(f"Failed to parse ISO date string {val}: {e}")
                        return val
            # Convert ISO date strings when the grandparent key is $match and parent is a date field
            elif grandparent_key == '$match' and parent_key in DATE_FIELDS:
                if ISO_DATE_PATTERN.match(val):
                    try:
                        return datetime.fromisoformat(val.replace('Z', '+00:00'))
                    except Exception as e:
                        logger.warning(f"Failed to parse date in $match.{parent_key}: {val}: {e}")
                        return val
        return val
    
    return [convert_value(stage) for stage in pipeline]


def _strip_objectids(results: list[dict]) -> list[dict]:
    """Remove _id fields (ObjectId) from results to prevent serialization errors.
    
    MongoDB's ObjectId cannot be serialized to JSON, so we strip all _id fields
    from the results before returning them to the API.
    """
    def clean_doc(doc):
        if isinstance(doc, dict):
            return {k: clean_doc(v) for k, v in doc.items() if k != '_id'}
        elif isinstance(doc, list):
            return [clean_doc(item) for item in doc]
        return doc
    
    return [clean_doc(doc) for doc in results]

# ── LLM singleton ─────────────────────────────────────────────────────────────
_llm: ChatOllama | None = None


def _get_llm() -> ChatOllama:
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
    return _llm


# ── System Prompt ─────────────────────────────────────────────────────────────
_QUERY_GENERATOR_SYSTEM = """You are a MongoDB aggregation pipeline expert.

Generate a MongoDB aggregation pipeline (JSON array) from natural language queries.

📋 CRITICAL RULES:
1. Output ONLY a valid JSON array - no explanations, markdown, or code fences
2. Match filters BEFORE grouping: $match → $group → $project
3. Only aggregate numeric fields (sum, avg, count, max, min)
4. String/categorical fields: use for filters or grouping ONLY
5. For date fields: ALWAYS use range queries with $gte and $lt, never direct string match
   - Example: {"date": {"$gte": {"$date": "2025-05-14T00:00:00.000Z"}, "$lt": {"$date": "2025-05-15T00:00:00.000Z"}}}
   - NEVER: {"date": "2025-05-14"}
6. Use {"$date": "ISO_STRING"} format for all date values
7. NO JavaScript constructors (new Date, new ObjectId) - JSON primitives only
8. Typo correction: match user input to correct field names and categorical values from schema
9. In $project, only reference fields that were created in $group or exist in documents
10. 🚨 ALWAYS exclude _id in $project stage: {"_id": 0, ...other fields...}
11. For UNIQUE/DISTINCT counts: Use $addToSet in $group, then $size in $project
    - Total unique: {"$group": {"_id": null, "unique_items": {"$addToSet": "$field"}}}
    - Unique BY dimension: {"$group": {"_id": "$dimension", "unique_items": {"$addToSet": "$field"}}}
    - CRITICAL: When user says "how many X by Y" or "X per Y", group by Y and count unique X
    - Example: "unique employees per warehouse" → group by warehouse_id, count unique employee_id
12. 🚨 For "HIGHEST/LOWEST AVERAGE" queries (CRITICAL PATTERN):
    - User asks: "X for highest/lowest average Y" (e.g., "part number for highest avg discrepancy")
    - MUST: Group by X dimension, calculate $avg of Y, sort by avg (desc/asc), limit 1
    - Example: {"$group": {"_id": "$part_number", "avg_val": {"$avg": "$discrepancy_qty"}}}
    - Then: {"$sort": {"avg_val": -1}}, {"$limit": 1}
    - Project BOTH the dimension AND the average value

🎯 GROUPING LOGIC (CRITICAL):
- Group by ONLY the dimensions explicitly mentioned in the query
- "compare X and Y" → group by that dimension only
- "what is total Z" → no grouping needed (or group all with _id: null)
- "for each A" → group by A
- DO NOT add extra grouping dimensions that weren't requested

📊 PATTERN EXAMPLES:

**Lookup value:**
```json
[
  {"$match": {"order_id": "ORD123"}},
  {"$project": {"_id": 0, "customer_id": 1}}
]
```

**Single aggregation:**
```json
[
  {"$match": {"employee_id": "E-100"}},
  {"$group": {"_id": null, "total": {"$sum": "$sales"}}},
  {"$project": {"_id": 0, "total": 1}}
]
```

**Comparison (group by ONE dimension):**
```json
[
  {"$match": {"product_id": "P-50"}},
  {"$group": {"_id": "$region", "total_sales": {"$sum": "$sales"}}},
  {"$project": {"_id": 0, "region": "$_id", "total_sales": 1}}
]
```

**Multiple filters + aggregation:**
```json
[
  {"$match": {"category": "Electronics", "status": "shipped"}},
  {"$group": {"_id": "$warehouse", "count": {"$sum": 1}}},
  {"$project": {"_id": 0, "warehouse": "$_id", "count": 1}}
]
```

**Top N:**
```json
[
  {"$group": {"_id": "$seller_id", "revenue": {"$sum": "$amount"}}},
  {"$sort": {"revenue": -1}},
  {"$limit": 10},
  {"$project": {"_id": 0, "seller_id": "$_id", "revenue": 1}}
]
```

**Date range:**
```json
[
  {"$match": {
    "date": {
      "$gte": {"$date": "2025-01-01T00:00:00.000Z"},
      "$lt": {"$date": "2025-02-01T00:00:00.000Z"}
    }
  }},
  {"$group": {"_id": null, "total": {"$sum": "$quantity"}}},
  {"$project": {"_id": 0, "total": 1}}
]
```

**Specific date (count orders on May 14, 2025):**
```json
[
  {"$match": {
    "promise_date": {
      "$gte": {"$date": "2025-05-14T00:00:00.000Z"},
      "$lt": {"$date": "2025-05-15T00:00:00.000Z"}
    }
  }},
  {"$group": {"_id": null, "count": {"$sum": 1}}},
  {"$project": {"_id": 0, "count": 1}}
]
```

**Count UNIQUE/DISTINCT values (critical pattern):**
```json
[
  {"$match": {"warehouse_id": "WH-01"}},
  {"$group": {
    "_id": null,
    "unique_employees": {"$addToSet": "$employee_id"}
  }},
  {"$project": {
    "_id": 0,
    "unique_employee_count": {"$size": "$unique_employees"}
  }}
]
```

**Count UNIQUE values BY dimension (e.g., unique employees per warehouse):**
```json
[
  {"$match": {"role": "Picker"}},
  {"$group": {
    "_id": "$warehouse_id",
    "unique_employees": {"$addToSet": "$employee_id"}
  }},
  {"$project": {
    "_id": 0,
    "warehouse_id": "$_id",
    "unique_employee_count": {"$size": "$unique_employees"}
  }},
  {"$sort": {"warehouse_id": 1}}
]
```

**Find item with HIGHEST/LOWEST AVERAGE of a metric (CRITICAL PATTERN):**
Example: "part number for highest average discrepancy quantity"
```json
[
  {"$group": {
    "_id": "$part_number",
    "avg_discrepancy": {"$avg": "$discrepancy_qty"}
  }},
  {"$sort": {"avg_discrepancy": -1}},
  {"$limit": 1},
  {"$project": {
    "_id": 0,
    "part_number": "$_id",
    "avg_discrepancy": 1
  }}
]
```

Example: "supplier with lowest average lead time"
```json
[
  {"$group": {
    "_id": "$supplier_name",
    "avg_lead_time": {"$avg": "$inbound_lead_time_days"}
  }},
  {"$sort": {"avg_lead_time": 1}},
  {"$limit": 1},
  {"$project": {
    "_id": 0,
    "supplier_name": "$_id",
    "avg_lead_time": 1
  }}
]
```

🚨 CRITICAL: When user asks for "highest/lowest AVERAGE", you MUST:
1. Group by the dimension (e.g., part_number, supplier_name)
2. Calculate the average using $avg
3. Sort by that average (descending for highest, ascending for lowest)
4. Limit to 1 (or N if "top N" specified)
5. Project both the dimension and the average value

**Categorical filter queries (CRITICAL - DO NOT treat as dates):**
Example: "total orders processed during the Day shift"
```json
[
  {"$match": {"shift": "Day"}},
  {"$group": {"_id": null, "total_orders": {"$sum": "$orders_processed"}}},
  {"$project": {"_id": 0, "total_orders": 1}}
]
```

Example: "average picks for Night shift employees"
```json
[
  {"$match": {"shift": "Night"}},
  {"$group": {"_id": null, "avg_picks": {"$avg": "$picks"}}},
  {"$project": {"_id": 0, "avg_picks": 1}}
]
```

Example: "count employees by role"
```json
[
  {"$group": {"_id": "$role", "count": {"$sum": 1}}},
  {"$project": {"_id": 0, "role": "$_id", "count": 1}},
  {"$sort": {"count": -1}}
]
```

🚨 CRITICAL SHIFT HANDLING:
- "Day shift", "day shift", "Day" (in shift context) → {"shift": "Day"}
- "Night shift", "night shift", "Night" (in shift context) → {"shift": "Night"}
- DO NOT treat shift values as dates!
- Shift is a STRING field with exact values "Day" or "Night"

⚠️ OUTPUT FORMAT:
Just the JSON array - nothing else. No markdown, no explanations, no text.
"""

# ── Human Prompt Template ─────────────────────────────────────────────────────
_QUERY_GENERATOR_HUMAN = """User Question: {user_query}

Target Collection: {collection}

📋 COMPLETE SCHEMA for {collection}:
{schema_json}

📊 ALL COLUMNS WITH TYPES AND VALUES:
{columns_json}

🚨 IMPORTANT - TYPO CORRECTION:
For fields with "values" listed, those are the ONLY valid values in the database.
If the user's text is similar to a value, use the EXACT valid value from the list.
Example: "Cutomer Z" → use "Customer Z" from values: ["Customer X", "Customer Y", "Customer Z"]

🎯 Generate the MongoDB aggregation pipeline to answer this question.
Output ONLY the JSON array, nothing else."""


@traceable(name="generate_mongodb_pipeline", tags=["llm", "query_generation"])
def generate_mongodb_pipeline_with_llm(
    user_query: str,
    collection: str,
    base_match: Optional[dict] = None,
) -> dict[str, Any]:
    """Generate MongoDB pipeline using LLM with full schema knowledge.
    
    Args:
        user_query: Natural language question
        collection: Target collection name
        base_match: Optional base filters (warehouse_id, dates, etc.)
        
    Returns:
        dict with:
            pipeline: MongoDB aggregation pipeline
            raw_llm_output: Raw LLM response for debugging
            success: Boolean indicating if generation succeeded
            error: Error message if failed
    """
    try:
        # Get complete schema for this collection
        schema = get_schema(collection)
        if not schema:
            return {
                "pipeline": [],
                "success": False,
                "error": f"Schema not found for collection: {collection}",
            }
        
        # Get column metadata for this collection
        columns_for_collection = {}
        for col_name, col_info in COLUMN_TO_COLLECTION_MAP.items():
            col_collections = col_info.get("collections", [col_info.get("collection")])
            if collection in col_collections:
                columns_for_collection[col_name] = {
                    "type": col_info.get("type"),
                    "values": col_info.get("values", []),
                    "description": col_info.get("description", ""),
                }
        
        # Prepare schema JSON
        schema_json = json.dumps(schema, indent=2, default=str)
        columns_json = json.dumps(columns_for_collection, indent=2, default=str)
        
        # Build prompt
        system_msg = SystemMessage(content=_QUERY_GENERATOR_SYSTEM)
        human_msg = HumanMessage(content=_QUERY_GENERATOR_HUMAN.format(
            user_query=user_query,
            collection=collection,
            schema_json=schema_json,
            columns_json=columns_json,
        ))
        
        # Call LLM
        llm = _get_llm()
        logger.info(f"Calling LLM to generate MongoDB pipeline for: {user_query}")
        response = llm.invoke([system_msg, human_msg])
        raw_output = response.content if hasattr(response, "content") else str(response)
        
        logger.debug(f"LLM raw output: {raw_output}")
        
        # Parse JSON response
        # LLM might wrap in markdown code fences, strip those
        output = raw_output.strip()
        if output.startswith("```"):
            # Remove code fences
            lines = output.split("\n")
            output = "\n".join(lines[1:-1]) if len(lines) > 2 else output
            output = output.replace("```json", "").replace("```", "").strip()
        
        # Parse the JSON pipeline
        pipeline = json.loads(output)
        
        # Validate it's a list
        if not isinstance(pipeline, list):
            return {
                "pipeline": [],
                "raw_llm_output": raw_output,
                "success": False,
                "error": f"LLM output is not a list: {type(pipeline)}",
            }
        
        # Convert {"$date": "..."} to datetime objects
        pipeline = _convert_dates_in_pipeline(pipeline)
        
        # Inject base_match if provided (prepend to pipeline)
        if base_match:
            # Check if pipeline starts with $match, merge if so
            if pipeline and "$match" in pipeline[0]:
                # Merge base_match with existing match
                pipeline[0]["$match"].update(base_match)
            else:
                # Prepend base_match
                pipeline.insert(0, {"$match": base_match})
        
        logger.info(f"Successfully generated pipeline with {len(pipeline)} stages")
        return {
            "pipeline": pipeline,
            "raw_llm_output": raw_output,
            "success": True,
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM output as JSON: {e}")
        logger.error(f"Raw LLM output was:\n{raw_output if 'raw_output' in locals() else 'N/A'}")
        logger.error(f"After stripping code fences:\n{output if 'output' in locals() else 'N/A'}")
        return {
            "pipeline": [],
            "raw_llm_output": raw_output if 'raw_output' in locals() else "",
            "success": False,
            "error": f"Invalid JSON from LLM: {str(e)}",
        }
    except Exception as e:
        logger.error(f"LLM query generation failed: {e}")
        return {
            "pipeline": [],
            "success": False,
            "error": str(e),
        }


@traceable(name="execute_llm_query", tags=["mongodb", "query_execution"])
def execute_llm_query(
    user_query: str,
    collection_name: str,
    collection_obj: Collection,
    base_match: Optional[dict] = None,
) -> dict[str, Any]:
    """Execute a query using LLM-generated MongoDB pipeline.
    
    Args:
        user_query: Natural language question
        collection_name: Collection name
        collection_obj: MongoDB collection object
        base_match: Optional base filters
        
    Returns:
        dict with:
            results: Query results
            pipeline: MongoDB pipeline used
            count: Number of results
            llm_output: Raw LLM output
            error: Error message if failed
    """
    # Generate pipeline with LLM
    gen_result = generate_mongodb_pipeline_with_llm(user_query, collection_name, base_match)
    
    if not gen_result["success"]:
        return {
            "results": [],
            "pipeline": [],
            "count": 0,
            "error": gen_result["error"],
            "llm_output": gen_result.get("raw_llm_output", ""),
        }
    
    pipeline = gen_result["pipeline"]
    
    try:
        # Execute pipeline
        results = list(collection_obj.aggregate(pipeline, allowDiskUse=True))
        
        # Strip _id fields to prevent ObjectId serialization errors
        results = _strip_objectids(results)
        
        logger.info(f"Pipeline returned {len(results)} results")
        
        return {
            "results": results,
            "pipeline": pipeline,
            "count": len(results),
            "llm_output": gen_result.get("raw_llm_output", ""),
        }
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        logger.error(f"Pipeline was: {pipeline}")
        return {
            "results": [],
            "pipeline": pipeline,
            "count": 0,
            "error": f"Pipeline execution error: {str(e)}",
            "llm_output": gen_result.get("raw_llm_output", ""),
        }
