# DOCex — Payment-Check Performance Roadmap

Latency plan for the compliance payment-check path. Companion to `CLAUDE.md`
and `DEVOPS_ROADMAP.md`. The deterministic-first principle is the foundation and
is **not** traded away for speed — the wins come from making Claude do less,
making code do more, and stopping the infra from sleeping.

---

## 1. Current check architecture (as built)

Endpoint: `POST /compliance/check/single` (see `api/compliance_routes.py`,
`compliance.py`).

1. **Read + extract** — uploaded bundle (voucher, invoice, PO, GRN, receipts)
   parsed to text in parallel (`fast_extract`: PyMuPDF/pdfplumber, python-docx,
   openpyxl; scanned pages flagged).
2. **Deterministic controls first (0 tokens)** — three-way match
   (invoice ↔ PO ↔ GRN) and duplicate-invoice detection run in code.
3. **Rule split** — rulebook rules partitioned into `deterministic` (run in code)
   and `llm`.
4. **Fast exits** — any code-level BLOCK returns immediately, no model call. No
   LLM rules or no documents also skips the model.
5. **One Claude call** — `messages.parse` on **claude-sonnet-4-6** (`COMPLIANCE_MODEL`
   = `MODEL_TIER_1`), `max_tokens=16384`, structured JSON out. System prompt +
   rulebook are prompt-cached (ephemeral, ~5 min TTL). Returns one result per
   rule, and one per (rule × receipt) for receipt-category rules, each citing
   policy + payment text.
6. **Merge + save** — code + LLM results merge (code BLOCK always wins); saved to
   `/checks/{id}.json` (ephemeral disk).

Batch mode (`check_payment_batch`): warm cache once, then fan out up to 5 in
parallel on the same rulebook.

Deployment: FastAPI on **Render free tier** (0.5 CPU, 512MB, sleeps after 15 min
idle → 30–50s cold start, ephemeral disk); Next.js on Vercel.

---

## 2. Where the latency actually is

Not Python/FastAPI. It's the combination of:

1. Render Free **cold starts** (biggest cause of the 30–50s first request).
2. Sending **too much work to Sonnet**.
3. Generating **far more output than the UI needs** (`max_tokens=16384`).
4. Making the LLM evaluate rules that could be **resolved deterministically**.
5. Treating one LLM call as one **large monolithic judgment**.

---

## 3. Target architecture

`Upload → parallel extraction → deterministic engine → rule router → tiny LLM
calls only where genuinely necessary → deterministic merge → audit record`

```text
                    PAYMENT BUNDLE
                         │
              ┌──────────▼──────────┐
              │ Parallel extraction │  PDF/DOCX/XLSX/OCR
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ Normalise documents │  invoice/PO/GRN/receipts
              └──────────┬──────────┘
              ┌──────────▼──────────┐
              │ DETERMINISTIC CORE  │  3-way match · duplicates · amounts
              │                     │  thresholds · dates · receipt totals
              │                     │  required fields
              └──────────┬──────────┘
                    Any BLOCK?
                    /        \
                  YES         NO
                   │           │
               RETURN     Rule router
                             │
                   ┌─────────┴─────────┐
             deterministic        semantic rules
                   │                   │
                   │              Haiku 4.5
                   │                   │
                   │              confident?
                   │              /      \
                   │            YES       NO
                   │             │      Sonnet 4.6
                   └─────────────┴────────┘
                                  │
                         deterministic merge
                                  │
                         audit + Excel/JSON
```

---

## 4. Priority ranking

| # | Change | Impact | Effort | Call |
|---|--------|--------|--------|------|
| 🥇 | Fix Render cold starts | Very high | Low–Med | Do immediately |
| 🥈 | Shrink LLM output dramatically | Very high | Low | Do immediately |
| 🥉 | Move more rules into deterministic engine | Very high | Med–High | Core architectural work |
| 4 | Haiku → Sonnet escalation | High | Med | Best long-term LLM strategy |
| 5 | Remove per-receipt LLM fan-out | High | Med | Do |
| 6 | Parallelise independent LLM groups | High | Med | Do after output redesign |
| 7 | Cache warming / longer TTL | Med–High | Low | Do |
| 8 | Streaming | Low actual / high perceived | Low–Med | Add for UX |
| 9 | More aggressive prompt optimisation | Med | Low | Fine-tune after above |

---

## 5. Fix Render cold starts first

The user pays the wake cost *before the check begins*. Keep the container warm
with a trivial external uptime ping every few minutes:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

No Anthropic, parsing, DB, OCR, or expensive imports inside it. Expected gain:
**30–50s on the first request. Very low effort.**

Caveat: this is a workaround, not production architecture. For the paid/Azure
version, use an always-available service, not a free tier that sleeps.

---

## 6. Shrink the LLM output (biggest in-call win)

`max_tokens=16384` is far too generous — the model is deciding PASS/FAIL/BLOCK
per rule, not writing essays. Target a compact contract:

```json
{
  "results": [
    { "rule_id": "PROC-07", "verdict": "PASS",
      "policy_citation": "4.2.1", "evidence": "Invoice INV-1042: ₦850,000" }
  ]
}
```

Do **not** ask for: chain-of-thought, long explanations, summaries, restated
policy/documents, recommendations, repeated evidence. Decision + traceable
evidence only.

**Never let the LLM return numbers.** If invoice = PO = GRN = ₦850,000, code
already knows that; the LLM says `PASS` and cites the source. Arithmetic stays in
the deterministic layer — this preserves the hard constraint.

