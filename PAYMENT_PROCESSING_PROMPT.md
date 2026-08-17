# Prompt for GPT — make DOCex payment-voucher/invoice processing faster

Paste everything below into GPT. It contains the real architecture, the actual
code, and the specific question. Ask it to rank concrete latency reductions.

---

You are optimising the latency of the module in "DOCex" that checks payment
vouchers / invoices against an organisation's policy. Diagnose it and propose
the fastest design, ranked by impact vs effort, WITHOUT weakening the hard
constraints. Be concrete and reference the code shown.

## What this part does
An NGO finance/compliance team uploads a payment bundle (voucher + invoice +
purchase order + goods-received note + receipts) and checks it against a saved
rulebook. Output: a per-rule verdict (pass / flag / block / insufficient) with
cited evidence, an overall verdict, and a one-line summary. There is a single
mode and a batch mode (many payments, one rulebook).

## Founding principle (DO NOT break)
DETERMINISTIC-FIRST: code owns every number, match and lookup; the LLM is used
ONLY for genuinely semantic rules. A code-level BLOCK always overrides the LLM.
Every verdict cites its evidence. Batch results export to Excel.

## The pipeline, stage by stage (and where it's code vs LLM)
1. **Extract text** from each upload (PDF/DOCX/XLSX) — `fast_extract.py`.
2. **Field extraction — PURE REGEX, no LLM** (`fast_fields.py`): invoice number,
   PO number, GRN number, totals, TIN, account numbers copied out via labelled
   regex, each with a confidence; only low-confidence fields are meant to fall
   back to the LLM.
3. **Deterministic AP controls — PURE CODE** (`payment_checks.py`): three-way
   match (invoice ↔ PO ↔ GRN amount agreement + PO cross-reference) and
   duplicate-invoice detection. Instant, zero tokens.
4. **Rule partition** (`compliance.py`): rulebook rules split into
   `deterministic` (run in code) and `llm`.
5. **Fast exit**: if code findings already BLOCK, return immediately — no model
   call. If there are no `llm` rules or no documents, also skip the model.
6. **One LLM call** (`compliance.py`): `claude-sonnet-4-6`, `max_tokens=16384`,
   `messages.parse` → structured JSON. System prompt + rulebook are
   prompt-cached (ephemeral, ~5-min TTL). The prompt asks for **one RuleResult
   per (rule × receipt)** for receipt-category rules.
7. **Merge** code + LLM results (code BLOCK wins) and save.
8. **Batch**: run the first payment alone to warm the cache, then fan out the
   rest across a thread pool (max 5 workers), all reusing the cached rulebook.

## Deployment reality
FastAPI on **Render free tier** (sleeps after ~15 min idle → 30–50s cold start;
0.5 CPU / 512 MB; local disk ephemeral). Next.js frontend on Vercel.
Models: `claude-sonnet-4-6` (COMPLIANCE_MODEL), `claude-haiku-4-5` available.

## The actual code

### Field extraction — regex, no LLM (`fast_fields.py`)
```python
# "Fast structured-field extraction — our own code, no LLM."
_TOTAL_LABEL = re.compile(
    r"(?:grand\s+total|total\s+amount|amount\s+due|total)\s*[:\-]?\s*"
    r"(?:₦|NGN|N|\$|USD)?\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", re.I)
_LABELLED = {
    "invoice_number": [r"invoice\s*(?:no|number|#|ref)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"],
    "po_number":      [r"(?:purchase\s*order|\bP\.?O\.?\b|\bLPO\b)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"],
    "grn_number":     [r"(?:\bGRN\b|goods\s*received\s*note)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})"],
    # tin, account_number, vat ...
}
def extract_fields(text: str) -> dict:
    # returns {field: {value, confidence}} + a `needs_llm` list
    ...
```

### Deterministic three-way match — pure code (`payment_checks.py`)
```python
def three_way_match(profiles) -> Optional[RuleResult]:
    inv = ...; po = ...; grn = ...           # classified documents
    if inv is None or po is None: return None
    inv_amt, po_amt = _amount(inv), _amount(po)
    if inv_amt is None or po_amt is None:
        return RuleResult(verdict="insufficient_evidence", ...)
    tol = max(inv_amt, po_amt) * 0.01        # 1% tolerance
    amounts_agree = abs(inv_amt - po_amt) <= tol
    if not amounts_agree:
        return RuleResult(verdict="block", reasoning="Three-way match failed ...")
    ...
def duplicate_invoice(profiles, prior_invoice_numbers) -> Optional[RuleResult]:
    num = _field(inv[0], "invoice_number")
    if num.strip().lower() in priors:
        return RuleResult(verdict="block", reasoning="... possible duplicate payment.")
    ...
```

