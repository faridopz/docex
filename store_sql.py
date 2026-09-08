"""
Durable SQL storage for DOCex — SQLite today, Postgres when you want cloud.

WHY NOT WRITE OUR OWN DATABASE
A finance/audit product's core promise is "these records are complete and
uncorrupted". Delivering that means crash-safe durability, write-ahead logging,
ACID transactions, concurrent writers, indexing, and point-in-time recovery —
years of work whose failure mode is silent data loss discovered during an audit.
So DOCex rents the storage engine and owns the part that actually matters: the
schema, the engines, and the audit model. Nothing here locks us to a vendor —
the same code runs on a laptop file or a managed Postgres.

ONE TABLE, TWO ENGINES
Everything lands in a single `records` table keyed by (org_id, collection,
record_id) with a JSON payload. That keeps the adapter tiny and identical across
SQLite and Postgres, while the org_id in the primary key preserves the hard
tenant isolation the JSON store already gives us.

  SQLite   — stdlib, zero servers, one file. WAL mode + synchronous=FULL so a
             crash or power cut can't lose a committed write. Ideal for an NGO
             self-hosting on one machine.
  Postgres — same SQL with JSONB and an upsert, over a checked connection
             pool. Use for multi-user cloud. Requires `psycopg` (v3) and
             `psycopg_pool`. Verified against a live PostgreSQL 16, including
             concurrent writers and recovery from a database restart — see
             `test_store_pg.py`.

Swap it in at startup:
    import store, store_sql
    store.set_store(store_sql.SqliteStore("docex.db"))
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from store import StoreError, _validate

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS records (
    org_id     TEXT NOT NULL,
    collection TEXT NOT NULL,
    record_id  TEXT NOT NULL,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (org_id, collection, record_id)
);
CREATE INDEX IF NOT EXISTS idx_records_org_collection
    ON records (org_id, collection);
"""

# NOT IN THE `public` SCHEMA — this is a security control, not tidiness.
#
# Supabase (and any Postgres fronted by PostgREST) publishes every table in
# `public` as an HTTPS REST endpoint, readable with the project's `anon` key.
# That key is designed to be public: it ships inside frontend bundles and is
# printed in the dashboard. A `public.records` table would therefore put every
# requisition, approval, vendor bank detail and payment amount one HTTP request
# away from anyone who learned the project URL — no password, no session, no
# trace in our audit log.
#
# The Data API only exposes schemas it has been told to expose, and `docex` is
# not one of them. So the table lives here, and the grants below remove it from
# the API roles as well. Two independent controls, because the cost of getting
# this wrong is a client's entire payment history.
_PG_SCHEMA_DEFAULT = "docex"

_SCHEMA_POSTGRES = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.records (
    org_id     TEXT NOT NULL,
    collection TEXT NOT NULL,
    record_id  TEXT NOT NULL,
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, collection, record_id)
);
CREATE INDEX IF NOT EXISTS idx_records_org_collection
    ON {schema}.records (org_id, collection);

-- Row-level security with no policies: a belt to the schema's braces. Even if
-- someone later exposes this schema to the Data API, RLS denies every read to
-- the API roles because no policy grants one. The owning role we connect as
-- bypasses RLS, so the application is unaffected.
ALTER TABLE {schema}.records ENABLE ROW LEVEL SECURITY;
"""

# Revoke from the roles PostgREST authenticates as. Wrapped in a DO block that
# checks each role exists first, because on a plain Postgres — a laptop, a CI
# runner, Render's own database — `anon` and `authenticated` do not exist and a
# bare REVOKE would abort the whole schema setup.
_REVOKE_API_ROLES = """
DO $$
DECLARE r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'public'] LOOP
        IF r = 'public' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA {schema} FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM %I', r);
        END IF;
    END LOOP;
