"""
Payment voucher export — a requisition rendered as the organisation's OWN
voucher, not ours.

WHY THIS IS CORE AND NOT CUSTOM

NEEM asked for their payment voucher. Every organisation that pays anyone has
one, and they all carry the same bones: who is being paid, out of which budget,
for what, how much, and who signed. What differs is the letterhead, the field
labels, the account codes and the names of the signature roles.

So none of NEEM's specifics live here. `voucher_template` in the org profile
supplies the letterhead, the certification wording, the signature roles and the
chart of accounts; this module renders whatever it is given. The test suite
stands up a second organisation with a deliberately different template and
asserts the two vouchers differ, because that assertion is the whole argument
for building it this way.

THE PV NUMBER IS ALLOCATED ONCE AND NEVER MOVES

NEEM's format is NF/HQ/B24/CARE/SEP23/PV/01 — org, location, project, donor,
month, sequence. Two properties matter more than the format:

  1. It is STABLE. Re-exporting a voucher must return the same number. A
     payment voucher number is a filing reference; if it changes on the second
     print, the copy in the file and the copy in the system disagree, and an
     auditor reconciling them finds two vouchers for one payment.
  2. It is allocated on FIRST EXPORT, not at requisition creation. Most
     requisitions never need a voucher, and burning a number on each one
     leaves gaps in a sequence that Finance reads as missing documents.

Numbers are therefore held in their own org-scoped collection keyed by
requisition id, not written back onto the requisition.

DETERMINISTIC-FIRST

Every amount here is computed in code. The total is the sum of the line
amounts, recomputed at render time rather than read from a stored field, and
an unmapped category renders a BLANK account code — never a guessed one. A
wrong code does not crash; it quietly posts a payment to the wrong ledger
account, which is exactly the class of error CLAUDE.md puts in code's hands.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

import store

_VOUCHER_NUMBERS = "voucher_numbers"
_VOUCHER_SEQ = "voucher_sequence"
_CONFIG = "config"
_TEMPLATE_ID = "voucher_template"


# ─── configuration ───────────────────────────────────────────────────────────
#
# Defaults are deliberately generic. An organisation that has configured
# nothing still gets a usable voucher with its own name on it, rather than an
# error or somebody else's letterhead.

_DEFAULT_TEMPLATE: dict = {
    "title": "Payment Voucher",
    "letterhead": {"org_name": "", "rc_number": "", "address_lines": []},
    "certification": (
        "I certify that the above account is correct, that the services have "
        "been duly performed or that the goods have been correctly received "
        "and that the expenditure was incurred in the interest of the "
        "organisation's works."
    ),
    # source: "submitter" | a workflow step key | "" (always blank, e.g. the
    # person receiving the money, who cannot be known before payment)
    "signature_roles": [
        {"label": "Prepared by", "source": "submitter"},
        {"label": "Approved by", "source": ""},
        {"label": "Received by", "source": ""},
    ],
    "account_codes": {},
    # Placeholders: {org} {location} {project_code} {donor} {MONYY} {seq}
    "pv_number_format": "",
    "pv_org_prefix": "",
    "pv_location": "",
}


def get_template(org_id: str) -> dict:
    """The org's voucher template, merged over the generic default."""
    raw = store.get_store().get(store.require_org(org_id), _CONFIG, _TEMPLATE_ID) or {}
    merged = {**_DEFAULT_TEMPLATE, **{k: v for k, v in raw.items() if v not in (None, "")}}
    # Nested dicts merge one level down so a partial letterhead does not wipe
    # the defaults for the keys it omits.
    merged["letterhead"] = {**_DEFAULT_TEMPLATE["letterhead"],
                            **(raw.get("letterhead") or {})}
    return merged


def set_template(org_id: str, template: dict) -> dict:
    """Store an org's voucher template. Validated by the caller (org_config)."""
    org = store.require_org(org_id)
    store.get_store().put(org, _CONFIG, _TEMPLATE_ID, dict(template))
    return get_template(org)


# ─── the PV number ───────────────────────────────────────────────────────────


_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _period_key(when: dt.datetime) -> str:
    return f"{_MONTHS[when.month - 1]}{when.year % 100:02d}"


