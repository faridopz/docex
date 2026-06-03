# DOCex — 2-Week Cleanup & Quality Action Plan

_Owner: Farid · Drafted: 3 June 2026 · Target: shippable, demo-able, sellable by 17 June 2026_

This plan organizes your notes + the ChatGPT input into a prioritized,
sprint-by-sprint program. It is scoped to your stated goal: **improve
flows, UI, process, and product quality** — not a re-architecture. Where I
disagree with the input, I say so plainly (see "Pushback").

---

## 0. The decisions that frame everything

Three product-truths from your notes that I'm treating as settled:

1. **DOCex screening side = extraction + deep analysis only.** The
   sub-award process does **not** do grantee payment verification.
   Screening, extraction, and document analysis is what the sub-award
   side sells.
2. **Payment/bank verification belongs to the Attendance flow** — plus a
   standalone one-off bank-check page (linked under Compliance) for people
   who just want a single lookup.
3. **"Programs Co-Pilot" → "Attendance & Payment Flow."** Save all
   attendance lists so repeat attendees can be reused.

Everything below serves one principle from your notes:

> **Every flow, every step must be clear and lead to solving the user's
> problem.** No step exists that doesn't move the user forward.

---

## 1. Pushback — where I'd diverge from the ChatGPT input

The ChatGPT research is strong on _positioning_ but pulls toward building a
much bigger company than two weeks allows. My honest read:

- **"Rebuild DOCex around a Cases model (Draft→Paid→Closed)" — not now.**
  It's the right long-term spine, but it's a multi-week rearchitecture. In
  a 2-week window it would blow up scope and leave you with a half-migrated
  product you can't demo. **Defer to post-pilot.** We can _borrow_ the
  vocabulary (status chips, single-thread query view) inside the existing
  Compliance check page without renaming the whole product.
- **Multi-channel intake (WhatsApp, shared drives, portal) — defer.**
  High value, zero relevance to the next two weeks. It's a Phase 3 bet.
- **Power Automate / one-click email approvals — partially yes.** The
  backend _already_ has escalation + clarification endpoints and an
  abstracted SMTP notification layer. We should surface those in the UI
  rather than build a new approval engine.
- **What I fully agree with:** the real pain is _visibility, chasing
  approvals, and Outlook chains_ — not "AI compliance checks." That should
  shape our copy and our query-thread UX now, even without the big rebuild.

Net: adopt the _insight_ (single-thread queries, email that closes the
loop, status clarity), reject the _scope_ (full Cases OS) for this sprint.

---

## 2. Issues inventory (from your notes → mapped to code)

| # | Your note | Where it lives | Severity |
|---|-----------|----------------|----------|
| A | Menus messy, navigation into features poor | No shared nav — each page hand-rolls its own header (`app/**/page.tsx`) | High |
| B | Sub-award Co-Pilot page is flawed; payment verify wrongly shown there | `app/agents/sub-award/page.tsx` (step 3 = bank verify) | High |
| C | "Tour the Co-Pilots" only tours sub-award | `app/page.tsx` CTA → `/agents/sub-award` | Med |
| D | "At a glance" block is irrelevant | `app/agents/sub-award/page.tsx` (Widgets) | Low |
| E | "Briefed by Claude / Built with Claude" — remove origin talk | `app/page.tsx` Assistant section + footer | Low |
| F | "ED-approved" → just "Approved" | 6 spots: `compliance/checks`, `compliance/page`, `VerdictScreen`, check detail | Low |
| G | Saved-checks page (`/compliance/checks/[id]`) inefficient back-and-forth | `app/compliance/checks/[id]/page.tsx` | Med |
| H | "Programs Co-Pilot" → "Attendance & Payment Flow"; save attendance lists | landing + `agents/attendance-payment/**` | Med |
| I | Standalone one-off bank check page, linked under Compliance | `app/verify/**` exists; needs surfacing | Med |
| J | Inbox page → make it "send email/alert to relevant parties (Outlook/Gmail)"; close the back-and-forth loop | `app/compliance/pending/page.tsx` + `notifications.py` + compliance escalate/clarify routes | High |
| K | Escalation should email parties (Outlook/Gmail) | backend routes exist; UI + provider wiring needed | High |
| L | Tour should be an immersive intro to ALL flows | new `/tour` or revamped landing section | Med |

