"""
Cross-engine integration — do the engines actually talk to each other?

Each engine passes its own suite. That is not the same as the seams between
them holding. These tests walk a real payment across module boundaries and
check the controls that only exist *between* engines:

  * field_receipts -> requisitions: a receipt cited on a payment must exist,
    belong to this org, not have been rejected, and above all not already be
    claimed on another payment. Reimbursing one receipt twice is a textbook
    duplicate-claim, and the vendor+amount duplicate check cannot see it.
  * grants -> requisitions: a cost charged to a grant must fall inside that
    agreement's period. Charging outside the budget period is one of the most
    common audit findings in donor-funded work.
  * fast_extract -> field_receipts -> requisitions: a real file becomes a
    receipt becomes a payment, with the amount surviving intact.

Run: python test_engine_integration.py
"""
from __future__ import annotations

import io
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-integ-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import field_receipts as fr  # noqa: E402
import grants  # noqa: E402
import requisitions as rq  # noqa: E402

ORG = "integration-org"
OTHER = "someone-elses-org"

_passed = 0
_failed = 0


def check(label: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def _find(req: rq.Requisition, code: str):
    return next((c for c in req.checks if c.code == code), None)


def _receipt(org: str, amount: float, name: str = "receipt.txt") -> fr.ReceiptLine:
    body = f"MAMA NGOZI PROVISIONS\nDATE: 2026-08-15\nTOTAL: {amount:,.2f}\n"
    return fr.upload_receipt(
        org_id=org, uploaded_by="fw@x.org", file_content=body.encode(),
        filename=name, amount_submitted=amount,
        project_code="P-101", category="supplies",
    )


def _raise(org: str, **kw) -> rq.Requisition:
    base = dict(
        submitted_by="officer@x.org", department="programs",
        vendor_name="Sahel Catering", amount=50000.0, category="supplies",
        project_code="P-101",
    )
    base.update(kw)
    return rq.create_requisition(org, **base)


# ─── receipts must be real ──────────────────────────────────────────────────


def test_unknown_receipt_blocks() -> None:
    print("\nA receipt id that matches nothing blocks the payment")
    req = _raise(ORG, receipt_ids=["rcp-does-not-exist"])
    c = _find(req, "RECEIPTS_VALID")
    check("check is present", c is not None)
    check("it fails", c is not None and c.result == rq.CheckResult.FAIL)
    check("it says the receipt was not found",
          c is not None and "not found" in (c.message or "").lower())


def test_valid_receipt_passes() -> None:
    print("\nA genuine, unclaimed receipt passes")
    r = _receipt(ORG, 50000)
    req = _raise(ORG, receipt_ids=[r.id])
    c = _find(req, "RECEIPTS_VALID")
    check("check passes", c is not None and c.result == rq.CheckResult.PASS)
    check("no blocking failures", len(rq.blocking_checks(req)) == 0)


def test_double_claim_is_caught() -> None:
    print("\nThe same receipt cannot back two payments (duplicate claim)")
    r = _receipt(ORG, 75000)

    first = _raise(ORG, amount=75000.0, receipt_ids=[r.id])
    check("first claim is clean",
          _find(first, "RECEIPTS_VALID").result == rq.CheckResult.PASS)

    # Different vendor AND different amount, so the vendor+amount duplicate
    # check is blind to it. Only the receipt link catches this.
    second = _raise(ORG, vendor_name="Totally Different Ltd",
                    amount=12345.0, receipt_ids=[r.id])
    c = _find(second, "RECEIPTS_VALID")
    check("second claim fails", c is not None and c.result == rq.CheckResult.FAIL)
    check("it names the requisition already holding it",
          c is not None and first.ref in (c.actual_value or ""))
    check("it blocks payment", any(
        x.code == "RECEIPTS_VALID" for x in rq.blocking_checks(second)))


def test_declined_requisition_releases_its_receipts() -> None:
    print("\nA declined requisition does not keep holding its receipts")
    r = _receipt(ORG, 31000)
    first = _raise(ORG, amount=31000.0, receipt_ids=[r.id])
    rq.decide(ORG, first.id, decision=rq.Decision.DECLINED,
              actor="approver@x.org", department="finance", notes="Wrong vendor")

    retry = _raise(ORG, amount=31000.0, receipt_ids=[r.id])
    c = _find(retry, "RECEIPTS_VALID")
    check("the receipt is claimable again",
          c is not None and c.result == rq.CheckResult.PASS)


def test_rejected_receipt_blocks() -> None:
    print("\nA receipt finance already rejected cannot back a payment")
    # Only a FLAGGED receipt can be resolved, so give this one a real problem
    # (no vendor) — which is also how a rejected receipt arises in practice.
    r = fr.upload_receipt(
        org_id=ORG, uploaded_by="fw@x.org",
        file_content=b"DATE: 2026-08-15\nTOTAL: 9,000.00\n",
        filename="no_vendor.txt", amount_submitted=9000.0,
        project_code="P-101", category="supplies",
    )
    check("receipt is flagged before rejection",
          r.status == fr.ReceiptStatus.FLAGGED)
    fr.resolve_flags(org_id=ORG, receipt_id=r.id, decision="rejected",
                     reviewed_by="finance@x.org", notes="Not a valid expense")
    req = _raise(ORG, amount=9000.0, receipt_ids=[r.id])
    c = _find(req, "RECEIPTS_VALID")
    check("it fails", c is not None and c.result == rq.CheckResult.FAIL)
    check("it says the receipt was rejected",
          c is not None and "rejected" in (c.message or "").lower())


def test_another_orgs_receipt_is_not_usable() -> None:
    print("\nOne org cannot cite another org's receipt")
    theirs = _receipt(OTHER, 60000)
    req = _raise(ORG, amount=60000.0, receipt_ids=[theirs.id])
    c = _find(req, "RECEIPTS_VALID")
    check("it fails", c is not None and c.result == rq.CheckResult.FAIL)
    # It must read as "not found" — confirming existence would leak that
    # another organisation holds that record.
    check("it does not confirm the receipt exists elsewhere",
          c is not None and "not found" in (c.message or "").lower())


# ─── grant period ───────────────────────────────────────────────────────────


def test_cost_outside_agreement_period_fails() -> None:
    print("\nA cost charged outside the agreement period is caught")
    grants.add_agreement(
        ORG, id="agr-closed", donor="FCDO", project_code="GF-CLOSED",
        title="Closed grant", value=5_000_000, currency="NGN",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    req = _raise(ORG, grant_code="GF-CLOSED")
    c = _find(req, "GRANT_PERIOD")
    check("check is present", c is not None)
    check("it fails", c is not None and c.result == rq.CheckResult.FAIL)
    check("it states the period",
          c is not None and "2024-12-31" in (c.policy_value or ""))
    check("it blocks payment",
          any(x.code == "GRANT_PERIOD" for x in rq.blocking_checks(req)))


def test_cost_inside_agreement_period_passes() -> None:
    print("\nA cost inside the period passes")
    grants.add_agreement(
        ORG, id="agr-open", donor="Global Fund", project_code="GF-OPEN",
        title="Active grant", value=9_000_000, currency="NGN",
        start_date="2020-01-01", end_date="2099-12-31",
    )
    req = _raise(ORG, grant_code="GF-OPEN")
    c = _find(req, "GRANT_PERIOD")
    check("it passes", c is not None and c.result == rq.CheckResult.PASS)


def test_unknown_grant_warns_but_does_not_block() -> None:
    print("\nAn unrecognised grant code warns rather than blocks")
    req = _raise(ORG, grant_code="NOT-A-REAL-GRANT")
    c = _find(req, "GRANT_PERIOD")
    check("it warns", c is not None and c.result == rq.CheckResult.WARNING)
    check("it does not block",
          not any(x.code == "GRANT_PERIOD" for x in rq.blocking_checks(req)))


def test_no_grant_code_skips_the_check() -> None:
    print("\nNo grant cited means no period check to run")
    req = _raise(ORG, grant_code=None)
    check("check is absent", _find(req, "GRANT_PERIOD") is None)


# ─── file -> receipt -> payment ─────────────────────────────────────────────


def test_file_becomes_a_payment_with_the_right_amount() -> None:
    print("\nA real file becomes a payment with its amount intact")
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in [["Vendor:", "Sahel Catering"], ["Date:", "2026-08-14"], [],
                ["", "SUBTOTAL", 375000], ["", "VAT 7.5%", 28125],
                ["", "TOTAL", 403125]]:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)

    r = fr.upload_receipt(
        org_id=ORG, uploaded_by="fw@x.org", file_content=buf.getvalue(),
        filename="voucher.xlsx", amount_submitted=403125.0,
        project_code="P-101", category="supplies",
    )
    check("the spreadsheet's TOTAL was read, not its SUBTOTAL",
          r.extracted.extracted_amount == 403125.0)

    req = _raise(ORG, amount=403125.0, vendor_name="Sahel Catering",
                 receipt_ids=[r.id])
    check("it becomes a requisition for the same amount", req.amount == 403125.0)
    check("the receipt backs it cleanly",
          _find(req, "RECEIPTS_VALID").result == rq.CheckResult.PASS)


def main() -> int:
    print("=" * 64)
    print("Cross-engine integration — the seams between modules")
    print("=" * 64)

    test_unknown_receipt_blocks()
    test_valid_receipt_passes()
    test_double_claim_is_caught()
    test_declined_requisition_releases_its_receipts()
    test_rejected_receipt_blocks()
    test_another_orgs_receipt_is_not_usable()
    test_cost_outside_agreement_period_fails()
    test_cost_inside_agreement_period_passes()
    test_unknown_grant_warns_but_does_not_block()
    test_no_grant_code_skips_the_check()
    test_file_becomes_a_payment_with_the_right_amount()

    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
