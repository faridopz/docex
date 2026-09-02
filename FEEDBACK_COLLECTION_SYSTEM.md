# Feedback Collection System — Test Run (Sep 10 – Oct 1)

**During the 3-week test run, you need to systematically capture:**
1. Bugs (things that break)
2. Challenges (workarounds users invent)
3. Lags (things that slow people down)
4. Requests (features they ask for)
5. Confusion (where users get lost)

**This data becomes your product roadmap + your case study.**

---

## The System (Simple, Not Elaborate)

### 1. Daily Standup (10 min, Async)

**What:** Each evening, NEEM finance team sends you a 2-min voice note or text:
- What worked today?
- What broke or confused you?
- What made you slow down?

**Why:** Real-time feedback, not a meeting. Async = they don't feel interrupted.

**Template they use:**
> "Submitted 3 requisitions today. OCR works great on photos. One issue: can't edit a requisition after submitting (had a typo in the amount). Also, it took 3 min to find the vendor list when adding new vendor to block list. One approval got stuck because [person] didn't see the notification."

**You respond same day:**
> "Thanks for the feedback. Editing after submit — will add that. Vendor list — noted, we can improve the UX. Notifications — let's check if their browser blocked them. Call tomorrow?"

**This creates a feedback loop.** They feel heard, you learn fast.

---

### 2. Weekly Bug/Issue Log (Spreadsheet)

**Keep a simple sheet:**

| Date | Category | Description | Severity | Status | Notes |
|------|----------|-------------|----------|--------|-------|
| Sep 12 | Bug | OCR misread "₦" as "8" | Med | Fixed | Updated regex |
| Sep 13 | Lag | Approval list takes 8 sec to load | Med | Investigating | Database query issue? |
| Sep 14 | Confusion | User tried to delete requisition (not possible) | Low | Design change | Add "archive" feature |
| Sep 15 | Request | "Can we see who declined a payment?" | Low | Backlog | Add to audit trail view |

**Update it weekly (Sun 5 pm):**
- You review all feedback
- Categorize (bug / lag / confusion / feature)
- Prioritize (critical / high / medium / low)
- Fix the critical stuff in real-time
- Log the rest for later

---

### 3. Weekly Video Call (30 min)

**Every Friday, 4 pm (their time):**
- Review the week's issues
- Demo fixes you shipped
- Show them the roadmap
- Ask for next week's priorities

**This is the hardest working you'll do all week, but it's worth it.**

**Agenda:**
- "Here's what we fixed this week" (5 min)
- "Here's what we found but didn't fix" (5 min)
- "What should we prioritize next?" (10 min)
- "Any other issues?" (10 min)

**Outcome:** They feel like they have a partner, not a vendor.

---

## Categories & Severity

### Bug (Something Breaks)

**Severity:**
- 🔴 **Critical:** Blocks their work (can't submit a requisition, can't approve)
  - Fix: TODAY
- 🟠 **High:** Workarounds exist but it's painful (OCR misread, slow load)
  - Fix: This week
- 🟡 **Medium:** Minor issue (typo in label, button placement)
  - Fix: Next release
- 🟢 **Low:** Cosmetic
  - Fix: Eventually

**Example:** "Login page doesn't work on Safari" = Critical (block). "Login button is slightly off-center" = Low (cosmetic).

---

### Lag (Things Slow Down)

**Measure:** How long does it take?

- > 5 seconds = investigate
- > 10 seconds = fix this week
- < 2 seconds = you're good

**Log it:**
> "Loading the approval list takes 8 seconds on their 3Mbps wifi. Users are waiting for it."

**Why:** Lags compound. By week 3, they're frustrated and slow. Fix early.

---

### Confusion (Users Get Lost)

**Watch for:**
- Users clicking the wrong button twice
- Users asking "how do I...?" the same question
- Users taking the long route to do something simple

**Example:**
> "When adding a new vendor, user looked in three places before finding the input field."

**This is a UX issue, not a bug.** Fix by week 3.

