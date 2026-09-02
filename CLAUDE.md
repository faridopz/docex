# DOCex — Project Memory

> **START HERE: read `MASTER_CONTEXT.md` first.** It carries the product, the
> architecture, the business model, pricing, the NEEM engagement, and every
> decision already made. This file covers coding conventions and build history.

## The rule that shapes everything

**One engine. One config file per client. Never fork the codebase.**

A new client is `profiles/<client>.json` applied with `org_config.py` — not new
code. If a client needs behaviour the engine can't express as configuration,
that is a feature request for the *engine*: built once, available to everyone,
gated behind a feature flag if only some should see it.

```bash
python3 org_config.py validate profiles/<client>.json
DOCEX_ORG=<client> DOCEX_DB=./docex.db python3 org_config.py apply profiles/<client>.json
DOCEX_ORG=<client> DOCEX_DB=./docex.db python3 org_config.py describe
```

## What We Are Building

DOCex has grown from a document-extraction tool into an **AI-native finance &
compliance platform** for donor-funded organisations. Two layers:

1. **Document intelligence** (original): extract answers from bulk documents;
   check payments against an org's policy rulebook.
2. **Finance workflow** (ERP layer): payments move through a cross-department
   approval pipeline — each work item has a reference (C24), a status trail,
   in-app notifications to the next department, per-department dashboards, and
   in-app approvals with role enforcement.

**Founding principle — DETERMINISTIC-FIRST.** Code owns every number: amounts,
deductions, allocations, thresholds, matching, duplicates, reconciliation. The
LLM only reads messy documents and judges genuinely semantic policy questions.
A code-level BLOCK always overrides the model.

**Organisations:** TA Connect (pilot — screening + event payments) and
**EVA / Education as a Vaccine** (second org — internal finance ops, payroll,
grants; see `EVA_BUILD_PLAN.md`). Decision: **separate instances, shared engine
core** — never fork the codebase.

### Original description (still accurate for the extraction layer)
DOCex is an AI-powered document extraction tool.
A sub-award team receives hundreds of applications. Each applicant
submits multiple files — registration certificate, financials,
proposal, organisational profile, audit report. The team needs to
answer specific questions across all those documents quickly:
Is this org registered with CAC? What states do they work in?
Have they managed donor funds before? Do they have an anti-fraud policy?

Right now someone reads every document manually to find this.
DOCex extracts exactly that information automatically.

The user defines the questions. DOCex reads every document and
returns the answer, the source document, the exact quote, and a
confidence level. For batches, it produces an Excel table —
one row per applicant, one column per question.

## Target Users
- Sub-award teams at NGOs screening partner applications (first pilot)
- Grants managers at foundations
- HR teams screening CVs against a job spec
- Procurement teams reviewing supplier proposals
- Legal / compliance teams scanning contracts at scale
- Any team that receives documents in bulk and needs structured answers

## The Core Workflow
1. User defines questions in plain language
   e.g. "What states does this organisation work in?"
   e.g. "Has this org been audited in the last 2 years?"
   e.g. "Does the org mention USAID, Gates, or international donors?"

2. Single applicant mode:
   Upload multiple files for ONE applicant (all their docs together)
   Claude reads all of them and answers every question
   Results show: answer, source doc, quote, confidence

3. Batch mode:
   User adds multiple applicants, each with their own files
   Claude processes each applicant's document set
   Results: table — one row per applicant, one column per question
   Export to Excel (critical — the team lives in Excel)

## Core Data Models
Question: id, text (plain language question)
ExtractionAnswer: question_id, question_text, answer, confidence,
  source_document, quote
ApplicantExtraction: applicant_id, applicant_name, documents[],
  answers[], error?
BatchExtractionResult: total, succeeded, failed, applicants[]

## Confidence Levels
- "found" — answer is explicitly stated in a document
- "inferred" — answer can be reasonably concluded from context
- "not_found" — not mentioned in any document

## Tech Stack
- Frontend: Next.js 14, TypeScript, Tailwind CSS, shadcn/ui
- Backend: FastAPI (Python)
- Core AI engine: screener.py (being rebuilt for extraction)
- Database: Supabase (postgres + auth + file storage) — Phase 2
- AI model: claude-sonnet-4-6
- Excel export: SheetJS (xlsx) on frontend

