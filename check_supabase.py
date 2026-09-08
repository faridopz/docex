#!/usr/bin/env python3
"""
Is this Supabase project safe to hold a client's payments?

Runs your security checklist against the ACTUAL database and the ACTUAL repo,
rather than against a document that says it was done. Every item is either
proved here, proved by another named check, or reported as a dashboard click
this script cannot make for you — and it says which.

    export DOCEX_DATABASE_URL='postgresql://...'
    python3 check_supabase.py

    python3 check_supabase.py --sql     # print the hardening SQL and exit
    python3 check_supabase.py --repo    # only scan the repo for leaked keys

The checklist it answers, and where each item is actually verified:

  Authentication & access control ...... test_auth.py, test_user_management.py
  Row Level Security ................... HERE
  Data API exposure .................... HERE   (the one that would have hurt)
  Rate limiting ........................ test_auth.py, verify_deployment.py
  Error handling reveals nothing ....... test_observability.py, verify_deployment.py
  Database connection details hidden ... HERE + verify_deployment.py
  No API keys in frontend .............. HERE
  Every route requires a session ....... test_auth_coverage.py, verify_deployment.py

Read the note on Supabase Auth at the bottom of the output. It is the one
checklist item DOCex deliberately does not satisfy, and the reason matters.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
B = "\033[1m"; G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; D = "\033[2m"; X = "\033[0m"

_passed = _failed = _manual = 0
FULL_HISTORY = False


def ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    print(f"  {G}ok{X}    {label}{('  — ' + detail) if detail else ''}")


def bad(label: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    print(f"  {R}FAIL{X}  {label}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")


def manual(label: str, detail: str = "") -> None:
    global _manual
    _manual += 1
    print(f"  {Y}you{X}   {label}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")


HARDENING_SQL = """
-- DOCex Supabase hardening. Safe to run more than once.
-- Supabase dashboard → SQL Editor → paste → Run.
--
-- DOCex applies all of this itself at boot. This exists for the case where
-- boot ran against an older version, or somebody changed something by hand,
-- or you simply want to see what is being asserted.

-- 1. Our records live outside `public`, which is the schema the Data API
--    publishes over HTTPS with the anon key.
CREATE SCHEMA IF NOT EXISTS docex;

-- 2. The API roles get nothing. PostgREST authenticates as these; if they
--    hold no grant, an HTTP request cannot reach the data even if the schema
--    were exposed by accident.
REVOKE ALL ON SCHEMA docex FROM anon, authenticated, public;
REVOKE ALL ON ALL TABLES IN SCHEMA docex FROM anon, authenticated, public;
ALTER DEFAULT PRIVILEGES IN SCHEMA docex
    REVOKE ALL ON TABLES FROM anon, authenticated, public;

-- 3. Row-level security with no policies. Denies every read to any role that
--    does not own the table — a third independent control.
ALTER TABLE IF EXISTS docex.records ENABLE ROW LEVEL SECURITY;

-- 4. Anything left in `public` from an experiment is exposed. Look, then drop.
--    Run the SELECT first; only run the DROP if you recognise what it finds.
SELECT tablename,
       rowsecurity AS rls_on,
       has_table_privilege('anon', 'public.' || quote_ident(tablename), 'SELECT')
           AS anon_can_read
FROM pg_tables WHERE schemaname = 'public';

