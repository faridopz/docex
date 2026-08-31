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
r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="chioma@eva.org", department="compliance",
               notes="Donor-aligned, documentation complete.")
check("routed to finance", r1.current_step, "finance")

# finance approves → 75k is above the 50k ED threshold, so ED is next
r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="amara@eva.org", department="finance",
               notes="Fund available on GR-USAID-2024.")
check("routed to ED", r1.current_step, "ed")

r1 = rq.decide(ORG, r1.id, decision=rq.Decision.APPROVED,
               actor="seun@eva.org", department="ed", notes="Approved.")
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
print("All requisition checks passed.")
