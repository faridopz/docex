# Stream A4 — Self-Learning Recommender

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex` AFTER auth (A1+A2) and onboarding (A3) are shipped.**

---

Read in order: `/PLAN.md`, `/CLAUDE.md`, `/SOUL.md`, `/prompts/auth-and-user-caps.md`, this file.

## What this stream delivers

An admin-facing dashboard at `/admin/insights` (gated by `ADMIN_SECRET`,
same as Self-Check) that tells Farid:

1. Which Co-Pilots are getting USED vs ignored, per tier
2. Where users get STUCK (drop-off in flows, abandoned uploads)
3. Which RULE TYPES flag most often across all compliance checks
4. Which DOC TYPES users upload most (so we know which to optimise next)
5. Concrete PRODUCT RECOMMENDATIONS Claude wrote based on the data above

This is the meta-layer Farid asked about: "give me product
recommendations based on usage."

## Architecture

### 1. Event collection (already partially in place)

Every primitive run already creates a result JSON (`checks/`,
`verifications/`, etc). After auth lands, those are under
`{user_id}/`. We don't need a separate events table for v1 — just
read the files.

Add a small `usage_events.jsonl` per user: one line per significant
action (`run_check`, `approve`, `escalate`, `upload_file`,
`hit_quota`). Append-only, never deleted.

### 2. Daily roll-up

Cron job at 2am runs `/scripts/usage_rollup.py`:

- For each user: count actions in last 24h
- For the org: count actions across all users
- Identify users who signed up but did 0 actions in last 7d
- Identify users who hit quota in last 24h
- Identify users on free tier with >50% utilisation (upgrade target)
- Save to `analytics/{yyyymmdd}/rollup.json`

### 3. Claude product recommender

Once a week (Sunday 6pm) `/scripts/weekly_recommend.py` runs:

- Loads last 7 days of rollups
- Loads usage of each primitive
- Loads which compliance rules flag most (cross-user, anonymised)
- Feeds the whole bundle to Claude Sonnet 4.6 with this prompt:
  > "You are advising the founder of DOCex. Based on this week's
  > usage, what are the top 3 product recommendations? Be specific,
  > cite numbers from the data, prioritise by impact."
- Saves Claude's response to `analytics/{week}/recommendations.md`
- Emails it to Farid

### 4. Admin insights page

`/admin/insights` shows:

| Section                   | Content                                         |
| ------------------------- | ----------------------------------------------- |
| Active users (7d / 30d)   | Number + sparkline                              |
| Co-Pilot adoption         | Per Co-Pilot: % of users who ran it once        |
| Drop-off funnel           | Signup → first run → second run → invited team  |
| Quota-bound users         | Free users at >50% — upgrade targets            |
| Common rule flags         | Top 10 rule types that flag, % of checks        |
| Common doc types          | What people upload most (extension + size)      |
| Claude recommendations    | Last week's auto-generated rec doc, rendered    |

## Privacy guardrails (CRITICAL)

- Roll-ups NEVER include document content, just counts and metadata
- Anonymised cross-user data ONLY (no "User X did Y")
- User-facing: an /account opt-out toggle for analytics (default-on for
  Free tier, default-off for Enterprise)
- All raw events stay in the user's own dir, never copied

## Files to touch

```
/api/usage_events.py                       NEW
/scripts/usage_rollup.py                   NEW
/scripts/weekly_recommend.py               NEW
/web/app/admin/insights/page.tsx           NEW
/web/components/admin/MetricCard.tsx       NEW
/api/admin_routes.py                       add /insights endpoints
```

## Definition of done

- [ ] Every primitive run appends to usage_events.jsonl
- [ ] Daily rollup writes `analytics/{date}/rollup.json`
- [ ] Weekly recommender writes a markdown rec doc + emails Farid
- [ ] `/admin/insights` renders all 7 sections
- [ ] All data privacy-checked: no document content, no cross-user leaks
- [ ] User can opt out via /account toggle

## Out of scope

- Real-time analytics (overkill)
- Per-pixel session replay (creepy, expensive)
- A/B testing infrastructure (premature)
- Funnel analytics product like PostHog (we own the data, no need)
