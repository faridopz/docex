# DOCex Skills — your operating system

Seven skills covering the work that recurs. They trigger automatically when the
situation matches, or you can invoke one by name.

## The set

| Skill | Fires when | What it does |
|---|---|---|
| **docex-prospect-prep** | Before a pitch or discovery call | Research, demo arc, the questions, the close |
| **docex-policy-to-profile** | A client sends policy PDFs | Drafts their profile with citations + a confirm list |
| **docex-client-onboarding** | New client, or a client asks for a change | CONFIG/CORE/CUSTOM triage → profile → build plan |
| **docex-build-feature** | Building something that doesn't exist | Classify → acceptance criteria → tests → flag → verify |
| **docex-go-live** | Deploying a client to production | The full gate: auth, durability, backups, secrets, rollback |
| **docex-client-checkin** | Weekly review, or a client reports something | Severity triage → route back through the buckets → update |
| **docex-margin-review** | Monthly, at renewal, before quoting | Real unit economics → raise, fix, or stop selling |
| **docex-incident** | Production is down or numbers look wrong | Triage → communicate → fix → write up → add the test |

## How they fit the year

```
PROSPECT              →  prospect-prep
  ↓ they send documents
CONFIGURE             →  policy-to-profile  →  client-onboarding
  ↓ they need something that doesn't exist
BUILD                 →  build-feature
  ↓ ready for real data
DEPLOY                →  go-live
  ↓ they're using it
RUN                   →  client-checkin  ·  incident (when it breaks)
  ↓ monthly
PRICE                 →  margin-review
  ↓ raise, refer, repeat
```

## Why seven and not twenty

Skills trigger on their descriptions. Twenty overlapping ones compete and fire
unpredictably — you end up with the wrong one, or none. Seven distinct stages of
one business cover the ground and stay reliable.

**Add another only when you notice yourself re-explaining the same process a
third time.** That is the real signal that something has become repeatable.

## What they encode

Each one carries the decisions that were expensive to learn, so they survive
being forgotten:

- **Never invent a number.** Unconfirmed values get a `_todo` and go on the
  confirm list. A guess looks like knowledge.
- **Never write a client's name into engine code.** Three of those and the
  codebase is forked without anyone deciding to.
- **Deterministic-first.** If being wrong produces a plausible wrong number
  rather than a crash, it is code, never a model call.
- **Prefer CORE over CUSTOM.** That is what turns one client's requirement into
  the next client's selling point.
- **A live client beats a future feature.** Every time.
- **`DOCEX_SIGNING_KEY` is never rotated.** It signs the audit chain.
- **An untested backup is not a backup.**
- **Speed is not the goal in an incident — trust is.**

## The one that matters most for growth

**`docex-client-onboarding`** is the first thing you hand to a hire. Config work
is a validated JSON file, so someone else can do it on day one and the validator
catches their mistakes. Engine work stays with you.

That split — config delegable, engine not — is what lets a second person carry
five clients while you do architecture and sales.

## The one that will save you money

**`docex-margin-review`.** Model spend is your largest variable cost and it
moves with client volume, not with your price. `usage.py` records it per org per
day. A client whose usage doubles quietly is a client whose margin disappears
quietly.

Run it monthly. Its purpose is not the number — it is forcing a decision: raise
a price, fix a leak, or stop selling something that does not pay.
