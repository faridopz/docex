# Chat Starters — copy-paste to open each workstream

Four chats, each staying sharp on its own thing. `MASTER_CONTEXT.md` carries the
shared context, so every one starts informed.

**The discipline that makes this work:** when a decision is made in any chat,
write it into `MASTER_CONTEXT.md`. A decision that only exists in a conversation
is one you will relitigate in six weeks.

---

## 1. EVA BUILD — start this one now

**Everything needed is already in the repo.** No waiting.

### Paste this:

```
This chat is the EVA build workstream for DOCex.

Read first, in this order:
  MASTER_CONTEXT.md        — product, architecture, the model, decisions made
  EVA_BUILD_SPEC.md        — who EVA is, their flow, what's net-new
  EVA_BUILD_PLAN.md        — the engine specs E1–E9 and the phase plan
  profiles/eva.json        — their config, with real thresholds + open questions
  EVA_CONFIRM_LIST.md      — what we've asked them, what's still unknown
  doa.py + test_doa.py     — Phase 1, already built and green

Where we are:
  Phase 1 (DOA matrix) is DONE — doa.py, 60 checks green. EVA's real approval
  bands are extracted from their signed Procurement Policy and configured:
  below N300,000 departmental · N300,000-N10m ED · N10m+ Board.

  Phase 2 is next: deductions.py (PAYE, pension, WHT, VAT) and coding.py
  (project/cost-centre coding + budget availability).

Rules that govern this work:
  - Deterministic-first. Code owns every number. If being wrong produces a
    plausible wrong number rather than a crash, it is code, never a model call.
  - Everything is CORE behind a feature flag, so NEEM inherits it too.
  - Never write "eva" into engine code. That's a config field or a flag.
  - Tests first, from written acceptance criteria. All suites stay green.
  - PAYROLL IS BLOCKED until EVA confirms the refinancing sign convention.
    Do not start it.

Start with deductions.py. Show me the acceptance criteria before you write code.
```

### What comes out of it

`deductions.py` and `coding.py`, tested, flagged. Both CORE — NEEM gets budget
checking free.

---

## 2. NEEM DELIVERY — start when you have 30 minutes at the Render dashboard

### Paste this:

```
This chat is the NEEM delivery workstream for DOCex. They are deploying for
real — no longer a demo — so their data is about to be live.

Read first:
  MASTER_CONTEXT.md          — product, architecture, decisions
  PRODUCTION_READINESS.md    — the go-live gate
  DEPLOYMENT_TOPOLOGY.md     — separate URL/server/database per client
  profiles/neem.json         — their config, placeholders marked _todo
  NEEM_FOLLOWUP_NOTES.md     — what they asked for

Where we are:
  Auth is closed (default-deny, test_auth_coverage.py green).
  Still blocking: durable storage on a persistent disk, tested backups,
  monitoring, secrets set explicitly.

Today: walk me through the production checklist step by step. I'll do the
dashboard work; tell me exactly what to set and how to verify each one.

When their policy documents and organogram arrive, we fill profiles/neem.json
from those and re-apply.
```

### Use the skill

Once open, invoke **`docex-go-live`** — it carries the full gate.

When their documents arrive, invoke **`docex-policy-to-profile`** — same
treatment EVA's policies got: real numbers, cited, with a confirm list.

---

## 3. BUSINESS & SALES — yes, create this one

### Paste this:

```
This chat is the business workstream for DOCex — pipeline, pricing, proposals,
positioning. No code.

Read first:
  MASTER_CONTEXT.md              — product, model, current clients
  business/SCALE_PLAN.md         — the plan and the honest math
  business/SCALING_STRATEGY.md   — sustainability, where agents help, path to scale
  business/PRICING_STRATEGY.md   — tiers and the reasoning
  business/CONSULTING_MODEL_TRUE_COSTS.md — real per-client economics
  business/REFERRALS_AND_MARKET.md        — who to approach
  business/INTERNATIONAL_NGO_TARGETS.md   — UK and international targets

Where we are:
  NEEM  — N450k/month, deploying now. Deliberate reputation trade.
  EVA   — N600k/month + phased build fees, Phase 1 built.
  Goal  — N3m/month, which is roughly five clients.

The binding constraint is my time on support, not demand. First hire is
support + config, not a developer.

Start by helping me build the prospect pipeline: who to approach, in what
order, and what the first message says.
```

### Use the skills

**`docex-prospect-prep`** before any pitch · **`docex-margin-review`** monthly
and before quoting anyone.

---

## 4. ENGINE & INFRA — this chat

Shared core, deployment automation, the profile generator, anything touching
both clients. Keep using it for work that isn't specific to one client.

---

## What to do right now, in order

| | Do | Where | Blocked on |
|---|---|---|---|
| **1** | Push the 15 commits | terminal | nothing |
| **2** | NEEM production infra | NEEM chat | nothing — **this is revenue** |
| **3** | Send EVA the confirm list | email | nothing |
| **4** | Build `deductions.py` | EVA chat | nothing |
| **5** | Open the sales chat, build the pipeline | Business chat | nothing |
| **6** | Fill `profiles/neem.json` | NEEM chat | their documents |
| **7** | Payroll | EVA chat | **their answer on refinancing** |

**Nothing you need is waiting on NEEM.** Items 1–5 are all unblocked today.

---

## On ₦3m/month — the honest arithmetic

```
NEEM     N450k    (reputation trade, rises to ~N550k at renewal)
EVA      N600k    + phased build fees
                  ─────────
                  N1.05m committed
```

**₦3m is roughly five clients** at ₦550–600k. Three more to close.

**Demand is not the constraint — your time is.** At ~20 support hours per
client, five clients is 100 hours a month before you write code or make a sale.

Which means the fastest route to ₦3m is not three more prospect calls. It is:

1. **Make NEEM and EVA visibly successful** — that produces the case study that
   makes clients three, four and five straightforward rather than uphill
2. **Hire support + config at client three**, not four. Config work is a
   validated JSON file, so it hands off on day one. Engine work stays with you.
3. **Charge properly from client three onward.** NEEM at ₦450k was deliberate.
   It does not repeat.

**Realistic:** ₦1.05m now → ~₦2m by mid-2027 (client 3 + NEEM renewal) → **₦3m
around late 2027** with clients four and five, which the hire makes possible.

Faster than that means either bigger clients (international, ₦700k–1.5m) or
hiring sooner. Both are available; both need the case study first.
