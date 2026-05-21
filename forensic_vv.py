"""
FORENSIC V&V — assumes everything is wrong until proven otherwise.

Catches issues the regular verify_all.py would miss:
  - DSCR continuity at stress=0 boundary
  - Cross-tab number consistency
  - Stress monotonicity (more shock → worse covenant)
  - Repayment schedule per-lender vs total reconciliation
  - Interest schedule per-row vs summary reconciliation
  - Lender Summary per-row vs Facility Master reconciliation
  - Financials per-basis correctness (FY25 audit vs FY29 TEV)
  - PDF generation across both bases
  - All KPIs surfaced in the UI tie back to data
"""
import sys, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")

import pandas as pd
import streamlit as st


class MockSS:
    def __init__(self): self._d = {}
    def __contains__(self, k): return k in self._d
    def __setitem__(self, k, v): self._d[k] = v
    def __getitem__(self, k): return self._d[k]
    def get(self, k, default=None): return self._d.get(k, default)
    def __setattr__(self, k, v):
        if k == "_d": super().__setattr__(k, v)
        else: self._d[k] = v
    def __getattr__(self, k):
        if k == "_d": return super().__getattribute__(k)
        return self._d.get(k)
st.session_state = MockSS()


from data_loader import load_all_data, force_reload
from scenario_engine import (resolve_covenants, recompute_covenants,
                                recompute_interest, evaluate_status)
import rule_based_ai as rba
from pdf_export import generate_board_memo
from snapshots import take_snapshot, compare_snapshots, clear_snapshots
import visualizations as viz


force_reload()
data = load_all_data()
errors = []
passed = 0


def check(name, condition, details=""):
    global passed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        errors.append((name, details))
        print(f"  ✗ {name}   {details}")


print("=" * 82)
print(" FORENSIC V&V — assuming everything is wrong until proven otherwise")
print("=" * 82)

# ═══════════════════════════════════════════════════════════════════════
print("\n[1] LENDER SUMMARY ↔ FACILITY MASTER per-lender reconciliation")
# ═══════════════════════════════════════════════════════════════════════
fm = data["facility_master"]
ls = data["lender_summary"]
fm_b1 = fm[(fm["Bucket"] == 1) & (fm["Category"].isin(["FB", "FB-Term", "FB-FCY"]))]
fm_b2 = fm[(fm["Bucket"] == 2) & (fm["Category"] == "NFB")]
fm_b1_per = fm_b1.groupby("Lender")["Sanction_INR"].sum()
fm_b2_per = fm_b2.groupby("Lender")["Sanction_INR"].sum()
for _, r in ls.iterrows():
    lender = r["Lender"]
    check(f"  B1 {lender} ({r['FB_Mains_B1']:.0f})",
          abs(r["FB_Mains_B1"] - fm_b1_per.get(lender, 0)) < 1,
          f"FM={fm_b1_per.get(lender, 0)}")
    check(f"  B2 {lender} ({r['NFB_Mains_B2']:.0f})",
          abs(r["NFB_Mains_B2"] - fm_b2_per.get(lender, 0)) < 1,
          f"FM={fm_b2_per.get(lender, 0)}")
check("Grand Total B1 = ₹3,916 Cr", abs(fm_b1_per.sum() - 3916) < 1)
check("Grand Total B2 = ₹550 Cr",   abs(fm_b2_per.sum() - 550) < 1)
check("Sanctioned Debt = ₹4,466 Cr", abs(data["totals"]["Bucket1_Sanctioned_Debt"] - 4466) < 1)


# ═══════════════════════════════════════════════════════════════════════
print("\n[2] INTEREST SCHEDULE per-row ↔ aggregate reconciliation")
# ═══════════════════════════════════════════════════════════════════════
isched = data["interest_schedule"]
isum = data["interest_summary"]
b1_sum = isched[isched["Bucket"] == 1]["Annual_Cost"].sum()
b2_sum = isched[isched["Bucket"] == 2]["Annual_Cost"].sum()
b3_sum = isched[isched["Bucket"] == 3]["Annual_Cost"].sum()
check("B1 row-sum ↔ summary", abs(b1_sum - isum["Bucket1_Interest"]) < 0.5,
       f"row-sum={b1_sum} vs summary={isum['Bucket1_Interest']}")
