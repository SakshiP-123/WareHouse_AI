"""Streamlit chat UI for the Warehouse KPI Agent — Attractive Dashboard Edition.

Usage:
    streamlit run app/streamlit_app.py --server.port 8501

Or via Makefile:
    make ui

Requires the FastAPI server to be running:
    make api
"""

import time
from pathlib import Path
from typing import Any, Optional

import requests
import streamlit as st

from app.config.session_manager import (
    create_session,
    list_sessions,
    get_session,
    update_session_access,
    rename_session,
    delete_session,
    update_session_first_query,
)
from app.config.memory import get_conversation_history

# ── Config ─────────────────────────────────────────────────────────────────────
_API_BASE    = "http://localhost:8000"
_QUERY_URL   = f"{_API_BASE}/query"
_HEALTH_URL  = f"{_API_BASE}/health"
_KPIS_URL    = f"{_API_BASE}/kpis"
_SYNC_URL    = f"{_API_BASE}/data/sync"
_TIMEOUT_SEC = 120

st.set_page_config(
    page_title="Warehouse KPI Agent",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base & Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Page Background ── */
.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1526 50%, #0a1420 100%);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1b2e 0%, #0a1520 100%);
    border-right: 1px solid rgba(0, 212, 255, 0.15);
}
[data-testid="stSidebar"] * {
    color: #c8d8e8 !important;
}

/* ── Header Banner ── */
.wh-banner {
    background: linear-gradient(135deg, #0d2137 0%, #0a2d4a 40%, #0d3a5c 100%);
    border: 1px solid rgba(0, 212, 255, 0.25);
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}
.wh-banner::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(0,212,255,0.06) 0%, transparent 70%);
    pointer-events: none;
}
.wh-banner h1 {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(90deg, #00d4ff, #00ff88, #00d4ff);
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: shimmer 3s linear infinite;
    margin: 0 0 6px 0;
}
@keyframes shimmer {
    0% { background-position: 0% center; }
    100% { background-position: 200% center; }
}
.wh-banner .subtitle {
    color: #7fb3cc;
    font-size: 0.9rem;
    font-weight: 400;
    margin: 0;
}
.wh-badge {
    display: inline-block;
    background: rgba(0, 212, 255, 0.12);
    border: 1px solid rgba(0, 212, 255, 0.3);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.72rem;
    font-weight: 500;
    color: #00d4ff;
    margin: 8px 4px 0 0;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Stat Cards Row ── */
.stat-row {
    display: flex;
    gap: 14px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}
.stat-card {
    flex: 1;
    min-width: 140px;
    background: linear-gradient(135deg, #0d2137 0%, #0a2040 100%);
    border: 1px solid rgba(0, 212, 255, 0.18);
    border-radius: 12px;
    padding: 16px 20px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
}
.stat-card:hover {
    transform: translateY(-2px);
    border-color: rgba(0, 212, 255, 0.45);
}
.stat-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #00d4ff, #00ff88);
}
.stat-card .s-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #5f9ab5;
    margin-bottom: 6px;
}
.stat-card .s-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #e4f4ff;
}
.stat-card .s-icon {
    position: absolute;
    top: 12px;
    right: 14px;
    font-size: 1.4rem;
    opacity: 0.35;
}

