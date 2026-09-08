"""
DOCex FastAPI wrapper.

Endpoints:
  GET  /health              — liveness check
  POST /extract/single      — one applicant, multiple files
  POST /extract/batch       — many applicants, each with their own files

Run locally:
  uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated

import anthropic
import fast_extract
import pdfplumber
from docx import Document as DocxDocument
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Load .env from the project root (sibling of /api). Means the user can paste
# ANTHROPIC_API_KEY into one file once and never re-export it per shell.
# override=False so an explicit `export ANTHROPIC_API_KEY=...` in the shell
# still wins, which matters for CI/CD and one-off testing.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Loud startup checks — if a required env var is missing, every call to the
# affected primitive will fail with a 401/RuntimeError and the user will
# only see "errors" in the UI. Catch them here so the terminal makes the
# cause obvious before the first request lands. The diagnostic at
# /admin/diagnostics surfaces the same issues at runtime; the startup
# print is the loud first-line-of-defence for ops.
_missing_secrets: list[str] = []
if not os.environ.get("ANTHROPIC_API_KEY"):
    _missing_secrets.append("ANTHROPIC_API_KEY  (powers Extraction + Compliance Check + follow-up drafting)")
if not os.environ.get("PAYSTACK_SECRET_KEY"):
    _missing_secrets.append("PAYSTACK_SECRET_KEY  (powers Bank Verify + Attendance Payment Agent verification)")

if _missing_secrets:
    print(
        "\n" + "=" * 70 + "\n"
        "[DOCex] WARNING — missing environment variables:\n  "
        + "\n  ".join(f"• {s}" for s in _missing_secrets) + "\n\n"
        "Affected calls will fail. Add the values to .env at the project\n"
        "root, then restart uvicorn. /admin/diagnostics will show the\n"
        "same status with fix hints once the API is running.\n"
        + "=" * 70 + "\n",
        flush=True,
    )

# Bootstrap persistence directories at app boot — every primitive's storage
# layer is file-based JSON under {project_root}/{thing}/. Creating these
# at import time means a fresh checkout doesn't trip on the first request
# that tries to write. mkdir(exist_ok=True) is idempotent so re-runs are safe.
for _dirname in ("rulebooks", "checks", "verifications",
                  "attendance_runs", "rate_cards", "diagnostics", "decks"):
    try:
        (Path(__file__).parent.parent / _dirname).mkdir(parents=True, exist_ok=True)
    except Exception as _exc:
        # Non-fatal — the lazy _ensure_dir() in each routes file will retry.
        # We don't want a chmod issue on one directory to prevent the whole
        # API from booting.
        print(f"[DOCex] Notice: could not pre-create {_dirname}/: {_exc}", flush=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

# Error reporting, before anything else can fail. No-op without SENTRY_DSN, so
# a developer without an account sees no change; with one, every unhandled
# exception is reported with credentials scrubbed and PII off.
try:
    import observability
    observability.init_sentry()
except Exception as _obs_err:   # never let monitoring setup break the boot
    print(f"[DOCex] Notice: error reporting not started: {_obs_err}", flush=True)

# ─── Storage initialization ──────────────────────────────────────────────────
# Choose the backend BEFORE any route is imported, so every engine sees the
# same store from its first line.
#
# Order: Postgres (DOCEX_DATABASE_URL) → SQLite (DOCEX_DB) → JSON files.
#
# DOCEX_DATABASE_URL used to be missing from this block entirely. The effect
# was quiet and expensive: an instance with a managed Postgres correctly wired
# up would ignore it and write JSON files to the container's local disk, which
# the platform replaces on every deploy. Nothing errored, because writing a
# file always succeeds — the records simply were not there the next morning.
# That is why the production guard below refuses to boot rather than warn.
try:
    import store
    import store_sql

    _pg_url = (os.environ.get("DOCEX_DATABASE_URL") or "").strip()
    _db_path = (os.environ.get("DOCEX_DB") or "").strip()
    _is_production = (os.environ.get("DOCEX_ENV", "").strip().lower() == "production")

    # True when WE own storage setup, i.e. the normal server boot. False when a
    # test or embedding process installed a backend before importing the app.
    _owns_storage = not store.is_configured()
    if not _owns_storage:
        # Respect the caller's store — overriding here silently redirected test
        # writes into the developer's real data/ directory, which then made
        # /auth/status report "already set up" and locked out first-run.
        print("[DOCex] Store already configured by caller; leaving it alone", flush=True)
    elif _pg_url:
        # Managed Postgres: the multi-user production path. Pooled and health
        # checked — see store_sql.PostgresStore for why that is not optional.
        print("[DOCex] Initializing PostgreSQL storage", flush=True)
        store.set_store(store_sql.PostgresStore(_pg_url))
    elif _db_path:
        # SQLite at a persistent path. Durable ONLY if that path is a mounted
        # volume; on a container's own disk it is wiped with everything else.
        print(f"[DOCex] Initializing SQLite storage at {_db_path}", flush=True)
        store.set_store(store_sql.SqliteStore(_db_path))
    elif _is_production:
        # The whole point of the guard. A finance system that starts up happily
        # and loses March on the April deploy is worse than one that refuses to
        # start, because the first failure is discovered by the client.
        raise RuntimeError(
            "Refusing to start: DOCEX_ENV=production but neither "
            "DOCEX_DATABASE_URL nor DOCEX_DB is set, so records would be "
            "written to the container's local disk and destroyed on the next "
            "deploy. Set DOCEX_DATABASE_URL to the managed database, or "
            "DOCEX_DB to a path on a mounted volume.")
    else:
        # Development: JSON files, backward compatible.
        from pathlib import Path as PathlibPath
        _json_root = PathlibPath(__file__).parent.parent / "data"
        print(f"[DOCex] Using JSON file store at {_json_root} "
              "(set DOCEX_DATABASE_URL or DOCEX_DB for durable storage)", flush=True)
        store.set_store(store.JsonFileStore(_json_root))

    # Secrets that are silently generated when absent. Both are fine to leave
    # unset on a laptop and both cause real damage in production, so they are
    # checked here rather than discovered later.
    if _is_production and _owns_storage:
        if not (os.environ.get("AUTH_SECRET") or "").strip():
            raise RuntimeError(
                "Refusing to start: AUTH_SECRET is not set in production. "
                "Without it each container invents its own signing secret, so "
                "every user is signed out on every deploy and two instances "
                "never agree on a session.")
        if not (os.environ.get("DOCEX_SIGNING_KEY") or "").strip():
            raise RuntimeError(
                "Refusing to start: DOCEX_SIGNING_KEY is not set in "
                "production. It signs the append-only audit chain; a "
                "per-container key means verify_audit_chain() fails on records "
                "written by any other container. Set it ONCE and never rotate "
                "it — rotating invalidates every historical record.")
except Exception as _store_err:
    print(f"[DOCex] FATAL: {_store_err}", flush=True)
    raise

# One-time import of accounts/departments from the pre-store file layout, so an
# instance upgraded in place keeps its logins. No-op once the store has data.
#
# ONLY on the real server boot. A test that points storage at a temp dir and
# then imports this app would otherwise have the developer's legacy users/
# directory imported into its fixture — which silently made the "first
# registered user becomes admin" path untestable, because a user already
# existed. Guarding on _owns_storage keeps the migration where it belongs.
#
# And NOT in production. The legacy directory is a developer's laptop artefact:
# on this machine it held a `demo@neem.org` admin created for a rehearsal,
# with a password nobody now remembers. Importing that into a client's live
# database would create a working administrator account outside the client's
# control — the kind of thing an auditor finds and you cannot explain. Render
# builds from git and the directory is gitignored, so it should never be
# present; this makes "should never" into "cannot".
if _owns_storage and not _is_production:
    try:
        import auth as _auth
        import departments as _departments
        _auth.migrate_legacy_users()
        _departments.migrate_legacy_registry()
        # The three engines that used to write loose files. Each import runs
        # only when the store holds nothing for the org, so this is a no-op on
        # every boot after the first. transactions carries its counter across
        # too, so references continue rather than restarting at 1 and colliding
        # with history.
        import notification_center as _nc
        import transactions as _tx
        import vouchers as _vouchers
        _nc.migrate_legacy_notifications()
        _tx.migrate_legacy_transactions()
        _vouchers.migrate_legacy_vouchers()
    except Exception as _mig_err:  # never block boot on a migration hiccup
        print(f"[DOCex] Notice: legacy import skipped: {_mig_err}", flush=True)
elif _is_production:
    from pathlib import Path as _P
    if (_P(__file__).parent.parent / "users").is_dir():
        print("[DOCex] WARNING: a legacy users/ directory is present in a "
              "production image and was NOT imported. It should not have been "
              "shipped — check .dockerignore.", flush=True)

from models import ApplicantExtraction, ExtractionAnswer, Question  # noqa: E402
from screener import extract_applicant, extract_batch  # noqa: E402
from .assistant_routes import router as assistant_router  # noqa: E402
from .attendance_agent_routes import router as attendance_router  # noqa: E402
from .attendance_collection_routes import router as attendance_collection_router  # noqa: E402
from .bank_verify_routes import router as bank_verify_router  # noqa: E402
from .compliance_routes import router as compliance_router  # noqa: E402
from .knowledge_routes import router as knowledge_router  # noqa: E402
from .timesheet_routes import router as timesheet_router  # noqa: E402
from .payroll_routes import router as payroll_router  # noqa: E402
from .reconciliation_routes import router as reconciliation_router  # noqa: E402
from .vendor_routes import router as vendor_router  # noqa: E402
from .accounting_routes import router as accounting_router  # noqa: E402
from .treasury_routes import router as treasury_router  # noqa: E402
from .advance_routes import router as advance_router  # noqa: E402
from .per_diem_routes import router as per_diem_router  # noqa: E402
from .rate_card_routes import router as rate_card_router  # noqa: E402
from .auth_routes import router as auth_router  # noqa: E402
from .department_routes import router as department_router  # noqa: E402
from .org_routes import router as org_router  # noqa: E402
from .security import AuthMiddleware  # noqa: E402
from .transaction_routes import router as transaction_router  # noqa: E402
from .voucher_routes import router as voucher_router  # noqa: E402
from .field_receipt_routes import router as field_receipt_router  # noqa: E402
from .requisition_routes import router as requisition_router  # noqa: E402
from .self_check_routes import router as self_check_router  # noqa: E402
from .schemas import (  # noqa: E402
    BatchExtractionResponse,
    FollowupDraft,
    FollowupRequest,
    FollowupResponse,
    HealthOut,
    QuestionIn,
    SingleExtractionResponse,
)

# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DOCex API",
    description="AI-powered document extraction — define questions, upload docs, get answers.",
    version="2.0.0",
)

# CORS configuration.
#   - Localhost origins are always allowed (so `npm run dev` works without
#     any env var setup).
#   - Production origins come from the ALLOWED_ORIGINS env var as a
#     comma-separated list. On Railway/Fly set this to your Vercel URL,
#     e.g. ALLOWED_ORIGINS=https://docex.vercel.app,https://docex.com
_default_dev_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:3001", "http://127.0.0.1:3001",
]
_extra_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
_extra_origins = (
    [o.strip() for o in _extra_origins_env.split(",") if o.strip()]
    if _extra_origins_env
    else []
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_dev_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression — shrinks JSON responses ~60-80% on payloads over 1KB.
# Cost is a tiny CPU bump on the API; benefit is faster page loads everywhere
# the frontend hits a list endpoint (Bank Verify batches, attendance runs,
# rate cards, diagnostic reports). FastAPI's stock GZipMiddleware handles
# the Accept-Encoding negotiation correctly.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Request-ID tracing — give every request a stable ID and log a one-line
# summary (method, path, status, duration). When a customer reports "it broke
# at 2:14pm", the X-Request-ID in their browser's network tab maps straight to
# a line in the Railway logs. Honours an inbound X-Request-ID if a proxy set
# one; otherwise generates a short uuid. Pure observability — no behaviour
# change to any endpoint.
_access_log = logging.getLogger("docex.access")
if not _access_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _access_log.addHandler(_h)
    _access_log.setLevel(logging.INFO)


class _RequestIDMiddleware:
    """Pure-ASGI request-ID stamping + one-line access log.

    Deliberately raw ASGI, NOT Starlette's BaseHTTPMiddleware (i.e. not
    `@app.middleware("http")`): BaseHTTPMiddleware buffers the whole response
    and DEADLOCKS with GZipMiddleware on any response large enough to be
    compressed (>1KB) — which made /compliance/checks and /org-profile hang in
    production while tiny responses (/health) were fine. A pure-ASGI middleware
    just streams messages through and tags the response start, so it composes
    correctly with GZip.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        rid = ""
        for k, v in scope.get("headers") or []:
            if k == b"x-request-id":
                rid = v.decode("latin-1")
                break
        rid = rid or uuid.uuid4().hex[:12]
        # Stash it where the exception handler can find it, so a 500 can quote
        # the same id that appears in the access log.
        scope.setdefault("state", {})["request_id"] = rid
        start = time.perf_counter()
        status = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", rid.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            _access_log.exception(
                "rid=%s %s %s -> EXCEPTION (%.0fms)",
                rid, scope.get("method", ""), scope.get("path", ""), elapsed,
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000
        _access_log.info(
            "rid=%s %s %s -> %s (%.0fms)",
            rid, scope.get("method", ""), scope.get("path", ""), status["code"], elapsed,
        )


