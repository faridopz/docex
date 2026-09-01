# NEEM — questions to ask, and what each answer changes

The demo shows what DOCex does. These questions find out what NEEM actually
needs, which is the more valuable half of the meeting. Ask maybe eight of
them — not all twenty-five. Let them talk.

**The single best question, if you only get one:**

> "Walk me through the last payment that went wrong. Not a typical one — the
> one that caused the most trouble."

People describe processes in the idealised form. They describe *incidents*
accurately, and the incident is where the product earns its money.

---

## 1. The shape of the work

These size the problem and tell you which tier they're on.

1. How many payments does finance process in a month? Roughly.
2. What's the split between field expenses, vendor invoices, and staff
   payments?
3. How many people are in finance? How many raise requests but don't approve?
4. How many active grants right now, and how many donors?

*Why it matters:* under ~50/month they're Starter; 50–200 is where ₦250k lands.
And if most spend is field expenses rather than vendor invoices, lead with
receipts — not requisitions.

---

## 2. Field receipts — their stated pain point

5. When a fieldworker buys something in Kano, what physically happens to that
   receipt between the market and your finance system?
6. How long does that take, typically? And what's the worst case?
7. What proportion of receipts arrive incomplete or unreadable?
8. What do you do *today* when a receipt is missing the vendor or the date?
   Chase it, estimate it, or reject it?
9. Do fieldworkers photograph receipts already? On WhatsApp, or something else?
10. Do you use KoboCollect or ODK for anything now? Which forms?

*Why it matters:* Q9 is the important one. **If they already WhatsApp photos to
finance, that's the workflow to replace** — and you don't need the Kobo
integration finished to be useful on day one. Q10 tells you how close the
offline piece really is.

---

## 3. Approvals

11. Who has to approve a ₦50,000 payment? A ₦500,000 one?
12. Is that written down, or is it understood?
13. How does an approver find out something is waiting for them?
14. Where do payments get stuck most often?
15. When someone approves an exception to policy — is that recorded anywhere?

*Why it matters:* Q12 is diagnostic. "It's understood" means the approval chain
lives in someone's head, and configuring DOCex will surface disagreements
between people who thought they agreed. That's valuable but it's work — budget
for it in onboarding rather than discovering it in week two.

Q15 is where you'll hear the honest answer: usually "in an email somewhere",
which is exactly the gap the audit trail fills.

---

## 4. Documentation and procurement

16. What documents must be attached before a payment goes out? Does that change
    with the amount?
17. Do you have a procurement threshold — a value above which you need three
    quotes?
18. Who enforces that today, and how do you know it happened?

*Why it matters:* this is the banded-rules gap. If they answer Q17 with a
specific naira figure, **write it down** — that's the first thing to configure,
and it's the feature I'd build next.

---

## 5. Advances

19. Do staff take cash advances for field activity?
20. How long do people have to retire an advance? Is that enforced?
21. How do you know today what's outstanding? A spreadsheet?
22. Has anyone ever taken a second advance while the first was unretired?

*Why it matters:* Q21 and Q22 usually land. The advance-aging report is cheap
to build and makes an invisible problem visible — often the fastest visible win
after receipts.

---

## 6. Audit

23. Who audits you, and how often?
24. What were the findings last time? Be specific.
25. How long does it take to assemble what the auditor asks for?

*Why it matters:* **Q24 is the money question.** If they say "unsupported
expenditure" or "missing documentation", DOCex is aimed exactly at that and you
should say so plainly. If they say "we've never had a finding", pivot to time
saved rather than risk avoided — the risk pitch will sound like fear-selling to
someone who's never been burned.

Q25 gives you the ROI number in their own words. "Two weeks" is a number you
can multiply by a salary.

---

## Listen for these

**"We track it in a spreadsheet."** Every time you hear it, that's a module.
Ask who maintains it and what happens when they're on leave.

**"It depends who's around."** A policy with no owner. This is where an audit
finding comes from.

**"We usually…"** The gap between usually and always is the exception the
system needs to record.

**"That's just how we've always done it."** Don't challenge it in the meeting.
Note it, ask what would have to be true to change it.

---

## Be straight about what isn't built

Say these before they find them. Credibility now is worth more than a signature
this week.

- **KoboCollect sync** — backend built and tested, field app connection still
  being finished
- **Onboarding wizard** — configuration is hands-on today, done with them
- **Auditor export** — the audit view is on-screen; no Excel/PDF export yet
- **Bank reconciliation** — not built
- **Banded procurement rules** — one document list today, not tiered by amount.
  If Q17 gets a real answer, this is next.

"Not yet, here's when" beats a vague yes every time. And if they push on a date,
give a range you'd be comfortable missing by a week.

---

## Ending it

> "If we built one thing for you in the next month, what would make the biggest
> difference?"

Then stop talking. Whatever they say next is your roadmap, and it's worth more
than anything in this document.
