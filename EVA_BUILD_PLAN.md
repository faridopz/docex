# EVA — Engineering Build Plan

**Education as a Vaccine (EVA) — donor-funded NGO finance & compliance platform.**
Separate org instance, shared engine core. Companion to `EVA_BUILD_SPEC.md`
(discovery + org analysis); this document is the *engineering* plan: which
engines run, what each owns, what's new, in what order, and how we know it works.

---

## 1. What we are building

A finance operations platform that takes EVA's five documented processes —
**cash disbursement, cash receipts, payroll, procurement, payroll schedule** —
and runs them through one auditable pipeline, with the **Compliance → Finance →
DOA → ED** approval chain enforced in software rather than by memory and email.

The product goal, stated the way EVA's own process map states it:
**be permanently ready for external audit.** Every naira traceable to a policy
clause, a document, an approver, and a timestamp.

---

## 2. Architecture principles (non-negotiable)

1. **Deterministic-first.** Code owns every number: amounts, deductions,
   allocations, thresholds, balances, budget checks, duplicate detection,
   reconciliation, DOA routing. The LLM never produces a figure that enters the
   ledger.
2. **Code-level BLOCK always wins.** No model output can overturn a deterministic
   block.
3. **The server owns evidence.** The LLM returns decisions + references; DOCex
   rehydrates authoritative policy text and document evidence.
4. **Append-only audit.** Every state change, approval and note is an immutable
   event carrying actor, department, timestamp, and reason.
5. **One engine, many orgs.** EVA runs its own instance and configuration, not a
   forked codebase.

---

## 3. Engine inventory

**Legend — Status:** `REUSE` = works as-is · `EXTEND` = small additions ·
`NEW` = build. **Mode:** `CODE` = deterministic · `AI` = model-assisted ·
`MIXED`.

### 3.1 Foundation engines (already built — EVA inherits)

| Engine | File | Status | Owns | Mode |
|---|---|---|---|---|
| Document extraction | `fast_extract.py` | REUSE | Parallel text extraction (PyMuPDF→pdfplumber, DOCX, XLSX); flags scans | CODE |
| Field extraction | `fast_fields.py` | EXTEND | Labelled-regex pull of invoice/PO/GRN no., totals, TIN, VAT, account no., dates | CODE |
| AP controls | `payment_checks.py` | EXTEND | Three-way match (invoice↔PO↔GRN + PO cross-ref, 1% tolerance), duplicate-invoice detection | CODE |
| Deterministic rules | `deterministic_checks.py` | EXTEND | Threshold, date-offset, membership, reference-lookup, outstanding-advance rules | CODE |
| Compliance engine | `compliance.py` | REUSE | Rulebook-driven semantic checks; lean output schema; code-block precedence | MIXED |
| Policy interpretation | `policy_rules.py` + `compliance.interpret_policy` | REUSE | Policy document → structured rulebook | MIXED |
| Transaction backbone | `transactions.py` | EXTEND | Reference (C24/V7), state machine, append-only history | CODE |
| Departments & routing | `departments.py` | REUSE | Org-defined departments; which department owns each stage | CODE |
| Notifications | `notification_center.py` | REUSE | In-app cross-department feed on every state change | CODE |
| Auth & RBAC | `auth.py` | EXTEND | Users, departments, roles (viewer/reviewer/approver/admin), PBKDF2 + HMAC sessions | CODE |
| Vouchers | `vouchers.py` | EXTEND | Consolidate payables → voucher → submit into workflow | CODE |
| Retirement reconciliation | `receipts.py` | REUSE | Advance vs actual spend, balance, recover/reimburse | CODE |
| Document completeness | `doc_completeness.py` | REUSE | Classify documents, required-document presence | CODE |
| Bank verification | `bank_verify.py` | REUSE | Account-name verification before disbursement | CODE |
| Assistant/narration | `assistant.py` | REUSE | Plain-English briefing of results | AI |

### 3.2 New engines (EVA-specific)

