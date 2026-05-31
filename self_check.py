"""
DOCex Self-Check Agent.

A runtime diagnostic that exercises every primitive and reports health.
Designed as an actual agent (not just a script) so it composes the same
way every other agent does — engine here, API in api/self_check_routes.py,
UI under /admin/diagnostics.

Each check is a small function that returns a CheckResult. Checks are
grouped into categories so the UI can collapse / expand by section.
Categories (in run order):

  1. environment    — API keys, env vars, model strings
  2. filesystem     — persistence directories exist + writable
  3. engines        — each primitive's engine module imports cleanly
  4. api            — every router is mounted and routes are registered
  5. smoke          — tiny end-to-end runs through each primitive's
                      pure-Python paths (no outbound network — Bank Verify
                      against a fake account would just hit a 401/429 and
                      isn't worth burning Paystack quota for diagnostic)
  6. data           — persisted records parse cleanly, no orphans

Why agent-shaped: this is V1 of the Self-Improvement Agent flagged in the
roadmap. Today it OBSERVES. Tomorrow's V2 will OBSERVE + RECOMMEND ("two
users edited the 'States operated' answer manually this week — here's a
tuned extraction prompt that would have got it right first time"). Same
report shape, more populated `fix_hint` field.

Run from anywhere:

    >>> from self_check import run_full_check
    >>> report = run_full_check()
    >>> print(report.overall, report.passed, report.failed)
"""
from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

from models import CheckResult, DiagnosticReport

# Project root (this file lives there)
_ROOT = Path(__file__).parent


# ─── Helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _time_check(fn: Callable[[], CheckResult]) -> CheckResult:
    """Run a check, time it, and recover from exceptions cleanly so a bad
    check never breaks the rest of the suite — defensive: the whole point
    of a diagnostic is to surface problems, not to be one."""
    started = time.monotonic()
    try:
        result = fn()
    except Exception as exc:
        # Capture the failure as a check result rather than propagating —
        # the user wants a report, not a crash.
        result = CheckResult(
            id="internal-check-error",
            category="internal",
            title=fn.__name__,
            status="fail",
            summary="Check itself crashed — bug in the diagnostic, not the system",
            evidence=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            fix_hint="File a bug — this means a check function has an unhandled exception",
        )
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


# ─── Environment checks ─────────────────────────────────────────────────────


def _check_anthropic_key() -> CheckResult:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return CheckResult(
            id="env-anthropic-key",
            category="environment",
            title="Anthropic API key",
            status="fail",
            summary="ANTHROPIC_API_KEY is not set",
            evidence="env var empty",
            fix_hint=(
                "Add ANTHROPIC_API_KEY=sk-ant-... to .env at the project "
                "root. Without it, every Extraction and Compliance Check "
                "call will return 401."
            ),
        )
    if not key.startswith("sk-ant-"):
        return CheckResult(
            id="env-anthropic-key",
            category="environment",
            title="Anthropic API key",
            status="warn",
            summary="ANTHROPIC_API_KEY is set but doesn't look like an Anthropic key",
            evidence=f"value starts with {key[:8]!r}",
            fix_hint="Anthropic keys start with 'sk-ant-'. Double-check you pasted the right key.",
        )
    return CheckResult(
        id="env-anthropic-key",
        category="environment",
        title="Anthropic API key",
        status="pass",
        summary="ANTHROPIC_API_KEY is set and well-formed",
    )


def _check_paystack_key() -> CheckResult:
    key = os.environ.get("PAYSTACK_SECRET_KEY", "").strip()
    if not key:
        return CheckResult(
            id="env-paystack-key",
            category="environment",
            title="Paystack secret key",
            status="fail",
            summary="PAYSTACK_SECRET_KEY is not set — Bank Verify will not function",
            evidence="env var empty",
            fix_hint=(
                "Add PAYSTACK_SECRET_KEY=sk_test_... (or sk_live_...) to "
                ".env at the project root. Get one at "
                "https://dashboard.paystack.com/#/settings/developers."
            ),
        )
    if key.startswith("sk_test_"):
        return CheckResult(
            id="env-paystack-key",
            category="environment",
            title="Paystack secret key",
            status="warn",
            summary="Paystack is in TEST mode — capped at 3 bank resolves/day",
            evidence="key prefix sk_test_",
            fix_hint=(
                "Activate live mode at https://dashboard.paystack.com/#/settings/business "
                "(upload CAC + tax ID). Live mode is free for /bank/resolve "
                "and removes the daily cap."
            ),
        )
    if key.startswith("sk_live_"):
        return CheckResult(
            id="env-paystack-key",
            category="environment",
            title="Paystack secret key",
            status="pass",
            summary="Paystack is in LIVE mode — production-ready",
        )
    return CheckResult(
        id="env-paystack-key",
        category="environment",
        title="Paystack secret key",
        status="warn",
        summary="Paystack key is set but the prefix is unexpected",
        evidence=f"value starts with {key[:8]!r}",
        fix_hint="Paystack keys start with sk_test_ or sk_live_. Verify the value.",
    )


