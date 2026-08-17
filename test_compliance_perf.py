"""Tests for the perf changes: lean LLM schema + transform (Change 2) and batch
deterministic AP controls (Change 3). The Anthropic client is mocked so these
run with no API key. Run: python test_compliance_perf.py"""
from __future__ import annotations

import types

import compliance
from models import PolicyRule, PolicyRulebook, RuleResult

_fail = 0


def check(name, cond, extra=""):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}{(' — ' + extra) if extra and not cond else ''}")
    if not cond:
        _fail += 1


# ── mock Anthropic client ────────────────────────────────────────────────────
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
    holder = {"calls": 0, "response": response, "last_kwargs": None}
    compliance._client = _FakeClient(holder)  # bypass _get_client's lazy build
    compliance._get_client = lambda: compliance._client  # type: ignore
    return holder


def fake_response(parsed, in_tok=1000, out_tok=200):
    usage = types.SimpleNamespace(
        input_tokens=in_tok, output_tokens=out_tok,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    return types.SimpleNamespace(parsed_output=parsed, usage=usage, stop_reason="end_turn")


def lean(results=None, receipt_results=None, verdict="approved", summary="ok"):
    return compliance._LeanCheckResponse(
        overall_verdict=verdict, overall_summary=summary,
        results=results or [], receipt_results=receipt_results or [],
    )


def rb(rules):
    return PolicyRulebook(id="rb-test", name="Test Rulebook", source_documents=["policy.pdf"], rules=rules)


def payment_rule(rid, desc, category="documentation", quote="POLICY TEXT"):
    return PolicyRule(id=rid, description=desc, category=category, source_quote=quote,
                      evaluation_type="llm", active=True)


DOCS = [("invoice.pdf", "Invoice total NGN 100,000")]
RECEIPT_DOCS = [("voucher.pdf", "voucher"), ("r1.jpg", "x"), ("r2.jpg", "y"), ("r3.jpg", "z")]


# ── 1. normal single payment: rehydration + evidence ──
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="pass", short_reason="all present",
                              evidence_ref="Invoice total NGN 100,000"),
])))
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "Invoice must be attached")]))
r = res.results[0]
check("1a normal: model called once", holder["calls"] == 1)
check("1b rule_description rehydrated from rulebook", r.rule_description == "Invoice must be attached")
check("1c policy_citation rehydrated from source_quote", r.policy_citation == "POLICY TEXT")
check("1d evidence carried into payment_evidence", r.payment_evidence == "Invoice total NGN 100,000")
check("1e verdict + confidence", r.verdict == "pass" and r.confidence == "found")


# ── 2/3/4. receipt fan-out expands to one RuleResult per (rule × receipt) ──
def receipt_case(n):
    receipts = [compliance._LlmReceiptVerdict(document_id=f"r{i}.jpg", verdict="pass",
                                              evidence_ref=f"r{i}: NGN {i}00") for i in range(1, n + 1)]
    holder = install_fake(fake_response(lean(receipt_results=[
        compliance._LlmReceiptRuleResult(rule_id="RC", receipts=receipts)])))
    docs = [("voucher.pdf", "v")] + [(f"r{i}.jpg", "x") for i in range(1, n + 1)]
    res = compliance.check_payment(docs, rb([payment_rule("RC", "Each receipt legible", category="receipts")]))
    rc_rows = [x for x in res.results if x.rule_id == "RC"]
    return holder, rc_rows


for n in (3, 20, 50):
    holder, rows = receipt_case(n)
    check(f"receipt fan-out n={n}: one model object, {n} public rows",
          holder["calls"] == 1 and len(rows) == n, f"got {len(rows)} rows")
    check(f"receipt n={n}: applied_to_document set per receipt",
          all(x.applied_to_document == f"r{i+1}.jpg" for i, x in enumerate(rows)))


# ── 5. deterministic BLOCK → model NOT called, verdict blocked ──
block_finding = RuleResult(rule_id="det-three-way-match", rule_description="3-way",
                           verdict="block", reasoning="mismatch", confidence="found")
