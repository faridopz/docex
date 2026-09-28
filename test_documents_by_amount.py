"""
The documents a payment needs can depend on how much it is — one quote for
a small purchase, three above a threshold, a tender above a higher one.

Research (28 Sep 2026: HIAS, Twaweza, ActionAid procurement policies;
USAID 2 CFR 200.320) and NEEM's own signed Procurement Policy (p6) all tie
the number of quotations to value bands. DOCex could only vary documents by
category, so "three quotes from N200,001" could not be expressed: either
every purchase asked for three quotes, or none did — and split purchases to
stay under a band are the classic audit finding.

`documents_by_amount` adds documents on top of the category pack once the
amount reaches a band, optionally only for some categories (a per diem is
not procured, so it never needs quotes).

Run: python test_documents_by_amount.py
"""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-docamount-")
os.environ["DOCEX_ORG"] = "acme"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


PROFILE = {
    "org_id": "acme", "currency": "NGN",
    "departments": [{"key": "program", "name": "Programmes"}, {"key": "finance", "name": "Finance"}],
    "workflow": {
        "max_amount": 100_000_000,
        "steps": [{"key": "finance", "label": "Finance review", "department": "finance"}],
        "required_documents": ["memo", "invoice"],
        "documents_by_category": {"dsa": ["memo", "travel_approval_form"]},
        "documents_by_amount": [
            {"min_amount": 200_001, "documents": ["three_quotes"], "categories": ["equipment", "venue"],
             "label": "3 quotations from N200,001"},
            {"min_amount": 7_000_001, "documents": ["tender_minutes"], "categories": ["equipment", "venue"],
             "label": "Tender above N7,000,000"},
        ],
    },
}


def test_the_bands() -> None:
    print("\nDocuments follow the amount, on top of the category pack")
    wf = rq.get_workflow("acme")
    small = rq.required_documents_for(wf, "equipment", 150_000)
    mid = rq.required_documents_for(wf, "equipment", 850_000)
    big = rq.required_documents_for(wf, "equipment", 9_000_000)
    check("small purchase: memo + invoice only", small == ["memo", "invoice"], str(small))
    check("from N200,001: three quotes added", mid == ["memo", "invoice", "three_quotes"], str(mid))
    check("above N7m: quotes and tender minutes", big == ["memo", "invoice", "three_quotes", "tender_minutes"], str(big))
    dsa = rq.required_documents_for(wf, "dsa", 900_000)
    check("a DSA is never procured: no quotes, whatever the amount", "three_quotes" not in dsa, str(dsa))
    check("exactly at the band edge counts", "three_quotes" in rq.required_documents_for(wf, "venue", 200_001))
    check("one naira under does not", "three_quotes" not in rq.required_documents_for(wf, "venue", 200_000))
    check("category-only callers still work (no amount)", rq.required_documents_for(wf, "equipment") == ["memo", "invoice"])


def test_the_check_uses_the_amount() -> None:
    print("\nThe documents check on a real request asks for the band's documents")
    r = rq.create_requisition("acme", submitted_by="a@acme.org", department="program",
                              vendor_name="Office Mart", amount=850_000, category="equipment",
                              documents=["memo", "invoice"])
    docs = next(c for c in r.checks if c.code == "DOCS_COMPLETE")
    check("fails without the quotes", docs.result == rq.CheckResult.FAIL, docs.message)
    check("and names them", "three quotes" in docs.message.lower() or "three_quotes" in docs.message.lower(), docs.message)


def test_workflow_endpoint_carries_the_bands() -> None:
    print("\nThe form can show the bands before anything is sent")
    from fastapi.testclient import TestClient
    import api.main as m
    A.create_user("a@acme.org", "A", "correct-horse-battery", "program", "reviewer", org_id="acme")
    c = TestClient(m.app, raise_server_exceptions=False)
    tok = c.post("/auth/login", json={"email": "a@acme.org", "password": "correct-horse-battery"}).json()["token"]
    wf = c.get("/requisitions/workflow", headers={"Authorization": f"Bearer {tok}"}).json()
    check("documents_by_amount returned", len(wf.get("documents_by_amount") or []) == 2, str(wf.get("documents_by_amount")))


def test_a_band_without_documents_is_refused() -> None:
    print("\nA band that lists no documents is a mistake, not a rule")
    bad = copy.deepcopy(PROFILE)
    bad["workflow"]["documents_by_amount"] = [{"min_amount": 1000, "documents": []}]
    rep = org_config.validate_profile(bad)
    check("rejected", not rep.ok and any("documents_by_amount" in e for e in rep.errors), "; ".join(rep.errors))


if __name__ == "__main__":
    print("Documents by amount (quotation bands)")
    org_config.apply_profile(copy.deepcopy(PROFILE))
    test_the_bands()
    test_the_check_uses_the_amount()
    test_workflow_endpoint_carries_the_bands()
    test_a_band_without_documents_is_refused()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