| # | Engine | File | Owns | Mode | Size |
|---|---|---|---|---|---|
| E1 | **Delegation of Authority** | `doa.py` | Amount band + payment type → required approver chain, incl. ED final authorisation | CODE | M |
| E2 | **Statutory deductions** | `deductions.py` | WHT, VAT, PAYE, pension — rate tables + computation + remittance schedule | CODE | M |
| E3 | **Coding & budget** | `coding.py` | Project/grant code, cost centre, expense code, office; budget-availability check | CODE | M |
| E4 | **Payroll** | `payroll.py` | Monthly schedule, gross→deductions→net, donor/project allocation splits, refinancing | CODE | L |
| E5 | **Grants & cash flow** | `grants.py` | Signed agreements, tranche schedules, expected vs requested vs received, variance/aging | CODE | L |
| E6 | **Procurement** | `procurement.py` | Request → budget check → quote thresholds → vendor selection → GRN → invoice | MIXED | M |
| E7 | **Cash receipts** | `cash_receipts.py` | Donor inflows, allocation to grant/code, bank reconciliation | CODE | S |
| E8 | **Accounting export** | `accounting_export.py` | QuickBooks/Tally journal + Excel exports with full coding | CODE | M |
| E9 | **Sub-recipient review** | `subrecipient.py` | Review sub-grantee financial reports against sub-award terms | MIXED | M |

---

## 4. Engine deep-dives

### E1 — Delegation of Authority (`doa.py`) · CODE

**Why:** EVA's process map routes every voucher "for approval in line with the
organisation's Delegation of Authority (DOA)", ending with **ED final
authorisation**. Today that lives in people's heads.

**Model**
```
DOAThreshold: min_amount, max_amount, currency, payment_type,
              required_approvers: [department_key | role], sequential: bool
DOAMatrix:    thresholds[], final_authority_department (EVA: "ed")
```
**Logic:** given `(amount, payment_type)` → resolve the band → produce the
ordered approver chain → drive `transactions.py` transitions. A transition to an
authorising state is **rejected** unless the acting user satisfies the current
step. Amount comparisons and band selection are pure arithmetic — never AI.

**Composes with:** `transactions.py` (states), `auth.py` (role check),
`notification_center.py` (notify the next approver), `departments.py` (who).

**Tests:** band boundaries (exactly at threshold, just under/over), missing band,
wrong-approver rejection, chain order enforced, ED-last, currency mismatch.

---

### E2 — Statutory deductions (`deductions.py`) · CODE

**Why:** Compliance's first job on every payment is that "**required deductions
are captured**" — WHT, VAT, PAYE, pension. Pure arithmetic against rate tables;
exactly the kind of thing an LLM must never estimate.

**Model**
```
DeductionRule: code ("WHT-SERVICES"), basis (gross|net|taxable),
               rate_percent, applies_to (vendor_type|payment_type),
               threshold_min, statutory_reference
DeductionResult: code, base_amount, rate, amount, net_after, reference
```
**Logic:** classify the payment (services / goods / rent / consultancy), apply
each matching rule to the correct base, compute deduction and net payable,
produce a **remittance schedule** (what's owed to FIRS/state IRS/pension PFA and
when). Rates are **configuration**, not code — they change with law.

**Guard rail:** if the extracted invoice total is low-confidence, we do NOT
compute silently — we surface `insufficient_evidence` and ask for confirmation.

**Tests:** each deduction type, VAT-inclusive vs exclusive invoices, threshold
edges, exempt vendors, multiple simultaneous deductions, rounding to kobo,
remittance grouping by month.

---

### E3 — Coding & budget (`coding.py`) · CODE

**Why:** EVA is a USG-funded prime with **per-grant compliance**; Finance's
review step is explicitly "availability of budget under the relevant project or
cost centre", and every transaction is recorded "under the appropriate project
and expense codes".

**Model**
```
Project:    code, donor, title, start, end, currency, status
CostCentre: code, office (HQ|state|field), title
ExpenseCode: code, title, account_mapping (for QuickBooks)
BudgetLine: project_code, cost_centre, expense_code, period, budgeted,
            committed, actual   → available = budgeted - committed - actual
```
**Logic:** validate the coding triplet on every transaction; compute
availability; **block** when a request exceeds the available balance (a hard,
deterministic block); track commitments so a raised-but-unpaid PO reserves funds.

