"""
A sign-in (or an emailed approval link) from one organisation never opens
another organisation's data.

Each client runs its own instance, and the instance's org comes from
DOCEX_ORG. The session token records the org it was issued for, but nothing
compared the two. Two instances that share a database (one Supabase project)
and a signing secret would therefore let an EVA user's token into NEEM's
instance, where it resolved to NEEM data with the EVA user's role.

Run: python test_token_org_guard.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-orgguard-")
os.environ["DOCEX_ORG"] = "neem"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import approval_tokens  # noqa: E402

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


def test_engine_refuses_a_token_from_another_org() -> None:
    print("\nauth.verify_token: an EVA token presented to the NEEM instance is refused")
    eva = A.create_user("amara@eva.org", "Amara", PW, "finance", "admin", org_id="eva")
    tok = A.issue_token(eva, org_id="eva")
    try:
        A.verify_token(tok)
        check("refused", False, "an EVA session was accepted by NEEM's instance")
    except A.AuthError:
        check("refused", True)


def test_own_org_and_legacy_tokens_still_work() -> None:
    print("\nNEEM's own tokens, and old tokens with no org claim, still sign in")
    u = A.create_user("amina@neem.org", "Amina", PW, "program", "reviewer", org_id="neem")
    check("NEEM token accepted", A.verify_token(A.issue_token(u, org_id="neem")).id == u.id)
    # A token minted before the org claim existed: same shape, no "org".
    import json
    body = A._b64(json.dumps({"uid": u.id, "iat": 0.0, "exp": 2**31}, separators=(",", ":")).encode())
    import hashlib
    import hmac
    sig = A._b64(hmac.new(A._secret(), body.encode(), hashlib.sha256).digest())
    check("pre-upgrade token accepted", A.verify_token(f"{body}.{sig}").id == u.id)


def test_http_refuses_the_foreign_token() -> None:
    print("\nHTTP: the foreign token gets 401 on an org-scoped endpoint")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    eva = A.get_by_email("amara@eva.org", "eva")
    r = c.get("/requisitions", headers={"Authorization": f"Bearer {A.issue_token(eva, org_id='eva')}"})
    check("401", r.status_code == 401, f"{r.status_code} {r.text[:120]}")


def test_emailed_approval_link_for_another_org_is_refused() -> None:
    print("\nAn approval link minted for EVA does nothing on NEEM's instance")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    link = approval_tokens.make_token("REQ-X", "finance", "amara@eva.org", org="eva", kind="requisition")
    r = c.get(f"/requisitions/approve/verify/{link}")
    check("refused as invalid, not looked up", r.status_code == 400, f"{r.status_code} {r.text[:120]}")


if __name__ == "__main__":
    print("Tokens are bound to the organisation that issued them")
    test_engine_refuses_a_token_from_another_org()
    test_own_org_and_legacy_tokens_still_work()
    test_http_refuses_the_foreign_token()
    test_emailed_approval_link_for_another_org_is_refused()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
