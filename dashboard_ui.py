"""Dashboard UI for JFL — sidebar + 5 tabs (Overview, Covenants, Schedule, AI, Tools).

Mirrors the JCL reference architecture, adapted for:
  - 9 lenders (vs JCL's 3 active)
  - 5-bucket framework (B1 / B2 / B3 / B4 / Hedge memo, plus B0 sub-limits)
  - 7 term loans (vs 3)
  - FY29 TEV-projected covenant compliance (43/44 Compliant + 1 Near Breach)
  - 18 Management Flags + 108-check Validation & Integrity
"""

from __future__ import annotations
from typing import Dict, Any
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from theme import LENDER_COLORS, STATUS_COLORS, CHART_LAYOUT, SEVERITY_COLORS
from scenario_engine import resolve_covenants, recompute_interest, run_scenario
import rule_based_ai as rba
import gemini_analyst as gem
from visualizations import (
    render_covenant_headroom_chart, render_facility_cost_chart,
    render_fb_rate_vs_wac_chart, render_lender_composition_stacked,
    render_repayment_timeline, render_renewal_timeline,
    render_scenario_comparison_chart, render_tev_trajectory,
    render_bucket_donut,
)


# ─── HTML helper ───────────────────────────────────────────────────────
def _html(s: str) -> str:
    """Strip leading whitespace — prevents Streamlit's markdown parser from
    treating 4-space-indented HTML as a code block."""
    return "\n".join(line.lstrip() for line in s.strip().splitlines())


def md(s: str):
    st.markdown(_html(s), unsafe_allow_html=True)


# ─── Formatters ────────────────────────────────────────────────────────
def inr(v, d=1):
    if v is None or pd.isna(v): return "—"
    return f"₹{v:,.{d}f} Cr"


def pct(v, d=2):
    if v is None or pd.isna(v): return "—"
    return f"{v*100:.{d}f}%" if abs(v) < 5 else f"{v:.{d}f}%"


# ─── Building-block widgets ────────────────────────────────────────────
def render_hero(verdict, color, narrative):
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    faint = f"rgba({r},{g},{b},0.10)"
    st.markdown(_html(f"""<div class='hero-card' style='--hero-color:{color};--hero-color-faint:{faint};'>
        <div class='hero-verdict' style='--hero-color:{color};'>● {verdict}</div>
        <div class='hero-narrative'>{narrative}</div></div>"""), unsafe_allow_html=True)


def render_tab_header(label, title, subtitle=""):
    sub = f"<div class='tab-section-subtitle'>{subtitle}</div>" if subtitle else ""
    st.markdown(_html(f"""<div class='tab-section-header'>
        <div>
          <div class='tab-section-eyebrow'>{label}</div>
          <div class='tab-section-title'>{title}</div>
          {sub}
        </div>
    </div>"""), unsafe_allow_html=True)


def render_big_kpi(label, value, sub="", color="#F1F5F9"):
    st.markdown(_html(f"""<div class='big-kpi-card' style='--kpi-color:{color};'>
        <div class='big-kpi-label'>{label}</div>
        <div class='big-kpi-value'>{value}</div>
        <div class='big-kpi-sub' style='color:{color};'>{sub}</div></div>"""), unsafe_allow_html=True)


