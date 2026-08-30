"""Tests for the payroll + refinancing engine. Run: python test_payroll.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import payroll
import store
import transactions as tx

_base = Path(tempfile.mkdtemp(prefix="docex_pay_"))
store.set_store(store.JsonFileStore(_base / "data"))
tx._TXN_DIR = _base / "txn"
tx._COUNTER_FILE = _base / "txn" / ".counter"

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


ORG = "eva"

# ── policy: the org configures its own rates; we never invent tax bands ──
payroll.set_policy(ORG, payroll.PayrollPolicy(
    rules=[
        # Illustrative rates supplied by the org — NOT real Nigerian bands.
        payroll.DeductionRule(code="PAYE", name="PAYE", method="bands",
                              bands=[(100_000, 5.0), (200_000, 10.0), (None, 15.0)]),
        payroll.DeductionRule(code="PENSION-EE", name="Pension (employee)",
                              method="percent", rate_percent=8.0),
        payroll.DeductionRule(code="PENSION-ER", name="Pension (employer)",
                              method="percent", rate_percent=10.0, employer_paid=True),
    ],
    refinancing_sign="negative",
))

# ── progressive band maths ──
# 300,000 gross: 5% of first 100k = 5,000; 10% of next 100k = 10,000;
#                15% of remaining 100k = 15,000  → 30,000
ded = {d.code: d.amount for d in payroll.compute_deductions(300_000, payroll.get_policy(ORG))}
check("PAYE progressive bands", ded["PAYE"], 30_000)
check("employee pension 8%", ded["PENSION-EE"], 24_000)
check("employer pension 10%", ded["PENSION-ER"], 30_000)

# ── staff: one split across two donors, one single-funded ──
payroll.add_staff(ORG, name="Aisha Bello", position="Programme Officer",
                  office="HQ", gross_salary=300_000,
                  allocations=[
                      payroll.SalaryAllocation(project_code="P-101", donor="USAID", percent=60),
                      payroll.SalaryAllocation(project_code="P-202", donor="Gates", percent=40),
                  ])
payroll.add_staff(ORG, name="Chidi Okonkwo", position="Finance Officer",
                  office="HQ", gross_salary=200_000,
                  allocations=[payroll.SalaryAllocation(project_code="P-101", donor="USAID", percent=100)])

run = payroll.build_run(ORG, "2026-08", beneficiaries_direct=1250, beneficiaries_indirect=6000)

check("two staff on the run", run.staff_count, 2)
check("total gross", run.total_gross, 500_000)
# Aisha net: 300,000 - 30,000 PAYE - 24,000 pension = 246,000
aisha = next(l for l in run.lines if l.name == "Aisha Bello")
check("Aisha net pay", aisha.net, 246_000)
check("Aisha employer cost (gross + employer pension)", aisha.employer_cost, 330_000)
check("no line flags on clean data", aisha.flags, [])

# ── allocation to donor + project code ──
# Aisha employer cost 330,000 → 60% P-101 (198,000), 40% P-202 (132,000)
# Chidi: 200,000 gross + 20,000 employer pension = 220,000 → 100% P-101
check("project P-101 total", run.by_project["P-101"], 198_000 + 220_000)
check("project P-202 total", run.by_project["P-202"], 132_000)
check("donor USAID total", run.by_donor["USAID"], 418_000)
check("donor Gates total", run.by_donor["Gates"], 132_000)

# ── refinancing carried as a NEGATIVE ──
check("Aisha refinancing is negative", aisha.refinancing, -330_000)
check("run total refinancing negative", run.total_refinancing, -(330_000 + 220_000))

# ── beneficiaries carried on the run ──
check("beneficiaries direct", run.beneficiaries_direct, 1250)
check("beneficiaries indirect", run.beneficiaries_indirect, 6000)

# ── allocation that doesn't total 100% is flagged and excluded ──
bad = payroll.StaffRecord(id="stf-bad", name="Bad Split", gross_salary=100_000,
                          allocations=[payroll.SalaryAllocation(project_code="P-999",
                                                                donor="X", percent=97)])
bad_run = payroll.build_run(ORG, "2026-09", staff=[bad])
check("97% split is flagged", any("must be 100%" in f for f in bad_run.lines[0].flags), True)
check("miscoded staff excluded from project roll-up", bad_run.by_project.get("P-999"), None)
check("refinancing zero when allocation invalid", bad_run.lines[0].refinancing, 0)

# ── unconfigured policy warns rather than paying gross as net silently ──
payroll.set_policy("neem", payroll.PayrollPolicy(rules=[]))
payroll.add_staff("neem", name="Someone", gross_salary=100_000,
                  allocations=[payroll.SalaryAllocation(project_code="N-1", donor="D", percent=100)])
neem_run = payroll.build_run("neem", "2026-08")
check("no deduction rules → run flagged",
      any("No deduction rules configured" in f for f in neem_run.flags), True)
check("other org isolated from EVA staff", neem_run.staff_count, 1)

# ── approval flow: payment only after approval ──
expect_err("cannot submit a run with flagged lines",
           lambda: payroll.submit_for_approval(ORG, bad_run.id))

submitted = payroll.submit_for_approval(ORG, run.id, created_by="finance.lead")
check("run has a PR reference", submitted.txn_ref.startswith("PR"), True)
check("run status submitted", submitted.status, "submitted")
check("transaction opened in compliance review", tx.load(submitted.txn_id).state, "compliance_review")

expect_err("cannot mark paid before approval", lambda: payroll.mark_paid(ORG, run.id))

# Walk the workflow to paid, then payment is allowed.
t = tx.load(submitted.txn_id)
t = tx.transition(t, "finance_review", department="compliance")
t = tx.transition(t, "approval", department="finance")
t = tx.transition(t, "paid", department="management")
paid = payroll.mark_paid(ORG, run.id)
check("run marked paid only after approval", paid.status, "paid")

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All payroll checks passed.")
