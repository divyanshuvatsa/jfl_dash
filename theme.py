"""Theme — colors, fonts, CSS. Polished dark mode (mirrors JCL aesthetic, JFL palette).

The JFL portfolio has 9 lenders (vs JCL's 3 active), so the lender palette is
expanded. Bucket / status colors stay aligned with the JCL theme so anyone
familiar with the reference dashboard reads the JFL view without re-learning.
"""

from __future__ import annotations


COLORS = {
    "bg_dark":     "#0B1426",
    "bg_card":     "#1A2540",
    "bg_subtle":   "#162136",
    "border":      "#1E3A5F",
    "border_subtle": "#2A3F66",
    "text":        "#F1F5F9",
    "text_dim":    "#94A3B8",
    "text_subtle": "#64748B",
    "accent":      "#3B82F6",
    "good":        "#10B981",
    "warn":        "#F59E0B",
    "bad":         "#EF4444",
    "info":        "#06B6D4",
    "purple":      "#8B5CF6",
    "magenta":     "#EC4899",
}


# All 9 JFL lenders — distinct, high-contrast on dark background.
LENDER_COLORS = {
    "UBI":              "#3B82F6",   # Royal blue (lead bank)
    "Indian Bank":      "#06B6D4",   # Cyan
    "RBL Bank":         "#F97316",   # Orange
    "YES Bank":         "#8B5CF6",   # Violet
    "IDFC First Bank":  "#10B981",   # Emerald
    "ICICI Bank":       "#EC4899",   # Magenta (WC)
    "HSBC":             "#94A3B8",   # Slate (uncommitted)
    "HDFC Bank":        "#F59E0B",   # Amber
    "ICICI Bank (TL)":  "#A855F7",   # Purple (takeover)
}


CATEGORY_COLORS = {
    "FB-Term":      "#3B82F6",   # Term loans
    "FB":           "#8B5CF6",   # WC fund-based
    "FB-FCY":       "#06B6D4",   # FX
    "FB-FDbacked":  "#10B981",   # FD-backed FB
    "NFB":          "#F59E0B",   # Non-fund-based
    "NFB-FDbacked": "#84CC16",
    "Hedge":        "#EC4899",
}


# Bucket colors used in KPI cards / stacked bars.
BUCKET_COLORS = {
    "1": "#3B82F6",   # FB Mains
    "2": "#F59E0B",   # NFB Mains
    "3": "#10B981",   # FD-Backed
    "4": "#94A3B8",   # Uncommitted
    "H": "#EC4899",   # Hedge memo
    "0": "#64748B",   # Sub-limit
}


STATUS_COLORS = {
    "Compliant":     "#10B981",
    "Watch":         "#3B82F6",
    "Near Breach":   "#F59E0B",
    "Breached":      "#EF4444",
    "Breach":        "#EF4444",
    "Pending Input": "#64748B",
    "Pending":       "#64748B",
}


SEVERITY_COLORS = {
    "Critical": "#EF4444",
    "High":     "#F59E0B",
    "Medium":   "#3B82F6",
    "Low":      "#10B981",
}


# Plotly default chart layout (dark)
CHART_LAYOUT = dict(
    plot_bgcolor="#0B1426",
    paper_bgcolor="#0B1426",
    font=dict(color="#F1F5F9", family="Inter, -apple-system, sans-serif"),
    margin=dict(l=20, r=20, t=20, b=40),
    transition=dict(duration=400, easing="cubic-in-out"),
)


CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

