# Build Roadmap — what to build, in what order, and why it pays

**From:** September 2026 · **Through:** Q1 2027
**Rule that governs everything below:** a live client beats a future feature.

---

## The recommendation in one line

**Get NEEM to production this month. Get EVA earning in phase one rather than
after phase six. Build every EVA engine as shared product, so client three buys
what the first two paid for.**

---

## Why this order

Three things are true at once, and the sequence falls out of them:

1. **NEEM is already paying and cannot go live** — the free tier wipes their
   data on every redeploy. That is revenue at risk today, and it's ~2–3 days of
   configuration, not code.
2. **EVA needs roughly six engines built.** At six weeks of work, waiting until
   all of it is finished before they pay is six weeks of unpaid building. Phase
   them instead: get them live on the backbone, build the rest while they pay.
3. **Every EVA engine is product.** DOA routing, budget checks, procurement
   bands, statutory deductions — all of it goes in the shared engine behind
   flags. Client three buys a system that two other organisations already paid
   to build.

---

## Month by month

### September — NEEM to production

| | |
|---|---|
| **Week 1** | Production infrastructure (`PRODUCTION_READINESS.md`): paid plan, `DOCEX_DB` on a persistent disk, backups with a **tested restore**, Sentry, uptime alerts, secrets set explicitly. **Verify data survives a redeploy.** |
| **Sep 10** | Their documents and flows. Sort every requirement into Config / Feature / Custom. Fill `profiles/neem.json` with real thresholds and grant codes. |
| **Weeks 3–4** | Apply their profile to their instance. Build vendor TIN validation. Start the test run with real receipts. |

**Ends with:** NEEM using their own system with their own data, on infrastructure
that doesn't lose it.

**Do not start EVA engine work until the production checklist is green.** It is
the one thing that turns a paying client into a former one.

---

### October — NEEM live, EVA phase one

**NEEM (60%)** — test run, daily issue triage, Friday calls, fixes. Go live end
of month. Write the close-out report and get the testimonial. **That report is
what sells client three.**

**EVA (40%)** — Phase 0 + Phase 1 from `EVA_BUILD_PLAN.md`:

- Stand up their instance, apply `profiles/eva.json`
- **`doa.py`** — the Delegation of Authority matrix. Amount band → ordered
  approver chain. Pure arithmetic, never AI.
- ED final-authorisation stage on the state machine
- Their five departments routing correctly

**Acceptance:** a voucher walks Program → Compliance → Finance → TLFA → ED →
Paid entirely in-app, with a complete audit trail, and a reviewer cannot
self-authorise.

**That is enough for EVA to go live and start paying.** Their core problem —
approvals living in people's heads, no audit trail — is solved at phase one.
Everything after it is improvement, not rescue.

---

### November — EVA earning, phase two

**EVA live on the backbone.** Now build while they pay:

- **`deductions.py`** — PAYE, pension, WHT, VAT. Deterministic. Their Compliance
  Officer's "deductions captured" check becomes code.
- **`coding.py`** — project / cost-centre coding + budget availability. An
  over-budget request blocked with the budget line cited.

**NEEM (20%)** — stable, monthly check-in, month-end bank reconciliation built.

**Both features are CORE.** NEEM gets budget checking for free; it's a flag.

---

### December — payroll, and the renewal conversation

**EVA** — Phase 3, payroll. **Blocked until the refinancing sign convention is
confirmed.** Ask them in October, not December; a wrong sign convention in a
payroll system is a serious defect and it is not guessable.

**NEEM** — month 11. Prepare the renewal: what shipped, what it prevented,
new price ₦550k. Ask for referrals now, with a case study in hand.

**Sales** — client three pipeline. You now have two live clients, two
testimonials, and a feature set neither of them asked for individually.

---

### Q1 2027 — the hire

**EVA** phases 4–5: agreements/cash-flow reconciliation, procurement bands.
**Client three** onboarding — and this one should take days, not weeks, because
everything they need already exists.

**Hire the support + config person.** This is the gate on everything after.
Three clients is where doing it all yourself stops working, and the failure
shows up as slow replies to the client who pays you most.

---

## How each client experiences it

They all run the same engine. Each one experiences it as *theirs*. That's what
the config file and the feature flags buy you.

### NEEM sees

> *"A system built for our receipt problem."*

Their screens: field receipts, requisitions, approvals, audit.
Their flow: Program → Compliance → Finance → Management.
Their language: their categories, their grant codes, their thresholds.

