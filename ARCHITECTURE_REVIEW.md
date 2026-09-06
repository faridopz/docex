# Architecture Review — why it feels janky, and the shape it should be

**Verdict: you were right.** There are **two complete, parallel money-flow
systems** in the codebase that never touch each other. Everything else that
feels off follows from that.

---

## 1. The finding

```python
requisitions.py imports transactions?   0
transactions.py imports requisitions?   0
```

Two engines. Same job. No shared code, no shared reference series, no shared
audit trail.

| | **Gen 1 — `transactions.py`** | **Gen 2 — `requisitions.py`** |
|---|---|---|
| States | submitted → intake → compliance_review → finance_review → approval → paid | draft → in_review → approved → paid |
| Reference | `V1`, `C24` | `REQ-0001`, `TRANS-0001` |
| Policy checks | ✗ none | ✅ deterministic, on submit |
| Approval authority | department only | ✅ role + amount + override limit |
| Audit trail | status history | ✅ hash-chained, tamper-evident |
| Immutable record | ✗ | ✅ frozen `TransactionRecord` |
| Fed by | vouchers, payroll, attendance | requisitions |
| Screens | `/dashboard`, `/transactions/[ref]`, `/compliance/*` | `/requisitions`, `/payments`, `/audit` |

**This is exactly what you saw.** The voucher screenshot showing `V1` with a
plain status history and no policy checks is Gen 1. The `REQ-0002` screen with
a blocking check and an override that demands a reason is Gen 2.

Same product, two different systems, and which one a user lands in depends
entirely on which button they pressed.

## 2. The consequences

**46 screens, ~16 of them on the same flow.** `/compliance/submit`,
`/compliance/new`, `/compliance/check`, `/compliance/checks`,
`/compliance/pending`, `/compliance/board`, `/compliance/retire`,
`/vouchers/new`, `/requisitions/new`, `/transactions/[ref]`, `/payments`,
`/dashboard`, `/audit`… all answering *"money is going out, is it allowed?"*

**Two dashboards.** `/dashboard` reads Gen 1. `/requisitions` reads Gen 2. A
finance officer has to know which system a payment lives in to find it.

**The audit trail has a hole.** Vouchers and payroll go through Gen 1, which has
no hash chain and no policy checks. The product's central claim — *"every
exception recorded with who, why and under what authority"* — is only true for
requisitions. **This is the most serious item on this page.**

**Three ways to raise the same thing.** Vendor payment via `/requisitions/new`,
participant payment via `/vouchers/new`, advance retirement via
`/compliance/retire`. Different forms, different rules, different rigour.

**None of this was a bad decision.** It is what happens when a product is built
in layers under demo pressure: each generation was better than the last, and
nothing was ever removed. The cost only shows up now, when a real client is
about to use all of it.

---

## 3. How NEEM-type organisations actually work

From their policies, EVA's process map, and how NGO finance functions are
described in practice:

**The daily rhythm of a finance officer:**

- Enter every transaction the day it happens — payments, advances, retirements,
  cash receipts
- Review activity requests and prepare payment request forms
- Check every receipt and invoice for accuracy and completeness **with its
  supporting documents**
- Escalate anything unclear for management approval
- Petty cash on an imprest basis, spot-checked weekly
- Review staff retirements, process and file them
- Reconcile at month end

**The critical structural fact: it is one continuous loop, not a set of
features.** And every kind of money movement has the same seven beats:

```
REQUEST → CHECK → APPROVE → PAY → DOCUMENT → RECONCILE → AUDIT
```

What differs between a vendor invoice, a staff advance and a participant
payment is only **three things**:

1. **What starts it** — an invoice, a trip, an event, a payroll run, a low float
2. **What evidence it needs** — invoice + GRN, or a receipt, or an attendance
   sheet
3. **Who must approve** — a function of amount and payment type (the DOA)

Everything else is identical. **That is the whole insight.** The current design
treats those three variations as three products; they are one product with a
type field.

**One more thing the research makes clear:** advances are special because they
create a **debt that must come back**. An advance is not finished when it is
paid — it is finished when it is retired. EVA's policies do not even state a
retirement window, which is why the advance-aging report matters so much.

---

## 4. The shape it should be

### One spine, many entry points

```
   VENDOR INVOICE ─┐
   STAFF ADVANCE ──┤
   REIMBURSEMENT ──┼──▶  ONE PAYMENT REQUEST  ──▶ CHECK ──▶ APPROVE ──▶ PAY
   PARTICIPANTS ───┤     (type + evidence)         │          │          │
   PAYROLL ────────┤                          deterministic  DOA     immutable
   PETTY CASH ─────┘                             policy      chain    record
                                                                        │
                                          RECONCILE ◀── month-end ──────┤
                                                                        ▼
                                                                     AUDIT
```

**`requisitions.py` becomes the spine.** It is the better engine and it already
has everything the others lack: policy checks, override authority, the hash
chain, the frozen record.

**`payment_type` becomes a field on the request**, not a separate system:

```python
class PaymentType(str, Enum):
    VENDOR_INVOICE = "vendor_invoice"
    ADVANCE        = "advance"          # creates a retirement obligation
    REIMBURSEMENT  = "reimbursement"    # receipts already spent
    PARTICIPANT    = "participant"      # from a voucher
    PAYROLL        = "payroll"
    PETTY_CASH     = "petty_cash"
```

