"""
DOCex deterministic rule engine — form-field checks that run in code, no LLM.

Mirrors doc_completeness.py's philosophy: routine, unambiguous rules (a date
comparison, a numeric threshold, "is this vendor on the approved list") don't
need a model call to evaluate. They're solved problems — solving them in code
means they cost zero tokens, return in milliseconds, and never hallucinate.

This is the evaluation backend for PolicyRule.deterministic_check. It reads
structured form_data (from a PaymentType with intake_mode "form" or "hybrid")
rather than parsed document text — see doc_completeness.py for the
document-presence equivalent.

Never raises on a malformed spec or a missing field: an absent or unparsable
value always resolves to a clear "insufficient_evidence" RuleResult, never an
exception that would take down a batch or a form submission.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from models import DeterministicCheckSpec, PolicyRule, RuleResult

_NUMERIC_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Best-effort ISO date parse ("YYYY-MM-DD" or full ISO datetime).
    Returns None (not an exception) on anything unparsable."""
    if not value or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        return None


def _parse_number(value: Optional[str]) -> Optional[float]:
    """Best-effort numeric parse — strips currency symbols, commas, and
    whitespace so "₦500,000" and "500000" both parse. None on failure."""
    if value is None:
        return None
    cleaned = "".join(ch for ch in value.strip() if ch.isdigit() or ch in ".-")
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _insufficient(rule: PolicyRule, missing: list[str], reason: str) -> RuleResult:
    return RuleResult(
        rule_id=rule.id,
        rule_description=rule.description,
        verdict="insufficient_evidence",
        reasoning=reason,
        missing_evidence=missing,
        confidence="not_found",
    )


def _evaluate_date_offset(rule: PolicyRule, spec: DeterministicCheckSpec, form_data: dict[str, str]) -> RuleResult:
    """Compares two dates by day-offset — e.g. departure_date must be at
    least N days after submission (spec.compare_field omitted defaults to
    today, i.e. "at least N days from now"). spec.value is the day threshold.
    """
    target = _parse_date(form_data.get(spec.field))
    if target is None:
        return _insufficient(rule, [spec.field], f"'{spec.field}' is missing or not a valid date.")

    if spec.compare_field:
        anchor = _parse_date(form_data.get(spec.compare_field))
        if anchor is None:
            return _insufficient(rule, [spec.compare_field], f"'{spec.compare_field}' is missing or not a valid date.")
    else:
        anchor = date.today()

    try:
        threshold_days = int(float(spec.value)) if spec.value is not None else 0
    except (TypeError, ValueError):
        threshold_days = 0

    offset_days = (target - anchor).days
    op = spec.operator or ">="
    ok = _NUMERIC_OPS.get(op, _NUMERIC_OPS[">="])(offset_days, threshold_days)

    return RuleResult(
        rule_id=rule.id,
        rule_description=rule.description,
        verdict="pass" if ok else "flag",
        reasoning=(
            f"{spec.field} is {offset_days} day(s) {'after' if offset_days >= 0 else 'before'} "
            f"{spec.compare_field or 'today'} — rule requires {op} {threshold_days} day(s)."
        ),
        payment_evidence=f"{spec.field}={form_data.get(spec.field)}",
        confidence="found",
    )


def _evaluate_threshold(rule: PolicyRule, spec: DeterministicCheckSpec, form_data: dict[str, str]) -> RuleResult:
    """Compares a numeric field against a fixed value with an operator."""
    actual = _parse_number(form_data.get(spec.field))
    if actual is None:
        return _insufficient(rule, [spec.field], f"'{spec.field}' is missing or not a valid number.")
    threshold = _parse_number(spec.value)
    if threshold is None:
        return _insufficient(rule, [], f"Rule '{rule.id}' has no valid threshold configured.")
    op = spec.operator or "<="
    ok = _NUMERIC_OPS.get(op, _NUMERIC_OPS["<="])(actual, threshold)
    return RuleResult(
        rule_id=rule.id,
        rule_description=rule.description,
        verdict="pass" if ok else "flag",
        reasoning=f"{spec.field} = {actual:g}, rule requires {op} {threshold:g}.",
        payment_evidence=f"{spec.field}={form_data.get(spec.field)}",
        confidence="found",
    )


def _evaluate_membership(rule: PolicyRule, spec: DeterministicCheckSpec, form_data: dict[str, str]) -> RuleResult:
    """Field's value must be (operator 'in') or must not be (operator
    'not_in') within spec.values — e.g. vendor must be on the approved list."""
    raw = form_data.get(spec.field)
    if raw is None or not raw.strip():
        return _insufficient(rule, [spec.field], f"'{spec.field}' was not provided.")
    value = raw.strip().lower()
    allowed = {v.strip().lower() for v in spec.values}
    is_member = value in allowed
    op = spec.operator or "in"
    ok = is_member if op == "in" else not is_member
    return RuleResult(
        rule_id=rule.id,
        rule_description=rule.description,
        verdict="pass" if ok else "block",
        reasoning=(
            f"'{raw}' {'is' if is_member else 'is not'} on the list for '{spec.field}' "
            f"(rule requires {op} the approved list)."
        ),
        payment_evidence=f"{spec.field}={raw}",
        confidence="found",
    )