def _next_sequence(org_id: str, period: str) -> int:
    """Monotonic per-org, per-month counter.

    Read-modify-write. The store is the serialisation point; two exports of
    different requisitions in the same second could in principle collide, and
    the mitigation is that a duplicate is visible (two vouchers with one
    number) rather than silent. A stronger guarantee belongs in the store, not
    here.
    """
    st = store.get_store()
    org = store.require_org(org_id)
    rec = st.get(org, _VOUCHER_SEQ, period) or {}
    nxt = int(rec.get("last", 0)) + 1
    st.put(org, _VOUCHER_SEQ, period, {"last": nxt, "period": period})
    return nxt


def pv_number_for(req, org_id: str, *, when: Optional[dt.datetime] = None) -> str:
    """The voucher number for this requisition, allocated once and reused.

    Returns "" when the org has configured no format, which is a legitimate
    choice: some finance teams keep the numbering in their own register and
    want the field left blank to write in by hand.
    """
    org = store.require_org(org_id)
    st = store.get_store()

    existing = st.get(org, _VOUCHER_NUMBERS, req.id) or {}
    if existing.get("pv_number"):
        return str(existing["pv_number"])

    tpl = get_template(org)
    fmt = (tpl.get("pv_number_format") or "").strip()
    if not fmt:
        return ""

    when = when or dt.datetime.now(dt.timezone.utc)
    period = _period_key(when)
    seq = _next_sequence(org, period)
    number = (fmt
              .replace("{org}", tpl.get("pv_org_prefix") or "")
              .replace("{location}", tpl.get("pv_location") or "")
              .replace("{project_code}", getattr(req, "project_code", "") or "")
              .replace("{donor}", getattr(req, "grant_code", None) or "")
              .replace("{MONYY}", period)
              .replace("{seq}", f"{seq:02d}"))

    st.put(org, _VOUCHER_NUMBERS, req.id,
           {"pv_number": number, "requisition_ref": getattr(req, "ref", ""),
            "allocated_at": when.isoformat(timespec="seconds")})
    return number


# ─── the voucher model ───────────────────────────────────────────────────────


@dataclass
class VoucherLine:
    account_code: str
    details: str
    amount: float


@dataclass
class VoucherSignature:
    label: str
    name: str          # "" when the role has not been filled yet
    date: str          # "" likewise


@dataclass
class Voucher:
    title: str
    org_name: str
    rc_number: str
    address_lines: list[str]
    pv_number: str
    payee: str
    date: str
    address: str
    bank_name: str
    chargeable_to: str
    cheque_no: str
    lines: list[VoucherLine] = field(default_factory=list)
    total: float = 0.0
    currency: str = "NGN"
    amount_in_words: str = ""
    certification: str = ""
    signatures: list[VoucherSignature] = field(default_factory=list)
    source_ref: str = ""


def _approvals_by_step(req) -> dict[str, tuple[str, str]]:
    """step key -> (actor, date) for approvals actually recorded.

    Read from the approval trail rather than inferred from status, because the
    trail is the tamper-evident record and status is a summary of it.
    """
    out: dict[str, tuple[str, str]] = {}
    for a in getattr(req, "approvals", None) or []:
        decision = str(getattr(a, "decision", "") or "").lower()
        if decision != "approved":
            continue
        step = str(getattr(a, "step", "") or getattr(a, "step_key", "") or "")
        actor = str(getattr(a, "actor", "") or "")
        at = str(getattr(a, "at", "") or "")[:10]
        if step:
            out[step] = (actor, at)
    return out


def _lines_for(req, codes: dict) -> list[VoucherLine]:
    """One row per payee for a batch, else one per budget line, else one row.

    A category with no configured account code renders BLANK. Guessing a code
    would post the payment to the wrong ledger account and nothing would
    crash — the failure would surface weeks later in a reconciliation.
    """
    code = str(codes.get((getattr(req, "category", "") or "").strip().lower(), "") or "")
    payees = list(getattr(req, "payees", None) or [])
    if payees:
        return [
            VoucherLine(
                account_code=code,
                details=(f"{p.name}" + (f" — {p.purpose}" if getattr(p, "purpose", "") else "")),
                amount=float(getattr(p, "amount", 0.0) or 0.0),
            )
            for p in payees
        ]

    budget = list(getattr(req, "budget_lines", None) or [])
    if budget:
        return [
            VoucherLine(account_code=code,
                        details=str(getattr(b, "description", "") or ""),
                        amount=float(getattr(b, "line_total", 0.0) or 0.0))
            for b in budget
        ]

    return [VoucherLine(account_code=code,
                        details=str(getattr(req, "description", "") or ""),
                        amount=float(getattr(req, "amount", 0.0) or 0.0))]


