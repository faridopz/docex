# Tomorrow Final Prep — Everything Together

**Sep 2, 2026 · NEEM Meeting**

---

## You, Distilled (Read First)

You're not a vendor. You're a builder who listens.

The goal is NOT to sell DOCex. The goal is to:
1. Show what's possible (the framework works)
2. Understand how they actually work (listen)
3. Identify which gap to solve first (theirs, not yours)
4. Propose a 4-week project to solve it (specific, achievable)

**Tone:** Curious, specific, taking notes. Confident but not defensive. Asking more than telling.

---

## The Code (Verified ✅)

All 105 tests pass:
- ✅ 31 extraction tests (file formats, OCR, vendor names, SUBTOTAL bug)
- ✅ 26 integration tests (receipt → requisition → payment pipeline)
- ✅ 48 requisition tests (full approval workflow, overrides, audit trail)

**The system works.** The workflow is solid. You can demo with confidence.

---

## Tomorrow's Arc (25–30 min total)

| Time | What | Tone |
|------|------|------|
| 0:00–2:00 | **Opening.** "I built a framework. Show me how YOU work so we can customize it." | Humble, partnership-minded |
| 2:00–6:00 | **Demo Segment 1: Field Receipts.** Show. Ask: "Does this look right?" | Curious, listening |
| 6:00–9:00 | **Demo Segment 2: Requisitions & Rules.** Show. Ask: "What rules matter?" | Collaborative, note-taking |
| 9:00–13:00 | **Demo Segment 3: Blocked Payment & Override.** Show. Ask: "When have you needed this?" | Diagnostic |
| 13:00–15:00 | **Demo Segment 4: Audit.** Show. Ask: "What do auditors ask for?" | Problem-finding |
| 15:00–27:00 | **Discovery Questions (baked in).** Ask: "What's the one thing we should tackle first?" | Stop talking. Listen. |
| 27:00–30:00 | **Close.** "Here's what I heard. Here's what I'd build first. Thoughts?" | Partnership proposal |

**Key:** You're not pitching. You're thinking out loud *with them*.

---

## Before You Leave Home (Tonight)

- [ ] Laptop charged + charger in bag
- [ ] Run: `python3 -c "import fast_extract; print(fast_extract.ocr_available())"` (must say `True`)
- [ ] Both terminals ready to go (API + frontend, don't run them yet)
- [ ] Signed in to localhost:3000 as demo@neem.org
- [ ] Phone has screenshots of all 4 screens (backup)
- [ ] Print:
  - [ ] DEMO_CHECKLIST.md (on your lap during demo)
  - [ ] PRICING_STRATEGY.md (for after, reference only)
  - [ ] NEEM_FOLLOWUP_TEMPLATE.md (to fill in during meeting)

---

## At the Venue (15 min before)

- [ ] Laptop plugged in (not battery)
- [ ] Confirm API and frontend both running
- [ ] Check projected screen works
- [ ] Test login: demo@neem.org
- [ ] Open Field Receipts, Requisitions, Audit in separate tabs (ready to switch)

---

## What You're Listening For (The Real Audit)

**Field Receipts segment:**
- Do they use WhatsApp photos today? → Offline capture is urgent
- What info gets lost? → What to flag first
- How long does a receipt take to process? → ROI story

**Requisitions segment:**
- Do they have procurement thresholds? → Banded rules needed?
- What rules are "understood" vs. written? → Governance gap
- Who approves what? → Approval chain complexity

**Override segment:**
- When was the last time someone overrode policy? → Real incident?
- How was it documented? → Probably "nowhere" → your win
- Do they have authority limits by role? → Or is it all ad-hoc?

**Audit segment:**
- What do auditors ask for first? → ROI story
- How long does audit prep take? → Time saved story
- Have they ever had to re-do work because docs were missing? → Pain validation

**Closing:**
- What's one thing we should build first? → This is the roadmap, not your ideas

---

## Your Backpocket Moves

**If they're hesitant:**
> "Let's do a 4-week test. You send me your real org structure and grant codes, we configure the system, and you run it live with a subset of payments. No commitment beyond that."

**If they ask about offline:**
> "KoboCollect backend is done and tested. The field app connection is finishing. Would that unblock a lot of your flow?"

**If they ask about a missing feature:**
> "Not yet. Is that blocking you from trying this, or is it nice-to-have?"

**If they ask price (too early):**
> "Let's dig into your process first. Price is easy once we both know we're solving the right thing."

**If they ask price (end of meeting):**
> "For your size and volume, ₦250k/month. That's ₦8 per requisition. Prevents one audit finding (₦500k value) in year one. Want to run a trial?"

---

## The Close (Read This Twice)

**Don't say:** "Let's sign a contract."  
**Don't say:** "You'll love this."  
**Don't say:** "Here's my standard pricing."

**Do say:**

> "Here's what I heard: [three pain points they mentioned]. I think we should start with [the one they said matters most]. Over the next 4 weeks, we'd configure your workflow, you'd test it live with your team, and we'd iterate. Then you decide if it's worth continuing. No lock-in. Sound good?"

**Then stop talking.**

Their response is your next move:
- "Yes, let's try it" → Send a project proposal (one page, 4 weeks, ₦250k/month)
- "We need to think about it" → Send follow-up one-pager with what you heard
- "We're not ready" → Understand why, plant a seed, stay in touch

---

## What Success Looks Like

**Low bar:** You walk out with:
- ✅ Their three biggest pain points (clear in your notes)
- ✅ Which one they want solved first (written down)
- ✅ Their org structure (departments, approvals, grant codes)
- ✅ Their email so you can follow up

**High bar:** You walk out with:
- ✅ All of the above
- ✅ A "yes, let's try it" or a credible "let's talk in 2 weeks"
- ✅ An intro to their Finance Director or Executive

**Either way:** You've learned something real about how NGO finance actually works. That's a win.

---

## After You Leave (Critical)

**By Thursday EOD:**
- Send NEEM_FOLLOWUP_TEMPLATE.md filled in with their answers
- Subject: "NEEM — DOCex Demo Summary (Sep 2)"
- Include: "Here's what you told us" + "Here's what I'd build" + "Thoughts?"
- Sign with your email

**Wait for their move.** Don't chase. Let them come to you.

**Update CLAUDE.md** with:
- What you learned about NEEM's process
- Their biggest pain point (the one they said matters most)
- Your recommendation for what to build first
- Any surprises or edge cases you discovered

---

## The One Thing to Remember

**You're not trying to make them fall in love with DOCex.**

**You're trying to fall in love with their problem.**

If you do that — if you genuinely understand their pain, write it down, and propose a specific solution — they'll want to work with you.

The demo is just the vehicle for that conversation.

---

## Physical Checklist (Print This)

```
☐ Laptop + charger
☐ Phone (screenshots backup)
☐ DEMO_CHECKLIST.md (print, bring)
☐ PRICING_STRATEGY.md (reference only)
☐ NEEM_FOLLOWUP_TEMPLATE.md (print, fill in)
☐ Pen (for notes)
☐ Notebook (to look like you take their problems seriously)
☐ Water (you'll need it)
☐ Backup: screenshots of all 4 screens on phone
☐ API running (uvicorn :8000)
☐ Frontend running (npm run dev :3000)
☐ Signed in to localhost:3000
☐ Confident (you've tested this, the code works, you know what you're doing)
```

---

## Last Thought

You built something real. The tests prove it. The workflow is solid. The ROI for them is huge.

Walk in calm. Listen hard. Take notes. Be specific. Let them want more.

You've got this.

**Go build something great with NEEM.**

---

*Sept 2, 2026 · faridmichika@gmail.com*