app.add_middleware(_RequestIDMiddleware)

# ─── Safe error responses ───────────────────────────────────────────────────
#
# An unhandled exception must never hand the caller our internals. Starlette's
# default 500 body is short, but a stray `detail=str(exc)` in a route can leak
# a filesystem path, a table name, a connection string or an API key that
# happened to be in the message — and a client's browser console is the last
# place any of those should appear.
#
# So: the client gets a fixed sentence and a request id. The full traceback
# goes to the server log and to Sentry (already scrubbed by observability.py).
# When a client reports a problem they quote the id, and we find the exact
# request without them having to describe it.


@app.exception_handler(Exception)
async def _safe_error(request, exc):  # noqa: ANN001
    from fastapi.responses import JSONResponse

    rid = getattr(request.state, "request_id", "") or "unknown"
    _access_log.exception("rid=%s unhandled error on %s %s",
                          rid, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": ("Something went wrong on our side. Nothing was saved. "
                       f"Quote reference {rid} if you contact support."),
            "request_id": rid,
        },
    )


# Authentication floor — DEFAULT DENY.
#
# Added last, so it is the OUTERMOST middleware and nothing reaches a route
# handler without a valid session except the small allowlist in api/security.py
# (health, login, register, status, docs, and the token-bearing public links for
# self-check-in and emailed approvals).
#
# This exists because ~90 routes had no auth at all: the newer routers gate
# every endpoint with Depends(current_user), but the older ones never did, which
# left client rulebooks, compliance checks, transactions and vouchers readable
# by anyone with the URL — and left endpoints that spend money (Claude,
# Paystack) open to anyone who felt like spending it.
#
# Decorators would have fixed it once; default-deny fixes it for every route
# added from now on. test_auth_coverage.py enumerates the live app and fails if
# anything becomes reachable without credentials.
app.add_middleware(
    AuthMiddleware,
    allowed_origins=_default_dev_origins + _extra_origins,
)

