# Stream A1+A2 — Auth + User Caps

**Paste this into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

You're picking up the auth + user-cap stream of DOCex. Before writing
any code, read these in order:

1. `/PLAN.md` — overall product plan
2. `/CLAUDE.md` — coding conventions
3. `/SOUL.md` — product values
4. This file

## What this stream delivers

A working sign-in flow that gates the app, plus per-tier usage caps
that map to the pricing on the landing page. After this, a stranger
hitting the landing can: sign up → land in `/onboarding` (handled by
A3) → run something → hit a soft cap → see the upgrade prompt.

## What already exists

- Three Co-Pilots are live: Sub-award, Programs (Attendance Payment),
  Compliance
- File-based JSON persistence at `verifications/`, `attendance_runs/`,
  `rate_cards/`, `decks/`, `diagnostics/`, `checks/`
- Self-Check Agent admin-gated via `ADMIN_SECRET` env var
- The landing page (`/web/app/page.tsx`) shows three tiers via the
  closing CTA — Free, Pro $99, Enterprise $299. No pricing page yet.
- Pricing: 3 sessions/month free, unlimited pro

## What to build

### Backend (FastAPI)

1. **Auth provider — Supabase Auth.**
   - Supabase project: create one named `docex-prod` (Farid will create
     and put the keys in `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
     `SUPABASE_SERVICE_ROLE_KEY`)
   - Add `auth_dependency.py` in `/api` with a `current_user` FastAPI
     dependency that validates the Bearer JWT against Supabase
   - Add `users` table in Supabase with: `id` (uuid, fk auth.users),
     `email`, `org_name`, `tier` (enum free/pro/enterprise), `created_at`
   - Every existing endpoint gets `user: User = Depends(current_user)`
     unless explicitly public (the diagnostic stays admin-gated)

2. **Usage caps.**
   - Add a `usage` table: `user_id`, `month_yyyymm` (varchar 7),
     `sessions_used` (int default 0), `bank_verifications_used`,
     `compliance_checks_used`, `extractions_used`
   - Cap helper `check_quota(user, primitive) -> bool` in
     `/api/quota.py` — returns true if within cap, false if over
   - Tier caps:
     | Tier        | Sessions | Bank verifications | Compliance checks | Extractions |
     | ----------- | -------- | ------------------ | ----------------- | ----------- |
     | Free        | 3        | 25                 | 10                | 25          |
     | Pro         | ∞        | 500                | 500               | 1000        |
     | Enterprise  | ∞        | ∞                  | ∞                 | ∞           |
   - Every primitive route bumps the relevant counter on success
   - Soft-cap: return 402 PAYMENT REQUIRED with `{ "upgrade_url": "/billing", "reason": ... }`

3. **Persistence migration.**
   - All file-based JSON gets a `user_id` prefix in the path:
     `verifications/{user_id}/{batch_id}.json` etc.
   - Write a one-shot migration script `/scripts/migrate_to_user_dirs.py`
     that moves existing files into a synthetic `demo` user dir

### Frontend (Next.js)

1. **Auth UI.**
   - `/login` — email + magic-link via Supabase
   - `/signup` — same + org name field
   - `/account` — view current tier, monthly usage, upgrade button
   - `useUser()` hook in `web/lib/auth.ts` wrapping Supabase client
   - Middleware in `web/middleware.ts` redirects unauth users from
     `/app`, `/compliance`, `/agents/*`, `/verify`, `/knowledge` to
     `/login`. Landing `/` stays public.

2. **Quota indicators.**
   - Header chip on every gated page: "12 / unlimited" or "8 / 25"
   - When over cap, every "Run" button is disabled with a tooltip:
     "Monthly limit reached — upgrade to keep going"
   - `/billing` page with the three tiers and a Stripe payment link
     (Stripe Payment Link, not full Checkout — fastest to ship)

3. **Friendly errors.**
   - Existing `web/lib/errors.ts` already has `friendlyError()` — add a
     402 case that auto-redirects to `/billing` after 2s with a toast

## Out of scope (do not do)

- SSO (Google, GitHub) — not needed for pilots
- Team seats / multi-user orgs — that's Phase 3
- Stripe Checkout flow — use Payment Links for now
- Email digests — separate stream

## Definition of done

- [ ] A new visitor can sign up, get a magic link, land in `/onboarding`
- [ ] Free user can run 3 bank verifications, gets blocked on the 4th
      with the upgrade prompt
- [ ] Pro user (set manually in Supabase) has no caps
- [ ] All existing data is namespaced under user dirs, no leaks
- [ ] Diagnostic still admin-gated and returns 404 to unauth
- [ ] No regression on existing flows — Self-Check passes 22/22

## Testing checklist

```bash
# 1. Sign up flow
open http://localhost:3000/signup
# fill form → check email → click magic link → land in /onboarding

# 2. Quota
# As free user: run 3 verifications, 4th must return 402

# 3. Tier bump
# As admin in Supabase: update users.tier to 'pro'
# Reload → quota shows unlimited
```

## Files to touch (predicted)

```
/api/auth_dependency.py          NEW
/api/quota.py                    NEW
/api/main.py                     add auth middleware
/api/*_routes.py                 add Depends(current_user) everywhere
/scripts/migrate_to_user_dirs.py NEW
/web/lib/auth.ts                 NEW
/web/middleware.ts               NEW
/web/app/login/page.tsx          NEW
/web/app/signup/page.tsx         NEW
/web/app/account/page.tsx        NEW
/web/app/billing/page.tsx        NEW
/web/lib/errors.ts               add 402 case
/web/lib/api.ts                  add Authorization header
.env.example                     add Supabase vars
```

## Commit pattern

Small commits per area: `auth: supabase JWT validator`, `auth: signup
UI`, `quota: schema + middleware`, `quota: 402 friendly error`, etc.
