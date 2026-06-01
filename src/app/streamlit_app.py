# Ensure project root is on sys.path when run via `streamlit run src/app/streamlit_app.py`
import sys as _sys, pathlib as _pl
_root = str(_pl.Path(__file__).resolve().parents[2])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

"""Streamlit UI — Zomato AI Recommends.

Design system based on Google Stitch output (stitch_zomato_ai_recommends.zip).

Run:
    streamlit run src/app/streamlit_app.py
    MOCK_LLM=1 streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import logging
import os
from typing import List

import streamlit as st
from dotenv import load_dotenv

from src.app.forms import parse_extras, validate_form
from src.data.ingest import load_catalog
from src.models.preferences import UserPreferences
from src.models.restaurant import Restaurant
from src.recommendation.cache import ResponseCache, build_cache
from src.recommendation.contracts import PipelineRequest, PipelineResponse
from src.recommendation.orchestrator import RecommendationOrchestrator

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Zomato AI Recommends",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Stitch design tokens — injected as CSS custom properties
# ---------------------------------------------------------------------------

STITCH_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap');

/* ── Stitch color tokens ─────────────────────────────────────────── */
:root {
    --primary:                #b7122a;
    --primary-container:      #db313f;
    --primary-fixed:          #ffdad8;
    --primary-fixed-dim:      #ffb3b1;
    --on-primary:             #ffffff;
    --on-primary-fixed:       #410007;
    --surface:                #fbf9f8;
    --surface-bright:         #fbf9f8;
    --surface-dim:            #dbdad9;
    --surface-container:      #efeded;
    --surface-container-low:  #f5f3f3;
    --surface-container-high: #e9e8e7;
    --surface-container-highest: #e4e2e2;
    --on-surface:             #1b1c1c;
    --on-surface-variant:     #5b403f;
    --secondary:              #5f5e5e;
    --outline:                #8f6f6e;
    --outline-variant:        #e4bebc;
    --ai-start:               #b7122a;
    --ai-end:                 #7e22ce;
    --radius:                 1rem;
    --radius-lg:              2rem;
    --radius-full:            9999px;
}

/* ── Global font override ────────────────────────────────────────── */
html, body, .stApp, [class*="st-"], .stMarkdown, p, h1, h2, h3, label,
button, input, select, textarea, div, span {
    font-family: 'Montserrat', sans-serif !important;
}

/* ── Page background ─────────────────────────────────────────────── */
.stApp, .main .block-container {
    background-color: var(--surface) !important;
}
.main .block-container {
    padding-top: 0.5rem !important;
    max-width: 960px !important;
}

/* ── Hide default Streamlit chrome ──────────────────────────────── */
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }

/* ── Sidebar ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--surface-container-low) !important;
    border-right: 1px solid var(--outline-variant) !important;
}
[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--primary) !important;
    font-size: 18px !important;
    font-weight: 700 !important;
    margin-bottom: 0.25rem;
}

/* ── Primary button ─────────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background-color: var(--primary) !important;
    color: var(--on-primary) !important;
    border: none !important;
    border-radius: var(--radius-full) !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    padding: 0.65rem 1.5rem !important;
    transition: background 0.2s, transform 0.1s, box-shadow 0.2s !important;
    box-shadow: 0 4px 14px rgba(183, 18, 42, 0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: var(--primary-container) !important;
    box-shadow: 0 6px 20px rgba(183, 18, 42, 0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
}

/* ── Secondary button ───────────────────────────────────────────── */
.stButton > button:not([kind="primary"]) {
    background-color: transparent !important;
    color: var(--primary) !important;
    border: 1.5px solid var(--primary) !important;
    border-radius: var(--radius-full) !important;
    font-weight: 600 !important;
}
.stButton > button:not([kind="primary"]):hover {
    background-color: var(--primary-fixed) !important;
}

/* ── Form inputs ─────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input {
    border-radius: var(--radius) !important;
    border-color: var(--outline-variant) !important;
    background-color: #ffffff !important;
    font-family: 'Montserrat', sans-serif !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stSelectbox"] > div > div:focus-within {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(183, 18, 42, 0.15) !important;
}

/* ── Slider ─────────────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {
    background-color: var(--primary) !important;
}
[data-testid="stSlider"] [data-testid="stSliderTrack"] > div {
    background-color: var(--primary) !important;
}

/* ── Metric ─────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: var(--surface-container-low);
    border-radius: var(--radius);
    padding: 0.75rem 1rem;
    border: 1px solid var(--outline-variant);
}
[data-testid="stMetricValue"] {
    color: var(--primary) !important;
    font-weight: 700 !important;
}

/* ── Alerts ─────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
    font-family: 'Montserrat', sans-serif !important;
}

/* ── Divider ────────────────────────────────────────────────────── */
hr { border-color: var(--outline-variant) !important; }

/* ── Custom keyframes ─────────────────────────────────────────────── */
@keyframes glow {
    0%, 100% { box-shadow: 0 0 20px rgba(183, 18, 42, 0.2); }
    50%       { box-shadow: 0 0 40px rgba(183, 18, 42, 0.5); }
}
@keyframes spin-slow { to { transform: rotate(360deg); } }
@keyframes shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""

# ---------------------------------------------------------------------------
# Stitch loading screen (from code.html — adapted for inline Streamlit use)
# ---------------------------------------------------------------------------

def _loading_html(step: int) -> str:
    """
    Render the Stitch-designed loading state.
    step: 1=filtering, 2=asking AI, 3=ranking
    """
    check = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#dcfce7"/><path d="M7 13l3 3 7-7" stroke="#16a34a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    spinner = '<div style="width:32px;height:32px;border-radius:50%;border:2.5px solid rgba(183,18,42,0.2);border-top-color:#b7122a;animation:spin-slow 0.8s linear infinite;"></div>'
    dot = '<div style="width:32px;height:32px;border-radius:50%;background:#efeded;display:flex;align-items:center;justify-content:center;"><div style="width:8px;height:8px;border-radius:50%;background:#5f5e5e;opacity:0.4;"></div></div>'

    def step_row(label, state, bold=False):
        if state == "done":
            icon = check
            style = "color:#1b1c1c;"
        elif state == "active":
            icon = spinner
            style = "color:#1b1c1c; font-weight:700;"
        else:
            icon = dot
            style = "color:#1b1c1c; opacity:0.4;"
        return f"""
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px;">
            {icon}
            <span style="font-family:'Montserrat',sans-serif;font-size:16px;{style}">{label}</span>
        </div>"""

    rows = [
        step_row("Filtering restaurants…",              "done"   if step >= 1 else "pending", step >= 1),
        step_row("Asking AI for personalised picks…",   "active" if step == 2 else ("done" if step > 2 else "pending")),
        step_row("Ranking and sorting results…",        "active" if step == 3 else "pending"),
    ]

    return f"""
    <div style="
        display:flex;flex-direction:column;align-items:center;justify-content:center;
        padding:2rem 1rem;font-family:'Montserrat',sans-serif;
    ">
        <!-- Animated Orb -->
        <div style="position:relative;margin-bottom:2rem;">
            <div style="
                width:140px;height:140px;border-radius:50%;
                background:linear-gradient(135deg,rgba(183,18,42,0.15),rgba(126,34,206,0.15),rgba(37,99,235,0.15));
                display:flex;align-items:center;justify-content:center;
                animation:glow 2s infinite ease-in-out;
                backdrop-filter:blur(12px);
                border:1px solid rgba(255,255,255,0.3);
            ">
                <svg width="72" height="72" viewBox="0 0 24 24" fill="none">
                    <defs>
                        <linearGradient id="aigrad" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#b7122a"/>
                            <stop offset="100%" stop-color="#7e22ce"/>
                        </linearGradient>
                    </defs>
                    <path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"
                          fill="url(#aigrad)" opacity="0.9"/>
                    <path d="M12 6l1.5 4.5H18l-3.8 2.8 1.5 4.5L12 15l-3.7 2.8 1.5-4.5L6 10.5h4.5z"
                          fill="url(#aigrad)"/>
                </svg>
            </div>
            <!-- Orbit ring -->
            <div style="
                position:absolute;inset:-24px;
                border:1px solid rgba(183,18,42,0.15);border-radius:50%;
                animation:spin-slow 10s linear infinite;
            ">
                <div style="
                    width:12px;height:12px;border-radius:50%;
                    background:#b7122a;
                    box-shadow:0 0 10px #b7122a;
                    position:absolute;top:0;left:50%;transform:translateX(-50%);
                "></div>
            </div>
        </div>

        <!-- Card -->
        <div style="
            width:100%;max-width:440px;
            background:rgba(255,255,255,0.92);
            backdrop-filter:blur(12px);
            border-radius:1.5rem;
            padding:1.5rem 2rem;
            box-shadow:0 8px 32px rgba(0,0,0,0.08);
            border:1px solid rgba(228,190,188,0.4);
        ">
            <h2 style="text-align:center;font-size:22px;font-weight:800;color:#1b1c1c;margin:0 0 6px;">
                Curating Your Experience
            </h2>
            <p style="text-align:center;font-size:14px;color:#5f5e5e;margin:0 0 1.25rem;">
                Our AI is analyzing thousands of local spots just for you.
            </p>
            {''.join(rows)}
        </div>

        <!-- Did you know pill -->
        <div style="margin-top:1.75rem;text-align:center;">
            <div style="
                display:inline-flex;align-items:center;gap:6px;
                background:#ffdad8;color:#410007;
                border-radius:9999px;padding:4px 14px;
                font-size:13px;font-weight:700;margin-bottom:8px;
            ">💡 Did you know?</div>
            <p style="font-size:14px;color:#5f5e5e;font-style:italic;max-width:360px;margin:0 auto;">
                "Honey is the only food that doesn't spoil — archaeologists found
                3,000-year-old edible honey in Egyptian tombs."
            </p>
        </div>
    </div>
    <style>
        @keyframes glow {{
            0%,100% {{ box-shadow:0 0 20px rgba(183,18,42,0.2); }}
            50%      {{ box-shadow:0 0 40px rgba(183,18,42,0.5); }}
        }}
        @keyframes spin-slow {{ to {{ transform:rotate(360deg); }} }}
    </style>
    """

# ---------------------------------------------------------------------------
# Custom header (branded, matches Stitch nav bar)
# ---------------------------------------------------------------------------

def _render_header(catalog_size: int = 0) -> None:
    groq_ok = bool(os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY"))
    mock_mode = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")

    if mock_mode:
        groq_badge = '<span style="background:#fef9c3;color:#713f12;border-radius:9999px;padding:3px 10px;font-size:12px;font-weight:600;">⚠ Offline mode</span>'
    elif groq_ok:
        groq_badge = '<span style="background:#dcfce7;color:#14532d;border-radius:9999px;padding:3px 10px;font-size:12px;font-weight:600;">✓ AI ready</span>'
    else:
        groq_badge = '<span style="background:#fee2e2;color:#7f1d1d;border-radius:9999px;padding:3px 10px;font-size:12px;font-weight:600;">✗ No API key</span>'

    catalog_badge = f'<span style="background:#ffdad8;color:#410007;border-radius:9999px;padding:3px 10px;font-size:12px;font-weight:600;">🍴 {catalog_size:,} restaurants</span>' if catalog_size else ""

    st.markdown(f"""
    <div style="
        display:flex;justify-content:space-between;align-items:center;
        padding:0.85rem 0;
        border-bottom:1px solid var(--outline-variant);
        margin-bottom:1.25rem;
    ">
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:22px;">🍽️</span>
            <span style="
                font-family:'Montserrat',sans-serif;
                font-size:20px;font-weight:800;
                background:linear-gradient(135deg,#b7122a,#7e22ce);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            ">Zomato AI Recommends</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
            {catalog_badge}
            {groq_badge}
        </div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Result card (matches Stitch card design)
# ---------------------------------------------------------------------------

def _render_card(index: int, rec, *, is_fallback: bool) -> None:
    fallback_badge = ""
    if is_fallback:
        fallback_badge = '<span style="background:#fef9c3;color:#713f12;border-radius:9999px;padding:2px 8px;font-size:11px;font-weight:600;margin-left:8px;">Ranked by ★</span>'

    explanation_bg = "linear-gradient(135deg,rgba(183,18,42,0.04),rgba(126,34,206,0.04))"
    ai_badge = "" if is_fallback else '<span style="background:linear-gradient(135deg,#b7122a,#7e22ce);color:#fff;border-radius:9999px;padding:2px 8px;font-size:11px;font-weight:700;">✦ AI</span>'

    st.markdown(f"""
    <div style="
        background:#ffffff;
        border-radius:1.25rem;
        padding:1.25rem 1.5rem;
        box-shadow:0 2px 12px rgba(0,0,0,0.07);
        border:1px solid var(--outline-variant);
        margin-bottom:1rem;
        animation:fadeInUp 0.4s ease {index * 0.08:.2f}s both;
        font-family:'Montserrat',sans-serif;
    ">
        <!-- Header row -->
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.75rem;">
            <div style="display:flex;align-items:center;gap:10px;">
                <div style="
                    width:34px;height:34px;border-radius:50%;
                    background:var(--primary);color:#fff;
                    display:flex;align-items:center;justify-content:center;
                    font-size:14px;font-weight:800;flex-shrink:0;
                ">{index}</div>
                <span style="font-size:17px;font-weight:800;color:var(--on-surface);">
                    {rec.restaurant_name}
                </span>
                {fallback_badge}
            </div>
            <span style="
                background:var(--primary-fixed);color:var(--on-primary-fixed);
                border-radius:9999px;padding:4px 12px;
                font-size:12px;font-weight:700;white-space:nowrap;
            ">{rec.cuisine}</span>
        </div>

        <!-- Metrics row -->
        <div style="display:flex;gap:1.25rem;margin-bottom:0.85rem;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:5px;">
                <span style="color:#f59e0b;font-size:16px;">★</span>
                <span style="font-size:15px;font-weight:700;color:var(--on-surface);">{rec.rating:.1f}</span>
            </div>
            <div style="display:flex;align-items:center;gap:4px;">
                <span style="font-size:13px;color:var(--secondary);">Cost for two</span>
                <span style="font-size:15px;font-weight:700;color:var(--on-surface);">₹{rec.estimated_cost:,.0f}</span>
            </div>
        </div>

        <!-- AI explanation -->
        <div style="
            background:{explanation_bg};
            border-left:3px solid {'#b7122a' if not is_fallback else '#d97706'};
            border-radius:0 0.75rem 0.75rem 0;
            padding:0.65rem 0.85rem;
            display:flex;gap:8px;align-items:flex-start;
        ">
            <div style="flex-shrink:0;padding-top:2px;">{ai_badge if not is_fallback else '📊'}</div>
            <span style="font-size:14px;color:var(--on-surface-variant);font-style:italic;line-height:1.5;">
                {rec.explanation}
            </span>
        </div>
    </div>
    <style>
        @keyframes fadeInUp {{
            from {{ opacity:0; transform:translateY(14px); }}
            to   {{ opacity:1; transform:translateY(0); }}
        }}
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Welcome screen
# ---------------------------------------------------------------------------

def _render_welcome(catalog_size: int) -> None:
    steps = [
        ("🔍", "Filter",   "We narrow the full catalog to relevant matches"),
        ("🤖", "AI Rank",  "Groq AI ranks picks with personalised explanations"),
        ("✨", "Discover", "Top matches with ratings, costs & reasons"),
    ]
    step_cards = "".join(
        '<div style="background:#fff;border-radius:1.25rem;padding:1.25rem 1rem;'
        'border:1px solid #e4bebc;width:clamp(160px,28%,200px);'
        'box-shadow:0 2px 8px rgba(0,0,0,0.05);">'
        f'<div style="font-size:28px;margin-bottom:0.5rem;">{emoji}</div>'
        f'<div style="font-weight:700;color:#1b1c1c;font-size:14px;margin-bottom:4px;">{step}</div>'
        f'<div style="font-size:12px;color:#5f5e5e;">{desc}</div>'
        '</div>'
        for emoji, step, desc in steps
    )
    catalog_str = f"{catalog_size:,}"

    st.markdown(f"""
    <div style="text-align:center;padding:2.5rem 1rem;font-family:'Montserrat',sans-serif;">
        <div style="font-size:52px;margin-bottom:0.75rem;">🍽️</div>
        <h1 style="
            font-size:clamp(24px,4vw,40px);font-weight:800;
            background:linear-gradient(135deg,#b7122a,#7e22ce);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            margin-bottom:0.5rem;
        ">Find your perfect restaurant,<br>powered by AI</h1>
        <p style="font-size:16px;color:#5f5e5e;margin-bottom:2rem;">
            Tell us what you want. We'll handle the rest.
        </p>
        <div style="display:flex;gap:1.25rem;justify-content:center;flex-wrap:wrap;
                    max-width:700px;margin:0 auto 2rem;">
            {step_cards}
        </div>
        <div style="display:inline-flex;align-items:center;gap:8px;
                    background:var(--primary-fixed);color:var(--on-primary-fixed);
                    border-radius:9999px;padding:8px 20px;font-size:13px;font-weight:600;">
            🍴 Searching across {catalog_str}+ restaurants in India
        </div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

def _render_empty_state(response: PipelineResponse) -> None:
    st.markdown("""
    <div style="text-align:center;padding:2rem 1rem;font-family:'Montserrat',sans-serif;">
        <div style="font-size:56px;margin-bottom:0.75rem;">🍽️</div>
        <h2 style="font-size:22px;font-weight:800;color:#1b1c1c;margin-bottom:0.5rem;">
            No restaurants matched your preferences
        </h2>
        <p style="color:#5f5e5e;font-size:15px;">Try adjusting your filters using the suggestions below.</p>
    </div>
    """, unsafe_allow_html=True)
    for hint in response.hints:
        st.info(hint)

# ---------------------------------------------------------------------------
# Results section header
# ---------------------------------------------------------------------------

def _render_results_header(response: PipelineResponse) -> None:
    if response.summary:
        st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,rgba(183,18,42,0.06),rgba(126,34,206,0.06));
            border:1px solid rgba(183,18,42,0.2);
            border-radius:1rem;padding:0.85rem 1.25rem;
            display:flex;gap:10px;align-items:center;margin-bottom:1rem;
            font-family:'Montserrat',sans-serif;
        ">
            <span style="font-size:18px;">✦</span>
            <span style="font-size:14px;font-weight:600;
                background:linear-gradient(135deg,#b7122a,#7e22ce);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                {response.summary}
            </span>
        </div>
        """, unsafe_allow_html=True)

    if response.used_fallback:
        st.warning("⚠️ Groq is unavailable or MOCK_LLM=1 — showing top matches ranked by rating.")

    count = response.shortlist_size
    label = f"Found **{count}** candidate{'s' if count != 1 else ''} · {len(response.recommendations)} recommendation{'s' if len(response.recommendations) != 1 else ''} · {response.latency_ms} ms"
    st.markdown(f"<p style='font-size:13px;color:#5f5e5e;margin-bottom:0.75rem;font-family:Montserrat,sans-serif;'>{label}</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Cached loaders and singletons
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_catalog() -> List[Restaurant]:
    return load_catalog()

@st.cache_data(show_spinner=False)
def _city_options(n: int) -> List[str]:
    catalog = _load_catalog()
    counts: dict[str, int] = {}
    for r in catalog:
        c = r.location.strip()
        if c and c != "Unknown":
            counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [c for c, _ in ranked[:30]]

_PIPELINE_CACHE: ResponseCache | None = build_cache()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Inject Stitch CSS
    st.markdown(STITCH_CSS, unsafe_allow_html=True)

    # Load catalog
    with st.spinner("Loading restaurant catalog…"):
        try:
            catalog = _load_catalog()
        except Exception as exc:
            logger.exception("Catalog load failed")
            st.error("Could not load the restaurant catalog. Run `python -m src.data.ingest` first.")
            with st.expander("Error details"):
                st.code(str(exc))
            return

    _render_header(len(catalog))

    cities = _city_options(len(catalog))
    default_city = "Bangalore" if "Bangalore" in cities else (cities[0] if cities else "")

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### Your Preferences")
        st.markdown("<p style='font-size:12px;color:#5f5e5e;margin-top:-8px;'>Set your dining filters below</p>", unsafe_allow_html=True)
        st.markdown("---")

        location_select = st.selectbox(
            "📍 Location",
            options=cities or [default_city],
            index=cities.index(default_city) if default_city in cities else 0,
        )
        location_custom = st.text_input(
            "Or type a custom location",
            placeholder="e.g. Koramangala",
            max_chars=100,
        )
        effective_location = location_custom.strip() or location_select

        budget = st.selectbox(
            "💰 Budget",
            options=["low", "medium", "high"],
            index=1,
            help="low ≤ ₹400 · medium ₹401–800 · high > ₹800",
        )
        cuisine = st.text_input(
            "🍜 Cuisine",
            value="North Indian",
            max_chars=100,
            help="e.g. Italian, Chinese, South Indian",
        )
        min_rating = st.slider(
            "⭐ Minimum rating",
            min_value=0.0, max_value=5.0, value=4.0, step=0.1,
        )
        extras_text = st.text_input(
            "✨ Extras (optional)",
            placeholder="family-friendly, outdoor, quick service",
        )
        max_results = st.slider("🎯 Max recommendations", 3, 10, 5)

        st.markdown("---")
        submitted = st.button("Find Restaurants →", type="primary", use_container_width=True)

        # System status
        st.markdown("<br>", unsafe_allow_html=True)
        groq_key = bool(os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY"))
        mock_mode = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes")
        st.markdown(f"""
        <div style="font-size:12px;color:#5f5e5e;font-family:Montserrat,sans-serif;">
            {"✅" if len(catalog) > 0 else "❌"} Catalog ({len(catalog):,} restaurants)<br>
            {"⚠️ Groq (offline)" if mock_mode else ("✅ Groq (ready)" if groq_key else "❌ Groq (no key)")}
        </div>
        """, unsafe_allow_html=True)

    # ── Main content ─────────────────────────────────────────────────────────
    if not submitted:
        _render_welcome(len(catalog))
        return

    # Validate
    errors, normalised_budget = validate_form(effective_location, cuisine, min_rating, budget, extras_text)
    if errors:
        for msg in errors:
            st.error(msg)
        return
    if normalised_budget is None:
        return

    # Build preferences
    try:
        prefs = UserPreferences(
            location=effective_location,
            budget=normalised_budget,
            cuisine=cuisine.strip(),
            min_rating=float(min_rating),
            extras=parse_extras(extras_text),
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    # ── Loading state (Stitch design) ────────────────────────────────────────
    loading_slot = st.empty()

    # Step 1: filtering
    loading_slot.markdown(_loading_html(1), unsafe_allow_html=True)

    # Run pipeline (step 2 shows while Groq call runs)
    loading_slot.markdown(_loading_html(2), unsafe_allow_html=True)

    try:
        orchestrator = RecommendationOrchestrator(catalog=catalog, cache=_PIPELINE_CACHE)
        request = PipelineRequest(preferences=prefs, max_recommendations=max_results)
        response = orchestrator.run(request)
    except Exception as exc:
        loading_slot.empty()
        logger.exception("Orchestrator error")
        st.error("Something went wrong. Check your `GROQ_API_KEY` in `.env` or set `MOCK_LLM=1`.")
        with st.expander("Error details"):
            st.code(str(exc))
        return

    # Step 3: ranking done
    loading_slot.markdown(_loading_html(3), unsafe_allow_html=True)
    loading_slot.empty()

    # ── Render results ───────────────────────────────────────────────────────
    if response.filter_code != "OK":
        _render_empty_state(response)
        return

    if not response.recommendations:
        st.warning("No recommendations could be generated. Try adjusting your preferences.")
        return

    _render_results_header(response)
    for i, rec in enumerate(response.recommendations, 1):
        _render_card(i, rec, is_fallback=response.used_fallback)


if __name__ == "__main__":
    main()
