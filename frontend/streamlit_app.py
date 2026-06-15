"""
Autonomous Research Agent — Premium Streamlit Frontend
Complete dark-mode glassmorphism redesign with live streaming progress.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import requests
import streamlit as st

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Research Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://localhost:8000/api/v1"

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  /* Global reset */
  html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
  }
  .stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1526 50%, #0a1020 100%);
    min-height: 100vh;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: rgba(15, 23, 42, 0.95) !important;
    border-right: 1px solid rgba(99, 179, 237, 0.15);
  }
  [data-testid="stSidebar"] .stMarkdown h1,
  [data-testid="stSidebar"] .stMarkdown h2,
  [data-testid="stSidebar"] .stMarkdown h3 {
    color: #63b3ed !important;
  }

  /* Main header */
  .hero-header {
    background: linear-gradient(135deg, rgba(99,179,237,0.08) 0%, rgba(139,92,246,0.08) 100%);
    border: 1px solid rgba(99,179,237,0.2);
    border-radius: 20px;
    padding: 2.5rem 2rem;
    margin-bottom: 2rem;
    text-align: center;
    backdrop-filter: blur(20px);
    position: relative;
    overflow: hidden;
  }
  .hero-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at 50% 50%, rgba(99,179,237,0.05) 0%, transparent 60%);
    animation: pulse-bg 4s ease-in-out infinite;
  }
  @keyframes pulse-bg {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }
  .hero-header h1 {
    font-size: 2.4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #63b3ed 0%, #a78bfa 50%, #f472b6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 0.5rem 0;
  }
  .hero-header p {
    color: rgba(148, 163, 184, 0.9);
    font-size: 1.05rem;
    margin: 0;
  }

  /* Glass cards */
  .glass-card {
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(99, 179, 237, 0.15);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
    backdrop-filter: blur(20px);
    transition: border-color 0.3s, transform 0.2s;
  }
  .glass-card:hover {
    border-color: rgba(99, 179, 237, 0.35);
    transform: translateY(-2px);
  }

  /* Phase tracker */
  .phase-tracker {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    margin-bottom: 1.5rem;
    overflow-x: auto;
  }
  .phase-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1;
    min-width: 80px;
  }
  .phase-dot {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    margin-bottom: 0.4rem;
    transition: all 0.4s ease;
    border: 2px solid rgba(99,179,237,0.3);
    background: rgba(15, 23, 42, 0.8);
  }
  .phase-dot.done {
    background: linear-gradient(135deg, #10b981, #059669);
    border-color: #10b981;
    box-shadow: 0 0 12px rgba(16,185,129,0.5);
  }
  .phase-dot.active {
    background: linear-gradient(135deg, #63b3ed, #a78bfa);
    border-color: #63b3ed;
    box-shadow: 0 0 16px rgba(99,179,237,0.6);
    animation: pulse-dot 1.5s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { box-shadow: 0 0 10px rgba(99,179,237,0.4); }
    50% { box-shadow: 0 0 24px rgba(99,179,237,0.9); }
  }
  .phase-label {
    font-size: 0.65rem;
    color: rgba(148,163,184,0.7);
    text-align: center;
    line-height: 1.2;
  }
  .phase-label.active {
    color: #63b3ed;
    font-weight: 600;
  }
  .phase-connector {
    flex: 0.5;
    height: 2px;
    background: rgba(99,179,237,0.15);
    margin-bottom: 1.2rem;
    transition: background 0.4s;
  }
  .phase-connector.done {
    background: linear-gradient(90deg, #10b981, #059669);
  }

  /* Progress bar */
  .progress-container {
    background: rgba(15, 23, 42, 0.8);
    border-radius: 999px;
    height: 8px;
    overflow: hidden;
    margin: 1rem 0;
  }
  .progress-bar {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #63b3ed, #a78bfa, #f472b6);
    transition: width 0.6s ease;
    box-shadow: 0 0 10px rgba(99,179,237,0.5);
  }

  /* Stats row */
  .stats-row {
    display: flex;
    gap: 1rem;
    margin: 1rem 0;
    flex-wrap: wrap;
  }
  .stat-chip {
    background: rgba(99,179,237,0.08);
    border: 1px solid rgba(99,179,237,0.2);
    border-radius: 999px;
    padding: 0.35rem 1rem;
    font-size: 0.82rem;
    color: #a5c8e8;
    white-space: nowrap;
  }
  .stat-chip span {
    font-weight: 700;
    color: #63b3ed;
  }

  /* Source cards */
  .source-card {
    background: rgba(15,23,42,0.6);
    border: 1px solid rgba(99,179,237,0.12);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.3s, transform 0.2s;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }
  .source-card:hover {
    border-color: rgba(99,179,237,0.3);
    transform: translateX(4px);
  }
  .source-icon {
    font-size: 1.5rem;
    flex-shrink: 0;
    width: 40px;
    text-align: center;
  }
  .source-info { flex: 1; min-width: 0; }
  .source-title {
    font-size: 0.9rem;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 0.2rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .source-domain {
    font-size: 0.75rem;
    color: rgba(148,163,184,0.7);
    margin-bottom: 0.4rem;
  }
  .source-score {
    display: inline-block;
    background: rgba(16,185,129,0.15);
    border: 1px solid rgba(16,185,129,0.3);
    border-radius: 4px;
    padding: 0.1rem 0.5rem;
    font-size: 0.72rem;
    color: #34d399;
    font-family: 'JetBrains Mono', monospace;
  }
  .content-badge {
    display: inline-block;
    border-radius: 4px;
    padding: 0.1rem 0.5rem;
    font-size: 0.7rem;
    font-weight: 500;
    margin-left: 0.5rem;
  }
  .badge-academic { background: rgba(99,179,237,0.15); color: #63b3ed; border: 1px solid rgba(99,179,237,0.3); }
  .badge-news     { background: rgba(251,191,36,0.12); color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
  .badge-gov      { background: rgba(167,139,250,0.15); color: #a78bfa; border: 1px solid rgba(167,139,250,0.3); }
  .badge-blog     { background: rgba(244,114,182,0.12); color: #f472b6; border: 1px solid rgba(244,114,182,0.3); }
  .badge-default  { background: rgba(148,163,184,0.1); color: #94a3b8; border: 1px solid rgba(148,163,184,0.2); }

  /* Claim cards */
  .claim-card {
    background: rgba(15,23,42,0.6);
    border-left: 3px solid #63b3ed;
    border-radius: 0 10px 10px 0;
    padding: 0.85rem 1.1rem;
    margin-bottom: 0.6rem;
    transition: background 0.2s;
  }
  .claim-card:hover { background: rgba(99,179,237,0.05); }
  .claim-card.contested { border-left-color: #f59e0b; }
  .claim-card.high-conf { border-left-color: #10b981; }
  .claim-text {
    font-size: 0.88rem;
    color: #e2e8f0;
    line-height: 1.5;
    margin-bottom: 0.4rem;
  }
  .claim-meta { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .conf-bar-wrap {
    flex: 1;
    background: rgba(99,179,237,0.1);
    border-radius: 999px;
    height: 5px;
    max-width: 120px;
  }
  .conf-bar {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #63b3ed, #10b981);
  }
  .conf-label {
    font-size: 0.72rem;
    color: #10b981;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    min-width: 40px;
  }
  .contested-badge {
    font-size: 0.68rem;
    background: rgba(245,158,11,0.15);
    border: 1px solid rgba(245,158,11,0.3);
    color: #f59e0b;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
  }

  /* Report content */
  .report-content {
    background: rgba(15,23,42,0.5);
    border: 1px solid rgba(99,179,237,0.1);
    border-radius: 12px;
    padding: 2rem;
    font-size: 0.93rem;
    line-height: 1.7;
    color: #cbd5e1;
  }
  .report-content h1,h2,h3,h4 { color: #e2e8f0 !important; }
  .report-content h2 { border-bottom: 1px solid rgba(99,179,237,0.2); padding-bottom: 0.4rem; }
  .report-content code {
    background: rgba(99,179,237,0.1);
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85em;
    color: #63b3ed;
  }
  .report-content blockquote {
    border-left: 3px solid #a78bfa;
    margin: 1rem 0;
    padding: 0.5rem 1rem;
    background: rgba(167,139,250,0.05);
    border-radius: 0 8px 8px 0;
  }
  .report-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 1rem 0;
  }
  .report-content th, .report-content td {
    border: 1px solid rgba(99,179,237,0.2);
    padding: 0.5rem 0.8rem;
    text-align: left;
  }
  .report-content th {
    background: rgba(99,179,237,0.08);
    color: #63b3ed;
    font-weight: 600;
  }

  /* Buttons */
  .stButton > button {
    background: linear-gradient(135deg, #63b3ed, #a78bfa) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.8rem !important;
    font-size: 0.95rem !important;
    transition: all 0.3s !important;
    box-shadow: 0 4px 20px rgba(99,179,237,0.3) !important;
  }
  .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 30px rgba(99,179,237,0.5) !important;
  }

  /* Text inputs */
  .stTextArea textarea, .stTextInput input {
    background: rgba(15,23,42,0.8) !important;
    border: 1px solid rgba(99,179,237,0.25) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    transition: border-color 0.3s !important;
  }
  .stTextArea textarea:focus, .stTextInput input:focus {
    border-color: rgba(99,179,237,0.6) !important;
    box-shadow: 0 0 0 3px rgba(99,179,237,0.1) !important;
  }

  /* Select boxes */
  .stSelectbox > div > div {
    background: rgba(15,23,42,0.8) !important;
    border: 1px solid rgba(99,179,237,0.25) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
  }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background: rgba(15,23,42,0.6);
    border-radius: 12px;
    padding: 0.3rem;
    gap: 0.3rem;
    border: 1px solid rgba(99,179,237,0.1);
  }
  .stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px !important;
    color: rgba(148,163,184,0.7) !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
  }
  .stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(99,179,237,0.2), rgba(167,139,250,0.2)) !important;
    color: #63b3ed !important;
    border: 1px solid rgba(99,179,237,0.3) !important;
  }

  /* Labels / headings */
  .stMarkdown h1 { color: #e2e8f0; }
  .stMarkdown h2 { color: #cbd5e1; }
  .stMarkdown h3 { color: #a5c8e8; }
  p, li, .stMarkdown p { color: #94a3b8; }

  /* Error / success / info */
  .stAlert { border-radius: 10px !important; }

  /* Divider */
  hr { border-color: rgba(99,179,237,0.12) !important; }

  /* History item */
  .history-item {
    background: rgba(15,23,42,0.5);
    border: 1px solid rgba(99,179,237,0.12);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .history-item:hover {
    border-color: rgba(99,179,237,0.35);
    background: rgba(99,179,237,0.05);
  }
  .history-q {
    font-size: 0.82rem;
    color: #cbd5e1;
    font-weight: 500;
    margin-bottom: 0.3rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .history-meta { display: flex; gap: 0.5rem; }
  .history-badge {
    font-size: 0.65rem;
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
  }
  .badge-done { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }
  .badge-fail { background: rgba(239,68,68,0.12); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
  .badge-run  { background: rgba(99,179,237,0.12); color: #63b3ed; border: 1px solid rgba(99,179,237,0.3); }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ─────────────────────────────────────────────────────────────────

PHASES = [
    ("plan_research",        "🧠", "Planning"),
    ("discover_sources",     "🔍", "Discovery"),
    ("rank_sources",         "📊", "Ranking"),
    ("retrieve_content",     "📥", "Retrieval"),
    ("extract_information",  "🧬", "Extraction"),
    ("verify_claims",        "✅", "Verification"),
    ("synthesize_knowledge", "💡", "Synthesis"),
    ("generate_report",      "📝", "Reporting"),
]

PHASE_ORDER = {
    "starting": -1,
    "planning_complete": 0,
    "discovery_complete": 1,
    "ranking_complete": 2,
    "retrieval_complete": 3,
    "extraction_complete": 4,
    "verification_complete": 5,
    "synthesis_complete": 6,
    "report_complete": 7,
}

CONTENT_TYPE_ICONS = {
    "academic_paper": "📄",
    "government_report": "🏛️",
    "industry_report": "📊",
    "news_article": "📰",
    "blog_post": "✍️",
    "wiki": "📖",
    "pdf": "📑",
    "documentation": "📚",
    "unknown": "🌐",
}

CONTENT_TYPE_BADGE = {
    "academic_paper": "badge-academic",
    "news_article": "badge-news",
    "government_report": "badge-gov",
    "blog_post": "badge-blog",
}


def api_get(path: str) -> dict | list | None:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=10)
        if r.ok:
            return r.json()
        return None
    except Exception:
        return None


def api_post(path: str, data: dict) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=data, timeout=10)
        if r.ok:
            return r.json()
        return None
    except Exception:
        return None


def render_phase_tracker(current_phase: str, status: str) -> None:
    phase_idx = PHASE_ORDER.get(current_phase, -1)

    html = '<div class="phase-tracker">'
    for i, (phase_key, icon, label) in enumerate(PHASES):
        # Determine state
        done_idx = PHASE_ORDER.get(current_phase, -1)
        phase_complete_idx = i  # index into PHASES

        if status == "completed":
            dot_class = "done"
            label_class = ""
        elif phase_complete_idx < done_idx:
            dot_class = "done"
            label_class = ""
        elif phase_complete_idx == done_idx:
            dot_class = "active"
            label_class = "active"
        else:
            dot_class = ""
            label_class = ""

        html += f'<div class="phase-item"><div class="phase-dot {dot_class}">{icon}</div><div class="phase-label {label_class}">{label}</div></div>'
        if i < len(PHASES) - 1:
            conn_class = "done" if phase_complete_idx < done_idx and status != "starting" else ""
            html += f'<div class="phase-connector {conn_class}"></div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_stats(status_data: dict) -> None:
    sources = status_data.get("sources_found", 0)
    facts = status_data.get("facts_extracted", 0)
    claims = status_data.get("claims_verified", 0)
    progress = status_data.get("progress_percent", 0)

    html = f"""
    <div class="stats-row">
      <div class="stat-chip">🌐 <span>{sources}</span> sources found</div>
      <div class="stat-chip">🧬 <span>{facts}</span> facts extracted</div>
      <div class="stat-chip">✅ <span>{claims}</span> claims verified</div>
      <div class="stat-chip">⚡ <span>{progress}%</span> complete</div>
    </div>
    <div class="progress-container">
      <div class="progress-bar" style="width: {progress}%"></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_source_card(source: dict, idx: int) -> None:
    ct = source.get("content_type", "unknown")
    icon = CONTENT_TYPE_ICONS.get(ct, "🌐")
    badge_class = CONTENT_TYPE_BADGE.get(ct, "badge-default")
    score = source.get("score", 0)
    title = source.get("title") or source.get("domain", "Unknown")
    domain = source.get("domain", "")
    url = source.get("url", "#")

    ct_label = ct.replace("_", " ").title()
    score_pct = f"{score:.0%}" if isinstance(score, float) else str(score)

    html = f"""
    <div class="source-card">
      <div class="source-icon">{icon}</div>
      <div class="source-info">
        <div class="source-title" title="{title}">[{idx}] {title}</div>
        <div class="source-domain">
          <a href="{url}" target="_blank" style="color:rgba(99,179,237,0.7);text-decoration:none;">{domain}</a>
        </div>
        <div>
          <span class="source-score">{score_pct}</span>
          <span class="content-badge {badge_class}">{ct_label}</span>
        </div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_claim_card(claim: dict) -> None:
    conf = claim.get("confidence", 0)
    conf_pct = f"{conf:.0%}"
    statement = claim.get("statement", "")
    contested = claim.get("is_contested", False)
    notes = claim.get("verification_notes", "")

    card_class = "claim-card contested" if contested else ("claim-card high-conf" if conf >= 0.7 else "claim-card")
    bar_width = f"{conf * 100:.0f}%"

    contested_html = '<span class="contested-badge">⚠️ Contested</span>' if contested else ""

    html = f"""
    <div class="{card_class}">
      <div class="claim-text">{statement}</div>
      <div class="claim-meta">
        <div class="conf-bar-wrap"><div class="conf-bar" style="width:{bar_width}"></div></div>
        <span class="conf-label">{conf_pct}</span>
        {contested_html}
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_history_item(job: dict) -> str:
    status = job.get("status", "unknown")
    question = job.get("question", "Unknown query")[:80]
    depth = job.get("depth", "standard")
    job_id = job.get("job_id", "")
    started = job.get("started_at", "")

    badge_class = {"completed": "badge-done", "failed": "badge-fail"}.get(status, "badge-run")
    status_label = {"completed": "✅ Done", "failed": "❌ Failed", "running": "⏳ Running", "queued": "🕐 Queued"}.get(status, status)

    return f"""
    <div class="history-item" id="hist-{job_id[:8]}">
      <div class="history-q" title="{question}">{question}</div>
      <div class="history-meta">
        <span class="history-badge {badge_class}">{status_label}</span>
        <span class="history-badge badge-default">{depth}</span>
      </div>
    </div>
    """


