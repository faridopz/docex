"""
The in-app onboarding wizard, end to end, through the real HTTP API.

This is the backend for Task #9/#10: an admin configures departments and an
approval chain themselves, inside DOCex, instead of a developer hand-editing
profiles/<client>.json. The two things worth proving are not "does the JSON
serialise" — they are:

  1. Detection is honest. A brand-new org must report unconfigured (nobody
     has saved anything yet), even though departments.load()/
     requisitions.get_workflow() both quietly return in-memory defaults so
     the rest of the app never 500s on a fresh store. If /onboarding/status
     used those getters directly instead of has_registry_configured() /
     has_workflow_configured(), every org would look "already set up" from
     the moment the process started, and the wizard would never show.

  2. Setup is atomic in the way that matters for a stuck-payment risk class:
     a bad workflow (unknown department, min_amount below override_limit,
     etc.) must not leave the org half-configured with no way to tell.
     validate_workflow() already guards the live-edit path
     (PUT /requisitions/workflow) from a prior session's work; this proves
     the wizard's one-call setup hits the exact same guard and reports which
     half succeeded via `partial`.

Run: python test_onboarding.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-onboarding-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as auth_mod  # noqa: E402

auth_mod._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth_mod._secret_cache = None

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402
import departments  # noqa: E402
import requisitions as rq  # noqa: E402
from api.context import default_org  # noqa: E402

client = TestClient(m.app)
ORG = default_org()

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _register(email: str, name: str, role: str, department: str,
              headers: dict | None = None) -> dict:
    r = client.post("/auth/register", headers=headers or {}, json={
        "email": email, "name": name, "password": "correct-horse-battery",
        "department": department, "role": role})
    if r.status_code >= 400:
        raise AssertionError(f"register {email}: {r.status_code} {r.text[:300]}")
    return r.json()


def _login(email: str) -> dict:
    r = client.post("/auth/login", json={"email": email,
                                         "password": "correct-horse-battery"})
    if r.status_code >= 400:
        raise AssertionError(f"login {email}: {r.status_code} {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


# ─── tests ──────────────────────────────────────────────────────────────────


def test_signed_out_gets_nothing() -> None:
    print("\nA signed-out caller reaches neither endpoint")
    check("GET /onboarding/status → 401", client.get("/onboarding/status").status_code == 401)
    check("POST /onboarding/setup → 401",
          client.post("/onboarding/setup", json={}).status_code == 401)


def test_brand_new_org_reports_unconfigured(admin: dict) -> None:
    print("\nA fresh org reports unconfigured, not the unpersisted defaults")
    r = client.get("/onboarding/status", headers=admin)
    check("status 200", r.status_code == 200)
    body = r.json()
    check("configured is False", body["configured"] is False, str(body))
    check("departments_configured is False", body["departments_configured"] is False)
    check("workflow_configured is False", body["workflow_configured"] is False)
    # The raw engine functions must still work (unpersisted fallback) — this
    # confirms status is reading a DIFFERENT signal than get_workflow()/load().
    check("has_registry_configured() agrees", departments.has_registry_configured(ORG) is False)
    check("has_workflow_configured() agrees", rq.has_workflow_configured(ORG) is False)
    check("load() still returns a usable default", len(departments.load(ORG).departments) > 0)
    check("get_workflow() still returns a usable default", len(rq.get_workflow(ORG).steps) > 0)


def test_non_admin_cannot_setup(reviewer: dict) -> None:
    print("\nA non-admin cannot run setup")
    r = client.post("/onboarding/setup", headers=reviewer, json={
        "currency": "NGN",
        "departments": [{"name": "Finance"}],
        "workflow_size": "small",
    })
    check("reviewer → 403", r.status_code == 403, f"got {r.status_code}: {r.text[:200]}")


def test_bad_custom_workflow_reports_partial(admin: dict) -> None:
    print("\nAn invalid custom workflow leaves departments saved and says so")
    r = client.post("/onboarding/setup", headers=admin, json={
        "currency": "NGN",
        "departments": [{"name": "Finance", "key": "finance"},
                        {"name": "Executive Director", "key": "ed", "is_final_authority": True}],
        "workflow_size": "custom",
        "custom_steps": [
            {"label": "Finance Review", "department": "finance", "min_amount": 0},
            # references a department that doesn't exist in this submission
            {"label": "Legal Review", "department": "legal", "min_amount": 0},
        ],
    })
    check("setup 200 (reports failure in body, not an HTTP error)", r.status_code == 200,
          f"got {r.status_code}: {r.text[:300]}")
    body = r.json()
    check("ok is False", body["ok"] is False, str(body))
    check("partial is True (departments did save)", body["partial"] is True, str(body))
    check("error mentions the bad department", "legal" in (body.get("error") or ""), str(body))
    check("departments really did persist", departments.has_registry_configured(ORG) is True)
    check("workflow did NOT persist", rq.has_workflow_configured(ORG) is False)

    status = client.get("/onboarding/status", headers=admin).json()
    check("status reflects the partial state", status["departments_configured"] is True
          and status["workflow_configured"] is False, str(status))


def test_successful_setup_with_a_preset(admin: dict) -> None:
    print("\nA full, valid setup using a preset workflow size")
    r = client.post("/onboarding/setup", headers=admin, json={
        "currency": "NGN",
        "departments": [
            {"name": "Program"}, {"name": "Compliance"},
            {"name": "Finance"}, {"name": "Management", "is_final_authority": True},
        ],
        "workflow_size": "medium",
        "max_amount": 5_000_000,
        "allowed_categories": ["travel", "supplies"],
        "required_documents": ["receipt"],
    })
    check("setup 200", r.status_code == 200, r.text[:300])
    body = r.json()
    check("ok is True", body["ok"] is True, str(body))
    check("partial is False", body["partial"] is False)
    check("4 departments reported", body["departments"] == 4, str(body))
    check("steps reported > 0", body["steps"] > 0, str(body))

    status = client.get("/onboarding/status", headers=admin).json()
    check("status now fully configured", status["configured"] is True, str(status))

    wf = rq.get_workflow(ORG)
    check("workflow currency applied", wf.currency == "NGN")
    check("max_amount applied", wf.max_amount == 5_000_000)
    check("allowed_categories applied", set(wf.allowed_categories) == {"travel", "supplies"})


def test_rerunning_setup_is_safe(admin: dict) -> None:
    print("\nRe-running setup overwrites cleanly rather than corrupting state")
    r = client.post("/onboarding/setup", headers=admin, json={
        "currency": "NGN",
        "departments": [{"name": "Finance"}, {"name": "Director", "is_final_authority": True}],
        "workflow_size": "small",
    })
    check("re-run 200 and ok", r.status_code == 200 and r.json()["ok"] is True, r.text[:300])
    check("department count now reflects the new submission",
          len(departments.load(ORG).departments) == 2)


def test_empty_departments_rejected(admin: dict) -> None:
    print("\nSetup refuses an empty department list outright")
    r = client.post("/onboarding/setup", headers=admin, json={
        "currency": "NGN", "departments": [], "workflow_size": "small",
    })
    check("422 on empty departments", r.status_code == 422, f"got {r.status_code}")


def test_duplicate_department_keys_rejected(admin: dict) -> None:
    print("\nSetup refuses two departments that collapse to the same key")
    r = client.post("/onboarding/setup", headers=admin, json={
        "currency": "NGN",
        "departments": [{"name": "Finance"}, {"name": "finance"}],
        "workflow_size": "small",
    })
    check("422 on duplicate department key", r.status_code == 422, f"got {r.status_code}")


def main() -> int:
    print("=" * 68)
    print("Onboarding wizard backend — through the API")
    print("=" * 68)

    _register("admin@org", "Admin", "admin", "finance")   # bootstraps the instance
    admin = _login("admin@org")
    _register("reviewer@org", "Reviewer", "reviewer", "program", headers=admin)
    reviewer = _login("reviewer@org")

    test_signed_out_gets_nothing()
    test_brand_new_org_reports_unconfigured(admin)
    test_non_admin_cannot_setup(reviewer)
    test_bad_custom_workflow_reports_partial(admin)
    test_successful_setup_with_a_preset(admin)
    test_rerunning_setup_is_safe(admin)
    test_empty_departments_rejected(admin)
    test_duplicate_department_keys_rejected(admin)

    print("\n" + "=" * 68)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 68)
    return 1 if _failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