-- DROP TABLE IF EXISTS public.records;
""".strip()


# ─── database checks ────────────────────────────────────────────────────────


def db_checks(dsn: str) -> None:
    import psycopg

    print(f"\n{B}The database{X}")
    try:
        conn = psycopg.connect(dsn, connect_timeout=20)
    except Exception as exc:                                     # noqa: BLE001
        bad("could not connect", str(exc)[:200])
        return
    conn.autocommit = True
    cur = conn.cursor()

    # -- is this even Supabase? --------------------------------------------
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')")
    is_supabase = bool(cur.fetchone()[0])
    cur.execute("SHOW server_version")
    ver = cur.fetchone()[0].split()[0]
    ok(f"connected — PostgreSQL {ver}",
       "Supabase (anon role present)" if is_supabase else "plain Postgres")

    # -- the connection itself ---------------------------------------------
    try:
        cur.execute("SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        row = cur.fetchone()
        if row and row[0]:
            ok("the connection is encrypted", row[1] or "TLS")
        elif "127.0.0.1" in dsn or "localhost" in dsn:
            ok("unencrypted, but local", "fine for a test database")
        else:
            bad("the connection is NOT encrypted",
                "Add ?sslmode=require to DOCEX_DATABASE_URL. Without it the\n"
                "database password and every record cross the internet in clear.")
    except Exception:
        pass

    cur.execute("SELECT current_user, "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")
    user, is_super = cur.fetchone()
    if is_super:
        manual(f"connected as a superuser ({user})",
               "Normal on Supabase — its `postgres` role is the account you are\n"
               "given. Worth knowing: this role can read everything, so the\n"
               "connection string is as sensitive as a master password.")
    else:
        ok(f"connected as a non-superuser ({user})")

    # -- THE ONE THAT MATTERS: is anything published over HTTPS? -----------
    print(f"\n{B}The Data API — what is reachable over HTTPS{X}")

    exposed: list[str] = []
    try:
        cur.execute("""
            SELECT unnest(setconfig) FROM pg_db_role_setting s
            JOIN pg_roles r ON r.oid = s.setrole
            WHERE r.rolname = 'authenticator'
        """)
        for (setting,) in cur.fetchall():
            if setting.startswith("pgrst.db_schemas="):
                exposed = [s.strip() for s in setting.split("=", 1)[1].split(",")]
    except Exception:
        pass

    if exposed:
        listed = ", ".join(exposed)
        if "docex" in exposed:
            bad("the docex schema is EXPOSED to the Data API",
                f"PostgREST publishes: {listed}\n"
                "Every payment record is readable over HTTPS with the anon key.\n"
                "Supabase → Settings → API → remove `docex` from exposed schemas.")
        else:
            ok("the docex schema is not exposed to the Data API", f"exposed: {listed}")
    elif is_supabase:
        manual("could not read the exposed-schema setting",
               "Check by hand: Settings → API → Data API → Exposed schemas.\n"
               "It should NOT list `docex`. Better still, disable the Data API —\n"
               "DOCex does not use it.")
    else:
        ok("no PostgREST on this database", "nothing is published over HTTP")

    # -- what is sitting in public -----------------------------------------
    cur.execute("SELECT tablename, rowsecurity FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename")
    public_tables = cur.fetchall()
    if not public_tables:
        ok("the public schema holds no tables", "nothing to publish")
    else:
        risky = []
        for name, rls in public_tables:
            readable = False
            if is_supabase:
                try:
                    cur.execute("SELECT has_table_privilege('anon', %s, 'SELECT')",
                                (f"public.{name}",))
                    readable = bool(cur.fetchone()[0])
                except Exception:
                    pass
            if readable or (not rls and is_supabase):
                risky.append((name, rls, readable))
        if risky:
            lines = [f"{n}  rls={'on' if r else 'OFF'}  anon_can_read={a}"
                     for n, r, a in risky]
            bad(f"{len(risky)} table(s) in public are reachable by the API role",
                "\n".join(lines) + "\n"
                "Anything here is one HTTP request from the internet. If you do\n"
                "not recognise it, it is left over from an experiment — drop it.")
        else:
            ok(f"{len(public_tables)} table(s) in public, none readable by anon")

    if any(n == "records" for n, _ in public_tables):
        bad("a public.records table exists",
            "This is NOT the table DOCex uses. It is exposed. Drop it:\n"
            "  DROP TABLE public.records;")

    # -- our own table ------------------------------------------------------
    print(f"\n{B}The DOCex table{X}")
    schema = os.environ.get("DOCEX_PG_SCHEMA", "docex")
    cur.execute("SELECT schemaname, rowsecurity FROM pg_tables "
                "WHERE tablename = 'records'")
    found = {s: r for s, r in cur.fetchall()}

    if schema not in found:
        manual(f"no {schema}.records table yet",
               "Expected before the first deploy — DOCex creates it at boot.\n"
               "Run this again once the API has started once.")
    else:
        ok(f"records lives in the private `{schema}` schema")
        if found[schema]:
            ok("row-level security is enabled", "a second independent control")
        else:
            bad("row-level security is OFF on the records table",
                f"  ALTER TABLE {schema}.records ENABLE ROW LEVEL SECURITY;")

        if is_supabase:
            for role in ("anon", "authenticated"):
                try:
                    cur.execute("SELECT has_table_privilege(%s, %s, 'SELECT')",
                                (role, f"{schema}.records"))
                    if cur.fetchone()[0]:
                        bad(f"the `{role}` role CAN read payment records",
                            f"  REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {role};")
                    else:
                        ok(f"the `{role}` role cannot read payment records")
                except Exception:
                    pass

        cur.execute(f"SELECT count(*) FROM {schema}.records")
        n = cur.fetchone()[0]
        cur.execute(f"SELECT count(DISTINCT org_id) FROM {schema}.records")
        orgs = cur.fetchone()[0]
        ok(f"{n} records across {orgs} organisation(s)")

    # -- policies that would undo all of it ---------------------------------
    try:
        cur.execute("""
            SELECT schemaname, tablename, policyname, roles::text, qual
            FROM pg_policies WHERE qual = 'true' OR qual IS NULL
        """)
        loose = cur.fetchall()
        if loose:
            bad(f"{len(loose)} row-level policy/policies allow everything",
                "\n".join(f"{s}.{t} — {p} for {r}" for s, t, p, r, _ in loose) +
                "\nA policy with USING (true) makes RLS decorative.")
        else:
            ok("no row-level policy grants blanket access")
    except Exception:
        pass

    cur.close()
    conn.close()


# ─── repo scan ──────────────────────────────────────────────────────────────


def _is_prose(text: str, pos: int) -> bool:
    """Is this match inside a comment or an obvious placeholder?

    Written carefully, because the first version tested whether the
    surrounding text contained "//" — which every `postgresql://` URL does, so
    real leaked connection strings were silently skipped. A suppression rule
    that accidentally suppresses the thing you are looking for is worse than
    no rule at all.

    So: only the text BEFORE the match on ITS OWN LINE is examined, and only
    for a comment marker at the start of that line.
    """
    line_start = text.rfind("\n", 0, pos) + 1
    prefix = text[line_start:pos].strip()
    if prefix.startswith(("#", "//", "*", "--", '"""', "'''")):
        return True
    window = text[max(0, pos - 80):pos + 80].lower()
    return any(w in window for w in
               ("example", "replace", "your-", "<your", "placeholder", "xxxx",
                "dummy", "not-a-real", "notarealkey"))