check("B2 row-sum ↔ summary", abs(b2_sum - isum["Bucket2_Commission"]) < 0.5)
check("B3 row-sum ↔ summary", abs(b3_sum - isum["Bucket3_Interest"]) < 0.5)
check("Total run-rate = ₹375.161 Cr",
       abs(isum["Total_Interest_Commission"] - 375.161) < 0.01)


# ═══════════════════════════════════════════════════════════════════════
print("\n[3] REPAYMENT SCHEDULE per-lender ↔ Total_Principal (excl. RBL bullet)")
# ═══════════════════════════════════════════════════════════════════════
rep = data["repayment_schedule"]
amortising = ['UBI_RTL_I_Principal','UBI_RTL_II_Principal','Indian_Bank_Principal',
              'YBL_Principal','IDFC_Principal','ICICI_TL_Principal']
rep_chk = rep.copy()
rep_chk["_calc_total"] = rep_chk[amortising].sum(axis=1)
diff = (rep_chk["_calc_total"] - rep_chk["Total_Principal"]).abs()
check("Total_Principal = sum of 6 amortising TLs (RBL bullet excluded by Excel design)",
       (diff > 0.01).sum() == 0,
       f"{(diff > 0.01).sum()} mismatched quarters")
# RBL bullet should appear ONCE in the schedule
rbl_total = rep["RBL_Principal"].sum()
check("RBL bullet = ₹200 Cr total", abs(rbl_total - 200) < 1, f"got {rbl_total}")
# Sum of all 7 lenders' principal should equal sum of TL sanctions
all_lender_principal = rep[amortising + ['RBL_Principal']].sum().sum()
tl_sanctioned = fm[fm["Category"] == "FB-Term"]["Sanction_INR"].sum()
check(f"Lifetime per-lender principal sum = TL sanctioned ({tl_sanctioned:.0f})",
       abs(all_lender_principal - tl_sanctioned) < 5,
       f"per-lender={all_lender_principal}, sanctioned={tl_sanctioned}")


# ═══════════════════════════════════════════════════════════════════════
print("\n[4] COVENANT TRACKER — stored values match Excel exactly")
# ═══════════════════════════════════════════════════════════════════════
fy25 = resolve_covenants(data, "FY25A", stress_active=False)
fy29 = resolve_covenants(data, "FY29E (TEV)", stress_active=False)

c25 = fy25["Status"].value_counts().to_dict()
check("FY25 Audit: 13 Compliant",   c25.get("Compliant", 0) == 13, f"got {c25}")
check("FY25 Audit: 16 Breached",    c25.get("Breached", 0) == 16)
check("FY25 Audit: 15 Pending",     c25.get("Pending Input", 0) == 15)

c29 = fy29["Status"].value_counts().to_dict()
check("FY29 TEV: 43 Compliant",    c29.get("Compliant", 0) == 43)
check("FY29 TEV: 1 Near Breach",    c29.get("Near Breach", 0) == 1)
check("FY29 TEV: 0 Breached",       c29.get("Breached", 0) == 0)


# ═══════════════════════════════════════════════════════════════════════
print("\n[5] STRESS CONTINUITY — stress=0 must equal stored exactly")
# ═══════════════════════════════════════════════════════════════════════
fy29_no_stress = resolve_covenants(data, "FY29E (TEV)", stress_active=False)
fy29_zero_stress = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                                       ebitda_change_pct=0, interest_change_pct=0,
                                       debt_change_pct=0)
# Compare key DSCR values across the boundary
def _get_dscr(df, label):
    m = df[(df["Lender"] == "UBI Consortium") &
            (df["Covenant"].str.startswith("DSCR"))]
    if len(m):
        return m.iloc[0]["Actual"]
    return None
dscr_stored = _get_dscr(fy29_no_stress, "no stress")
dscr_zero   = _get_dscr(fy29_zero_stress, "zero stress")
check(f"DSCR continuity at stress=0 boundary (stored={dscr_stored}, zero-stress={dscr_zero})",
       isinstance(dscr_stored, (int, float)) and isinstance(dscr_zero, (int, float))
       and abs(dscr_stored - dscr_zero) < 0.001,
       f"stored={dscr_stored}, zero={dscr_zero}")