# Compliance Check routes — policy interpretation, rulebook CRUD, payment
# checks (single + batch). See api/compliance_routes.py.
app.include_router(compliance_router)

# Bank Verify routes — bulk verification of recipient bank accounts against
# Paystack /bank/resolve, with fuzzy name matching. See api/bank_verify_routes.py.
app.include_router(bank_verify_router)

# Attendance Payment Agent — DOCex's first composite agent. Chains the
# attendance-log + payment-info parsing primitives with cross-matching,
# then hands the resulting schedule off to Bank Verify for verification.
# See api/attendance_agent_routes.py.
app.include_router(attendance_router)

# Attendance Collections — native intake grid + public self-check-in links.
# Converts collected attendees into a normal run. See
# api/attendance_collection_routes.py.
app.include_router(attendance_collection_router)

# Rate cards — reusable per-diem schedules consumed by the Attendance
# Payment Agent and (later) any other agent that needs to compute payment
# amounts. See api/rate_card_routes.py.
app.include_router(rate_card_router)

# Per-diem — computes one participant's payable from a rate card's per-diem
# policy + the days/coverage/receipts a worker submits. See api/per_diem_routes.py.
app.include_router(per_diem_router)

# Transactions + notifications — the cross-department workflow spine. Every work
# item gets a reference (C24) and a status trail; state changes fan out in-app
# notifications to the department that must act next. See api/transaction_routes.py.
app.include_router(transaction_router)

