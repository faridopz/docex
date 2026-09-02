# NEEM Demo Pack — September 2, 2026

**Demo time: 12–15 minutes · Discovery time: 10–15 minutes · Total: 25–30 minutes**

---

## Pre-Demo Checklist (Tonight)

These are non-negotiable. Do them before tomorrow.

```bash
cd ~/Desktop/docex
python3 demo_seed.py
python3 make_demo_docs.py
cd web && npm run build
```

Then verify in two terminals:

**Terminal 1:**
```bash
cd ~/Desktop/docex && uvicorn api.main:app --reload --port 8000
```

**Terminal 2:**
```bash
cd ~/Desktop/docex/web && npm run dev
```

Sign in at http://localhost:3000/login as `demo@neem.org` / password shown in setup output.

**Critical check:**
```bash
python3 -c "import fast_extract; print('OCR ready:', fast_extract.ocr_available())"
```

Must say `True`. If False: `brew install tesseract`, then restart API.

---

## Why Demo from Laptop (Not Live URL)

1. **Live site is behind** — Vercel build hasn't shipped the latest code
2. **Render free tier sleeps** — 30–50 second blank screen mid-demo is a killer
3. **Venue wifi** — local needs zero network

If they ask: *"It runs in the cloud; I'm showing locally so we're not at the mercy of wifi."* Completely normal.

---

## The Story (In Their Words)

> "Amina photographs a handwritten receipt in a market. No signal, no typing. DOCex reads the vendor, date and total off the photograph. When she gets signal, it syncs automatically. Back in Abuja, finance sees every receipt with its audit trail: who submitted, what was missing, who filled the gap, on whose authority. If a receipt is charged to a grant that closed last year, the system blocks it because donor rules matter. Finance approves with reasons attached. Most systems record an override somewhere. This one refuses an unexplained one."

The story has three beats:
1. **Field capture** — offline receipts, automatic sync
2. **Governance** — missing data flagged, not invented; policy enforced
3. **Audit** — every exception recorded with who, why, authority

---

## Demo Flow (12–15 min)

### Segment 1: Their Pain Point (3 min) — Field Receipts

**Navigation:** Open http://localhost:3000/login and sign in  
**Then:** Requisitions → Field Receipts

Point at the **photographed market receipt**.

> "Amina photographs a handwritten receipt in a market. No signal, no typing. The system reads the vendor, the date and the total off the photograph. It flags data quality issues — but doesn't invent a vendor to fill the gap."

Then the **incomplete receipt** (no vendor).

> "This one came in missing the vendor. Which is normal, and the system says so rather than rejecting it. It doesn't guess a supplier name. The blank is the honest answer, and finance can see exactly what's missing."

**Timing:** 90 seconds. That is their stated problem, solved.

---

### Segment 2: Raise a Payment (3 min) — Policy & Approvals

**Navigation:** Requisitions → New

Fill in a simple requisition:
- **Vendor:** "Sahel Catering Services"  
- **Amount:** ₦100,000 (keep it safe)  
- **Grant Code:** "GF-2026-TB"  
- **Project Code:** "P-101"  
- **Receipt:** Attach one of the demo docs  
- **Submit**

> "Policy checks run the *moment* it's submitted — not three days later when an approver bounces it back. Whoever raised it sees the problem while the invoice is still open in front of them."

Show the policy checks firing. They should all pass (amount is low, grant is current).

---

### Segment 3: The Blocking Check (5 min) — Accountability

**Navigation:** Requisitions → Waiting on Me

Open **REQ-0002 (Northern Logistics, ₦140,000)** — this one is deliberately blocked.

> "This one is charged to a grant that closed in December 2024. Donor rules only allow costs incurred inside the agreement period, and charging outside it is one of the most common audit findings there is. The system caught it by comparing two dates — code owns the number, not the LLM."

Try to **Approve**. The button is disabled.

> "I can't approve this, and neither can anyone else, until three things exist: the specific check ticked, a written reason, and the authority it's being released under. That's role-based — not a suggestion."

**Tick the check.** Write a reason. Name the authority (e.g., "Finance Director override"). Approve.

> "That's now permanently attached to the payment, against my name."

Record payment with any bank reference (e.g., "TXN-001").

---

### Segment 4: Audit (3 min) — The Close

**Navigation:** Audit

> "This is what your auditor opens. Every exception, who released it, why, and under what authority. The verdict at the top is the whole product: if a single payment went out over a failing check with no explanation, this reads 'N unexplained' in red and you fix it before the auditor arrives, not after."

> "Most systems record an override. This one refuses an unexplained one. Governance isn't optional — it's baked in."

---

## If They Ask (Prepared Answers)

**"Does it work offline?"**

Yes — that's the KoboCollect integration. The backend is built and tested; the field app connection is still being finished. Fieldworkers capture on KoboCollect offline as they already do, and receipts log automatically as soon as a phone gets signal.

**"Can it read our Excel vouchers / PDF invoices?"**