END $$;
"""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class SqliteStore:
    """Durable local storage. ACID, crash-safe, single file, no server.

    Concurrency: WAL lets many readers run alongside one writer, which matches
    DOCex's shape (a handful of finance users). `synchronous=FULL` trades a
    little speed for the guarantee that a committed transaction survives a power
    loss — the right trade for audit records.
    """

    def __init__(self, path: Path | str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False: FastAPI serves requests from a thread pool.
        # Each call opens its own short-lived connection, so there's no shared
        # cursor state to corrupt.
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQLITE)

    # ── Store protocol ───────────────────────────────────────────────────────

    def put(self, org_id: str, collection: str, record_id: str, data: dict) -> dict:
        org = _validate(org_id, "org id")
        coll = _validate(collection, "collection")
        rid = _validate(record_id, "record id")
        payload = {**data, "org_id": org}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO records (org_id, collection, record_id, data, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(org_id, collection, record_id)
                DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
                """,
                (org, coll, rid, json.dumps(payload, default=str), _now_iso()),
            )
        return payload

    def get(self, org_id: str, collection: str, record_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM records WHERE org_id=? AND collection=? AND record_id=?",
                (_validate(org_id, "org id"), _validate(collection, "collection"),
                 _validate(record_id, "record id")),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except Exception as exc:
            print(f"Warning: corrupt record {org_id}/{collection}/{record_id}: {exc}")
            return None

    def list(self, org_id: str, collection: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT record_id, data FROM records WHERE org_id=? AND collection=? "
                "ORDER BY record_id",
                (_validate(org_id, "org id"), _validate(collection, "collection")),
            ).fetchall()
        out: list[dict] = []
        for rid, raw in rows:
            try:
                out.append(json.loads(raw))
            except Exception as exc:
                print(f"Warning: skipping corrupt record {rid}: {exc}")
        return out

    def delete(self, org_id: str, collection: str, record_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM records WHERE org_id=? AND collection=? AND record_id=?",
                (_validate(org_id, "org id"), _validate(collection, "collection"),
                 _validate(record_id, "record id")),
            )
            return cur.rowcount > 0

    def collections(self, org_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT collection FROM records WHERE org_id=? ORDER BY collection",
                (_validate(org_id, "org id"),),
            ).fetchall()
        return [r[0] for r in rows]

    # ── operational helpers ──────────────────────────────────────────────────

    def backup(self, destination: Path | str) -> str:
        """Consistent online backup — safe to run while the app is serving.
        Use it on a schedule; a database without backups isn't durable."""
        dest = str(destination)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as src, sqlite3.connect(dest) as dst:
            src.backup(dst)
        return dest

    def count(self, org_id: Optional[str] = None) -> int:
        with self._connect() as conn:
            if org_id:
                row = conn.execute("SELECT COUNT(*) FROM records WHERE org_id=?",
                                   (_validate(org_id, "org id"),)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM records").fetchone()
        return int(row[0])

    def export_jsonl(self, destination: Path | str) -> str:
        """A backup that does not need SQLite — or us — to read.

        `backup()` above produces a .db file, which is the right thing to
        restore from quickly. This produces the same records as plain text, one
        JSON object per line, because the question an auditor eventually asks is
        not "can you restore it" but "can we read our own records without you".
        Both are written by the backup job; they answer different questions.
        """
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn, dest.open("w", encoding="utf-8") as fh:
            rows = conn.execute(
                "SELECT org_id, collection, record_id, data FROM records "
                "ORDER BY org_id, collection, record_id").fetchall()
            for org, coll, rid, raw in rows:
                fh.write(json.dumps({
                    "org_id": org, "collection": coll, "record_id": rid,
                    "data": json.loads(raw),
                }, ensure_ascii=False) + "\n")
        return str(dest)

    def restore(self, source: Path | str) -> int:
        """Load a JSON Lines backup. Upserts, so replaying it is harmless."""
        n = 0
        with Path(source).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                self.put(rec["org_id"], rec["collection"], rec["record_id"], rec["data"])
                n += 1
        return n


class PostgresStore:
    """Same contract, managed Postgres underneath — for multi-user cloud.

    WHY A CONNECTION POOL
    The first version of this class opened a fresh connection for every single
    read and write. That is correct and it passes every functional test, which
    is exactly what makes it dangerous: it fails only under load, in production,
    on somebody's payroll day.

    Measured against a real PostgreSQL 16 on localhost, connection-per-operation
    cost 6.5ms per read versus 0.54ms on a reused connection — twelve times
    slower with no network and no TLS in the way. Managed Postgres is a separate
    host and insists on TLS, so the handshake there is tens of milliseconds. A
    dashboard that touches a hundred records would have spent seconds doing
    nothing but shaking hands.

    The second failure is harder. Managed Postgres caps concurrent connections.
    Twenty finance officers, each request opening and dropping connections as
    fast as the app can, walks into that cap and into TIME_WAIT socket
    exhaustion. The error surfaces as "too many connections" — during month end,
    to the client, not to us.

    So connections are pooled, reused, health-checked, and a query that fails on
    a connection the database closed underneath us (maintenance, failover) is
    retried once. A finance user should never see a 500 because their database
    was restarted while they were reading.
    """

    #: Tune with DOCEX_PG_POOL_MAX. Kept well under a managed instance's cap so
    #: several app instances and a psql session can coexist.
    DEFAULT_MAX = 10

    def __init__(self, dsn: str, *, min_size: int = 1, max_size: Optional[int] = None):
        try:
            import psycopg  # noqa: F401
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise StoreError(
                "PostgresStore needs psycopg v3 and its pool: "
                "pip install 'psycopg[binary,pool]'."
            ) from exc

        import os
        import re as _re
        self.dsn = dsn
        # Identifier, not a value — it is interpolated into DDL, so it is
        # restricted rather than escaped.
        raw_schema = (os.environ.get("DOCEX_PG_SCHEMA", "").strip()
                      or _PG_SCHEMA_DEFAULT)
        if not _re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", raw_schema):
            raise StoreError(
                f"Invalid DOCEX_PG_SCHEMA {raw_schema!r}: lowercase letters, "
                "digits and underscores only.")
        if raw_schema == "public":
            raise StoreError(
                "DOCEX_PG_SCHEMA must not be 'public'. A Data API (Supabase, "
                "PostgREST) publishes every table in the public schema over "
                "HTTPS with a key that is designed to be public — that would "
                "make every payment record readable without a session.")
        self.schema = raw_schema
        if max_size is None:
            try:
                max_size = int(os.environ.get("DOCEX_PG_POOL_MAX", "") or self.DEFAULT_MAX)
            except ValueError:
                max_size = self.DEFAULT_MAX
        self.max_size = max(1, int(max_size))

        # PREPARED STATEMENTS AND POOLERS
        # psycopg3 promotes a query to a server-side prepared statement after
        # it has run a few times. That is a straight win against a real
        # Postgres and a hard failure against a transaction-mode connection
        # pooler (Supabase's port 6543, PgBouncer, Supavisor): the pooler hands
        # the next query to a different backend, which has never heard of the
        # prepared statement, and you get "prepared statement _pg3_0 does not
        # exist" — intermittently, under load, never on a laptop.
        #
        # Detected from the DSN rather than left as a flag somebody must
        # remember, because the failure appears weeks later and looks like a
        # database fault rather than a configuration one.
        lowered = dsn.lower()
        pooled_upstream = (":6543" in lowered or "pooler" in lowered
                           or "pgbouncer" in lowered)
        override = os.environ.get("DOCEX_PG_PREPARE", "").strip().lower()
        if override in ("0", "off", "false", "no"):
            pooled_upstream = True
        elif override in ("1", "on", "true", "yes"):
            pooled_upstream = False
        self.prepared_statements = not pooled_upstream

        kwargs = {} if self.prepared_statements else {"prepare_threshold": None}

        from psycopg_pool import ConnectionPool as _Pool
        self._pool = _Pool(
            dsn,
            min_size=min(min_size, self.max_size),
            max_size=self.max_size,
            kwargs=kwargs,
            # Hand out a connection only after checking it is alive. Costs one
            # cheap round trip; saves handing a finance user a dead socket after
            # the database was restarted.
            check=_Pool.check_connection,
            timeout=30.0,
            max_lifetime=30 * 60,
            name="docex",
        )
        if pooled_upstream:
            print("[store] Connection pooler detected — server-side prepared "
                  "statements disabled.", flush=True)
        self._pool.wait(timeout=30.0)
        self._init_schema()

    # ── plumbing ─────────────────────────────────────────────────────────────

    def _run(self, sql: str, params: tuple, *, fetch: str = "none"):
        """Execute inside a pooled connection, retrying once on a dead socket.

        `fetch` is "none", "one", "all" or "rowcount". The retry covers exactly
        one case — the connection was closed by the server between the health
        check and the query — and deliberately does not cover query errors,
        which must surface.

        `{t}` in the SQL becomes the fully qualified table name. Every query
        goes through here, so the schema cannot be forgotten in a new method —
        and a bare `records` would not silently resolve to a `public` table
        that a Data API might publish, it would simply fail.
        """
        sql = sql.format(t=f"{self.schema}.records")
        import psycopg
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                with self._pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(sql, params)
                        if fetch == "one":
                            return cur.fetchone()
                        if fetch == "all":
                            return cur.fetchall()
                        if fetch == "rowcount":
                            return cur.rowcount
                        return None
            except psycopg.OperationalError as exc:
                last = exc
                if attempt == 2:
                    break
        raise StoreError(f"Database unavailable: {last}") from last

    def _init_schema(self) -> None:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(_SCHEMA_POSTGRES.format(schema=self.schema))
            try:
                cur.execute(_REVOKE_API_ROLES.format(schema=self.schema))
            except Exception as exc:                  # pragma: no cover
                # Not fatal: the schema itself already keeps this table off the
                # Data API. Say so loudly rather than silently, because "we
                # thought it was locked down" is how data gets published.
                print(f"[store] Note: could not revoke API-role access "
                      f"({exc}). The '{self.schema}' schema is still not "
                      "exposed by default — verify in the provider's API "
                      "settings.", flush=True)

        # Prove it, rather than assume the DDL did what it said. One cheap
        # query at boot, and a wrong answer here means client records are
        # reachable over the internet.
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT schemaname, rowsecurity FROM pg_tables "
                "WHERE tablename = 'records' AND schemaname IN ('public', %s)",
                (self.schema,))
            found = {row[0]: row[1] for row in cur.fetchall()}
        if "public" in found:
            print("[store] WARNING: a `public.records` table exists. If this "
                  "database is fronted by a Data API (Supabase, PostgREST), "
                  "that table is readable over HTTPS with the project's public "
                  "anon key. It is NOT the table DOCex uses — drop it.",
                  flush=True)
        if self.schema not in found:
            raise StoreError(
                f"Schema setup did not create {self.schema}.records. Refusing "
                "to continue rather than fall back to a table that may be "
                "publicly readable.")

    def close(self) -> None:
        """Release pooled connections. Call on shutdown; safe to call twice."""
        try:
            self._pool.close()
        except Exception:  # pragma: no cover - shutdown is best effort
            pass

    # ── Store protocol ───────────────────────────────────────────────────────

    def put(self, org_id: str, collection: str, record_id: str, data: dict) -> dict:
        org = _validate(org_id, "org id")
        payload = {**data, "org_id": org}
        self._run(
            """
            INSERT INTO {t} (org_id, collection, record_id, data, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (org_id, collection, record_id)
            DO UPDATE SET data = EXCLUDED.data, updated_at = now()
            """,
            (org, _validate(collection, "collection"), _validate(record_id, "record id"),
             json.dumps(payload, default=str)),
        )
        return payload

    def get(self, org_id: str, collection: str, record_id: str) -> Optional[dict]:
        row = self._run(
            "SELECT data FROM {t} WHERE org_id=%s AND collection=%s AND record_id=%s",
            (_validate(org_id, "org id"), _validate(collection, "collection"),
             _validate(record_id, "record id")),
            fetch="one",
        )
        return _as_dict(row[0]) if row else None

    def list(self, org_id: str, collection: str) -> list[dict]:
        rows = self._run(
            "SELECT data FROM {t} WHERE org_id=%s AND collection=%s ORDER BY record_id",
            (_validate(org_id, "org id"), _validate(collection, "collection")),
            fetch="all",
        )
        return [_as_dict(r[0]) for r in rows]

    def delete(self, org_id: str, collection: str, record_id: str) -> bool:
        n = self._run(
            "DELETE FROM {t} WHERE org_id=%s AND collection=%s AND record_id=%s",
            (_validate(org_id, "org id"), _validate(collection, "collection"),
             _validate(record_id, "record id")),
            fetch="rowcount",
        )
        return bool(n and n > 0)

    def collections(self, org_id: str) -> list[str]:
        rows = self._run(
            "SELECT DISTINCT collection FROM {t} WHERE org_id=%s ORDER BY collection",
            (_validate(org_id, "org id"),),
            fetch="all",
        )
        return [r[0] for r in rows]

    # ── operational helpers (parity with SqliteStore) ────────────────────────

    def count(self, org_id: Optional[str] = None) -> int:
        if org_id:
            row = self._run("SELECT COUNT(*) FROM {t} WHERE org_id=%s",
                            (_validate(org_id, "org id"),), fetch="one")
        else:
            row = self._run("SELECT COUNT(*) FROM {t}", (), fetch="one")
        return int(row[0]) if row else 0

    def backup(self, destination: Path | str) -> str:
        """Dump every record to a portable JSON Lines file.

        Deliberately not pg_dump. A managed provider already takes its own
        binary snapshots, and those are the fast path for restoring the same
        provider. What they do NOT give you is a copy you can read without
        them — and the question a client's auditor actually asks is "what
        happens to our records if your vendor disappears".

        One JSON object per line, so a partially written file still yields
        every complete record before the interruption.
        """
        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        rows = self._run(
            "SELECT org_id, collection, record_id, data FROM {t} "
            "ORDER BY org_id, collection, record_id", (), fetch="all")
        with dest.open("w", encoding="utf-8") as fh:
            for org, coll, rid, data in rows:
                fh.write(json.dumps({
                    "org_id": org, "collection": coll, "record_id": rid,
                    "data": _as_dict(data),
                }, ensure_ascii=False, default=str) + "\n")
        return str(dest)

    def restore(self, source: Path | str) -> int:
        """Load a JSON Lines backup back in. Upserts, so it is idempotent and
        can be replayed over a partially recovered database."""
        n = 0
        with Path(source).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                self.put(rec["org_id"], rec["collection"], rec["record_id"], rec["data"])
                n += 1
        return n


def _as_dict(value: Any) -> dict:  # pragma: no cover
    """psycopg returns JSONB as a dict already; tolerate a string too."""
    return value if isinstance(value, dict) else json.loads(value)


# ─── migration ──────────────────────────────────────────────────────────────


def migrate_json_to_sql(json_root: Path | str, target) -> int:
    """Copy every record from the JSON file store into a SQL store.

    Idempotent: records are upserted by (org, collection, id), so running it
    twice is harmless. Returns the number of records migrated.
    """
    root = Path(json_root)
    if not root.exists():
        return 0
    migrated = 0
    for org_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for coll_dir in sorted(p for p in org_dir.iterdir() if p.is_dir()):
            for path in sorted(coll_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text())
                except Exception as exc:
                    print(f"Warning: skipping unreadable {path}: {exc}")
                    continue
                target.put(org_dir.name, coll_dir.name, path.stem, data)
                migrated += 1
    return migrated
