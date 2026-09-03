"""
Per-organisation model usage metering.

WHY THIS EXISTS
Model calls are the largest variable cost of running DOCex for a client, and
until now they were printed to stdout and forgotten. That made three questions
unanswerable, all of which matter commercially:

  * "What does NEEM actually cost us this month?"  — you cannot price a
    renewal, or quote the next client, on a guess.
  * "Which client's volume is growing?"            — the one whose usage
    doubles quietly is the one whose margin disappears quietly.
  * "Did the caching work?"                        — cache_read vs
    cache_creation tokens is the only honest answer.

WHAT IT RECORDS
One record per (org, day, model, operation), holding call count and token
totals. Daily granularity is enough to spot a spike and answer a billing
question, while keeping storage bounded — a busy org produces a handful of
records a day, not one per request.

TOKENS ARE FACTS. COST IS DERIVED.
Only token counts are stored. Money is computed on read from a rate table you
configure, because published prices change and a number baked into a database
row becomes wrong silently. Set the rates below via environment variables and
verify them against Anthropic's current pricing page before quoting anyone.

METERING MUST NEVER BREAK A PAYMENT
`record()` swallows every exception. A compliance check that produced a correct
answer must not fail because we couldn't write a usage row. Losing a metering
record costs you a rounding error; failing the check costs the client a payment.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Optional

import store

_USAGE = "model_usage"


def _today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _month_of(day: str) -> str:
    return day[:7]


def _rid(day: str, model: str, operation: str) -> str:
    """Record id, safe for the store's key validation (no spaces or slashes)."""
    safe = lambda s: "".join(c if (c.isalnum() or c in "-_.") else "-" for c in s)
    return f"{day}.{safe(model)}.{safe(operation) or 'unknown'}"


# ─── rates ──────────────────────────────────────────────────────────────────
# USD per MILLION tokens. ⚠️ VERIFY against Anthropic's current pricing before
# using these for anything commercial — they are configuration, not facts, and
# published prices change.
#
#   DOCEX_RATE_<TIER>_IN / _OUT   where TIER is SONNET or HAIKU
#   DOCEX_USD_NGN                 exchange rate used for the NGN view
#
# Cached input is billed differently from fresh input; the split is kept so the
# saving from prompt caching is visible rather than assumed.


def _rate(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _rates_for(model: str) -> tuple[float, float, float]:
    """(input, output, cached-input) USD per million tokens."""
    m = (model or "").lower()
    if "haiku" in m:
        return (_rate("DOCEX_RATE_HAIKU_IN", 1.0),
                _rate("DOCEX_RATE_HAIKU_OUT", 5.0),
                _rate("DOCEX_RATE_HAIKU_CACHED_IN", 0.1))
    # Default to the more expensive tier: an unknown model should over-estimate
    # cost, never under-estimate it.
    return (_rate("DOCEX_RATE_SONNET_IN", 3.0),
            _rate("DOCEX_RATE_SONNET_OUT", 15.0),
            _rate("DOCEX_RATE_SONNET_CACHED_IN", 0.3))


def usd_to_ngn() -> float:
    return _rate("DOCEX_USD_NGN", 1600.0)


# ─── recording ──────────────────────────────────────────────────────────────


def record(
    org_id: Optional[str],
    operation: str,
    model: str,
    *,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cache_read_tokens: Optional[int] = None,
    cache_creation_tokens: Optional[int] = None,
    calls: int = 1,
) -> None:
    """Add one call's usage to today's bucket. Never raises.

    `operation` is a short stable label — "compliance_check", "extraction",
    "assistant_brief" — so you can see which part of the product is expensive,
    not just which client.
    """
    try:
        if not org_id:
            return
        org = store.require_org(org_id)
        day = _today()
        rid = _rid(day, model, operation)
        st = store.get_store()
        cur = st.get(org, _USAGE, rid) or {}
        st.put(org, _USAGE, rid, {
            "day": day,
            "month": _month_of(day),
            "model": model,
            "operation": operation,
            "calls": int(cur.get("calls", 0)) + int(calls or 0),
            "input_tokens": int(cur.get("input_tokens", 0)) + int(input_tokens or 0),
            "output_tokens": int(cur.get("output_tokens", 0)) + int(output_tokens or 0),
            "cache_read_tokens": int(cur.get("cache_read_tokens", 0)) + int(cache_read_tokens or 0),
            "cache_creation_tokens": int(cur.get("cache_creation_tokens", 0)) + int(cache_creation_tokens or 0),
        })
    except Exception as exc:  # pragma: no cover - defensive by design
        # Deliberately swallowed. See the module docstring: a metering failure
        # must never turn a correct compliance answer into a failed request.
        print(f"[usage] not recorded ({exc})")


def record_metrics(org_id: Optional[str], operation: str, metrics: dict) -> None:
    """Convenience wrapper for engines that already build a metrics dict
    (compliance.check_payment returns one shaped exactly like this)."""
    if not metrics:
        return
    record(
        org_id, operation, metrics.get("model") or "unknown",
        input_tokens=metrics.get("input_tokens"),
        output_tokens=metrics.get("output_tokens"),
        cache_read_tokens=metrics.get("cache_read_tokens"),
        cache_creation_tokens=metrics.get("cache_creation_tokens"),
        calls=int(metrics.get("llm_calls") or 1),
    )


# ─── reading ────────────────────────────────────────────────────────────────


@dataclass
class UsageSummary:
    org_id: str
    period: str                      # "2026-09" or "all"
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    cost_ngn: float = 0.0
    by_model: dict = field(default_factory=dict)
    by_operation: dict = field(default_factory=dict)

    @property
    def cache_hit_rate(self) -> float:
        """Share of input tokens served from cache. The honest measure of
        whether prompt caching is earning its keep."""
        total = self.input_tokens + self.cache_read_tokens
        return round(self.cache_read_tokens / total, 4) if total else 0.0

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id, "period": self.period, "calls": self.calls,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_hit_rate": self.cache_hit_rate,
            "cost_usd": round(self.cost_usd, 4),
            "cost_ngn": round(self.cost_ngn, 2),
            "by_model": self.by_model, "by_operation": self.by_operation,
        }


