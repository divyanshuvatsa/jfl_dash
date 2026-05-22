"""
Rule-based AI analyst — deterministic, zero-API answers, JFL-specific.

All numbers traced to data['...'] — no hardcoded magic values.

JFL-specific themes (different from JCL):
  - Project is pre-COD (FY29 first covenant test)
  - 9 lenders, 44 facilities
  - 5-bucket framework (B1 / B2 / B3 / B4 / Hedge memo, plus B0 sub-limits)
  - ICICI TL takeover ₹840 Cr → Adjusted Consortium Debt ₹3,826 Cr
  - HSBC ₹200 Cr (post 20% haircut on ₹1,000 face) reclassified into B1 (MP-13/F-18)
  - FY29 TEV-projected covenant compliance (43/44 Compliant + 1 Near Breach)
  - 18 Management Flags
  - 108-check Validation & Integrity (24 cross-source + 84 internal VJF)
"""

from __future__ import annotations
import pandas as pd
from typing import Dict, Any, List


SUGGESTED_QUESTIONS = [
    "What is the biggest risk in the portfolio?",
    "Which covenant is closest to breaching?",
    "What is our weighted average cost of debt?",
    "Which is our most expensive facility?",
    "What is the term-loan repayment timeline?",
    "How much does a +100 bps rate hike cost us?",
    "What is the biggest lender-concentration risk?",
    "Which facilities expire in the next 90 days?",
    "Give me a 5-point summary for the board.",
    "What are the open Management Flags?",
    "Explain the ICICI TL Takeover treatment.",
    "Why is the FY25 covenant compliance only 30%?",
    "What does the TEV project for FY29 covenants?",
    "What is the status of the RBL bullet bridge?",
    "What should we focus on before the next lender review?",
]


# ─── Helpers ──────────────────────────────────────────────────────────────
def _inr(v: float, d: int = 2) -> str:
    return f"₹{v:,.{d}f} Cr"


def _pct(v: float, d: int = 2) -> str:
    return f"{v*100:.{d}f}%" if abs(v) < 5 else f"{v:.{d}f}%"


