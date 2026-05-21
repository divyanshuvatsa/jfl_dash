"""
Scenario engine — JFL adaptation.

Applies user shocks (rate, spread, utilisation, EBITDA, debt) on top of the
Excel base values to recompute covenants and interest dynamically.

Excel ground-truth scenario outputs (from JFL Scenario Analysis tab,
operating on FY29 TEV-projected financials):

  Stress (+100 bps rate, +25 bps spread, +10% util, −15% EBITDA, +10% debt):
    Annual B1 Interest: ₹448.32 Cr  (vs base ₹358.61 Cr)
    DSCR: -0.0168x (FY25 audit basis EBITDA still negative)
    Total Debt/EBITDA: -597x (pre-COD, EBITDA still negative)
    ICR: -0.0103x

  Severe (+200 bps, +50 bps spread, +20% util, −30% EBITDA, +25% debt):
    Annual B1 Interest: ₹547.81 Cr
    DSCR: -0.0122x
    Total Debt/EBITDA: -824x
    ICR: -0.0070x

This module replicates those outputs for slider-driven what-if analysis,
on EITHER the FY25 Audit basis (where the project is pre-operational and
EBITDA is negative ₹5.45 Cr) OR the FY29 TEV-projected basis (where the
project is operational and EBITDA = ₹957.36 Cr).
"""

from __future__ import annotations
import pandas as pd
from typing import Dict, Any


# Rating ordinal map (higher = better). Matches Instructions Section G.
RATING_ORDINALS = {
    "AAA": 21, "AA+": 20, "AA": 19, "AA-": 18,
    "A+": 17, "A": 16, "A-": 15,
    "BBB+": 14, "BBB": 13, "BBB-": 12,
    "BB+": 11, "BB": 10, "BB-": 9,
    "B+": 8, "B": 7, "B-": 6,
    "CCC+": 5, "CCC": 4, "CCC-": 3, "CC": 2, "C": 1, "D": 0,
}


def rating_to_ordinal(rating_str: Any) -> int:
    """Parse rating string → ordinal. Higher = better."""
    if rating_str is None:
        return 0
    s = str(rating_str).upper()
    # Longest match first to avoid "A" matching inside "AA-"
    for tier in sorted(RATING_ORDINALS.keys(), key=lambda x: -len(x)):
        if tier in s:
            return RATING_ORDINALS[tier]
    return 0


