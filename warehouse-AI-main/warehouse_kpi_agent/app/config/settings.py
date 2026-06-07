"""
Application settings loaded from .env file.
Also adds parent directory to sys.path so kpi_registry.py and
collections_schema.py (located in Warehouse_Mgmt_Assignment/) are importable.
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
# warehouse_kpi_agent/app/config/ -> parent.parent.parent = warehouse_kpi_agent/
AGENT_DIR: Path = Path(__file__).resolve().parent.parent.parent
# warehouse_kpi_agent/ -> parent = Warehouse_Mgmt_Assignment/
WORKSPACE_DIR: Path = AGENT_DIR.parent

# Make kpi_registry.py and collections_schema.py importable
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv(AGENT_DIR / ".env")

# ── Settings ──────────────────────────────────────────────────────────────────
MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB: str = os.getenv("MONGODB_DB", "sales_warehouse_db")

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:7b")

# ── LangSmith (Observability) ──────────────────────────────────────────────────
LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "warehouse-kpi-agent")
LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1", "yes")

# Initialize LangSmith if enabled
if LANGSMITH_TRACING and LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    logging.info(f"LangSmith tracing enabled for project: {LANGSMITH_PROJECT}")
else:
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

DATA_DIR: Path = WORKSPACE_DIR   # CSVs live here
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── CSV → Collection mapping ───────────────────────────────────────────────────
COLLECTION_FILE_MAP: dict = {
    "inbound_parts":         "inbound_parts.csv",
    "outbound_parts":        "outbound_parts.csv",
    "inventory_snapshot":    "inventry_snapshot.csv",   # intentional typo in filename
    "warehouse_productivity":"warehouse_productivity.csv",
    "employee_productivity": "employee_productivity.csv",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