# Vouchers — consolidate participant payables into one payment voucher and
# submit it into the approval workflow. See api/voucher_routes.py.
app.include_router(voucher_router)

# Field Receipts — real-time receipt capture, OCR extraction, and policy
# validation for field-based NGOs. Fieldworkers upload receipts, system
# auto-validates and flags issues. See api/field_receipt_routes.py.
app.include_router(field_receipt_router)

# Requisitions — the universal department→payment spine. Any department raises a
# payment request; deterministic policy checks run immediately; the org's own
# approval chain routes it; a failing check can only be released by an
# authorised approver with a written reason; every decision lands in an
# append-only, hash-chained audit log; final approval freezes an immutable
# transaction record. See api/requisition_routes.py.
app.include_router(requisition_router)

# Auth + dashboards — per-department logins, roles/RBAC, and the per-department
# dashboard aggregation. See api/auth_routes.py.
app.include_router(auth_router)

# Departments — each org defines its own departments + which one owns each
# workflow state. See api/department_routes.py.
app.include_router(department_router)

# Org config — which product modules and feature flags this client has switched
# on. The frontend reads it to build navigation, so a client never sees a menu
# item for something their organisation didn't buy. See api/org_routes.py.
app.include_router(org_router)

# Self-Check Agent — runtime diagnostic that exercises every primitive and
# reports health. V1 of the longer-term Self-Improvement Agent (observe →
# recommend). See api/self_check_routes.py.
app.include_router(self_check_router)

