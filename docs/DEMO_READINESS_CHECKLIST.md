# DOCex — Demo Readiness Checklist

_Compiled from ACTION_PLAN.md, DEVOPS_ROADMAP.md, docs/DEMO_DAY_RUNOFSHOW.md,
docs/DEPLOY_CHECKLIST.md, docs/POWER_AUTOMATE_INTEGRATION.md, and current git
history. Owner: Farid · Compiled: 2 July 2026._

---

## 1. What's already done (verified in code/git)

The full ACTION_PLAN.md backlog (Sprint 1 + Sprint 2 + QA) is shipped:

- ✅ Shared `AppNav` / left-sidebar `AppShell` — consistent nav everywhere
- ✅ Copy pass — no "ED-approved" or "Briefed by Claude" strings left in `web/app`
- ✅ Sub-award page slimmed (bank-verify step removed, reframed as screening only)
- ✅ "Programs Co-Pilot" → "Attendance & Payment Flow", renamed everywhere
- ✅ Standalone Bank Verify surfaced under Compliance (`compliance/new`, `compliance/page`)
- ✅ Query-thread view + SMTP email escalation/clarification (Outlook/Gmail), logged to audit trail
- ✅ Immersive `/tour` walking all flows (screening, attendance, compliance, knowledge)
- ✅ Since the original plan: Payment Voucher framing, verified email magic-link
  sign-off, requisition-vs-voucher distinction, risk & actions register,
  org-configurable approval workflow, connector framework (ERPNext, Odoo),
  Knowledge Hub RAG, full AWS/Terraform deployment
- ✅ Git is clean, no uncommitted changes; latest commit gitignores the HMAC
  approval secret

**Product/UX side is in good shape.** The open risk is infrastructure and
document hygiene, below.

---

## 2. Blocking or high-risk before a demo

- [ ] **Two conflicting demo environments.** `docs/DEMO_DAY_RUNOFSHOW.md` and
  `docs/DEPLOY_CHECKLIST.md` both point at the **old Railway + Vercel** setup
  (`docex-demo.vercel.app` / a Railway backend). CLAUDE.md says the **real
  live deployment is now AWS ECS Fargate**, with Vercel kept only as a demo
  mirror. Decide which one you're actually presenting from, and update (or
  retire) whichever run-of-show doc doesn't match — presenting from the wrong
  one, or improvising the URL live, is the single easiest way to lose
  polish in front of investors.
- [ ] **AWS has no HTTPS / custom domain yet** (deferred in DEVOPS_ROADMAP.md
  Module 4 polish). If you demo from AWS, it's a raw `.elb.amazonaws.com`
  HTTP URL — fine for a technical audience, but confirm that's acceptable
  for this specific room before you're on stage.
- [ ] **Data is ephemeral on AWS** (per CLAUDE.md: container disk is wiped on
  every redeploy; durable storage isn't built yet). If you demo from AWS:
  seed the instance **after** your last deploy, and don't push to
  `demo-release` between seeding and the demo — a CI-triggered redeploy will
  wipe it live.
- [ ] **Re-run the go/no-go list in DEMO_DAY_RUNOFSHOW.md against whichever
  environment you pick** — `/health` check, sign-in, seeded rulebook +
  documents, one clean + one flagged voucher so Saved Checks isn't empty.

---

## 3. Worth deciding before the pitch

- [ ] **Bank Verify is still in the rehearsed demo script** (Step 3 of
  DEMO_DAY_RUNOFSHOW.md). You asked the new Miro boards to leave out
  Attendance & Payment entirely — worth deciding whether the live demo flow
  should also drop Bank Verify to match that positioning, or whether it
  stays in the live walkthrough even though it's out of the explainer boards.
- [ ] **Power Automate / Outlook approvals** — the DOCex side is fully built
  (`approval_webhook.py`, `/compliance/approval-callback`), but the actual
  3-step flow has to be built **inside TA Connect's Microsoft 365 tenant**
  (needs their IT + a Power Automate licence). Not a blocker — the
  magic-link email flow is the working fallback — but don't claim it's live
  end-to-end unless that flow has actually been built on their side.
- [ ] **Observability (DEVOPS_ROADMAP Module 6) isn't built** — no
  CloudWatch dashboards/alarms yet. Not demo-visible, but if asked "how do
  you know if it's down," the honest answer today is "I'd notice manually."

---

## 4. Day-of checklist (from DEMO_DAY_RUNOFSHOW.md — adapt to your chosen environment)

- [ ] Backend `/health` returns 200
- [ ] Sign-in lands cleanly, no red errors
- [ ] Compliance rulebook list renders
- [ ] Instance is seeded: 1 rulebook, 2–3 Knowledge docs, 1 clean + 1
  flagged/blocked voucher
- [ ] Loom fallback of the main flow open in a hidden tab (connectivity insurance)
- [ ] Notifications off, browser full-screen, extra tabs closed
- [ ] Rehearse the close: "Screening a 200-applicant cycle goes from weeks of
  reading to an afternoon of review — every answer cited, every approval
  defensible."

---

## 5. New assets for this round of demos

Four Miro boards built to explain the product (Attendance & Payment and Bank
Verify intentionally excluded, per your instruction):

1. **Product Overview & Problem** — the "why," what DOCex does, the three
   core capabilities (Extraction, Knowledge Hub, Compliance)
2. **Core Workflow Walkthrough** — Extraction flow and Compliance flow, step by step
3. **Data Model & RAG Pipeline** — the core data models, confidence levels,
   and how the Knowledge Hub answers with citations
4. **Target Users & Use Cases** — the five segments DOCex serves and what
   each one asks it

(There's also a pre-existing **Architecture board** — linked from README.md —
covering the AWS/DevOps side; left untouched since it's already
infrastructure-focused, not a product explainer.)