/* ── Intent Badge ── */
.intent-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-right: 6px;
}
.intent-analytical_single  { background: rgba(0,212,255,0.15); border: 1px solid rgba(0,212,255,0.4); color: #00d4ff; }
.intent-analytical_parallel{ background: rgba(130,80,255,0.15); border: 1px solid rgba(130,80,255,0.4); color: #a06eff; }
.intent-registered_kpi     { background: rgba(0,255,136,0.12); border: 1px solid rgba(0,255,136,0.4); color: #00ff88; }
.intent-out_of_scope       { background: rgba(255,80,80,0.12); border: 1px solid rgba(255,80,80,0.35); color: #ff6b6b; }

/* ── Execution Path ── */
.exec-path {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin: 8px 0 4px 0;
}
.exec-node {
    background: rgba(0, 212, 255, 0.08);
    border: 1px solid rgba(0, 212, 255, 0.22);
    border-radius: 6px;
    padding: 3px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    color: #7dcce0;
}
.exec-arrow {
    color: #2a6a80;
    font-size: 0.75rem;
}

/* ── Meta Strip ── */
.meta-strip {
    background: rgba(0, 212, 255, 0.04);
    border: 1px solid rgba(0, 212, 255, 0.12);
    border-radius: 10px;
    padding: 12px 16px;
    margin-top: 12px;
}
.meta-row {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: center;
}
.meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
}
.meta-lbl {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #4a8a9f;
}
.meta-val {
    font-size: 0.8rem;
    color: #9ed0e8;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Collection Pills ── */
.coll-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(0, 255, 136, 0.07);
    border: 1px solid rgba(0, 255, 136, 0.2);
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 0.69rem;
    color: #5dcc91;
    font-family: 'JetBrains Mono', monospace;
    margin: 3px 3px 3px 0;
}

/* ── Welcome Cards ── */
.welcome-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
    margin: 20px 0;
}
.welcome-card {
    background: linear-gradient(135deg, #0d1f33 0%, #0a1c30 100%);
    border: 1px solid rgba(0, 212, 255, 0.14);
    border-radius: 12px;
    padding: 20px;
    cursor: pointer;
    transition: all 0.25s;
}
.welcome-card:hover {
    border-color: rgba(0, 212, 255, 0.4);
    background: linear-gradient(135deg, #0d2540 0%, #0a2238 100%);
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0, 212, 255, 0.08);
}
.welcome-card .wc-icon { font-size: 1.6rem; margin-bottom: 8px; }
.welcome-card .wc-title { font-size: 0.85rem; font-weight: 600; color: #c0dded; margin-bottom: 4px; }
.welcome-card .wc-desc  { font-size: 0.73rem; color: #507a94; line-height: 1.4; }

/* ── Chat message overrides ── */
[data-testid="stChatMessageContent"] {
    background: rgba(13, 33, 55, 0.7) !important;
    border: 1px solid rgba(0, 212, 255, 0.1) !important;
    border-radius: 12px !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
    background: #0d1e33 !important;
    border: 1px solid rgba(0, 212, 255, 0.3) !important;
    border-radius: 12px !important;
    color: #e0f0ff !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: rgba(0, 212, 255, 0.6) !important;
    box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.08) !important;
}

/* ── Sidebar Section Headers ── */
.sb-section {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #3a7a9a !important;
    margin: 16px 0 8px 0;
    padding-bottom: 4px;
    border-bottom: 1px solid rgba(0, 212, 255, 0.1);
}

/* ── Sidebar buttons ── */
[data-testid="stSidebar"] .stButton button {
    background: rgba(13, 33, 55, 0.8) !important;
    border: 1px solid rgba(0, 212, 255, 0.2) !important;
    color: #7db5cc !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
    padding: 6px 12px !important;
    transition: all 0.2s !important;
    text-align: left !important;
    font-weight: 400 !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(0, 212, 255, 0.1) !important;
    border-color: rgba(0, 212, 255, 0.45) !important;
    color: #c0e8f5 !important;
}
[data-testid="stSidebar"] .stButton button:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}

/* ── Sidebar text input (for rename) ── */
[data-testid="stSidebar"] input[type="text"] {
    background: rgba(13, 33, 55, 0.6) !important;
    border: 1px solid rgba(0, 212, 255, 0.25) !important;
    color: #c0e8f5 !important;
    border-radius: 6px !important;
    font-size: 0.75rem !important;
    padding: 6px 10px !important;
}
[data-testid="stSidebar"] input[type="text"]:focus {
    border-color: rgba(0, 212, 255, 0.5) !important;
    box-shadow: 0 0 0 2px rgba(0, 212, 255, 0.1) !important;
}

/* ── Metric overrides ── */
[data-testid="stMetricValue"] {
    color: #00d4ff !important;
    font-size: 1.4rem !important;
}
[data-testid="stMetricLabel"] {
    color: #4a8a9f !important;
    font-size: 0.72rem !important;
}

/* ── Status dot ── */
.status-online  { color: #00ff88; font-weight: 600; }
.status-offline { color: #ff6b6b; font-weight: 600; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #080e1a; }
::-webkit-scrollbar-thumb { background: #1a4060; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #0078a8; }

/* ── Expander ── */
.streamlit-expanderHeader {
    background: rgba(13, 33, 55, 0.6) !important;
    border: 1px solid rgba(0, 212, 255, 0.12) !important;
    border-radius: 8px !important;
    color: #7db5cc !important;
}
</style>
""", unsafe_allow_html=True)


# ── Helper: render metadata strip ─────────────────────────────────────────────
def _render_meta(meta: dict[str, Any]) -> None:
    intent    = meta.get("intent", "—")
    n_results = meta.get("result_count", 0)
    elapsed   = meta.get("elapsed_ms", 0)
    path      = meta.get("execution_path") or []
    entities  = meta.get("entities") or {}

    # Intent badge + path
    badge_cls = f"intent-{intent}".replace(" ", "_")
    nodes_html = ""
    for i, node in enumerate(path):
        nodes_html += f'<span class="exec-node">{node}</span>'
        if i < len(path) - 1:
            nodes_html += '<span class="exec-arrow">▶</span>'

    # Entity filters
    ent_parts = []
    if entities.get("warehouse_id"):
        ent_parts.append(f"🏢 {entities['warehouse_id']}")
    if entities.get("start_date"):
        ent_parts.append(f"📅 {entities['start_date']} → {entities.get('end_date', '—')}")
    filters_html = "  ·  ".join(ent_parts) if ent_parts else ""

    st.markdown(f"""
<div class="meta-strip">
  <div class="meta-row">
    <div class="meta-item">
      <span class="meta-lbl">Intent</span>
      <span class="intent-badge {badge_cls}">{intent}</span>
    </div>
    <div class="meta-item">
      <span class="meta-lbl">Results</span>
      <span class="meta-val">📦 {n_results}</span>
    </div>
    <div class="meta-item">
      <span class="meta-lbl">Latency</span>
      <span class="meta-val">⚡ {elapsed:.0f} ms</span>
    </div>
    {"<div class='meta-item'><span class='meta-lbl'>Filters</span><span class='meta-val'>" + filters_html + "</span></div>" if filters_html else ""}
  </div>
  {('<div class="exec-path" style="margin-top:10px">' + nodes_html + '</div>') if nodes_html else ""}
</div>
""", unsafe_allow_html=True)


# ── Helper: API health ─────────────────────────────────────────────────────────
def _check_health() -> tuple[bool, dict]:
    try:
        r = requests.get(_HEALTH_URL, timeout=5)
        data = r.json()
        return data.get("status") == "ok", data
    except Exception:
        return False, {}


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Brand
    st.markdown("""
<div style="text-align:center; padding: 12px 0 8px 0;">
  <div style="font-size:2rem;">🏭</div>
  <div style="font-size:1rem; font-weight:700; color:#c0dded; margin:4px 0 2px 0;">WH KPI Agent</div>
  <div style="font-size:0.68rem; color:#3a7a9a;">LangGraph · Ollama · MongoDB</div>
</div>
""", unsafe_allow_html=True)
    st.divider()

    # ── Session Management ────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">💬 Conversations</div>', unsafe_allow_html=True)
    
    # Initialize current session if not exists
    if "current_session_id" not in st.session_state:
        st.session_state["current_session_id"] = create_session()
        st.session_state["chat_history"] = []
        st.session_state["history_loaded"] = True  # New empty session, nothing to load
    
    # Current session indicator
    current_session = get_session(st.session_state["current_session_id"])
    if current_session:
        st.markdown(
            f'<div style="background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);'
            f'border-radius:8px;padding:10px 14px;margin-bottom:12px;">'
            f'<div style="font-size:0.64rem;color:#5a9ab5;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:5px;">● Active Session</div>'
            f'<div style="font-size:0.73rem;color:#c0e8f5;font-weight:500;line-height:1.3;">{current_session.name}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    
    # Action buttons
    col_new, col_rename = st.columns(2)
    with col_new:
        if st.button("➕ New Chat", use_container_width=True, key="btn_new_session"):
            new_session_id = create_session()
            st.session_state["current_session_id"] = new_session_id
            st.session_state["chat_history"] = []
            st.session_state["history_loaded"] = False
            st.session_state.pop("show_rename_dialog", None)
            st.rerun()
    
    with col_rename:
        if st.button("✏️ Rename", use_container_width=True, key="btn_show_rename"):
            st.session_state["show_rename_dialog"] = not st.session_state.get("show_rename_dialog", False)
            st.rerun()
    
    # Rename dialog
    if st.session_state.get("show_rename_dialog", False):
        st.markdown('<div style="font-size:0.7rem;color:#5a9ab5;margin:8px 0 4px 0;">Rename Session:</div>', unsafe_allow_html=True)
        new_name = st.text_input(
            "New name:",
            value=current_session.name if current_session else "",
            key="rename_input",
            label_visibility="collapsed",
        )
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("💾 Save", use_container_width=True, key="btn_save_rename"):
                if new_name.strip():
                    rename_session(st.session_state["current_session_id"], new_name.strip())
                st.session_state["show_rename_dialog"] = False
                st.rerun()
        with col_cancel:
            if st.button("❌ Cancel", use_container_width=True, key="btn_cancel_rename"):
                st.session_state["show_rename_dialog"] = False
                st.rerun()
    
    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
    
    # Session list
    st.markdown(
        '<div style="font-size:0.68rem;color:#5a9ab5;margin:8px 0 8px 0;font-weight:600;">📚 Recent Chats</div>',
        unsafe_allow_html=True,
    )
    
    sessions = list_sessions(limit=10)
    if not sessions:
        st.caption("_No previous sessions_")
    else:
        for idx, session in enumerate(sessions):
            is_current = session.session_id == st.session_state["current_session_id"]
            
            # Use columns for better layout
            col_btn, col_del = st.columns([5, 1])
            
            with col_btn:
                # Session button with cleaner styling
                if is_current:
                    # Current session - highlighted
                    st.markdown(
                        f'<div style="background:rgba(0,212,255,0.15);border:1px solid rgba(0,212,255,0.3);'
                        f'border-radius:6px;padding:8px 10px;margin-bottom:4px;cursor:not-allowed;">'
                        f'<div style="font-size:0.7rem;color:#00d4ff;font-weight:600;">🟢 {session.name}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    # Other sessions - clickable
                    if st.button(
                        session.name,
                        use_container_width=True,
                        key=f"sess_{session.session_id}",
                        help=f"Switch to: {session.name}",
                    ):
                        # Switch to this session and LOAD its history
                        st.session_state["current_session_id"] = session.session_id
                        st.session_state["history_loaded"] = False  # Mark as needs loading
                        st.session_state.pop("show_rename_dialog", None)
                        update_session_access(session.session_id)
                        st.rerun()
            
            with col_del:
                if not is_current:  # Can't delete active session
                    if st.button("🗑️", key=f"del_{session.session_id}", help="Delete session"):
                        delete_session(session.session_id)
                        st.rerun()
    
    st.divider()

    # ── API Status ────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">⚡ System Status</div>', unsafe_allow_html=True)

    if "api_status" not in st.session_state:
        st.session_state["api_status"] = None

    col_a, col_b = st.columns([3, 2])
    with col_a:
        if st.button("↻ Refresh", use_container_width=True, key="btn_health"):
            ok, health_data = _check_health()
            st.session_state["api_status"] = (ok, health_data)
    with col_b:
        if st.session_state["api_status"] is None:
            st.markdown('<span style="font-size:0.72rem;color:#3a7a9a;">unknown</span>', unsafe_allow_html=True)
        elif st.session_state["api_status"][0]:
            st.markdown('<span class="status-online">● online</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-offline">● offline</span>', unsafe_allow_html=True)

    if st.session_state["api_status"] is not None:
        ok, health_data = st.session_state["api_status"]
        if ok:
            col_counts = health_data.get("checks", {}).get("mongodb", {}).get("collections", {})
            if col_counts:
                for c, n in col_counts.items():
                    st.markdown(
                        f'<span class="coll-pill">📂 {c} <b style="color:#9ed0e8">{n:,}</b></span>',
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("⚠️ Run `make api` to start the API server")

    st.divider()

    # ── Collections ───────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">🗃️ Collections</div>', unsafe_allow_html=True)
    _COLL_ICONS = {
        "inbound_parts":          ("📥", "Supply & lead times"),
        "outbound_parts":         ("📤", "Orders & fill rates"),
        "inventory_snapshot":     ("📦", "Stock & stockouts"),
        "warehouse_productivity": ("⚙️", "Shift operations"),
        "employee_productivity":  ("👷", "Employee metrics"),
    }
    for cname, (icon, desc) in _COLL_ICONS.items():
        st.markdown(
            f'<div style="padding:5px 0;border-bottom:1px solid rgba(0,212,255,0.06);">'
            f'<span style="font-size:0.8rem;">{icon}</span> '
            f'<span style="font-size:0.72rem;color:#8cbbd0;font-weight:500;">{cname}</span><br/>'
            f'<span style="font-size:0.66rem;color:#3a7a9a;padding-left:20px;">{desc}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Available KPIs ────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">📊 KPI Registry</div>', unsafe_allow_html=True)
    try:
        r = requests.get(_KPIS_URL, timeout=4)
        if r.status_code == 200:
            kpis: list[dict] = r.json().get("kpis", [])
            area_map: dict[str, list] = {}
            for k in kpis:
                area_map.setdefault(k.get("area", "other"), []).append(k)
            for area, area_kpis in sorted(area_map.items()):
                with st.expander(f"**{area.title()}** ({len(area_kpis)})"):
                    for k in area_kpis:
                        st.caption(f"• `{k['key']}` — {k.get('name', k['key'])}")
        else:
            st.caption("_No KPIs loaded_")
    except Exception:
        st.caption("_Start API to load KPIs_")

    st.divider()

    # ── Example queries ───────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">💡 Quick Queries</div>', unsafe_allow_html=True)
    _EXAMPLES = [
        ("📦", "What is the fill rate for WH-01?"),
        ("📊", "Show all KPIs for warehouse WH-02 in Q1 2025"),
        ("📥", "Analyse inbound supplier performance for WH-03"),
        ("🌐", "Give me a complete overview of all collections"),
        ("🚚", "Top delaying suppliers by lead time"),
        ("👷", "Employee error rate across all warehouses"),
        ("⚠️", "What is the stockout percentage by warehouse?"),
        ("📈", "OTIF and backorder rate comparison"),
    ]
    for icon, ex in _EXAMPLES:
        if st.button(f"{icon} {ex}", use_container_width=True, key=f"ex_{ex[:20]}"):
            st.session_state["_prefill"] = ex

    st.divider()

    # ── Clear Chat ────────────────────────────────────────────────────────────
    if st.button("🗑️ Clear Current Chat", use_container_width=True, key="btn_clear"):
        st.session_state["chat_history"] = []
        st.rerun()

    st.divider()

    # ── Data Sync ─────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section">🔄 Data Management</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.68rem;color:#3a7a9a;margin-bottom:8px;">'
        'Drops all collections and reloads from raw CSV files.</div>',
        unsafe_allow_html=True,
    )
    if st.button("⚡ Sync Data from CSVs", use_container_width=True, key="btn_sync"):
        with st.spinner("⏳ Syncing data — dropping collections and re-ingesting…"):
            try:
                resp = requests.post(_SYNC_URL, timeout=300)
                if resp.status_code == 200:
                    data = resp.json()
                    counts = data.get("collection_counts", {})
                    elapsed = data.get("elapsed_ms", 0)
                    st.success(f"✅ Sync complete in {elapsed/1000:.1f}s")
                    for cname, cnt in counts.items():
                        st.markdown(
                            f'<span class="coll-pill">📂 {cname} '
                            f'<b style="color:#9ed0e8">{cnt:,}</b></span>',
                            unsafe_allow_html=True,
                        )
                    # Reset API status so it reflects new counts
                    st.session_state["api_status"] = None
                else:
                    st.error(f"❌ Sync failed ({resp.status_code}): {resp.text[:200]}")
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Start it first.")
            except requests.exceptions.Timeout:
                st.warning("⏱️ Sync timed out — the pipeline may still be running.")
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")


# ── Header Banner ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="wh-banner">
  <h1>🏭 Warehouse Intelligence Agent</h1>
  <p class="subtitle">AI-powered analytics across inbound, outbound, inventory, operations & workforce</p>
  <div>
    <span class="wh-badge">LangGraph</span>
    <span class="wh-badge">qwen2.5:7b</span>
    <span class="wh-badge">MongoDB</span>
    <span class="wh-badge">5 Collections</span>
    <span class="wh-badge">FastAPI</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Chat history init ──────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# ── Welcome screen (no messages yet) ──────────────────────────────────────────
if not st.session_state["chat_history"]:
    st.markdown("""
<div style="text-align:center; padding: 10px 0 4px 0;">
  <div style="font-size:0.8rem; color:#3a7a9a; text-transform:uppercase; letter-spacing:0.1em; font-weight:600;">
    What would you like to analyse?
  </div>
</div>
""", unsafe_allow_html=True)

    _QUICK_CARDS = [
        ("📥", "Inbound Analysis",     "Supplier delays, lead times, discrepancy rates",
         "Analyse inbound supplier performance and lead times across all warehouses"),
        ("📤", "Outbound Fulfilment",  "Fill rate, OTIF, backorder analysis",
         "Show me the OTIF performance and fill rate across all warehouses"),
        ("📦", "Inventory Health",     "Stockouts, aging, safety stock",
         "What is the stockout percentage and inventory health across all warehouses?"),
        ("⚙️", "Warehouse Operations","Picks/hr, SLA adherence, equipment utilisation",
         "Analyse warehouse productivity by shift — picks per hour, SLA and equipment utilisation"),
        ("👷", "Employee Productivity","Error rates, overtime, top performers",
         "Analyse the employee productivity data — picks per hour, error rate and overtime by role"),
        ("🌐", "Full Overview",        "Cross-collection KPI dashboard",
         "Give me a complete overview of all warehouse collections and key KPIs"),
    ]

    cols = st.columns(3)
    for i, (icon, title, desc, query_text) in enumerate(_QUICK_CARDS):
        with cols[i % 3]:
            st.markdown(f"""
<div class="welcome-card">
  <div class="wc-icon">{icon}</div>
  <div class="wc-title">{title}</div>
  <div class="wc-desc">{desc}</div>
</div>
""", unsafe_allow_html=True)
            if st.button(f"Ask →", key=f"wc_{i}", use_container_width=True):
                st.session_state["_prefill"] = query_text
                st.rerun()

    st.markdown("<br/>", unsafe_allow_html=True)

# ── Load conversation history from database if switching sessions ──────────────
if not st.session_state.get("history_loaded", False):
    # Load conversation history from SQLite checkpoint
    conv_history = get_conversation_history(st.session_state["current_session_id"])
    
    if conv_history:
        # Convert conversation history to chat display format
        st.session_state["chat_history"] = []
        for turn in conv_history:
            # Add user message
            st.session_state["chat_history"].append({
                "role": "user",
                "content": turn.get("query", ""),
                "avatar": "👤"
            })
            # Add assistant message
            st.session_state["chat_history"].append({
                "role": "assistant",
                "content": turn.get("response", ""),
                "avatar": "🤖"
            })
    else:
        # No history found - ensure chat_history is empty
        st.session_state["chat_history"] = []
    
    # Mark as loaded
    st.session_state["history_loaded"] = True

# ── Render existing messages ───────────────────────────────────────────────────
for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"], avatar=msg.get("avatar")):
        if msg["role"] == "assistant":
            st.markdown(msg["content"])
            _meta: Optional[dict[str, Any]] = msg.get("meta")
            if _meta:
                _render_meta(_meta)
            # Replay download button for registered_kpi results
            _hist_excel: Optional[str] = msg.get("excel_export_path")
            if _hist_excel:
                _hist_path = Path(_hist_excel)
                if _hist_path.exists():
                    with open(_hist_path, "rb") as _f:
                        _hist_bytes = _f.read()
                    st.download_button(
                        label="⬇️ Download KPI Report (.xlsx)",
                        data=_hist_bytes,
                        file_name=_hist_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"hist_dl_{_hist_path.name}",
                    )
        else:
            st.markdown(msg["content"])


# ── Query input ────────────────────────────────────────────────────────────────
_prefill = st.session_state.pop("_prefill", "")
query = st.chat_input("Ask about warehouse KPIs, inventory, operations, employee productivity…")

if _prefill and not query:
    query = _prefill

if query:
    # Update session with first query if this is the first message
    if len(st.session_state["chat_history"]) == 0:
        update_session_first_query(st.session_state["current_session_id"], query)
    
    # Update last accessed timestamp
    update_session_access(st.session_state["current_session_id"])
    
    # Display user turn
    with st.chat_message("user", avatar="👤"):
        st.markdown(query)
    st.session_state["chat_history"].append({"role": "user", "content": query, "avatar": "👤"})

    # Assistant turn
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🔍 Querying warehouse intelligence…"):
            try:
                t0 = time.perf_counter()
                resp = requests.post(
                    _QUERY_URL,
                    json={
                        "query": query,
                        "session_id": st.session_state["current_session_id"],
                    },
                    timeout=_TIMEOUT_SEC,
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

                if resp.status_code == 200:
                    data: dict[str, Any] = resp.json()
                    md_text: str = data.get("formatted_response") or "_No response generated._"

                    st.markdown(md_text)

                    meta: dict[str, Any] = {
                        "intent":         data.get("classified_intent", "—"),
                        "result_count":   data.get("result_count", 0),
                        "elapsed_ms":     data.get("elapsed_ms", elapsed_ms),
                        "execution_path": data.get("execution_path") or [],
                        "entities":       data.get("entities_extracted") or {},
                    }
                    _render_meta(meta)

                    # ── Excel download button (registered_kpi only) ────────────
                    excel_path_str: Optional[str] = data.get("excel_export_path")
                    if excel_path_str:
                        excel_path = Path(excel_path_str)
                        if excel_path.exists():
                            with open(excel_path, "rb") as f:
                                excel_bytes = f.read()
                            st.download_button(
                                label="⬇️ Download KPI Report (.xlsx)",
                                data=excel_bytes,
                                file_name=excel_path.name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_{excel_path.name}",
                            )

                    st.session_state["chat_history"].append({
                        "role":             "assistant",
                        "avatar":           "🤖",
                        "content":          md_text,
                        "meta":             meta,
                        "excel_export_path": excel_path_str,
                    })

                    if data.get("error"):
                        st.warning(f"⚠️ {data['error']}")

                else:
                    err_msg = f"**API Error {resp.status_code}**\n\n```\n{resp.text}\n```"
                    st.error(err_msg)
                    st.session_state["chat_history"].append(
                        {"role": "assistant", "avatar": "🤖", "content": err_msg}
                    )

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API. Start it with: `make api`")
            except requests.exceptions.Timeout:
                st.warning(
                    "⏱️ Request timed out (>120 s). "
                    "The LLM may be slow — try again or restart Ollama."
                )
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")


# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="
    border-top: 1px solid rgba(0,212,255,0.1);
    margin-top: 32px;
    padding-top: 16px;
    text-align: center;
    font-size: 0.7rem;
    color: #2a6a80;
">
  🏭 <b style="color:#3a8a9a">Warehouse KPI Agent</b>
  &nbsp;·&nbsp; LangGraph + Ollama (qwen2.5:7b) + MongoDB
  &nbsp;·&nbsp; <a href="http://localhost:8000/docs" style="color:#0a8aaa;">API Docs</a>
  &nbsp;·&nbsp; <a href="http://localhost:8000/redoc" style="color:#0a8aaa;">Redoc</a>
</div>
""", unsafe_allow_html=True)