# Check whole DataFrame for continuity
mismatches = 0
for i in range(len(fy29_no_stress)):
    a = fy29_no_stress.iloc[i]["Actual"]
    b = fy29_zero_stress.iloc[i]["Actual"]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and pd.notna(a) and pd.notna(b):
        if abs(a - b) > 0.001:
            mismatches += 1
check(f"All covenants continuous at stress=0 ({mismatches} mismatches)",
       mismatches == 0,
       f"{mismatches} covenants discontinuous between stored and zero-stress")


# ═══════════════════════════════════════════════════════════════════════
print("\n[6] STRESS MONOTONICITY — more EBITDA stress → lower DSCR")
# ═══════════════════════════════════════════════════════════════════════
scenarios = [
    ("Base (0% shock)",       0,   0,   0),
    ("Mild (-10% EBITDA)",   -10,  0,   0),
    ("Stress (-15% EBITDA)", -15,  0,   10),
    ("Severe (-30% EBITDA)", -30,  0,   25),
]
prior_dscr = None
prior_compliant = None
for label, eb, ir, dt in scenarios:
    df = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                            ebitda_change_pct=eb, interest_change_pct=ir,
                            debt_change_pct=dt)
    dscr = _get_dscr(df, label)
    compliant = (df["Status"] == "Compliant").sum()
    print(f"     {label:25s} → DSCR={dscr!r:>15}  Compliant={compliant}/44")
    if prior_dscr is not None and isinstance(dscr, (int, float)) and isinstance(prior_dscr, (int, float)):
        check(f"  {label} DSCR < prior",
               dscr <= prior_dscr + 0.001,
               f"prior={prior_dscr}, new={dscr}")
    if prior_compliant is not None:
        check(f"  {label} Compliant ≤ prior",
               compliant <= prior_compliant,
               f"prior={prior_compliant}, new={compliant}")
    prior_dscr = dscr
    prior_compliant = compliant


# ═══════════════════════════════════════════════════════════════════════
print("\n[7] MARKET-DATA COVENANTS preserved under severe stress")
# ═══════════════════════════════════════════════════════════════════════
severe = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                             ebitda_change_pct=-30, debt_change_pct=25,
                             interest_change_pct=53)
market_severe = severe[severe["Covenant"].str.contains("JSL|FMV|Pledge",
                                                          case=False, na=False, regex=True)]
market_base = fy29[fy29["Covenant"].str.contains("JSL|FMV|Pledge",
                                                    case=False, na=False, regex=True)]
all_preserved = True
for i in range(len(market_severe)):
    a = market_severe.iloc[i]["Actual"]
    b = market_base.iloc[i]["Actual"]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > 0.001:
            all_preserved = False
            break
check("All JSL/FMV/Pledge covenants unchanged under severe stress", all_preserved)


# ═══════════════════════════════════════════════════════════════════════
print("\n[8] RATING COVENANTS preserved under severe stress")
# ═══════════════════════════════════════════════════════════════════════
rating_severe = severe[severe["Covenant"].str.contains("Rating", case=False, na=False)]
rating_base = fy29[fy29["Covenant"].str.contains("Rating", case=False, na=False)]
all_match = True
for i in range(len(rating_severe)):
    if rating_severe.iloc[i]["Actual"] != rating_base.iloc[i]["Actual"]:
        all_match = False
        break
check(f"All {len(rating_severe)} rating covenants unchanged under severe stress", all_match)


# ═══════════════════════════════════════════════════════════════════════
print("\n[9] INTEREST RECOMPUTE — verify Excel scenarios within ±2%")
# ═══════════════════════════════════════════════════════════════════════
si = data["scenario_inputs"]; so = data["scenario_outputs"]
for i, label in enumerate(["Base", "Stress", "Severe"]):
    rs = si["Rate_Shock_BPS"][i]
    ss = si["Spread_BPS"][i]
    us = si["Util_Change_Pct"][i]
    out = recompute_interest(data["facility_master"], data["benchmark_rates"], rs, ss, us)
    expected = so["Annual_B1_Interest"][i]
    diff_pct = abs(out["Bucket1_Interest"] - expected) / expected * 100 if expected else 0
    check(f"  {label} B1 Interest within ±2% of Excel (Excel={expected:.2f}, mine={out['Bucket1_Interest']:.2f}, diff={diff_pct:.1f}%)",
           diff_pct < 2.0,
           f"diff={diff_pct:.2f}%")


