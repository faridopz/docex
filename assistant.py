"""
DOCex Assistant.

The agentic narrator. Every result page calls this primitive to get a
plain-English briefing on what just happened plus 0-5 ranked suggested
next actions. Turns DOCex from "a tool with results" into "an AI doing
the work" — which is the whole product thesis.

Why centralised: each result type (bank_verify_batch, attendance_run,
compliance_check, diagnostic) has its own context shape and the right
tone shifts subtly. Keeping the prompt logic here means we tune all of
them in one place. The /assistant/summarize endpoint is the only consumer.

The Assistant runs through Claude Sonnet 4.6, with `response_format` JSON
structured output so the UI can render actions as buttons reliably (no
"please return JSON" fragility).

Cost note: each briefing is one short Claude call (~500-800 input tokens,
~300 output tokens). At Sonnet 4.6 pricing that's ~$0.002 per briefing.
For Farid's expected pilot volume (~50 result-page-views/day across 3
pilots) that's $0.30/day, $9/month, negligible.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from ai_config import ASSISTANT_MODEL
from models import AssistantBrief, SuggestedAction

logger = logging.getLogger(__name__)

# Reusing the singleton-style client pattern from compliance.py / screener.py.
# The Anthropic SDK pulls ANTHROPIC_API_KEY from env automatically.
# Explicit 120s timeout per call. The SDK default is generous (~10 min on
# some versions), which means a hung request ties up an API worker until
# the load balancer kills the connection. 120s is comfortable for the
# longest legitimate briefings (full diagnostic report ≈ 4-8K input tokens,
# resolves in under 30s in practice) while preventing pathological hangs.
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Lazily construct the Anthropic client (see screener.py rationale)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=120.0)
    return _client


_MODEL = ASSISTANT_MODEL
_MAX_TOKENS = 800


# ─── Per-context system prompts ─────────────────────────────────────────────

_SYSTEM_BASE = """You are the DOCex Assistant — a calm, expert teammate \
who narrates what an agent just did and proposes next steps. You write \
in plain, conversational English. You never hedge with words like \
"appears to" or "may be". You make calls.

You are talking to a finance / programs officer at an African NGO. They \
are competent, busy, and need a TL;DR before they read the table. They \
want to know:
  1. What happened in one sentence (the headline)
  2. The 2-3 things that matter (the narrative — natural sentences, NOT a list)
  3. What to do next (the actions — concrete verbs)

Tone: confident, friendly, lightly informal. Do NOT use exclamation marks. \
Do NOT use emojis except where the action label naturally calls for one \
(e.g. an icon-style ✓ in a label is fine; emoji in narrative is not).

You will receive the run data as JSON. Read every field. Pay attention \
to status / verdict counts, individual flagged items, and any error \
messages. Don't re-state what the user can already see in the table — \
synthesise. Name specific people when relevant ("Aisha Bello") not generics \
("one row").

OUTPUT FORMAT: Return JSON matching this shape exactly:
{
  "headline": "one short sentence — max 12 words",
  "narrative": "2-4 sentences in natural English. Synthesise; don't list.",
  "actions": [
    {"label": "verb phrase, max 6 words", "urgency": "high|medium|low", "reason": "1 sentence"}
  ]
}

Return at most 5 actions, ordered by urgency. Empty actions array is fine \
if the result is fully clean (nothing to do).

Urgency rules:
- high: stop-the-line items. Block fraud. Reject malformed data. Resolve \
  before money moves.
- medium: review-worthy. Human eyeballs should look at it but it's not \
  blocking.
- low: informational. FYI items, suggestions, optimisations.
"""


_CONTEXT_PROMPTS: dict[str, str] = {
    "bank_verify_batch": """The user just ran a Bank Verify batch through \
Paystack — every row of a payment schedule was checked against the bank-of-\
record. Verdicts:
  - verified: name on the account matches the recipient name closely
  - warning: partial match — likely a typo or name variant
  - mismatch: completely different name on the account (potential fraud or admin error)
  - unverifiable: bank API couldn't resolve the account

For warnings, call out specific name variants in the narrative. For \
mismatches, recommend blocking. For unverifiable rows, recommend chasing \
a corrected account number.""",

    "attendance_run": """The user just ran the Attendance Payment Agent. \
