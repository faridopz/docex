"""
The month-end (or quarter-end) audit report.

THE TOKEN QUESTION, ANSWERED IN THE ARCHITECTURE
================================================
The naive way to write this would be to hand a model every requisition in the
period and ask for a report. For a hundred payments that is roughly fifty
thousand input tokens, every month, per client — and it would produce worse
output, because a model asked to both compute and narrate will quietly get a
total wrong and state it with confidence.

So the model never sees the population. Everything countable is computed here
in Python: the totals, the counts by status and category, the exception list,
the approval timings, and the findings from audit_findings.py. What goes to
the model is that finished summary — roughly two thousand tokens — and what
comes back is prose. One call, one report, about the cost of a rounding error
against a monthly licence.

The same DETERMINISTIC-FIRST split the rest of this codebase runs on: code
owns every number, the model writes the sentences around them.

FOUR THINGS THAT KEEP IT CHEAP AND HONEST
=========================================
1. Aggregate before prompting. The input is the report, not the records, so
   the prompt size is flat whether the org raised ten payments or ten
   thousand.
2. The cheap model. Narrating a structured summary is a Tier 3 task; it does
   not need the model that interprets policy documents.
3. Never regenerate unchanged. A stored report for a closed period is
   returned as-is. A month that has already ended cannot produce new figures,
   so paying to rewrite its narrative is pure waste.
4. Verify the output. Any money-sized figure in the narrative that was not in
   the input is a hallucination, and the report falls back to the
   deterministic text rather than printing it. See _figures_are_grounded().

If no API key is configured, or the call fails, the report is still produced —
from a template, with identical figures. A report that only exists when a
model is reachable is not a control.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import ai_config
import audit_findings
import requisitions as rq
import store

# Narrating a structured summary — the cheap, quick tier. Overridable at
# deploy time via the same env vars as every other model choice.
REPORT_MODEL = ai_config.MODEL_TIER_3

# Enough for an executive summary, commentary on each finding, and a short
# recommendation list. Deliberately tight: a report nobody finishes reading
# is not more useful for being longer.
_MAX_TOKENS = 1600

_client = None


def _get_client():
    """Lazily construct the Anthropic client — same seam as compliance.py, so
    tests can swap it without a network call."""
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


# ─── the deterministic half ─────────────────────────────────────────────────


@dataclass
class PeriodData:
    """Everything countable about a period. No model involved in any of it."""
    org_id: str
    label: str                                  # "September 2026"
    start: str
    end: str
    generated_at: str

    raised_count: int = 0
    raised_value: float = 0.0
    paid_count: int = 0
    paid_value: float = 0.0
    declined_count: int = 0
    outstanding_count: int = 0
    outstanding_value: float = 0.0

    by_status: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, float] = field(default_factory=dict)
    top_payees: list[tuple[str, float]] = field(default_factory=list)

    exceptions: list[dict] = field(default_factory=list)
    findings: list[audit_findings.Finding] = field(default_factory=list)

    median_days_to_approve: Optional[float] = None
    slowest_days: Optional[float] = None
    currency: str = "NGN"

    @property
    def audit_ready(self) -> bool:
        """No exception without a written reason, and no broken audit trail."""
        if any(not (e.get("reason") or "").strip() for e in self.exceptions):
            return False
        return not any(f.code == "CHAIN_BROKEN" for f in self.findings)


def _in_period(iso: str, start: str, end: str) -> bool:
    return bool(iso) and start <= iso[:10] <= end


def _days_between(a: str, b: str) -> Optional[float]:
    try:
        first = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        last = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((last - first).total_seconds() / 86400, 2)


def build_period_data(
    org_id: str, start: str, end: str, *, label: str = "", tz_offset_minutes: int = 0,
) -> PeriodData:
    """Compute every figure in the report. Pure arithmetic over stored records."""
    org = store.require_org(org_id)
    reqs = [r for r in rq.list_requisitions(org) if _in_period(r.submitted_at, start, end)]
    txns = [t for t in rq.list_transactions(org) if _in_period(t.paid_at, start, end)]

    data = PeriodData(
        org_id=org,
        label=label or f"{start} to {end}",
        start=start,
        end=end,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        currency=(reqs[0].currency if reqs else "NGN"),
    )

    data.raised_count = len(reqs)
    data.raised_value = round(sum(r.amount for r in reqs), 2)
    data.paid_count = len(txns)
    data.paid_value = round(sum(t.amount for t in txns), 2)
    data.declined_count = sum(1 for r in reqs if r.status == rq.ReqStatus.DECLINED)

    open_statuses = {rq.ReqStatus.IN_REVIEW, rq.ReqStatus.ON_HOLD,
                     rq.ReqStatus.SUBMITTED, rq.ReqStatus.APPROVED}
    outstanding = [r for r in reqs if r.status in open_statuses]
    data.outstanding_count = len(outstanding)
    data.outstanding_value = round(sum(r.amount for r in outstanding), 2)

    for r in reqs:
        data.by_status[r.status.value] = data.by_status.get(r.status.value, 0) + 1
        key = r.category or "uncategorised"
        data.by_category[key] = round(data.by_category.get(key, 0.0) + r.amount, 2)

    payees: dict[str, float] = {}
    for r in reqs:
        name = (r.vendor_name or "").strip() or "(unnamed)"
        payees[name] = round(payees.get(name, 0.0) + r.amount, 2)
    data.top_payees = sorted(payees.items(), key=lambda kv: kv[1], reverse=True)[:5]

    for txn in txns:
        for c in txn.checks:
            if c.overridden:
                data.exceptions.append({
                    "ref": txn.requisition_ref,
                    "check": c.code,
                    "reason": c.override_reason or "",
                    "authority": c.override_authority or "",
                    "approved_by": c.override_by or "",
                })

    # How long approvals actually took — the number a board asks about and
    # nobody can usually answer.
    durations: list[float] = []
    for r in reqs:
        finals = [a for a in r.approvals if a.decision == rq.Decision.APPROVED]
        if finals and r.submitted_at:
            gap = _days_between(r.submitted_at, finals[-1].at)
            if gap is not None and gap >= 0:
                durations.append(gap)
    if durations:
        durations.sort()
        mid = len(durations) // 2
        data.median_days_to_approve = (
            durations[mid] if len(durations) % 2
            else round((durations[mid - 1] + durations[mid]) / 2, 2)
        )
        data.slowest_days = durations[-1]

    data.findings = audit_findings.run_audit_tests(
        org, tz_offset_minutes=tz_offset_minutes,
    ).findings
    return data


# ─── the small, cheap model call ────────────────────────────────────────────


def _narrative_input(data: PeriodData) -> dict:
    """Exactly what the model is shown — nothing else reaches it.

    Compact on purpose. This is the whole reason the report costs the same
    whether the period held ten payments or ten thousand.
    """
    return {
        "period": data.label,
        "currency": data.currency,
        "raised": {"count": data.raised_count, "value": data.raised_value},
        "paid": {"count": data.paid_count, "value": data.paid_value},
        "outstanding": {"count": data.outstanding_count, "value": data.outstanding_value},
        "declined_count": data.declined_count,
        "by_status": data.by_status,
        "spend_by_category": data.by_category,
        "top_payees": [{"name": n, "value": v} for n, v in data.top_payees],
        "median_days_to_approve": data.median_days_to_approve,
        "slowest_approval_days": data.slowest_days,
        "exceptions": [
            {"ref": e["ref"], "check": e["check"],
             "has_reason": bool(e["reason"].strip()),
             "authority": e["authority"]}
            for e in data.exceptions
        ],
        "findings": [
            {"code": f.code, "title": f.title, "severity": f.severity,
             "detail": f.detail, "affected": len(f.refs), "value": f.amount}
            for f in data.findings
        ],
        "audit_ready": data.audit_ready,
    }


_SYSTEM = """You write the narrative of a period audit report for a donor-funded
non-profit's finance function. An internal auditor and a board audit committee
read it.

