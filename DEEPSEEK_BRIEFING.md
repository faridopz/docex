# DOCex — Context Briefing (Day 11 snapshot)

Paste this entire document as the first message to DeepSeek (or any other LLM). It contains everything they need about who I am, what DOCex is, the architecture, what's shipped, what's pending, what conventions to honour, and what's coming next. After the briefing, ask your specific question.

---

## 1. Who I am

- **Farid Abdurrahman**. Solo founder. Abuja, Nigeria.
- **DOCex** — AI back-office for African NGOs. Replaces document-heavy work in finance, programs, and sub-award teams.
- ~1-2 hours/day baseline, much more on sprint nights.
- **Goal**: 3 paying pilots by July 31, 2026.
- **Today's status**: pre-revenue, but three warm leads in play (see Customer Pipeline below).
- **Pricing model**: internal — never surfaced on landing, in the PDF, or in product UI. Volume scoped per-pilot in conversation. Founder retains tier amounts in private notes.

## 2. Customer pipeline (three warm leads)

| Lead | Validation | What they care most about |
|---|---|---|
| **TA Connect** (Abuja, public-health NGO) | Sub-award team screens 200+ applications per cycle; programs team verifies bank accounts manually | Sub-award Agent (Abosede) — Extraction + Bank Verify + Quarterly Review lifecycle. Compliance officer back ~mid-June. |
| **Sydani Group contact** | "We have a knowledge management system, but searching across past project docs is broken — you have to open each file individually" | Knowledge Hub — multi-doc library + library-wide chat |
| **Neem (owner)** | "We do attendance manually. I used to have an internal auditor but don't anymore." | Compliance Check ("internal auditor in a box") + Attendance Payment Agent |

Each lead maps to specific primitives — same product, three different opening pitches.

## 3. The product, plain English

DOCex is an AI back-office. **Five primitives** (engines that do work), **three composite agents** (named workflows that chain primitives), **two meta-layers** (Self-Check + DOCex Assistant), one Knowledge Hub that's becoming the moat.

## 4. Three-layer architecture (the mental model)

**Layer 1 — Primitives**. Each works standalone AND composes into agents.
**Layer 2 — Agents (templates)**. Pre-built sequences tuned for personas.
**Layer 3 — Flow Builder** (Phase 3). Make.com-style canvas for composing custom agents. Not built — every primitive must expose clean inputs/outputs so it slots in later.

## 5. The five primitives (engines)

### 5.1 Extraction (`screener.py`, `/app`)
Read N documents, answer M user-defined questions. Each answer has confidence (found / inferred / not_found), source document, page, verbatim quote. Templates for sub-award screening, quarterly report review, invoice/receipt extraction, financial-vs-service reconciliation. Auto-buckets applicants (complete / partial / major-gaps), drafts follow-up emails, exports Excel + JSON. Parallelised batch. PDF + DOCX + TXT input.

### 5.2 Compliance Check (`compliance.py`, `/compliance`)
Read a policy doc → interpret into a structured rulebook (editable). Run any payment voucher against the rulebook, rule-by-rule. Five verdicts per rule: pass / flag / block / not_applicable / insufficient_evidence. Overall: approved / flagged / blocked. Approved-PV archive with frozen rulebook snapshot (audit-defensibility — editing the rulebook later never changes historical checks). Email notifications, Excel export, single + batch modes. **A pre-built sample rulebook ships at `rulebooks/sample-ngo-procurement.json`** so new users can demo Day 1 without bringing their own policy.

### 5.3 Bank Verify (`bank_verify.py`, `/verify`)
Bulk verification of recipient bank accounts via Paystack `/bank/resolve`. Blended fuzzy matcher: `min(fuzz.WRatio, fuzz.token_sort_ratio + 10)` with `processor=str.lower` — catches typos as verified, prevents shared-first-name false positives. Thresholds: ≥85 verified, 65-84 warning, <65 mismatch. Four verdicts: verified / warning / mismatch / unverifiable. Bank-name → Paystack code lookup for ~50 Nigerian banks. Auto-detects Excel header rows + columns. **Purpose tagging** (event_payment / grantee_disbursement / vendor_payment / partner_reimbursement / other) drives audit filtering + future notification routing. Colour-coded xlsx export with verdict + match score + bank-of-record name. CLI mode also works.

