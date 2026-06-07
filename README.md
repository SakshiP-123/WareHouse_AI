🏭 Warehouse KPI Agent
AI-powered warehouse analytics agent using LangGraph, Ollama (qwen2.5:7b), and MongoDB

A sophisticated warehouse KPI analytics system that provides natural language querying of warehouse operations data across 5 key domains: Inbound, Outbound, Inventory, Warehouse Productivity, and Employee Productivity.

📋 Table of Contents
Overview
Architecture
Query Processing Flow
Features
Data Collections
KPI Registry
Setup
Usage
API Documentation
Project Structure
🎯 Overview
The Warehouse KPI Agent is a schema-driven, keyword-aware analytics system that:

✅ Answers natural language questions about warehouse operations
✅ Computes 16+ registered KPIs across 5 collections
✅ Provides analytical queries with intelligent routing
✅ Exports KPI reports to Excel
✅ Offers both CLI, API (FastAPI), and UI (Streamlit) interfaces
✅ Uses zero hardcoded logic - all routing is schema and keyword-driven
Key Capabilities
"How many warehouses do we have?"              → Analytical Single
"Fill rate for WH-02 from Dec to Jan"         → Registered KPI
"Show me all KPIs for WH-01"                   → Registered KPI (All Collections)
"Supplier delays and stockout levels"         → Analytical Parallel (Multi-collection)
"Employee E-1033 performance last month"      → Analytical Single (Employee-specific)
