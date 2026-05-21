# JFL Debt Monitoring Dashboard

A Streamlit dashboard for monitoring the debt portfolio of **Jindal Ferrous
Limited** (JFL) — a 2.0 MTPA greenfield steel project at Kalinga Nagar,
Odisha. Built on the JCL reference architecture, adapted for JFL's
9-lender / 5-bucket / 7-TL / dual-basis covenant structure.

## What it does

- Tracks 44 facilities across 9 lenders (UBI, Indian Bank, RBL, YES Bank,
  IDFC First, ICICI (WC), ICICI (TL), HDFC, HSBC).
- Five-bucket framework: B1 (FB Mains ₹3,916 Cr) · B2 (NFB Mains ₹550 Cr) ·
  B3 (FD-Backed ₹150 Cr) · B4 (Uncommitted ₹1,000 Cr) · Hedge memo ₹75 Cr.
- ICICI TL takeover (₹840 Cr) → Adjusted Consortium Debt ₹3,626 Cr.
- Dual covenant basis: **FY25 Audit** (pre-COD reality, 13/44 compliant) and
  **FY29E TEV** (post-COD projection, 43/44 compliant).
- Interactive stress testing: rate, spread, utilisation, EBITDA, debt shocks.
- 15 Management Flags register + 87-check Validation Engine status.
- AI Analyst (rule-based, deterministic Q&A) covering 15 JFL-specific topics.
- PDF Board Memo, CSV exports, historical snapshot tracking.

## File layout

```
JFL_Debt_Dashboard/
├── main.py                    # Streamlit entry point — 5 tabs
├── data_loader.py             # Reads JFL_Debt_Model_Final.xlsx
├── dashboard_ui.py            # All tab UIs
├── scenario_engine.py         # Covenant + interest recompute under stress
├── visualizations.py          # Plotly chart helpers
├── rule_based_ai.py           # Deterministic Q&A
├── snapshots.py               # Historical state capture
├── pdf_export.py              # Board memo PDF generator
├── market_rates.py            # Live market-rate sidebar
├── theme.py                   # Dark theme CSS + lender colours
├── verify_all.py              # V&V test suite
├── requirements.txt
├── .streamlit/config.toml     # Dark theme settings
├── JFL_Debt_Model_Final.xlsx  # Single source of truth (v11)
└── README.md
```

## Quick start

```bash
pip install -r requirements.txt
streamlit run main.py
```

## Streamlit Cloud deployment

1. Push this folder to a GitHub repository.
2. Connect the repo to https://share.streamlit.io
3. Set the main file to `main.py`.
4. Done — the bundled Excel is loaded automatically on boot.

## Updating data

Two ways to refresh the underlying numbers:

1. **In-app upload**: open the sidebar → upload an updated
   `JFL_Debt_Model_Final.xlsx`. The dashboard re-reads it instantly.
2. **Direct replacement**: replace the Excel file at the project root and
   click **Reload from Excel** in the sidebar.

The Excel is the single source of truth; the dashboard never carries
hard-coded numbers.

## Tabs at a glance

| Tab | Contents |
|---|---|
| **📊 Overview** | Hero verdict, 12 KPI cards (5 bucket + 4 health + 3 concentration), lender concentration donut, 5-bucket pie, per-lender stacked composition, facility cost contribution, FB rate vs WAC. |
| **🛡️ Covenants** | Status pie, binding-covenant headroom chart, TEV-projected forward trajectory (FY27→FY38), attention items, full per-lender table. Toggle FY25 Audit ↔ FY29 TEV basis from sidebar. |
| **📅 Schedule** | Sub-nav: (a) Repayment Profile — TL maturity panel, annual debt-service stacked bar, cumulative run-down, quarterly schedule, facility browser. (b) Renewals — interactive filters, urgency bucket KPIs, gantt timeline, action items. (c) Mgmt Flags & Validation — 15 flag cards, 87-check status register. |
| **🤖 AI Analyst** | 4 proactive insight cards + 15 suggested questions + free-form chat + conversation history. |
| **🔧 Tools** | Sub-nav: (a) Export — PDF board memo + 6 CSV downloads + reconciliation summary. (b) Snapshots — capture state, compare across time, JSON backup/restore. |

## Validation

The Excel ships with an **87-check Validation Engine**. The dashboard
reads its status directly from the workbook and surfaces it in the header
badge. Independent V&V can be run from the command line:

```bash
python verify_all.py
```

This re-runs the full reconciliation suite (data loading, covenant logic,
interest re-computation, PDF generation, snapshot round-trip, AI router).

## Architectural notes

- **Excel-stored covenant values are sacred**: when no stress is applied,
  the dashboard uses the Excel's audited Actual + Status values directly,
  rather than re-deriving them. This preserves auditability.
- **Stress recompute respects market-data covenants**: JSL FMV / Pledge
  covenants cannot be re-derived from borrower financials, so they
  inherit their stored values even under stress.
- **Rating covenants** use ordinal logic (BBB=10, A-=14, etc.) so the
  rating-vs-threshold comparison is well-defined.
- **Dual-basis design**: FY25A is the audited pre-COD reality; FY29E TEV
  is the post-COD projection (DCCO 01-Apr-2026). The sidebar toggles which
  basis the covenant tab uses. JCL didn't need this dual view because it
  is operational; JFL is pre-operational.
