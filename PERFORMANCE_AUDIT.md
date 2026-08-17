# DOCex Performance Audit — Payment-Voucher / Invoice Checking

Evidence-based, read-only. No files were modified. Line references are to the
repo as inspected. The next step is to implement the highest-impact changes one
at a time and benchmark each.

---

## 1. Executive diagnosis — the 3 biggest bottlenecks

1. **Render free-tier cold start (~30–50s) dominates the first request.**
   `render.yaml` pins `plan: free`, which sleeps after ~15 min idle. On wake,
   the container also imports heavy C-extension parsers (`pymupdf`/`fitz`,
   `pdfplumber`, `python-pptx`, `python-docx`, `anthropic`) at module import in
   `api/main.py`. A single uvicorn process (`api/Dockerfile` CMD, no workers) on
   0.5 CPU / 512 MB makes that import + boot slow. This is latency the check
   pays *before any work starts*.

2. **LLM output size — the `rule × receipt` fan-out plus a verbose schema.**
   The system prompt instructs *"Return one RuleResult per (rule × receipt)
   pair"* for receipt-category rules (`compliance.py` `_CHECK_PAYMENT_SYSTEM_PROMPT`),
   and each `RuleResult` (`models.py:448`) makes the model regenerate
   `rule_description` (the full rule text it already has), plus `policy_citation`
   AND `payment_evidence` quotes, per object. Output tokens — the slow part of
   inference — scale with rules × receipts. At realistic sizes this both slows
   the call and can **exceed `max_tokens=16384` → truncated JSON → parse failure**
   (`check_payment` raises `ValueError` when `parsed_output is None`,
   `compliance.py:563`).

3. **Sonnet-only for every semantic rule.** `COMPLIANCE_MODEL = MODEL_TIER_1 =
   claude-sonnet-4-6` (`ai_config.py:24,30`) handles *all* `llm` rules in one
   call. Sonnet is the slow tier for what is frequently a simple present/absent
   or pass/fail judgement; there is no Haiku-first path and no escalation logic.

Cold start hits the *first* request of a session hardest; #2 and #3 dominate
every *warm* request thereafter.

---

## 2. Current request path (upload → result)

`POST /compliance/check/single` (`api/compliance_routes.py:1079`):

1. **Read files** — `_read_files()` (`api/compliance_routes.py:108`) reads bytes
   sequentially, then parses **in parallel** via `fast_extract.extract_many_detailed`
   (thread pool, `_MAX_WORKERS=8`; fitz-first, pdfplumber fallback; flags scans).
2. **Load rulebook** — `_load_rulebook(rulebook_id)` from disk JSON.
3. **Deterministic AP controls (0 tokens)** — `_run_ap_controls(docs)` →
   `payment_checks.run_document_checks`: `three_way_match` (`payment_checks.py:85`)
   + `duplicate_invoice` (`payment_checks.py:169`). Fields come from
   `fast_fields.extract_fields` — **pure regex, no LLM** (`fast_fields.py`).
4. **Check** — `check_payment_safe` → `check_payment` (`compliance.py:408`):
   - Partition active rules into `llm` vs `deterministic` (`:459-460`).
   - Evaluate deterministic rules in code (`evaluate_deterministic_rules`).
   - **Fast exit**: if code findings already `blocked`, return now — no model
     call (`:486-497`).
   - **Skip model** if no `llm` rules or no documents (`:502-527`).
   - Else **one** `messages.parse` call: `claude-sonnet-4-6`, `max_tokens=16384`,
     system = [system prompt (cached), rulebook block (cached)], user = document
     bundle (`:541-561`).
   - Merge code + LLM results; a code-level block overrides the model
     (`:576-584`).
5. **Apply requisition form fields**, auto-save to `/checks/{id}.json`
   (ephemeral disk), return.
6. **Frontend** (`web/lib/api.ts:415`) `await`s the single POST and renders
   `res.json()` — **no streaming, no polling**; the user waits on the whole call.

**Batch** (`compliance.py:651`): run payment #1 alone to warm the system+rulebook
cache, then fan out the rest across a thread pool (`min(_BATCH_MAX_PARALLEL=5,
n-1)` workers), each reusing the cached prefix.

---

## 3. Bottleneck table

