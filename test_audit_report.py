"""
WO-38: the period audit report.

The question this suite exists to answer with evidence rather than assertion:
does the report stay cheap as the organisation grows?

It does, because the model never sees the population. It is shown the
already-computed summary, so the prompt is the same size for ten payments and
for four hundred. The first test MEASURES that rather than claiming it.

Also covers: every figure is computed in Python; a hallucinated money figure
is caught and the report falls back to the deterministic text; the report is
still produced with no API key at all; and the PDF carries the real numbers.

The Anthropic client is mocked with the same technique as
test_requisition_compliance.py — no key, no network.

Run: python test_audit_report.py
"""
from __future__ import annotations

import io
import json
import tempfile
import types
from pathlib import Path

import store

_base = Path(tempfile.mkdtemp(prefix="docex_audit_report_"))
store.set_store(store.JsonFileStore(_base / "store"))

import audit_report as ar  # noqa: E402
import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


# ─── mock the model ─────────────────────────────────────────────────────────

class _Captured:
    """Records what was actually sent, so the prompt size can be measured."""
    def __init__(self):
        self.kwargs = None
        self.reply = ""


captured = _Captured()


class _FakeMessages:
    def create(self, **kwargs):
        captured.kwargs = kwargs
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=captured.reply)],
            usage=types.SimpleNamespace(input_tokens=1800, output_tokens=900),
        )


ar._client = types.SimpleNamespace(messages=_FakeMessages())
ar._get_client = lambda: ar._client


GOOD_REPLY = json.dumps({
    "executive_summary": "Activity was routine this period and nothing requires escalation.",
    "finding_commentary": [],
    "recommendations": [],
})


def seed(org: str, n: int, *, amount: float = 50_000) -> None:
    wf = rq.default_workflow(org, size="small")
    wf.max_amount = 500_000_000
    rq.set_workflow(org, wf)
    for i in range(n):
        rq.create_requisition(org, submitted_by="program@x.org", department="program",
                              vendor_name=f"Vendor {i:03d}", amount=amount,
                              category="supplies")


def period_for(org: str):
    import datetime as dt
    today = dt.date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    return ar.build_period_data(org, start, end, label="This period")


# ─── THE COST QUESTION, MEASURED ───────────────────────────────────────────

SMALL, LARGE = "cost-small", "cost-large"
seed(SMALL, 5)
seed(LARGE, 400)

captured.reply = GOOD_REPLY
ar.narrate(period_for(SMALL))
small_prompt = len(captured.kwargs["messages"][0]["content"])

captured.reply = GOOD_REPLY
ar.narrate(period_for(LARGE))
large_prompt = len(captured.kwargs["messages"][0]["content"])

print(f"\n  prompt for 5 payments   : {small_prompt:,} chars (~{small_prompt // 4:,} tokens)")
print(f"  prompt for 400 payments : {large_prompt:,} chars (~{large_prompt // 4:,} tokens)")
print(f"  growth for 80x the work : {large_prompt / max(small_prompt, 1):.2f}x\n")

check("80x the payments does not mean 80x the prompt",
      large_prompt < small_prompt * 3)
check("even 400 payments stay under ~4k tokens of input",
      large_prompt < 16_000)
check("the cheap model tier is used, not the policy-interpretation one",
      captured.kwargs["model"] == ar.REPORT_MODEL)
check("output is capped", captured.kwargs["max_tokens"] <= 2000)

# The decisive one: no payee name from the population reaches the model
# except the handful in `top_payees`.
sent = captured.kwargs["messages"][0]["content"]
check("the model is NOT shown every payee — only the largest few",
      sent.count("Vendor ") <= 5)
check("the model is not shown individual requisition references",
      "REQ-0007" not in sent)

# ─── every figure is computed in Python ────────────────────────────────────

FIG = "figures-org"
seed(FIG, 3, amount=100_000)
data = period_for(FIG)
check("raised count is counted, not estimated", data.raised_count == 3)
check("raised value is summed in code", data.raised_value == 300_000.0)
check("spend by category is computed", data.by_category.get("supplies") == 300_000.0)
check("top payees are computed", len(data.top_payees) == 3)
check("a period with no exceptions is audit-ready", data.audit_ready is True)