Yes. Excel, Word, PDF, CSV, photos, scans. Offer to drop one of *their* files in live if you have one. It handles a scanned PDF and a phone photo through OCR.

*(Note: It reads the labelled TOTAL correctly and ignores SUBTOTAL — a real bug found and fixed this week. Don't promise perfection on an unseen document. "Let's see" is a strong answer.)*

**"What happens if two people submit the same invoice?"**

Duplicate detection on vendor + amount inside a configurable window. And a receipt can only back one payment — attach it to a second and it blocks.

**"Is our data safe / where does it live?"**

Runs in the cloud, one instance per organisation, your data never mixes with another org's. Durable Postgres storage is the next infrastructure piece. Don't overclaim here.

**"How much?"**

₦250,000/month for an org your size. Anchor on prevention: one audit finding costs vastly more than a year of this.

---

## If Something Breaks

| Problem | Fix |
|---------|-----|
| Blank screen / API errors | Check both terminals are running. Frontend talks to `localhost:8000`. |
| Can't sign in | `python3 demo_seed.py` again — resets the password. |
| Data looks wrong | `python3 demo_seed.py --reset` — rebuilds in ~5 seconds. You can do this between meetings. |
| OCR shows nothing on photo | Tesseract isn't installed. `brew install tesseract`, restart the API. Check tonight, not tomorrow. |
| Worst case | Take screenshots of all four screens tonight. Keep in your phone as backup. Five minutes of insurance. |

---

## The Ten Discovery Questions

Ask **maybe eight**. Not all. Let them talk. The single best question is first.

### Q1: The Incident (Best Question)

> "Walk me through the last payment that went wrong. Not a typical one — the one that caused the most trouble."

*Why:* People describe processes idealised. They describe incidents accurately. The incident is where the product earns its money.

---

### Q2: Workload Shape

> "How many payments does finance process in a month? Roughly."

*Why:* Sizes the problem. Under ~50/month = Starter tier. 50–200 = ₦250k lands.

---

### Q3: Payment Types

> "What's the split between field expenses, vendor invoices, and staff payments?"

*Why:* If most spend is field receipts, lead with that. If invoices dominate, lead with approval workflow.

---

### Q4: Finance Team Structure

> "How many people are in finance? How many raise requests but don't approve?"

*Why:* Tells you approval-chain complexity. "We have one person doing everything" = different product than "eight people across four departments."

---

### Q5: The Receipt Problem (Their Pain Point)

> "When a fieldworker buys something in the market, what happens to that receipt between purchase and when finance sees it?"

*Why:* This is the NEEM story. Listen for: WhatsApp photos, handwritten, slow, missing info, auditor complaints.

---

### Q6: Document Tiering

> "What documents must be attached before a payment goes out? Does that change with the amount?"

*Why:* This is the banded-rules gap. If they answer with a specific naira figure, **write it down** — that's the next feature I'd build.

---

### Q7: Advances & Retirement

> "Do staff take cash advances for field activity? How long do they have to retire them?"

*Why:* Usually lands. The advance-aging report is cheap to build and makes an invisible problem visible.

---

### Q8: Audit Findings

> "What were the findings last time you were audited? Be specific."

*Why:* If they say "unsupported expenditure" or "missing documentation," DOCex is aimed exactly at that. Say so plainly. If they say "we've never had a finding," pivot to time saved.

---

### Q9: Policy Clarity

> "Are your approval thresholds written down, or are they understood?"

*Why:* "Understood" means the chain lives in someone's head. Configuring DOCex surfaces disagreements between people who thought they agreed. That's work, but it's valuable work.

---

### Q10: The Closing Question

> "If we built one thing for you in the next month, what would make the biggest difference?"

*Why:* Then stop talking. Whatever they say next is your roadmap and it's worth more than anything in this document.

---

## The Pattern (How It All Fits)

1. **Segment 1** answers their stated pain point (receipts, audit trail)
2. **Segment 2** shows they can see policy problems *before* approval (not three days later)
3. **Segment 3** proves accountability is structural (can't approve without reason + authority)
4. **Segment 4** shows the auditor's view (complete, verifiable, exception-first)
5. **Questions 1–8** map what they said to what DOCex does
6. **Questions 9–10** find the gaps you close next

Everything reinforces: **Code owns the numbers. Governance isn't optional.**

---

## Tone

- Confident, not defensive
- Specific ("the most common audit finding is…"), not vague
- Honest about what's not done ("KoboCollect sync is still being finished")
- Listen more than you talk — especially after Q1

When they ask about a feature not built: *"Not yet, here's the thinking…"* beats a vague yes.

---

## The Close

> "You know your process better than anyone. These questions help us build something that actually fits how you work — not how we assume you work. That's the difference between a tool and a product."

Then: send over a one-pager with your email, their answers, and next steps.

---

**You've got this.** The system works. The questions are sharp. Run the dry run tonight and you'll walk in calm tomorrow.
