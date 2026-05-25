"""
PDF board memo generator, produces a polished 2-3 page PDF summary of the
JFL debt portfolio. Mirrors JCL's pdf_export.py structure.
"""

from __future__ import annotations
import io
from datetime import datetime
from typing import Dict, Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                  TableStyle, PageBreak, KeepTogether)


# ─── Palette ─────────────────────────────────────────────────────────────
NAVY = colors.HexColor("#0F1A30")
BLUE = colors.HexColor("#3B82F6")
SLATE = colors.HexColor("#94A3B8")
LIGHT = colors.HexColor("#F1F5F9")
GREEN = colors.HexColor("#10B981")
AMBER = colors.HexColor("#F59E0B")
RED   = colors.HexColor("#EF4444")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="JFL_Title", fontName="Helvetica-Bold",
                           fontSize=18, textColor=NAVY, spaceAfter=4))
    ss.add(ParagraphStyle(name="JFL_Subtitle", fontName="Helvetica",
                           fontSize=10, textColor=SLATE, spaceAfter=12))
    ss.add(ParagraphStyle(name="JFL_H2", fontName="Helvetica-Bold",
                           fontSize=12, textColor=BLUE, spaceBefore=10, spaceAfter=6))
    ss.add(ParagraphStyle(name="JFL_Body", fontName="Helvetica", fontSize=9,
                           textColor=colors.black, leading=12, spaceAfter=4))
    ss.add(ParagraphStyle(name="JFL_Verdict", fontName="Helvetica-Bold",
                           fontSize=11, textColor=colors.white, spaceAfter=6))
    ss.add(ParagraphStyle(name="JFL_Footer", fontName="Helvetica",
                           fontSize=7, textColor=SLATE))
    return ss


