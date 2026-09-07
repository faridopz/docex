# DOCex improvement audit — from NEEM's documents

Second, closer pass over the twelve documents, asking one question: where does
DOCex not yet fit the way these organisations actually work?

Ranked by value, not by effort. Effort is noted so the order can be argued
with.

---

## Already fixed since the first pass

- **Withholding tax** — one approval, two debits, both reconcilable
- **Bank accounts** — twenty of them, reconciliation scoped per account, the
  account read out of the statement header

Both were found in these documents and both were shipping blockers.

---

## 1. The document pack changes by payment type · HIGH value · LOW effort

Their Finance Processes deck (slide 8) and the workflow document both say it
plainly: *"A request will not always contain every document below. The correct
pack depends on whether it concerns goods, services, an activity, an advance, a
reimbursement or a final balance payment."*

DOCex has **one flat list** of required documents per organisation. So a
₦40,000 reimbursement is asked for the same evidence as a ₦3,000,000 equipment
purchase — which trains people to ignore the check, and an ignored check is
worse than no check.

What they actually need, from their own documents:

| Payment type | Pack |
|---|---|
| Goods | Memo · invoice/quote · PO · **GRN or delivery note** |
| Services | Memo · invoice · contract · **service completion form** |
| Activity | Memo · **attendance list** · **payment sheet** · activity report |
| Advance | Memo · **advance request form** · (retirement follows) |
| DSA / travel | **Travel approval form** (before) · **unreceipted expenses form** (after) |
| Reimbursement | Signed receipts · supporting documents |
| Balance payment | **Reference to the earlier advance** · evidence for that stage |
| Car hire / fuel | **Vehicle log sheet** / **fuel log sheet** |

This is a small change to the policy engine — required documents become a map
keyed by category rather than a list — and it is the single cheapest way to
make DOCex feel like it was built for them.

**Recommend doing this before Wednesday.** It is an hour, and it turns a
generic check into their check.

---

## 2. Advance retirement: the clock and the ladder · HIGH value · MEDIUM effort

NEEM has written down something most organisations have not — a **consequence**:

> Advances must be retired within 7 days or 5 working days of receipt. Failure
> means no payment will be made to that individual. A collective default blocks
> the whole project's next activity. Persisting to month end means the amount is
> **recovered from salary**.

We have the retirement *maths* (receipts.py reconciles what was spent against
what was advanced). We have none of:

- the clock — how many days an advance has been outstanding
- the block — refusing a new requisition from someone with an overdue advance
- the escalation — project-level block, then payroll deduction
- the ageing list finance chases from

This is enforceable policy handed to us in writing. It is also the feature with
the clearest line to money: unretired advances are the most common source of
ineligible cost in donor-funded work.

All three clients need it. EVA's policy has the same concept but, notably, **no
stated window** — which is itself a finding we already logged for them.

---

## 3. The weekly payment schedule · HIGH value · MEDIUM effort

NEEM does not pay continuously. From the workflow document and the deck:

- Memos are due **Mondays and Tuesdays before 2pm**
- Finance builds **one schedule for the week's approved payments**
- The Head of Finance uploads that schedule to **GTBank GAPS**
- The AED gives final release approval **inside GAPS**

DOCex treats every payment as independent. That is not wrong, but it is not
their rhythm, and the weekly schedule is the artefact their process is built
around.

Worth building:

- a **weekly batch** view — everything approved and awaiting the upload
- a **GAPS-format export** so the schedule is not retyped into the bank portal
- the batch as the unit reconciliation expects, since the statement may show
  one debit per batch rather than per payee

The disbursement ledger already handles one approval settling as many debits or
one, so the foundation is there.

**Ask on Wednesday whether the GAPS statement shows one line per payee or per
batch.** That single answer decides how this is built.

---

## 4. Generate the Payment Voucher · MEDIUM-HIGH value · MEDIUM effort

Their PV is a fixed form: RC No 83813, payee, address, bank, **chargeable to**,
transaction code, details, amount in words, and **five signature lines** —
Prepared by, Checked by, Review & Authorised by, Approved by, Received by.

DOCex holds every one of those fields by the time a payment is approved. It
could produce the voucher as a PDF, already filled, with the four internal
signatures represented by the approval trail (who, when, on what authority).

