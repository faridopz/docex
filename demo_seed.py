#!/usr/bin/env python3
"""
Seed a realistic NEEM demo. One command, repeatable, safe to re-run.

    python demo_seed.py                  # seed + create the demo login
    python demo_seed.py --reset          # wipe demo data first, then seed

Why this exists: empty screens demo badly. A queue with nothing in it, an
audit page reading "0 exceptions", a payments list with no rows — none of that
shows what the product does. This populates every screen with data an NGO
finance officer would recognise, and deliberately leaves ONE requisition
sitting in the approval queue with a blocking check, so the override flow can
be walked live rather than described.

Everything here is fictional. Vendors, staff and grant codes are invented.

Creates:
  * a login you can actually use            (demo@neem.org)
  * an approval chain that routes correctly (Compliance → Finance → Management)
  * a funding agreement, so grant-period checks have something to check
  * field receipts, including one PHOTOGRAPH that gets read by OCR
  * requisitions across every state: clean and waiting, blocked and waiting,
    paid cleanly, and paid over an override that the audit page will report
"""
from __future__ import annotations

import argparse
import getpass
import io
import os
import sys
from datetime import datetime, timedelta, timezone

# Select the SAME storage backend api/main.py will use. Without this the seeder
# writes into the default JSON store while the running API reads SQLite, so the
# demo login it just created does not exist as far as the API is concerned —
# and the failure surfaces as a 401 at the login screen, which looks like a
# password problem rather than a storage one.
import store as _store
_store.configure_from_env(quiet=True)

# Read the org from the environment, exactly as the API does. Hard-coding
# "default" here while auth.create_user() reads DOCEX_ORG split the demo across
# two organisations the moment anyone ran this with DOCEX_ORG set: the login
# landed in one org and every requisition in the other, so the seeded account
# signed in successfully to a completely empty system. Nothing errored — which
# is what made it expensive.
ORG = (os.environ.get("DOCEX_ORG") or "default").strip() or "default"
DEMO_EMAIL = "demo@neem.org"


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ─── fixtures ───────────────────────────────────────────────────────────────


def _receipt_text(vendor: str, date: str, total: float) -> bytes:
    return (
        f"{vendor}\nDATE: {date}\nCommunity outreach supplies\n"
        f"TOTAL: {total:,.2f}\n"
    ).encode()