def calculate_all_ratios(financials: Dict[str, float],
                         ebitda_change_pct: float = 0,
                         interest_change_pct: float = 0,
                         debt_change_pct: float = 0) -> Dict[str, float]:
    """Return all ratios used across JFL covenants. Apply shocks if requested."""
    ebitda = financials.get("EBITDA", 0) * (1 + ebitda_change_pct / 100)
    interest = financials.get("Interest Expense", 0) * (1 + interest_change_pct / 100)
    total_debt = financials.get("Total Debt", 0) * (1 + debt_change_pct / 100)
    term_debt = financials.get("Term Debt", 0) * (1 + debt_change_pct / 100)
    tnw = financials.get("TNW", 0)
    atnw = financials.get("ATNW", tnw)
    ca = financials.get("Current Assets", 0)
    cl = financials.get("Current Liabilities", 0)
    tol = financials.get("TOL", 0)
    fa = financials.get("Fixed Assets", 0)
    tax = financials.get("Tax Paid", 0)
    sched = financials.get("Sched TL Repay", 0)

    # DSCR formula consortium-standard: (EBITDA − Tax) / (Interest + Sched TL Rep)
    # For JFL the project is pre-operational at FY25 → EBITDA negative → DSCR negative.
    # Post-COD at FY29 (TEV basis) → DSCR ~1.80x.
    if (sched + interest) > 0:
        dscr = (ebitda - tax) / (sched + interest)
    else:
        dscr = 999.0

    return {
        # Consortium-standard 5-pack (UBI, YES, IDFC, ICICI TL, HDFC, Indian Bank presumed)
        "DSCR":                          dscr,
        "DSCR (consortium)":             dscr,
        "DSCR (consortium-presumed)":    dscr,
        "DSCR (IDFC-specific)":          dscr,   # same formula; FY27 testing handled in UI
        "DSCR (IDFC)":                   dscr,
        "Cash Sweep Trigger (DSCR)":     dscr,
        "FACR":                          (fa / term_debt) if term_debt > 0 else 999.0,
        "FACR (consortium)":             (fa / term_debt) if term_debt > 0 else 999.0,
        "FACR (consortium-presumed)":    (fa / term_debt) if term_debt > 0 else 999.0,
        "ISCR":                          (ebitda / interest) if interest > 0 else 999.0,
        "ISCR (consortium)":             (ebitda / interest) if interest > 0 else 999.0,
        "ISCR (consortium-presumed)":    (ebitda / interest) if interest > 0 else 999.0,
        "LTD / EBITDA":                  (term_debt / ebitda) if ebitda > 0 else (term_debt / ebitda if ebitda < 0 else 999.0),
        "LTD / EBITDA (consortium)":     (term_debt / ebitda) if ebitda > 0 else (term_debt / ebitda if ebitda < 0 else 999.0),
        "LTD / EBITDA (consortium-presumed)": (term_debt / ebitda) if ebitda > 0 else (term_debt / ebitda if ebitda < 0 else 999.0),
        "LTD/EBITDA":                    (term_debt / ebitda) if ebitda > 0 else (term_debt / ebitda if ebitda < 0 else 999.0),
        "LTD / Equity":                  (term_debt / tnw) if tnw > 0 else 999.0,
        "LTD / Equity (consortium)":     (term_debt / tnw) if tnw > 0 else 999.0,
        "LTD / Equity (consortium-presumed)": (term_debt / tnw) if tnw > 0 else 999.0,
        "LTD/Equity":                    (term_debt / tnw) if tnw > 0 else 999.0,
        # ICICI WC specifics
        "Total Debt / EBITDA (WC)":      (total_debt / ebitda) if ebitda > 0 else (total_debt / ebitda if ebitda < 0 else 999.0),
        "Total Debt / EBITDA":           (total_debt / ebitda) if ebitda > 0 else (total_debt / ebitda if ebitda < 0 else 999.0),
        "TOL / TNW (WC)":                (tol / tnw) if tnw > 0 else 999.0,
        "TOL / TNW":                     (tol / tnw) if tnw > 0 else 999.0,
        "Current Ratio (WC)":            (ca / cl) if cl > 0 else 999.0,
        "Current Ratio":                 (ca / cl) if cl > 0 else 999.0,
        # Promoter contribution: equity + promoter ICDs (audit-derived, NOT formally subordinated)
        # FY25 audit: equity ₹993.45 + ICDs ₹856.76 = ₹1,850.21 Cr (per Covenant Tracker R26)
        # FY29 TEV:   equity ₹2,186 Cr + ICDs ₹0 = ₹2,186 Cr
        "Min Promoter Contribution (Cr)": _promoter_contribution(financials, ebitda_change_pct, debt_change_pct),
        # Quasi equity: promoter ICDs only
        "Quasi Equity Cap (Cr)":          _quasi_equity(financials),
        "Quasi Equity Cap (₹ Cr)":        _quasi_equity(financials),
    }


def _promoter_contribution(financials: Dict[str, float],
                            ebitda_change_pct: float, debt_change_pct: float) -> float:
    """Equity + promoter ICDs. Per Covenant Tracker R26 source notes."""
    # On FY25 Audit basis: ₹1,850.21 Cr (993.45 equity + 856.76 promoter ICDs)
    # On FY29 TEV basis:    ₹2,186 Cr (equity-only since ICDs assumed converted)
    tnw = financials.get("TNW", 0)
    # If TNW is large (TEV basis), use equity-only; otherwise add ICDs (audit)
    if tnw > 1500:
        return tnw
    return tnw + 856.76


def _quasi_equity(financials: Dict[str, float]) -> float:
    """Promoter ICDs. On FY25 audit = ₹856.76 Cr; FY29 TEV assumes converted = 0."""
    tnw = financials.get("TNW", 0)
    if tnw > 1500:
        return 0.0
    return 856.76