**Tests:** over-budget blocks, commitment reserves funds, period boundaries,
invalid code combinations, multi-project split coding.

---

### E4 — Payroll (`payroll.py`) · CODE

**Why:** the biggest new module, and EVA's stated monthly need: salaries paid,
each linked to **donor + project code**, with **people supported directly and
indirectly**, an approval flow, and **refinancing carried as a negative**.

**Model**
```
StaffRecord:   staff_id, name, position, office, gross_salary, bank, pension_id, tax_id
Allocation:    staff_id, project_code, donor, percent   (Σ percent per staff == 100)
PayrollRun:    period (YYYY-MM), lines[], totals_by_project, totals_by_donor,
               beneficiaries_direct, beneficiaries_indirect, status, txn_ref
PayrollLine:   staff_id, gross, deductions[DeductionResult], net,
               allocations[], refinancing_amount (signed)
```
**Logic:**
1. Build the schedule from staff records (their five fields: Name, Position,
   Gross, Statutory Deductions, Net Pay).
2. Deductions via **E2** (PAYE, pension) — never re-implemented here.
3. **Allocation split** across donors/projects; code *enforces* Σ = 100% and
   rejects the run otherwise — a silent 97% split is a donor-compliance incident.
4. Roll up totals per project, per donor, per office.
5. **Refinancing / cost recovery** carried as a **signed** amount with an
   explicit `sign_convention` setting so it offsets the expense line as EVA
   expects.
6. Route through **E1 (DOA)** → ED authorisation → payment.

> ⚠ **Blocking question before coding §5:** confirm that "refinancing" = amount
> recovered from a donor against staff cost, and that the negative renders it a
> credit against that project's expense line. The engine is written so this is a
> one-line configuration flip, but we confirm before shipping — a wrong sign
> convention in payroll is a serious defect, not a cosmetic one.

**Tests:** Σ-allocation enforcement (99%/101% rejected), gross→net accuracy,
multi-donor split staff, refinancing sign both ways, period immutability once
approved, headcount roll-ups, re-run idempotency.

---

### E5 — Grants & cash flow (`grants.py`) · CODE

**Why:** the "monthly compliance system" — table every signed agreement and
compare **expected vs requested vs actually received**, per project.

**Model**
```
Agreement:     id, donor, project_code, signed_date, value, currency,
               start, end, document_ref
Tranche:       agreement_id, due_date, expected_amount, condition
FundingRequest: agreement_id, period, requested_amount, submitted_date
CashInflow:    agreement_id, received_date, amount, bank_ref, allocated_code
CashFlowRow:   period, project, expected, requested, received,
               variance (= received - expected), days_outstanding
```
**Logic:** deterministic joins + arithmetic across the four record types →
monthly matrix, variance, aging of late tranches, per-donor totals. Feeds the
**Excel monthly report** and the dashboard.

**Tests:** partial tranches, over/under receipt, FX where currencies differ,
aging buckets, agreements with no inflow yet, period roll-forward.

---

### E6 — Procurement (`procurement.py`) · MIXED

**Why:** their documented procurement process, with the quote-count rule that is
a classic deterministic control.

**Logic (code):** budget availability via **E3**; **quotation-count rule** by
threshold band (e.g. ≥3 quotes above ₦X); vendor on approved list; **three-way
match + duplicate detection** via existing `payment_checks.py`; DOA via **E1**.
**Logic (AI, narrow):** read messy quotes/bid analyses, and judge genuinely
semantic questions — e.g. *does this sole-source justification satisfy the
policy's exception clause?* Also flags collusion signals (identical addresses on
"competing" quotes) for human review — never auto-blocks on that alone.

**Tests:** below/above quote threshold, insufficient quotes blocked, unapproved
vendor, GRN quantity mismatch, sole-source with/without justification.

---

### E7 — Cash receipts (`cash_receipts.py`) · CODE