# DOCex Assistant — agentic narrator. Every result page calls this to get
# a plain-English briefing on what just happened plus recommended next
# actions. See api/assistant_routes.py.
app.include_router(assistant_router)

# Knowledge Hub — slide-deck ingestion + chat-with-slides. The fifth
# DOCex primitive. Upload .pptx → parsed slide-by-slide → ask questions
# with slide-N citations. See api/knowledge_routes.py.
app.include_router(knowledge_router)

# Effort reporting — daily hours per project code, approved by a supervisor.
# 2 CFR 200.430(i) lets a grant be charged only for work actually performed,
# so this is what makes a salary allocation defensible rather than budgeted.
# Gated on the `timesheets` feature flag. See api/timesheet_routes.py.
app.include_router(timesheet_router)

# Payroll — gross → deductions → net, allocated to donors and project codes,
# preferring approved timesheets over budgeted percentages. Computing a run
# pays nobody: payment goes through the same approval workflow as any other
# payment. Gated on `payroll`. See api/payroll_routes.py.
app.include_router(payroll_router)

# Month-end bank reconciliation — match what we say we paid against what the
# bank says left the account, in BOTH directions. Gated on
# `bank_reconciliation`. See api/reconciliation_routes.py.
app.include_router(reconciliation_router)

# Vendor register — who we are allowed to pay, and whether anyone checked.
# The bank-account check is the control that catches a diverted payment: a real
# invoice from a real supplier with the account number altered passes every
# other check in the system. Gated on `vendor_register`. See api/vendor_routes.py.
app.include_router(vendor_router)

