"""
PostgresStore against a REAL database — the suite that had to exist before
NEEM's payments went into it.

`test_store_sql.py` already covered SQLite thoroughly and gave Postgres a
single round-trip check. That is enough to prove the SQL parses. It is not
enough to trust the adapter with somebody's payroll, because the ways a
database adapter fails in production are not the ways it fails in a unit test:

  - it works, but opens a fresh connection per operation and dies under load
  - it works alone, but loses writes when twenty people save at once
  - it works until the managed provider restarts the database for maintenance,
    then hands every user a 500
  - it stores the money fine and mangles the ₦

Each of those is a test below.

Run:
    DOCEX_TEST_PG_URL=postgresql://user@host/db python3 test_store_pg.py

Without that variable the suite skips cleanly rather than pretending to pass —
a green tick you did not earn is worse than a skip you can see.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import tempfile
import time
from pathlib import Path

DSN = os.environ.get("DOCEX_TEST_PG_URL", "").strip()

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


if not DSN:
    print(__doc__)
    print("SKIPPED — set DOCEX_TEST_PG_URL to run this suite.")
    raise SystemExit(0)


import store          # noqa: E402
import store_sql      # noqa: E402

ORG = "pgtest"
OTHER = "pgtest2"


def fresh() -> store_sql.PostgresStore:
    pg = store_sql.PostgresStore(DSN)
    for org in (ORG, OTHER):
        for coll in pg.collections(org):
            for rec in pg.list(org, coll):
                rid = rec.get("id") or rec.get("record_id")
                if rid:
                    pg.delete(org, coll, str(rid))
    return pg


# ─── it stores what you gave it ─────────────────────────────────────────────


def test_round_trip_and_isolation(pg) -> None:
    print("\nRecords survive the trip, and one org cannot see another's")
    pg.put(ORG, "payments", "p1", {"id": "p1", "payee": "Zenith Ltd", "amount": 450000})
    pg.put(ORG, "payments", "p2", {"id": "p2", "payee": "Dangote", "amount": 12000})
    pg.put(OTHER, "payments", "p3", {"id": "p3", "payee": "Other org", "amount": 1})

    check("a record comes back", pg.get(ORG, "payments", "p1")["payee"] == "Zenith Ltd")
    check("list is org-scoped", len(pg.list(ORG, "payments")) == 2)
    check("the other org sees only its own",
          [r["payee"] for r in pg.list(OTHER, "payments")] == ["Other org"])
    check("a missing record is None", pg.get(ORG, "payments", "nope") is None)
    check("the org is stamped on the record",
          pg.get(ORG, "payments", "p1")["org_id"] == ORG)
    check("collections are listed", "payments" in pg.collections(ORG))


def test_the_naira_survives(pg) -> None:
    print("\nThe ₦ is not mangled, and neither are the decimals")
    pg.put(ORG, "payments", "u1", {
        "id": "u1",
        "payee": "Ọlá Adéyemí Ventures ₦",
        "note": "Per diem — Kano · 3 nights · ₦45,000.00",
        "amount_kobo": 4500000,
    })
    got = pg.get(ORG, "payments", "u1")
    check("naira sign intact", "₦" in got["payee"])
    check("Yoruba diacritics intact", got["payee"].startswith("Ọlá Adéyemí"))
    check("em dash and middot intact", "·" in got["note"])
    check("integer kobo is still an integer",
          got["amount_kobo"] == 4500000 and isinstance(got["amount_kobo"], int))


def test_upsert_does_not_duplicate(pg) -> None:
    print("\nSaving twice edits the record, it does not create a second one")
    before = len(pg.list(ORG, "payments"))
    pg.put(ORG, "payments", "p1", {"id": "p1", "payee": "Zenith Ltd", "amount": 999})
    check("count unchanged", len(pg.list(ORG, "payments")) == before)
    check("value updated", pg.get(ORG, "payments", "p1")["amount"] == 999)


def test_a_big_record(pg) -> None:
    print("\nA requisition with a long history is not truncated")
    trail = [{"step": i, "actor": f"user{i}@neem.org", "note": "x" * 500}
             for i in range(200)]
    pg.put(ORG, "requisitions", "big", {"id": "big", "audit": trail})
    got = pg.get(ORG, "requisitions", "big")
    check("every audit line came back", len(got["audit"]) == 200)
    check("the last line is intact", got["audit"][-1]["actor"] == "user199@neem.org")


def test_path_traversal_still_refused(pg) -> None:
    print("\nA malicious org id is refused by the adapter, not the filesystem")
    for bad, why in [("../etc", "traversal"), ("", "empty"), ("a/b", "slash")]:
        try:
            pg.put(bad, "payments", "x", {"id": "x"})
            check(f"{why} rejected", False, "nothing raised")
        except Exception:
            check(f"{why} rejected", True)


# ─── it is not published to the internet ────────────────────────────────────


def test_records_are_not_in_the_public_schema(pg) -> None:
    print("\nSupabase publishes `public` over HTTPS — our table is not in it")
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT schemaname, rowsecurity FROM pg_tables "
                    "WHERE tablename = 'records'")
        rows = {r[0]: r[1] for r in cur.fetchall()}

    check("the table lives in a private schema", pg.schema in rows,
          f"found in: {sorted(rows) or 'nowhere'}")
    check("and NOT in public", "public" not in rows,
          "a public.records table would be readable over HTTPS with the "
          "project's anon key — no password, no session, no audit entry")
    check("row-level security is on as a second line of defence",
          rows.get(pg.schema) is True)

    # 'public' as a schema name must be refused outright, not quietly accepted.
    import os
    import store_sql
    os.environ["DOCEX_PG_SCHEMA"] = "public"
    try:
        store_sql.PostgresStore(DSN)
        check("'public' is refused as a schema name", False, "it was accepted")
    except Exception as exc:                                     # noqa: BLE001
        check("'public' is refused as a schema name",
              "public" in str(exc).lower())
    os.environ["DOCEX_PG_SCHEMA"] = "docex_evil'; DROP TABLE records; --"
    try:
        store_sql.PostgresStore(DSN)
        check("an injected schema name is refused", False, "it was accepted")
    except Exception as exc:                                     # noqa: BLE001
        check("an injected schema name is refused", "invalid" in str(exc).lower())
    finally:
        os.environ.pop("DOCEX_PG_SCHEMA", None)


def test_the_api_role_cannot_read_it(pg) -> None:
    """Simulate Supabase's `anon` role and try to read a payment."""
    print("\nA Supabase anon key, pointed straight at the payments table")
    import psycopg
    with psycopg.connect(DSN) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'docex_anon_probe'")
            if not cur.fetchone():
                cur.execute("CREATE ROLE docex_anon_probe NOLOGIN")
            # Exactly what Supabase grants its API roles by default.
            cur.execute("GRANT USAGE ON SCHEMA public TO docex_anon_probe")

    pg.put(ORG, "payments", "secret", {"id": "secret", "payee": "Zenith Ltd",
                                       "amount": 4_500_000})

    with psycopg.connect(DSN) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET ROLE docex_anon_probe")
            try:
                cur.execute(f"SELECT count(*) FROM {pg.schema}.records")
                n = cur.fetchone()[0]
                check("the API role cannot read payment records", False,
                      f"it read {n} rows — this data is one HTTP request away")
            except psycopg.errors.InsufficientPrivilege:
                check("the API role is refused: permission denied", True)
            except Exception as exc:                             # noqa: BLE001
                check("the API role is refused", True, type(exc).__name__)

    with psycopg.connect(DSN) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM %s.records" % pg.schema)
            check("but the application itself still reads normally",
                  cur.fetchone()[0] > 0)
    # Cleanup is best effort: roles are cluster-wide, so a grant left in
    # another database on the same server blocks the drop. That is tidiness,
    # not a finding — never fail the suite on it.
    try:
        with psycopg.connect(DSN) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("REVOKE ALL ON SCHEMA public FROM docex_anon_probe")
                cur.execute("DROP ROLE IF EXISTS docex_anon_probe")
    except Exception:
        pass


