# DOCex — Prompt Pack

Paste-ready context+task docs for each big stream in `/PLAN.md`. Open a
new Claude Code session, paste the doc, and execute.

Each prompt assumes the agent will read `/PLAN.md` and `/CLAUDE.md`
first (the prompt tells them to). Don't shortcut this — it's the
context that prevents speculative work.

## How to open a stream

```
1. Open Claude Code in /Users/faridabdurrahman/Desktop/docex
2. Paste the contents of the matching prompt below
3. Approve tool calls as Claude works
4. When done, commit with the stream name in the commit message
```

## Streams

| File                            | Stream                        | Est. effort |
| ------------------------------- | ----------------------------- | ----------- |
| `auth-and-user-caps.md`         | A1+A2 — auth + quotas         | 3 days      |
| `onboarding-agent.md`           | A3 — onboarding agent         | 2 days      |
| `self-learning-system.md`       | A4 — usage analyser           | 4 days      |
| `ui-overhaul.md`                | A5 — Spotify-grade UI         | 5 days      |
| `monitoring-agent.md`           | B1 — daily code monitor       | 2 days      |
| `sales-agent.md`                | B2 — outbound + CRM           | 3 days      |
| `ops-agent.md`                  | B3 — back-office ops          | 3 days      |
| `demo-artifact-agent.md`        | B4 — ephemeral demo data      | 2 days      |
| `github-notion-link.md`         | C5 — dev infra integration    | 1 day       |

## Order Farid recommends

1. **`auth-and-user-caps.md`** — gates everything else (you can't onboard
   users without sign-in)
2. **`onboarding-agent.md`** — first thing a new user touches
3. **`demo-artifact-agent.md`** — unblocks better demos immediately
4. **`ui-overhaul.md`** — wins the demos
5. **`sales-agent.md`** — drives pipeline once UI is presentable
6. **`monitoring-agent.md`** — runs in background, no rush
7. **`self-learning-system.md`** — needs real usage data first
8. **`ops-agent.md`** — needs revenue first
9. **`github-notion-link.md`** — quality-of-life, do whenever
