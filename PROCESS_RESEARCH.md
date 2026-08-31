# How donor-funded orgs actually run money — and what DOCex does about it

Research into the standard processes at donor-funded NGOs, each mapped to what
DOCex enforces today, what it half-does, and what it doesn't touch. Sources at
the bottom.

The recurring theme: **most audit findings are arithmetic or date checks that a
human forgot, not judgement calls.** Those are exactly what code should own.

---

## 1. Advance requests and retirement

**How it works.** Staff take a cash advance before field activity, then
"retire" it afterwards by submitting receipts. The finance team reconciles
receipts against the advance and either reimburses an overspend or recovers the
unspent balance.

**What the standard says**

- Advances are liquidated **within about a week** of the activity ending.
- Unspent cash is **returned immediately**, with the deposit receipt attached.
- Finance keeps a **monthly schedule of unretired advances** for follow-up.

**DOCex today**

| Piece | Status |
|---|---|
| Reconcile receipts vs advance, compute balance and direction | ✅ `receipts.py` |
| Recover-vs-reimburse decision | ✅ deterministic |
| **Retirement deadline (e.g. 7 days) enforced** | ❌ not built |
| **Aged listing of outstanding advances** | ❌ not built |
| **Block a second advance while one is unretired** | ❌ not built |

**Gap that matters.** The engine can reconcile a retirement but nothing *chases*
one. An advance taken in March and never retired is invisible until an auditor
finds it. The aging report is the single highest-value addition here, and it is
straightforward — `grants.py` already has aging logic to copy.

---

## 2. Procurement thresholds

**How it works.** Spend above a threshold requires competition — quotes, then
tenders. Thresholds are set per org, usually anchored to donor rules.

**Typical tiers** (US federal / 2 CFR 200 lineage, widely mirrored by others):

| Band | Requirement |
|---|---|
| Micro-purchase (often ~$3.5k–10k) | No quotes needed if price is reasonable |
| Small purchase (to ~$250k) | Quotes from "an adequate number" — most orgs write **three** |
| Above that | Full RFP / competitive proposals |

Nigerian NGOs typically set much lower naira bands, but the shape is identical.

**DOCex today**

| Piece | Status |
|---|---|
| Amount ceiling per requisition | ✅ `AMOUNT_LIMIT` |
| Approval steps escalate by amount (`min_amount`) | ✅ workflow steps |
| Required-document list | ✅ `DOCS_COMPLETE` — but it's one flat list |
| **Threshold-banded requirements ("3 quotes above ₦500k")** | ❌ not built |
| **Quote count / comparison** | ❌ not built |
| **Sole-source justification** | ❌ not built |

**Gap that matters.** `required_documents` is a single list applied to every
requisition regardless of size. Real policy is banded: a ₦20,000 taxi needs a
receipt, a ₦2,000,000 vehicle needs three quotes and a committee memo. Asking
for three quotes on a taxi trains people to ignore the check — which is worse
than not having it.

This is the **most valuable single feature** on this list, because
"procurement without competition" is a top-tier audit finding and it's pure
arithmetic to detect.

---

## 3. Cost allowability (2 CFR 200 and equivalents)

A cost charged to a grant must be:

| Criterion | Deterministic? | DOCex |
|---|---|---|
| Incurred **inside the budget period** | Yes — date comparison | ✅ **just built** (`GRANT_PERIOD`) |
| **Adequately documented** | Yes — presence check | ✅ `DOCS_COMPLETE` + receipt validation |
| Within the **approved budget line** | Yes — arithmetic | ⚠️ `grants.py` has the data; not wired to requisitions |
| Not **double-charged** to two grants | Yes | ⚠️ partial — receipt double-claim now caught, but not the same cost split across two grants |
| **Necessary and reasonable** | No — judgement | LLM territory, correctly |
| **Consistent treatment** | No — judgement | Not attempted |