# QuickBooks handoff. DOCex sits in FRONT of the accounting system: it owns
# approval and evidence, QuickBooks owns the book of record. This exports the
# coded payment register (so nobody re-types it) and cleans a Nigerian bank
# statement into a file QuickBooks will actually accept — Nigerian banks cannot
# be connected to QuickBooks bank feeds, so that reformatting is done by hand
# today. Gated on `accounting_export`. See api/accounting_routes.py.
app.include_router(accounting_router)

# Treasury — the bank accounts money leaves from, and the tax withheld before
# it goes. Both exist so a payment can be reconciled: a donor-funded NGO
# ring-fences each grant in its own account, and every Nigerian vendor payment
# produces a second debit for withholding tax. See api/treasury_routes.py.
app.include_router(treasury_router)

# Advance retirement — the clock and the consequence. An unretired advance is
# the most common source of ineligible cost in donor-funded work; NEEM wrote
# down a three-stage escalation ladder and this enforces it. Gated on
# `advance_retirement`. See api/advance_routes.py.
app.include_router(advance_router)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _extract_text(upload: UploadFile) -> str:
    """Extract plain text from a single PDF, DOCX, or TXT upload.

    Thin wrapper over the shared fast_extract layer so screening, compliance,
    and knowledge all parse documents identically (same fitz→pdfplumber PDF
    path, same order-preserving DOCX walk, same fallbacks).
    """
    return fast_extract.extract_text(upload.filename or "", upload.file.read()).strip()


def _parse_questions(questions_json: str) -> list[Question]:
    """Parse and validate the questions JSON string sent from the frontend."""
    try:
        raw = json.loads(questions_json)
        validated = [QuestionIn.model_validate(q) for q in raw]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid questions: {exc}") from exc

    if not validated:
        raise HTTPException(status_code=422, detail="At least one question is required.")

    return [Question(id=q.id, text=q.text) for q in validated]


def _read_uploads(uploads: list[UploadFile]) -> dict[str, tuple[str, str]]:
    """
    Extract text from every uploaded file, IN PARALLEL.
    Returns a dict of {filename: (filename, text)}.

    Reading the bytes is quick sequential I/O; the slow part is parsing, which
    fast_extract.extract_many fans out across a thread pool. For an applicant
    with 5-8 documents this turns a serial parse into a concurrent one.
    Files that yield no text are skipped — the caller decides whether to raise
    or continue.
    """
    named_bytes: list[tuple[str, bytes]] = []
    for upload in uploads:
        filename = upload.filename or f"file_{uuid.uuid4().hex[:6]}"
        try:
            named_bytes.append((filename, upload.file.read()))
        except Exception as exc:
            print(f"Warning: could not read '{filename}': {exc}")

    result: dict[str, tuple[str, str]] = {}
    for filename, text in fast_extract.extract_many(named_bytes):
        if text:
            result[filename] = (filename, text)
    return result


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthOut, tags=["meta"])
def health() -> HealthOut:
    return HealthOut()


