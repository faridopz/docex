"""
Spend-limit and kill-switch tests.

The bug these prevent: before this module, an authenticated user could loop a
compliance check and generate an unbounded Anthropic bill. max_tokens caps one
request; nothing capped the number of them.

So the tests care about one thing above all — that the guards FAIL CLOSED.

Run: python test_observability.py
"""
from __future__ import annotations

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-obs-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import observability as obs  # noqa: E402
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


def clear_env(*names):
    for n in names:
        os.environ.pop(n, None)


def reset_window(org: str) -> None:
    obs._recent.pop(org, None)


def test_burst_is_capped() -> None:
    print("\nA burst of requests is stopped")
    os.environ["DOCEX_LLM_RATE_PER_MIN"] = "5"
    reset_window("burst")
    for i in range(5):
        obs.check_llm_allowed("burst")
    try:
        obs.check_llm_allowed("burst")
        check("the 6th request is refused", False)
    except obs.LimitExceeded as exc:
        check("the 6th request is refused", True)
        check("the message names the limit", "5 per minute" in str(exc))
        check("and says when to retry", "Try again" in str(exc))
    clear_env("DOCEX_LLM_RATE_PER_MIN")


def test_limits_are_per_org() -> None:
    print("\nOne client cannot exhaust another's allowance")
    os.environ["DOCEX_LLM_RATE_PER_MIN"] = "3"
    reset_window("orgA"); reset_window("orgB")
    for _ in range(3):
        obs.check_llm_allowed("orgA")
    try:
        obs.check_llm_allowed("orgA")
        check("orgA is now blocked", False)
    except obs.LimitExceeded:
        check("orgA is now blocked", True)
    try:
        obs.check_llm_allowed("orgB")
        check("orgB is unaffected", True)
    except obs.LimitExceeded:
        check("orgB is unaffected", False)
    clear_env("DOCEX_LLM_RATE_PER_MIN")


def test_daily_call_cap() -> None:
    print("\nSustained volume is capped for the day")
    os.environ["DOCEX_LLM_DAILY_CALLS"] = "10"
    os.environ["DOCEX_LLM_RATE_PER_MIN"] = "0"        # isolate this guard
    reset_window("volume")
    obs.check_llm_allowed("volume")                    # under the cap
    check("allowed while under the cap", True)

    usage.record("volume", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=100, output_tokens=10, calls=10)
    try:
        obs.check_llm_allowed("volume")
        check("blocked once the daily cap is reached", False)
    except obs.LimitExceeded as exc:
        check("blocked once the daily cap is reached", True)
        check("the message names the cap", "10 requests" in str(exc))
        check("and says when it resets", "midnight UTC" in str(exc))
    clear_env("DOCEX_LLM_DAILY_CALLS", "DOCEX_LLM_RATE_PER_MIN")


def test_daily_spend_cap() -> None:
    print("\nSpend is capped even when the call count is fine")
    os.environ["DOCEX_LLM_DAILY_USD"] = "1.00"
    os.environ["DOCEX_LLM_RATE_PER_MIN"] = "0"
    os.environ["DOCEX_LLM_DAILY_CALLS"] = "0"
    reset_window("spendy")
    # 1M input + 1M output on Sonnet defaults ≈ $18 — well past a $1 cap,
    # on a single call. Volume caps alone would not have caught this.
    usage.record("spendy", "compliance_check", "claude-sonnet-4-6",
                 input_tokens=1_000_000, output_tokens=1_000_000)
    try:
        obs.check_llm_allowed("spendy")
        check("blocked on spend", False)
    except obs.LimitExceeded as exc:
        check("blocked on spend", True)
        check("the message names the amount", "$1.00" in str(exc))
    clear_env("DOCEX_LLM_DAILY_USD", "DOCEX_LLM_RATE_PER_MIN", "DOCEX_LLM_DAILY_CALLS")


def test_metering_failure_does_not_take_the_product_down() -> None:
    print("\nIf metering breaks, the burst guard still holds")
    class Broken:
        def list(self, *a, **k): raise RuntimeError("store down")
        def get(self, *a, **k): raise RuntimeError("store down")
        def put(self, *a, **k): raise RuntimeError("store down")
    good = store.get_store()
    store.set_store(Broken())
    reset_window("degraded")
    try:
        obs.check_llm_allowed("degraded")
        check("a request still goes through", True)
    except obs.LimitExceeded:
        check("a request still goes through", False)

    os.environ["DOCEX_LLM_RATE_PER_MIN"] = "2"
    reset_window("degraded")
    obs.check_llm_allowed("degraded"); obs.check_llm_allowed("degraded")
    try:
        obs.check_llm_allowed("degraded")
        check("but the burst guard still fires", False)
    except obs.LimitExceeded:
        check("but the burst guard still fires", True)
    clear_env("DOCEX_LLM_RATE_PER_MIN")
    store.set_store(good)


def test_kill_switch() -> None:
    print("\nThe kill switch works without a deploy")
    clear_env("DOCEX_KILL_ALL", "DOCEX_KILL_LLM")
    check("nothing killed by default", obs.feature_killed("llm") is False)

    os.environ["DOCEX_KILL_LLM"] = "1"
    check("a named feature can be killed", obs.feature_killed("llm") is True)
    check("others are unaffected", obs.feature_killed("uploads") is False)
    try:
        obs.require_enabled("llm", "AI features")
        check("require_enabled raises", False)
    except obs.LimitExceeded as exc:
        check("require_enabled raises", True)
        check("the message is for a user, not a log", "temporarily disabled" in str(exc))
    clear_env("DOCEX_KILL_LLM")

    os.environ["DOCEX_KILL_ALL"] = "true"
    check("KILL_ALL kills everything", obs.feature_killed("anything") is True)
    clear_env("DOCEX_KILL_ALL")
    check("and lifts cleanly", obs.feature_killed("anything") is False)


def test_sentry_is_optional_and_scrubs() -> None:
    print("\nSentry is optional, and never ships credentials")
    clear_env("SENTRY_DSN")
    obs._sentry_ready = False
    check("no DSN means no Sentry, and no crash", obs.init_sentry() is False)
    obs.capture(ValueError("x"), context="safe")     # must be a no-op
    check("capture is safe when unconfigured", True)

    event = {
        "request": {
            "headers": {"Authorization": "Bearer secret-token",
                        "X-Api-Key": "sk-ant-123", "User-Agent": "Mozilla"},
            "query_string": "token=abc",
            "data": {"password": "hunter2"},
        },
        "extra": {"api_key": "sk-ant-xyz", "vendor": "Sahel Ltd"},
    }
    cleaned = obs._scrub(event, None)
    h = cleaned["request"]["headers"]
    check("Authorization redacted", h["Authorization"] == "[redacted]")
    check("API key header redacted", h["X-Api-Key"] == "[redacted]")
    check("harmless headers kept", h["User-Agent"] == "Mozilla")
    check("query string dropped", "query_string" not in cleaned["request"])
    check("body dropped", "data" not in cleaned["request"])
    check("secret extras redacted", cleaned["extra"]["api_key"] == "[redacted]")
    check("non-secret extras kept", cleaned["extra"]["vendor"] == "Sahel Ltd")


def main() -> int:
    print("=" * 64)
    print("Spend limits and kill switch — fail closed, always")
    print("=" * 64)
    test_burst_is_capped()
    test_limits_are_per_org()
    test_daily_call_cap()
    test_daily_spend_cap()
    test_metering_failure_does_not_take_the_product_down()
    test_kill_switch()
    test_sentry_is_optional_and_scrubs()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
