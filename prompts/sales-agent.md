# Stream B2 — Sales Agent (Outbound + CRM Hygiene)

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read: `/PLAN.md`, this file. Also confirm the Notion Sales CRM
database exists (created during this session — URL in PLAN.md or in
Farid's Notion workspace under DOCex > Sales).

## What this stream delivers

A semi-autonomous agent (runs on schedule + on-demand) that:

1. Researches a target prospect (NGO, foundation, INGO, programs team)
2. Drafts a personalised outbound email tying their work to a specific
   DOCex Co-Pilot
3. Logs the contact in the Notion Sales CRM
4. Tracks reply state and bumps stale prospects
5. Generates a weekly pipeline report for Farid

This is NOT a spam-bot. Every email is hand-approved before send.

## Setup needed (one-time)

- Notion connector authorised (done this session)
- Email connector — Gmail recommended (already authorised this session)
- Sales CRM Notion database (created this session — see PLAN.md)

## Agent capabilities

### 1. Prospect research

Given a target name (e.g. "Health Strategy and Delivery Foundation"):

- Web-search for: about page, mission, recent grants, team size, country
- Identify the relevant role (sub-award officer, finance director,
  programs lead) and their LinkedIn
- Identify which DOCex Co-Pilot fits their workflow best
- Save findings as a Notion page under DOCex > Sales > Research >
  {Company Name}

### 2. Email drafting

Generate a 4-paragraph outbound email:

1. Specific hook tied to their public work
2. The pain DOCex addresses (one sentence)
3. Concrete proof point — "X NGO compressed Y from Z weeks to Z hours"
4. Soft CTA — "want a 15-min screen-share"

Save as draft in Gmail (do NOT auto-send).
Log the draft URL to the Sales CRM row for that prospect.

### 3. Pipeline hygiene

Daily check on the Sales CRM:

- Prospects in "Sent" status with no reply > 7 days → bump email draft
- Prospects in "Demoed" status > 14 days → "any thoughts?" email
- Prospects in "Pilot scoping" > 30 days → check-in email
- New prospects added with no research → research-and-draft

All bump emails saved as drafts, never auto-sent.

### 4. Weekly pipeline report

Every Monday 9am:

- Read the Sales CRM
- Count prospects per stage
- Identify the next 3 highest-priority actions for Farid
- Write to Notion as a new page under DOCex > Sales > Weekly Reports
- Email Farid the link

## Notion CRM schema

(Already created — `Sales CRM` database under DOCex teamspace.)

| Property            | Type                                                  |
| ------------------- | ----------------------------------------------------- |
| Org name            | Title                                                 |
| Contact name        | Rich text                                             |
| Email               | Email                                                 |
| Role                | Rich text                                             |
| Country             | Select                                                |
| Stage               | Status (New, Researched, Drafted, Sent, Replied, Demoed, Pilot scoping, Signed, Lost) |
| Co-Pilot fit        | Multi-select (Sub-award, Programs, Compliance, KH)    |
| Last contact        | Date                                                  |
| Next action         | Rich text                                             |
| Draft email URL     | URL                                                   |
| Research notes URL  | URL                                                   |
| Owner               | Person                                                |

## Files / setup

This stream is mostly Notion + Gmail tool orchestration via MCPs. The
only code that lives in the repo:

```
/agents/sales/research_prospect.py   NEW (callable via Cowork mode)
/agents/sales/draft_outreach.py      NEW
/agents/sales/bump_stale.py          NEW (cron job target)
/agents/sales/weekly_report.py       NEW
```

These are utility scripts, not API endpoints — they call Anthropic
directly and write to Notion/Gmail via the MCPs.

## Definition of done

- [ ] Research script produces a Notion page given an org name
- [ ] Draft script produces a Gmail draft + logs to CRM
- [ ] Bump script identifies stale rows and drafts follow-ups
- [ ] Weekly report runs Monday 9am and emails Farid
- [ ] All emails are DRAFTS, never sent automatically
- [ ] First 10 prospects loaded into the CRM and researched

## Initial prospect list (Farid to populate)

1. TA Connect (Abuja, NG) — pilot in progress
2. Neem Foundation (Abuja, NG) — demo'd
3. Sydani (Abuja, NG) — knowledge hub interest
4. Health Strategy and Delivery Foundation (Abuja, NG)
5. Africa Health Budget Network
6. African Health Observatory Platform
7. Health Policy Plus
8. Mastercard Foundation
9. ELMA Philanthropies
10. Lagos State Trust Fund

## Anti-patterns

- DON'T auto-send any email. Drafts only.
- DON'T scrape paywalled content (academic journals, leaked docs).
- DON'T email-blast — one prospect at a time.
- DON'T fake personalisation. If you can't find a real hook, skip the prospect.
