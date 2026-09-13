# NEEM's three original asks — where each one actually stands

At the first scoping meeting (see `NEEM_FOLLOWUP_NOTES.md`) NEEM asked for three
things by name, beyond the core requisition/approval/audit system: vendor Tax ID
verification, month-end payment reconciliation, and a timesheet integration.
This checks each one against what is actually built and live today, rather than
against what a feature flag says.

---

## 1. Vendor Tax ID (TIN) verification — ✅ built as scoped

**What was asked:** validate a vendor's TIN before payment; start with manual
entry + format validation, add a real FIRS lookup later if wanted.

**What's built (`vendors.py`):** exactly that split, and it is careful about
the distinction that matters to an auditor. Every TIN is format-checked
instantly and for free — length, digit patterns, obvious placeholders (all the
same digit, a phone number typed into the wrong field). That result is stored
as `format_ok`, **never** as `verified`. A real FIRS lookup is a separate,
explicitly-named path (`verify_tin`) that only runs if a paid provider is
configured — today none is, so it correctly reports "not configured" rather
than pretending to check something it can't. The vendor register report
(`vendor_summary`) shows counts for present / invalid / format-checked /
externally-verified TINs, so finance can see at a glance which vendors have
only a format check versus a real one.

**Status: live for NEEM** (`vendor_register: true`, `tin_verification: true`).
Tested in `test_vendors.py`. Nothing further needed unless NEEM wants the paid
FIRS lookup, which is a new integration (cost/timeline conversation), not a
gap in what shipped.

---

## 2. Month-end payment reconciliation — ✅ built as scoped

**What was asked:** match requisitions (what we said we'd pay) against the
bank statement (what actually left the account) — vendor name, amount, date
window — and flag both a bank debit with no requisition AND an approved
requisition with no matching bank line.

**What's built (`bank_reconciliation.py`):** matches in three ways — bank
reference, exact amount+date, and vendor name — and, importantly, checks
**both directions**, which the module's own docstring calls out as the finding
a manual spreadsheet reconciliation misses most often (a person ticking off a
statement works from the payment list forward, rarely backward from the
statement). Amounts compare in integer minor units, not floats. A pairing that
would be ambiguous (two payments, two bank lines, same amount and week) is
reported as ambiguous rather than guessed. Nigerian date formats are read
defensively (`03/04` is not silently assumed to mean either 3 April or 4
March).

**Status: live for NEEM** (`bank_reconciliation: true`). Tested in
`test_bank_reconciliation.py`. The one thing still needed — already flagged in
`NEEM_WELCOME.md`'s six questions — is a real bank statement from NEEM's own
bank to confirm the column-mapping auto-detection reads it correctly.
Auto-detection handles common Nigerian layouts; it has not been checked
against NEEM's actual GTBank/Zenith/Lotus exports.

---

## 3. Timesheet integration — ⚠️ NOT the feature that was asked for

**What was asked**, verbatim from the scoping notes: *"Link staff timesheets
to per-diem payments / advance tracking... When an advance is submitted,
check: did this person work on that project that week? Link the per-diem
reimbursement to the timesheet entry."* The point was corroboration — proving
a per-diem or advance claim matches actual recorded work.

**What's built (`timesheets.py`) is a real, different feature**: effort
reporting for **grant salary cost-sharing** under 2 CFR 200.430(i) — the
federal rule that personnel costs charged to a donor grant must be backed by
after-the-fact records of actual hours worked, not a budgeted percentage. It
enforces exactly that: allocation is derived from recorded hours (never
accepted as input), every hour needs a project code, nobody approves their own
timesheet, and an approved/processed record is frozen. It is well-built and
audit-relevant — but it answers "how should this person's *salary* be split
across grants," not "did this person's *per-diem claim* match a day they
actually worked."

**The gap, concretely:** nothing in `advances.py` or `per_diem.py` reads a
timesheet record at all. An advance can be issued and a per-diem paid with no
cross-check against anyone's recorded hours. Grepping the codebase for any
link between the two modules turns up none — this isn't a partially-built
feature, it's a feature that hasn't been started.

**Why it hasn't been built:** it needs a specific answer from NEEM first —
per-diem and advances are typically tied to a *trip* or an *activity*, not to
a working day the way effort-reporting timesheets are. Building the check
before knowing what "did this person work on that project that week" actually
means for a field activity (attendance list? a specific timesheet code? the
existing `travel_approval_form`?) risks shipping a cross-check that doesn't
match how NEEM's field activities actually record time — which would be worse
than not having it, the same reasoning `withholding.py` and this module both
already state elsewhere in the codebase: a confident wrong check is worse than
an honest gap.

**What's needed to close it:** one real example from NEEM — an advance or
per-diem claim they'd want flagged, and what record would have proven or
disproven it. That's a short conversation, and after it this is a
straightforward addition to `advances.py`/`per_diem.py`'s existing checks —
not a rebuild.

---

## Bottom line

Two of the three original asks are built, tested, and live exactly as scoped.
The third shipped a genuinely useful, audit-grade feature that happens to
share the word "timesheet" with what was actually requested — but it isn't a
substitute for it. Worth saying so directly rather than letting NEEM discover
the difference themselves.