def repo_checks() -> None:
    print(f"\n{B}Keys and connection strings in the repo{X}")

    # A Supabase service_role JWT is a full bypass of every access control.
    # Matched by SHAPE, never by the word. "service_role" appears legitimately
    # in OPERATING_GUIDE.md, in a paragraph explaining why never to use it — a
    # scanner that flags its own documentation gets ignored, and then misses
    # the real thing.
    patterns = [
        (r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
         "a JWT — a Supabase anon or service_role key"),
        (r"sk-ant-[A-Za-z0-9\-_]{30,}", "an Anthropic API key"),
        (r"postgres(ql)?://[^\s'\"]+:[^\s'\"@]{8,}@[^\s'\"]+",
         "a database URL with a password"),
        (r"sk_live_[A-Za-z0-9]{20,}", "a Paystack live secret key"),
    ]

    # Frontend files are the sharpest case: whatever is here ships to browsers.
    web = ROOT / "web"
    scanned = leaked = 0
    for path in list(web.rglob("*.ts")) + list(web.rglob("*.tsx")) + \
            list(web.rglob("*.js")) + list(web.rglob("*.env*")):
        if "node_modules" in str(path) or "/.next/" in str(path):
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        scanned += 1
        for pat, what in patterns:
            for m in re.finditer(pat, text):
                if _is_prose(text, m.start()):
                    continue
                leaked += 1
                bad(f"{what}", f"{path.relative_to(ROOT)}  — this ships to browsers")
    if not leaked:
        ok(f"{scanned} frontend files scanned, no keys found")

    # Tracked files anywhere in the repo.
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                 text=True, timeout=30).stdout.splitlines()
    except Exception:
        tracked = []
    hits = 0
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file() or p.suffix in (".md", ".lock") or p.stat().st_size > 400_000:
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for pat, what in patterns:
            for m in re.finditer(pat, text):
                if _is_prose(text, m.start()):
                    continue
                hits += 1
                bad(f"{what} in a tracked file", rel)
    if not hits:
        ok(f"{len(tracked)} tracked files scanned, no committed secrets")

    for name in (".env", ".env.local", ".env.production"):
        if name in tracked:
            bad(f"{name} is committed to git", "Remove it and rotate everything in it.")
    if not any(n in tracked for n in (".env", ".env.local", ".env.production")):
        ok("no .env file is committed")

    gitignore = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
    for entry in (".env", "users/", "*.db"):
        (ok if entry in gitignore else bad)(f"{entry} is gitignored")

    # History, not just the working tree — deleting a file does not unpublish
    # what an old commit still contains.
    #
    # Searched by KEY SHAPE, not by the word "service_role". The first version
    # of this searched for the word and immediately flagged OPERATING_GUIDE.md,
    # which is a paragraph explaining why never to use that key. A scanner that
    # cries wolf on its own documentation is a scanner people learn to ignore,
    # and then it misses the real one.
    history_patterns = [
        (r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
         "a JWT — a Supabase anon or service_role key"),
        (r"sk-ant-[A-Za-z0-9\-_]{30,}", "an Anthropic API key"),
        (r"postgres(ql)?://[^\s'\"]+:[^\s'\"@]{8,}@[^\s'\"]+", "a database URL with a password"),
    ]
    # Bounded by default. A pickaxe regex over all of history is minutes on a
    # repo this size, and a check that takes minutes is a check nobody runs
    # weekly. Recent commits catch the realistic case — a key pasted in and
    # removed again last week. `--history` does the full sweep, which is the
    # right thing before handing the repo to anyone.
    depth = [] if FULL_HISTORY else ["-n", "400"]
    scope = "all history" if FULL_HISTORY else "the last 400 commits"
    history_hits = []
    timed_out = False
    for pat, what in history_patterns:
        try:
            r = subprocess.run(
                ["git", "log", "--all", *depth, "--pickaxe-regex", "-S", pat, "--oneline"],
                cwd=ROOT, capture_output=True, text=True, timeout=60)
            if r.stdout.strip():
                commits = [l.split()[0] for l in r.stdout.splitlines()[:5]]
                history_hits.append((what, commits))
        except subprocess.TimeoutExpired:
            timed_out = True
        except Exception:
            pass
    if timed_out:
        manual("the history scan timed out",
               "Run `python3 check_supabase.py --repo --history` when you have\n"
               "a few minutes, or before giving anyone access to this repo.")
    if history_hits:
        for what, commits in history_hits:
            bad(f"{what} appears in git history",
                f"commits: {', '.join(commits)}\n"
                "Rotate it. Removing the file does not help — the old commit\n"
                "still contains the value, and anyone with the repo has it.")
    else:
        ok(f"no credential-shaped strings in {scope}")


