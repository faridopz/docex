# DOCex — Deterministic-First Document Intelligence for Compliance & Finance

> A full-stack AI system that reads an organisation's documents and answers
> compliance and finance questions in **milliseconds**, reserving the language
> model only for genuine judgment calls.
>
> **Role:** Sole designer & engineer (product, backend, frontend, infrastructure)
> **Stack:** Next.js 14 · TypeScript · FastAPI · Python · Anthropic Claude · AWS / Railway / Vercel
> **Status:** Working system, deployed to production

*(Built as an independent project. All examples below use synthetic data; no
client information is included.)*

---

## The problem

Compliance and grants teams drown in documents. A single reviewer might process
hundreds of partner applications and payment vouchers by hand — reading each PDF,
checking a policy, adding up receipts, spotting duplicates, verifying that an
invoice, a purchase order and a delivery note all agree. It's slow, error-prone,
and exactly the kind of rules-and-arithmetic work that shouldn't require a human
squinting at a scan.

The obvious solution — "throw it all at an LLM" — is tempting and wrong. It's
slow, expensive, non-deterministic, and for a tool that greenlights *payments*,
"the AI usually gets it right" is not good enough.

## The core idea: deterministic-first, LLM-for-judgment

The central engineering decision — and the thing I'm proudest of — was refusing
to make the LLM do work that code does better. Reading a number off a labelled
field, summing receipts, matching a PO to an invoice, detecting a duplicate: these
are **solved, deterministic problems**. Code does them in microseconds, for free,
and never hallucinates.

So DOCex is built as a layered pipeline where each layer is as cheap and reliable
as possible, and the LLM is the *last* resort, not the first:

1. **Parsing** — a shared extractor pulls text from PDF, DOCX, Excel and CSV
   (PyMuPDF with a pdfplumber fallback; Excel rendered so labelled fields survive).
2. **Field extraction** — labelled-regex pulls amounts, invoice/PO/GRN numbers,
   dates and tax IDs with a confidence score.
3. **Completeness** — signature-matching checks the required documents are present.
4. **Deterministic controls** — three-way match, duplicate-payment detection,
   thresholds and deadlines evaluated in code.
5. **Policy → rules** — an organisation's policy document is turned into a
   structured, citeable rulebook by regex/heuristics, instantly.
6. **The LLM** — Claude runs **only** on the rules that genuinely need reading
   comprehension, and it's handed the code-extracted facts as grounding so it does
   less and is more accurate. If the deterministic layer already *blocks* a
   payment, the model call is skipped entirely.

The result: a typical payment voucher is verdicted almost entirely in code, in
milliseconds, and the model is reserved for the handful of nuanced judgments that
actually need it.

## What I built

- **A shared document-intelligence engine** (extraction, field-pull, completeness,
  policy→rules, AP controls, receipt reconciliation) that every feature reuses.
- **Compliance checks** — upload a payment bundle, get a rule-by-rule verdict
  (pass / flag / block) with citations from both the policy and the payment, plus
  an instant three-way match and duplicate-payment control.
- **A policy-to-rulebook engine** — drop in a procurement or travel policy and get
  a structured, editable, citeable rulebook back in ~1 second, no model call for
  the common case.
- **Travel-advance retirement** — reconcile a stack of receipts against an advance
  and compute who owes whom, deterministically, with problem receipts flagged —
  *without* OCR, by capturing amounts at entry and reading digital receipts for
  free.
- **An audit trail** — every decision (check, approval, amendment) is logged
  append-only and exportable, because compliance lives and dies on provenance.
- **Async, non-blocking UX** — slow work (a large policy interpretation) runs in a
  background job with an instant preview and a stale-guard, so the UI never lies
  about progress or spins forever.

## Architecture

```
Next.js 14 (TypeScript, Tailwind, shadcn/ui)      ← product UI
        │  typed API client
        ▼
FastAPI (Python)                                  ← API layer
        │
        ├─ fast_extract     parsing (PDF/DOCX/XLSX)   ── code
        ├─ fast_fields      labelled-field extraction ── code
        ├─ doc_completeness required-doc detection    ── code
        ├─ policy_rules     policy → structured rules  ── code
        ├─ payment_checks   three-way match, dup detect ─ code
        ├─ receipts         retirement reconciliation  ── code
        └─ Claude (Sonnet)  judgment rules only        ── LLM
```

Deployed on AWS ECS Fargate (two services behind load balancers, infra as code in
Terraform) with a GitHub Actions CI/CD pipeline; a Railway + Vercel deployment for
the demo environment.

## What I learned (the honest version)

- **Knowing when *not* to use the LLM is the senior skill.** The instinct to reach
  for the model first is common; the discipline to solve 80% of the problem in
  fast, testable, auditable code is what makes a system reliable and affordable.
- **Reliability is a feature.** I built graceful degradation everywhere — a bug in
  the fast path falls back to the LLM, a failed AI pass still ships the
  code-extracted rules, a stalled background job surfaces an honest error instead
  of spinning forever.
- **Shipping is its own discipline.** Getting this live meant fighting real
  production problems — a boot-crash from a missing import, a middleware deadlock,
  build-time env-var baking, a broken deploy pipeline — and building the
  observability to diagnose them. That operational scar tissue is as valuable as
  the features.

## Tech stack

**Frontend:** Next.js 14 (App Router), TypeScript (strict), Tailwind, shadcn/ui
**Backend:** FastAPI, Python, Pydantic v2, PyMuPDF, openpyxl
**AI:** Anthropic Claude (Sonnet for judgment, Haiku for lightweight tasks), prompt caching
**Infra:** AWS ECS Fargate, Terraform, GitHub Actions, Railway, Vercel

---

*Want a walkthrough? [live demo link] · [2-minute video] · [architecture diagram]*