def _receipt_photo(vendor: str, date: str, total: float) -> bytes:
    """A phone photo of a market receipt — no text layer, OCR only.

    This is the NEEM story in one file: the fieldworker photographs a hand-
    written receipt in a market with no signal, and the system still reads it.
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 560), "white")
    dr = ImageDraw.Draw(img)
    lines = [vendor, f"DATE: {date}", "", "Exercise books x40",
             "Pens and markers", "", f"TOTAL: {total:,.2f}"]
    for i, t in enumerate(lines):
        dr.text((45, 45 + i * 62), t, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── seeding ────────────────────────────────────────────────────────────────


def seed(reset: bool) -> int:
    import store
    import auth
    import departments
    import field_receipts as fr
    import grants
    import requisitions as rq

    db = store.get_store()

    if reset:
        # Collection names come from the modules themselves. Hard-coding them
        # here got "field_receipts" wrong (it was "receipts"), so receipts
        # silently piled up on every --reset while the message claimed
        # everything was cleared.
        cleared = 0
        for coll in ("requisitions", "transaction_records",
                     fr._RECEIPTS, grants._AGREEMENTS,
                     "idempotency_keys"):
            for rec in db.list(ORG, coll):
                rid = rec.get("id")
                if rid and db.delete(ORG, coll, rid):
                    cleared += 1

        # These are singletons stored under fixed record ids rather than
        # carrying an "id" field, so the loop above cannot see them. Without
        # this the reference counter keeps climbing and a "fresh" demo opens
        # at REQ-0009.
        for rid in ("requisition", "transaction"):
            db.delete(ORG, rq._COUNTER, rid)
        db.delete(ORG, "requisition_workflow", rq._WORKFLOW_ID)

        print(f"· cleared {cleared} record(s); references restart at REQ-0001")

    # 1. Departments — the defaults already match the workflow below.
    known = {d.key for d in departments.list_departments()}
    print(f"· departments: {', '.join(sorted(known))}")

    # 1b. Feature flags. The nav is driven by these, so a screen that is not
    #     switched on here simply does not exist for the demo — which is a
    #     confusing thing to discover with a client watching. Set explicitly
    #     rather than relying on whatever the last profile applied left behind.
    _store.get_store().put(ORG, "config", "features", {
        "modules": ["compliance", "extraction", "knowledge"],
        "features": {
            "bank_reconciliation": True,   # NEEM asked for this by name
            "timesheets": True,
            "tin_verification": True,
            "payroll": False,              # no confirmed PAYE bands — see profiles/neem.json
            "legacy_intake": False,
        },
    })
    print("· features: reconciliation ON, timesheets ON, payroll OFF")

    # 2. Approval chain. Explicit rather than default_workflow(), so the demo
    #    doesn't depend on which default happens to be current.
    wf = rq.RequisitionWorkflow(
        org_id=ORG,
        currency="NGN",
        max_amount=500_000,
        allowed_categories=["supplies", "training", "travel", "logistics",
                            "venue", "stipend", "communications"],
        required_documents=["receipt", "invoice"],
        duplicate_window_days=30,
        # Finance FIRST, deliberately.
        #
        # The demo login sits in Finance, and "Waiting on me" filters by the
        # signed-in user's department. With Compliance first, every requisition
        # would queue behind a department nobody is logged into and the demo
        # user's queue would be empty.
        #
        # It also avoids a real constraint in the engine: an approver may not
        # advance a requisition carrying a FAIL they lack the authority to
        # release. So a blocking check has to arrive at a step that CAN clear
        # it, or it can only be declined or returned.
        steps=[
            rq.WorkflowStep(key="finance", label="Finance Review",
                            department="finance",
                            can_override=True, override_limit=150_000),
            rq.WorkflowStep(key="approval", label="Executive Approval",
                            department="management", min_amount=250_000,
                            can_override=True, override_limit=1_000_000),
        ],
    )
    rq.set_workflow(ORG, wf)

    bad = rq.unroutable_steps(ORG, wf)
    if bad:
        print(f"  ! these steps route nowhere: {bad}", file=sys.stderr)
        return 1
    print("· approval chain: Finance → Executive (over ₦250,000)")

    # 3. A live funding agreement, so GRANT_PERIOD has something to check.
    grants.add_agreement(
        ORG, id="agr-neem-2026", donor="Global Fund", project_code="GF-2026-TB",
        title="Community TB Case Finding", value=48_000_000, currency="NGN",
        signed_date="2025-11-02", start_date="2026-01-01", end_date="2026-12-31",
    )
    # A closed one, so the "outside the period" failure can be shown on demand.
    grants.add_agreement(
        ORG, id="agr-neem-2024", donor="FCDO", project_code="FCDO-2024",
        title="Adolescent Health (closed)", value=12_000_000, currency="NGN",
        signed_date="2023-10-01", start_date="2024-01-01", end_date="2024-12-31",
    )
    print("· grants: GF-2026-TB (live), FCDO-2024 (closed — for the period demo)")

    # 4. Field receipts, including the photographed one.
    receipts = {}
    r = fr.upload_receipt(
        org_id=ORG, uploaded_by="amina.field@neem.org",
        file_content=_receipt_text("SAHEL CATERING SERVICES", "2026-08-20", 96_000),
        filename="catering_kano.txt", amount_submitted=96_000,
        project_code="GF-2026-TB", category="training",
    )
    receipts["catering"] = r

    r = fr.upload_receipt(
        org_id=ORG, uploaded_by="amina.field@neem.org",
        file_content=_receipt_photo("MAMA NGOZI PROVISIONS", "2026-08-21", 47_500),
        filename="market_receipt.png", amount_submitted=47_500,
        project_code="GF-2026-TB", category="supplies",
    )
    receipts["photo"] = r
    photo_read = r.extracted.extracted_amount
    print(f"· receipts: 3 logged — the photographed one OCR'd to "
          f"{'₦{:,.0f}'.format(photo_read) if photo_read else 'nothing (OCR not installed)'}")

    # A deliberately incomplete one — NEEM's actual pain point.
    fr.upload_receipt(
        org_id=ORG, uploaded_by="amina.field@neem.org",
        file_content=b"DATE: 2026-08-22\nTOTAL: 18,000.00\n",   # no vendor
        filename="transport_no_vendor.txt", amount_submitted=18_000,
        project_code="GF-2026-TB", category="travel",
    )

    def raise_req(**kw) -> rq.Requisition:
        base = dict(
            submitted_by="amina.field@neem.org", department="program",
            currency="NGN", grant_code="GF-2026-TB",
            project_code="GF-2026-TB", documents=["receipt", "invoice"],
        )
        base.update(kw)
        return rq.create_requisition(ORG, **base)

    # 5a. Clean, waiting on Compliance — the happy path in the queue.
    raise_req(vendor_name="Sahel Catering Services", amount=96_000,
              category="training", description="Refreshments, Kano training, 2 days",
              receipt_ids=[receipts["catering"].id])

    # 5b. THE DEMO ONE: blocked and waiting on Finance, at an amount the demo
    #     login has authority to release (₦140,000 ≤ the ₦150,000 limit).
    #     The block is a genuine donor rule — the cost is charged to a grant
    #     that closed in 2024 — which is a far better story than a missing
    #     attachment, and it is exactly the kind of finding an auditor writes up.
    blocked = raise_req(vendor_name="Northern Logistics Ltd", amount=140_000,
                        category="logistics", grant_code="FCDO-2024",
                        project_code="FCDO-2024",
                        description="Vehicle hire, 3 LGAs, September outreach")
    n_blocking = len(rq.blocking_checks(blocked))

    # 5c. Paid cleanly — gives the Payments screen a row with no exceptions.
    clean = raise_req(vendor_name="Zenith Stationers", amount=47_500,
                      category="supplies", description="Exercise books and pens",
                      receipt_ids=[receipts["photo"].id])
    clean = rq.decide(ORG, clean.id, decision=rq.Decision.APPROVED,
                      actor="finance@neem.org", department="finance",
                      notes="Checked against the photographed receipt.")
    rq.mark_paid(ORG, clean.id, actor="finance@neem.org",
                 bank_reference="FT26082100417", department="finance")

    # 5d. Paid OVER an override — this is what the Audit screen exists for.
    exception = raise_req(vendor_name="Kaduna Venue Services", amount=95_000,
                          category="venue", grant_code="FCDO-2024",
                          project_code="FCDO-2024",
                          description="Venue hire, community dialogue")
    exception = rq.decide(
        ORG, exception.id, decision=rq.Decision.APPROVED,
        actor="finance@neem.org", department="finance",
        notes="Released on the Finance Manager's authority.",
        overrides=[c.code for c in rq.blocking_checks(exception)],
        override_reason=("Activity ran in the FCDO close-out window and the cost "
                         "was approved by the donor in writing on 2024-12-18 "
                         "(ref FCDO/CO/2024/331)."),
        override_authority="Finance Manager — delegated authority to ₦150,000")
    rq.mark_paid(ORG, exception.id, actor="finance@neem.org",
                 bank_reference="FT26081900288", department="finance")

    print(f"· requisitions: 4 — one clean in the queue, one BLOCKED with "
          f"{n_blocking} failing check for the live override ({blocked.ref}), two paid")

    summary = rq.audit_summary(ORG)
    print(f"· audit: {summary['exceptions_total']} exception(s), "
          f"audit_ready={summary['audit_ready']}")

    return 0


def ensure_login(password: str | None) -> None:
    import auth

    existing = auth.get_by_email(DEMO_EMAIL)
    if not password:
        # Only prompt when there is a real terminal to prompt on. Run from a
        # script, a CI job, or anywhere stdin isn't a TTY, getpass() blocks
        # forever with no visible prompt — which looks exactly like the seeder
        # hanging, and cost an evening before anyone noticed it was waiting
        # for input rather than generating data.
        if sys.stdin is not None and sys.stdin.isatty():
            password = getpass.getpass(f"Password for {DEMO_EMAIL} (min 6 chars): ")
        else:
            print("error: no terminal available to prompt for a password.\n"
                  "       Pass one explicitly:  python3 demo_seed.py --password '<something>'",
                  file=sys.stderr)
            raise SystemExit(1)
    if len(password) < 6:
        print("error: password must be at least 6 characters.", file=sys.stderr)
        raise SystemExit(1)

    if existing:
        pw_hash, pw_salt = auth.hash_password(password)
        existing.password_hash, existing.password_salt = pw_hash, pw_salt
        existing.role, existing.active = "admin", True
        auth._save(existing)
        print(f"· login reset: {DEMO_EMAIL} (admin, finance)")
    else:
        auth.create_user(email=DEMO_EMAIL, name="NEEM Demo",
                         password=password, department="finance", role="admin")
        print(f"· login created: {DEMO_EMAIL} (admin, finance)")


def main() -> int:
    p = argparse.ArgumentParser(description="Seed the NEEM demo dataset.")
    p.add_argument("--reset", action="store_true",
                   help="Wipe existing demo data before seeding")
    p.add_argument("--password", help="Password for the demo login")
    args = p.parse_args()

    print("Seeding NEEM demo\n" + "─" * 50)
    rc = seed(args.reset)
    if rc:
        return rc
    ensure_login(args.password)

    print("─" * 50)
    print("Ready.\n")
    print("  1. uvicorn api.main:app --reload --port 8000")
    print("  2. cd web && npm run dev")
    print(f"  3. http://localhost:3000/login  →  {DEMO_EMAIL}")
    print("\nThe money shot: Requisitions → the ₦140,000 Northern Logistics")
    print("row → try to Approve. The button stays disabled until you tick the")
    print("blocking check and write a reason and an authority.")
    print("\nKeep every demo amount under ₦150,000 — above ₦250,000 routes to")
    print("Executive Approval, where nobody is logged in, and it will sit there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