## Infrastructure & Deployment (CURRENT — read before any deploy/infra change)

> ⚠️ **DEPLOYMENT TRUTH (confirmed by Farid, Aug 2026): the LIVE demo runs on
> RENDER (free tier) + VERCEL — NOT AWS.**
> - **API:** Render free tier — see `render.yaml` (`plan: free`, Docker, branch
>   `demo-release`, `autoDeploy: true`, health check `/health`). Sleeps after
>   ~15 min idle → **30–50s cold start** (mitigated by the keep-warm workflow).
> - **Frontend:** Vercel (`.vercel/`), talks to the API via `NEXT_PUBLIC_API_URL`
>   (baked at BUILD time).
> - **Data is EPHEMERAL:** local-disk JSON stores (`checks/`, `rulebooks/`,
>   `transactions/`, `notifications/`, `users/`, `vouchers/`, `departments.json`)
>   RESET on redeploy. Durable storage is the top infra priority.
>
> The AWS/Terraform description below is **historical/aspirational** — the
> `/terraform` and `/deploy` directories exist, but the live demo is Render.
> Verify before acting on anything in this section.

### Historical AWS description (NOT the live demo — verify first)
DOCex was described as LIVE on AWS (region eu-west-1). (A Vercel demo
still exists, but AWS was called the real deployment.)
- **Runs on:** AWS ECS Fargate — two services, `docex-web` (Next.js) and
  `docex-api` (FastAPI), each behind its own Application Load Balancer, inside
  the default VPC. Images live in ECR; logs in CloudWatch.
- **CI/CD:** GitHub Actions. A push to `demo-release` auto-builds both images,
  pushes to ECR, and rolls out a zero-downtime deploy (auth via OIDC, no stored
  keys). So: **APP changes ship by `git commit` + `git push`.** Nothing manual.
- **Infrastructure as Code:** ALL AWS infra is defined in `/terraform`. **INFRA
  changes go through Terraform** (edit `.tf` → `terraform plan` → `apply`).
  NEVER change AWS via the console — it causes drift from the code.
- **Secrets:** `ANTHROPIC_API_KEY` lives in AWS Secrets Manager and is injected
  at runtime. Never hardcode secrets. New secrets → Secrets Manager + task def
  + grant the execution role read access.
- **Frontend env gotcha:** `NEXT_PUBLIC_*` vars are baked at BUILD time. The API
  URL is passed as a Docker `--build-arg` in CI. If the API URL changes, the web
  image must be rebuilt AND the API's `ALLOWED_ORIGINS` (CORS) must include the
  web origin.
- **⚠️ DATA IS EPHEMERAL:** container local disk (`decks/`, `checks/`,
  `verifications/`, etc.) is WIPED on every redeploy. Do NOT rely on local-disk
  persistence for anything that must survive. Durable storage (S3 for files + a
  database for structured data) is the next foundational piece and is NOT built
  yet — until then, treat persistence as unavailable.
- **Key infra files:** `/terraform` (IaC), `/deploy` (task defs, IAM, scripts),
  `/.github/workflows` (ci.yml, deploy.yml). See `DEVOPS_ROADMAP.md` for the full
  infra history and the running decision log.

## Project Structure

Engines live at the repo ROOT (not in /ngo_screener — that layout was never built).

**Deterministic core (code owns numbers — never the LLM):**
  `fast_extract.py`      — parallel text extraction (PyMuPDF→pdfplumber, DOCX, XLSX)
  `fast_fields.py`       — labelled-regex field extraction (invoice/PO/GRN no., totals, TIN)
  `payment_checks.py`    — AP controls: three-way match, duplicate invoice
  `deterministic_checks.py` — form/threshold/date/reference rule engine
  `receipts.py`          — advance-retirement reconciliation
  `per_diem.py`          — per-diem entitlement + participant payable
  `doc_completeness.py`  — document classification + required-doc presence

