# WO-71 to WO-74 — Projects, timesheets, donor report, expense claims

Agreed with Farid on 4 Oct 2026, after the Smart HR Africa demo. Built on what
already exists, not beside it: grant agreements (`grants.py`), per-project
salary splits (`payroll.py`), per-project hours (`timesheets.py`), the payment
spine (`requisitions.py`) and advances (`advances.py`). One engine, a feature
flag per piece, no client names in code. Tests first, named after the failure
they prevent.

## WO-71 Projects & grants (flag `projects`)
- `Agreement` gains **budget lines** (`code`, `label`, `amount`) and
  **planned staff** (`name`, `staff_id`, `role`, `percent`): what the donor
  budget says.
- `projects.py` computes, never stores, the money: **paid** (frozen payment
  records carrying the code), **committed** (requests approved or in review,
  not yet paid), **salary charged** (approved/paid payroll runs, by project),
  **remaining** = value − paid − salary − committed. Per budget line, when
  requests itemise by line; otherwise "not assigned to a line".
- **Funds-left check** on every request charged to a grant (`FUNDS_AVAILABLE`):
  a FAIL when the request is larger than what is left on the grant or on the
  named budget line. A FAIL, not a wall: an authority can still release it
  with a written reason, which is how real budget realignments happen, and
  it lands on the audit page.
- API `/projects` (approvers, Finance, admin read; Finance approver/admin
  write). Page: list with a used/remaining bar; one project with budget lines,
  staff, approved time, payments.
- Their competitor's demo showed "6429.8% of budget used". Ours must never
  show a number that can't be traced: every figure on the page links to the
  records behind it.

## WO-72 Timesheets
- An entry can cover a **day, a week or a month** (`span`). Daily stays the
  default; a weekly or monthly line is honest about being one, rather than
  inventing daily figures. Limits per span (24 h/day, 80 h/week, 320 h/month).
- **History**: a person's own sheets by period, with status and who signed.
- **Per-project log of approved time**: staff, period, hours, approved by,
  approved on — on the project page and in the donor report.
- Quick entry: pick a project, a span and hours; no spreadsheet grid needed.

## WO-73 Donor report PDF (one click, per project and period)
Sections: summary (budget, paid, salary, committed, remaining), budget vs
actual by line, staff time (approved hours by person and month), salary
charged, payments (date, ref, payee, amount, voucher no, bank ref), and
exceptions (every released policy check with its reason and who released it).
Masked bank numbers. Built with reportlab like the other PDFs.

## WO-74 Expense claims (flag `expense_claims`)
- A claim is a payment request of kind `expense_claim`: several items, each
  with its own receipt, through the same policy checks and approval chain.
  One engine — no second approval system.
- New check `ITEM_RECEIPTS`: every item needs its own attached receipt.
- Payee is the claimant. "Paid" means reimbursed.
- **Against an advance**: the claim names the advance; on final approval the
  advance is retired with the claim total as the spend; only the difference
  is paid (or recorded as owed back).

## Order
WO-71 → WO-72 → WO-73 (needs both) → WO-74. Each: tests, code, full suite,
web type-check, commit. Then the demo data shows all four.
