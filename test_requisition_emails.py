"""
The people who must act on a payment request are emailed; nobody copies
links by hand.

Found checking why links were being forwarded manually:
  * submitting a DRAFT told nobody at all — not even the first approver.
    Since WO-44 every request with documents is raised as draft → attach →
    submit, so every such request reached no one;
  * the "copy the Executive Director above ₦2m" rule only fired on the
    one-step create path, so for the same reason it never fired;
  * returned / declined / paid told the submitter's whole department rather
    than the person who raised it;
  * and none of it was email — only the in-app bell.

Gated by `email_notifications`. No SMTP configured: nothing is sent and
nothing breaks.

Run: python test_requisition_emails.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-reqmail-")
os.environ["DOCEX_ORG"] = "acme"
os.environ["APP_URL"] = "https://app.example.org"
os.environ["SMTP_HOST"] = "smtp.example.org"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import attachments  # noqa: E402

attachments.set_backend(attachments.LocalDiskAttachmentBackend(Path(_TMP) / "files"))

import auth as A  # noqa: E402

A._SECRET_FILE = Path(_TMP) / ".s"
A._secret_cache = None

import org_config  # noqa: E402
import requisition_mail  # noqa: E402

SENT: list[tuple[str, str, str]] = []
requisition_mail._sender = lambda to, subject, body: SENT.append((to, subject, body)) or True
requisition_mail._background = False          # send inline so the test can see it

_passed = _failed = 0
PW = "correct-horse-battery"


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


PROFILE = {
    "org_id": "acme", "currency": "NGN",
    "departments": [
        {"key": "program", "name": "Programmes"},
        {"key": "finance", "name": "Finance"},
        {"key": "ed", "name": "Executive Director", "is_final_authority": True},
    ],
    "workflow": {
        "max_amount": 100_000_000,
        "steps": [{"key": "finance", "label": "Finance review", "department": "finance"},
                  {"key": "ed", "label": "ED approval", "department": "ed"}],
        "cc_rules": [{"min_amount": 1_000_000, "department": "ed", "label": "Executive Director"}],
    },
    "features": {"email_notifications": True, "requisition_attachments": True},
}

USERS = [
    ("amina@acme.org", "Amina", "program", "reviewer"),
    ("sam@acme.org", "Sam", "program", "reviewer"),
    ("femi@acme.org", "Femi", "finance", "approver"),
    ("tunde@acme.org", "Tunde", "finance", "approver"),
    ("fola@acme.org", "Fola", "finance", "viewer"),
    ("ngozi@acme.org", "Dr Ngozi", "ed", "approver"),
]


def _client():
    from fastapi.testclient import TestClient
    import api.main as m
    return TestClient(m.app, raise_server_exceptions=False)


def _h(c, email):
    tok = c.post("/auth/login", json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _to(subject_part: str) -> set[str]:
    return {to for to, subj, _ in SENT if subject_part in subj}


def _raise_via_draft(c, amount: str) -> dict:
    H = _h(c, "amina@acme.org")
    r = c.post("/requisitions", headers=H, data={"vendor_name": "Hotel Maiduguri", "amount": amount,
                                                 "description": "Workshop venue", "submit": "false"})
    rid = r.json()["id"]
    c.post(f"/requisitions/{rid}/attachments", headers=H,
           files={"file": ("invoice.pdf", b"%PDF-1.4", "application/pdf")}, data={"document_type": "invoice"})
    return c.post(f"/requisitions/{rid}/submit", headers=H).json()


def test_submitting_a_draft_emails_the_first_approvers() -> None:
    print("\nDraft → attach → submit: Finance's approvers are emailed; nobody else")
    c = _client()
    SENT.clear()
    req = _raise_via_draft(c, "850000")
    to = _to("Action needed")
    check("Finance approvers emailed", to == {"femi@acme.org", "tunde@acme.org"}, str(to))
    check("not the viewer, not the submitter", "fola@acme.org" not in to and "amina@acme.org" not in to)
    body = next(b for t, s, b in SENT if "Action needed" in s)
    check("the email has a link to the request",
          f"https://app.example.org/requisitions/{req['id']}" in body, body[:300])
    check("and says what it is", "Hotel Maiduguri" in body and "850,000" in body and "Workshop venue" in body,
          body[:300])
    check("below the copy threshold, nobody copied", not _to("FYI"))
    import notification_center as nc
    feed = nc.list_for("finance", org_id="acme")
    check("the in-app bell fires too (it didn't for drafts)", any(n.txn_ref == req["ref"] for n in feed))


def test_a_large_request_copies_the_senior_people() -> None:
    print("\nAt or above ₦1m: the ED is copied by email — informed, not asked to act")
    c = _client()
    SENT.clear()
    _raise_via_draft(c, "2500000")
    check("ED copied", _to("FYI") == {"ngozi@acme.org"}, str(_to("FYI")))
    check("copy is not an 'action needed'", "ngozi@acme.org" not in _to("Action needed"))


def test_the_next_step_is_emailed_when_one_approves() -> None:
    print("\nFinance approves: the next step (ED) is emailed")
    c = _client()
    req = _raise_via_draft(c, "300000")
    SENT.clear()
    r = c.post(f"/requisitions/{req['id']}/decide", headers=_h(c, "femi@acme.org"),
               data={"decision": "approved", "notes": "fine"})
    check("approved at finance", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    check("ED emailed", _to("Action needed") == {"ngozi@acme.org"}, str(SENT))
    check("the approver isn't emailed about their own action", "femi@acme.org" not in {t for t, _, _ in SENT})


def test_a_return_goes_to_the_person_who_raised_it() -> None:
    print("\nReturned: the submitter is emailed, not their whole department")
    c = _client()
    req = _raise_via_draft(c, "120000")
    SENT.clear()
    c.post(f"/requisitions/{req['id']}/decide", headers=_h(c, "femi@acme.org"),
           data={"decision": "returned", "notes": "attach the quotation"})
    to = {t for t, _, _ in SENT}
    check("submitter emailed", to == {"amina@acme.org"}, str(to))
    check("with the reason", any("attach the quotation" in b for _, _, b in SENT))


def test_flag_off_sends_nothing() -> None:
    print("\nemail_notifications off: nothing sent")
    org_config.set_features("acme", email_notifications=False)
    try:
        c = _client()
        SENT.clear()
        _raise_via_draft(c, "5000")
        check("no emails", SENT == [], str(SENT))
    finally:
        org_config.set_features("acme", email_notifications=True)


def test_no_mail_server_breaks_nothing() -> None:
    print("\nNo SMTP configured: the request still goes through")
    saved = os.environ.pop("SMTP_HOST")
    try:
        c = _client()
        SENT.clear()
        req = _raise_via_draft(c, "6000")
        check("submitted", req.get("status") == "in_review", str(req.get("status")))
        check("no emails attempted", SENT == [])
    finally:
        os.environ["SMTP_HOST"] = saved


if __name__ == "__main__":
    print("Payment requests email the people who must act")
    import copy
    org_config.apply_profile(copy.deepcopy(PROFILE))
    for email, name, dept, role in USERS:
        A.create_user(email, name, PW, dept, role, org_id="acme")
    test_submitting_a_draft_emails_the_first_approvers()
    test_a_large_request_copies_the_senior_people()
    test_the_next_step_is_emailed_when_one_approves()
    test_a_return_goes_to_the_person_who_raised_it()
    test_flag_off_sends_nothing()
    test_no_mail_server_breaks_nothing()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
