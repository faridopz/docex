"""
WO-44 — the documents a payment needs are the documents the submitter is
asked for, and "provided" means a file, not a tick.

Found by using the system end to end: the form asked for the org-wide list
(memo, invoice) while the engine enforced the category's pack (memo,
invoice, payment sheet, attendance list), so a correctly filled request was
blocked the moment it was submitted. And a ticked label satisfied the check
with no file behind it, while an attached file without a tick did not.

Two organisations, deliberately different, so nothing here is one client's
process: "packs" has per-category document packs and requires real files;
"simple" has one org-wide list and still works on ticks.

Run: python test_requisition_documents.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-docs-")
os.environ["DOCEX_ORG"] = "packs"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import attachments  # noqa: E402

# Uploads go to a temp folder, never the repo — as test_requisition_attachments
# already does. Without this the HTTP test wrote files into the working tree.
attachments.set_backend(attachments.LocalDiskAttachmentBackend(Path(_TMP) / "files"))

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


def _setup_orgs() -> None:
    packs = rq.get_workflow("packs")
    packs.required_documents = ["memo", "invoice"]
    packs.documents_by_category = {"workshop": ["memo", "payment_sheet", "attendance_list"]}
    rq.set_workflow("packs", packs)
    org_config.set_features("packs", requisition_attachments=True, documents_require_files=True)

    simple = rq.get_workflow("simple")
    simple.required_documents = ["invoice"]
    simple.documents_by_category = {}
    rq.set_workflow("simple", simple)
    org_config.set_features("simple", requisition_attachments=True)


def _docs(req: rq.Requisition) -> rq.PolicyCheck:
    return next(c for c in req.checks if c.code == "DOCS_COMPLETE")


def _attach(org, req, doc_type="", name="file.pdf"):
    return rq.add_attachment(org, req.id, actor="amina@t", filename=name,
                             content_type="application/pdf", size=10,
                             storage_key=f"k/{name}", document_type=doc_type)


def test_a_tick_is_not_a_document_when_the_org_requires_files() -> None:
    print("\nFiles-required org: ticking a label proves nothing")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="workshop",
                                documents=["memo", "payment_sheet", "attendance_list"])
    check("all three ticked, no files ⇒ still blocked", _docs(req).result == rq.CheckResult.FAIL,
          _docs(req).message)


def test_attaching_the_file_is_what_provides_the_document() -> None:
    print("\nFiles-required org: draft, attach each document, submit — clean")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="workshop", submit=False)
    for d in ("memo", "payment_sheet", "attendance_list"):
        req = _attach("packs", req, d, f"{d}.pdf")
    req = rq.submit_draft("packs", req.id, actor="amina@t")
    check("submitted with every file attached ⇒ documents check passes",
          _docs(req).result == rq.CheckResult.PASS, _docs(req).message)
    check("the check names what was provided", "payment sheet" in (_docs(req).actual_value or "").lower(),
          str(_docs(req).actual_value))


def test_the_pack_follows_the_category_and_falls_back_when_there_is_none() -> None:
    print("\nThe pack is the category's; an unlisted category gets the org-wide list")
    wf = rq.get_workflow("packs")
    check("workshop ⇒ its own pack", rq.required_documents_for(wf, "Workshop") ==
          ["memo", "payment_sheet", "attendance_list"])
    check("anything else ⇒ the org-wide list", rq.required_documents_for(wf, "fuel") == ["memo", "invoice"])


def test_a_late_file_clears_the_block_without_resubmitting() -> None:
    print("\nReturned for a missing document: attaching it clears the check")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="workshop")
    req = _attach("packs", req, "memo")
    req = _attach("packs", req, "payment_sheet")
    check("two of three ⇒ still blocked", _docs(req).result == rq.CheckResult.FAIL, _docs(req).message)
    check("and the message names only what is still missing",
          "attendance list" in _docs(req).message.lower() and "memo" not in _docs(req).message.lower(),
          _docs(req).message)
    req = _attach("packs", req, "attendance_list")
    check("third arrives ⇒ block cleared on the spot", _docs(req).result == rq.CheckResult.PASS,
          _docs(req).message)
    check("the re-check is on the audit trail",
          any(e.event == "documents_rechecked" for e in req.audit_log))
    check("and the chain still verifies", rq.verify_audit_chain(req))


def test_an_untyped_file_does_not_count_as_a_required_document() -> None:
    print("\nA file with no type is a supporting file, not the invoice")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="fuel")
    req = _attach("packs", req, "", "photo.jpg")
    check("still blocked", _docs(req).result == rq.CheckResult.FAIL)


def test_a_decided_payment_is_never_rewritten_by_a_late_file() -> None:
    print("\nAfter approval or payment, attaching files changes nothing about the checks")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="fuel")
    raw = store.get_store().get("packs", "requisitions", req.id)
    raw["status"] = "approved"
    store.get_store().put("packs", "requisitions", req.id, raw)
    req = _attach("packs", req, "memo")
    req = _attach("packs", req, "invoice")
    check("an approved payment keeps the checks it was approved on",
          _docs(req).result == rq.CheckResult.FAIL, _docs(req).message)


def test_an_override_is_never_quietly_replaced() -> None:
    print("\nA released block stays released — with the approver's name and reason")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="fuel")
    raw = store.get_store().get("packs", "requisitions", req.id)
    for c in raw["checks"]:
        if c["code"] == "DOCS_COMPLETE":
            c.update(overridden=True, override_by="aed@t", override_reason="invoice to follow")
    store.get_store().put("packs", "requisitions", req.id, raw)
    req = _attach("packs", req, "memo")
    d = _docs(req)
    check("still marked overridden, by the same person, for the same reason",
          d.overridden and d.override_by == "aed@t" and d.override_reason == "invoice to follow", str(d))


def test_an_org_without_file_rules_still_works_on_ticks() -> None:
    print("\nFlag off: ticks still satisfy the check, and a typed file does too")
    a = rq.create_requisition("simple", submitted_by="u@s", department="program",
                              vendor_name="Vendor", amount=10, documents=["invoice"])
    check("ticked ⇒ passes (unchanged behaviour)", _docs(a).result == rq.CheckResult.PASS, _docs(a).message)
    b = rq.create_requisition("simple", submitted_by="u@s", department="program",
                              vendor_name="Vendor 2", amount=11)
    b = _attach("simple", b, "invoice")
    check("attached as the invoice ⇒ passes too", _docs(b).result == rq.CheckResult.PASS, _docs(b).message)


def test_people_read_words_not_codes() -> None:
    print("\nMessages say 'payment sheet', not 'payment_sheet'")
    req = rq.create_requisition("packs", submitted_by="amina@t", department="program",
                                vendor_name="Hotel", amount=1000, category="workshop")
    msg = _docs(req).message
    check("no underscores in the message", "_" not in msg, msg)


def test_the_upload_route_records_what_the_file_is() -> None:
    print("\nHTTP: draft → attach typed files → submit is clean")
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    PW = "correct-horse-battery"
    A.create_user("amina@t", "Amina", PW, "program", "reviewer", org_id="packs")
    tok = c.post("/auth/login", json={"email": "amina@t", "password": PW}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    r = c.post("/requisitions", headers=H, data={"vendor_name": "Hotel", "amount": "1000",
                                                 "category": "workshop", "submit": "false"})
    check("draft created", r.status_code < 300, f"{r.status_code} {r.text[:120]}")
    rid = r.json()["id"]
    for d in ("memo", "payment_sheet", "attendance_list"):
        up = c.post(f"/requisitions/{rid}/attachments", headers=H,
                    files={"file": (f"{d}.pdf", b"%PDF-1.4 test", "application/pdf")},
                    data={"document_type": d})
        check(f"{d} uploaded", up.status_code < 300, f"{up.status_code} {up.text[:120]}")
    types = {a["document_type"] for a in up.json()["attachments"]}
    check("each attachment reports what it is", types == {"memo", "payment_sheet", "attendance_list"},
          str(types))
    s = c.post(f"/requisitions/{rid}/submit", headers=H)
    docs = next(x for x in s.json()["checks"] if x["code"] == "DOCS_COMPLETE")
    check("submitted clean", docs["result"] == "pass", str(docs))


if __name__ == "__main__":
    print("WO-44 — documents follow the category; a document is a file")
    _setup_orgs()
    test_a_tick_is_not_a_document_when_the_org_requires_files()
    test_attaching_the_file_is_what_provides_the_document()
    test_the_pack_follows_the_category_and_falls_back_when_there_is_none()
    test_a_late_file_clears_the_block_without_resubmitting()
    test_an_untyped_file_does_not_count_as_a_required_document()
    test_a_decided_payment_is_never_rewritten_by_a_late_file()
    test_an_override_is_never_quietly_replaced()
    test_an_org_without_file_rules_still_works_on_ticks()
    test_people_read_words_not_codes()
    test_the_upload_route_records_what_the_file_is()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
