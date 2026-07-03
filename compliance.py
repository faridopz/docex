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

- Payment-level rules (categories: procurement, approvals, vendor, advance,
  retirement, documentation, general) are evaluated against the bundle
  as a whole. Return one RuleResult per such rule with
  applied_to_document = null.

- Receipt-level rules (category: receipts) are evaluated against EACH
  individual receipt in the bundle. Return one RuleResult per
  (rule × receipt) pair, with applied_to_document set to the exact
  filename of that receipt.

If the bundle has no receipts and a receipts-category rule exists, return
one RuleResult per such rule with verdict "insufficient_evidence",
applied_to_document = null, and missing_evidence listing what is missing
(e.g. ["original receipts to verify expense"]).

## Verdict per rule
- "pass" — the payment satisfies the rule. payment_evidence quotes the
  supporting text from the payment bundle verbatim. policy_citation
  quotes the rule's source from the policy.
- "flag" — borderline or partial compliance. A human needs to judge.
  Use this when something is technically met but suspicious (e.g. all 3
  quotes are from companies with the same address, or a receipt is
  legible but missing a non-critical field).
- "block" — the payment clearly violates the rule. Specific evidence of
  the violation MUST be quoted in payment_evidence.
- "not_applicable" — the rule's condition does not apply to this payment
  (e.g. a > NGN 500k rule when the payment is NGN 50k). Set reasoning
  to a short explanation; payment_evidence and policy_citation may be
  null.
- "insufficient_evidence" — the payment bundle does not contain enough
  information to evaluate this rule. Populate missing_evidence with a
  specific list of what is missing (e.g. ["original invoice",
  "Director's signature on approval form"]).

## Overall verdict
- "approved" — every active rule resolved to pass or not_applicable.
- "flagged"  — at least one flag or insufficient_evidence, but no blocks.
- "blocked"  — at least one block.

## Writing the per-rule `reasoning` — be concise and decision-oriented
Each rule's `reasoning` is ONE short, decisive sentence (aim for ≤ 20 words).
Lead with the decision and the specific fact that drives it — not a recap of
the rule. The officer should read it and know the next action instantly.
  GOOD (block): "No third quotation attached — only 2 of the required 3."
  GOOD (pass):  "PO #3391, invoice and GRN all reconcile at ₦2.9m."
  BAD:          "This rule requires that for procurements in this threshold
                 band, at least three quotations be obtained, and upon review
                 of the documents provided it appears that..."
Do not restate the rule text; the rule is shown next to your reasoning.

## Overall summary
1-2 sentences for a busy officer. Lead with the bottom line ("Approved.",
"Flagged for 2 issues.", "Blocked — vendor not pre-approved."), then the
most material reason if not approved.

## Rules — absolute
- Cite verbatim. policy_citation must be word-for-word from the rule's
  source_quote in the rulebook. payment_evidence must be word-for-word
  from a document in the bundle.
- For receipts-category rules with multiple receipts, return one
  RuleResult per (rule × receipt) pair. applied_to_document must match
  the receipt's exact filename.
- If a rule is marked inactive in the rulebook (it will not appear in
  the list of active rules you receive), skip it entirely.
- Never use outside knowledge. Never invent policy clauses. Never assume
  a payment is compliant if the evidence is not in the documents.
- Confidence per rule: "found" if the rule was met or violated
  explicitly with a direct quote; "inferred" if the verdict required
  reasoning from context; "not_found" if relevant info isn't in the
  bundle (paired with verdict "insufficient_evidence").
- rule_description must be copied from the rule in the rulebook so the
  output is self-contained for downstream display."""


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
) -> ComplianceCheckResult:
    """
    Evaluate a payment request bundle against a PolicyRulebook.

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

    # Inner response class. overall_verdict is intentionally typed as str
    # (not the strict Literal) so a model slip on casing or phrasing doesn't
    # crash the parse — we normalise below.
    class _CheckResponse(anthropic.BaseModel):
        overall_verdict: str
        overall_summary: str
        results: list[RuleResult]

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

    filenames = [fn for fn, _ in payment_documents]

    # Nothing for Claude to do — either every active rule is deterministic
    # (a pure-form payment type), or there's no LLM-evaluable evidence
    # (no documents) to hand it. Skip the API call entirely.
    if not llm_rules or not payment_documents:
        results = list(deterministic_results)
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

Evaluate this payment against every active rule in the rulebook (provided
in the system message). For receipts-category rules, evaluate each receipt
in the bundle separately and return one RuleResult per (rule × receipt).
For all other rules, return one RuleResult per rule. Cite policy and
payment text verbatim."""

    response = _get_client().messages.parse(
        model=COMPLIANCE_MODEL,
        max_tokens=16384,
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
        output_format=_CheckResponse,
    )

    if response.parsed_output is None:
        raise ValueError(
            f"Model could not parse output. Stop reason: {response.stop_reason}. "
            f"Usage: in={getattr(response.usage, 'input_tokens', '?')} "
            f"out={getattr(response.usage, 'output_tokens', '?')}."
        )

    parsed = response.parsed_output

    # Normalise overall_verdict to the expected literal set. If the model
    # returned something weird, derive the verdict from the rule outcomes —
    # now including the deterministic results, since both count toward the
    # final verdict.
    all_results = deterministic_results + parsed.results
    verdict = parsed.overall_verdict.lower().strip()
    if verdict not in {"approved", "flagged", "blocked"}:
        verdict = _derive_overall_verdict(all_results)
    elif deterministic_results and _derive_overall_verdict(deterministic_results) == "blocked":
        # The model only ever saw llm_rules, so it can't know a deterministic
        # rule blocked the payment. A deterministic block always wins.
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

    Output order matches input order. The batch never raises — individual
    failures show up as error fields on the affected ComplianceCheckResult.
    """
    if not payments:
        return ComplianceCheckBatchResult(
            total=0, approved=0, flagged=0, blocked=0, checks=[]
        )

    def _run(p: dict) -> ComplianceCheckResult:
        return check_payment_safe(
            payment_documents=p["documents"],
            rulebook=rulebook,
            payment_label=p.get("label", "Payment Request"),
        )

    n = len(payments)
    if n == 1:
        checks = [_run(payments[0])]
    else:
        parallel_workers = min(_BATCH_MAX_PARALLEL, n - 1)
        print(
            f"[DOCex] Compliance batch: {n} payments "
            f"(1 cache warmup, then {n - 1} parallel across {parallel_workers} workers)",
            flush=True,
        )
        started = time.monotonic()
        first = _run(payments[0])
        print(
            f"[DOCex] Warmup done in {time.monotonic() - started:.1f}s. "
            f"Fanning out the remaining {n - 1}...",
            flush=True,
        )
        fanout_started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as ex:
            rest = list(ex.map(_run, payments[1:]))
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