/* ─── Base ─────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.stApp {
    background: linear-gradient(180deg, #0B1426 0%, #0A1220 100%);
}

.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at 20% 0%, rgba(59,130,246,0.04), transparent 50%),
                radial-gradient(circle at 80% 100%, rgba(139,92,246,0.04), transparent 50%);
    pointer-events: none;
    z-index: 0;
}

/* ─── Sidebar ──────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F1A30 0%, #0B1426 100%);
    border-right: 1px solid #1E3A5F;
}

section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #F1F5F9;
    font-weight: 700;
    letter-spacing: -0.02em;
}

/* ─── Tabs ─────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: rgba(26,37,64,0.4);
    padding: 6px;
    border-radius: 14px;
    border: 1px solid #1E3A5F;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #94A3B8;
    border-radius: 10px;
    font-weight: 600;
    font-size: 0.95rem;
    padding: 10px 18px;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    border: 0;
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(59,130,246,0.10);
    color: #F1F5F9;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #3B82F6, #6366F1);
    color: white !important;
    box-shadow: 0 4px 12px rgba(59,130,246,0.35);
}

/* ─── Hero card ────────────────────────────────────────────────────── */
.hero-card {
    background: linear-gradient(135deg, #1A2540 0%, #162136 100%);
    border: 1px solid #1E3A5F;
    border-left: 5px solid var(--hero-color, #3B82F6);
    border-radius: 16px;
    padding: 24px 28px;
    margin: 16px 0 24px 0;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4),
                inset 0 1px 0 rgba(255,255,255,0.05);
    position: relative;
    overflow: hidden;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.hero-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 280px; height: 100%;
    background: radial-gradient(circle, var(--hero-color-faint, rgba(59,130,246,0.10)), transparent 70%);
    pointer-events: none;
}

.hero-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}

