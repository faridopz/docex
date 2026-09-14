"""
Tests for the payment requisition engine.

Run: python test_requisitions.py

Covers:
- Requisition creation + deterministic policy checks
- Approval routing through the org's own workflow
- Decline / return / resubmit
- Policy override: refused without reason, refused without authority,
  refused above the override limit, allowed when all three hold
- Approval blocked while a FAIL is unreleased
- Immutable transaction record + hash-chained audit log
- Auditor summary (every exception explained)
- Org isolation
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import requisitions as rq
import store
import departments

_base = Path(tempfile.mkdtemp(prefix="docex_req_"))
store.set_store(store.JsonFileStore(_base / "data"))

_fail = 0


def check(name, got, want):
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) and isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_err(name, fn):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except Exception:
        print(f"PASS  {name}: raised as expected")


# ─── setup: EVA runs the medium workflow with a real spend policy ───────────

ORG = "eva"
OTHER = "neem"

wf = rq.default_workflow(ORG, size="medium")
wf.max_amount = 100_000
wf.allowed_categories = ["training", "supplies", "travel"]
wf.forbidden_vendors = ["Ghost Traders Ltd"]
wf.required_documents = ["receipt"]
wf.duplicate_window_days = 30
rq.set_workflow(ORG, wf)

loaded = rq.get_workflow(ORG)
check("workflow persisted", loaded.max_amount, 100_000)
check("workflow has 3 steps", len(loaded.steps), 3)

# ─── clean requisition sails through ────────────────────────────────────────

r1 = rq.create_requisition(
    ORG,
    submitted_by="program@eva.org", department="program",
    vendor_name="Supply Store Ltd", amount=75_000,
    category="training", project_code="P-EVA-001",
    grant_code="GR-USAID-2024", vendor_account="UBA 1234567890",
    description="Training materials", documents=["receipt", "quote"],
)

check("ref assigned", r1.ref, "REQ-0001")
check("status in review", r1.status, rq.ReqStatus.IN_REVIEW)
check("parked on compliance", r1.current_step, "compliance")
check("no blocking failures", len(rq.blocking_checks(r1)), 0)
check("audit log started", len(r1.audit_log) >= 3, True)
check("audit chain valid", rq.verify_audit_chain(r1), True)

# compliance approves
# ─── THE ONE THAT MATTERED: only the step's department may act ──────────
#
# This block did not exist, and the engine did not check. A reviewer in
# Programmes could approve the compliance step, then finance, then the
# executive step — the whole chain alone. The approval route was decorative.
#
# Every earlier test drove the chain with the RIGHT actor at each step and
# never asked whether the WRONG one would be refused. That is the difference
# between testing that a control works and testing that it cannot be walked
# around. Only the second one is a test of a control.
expect_err("the submitter's own department cannot approve the compliance step",
    lambda: rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
                      actor="program@eva.org", department="program",
                      notes="Approving my own request."))
expect_err("finance cannot act while it sits with compliance",
    lambda: rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
                      actor="amara@eva.org", department="finance",
                      notes="Jumping the queue."))
expect_err("nor can they decline it out of turn",
    lambda: rq.decide(ORG, r1.id, decision=rq.Decision.DECLINED,
                      actor="amara@eva.org", department="finance"))
check("nothing was recorded by the refused attempts",
      len([a for a in rq.get_requisition(ORG, r1.id).approvals]), 0)
check("still parked on compliance",
      rq.get_requisition(ORG, r1.id).current_step, "compliance")


r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="chioma@eva.org", department="compliance",
               notes="Donor-aligned, documentation complete.")
check("routed to finance", r1.current_step, "finance")

# finance approves → 75k is above the 50k ED threshold, so ED is next
r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="amara@eva.org", department="finance",
               notes="Fund available on GR-USAID-2024.")
check("routed to executive approval", r1.current_step, "approval")

# Every step must name a department that actually exists. The final step used
# to route to "ed", which is not in the department registry — so anything over
# the threshold queued behind a department with no users and sat there
# silently, with nothing in the UI to explain why it never moved.
check("no step routes to a non-existent department",
      rq.unroutable_steps(ORG, rq.get_workflow(ORG)), [])

r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="seun@eva.org", department="management", notes="Approved.")
check("fully approved", r1.status, rq.ReqStatus.APPROVED)
check("no step pending", r1.current_step, None)
check("three approvals recorded", len(r1.approvals), 3)
check("approvals are signed", all(a.signature for a in r1.approvals), True)

# ─── payment freezes an immutable transaction record ────────────────────────

txn = rq.mark_paid(ORG, r1.id, actor="tunde@eva.org", bank_reference="UBA-REF-XYZ123")
check("transaction ref", txn.id, "TRANS-0001")
check("transaction locked", txn.locked, True)
check("transaction amount", txn.amount, 75_000)
check("transaction carries approvals", len(txn.approvals), 3)
check("transaction carries checks", len(txn.checks) > 0, True)
check("no exceptions on clean payment", txn.exceptions_count, 0)

r1_after = rq.get_requisition(ORG, r1.id)
check("requisition now paid", r1_after.status, rq.ReqStatus.PAID)
check("requisition links transaction", r1_after.transaction_id, "TRANS-0001")

expect_err("cannot pay twice", lambda: rq.mark_paid(ORG, r1.id, actor="tunde@eva.org"))

# ─── over-limit requisition FAILS and blocks approval ───────────────────────

r2 = rq.create_requisition(
    ORG,
    submitted_by="program@eva.org", department="program",
    vendor_name="Medical Supplies Co", amount=150_000,
    category="supplies", project_code="P-EVA-002",
    grant_code="GR-USAID-EMERGENCY", documents=["receipt"],
)

blockers = rq.blocking_checks(r2)
check("amount limit failed", any(c.code == "AMOUNT_LIMIT" for c in blockers), True)

expect_err(
    "approval refused while a FAIL is unreleased",
    lambda: rq.decide(ORG, r2.id, decision=rq.Decision.APPROVED,
                      actor="chioma@eva.org", department="compliance"),
)

# compliance cannot override — it has no override authority
expect_err(
    "step without authority cannot override",
    lambda: rq.decide(ORG, r2.id, decision=rq.Decision.APPROVED,
                      actor="chioma@eva.org", department="compliance",
                      overrides=["AMOUNT_LIMIT"], override_reason="Emergency."),
)

# ─── returning a requisition, then resubmitting ─────────────────────────────

r3 = rq.create_requisition(
    ORG, submitted_by="program@eva.org", department="program",
    vendor_name="Office Mart", amount=20_000, category="supplies",
    project_code="P-EVA-003", documents=["receipt"],
)
r3 = rq.decide(ORG, r3.id, decision=rq.Decision.RETURNED,
               actor="chioma@eva.org", department="compliance",
               notes="Attach the delivery note.")
check("returned status", r3.status, rq.ReqStatus.RETURNED)

r3 = rq.resubmit(ORG, r3.id, actor="program@eva.org", notes="Delivery note attached.")
check("resubmitted back into review", r3.status, rq.ReqStatus.IN_REVIEW)
check("resubmitted to first step", r3.current_step, "compliance")

# ─── decline is terminal ────────────────────────────────────────────────────

r4 = rq.create_requisition(
    ORG, submitted_by="program@eva.org", department="program",
    vendor_name="Ghost Traders Ltd", amount=10_000, category="supplies",
    project_code="P-EVA-004", documents=["receipt"],
)
check("blocked vendor fails", any(c.code == "VENDOR_BLOCKED" for c in rq.blocking_checks(r4)), True)

r4 = rq.decide(ORG, r4.id, decision=rq.Decision.DECLINED,
               actor="chioma@eva.org", department="compliance",
               notes="Vendor is on the blocked list.")
check("declined status", r4.status, rq.ReqStatus.DECLINED)
expect_err("cannot act on a declined requisition",
           lambda: rq.decide(ORG, r4.id, decision=rq.Decision.APPROVED, actor="x@eva.org"))

# ─── the override path, done properly ───────────────────────────────────────

# Move r2 to finance, which holds override authority up to 100k... but the
# requisition is 150k, so finance is over its limit and must escalate.
expect_err(
    "override refused above the step's limit",
    lambda: rq.decide(ORG, r2.id, decision=rq.Decision.APPROVED,
                      actor="amara@eva.org", department="finance",
                      overrides=["AMOUNT_LIMIT"],
                      override_reason="USAID emergency grant.",
                      override_authority="Finance"),
)

# Give ED the ball by widening the workflow: ED overrides up to 200k.
# Compliance declines nothing here — we simply route r2 forward by having
# compliance return-then-approve is not needed; instead reconfigure so the
# first step for this amount is ED's peer. Simplest correct path: compliance
# approves only once the FAIL is released by an authorised step, so we raise
# a fresh requisition and send it straight to a workflow whose first step can
# override.
wf_ed_first = rq.default_workflow(ORG, size="medium")
wf_ed_first.max_amount = 100_000
wf_ed_first.allowed_categories = ["training", "supplies", "travel"]
wf_ed_first.steps = [
    rq.WorkflowStep(key="ed", label="Executive Director", department="ed",
                    can_override=True, override_limit=200_000),
]
# A step must route to a department that actually exists — set_workflow now
# enforces this (see requisitions.validate_workflow), the same guard that
# stops the exact bug default_workflow()'s docstring describes: an earlier
# version routed to "ed" with no such department, so anything above the
# threshold sat in the queue forever with no one able to act on it. A real
# org would create this department before configuring the workflow; so does
# this test.
try:
    departments.add("Executive Director", key="ed", is_final_authority=True, org_id=ORG)
except departments.DepartmentError:
    pass  # already created by an earlier run against a reused store
rq.set_workflow(ORG, wf_ed_first)

r5 = rq.create_requisition(
    ORG, submitted_by="program@eva.org", department="program",
    vendor_name="Medical Supplies Co", amount=150_000, category="supplies",
    project_code="P-EVA-005", grant_code="GR-USAID-EMERGENCY",
    documents=["receipt"],
)
check("r5 blocked on amount", any(c.code == "AMOUNT_LIMIT" for c in rq.blocking_checks(r5)), True)

expect_err(
    "override refused without a written reason",
    lambda: rq.decide(ORG, r5.id, decision=rq.Decision.APPROVED,
                      actor="seun@eva.org", department="ed",
                      overrides=["AMOUNT_LIMIT"], override_reason="   "),
)

r5 = rq.decide(
    ORG, r5.id, decision=rq.Decision.APPROVED,
    actor="seun@eva.org", department="ed",
    notes="Emergency procurement authorised.",
    overrides=["AMOUNT_LIMIT"],
    override_reason=("USAID emergency grant received 28 Aug requires expedited "
                     "procurement of medical supplies to meet the donor timeline."),
    override_authority="Executive Director (DOA: up to 200,000 NGN)",
)
check("override cleared the block", r5.status, rq.ReqStatus.APPROVED)

overridden = [c for c in r5.checks if c.overridden]
check("one check overridden", len(overridden), 1)
check("override reason stored", bool(overridden[0].override_reason), True)
check("override authority stored", "Executive Director" in (overridden[0].override_authority or ""), True)
check("override logged in audit trail",
      any(e.event == "policy_override" for e in r5.audit_log), True)
check("audit chain still valid after override", rq.verify_audit_chain(r5), True)

txn5 = rq.mark_paid(ORG, r5.id, actor="tunde@eva.org", bank_reference="UBA-REF-EMG-001")
check("exception carried onto the transaction", txn5.exceptions_count, 1)
check("transaction keeps the reason",
      bool(txn5.checks[0].override_reason or
           any(c.override_reason for c in txn5.checks)), True)

# ─── auditor summary ────────────────────────────────────────────────────────

summary = rq.audit_summary(ORG)
check("summary counts transactions", summary["transactions_total"], 2)
check("summary counts exceptions", summary["exceptions_total"], 1)
check("every exception is explained", summary["exceptions_unexplained"], 0)
check("org is audit ready", summary["audit_ready"], True)
check("exception names the authority",
      "Executive Director" in summary["exceptions"][0]["authority"], True)

# ─── listing / filtering ────────────────────────────────────────────────────

all_reqs = rq.list_requisitions(ORG)
check("all requisitions listed", len(all_reqs), 5)
check("filter by status", len(rq.list_requisitions(ORG, status=rq.ReqStatus.PAID)), 2)
check("filter by grant code",
      len(rq.list_requisitions(ORG, grant_code="GR-USAID-EMERGENCY")), 2)
check("filter by pending step",
      all(r.current_step == "compliance" for r in rq.list_requisitions(ORG, step="compliance")), True)

# ─── duplicate detection ────────────────────────────────────────────────────

rq.set_workflow(ORG, wf)  # restore the 3-step workflow
dup = rq.create_requisition(
    ORG, submitted_by="program@eva.org", department="program",
    vendor_name="Supply Store Ltd", amount=75_000, category="training",
    project_code="P-EVA-006", documents=["receipt"],
)
check("duplicate flagged as warning",
      any(c.code == "DUPLICATE" and c.result == rq.CheckResult.WARNING for c in dup.checks), True)
check("warning does not block approval", len(rq.blocking_checks(dup)), 0)

# ─── small org: one step, no ceremony ───────────────────────────────────────

rq.set_workflow(OTHER, rq.default_workflow(OTHER, size="small"))
n1 = rq.create_requisition(
    OTHER, submitted_by="field@neem.org", department="program",
    vendor_name="Local Market", amount=8_000, category="supplies",
    project_code="NEEM-001",
)
check("NEEM parked on finance", n1.current_step, "finance")
n1 = rq.decide(OTHER, n1.id, decision=rq.Decision.APPROVED,
               actor="finance@neem.org", department="finance")
check("NEEM approved in one step", n1.status, rq.ReqStatus.APPROVED)

# ─── org isolation ──────────────────────────────────────────────────────────

check("NEEM sees only its own", len(rq.list_requisitions(OTHER)), 1)
check("EVA unaffected by NEEM", len(rq.list_requisitions(ORG)), 6)
check("NEEM cannot read an EVA requisition", rq.get_requisition(OTHER, r1.id), None)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")

# ─── per-category document packs ────────────────────────────────────────────
# NEEM's own deck: "the correct pack depends on whether it concerns goods,
# services, an activity, an advance, a reimbursement or a final balance
# payment." Asking a N40,000 reimbursement for a GRN trains people to ignore
# the check, and an ignored check is worse than no check.

_pack_wf = rq.RequisitionWorkflow(
    org_id=ORG,
    steps=[rq.WorkflowStep(key="finance", label="Finance", department="finance")],
    required_documents=["memo", "invoice"],
    documents_by_category={
        "equipment": ["memo", "invoice", "purchase_order", "grn"],
        "dsa": ["memo", "travel_approval_form", "unreceipted_expenses_form"],
    },
    allowed_categories=["equipment", "dsa", "utilities"],
)
rq.set_workflow(ORG, _pack_wf)

check("goods need a GRN",
      "grn" in rq.required_documents_for(_pack_wf, "equipment"), True)
check("a travel allowance does NOT need a GRN",
      "grn" in rq.required_documents_for(_pack_wf, "dsa"), False)
check("it needs the travel approval form instead",
      "travel_approval_form" in rq.required_documents_for(_pack_wf, "dsa"), True)
check("a category with no pack falls back to the org-wide list",
      rq.required_documents_for(_pack_wf, "utilities"), ["memo", "invoice"])

_equip = rq.Requisition(id="pack1", org_id=ORG, vendor_name="Laptop Vendor",
                        amount=900_000, category="equipment", project_code="B24",
                        documents=["memo", "invoice"])
_c = next(c for c in rq.run_policy_checks(ORG, _equip) if c.code == "DOCS_COMPLETE")
# A missing required document is a FAIL, not a WARNING — an approver must not
# be able to clear a payment with zero attached documents and no override.
# (This test asserted WARNING until that was fixed; it must assert the real,
# binding behaviour, not the bug that made document packs advisory-only.)
check("equipment missing its GRN blocks the payment", _c.result, rq.CheckResult.FAIL)
check("and the message names the payment type",
      "equipment payment" in _c.message, True)

_dsa = rq.Requisition(id="pack2", org_id=ORG, vendor_name="Amina Bello",
                      amount=60_000, category="dsa", project_code="B24",
                      documents=["memo", "travel_approval_form",
                                 "unreceipted_expenses_form"])
_c = next(c for c in rq.run_policy_checks(ORG, _dsa) if c.code == "DOCS_COMPLETE")
check("a correctly documented DSA passes without a GRN", _c.result, rq.CheckResult.PASS)
check("and says so in the payment's own terms",
      "dsa payment are attached" in _c.message, True)


# ─── nobody approves or pays their own request ─────────────────────────────
# Own org, so the counts asserted elsewhere in this file are untouched.
SOD = "sod-test"
departments.save(departments.default_registry(), SOD)
_wf = rq.default_workflow(SOD, size="medium")
_wf.allowed_categories = ["supplies"]
_wf.required_documents = ["receipt"]
rq.set_workflow(SOD, _wf)
#
# The department check is necessary and not sufficient. A compliance officer
# raises a requisition; compliance is the first step; the same person approves
# it. Right department, wrong person. Separately: the person who raised it
# must not be the one who releases the money, whatever happened in between.
# These are the first two questions an auditor asks.
own = rq.create_requisition(
    SOD,
    submitted_by="chioma@eva.org", department="compliance",
    vendor_name="Supply Store Ltd", amount=20_000,
    category="supplies", project_code="P-EVA-001",
    grant_code="GR-USAID-2024", vendor_account="UBA 1234567890",
    description="Raised by the compliance officer herself", documents=["receipt"],
)
check("own request parked on the submitter's own department", own.current_step, "compliance")
expect_err("she cannot approve what she raised, even at her own step",
    lambda: rq.decide(SOD, own.id, decision=rq.Decision.APPROVED,
                      actor="chioma@eva.org", department="compliance",
                      notes="Looks fine to me."))
own = rq.decide(SOD, own.id, decision=rq.Decision.RETURNED,
                actor="chioma@eva.org", department="compliance",
                notes="Withdrawing to fix the amount.")
check("but she CAN return her own request — withdrawing is not a conflict",
      own.status, rq.ReqStatus.RETURNED)

# And the payment side: fully approved by others, the submitter still may not
# release it.
own2 = rq.create_requisition(
    SOD,
    submitted_by="amara@eva.org", department="finance",
    vendor_name="Supply Store Ltd", amount=20_000,
    category="supplies", project_code="P-EVA-001",
    grant_code="GR-USAID-2024", vendor_account="UBA 1234567890",
    description="Raised by finance", documents=["receipt"],
)
own2 = rq.decide(SOD, own2.id, decision=rq.Decision.APPROVED,
                 actor="chioma@eva.org", department="compliance", notes="ok")
# finance step: amara raised it, so a DIFFERENT finance person must approve
expect_err("finance colleague who raised it cannot approve at the finance step",
    lambda: rq.decide(SOD, own2.id, decision=rq.Decision.APPROVED,
                      actor="amara@eva.org", department="finance", notes="ok"))
own2 = rq.decide(SOD, own2.id, decision=rq.Decision.APPROVED,
                 actor="tunde@eva.org", department="finance", notes="ok")
check("another finance officer can", own2.status, rq.ReqStatus.APPROVED)
expect_err("the submitter cannot release the payment",
    lambda: rq.mark_paid(SOD, own2.id, actor="amara@eva.org",
                         bank_reference="GTB/000"))
paid_by_other = rq.mark_paid(SOD, own2.id, actor="tunde@eva.org",
                             bank_reference="GTB/001")
check("someone else can", paid_by_other.paid_by, "tunde@eva.org")


# ─── multi-user: two people submitting in the same instant ─────────────────
# Not an edge case for a finance tool several people use at once — it's
# Tuesday. _next_ref used to be an unprotected read-then-write across two
# separate store calls: two threads could both read counter=N and both write
# N+1, walking away with the SAME reference. Fired for real with 20 threads
# racing on an unpatched build; asserts it cannot happen now.
import threading as _threading

CONC = "concurrency-test"
departments.save(departments.default_registry(), CONC)
_cwf = rq.default_workflow(CONC, size="small")
_cwf.allowed_categories = ["supplies"]
rq.set_workflow(CONC, _cwf)

_created: list[rq.Requisition] = []
_errors: list[Exception] = []
_creation_lock = _threading.Lock()

def _create_one(i: int) -> None:
    try:
        r = rq.create_requisition(
            CONC, submitted_by=f"user{i}@eva.org", department="finance",
            vendor_name=f"Vendor {i}", amount=1_000 + i, category="supplies",
            project_code="P-1", description="concurrent submit",
        )
        with _creation_lock:
            _created.append(r)
    except Exception as exc:                        # noqa: BLE001
        with _creation_lock:
            _errors.append(exc)

_threads = [_threading.Thread(target=_create_one, args=(i,)) for i in range(20)]
for t in _threads:
    t.start()
for t in _threads:
    t.join()

check("all twenty submissions succeeded", len(_errors), 0)
check("all twenty got a reference", len(_created), 20)
_refs = [r.ref for r in _created]
check("every reference is unique — no two people got the same one",
      len(set(_refs)), 20)
check("the sequence has no gaps despite the race",
      sorted(int(r.split("-")[1]) for r in _refs),
      list(range(1, 21)))

# The script tracked failures in _fail throughout but, until this fix, always
# printed a clean success message and exited 0 regardless — exactly the
# "every signal was green" failure mode the .gitignore incident (see
# test_routes_are_committed.py) was about. A test file that cannot itself
# report failure is the one that lets a real regression through silently.
import sys as _sys
if _fail:
    print(f"\n{_fail} requisition check(s) FAILED.")
    _sys.exit(1)
print("All requisition checks passed.")
