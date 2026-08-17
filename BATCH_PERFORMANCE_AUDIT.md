# DOCex — Deep Performance, Latency & Batch Architecture Audit (First Response)

Read-only reconnaissance. No code changed. This is the "required first response"
(Part 32). It extends `PERFORMANCE_AUDIT.md` (single-payment deep-dive) into
batch, storage, failure/retry, Excel, cost and multi-org. Line references are to
the repo as inspected; the repo is the source of truth.

> Honesty note on benchmarks: I have **not** produced live timing numbers — there
> are no payment fixtures in the repo and no runnable Anthropic key in this
> environment, so every latency figure below is a reasoned estimate derived from
> the actual code/schema, clearly labelled. Section 15 makes "build the harness +
> baseline" the first change precisely so the next round is measured, not
> estimated.

---

## 1. Current architecture

- **Backend:** FastAPI (`api/main.py`), one uvicorn process (`api/Dockerfile:39`,
  no `--workers`), routers included per feature. Anthropic clients are **lazy
  singletons**, reused (`compliance.py:49-56`; `api/main.py:441`).
- **Compliance engine:** `compliance.py` (LLM + orchestration), `payment_checks.py`
  (deterministic AP controls), `deterministic_checks.py` (form-rule engine),
  `fast_extract.py` (text extraction, fitz→pdfplumber), `fast_fields.py` (regex
  field extraction, no LLM), `receipts.py` (advance reconciliation),
  `doc_completeness.py` (doc presence/classification).
- **Model:** `COMPLIANCE_MODEL = MODEL_TIER_1 = claude-sonnet-4-6`
  (`ai_config.py:24,30`); `claude-haiku-4-5` available (`MODEL_TIER_2`).
- **Persistence:** file-based JSON — `checks/`, `rulebooks/`, `rate_cards/`,
  and the new `transactions/ notifications/ users/ vouchers/`. **Ephemeral disk**
  on Render free (wiped on redeploy). No database.
- **Excel:** generated **client-side** via SheetJS (`web/lib/api.ts:154,706`).
- **Auth/multi-org:** real per-user auth now exists (`auth.py`), but compliance
  **checks/rulebooks are not scoped by `org_id`** — `OrgProfile` is a singleton
  and comments explicitly defer tenant scoping (`models.py:403-404`).
- **Deploy:** Render free (`render.yaml`, `plan: free`, sleeps ~15 min →
  30–50s cold start, 0.5 CPU / 512 MB); Next.js on Vercel.
- **Instrumentation:** none beyond `time.monotonic()` prints in
  `check_payment_batch` (`compliance.py:691-704`) and per-request ms in
  `_RequestIDMiddleware`.

---

## 2. Actual single-payment execution path

`POST /compliance/check/single` (`api/compliance_routes.py:1079`):

```
upload
  → _read_files()            # bytes read seq, PARSE IN PARALLEL (extract_many_detailed, ≤8 threads)
  → _load_rulebook()         # disk JSON
  → _run_ap_controls(docs)   # DETERMINISTIC: three-way match + duplicate (fast_fields regex) — 0 tokens
  → check_payment_safe → check_payment():
        partition rules (llm vs deterministic)
        evaluate deterministic rules in code
        FAST EXIT if code findings == blocked  (no LLM)
        else ONE messages.parse (sonnet, max_tokens=16384, system+rulebook cached)
        merge (code BLOCK always wins)
  → apply requisition form fields
  → _save_check() → /checks/{id}.json   (ephemeral)
  → return ComplianceCheckResult
frontend: awaits the whole POST, renders JSON (no streaming)
```

Deterministic-first is correctly wired **here**: AP controls run, block short-
circuits the model, code block overrides.

---

## 3. Actual batch execution path

`POST /compliance/check/batch` (`api/compliance_routes.py:1680`):

```
upload ALL files + payments JSON [{label, filenames[]}]   # grouping is CLIENT-SUPPLIED
  → _load_rulebook()
  → for each uploaded file: _extract_text(upload)          # ⚠ SEQUENTIAL loop, not parallel
  → build payment_jobs by plucking filenames per label      # missing filename → 422 aborts WHOLE batch
  → check_payment_batch(payment_jobs, rulebook):
        _run(p) = check_payment_safe(documents, rulebook, label)   # ⚠ NO document_findings passed
        first runs alone (cache warmup); rest via ThreadPoolExecutor(max_workers=min(5, n-1))
  → for each check: _save_check(); send_check_notification()
  → return ComplianceCheckBatchResult   # ⚠ SYNCHRONOUS: one POST, awaits the WHOLE batch
```

**Three material findings in batch mode:**
1. **Extraction is sequential** in the batch endpoint (a plain `for upload`
   loop calling `_extract_text`), whereas single-check extraction is parallel
   (`extract_many_detailed`). On a 50-receipt bundle this alone is a large,
   avoidable serial cost.
