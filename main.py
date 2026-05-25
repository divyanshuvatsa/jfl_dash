"""
JFL Debt Monitoring Dashboard - Streamlit entry point.

Run locally:        streamlit run main.py
Cloud deployment:   point Streamlit Cloud at this file.
"""

from __future__ import annotations
import warnings
import streamlit as st

# Page config FIRST (must precede any other st call)
st.set_page_config(
    page_title="JFL Debt Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "JFL Debt Monitoring Dashboard.",
    },
)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
warnings.filterwarnings("ignore", category=FutureWarning)

# Apply custom CSS
from theme import CUSTOM_CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ─── Boot the data layer ───────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load(_signature: str):
    """Cache-friendly wrapper around the loader. Signature changes invalidate cache."""
    from data_loader import load_all_data
    return load_all_data()


def _get_data():
    from data_loader import get_excel_path, file_signature
    sig = file_signature(get_excel_path())
    return _load(sig)


# ─── Load data ─────────────────────────────────────────────────────────
try:
    data = _get_data()
except FileNotFoundError as e:
    st.error(f"❌ {e}")
    st.info("Place **JFL_Debt_Model_Final.xlsx** in the project root, or upload it from the sidebar.")
    st.stop()
except Exception as e:
    st.error(f"Error loading JFL Excel: {e}")
    import traceback
    st.code(traceback.format_exc())
    st.stop()

if not data.get("excel_exists"):
    st.error(f"⚠️ JFL Excel not found at {data.get('excel_path')}")
    st.info("Upload it from the sidebar or place it at the project root.")
    st.stop()


# ─── Sidebar + Header ──────────────────────────────────────────────────
from dashboard_ui import (
    render_sidebar, render_header,
    render_tab_overview, render_tab_covenants,
    render_tab_repayment, render_tab_renewals,
    render_tab_ai, render_tab_export, render_tab_snapshots,
)

controls = render_sidebar(data)
render_header(data)


# ─── 5 main tabs ───────────────────────────────────────────────────────
tab_overview, tab_covenants, tab_schedule, tab_ai, tab_tools = st.tabs([
    "Overview",
    "Covenants",
    "Schedule",
    "AI Analyst",
    "Tools",
])


# ─── TAB 1 - Overview ──────────────────────────────────────────────────
with tab_overview:
    render_tab_overview(data, controls)


# ─── TAB 2 - Covenants ─────────────────────────────────────────────────
with tab_covenants:
    render_tab_covenants(data, controls)


# ─── TAB 3 - Schedule (Repayment + Renewals) ──────────────────────────
with tab_schedule:
    sub = st.radio("Section",
                    ["Repayment Profile",
                     "Renewals & Calendar"],
                    horizontal=True, key="schedule_subnav",
                    label_visibility="collapsed")
    if sub == "Repayment Profile":
        render_tab_repayment(data, controls)
    else:
        render_tab_renewals(data, controls)


# ─── TAB 4 - AI Analyst ────────────────────────────────────────────────
with tab_ai:
    render_tab_ai(data, controls)


# ─── TAB 5 - Tools ─────────────────────────────────────────────────────
with tab_tools:
    sub = st.radio("Section",
                    ["Export / Reports",
                     "Snapshots"],
                    horizontal=True, key="tools_subnav",
                    label_visibility="collapsed")
    if sub == "Export / Reports":
        render_tab_export(data, controls)
    else:
        render_tab_snapshots(data, controls)


# ─── Footer ────────────────────────────────────────────────────────────
import pandas as pd
st.markdown(f"""
<div style='margin-top:40px;padding-top:20px;border-top:1px solid #1E293B;
            text-align:center;color:#64748B;font-size:0.78rem;'>
    JFL Debt Monitor &middot; As of {pd.Timestamp(data['as_of_date']).strftime('%d-%b-%Y')} &middot;
    Confidential - Treasury / Senior Management
</div>
""", unsafe_allow_html=True)
