# NEEM — what to know walking in

Today. The system is live. This is the list of things to say before they find
them, and the things to ask for.

---

## The two URLs

| | |
|---|---|
| **App** | `docex-demo-faridmichika-4084s-projects.vercel.app` |
| API | `docex-g0up.onrender.com` — not for humans; it answers `Not authenticated` by design |

**Hit the app ten minutes before you walk in.** The free instance sleeps after
fifteen idle minutes and the first click then takes 30–50 seconds. That is the
one thing that would make it feel slow at the worst possible moment.

Sign in: `admin@neemfoundation.org`. You will be forced to change the password
immediately — do that before the meeting, not during it.

---

## Live and demonstrable

| | State |
|---|---|
| Requisitions, policy checks, approval chain | Screens, on real config |
| Their 6 departments, 4 approval steps | From their signed policy |
| **19 document packs by payment type** | From their own deck |
| Hash-chained audit log | Screens |
| Bank reconciliation, per account | Screens |
| Timesheets → grant allocation | Screens |
| Withholding tax | API only, no screen |
| Advance retirement + escalation | API only, no screen |
| Vendor register | API only, no screen |
| QuickBooks export | API only, no screen |
| Two-factor authentication | Screens, **leave it off today** |

**API only means describe it, do not promise to click it.**

---

## Things to say before they find them

### 1. Tax ID checking is a format check

DOCex confirms a TIN is *well-formed*. It does **not** confirm it is registered
to that company.

Why: there is no free official lookup. The Joint Tax Board became the Joint
Revenue Board in January 2026 and the portals are web forms, not APIs. Live
verification needs a paid provider at roughly **₦50–100 per lookup**.

**What to ask:** do they want it, and which provider do they already use? It is
a few hours to wire in once they choose.

**Do not undersell the thing that does work.** Bank account verification is
real: DOCex confirms an account number resolves to the name on the invoice.
That is the check that catches a payment being redirected — the fraud that
actually happens. TIN mismatches are a filing problem; a wrong account number
is money gone.

> ⚠️ Needs `PAYSTACK_SECRET_KEY` in Render. **If it is not set, do not demo it**
> — the screen now says "not configured on this instance" rather than throwing
> an error, which is honest but not impressive. Set the key or skip the screen.

### 2. Payroll is switched off

No confirmed PAYE bands, no pension rate. Running payroll without them produces
payslips that look right and are wrong — the kind of error someone's accountant
finds months later.

**Ask for their tax schedule.** Then it is one setting.

### 3. The first click after a quiet spell is slow

Free hosting idles the app. A scheduled ping keeps it awake through the working
day. **No data is lost when it sleeps** — say that part, because "it went to
sleep" sounds alarming and is not.

### 4. You can read their database

Someone has to, to operate and repair it. Say it before they work it out.

What limits it: DOCex cannot *approve* anything. Every approval is recorded
against a named NEEM account in a tamper-evident chain, so no payment can be
authorised without one of their people doing it.

And they now get a **complete readable copy of their own records every month**,
unasked. That turns "what if you disappear" from a worry into a routine.

### 5. Backups are ours alone

The free database tier has no provider snapshots. Ours run nightly, off the
hosting, and every one is verified by actually restoring it. Last verified
restore: **8 September 2026**.

### 6. No staging yet

Changes are tested and then deployed. You can roll back in minutes. Being built.

---

## Six questions worth more than the demo

1. **The ₦200,001 conflict.** Their signed Procurement Policy requires three
   quotes from ₦200,001. The Finance Processes deck their staff are trained on
   says a direct memo suffices to ₦499,999. **Which governs?** Every
   single-quote purchase in that band is a finding waiting to happen, and it is
   the band most of their spending sits in.
2. **GAPS statements** — one debit per payee, or one per weekly batch? That
   answer decides how the payment schedule is built.
3. **Their WHT schedule.** The cashbook shows 5% and 10%. DOCex ships no rates
   and will withhold nothing until theirs is entered — deliberately.
4. **PAYE bands and pension rate**, to switch payroll on.
5. **"A collective default"** — how many overdue advances make it collective?
   Their policy does not say. We assumed two.
6. **One real bank statement**, and their chart of accounts. Without the chart,
   the QuickBooks export posts everything to Uncategorised Expense.

Lead with number one. Asked as a question, it is the moment the meeting stops
being a demo and starts being a consultancy.

---

## Money

### The pilot

**₦450,000/month stands.** Do not renegotiate a number you named. The real
conversation is month four, when they have used it and you can price on what
they actually got.

### What it costs you

| | |
|---|---|
| Model spend (~250 payments/mo, cached) | ~₦32,000 |
| Hosting | ₦0 now, ~₦51,000 on paid |
| **Support** | **the real cost — 20+ hours/month early on** |

Model spend is noise. **Support hours are the constraint** and the thing that
caps how many clients you can hold.

### What to charge next

- **Client two and three: ₦650,000–850,000/month.** You are no longer selling a
  promise — you have a live client and a system that survived a month end.
- **Price on what it prevents.** One disallowed cost on a donor grant runs to
  millions of naira, and unretired advances are the most common source. You now
  block those at the point of payment. That is the anchor — not hours, not
  hosting.
- **Onboarding fee, ₦300–500k one-off.** Reading their policies and building
  their profile is real work that happens once. Bundling it into month one
  makes the recurring price look inflated.
- **Charge separately for anything CUSTOM.** Absorb bespoke work twice and it
  becomes the expectation.
- **Never price per seat.** Twenty users at NEEM, five at a smaller NGO, same
  engine and same support load. Per-seat punishes the clients you most want.

### If they ask to expand today

Say yes to the conversation, not to the scope. Anything new goes through
config / core / custom triage first — that discipline is why one engine can
serve three clients.

---

## What NOT to do today

- **Do not switch on two-factor authentication.** It works, and requiring it of
  twenty people mid-payment-run is how a payment run gets missed. Turn it on
  once they have settled.
- **Do not demo Bank Verify without the Paystack key set.**
- **Do not promise a date for TIN, payroll or QuickBooks sync.** Each waits on
  something only they can give you.
- **Do not create their twenty accounts before they have watched you create
  one.** Let them see the one-time password flow — it is a control worth
  showing, and it explains itself better than you can.

---

## The one line to have ready

If they ask why this instead of a spreadsheet and QuickBooks:

> In QuickBooks, an unauthorised ₦750,000 transfer and a payment somebody forgot
> to enter look identical — both are unmatched lines, and the fix for both is
> the same button. That is how an unauthorised payment gets absorbed into the
> books. DOCex refuses to close the month until someone explains it in writing,
> under their own name.
