# DOCex for Neem Foundation

Your system is live. This is everything you need to start using it.

---

## Getting in

**https://docex-demo-faridmichika-4084s-projects.vercel.app**

Bookmark it. It works in any browser, on a laptop or a phone.

### Your account

You will not create your own account, and neither will anyone else. Your
administrator creates them, and DOCex shows the new password **once** —
it is never stored in a form anyone can read back, including us.

The first time you sign in:

1. Enter your email and the one-time password you were given
2. DOCex asks you to set your own password immediately
3. Until you do, nothing else in the system opens

That last step is deliberate. Until you have chosen your own password, the
account is still one somebody else knows the password to, and it should not be
able to approve a payment.

**Forgotten it, or locked out after too many attempts?** Your administrator
issues a new one-time password. There is no reset email — a link sent to a
mailbox is a way to lose an approver's account to whoever controls that
mailbox, and this system releases money.

### If the first page is slow

The first click after a quiet period can take up to a minute while the system
wakes. **Nothing is lost while it sleeps** — every record is in a managed
database that is always on. Only the web service idles, and only to keep the
pilot free of hosting cost. It disappears the moment we move to a paid plan.

---

## What it does

DOCex runs your payment workflow from the memo to the bank.

**Your policy, not a generic one.** The system was configured from your signed
Procurement Policy and your Finance Processes deck. It knows your six
departments, your approval route — Finance/Audit → Admin → AED, with the ED
joining above ₦7,000,000 — and your twenty payment categories.

**The right documents for the right payment.** Nineteen document packs, taken
from your own process deck. An equipment purchase asks for a purchase order and
a goods-received note. An advance asks for an advance request form. A DSA asks
for the travel approval form and the unreceipted expenses form. Nobody has to
remember which pack applies.

**Problems surface before an approver sees them.** When a request is raised,
DOCex checks it immediately — the amount ceiling, the category, the required
documents, whether this looks like a duplicate of something paid in the last
thirty days. The person raising it fixes the problem while the invoice is still
in front of them.

**Policy can be overridden — and the override is the record.** Releasing a
blocked payment requires a written reason and someone with the authority to
give it, and both are recorded permanently against that payment. Not to make
overriding difficult, but so that six months later the answer to "why did this
go through" is written down rather than remembered.

**An audit trail that cannot be quietly edited.** Every step is written to an
append-only log where each entry is cryptographically linked to the one before
it. Change any historical entry and the chain fails to verify and says so.
Nothing is ever overwritten or deleted.

**Bank reconciliation, per account.** Your statement lines matched against your
records, one bank account at a time. Your own reconciliation compares balances;
this compares individual lines, which is what finds the payment nobody entered.

**Advance retirement.** Your policy gives five working days and escalates from
there. DOCex runs that clock and shows what is overdue before it becomes a
finding.

**Timesheets to grant allocation.** Approved effort decides what each grant is
charged for a salary, rather than a budgeted percentage that nobody revisits.

**Bank account verification.** Confirms an account number resolves to the name
on the invoice, before the payment is made. This is the check that catches a
payment being redirected.

---

## What is deliberately switched off

We would rather tell you this now than have you find it.

**Payroll.** We do not have your confirmed PAYE bands or pension rate. Running
payroll without them produces payslips that look correct and are wrong — the
kind of error an accountant finds months later. **Send us your tax schedule and
it becomes one setting.**

**Withholding tax rates.** Your cashbook shows 5% and 10% in different places.
DOCex ships no rates at all and will withhold nothing until yours are entered.
A guessed tax rate is worse than an empty one: an empty one gets asked about, a
guessed one gets trusted.

**Tax ID verification is a format check.** DOCex confirms a TIN is well-formed.
It does not yet confirm that number is registered to that company — there is no
free official lookup, and live verification means a paid provider. Tell us if
you want it and which provider you use.

**Accounting export needs your chart of accounts.** Until we have it, exported
entries post to a single uncategorised line.

Some capabilities exist in the system but do not yet have their own screen —
withholding tax, the vendor register, advance escalation and the accounting
export run today, and get proper screens as the pilot goes on.

---

## Your data

**It is yours, and you can take it at any time.** Every month, without asking,
you receive a complete copy of your records as spreadsheets your finance team
opens in Excel, plus the full audit trail. A client who stays because leaving
would cost them their records is not a client.

**Backups run nightly**, stored away from the system itself, and each one is
verified by actually restoring it — not merely written and hoped for.

**We can read your database.** Someone has to be able to, to operate and repair
the system, and you should hear that from us rather than work it out. What we
cannot do is approve anything: every approval is recorded against a named Neem
account, so no payment can be authorised without one of your people doing it.

**Your data sits in its own database**, used by no other organisation, in a
private schema that is not reachable from the public internet.

---

## What we need from you

Bring these and the system gets sharper within days.

1. **A ruling on the quote threshold.** Your signed Procurement Policy requires
   three quotes from ₦200,001. Your Finance Processes deck says a direct memo
   is sufficient to ₦499,999. These disagree across the band where most
   purchases sit. **Which one governs?**
2. **How GAPS shows a weekly batch** on your statement — one debit per payee,
   or one for the whole batch?
3. **Your withholding tax schedule**, from your auditor.
4. **PAYE bands and pension rate**, to switch payroll on.
5. **How many overdue advances make a "collective default"?** Your policy uses
   the phrase without defining it. We have assumed two, and would rather use
   your number.
6. **One real bank statement** and your chart of accounts.

---

## When something goes wrong

Tell us. Early and in plain terms — "the approve button did nothing on
REQ-0007" is more useful than a general sense that something is off.

If a change we make causes a problem, we roll it back in minutes and tell you
what happened before you have to ask.

**Two-factor authentication** is built and available for approvers and
administrators. We have left it off for now, on purpose: introducing it in the
middle of a payment run is how a payment run gets missed. Turn it on once
everyone has settled in.

---

*Questions, problems, or anything that looks wrong — contact Farid directly.*
