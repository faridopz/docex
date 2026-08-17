"""
DOCex compliance engine.

Two-pass architecture for policy-based compliance checking:
  Pass 1 — interpret_policy() reads a policy document and returns a
           structured PolicyRulebook with all rules, thresholds, and
           evidence requirements.
  Pass 2 — check_payment() evaluates a payment request bundle against
           the rulebook, rule by rule, returning a ComplianceCheckResult
           with per-rule verdicts and citations from both sides.

The system prompt AND the rulebook are both cached with cache_control so
that batch checks (many payments against one rulebook) only pay full price
for the first check; subsequent checks reuse the cached blocks.

Mirrors the three-tier pattern in screener.py:
  interpret_policy()        — raw policy interpretation
  check_payment()           — raw single check (may raise)
  check_payment_safe()      — error-wrapped single check
  check_payment_batch()     — parallel fan-out with cache warmup
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
import traceback
import uuid
from typing import Literal, Optional

import anthropic
import payment_checks
from ai_config import COMPLIANCE_MODEL
from deterministic_checks import evaluate_deterministic_rules
from models import (
    ComplianceCheckBatchResult,
    ComplianceCheckResult,
    PolicyRule,
    PolicyRulebook,
    RuleResult,
)

logger = logging.getLogger(__name__)

# Same tuning rationale as screener — all I/O-bound waiting on Anthropic,
# so a small thread pool is plenty. Adjust downward if rate limits bite
# on big batches.
_BATCH_MAX_PARALLEL = 5

# Output-token ceiling for the compliance call. Lowered from 16384 after the
# lean-output + collapsed-receipt schema (see _LeanCheckResponse): the model now
# returns ONE object per receipt-rule with a compact receipts[] array instead of
# one verbose object per (rule × receipt), so even a 50-receipt bundle fits well
# under this. Kept as a named constant so it's easy to tune against benchmarks.
_CHECK_MAX_TOKENS = 8192

# Valid verdicts + a verdict → confidence map, used to normalise the compact
# model output back into the public RuleResult schema.
_VALID_VERDICTS = {"pass", "flag", "block", "not_applicable", "insufficient_evidence"}
_VERDICT_CONFIDENCE = {
    "pass": "found",
    "flag": "found",
    "block": "found",
    "not_applicable": "inferred",
    "insufficient_evidence": "not_found",
}


def _norm_verdict(v: str) -> str:
    """Coerce a model-returned verdict string to the valid set; anything
    unrecognised is treated as insufficient_evidence (safe — never a silent
    pass)."""
    v = (v or "").strip().lower()
    return v if v in _VALID_VERDICTS else "insufficient_evidence"


# ─── Lean LLM output schema (server rehydrates the rest) ─────────────────────
# The model returns DECISIONS + compact evidence pointers only. It does NOT
# regenerate rule_description or policy_citation — the server owns those via
# rule_id → rulebook rule. Receipt-category rules return ONE object with a
# receipts[] array (one verdict per receipt) instead of one object per
# (rule × receipt), which removes the output-token explosion. _lean_to_public()
# expands this back into the existing public RuleResult shape, so the API and
# frontend are unchanged.


class _LlmReceiptVerdict(anthropic.BaseModel):
    document_id: str                       # receipt filename
    verdict: str
    evidence_ref: Optional[str] = None     # short verbatim snippet / locator
    short_reason: Optional[str] = None


class _LlmRuleResult(anthropic.BaseModel):
    rule_id: str
    verdict: str
    short_reason: Optional[str] = None
    evidence_ref: Optional[str] = None
    missing: list[str] = []                # for insufficient_evidence


class _LlmReceiptRuleResult(anthropic.BaseModel):
    rule_id: str
    receipts: list[_LlmReceiptVerdict] = []


class _LeanCheckResponse(anthropic.BaseModel):
    overall_verdict: str
    overall_summary: str
    results: list[_LlmRuleResult] = []              # payment-level rules
    receipt_results: list[_LlmReceiptRuleResult] = []  # receipt-level rules


def _lean_to_public(
    parsed: "_LeanCheckResponse",
    rules_by_id: dict[str, PolicyRule],
) -> list[RuleResult]:
    """Expand the compact model output into the public RuleResult list — one
    RuleResult per payment-level rule and one per (receipt-rule × receipt), with
    rule_description + policy_citation rehydrated authoritatively from the
    rulebook (never from the model). This preserves full auditability and the
    existing API shape while the model's own output stays tiny."""

    def rehydrate(rule_id: str) -> tuple[str, Optional[str]]:
        r = rules_by_id.get(rule_id)
        if r is None:
            # The model referenced an id we don't have — keep the id as the
            # description so the row is still traceable, no policy citation.
            return rule_id, None
        return r.description, (r.source_quote or r.clause_reference)

    out: list[RuleResult] = []

    for lr in parsed.results:
        desc, citation = rehydrate(lr.rule_id)
        verdict = _norm_verdict(lr.verdict)
        out.append(RuleResult(
            rule_id=lr.rule_id,
            rule_description=desc,
            verdict=verdict,
            reasoning=lr.short_reason or "",
            policy_citation=citation,
            payment_evidence=lr.evidence_ref,
            missing_evidence=lr.missing,
            applied_to_document=None,
            confidence=_VERDICT_CONFIDENCE.get(verdict, "found"),
        ))

    for rr in parsed.receipt_results:
        desc, citation = rehydrate(rr.rule_id)
        if not rr.receipts:
            # A receipts-category rule with no receipts to evaluate against.
            out.append(RuleResult(
                rule_id=rr.rule_id,
                rule_description=desc,
                verdict="insufficient_evidence",
                reasoning="No receipts in the bundle to evaluate this rule.",
                policy_citation=citation,
                missing_evidence=["original receipts to verify expense"],
                applied_to_document=None,
                confidence="not_found",
            ))
            continue
        for rc in rr.receipts:
            verdict = _norm_verdict(rc.verdict)
            out.append(RuleResult(
                rule_id=rr.rule_id,
                rule_description=desc,
                verdict=verdict,
                reasoning=rc.short_reason or "",
                policy_citation=citation,
                payment_evidence=rc.evidence_ref,
                applied_to_document=rc.document_id,
                confidence=_VERDICT_CONFIDENCE.get(verdict, "found"),
            ))

    return out

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazily construct the Anthropic client (see screener.py rationale)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ─── System prompts ─────────────────────────────────────────────────────────

