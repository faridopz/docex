# Stream B1 — Monitoring Agent (Daily Code Health)

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read: `/PLAN.md`, `/CLAUDE.md`, this file.

## What this stream delivers

A scheduled agent that runs every morning at 7am, reads the last 24h
of code activity + production errors + Self-Check results, and writes
a short briefing for Farid:

- What changed in the last 24h (commits, PRs)
- Self-Check status (22/22? Which ones flipped?)
- Production errors (if deployed)
- Test results trend
- ONE recommended next action

## Architecture

This runs INSIDE Cowork mode using the `mcp__scheduled-tasks__create_scheduled_task` tool, NOT inside the deployed app. The user (Farid) creates the schedule once and it runs autonomously.

### Schedule

`cronExpression: "0 7 * * *"` → 7am every day, in Farid's TZ (Africa/Lagos)

### Job prompt (this is what gets run by the schedule)

```
You are the DOCex monitoring agent. Today's briefing:

1. Read git log from /Users/faridabdurrahman/Desktop/docex for the
   last 24h. Summarise: how many commits, what areas of the codebase,
   any merge conflicts or reverts.

2. Run /admin/diagnostics against the local API (if reachable) and
   note which Self-Check items pass/fail. Highlight any that flipped
   from yesterday's status (compare to /diagnostics/{date}.json).

3. Read /diagnostics/latest.json — if it doesn't exist yet, skip.

4. Read the last 24h of usage_events.jsonl (if exists) — count
   significant events: runs, approvals, escalations, errors.

5. Read GitHub Issues + PRs via the GitHub MCP (if available).
   Highlight any open PR with a "needs-review" label or any new issue
   with a "bug" label.

6. Write a single-screen briefing to /diagnostics/briefing-{date}.md:
   - 5 bullet points of what happened
   - 1 line on Self-Check status
   - 1 line per production error category (if any)
   - 1 RECOMMENDED ACTION for today

7. Save the briefing AND text Farid a summary via the available
   email / Slack / Notion connector (whichever is set up).
```

## Setup

Farid runs this once in Cowork mode:

```
"Schedule the DOCex monitoring agent every day at 7am using the prompt
in /Users/faridabdurrahman/Desktop/docex/prompts/monitoring-agent.md"
```

The agent will use the scheduled-tasks MCP to register the cron.

## Definition of done

- [ ] Schedule is registered and visible in `list_scheduled_tasks`
- [ ] First briefing fires at 7am next morning
- [ ] Briefing written to `/diagnostics/briefing-{date}.md`
- [ ] Notification sent (email or Notion page) with the summary
- [ ] Briefing format is one-screen, scannable in 30 seconds

## Out of scope

- Production monitoring (Sentry, Datadog) — separate stream once deployed
- Auto-fix bugs — read-only agent, never writes code
- Multi-engineer team briefings — single-user for now

## Failure modes to handle

- If API isn't running locally, note it and skip the diagnostic
- If git log shows no activity, just say so (don't pad)
- If briefing fails to send, write to disk anyway so Farid can find it
