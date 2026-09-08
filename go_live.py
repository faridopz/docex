#!/usr/bin/env python3
"""
Go live — the steps, in order, with the values filled in.

Everything DOCex needs to serve a real client, from a laptop with nothing set
up, on a budget of nothing. Run it and follow along:

    python3 go_live.py

It generates the two secrets that must never be lost, checks the things that
are checkable from here, and prints the exact clicks for the parts that need
a browser. It changes nothing on any server — the destructive steps are yours.

    python3 go_live.py --check     # just tell me what is missing
    python3 go_live.py --secrets   # just generate the keys
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
B = "\033[1m"; G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; D = "\033[2m"; X = "\033[0m"


def h(n: int, title: str) -> None:
    print(f"\n{B}{n}. {title}{X}")


def bullet(s: str = "") -> None:
    print(f"   {s}")


def cmd(s: str) -> None:
    print(f"   {D}${X} {s}")


# ─── checks we can actually do from here ────────────────────────────────────


def local_checks() -> list[tuple[bool, str]]:
    out: list[tuple[bool, str]] = []

    suites = sorted(ROOT.glob("test_*.py"))
    out.append((bool(suites), f"{len(suites)} test suites present"))

    for name, why in [
        ("render.yaml", "deployment blueprint"),
        ("backup.py", "backups"),
        ("verify_deployment.py", "post-deploy verification"),
        (".github/workflows/backup.yml", "nightly backup job"),
        ("profiles/neem.json", "NEEM's configuration"),
        ("NEEM_SECURITY_SUMMARY.md", "the document you hand the client"),
    ]:
        out.append(((ROOT / name).exists(), f"{name} — {why}"))

    try:
        import psycopg  # noqa: F401
        import psycopg_pool  # noqa: F401
        out.append((True, "psycopg + pool installed (Postgres driver)"))
    except ImportError:
        out.append((False, "psycopg NOT installed — pip install 'psycopg[binary,pool]'"))

    req = (ROOT / "requirements.txt").read_text() if (ROOT / "requirements.txt").exists() else ""
    out.append(("psycopg" in req, "psycopg is in requirements.txt (the image needs it)"))
    out.append(("sentry-sdk" in req, "sentry-sdk is in requirements.txt"))

    dockerignore = (ROOT / ".dockerignore").read_text() if (ROOT / ".dockerignore").exists() else ""
    out.append(("users/" in dockerignore,
                "users/ is excluded from the image (no stale admin ships)"))

    legacy = ROOT / "users"
    if legacy.is_dir():
        out.append((False, f"a local users/ directory exists ({len(list(legacy.glob('*.json')))} "
                           "account(s)) — gitignored, so it will not deploy, but delete it "
                           "once you have signed in to production"))

    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        out.append((not r.stdout.strip(), "working tree is clean (everything committed)"))
        r = subprocess.run(["git", "log", "--oneline", "origin/demo-release..HEAD"],
                           cwd=ROOT, capture_output=True, text=True, timeout=20)
        unpushed = len([l for l in r.stdout.splitlines() if l.strip()])
        out.append((unpushed == 0,
                    "everything is pushed" if unpushed == 0
                    else f"{unpushed} commit(s) not pushed — Render deploys from the branch"))
    except Exception:
        pass

    return out


def cmd_check() -> int:
    print(f"{B}What is ready on this machine{X}")
    results = local_checks()
    for good, label in results:
        print(f"  {G}ok{X}   {label}" if good else f"  {R}--{X}   {label}")
    bad = [l for ok, l in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} ready")
    return 1 if bad else 0


# ─── secrets ────────────────────────────────────────────────────────────────


def cmd_secrets() -> int:
    auth = secrets.token_urlsafe(48)
    signing = secrets.token_urlsafe(48)
    print(f"""
{B}Two secrets. Put them in a password manager BEFORE pasting them anywhere.{X}

AUTH_SECRET={auth}

DOCEX_SIGNING_KEY={signing}

{Y}AUTH_SECRET{X} signs session tokens. Lose it and everyone is signed out once,
which is annoying and survivable.

{R}DOCEX_SIGNING_KEY signs the audit chain, and can NEVER be changed.{X}
It is what lets DOCex prove to an auditor that a payment record has not been
altered since it was written. Replace it and verify_audit_chain() fails on
every historical record — not because anything was tampered with, but because
the proof was thrown away. There is no repair: re-signing the old records with
a new key would destroy the exact property the chain exists to demonstrate.