Two files were cross-matched (attendance log + payment info form) and people \
were bucketed:
  - paid: registered AND attended ≥1 day — will be paid
  - no_attendance: registered but never showed up — blocked
  - no_payment_info: attended but missing bank details — needs chasing

Accuracy flags may also be present — surface them. Mention the total amount \
to pay. For no_payment_info entries, suggest drafting a chase email. For \
no_attendance, suggest confirming with the attendance team in case the log \
is wrong.""",

    "compliance_check": """The user just ran a Compliance Check — a payment \
voucher was evaluated against a policy rulebook, rule by rule. Each rule got \
one of: pass, flag, block, not_applicable, insufficient_evidence. Overall \
verdict is approved / flagged / blocked.

For blocked checks, name the specific rule(s) that blocked. For flagged, \
name the borderline rules. For insufficient_evidence rules, suggest what \
documents to attach.""",

    "diagnostic": """The user just ran the Self-Check Agent — DOCex \
inspected its own environment, filesystem, engine modules, API routes, \
end-to-end smoke tests, and persisted data integrity.

For failing checks, group by category in the narrative and recommend the \
top 1-2 fixes. For warnings, mention them briefly. For all-pass, give a \
brief reassuring summary.""",
}


# ─── Engine ─────────────────────────────────────────────────────────────────


def summarize(
    context_kind: str,
    payload: dict[str, Any],
    context_id: str | None = None,
) -> AssistantBrief:
    """
    Ask Claude to brief the user on a result.

    payload is the JSON-serialisable result dict — usually a Pydantic
    model dumped via .model_dump(). The Assistant reads the whole thing
    and synthesises a briefing.

    Returns an AssistantBrief. On API failure, returns a graceful fallback
    that still renders something useful so the UI never crashes.
    """
    if context_kind not in _CONTEXT_PROMPTS:
        return _fallback(
            context_kind,
            context_id,
            f"Unknown context kind {context_kind!r}. The Assistant has no prompt for this — defaulting to a generic summary.",
        )

    system = _SYSTEM_BASE + "\n\n" + _CONTEXT_PROMPTS[context_kind]
    user_msg = (
        "Here is the run data as JSON. Brief me.\n\n```json\n"
        + json.dumps(payload, default=str, indent=2)[:50_000]  # cap input
        + "\n```"
    )

    try:
        response = _get_client().messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
    except Exception as exc:
        logger.warning(f"Assistant summarize failed: {exc}")
        return _fallback(
            context_kind,
            context_id,
            "The Assistant couldn't reach Claude right now — your data is below.",
        )

    # Claude returns JSON inside the message. Strip code fences if present
    # (some prompts produce ```json ... ``` wrappers).
    raw = _strip_code_fence(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"Assistant returned non-JSON: {exc}; raw={raw[:200]!r}")
        # Use the raw text as the narrative — better than nothing.
        return AssistantBrief(
            headline=None,
            narrative=raw[:1000],
            actions=[],
            context_kind=context_kind,
            context_id=context_id,
        )

    actions_raw = data.get("actions", []) or []
    actions: list[SuggestedAction] = []
    for a in actions_raw[:5]:
        try:
            actions.append(
                SuggestedAction(
                    label=str(a.get("label", "")).strip()[:80],
                    urgency=a.get("urgency", "low"),
                    reason=str(a.get("reason", "")).strip() or None,
                )
            )
        except Exception:
            continue

    return AssistantBrief(
        headline=str(data.get("headline", "")).strip() or None,
        narrative=str(data.get("narrative", "")).strip() or "No summary available.",
        actions=actions,
        context_kind=context_kind,
        context_id=context_id,
    )


# ─── Helpers ────────────────────────────────────────────────────────────────


def _strip_code_fence(s: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ``` — strip if present."""
    s = s.strip()
    if s.startswith("```"):
        # Drop the opening fence (might be ``` or ```json)
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def _fallback(context_kind: str, context_id: str | None, message: str) -> AssistantBrief:
    """A briefing the UI can still render when Claude is unavailable."""
    return AssistantBrief(
        headline=None,
        narrative=message,
        actions=[],
        context_kind=context_kind,
        context_id=context_id,
    )
