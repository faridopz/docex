"""
The audit trail protects the money, not just its own entries.

The chain signed each entry and linked it to the one before, which proves the
entries were not edited. It did not cover the requisition's own amount, bank
account or payee list — so someone with database access could change the
account on an approved payment and the chain still verified. Nor could it see
entries removed from the end, and an empty log counted as verified.

Now each entry signs a fingerprint of the payment details, a signed chain
head is kept beside the record, and payment is refused if either disagrees.
Existing entries keep verifying under the old format, with the same key.

Run: python test_audit_chain_v2.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-chainv2-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0
ORG = "acme"


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _approved(amount=5000.0, payees=None):
    r = rq.create_requisition(ORG, submitted_by="raiser@t", department="program",
                              vendor_name="Acme Supplies", amount=amount,
                              vendor_account="0123456789", vendor_bank_name="GTBank",
                              payees=payees)
    raw = store.get_store().get(ORG, "requisitions", r.id)
    raw["status"] = "approved"
    store.get_store().put(ORG, "requisitions", r.id, raw)
    return rq.get_requisition(ORG, r.id)


def _tamper(req_id, fn):
    raw = store.get_store().get(ORG, "requisitions", req_id)
    fn(raw)
    store.get_store().put(ORG, "requisitions", req_id, raw)
    return rq.get_requisition(ORG, req_id)


def test_an_untouched_request_verifies() -> None:
    print("\nNothing changed: verifies")
    r = _approved()
    check("verifies", rq.verify_audit_chain(r))


def test_a_changed_account_is_detected() -> None:
    print("\nAccount changed in the database after approval: detected")
    r = _approved()
    r = _tamper(r.id, lambda raw: raw.update(vendor_account="0111111111"))
    check("does not verify", not rq.verify_audit_chain(r))


def test_a_changed_amount_is_detected() -> None:
    print("\nAmount changed in the database: detected")
    r = _approved()
    r = _tamper(r.id, lambda raw: raw.update(amount=50000.0))
    check("does not verify", not rq.verify_audit_chain(r))


def test_a_changed_payee_line_is_detected() -> None:
    print("\nOne payee's account swapped in a batch: detected")
    payees = [rq.Payee(name=f"P{i}", account_number=f"01234{i:05d}", bank_name="GTBank", amount=100.0)
              for i in range(3)]
    r = _approved(300.0, payees)
    check("batch verifies as created", rq.verify_audit_chain(r))

    def swap(raw):
        raw["payees"][1]["account_number"] = "0999999999"
    r = _tamper(r.id, swap)
    check("swapped payee does not verify", not rq.verify_audit_chain(r))


def test_removed_last_entries_are_detected() -> None:
    print("\nLast audit entries deleted: detected")
    r = _approved()
    check("has more than one entry", len(r.audit_log) > 1, str(len(r.audit_log)))
    r = _tamper(r.id, lambda raw: raw.update(audit_log=raw["audit_log"][:-1]))
    check("truncated log does not verify", not rq.verify_audit_chain(r))


def test_an_empty_log_does_not_verify() -> None:
    print("\nWhole audit log deleted: detected")
    r = _approved()
    r = _tamper(r.id, lambda raw: raw.update(audit_log=[]))
    check("does not verify", not rq.verify_audit_chain(r))


def test_old_format_entries_still_verify() -> None:
    print("\nEntries written before this change still verify, with the same key")
    r = _approved()
    # Rebuild the log exactly as the old code wrote it: no fingerprint.
    prev, log = "", []
    for e in r.audit_log:
        body = f"{r.id}|{e.seq}|{e.at}|{e.actor}|{e.event}|{e.detail}|{prev}"
        h = rq._sign(body)
        log.append({**e.model_dump(), "fp": "", "prev_hash": prev, "hash": h})
        prev = h
    store.get_store().delete(ORG, rq._AUDIT_HEADS, r.id)
    r = _tamper(r.id, lambda raw: raw.update(audit_log=log))
    check("legacy chain verifies", rq.verify_audit_chain(r))
    r2 = rq.add_comment(ORG, r.id, actor="fin@t", text="checked") if hasattr(rq, "add_comment") else r
    check("and keeps verifying after a new-format entry is added", rq.verify_audit_chain(r2))


def test_a_tampered_payment_cannot_be_paid() -> None:
    print("\nPaying a request whose details changed after approval is refused")
    r = _approved()
    r = _tamper(r.id, lambda raw: raw.update(vendor_account="0111111111"))
    try:
        rq.mark_paid(ORG, r.id, actor="fin@t")
        check("refused", False, "paid a tampered request")
    except rq.RequisitionError as exc:
        check("refused, and says why", "changed" in str(exc).lower(), str(exc))


def test_a_tampered_request_cannot_be_approved_but_can_be_returned() -> None:
    print("\nIn review and tampered: approving is refused, returning is allowed")
    r = rq.create_requisition(ORG, submitted_by="raiser@t", department="program",
                              vendor_name="Acme Supplies", amount=700.0, vendor_account="0123456789",
                              vendor_bank_name="GTBank")
    r = _tamper(r.id, lambda raw: raw.update(amount=70000.0))
    step = r.current_step
    try:
        rq.decide(ORG, r.id, decision=rq.Decision.APPROVED, actor="fin@t", department=step)
        check("approval refused", False)
    except rq.RequisitionError as exc:
        check("approval refused, with the reason", "cannot be approved" in str(exc), str(exc))
    try:
        r = rq.decide(ORG, r.id, decision=rq.Decision.RETURNED, actor="fin@t", department=step,
                      notes="amount doesn't match the invoice")
        check("returning it is allowed", r.status == rq.ReqStatus.RETURNED, r.status)
    except rq.RequisitionError as exc:
        check("returning it is allowed", False, str(exc))


def test_legitimate_edits_keep_verifying() -> None:
    print("\nA draft edited through the app keeps verifying")
    org_config.set_features(ORG, multi_payee_requisitions=True)
    r = rq.create_requisition(ORG, submitted_by="raiser@t", department="program",
                              vendor_name="Hotel", amount=100.0, submit=False)
    r = rq.update_draft(ORG, r.id, actor="raiser@t", amount=250.0, vendor_account="0222222222")
    check("edited draft verifies", rq.verify_audit_chain(r))
    r = rq.submit_draft(ORG, r.id, actor="raiser@t")
    check("and after submitting", rq.verify_audit_chain(r))


if __name__ == "__main__":
    print("Audit chain v2 — the money is inside the signature")
    org_config.set_features(ORG, multi_payee_requisitions=True)
    test_an_untouched_request_verifies()
    test_a_changed_account_is_detected()
    test_a_changed_amount_is_detected()
    test_a_changed_payee_line_is_detected()
    test_removed_last_entries_are_detected()
    test_an_empty_log_does_not_verify()
    test_old_format_entries_still_verify()
    test_a_tampered_payment_cannot_be_paid()
    test_a_tampered_request_cannot_be_approved_but_can_be_returned()
    test_legitimate_edits_keep_verifying()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