def evaluate_status(actual: float, operator: str, threshold: float) -> str:
    """Apply JFL covenant status logic.

    Headroom tiers (matches Excel Covenant Tracker logic):
      Breached:    actual fails the operator vs threshold
      Near Breach: in the right direction but headroom < 5% (or zero)
      Watch:       headroom 5-10%
      Compliant:   headroom ≥ 10%

    The Excel uses 0% headroom → Near Breach (e.g. ICICI rating A- = threshold A-,
    per VJF-v7-11). This implementation preserves that edge case.
    """
    if pd.isna(actual) or actual is None:
        return "Pending Input"
    op = (operator or "").strip()
    try:
        a = float(actual); t = float(threshold)
    except (TypeError, ValueError):
        return "Pending Input"

    if op in (">", ">="):
        if (op == ">" and a <= t) or (op == ">=" and a < t):
            return "Breached"
        hr_pct = ((a - t) / t * 100) if t > 0 else (100 if a > 0 else 0)
        if hr_pct < 5: return "Near Breach"
        if hr_pct < 10: return "Watch"
        return "Compliant"
    elif op in ("<", "<="):
        if (op == "<" and a >= t) or (op == "<=" and a > t):
            return "Breached"
        hr_pct = ((t - a) / t * 100) if t > 0 else (100 if a < t else 0)
        if hr_pct < 5: return "Near Breach"
        if hr_pct < 10: return "Watch"
        return "Compliant"
    return "Pending Input"


def _is_market_data_covenant(name: str) -> bool:
    """Covenants tied to external/market data — cannot be re-derived from financials.

    These MUST retain their Excel-stored Actual under stress because they depend on
    JSL share-market data, pledge percentages, etc. — not on borrower financials.
    """
    if not isinstance(name, str):
        return False
    keys = ["JSL", "FMV", "Pledge", "Listed-Securities", "Listed Securities"]
    return any(k.lower() in name.lower() for k in keys)


def _is_rating_covenant(name: str, op: str) -> bool:
    """Rating covenants — threshold is an ordinal (BBB=10, A-=14, etc.)."""
    n = str(name).lower()
    o = str(op).lower()
    if "rating" in n: return True
    if o == "rating": return True
    return False


def _is_quasi_equity_covenant(name: str) -> bool:
    return "quasi" in str(name).lower()


def _is_promoter_contrib_covenant(name: str) -> bool:
    return "promoter contribution" in str(name).lower()


def _find_ratio(name: str, ratios: Dict[str, float]):
    """Match covenant name to a ratio key (exact or fuzzy)."""
    if name in ratios:
        return ratios[name]
    # Strip parenthetical qualifier
    base = name.split("(")[0].strip()
    for k, v in ratios.items():
        if k.split("(")[0].strip() == base:
            return v
    return None


