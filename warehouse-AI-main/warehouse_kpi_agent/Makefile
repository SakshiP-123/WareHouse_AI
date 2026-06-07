##############################################################################
# Warehouse KPI Agent  ──  Makefile
# Cross-platform helper (Windows PowerShell / GNU Make)
##############################################################################

VENV        := venv
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
LANGGRAPH   := $(VENV)/bin/langgraph

.PHONY: help setup venv install load-data run run-fresh api ui dev backend backend-stop test clean lint

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Warehouse KPI Agent  -- Available commands:"
	@echo "-------------------------------------------------"
	@echo "make setup        -- Create venv + install packages"
	@echo "make venv         -- Create virtual environment only"
	@echo "make install      -- Install Python dependencies"
	@echo "make load-data    -- Load CSV data into MongoDB"
	@echo "make test         -- Run test suite"
	@echo "make run          -- Start interactive CLI agent"
	@echo "make api          -- Start FastAPI server on http://localhost:8000"
	@echo "make ui           -- Start Streamlit UI on http://localhost:8501"
	@echo "make dev          -- Start LangGraph dev server (Studio)"
	@echo "make backend      -- Start MongoDB via Docker"
	@echo "make backend-stop -- Stop MongoDB Docker container"
	@echo "make clean        -- Remove venv and cache files"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
setup: venv install
	@echo "Setup complete. Run 'make load-data' then 'make run'."

venv:
	python -m venv $(VENV)
	@echo "Virtual environment created at $(VENV)"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Dependencies installed."

# ── Data ──────────────────────────────────────────────────────────────────────
load-data:
	$(PY) -c "from app.db.data_loader import load_all; load_all(force_reload=True)"
	@echo "Data loaded into MongoDB."

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	$(PY) tests/run_tests.py

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	$(PY) -m app.main

run-fresh:
	$(PY) -m app.main --load-data

# ── FastAPI Server ───────────────────────────────────────────────────────────
api:
	$(PY) -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload

# ── Streamlit UI ─────────────────────────────────────────────────────────────
ui:
	$(PY) -m streamlit run app/streamlit_app.py --server.port 8501

# ── LangGraph Dev Server ──────────────────────────────────────────────────────
dev:
	$(LANGGRAPH) dev --config langgraph.json

# ── Backend (MongoDB via Docker) ──────────────────────────────────────────────
backend:
	docker run -d --name warehouse-mongo -p 27017:27017 \
		-e MONGO_INITDB_DATABASE=warehouse_kpi \
		mongo:7.0
	@echo "MongoDB started on port 27017"

backend-stop:
	docker stop warehouse-mongo
	docker rm warehouse-mongo

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleaned."
