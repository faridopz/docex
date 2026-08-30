"""
TAConnect compliance & finance tool — STARTER SCAFFOLD.

A clean frame built from the DOCex *architecture guide* (not the DOCex product
implementation). It gives you and the IT lead a shared starting point to build
the TAConnect version together. Fill in the TODOs.

Principle (keep it): DETERMINISTIC-FIRST. Code does the arithmetic and exact
lookups; the AI model is used only for judgment. A code-level BLOCK always wins.

Deps to add as you go:  pip install fastapi uvicorn pymupdf python-docx openpyxl anthropic
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ─── Data models ─────────────────────────────────────────────────────────────
@dataclass
class Rule:
    id: str
    description: str
    condition: Optional[str] = None
    evidence_required: list[str] = field(default_factory=list)
    category: str = "general"
    source_quote: Optional[str] = None
    evaluation_type: str = "ai"          # "code" | "ai"


@dataclass
class RuleResult:
    rule_id: str
    verdict: str                          # "pass" | "flag" | "block" | "insufficient"
    reasoning: str
    citation: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class CheckResult:
    documents: list[str]
    overall_verdict: str                  # "approved" | "flagged" | "blocked"
    summary: str
    results: list[RuleResult] = field(default_factory=list)
    invoice_number: Optional[str] = None


# ─── Stage 1 — Parse (TODO) ──────────────────────────────────────────────────
def extract_text(filename: str, data: bytes) -> str:
    """Turn a file into text.
    TODO:
      - .pdf  → PyMuPDF (fitz); fall back to pdfplumber
      - .docx → python-docx (walk paragraphs AND table cells, in order)
      - .xlsx → openpyxl (render label:value rows so fields survive)
      - image / scanned PDF → return "" here and route to the vision model
    """
    raise NotImplementedError


# ─── Stage 2 — Field extraction (TODO) ───────────────────────────────────────
def extract_fields(text: str) -> dict:
    """Pull key values behind their labels (labelled-regex).
    TODO: total_amount, invoice_number, po_number, grn_number, date — each with
    a confidence. Return e.g. {"total_amount": 1250000.0, "invoice_number": "INV-045"}.
    """
    raise NotImplementedError


# ─── Stage 4 — Deterministic controls (reference impls — textbook, keep) ─────
_TOL = 0.01

def three_way_match(invoice_amount: float, po_amount: float,
                    grn_amount: Optional[float] = None) -> dict:
    inv, po = float(invoice_amount), float(po_amount)
    diff = round(abs(inv - po), 2)
    agree = diff <= max(inv, po) * _TOL
    if grn_amount is not None:
        agree = agree and abs(inv - float(grn_amount)) <= max(inv, float(grn_amount)) * _TOL
    return {"agree": agree, "difference": diff,
            "message": f"invoice {inv:,.2f} vs PO {po:,.2f}: " + ("agree" if agree else f"DIFFER by {diff:,.2f}")}

def duplicate_invoice(invoice_number: str, prior_numbers: list[str]) -> dict:
    n = str(invoice_number).strip().lower()
    dup = n in {str(p).strip().lower() for p in (prior_numbers or [])}
    return {"duplicate": dup, "message": f"{invoice_number} " + ("already processed — possible duplicate" if dup else "not seen before")}

def reconcile(advance_amount: Optional[float], receipt_amounts: list[float]) -> dict:
    spent = round(sum(float(a) for a in receipt_amounts if a is not None), 2)
    if advance_amount is None:
        return {"total_spent": spent, "direction": "out_of_pocket", "balance": None}
    bal = round(float(advance_amount) - spent, 2)
    direction = "settled" if abs(bal) < 0.01 else ("recover" if bal > 0 else "reimburse")
    return {"total_spent": spent, "balance": bal, "direction": direction}


# ─── Stage 6 — Evaluate (skeleton) ───────────────────────────────────────────
def evaluate(rules: list[Rule], documents: list[tuple[str, str]],
             prior_invoice_numbers: Optional[list[str]] = None, ai=None) -> CheckResult:
    """Deterministic-first evaluation.
    1) run the code controls (three_way_match, duplicate_invoice) from extracted fields;
    2) if any BLOCKS → return blocked (skip the AI);
    3) otherwise, send the remaining judgment rules to the AI (grounded with the
       extracted fields), then merge.  TODO: wire steps 1 and 3.
    """
    results: list[RuleResult] = []
    # TODO: extract fields per doc, run the deterministic controls into `results`
    # TODO: if a control blocks -> overall "blocked", return now
    # TODO: for evaluation_type == "ai" rules, call the model with the facts
    overall = "blocked" if any(r.verdict == "block" for r in results) else (
        "flagged" if any(r.verdict in ("flag", "insufficient") for r in results) else "approved")
    return CheckResult(documents=[fn for fn, _ in documents], overall_verdict=overall,
                       summary="TODO: one-line summary", results=results)


# ─── Stage 5 — Policy → rulebook (TODO) ──────────────────────────────────────
def extract_rules(policy_text: str) -> list[Rule]:
    """TODO: pull thresholds, required-docs, approval limits, deadlines from the
    policy text (regex/heuristics for the obvious ones); AI only for the rest.
    Each Rule cites its source clause."""
    raise NotImplementedError


# ─── API skeleton (lazy — needs fastapi) ─────────────────────────────────────
def build_app():
    from fastapi import FastAPI, UploadFile, File, Form  # noqa
    app = FastAPI(title="TAConnect Compliance Tool")

    @app.post("/check")
    async def check(payment_documents: list[UploadFile] = File(...), rulebook_id: str = Form(...)):
        # TODO: read files -> extract_text; load rules; evaluate(); save; return
        return {"todo": "wire evaluate()"}

    @app.post("/retire")
    async def retire(advance_reference: str = Form(""), receipts_json: str = Form("[]")):
        # TODO: parse receipts -> reconcile(); return
        return {"todo": "wire reconcile()"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    # Quick smoke test of the deterministic controls (no deps needed).
    print(three_way_match(1_250_000, 1_250_000))
    print(three_way_match(1_900_000, 1_250_000))
    print(duplicate_invoice("INV-045", ["INV-045"]))
    print(reconcile(150_000, [80_000, 20_000]))