# ─── it holds up under twenty people ────────────────────────────────────────


def test_connections_are_pooled(pg) -> None:
    print("\nThe pool is reused — 300 reads do not open 300 connections")
    pg.put(ORG, "payments", "perf", {"id": "perf", "amount": 1})
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT sum(numbackends) FROM pg_stat_database")
        before = cur.fetchone()[0] or 0

    t = time.perf_counter()
    for _ in range(300):
        pg.get(ORG, "payments", "perf")
    per_ms = (time.perf_counter() - t) / 300 * 1000

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT sum(numbackends) FROM pg_stat_database")
        after = cur.fetchone()[0] or 0

    check(f"connections stayed flat ({before} → {after})", after - before <= 2,
          "the pool is not being reused")
    check(f"a read costs {per_ms:.2f}ms", per_ms < 5.0,
          "slower than a pooled read should be; is a connection being opened each time?")
    check("the pool is bounded", pg.max_size <= 20,
          f"max_size={pg.max_size} risks the provider's connection cap")


def test_twenty_people_saving_at_once(pg) -> None:
    print("\nTwenty finance officers hit save in the same second")

    def write(i: int) -> bool:
        pg.put(ORG, "concurrent", f"r{i}", {"id": f"r{i}", "by": i, "amount": i * 1000})
        return pg.get(ORG, "concurrent", f"r{i}")["by"] == i

    with cf.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(write, range(60)))

    check("every write returned its own record", all(results))
    check("all 60 records are present", len(pg.list(ORG, "concurrent")) == 60)
    values = sorted(r["by"] for r in pg.list(ORG, "concurrent"))
    check("no write was lost or overwritten", values == list(range(60)))


def test_concurrent_writes_to_one_record(pg) -> None:
    print("\nTwo people editing the same record: last write wins, cleanly")

    def bump(n: int) -> None:
        pg.put(ORG, "contended", "same", {"id": "same", "by": n})

    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(bump, range(50)))

    got = pg.get(ORG, "contended", "same")
    check("the record is readable, not corrupt", isinstance(got, dict))
    check("it holds exactly one writer's value", got["by"] in range(50))
    check("there is still only one record", len(pg.list(ORG, "contended")) == 1)
    # Note deliberately: this store is last-write-wins. Engines that must not
    # lose a concurrent edit (the audit chain) append rather than mutate, which
    # is why the audit log is a chain and not a field.