**Gap that matters.** Budget-line availability. `grants.py` knows agreement
values and tranches; `requisitions.py` never asks whether money remains on the
line being charged. An org can approve past its budget and only discover it at
reporting. The engine exists — it just isn't connected.

---

## 4. Three-way match (invoice / PO / goods received)

**How it works.** Before paying a supplier, match the invoice to the purchase
order and the goods-received note. Quantities and amounts must agree.

**DOCex today.** ✅ `payment_checks.py` implements it, and batch runs it too
(fixed in the Phase 3 work). This is genuinely solid.

**Caveat.** It runs in the compliance-check path, not in the requisition policy
engine. A requisition raised directly doesn't get a three-way match unless the
documents are routed through the check flow. Worth unifying.

---

## 5. Per diem

**How it works.** Participants and staff get a daily allowance, reduced when the
org already provides a meal or accommodation.

**DOCex today.** ✅ `per_diem.py`, coverage-weighted, with the policy held as
**data on the rate card** rather than in code — which is the right shape, since
every org's rates differ and they change yearly.

---

## 6. Payroll and statutory deductions

Nigerian payroll carries PAYE and PENCOM; grant-funded staff are usually split
across several grants by an agreed allocation percentage.

**DOCex today.** ✅ `payroll.py` computes deductions and allocations
deterministically.

**Gap.** Allocation percentages must sum to 100% across grants and must respect
each grant's period — the same period logic just added for requisitions applies
to payroll allocations and isn't wired there.

---

## 7. What auditors actually ask for

From the audit-readiness literature, the recurring requests:

1. A **complete list of transactions** for the period — ✅ `/payments`
2. **Supporting documents** for a sample — ⚠️ receipts are linked, but there's
   no "pull the evidence pack for these 20 transactions" export
3. **Every exception, with who authorised it and why** — ✅ `/audit`, and this
   is genuinely strong: the engine refuses an unexplained override
4. **Proof the record wasn't altered** — ✅ hash-chained audit log
5. **Bank reconciliation** — ❌ not built

Point 3 is DOCex's real differentiator and it's worth saying plainly in a
pitch: most systems *record* an override, few *refuse* an unexplained one.

---

## Priority order, if it were my call

1. **Banded procurement rules** — biggest compliance gap, pure arithmetic,
   directly prevents a top-tier audit finding.
2. **Advance aging report** — cheap to build, immediately useful daily, and it
   makes an invisible problem visible.
3. **Budget-line availability** — the engine is already written; connect it.
4. **Auditor evidence-pack export** — turns the audit view into something you
   hand over rather than read on screen.
5. Unify three-way match into the requisition path.

---

## Sources

- [Procedures for salaries and advances in NGOs — fundsforNGOs](https://www.fundsforngos.org/financial-management-for-ngos/procedures-salaries-advances-ngos-ngo-financial-management-policy/)
- [Financial Policy and Procedures Manual — Integrity Action](https://www.integrityaction.org/media/4952/6-financial-policies-and-procedures.pdf)
- [NACO guidelines on financial & procurement systems for NGOs/CBOs](https://naco.gov.in/sites/default/files/NACO%20Guidelines%20on%20Financial%20&%20Procurement%20Systmes%20for%20NGOs-CBOs.pdf)
- [2 CFR 200 Subpart E — Cost Principles (eCFR)](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E)
- [2 CFR 200 Subpart E noteworthy items — US Dept of Education](https://www.ed.gov/sites/ed/files/policy/fund/guid/uniform-guidance/selectitemsofcost.pdf)
- [Sample Non-Profit Procurement Policy — HUD Exchange](https://files.hudexchange.info/resources/documents/SampleProcurementPolicy_Handout6.pdf)
- [Procurement solicitation and selection — NGOConnect](https://www.ngoconnect.net/sites/default/files/resources/Compliance%20-%20Procurement%20Soliciation%20and%20Selection.pdf)
- [Guide to federally funded procurement — UGA](https://onesource.uga.edu/wp-content/uploads/federally_funded_procurement.pdf)