# ─── State helpers ────────────────────────────────────────────────────────────

def get_status(job_id: str) -> dict:
    data = api_get(f"/research/{job_id}/status")
    return data or {}


def get_report(job_id: str) -> dict:
    data = api_get(f"/research/{job_id}/report")
    return data or {}


def get_sources(job_id: str) -> list:
    data = api_get(f"/research/{job_id}/sources")
    return data or []


def get_claims(job_id: str) -> list:
    data = api_get(f"/research/{job_id}/claims")
    return data or []


def get_history() -> list:
    data = api_get("/history")
    return data or []


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0 0.5rem;">
      <div style="font-size:2.5rem;">🔬</div>
      <div style="font-size:1.1rem; font-weight:700; color:#63b3ed; margin-top:0.3rem;">Research Agent</div>
      <div style="font-size:0.72rem; color:rgba(148,163,184,0.6); margin-top:0.2rem;">AI-Powered Deep Research</div>
    </div>
    <hr>
    """, unsafe_allow_html=True)

    # API health check
    health = api_get("/health")
    if health:
        st.markdown('<div style="text-align:center;"><span style="background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.3);border-radius:20px;padding:0.2rem 0.8rem;font-size:0.75rem;color:#34d399;">● API Online</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align:center;"><span style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);border-radius:20px;padding:0.2rem 0.8rem;font-size:0.75rem;color:#f87171;">● API Offline</span></div>', unsafe_allow_html=True)
        st.warning("Start the API: `uvicorn app.main:app --port 8000`")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📜 Recent Searches")

    history = get_history()
    if history:
        for job in history[:8]:
            job_id = job.get("job_id", "")
            if st.button(
                f"{'✅' if job.get('status') == 'completed' else '❌' if job.get('status') == 'failed' else '⏳'} {job.get('question','')[:40]}...",
                key=f"hist_{job_id}",
                use_container_width=True,
            ):
                st.session_state.current_job_id = job_id
                st.session_state.show_results = True
                st.rerun()
    else:
        st.markdown('<div style="color:rgba(148,163,184,0.5);font-size:0.8rem;text-align:center;padding:1rem 0;">No history yet</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### ⚙️ About")
    st.markdown("""
    <div style="font-size:0.78rem; color:rgba(148,163,184,0.7); line-height:1.8;">
    🧠 LangGraph 8-phase workflow<br>
    🔍 Tavily + DuckDuckGo search<br>
    🤖 Gemini + Groq with fallback<br>
    📊 ChromaDB vector memory<br>
    ✅ Cross-source fact verification<br>
    📝 IEEE-cited Markdown reports
    </div>
    """, unsafe_allow_html=True)


# ─── Main content ─────────────────────────────────────────────────────────────

# Hero header
st.markdown("""
<div class="hero-header">
  <h1>🔬 Autonomous Research Agent</h1>
  <p>Submit any research question and get a comprehensive, fact-verified report with citations — powered by multi-agent AI.</p>