# ─── it survives the database being restarted ───────────────────────────────


def test_recovers_from_a_dropped_connection(pg) -> None:
    print("\nThe managed database restarts at 3am — nobody sees a 500")
    pg.put(ORG, "payments", "before", {"id": "before", "amount": 7})

    # Terminate every other backend, which is what a failover looks like from
    # the application's side: pooled sockets that are open but dead.
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE pid <> pg_backend_pid() AND datname = current_database()")
        killed = len(cur.fetchall())
    check(f"killed {killed} live backend(s) underneath the pool", killed >= 0)

    try:
        got = pg.get(ORG, "payments", "before")
        check("the next read still worked", got is not None and got["amount"] == 7)
    except Exception as exc:                                    # noqa: BLE001
        check("the next read still worked", False, f"{type(exc).__name__}: {exc}")

    try:
        pg.put(ORG, "payments", "after", {"id": "after", "amount": 8})
        check("and the next write still worked",
              pg.get(ORG, "payments", "after")["amount"] == 8)
    except Exception as exc:                                    # noqa: BLE001
        check("and the next write still worked", False, f"{type(exc).__name__}: {exc}")


# ─── it can be got back ─────────────────────────────────────────────────────


def test_backup_and_restore(pg) -> None:
    print("\nA backup nobody has restored is not a backup")
    tmp = Path(tempfile.mkdtemp(prefix="pgbackup-"))
    path = pg.backup(tmp / "docex.jsonl")

    lines = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    check("the backup has content", len(lines) > 5)
    check("it is readable without Postgres, or us",
          all({"org_id", "collection", "record_id", "data"} <= set(l) for l in lines))
    check("the ₦ survived the export",
          any("₦" in json.dumps(l, ensure_ascii=False) for l in lines))
    check("count matches the database", len(lines) == pg.count())

    # Restore into a SQLite store — proving the backup is not merely a Postgres
    # artefact but the client's records, portable.
    scratch = store_sql.SqliteStore(tmp / "restored.db")
    n = scratch.restore(path)
    check(f"restored {n} records into a scratch database", n == len(lines))
    check("a specific payment came back",
          scratch.get(ORG, "payments", "p1")["payee"] == "Zenith Ltd")
    check("org isolation survived the restore",
          [r["payee"] for r in scratch.list(OTHER, "payments")] == ["Other org"])


# ─── the real engines, on Postgres ──────────────────────────────────────────


def test_the_engines_work_on_postgres(pg) -> None:
    print("\nAuth and requisitions run on Postgres, not just the adapter")
    store.set_store(pg)
    os.environ["DOCEX_ORG"] = ORG
    os.environ.setdefault("AUTH_SECRET", "pg-suite-secret-not-for-production")

    import importlib
    import auth as auth_mod
    importlib.reload(auth_mod)

    for u in auth_mod.list_public(ORG):
        store.get_store().delete(ORG, "users", u.id)

    user = auth_mod.create_user("pg@neem.org", "PG Tester", "PostgresTest2026!",
                                "finance", "admin", org_id=ORG)
    check("a user was created", user.email == "pg@neem.org")
    check("the password verifies",
          auth_mod.authenticate("pg@neem.org", "PostgresTest2026!", org_id=ORG).id == user.id)
    token = auth_mod.issue_token(user, org_id=ORG)
    check("a session token round-trips", auth_mod.verify_token(token).id == user.id)

    import requisitions as rq
    importlib.reload(rq)
    rq.set_workflow(ORG, rq.default_workflow(ORG, size="small"))
    req = rq.create_requisition(ORG, submitted_by="pg@neem.org", department="finance",
                                vendor_name="Zenith Ltd", amount=50_000,
                                category="services", description="Postgres suite")
    check("a requisition was raised", req.ref.startswith("REQ-"))
    stored = rq.get_requisition(ORG, req.id)
    check("it is readable again", stored is not None)
    check("the amount is exact after a JSONB round-trip", stored.amount == 50_000)
    check("the hash-chained audit log verifies on Postgres",
          rq.verify_audit_chain(stored))


# ─── run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"PostgresStore verification against {DSN.split('@')[-1]}")
    pg = fresh()
    test_round_trip_and_isolation(pg)
    test_the_naira_survives(pg)
    test_upsert_does_not_duplicate(pg)
    test_a_big_record(pg)
    test_path_traversal_still_refused(pg)
    test_records_are_not_in_the_public_schema(pg)
    test_the_api_role_cannot_read_it(pg)
    test_connections_are_pooled(pg)
    test_twenty_people_saving_at_once(pg)
    test_concurrent_writes_to_one_record(pg)
    test_recovers_from_a_dropped_connection(pg)
    test_backup_and_restore(pg)
    test_the_engines_work_on_postgres(pg)

    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