**What's hidden:** payroll, procurement bands, DOA matrix, QuickBooks export.
Flags off. They don't know those exist, and nothing on screen hints at them.

**What they'd see later, if they wanted it:** you turn on a flag. Budget
checking appears. No build, no deploy, no invoice.

### EVA sees

> *"A system built for our audit readiness."*

Their screens: the same requisitions engine — plus payroll, agreements,
procurement.
Their flow: Program → Compliance → Finance → TLFA → **ED authorisation**.
Their language: DOA bands, project and cost-centre codes, sub-recipients.

**What's hidden:** NEEM's TIN checking, unless they want it.

**The point:** EVA's Compliance Officer and NEEM's finance officer are looking
at the same code and would each swear it was built for them.

### Client three sees

> *"This is more complete than anything else we've been shown."*

They get, on day one, features neither NEEM nor EVA asked for individually:
grant-period blocking, duplicate detection, TIN validation, budget checks, DOA
routing, procurement bands, reconciliation.

**They pay more, and they onboard faster.** That's the whole model working.

---

## What each engagement funds

| Client | Price | What they pay for | What you keep |
|---|---|---|---|
| **NEEM** | ₦450k/mo | Production infrastructure · TIN validation · bank reconciliation | Reputation, first case study, **two features** |
| **EVA** | ₦600k/mo *+ build fee* | DOA · deductions · budget · payroll · procurement · accounting export | Second case study, **six engines** |
| **Client 3** | ₦600–700k/mo | Nothing new — it already exists | **Near-pure margin** |
| **Client 4+** | ₦600k–1.5m | Nothing new | Margin, and it gets easier each time |

**Read the right-hand column downward.** That's the business: the first two
clients pay you to build inventory you sell for years.

---

## A pricing point on EVA — worth deciding before you quote

EVA needs roughly six engines. That's about six weeks of build. At ₦600k/month
with no setup fee, you'd be four months in before the build is covered — and
you can't do that twice in a row and stay solvent. NEEM at near break-even was
a deliberate reputation trade. Doing it again isn't a strategy, it's a habit.

Three ways to structure it:

**A. Build fee + monthly** *(cleanest)*
₦1.5m one-time build, then ₦600k/month. Honest and easy to explain: *"Phase one
gets you live in six weeks. That's a defined build. Then it's ₦600k/month to run,
support and keep improving it."*

**B. Higher monthly, 12-month commitment**
₦850k/month for year one, dropping to ₦600k at renewal. Same money, no upfront
ask — easier for an NGO whose cash arrives in tranches.

**C. Phased build fees**
₦500k per phase as each ships, plus ₦600k/month from phase one. Lowest risk for
both sides; they pay for what's delivered.

**I'd lead with C, and settle at A or B.** C matches how NGO money actually
arrives, and phase-one-first means they're live and paying before the big build
lands. It also gives you a natural stop if a later phase turns out not to matter
to them.

**What not to do:** quote ₦600k/month flat and absorb six weeks of build. That's
NEEM's deal again, and NEEM's deal only made sense once.

---

## The two things most likely to go wrong

**1. EVA work eats NEEM's go-live.** New engines are more interesting than
production configuration. But a live client with a problem outranks a future
client with a feature — every time, no exceptions. NEEM's production checklist
is the gate on everything in October.

**2. You build all six EVA engines before they pay.** Phase them. Get them live
on the backbone in October and let the revenue run while phases two through five
land. If EVA turns out to need only four of the six, you'll find that out by
shipping, not by planning.

---

## Decision points

| When | Decision |
|---|---|
| **This week** | Which EVA pricing structure — A, B, or C |
| **October** | Confirm EVA's refinancing sign convention — blocks payroll entirely |
| **December** | NEEM renewal price (recommend ₦550k) |
| **Q1 2027** | Make the hire. Don't defer past client three. |
| **Mid-2027** | Move to AWS; start the standard tier if Track B still looks right |

---

## Where the work happens

Separate chats, `MASTER_CONTEXT.md` carrying context between them:

1. **NEEM delivery** — production deploy, their config, their test run
2. **EVA build** — engines, one work order at a time
3. **Engine / infra** — shared core, deployment automation, the profile generator
4. **Business** — pricing, pipeline, proposals

**Start with NEEM production.** It's blocking revenue, it's mostly configuration,
and it's two or three focused days.
