# QuickBooks — what exists today, and what a live API sync would actually cost

NEEM asked, in the original scoping conversation, whether DOCex can link to
their QuickBooks. Short answer: yes, a working handoff already exists and is
live for NEEM — but "linking to QuickBooks" can mean two very different
things, and it's worth being precise about which one this is before anyone
scopes the other one.

---

## What exists today: the CSV handoff

DOCex does not try to become a general ledger, and that is a deliberate
position, not a limitation we're working around. QuickBooks already
reconciles a bank account; what it cannot do is answer *who approved this
payment, under which policy, with what evidence* — there is no delegation of
authority inside QuickBooks, no policy check, no hash-chained trail. Someone
types an expense in and it's there. DOCex owns that front half — approval and
evidence — and hands off to QuickBooks for the books themselves.

Two exports do that handoff:

**1. The coded payment register.** Every approved, paid disbursement for the
month — vendor, amount, account, project/grant class, DOCex reference, bank
reference — ready to enter. Today someone re-types these into QuickBooks by
hand, which is both the slowest part of month-end and the place where the
QuickBooks entry quietly drifts from what was actually approved. This export
removes the re-typing: the entry says what the approval said.

**2. A QuickBooks-ready bank statement.** Nigerian banks (GTBank, Zenith,
etc.) cannot be connected to QuickBooks' own bank feeds, so NEEM already
downloads a statement and imports it by hand — and QuickBooks rejects exactly
what those files contain: ₦ symbols, comma thousands separators, title rows
above the header. DOCex already parses these properly for its own
reconciliation, so producing a clean file is close to free and removes a
monthly Excel chore nobody had flagged as a problem, because everyone assumed
it was just how bank statements are.

**Where this lives:** Settings → QuickBooks handoff, for any org with the
`accounting_export` feature on (NEEM has it on). An admin maps DOCex's spend
categories and project/grant codes to the organisation's real chart of
accounts — never guessed; an invented account name imports cleanly and posts
the money to the wrong place, which is a worse failure than an import that
simply refuses. The same screen shows what an export will contain before
anyone downloads it, names any spend category still unmapped, and downloads
both files.

**Status for NEEM specifically:** the mechanism is built, tested, and — as of
this week — verified against a real requisition carried through actual
approval and payment, confirmed to reach the export correctly coded,
including the QuickBooks Class column resolving from the payment's project
code (this took a real bug fix; see the commit history around
`accounting_export.py` for what was wrong and how it was verified). What's
still open is data entry, not code: nobody has yet entered NEEM's real
chart-of-accounts mapping — their `_account_codes`/`_project_codes` in the
profile are cashbook reference codes, not a QuickBooks account map, so
someone needs to sit down with NEEM's actual QuickBooks and decide what each
of their ~20 spend categories and ~13 project/grant codes should map to.
Fifteen minutes on that settings screen and the export is ready.

**Why CSV before API.** The QuickBooks Online API is the right long-term
integration, and this module is deliberately shaped so it can become the
write destination later — the account-mapping logic is already separate from
the export formatting. But the API needs an Intuit developer app, OAuth, and
NEEM's own QuickBooks credentials, none of which exist before that's
explicitly decided and set up. A file works today, with no access to anyone's
live accounting system, which is also a much easier thing for a finance lead
to say yes to on a first pass.

---

## Phase 2: a live QuickBooks Online API sync — what it would add, and what it costs

This is not something to build today. It's a scoped proposal, so that if
NEEM asks "can it just push straight into QuickBooks, no CSV at all," there's
a grounded answer rather than a guess — and it's a decision for Farid to
bring to NEEM, not a default upgrade path.

**What it would change.** Instead of an admin downloading a CSV once a month
and importing it, DOCex would write each paid disbursement directly into
QuickBooks via its API the moment it's paid — no monthly file, no import
click. It could optionally also *read* QuickBooks (its chart of accounts, to
keep the mapping screen's dropdown in sync automatically; its GL, for a
second reconciliation cross-check against QuickBooks' own view of the
books).

**What it takes to build:**

- **An Intuit developer app**, registered at developer.intuit.com, with
  separate Development (sandbox) and Production credential sets — the
  sandbox needs no approval and is where the integration gets built and
  tested; Production requires a self-assessment questionnaire and Intuit's
  review before it can touch a real company file.
