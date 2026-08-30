# DOCex — Architecture & Build Guide (shareable)

*This document describes the DESIGN and LOGIC for building a compliance & finance
tool. It is the blueprint for a co-built TAConnect version. It intentionally does
not include the proprietary DOCex implementation — build the implementation fresh
from this design.*

## The one principle everything follows
**Deterministic-first. Code does the certain; AI does the judgment.**
Anything that is arithmetic or an exact lookup — comparing invoice vs PO amounts,
summing receipts, detecting a duplicate invoice, checking a threshold — is done in
**code**: fast, exact, auditable, free, no hallucination. An AI model (Claude) is
used **only** for what code can't do well: reading messy/varied documents,
interpreting a policy clause, judging ambiguous cases, and drafting narrative.
**A code-level "block" always overrides the AI.**

## The pipeline (stages + responsibility)
1. **Parse** — turn each uploaded file into text. Digital docs (PDF/DOCX/XLSX) →
   a parser library. Photos/scans → a vision model (reads them natively; no OCR).
2. **Extract fields** — pull the key values behind their labels (amounts, invoice/
   PO/GRN numbers, dates) with labelled-regex; attach a confidence to each.
3. **Completeness** — check the required documents for this payment type are present.
4. **Deterministic controls** — three-way match (invoice↔PO↔GRN amounts + PO
   cross-reference) and duplicate-payment detection (invoice number vs history).
5. **Policy → rules** — convert a policy document into a structured, citeable
   rulebook (rules with: description, condition, required evidence, category,
   the source clause). Do the obvious rules by pattern; use AI only for the rest.
6. **Evaluate** — for each active rule: run it in code where possible; send only
   genuine judgment rules to the AI, grounded with the code-extracted facts.
   Merge into a verdict per rule (pass / flag / block) + an overall verdict.
   *If the deterministic controls already block, skip the AI entirely.*
7. **Retirement (travel)** — reconcile submitted receipts against an advance:
   sum receipts (code), compute balance, decide recover / reimburse / settled,
   and flag problem receipts (duplicate, out-of-window date, unreadable amount).
8. **Around it** — an append-only audit log of every decision; an approval
   workflow; a payment lifecycle (needs-attention → requisition → in-approval →
   approved → paid).

## Two ways to run it (same logic underneath)
- **Pipeline mode:** your code orchestrates the stages and calls the AI as one step.
  Fast, cheap, deterministic — the default for routine, high-volume work.
- **Agent mode:** the AI orchestrates — it reads the documents and decides which
  tools to call; the deterministic checks above are exposed to it as **tools**
  (so it never does the maths itself). Best for messy inputs and autonomous,
  end-to-end "here's the finished audit" runs. Always keep a deterministic
  fallback so a result is produced even if the AI is unavailable.

## Data shapes (what to model)
- **Rule:** `id, description, condition, evidence_required[], category, source_quote, evaluation_type(code|ai)`
- **RuleResult:** `rule_id, verdict(pass|flag|block|insufficient), reasoning, citation, evidence`
- **CheckResult:** `id, documents[], rulebook_id, overall_verdict, summary, results[], invoice_number, reconciliation?, audit_log[]`
- **Reconciliation:** `advance_amount, total_spent, balance, direction(recover|reimburse|settled|out_of_pocket), flags[]`
- **OrgProfile:** `name, payment_types[], approval_workflow[]`

## Suggested stack
- Backend: **FastAPI + Python** (endpoints: `/check`, `/policy`, `/retire`).
- AI: **Anthropic Claude** (a strong model for judgment/vision; a lighter one for
  simple tasks). Enable prompt caching for the rulebook.
- Parsing: PyMuPDF (PDF), python-docx (DOCX), openpyxl (XLSX).
- Frontend: any (Next.js works well); or start API-only.
- Storage: start with a database (Postgres) — do NOT rely on container local disk.

## Build order (fastest path to value)
1. Parse + field extraction (stages 1–2).
2. The two deterministic controls: three-way match + duplicate detection (stage 4).
3. Completeness check (stage 3).
4. Policy → rulebook (stage 5), then evaluate (stage 6).
5. Retirement (stage 7).
6. Audit log + approval workflow (stage 8).

## Non-negotiables
- Keep the arithmetic/lookups in code, always. Never let the AI assert a number.
- Every verdict cites its source (policy clause + payment evidence).
- Human approves anything consequential (releasing a payment / a sign-off).
- Store data durably (DB), not on ephemeral disk.
