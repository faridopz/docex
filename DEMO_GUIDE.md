# NEEM demo guide — what to show, what to say about the gaps, what to ask

Quick-reference for the live demo. Three parts: what's genuinely ready to
show, exactly why each not-yet-ready feature isn't (so you're never caught
improvising an answer), and the questions worth getting answered while
everyone's in the room.

---

## 1. Demo with confidence — these are built, tested, and live

- **Requisition → approval → payment**, running NEEM's actual configured
  chain (Finance/Audit → Admin → AED, ED joining above ₦7,000,000), their
  twenty categories, and their document packs (a DSA asks for the travel
  approval form and the unreceipted expenses form; equipment asks for a PO
  and a GRN — nobody has to remember which).
- **Checks run the instant a request is raised** — ceiling, category,
  duplicate-in-30-days, required documents — so the person raising it fixes
  problems before an approver ever sees them.
- **Policy overrides require a written reason and a named authority**, both
  permanently attached to that payment.
- **The audit trail** — hash-chained, append-only, tamper-evident. Worth
  actually showing: open a paid item's audit log and point out it's not just
  a list, it's cryptographically linked.
- **Separation of duties** — the same person cannot raise and approve, or
  approve and pay, their own request. Worth demoing live with two accounts if
  you set up a second user beforehand (see the guide from earlier today).
- **TIN format checking, bank account name verification, bank
  reconciliation, advance retirement, timesheets/effort-reporting** — all
  live and working as built (see part 2 for the honest caveat on each).
- **The onboarding wizard** and the **QuickBooks handoff screen** — both new
  today. Fine to show as "here's how you'd configure a second department or
  a new client from scratch," but don't present QuickBooks export as
  something NEEM can use immediately — see below.

---

## 2. The gaps — what to say, and why, if it comes up

Say these plainly if asked. Guessing an answer live is worse than "here's
exactly why, and what closes it."

**TIN verification is a format check, not a live registry lookup.**
DOCex confirms a TIN is well-formed — length, digit pattern, not an obvious
placeholder. It does **not** confirm that number is actually registered to
that company with FIRS, because there's no free official lookup; a real
verification needs a paid provider. *Why not built yet:* nobody's asked for
it and picked a provider. *Closes with:* NEEM saying they want it, and which
provider (if they have a preference).

**Bank reconciliation works, but hasn't been proven against NEEM's own
statement format.** The matching logic (reference, exact amount+date, vendor
name, both directions) is built and tested. What's unconfirmed is whether
the column-detection correctly reads NEEM's actual GTBank/Zenith/Lotus
export — different banks format differently, and we've only tested against
representative samples, not a real NEEM file. *Why not confirmed yet:* we
don't have one. *Closes with:* one real bank statement.

**Timesheets do something real, but not what was originally asked.** What
was requested was corroboration — "did this person actually work on that
project the week they claimed a per-diem." What's built is effort-reporting
for grant salary cost-sharing (2 CFR 200.430(i) compliance): it decides how
someone's *salary* splits across grants based on approved hours. It is not
wired to advances or per-diem at all — nothing cross-checks a claim against
a timesheet today. *Why not built yet:* corroboration needs a real example
from NEEM first — is it checked against a timesheet code, an attendance
list, or the travel approval form itself? Guessing wrong here would ship a
check that doesn't match how NEEM's field activities actually get recorded,
which is worse than no check. *Closes with:* one concrete example of a claim
NEEM would want flagged, and what record should have proven or disproven it.

**Payroll is switched off.** We don't have NEEM's confirmed PAYE bands or
pension rate. Running payroll without them produces payslips that look
right and are wrong — the kind of error an accountant finds months later.
*Closes with:* the tax schedule from NEEM's side.

**Withholding tax is switched off, deliberately — not a bug.** NEEM's own
cashbook shows 5% and 10% in different places for what looks like the same
category. DOCex ships no rates of its own; a guessed rate is worse than an
empty one, because an empty one gets asked about and a guessed one gets
trusted. *Closes with:* the schedule from NEEM's auditor.

**QuickBooks export needs NEEM's chart of accounts entered.** The export
itself is built, tested, and — as of this week — has a real settings screen
(Settings → QuickBooks handoff). What's missing is data, not code: someone
needs fifteen minutes with NEEM's actual QuickBooks to map their ~20 spend
categories and ~13 project/grant codes to real account and class names.
Until that's entered, exports would post everything to a single
"Uncategorised Expense" line — visible, never silently dropped, but not
useful yet. *Closes with:* that fifteen-minute mapping session, or NEEM's
account list handed over so it can be done for them. (Full write-up,
including the option of a live QuickBooks API sync later and what that would
cost: `QUICKBOOKS_INTEGRATION.md`.)

---

## 3. Questions worth getting answered in the room

These are the six from `NEEM_WELCOME.md`, plus one new one from this week's
work. Getting even two or three answered today saves a follow-up email.

1. **The quote-threshold conflict.** Their signed Procurement Policy requires
   three quotes from ₦200,001. Their Finance Processes deck says a direct
   memo is sufficient to ₦499,999. These disagree across the band where most
   purchases actually sit. **Which one governs?**
2. **How does GAPS show a weekly batch** on the bank statement — one debit
   per payee, or one line for the whole batch? (Affects how reconciliation
   matches it.)
3. **NEEM's withholding tax schedule**, from their auditor.
4. **PAYE bands and pension rate**, to switch payroll on.
5. **What counts as a "collective default"** on overdue advances? Their
   policy uses the phrase without a number attached. We've assumed two —
   would rather use theirs.
6. **One real bank statement, and their chart of accounts** — unlocks
   confirming reconciliation and switching on the QuickBooks export for
   real.
7. *(New this week)* **Does NEEM want live TIN verification against FIRS**,
   and do they have a preferred provider, or is the format check enough for
   now?

---

## One line on system readiness, if asked directly

Multiple staff can use this at once safely — separation of duties, org
isolation, and (as of today) a fixed race condition in reference-number
generation are all tested under real concurrent load, not just assumed. If
someone asks "what if two people click submit at the same second," the
honest answer as of today is: tested, and it holds.
