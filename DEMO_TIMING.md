# Demo Timing — Stay on Track

**Total: 25–30 minutes (demo 12–15 min, questions 10–15 min)**

---

## Setup (Before They Arrive)

```
Laptop open, signed in to localhost:3000 as demo@neem.org
Terminal 1 running: uvicorn (API)
Terminal 2 running: npm run dev (frontend)
All four screens (Field Receipts, Requisitions, Payments, Audit) cached/ready to click
Backup: screenshots of all four screens on your phone (5-min insurance)
```

---

## Demo (12–15 minutes)

| Time | What | Where | Notes |
|------|------|-------|-------|
| 0:00–0:30 | Context: "Amina in the market" | Talk (no click) | Set the story. This is their world. |
| 0:30–2:00 | **Segment 1: Field Receipts** | Requisitions → Field Receipts | Point at photo. Point at incomplete one. Emphasize: no guessing. |
| 2:00–3:00 | Breathe. Any questions? | — | Let them ask. This is their pain point. |
| 3:00–5:00 | **Segment 2: New Requisition** | Requisitions → New | Fill in a simple one (₦100k, safe). Submit. Show policy checks pass. |
| 5:00–5:30 | Breathe. Any questions? | — | Natural pause. |
| 5:30–10:00 | **Segment 3: Blocked Payment** | Requisitions → Waiting on Me | Open REQ-0002 (blocked, ₦140k). Show why it's blocked (grant closed). Try to approve (button disabled). Tick check, write reason, name authority, approve. Record payment. |
| 10:00–10:30 | Breathe. Any questions? | — | This is the governance moment. Let it land. |
| 10:30–12:00 | **Segment 4: Audit** | Audit | Show the verdict (audit-ready or N unexplained). Explain: auditor opens this, sees every exception with who/why/authority. |
| 12:00–12:30 | Close the story | Talk (no click) | "Most systems record an override. This one refuses unexplained ones." |

---

## Discovery Questions (10–15 minutes)

| Time | Q | Listen For | Time Box |
|------|---|------------|----------|
| 12:30–13:00 | **Q1: Incident** | What actually went wrong? | 2 min (let them talk) |
| 13:00–13:20 | **Q2: Workload** | Payments/month? | 1 min |
| 13:20–13:35 | **Q3: Types** | Field / vendor / payroll split? | 1 min |
| 13:35–13:50 | **Q4: Team** | Finance size? Approvers? | 1 min |
| 13:50–14:10 | **Q5: Receipt Problem** | How do receipts move today? | 1 min |
| 14:10–14:25 | **Q6: Docs** | What's required? By amount? | 1 min |
| 14:25–14:40 | **Q7: Advances** | Do they do advances? Aging? | 1 min |
| 14:40–15:00 | **Q8: Audit** | Last findings? | 1 min |
| 15:00–15:15 | **Q9: Policy** | Written or understood? | 1 min |
| 15:15–15:30 | **Q10: Close** | One thing to build first? | 2 min (stop talking) |

---

## Red Lights (Shut It Down)

**If > 2 min on any one topic during demo:** Say *"This is exactly what we should dig into in the discovery phase. Let me note that down."* Then move on.

**If > 15 min into questions and you haven't asked Q10:** Jump to Q10. It's the most valuable question.

**If they ask about something not built (e.g., bank reconciliation):** *"Not yet. Here's what's next: [KoboCollect / advance aging / banded rules]. Which of those matters most to you?"* Then note it.

---

## The Backpocket Offer

If they look hesitant or want to see more: *"I can do a 30-minute working session next week — walk through your grant codes, your approval chain, and your required documents. That's where you see whether this actually fits."*

Do NOT oversell. Let them want more.

---

## Wrap

1. Hand them the **NEEM_FOLLOWUP_TEMPLATE.md** (printed or emailed after the call)
2. Say: *"I'll send this over with what you told us. We can start next week if you want to try a real test with your data."*
3. Get their email, confirm: *"I'll follow up by Thursday."*

Done.

---

## Watch-Outs

- **REQ-0002 is blocked on purpose.** This is the live moment where you show governance works. Don't rush it.
- **Don't open Payment screens unless they ask.** The Audit view is the closer.
- **If OCR failed on the photo receipt:** Point to it anyway. *"This is a photographed receipt from a market. The system reads the vendor and amount off the photo. Here's what it extracted."* Show confidence even if the feature is down.
- **If the API is slow:** Say *"We're running this locally so network isn't the bottleneck. In the cloud it's faster."* Completely true.
- **If something crashes:** Go to phone backup screenshots. You prepared for this.

---

## After Tomorrow

- Follow up by Thursday with the one-pager filled in
- Include: "Here's what you told us" + "Here's how DOCex addresses it"
- Offer: 30-min working session to config their org
- Wait for their move. Don't chase.