@app.post("/extract/single", response_model=SingleExtractionResponse, tags=["extraction"])
async def extract_single(
    documents: Annotated[list[UploadFile], File(description="All documents for this one applicant")],
    questions: Annotated[str, Form(description='JSON array: [{id, text}, ...]')],
    applicant_name: Annotated[str, Form(description="Name or label for this applicant")] = "Applicant",
) -> SingleExtractionResponse:
    """
    Extract answers for a single applicant from multiple uploaded documents.
    All files are read together — answers can come from any of them.
    """
    questions_list = _parse_questions(questions)
    file_texts = _read_uploads(documents)

    if not file_texts:
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the uploaded documents. "
                   "Make sure the files are readable PDFs, DOCX, or plain text.",
        )

    result = extract_applicant(
        applicant_id=str(uuid.uuid4()),
        applicant_name=applicant_name,
        documents=list(file_texts.values()),
        questions=questions_list,
    )

    return SingleExtractionResponse(
        applicant_name=result.applicant_name,
        documents=result.documents,
        answers=result.answers,
        error=result.error,
    )


@app.post("/extract/batch", response_model=BatchExtractionResponse, tags=["extraction"])
async def extract_batch_endpoint(
    documents: Annotated[list[UploadFile], File(description="All files for all applicants")],
    questions: Annotated[str, Form(description='JSON array: [{id, text}, ...]')],
    applicants: Annotated[str, Form(description='JSON array: [{id, name, filenames: [...]}]')],
) -> BatchExtractionResponse:
    """
    Extract answers for multiple applicants in one request.

    Upload ALL files for ALL applicants together, then pass an `applicants`
    JSON array mapping each applicant to their specific filenames.

    Example applicants JSON:
    [
      {"id": "org-1", "name": "Health Initiative Abuja", "filenames": ["hi_cac.pdf", "hi_proposal.docx"]},
      {"id": "org-2", "name": "Women in Agric",          "filenames": ["wia_reg.pdf", "wia_budget.pdf"]}
    ]
    """
    questions_list = _parse_questions(questions)

    try:
        applicants_raw = json.loads(applicants)
        if not isinstance(applicants_raw, list) or len(applicants_raw) == 0:
            raise ValueError("Must be a non-empty array.")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid applicants JSON: {exc}") from exc

    # Extract text from every uploaded file, keyed by filename
    file_texts = _read_uploads(documents)

    # Build the applicant list, catching missing files loudly
    applicant_list = []
    for ap in applicants_raw:
        ap_name = ap.get("name", "Unknown")
        ap_id = ap.get("id", str(uuid.uuid4()))
        requested_files = ap.get("filenames", [])

        missing = [fn for fn in requested_files if fn not in file_texts]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Applicant '{ap_name}': these filenames were listed but not uploaded: {missing}. "
                       f"Uploaded files are: {list(file_texts.keys())}",
            )

        ap_docs = [file_texts[fn] for fn in requested_files if fn in file_texts]

        if not ap_docs:
            raise HTTPException(
                status_code=422,
                detail=f"Applicant '{ap_name}' has no readable documents. "
                       "Check that the files uploaded are valid PDFs, DOCX, or text files.",
            )

        applicant_list.append({"id": ap_id, "name": ap_name, "documents": ap_docs})

    results: list[ApplicantExtraction] = extract_batch(applicant_list, questions_list)

    succeeded = sum(1 for r in results if not r.error)
    failed = len(results) - succeeded

    return BatchExtractionResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        applicants=results,
    )


# ─── Follow-up note drafting ───────────────────────────────────────────────

# Lazily constructed so the backend boots even when ANTHROPIC_API_KEY is
# missing/invalid. Constructing anthropic.Anthropic() at import time would
# abort the whole app on startup (uvicorn never serves -> every feature shows
# "Failed to fetch"). We only build the client the first time a follow-up note
# is actually drafted, and surface any key error to that one endpoint instead.
_followup_client: "anthropic.Anthropic | None" = None


def _get_followup_client() -> "anthropic.Anthropic":
    global _followup_client
    if _followup_client is None:
        _followup_client = anthropic.Anthropic()
    return _followup_client


