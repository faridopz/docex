"""
Wipe all demo data from the local DOCex install.

Usage:
    python demo_fixtures/wipe.py --confirm

What it removes:
    - Any rulebook whose id starts with "demo-"
    - The entire demo_uploads/ directory
    - Any check / verification / attendance run with id starting "demo-"

Safe by default — refuses to run without --confirm. Lists what it
would delete first.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_targets() -> list[Path]:
    targets: list[Path] = []

    # demo_uploads — whole dir
    uploads = ROOT / "demo_uploads"
    if uploads.exists():
        targets.append(uploads)

    # rulebooks/demo-*.json
    rbdir = ROOT / "rulebooks"
    if rbdir.exists():
        for f in rbdir.glob("demo-*.json"):
            targets.append(f)

    # checks/, verifications/, attendance_runs/, decks/ — any id starting "demo-"
    for subdir in ["checks", "verifications", "attendance_runs", "decks"]:
        d = ROOT / subdir
        if not d.exists():
            continue
        for f in d.glob("demo-*"):
            targets.append(f)

    return targets


def main() -> None:
    targets = find_targets()
    if not targets:
        print("Nothing to wipe — no demo data found.")
        return

    print("The following demo artefacts will be deleted:")
    for t in targets:
        print(f"  · {t.relative_to(ROOT)}")
    print()

    if "--confirm" not in sys.argv:
        print(
            "Refusing to delete without --confirm. Re-run as: "
            "python demo_fixtures/wipe.py --confirm"
        )
        sys.exit(2)

    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink()
    print(f"\n✓ Wiped {len(targets)} demo artefacts.")


if __name__ == "__main__":
    main()
