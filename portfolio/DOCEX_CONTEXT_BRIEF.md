# DOCex — architecture & flow brief (for onboarding another AI/chat)

## What it is
AI document-intelligence for **donor-funded NGO finance & compliance**. Input:
documents (vouchers, invoices, POs, GRNs, receipts, policies). Output: per-rule
**verdicts** (pass / flag / block) with citations + an audit trail.

## Core philosophy (do not re-litigate)
**Deterministic-first. Code does the certain; the LLM does the judgment.**
Arithmetic + exact lookups run in code (fast, exact, auditable, free, no
hallucination). Claude is used only for messy reading, policy interpretation,
ambiguous judgment, drafting. **A code-level `block` always overrides the LLM.**

---

## Repo map (backend engine — root-level Python)
| Module | Responsibility | Key entry points |
|---|---|---|
| `fast_extract.py` | Parse files → text (PyMuPDF→pdfplumber; DOCX order-preserving; XLSX) | `extract_text(fn,bytes)`, `extract_many(files)`, `is_probably_scanned` |
| `fast_fields.py` | Labelled-regex field pull | `extract_fields(text)` → `{fields:{f:{value,confidence}}, needs_llm}` |
| `doc_completeness.py` | Which required docs are present | `classify(fn,text)`, `check_completeness(required, files)` |
| `policy_rules.py` | Policy text → structured rules (no LLM) | `extract_rules(documents)` → `list[PolicyRule]` |
| `payment_checks.py` | AP controls | `run_document_checks(docs, prior_invoice_numbers)` → `list[RuleResult]`; `three_way_match`, `duplicate_invoice`, `primary_invoice_number` |
| `deterministic_checks.py` | Form-field rules (date/threshold/membership/…) | `evaluate_deterministic_rules(rules, form_data)` → `list[RuleResult]` |
| `receipts.py` | Retirement reconciliation | `reconcile(advance, receipts, trip_start, trip_end)` → `Reconciliation` |
| `compliance.py` | **Hybrid check engine** + policy interpret | `check_payment` / `check_payment_safe`, `interpret_policy`, `_derive_overall_verdict` |
| `compliance_router.py` | Auto-pick rulebook for a payment | `rank_rulebooks(text, rulebooks)` |
| `hybrid.py` | Code-first + graceful-degradation helpers | `scope_llm`, `run_with_fallback` |
| `models.py` | All Pydantic models | see below |
| `docex_agent.py` | **Agent runner** (Claude orchestrates; tools = the engine) | `process`, `run_agent`, `build_tools`, `_ingest` |

API layer: `api/main.py` (app + `/extract/*`), `api/compliance_routes.py` (all
`/compliance/*`), plus knowledge / bank_verify / attendance / rate_card routes
(archived from the demo via `enabled_modules`). Frontend: Next.js 14 App Router
in `web/` — pages under `web/app/compliance/*`, typed client `web/lib/api.ts`.

## Key data models (`models.py`)
- **PolicyRule**: `id, description, condition, evidence_required[], category, source_quote, clause_reference, evaluation_type("llm"|"deterministic"), deterministic_check`
- **PolicyRulebook**: `id, name, source_documents[], rules[], approval_workflow[], org`
- **RuleResult**: `rule_id, rule_description, verdict("pass"|"flag"|"block"|"insufficient_evidence"), reasoning, policy_citation, payment_evidence, confidence`
- **ComplianceCheckResult**: `payment_id, documents[], rulebook_id, overall_verdict("approved"|"flagged"|"blocked"), overall_summary, results[RuleResult], invoice_number, reconciliation, decision_log[], approved, paid, risks[]`
- **Reconciliation**: `advance_amount, total_spent, balance, direction("recover"|"reimburse"|"settled"|"out_of_pocket"), flags[RuleResult], summary`
- **OrgProfile**: `name, roles, default_approval_workflow, payment_types[PaymentType], enabled_modules[]`

## API surface (compliance)
`POST /compliance/policy/async` → `PolicyJob` (bg rulebook build) · `GET /policy/jobs/{id}`
· `POST /precheck` · `POST /route` · `POST /check/single` · `POST /check/form`
· `POST /retire` · `GET /rulebooks|/checks|/audit-log|/pending` · `POST /checks/{id}/request-signoff|risks|mark-paid|notes` · `GET/POST /approve/{token}` · `approval-callback` · `GET/PUT /org-profile`

---

