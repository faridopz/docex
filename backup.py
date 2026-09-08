#!/usr/bin/env python3
"""
DOCex backups — take one, check it, restore it, prove it.

WHY THIS FILE EXISTS
A managed database provider takes its own snapshots, and those are the fastest
way to recover from a fat-fingered delete. They answer one question well and
two questions badly:

  1. "Can we get last Tuesday back?"           — the provider answers this.
  2. "Can we read our records without you?"    — it cannot; the snapshot is a
     binary in their format, restorable only into their product.
  3. "Has anyone ever actually restored one?"  — nobody has, and an untested
     backup is a belief, not a backup.

So this writes a plain JSON Lines export — one record per line, readable with
any text editor a decade from now — and it can restore that export into a
scratch database and count what came back. That last part is the point. The
`verify` command is what turns "we have backups" into a sentence you can say
to a client's auditor without crossing your fingers.

USAGE
    python3 backup.py create                    # write a timestamped backup
    python3 backup.py list                      # what we hold, and how old
    python3 backup.py verify [FILE]             # restore into a scratch DB
    python3 backup.py restore FILE --into DB    # deliberate, explicit recovery
    python3 backup.py prune                     # apply the retention policy

Storage is chosen the same way the API chooses it (store.configure_from_env),
so the backup always comes from the database the app is actually using — the
mistake that produces a confident daily backup of an empty development store.

WHERE BACKUPS GO
DOCEX_BACKUP_DIR, else ./backups. On a container that directory MUST be a
mounted volume or object storage; a backup on the same ephemeral disk as the
database is not a backup, it is a second copy of the thing you are about to
lose. `create` says so out loud when it detects that case.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import store  # noqa: E402

# Retention. Thirty daily copies covers "we noticed at the month end"; twelve
# monthly copies covers "the auditor asked in October about March".
KEEP_DAILY = 30
KEEP_MONTHLY = 12


def backup_dir() -> Path:
    d = Path(os.environ.get("DOCEX_BACKUP_DIR", "").strip() or "backups")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _describe_store() -> str:
    return store.configure_from_env(quiet=True)


def _warn_if_same_disk(target: Path) -> None:
    """A backup beside the database survives everything except what matters."""
    db = os.environ.get("DOCEX_DB", "").strip()
    if not db:
        return
    try:
        if Path(db).resolve().parent == target.resolve().parent:
            print("  ! WARNING: backups are being written next to the database.")
            print("    A disk failure, a wiped container or an accidental volume")
            print("    delete takes both. Set DOCEX_BACKUP_DIR to somewhere else,")
            print("    and copy these files off the machine.")
    except Exception:
        pass


# ─── create ─────────────────────────────────────────────────────────────────


def cmd_create(args) -> int:
    backend = _describe_store()
    s = store.get_store()
    if not hasattr(s, "backup"):
        print(f"The active store ({backend}) has no backup method.")
        print("Set DOCEX_DB or DOCEX_DATABASE_URL so this runs against the real "
              "database rather than the JSON fallback.")
        return 2

    out = backup_dir()
    _warn_if_same_disk(out)
    stamp = _stamp()

    # The portable copy — always. This is the one that outlives us.
    jsonl = out / f"docex-{stamp}.jsonl"
    if hasattr(s, "export_jsonl"):
        s.export_jsonl(jsonl)               # SqliteStore
    else:
        s.backup(jsonl)                     # PostgresStore writes JSONL directly
    records = sum(1 for line in jsonl.open(encoding="utf-8") if line.strip())

    written = [jsonl]

    # The fast copy — SQLite only. Restoring a .db file is a file copy; the
    # JSONL path has to replay every record. Keep both: one is quick, the other
    # is readable.
    if type(s).__name__ == "SqliteStore":
        db_copy = out / f"docex-{stamp}.db"
        s.backup(db_copy)
        written.append(db_copy)

    total = sum(p.stat().st_size for p in written)
    print(f"Backed up {records} records from {backend}")
    for p in written:
        print(f"  {p}  ({p.stat().st_size / 1024:.0f} KB)")

    if records == 0:
        print("  ! WARNING: zero records. Either this database is genuinely empty,")
        print("    or this process is pointed at a different store from the API.")
        print("    Check DOCEX_DB / DOCEX_DATABASE_URL before trusting this file.")
        return 1

    if args.verify:
        print()
        return _verify(jsonl, expect=records)
    return 0


# ─── verify ─────────────────────────────────────────────────────────────────


def _verify(path: Path, expect: int | None = None) -> int:
    """Restore a backup into a throwaway database and check what came back.

    This is the only step that distinguishes a backup from a file.
    """
    import store_sql

    print(f"Verifying {path.name}")
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        print("  FAIL: the file is empty.")
        return 1

    bad = 0
    orgs: set[str] = set()
    collections: set[str] = set()
    for i, line in enumerate(lines, 1):
        try:
            rec = json.loads(line)
            assert {"org_id", "collection", "record_id", "data"} <= set(rec)
            orgs.add(rec["org_id"])
            collections.add(rec["collection"])
        except Exception as exc:
            bad += 1
            if bad <= 3:
                print(f"  line {i} is unreadable: {exc}")
    if bad:
        print(f"  FAIL: {bad} of {len(lines)} lines are corrupt.")
        return 1

    scratch = Path(tempfile.mkdtemp(prefix="docex-verify-")) / "restored.db"
    target = store_sql.SqliteStore(scratch)
    restored = target.restore(path)

    print(f"  {restored} records restored into a scratch database")
    print(f"  {len(orgs)} organisation(s): {', '.join(sorted(orgs))}")
    print(f"  {len(collections)} collections")

    ok = True
    if expect is not None and restored != expect:
        print(f"  FAIL: expected {expect} records, restored {restored}.")
        ok = False

    # The specific things whose loss would be unrecoverable, checked by name.
    for org in sorted(orgs):
        users = target.list(org, "users")
        active_admins = [u for u in users
                         if u.get("role") == "admin" and u.get("active", True)]
        reqs = len(target.list(org, "requisitions"))
        txns = len(target.list(org, "transactions"))
        print(f"    {org}: {len(users)} users ({len(active_admins)} active admin), "
              f"{reqs} requisitions, {txns} transactions")
        if users and not active_admins:
            print(f"  FAIL: {org} would restore with no active administrator — "
                  "nobody could sign in to the recovered system.")
            ok = False

    print(f"\n{'VERIFIED' if ok else 'FAILED'} — {path}")
    if ok:
        print("Record today's date in DEPLOYMENT.md. An auditor will ask when "
              "you last tested a restore, and 'we have backups' is not the answer.")
    return 0 if ok else 1


def cmd_verify(args) -> int:
    if args.file:
        return _verify(Path(args.file))
    files = sorted(backup_dir().glob("docex-*.jsonl"))
    if not files:
        print(f"No backups found in {backup_dir()}. Run: python3 backup.py create")
        return 2
    return _verify(files[-1])


# ─── restore ────────────────────────────────────────────────────────────────


def cmd_restore(args) -> int:
    """Deliberately awkward: an explicit target, and a typed confirmation.

    Restoring over a live database is how a bad afternoon becomes a bad
    quarter. In an incident the first move is a rollback, not a restore — this
    is for when the data itself is gone or corrupt.
    """
    import store_sql

    src = Path(args.file)
    if not src.exists():
        print(f"No such backup: {src}")
        return 2

    into = args.into
    if not into:
        print("Say where. --into ./restored.db, or --into $DOCEX_DATABASE_URL")
        return 2

    target = (store_sql.PostgresStore(into) if into.startswith("postgres")
              else store_sql.SqliteStore(into))
    existing = target.count() if hasattr(target, "count") else 0
    if existing and not args.force:
        print(f"{into} already holds {existing} records.")
        print("Restoring upserts by (org, collection, id): records in the backup")
        print("overwrite their counterparts, and anything created since the")
        print("backup is left untouched. Re-run with --force if that is what")
        print("you want.")
        return 3

    n = target.restore(src)
    print(f"Restored {n} records from {src.name} into {into}")
    print("Sign in before telling anyone it worked.")
    return 0


# ─── list / prune ───────────────────────────────────────────────────────────


def cmd_list(args) -> int:
    files = sorted(backup_dir().glob("docex-*.jsonl"))
    if not files:
        print(f"No backups in {backup_dir()}.")
        return 1
    now = dt.datetime.now(dt.timezone.utc)
    print(f"{len(files)} backup(s) in {backup_dir()}\n")
    for p in files[-15:]:
        try:
            when = dt.datetime.strptime(p.stem.split("-", 1)[1], "%Y%m%dT%H%M%SZ") \
                .replace(tzinfo=dt.timezone.utc)
            age = now - when
            age_s = (f"{age.days}d ago" if age.days else
                     f"{int(age.total_seconds() // 3600)}h ago")
        except Exception:
            age_s = "?"
        n = sum(1 for line in p.open(encoding="utf-8") if line.strip())
        print(f"  {p.name}  {n:>6} records  {p.stat().st_size / 1024:>7.0f} KB  {age_s}")

    newest = files[-1]
    try:
        when = dt.datetime.strptime(newest.stem.split("-", 1)[1], "%Y%m%dT%H%M%SZ") \
            .replace(tzinfo=dt.timezone.utc)
        hours = (now - when).total_seconds() / 3600
        if hours > 36:
            print(f"\n  ! The newest backup is {hours / 24:.1f} days old. "
                  "Is the scheduled job running?")
    except Exception:
        pass
    return 0


def cmd_prune(args) -> int:
    """Keep 30 daily and 12 monthly. Never delete the newest."""
    files = sorted(backup_dir().glob("docex-*.jsonl"))
    if len(files) <= KEEP_DAILY:
        print(f"{len(files)} backups — nothing to prune (keeping {KEEP_DAILY} daily).")
        return 0

    keep: set[Path] = set(files[-KEEP_DAILY:])
    by_month: dict[str, Path] = {}
    for p in files:
        try:
            month = p.stem.split("-", 1)[1][:6]
        except Exception:
            continue
        by_month[month] = p              # last of each month wins
    for month in sorted(by_month)[-KEEP_MONTHLY:]:
        keep.add(by_month[month])

    removed = 0
    for p in files:
        if p in keep:
            continue
        sibling = p.with_suffix(".db")
        p.unlink(missing_ok=True)
        sibling.unlink(missing_ok=True)
        removed += 1
    print(f"Pruned {removed}, kept {len(keep)}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="write a timestamped backup")
    c.add_argument("--verify", action="store_true",
                   help="restore it into a scratch database straight away")
    c.set_defaults(func=cmd_create)

    v = sub.add_parser("verify", help="restore a backup into a scratch database")
    v.add_argument("file", nargs="?", help="defaults to the newest backup")
    v.set_defaults(func=cmd_verify)

    r = sub.add_parser("restore", help="restore into a named database")
    r.add_argument("file")
    r.add_argument("--into", required=False, help="path or postgres:// URL")
    r.add_argument("--force", action="store_true")
    r.set_defaults(func=cmd_restore)

    sub.add_parser("list", help="what we hold, and how old").set_defaults(func=cmd_list)
    sub.add_parser("prune", help="apply the retention policy").set_defaults(func=cmd_prune)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