**Workflow layer:**
  `requisitions.py`      — UNIVERSAL department→payment spine: deterministic
                           policy checks, org-configured approval chain,
                           authority-checked policy OVERRIDES (written reason
                           required), hash-chained append-only audit log,
                           immutable frozen TransactionRecord on payment
  `kobo_sync.py`         — KoboCollect offline field capture → receipt on sync
  `transactions.py`      — reference + state machine + append-only audit
  `departments.py`       — org-defined departments + stage routing
  `notification_center.py` — in-app cross-department notifications
  `auth.py`              — users, roles, sessions (PBKDF2 + HMAC)
  `vouchers.py`          — payables → voucher → routed transaction

**AI-assisted:**
  `compliance.py`        — rulebook-driven semantic checks (lean output schema)
  `screener.py`          — extraction engine
  `knowledge.py`, `assistant.py`, `policy_rules.py`

`/api`   — FastAPI routers (one per feature; all registered in api/main.py)
`/web`   — Next.js frontend
`/bench` — benchmark harness
`test_*.py` (repo root) — 9 test suites, all green; run with `python test_x.py`

**Key docs:** `CLAUDE.md` (this) · `SOUL.md` · `PERFORMANCE_AUDIT.md` ·
`BATCH_PERFORMANCE_AUDIT.md` · `ERP_ARCHITECTURE.md` · `EVA_BUILD_SPEC.md` ·
`EVA_BUILD_PLAN.md`

## Design System
- Font: Geist (Next.js default)
- Accent: #2563eb (blue-600)
- Background: white / gray-50
- Cards: white with subtle border and shadow
- Confidence colors: emerald = found, amber = inferred, gray = not_found
- Style: Clean, minimal, professional — Notion meets Linear

## Key Conventions
- TypeScript strict mode throughout frontend
- All API calls from frontend go through web/lib/api.ts
- Python files follow existing patterns in ngo_screener/
- Never rewrite existing working code unless told to
- One feature at a time — no unrequested additions
- Always add error handling and loading states
- Comments on non-obvious logic

## Build Phases

### Phase 1 — Core extraction ✅ SHIPPED
Extraction engine, rulebooks, compliance checking, Bank Verify, Attendance
Payment Agent, Knowledge Hub, rate cards, self-check diagnostics — all live.

### Phase 2 — ERP workflow layer ✅ SHIPPED
DOCex is no longer only a document checker; it runs cross-department finance
workflow. All tested (9 suites green, `test_*.py` in repo root):
- [x] `per_diem.py` — per-diem entitlement (coverage-weighted: org covers food →
      pay 75%); combined with reimbursable receipts into one payable.
      Policy is data on the **rate card**, not code.
- [x] `transactions.py` — human reference (C24 / V7), workflow state machine
      (`submitted → intake → compliance_review → finance_review → approval →
      paid`, plus `returned`), append-only audit history, locked monotonic
      counter.
- [x] `departments.py` — **org-defined departments** + which department owns
      each workflow stage. NOT hard-coded: EVA runs Program/Compliance/Finance/
      TLFA/ED. Defaults reproduce the original four.
- [x] `notification_center.py` — in-app cross-department feed; every state
      change notifies the department that must act next.
- [x] `auth.py` — users, departments, roles (viewer/reviewer/approver/admin),
      PBKDF2 password hashing + HMAC session tokens, first-user bootstrap.
- [x] `vouchers.py` — consolidate participant payables → voucher → submit,
      which opens a routed transaction.
- [x] **In-app approvals** — transitions are authenticated + role-gated;
      actor/department come from the signed-in user (not the request body).
      Reviewers can progress work but cannot self-authorise payment.
- [x] Frontend: real auth (`lib/auth.tsx` → `/auth/login`), per-department
      dashboard (`/dashboard`), transaction detail + status timeline,
      notification bell, voucher builder, admin screen
      (`/settings/departments`).

### Phase 3 — Compliance performance ✅ SHIPPED
See `PERFORMANCE_AUDIT.md` + `BATCH_PERFORMANCE_AUDIT.md` for the evidence.
- [x] **Lean LLM output schema** — the model returns decisions + compact evidence
      refs; the server rehydrates `rule_description`/`policy_citation` from the
      rulebook by `rule_id`. Public `RuleResult` API is unchanged.