holder = install_fake(fake_response(lean(verdict="approved")))  # model WOULD say approved
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "x")]), document_findings=[block_finding])
check("5a code BLOCK short-circuits: model NOT called", holder["calls"] == 0)
check("5b code BLOCK wins over would-be-approved model", res.overall_verdict == "blocked")


# ── 6. mixed deterministic doc-finding (pass) + llm rule ──
pass_finding = RuleResult(rule_id="det-three-way-match", rule_description="3-way",
                          verdict="pass", reasoning="ok", confidence="found")
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="pass", short_reason="ok")], verdict="approved")))
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "x")]), document_findings=[pass_finding])
check("6 mixed: both code finding and llm result present",
      any(x.rule_id == "det-three-way-match" for x in res.results)
      and any(x.rule_id == "R1" for x in res.results))


# ── 7. missing evidence → insufficient + missing_evidence populated ──
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="insufficient_evidence",
                              short_reason="no signature", missing=["Director's signature"])],
    verdict="flagged")))
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "Signature required")]))
r = res.results[0]
check("7 insufficient carries missing_evidence + not_found confidence",
      r.verdict == "insufficient_evidence" and r.missing_evidence == ["Director's signature"]
      and r.confidence == "not_found")


# ── 8. multiple receipt verdicts (mixed pass/flag/block) ──
holder = install_fake(fake_response(lean(receipt_results=[
    compliance._LlmReceiptRuleResult(rule_id="RC", receipts=[
        compliance._LlmReceiptVerdict(document_id="r1.jpg", verdict="pass"),
        compliance._LlmReceiptVerdict(document_id="r2.jpg", verdict="flag", short_reason="faint"),
        compliance._LlmReceiptVerdict(document_id="r3.jpg", verdict="block", evidence_ref="altered total"),
    ])], verdict="blocked")))
res = compliance.check_payment(RECEIPT_DOCS, rb([payment_rule("RC", "legible", category="receipts")]))
verds = {x.applied_to_document: x.verdict for x in res.results if x.rule_id == "RC"}
check("8 mixed receipt verdicts preserved", verds == {"r1.jpg": "pass", "r2.jpg": "flag", "r3.jpg": "block"})
check("8b overall verdict blocked from a receipt block", res.overall_verdict == "blocked")


# ── 9. malformed model output ──
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="MAYBE?!", short_reason="weird")])))
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "x")]))
check("9a unknown verdict normalised to insufficient_evidence",
      res.results[0].verdict == "insufficient_evidence")
# parsed_output None → check_payment raises; check_payment_safe isolates it.
holder = install_fake(fake_response(None))
safe = compliance.check_payment_safe(DOCS, rb([payment_rule("R1", "x")]))
check("9b parse failure isolated by _safe (flagged + error set)",
      safe.overall_verdict == "flagged" and bool(safe.error))


# ── 10. API compatibility: every public RuleResult field still present ──
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="pass", short_reason="ok", evidence_ref="x")])))
res = compliance.check_payment(DOCS, rb([payment_rule("R1", "x")]))
d = res.results[0].model_dump()
required = {"rule_id", "rule_description", "verdict", "reasoning", "policy_citation",
            "payment_evidence", "missing_evidence", "applied_to_document", "confidence"}
check("10 public RuleResult keeps all API fields", required.issubset(d.keys()))


# ── metrics hook populated ──
holder = install_fake(fake_response(lean(results=[
    compliance._LlmRuleResult(rule_id="R1", verdict="pass")]), in_tok=1234, out_tok=88))
m: dict = {}
compliance.check_payment(DOCS, rb([payment_rule("R1", "x")]), metrics=m)
check("metrics: tokens + calls captured",
      m.get("llm_calls") == 1 and m.get("input_tokens") == 1234 and m.get("output_tokens") == 88)


print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All compliance-perf checks passed.")