- **OAuth 2.0**, Intuit's own flow: NEEM's admin authorises DOCex against
  their real QuickBooks account once, DOCex stores a refresh token, and every
  API call needs a valid access token that **expires every 60 minutes** — so
  this needs a small, permanent piece of infrastructure (a token-refresh job)
  that doesn't exist anywhere in DOCex today, not just an API call.
- **CloudEvents-format webhooks**, if DOCex wants to react to changes made
  *inside* QuickBooks (e.g., someone edits an account name and the mapping
  should know). Intuit rebuilt its webhook payload format around the
  CloudEvents standard, with a migration deadline of July 31, 2026 — which
  has already passed, so anything built from here forward is built directly
  against the current format with no legacy path to support. One less thing
  to worry about, if this had been scoped a year ago it would have been two.

**Production approval timeline.** Advertised as "1–3 weeks if the
questionnaire is filled in thoroughly," but the underlying reviews run
longer and don't all move in parallel: a technical review budgeted at ~10
business days, and — separately, if the app is ever listed on Intuit's own
app marketplace rather than used privately for one client — a security
review budgeted at up to 30 business days. For a private integration serving
one client (NEEM), the marketplace listing and its security review likely
aren't required at all, which meaningfully shortens this; worth confirming
directly with Intuit's developer support before committing to a client
deadline around it.

**What it costs.** This is the part that changed since the API was designed
as CSV-first: as of July 2025, Intuit runs a metered "App Partner Program."
Every app is enrolled by default at the **Builder tier**, which includes
**500,000 read calls per month for free**, and **writes remain free and
unlimited** at every tier. NEEM's actual usage — pushing perhaps a few dozen
to a few hundred paid disbursements a month, occasionally reading the chart
of accounts — would sit nowhere near that 500,000-read ceiling. The paid
tiers (Silver $300/mo, Gold $1,700/mo, Platinum $4,500/mo) exist for
high-volume apps serving many companies at once; they're the ceiling to be
aware of if DOCex ever resells this integration across many client
QuickBooks accounts at once, not a cost NEEM alone would be expected to
trigger. Said plainly: for one client at NEEM's transaction volume, this is
very likely a **$0/month** API cost, not the top of the range — but it is
metered where it used to be simply free, and that's worth knowing before
quoting anyone confidently.

**Bottom line on phase 2:** technically straightforward, grounded in a real,
already-separated piece of the existing export code, and probably free at
NEEM's volume — but it adds a permanent operational piece (token refresh)
that doesn't exist today, needs NEEM's own QuickBooks credentials and their
sign-off on Intuit's data-access terms, and buys them "no CSV click" in
exchange for depending on a live third-party integration instead of a file
they fully control. That trade is NEEM's to make, not ours to assume — the
CSV handoff already removes the actual pain (re-typing, reformatting bank
statements); going further is worth doing when NEEM says the monthly click
itself is the remaining friction, not before.

---

Sources:
- [How Much Does the QuickBooks API Cost? (2026 Pricing & Rate Limits)](https://truto.one/blog/how-much-does-the-quickbooks-api-cost-2026-pricing-rate-limits/)
- [QuickBooks API Pricing and the Intuit App Partner Program](https://www.apideck.com/blog/quickbooks-api-pricing-and-the-intuit-app-partner-program)
- [How to Integrate Your App with QuickBooks Online: A Complete Guide for 2026](https://www.apideck.com/blog/how-to-integrate-your-app-with-quickbooks-online)
- [QuickBooks Online API: official REST, GraphQL, and MCP paths with production review, periodic security reviews, and a metering surprise](https://vorplabs.com/agent-tools/quickbooks-online-api)
- [Upcoming change to webhooks payload structure — Intuit Developer](https://blogs.intuit.com/2025/11/12/upcoming-change-to-webhooks-payload-structure)
- [Intuit Webhooks Migration to CloudEvents by May 15, 2026 (deadline later extended to July 31, 2026)](https://www.linkedin.com/posts/joshhofmann_webhooks-allow-developers-to-instantly-sync-activity-7440045611812376577-B6N5)