### 5.4 Knowledge Hub (`slides.py` + `knowledge.py`, `/knowledge`)
Multi-format document library with chat. Accepts **PPTX, DOCX, PDF**. Each format parses into a `SlideDeck` with format-aware chunks:
- PPTX → slides with title + body + speaker notes + tables
- PDF → pages with body + heuristic title + extracted tables
- DOCX → sections split by Heading style, each with title + body + tables

Two chat surfaces:
- **Per-document chat** (`/knowledge/[id]`) — focused conversation with one document. Citations use vocab matching the format: `[Slide N]` for PPTX, `[Page N]` for PDF, `[Section N]` for DOCX. Clickable chips scroll to the cited chunk + pulse-highlight.
- **Library-wide chat** (`/knowledge`) — one chat across every document. Citations carry document name + chunk: `[Anti-Fraud Policy → Page 4]`, `[Gates Check-in March → Slide 11]`. Chips deep-link to the source document.

**Smart folders**: every document has an optional `folder` field (slash-delimited path like `Reports/2026/Q1`). Folder filter pills on the library landing. Each card has inline folder edit + AI **"Suggest folder"** button — Claude reads the document + existing library structure → proposes a path.

### 5.5 Rate Cards (`/rate-cards`)
Reusable per-diem schedules. One default rate + zero-to-many per-role overrides (Facilitator ₦30k/day, Participant ₦15k/day). Consumed by Attendance Payment Agent. Card snapshot frozen onto each run for audit-defensibility. In-place CRUD editor.

## 6. The three composite agents

### 6.1 Attendance Payment Agent (`/agents/attendance-payment`)
Programs team's full event-payment cycle. Two inputs: attendance log + payment info form. Each can be `.xlsx` OR a **Google Sheets URL** (the same pattern Knowledge Hub will use for connectors). Fuzzy cross-matches names. Buckets: paid / no_attendance / no_payment_info. Applies per-role rates from a chosen rate card. Generates `accuracy_flags` (duplicates, implausible days, low-confidence matches) shown in an amber panel. **Verify button gated on user ticking "I've reviewed these flags"**. One-click hand-off to Bank Verify primitive with `purpose=event_payment` + back-linked `attendance_run_id`. Schedule download as polished xlsx.

### 6.2 Sub-award Agent (`/agents/sub-award`)
Lifecycle shell over existing primitives. Five steps: Screen applicants → Award decision (human-only) → Verify grantee accounts → Quarterly report review → Follow up on gaps. Each step links into the underlying primitive pre-configured (Extraction with sub-award template, Bank Verify with `purpose=grantee_disbursement`, Extraction with quarterly template). Live counts dashboard. No new backend engine — composes existing primitives.

### 6.3 Compliance Agent
The Compliance Check primitive rebranded per persona for compliance officers. Same engine.

## 7. The meta-layers

### 7.1 DOCex Assistant (`assistant.py`, `<AssistantBrief>` component)
Claude-powered narrator. Every result page renders a briefing card at the top: 1-line headline + 2-4 sentence narrative + 0-5 ranked next-action chips (high/medium/low urgency). Type-specific prompts: `bank_verify_batch` / `attendance_run` / `compliance_check` / `diagnostic`. Action chips can wire to real handlers. Graceful fallback when Claude is unreachable. Cost ~$0.002 per briefing.

