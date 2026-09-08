"""
Client-profile tests — the "one engine, one config per client" contract.

What these protect:
  * A bad profile fails BEFORE any write (never a half-configured org).
  * Applying a profile is idempotent (re-running changes nothing).
  * Two orgs applied side by side cannot see each other's config or users.
  * The template ships valid, so onboarding never starts from a broken file.

Run: python test_org_config.py
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-orgcfg-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth  # noqa: E402
import departments  # noqa: E402
import org_config as oc  # noqa: E402
import requisitions as rq  # noqa: E402

auth._SECRET_FILE = Path(_TMP) / ".auth_secret"
auth._secret_cache = None

_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def expect_error(label: str, fn) -> None:
    try:
        fn()
        check(label, False)
    except oc.ProfileError:
        check(label, True)


TEMPLATE = Path(__file__).parent / "profiles" / "_template.json"
NEEM = Path(__file__).parent / "profiles" / "neem.json"


def good_profile(org: str = "acme") -> dict:
    p = oc.load_profile(TEMPLATE)
    p["org_id"] = org
    p["admin"]["email"] = f"admin@{org}.org"
    return p


def test_shipped_profiles_are_valid() -> None:
    print("\nShipped profiles validate")
    for path in (TEMPLATE, NEEM):
        rep = oc.validate_profile(oc.load_profile(path))
        check(f"{path.name} has no errors ({rep.errors})", rep.ok)


def test_validation_catches_stuck_payment_causes() -> None:
    print("\nValidation catches the mistakes that strand payments")
    p = good_profile()
    p["workflow"]["steps"][0]["department"] = "legal"          # doesn't exist
    rep = oc.validate_profile(p)
    check("step routed to unknown department is an error",
          any("unknown department 'legal'" in e for e in rep.errors))

    p = good_profile()
    p["state_owners"]["approval"] = "board"
    rep = oc.validate_profile(p)
    check("state owner naming a missing department is an error",
          any("state_owners['approval']" in e for e in rep.errors))

    p = good_profile()
    p["workflow"]["steps"][2]["override_limit"] = 1000           # below min_amount 250000
    rep = oc.validate_profile(p)
    check("override_limit below min_amount is an error",
          any("override_limit" in e for e in rep.errors))

    p = good_profile()
    p["grants"][0]["end_date"] = "2025-01-01"                    # before start
    rep = oc.validate_profile(p)
    check("grant ending before it starts is an error",
          any("ends before it starts" in e for e in rep.errors))

    p = good_profile()
    del p["org_id"]
    check("missing org_id is an error", not oc.validate_profile(p).ok)


def test_invalid_profile_writes_nothing() -> None:
    print("\nAn invalid profile leaves the org untouched")
    p = good_profile("untouched")
    p["workflow"]["steps"][0]["department"] = "nowhere"
    expect_error("apply raises ProfileError", lambda: oc.apply_profile(p))
    check("no departments were written",
          store.get_store().get("untouched", "config", "departments") is None)
    check("no admin was created", auth.get_by_email("admin@untouched.org", "untouched") is None)


def test_apply_then_describe_round_trips() -> None:
    print("\nApply writes every section; describe reads it back")
    p = good_profile("acme")
    res = oc.apply_profile(p)
    check("4 departments written", res.departments == 4)
    check("workflow written", res.workflow)
    check("1 grant added", res.grants_added == 1)
    check("admin created", res.admin_created)

    live = oc.describe_org("acme")
    check("departments round-trip", [d["key"] for d in live["departments"]]
          == [d["key"] for d in p["departments"]])
    check("workflow steps round-trip", [s["key"] for s in live["workflow"]["steps"]]
          == [s["key"] for s in p["workflow"]["steps"]])
    check("max_amount round-trips", live["workflow"]["max_amount"] == p["workflow"]["max_amount"])
    check("grant round-trips", live["grants"][0]["project_code"] == "GRANT-2026-A")
    check("one user exists", live["users"] == 1)
    check("features round-trip", live["features"] == p["features"])

    u = auth.get_by_email("admin@acme.org", "acme")
    check("admin has admin role", u is not None and u.role == "admin")
    check("admin can authenticate", auth.authenticate("admin@acme.org",
                                                      p["admin"]["password"], "acme").id == u.id)

    stored = store.get_store().get("acme", "config", "profile") or {}
    check("password is NOT persisted in the stored profile",
          "admin" not in (stored.get("profile") or {}))


def test_reapply_is_idempotent() -> None:
    print("\nRe-applying the same profile changes nothing")
    p = good_profile("acme")
    before = json.dumps(oc.describe_org("acme"), sort_keys=True, default=str)
    res = oc.apply_profile(p)
    after = json.dumps(oc.describe_org("acme"), sort_keys=True, default=str)
    check("grant not duplicated", res.grants_added == 0 and res.grants_skipped == 1)
    check("admin not recreated", res.admin_existing and not res.admin_created)
    check("live config identical", before == after)
    check("still exactly one user", len(auth.list_public("acme")) == 1)


def test_partial_profile_only_touches_its_sections() -> None:
    print("\nA partial profile updates only what it names")
    oc.apply_profile({"org_id": "acme", "workflow": {"max_amount": 999}})
    live = oc.describe_org("acme")
    check("max_amount updated", live["workflow"]["max_amount"] == 999)
    check("steps preserved", len(live["workflow"]["steps"]) == 3)
    check("departments preserved", len(live["departments"]) == 4)
    check("user preserved", live["users"] == 1)


def test_orgs_are_isolated() -> None:
    print("\nTwo clients on one engine cannot see each other")
    beta = good_profile("beta")
    beta["departments"] = [
        {"key": "ops", "name": "Operations", "order": 10},
        {"key": "finance", "name": "Finance", "order": 20, "is_final_authority": True},
    ]
    beta["state_owners"] = {"submitted": "ops", "finance_review": "finance", "approval": "finance"}
    beta["workflow"]["steps"] = [
        {"key": "finance", "label": "Finance", "department": "finance",
         "can_override": True, "override_limit": 100000},
    ]
    beta["workflow"]["max_amount"] = 100000
    beta["admin"]["department"] = "finance"
    oc.apply_profile(beta)

    check("beta has 2 departments", departments.keys("beta") == ["ops", "finance"])
    check("acme still has 4", len(departments.keys("acme")) == 4)
    check("beta ceiling is 100k", rq.get_workflow("beta").max_amount == 100000)
    check("acme ceiling unchanged", rq.get_workflow("acme").max_amount == 999)
    check("beta admin invisible to acme", auth.get_by_email("admin@beta.org", "acme") is None)
    check("acme admin invisible to beta", auth.get_by_email("admin@acme.org", "beta") is None)

    tok = auth.issue_token(auth.get_by_email("admin@beta.org", "beta"), org_id="beta")
    check("token carries its org", auth.token_org(tok) == "beta")
    check("token resolves in the right org", auth.verify_token(tok).email == "admin@beta.org")


def test_client_config_drives_what_each_client_sees() -> None:
    print("\nclient_config() is what makes one engine look like many products")
    # This is the contract the frontend navigation depends on. If it breaks,
    # a client sees a menu item for something they never bought.
    acme = oc.client_config("acme")
    check("modules default to all three when unset",
          sorted(acme["modules"]) == ["compliance", "knowledge", "screening"])
    check("features are returned", isinstance(acme["features"], dict))

    # An org with no profile at all must behave exactly as before this existed:
    # every module, no features.
    fresh = oc.client_config("never-configured")
    check("unconfigured org gets every module", len(fresh["modules"]) == 3)
    check("unconfigured org gets no features", fresh["features"] == {})

    # Selling one module only.
    oc.apply_profile({"org_id": "acme", "modules": ["compliance"]})
    check("modules narrow to what was bought",
          oc.client_config("acme")["modules"] == ["compliance"])
    check("beta is unaffected", len(oc.client_config("beta")["modules"]) == 3)

    # Modules must survive a later profile apply that doesn't mention them —
    # otherwise a workflow tweak would silently hand the client back modules
    # they never paid for.
    oc.apply_profile({"org_id": "acme", "workflow": {"max_amount": 12345}})
    check("modules survive an unrelated apply",
          oc.client_config("acme")["modules"] == ["compliance"])

    rep = oc.validate_profile({"org_id": "acme", "modules": ["compliance", "wat"]})
    check("unknown module is rejected", any("Unknown module" in e for e in rep.errors))
    rep = oc.validate_profile({"org_id": "acme", "modules": []})
    check("empty module list is rejected", not rep.ok)


def test_two_clients_see_different_systems() -> None:
    print("\nTwo clients, one engine, different products")
    # The whole model in one test: EVA gets payroll, NEEM does not, and
    # neither can tell the other's capability exists.
    oc.apply_profile({
        "org_id": "neemish",
        "modules": ["compliance"],
        "features": {"tin_verification": True, "payroll": False},
    })
    oc.apply_profile({
        "org_id": "evaish",
        "modules": ["compliance", "knowledge"],
        "features": {"payroll": True, "doa_matrix": True, "tin_verification": False},
    })
    n, e = oc.client_config("neemish"), oc.client_config("evaish")

    check("NEEM-ish sees one module", n["modules"] == ["compliance"])
    check("EVA-ish sees two", e["modules"] == ["compliance", "knowledge"])
    check("NEEM-ish has TIN", n["features"]["tin_verification"] is True)
    check("NEEM-ish does NOT have payroll", n["features"].get("payroll") is not True)
    check("EVA-ish has payroll", e["features"]["payroll"] is True)
    check("EVA-ish does NOT have TIN", e["features"].get("tin_verification") is not True)
    check("flags agree with feature_enabled()",
          oc.feature_enabled("evaish", "payroll") is True
          and oc.feature_enabled("neemish", "payroll") is False)


def test_feature_flags() -> None:
    print("\nFeature flags gate per-client behaviour")
    check("acme kobo off", oc.feature_enabled("acme", "kobo_sync") is False)
    check("unknown flag defaults False", oc.feature_enabled("acme", "made_up") is False)
    check("unknown flag honours explicit default", oc.feature_enabled("acme", "made_up", True) is True)
    oc.apply_profile({"org_id": "acme", "features": {"kobo_sync": True}})
    check("flag flips on after apply", oc.feature_enabled("acme", "kobo_sync") is True)
    check("flag is per-org", oc.feature_enabled("beta", "kobo_sync") is False)


def test_no_workflow_field_is_silently_dropped() -> None:
    """The bridge from profile to engine must carry EVERY workflow field.

    Written after `documents_by_category` was missing from apply_profile for
    weeks. The profile carried nineteen document packs, the engine supported
    them, and the mapping between the two quietly omitted the field — so NEEM
    would have been asked for the same two documents on a ₦40,000
    reimbursement as on a ₦3,000,000 equipment purchase.

    Nothing errored, and nothing could: an unmapped field just takes its
    default. That is the failure mode of "one engine, one config file" and it
    deserves a test that fails for the NEXT field somebody forgets, not only
    for this one.
    """
    print("\nEvery workflow field a profile can set must reach the engine")
    import re
    import requisitions as rq

    engine_fields = set(rq.RequisitionWorkflow.model_fields.keys())
    src = (Path(__file__).parent / "org_config.py").read_text()
    block = src[src.index("new = requisitions.RequisitionWorkflow("):]
    block = block[:block.index(")\n")]
    mapped = set(re.findall(r"^\s*(\w+)=", block, re.M))

    # Set by the engine itself, never by a profile.
    derived = {"org_id", "updated_at"}
    dropped = engine_fields - mapped - derived
    if dropped:
        print(f"       dropped: {sorted(dropped)}")
    check("no workflow field is dropped by apply_profile", not dropped)


def test_document_packs_reach_the_engine() -> None:
    """The specific case, end to end: packs in a profile become packs in use."""
    print("\nPer-category document packs survive apply()")
    import requisitions as rq

    org = "packtest"
    oc.apply_profile({
        "org_id": org,
        "name": "Pack Test",
        "departments": [{"key": "finance", "name": "Finance"}],
        "state_owners": {"approval": "finance"},
        "workflow": {
            "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
            "required_documents": ["memo", "invoice"],
            "documents_by_category": {
                "equipment": ["memo", "invoice", "purchase_order", "grn"],
                "advance": ["memo", "advance_request_form"],
            },
        },
    })

    wf = rq.get_workflow(org)
    check("the packs were stored", len(wf.documents_by_category) == 2)
    check("equipment needs a goods-received note",
          "grn" in rq.required_documents_for(wf, "equipment"))
    check("an advance does NOT need a GRN",
          "grn" not in rq.required_documents_for(wf, "advance"))
    check("an unlisted category falls back to the org-wide list",
          sorted(rq.required_documents_for(wf, "stationery")) == ["invoice", "memo"])
    # An ignored check is worse than no check: asking for a purchase order on a
    # ₦40,000 reimbursement is how people learn to click past the warning.


def main() -> int:
    print("=" * 64)
    print("Client profiles — one engine, one config per organisation")
    print("=" * 64)
    test_shipped_profiles_are_valid()
    test_validation_catches_stuck_payment_causes()
    test_invalid_profile_writes_nothing()
    test_apply_then_describe_round_trips()
    test_reapply_is_idempotent()
    test_partial_profile_only_touches_its_sections()
    test_orgs_are_isolated()
    test_client_config_drives_what_each_client_sees()
    test_two_clients_see_different_systems()
    test_feature_flags()
    test_no_workflow_field_is_silently_dropped()
    test_document_packs_reach_the_engine()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