- [x] **Collapsed receipt fan-out** — one model object per receipt-rule with a
      `receipts[]` array instead of one per (rule × receipt). A 50-receipt bundle
      went from ~321 objects (~64k tokens — exceeded the ceiling and FAILED) to
      ~7. `max_tokens` 16384 → 8192 (`_CHECK_MAX_TOKENS`).
- [x] **Batch fixed** — batch now runs the same deterministic AP controls as
      single (three-way match + duplicate detection were previously SKIPPED in
      batch), detects duplicate invoices *within* a batch, extracts in parallel,
      and isolates a failed payment instead of 422-ing the whole run.
- [x] `bench/bench_check.py` — stage-timing benchmark harness (runs non-LLM
      stages without an API key; never invents numbers).
- [x] Keep-warm workflow (`.github/workflows/keep-warm.yml`) pings `/health`
      every 10 min so the free instance stops sleeping. **Needs repo variable
      `DOCEX_API_URL` set, or it no-ops.**

### Phase 4 — Universal org flow ✅ BACKEND SHIPPED
One flow every org runs, adapted by CONFIG not code. `requisitions.py` +
`api/requisition_routes.py` + `test_requisitions.py` (48 checks green).
- [x] **Payment requisitions** — any department raises a request; policy checks
      run instantly so the submitter sees problems before an approver does.
- [x] **Deterministic policy engine** — amount ceiling, vendor allow/block,
      category, required documents, duplicate window, project code. Code owns
      every number. A FAIL blocks; a WARNING informs.
- [x] **Org-configured approval chain** — `default_workflow(size=small|medium|
      large)` gives a working chain on day one; steps carry `min_amount`,
      `can_override`, `override_limit`.
- [x] **Policy override with accountability** — releasing a FAIL requires a
      written reason AND a step that holds the authority AND an amount within
      that step's override limit. All three are enforced, not advisory.
- [x] **Hash-chained audit log** — append-only, HMAC-chained; `verify_audit_chain()`
      detects tampering. Nothing is ever mutated.
- [x] **Immutable TransactionRecord** — frozen copies of every check, approval
      and audit line at time of payment. `locked=True`.
- [x] **Auditor summary** — `audit_summary()` reports every exception with its
      reason + named authority; `audit_ready` is False if any lacks a reason.
- [x] `api/context.py` — single place resolving (user, org_id). Replaces the
      non-existent `get_current_session()` that was breaking `api.main` import.
- [x] **Idempotency keys** (`idempotency.py` + `test_idempotency.py`, 21 checks
      green). `POST /requisitions` and `POST /requisitions/{id}/pay` accept an
      `Idempotency-Key` header: a retry after a dropped connection replays the
      original record instead of raising a duplicate requisition or freezing a
      second transaction against one debit. Org-scoped, operation-namespaced,
      409 on a concurrent retry, key released if the wrapped write raises.
      Verified end-to-end through the real API (same key → REQ-0001 twice;
      different key → REQ-0002; two records stored, not three).

### Phase 4b — Requisition frontend ✅ SHIPPED
The screens for the Phase 4 backend. `npx tsc --noEmit` clean.
- [x] `web/types/requisition.ts` — types mirroring the route serialisers, with
      unions (not `string`) for status/result/decision so a bad comparison on a
      payments screen is a build error.
- [x] `web/lib/requisitionApi.ts` — typed client for all 12 endpoints, plus
      `newIdempotencyKey()`. Writes are multipart, matching the Form routes.
- [x] `web/lib/session.ts` — `apiFetch` no longer forces a JSON Content-Type on
      FormData bodies (it was overriding the multipart boundary).
- [x] `web/lib/requisitionFormat.ts` + `components/erp/PolicyChecks.tsx` —
      shared money/date/aging helpers and the check list. An **overridden FAIL
      gets its own colour**: it is neither clean nor still blocking, and an
      auditor must spot it at a glance.
- [x] `/requisitions/new` — policy checks shown the instant it's submitted, so
      the submitter fixes problems while the invoice is still open. The org's
      real ceiling/categories/required documents are read from the workflow and
      shown as guidance. Idempotency key held in a ref across retries.
- [x] `/requisitions` — "Waiting on me" is the default tab; dense scannable
      rows with amount, aging, and blocking/warning counts.
