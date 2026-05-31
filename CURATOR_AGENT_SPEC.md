# Curator Agent — Spec

The agent that makes DOCex's Knowledge Hub *alive* rather than just searchable.

## The thesis

Today's Knowledge Hub is reactive — it answers when asked. Other knowledge tools (SharePoint, Google Drive, Notion) are even more passive — they just store. The Curator Agent is what makes DOCex categorically different: **a librarian that watches your library and proactively keeps it healthy, surfaces connections, and tells you what's worth your attention.**

A SharePoint with AI search is incremental. A Curator Agent is the moat.

## What it does (V1 — observe + suggest, never act without permission)

Five capabilities, each shipping value on its own. Listed in build-order priority.

### 1. Welcome briefing on upload
When any document lands in the library, within ~5 seconds the Curator returns:
- 2-3 sentence executive summary
- 3-5 key takeaways
- Proposed folder (already partially built as `/folders/suggest`)
- "Related to" — names 1-3 existing library documents this overlaps with
- Suggested tags pulled from content

UX: appears as a small inline card on the document detail page within seconds of upload finishing. Click "Accept all" to apply folder + tags in one click.

**Why it matters:** the user who just uploaded 12 documents feels productive immediately. The library becomes warm the moment the last file finishes.

### 2. Near-duplicate detection
When a new document is similar to an existing one (>70% content overlap), the Curator flags it:
> "This proposal looks very similar to *Health Initiative Abuja — Original Proposal* uploaded 3 weeks ago. Is this a revision or a separate document?"

Two actions offered: "Mark as revision of X" (links them, supersedes old) or "Keep as separate document."

**Why it matters:** NGO knowledge bases rot from version chaos. The Curator prevents the rot.

### 3. Stale document watcher
A scheduled scan (weekly) identifies documents that haven't been touched in N months AND whose content references dates / policies / commitments that may have superseded them. Surfaces in a weekly digest:
> "*WGCEO Anti-Fraud Policy* hasn't been opened in 14 months. It references the 2022 procurement standard. Has it been superseded?"

Two actions: "Mark as current" (resets the clock) or "Archive."

**Why it matters:** auditors ask "is this still your current policy?" The Curator answers proactively.

### 4. Cross-reference mapping
After parsing, the Curator extracts named entities (policies referenced, partners named, projects cited) and stores them as lightweight metadata. The detail page gets a new section:
> **Referenced in this document:**
> - Anti-Fraud Policy → 4 documents reference this
> - Gates Foundation INV-043440 → 7 documents
> - CHAI Gombe → 2 documents

Click any reference to see all related documents. **No knowledge graph required** — just per-document entity tags + reverse-index queries.

**Why it matters:** "show me everything we have on the Gates INV-043440 grant" becomes one click. That's the Sydani moment.

### 5. Weekly digest
Every Monday morning, the Curator emails the user (or surfaces in-app):
> **This week in your library**
> - 4 new documents added (summarised below)
> - 2 stale documents flagged
> - 1 near-duplicate detected
> - 3 documents in *Reports/2026* updated
> - Most-queried topics this week: PPH coverage, vendor verification, sub-grant approval

**Why it matters:** the Curator becomes a permanent presence — a quiet teammate who keeps the librarian work moving without anyone asking.

## What it does NOT do (V1)

Deliberately ruled out for the first build to keep scope honest:
- Edit document content
- Move documents without user confirmation
- Send emails to external partners
- Make compliance judgments
- Generate new documents (drafting concept notes is a Phase 2 separate agent)
- Replace the Knowledge Hub chat — the Curator is the librarian, the Hub chat is the analyst

## Technical scope

Mostly composes what we already built. New code is small.

| Capability | Backend work | Frontend work | Cost |
|---|---|---|---|
| Welcome briefing | New `curator.welcome(deck)` function. ~1 Claude call. | Inline card on detail page. | ~2 hours |
| Near-duplicate detection | Compare new deck to top-K existing via Claude (or pgvector when corpus > ~30 docs). | Modal on upload completion. | ~half day |
| Stale watcher | Weekly cron. Read decks where `updated_at` > 6 months. Score staleness. | Surface in weekly digest + library badge. | ~half day |
| Cross-reference mapping | Entity extraction on upload (Claude call). Store on deck as `referenced_entities: list[str]`. | "Referenced in" section on detail page. Reverse-index endpoint. | ~1 day |
| Weekly digest | Background job. Aggregate week's events. Send via existing notifications.py. | Optional in-app digest page. | ~1 day |

**Total V1 build: 3-4 days of focused work.**

## When to build

After the first paying pilot signs. The Curator's value compounds with library size — building it for one-user-with-3-decks proves nothing. Building it for TA Connect (or Sydani) once they've uploaded their first 50 documents shows the magic.

## How it changes the sales pitch

Add one bullet to the Knowledge Hub section of the proposal:

> **Curator Agent**: DOCex doesn't wait for you to ask. The Curator watches your library — proposes folders, flags duplicates, surfaces what's stale, and emails you a weekly digest of what changed and what's worth attention. Your knowledge base stays clean without anyone curating it.

That single bullet is what separates DOCex from every other "AI document search" in the market. **No one else is doing proactive curation for NGOs.**

## V2 (post-Curator launch)

Once V1 lands and we have data on what users accept vs reject:
- Auto-folder / auto-tag (skip the confirmation step for high-confidence suggestions)
- Cross-corpus pattern detection ("you've uploaded 5 proposals — here's the structural template that recurs")
- Concept-note drafting ("based on the 3 most successful past proposals, here's a draft for this RFP")
- Connector triggers (watch a Google Drive folder, ingest new files automatically)

But V1 first. Land the proactive layer. Earn the right to act, not just suggest.