def build_voucher(req, org_id: str, *, when: Optional[dt.datetime] = None) -> Voucher:
    """Assemble the voucher. Pure apart from the PV number allocation.

    Kept separate from rendering so every number on the page can be asserted
    without parsing a PDF.
    """
    tpl = get_template(org_id)
    head = tpl["letterhead"]
    lines = _lines_for(req, tpl.get("account_codes") or {})

    # Recomputed, never read from a stored total. For a multi-payee batch the
    # requisition's own amount is the authority the engine already validated,
    # so a mismatch here would mean the payee rows and the approved amount
    # disagree — surface it by summing what is actually printed.
    total = round(sum(l.amount for l in lines), 2)

    approvals = _approvals_by_step(req)
    sigs: list[VoucherSignature] = []
    for role in tpl.get("signature_roles") or []:
        source = str(role.get("source") or "")
        name = date = ""
        if source == "submitter":
            name = str(getattr(req, "submitted_by", "") or "")
            date = str(getattr(req, "submitted_at", "") or "")[:10]
        elif source and source in approvals:
            name, date = approvals[source]
        sigs.append(VoucherSignature(label=str(role.get("label") or ""),
                                     name=name, date=date))

    payees = list(getattr(req, "payees", None) or [])
    payee_name = (f"Various ({len(payees)} payees)" if len(payees) > 1
                  else (payees[0].name if payees
                        else str(getattr(req, "vendor_name", "") or "")))
    bank = (str(getattr(req, "vendor_bank_name", "") or "") if not payees
            else ("Various" if len({p.bank_name for p in payees}) > 1
                  else (payees[0].bank_name or "")))

    chargeable = " / ".join(x for x in (getattr(req, "project_code", "") or "",
                                        getattr(req, "grant_code", None) or "") if x)

    return Voucher(
        title=str(tpl.get("title") or "Payment Voucher"),
        org_name=str(head.get("org_name") or ""),
        rc_number=str(head.get("rc_number") or ""),
        address_lines=[str(x) for x in (head.get("address_lines") or [])],
        pv_number=pv_number_for(req, org_id, when=when),
        payee=payee_name,
        date=str(getattr(req, "submitted_at", "") or "")[:10],
        address="",
        bank_name=bank,
        chargeable_to=chargeable,
        cheque_no="",
        lines=lines,
        total=total,
        currency=str(getattr(req, "currency", "NGN") or "NGN"),
        amount_in_words=str(getattr(req, "amount_in_words", "") or ""),
        certification=str(tpl.get("certification") or ""),
        signatures=sigs,
        source_ref=str(getattr(req, "ref", "") or ""),
    )


# ─── rendering ───────────────────────────────────────────────────────────────
#
# Laid out to match a conventional Nigerian payment voucher: letterhead with
# RC number, the payee/date/bank/chargeable box, a coded line table with naira
# and kobo in separate columns, amount in words, the certification sentence,
# and the signature block. The shape is common enough across organisations to
# be the default; the WORDS in it all come from config.


_UNICODE_FONT: Optional[str] = None
_FONT_SEARCHED = False