| Bottleneck | Evidence in code | Estimated impact | Confidence | Effort |
|---|---|---:|---|---|
| Render free cold start | `render.yaml` `plan: free`; heavy imports in `api/main.py:24-27`; single uvicorn `api/Dockerfile:39` | +30–50s on first/idle request | High | Low |
| `rule × receipt` output explosion | `_CHECK_PAYMENT_SYSTEM_PROMPT` "one RuleResult per (rule × receipt)"; `applied_to_document` field | +seconds→minutes; truncation cliff | High | Medium |
| Verbose `RuleResult` schema (echoes `rule_description`, dual quotes) | `models.py:448-464` | 25–40% of output tokens redundant | High | Low–Med |
| Sonnet-only, no tiering | `ai_config.py:24,30`; single `messages.parse` `compliance.py:541` | 2–4× on the LLM leg for simple rules | Medium | Medium |
| One-off checks miss prompt cache | ephemeral (5-min) `cache_control` `compliance.py:548,556` | Full input re-bill + slower TTFT on isolated checks | Medium | Low |
| No streaming / staged progress | `web/lib/api.ts:415` awaits whole POST | Perceived latency only | High | Med |
| Cold parser imports at startup | `api/main.py:24-27`, `fast_extract.py` | Adds to cold start; ~0 when warm | Medium | Low |

Note: Anthropic clients are **not** a bottleneck — they're lazy singletons and
reused (`compliance.py:49-56` `_get_client`; `api/main.py:441` `_get_followup_client`),
so there's no per-request client init.

---

## 4. LLM output analysis (where it balloons)

Fields the model generates per object (`RuleResult`, `models.py:448`): `rule_id`,
`rule_description` (full rule text — **already known**, pure duplication),
`verdict`, `reasoning` (1–3 sentences), `policy_citation` (quote),
`payment_evidence` (quote), `missing_evidence[]`, `applied_to_document`,
`confidence`.

Rough cost per object ≈ **~200 output tokens** (JSON keys/structure ~35;
`rule_description` ~40; `reasoning` ~55; two quotes ~60; small fields ~10).

Objects generated = `payment_level_rules + (receipt_rules × receipts)`.

| Scenario | Assume receipt-cat rules | Objects | ~Output tokens | Vs 16,384 cap |
|---|---|---:|---:|---|
| 10 rules / 5 receipts | 3 | 7 + 3×5 = 22 | ~4,400 | OK |
| 10 rules / 5 (worst: all receipt-cat) | 10 | 50 | ~10,000 | OK-ish |
| 20 rules / 10 receipts | 6 | 14 + 6×10 = 74 | ~14,800 | **near cap** |
| 20 rules / 10 (worst) | 20 | 200 | ~40,000 | **truncates** |
| 30 rules / 20 receipts | 9 | 21 + 9×20 = 201 | ~40,200 | **truncates** |
| 30 rules / 20 (worst) | 30 | 600 | ~120,000 | **catastrophic** |

