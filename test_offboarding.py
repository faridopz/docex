"""
At the end of a contract, a client's data can be handed over and then
deleted — completely, only theirs, and provably.

There was no way to do it: records could only be removed one at a time, and
uploaded files had no delete at all, so a client's invoices and payment
sheets would outlive the contract. A data processing agreement needs both
the deletion and the evidence of it.

Run: python test_offboarding.py
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-offboard-")
os.environ["DOCEX_ORG"] = "gone"

import store  # noqa: E402

store.set_store(store.JsonFileStore(Path(_TMP) / "db"))

import attachments  # noqa: E402

attachments.set_backend(attachments.LocalDiskAttachmentBackend(Path(_TMP) / "files"))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import org_offboard  # noqa: E402
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


def _seed(org: str) -> str:
    org_config.set_features(org, requisition_attachments=True)
    A.create_user(f"u@{org}.org", "U", "correct-horse-battery", "program", "reviewer", org_id=org)
    r = rq.create_requisition(org, submitted_by=f"u@{org}.org", department="program",
                              vendor_name="Hotel", amount=1000.0)
    key = attachments.get_backend().put(org, r.id, "att1", "invoice.pdf", b"%PDF-1.4 x", "application/pdf")
    rq.add_attachment(org, r.id, actor=f"u@{org}.org", filename="invoice.pdf",
                      content_type="application/pdf", size=10, storage_key=key, document_type="invoice")
    return key


def test_preview_deletes_nothing() -> None:
    print("\nPreview: says what would go, removes nothing")
    plan = org_offboard.plan("gone")
    check("counts the records", plan["records"] > 0 and "requisitions" in plan["collections"], str(plan))
    check("finds the uploaded file", len(plan["files"]) == 1, str(plan["files"]))
    check("nothing removed", rq.list_requisitions("gone"))


def test_refused_without_the_org_typed_back() -> None:
    print("\nDeleting needs the organisation's id typed back exactly")
    try:
        org_offboard.offboard("gone", confirm="gon", export_dir=Path(_TMP) / "x", actor="farid")
        check("refused", False)
    except org_offboard.OffboardError as exc:
        check("refused", "confirm" in str(exc).lower(), str(exc))
    check("nothing removed", rq.list_requisitions("gone"))


def test_hand_over_then_delete(file_key: str, keep_key: str) -> None:
    print("\nHand over, then delete: their export exists, their data doesn't, others untouched")
    out = Path(_TMP) / "handover"
    cert = org_offboard.offboard("gone", confirm="gone", export_dir=out, actor="farid")
    zips = list(out.glob("*.zip"))
    check("export handed over as one zip", len(zips) == 1 and zipfile.ZipFile(zips[0]).namelist(),
          str(zips))
    check("every record removed", store.get_store().collections("gone") == [],
          str(store.get_store().collections("gone")))
    check("uploaded file removed", not (Path(_TMP) / "files" / file_key).exists())
    check("another organisation untouched", rq.list_requisitions("keep")
          and (Path(_TMP) / "files" / keep_key).exists())
    check("certificate names counts and the export's fingerprint",
          cert["records_deleted"] > 0 and cert["files_deleted"] == 1 and len(cert["export_sha256"]) == 64,
          str(cert))
    kept = store.get_store().list(org_offboard.SYSTEM_ORG, org_offboard.CERTIFICATES)
    check("certificate kept outside the deleted organisation", any(c.get("deleted_org") == "gone" for c in kept))
    check("and written beside the export", (out / "deletion-certificate.json").exists())


if __name__ == "__main__":
    print("Offboarding: hand over, delete, prove it")
    key = _seed("gone")
    keep = _seed("keep")
    test_preview_deletes_nothing()
    test_refused_without_the_org_typed_back()
    test_hand_over_then_delete(key, keep)
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
