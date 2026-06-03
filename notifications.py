"""
DOCex notification system.

Sends email notifications when compliance checks complete. Triggered
server-side from api/compliance_routes.py after each check is saved.

Configuration is via env vars — works with any SMTP provider:
  SMTP_HOST           e.g. smtp.resend.com, smtp.gmail.com, smtp.office365.com
  SMTP_PORT           typically 587 (STARTTLS) or 465 (SSL). Default 587.
  SMTP_USERNAME       provider username (or "resend" for Resend)
  SMTP_PASSWORD       provider password / API key
  SMTP_FROM_ADDRESS   the From address — must be verified with the provider
  SMTP_FROM_NAME      display name (default "DOCex")
  APP_URL             frontend URL, used to build audit URLs in the email
                      body. e.g. https://docex.vercel.app

If SMTP_HOST is unset, notifications are silently skipped — useful for
local dev where you don't want to spam yourself.

If the rulebook has no notification_email or no notification_trigger,
notifications are silently skipped — opt-in per rulebook.
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from models import ComplianceCheckResult, PolicyRulebook, RuleResult


# Loose email detection — good enough to decide "is pending_with an address
# we can email, or just a person's name?" Not RFC-complete on purpose.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_email(value: Optional[str]) -> bool:
    """True if `value` is something we can send an email to."""
    return bool(value and _EMAIL_RE.match(value.strip()))


# ─── Pure helpers (subject + body) ──────────────────────────────────────────

_VERDICT_LABELS = {
    "pass": "PASS",
    "flag": "FLAG",
    "block": "BLOCK",
    "not_applicable": "N/A",
    "insufficient_evidence": "NEED INFO",
}

# Severity ordering — used to pick the top issues for the email body
_SEVERITY = {
    "block": 0,
    "flag": 1,
    "insufficient_evidence": 2,
    "pass": 3,
    "not_applicable": 4,
}


def _build_subject(check: ComplianceCheckResult) -> str:
    """Short, scannable subject. Verdict first so it sorts well in inboxes."""
    verdict_word = check.overall_verdict.capitalize()
    return f"[DOCex] {verdict_word}: {check.payment_label}"


def _format_finding(idx: int, result: RuleResult) -> str:
    label = _VERDICT_LABELS.get(result.verdict, result.verdict.upper())
    lines = [f"  {idx}. [{label}] {result.rule_description}"]
    if result.reasoning:
        # Indent the reasoning visually so it's clearly a sub-line
        lines.append(f"     → {result.reasoning}")
    return "\n".join(lines)


def _build_body(
    check: ComplianceCheckResult,
    rulebook: PolicyRulebook,
    audit_url: Optional[str],
) -> str:
    # Counts by verdict
    counts: dict[str, int] = {
        "pass": 0,
        "flag": 0,
        "block": 0,
        "not_applicable": 0,
        "insufficient_evidence": 0,
    }
    for r in check.results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    # Top 3 issues — blocks first, then flags, then need-info. Skip passes/NA.
    sorted_issues = sorted(
        check.results,
        key=lambda r: _SEVERITY.get(r.verdict, 99),
    )
    top_issues = [
        r for r in sorted_issues if r.verdict not in ("pass", "not_applicable")
    ][:3]

    lines = [
        "A compliance check has just completed.",
        "",
        f"Verdict:   {check.overall_verdict.upper()}",
        f"Payment:   {check.payment_label}",
        f"Rulebook:  {check.rulebook_name}",
        f"Checked:   {check.created_at or 'just now'}",
        "",
        f"Summary: {check.overall_summary}",
        "",
        "Findings:",
        f"  Pass:      {counts['pass']}",
        f"  Flag:      {counts['flag']}",
        f"  Block:     {counts['block']}",
        f"  Need info: {counts['insufficient_evidence']}",
        f"  N/A:       {counts['not_applicable']}",
    ]

    if top_issues:
        lines.append("")
        lines.append("Top issues:")
        for i, issue in enumerate(top_issues, 1):
            lines.append(_format_finding(i, issue))

    if audit_url:
        lines.append("")
        lines.append("View the full audit trail:")
        lines.append(audit_url)

    lines.append("")
    lines.append("---")
    lines.append(
        "This is an automated notification from DOCex. To change "
        "notification settings, edit the rulebook in DOCex."
    )
    return "\n".join(lines)


# ─── SMTP send ─────────────────────────────────────────────────────────────


def _is_smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _check_url(check: ComplianceCheckResult) -> Optional[str]:
    """Deep link back to the check, if APP_URL is configured."""
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    return f"{app_url}/compliance/checks/{check.payment_id}" if app_url else None


def _send_raw_email(to_address: str, subject: str, body: str) -> bool:
    """Low-level send used by every notification type.

    Provider-agnostic: works with any SMTP host — Outlook/Office 365
    (smtp.office365.com), Gmail (smtp.gmail.com), Resend, etc. Returns True
    if a message was handed to the SMTP server, False if SMTP isn't
    configured. Raises only on real transport errors so callers can decide
    whether to swallow them (notifications must never break the action they
    accompany).
    """
    if not _is_smtp_configured():
        return False

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USERNAME", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    from_address = os.environ.get(
        "SMTP_FROM_ADDRESS",
        smtp_user or "notifications@docex.app",
    )
    from_name = os.environ.get("SMTP_FROM_NAME", "DOCex")

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_address}>"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # SSL on 465, STARTTLS on 587 (and everywhere else)
    if smtp_port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=ssl.create_default_context())
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)

    return True


# ─── Escalation + clarification emails (Sprint 2) ───────────────────────────
#
# These replace the Outlook back-and-forth: when an officer escalates a check
# or asks a question, the responsible party gets an email with the context and
# a one-click link straight to the check — no copy-pasting, no lost threads.


def send_escalation_email(
    check: ComplianceCheckResult,
    to_address: str,
    reason: Optional[str],
) -> bool:
    """Email the person a check has been escalated to. Returns True if sent."""
    if not looks_like_email(to_address):
        return False
    url = _check_url(check)
    subject = f"[DOCex] Escalated to you: {check.payment_label}"
    lines = [
        "A compliance check has been escalated to you for review.",
        "",
        f"Payment:  {check.payment_label}",
        f"Rulebook: {check.rulebook_name}",
        f"Verdict:  {check.overall_verdict.upper()}",
    ]
    if reason:
        lines += ["", f"Note from the officer:", f"  {reason}"]
    if url:
        lines += ["", "Review and act on it here:", url]
    lines += [
        "",
        "---",
        "Automated handoff from DOCex. Everything you decide is captured on "
        "the check's audit trail.",
    ]
    return _send_raw_email(to_address, subject, "\n".join(lines))


def send_clarification_email(
    check: ComplianceCheckResult,
    to_address: str,
    question: str,
) -> bool:
    """Email a clarification question to the responsible party. Returns True
    if sent."""
    if not looks_like_email(to_address):
        return False
    url = _check_url(check)
    subject = f"[DOCex] Question on {check.payment_label}"
    lines = [
        "A DOCex compliance reviewer has a question before this payment can "
        "proceed.",
        "",
        f"Payment:  {check.payment_label}",
        f"Rulebook: {check.rulebook_name}",
        "",
        "Question:",
        f"  {question}",
    ]
    if url:
        lines += [
            "",
            "Answer directly on the check (keeps everything in one thread):",
            url,
        ]
    lines += [
        "",
        "---",
        "Automated request from DOCex. Replying on the check keeps the "
        "question, your answer, and the audit trail together.",
    ]
    return _send_raw_email(to_address, subject, "\n".join(lines))


def _should_send(verdict: str, trigger: Optional[str]) -> bool:
    if not trigger:
        return False
    if trigger == "always":
        return True
    if trigger == "flagged_or_blocked":
        return verdict != "approved"
    if trigger == "blocked_only":
        return verdict == "blocked"
    return False


def send_check_notification(
    check: ComplianceCheckResult,
    rulebook: PolicyRulebook,
) -> bool:
    """
    Send a compliance notification email if conditions are met.

    Returns True if an email was actually sent, False if it was skipped
    (no SMTP config, no recipient, or trigger doesn't match the verdict).
    Raises only on actual SMTP / transport errors so the caller can log
    them. The caller is responsible for not letting a notification failure
    break the check itself.
    """
    if not _is_smtp_configured():
        return False
    if not rulebook.notification_email:
        return False
    if not _should_send(check.overall_verdict, rulebook.notification_trigger):
        return False

    audit_url = _check_url(check)
    return _send_raw_email(
        rulebook.notification_email,
        _build_subject(check),
        _build_body(check, rulebook, audit_url),
    )