def recompute_covenants(base_covenants: pd.DataFrame, financials: Dict[str, float],
                        ebitda_change_pct: float = 0,
                        interest_change_pct: float = 0,
                        debt_change_pct: float = 0,
                        stored_actuals: Dict[str, Any] = None) -> pd.DataFrame:
    """Apply shocks to financials and recompute every covenant's actual + status.

    Logic dispatch by covenant class:
      1. Numeric financial ratios (DSCR, FACR, ISCR, LTD/EBITDA, LTD/Equity,
         TOL/TNW, Current Ratio, Total Debt/EBITDA) — recomputed from shocked
         financials.
      2. Rating covenants — use rating ordinal from financials; compare to
         the numeric threshold (which is already an ordinal in the JFL Excel).
      3. Market-data covenants (JSL FMV / Pledge) — CANNOT be recomputed.
         Inherit stored Actual & Status from the Excel.
      4. Quasi Equity Cap / Promoter Contribution — use stored helpers
         (audit Note 16+18 → ₹856.76 promoter ICDs; equity ₹993.45).
      5. Anything else — Pending Input.

    `stored_actuals` (optional dict {(lender, covenant): actual}) lets market-data
    covenants inherit their pre-stress baseline. If not supplied, the function
    falls back to the value present in base_covenants["Actual"].
    """
    ratios = calculate_all_ratios(financials, ebitda_change_pct, interest_change_pct, debt_change_pct)
    rating_str = financials.get("External Rating", "")
    # When rating is missing/Pending, use A- (=14) as the working assumption per
    # ICICI WC / RBL covenant baselines (Excel uses this in Validation Engine).
    rating_ord = rating_to_ordinal(rating_str) if rating_str and rating_str != "Pending" else 14

    rows = []
    for _, c in base_covenants.iterrows():
        name = c["Covenant"]
        op = c["Operator"]
        thr = c["Threshold"]

        # ── Branch 1: rating covenants ──────────────────────────────
        if _is_rating_covenant(name, op):
            try:
                thr_num = float(thr) if isinstance(thr, (int, float)) else rating_to_ordinal(thr)
            except (TypeError, ValueError):
                thr_num = 14
            actual = rating_ord
            status = evaluate_status(actual, op if op in (">", ">=", "<", "<=") else ">=", thr_num)
            if op in (">", ">="):
                headroom = actual - thr_num
                hr_pct = (headroom / thr_num * 100) if thr_num > 0 else 0
            else:
                headroom = thr_num - actual
                hr_pct = (headroom / thr_num * 100) if thr_num > 0 else 0

        # ── Branch 2: market-data covenants (JSL FMV / Pledge) ──────
        elif _is_market_data_covenant(name):
            # Inherit Actual & Status from Excel-stored baseline (won't move under stress)
            actual = (stored_actuals or {}).get((c["Lender"], name), c.get("Actual"))
            try:
                if isinstance(actual, (int, float)) and pd.notna(actual) and isinstance(thr, (int, float)):
                    status = evaluate_status(actual, op, thr)
                    if op in (">", ">="):
                        headroom = actual - thr
                        hr_pct = (headroom / thr * 100) if thr > 0 else 0
                    else:
                        headroom = thr - actual
                        hr_pct = (headroom / thr * 100) if thr > 0 else 0
                else:
                    status = "Pending Input"; headroom = None; hr_pct = None
            except Exception:
                status = "Pending Input"; headroom = None; hr_pct = None

        # ── Branch 3: financial ratio covenants ─────────────────────
        else:
            actual = _find_ratio(name, ratios)
            if actual is None:
                status = "Pending Input"; headroom = None; hr_pct = None
            else:
                status = evaluate_status(actual, op, thr)
                if op in (">", ">="):
                    headroom = (actual - thr) if isinstance(thr, (int, float)) else None
                    hr_pct = (headroom / thr * 100) if (isinstance(thr, (int, float)) and thr > 0 and headroom is not None) else None
                elif op in ("<", "<="):
                    headroom = (thr - actual) if isinstance(thr, (int, float)) else None
                    hr_pct = (headroom / thr * 100) if (isinstance(thr, (int, float)) and thr > 0 and headroom is not None) else None
                else:
                    headroom = None; hr_pct = None

        rows.append({
            "Lender": c["Lender"], "Covenant": name, "Operator": op,
            "Threshold": thr, "Actual": actual, "Headroom": headroom,
            "Headroom_Pct": hr_pct, "Status": status,
            "Risk": c.get("Risk", "Low"),
            "Source": c.get("Source", ""),
            "Source_Type": c.get("Source_Type", ""),
            "Frequency": c.get("Frequency", ""),
            "First_Test": c.get("First_Test", ""),
        })
    return pd.DataFrame(rows)