def _build_followup_system(template_id: Optional[str]) -> str:
    """
    Return a follow-up drafting system prompt tuned to the workflow.

    The shape is the same across templates (acknowledge → list 2-3 specific
    gaps → close politely), but the vocabulary and the ask differ:
      - For application screening, partners are "applicants" and the ask is
        to submit missing items before assessment can complete.
      - For quarterly report review, the partners are existing collaborators
        and the ask is for an addendum or for next reporting cycle.

    Mirrors the workflow-labels file used on the frontend.
    """
    if template_id == "quarterly-report-review":
        return """You draft short follow-up notes about partner quarterly progress reports.

The user will give you the partner's name and a summary of gaps a reviewer
flagged — questions where the answer was "not_found" or confidence was
"inferred". The partner is an EXISTING collaborator, not a new applicant.

Write a SHORT follow-up note (2-3 sentences, never more):
- Opens by acknowledging the partner's quarterly submission (not "application")
- Names 2-3 specific gaps with the missing data point or section
- Closes with a clear, low-friction ask: a brief addendum, or that the gap
  be addressed in the next reporting cycle
- Maintains a respectful, collegial tone — this is a continuing partnership

DO NOT:
- Use the word "applicant" or "application"
- Imply an approval or selection decision is pending
- Assert facts about section letters (Section A/B/C/D) unless the search
  notes explicitly mention them
- Use bureaucratic phrasing like "before the review can be completed"

Return ONLY the note body — no greeting, no signature, no subject line.
Be specific about each gap. Cite the actual data point that was missing, not
generic phrases like "some areas need improvement"."""

    # Default: application screening (sub-award or generic)
    return """You draft short follow-up notes for partner application screening.

The user will give you an applicant's name and a summary of screening gaps —
questions where the answer was "not_found" or confidence was "inferred".

Write a SHORT follow-up note (2-3 sentences, never more):
- Acknowledges the applicant submitted their application
- Names 2-3 specific gaps with the missing document or data point
- Closes with a clear, low-friction ask for what to provide
- Maintains a respectful, encouraging tone
- Does NOT make a final selection decision — that is up to the human reviewer

Return ONLY the note body — no greeting, no signature, no subject line.

Be specific about the gaps — name the missing document, policy, or data point.
Do not use generic phrases like "some areas need improvement". Cite what was
actually missing based on the screening data provided."""


def _build_gap_summary(
    answers: list[ExtractionAnswer],
) -> str:
    """Summarise the gaps (not_found and inferred) for the follow-up prompt."""
    gaps: list[str] = []
    for a in answers:
        if a.confidence == "not_found":
            gaps.append(f"- NOT FOUND: {a.question_text}")
            if a.search_notes:
                gaps.append(f"  Search note: {a.search_notes}")
        elif a.confidence == "inferred":
            gaps.append(f"- INFERRED (not explicitly stated): {a.question_text}")
            if a.answer:
                gaps.append(f"  Best guess: {a.answer}")
            if a.search_notes:
                gaps.append(f"  Reasoning: {a.search_notes}")
    return "\n".join(gaps) if gaps else "No gaps identified — all answers were found."


@app.post("/draft-followups", response_model=FollowupResponse, tags=["followups"])
async def draft_followups(body: FollowupRequest) -> FollowupResponse:
    """
    Draft short follow-up notes based on extraction gaps.
    Vocabulary and ask shape adapt to the active template (sub-award
    application review vs quarterly report review).
    """
    system_prompt = _build_followup_system(body.template_id)
    workflow_label = (
        "partner" if body.template_id == "quarterly-report-review" else "applicant"
    )

    drafts: list[FollowupDraft] = []

    for ap in body.applicants:
        gap_summary = _build_gap_summary(ap.answers)

        user_msg = (
            f"{workflow_label.capitalize()}: {ap.applicant_name}\n\n"
            f"Gaps identified:\n{gap_summary}"
        )

        try:
            response = _get_followup_client().messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            note = response.content[0].text.strip()
        except Exception as exc:
            note = f"[Could not generate draft: {exc}]"

        drafts.append(FollowupDraft(
            applicant_id=ap.applicant_id,
            applicant_name=ap.applicant_name,
            note=note,
        ))

    return FollowupResponse(drafts=drafts)
