# Client Onboarding Runbook

**What this is:** the exact steps from first call to go-live. Follow it in
order. No strategy here — that's `DELIVERY_PLAYBOOK.md`. This is the doing.

**Time:** about 3 weeks for a normal client. Longer if they need features that
don't exist yet.

---

## The idea in one picture

```
        ONE ENGINE (never copied, never forked)
                     │
   ┌─────────────────┼─────────────────┐
   │                 │                 │
neem.json        eva.json        client3.json      ← config files
   │                 │                 │
NEEM's system    EVA's system    Client 3's system
```

Each client gets their own config file and their own instance. They all run the
same code. When you improve the code, everyone improves.

---

## Step 1 — Collect (2–3 days)

**Goal:** get their documents. Not their opinions — their documents.

Ask for:

- [ ] Their finance/procurement policy (the signed PDF)
- [ ] Their approval matrix — who signs off on what amount
- [ ] Their org chart or department list
- [ ] 10 real receipts and invoices (blurry ones included — those are the useful ones)
- [ ] A bank statement (one month, they can redact it)
- [ ] Their grant/project codes with start and end dates
- [ ] Their last audit report, if they'll share it

> **Why documents, not conversation:** people describe the process they *think*
> they run. The policy says what they agreed to. The receipts show what actually
> happens. Where those three disagree is where your product earns its money.

Run the discovery questions alongside (`NEEM_DISCOVERY.md`). Ask eight, not
twenty-five. Let them talk.

---

## Step 2 — Sort every requirement into a bucket (half a day)

Go through everything they said and asked for. Put each item in one of three
columns. **Do this before writing anything.**

| Bucket | Test | Example |
|---|---|---|
| **CONFIG** | Can it be a value in their JSON? | "Our ceiling is ₦2m" |
| **FEATURE** | Would another client plausibly want it? | "Block payments outside the grant period" |
| **CUSTOM** | Only they will ever want it? | "Export to our 2009 Tally build" |

Rules:

1. **Default to CONFIG.** Most things are.
2. **Prefer FEATURE over CUSTOM.** If two clients might want it, build it into
   the engine behind a flag. You build once, sell many times.
3. **CUSTOM gets quoted separately.** Always. It's a one-time build fee.
4. **If you can't classify it, you don't understand it yet.** Go back and ask.

Write the list down. It becomes the scope in your proposal.

---

## Step 3 — Write their config file (half a day)

```bash
cp profiles/_template.json profiles/<client>.json
```

Fill in from their documents:

| Section | Comes from |
|---|---|
| `departments` | Their org chart |
| `state_owners` | Who handles each stage |
| `workflow.steps` | Their approval matrix — who signs at what amount |
| `workflow.max_amount` | Their spending ceiling |
| `allowed_categories` | What they actually buy |
| `required_documents` | What must be attached before payment |
| `grants` | Their agreements, with real start/end dates |
| `admin` | Their finance lead |
| `features` | Which flags to turn on |

Then check it:

```bash
python3 org_config.py validate profiles/<client>.json
```

Fix anything it complains about. It catches the mistakes that would strand a
payment somewhere nobody can see it — a step routed to a department that
doesn't exist, an override limit that could never fire.

> **Anything you're unsure about, mark `_todo` and ask them.** Never guess a
> financial threshold. A wrong ceiling is worse than an empty one.

---

## Step 4 — Build the FEATURE items (varies)

Only for things in bucket 2. Skip this step if their needs are all config.

For each feature:

1. **Write down what "done" looks like first** — the acceptance criteria
2. **Write the tests from that list**
3. **Then write the code**
4. **Put it behind a feature flag** from the very first commit
5. **Check the flag both ways** — on, it works; off, it's invisible
6. **Run all suites** before moving on

Example:

```
Feature    Vendor TIN validation
Flag       tin_verification
Done when  · valid TIN accepted and stored
           · malformed TIN → WARNING, never blocks payment
           · missing TIN → WARNING, finance decides
           · flag off → check doesn't appear at all
           · report lists every vendor, TIN present or absent
Estimate   2 days
```

**The flag is what keeps one engine serving many clients.** No flag means
client two sees a screen built for client one's process.

---

## Step 5 — Set up their instance (half a day)