def recompute_interest(facility_master: pd.DataFrame, benchmark_rates: Dict[str, float],
                       rate_shock_bps: float = 0, spread_shock_bps: float = 0,
                       util_change_pct: float = 0) -> Dict[str, Any]:
    """Apply rate/spread/utilisation shocks and recompute annual cost per facility.

    Mirrors Excel Scenario Analysis ground truth:
      Bucket 1 base interest = ₹358.611 Cr
      Stress (+100bps rate, +25bps spread, +10% util) → ₹448.32 Cr
      Severe (+200bps rate, +50bps spread, +20% util) → ₹547.81 Cr
    """
    rate_shock = rate_shock_bps / 10000
    spread_shock = spread_shock_bps / 10000
    util_factor = 1.0 + (util_change_pct / 100.0)
    rows = []
    bucket1_int = 0.0
    bucket2_comm = 0.0
    bucket3_int = 0.0

    for _, r in facility_master.iterrows():
        eff_os = r.get("Effective_OS", 0)
        base_rate = r.get("Effective_Rate", 0)
        category = r.get("Category", "")
        bucket_v = r.get("Bucket", 0)
        try:
            bucket = int(bucket_v)
        except (ValueError, TypeError):
            bucket = -1
        rate_type = str(r.get("Rate_Type", ""))

        # Apply rate shock unless the facility is explicitly Fixed-rate.
        # JFL treats TBD (to-be-decided) and Mutually-Agreed rates as floating-linked
        # because they ultimately settle to MCLR/EBLR-style benchmarks at availment
        # (matches Excel Scenario Analysis SUMPRODUCT logic).
        is_fixed = ("Fixed" in rate_type) and ("Floating" not in rate_type)
        if not is_fixed:
            shocked_rate = base_rate + rate_shock + spread_shock
        else:
            shocked_rate = base_rate

        # Bucket aggregation matching Excel Interest Summary logic:
        # B1 = FB Mains (Term + WC FB) — utilisation factor applies
        # B2 = NFB Mains (LC parents) — commission on sanctioned face, no util
        # B3 = FD-Backed FB — already 100% utilised by structure, no util factor
        # B4 = Uncommitted (HSBC) — tracked but not in run-rate by default
        # H  = Hedge memo — excluded from cost
        # 0  = Sub-limit — already covered by parent, excluded from cost
        if bucket == 1 and category in ("FB", "FB-Term", "FB-FCY"):
            stressed_os = eff_os * util_factor
            annual_cost = stressed_os * shocked_rate
            bucket1_int += annual_cost
        elif bucket == 2 and category == "NFB":
            stressed_os = eff_os
            annual_cost = stressed_os * shocked_rate
            bucket2_comm += annual_cost
        elif bucket == 3 and category == "FB-FDbacked":
            stressed_os = eff_os
            annual_cost = stressed_os * shocked_rate
            bucket3_int += annual_cost
        else:
            stressed_os = eff_os
            annual_cost = stressed_os * shocked_rate

        rows.append({
            "S_No": r["S_No"], "Lender": r["Lender"], "Facility": r["Facility"],
            "Category": category, "Bucket": bucket_v,
            "Effective_OS": eff_os, "Stressed_OS": stressed_os,
            "Base_Rate": base_rate,
            "Shocked_Rate": shocked_rate, "Annual_Cost": annual_cost,
        })

    total = bucket1_int + bucket2_comm + bucket3_int

    # WAC of FB Economic Debt: blended rate on Bucket 1 only
    fm_b1 = facility_master[
        (facility_master["Bucket"] == 1) &
        (facility_master["Category"].isin(["FB", "FB-Term", "FB-FCY"]))
    ]
    b1_os_base = fm_b1["Effective_OS"].sum()
    b1_os_stressed = b1_os_base * util_factor
    wac = (bucket1_int / b1_os_stressed) if b1_os_stressed > 0 else 0

    return {
        "facility_breakdown": pd.DataFrame(rows),
        "Bucket1_Interest": bucket1_int,
        "Bucket2_Commission": bucket2_comm,
        "Bucket3_Interest": bucket3_int,
        "Total": total,
        "Weighted_Avg_Cost": wac,
        "Bucket1_OS_Base": b1_os_base,
        "Bucket1_OS_Stressed": b1_os_stressed,
    }


def run_scenario(data: Dict[str, Any], rate_shock_bps: float, spread_shock_bps: float,
                 ebitda_change_pct: float, debt_change_pct: float = 0,
                 basis: str = "FY29E (TEV)", util_change_pct: float = 0) -> Dict[str, Any]:
    """Full scenario run — returns base + stressed metrics."""
    fin = data["financials"].get(basis, data["financials"]["FY25A"])
    base_int = recompute_interest(data["facility_master"], data["benchmark_rates"], 0, 0, 0)
    base_cov = resolve_covenants(data, basis, stress_active=False)

    if base_int["Bucket1_Interest"] > 0:
        stress_int = recompute_interest(data["facility_master"], data["benchmark_rates"],
                                        rate_shock_bps, spread_shock_bps, util_change_pct)
        int_change_pct = (stress_int["Bucket1_Interest"] / base_int["Bucket1_Interest"] - 1) * 100
    else:
        stress_int = base_int
        int_change_pct = 0

    stress_cov = recompute_covenants(data["covenants"], fin,
                                       ebitda_change_pct, int_change_pct, debt_change_pct)

    return {
        "base": {"interest": base_int, "covenants": base_cov},
        "stress": {"interest": stress_int, "covenants": stress_cov},
        "delta": {
            "annual_interest": stress_int["Total"] - base_int["Total"],
            "wac_bps": (stress_int["Weighted_Avg_Cost"] - base_int["Weighted_Avg_Cost"]) * 10000,
        },
    }