## FLOW A — Payment check (`POST /compliance/check/single`)
```
multipart: payment_documents[] + rulebook_id
  → _read_files()            → fast_extract.extract_many()  → [(filename, text)]        (parallel, code)
  → _run_ap_controls()       → payment_checks.run_document_checks(docs, prior_invoice_numbers)
                                → [RuleResult] (three-way match, duplicate)  + primary_invoice_number   (code)
  → check_payment_safe(docs, rulebook, document_findings=ap_findings):
        active = [r for r in rulebook.rules if r.active]
        split → llm_rules (evaluation_type="llm") | deterministic_rules ("deterministic")
        deterministic_results = evaluate_deterministic_rules(deterministic_rules, form_data)      (code)
        early = document_findings + deterministic_results
        IF _derive_overall_verdict(early) == "blocked": RETURN now  (skip Claude — fast path)
        ELSE: Claude messages.parse(system + rulebook  [both cache_control])  → parsed.results    (LLM, judgment only)
        all_results = document_findings + deterministic_results + parsed.results
        verdict = parsed verdict, but a code-level block ALWAYS wins
  → result.invoice_number set; _save_check() (snapshots active rules + seeds decision_log); notifications
  ← ComplianceCheckResult
```

## FLOW B — Policy → rulebook (`POST /compliance/policy/async`)
```
upload policy file(s) → returns PolicyJob {status:"processing", preview} INSTANTLY
background _run_policy_job():
   code_rules = policy_rules.extract_rules(docs)          (deterministic, ~ms)
   IF len(code_rules) >= 3: build rulebook from code_rules            (no LLM)
   ELSE: interpret_policy(docs)  (Claude) ; if that fails but code found some → use code_rules
   save rulebook; job.status="ready" (stale-guard flips stuck jobs to error)
frontend polls /policy/jobs/{id} → opens the rulebook
```

## FLOW C — Travel retirement (`POST /compliance/retire`)
```
receipts_json (entered lines) + receipt_files[]
  → _assemble_receipts(): entered lines + digital receipts auto-read (fast_fields) + photos flagged for manual amount  (no OCR)
  → _resolve_advance_amount(reference)  (looks up the advance check)
  → receipts.reconcile(advance, receipts, trip_start, trip_end) → Reconciliation (recover/reimburse/settled)
  → save as ComplianceCheckResult (reconciliation embedded) ; flags = per-receipt issues (duplicate/out-of-window/unreadable)
```

## FLOW D — Agent (`docex_agent.process`) — Claude orchestrates, engine = tools
```
process(files, org, rulebook_text, prior_invoice_numbers, client):
  if API key/client → run_agent(...) ; on any failure → _deterministic_fallback()
run_agent:
  _ingest(files): digital→text (fast_extract, free) ; photos/scanned→Claude vision blocks (native, no OCR)
  tools = build_tools(): three_way_match, reconcile_advance, check_duplicate, get_rulebook   (backed by engine)
  Anthropic tool-use loop:
     Claude reads docs+images → emits tool_use → we run the tool → return tool_result → repeat → final report
  _infer_verdict(): a tool-reported mismatch/duplicate forces "blocked" (seatbelt)
  → {report, overall_verdict, tool_calls (audit trail), steps, mode:"agent"|"deterministic_fallback"}
_deterministic_fallback: fast_extract + payment_checks.run_document_checks → verdict (no LLM)
STATUS: standalone module, NOT wired into the app yet.
```

## Pipeline lifecycle (derived in `_derive_lifecycle`)
`needs_attention → requisition → in_approval → approved → paid`
(approvals via HMAC token links / Power Automate; risk register + append-only decision_log per check).

---

## Tech stack
Next.js 14 + TS · FastAPI + Python · Anthropic Claude (sonnet-4-6 judgment, haiku
light; prompt+rulebook caching) · Railway (backend) + Vercel (frontend) ·
file-per-record JSON storage (**ephemeral — wiped on redeploy**).

## Current state
- **Works:** policy→rulebook, payment checks (deterministic+LLM, fast-path), retirement, Excel ingest, audit log, agent runner (offline-tested).
- **Standalone/not wired:** `docex_agent.py`.
- **Blocked:** backend down (Railway trial ended); Vercel prod stuck on old commit (Production Branch ≠ `demo-release`); data ephemeral; no auth.

## Improve next (priority)
1. Hosting + durable storage (S3 + DB) — data wipes on redeploy. #1.
2. Auth + multi-tenancy (shared demo login today).
3. Deploy reliability: Vercel Production Branch=`demo-release`; Railway auto-deploy; CI that imports backend + builds frontend.
4. Wire the agent into the app (endpoint/scheduled), pipeline stays default.
5. `policy_rules` over-extracts (~94 rules/policy) → dedupe/rank + emit deterministic-check specs for thresholds.

## Hard constraints
- **IP:** built during a TA Connect **volunteer** term with a broad IP-assignment clause → ownership unresolved. No deploying/selling to TA Connect without a written carve-out; portfolio work = **synthetic data only**.
- **Data privacy:** executing for clients = data processor (NDPA/GDPR) → DPAs + "decision-support, human decides" framing.
