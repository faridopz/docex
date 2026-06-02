"""
Build the DOCex product brief PDF.

Produces docs/DOCex-Product-Brief.pdf — a prospect-ready one-pager
(actually 6 pages) that Farid can attach to outbound emails. The PDF
covers: problem, what DOCex is, the three Co-Pilots, the audit-trail
moat, pricing, pilot path, and contact.

No external dependencies beyond reportlab (already in requirements).

Usage:
    python docs/build_product_pdf.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "DOCex-Product-Brief.pdf"

# Brand palette — mirrors UI_DIRECTION.md
BRAND = colors.HexColor("#2563eb")
INK = colors.HexColor("#111827")
SUBTLE = colors.HexColor("#6b7280")
WARM = colors.HexColor("#fafaf7")
AMBER = colors.HexColor("#f97316")
VIOLET = colors.HexColor("#7c3aed")
EMERALD = colors.HexColor("#10b981")
ROSE = colors.HexColor("#ef4444")
LINE = colors.HexColor("#e5e7eb")


# ─── Styles ─────────────────────────────────────────────────────────────

def styles():
    """Build a stylesheet derived from reportlab defaults."""
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle(
        "title",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=34,
        leading=38,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=14,
        leading=20,
        textColor=SUBTLE,
        spaceAfter=18,
    )
    s["h1"] = ParagraphStyle(
        "h1",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=INK,
        spaceBefore=18,
        spaceAfter=8,
    )
    s["h2"] = ParagraphStyle(
        "h2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=INK,
        spaceBefore=14,
        spaceAfter=4,
    )
    s["body"] = ParagraphStyle(
        "body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=INK,
        spaceAfter=8,
        alignment=TA_LEFT,
    )
    s["bullet"] = ParagraphStyle(
        "bullet",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        textColor=INK,
        leftIndent=14,
        bulletIndent=2,
        spaceAfter=4,
    )
    s["small"] = ParagraphStyle(
        "small",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=SUBTLE,
    )
    s["eyebrow"] = ParagraphStyle(
        "eyebrow",
        parent=base["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=BRAND,
        spaceAfter=4,
    )
    s["pillar"] = ParagraphStyle(
        "pillar",
        parent=base["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=INK,
        spaceAfter=4,
    )
    s["quote"] = ParagraphStyle(
        "quote",
        parent=base["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=11,
        leading=16,
        textColor=SUBTLE,
        leftIndent=12,
        rightIndent=12,
    )
    s["center"] = ParagraphStyle(
        "center",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=INK,
        alignment=TA_CENTER,
    )
    return s


# ─── Reusable visual blocks ────────────────────────────────────────────

def stat_row(stats):
    """A row of (label, value) stat boxes spanning the page width."""
    data = [
        [Paragraph(v, ParagraphStyle("statv", fontName="Helvetica-Bold",
                                     fontSize=22, leading=26, textColor=BRAND)),
         Paragraph(k, ParagraphStyle("statl", fontName="Helvetica",
                                     fontSize=9, leading=12, textColor=SUBTLE))]
        for k, v in stats
    ]
    # Two-row table — values on top, labels below
    top = [[d[0] for d in data]]
    bot = [[d[1] for d in data]]
    rows = top + bot
    col_w = 16 * cm / len(stats)
    t = Table(rows, colWidths=[col_w] * len(stats))
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def copilot_card(eyebrow, title, body, proof, accent=BRAND):
    """A coloured-accent card for one Co-Pilot."""
    inner = [
        Paragraph(eyebrow.upper(), ParagraphStyle(
            "cp-eye", fontName="Helvetica-Bold", fontSize=8, leading=11,
            textColor=accent, spaceAfter=2)),
        Paragraph(title, ParagraphStyle(
            "cp-t", fontName="Helvetica-Bold", fontSize=14, leading=18,
            textColor=INK, spaceAfter=4)),
        Paragraph(body, ParagraphStyle(
            "cp-b", fontName="Helvetica", fontSize=10, leading=14,
            textColor=INK, spaceAfter=6)),
        Paragraph(f"<b>{proof}</b>", ParagraphStyle(
            "cp-p", fontName="Helvetica-Bold", fontSize=9, leading=12,
            textColor=accent)),
    ]
    t = Table([[inner]], colWidths=[16 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WARM),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t


def included_table():
    """A 'what every account gets' table — no pricing, just capabilities."""
    rows = [
        ["DOCex Assistant brief on every result", "✓"],
        ["Append-only decision log + signatures", "✓"],
        ["Frozen rulebook snapshot per check", "✓"],
        ["Excel and PDF export of any result", "✓"],
        ["Citations on every claim, policy and document side", "✓"],
        ["Knowledge Hub library + library-wide chat", "✓"],
        ["Bank account verification (recipient match)", "✓"],
        ["All three Co-Pilots: Sub-award · Programs · Compliance", "✓"],
        ["Sample-data preview before bringing your own files", "✓"],
        ["Audit-ready archive — every check has a stable URL", "✓"],
    ]
    t = Table(rows, colWidths=[13.5 * cm, 2.5 * cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (1, 0), (1, -1), EMERALD),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, WARM]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
    ]))
    return t


def footer_canvas(canvas_obj, doc):
    """Draw a thin footer on every page."""
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(SUBTLE)
    canvas_obj.drawString(2 * cm, 1.2 * cm, "DOCex · The AI back-office for document-heavy operations")
    canvas_obj.drawRightString(
        A4[0] - 2 * cm, 1.2 * cm,
        f"Page {doc.page} · contact: faridmichika@gmail.com"
    )
    canvas_obj.setStrokeColor(LINE)
    canvas_obj.line(2 * cm, 1.7 * cm, A4[0] - 2 * cm, 1.7 * cm)
    canvas_obj.restoreState()


# ─── Page assembly ──────────────────────────────────────────────────────

def build():
    s = styles()

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.2 * cm,
        title="DOCex — Product Brief",
        author="Farid Abdurrahman",
        subject="DOCex product brief for prospects",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="normal",
    )
    doc.addPageTemplates(PageTemplate(id="main", frames=frame, onPage=footer_canvas))

    story = []

    # ── Cover ──
    story.append(Paragraph("DOCex", ParagraphStyle(
        "wm", fontName="Helvetica-Bold", fontSize=12,
        textColor=BRAND, spaceAfter=18)))
    story.append(Paragraph(
        "The AI back-office for<br/>document-heavy operations.",
        s["title"]))
    story.append(Paragraph(
        "Verify payments. Check compliance. Read every document. "
        "In minutes, with citations.",
        s["subtitle"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(stat_row([
        ("Co-Pilots", "3"),
        ("Primitives", "5"),
        ("Audit trail", "Frozen"),
        ("Time to first value", "< 5 min"),
    ]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "<b>Built for finance, programs, sub-award, and compliance "
        "teams</b> who spend their weeks reading PDFs, cross-checking "
        "spreadsheets, and verifying bank accounts by hand. DOCex does "
        "the document-heavy parts of the job in the time it takes to "
        "make coffee — and leaves an audit trail your auditor can't "
        "argue with.",
        s["body"]))

    # ── The problem ──
    story.append(PageBreak())
    story.append(Paragraph("THE PROBLEM", s["eyebrow"]))
    story.append(Paragraph("Document-heavy operations cost real time.", s["h1"]))
    story.append(Paragraph(
        "A typical sub-award team receives 200+ partner applications per "
        "cycle. Each applicant submits 5–8 documents — registration "
        "certificate, financials, proposal, organisational profile, audit "
        "report. The team needs concrete answers across all of them:",
        s["body"]))
    for b in [
        "Is this org registered with the right authority?",
        "Have they managed donor funds before?",
        "Do they have an anti-fraud policy?",
        "What states or regions do they operate in?",
        "Has their audit been signed in the last 24 months?",
    ]:
        story.append(Paragraph(f"• {b}", s["bullet"]))

    story.append(Paragraph(
        "Today, someone reads every document. By hand. The whole cycle "
        "takes <b>two weeks</b>. Compliance teams hit the same wall on the "
        "way out: every payment voucher gets checked rule by rule against "
        "a policy nobody has time to read end-to-end, and finance teams "
        "verify recipient bank accounts by thumb-typing them into a phone "
        "app and hoping.",
        s["body"]))

    story.append(Paragraph("WHY EXISTING TOOLS DON'T SOLVE IT", s["eyebrow"]))
    story.append(Paragraph(
        "<b>Generic AI chatbots</b> don't know your policy or your "
        "workflow. <b>Grant-management platforms</b> charge $30k/year for "
        "form-builders and never learned to read documents. <b>OCR tools</b> "
        "extract text but leave the actual work — turning that text into a "
        "verdict — to a human.",
        s["body"]))

    # ── What DOCex is ──
    story.append(PageBreak())
    story.append(Paragraph("WHAT DOCEX IS", s["eyebrow"]))
    story.append(Paragraph(
        "Three Co-Pilots. One audit trail. One price.", s["h1"]))
    story.append(Paragraph(
        "DOCex is not a chatbot you ask questions to. It's three named "
        "Co-Pilots, each one replacing the document-heavy parts of a "
        "specific role on your team. They share an engine, a Claude-"
        "written brief on every result, and an audit trail that survives "
        "later policy edits.",
        s["body"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(copilot_card(
        eyebrow="For sub-award & grants teams",
        title="Sub-award Co-Pilot",
        body=("Screen hundreds of partner applications in an afternoon. "
              "Verify grantee bank accounts before disbursement. Review "
              "quarterly reports against the original proposal."),
        proof="Two-week screening cycles compressed to an afternoon.",
        accent=AMBER,
    ))
    story.append(Spacer(1, 0.25 * cm))
    story.append(copilot_card(
        eyebrow="For events, training & programs teams",
        title="Programs Co-Pilot",
        body=("Drop in your attendance log and payment list. The Co-Pilot "
              "matches names, applies per-diem rates, flags attendees who "
              "never made it onto the schedule, and verifies every bank "
              "account before finance touches the file."),
        proof="Three hours of cross-checking becomes a three-minute review.",
        accent=VIOLET,
    ))
    story.append(Spacer(1, 0.25 * cm))
    story.append(copilot_card(
        eyebrow="For compliance & finance teams",
        title="Compliance Co-Pilot",
        body=("Upload your procurement, travel, or donor policy once. The "
              "Co-Pilot turns it into an editable rulebook. Every voucher "
              "gets checked rule by rule, with citations from both the "
              "policy and the voucher — and a decision log that captures "
              "approvals, escalations, and signatures."),
        proof="Defensible compliance, every time, with no extra paperwork.",
        accent=BRAND,
    ))
    story.append(Spacer(1, 0.25 * cm))

    # ── The moat: audit trail ──
    story.append(PageBreak())
    story.append(Paragraph("WHY IT HOLDS UP IN AUDIT", s["eyebrow"]))
    story.append(Paragraph("The audit trail that doesn't drift.", s["h1"]))
    story.append(Paragraph(
        "Most AI tools win the demo and lose the audit. DOCex was built "
        "from the start to be defensible. Every compliance check captures "
        "a frozen snapshot of the rulebook that was active when the check "
        "ran. Edit the policy a year later — yesterday's audit doesn't "
        "quietly change underneath you.",
        s["body"]))

    story.append(Paragraph("What we capture on every check:", s["h2"]))
    for b in [
        ("Rulebook snapshot",
         "Frozen at check-run time. Later edits create a new rulebook version."),
        ("Verdict per rule",
         "Pass / flag / block with the AI's reasoning and the source citations."),
        ("Document citations",
         "Every claim links back to the page + paragraph it came from."),
        ("Decision log",
         "Append-only timeline: notes, escalations, clarifications, approvals."),
        ("Signatures",
         "Drawn + typed signatures on approvals, escalations, and responses."),
        ("Approval chain",
         "Who reviewed, who escalated, who approved. Timestamped throughout."),
    ]:
        story.append(Paragraph(
            f"• <b>{b[0]}</b> — {b[1]}", s["bullet"]))

    story.append(Paragraph(
        "<b>The result:</b> when your auditor asks \"why was this voucher "
        "approved?\", you don't dig through inboxes. You send them a URL.",
        s["body"]))

    # ── What's included ──
    story.append(PageBreak())
    story.append(Paragraph("WHAT YOU GET", s["eyebrow"]))
    story.append(Paragraph("Every account, all the capabilities.", s["h1"]))
    story.append(Paragraph(
        "No \"premium\" features hidden behind tier walls. Every DOCex "
        "account ships with the full Co-Pilot suite, the full audit "
        "trail, and every export your auditor will ever ask for. We "
        "scope volume per organisation as part of the pilot conversation.",
        s["body"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(included_table())
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Volume, seats, and integration support are scoped together "
        "during the pilot — sized to your team and your document load.",
        s["small"]))

    # ── Pilot path ──
    story.append(PageBreak())
    story.append(Paragraph("HOW WE START", s["eyebrow"]))
    story.append(Paragraph("The 30-day pilot.", s["h1"]))
    story.append(Paragraph(
        "Most prospects start with a paid 30-day pilot. The flow:",
        s["body"]))

    stages = [
        ("Week 0 · Demo",
         "30-minute screen-share. We use sample data first, then your "
         "real (anonymised) docs for the last 10 minutes."),
        ("Week 1 · Setup",
         "We load your real policy, set up your team accounts, and seed "
         "one real check together so you see end-to-end how it works."),
        ("Week 2 · Run",
         "Your team runs real checks against real vouchers. The DOCex "
         "Assistant briefs every result. We sit in your Slack for fast "
         "fixes."),
        ("Week 3 · Tune",
         "We adjust thresholds, rulebook phrasing, and integrations based "
         "on what you saw. Most pilots only need 1–2 tweaks."),
        ("Week 4 · Decide",
         "You decide: convert to a monthly subscription, extend the "
         "pilot, or step away. No lock-in."),
    ]
    for stage, body in stages:
        story.append(Paragraph(f"<b>{stage}</b>", s["pillar"]))
        story.append(Paragraph(body, s["body"]))

    # ── Contact ──
    story.append(PageBreak())
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Ready to see it on your docs?", ParagraphStyle(
        "cta", fontName="Helvetica-Bold", fontSize=28, leading=32,
        textColor=INK, alignment=TA_CENTER)))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "Reply to this email with a 15-minute window. We'll send a "
        "screen-share link and a sample-data preview you can click "
        "before the call.",
        ParagraphStyle("ctab", fontName="Helvetica", fontSize=12,
                       leading=18, textColor=SUBTLE, alignment=TA_CENTER)))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "<b>Farid Abdurrahman</b>", s["center"]))
    story.append(Paragraph(
        "Founder, DOCex", s["center"]))
    story.append(Paragraph(
        "faridmichika@gmail.com", s["center"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Built with Claude · Hosted in the EU and US",
        ParagraphStyle("foot-sm", fontName="Helvetica", fontSize=9,
                       leading=12, textColor=SUBTLE, alignment=TA_CENTER)))

    doc.build(story)
    print(f"✓ Built {OUTPUT}")


if __name__ == "__main__":
    build()