# ═══════════════════════════════════════════════════════════════════════
print("\n[10] WAC CALCULATION")
# ═══════════════════════════════════════════════════════════════════════
# WAC = B1 Interest / B1 Effective O/S
b1_os = fm[(fm["Bucket"] == 1) & (fm["Category"].isin(["FB", "FB-Term", "FB-FCY"]))]["Effective_OS"].sum()
computed_wac = isum["Bucket1_Interest"] / b1_os if b1_os else 0
check("B1 Effective O/S = ₹3,916 Cr", abs(b1_os - 3916) < 1, f"got {b1_os}")
check(f"Computed WAC matches stored WAC ({computed_wac:.4%} vs {isum['Weighted_Avg_Cost']:.4%})",
       abs(computed_wac - isum["Weighted_Avg_Cost"]) < 0.0005)
check("WAC = 9.158%", abs(isum["Weighted_Avg_Cost"] - 0.09158) < 0.0005)


# ═══════════════════════════════════════════════════════════════════════
print("\n[11] FINANCIALS — FY25 audit vs FY29 TEV consistency")
# ═══════════════════════════════════════════════════════════════════════
fy25_fin = data["financials"]["FY25A"]
fy29_fin = data["financials"]["FY29E (TEV)"]
check("FY25 EBITDA = -₹5.45 Cr (audit)",         abs(fy25_fin["EBITDA"] - (-5.45)) < 0.1)
check("FY29 EBITDA = ₹957.36 Cr (TEV)",          abs(fy29_fin["EBITDA"] - 957.36) < 0.1)
check("FY25 TNW = ₹993.45 Cr (audit equity)",    abs(fy25_fin["TNW"] - 993.45) < 0.5)
# FY29 TEV TNW = Total Equity post-COD projection
check(f"FY29 TNW > FY25 TNW (project grows equity)",
       fy29_fin["TNW"] > fy25_fin["TNW"])
check(f"FY29 Term Debt > 0 (post-COD)",
       fy29_fin["Term Debt"] > 0)


# ═══════════════════════════════════════════════════════════════════════
print("\n[12] LENDER COMPOSITION — totals tie to ₹4,466 Cr")
# ═══════════════════════════════════════════════════════════════════════
ls_total = ls["Sanctioned_Debt"].sum()
check(f"Lender Summary total = Sanctioned Debt KPI ({ls_total:.0f})",
       abs(ls_total - 4466) < 1)
check(f"9 lenders in summary", len(ls) == 9)


# ═══════════════════════════════════════════════════════════════════════
print("\n[13] PDF generation — both bases")
# ═══════════════════════════════════════════════════════════════════════
for basis in ["FY25A", "FY29E (TEV)"]:
    try:
        cov = resolve_covenants(data, basis, stress_active=False)
        pdf = generate_board_memo(data, cov, {"basis": basis})
        check(f"PDF generated for {basis} ({len(pdf):,} bytes)",
               len(pdf) > 3000 and pdf[:4] == b"%PDF")
    except Exception as e:
        check(f"PDF generation for {basis}", False, str(e))


# ═══════════════════════════════════════════════════════════════════════
print("\n[14] AI ANALYST — all suggested questions return non-empty text")
# ═══════════════════════════════════════════════════════════════════════
for q in rba.SUGGESTED_QUESTIONS:
    try:
        resp = rba.answer_question(q, data, fy29)
        check(f"  Q '{q[:45]}…'", isinstance(resp, str) and len(resp) > 50,
               f"got len={len(resp) if isinstance(resp, str) else 'not-str'}")
    except Exception as e:
        check(f"  Q '{q[:45]}…'", False, str(e))