def _evaluate_no_outstanding_advance(
    rule: PolicyRule,
    spec: DeterministicCheckSpec,
    form_data: dict[str, str],
    prior_open_submissions: Optional[list[dict]],
) -> RuleResult:
    """Blocks if the requester already has a prior submission of the same
    payment type that hasn't been retired/closed. Caller (the API layer,
    which has access to persisted checks) is responsible for gathering
    prior_open_submissions — this function stays storage-agnostic.

    Each item in prior_open_submissions is expected to be a dict with at
    least {"label": str} — the label the officer sees, for the reasoning.
    """
    requester = (form_data.get(spec.field) or "").strip()
    if not requester:
        return _insufficient(rule, [spec.field], f"'{spec.field}' (the requester) was not provided.")
    open_items = prior_open_submissions or []
    if open_items:
        labels = ", ".join(i.get("label", "an earlier request") for i in open_items[:3])
        return RuleResult(
            rule_id=rule.id,
            rule_description=rule.description,
            verdict="block",
            reasoning=f"{requester} has an outstanding, unretired advance ({labels}).",
            payment_evidence=f"{spec.field}={requester}",
            confidence="found",
        )
    return RuleResult(
        rule_id=rule.id,
        rule_description=rule.description,
        verdict="pass",
        reasoning=f"No outstanding advance found for {requester}.",
        payment_evidence=f"{spec.field}={requester}",
        confidence="found",
    )


def _evaluate_reference_lookup(
    rule: PolicyRule,
    spec: DeterministicCheckSpec,
    form_data: dict[str, str],
    referenced_submission: Optional[dict],
) -> RuleResult:
    """Validates that a field (e.g. 'advance_reference') points at a real,
    unretired, same-requester prior submission — e.g. a Travel Retirement
    referencing the Travel Advance it's closing out. The caller (API layer)
    resolves the actual lookup and requester match; this function only
    interprets the result, staying storage-agnostic like every other check
    here.

    referenced_submission is expected to be one of:
      None                                    — no reference value provided
      {"found": False}                        — reference didn't resolve
      {"found": True, "retired": bool,
       "requester_match": bool, "label": str} — resolved; caller already
                                                 checked requester identity
    """
    ref = (form_data.get(spec.field) or "").strip()
    if not ref:
        return _insufficient(rule, [spec.field], f"'{spec.field}' was not provided.")
    if referenced_submission is None or not referenced_submission.get("found"):
        return RuleResult(
            rule_id=rule.id, rule_description=rule.description, verdict="block",
            reasoning=f"No matching advance found for reference '{ref}'.",
            payment_evidence=f"{spec.field}={ref}", confidence="found",
        )
    if not referenced_submission.get("requester_match", True):
        return RuleResult(
            rule_id=rule.id, rule_description=rule.description, verdict="block",
            reasoning=f"Reference '{ref}' does not belong to this requester.",
            payment_evidence=f"{spec.field}={ref}", confidence="found",
        )
    if referenced_submission.get("retired"):
        return RuleResult(
            rule_id=rule.id, rule_description=rule.description, verdict="block",
            reasoning=f"Advance '{referenced_submission.get('label', ref)}' has already been retired.",
            payment_evidence=f"{spec.field}={ref}", confidence="found",
        )
    return RuleResult(
        rule_id=rule.id, rule_description=rule.description, verdict="pass",
        reasoning=f"Matches outstanding advance '{referenced_submission.get('label', ref)}'.",
        payment_evidence=f"{spec.field}={ref}", confidence="found",
    )


def evaluate_rule(
    rule: PolicyRule,
    form_data: dict[str, str],
    *,
    prior_open_submissions: Optional[list[dict]] = None,
    referenced_submission: Optional[dict] = None,
) -> RuleResult:
    """Evaluate one deterministic rule. Never raises."""
    spec = rule.deterministic_check
    if spec is None:
        return _insufficient(rule, [], f"Rule '{rule.id}' is marked deterministic but has no check configured.")
    if spec.kind == "date_offset":
        return _evaluate_date_offset(rule, spec, form_data)
    if spec.kind == "threshold":
        return _evaluate_threshold(rule, spec, form_data)
    if spec.kind == "membership":
        return _evaluate_membership(rule, spec, form_data)
    if spec.kind == "no_outstanding_advance":
        return _evaluate_no_outstanding_advance(rule, spec, form_data, prior_open_submissions)
    if spec.kind == "reference_lookup":
        return _evaluate_reference_lookup(rule, spec, form_data, referenced_submission)
    return _insufficient(rule, [], f"Unknown deterministic check kind: '{spec.kind}'.")


def evaluate_deterministic_rules(
    rules: list[PolicyRule],
    form_data: dict[str, str],
    *,
    prior_open_submissions: Optional[list[dict]] = None,
    referenced_submission: Optional[dict] = None,
) -> list[RuleResult]:
    """Evaluate every deterministic rule in `rules` against `form_data`.
    Order matches input order; every rule produces exactly one RuleResult."""
    return [
        evaluate_rule(
            r, form_data,
            prior_open_submissions=prior_open_submissions,
            referenced_submission=referenced_submission,
        )
        for r in rules
    ]
