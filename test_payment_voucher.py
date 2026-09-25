"""
WO-41 — payment voucher export.

Named after the failures each one prevents, not the functions they call.

Run: python test_payment_voucher.py
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-voucher-")
os.environ["DOCEX_ORG"] = "alpha"

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import payment_voucher as pv  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


# ─── fakes: just enough shape, no engine dependency ─────────────────────────


class _Payee:
    def __init__(self, name, amount, bank_name="", purpose=""):
        self.name, self.amount, self.bank_name, self.purpose = name, amount, bank_name, purpose


class _Line:
    def __init__(self, description, line_total):
        self.description, self.line_total = description, line_total


class _Approval:
    def __init__(self, step, actor, decision="approved", at="2026-09-20T10:00:00+00:00"):
        self.step, self.actor, self.decision, self.at = step, actor, decision, at


class _Req:
    def __init__(self, **kw):
        self.id = kw.get("id", "req-1")
        self.ref = kw.get("ref", "REQ-0001")
        self.vendor_name = kw.get("vendor_name", "Zenith Travels Ltd")
        self.vendor_bank_name = kw.get("vendor_bank_name", "GTBank")
        self.amount = kw.get("amount", 500000.0)
        self.currency = "NGN"
        self.category = kw.get("category", "transportation_ground")
        self.project_code = kw.get("project_code", "B24")
        self.grant_code = kw.get("grant_code", "CARE")
        self.description = kw.get("description", "Field travel, September")
        self.amount_in_words = kw.get("amount_in_words", "Five Hundred Thousand Naira Only")
        self.submitted_by = kw.get("submitted_by", "officer@neem")
        self.submitted_at = kw.get("submitted_at", "2026-09-18T09:00:00+00:00")
        self.payees = kw.get("payees", [])
        self.budget_lines = kw.get("budget_lines", [])
        self.approvals = kw.get("approvals", [])


NEEM_TEMPLATE = {
    "title": "Payment Voucher",
    "letterhead": {"org_name": "Neem Foundation", "rc_number": "83813",
                   "address_lines": ["2 Kwa Falls Street,", "Maitama, Abuja"]},
    "certification": "I certify that the above account is correct...",
    "signature_roles": [
        {"label": "Prepared by", "source": "submitter"},
        {"label": "Checked by", "source": "finance"},
        {"label": "Review & Authorised by", "source": "admin"},
        {"label": "Approved by", "source": "aed"},
        {"label": "Received by", "source": ""},
    ],
    "account_codes": {"transportation_ground": "52052", "client_support_food": "9600"},
    "pv_number_format": "{org}/{location}/{project_code}/{donor}/{MONYY}/PV/{seq}",
    "pv_org_prefix": "NF",
    "pv_location": "HQ",
}

_org_seq = 0


def _fresh(base: str, template: dict | None = None) -> str:
    """A brand-new org id per call, returned to the caller.

    Not a wipe. The store's list() returns records without their ids, so a
    generic clear is not possible — and a test that shares an org with the
    previous test is not isolated anyway. Minting a new org makes the
    isolation real rather than assumed.

    Learned the hard way: the voucher sequence carried across tests, and four
    assertions about "starts at 01" were checking a counter already at 11.
    """
    global _org_seq
    _org_seq += 1
    org = f"{base}-{_org_seq}"
    if template:
        pv.set_template(org, template)
    return org


# ─── tests ───────────────────────────────────────────────────────────────────


def test_the_letterhead_is_never_hardcoded() -> None:
    print("\nThe letterhead comes from config, so client two is not sent NEEM's voucher")
    org = _fresh("alpha", NEEM_TEMPLATE)
    v = pv.build_voucher(_Req(), org)
    check("org name from config", v.org_name == "Neem Foundation", v.org_name)
    check("RC number from config", v.rc_number == "83813", v.rc_number)
    check("address from config",
          v.address_lines == ["2 Kwa Falls Street,", "Maitama, Abuja"])
    check("title from config", v.title == "Payment Voucher")


def test_an_unconfigured_org_still_gets_a_usable_voucher() -> None:
    print("\nAn org that configured nothing gets a blank-letterhead voucher, not a crash")
    org = _fresh("beta")
    v = pv.build_voucher(_Req(), org)
    check("it renders", isinstance(v.total, float))
    check("no letterhead invented", v.org_name == "")
    check("no account code invented", v.lines[0].account_code == "")
    check("no PV number invented", v.pv_number == "")


def test_two_orgs_get_visibly_different_vouchers() -> None:
    print("\nOne engine, two templates — the argument for building this as CORE")
    a_org = _fresh("alpha", NEEM_TEMPLATE)
    g_org = _fresh("gamma", {
        "title": "Payment Authorisation",
        "letterhead": {"org_name": "Other Org Ltd", "rc_number": "11111",
                       "address_lines": ["Somewhere else"]},
        "signature_roles": [{"label": "Raised by", "source": "submitter"},
                            {"label": "Authorised by", "source": ""}],
        "account_codes": {"transportation_ground": "999"},
    })
    a = pv.build_voucher(_Req(id="r-a"), a_org)
    g = pv.build_voucher(_Req(id="r-g"), g_org)
    check("titles differ", a.title != g.title, f"{a.title} / {g.title}")
    check("letterheads differ", a.org_name != g.org_name)
    check("account codes differ", a.lines[0].account_code != g.lines[0].account_code,
          f"{a.lines[0].account_code} / {g.lines[0].account_code}")
    check("signature roles differ in number and wording",
          [s.label for s in a.signatures] != [s.label for s in g.signatures])
    check("neither leaked into the other", "Neem" not in g.org_name)


def test_an_unmapped_category_leaves_the_code_blank() -> None:
    print("\nAn unmapped category renders BLANK — a guessed code posts to the wrong ledger")
    org = _fresh("alpha", NEEM_TEMPLATE)
    v = pv.build_voucher(_Req(id="r-unmapped", category="venue"), org)
    check("code is empty, not guessed", v.lines[0].account_code == "",
          repr(v.lines[0].account_code))
    v2 = pv.build_voucher(_Req(id="r-mapped", category="transportation_ground"), org)
    check("a mapped category does carry its code", v2.lines[0].account_code == "52052")


def test_the_total_is_the_sum_of_what_is_printed() -> None:
    print("\nThe total is recomputed from the printed lines, never read from a field")
    org = _fresh("alpha", NEEM_TEMPLATE)
    v = pv.build_voucher(_Req(id="r-b", amount=999999.0, budget_lines=[
        _Line("Fuel", 120000.0), _Line("Driver allowance", 45000.0),
        _Line("Tolls", 5500.0)]), org)
    check("three lines", len(v.lines) == 3)
    check("total is the sum of the lines, not the stored amount",
          v.total == 170500.0, str(v.total))


def test_a_batch_becomes_one_voucher_with_payees_as_lines() -> None:
    print("\nA 100-payee run is one voucher, not 100")
    org = _fresh("alpha", NEEM_TEMPLATE)
    payees = [_Payee(f"Person {i}", 5000.0, "GTBank") for i in range(1, 13)]
    v = pv.build_voucher(_Req(id="r-batch", payees=payees), org)
    check("one line per payee", len(v.lines) == 12)
    check("payee box says Various with the count", v.payee == "Various (12 payees)", v.payee)
    check("total is the batch total", v.total == 60000.0, str(v.total))
    single = pv.build_voucher(_Req(id="r-one", payees=[_Payee("Aisha Bello", 7000.0)]), org)
    check("a single payee is named rather than 'Various'", single.payee == "Aisha Bello")
    mixed = pv.build_voucher(_Req(id="r-mixed", payees=[
        _Payee("A", 1.0, "GTBank"), _Payee("B", 1.0, "Zenith")]), org)
    check("mixed banks report Various rather than the first one",
          mixed.bank_name == "Various", mixed.bank_name)


def test_signatures_reflect_the_approval_trail_not_the_status() -> None:
    print("\nSignature lines are filled from recorded approvals, and only those")
    org = _fresh("alpha", NEEM_TEMPLATE)
    req = _Req(id="r-sig", approvals=[
        _Approval("finance", "finance@neem", at="2026-09-19T10:00:00+00:00"),
        _Approval("admin", "admin@neem", at="2026-09-19T14:00:00+00:00"),
    ])
    by = {s.label: s for s in pv.build_voucher(req, org).signatures}
    check("Prepared by is the submitter", by["Prepared by"].name == "officer@neem")
    check("Prepared by carries the submission date",
          by["Prepared by"].date == "2026-09-18", by["Prepared by"].date)
    check("Checked by filled from the finance approval",
          by["Checked by"].name == "finance@neem")
    check("Review & Authorised filled from the admin approval",
          by["Review & Authorised by"].name == "admin@neem")
    check("Approved by is BLANK — the AED has not signed yet",
          by["Approved by"].name == "", by["Approved by"].name)
    check("Received by is always blank — unknowable before payment",
          by["Received by"].name == "")


def test_a_declined_step_never_appears_as_a_signature() -> None:
    print("\nA decline is not a signature")
    org = _fresh("alpha", NEEM_TEMPLATE)
    req = _Req(id="r-dec", approvals=[_Approval("aed", "aed@neem", decision="declined")])
    by = {s.label: s for s in pv.build_voucher(req, org).signatures}
    check("declined step leaves the line blank", by["Approved by"].name == "")


def test_the_pv_number_is_allocated_once_and_never_changes() -> None:
    print("\nRe-exporting returns the SAME number — two numbers means two vouchers")
    org = _fresh("alpha", NEEM_TEMPLATE)
    when = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc)
    first = pv.build_voucher(_Req(id="r-pv"), org, when=when).pv_number
    second = pv.build_voucher(_Req(id="r-pv"), org, when=when).pv_number
    third = pv.pv_number_for(_Req(id="r-pv"), org, when=when)
    check("format matches the org's own", first == "NF/HQ/B24/CARE/SEP26/PV/01", first)
    check("re-export is identical", first == second == third, f"{first} {second} {third}")
    other = pv.build_voucher(_Req(id="r-pv2"), org, when=when).pv_number
    check("a different requisition gets the next number",
          other == "NF/HQ/B24/CARE/SEP26/PV/02", other)


def test_the_sequence_restarts_each_month() -> None:
    print("\nThe sequence is per month, as their format implies")
    org = _fresh("alpha", NEEM_TEMPLATE)
    sep = pv.build_voucher(_Req(id="s1"), org,
                           when=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)).pv_number
    octo = pv.build_voucher(_Req(id="s2"), org,
                            when=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)).pv_number
    check("September starts at 01", sep.endswith("SEP26/PV/01"), sep)
    check("October starts again at 01", octo.endswith("OCT26/PV/01"), octo)


def test_numbers_do_not_leak_between_organisations() -> None:
    print("\nTwo orgs number independently")
    a_org = _fresh("alpha", NEEM_TEMPLATE)
    d_org = _fresh("delta", {**NEEM_TEMPLATE, "pv_org_prefix": "XX"})
    when = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc)
    a = pv.build_voucher(_Req(id="x1"), a_org, when=when).pv_number
    d = pv.build_voucher(_Req(id="x1"), d_org, when=when).pv_number
    check("alpha numbered from its own sequence", a.endswith("PV/01"), a)
    check("delta numbered from its own sequence too", d.endswith("PV/01"), d)
    check("prefixes differ", a.split("/")[0] != d.split("/")[0], f"{a} / {d}")


def test_an_org_that_wants_to_number_by_hand_gets_a_blank() -> None:
    print("\nNo format configured means a blank field to write in, not an invented number")
    org = _fresh("epsilon", {**NEEM_TEMPLATE, "pv_number_format": ""})
    v = pv.build_voucher(_Req(id="r-blank"), org)
    check("blank", v.pv_number == "", v.pv_number)
    check("and no sequence was burned",
          not (store.get_store().list(org, "voucher_sequence") or []))


def test_chargeable_to_carries_project_and_donor() -> None:
    print("\nChargeable-to is the project and donor, which is what their filing keys on")
    org = _fresh("alpha", NEEM_TEMPLATE)
    v = pv.build_voucher(_Req(id="r-ch"), org)
    check("both present", v.chargeable_to == "B24 / CARE", v.chargeable_to)
    v2 = pv.build_voucher(_Req(id="r-ch2", grant_code=None), org)
    check("no trailing separator when the donor is absent",
          v2.chargeable_to == "B24", v2.chargeable_to)


# ─── the flag, through the real API ──────────────────────────────────────────
#
# Appended as an HTTP suite because "flag off ⇒ entirely invisible" is a claim
# about the ROUTE, not about the engine. Asserting it against build_voucher()
# would prove nothing: the engine is perfectly happy to render for an org that
# never bought the feature. Only the endpoint can refuse.


def test_two_vouchers_exported_together_never_share_a_number() -> None:
    print("\nTwo vouchers exported at the same moment get different PV numbers")
    import threading, time
    org = "race"
    pv.set_template(org, NEEM_TEMPLATE)
    st = store.get_store()
    real_get = st.get

    def slow_get(*a, **k):          # the network round-trip to Supabase
        r = real_get(*a, **k)
        time.sleep(0.05)
        return r

    st.get = slow_get
    try:
        out = {}
        reqs = [_Req(id="race-a", ref="REQ-0101"), _Req(id="race-b", ref="REQ-0102")]
        ts = [threading.Thread(target=lambda r=r: out.__setitem__(r.id, pv.pv_number_for(r, org)))
              for r in reqs]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        st.get = real_get
    check("two different requisitions, two different PV numbers",
          out.get("race-a") != out.get("race-b"), str(out))


def test_a_double_click_prints_the_number_that_is_stored() -> None:
    print("\nA double-click on Download prints one number, and it is the stored one")
    import threading, time
    org = "dblclick"
    pv.set_template(org, NEEM_TEMPLATE)
    st = store.get_store()
    real_get = st.get

    def slow_get(*a, **k):
        r = real_get(*a, **k)
        time.sleep(0.05)
        return r

    st.get = slow_get
    try:
        req = _Req(id="dbl-1", ref="REQ-0201")
        got = []
        ts = [threading.Thread(target=lambda: got.append(pv.pv_number_for(req, org))) for _ in range(3)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        st.get = real_get
    stored = pv.pv_number_for(req, org)
    check("every click got the same number", len(set(got)) == 1, str(got))
    check("and it is the number the system keeps", got and got[0] == stored, f"{got} vs {stored}")
    check("and only one number was used from the sequence",
          stored.endswith("/01"), stored)


def test_drafts_and_declined_payments_cannot_become_vouchers() -> None:
    print("\nOnly a submitted, still-live payment can become a voucher")
    for status, allowed in [("draft", False), ("declined", False), ("submitted", True),
                            ("in_review", True), ("on_hold", True), ("returned", True),
                            ("approved", True), ("paid", True)]:
        req = _Req(id=f"st-{status}")
        req.status = status
        reason = pv.export_refusal(req)
        check(f"{status:9s} ⇒ {'allowed' if allowed else 'refused'}",
              (reason is None) == allowed, str(reason))
    req = _Req(id="st-draft-2")
    req.status = "draft"
    check("the refusal says why, in words a finance officer understands",
          "draft" in (pv.export_refusal(req) or "").lower())


def test_the_flag_actually_hides_the_endpoint() -> None:
    print("\nFlag off means the endpoint is gone, not merely hidden in the nav")
    import os as _os
    import tempfile as _tf
    from pathlib import Path as _P

    tmp = _tf.mkdtemp(prefix="docex-vflag-")
    _os.environ["DOCEX_ORG"] = "vflag"
    store.set_store(store.JsonFileStore(tmp))

    import auth as A
    A._SECRET_FILE = _P(tmp) / ".s"
    A._secret_cache = None
    import org_config
    from fastapi.testclient import TestClient
    import api.main as m

    c = TestClient(m.app, raise_server_exceptions=False)
    PW = "correct-horse-battery"
    ORG = "vflag"
    A.create_user("admin@v", "Admin", PW, "finance", "admin", org_id=ORG)
    tok = c.post("/auth/login", json={"email": "admin@v", "password": PW}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    r = c.post("/requisitions", headers=H, data={
        "vendor_name": "Vendor Ltd", "amount": "100000", "category": "transport",
        "description": "Test", "documents": "memo,invoice", "submit": "true"})
    ref = r.json().get("ref") if r.status_code < 300 else None
    check("a requisition exists to export", bool(ref), f"{r.status_code} {r.text[:80]}")

    org_config.set_features(ORG, voucher_export=False)
    off = c.get(f"/requisitions/{ref}/voucher.pdf", headers=H)
    check("flag OFF ⇒ 404, indistinguishable from a route that does not exist",
          off.status_code == 404, str(off.status_code))
    check("and no PV number was burned",
          not (store.get_store().list(ORG, "voucher_sequence") or []))

    org_config.set_features(ORG, voucher_export=True)
    pv.set_template(ORG, NEEM_TEMPLATE)

    d = c.post("/requisitions", headers=H, data={
        "vendor_name": "Draft Vendor Ltd", "amount": "50000", "category": "transport",
        "description": "Not yet submitted", "documents": "memo,invoice", "submit": "false"})
    dref = d.json().get("ref") if d.status_code < 300 else None
    check("a draft exists", bool(dref), f"{d.status_code} {d.text[:80]}")
    dr = c.get(f"/requisitions/{dref}/voucher.pdf", headers=H)
    check("exporting a DRAFT is refused with 409", dr.status_code == 409, str(dr.status_code))
    check("and still no PV number was burned",
          not (store.get_store().list(ORG, "voucher_sequence") or []))

    on = c.get(f"/requisitions/{ref}/voucher.pdf", headers=H)
    check("flag ON ⇒ a PDF comes back", on.status_code == 200, str(on.status_code))
    check("it is really a PDF", on.content[:5] == b"%PDF-", str(on.content[:12]))
    check("filename is the PV number, which is what their filing keys on",
          "voucher-NF-HQ" in on.headers.get("content-disposition", ""),
          on.headers.get("content-disposition", ""))

    again = c.get(f"/requisitions/{ref}/voucher.pdf", headers=H)
    check("re-export keeps the same PV number",
          again.headers.get("content-disposition") == on.headers.get("content-disposition"))

    # The audit packet has its OWN flag. Enabling it here proves the two
    # exports are independent rather than entangled: the voucher worked above
    # while `requisition_export` was still off.
    org_config.set_features(ORG, requisition_export=True)
    other = c.get(f"/requisitions/{ref}/export.pdf", headers=H)
    check("the audit packet is a separate capability with its own flag",
          other.status_code == 200, str(other.status_code))


if __name__ == "__main__":
    print("WO-41 — payment voucher export")
    test_the_letterhead_is_never_hardcoded()
    test_an_unconfigured_org_still_gets_a_usable_voucher()
    test_two_orgs_get_visibly_different_vouchers()
    test_an_unmapped_category_leaves_the_code_blank()
    test_the_total_is_the_sum_of_what_is_printed()
    test_a_batch_becomes_one_voucher_with_payees_as_lines()
    test_signatures_reflect_the_approval_trail_not_the_status()
    test_a_declined_step_never_appears_as_a_signature()
    test_the_pv_number_is_allocated_once_and_never_changes()
    test_the_sequence_restarts_each_month()
    test_numbers_do_not_leak_between_organisations()
    test_an_org_that_wants_to_number_by_hand_gets_a_blank()
    test_chargeable_to_carries_project_and_donor()
    test_two_vouchers_exported_together_never_share_a_number()
    test_a_double_click_prints_the_number_that_is_stored()
    test_drafts_and_declined_payments_cannot_become_vouchers()
    test_the_flag_actually_hides_the_endpoint()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)