### The core check — partition, fast exit, single Sonnet call (`compliance.py`)
```python
def check_payment(payment_documents, rulebook, payment_label="Payment Request",
                  form_data=None, ..., document_findings=None):
    class _CheckResponse(anthropic.BaseModel):
        overall_verdict: str
        overall_summary: str
        results: list[RuleResult]

    active_rules = [r for r in rulebook.rules if r.active]
    llm_rules           = [r for r in active_rules if r.evaluation_type == "llm"]
    deterministic_rules = [r for r in active_rules if r.evaluation_type == "deterministic"]

    deterministic_results = evaluate_deterministic_rules(deterministic_rules, form_data or {}, ...) \
                            if deterministic_rules else []
    document_findings = list(document_findings or [])

    # Fast path: a code-level BLOCK skips the model entirely (zero tokens).
    early_code_results = document_findings + deterministic_results
    if early_code_results and _derive_overall_verdict(early_code_results) == "blocked":
        return ComplianceCheckResult(overall_verdict="blocked", results=early_code_results, ...)

    # Nothing for the model to do → skip the API call.
    if not llm_rules or not payment_documents:
        results = document_findings + list(deterministic_results)
        ...
        return ComplianceCheckResult(overall_verdict=_derive_overall_verdict(results), results=results, ...)

    rulebook_block = _rulebook_to_prompt(rulebook.name, llm_rules)
    doc_block      = _build_document_block(payment_documents)
    user_message = f"""PAYMENT REQUEST BUNDLE — {payment_label}:
{doc_block}
Evaluate this payment against every active rule ... For receipts-category rules,
evaluate each receipt separately and return one RuleResult per (rule × receipt).
For all other rules, return one RuleResult per rule. Cite policy and payment text verbatim."""

    response = _get_client().messages.parse(
        model=COMPLIANCE_MODEL,                 # claude-sonnet-4-6
        max_tokens=16384,
        system=[
            {"type": "text", "text": _CHECK_PAYMENT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": rulebook_block,                "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": user_message}],
        output_format=_CheckResponse,
    )
    parsed = response.parsed_output
    code_results = document_findings + deterministic_results
    all_results  = code_results + parsed.results
    verdict = parsed.overall_verdict.lower().strip()
    if verdict not in {"approved","flagged","blocked"}:
        verdict = _derive_overall_verdict(all_results)
    elif code_results and _derive_overall_verdict(code_results) == "blocked":
        verdict = "blocked"                     # a code block always wins
    return ComplianceCheckResult(overall_verdict=verdict, overall_summary=parsed.overall_summary,
                                 results=all_results, ...)
```

### Batch — warmup + parallel fan-out (`compliance.py`)
```python
def check_payment_batch(payments, rulebook):
    def _run(p): return check_payment_safe(p["documents"], rulebook, p.get("label","Payment Request"))
    first = _run(payments[0])                    # warms system+rulebook cache
    parallel_workers = min(5, len(payments) - 1) # _BATCH_MAX_PARALLEL = 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as ex:
        rest = list(ex.map(_run, payments[1:]))
    ...
```

## Observed / suspected latency sources
1. Render free-tier **cold start** (~30–50s on the first request after idle).
2. The single **Sonnet** call generating a lot of output — `max_tokens=16384`
   and **one result per (rule × receipt)** balloons generation time.
3. Sonnet is the slow tier for what is often a simple pass/fail judgement.
4. A one-off check gets **no prompt-cache benefit** (5-min TTL is cold).
5. 0.5 CPU / 512 MB makes parsing + client init slower.

## Hard constraints to preserve
- Deterministic-first; a code-level block always wins; the LLM never asserts a number.
- Every verdict cites policy clause + payment evidence; keep the audit trail.
- Batch results must export to Excel (one row per payment).
- Runs on cheap/free infra now (Azure later).

## Deliverable
Rank concrete latency reductions by impact vs effort. Cover at least:
cold-start mitigation; model tiering (Haiku-first, escalate to Sonnet only on
ambiguity/high-risk) vs Sonnet-only; cutting output tokens (result shape,
collapsing the per-receipt fan-out, capping reasoning, lowering `max_tokens`);
pushing more "llm" rules into deterministic code; prompt-cache warming + TTL;
streaming/partial results for perceived speed; and parallelising rule groups
without exploding into many API calls. For each: expected latency win, the
tradeoff, and rough effort. Then give a concrete step-by-step plan for the
first three changes you'd make.
```
