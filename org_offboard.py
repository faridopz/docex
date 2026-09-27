#!/usr/bin/env python3
"""
End of contract: hand a client their data, delete it, and prove it.

    # 1. See what would go (changes nothing):
    DOCEX_DATABASE_URL=... python3 org_offboard.py --org neem

    # 2. Hand over and delete (asks for the org id typed back):
    DOCEX_DATABASE_URL=... python3 org_offboard.py --org neem --delete \\
        --confirm neem --out ./neem-final --actor farid

WHAT --delete DOES, IN ORDER
  1. Exports every record (client_export.py: CSVs + raw JSON + README) and
     copies every uploaded file into the same folder, then zips it. If the
     export is empty, it stops — nothing is deleted without a hand-over.
  2. Deletes the uploaded files from storage (local disk or Supabase).
  3. Deletes every record in that organisation, and only that organisation.
  4. Writes a deletion certificate — who, when, counts, and the SHA-256 of
     the export zip — beside the export and in a system record outside the
     deleted organisation, as evidence under a data processing agreement.

The signing key (DOCEX_SIGNING_KEY) is not touched: it belongs to the
instance, not to the data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import store

SYSTEM_ORG = "docex-system"
CERTIFICATES = "offboarding_certificates"


class OffboardError(RuntimeError):
    pass


def _storage_keys(value: Any, out: set) -> None:
    """Every `storage_key` anywhere in a record — attachments on requisitions
    today, and any future engine that stores files the same way."""
    if isinstance(value, dict):
        key = value.get("storage_key")
        if isinstance(key, str) and key.strip():
            out.add(key.strip())
        for v in value.values():
            _storage_keys(v, out)
    elif isinstance(value, list):
        for v in value:
            _storage_keys(v, out)


def plan(org_id: str) -> dict:
    """What deleting this organisation would remove. Changes nothing."""
    org = store.require_org(org_id)
    st = store.get_store()
    collections: dict[str, int] = {}
    files: set[str] = set()
    for coll in st.collections(org):
        rows = st.list(org, coll)
        collections[coll] = len(rows)
        for r in rows:
            _storage_keys(r, files)
    return {"org_id": org, "collections": collections,
            "records": sum(collections.values()), "files": sorted(files)}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def offboard(org_id: str, *, confirm: str, export_dir: Path, actor: str) -> dict:
    org = store.require_org(org_id)
    if (confirm or "").strip() != org:
        raise OffboardError(f"Type the organisation id to confirm: --confirm {org}")
    if org == SYSTEM_ORG:
        raise OffboardError("The system records are not an organisation's data.")
    if not (actor or "").strip():
        raise OffboardError("Say who is doing this (--actor): it goes on the certificate.")

    import attachments
    import client_export

    before = plan(org)
    if before["records"] == 0:
        raise OffboardError(f"No records for '{org}'. Is this the right database?")

    # 1. Hand-over first. Nothing is deleted without it.
    export_dir = Path(export_dir)
    summary = client_export.export(org, export_dir)
    if not summary:
        raise OffboardError("The export came out empty — nothing was deleted.")
    backend = attachments.get_backend()
    files_dir = export_dir / "files"
    missing: list[str] = []
    for key in before["files"]:
        try:
            data = backend.read(key)
        except Exception:  # noqa: BLE001 — record it; don't block the hand-over
            missing.append(key)
            continue
        target = files_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    archive = export_dir.parent / f"{export_dir.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(export_dir.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(export_dir))
    shutil.move(str(archive), str(export_dir / archive.name))
    archive = export_dir / archive.name
    export_sha = _sha256(archive)

    # 2. Files, then 3. records — only this organisation's.
    files_deleted = 0
    for key in before["files"]:
        if not key.startswith(f"{org}/"):
            continue                       # never touch a key outside this org
        try:
            files_deleted += 1 if backend.delete(key) else 0
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{key} (delete failed: {exc})")
    st = store.get_store()
    records_deleted = st.delete_org(org)

    # 4. The certificate.
    cert = {
        # Not "org_id": the store stamps that field with the org a record is
        # kept under, which for the certificate is the system org.
        "deleted_org": org,
        "deleted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "deleted_by": actor.strip(),
        "records_deleted": records_deleted,
        "records_by_type": before["collections"],
        "files_deleted": files_deleted,
        "files_not_handled": missing,
        "export_file": archive.name,
        "export_sha256": export_sha,
        "remaining_records": plan(org)["records"],
    }
    (export_dir / "deletion-certificate.json").write_text(json.dumps(cert, indent=2))
    st.put(SYSTEM_ORG, CERTIFICATES, f"{org}-{cert['deleted_at'][:10]}", cert)
    return cert


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", required=True)
    ap.add_argument("--delete", action="store_true", help="hand over and delete (default: preview only)")
    ap.add_argument("--confirm", default="", help="the org id, typed again")
    ap.add_argument("--out", default="", help="folder for the hand-over export")
    ap.add_argument("--actor", default="", help="who is doing this (goes on the certificate)")
    a = ap.parse_args()

    print(f"Storage: {store.configure_from_env(quiet=True)}")
    p = plan(a.org)
    print(f"Organisation '{p['org_id']}': {p['records']:,} records, {len(p['files'])} uploaded files")
    for coll, n in sorted(p["collections"].items()):
        print(f"  {coll:<32} {n:>7,}")
    if not a.delete:
        print("\nPreview only. Nothing was changed. Add --delete --confirm <org> --out <folder> --actor <name>.")
        return 0
    out = Path(a.out or f"./{a.org}-final-{dt.date.today().isoformat()}")
    try:
        cert = offboard(a.org, confirm=a.confirm, export_dir=out, actor=a.actor)
    except OffboardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\nHanded over: {out / cert['export_file']}  (sha256 {cert['export_sha256'][:16]}…)")
    print(f"Deleted {cert['records_deleted']:,} records and {cert['files_deleted']} files.")
    if cert["files_not_handled"]:
        print(f"Check by hand: {len(cert['files_not_handled'])} file(s) — see deletion-certificate.json")
    if cert["remaining_records"]:
        print(f"WARNING: {cert['remaining_records']} records remain.")
        return 1
    print(f"Certificate: {out / 'deletion-certificate.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
