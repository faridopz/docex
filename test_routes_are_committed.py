#!/usr/bin/env python3
"""
Every page that exists must actually ship.

Written after three screens 404'd in production while existing perfectly on the
developer's machine, compiling cleanly, and passing every type check.

The cause was one character. `.gitignore` carried bare patterns for the local
JSON data stores at the repo root:

    users/
    transactions/
    vouchers/

A bare pattern in .gitignore matches a directory of that name at ANY depth. So
those three lines also matched:

    web/app/settings/users/       — People & access, the user-management screen
    web/app/transactions/[ref]/   — transaction detail
    web/app/vouchers/new/         — voucher builder

The files were never committed, so they were never built, so the routes 404'd.

What made it invisible for weeks is that NOTHING reported a problem. `git
status` was clean — an ignored file is not untracked, it is simply not there as
far as git is concerned. `tsc` passed, because the files are on disk and
type-check fine. The test suites passed. The build succeeded. Every signal we
had was green, and the pages did not exist.

That is the shape of failure this suite exists for: not a thing that breaks,
but a thing that is silently absent while every check reports success.

The test does not name those three directories. It asks git which files under
web/app are ignored, and fails on any of them — so it catches the NEXT
directory somebody names after a data store, which is the one that matters.

Run: python3 test_routes_are_committed.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
WEB_APP = ROOT / "web" / "app"

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout


def test_no_source_file_is_ignored() -> None:
    """Ask git, rather than guessing. Any ignored source file is the bug."""
    print("\nNo page, component or library file is excluded by .gitignore")

    if not (ROOT / ".git").exists():
        print("  --   not a git checkout, skipping")
        return

    roots = [WEB_APP, ROOT / "web" / "components", ROOT / "web" / "lib", ROOT / "api"]
    files: list[Path] = []
    for r in roots:
        if r.exists():
            files += [p for p in r.rglob("*")
                      if p.suffix in {".tsx", ".ts", ".py"} and p.is_file()
                      and "node_modules" not in p.parts and ".next" not in p.parts]

    check(f"found {len(files)} source files to check", bool(files))

    # `git check-ignore --stdin` answers for many paths in one call.
    rel = "\n".join(str(p.relative_to(ROOT)) for p in files)
    out = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT,
                         input=rel, capture_output=True, text=True).stdout
    ignored = [line for line in out.splitlines() if line.strip()]

    if ignored:
        print("\n  These files exist on disk and will NEVER be deployed:")
        for line in ignored:
            print(f"    {line}")
        print("  A bare pattern like `users/` in .gitignore matches that name at")
        print("  ANY depth. Anchor it with a leading slash: `/users/`.\n")

    check("no source file is ignored", not ignored,
          f"{len(ignored)} ignored — listed above")


def test_every_page_is_tracked() -> None:
    """On disk is not the same as in the repository."""
    print("\nEvery page.tsx on disk is tracked by git")

    if not (ROOT / ".git").exists() or not WEB_APP.exists():
        print("  --   not a git checkout, skipping")
        return

    on_disk = {p.relative_to(ROOT).as_posix()
               for p in WEB_APP.rglob("page.tsx")
               if "node_modules" not in p.parts}
    tracked = set(git("ls-files", "web/app").splitlines())

    missing = sorted(on_disk - tracked)
    if missing:
        print("\n  Untracked pages — these routes 404 in production:")
        for m in missing:
            print(f"    {m}")
        print()

    check(f"all {len(on_disk)} pages are tracked", not missing,
          f"{len(missing)} untracked")


def test_the_data_stores_are_still_ignored() -> None:
    """The fix must not accidentally start committing a client's records.

    Anchoring the patterns was the right repair; anchoring them WRONG would put
    live payment data into git history, where deleting it no longer removes it.
    """
    print("\nThe root data directories are still excluded")

    if not (ROOT / ".git").exists():
        print("  --   not a git checkout, skipping")
        return

    for name in ("users", "transactions", "notifications", "vouchers"):
        probe = f"{name}/some-record.json"
        out = subprocess.run(["git", "check-ignore", probe], cwd=ROOT,
                             capture_output=True, text=True)
        check(f"{name}/ at the repo root is ignored", out.returncode == 0,
              "a client's records would be committed")


def main() -> int:
    print("=" * 64)
    print("Does every page that exists actually ship?")
    print("=" * 64)
    test_no_source_file_is_ignored()
    test_every_page_is_tracked()
    test_the_data_stores_are_still_ignored()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
