# EVA (Education as a Vaccine) — Build Spec

Decision: **EVA is a SEPARATE org build**, not a tenant inside TA Connect's instance.
Same underlying engine, separate deployment + separate data. See "What separate
means" below so we don't accidentally fork the codebase.

Sources: EVA's four finance role descriptions (Team Lead / Coordinator / Officer /
Compliance Officer), the "Key Finance Process Descriptions (Prepared for External
Audit Review)" process map, and Farid's added requirements.

---

## 1. Who EVA is

Nigerian NGO, donor-funded (notably **USG** + others), operating **HQ + State +
field offices**. Acts as a **prime/pass-through** — manages sub-recipients and
reviews their financial reports. Runs on **QuickBooks** (Tally mentioned too).
Regulated: **SCUML / AML-CFT**, PAYE, WHT, VAT, annual returns. Staff certified
ICAN/ACCA. Their process map exists explicitly **for external audit review** —
audit-readiness is the product's north star.

**Finance hierarchy (drives roles + approvals):**
ED / Board → **Admin/Finance Team Lead (TLFA)** → Finance Coordinator →
Finance Officer / Assistant. **Compliance Officer** sits in Finance but reports to
**ED/Board** (independence) and reviews *every* payment.

---

## 2. EVA's disbursement flow (from their own process map)

```
Program/Admin initiates request + supporting docs
  → COMPLIANCE review (deductions captured, approvals obtained, docs complete,
                        donor rules met)
  → FINANCE review (completeness, accuracy, budget availability by project/cost centre)
  → Payment voucher raised
  → Approval per DELEGATION OF AUTHORITY (DOA)
  → TLFA processes payment on the bank platform
  → ED final authorisation
  → Recorded in accounting system under project + expense codes
  → Filed for audit
```

This is nearly identical to the transaction state machine already built in DOCex
(`submitted → compliance_review → finance_review → approval → paid`). The delta is
an **ED final-authorisation** stage after TLFA processing, and **DOA-driven**
routing.

---

## 3. The new layer Farid was advised to add

### 3.1 Monthly compliance system — agreements vs cash flow
Table every **signed agreement** and reconcile, per project, monthly:
- **Expected** — what the agreement/tranche schedule says should come in
- **Requested/invoiced** — what we asked the donor for
- **Actual received** — what actually hit the bank
- **Variance + aging** — shortfall, late tranches

Deterministic arithmetic (code owns it). Output: a monthly table + Excel export.
Data model: `Agreement (donor, project_code, value, currency, start/end,
tranche_schedule[])`, `ExpectedInflow`, `ActualReceipt` (ties to the Cash Receipt
process in their map).

### 3.2 Procurement flow + custom finance process
```
Purchase request (department)
  → Finance confirms BUDGET AVAILABILITY
  → Procurement sources quotations (count required by threshold band)
  → Vendor selection per policy
  → DOA approval
  → Delivery + verification by requesting unit (GRN)
  → Invoice processed by Finance → payment
```
Deterministic: threshold → number of quotes required; budget check; **three-way
match + duplicate detection already built** in `payment_checks.py`.

### 3.3 Payroll / salary allocation ("refinancing")
Monthly: staff paid salary; each salary **linked to the donor + project code**
funding it; track **people supported directly and indirectly**; **approval flow**;
once approved, payment goes through. **Refinancing inflow is represented as a
NEGATIVE** — particularly for salaries.

Deterministic engine:
- Gross → statutory deductions (**PAYE, pension**) → net (their payroll schedule
  fields: Staff Name, Position, Gross, Statutory Deductions, Net Pay)
- **Allocation split** per staff across donors/project codes — splits must sum to
  100% (level-of-effort); code enforces it
- Roll-ups: total per donor, per project code, per month
- Refinancing/recovery amount carried with a **sign convention** so it offsets cost

⚠ **OPEN QUESTION — "refinancing".** I don't want to guess at finance semantics.
My working interpretation: it's **cost recovery / recharge** — salary cost charged
back to a donor grant, shown as a negative because it *offsets* the expense in the
schedule. Needs confirming with EVA before coding, because a wrong sign convention
in a finance system is a serious defect. Ask them: *is "refinancing" the amount
recovered from a donor against staff cost, and does the negative make it a credit
against the project's expense line?*

