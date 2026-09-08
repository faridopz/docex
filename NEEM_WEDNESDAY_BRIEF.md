# NEEM follow-up — Wednesday

Everything for the meeting in one place: what to run beforehand, what to show,
what to ask, and what not to claim.

---

## Before you leave (15 minutes)

```bash
cd ~/Desktop/docex
git pull

# One database, one org, everything pointed at it
DOCEX_DB=./demo.db DOCEX_ORG=default python3 demo_seed.py --reset --password 'DemoPass2026'
DOCEX_DB=./demo.db DOCEX_ORG=default python3 org_config.py features \
  timesheets=on bank_reconciliation=on advance_retirement=on \
  withholding_tax=on vendor_register=on accounting_export=on
DOCEX_DB=./demo.db DOCEX_ORG=default python3 make_demo_statement.py
DOCEX_DB=./demo.db DOCEX_ORG=default python3 demo_check.py     # must be green

# Two terminals
DOCEX_DB=./demo.db DOCEX_ORG=default uvicorn api.main:app --reload --port 8000
cd web && npm run dev
```

Then **open every screen you intend to show** and hard-refresh. If a port is
occupied, `lsof -ti:8000 | xargs kill -9` — a stale server pointed at the wrong
database is what went wrong last time, and `demo_check.py` catches it.

Sign in: **demo@neem.org / DemoPass2026**

---

## The one thing to lead with

Their own documents contradict each other, and you found it by reading what
they sent.

> The signed Procurement Policy requires **three quotes from ₦200,001**. The
> Finance Processes deck your staff are trained on says a **direct memo is fine
> up to ₦499,999**. Which governs? Because every single-quote purchase between
> those two numbers is a finding waiting to happen, and it is the band most of
> your spending sits in.

Ask it as a question, not a correction. This is the moment you stop being
someone selling software and become someone who read their policy.

---

## What to show, in order

### 1. Reconciliation — the ₦750,000

Upload the statement. It finds a transfer to a vendor that exists nowhere in
the approval system, and the month cannot be closed until someone explains it
in writing, under their name.

> In QuickBooks, an unauthorised ₦750,000 transfer looks identical to a payment
> someone forgot to enter. Both are unmatched lines, and the fix for both is
> the same button: Add. That is how an unauthorised payment gets absorbed into
> the books.

If they have a bank feed with auto-add rules, this argument gets stronger, not
weaker — a fed transaction posts with nobody looking at it.

### 2. Withholding tax — the thing that would have broken it

Worth showing precisely because it is unglamorous.

> Your cashbook has WHT on nearly every line, 5% or 10%, remitted separately by
> RRR. So one invoice is two debits. Built naively, reconciliation would flag
> every tax remittance as unapproved money — on half your statement. We model
> the pair, so both are expected.

This says: we read six months of your cashbook.

### 3. Advance retirement — their own policy, enforced

> Your deck says an advance must be retired in 7 days or 5 working days, that
> failure means no further payment to that person, that a collective default
> blocks the project's next activity, and that persisting to month end means
> recovery from salary. Most organisations never write down the consequence.
> Yours did, so we enforce it.

Show the aging list, then raise a requisition for someone with an overdue
advance and let it block.

The clock runs on **working** days, and for DSA it starts at the **end of the
trip** — both taken from their wording.

### 4. Timesheets → payroll

Fill a month in the grid in about thirty seconds. Half-day clicks, no keyboard.

> Budgeted 50/50, actually worked 30/70 — the grant is charged 30/70. That
> difference is what donors disallow.

### 5. Twenty bank accounts

Show the portfolio: which are reconciled, which are not.

> A ₦380,000 CARE payment and a ₦380,000 UNFPA payment look identical. Upload
> the wrong statement and both months would report clean. So DOCex reads the
> account number out of the statement header, and refuses to guess.

---

## Six questions to ask

1. **The ₦200,001 threshold conflict** — which document governs?
2. **Can you connect your bank to QuickBooks directly?** And if so, **do you
   use auto-add rules?** (If yes, our control argument sharpens.)
3. **Does the GAPS statement show one debit per payee, or one per weekly
   batch?** This decides how the payment schedule is built.
4. **Your WHT schedule** — we ship no rates deliberately; we need the one your
   auditor applies.
5. **"A collective default"** — how many overdue advances make it collective?
   Your policy does not say. We assumed two.
6. **One bank statement**, for whichever account you want to start with. Plus
   your chart of accounts, or the QuickBooks export posts everything to
   Uncategorised Expense.

---

## What NOT to claim

Say these plainly if they come up. Each one is more credible than a hedge.

- **Payroll is switched off for you.** We have no confirmed PAYE bands or
  pension rate, and running payroll without them would pay gross as net.
- **We have not tested against a real NEEM bank statement.** Everything so far
  is a file we generated. The column mapping gets confirmed in the first
  session, and the importer refuses rather than guessing when it cannot read a
  date.
- **Tax ID checking is a format check today.** There is no free official API —
  JTB became the Joint Revenue Board in January 2026 and the portals are web
  forms. Live verification needs a paid provider, roughly ₦50–100 a lookup, and
  we would wire it to whichever they choose. **Bank account verification is
  real** and already works.
- **QuickBooks is export today, direct sync once we are working together.** The
  API needs their credentials and a registered app.
- **Some things are API-only.** Vendor register, QuickBooks export and advances
  have no screens yet. Describe them; do not promise to click them.

---

## What is genuinely built

| Area | State |
|---|---|
| Requisitions, policy checks, approval chain | Screens, tested |
| Immutable audit trail, hash-chained | Screens, tested |
| Bank reconciliation, per account | Screens, tested |
| Timesheets → payroll allocation | Screens, tested |
| Withholding tax | API, tested |
| Advance retirement + escalation | API, tested |
| Vendor register + bank verification | API, tested |
| QuickBooks export | API, tested |
| Payroll | Built, **off for NEEM** — no rates |

**33 test suites green.** Security: brute-force lockout, real logout, org
isolation, default-deny on every route.

---

## If they ask "when can we start?"

The honest answer, and it is a good one:

> The system is ready. Three things are yours, not ours: a bank statement so we
> can confirm the format, your chart of accounts, and your WHT schedule. Give
> us those and you could be running your next month end in it.

Then, separately, the two you owe them before real data:

- **durable hosting** — the current instance wipes on redeploy
- **password reset** — no recovery path exists yet

Neither is a reason to delay the conversation; both are a reason not to promise
next Monday.