- [x] `/requisitions/[id]` — checks, approval trail, hash-chained audit log
      with a loud banner if the chain fails to verify. **Approve stays disabled
      until every blocking check is ticked AND a written reason AND an
      authority are supplied** — the server enforces the same rules, the UI
      just refuses to send a request it knows is incomplete.
- [x] `/payments` + `/payments/[id]` — the locked record: checks *as applied*,
      not recomputed against today's policy.
- [x] `/audit` — the verdict first (audit-ready or N unexplained), then
      unexplained exceptions before explained ones.
- [x] AppShell nav: Requisitions · Payments · Audit.

### Phase 5 — Multi-tenancy foundation ✅ SHIPPED (Sep 2026)
The change that turns DOCex from one deployment into a repeatable product.
`org_config.py` + `profiles/` + `test_org_config.py` (44 checks green).
- [x] **`auth.py` on the store layer** — users were JSON files at the repo root:
      wiped on every redeploy and not org-scoped. Now org-scoped records with
      SQLite durability. `issue_token()` stamps the org into the session token,
      so multi-org needs no token format change later. `migrate_legacy_users()`
      imports the old `users/` directory once, on real server boot only.
- [x] **`departments.py` on the store layer** — same fix for
      `departments.json`. Every function takes an optional `org_id` defaulting
      to `DOCEX_ORG`, so single-org callers were untouched. Added
      `replace_all()`, which validates that every state owner names a
      department that exists.
- [x] **`org_config.py`** — validate → apply → describe for client profiles.
      Validation runs BEFORE any write, so an invalid profile can never leave
      an org half-configured. Catches the mistakes that strand payments: a step
      routed to a missing department, a state owner naming one, an
      `override_limit` below the `min_amount` where the step engages. Applying
      is idempotent. Admin passwords are never persisted.
- [x] **`store.is_configured()`** — lets a test install its own backend before
      importing the app; `api/main.py` now respects it instead of silently
      redirecting test writes into the developer's real `data/` directory.
      The legacy import is likewise gated to real server boot only.
- [x] **`profiles/_template.json`** (commented reference) + `profiles/neem.json`
      (awaiting NEEM's real thresholds and grant codes).
- [x] Verified end-to-end: profile → SQLite → API login → org-scoped data.

### Phase 6 — Next (not started)
- [ ] Onboarding wizard (5 questions → generated workflow + policy)
- [ ] Auditor export (Excel + PDF) from `audit_summary()`
- [ ] Fund/budget balance checks wired to `grants.py` (engine ready, not linked)
- [ ] Measure the LLM leg with a real key (`bench/bench_check.py --llm`) to get
      true before/after numbers — currently unmeasured, do NOT quote figures.
- [ ] Haiku-first + conservative Sonnet escalation (benchmark against
      Sonnet-only before trusting it).
- [ ] **Remaining engines still writing raw files** — `notification_center.py`,
      `transactions.py`, `vouchers.py`, and the directory-based storage in
      several `api/*_routes.py` (rulebooks, checks, verifications, rate cards,
      decks). Same durability + tenancy gap `auth`/`departments` just had. Move
      them onto `store.get_store()`.
- [ ] **Verify `PostgresStore` against a live database** — written but untested.
      Run `test_store_sql.py` with `DOCEX_DATABASE_URL` set before trusting it.
- [ ] Async batch (`batch_id`, progressive results), retries.
- [ ] Fix `demo_seed.py` — hangs during data generation (not engine logic).

## Business Model
Pricing happens per-pilot in conversation — NOT on the landing, NOT
in the PDF, NOT in the product UI. Internal quota tiers exist in
code (free / pilot / scale) for rate-limiting but their dollar
amounts and tier names are never surfaced publicly. When a free
user hits cap, the message is "contact founder@docex.app to scale"
— never an upgrade-with-price prompt.

## Primary Pilot Client
TA Connect — public health NGO, Abuja Nigeria
Sub-award team screens 200+ partner applications per cycle
Each applicant submits 5–8 documents
Team needs answers to ~15 standard questions per applicant

## Agent Rules
- Always read CLAUDE.md and SOUL.md at the start of every session
- Never rewrite working code to fix one small thing
- One file at a time, show me before moving on
- After each step tell me exactly what to run to test it
- When in doubt do less better
- Commit after every working feature