Two conclusions: (a) at ~50–80 output tok/s for Sonnet, ~14,800 tokens ≈ **3–5
minutes** of generation — the dominant warm-path cost; (b) beyond ~mid-size
bundles the fan-out **exceeds `max_tokens` and the response can't be parsed** —
a correctness/reliability cliff, not just slowness. `max_tokens=16384` isn't
itself a cost (it's a ceiling), but it's masking this cliff instead of the
output being made compact.

Roughly **25–40% of tokens are safely removable** by dropping the echoed
`rule_description` (rehydrate server-side from `rule_id`) and collapsing the two
quote fields — with **no loss of auditability**, because the rule text and
policy live in the rulebook already and evidence can be a reference.

---

## 5. Model strategy — A vs B

**A. Sonnet-only (today).** Highest single-rule accuracy; simplest; one call.
But every trivial "is the GRN present?" pays Sonnet latency, and there's no
cheaper lane for the majority of rules that are simple.

**B. Haiku-first + Sonnet escalation (recommended, conservative).** Run `llm`
rules on Haiku 4.5; escalate the specific rules that are risky or uncertain to
Sonnet. Because **a false PASS is worse than an escalation**, escalate on *any*
of: verdict `block`/`flag`; `confidence` `inferred`/`not_found`;
`insufficient_evidence`; missing required fields; or `rule.category` in a
high-risk set. Likely **Haiku-safe**: documentation-presence, simple
`documentation`/`general` category checks, "is X attached". **Keep on Sonnet**:
collusion/anomaly judgement ("3 quotes share an address"), exception-clause
interpretation, fraud indicators, and anything that resolves to `block`.

Tradeoff for DOCex: B adds orchestration complexity and, when escalation fires,
a second call — but the deterministic-first guard rail means the *dangerous*
outcomes (blocks) are either already caught in code or escalated to Sonnet, so
the accuracy risk is contained while most rules get the fast lane. Net: large
latency win on typical payments, bounded risk. Do **not** go Haiku-only.

---

## 6. Deterministic candidates (currently `llm` → could be code)

The system prompt already asks the model to *reconcile* documents — much of that
is arithmetic/lookup that belongs in code (and partly already is, via
`three_way_match`). Candidates:

| Rule (as phrased in policy) | Why LLM today | Data needed | Deterministic approach | Latency win | Effort | Risk |
|---|---|---|---|---|---|---|
| Voucher total = invoice = PO | Prompt reconciliation | `fast_fields` totals on voucher/invoice/PO | Extend `three_way_match` to include the voucher amount | Med | Low | Low |
| Payee/vendor consistent across voucher/invoice/PO | Prompt reconciliation | vendor field extraction + `rapidfuzz` (already a dep) | Normalised fuzzy match in `payment_checks.py` | Med | Med | Low–Med |
| Receipt totals reconcile to advance/voucher | Per-receipt LLM | receipt amounts (`fast_fields`) | Sum in code — `receipts.py` already reconciles advances | High | Med | Low |
| Duplicate invoice | already deterministic | — | `duplicate_invoice` (done) | — | — | — |
| Threshold rules (> ₦X needs Y) | already `deterministic` type | form/amount | `deterministic_checks.py` (done) | — | — | — |
| Required signature/approval **present** for threshold | Prompt | needs signature/section detection | Partially code-able (presence of labelled section), but *validity* of a signature stays semantic | Low–Med | High | Med |

Guidance: move the arithmetic/lookup ones (amount reconciliation incl. voucher,
vendor consistency, receipt totals). **Do not** move genuine judgement
("does this justification satisfy the exception clause", signature *authenticity*,
collusion) into code.

---

## 7. Recommended target architecture (deterministic-first intact)

```text
Upload
  → parallel text extraction (fast_extract, unchanged)
  → regex field extraction (fast_fields, unchanged)
  → DETERMINISTIC CORE (payment_checks + deterministic_checks)
       three-way match (+voucher amount) · duplicates · thresholds
       · vendor consistency · receipt-total reconciliation
  → hard BLOCK?  ── yes ──▶ return (0 tokens)   [unchanged fast exit]
       │ no
  → rule router
       ├─ deterministic rules → code
       └─ semantic rules → Haiku 4.5 (compact schema, receipts collapsed)
                             │
                        uncertain / high-risk / block? ── yes ──▶ Sonnet 4.6
  → deterministic MERGE (code BLOCK always wins)   [unchanged guarantee]
  → audit record + Excel export                    [unchanged]
Frontend: stream staged progress (extract ✓ · AP checks ✓ · AI review …)
```

Unchanged guarantees: code owns numbers/matching/lookups; a code BLOCK overrides
any LLM output; every result stays traceable (rule_id → rehydrated rule text +
evidence reference); batch Excel export untouched.

---

## 8. Ranked optimisation plan

**P0 — do immediately**
- Instrument first (Section 10). You can't rank real wins without stage timings + token counts.
- Keep-warm ping to eliminate the cold start (workaround; measure the real gain). *Very high impact on first request, low effort.*
- Slim the LLM output: drop echoed `rule_description`, single evidence reference, collapse `rule × receipt` into one object per rule with a `receipts[]` array. *Very high, medium; also removes the truncation cliff.*

**P1 — next**
- Haiku-first + Sonnet escalation. *High, medium.*
- Move arithmetic/lookup rules into the deterministic core (voucher amount, vendor consistency, receipt totals). *High, medium.*
- Streaming / staged progress on the frontend. *Perceived-high, medium.*

**P2 — later**
- Lower `max_tokens` once output is compact (kills the truncation risk explicitly). *Low.*
- Prompt-cache: evaluate 1-hour TTL for bursty finance sessions + warm the cache when a rulebook is opened. *Low.*
- Revisit batch worker count with real memory numbers on 512 MB. *Low.*

Cost impact: slimmer output + Haiku both **reduce** token spend; keep-warm has a
tiny always-on cost; none increase risk if the deterministic guard rails stay.

---

## 9. First three changes (concrete)

### Change 1 — Compact LLM output schema + collapse the receipt fan-out
- **Files:** `compliance.py` (the inner `_CheckResponse`/`RuleResult` used for
  `output_format`, the `_CHECK_PAYMENT_SYSTEM_PROMPT`, and the merge step
  `:570-595`). No change to the stored `models.RuleResult`.
- **What changes:** introduce a lean LLM-only model — `rule_id`, `verdict`,
  `evidence_ref` (filename + short locator), `short_reason` (≤1 sentence), and
  for receipt rules a single object per rule with `receipts: [{file, verdict,
  ref}]` instead of one object per (rule × receipt). Server rehydrates
  `rule_description`/`policy_citation` from the rulebook by `rule_id` when
  building the stored `RuleResult`.
- **Why:** removes 25–40% redundant tokens and the multiplicative fan-out — the
  dominant warm-path cost — and eliminates the `>16,384` truncation failure.
- **Expected improvement:** warm LLM leg ~40–70% faster on receipt-heavy
  bundles; parse failures on large bundles eliminated.
- **Regression risks:** the UI groups by `applied_to_document`; must map the new
  `receipts[]` back to per-document rows. Rehydration must handle a `rule_id`
  the model invented (fall back gracefully).
- **Tests:** golden-output test asserting per-rule + per-receipt verdicts match
  today's semantics on a fixture bundle; a large-bundle test (30 rules / 20
  receipts) that previously truncated now parses; verify a code BLOCK still
  overrides.