def _kpi_table(t, isum):
    data = [
        ["Sanctioned Debt (B1+B2)", f"Rs. {t['Bucket1_Sanctioned_Debt']:,.0f} Cr"],
        ["FB Mains (Bucket 1)",     f"Rs. {t['FB_Mains_B1']:,.0f} Cr"],
        ["NFB Mains (Bucket 2)",    f"Rs. {t['NFB_Mains_B2']:,.0f} Cr"],
        ["NFB Contingent",          f"Rs. {t['NFB_Contingent']:,.0f} Cr"],
        ["FD-Backed (Bucket 3)",    f"Rs. {t['FD_Backed_B3']:,.0f} Cr"],
        ["Uncommitted (Bucket 4)",  f"Rs. {t['Uncommitted_B4']:,.0f} Cr"],
        ["Hedge Memo",              f"Rs. {t['Hedge_Memo']:,.0f} Cr"],
        ["ICICI TL Takeover",       f"(Rs. {t['ICICI_TL_Takeover']:,.0f} Cr)"],
        ["Adjusted Consortium Debt",f"Rs. {t['Adjusted_Consortium']:,.0f} Cr"],
        ["Annual Run-Rate",         f"Rs. {isum['Total_Interest_Commission']:,.1f} Cr"],
        ["WAC of FB Economic Debt", f"{isum['Weighted_Avg_Cost']*100:.2f}%"],
    ]
    tbl = Table(data, colWidths=[8*cm, 5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, SLATE),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 8), (-1, 8), colors.HexColor("#FEF3C7")),  # Adjusted Consortium row
        ("FONTNAME", (0, 8), (-1, 8), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),  # Sanctioned Debt row
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _lender_table(ls):
    """Per-lender Sanctioned Debt table."""
    data = [["Lender", "Sanctioned (Rs.  Cr)", "% Share", "Facility Count", "NFB Contingent"]]
    nz = ls[ls["Sanctioned_Debt"] > 0].sort_values("Sanctioned_Debt", ascending=False)
    total = nz["Sanctioned_Debt"].sum()
    for _, r in nz.iterrows():
        pct = r["Sanctioned_Debt"] / total * 100 if total else 0
        data.append([
            r["Lender"], f"{r['Sanctioned_Debt']:,.0f}", f"{pct:.1f}%",
            str(r["Facility_Count_B1B2"]), f"{r['NFB_Contingent']:,.0f}",
        ])
    data.append(["TOTAL", f"{total:,.0f}", "100.0%",
                  str(nz["Facility_Count_B1B2"].sum()), f"{nz['NFB_Contingent'].sum():,.0f}"])

    tbl = Table(data, colWidths=[4.5*cm, 3*cm, 2*cm, 2.5*cm, 3*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
        ("GRID", (0, 0), (-1, -1), 0.25, SLATE),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _covenant_table(cov_df):
    """Top 10 tightest covenants table."""
    cv = cov_df.copy()
    cv["hr"] = pd.to_numeric(cv.get("Headroom_Pct"), errors="coerce")
    cv = cv.dropna(subset=["hr"]).sort_values("hr").head(10)

    data = [["Lender", "Covenant", "Threshold", "Actual", "Headroom", "Status"]]
    for _, r in cv.iterrows():
        actual_str = (f"{r['Actual']:.2f}x" if isinstance(r['Actual'], (int, float))
                      else str(r['Actual'])[:15])
        thr_str = (f"{r['Operator']}{r['Threshold']:.2f}"
                   if isinstance(r['Threshold'], (int, float))
                   else f"{r['Operator']}{r['Threshold']}")
        data.append([r["Lender"], r["Covenant"][:35], thr_str, actual_str,
                      f"{r['hr']:+.1f}%", r["Status"]])

    tbl = Table(data, colWidths=[2.8*cm, 5*cm, 2*cm, 2*cm, 2*cm, 2.2*cm])

    status_colors_map = {
        "Compliant": colors.HexColor("#D1FAE5"),
        "Watch": colors.HexColor("#DBEAFE"),
        "Near Breach": colors.HexColor("#FEF3C7"),
        "Breached": colors.HexColor("#FEE2E2"),
        "Pending Input": colors.HexColor("#F1F5F9"),
    }
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, SLATE),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, (_, r) in enumerate(cv.iterrows(), 1):
        bg = status_colors_map.get(r["Status"], colors.white)
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
    tbl.setStyle(TableStyle(style))
    return tbl


def generate_board_memo(data: Dict[str, Any], cov_df: pd.DataFrame,
                         controls: Dict[str, Any]) -> bytes:
    """Generate a polished 2-3 page PDF board memo. Returns bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=1.5*cm, rightMargin=1.5*cm,
                             topMargin=1.5*cm, bottomMargin=1.5*cm,
                             title="JFL Debt Monitor, Board Memo",
                             author="JFL Treasury Modelling")
    ss = _styles()
    story = []

    # ─── Cover header ────────────────────────────────────────────────
    story.append(Paragraph("JINDAL FERROUS LIMITED, Debt Monitor Board Memo",
                             ss["JFL_Title"]))
    sub = (f"As of {pd.Timestamp(data['as_of_date']).strftime('%d-%b-%Y')}  ·  "
           f"Basis: {controls.get('basis', 'FY29E (TEV)')}  ·  "
           f"Lenders: 9  ·  Facilities: 44  ·  "
           f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M IST')}")
    story.append(Paragraph(sub, ss["JFL_Subtitle"]))

    # ─── Verdict box ────────────────────────────────────────────────
    compliant = (cov_df["Status"] == "Compliant").sum()
    breached = (cov_df["Status"] == "Breached").sum()
    near = (cov_df["Status"].isin(["Near Breach", "Watch"])).sum()

    if breached > 5:
        verdict_text = "ACTION REQUIRED"
        verdict_bg = RED
    elif breached > 0 or near > 0:
        verdict_text = "MONITOR CLOSELY"
        verdict_bg = AMBER
    else:
        verdict_text = "HEALTHY"
        verdict_bg = GREEN

    verdict_table = Table([[Paragraph(f"● {verdict_text}", ss["JFL_Verdict"]),
                             Paragraph(
                                 f"<font color='white'>"
                                 f"Sanctioned Debt Rs. {data['totals']['Bucket1_Sanctioned_Debt']:,.0f} Cr | "
                                 f"Adjusted Consortium Rs. {data['totals']['Adjusted_Consortium']:,.0f} Cr | "
                                 f"WAC {data['interest_summary']['Weighted_Avg_Cost']*100:.2f}% | "
                                 f"Compliant {compliant}/{len(cov_df)}"
                                 f"</font>",
                                 ParagraphStyle(name="x", fontSize=9, textColor=colors.white,
                                                fontName="Helvetica"))]],
                            colWidths=[5*cm, 12.5*cm])
    verdict_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verdict_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 10))

    # ─── Section A: KPIs ────────────────────────────────────────────
    story.append(Paragraph("A. Headline KPIs", ss["JFL_H2"]))
    story.append(_kpi_table(data["totals"], data["interest_summary"]))
    story.append(Spacer(1, 10))

    # ─── Section B: Lender concentration ────────────────────────────
    story.append(Paragraph("B. Lender Concentration", ss["JFL_H2"]))
    story.append(_lender_table(data["lender_summary"]))
    story.append(Spacer(1, 10))

    # ─── Section C: Covenants ───────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph(f"C. Covenants - Top 10 Tightest "
                             f"({compliant}/{len(cov_df)} compliant, "
                             f"{breached} breached, {near} watch/near)",
                             ss["JFL_H2"]))
    story.append(_covenant_table(cov_df))
    story.append(Spacer(1, 10))

    # ─── Section D: Closing notes ───────────────────────────────────
    story.append(Paragraph("D. Key Observations", ss["JFL_H2"]))
    notes = [
        f"<b>1. Pre-COD context.</b> JFL is a 2.0 MTPA greenfield steel project; "
        f"DCCO 01-Apr-2026. Most consortium covenants first test from FY29 onwards (post-COD). "
        f"The FY29 TEV-projected basis shows 43/44 compliant with 1 near breach "
        f"(ICICI WC Rating).",
        f"<b>2. ICICI TL takeover.</b> ICICI Rs. 840 Cr substitutes for existing consortium TL "
        f"rather than adding new debt. Adjusted Consortium Debt = Rs. {data['totals']['Adjusted_Consortium']:,.0f} Cr "
        f"is the economic representation.",
        f"<b>3. Bridge facility.</b> RBL Rs. 200 Cr is a 12-month bullet maturing 13-Nov-2026. "
        f"Refinance plan required.",
        f"<b>4. HSBC reclassification.</b> HSBC Rs. 1,000 Cr Combined Limit (uncommitted per sanction letter) "
        f"is haircut by 80% and Rs. 200 Cr is carried in Bucket 1 (Sanctioned / FB Mains) as the "
        f"realistic effective committed amount. Bank retains right to withdraw.",
    ]
    for n in notes:
        story.append(Paragraph(n, ss["JFL_Body"]))
        story.append(Spacer(1, 4))

    # ─── Footer ─────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Source: JFL_Debt_Model_Final.xlsx | "
        "Classification: Confidential - Treasury / Senior Management.",
        ss["JFL_Footer"]))

    doc.build(story)
    return buf.getvalue()