Save it somewhere you will still have in three years. Not only in Render.
""")
    return 0


# ─── the walkthrough ────────────────────────────────────────────────────────


def walkthrough() -> int:
    print(f"""
{B}Getting DOCex to NEEM{X}
{D}Free to launch. Every paid upgrade below is one click, later, with no data
migration — the database lives outside the web host precisely so that is true.{X}
""")

    print(f"{B}What runs where{X}")
    bullet(f"Frontend    Vercel          free")
    bullet(f"API         Render          free   {D}sleeps when idle; kept warm{X}")
    bullet(f"Database    Supabase        free   {D}500 MB, durable, never pauses in daily use{X}")
    bullet(f"Backups     GitHub Actions  free   {D}nightly, off-box, verified{X}")
    print()
    bullet(f"{Y}The free tier costs you a cold start, not your data.{X} The first request")
    bullet("after fifteen idle minutes waits 30-50 seconds. Data loss is the failure")
    bullet("that ends a client relationship; a slow first click is not. Spend money on")
    bullet("this the day NEEM's first invoice clears, not before.")

    h(1, "Database — Supabase (5 minutes)")
    bullet("supabase.com → New project. Region: choose the one nearest Nigeria")
    bullet("(eu-west-1 / London is usually the closest available).")
    bullet(f"{Y}Save the database password Supabase makes you set.{X} It is in the")
    bullet("connection string, and you cannot read it back later.")
    bullet("Then: Project Settings → Database → Connection string → URI.")
    bullet(f"Prefer the {B}Session pooler{X} (port 5432). DOCex handles the transaction")
    bullet("pooler on 6543 too — it detects it and turns off prepared statements,")
    bullet("which that mode cannot support — but session mode is simpler.")
    bullet("")
    bullet("Free tier pauses a project only after SEVEN DAYS of no activity. NEEM")
    bullet("using it daily means it never pauses. It has no provider backups,")
    bullet("which is why step 5 is not optional.")

    h(2, "Secrets")
    cmd("python3 go_live.py --secrets")
    bullet("Password manager first. Render second.")

    h(3, "API — Render (10 minutes)")
    bullet("render.com → New → Blueprint → connect this repo → branch demo-release.")
    bullet("Render reads render.yaml and creates docex-api on the free plan.")
    bullet("Then set these in the dashboard (Environment):")
    print()
    bullet(f"  {B}DOCEX_DATABASE_URL{X}   the Supabase URI from step 1")
    bullet(f"  {B}AUTH_SECRET{X}          from step 2")
    bullet(f"  {B}DOCEX_SIGNING_KEY{X}    from step 2")
    bullet(f"  {B}ANTHROPIC_API_KEY{X}    your Claude key")
    bullet(f"  {B}ALLOWED_ORIGINS{X}      the Vercel URL, exactly, no trailing slash")
    bullet(f"  {B}DOCEX_ORG{X}            neem")
    bullet(f"  {B}DOCEX_ENV{X}            production")
    print()
    bullet(f"{D}If a required one is missing the container refuses to start and says{X}")
    bullet(f"{D}which. That is deliberate — the alternative is booting happily and{X}")
    bullet(f"{D}losing every record on the next deploy.{X}")

    h(4, "Configure NEEM")
    cmd("export DOCEX_DATABASE_URL='<the Supabase URI>'")
    cmd("export DOCEX_ORG=neem")
    cmd("python3 org_config.py validate profiles/neem.json")
    cmd("python3 org_config.py apply    profiles/neem.json")
    cmd("python3 org_config.py describe")
    bullet("")
    bullet("Read describe against their signed policy. Then check the profile's")
    bullet("_confirm_before_go_live list — those are open questions for Wednesday,")
    bullet("not settings. A guessed threshold is worse than an empty one: an empty")
    bullet("one gets asked about, a guessed one gets trusted.")

    h(5, "Backups — do this before any real payment")
    bullet("GitHub → Settings → Secrets and variables → Actions → New secret:")
    bullet(f"  {B}DOCEX_DATABASE_URL{X} = the same Supabase URI")
    bullet("Then Actions → backup → Run workflow, and watch it go green.")
    bullet("")
    bullet("It takes a backup and immediately restores it into a scratch database to")
    bullet("check the records come back — including that an active administrator")
    bullet("survives, because a restore nobody can sign in to is not a recovery.")
    bullet(f"{Y}Supabase's free tier has no provider backups. This is the only one.{X}")

    h(6, "Frontend — Vercel")
    bullet("Set NEXT_PUBLIC_API_URL to the Render API URL and redeploy.")
    bullet(f"{Y}It is baked in at build time{X} — changing it in the dashboard does")
    bullet("nothing until you rebuild. And ALLOWED_ORIGINS on the API must contain")
    bullet("this exact origin, or every request fails with an opaque browser error.")

    h(7, "Verify")
    cmd("python3 verify_deployment.py https://<api> --frontend https://<web>")
    bullet("Checks every route the instance actually serves — read from its own")
    bullet("OpenAPI schema, not a list someone maintains by hand — plus CORS,")
    bullet("error leaks and login throttling.")

    h(8, "The one check no script can do")
    bullet("Sign in. Create a requisition. Write the reference down.")
    bullet("Redeploy (Render → Manual Deploy). Wait for the health check.")
    bullet("Sign in. Look for that reference.")
    print()
    bullet(f"  {G}It is there{X}  → storage is durable. Record the date in DEPLOYMENT.md.")
    bullet(f"  {R}It is gone{X}   → STOP. DOCEX_DATABASE_URL is not reaching the app.")
    bullet(f"                  No client data until it does.")

    h(9, "The twenty accounts")
    bullet("Sign in as the admin from step 4 — you will be made to change that")
    bullet("password immediately, which is the point of it.")
    bullet("Then /settings/users. Each person gets a one-time password shown once.")
    bullet("Delete the local users/ directory once you are in.")

    print(f"""
{B}Then, in order of what actually goes wrong{X}

  1. {Y}Upgrade Render to starter ($7){X} the day money arrives. Kills the cold
     start. One word in render.yaml, no data moves.
  2. {Y}Uptime check on /health{X} from outside, alerting to your phone. Sentry
     tells you about crashes; nothing currently tells you it is unreachable.
  3. {Y}Standard ($25){X} when NEEM starts bulk document extraction. Measured:
     139 MB idle, ~250 MB peak on a scanned PDF. Starter is comfortable for
     approvals, tight for bulk.

{D}The full runbook, including rollback, is DEPLOYMENT.md.
The document you hand NEEM is NEEM_SECURITY_SUMMARY.md.{X}
""")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="what is missing locally")
    ap.add_argument("--secrets", action="store_true", help="generate the two keys")
    a = ap.parse_args()
    if a.secrets:
        return cmd_secrets()
    if a.check:
        return cmd_check()
    rc = walkthrough()
    print()
    cmd_check()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
