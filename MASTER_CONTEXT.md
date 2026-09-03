# DOCex — Master Context

**Owner:** Farid Abdurrahman · faridmichika@gmail.com
**Last substantive update:** 2 September 2026
**Purpose:** the single file to read before any DOCex work. It carries the
product, the architecture, the business, and the decisions already made — so a
new session (mine or anyone's) starts informed instead of asking again.

> Read this, then `CLAUDE.md` for coding conventions. Everything else in the
> repo is detail hanging off one of these two.

---

## 0. THE MODEL — settle this before anything else

Four questions get confused with each other constantly. Here are the answers,
and they are not negotiable without a deliberate decision recorded in §10.

| Question | Answer |
|---|---|
| How many **codebases**? | **ONE.** Never forked, never copied. |
| How many **versions of the software**? | **ONE.** Every client runs the same release. |
| How many **running instances**? | **ONE PER CLIENT.** Own server, own database. |
| Do clients see the **same thing**? | **NO.** Config + feature flags make each one theirs. |

### Said plainly

**You are not building a new version per client. You are running the same
version for every client, configured differently.**

The analogy that holds: you are a **house builder with one design system**. Same
blueprint, same construction method, same suppliers. Each house is built on its
own plot with its own utilities and its own front-door key. The owner picks the
layout and the finishes. When you learn a better way to build a roof, every
future house gets it — and you can retrofit the existing ones.

You do not design a new house from scratch for each buyer. That is what forking
the codebase would be, and it is the one thing that kills this business.

### The picture

```
                    ONE CODEBASE  ·  ONE VERSION
                  (github.com/faridopz/docex)
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   NEEM instance         EVA instance        Client 3 instance
   own server            own server          own server
   own database          own database        own database
        │                     │                     │
   neem.json             eva.json            client3.json
   4 departments         5 departments       their departments
   ₦250k ceiling         ₦20m ceiling        their ceiling
   TIN flag ON           payroll flag ON     both ON
   payroll flag OFF      TIN flag OFF        + procurement
```

Same code in all three boxes. Different config, different data, different
experience.

### Why separate instances rather than one shared platform

The code supports both — `org_id` is part of every storage key and
`test_org_config.py` proves two organisations on one instance cannot see each
other. Separate instances is a **deployment choice**, not an architectural one,
and it is reversible.

Three reasons it is the right default now:

1. **Blast radius.** A bad deploy takes down one client, not all of them.
2. **The compliance story.** *"Your data is on your own instance, your own
   database"* ends a conversation that *"we isolate by tenant key"* starts.
   For donor-funded finance data this matters more than the hosting cost.
3. **Data residency.** Some donors require data in-country. Per-client instances
   let NEEM sit in one region and a UK charity in another.

The shared-instance option stays open for a future low-cost tier — small NGOs at
₦150k/month where per-client infrastructure wouldn't pay for itself. **That is
why the multi-tenancy work was worth doing before there was a second client.**

### What differs between clients, and how

| Layer | Shared or per-client? | Where it lives |
|---|---|---|
| Engine code | **Shared** | the repo |
| Features | **Shared**, switched per client | feature flags |
| Departments, approval chain, thresholds, categories, grant codes | Per client | `profiles/<client>.json` |
| Data (payments, receipts, audit trail) | Per client | their own database |
| Branding / URL | Per client | their instance |

### The three buckets every client request falls into

| | What | Time | Who gets it |
|---|---|---|---|
| **CONFIG** | A value in their JSON | Minutes | Just them |
| **CORE** | A capability the engine lacks | Days | **Everyone, forever** |
| **CUSTOM** | Only they will ever want it | Weeks | Just them — **priced separately** |

Default to CONFIG. Prefer CORE over CUSTOM — that is what turns one client's
requirement into the next client's selling point. CUSTOM is rare and always
quoted.

### The one rule that protects all of it

> **Never write a client's name into engine code.**
> If you catch yourself typing `if org == "eva"`, stop. That is a config field
> or a feature flag. Three of those and you have forked the codebase without
> having decided to.

---

## 1. What DOCex is

An **AI-native finance and compliance platform for donor-funded organisations.**

Two layers:

1. **Document intelligence** — extract structured answers from bulk documents;
   read receipts and invoices (including photographs, via OCR).
2. **Finance workflow (ERP)** — payments move through a cross-department
   approval pipeline with references, status trails, in-app notifications,
   role-enforced approvals, and an immutable audit trail.

**Founding principle — DETERMINISTIC-FIRST.** Code owns every number: amounts,
deductions, allocations, thresholds, matching, duplicates, reconciliation. The
LLM only reads messy documents and judges genuinely semantic policy questions.
**A code-level BLOCK always overrides the model.**

### The problem, in a customer's words

Fieldworkers pay for things in the field and come back with receipts that are
incomplete — no vendor name, smudged date, unclear amount. Finance logs them by
hand. Approvals happen in email. When the auditor arrives, nobody can prove why
an exception was released. **Organisations get penalised for missing
documentation.** DOCex reads the receipt, flags what's missing rather than
inventing it, forces a written reason and a named authority on every override,
and hands the auditor a complete trail.

### The one-line pitch

> Most systems record an override. This one refuses an unexplained one.

---

## 2. Current state (as of 2 Sep 2026)

**Working and tested — 17 suites, all green.**

| Capability | Status |
|---|---|
| Receipt capture — photo, PDF, Excel, CSV, scan | ✅ |
| OCR on photographs and scanned PDFs (tesseract) | ✅ |
| Vendor/amount extraction that never invents data | ✅ |
| Requisitions + deterministic policy checks | ✅ |
| Org-configured approval chain, role-enforced | ✅ |
| Overrides requiring reason + authority + limit | ✅ |
| Hash-chained, append-only audit log | ✅ |
| Immutable frozen TransactionRecord on payment | ✅ |
| Auditor view (verdict first, exceptions first) | ✅ |
| Duplicate invoice + receipt double-claim blocking | ✅ |
| Grant-period enforcement (donor compliance) | ✅ |
| Idempotency keys on create + pay | ✅ |
| Durable SQLite storage (`DOCEX_DB`) | ✅ |
| **Per-client config profiles (`org_config.py`)** | ✅ **new** |
| **Org-scoped, durable users + departments** | ✅ **new** |

**Not built — say so plainly, never imply otherwise:**

- KoboCollect offline sync (backend written + tested; field app connection unfinished)
- Onboarding wizard (configuration is hands-on, via profiles)
- Auditor export to Excel/PDF (on-screen only)
- Bank reconciliation / month-end matching
- Banded procurement rules (three-quote thresholds by amount)
- Vendor TIN verification against FIRS (flag exists; logic not built)
- Timesheet integration
- Postgres adapter is written but **unverified against a live database**

---

## 3. Architecture

### The rule that makes this a business

**One engine. One config file per client. Never fork the codebase.**

Adding a client must not mean adding code. If a client needs behaviour the
engine can't express as configuration, that's a feature request for the
*engine* — built once, available to all, gated behind a feature flag if only
some should see it.

```
profiles/<client>.json   →  org_config.apply_profile()  →  org-scoped store
   (data: departments,        (validates BEFORE writing)      (SQLite/Postgres)
    workflow, policy,
    grants, admin, flags)
```

### Layers

```
web/            Next.js 14 · TypeScript · Tailwind · shadcn/ui
api/            FastAPI routers, one per feature, all registered in api/main.py
                api/context.py resolves (user, org_id) for every request
engines/        (repo root) deterministic core + AI-assisted modules
store.py        Store protocol — org-scoped persistence contract
store_sql.py    SqliteStore (durable, WAL, crash-safe) · PostgresStore (untested)
org_config.py   client profiles: validate → apply → describe
```

### Deterministic core (code owns numbers — never the LLM)

`fast_extract.py` (parallel text extraction + OCR + magic-byte sniffing) ·
`fast_fields.py` (labelled-regex fields) · `payment_checks.py` (three-way match,
duplicates) · `deterministic_checks.py` · `receipts.py` (advance retirement) ·
`per_diem.py` · `doc_completeness.py`

### Workflow layer

`requisitions.py` — the universal department→payment spine. Policy checks,
approval chain, authority-checked overrides, hash-chained audit, immutable
TransactionRecord.
`field_receipts.py` · `kobo_sync.py` · `transactions.py` · `departments.py` ·
`notification_center.py` · `auth.py` · `vouchers.py` · `grants.py` ·
`idempotency.py`

### AI-assisted (the only places the model runs)

`compliance.py` (rulebook-driven semantic checks) · `screener.py` (extraction) ·
`knowledge.py` · `assistant.py` · `policy_rules.py`

### Storage — how it actually works

Everything goes through `store.get_store()`, keyed by
`(org_id, collection, record_id)`. `org_id` is **part of the key, not a
filter** — Org A structurally cannot read Org B's data.

- `DOCEX_DB` set → SQLite (WAL, `synchronous=FULL`), durable across redeploys
- unset → JSON files under `data/` (development only)
- `store.is_configured()` lets a test install its own backend before importing
  the app, and `api/main.py` respects it

**Never write files directly from an engine.** Four modules still do
(`notification_center`, `transactions`, `vouchers`, and some `api/*_routes.py`
directories) — see Open Work.

---

## 4. Per-client configuration — the mechanism

A profile is a plain JSON (or YAML) file. `profiles/_template.json` is the
commented reference; `profiles/neem.json` is NEEM's, awaiting their real data.

```bash
python3 org_config.py validate profiles/neem.json          # no writes
DOCEX_DB=./docex.db DOCEX_ORG=neem \
  python3 org_config.py apply profiles/neem.json           # write it
DOCEX_DB=./docex.db DOCEX_ORG=neem \
  python3 org_config.py describe                           # live config as JSON
```

**Sections** (all optional except `org_id`): `departments`, `state_owners`,
`workflow` (steps + spend policy), `grants`, `admin`, `features`.

**Guarantees, each covered by a test:**

- Invalid profile → `ProfileError` **before any write**. Never a half-configured org.
- Validation catches the failures that strand a payment: a step routed to a
  department that doesn't exist, a state owner naming a missing department, an
  `override_limit` below the `min_amount` at which the step engages.
- Applying twice is a no-op — grants are add-only by `project_code`, the admin
  is create-only, and a re-apply produces a byte-identical live config.
- A partial profile touches only the sections it names.
- Two orgs on one engine are fully isolated: departments, workflow, users,
  tokens (the org rides in the session token).
- The admin password is **never** persisted into the stored profile.

**Feature flags:** `org_config.feature_enabled(org_id, "kobo_sync")`. Unknown
flags default to `False`, so new capabilities are opt-in per client.

### Onboarding a new client

1. `cp profiles/_template.json profiles/<client>.json`
2. Fill in from the discovery call (departments, thresholds, categories,
   required documents, grant codes, first admin)
3. `python3 org_config.py validate profiles/<client>.json`
4. `DOCEX_ORG=<client> DOCEX_DB=... python3 org_config.py apply ...`
5. Client signs in, changes the password, uploads a real receipt

No code is written. That is the whole point.

---

## 5. Business model

### What it is

**Consulting-first, productise later.** Not SaaS yet. Each client gets a system
fitted to how they work, plus ongoing support and strategy. Farid is the
architect and the relationship.

### Pricing

| Tier | Users / volume | Price/month | Notes |
|---|---|---|---|
| Starter | <20 users, ~30 reqs | ₦250k | Light-touch, mostly self-serve |
| Growth | 20–50 users, ~100 reqs | ₦450–600k | **NEEM sits here** |
| Scale | 50+ users, 250+ reqs | ₦800k–1m | Real margin |
| International | UK / multi-country | ₦700k–1.5m+ | Larger budgets, more compliance |

**Pricing strategy — deliberate, not accidental:**

- **NEEM at ₦450k is a reputation trade, near break-even.** It buys the case
  study, the testimonial, and the referrals.
- **Referrals from NEEM: ₦550–600k** — warm intro, proven value.
- **Cold prospects: ₦600–700k** — you're doing the sales work and have proof.
- **NEEM at renewal (month 12): raise to ₦550k**, justified by features shipped
  and value demonstrated.
- Never lead with price. Lead with: *one audit finding costs ₦500k to fix.*

### True cost per client (Growth tier, ~100 requisitions/month)

| Item | Monthly |
|---|---|
| AWS hosting (shared; marginal cost per extra client is ~₦40k) | ₦128k |
| **Claude API** (~₦1 per requisition — the real variable cost) | ₦100k |
| Sentry + CloudWatch + uptime monitoring | ₦18k |
| Farid's consulting time (~20 h at ₦11k/h) | ₦200k |
| Business admin, licences, contingency | ₦20k |
| **Total** | **≈₦466k** |

At ₦450k that is roughly break-even — **intentional for client one.**

**Hosting scales sub-linearly.** Five clients cost ~₦200k total, not ₦640k.
Support time is what actually caps growth, which is why hiring is the unlock.

**Claude cost is the variable to watch.** Optimisations available: batch
processing, caching repeated policy checks, Haiku-first with Sonnet escalation.
Realistic saving: 30–50%.

### Path to ₦2m/month profit

| When | Clients | Revenue | Profit |
|---|---|---|---|
| Dec 2026 | 1 (NEEM) | ₦450k | ≈break-even |
| Jun 2027 | 3 | ₦1.8m | ₦435k |
| Dec 2027 | 5 | ₦2.6m | ₦1.4m |
| **Hire support person (₦300k/mo) — the unlock** | | | |
| Dec 2028 | 8–10 | ₦3.5m | **₦2.0–2.5m** ✅ |

Hiring is what breaks the ceiling: Farid stops doing support and does sales and
architecture. One support person covers five or six clients.

### Markets, in priority order

1. **Nigerian NGOs** — ~500 large enough to afford this. Warm, known, proven.
2. **UK charities** — ~5,000 major; a friend in England is the entry point.
   Budgets are 2–3× Nigerian. Targets: Oxfam, Save the Children UK, British Red
   Cross, Christian Aid, Tearfund.
3. **International NGOs** — Mercy Corps, IRC, CARE, World Vision. USAID
   grantees live under 2 CFR 200 and feel this pain acutely.
4. **Adjacent verticals (2027+)** — private healthcare, microfinance
   institutions, universities, cooperatives. Same workflow, ~70%+ code reuse.
   Attack only after 2–3 NGO case studies exist.

---

## 6. NEEM — the first client

**Status:** demo done and successful (2 Sep 2026). Warming up. Follow-up
booked **10 September 2026**.

**Agreed:** DOCex is the base; Farid builds them a custom version.
**Price:** ₦450k/month · **Users:** 20 · **Positioning:** consultant, not vendor.

### What they asked for

1. **Vendor tax ID (TIN) verification** — audit requirement. Start with manual
   format validation + reporting; FIRS API integration is a paid add-on
   (~₦50k/month).
2. **End-of-month payment reconciliation** — match requisitions against the
   bank statement; flag unmatched both ways. Needs their statement format.
   ~₦150k to build.
3. **Timesheet integration** — link staff hours to per-diem and advances.
   Understand their current process first; likely phase 3.

They also flagged **significant legal/compliance requirements** — this is why
Section 7 exists.

### Sep 10 agenda

30 min reviewing their real documents and flows · 30 min running their data
through the system · 30 min designing the three features together · 15 min
confirming the build plan · 5 min next steps.

**Then:** fill `profiles/neem.json` with their real departments, thresholds,
categories, required documents and grant codes. Apply. That is the build.

### Test-run discipline (Sep 10 – Oct 1)

Daily async standup from their team · a shared issue log (bug / lag / confusion
/ request, with severity) · a weekly Friday call · critical bugs fixed same day.
At the end: a written report with metrics and testimonials. **That report is
the sales asset for client two.**

---

## 7. Legal, data and security

Non-negotiable for finance data. Most of this is contract and documentation
work, not code.

**Must be settled with every client, in writing:**

- **Data residency** — AWS has no Nigeria region; nearest are Cape Town and
  London. *Ask each client whether their donors require data to stay in-country.*
  Rack Centre (Nigeria) is the fallback if so.
- **Data ownership** — the client owns everything. Full export on request. On
  termination: export provided, data deleted after a 90-day audit window.
- **Encryption** — TLS in transit, AES-256 at rest, encrypted backups.
- **Backups** — daily, stored separately, **restore tested quarterly.** RTO 4h,
  RPO 24h.
- **Access control** — role-based; login and action audit trails; Farid cannot
  read client data without a request.

**Compliance frameworks to be able to answer on:** 2 CFR 200 (USAID grantees) ·
UK Charity Commission · GDPR (only if UK/EU clients — needs a DPA, ~₦100k) ·
donor-specific rules.

**Certification roadmap:** nothing required for NEEM. Penetration test and
security audit around client two (~₦150k). Start SOC 2 Type II before
approaching international NGOs (~₦300k, six-month process).

**Deliverable for every client:** a one-page *Security & Compliance Summary*
covering data location, encryption, access control, backups, ownership and
incident response. It answers the auditor's questions before they're asked.

---

## 8. Infrastructure

**Today:** Render free tier (API, Docker, branch `demo-release`, autodeploy,
health check `/health`) + Vercel (frontend, `NEXT_PUBLIC_API_URL` baked at
**build** time). Render sleeps after ~15 min idle → 30–50s cold start,
mitigated by `.github/workflows/keep-warm.yml` (**needs repo variable
`DOCEX_API_URL` or it silently no-ops**).

**The `/terraform` and `/deploy` AWS directories are historical/aspirational.**
The live demo is Render. Verify before acting on anything in them.

**Hosting decision:**

- **Now → client 2:** Digital Ocean or Render (₦43k/mo). Cheap while proving
  the model.
- **From client 3 (~mid-2027):** AWS (₦128k/mo). Justified because compliance
  work costs ₦300–500k regardless, larger clients expect enterprise hosting,
  and one platform then scales to 10+ clients.

**Durability:** set `DOCEX_DB` to a path on a mounted volume. Without it,
storage is ephemeral JSON and resets on every redeploy.

**Demo discipline:** demo from the laptop, not the live URL. Cold starts and
venue wifi are unnecessary risks. *"It runs in the cloud; I'm showing you
locally so we're not at the mercy of the wifi"* is a completely normal thing to
say.

---

## 9. Open work, in priority order

**Before NEEM go-live**

1. Fill `profiles/neem.json` from their real documents and apply it.
2. Vendor TIN validation — manual format check, storage, reporting.
3. Set `DOCEX_DB` in the deployed environment and confirm data survives a redeploy.
4. Set up Sentry; set the `DOCEX_API_URL` repo variable for keep-warm.
5. Produce the Security & Compliance Summary and the one-page SOW.
6. Fix `demo_seed.py` — it hangs (data generation, not engine logic).

**Soon after**

7. Move `notification_center`, `transactions` and `vouchers` onto the store
   layer (they still write raw files — same durability and tenancy gap that
   `auth` and `departments` just had).
8. Move `api/*_routes.py` directory-based storage (rulebooks, checks,
   verifications, rate cards, decks) onto the store.
9. Month-end bank reconciliation.
10. Auditor export (Excel + PDF) from `audit_summary()`.
11. Advance aging report.
12. Banded procurement rules (three quotes above a threshold).
13. Verify `PostgresStore` against a live database, then migrate.
14. Measure the LLM leg properly (`bench/bench_check.py --llm`). **Do not quote
    performance figures until measured.**

---

## 10. Decisions already made — do not relitigate without new information

- **Deterministic-first.** Code owns numbers. A code BLOCK beats the model.
- **One engine, config per client.** Never fork the codebase per customer.
- **Separate instances, shared engine core** for TA Connect / EVA / NEEM.
- **`org_id` is part of the storage key**, not a filter.
- **Consulting first, productise later.** Depth and case studies before scale.
- **NEEM at ₦450k is deliberately near break-even.** Reputation buy.
- **Raise prices for referrals and cold prospects**; raise NEEM at renewal.
- **Hiring a support person is the unlock** for ₦2m/month, not more clients alone.
- **AWS from client three**, not before.
- **Honesty about what isn't built** beats a vague yes. Every time.
- **Never invent data.** A blank vendor field is the correct answer; a guessed
  one is a bug. This is the product's whole credibility.

---

## 11. Working agreements

- Read `MASTER_CONTEXT.md` and `CLAUDE.md` at the start of every session.
- Never rewrite working code to fix one small thing.
- One file at a time; show the change before moving on.
- After each step, say exactly what to run to test it.
- Commit after every working feature.
- When in doubt, do less, better.
- Tests are the specification. All suites must stay green.
- No unrequested additions.

---

## 11b. EVA — the second client

**Status:** 18 signed policy PDFs and a process map are in `uploads/`.
`EVA_BUILD_SPEC.md` and `EVA_BUILD_PLAN.md` already analyse them.
`profiles/eva.json` is scaffolded and validates.

**EVA is engine work, not a config file.** They need a Delegation of Authority
matrix, statutory deductions, budget-availability checking, banded procurement,
and an accounting export. Roughly 70% of what they need already exists;
`payroll.py` and `grants.py` are built and tested. Missing: `doa.py`,
`deductions.py`, `coding.py`, `procurement.py`, `cash_receipts.py`,
`accounting_export.py`, `subrecipient.py`.

**Their flow** (from their own process map, written for external audit review):
Program initiates → Compliance review (independent, reports to ED/Board) →
Finance review (budget availability by project) → voucher raised → approval per
DOA → **TLFA processes payment on the bank platform** → **ED final
authorisation** → recorded under project + expense codes → filed for audit.

Five departments: `program`, `compliance`, `finance`, `tlfa`, `ed`.

**Blocking open question — the "refinancing" sign convention.** Working
interpretation: cost recovery / recharge, salary charged back to a donor grant,
shown negative because it offsets the expense line. **Confirm with EVA before
writing any payroll code.** A wrong sign convention in a finance system is a
serious defect, and this one is not guessable.

**Why building EVA helps NEEM:** every EVA engine is CORE, behind a feature
flag, so NEEM (and client three) inherit DOA routing, budget checks and
procurement bands for free. See `DELIVERY_PLAYBOOK.md` §3.

---


## 11c. Where each client stands (Sept 2026)

| | NEEM | EVA |
|---|---|---|
| Stage | **Deploying for real** — no longer a demo | Engine build, Phase 1 done |
| Price | ₦450k/mo (reputation trade) | ₦600k/mo + phased build fees |
| Blocker | Production config — 2–3 days | 5 more engines |
| Config | `profiles/neem.json`, needs their Sep 10 numbers | `profiles/eva.json`, needs their policy numbers |

**NEEM is live-bound.** Everything in `PRODUCTION_READINESS.md` must be green
before their real payment data goes in. Auth is now closed (default-deny);
durable storage and tested backups are the remaining blockers.

**EVA Phase 1 is built:** `doa.py` — the Delegation of Authority matrix, 60
checks green. That is the piece that lets EVA go live and start paying. Phases
2–5 (deductions, coding/budget, payroll, procurement, accounting export) follow
while they pay. Payroll stays blocked on the refinancing sign convention.

---

## 12. Repo map

**Read first:** `MASTER_CONTEXT.md` (this) · `CLAUDE.md` (conventions) · `SOUL.md`

**Plan + skills:** `business/SCALE_PLAN.md` · `SKILLS.md` (seven installed skills covering prospect → configure → build → deploy → run → price → incident)

**Deployment shape:** `DEPLOYMENT_TOPOLOGY.md` (separate URL, server and database per client; one codebase)

**How work gets done:** `DELIVERY_PLAYBOOK.md` (the factory model + the
Config/Core/Custom triage gate) · `PRODUCTION_READINESS.md` (the go-live gap list)

**Client onboarding:** `org_config.py` · `profiles/_template.json` ·
`profiles/neem.json` · `profiles/eva.json`

**Business:** `NEEM_FOLLOWUP_NOTES.md` · `CONSULTING_MODEL_TRUE_COSTS.md` ·
`NEEM_PAYMENT_PLANS_PROFIT.md` · `ONE_CLIENT_COSTS_AND_HOSTING.md` ·
`BUSINESS_MODEL_SCALING.md` · `REFERRALS_AND_MARKET.md` ·
`INTERNATIONAL_NGO_TARGETS.md` · `VERTICAL_EXPANSION.md` · `PRICING_STRATEGY.md`

**Sales motion:** `DEMO_PACK.md` · `DEMO_COLLABORATIVE.md` · `DEMO_CHECKLIST.md` ·
`NEEM_DISCOVERY.md` · `FEEDBACK_COLLECTION_SYSTEM.md`

**Engineering:** `ERP_ARCHITECTURE.md` · `PERFORMANCE_AUDIT.md` ·
`BATCH_PERFORMANCE_AUDIT.md` · `DEVOPS_ROADMAP.md` · `EVA_BUILD_PLAN.md`

**Tests (17 suites, all green):** `test_org_config.py` · `test_requisitions.py` ·
`test_engine_integration.py` · `test_extraction.py` · `test_auth.py` ·
`test_departments.py` · `test_integration_erp.py` · `test_field_receipts.py` ·
`test_transactions.py` · `test_vouchers.py` · `test_store_sql.py` ·
`test_idempotency.py` · `test_per_diem.py` · `test_payroll.py` ·
`test_kobo_sync.py` · `test_compliance_perf.py` · `test_batch_perf.py`

---

*Keep this file current. When a decision changes, change it here — not in a
chat that will be gone next month.*