.hero-verdict {
    color: var(--hero-color, #3B82F6);
    font-size: 0.78rem;
    letter-spacing: 0.16em;
    font-weight: 800;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.hero-narrative {
    color: #F1F5F9;
    font-size: 1.05rem;
    font-weight: 500;
    line-height: 1.5;
}

/* ─── Tab section header ───────────────────────────────────────────── */
.tab-section-header {
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin: 32px 0 16px 0;
}

.tab-section-eyebrow {
    color: #3B82F6;
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    font-weight: 800;
    text-transform: uppercase;
}

.tab-section-title {
    color: #F1F5F9;
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0;
}

.tab-section-subtitle {
    color: #94A3B8;
    font-size: 0.88rem;
    margin-top: 2px;
}

/* ─── Big KPI cards ────────────────────────────────────────────────── */
.big-kpi-card {
    background: linear-gradient(180deg, #1A2540 0%, #162136 100%);
    border: 1px solid #1E3A5F;
    border-top: 3px solid var(--kpi-color, #3B82F6);
    border-radius: 12px;
    padding: 16px 18px;
    height: 100%;
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
}

.big-kpi-card::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0;
    height: 1px; width: 100%;
    background: linear-gradient(90deg, transparent, var(--kpi-color, #3B82F6), transparent);
    opacity: 0.5;
}

.big-kpi-card:hover {
    transform: translateY(-4px);
    border-color: var(--kpi-color, #3B82F6);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}

.big-kpi-label {
    color: #94A3B8;
    font-size: 0.72rem;
    letter-spacing: 0.10em;
    font-weight: 600;
    text-transform: uppercase;
    margin-bottom: 8px;
}

.big-kpi-value {
    color: #F1F5F9;
    font-size: 1.85rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
}

.big-kpi-sub {
    color: var(--kpi-color, #94A3B8);
    font-size: 0.78rem;
    font-weight: 500;
    margin-top: 6px;
}

/* ─── Insight / flag cards ─────────────────────────────────────────── */
.insight-card {
    background: #1A2540;
    border-left: 4px solid #3B82F6;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 12px;
    transition: transform 0.2s ease;
}

.insight-card:hover { transform: translateX(4px); }

.insight-card.warn   { border-left-color: #F59E0B; background: rgba(245,158,11,0.06); }
.insight-card.warning{ border-left-color: #F59E0B; background: rgba(245,158,11,0.06); }
.insight-card.bad    { border-left-color: #EF4444; background: rgba(239,68,68,0.06); }
.insight-card.good   { border-left-color: #10B981; background: rgba(16,185,129,0.06); }
.insight-card.info   { border-left-color: #06B6D4; background: rgba(6,182,212,0.04); }

.insight-title { color: #F1F5F9; font-weight: 700; font-size: 0.95rem; margin-bottom: 4px; }
.insight-body  { color: #CBD5E1; font-size: 0.85rem; line-height: 1.5; }

/* ─── Callouts ─────────────────────────────────────────────────────── */
.callout-good { background: rgba(16,185,129,0.10); border-left: 4px solid #10B981;
                padding: 14px 18px; border-radius: 10px; color: #6EE7B7; }
.callout-warn { background: rgba(245,158,11,0.10); border-left: 4px solid #F59E0B;
                padding: 14px 18px; border-radius: 10px; color: #FCD34D; }
.callout-bad  { background: rgba(239,68,68,0.10); border-left: 4px solid #EF4444;
                padding: 14px 18px; border-radius: 10px; color: #FCA5A5; }
.callout-info { background: rgba(59,130,246,0.10); border-left: 4px solid #3B82F6;
                padding: 14px 18px; border-radius: 10px; color: #93C5FD; }

/* ─── Buttons ──────────────────────────────────────────────────────── */
.stButton > button {
    background: #1A2540;
    border: 1px solid #1E3A5F;
    color: #F1F5F9;
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 0.9rem;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    background: #1E3A5F;
    border-color: #3B82F6;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(59,130,246,0.25);
}

.stButton > button:focus { box-shadow: 0 0 0 3px rgba(59,130,246,0.30); }

/* ─── Inputs / Selects ─────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div,
.stNumberInput > div > div > input {
    background: #162136 !important;
    color: #F1F5F9 !important;
    border: 1px solid #1E3A5F !important;
    border-radius: 8px !important;
}

/* ─── Sliders ──────────────────────────────────────────────────────── */
.stSlider > div > div > div > div { background: #3B82F6; }

/* ─── DataFrame ────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #1E3A5F;
    border-radius: 10px;
    overflow: hidden;
}

[data-testid="stDataFrame"] thead tr th {
    background: #162136 !important;
    color: #94A3B8 !important;
    font-weight: 700 !important;
    font-size: 0.78rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

/* ─── Metric ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: linear-gradient(180deg, #1A2540 0%, #162136 100%);
    border: 1px solid #1E3A5F;
    border-radius: 10px;
    padding: 12px 16px;
    transition: transform 0.2s ease;
}

[data-testid="stMetric"]:hover { transform: translateY(-2px); }

[data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 0.78rem !important;
                                  letter-spacing: 0.06em; font-weight: 600 !important; }
[data-testid="stMetricValue"] { color: #F1F5F9 !important; font-weight: 800 !important;
                                  font-size: 1.5rem !important; letter-spacing: -0.02em; }
[data-testid="stMetricDelta"] { font-size: 0.85rem !important; font-weight: 500 !important; }

/* ─── Radio ────────────────────────────────────────────────────────── */
.stRadio > div { gap: 8px; flex-wrap: wrap; }

.stRadio > div > label {
    background: #162136;
    border: 1px solid #1E3A5F;
    border-radius: 10px;
    padding: 6px 14px !important;
    margin: 0 !important;
    transition: all 0.2s ease;
    cursor: pointer;
}

.stRadio > div > label:hover {
    border-color: #3B82F6;
    background: rgba(59,130,246,0.08);
}

/* ─── Expander ─────────────────────────────────────────────────────── */
.streamlit-expanderHeader,
[data-testid="stExpander"] > details > summary {
    background: #162136 !important;
    border-radius: 10px !important;
    padding: 10px 16px !important;
    border: 1px solid #1E3A5F !important;
    color: #F1F5F9 !important;
    font-weight: 600;
}

.streamlit-expanderHeader:hover { border-color: #3B82F6 !important; }

/* ─── Plotly ───────────────────────────────────────────────────────── */
.js-plotly-plot {
    background: transparent !important;
    border-radius: 12px;
    transition: transform 0.3s ease;
}

/* ─── Scroll bar ───────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: #0B1426; }
::-webkit-scrollbar-thumb {
    background: #1E3A5F;
    border-radius: 6px;
    border: 2px solid #0B1426;
}
::-webkit-scrollbar-thumb:hover { background: #3B82F6; }

#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}

.hero-card, .big-kpi-card, .insight-card {
    animation: fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) backwards;
}

.big-kpi-card { animation-delay: 0.05s; }

button[data-testid="stNumberInputStepUp"],
button[data-testid="stNumberInputStepDown"] {
    background: #1A2540 !important;
    border: 1px solid #1E3A5F !important;
}

/* ─── JFL-specific: severity badges ────────────────────────────────── */
.severity-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.severity-critical { background: rgba(239,68,68,0.18); color: #FCA5A5; }
.severity-high     { background: rgba(245,158,11,0.18); color: #FCD34D; }
.severity-medium   { background: rgba(59,130,246,0.18); color: #93C5FD; }
.severity-low      { background: rgba(16,185,129,0.18); color: #6EE7B7; }

.mini-stat {
    display: inline-block;
    background: rgba(59,130,246,0.12);
    color: #93C5FD;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 600;
}

</style>
"""