Donor funds received → verify against bank statement/transfer confirmation →
allocate to grant/project/account code → reconcile. Feeds **E5**'s "actually
came" column. Small engine; mostly recording + allocation + reconciliation math.

**Tests:** unallocated receipt flagged, partial allocation, duplicate receipt,
bank-reference matching.

---

### E8 — Accounting export (`accounting_export.py`) · CODE

**Why:** EVA lives in **QuickBooks** (Tally referenced too). If DOCex doesn't
export cleanly, it creates double entry work and won't be adopted.

**Output:** journal entries (debit/credit, account mapping from **E3**, project +
cost centre + expense code, memo, date) as QuickBooks-compatible file, plus the
Excel workbooks: **payments register**, **payroll schedule**, **monthly cash-flow
matrix**, **deduction remittance schedule**.

**Tests:** balanced journals (Σ debits = Σ credits), coding present on every line,
Excel round-trip, large-batch export.

---

### E9 — Sub-recipient review (`subrecipient.py`) · MIXED

EVA is a pass-through: the Compliance Officer must "facilitate external quality
assurance review of sub-recipient financial documents" and mentor sub-recipients.
Reuses the existing compliance engine with a **sub-award rulebook**; adds
per-sub-recipient tracking of findings and corrective actions.

---

## 5. Data model additions (summary)

New: `DOAThreshold`, `DOAMatrix`, `DeductionRule`, `DeductionResult`, `Project`,
`CostCentre`, `ExpenseCode`, `BudgetLine`, `StaffRecord`, `Allocation`,
`PayrollRun`, `PayrollLine`, `Agreement`, `Tranche`, `FundingRequest`,
`CashInflow`, `CashFlowRow`, `PurchaseRequest`, `Quotation`, `Vendor`,
`SubRecipient`.

Extended: `Transaction` gains `project_code`, `cost_centre`, `expense_code`,
`office`, `payment_type`; `TxnKind` gains `payroll_run`, `purchase_request`,
`cash_receipt`.

---

## 6. How the engines compose (disbursement, end to end)

```
Program raises request + documents
   │
   ├─ fast_extract ──► text (parallel)
   ├─ fast_fields  ──► invoice/PO/GRN no., totals, TIN, dates      [CODE]
   ├─ doc_completeness ► required documents present?               [CODE]
   │
   ├─ COMPLIANCE STAGE
   │    ├─ payment_checks  → three-way match, duplicates           [CODE]
   │    ├─ deductions (E2) → WHT/VAT/PAYE captured?                [CODE]
   │    ├─ deterministic_checks → thresholds, dates, references    [CODE]
   │    └─ compliance.py   → semantic policy rules only            [AI]
   │        └─ any code BLOCK ⇒ stop here, no model call
   │
   ├─ FINANCE STAGE
   │    ├─ coding (E3) → valid project/cost-centre/expense code    [CODE]
   │    └─ coding (E3) → budget availability                       [CODE]
   │
   ├─ VOUCHER raised (vouchers.py)                                 [CODE]
   ├─ DOA (E1) → approver chain by amount + type                   [CODE]
   ├─ TLFA processes on bank platform → ED final authorisation     [in-app]
   ├─ transactions.py → state + append-only audit trail            [CODE]
   ├─ notification_center → next department notified               [CODE]
   └─ accounting_export (E8) → QuickBooks journal + Excel          [CODE]
```

---

## 7. Phase plan

Each phase ends with: tests green, engine benchmarked where relevant, and a
demo EVA can actually click through.

### Phase 0 — Instance setup · S
Stand up EVA's own instance; configure departments (**Program, Compliance,
Finance, TLFA, ED**) and route stages (`approval` → ED). Load their policy
document into a rulebook. Create users/roles.
**Acceptance:** an EVA user logs in and sees their department's queue.

### Phase 1 — Disbursement backbone (E1 + in-app approvals) · M
DOA matrix engine; ED final-authorisation stage on the state machine; approval
chain enforced; notifications to the next approver.
**Acceptance:** a voucher walks Program → Compliance → Finance → DOA → ED → Paid
entirely in-app, with a complete audit trail; a reviewer cannot self-authorise.