Compact evidence IDs, not repeated text:

```json
"evidence": ["invoice:INV-1042"]
```

Let the audit DB resolve the ID to immutable source text.

---

## 7. Move deterministic rules out of the LLM

Compile policy statements into executable controls. Example — "payments over
₦500,000 require Finance Director approval":

```python
if payment.amount > 500_000 and not payment.has_approval("Finance Director"):
    BLOCK   # zero tokens
```

**Move into code:** arithmetic, totals, VAT/tax, thresholds, dates, approval
limits/hierarchy, duplicate invoice IDs, vendor+invoice combos, three-way match,
PO/GRN match, receipt totals, budget limits, required fields, document presence,
payment-method rules, vendor/bank matching, quotation counts/thresholds, currency
checks, tolerances, invoice date ranges, PO validity, GRN quantities,
quantity × unit price, invoice reconciliation.

**Keep for the LLM:** genuinely semantic judgment — e.g. "does this justification
satisfy the exception clause in section 7.4?"

---

## 8. Model strategy — Haiku-first, Sonnet as exception

Not Sonnet-only. Not Haiku-only.

```text
Tier 0  code            deterministic
Tier 1  Haiku 4.5       simple semantic interpretation
Tier 2  Sonnet 4.6      ambiguous / high-risk / complex
```

Risk-aware escalation using both verdict and rule metadata:

```python
if rule.risk == "critical":            use_sonnet = True
elif result.verdict in ("BLOCK","REVIEW") or result.confidence < 0.90:
                                        escalate = True
else:                                   use_haiku = True
```

Confidence is never authority — the LLM is an evidence interpreter, not the
compliance engine. Final merge stays: `code BLOCK wins → else LLM result`.

---

## 9. Kill the (rule × receipt) fan-out

15 rules × 10 receipts = 150 evaluations of repetitive output. Instead:

1. **Pre-process receipts in code** — extraction emits structured receipts
   (`{id, vendor, date, amount, currency, text}`), so code already computes
   `sum(receipts)`. Fewer input tokens, output tokens, and reasoning.
2. Pass receipts as a **structured collection**; ask once per rule, returning
   only the receipt IDs that matter:

```json
{ "rule_id": "RECEIPT_001", "verdict": "PASS", "evidence": ["R1","R2","R3"] }
```

---

## 10. Parallelise carefully — don't create 20 Sonnet calls

Splitting one call into 20 can be *worse* (round trips, scheduling, cost, merge
complexity, rate limits). Order: **shrink the single call first, then benchmark
whether splitting helps.** Only split rule groups that genuinely need different
context (procurement / receipts / justification).

---

## 11. Prompt caching

- Keep the cache prefix **stable**: `[CACHED] system + rulebook + schema/tool
  defs` then `[UNCACHED] payment id + document text + evidence`. Never put
  timestamps/UUIDs/request metadata inside the cached section.
- **Warm the cache deliberately** at startup / on rulebook change — don't wait
  for the first payment, and don't warm blindly every 5 min (wasted spend).
- Evaluate the optional **1-hour TTL** vs the default 5-min against real traffic
  (a finance user may batch, leave, and return). Measure, don't assume.

---

## 12. Instrument before optimising

Return/log a timing breakdown per request and compute p50/p90/p95/p99 across
warm / cold / no-LLM / Haiku / Sonnet / batch:

```json
{ "timing": { "upload_ms":421, "extraction_ms":803, "deterministic_ms":31,
  "llm_ttfb_ms":941, "llm_generation_ms":4120, "merge_ms":18, "total_ms":6334 }}
```

Then you optimise the real bottleneck (Render vs Anthropic vs parsing) instead of
guessing.

---

## 13. Streaming (perceived speed)

Backend completion time barely changes, but the UX does. Stream per-stage
progress to the UI; only commit the **validated** structured result to the audit
record (never stream half-formed JSON into the DB):

```text
✓ Documents extracted   ✓ Duplicate check   ✓ Three-way match
✓ Threshold checks      AI review… ✓ Procurement  ◌ Exception clause
```

---

## 14. Rough latency targets (validate with telemetry)

| Architecture | Warm-request target |
|---|---|
| Current Sonnet + huge output | 8–20s+ |
| + compact output | 4–10s |
| + less context | 3–8s |
| + Haiku-first | 1.5–5s |
| + more deterministic rules | sub-second – ~3s (many payments) |
| Hard deterministic BLOCK | ~sub-second |

Cold start: current 30–50s → warm Render ~0s startup → always-on infra removes
the class entirely.

---

## Execution order

- **Phase 1 (fastest wins):** keep Render warm · add timing instrumentation ·
  drop `max_tokens` (measure real max — likely hundreds not thousands) · remove
  reasoning/explanatory output · collapse receipt results · compact evidence IDs.
- **Phase 2 (model):** deterministic → Haiku → escalate to Sonnet only on
  ambiguous/high-risk. Sonnet becomes the exception, not the default.
- **Phase 3 (policy engineering):** compile the rulebook into an executable
  representation; push more rules into code so the LLM is the semantic layer
  *around* the deterministic engine, not the engine.
- **Phase 4 (UX):** streaming/progress.

Keep structured JSON outputs (Sonnet 4.6 + Haiku 4.5 both support schema-valid
output) — but keep the schema tiny. The biggest wins come from making Claude do
less, making code do more, and making the infra stop sleeping.