_INTERPRET_POLICY_SYSTEM_PROMPT = """You are a compliance policy interpreter for NGO financial operations.

Your job is to read a policy document (procurement policy, travel policy,
grant agreement, or similar) and extract its rules into a structured rulebook.
The rulebook will be used downstream to check whether specific payment
requests, expense claims, or other transactions comply with the policy.

Accuracy matters more than coverage. A misread rule will cause every payment
to be evaluated against the wrong standard. When in doubt, mark a clause as
ambiguous in interpretation_notes rather than guessing its meaning.

## What counts as a rule
A rule is any statement in the policy that:
- Sets a threshold or limit ("amounts above X require Y")
- Requires specific evidence ("all receipts must show vendor address")
- Mandates approval at a level ("expenses over X need Director sign-off")
- Forbids something specific ("advance payments to vendors are not permitted")
- Specifies a deadline ("travel advance retirement must occur within 5 days")
- Specifies who is authorized to act ("only the Finance Manager may approve...")

Do NOT extract:
- Aspirational statements ("We strive for transparency")
- Mission statements or vision text
- Definitions sections (unless a definition is part of a rule)
- General principles without a specific testable condition

## For each rule, return:
- id: a kebab-case identifier you generate that summarises the rule
  (e.g. "rule-procurement-3-quote-threshold", "rule-receipt-vendor-address")
- clause_reference: the section number, clause number, or heading from
  the policy (e.g. "Section 4.2", "Clause 6.1.b", "Annex A para 3")
- description: a plain-language summary in 1-2 sentences
- condition: when this rule applies, in plain words
  (e.g. "amount > NGN 500,000", "vendor is new to the org", "always")
- evidence_required: list of what a compliant payment must include to
  prove the rule is met (e.g. ["3 vendor quotes", "comparative analysis"])
- category: ONE of "procurement", "receipts", "approvals", "vendor",
  "advance", "retirement", "documentation", "general"
- source_quote: the verbatim policy text the rule comes from. Copy
  word-for-word, preserving punctuation and casing.
- source_page: page number from === PAGE N === markers, or null
- active: true (the officer can deactivate rules in the UI later)

## Categories — use these strictly
- "procurement"   — sourcing, quotes, vendor selection, tender requirements
- "receipts"      — what a valid receipt must contain, original vs photocopy,
                    receipt-to-invoice reconciliation
- "approvals"     — who must sign off, at what amount thresholds, authority
                    limits
- "vendor"        — vendor due diligence, blacklists, pre-approval lists
- "advance"       — travel/operational advance rules
- "retirement"    — advance retirement timing, refund of unspent funds
- "documentation" — what supporting docs must accompany a payment
- "general"       — anything else policy-specific that doesn't fit above

## interpretation_notes
Use this field for clauses that could not be confidently structured:
- Cross-references to annexes or external documents that were not provided
- Clauses with multiple reasonable interpretations
- Apparent contradictions between sections
- References to donor rules (BMGF, USAID) without specifying them inline

Be terse — one bullet per ambiguity, citing the section.

## Rules — absolute
- Extract ONLY what is written in the policy. No outside knowledge.
  No industry defaults. No "what most policies say."
- If the policy does not specify a threshold, do not invent one. Mark
  it ambiguous in interpretation_notes.
- Use the policy's own vocabulary in descriptions, in plain English (no
  legalese).
- A single rule should test ONE thing. If a clause has multiple tests
  ("needs 3 quotes AND a committee review"), emit two separate rules.
- The source_quote must be verbatim — copy exactly, including punctuation
  and casing.
- IDs must be unique within the rulebook."""


