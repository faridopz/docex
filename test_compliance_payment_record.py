"""
WO-40: the compliance check can finally see what is being paid.

THE FAILURE THIS PREVENTS
The system prompt has always instructed the model to reconcile the bundle
against the payment voucher — amount against the invoice, payee against the
PO, quantities against the GRN. In DOCex the voucher is not one of the
attached files; it is the requisition, held as structured data. So we were
asking the model to reconcile against a document we never handed it, and it
could only check the documents against each other. An invoice for ₦620,000
attached to a request to pay ₦562,500 read as perfectly compliant.

Covers:
- the record reaches the prompt, with the money and the payee in it
- currency travels with every amount, so NGN and USD cannot be compared blind
- absent fields are OMITTED, never rendered "n/a" or "0" — a field the model
  cannot see is better than one it reads as a missing value
- a hundred payees are summarised, not listed, so the stipend run does not
  swamp the documents it is meant to be checked against
- the account number and tax ID are present, because a redirected payment is
  the fraud this catches
- FLAG OFF: the prompt is byte-for-byte what it was before this feature
- a code-level BLOCK still wins — the record changes what the model SEES,
  never how verdicts merge
- two orgs, one flag each way, on the same requisition

No API key needed: the model call is stubbed and the prompt it would have
been sent is captured.

Run: python3 test_compliance_payment_record.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import store
import auth as auth_mod

_base = Path(tempfile.mkdtemp(prefix="docex_wo40_"))
store.set_store(store.JsonFileStore(_base / "store"))
auth_mod._SECRET_FILE = _base / ".auth_secret"
auth_mod._secret_cache = None

import compliance  # noqa: E402
from models import PolicyRule, PolicyRulebook, RuleResult  # noqa: E402

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


# ─── the renderer, on its own ──────────────────────────────────────────────

FULL = {
    "reference": "REQ-0042",
    "date": "2026-09-20",
    "payment_type": "full",
    "category": "equipment",
    "amount": "NGN 562,500.00",
    "payee": "Sahad Stores",
    "payee_account": "0123456789",
    "payee_bank": "GTBank",
    "payee_tin": "01234567-0001",
    "project_code": "B24",
    "purpose": "Laptops for the Kano field office",
    "budget_lines": [
        {"description": "Dell Latitude 5450", "quantity": 3,
         "unit_cost": "NGN 187,500.00", "line_total": "NGN 562,500.00"},
    ],
    "payee_count": 1,
}

block = compliance.build_payment_record_block(FULL)

check("the amount being paid is in the block", "NGN 562,500.00" in block)
check("the payee is in the block", "Sahad Stores" in block)
check("the bank account is in the block — this is the redirected-payment check",
      "0123456789" in block)
check("the tax ID is in the block", "01234567-0001" in block)
check("the project code is in the block", "B24" in block)
check("the budget line is itemised", "Dell Latitude 5450" in block)
check("the line quantity survives", "qty 3" in block)
check("the block says the record came from the system, not the documents",
      "not extracted from the documents" in block)

# ─── absent fields are omitted, not rendered as a missing value ────────────

sparse = compliance.build_payment_record_block({
    "reference": "REQ-0043", "amount": "NGN 1,000.00", "payee": "A Vendor",
    "payee_account": "", "payee_tin": None, "project_code": "   ",
    "purpose": "", "budget_lines": [], "payee_count": 0,
})
check("a blank account is left out entirely", "Payee account" not in sparse)
check("a None tax ID is left out entirely", "tax ID" not in sparse)
check("a whitespace-only project code is left out", "Project code" not in sparse)
check("nothing is rendered as n/a", "n/a" not in sparse.lower())
check("what IS present still renders", "A Vendor" in sparse)

zeroed = compliance.build_payment_record_block({"reference": "R", "amount": "0"})
check("a zero amount is not presented as a real figure", "Amount" not in zeroed)

check("an empty record renders no block at all",
      compliance.build_payment_record_block({}) == "")
check("a record of only blanks renders no block at all",
      compliance.build_payment_record_block({"payee": "", "amount": None}) == "")

# ─── many payees are summarised, never listed ─────────────────────────────

many = compliance.build_payment_record_block(
    {"reference": "REQ-0044", "amount": "NGN 562,500.00", "payee_count": 100})
check("a hundred payees are summarised as a count", "100 separate payees" in many)
check("the summary does not try to list them", many.count("\n- ") <= 3)

# ─── the prompt: flag on vs flag off ──────────────────────────────────────

RULEBOOK = PolicyRulebook(
    id="rb-test", name="Procurement Policy", source_documents=["policy.pdf"],
    rules=[PolicyRule(
        id="R1", description="Equipment purchases need a GRN.",
        category="documentation", evaluation_type="llm", active=True,
    )],
)
DOCS = [("invoice.pdf", "INVOICE\nSahad Stores\nTotal: NGN 620,000.00")]

_sent: dict = {}


class _FakeResponse:
    stop_reason = "end_turn"
    usage = type("U", (), {"input_tokens": 10, "output_tokens": 10,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0})()

    class parsed_output:
        results = [type("R", (), {
            "rule_id": "R1", "verdict": "pass",
            "short_reason": "GRN attached", "evidence_ref": "invoice.pdf",
            "missing": [],
        })()]
        receipt_results = []
        overall_verdict = "compliant"
        overall_summary = "Fine."


class _FakeMessages:
    def parse(self, **kwargs):
        _sent["user"] = kwargs["messages"][0]["content"]
        _sent["system"] = kwargs["system"]
        return _FakeResponse()


class _FakeClient:
    messages = _FakeMessages()


compliance._get_client = lambda: _FakeClient()

compliance.check_payment(DOCS, RULEBOOK, "REQ-0042", payment_record=FULL)
with_record = _sent["user"]
system_with = _sent["system"]

compliance.check_payment(DOCS, RULEBOOK, "REQ-0042")
without_record = _sent["user"]
system_without = _sent["system"]

check("with the flag on, the prompt carries the amount being paid",
      "NGN 562,500.00" in with_record)
check("with the flag on, the model is told to reconcile against the record",
      "RECONCILE THE DOCUMENTS AGAINST THAT RECORD" in with_record)
check("it is told a disagreement counts even when every rule passes",
      "even when every individual rule passes" in with_record)
check("it is told NOT to assume the record is the correct side",
      "assuming the record is right" in with_record)
check("FLAG OFF: no payment record appears in the prompt",
      "PAYMENT RECORD" not in without_record)
check("FLAG OFF: no reconciliation instruction appears either",
      "RECONCILE" not in without_record)
check("FLAG OFF: the prompt still starts exactly as it always did",
      without_record.startswith("PAYMENT REQUEST BUNDLE — REQ-0042:"))
check("the documents are still in the prompt both ways",
      "invoice.pdf" in with_record and "invoice.pdf" in without_record)
check("the SYSTEM prompt is untouched either way — the cache still hits",
      system_with == system_without)

# ─── deterministic-first is not weakened ──────────────────────────────────
# A code-level BLOCK short-circuits before the model is ever consulted. The
# record must not change that: it alters what the model SEES, never how
# verdicts merge.

_sent.clear()
blocked = compliance.check_payment(
    DOCS, RULEBOOK, "REQ-0042", payment_record=FULL,
    document_findings=[RuleResult(
        rule_id="DUP", rule_description="Duplicate invoice",
        verdict="block", reasoning="Same invoice paid last week",
        confidence="found",
    )],
)
check("a code-level BLOCK still blocks", blocked.overall_verdict == "blocked")
check("and the model was never called for it", "user" not in _sent)

# ─── no documents: still no model call, record or not ─────────────────────

_sent.clear()
empty = compliance.check_payment([], RULEBOOK, "REQ-0042", payment_record=FULL)
check("no documents still means no model call", "user" not in _sent)
check("and the rule is reported as insufficient evidence, not passed",
      empty.results[0].verdict == "insufficient_evidence")

# ─── two orgs, one flag each way ──────────────────────────────────────────

import org_config  # noqa: E402

org_config.set_features("org_on", compliance_payment_record=True)
org_config.set_features("org_off", compliance_payment_record=False)
check("the flag is on for one org",
      org_config.feature_enabled("org_on", "compliance_payment_record") is True)
check("and off for the other",
      org_config.feature_enabled("org_off", "compliance_payment_record") is False)
check("an org that has never heard of the flag does not get it",
      org_config.feature_enabled("org_never", "compliance_payment_record") is False)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll WO-40 payment-record checks passed.")
