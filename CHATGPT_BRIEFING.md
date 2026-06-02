# DOCex — Honest Briefing for ChatGPT

Paste this entire document as your first message to ChatGPT. It's deliberately blunt about what works, what's brittle, and what's not yet built. The point is for ChatGPT to help me without making assumptions I'd have to correct later. After the briefing, ask whatever specific question you have.

---

## 1. Who I am and what I'm building

- **Farid Abdurrahman**. Solo founder, Abuja, Nigeria. Email: faridmichika@gmail.com.
- **DOCex** is an AI back-office for African NGOs. It replaces the document-heavy parts of finance, programs, and sub-award work with named agents tuned to specific roles.
- **Today's reality**: pre-revenue. Three warm leads (TA Connect, Sydani Group contact, Neem). Goal is 3 paying pilots by July 31, 2026 (we're in June 2026 now — running tight).
- **My capacity**: ~1-2 hours per day on a normal day, much more on focused build nights.
- **Pricing intent**: Free (3 sessions/month), Pro $99/mo, Enterprise $299/mo. First pilot is ₦6.5M/year (~$4k) with a 3-month free trial.

## 2. The thesis in one paragraph

Every African NGO with more than two years of history has the same problem: too many documents, too few hours, audit and compliance pressure rising as donor funding tightens. The big tools (Fluxx, Foundant, SmartSimple) cost $25-100k/year and aren't built for the African context. DOCex is the AI-native, Paystack-native, NDPR-aware alternative — built for how Nigerian and Pan-African NGOs actually work. The Knowledge Hub becomes the moat (your org's memory); the agents (Bank Verify, Compliance, Attendance Payment) become the daily utility.

## 3. The product — three layers

**Layer 1 — Primitives.** Engines that do work. Each standalone AND composable.
**Layer 2 — Agents.** Pre-built sequences of primitives, tuned for personas.
**Layer 3 — Flow Builder.** Make.com-style canvas for composing custom agents. NOT BUILT YET — Phase 3.

## 4. The five primitives — honestly

### 4.1 Extraction
- **What it does**: User defines N questions, uploads M documents, gets a structured answer per question with confidence + source filename + page + verbatim quote.
- **What works**: handles PDF / DOCX / TXT, parallelised batch, four templates (sub-award screening, quarterly report, invoice/receipt, financial-vs-service reconciliation), Excel export, follow-up email drafting.
- **What's brittle**: image-only PDFs (no OCR), heavily-formatted DOCX with non-standard heading styles, very-long documents > Claude context.

### 4.2 Compliance Check
- **What it does**: Reads a policy PDF/DOCX → produces a structured rulebook with `id, clause_reference, description, evidence_required, category, source_quote, active`. User edits the rulebook. Then runs any payment voucher (with supporting receipts) against the rulebook, rule-by-rule. Five verdicts per rule. Overall verdict: approved / flagged / blocked.
- **What works**: rulebook editor with category grouping, single + batch check modes, approved-PV archive, frozen rulebook snapshot on each check (audit-defensible), email notifications, Excel export, **decision log (just shipped Day 13)** tracking every human action on a check with append-only timeline.
- **What's brittle / weak**: the rulebook detail page doesn't show which checks have been run against it (cohesion gap, identified, not yet fixed); the check upload form doesn't show evidence-required hints upfront so users upload blind; receipt grouping UX could be more intuitive.
- **Sample seeded**: `rulebooks/sample-ngo-procurement.json` ships with 10 realistic Nigerian NGO procurement rules so new users can demo Day 1 without uploading their own policy.

### 4.3 Bank Verify
- **What it does**: Bulk-verifies recipient bank accounts via Paystack `/bank/resolve`. Fuzzy-matches the returned account holder name against the recipient name on the payment schedule.
- **What works**: ~50 Nigerian banks recognized by name OR Paystack code, blended fuzzy matcher (`min(WRatio, token_sort_ratio + 10)` with `processor=str.lower` — tuned for Nigerian names so typos like Abdul↔Abdur land as verified not mismatch), colour-coded Excel export with verdict + match score + bank-of-record name, **CLI mode** also works (`python bank_verify.py schedule.xlsx`), retry with exponential backoff on transient 5xx/network errors, **purpose tagging** (event_payment / grantee_disbursement / vendor_payment / partner_reimbursement / other).
- **What's brittle**: **Paystack test mode caps at 3 bank resolutions per day**. Live mode is free but requires business KYC (CAC + tax ID — in progress with Farid). Until live mode activates, anything more than a 3-row demo will show "Test mode daily limit exceeded" verdicts.
- **Only Nigerian banks**. Pan-African expansion would require Flutterwave/Mono integration — not built.