---

### Requests (Features They Want)

**Don't build all of them. Log them.**

**Severity:**
- 🔴 **Blocking:** "We can't go live without this" (rare)
- 🟠 **Important:** "This would save us hours" (add to phase 2)
- 🟡 **Nice-to-have:** "It would be nice if..." (backlog)

**Example:**
> "Can we see a report of all payments to a specific vendor this month?" = Nice-to-have, backlog.
> "Can we block payments to vendors we didn't approve?" = Important, phase 2.

---

## How To Capture Feedback (Tools)

### Option 1: Simple Google Sheet (Recommended)

**One sheet for bugs, one for requests:**

```
Feedback Log (Sep 10 – Oct 1)
[Shared with NEEM]

Date | Who | Issue | Category | Severity | Status
Sep 12 | Abby | OCR reads ₦ as 8 | Bug | High | Fixed Sep 12
Sep 13 | Taiwo | Approval list slow | Lag | High | Investigating
Sep 14 | Abby | Can't edit after submit | Feature | Medium | Backlog
```

**Why:** Transparent, both of you can edit, searchable.

**Share the sheet with NEEM.** They see you're taking issues seriously.

---

### Option 2: Slack Channel (If They Use Slack)

**Create: #feedback-docex**

**Guidelines:**
- Post bugs / lags / requests freely
- You check it daily
- You respond within 24 hours
- Weekly Friday call to prioritize

**Pros:** Real-time, fast, low friction  
**Cons:** Gets messy, hard to track

**Combo:** Slack for quick chat, Google Sheet for the record.

---

### Option 3: Weekly Form (If They Prefer Formal)

**Google Form sent every Mon, due Tue:**

Questions:
1. "What bugs did you find?" (free text)
2. "Did anything feel slow?" (free text)
3. "Got confused anywhere?" (free text)
4. "Feature request?" (free text)
5. "Overall, how's it going? (1–5 stars)

**Pros:** Structured, easy to analyze  
**Cons:** Takes more effort, less real-time

**I'd recommend: Daily standup + Google Sheet + Friday call.**

---

## What To Track (The Data You Need)

### Performance Metrics

**Measure these daily:**
- Slowest page to load? (approval list, audit view?)
- Most-clicked features? (requisition submit, approve)
- Most errors? (login, file upload, search?)

**Why:** Tells you where to optimize.

**Example:**
> "Approval list is our slowest page. 8 seconds. ~50 clicks/day. 30% of all time spent on app. FIX THIS FIRST."

---

### User Behavior

**Watch for:**
- Who uses what? (finance director uses approvals, fieldworker uses receipts)
- What's the success rate? (How many requisitions get approved on first try?)
- What's the rework rate? (How many get returned for changes?)

**Why:** Tells you if the design is working.

**Example:**
> "50% of requisitions get returned on first submission. Most common reason: missing vendor TIN (23%), wrong grant code (14%), amount mismatch (13%). FIX TIN VALIDATION FIRST."

---

### Feature Usage

**Track:**
- How many field receipts uploaded per day?
- How many requisitions created per day?
- How many approvals per day?
- How many audit trail views?

**Why:** Tells you what they actually care about.

**Example:**
> "Audit trail is viewed 3 times a week (their auditor prep). Requisitions average 5/day. Field receipts average 12/day. They care MOST about field receipts. Make that perfect."

---

## The Feedback Analysis (Weekly)

**Every Sunday, 30 min:**

1. **Review all feedback** (Slack, form, sheet, calls)
2. **Categorize** (bug / lag / confusion / feature)
3. **Prioritize** (critical / high / medium / low)
4. **Estimate** (how long to fix?)
5. **Plan** (what's this week's fix list?)

**Example analysis:**

**Critical (fix this week):**
- OCR reads ₦ as 8 (2 hours to fix)
- Can't edit after submit (1 hour to add)
- Approval notifications not sending (1 hour to debug)

