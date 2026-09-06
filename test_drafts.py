"""
Draft requisition tests.

A draft is work in progress, not a commitment. The distinction matters in three
places, and each is a test below: a draft must not enter anyone's approval
queue, must not count as a duplicate against a real payment, and must not be
editable once it stops being a draft — changing an amount underneath an
approver is what the audit trail exists to prevent.

Run: python test_drafts.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-drafts-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import requisitions as rq  # noqa: E402

ORG = "draftco"
_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def expect_error(label: str, fn) -> None:
    try:
        fn()
        check(label, False)
    except rq.RequisitionError:
        check(label, True)


def setup() -> None:
    wf = rq.default_workflow(ORG, "medium")
    wf.max_amount = 1_000_000
    wf.allowed_categories = ["supplies", "travel"]
    rq.set_workflow(ORG, wf)


def new_draft(**kw) -> rq.Requisition:
    args = dict(submitted_by="amina@draftco.org", department="program",
                vendor_name="Sahel Supplies", amount=50_000,
                category="supplies", submit=False)
    args.update(kw)
    return rq.create_requisition(ORG, **args)


def test_a_draft_is_not_a_submission() -> None:
    print("\nA draft stays out of everyone's queue")
    d = new_draft()
    check("status is draft", d.status == rq.ReqStatus.DRAFT)
    check("not parked on any step", d.current_step is None)
    check("has a reference already", d.ref.startswith("REQ-"))
    check("checks still ran", len(d.checks) > 0)

    pending = rq.list_requisitions(ORG, status=rq.ReqStatus.IN_REVIEW)
    check("invisible to the review queue", d.id not in [r.id for r in pending])
    drafts = rq.list_requisitions(ORG, status=rq.ReqStatus.DRAFT)
    check("visible in the draft list", d.id in [r.id for r in drafts])


def test_checks_run_on_every_edit() -> None:
    print("\nEditing re-runs the checks, so problems surface while typing")
    d = new_draft(amount=50_000)
    clean = [c for c in d.checks if c.result == rq.CheckResult.FAIL]
    check("starts clean", not clean)

    # Push it over the org's ceiling.
    d = rq.update_draft(ORG, d.id, actor="amina@draftco.org", amount=5_000_000)
    fails = [c for c in d.checks if c.result == rq.CheckResult.FAIL]
    check("over-ceiling amount now fails a check", bool(fails))
    check("amount was actually updated", d.amount == 5_000_000)

    # Bring it back down.
    d = rq.update_draft(ORG, d.id, actor="amina@draftco.org", amount=40_000)
    fails = [c for c in d.checks if c.result == rq.CheckResult.FAIL]
    check("lowering it clears the failure", not fails)

    d = rq.update_draft(ORG, d.id, actor="amina@draftco.org", vendor_name="New Vendor Ltd")
    check("vendor updated", d.vendor_name == "New Vendor Ltd")
    check("edit is in the audit trail",
          any(e.event == "draft_edited" for e in d.audit_log))
    check("audit chain still verifies", rq.verify_audit_chain(d))


def test_submitting_a_draft() -> None:
    print("\nSubmitting moves it into the chain, after re-checking")
    d = new_draft(amount=60_000)
    d = rq.submit_draft(ORG, d.id, actor="amina@draftco.org")
    check("now in review", d.status == rq.ReqStatus.IN_REVIEW)
    check("parked on the first step", d.current_step is not None)
    check("re-check recorded at submit",
          any("re-checked at submit" in e.detail for e in d.audit_log))
    expect_error("cannot submit twice",
                 lambda: rq.submit_draft(ORG, d.id, actor="amina@draftco.org"))


def test_a_submitted_requisition_cannot_be_edited() -> None:
    print("\nOnce submitted, the figures are frozen for the approver")
    d = rq.submit_draft(ORG, new_draft().id, actor="amina@draftco.org")
    expect_error("editing a submitted requisition is refused",
                 lambda: rq.update_draft(ORG, d.id, actor="x", amount=1))
    expect_error("deleting a submitted requisition is refused",
                 lambda: rq.discard_draft(ORG, d.id, actor="x"))
    try:
        rq.update_draft(ORG, d.id, actor="x", amount=1)
    except rq.RequisitionError as exc:
        check("the refusal explains why", "approver" in str(exc).lower())


def test_incomplete_drafts_cannot_be_submitted() -> None:
    print("\nAn incomplete draft is caught at submit, not by an approver")
    d = new_draft(vendor_name="", amount=0)
    expect_error("no vendor is refused",
                 lambda: rq.submit_draft(ORG, d.id, actor="a"))
    rq.update_draft(ORG, d.id, actor="a", vendor_name="Someone Ltd")
    expect_error("zero amount is refused",
                 lambda: rq.submit_draft(ORG, d.id, actor="a"))
    rq.update_draft(ORG, d.id, actor="a", amount=1000)
    ok = rq.submit_draft(ORG, d.id, actor="a")
    check("submits once complete", ok.status == rq.ReqStatus.IN_REVIEW)


def test_drafts_never_count_as_duplicates() -> None:
    print("\nA draft is not a commitment, so it never blocks a real payment")
    # Two drafts for the same vendor and amount are normal — someone is
    # preparing a batch. Treating them as duplicates would make the feature
    # unusable.
    a = new_draft(vendor_name="Repeat Ltd", amount=77_000)
    b = new_draft(vendor_name="Repeat Ltd", amount=77_000)
    dups = [c for c in b.checks
            if "DUPLICATE" in c.code.upper()
            and c.result != rq.CheckResult.PASS]
    check("a second draft is not flagged as a duplicate", not dups)

    # But once one is submitted, the next real one should notice.
    rq.submit_draft(ORG, a.id, actor="a")
    live = rq.create_requisition(
        ORG, submitted_by="a", department="program",
        vendor_name="Repeat Ltd", amount=77_000, category="supplies")
    flagged = [c for c in live.checks
               if "DUPLICATE" in c.code.upper()
               and c.result != rq.CheckResult.PASS]
    check("a submitted one IS noticed by the next", bool(flagged))


def test_discarding() -> None:
    print("\nDrafts can be thrown away; records cannot")
    d = new_draft()
    check("discarded", rq.discard_draft(ORG, d.id, actor="a") is True)
    check("gone", rq.get_requisition(ORG, d.id) is None)
    check("discarding nothing is not an error",
          rq.discard_draft(ORG, "no-such-id", actor="a") is False)


def main() -> int:
    print("=" * 64)
    print("Drafts — work in progress, not a commitment")
    print("=" * 64)
    setup()
    test_a_draft_is_not_a_submission()
    test_checks_run_on_every_edit()
    test_submitting_a_draft()
    test_a_submitted_requisition_cannot_be_edited()
    test_incomplete_drafts_cannot_be_submitted()
    test_drafts_never_count_as_duplicates()
    test_discarding()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