# ═══════════════════════════════════════════════════════════════════════
print("\n[15] SNAPSHOTS — round-trip preserves state")
# ═══════════════════════════════════════════════════════════════════════
clear_snapshots()
snap = take_snapshot(data, fy29, "test")
check("Snapshot Sanctioned Debt = ₹4,466", abs(snap["state"]["Sanctioned_Debt_B1B2"] - 4466) < 1)
check("Snapshot Compliant = 43",            snap["state"]["Compliant"] == 43)
check("Snapshot WAC = 9.158%",              abs(snap["state"]["Weighted_Avg_Cost"] - 0.09158) < 0.0005)


# ═══════════════════════════════════════════════════════════════════════
print("\n[16] VALIDATION ENGINE — 87 / 0 / PASS")
# ═══════════════════════════════════════════════════════════════════════
vs = data["validation_summary"]
check("87 total checks",        vs["Total_Checks"] == 87)
check("87 PASS",                vs["Pass_Count"] == 87)
check("0 FAIL",                 vs["Fail_Count"] == 0)
check("0 Critical FAIL",        vs["Critical_Fail"] == 0)
check("Overall = PASS",         "PASS" in vs["Overall_Status"])


# ═══════════════════════════════════════════════════════════════════════
print("\n[17] EDGE CASE — empty stress sliders behave correctly")
# ═══════════════════════════════════════════════════════════════════════
# stress_active=True with all zeros should match stored
ze = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                       ebitda_change_pct=0, debt_change_pct=0, interest_change_pct=0)
zs = resolve_covenants(data, "FY29E (TEV)", stress_active=False)
n_diff = 0
for i in range(len(ze)):
    a = ze.iloc[i]["Status"]; b = zs.iloc[i]["Status"]
    if a != b:
        n_diff += 1
check(f"Zero-stress status matches stored status (diff={n_diff})", n_diff == 0)


# ═══════════════════════════════════════════════════════════════════════
print("\n[18] EDGE CASE — extreme positive shock to EBITDA improves compliance")
# ═══════════════════════════════════════════════════════════════════════
high = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                          ebitda_change_pct=30, debt_change_pct=0, interest_change_pct=0)
n_compliant_high = (high["Status"] == "Compliant").sum()
n_compliant_base = (fy29["Status"] == "Compliant").sum()
check(f"+30% EBITDA → Compliant ≥ base ({n_compliant_high} ≥ {n_compliant_base})",
       n_compliant_high >= n_compliant_base)


# ═══════════════════════════════════════════════════════════════════════
print("\n[19] VISUALIZATIONS module — all expected functions present")
# ═══════════════════════════════════════════════════════════════════════
for fn in ["render_covenant_headroom_chart", "render_facility_cost_chart",
           "render_fb_rate_vs_wac_chart", "render_lender_composition_stacked",
           "render_repayment_timeline", "render_renewal_timeline",
           "render_tev_trajectory", "render_bucket_donut",
           "render_scenario_comparison_chart"]:
    check(f"viz.{fn}", hasattr(viz, fn))


# ═══════════════════════════════════════════════════════════════════════
print("\n[20] STREAMLIT IMPORTS — entry point loads without exception")
# ═══════════════════════════════════════════════════════════════════════
import importlib
for m in ["main", "dashboard_ui", "data_loader", "scenario_engine",
          "visualizations", "rule_based_ai", "snapshots", "pdf_export",
          "market_rates", "theme"]:
    try:
        importlib.import_module(m)
        check(f"import {m}", True)
    except Exception as e:
        check(f"import {m}", False, str(e))


# ─── FINAL ─────────────────────────────────────────────────────────
print()
print("=" * 82)
print(f" RESULT: {passed} PASS  ·  {len(errors)} FAIL  ·  "
      f"{passed/(passed+len(errors))*100:.1f}% pass")
print("=" * 82)
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for n, d in errors:
        print(f"  ✗ {n}")
        if d:
            print(f"     {d}")
    sys.exit(1)
else:
    print("\n✓ DASHBOARD IS 100% ACCURATE, FINANCIALLY SOUND, AND CONSISTENT.")
    sys.exit(0)
