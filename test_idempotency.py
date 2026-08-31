"""
Tests for idempotency.py — a retry must never create a second write.

Run: python test_idempotency.py
"""
from __future__ import annotations

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-idem-")
os.environ.setdefault("DOCEX_SECRET", "test-secret-idempotency")

import store  # noqa: E402

# Redirect persistence to a temp dir so the suite never touches real data.
store.set_store(store.JsonFileStore(_TMP))

import idempotency  # noqa: E402

ORG = "test-org"
OTHER_ORG = "other-org"

_passed = 0
_failed = 0


def check(label: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


# ─── no key: guard is a transparent no-op ───────────────────────────────────

def test_without_key_is_noop() -> None:
    print("\nWithout a key the guard does nothing")
    with idempotency.guard(ORG, "op", None) as slot:
        check("not marked as a replay", slot.replayed is False)
        slot.store({"value": 1})

    # A second call with no key runs again — no protection was requested.
    with idempotency.guard(ORG, "op", None) as slot:
        check("second call also runs", slot.replayed is False)

    with idempotency.guard(ORG, "op", "   ") as slot:
        check("whitespace-only key treated as absent", slot.replayed is False)


# ─── first call runs, retry replays ─────────────────────────────────────────

def test_replay_returns_original() -> None:
    print("\nA retry with the same key replays the original result")
    calls = {"n": 0}

    def do_work() -> dict:
        calls["n"] += 1
        return {"ref": "REQ-0001", "attempt": calls["n"]}

    with idempotency.guard(ORG, "requisition.create", "key-a") as slot:
        check("first call is not a replay", slot.replayed is False)
        slot.store(do_work())

    with idempotency.guard(ORG, "requisition.create", "key-a") as slot:
        check("second call is flagged as a replay", slot.replayed is True)
        replayed = slot.result

    check("work ran exactly once", calls["n"] == 1)
    check("replay returns the original record", replayed == {"ref": "REQ-0001", "attempt": 1})


# ─── different keys are independent ─────────────────────────────────────────

def test_distinct_keys_do_not_collide() -> None:
    print("\nDifferent keys are independent writes")
    with idempotency.guard(ORG, "requisition.create", "key-b") as slot:
        slot.store({"ref": "REQ-0002"})

    with idempotency.guard(ORG, "requisition.create", "key-c") as slot:
        check("a different key still runs", slot.replayed is False)
        slot.store({"ref": "REQ-0003"})

    with idempotency.guard(ORG, "requisition.create", "key-b") as slot:
        check("key-b replays its own result", slot.result == {"ref": "REQ-0002"})


# ─── the same key on a different operation is a different write ─────────────

def test_operation_namespacing() -> None:
    print("\nThe same key under a different operation is a separate write")
    with idempotency.guard(ORG, "requisition.create", "shared") as slot:
        slot.store({"kind": "create"})

    with idempotency.guard(ORG, "requisition.pay", "shared") as slot:
        check("pay is not treated as a replay of create", slot.replayed is False)
        slot.store({"kind": "pay"})

    with idempotency.guard(ORG, "requisition.pay", "shared") as slot:
        check("pay replays its own result", slot.result == {"kind": "pay"})

    with idempotency.guard(ORG, "requisition.create", "shared") as slot:
        check("create still replays create", slot.result == {"kind": "create"})


# ─── org isolation ──────────────────────────────────────────────────────────

def test_org_isolation() -> None:
    print("\nOne org's key never resolves to another org's record")
    with idempotency.guard(ORG, "requisition.create", "same-key") as slot:
        slot.store({"org": ORG})

    with idempotency.guard(OTHER_ORG, "requisition.create", "same-key") as slot:
        check("other org is not a replay", slot.replayed is False)
        slot.store({"org": OTHER_ORG})

    with idempotency.guard(ORG, "requisition.create", "same-key") as slot:
        check("first org still sees its own result", slot.result == {"org": ORG})

    with idempotency.guard(OTHER_ORG, "requisition.create", "same-key") as slot:
        check("second org sees its own result", slot.result == {"org": OTHER_ORG})


# ─── concurrent retry is refused, not served half-done ──────────────────────

def test_in_flight_conflict() -> None:
    print("\nA retry while the first call is still running is refused")
    conflicted = False
    with idempotency.guard(ORG, "requisition.create", "key-inflight"):
        try:
            with idempotency.guard(ORG, "requisition.create", "key-inflight"):
                pass
        except idempotency.IdempotencyConflict:
            conflicted = True
    check("concurrent retry raises IdempotencyConflict", conflicted)


# ─── a failed write releases its key ────────────────────────────────────────

def test_failure_releases_key() -> None:
    print("\nA write that raises does not permanently burn its key")
    try:
        with idempotency.guard(ORG, "requisition.create", "key-boom"):
            raise ValueError("bank rejected the transfer")
    except ValueError:
        pass

    with idempotency.guard(ORG, "requisition.create", "key-boom") as slot:
        check("the key is reusable after a failure", slot.replayed is False)
        slot.store({"ref": "REQ-0009"})

    with idempotency.guard(ORG, "requisition.create", "key-boom") as slot:
        check("the successful retry is then recorded", slot.result == {"ref": "REQ-0009"})


# ─── a block that stores nothing does not lock the key ──────────────────────

def test_no_result_does_not_lock() -> None:
    print("\nA block that records no result leaves the key free")
    with idempotency.guard(ORG, "requisition.create", "key-empty"):
        pass

    with idempotency.guard(ORG, "requisition.create", "key-empty") as slot:
        check("key still available", slot.replayed is False)


# ─── forget() drops a key ───────────────────────────────────────────────────

def test_forget() -> None:
    print("\nforget() drops a stored key")
    with idempotency.guard(ORG, "requisition.create", "key-forget") as slot:
        slot.store({"ref": "REQ-0010"})

    check("key exists before forget", idempotency.forget(ORG, "requisition.create", "key-forget"))

    with idempotency.guard(ORG, "requisition.create", "key-forget") as slot:
        check("runs fresh after forget", slot.replayed is False)


def main() -> int:
    print("=" * 62)
    print("idempotency.py — retries must not duplicate financial writes")
    print("=" * 62)

    test_without_key_is_noop()
    test_replay_returns_original()
    test_distinct_keys_do_not_collide()
    test_operation_namespacing()
    test_org_isolation()
    test_in_flight_conflict()
    test_failure_releases_key()
    test_no_result_does_not_lock()
    test_forget()

    print("\n" + "=" * 62)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 62)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
