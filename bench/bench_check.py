"""
DOCex compliance benchmark harness.

Measures the payment-check pipeline stage-by-stage so optimisations can be
compared BEFORE vs AFTER with real numbers instead of guesses. Read-only: it
imports the production engine and times it; it does not change any behaviour.

What it measures per test:
  extraction_ms   — parallel text extraction (fast_extract.extract_many_detailed)
  field_ms        — regex field extraction over every doc (fast_fields)
  deterministic_ms— AP controls (payment_checks.run_document_checks)
  llm_ms          — the compliance model call (only if ANTHROPIC_API_KEY is set)
  merge/total_ms  — end-to-end check_payment
  input_tokens / output_tokens / llm_calls / model / cache_* (from the metrics hook)
  document_count / receipt_count

LLM stage: requires a real ANTHROPIC_API_KEY (and network). Without one, the
harness runs every non-LLM stage and reports the LLM stage as "not measured"
— it NEVER invents numbers.

Fixtures: this harness uses SYNTHETIC text bundles so the deterministic path and
the output-shape can be exercised anywhere. They are plain text, so the
`extraction_ms` figure reflects the extraction *orchestration*, not real PDF/scan
parsing. For a true extraction/OCR baseline, drop real fixtures in
bench/fixtures/ (see REQUIRED_FIXTURES below) and point --real at them.

Run:
  python bench/bench_check.py                 # non-LLM stages (no key needed)
  ANTHROPIC_API_KEY=... python bench/bench_check.py --llm   # full, incl. model
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fast_extract  # noqa: E402
import fast_fields  # noqa: E402
import payment_checks  # noqa: E402
import compliance  # noqa: E402
from models import PolicyRule, PolicyRulebook  # noqa: E402

# Real fixtures we still need for a true extraction/OCR/semantic baseline:
REQUIRED_FIXTURES = [
    "Test E: a scanned/image-only PDF bundle (to measure OCR need — none wired yet)",
    "Test F: a real bundle that triggers a deterministic BLOCK (native PDFs)",
    "Test G: a real bundle requiring genuine semantic judgement",
    "Test H: a real bundle with ambiguous semantic evidence",
]


# ─── synthetic fixtures ──────────────────────────────────────────────────────

def _bundle(n_receipts: int, mismatch: bool = False, inv_no: str = "INV-1") -> list[tuple[str, str]]:
    po_total = "200,000" if mismatch else "100,000"
    docs = [
        ("voucher.txt", "PAYMENT VOUCHER\nPayee: ACME Ltd\nTotal Amount: NGN 100,000"),
        ("invoice.txt", f"INVOICE\nInvoice No: {inv_no}\nPurchase Order: PO-1\nTotal Amount: NGN 100,000"),
        ("po.txt", f"PURCHASE ORDER\nPurchase Order No: PO-1\nTotal: NGN {po_total}"),
        ("grn.txt", "GOODS RECEIVED NOTE\nGRN No: GRN-1\nItems received in full"),
    ]
    for i in range(1, n_receipts + 1):
        docs.append((f"receipt_{i:02d}.txt",
                     f"RECEIPT\nVendor: Taxi {i}\nDate: 2026-08-0{(i % 9) + 1}\nAmount: NGN {i}000"))
    return docs


def _synthetic_rulebook() -> PolicyRulebook:
    return PolicyRulebook(
        id="rb-bench", name="Bench Rulebook", source_documents=["policy.pdf"],
        rules=[
            PolicyRule(id="DOC-1", description="Invoice, PO and GRN must be attached",
                       category="documentation", source_quote="All three docs required.",
                       evaluation_type="llm", active=True),
            PolicyRule(id="APR-1", description="Payments over NGN 500k need Director sign-off",
                       category="approvals", source_quote="Over 500k → Director.",
                       evaluation_type="llm", active=True),
            PolicyRule(id="REC-1", description="Each receipt must show vendor, date and amount",
                       category="receipts", source_quote="Receipts must be complete.",
                       evaluation_type="llm", active=True),
        ],
    )


# ─── measurement ─────────────────────────────────────────────────────────────

def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def run_case(name: str, docs: list[tuple[str, str]], rulebook: PolicyRulebook,
             use_llm: bool) -> dict:
    receipt_count = sum(1 for fn, _ in docs if fn.startswith("receipt"))
    row: dict = {"test": name, "document_count": len(docs), "receipt_count": receipt_count}

    # Extraction (orchestration): encode to bytes and run the real parallel path.
    named_bytes = [(fn, text.encode()) for fn, text in docs]
    t0 = time.perf_counter()
    extracted = list(fast_extract.extract_many_detailed(named_bytes))
    row["extraction_ms"] = _ms(t0)
    docs_text = [(fn, txt) for fn, txt, _ in extracted if txt]

    # Field extraction (regex, no LLM).
    t0 = time.perf_counter()
    for _fn, txt in docs_text:
        fast_fields.extract_fields(txt)
    row["field_ms"] = _ms(t0)

    # Deterministic AP controls.
    t0 = time.perf_counter()
    payment_checks.run_document_checks(docs_text)
    row["deterministic_ms"] = _ms(t0)

    # Full check (adds the LLM leg + merge). Only when a key is available.
    if use_llm:
        metrics: dict = {}
        t0 = time.perf_counter()
        result = compliance.check_payment(docs_text, rulebook, payment_label=name, metrics=metrics)
        row["total_ms"] = _ms(t0)
        row["llm_ms"] = metrics.get("llm_ms")
        row["llm_calls"] = metrics.get("llm_calls")
        row["model"] = metrics.get("model")
        row["input_tokens"] = metrics.get("input_tokens")
        row["output_tokens"] = metrics.get("output_tokens")
        row["cache_read_tokens"] = metrics.get("cache_read_tokens")
        row["result_rows"] = len(result.results)
        row["overall_verdict"] = result.overall_verdict
    else:
        row["llm_ms"] = "not measured (no ANTHROPIC_API_KEY / --llm)"
        row["llm_calls"] = 0
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true",
                    help="also measure the model call (requires ANTHROPIC_API_KEY)")
    args = ap.parse_args()

    use_llm = args.llm and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if args.llm and not use_llm:
        print("WARNING: --llm requested but ANTHROPIC_API_KEY is not set; "
              "measuring non-LLM stages only.\n", file=sys.stderr)

    rulebook = _synthetic_rulebook()
    cases = [
        ("A_3_receipts", _bundle(3)),
        ("B_10_receipts", _bundle(10)),
        ("C_20_receipts", _bundle(20)),
        ("D_50_receipts", _bundle(50)),
        ("F_deterministic_block", _bundle(3, mismatch=True)),
    ]

    rows = [run_case(name, docs, rulebook, use_llm) for name, docs in cases]
    print(json.dumps({"llm_measured": use_llm, "results": rows}, indent=2))

    if not use_llm:
        print("\nLLM stage NOT measured. Set ANTHROPIC_API_KEY and pass --llm for the full picture.",
              file=sys.stderr)
    print("\nReal fixtures still needed for a true extraction/OCR/semantic baseline:", file=sys.stderr)
    for f in REQUIRED_FIXTURES:
        print(f"  - {f}", file=sys.stderr)


if __name__ == "__main__":
    main()