# ─── Sidebar ───────────────────────────────────────────────────────────
def render_sidebar(data: Dict[str, Any]) -> Dict[str, Any]:
    with st.sidebar:
        st.markdown("""<div style='padding:16px 0;border-bottom:1px solid #334155;'>
            <h1 style='font-size:1.4rem;margin:0;'>📊 JFL Debt Monitor</h1>
            <p style='color:#94A3B8;font-size:0.78rem;margin:4px 0 0 0;'>Jindal Ferrous Limited</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("### 🔴 Live Excel Sync")
        if data.get("excel_exists"):
            st.caption(f"✅ Source: {data['excel_path'].split('/')[-1]}")
            st.caption(f"📅 Modified: {data['excel_mtime']}")
            st.caption(f"🔑 Hash: `{data['excel_signature'][:8]}…`")
        else:
            st.error("⚠️ Excel not found")

        uploaded = st.file_uploader("📤 Upload Updated Excel", type=["xlsx"],
                                     help="Replaces the bundled Excel. Changes apply instantly.",
                                     key="excel_upload")
        if uploaded is not None:
            file_id = getattr(uploaded, "file_id", uploaded.name + str(uploaded.size))
            if st.session_state.get("_last_processed_upload") != file_id:
                from data_loader import save_uploaded_excel, force_reload
                with st.spinner(f"💾 Saving {uploaded.name}..."):
                    save_uploaded_excel(uploaded.getbuffer())
                st.session_state["_last_processed_upload"] = file_id
                force_reload()
                st.success(f"✅ {uploaded.name} loaded. Refreshing…")
                st.rerun()
            else:
                st.caption(f"✓ Active: {uploaded.name}")

        if st.button("🔄 Reload from Excel", use_container_width=True):
            from data_loader import force_reload
            force_reload()
            st.session_state.pop("_last_processed_upload", None)
            st.rerun()

        with st.expander("📋 Data Provenance", expanded=False):
            st.markdown("""
**Live (from Excel each reload):**
- All 44 facility records
- 9 benchmark rates
- FY25 audit financials + FY29 TEV projections
- 44 active covenants (FY29 TEV projected)
- Repayment & Interest schedules (7 TLs)
- 5-bucket totals (B1/B2/B3/B4/Hedge) + B0 sub-limits
- 18 Management Flags
- 108 Validation & Integrity checks (24 cross-source + 84 internal VJF)

**Edit the Excel → Reload → everything updates.**
""")

        st.markdown("---")
        st.markdown("### ⚙️ View Controls")

        basis = st.radio(
            "Financial Basis",
            options=["FY29E (TEV)", "FY25A"],
            index=0, horizontal=True, key="basis_input",
            help=("FY29E (TEV): post-COD TEV-projected financials (used for "
                  "covenant testing — 43/44 Compliant). "
                  "FY25A: pre-COD audit baseline financials.")
        )

        st.markdown("### 🔬 Scenario Stress")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📈 Stress", use_container_width=True,
                          help="Excel preset: +100bps, +25bps spread, +10% util, -15% EBITDA, +10% debt"):
                st.session_state.update(rate_shock=100, spread_shock=25,
                                          util_change=10,
                                          ebitda_change=-15, debt_change=10)
            if st.button("⛈ Severe", use_container_width=True,
                          help="Excel preset: +200bps, +50bps spread, +20% util, -30% EBITDA, +25% debt"):
                st.session_state.update(rate_shock=200, spread_shock=50,
                                          util_change=20,
                                          ebitda_change=-30, debt_change=25)
        with c2:
            if st.button("📉 EBITDA -20%", use_container_width=True):
                st.session_state.update(rate_shock=0, spread_shock=0,
                                          util_change=0,
                                          ebitda_change=-20, debt_change=0)
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.update(rate_shock=0, spread_shock=0,
                                          util_change=0,
                                          ebitda_change=0, debt_change=0)

        for k, default in [("rate_shock", 0), ("spread_shock", 0),
                            ("util_change", 0),
                            ("ebitda_change", 0), ("debt_change", 0)]:
            if k not in st.session_state:
                st.session_state[k] = default

        rate_shock    = st.slider("Rate Shock (bps)",       -100, 300, step=25, key="rate_shock")
        spread_shock  = st.slider("Spread Shock (bps)",        0, 200, step=25, key="spread_shock")
        util_change   = st.slider("Utilisation Change (%)",    0,  30, step=5,  key="util_change",
                                    help="Applied to Bucket 1 (drawable FB economic debt).")
        ebitda_change = st.slider("EBITDA Change (%)",       -40,  30, step=5,  key="ebitda_change")
        debt_change   = st.slider("Debt Change (%)",           0,  50, step=5,  key="debt_change")

        is_stressed = any([rate_shock, spread_shock, util_change, ebitda_change, debt_change])
        if is_stressed:
            st.markdown(_html(f"""<div class='callout-warn'>
                ⚠️ <b>Stress Active</b><br>
                Rate {rate_shock:+d}bps · Spread {spread_shock:+d}bps · Util {util_change:+d}% ·
                EBITDA {ebitda_change:+d}% · Debt {debt_change:+d}%
            </div>"""), unsafe_allow_html=True)

    # Live market rates (outside main sidebar block)
    try:
        from market_rates import render_market_rates_sidebar
        render_market_rates_sidebar()
    except Exception:
        pass

    return {
        "basis": basis,
        "rate_shock": rate_shock,
        "spread_shock": spread_shock,
        "util_change": util_change,
        "ebitda_change": ebitda_change,
        "debt_change": debt_change,
        "is_stressed": is_stressed,
    }


# ─── Header ────────────────────────────────────────────────────────────
def render_header(data: Dict[str, Any]):
    c1, c2, c3 = st.columns([5, 2, 2])
    with c1:
        dcco_str = pd.Timestamp(data['dcco']).strftime('%d-%b-%Y') if data.get('dcco') else '—'
        st.markdown(_html(f"""<div style='background:linear-gradient(90deg, rgba(37,99,235,0.1) 0%, transparent 100%);
                                padding:16px 20px;border-radius:12px;border:1px solid #1E293B;'>
            <div style='font-size:1.7rem;font-weight:800;
                        background:linear-gradient(90deg,#60A5FA 0%,#C084FC 100%);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
                JFL Debt Monitoring Dashboard
            </div>
            <div style='color:#94A3B8;font-size:0.85rem;margin-top:4px;'>
                Jindal Ferrous Limited · 2.0 MTPA Greenfield Steel · Kalinga Nagar, Odisha ·
                As-of {pd.Timestamp(data['as_of_date']).strftime('%d-%b-%Y')} · DCCO {dcco_str}
            </div>
        </div>"""), unsafe_allow_html=True)
    with c2:
        st.markdown(_html(f"""<div style='background:#1E293B;border-radius:12px;padding:14px 18px;text-align:right;'>
            <div style='color:#94A3B8;font-size:0.7rem;text-transform:uppercase;'>FX Rate</div>
            <div style='color:#F1F5F9;font-size:1.3rem;font-weight:700;'>₹{data['fx_rate']:.2f}/USD</div>
        </div>"""), unsafe_allow_html=True)
    with c3:
        vs = data.get("validation_summary", {})
        ok = vs.get("Overall_Status", "—")
        ok_color = "#10B981" if "PASS" in str(ok) else "#EF4444"
        st.markdown(_html(f"""<div style='background:#1E293B;border-radius:12px;padding:14px 18px;text-align:right;'>
            <div style='color:#94A3B8;font-size:0.7rem;text-transform:uppercase;'>Validation</div>
            <div style='color:{ok_color};font-size:1.3rem;font-weight:700;'>{vs.get('Pass_Count','—')}/{vs.get('Total_Checks','—')} {ok}</div>
        </div>"""), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════
def render_tab_overview(data: Dict[str, Any], controls: Dict[str, Any]):
    cov_df = resolve_covenants(data, controls["basis"],
                                stress_active=controls["is_stressed"],
                                ebitda_change_pct=controls["ebitda_change"],
                                interest_change_pct=0,
                                debt_change_pct=controls["debt_change"])
    int_calc = recompute_interest(data["facility_master"], data["benchmark_rates"],
                                    controls["rate_shock"], controls["spread_shock"],
                                    controls.get("util_change", 0))

    t = data["totals"]
    isum = data["interest_summary"]

    compliant = (cov_df["Status"] == "Compliant").sum()
    breach    = (cov_df["Status"] == "Breached").sum()
    near      = (cov_df["Status"] == "Near Breach").sum()
    watch     = (cov_df["Status"] == "Watch").sum()
    pending   = (cov_df["Status"] == "Pending Input").sum()

    # ─── Hero verdict ──────────────────────────────────────────
    flags = data.get("management_flags", pd.DataFrame())
    open_high = len(flags[(flags["Severity"].isin(["High", "Critical"])) &
                            (flags["Status"].isin(["Open", "Open (linked F-01)"]))]) if len(flags) else 0
    if breach > 3:
        verdict, color = "PRE-COD WATCH", "#F59E0B"
        narrative = (f"On <b>{controls['basis']}</b> basis, <b>{breach} covenants</b> show as breached — "
                     f"reflecting pre-operational reality (EBITDA still negative at FY25). "
                     f"<b>{open_high}</b> high-severity Management Flags open. "
                     f"FY29 TEV projection reaches 43/44 compliant post-COD.")
    elif breach > 0 or near > 0:
        verdict, color = "MONITOR CLOSELY", "#F59E0B"
        narrative = (f"Sanctioned debt <b>{inr(t['Bucket1_Sanctioned_Debt'])}</b> · "
                     f"<b>{breach} breached</b>, <b>{near} near-breach</b>. "
                     f"Annual run-rate {inr(int_calc['Total'])}.")
    else:
        verdict, color = "HEALTHY", "#10B981"
        narrative = (f"Sanctioned debt <b>{inr(t['Bucket1_Sanctioned_Debt'])}</b> across 9 lenders "
                     f"(8 funded + HSBC uncommitted memo). "
                     f"Adjusted Consortium <b>{inr(t['Adjusted_Consortium'])}</b> (after ICICI ₹840 Cr takeover). "
                     f"Annual run-rate <b>{inr(int_calc['Total'])}</b> at WAC <b>{int_calc['Weighted_Avg_Cost']*100:.2f}%</b>. "
                     f"<b>{compliant}/{len(cov_df)} covenants compliant</b>.")
    render_hero(verdict, color, narrative)

    # ─── Five-bucket KPIs (row 1) ──────────────────────────────
    render_tab_header("AT A GLANCE", "Five-Bucket View",
                       "B1+B2 = Sanctioned Debt. B3 FD-backed tracked separately; B4 emptied after HSBC "
                       "reclassification to B1 per MP-13/F-18. "
                       "ICICI TL takeover ₹840 Cr reduces gross Sanctioned to Adjusted Consortium ₹3,826 Cr.")
    fm_count = len(data["facility_master"])
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_big_kpi("Sanctioned Debt", inr(t["Bucket1_Sanctioned_Debt"]),
                        f"B1 FB ₹{t['FB_Mains_B1']:,.0f} + B2 NFB ₹{t['NFB_Mains_B2']:,.0f}",
                        color="#3B82F6")
    with c2:
        render_big_kpi("Adjusted Consortium", inr(t["Adjusted_Consortium"]),
                        f"Sanctioned − ICICI TL Takeover ₹{t['ICICI_TL_Takeover']:,.0f}",
                        color="#8B5CF6")
    with c3:
        render_big_kpi("NFB Contingent", inr(t["NFB_Contingent"], 0),
                        f"B2 + sub-of-FB (off-B/S)",
                        color="#F59E0B")
    with c4:
        render_big_kpi("Annual Run-Rate", inr(int_calc["Total"]),
                        f"WAC {int_calc['Weighted_Avg_Cost']*100:.2f}% · {fm_count} facilities",
                        color="#10B981")

    # ─── Bucket KPIs (row 2) ──────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_big_kpi("FD-Backed (B3)", inr(t["FD_Backed_B3"], 0),
                        "Self-collateralised", color="#06B6D4")
    with c2:
        render_big_kpi("Uncommitted (B4)", inr(t["Uncommitted_B4"], 0),
                        "HSBC · bank discretion", color="#94A3B8")
    with c3:
        render_big_kpi("Hedge Memo", inr(t["Hedge_Memo"], 0),
                        "UBI Forward · out of buckets", color="#EC4899")
    with c4:
        ls = data["lender_summary"]
        ls_nz = ls[ls["Sanctioned_Debt"] > 0]
        top = ls_nz.loc[ls_nz["Sanctioned_Debt"].idxmax()]
        top_pct = top["Sanctioned_Debt"] / t["Bucket1_Sanctioned_Debt"] * 100
        render_big_kpi("Top Lender", f"{top_pct:.1f}%", top["Lender"],
                        color="#F59E0B" if top_pct > 35 else "#10B981")

    # ─── Health KPIs (row 3) ──────────────────────────────────
    render_tab_header("HEALTH", "Cost & Compliance",
                       "Live values reflect current sliders." if controls["is_stressed"]
                       else f"Base case ({controls['basis']} basis).")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        delta = int_calc["Total"] - isum["Total_Interest_Commission"]
        sub = f"Δ {delta:+.1f} vs base" if abs(delta) > 0.01 else f"WAC {int_calc['Weighted_Avg_Cost']*100:.2f}%"
        render_big_kpi("Annual Run-Rate", inr(int_calc["Total"]), sub,
                        color="#FBBF24" if int_calc["Weighted_Avg_Cost"] > 0.10 else "#F1F5F9")
    with c2:
        render_big_kpi("Weighted Avg Cost", pct(int_calc["Weighted_Avg_Cost"]),
                        "On B1 FB economic debt",
                        color="#FBBF24" if int_calc["Weighted_Avg_Cost"] > 0.10 else "#10B981")
    with c3:
        if breach + near > 0:
            status_color = "#EF4444" if breach > 5 else "#F59E0B"
        else:
            status_color = "#10B981"
        cov_sub = (f"{breach} breach · {near} near · {watch} watch · {pending} pending"
                   if (breach + near + watch + pending) > 0 else "All clear")
        render_big_kpi("Covenants", f"{compliant}/{len(cov_df)}", cov_sub, color=status_color)
    with c4:
        flags_open = len(flags[flags["Status"].isin(["Open", "Open (linked F-01)"])]) if len(flags) else 0
        render_big_kpi("Mgmt Flags Open", str(flags_open),
                        f"{open_high} high-severity",
                        color="#F59E0B" if open_high > 0 else "#10B981")

    # ─── Concentration & bucket donuts ────────────────────────
    render_tab_header("STRUCTURE", "Lender Concentration & Bucket Mix",
                       "Left: Sanctioned Debt (B1+B2) share per lender. "
                       "Right: total committed capital across all 5 buckets.")
    c1, c2 = st.columns([3, 2])
    with c1:
        ls_nz = data["lender_summary"][data["lender_summary"]["Sanctioned_Debt"] > 0]
        ls_nz = ls_nz.sort_values("Sanctioned_Debt", ascending=False)
        lender_colors = [LENDER_COLORS.get(l, "#94A3B8") for l in ls_nz["Lender"]]
        fig = go.Figure(data=[go.Pie(
            labels=ls_nz["Lender"], values=ls_nz["Sanctioned_Debt"],
            marker=dict(colors=lender_colors, line=dict(color="#0F172A", width=2)),
            hole=0.55, textinfo="label+percent",
            textfont=dict(color="white", size=10),
            hovertemplate="<b>%{label}</b><br>₹%{value:,.0f} Cr<br>%{percent}<extra></extra>",
        )])
        fig.update_layout(**CHART_LAYOUT, height=400, showlegend=False,
                           annotations=[dict(text=f"<b>₹{t['Bucket1_Sanctioned_Debt']:,.0f}</b><br>"
                                                  f"<span style='font-size:0.85rem;color:#94A3B8'>Cr Sanctioned</span>",
                                              x=0.5, y=0.5, font=dict(size=22, color="#F1F5F9"),
                                              showarrow=False)])
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        render_bucket_donut(data)

    # ─── Detailed table (collapsed) ───────────────────────────
    with st.expander("🔍 Detailed five-bucket breakdown by lender", expanded=False):
        ls = data["lender_summary"].copy()
        b3 = data["lender_bucket3"].copy()
        merged = ls.merge(b3[["Lender", "FD_Backed"]], on="Lender", how="left").fillna(0)
        show = merged.copy()
        for c in ["FB_Mains_B1", "NFB_Mains_B2", "Sanctioned_Debt", "NFB_Contingent", "FD_Backed"]:
            if c in show.columns:
                show[c] = show[c].apply(lambda x: f"₹{x:,.0f}")
        show["Pct_Sanctioned"] = (merged["Pct_Sanctioned"] * 100).apply(lambda x: f"{x:.1f}%")
        show.columns = [c.replace("_", " ") for c in show.columns]
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ─── Composition stacked ───────────────────────────────────
    render_tab_header("COMPOSITION", "Each Lender's Sanctioned Capacity Mix",
                       "How each lender's exposure splits across Term Loans, WC FB, and NFB umbrellas. "
                       "Bars sum to the headline ₹4,666 Cr Sanctioned Debt.")
    render_lender_composition_stacked(data)

    # ─── Cost contribution ────────────────────────────────────
    render_tab_header("COST", "Annual Cost Contribution by Facility",
                       "Where the ~₹375 Cr annual run-rate comes from. Blue = FB interest; "
                       "Amber = NFB commission. HSBC uncommitted excluded.")
    render_facility_cost_chart(data)

    # ─── FB rate vs WAC ───────────────────────────────────────
    render_tab_header("RATE", "FB Effective Rate vs Portfolio WAC",
                       "Apples-to-apples interest-rate comparison. NFB commission rates excluded.")
    render_fb_rate_vs_wac_chart(data)


# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — COVENANTS
# ═══════════════════════════════════════════════════════════════════════
def render_tab_covenants(data: Dict[str, Any], controls: Dict[str, Any]):
    cov_df = resolve_covenants(data, controls["basis"],
                                stress_active=controls["is_stressed"],
                                ebitda_change_pct=controls["ebitda_change"],
                                interest_change_pct=0,
                                debt_change_pct=controls["debt_change"])

    compliant = (cov_df["Status"] == "Compliant").sum()
    watch     = (cov_df["Status"] == "Watch").sum()
    near      = (cov_df["Status"] == "Near Breach").sum()
    breach    = (cov_df["Status"] == "Breached").sum()
    pending   = (cov_df["Status"] == "Pending Input").sum()

    # ─── Hero ─────────────────────────────────────────────
    if breach > 5:
        verdict, color = "PRE-COD STRUCTURAL BREACHES", "#F59E0B"
        narrative = (f"<b>{breach} covenants breached</b> on {controls['basis']} basis — "
                     f"reflects pre-operational reality (EBITDA still negative at FY25). "
                     f"Toggle basis to <b>FY29E (TEV)</b> in sidebar to see post-COD projection.")
    elif breach > 0:
        verdict, color = "ATTENTION REQUIRED", "#EF4444"
        narrative = f"<b>{breach} covenant(s)</b> breached. Lender dialogue needed."
    elif near > 0:
        verdict, color = "MONITOR CLOSELY", "#F59E0B"
        narrative = f"All compliant but <b>{near} near-breach</b>. Maintain buffer."
    else:
        verdict, color = "COVENANTS COMPLIANT", "#10B981"
        narrative = f"All <b>{len(cov_df)} covenants compliant</b> on {controls['basis']} basis."
    render_hero(verdict, color, narrative)

    # ─── Status mix ───────────────────────────────────────
    render_tab_header("STATUS MIX",
                       f"Covenant Status on {controls['basis']}",
                       f"Total {len(cov_df)} active covenants across 9 lenders.")
    c1, c2 = st.columns([2, 3])
    with c1:
        labels = ["Compliant", "Watch", "Near Breach", "Breached", "Pending Input"]
        values = [compliant, watch, near, breach, pending]
        pie_colors = ["#10B981", "#3B82F6", "#F59E0B", "#EF4444", "#64748B"]
        keep = [(l, v, c) for l, v, c in zip(labels, values, pie_colors) if v > 0]
        if keep:
            ll, vv, cc = zip(*keep)
            fig = go.Figure(data=[go.Pie(
                labels=ll, values=vv, hole=0.55,
                marker=dict(colors=cc, line=dict(color="#0F172A", width=2)),
                textinfo="label+value", textfont=dict(color="white", size=11),
            )])
            fig.update_layout(**CHART_LAYOUT, height=320, showlegend=False,
                                annotations=[dict(text=f"<b>{len(cov_df)}</b><br>"
                                                       f"<span style='font-size:0.8rem;color:#94A3B8'>covenants</span>",
                                                  x=0.5, y=0.5, font=dict(size=22, color="#F1F5F9"),
                                                  showarrow=False)])
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown(_html(f"""
        <div style='padding:14px 0;'>
            <div style='font-size:0.78rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;'>Compliance Rate</div>
            <div style='font-size:2rem;font-weight:800;color:#10B981;'>{compliant/len(cov_df)*100:.1f}%</div>
            <div style='color:#94A3B8;font-size:0.85rem;'>{compliant} of {len(cov_df)} covenants compliant</div>
        </div>
        <div style='padding:14px 0;border-top:1px solid #334155;'>
            <div style='font-size:0.78rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;'>First-Test Window</div>
            <div style='font-size:1.4rem;font-weight:700;color:#F1F5F9;'>FY29 (post-COD)</div>
            <div style='color:#CBD5E1;font-size:0.82rem;'>Consortium first formal test once plant is operational. IDFC tests from FY27 (2-yr earlier — flag F-04).</div>
        </div>
        <div style='padding:14px 0;border-top:1px solid #334155;'>
            <div style='font-size:0.78rem;color:#94A3B8;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;'>Basis Note</div>
            <div style='font-size:0.9rem;color:#CBD5E1;'>The verified Excel tracks covenants on the FY29 TEV-projected basis (post-COD). FY25 audit covenant testing is not separately maintained since most JFL covenants first test in FY27/FY29 (post-COD). Result: <b>43 of 44 Compliant + 1 Near Breach</b> (ICICI WC Rating).</div>
        </div>
        """), unsafe_allow_html=True)

    # ─── Headroom chart ──────────────────────────────────
    _hr = cov_df.copy()
    _hr["_HR"] = pd.to_numeric(_hr["Headroom_Pct"], errors="coerce")
    _hr_valid = _hr.dropna(subset=["_HR"])
    if len(_hr_valid):
        _tight = _hr_valid.loc[_hr_valid["_HR"].idxmin()]
        _binding = (f"<b>{_tight['Covenant']}</b> is the binding constraint at "
                     f"<b>{_tight['_HR']:+.0f}%</b> headroom ({_tight['Lender']}).")
    else:
        _binding = "No numeric headroom data available."

    render_tab_header("HEADROOM", "Binding Covenants — Tightest Instance per Ratio",
                       f"{_binding} Expand the audit view below for every instance.")
    render_covenant_headroom_chart(cov_df, mode="tightest")

    with st.expander("📋 Full audit view — all instances by lender", expanded=False):
        st.caption("Same data, broken out per lender. Useful for verifying no single lender's "
                    "threshold is being inadvertently relaxed.")
        render_covenant_headroom_chart(cov_df, mode="all")

    # ─── TEV forward (JFL-specific) ──────────────────────
    if controls["basis"] == "FY29E (TEV)" and not controls["is_stressed"]:
        render_tab_header("FORWARD LOOK", "TEV-Projected Trajectory (FY27 → FY38)",
                           "Forward path of the five binding ratios. JFL is pre-operational, "
                           "so future-year visibility matters for treasury planning.")
        render_tev_trajectory(data)

    # ─── Attention items ─────────────────────────────────
    attention = cov_df[cov_df["Status"].isin(["Breached", "Near Breach", "Watch"])]
    if len(attention) > 0:
        render_tab_header("ATTENTION", f"{len(attention)} Covenants Requiring Watch")
        for _, r in attention.head(20).iterrows():
            color = STATUS_COLORS.get(r["Status"], "#3B82F6")
            bg = {"Breached": "rgba(239,68,68,0.10)",
                   "Near Breach": "rgba(245,158,11,0.10)",
                   "Watch": "rgba(59,130,246,0.05)"}.get(r["Status"], "rgba(59,130,246,0.05)")
            actual_str = (f"{r['Actual']:.2f}x" if isinstance(r['Actual'], (int, float)) and pd.notna(r['Actual'])
                          else str(r['Actual'])[:30])
            thr_str = (f"{r['Operator']}{r['Threshold']:.2f}x"
                       if isinstance(r['Threshold'], (int, float))
                       else f"{r['Operator']}{r['Threshold']}")
            hr_str = (f"{r['Headroom_Pct']:+.1f}%"
                      if isinstance(r["Headroom_Pct"], (int, float)) and pd.notna(r["Headroom_Pct"])
                      else "—")
            st.markdown(_html(f"""<div style='background:{bg};border-left:4px solid {color};
                                  border-radius:12px;padding:14px 18px;margin-bottom:8px;'>
                <div style='display:flex;justify-content:space-between;'>
                    <div style='flex:1;'>
                        <div style='font-size:0.7rem;color:{color};text-transform:uppercase;font-weight:700;'>
                            {r['Status']} · {r['Lender']}
                        </div>
                        <div style='font-size:1.05rem;font-weight:700;color:#F1F5F9;margin:4px 0;'>{r['Covenant']}</div>
                        <div style='color:#CBD5E1;font-size:0.88rem;'>
                            Actual: <b>{actual_str}</b> · Threshold: {thr_str}
                        </div>
                    </div>
                    <div style='text-align:right;'>
                        <div style='font-size:0.7rem;color:#94A3B8;text-transform:uppercase;'>Headroom</div>
                        <div style='font-size:1.5rem;font-weight:800;color:{color};'>{hr_str}</div>
                    </div>
                </div>
            </div>"""), unsafe_allow_html=True)
        if len(attention) > 20:
            st.caption(f"… and {len(attention)-20} more — see full table below.")
    else:
        st.markdown("<div class='callout-good'><b>✅ All covenants well within thresholds.</b></div>",
                     unsafe_allow_html=True)

    # ─── Full per-lender table ────────────────────────────
    with st.expander("📋 All covenants by lender", expanded=False):
        for lender in sorted(cov_df["Lender"].unique()):
            sub = cov_df[cov_df["Lender"] == lender]
            st.markdown(f"#### {lender} ({len(sub)} covenants)")
            d = sub.copy()
            d["Actual_S"] = d["Actual"].apply(
                lambda x: f"{x:.4f}x" if isinstance(x, (int, float)) and pd.notna(x)
                else (str(x)[:25] if x is not None else "—"))
            d["Headroom_S"] = d["Headroom_Pct"].apply(
                lambda x: f"{x:+.1f}%" if isinstance(x, (int, float)) and pd.notna(x) else "—")
            d["Threshold_S"] = d.apply(
                lambda r: (f"{r['Operator']}{r['Threshold']:.2f}x"
                           if isinstance(r['Threshold'], (int, float))
                           else f"{r['Operator']}{r['Threshold']}" if pd.notna(r['Threshold']) else "—"),
                axis=1)
            d_show = d[["Covenant", "Threshold_S", "Actual_S", "Headroom_S", "Status"]].copy()
            d_show.columns = ["Covenant", "Threshold", "Actual", "Headroom", "Status"]
            st.dataframe(d_show, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — SCHEDULE (Repayment + Renewals + Mgmt Flags + Validation)
# ═══════════════════════════════════════════════════════════════════════
def render_tab_repayment(data: Dict[str, Any], controls: Dict[str, Any]):
    rep = data["repayment_schedule"].copy()
    if rep.empty:
        st.info("No repayment schedule available.")
        return

    fm = data["facility_master"]
    as_of = pd.Timestamp(data["as_of_date"])
    rep["FY"] = rep["Period_End"].dt.year + (rep["Period_End"].dt.month >= 4).astype(int)
    rep["FY_Label"] = "FY" + rep["FY"].astype(str).str[-2:]

    fy_agg = rep.groupby("FY_Label", sort=False).agg(
        UBI_I=("UBI_RTL_I_Principal", "sum"),
        UBI_II=("UBI_RTL_II_Principal", "sum"),
        IndianBank=("Indian_Bank_Principal", "sum"),
        RBL=("RBL_Principal", "sum"),
        YBL=("YBL_Principal", "sum"),
        IDFC=("IDFC_Principal", "sum"),
        ICICI_TL=("ICICI_TL_Principal", "sum"),
        Total_Prin=("Total_Principal", "sum"),
        Total_Int=("Total_Interest", "sum"),
        Total_DS=("Total_DS", "sum"),
    ).reset_index()

    next_12m = rep[rep["Period_End"].between(as_of, as_of + pd.Timedelta(days=365))]
    next_12m_ds = next_12m["Total_DS"].sum()

    tl_total_outstanding = fm[fm["Category"] == "FB-Term"]["Effective_OS"].sum()
    fy_active = fy_agg[fy_agg["Total_Prin"] > 0]

    # ─── Hero ───────────────────────────────────────────────────
    upcoming = fm[(fm["Validity_Date"] - as_of).dt.days.between(0, 60)]
    if len(upcoming) > 10:
        verdict, color = "RENEWALS DUE", "#F59E0B"
        narrative = (f"<b>{len(upcoming)} facilities</b> "
                     f"({inr(upcoming['Sanction_INR'].sum())}) need renewal in 60 days.")
    else:
        verdict, color = "ON TRACK", "#10B981"
        narrative = (f"Term-loan portfolio on structured 12-year amortisation path (FY27 → FY39). "
                     f"Next 12 months debt service: <b>{inr(next_12m_ds)}</b>.")
    render_hero(verdict, color, narrative)

    render_tab_header("LIQUIDITY", "Cash-Flow Obligations")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        n_tl = (fm["Category"] == "FB-Term").sum()
        n_drawn = ((fm["Category"] == "FB-Term") & (fm["Effective_OS"] > 0)).sum()
        render_big_kpi("TL Outstanding", inr(tl_total_outstanding, 0),
                        f"{n_drawn}/{n_tl} TLs drawn")
    with c2:
        prin_12m = next_12m["Total_Principal"].sum()
        int_12m = next_12m["Total_Interest"].sum()
        render_big_kpi("Next 12 Months", inr(next_12m_ds, 1),
                        f"P {inr(prin_12m, 0)} + I {inr(int_12m, 0)}")
    with c3:
        if len(fy_active):
            peak = fy_agg.loc[fy_agg["Total_DS"].idxmax()]
            render_big_kpi("Peak DS Year", peak["FY_Label"],
                            f"{inr(peak['Total_DS'])} (P+I)")
        else:
            render_big_kpi("Peak DS Year", "—", "")
    with c4:
        cov_df = resolve_covenants(data, controls["basis"],
                                     stress_active=controls["is_stressed"],
                                     ebitda_change_pct=controls["ebitda_change"],
                                     debt_change_pct=controls["debt_change"])
        dscr_rows = cov_df[cov_df["Covenant"].str.contains("DSCR", case=False, na=False) &
                             ~cov_df["Covenant"].str.contains("Cash Sweep", case=False, na=False)]
        if len(dscr_rows):
            dscr = dscr_rows.iloc[0]["Actual"]
            dscr_val = f"{dscr:.2f}x" if isinstance(dscr, (int, float)) and pd.notna(dscr) else "—"
            dscr_color = "#10B981" if isinstance(dscr, (int, float)) and dscr >= 1.5 else "#F59E0B"
        else:
            dscr_val, dscr_color = "—", "#94A3B8"
        render_big_kpi("DSCR", dscr_val, f"vs ≥1.25x · {controls['basis']}", color=dscr_color)

    # ─── TL maturity panel ─────────────────────────────────────
    tl_mat = fm[(fm["Category"] == "FB-Term") & fm["Maturity_Date"].notna() & (fm["Effective_OS"] > 0)]
    if len(tl_mat) > 0:
        earliest = tl_mat["Maturity_Date"].min()
        farthest = tl_mat["Maturity_Date"].max()
        e_row = tl_mat[tl_mat["Maturity_Date"] == earliest].iloc[0]
        f_row = tl_mat[tl_mat["Maturity_Date"] == farthest].iloc[0]
        # weighted-avg remaining life
        wal_days = ((tl_mat["Maturity_Date"] - as_of).dt.days * tl_mat["Effective_OS"]).sum()
        wal = (wal_days / tl_mat["Effective_OS"].sum() / 365) if tl_mat["Effective_OS"].sum() else 0

        render_tab_header("MATURITY", "Term-Loan Maturity Profile",
                           "Earliest = RBL bridge (12-month bullet). Farthest = consortium 12-year "
                           "amortisers maturing 31-Mar-2039.")
        m1, m2, m3 = st.columns(3)
        with m1:
            render_big_kpi("Earliest TL Maturity", earliest.strftime("%d-%b-%Y"),
                            f"{e_row['Lender']} TL", color="#EF4444")
        with m2:
            render_big_kpi("Farthest TL Maturity", farthest.strftime("%d-%b-%Y"),
                            f"{f_row['Lender']} TL", color="#3B82F6")
        with m3:
            render_big_kpi("Wtd Avg Remaining Life", f"{wal:.1f} yrs",
                            "Weighted by outstanding", color="#06B6D4")

    # ─── Annual debt service chart ──────────────────────────────
    # Excel's Total_Principal column EXCLUDES the RBL bullet (it's a 12-month
    # bridge that refinances, not a true amortising payment). So for the chart
    # we stack only the 6 amortising consortium TLs whose sum DOES equal
    # Total_Principal, and add the RBL bullet as a separately-coloured overlay
    # line so the viewer can see the bridge maturity event.
    render_tab_header("TIMELINE", "Annual Debt Service by Lender",
                       "Stacked bars = scheduled consortium TL principal (6 TLs). "
                       "RBL bullet bridge is overlaid in red as a one-off refinance event. "
                       "Line = total interest each FY. Repayments begin FY27.")
    fy_chart = fy_agg[(fy_agg["Total_Prin"] > 0) | (fy_agg["Total_Int"] > 0) |
                       (fy_agg["RBL"] > 0)].copy()
    if len(fy_chart):
        fig = go.Figure()
        # Stacked consortium TLs (these sum to Total_Principal — Excel's intent)
        bar_specs = [
            ("UBI_I",      "UBI RTL-I",   "#3B82F6"),
            ("UBI_II",     "UBI RTL-II",  "#60A5FA"),
            ("IndianBank", "Indian Bank", "#06B6D4"),
            ("YBL",        "YES Bank",    "#8B5CF6"),
            ("IDFC",       "IDFC First",  "#10B981"),
            ("ICICI_TL",   "ICICI TL",    "#A855F7"),
        ]
        for col, name, color in bar_specs:
            if col not in fy_chart.columns:
                continue
            if fy_chart[col].sum() <= 0:
                continue
            fig.add_trace(go.Bar(
                name=name, x=fy_chart["FY_Label"], y=fy_chart[col],
                marker_color=color, opacity=0.95,
                hovertemplate=f"<b>{name} Principal</b><br>%{{x}}: ₹%{{y:.2f}} Cr<extra></extra>",
            ))
        # RBL bullet — separate bar group to mark the one-off refinance
        if fy_chart["RBL"].sum() > 0:
            fig.add_trace(go.Bar(
                name="RBL Bridge bullet (refinance)",
                x=fy_chart["FY_Label"], y=fy_chart["RBL"],
                marker_color="#EF4444", opacity=0.85,
                hovertemplate="<b>RBL Bridge</b><br>%{x}: ₹%{y:.2f} Cr "
                              "(12-month bullet — assumed refinanced)<extra></extra>",
            ))
        # Interest overlay
        fig.add_trace(go.Scatter(
            name="Interest (all)", x=fy_chart["FY_Label"], y=fy_chart["Total_Int"],
            mode="lines+markers",
            line=dict(color="#F59E0B", width=2.5, dash="dot"),
            marker=dict(size=7, color="#F59E0B"),
            hovertemplate="<b>Interest</b><br>%{x}: ₹%{y:.2f} Cr<extra></extra>",
        ))
        # Total DS annotation — only on the consortium stack (matches Excel intent)
        for _, r in fy_chart.iterrows():
            if r["Total_DS"] > 0:
                fig.add_annotation(
                    x=r["FY_Label"], y=r["Total_DS"],
                    text=f"₹{r['Total_DS']:.0f}", showarrow=False, yshift=14,
                    font=dict(color="#F1F5F9", size=9, family="Inter, sans-serif"),
                )
        fig.update_layout(**CHART_LAYOUT, height=460, barmode="stack",
                           xaxis=dict(title="Financial Year", tickangle=-25),
                           yaxis=dict(title="Debt Service (₹ Cr)", gridcolor="#334155"),
                           legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.22,
                                        font=dict(color="#94A3B8")))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Numbers above bars = consortium total DS (P+I, excl. RBL bullet — per Excel methodology).")

    # ─── Cumulative run-down ───────────────────────────────────
    render_tab_header("RUNDOWN", "Term-Loan Outstanding Over Time",
                       "Stacked area: total TL outstanding by lender, decreasing as scheduled principal is paid.")
    render_repayment_timeline(data)

    # ─── Quarterly schedule table ──────────────────────────────
    with st.expander("📅 Full quarterly repayment schedule", expanded=False):
        rep_show = rep.copy()
        rep_show["Period"] = (rep_show["Period_End"].dt.strftime("%d-%b-%Y")
                                + " (" + rep_show["Period_Label"] + ")")
        rep_show = rep_show[(rep_show["Period_End"] >= as_of - pd.Timedelta(days=90))].head(40)
        cols = ["Period", "Total_Principal", "Total_Interest", "Total_DS", "Combined_OS"]
        for c in ["Total_Principal", "Total_Interest", "Total_DS", "Combined_OS"]:
            rep_show[c] = rep_show[c].apply(lambda x: f"{x:.2f}" if x > 0 else "—")
        rep_show.columns = [c.replace("_", " ") for c in rep_show.columns]
        cols_show = [c.replace("_", " ") for c in cols]
        st.dataframe(rep_show[cols_show], use_container_width=True, hide_index=True)

    # ─── Facility browser ──────────────────────────────────────
    with st.expander(f"🔍 Browse all {len(fm)} facilities", expanded=False):
        search = st.text_input("Search by lender / facility / category", "", key="fac_search_browser")
        df = fm.copy()
        if search:
            mask = (df["Facility"].str.contains(search, case=False, na=False) |
                    df["Lender"].str.contains(search, case=False, na=False) |
                    df["Category"].str.contains(search, case=False, na=False))
            df = df[mask]
        disp = df[["S_No", "Lender", "Facility", "Category", "Bucket",
                    "Sanction_INR", "Effective_OS", "Effective_Rate",
                    "Validity_Date", "Maturity_Date"]].copy()
        # Normalize Bucket to string — JFL mixes int (1-4) with "H" (hedge) and 0 (sub-limit).
        # pyarrow can't convert mixed-type object columns, so coerce to string for display.
        disp["Bucket"] = disp["Bucket"].astype(str)
        disp["Sanction_INR"]  = disp["Sanction_INR"].apply(lambda x: f"₹{x:,.1f}")
        disp["Effective_OS"]  = disp["Effective_OS"].apply(lambda x: f"₹{x:,.2f}")
        disp["Effective_Rate"]= disp["Effective_Rate"].apply(lambda x: f"{x*100:.2f}%" if x > 0 else "TBD")
        disp["Validity_Date"] = pd.to_datetime(disp["Validity_Date"]).dt.strftime("%d-%b-%Y")
        disp["Maturity_Date"] = pd.to_datetime(disp["Maturity_Date"]).dt.strftime("%d-%b-%Y").fillna("Revolving")
        disp.columns = ["S.No", "Lender", "Facility", "Cat", "Bkt",
                         "Sanc", "Eff O/S", "Rate", "Validity", "Maturity"]
        st.dataframe(disp, use_container_width=True, hide_index=True, height=400)


# ═══════════════════════════════════════════════════════════════════════
# TAB 3b — RENEWALS (called from same Schedule tab below repayment)
# ═══════════════════════════════════════════════════════════════════════
def render_tab_renewals(data: Dict[str, Any], controls: Dict[str, Any]):
    fm = data["facility_master"].copy()
    as_of = pd.Timestamp(data["as_of_date"])
    fm["days_to_expiry"] = (fm["Validity_Date"] - as_of).dt.days

    expired  = fm[fm["days_to_expiry"] < 0]
    next_30  = fm[fm["days_to_expiry"].between(0, 30)]
    next_60  = fm[fm["days_to_expiry"].between(31, 60)]
    next_90  = fm[fm["days_to_expiry"].between(61, 90)]
    next_180 = fm[fm["days_to_expiry"].between(91, 180)]
    later    = fm[fm["days_to_expiry"] > 180]

    total_urgent = len(expired) + len(next_30) + len(next_60)
    total_urgent_value = pd.concat([expired, next_30, next_60])["Sanction_INR"].sum() if total_urgent else 0

    if total_urgent > 10:
        verdict, color = "ACTION REQUIRED", "#EF4444"
        narrative = f"<b>{total_urgent} facilities</b> ({inr(total_urgent_value)}) overdue or ≤60 days."
    elif total_urgent > 0:
        verdict, color = "RENEWAL CYCLE", "#F59E0B"
        narrative = f"<b>{total_urgent} facilities</b> ({inr(total_urgent_value)}) need renewal soon."
    else:
        verdict, color = "NO IMMEDIATE ACTION", "#10B981"
        narrative = "No renewals required in next 60 days."
    render_hero(verdict, color, narrative)

    # ─── Filters ──────────────────────────────────────────────
    render_tab_header("FILTER", "Refine the View",
                       "Pick urgency bucket and lenders. Timeline + action list update together. "
                       "Sub-limits and Term Loans excluded from the renewal Gantt by default.")
    fc1, fc2 = st.columns([2, 3])
    with fc1:
        urgency_filter = st.radio(
            "Urgency Bucket",
            ["All", "Overdue", "≤30 days", "31-60 days", "61-90 days", "91-180 days", ">180 days"],
            key="renewal_urgency_filter",
        )
    with fc2:
        all_lenders = sorted(fm["Lender"].unique().tolist())
        selected_lenders = st.multiselect("Lenders", options=all_lenders, default=all_lenders,
                                            key="renewal_lender_filter")
        if not selected_lenders:
            st.caption("⚠ No lenders selected — defaulting to all.")
        st.markdown("##### KPIs (within filter)")

    filtered = fm.copy()
    if urgency_filter == "Overdue":
        filtered = filtered[filtered["days_to_expiry"] < 0]
    elif urgency_filter == "≤30 days":
        filtered = filtered[filtered["days_to_expiry"].between(0, 30)]
    elif urgency_filter == "31-60 days":
        filtered = filtered[filtered["days_to_expiry"].between(31, 60)]
    elif urgency_filter == "61-90 days":
        filtered = filtered[filtered["days_to_expiry"].between(61, 90)]
    elif urgency_filter == "91-180 days":
        filtered = filtered[filtered["days_to_expiry"].between(91, 180)]
    elif urgency_filter == ">180 days":
        filtered = filtered[filtered["days_to_expiry"] > 180]
    if selected_lenders:
        filtered = filtered[filtered["Lender"].isin(selected_lenders)]

    # ─── Bucket KPIs ──────────────────────────────────────────
    c0, c1, c2, c3, c4, c5 = st.columns(6)

    def _kpi_with_filter(col_ctx, label, df, color, key):
        is_active = (urgency_filter == key) or (urgency_filter == "All")
        opacity = "1.0" if is_active else "0.4"
        with col_ctx:
            count = len(df)
            value = df["Sanction_INR"].sum() if count else 0
            st.markdown(_html(f"""<div style='opacity:{opacity};background:#1E293B;
                border-left:4px solid {color};border-radius:8px;padding:12px;'>
                <div style='color:#94A3B8;font-size:0.7rem;letter-spacing:0.08em;'>{label}</div>
                <div style='color:#F1F5F9;font-size:1.5rem;font-weight:700;'>{count}</div>
                <div style='color:{color};font-size:0.78rem;'>{f"₹{value:,.1f} Cr" if count else "—"}</div></div>"""), unsafe_allow_html=True)

    _kpi_with_filter(c0, "Overdue", expired, "#7F1D1D", "Overdue")
    _kpi_with_filter(c1, "≤30 days", next_30, "#EF4444", "≤30 days")
    _kpi_with_filter(c2, "31-60 days", next_60, "#F59E0B", "31-60 days")
    _kpi_with_filter(c3, "61-90 days", next_90, "#3B82F6", "61-90 days")
    _kpi_with_filter(c4, "91-180 days", next_180, "#94A3B8", "91-180 days")
    _kpi_with_filter(c5, ">180 days", later, "#10B981", ">180 days")

    # ─── Timeline (parents only, exclude TLs) ─────────────────
    renewal_view = filtered[
        (~filtered["Sub_Limit_Flag"]) & (filtered["Category"] != "FB-Term")
    ].copy()

    render_tab_header("INTEGRATED VIEW",
                       f"Renewal Timeline — {len(renewal_view)} Parent Facilities",
                       "Sub-limits ride their parent's renewal cycle (excluded). Term Loans amortise "
                       "rather than renew (shown separately below). Hover any bar for full detail.")

    if len(renewal_view) == 0:
        st.info("No renewal-bearing facilities match the current filter.")
    else:
        renewal_view = renewal_view.sort_values("days_to_expiry")
        fdf = renewal_view.copy()
        fdf["label"] = fdf["Lender"] + " — " + fdf["Facility"].str[:35]
        fdf["expiry_str"] = fdf["Validity_Date"].dt.strftime("%d-%b-%Y")

        def _color(d):
            if d < 0: return "#7F1D1D"
            if d <= 30: return "#EF4444"
            if d <= 60: return "#F59E0B"
            if d <= 90: return "#3B82F6"
            if d <= 180: return "#8B5CF6"
            return "#64748B"

        def _action(d):
            if d < 0: return "🚨 OVERDUE — contact lender now"
            if d <= 30: return "🔴 Submit renewal request"
            if d <= 60: return "🟠 Begin renewal preparation"
            if d <= 90: return "🔵 Schedule discussions"
            if d <= 180: return "🟣 Monitor & plan"
            return "⚪ Routine monitoring"

        fdf["color"] = fdf["days_to_expiry"].apply(_color)
        fdf["action"] = fdf["days_to_expiry"].apply(_action)

        fig = go.Figure()
        max_day = max(200, fdf["days_to_expiry"].max() + 80) if len(fdf) else 400
        min_day = min(-10, fdf["days_to_expiry"].min() - 10) if len(fdf) else -30
        fig.add_vrect(x0=min_day, x1=0,   fillcolor="rgba(127,29,29,0.18)", line_width=0, layer="below")
        fig.add_vrect(x0=0, x1=30,        fillcolor="rgba(239,68,68,0.10)", line_width=0, layer="below")
        fig.add_vrect(x0=30, x1=60,       fillcolor="rgba(245,158,11,0.08)", line_width=0, layer="below")
        fig.add_vrect(x0=60, x1=90,       fillcolor="rgba(59,130,246,0.06)", line_width=0, layer="below")
        fig.add_vrect(x0=90, x1=180,      fillcolor="rgba(139,92,246,0.05)", line_width=0, layer="below")
        fig.add_vrect(x0=180, x1=max_day, fillcolor="rgba(100,116,139,0.04)", line_width=0, layer="below")

        fig.add_trace(go.Bar(
            x=fdf["days_to_expiry"], y=fdf["label"], orientation="h",
            marker=dict(color=fdf["color"].tolist(), line=dict(color="#0F172A", width=0.5)),
            text=[f"{d:+d}d · {date} · ₹{san:.1f} Cr"
                  for d, date, san in zip(fdf["days_to_expiry"], fdf["expiry_str"], fdf["Sanction_INR"])],
            textposition="outside",
            textfont=dict(size=10, color="#F1F5F9"),
            customdata=list(zip(fdf["expiry_str"], fdf["Sanction_INR"], fdf["Category"], fdf["action"])),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "📅 Expires: %{customdata[0]}<br>"
                "⏱ Days to expiry: %{x:+d}<br>"
                "💰 Sanction: ₹%{customdata[1]:.1f} Cr<br>"
                "📋 Category: %{customdata[2]}<br>"
                "🎯 %{customdata[3]}<extra></extra>"
            ),
            showlegend=False,
        ))
        for d, color in [(0, "#94A3B8"), (30, "#EF4444"), (60, "#F59E0B"),
                          (90, "#3B82F6"), (180, "#8B5CF6")]:
            fig.add_vline(x=d, line=dict(color=color, width=1, dash="dot"))

        fig.update_layout(
            height=max(360, 26 * len(fdf)),
            plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
            font=dict(color="#F1F5F9", family="Inter, sans-serif"),
            xaxis=dict(title="Days to Expiry (negative = overdue)",
                        gridcolor="#334155", color="#94A3B8",
                        range=[min_day, max_day]),
            yaxis=dict(autorange="reversed", color="#F1F5F9"),
            margin=dict(l=20, r=200, t=20, b=60),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ─── Action list ──────────────────────────────────────────
    if len(filtered) == 0:
        return

    render_tab_header("ACTION ITEMS",
                       f"{len(filtered)} Facilit{'y' if len(filtered)==1 else 'ies'} · Priority Order")
    upcoming = filtered[filtered["days_to_expiry"].between(-365, 730)].sort_values("days_to_expiry").head(30)

    for _, r in upcoming.iterrows():
        days = int(r["days_to_expiry"])
        if days < 0:
            priority, color = "EXPIRED", "#7F1D1D"
            bg = "linear-gradient(90deg, rgba(239,68,68,0.18), rgba(239,68,68,0.06))"
            action = "Renewal overdue. Contact lender immediately."
            icon = "🚨"
        elif days <= 30:
            priority, color = "URGENT", "#EF4444"
            bg = "linear-gradient(90deg, rgba(239,68,68,0.15), rgba(239,68,68,0.03))"
            action = "Submit renewal request now."
            icon = "🔴"
        elif days <= 60:
            priority, color = "HIGH", "#F59E0B"
            bg = "linear-gradient(90deg, rgba(245,158,11,0.12), rgba(245,158,11,0.02))"
            action = "Begin renewal preparation."
            icon = "🟠"
        elif days <= 90:
            priority, color = "MEDIUM", "#3B82F6"
            bg = "linear-gradient(90deg, rgba(59,130,246,0.08), rgba(59,130,246,0.02))"
            action = "Schedule renewal discussions."
            icon = "🔵"
        elif days <= 180:
            priority, color = "LOW", "#8B5CF6"
            bg = "linear-gradient(90deg, rgba(139,92,246,0.06), rgba(139,92,246,0.02))"
            action = "Monitor and plan ahead."
            icon = "🟣"
        else:
            priority, color = "MONITOR", "#64748B"
            bg = "linear-gradient(90deg, rgba(100,116,139,0.05), rgba(100,116,139,0.01))"
            action = "Routine monitoring only."
            icon = "⚪"

        st.markdown(_html(f"""<div style='background:{bg};border-left:4px solid {color};
                              border-radius:12px;padding:14px 18px;margin-bottom:8px;'>
            <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:16px;'>
                <div style='flex:2;'>
                    <span style='background:{color};color:white;padding:3px 10px;
                                  border-radius:6px;font-size:0.65rem;font-weight:800;
                                  letter-spacing:0.08em;'>{icon} {priority}</span>
                    <span style='color:#94A3B8;font-size:0.78rem;margin-left:10px;'>
                        {r['Lender']} · {r['Facility'][:60]}
                    </span>
                    <div style='color:#F1F5F9;font-size:0.95rem;margin-top:6px;font-weight:500;'>{action}</div>
                    <div style='color:#64748B;font-size:0.72rem;margin-top:2px;'>
                        {r['Category']} · Sub-limit: {'Yes' if r.get('Sub_Limit_Flag') else 'No'}
                    </div>
                </div>
                <div style='flex:1;text-align:right;min-width:160px;'>
                    <div style='color:#94A3B8;font-size:0.7rem;letter-spacing:0.06em;'>EXPIRES</div>
                    <div style='color:#F1F5F9;font-size:1.1rem;font-weight:700;'>
                        {r['Validity_Date'].strftime('%d-%b-%Y')}
                    </div>
                    <div style='color:{color};font-size:0.9rem;font-weight:600;'>{days:+d} days</div>
                    <div style='color:#94A3B8;font-size:0.78rem;margin-top:2px;'>{inr(r['Sanction_INR'])}</div>
                </div>
            </div>
        </div>"""), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# TAB 3c — MANAGEMENT FLAGS + VALIDATION ENGINE
# ═══════════════════════════════════════════════════════════════════════
def render_tab_flags_and_validation(data: Dict[str, Any]):
    flags = data.get("management_flags", pd.DataFrame())
    val   = data.get("validation_engine", pd.DataFrame())
    vs    = data.get("validation_summary", {})

    # ─── Flag KPIs ─────────────────────────────────────────────
    if len(flags) > 0:
        open_flags = flags[flags["Status"].isin(["Open", "Open (linked F-01)"])]
        closed     = flags[flags["Status"] == "Closed"]
        acceptable = flags[flags["Status"] == "Acceptable"]
        crit_high  = open_flags[open_flags["Severity"].isin(["Critical", "High"])]

        render_tab_header("FLAGS", "Management Watch Items (F-01 → F-15)",
                           "Treasury / credit-committee items requiring decision, action, or "
                           "external verification.")
        c1, c2, c3, c4 = st.columns(4)
        with c1: render_big_kpi("Total Flags", str(len(flags)), "F-01..F-15 (F-11 retired as duplicate)", color="#3B82F6")
        with c2: render_big_kpi("Open", str(len(open_flags)),
                                  f"{len(crit_high)} High/Critical",
                                  color="#F59E0B" if len(crit_high) > 0 else "#10B981")
        with c3: render_big_kpi("Closed / Verified", str(len(closed)), "Resolved", color="#10B981")
        with c4: render_big_kpi("Acceptable", str(len(acceptable)),
                                  "Documented exception", color="#06B6D4")

        # Flag list
        sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        flag_sorted = flags.copy()
        flag_sorted["_sev"] = flag_sorted["Severity"].map(sev_order).fillna(99)
        flag_sorted["_st"] = flag_sorted["Status"].map(
            {"Open": 0, "Open (linked F-01)": 1, "Acceptable": 2, "Closed": 3}).fillna(99)
        flag_sorted = flag_sorted.sort_values(["_st", "_sev"])

        for _, f in flag_sorted.iterrows():
            sev = f["Severity"]
            color = SEVERITY_COLORS.get(sev, "#64748B")
            status = f["Status"]
            status_color = ("#10B981" if status == "Closed"
                            else "#06B6D4" if status == "Acceptable"
                            else "#F59E0B" if "Open" in status
                            else "#94A3B8")
            severity_class = sev.lower() if sev in SEVERITY_COLORS else "low"
            st.markdown(_html(f"""<div class='insight-card' style='border-left-color:{color};
                                  background:rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.06);'>
                <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:14px;'>
                    <div style='flex:3;'>
                        <div style='display:flex;gap:10px;align-items:center;'>
                            <span style='font-size:0.85rem;font-weight:700;color:#F1F5F9;'>{f['Flag']}</span>
                            <span class='severity-badge severity-{severity_class}'>{sev}</span>
                            <span style='color:#94A3B8;font-size:0.72rem;'>{f['Category']}</span>
                        </div>
                        <div style='color:#CBD5E1;font-size:0.86rem;margin-top:4px;line-height:1.4;'>
                            {f['Description']}
                        </div>
                        <div style='color:#94A3B8;font-size:0.75rem;margin-top:6px;'>
                            <b>Action:</b> {f['Action']}
                        </div>
                    </div>
                    <div style='flex:1;text-align:right;min-width:120px;'>
                        <div style='color:{status_color};font-size:0.78rem;font-weight:700;letter-spacing:0.06em;'>
                            {status.upper()}
                        </div>
                        <div style='color:#94A3B8;font-size:0.72rem;margin-top:4px;'>
                            Owner: {f['Owner']}
                        </div>
                    </div>
                </div>
            </div>"""), unsafe_allow_html=True)

    # ─── Validation & Integrity ───────────────────────────────
    render_tab_header("VALIDATION", "Model Integrity — Validation & Integrity",
                       f"{vs.get('Pass_Count', 0)}/{vs.get('Total_Checks', 0)} checks passed · "
                       f"Overall {vs.get('Overall_Status', 'PASS')}.")
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_big_kpi("Total Checks",  str(vs.get("Total_Checks", "—")),
                              "Excel V&V suite", color="#3B82F6")
    with c2: render_big_kpi("PASS",           str(vs.get("Pass_Count", "—")),
                              "Verified", color="#10B981")
    with c3: render_big_kpi("FAIL",           str(vs.get("Fail_Count", "—")),
                              "Non-critical", color="#10B981" if vs.get("Fail_Count", 0) == 0 else "#F59E0B")
    with c4: render_big_kpi("Critical FAIL",  str(vs.get("Critical_Fail", "—")),
                              "Must be zero",
                              color="#10B981" if vs.get("Critical_Fail", 0) == 0 else "#EF4444")

    if len(val) > 0:
        with st.expander(f"📋 Full integrity-check register ({len(val)} checks)", expanded=False):
            # Filter / search
            grp = st.selectbox("Filter group", options=["All"] + sorted(val["Group"].unique().tolist()),
                                key="ve_group_filter")
            disp = val.copy()
            if grp != "All":
                disp = disp[disp["Group"] == grp]
            st.dataframe(disp[["Check_ID", "Description", "Expected", "Actual",
                                "Status", "Severity", "Group"]],
                          use_container_width=True, hide_index=True, height=400)


# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — AI ANALYST  (Rule-Based + optional Gemini API)
# ═══════════════════════════════════════════════════════════════════════
def render_tab_ai(data: Dict[str, Any], controls: Dict[str, Any]):
    cov_df = resolve_covenants(data, controls["basis"],
                                stress_active=controls["is_stressed"],
                                ebitda_change_pct=controls["ebitda_change"],
                                interest_change_pct=0,
                                debt_change_pct=controls["debt_change"])

    render_tab_header("AI ANALYST", "Ask Anything",
                       "Two analyst modes available: a Rule-Based engine (free, instant, "
                       "deterministic) and a Gemini-powered conversational analyst "
                       "(bring your own API key).")

    # ─── Mode toggle ─────────────────────────────────────────
    mode = st.radio(
        "Analyst mode",
        ["🤖 Rule-Based (free, instant)", "✨ Gemini AI (bring your API key)"],
        horizontal=True,
        key="ai_mode",
        help=("Rule-Based gives deterministic answers from 15 pre-built JFL templates. "
              "Gemini AI sends your question + portfolio snapshot to Google's Gemini "
              "API for free-form conversational analysis.")
    )
    st.markdown("---")

    # ─── Proactive insight cards (shown in both modes) ────────
    st.markdown("#### 💡 Proactive Insights")
    insights = rba.get_proactive_insights(data, cov_df)
    cols = st.columns(2)
    for i, ins in enumerate(insights):
        with cols[i % 2]:
            level = ins.get("level", "info")
            st.markdown(_html(f"""<div class='insight-card {level}'>
                <div class='insight-title'>{ins['icon']} {ins['title']}</div>
                <div class='insight-body'>{ins['body']}</div></div>"""), unsafe_allow_html=True)

    st.markdown("---")

    # ════════════════════════════════════════════════════════════
    # MODE A — RULE-BASED ANALYST
    # ════════════════════════════════════════════════════════════
    if mode.startswith("🤖"):
        st.markdown("#### 💬 Suggested Questions")
        st.caption("Click any question for an instant answer drawn directly from the verified Excel.")
        cols = st.columns(2)
        for i, q in enumerate(rba.SUGGESTED_QUESTIONS):
            with cols[i % 2]:
                if st.button(q, key=f"rq_{i}", use_container_width=True):
                    resp = rba.answer_question(q, data, cov_df)
                    if "ai_history" not in st.session_state:
                        st.session_state.ai_history = []
                    st.session_state.ai_history.append({"role": "user", "content": q})
                    st.session_state.ai_history.append({"role": "assistant", "content": resp})
                    st.rerun()

        # Free-form input
        user_input = st.chat_input("Ask anything about the JFL portfolio…")
        if user_input:
            resp = rba.answer_question(user_input, data, cov_df)
            if "ai_history" not in st.session_state:
                st.session_state.ai_history = []
            st.session_state.ai_history.append({"role": "user", "content": user_input})
            st.session_state.ai_history.append({"role": "assistant", "content": resp})
            st.rerun()

    # ════════════════════════════════════════════════════════════
    # MODE B — GEMINI AI ANALYST
    # ════════════════════════════════════════════════════════════
    else:
        st.markdown("#### ✨ Gemini AI Conversational Analyst")

        # ─── API key + model selector (collapsed by default once configured)
        key_configured = bool(st.session_state.get("gemini_api_key", "").strip())
        with st.expander(
            "🔑 API Configuration" + (" — ✅ configured" if key_configured else " — ⚠ not configured"),
            expanded=not key_configured
        ):
            st.markdown(
                "**Bring your own Gemini API key.** Get a free key at "
                "[aistudio.google.com/apikey](https://aistudio.google.com/apikey). "
                "Your key is held only in this browser session and is **never** "
                "saved to disk or transmitted anywhere except Google's API endpoint."
            )

            colk1, colk2 = st.columns([3, 2])
            with colk1:
                api_key = st.text_input(
                    "Gemini API Key",
                    value=st.session_state.get("gemini_api_key", ""),
                    type="password",
                    key="gemini_api_key_input",
                    placeholder="AIzaSy…",
                    help="Starts with 'AIza' and is ~39 characters.",
                )
                if api_key != st.session_state.get("gemini_api_key", ""):
                    st.session_state.gemini_api_key = api_key
            with colk2:
                model_choices = {label: mid for mid, label in gem.GEMINI_MODELS}
                model_label = st.selectbox(
                    "Model",
                    options=list(model_choices.keys()),
                    index=0,
                    key="gemini_model_selector",
                )
                st.session_state.gemini_model = model_choices[model_label]

            # Validate key format
            if api_key:
                if gem.is_valid_key_format(api_key):
                    st.success("✅ Key format looks valid. Ready to chat.")
                else:
                    st.warning("⚠ Key doesn't look like a Gemini API key (should start with 'AIza').")

        if not st.session_state.get("gemini_api_key", "").strip():
            st.info(
                "👆 **Enter your Gemini API key above** to start chatting. "
                "Don't have one? It's free for casual use — sign up at "
                "[aistudio.google.com](https://aistudio.google.com/apikey)."
            )
        else:
            # ─── Quick-start suggested prompts for Gemini
            st.markdown("**Quick-start prompts** (click to send):")
            gemini_prompts = [
                "Summarize the top 3 risks in this portfolio and recommend mitigations.",
                "If RBL's ₹200 Cr bullet can't be refinanced, what's the financial impact?",
                "Compare our debt cost (9.15% WAC) to typical Indian steel sector benchmarks.",
                "Draft a 1-page board memo on covenant compliance for the next review meeting.",
                "What questions should I prepare for our next consortium meeting with UBI?",
                "How would a 200 bps rate hike change our debt service profile?",
            ]
            gpcols = st.columns(2)
            for i, p in enumerate(gemini_prompts):
                with gpcols[i % 2]:
                    if st.button(p, key=f"gp_{i}", use_container_width=True):
                        with st.spinner("✨ Gemini is thinking…"):
                            ok, resp = gem.ask_gemini(
                                st.session_state.gemini_api_key,
                                st.session_state.get("gemini_model", gem.DEFAULT_MODEL),
                                data, cov_df, p,
                                history=st.session_state.get("ai_history", [])
                            )
                        if "ai_history" not in st.session_state:
                            st.session_state.ai_history = []
                        st.session_state.ai_history.append({"role": "user", "content": p})
                        st.session_state.ai_history.append({
                            "role": "assistant",
                            "content": ("**✨ Gemini:**\n\n" + resp) if ok else resp
                        })
                        st.rerun()

            # ─── Free-form Gemini chat
            user_input = st.chat_input("Ask Gemini anything about the JFL portfolio…")
            if user_input:
                with st.spinner("✨ Gemini is thinking…"):
                    ok, resp = gem.ask_gemini(
                        st.session_state.gemini_api_key,
                        st.session_state.get("gemini_model", gem.DEFAULT_MODEL),
                        data, cov_df, user_input,
                        history=st.session_state.get("ai_history", [])
                    )
                if "ai_history" not in st.session_state:
                    st.session_state.ai_history = []
                st.session_state.ai_history.append({"role": "user", "content": user_input})
                st.session_state.ai_history.append({
                    "role": "assistant",
                    "content": ("**✨ Gemini:**\n\n" + resp) if ok else resp
                })
                st.rerun()

    # ─── Conversation history (shared across modes) ─────────────
    if st.session_state.get("ai_history"):
        st.markdown("---")
        st.markdown("#### 📝 Conversation")
        for m in st.session_state.ai_history:
            if m["role"] == "user":
                st.markdown(f"**🧑 You:** {m['content']}")
            else:
                st.markdown(m["content"], unsafe_allow_html=True)
            st.markdown("")
        col_clear, col_export = st.columns([1, 5])
        with col_clear:
            if st.button("🗑️ Clear", key="clear_ai_hist"):
                st.session_state.ai_history = []
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# TAB 5 — TOOLS (Export + Snapshots)
# ═══════════════════════════════════════════════════════════════════════
def render_tab_export(data: Dict[str, Any], controls: Dict[str, Any]):
    cov_df = resolve_covenants(data, controls["basis"],
                                stress_active=controls["is_stressed"],
                                ebitda_change_pct=controls["ebitda_change"],
                                debt_change_pct=controls["debt_change"])

    render_tab_header("EXPORT", "Data & Reports",
                       "Download CSVs, PDF board memo, or snapshot the current state.")

    # ─── PDF Board Memo ──────────────────────────────────────
    st.markdown("#### 📄 Board Memo (PDF)")
    st.caption("A polished multi-page PDF with verdict, KPIs, five-bucket table, "
                "lender concentration, top tightest covenants, open Management Flags, "
                "and Validation & Integrity status. Suitable for senior-management distribution.")
    try:
        from pdf_export import generate_board_memo
        pdf_bytes = generate_board_memo(data, cov_df, controls)
        st.download_button(
            "📄 Download Board Memo PDF",
            data=pdf_bytes,
            file_name=f"JFL_Board_Memo_{data['as_of_date']}.pdf",
            mime="application/pdf",
            use_container_width=True, type="primary",
        )
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        import traceback
        st.code(traceback.format_exc())

    st.markdown("---")
    st.markdown("#### 📊 Data Files (CSV)")
    c1, c2, c3 = st.columns(3)
    with c1:
        csv = cov_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Covenants CSV", csv,
                            file_name=f"jfl_covenants_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)
    with c2:
        csv = data["facility_master"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Facility Master CSV", csv,
                            file_name=f"jfl_facilities_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)
    with c3:
        csv = data["interest_schedule"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Interest Schedule CSV", csv,
                            file_name=f"jfl_interest_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        csv = data["repayment_schedule"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Repayment Schedule CSV", csv,
                            file_name=f"jfl_repayment_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)
    with c2:
        csv = data["management_flags"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Management Flags CSV", csv,
                            file_name=f"jfl_mgmt_flags_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)
    with c3:
        csv = data["validation_engine"].to_csv(index=False).encode("utf-8")
        st.download_button("📥 Validation & Integrity CSV", csv,
                            file_name=f"jfl_validation_{data['as_of_date']}.csv",
                            mime="text/csv", use_container_width=True)

    st.markdown("---")
    st.markdown("#### 📌 Quick reconciliation summary")
    t = data["totals"]; isum = data["interest_summary"]
    st.markdown(f"""
| KPI | Value |
|---|---|
| Sanctioned Debt (B1+B2) | ₹{t['Bucket1_Sanctioned_Debt']:,.0f} Cr |
| FB Mains (B1) | ₹{t['FB_Mains_B1']:,.0f} Cr |
| NFB Mains (B2) | ₹{t['NFB_Mains_B2']:,.0f} Cr |
| NFB Contingent | ₹{t['NFB_Contingent']:,.0f} Cr |
| FD-Backed (B3) | ₹{t['FD_Backed_B3']:,.0f} Cr |
| Uncommitted (B4) | ₹{t['Uncommitted_B4']:,.0f} Cr |
| Hedge Memo | ₹{t['Hedge_Memo']:,.0f} Cr |
| ICICI TL Takeover | ₹{t['ICICI_TL_Takeover']:,.0f} Cr |
| Adjusted Consortium Debt | ₹{t['Adjusted_Consortium']:,.0f} Cr |
| Annual Run-Rate | ₹{isum['Total_Interest_Commission']:,.1f} Cr |
| WAC | {isum['Weighted_Avg_Cost']*100:.2f}% |
| Total Covenants | {len(cov_df)} |
| Compliant | {(cov_df['Status'] == 'Compliant').sum()} |
| Breached | {(cov_df['Status'] == 'Breached').sum()} |
| Pending | {(cov_df['Status'] == 'Pending Input').sum()} |
""")


# ═══════════════════════════════════════════════════════════════════════
# TAB 5b — HISTORICAL SNAPSHOTS
# ═══════════════════════════════════════════════════════════════════════
def render_tab_snapshots(data: Dict[str, Any], controls: Dict[str, Any]):
    from snapshots import (take_snapshot, list_snapshots, get_snapshot,
                            delete_snapshot, compare_snapshots, clear_snapshots,
                            export_snapshots_to_json, import_snapshots_from_json)

    cov_df = resolve_covenants(data, controls["basis"],
                                stress_active=controls["is_stressed"],
                                ebitda_change_pct=controls["ebitda_change"],
                                debt_change_pct=controls["debt_change"])

    render_tab_header("SNAPSHOTS", "Historical State Tracking",
                       "Capture current state. Compare against past states to see what changed.")

    st.markdown("#### 📸 Capture Current State")
    c1, c2 = st.columns([3, 1])
    with c1:
        snap_label = st.text_input("Label (optional)", "",
                                     placeholder="e.g., 'Pre-Q1 review' or 'Before refinancing'",
                                     key="snap_label_input")
    with c2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📸 Take Snapshot", use_container_width=True, type="primary"):
            snap = take_snapshot(data, cov_df, snap_label or "")
            st.success(f"✅ Captured: {snap['label']}")
            st.rerun()

    snaps = list_snapshots()
    if not snaps:
        st.markdown("<div class='callout-info'>No snapshots yet. Take one to start tracking changes.</div>",
                     unsafe_allow_html=True)
        return

    st.markdown(f"#### 📚 Saved Snapshots ({len(snaps)})")
    for snap in reversed(snaps):
        with st.expander(f"📋 {snap['label']} — {snap['captured_at_pretty']}", expanded=False):
            state = snap["state"]
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Sanctioned Debt", f"₹{state.get('Sanctioned_Debt_B1B2', 0):,.0f} Cr")
            with c2:
                st.metric("Annual Run-Rate", f"₹{state['Annual_Run_Rate']:,.1f} Cr")
            with c3:
                st.metric("WAC", f"{state['Weighted_Avg_Cost']*100:.2f}%")
            with c4:
                st.metric("Compliant", f"{state['Compliant']}/{state['Total_Covenants']}")
            if st.button("🗑️ Delete", key=f"del_{snap['id']}"):
                delete_snapshot(snap["id"])
                st.rerun()

    # Compare
    if len(snaps) >= 2:
        st.markdown("---")
        st.markdown("#### 🔍 Compare Two Snapshots")
        snap_opts = {s["id"]: f"{s['label']} ({s['captured_at_pretty']})" for s in snaps}
        c1, c2 = st.columns(2)
        with c1:
            sa = st.selectbox("Earlier", list(snap_opts.keys()),
                                format_func=lambda x: snap_opts[x], index=0, key="snap_a")
        with c2:
            sb = st.selectbox("Later", list(snap_opts.keys()),
                                format_func=lambda x: snap_opts[x],
                                index=len(snaps)-1, key="snap_b")

        if sa != sb:
            delta = compare_snapshots(get_snapshot(sa), get_snapshot(sb))
            if delta["changed"]:
                st.markdown("##### 📈 Metric Changes")
                rows = []
                for c in sorted(delta["changed"], key=lambda x: -abs(x.get("pct_change", 0))):
                    arrow = "⬆️" if c["abs_change"] > 0 else "⬇️"
                    rows.append({
                        "Metric": c["metric"].replace("_", " "),
                        "Before": f"{c['before']:,.4f}" if abs(c['before']) < 100 else f"{c['before']:,.2f}",
                        "After":  f"{c['after']:,.4f}"  if abs(c['after']) < 100  else f"{c['after']:,.2f}",
                        "Change": f"{arrow} {c['abs_change']:+,.2f}",
                        "%":      f"{c['pct_change']:+.2f}%",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.markdown("<div class='callout-good'>✅ No metric changes between these snapshots.</div>",
                             unsafe_allow_html=True)

            if delta["covenant_changes"]:
                st.markdown("##### 📋 Covenant Actual Changes")
                rows = []
                for c in sorted(delta["covenant_changes"], key=lambda x: -abs(x["abs_change"])):
                    arrow = "⬆️" if c["abs_change"] > 0 else "⬇️"
                    rows.append({
                        "Lender": c["lender"], "Covenant": c["covenant"],
                        "Before": f"{c['before']:.4f}", "After": f"{c['after']:.4f}",
                        "Change": f"{arrow} {c['abs_change']:+.4f}",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if delta["exposure_changes"]:
                st.markdown("##### 🏦 Lender Exposure Changes")
                rows = []
                for c in delta["exposure_changes"]:
                    arrow = "⬆️" if c["abs_change"] > 0 else "⬇️"
                    rows.append({
                        "Lender": c["lender"],
                        "Before (₹ Cr)": f"{c['before']:,.1f}",
                        "After (₹ Cr)":  f"{c['after']:,.1f}",
                        "Change":        f"{arrow} ₹{c['abs_change']:+,.1f}",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Export / Import
    st.markdown("---")
    st.markdown("#### 💾 Backup Snapshots")
    c1, c2, c3 = st.columns(3)
    with c1:
        js = export_snapshots_to_json()
        st.download_button("📥 Download Snapshots JSON", js,
                            file_name=f"jfl_snapshots_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
                            mime="application/json", use_container_width=True)
    with c2:
        uploaded = st.file_uploader("📤 Restore from JSON", type=["json"],
                                     key="snap_restore", label_visibility="collapsed")
        if uploaded is not None:
            try:
                n = import_snapshots_from_json(uploaded.getvalue())
                st.success(f"✅ Restored {n} new snapshots")
                st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")
    with c3:
        if st.button("🗑️ Clear All Snapshots", use_container_width=True):
            clear_snapshots()
            st.rerun()
