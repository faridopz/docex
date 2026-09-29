#!/usr/bin/env python3
"""
Seed the demo organisation — Riverbend Health Foundation, a made-up NGO — with
eight weeks of payment requests in every state a recording or sales call needs.

    DOCEX_ORG=demo DOCEX_DB=./demo.db python3 demo_seed.py --password '…'
    DOCEX_ORG=demo DOCEX_DB=./demo.db python3 demo_seed.py --password '…' --reset
    (or set DEMO_PASSWORD instead of --password)

Rules this file keeps, and why:

* It writes to the organisation "demo" and nowhere else. Run with DOCEX_ORG
  set to a real client and it stops before touching anything: a seeder that
  can fill a client's live system with fake payments is a data incident
  waiting to happen.
* No password is written here or in profiles/demo.json. Every demo login gets
  the one you pass in.
* Everything is fictional. Email addresses use the reserved ".example"
  domain, so no notification can ever reach a real inbox.
* The data goes through the real engine (create, attach, approve, pay), not
  written straight into the database. So every audit trail is a genuine,
  verifiable chain, and every check shown is the check the engine really ran.
  Only the clock is moved, so the history spans weeks instead of seconds.

The configuration itself (departments, approval steps, quote bands, grants,
voucher letterhead) is profiles/demo.json, applied like any client's.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import sys
import uuid
import zlib
from pathlib import Path

DEMO_ORG = "demo"
DOMAIN = "riverbend.example"
PROFILE = Path(__file__).parent / "profiles" / "demo.json"

# (email local part, name, department, role, job title shown in the summary)
PEOPLE = [
    ("aisha", "Aisha Bello", "program", "reviewer", "Programme Officer"),
    ("musa", "Musa Danjuma", "program", "reviewer", "Field Officer"),
    ("tunde", "Tunde Okafor", "program", "approver", "Programme Manager (budget holder)"),
    ("grace", "Grace Eze", "hr", "reviewer", "Admin Officer"),
    ("halima", "Halima Yusuf", "hr", "approver", "HR & Admin Manager (budget holder)"),
    ("ngozi", "Ngozi Obi", "finance", "reviewer", "Finance Officer"),
    ("ibrahim", "Ibrahim Sule", "finance", "approver", "Finance Manager"),
    ("amaka", "Amaka Nwosu", "ed", "approver", "Executive Director"),
    ("admin", "Demo Admin", "finance", "admin", "System administrator"),
]


def _email(local: str) -> str:
    return f"{local}@{DOMAIN}"


# ─── the moved clock ──────────────────────────────────────────────────────────


class _Clock:
    """Every engine that stamps a time reads it from here while seeding."""

    def __init__(self) -> None:
        self.now = dt.datetime.now(dt.timezone.utc)

    def at(self, days_ago: float, hour: int = 10, minute: int = 0, *, fresh: bool = False) -> None:
        """Move to `days_ago` days back at hour:minute (UTC), on a working day.

        Weekends move to the Friday before, because a demo full of Saturday
        approvals trips the product's own out-of-hours audit test. Within one
        request time only moves forward (`fresh` starts a new request), so a
        payment can never be stamped before the approval it follows.
        """
        real = dt.datetime.now(dt.timezone.utc)
        t = real.replace(hour=hour, minute=minute, second=0, microsecond=0) - dt.timedelta(days=int(days_ago))
        while t.weekday() >= 5:
            t -= dt.timedelta(days=1)
        if not fresh and t <= self.now:
            t = self.now + dt.timedelta(minutes=40)
        self.now = min(t, real - dt.timedelta(minutes=5))   # never in the future

    def iso(self, spec: str = "microseconds") -> str:
        self.now += dt.timedelta(seconds=7)         # keep events in order within a day
        return self.now.isoformat(timespec=spec)


@contextlib.contextmanager
def _moved_clock(clock: _Clock):
    import advances
    import auth
    import grants
    import notification_center
    import requisitions as rq

    saved = (rq._now_iso, advances._now_iso, advances._today, grants._now_iso,
             notification_center._now_iso, auth._now_iso)
    rq._now_iso = lambda: clock.iso("microseconds")
    advances._now_iso = lambda: clock.iso("seconds")
    advances._today = lambda: clock.now.date()
    grants._now_iso = lambda: clock.iso("seconds")
    notification_center._now_iso = lambda: clock.iso("microseconds")
    auth._now_iso = lambda: clock.iso("seconds")
    try:
        yield clock
    finally:
        (rq._now_iso, advances._now_iso, advances._today, grants._now_iso,
         notification_center._now_iso, auth._now_iso) = saved


# ─── small helpers ────────────────────────────────────────────────────────────


def _pdf(title: str, lines: list[str]) -> bytes:
    """A one-page PDF standing in for a scanned memo, invoice or quote."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 11)
    for i, line in enumerate(lines):
        c.drawString(60, 750 - i * 18, line)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(60, 60, "Demonstration document — Riverbend Health Foundation is fictional.")
    c.save()
    return buf.getvalue()