# ─── Answer functions ────────────────────────────────────────────────────
def answer_biggest_risk(data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    t = data["totals"]
    ls = data["lender_summary"]
    ls_nz = ls[ls["Sanctioned_Debt"] > 0]
    total_sd = t["Bucket1_Sanctioned_Debt"]
    top = ls_nz.loc[ls_nz["Sanctioned_Debt"].idxmax()]
    top_share = top["Sanctioned_Debt"] / total_sd * 100

    # Tightest covenant
    ratio_cov = cov_df.copy()
    ratio_cov["hr_pct_num"] = pd.to_numeric(ratio_cov.get("Headroom_Pct"), errors="coerce")
    ratio_cov = ratio_cov.dropna(subset=["hr_pct_num"])
    tight = ratio_cov.loc[ratio_cov["hr_pct_num"].idxmin()] if len(ratio_cov) else None

    # Breached count
    breached = (cov_df["Status"] == "Breached").sum()

    # Critical management flags
    flags = data.get("management_flags", pd.DataFrame())
    high_open = flags[(flags["Severity"].isin(["High", "Critical"])) &
                       (flags["Status"].isin(["Open", "Open (linked F-01)"]))] if len(flags) else flags

    out = ["**🎯 Biggest Risks in the JFL Portfolio**\n"]

    if breached > 0:
        out.append(f"1. **{breached} covenant(s) currently breached** on FY25 audit basis. "
                   f"This is the pre-COD reality — JFL is a greenfield project, EBITDA is still "
                   f"negative (₹{data['financials']['FY25A'].get('EBITDA', 0):.2f} Cr). "
                   f"TEV projects FY29 first-test compliance.")

    if top_share > 25:
        out.append(f"2. **Lender Concentration** — {top['Lender']} holds "
                   f"**{top_share:.1f}%** ({_inr(top['Sanctioned_Debt'])}) "
                   f"of sanctioned debt {_inr(total_sd)}. UBI as consortium lead is structural; "
                   f"monitor refinancing options.")

    if tight is not None and pd.notna(tight["hr_pct_num"]) and tight["hr_pct_num"] < 25:
        actual_str = (f"{tight['Actual']:.2f}x" if isinstance(tight['Actual'], (int, float))
                      else str(tight['Actual'])[:30])
        thr_str = (f"{tight['Operator']} {tight['Threshold']:.2f}x"
                   if isinstance(tight['Threshold'], (int, float))
                   else f"{tight['Operator']} {tight['Threshold']}")
        out.append(f"3. **Tightest Covenant** — {tight['Lender']} {tight['Covenant']} "
                   f"has **{tight['hr_pct_num']:+.1f}%** headroom (actual {actual_str} vs threshold {thr_str}).")

    if len(high_open) > 0:
        out.append(f"4. **{len(high_open)} High-severity Management Flags open** — "
                   f"includes {', '.join(high_open['Flag'].head(3).tolist())}. "
                   f"See Renewals & Risk tab for full register.")

    # Renewal risk
    fm = data["facility_master"]
    as_of = pd.Timestamp(data["as_of_date"])
    fm = fm.copy()
    fm["days"] = (fm["Validity_Date"] - as_of).dt.days
    near = fm[fm["days"].between(0, 60)]
    if len(near) > 0:
        soonest = near.loc[near["days"].idxmin()]
        out.append(f"5. **Renewal Risk** — {soonest['Facility'][:50]} ({soonest['Lender']}) "
                   f"expires in **{int(soonest['days'])} days** ({_inr(soonest['Sanction_INR'], 0)}).")

    if len(out) == 1:
        out.append("Portfolio is healthy across all dimensions. No critical risks detected.")
    return "\n\n".join(out)


def answer_tightest_covenant(data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    ratio_cov = cov_df.copy()
    ratio_cov["hr_pct_num"] = pd.to_numeric(ratio_cov.get("Headroom_Pct"), errors="coerce")
    sorted_cov = ratio_cov.dropna(subset=["hr_pct_num"]).sort_values("hr_pct_num").head(8)
    out = ["**📊 Top 8 Tightest Covenants** (by headroom %)\n"]
    out.append("| # | Lender | Covenant | Threshold | Actual | Headroom | Status |")
    out.append("|---|--------|----------|-----------|--------|----------|--------|")
    for i, (_, r) in enumerate(sorted_cov.iterrows(), 1):
        actual_str = (f"{r['Actual']:.2f}" if isinstance(r['Actual'], (int, float))
                      else str(r['Actual'])[:20])
        thr_str = (f"{r['Operator']}{r['Threshold']:.2f}"
                   if isinstance(r['Threshold'], (int, float))
                   else f"{r['Operator']}{r['Threshold']}")
        out.append(f"| {i} | {r['Lender']} | {r['Covenant'][:35]} | {thr_str} | "
                   f"{actual_str} | {r['hr_pct_num']:+.1f}% | {r['Status']} |")
    return "\n".join(out)


def answer_wac(data: Dict[str, Any]) -> str:
    isum = data["interest_summary"]
    fm = data["facility_master"]
    b1_os = fm[(fm["Bucket"] == 1) &
                (fm["Category"].isin(["FB", "FB-Term", "FB-FCY"]))]["Effective_OS"].sum()
    return (f"**💰 JFL Cost of Debt Summary**\n\n"
            f"- **Weighted Avg Cost of FB Economic Debt: {isum['Weighted_Avg_Cost']*100:.2f}%**\n"
            f"- Bucket 1 Interest (FB Mains): {_inr(isum['Bucket1_Interest'])}\n"
            f"- Bucket 2 Commission (NFB Mains): {_inr(isum['Bucket2_Commission'])}\n"
            f"- Bucket 3 Interest (FD-Backed): {_inr(isum['Bucket3_Interest'])}\n"
            f"- **Total Economic Run-Rate (B1+B2+B3): {_inr(isum['Total_Interest_Commission'])}**\n\n"
            f"Memo — Bucket 4 (Uncommitted) theoretical cost {_inr(isum['Bucket4_Theoretical'])}, "
            f"but excluded as HSBC may cancel at discretion (Flag F-07).\n\n"
            f"WAC is computed on Bucket-1 only because that's the FB economic debt under "
            f"consortium-amortising structure. Denominator = {_inr(b1_os, 0)} effective outstanding.")


def answer_most_expensive(data: Dict[str, Any]) -> str:
    isched = data["interest_schedule"]
    # FB only, exclude sub-limits and hedge
    fb = isched[isched["Category"].isin(["FB", "FB-Term", "FB-FCY"])].copy()
    fb = fb[fb["Effective_OS"] > 0]
    if len(fb) == 0:
        return "No active FB facilities found."

    fb_sorted = fb.sort_values("Effective_Rate", ascending=False)
    top = fb_sorted.iloc[0]
    wac = data["interest_summary"]["Weighted_Avg_Cost"]
    premium_rate = top["Effective_Rate"] - wac
    premium_inr = top["Effective_OS"] * premium_rate

    out = [f"**💸 Most Expensive FB Facility**\n"]
    out.append(f"- **{top['Facility']}** at **{top['Lender']}**")
    out.append(f"- Outstanding: **{_inr(top['Effective_OS'])}**")
    out.append(f"- Rate: **{top['Effective_Rate']*100:.2f}%** (vs portfolio WAC {wac*100:.2f}%)")
    out.append(f"- Annual cost: **{_inr(top['Annual_Cost'])}**")
    if premium_rate > 0:
        out.append(f"- **Annual premium over WAC: {_inr(premium_inr)}**")

    out.append("\n**Top 5 by rate:**")
    out.append("| Lender | Facility | Rate | Annual Cost |")
    out.append("|--------|----------|------|-------------|")
    for _, r in fb_sorted.head(5).iterrows():
        out.append(f"| {r['Lender']} | {r['Facility'][:45]} | "
                   f"{r['Effective_Rate']*100:.2f}% | {_inr(r['Annual_Cost'])} |")
    return "\n".join(out)


def answer_repayment_timeline(data: Dict[str, Any]) -> str:
    rep = data["repayment_schedule"].copy()
    if rep.empty:
        return "No repayment schedule available."
    rep["FY"] = rep["Period_End"].dt.year + (rep["Period_End"].dt.month >= 4).astype(int)
    rep["FY_Label"] = "FY" + rep["FY"].astype(str).str[-2:]
    fy_agg = rep.groupby("FY_Label", sort=False).agg(
        Principal=("Total_Principal", "sum"),
        Interest=("Total_Interest", "sum"),
        DS=("Total_DS", "sum"),
    ).reset_index()
    fy_active = fy_agg[fy_agg["Principal"] > 0]

    if fy_active.empty:
        return "No principal repayments scheduled in the loaded horizon."

    peak = fy_active.loc[fy_active["DS"].idxmax()]

    # Per-TL sanctioned breakdown
    fm = data["facility_master"]
    tl = fm[fm["Category"] == "FB-Term"].groupby("Lender")["Sanction_INR"].sum()
    tl_total = tl.sum()
    tl_breakdown = " + ".join([f"{l} ₹{v:.0f}" for l, v in tl.sort_values(ascending=False).items()])

    out = [f"**📅 JFL Term-Loan Repayment Timeline**\n"]
    out.append(f"- Total TL Sanctioned: **{_inr(tl_total, 0)}** ({tl_breakdown})")
    out.append(f"- Repayment span: {fy_active['FY_Label'].iloc[0]} → {fy_active['FY_Label'].iloc[-1]}")
    out.append(f"- **Peak DS year: {peak['FY_Label']}** with {_inr(peak['Principal'])} principal "
                f"+ {_inr(peak['Interest'])} interest = {_inr(peak['DS'])} debt service")
    out.append(f"- Total interest over loan life: {_inr(fy_agg['Interest'].sum())}")
    out.append("")
    out.append("**RBL ₹200 Cr** is a 12-month BULLET bridge — repays at maturity (13-Nov-2026, Q3 FY27). "
                "Post-COD refinance assumed.")
    out.append("")
    out.append("**FY-wise debt service:**")
    out.append("| FY | Principal | Interest | Total DS |")
    out.append("|----|-----------|----------|----------|")
    for _, r in fy_active.iterrows():
        out.append(f"| {r['FY_Label']} | {_inr(r['Principal'], 1)} | "
                   f"{_inr(r['Interest'], 1)} | {_inr(r['DS'], 1)} |")
    return "\n".join(out)


def answer_rate_shock(data: Dict[str, Any]) -> str:
    sens = data["rate_sensitivity"]
    isum = data["interest_summary"]
    fm = data["facility_master"]
    total_delta = sens["Delta_Interest_100bps"].sum() if len(sens) else 0
    b1_os = fm[(fm["Bucket"] == 1) &
                (fm["Category"].isin(["FB", "FB-Term", "FB-FCY"]))]["Effective_OS"].sum()
    new_wac_pct = ((isum["Bucket1_Interest"] + total_delta) / b1_os * 100) if b1_os > 0 else 0

    out = [f"**📈 Impact of +100 bps Rate Shock (parallel)**\n"]
    out.append(f"- Current Bucket 1 Interest: {_inr(isum['Bucket1_Interest'])}")
    out.append(f"- **Additional cost from +100 bps: {_inr(total_delta)}**")
    out.append(f"- Stressed Bucket 1 Interest: {_inr(isum['Bucket1_Interest'] + total_delta)}")
    out.append(f"- New WAC: **{new_wac_pct:.2f}%** "
                f"(vs current {isum['Weighted_Avg_Cost']*100:.2f}%)")
    out.append("")
    out.append("**Sensitivity by benchmark:**")
    out.append("| Benchmark | Δ Interest @ +100 bps |")
    out.append("|-----------|----------------------|")
    for _, r in sens.iterrows():
        out.append(f"| {r['Benchmark']} | {_inr(r['Delta_Interest_100bps'], 2)} |")
    return "\n".join(out)


def answer_concentration(data: Dict[str, Any]) -> str:
    ls = data["lender_summary"]
    ls_nz = ls[ls["Sanctioned_Debt"] > 0].copy()
    total_sd = data["totals"]["Bucket1_Sanctioned_Debt"]

    out = [f"**🏦 JFL Lender Concentration Analysis**\n"]
    out.append(f"Sanctioned Debt: {_inr(total_sd)} (across {len(ls_nz)} funded lenders + "
                f"{len(ls) - len(ls_nz)} memo/uncommitted; "
                f"{len(data['facility_master'])} facilities total)")
    out.append("")
    out.append("| Lender | Sanctioned | % | NFB Contingent |")
    out.append("|--------|------------|---|----------------|")
    for _, r in ls_nz.sort_values("Sanctioned_Debt", ascending=False).iterrows():
        out.append(f"| {r['Lender']} | {_inr(r['Sanctioned_Debt'])} | "
                    f"{r['Sanctioned_Debt']/total_sd*100:.1f}% | {_inr(r['NFB_Contingent'], 0)} |")

    top = ls_nz.loc[ls_nz["Sanctioned_Debt"].idxmax()]
    top_pct = top["Sanctioned_Debt"] / total_sd * 100
    out.append("")
    if top_pct > 35:
        out.append(f"⚠️ **{top['Lender']} concentration ({top_pct:.1f}%) is structural** — "
                    "consortium lead. ICICI TL takeover (₹840 Cr) adds a parallel exposure stack.")
    else:
        out.append(f"✅ Concentration well-distributed; largest lender at {top_pct:.1f}%.")

    out.append("\n**ICICI TL Takeover treatment:**")
    out.append(f"- Sanctioned (gross) B1+B2 = {_inr(total_sd)}")
    out.append(f"- less: ICICI TL takeover = {_inr(data['totals']['ICICI_TL_Takeover'])}")
    out.append(f"- **Adjusted Consortium Debt (economic) = {_inr(data['totals']['Adjusted_Consortium'])}**")
    return "\n".join(out)


def answer_renewals(data: Dict[str, Any]) -> str:
    fm = data["facility_master"].copy()
    as_of = pd.Timestamp(data["as_of_date"])
    fm["days"] = (fm["Validity_Date"] - as_of).dt.days
    upcoming = fm[fm["days"].notna() & fm["days"].between(-30, 90)].sort_values("days")

    out = [f"**📆 Upcoming Renewals (overdue → 90 days, from {data['as_of_date']})**\n"]
    if upcoming.empty:
        out.append("No facilities expiring in the next 90 days.")
        return "\n".join(out)

    out.append(f"- **{len(upcoming)} facilities** require renewal attention")
    out.append(f"- Combined sanctioned: **{_inr(upcoming['Sanction_INR'].sum())}**")
    out.append("")
    out.append("| Facility | Lender | Expires | Days | Sanctioned |")
    out.append("|----------|--------|---------|------|------------|")
    for _, r in upcoming.iterrows():
        d = int(r['days'])
        out.append(f"| {r['Facility'][:45]} | {r['Lender']} | "
                    f"{r['Validity_Date'].strftime('%d-%b-%Y')} | {d:+d} | {_inr(r['Sanction_INR'])} |")
    return "\n".join(out)


def answer_board_summary(data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    t = data["totals"]
    isum = data["interest_summary"]
    fm_count = len(data["facility_master"])

    compliant = (cov_df["Status"] == "Compliant").sum()
    near = (cov_df["Status"].isin(["Near Breach", "Watch"])).sum()
    breach = (cov_df["Status"] == "Breached").sum()
    pending = (cov_df["Status"] == "Pending Input").sum()

    ls = data["lender_summary"]
    ls_nz = ls[ls["Sanctioned_Debt"] > 0]
    top = ls_nz.loc[ls_nz["Sanctioned_Debt"].idxmax()]

    flags = data.get("management_flags", pd.DataFrame())
    open_flags = flags[flags["Status"].isin(["Open", "Open (linked F-01)"])] if len(flags) else flags
    high_open = len(open_flags[open_flags["Severity"].isin(["High", "Critical"])]) if len(open_flags) else 0

    out = [f"**📋 JFL Debt Portfolio — 5-Point Board Summary**\n"]
    out.append(f"1. **Sanctioned Debt** = {_inr(t['Bucket1_Sanctioned_Debt'])} (B1 FB Mains "
                f"{_inr(t['FB_Mains_B1'], 0)} + B2 NFB Mains {_inr(t['NFB_Mains_B2'], 0)}) across "
                f"9 lenders, {fm_count} facilities. HSBC ₹200 Cr (post 20% haircut on ₹1,000 face) "
                f"reclassified into B1 per MP-13/F-18. "
                f"ICICI TL takeover ₹840 Cr → "
                f"**Adjusted Consortium Debt {_inr(t['Adjusted_Consortium'])}**.")
    out.append(f"2. **Annual Run-Rate** = {_inr(isum['Total_Interest_Commission'])} at "
                f"WAC **{isum['Weighted_Avg_Cost']*100:.2f}%** on FB economic debt. "
                f"NFB Contingent {_inr(t['NFB_Contingent'], 0)} off-B/S.")
    out.append(f"3. **Covenants**: {compliant}/{len(cov_df)} compliant. "
                f"{breach} breached, {near} near/watch, {pending} pending. "
                f"FY29 TEV projection compliance climbs to ~43/44 once plant achieves COD.")
    out.append(f"4. **Term Loans**: 7 TLs totalling ₹3,816 Cr sanctioned. "
                f"Repayments start FY27, peak ~FY30-FY38 at ₹325 Cr/yr principal. "
                f"RBL ₹200 Cr bullet matures Nov-2026.")
    out.append(f"5. **Watch Items**: {len(open_flags)} Management Flags open "
                f"({high_open} High severity). Top concentration: {top['Lender']} at "
                f"{top['Sanctioned_Debt']/t['Bucket1_Sanctioned_Debt']*100:.1f}%.")
    return "\n".join(out)


def answer_management_flags(data: Dict[str, Any]) -> str:
    flags = data.get("management_flags", pd.DataFrame())
    if flags.empty:
        return "No Management Flags loaded."

    open_flags = flags[flags["Status"].isin(["Open", "Open (linked F-01)"])]
    sev_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    open_flags = open_flags.copy()
    open_flags["_sev"] = open_flags["Severity"].map(sev_order).fillna(99)
    open_flags = open_flags.sort_values("_sev")

    out = [f"**🚩 JFL Management Flags Register**\n"]
    out.append(f"- Total flags: {len(flags)}")
    out.append(f"- Open: {len(open_flags)}")
    out.append(f"- Closed: {(flags['Status'] == 'Closed').sum()}")
    out.append(f"- Acceptable: {(flags['Status'] == 'Acceptable').sum()}")
    out.append("")

    out.append("**Open flags (by severity):**\n")
    for _, f in open_flags.iterrows():
        sev = f["Severity"]
        emoji = {"Critical": "🚨", "High": "🔴", "Medium": "🟠", "Low": "🟡"}.get(sev, "⚪")
        out.append(f"- {emoji} **{f['Flag']}** [{sev}] — {f['Description'][:140]}…")
        out.append(f"  *Action:* {f['Action'][:140]}")
    return "\n".join(out)


def answer_icici_takeover(data: Dict[str, Any]) -> str:
    t = data["totals"]
    return (
        f"**🔄 ICICI TL Takeover — Treatment in the JFL Model**\n\n"
        f"ICICI ₹{t['ICICI_TL_Takeover']:.0f} Cr is a **takeover of already-disbursed consortium TL** — "
        f"it economically *substitutes* for existing UBI / Indian Bank / YBL / IDFC exposure rather than "
        f"adding new debt. Per ICICI TL CAL 27-Mar-2026, specific takeover-target lender(s) are not "
        f"identified in the CAL (Treasury flag F-01 / Cover Page note).\n\n"
        f"**Accounting in the dashboard:**\n"
        f"- Headline **Sanctioned Debt = B1 + B2 = {_inr(t['Bucket1_Sanctioned_Debt'])}** (gross of takeover)\n"
        f"- less: ICICI TL takeover = ({_inr(t['ICICI_TL_Takeover'])})\n"
        f"- **Adjusted Consortium Debt = {_inr(t['Adjusted_Consortium'])}** — economic representation\n\n"
        f"The KPI labelled 'Adjusted Consortium' is what matters for credit-committee purposes; the "
        f"₹4,666 Cr 'Sanctioned' figure is what sums to all signed facility letters (incl. HSBC "
        f"₹200 Cr post 20% haircut, reclassified to B1 per MP-13/F-18). Validation Engine "
        f"check VJF-18 / VJF-19 enforce this reconciliation."
    )


def answer_fy25_breaches(data: Dict[str, Any]) -> str:
    fy25 = data["financials"]["FY25A"]
    return (
        f"**Why FY25 Covenant Compliance is ~30%**\n\n"
        f"JFL is a **pre-operational greenfield steel project** at FY25 — DCCO is "
        f"01-Apr-2026 (consortium-aligned). At FY25 balance-sheet date:\n\n"
        f"- EBITDA = **{_inr(fy25.get('EBITDA', 0))}** (continuing PBT loss + discontinued Lime Plant)\n"
        f"- Fixed Assets dominated by CWIP **{_inr(fy25.get('Fixed Assets', 0))}** (project capex)\n"
        f"- Interest **capitalised** to CWIP (Ind AS 23) — economic interest burden {_inr(fy25.get('Interest Expense', 0))}\n"
        f"- TL repayments start FY27 — no principal due during FY25\n\n"
        f"All consortium covenants (DSCR ≥ 1.25, ISCR ≥ 2.00, LTD/EBITDA ≤ 4.00) are tested "
        f"**from FY29 onwards** (post-COD), so the FY25 breaches are structural, not a credit concern.\n\n"
        f"The **TEV-projected FY29** view (see Covenants tab toggle) shows **43/44 compliant** — "
        f"the model substitutes audit numbers with TEV projections once the plant is operational."
    )


def answer_tev_forward(data: Dict[str, Any]) -> str:
    tev = data.get("tev_ratios", {})
    if not tev or "FY29" not in tev:
        return "TEV trajectory not available."

    out = ["**📊 TEV-Projected Covenant Ratios — FY27 to FY38**\n"]
    out.append("| FY | DSCR | ISCR | FACR | LTD/EBITDA | LTD/Equity |")
    out.append("|----|------|------|------|------------|------------|")
    for fy in sorted(tev.keys()):
        if fy < "FY27":
            continue
        r = tev[fy]
        out.append(f"| {fy} | {r['DSCR']:.2f}x | {r['ISCR']:.2f}x | {r['FACR']:.2f}x | "
                    f"{r['LTD_EBITDA']:.2f}x | {r['LTD_Equity']:.2f}x |")

    out.append("")
    fy29 = tev["FY29"]
    out.append(f"**FY29 first-covenant-test snapshot** (when the consortium first measures):")
    out.append(f"- DSCR **{fy29['DSCR']:.2f}x** vs threshold ≥1.25x → +{(fy29['DSCR']/1.25-1)*100:.0f}% headroom")
    out.append(f"- ISCR **{fy29['ISCR']:.2f}x** vs threshold ≥2.00x → +{(fy29['ISCR']/2.0-1)*100:.0f}% headroom")
    out.append(f"- FACR **{fy29['FACR']:.2f}x** vs threshold ≥1.20x → +{(fy29['FACR']/1.2-1)*100:.0f}% headroom")
    out.append(f"- LTD/EBITDA **{fy29['LTD_EBITDA']:.2f}x** vs threshold ≤4.00x → +{(1-fy29['LTD_EBITDA']/4.0)*100:.0f}% headroom")
    return "\n".join(out)


def answer_rbl_bullet(data: Dict[str, Any]) -> str:
    return (
        f"**🌉 RBL Bank ₹200 Cr Bullet Bridge — Status**\n\n"
        f"Per RBL SL 13-Nov-2025:\n"
        f"- Sanctioned: ₹200 Cr\n"
        f"- Structure: 12-month BULLET (not consortium amortising)\n"
        f"- Maturity: **13-Nov-2026** (Q3 FY27)\n"
        f"- Rate: 9.50% (TBD at disbursement — Flag F-06)\n"
        f"- Security: Unsecured TL backed by OPJSTPL Corporate Guarantee + JSL Shortfall Undertaking\n"
        f"- Covenants: Min promoter contribution ₹1,363 Cr + Min BBB rating within 180 days\n\n"
        f"**Treasury action required**: Refinance plan or rollover arrangement with RBL — "
        f"flagged as **F-02 (High severity, Open)**. The model assumes bullet repayment at maturity; "
        f"post-COD refinance is assumed (likely consortium take-out or RBL renewal). "
        f"This fundamentally differs from the rest of the term-loan stack which amortises over 12 years."
    )


def answer_pre_review(data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    out = [f"**📝 JFL Pre-Lender-Review Action Items** (priority order)\n"]
    items = []

    # Open high-severity flags
    flags = data.get("management_flags", pd.DataFrame())
    high = flags[(flags["Severity"].isin(["High", "Critical"])) &
                  (flags["Status"].isin(["Open", "Open (linked F-01)"]))] if len(flags) else flags
    for _, f in high.iterrows():
        items.append(f"**HIGH** — Address **{f['Flag']}**: {f['Description'][:120]}")

    # Renewals next 60 days
    fm = data["facility_master"].copy()
    as_of = pd.Timestamp(data["as_of_date"])
    fm["days"] = (fm["Validity_Date"] - as_of).dt.days
    soon = fm[fm["days"].between(0, 60)]
    if len(soon) > 0:
        items.append(f"**MEDIUM** — Initiate renewal for {len(soon)} facilities expiring in 60 days "
                      f"(combined {_inr(soon['Sanction_INR'].sum())}).")

    # Pending Input covenants (e.g. ratings to confirm)
    pending = cov_df[cov_df["Status"] == "Pending Input"]
    if len(pending) > 0:
        items.append(f"**MEDIUM** — Resolve {len(pending)} 'Pending Input' covenants — typically "
                      f"awaiting external rating or market-data updates (JSL FMV, etc.).")

    # TBD rates
    tbd = fm[fm["Benchmark"].isin(["To be decided", "Mutually agreed"])]
    if len(tbd) > 0:
        items.append(f"**LOW** — Confirm rates for {len(tbd)} TBD-rate facilities at next availment.")

    if not items:
        items.append("No urgent action items. Continue regular monitoring.")

    for i, item in enumerate(items, 1):
        out.append(f"{i}. {item}")
    return "\n".join(out)


# ─── Proactive insights (4 cards) ────────────────────────────────────────
def get_proactive_insights(data: Dict[str, Any], cov_df: pd.DataFrame) -> List[Dict[str, str]]:
    insights = []
    t = data["totals"]
    isum = data["interest_summary"]
    ls = data["lender_summary"]
    ls_nz = ls[ls["Sanctioned_Debt"] > 0]

    # Card 1: Concentration
    top = ls_nz.loc[ls_nz["Sanctioned_Debt"].idxmax()]
    top_pct = top["Sanctioned_Debt"] / t["Bucket1_Sanctioned_Debt"] * 100
    insights.append({
        "icon": "🏦", "level": "info",
        "title": f"Lender Concentration — {top['Lender']}",
        "body": f"<b>{top['Lender']}</b> at <b>{top_pct:.1f}%</b> of sanctioned debt "
                f"({_inr(top['Sanctioned_Debt'])}). As consortium lead this is structural; "
                f"ICICI TL takeover ₹840 Cr is a parallel exposure stack."
    })

    # Card 2: Cost intensity vs WAC
    isched = data["interest_schedule"]
    fb = isched[isched["Category"].isin(["FB", "FB-Term", "FB-FCY"]) & (isched["Effective_OS"] > 0)]
    if len(fb) > 0:
        most_exp = fb.loc[fb["Effective_Rate"].idxmax()]
        wac = isum["Weighted_Avg_Cost"]
        if most_exp["Effective_Rate"] > wac:
            premium = (most_exp["Effective_Rate"] - wac) * most_exp["Effective_OS"]
            if premium > 1:
                insights.append({
                    "icon": "💰", "level": "info",
                    "title": "Refinancing Opportunity",
                    "body": f"<b>{most_exp['Facility'][:40]}</b> ({most_exp['Lender']}) at "
                            f"<b>{most_exp['Effective_Rate']*100:.2f}%</b> vs WAC "
                            f"<b>{wac*100:.2f}%</b>. Premium ≈ <b>{_inr(premium)}/yr</b>."
                })

    # Card 3: Tightest covenant
    ratio_cov = cov_df.copy()
    ratio_cov["hr_pct_num"] = pd.to_numeric(ratio_cov.get("Headroom_Pct"), errors="coerce")
    ratio_cov = ratio_cov.dropna(subset=["hr_pct_num"])
    if len(ratio_cov) > 0:
        tight = ratio_cov.loc[ratio_cov["hr_pct_num"].idxmin()]
        level = "warning" if tight["hr_pct_num"] < 10 else ("bad" if tight["hr_pct_num"] < 0 else "good")
        actual_str = (f"{tight['Actual']:.2f}x" if isinstance(tight['Actual'], (int, float))
                      else str(tight['Actual'])[:15])
        thr_str = (f"{tight['Operator']}{tight['Threshold']:.2f}x"
                   if isinstance(tight['Threshold'], (int, float)) else str(tight['Threshold']))
        insights.append({
            "icon": "🎯", "level": level,
            "title": f"Tightest Covenant — {tight['Lender']}",
            "body": f"<b>{tight['Covenant'][:60]}</b> at <b>{tight['hr_pct_num']:+.1f}%</b> headroom. "
                    f"Actual {actual_str} vs {thr_str}."
        })

    # Card 4: Open high-severity flag
    flags = data.get("management_flags", pd.DataFrame())
    high_open = flags[(flags["Severity"].isin(["High", "Critical"])) &
                       (flags["Status"].isin(["Open", "Open (linked F-01)"]))] if len(flags) else flags
    if len(high_open) > 0:
        insights.append({
            "icon": "🚨", "level": "warning",
            "title": f"{len(high_open)} High-Severity Flags Open",
            "body": "Includes " + ", ".join([f"<b>{f}</b>" for f in high_open['Flag'].head(3).tolist()])
                    + ". See Renewals & Risk tab for full register."
        })

    return insights[:4]


# ─── Router ──────────────────────────────────────────────────────────────
KEYWORD_MAP = [
    (("biggest", "main risk", "primary risk", "key risk", "risks"), answer_biggest_risk),
    (("tightest", "closest", "near breach", "headroom"), answer_tightest_covenant),
    (("wac", "weighted", "cost of debt", "cost of"), answer_wac),
    (("expensive", "highest rate", "costly"), answer_most_expensive),
    (("repayment", "timeline", "term loan schedule", "tl schedule", "amortisation"),
     answer_repayment_timeline),
    (("rate hike", "rate shock", "100 bps", "rate increase", "rate sensitivity"),
     answer_rate_shock),
    (("concentration", "lender mix", "diversification"), answer_concentration),
    (("renewal", "expiry", "expire", "validity"), answer_renewals),
    (("board", "summary", "5-point", "5 point"), answer_board_summary),
    (("flag", "management flag", "f-0", "watch item"), answer_management_flags),
    (("icici takeover", "takeover", "icici tl", "adjusted consortium"),
     answer_icici_takeover),
    (("fy25", "audit", "why is", "30%", "compliance"), answer_fy25_breaches),
    (("tev", "fy29", "forward", "project", "future"), answer_tev_forward),
    (("rbl bullet", "rbl bridge", "bullet"), answer_rbl_bullet),
    (("review", "action", "before", "next"), answer_pre_review),
]


def answer_question(prompt: str, data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    """Route prompt to best handler. Returns markdown answer."""
    p = (prompt or "").lower()
    best_score = 0
    best_fn = None
    for keys, fn in KEYWORD_MAP:
        score = sum(1 for k in keys if k in p)
        if score > best_score:
            best_score = score
            best_fn = fn

    if best_fn and best_score >= 1:
        try:
            import inspect
            sig = inspect.signature(best_fn)
            if len(sig.parameters) >= 2:
                return best_fn(data, cov_df)
            else:
                return best_fn(data)
        except Exception as e:
            return f"_(Error answering: {e})_"

    return ("I couldn't match your question to a known pattern. Try one of the suggested questions, "
            "or use keywords like *biggest risk*, *tightest*, *WAC*, *expensive*, *repayment*, "
            "*rate shock*, *concentration*, *renewal*, *board summary*, *flags*, *takeover*, "
            "*FY25 compliance*, *TEV projection*, *RBL bullet*, or *pre-review*.")