def _cost_of(row: dict) -> float:
    rin, rout, rcached = _rates_for(row.get("model", ""))
    m = 1_000_000.0
    # Cache CREATION is charged at (usually above) the normal input rate; cache
    # READ is the cheap one. Treating creation as normal input keeps the
    # estimate conservative rather than flattering.
    return (
        (int(row.get("input_tokens", 0)) + int(row.get("cache_creation_tokens", 0))) / m * rin
        + int(row.get("output_tokens", 0)) / m * rout
        + int(row.get("cache_read_tokens", 0)) / m * rcached
    )


def summary(org_id: str, period: Optional[str] = None) -> UsageSummary:
    """Usage for one org. `period` is "YYYY-MM"; omitted means everything.

    Pass the current month to answer "what is this client costing us now"; pass
    nothing to answer "what have they cost us in total".
    """
    org = store.require_org(org_id)
    out = UsageSummary(org_id=org, period=period or "all")
    for row in store.get_store().list(org, _USAGE):
        if period and row.get("month") != period:
            continue
        cost = _cost_of(row)
        out.calls += int(row.get("calls", 0))
        out.input_tokens += int(row.get("input_tokens", 0))
        out.output_tokens += int(row.get("output_tokens", 0))
        out.cache_read_tokens += int(row.get("cache_read_tokens", 0))
        out.cache_creation_tokens += int(row.get("cache_creation_tokens", 0))
        out.cost_usd += cost

        model = row.get("model") or "unknown"
        op = row.get("operation") or "unknown"
        for bucket, key in ((out.by_model, model), (out.by_operation, op)):
            b = bucket.setdefault(key, {"calls": 0, "cost_usd": 0.0})
            b["calls"] += int(row.get("calls", 0))
            b["cost_usd"] = round(b["cost_usd"] + cost, 4)

    out.cost_ngn = out.cost_usd * usd_to_ngn()
    return out


def daily(org_id: str, period: Optional[str] = None) -> list[dict]:
    """Per-day totals, oldest first. This is the series that shows a client's
    volume climbing before it shows up in a bill."""
    org = store.require_org(org_id)
    days: dict[str, dict] = {}
    for row in store.get_store().list(org, _USAGE):
        if period and row.get("month") != period:
            continue
        d = days.setdefault(row.get("day", "?"),
                            {"day": row.get("day", "?"), "calls": 0, "cost_usd": 0.0})
        d["calls"] += int(row.get("calls", 0))
        d["cost_usd"] = round(d["cost_usd"] + _cost_of(row), 4)
    return sorted(days.values(), key=lambda r: r["day"])