def _label(doc: str) -> str:
    import requisitions as rq
    return rq._doc_label(doc)


def _attach(req, docs: list[str], actor: str) -> None:
    import attachments
    import requisitions as rq

    backend = attachments.get_backend()
    for doc in docs:
        att_id = uuid.uuid4().hex[:12]
        name = f"{doc}.pdf"
        body = _pdf(_label(doc), [f"Request {req.ref}", f"Payee: {req.vendor_name}",
                                  f"Amount: NGN {req.amount:,.2f}", f"Project: {req.project_code or '-'}"])
        key = backend.put(DEMO_ORG, req.id, att_id, name, body, "application/pdf")
        rq.add_attachment(DEMO_ORG, req.id, actor=actor, filename=name, content_type="application/pdf",
                          size=len(body), storage_key=key, attachment_id=att_id, document_type=doc)


# ─── the story ────────────────────────────────────────────────────────────────


class _Story:
    """Raise, approve and pay requests the way people would, on given days."""

    def __init__(self, clock: _Clock) -> None:
        import requisitions as rq
        self.rq = rq
        self.clock = clock
        self.wf = rq.get_workflow(DEMO_ORG)
        self.dept = {_email(p[0]): p[2] for p in PEOPLE}

    def raise_(self, days_ago: float, who: str, *, vendor: str, amount: float, category: str,
               grant: str = "GF-TB-26", description: str = "", attach: list[str] | None = None,
               missing: tuple[str, ...] = (), submit: bool = True, payees=None,
               account: str = "", bank: str = "GTBank", activity_end: str = ""):
        rq = self.rq
        self.clock.at(days_ago, 9, 20, fresh=True)
        actor = _email(who)
        req = rq.create_requisition(
            DEMO_ORG, submitted_by=actor, department=self.dept[actor], vendor_name=vendor,
            amount=amount, category=category, project_code=grant, grant_code=grant,
            vendor_account=account or f"01{zlib.crc32(vendor.encode()) % 10**8:08d}", vendor_bank_name=bank,
            description=description, payees=payees, submit=False, activity_end=activity_end)
        docs = attach if attach is not None else rq.required_documents_for(self.wf, category, req.amount)
        _attach(req, [d for d in docs if d not in missing], actor)
        if submit:
            req = rq.submit_draft(DEMO_ORG, req.id, actor=actor)
        return req

    def _approver_for(self, req) -> str:
        owner = self.rq.step_owner(self.rq._step(self.wf, req.current_step), req)
        return {"program": "tunde", "hr": "halima", "finance": "ibrahim", "ed": "amaka"}[owner]

    def approve(self, req, days_ago: float, *, until: str | None = None, notes: str = "",
                overrides: list[str] | None = None, reason: str = ""):
        """Approve step by step; stop before step `until` (None = all the way)."""
        rq = self.rq
        hour = 11
        while req.status == rq.ReqStatus.IN_REVIEW and req.current_step != until:
            who = self._approver_for(req)
            self.clock.at(days_ago, hour)
            hour += 2
            step = rq._step(self.wf, req.current_step)
            if rq.blocking_checks(req) and not step.can_override:
                # What a budget holder does with a request they can't clear:
                # confirm the need and pass it to whoever holds the authority
                # (the "Pass to Finance" button), recorded with a reason.
                chain = [s.key for s in rq._steps_for(self.wf, req.amount)]
                later = [s for s in rq._steps_for(self.wf, req.amount)
                         if chain.index(s.key) > chain.index(step.key) and s.can_override]
                req = rq.route_to(DEMO_ORG, req.id, target_step=later[0].key, actor=_email(who),
                                  department=self.dept[_email(who)],
                                  reason="Needed for the activity. A check is failing that I can't "
                                         f"release; passing to {later[0].label} to decide.")
                continue
            kwargs = {}
            if overrides and rq.blocking_checks(req):
                kwargs = dict(overrides=overrides, override_reason=reason,
                              override_authority=f"{req.current_step} override limit")
            req = rq.decide(DEMO_ORG, req.id, decision=rq.Decision.APPROVED, actor=_email(who),
                            department=self.dept[_email(who)], notes=notes, **kwargs)
            days_ago = max(days_ago - 0.6, 0)
        return req

    def pay(self, req, days_ago: float):
        self.clock.at(days_ago, 15)
        return self.rq.mark_paid(DEMO_ORG, req.id, actor=_email("ngozi"), department="finance",
                                 bank_reference=f"GTB/FT/{req.ref.replace('REQ-', '')}{int(req.amount) % 997:03d}")

    def decide(self, req, days_ago: float, decision, notes: str):
        who = self._approver_for(req)
        self.clock.at(days_ago, 14)
        return self.rq.decide(DEMO_ORG, req.id, decision=decision, actor=_email(who),
                              department=self.dept[_email(who)], notes=notes)