The existing engines stop being destinations and become **builders** that
produce a payment request: `vouchers.py` builds a PARTICIPANT request from
per-diem lines, `payroll.py` builds a PAYROLL request, `field_receipts.py`
attaches evidence to a REIMBURSEMENT. Each keeps its specialist arithmetic and
hands the result to one spine.

**One reference series. One status trail. One audit chain. One dashboard.**

### What this fixes, concretely

- The audit trail becomes true for **every** payment, not just requisitions
- `doa.py` (already built) governs everything, because everything is one request
- Month-end reconciliation has **one** table to reconcile against
- A finance officer learns one screen instead of three
- New payment types are a config change, not a new subsystem

### Screens: 46 → about 12

| Keep | Why |
|---|---|
| **Requests** (list + detail + new) | The one queue. Filter by type. |
| **Receipts** | Evidence capture — genuinely different work |
| **Payments** | The locked record |
| **Reconciliation** | Month end |
| **Audit** | The verdict |
| **Reports** | Draws on the above |
| **Settings** (org, departments, policy) | Config, incl. the self-service policy screen |
| **Login / setup** | — |

Everything under `/compliance/*` and `/transactions/*` folds into **Requests**.
Screening, Knowledge and Attendance stay as separate modules — they are genuinely
different products, already flagged, and correctly not part of this flow.

---

## 5. Making it simple to raise one

Today's form asks for everything at once with policy shown as guidance. What
NEEM's officers actually need is **one question at a time, with the policy
answering back as they type**:

```
Step 1   What kind of payment?        [Vendor] [Advance] [Reimbursement] …
                                       └─ determines the rest of the form

Step 2   Who and how much?            Vendor ▾   ₦ ______
                                       ⚠ live: "Above ₦300,000 — needs ED approval"
                                       ⚠ live: "Three quotations required at this amount"

Step 3   What is it for?              Category ▾  Project ▾  Grant ▾
                                       ⚠ live: "This grant closed 31 Dec 2024" ← blocks

Step 4   Evidence                     [drag a receipt]  ✓ invoice attached
                                       ⚠ live: "Missing: goods received note"

         ┌────────────────────────────────────────────┐
         │ THIS WILL GO TO                            │
         │ Compliance → Finance → TLFA → ED           │
         │ 1 blocking issue must be fixed first       │
         └────────────────────────────────────────────┘
                    [Save draft]  [Submit]
```

Three principles:

1. **Type first.** It decides which fields are even relevant. An advance needs a
   return date; a vendor invoice needs a GRN. Asking for both is what makes a
   form feel bureaucratic.
2. **Policy answers as you type**, not after you submit. The check engine already
   runs on every draft edit — the UI just needs to show it inline.
3. **Show the route before submitting.** *"This goes to the ED"* is the single
   most useful thing a submitter can know, and it comes free from `doa.py`.

---

## 6. Migration — without breaking NEEM

**The rule: NEEM is deploying. Nothing here may put that at risk.**

The good news is that this is mostly *deletion and redirection*, not rewriting.
Gen 2 already works and is well tested.

| Phase | Work | Risk |
|---|---|---|
| **0** *(done)* | Legacy intake screens flagged off | none |
| **1** | Add `payment_type` to `Requisition`, defaulting to `vendor_invoice` | very low — additive |
| **2** | `vouchers.py` builds a PARTICIPANT request instead of a Gen-1 transaction | medium — one seam, well tested |
| **3** | `/dashboard` reads Gen 2; `/transactions/[ref]` redirects to `/requisitions/[id]` | low |
| **4** | Fold `/compliance/*` payment screens into Requests | low — mostly deletion |
| **5** | Retire `transactions.py` once nothing imports it | low by then |
| **6** | The type-first form from §5 | medium — new UI |

**Phase 1 is genuinely small and unlocks the reporting and reconciliation work**,
because it gives every payment one shape to report on.

**Do this after NEEM's production deployment, not before.** The deployment is
days of configuration; this is weeks of engineering. A live client with a
problem outranks a cleaner architecture, every time.

---

## 7. What I would do, in order

1. **NEEM to production** — unchanged, still first
2. **Phase 1** — `payment_type` on the request. Small, additive, unblocks the rest
3. **Reconciliation** (NEEM's ask #2) — now has one table to reconcile
4. **Reports** — draws on reconciliation rather than duplicating it
5. **Phase 2–3** — vouchers onto the spine, one dashboard
6. **Phase 6** — the type-first form
7. **Phases 4–5** — delete the old screens and engine

**The single most valuable item is Phase 1.** Everything downstream — reports,
reconciliation, the simpler form, EVA's payroll — gets easier once every payment
is the same shape.

---

## Sources

- [How to Manage Cash Account and Transactions in NGOs — fundsforNGOs](https://www.fundsforngos.org/financial-management-for-ngos/manage-cash-account-transactions-ngos-ngo-financial-management-policy/)
- [UNFPA — Policy and Procedures on Management of Cash Disbursements](https://www.unfpa.org/sites/default/files/admin-resource/FINA_Cash_Disbursements.pdf)
- [2 CFR Part 200 Subpart D — Subrecipient Monitoring and Management](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-D/subject-group-ECFR031321e29ac5bbd)
- [2 CFR 200 Uniform Guidance: What Nonprofits Must Know](https://www.charitycharge.com/nonprofit-resources/2-cfr-200-uniform/)
- [USAID Standard Provisions for Non-U.S. Contractors](https://www.iavi.org/wp-content/uploads/2023/11/RFPs_Appendix-II-USAID-ADVANCE-CoAg-Standard-Provisions-Non-US-Contractors_Feb2020.pdf)