# ─── a hallucinated figure is caught ───────────────────────────────────────

captured.reply = json.dumps({
    "executive_summary": "Total spend for the period was NGN 9,999,999.00 across all departments.",
    "finding_commentary": [],
    "recommendations": [],
})
narrative = ar.narrate(data)
check("a money figure that was never supplied is rejected",
      narrative["generated_by"] == "template")
check("the fallback text is used instead",
      "9,999,999" not in narrative["executive_summary"])

# A figure that WAS supplied passes.
captured.reply = json.dumps({
    "executive_summary": f"Requests totalling {data.raised_value:.2f} were raised.",
    "finding_commentary": [],
    "recommendations": [],
})
narrative = ar.narrate(data)
check("a figure taken from the input is accepted",
      narrative["generated_by"] == ar.REPORT_MODEL)
check("token usage is reported back for cost tracking",
      narrative["tokens"]["input"] == 1800)

# Small numbers are left alone — forbidding them makes the prose stilted.
captured.reply = json.dumps({
    "executive_summary": "Three requests were raised and all cleared within 5 days.",
    "finding_commentary": [],
    "recommendations": [],
})
check("small counts like 'three' and '5 days' are not treated as money claims",
      ar.narrate(data)["generated_by"] == ar.REPORT_MODEL)

# ─── the report survives with no model at all ──────────────────────────────

def explode():
    raise RuntimeError("no API key configured")


saved = ar._get_client
ar._get_client = explode
offline = ar.narrate(data)
ar._get_client = saved

check("with no API key the report is STILL produced",
      bool(offline["executive_summary"]))
check("it is marked as template-generated, not passed off as model output",
      offline["generated_by"] == "template")
check("the offline summary still carries the real counts",
      "3 payment requests" in offline["executive_summary"])

# ─── findings reach the report ─────────────────────────────────────────────

SOD = "report-sod-org"
wf = rq.default_workflow(SOD, size="small")
wf.steps = [
    rq.WorkflowStep(key="a", label="First", department="finance"),
    rq.WorkflowStep(key="b", label="Second", department="finance"),
]
rq.set_workflow(SOD, wf)
req = rq.create_requisition(SOD, submitted_by="raiser@x.org", department="program",
                            vendor_name="Two Hats", amount=40_000)
rq.decide(SOD, req.id, decision=rq.Decision.APPROVED, actor="one@x.org", department="finance")
rq.decide(SOD, req.id, decision=rq.Decision.APPROVED, actor="one@x.org", department="finance")

sod_data = period_for(SOD)
check("audit findings are carried into the report",
      any(f.code == "SOD_SAME_APPROVER" for f in sod_data.findings))

captured.reply = GOOD_REPLY
narrative = ar.narrate(sod_data)

# ─── the PDF ────────────────────────────────────────────────────────────────

pdf = ar.audit_report_pdf(sod_data, narrative, org_name="Test Organisation")
check("a real PDF is produced", pdf.startswith(b"%PDF"))

import pdfplumber  # noqa: E402
with pdfplumber.open(io.BytesIO(pdf)) as doc:
    text = "\n".join((p.extract_text() or "") for p in doc.pages)

check("the PDF names the organisation", "Test Organisation" in text)
check("the PDF states the verdict", "audit-ready" in text.lower())
check("the PDF carries the finding", "approved at multiple stages" in text.lower())
check("the PDF carries computed figures, not narrative ones", "40,000.00" in text)
check("the PDF discloses how the narrative was produced",
      "narrative" in text.lower() and "drafted" in text.lower())

# And the clean case reads as clean rather than manufacturing concern.
clean_pdf = ar.audit_report_pdf(data, ar._fallback_narrative(data))
with pdfplumber.open(io.BytesIO(clean_pdf)) as doc:
    clean_text = "\n".join((p.extract_text() or "") for p in doc.pages)
check("a clean period says every test passed", "Every test passed" in clean_text)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll audit-report checks passed.")
