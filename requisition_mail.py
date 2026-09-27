"""
requisition_mail.py — email the people a payment request needs.

The in-app bell only reaches someone who happens to be signed in. People in
finance teams live in their inbox, so every event that needs a person also
sends them an email:

  assigned   the approving department's people (not viewers):
             "Action needed: REQ-0012 · ₦850,000 · Hotel Maiduguri"
  cc         the org's copy rules (e.g. the ED above ₦2m):
             "FYI: REQ-0012 raised · ₦2,500,000 · ..." — informed, not asked
  returned / declined / paid / held
             the person who raised it, personally

The email links to the request; approving still needs a signed-in session,
so a forwarded email cannot approve anything. Nobody is emailed about their
own action. Gated by the `email_notifications` flag; with no SMTP configured
nothing is sent and nothing fails. Sending runs in the background so an
approval never waits on a mail server.
"""
from __future__ import annotations

import os
import threading
from typing import Callable, Iterable, Optional

# Replaced in tests with a capturing stand-in.
_sender: Optional[Callable[[str, str, str], bool]] = None
_background = True

_ACTING_ROLES = {"reviewer", "approver", "admin"}

_KINDS_EMAILED = {"assigned", "cc", "returned", "declined", "paid", "held"}


def enabled(org_id: str) -> bool:
    try:
        import notifications
        import org_config
        return notifications.is_smtp_configured() and org_config.feature_enabled(org_id, "email_notifications")
    except Exception:  # noqa: BLE001
        return False


def _send(to: str, subject: str, body: str) -> None:
    try:
        if _sender is not None:
            _sender(to, subject, body)
            return
        import notifications
        notifications.send_raw_email(to, subject, body)
    except Exception as exc:  # noqa: BLE001 — the action it accompanies already succeeded
        print(f"[requisition_mail] not sent to {to}: {exc}")


def department_people(org_id: str, department: str) -> list[str]:
    """Active people in a department who can act (viewers only watch)."""
    if not department:
        return []
    import auth
    return sorted({u.email.strip().lower() for u in auth.list_public(org_id)
                   if (u.department or "").lower() == department.lower()
                   and getattr(u, "active", True)
                   and (u.role or "") in _ACTING_ROLES})


def _name_of(org_id: str, email: str) -> str:
    try:
        import auth
        u = auth.get_by_email(email, org_id)
        return (u.name if u and u.name else "") or email
    except Exception:  # noqa: BLE001
        return email


def _dept_name(org_id: str, key: str) -> str:
    try:
        import departments
        d = next((d for d in departments.load(org_id).departments if d.key == key), None)
        return (d.name if d and d.name else "") or key
    except Exception:  # noqa: BLE001
        return key


def _money(amount: float, currency: str) -> str:
    sym = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€"}.get((currency or "").upper(), "")
    return f"{sym}{amount:,.0f}" if sym else f"{amount:,.2f} {currency}"


def _link(req) -> str:
    base = (os.environ.get("APP_URL") or "").rstrip("/")
    return f"{base}/requisitions/{req.id}" if base else ""


def compose(org_id: str, req, kind: str, *, step_label: str = "", note: str = "",
            reason: str = "") -> tuple[str, str]:
    what = f"{req.ref} · {_money(req.amount, req.currency)} · {req.vendor_name}"
    raiser = _name_of(org_id, req.submitted_by)
    blocking = [c for c in (req.checks or [])
                if getattr(c.result, "value", c.result) == "fail" and not c.overridden]
    subject = {
        "assigned": f"Action needed: {what}",
        "cc": f"FYI: {what}",
        "returned": f"Returned to you: {what}",
        "declined": f"Declined: {what}",
        "paid": f"Paid: {what}",
        "held": f"On hold: {what}",
    }.get(kind, f"{req.ref}: update")

    lines = []
    if kind == "assigned":
        lines.append(f"{req.ref} is waiting for you{f' ({step_label})' if step_label else ''}.")
    elif kind == "cc":
        lines.append(f"A payment request has been raised that you are copied on{f' ({reason})' if reason else ''}. "
                     "No action is needed from you.")
    elif kind == "returned":
        lines.append(f"Your request {req.ref} was returned to you to correct and resubmit.")
    elif kind == "declined":
        lines.append(f"Your request {req.ref} was declined.")
    elif kind == "paid":
        lines.append(f"Your request {req.ref} has been paid.")
    elif kind == "held":
        lines.append(f"Your request {req.ref} has been put on hold.")
    if note:
        lines += ["", f"Note: {note}"]
    lines += [
        "",
        f"Payee:      {req.vendor_name}" + (f" and {len(req.payees) - 1} others" if len(req.payees or []) > 1 else ""),
        f"Amount:     {_money(req.amount, req.currency)}",
        f"Raised by:  {raiser}" + (f" ({_dept_name(org_id, req.department)})" if req.department else ""),
    ]
    if req.description:
        lines.append(f"For:        {req.description}")
    if req.project_code:
        lines.append(f"Project:    {req.project_code}")
    if kind == "assigned" and blocking:
        lines.append(f"Checks:     {len(blocking)} need{'s' if len(blocking) == 1 else ''} attention before it can be approved")
    link = _link(req)
    if link:
        lines += ["", f"Open it in DOCex: {link}"]
    lines += ["", "You can only approve after signing in to DOCex; this email cannot approve anything."]
    return subject, "\n".join(lines)


def notify(org_id: str, req, kind: str, *, department: str = "", to_user: str = "",
           actor: str = "", step_label: str = "", note: str = "", reason: str = "") -> list[str]:
    """Email the right people for one event. Returns who was emailed."""
    if kind not in _KINDS_EMAILED or not enabled(org_id):
        return []
    recipients: Iterable[str]
    if to_user:
        recipients = [to_user.strip().lower()]
    else:
        recipients = department_people(org_id, department)
    me = (actor or "").strip().lower()
    recipients = sorted({r for r in recipients if r and r != me})
    if not recipients:
        return []
    subject, body = compose(org_id, req, kind, step_label=step_label, note=note, reason=reason)

    def _go():
        for r in recipients:
            _send(r, subject, body)

    if _background:
        threading.Thread(target=_go, daemon=True).start()
    else:
        _go()
    return recipients
