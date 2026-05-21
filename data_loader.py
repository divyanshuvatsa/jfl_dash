"""
Excel reader — JFL_Debt_Model_Final.xlsx is the single source of truth.

Reads pre-computed values from the Excel:
  - Facility Master (44 rows × 34 columns)
  - Lender Summary (5-bucket totals: B1 FB Mains, B2 NFB Mains, B3 FD-Backed,
    B4 Uncommitted, Hedge memo; plus Adjusted Consortium = B1+B2 − ICICI TL takeover)
  - Covenant Tracker (44 active covenants on FY25 audit basis)
  - FY29 Covenant Compliance — TEV-projected (44 covenants on TEV FY29 basis)
  - TEV Inputs (full FY23-FY38 P&L / BS / debt schedule)
  - Repayment Schedule (quarterly, Q1 FY24 to Q4 FY39, 7 TLs)
  - Interest Schedule (per-facility annual cost)
  - Scenario Analysis (Base / Stress / Severe presets)
  - Renewal & Review Calendar
  - Management Flags (F-01..F-15)
  - Validation Engine (87 integrity checks)
  - Security & Charge Matrix
  - Debt Pricing Table

The loader output dict preserves the JCL-compatible key names where possible
so downstream modules (dashboard_ui, visualizations, rule_based_ai,
scenario_engine) can be ported with minimum churn.

Falls back to recomputation only if Excel cells are blank.
"""

from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import warnings

import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")


# ─── PATH RESOLUTION ───────────────────────────────────────────────────────
def get_excel_path() -> Path:
    """Find the JFL Excel file. Checks env var, project root, and common locations."""
    candidates = []
    env_path = os.environ.get("JFL_EXCEL_PATH")
    if env_path:
        candidates.append(Path(env_path))
    here = Path(__file__).parent
    candidates.extend([
        here / "JFL_Debt_Model_Final.xlsx",
        here / "jfl_model.xlsx",
        Path.cwd() / "JFL_Debt_Model_Final.xlsx",
        Path.cwd() / "jfl_model.xlsx",
        Path("/mnt/user-data/uploads/jfl_model.xlsx"),
    ])
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # for error reporting


def _excel_engine() -> str:
    """Pick the fastest available Excel engine. Calamine is ~8x faster than openpyxl."""
    try:
        import python_calamine  # noqa: F401
        return "calamine"
    except ImportError:
        return "openpyxl"


_EXCEL_ENGINE = _excel_engine()


def file_signature(path: Path) -> str:
    """Cheap composite signature: mtime + size. No MD5 cost."""
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{int(stat.st_mtime)}_{stat.st_size}"


def file_mtime_pretty(path: Path) -> str:
    if not path.exists():
        return "FILE NOT FOUND"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d-%b-%Y %H:%M:%S")