def _tell(s: _Story) -> None:
    """The last eight weeks at Riverbend, in the order they happened, so the
    request numbers run in date order just as they would in real use."""
    rq = s.rq
    import advances
    Payee = rq.Payee

    # ── August: paid, cleanly ───────────────────────────────────────────────
    r = s.raise_(56, "aisha", vendor="Greenfield Conference Centre", amount=420_000, category="venue",
                 description="Hall and lunch, TB case-finding training, Kaduna (2 days)")
    s.pay(s.approve(r, 55), 53)

    r = s.raise_(50, "musa", vendor="Swift Movers Ltd", amount=185_000, category="transport",
                 grant="MNH-26", description="Bus hire, outreach to 4 wards, Zaria")
    s.pay(s.approve(r, 49), 48)

    r = s.raise_(46, "grace", vendor="Crestline Office Supplies", amount=96_500, category="supplies",
                 description="Printer toner and paper, Q3 office supplies")
    s.pay(s.approve(r, 45), 44)

    r = s.raise_(42, "aisha", vendor="Pathway Consulting", amount=1_850_000, category="consultancy",
                 description="Baseline survey analysis, community TB project")
    s.pay(s.approve(r, 41), 38)

    # ── paid over an override: the audit page shows it, with the reason ─────
    r = s.raise_(36, "musa", vendor="Northern Logistics Ltd", amount=140_000, category="transport",
                 description="Vehicle hire, 3 LGAs, supervision visit", missing=("invoice",))
    r = s.approve(r, 35, overrides=["DOCS_COMPLETE"],
                  reason="Driver's invoice lost in transit; trip log and bank details confirmed by phone. "
                         "Invoice copy requested for the file.")
    s.pay(r, 34)

    # ── a stipend list: twelve people, one request ──────────────────────────
    payees = [Payee(name=n, account_number=f"20{i:08d}", bank_name=b, amount=15_000)
              for i, (n, b) in enumerate([("Fatima Abubakar", "Access Bank"), ("John Adeyemi", "GTBank"),
                                          ("Blessing Okon", "Zenith Bank"), ("Sani Lawal", "First Bank"),
                                          ("Mary Johnson", "UBA"), ("Ahmed Bala", "Access Bank"),
                                          ("Chioma Nnaji", "GTBank"), ("Yusuf Garba", "Zenith Bank"),
                                          ("Esther Musa", "Fidelity Bank"), ("Ibrahim Ali", "GTBank"),
                                          ("Ruth Danladi", "UBA"), ("Peter Okeke", "First Bank")], 1)]
    r = s.raise_(34, "musa", vendor="Community health volunteers (12)", amount=180_000,
                 category="stipends", grant="MNH-26", payees=payees,
                 description="Monthly stipends, safe-delivery volunteers, August")
    s.pay(s.approve(r, 33), 31)

    # ── September ───────────────────────────────────────────────────────────
    r = s.raise_(28, "aisha", vendor="Harbour Medical Stores", amount=740_000, category="supplies",
                 grant="MNH-26", description="Clean delivery kits x 200 (three quotes attached)")
    s.pay(s.approve(r, 27), 25)

    # Declined by the ED.
    r = s.raise_(24, "grace", vendor="Crestline Office Supplies", amount=1_200_000, category="equipment",
                 description="Four laptops for the HR team")
    r = s.approve(r, 23, until="ed")
    s.decide(r, 22, rq.Decision.DECLINED, "Not in this year's budget. Bring it back with the 2027 plan.")

    r = s.raise_(21, "grace", vendor="Abuja Electricity Distribution Plc", amount=64_000,
                 category="utilities", description="Office electricity, August")
    s.pay(s.approve(r, 20), 19)

    # Advances: Aisha's is never retired (overdue); Musa's is retired on time.
    r = s.raise_(18, "aisha", vendor="Aisha Bello", amount=120_000, category="advance",
                 description="Cash advance for community dialogue refreshments, Kafanchan")
    s.pay(s.approve(r, 17.5), 17)

    r = s.raise_(16, "musa", vendor="Musa Danjuma", amount=150_000, category="dsa",
                 description="DSA, supervision trip to Katsina (4 nights)",
                 activity_end=(dt.date.today() - dt.timedelta(days=11)).isoformat())
    s.pay(s.approve(r, 15.5), 15)
    adv = next(a for a in advances.list_advances(DEMO_ORG) if a.source_ref == r.ref)
    s.clock.at(8, 12)
    advances.retire(DEMO_ORG, adv.id, spent=142_500, actor=_email("ngozi"),
                    note="Receipts and trip report checked; N7,500 refunded to the project account.")

    # ── this week and last: something waiting at every step ─────────────────
    r = s.raise_(7, "musa", vendor="Swift Movers Ltd", amount=95_000, category="transport",
                 grant="MNH-26", description="Bus hire, ward meetings")
    r = s.approve(r, 6.5, until="finance")
    s.decide(r, 6, rq.Decision.RETURNED,
             "Please attach the vehicle log for the last trip and confirm the number of days.")

    r = s.raise_(6, "grace", vendor="Greenfield Conference Centre", amount=510_000, category="venue",
                 description="Staff retreat venue, 2 days")
    r = s.approve(r, 5.5, until="finance")
    s.clock.at(5, 16)
    rq.place_on_hold(DEMO_ORG, r.id, actor=_email("ibrahim"), department="finance",
                     reason="Waiting for the venue's corrected invoice: they charged for 3 days, we booked 2.")

    r = s.raise_(5, "musa", vendor="Pathway Consulting", amount=2_400_000, category="consultancy",
                 description="Endline survey, community TB project")
    s.approve(r, 4.5, until="ed")                                                 # with the ED

    r = s.raise_(4, "musa", vendor="Crestline Office Supplies", amount=620_000, category="equipment",
                 grant="MNH-26", description="Spare parts for two outreach motorbikes",
                 missing=("three_quotes",))
    s.approve(r, 3.5, until="finance")                                            # blocked: quotes

    r = s.raise_(3, "musa", vendor="Greenfield Conference Centre", amount=380_000, category="venue",
                 description="Hall, quarterly review meeting with LGA health teams")
    s.approve(r, 2.5, until="finance")                                            # with Finance, clean

    r = s.raise_(2, "musa", vendor="Northern Logistics Ltd", amount=140_000, category="transport",
                 grant="YTH-24", description="Vehicle hire, adolescent health follow-up visits")
    s.approve(r, 1.5, until="finance")                                            # blocked: grant closed

    # Aisha hasn't retired last month's advance, so her new request is blocked
    # until she does: the advance policy doing its job, on screen.
    s.raise_(1, "aisha", vendor="Kano Print House", amount=88_000, category="supplies",
             description="Printing, 500 referral forms")                           # budget holder, blocked
    s.raise_(0, "grace", vendor="SafeWorks Training Ltd", amount=210_000, category="training",
             description="Fire safety training for office staff")                 # budget holder (HR)
    s.raise_(0, "musa", vendor="Kaduna Water Services", amount=45_000, category="supplies",
             description="Drinking water for outreach teams", submit=False)        # draft