_CHECK_PAYMENT_SYSTEM_PROMPT = """You are a compliance checker for NGO payment requests.

You will be given:
1. A POLICY RULEBOOK (already interpreted) listing the active rules to check.
2. A PAYMENT REQUEST BUNDLE — usually a payment voucher plus supporting docs
   (invoice, receipts, vendor quotes, approval forms, signed contracts).

Your job is to evaluate the payment against EVERY active rule in the rulebook
and produce a verdict for each. A compliance officer reads your output to
decide whether to approve, flag, or block the payment.

## How to process the bundle
First, silently identify what each document in the bundle is — payment
voucher, invoice, individual receipt, quote, approval form, contract,
etc. Then use that understanding when applying rules:

The bundle is a PAYMENT VOUCHER package. Treat the payment voucher as the
cover document that aggregates everything else (Goods Received Note, invoice(s),
purchase order, quotations / competitive bid analysis, approvals). Beyond
checking each rule, RECONCILE the documents against one another and flag any
mismatch:
  - The amount on the voucher should reconcile with the invoice total and the
    Purchase Order amount; flag material discrepancies.
  - The vendor/payee on the voucher should match the invoice and the PO/award.
  - For goods, a Goods Received Note (and, where required, a delivery note)
    should confirm the items and quantities on the invoice were actually
    received before payment.
  - Required approvals/signatures for the threshold should be present on the
    voucher (e.g. reviewing officer, DFOA authorization, ED approval).
A rule whose required supporting document is simply absent from the bundle is
"insufficient_evidence" (list exactly what's missing), not "pass".

## What to return — COMPACT (the server owns the rest)
Do NOT restate rule text or policy text. The server already has the rulebook and
fills in each rule's description and policy citation from `rule_id`. Return only
the DECISION and a compact pointer to the evidence, in two lists:

1. `results` — one entry per PAYMENT-LEVEL rule (categories: procurement,
   approvals, vendor, advance, retirement, documentation, general), evaluated
   against the bundle as a whole. Each entry:
     { "rule_id", "verdict", "short_reason", "evidence_ref" }

2. `receipt_results` — one entry per RECEIPT-LEVEL rule (category: receipts).
   Evaluate the rule against EVERY receipt, but return it ONCE with a receipts
   array — one element per receipt:
     { "rule_id", "receipts": [ { "document_id", "verdict", "evidence_ref", "short_reason" }, ... ] }
   `document_id` is the receipt's exact filename. Every receipt still gets its
   own verdict — you are collapsing the OUTPUT SHAPE, not skipping any receipt.
   If the bundle has no receipts but a receipts-category rule exists, return that
   rule in `receipt_results` with an empty `receipts` list.

`evidence_ref`: a SHORT verbatim snippet or precise locator from the payment that
proves the verdict — e.g. "Voucher total ₦850,000", "receipt r04: ₦12,000 taxi",
"PO-3391 amount 2,900,000". Keep it under ~12 words. NEVER paste whole documents.
`short_reason`: ONE decisive clause (≤ 15 words), leading with the fact that
drives the verdict — not a recap of the rule. Omit it on a clean pass where the
evidence_ref already speaks for itself.

## Verdict values (per rule and per receipt)
- "pass" — satisfies the rule; evidence_ref points at the supporting fact.
- "flag" — borderline/partial compliance; a human must judge.
- "block" — clearly violates the rule; evidence_ref MUST point at the violation.
- "not_applicable" — the rule's condition does not apply to this payment.
- "insufficient_evidence" — the bundle lacks enough info to evaluate; put what's
  missing in `missing` (payment rules) or `short_reason` (receipts), e.g.
  "missing: Director's signature".

## Overall
- overall_verdict: "approved" (all pass/not_applicable), "flagged" (≥1 flag or
  insufficient_evidence, no blocks), "blocked" (≥1 block).
- overall_summary: 1-2 sentences, bottom line first ("Approved.",
  "Flagged for 2 issues.", "Blocked — vendor not pre-approved.").

## Absolute
- Never use outside knowledge. Never invent policy clauses. Never assume
  compliance if the evidence is not in the documents.
- `evidence_ref` must be grounded in the actual document text (a verbatim snippet
  or a precise locator) — it is the audit anchor the server expands.
- Skip inactive rules (they will not appear in the active list you receive)."""


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_document_block(documents: list[tuple[str, str]]) -> str:
    """Format documents into a single readable block for the prompt.

    Identical format to screener._build_document_block so Claude sees a
    consistent structure across both engines.
    """
    parts = []
    for filename, text in documents:
        parts.append(
            f"=== DOCUMENT: {filename} ===\n{text.strip()}\n=== END: {filename} ==="
        )
    return "\n\n".join(parts)