---

## 3. The plan — two sprints

### Sprint 1 (Days 1–6): Navigation, clarity, quick wins

**Goal:** the product stops feeling messy. Every page shares one nav, every
label is honest, dead weight is gone.

1. **Shared `AppNav` component** (issue A). One header used by every
   in-product page: left = DOCex home, center = the four primitives /
   flows, right = context action. Kills the per-page hand-rolled headers.
   _This is the single highest-leverage fix._
2. **Copy/wording pass** (E, F): "ED-approved" → "Approved"; strip
   "Briefed by Claude" / "Built with Claude"; tighten any
   assistant-origin language.
3. **Fix the sub-award page** (B, D): remove bank-verify step (it's not
   part of sub-award), remove "At a glance" widgets, reframe the page as
   screening + extraction + quarterly review only. Decide: keep as a clean
   lifecycle shell **or** collapse it into a redirect to `/app` with the
   sub-award template. (Recommendation: keep, but slimmed.)
4. **Rename Attendance flow** (H): "Programs Co-Pilot" → "Attendance &
   Payment Flow" everywhere; verify the saved-attendance/repeat-attendee
   story is wired (it partially is via `attendance_runs/`).
5. **Surface standalone Bank Verify** (I): clear entry from Compliance for
   a one-off check; keep it linked, not buried.

**Test after each:** `cd web && npm run build` compiles; click through
`/`, `/app`, `/compliance`, `/agents/attendance-payment`, `/verify`.

### Sprint 2 (Days 7–12): Query loop + email, immersive tour

**Goal:** kill the Outlook back-and-forth pain; make the intro sell itself.

6. **Query Resolution thread** (G, J): turn the saved-check page into a
   single-thread view — compliance officer → "missing invoice" → reply →
   resolved, all in one place. Reuse existing escalate/clarification
   endpoints; render the decision log as a Slack-like thread.
7. **Provider-agnostic email layer** (J, K): the SMTP layer in
   `notifications.py` already abstracts Outlook/Gmail (it's just an SMTP
   host + creds). Wire escalation and clarification to send through it, log
   every send in the audit trail, and ingest the reply state back into the
   check. Start with: on escalate/clarify → email the named party with a
   one-click link back to the check.
8. **Immersive tour** (C, L): replace "Tour the Co-Pilots" (which only goes
   to sub-award) with a guided intro that walks all flows — extraction,
   attendance & payment, compliance, knowledge — each with a one-line "this
   solves X" and a live sample. Either a `/tour` page or an interactive
   landing section.

### Days 13–14: Verification & polish

9. Full click-through QA on every flow; fix loading/empty/error states.
10. Self-check / lint / build green. Commit per feature (per your rules).

---

## 4. Sequenced backlog (ordered by leverage)

1. Shared AppNav (unblocks all nav fixes)
2. Wording pass (ED-approved, Claude-origin copy)
3. Sub-award page slim-down + bank-verify removal
4. Attendance & Payment rename + saved-lists check
5. Standalone bank check surfaced under Compliance
6. Saved-check → single-thread query view
7. Email loop on escalate/clarify (Outlook + Gmail via SMTP)
8. Immersive multi-flow tour
9. QA + verification pass

---

## 5. Out of scope for these two weeks (parked, not forgotten)

- Full Cases lifecycle rebuild (Draft→Paid→Closed as product spine)
- Multi-channel intake (WhatsApp / shared drive / submission portal)
- Donor Readiness Score, Audit Pack Generator, Bottleneck Dashboard
- Supabase auth / persistence (already your Phase 2)

These are real and good — they're just not what makes the next demo land.

---

## 6. Working agreement (from CLAUDE.md)

- One file at a time; I show you before moving to the next big change.
- Never rewrite working code to fix one small thing.
- After each step, I tell you exactly what to run to test it.
- Commit after every working feature.
- When in doubt, do less, better.