Their PV numbering is structured — `NF/HQ/B24/CARE/SEP23/PV/01` — org, location,
project code, donor, month, sequence. We generate `REQ-0001`. **Generating
theirs instead is nearly free and means DOCex output files straight into their
existing system without translation.** That is a small change with a
disproportionate effect on whether this feels like their system.

---

## 5. Procurement evaluation scoring · MEDIUM-HIGH value · MEDIUM effort

Their evaluation sheet is a fixed 40-point matrix, four criteria at 10 each:

1. Compliance with requirements
2. Compliance with quality of service
3. Previous relationship with the organisation (past history)
4. Financial proposal

The example is instructive. Two vendors scored 10/10/0/10 and 10/10/0/5 — so
the decision came down entirely to the financial proposal, and *"previous
relationship"* scored zero for both because neither had one. That is a
defensible decision, but only because someone kept the sheet.

The evaluation report is a **required document** for anything above ₦500,000.
Producing it inside DOCex — criteria, scores, a computed total, and the
justification — turns a spreadsheet someone rebuilds each time into a record
that is consistent, comparable across procurements, and already attached to the
requisition it justifies.

It also feeds the vendor register: a vendor's score history is exactly what
*"previous relationship"* should be scored from next time, rather than
memory.

---

## 6. Partial payments: advance and balance · MEDIUM value · MEDIUM effort

Their memo template offers three shapes: *"full payment, 70% advance, or 30%
balance payment (in the event of balance payment, the advance should be clearly
stated with complete documentation)"*.

DOCex has no link between an advance and its balance. So:

- nothing checks that advance + balance equals the contract value
- nothing stops a balance being paid before delivery is evidenced
- nothing shows a supplier's outstanding commitment

The PO template also states **"Terms of Delivery: 100% Delivery"** and
**"5 Working Days Upon Receipt of Valid Invoice"** — real terms that could be
checked against rather than filed.

---

## 7. Multi-currency · MEDIUM value · MEDIUM-HIGH effort

Their cashbook carries **EXCHANGE RATE** and **CURR** columns. Donor funding
arrives in USD, GBP or EUR and is spent in naira; the rate used decides the
reported figure, and donors care which rate and which date.

DOCex is naira-only. This is fine today — every payment in six months of
cashbook is NGN — but it will surface the moment a donor asks for a report in
their own currency. Worth knowing about, not worth building yet.

---

## 8. Petty cash · MEDIUM value · LOW-MEDIUM effort

A separate account (B15 HQ Petty Cash), a monthly ledger, and a clear rule:
**outstanding petty cash must be retired before the next disbursement**. The
policy also allows a VISA card on management approval.

Same shape as advance retirement — a float, expenses against it, a reconcile,
and a block on the next float until it clears. Once retirement aging exists,
petty cash is largely the same engine.

---

## 9. Vendor prequalification · MEDIUM value · LOW effort

The policy requires vendors to be **prequalified before inclusion in the
preapproved list**, and the procurement committee approves that list. Below
₦200,000 they may only use **preapproved suppliers**.

Our vendor register has the right shape but no prequalification state and no
committee approval. It is a small addition — a status and who approved it — and
it makes the threshold rule enforceable rather than advisory.

---

## 10. Sole source justification · LOW-MEDIUM value · LOW effort

Sole sourcing above ₦1,000,000 needs ED **and** AED approval on a **Sole Source
Justification Form**. Our policy override is close in spirit — written reason,
named authority — but it is not the same artefact and does not carry the
committee recommendation the policy requires.

---

## What I would not build

Being clear about this matters as much as the list above.

- **A general ledger.** They have QuickBooks. We hand off to it.
- **A bidding portal.** They run RFQs by email and social media, and it works.
  Their RFQ terms are thorough and legally careful; a portal would be a worse
  version of something already fine.
- **M&E / MEAL.** Not our problem, and a large one.
- **Payroll for organisations that have not given us their rates.** Still off
  for NEEM, and it should stay off.

---

## Suggested order

**Before Wednesday (about two hours):**

1. Required documents per payment type — cheap, and visibly theirs
2. PV number format — nearly free, disproportionate effect

**Next (the real build):**

3. Advance retirement aging and escalation
4. Weekly payment schedule and GAPS export
5. Payment voucher PDF generation

**After that:**

6. Procurement evaluation scoring
7. Advance/balance linking
8. Vendor prequalification

**Later, or never:**

9. Multi-currency — when a donor asks
10. Petty cash — mostly free once retirement aging exists
