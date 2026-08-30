"""
docex_agent.py — an agent-first compliance runner for DOCex.

The agent (Claude) does the tasks: it reads the payment documents, reasons over
the organisation's rulebook, judges the ambiguous cases, and writes the report —
which is what an LLM is genuinely good at. But for the handful of things an LLM
is provably weak at and where being wrong means a wrong payment — arithmetic
(three-way match, receipt sums, advance reconciliation) and exact lookups
(duplicate invoices) — it MUST call the deterministic tools below rather than
computing in its head. That "seatbelt" is what keeps an autonomous agent from
hallucinating the numbers, and it makes every figure in the report traceable.

Portable by design: built on the standard Anthropic tool-use loop — the same
loop the Claude Agent SDK wraps — so it runs today with an API key and graduates
to the Agent SDK / MCP later without a rewrite. Storage-agnostic: the caller
supplies the rulebook and the invoice history as context.

Runs offline for testing via a stub client (no API key, no tokens) that
exercises the full loop and tool execution.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable, Optional

_TOLERANCE = 0.01  # 1% slack on amount comparisons (rounding / VAT-inclusive)

DEFAULT_MODEL = "claude-sonnet-4-6"


# ─── Deterministic tools (the seatbelt) ──────────────────────────────────────
# Each returns a JSON-serialisable dict. The agent supplies the values it read
# from the documents; the tool does the exact maths / lookup and returns a fact.

def _three_way_match(invoice_amount: float, po_amount: float,
                     grn_amount: Optional[float] = None) -> dict:
    inv, po = float(invoice_amount), float(po_amount)
    diff = round(abs(inv - po), 2)
    agree = diff <= max(inv, po) * _TOLERANCE
    parts = [f"invoice {inv:,.2f} vs PO {po:,.2f}: " + ("agree" if agree else f"DIFFER by {diff:,.2f}")]
    if grn_amount is not None:
        g = float(grn_amount)
        gdiff = round(abs(inv - g), 2)
        gagree = gdiff <= max(inv, g) * _TOLERANCE
        agree = agree and gagree
        parts.append(f"GRN {g:,.2f}: " + ("agree" if gagree else f"DIFFERS by {gdiff:,.2f}"))
    return {"agree": agree, "invoice": inv, "po": po,
            "grn": (float(grn_amount) if grn_amount is not None else None),
            "difference": diff, "message": "; ".join(parts)}


def _reconcile_advance(advance_amount: Optional[float], receipt_amounts: list) -> dict:
    spent = round(sum(float(a) for a in (receipt_amounts or []) if a is not None), 2)
    if advance_amount is None:
        return {"advance": None, "total_spent": spent, "balance": None,
                "direction": "out_of_pocket",
                "message": f"No advance — reimburse the full {spent:,.2f} paid out of pocket."}
    adv = float(advance_amount)
    bal = round(adv - spent, 2)
    direction = "settled" if abs(bal) < 0.01 else ("recover" if bal > 0 else "reimburse")
    verb = {"settled": "fully retired", "recover": "to return", "reimburse": "to reimburse"}[direction]
    return {"advance": adv, "total_spent": spent, "balance": bal, "direction": direction,
            "message": f"Spent {spent:,.2f} of {adv:,.2f} advance — {abs(bal):,.2f} {verb}."}


def build_tools(*, rulebook_text: str = "",
                prior_invoice_numbers: Optional[list] = None) -> dict[str, tuple[dict, Callable]]:
    """Build the tool registry, binding run-specific context (rulebook + invoice
    history) into the closures. Returns {name: (schema, fn)}."""
    priors = {str(p).strip().lower() for p in (prior_invoice_numbers or []) if str(p).strip()}

    def check_duplicate(invoice_number: str) -> dict:
        n = str(invoice_number).strip().lower()
        dup = n in priors
        return {"duplicate": dup, "invoice_number": invoice_number,
                "message": (f"Invoice {invoice_number} has ALREADY been processed — possible duplicate payment."
                            if dup else f"Invoice {invoice_number} has not been processed before.")}

    def get_rulebook() -> dict:
        return {"rulebook": rulebook_text or "(no rulebook supplied)"}

    return {
        "three_way_match": ({
            "name": "three_way_match",
            "description": "Compare the invoice, purchase-order and (optional) goods-received-note amounts. Call this instead of comparing amounts yourself.",
            "input_schema": {"type": "object", "properties": {
                "invoice_amount": {"type": "number"}, "po_amount": {"type": "number"},
                "grn_amount": {"type": "number", "description": "optional"}},
                "required": ["invoice_amount", "po_amount"]},
        }, lambda **k: _three_way_match(**k)),
        "reconcile_advance": ({
            "name": "reconcile_advance",
            "description": "Reconcile submitted receipts against a travel advance. Call this to sum receipts and compute the balance — never add them yourself.",
            "input_schema": {"type": "object", "properties": {
                "advance_amount": {"type": ["number", "null"]},
                "receipt_amounts": {"type": "array", "items": {"type": "number"}}},
                "required": ["receipt_amounts"]},
        }, lambda **k: _reconcile_advance(k.get("advance_amount"), k.get("receipt_amounts", []))),
        "check_duplicate": ({
            "name": "check_duplicate",
            "description": "Check whether an invoice number has already been processed (duplicate-payment control).",
            "input_schema": {"type": "object", "properties": {"invoice_number": {"type": "string"}},
                             "required": ["invoice_number"]},
        }, lambda **k: check_duplicate(**k)),
        "get_rulebook": ({
            "name": "get_rulebook",
            "description": "Fetch the organisation's compliance rulebook to check the payment against.",
            "input_schema": {"type": "object", "properties": {}},
        }, lambda **k: get_rulebook()),
    }


_IMAGE_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
              ".gif": "image/gif", ".webp": "image/webp"}
_DIGITAL_EXT = (".pdf", ".docx", ".xlsx", ".xlsm", ".txt", ".csv", ".tsv")


def _ingest(files: list) -> tuple[str, list]:
    """Route each uploaded file for the agent — no OCR needed.

      - a digital doc with a real text layer → extracted to text (free, exact)
      - a photo (JPG/PNG) → a native image block for Claude vision
      - a scanned PDF with no text layer → a native PDF document block (vision)

    Returns (text_context, media_blocks) — media_blocks are Anthropic content
    blocks Claude reads directly, so the agent handles messy real-world bundles.
    """
    import base64
    import fast_extract

    text_parts: list[str] = []
    media: list = []
    for fn, data in files:
        low = (fn or "").lower()
        ext = low[low.rfind("."):] if "." in low else ""
        if ext in _IMAGE_EXT:
            media.append({"type": "image", "source": {"type": "base64",
                          "media_type": _IMAGE_EXT[ext],
                          "data": base64.standard_b64encode(data).decode()}})
            continue
        if low.endswith(_DIGITAL_EXT):
            text = fast_extract.extract_text(fn, data)
            if text.strip():
                text_parts.append(f"--- {fn} ---\n{text}")
                continue
            if low.endswith(".pdf"):  # scanned PDF, no text → let Claude read it
                media.append({"type": "document", "source": {"type": "base64",
                              "media_type": "application/pdf",
                              "data": base64.standard_b64encode(data).decode()}})
                continue
        # unknown → best-effort text
        try:
            text = fast_extract.extract_text(fn, data)
            if text.strip():
                text_parts.append(f"--- {fn} ---\n{text}")
        except Exception:  # noqa: BLE001
            pass
    return "\n\n".join(text_parts), media


_SYSTEM = """You are DOCex, a compliance & finance agent for {org}.