2. **Deterministic AP controls are SKIPPED in batch.** `check_payment_batch`'s
   `_run` calls `check_payment_safe` **without `document_findings`**, so
   three-way match and duplicate-invoice detection — which the single endpoint
   runs via `_run_ap_controls` — **do not run in batch at all**. This is both a
   speed miss (more falls to the LLM) and, more importantly, a **compliance
   gap**: the deterministic controls that must catch bad payments fast are
   absent in exactly the high-volume path.
3. **No cross-payment duplicate detection.** Even where `duplicate_invoice`
   runs, it only compares against `prior_invoice_numbers` supplied by the
   caller; nothing checks INV-001 appearing twice **within the same batch**
   (Part 21's "major organisational feature" is currently absent).

Plus: batch is **synchronous** (no `batch_id`, no progressive results — time to
first result = whole-batch time), and a single missing filename **422s the
entire batch** rather than isolating that one payment.

---

## 4. Top latency bottlenecks

1. **Render free cold start (~30–50s)** on first/idle request (`render.yaml`).
2. **LLM output size** — `rule × receipt` fan-out + verbose `RuleResult`
   (echoes `rule_description`, dual quotes); can exceed `max_tokens=16384` →
   truncation → parse `ValueError` (`compliance.py:563`).
3. **Sonnet-only** for all semantic rules (`ai_config.py:30`).
4. **Batch: sequential extraction** (`check/batch` loop) — serial on big bundles.
5. **Batch: no deterministic fast-exit** (AP controls skipped) → everything pays
   the LLM even when a three-way-match block would have been free.
6. **Synchronous batch** — user waits for the last payment before seeing any.

---

## 5. Latency contribution by stage (estimated, to be measured)

For one payment (1 voucher/invoice/PO/GRN + N receipts), warm instance:

| Stage | Est. warm latency | Basis |
|---|---|---|
| File read + text extract (native PDF) | 50–400 ms | fitz, parallel in single path |
| OCR (scanned) | **0 today** | no OCR wired — scans return empty text, flagged (`fast_extract.py`) |
| Regex field extraction | <20 ms | pure stdlib (`fast_fields.py`) |
| Deterministic AP + rules | <30 ms | arithmetic/lookup (`payment_checks.py`) |
| **LLM call (the dominant term)** | **2–5 s (small) → 3–5 min (large)** | output-token bound; §6–7 |
| Merge + persist (JSON) | <20 ms | local file write |
| **Cold start (first request only)** | **+30–50 s** | Render free sleep |

So on a warm instance the **LLM leg is ~90%+ of wall-clock**; on a cold instance
the **cold start dwarfs everything**. Everything deterministic is already ms-scale.

Note: OCR is a *latent* risk, not a current cost — there is **no OCR stage**
today; scanned pages yield empty text and are surfaced as a flag. Part 6's
"don't blindly OCR 50 receipts" is a design guard for when OCR is added, not a
present bottleneck.

---

## 6. LLM token / output problem

`RuleResult` fields the model generates (`models.py:448`): `rule_id`,
`rule_description` (**duplicate** of known rule text), `verdict`, `reasoning`
(1–3 sentences), `policy_citation` (quote), `payment_evidence` (quote),
`missing_evidence[]`, `applied_to_document`, `confidence`. ~**200 output tokens
per object**, of which ~25–40% (`rule_description` + one of the two quotes) is
recoverable server-side and need not be generated. The fix (per
`PERFORMANCE_AUDIT.md` §9) is a lean LLM schema returning `rule_id`, `verdict`,
`evidence_ref`, `short_reason`, and DOCex rehydrating the rest from the rulebook.

---

## 7. Receipt-scaling problem

The prompt asks for **one RuleResult per (rule × receipt)** for receipt-category
rules. Objects = `payment_rules + receipt_rules × receipts`. Derived from the
schema (~200 tok/object):

| Payment | Receipts | Assume receipt-rules | Objects | ~Output tokens | vs 16,384 |
|---|---|---|---|---:|---|
| A | 3 | 3 | 7 + 3×3 = 16 | ~3,200 | OK |
| B | 10 | 4 | 14 + 4×10 = 54 | ~10,800 | OK-ish |
| C | 20 | 6 | 21 + 6×20 = 141 | ~28,200 | **truncates** |
| D | 50 | 6 | 21 + 6×50 = 321 | ~64,200 | **catastrophic** |

The 50-receipt organisational case (Test D) **cannot complete** under the current
schema — it exceeds the token ceiling and the parse raises. Collapsing to one
object per rule with a compact `receipts:[{file,verdict,ref}]` array turns 321
objects back into ~7 and removes the cliff, while preserving per-receipt
auditability (the array still records each receipt's verdict + evidence ref).

---

## 8. Current concurrency model

- **Single check extraction:** parallel (`extract_many_detailed`, ≤8 threads).
- **Batch extraction:** **sequential** (endpoint loop) — a real gap.
- **Batch checks:** `ThreadPoolExecutor(max_workers=min(5, n-1))` after a 1-payment
  cache warmup (`compliance.py:685-700`). I/O-bound (Anthropic calls release the
  GIL), so 5 is reasonable; but on 512 MB, 5 concurrent large bundles hold a lot
  of doc text in memory simultaneously — memory, not CPU, is the limit to watch.
- **No** per-rule-group LLM splitting (correct — that would lose the cache and
  multiply round-trips).

---

## 9. Current storage model

File-based JSON on the container's **ephemeral** local disk (`_CHECK_DIR =
checks/`, `api/compliance_routes.py:159`, saved at `:303`). Wiped on every
redeploy (`render.yaml` notes; `CLAUDE.md` "DATA IS EPHEMERAL"). No database, no
object storage, no `org_id` scoping on checks/rulebooks. Fine for a demo;
**not** durable or multi-tenant for organisational use. Minimum production path:
durable object storage (S3/Azure Blob) for documents + a small DB (Postgres) for
check/batch records keyed by `org_id` — introduced only when moving off the demo.

---

## 10. Current failure / retry model

- **Isolation:** good at the check level — `check_payment_safe`
  (`compliance.py:598`) wraps each check in try/except, logs, and returns a
  result with an `error` field and a **safe "flagged"** verdict (never a false
  approve). Batch never raises as a whole.
- **Gaps:** (a) a missing filename in the `payments` map **422s the entire
  batch** (`api/compliance_routes.py`), breaking isolation at the input stage;
  (b) **no retries** on transient Anthropic/network errors — a blip fails that
  payment outright; (c) **no idempotency** — re-POSTing a batch (browser refresh)
  re-runs and re-persists everything with new `payment_id`s; (d) no document-hash
  or invoice-number idempotency key.

---

## 11. Current Excel export

**Client-side** via SheetJS (`web/lib/api.ts:154,701-711`): the browser builds
the workbook from the returned JSON. There is a server-side xlsx path only for
Bank Verify batches, **not** for compliance checks/batches. Implication: the
Excel export depends on the full JSON reaching the browser — which is exactly
what the receipt-scaling problem (§7) can truncate/inflate. Slimming the payload
(§6–7) also de-risks the export. A server-side export becomes worthwhile once
batches are large or run as background jobs (browser may not be open).

---

## 12. Top 10 improvements — ranked

| # | Improvement | Latency impact | Cost impact | Effort | Compliance risk |
|---|---|---|---|---|---|
| 1 | Benchmark harness + baseline (measure first) | enables all | none | Low | none |
| 2 | Slim LLM schema + collapse `rule×receipt` | **Very high** (warm) | ↓ tokens | Med | Low (rehydrate from rulebook) |
| 3 | Keep-warm ping (kill cold start) | **Very high** (first req) | ~0 | Low | none |
| 4 | **Wire AP controls into batch** (pass `document_findings`) | High + correctness | ↓ (fast-exit) | Low | **fixes a gap** |
| 5 | Parallelise batch extraction | High (big bundles) | none | Low | none |
| 6 | Haiku-first + Sonnet escalation | High | ↓↓ tokens | Med | Med (needs eval) |
| 7 | Async batch + `batch_id` + progressive results (poll/SSE) | perceived (not actual) | none | Med | none |
| 8 | In-batch + historical duplicate detection (code) | Med + correctness | ↓ | Med | Low |
| 9 | Retries (transient only) + idempotency key | reliability | ~0 | Med | Low |
| 10 | Durable storage + `org_id` scoping | reliability/tenancy | infra | High | Med (isolation) |

Deterministic-first, code-block-precedence, auditability and Excel are preserved
in every item above.

---

## 13. Expected effect (estimates, pre-benchmark)

Assumes: cold start removed by keep-warm; LLM output slimmed; AP controls +
parallel extraction in batch; Haiku-first later. "Before" = current warm path.

| Volume | Before (warm) | After #2–#5 | After +Haiku (#6) | Notes |
|---|---|---|---|---|
| 1 payment (Test A) | ~3–6 s | ~2–4 s | ~1–2.5 s | LLM-bound; slimmer output is the win |
| 1 payment, 20 receipts (C) | fails/truncates or 30 s+ | ~4–8 s | ~2–5 s | fan-out collapse removes the cliff |
| 10 payments | ~30–60 s | ~12–25 s | ~8–15 s | parallel extract + fast-exit + cache |
| 50 payments | minutes; some fail (D) | ~1–2 min, first result in seconds (async) | faster + cheaper | AP fast-exit skips LLM on clean blocks |
| 100 payments | often unreliable | steady with isolation + retries | + cost ↓ | needs #7/#9 for UX + reliability |

Cost per payment drops mainly from #2 (fewer output tokens) and #6 (Haiku for
simple rules); exact figures need measured token counts (Section 15) before any
pricing claim — I won't invent numbers.

---

## 14. Recommended architecture (deterministic-first intact)

```
Upload ─▶ durable object store (later) ─▶ document IDs
   │
   ├─ PARALLEL extraction (native text; OCR only pages that need it, cached)
   ├─ regex field extraction (fast_fields)
   ├─ DETERMINISTIC CORE (payment_checks + deterministic_checks)   ← also in BATCH
   │     three-way match · duplicates (in-batch + historical) · thresholds
   │     · receipt-total reconciliation · vendor/amount consistency
   ├─ hard BLOCK? ──yes──▶ return (0 tokens)         [fast exit, batch too]
   │  no
   ├─ semantic rules ─▶ Haiku 4.5 (lean schema, receipts collapsed)
   │                      └─ uncertain/high-risk/block ─▶ Sonnet 4.6
   └─ deterministic MERGE (code BLOCK wins) ─▶ audit record ─▶ Excel

Single payment  = this pipeline once.
Batch (async)   = POST → batch_id → same pipeline per payment across a bounded
                  pool, isolated failures, retries on transient errors,
                  progressive results via polling/SSE, one Excel at the end.
```

Same engine for one payment and 500 — the batch layer wraps the (now faster)
single-payment pipeline; it never forks into a second compliance path.

---

## 15. Exact first three changes to implement

### Change 1 — Benchmark harness + baseline (measure before optimising)
- **Files (new):** `bench/bench_check.py`, small fixtures under `bench/fixtures/`
  (or state clearly that real sample bundles are needed).
- **What:** run representative bundles (Tests A–D, F, G) through
  `check_payment_safe`, timing each stage with `time.perf_counter()` and
  capturing `response.usage.input_tokens/output_tokens`, number of LLM calls,
  and cold-vs-warm; emit JSON rows + p50/p90. Gated behind `DOCEX_BENCH=1` so
  production is unaffected.
- **Why:** turns every later change into a measured before/after; validates the
  §5–7 estimates against real token counts.
- **Risk/tests:** none to prod (read-only harness); assert it runs without
  touching `checks/`.

### Change 2 — Slim LLM output + collapse the receipt fan-out
- **Files:** `compliance.py` (the inner `output_format` model, the
  `_CHECK_PAYMENT_SYSTEM_PROMPT`, and the merge `:570-595`). Stored
  `models.RuleResult` unchanged.
- **What:** lean LLM schema (`rule_id`, `verdict`, `evidence_ref`,
  `short_reason`, and for receipt rules a single object with
  `receipts:[{file,verdict,ref}]`); rehydrate `rule_description`/
  `policy_citation` server-side from the rulebook by `rule_id`.
- **Why:** removes 25–40% redundant tokens + the multiplicative fan-out (the
  dominant warm cost) and eliminates the >16k truncation failure (Test C/D).
- **Risk/tests:** UI groups by `applied_to_document` — map `receipts[]` back to
  per-document rows; golden test that verdicts match today on a fixture; a
  30-rule/20-receipt test that previously truncated now parses; assert a code
  BLOCK still overrides.

### Change 3 — Wire deterministic AP controls into batch + parallelise batch extraction
- **Files:** `api/compliance_routes.py` (`check_batch_endpoint`) and/or
  `compliance.py` (`check_payment_batch` `_run`).
- **What:** (a) extract batch files via `extract_many_detailed` (parallel) like
  the single path; (b) compute `_run_ap_controls` per payment and pass
  `document_findings` into `check_payment_safe` so three-way match + duplicate
  detection (and the fast-exit) run in batch too; (c) isolate a missing-filename
  payment as a `processing_error` result instead of 422-ing the whole batch.
- **Why:** closes a real compliance gap (AP controls currently absent in batch),
  adds the free deterministic fast-exit at scale, and removes serial extraction.
- **Risk/tests:** batch test asserting a duplicate/mismatch is BLOCKED in batch
  exactly as in single; a batch with one missing-file payment still processes the
  rest; extraction order preserved.

Sequence for the whole programme: **Change 1 → 2 → 3**, then Haiku tiering,
async/progressive batch, retries/idempotency, durable storage + `org_id` — each
benchmarked and compliance-verified against baseline before the next.

---

*Constraints honoured throughout: code owns numbers/matching/lookups; a code
BLOCK always wins; the LLM returns decisions + references, never authoritative
financial facts; every verdict stays auditable; batch stays isolated and Excel
export keeps working.*