### 7.2 Self-Check Agent (`self_check.py`, `/admin/diagnostics`)
Runtime production-readiness diagnostic. 22 checks across 6 categories: environment (API keys, Python version) · filesystem (persistence dirs writable) · engines (modules import cleanly) · api (all routes registered) · smoke (fuzzy matcher canonical cases, bank-code lookup, Attendance e2e) · data (every persisted record parses under its model). Three overall states: healthy / degraded / broken. Every failing check has a `fix_hint`. **Admin-gated via `ADMIN_SECRET` env var** — returns 404 to anyone without the matching `X-Admin-Secret` header (invisible to regular users).

### 7.3 Curator Agent (spec only, not built)
The agent that makes the Knowledge Hub *alive*. V1 ships after first paying pilot signs. Five capabilities:
1. **Welcome briefing on upload** — summary + folder + tags + related docs in one card
2. **Near-duplicate detection** — flag when new uploads overlap existing
3. **Stale document watcher** — weekly scan for docs untouched in N months
4. **Cross-reference mapping** — entity-based "Referenced in this document" panel
5. **Weekly digest** — "what changed in your library this week"

Full spec at `CURATOR_AGENT_SPEC.md` in the project root. ~3-4 days of work when built.

## 8. Tech stack

**Backend** (project root):
- Python 3.12+ (3.13 recommended)
- FastAPI + uvicorn
- Pydantic v2 (use `model_validate_json` / `model_dump_json` — never v1 patterns)
- openpyxl (Excel I/O)
- python-pptx, python-docx, pdfplumber (Knowledge Hub parsers)
- rapidfuzz (fuzzy name matching)
- httpx (Paystack, Google Sheets, etc.)
- anthropic SDK
- python-dotenv
- File-based JSON persistence — swaps to Supabase in Phase 2

**Frontend** (`/web/`):
- Next.js 14 App Router
- TypeScript strict mode
- Tailwind CSS
- shadcn/ui aesthetic
- lucide-react icons
- Geist font
- Brand colour `brand-600` = `#2563eb` (blue-600)
- Warm cream landing background `#fafaf7`
- Verdict palette: emerald (pass/found/verified), amber (flag/inferred/warning), rose (block/mismatch), gray (n/a/not_found/unverifiable), sky (insufficient_evidence)

**AI**: Claude Sonnet 4.6 (`claude-sonnet-4-6`)
**Banking**: Paystack `/bank/resolve` (test mode caps at 3 resolves/day; live mode is free but needs business KYC)

## 9. Project structure

```
docex/
  models.py                          # All Pydantic models — single source of truth
  screener.py                        # Extraction engine
  compliance.py                      # Compliance Check engine
  bank_verify.py                     # Bank Verify engine + Excel parser + CLI
  attendance_agent.py                # Attendance Payment Agent engine
  slides.py                          # Knowledge Hub multi-format parser
  knowledge.py                       # Knowledge Hub Q&A engine (per-doc + library-wide)
  assistant.py                       # DOCex Assistant narrator
  self_check.py                      # Self-Check diagnostic
  notifications.py                   # SMTP email notifications
  requirements.txt
  .env / .env.example                # ANTHROPIC_API_KEY, PAYSTACK_SECRET_KEY, ADMIN_SECRET

  CURATOR_AGENT_SPEC.md              # Spec for the Curator Agent (build after first pilot)
  DEEPSEEK_BRIEFING.md               # This file
  CLAUDE.md                          # Project memory
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

  web/
    app/
      page.tsx                       # Anthropic-style landing (4 agent cards + Assistant moment)
      app/page.tsx                   # Extraction wizard
      compliance/
        page.tsx                     # "Your internal auditor, automated" landing
        new/page.tsx                 # New policy upload
        rulebooks/[id]/page.tsx      # Rulebook editor
        rulebooks/[id]/check/page.tsx
        checks/page.tsx              # Saved checks list
        checks/[id]/page.tsx         # Check detail (with AssistantBrief)
      verify/
        page.tsx                     # "Never pay the wrong account again" landing
        new/page.tsx                 # Bank Verify upload wizard
        [id]/page.tsx                # Result detail (with AssistantBrief)
      agents/
        attendance-payment/          # "Attendance to paid, in three minutes"
        sub-award/page.tsx           # Lifecycle shell over primitives
      knowledge/
        page.tsx                     # Library landing — library-wide chat + folder pills + smart cards
        new/page.tsx                 # Upload (PPTX/DOCX/PDF)
        [id]/page.tsx                # Per-doc chat with slide list + clickable citations
      rate-cards/page.tsx            # CRUD editor
      admin/diagnostics/page.tsx     # Self-Check (admin-gated)
    components/
      AssistantBrief.tsx             # Reusable briefing card
      GuidanceCard.tsx
      ApplicantUpload.tsx
      DropZone.tsx
      ExtractionTable.tsx
      QuestionBuilder.tsx
      compliance/
      ui/
    lib/
      api.ts                         # ALL API client functions
      buckets.ts
      quarter-detect.ts
      templates.ts
      utils.ts
      workflow-labels.ts
    types/index.ts                   # ALL frontend types — mirrors models.py

  rulebooks/                         # Persisted rulebooks (incl. sample-ngo-procurement.json)
  checks/                            # Persisted compliance checks
  verifications/                     # Persisted Bank Verify batches
  attendance_runs/                   # Persisted Attendance Payment runs
  rate_cards/                        # Persisted rate cards
  decks/                             # Persisted Knowledge Hub documents
  diagnostics/                       # Persisted Self-Check reports
```