def _derive_overall_verdict(results: list[RuleResult]) -> Literal["approved", "flagged", "blocked"]:
    """Same rollup logic check_payment() uses for the LLM path, reused for
    the deterministic-only path (a pure-form submission with no documents)."""
    verdicts = {r.verdict for r in results}
    if "block" in verdicts:
        return "blocked"
    if "flag" in verdicts or "insufficient_evidence" in verdicts:
        return "flagged"
    return "approved"


def _summarize_results(results: list[RuleResult]) -> str:
    """One-line officer-facing summary for a deterministic-only check."""
    if not results:
        return "No rules were evaluated."
    blocks = [r for r in results if r.verdict == "block"]
    flags = [r for r in results if r.verdict in ("flag", "insufficient_evidence")]
    if blocks:
        return f"Blocked — {blocks[0].reasoning}"
    if flags:
        return f"Flagged for {len(flags)} issue(s) — {flags[0].reasoning}"
    return "Approved — all rules satisfied."


def _rulebook_to_prompt(rulebook_name: str, rules: list[PolicyRule]) -> str:
    """Serialise a set of rules to a readable text block for the prompt.

    Plain labelled text is easier for the model to reason over than JSON
    and lets the system prompt reference fields by name. Callers pass only
    the rules that should reach the model — today that's active rules with
    evaluation_type == "llm"; deterministic rules are evaluated in code
    (see deterministic_checks.py) and never enter the prompt at all.
    """
    lines = [f"RULEBOOK: {rulebook_name}", f"Active rules: {len(rules)}\n"]
    for r in rules:
        lines.append(f"--- Rule: {r.id} ---")
        if r.clause_reference:
            lines.append(f"Clause: {r.clause_reference}")
        lines.append(f"Description: {r.description}")
        if r.condition:
            lines.append(f"Condition: {r.condition}")
        if r.category:
            lines.append(f"Category: {r.category}")
        if r.evidence_required:
            lines.append("Evidence required:")
            for ev in r.evidence_required:
                lines.append(f"  - {ev}")
        if r.source_quote:
            lines.append(f'Source quote: "{r.source_quote}"')
        lines.append("")
    return "\n".join(lines)


# ─── Pass 1: Policy Interpretation ──────────────────────────────────────────