### Change 2 — Keep-warm to remove cold start
- **Files:** ops (an external cron/uptime pinger hitting `GET /health` every
  ~10 min); confirm `/health` is trivial (no Anthropic/parse/import work).
- **What changes:** the free instance stops sleeping; the check no longer pays
  30–50s on the first request.
- **Why:** biggest single latency number for intermittent users.
- **Expected improvement:** −30–50s on first/idle requests; ~0 on warm.
- **Regression risks:** none functional; note it's a workaround, not a
  production posture (Azure/always-on later). Don't put real work in `/health`.
- **Tests:** assert `/health` does no LLM/IO; measure cold vs warm with the
  Section 10 harness.

### Change 3 — Haiku-first with conservative Sonnet escalation
- **Files:** `ai_config.py` (add a light tier alias for compliance),
  `compliance.py` (`check_payment`: run `llm` rules on Haiku, collect
  uncertain/high-risk/block results, re-run just those on Sonnet, merge).
- **What changes:** two-tier evaluation; escalate on `block`/`flag`,
  `insufficient_evidence`, low confidence, missing fields, or high-risk
  category. A false PASS never survives — it either fails a deterministic check
  or gets escalated.
- **Why:** most rules are simple; Haiku is the fast lane while Sonnet still
  judges the dangerous ones.
- **Expected improvement:** typical-payment LLM leg 2–4× faster; token cost down.
- **Regression risks:** escalation predicate must be conservative; measure
  Haiku→Sonnet escalation rate and any verdict disagreements against a Sonnet-only
  baseline before trusting it.
- **Tests:** for a labelled fixture set, assert Haiku-first + escalation never
  produces a PASS where Sonnet-only produced flag/block; record escalation rate.

Sequence: **instrument → Change 1 → Change 2 → Change 3**, benchmarking each.

---

## 10. Smallest useful benchmark to build first

There is **no perf harness today** — only `time.monotonic()` prints in
`check_payment_batch` (`compliance.py:691-704`) and per-request ms in the
`_RequestIDMiddleware` log. Build a minimal harness before any change:

- **Shape:** a script `bench/bench_check.py` that runs a handful of fixture
  bundles (small / receipt-heavy / large) through `check_payment_safe` and
  records, per run, a JSON row.
- **Metrics (start with what's cheap and local):**
  - total request latency; extraction latency; field-extraction latency;
    deterministic-check latency; LLM total latency.
  - `response.usage.input_tokens` / `output_tokens` (already on the SDK
    response); number of LLM calls; cache read/creation tokens if exposed.
  - cold vs warm (first call after boot vs subsequent).
  - later, when tiering lands: Haiku escalation rate; TTFT if you switch to
    streaming.
- **How:** wrap each stage in `time.perf_counter()`; return the timings on the
  result object behind a `DOCEX_BENCH=1` flag (so prod is unaffected), or log a
  structured line. Aggregate p50/p90 across N runs per fixture.
- **Why first:** it turns every subsequent change into a measured before/after,
  and it will confirm or correct the estimates in Sections 3–4 against real
  token counts on your actual rulebooks.

Do this, then implement Change 1 and measure.
