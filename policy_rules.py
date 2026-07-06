"""
Deterministic policy-rule extraction — code, not an LLM.

Turns a policy document into structured ``PolicyRule`` objects for the common,
well-shaped rule types — spending thresholds, required documents, approval
limits, and deadlines — using regex + heuristics. It runs in milliseconds with
zero tokens, so creating a rulebook doesn't have to wait on (or depend on) a
model call.

Design principle: **precision over recall.** It only emits a rule when a
pattern clearly fires, and every rule carries the exact sentence it came from
(``source_quote``) so a human can verify it. Missing a subtly-worded clause is
acceptable — the reviewer (or an optional LLM pass) catches the long tail.
Emitting a *wrong* rule is not acceptable in a compliance tool, so the matchers
stay conservative.

This is the code-first pass in the hybrid design: code does the obvious rules
instantly; an LLM is only needed for the residual nuance, or not at all.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from models import PolicyRule

# ── Amounts / currency (Nigerian-naira-first, USD-aware) ────────────────────
# Matches ₦500,000 · NGN 500,000 · N500,000 · ₦1.5m · ₦500k · $2,000 · 500,000 naira
_AMOUNT_RE = re.compile(
    # ₦/NGN/US$/$/ bare-N (word-boundary N so it can't match the 'n' in "within"),
    # then digits, then an OPTIONAL magnitude suffix that must end on a word
    # boundary (so it can't swallow the 'm' in "must").
    r"(?:(?:₦|NGN|US\$|USD|\$|\bN)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|thousand|bn|m|k)\b)?)"
    r"|(?:\b\d[\d,]*(?:\.\d+)?\s?(?:naira|dollars?|USD|NGN)\b)",
    re.IGNORECASE,
)

# Obligation language — the signal that a sentence states a *rule*, not prose.
_MODAL_RE = re.compile(
    r"\b(must|shall|require[sd]?|required|need(?:s|ed)?|mandatory|obligatory|"
    r"prohibited|not\s+permitted|may\s+not|are\s+not\s+allowed|only\s+(?:be|if|where))\b",
    re.I,
)
# Comparison words that turn an amount into a threshold.
_THRESHOLD_CTX_RE = re.compile(
    r"\b(above|over|exceed(?:s|ing)?|greater\s+than|more\s+than|up\s+to|below|"
    r"less\s+than|at\s+least|at\s+most|maximum|minimum|not\s+exceed(?:ing)?|"
    r"in\s+excess\s+of|equal\s+to\s+or\s+(?:greater|more))\b",
    re.I,
)
_APPROVAL_RE = re.compile(
    r"\b(approv\w*|authoris\w*|authoriz\w*|sign[-\s]?off|signed\s+off|"
    r"counter[-\s]?sign\w*|endorse\w*|sign\s+off)\b",
    re.I,
)
_DOC_TRIGGER_RE = re.compile(
    r"\b(attach\w*|submit\w*|provide\w*|accompan\w*|support(?:ed|ing)?\s+by|"
    r"enclose\w*|include\s+the\s+following|supporting\s+document\w*|"
    r"must\s+be\s+supported)\b",
    re.I,
)
_DEADLINE_RE = re.compile(
    r"\bwithin\s+(\d+)\s+(working|business|calendar)?\s*(day|week|month)s?\b", re.I
)
_PROCUREMENT_RE = re.compile(
    r"\b(quotation|\bquote\b|tender|\bbid\b|purchase\s+order|\bP\.?O\.?\b|\bLPO\b|"
    r"procure\w*|vendor|supplier|competitive)\b",
    re.I,
)

# Leading clause reference, e.g. "4.2 ", "5.1.b) ", "Section 3 ".
_CLAUSE_RE = re.compile(r"^\s*((?:section\s+|clause\s+|article\s+)?\d+(?:\.\d+)*)[.)]?\s+", re.I)
_PAGE_RE = re.compile(r"^\s*={2,}\s*PAGE\s+\d+\s*={2,}\s*$", re.I)

# Known supporting-document names → canonical label. Presence-based (reliable),
# not phrase-parsing (fragile).
_DOC_KEYWORDS: list[tuple[str, str]] = [
    ("invoice", r"\binvoice\b"),
    ("purchase order", r"purchase\s+order|\bLPO\b|\bP\.?O\.?\b"),
    ("goods received note", r"goods\s+received\s+note|\bGRN\b|delivery\s+note|\bwaybill\b|proof\s+of\s+delivery"),
    ("receipt", r"\breceipt\b"),
    ("quotation(s)", r"\bquotation\b|\bquote\b|\bRFQ\b"),
    ("signed contract", r"\bcontract\b|\bagreement\b|terms\s+of\s+reference|\bToR\b"),
    ("bank details", r"bank\s+details|account\s+(?:number|name|details)"),
    ("attendance sheet", r"attendance\s+(?:sheet|list|register)|sign[-\s]?in\s+sheet"),
    ("approval memo/email", r"approval\s+(?:memo|form|email|note)"),
    ("budget", r"\bbudget\b"),
    ("activity/completion report", r"activity\s+report|completion\s+report|narrative\s+report|deliverabl\w*"),
]

_MAX_RULES = 120
_MIN_UNIT_LEN = 25


def _units(text: str) -> list[tuple[Optional[str], str]]:
    """Split policy text into candidate 'units' (a clause or sentence), each as
    ``(clause_reference, text)``. Skips page markers and short headings."""
    out: list[tuple[Optional[str], str]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or _PAGE_RE.match(line):
            continue
        # Split a long line into sentences. The lookbehind on . ; and lookahead
        # on a capital/digit avoids splitting decimals inside amounts (₦1.5m).
        for chunk in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", line):
            unit = chunk.strip()
            if len(unit) < _MIN_UNIT_LEN:
                continue
            ref: Optional[str] = None
            m = _CLAUSE_RE.match(unit)
            if m:
                ref = re.sub(r"^\s*(section|clause|article)\s+", "", m.group(1), flags=re.I).strip()
                stripped = _CLAUSE_RE.sub("", unit, count=1).strip()
                if len(stripped) >= 20:  # don't strip if it leaves nothing meaningful
                    unit = stripped
            out.append((ref, unit))
    return out


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_raw(documents: list[tuple[str, str]]) -> list[dict]:
    """Core extraction — returns plain dicts (unit-testable without pydantic)."""
    rules: list[dict] = []
    seen: set[str] = set()

    for _filename, text in documents:
        for ref, unit in _units(text):
            amount = _AMOUNT_RE.search(unit)
            is_approval = bool(_APPROVAL_RE.search(unit))
            is_doc = bool(_DOC_TRIGGER_RE.search(unit))
            deadline = _DEADLINE_RE.search(unit)
            has_modal = bool(_MODAL_RE.search(unit))
            thr_ctx = _THRESHOLD_CTX_RE.search(unit)

            is_threshold = bool(amount) and (has_modal or bool(thr_ctx))

            fired = (
                is_threshold
                or (is_approval and (bool(amount) or has_modal))
                or is_doc
                or bool(deadline)
            )
            if not fired:
                continue

            norm = _clean(unit).lower()
            if norm in seen:
                continue
            seen.add(norm)

            # Category — most specific signal wins.
            if is_approval:
                category = "approvals"
            elif is_threshold and _PROCUREMENT_RE.search(unit):
                category = "procurement"
            elif is_threshold:
                category = "thresholds"
            elif deadline:
                category = "deadlines"
            else:
                category = "documentation"

            # Condition (when the rule applies).
            condition: Optional[str] = None
            if amount:
                prefix = (thr_ctx.group(0) + " ") if thr_ctx else ""
                condition = _clean(prefix + amount.group(0))
            elif deadline:
                span = f"{deadline.group(1)} {(deadline.group(2) or '').strip()} {deadline.group(3)}s"
                condition = _clean("within " + span)

            # Evidence required (supporting documents named in the clause).
            evidence: list[str] = []
            if is_doc or is_threshold:
                for label, pat in _DOC_KEYWORDS:
                    if re.search(pat, unit, re.I) and label not in evidence:
                        evidence.append(label)

            desc = _clean(unit)
            if len(desc) > 240:
                desc = desc[:237].rstrip() + "…"

            rules.append(
                {
                    "clause_reference": ref,
                    "description": desc,
                    "condition": condition,
                    "evidence_required": evidence,
                    "category": category,
                    "source_quote": _clean(unit),
                }
            )
            if len(rules) >= _MAX_RULES:
                return rules
    return rules


def extract_rules(documents: list[tuple[str, str]]) -> list[PolicyRule]:
    """Extract structured PolicyRules from policy document text — no LLM.

    documents: list of (filename, extracted_text).
    Returns a list of PolicyRule (evaluation_type='llm' so the *checking* engine
    still reasons over the uploaded payment documents against each rule — only
    the *authoring* of the rulebook is made deterministic here).
    """
    out: list[PolicyRule] = []
    for r in _extract_raw(documents):
        out.append(
            PolicyRule(
                id=f"{r['category']}-{uuid.uuid4().hex[:6]}",
                clause_reference=r["clause_reference"],
                description=r["description"],
                condition=r["condition"],
                evidence_required=r["evidence_required"],
                category=r["category"],
                source_quote=r["source_quote"],
                evaluation_type="llm",
            )
        )
    return out
