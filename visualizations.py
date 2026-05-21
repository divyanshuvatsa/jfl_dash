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
        marker=dict(color=colors, line=dict(color="#0F172A", width=0.5)),
        text=df["actual_text"], textposition="outside",
        textfont=dict(size=11, color="#F1F5F9"),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Actual: %{customdata[0]}<br>"
            "Threshold: %{customdata[1]} %{customdata[2]}<br>"
            "Headroom: %{customdata[3]:+.1f}%<br>"
            "Status: %{customdata[4]}<extra></extra>"
        ),
        customdata=list(zip(hover_actual, df["Operator"], hover_threshold,
                            df["headroom"], df["Status"])),
    ))
    fig.add_vline(x=0,  line=dict(color="#EF4444", width=2))
    fig.add_vline(x=20, line=dict(color="#F59E0B", width=1, dash="dot"))

    fig.update_layout(
        height=max(400, 30 * len(df)),
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(
            title="Headroom % (positive = compliant, negative = breach)",
            gridcolor="#334155", color="#94A3B8",
            range=[-110, CAP + 30],
        ),
        yaxis=dict(color="#F1F5F9"),
        margin=dict(l=20, r=140, t=50, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        f"<div style='font-size:0.82rem;color:#94A3B8;margin-top:4px;text-align:center;'>{subtitle}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='display:flex;gap:20px;justify-content:center;font-size:0.82rem;"
        "color:#94A3B8;margin-top:6px;flex-wrap:wrap;'>"
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
        "Interest (FB)": "#3B82F6",
        "Commission (NFB)": "#F59E0B",
    })
    total_cost = df["Annual_Cost"].sum()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["Annual_Cost"], y=df["Label"], orientation="h",
        marker_color=df["color"].tolist(),
        text=[f"₹{c:.2f}" for c in df["Annual_Cost"]],
        textposition="outside",
        textfont=dict(size=10, color="#F1F5F9"),
        customdata=list(zip(df["Rate_Pct"], df["Base"], df["Cost_Type"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Annual Cost: ₹%{x:.2f} Cr<br>"
            "Type: %{customdata[2]}<br>"
            "Rate: %{customdata[0]:.2f}%<br>"
            "Base: ₹%{customdata[1]:.1f} Cr<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=max(380, 22 * len(df)),
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(title=f"Annual Cost Contribution (₹ Cr)  ·  total ≈ ₹{total_cost:.1f} Cr",
                   gridcolor="#334155", color="#94A3B8"),
        yaxis=dict(color="#F1F5F9", autorange="reversed"),
        margin=dict(l=20, r=80, t=20, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        "<div style='display:flex;gap:24px;justify-content:center;font-size:0.85rem;"
        "color:#94A3B8;margin-top:6px;'>"
        "<span><span style='color:#3B82F6'>■</span> Interest on drawn FB principal</span>"
        "<span><span style='color:#F59E0B'>■</span> Commission on NFB sanctioned face</span>"
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
        marker_color=fm["color"].tolist(),
        text=[f"{r:.2f}%" for r in fm["rate_pct"]],
        textposition="outside",
        textfont=dict(size=10, color="#F1F5F9"),
        customdata=list(zip(fm["Effective_OS"], fm["Effective_OS"] * fm["Effective_Rate"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Rate: %{x:.2f}%<br>"
            "Outstanding: ₹%{customdata[0]:.1f} Cr<br>"
            "Annual Interest: ₹%{customdata[1]:.2f} Cr<extra></extra>"
        ),
    ))
    fig.add_vline(
        x=wac * 100,
        line=dict(color="#F59E0B", width=2, dash="dash"),
        annotation=dict(text=f"Portfolio WAC: {wac*100:.2f}%",
                        font=dict(color="#F59E0B")),
    )
    fig.update_layout(
        height=max(280, 26 * len(fm)),
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(title="Effective Interest Rate (%)  ·  fund-based facilities only",
                   gridcolor="#334155", color="#94A3B8"),
        yaxis=dict(color="#F1F5F9", autorange="reversed"),
        margin=dict(l=20, r=20, t=20, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


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
        "Term Loan":         "#3B82F6",
        "WC Fund-Based":     "#8B5CF6",
        "FX Buyer's Credit": "#06B6D4",
        "FD-Backed FB":      "#10B981",
        "NFB (LC/SBLC/BG)":  "#F59E0B",
    }

    fig = go.Figure()
    for cat in pivot.columns:
        fig.add_trace(go.Bar(
            name=cat,
            y=list(pivot.index),
            x=pivot[cat].values,
            orientation="h",
            marker_color=cat_colors.get(cat, "#94A3B8"),
            text=[f"₹{v:.0f}" if v >= 20 else "" for v in pivot[cat].values],
            textposition="inside",
            textfont=dict(color="white", size=10),
            hovertemplate=f"<b>%{{y}}</b><br>{cat}: ₹%{{x:,.1f}} Cr (sanctioned)<extra></extra>",
        ))

    totals = pivot.sum(axis=1)
    grand = totals.sum()
    for lender, total in totals.items():
        fig.add_annotation(
            x=total + grand * 0.012, y=lender, text=f"<b>₹{total:.0f}</b>",
            showarrow=False, font=dict(color="#F1F5F9", size=11),
            xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        height=max(320, 35 * len(pivot)),
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(title=f"Sanctioned Capacity (₹ Cr)  ·  total ties to ₹{grand:,.0f} Cr",
                    gridcolor="#334155", color="#94A3B8",
                    range=[0, totals.max() * 1.22]),
        yaxis=dict(autorange="reversed", color="#F1F5F9"),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
        margin=dict(l=20, r=20, t=20, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)


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
        height=440,
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(title="Financial Year-End", gridcolor="#334155", color="#94A3B8",
                    tickangle=-30),
        yaxis=dict(title="Term Loan Outstanding (₹ Cr)",
                    gridcolor="#334155", color="#94A3B8"),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.22,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
        margin=dict(l=20, r=20, t=20, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)


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
        if d <= 30: return "#EF4444"
        if d <= 60: return "#F59E0B"
        if d <= 90: return "#3B82F6"
        if d <= 180: return "#8B5CF6"
        return "#64748B"

    fm["color"] = fm["days"].apply(_color)
    fm["expiry_str"] = fm["Validity_Date"].dt.strftime("%d-%b-%Y")

    fig = go.Figure()
    fig.add_vrect(x0=-40, x1=0, fillcolor="rgba(127,29,29,0.18)", line_width=0, layer="below")
    fig.add_vrect(x0=0, x1=30,  fillcolor="rgba(239,68,68,0.10)", line_width=0, layer="below")
    fig.add_vrect(x0=30, x1=60, fillcolor="rgba(245,158,11,0.08)", line_width=0, layer="below")
    fig.add_vrect(x0=60, x1=90, fillcolor="rgba(59,130,246,0.06)", line_width=0, layer="below")
    fig.add_vrect(x0=90, x1=180, fillcolor="rgba(139,92,246,0.05)", line_width=0, layer="below")
    fig.add_vrect(x0=180, x1=400, fillcolor="rgba(100,116,139,0.04)", line_width=0, layer="below")

    fig.add_trace(go.Bar(
        x=fm["days"], y=fm["label"], orientation="h",
        marker=dict(color=fm["color"].tolist(), line=dict(color="#0F172A", width=0.5)),
        text=[f"{d:+d}d · {date}" for d, date in zip(fm["days"], fm["expiry_str"])],
        textposition="outside",
        textfont=dict(size=10, color="#F1F5F9"),
        customdata=list(zip(fm["expiry_str"], fm["Sanction_INR"], fm["Category"])),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Expires: %{customdata[0]}<br>"
            "Days to expiry: %{x:+d}<br>"
            "Sanction: ₹%{customdata[1]:.1f} Cr<br>"
            "Category: %{customdata[2]}<extra></extra>"
        ),
        showlegend=False,
    ))
    for d, color in [(0, "#94A3B8"), (30, "#EF4444"), (60, "#F59E0B"),
                      (90, "#3B82F6"), (180, "#8B5CF6")]:
        fig.add_vline(x=d, line=dict(color=color, width=1, dash="dot"))

    fig.update_layout(
        height=max(450, 22 * len(fm)),
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(title="Days to Expiry (negative = overdue)",
                    gridcolor="#334155", color="#94A3B8",
                    range=[-40, max(200, fm["days"].max() + 60)]),
        yaxis=dict(autorange="reversed", color="#F1F5F9"),
        margin=dict(l=20, r=180, t=20, b=60),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(
        "<div style='display:flex;gap:18px;justify-content:center;font-size:0.82rem;"
        "color:#94A3B8;margin-top:4px;flex-wrap:wrap;'>"
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
            line=dict(color=color, width=2.5),
            marker=dict(size=7),
            hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:.2f}}x<extra></extra>",
        ))

    fig.add_hline(y=1.25, line=dict(color="#EF4444", width=1, dash="dash"),
                  annotation=dict(text="DSCR floor 1.25x", font=dict(color="#FCA5A5")))
    fig.add_hline(y=4.0, line=dict(color="#F59E0B", width=1, dash="dot"),
                  annotation=dict(text="LTD/EBITDA cap 4.0x", font=dict(color="#FCD34D")))

    fig.update_layout(
        height=400,
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(gridcolor="#334155", color="#94A3B8"),
        yaxis=dict(title="Ratio (x)", gridcolor="#334155", color="#94A3B8",
                    range=[0, 7]),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.18,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
        margin=dict(l=20, r=20, t=40, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════
# 5-BUCKET DONUT
# ════════════════════════════════════════════════════════════════════
def render_bucket_donut(data: Dict[str, Any]):
    """Headline 5-bucket view: B1 + B2 + B3 + B4 + Hedge memo."""
    t = data["totals"]
    labels = [
        f"B1 FB Mains<br>₹{t['FB_Mains_B1']:.0f} Cr",
        f"B2 NFB Mains<br>₹{t['NFB_Mains_B2']:.0f} Cr",
        f"B3 FD-Backed<br>₹{t['FD_Backed_B3']:.0f} Cr",
        f"B4 Uncommitted<br>₹{t['Uncommitted_B4']:.0f} Cr",
        f"Hedge memo<br>₹{t['Hedge_Memo']:.0f} Cr",
    ]
    values = [t['FB_Mains_B1'], t['NFB_Mains_B2'],
              t['FD_Backed_B3'], t['Uncommitted_B4'], t['Hedge_Memo']]
    colors = ["#3B82F6", "#F59E0B", "#10B981", "#94A3B8", "#EC4899"]

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#0F172A", width=2)),
        hole=0.55, textinfo="label+percent",
        textfont=dict(color="white", size=11),
        hovertemplate="<b>%{label}</b><br>₹%{value:.0f} Cr<br>%{percent}<extra></extra>",
    )])
    total = sum(values)
    fig.update_layout(
        height=400,
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        annotations=[dict(text=f"<b>₹{total:,.0f}</b><br>"
                              f"<span style='font-size:0.85rem;color:#94A3B8'>Cr Total Committed</span>",
                          x=0.5, y=0.5, font=dict(size=22, color="#F1F5F9"),
                          showarrow=False)],
    )
    st.plotly_chart(fig, use_container_width=True)


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
        marker_color="#3B82F6",
        text=[f"{v:.2f}" for v in base_v], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Stress", x=labels, y=stress_v,
        marker_color="#F59E0B",
        text=[f"{v:.2f}" for v in stress_v], textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="Threshold", x=labels, y=thresholds,
        mode="markers",
        marker=dict(symbol="line-ew", size=20, color="#EF4444",
                     line=dict(width=3)),
    ))
    fig.update_layout(
        barmode="group",
        height=380,
        plot_bgcolor="#0F172A", paper_bgcolor="#0F172A",
        font=dict(color="#F1F5F9", family="Inter, sans-serif"),
        xaxis=dict(gridcolor="#334155", color="#94A3B8"),
        yaxis=dict(gridcolor="#334155", color="#94A3B8"),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.15,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
        margin=dict(l=20, r=20, t=20, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)
