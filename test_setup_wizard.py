"""
The setup wizard: any organisation sets up its own payment approvals by
answering six questions, with no settings file and no developer.

Why (29 Sep 2026): every client so far needed a hand-written profile, so the
business could only grow as fast as one person could write them. The wizard
has to (a) set up a brand-new NGO that has never been configured, (b) express
the organisations we already have, NEEM included, without losing anything the
six questions don't cover, and (c) refuse, with nothing written, any change
that would strand a waiting request or a person.

Run: python test_setup_wizard.py
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-wizard-")
os.environ["DOCEX_ORG"] = "fresh"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402
import setup_wizard as W  # noqa: E402

ROOT = Path(__file__).parent
PW = "correct-horse-battery"
_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def _snapshot(org: str) -> str:
    db = store.get_store()
    return json.dumps({c: sorted(json.dumps(r, sort_keys=True) for r in db.list(org, c))
                       for c in sorted(db.collections(org))}, sort_keys=True)


def _steps(org: str) -> list[tuple]:
    return [(s.key, s.label, s.department, s.requester_department, s.min_amount, s.can_override,
             s.override_limit) for s in rq.get_workflow(org).steps]


# ─── a brand-new organisation ────────────────────────────────────────────────


def test_a_new_org_starts_from_the_common_setup() -> None:
    print("\nA new organisation: the common NGO setup, ready to confirm")
    a = W.load_answers("fresh")
    check("departments suggested", [d["name"] for d in a["departments"]] ==
          ["Programmes", "Finance", "Admin & HR", "Executive Director"], str(a["departments"]))
    check("the requester's manager approves first", a["first_approver"] == "budget_holder")
    check("Finance checks policy", a["policy_department"] == "finance")
    check("no release authority switched on for them", a["policy_can_release"] is False)
    p = W.preview("fresh", {**a, "org_name": "Hope Clinic Trust"})
    check("the preview is valid", p["ok"], str(p["errors"]))
    words = " → ".join(s["who"] for s in p["route"][0]["steps"])
    check("route in words", words == "The requester's own manager → Finance → Executive Director", words)
    p = W.preview("fresh", a)
    check("it asks for the organisation's name", not p["ok"] and any("name" in e for e in p["errors"]))


def test_a_new_org_sets_itself_up_and_pays_someone() -> None:
    print("\nHope Clinic Trust sets itself up, then a real request goes all the way through")
    a = W.load_answers("fresh")
    a.update(org_name="Hope Clinic Trust", address_lines=["4 Example Road", "Jos"],
             policy_can_release=True, policy_release_limit=200_000,
             signoffs=[{"department": "ed", "from_amount": 1_000_000, "can_release": True, "release_limit": None}],
             quotes_from=500_000, tender_from=5_000_000)
    res = W.apply("fresh", a, actor="admin@hope.example")
    check("saved", res.get("saved") is True)
    check("three steps", [s[0] for s in _steps("fresh")] == ["budget-holder", "finance", "ed"], str(_steps("fresh")))
    check("ED only from ₦1,000,000", _steps("fresh")[2][4] == 1_000_000)
    wf = rq.get_workflow("fresh")
    check("quotes and tender bands", [b.documents for b in wf.documents_by_amount] ==
          [["three_quotes"], ["tender_minutes"]], str(wf.documents_by_amount))
    check("the payment request screens are on", org_config.feature_enabled("fresh", "requisition_attachments"))
    import payment_voucher as pv
    check("letterhead carries their name", pv.get_template("fresh")["letterhead"]["org_name"] == "Hope Clinic Trust")

    # This test ticks documents instead of uploading files; a new org
    # requires real files, which the upload screens cover elsewhere.
    org_config.set_features("fresh", documents_require_files=False)
    for email, name, dept, role in [("nurse@hope.example", "Nurse", "program", "reviewer"),
                                    ("pm@hope.example", "PM", "program", "approver"),
                                    ("fin@hope.example", "Fin", "finance", "approver"),
                                    ("ed@hope.example", "ED", "ed", "approver")]:
        A.create_user(email, name, PW, dept, role, org_id="fresh")
    r = rq.create_requisition("fresh", submitted_by="nurse@hope.example", department="program",
                              vendor_name="Plateau Pharmacy", amount=1_200_000, category="supplies",
                              documents=["memo", "invoice", "three_quotes"])
    for who, dept in [("pm@hope.example", "program"), ("fin@hope.example", "finance"), ("ed@hope.example", "ed")]:
        r = rq.decide("fresh", r.id, decision=rq.Decision.APPROVED, actor=who, department=dept)
    check("manager → Finance → ED → approved", r.status == rq.ReqStatus.APPROVED, r.status.value)
    txn = rq.mark_paid("fresh", r.id, actor="fin@hope.example")
    check("and paid", bool(txn.id))


# ─── organisations already set up another way ────────────────────────────────


def _roundtrip(profile_path: Path, org: str) -> None:
    prof = json.loads(profile_path.read_text())
    prof["org_id"] = org
    prof.pop("admin", None)
    org_config.apply_profile(prof)
    before_wf = rq.get_workflow(org).model_dump()
    before_steps = _steps(org)
    a = W.load_answers(org)
    a["org_name"] = a["org_name"] or "Named"
    p = W.preview(org, a)
    check(f"{profile_path.stem}: its setup reads back as valid answers", p["ok"], str(p["errors"]))
    W.apply(org, a)
    check(f"{profile_path.stem}: the approval route is exactly the same", _steps(org) == before_steps,
          f"{before_steps}\n     → {_steps(org)}")
    after = rq.get_workflow(org).model_dump()
    for field in ("documents_by_category", "allowed_categories", "cc_rules", "required_documents",
                  "max_amount", "duplicate_window_days", "currency"):
        check(f"{profile_path.stem}: {field} untouched", after[field] == before_wf[field],
              f"{before_wf[field]} → {after[field]}")
    check(f"{profile_path.stem}: every document band kept",
          [b["documents"] for b in after["documents_by_amount"]] ==
          [b["documents"] for b in before_wf["documents_by_amount"]],
          f"{before_wf['documents_by_amount']} → {after['documents_by_amount']}")


def test_neem_is_one_set_of_answers() -> None:
    print("\nNEEM's setup, read into the wizard and saved again, is unchanged")
    _roundtrip(ROOT / "profiles" / "neem.json", "neemcopy")
    import departments
    check("NEEM's ED keeps final authority",
          next(d for d in departments.list_departments("neemcopy") if d.key == "ed").is_final_authority)


def test_the_demo_org_is_one_set_of_answers() -> None:
    print("\nThe demo organisation, the same")
    _roundtrip(ROOT / "profiles" / "demo.json", "democopy")


def test_changing_one_answer_changes_only_that() -> None:
    print("\nNEEM decides quotes start at ₦500,000: only the quote band moves")
    a = W.load_answers("neemcopy")
    before = rq.get_workflow("neemcopy").model_dump()
    a["quotes_from"] = 500_000
    W.apply("neemcopy", a)
    after = rq.get_workflow("neemcopy").model_dump()
    q = next(b for b in after["documents_by_amount"] if "three_quotes" in b["documents"])
    check("quotes now from ₦500,000", q["min_amount"] == 500_000, str(q))
    check("the committee band is untouched", any("procurement_committee_recommendation" in b["documents"]
                                                  for b in after["documents_by_amount"]))
    check("steps untouched", after["steps"] == before["steps"])


# ─── refusing a change that would strand someone ─────────────────────────────


def test_it_will_not_strand_a_waiting_request() -> None:
    print("\nRemoving a step with a request waiting on it: refused, nothing written")
    A.create_user("amina@hope.example", "Amina", PW, "admin", "reviewer", org_id="fresh")
    r = rq.create_requisition("fresh", submitted_by="nurse@hope.example", department="program",
                              vendor_name="X", amount=2_000_000, category="supplies",
                              documents=["memo", "invoice", "three_quotes"])
    rq.decide("fresh", r.id, decision=rq.Decision.APPROVED, actor="pm@hope.example", department="program")
    rq.decide("fresh", r.id, decision=rq.Decision.APPROVED, actor="fin@hope.example", department="finance")
    a = W.load_answers("fresh")
    a["signoffs"] = []                                  # remove the ED step, where r is waiting
    snap = _snapshot("fresh")
    try:
        W.apply("fresh", a)
        check("refused", False)
    except W.WizardError as exc:
        check("refused, naming the request", any(r.ref in e for e in exc.errors), str(exc.errors))
    check("nothing written", _snapshot("fresh") == snap)


def test_it_will_not_strand_a_person() -> None:
    print("\nRemoving a department people are in: refused")
    a = W.load_answers("fresh")
    a["departments"] = [d for d in a["departments"] if d["key"] != "admin"]
    p = W.preview("fresh", a)
    check("refused, saying to move them first", not p["ok"] and any("people" in e for e in p["errors"]),
          str(p["errors"]))


def test_plain_mistakes_are_explained() -> None:
    print("\nMistakes an admin could make, each in plain words")
    a = W.load_answers("fresh")
    cases = [
        ({"policy_department": "Procurement"}, "not one of your departments"),
        ({"departments": a["departments"] + [{"name": "Finance"}]}, "Two departments"),
        ({"signoffs": [{"department": "finance", "from_amount": 0}]}, "twice"),
        ({"tender_from": 100, "quotes_from": 500}, "higher than the quotes"),
        ({"signoffs": [{"department": "ed", "from_amount": 5_000_000},
                       {"department": "admin", "from_amount": 1_000}]}, "smallest to largest"),
    ]
    for change, words in cases:
        p = W.preview("fresh", {**a, **change})
        check(f"'{words}'", not p["ok"] and any(words in e for e in p["errors"]), str(p["errors"]))


# ─── the screens' API ────────────────────────────────────────────────────────


def test_only_an_admin_can_save() -> None:
    print("\nThe API: only an admin may open or save the setup")
    from fastapi.testclient import TestClient
    import api.main as m
    A.create_user("boss@hope.example", "Boss", PW, "finance", "admin", org_id="fresh")
    c = TestClient(m.app, raise_server_exceptions=False)

    def h(email):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]}

    r = c.get("/onboarding/answers", headers=h("boss@hope.example"))
    check("answers load", r.status_code == 200 and r.json()["answers"]["org_name"] == "Hope Clinic Trust",
          f"{r.status_code} {r.text[:160]}")
    ans = r.json()["answers"]
    r = c.post("/onboarding/preview", headers=h("boss@hope.example"), json={"answers": ans})
    check("preview", r.status_code == 200 and r.json()["ok"], r.text[:200])
    r = c.post("/onboarding/apply", headers=h("nurse@hope.example"), json={"answers": ans})
    check("a non-admin can't save", r.status_code == 403, str(r.status_code))
    bad = {**ans, "policy_department": "nowhere"}
    r = c.post("/onboarding/apply", headers=h("boss@hope.example"), json={"answers": bad})
    check("a bad answer comes back as 422 with the reasons", r.status_code == 422
          and "nowhere" in json.dumps(r.json()), r.text[:200])
    r = c.post("/onboarding/apply", headers=h("boss@hope.example"), json={"answers": ans})
    check("an admin can save", r.status_code == 200 and r.json()["saved"], r.text[:200])
    org_config.set_features("fresh", setup_wizard=False)
    r = c.get("/onboarding/answers", headers=h("boss@hope.example"))
    check("switched off: not there", r.status_code == 404, str(r.status_code))
    org_config.set_features("fresh", setup_wizard=True)


if __name__ == "__main__":
    print("Setup wizard: six questions, any organisation")
    test_a_new_org_starts_from_the_common_setup()
    test_a_new_org_sets_itself_up_and_pays_someone()
    test_neem_is_one_set_of_answers()
    test_the_demo_org_is_one_set_of_answers()
    test_changing_one_answer_changes_only_that()
    test_it_will_not_strand_a_waiting_request()
    test_it_will_not_strand_a_person()
    test_plain_mistakes_are_explained()
    test_only_an_admin_can_save()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
