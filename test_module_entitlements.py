"""
A module the organisation hasn't switched on is refused by the server, not
just hidden in the menu.

Modules (compliance, screening, knowledge) were enforced only by the
navigation. NEEM has compliance only, yet any NEEM user could call the
screening and knowledge endpoints directly — the ones that spend model
credit on every call.

Run: python test_module_entitlements.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-modules-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402

_passed = _failed = 0
PW = "correct-horse-battery"


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    c = TestClient(m.app, raise_server_exceptions=False)
    if not A.get_by_email("u@acme.org", "acme"):
        A.create_user("u@acme.org", "U", PW, "program", "reviewer", org_id="acme")
    tok = c.post("/auth/login", json={"email": "u@acme.org", "password": PW}).json()["token"]
    return c, {"Authorization": f"Bearer {tok}"}


def test_modules_not_bought_are_refused() -> None:
    print("\nCompliance only: screening and knowledge endpoints answer 403")
    org_config.set_modules("acme", ["compliance"])
    c, H = _client()
    r = c.post("/extract/single", headers=H, data={"questions": "[]"},
               files={"documents": ("a.txt", b"hello", "text/plain")})
    check("screening refused", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    check("says it isn't part of the plan, and who to contact",
          "plan" in r.text.lower() and "founder@docex.app" in r.text, r.text[:200])
    check("machine-readable flag for the frontend", r.json().get("module_not_enabled") == "screening", r.text[:200])
    r = c.post("/draft-followups", headers=H, json={})
    check("follow-up drafting (screening) refused", r.status_code == 403, str(r.status_code))
    r = c.get("/knowledge/decks", headers=H)
    check("knowledge refused", r.status_code == 403, f"{r.status_code} {r.text[:120]}")


def test_the_module_they_have_still_works() -> None:
    print("\nCompliance still answers")
    c, H = _client()
    r = c.get("/requisitions", headers=H)
    check("requisitions 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")


def test_switching_a_module_on_opens_it() -> None:
    print("\nModule switched on: its endpoints answer again")
    org_config.set_modules("acme", ["compliance", "knowledge"])
    c, H = _client()
    r = c.get("/knowledge/decks", headers=H)
    check("knowledge no longer refused", r.status_code != 403, f"{r.status_code} {r.text[:120]}")


def test_an_org_never_configured_keeps_everything() -> None:
    print("\nAn org with no modules ever set keeps every module (unchanged behaviour)")
    store.get_store().delete("acme", org_config._CONFIG, org_config._FEATURES_ID)
    c, H = _client()
    r = c.get("/knowledge/decks", headers=H)
    check("knowledge not refused", r.status_code != 403, str(r.status_code))


if __name__ == "__main__":
    print("Modules are enforced by the server")
    test_modules_not_bought_are_refused()
    test_the_module_they_have_still_works()
    test_switching_a_module_on_opens_it()
    test_an_org_never_configured_keeps_everything()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