**High (fix if time):**
- Approval list slow (4 hours optimization)
- Vendor input confusing (2 hours UX redesign)

**Medium (next release):**
- Add vendor TIN validation (3 hours)
- Show payment status report (2 hours)

**Low (backlog):**
- Cosmetic tweaks
- Nice-to-have features

---

## Communication Template (Weekly Update)

**Send to NEEM every Monday:**

Subject: "DOCex Weekly Update — Sep 12"

> Hi [NEEM],
>
> **Last week's feedback:**
> - 23 issues logged (3 bugs, 4 lags, 8 confusions, 8 feature requests)
> - Critical issues: 0 🎉
> - High issues: 2 (fixing this week)
>
> **We fixed:**
> - OCR ₦ bug ✅
> - Added edit-after-submit feature ✅
> - Optimized approval list loading (now 3 sec, was 8 sec) ✅
>
> **This week's priority:**
> - Fix notification delivery (audit trail view isn't showing)
> - UX improvement: vendor input field (users confused)
> - Build vendor TIN validation
>
> **Questions for you:**
> - Did you feel the speed improvement on the approval list?
> - Any new issues this week?
>
> See you Friday for our call.
>
> Farid

**This says:** "I'm listening, I'm fixing things, I'm tracking progress."

**That's trust.** That's how you become their favorite vendor.

---

## After 3 Weeks (Go-Live)

**Compile a report:**

### NEEM Test Run Report (Oct 1)

**Executive Summary:**
- System is production-ready ✅
- 23 issues found and fixed ✅
- 2 features built (edit, TIN validation) ✅
- 8 feature requests logged for phase 2 ✅
- Zero critical bugs remaining ✅

**Detailed:**
- Bugs found: 3 (all fixed)
- Lag issues: 4 (all resolved)
- UX confusion: 8 (7 fixed, 1 in progress)
- Feature requests: 8 (logged for priority discussion)

**User feedback:**
> "System is solid. Audit trail is perfect. One thing: OCR sometimes struggles with handwritten amounts. But the interface is intuitive and fast." — Abby, NEEM Finance

> "Requisition workflow is smooth. Approvals are fast. Only issue was the initial learning curve on vendor TIN entry, but that's fixed now." — Taiwo, NEEM Program

**Performance:**
- Slowest page: Audit view (2.5 sec, acceptable)
- Fastest: Submit requisition (0.8 sec, great)
- Zero downtime ✅
- Average load time across all features: 1.8 sec ✅

**Recommendation:**
- System is ready for production
- Go-live Oct 1 as planned
- Phase 2 features (reconciliation, advance aging) start Oct 5

---

## Why This Matters

**By the time NEEM goes live, you'll have:**

1. ✅ A list of every issue they found (and proof you fixed it)
2. ✅ Metrics showing the system is performant and stable
3. ✅ A roadmap for the next 2 phases (built with their input)
4. ✅ Testimonials ("System is solid", etc.)
5. ✅ A case study (NEEM went from chaos to order)

**All of this becomes your sales deck for Client 2.**

**"We tested this with NEEM. Here's what we learned. Here's how it works. Here's what happens next."**

**That's how you sell at ₦400k/month to the next client.**

---

## Implementation Checklist

**Week 1 (Sep 10–15):**
- [ ] Set up Google Sheet for feedback
- [ ] Create Slack #feedback channel (if they use Slack)
- [ ] Agree on daily standup format (voice note or text)
- [ ] Schedule Friday calls (4 pm, recurring)

**Week 2–3 (Sep 16–Oct 1):**
- [ ] Collect feedback daily
- [ ] Update sheet weekly
- [ ] Fix critical bugs same-day
- [ ] Fix high issues within 24–48 hours

**Oct 1 (Go-Live):**
- [ ] Compile final report
- [ ] Get testimonials from NEEM
- [ ] Celebrate ✅
- [ ] Start planning Client 2

---

**This system is simple, but it's the difference between a vendor and a partner.**

**Use it. You'll build something great.**

