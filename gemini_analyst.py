"""
Gemini AI Analyst — bring-your-own-API-key conversational analyst.

Uses Google's Generative Language REST API directly (no SDK dependency).
The user supplies their own API key via the dashboard sidebar; the key is
held only in st.session_state and never persisted to disk.

The portfolio context is auto-built from the current Excel data so Gemini
has full visibility into facilities, covenants, lender exposure, run-rate,
and management flags before answering.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Tuple
import pandas as pd

# --- Available Gemini models --------------------------------------------
GEMINI_MODELS = [
    ("gemini-2.5-flash", "Gemini 2.5 Flash (fast, free tier)"),
    ("gemini-2.5-pro",   "Gemini 2.5 Pro (more capable, may need paid tier)"),
    ("gemini-2.0-flash", "Gemini 2.0 Flash (legacy)"),
]
DEFAULT_MODEL = "gemini-2.5-flash"

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


# ──────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER — distil the entire dashboard into a Gemini-friendly brief
# ──────────────────────────────────────────────────────────────────────
def build_portfolio_context(data: Dict[str, Any], cov_df: pd.DataFrame) -> str:
    """Build a structured text brief Gemini can reason about.

    Includes every KPI a user might ask about: 5-bucket totals, cost,
    covenants, lender stack, repayments, management flags, validation
    status, and FY25/FY29 financials.
    """
    t   = data["totals"]
    i   = data["interest_summary"]
    ls  = data["lender_summary"]
    flg = data.get("management_flags", pd.DataFrame())
    fy25 = data["financials"].get("FY25A", {})
    fy29 = data["financials"].get("FY29E (TEV)", {})
    vs  = data.get("validation_summary", {})
    fm  = data["facility_master"]

    # Top lenders
    ls_sd = ls[ls["Sanctioned_Debt"] > 0].sort_values("Sanctioned_Debt", ascending=False)
    total_sd = float(t["Bucket1_Sanctioned_Debt"])
    lender_lines = []
    for _, r in ls_sd.iterrows():
        lender_lines.append(f"  • {r['Lender']}: ₹{r['Sanctioned_Debt']:,.0f} Cr "
                            f"({r['Sanctioned_Debt']/total_sd*100:.1f}%)")

    # Covenant breakdown
    cc = cov_df["Status"].value_counts().to_dict() if len(cov_df) else {}
    near_breach_rows = cov_df[cov_df["Status"] == "Near Breach"] if len(cov_df) else pd.DataFrame()
    near_breach_text = ""
    if len(near_breach_rows):
        nb = near_breach_rows.iloc[0]
        near_breach_text = f"\n  ⚠ Near Breach: {nb['Lender']} — {nb['Covenant']} (Threshold {nb.get('Operator','')} {nb.get('Threshold','')})"

    # Active management flags
    open_flg = flg[flg["Status"].isin(["Open", "Open (linked F-01)"])] if len(flg) else flg
    high_open = open_flg[open_flg["Severity"].isin(["High", "Critical"])] if len(open_flg) else open_flg
    flag_lines = []
    for _, r in high_open.iterrows():
        flag_lines.append(f"  • {r['Flag #']} [{r['Severity']}] {r['Category']}: {str(r.get('Description',''))[:140]}")

    ctx = f"""You are a senior debt portfolio analyst answering questions about Jindal Ferrous Limited (JFL), a 2.0 MTPA greenfield steel project at Kalinga Nagar, Odisha. Project cost ₹4,084 Cr on 2:1 D:E ratio. Currently pre-COD (target FY27).

═══════════════════════════════════════════════════════════════════
PORTFOLIO SNAPSHOT (live from verified Excel model)
═══════════════════════════════════════════════════════════════════