## 10. API endpoint inventory (~50 endpoints across 8 routers)

```
GET    /health
POST   /extract/single
POST   /extract/batch
POST   /draft-followups

POST   /compliance/policy
GET    /compliance/rulebooks
GET    /compliance/rulebooks/{id}
PUT    /compliance/rulebooks/{id}
DELETE /compliance/rulebooks/{id}
POST   /compliance/check/single
POST   /compliance/check/batch
GET    /compliance/checks
GET    /compliance/checks/{id}
POST   /compliance/checks/{id}/approve
POST   /compliance/checks/{id}/unapprove
DELETE /compliance/checks/{id}

POST   /verify/bank-batch                    # purpose-tagged batch verification
GET    /verify/batches
GET    /verify/batches/{id}
GET    /verify/batches/{id}/export.xlsx      # colour-coded xlsx
DELETE /verify/batches/{id}

POST   /agents/attendance-payment/run        # accepts files OR Google Sheets URLs + rate_card_id
GET    /agents/attendance-payment/runs
GET    /agents/attendance-payment/runs/{id}
POST   /agents/attendance-payment/runs/{id}/verify     # chains to Bank Verify
GET    /agents/attendance-payment/runs/{id}/schedule.xlsx
DELETE /agents/attendance-payment/runs/{id}

GET    /rate-cards
GET    /rate-cards/{id}
POST   /rate-cards
PUT    /rate-cards/{id}
DELETE /rate-cards/{id}

POST   /knowledge/decks                      # upload PPTX/DOCX/PDF
GET    /knowledge/decks
GET    /knowledge/decks/{id}
PATCH  /knowledge/decks/{id}                 # rename, move folder, retag
DELETE /knowledge/decks/{id}
POST   /knowledge/decks/{id}/chat            # per-document chat
POST   /knowledge/library/chat               # library-wide chat (optional folder + tag scoping)
POST   /knowledge/folders/suggest            # Claude proposes a folder for a document

POST   /assistant/summarize                  # used by every result page

POST   /diagnostics/run                      # admin-gated
GET    /diagnostics/last                     # admin-gated
GET    /diagnostics                          # admin-gated (list)
GET    /diagnostics/{id}                     # admin-gated
DELETE /diagnostics/{id}                     # admin-gated
```

## 11. Key technical decisions to honour

