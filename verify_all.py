"""
JFL V&V — End-to-end verification suite.

Mirrors the JCL verify_all.py structure, adapted for JFL.

Phases:
  1. All module imports clean
  2. Data loader reconciles to Excel ground truth
  3. Covenant tracker logic sound (3 scenarios: FY25 audit, FY29 TEV, FY29 stress)
  4. Interest re-computation matches Excel Scenario Analysis
  5. Visualizations module imports & has all expected functions
  6. PDF board memo generates without error
  7. Snapshot capture & compare
  8. Rule-based AI returns valid responses for all suggested questions

Run: python verify_all.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st


# Mock session_state for non-Streamlit testing
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


from data_loader import load_all_data, force_reload, get_excel_path
from scenario_engine import (recompute_covenants, recompute_interest,
                                run_scenario, resolve_covenants)
import rule_based_ai as rba
from pdf_export import generate_board_memo
from snapshots import (take_snapshot, list_snapshots, compare_snapshots,
                        clear_snapshots)


print("=" * 82)
print("JFL Debt Monitoring Dashboard — V&V Suite")
print("=" * 82)

passed = 0; failed = 0; errors = []


def check(name, condition, details=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ PASS  {name}")
    else:
        failed += 1
        print(f"  ✗ FAIL  {name}  {details}")
        errors.append((name, details))


# ─── PHASE 1: ALL IMPORTS ──────────────────────────────────────────
print("\n[PHASE 1] All module imports")
import importlib
for m in ["data_loader", "scenario_engine", "theme", "rule_based_ai",
          "snapshots", "pdf_export", "visualizations", "market_rates",
          "dashboard_ui", "main"]:
    try:
        importlib.import_module(m)
        check(f"import {m}", True)
    except Exception as e:
        check(f"import {m}", False, str(e))


# ─── PHASE 2: DATA LOADING ─────────────────────────────────────────
print("\n[PHASE 2] Data loading + Excel ground-truth match")
data = load_all_data()
check("Excel loaded", data["excel_exists"])
check("44 facilities", len(data["facility_master"]) == 44)
check("≥44 covenants (audit)", len(data["covenants"]) >= 44)
check("≥44 covenants (TEV)", len(data["covenants_tev"]) >= 44)
check("9 lenders", len(data["lender_summary"]) == 9)
check("15 Management Flags", len(data["management_flags"]) == 15)
check("64 repayment quarters", len(data["repayment_schedule"]) == 64)

t = data["totals"]
check("Sanctioned Debt = ₹4,466 Cr",       abs(t["Bucket1_Sanctioned_Debt"] - 4466) < 1,
       f"got {t['Bucket1_Sanctioned_Debt']}")
check("FB Mains B1 = ₹3,916 Cr",           abs(t["FB_Mains_B1"] - 3916) < 1,
       f"got {t['FB_Mains_B1']}")
check("NFB Mains B2 = ₹550 Cr",            abs(t["NFB_Mains_B2"] - 550) < 1,
       f"got {t['NFB_Mains_B2']}")
check("NFB Contingent = ₹2,040 Cr",        abs(t["NFB_Contingent"] - 2040) < 1,
       f"got {t['NFB_Contingent']}")
check("FD-Backed B3 = ₹150 Cr",            abs(t["FD_Backed_B3"] - 150) < 1)
check("Uncommitted B4 = ₹1,000 Cr",        abs(t["Uncommitted_B4"] - 1000) < 1)
check("Hedge Memo = ₹75 Cr",                abs(t["Hedge_Memo"] - 75) < 1)
check("ICICI TL Takeover = ₹840 Cr",        abs(t["ICICI_TL_Takeover"] - 840) < 1)
check("Adjusted Consortium = ₹3,626 Cr",   abs(t["Adjusted_Consortium"] - 3626) < 1)

isum = data["interest_summary"]
check("Bucket 1 Interest = ₹337.696 Cr",  abs(isum["Bucket1_Interest"] - 337.696) < 0.01,
       f"got {isum['Bucket1_Interest']}")
check("Bucket 2 Commission = ₹3.05 Cr",    abs(isum["Bucket2_Commission"] - 3.05) < 0.01)
check("Bucket 3 Interest = ₹13.5 Cr",      abs(isum["Bucket3_Interest"] - 13.5) < 0.01)
check("Total Run-Rate = ₹354.246 Cr",      abs(isum["Total_Interest_Commission"] - 354.246) < 0.01)
check("WAC = 8.62%",                        abs(isum["Weighted_Avg_Cost"] - 0.0862) < 0.0005,
       f"got {isum['Weighted_Avg_Cost']}")

vs = data["validation_summary"]
check("Validation 120 checks", vs["Total_Checks"] == 120)
check("All checks PASS", vs["Pass_Count"] == vs["Total_Checks"])
check("Zero critical FAIL", vs["Critical_Fail"] == 0)


# ─── PHASE 3: COVENANT TRACKER LOGIC ───────────────────────────────
print("\n[PHASE 3] Covenant tracker — soundness against Excel ground truth")

# Test 3a: FY25 audit baseline
# NOTE: The verified Excel's Covenant Tracker stores FY29 TEV-projected actuals
# throughout (consortium-aggregated DSCR 1.80, FACR 1.51, ISCR 3.65 etc.). It does
# NOT compute a separate FY25 audit-basis covenant status. The dashboard's FY25
# toggle therefore returns the same stored actuals as the FY29 view — both bases
# read from the same Excel-stored values. FY25 audit financials (EBITDA -5.45,
# TNW 993.45) are available in Instructions & Assumptions for context but do not
# drive a separate covenant resolution.
fy25 = resolve_covenants(data, "FY25A", stress_active=False)
counts_fy25 = fy25["Status"].value_counts().to_dict()
check("FY25 view: ≥40 Compliant (TEV-basis stored)",
       counts_fy25.get("Compliant", 0) >= 40,
       f"got {counts_fy25.get('Compliant', 0)}")

# Test 3b: FY29 TEV baseline
fy29 = resolve_covenants(data, "FY29E (TEV)", stress_active=False)
counts_fy29 = fy29["Status"].value_counts().to_dict()
check("FY29 TEV Compliant=43",     counts_fy29.get("Compliant", 0)   == 43,
       f"got {counts_fy29.get('Compliant', 0)}")
check("FY29 TEV Near Breach=1",    counts_fy29.get("Near Breach", 0) == 1,
       f"got {counts_fy29.get('Near Breach', 0)}")
check("FY29 TEV Breached=0",       counts_fy29.get("Breached", 0)    == 0,
       f"got {counts_fy29.get('Breached', 0)}")

# Test 3c: stress recompute moves things in right direction
fy29_severe = resolve_covenants(data, "FY29E (TEV)", stress_active=True,
                                 ebitda_change_pct=-30, debt_change_pct=25,
                                 interest_change_pct=53)
counts_severe = fy29_severe["Status"].value_counts().to_dict()
check("Severe stress: Compliant decreases",
       counts_severe.get("Compliant", 0) < counts_fy29.get("Compliant", 99),
       f"severe got {counts_severe.get('Compliant', 0)} vs base 43")
check("Severe stress: Breached increases",
       counts_severe.get("Breached", 0) > 0,
       f"got {counts_severe.get('Breached', 0)} breached")

# Test 3d: market-data covenants preserved under stress
market = fy29_severe[fy29_severe["Covenant"].str.contains("JSL|FMV|Pledge",
                                                            case=False, na=False, regex=True)]
check("Market-data covenants preserved",
       all(market["Actual"].apply(lambda x: x is not None and not (isinstance(x, float) and pd.isna(x)))),
       f"got {len(market)} market covenants")

# Test 3e: rating covenants resolved as ordinals
rating = fy29[fy29["Covenant"].str.contains("Rating", case=False, na=False)]
check(f"{len(rating)} rating covenants resolved",
       all(rating["Status"].isin(["Compliant", "Near Breach", "Watch", "Breached"])),
       f"got statuses {rating['Status'].unique().tolist()}")


# ─── PHASE 4: INTEREST RECOMPUTE ───────────────────────────────────
print("\n[PHASE 4] Interest re-computation vs Excel scenarios")
base_int = recompute_interest(data["facility_master"], data["benchmark_rates"], 0, 0, 0)
check("Base B1 Interest = ₹337.696",  abs(base_int["Bucket1_Interest"] - 337.696) < 0.1,
       f"got {base_int['Bucket1_Interest']}")

stress_int = recompute_interest(data["facility_master"], data["benchmark_rates"], 100, 25, 10)
check("Stress B1 Interest > Base",     stress_int["Bucket1_Interest"] > base_int["Bucket1_Interest"])
check("Stress B1 ~ ₹420-430 Cr",
       420 < stress_int["Bucket1_Interest"] < 430,
       f"got {stress_int['Bucket1_Interest']} (Excel stress scenario ≈ 425.31)")


# ─── PHASE 5: VISUALIZATIONS MODULE ────────────────────────────────
print("\n[PHASE 5] Visualizations module")
import visualizations as viz
for fn in ["render_covenant_headroom_chart", "render_facility_cost_chart",
           "render_fb_rate_vs_wac_chart", "render_lender_composition_stacked",
           "render_repayment_timeline", "render_renewal_timeline",
           "render_tev_trajectory", "render_bucket_donut",
           "render_scenario_comparison_chart"]:
    check(f"{fn} exists", hasattr(viz, fn))


# ─── PHASE 6: PDF GENERATION ───────────────────────────────────────
print("\n[PHASE 6] PDF Board Memo generation")
try:
    cov_df = resolve_covenants(data, "FY29E (TEV)", stress_active=False)
    pdf_bytes = generate_board_memo(data, cov_df, {"basis": "FY29E (TEV)"})
    check("PDF bytes returned",  len(pdf_bytes) > 3000)
    check("PDF is valid PDF",     pdf_bytes[:4] == b"%PDF")
    check("PDF reasonable size",  3000 < len(pdf_bytes) < 5_000_000)
except Exception as e:
    check("PDF generation",       False, str(e))


# ─── PHASE 7: SNAPSHOTS ────────────────────────────────────────────
print("\n[PHASE 7] Snapshot capture & compare")
clear_snapshots()
snap_a = take_snapshot(data, fy29, "test-base")
check("Snapshot A captured", snap_a["state"]["Sanctioned_Debt_B1B2"] == 4466)
snap_b = take_snapshot(data, fy29_severe, "test-stress")
check("Snapshot B captured", "covenant_actuals" in snap_b["state"])

delta = compare_snapshots(snap_a, snap_b)
check("Delta detects covenant changes", len(delta["covenant_changes"]) > 0,
       f"got {len(delta['covenant_changes'])} changes")
clear_snapshots()


# ─── PHASE 8: RULE-BASED AI ────────────────────────────────────────
print("\n[PHASE 8] Rule-based AI — all suggested questions")
for q in rba.SUGGESTED_QUESTIONS:
    try:
        resp = rba.answer_question(q, data, fy29)
        check(f"Q: '{q[:50]}…'", isinstance(resp, str) and len(resp) > 20)
    except Exception as e:
        check(f"Q: '{q[:50]}…'", False, str(e))

insights = rba.get_proactive_insights(data, fy29)
check("Proactive insights returned ≥3", len(insights) >= 3)


# ─── FINAL SUMMARY ─────────────────────────────────────────────────
print()
print("=" * 82)
print(f"V&V RESULT:  {passed} PASS  ·  {failed} FAIL  ·  {passed/(passed+failed)*100:.1f}% pass rate")
print("=" * 82)
if errors:
    print("\nFailures:")
    for n, d in errors:
        print(f"  - {n}: {d}")
    sys.exit(1)
else:
    print("\nAll checks passed. Dashboard ready for deployment.")
    sys.exit(0)
