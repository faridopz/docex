"""Change 3 tests: batch runs the SAME deterministic AP controls as single,
detects duplicates within a batch, and isolates a failed payment. Anthropic is
mocked. Run: python test_batch_perf.py"""
from __future__ import annotations

import types

import compliance
from models import PolicyRule, PolicyRulebook

_fail = 0


def check(name, cond, extra=""):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}{(' — ' + extra) if extra and not cond else ''}")
    if not cond:
        _fail += 1


# Mock client that always returns an "approved" lean response and counts calls.
class _FakeParse:
    def __init__(self, holder): self.holder = holder
    def parse(self, **kw):
        self.holder["calls"] += 1
        return types.SimpleNamespace(
            parsed_output=compliance._LeanCheckResponse(
                overall_verdict="approved", overall_summary="ok",
                results=[compliance._LlmRuleResult(rule_id="R1", verdict="pass")]),
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1,
                                        cache_read_input_tokens=0, cache_creation_input_tokens=0),
            stop_reason="end_turn")


class _FakeClient:
    def __init__(self, holder): self.messages = _FakeParse(holder)


def install_fake():
    holder = {"calls": 0}
    compliance._client = _FakeClient(holder)
    compliance._get_client = lambda: compliance._client  # type: ignore
    return holder


def rb():
    return PolicyRulebook(
        id="rb", name="RB", source_documents=["p.pdf"],
        rules=[PolicyRule(id="R1", description="an llm rule", category="documentation",
                          source_quote="X", evaluation_type="llm", active=True)])


INV1 = ("invoice.pdf", "INVOICE\nInvoice No: INV-001\nPurchase Order: PO-9\nTotal Amount: NGN 100,000")
PO_BAD = ("po.pdf", "PURCHASE ORDER\nPurchase Order No: PO-9\nTotal: NGN 200,000")
INV2 = ("invoice2.pdf", "INVOICE\nInvoice No: INV-002\nTotal Amount: NGN 50,000")
INV1_DUP = ("invoice3.pdf", "INVOICE\nInvoice No: INV-001\nTotal Amount: NGN 100,000")


# ── 1. Three-way-match block runs IN BATCH and short-circuits the LLM ──
holder = install_fake()
batch = compliance.check_payment_batch([
    {"label": "P1 mismatch", "documents": [INV1, PO_BAD]},
    {"label": "P2 clean", "documents": [INV2]},
], rb())
p1 = next(c for c in batch.checks if c.payment_label == "P1 mismatch")
p2 = next(c for c in batch.checks if c.payment_label == "P2 clean")
check("1a batch runs three-way match (P1 blocked)", p1.overall_verdict == "blocked")
check("1b block came from deterministic code", any(r.rule_id == "det-three-way-match" and r.verdict == "block" for r in p1.results))
check("1c blocked payment skipped the LLM (only P2 called it)", holder["calls"] == 1, f"calls={holder['calls']}")
check("1d clean payment still processed", p2.overall_verdict == "approved")


# ── 2. In-batch duplicate detection (INV-001 appears in P1 and P3) ──
holder = install_fake()
batch = compliance.check_payment_batch([
    {"label": "P1", "documents": [INV1]},        # INV-001 (has PO ref but no PO doc → no TWM; dup pass)
    {"label": "P2", "documents": [INV2]},        # INV-002
    {"label": "P3", "documents": [INV1_DUP]},    # INV-001 again → duplicate BLOCK
], rb())
p3 = next(c for c in batch.checks if c.payment_label == "P3")
check("2a in-batch duplicate blocks the repeat", p3.overall_verdict == "blocked")
check("2b duplicate block is deterministic (no LLM for P3)",
      any(r.rule_id == "det-duplicate-invoice" and r.verdict == "block" for r in p3.results))
# P1 and P2 clean → 2 LLM calls; P3 short-circuits.
check("2c only the two non-duplicate payments called the LLM", holder["calls"] == 2, f"calls={holder['calls']}")


# ── 3. Batch failure isolation via the endpoint (missing file) ──
import tempfile, os
from pathlib import Path
from fastapi.testclient import TestClient
import api.compliance_routes as cr
import api.main as m

# Persist a rulebook to the real store, then clean it up.
rulebook = rb()
# Redirect check persistence to a temp dir so the test never pollutes checks/.
cr._CHECK_DIR = Path(tempfile.mkdtemp(prefix="docex_checks_"))
rb_path = cr._rulebook_path(rulebook.id)
rb_path.write_text(rulebook.model_dump_json())
try:
    holder = install_fake()
    client = TestClient(m.app)
    files = [
        ("documents", ("a.txt", b"INVOICE\nInvoice No: INV-900\nTotal Amount: NGN 10,000", "text/plain")),
    ]
    # P1 references the uploaded file; P2 references a filename that was NOT uploaded.
    payments = '[{"label":"P1 ok","filenames":["a.txt"]},{"label":"P2 missing","filenames":["ghost.txt"]}]'
    r = client.post("/compliance/check/batch",
                    files=files, data={"rulebook_id": rulebook.id, "payments": payments})
    check("3a endpoint 200 (no whole-batch 422)", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        body = r.json()
        checks = {c["payment_label"]: c for c in body["checks"]}
        check("3b both payments present in order", list(checks.keys()) == ["P1 ok", "P2 missing"])
        check("3c missing-file payment isolated as error", bool(checks["P2 missing"].get("error")))
        check("3d valid payment still processed", checks["P1 ok"].get("error") in (None, ""))
finally:
    try: rb_path.unlink()
    except Exception: pass
    # clean any checks persisted during the endpoint test
    for c_id in []:
        pass


print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All batch-perf checks passed.")