def _check_python_version() -> CheckResult:
    major, minor = sys.version_info[:2]
    version_string = sys.version.split()[0]
    # Minimum: 3.12 (current target). Recommended: 3.13+ for the speed gains.
    if major < 3 or (major == 3 and minor < 12):
        return CheckResult(
            id="env-python-version",
            category="environment",
            title="Python version",
            status="fail",
            summary=f"Python {major}.{minor} is too old — DOCex requires 3.12+",
            evidence=version_string,
            fix_hint=(
                "Install Python 3.13 (or newer) and rebuild the venv: "
                "`rm -rf .venv && python3.13 -m venv .venv && source .venv/bin/activate "
                "&& pip install -r requirements.txt`. 3.13 is faster than 3.12 and "
                "ships with better async + type-checker support."
            ),
        )
    if major == 3 and minor == 12:
        return CheckResult(
            id="env-python-version",
            category="environment",
            title="Python version",
            status="warn",
            summary=f"Python {major}.{minor} meets the minimum, but 3.13+ is recommended for speed",
            evidence=version_string,
            fix_hint=(
                "Optional but recommended: upgrade to Python 3.13 (~15% faster on FastAPI "
                "workloads, improved error messages). On macOS: `brew install python@3.13`, "
                "then rebuild the venv."
            ),
        )
    return CheckResult(
        id="env-python-version",
        category="environment",
        title="Python version",
        status="pass",
        summary=f"Python {major}.{minor} — modern and fast",
        evidence=version_string,
    )


# ─── Filesystem checks ──────────────────────────────────────────────────────


_PERSIST_DIRS = [
    "rulebooks",
    "checks",
    "verifications",
    "attendance_runs",
    "rate_cards",
    "diagnostics",
]


def _check_persistence_dir(name: str) -> CheckResult:
    path = _ROOT / name
    try:
        # Idempotent creation — if it doesn't exist yet, we create it. This
        # means the diagnostic ALSO bootstraps a fresh checkout. Side effect
        # is intentional: "make sure things work" includes making them work.
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return CheckResult(
            id=f"fs-dir-{name}",
            category="filesystem",
            title=f"Persistence directory: {name}/",
            status="fail",
            summary=f"Could not create {name}/",
            evidence=f"{type(exc).__name__}: {exc}",
            fix_hint=(
                f"Check filesystem permissions on the project root. The "
                f"backend writes JSON files under {path}/ as the source of "
                f"truth for {name}."
            ),
        )

    # Write a temp file to confirm we can actually persist (the mkdir
    # might succeed on a read-only FS due to caching quirks).
    probe = path / ".self-check-probe"
    try:
        probe.write_text("ok")
        probe.unlink()
    except Exception as exc:
        return CheckResult(
            id=f"fs-dir-{name}",
            category="filesystem",
            title=f"Persistence directory: {name}/",
            status="fail",
            summary=f"{name}/ exists but isn't writable",
            evidence=f"{type(exc).__name__}: {exc}",
            fix_hint=f"chmod the directory or run as a user who owns {path}",
        )

    count = sum(1 for _ in path.glob("*.json"))
    return CheckResult(
        id=f"fs-dir-{name}",
        category="filesystem",
        title=f"Persistence directory: {name}/",
        status="pass",
        summary=f"{name}/ exists, is writable, holds {count} record{'s' if count != 1 else ''}",
    )


# ─── Engine import checks ───────────────────────────────────────────────────


