# How DOCex's engine compares to the ones already in the market

Benchmarked September 2026 against enterprise ERP approval engines (Oracle
Fusion, Dynamics), mid-market AP automation (Coupa, Tipalti, Stampli, Medius,
Ramp), nonprofit finance systems (Sage Intacct, Blackbaud Financial Edge), and
proper workflow engines (Camunda/BPMN + DMN).

Read the first section before the rest. The temptation after a benchmark is to
copy everything; most of what these systems have, DOCex should not want.

---

## 1. What DOCex already gets right — do not change these

**Deterministic-first is now the documented best practice, not a quirk.** The
2026 consensus on AI in compliance has converged on exactly the split
`CLAUDE.md` has stated from the beginning: the model handles semantic routing
of evidence to the relevant controls, and deterministic rule evaluation applies
the thresholds — specifically so model uncertainty cannot propagate into a
compliance decision, and so every verdict stays explainable. Tools that started
LLM-first are retrofitting this. DOCex started here. A code-level BLOCK
overriding the model is the single most defensible thing in the architecture.

**The audit trail is better than most of the mid-market.** Hash-chained,
append-only, with `verify_audit_chain()` and a frozen `TransactionRecord` at
payment. Most AP tools offer an audit *log*; few offer tamper-evidence. The
2026 audit-trail guidance asks for reproducible, traceable decisions with a
retained record — DOCex's chain answers that more strongly than a database
table with an `updated_at` column.

**Maker-checker is enforced, not advisory.** Nobody approves their own
requisition; overrides need a written reason, a named authority, and an amount
within that step's limit. That is the four-eyes principle implemented properly.

**One engine, one config file per client** is the same architectural bet Sage
Intacct made against Blackbaud, and it is the reason Intacct wins that
comparison: a cloud-native, configuration-driven core beats a product with
decades of per-client divergence. Onboarding as a JSON profile rather than a
consulting engagement is a genuine moat at this price point.

---

## 2. A control gap found during this benchmark — fix first

The vendor fraud literature is unanimous that the highest-frequency AP fraud is
not a fake invoice, it is a **redirected payment**: the payee is real, the work
is real, the bank account is not. The control is segregation between who
maintains vendor bank details and who raises or releases a payment.

**DOCex has the register, the bank verification, and the check — and then does
not compare the two numbers.**

`_check_vendor_bank_match()` in `requisitions.py` looks the vendor up, reads
`vendor.bank.account_number` from the register, and reports:

> "Bank account 0123456789 confirmed as 'Sahad Stores'"

…while the payment itself goes to `req.vendor_account`, a free-text field typed
on the form. The two are never compared. A requisition can pass `VENDOR_VERIFIED`
with a PASS, quoting a verified account number, and pay a different account
entirely. In the recording of the live demo the account number and bank were
typed by hand into the form with nothing checking them.

**Fix:** compare `req.vendor_account` against the register's verified account.
Equal → PASS as today. Different → FAIL, naming both numbers, releasable only
by the existing override path (written reason, named authority). Absent from
the form → fall back to the register's account rather than paying a blank.
This is a small change to one function and it closes the fraud that actually
happens. The same applies per-row to `Payee.account_number` in a batch.

Two adjacent controls worth having once that is done: log every change to a
vendor's bank details with who changed it and when, and require a second person
to confirm a bank-detail change (the callback-verification control, enforced in
software).

---

## 3. Where the engines are genuinely ahead

### 3.1 Routing conditions should be data, not one hardcoded field

Every serious engine separates a **rules engine** from the workflow: routing
decisions evaluate conditions over department, amount, requester role, category,
risk level and data sensitivity. Camunda formalises this as DMN — decision
tables kept beside the process so business logic is never buried in code.

`WorkflowStep` conditions on exactly one thing: `min_amount`. That is one
dimension out of six, and it is why NEEM's own signed policy cannot be expressed:

- "sole sourcing above ₦1,000,000 → ED and AED" — needs a *sourcing* condition
- "procurement above ₦2,000,000 → procurement committee" — needs a *category*
  condition
- "three quotes from ₦200,001" — a document-count rule, enforced nowhere today

This is the single highest-value architectural change, and it stays inside the
config-not-code philosophy: generalise `min_amount` into a small condition
object — amount range, categories, payment types, grant codes, sourcing method —
evaluated by the engine, authored in the profile JSON. No new product surface,
one new shape in a file that is already data.

### 3.2 Sequential and parallel, not only sequential

The standard pattern is hybrid: financial authority runs **sequentially** (each
level must clear before the next), while specialist reviews run **in parallel**
(compliance, legal, technical — any order, all must sign).

DOCex is strictly linear. NEEM's procurement committee is a parallel specialist
review sitting alongside the finance chain, and today it can only be modelled as
one more sequential step, which makes every large purchase slower than their own
policy requires.

### 3.3 SLA, reminders, escalation

