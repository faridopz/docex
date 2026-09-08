#!/usr/bin/env python3
"""
Hand a client a complete, readable copy of their own records.

WHY THIS EXISTS
A one-person supplier holding a finance team's payment history is a real risk,
and the client is right to think about it. There is no engineering answer to
"what if you are hit by a bus" — but there is a practical one: give them a copy
they can open without us, on a schedule, before they ask.

That turns an uncomfortable question into a boring one. It also removes the
worst version of lock-in: a client who stays because leaving would cost them
their records is not a client, and a supplier who relies on that is not one
either.

WHAT IT PRODUCES
A folder of CSV files — one per kind of record — plus a README that explains
each column in plain language, and the raw JSON for anything a spreadsheet
cannot represent. CSV because their finance team lives in Excel, and because a
CSV will still open in twenty years.

    python3 client_export.py --org neem --out ./neem-export
    python3 client_export.py --org neem --zip          # one file to send

DIFFERENT FROM backup.py
`backup.py` is OUR disaster recovery: everything, in a format built to be
restored. This is THEIRS: their records, organised the way their finance team
thinks about them, meant to be read rather than restored.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import store  # noqa: E402

# Collections worth giving a client, and the columns their finance team
# actually cares about. Anything not listed here is still exported as JSON, so
# nothing is silently withheld — this only decides what gets a tidy CSV.
_SHEETS: dict[str, tuple[str, list[str]]] = {
    "requisitions": ("Payment requests", [
        "ref", "status", "vendor_name", "amount", "currency", "category",
        "project_code", "department", "submitted_by", "created_at", "paid_at",
        "description",
    ]),
    "transactions": ("Workflow items", [
        "ref", "kind", "title", "state", "amount", "currency",
        "owner_department", "created_by", "created_at", "updated_at",
    ]),
    "disbursements": ("Money that left the account", [
        "id", "source_kind", "source_ref", "payee_name", "amount", "currency",
        "account_code", "paid_at", "bank_reference", "settlement",
    ]),
    "vendors": ("Vendor register", [
        "id", "name", "tax_id", "bank_name", "account_name", "status",
        "created_at",
    ]),
    "advances": ("Advances and retirement", [
        "ref", "staff_id", "staff_name", "amount", "purpose", "project_code",
        "issued_at", "due_at", "status", "retired_at",
    ]),
    "vouchers": ("Payment vouchers", [
        "id", "event_name", "total", "currency", "participant_count",
        "txn_ref", "created_at",
    ]),
    "users": ("People with access", [
        "email", "name", "department", "role", "active", "created_at",
        "last_login_at",
    ]),
    "timesheets": ("Timesheets", [
        "id", "staff_id", "period", "status", "total_hours", "submitted_at",
    ]),
    "bank_accounts": ("Bank accounts", [
        "id", "code", "name", "bank_name", "project_code", "active",
    ]),
}

# Never leave the building, even in a client's own export. A password hash is
# still a credential, and a session cutoff is operational noise.
_NEVER_EXPORT = {"password_hash", "password_salt", "secret", "recovery_hashes",
                 "used_counters"}
_SKIP_COLLECTIONS = {"login_attempts", "session_cutoffs", "mfa", "idempotency"}


def _clean(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in _NEVER_EXPORT}


def _flat(value) -> str:
    """CSV cells hold text. Nested structures become compact JSON rather than
    Python's repr, which nothing else can read back."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def export(org_id: str, out_dir: Path) -> dict:
    st = store.get_store()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw-json"
    raw_dir.mkdir(exist_ok=True)

    collections = [c for c in st.collections(org_id) if c not in _SKIP_COLLECTIONS]
    summary: dict[str, int] = {}

    for coll in sorted(collections):
        rows = [_clean(r) for r in st.list(org_id, coll)]
        if not rows:
            continue
        summary[coll] = len(rows)

        # The full record, always — a CSV picks columns, and the client should
        # never have to take our word for what was left out.
        (raw_dir / f"{coll}.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")

        title, columns = _SHEETS.get(coll, (coll.replace("_", " ").title(), []))
        if not columns:
            # Unknown collection: every key any record uses, so nothing hides.
            keys: list[str] = []
            for r in rows:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            columns = keys

        # utf-8-sig so Excel on Windows shows ₦ and Yoruba names correctly
        # instead of mojibake. Without the BOM, the first thing the client sees
        # is their own data looking corrupted.
        with (out_dir / f"{coll}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(columns)
            for r in rows:
                w.writerow([_flat(r.get(c)) for c in columns])

    _write_readme(org_id, out_dir, summary)
    return summary


def _write_readme(org_id: str, out_dir: Path, summary: dict[str, int]) -> None:
    today = dt.date.today().isoformat()
    lines = [
        f"# Your DOCex records — {org_id}",
        "",
        f"Exported {today}. This is a complete copy of your organisation's",
        "records, in formats you can open without DOCex and without us.",
        "",
        "## What is here",
        "",
        "| File | What it holds | Records |",
        "|---|---|---|",
    ]
    for coll, count in sorted(summary.items()):
        title = _SHEETS.get(coll, (coll.replace("_", " ").title(), []))[0]
        lines.append(f"| `{coll}.csv` | {title} | {count:,} |")
    lines += [
        "",
        "`raw-json/` holds the same records with every field, including any a",
        "spreadsheet cannot show neatly — full approval trails, policy check",
        "results, audit entries. The CSVs are a readable view; the JSON is the",
        "complete record.",
        "",
        "## Opening these",
        "",
        "Double-click any `.csv` and it opens in Excel, LibreOffice or Google",
        "Sheets. Amounts are plain numbers, so they sum and filter normally.",
        "Dates are `YYYY-MM-DD`, which sorts correctly as text.",
        "",
        "## What is deliberately NOT here",
        "",
        "- **Passwords.** Only irreversible hashes are ever stored, and those",
        "  are excluded — they are credentials, not records.",
        "- **Two-factor secrets and recovery codes.**",
        "- **Sign-in attempt logs**, which are operational noise.",
        "",
        "Everything else your organisation has entered is in this folder.",
        "",
        "## The audit trail",
        "",
        "`raw-json/requisitions.json` contains each payment's full approval",
        "trail: who approved, when, on what authority, and the hash chaining",
        "each entry to the one before it. That chain is what lets DOCex show a",
        "record has not been altered since it was written — and it is readable",
        "here without us.",
        "",
        "## Questions",
        "",
        "Ask for an export any time. It is your data; there is no charge and no",
        "notice period.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", default=os.environ.get("DOCEX_ORG", "").strip(),
                    help="organisation id (defaults to DOCEX_ORG)")
    ap.add_argument("--out", default="", help="output folder")
    ap.add_argument("--zip", action="store_true",
                    help="also produce a single .zip to send")
    a = ap.parse_args()

    if not a.org:
        print("Which organisation? Pass --org or set DOCEX_ORG.")
        return 2

    backend = store.configure_from_env(quiet=True)
    print(f"Reading from {backend}")

    stamp = dt.date.today().isoformat()
    out = Path(a.out or f"./{a.org}-export-{stamp}")
    summary = export(a.org, out)

    if not summary:
        print(f"No records found for org '{a.org}'. Is DOCEX_DATABASE_URL "
              "pointing at the right database?")
        return 1

    total = sum(summary.values())
    print(f"\nExported {total:,} records for '{a.org}' to {out}/")
    for coll, n in sorted(summary.items()):
        print(f"  {coll:<20} {n:>7,}")

    if a.zip:
        archive = out.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(out.parent))
        print(f"\n{archive}  ({archive.stat().st_size / 1024:.0f} KB) — ready to send")

    print("\nSend it with a sentence, not an explanation:")
    print('  "Your monthly copy of your DOCex records. Opens in Excel; no')
    print('   software needed. Ask any time."')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
