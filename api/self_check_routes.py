"""
DOCex Self-Check Agent routes.

Endpoints:
  POST /diagnostics/run        — run the full diagnostic suite, return report
  GET  /diagnostics/last       — fetch the last saved report (404 if none)
  GET  /diagnostics            — list saved reports (newest first)
  GET  /diagnostics/{id}       — fetch one saved report in full
  DELETE /diagnostics/{id}     — delete one

Reports persist under {project_root}/diagnostics/{id}.json so the team
has a track record over time — useful for "did something break between
last week and today?".
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import DiagnosticReport  # noqa: E402
from self_check import run_full_check  # noqa: E402


# ─── Admin gate ─────────────────────────────────────────────────────────────
#
# When ADMIN_SECRET is set in the environment, every /diagnostics/* request
# must include a matching X-Admin-Secret header. When UNSET, the routes are
# open (fine for local dev). The mismatch response is 404 (not 401) so the
# feature looks like it doesn't exist to anyone without the secret — better
# UX for hiding admin surface than a clear "you can't access this" 401.

def _require_admin(
    x_admin_secret: Annotated[str | None, Header(alias="X-Admin-Secret")] = None,
) -> None:
    expected = os.environ.get("ADMIN_SECRET", "").strip()
    if not expected:
        # No secret configured — admin gate is intentionally open.
        # Devs can hit /diagnostics directly during local development.
        return
    if x_admin_secret != expected:
        # 404 (not 401) so the route appears not to exist at all from the
        # perspective of someone without the secret.
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(
    prefix="/diagnostics",
    tags=["diagnostics"],
    dependencies=[Depends(_require_admin)],
)

_DIAG_DIR = Path(__file__).parent.parent / "diagnostics"


def _ensure_dir() -> None:
    _DIAG_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _report_path(report_id: str) -> Path:
    if "/" in report_id or ".." in report_id or not report_id.strip():
        raise HTTPException(status_code=400, detail="Invalid report id.")
    return _DIAG_DIR / f"{report_id}.json"


def _save(report: DiagnosticReport) -> DiagnosticReport:
    _ensure_dir()
    if not report.report_id:
        report.report_id = uuid.uuid4().hex
    _report_path(report.report_id).write_text(report.model_dump_json(indent=2))
    return report


def _list_reports() -> list[DiagnosticReport]:
    _ensure_dir()
    paths = sorted(
        _DIAG_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out: list[DiagnosticReport] = []
    for p in paths:
        try:
            out.append(DiagnosticReport.model_validate_json(p.read_text()))
        except Exception as exc:
            print(f"Warning: skipping corrupted report {p.name}: {exc}")
            continue
    return out


@router.post("/run", response_model=DiagnosticReport)
def run_diagnostic() -> DiagnosticReport:
    """Run the full Self-Check suite and persist the report."""
    report = run_full_check()
    try:
        report = _save(report)
    except Exception as exc:
        # Persistence failed (probably the filesystem check itself failed).
        # Return the report anyway — observation is the point.
        print(f"Warning: could not persist diagnostic report: {exc}")
    return report


@router.get("/last", response_model=DiagnosticReport)
def get_last_report() -> DiagnosticReport:
    """Convenience: fetch the most recent saved report without listing."""
    reports = _list_reports()
    if not reports:
        raise HTTPException(
            status_code=404,
            detail="No saved diagnostic reports yet. POST /diagnostics/run to generate one.",
        )
    return reports[0]


@router.get("", response_model=dict)
def list_reports() -> dict:
    """List every saved report. Slim summary projection per item."""
    reports = _list_reports()
    return {
        "reports": [
            {
                "report_id": r.report_id,
                "started_at": r.started_at,
                "duration_ms": r.duration_ms,
                "overall": r.overall,
                "total": r.total,
                "passed": r.passed,
                "warned": r.warned,
                "failed": r.failed,
                "skipped": r.skipped,
            }
            for r in reports
        ]
    }


@router.get("/{report_id}", response_model=DiagnosticReport)
def get_report(report_id: str) -> DiagnosticReport:
    path = _report_path(report_id)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Diagnostic report '{report_id}' not found."
        )
    return DiagnosticReport.model_validate_json(path.read_text())


@router.delete("/{report_id}")
def delete_report(report_id: str) -> dict[str, str]:
    path = _report_path(report_id)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail=f"Diagnostic report '{report_id}' not found."
        )
    path.unlink()
    return {"status": "deleted", "report_id": report_id}
