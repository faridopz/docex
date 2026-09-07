# NEEM documents — what they tell us

Twelve official documents, read 7 September 2026. This is the first time we
have configured against NEEM's own paperwork rather than a reasonable guess.

Source documents: Procurement Policy (signed PDF, 25pp) · Finance and
Procurement Workflow · NEEM_Finance_Processes.pptx (2024) · CARE/FCDO Cashbook
& Bank Reconciliation Sep'23–Feb'24 · Payment Voucher · Memo template ·
Advance/Reimbursement Request Form · PO, GRN, Receipt and RFQ templates ·
Account Details · Procurement Evaluation (POCI cameras).

---

## 1. The approval chain, as it actually runs

Not what we had. The real path:

    Requesting staff → Line manager (signs the memo, confirms by email)
      → Finance/Audit (checks the pack, returns it with questions)
      → Admin (forwards to the AED, keeping the copy list)
      → AED (reviews, approves)
      → Head of Finance (uploads the WEEKLY schedule to GTBank GAPS)
      → AED (final approval IN GAPS — this is what releases the money)
      → Finance (confirms, updates cashbook, reconciles)

Three things we had wrong:

**Admin is a real step**, not a formality. Requests do not go from Finance to
the AED directly; Admin forwards them and adds the Director of Operations.

**The AED approves twice** — once on the memo, once inside GAPS. The second is
the one that moves money. That is genuine dual control and worth saying back to
them, because most organisations we will meet do not have it.

**Payments are weekly, not continuous.** Memos are due Mondays and Tuesdays
before 2pm; Finance builds one schedule for the week. Our requisition flow
treats each payment as independent. That is not wrong, but the natural unit for
them is the weekly batch.

---

## 2. Thresholds — and a contradiction they should know about

From the **signed Procurement Policy, page 6**:

| Value (₦) | Approval | Quotes | Vendor source |
|---|---|---|---|
| 1 – 200,000 | AED | Single quote | Preapproved supplier |
| 200,001 – 2,000,000 | AED | Min 3 quotes | Preapproved / online advert |
| 2,000,001 – 7,000,000 | AED, on committee recommendation | Min 3 quotes | Competitive tender |
| Above 7,000,000 | **ED and AED**, on committee recommendation | Min 5 quotes | Competitive tender |
| Sole source above 1,000,000 | ED and AED | Single quote | Justification form |

The AED is separately authorised to approve up to **₦7,000,000** for
administrative purposes — rent, utilities, equipment rental, computers,
furniture (p2).

**⚠️ The Finance Processes deck disagrees with the signed policy.**

The deck (slide 4, dated 2024) says:

- ₦10,000 – ₦499,999 → direct memo, no RFQ
- ₦500,000 – ₦1,999,999 → RFQ/RFP to identified vendors
- ₦2,000,000+ → public tender

The policy requires three quotes from **₦200,001**. The deck says a direct memo
is fine up to **₦499,999**. Those conflict across a ₦300,000 band, and it is
the band most of their spending sits in.

This matters beyond configuration: if staff are trained on the deck and audited
against the policy, every purchase between ₦200,001 and ₦499,999 done on a
single quote is a finding waiting to happen. **Raise this on Wednesday.** It is
the single most useful thing in this document set, and we found it by reading
what they sent.

The profile is configured to the **signed policy**, since that is what an
auditor will hold them to.

---

## 3. Their bank reconciliation — and why ours is not a duplicate

Their method (six months of it, Sep'23–Feb'24) is the classic accounting
balance reconciliation:

    Balance per bank statement
    Balance per cash book
      + Unpresented cheques / transfers   (in the cashbook, not yet cleared)
      − Uncredited cheques / transfers
    = Adjusted cash book balance
      Difference — should be zero

This answers *do the two balances agree*. Ours answers *was every payment
authorised, and is there anything on the statement nobody approved*. Different
questions, and theirs cannot answer the second — the cashbook only contains
what Finance already wrote down.

Three things visible in the file itself:

- **Sept'23 reconciles against a bank statement balance of 0.** They completed
  a reconciliation without the statement figure. The maths still "worked"
  because both sides were derived from the cashbook.
- **Feb'24 difference is 1.54 × 10⁻⁹** — floating-point noise being carried as
  a real number. Harmless, but it means "difference: 0" is being eyeballed
  rather than enforced.
- **The account number changes between months in the same workbook** —
  Sept/Dec/Jan/Feb cite one account, Oct/Nov cite another. Either the project
  moved accounts or a tab was copied and not updated. Worth asking.

None of these are criticisms to lead with. They are evidence that a
reconciliation done by hand in Excel drifts, which is the argument for doing it
in software.

