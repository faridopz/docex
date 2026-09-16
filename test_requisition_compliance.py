"""
End-to-end HTTP test: WO-21, linking compliance.py's rulebook engine to
requisitions.

Architecturally blocked until WO-22 (real file attachments) existed — a
compliance check needs real document text to evaluate, and requisitions
previously only carried ticked document LABELS, not files. Now that
attachments exist, this wires an org's saved compliance rulebook
(compliance.py / api/compliance_routes.py's "rulebooks" store collection)
to the requisition engine: any signed-in user who can see a requisition
can run its real attachments against the rulebook and see AI-assisted
verdicts alongside (never merged into) the engine's own deterministic
PolicyCheck list — including the submitter themselves, before an
approver ever opens it.

The Anthropic client is mocked (same technique as test_compliance_perf.py)
so this suite runs with no API key and no network call. Covers: the flag
gates the whole capability; no rulebook configured on the workflow refuses
with a clear message; a configured-but-deleted rulebook 404s; no
attachments refuses; a valid run round-trips the verdict, summary, and
per-rule findings onto the requisition and into the audit log; a plain
viewer can trigger the check same as anyone else (no role gate — see
WO-21's follow-up note below); the requisition's own deterministic checks
are untouched by any of this.

NOT role-gated (changed from the original WO-21 cut, at Farid's explicit
request): running this was initially restricted to reviewer/approver/admin
because it costs a real Claude API call, but that's a poor proxy for who
should be allowed to spend it — a submitter wants to check their own
request before it even reaches an approver. Cost control now lives at the
org level, via the requisition_compliance_check flag itself.

Run: python test_requisition_compliance.py
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_compliance_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

import attachments  # noqa: E402
_files = Path(tempfile.mkdtemp(prefix="docex_compliance_files_"))
attachments.set_backend(attachments.LocalDiskAttachmentBackend(_files))

import compliance  # noqa: E402
import org_config  # noqa: E402
from models import PolicyRule, PolicyRulebook  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import api.main as m  # noqa: E402

client = TestClient(m.app)
_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


def hdr(email, password):
    tok = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ─── mock Anthropic client — identical technique to test_compliance_perf.py ─

class _FakeParse:
    def __init__(self, holder):
        self.holder = holder

    def parse(self, **kwargs):
        self.holder["calls"] += 1
        self.holder["last_kwargs"] = kwargs
        payload = self.holder["response"]
        if isinstance(payload, Exception):
            raise payload
        return payload


class _FakeClient:
    def __init__(self, holder):
        self.messages = _FakeParse(holder)


def install_fake(response):
    holder = {"calls": 0, "response": response}
    compliance._client = _FakeClient(holder)
    compliance._get_client = lambda: compliance._client  # type: ignore
    return holder


def fake_response(parsed):
    usage = types.SimpleNamespace(
        input_tokens=500, output_tokens=100,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    return types.SimpleNamespace(parsed_output=parsed, usage=usage, stop_reason="end_turn")


def lean(verdict, rule_id, rule_verdict, reason):
    return compliance._LeanCheckResponse(
        overall_verdict=verdict, overall_summary=f"{verdict.capitalize()}.",
        results=[compliance._LlmRuleResult(
            rule_id=rule_id, verdict=rule_verdict, short_reason=reason,
            evidence_ref="Voucher total ₦60,000",
        )],
        receipt_results=[],
    )


# ─── bootstrap ──────────────────────────────────────────────────────────────

client.post("/auth/register", json={
    "email": "admin@neem.org", "name": "Admin", "password": "admin-passphrase",
    "department": "management", "role": "admin"})
ah = hdr("admin@neem.org", "admin-passphrase")

client.post("/auth/register", headers=ah, json={
    "email": "program@neem.org", "name": "Program", "password": "program-passphrase",
    "department": "program", "role": "reviewer"})
ph = hdr("program@neem.org", "program-passphrase")

client.post("/auth/register", headers=ah, json={
    "email": "viewer@neem.org", "name": "Viewer", "password": "viewer-passphrase",
    "department": "compliance", "role": "viewer"})
vh = hdr("viewer@neem.org", "viewer-passphrase")

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
})
check("workflow saved", r.status_code == 200)
check("workflow starts with no rulebook configured", r.json()["rulebook_id"] is None)

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Sahad Stores", "amount": "60000", "category": "supplies",
})
check("requisition raised", r.status_code == 200)
req_id, req_ref = r.json()["id"], r.json()["ref"]
check("starts with no compliance result", r.json()["compliance"] is None)
baseline_checks = r.json()["checks"]

# ─── flag off: refused ──────────────────────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("flag off: refused", r.status_code == 400)
check("refusal names the feature flag", "requisition_compliance_check" in r.json()["detail"])

org_config.set_features("default", requisition_compliance_check=True)

# ─── flag on, no rulebook configured: refused with a clear message ─────────

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("no rulebook configured: refused", r.status_code == 400)
check("refusal mentions the rulebook", "rulebook" in r.json()["detail"].lower())

# ─── flag on, rulebook configured but nonexistent: 404s ────────────────────

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
    "rulebook_id": "rb-does-not-exist",
})
check("workflow saved with a rulebook id", r.status_code == 200 and r.json()["rulebook_id"] == "rb-does-not-exist")

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("nonexistent rulebook: 404s", r.status_code == 404)

# ─── a real rulebook, saved the way compliance_routes.py would save one ────

rulebook = PolicyRulebook(
    id="rb-test-001", name="NEEM Procurement Policy",
    source_documents=["policy.pdf"],
    rules=[PolicyRule(
        id="rule-vendor-quote", description="Purchases over ₦50,000 need 3 vendor quotes.",
        category="documentation", source_quote="All purchases over N50,000 require 3 quotes.",
        evaluation_type="llm", active=True,
    )],
)
store.get_store().put("default", "rulebooks", rulebook.id, json.loads(rulebook.model_dump_json()))

r = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
    "rulebook_id": rulebook.id,
})
check("workflow points at the real rulebook", r.status_code == 200)

# ─── flag on, rulebook configured, but no attachments: refused ─────────────

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("no attachments: refused", r.status_code == 400)
check("refusal mentions attaching a file", "attach" in r.json()["detail"].lower())

# ─── attach a file, then run the check ─────────────────────────────────────

r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                 files={"file": ("quote.txt", b"Vendor quote #1 from Sahad Stores.", "text/plain")})
check("this test needs requisition_attachments too", r.status_code in (200, 400))
if r.status_code == 400:
    # requisition_attachments is a SEPARATE flag from requisition_compliance_check
    # — enable it too, exactly as an org actually configuring both would.
    org_config.set_features("default", requisition_attachments=True)
    r = client.post(f"/requisitions/{req_id}/attachments", headers=ph,
                     files={"file": ("quote.txt", b"Vendor quote #1 from Sahad Stores.", "text/plain")})
check("attachment uploaded", r.status_code == 200)

install_fake(fake_response(lean("flagged", "rule-vendor-quote", "flag", "Only 1 of 3 quotes attached")))

# ─── a plain viewer — no elevated role — can trigger the check ─────────────
# Not role-gated: visibility of the requisition is the only bar, the same
# rule as attaching a file or posting a comment.

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=vh)
check("a plain viewer can run the check — no role gate", r.status_code == 200)
body = r.json()
comp = body["compliance"]
check("compliance summary present", comp is not None)
check("rulebook id recorded", comp["rulebook_id"] == "rb-test-001")
check("rulebook name recorded", comp["rulebook_name"] == "NEEM Procurement Policy")
check("overall verdict flagged", comp["overall_verdict"] == "flagged")
check("checked_by recorded as the viewer who ran it", comp["checked_by"] == "viewer@neem.org")
check("checked_at recorded", bool(comp["checked_at"]))
check("document_count reflects the one attachment", comp["document_count"] == 1)
check("one finding", len(comp["results"]) == 1)
finding = comp["results"][0]
check("finding rule_id", finding["rule_id"] == "rule-vendor-quote")
check("finding verdict", finding["verdict"] == "flag")
check("finding reasoning carried through", "3 quotes" in finding["reasoning"])

# ─── the requisition's own deterministic checks are untouched ─────────────

check("deterministic PolicyCheck list unchanged by the compliance run",
      [c["code"] for c in body["checks"]] == [c["code"] for c in baseline_checks])

# ─── the audit log records the run ──────────────────────────────────────────

check("audit log has a compliance_checked entry",
      any(e["event"] == "compliance_checked" for e in body["audit_log"]))

# ─── a different user (the submitter) can also re-run it — replaces the
# snapshot, doesn't accumulate ──────────────────────────────────────────────

install_fake(fake_response(lean("approved", "rule-vendor-quote", "pass", "All 3 quotes now attached")))
r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("second run, by a different user, succeeds", r.status_code == 200)
body2 = r.json()
check("verdict updated to approved", body2["compliance"]["overall_verdict"] == "approved")
check("checked_by updated to whoever ran it this time", body2["compliance"]["checked_by"] == "program@neem.org")
check("still exactly one finding (replaced, not appended)", len(body2["compliance"]["results"]) == 1)
check("two compliance_checked audit entries now (history preserved)",
      sum(1 for e in body2["audit_log"] if e["event"] == "compliance_checked") == 2)

# ─── WO-30: an explicit rulebook_id on the request overrides the workflow's
# configured default for that one run — not every requisition should be
# judged against the same policy document, so whoever is running the check
# picks it, rather than always using whatever the workflow was set up with
# once, org-wide ──────────────────────────────────────────────────────────

second_rulebook = PolicyRulebook(
    id="rb-test-002", name="NEEM Travel Policy",
    source_documents=["travel_policy.pdf"],
    rules=[PolicyRule(
        id="rule-travel-approval", description="Travel over 3 days needs Director sign-off.",
        category="documentation", source_quote="Travel exceeding 3 days requires the Director's approval.",
        evaluation_type="llm", active=True,
    )],
)
store.get_store().put("default", "rulebooks", second_rulebook.id, json.loads(second_rulebook.model_dump_json()))

install_fake(fake_response(lean("approved", "rule-travel-approval", "pass", "Director sign-off attached")))
r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph,
                 data={"rulebook_id": "rb-test-002"})
check("explicit rulebook override succeeds", r.status_code == 200)
override_body = r.json()
check("checked against the EXPLICIT rulebook, not the workflow default",
      override_body["compliance"]["rulebook_id"] == "rb-test-002")
check("explicit rulebook's name recorded", override_body["compliance"]["rulebook_name"] == "NEEM Travel Policy")

wf_after_override = client.get("/requisitions/workflow", headers=ah).json()
check("the workflow's own default rulebook_id is untouched by a one-off override",
      wf_after_override["rulebook_id"] == "rb-test-001")

r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph,
                 data={"rulebook_id": "rb-does-not-exist-either"})
check("an explicit but nonexistent rulebook_id still 404s", r.status_code == 404)

# No override given at all still falls back to the workflow's own default,
# exactly as before this feature existed.
install_fake(fake_response(lean("approved", "rule-vendor-quote", "pass", "Back to the default rulebook")))
r = client.post(f"/requisitions/{req_id}/compliance-check", headers=ph)
check("no override given: falls back to the workflow's configured default", r.status_code == 200)
check("fallback checked against the workflow default rulebook",
      r.json()["compliance"]["rulebook_id"] == "rb-test-001")

# Neither an explicit override nor a workflow default: refused with a
# message that makes clear a choice is needed, not just missing config.
r2 = client.post("/requisitions", headers=ph, data={
    "vendor_name": "No Rulebook At All Ltd", "amount": "10000", "category": "supplies",
})
no_rb_req_id = r2.json()["id"]
client.post(f"/requisitions/{no_rb_req_id}/attachments", headers=ph,
            files={"file": ("note.txt", b"Some note.", "text/plain")})
r3 = client.put("/requisitions/workflow", headers=ah, json={
    "steps": [{"key": "finance", "label": "Finance", "department": "finance"}],
    "rulebook_id": None,
})
check("workflow can be cleared back to no default rulebook", r3.json()["rulebook_id"] is None)
r4 = client.post(f"/requisitions/{no_rb_req_id}/compliance-check", headers=ph)
check("neither an override nor a default: refused", r4.status_code == 400)
check("refusal explains a rulebook must be chosen",
      "chosen" in r4.json()["detail"].lower() or "rulebook" in r4.json()["detail"].lower())

# ─── WO-31: the exact sequence /requisitions/new now performs when someone
# raises a request, attaches the documents and picks the policy on the one
# form — create, attach, then check against the CHOSEN rulebook. Worth
# testing as a sequence and not just as three endpoints: the frontend now
# depends on each step returning the updated requisition so the next step
# has something to act on, and on the check working with NO workflow
# default configured (cleared above) because the policy was chosen at raise
# time instead ─────────────────────────────────────────────────────────────

r = client.post("/requisitions", headers=ph, data={
    "vendor_name": "Raise-Flow Ltd", "amount": "250000", "category": "supplies",
    "payment_type": "advance", "vendor_bank_name": "Zenith Bank",
})
check("raise-flow: requisition created", r.status_code == 200)
flow_id, flow_ref = r.json()["id"], r.json()["ref"]
check("raise-flow: no compliance verdict before the check runs", r.json()["compliance"] is None)

r = client.post(f"/requisitions/{flow_id}/attachments", headers=ph,
                 files={"file": ("quote-a.txt", b"Quote A from Raise-Flow Ltd, N250,000.", "text/plain")})
check("raise-flow: first document attached", r.status_code == 200)
r = client.post(f"/requisitions/{flow_id}/attachments", headers=ph,
                 files={"file": ("quote-b.txt", b"Quote B from another vendor, N265,000.", "text/plain")})
check("raise-flow: second document attached", r.status_code == 200)
check("raise-flow: attach returns the updated requisition, so the next step can use it",
      len(r.json()["attachments"]) == 2)

install_fake(fake_response(lean("flagged", "rule-vendor-quote", "flag", "Only 2 of 3 quotes attached")))
r = client.post(f"/requisitions/{flow_id}/compliance-check", headers=ph,
                 data={"rulebook_id": "rb-test-001"})
check("raise-flow: check runs against the policy chosen at raise time, with no workflow default set",
      r.status_code == 200)
flow_body = r.json()
check("raise-flow: verdict lands on the requisition",
      flow_body["compliance"]["overall_verdict"] == "flagged")
check("raise-flow: verdict names the chosen policy",
      flow_body["compliance"]["rulebook_id"] == "rb-test-001")
check("raise-flow: both attached documents were read",
      flow_body["compliance"]["document_count"] == 2)
check("raise-flow: the deterministic checks are still there, unmerged",
      len(flow_body["checks"]) > 0)
check("raise-flow: WO-29 detail survives the whole sequence",
      flow_body["payment_type"] == "advance" and flow_body["vendor_bank_name"] == "Zenith Bank")

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll requisition-compliance checks passed.")
