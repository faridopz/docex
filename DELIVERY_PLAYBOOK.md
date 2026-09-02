# Delivery Playbook — how DOCex builds for clients

**The model:** a software factory, adapted for a two-person shop.
**The promise to a client:** you get a system fitted to how you work.
**The promise to yourself:** you never build the same thing twice.

---

## Why this document exists

Consulting dies one of two ways. Either you fork the codebase per client and
spend year two fixing every bug five times, or you say yes to everything and
scope creep eats the margin. Both are failures of *process*, not of skill.

The factory model fixes it by separating **what varies** (the client) from
**what is manufactured once** (the engine), and by putting a decision gate
between a client's request and your keyboard.

The reference is 8090's Software Factory — Chamath Palihapitiya's argument that
time-and-materials outsourcing is losing relevance because AI changes the unit
of production from *hours* to *work orders that accumulate institutional
knowledge*. Their line worth stealing: institutional knowledge should
**accumulate rather than evaporate.** A workshop rebuilds. A factory reuses.

You are not 8090 — they raised $135M and sell $1M/year engagements. But the
structure scales down cleanly, and adopting it now is what lets you go from
one client to ten without hiring five people.

---

## 1. The triage gate — the single most important discipline

Every client request, without exception, is classified before any code is
written. Three outcomes:

| | **CONFIG** | **CORE** | **CUSTOM** |
|---|---|---|---|
| What it is | A value in their profile | A capability in the shared engine | A module only this client gets |
| Effort | Minutes to hours | Days | Weeks |
| Who benefits | This client | **Every client, now and future** | This client only |
| Cost to them | Included | Included | **Quoted separately** |
| Example | "Our ceiling is ₦2m" | "Block payments outside the grant period" | "Export to our 2009 Tally build" |

**The rules:**

1. **Default to CONFIG.** If it can be a profile field, it is a profile field.
2. **Prefer CORE over CUSTOM, always.** If two clients could plausibly want it,
   it goes in the engine behind a feature flag. You build it once and it
   becomes part of what you sell to client three.
3. **CUSTOM is a last resort and it is priced.** Genuinely client-specific work
   — their bespoke accounting system, their unique regulator — is a separate
   line item. Saying "that's custom, here's the quote" is not friction; it is
   the conversation that keeps you solvent.
4. **Nothing is built without a classification.** If you can't classify it, you
   don't understand the request yet. Go back and ask.

### Worked example — NEEM's three asks

| Request | Class | Why | Effort |
|---|---|---|---|
| Vendor TIN validation | **CORE** | Every Nigerian NGO has this audit requirement. Behind `tin_verification`. | ~2 days |
| Month-end bank reconciliation | **CORE** | Universal finance need. Behind `bank_reconciliation`. | ~1 week |
| FIRS live API lookup | **CUSTOM → paid add-on** | Nigeria-specific, external dependency, ongoing API cost | ₦100k + ₦50k/mo |
| Their approval thresholds | **CONFIG** | Profile field | Minutes |
| Timesheet link to per-diem | **CORE** *(if generic)* | Depends entirely on their process — classify after Sep 10 | TBD |

Note what happened: two of NEEM's asks became **product**. When you pitch client
three, TIN validation and reconciliation are features you already have. NEEM
paid for reputation; you got inventory.

---

## 2. The five stations

8090 runs Refinery → Foundry → Planner → Builder → Validator. Same shape here,
sized for you.

### Station 1 — REFINERY · vague intent → precise requirements

**Input:** a discovery call, a policy PDF, "we get penalised for missing receipts."
**Output:** a filled requirements sheet and a classified request list.

- Run the discovery questions (`NEEM_DISCOVERY.md`)
- Collect their **real artefacts**: policy documents, a bank statement, ten real
  receipts, their org chart, their approval matrix
- Write down, in their words, the three problems that cost them the most
- Classify every request through the triage gate

**Exit criterion:** you can state, in one sentence each, what changes for them
and what you are building. If you can't, you are still in Refinery.

*Anti-pattern:* starting to code from the demo conversation. The demo tells you
they're interested. The documents tell you what to build.

### Station 2 — FOUNDRY · requirements → blueprint

**Input:** the classified request list.
**Output:** a draft profile + an engine work list.

- Draft `profiles/<client>.json` — departments, workflow steps, thresholds,
  categories, required documents, grant codes, feature flags
- `python3 org_config.py validate profiles/<client>.json` until clean
- List the CORE features needed, each with the flag that gates it
- List the CUSTOM work, each with a price

**Exit criterion:** the profile validates, and every engine item has a flag name
and an estimate.

### Station 3 — PLANNER · blueprint → work orders

**Input:** the engine work list.
**Output:** work orders — one per feature, each with acceptance tests written
*before* the code.

A work order is:

```
WO-014 · Vendor TIN validation
Flag        tin_verification
Class       CORE
Client      NEEM (first), available to all
Behaviour   Validate TIN format on requisition create. Store on the record.
            WARN (never BLOCK) when a vendor has no TIN — finance decides.
            Report: all vendors + registration status.
Acceptance  · valid TIN accepted and stored
            · malformed TIN raises a WARNING check, not a FAIL
            · missing TIN is a WARNING, never blocks payment
            · flag off ⇒ no check appears at all
            · report lists every vendor with TIN present/absent
Estimate    2 days
```

**The acceptance list is the spec.** Write it before the code. This is how the
existing 17 suites got built and it is why refactoring the storage layer
yesterday was safe.

**Exit criterion:** every work order has acceptance criteria a test can assert.

### Station 4 — BUILDER · work orders → shipped code

- One work order at a time
- Tests first, from the acceptance list
- Feature flag from the first commit — never ship an ungated client feature
- Commit per working feature
- All suites green before moving on

**Exit criterion:** the suite count went up, everything is green, the flag
works both on and off.

### Station 5 — VALIDATOR · feedback → structured tasks

This is the loop that makes the factory improve rather than just produce. You
already designed it (`FEEDBACK_COLLECTION_SYSTEM.md`): daily async standup, a
shared issue log with severity, a Friday call, critical bugs same day.

The addition: **every issue gets triaged back through the gate.** A confusion
report might be CONFIG (their profile is wrong), CORE (the UI is unclear for
everyone), or documentation. Route it, don't just fix it.

**Exit criterion:** a written close-out report with metrics and a testimonial.
That report is the sales asset for the next client.

---

## 3. Running two clients at once

**The question: can EVA be built while NEEM deploys? Yes — and they compound.**

They are at different stations, which is exactly why it works:

```
NEEM   Refinery ✅ → Foundry ⏳(Sep 10) → Planner → Builder → Validator → LIVE
EVA    Refinery ⏳(their policy PDFs are in hand) → Foundry → Planner → Builder
```

NEEM is in **deployment and config**. EVA is in **requirements and engine
work**. Different muscles, different days.

**The compounding effect is the real argument.** EVA needs a Delegation of
Authority matrix, budget-availability checking, and banded procurement rules.
NEEM asked about procurement thresholds in the demo. Build them once as CORE:

| EVA needs | NEEM also gets | Client 3 sells with |
|---|---|---|
| DOA matrix (amount band → approver) | Better approval routing | ✅ |
| Budget availability check | Overspend prevention | ✅ |
| Banded procurement (3 quotes above X) | The thing they asked about | ✅ |
| Statutory deductions (PAYE/WHT/VAT) | Available if they need it | ✅ |
| Accounting export | QuickBooks/Excel export | ✅ |

**Building EVA makes the product you sell to everyone better.** That is only
true if you obey rule 2 of the triage gate. Fork EVA into its own codebase and
you get none of it — you get two products and half the time each.

### The one hard rule for parallel work

> **NEEM's go-live beats EVA's features. Always.**

A live client with a problem outranks a future client with a feature. If EVA
work threatens NEEM's deployment date, EVA waits. Reputation with client one is
what buys clients three through ten.

### Suggested rhythm

| | Focus |
|---|---|
| **Mon–Tue** | NEEM — deployment, config, their issues, their calls |
| **Wed–Thu** | EVA — engine work, one work order at a time |
| **Fri** | NEEM Friday call · triage the week's issues · ship fixes |
| **Weekend** | Nothing. Burnout is the actual risk to this business. |

Adjust the split as NEEM stabilises. In month one NEEM takes 80%; by month
three it should be 30% and EVA gets the rest.

---

## 4. Where the work lives — chats and context

**Use a separate chat per client workstream, and let `MASTER_CONTEXT.md` carry
the shared context between them.**

| Workstream | Chat | Reads | Writes |
|---|---|---|---|
| **NEEM delivery** | its own | `MASTER_CONTEXT` + `NEEM_FOLLOWUP_NOTES` + `profiles/neem.json` | NEEM profile, NEEM issue log |
| **EVA build** | its own | `MASTER_CONTEXT` + `EVA_BUILD_PLAN` + `EVA_BUILD_SPEC` + their PDFs | EVA profile, new engines |
| **Engine / infra** | this one | `MASTER_CONTEXT` + `CLAUDE.md` | shared core, tests, deployment |
| **Business / sales** | its own | the business docs | pricing, pipeline, proposals |

**Why separate:** a chat that carries NEEM's receipt formats *and* EVA's payroll
sign conventions *and* your AWS bill will lose the thread on all three. Each
workstream stays sharp on its own.