def _safe_float(v, default=0.0):
    """Coerce to float; handle bool / string edge cases. Returns default for non-numeric strings."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes"):
            return 1.0
        if s in ("false", "no", "-", "pending", "pending input", "n/m", ""):
            return default
        try:
            return float(s)
        except (ValueError, TypeError):
            return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _safe_str(v, default=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    return str(v)


def _safe_ts(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return pd.NaT
    try:
        return pd.Timestamp(v)
    except Exception:
        return pd.NaT


# ─── EXCEL PARSING ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading JFL Excel...")
def load_excel(signature: str, path_str: str) -> Dict[str, Any]:
    """Read every relevant section of the JFL Excel.

    The signature parameter is the cache key — changes when file changes.
    """
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"JFL Excel not found at {path}. Place JFL_Debt_Model_Final.xlsx "
            f"in the project root."
        )

    out: Dict[str, Any] = {}

    # ─── Cover Page metadata ────────────────────────────────────────────
    cov = pd.read_excel(path, sheet_name="Cover Page", header=None,
                        engine=_EXCEL_ENGINE)
    out["borrower"] = "Jindal Ferrous Limited"
    out["short_name"] = "JFL"
    out["parent_group"] = "Jindal Stainless Group (Ratan Jindal Group)"
    out["project"] = "2.0 MTPA Greenfield Steel Making Unit, Kalinga Nagar, Odisha"
    out["model_version"] = "v11 — Independent V&V Audit (May-2026)"
    out["classification"] = "Confidential — Treasury / Senior Management / Audit"

    # ─── Instructions & Assumptions ─────────────────────────────────────
    ins = pd.read_excel(path, sheet_name="Instructions & Assumptions",
                        header=None, engine=_EXCEL_ENGINE)

    out["as_of_date"] = pd.Timestamp(ins.iloc[4, 1]).date()
    out["fx_rate"] = _safe_float(ins.iloc[5, 1], 84.5)
    out["use_full_util"] = bool(ins.iloc[6, 1]) if pd.notna(ins.iloc[6, 1]) else True
    out["days_in_year"] = int(_safe_float(ins.iloc[7, 1], 365))
    out["financial_basis"] = _safe_str(ins.iloc[8, 1], "Audited FY25")
    out["dcco"] = pd.Timestamp(ins.iloc[9, 1]).date() if pd.notna(ins.iloc[9, 1]) else None

    # Benchmark rates (rows 13-26)
    out["benchmark_rates"] = {}
    benchmark_map = {
        "1Y MCLR (UBI)": "1Y MCLR (UBI)",
        "EBLR (YES Bank)": "EBLR (YES Bank)",
        "EBLR (IDFC First)": "EBLR (IDFC First)",
        "3M I-MCLR (ICICI)": "3M I-MCLR (ICICI)",
        "6M I-MCLR (ICICI)": "6M I-MCLR (ICICI)",
        "14-day Repo (HDFC)": "14-day Repo (HDFC)",
        "Repo Rate": "Repo Rate",
        "FD Rate (HDFC)": "FD Rate (HDFC)",
        "Term SOFR (USD) 3M": "Term SOFR (USD)",
        "1Y MCLR (UBI) - RTL-II": "1Y MCLR (UBI) - RTL-II",
    }
    for i in range(12, 28):
        try:
            label = ins.iloc[i, 0]
            val = ins.iloc[i, 1]
            if pd.notna(label) and pd.notna(val) and isinstance(val, (int, float)):
                key = benchmark_map.get(str(label).strip())
                if key:
                    out["benchmark_rates"][key] = float(val)
        except Exception:
            continue

    # ─── JFL Financials (TWO bases: FY25 Audit and FY29 TEV-projected) ──
    # FY25 Audit: from Instructions Section C (rows 28-44)
    fy25 = {}
    audit_label_map = {
        "EBITDA": "EBITDA",
        "Total Debt (Gross)": "Total Debt",
        "Term Debt (LTD)": "Term Debt",
        "Tangible Net Worth (TNW)": "TNW",
        "Adjusted TNW (ATNW)": "ATNW",
        "Current Assets": "Current Assets",
        "Current Liabilities": "Current Liabilities",
        "Total Outside Liabilities (TOL)": "TOL",
        "Interest Expense (TTM)": "Interest Expense",
        "Fixed Assets (net block)": "Fixed Assets",
        "Secured Debt (outstanding)": "Secured Debt",
        "External Rating": "External Rating",
        "Promoter Shareholding %": "Promoter Shareholding",
        "Principal Repayment (TTM)": "Principal Repayment TTM",
        "Tax Paid (TTM)": "Tax Paid",
        "Scheduled TL Repayment (next 12M)": "Sched TL Repay",
    }
    for i in range(28, 46):
        try:
            label = ins.iloc[i, 0]
            if pd.isna(label):
                continue
            key = audit_label_map.get(str(label).strip())
            if not key:
                continue
            val = ins.iloc[i, 1]
            if pd.notna(val):
                if key == "External Rating":
                    fy25[key] = str(val)
                else:
                    fy25[key] = _safe_float(val, default=0.0)
        except Exception:
            continue

    # FY29 TEV-projected: derive from TEV Inputs sheet
    tev = pd.read_excel(path, sheet_name="TEV Inputs", header=None,
                        engine=_EXCEL_ENGINE)

    def _tev_row(row_idx: int, fy_col: int = 8) -> float:
        """Read a single TEV value. FY29 is in column index 8 (FY23=2, ..., FY29=8)."""
        try:
            return _safe_float(tev.iloc[row_idx, fy_col], default=0.0)
        except Exception:
            return 0.0

    # TEV row indices (validated from the workbook scan)
    # FY29 column = index 8 (FY23 is col 2 → FY29 is col 2+6 = 8)
    fy29 = {
        "EBITDA":              _tev_row(7),      # EBITDA row 7
        "Total Debt":          _tev_row(20) + _tev_row(22),  # LTD + ST WC borrowings
        "Term Debt":           _tev_row(20),     # TL closing balance
        "TNW":                 _tev_row(19),     # Total Equity
        "ATNW":                _tev_row(19),     # = TNW for JFL
        "Current Assets":      _tev_row(33),     # Total Current Assets
        "Current Liabilities": _tev_row(24),     # Total Current Liabilities
        "TOL":                 _tev_row(34) - _tev_row(19),  # Total Assets − Total Equity
        "Interest Expense":    _tev_row(10) + _tev_row(11),  # WC interest + TL interest
        "Fixed Assets":        _tev_row(28),     # Net Block
        "Secured Debt":        _tev_row(20),     # Term Loan LT
        "External Rating":     fy25.get("External Rating", "Pending"),
        "Promoter Shareholding": 1.0,
        "Principal Repayment TTM": _tev_row(39),
        "Tax Paid":            _tev_row(13),     # Tax Expense as proxy
        "Sched TL Repay":      _tev_row(39),     # Term Loan Repayment
    }

    # Active basis = audit by default; UI lets user toggle.
    out["financials"] = {
        "FY25A": fy25,
        "FY29E (TEV)": fy29,
        "Active": fy25,
    }

    # Sanction caps (rows 47-58)
    out["caps"] = {}
    for i in range(46, 60):
        try:
            label = ins.iloc[i, 0]
            val = ins.iloc[i, 1]
            if pd.notna(label) and pd.notna(val) and isinstance(val, (int, float)):
                out["caps"][str(label).strip()] = float(val)
        except Exception:
            continue

    # ─── Facility Master ────────────────────────────────────────────────
    fm_raw = pd.read_excel(path, sheet_name="Facility Master", header=3,
                            engine=_EXCEL_ENGINE)
    fm_raw = fm_raw[pd.to_numeric(fm_raw["S.No"], errors="coerce").notna()].copy()
    fm_raw["S.No"] = fm_raw["S.No"].astype(int)

    fm_records = []
    for _, r in fm_raw.iterrows():
        bucket_raw = r.get("Bucket")
        # Bucket can be 1, 2, 3, 4, "H" (hedge), 0 (sub-limit)
        try:
            bucket = int(bucket_raw)
        except (ValueError, TypeError):
            bucket = str(bucket_raw) if pd.notna(bucket_raw) else 0

        fm_records.append({
            "S_No": int(r["S.No"]),
            "Lender": str(r["Lender"]),
            "Facility": str(r["Facility"]),
            "Category": str(r["Category"]),
            "Nature": _safe_str(r["Nature"]),
            "Sub_Limit_Flag": bool(r["Sub-Limit Flag"]) if pd.notna(r["Sub-Limit Flag"]) else False,
            "FD_Backed": bool(r["FD-Backed"]) if pd.notna(r["FD-Backed"]) else False,
            "NFB_Contingent_Flag": bool(r.get("NFB Contingent Flag", False)),
            "Takeover_Flag": bool(r.get("Takeover Flag", False)),
            "Bucket": bucket,
            "Currency": _safe_str(r["Currency"], "INR"),
            "Sanc_Orig_Ccy": _safe_float(r["Sanc Orig Ccy"]),
            "Sanction_INR": _safe_float(r["Sanc INR Cr"]),
            "Current_OS": _safe_float(r["Current O/S"]),
            "Effective_OS": _safe_float(r["Eff O/S"]),
            "Util_Pct": _safe_float(r["Util %"]),
            "Headroom": _safe_float(r["Headroom"]),
            "Benchmark": _safe_str(r["Benchmark"]),
            "Spread_BPS": _safe_float(r["Spread"]) * 10000,
            "Effective_Rate": _safe_float(r["Eff Rate p.a."]),
            "Rate_Type": _safe_str(r["Rate Type"]),
            "Moratorium_Months": int(_safe_float(r["Moratorium Mths"])),
            "Repayment_Frequency": _safe_str(r["Rep Frequency"]),
            "Tenor_Months": int(_safe_float(r["Tenor Mths"])),
            "Num_Instalments": int(_safe_float(r["No of Instals"])),
            "Drawdown_Date": _safe_ts(r["Drawdown Date"]),
            "Rep_Start_Date": _safe_ts(r["Rep Start Date"]),
            "Maturity_Date": _safe_ts(r["Maturity Date"]),
            "Sanction_Date": _safe_ts(r["Sanction Date"]),
            "Validity_Date": _safe_ts(r["Validity Date"]),
            "Purpose": _safe_str(r["Purpose"]),
            "Security_Summary": _safe_str(r["Security Summary"]),
            "Sanction_Reference": _safe_str(r["Sanction Reference"]),
            "Remarks": _safe_str(r["Remarks"]),
        })
    out["facility_master"] = pd.DataFrame(fm_records)

    # ─── Covenant Tracker (FY25 audit basis) ────────────────────────────
    cov_raw = pd.read_excel(path, sheet_name="Covenant Tracker", header=2,
                            engine=_EXCEL_ENGINE)
    cov_records = []
    for _, r in cov_raw.iterrows():
        lender_v = r.get("Lender")
        cov_v = r.get("Covenant")
        if pd.isna(lender_v) or pd.isna(cov_v):
            continue
        lender_str = str(lender_v)
        # Skip section headers / summary rows
        if lender_str.startswith(("[REMOVED", "Covenant Dashboard", "Total ",
                                  "Compliant", "Near", "Breached", "Pending",
                                  "Portfolio")):
            continue

        cov_records.append({
            "Lender": lender_str,
            "Covenant": str(cov_v),
            "Operator": _safe_str(r["Operator"]),
            "Threshold": r["Threshold"] if pd.notna(r["Threshold"]) else None,
            "Actual": r["Actual"] if pd.notna(r["Actual"]) else None,
            "Headroom": r["Headroom"] if pd.notna(r["Headroom"]) else None,
            "Status": _safe_str(r["Status"], "Pending"),
            "Risk": _safe_str(r.get("Risk", "Low")),
            "Source": _safe_str(r.get("Source / Notes", "")),
            "Source_Type": _safe_str(r.get("Source Type", "")),
            "Frequency": _safe_str(r.get("Reporting Frequency", "")),
            "First_Test": _safe_str(r.get("First Test Date", "")),
        })
    out["covenants"] = pd.DataFrame(cov_records)

    # ─── FY29 Covenant Compliance (TEV-projected) ───────────────────────
    cov_tev_raw = pd.read_excel(path, sheet_name="FY29 Covenant Compliance (TEV)",
                                 header=3, engine=_EXCEL_ENGINE)
    cov_tev_records = []
    for _, r in cov_tev_raw.iterrows():
        if pd.isna(r.get("Lender")) or pd.isna(r.get("Covenant")):
            continue
        lender_str = str(r["Lender"])
        if lender_str.startswith(("SUMMARY", "COVENANTS REMOVED", "KEY INSIGHTS",
                                  "Compliant", "Near", "Breached", "Status",
                                  "Pending", "TOTAL", "R#")):
            continue
        cov_tev_records.append({
            "Lender": lender_str,
            "Covenant": _safe_str(r["Covenant"]),
            "Operator": _safe_str(r.get("Op", ">=")),
            "Threshold": r.get("Threshold") if pd.notna(r.get("Threshold")) else None,
            "Actual_FY29": r["FY29 Actual\n(TEV)"] if pd.notna(r.get("FY29 Actual\n(TEV)")) else None,
            "Status_FY29": _safe_str(r.get("FY29 Status\n(TEV)", "")),
            "Headroom_FY29": _safe_str(r.get("Headroom", "")),
            "Actual_FY25": r["FY25 Audit\nActual"] if pd.notna(r.get("FY25 Audit\nActual")) else None,
            "Status_FY25": _safe_str(r.get("FY25 Audit\nStatus", "")),
            "Trend": _safe_str(r.get("Trend FY25→29", "")),
            "Source_FY29": _safe_str(r.get("Source", "")),
        })
    out["covenants_tev"] = pd.DataFrame(cov_tev_records)

    # ─── Lender Summary (5-bucket framework) ────────────────────────────
    ls = pd.read_excel(path, sheet_name="Lender Summary", header=None,
                       engine=_EXCEL_ENGINE)

    # Section A: Per-lender Sanctioned Debt (B1 + B2 + NFB contingent count) — rows 5-13
    lender_records = []
    for i in range(5, 14):
        if pd.notna(ls.iloc[i, 0]) and str(ls.iloc[i, 0]) != "Grand Total":
            lender_records.append({
                "Lender": str(ls.iloc[i, 0]),
                "FB_Mains_B1": _safe_float(ls.iloc[i, 1]),
                "NFB_Mains_B2": _safe_float(ls.iloc[i, 2]),
                "Sanctioned_Debt": _safe_float(ls.iloc[i, 3]),
                "Pct_Sanctioned": _safe_float(ls.iloc[i, 4]),
                "Facility_Count_B1B2": int(_safe_float(ls.iloc[i, 5])),
                "NFB_Contingent": _safe_float(ls.iloc[i, 6]),
            })
    out["lender_summary"] = pd.DataFrame(lender_records)

    # JCL-compatibility alias — downstream code that expects 'lender_bucket1'
    # gets a DataFrame with the same shape as JCL's lender_bucket1.
    bucket1_compat = []
    fm_df = out["facility_master"]
    tl_per_lender = (
        fm_df[fm_df["Category"] == "FB-Term"]
        .groupby("Lender")["Sanction_INR"].sum().to_dict()
    )
    for rec in lender_records:
        bucket1_compat.append({
            "Lender": rec["Lender"],
            "TL_Sanctioned": float(tl_per_lender.get(rec["Lender"], 0.0)),
            "WC_FB_Cap": max(0.0, rec["FB_Mains_B1"] - float(tl_per_lender.get(rec["Lender"], 0.0))),
            "Bucket1_Total_Debt": rec["Sanctioned_Debt"],
        })
    out["lender_bucket1"] = pd.DataFrame(bucket1_compat)

    # Bucket 2 NFB Contingent per lender (rows 5-13, col 6)
    bucket2_compat = []
    for rec in lender_records:
        bucket2_compat.append({
            "Lender": rec["Lender"],
            "LCs": rec["NFB_Mains_B2"],
            "SBLCs": 0.0,
            "BGs_memo": 0.0,
            "Capex_LCs": max(0.0, rec["NFB_Contingent"] - rec["NFB_Mains_B2"]),
            "Bucket2_Total_NFB": rec["NFB_Contingent"],
        })
    out["lender_bucket2"] = pd.DataFrame(bucket2_compat)

    # Section C: FD-Backed (Bucket 3) — rows 32-40
    fd_records = []
    for i in range(32, 41):
        if pd.notna(ls.iloc[i, 0]) and str(ls.iloc[i, 0]) not in ("Grand Total (FD-Backed)",):
            fd_records.append({
                "Lender": str(ls.iloc[i, 0]),
                "FD_Backed": _safe_float(ls.iloc[i, 1]),
                "Hedge_Notional": 0.0,
                "Bucket3_Total": _safe_float(ls.iloc[i, 1]),
                "Pct_FD": _safe_float(ls.iloc[i, 2]),
            })
    out["lender_bucket3"] = pd.DataFrame(fd_records)

    # Section B: Key KPIs (used as ground truth for totals)
    # Layout (col 2 holds the value — col 1 is merged with col 2 in source):
    #   row 20 = Sanctioned (B1+B2);   row 21 = B1 only;  row 22 = B2 only;
    #   row 23 = NFB Contingent;       row 24 = FD-Backed; row 25 = Uncommitted;
    #   row 26 = Hedge memo;           row 27 = ICICI TL takeover;
    #   row 28 = Adjusted Consortium
    out["totals"] = {
        # JCL-compatible aliases — populate the same keys the JCL UI expects
        "Bucket1_Sanctioned_Debt": _safe_float(ls.iloc[20, 2]),  # 4466
        "Bucket2_NFB_Contingent":  _safe_float(ls.iloc[23, 2]),  # 2040
        "Bucket3_Separate":        _safe_float(ls.iloc[24, 2]),  # 150
        # JFL-specific extras
        "FB_Mains_B1":             _safe_float(ls.iloc[21, 2]),  # 3916
        "NFB_Mains_B2":            _safe_float(ls.iloc[22, 2]),  # 550
        "NFB_Contingent":          _safe_float(ls.iloc[23, 2]),  # 2040
        "FD_Backed_B3":            _safe_float(ls.iloc[24, 2]),  # 150
        "Uncommitted_B4":          _safe_float(ls.iloc[25, 2]),  # 1000
        "Hedge_Memo":              _safe_float(ls.iloc[26, 2]),  # 75
        "ICICI_TL_Takeover":       _safe_float(ls.iloc[27, 2]),  # 840
        "Adjusted_Consortium":     _safe_float(ls.iloc[28, 2]),  # 3626
    }

    # Lender concentration (per-lender shares of Sanctioned Debt)
    conc = []
    sd_total = out["totals"]["Bucket1_Sanctioned_Debt"]
    for rec in lender_records:
        if rec["Sanctioned_Debt"] > 0:
            conc.append({
                "Lender": rec["Lender"],
                "Sanctioned_Debt": rec["Sanctioned_Debt"],
                "Pct_Sanctioned_Debt": rec["Sanctioned_Debt"] / sd_total if sd_total else 0,
            })
    out["lender_concentration"] = pd.DataFrame(conc)

    # ─── Interest Schedule ──────────────────────────────────────────────
    int_raw = pd.read_excel(path, sheet_name="Interest Schedule", header=2,
                             engine=_EXCEL_ENGINE)
    int_records = []
    for _, r in int_raw.iterrows():
        sno = pd.to_numeric(r.get("S.No"), errors="coerce")
        if pd.isna(sno):
            continue
        bucket_raw = r.get("Bucket")
        try:
            bucket = int(bucket_raw)
        except (ValueError, TypeError):
            bucket = str(bucket_raw) if pd.notna(bucket_raw) else 0
        int_records.append({
            "S_No": int(sno),
            "Lender": str(r["Lender"]),
            "Facility": str(r["Facility"]),
            "Category": str(r["Category"]),
            "Bucket": bucket,
            "Sanction_INR": _safe_float(r["Sanc ₹ Cr"]),
            "Effective_OS": _safe_float(r["Eff O/S"]),
            "Effective_Rate": _safe_float(r["Eff Rate"]),
            "Annual_Cost": _safe_float(r["Annual Interest/Comm. ₹Cr"]),
            "Currency": _safe_str(r.get("Ccy", "INR")),
            "Remarks": _safe_str(r.get("Remarks", "")),
        })
    out["interest_schedule"] = pd.DataFrame(int_records)

    # Interest summary block — values are in column 8 (Annual Interest column)
    int_summary_raw = pd.read_excel(path, sheet_name="Interest Schedule",
                                     header=None, engine=_EXCEL_ENGINE)
    out["interest_summary"] = {
        "Bucket1_Interest":         _safe_float(int_summary_raw.iloc[50, 8]),  # 358.611
        "Bucket2_Commission":       _safe_float(int_summary_raw.iloc[51, 8]),  # 3.05
        "Bucket3_Interest":         _safe_float(int_summary_raw.iloc[52, 8]),  # 13.5
        "Total_Interest_Commission":_safe_float(int_summary_raw.iloc[53, 8]),  # 375.161
        "Bucket4_Theoretical":      _safe_float(int_summary_raw.iloc[54, 8]),  # 90
        "Bucket0_Sublimit":         _safe_float(int_summary_raw.iloc[55, 8]),  # 253.4464
        "Weighted_Avg_Cost":        _safe_float(int_summary_raw.iloc[60, 8]),  # 0.0916
    }

    # ─── Repayment Schedule (quarterly, 7 TLs) ──────────────────────────
    rep_raw = pd.read_excel(path, sheet_name="Repayment Schedule",
                             header=None, engine=_EXCEL_ENGINE)
    # JFL layout: rows 0-1 are titles; rows 2-3 are 2-row headers; data starts row 4.
    # Columns: 0=#, 1=Period End, 2=Label,
    #   3-7   UBI RTL-I:    Opening, Drawdown, Prin Rep, Interest, Closing
    #   8-12  UBI RTL-II:   ...
    #   13-17 Indian Bank:  ...
    #   18-22 RBL Bridge:   ...
    #   23-27 YES Bank:     ...
    #   28-32 IDFC First:   ...
    #   33-37 ICICI TL:     ...
    #   38-41 Consolidated: Total Prin, Total Int, Total DS, Combined O/S
    rep_records = []
    for i in range(4, len(rep_raw)):
        period_end = rep_raw.iloc[i, 1]
        label = rep_raw.iloc[i, 2]
        if pd.isna(period_end):
            continue
        if not isinstance(period_end, (pd.Timestamp, datetime)):
            continue
        try:
            rec = {
                "Period_End": pd.Timestamp(period_end),
                "Period_Label": _safe_str(label),
                # Per-lender opening / drawdown / principal / interest / closing
                "UBI_RTL_I_Opening":   _safe_float(rep_raw.iloc[i, 3]),
                "UBI_RTL_I_Drawdown":  _safe_float(rep_raw.iloc[i, 4]),
                "UBI_RTL_I_Principal": _safe_float(rep_raw.iloc[i, 5]),
                "UBI_RTL_I_Interest":  _safe_float(rep_raw.iloc[i, 6]),
                "UBI_RTL_I_Closing":   _safe_float(rep_raw.iloc[i, 7]),
                "UBI_RTL_II_Opening":  _safe_float(rep_raw.iloc[i, 8]),
                "UBI_RTL_II_Drawdown": _safe_float(rep_raw.iloc[i, 9]),
                "UBI_RTL_II_Principal":_safe_float(rep_raw.iloc[i, 10]),
                "UBI_RTL_II_Interest": _safe_float(rep_raw.iloc[i, 11]),
                "UBI_RTL_II_Closing":  _safe_float(rep_raw.iloc[i, 12]),
                "Indian_Bank_Opening":  _safe_float(rep_raw.iloc[i, 13]),
                "Indian_Bank_Drawdown": _safe_float(rep_raw.iloc[i, 14]),
                "Indian_Bank_Principal":_safe_float(rep_raw.iloc[i, 15]),
                "Indian_Bank_Interest": _safe_float(rep_raw.iloc[i, 16]),
                "Indian_Bank_Closing":  _safe_float(rep_raw.iloc[i, 17]),
                "RBL_Opening":   _safe_float(rep_raw.iloc[i, 18]),
                "RBL_Drawdown":  _safe_float(rep_raw.iloc[i, 19]),
                "RBL_Principal": _safe_float(rep_raw.iloc[i, 20]),
                "RBL_Interest":  _safe_float(rep_raw.iloc[i, 21]),
                "RBL_Closing":   _safe_float(rep_raw.iloc[i, 22]),
                "YBL_Opening":   _safe_float(rep_raw.iloc[i, 23]),
                "YBL_Drawdown":  _safe_float(rep_raw.iloc[i, 24]),
                "YBL_Principal": _safe_float(rep_raw.iloc[i, 25]),
                "YBL_Interest":  _safe_float(rep_raw.iloc[i, 26]),
                "YBL_Closing":   _safe_float(rep_raw.iloc[i, 27]),
                "IDFC_Opening":   _safe_float(rep_raw.iloc[i, 28]),
                "IDFC_Drawdown":  _safe_float(rep_raw.iloc[i, 29]),
                "IDFC_Principal": _safe_float(rep_raw.iloc[i, 30]),
                "IDFC_Interest":  _safe_float(rep_raw.iloc[i, 31]),
                "IDFC_Closing":   _safe_float(rep_raw.iloc[i, 32]),
                "ICICI_TL_Opening":   _safe_float(rep_raw.iloc[i, 33]),
                "ICICI_TL_Drawdown":  _safe_float(rep_raw.iloc[i, 34]),
                "ICICI_TL_Principal": _safe_float(rep_raw.iloc[i, 35]),
                "ICICI_TL_Interest":  _safe_float(rep_raw.iloc[i, 36]),
                "ICICI_TL_Closing":   _safe_float(rep_raw.iloc[i, 37]),
                "Total_Principal": _safe_float(rep_raw.iloc[i, 38]),
                "Total_Interest":  _safe_float(rep_raw.iloc[i, 39]),
                "Total_DS":        _safe_float(rep_raw.iloc[i, 40]),
                "Combined_OS":     _safe_float(rep_raw.iloc[i, 41]),
            }
            rep_records.append(rec)
        except Exception:
            continue
    out["repayment_schedule"] = pd.DataFrame(rep_records)

    # ─── Scenario Analysis ──────────────────────────────────────────────
    sc_raw = pd.read_excel(path, sheet_name="Scenario Analysis",
                            header=None, engine=_EXCEL_ENGINE)
    out["scenario_inputs"] = {
        # Row 5 = Rate Shock; col 2=Base, 3=Stress, 4=Severe
        "Rate_Shock_BPS":    [_safe_float(sc_raw.iloc[5, 2])*10000,
                              _safe_float(sc_raw.iloc[5, 3])*10000,
                              _safe_float(sc_raw.iloc[5, 4])*10000],
        "Spread_BPS":        [_safe_float(sc_raw.iloc[6, 2])*10000,
                              _safe_float(sc_raw.iloc[6, 3])*10000,
                              _safe_float(sc_raw.iloc[6, 4])*10000],
        "Util_Change_Pct":   [_safe_float(sc_raw.iloc[7, 2])*100,
                              _safe_float(sc_raw.iloc[7, 3])*100,
                              _safe_float(sc_raw.iloc[7, 4])*100],
        "EBITDA_Change_Pct": [_safe_float(sc_raw.iloc[8, 2])*100,
                              _safe_float(sc_raw.iloc[8, 3])*100,
                              _safe_float(sc_raw.iloc[8, 4])*100],
        "Debt_Change_Pct":   [_safe_float(sc_raw.iloc[9, 2])*100,
                              _safe_float(sc_raw.iloc[9, 3])*100,
                              _safe_float(sc_raw.iloc[9, 4])*100],
    }
    out["scenario_outputs"] = {
        "Annual_B1_Interest":[_safe_float(sc_raw.iloc[13, 2]),
                              _safe_float(sc_raw.iloc[13, 3]),
                              _safe_float(sc_raw.iloc[13, 4])],
        "DSCR_Stressed":     [_safe_float(sc_raw.iloc[14, 2]),
                              _safe_float(sc_raw.iloc[14, 3]),
                              _safe_float(sc_raw.iloc[14, 4])],
        "Total_Debt_EBITDA": [_safe_float(sc_raw.iloc[15, 2]),
                              _safe_float(sc_raw.iloc[15, 3]),
                              _safe_float(sc_raw.iloc[15, 4])],
        "ICR":               [_safe_float(sc_raw.iloc[16, 2]),
                              _safe_float(sc_raw.iloc[16, 3]),
                              _safe_float(sc_raw.iloc[16, 4])],
    }
    # Rate sensitivity table (rows 22-30, value in col 2)
    rate_sens = []
    for i in range(22, 32):
        try:
            label = sc_raw.iloc[i, 0]
            val = sc_raw.iloc[i, 2]
            if pd.notna(label) and pd.notna(val) and isinstance(val, (int, float)):
                lbl_str = str(label)
                if "Total" in lbl_str:
                    continue
                rate_sens.append({"Benchmark": lbl_str, "Delta_Interest_100bps": float(val)})
        except Exception:
            continue
    out["rate_sensitivity"] = pd.DataFrame(rate_sens)

    # ─── Management Flags (F-01..F-15) ──────────────────────────────────
    mf_raw = pd.read_excel(path, sheet_name="Management Flags", header=3,
                            engine=_EXCEL_ENGINE)
    mf_records = []
    for _, r in mf_raw.iterrows():
        flag = r.get("Flag #")
        if pd.isna(flag) or not str(flag).startswith("F-"):
            continue
        mf_records.append({
            "Flag": str(flag),
            "Severity": _safe_str(r.get("Severity", "Low")),
            "Category": _safe_str(r.get("Category", "")),
            "Lender_Sheet": _safe_str(r.get("Lender / Sheet", "")),
            "Description": _safe_str(r.get("Description", "")),
            "Source": _safe_str(r.get("Source / Trigger", "")),
            "Action": _safe_str(r.get("Action Required", "")),
            "Owner": _safe_str(r.get("Owner", "")),
            "Status": _safe_str(r.get("Status", "Open")),
        })
    out["management_flags"] = pd.DataFrame(mf_records)

    # ─── Validation Engine ──────────────────────────────────────────────
    ve_raw = pd.read_excel(path, sheet_name="Validation Engine", header=11,
                            engine=_EXCEL_ENGINE)
    ve_records = []
    for _, r in ve_raw.iterrows():
        cid = r.get("Check ID")
        if pd.isna(cid) or not str(cid).startswith("VJF"):
            continue
        ve_records.append({
            "Check_ID": str(cid),
            "Description": _safe_str(r.get("Description", "")),
            "Expected": _safe_str(r.get("Expected", "")),
            "Actual": _safe_str(r.get("Actual", "")),
            "Status": _safe_str(r.get("Status", "")),
            "Severity": _safe_str(r.get("Severity", "")),
            "Group": _safe_str(r.get("Group", "")),
        })
    out["validation_engine"] = pd.DataFrame(ve_records)

    # Master status summary
    ve_full = pd.read_excel(path, sheet_name="Validation Engine", header=None,
                             engine=_EXCEL_ENGINE)
    try:
        out["validation_summary"] = {
            "Total_Checks":  int(_safe_float(ve_full.iloc[102, 1])),
            "Pass_Count":    int(_safe_float(ve_full.iloc[103, 1])),
            "Fail_Count":    int(_safe_float(ve_full.iloc[104, 1])),
            "Critical_Fail": int(_safe_float(ve_full.iloc[105, 1])),
            "Overall_Status":_safe_str(ve_full.iloc[106, 1], "✓ PASS"),
        }
    except Exception:
        out["validation_summary"] = {
            "Total_Checks": len(ve_records),
            "Pass_Count":   sum(1 for r in ve_records if r["Status"] == "PASS"),
            "Fail_Count":   sum(1 for r in ve_records if r["Status"] != "PASS"),
            "Critical_Fail": 0,
            "Overall_Status": "✓ PASS",
        }

    # ─── Renewal & Review Calendar ──────────────────────────────────────
    ren_raw = pd.read_excel(path, sheet_name="Renewal & Review Calendar",
                             header=2, engine=_EXCEL_ENGINE)
    ren_records = []
    for _, r in ren_raw.iterrows():
        sno = pd.to_numeric(r.get("S.No"), errors="coerce")
        if pd.isna(sno):
            continue
        ren_records.append({
            "S_No": int(sno),
            "Lender": _safe_str(r["Lender"]),
            "Facility": _safe_str(r["Facility"]),
            "Sanction_Date": _safe_ts(r["Sanction Date"]),
            "Validity_Maturity": _safe_ts(r["Validity / Maturity"]),
            "Days": int(_safe_float(r["Days"])),
            "Status": _safe_str(r["Status"]),
            "Action": _safe_str(r["Action"]),
        })
    out["renewal_calendar"] = pd.DataFrame(ren_records)

    # ─── Security & Charge Matrix ───────────────────────────────────────
    sec_raw = pd.read_excel(path, sheet_name="Security & Charge Matrix",
                             header=2, engine=_EXCEL_ENGINE)
    sec_records = []
    for _, r in sec_raw.iterrows():
        lender = r.get("Lender")
        if pd.isna(lender):
            continue
        sec_records.append({
            "Lender": str(lender),
            "Facilities_Count": int(_safe_float(r["# Facilities"])),
            "Sanctioned": _safe_float(r["Sanctioned ₹ Cr"]),
            "Guarantee": _safe_str(r["Personal/Corp Guarantee"]),
            "Charge_Type": _safe_str(r["Charge Type"]),
            "Security_Description": _safe_str(r["Security Description"]),
        })
    out["security_matrix"] = pd.DataFrame(sec_records)

    # ─── Debt Pricing Table ─────────────────────────────────────────────
    dp_raw = pd.read_excel(path, sheet_name="Debt Pricing Table", header=2,
                            engine=_EXCEL_ENGINE)
    dp_records = []
    for _, r in dp_raw.iterrows():
        no = pd.to_numeric(r.get("#"), errors="coerce")
        if pd.isna(no):
            continue
        dp_records.append({
            "S_No": int(no),
            "Lender": _safe_str(r["Lender"]),
            "Facility": _safe_str(r["Facility"]),
            "Currency": _safe_str(r["Ccy"]),
            "Benchmark": _safe_str(r["Benchmark / Reference Rate"]),
            "Spread_BPS": _safe_float(r["Spread (bps)"]),
            "Effective_Rate": _safe_float(r["Eff. Rate p.a."]),
            "Rate_Type": _safe_str(r["Rate Type"]),
            "Source": _safe_str(r["Source"]),
        })
    out["debt_pricing"] = pd.DataFrame(dp_records)

    # ─── TEV-projected ratios for FY27-FY38 (used for forward look) ─────
    tev_ratios = {}
    fy_labels = [f"FY{y}" for y in range(23, 39)]
    for i, fy in enumerate(fy_labels):
        col = i + 2  # FY23 = col index 2
        tev_ratios[fy] = {
            "EBITDA":           _tev_row(7, col),
            "Term_Debt":        _tev_row(20, col),
            "Total_Equity":     _tev_row(19, col),
            "Net_Block":        _tev_row(28, col),
            "Interest_TL":      _tev_row(11, col),
            "Interest_WC":      _tev_row(10, col),
            "TL_Repayment":     _tev_row(39, col),
            "DSCR":             _tev_row(45, col),
            "ISCR":             _tev_row(46, col),
            "FACR":             _tev_row(47, col),
            "LTD_EBITDA":       _tev_row(48, col),
            "LTD_Equity":       _tev_row(49, col),
        }
    out["tev_ratios"] = tev_ratios

    return out


# ─── PUBLIC API ────────────────────────────────────────────────────────────
def load_all_data() -> Dict[str, Any]:
    """Public entry point. Returns full data dictionary with file metadata."""
    path = get_excel_path()
    sig = file_signature(path)
    if not path.exists():
        return {
            "error": f"JFL Excel not found at {path}",
            "excel_exists": False,
            "excel_path": str(path),
            "excel_mtime": "FILE NOT FOUND",
            "excel_signature": "missing",
        }
    data = load_excel(sig, str(path))
    data["excel_exists"] = True
    data["excel_path"] = str(path)
    data["excel_mtime"] = file_mtime_pretty(path)
    data["excel_signature"] = sig
    return data


def force_reload():
    """Clear cache. Called by Reload button or after Excel upload."""
    st.cache_data.clear()
    try:
        st.cache_resource.clear()
    except Exception:
        pass


def save_uploaded_excel(uploaded_file_bytes: bytes) -> Path:
    """Persist uploaded Excel to project root, replacing the bundled file."""
    target = get_excel_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(uploaded_file_bytes)
    return target
