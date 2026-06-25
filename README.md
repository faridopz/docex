# DOCex

**AI-powered document intelligence for teams that screen documents in bulk.**
Define questions in plain language, upload a stack of files, and get back
structured, **cited** answers — the answer, the source document, the exact
quote, and a confidence level — in minutes instead of weeks.

> Somewhere in Abuja, a sub-award officer has 200 application documents open
> in tabs and 3 days to shortlist 10 partners. She'll miss strong organisations
> because she ran out of time. **DOCex exists so that never has to happen
> again.** It was built from a real volunteer engagement with an NGO in Abuja,
> Nigeria — the problem was real before the product existed.

---

## Live

- **Demo:** https://docex-demo.vercel.app
- **Architecture board (Miro):** https://miro.com/app/board/uXjVHBt3n8U=/
- **Production:** containerized and deployed on **AWS ECS Fargate**, shipped by
  a keyless CI/CD pipeline, with the entire stack defined in **Terraform**.

---

## What it does

DOCex reads documents the way a careful analyst would, and returns answers you
can trust because every claim is **traceable to its source**:

- **Extraction** — ask plain-language questions across an applicant's documents
  (registration, financials, proposal, audit) and get `answer · source · quote ·
  confidence (found / inferred / not_found)`, one row per applicant for a batch.
- **Knowledge Hub (RAG)** — upload slide decks / Word / PDFs and ask questions
  across the whole library; answers cite the exact slide/page (`[Slide 11]`)
  rendered as clickable source chips.
- **Compliance, Bank Verify, Attendance** — additional document-driven workflows
  built on the same extraction + citation core.

Everything is designed around one rule from the project's soul: *does this make
the overworked grants officer's life simpler, or more complicated?* If it's more
complicated, it doesn't get built.

---

## Architecture

Two load-balanced services on AWS Fargate, behind a keyless CI/CD pipeline, all
defined as code. (Full interactive diagram on the
[Miro board](https://miro.com/app/board/uXjVHBt3n8U=/).)

```
                          ┌──────────────────── VPC ────────────────────┐
  Browser ──▶ Web ALB ──▶ │  docex-web (Next.js, Fargate)                │
     │                    │                                              │
     └─────▶ API ALB ──▶  │  docex-api (FastAPI, Fargate) ──┐            │
                          └────────────────────────────────┼────────────┘
                                                            │
                  ┌──────────────────┬──────────────────────┼───────────────┐
                  ▼                  ▼                       ▼               ▼
          Secrets Manager     Anthropic Claude          CloudWatch       Amazon ECR
          (API key)           (Sonnet 4.6)              Logs             (images)
```

**Deploy pipeline:** `git push` → GitHub Actions → assume an IAM role via
**OIDC (no stored AWS keys)** → build images → push to ECR → `ecs update-service`
→ **zero-downtime rolling deploy**.

---

## The RAG pipeline

The Knowledge Hub answers questions over a document library with verifiable
citations — retrieve-then-generate, grounded to prevent hallucination:

1. **Ingest** — documents are parsed into chunks (slides / pages / sections).
2. **Retrieve** — a query ranks chunks with **BM25** (a dependency-free lexical
   retriever — no vector DB required, but structured so embeddings + pgvector
   can slot in behind the same `retrieve()` interface later); the top ~24 chunks
   are selected.
3. **Generate** — only those chunks become the context for **Claude Sonnet 4.6**,
   which must answer *from the source* and cite every claim as `[Slide N]`.
4. **Ground** — citations are parsed back out into clickable chips, so the user
   can verify every statement against the original document.

A clear "this document doesn't cover that" is treated as more valuable than a
confident guess.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js 14 (TypeScript, Tailwind, shadcn/ui) |
| Backend | FastAPI (Python) |
| AI | Anthropic Claude (Sonnet 4.6) |
| Retrieval | BM25 over document chunks (pure-Python, swappable for embeddings) |
| Containers | Docker (multi-stage, Next.js standalone output) |
| Cloud | AWS: ECS Fargate, ECR, ALB, VPC, Secrets Manager, CloudWatch, IAM |
| CI/CD | GitHub Actions + OIDC (keyless) |
| IaC | Terraform (entire stack) |

---

## Engineering highlights

- **Keyless CI/CD** — GitHub Actions authenticates to AWS via OIDC, assuming a
  least-privilege role per run. No long-lived AWS credentials stored anywhere.
- **Secrets done right** — the Anthropic key lives in AWS Secrets Manager and is
  injected into the container at runtime; it never appears in code, image, or
  task definition.
- **Least-privilege IAM** — task execution and deploy roles grant only the exact
  actions/resources they need.
- **Zero-downtime deploys** — ECS rolling updates start new tasks, wait for
  health checks, then drain the old ones.
- **Infrastructure as Code** — the *entire* live stack was imported into
  Terraform with **zero downtime**; it can now be reviewed, reproduced, or torn
  down and rebuilt with one command.
- **Optimized images** — multi-stage builds + Next.js standalone output cut the
  web image by ~80%.

See [`CASE_STUDY.md`](./CASE_STUDY.md) for the full engineering story, including
the production bugs debugged from CloudWatch logs.

---

## Repository layout

```
/ngo_screener (root *.py)  Python extraction + RAG engine
  models.py                Pydantic data models
  screener.py              Core Claude extraction logic
  retrieval.py             BM25 retrieval layer
  knowledge.py             RAG Q&A with citations
/api                       FastAPI app + routes + Dockerfile
/web                       Next.js frontend + Dockerfile
/deploy                    Task definitions, IAM policies, service scripts
/terraform                 Infrastructure as Code (the whole AWS stack)
/.github/workflows         CI (ci.yml) and CD (deploy.yml)
```

---

## Running locally

Requires Docker and an Anthropic API key.

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY
docker compose up --build     # API on :8000, web on :3000
```

Open http://localhost:3000.

---

## Operating model

- **App changes** → `git push` → the pipeline builds and deploys automatically.
- **Infrastructure changes** → edit Terraform → `terraform plan` → `apply`.
  (The AWS console is never edited by hand — that would cause drift.)

---

*Built by Farid. Origin: a volunteer engagement with TA Connect, Abuja, Nigeria.*
