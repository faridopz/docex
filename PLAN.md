# DOCex — Master Plan
*Last updated: 2 June 2026 · Owner: Farid · Status: shipping pilot prep*

The single source of truth that organises everything in flight. Every other
doc in `/prompts`, `/docs`, and our task list points back here. When you
open a new Claude Code task, hand it the matching prompt from `/prompts`
and tell it to read this file first.

---

## 1. North Star

**DOCex is the AI back-office for document-heavy operations.**
Read every document, verify every payment, check every rule — in minutes,
with citations.

Three composite Co-Pilots (Sub-award, Programs/Attendance Payment,
Compliance), four primitives (Extraction, Compliance, Bank Verify,
Knowledge Hub), one Assistant layer (Claude reads results and briefs the
human in plain English). Built for finance, programs, sub-award,
compliance, procurement, and grants teams anywhere.

The product is *cohesive*, not Nigeria-specific. It happens to be tested
first against Nigerian NGO workflows because that's where the pilot
demand is, but every primitive generalises (US foundations, UK trusts,
SE Asia INGOs).

## 2. Pilot Goals (next 6 weeks)

| Org              | Status                | Next action                          |
| ---------------- | --------------------- | ------------------------------------ |
| TA Connect       | Pilot proposal ready  | Send + book demo with Abosede        |
| Neem             | Demo prep             | Tailor decision log + send proposal  |
| Sydani           | Knowledge Hub angle   | Knowledge Hub demo + proposal        |
| 2 more by July   | Prospect now          | Sales agent runs outbound            |

**Goal:** 3 signed pilots by end of July 2026.

---

## 3. Streams in flight

Each stream has a corresponding paste-ready prompt in `/prompts/` that
you can open as its own Claude Code task. The numbers are priority order
for the next 4 weeks.

### A. Product hardening (highest priority, do this first)

| #   | Stream                          | Status   | Prompt file                            |
| --- | ------------------------------- | -------- | -------------------------------------- |
| A1  | Auth + onboarding flow          | Not started | `prompts/auth-and-user-caps.md`     |
| A2  | User caps + quota enforcement   | Not started | `prompts/auth-and-user-caps.md`     |
| A3  | Onboarding agent                | Not started | `prompts/onboarding-agent.md`       |
| A4  | Self-learning recommender       | Not started | `prompts/self-learning-system.md`   |
| A5  | UI overhaul (Spotify-grade)     | Plan only   | `prompts/ui-overhaul.md` + `UI_DIRECTION.md` |

### B. Internal agents (build once we have a customer)

| #   | Stream                          | Status   | Prompt file                            |
| --- | ------------------------------- | -------- | -------------------------------------- |
| B1  | Monitoring agent (daily code)   | Not started | `prompts/monitoring-agent.md`       |
| B2  | Sales agent (outbound + CRM)    | Not started | `prompts/sales-agent.md`            |
| B3  | Operations agent (back-office)  | Not started | `prompts/ops-agent.md`              |
| B4  | Demo artifact agent             | Not started | `prompts/demo-artifact-agent.md`    |

### C. Distribution & growth (sales motion)

| #   | Stream                          | Status   | Prompt file                            |
| --- | ------------------------------- | -------- | -------------------------------------- |
| C1  | Product PDF (prospect-ready)    | Shipping today | `docs/DOCex-Product-Brief.pdf`  |
| C2  | Demo fixture pack               | Shipping today | `demo_fixtures/`                |
| C3  | Notion CRM + Pilot Tracker      | Shipping today | Notion workspace                |
| C4  | GDrive folder structure         | Shipping today | Google Drive                    |
| C5  | GitHub ↔ Notion ↔ Claude link   | Not started | `prompts/github-notion-link.md`     |

---

## 4. Architecture (3-layer)

