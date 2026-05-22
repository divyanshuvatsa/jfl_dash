"""Visualization helpers — JFL portfolio adapted from JCL chart suite.

Charts:
  - render_covenant_headroom_chart         : compliance headroom bars
  - render_facility_cost_chart             : annual ₹ cost by facility
  - render_fb_rate_vs_wac_chart            : FB rate vs portfolio WAC
  - render_lender_composition_stacked      : per-lender category mix
  - render_repayment_timeline              : 7-TL cumulative run-down
  - render_renewal_timeline                : next-12-month validity gantt
  - render_tev_trajectory                  : FY27-FY38 TEV ratio forward-look
  - render_bucket_donut                    : 5-bucket pie of total committed
"""

from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from typing import Dict, Any
from theme import LENDER_COLORS, STATUS_COLORS


# ════════════════════════════════════════════════════════════════════
# SHARED STYLE CONSTANTS — JFL Dashboard Polish (May 2026)
# ════════════════════════════════════════════════════════════════════
BG_DARK       = "#0F172A"   # slate-900 — primary background
BG_PANEL      = "#1E293B"   # slate-800 — chart inner panel
GRID          = "rgba(148,163,184,0.12)"  # slate-400 @ 12% — subtle gridlines
AXIS          = "rgba(148,163,184,0.35)"  # slate-400 @ 35% — axis lines
TEXT_PRIMARY  = "#F1F5F9"   # slate-100 — main text
TEXT_MUTED    = "#94A3B8"   # slate-400 — secondary text
TEXT_DIM      = "#64748B"   # slate-500 — tertiary

# Coherent 8-stop palette (each chart picks the slice it needs)
PALETTE = {
    "primary":   "#3B82F6",   # blue-500
    "secondary": "#8B5CF6",   # violet-500
    "success":   "#10B981",   # emerald-500
    "warning":   "#F59E0B",   # amber-500
    "danger":    "#EF4444",   # red-500
    "pink":      "#EC4899",   # pink-500
    "teal":      "#14B8A6",   # teal-500
    "indigo":    "#6366F1",   # indigo-500
}

# Multi-series sequences
BUCKET_COLORS = ["#3B82F6", "#F59E0B", "#10B981", "#94A3B8", "#EC4899"]  # B1/B2/B3/B4/Hedge
DIVERGING     = ["#10B981", "#22C55E", "#EAB308", "#F59E0B", "#EF4444"]  # green→amber→red
SEQUENTIAL_B  = ["#1E40AF", "#2563EB", "#3B82F6", "#60A5FA", "#93C5FD"]  # blue dark→light


def _common_layout(height: int = 420, *,
                   title: str = "",
                   show_legend: bool = True,
                   legend_orientation: str = "h",
                   margin_t: int = 60,
                   margin_b: int = 60) -> dict:
    """Standard layout kwargs every chart in the suite uses.

    Ensures consistent dark theme, gridlines, font, margins, and legend
    positioning across all 9 charts. Pass into fig.update_layout(**kwargs).
    """
    layout = {
        "height": height,
        "plot_bgcolor": BG_DARK,
        "paper_bgcolor": BG_DARK,
        "font": dict(color=TEXT_PRIMARY, family="Inter, -apple-system, sans-serif",
                     size=12),
        "title": dict(text=title, x=0.02, xanchor="left", y=0.98, yanchor="top",
                      font=dict(size=15, color=TEXT_PRIMARY, family="Inter")) if title else None,
        "margin": dict(l=60, r=30, t=margin_t, b=margin_b),
        "hoverlabel": dict(bgcolor=BG_PANEL, bordercolor=PALETTE["primary"],
                           font=dict(color=TEXT_PRIMARY, size=12, family="Inter")),
        "xaxis": dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                      tickfont=dict(color=TEXT_MUTED, size=11),
                      title_font=dict(color=TEXT_MUTED, size=12)),
        "yaxis": dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                      tickfont=dict(color=TEXT_MUTED, size=11),
                      title_font=dict(color=TEXT_MUTED, size=12)),
    }
    if show_legend:
        if legend_orientation == "h":
            layout["legend"] = dict(orientation="h", yanchor="bottom", y=-0.22,
                                     xanchor="center", x=0.5,
                                     font=dict(color=TEXT_PRIMARY, size=11),
                                     bgcolor="rgba(0,0,0,0)")
        else:
            layout["legend"] = dict(orientation="v", yanchor="top", y=1,
                                     xanchor="left", x=1.02,
                                     font=dict(color=TEXT_PRIMARY, size=11),
                                     bgcolor="rgba(0,0,0,0)")
    else:
        layout["showlegend"] = False
    return {k: v for k, v in layout.items() if v is not None}