# ─── entry points ─────────────────────────────────────────────────────────────


def seed(*, password: str, reset: bool = False) -> dict:
    import auth
    import org_config
    import store

    org = (os.environ.get("DOCEX_ORG") or "").strip()
    if org != DEMO_ORG:
        raise SystemExit(f"demo_seed only writes to the '{DEMO_ORG}' organisation "
                         f"(DOCEX_ORG is '{org or 'unset'}'). Nothing was written.")
    if len(password or "") < 10:
        raise SystemExit("Give the demo password with --password or DEMO_PASSWORD (10+ characters).")

    db = store.get_store()
    if reset:
        db.delete_org(DEMO_ORG)
    elif db.list(DEMO_ORG, "requisitions"):
        raise SystemExit("The demo already has data. Re-run with --reset to start it again.")

    profile = json.loads(PROFILE.read_text())
    clock = _Clock()
    with _moved_clock(clock):
        clock.at(70, fresh=True)
        org_config.apply_profile(profile)
        for local, name, dept, role, _title in PEOPLE:
            auth.create_user(_email(local), name, password, dept, role, org_id=DEMO_ORG)
        _tell(_Story(clock))

    return {"org": DEMO_ORG, "logins": [(_email(p[0]), p[4]) for p in PEOPLE]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the fictional demo organisation.")
    ap.add_argument("--password", default=os.environ.get("DEMO_PASSWORD", ""),
                    help="password for every demo login (or set DEMO_PASSWORD)")
    ap.add_argument("--reset", action="store_true", help="wipe the demo organisation first")
    ap.add_argument("--statement", default="",
                    help="also write this month's matching bank statement (CSV) to this path, "
                         "for the reconciliation part of a demo")
    args = ap.parse_args()

    org = (os.environ.get("DOCEX_ORG") or "").strip()
    if org != DEMO_ORG:
        print(f"Refusing: demo_seed only writes to the '{DEMO_ORG}' organisation, "
              f"and DOCEX_ORG is '{org or 'unset'}'. Nothing was written.", file=sys.stderr)
        return 2
    if len(args.password or "") < 10:
        print("Refusing: give the demo password with --password or DEMO_PASSWORD "
              "(10+ characters). No password is ever stored in the code.", file=sys.stderr)
        return 2

    import store
    where = store.configure_from_env(quiet=True)
    summary = seed(password=args.password, reset=args.reset)
    import requisitions as rq
    reqs = rq.list_requisitions(DEMO_ORG)
    print(f"Seeded Riverbend Health Foundation into {where}: {len(reqs)} requests.")
    print("Logins (all use the password you gave):")
    for email, title in summary["logins"]:
        print(f"  {email:32} {title}")
    if args.statement:
        import make_demo_statement
        # The month of the latest payment, not "this month": seeded on the 1st,
        # this month would have no payments in it yet.
        latest = max(t.paid_at for t in rq.list_transactions(DEMO_ORG))[:7]
        csv_text, stats = make_demo_statement.build(DEMO_ORG, latest)
        Path(args.statement).write_text(csv_text, encoding="utf-8")
        print(f"Bank statement for {stats['period']}: {args.statement} "
              f"({stats['matched_payments']} payments that match, 1 transfer nobody approved, "
              f"2 bank charges, 2 credits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
