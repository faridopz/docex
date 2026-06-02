# Stream A3 — Onboarding Agent

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex` AFTER `auth-and-user-caps.md` is shipped.**

---

Read in order:
1. `/PLAN.md`
2. `/CLAUDE.md`
3. `/SOUL.md`
4. `/prompts/auth-and-user-caps.md` (the auth flow you'll plug into)
5. This file

## What this stream delivers

A 4-step onboarding flow that runs once per user immediately after
sign-up, plus a smart background agent that watches the first 7 days
of usage and proactively coaches the user toward the "aha" moment for
their role.

## The 4-step onboarding flow

After magic-link sign-in, new user lands at `/onboarding`:

**Step 1 — "What's your role?"**
- Sub-award / Grants officer
- Programs / Events officer
- Compliance / Finance officer
- Procurement
- Something else (free-text)

**Step 2 — "What documents do you usually handle?"** (multi-select)
- Payment vouchers
- Grantee applications
- Attendance sheets
- Procurement quotes
- Quarterly reports
- Board decks / training slides
- Other (free-text)

**Step 3 — "Pick a starting point"** (1 click)
- Based on role+docs, show ONE recommended Co-Pilot prominently and
  the other two as "also available" small cards
- Pre-seed sample data for that Co-Pilot from `/demo_fixtures/`

**Step 4 — Drop them into the Co-Pilot with sample data loaded**
- The first run uses sample data, not their files
- An onboarding banner reads: "This is sample data — when you've seen
  the result, upload your own and re-run."

## The proactive onboarding agent

A background scheduled job (cron, or via the `schedule` skill once
deployed) that:

- Day 0: send welcome email (Resend or Supabase email) with quickstart link
- Day 1: if user hasn't run a real (non-sample) check, email "Need help
  uploading your first real file? Reply to this email." (replies go to
  Farid for hand-hold)
- Day 3: if user has run only one Co-Pilot, suggest the next one based
  on their stated role
- Day 7: send a personal "How's it going?" from Farid (template, but
  feels personal) — this is the conversion push to Pro

Implementation: a `/api/onboarding/state.py` module that computes
which event the user is "in" based on their usage row, plus a
`/scripts/onboarding_emailer.py` script run by cron.

## Files to touch

```
/web/app/onboarding/page.tsx                NEW
/web/app/onboarding/role/page.tsx           NEW (step 1)
/web/app/onboarding/docs/page.tsx           NEW (step 2)
/web/app/onboarding/start/page.tsx          NEW (step 3)
/web/components/onboarding/Banner.tsx       NEW (sample-data banner)
/api/onboarding_routes.py                   NEW (save profile + start)
/api/onboarding_emailer.py                  NEW (scheduled job)
/models.py                                  add OnboardingProfile
/web/types/index.ts                         mirror
```

## Definition of done

- [ ] New signup goes directly to `/onboarding` after magic-link
- [ ] Profile (role + docs) saved to Supabase `users` table
- [ ] One-click "Start with sample data" seeds the Co-Pilot
- [ ] Sample-data banner appears until user uploads a real file
- [ ] Cron job sends welcome email at signup
- [ ] Day 7 "how's it going" email fires automatically

## Out of scope

- Onboarding for existing pre-auth users (they get a one-time wizard
  prompt instead, handled by auth stream)
- Multi-language onboarding — English only for v1
- Video walkthroughs — text + screenshots only

## Anti-patterns to avoid

- DON'T require 6+ fields in onboarding. The bar is "less than 60
  seconds to first value."
- DON'T pre-fill demo data invisibly. Show the banner so users know
  what they're looking at.
- DON'T email-spam. Three emails over 7 days max.
