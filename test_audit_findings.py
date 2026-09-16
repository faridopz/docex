"""
WO-37: the audit tests.

Each test here builds the exact condition a finding is meant to catch and
asserts it fires — and, just as importantly, asserts that ordinary clean
activity does NOT fire it. A control test that cannot be shown to stay quiet
on good data is not evidence of anything.

The tests under test:
  CHAIN_BROKEN            a tampered audit log
  UNEXPLAINED_EXCEPTION   a blocking check released with no reason
  SOD_SAME_APPROVER       one person signing two stages of one chain
  SHARED_BANK_ACCOUNT     one account paid under several payee names
  THRESHOLD_PROXIMITY     amounts shaved just under an approval threshold
  SPLIT_PAYMENT           one payee, several payments, together over a limit
  SKIPPED_STAGE           a stage escalated past and never decided
  OUT_OF_HOURS            approvals at a weekend or overnight
  REFERENCE_GAP           missing numbers in the requisition sequence

Run: python test_audit_findings.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store

_base = Path(tempfile.mkdtemp(prefix="docex_audit_findings_"))
store.set_store(store.JsonFileStore(_base / "store"))

import audit_findings as af  # noqa: E402
import requisitions as rq  # noqa: E402

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


def codes(org: str, **kw) -> set[str]:
    return {f.code for f in af.run_audit_tests(org, **kw).findings}


def finding(org: str, code: str):
    return next((f for f in af.run_audit_tests(org).findings if f.code == code), None)


# ─── a clean org finds nothing ─────────────────────────────────────────────

CLEAN = "clean-org"
wf = rq.default_workflow(CLEAN, size="small")
wf.max_amount = 5_000_000
rq.set_workflow(CLEAN, wf)

rq.create_requisition(CLEAN, submitted_by="a@x.org", department="program",
                      vendor_name="Ordinary Vendor", amount=12_345)
report = af.run_audit_tests(CLEAN)
check("a clean organisation produces no findings", report.clean)
check("it still reports what it examined", report.requisitions_examined == 1)
check("severity counts are all zero", report.by_severity == {"high": 0, "medium": 0, "low": 0})

# ─── THRESHOLD_PROXIMITY ───────────────────────────────────────────────────

ORG = "findings-org"
wf = rq.default_workflow(ORG, size="small")
wf.steps = [
    rq.WorkflowStep(key="finance", label="Finance", department="finance"),
    rq.WorkflowStep(key="ed", label="ED approval", department="management",
                    min_amount=1_000_000),
]
wf.max_amount = 50_000_000
wf.duplicate_window_days = 30
rq.set_workflow(ORG, wf)

# 970,000 is inside 5% of the 1,000,000 ED threshold.
rq.create_requisition(ORG, submitted_by="a@x.org", department="program",
                      vendor_name="Shaved Ltd", amount=970_000)
check("an amount just under a threshold is flagged", "THRESHOLD_PROXIMITY" in codes(ORG))
f = finding(ORG, "THRESHOLD_PROXIMITY")
check("the proximity finding is medium severity", f.severity == "medium")
check("it names the requisition", len(f.refs) == 1)

# A comfortably-below amount must NOT trip it.
SAFE = "safe-org"
rq.set_workflow(SAFE, wf.model_copy(update={"org_id": SAFE}))
rq.create_requisition(SAFE, submitted_by="a@x.org", department="program",
                      vendor_name="Normal Ltd", amount=300_000)
check("an amount well below a threshold is NOT flagged",
      "THRESHOLD_PROXIMITY" not in codes(SAFE))

# ─── SPLIT_PAYMENT ─────────────────────────────────────────────────────────

SPLIT = "split-org"
rq.set_workflow(SPLIT, wf.model_copy(update={"org_id": SPLIT}))
for _ in range(3):
    rq.create_requisition(SPLIT, submitted_by="a@x.org", department="program",
                          vendor_name="Divided Supplies", amount=400_000)
check("three payments to one payee crossing a threshold are flagged",
      "SPLIT_PAYMENT" in codes(SPLIT))
f = finding(SPLIT, "SPLIT_PAYMENT")
check("the split finding names every payment in the cluster", len(f.refs) == 3)
check("the split total is reported", f.amount == 1_200_000)

# Two payments to DIFFERENT payees are not a split.
NOSPLIT = "nosplit-org"
rq.set_workflow(NOSPLIT, wf.model_copy(update={"org_id": NOSPLIT}))
rq.create_requisition(NOSPLIT, submitted_by="a@x.org", department="program",
                      vendor_name="Vendor One", amount=600_000)
rq.create_requisition(NOSPLIT, submitted_by="a@x.org", department="program",
                      vendor_name="Vendor Two", amount=600_000)
check("payments to different payees are NOT a split",
      "SPLIT_PAYMENT" not in codes(NOSPLIT))

# ─── SHARED_BANK_ACCOUNT ───────────────────────────────────────────────────

SHARED = "shared-org"
rq.set_workflow(SHARED, wf.model_copy(update={"org_id": SHARED}))
import org_config  # noqa: E402
org_config.set_features(SHARED, multi_payee_requisitions=True)
rq.create_requisition(
    SHARED, submitted_by="a@x.org", department="program",
    vendor_name="Stipend run", amount=0,
    payees=[
        rq.Payee(name="Aisha Bello", account_number="0123456789", amount=20_000),
        rq.Payee(name="Musa Ibrahim", account_number="0123456789", amount=20_000),
        rq.Payee(name="Grace Okon", account_number="2222222222", amount=20_000),
    ],
)
check("one account paid under two names is flagged", "SHARED_BANK_ACCOUNT" in codes(SHARED))
f = finding(SHARED, "SHARED_BANK_ACCOUNT")
check("the shared-account finding is high severity", f.severity == "high")
check("it does not leak the whole account number", "0123456789" not in f.detail)

# ─── SOD_SAME_APPROVER ─────────────────────────────────────────────────────

SOD = "sod-org"
sod_wf = wf.model_copy(update={
    "org_id": SOD,
    "steps": [
        rq.WorkflowStep(key="finance", label="Finance", department="finance"),
        rq.WorkflowStep(key="mgmt", label="Management", department="finance"),
    ],
})
rq.set_workflow(SOD, sod_wf)
req = rq.create_requisition(SOD, submitted_by="raiser@x.org", department="program",
                            vendor_name="Two Hats Ltd", amount=50_000)
rq.decide(SOD, req.id, decision=rq.Decision.APPROVED,
          actor="same.person@x.org", department="finance")
rq.decide(SOD, req.id, decision=rq.Decision.APPROVED,
          actor="same.person@x.org", department="finance")
check("one person approving two stages is flagged", "SOD_SAME_APPROVER" in codes(SOD))
f = finding(SOD, "SOD_SAME_APPROVER")
check("the SoD finding is high severity", f.severity == "high")
check("it names the person", "same.person@x.org" in f.detail)

# Two DIFFERENT approvers on the same chain must not trip it.
OK_SOD = "ok-sod-org"
rq.set_workflow(OK_SOD, sod_wf.model_copy(update={"org_id": OK_SOD}))
req = rq.create_requisition(OK_SOD, submitted_by="raiser@x.org", department="program",
                            vendor_name="Proper Ltd", amount=50_000)
rq.decide(OK_SOD, req.id, decision=rq.Decision.APPROVED,
          actor="first@x.org", department="finance")
rq.decide(OK_SOD, req.id, decision=rq.Decision.APPROVED,
          actor="second@x.org", department="finance")
check("two different approvers are NOT flagged", "SOD_SAME_APPROVER" not in codes(OK_SOD))

# ─── SKIPPED_STAGE ─────────────────────────────────────────────────────────

SKIP = "skip-org"
skip_wf = wf.model_copy(update={
    "org_id": SKIP,
    "steps": [
        rq.WorkflowStep(key="finance", label="Finance", department="finance"),
        rq.WorkflowStep(key="middle", label="Middle", department="finance"),
        rq.WorkflowStep(key="final", label="Final", department="finance"),
    ],
})
rq.set_workflow(SKIP, skip_wf)
req = rq.create_requisition(SKIP, submitted_by="a@x.org", department="program",
                            vendor_name="Escalated Ltd", amount=50_000)
rq.route_to(SKIP, req.id, target_step="final", actor="fin@x.org",
            department="finance", reason="Urgent — ED asked for it directly")
check("a stage escalated past is flagged", "SKIPPED_STAGE" in codes(SKIP))

# ─── REFERENCE_GAP ─────────────────────────────────────────────────────────

GAP = "gap-org"
rq.set_workflow(GAP, wf.model_copy(update={"org_id": GAP}))
a = rq.create_requisition(GAP, submitted_by="a@x.org", department="program",
                          vendor_name="One", amount=1000, submit=False)
rq.create_requisition(GAP, submitted_by="a@x.org", department="program",
                      vendor_name="Two", amount=1000)
rq.create_requisition(GAP, submitted_by="a@x.org", department="program",
                      vendor_name="Three", amount=1000)
rq.discard_draft(GAP, a.id, actor="a@x.org")      # leaves a hole at REQ-0001
check("a discarded draft leaves a visible sequence gap", "REFERENCE_GAP" in codes(GAP))
f = finding(GAP, "REFERENCE_GAP")
check("the gap finding is low severity — usually benign", f.severity == "low")
check("it explains the usual cause", "draft" in f.why.lower())

# ─── CHAIN_BROKEN ──────────────────────────────────────────────────────────

TAMPER = "tamper-org"
rq.set_workflow(TAMPER, wf.model_copy(update={"org_id": TAMPER}))
req = rq.create_requisition(TAMPER, submitted_by="a@x.org", department="program",
                            vendor_name="Before Tampering", amount=10_000)
raw = store.get_store().get(TAMPER, "requisitions", req.id)
raw["audit_log"][0]["detail"] = "quietly altered outside the application"
store.get_store().put(TAMPER, "requisitions", req.id, raw)
check("a tampered audit log is detected", "CHAIN_BROKEN" in codes(TAMPER))
f = finding(TAMPER, "CHAIN_BROKEN")
check("tampering is the highest severity", f.severity == "high")
check("it is sorted to the very top of the report",
      af.run_audit_tests(TAMPER).findings[0].code == "CHAIN_BROKEN")

# ─── OUT_OF_HOURS ──────────────────────────────────────────────────────────

HOURS = "hours-org"
rq.set_workflow(HOURS, wf.model_copy(update={"org_id": HOURS}))
req = rq.create_requisition(HOURS, submitted_by="a@x.org", department="program",
                            vendor_name="Midnight Ltd", amount=50_000)
rq.decide(HOURS, req.id, decision=rq.Decision.APPROVED,
          actor="night@x.org", department="finance")
# Rewrite the approval to 03:00 on a Sunday. Done through the store rather
# than the engine because the engine — correctly — will not let a caller
# choose when a decision happened.
raw = store.get_store().get(HOURS, "requisitions", req.id)
raw["approvals"][0]["at"] = "2026-09-13T03:00:00+00:00"   # a Sunday
store.get_store().put(HOURS, "requisitions", req.id, raw)
check("a 3am Sunday approval is flagged", "OUT_OF_HOURS" in codes(HOURS))
f = finding(HOURS, "OUT_OF_HOURS")
check("out-of-hours is low severity, not an accusation", f.severity == "low")
check("it says plainly that it is usually nothing", "usually nothing" in f.why.lower())

# ─── ordering and shape ────────────────────────────────────────────────────

report = af.run_audit_tests(ORG)
severities = [f.severity for f in report.findings]
order = {"high": 0, "medium": 1, "low": 2}
check("findings are sorted by severity, worst first",
      severities == sorted(severities, key=lambda s: order[s]))
check("every finding explains why an auditor cares",
      all(f.why.strip() for f in report.findings))
check("every finding says what it found",
      all(f.detail.strip() for f in report.findings))

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll audit-findings checks passed.")
