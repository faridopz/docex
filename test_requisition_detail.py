"""
Tests for WO-29: richer payment-request detail — bank/TIN/phone for the
single-vendor path (batch already carries these per-row on Payee), a
payment_type field, a deterministic budget-line breakdown, and computed
amount-in-words. Modelled directly on NEEM's own Advance/Reimbursement
Request Form and Payment Voucher (see requisitions.py's BudgetLine and
Requisition docstrings) — nothing here is an invented shape.

Engine-level, like test_requisitions.py: no HTTP, no LLM, just
requisitions.py against a JsonFileStore.

Covers:
- vendor_bank_name/vendor_tin/vendor_phone_or_email round-trip
- payment_type defaults to "full" and rejects anything outside
  full/advance/balance
- budget_lines: line_total is ALWAYS server-computed from
  quantity * frequency * unit_cost — a client-supplied total is discarded,
  never trusted (DETERMINISTIC-FIRST)
- editing a draft's budget_lines recomputes totals the same way
- amount_in_words renders a real, checkable English string
- a requisition raised with none of this behaves exactly as before (no
  regression for existing callers)

Run: python test_requisition_detail.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import requisitions as rq
import store

_base = Path(tempfile.mkdtemp(prefix="docex_req_detail_"))
store.set_store(store.JsonFileStore(_base / "data"))

_fail = 0


def check(name, got, want):
    global _fail
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_err(name, fn):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except Exception as exc:
        print(f"PASS  {name}: raised as expected ({exc})")


ORG = "neem-detail"
wf = rq.default_workflow(ORG, size="small")
rq.set_workflow(ORG, wf)

# ─── a requisition with the full memo-level detail ──────────────────────────

req = rq.create_requisition(
    ORG,
    submitted_by="program@neem.org",
    department="program",
    vendor_name="Aisha Bello",
    amount=1,  # deliberately wrong — budget_lines should drive the real figure via caller math below
    vendor_account="0123456789",
    vendor_bank_name="GTBank",
    vendor_tin="TIN-99182",
    vendor_phone_or_email="aisha@example.com",
    payment_type="advance",
    budget_lines=[
        rq.BudgetLine(description="Flip charts", unit="Pieces", budget_line="B-101",
                       quantity=4, frequency=1, unit_cost=2500, line_total=999999),  # bogus total, must be ignored
        rq.BudgetLine(description="Facilitator stipend", unit="Person", budget_line="B-102",
                       quantity=2, frequency=3, unit_cost=15000, line_total=1),  # bogus total, must be ignored
    ],
)

check("vendor_bank_name round-trips", req.vendor_bank_name, "GTBank")
check("vendor_tin round-trips", req.vendor_tin, "TIN-99182")
check("vendor_phone_or_email round-trips", req.vendor_phone_or_email, "aisha@example.com")
check("payment_type round-trips", req.payment_type, "advance")
check("two budget lines saved", len(req.budget_lines), 2)

bl1, bl2 = req.budget_lines
check("line 1 total is server-computed (4 * 1 * 2500), not the bogus 999999", bl1.line_total, 10_000.0)
check("line 2 total is server-computed (2 * 3 * 15000), not the bogus 1", bl2.line_total, 90_000.0)

# amount itself was NOT derived from budget_lines (only payees[] drives a
# recompute) — confirms budget_lines is purely an expense breakdown, not a
# second source of truth for the total, matching the module's own doc note.
check("amount stays whatever create_requisition was given (budget_lines is a breakdown, not a total)",
      req.amount, 1.0)

# ─── payment_type validation ─────────────────────────────────────────────────

expect_err("payment_type rejects an unknown value", lambda: rq.create_requisition(
    ORG, submitted_by="program@neem.org", department="program",
    vendor_name="X", amount=100, payment_type="half",
))

req_default = rq.create_requisition(
    ORG, submitted_by="program@neem.org", department="program",
    vendor_name="Default Payment Type Co", amount=5000,
)
check("payment_type defaults to full", req_default.payment_type, "full")
check("budget_lines defaults to empty — no regression for existing callers",
      req_default.budget_lines, [])
check("vendor_bank_name defaults to empty", req_default.vendor_bank_name, "")

# ─── editing a draft recomputes budget-line totals the same way ────────────

draft = rq.create_requisition(
    ORG, submitted_by="program@neem.org", department="program",
    vendor_name="Draft Co", amount=1000, submit=False,
)
draft = rq.update_draft(
    ORG, draft.id, actor="program@neem.org",
    budget_lines=[rq.BudgetLine(description="Venue hire", unit="Day", budget_line="B-200",
                                 quantity=2, frequency=1, unit_cost=30000, line_total=0)],
)
check("draft edit computes the line total", draft.budget_lines[0].line_total, 60_000.0)

draft2 = rq.update_draft(ORG, draft.id, actor="program@neem.org", payment_type="balance")
check("draft edit updates payment_type", draft2.payment_type, "balance")

expect_err("draft edit rejects an invalid payment_type", lambda: rq.update_draft(
    ORG, draft.id, actor="program@neem.org", payment_type="nonsense",
))

# ─── amount_in_words ─────────────────────────────────────────────────────────

check("60,000 Naira in words", rq.amount_in_words(60_000, "NGN"), "Sixty Thousand Naira Only")
check("zero in words", rq.amount_in_words(0, "NGN"), "Zero Naira Only")
check("naira + kobo in words",
      rq.amount_in_words(120_000.50, "NGN"),
      "One Hundred Twenty Thousand Naira, Fifty Kobo Only")
check("an unrecognised currency still produces a sane sentence",
      rq.amount_in_words(42, "XYZ"), "Forty-Two Units Only")
check("USD uses Dollars/Cents", rq.amount_in_words(1_500_000, "USD"), "One Million Five Hundred Thousand Dollars Only")

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-detail checks passed.")