def _check_engine_import(module: str, expected_attrs: list[str]) -> CheckResult:
    try:
        mod = importlib.import_module(module)
    except Exception as exc:
        return CheckResult(
            id=f"engine-{module}",
            category="engines",
            title=f"Engine module: {module}",
            status="fail",
            summary=f"Could not import {module}",
            evidence=f"{type(exc).__name__}: {exc}",
            fix_hint=(
                f"Either a syntax error in {module}.py or a missing "
                f"dependency. Run `pip install -r requirements.txt` and "
                f"check the file imports cleanly with `python -c 'import {module}'`."
            ),
        )

    missing = [a for a in expected_attrs if not hasattr(mod, a)]
    if missing:
        return CheckResult(
            id=f"engine-{module}",
            category="engines",
            title=f"Engine module: {module}",
            status="fail",
            summary=f"{module} imports but is missing expected symbols: {', '.join(missing)}",
            evidence=f"missing: {missing}",
            fix_hint=(
                f"Make sure {module}.py defines: {', '.join(expected_attrs)}. "
                f"If you renamed any of them, update the consumers too."
            ),
        )

    return CheckResult(
        id=f"engine-{module}",
        category="engines",
        title=f"Engine module: {module}",
        status="pass",
        summary=f"{module} imports cleanly and exposes {len(expected_attrs)} expected symbol(s)",
    )


# ─── API route registration check ───────────────────────────────────────────


def _check_api_routes() -> CheckResult:
    """Boot the FastAPI app (sandbox-safely) and inspect its route table."""
    try:
        from api.main import app
    except Exception as exc:
        return CheckResult(
            id="api-mount",
            category="api",
            title="FastAPI app boots",
            status="fail",
            summary="api.main.app could not be imported",
            evidence=f"{type(exc).__name__}: {exc}",
            fix_hint=(
                "Check api/main.py imports. The most common cause is a "
                "missing dependency or a circular import added recently."
            ),
        )

    # Every router we expect to be mounted, expressed as a path prefix.
    expected_prefixes = [
        "/health",
        "/extract/single",
        "/extract/batch",
        "/draft-followups",
        "/compliance/policy",
        "/compliance/rulebooks",
        "/compliance/check/single",
        "/compliance/check/batch",
        "/compliance/checks",
        "/verify/bank-batch",
        "/verify/batches",
        "/agents/attendance-payment/run",
        "/agents/attendance-payment/runs",
        "/rate-cards",
    ]

    found_paths = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            found_paths.add(path)

    missing = []
    for prefix in expected_prefixes:
        if not any(p == prefix or p.startswith(prefix + "/") for p in found_paths):
            missing.append(prefix)

    if missing:
        return CheckResult(
            id="api-mount",
            category="api",
            title="API route inventory",
            status="fail",
            summary=f"{len(missing)} expected route(s) not registered",
            evidence=f"missing: {missing}",
            fix_hint=(
                "Check api/main.py — each router (compliance, bank verify, "
                "attendance agent, rate cards) must be included with "
                "app.include_router(...). Verify the relevant *_routes.py "
                "imports cleanly."
            ),
        )

    return CheckResult(
        id="api-mount",
        category="api",
        title="API route inventory",
        status="pass",
        summary=f"All {len(expected_prefixes)} expected route groups registered; {len(found_paths)} total routes",
    )


# ─── Smoke checks (no outbound network) ─────────────────────────────────────