# Candidate fonts carrying U+20A6 (NAIRA SIGN). Helvetica, reportlab's
# default, does not have it: the symbol renders as a filled black box.
_FONT_CANDIDATES = (
    ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("DejaVuSans", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("LiberationSans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
)


def _unicode_font() -> Optional[str]:
    """A registered font family that can draw the naira sign, or None.

    TWO FAILURES THIS PREVENTS, and the second one cost a render to find.

    First: the production image (python:3.12-slim) had no font package at
    all, while any developer machine ships DejaVu. A voucher that looked
    perfect locally would print the currency symbol as a filled black box for
    the client. api/Dockerfile now installs fonts-dejavu-core.

    Second: registering only the REGULAR face is not enough. Every place the
    symbol appears on this voucher is inside <b></b>, so reportlab looks for
    the "-Bold" variant, fails to find it, and silently falls back to
    Helvetica — which is where the box came from in the first place. Both
    faces are registered and mapped with registerFontFamily so bold resolves.
    """
    global _UNICODE_FONT, _FONT_SEARCHED
    if _FONT_SEARCHED:
        return _UNICODE_FONT
    _FONT_SEARCHED = True
    import os.path
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for name, regular, bold in _FONT_CANDIDATES:
            if not (os.path.exists(regular) and os.path.exists(bold)):
                continue
            pdfmetrics.registerFont(TTFont(name, regular))
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold))
            pdfmetrics.registerFontFamily(name, normal=name, bold=f"{name}-Bold",
                                          italic=name, boldItalic=f"{name}-Bold")
            _UNICODE_FONT = name
            break
    except Exception:
        _UNICODE_FONT = None
    return _UNICODE_FONT


def _currency_mark(currency: str) -> str:
    """The symbol if it can actually be drawn, else the ISO code.

    "TOTAL NGN" is plain. A black box is a defect a finance officer will
    photograph and send to you.
    """
    if (currency or "NGN").upper() == "NGN" and _unicode_font():
        return "\u20a6"
    return (currency or "NGN").upper()


def _naira_kobo(amount: float) -> tuple[str, str]:
    """Split into the two columns the voucher prints separately.

    Rounded to the nearest kobo first. Formatting a float directly can print
    99 kobo as 98 on values that are not exactly representable, and a voucher
    that is a kobo out from the invoice is a query from the bank.
    """
    cents = int(round(float(amount) * 100))
    return f"{cents // 100:,}", f"{abs(cents) % 100:02d}"


