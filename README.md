# JFL Debt Monitor

Streamlit dashboard for monitoring the debt portfolio of Jindal Ferrous Limited (JFL),
a 2.0 MTPA greenfield steel project at Kalinga Nagar, Odisha.

## What it covers

- 44 facilities across 9 lenders: UBI, Indian Bank, RBL, YES Bank, IDFC First,
  ICICI (WC), ICICI (TL), HDFC, HSBC.
- Five-bucket framework:
  - B1 (FB Mains): INR 4,116 Cr
  - B2 (NFB Mains): INR 550 Cr
  - B3 (FD-Backed): INR 150 Cr
  - B4 (Uncommitted): nil after HSBC reclassification
  - Hedge memo (UBI Forward): INR 75 Cr
- Sanctioned Debt (B1+B2): INR 4,666 Cr.
- Adjusted Consortium Debt: INR 3,826 Cr after netting out ICICI TL takeover of INR 840 Cr.
- Covenant basis: FY29 TEV (post-COD projected), 43 of 44 compliant, 1 near breach
  (ICICI WC Rating at threshold). First formal covenant test from FY29.
- Stress testing: rate, spread, utilisation, EBITDA, debt shocks.
- AI Analyst with two modes:
  - Quick Answers: a set of pre-built JFL portfolio queries
  - Gemini AI: bring your own API key for free-form analysis
- PDF board memo and CSV exports.
- Historical snapshots.

## Files

```
.
├── main.py                    # Streamlit entry point
├── data_loader.py             # Reads JFL_Debt_Model_Final.xlsx
├── dashboard_ui.py            # Tab UIs
├── scenario_engine.py         # Covenant + interest recompute under stress
├── visualizations.py          # Plotly chart helpers
├── rule_based_ai.py           # Quick Answers backend
├── gemini_analyst.py          # Gemini API integration
├── snapshots.py               # Historical state capture
├── pdf_export.py              # Board memo PDF
├── market_rates.py            # Live market-rate sidebar
├── theme.py                   # Theme/CSS
├── requirements.txt
├── .streamlit/config.toml
├── JFL_Debt_Model_Final.xlsx
└── README.md
```

## Quick start

```bash
pip install -r requirements.txt
streamlit run main.py
```

## Streamlit Cloud deployment

1. Push this folder to GitHub.
2. Connect the repo to https://share.streamlit.io
3. Set main file to `main.py`.

## Updating data

Either upload an updated `JFL_Debt_Model_Final.xlsx` from the sidebar, or replace
the file in the project root and click "Reload from Excel". The Excel is the
working file; the dashboard does not carry hard-coded numbers.

## Notes

- Dual-basis design: FY25A is the audited pre-COD baseline; FY29E (TEV) is the
  post-COD projection (DCCO 01-Apr-2026). The sidebar toggles which basis the
  covenant tab uses.
- Rating covenants use ordinal logic (BBB=10, A-=14, etc.) so the
  rating-vs-threshold comparison is well-defined.
- When no stress is applied, the dashboard uses the Excel's Actual + Status
  values directly rather than re-deriving them. Stress recompute respects
  market-data covenants (FMV/Pledge) which cannot be re-derived from borrower
  financials.