def _check_fuzzy_matcher_smoke() -> CheckResult:
    """The blended fuzzy scorer is the heart of Bank Verify + Attendance
    Agent. Sanity-check it against known cases — if these regress, every
    downstream verdict goes wrong silently."""
    try:
        from bank_verify import _name_match_score
    except Exception as exc:
        return CheckResult(
            id="smoke-fuzzy-matcher",
            category="smoke",
            title="Fuzzy name matcher (Bank Verify / Attendance Agent)",
            status="fail",
            summary="Could not import _name_match_score",
            evidence=f"{type(exc).__name__}: {exc}",
        )

    # Ground-truth cases — these are the canonical Nigerian-name scenarios
    # the engine is tuned for. Bands stay generous to absorb scorer drift
    # across rapidfuzz minor versions.
    cases = [
        # (a, b, expected_min, expected_max, label)
        ("MOHAMMED FARID ABDURRAMAN", "MOHAMMED FARID ABDURRAMAN", 100, 100, "exact"),
        ("Mohammed Farid Abdulrahman", "MOHAMMED FARID ABDURRAMAN", 85, 100, "Abdul vs Abdur typo"),
        ("Aisha Bello", "MOHAMMED FARID ABDURRAMAN", 0, 50, "unrelated mismatch"),
        ("Mohammed Tunde", "MOHAMMED FARID ABDURRAMAN", 0, 65, "shared first name attack"),
    ]

    failures = []
    for a, b, lo, hi, label in cases:
        score = _name_match_score(a, b)
        if not (lo <= score <= hi):
            failures.append(f"{label}: scored {score}, expected {lo}-{hi}")

    if failures:
        return CheckResult(
            id="smoke-fuzzy-matcher",
            category="smoke",
            title="Fuzzy name matcher",
            status="fail",
            summary=f"{len(failures)} of {len(cases)} canonical case(s) regressed",
            evidence="; ".join(failures),
            fix_hint=(
                "The blended scorer in bank_verify._name_match_score has "
                "drifted. Common causes: rapidfuzz upgrade, processor= "
                "argument lost, threshold constants changed. Compare against "
                "the canonical formula min(WRatio, token_sort_ratio + 10) "
                "with processor=str.lower."
            ),
        )

    return CheckResult(
        id="smoke-fuzzy-matcher",
        category="smoke",
        title="Fuzzy name matcher",
        status="pass",
        summary=f"All {len(cases)} canonical Nigerian-name cases pass",
    )


def _check_bank_code_lookup() -> CheckResult:
    """resolve_bank_code translates free-text bank names to Paystack codes.
    A regression here turns every verification into 'unverifiable'."""
    try:
        from bank_verify import resolve_bank_code
    except Exception as exc:
        return CheckResult(
            id="smoke-bank-code-lookup",
            category="smoke",
            title="Bank code lookup",
            status="fail",
            summary="Could not import resolve_bank_code",
            evidence=f"{type(exc).__name__}: {exc}",
        )

    cases = [
        ("Opay", "999992"),
        ("GTBank", "058"),
        ("Access Bank", "044"),
        ("Kuda", "50211"),
        ("Zenith", "057"),
    ]
    failures = []
    for name, expected in cases:
        got = resolve_bank_code(name)
        if got != expected:
            failures.append(f"{name!r} → {got!r}, expected {expected!r}")

    if failures:
        return CheckResult(
            id="smoke-bank-code-lookup",
            category="smoke",
            title="Bank code lookup",
            status="fail",
            summary=f"{len(failures)} bank name(s) didn't resolve correctly",
            evidence="; ".join(failures),
            fix_hint="BANK_CODES dict in bank_verify.py may have drifted.",
        )

    return CheckResult(
        id="smoke-bank-code-lookup",
        category="smoke",
        title="Bank code lookup",
        status="pass",
        summary=f"All {len(cases)} bank names resolve to the expected Paystack code",
    )