Every engine benchmarked has configurable reminder and escalation triggers —
a step unactioned for N days notifies the approver, then their manager, then
surfaces as overdue.

DOCex has none. This matters more than its size suggests: **"approval delays —
payments stuck in someone's inbox" is NEEM's own number-two stated pain point.**
The product currently shows that a payment is stuck but does nothing about it.
Aging is already computed and displayed; escalation is the missing half.

### 3.4 Delegation / out-of-office

Standard everywhere (Oracle calls it delegating workflow; Dynamics separates
escalation, delegation and reassignment). It temporarily reassigns a person's
tasks without rewriting the chain's rules.

DOCex has nothing. An approver travels and the chain stops until they return.
For a four-step chain ending at the AED and ED, that is a real operational stall.

### 3.5 Dimensions, not flat codes

Sage Intacct's advantage in nonprofit finance is **dimensional accounting**:
every transaction is tagged across fund, grant, program, department and location
simultaneously, so donor reporting is a query rather than a custom report.

DOCex carries `project_code`, `grant_code` and `category` as flat optional
strings. NEEM's own data is already dimensional — project codes B2 to B24, a
separate bank account per project, donor names, account codes — and is being
flattened on the way in. Since donor reporting *is* the job in NGO finance, this
is the structural upgrade with the longest payoff, and the one to design before
there is too much data to migrate.

---

## 4. What not to copy

**Do not adopt Camunda or BPMN.** The concepts are right; the weight is wrong.
Camunda is enterprise Java process orchestration aimed at organisations with a
process-modelling function. Borrow the *separation* — rules as data, evaluated
by an engine — not the engine.

**Do not chase Coupa's breadth.** Spend management, sourcing, contract lifecycle
and supplier risk are a different product for a different buyer.

**Do not become the general ledger.** Oracle and Intacct are the books. DOCex is
the control layer in front of them, and the QuickBooks handoff is the right
shape for that relationship.

**Do not copy per-seat pricing**, which every one of these uses and which
punishes exactly the clients DOCex wants.

---

## 5. Order of work

1. **Vendor account comparison** (§2) — a control gap in a product sold on
   control. Small, and it closes the fraud that actually happens.
2. **Condition objects on workflow steps** (§3.1) — unlocks three NEEM policy
   rules that cannot be expressed today, including the ₦200,001 quote rule.
3. **SLA + escalation** (§3.3) — directly answers their second-ranked pain point.
4. **Delegation** (§3.4) — small, and removes a recurring operational stall.
5. **Parallel review steps** (§3.2) — needed for the procurement committee.
6. **Dimensions** (§3.5) — the largest, and the one that gets harder the longer
   real data accumulates. Design it before the pilot ends.

Items 1 to 4 are all CORE by the `docex-build-feature` triage: built once,
flagged, and available to every client afterwards. None of them is CUSTOM work
for NEEM, which is what makes them worth doing now rather than when the second
client asks.

---

## Sources

- [Approval workflow design patterns](https://www.cflowapps.com/approval-workflow-design-patterns/) · [Approval routing in ERP environments](https://www.intellichief.com/approval-routing-software/) · [Multi-level approval automation](https://kissflow.com/workflow/bpm/multi-level-capex-and-opex-approval-automation/)
- [Oracle: delegating workflow](https://docs.oracle.com/cd/E17984_01/doc.898/e14729/delegating_workflow.htm) · [Dynamics: escalation vs delegation vs reassign](https://community.dynamics.com/forums/thread/details/?threadid=4a43f0b1-0f28-40b9-bccc-faa063e37c84)
- [Camunda workflow patterns](https://docs.camunda.io/docs/components/concepts/workflow-patterns/) · [Migrating hardcoded workflow to Camunda](https://camunda.com/blog/2024/05/developer-guide-migrating-existing-workflow-camunda/)
- [Segregation of duties in AP](https://ramp.com/blog/accounts-payable/segregation-of-duties-in-accounts-payable) · [Maker-checker principle](https://en.wikipedia.org/wiki/Maker-checker) · [Protecting the vendor master file](https://sao.wa.gov/the-audit-connection-blog/protect-your-vendor-master-file-fraudsters) · [Vendor impersonation fraud in AP](https://www.corpay.com/resources/blog/prevent-vendor-impersonation-fraud-accounts-payable)
- [Sage Intacct vs Blackbaud for nonprofits](https://restrictedbooks.app/compare/versus/blackbaud-vs-sage-intacct/) · [Nonprofit fund accounting options compared](https://www.lucentive.com/nonprofit-fund-accounting-software)
- [AI audit trail requirements 2026](https://www.kognitos.com/blog/ai-audit-trail-requirements-2026-checklist/) · [Hybrid ML–LLM compliance auditing](https://www.mdpi.com/1999-5903/18/6/329) · [AP automation tools compared 2026](https://www.medius.com/blog/top-ap-automation-software-compared-features-fit-and-tradeoffs/)