### Fuzzy name matching (Bank Verify + Attendance Agent)
```python
def _name_match_score(schedule_name: str, bank_record_name: str) -> int:
    w = fuzz.WRatio(schedule_name, bank_record_name, processor=str.lower)
    t = fuzz.token_sort_ratio(schedule_name, bank_record_name, processor=str.lower)
    return int(min(w, t + 10))
```
`processor=str.lower` is critical — rapidfuzz is case-sensitive by default; bank-of-record names come back UPPERCASE. WRatio catches within-token typos (Abdul ↔ Abdur). The token_sort_ratio + 10 clamp prevents "shared first name" false positives. Thresholds: 85+ verified, 65-84 warning, <65 mismatch.

### Pydantic v2 throughout
`model_validate_json` / `model_dump_json(indent=2)` everywhere. `from __future__ import annotations` at the top of every Python file. `Optional[X]` (the codebase is consistent — match it). Persistence pattern: `path.write_text(model.model_dump_json(indent=2))` and `Model.model_validate_json(path.read_text())`.

### File-based persistence
Each primitive owns a directory: `/rulebooks/`, `/checks/`, `/verifications/`, `/rate_cards/`, `/attendance_runs/`, `/decks/`, `/diagnostics/`. The `_save_*` / `_load_*` / `_list_*` helpers in each routes file follow the same shape. Bootstrapped at `api.main` import time so fresh checkouts don't trip on first request.

### "Purpose" tagging on Bank Verify batches
Every batch carries `purpose` (event_payment / grantee_disbursement / vendor_payment / partner_reimbursement / other) and optional `purpose_detail`. Drives audit filtering, future notification routing, and per-purpose threshold tuning.

### Audit-trail snapshotting
When a Compliance Check runs, the active rules are snapshotted onto the result (`rulebook_snapshot_rules`). When an Attendance Payment run consumes a rate card, the entire RateCard is snapshotted onto the run. Editing the source later doesn't alter historical audit trails.

### Composite-agent pattern
Composite agents chain primitives via shared engine imports. From `api/attendance_agent_routes.py`:
```python
from bank_verify import verify_batch
from .bank_verify_routes import _save_batch

# inside POST /runs/{id}/verify:
rows = [BankAccountRow(...) for m in run.matched]
batch = verify_batch(rows)
batch.purpose = "event_payment"
batch.attendance_run_id = run.run_id
batch = _save_batch(batch)
run.bank_verify_batch_id = batch.batch_id
_save_run(run)
```

### Knowledge Hub multi-format unified shape
All three formats (PPTX, DOCX, PDF) parse into the same `SlideDeck` model with `content_type` field. Chunks call themselves "slides" in code (historical name), but `chunk_label_for(content_type)` returns "Slide" / "Page" / "Section" for UI vocabulary. Citation regex matches all three: `\[(?:Slide|Section|Page)\s+(\d+(?:\s*,\s*\d+)*)\]`.

### Library-wide chat citations
Format: `[Document Name → Slide N]` / `[Document Name → Page N]` / `[Document Name → Section N]`. Parser back-resolves the document name (case-insensitive, substring-tolerant) to a deck_id so citation chips can deep-link.

### Admin gate
`/diagnostics/*` routes gated by FastAPI Depends on `_require_admin` which checks `ADMIN_SECRET` env var vs `X-Admin-Secret` header. Returns 404 (not 401) when mismatched — feature appears not to exist to anyone without the secret. Frontend stores secret in localStorage after a one-time secret-input prompt.

### Accuracy gate before Bank Verify chains
Attendance Payment Agent generates `accuracy_flags` after matching (duplicates, implausible days, low-confidence matches). Frontend renders these in an amber panel; **Verify button is gated on the user ticking "I've reviewed these flags"**. Bank Verify is still the final hard gate at payment time; this is the earlier soft gate.