def _check_attendance_e2e_smoke() -> CheckResult:
    """Run the Attendance Payment Agent end-to-end on in-memory test data.
    Pure-Python; no outbound network. Catches regressions in the matcher,
    rate-card application, and accuracy-flag generation in one shot."""
    try:
        import io

        from openpyxl import Workbook

        from attendance_agent import (
            match_and_build_run,
            parse_attendance_log,
            parse_payment_info,
        )
        from models import RateCard, RateLine
    except Exception as exc:
        return CheckResult(
            id="smoke-attendance-e2e",
            category="smoke",
            title="Attendance Payment Agent end-to-end",
            status="fail",
            summary="Could not import the agent or its dependencies",
            evidence=f"{type(exc).__name__}: {exc}",
        )

    # Build two in-memory xlsx files that exercise all three buckets
    wb1 = Workbook(); ws1 = wb1.active
    ws1.append(["Participant Name", "Day 1", "Day 2"])
    ws1.append(["Alpha Person", "x", "x"])
    ws1.append(["Beta Person", "x", ""])
    ws1.append(["Gamma Person", "", ""])         # registered, didn't show
    ws1.append(["Delta Person", "x", "x"])       # attended, no payment info
    buf1 = io.BytesIO(); wb1.save(buf1); buf1.seek(0)

    wb2 = Workbook(); ws2 = wb2.active
    ws2.append(["Name", "Role", "Account Number", "Bank"])
    ws2.append(["Alpha Person", "Facilitator", "1111111111", "GTBank"])
    ws2.append(["Beta Person",  "Participant", "2222222222", "Opay"])
    ws2.append(["Gamma Person", "Participant", "3333333333", "Access Bank"])
    buf2 = io.BytesIO(); wb2.save(buf2); buf2.seek(0)

    try:
        att = parse_attendance_log(buf1)
        pay = parse_payment_info(buf2)
        card = RateCard(
            id="smoke",
            name="Smoke",
            default_rate_per_day=10_000,
            roles=[
                RateLine(role="Facilitator", amount_per_day=20_000),
                RateLine(role="Participant", amount_per_day=10_000),
            ],
        )
        run = match_and_build_run(
            event_name="Smoke",
            rate_per_day=10_000,
            attendance=att,
            payment_info=pay,
            rate_card=card,
        )
    except Exception as exc:
        return CheckResult(
            id="smoke-attendance-e2e",
            category="smoke",
            title="Attendance Payment Agent end-to-end",
            status="fail",
            summary="Engine threw on a known-good input",
            evidence=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )

    # Expected: 2 paid (Alpha 2 × ₦20k = 40k, Beta 1 × ₦10k = 10k), 1
    # no_attendance (Gamma), 1 no_payment_info (Delta), total 50k.
    issues = []
    if run.paid_count != 2:
        issues.append(f"paid_count={run.paid_count}, expected 2")
    if run.no_attendance_count != 1:
        issues.append(f"no_attendance_count={run.no_attendance_count}, expected 1")
    if run.no_payment_info_count != 1:
        issues.append(f"no_payment_info_count={run.no_payment_info_count}, expected 1")
    if int(run.total_to_pay) != 50_000:
        issues.append(f"total_to_pay={run.total_to_pay}, expected 50000")

    if issues:
        return CheckResult(
            id="smoke-attendance-e2e",
            category="smoke",
            title="Attendance Payment Agent end-to-end",
            status="fail",
            summary="Engine ran but the output differs from expectations",
            evidence="; ".join(issues),
            fix_hint=(
                "Recent changes to the matcher, rate-card application, or "
                "bucket logic in attendance_agent.py probably broke "
                "expected behaviour. Revisit the smoke baseline."
            ),
        )

    return CheckResult(
        id="smoke-attendance-e2e",
        category="smoke",
        title="Attendance Payment Agent end-to-end",
        status="pass",
        summary=(
            f"Bucketed 2 paid + 1 no_attendance + 1 no_payment_info "
            f"correctly; rate card produced ₦50,000 total"
        ),
    )


# ─── Data integrity checks ──────────────────────────────────────────────────


def _check_data_integrity_for(dir_name: str, model_name: str) -> CheckResult:
    """Walk a persistence directory and confirm every record parses
    cleanly under its Pydantic model. Surfaces orphans from old schemas."""
    path = _ROOT / dir_name
    if not path.exists():
        return CheckResult(
            id=f"data-{dir_name}",
            category="data",
            title=f"Persisted {dir_name} integrity",
            status="skip",
            summary=f"{dir_name}/ doesn't exist yet — no records to validate",
        )

    try:
        import models as models_module
        ModelClass = getattr(models_module, model_name)
    except Exception as exc:
        return CheckResult(
            id=f"data-{dir_name}",
            category="data",
            title=f"Persisted {dir_name} integrity",
            status="fail",
            summary=f"Could not resolve model {model_name}",
            evidence=f"{type(exc).__name__}: {exc}",
        )

    files = list(path.glob("*.json"))
    if not files:
        return CheckResult(
            id=f"data-{dir_name}",
            category="data",
            title=f"Persisted {dir_name} integrity",
            status="skip",
            summary=f"{dir_name}/ is empty",
        )

    bad: list[str] = []
    for f in files:
        try:
            ModelClass.model_validate_json(f.read_text())
        except Exception as exc:
            bad.append(f"{f.name}: {type(exc).__name__}")

    if bad:
        return CheckResult(
            id=f"data-{dir_name}",
            category="data",
            title=f"Persisted {dir_name} integrity",
            status="warn",
            summary=f"{len(bad)} of {len(files)} record(s) failed to parse",
            evidence="; ".join(bad[:5]) + (f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""),
            fix_hint=(
                f"Some records in {dir_name}/ are from an older schema. "
                f"Either migrate them (Pydantic forwards-compat layer) or "
                f"delete the affected files. List with: "
                f"`ls {dir_name}/`"
            ),
        )

    return CheckResult(
        id=f"data-{dir_name}",
        category="data",
        title=f"Persisted {dir_name} integrity",
        status="pass",
        summary=f"All {len(files)} record(s) parse cleanly",
    )