def voucher_pdf(req, org_id: str, *, when: Optional[dt.datetime] = None) -> bytes:
    """Render the voucher as a PDF. All content decisions live in build_voucher."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    v = build_voucher(req, org_id, when=when)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"{v.title} {v.pv_number or v.source_ref}".strip())

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("V", parent=styles["Normal"], fontSize=9, leading=12)
    small = ParagraphStyle("VS", parent=normal, fontSize=7.5, leading=10,
                           textColor=colors.HexColor("#444444"))
    right = ParagraphStyle("VR", parent=small, alignment=2)
    title = ParagraphStyle("VT", parent=styles["Heading1"], fontSize=14,
                           alignment=1, spaceBefore=4, spaceAfter=10,
                           textColor=colors.black)
    cell = ParagraphStyle("VC", parent=normal, fontSize=8.5, leading=11)

    RULE = colors.HexColor("#1F4E79")
    GRID = colors.HexColor("#333333")
    W = doc.width
    flow: list = []

    # Letterhead: name left, RC number and address right.
    head_right = "<br/>".join(
        ([f"<b><i>RC No: {v.rc_number}</i></b>"] if v.rc_number else [])
        + ([f"<i>{line}</i>" for line in v.address_lines] if v.address_lines else []))
    flow.append(Table(
        [[Paragraph(f"<b>{v.org_name}</b>" if v.org_name else "", normal),
          Paragraph(head_right, right)]],
        colWidths=[W * 0.55, W * 0.45],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                          ("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                          ("LINEBELOW", (0, 0), (-1, -1), 1.4, RULE),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])))
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(f"<u>{v.title}</u>", title))

    # P.V. number, right-aligned above the box.
    flow.append(Table(
        [[Paragraph(f"<b>P.V. NO:</b>&nbsp;&nbsp;{v.pv_number or '_' * 28}", right)]],
        colWidths=[W],
        style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                          ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])))

    # The payee box.
    def _kv(label: str, value: str) -> "Paragraph":
        return Paragraph(f"<b>{label}</b>&nbsp; {value or ''}", cell)

    flow.append(Table(
        [[_kv("PAYEE:", v.payee), _kv("DATE:", v.date)],
         [_kv("ADDRESS:", v.address), _kv("BANK NAME:", v.bank_name)],
         [_kv("CHARGEABLE TO:", v.chargeable_to), _kv("CHEQUE NO.:", v.cheque_no)]],
        colWidths=[W * 0.55, W * 0.45],
        style=TableStyle([("GRID", (0, 0), (-1, -1), 0.7, GRID),
                          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                          ("TOPPADDING", (0, 0), (-1, -1), 5),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                          ("LEFTPADDING", (0, 0), (-1, -1), 6)])))
    flow.append(Spacer(1, 12))

    # Line table. Naira and kobo are separate columns, as on the paper form.
    hdr = ParagraphStyle("VH", parent=cell, alignment=1, fontSize=8)
    # The currency symbol needs a font that actually has the glyph, and only
    # the two cells that print it are switched to it — the rest of the
    # voucher stays on Helvetica so the document keeps one consistent look.
    uni = _unicode_font()
    money_hdr = ParagraphStyle("VMH", parent=hdr, fontName=uni) if uni else hdr
    mark = _currency_mark(v.currency)
    rows: list[list] = [
        [Paragraph("<b>TRANSACTION<br/>CODE</b>", hdr),
         Paragraph("<b>DETAILS</b>", hdr),
         Paragraph("<b>AMOUNT</b>", hdr), ""],
        ["", "", Paragraph(f"<b>{mark}</b>", money_hdr), Paragraph("<b>K</b>", hdr)],
    ]
    for line in v.lines:
        naira, kobo = _naira_kobo(line.amount)
        rows.append([Paragraph(line.account_code or "", cell),
                     Paragraph(line.details or "", cell),
                     Paragraph(naira, ParagraphStyle("VA", parent=cell, alignment=2)),
                     Paragraph(kobo, hdr)])

    # Keep the form looking like a form even when a payment has two lines.
    for _ in range(max(0, 8 - len(v.lines))):
        rows.append(["", "", "", ""])

    t_naira, t_kobo = _naira_kobo(v.total)
    rows.append(["", Paragraph(f"<b>TOTAL {mark}</b>", ParagraphStyle(
        "VTot", parent=cell, alignment=1,
        **({"fontName": uni} if uni else {}))),
        Paragraph(f"<b>{t_naira}</b>", ParagraphStyle("VA2", parent=cell, alignment=2)),
        Paragraph(f"<b>{t_kobo}</b>", hdr)])

    cw = [W * 0.16, W * 0.54, W * 0.22, W * 0.08]
    flow.append(Table(rows, colWidths=cw, repeatRows=2, style=TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, GRID),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (3, 0)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))
    flow.append(Spacer(1, 10))

    words = v.amount_in_words or ""
    flow.append(Paragraph(
        f"<b>Amount In Words:</b>&nbsp; {words}{'' if words else '_' * 90}", normal))
    flow.append(Spacer(1, 10))
    if v.certification:
        flow.append(Paragraph(f"<b>{v.certification}</b>", small))
    flow.append(Spacer(1, 12))

    # Signature block. A filled name sits ABOVE the rule rather than replacing
    # it: the system records who approved and when, and the rule is still
    # there for a wet signature where the organisation wants one.
    sig_rows = []
    for s in v.signatures:
        who = s.name or ""
        sig_rows.append([
            Paragraph(f"<b>{s.label}:</b>&nbsp; {who}<br/>"
                      f"<font color='#888888'>{'_' * 46}</font>", cell),
            Paragraph(f"<b>Date:</b>&nbsp; {s.date or ''}<br/>"
                      f"<font color='#888888'>{'_' * 24}</font>", cell),
        ])
    if sig_rows:
        flow.append(Table(sig_rows, colWidths=[W * 0.62, W * 0.38],
                          style=TableStyle([
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 9),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                              ("VALIGN", (0, 0), (-1, -1), "BOTTOM")])))

    # Provenance. Ties the paper back to the record without dominating it.
    flow.append(Spacer(1, 12))
    flow.append(Paragraph(
        f"Generated from {v.source_ref} · "
        f"{(when or dt.datetime.now(dt.timezone.utc)).strftime('%d %b %Y')}", small))

    doc.build(flow)
    return buf.getvalue()