def interpret_policy(
    documents: list[tuple[str, str]],  # (filename, text)
    name: str,
) -> PolicyRulebook:
    """
    Read a policy document and extract its rules into a structured rulebook.

    documents: (filename, extracted_text) tuples for the policy doc(s)
    name:      user-supplied label, e.g. "TA Connect Procurement Policy 2025"

    Returns: PolicyRulebook with rules, citations, and interpretation_notes.
    Raises:  ValueError if no rules were extracted or the model failed to
             produce parsable output.
    """

    class _InterpretationResponse(anthropic.BaseModel):
        rules: list[PolicyRule]
        interpretation_notes: Optional[str] = None

    if not documents:
        raise ValueError("At least one policy document is required.")

    doc_block = _build_document_block(documents)
    filenames = [fn for fn, _ in documents]

    user_message = f"""POLICY DOCUMENTS:
{doc_block}

Extract every rule from these documents into the structured rulebook format.
Read all documents carefully before emitting any rules. Generate a unique
kebab-case id for each rule. Cite source_quote verbatim from the policy.
Note any ambiguous clauses in interpretation_notes."""

    response = _get_client().messages.parse(
        model=COMPLIANCE_MODEL,
        max_tokens=16384,
        system=[
            {
                "type": "text",
                "text": _INTERPRET_POLICY_SYSTEM_PROMPT,
                # The interpretation prompt is hefty and reused across orgs.
                # Caching means re-interpretation of a different policy by
                # the same user still gets a discount on the instructions.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
        output_format=_InterpretationResponse,
    )

    if response.parsed_output is None:
        raise ValueError(
            f"Model could not parse output. Stop reason: {response.stop_reason}. "
            f"Usage: in={getattr(response.usage, 'input_tokens', '?')} "
            f"out={getattr(response.usage, 'output_tokens', '?')}."
        )

    parsed = response.parsed_output
    if not parsed.rules:
        raise ValueError(
            "No rules were extracted from the policy. The document may be "
            "empty, unreadable, or contain only aspirational statements "
            "without testable requirements."
        )

    # De-duplicate any rule IDs the model may have collided on. Belt and
    # braces — the system prompt asks for unique IDs, but if the model
    # slips we'd rather have unique IDs with a suffix than silent collisions
    # that break the downstream "apply rule X to payment" mapping.
    seen_ids: set[str] = set()
    for rule in parsed.rules:
        if rule.id in seen_ids:
            rule.id = f"{rule.id}-{uuid.uuid4().hex[:4]}"
        seen_ids.add(rule.id)

    return PolicyRulebook(
        id=f"rb-{uuid.uuid4().hex[:8]}",
        name=name,
        source_documents=filenames,
        rules=parsed.rules,
        interpretation_notes=parsed.interpretation_notes,
        # Seed a sensible default approval chain so a freshly-interpreted
        # rulebook isn't left with an empty approval section. The org edits
        # these stages to match their own process (the workflow editor in the
        # rulebook screen) — nothing here is TA-Connect-specific.
        approval_workflow=["Compliance Check", "Review", "Approval"],
    )


# ─── Pass 2: Payment Check ──────────────────────────────────────────────────

def check_payment(
    payment_documents: list[tuple[str, str]],  # (filename, text)
    rulebook: PolicyRulebook,
    payment_label: str = "Payment Request",
    form_data: Optional[dict[str, str]] = None,
    prior_open_submissions: Optional[list[dict]] = None,
    referenced_submission: Optional[dict] = None,
    document_findings: Optional[list[RuleResult]] = None,
    metrics: Optional[dict] = None,
) -> ComplianceCheckResult:
    """
    Evaluate a payment request bundle against a PolicyRulebook.

    metrics: optional dict the caller passes in to receive LLM instrumentation
    (llm_calls, llm_ms, input_tokens, output_tokens, model, cache_* ) for
    benchmarking. Inert by default (None) — production behaviour is unchanged.

    The system prompt AND the rulebook are both cached, so batch checks
    (many payments against the same rulebook) only pay full price for the
    first check; the rest reuse both cached blocks.

    form_data / prior_open_submissions / referenced_submission: structured
    intake for "form" and "hybrid" PaymentTypes (see
    models.PaymentType.intake_mode). Rules on the rulebook with
    evaluation_type == "deterministic" are evaluated in code against
    form_data (see deterministic_checks.py) — zero LLM cost — and merged
    into the same results list as the LLM-evaluated rules.
    prior_open_submissions feeds "no_outstanding_advance" rules;
    referenced_submission feeds "reference_lookup" rules (e.g. a Travel
    Retirement validating the advance it's closing out). A rulebook whose
    active rules are ALL deterministic, or a check with no documents, skips
    the Claude call entirely: this is what makes a pure-form or hybrid
    submission with only field-level rules cost nothing.

    Raises:
        ValueError if the rulebook has no active rules, or the model failed
        to produce parsable output.
    """

    # Default metrics for the paths that skip the model, so a benchmark caller
    # always gets a consistent shape back.
    if metrics is not None:
        metrics.setdefault("llm_calls", 0)
        metrics.setdefault("model", None)

    active_rules = [r for r in rulebook.rules if r.active]
    if not active_rules:
        raise ValueError(
            f"Rulebook '{rulebook.name}' has no active rules to check against. "
            "Activate at least one rule before running a check."
        )

    # Partition: deterministic rules never reach the model at all — they're
    # evaluated in code below and folded into the same results list.
    llm_rules = [r for r in active_rules if r.evaluation_type == "llm"]
    deterministic_rules = [r for r in active_rules if r.evaluation_type == "deterministic"]

    deterministic_results: list[RuleResult] = (
        evaluate_deterministic_rules(
            deterministic_rules, form_data or {},
            prior_open_submissions=prior_open_submissions,
            referenced_submission=referenced_submission,
        )
        if deterministic_rules
        else []
    )

    # Deterministic AP controls (three-way match, duplicate detection) computed
    # by the caller from the documents themselves — no rule/form needed. They
    # merge into the results exactly like form-field deterministic rules, and a
    # block from them wins the verdict the same way.
    document_findings = list(document_findings or [])

    filenames = [fn for fn, _ in payment_documents]

    # Fast path: if the instant deterministic controls (AP three-way match /
    # duplicate detection, or a hard deterministic rule) already BLOCK the
    # payment, the LLM can't salvage the verdict — a code-level block always
    # wins. Skip the expensive model call entirely and return now. This is the
    # biggest speed win on exactly the payments you most want caught fast (the
    # bad ones), and it costs zero tokens.
    early_code_results = document_findings + deterministic_results
    if early_code_results and _derive_overall_verdict(early_code_results) == "blocked":
        return ComplianceCheckResult(
            payment_id=f"pay-{uuid.uuid4().hex[:8]}",
            payment_label=payment_label,
            documents=filenames,
            rulebook_id=rulebook.id,
            rulebook_name=rulebook.name,
            overall_verdict="blocked",
            overall_summary=_summarize_results(early_code_results),
            results=early_code_results,
        )

    # Nothing for Claude to do — either every active rule is deterministic
    # (a pure-form payment type), or there's no LLM-evaluable evidence
    # (no documents) to hand it. Skip the API call entirely.
    if not llm_rules or not payment_documents:
        results = document_findings + list(deterministic_results)
        if llm_rules and not payment_documents:
            # There ARE llm rules but nothing to evaluate them against — make
            # that explicit per rule rather than silently dropping them.
            results.extend(
                RuleResult(
                    rule_id=r.id,
                    rule_description=r.description,
                    verdict="insufficient_evidence",
                    reasoning="No documents were provided to evaluate this rule.",
                    missing_evidence=["supporting document(s)"],
                    confidence="not_found",
                )
                for r in llm_rules
            )
        return ComplianceCheckResult(
            payment_id=f"pay-{uuid.uuid4().hex[:8]}",
            payment_label=payment_label,
            documents=filenames,
            rulebook_id=rulebook.id,
            rulebook_name=rulebook.name,
            overall_verdict=_derive_overall_verdict(results),
            overall_summary=_summarize_results(results),
            results=results,
        )

    rulebook_block = _rulebook_to_prompt(rulebook.name, llm_rules)
    doc_block = _build_document_block(payment_documents)

    user_message = f"""PAYMENT REQUEST BUNDLE — {payment_label}:
{doc_block}

Evaluate this payment against every active rule in the rulebook (provided in the
system message). Return the COMPACT structure described there: payment-level
rules in `results`, receipt-level rules in `receipt_results` (one object per
rule with a `receipts` array, `document_id` = the receipt's filename). Return
decisions + short evidence pointers only — do NOT restate rule or policy text."""

    _t0 = time.perf_counter()
    response = _get_client().messages.parse(
        model=COMPLIANCE_MODEL,
        max_tokens=_CHECK_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": _CHECK_PAYMENT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": rulebook_block,
                # The rulebook is fixed for a batch run. Caching this block
                # is the single biggest cost lever for batch mode — every
                # subsequent check pays $0 for the rulebook tokens.
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_message}],
        output_format=_LeanCheckResponse,
    )
    _llm_ms = (time.perf_counter() - _t0) * 1000.0

    if metrics is not None:
        usage = getattr(response, "usage", None)
        metrics["llm_calls"] = 1
        metrics["llm_ms"] = round(_llm_ms, 1)
        metrics["model"] = COMPLIANCE_MODEL
        metrics["input_tokens"] = getattr(usage, "input_tokens", None)
        metrics["output_tokens"] = getattr(usage, "output_tokens", None)
        metrics["cache_read_tokens"] = getattr(usage, "cache_read_input_tokens", None)
        metrics["cache_creation_tokens"] = getattr(usage, "cache_creation_input_tokens", None)

    if response.parsed_output is None:
        raise ValueError(
            f"Model could not parse output. Stop reason: {response.stop_reason}. "
            f"Usage: in={getattr(response.usage, 'input_tokens', '?')} "
            f"out={getattr(response.usage, 'output_tokens', '?')}."
        )

    parsed = response.parsed_output

    # Expand the compact model output into the public RuleResult shape,
    # rehydrating rule_description + policy_citation authoritatively from the
    # rulebook (keyed by rule_id) — never from the model.
    rules_by_id = {r.id: r for r in active_rules}
    llm_results = _lean_to_public(parsed, rules_by_id)

    # Normalise overall_verdict to the expected literal set. If the model
    # returned something weird, derive the verdict from the rule outcomes —
    # now including the deterministic results, since both count toward the
    # final verdict.
    code_results = document_findings + deterministic_results
    all_results = code_results + llm_results
    verdict = parsed.overall_verdict.lower().strip()
    if verdict not in {"approved", "flagged", "blocked"}:
        verdict = _derive_overall_verdict(all_results)
    elif code_results and _derive_overall_verdict(code_results) == "blocked":
        # The model only ever saw llm_rules, so it can't know a deterministic
        # rule or AP control blocked the payment. A code-level block always wins.
        verdict = "blocked"

    return ComplianceCheckResult(
        payment_id=f"pay-{uuid.uuid4().hex[:8]}",
        payment_label=payment_label,
        documents=filenames,
        rulebook_id=rulebook.id,
        rulebook_name=rulebook.name,
        overall_verdict=verdict,  # type: ignore[arg-type]
        overall_summary=parsed.overall_summary,
        results=all_results,
    )