### Phase 2 — Money correctness (E2 + E3) · M
Statutory deductions + coding/budget availability wired into the Compliance and
Finance stages.
**Acceptance:** a payment missing WHT is flagged deterministically; an
over-budget request is blocked with the budget line cited.

### Phase 3 — Payroll (E4) · L  *(gated on the refinancing confirmation)*
Monthly schedule, deductions, donor/project allocation with Σ=100% enforcement,
refinancing sign convention, beneficiaries direct/indirect, DOA → ED → payment.
**Acceptance:** a month's payroll produces a correct schedule, per-donor and
per-project totals reconcile to the gross, and the run is approved and paid
in-app.

### Phase 4 — Monthly compliance / cash flow (E5 + E7) · L
Agreements register, tranche schedules, funding requests, inflows; the monthly
expected-vs-requested-vs-received matrix with variance and aging.
**Acceptance:** the monthly table matches EVA's own manual numbers for a test
month — the strongest possible validation.

### Phase 5 — Procurement (E6) · M
Request → budget → quotes → vendor → GRN → invoice → payment, with quote-count
thresholds and the existing three-way match.
**Acceptance:** an under-quoted procurement is blocked; a compliant one flows to
payment.

### Phase 6 — Exports & accounting (E8) · M
QuickBooks journals + the four Excel workbooks.
**Acceptance:** a month's activity imports into QuickBooks with correct coding
and balanced journals.

### Phase 7 — Sub-recipient review (E9) + hardening · M
Sub-award rulebook, findings/corrective-action tracking; then durable storage
(Postgres + object store), backups, and multi-office reporting.

---

## 8. The AI boundary (explicit)

**AI is used for:** reading messy/scanned documents, classifying document types,
interpreting free-text justifications, judging genuinely semantic policy clauses,
fuzzy name matching (with code confirming), drafting human-readable summaries,
reviewing sub-recipient narrative reports.

**AI is NEVER used for:** any amount, deduction, allocation percentage, balance,
budget availability, threshold decision, DOA routing, duplicate detection,
reconciliation, journal entry, or final verdict where code has spoken.

---

## 9. Testing strategy

- **Unit tests per engine** — every boundary condition above; deterministic
  engines are pure functions and must be exhaustively tested (they own money).
- **Golden-file tests** — real EVA documents (anonymised) → expected verdicts.
- **Workflow tests** — full state-machine walks incl. permission denials.
- **Reconciliation tests** — Phase 4's "matches their manual numbers" check.
- **Regression suite** — the existing 9 suites must stay green; EVA work must not
  degrade the shared core.

---

## 10. Deployment & infrastructure

Start on the current stack (containerised API + Next.js front end) as a
**separate EVA instance** with its own data. Two upgrades are required before
real operational use:
1. **Durable storage** — Postgres for records + object storage for documents.
   Ephemeral disk is acceptable for a demo, not for audit records.
2. **Backups + retention** — audit trails must survive redeploys, and donors
   expect multi-year retention.
Keep-warm/always-on to remove cold-start latency.

---

## 11. Risks & open questions

| # | Item | Why it matters | Action |
|---|---|---|---|
| 1 | **"Refinancing" sign convention** | Wrong sign corrupts payroll + donor reporting | Confirm with EVA before Phase 3 |
| 2 | Statutory rates (WHT/VAT/PAYE/pension) | Rates change by law and vendor type | Get their current rate table; keep as config |
| 3 | DOA thresholds | Drives every approval | Obtain the actual DOA matrix document |
| 4 | Chart of accounts | Needed for QuickBooks export | Export their existing CoA |
| 5 | Scanned documents | No OCR wired today | Assess volume of image-only docs; add OCR only if evidenced |
| 6 | Durable storage | Audit records must persist | Phase 7 at the latest; earlier if they go live |
| 7 | Multi-office rollout | HQ vs state offices differ | Confirm whether state offices transact directly |

---

*One engine core, two organisations. TA Connect and EVA share the deterministic
foundation — extraction, AP controls, transactions, departments, notifications,
compliance — and differ only in configuration and their own domain engines.*