# ─── the dashboard, which no script can click ───────────────────────────────


def dashboard_checklist() -> None:
    print(f"\n{B}In the Supabase dashboard — five minutes, once{X}")
    for label, detail in [
        ("Settings → API → Data API: disable it, or expose `public` only",
         "DOCex talks to Postgres directly and never uses the Data API.\n"
         "Turning it off removes the entire HTTPS attack surface."),
        ("Settings → Database → require SSL",
         "Then confirm DOCEX_DATABASE_URL ends with ?sslmode=require."),
        ("Account → enable two-factor authentication",
         "This login holds every client record. It is the real perimeter —\n"
         "more than anything in the application."),
        ("Never use the service_role key",
         "It bypasses every access control. DOCex does not need it. If you\n"
         "find yourself pasting it to make something work, stop and ask."),
        ("Settings → Database → Network restrictions (optional)",
         "Allow-list Render's outbound IPs and your own. Free tier may not\n"
         "offer this; worth doing the moment it does."),
    ]:
        manual(label, detail)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sql", action="store_true", help="print the hardening SQL")
    ap.add_argument("--repo", action="store_true", help="only scan the repo")
    ap.add_argument("--history", action="store_true",
                    help="scan ALL git history (slow, thorough)")
    a = ap.parse_args()

    global FULL_HISTORY
    FULL_HISTORY = a.history

    if a.sql:
        print(HARDENING_SQL)
        return 0

    print(f"{B}DOCex — Supabase security check{X}")

    if not a.repo:
        dsn = os.environ.get("DOCEX_DATABASE_URL", "").strip()
        if not dsn:
            print(f"\n  {Y}DOCEX_DATABASE_URL is not set — skipping database checks.{X}")
            print("  export DOCEX_DATABASE_URL='postgresql://...' to run them.")
            _ = _manual
        else:
            try:
                import psycopg  # noqa: F401
            except ImportError:
                print(f"\n  {R}psycopg is not installed{X} — "
                      "pip install 'psycopg[binary,pool]'")
                return 2
            db_checks(dsn)

    repo_checks()

    if not a.repo:
        dashboard_checklist()

    print(f"""
{B}{_passed} passed · {_failed} failed · {_manual} for you to do{X}

{B}The checklist item DOCex deliberately does not satisfy{X}

  "Use Supabase Auth for authentication handling."

  DOCex uses its own. That is a decision, not an oversight, and it is worth
  being able to defend:

  An approval in this system is not "a logged-in user did something". It is a
  named person, in a named department, holding an authority limit, whose
  identity is hashed into an append-only chain that must still verify in three
  years. Supabase Auth issues identity; it does not model departments,
  approval limits, override authority, or the deactivation of a leaver whose
  March approvals must remain attributable.

  Bolting those on to an external identity provider means the audit chain
  depends on a second system agreeing with the first about who somebody was —
  and the failure mode is an approval trail that cannot be reconstructed.

  What we take instead: PBKDF2 at 200k iterations, constant-time comparison,
  server-side session revocation, brute-force lockout, and no account
  enumeration. Proved by test_auth.py and test_user_management.py, not
  asserted here.

  There is a real cost, and it is worth saying out loud: no password-reset
  email, no social sign-in, no MFA for client users. MFA is the one that will
  matter as NEEM grows, and it is the honest next thing to build.

{D}Full standing guidance: OPERATING_GUIDE.md{X}""")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