### 3.4 Approval flow
Explicit approval gate before payment across all of the above, driven by the **DOA
matrix** (amount band → required approver), ending at **ED authorisation**.

---

## 4. What DOCex already gives EVA (~70%)

Reusable as-is: transaction backbone + reference/status trail, per-department
in-app notifications, per-department dashboards, voucher building, **deterministic
AP controls** (three-way match, duplicate invoice), the rulebook/policy engine,
compliance checking, audit trail, Excel export.

## 5. Net-new for EVA

| # | Module | Deterministic? | Notes |
|---|---|---|---|
| 1 | DOA matrix engine (amount → approver) | Yes | formalises existing approval chain |
| 2 | Statutory deductions (PAYE, pension, WHT, VAT) | Yes | Compliance's "deductions captured" becomes code |
| 3 | Project / cost-centre / expense coding + budget availability | Yes | every txn grant-coded |
| 4 | ED final-authorisation stage | Yes | add to state machine |
| 5 | Payroll module + donor/project allocation ("refinancing") | Yes | §3.3 |
| 6 | Agreements ↔ cash-flow monthly reconciliation | Yes | §3.1 |
| 7 | Procurement request → quotes → GRN → invoice | Mixed | §3.2 |
| 8 | Cash receipts / receivable liquidation | Yes | their process #2 |
| 9 | QuickBooks/Tally journal export | Yes | they live in QuickBooks |
| 10 | Multi-office (HQ / State / field) dimension | Yes | entity dimension on txns |
| 11 | Beneficiaries supported (direct/indirect) | Yes | reporting metric |

## 6. Differences vs TA Connect

| | TA Connect | EVA |
|---|---|---|
| Centre of gravity | Screening applications + paying event participants | Internal payment ops + audit readiness |
| Core objects | Applicants, attendance, per-diem, travel claims | Payment vouchers, payroll, agreements, procurement |
| Approvals | Light chain | Formal **DOA** + **ED** authorisation |
| Statutory | Minor | **Central** (PAYE/WHT/VAT/pension, SCUML) |
| Grant coding | Light | **Every transaction** project/cost-centre coded |
| Accounting system | — | **QuickBooks** (export required) |
| Structure | Single team | HQ + State + field offices |
| Payroll | None | **Monthly, donor-allocated** |

## 7. What "separate" should mean (important)

Separate **org instance + data + deployment**, but **NOT a forked engine**:
- Keep the deterministic core, transaction/state machine, notifications, and
  compliance engine as the shared foundation.
- EVA gets its own configuration: departments (Program / Compliance / Finance /
  TLFA / ED), DOA matrix, rulebook, project codes, deduction rates.
- EVA-specific modules (payroll, agreements, procurement) live as their own
  modules — additive, not rewrites.
- Rationale: two divergent codebases would double every future fix (the perf work
  we just did would have to be done twice).

## 8. Meanwhile — updates DOCex needs regardless

1. **Custom departments per org** (EVA needs Program/Compliance/Finance/TLFA/ED —
   not the hard-coded four).
2. **In-app approvals as the primary path** — approve/return inside the app from
   the department queue, replacing the emailed magic-link as the main route.
3. Admin screen to create departments + assign users (so finance vs compliance
   sections are actually visible/usable).
4. Keep-warm fix for the cold start (the latency users actually feel).

## 9. Suggested build order for EVA

- **Phase 1 (fastest visible value):** departments + DOA + ED stage + in-app
  approvals → EVA's disbursement flow works end-to-end.
- **Phase 2:** statutory deductions + project/cost-centre coding + budget check.
- **Phase 3:** Payroll + donor allocation ("refinancing") — after the sign
  convention is confirmed.
- **Phase 4:** Agreements ↔ cash-flow monthly reconciliation + Excel.
- **Phase 5:** Procurement flow; then QuickBooks export.

---

*Deterministic-first still governs: code owns every amount, deduction, allocation
split, threshold and reconciliation. AI reads messy documents and judges genuinely
semantic policy questions — never the numbers.*