Read the payment documents and evaluate them against the organisation's rulebook
(call get_rulebook first). Produce a verdict for each applicable rule — pass,
flag, or block — with a short citation, then an overall verdict and a one-line
summary an officer can act on.

STRICT RULES:
- For ANY arithmetic (comparing invoice vs PO/GRN amounts, summing receipts,
  reconciling an advance) and for duplicate-invoice checks, you MUST call the
  provided tools with the values you extracted. NEVER compute or assert these
  numbers yourself.
- If a code-level tool reports a mismatch or a duplicate, the payment is BLOCKED.
- Escalate anything ambiguous. A human approves anything consequential
  (releasing a payment or a sign-off); you only produce the assessment."""


def run_agent(*, files: Optional[list] = None, documents_text: str = "",
              org_name: str = "the organisation", rulebook_text: str = "",
              prior_invoice_numbers: Optional[list] = None, client: Any = None,
              model: str = DEFAULT_MODEL, max_steps: int = 10) -> dict:
    """Run the compliance agent over a payment bundle.

    files: list of (filename, bytes) — ingested here (digital→text, images/scans
           →Claude vision). Or pass documents_text if you've extracted already.
    client: an Anthropic client (or None to use the offline stub for testing).
    Returns {report, overall_verdict, tool_calls, steps} — tool_calls is the
    audit trail of every deterministic check the agent invoked.
    """
    tools = build_tools(rulebook_text=rulebook_text, prior_invoice_numbers=prior_invoice_numbers)
    schemas = [schema for (schema, _fn) in tools.values()]
    system = _SYSTEM.format(org=org_name)
    if files:
        text_ctx, media_blocks = _ingest(files)
        content: list = []
        if text_ctx:
            content.append({"type": "text", "text": f"PAYMENT DOCUMENTS (extracted text):\n{text_ctx}"})
        content.extend(media_blocks)
        content.append({"type": "text", "text": "The bundle above may include text, photos and scans. Read all of it, then run the compliance audit."})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": f"PAYMENT DOCUMENTS:\n{documents_text}\n\nRun the compliance audit."}]
    call_log: list[dict] = []

    if client is None:
        client = _StubClient()  # offline: exercises the loop without an API key

    for _ in range(max_steps):
        resp = client.messages.create(model=model, max_tokens=2000, system=system,
                                      tools=schemas, messages=messages)
        if getattr(resp, "stop_reason", None) == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                fn = tools.get(block.name, (None, None))[1]
                try:
                    out = fn(**(block.input or {})) if fn else {"error": f"unknown tool {block.name}"}
                except Exception as exc:  # noqa: BLE001 — a bad tool call is a fact, not a crash
                    out = {"error": str(exc)}
                call_log.append({"tool": block.name, "input": block.input, "output": out})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
            continue
        # Final assistant message → the report.
        report = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text").strip()
        verdict = _infer_verdict(report, call_log)
        return {"report": report, "overall_verdict": verdict, "tool_calls": call_log, "steps": len(call_log)}

    return {"report": "(agent hit max steps without finishing)", "overall_verdict": "flagged",
            "tool_calls": call_log, "steps": len(call_log)}


def _infer_verdict(report: str, call_log: list[dict]) -> str:
    """A code-level block always wins, regardless of what the model wrote."""
    for c in call_log:
        out = c.get("output", {})
        if out.get("duplicate") is True or out.get("agree") is False:
            return "blocked"
    low = report.lower()
    if "block" in low:
        return "blocked"
    if "flag" in low:
        return "flagged"
    return "approved"


# ─── Deterministic fallback (agent unavailable) ──────────────────────────────
def _deterministic_fallback(files: list, prior_invoice_numbers: Optional[list] = None) -> dict:
    """Run the deterministic engine directly — no LLM — so a result is always
    produced even when the agent is unavailable (no key, API down, error)."""
    try:
        import fast_extract
        import payment_checks
    except Exception as exc:  # noqa: BLE001
        return {"report": f"Agent unavailable and deterministic fallback failed to load ({exc}).",
                "overall_verdict": "flagged", "tool_calls": [], "steps": 0, "mode": "fallback_error"}
    docs = fast_extract.extract_many([(fn, data) for fn, data in files])
    findings = payment_checks.run_document_checks(docs, prior_invoice_numbers=prior_invoice_numbers)
    verdicts = {f.verdict for f in findings}
    overall = ("blocked" if "block" in verdicts
               else "flagged" if verdicts & {"flag", "insufficient_evidence"} else "approved")
    report = ("Deterministic fallback (AI agent unavailable). " + (
        "; ".join(f.reasoning for f in findings) if findings
        else "No automated AP issues detected — manual review recommended."))
    log = [{"tool": f.rule_id, "input": {}, "output": {"verdict": f.verdict, "message": f.reasoning}}
           for f in findings]
    return {"report": report, "overall_verdict": overall, "tool_calls": log,
            "steps": len(log), "mode": "deterministic_fallback"}


def process(*, files: list, org_name: str = "the organisation", rulebook_text: str = "",
            prior_invoice_numbers: Optional[list] = None, client: Any = None,
            model: str = DEFAULT_MODEL) -> dict:
    """Agent-first, with a deterministic fallback.

    Claude is the primary engine — it reads the documents and images natively and
    runs the audit. If Claude is unavailable (no API key, client error) or the
    agent run throws, the deterministic engine runs instead so a trustworthy
    result is always returned. The `mode` field says which path ran.
    """
    import os
    if client is None and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception as exc:  # noqa: BLE001
            print(f"[docex-agent] anthropic client unavailable ({exc}); using fallback")
    if client is not None:
        try:
            res = run_agent(files=files, org_name=org_name, rulebook_text=rulebook_text,
                            prior_invoice_numbers=prior_invoice_numbers, client=client, model=model)
            res.setdefault("mode", "agent")
            return res
        except Exception as exc:  # noqa: BLE001 — agent failed → fall back, never crash
            print(f"[docex-agent] agent run failed ({exc}); using deterministic fallback")
    return _deterministic_fallback(files, prior_invoice_numbers)


# ─── Offline stub client (no API key) ────────────────────────────────────────
# Simulates a realistic agent trajectory so the loop + tool execution can be
# tested without tokens: step 1 fetches the rulebook, step 2 runs the three-way
# match, step 3 writes the report.

class _StubClient:
    def __init__(self):
        self.messages = self  # so client.messages.create(...) works
        self._step = 0

    def create(self, **kwargs):
        self._step += 1
        if self._step == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                SimpleNamespace(type="tool_use", name="get_rulebook", id="t1", input={})])
        if self._step == 2:
            return SimpleNamespace(stop_reason="tool_use", content=[
                SimpleNamespace(type="tool_use", name="three_way_match", id="t2",
                                input={"invoice_amount": 1250000, "po_amount": 1250000})])
        if self._step == 3:
            return SimpleNamespace(stop_reason="tool_use", content=[
                SimpleNamespace(type="tool_use", name="check_duplicate", id="t3",
                                input={"invoice_number": "INV-045"})])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
            type="text",
            text=("Overall: PASS. Three-way match confirmed (invoice = PO = 1,250,000); "
                  "invoice INV-045 is not a duplicate. All required documents present. "
                  "Ready for officer sign-off."))])


# ─── CLI runner — `python docex_agent.py [file1 file2 ...]` ──────────────────
if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) > 1:
        files = []
        for path in sys.argv[1:]:
            with open(path, "rb") as fh:
                files.append((os.path.basename(path), fh.read()))
    else:
        inv = ("PAYMENT VOUCHER / TAX INVOICE\nInvoice No: INV-045\nPurchase Order: PO-8890\n"
               "Vendor: Acme Supplies Ltd\nTotal Amount: NGN 1,250,000.00\n").encode()
        po = ("PURCHASE ORDER\nP.O. Number: PO-8890\nVendor: Acme Supplies Ltd\n"
              "Total: NGN 1,250,000.00\n").encode()
        files = [("invoice.txt", inv), ("po.txt", po)]

    res = process(
        files=files,
        org_name="Meridian Foundation (demo)",
        rulebook_text=("Rule 3.1: purchases above NGN 500,000 require a PO and a three-way match. "
                       "Rule 6.2: an invoice must not be paid twice."),
        prior_invoice_numbers=["INV-100", "INV-101"],
    )
    print(f"DOCex agent · mode: {res.get('mode')}   (set ANTHROPIC_API_KEY for live Claude)\n" + "=" * 60)
    print("VERDICT:", res["overall_verdict"].upper(), f"({res['steps']} tool calls)")
    print("\nREPORT\n------\n" + res["report"])
    print("\nAUDIT TRAIL — every deterministic check\n" + "-" * 60)
    for c in res["tool_calls"]:
        out = c["output"]
        print(f"  · {c['tool']} -> {out.get('message', out)}")
