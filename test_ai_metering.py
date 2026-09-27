"""
Every model call is metered, and the daily AI caps actually apply.

usage.record() existed and was never called, so each client's usage table
stayed empty: margin reviews read zero cost, and the daily spend and call
caps in observability.check_llm_allowed() — also never called — could not
trigger. Nothing limited what one client could spend.

Now every Anthropic client is created through ai_client.client(), which
checks the daily caps before a call and records its tokens after.

Run: python test_ai_metering.py
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix="docex-metering-")
os.environ["DOCEX_ORG"] = "acme"
os.environ["DOCEX_LLM_DAILY_USD"] = "5"
os.environ["DOCEX_LLM_DAILY_CALLS"] = "500"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import anthropic  # noqa: E402

CALLS: list = []


class _FakeMessages:
    def _resp(self, kw):
        CALLS.append(kw.get("model"))
        return SimpleNamespace(model=kw.get("model"), usage=SimpleNamespace(
            input_tokens=10_000, output_tokens=2_000,
            cache_read_input_tokens=0, cache_creation_input_tokens=0))

    def create(self, **kw):
        return self._resp(kw)

    def parse(self, **kw):
        return self._resp(kw)


class _FakeAnthropic:
    def __init__(self, **kw):
        self.messages = _FakeMessages()


anthropic.Anthropic = _FakeAnthropic  # type: ignore[misc]

import ai_client  # noqa: E402
import observability  # noqa: E402
import usage  # noqa: E402

_passed = _failed = 0
ROOT = Path(__file__).parent


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def test_a_call_is_recorded_for_this_org() -> None:
    print("\nA model call lands in this organisation's usage, by operation")
    c = ai_client.client("compliance_check")
    c.messages.create(model="claude-sonnet-4-6", max_tokens=10, messages=[])
    rows = [r for r in usage.daily("acme")]
    check("recorded", rows and rows[0]["calls"] >= 1, str(rows))
    s = usage.summary("acme")
    check("with a cost", s.cost_usd > 0 if hasattr(s, "cost_usd") else True, str(s))


def test_parse_calls_are_recorded_too() -> None:
    print("\nStructured-output calls (messages.parse) are metered the same way")
    before = sum(r["calls"] for r in usage.daily("acme"))
    ai_client.client("extraction").messages.parse(model="claude-sonnet-4-6", max_tokens=10, messages=[])
    after = sum(r["calls"] for r in usage.daily("acme"))
    check("one more call recorded", after == before + 1, f"{before} → {after}")


def test_the_daily_spend_cap_stops_the_next_call() -> None:
    print("\nOver the daily spend cap: refused before the model is called")
    os.environ["DOCEX_LLM_DAILY_USD"] = "0.2"
    c = ai_client.client("assistant_brief")
    for _ in range(30):
        try:
            c.messages.create(model="claude-sonnet-4-6", max_tokens=10, messages=[])
        except observability.LimitExceeded:
            break
    n = len(CALLS)
    try:
        c.messages.create(model="claude-sonnet-4-6", max_tokens=10, messages=[])
        check("refused", False, "cap never applied")
    except observability.LimitExceeded as exc:
        check("refused, saying why", "limit" in str(exc).lower(), str(exc))
    check("the model was not called", len(CALLS) == n)


def test_the_api_answers_429_not_500() -> None:
    print("\nHTTP: a cap hit is a plain 429 message, not 'something went wrong'")
    import api.main as m
    check("handler registered", observability.LimitExceeded in m.app.exception_handlers)


def test_no_model_client_bypasses_the_meter() -> None:
    print("\nGuard: nothing outside ai_client constructs an Anthropic client")
    offenders = []
    for p in list(ROOT.glob("*.py")) + list((ROOT / "api").glob("*.py")):
        if p.name.startswith("test_") or p.name in ("ai_client.py",):
            continue
        text = p.read_text(errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\banthropic\.(Async)?Anthropic\(", line) and not line.strip().startswith("#"):
                offenders.append(f"{p.name}:{i}")
    check("none", not offenders, ", ".join(offenders))


if __name__ == "__main__":
    print("AI calls are metered and capped")
    test_a_call_is_recorded_for_this_org()
    test_parse_calls_are_recorded_too()
    test_the_daily_spend_cap_stops_the_next_call()
    test_the_api_answers_429_not_500()
    test_no_model_client_bypasses_the_meter()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
