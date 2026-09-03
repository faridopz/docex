"""
Usage metering tests.

The point of this module is commercial: it answers "what does this client cost
us this month". So the tests care about three things — that the arithmetic is
right, that orgs never mix, and that metering can never break a payment.

Run: python test_usage.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-usage-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import usage  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def test_records_and_totals() -> None:
    print("\nCalls accumulate into the day's bucket")
    usage.record("acme", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=1000, output_tokens=500)
    usage.record("acme", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=2000, output_tokens=250)
    s = usage.summary("acme")
    check("two calls counted", s.calls == 2)
    check("input tokens summed", s.input_tokens == 3000)
    check("output tokens summed", s.output_tokens == 750)
    check("cost is positive", s.cost_usd > 0)
    check("naira view derived", s.cost_ngn > s.cost_usd)


def test_cost_arithmetic() -> None:
    print("\nCost maths is right, and conservative where it's uncertain")
    # 1M input + 1M output on the default Sonnet rates (3 / 15 per million).
    usage.record("math", "x", "claude-sonnet-4-6",
                 input_tokens=1_000_000, output_tokens=1_000_000)
    s = usage.summary("math")
    check(f"1M in + 1M out ≈ $18 (got ${s.cost_usd:.2f})", abs(s.cost_usd - 18.0) < 0.01)

    # Haiku must be cheaper than Sonnet for identical volume — if this ever
    # inverts, the tiering in ai_config is pointless.
    usage.record("cheap", "x", "claude-haiku-4-5-20251001",
                 input_tokens=1_000_000, output_tokens=1_000_000)
    check("haiku is cheaper than sonnet for the same tokens",
          usage.summary("cheap").cost_usd < s.cost_usd)

    # An unknown model must over-estimate, never under-estimate.
    usage.record("unknown", "x", "some-future-model",
                 input_tokens=1_000_000, output_tokens=1_000_000)
    check("unknown model is priced at the expensive tier",
          abs(usage.summary("unknown").cost_usd - 18.0) < 0.01)


def test_cache_savings_are_visible() -> None:
    print("\nPrompt caching shows up as a measurable saving")
    usage.record("cached", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=1000, output_tokens=100, cache_read_tokens=99_000)
    usage.record("uncached", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=100_000, output_tokens=100)
    c, u = usage.summary("cached"), usage.summary("uncached")
    check(f"cached run is cheaper (${c.cost_usd:.4f} vs ${u.cost_usd:.4f})",
          c.cost_usd < u.cost_usd)
    check(f"hit rate reported ({c.cache_hit_rate:.0%})", c.cache_hit_rate > 0.9)
    check("no cache ⇒ 0% hit rate", u.cache_hit_rate == 0.0)


def test_breakdowns() -> None:
    print("\nBroken down by model and by operation")
    usage.record("split", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=1000, output_tokens=100)
    usage.record("split", "extraction", "claude-haiku-4-5-20251001",
                 input_tokens=5000, output_tokens=200)
    s = usage.summary("split")
    check("two operations tracked", set(s.by_operation) == {"compliance_check", "extraction"})
    check("two models tracked", len(s.by_model) == 2)
    check("per-operation calls counted", s.by_operation["extraction"]["calls"] == 1)
    check("dict form is serialisable", isinstance(s.to_dict()["cost_ngn"], float))


def test_orgs_never_mix() -> None:
    print("\nOne client's usage is never another's bill")
    usage.record("orgA", "x", "claude-sonnet-4-6", input_tokens=10_000, output_tokens=1)
    usage.record("orgB", "x", "claude-sonnet-4-6", input_tokens=20_000, output_tokens=1)
    check("A sees only its own", usage.summary("orgA").input_tokens == 10_000)
    check("B sees only its own", usage.summary("orgB").input_tokens == 20_000)
    check("an org with no usage reports zero", usage.summary("orgC").calls == 0)


def test_period_filter_and_daily() -> None:
    print("\nFiltering by month, and the daily series")
    usage.record("period", "x", "claude-sonnet-4-6", input_tokens=100, output_tokens=10)
    this_month = usage._month_of(usage._today())
    check("current month matches all-time here",
          usage.summary("period", this_month).calls == usage.summary("period").calls)
    check("a month with no usage is empty", usage.summary("period", "1999-01").calls == 0)
    d = usage.daily("period")
    check("one day in the series", len(d) == 1)
    check("the day carries a cost", d[0]["cost_usd"] > 0)


def test_metering_never_breaks_the_caller() -> None:
    print("\nMetering failures are swallowed — a payment must never fail for this")
    usage.record(None, "x", "m", input_tokens=1)          # no org
    usage.record("", "x", "m", input_tokens=1)            # blank org
    usage.record("bad/org", "x", "m", input_tokens=1)     # invalid key
    usage.record("ok", "x", "m")                          # no token counts at all
    check("none of those raised", True)
    check("the valid one still recorded", usage.summary("ok").calls == 1)

    class Broken:
        def list(self, *a, **k): raise RuntimeError("store down")
        def get(self, *a, **k): raise RuntimeError("store down")
        def put(self, *a, **k): raise RuntimeError("store down")
    good = store.get_store()
    store.set_store(Broken())
    usage.record("acme", "x", "m", input_tokens=1)
    check("a dead store does not raise", True)
    store.set_store(good)


def test_record_metrics_wrapper() -> None:
    print("\nrecord_metrics() accepts what compliance.check_payment returns")
    usage.record_metrics("wrap", "compliance_check", {
        "model": "claude-sonnet-4-6", "llm_calls": 3,
        "input_tokens": 900, "output_tokens": 120,
        "cache_read_tokens": 4000, "cache_creation_tokens": 500,
    })
    s = usage.summary("wrap")
    check("llm_calls used as the call count", s.calls == 3)
    check("cache fields carried through", s.cache_read_tokens == 4000)
    usage.record_metrics("wrap", "x", {})       # empty metrics
    usage.record_metrics("wrap", "x", None)     # missing metrics
    check("empty metrics are ignored, not an error", usage.summary("wrap").calls == 3)


def main() -> int:
    print("=" * 64)
    print("Usage metering — what each client actually costs")
    print("=" * 64)
    test_records_and_totals()
    test_cost_arithmetic()
    test_cache_savings_are_visible()
    test_breakdowns()
    test_orgs_never_mix()
    test_period_filter_and_daily()
    test_metering_never_breaks_the_caller()
    test_record_metrics_wrapper()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