def check_payment_safe(
    payment_documents: list[tuple[str, str]],
    rulebook: PolicyRulebook,
    payment_label: str = "Payment Request",
    form_data: Optional[dict[str, str]] = None,
    prior_open_submissions: Optional[list[dict]] = None,
    referenced_submission: Optional[dict] = None,
    document_findings: Optional[list[RuleResult]] = None,
    metrics: Optional[dict] = None,
) -> ComplianceCheckResult:
    """
    Error-wrapped single check. A failure on one payment never breaks a batch.

    Mirrors extract_applicant in screener.py — log loudly to the uvicorn
    terminal AND bubble the error into the response so the UI can show it.
    """
    filenames = [fn for fn, _ in payment_documents]
    try:
        return check_payment(
            payment_documents, rulebook, payment_label,
            form_data=form_data, prior_open_submissions=prior_open_submissions,
            referenced_submission=referenced_submission,
            document_findings=document_findings,
            metrics=metrics,
        )
    except Exception as exc:
        logger.error(
            "Compliance check failed for '%s' (rulebook=%s): %s\n%s",
            payment_label,
            rulebook.name,
            exc,
            traceback.format_exc(),
        )
        print(
            f"\n[DOCex] Compliance check failed for '{payment_label}': "
            f"{type(exc).__name__}: {exc}\n",
            flush=True,
        )
        return ComplianceCheckResult(
            payment_id=f"pay-{uuid.uuid4().hex[:8]}",
            payment_label=payment_label,
            documents=filenames,
            rulebook_id=rulebook.id,
            rulebook_name=rulebook.name,
            # Safe default: surface the error as a flag, not an approval.
            # Officer should see something went wrong, not assume green light.
            overall_verdict="flagged",
            overall_summary=f"Check failed: {type(exc).__name__}",
            results=[],
            error=f"{type(exc).__name__}: {exc}",
        )


