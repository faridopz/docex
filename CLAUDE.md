# DOCex — Project Memory

## What We Are Building
DOCex is an AI-powered document extraction tool.
A sub-award team receives hundreds of applications. Each applicant
submits multiple files — registration certificate, financials,
proposal, organisational profile, audit report. The team needs to
answer specific questions across all those documents quickly:
Is this org registered with CAC? What states do they work in?
Have they managed donor funds before? Do they have an anti-fraud policy?

Right now someone reads every document manually to find this.
DOCex extracts exactly that information automatically.

The user defines the questions. DOCex reads every document and
returns the answer, the source document, the exact quote, and a
confidence level. For batches, it produces an Excel table —
one row per applicant, one column per question.

## Target Users
- Sub-award teams at NGOs screening partner applications (first pilot)
- Grants managers at foundations
- HR teams screening CVs against a job spec
- Procurement teams reviewing supplier proposals
- Legal / compliance teams scanning contracts at scale
- Any team that receives documents in bulk and needs structured answers

## The Core Workflow
1. User defines questions in plain language
   e.g. "What states does this organisation work in?"
   e.g. "Has this org been audited in the last 2 years?"
   e.g. "Does the org mention USAID, Gates, or international donors?"

2. Single applicant mode:
   Upload multiple files for ONE applicant (all their docs together)
   Claude reads all of them and answers every question
   Results show: answer, source doc, quote, confidence

3. Batch mode:
   User adds multiple applicants, each with their own files
   Claude processes each applicant's document set
   Results: table — one row per applicant, one column per question
   Export to Excel (critical — the team lives in Excel)

## Core Data Models
Question: id, text (plain language question)
ExtractionAnswer: question_id, question_text, answer, confidence,
  source_document, quote
ApplicantExtraction: applicant_id, applicant_name, documents[],
  answers[], error?
BatchExtractionResult: total, succeeded, failed, applicants[]

## Confidence Levels
- "found" — answer is explicitly stated in a document
- "inferred" — answer can be reasonably concluded from context
- "not_found" — not mentioned in any document

## Tech Stack
- Frontend: Next.js 14, TypeScript, Tailwind CSS, shadcn/ui
- Backend: FastAPI (Python)
- Core AI engine: screener.py (being rebuilt for extraction)
- Database: Supabase (postgres + auth + file storage) — Phase 2
- AI model: claude-sonnet-4-6
- Excel export: SheetJS (xlsx) on frontend

## Project Structure
/ngo_screener   — Python extraction engine
  models.py     — Pydantic models: Question, ExtractionAnswer, etc.
  screener.py   — Core Claude API extraction logic
  main.py       — CLI interface
/api            — FastAPI wrapper
/web            — Next.js frontend
CLAUDE.md       — This file
SOUL.md         — Project soul and values

## Design System
- Font: Geist (Next.js default)
- Accent: #2563eb (blue-600)
- Background: white / gray-50
- Cards: white with subtle border and shadow
- Confidence colors: emerald = found, amber = inferred, gray = not_found
- Style: Clean, minimal, professional — Notion meets Linear

## Key Conventions
- TypeScript strict mode throughout frontend
- All API calls from frontend go through web/lib/api.ts
- Python files follow existing patterns in ngo_screener/
- Never rewrite existing working code unless told to
- One feature at a time — no unrequested additions
- Always add error handling and loading states
- Comments on non-obvious logic

## Build Phases

### Phase 1 — Core extraction (current)
- [x] Landing page (DOCex branded)
- [x] Next.js scaffold with Tailwind + shadcn
- [ ] models.py — extraction data models
- [ ] screener.py — extraction logic (combine docs, answer questions)
- [ ] api/schemas.py — extraction API schemas
- [ ] api/main.py — /extract/single and /extract/batch endpoints
- [ ] web/types/index.ts — extraction types
- [ ] web/lib/api.ts — API calls + Excel export
- [ ] QuestionBuilder component
- [ ] ApplicantUpload component
- [ ] ExtractionTable component
- [ ] App wizard page (3-step: questions → applicants → results)

### Phase 2 — Persistence + auth
- [ ] Supabase auth (login/signup with org creation)
- [ ] Questions saved as reusable templates
- [ ] Extraction sessions saved to database
- [ ] Session history page
- [ ] Real-time progress during batch extraction
- [ ] PDF export of results

### Phase 3 — Scale
- [ ] Multi-tenant with row level security
- [ ] Subscription billing via Paystack
- [ ] Applicant submission portal
- [ ] Team member invites
- [ ] Deploy to Vercel + Railway

## Business Model
Pricing happens per-pilot in conversation — NOT on the landing, NOT
in the PDF, NOT in the product UI. Internal quota tiers exist in
code (free / pilot / scale) for rate-limiting but their dollar
amounts and tier names are never surfaced publicly. When a free
user hits cap, the message is "contact founder@docex.app to scale"
— never an upgrade-with-price prompt.

## Primary Pilot Client
TA Connect — public health NGO, Abuja Nigeria
Sub-award team screens 200+ partner applications per cycle
Each applicant submits 5–8 documents
Team needs answers to ~15 standard questions per applicant

## Agent Rules
- Always read CLAUDE.md and SOUL.md at the start of every session
- Never rewrite working code to fix one small thing
- One file at a time, show me before moving on
- After each step tell me exactly what to run to test it
- When in doubt do less better
- Commit after every working feature