### Frontend conventions
- All API calls go through `web/lib/api.ts` — one function per endpoint, throws `Error` on non-2xx
- All types in `web/types/index.ts` — mirror `models.py` exactly, snake_case preserved
- "Whole card is the click target" pattern (Fitts's law)
- Sticky header on every internal page
- GuidanceCard reused for first-time-user copy
- "Static class maps" for Tailwind colour tokens (Tailwind purges interpolated class names — never `bg-${tone}-50`)
- DOCex Assistant briefing card at the top of every result page

## 12. Customer-facing positioning (current, May 2026)

- Landing page: "The AI back-office for African NGOs · Stop reading every document. Start doing the work."
- Compliance Check landing: **"Your internal auditor, automated"** (Neem's exact pain)
- Bank Verify landing: **"Never pay the wrong account again"** (fraud-prevention framing)
- Attendance Agent landing: **"Attendance to paid, in three minutes"** (outcome-led)
- Knowledge Hub landing: **"Your organisation's memory"** (cross-doc memory framing)

## 13. What's shipped (everything below is working locally today)

- Extraction primitive + 4 templates + follow-up email drafter
- Compliance Check + sample seeded rulebook + approved-PV archive + email notifications
- Bank Verify + Paystack live integration tested with real Nigerian account
- Attendance Payment Agent (composite) — files OR Google Sheets URLs, rate cards, accuracy gate, one-click chain to Bank Verify
- Knowledge Hub — PPTX/DOCX/PDF library, per-doc chat, library-wide chat, smart folders with AI suggest
- Sub-award Agent (lifecycle shell)
- Rate Cards (CRUD with per-role rates)
- DOCex Assistant briefings on every result page
- Self-Check Agent (admin-gated diagnostic, 22 checks)
- Anthropic-style landing redesign
- Cross-navigation everywhere
- File-based persistence, audit snapshotting, gzip compression, bootstrap dirs at boot

## 14. What's pending

- **Paystack live mode** — test mode caps at 3 resolves/day; live mode is free but needs CAC + tax ID (Farid is processing business registration)
- **Public deployment** — Vercel + Railway. Gated on first signed pilot per playbook, but considering doing earlier
- **Supabase auth + multi-tenant** — Phase 2, needed when pilot #2 onboards
- **Curator Agent V1** — spec is locked (`CURATOR_AGENT_SPEC.md`), build after first pilot signs
- **Onboarding Agent** (bulk historical doc ingestion + AI organize) — deferred
- **External connectors** (Google Drive, SharePoint) — defer until paying customer drives which one
- **Procurement Agent** (Bid Analyst + GRN Match) — defer
- **Self-Improvement Agent V2** — observe + recommend
- **Flow Builder** — Phase 3
- **Mobile-optimised UI** — desktop-first, defer indefinitely

## 15. CLAUDE.md working rules (apply these too)

- Never rewrite working code to fix one small thing
- One feature at a time, show before moving on
- After each step tell me exactly what to run to test it
- When in doubt do less better
- Comments on non-obvious logic
- Always add error handling and loading states
- Match Pydantic v2 conventions, snake_case in models, the verdict palette, the comment style

## 16. What I might ask you (DeepSeek)

- Reviewing code for security, correctness, or style
- Drafting the TA Connect / Neem / Sydani pilot proposals
- Helping design the Curator Agent or future agents
- Sanity-checking the fuzzy matcher against edge cases
- Drafting marketing copy / Loom scripts
- Helping with Supabase migration design
- Helping prep for pilot demos

When you respond:
- Match existing conventions (Pydantic v2, file persistence, verdict palette, comment style)
- Explain WHY before WHAT
- Don't rewrite working code unless I explicitly ask
- If I'm pushing too hard / too tired, say so
- Prefer Nigerian / African defaults for anything region-specific

## 17. The one-sentence pitch

> DOCex gives African NGOs an AI back-office — a Knowledge Hub that's their organisation's memory, plus agents for sub-award screening, event payments, bank verification, and compliance review — every answer cited so it's audit-defensible, every flow built around how African finance and programs teams actually work.

---

End of briefing. Ask away.