# ════════════════════════════════════════════════════════════════════
# COVENANT HEADROOM BAR CHART
# ════════════════════════════════════════════════════════════════════
def render_covenant_headroom_chart(cov_df: pd.DataFrame, *, mode: str = "tightest"):
    """Compliance buffer chart.

    mode="tightest" → one bar per unique ratio type (tightest lender).
    mode="all"      → every instance.
    """
    df = cov_df.copy()
    df["headroom"] = pd.to_numeric(df.get("Headroom_Pct"), errors="coerce")
    df = df[df["headroom"].notna()].copy()

    if df.empty:
        st.info("No numeric covenants to plot — all rows are pending input or rating-based.")
        return

    if mode == "tightest":
        df = df.sort_values("headroom").groupby("Covenant", sort=False).head(1)
        df["label"] = df["Covenant"] + "  ·  " + df["Lender"]
        subtitle = (f"<i>Tightest instance of each ratio type — "
                    f"{len(df)} unique ratios from {len(cov_df)} total covenants.</i>")
    else:
        df["label"] = df["Lender"] + " — " + df["Covenant"]
        subtitle = "<i>All instances shown per lender.</i>"

    df = df.sort_values("headroom", ascending=True)

    CAP = 200
    df["display_value"] = df["headroom"].clip(lower=-100, upper=CAP)
    df["actual_text"] = df["headroom"].apply(
        lambda v: f">{CAP}% (actual {v:.0f}%)" if v > CAP
        else f"<-100% (actual {v:.0f}%)" if v < -100
        else f"{v:+.0f}%"
    )

    colors = [STATUS_COLORS.get(s, "#64748B") for s in df["Status"]]

    fig = go.Figure()
    fig.add_vrect(x0=-110, x1=0,    fillcolor="rgba(239,68,68,0.08)",  line_width=0, layer="below")
    fig.add_vrect(x0=0,    x1=20,   fillcolor="rgba(245,158,11,0.06)", line_width=0, layer="below")
    fig.add_vrect(x0=20,   x1=CAP+10, fillcolor="rgba(16,185,129,0.04)", line_width=0, layer="below")

    def _fmt_actual(v):
        if isinstance(v, (int, float)) and pd.notna(v):
            return f"{v:.4f}"
        return str(v)[:30]

    hover_actual = df["Actual"].apply(_fmt_actual)
    hover_threshold = df["Threshold"].apply(
        lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else str(v))

    fig.add_trace(go.Bar(
        x=df["display_value"], y=df["label"], orientation="h",
        marker=dict(color=colors,
                    line=dict(color=BG_DARK, width=1),
                    opacity=0.92),
        text=df["actual_text"], textposition="outside",
        textfont=dict(size=11, color=TEXT_PRIMARY, family="Inter"),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Actual: %{customdata[0]}<br>"
            "Threshold: %{customdata[1]} %{customdata[2]}<br>"
            "Headroom: %{customdata[3]:+.1f}%<br>"
            "Status: <b>%{customdata[4]}</b><extra></extra>"
        ),
        customdata=list(zip(hover_actual, df["Operator"], hover_threshold,
                            df["headroom"], df["Status"])),
    ))
    fig.add_vline(x=0,  line=dict(color=PALETTE["danger"], width=2))
    fig.add_vline(x=20, line=dict(color=PALETTE["warning"], width=1, dash="dot"))

    fig.update_layout(
        **_common_layout(height=max(420, 32 * len(df)), show_legend=False,
                         margin_t=30, margin_b=50),
    )
    fig.update_xaxes(
        title="Headroom % (positive = compliant, negative = breach)",
        range=[-110, CAP + 30],
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        f"<div style='font-size:0.82rem;color:{TEXT_MUTED};margin-top:4px;text-align:center;'>{subtitle}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='display:flex;gap:20px;justify-content:center;font-size:0.82rem;"
        f"color:{TEXT_MUTED};margin-top:6px;flex-wrap:wrap;'>"
        "<span>🟢 Compliant (>10% buffer)</span>"
        "<span>🔵 Watch (5-10%)</span>"
        "<span>🟡 Near Breach (<5%)</span>"
        "<span>🔴 Breached</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# FACILITY COST CONTRIBUTION
# ════════════════════════════════════════════════════════════════════
def render_facility_cost_chart(data: Dict[str, Any]):
    """Annual ₹ cost contribution by facility — where the ₹375 Cr comes from.

    Blue = interest on drawn FB principal (Bucket 1 & 3).
    Amber = commission on NFB sanctioned face (Bucket 2).
    Excludes Bucket-4 uncommitted lines (HSBC) and Bucket-0 sub-limits.
    """
    fm = data["facility_master"].copy()
    fm = fm[~fm["Sub_Limit_Flag"]].copy()

    rows = []
    for _, r in fm.iterrows():
        rate = r.get("Effective_Rate") or 0
        if not isinstance(rate, (int, float)) or rate <= 0:
            continue
        cat = r.get("Category", "")
        if cat == "Hedge":
            continue
        try:
            bucket_int = int(r.get("Bucket", 0))
        except (ValueError, TypeError):
            continue
        if bucket_int == 4:   # Skip HSBC uncommitted
            continue

        if cat == "NFB":
            base = r.get("Sanction_INR", 0)
            cost_type = "Commission (NFB)"
        else:
            base = r.get("Effective_OS", 0)
            cost_type = "Interest (FB)"
        if base <= 0:
            continue

        cost = base * rate
        rows.append({
            "Lender": r["Lender"],
            "Label": f"{r['Lender']} — {r['Facility'][:40]}",
            "Rate_Pct": rate * 100,
            "Base": base,
            "Annual_Cost": cost,
            "Cost_Type": cost_type,
        })
    if not rows:
        st.info("No interest- or commission-bearing facilities to plot.")
        return

    df = pd.DataFrame(rows).sort_values("Annual_Cost", ascending=True)
    df["color"] = df["Cost_Type"].map({
        "Interest (FB)": PALETTE["primary"],
        "Commission (NFB)": PALETTE["warning"],
    })
    total_cost = df["Annual_Cost"].sum()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["Annual_Cost"], y=df["Label"], orientation="h",
        marker=dict(color=df["color"].tolist(),
                    line=dict(color=BG_DARK, width=1),
                    opacity=0.92),
        text=[f"₹{c:.2f}" for c in df["Annual_Cost"]],
        textposition="outside",
        textfont=dict(size=10, color=TEXT_PRIMARY, family="Inter"),
        customdata=list(zip(df["Rate_Pct"], df["Base"], df["Cost_Type"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Annual Cost: <b>₹%{x:.2f} Cr</b><br>"
            "Type: %{customdata[2]}<br>"
            "Rate: %{customdata[0]:.2f}%<br>"
            "Base: ₹%{customdata[1]:.1f} Cr<extra></extra>"
        ),
    ))
    fig.update_layout(
        **_common_layout(height=max(400, 24 * len(df)), show_legend=False,
                         margin_t=30, margin_b=50),
    )
    fig.update_xaxes(
        title=f"Annual Cost Contribution (₹ Cr)  ·  total ≈ ₹{total_cost:.1f} Cr",
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        f"<div style='display:flex;gap:24px;justify-content:center;font-size:0.85rem;"
        f"color:{TEXT_MUTED};margin-top:6px;'>"
        f"<span><span style='color:{PALETTE['primary']};font-size:1.1rem'>■</span> Interest on drawn FB principal</span>"
        f"<span><span style='color:{PALETTE['warning']};font-size:1.1rem'>■</span> Commission on NFB sanctioned face</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# FB RATE vs WAC
# ════════════════════════════════════════════════════════════════════
def render_fb_rate_vs_wac_chart(data: Dict[str, Any]):
    """FB-only effective rate vs portfolio WAC (apples-to-apples)."""
    fm = data["facility_master"].copy()
    fm = fm[(fm["Effective_OS"] > 0) & ~fm["Sub_Limit_Flag"]]
    fm = fm[fm["Effective_Rate"].notna() & (fm["Effective_Rate"] > 0)]
    fm = fm[~fm["Category"].isin(["NFB", "Hedge"])]
    # Exclude HSBC uncommitted (B4) — those rates are placeholders
    fm = fm[fm["Bucket"] != 4]

    if fm.empty:
        st.info("No FB interest-bearing facilities to plot.")
        return

    wac = data["interest_summary"]["Weighted_Avg_Cost"]
    fm = fm.sort_values("Effective_Rate", ascending=True)
    fm["label"] = fm["Lender"] + " — " + fm["Facility"].str[:35]
    fm["rate_pct"] = fm["Effective_Rate"] * 100
    fm["color"] = [LENDER_COLORS.get(l, "#3B82F6") for l in fm["Lender"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=fm["rate_pct"], y=fm["label"], orientation="h",
        marker=dict(color=fm["color"].tolist(),
                    line=dict(color=BG_DARK, width=1),
                    opacity=0.92),
        text=[f"{r:.2f}%" for r in fm["rate_pct"]],
        textposition="outside",
        textfont=dict(size=10, color=TEXT_PRIMARY, family="Inter"),
        customdata=list(zip(fm["Effective_OS"], fm["Effective_OS"] * fm["Effective_Rate"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Rate: <b>%{x:.2f}%</b><br>"
            "Outstanding: ₹%{customdata[0]:.1f} Cr<br>"
            "Annual Interest: ₹%{customdata[1]:.2f} Cr<extra></extra>"
        ),
    ))
    fig.add_vline(
        x=wac * 100,
        line=dict(color=PALETTE["warning"], width=2.5, dash="dash"),
        annotation=dict(text=f"<b>Portfolio WAC: {wac*100:.2f}%</b>",
                        font=dict(color=PALETTE["warning"], size=12, family="Inter"),
                        bgcolor="rgba(15,23,42,0.85)",
                        bordercolor=PALETTE["warning"], borderwidth=1, borderpad=4),
    )
    fig.update_layout(
        **_common_layout(height=max(320, 28 * len(fm)), show_legend=False,
                         margin_t=30, margin_b=50),
    )
    fig.update_xaxes(title="Effective Interest Rate (%)  ·  fund-based facilities only")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════
# LENDER × CATEGORY STACKED BAR
# ════════════════════════════════════════════════════════════════════
CATEGORY_LABELS = {
    "FB-Term":      "Term Loan",
    "FB":           "WC Fund-Based",
    "FB-FCY":       "FX Buyer's Credit",
    "FB-FDbacked":  "FD-Backed FB",
    "NFB":          "NFB (LC/SBLC/BG)",
}
CATEGORY_ORDER = ["Term Loan", "WC Fund-Based", "FX Buyer's Credit",
                   "FD-Backed FB", "NFB (LC/SBLC/BG)"]


def render_lender_composition_stacked(data: Dict[str, Any]):
    """Each lender's Sanctioned Debt (B1+B2) split by facility category."""
    fm = data["facility_master"].copy()
    fm_main = fm[fm["Bucket"].isin([1, 2])].copy()
    if fm_main.empty:
        st.info("No B1/B2 facilities to plot.")
        return

    fm_main["Cat_Label"] = fm_main["Category"].map(CATEGORY_LABELS).fillna(fm_main["Category"])
    pivot = fm_main.pivot_table(
        index="Lender", columns="Cat_Label",
        values="Sanction_INR", aggfunc="sum", fill_value=0,
    )
    cols_present = [c for c in CATEGORY_ORDER if c in pivot.columns]
    cols_extra = [c for c in pivot.columns if c not in cols_present]
    pivot = pivot[cols_present + cols_extra]

    pivot["__total__"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("__total__", ascending=False)
    pivot = pivot.drop(columns="__total__")

    cat_colors = {
        "Term Loan":         PALETTE["primary"],
        "WC Fund-Based":     PALETTE["secondary"],
        "FX Buyer's Credit": PALETTE["teal"],
        "FD-Backed FB":      PALETTE["success"],
        "NFB (LC/SBLC/BG)":  PALETTE["warning"],
    }

    fig = go.Figure()
    for cat in pivot.columns:
        fig.add_trace(go.Bar(
            name=cat,
            y=list(pivot.index),
            x=pivot[cat].values,
            orientation="h",
            marker=dict(color=cat_colors.get(cat, "#94A3B8"),
                        line=dict(color=BG_DARK, width=1),
                        opacity=0.92),
            text=[f"₹{v:.0f}" if v >= 30 else "" for v in pivot[cat].values],
            textposition="inside",
            textfont=dict(color="white", size=11, family="Inter"),
            hovertemplate=f"<b>%{{y}}</b><br>{cat}: <b>₹%{{x:,.1f}} Cr</b> sanctioned<extra></extra>",
        ))

    totals = pivot.sum(axis=1)
    grand = totals.sum()
    for lender, total in totals.items():
        fig.add_annotation(
            x=total + grand * 0.012, y=lender, text=f"<b>₹{total:.0f}</b>",
            showarrow=False, font=dict(color=TEXT_PRIMARY, size=12, family="Inter"),
            xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        **_common_layout(height=max(360, 40 * len(pivot)),
                         margin_t=30, margin_b=80),
    )
    fig.update_xaxes(
        title=f"Sanctioned Capacity (₹ Cr)  ·  total ties to ₹{grand:,.0f} Cr",
        range=[0, totals.max() * 1.22],
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════
# TERM LOAN OUTSTANDING RUN-DOWN (7 TLs)
# ════════════════════════════════════════════════════════════════════
# Mapping: TL display name → closing-balance column → lender colour key
JFL_TL_TRACKS = [
    ("UBI RTL-I",     "UBI_RTL_I_Closing",   "UBI"),
    ("UBI RTL-II",    "UBI_RTL_II_Closing",  "UBI"),
    ("Indian Bank",   "Indian_Bank_Closing", "Indian Bank"),
    ("RBL Bridge",    "RBL_Closing",         "RBL Bank"),
    ("YES Bank",      "YBL_Closing",         "YES Bank"),
    ("IDFC First",    "IDFC_Closing",        "IDFC First Bank"),
    ("ICICI TL",      "ICICI_TL_Closing",    "ICICI Bank (TL)"),
]


def render_repayment_timeline(data: Dict[str, Any]):
    """Cumulative TL outstanding running down over time — stacked area per TL.

    Uses the Excel's quarterly closing balances aggregated to FY-end.
    """
    rep = data["repayment_schedule"].copy()
    if rep.empty:
        st.info("No term-loan schedule to plot.")
        return

    rep["FY"] = rep["Period_End"].dt.year + (rep["Period_End"].dt.month >= 4).astype(int)
    rep["FY_Label"] = "FY" + rep["FY"].astype(str).str[-2:]

    # Take the LAST closing of each FY (Q4) as the year-end balance
    fy_end = rep.sort_values("Period_End").groupby("FY_Label", sort=False).last()
    fy_end = fy_end.sort_index()  # FY24, FY25, ... FY39

    fig = go.Figure()
    for tl_name, col, lender_key in JFL_TL_TRACKS:
        if col not in fy_end.columns:
            continue
        vals = fy_end[col].values
        if vals.sum() <= 0:
            continue
        color = LENDER_COLORS.get(lender_key, "#3B82F6")
        fig.add_trace(go.Scatter(
            x=fy_end.index, y=vals,
            mode="lines", name=tl_name,
            line=dict(color=color, width=2),
            stackgroup="one",
            hovertemplate=f"<b>{tl_name}</b><br>%{{x}}: ₹%{{y:.1f}} Cr<extra></extra>",
        ))

    fig.update_layout(
        **_common_layout(height=460, margin_t=30, margin_b=80),
    )
    fig.update_xaxes(title="Financial Year-End", tickangle=-30)
    fig.update_yaxes(title="Term Loan Outstanding (₹ Cr)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════
# RENEWAL TIMELINE (next 12 months)
# ════════════════════════════════════════════════════════════════════
def render_renewal_timeline(data: Dict[str, Any]):
    """Each facility's validity expiry on a horizontal gantt (next 12 months)."""
    fm = data["facility_master"].copy()
    as_of = pd.Timestamp(data["as_of_date"])
    fm["days"] = (fm["Validity_Date"] - as_of).dt.days
    fm = fm[fm["days"].notna() & (fm["days"].between(-30, 365))].copy()

    if fm.empty:
        st.info("No facilities expiring in the next 12 months.")
        return

    fm["label"] = fm["Lender"] + " — " + fm["Facility"].str[:35]
    fm = fm.sort_values("days")

    def _color(d):
        if d < 0: return "#7F1D1D"
        if d <= 30: return PALETTE["danger"]
        if d <= 60: return PALETTE["warning"]
        if d <= 90: return PALETTE["primary"]
        if d <= 180: return PALETTE["secondary"]
        return TEXT_DIM

    fm["color"] = fm["days"].apply(_color)
    fm["expiry_str"] = fm["Validity_Date"].dt.strftime("%d-%b-%Y")

    fig = go.Figure()
    fig.add_vrect(x0=-40, x1=0, fillcolor="rgba(127,29,29,0.20)", line_width=0, layer="below")
    fig.add_vrect(x0=0, x1=30,  fillcolor="rgba(239,68,68,0.12)", line_width=0, layer="below")
    fig.add_vrect(x0=30, x1=60, fillcolor="rgba(245,158,11,0.10)", line_width=0, layer="below")
    fig.add_vrect(x0=60, x1=90, fillcolor="rgba(59,130,246,0.08)", line_width=0, layer="below")
    fig.add_vrect(x0=90, x1=180, fillcolor="rgba(139,92,246,0.06)", line_width=0, layer="below")
    fig.add_vrect(x0=180, x1=400, fillcolor="rgba(100,116,139,0.04)", line_width=0, layer="below")

    fig.add_trace(go.Bar(
        x=fm["days"], y=fm["label"], orientation="h",
        marker=dict(color=fm["color"].tolist(),
                    line=dict(color=BG_DARK, width=1),
                    opacity=0.95),
        text=[f"{d:+d}d · {date}" for d, date in zip(fm["days"], fm["expiry_str"])],
        textposition="outside",
        textfont=dict(size=10, color=TEXT_PRIMARY, family="Inter"),
        customdata=list(zip(fm["expiry_str"], fm["Sanction_INR"], fm["Category"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Expires: <b>%{customdata[0]}</b><br>"
            "Days to expiry: %{x:+d}<br>"
            "Sanction: ₹%{customdata[1]:.1f} Cr<br>"
            "Category: %{customdata[2]}<extra></extra>"
        ),
        showlegend=False,
    ))
    for d, color in [(0, TEXT_MUTED), (30, PALETTE["danger"]), (60, PALETTE["warning"]),
                      (90, PALETTE["primary"]), (180, PALETTE["secondary"])]:
        fig.add_vline(x=d, line=dict(color=color, width=1, dash="dot"))

    fig.update_layout(
        **_common_layout(height=max(460, 24 * len(fm)), show_legend=False,
                         margin_t=30, margin_b=60),
    )
    fig.update_xaxes(
        title="Days to Expiry (negative = overdue)",
        range=[-40, max(200, fm["days"].max() + 60)],
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        f"<div style='display:flex;gap:18px;justify-content:center;font-size:0.82rem;"
        f"color:{TEXT_MUTED};margin-top:4px;flex-wrap:wrap;'>"
        "<span>🩸 Overdue</span>"
        "<span>🔴 ≤30 days</span>"
        "<span>🟠 31-60</span>"
        "<span>🔵 61-90</span>"
        "<span>🟣 91-180</span>"
        "<span>⚫ >180</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# TEV FORWARD COVENANT TRAJECTORY (FY27 → FY38)
# ════════════════════════════════════════════════════════════════════
def render_tev_trajectory(data: Dict[str, Any]):
    """TEV-projected DSCR / ISCR / FACR / LTD-EBITDA / LTD-Equity over FY27-FY38.

    JFL-specific. The JCL reference didn't need this — JCL is operational.
    JFL is pre-COD, so a forward look on the binding constraints matters.
    """
    tev = data.get("tev_ratios", {})
    fys = sorted([f for f in tev.keys() if f >= "FY27"])
    if not fys:
        st.info("No future-year TEV ratio data available.")
        return

    metrics = [
        ("DSCR",       1.25, ">=", "#3B82F6"),
        ("ISCR",       2.00, ">=", "#8B5CF6"),
        ("FACR",       1.20, ">=", "#10B981"),
        ("LTD_EBITDA", 4.00, "<=", "#F59E0B"),
        ("LTD_Equity", 2.00, "<=", "#EC4899"),
    ]

    fig = go.Figure()
    for m, thr, op, color in metrics:
        vals = [tev[fy].get(m, 0) for fy in fys]
        label = m.replace("_", "/")
        fig.add_trace(go.Scatter(
            x=fys, y=vals, mode="lines+markers",
            name=f"{label} (threshold {op} {thr})",
            line=dict(color=color, width=3, shape="spline", smoothing=0.6),
            marker=dict(size=9, line=dict(color=BG_DARK, width=1.5),
                        symbol="circle"),
            hovertemplate=f"<b>{label}</b><br>%{{x}}: <b>%{{y:.2f}}x</b><extra></extra>",
        ))

    fig.add_hline(y=1.25, line=dict(color=PALETTE["danger"], width=1.5, dash="dash"),
                  annotation=dict(text="<b>DSCR floor 1.25x</b>",
                                   font=dict(color="#FCA5A5", size=11),
                                   bgcolor="rgba(15,23,42,0.85)", bordercolor="#FCA5A5",
                                   borderwidth=1, borderpad=3))
    fig.add_hline(y=4.0, line=dict(color=PALETTE["warning"], width=1.5, dash="dot"),
                  annotation=dict(text="<b>LTD/EBITDA cap 4.0x</b>",
                                   font=dict(color="#FCD34D", size=11),
                                   bgcolor="rgba(15,23,42,0.85)", bordercolor="#FCD34D",
                                   borderwidth=1, borderpad=3))

    fig.update_layout(
        **_common_layout(height=440, margin_t=30, margin_b=80),
    )
    fig.update_yaxes(title="Ratio (x)", range=[0, 7])
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════
# 5-BUCKET DONUT
# ════════════════════════════════════════════════════════════════════
def render_bucket_donut(data: Dict[str, Any]):
    """Headline 5-bucket view: B1 + B2 + B3 + B4 + Hedge memo."""
    t = data["totals"]
    labels = [
        f"B1 FB Mains",
        f"B2 NFB Mains",
        f"B3 FD-Backed",
        f"B4 Uncommitted",
        f"Hedge Memo",
    ]
    values = [t['FB_Mains_B1'], t['NFB_Mains_B2'],
              t['FD_Backed_B3'], t['Uncommitted_B4'], t['Hedge_Memo']]
    custom_amounts = [f"₹{v:,.0f} Cr" for v in values]
    total = sum(values)

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, customdata=custom_amounts,
        marker=dict(colors=BUCKET_COLORS,
                    line=dict(color=BG_DARK, width=3)),
        hole=0.62,
        textinfo="label+percent",
        textposition="outside",
        textfont=dict(color=TEXT_PRIMARY, size=12, family="Inter"),
        hovertemplate="<b>%{label}</b><br>%{customdata}<br><b>%{percent}</b> of total<extra></extra>",
        rotation=90,
        pull=[0.02, 0.02, 0.02, 0.02, 0.02],
    )])
    fig.update_layout(
        **_common_layout(height=440, show_legend=False, margin_t=30, margin_b=30),
        annotations=[
            dict(text=f"<b style='font-size:30px;color:{TEXT_PRIMARY}'>₹{total:,.0f}</b>"
                       f"<br><span style='font-size:11px;color:{TEXT_MUTED};letter-spacing:0.05em'>CR · TOTAL COMMITTED</span>"
                       f"<br><span style='font-size:10px;color:{TEXT_DIM}'>(incl. uncommitted &amp; hedge)</span>",
                  x=0.5, y=0.5, showarrow=False, font=dict(family="Inter")),
        ],
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════
# SCENARIO COMPARISON (base vs stress)
# ════════════════════════════════════════════════════════════════════
def render_scenario_comparison_chart(base: Dict, stress: Dict, basis: str):
    """Side-by-side base vs stress comparison for key ratios."""
    base_cov = base.get("covenants")
    stress_cov = stress.get("covenants")
    if base_cov is None or stress_cov is None:
        return

    def _pull(df, name):
        m = df[df["Covenant"].str.contains(name, case=False, na=False, regex=False)]
        if len(m) == 0: return None
        v = m.iloc[0]["Actual"]
        return v if isinstance(v, (int, float)) and pd.notna(v) else None

    rows = [
        ("DSCR",       _pull(base_cov, "DSCR"),       _pull(stress_cov, "DSCR"),       1.25, ">="),
        ("ISCR",       _pull(base_cov, "ISCR"),       _pull(stress_cov, "ISCR"),       2.00, ">="),
        ("FACR",       _pull(base_cov, "FACR"),       _pull(stress_cov, "FACR"),       1.20, ">="),
        ("LTD/EBITDA", _pull(base_cov, "LTD / EBITDA"),_pull(stress_cov,"LTD / EBITDA"),4.00, "<="),
        ("LTD/Equity", _pull(base_cov, "LTD / Equity"),_pull(stress_cov,"LTD / Equity"),2.00, "<="),
    ]
    rows = [r for r in rows if r[1] is not None and r[2] is not None]
    if not rows:
        return

    labels = [r[0] for r in rows]
    base_v = [r[1] for r in rows]
    stress_v = [r[2] for r in rows]
    thresholds = [r[3] for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=f"Base ({basis})", x=labels, y=base_v,
        marker=dict(color=PALETTE["primary"],
                    line=dict(color=BG_DARK, width=1.5),
                    opacity=0.92),
        text=[f"<b>{v:.2f}x</b>" for v in base_v], textposition="outside",
        textfont=dict(color=TEXT_PRIMARY, size=12, family="Inter"),
        hovertemplate="<b>%{x}</b><br>Base: <b>%{y:.2f}x</b><extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Stress", x=labels, y=stress_v,
        marker=dict(color=PALETTE["warning"],
                    line=dict(color=BG_DARK, width=1.5),
                    opacity=0.92),
        text=[f"<b>{v:.2f}x</b>" for v in stress_v], textposition="outside",
        textfont=dict(color=TEXT_PRIMARY, size=12, family="Inter"),
        hovertemplate="<b>%{x}</b><br>Stress: <b>%{y:.2f}x</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Threshold", x=labels, y=thresholds,
        mode="markers",
        marker=dict(symbol="line-ew", size=28, color=PALETTE["danger"],
                     line=dict(width=4)),
        hovertemplate="<b>%{x}</b><br>Threshold: %{y:.2f}x<extra></extra>",
    ))
    fig.update_layout(
        barmode="group",
        **_common_layout(height=420, margin_t=30, margin_b=70),
    )
    fig.update_yaxes(title="Ratio (x)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
