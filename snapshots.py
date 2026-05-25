"""Historical snapshots, save current state, compare against past states.

Storage: st.session_state (in-memory) + JSON export/import for cross-session
persistence. Mirrors JCL snapshots.py; adapted for JFL's 5-bucket framework
and dual covenant basis.
"""

from __future__ import annotations
import json
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import streamlit as st


def _extract_state(data: Dict[str, Any], cov_df: pd.DataFrame) -> Dict[str, Any]:
    """Extract key metrics from current state into a snapshottable dict."""
    t = data["totals"]
    isum = data["interest_summary"]
    fy25 = data["financials"].get("FY25A", {})

    state = {
        "as_of_date": str(data["as_of_date"]),
        "fx_rate": float(data["fx_rate"]),
        "excel_signature": data.get("excel_signature", ""),
        "excel_mtime": data.get("excel_mtime", ""),

        # 5-bucket totals
        "Sanctioned_Debt_B1B2": float(t["Bucket1_Sanctioned_Debt"]),
        "FB_Mains_B1":          float(t["FB_Mains_B1"]),
        "NFB_Mains_B2":         float(t["NFB_Mains_B2"]),
        "NFB_Contingent":       float(t["NFB_Contingent"]),
        "FD_Backed_B3":         float(t["FD_Backed_B3"]),
        "Uncommitted_B4":       float(t["Uncommitted_B4"]),
        "Hedge_Memo":           float(t["Hedge_Memo"]),
        "ICICI_TL_Takeover":    float(t["ICICI_TL_Takeover"]),
        "Adjusted_Consortium":  float(t["Adjusted_Consortium"]),

        # Cost
        "Annual_Run_Rate":      float(isum["Total_Interest_Commission"]),
        "Bucket1_Interest":     float(isum["Bucket1_Interest"]),
        "Bucket2_Commission":   float(isum["Bucket2_Commission"]),
        "Bucket3_Interest":     float(isum["Bucket3_Interest"]),
        "Weighted_Avg_Cost":    float(isum["Weighted_Avg_Cost"]),

        # FY25 audit financials
        "EBITDA_FY25":          float(fy25.get("EBITDA", 0)),
        "Total_Debt_FY25":      float(fy25.get("Total Debt", 0)),
        "Term_Debt_FY25":       float(fy25.get("Term Debt", 0)),
        "TNW_FY25":             float(fy25.get("TNW", 0)),
        "Interest_Expense_FY25":float(fy25.get("Interest Expense", 0)),

        # Covenant counts
        "Total_Covenants":      len(cov_df),
        "Compliant":            int((cov_df["Status"] == "Compliant").sum()),
        "Watch":                int((cov_df["Status"] == "Watch").sum()),
        "Near_Breach":          int((cov_df["Status"] == "Near Breach").sum()),
        "Breached":             int((cov_df["Status"] == "Breached").sum()),
        "Pending_Input":        int((cov_df["Status"] == "Pending Input").sum()),

        "covenant_actuals": {},
    }

    # Per-covenant actuals (numeric only)
    for _, r in cov_df.iterrows():
        key = f"{r['Lender']}::{r['Covenant']}"
        actual = r.get("Actual")
        if isinstance(actual, (int, float)) and pd.notna(actual):
            state["covenant_actuals"][key] = float(actual)

    # Per-lender exposure
    state["lender_exposure"] = {}
    ls = data["lender_summary"]
    for _, r in ls.iterrows():
        if r["Sanctioned_Debt"] > 0:
            state["lender_exposure"][r["Lender"]] = float(r["Sanctioned_Debt"])

    return state


def take_snapshot(data: Dict[str, Any], cov_df: pd.DataFrame, label: str = "") -> Dict[str, Any]:
    """Capture current state and store in session_state."""
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = []

    timestamp = datetime.now()
    snap = {
        "id": f"snap_{timestamp.strftime('%Y%m%d_%H%M%S')}",
        "label": label or f"Snapshot {timestamp.strftime('%d-%b-%Y %H:%M')}",
        "captured_at": timestamp.isoformat(),
        "captured_at_pretty": timestamp.strftime("%d-%b-%Y %H:%M:%S"),
        "state": _extract_state(data, cov_df),
    }
    st.session_state.snapshots.append(snap)
    return snap


def list_snapshots() -> List[Dict[str, Any]]:
    return st.session_state.get("snapshots", [])


def get_snapshot(snap_id: str) -> Dict[str, Any]:
    for s in list_snapshots():
        if s["id"] == snap_id:
            return s
    return None


def delete_snapshot(snap_id: str):
    snaps = list_snapshots()
    st.session_state.snapshots = [s for s in snaps if s["id"] != snap_id]


def clear_snapshots():
    st.session_state.snapshots = []


def compare_snapshots(snap_a: Dict[str, Any], snap_b: Dict[str, Any]) -> Dict[str, Any]:
    """Delta between two snapshots. snap_a = older, snap_b = newer."""
    a = snap_a["state"]
    b = snap_b["state"]
    delta = {"changed": [], "unchanged": [], "covenant_changes": [], "exposure_changes": []}

    skip_keys = {"covenant_actuals", "lender_exposure", "as_of_date",
                  "excel_signature", "excel_mtime"}

    for key in a.keys():
        if key in skip_keys: continue
        va = a.get(key); vb = b.get(key)
        if va is None or vb is None: continue
        if isinstance(va, (int, float)):
            if abs(vb - va) > 0.001:
                delta["changed"].append({
                    "metric": key,
                    "before": va, "after": vb,
                    "abs_change": vb - va,
                    "pct_change": ((vb - va) / va * 100) if va != 0 else 0,
                })
            else:
                delta["unchanged"].append(key)

    cov_a = a.get("covenant_actuals", {})
    cov_b = b.get("covenant_actuals", {})
    for k in set(list(cov_a.keys()) + list(cov_b.keys())):
        va = cov_a.get(k); vb = cov_b.get(k)
        if va is None or vb is None: continue
        if abs(vb - va) > 0.001:
            lender, cov = k.split("::", 1)
            delta["covenant_changes"].append({
                "lender": lender, "covenant": cov,
                "before": va, "after": vb, "abs_change": vb - va,
            })

    exp_a = a.get("lender_exposure", {})
    exp_b = b.get("lender_exposure", {})
    for lender in set(list(exp_a.keys()) + list(exp_b.keys())):
        va = exp_a.get(lender, 0); vb = exp_b.get(lender, 0)
        if abs(vb - va) > 0.01:
            delta["exposure_changes"].append({
                "lender": lender, "before": va, "after": vb, "abs_change": vb - va,
            })

    return delta


def export_snapshots_to_json() -> bytes:
    return json.dumps(list_snapshots(), indent=2, default=str).encode("utf-8")


def import_snapshots_from_json(json_bytes: bytes) -> int:
    snaps = json.loads(json_bytes.decode("utf-8"))
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = []
    existing_ids = {s["id"] for s in st.session_state.snapshots}
    count = 0
    for s in snaps:
        if s.get("id") not in existing_ids:
            st.session_state.snapshots.append(s)
            count += 1
    return count