### 4.4 Knowledge Hub
- **What it does**: Library of uploaded documents (PPTX, DOCX, PDF). Per-document chat with citations. Library-wide chat across all documents with cross-doc citations. Smart folders with AI suggest.
- **What works**: parsers tested against real TA Connect Gates Foundation decks (29 + 67 slides), CHAI Gombe Quarterly Report (DOCX), WGCEO Anti-Fraud Policy (PDF). Citations are clickable chips that deep-link to the right document at the right chunk. Folder filtering, AI folder suggestions.
- **What's brittle**:
  - DOCX without Heading styles collapses into one giant "section" (the CHAI Gombe report did this — 104 body lines, 40 tables, all in section 1). User can still chat with it; just no internal chunking.
  - PDF parsing extracts text + tables but loses any chart/image content. Charts in a 50-page report won't be answerable.
  - **Library-wide chat caps at ~80-100 documents** (Claude Sonnet 4.6's 200K input token limit). When exceeded, the engine populates `truncated_decks: list[str]` and the UI shows an amber warning chip listing which docs were skipped. Semantic retrieval (pgvector) is the Phase 2 escape hatch — not built.
  - Single-deck size cap: 50 MB upload limit (returns 413 with a friendly message).

### 4.5 Rate Cards
- **What it does**: Reusable per-diem schedules. One default rate + per-role overrides (Facilitator ₦30k/day, Participant ₦15k/day). Consumed by the Attendance Payment Agent.
- **What works**: full CRUD editor with in-place rate editing, snapshot frozen onto each Attendance run for audit-defensibility.
- **What's brittle**: nothing significant. Probably the cleanest primitive in the codebase.

## 5. The three composite agents — honestly

### 5.1 Attendance Payment Agent (`/agents/attendance-payment`)
- **What it does**: Programs team's event-payment cycle. Two file inputs (attendance log + payment info form), each can be **.xlsx upload OR Google Sheets URL**. Fuzzy cross-matches names across both. Buckets: paid / no_attendance / no_payment_info. Applies per-role rates from a chosen rate card. Generates `accuracy_flags` (duplicates, implausible days, low-confidence matches) shown in an amber panel above the action band. **Verify button gated on user ticking "I've reviewed these flags"**. One-click hand-off to Bank Verify primitive with `purpose=event_payment` + back-linked `attendance_run_id`. Schedule download as polished xlsx.
- **What works**: end-to-end smoke tested against in-memory test data via the diagnostic.
- **What's brittle**: assumes Excel schedules have headers that hint at "name", "account", "bank", "amount" columns. Heuristic header detection works on TA-Connect-shaped files but might miss unusual layouts.

### 5.2 Sub-award Agent (`/agents/sub-award`)
- **What it does**: Lifecycle shell over existing primitives. Five-step viz: Screen applicants → Award decision (human-only) → Verify grantee accounts → Quarterly report review → Follow up on gaps. Each step links into the underlying primitive pre-configured. Live counts dashboard at the bottom.
- **HONEST CALL-OUT**: this is **a UI shell, not a real composite agent**. It doesn't have its own backend engine; it just routes the user to existing primitive flows with pre-filled context (template_id, purpose). That's fine for now (it solves the discoverability problem for Abosede), but don't assume it has cross-primitive orchestration logic — it doesn't.

### 5.3 Compliance Agent
- **What it is**: The Compliance Check primitive rebranded per persona. Same engine. Different doorway.

## 6. The meta-layers

### 6.1 DOCex Assistant (`assistant.py`, `<AssistantBrief>` component)
- **What it does**: Claude-powered narrator. Every result page (Bank Verify, Attendance Run, Compliance Check, Diagnostic) renders a briefing card at the top: 1-line headline + 2-4 sentence narrative + 0-5 ranked next-action chips (high/medium/low urgency). Type-specific prompts per context. Action chips can wire to real handlers.
- **What works**: structured JSON output from Claude with graceful text fallback on parse failure, graceful "Claude unreachable" fallback that shows a calm message without breaking the page.
- **Cost**: ~$0.002 per briefing. At 50 result-page views/day across 3 pilots, $0.30/day.

### 6.2 Self-Check Agent (`self_check.py`, `/admin/diagnostics`)
- **What it does**: 22 checks across 6 categories (environment, filesystem, engines, API, smoke tests, data integrity). Every failing check has a `fix_hint` telling the operator exactly what to do. Three overall states: healthy / degraded / broken.
- **Admin-gated** via `ADMIN_SECRET` env var — returns 404 (not 401) to anyone without matching `X-Admin-Secret` header. The frontend prompts for the secret once and stores it in localStorage. **Invisible to regular users** by design.

### 6.3 Curator Agent — NOT BUILT, only spec'd
- File `CURATOR_AGENT_SPEC.md` describes 5 capabilities (welcome briefing on upload, near-duplicate detection, stale watcher, cross-reference mapping, weekly digest). **Don't suggest building this** — it ships after first paying pilot.

## 7. The user flow, honestly

A first-time user lands at `http://localhost:3000` (no public URL yet — see "What's missing").

1. They see the Anthropic-style landing with 4 agent cards. They pick one (most likely Compliance based on language framing).
2. They land at `/compliance` — "Your internal auditor, automated". Empty state shows two CTAs: "Try the sample rulebook" (preferred) or "Upload your own policy".
3. If they click sample → `/compliance/rulebooks/sample-ngo-procurement` — they see 10 NGO procurement rules in an editor.
4. From there they can click "Run check" → upload a payment voucher + supporting receipts → DOCex parses the docs, asks Claude to evaluate each rule against the evidence, returns a verdict per rule + overall verdict.
5. Result page shows: Assistant briefing (Claude's plain-English summary) → Decision log timeline (currently just the auto-generated check_run event) → VerdictScreen (rule-by-rule findings with citations from both policy AND payment).
6. User can add notes to the decision log, dismiss specific flags with reasons, mark the check approved. Every action is timestamped + append-only.
7. Approved check goes into the audit-friendly archive at `/compliance/checks`.

## 8. What's missing or weak right now — be honest

### Missing infrastructure
- **No public deployment.** Localhost only. `DEPLOY.md` has the Vercel + Railway walkthrough (~45 min) but Farid hasn't pushed the button.
- **No authentication.** Single-user app. Anyone with the URL can see/edit everything. This is the gate for pilot #2 onboarding (Supabase auth is Phase 2).
- **No multi-tenant data isolation.** When two NGOs share an instance, they share data. Phase 2.
- **No billing.** Pilots will be invoiced manually until Paystack subscriptions are wired.
- **No backup of audit data.** Persistence is JSON files on the Railway volume; if the volume dies, the audit trail dies with it.

### Brittle today
- **Pagination missing** on `/compliance/checks`, `/verify/batches`, `/agents/attendance-payment/runs`, `/knowledge/decks`. List endpoints return everything. Will get slow above ~500 records per primitive.
- **No background job system.** Long extractions (e.g. a 100-doc batch) hold an HTTP connection. Anthropic has a 180s timeout in `knowledge.py` and 120s in `assistant.py` — beyond that, the request fails. Heavy batch operations may time out.
- **Bank Verify is sequential.** 200ms delay between Paystack calls. A 50-row batch takes 10+ seconds; a 500-row batch is unusable in the current sync model.
- **No request ID logging.** Debugging a customer issue across logs is brutal — no trace IDs.

### Cohesion gaps (identified, not yet fixed)
- **Rulebook detail page** has no list of recent checks run against it. User can't easily see "is this rulebook actually in use?"
- **Check upload page** doesn't show `evidence_required` for each rule upfront. Users upload blind and find out what was missing AFTER the check runs.
- **No unified "officer inbox"** at `/compliance` showing "checks awaiting your decision." Officer has to navigate to `/compliance/checks` and filter manually.

## 9. Tech stack

**Backend** (project root, Python 3.12+ recommended 3.13):
- FastAPI + uvicorn
- Pydantic v2 — `model_validate_json` / `model_dump_json` everywhere, NEVER v1 patterns
- openpyxl (Excel I/O), python-pptx, python-docx, pdfplumber (Knowledge Hub parsers)
- rapidfuzz (fuzzy matching)
- httpx (Paystack, Google Sheets, etc.)
- anthropic SDK
- python-dotenv
- File-based JSON persistence under `{project_root}/{primitive}/`
- GZip compression middleware (minimum_size=1024)

**Frontend** (`/web/`):
- Next.js 14 App Router
- TypeScript strict mode
- Tailwind CSS
- shadcn/ui aesthetic
- lucide-react icons
- Geist font
- Brand colour `brand-600` = `#2563eb`
- Warm cream landing background `#fafaf7`
- Verdict palette: emerald (pass/found/verified), amber (flag/inferred/warning), rose (block/mismatch), gray (n/a/not_found/unverifiable), sky (insufficient_evidence)

**AI**: Claude Sonnet 4.6 (`claude-sonnet-4-6`) with explicit timeouts (120s assistant, 180s knowledge)
**Banking**: Paystack `/bank/resolve` only (Nigerian banks)
**Deployment target**: Vercel (frontend) + Railway (backend with persistent volume)

## 10. Project structure

```
docex/
  models.py                          # All Pydantic models — single source of truth
  screener.py                        # Extraction engine
  compliance.py                      # Compliance Check engine
  bank_verify.py                     # Bank Verify engine + Excel parser + CLI
  attendance_agent.py                # Attendance Payment Agent engine
  slides.py                          # Knowledge Hub multi-format parser (PPTX/DOCX/PDF)
  knowledge.py                       # Knowledge Hub Q&A engine (per-doc + library-wide)
  assistant.py                       # DOCex Assistant narrator
  self_check.py                      # Self-Check diagnostic
  notifications.py                   # SMTP email notifications
  requirements.txt
  .env / .env.example                # ANTHROPIC_API_KEY, PAYSTACK_SECRET_KEY, ADMIN_SECRET

  CURATOR_AGENT_SPEC.md              # Spec for the Curator Agent (build after first pilot)
  CLAUDE.md                          # Project memory
  DEEPSEEK_BRIEFING.md               # Briefing for DeepSeek (parallel to this file)
  DEPLOY.md                          # 45-min deployment walkthrough
  PLAYBOOK.md                        # Sales playbook (Jul 31 target)

  api/
    main.py                          # FastAPI app, mounts every router
    schemas.py                       # Request/response Pydantic schemas
    compliance_routes.py             # /compliance/*
    bank_verify_routes.py            # /verify/*
    attendance_agent_routes.py       # /agents/attendance-payment/*
    rate_card_routes.py              # /rate-cards/*
    knowledge_routes.py              # /knowledge/*
    assistant_routes.py              # /assistant/*
    self_check_routes.py             # /diagnostics/* (admin-gated)
    Dockerfile                       # Python 3.12-slim base
  railway.toml                       # Railway deploy config
  web/vercel.json                    # Vercel deploy config

  web/
    app/
      page.tsx                       # Anthropic-style landing
      app/page.tsx                   # Extraction wizard
      compliance/                    # Compliance Check pages
      verify/                        # Bank Verify pages
      agents/attendance-payment/     # Attendance Agent pages
      agents/sub-award/page.tsx      # Sub-award lifecycle shell
      knowledge/                     # Knowledge Hub pages (library + chat)
      rate-cards/page.tsx
      admin/diagnostics/page.tsx     # Self-Check (admin-gated)
      error.tsx                      # Global error boundary
    components/
      AssistantBrief.tsx             # Reusable briefing card
      GuidanceCard.tsx
      compliance/DecisionTimeline.tsx   # Human decision log timeline
      compliance/VerdictScreen.tsx
      ...
    lib/
      api.ts                         # All API client functions (88 calls converted to throwFriendly)
      errors.ts                      # User-friendly error mapping
      buckets.ts, templates.ts, ...
    types/index.ts                   # ALL frontend types — mirrors models.py

  rulebooks/                         # Persisted rulebooks (sample-ngo-procurement.json shipped)
  checks/                            # Persisted compliance checks
  verifications/                     # Persisted Bank Verify batches
  attendance_runs/                   # Persisted Attendance Payment runs
  rate_cards/                        # Persisted rate cards
  decks/                             # Persisted Knowledge Hub documents
  diagnostics/                       # Persisted Self-Check reports
```

## 11. Key technical decisions to honour

### Fuzzy name matching (Bank Verify + Attendance Agent)
```python
def _name_match_score(schedule_name: str, bank_record_name: str) -> int:
    w = fuzz.WRatio(schedule_name, bank_record_name, processor=str.lower)
    t = fuzz.token_sort_ratio(schedule_name, bank_record_name, processor=str.lower)
    return int(min(w, t + 10))
```
`processor=str.lower` is **critical** — rapidfuzz is case-sensitive by default; bank-of-record names come back UPPERCASE. Without lowering, "Mohammed" vs "MOHAMMED" tanks to ~20. WRatio catches within-token typos (Abdul↔Abdur). `token_sort_ratio + 10` clamp prevents shared-first-name false positives (Mohammed Tunde vs Mohammed Farid Abdurraman). Thresholds: 85+ verified, 65-84 warning, <65 mismatch.

### Pydantic v2 everywhere
`model_validate_json` / `model_dump_json(indent=2)`. `from __future__ import annotations` at the top of every Python file. `Optional[X]` (the codebase is consistent). Persistence: `path.write_text(model.model_dump_json(indent=2))` and `Model.model_validate_json(path.read_text())`.

### Audit-trail snapshotting
- Compliance Check: snapshots the active rules onto the result (`rulebook_snapshot_rules`).
- Attendance Payment run: snapshots the entire RateCard onto the run.
- Editing the source later never changes historical records.

### Decision log (Day 13 build)
Compliance checks now carry a `decision_log: list[DecisionEvent]` — append-only. Seven event types (check_run, note_added, rule_dismissed, rule_escalated, clarification_requested, approved, unapproved). Auto-seeded on first save. Endpoints: `POST /compliance/checks/{id}/notes`, `POST /compliance/checks/{id}/rules/{rule_id}/decision`. Frontend `<DecisionTimeline>` component sits between AssistantBrief and VerdictScreen.

### Friendly error helper
`web/lib/errors.ts` exposes `throwFriendly(res)` used by ~32 call sites. Maps HTTP status + body to user-friendly sentences (Anthropic auth, Paystack quota, validation, network, 5xx). Raw error preserved on `.cause` for debugging.

### Admin gate
`/diagnostics/*` routes use `Depends(_require_admin)` which checks `ADMIN_SECRET` env vs `X-Admin-Secret` header. Returns 404 (not 401) when mismatched — feature appears not to exist. Frontend stores secret in localStorage.

### Composite-agent pattern
Composite agents chain primitives via shared engine imports. Pattern from `api/attendance_agent_routes.py`:
```python
from bank_verify import verify_batch
from .bank_verify_routes import _save_batch

# in POST /runs/{id}/verify:
rows = [BankAccountRow(...) for m in run.matched]
batch = verify_batch(rows)
batch.purpose = "event_payment"
batch.attendance_run_id = run.run_id
batch = _save_batch(batch)
run.bank_verify_batch_id = batch.batch_id
_save_run(run)
```

### Knowledge Hub multi-format unified shape
All three formats parse into the same `SlideDeck` Pydantic model with a `content_type` field. Internal "Slide" model is used for any chunk; `chunk_label_for(content_type)` returns "Slide"/"Page"/"Section" for UI. Citation regex matches all three: `\[(?:Slide|Section|Page)\s+(\d+(?:\s*,\s*\d+)*)\]`. Library-wide citations: `[Document Name → Slide N]`.

## 12. CLAUDE.md working rules (these apply to you too)

- Never rewrite working code to fix one small thing
- One feature at a time, show before moving on
- After each step tell me exactly what to run to test it
- When in doubt do less better
- Comments on non-obvious logic
- Always add error handling and loading states
- Match Pydantic v2 conventions, snake_case in models, verdict palette, the comment style

## 13. The pitch (per persona)

- **TA Connect / Abosede (sub-award)**: lead with the Sub-award Agent lifecycle (Extraction → Bank Verify → Quarterly Review)
- **Neem owner (lost her auditor)**: lead with "Your internal auditor, automated" (Compliance Check + Decision Log)
- **Sydani contact (search across past docs)**: lead with Knowledge Hub library-wide chat

Same product, three different opening pitches.

## 14. What I might ask you (ChatGPT)

- Code review on a specific file or feature
- Drafting proposal emails per pilot
- Brainstorming product features but ALWAYS scope honestly (don't suggest 18-hour items in a 2-day window — see how DeepSeek over-estimated three times in our last brief)
- Helping me prep for pilot demos (Loom scripts, talking points)
- Designing future agents (Curator, Onboarding, Procurement)
- Reviewing the cohesion gaps in section 8 and suggesting targeted fixes

## 15. Things I do NOT want suggested

- Adding authentication NOW (Phase 2, gated on pilot #2)
- Switching to a database NOW (file-based works, Supabase is Phase 2)
- Building new agents speculatively (none of the 3 leads have asked for them)
- Procurement Agent / Bid Analyst / GRN Match (defer until customer signal)
- Mobile UI optimization (desktop-first, defer indefinitely)
- Kubernetes / microservices / GraphQL / anything enterprise-shaped (overkill)
- Auto-deletion of old runs (audit trails should never auto-delete)
- Keyboard shortcuts, changelog modals, "what's new" badges (premature)
- Onboarding wizards or product tours (haven't earned this user yet)

## 16. The single-line pitch

> DOCex gives African NGOs an AI back-office — a Knowledge Hub that's their organisation's memory, plus agents for sub-award screening, event payments, bank verification, and compliance review — every answer cited so it's audit-defensible, every flow built around how African finance and programs teams actually work.

---

End of briefing. Ask away — and please be as honest as I've tried to be here.