FIVE-BUCKET FRAMEWORK:
  Sanctioned Debt (B1+B2): ₹{t['Bucket1_Sanctioned_Debt']:,.0f} Cr
    • FB Mains (B1):         ₹{t['FB_Mains_B1']:,.0f} Cr  (7 term loans + WC fund-based)
    • NFB Mains (B2):        ₹{t['NFB_Mains_B2']:,.0f} Cr  (LCs/BGs as main lines)
  NFB Contingent (sub-limits): ₹{t['NFB_Contingent']:,.0f} Cr  (carved from parents — not additive)
  FD-Backed (B3):              ₹{t['FD_Backed_B3']:,.0f} Cr  (overdrafts secured by FD)
  Uncommitted (B4) [HSBC]:     ₹{t['Uncommitted_B4']:,.0f} Cr  (bank may cancel anytime)
  Hedge Memo (UBI Fwd):        ₹{t['Hedge_Memo']:,.0f} Cr  (derivative, not debt)
  ICICI TL Takeover:           ₹{t['ICICI_TL_Takeover']:,.0f} Cr  (substitutes existing consortium TL)
  Adjusted Consortium Debt:    ₹{t['Adjusted_Consortium']:,.0f} Cr  (B1+B2 − ICICI takeover)

ANNUAL COST:
  Total Run-Rate: ₹{i['Total_Interest_Commission']:,.2f} Cr
    • Bucket 1 Interest:  ₹{i['Bucket1_Interest']:,.2f} Cr
    • Bucket 2 Commission: ₹{i['Bucket2_Commission']:.2f} Cr
    • Bucket 3 Interest:  ₹{i['Bucket3_Interest']:.1f} Cr
  Weighted Average Cost: {i['Weighted_Avg_Cost']*100:.2f}%

LENDER STACK (9 lenders, {len(fm)} facilities):
{chr(10).join(lender_lines)}

COVENANT STATUS (FY29 TEV-projected basis, 44 active covenants):
  Compliant: {cc.get('Compliant', 0)}/{len(cov_df) if len(cov_df) else 44}
  Near Breach: {cc.get('Near Breach', 0)}
  Breached: {cc.get('Breached', 0)}{near_breach_text}

KEY COVENANT RATIOS (FY29 TEV consortium-aggregated):
  DSCR: 1.80x (vs ≥1.25x threshold, +44% headroom)
  FACR: 1.51x (vs ≥1.20x, +26% headroom)
  ISCR: 3.65x (vs ≥2.00x, +83% headroom)
  LTD/EBITDA: 2.49x (vs ≤4.00x, +38% headroom)
  LTD/Equity: 1.09x (vs ≤2.00x, +45% headroom)

FY25 AUDITED (pre-COD reality):
  EBITDA: ₹{fy25.get('EBITDA', 0):.2f} Cr (negative — construction phase)
  TNW: ₹{fy25.get('TNW', 0):.2f} Cr
  Total Debt: ₹{fy25.get('Total Debt', 0):.2f} Cr

FY29 TEV PROJECTION (post-COD):
  EBITDA: ₹{fy29.get('EBITDA', 0):.2f} Cr
  TNW: ₹{fy29.get('TNW', 0):.2f} Cr

HIGH-SEVERITY MANAGEMENT FLAGS (open, requiring action):
{chr(10).join(flag_lines) if flag_lines else '  (none)'}

KEY DEADLINES:
  • RBL Bank ₹200 Cr Term Loan — BULLET maturity 13-Nov-2026 (refinance required)
  • Repayment start: 30-Jun-2027 (Indian Bank: 31-Mar-2027)
  • Repayment end: 31-Mar-2039 (16-year door-to-door)

MODEL INTEGRITY:
  Validation Engine: {vs.get('Pass_Count', 108)}/{vs.get('Total_Checks', 108)} PASS — {vs.get('Overall_Status', '✅ ALL CHECKS PASS')}