# ─── Orchestrator ───────────────────────────────────────────────────────────


def run_full_check() -> DiagnosticReport:
    """
    Run every check in the suite, return a structured report. Safe to call
    from anywhere — never raises (each check is wrapped in _time_check).
    """
    started_at = _now_iso()
    started_t = time.monotonic()

    checks: list[CheckResult] = []

    # Environment
    checks.append(_time_check(_check_python_version))
    checks.append(_time_check(_check_anthropic_key))
    checks.append(_time_check(_check_paystack_key))

    # Filesystem — one check per persistence dir; runs mkdir as a side
    # effect so a fresh checkout boots into a healthy state.
    for d in _PERSIST_DIRS:
        checks.append(_time_check(lambda d=d: _check_persistence_dir(d)))

    # Engine imports
    engines = [
        ("models", ["BankVerifyBatchResult", "AttendancePaymentRun", "RateCard", "DiagnosticReport"]),
        ("bank_verify", ["verify_batch", "verify_account", "resolve_bank_code", "parse_schedule", "_name_match_score"]),
        ("attendance_agent", ["match_and_build_run", "parse_attendance_log", "parse_payment_info", "google_sheets_xlsx_bytes"]),
        ("compliance", ["interpret_policy", "check_payment_safe", "check_payment_batch"]),
        ("screener", ["extract_applicant", "extract_batch"]),
    ]
    for module, attrs in engines:
        checks.append(_time_check(lambda m=module, a=attrs: _check_engine_import(m, a)))

    # API routes
    checks.append(_time_check(_check_api_routes))

    # Smoke
    checks.append(_time_check(_check_fuzzy_matcher_smoke))
    checks.append(_time_check(_check_bank_code_lookup))
    checks.append(_time_check(_check_attendance_e2e_smoke))

    # Data integrity
    data_dirs = [
        ("rulebooks", "PolicyRulebook"),
        ("checks", "ComplianceCheckResult"),
        ("verifications", "BankVerifyBatchResult"),
        ("rate_cards", "RateCard"),
        ("attendance_runs", "AttendancePaymentRun"),
    ]
    for d, model_name in data_dirs:
        checks.append(_time_check(lambda d=d, m=model_name: _check_data_integrity_for(d, m)))

    # Aggregate
    finished_at = _now_iso()
    duration_ms = int((time.monotonic() - started_t) * 1000)

    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    skipped = sum(1 for c in checks if c.status == "skip")

    if failed > 0:
        overall = "broken"
    elif warned > 2:
        overall = "degraded"
    else:
        overall = "healthy"

    return DiagnosticReport(
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        total=len(checks),
        passed=passed,
        warned=warned,
        failed=failed,
        skipped=skipped,
        overall=overall,  # type: ignore[arg-type]
        checks=checks,
    )


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_full_check()
    print()
    print("─" * 70)
    print(f"  DOCex Self-Check — overall: {report.overall.upper()}")
    print("─" * 70)
    print(
        f"  {report.passed} passed · {report.warned} warned · "
        f"{report.failed} failed · {report.skipped} skipped"
    )
    print(f"  ran in {report.duration_ms}ms")
    print()
    icons = {"pass": "✓", "warn": "!", "fail": "✗", "skip": "·"}
    colors = {"pass": "\033[92m", "warn": "\033[93m", "fail": "\033[91m", "skip": "\033[90m"}
    reset = "\033[0m"
    by_category: dict[str, list[CheckResult]] = {}
    for c in report.checks:
        by_category.setdefault(c.category, []).append(c)
    for cat, group in by_category.items():
        print(f"  {cat.upper()}")
        for c in group:
            color = colors.get(c.status, "")
            icon = icons.get(c.status, "·")
            print(f"    {color}{icon} {c.title}{reset}")
            print(f"        {c.summary}")
            if c.evidence:
                print(f"        evidence: {c.evidence[:120]}")
            if c.fix_hint:
                print(f"        fix: {c.fix_hint[:120]}")
        print()
    sys.exit(0 if report.overall != "broken" else 1)
