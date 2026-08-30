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
  Postgres — same SQL with JSONB and an upsert. Use for multi-user cloud.
             Requires `psycopg` (v3) at runtime; untested until a real database
             URL exists, which is stated plainly rather than assumed.

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

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS records (
    org_id     TEXT NOT NULL,
    collection TEXT NOT NULL,
    record_id  TEXT NOT NULL,
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, collection, record_id)
);
CREATE INDEX IF NOT EXISTS idx_records_org_collection
    ON records (org_id, collection);
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


class PostgresStore:
    """Same contract, managed Postgres underneath — for multi-user cloud.

    Requires `psycopg` (v3) and a connection URL. NOTE: this adapter has been
    written but NOT verified against a live database in development; run
    `test_store_sql.py` with DOCEX_DATABASE_URL set before trusting it in
    production. The SQL is deliberately identical in shape to the SQLite path so
    behaviour matches.
    """

    def __init__(self, dsn: str):
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise StoreError(
                "PostgresStore needs the 'psycopg' package (pip install 'psycopg[binary]')."
            ) from exc
        self.dsn = dsn
        self._init_schema()

    def _connect(self):  # pragma: no cover - needs a live database
        import psycopg
        return psycopg.connect(self.dsn)

    def _init_schema(self) -> None:  # pragma: no cover
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(_SCHEMA_POSTGRES)
            conn.commit()

    def put(self, org_id: str, collection: str, record_id: str, data: dict) -> dict:  # pragma: no cover
        org = _validate(org_id, "org id")
        payload = {**data, "org_id": org}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO records (org_id, collection, record_id, data, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (org_id, collection, record_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                """,
                (org, _validate(collection, "collection"), _validate(record_id, "record id"),
                 json.dumps(payload, default=str)),
            )
            conn.commit()
        return payload

    def get(self, org_id: str, collection: str, record_id: str) -> Optional[dict]:  # pragma: no cover
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM records WHERE org_id=%s AND collection=%s AND record_id=%s",
                (_validate(org_id, "org id"), _validate(collection, "collection"),
                 _validate(record_id, "record id")),
            )
            row = cur.fetchone()
        return _as_dict(row[0]) if row else None

    def list(self, org_id: str, collection: str) -> list[dict]:  # pragma: no cover
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM records WHERE org_id=%s AND collection=%s ORDER BY record_id",
                (_validate(org_id, "org id"), _validate(collection, "collection")),
            )
            return [_as_dict(r[0]) for r in cur.fetchall()]

    def delete(self, org_id: str, collection: str, record_id: str) -> bool:  # pragma: no cover
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM records WHERE org_id=%s AND collection=%s AND record_id=%s",
                (_validate(org_id, "org id"), _validate(collection, "collection"),
                 _validate(record_id, "record id")),
            )
            deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def collections(self, org_id: str) -> list[str]:  # pragma: no cover
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT collection FROM records WHERE org_id=%s ORDER BY collection",
                (_validate(org_id, "org id"),),
            )
            return [r[0] for r in cur.fetchall()]


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