```
┌─────────────────────────────────────────────────┐
│  LAYER 3 — Composite Co-Pilots                  │
│  Sub-award · Attendance Payment · Compliance    │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  LAYER 2 — Primitives                           │
│  Extraction · Compliance Check · Bank Verify    │
│  Knowledge Hub · Rate Cards                     │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  LAYER 1 — Engines                              │
│  Claude Sonnet 4.6 · Paystack · openpyxl ·      │
│  pdfplumber · python-pptx · rapidfuzz           │
└─────────────────────────────────────────────────┘

Cross-cutting:
  · DOCex Assistant (Claude briefer over every result)
  · Self-Check Agent (admin diagnostics, ADMIN_SECRET gated)
  · Decision Log (append-only audit trail per check)
```

Phase-3 will add a **Flow Builder** (Make.com-style canvas) so customers
can compose their own agents from primitives. Not built yet.

---

## 5. The 14 asks (organised)

Mapping Farid's brain-dump → streams above.

| Ask (verbatim)                                              | Stream | Status |
| ----------------------------------------------------------- | ------ | ------ |
| Monitoring agent that monitors code daily                   | B1     | Prompt ready |
| Operations agent                                            | B3     | Prompt ready |
| Sales agent                                                 | B2     | Prompt ready |
| Demo artifact agent (creates + deletes)                     | B4     | Prompt ready |
| Notion-linked system → signed clients                       | C3     | Building today |
| Onboarding agent                                            | A3     | Prompt ready |
| Finish product to ready for sign-in + user caps             | A1+A2  | Prompt ready |
| Self-learning system (analyse usage → product recs)         | A4     | Prompt ready |
| Reframe landing (less Nigeria-specific, cohesive)           | —      | Shipping today |
| Clear draft data, ensure engines scaled                     | C2     | Shipping today |
| Demo fixture data (fake policies etc)                       | C2     | Shipping today |
| UI overhaul (Spotify-grade, not basic SaaS)                 | A5     | Plan + landing today |
| Product PDF                                                 | C1     | Shipping today |
| GitHub ↔ Notion ↔ Claude Code ↔ debugger link               | C5     | Prompt ready |

---

## 6. What's shipping THIS session

1. `PLAN.md` (this file)
2. `UI_DIRECTION.md` — UI overhaul direction doc
3. Rewritten landing page (global, cohesive framing)
4. `prompts/` — 9 paste-ready context+prompt docs
5. `demo_fixtures/` — fake policy + voucher + bank-verify seed
6. `demo_fixtures/seed.py` and `demo_fixtures/wipe.py`
7. `docs/DOCex-Product-Brief.pdf`
8. Notion CRM + Pilot Tracker (live, URLs returned in chat)
9. GDrive folder structure (live, URLs returned in chat)

Everything else gets a prompt doc so you can open the work as its own
Claude Code session.

---

## 7. How to use the prompt pack

When you want to work on a stream, open a new Claude Code session and
paste this:

> Read `/Users/faridabdurrahman/Desktop/docex/PLAN.md` first.
> Then read `/Users/faridabdurrahman/Desktop/docex/prompts/<stream>.md`
> and execute the task it describes.

The prompt file contains: the problem, what already exists, what to
build, the contract (API/UI/tests), and the success criteria. The agent
won't have to ask you a hundred clarifying questions because the doc
already answered them.

---

## 8. Operating principles (carry-over from CLAUDE.md)

- One feature at a time — ship before adding scope
- Audit defensibility > raw speed (every check snapshot the rulebook)
- No fake confidence — `not_found` is a real answer
- Frame as cohesive solution, never name-drop one country in copy
- Use plain English in every Assistant brief — no jargon
- File-based JSON persistence today, Supabase in Phase 2

---

## 9. Open decisions (Farid to resolve)

- [ ] Auth provider: Supabase Auth vs Clerk vs WorkOS? (default: Supabase)
- [ ] Pricing tier change? Current: Free 3 sessions / Pro $99 / Ent $299
- [ ] Self-learning agent — opt-in or default-on? (default suggestion: opt-in)
- [ ] Demo artifact deletion — auto after N days vs manual button?
- [ ] Sales agent outbound channel — email only or LinkedIn too?
