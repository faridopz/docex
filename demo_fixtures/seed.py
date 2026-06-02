"""
Seed demo fixtures into the local DOCex install.

Usage:
    python demo_fixtures/seed.py generic
    python demo_fixtures/seed.py ngo-procurement

What it does:
    1. Reads the named fixture pack from demo_fixtures/<pack>/
    2. Drops a rulebook (if rulebook.json present) into rulebooks/
    3. Copies voucher files into demo_uploads/<pack>/
    4. Prints the URLs to visit in the running app

This is intentionally simple. The DemoSession model + ephemeral user
dirs come later (see prompts/demo-artifact-agent.md). For now, this
script just gets fixtures into the right places so a demo viewer sees
populated data when they open the app.

Idempotent — re-running just overwrites.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "demo_fixtures"


def seed_pack(pack: str) -> None:
    src = FIXTURES / pack
    if not src.is_dir():
        sys.exit(f"Unknown fixture pack: {pack}. Available: {available_packs()}")

    print(f"Seeding pack: {pack}")
    print(f"From: {src}")

    # Rulebook → rulebooks/
    rulebook_src = src / "rulebook.json"
    if rulebook_src.exists():
        rb = json.loads(rulebook_src.read_text())
        rulebook_id = rb["id"]
        dest = ROOT / "rulebooks" / f"{rulebook_id}.json"
        dest.parent.mkdir(exist_ok=True)
        shutil.copy(rulebook_src, dest)
        print(f"  ✓ Rulebook seeded → rulebooks/{rulebook_id}.json")

    # Voucher / policy / schedule files → demo_uploads/<pack>/
    upload_dest = ROOT / "demo_uploads" / pack
    upload_dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in src.iterdir():
        if f.name in {"rulebook.json", "README.md"}:
            continue
        if f.is_file():
            shutil.copy(f, upload_dest / f.name)
            copied += 1
    if copied:
        print(f"  ✓ {copied} upload files staged → demo_uploads/{pack}/")

    print()
    print("Done. Suggested next steps:")
    print(f"  · Start the API:  python -m uvicorn api.main:app --reload --port 8000")
    print(f"  · Start the web:  cd web && npm run dev")
    print(f"  · Open:           http://localhost:3000/compliance")
    if rulebook_src.exists():
        print(
            f"  · Use the seeded rulebook: it'll show up in the rulebooks list"
        )


def available_packs() -> list[str]:
    return sorted(d.name for d in FIXTURES.iterdir() if d.is_dir())


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python demo_fixtures/seed.py <pack>")
        print(f"Available packs: {', '.join(available_packs())}")
        sys.exit(1)
    seed_pack(sys.argv[1])


if __name__ == "__main__":
    main()