One instance per client. Not shared. (`PRODUCTION_READINESS.md` explains why.)

```bash
# 1. Create the service on your host, with a persistent disk

# 2. Set the environment
DOCEX_ORG=<client>
DOCEX_DB=/data/docex.db
ANTHROPIC_API_KEY=...
AUTH_SECRET=...              # set explicitly, back it up
DOCEX_SIGNING_KEY=...        # signs the audit chain — NEVER rotate this
ALLOWED_ORIGINS=https://<their-frontend>
SENTRY_DSN=...

# 3. Apply their config
DOCEX_ORG=<client> DOCEX_DB=/data/docex.db \
  python3 org_config.py apply profiles/<client>.json

# 4. Check it landed
DOCEX_ORG=<client> DOCEX_DB=/data/docex.db \
  python3 org_config.py describe
```

Then, before anyone logs in:

- [ ] Backups running daily
- [ ] **One backup actually restored** — an untested backup isn't a backup
- [ ] Sentry receiving events
- [ ] Uptime monitor alerting your phone
- [ ] Data survives a redeploy (create a record, redeploy, check it's still there)

---

## Step 6 — Test with their real data (1 week)

They use it. You watch and fix.

**Daily:** they send a short note — what worked, what broke, what was confusing.
**You reply the same day.**

**Log every issue** with a severity:

| | Meaning | Fix by |
|---|---|---|
| 🔴 Critical | Blocks their work | Today |
| 🟠 High | Painful workaround exists | This week |
| 🟡 Medium | Minor annoyance | Next release |
| 🟢 Low | Cosmetic | Eventually |

**Friday call:** show what you fixed, ask what to prioritise next.

**Sort every issue back into the buckets.** A confusion report might be config
(their profile is wrong), a feature (the UI is unclear for everyone), or just
documentation. Route it — don't just patch it.

---

## Step 7 — Go live (1 day)

Checklist:

- [ ] All critical and high issues closed
- [ ] Staff trained (2 hours, hands-on)
- [ ] One-page "how to use this" written for them
- [ ] Security & Compliance Summary handed over
- [ ] Backups tested again
- [ ] They know how to reach you

---

## Step 8 — Close out (half a day)

**Write the report.** Issues found and fixed, performance numbers, before-and-after.

**Get a quote from them.** One or two sentences about what changed.

**Ask for referrals.** Not a hard sell:

> "Do you know other organisations with the same problem we just solved?"

**Update `MASTER_CONTEXT.md`** — what you learned, what you decided, anything
that changes how you'd do the next one.

> That report and that quote are what sell the *next* client. Without them
> you're cold calling forever.

---

## What every client leaves behind

1. `profiles/<client>.json` — their config, in version control
2. Any FEATURE work — flagged, tested, **available to every future client**
3. A close-out report and a testimonial
4. A Security & Compliance Summary
5. An updated `MASTER_CONTEXT.md`

**After three clients** you have a proven engine, three case studies, a feature
set nobody else in this market has, and onboarding that takes days instead of
weeks. That repeatability is the asset — not the code.

---

## Where each client stands right now

| | NEEM | EVA |
|---|---|---|
| Step 1 Collect | ✅ demo done, docs coming Sep 10 | ✅ 18 policy PDFs in hand |
| Step 2 Sort | ⏳ after Sep 10 | ✅ done (`EVA_BUILD_SPEC.md`) |
| Step 3 Config | ⏳ scaffolded, needs their numbers | ⏳ scaffolded, needs their numbers |
| Step 4 Features | 2 to build (TIN, reconciliation) | ~6 engines to build |
| Step 5 Instance | ❌ **blocked — free tier wipes data** | ❌ not started |
| Steps 6–8 | not started | not started |

**NEEM's blocker is Step 5, and it's configuration, not code** — 2–3 days of
work in `PRODUCTION_READINESS.md`.

**EVA's is Step 4** — real engine work, but every piece of it also makes NEEM's
system better.

---

## The two rules that matter most

**1. Never write a client's name into engine code.**
If you catch yourself typing `if org == "eva"`, stop. That's a config field or
a feature flag. Three of those and you've forked the codebase without deciding to.

**2. A live client beats a future feature.**
If EVA work threatens NEEM's go-live, EVA waits. Every time.