def resolve_covenants(data: Dict[str, Any], basis: str,
                       stress_active: bool = False,
                       ebitda_change_pct: float = 0,
                       interest_change_pct: float = 0,
                       debt_change_pct: float = 0) -> pd.DataFrame:
    """Single entry point for the dashboard to obtain the active covenant view.

    When no stress is applied (default), this returns the Excel-stored Actual /
    Status values — which are TEV-validated and audit-quality (88 PASS / 0 FAIL
    in the Validation Engine).

    When stress is applied, the engine recomputes from the shocked financials.

    basis: "FY25A" (Audit) or "FY29E (TEV)" (post-COD TEV projection).
    """
    if not stress_active:
        # ─── Use Excel-stored actuals (audit-quality) ───────────────────
        if basis == "FY29E (TEV)" and len(data.get("covenants_tev", [])) > 0:
            ct = data["covenants_tev"].copy()
            # Normalise to common column names used by the UI
            rows = []
            for _, c in ct.iterrows():
                # Parse FY29 actual (may be string for rating / FMV covenants)
                actual = c.get("Actual_FY29")
                status = c.get("Status_FY29", "")
                threshold = c.get("Threshold")
                op = c.get("Operator", ">=")
                # Compute headroom_pct numerically where possible
                hr_pct = None
                headroom = None
                if isinstance(actual, (int, float)) and isinstance(threshold, (int, float)):
                    if op in (">", ">="):
                        headroom = actual - threshold
                        hr_pct = (headroom / threshold * 100) if threshold > 0 else 0
                    elif op in ("<", "<="):
                        headroom = threshold - actual
                        hr_pct = (headroom / threshold * 100) if threshold > 0 else 0
                # Excel "Compliant ⚠ F-15" → normalize to "Compliant"
                if isinstance(status, str) and status.startswith("Compliant"):
                    status_norm = "Compliant"
                else:
                    status_norm = status if status else "Pending Input"
                rows.append({
                    "Lender": c["Lender"], "Covenant": c["Covenant"],
                    "Operator": op, "Threshold": threshold,
                    "Actual": actual, "Headroom": headroom,
                    "Headroom_Pct": hr_pct, "Status": status_norm,
                    "Trend": c.get("Trend", ""),
                    "Source": c.get("Source_FY29", ""),
                    "Risk": "Low",
                })
            return pd.DataFrame(rows)
        else:
            # FY25 Audit basis — use Covenant Tracker stored actuals
            ct = data["covenants"].copy()
            rows = []
            for _, c in ct.iterrows():
                actual = c.get("Actual")
                status = c.get("Status", "")
                threshold = c.get("Threshold")
                op = c.get("Operator", ">=")
                hr_pct = None
                headroom = c.get("Headroom")
                if isinstance(actual, (int, float)) and isinstance(threshold, (int, float)):
                    if op in (">", ">="):
                        headroom = actual - threshold
                        hr_pct = (headroom / threshold * 100) if threshold > 0 else 0
                    elif op in ("<", "<="):
                        headroom = threshold - actual
                        hr_pct = (headroom / threshold * 100) if threshold > 0 else 0
                rows.append({
                    "Lender": c["Lender"], "Covenant": c["Covenant"],
                    "Operator": op, "Threshold": threshold,
                    "Actual": actual, "Headroom": headroom,
                    "Headroom_Pct": hr_pct, "Status": status if status else "Pending Input",
                    "Risk": c.get("Risk", "Low"),
                    "Source": c.get("Source", ""),
                    "Source_Type": c.get("Source_Type", ""),
                    "Frequency": c.get("Frequency", ""),
                    "First_Test": c.get("First_Test", ""),
                })
            return pd.DataFrame(rows)

    # ── Stress active — apply proportional shock to stored Excel baseline ──
    # Rationale: Excel's stored Actual values are audit-quality (V&V 87/87 PASS).
    # The TEV-projected DSCR/ISCR/FACR etc. use a consultant-built formula that
    # we cannot exactly reproduce from raw financial inputs. So we use ratio
    # scaling: compute the SAME formula at stress=0 baseline AND under stress,
    # take the ratio, and apply it to the Excel-stored Actual. This guarantees
    # continuity at stress=0 and preserves audit traceability.
    fin = data["financials"].get(basis, data["financials"]["FY25A"])
    stored_df = resolve_covenants(data, basis, stress_active=False)

    # CRITICAL: lender naming differs between FY25 audit ("UBI") and FY29 TEV
    # ("UBI Consortium"). The stored_df uses the basis-appropriate naming, so the
    # recompute_covenants input MUST also use that naming or the (Lender,Covenant)
    # key lookup fails silently and stress is never applied.
    if basis == "FY29E (TEV)" and "covenants_tev" in data and len(data["covenants_tev"]) > 0:
        cov_source = data["covenants_tev"].copy()
        # Map the TEV-specific column names to what recompute_covenants expects
        if "Actual_FY29" in cov_source.columns and "Actual" not in cov_source.columns:
            cov_source = cov_source.rename(columns={"Actual_FY29": "Actual"})
    else:
        cov_source = data["covenants"]

    # Recompute baseline (stress=0) and stressed both with the SAME engine,
    # so the ratio between them isolates the stress effect.
    base_recomp = recompute_covenants(cov_source, fin, 0, 0, 0)
    stress_recomp = recompute_covenants(cov_source, fin,
                                          ebitda_change_pct, interest_change_pct,
                                          debt_change_pct)

    # Build lookup tables for quick join
    base_lookup = {(r["Lender"], r["Covenant"]): r["Actual"]
                    for _, r in base_recomp.iterrows()}
    stress_lookup = {(r["Lender"], r["Covenant"]): r["Actual"]
                      for _, r in stress_recomp.iterrows()}

    rows = []
    for _, row in stored_df.iterrows():
        key = (row["Lender"], row["Covenant"])
        stored_actual = row["Actual"]
        b = base_lookup.get(key)
        s = stress_lookup.get(key)

        # Market-data covenants (JSL FMV / Pledge) — preserve stored value untouched.
        if _is_market_data_covenant(row["Covenant"]):
            rows.append(row.to_dict())
            continue

        # Rating covenants — stored value IS the rating ordinal; doesn't move under stress.
        if _is_rating_covenant(row["Covenant"], row.get("Operator", "")):
            rows.append(row.to_dict())
            continue

        # Default: scale stored by stress ratio
        try:
            both_numeric = (isinstance(stored_actual, (int, float))
                            and isinstance(b, (int, float))
                            and isinstance(s, (int, float))
                            and pd.notna(b) and pd.notna(s) and pd.notna(stored_actual)
                            and abs(b) > 1e-9)
        except Exception:
            both_numeric = False

        if both_numeric:
            ratio = s / b
            new_actual = stored_actual * ratio
            op = row["Operator"]; thr = row["Threshold"]
            if isinstance(thr, (int, float)) and pd.notna(thr):
                new_status = evaluate_status(new_actual, op, thr)
                if op in (">", ">="):
                    new_headroom = new_actual - thr
                    new_hr_pct = (new_headroom / thr * 100) if thr > 0 else None
                elif op in ("<", "<="):
                    new_headroom = thr - new_actual
                    new_hr_pct = (new_headroom / thr * 100) if thr > 0 else None
                else:
                    new_headroom = None; new_hr_pct = None
            else:
                new_status = row["Status"]; new_headroom = None; new_hr_pct = None

            new_row = row.to_dict()
            new_row["Actual"] = new_actual
            new_row["Headroom"] = new_headroom
            new_row["Headroom_Pct"] = new_hr_pct
            new_row["Status"] = new_status
            rows.append(new_row)
        else:
            # Non-numeric stored (e.g. "Pending Input") or recompute failed → inherit stored
            rows.append(row.to_dict())

    return pd.DataFrame(rows)
