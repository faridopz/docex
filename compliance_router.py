"""
DOCex policy router — auto-select the best-fitting rulebook(s) for a payment.

An organisation can hold many policy sets (procurement, travel, a specific
donor's terms…). Rather than make the officer pick the right one every time,
the router reads the payment documents and ranks the rulebooks by how well
they fit — so the system applies the right policy automatically.

This is dependency-free lexical ranking (no LLM, no extra deps): each
rulebook is profiled from its routing hints (`applies_to`), its name, and
its rule text; the payment text is scored against each profile with an
idf-weighted overlap so generic words ("payment", "amount") don't dominate.
A semantic backend can slot in behind rank_rulebooks() later.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from models import PolicyRulebook

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Very common words that carry no routing signal — every payment/policy has
# them, so they'd otherwise reward every rulebook equally.
_STOPISH = {
    "the", "and", "for", "are", "with", "that", "this", "shall", "must",
    "any", "all", "from", "per", "payment", "amount", "policy", "rule",
    "rules", "procurement", "of", "to", "a", "an", "is", "in", "on", "or",
    "be", "by", "as", "at", "it",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPISH]


@dataclass
class RouteSuggestion:
    rulebook_id: str
    rulebook_name: str
    score: float
    confidence: str            # "high" | "medium" | "low"
    matched_terms: list[str]   # why it matched (for the UI)


def _profile_terms(rb: PolicyRulebook) -> list[str]:
    """The vocabulary that characterises when a rulebook applies."""
    parts: list[str] = [rb.name]
    parts += rb.applies_to or []
    for r in rb.rules:
        parts.append(r.description or "")
        parts.append(r.category or "")
    # applies_to keywords are the strongest signal — weight them by repeating.
    parts += (rb.applies_to or []) * 2
    return _tokens(" ".join(parts))


def rank_rulebooks(
    payment_text: str, rulebooks: list[PolicyRulebook]
) -> list[RouteSuggestion]:
    """Rank rulebooks by fit to the payment text (best first)."""
    pay = _tokens(payment_text)
    if not pay or not rulebooks:
        return []
    pay_tf = Counter(pay)

    profiles = {rb.id: set(_profile_terms(rb)) for rb in rulebooks}
    n = len(rulebooks)
    df: Counter[str] = Counter()
    for terms in profiles.values():
        for t in terms:
            df[t] += 1

    raw: list[tuple[PolicyRulebook, float, list[str]]] = []
    for rb in rulebooks:
        terms = profiles[rb.id]
        score = 0.0
        hits: list[tuple[str, float]] = []
        for t in terms:
            tf = pay_tf.get(t, 0)
            if tf == 0:
                continue
            idf = math.log(1 + n / (1 + df[t]))  # rarer across rulebooks → higher
            w = tf * idf
            score += w
            hits.append((t, w))
        # Normalise so a huge rulebook doesn't win on sheer vocabulary size.
        norm = score / (math.sqrt(len(terms)) or 1.0)
        hits.sort(key=lambda x: x[1], reverse=True)
        raw.append((rb, norm, [h[0] for h in hits[:6]]))

    raw.sort(key=lambda x: x[1], reverse=True)

    top = raw[0][1] if raw else 0.0
    second = raw[1][1] if len(raw) > 1 else 0.0
    out: list[RouteSuggestion] = []
    for rb, sc, hits in raw:
        if sc <= 0:
            continue
        # Confidence: clear leader = high; matched-but-contested = medium; weak = low.
        if sc == top and (second == 0 or top >= 1.5 * second) and top > 0.5:
            conf = "high"
        elif sc >= 0.5 * top and sc > 0.3:
            conf = "medium"
        else:
            conf = "low"
        out.append(
            RouteSuggestion(
                rulebook_id=rb.id,
                rulebook_name=rb.name,
                score=round(sc, 3),
                confidence=conf,
                matched_terms=hits,
            )
        )
    return out
