# 🛠️ Warehouse KPI Agent - Developer Guide

**Complete guide for developers to understand, setup, and contribute to the Warehouse KPI Agent**

---

## 📚 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Development Setup](#development-setup)
5. [Development Workflow](#development-workflow)
6. [Testing Guide](#testing-guide)
7. [Contributing](#contributing)
8. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

### System Architecture

The Warehouse KPI Agent is built as a **stateful AI agent** using LangGraph for orchestration, Ollama for local LLM inference, and MongoDB for data storage.

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                          │
│                                                                 │
│  ┌──────────┐      ┌──────────┐      ┌──────────────┐         │
│  │   CLI    │      │ FastAPI  │      │  Streamlit   │         │
│  │ Terminal │      │   REST   │      │      UI      │         │
│  └──────────┘      └──────────┘      └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LANGGRAPH STATE MACHINE                      │
│                                                                 │
│  ┌────────────────┐                                            │
│  │ classify_intent│ ──► LLM Call #1 (qwen2.5:7b)              │
│  └────────┬───────┘                                            │
│           │                                                     │
│           ├──► registered_kpi_handler                          │
│           ├──► single_query_handler                            │
│           ├──► parallel_query_handler                          │
│           └──► format_response ──► LLM Call #2                 │
│                                                                 │
│  Memory: SQLite Checkpointing (Conversation History)           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        TOOLS LAYER                              │
│                                                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │  Inbound   │  │  Outbound  │  │ Inventory  │               │
│  │   Tool     │  │    Tool    │  │    Tool    │               │
│  └────────────┘  └────────────┘  └────────────┘               │
│                                                                 │
│  ┌────────────────┐  ┌───────────────────────┐                │
│  │   Warehouse    │  │     Employee          │                │
│  │ Productivity   │  │   Productivity        │                │
│  └────────────────┘  └───────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────┐          │
│  │           MongoDB (warehouse_data)               │          │
│  │                                                  │          │
│  │  • inbound_parts         (3,000 docs)           │          │
│  │  • outbound_parts        (3,000 docs)           │          │
│  │  • inventory_snapshot    (3,000 docs)           │          │
│  │  • warehouse_productivity (3,000 docs)          │          │
│  │  • employee_productivity (3,000 docs)           │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

#### 1. **Schema-Driven Design**

All data schemas are defined in a **single source of truth**: `collections_schema.py`

```python
# Single schema definition
COLLECTIONS_SCHEMA = {
    "warehouse_productivity": {
        "columns": {
            "warehouse_id": "string",
            "date": "datetime",
            "shift": "string",
            ...
        },
        "business_metrics": {
            "lines_per_labor_hour": "SUM(lines_picked) / SUM(labor_hours)"
        }
    }
}
```

**Benefits**:
- ✅ No hardcoded logic scattered across codebase
- ✅ Self-documenting - LLM sees actual schema
- ✅ Single point of change for schema updates
- ✅ Type-safe queries and validations

#### 2. **Keyword-Based Routing**

The system uses **80+ domain-specific keywords** per collection to ensure correct routing even when the LLM misclassifies intent.

**Six-Level Guardrail System**:
1. **Priority**: Employee ID detection (E-XXXX pattern) → Force analytical_single
2. **Critical**: Empty collections → Add from keywords
3. **Upgrade**: out_of_scope + keywords → Analytical query
4. **Multi-detect**: Single but 2+ keywords → Parallel query
5. **Enhancement**: Merge LLM + keyword collections
6. **KPI-All**: Ensure all collections for scope=all

#### 3. **Three-Stage LLM Pipeline**

**Stage 1: Intent Classification**
- LLM: `qwen2.5:7b` in JSON mode
- Purpose: Classify intent, extract entities (warehouse_id, dates, KPIs)
- Guardrails: Keyword validation and correction
- Output: Intent + target collections + entities

**Stage 2: Query Generation (Optional - Analytical queries only)**
- LLM: `qwen2.5:7b` in text mode
- Purpose: Generate MongoDB aggregation pipeline from natural language
- Context: Schema details + user query
- Output: MongoDB aggregation pipeline JSON
- When: Only for analytical_single and analytical_parallel intents

**Stage 3: Response Formatting**
- LLM: `qwen2.5:7b` in text mode
- Purpose: Convert DB results to human-readable markdown
- Context: Schema details + query + actual data
- Output: Formatted markdown response

**Why Three Stages?**
- Separation of concerns: routing → query generation → formatting
- LLM #1 can fail safely (keyword guardrails)
- LLM #2 generates precise MongoDB queries (optional, only for complex analytics)
- LLM #3 sees actual data (not hallucinated)

#### 4. **Stateful Conversations**

Uses **SQLite checkpointing** via LangGraph to maintain conversation history:
- Thread-based conversations
- Full state persistence
- Resume interrupted conversations
- Context-aware follow-up queries

---

## 💻 Technology Stack

### Core Framework

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **Python** | 3.12+ | Primary language | Type hints, async support, rich ecosystem |
| **LangGraph** | 0.2.55+ | AI agent orchestration | Stateful workflow, graph-based routing, built-in checkpointing |
| **LangChain** | 0.3.0+ | LLM framework | Tool abstraction, prompt management, Ollama integration |

### LLM & AI

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **Ollama** | Latest | Local LLM runtime | Privacy, no API costs, offline-capable |
| **qwen2.5:7b** | 7B params | LLM model | Best balance of performance/speed, good JSON mode |
| **langchain-ollama** | 0.2.0+ | Ollama connector | Native LangChain integration |

**Why Ollama + qwen2.5:7b?**
- ✅ Runs locally (no cloud dependency)
- ✅ No API costs
- ✅ Data privacy (warehouse data stays local)
- ✅ Fast inference on consumer hardware
- ✅ Excellent JSON mode for structured outputs

### Data & Storage

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **MongoDB** | 7.0+ | Document database | Flexible schema, native Python support, aggregation pipelines |
| **PyMongo** | 4.8.0+ | MongoDB driver | Official driver, connection pooling |
| **Pandas** | 2.1.0+ | Data manipulation | CSV processing, data transformations |
| **SQLite** | Built-in | Conversation memory | Zero-config, file-based, perfect for checkpoints |

**Why MongoDB?**
- ✅ Document model fits warehouse data (nested fields, varied structures)
- ✅ Powerful aggregation for KPI calculations
- ✅ Easy to add new collections without migrations
- ✅ Great Python support with PyMongo

### APIs & UI

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **FastAPI** | 0.111.0+ | REST API server | Fast, automatic OpenAPI docs, async support |
| **Uvicorn** | 0.29.0+ | ASGI server | High performance, production-ready |
| **Streamlit** | 1.32.0+ | Web UI | Rapid prototyping, built for data apps |

### Export & Formatting

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **openpyxl** | 3.1.0+ | Excel generation | Multi-sheet workbooks, formatting |
| **Rich** | 13.7.0+ | Terminal output | Colored output, tables, progress bars |
| **Pydantic** | 2.5.0+ | Data validation | Type validation, settings management |

### Development Tools

| Technology | Version | Purpose | Why We Chose It |
|------------|---------|---------|-----------------|
| **python-dotenv** | 1.0.1+ | Environment config | Standard .env file support |
| **Docker** | Latest | MongoDB container | Consistent dev environment |
| **Makefile** | Standard | Task automation | Cross-platform developer commands |

---

## 📁 Project Structure

### Root Level

```
warehouse_AI/
├── collections_schema.py      # ⭐ Single source of truth for all schemas
├── kpi_registry.py            # ⭐ All 16 registered KPI definitions
├── output/                    # Generated exports (Excel/JSON/HTML)
│   └── <timestamp>/           # Timestamped folders per export
├── README.md                  # User documentation
├── DEVELOPER_GUIDE.md         # This file - developer documentation
└── warehouse_kpi_agent/       # Main application package
```

**Why this structure?**
- `collections_schema.py` and `kpi_registry.py` at root = project-level configurations
- Easy to find and modify central definitions
- `output/` separate from code for clean .gitignore

### Main Application Package

```
warehouse_kpi_agent/
├── .env                       # Environment variables (local, git-ignored)
├── langgraph.json             # LangGraph server configuration
├── Makefile                   # Developer commands
├── requirements.txt           # Python dependencies
├── SCHEMA_ARCHITECTURE.md     # Detailed schema documentation
│
├── app/                       # Main application code
│   ├── __init__.py
│   ├── __main__.py            # CLI entry point (python -m app)
│   ├── main.py                # CLI application logic
│   ├── server.py              # FastAPI REST API
│   ├── streamlit_app.py       # Streamlit web UI
│   │
│   ├── config/                # ⚙️ Configuration layer
│   ├── db/                    # 📊 Database layer
│   ├── graph/                 # 🧠 LangGraph state machine
│   ├── services/              # 🔧 Business logic services
│   └── tools/                 # 🛠️ Collection-specific query tools
│
├── data_ingestion/            # CSV → MongoDB data pipeline
│   ├── raw_data/              # Original CSV files
│   └── pruned/                # Cleaned CSV files
│
└── tests/                     # Test suite
    ├── run_tests.py           # Test runner
    ├── test_intent_classification.py
    ├── test_kpi_calculations.py
    └── test_graph_flow.py
```

### Deep Dive: `app/` Directory

#### `app/config/` - Configuration Layer

```
config/
├── __init__.py
├── settings.py           # Environment variables, app settings
├── schema_registry.py    # Schema access layer (reads collections_schema.py)
└── column_metadata.py    # Column-level metadata utilities
```

**Purpose**: Centralized configuration management
- `settings.py`: Loads `.env`, provides `Settings` object
- `schema_registry.py`: Provides `get_schema()`, `get_columns()` functions
- All config accessed through this layer (no direct env variable reads)

#### `app/db/` - Database Layer

```
db/
├── __init__.py
└── data_loader.py        # CSV → MongoDB ingestion logic
```

**Purpose**: Data persistence layer
- MongoDB connection management
- CSV data loading and validation
- Collection initialization

#### `app/graph/` - LangGraph State Machine

```
graph/
├── __init__.py
├── state.py              # AgentState TypedDict definition
├── graph_builder.py      # Graph construction and compilation
├── conditions.py         # Routing logic (conditional edges)
│
└── nodes/                # Individual graph nodes
    ├── intent_classifier.py      # LLM Call #1 + Guardrails
    ├── registered_kpi.py         # KPI computation handler
    ├── single_query_handler.py   # Single-collection query handler
    ├── analytical_parallel.py    # Multi-collection query handler
    ├── join_results.py           # Multi-collection result aggregation
    ├── format_response.py        # LLM Call #2 (response formatting)
    └── query_tools.py            # Tool dispatch layer
```

**Purpose**: Core AI agent logic
- **state.py**: Defines what data flows through the graph
- **graph_builder.py**: Wires nodes together, compiles with checkpointing
- **conditions.py**: Routing decisions (registered_kpi / single / parallel)
- **nodes/**: Each file = one node in the graph

**Graph Flow**:
```
START → classify_intent → route_after_classification
                            ├─► registered_kpi_handler → join_results ──┐
                            ├─► single_query_handler ──────────────────┤
                            ├─► parallel_query_handler → join_results ─┤
                            └─► format_response ────────────────────────┘
                                                                         │
                                                            format_response → END
```

#### `app/services/` - Business Logic Services

```
services/
├── __init__.py
├── intent_classifier.py   # Intent classification service (6-level guardrails)
└── excel_exporter.py      # Multi-format export (Excel/JSON/HTML)
```

**Purpose**: Reusable business logic
- `intent_classifier.py`: LLM call + keyword matching + 6-level guardrails
- `excel_exporter.py`: Triple export generation (Excel, JSON, HTML)

**Why separate from nodes?**
- Services are reusable (API can call directly)
- Easier to test in isolation
- Nodes are workflow-specific, services are business-specific

#### `app/tools/` - Collection Query Tools

```
tools/
├── __init__.py
├── base.py                          # Shared MongoDB utilities
├── inbound_tool.py                  # Inbound KPI queries
├── outbound_tool.py                 # Outbound KPI queries
├── inventory_tool.py                # Inventory KPI queries
├── warehouse_productivity_tool.py   # Warehouse KPI queries
├── employee_productivity_tool.py    # Employee KPI queries
└── llm_query_generator.py           # (Future) LLM-based query generation
```

**Purpose**: Collection-specific data access
- Each tool corresponds to one MongoDB collection
- Registered KPI functions: `compute_registered_kpis()`
- Analytical query functions: `compute_general_stats()`, `query_by_llm()`
- All tools use `base.py` for MongoDB connection

**Tool Pattern**:
```python
# Each tool provides:
def compute_registered_kpis(
    kpi_names: Optional[list[str]] = None,
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Compute specific or all registered KPIs."""
    ...
```

#### `data_ingestion/` - Data Pipeline

```
data_ingestion/
├── __init__.py
├── __main__.py          # CLI: python -m data_ingestion
├── pipeline.py          # Data loading logic
│
├── raw_data/            # Original CSV files (as received)
│   ├── inbound_parts_with_warehouse.csv
│   ├── outbound_parts_with_warehouse.csv
│   ├── inventory_snapshot.csv
│   ├── warehouse_productivity.csv
│   └── employee_productivity.csv
│
└── pruned/              # Cleaned CSV files (ready for MongoDB)
    └── (same files)
```

**Purpose**: Data ingestion and management
- Load CSV files into MongoDB
- Data validation and cleaning
- Runnable as module: `python -m data_ingestion`

#### `tests/` - Test Suite

```
tests/
├── __init__.py
├── README.md                       # Test documentation
├── run_tests.py                    # Test runner with categories
├── test_intent_classification.py   # Intent routing tests (5 tests)
├── test_kpi_calculations.py        # KPI computation tests (5 tests)
└── test_graph_flow.py              # End-to-end tests (6 tests)
```

**Purpose**: Automated testing
- **16 total tests** across 3 categories
- Run via: `make test` or `python tests/run_tests.py`
- Each test file can run independently

---

## 🚀 Development Setup

### Prerequisites

Before you begin, ensure you have:

- **Python 3.12+** installed
- **Docker Desktop** (for MongoDB)
- **Ollama** with `qwen2.5:7b` model
- **Git** for version control

### Step-by-Step Setup

#### 1. **Clone the Repository**

```bash
git clone -b dev 
cd Warehouse-AI/warehouse_kpi_agent
```

#### 2. **Create Virtual Environment**

```bash
# Create venv
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows PowerShell)
venv\Scripts\Activate.ps1
```

#### 3. **Install Dependencies**

```bash
# Using Makefile (recommended)
make install

# Or manually
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected output**:
```
Successfully installed langgraph-0.2.55 langchain-0.3.0 ...
Dependencies installed.
```

#### 4. **Configure Environment Variables**

Create `.env` file in `warehouse_kpi_agent/` directory:

```bash
cat > .env << 'EOF'
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=warehouse_data

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5:7b

# Logging
LOG_LEVEL=INFO

# LangSmith (Optional - for tracing)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=your_key_here
EOF
```

#### 5. **Start MongoDB**

```bash
# Using Makefile
make backend

# Or manually with Docker
docker run -d --name warehouse-mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_DATABASE=warehouse_data \
  mongo:7.0
```

**Verify MongoDB is running**:
```bash
docker ps | grep warehouse-mongo
# Should show CONTAINER running on port 27017
```

#### 6. **Install and Start Ollama**

```bash
# Install Ollama (if not already installed)
# Visit: https://ollama.ai/download

# Pull qwen2.5:7b model
ollama pull qwen2.5:7b

# Verify Ollama is running
ollama list
# Should show qwen2.5:7b in the list
```

**Test Ollama**:
```bash
curl http://localhost:11434/api/tags
# Should return JSON with model list
```

#### 7. **Load Data into MongoDB**

```bash
# Using Makefile
make load-data

# Or manually
python -c "from app.db.data_loader import load_all; load_all(force_reload=True)"
```

**Expected output**:
```
Loading inbound_parts... ✓ 3000 documents
Loading outbound_parts... ✓ 3000 documents
Loading inventory_snapshot... ✓ 3000 documents
Loading warehouse_productivity... ✓ 3000 documents
Loading employee_productivity... ✓ 3000 documents
Data loaded into MongoDB.
```

**Verify data loaded**:
```bash
python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
db = client['warehouse_data']
for col in db.list_collection_names():
    print(f'{col}: {db[col].count_documents({})} docs')
"
```

#### 8. **Run Tests**

```bash
# Run all tests
make test

# Or manually
python tests/run_tests.py
```

**Expected output**:
```
✅ Intent Classification Tests: ALL 5 PASSED
✅ KPI Calculation Tests: ALL 5 PASSED
✅ Graph Flow Tests: ALL 6 PASSED

Total: 16/16 tests passed
```

#### 9. **Start the Application**

**Option A: CLI Interface**
```bash
make run

# Or manually
python -m app.main
```

**Option B: FastAPI Server**
```bash
make api

# Visit: http://localhost:8000/docs (Swagger UI)
```

**Option C: Streamlit UI**
```bash
make ui

# Visit: http://localhost:8501
```

### Verify Setup

Test with a simple query:

```bash
# In CLI
> How many warehouses do we have?
```

**Expected response**:
```markdown
We have **3 warehouses**: WH-01, WH-02, and WH-03.
```

---

## 🔄 Development Workflow

### Daily Development

```bash
# 1. Activate environment
source venv/bin/activate  # or venv\Scripts\Activate.ps1 on Windows

# 2. Start MongoDB (if not running)
make backend

# 3. Run application
make run    # CLI
make api    # FastAPI server
make ui     # Streamlit UI

# 4. Make changes...

# 5. Run tests
make test

# 6. Clean up
make backend-stop
deactivate
```

### Making Changes

#### Adding a New KPI

**1. Update `kpi_registry.py`**:
```python
"new_kpi_name": {
    "area": "outbound",
    "name": "New KPI Display Name",
    "description": "What this KPI measures",
    "formula": "SUM(field_a) / SUM(field_b)",
    "tables": ["outbound_parts"],
    "type": "metric",
    "owner": "Team Name"
}
```

**2. Implement in tool (e.g., `outbound_tool.py`)**:
```python
def _compute_new_kpi(match: dict) -> dict:
    """Compute new KPI."""
    pipeline = [
        {"$match": match},
        # ... aggregation logic
    ]
    return {
        "kpi": "new_kpi_name",
        "name": "New KPI Display Name",
        "value": result,
        "unit": "%"
    }

# Add to _KPI_FN mapping
_KPI_FN = {
    ...
    "new_kpi_name": _compute_new_kpi,
}
```

**3. Add to ALL_KPIS list**:
```python
ALL_KPIS = [
    ...,
    "new_kpi_name"
]
```

**4. Test**:
```bash
python -c "
from app.tools.outbound_tool import compute_registered_kpis
result = compute_registered_kpis(kpi_names=['new_kpi_name'])
print(result)
"
```

#### Adding a New Collection

**1. Add schema to `collections_schema.py`**:
```python
"new_collection": {
    "columns": {
        "field_1": "string",
        "field_2": "integer",
        # ...
    },
    "business_metrics": {
        "metric_name": "formula"
    },
    "description": "What this collection stores"
}
```

**2. Create tool file `app/tools/new_collection_tool.py`**:
```python
from app.tools.base import get_collection

COLLECTION = "new_collection"
DATE_FIELD = "field_date"

def compute_registered_kpis(
    kpi_names: Optional[list[str]] = None,
    warehouse_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    # Implementation
    ...
```

**3. Add keywords to `intent_classifier.py`**:
```python
DOMAIN_KEYWORDS = {
    ...
    "new_collection": [
        "keyword1", "keyword2", "keyword3",
        # 80+ domain-specific keywords
    ]
}
```

**4. Update `query_tools.py`** to import new tool:
```python
from app.tools import new_collection_tool

_TOOL_MAP = {
    ...
    "new_collection": new_collection_tool,
}
```

**5. Load data**:
```bash
# Add CSV to data_ingestion/raw_data/
# Update pipeline.py to include new collection
make load-data
```

### Debugging

#### Enable Debug Logging

Edit `.env`:
```bash
LOG_LEVEL=DEBUG
```

#### LangSmith Tracing (Optional)

For detailed LLM tracing:

```bash
# Add to .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=warehouse-kpi-agent
```

Visit [LangSmith](https://smith.langchain.com/) to view traces.

#### Common Debug Commands

```python
# Test MongoDB connection
python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
print(client.server_info())
"

# Test Ollama
python -c "
from langchain_ollama import ChatOllama
llm = ChatOllama(model='qwen2.5:7b')
print(llm.invoke('Hello'))
"

# Test specific tool
python -c "
from app.tools.outbound_tool import compute_registered_kpis
print(compute_registered_kpis(kpi_names=['fill_rate']))
"

# Test graph
python -c "
from app.graph.graph_builder import graph
result = graph.invoke({'query': 'How many warehouses?'})
print(result['formatted_response'])
"
```

---

## 🧪 Testing Guide

### Test Structure

```
tests/
├── test_intent_classification.py   # LLM routing and keyword guardrails
├── test_kpi_calculations.py        # KPI computation accuracy
└── test_graph_flow.py              # End-to-end graph execution
```

### Running Tests

```bash
# All tests
make test

# Specific category
python tests/run_tests.py intent      # Intent classification only
python tests/run_tests.py kpi         # KPI calculations only
python tests/run_tests.py graph       # Graph flow only

# Single test file
python tests/test_intent_classification.py
```

### Writing Tests

**Example: Testing a new KPI**

```python
# In test_kpi_calculations.py

def test_new_kpi():
    """Test new KPI calculation."""
    from app.tools.outbound_tool import compute_registered_kpis
    
    results = compute_registered_kpis(
        kpi_names=["new_kpi_name"],
        warehouse_id="WH-01",
        start_date="2025-01-01",
        end_date="2025-01-31"
    )
    
    # Verify structure
    assert len(results) > 0, "Should return results"
    
    # Find specific KPI
    kpi_result = next((r for r in results if r.get("kpi") == "new_kpi_name"), None)
    assert kpi_result is not None, "Should include new_kpi_name"
    
    # Verify required fields
    assert "value" in kpi_result
    assert "name" in kpi_result
    assert "collection" in kpi_result
    
    print(f"✅ New KPI test passed: {kpi_result['name']} = {kpi_result['value']}")
```

### Test Best Practices

- ✅ Test with real data (not mocks)
- ✅ Verify data structure, not exact values (data may change)
- ✅ Test edge cases (no data, invalid dates)
- ✅ Keep tests fast (< 5 seconds each)
- ✅ Use descriptive assertions

---

## 🤝 Contributing

### Code Style

- Follow **PEP 8** style guide
- Use **type hints** for all functions
- Write **docstrings** for public functions
- Keep functions **focused and small** (< 50 lines)

### Commit Messages

Follow conventional commits:

```
feat: add new inventory turnover KPI
fix: correct fill rate calculation for multi-warehouse
docs: update developer guide with test examples
test: add tests for parallel query handler
refactor: extract schema loading to separate module
```

### Pull Request Process

1. Create feature branch: `git checkout -b feature/your-feature-name`
2. Make changes and test: `make test`
3. Update documentation if needed
4. Commit with descriptive messages
5. Push and create PR

### Adding Documentation

- Update `README.md` for user-facing changes
- Update `DEVELOPER_GUIDE.md` for architecture/setup changes
- Add docstrings for new functions
- Update `SCHEMA_ARCHITECTURE.md` for schema changes

---

## 🔧 Troubleshooting

### MongoDB Connection Failed

```
ERROR: pymongo.errors.ServerSelectionTimeoutError
```

**Solutions**:
```bash
# Check if MongoDB is running
docker ps | grep warehouse-mongo

# Restart MongoDB
make backend-stop
make backend

# Verify connection
python -c "from pymongo import MongoClient; print(MongoClient('mongodb://localhost:27017/').server_info())"
```

### Ollama Not Responding

```
ERROR: Connection refused to http://localhost:11434
```

**Solutions**:
```bash
# Check Ollama status
ollama list

# Restart Ollama
# macOS: killall ollama && ollama serve
# Linux: systemctl restart ollama

# Test connection
curl http://localhost:11434/api/tags
```

### LLM Returns Empty Response

**Cause**: Model not loaded or insufficient memory

**Solutions**:
```bash
# Verify model is pulled
ollama pull qwen2.5:7b

# Test model directly
ollama run qwen2.5:7b "test"

# Check system memory (need ~8GB free)
```

### Tests Failing

```
AssertionError: Should return results
```

**Solutions**:
```bash
# Ensure data is loaded
make load-data

# Check MongoDB has data
python -c "
from pymongo import MongoClient
db = MongoClient('mongodb://localhost:27017/')['warehouse_data']
print(db['outbound_parts'].count_documents({}))
"

# Run tests with debug logging
LOG_LEVEL=DEBUG python tests/run_tests.py
```

### Import Errors

```
ModuleNotFoundError: No module named 'app'
```

**Solutions**:
```bash
# Ensure venv is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Run from correct directory
cd warehouse_kpi_agent
python -m app.main
```

### Excel Export Fails

```
ERROR: Permission denied writing to output/
```

**Solutions**:
```bash
# Create output directory
mkdir -p ../output

# Check permissions
ls -la ../output

# Run with sudo if needed (not recommended)
```

---

## 📚 Additional Resources

### Documentation

- [README.md](README.md) - User documentation
- [SCHEMA_ARCHITECTURE.md](warehouse_kpi_agent/SCHEMA_ARCHITECTURE.md) - Detailed schema docs
- [kpi_registry.py](kpi_registry.py) - KPI definitions
- [collections_schema.py](collections_schema.py) - Schema definitions

### External Resources

- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [Ollama Documentation](https://github.com/ollama/ollama)
- [MongoDB Aggregation Guide](https://www.mongodb.com/docs/manual/aggregation/)
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)

### Community

- GitHub Issues: Report bugs or request features
- Discussions: Ask questions or share ideas

---

## 📝 Quick Reference

### Essential Commands

```bash
make setup        # Initial setup
make backend      # Start MongoDB
make load-data    # Load warehouse data
make test         # Run tests
make run          # Start CLI
make api          # Start REST API
make ui           # Start Streamlit UI
make clean        # Clean environment
```

### Directory Quick Find

| What | Where |
|------|-------|
| Add new KPI | `kpi_registry.py` → `app/tools/<collection>_tool.py` |
| Modify schema | `collections_schema.py` |
| Change routing logic | `app/graph/conditions.py` |
| Update LLM prompts | `app/graph/nodes/intent_classifier.py`, `format_response.py` |
| Add keywords | `app/services/intent_classifier.py` → `DOMAIN_KEYWORDS` |
| Modify exports | `app/services/excel_exporter.py` |
| Test changes | `tests/test_*.py` |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB` | `warehouse_data` | Database name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `LLM_MODEL` | `qwen2.5:7b` | LLM model name |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |

---

**Ready to contribute? Start by running `make setup` and exploring the codebase!** 🚀