---

## 4. Two findings that change what we build

### 4a. Withholding tax doubles every payment

WHT at 5% or 10% appears on **nearly every vendor payment** in the cashbook,
as its own line, coded **62010**, remitted separately by **RRR** (Remita) to
FIRS.

So one invoice produces **two debits on the bank statement**: net to the
vendor, and WHT to the tax authority.

Our reconciliation currently knows nothing about this. Every WHT remittance
would be reported as *"money left the account with no approved request"* — the
highest-severity finding we produce, fired at a statutory tax payment, on
roughly half the lines in the statement.

That would destroy trust in the feature on first use. **This must be handled
before NEEM reconciles anything real.**

The fix is not difficult: a payment can carry an associated tax remittance, so
the pair is expected. But it has to be built.

### 4b. Roughly twenty bank accounts, one per project

From Account Details: each project has its **own** bank account.

- **GTBank** — B2 Salary, B4 US Embassy/TSC, B6 Admin, B7 LOTG, B16 UNFPA,
  B20 GIZ, B22 French Embassy, B23 MacArthur, B24 CARE/FCDO
- **Zenith** — B9 Lafiya Sarari, B14 Flight Booking, B15 HQ Petty Cash,
  B16 UNDP, B19 POCI/Karuna
- **Lotus** — B20 GIZ
- Plus **Neem Institute Ltd**, a separate legal entity, with its own accounts

Our reconciliation assumes one account per organisation. For NEEM it needs to
be per account, with the project code attached — otherwise a payment from the
CARE account gets matched against a UNFPA statement line of the same amount.

This is also good news commercially: it is exactly the complexity that makes a
spreadsheet painful, and twenty accounts reconciled monthly by hand is a real
cost we can quantify for them.

---

## 5. What we can now configure exactly

**Chart of accounts** — real codes, straight from the cashbook:

| Code | Description | Code | Description |
|---|---|---|---|
| 9600 | Client Support Food | 71010 | Rent Expense |
| 16000 | Due to / From | 71013 | Utilities Expense |
| 52052 | Transportation Ground | 71019 | Furniture & Fittings |
| 52054 | Transportation Airfare | 81010 | Client Support Food |
| 52056 | Per diem | 81016 | Client Support Transportation |
| 61011 | Independent Contractor | 81018 | Client Support Educational |
| 61020 | Admin Fees – Operational | 81030 | Client Support Other |
| 62010 | WHT Expense | | |

This is what the QuickBooks export needs. It was going to post everything to
"Uncategorised Expense" without it.

**Payment voucher numbering** — `NF/HQ/B24/CARE/SEP23/PV/01`
(org / location / project code / donor / month / PV / sequence). We can
generate this format rather than our own references, which means our output
drops into their existing filing without translation.

**Advance retirement: 7 days or 5 working days**, with an escalation ladder
they have already written down — no further payment to that individual, then
the project's next activity blocked, then recovery from salary at month end.
That is enforceable policy, and it is unusually specific. Most organisations
have no stated consequence at all.

**They already collect what our vendor register needs.** The
Advance/Reimbursement Request Form asks for Tax Identification Number, and for
the payee's *"Name (as it appears on the bank statement)"*. They have
independently arrived at the two checks we built — they are just doing them on
paper.

---

## 6. Where we already fit, unchanged

Their documented pack — memo, invoice/quote, RFQ/RFP, vendor bids, evaluation
and minutes, PO/contract, GRN or delivery note, attendance list, payment sheet,
vehicle and fuel logs, unreceipted expenses form, travel approval — maps onto
the required-documents check without inventing anything.

The **issue register** ("documents Finance is still waiting to receive") is our
exception list, already part of their vocabulary.

The **Payment Voucher** has five signature lines: Prepared by, Checked by,
Review & Authorised by, Approved by, Received by. Our approval trail records
the same five roles.

---

## 7. What to do

**Before NEEM uses reconciliation on real data:**

1. **WHT pairing.** Highest priority. Without it the feature cries wolf on
   every tax remittance.
2. **Per-account reconciliation.** Twenty accounts cannot share one ledger view.

**Ask on Wednesday:**

3. The ₦200,001–₦499,999 threshold conflict. Which governs — the signed policy
   or the deck staff are trained on?
4. Does the GAPS statement show one debit per payee, or one per weekly batch?
5. One bank statement, for whichever account they want to start with.
6. PAYE and pension rates — still absent, so payroll stays off.

**Already done from these documents:**

- `profiles/neem.json` rebuilt with their real thresholds, real departments,
  real account codes and real project codes
- Retirement window, memo deadlines and payment terms recorded
- Account numbers deliberately **not** stored in the repo
