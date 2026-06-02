# Stream C5 — GitHub ↔ Notion ↔ Claude Code ↔ Debugger Link

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read: `/PLAN.md`, this file.

## What this stream delivers

Quality-of-life infrastructure so that:

1. Every GitHub commit/PR creates a Notion task row under DOCex >
   Engineering > Commits
2. Every GitHub Issue mirrors into Notion under DOCex > Engineering >
   Issues
3. Claude Code in the repo automatically tags work to the matching
   GitHub Issue (commit message conventions)
4. Errors caught by Sentry (or equivalent) auto-create a Notion bug row

## Setup needed

- Notion connector authorised (done this session)
- GitHub connector authorised (Farid to do — `Settings > Connectors >
  GitHub`)
- Sentry (or chosen error tracker) — Farid to pick

## Build steps

### 1. GitHub → Notion mirror

Option A — built-in Notion automations:

- In Notion, go to DOCex > Engineering > Commits database
- Add automation: "When new GitHub commit on `farid/docex` → create row"
- Properties: commit SHA, message, author, files changed (linked),
  date

Option B — code-side webhook (if Notion automations don't work):

- GitHub Actions workflow `.github/workflows/notion-sync.yml`
- On push: POST to Notion via the Notion API
- Needs `NOTION_API_KEY` GitHub secret

### 2. Issue mirror

Same pattern. DOCex > Engineering > Issues database. Issue body
mirrored as Notion page content.

### 3. Commit message convention for Claude Code

Document in `/CLAUDE.md`:

```
Commit messages follow this format:

  <type>: <short summary> (#<issue-number>)

Types: feat, fix, docs, test, refactor, chore, perf
Issue number references the GitHub issue this commit resolves
or contributes to. Always include if it exists.

Example: "fix: rapidfuzz scorers handle case-folded names (#42)"
```

This makes the Notion mirror automatically link commits to issues.

### 4. Error tracking

If picking Sentry:

- `pip install sentry-sdk[fastapi]` in `api/requirements.txt`
- `Sentry.init(...)` in `api/main.py` with `SENTRY_DSN` from env
- Sentry issue alerts → Notion via Sentry's Notion integration

If picking the simpler route: just send unhandled exceptions to
Notion DOCex > Engineering > Bugs directly.

### 5. Notion engineering databases needed

Build these in DOCex > Engineering teamspace:

| Database     | Schema                                                       |
| ------------ | ------------------------------------------------------------ |
| Commits      | SHA, Message, Author, Branch, Date, Files                    |
| Issues       | Number, Title, Status, Labels, Author, Created, Last update  |
| Pull requests| Number, Title, Status, Reviewer, Created, Merged             |
| Bugs         | Title, Stack trace, Severity, Status, First seen, Last seen  |

## Files

This stream is mostly Notion + GitHub MCP / webhook orchestration.
Code added:

```
.github/workflows/notion-sync.yml         NEW (push/issue mirror)
.github/workflows/issue-sync.yml          NEW (issue mirror)
api/main.py                               sentry init
api/requirements.txt                      sentry-sdk[fastapi]
CLAUDE.md                                 commit message convention
```

## Definition of done

- [ ] Pushing a commit to GitHub creates a row in Notion Commits within
      60 seconds
- [ ] Opening a GitHub issue creates a Notion Issues row
- [ ] An unhandled error in production sends a row to Notion Bugs
- [ ] Claude Code's commits follow the convention

## Out of scope

- Bidirectional sync (Notion changes do NOT propagate back to GitHub)
- Slack mirror (separate stream if needed)
- Custom dashboards (Notion is the dashboard)

## Anti-patterns

- DON'T mirror EVERY commit comment to Notion — noise. Just commits
  + issues + PRs.
- DON'T sync customer-content errors to Notion — privacy. Strip
  identifiers first.