**Why it works now and didn't before:** `MASTER_CONTEXT.md` exists. Any chat
starts by reading it and knows the product, the architecture, the pricing, and
the decisions already made. Context lives in the repo, not in a conversation.

**The discipline that keeps it true:** when a decision is made in any chat,
**write it into `MASTER_CONTEXT.md`.** A decision that only exists in a chat is
a decision you will relitigate in six weeks.

---

## 5. What each client engagement produces

Every engagement leaves five artefacts behind. They are the factory's real
output — the client's working system is just one of them.

1. **`profiles/<client>.json`** — their configuration, in version control
2. **CORE features** — flagged, tested, available to every future client
3. **A close-out report** — issues found and fixed, metrics, testimonial
4. **A one-page Security & Compliance Summary** — answers the auditor
5. **An updated `MASTER_CONTEXT.md`** — what you learned, what you decided

After three clients you have: a validated engine, three case studies, a feature
set nobody else in this market has, and an onboarding process that takes days
instead of weeks. **That is the asset.** Not the code — the repeatability.

---

## 6. Pricing that fits the model

The triage gate maps directly onto how you charge. This is not a coincidence;
it is the point.

| Class | How it's priced |
|---|---|
| CONFIG | **Included.** It's why they pay a monthly fee. |
| CORE | **Included** for the client who triggers it — and it becomes part of what the next client buys at a higher price. |
| CUSTOM | **Quoted separately**, one-time build fee + any ongoing cost. |

This is why NEEM at ₦450k near break-even is defensible: their engagement is
paying for CORE features that you will sell at ₦600k+ to the next three
clients. You are being paid to build your own inventory.

**The escalation, restated:** NEEM ₦450k (reputation) → referrals ₦550–600k
(proven) → cold ₦600–700k (proof + sales work) → international ₦700k–1.5m
(bigger budgets, more compliance) → NEEM at renewal ₦550k (value shipped).

**On outcome-based pricing:** the market is drifting toward charging for
results rather than hours. You are already positioned for it — *"one audit
finding costs ₦500k; this prevents it"* is an outcome pitch. Don't formalise it
into a contingent fee yet; you need audit-cycle data first. Revisit after NEEM
has been through one audit with the system in place. That data is worth more
than the fee structure.

---

## 7. Anti-patterns — the ways this fails

**Forking per client.** The one thing that kills the model. If you find
yourself writing `if org == "eva"` in an engine, stop: that is a feature flag
or a profile field, not a branch.

**Building before Refinery.** Coding from the demo conversation instead of
their documents. You will build the thing they described, not the thing they do.

**Unpriced CUSTOM.** Saying yes to bespoke work inside the monthly fee. Once
you do it twice, it's the expectation.

**Ungated features.** Shipping a client-specific behaviour without a flag.
Client two sees a screen built for client one's process and loses trust.

**Skipping the Validator.** Going live and moving to the next client. The
close-out report and testimonial *are* the next sale; without them you're cold
calling forever.

**Letting EVA slip NEEM.** Covered above. It's the rule most likely to be
broken because new work is more fun than support.

**Decisions that live only in chat.** Six weeks from now you will not remember
why the override limit is ₦250k. Write it down.

---

## 8. The scale question, answered

You cap out around 3–4 clients doing everything yourself. The factory model
raises that ceiling in a specific way:

- **CONFIG work** can be done by someone else almost immediately — it's a JSON
  file with a validator that catches mistakes
- **CORE work** stays with you (it's the architecture)
- **VALIDATOR work** — triage, first-line support, the issue log — is the first
  thing to hand off

So the first hire is **support + config**, not a developer. They handle five
clients' day-to-day; you do engine work and sales. That is the ₦2m/month
unlock, and it arrives roughly at client four.

---

## Sources

- [8090 — AI-Native Software Development Platform](https://www.8090.ai/)
- [8090 Raises $135M Series A to Accelerate Their Rollout of Software Factory](https://www.businesswire.com/news/home/20260626795833/en/8090-Raises-$135M-Series-A-to-Accelerate-Their-Rollout-of-Software-Factory)
- [Time-and-materials outsourcing losing relevance: 8090 CEO Chamath](https://www.newkerala.com/news/a/time-and-materials-outsourcing-model-losing-relevance-ai-era-8090-616.htm)
- [8090's Software Factory: Why Salesforce Bet $135M on an Audit Trail](https://blog.pebblous.ai/blog/agent-built-enterprise-software-oversight/en/)
- [How to Productize a Consulting Service: A 2026 Playbook for Boutique Firms](https://practiq.dev/blog/consulting-firm-productization-playbook)
- [The Productized Service Guide: How to Build, Price, and Scale](https://www.manyrequests.com/blog/productized-service-guide)
- [What is Outcome-Based Pricing?](https://dealhub.io/glossary/outcome-based-pricing/)