# ─── Batch ──────────────────────────────────────────────────────────────────

def check_payment_batch(
    payments: list[dict],  # each: {"label": str, "documents": [(filename, text)]}
    rulebook: PolicyRulebook,
    prior_invoice_numbers: Optional[list[str]] = None,
) -> ComplianceCheckBatchResult:
    """
    Check many payment requests against one rulebook.

    Strategy: HYBRID warmup + parallel fan-out (same as extract_batch).
      - First payment runs alone and writes the system-prompt + rulebook
        cache on the Anthropic side. Both blocks have cache_control:
        ephemeral set in check_payment.
      - Remaining payments run concurrently in a small thread pool. They
        all benefit from the cached system + rulebook, so each call only
        pays for its own payment-bundle tokens AND completes much faster.

    Deterministic AP controls (three-way match + duplicate detection) run in
    the SAME engine as the single-payment endpoint: a sequential pre-pass
    computes each payment's document_findings and detects duplicate invoice
    numbers WITHIN the batch (in input order) as well as against any
    `prior_invoice_numbers` from history. Because those findings are passed into
    check_payment, a deterministic BLOCK still short-circuits the LLM per payment
    — the batch gets the same fast-exit and the same code-block-wins guarantee.

    Output order matches input order. The batch never raises — individual
    failures show up as error fields on the affected ComplianceCheckResult.
    """
    if not payments:
        return ComplianceCheckBatchResult(
            total=0, approved=0, flagged=0, blocked=0, checks=[]
        )

    # ── Deterministic AP pre-pass (sequential, fast, code-only) ──────────────
    # Runs three-way match + duplicate detection over each payment's documents,
    # accumulating invoice numbers so an invoice repeated later in the SAME
    # batch is caught deterministically (never by the LLM). Fail-safe: any error
    # yields empty findings so the LLM check still runs.
    seen_invoices: list[str] = list(prior_invoice_numbers or [])
    findings_by_index: list[list[RuleResult]] = []
    for p in payments:
        docs = p.get("documents", [])
        try:
            findings = payment_checks.run_document_checks(
                docs, prior_invoice_numbers=seen_invoices
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[DOCex] AP controls failed for '{p.get('label')}': {exc}", flush=True)
            findings = []
        findings_by_index.append(findings)
        try:
            inv = payment_checks.primary_invoice_number(docs)
            if inv:
                seen_invoices.append(inv)
        except Exception:
            pass

    def _run(item: tuple[int, dict]) -> ComplianceCheckResult:
        idx, p = item
        return check_payment_safe(
            payment_documents=p["documents"],
            rulebook=rulebook,
            payment_label=p.get("label", "Payment Request"),
            document_findings=findings_by_index[idx],
        )

    indexed = list(enumerate(payments))
    n = len(payments)
    if n == 1:
        checks = [_run(indexed[0])]
    else:
        parallel_workers = min(_BATCH_MAX_PARALLEL, n - 1)
        print(
            f"[DOCex] Compliance batch: {n} payments "
            f"(1 cache warmup, then {n - 1} parallel across {parallel_workers} workers)",
            flush=True,
        )
        started = time.monotonic()
        first = _run(indexed[0])
        print(
            f"[DOCex] Warmup done in {time.monotonic() - started:.1f}s. "
            f"Fanning out the remaining {n - 1}...",
            flush=True,
        )
        fanout_started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as ex:
            rest = list(ex.map(_run, indexed[1:]))
        print(
            f"[DOCex] Compliance batch complete: {n} payments in "
            f"{time.monotonic() - started:.1f}s "
            f"(fan-out alone: {time.monotonic() - fanout_started:.1f}s).",
            flush=True,
        )
        checks = [first] + rest

    approved = sum(1 for c in checks if c.overall_verdict == "approved" and not c.error)
    flagged = sum(1 for c in checks if c.overall_verdict == "flagged" and not c.error)
    blocked = sum(1 for c in checks if c.overall_verdict == "blocked" and not c.error)

    return ComplianceCheckBatchResult(
        total=len(checks),
        approved=approved,
        flagged=flagged,
        blocked=blocked,
        checks=checks,
    )