</div>
""", unsafe_allow_html=True)

# ─── Input form ───────────────────────────────────────────────────────────────

if "current_job_id" not in st.session_state:
    st.session_state.current_job_id = None
if "show_results" not in st.session_state:
    st.session_state.show_results = False
if "polling" not in st.session_state:
    st.session_state.polling = False

with st.container():
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🎯 New Research Query")

    col1, col2 = st.columns([3, 1])
    with col1:
        question = st.text_area(
            "Research Question",
            placeholder="e.g., What is the impact of large language models on software engineering productivity in 2025?",
            height=100,
            label_visibility="collapsed",
        )
    with col2:
        depth = st.selectbox(
            "Depth",
            ["quick", "standard", "deep"],
            index=1,
            help="Quick: ~2 min | Standard: ~5 min | Deep: ~10 min",
        )
        st.markdown("<br>", unsafe_allow_html=True)
        submit = st.button("🚀 Start Research", use_container_width=True, type="primary")

    st.markdown('</div>', unsafe_allow_html=True)

# ─── Submit handler ────────────────────────────────────────────────────────────

if submit:
    if not question or len(question.strip()) < 10:
        st.error("Please enter a research question (at least 10 characters).")
    else:
        with st.spinner("Submitting research job..."):
            result = api_post("/research", {
                "question": question.strip(),
                "depth": depth,
            })
        if result and result.get("job_id"):
            st.session_state.current_job_id = result["job_id"]
            st.session_state.show_results = True
            st.session_state.polling = True
            st.rerun()
        else:
            st.error("Failed to submit research job. Is the API server running?")

# ─── Results panel ─────────────────────────────────────────────────────────────

if st.session_state.show_results and st.session_state.current_job_id:
    job_id = st.session_state.current_job_id

    st.markdown("---")

    # Get current status
    status_data = get_status(job_id)
    status = status_data.get("status", "unknown")
    phase = status_data.get("current_phase", "starting")
    progress = status_data.get("progress_percent", 0)
    errors = status_data.get("errors", [])

    # ── Progress section ──────────────────────────────────────────────────────
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    phase_label = phase.replace("_", " ").replace("complete", "✓").title()
    if status == "completed":
        st.markdown(f"### ✅ Research Complete")
    elif status == "failed":
        st.markdown(f"### ❌ Research Failed")
    elif status == "running":
        st.markdown(f"### ⏳ Researching... — *{phase_label}*")
    else:
        st.markdown(f"### 🕐 Queued")

    render_phase_tracker(phase, status)
    render_stats(status_data)

    if errors:
        with st.expander(f"⚠️ {len(errors)} warning(s)"):
            for err in errors:
                st.warning(err)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Auto-refresh while running ────────────────────────────────────────────
    if status in ("running", "queued"):
        time.sleep(3)
        st.rerun()

    # ── Results tabs ──────────────────────────────────────────────────────────
    if status == "completed":
        report_data = get_report(job_id)
        sources = get_sources(job_id)
        claims = get_claims(job_id)

        tab1, tab2, tab3, tab4 = st.tabs([
            f"📋 Summary",
            f"📄 Full Report",
            f"🌐 Sources ({len(sources)})",
            f"✅ Claims ({len(claims)})",
        ])

        # ── Tab 1: Summary ────────────────────────────────────────────────────
        with tab1:
            if report_data:
                # Quick stats
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Sources Used", report_data.get("total_sources", 0))
                with c2:
                    st.metric("Claims Verified", report_data.get("total_claims", 0))
                with c3:
                    gen_time = report_data.get("generation_time_seconds", 0)
                    st.metric("Generation Time", f"{gen_time:.0f}s")
                with c4:
                    high_conf = sum(1 for c in claims if c.get("confidence", 0) >= 0.7)
                    st.metric("High-Confidence", high_conf)

                # Executive summary (first section)
                md = report_data.get("markdown_content", "")
                if md:
                    # Extract executive summary section
                    lines = md.split("\n")
                    in_exec = False
                    exec_lines = []
                    for line in lines:
                        if "executive summary" in line.lower() and line.startswith("#"):
                            in_exec = True
                            continue
                        if in_exec:
                            if line.startswith("##") and "executive" not in line.lower():
                                break
                            exec_lines.append(line)
                    if exec_lines:
                        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                        st.markdown("#### 📋 Executive Summary")
                        st.markdown("\n".join(exec_lines))
                        st.markdown('</div>', unsafe_allow_html=True)

                # Top claims preview
                if claims:
                    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                    st.markdown("#### 🏆 Top Verified Claims")
                    top_claims = sorted(claims, key=lambda c: c.get("confidence", 0), reverse=True)[:5]
                    for claim in top_claims:
                        render_claim_card(claim)
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.warning("Report not available yet.")

        # ── Tab 2: Full Report ────────────────────────────────────────────────
        with tab2:
            if report_data and report_data.get("markdown_content"):
                md = report_data["markdown_content"]

                # Download button
                st.download_button(
                    label="⬇️ Download Markdown",
                    data=md,
                    file_name=f"research_report_{job_id[:8]}.md",
                    mime="text/markdown",
                )

                st.markdown('<div class="report-content">', unsafe_allow_html=True)
                st.markdown(md)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.warning("Full report not available.")

        # ── Tab 3: Sources ────────────────────────────────────────────────────
        with tab3:
            if sources:
                # Filter controls
                col1, col2 = st.columns([2, 1])
                with col1:
                    search_filter = st.text_input("🔍 Filter sources", placeholder="domain or title...")
                with col2:
                    sort_by = st.selectbox("Sort by", ["Score ↓", "Score ↑", "Type"])

                filtered = sources
                if search_filter:
                    s = search_filter.lower()
                    filtered = [
                        src for src in sources
                        if s in (src.get("domain", "") + src.get("title", "")).lower()
                    ]

                if sort_by == "Score ↑":
                    filtered = sorted(filtered, key=lambda x: x.get("score", 0))
                elif sort_by == "Type":
                    filtered = sorted(filtered, key=lambda x: x.get("content_type", ""))
                else:
                    filtered = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)

                st.markdown(f'<div style="color:rgba(148,163,184,0.6);font-size:0.8rem;margin-bottom:1rem;">Showing {len(filtered)} of {len(sources)} sources</div>', unsafe_allow_html=True)
                for i, source in enumerate(filtered, 1):
                    render_source_card(source, i)
            else:
                st.info("No sources found for this research job.")

        # ── Tab 4: Claims ─────────────────────────────────────────────────────
        with tab4:
            if claims:
                # Filters
                col1, col2 = st.columns(2)
                with col1:
                    min_conf = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
                with col2:
                    show_contested = st.checkbox("Show only contested", value=False)

                filtered_claims = [
                    c for c in claims
                    if c.get("confidence", 0) >= min_conf
                    and (not show_contested or c.get("is_contested", False))
                ]

                filtered_claims = sorted(filtered_claims, key=lambda c: c.get("confidence", 0), reverse=True)

                st.markdown(f'<div style="color:rgba(148,163,184,0.6);font-size:0.8rem;margin-bottom:1rem;">Showing {len(filtered_claims)} of {len(claims)} claims</div>', unsafe_allow_html=True)

                for claim in filtered_claims:
                    render_claim_card(claim)
                    if claim.get("verification_notes"):
                        with st.expander("📝 Verification notes"):
                            st.markdown(f'<div style="font-size:0.82rem;color:#94a3b8;">{claim["verification_notes"]}</div>', unsafe_allow_html=True)
            else:
                st.info("No claims verified for this research job.")

    elif status == "failed":
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.error("The research job failed. Common causes:")
        st.markdown("""
        - **LLM quota exhausted** — both Gemini and Groq quota hit simultaneously
        - **No search results** — Tavily key not configured and DuckDuckGo returned nothing
        - **Network error** — check your internet connection

        Try again with a **Quick** depth level or check your API keys in `.env`.
        """)
        error = status_data.get("errors", [])
        if error:
            with st.expander("Technical details"):
                for e in error:
                    st.code(e)
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("🔄 Try Again"):
            st.session_state.current_job_id = None
            st.session_state.show_results = False
            st.rerun()