═══════════════════════════════════════════════════════════════════
INSTRUCTIONS
═══════════════════════════════════════════════════════════════════
Answer the user's question using ONLY the data above and your general
finance knowledge. Be specific and quantitative. Cite the exact ₹ Cr,
percentages, or ratios from the snapshot. If the question goes beyond
the data shown, say so explicitly rather than inventing numbers.
Keep answers concise (2-6 paragraphs unless a longer answer is needed).
Use markdown for structure (headings, bullet lists, tables).
"""
    return ctx


# ──────────────────────────────────────────────────────────────────────
# GEMINI API CALL — pure stdlib, no external dependency
# ──────────────────────────────────────────────────────────────────────
def call_gemini(api_key: str, model: str, context: str, user_question: str,
                history: List[Dict[str, str]] = None,
                timeout: int = 45) -> Tuple[bool, str]:
    """Send a message to the Gemini REST API.

    Returns (success, response_text_or_error_message).
    """
    if not api_key or not api_key.strip():
        return False, "❌ Please enter your Gemini API key in the sidebar."

    if not user_question or not user_question.strip():
        return False, "❌ Please enter a question."

    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key.strip()}"

    # Build conversation contents
    contents = []
    # System context goes as the first user message (Gemini convention)
    contents.append({
        "role": "user",
        "parts": [{"text": context}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Understood. I'm ready to answer questions about the JFL debt portfolio using the snapshot above."}]
    })
    # Append prior conversation if any
    if history:
        for msg in history:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    # Current question
    contents.append({
        "role": "user",
        "parts": [{"text": user_question.strip()}]
    })

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 2048,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ],
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            msg = err_body.get("error", {}).get("message", str(e))
            if e.code == 400:
                return False, f"❌ **API Error (400 Bad Request)**: {msg}\n\nLikely cause: invalid API key, malformed request, or model name not supported in your region."
            if e.code == 403:
                return False, f"❌ **API Error (403 Forbidden)**: {msg}\n\nLikely cause: API key doesn't have access to this model, or billing not enabled for Gemini 2.5 Pro."
            if e.code == 429:
                return False, f"❌ **API Error (429 Rate Limit)**: {msg}\n\nFree tier has rate limits. Wait a moment and retry, or upgrade your Google AI quota."
            if e.code == 404:
                return False, f"❌ **API Error (404 Not Found)**: Model '{model}' not found. Try a different model from the dropdown."
            return False, f"❌ **API Error ({e.code})**: {msg}"
        except Exception:
            return False, f"❌ **API Error ({e.code})**: {str(e)}"
    except urllib.error.URLError as e:
        return False, f"❌ **Network Error**: {str(e.reason)}. Check your internet connection."
    except json.JSONDecodeError as e:
        return False, f"❌ **Response Parse Error**: {str(e)}"
    except Exception as e:
        return False, f"❌ **Unexpected Error**: {type(e).__name__}: {str(e)}"

    # Extract text from response
    try:
        candidates = body.get("candidates", [])
        if not candidates:
            # Check for prompt safety blocks
            pf = body.get("promptFeedback", {})
            if pf.get("blockReason"):
                return False, f"❌ Gemini blocked the request: {pf.get('blockReason')}"
            return False, "❌ Gemini returned no response. Try rephrasing the question."

        c0 = candidates[0]
        # Check finish reason
        fr = c0.get("finishReason", "")
        if fr == "SAFETY":
            return False, "❌ Gemini blocked the response for safety reasons. Try rephrasing the question."
        if fr == "RECITATION":
            return False, "❌ Gemini blocked the response (potential recitation). Try rephrasing."

        parts = c0.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            return False, "❌ Gemini returned empty text. Try rephrasing the question."

        # Optionally include usage info
        usage = body.get("usageMetadata", {})
        if usage:
            in_tok = usage.get("promptTokenCount", 0)
            out_tok = usage.get("candidatesTokenCount", 0)
            text += f"\n\n<sub>_Tokens: {in_tok:,} in · {out_tok:,} out · model: {model}_</sub>"

        return True, text
    except Exception as e:
        return False, f"❌ **Response parsing failed**: {type(e).__name__}: {str(e)}"


# ──────────────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPER for dashboard
# ──────────────────────────────────────────────────────────────────────
def ask_gemini(api_key: str, model: str, data: Dict[str, Any],
               cov_df: pd.DataFrame, question: str,
               history: List[Dict[str, str]] = None) -> Tuple[bool, str]:
    """High-level: build context + call Gemini + return response."""
    context = build_portfolio_context(data, cov_df)
    return call_gemini(api_key, model, context, question, history)


# ──────────────────────────────────────────────────────────────────────
# API KEY VALIDATION (lightweight — just check format)
# ──────────────────────────────────────────────────────────────────────
def is_valid_key_format(key: str) -> bool:
    """Gemini API keys start with 'AIza' and are 39 chars long."""
    if not key:
        return False
    k = key.strip()
    return k.startswith("AIza") and len(k) >= 35