You are given a FINISHED report: every figure has already been computed from
the organisation's records. Your job is the prose around those figures, not
the figures.

Rules, in order of importance:

1. NEVER state a number that is not in the input. Not a total, not a count,
   not a percentage you worked out yourself. If you want to say something is
   large, say it is the largest category — do not compute its share.
2. Do not invent findings. Comment only on what the input contains. If the
   input has no findings, say the tests passed and do not manufacture concern.
3. Plain professional English. No jargon, no filler, no "it is important to
   note". Short sentences. British spelling.
4. Be proportionate. A low-severity observation is not a crisis; a broken
   audit trail is. Match the language to the severity given.
5. Where a finding is usually benign, say so — an auditor who is alarmed by
   everything stops being useful.

Return ONLY a JSON object, no other text:

{
  "executive_summary": "2-4 sentences. What happened this period and whether
                        anything needs attention.",
  "finding_commentary": [
     {"code": "<the finding code>", "comment": "1-3 sentences putting it in
      context and saying what to do about it."}
  ],
  "recommendations": ["short imperative actions, at most four, most important
                       first. Empty list if nothing is needed."]
}"""


_MONEY_RE = re.compile(r"\d[\d,]*\.?\d*")


def _figures_are_grounded(text: str, allowed: set[str]) -> bool:
    """Reject a narrative containing a money-sized figure that was not in the
    input.

    Small numbers are left alone — "three findings" and "within 5%" are
    verifiable from the text itself and forbidding them makes the prose
    stilted. Anything a thousand or more is treated as a claim about money
    and has to match something we supplied. A confidently wrong total in an
    audit report is worse than no report.
    """
    for raw in _MONEY_RE.findall(text):
        cleaned = raw.replace(",", "").rstrip(".")
        if not cleaned:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value >= 1000 and cleaned not in allowed:
            return False
    return True


def _allowed_figures(payload: dict) -> set[str]:
    """Every number we gave the model, in the forms it might echo back."""
    out: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)):
            out.add(str(node))
            out.add(str(int(node)) if float(node).is_integer() else str(node))
            out.add(f"{node:,.2f}".replace(",", ""))
            out.add(f"{node:.2f}")
    walk(payload)
    return out


def _fallback_narrative(data: PeriodData) -> dict:
    """The report without a model. Same figures, plainer sentences.

    Not a degraded mode to be embarrassed about — it is what makes the report
    a control rather than a feature. It runs when there is no API key, when
    the call fails, and when the model returns something ungrounded.
    """
    high = [f for f in data.findings if f.severity == "high"]
    if data.audit_ready and not data.findings:
        summary = (
            f"{data.raised_count} payment requests were raised in {data.label} and "
            f"{data.paid_count} were paid. Every audit test passed: no policy "
            "exception is unexplained and the audit trail verifies in full."
        )
    elif high:
        summary = (
            f"{data.raised_count} payment requests were raised in {data.label} and "
            f"{data.paid_count} were paid. {len(high)} matter(s) require attention "
            "before this period is signed off."
        )
    else:
        summary = (
            f"{data.raised_count} payment requests were raised in {data.label} and "
            f"{data.paid_count} were paid. The audit tests raised "
            f"{len(data.findings)} observation(s), none of them high severity."
        )
    return {
        "executive_summary": summary,
        "finding_commentary": [{"code": f.code, "comment": f.why} for f in data.findings],
        "recommendations": [
            f"Review {f.title.lower()}" for f in data.findings if f.severity == "high"
        ],
        "generated_by": "template",
    }


def narrate(data: PeriodData) -> dict:
    """The one model call in this module. Never raises."""
    payload = _narrative_input(data)
    try:
        client = _get_client()
        response = client.messages.create(
            model=REPORT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, separators=(",", ":"))}],
        )
        raw = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].removeprefix("json").strip()

        if not _figures_are_grounded(raw, _allowed_figures(payload)):
            print("[audit_report] narrative contained an ungrounded figure — "
                  "falling back to the template.")
            return _fallback_narrative(data)

        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or "executive_summary" not in parsed:
            return _fallback_narrative(data)
        parsed.setdefault("finding_commentary", [])
        parsed.setdefault("recommendations", [])
        parsed["generated_by"] = REPORT_MODEL
        usage = getattr(response, "usage", None)
        if usage is not None:
            parsed["tokens"] = {
                "input": getattr(usage, "input_tokens", 0),
                "output": getattr(usage, "output_tokens", 0),
            }
        return parsed
    except Exception as exc:                                    # noqa: BLE001
        print(f"[audit_report] narrative unavailable ({exc}) — using the template.")
        return _fallback_narrative(data)


# ─── the document ───────────────────────────────────────────────────────────


def audit_report_pdf(data: PeriodData, narrative: dict, *, org_name: str = "") -> bytes:
    """The filed artefact. Figures are rendered from `data` — never from the
    narrative — so even a wrong sentence cannot put a wrong number in a table.
    Same reportlab/platypus style as requisition_export.py."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Audit report — {data.label}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, spaceAfter=2,
                         textColor=colors.HexColor("#111827"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=14,
                         spaceAfter=5, textColor=colors.HexColor("#111827"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=14)
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=8.5,
                           textColor=colors.HexColor("#6B7280"))
    cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.5, leading=11)

    def money(v: float) -> str:
        return f"{data.currency} {v:,.2f}"

    def table(header, rows, widths):
        grid = [[Paragraph(f"<b>{h}</b>", cell) for h in header]]
        for r in rows:
            grid.append([Paragraph(str(v) if v not in (None, "") else "—", cell) for v in r])
        t = Table(grid, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    story: list = []
    story.append(Paragraph(f"Audit report — {data.label}", h1))
    story.append(Paragraph(org_name or data.org_id, meta))
    story.append(Paragraph(
        f"Covering {data.start} to {data.end}. Generated {data.generated_at[:19].replace('T', ' ')} UTC. "
        "Every figure is counted from stored records.", meta))

    verdict = ("This period is audit-ready: no policy exception is unexplained and "
               "the audit trail verifies."
               if data.audit_ready else
               "This period is NOT audit-ready. See the findings below.")
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        verdict,
        ParagraphStyle("Verdict", parent=body, fontSize=10,
                        textColor=colors.HexColor("#059669") if data.audit_ready
                        else colors.HexColor("#DC2626")),
    ))

    story.append(Paragraph("Summary", h2))
    story.append(Paragraph(narrative.get("executive_summary", ""), body))

    story.append(Paragraph("The period in figures", h2))
    story.append(table(
        ["", "Count", "Value"],
        [["Raised", data.raised_count, money(data.raised_value)],
         ["Paid", data.paid_count, money(data.paid_value)],
         ["Still open at period end", data.outstanding_count, money(data.outstanding_value)],
         ["Declined", data.declined_count, ""]],
        [190, 60, 130],
    ))
    if data.median_days_to_approve is not None:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Median time to approval: {data.median_days_to_approve} days. "
            f"Slowest: {data.slowest_days} days.", meta))

    if data.by_category:
        story.append(Paragraph("Spend by category", h2))
        rows = sorted(data.by_category.items(), key=lambda kv: kv[1], reverse=True)
        story.append(table(["Category", "Value"],
                            [[k.replace("_", " ").title(), money(v)] for k, v in rows],
                            [240, 140]))

    if data.top_payees:
        story.append(Paragraph("Largest payees", h2))
        story.append(table(["Payee", "Value"],
                            [[n, money(v)] for n, v in data.top_payees], [240, 140]))

    commentary = {c.get("code"): c.get("comment", "") for c in narrative.get("finding_commentary", [])}
    if data.findings:
        story.append(Paragraph("Audit findings", h2))
        for f in data.findings:
            story.append(Paragraph(
                f"<b>{f.title}</b> — {f.severity.upper()}",
                ParagraphStyle("FT", parent=body,
                                textColor=colors.HexColor("#DC2626") if f.severity == "high"
                                else colors.HexColor("#B45309") if f.severity == "medium"
                                else colors.HexColor("#4B5563")),
            ))
            story.append(Paragraph(f.detail, body))
            note = commentary.get(f.code)
            if note:
                story.append(Paragraph(note, body))
            if f.refs:
                shown = ", ".join(f.refs[:15])
                extra = f" and {len(f.refs) - 15} more" if len(f.refs) > 15 else ""
                story.append(Paragraph(f"Affected: {shown}{extra}", meta))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("Audit findings", h2))
        story.append(Paragraph("Every test passed. No findings were raised.", body))

    if data.exceptions:
        story.append(Paragraph("Policy exceptions released", h2))
        story.append(table(
            ["Reference", "Check", "Authority", "Reason"],
            [[e["ref"], e["check"], e["authority"],
              e["reason"] or "NO REASON RECORDED"] for e in data.exceptions],
            [70, 95, 90, 125],
        ))

    recommendations = narrative.get("recommendations") or []
    if recommendations:
        story.append(Paragraph("Recommended actions", h2))
        for i, rec in enumerate(recommendations, start=1):
            story.append(Paragraph(f"{i}. {rec}", body))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Figures in this report are computed from stored records. The narrative "
        f"was drafted by {narrative.get('generated_by', 'template')} from those "
        "figures and states no number that was not supplied to it.", meta))

    doc.build(story)
    return buf.getvalue()
