# Demo Pack Index — What to Read When

**Today (Sep 2):** Read in this order.  
**Tonight:** Run DEMO_SETUP.sh.  
**Tomorrow:** Print DEMO_CHECKLIST.md and use DEMO_TIMING.md.

---

## Today (Read First)

### 1. **DEMO_PACK.md** (Read First — 10 min)
The master document. Everything patterned and together.
- The story (why field receipts matter)
- The four-segment demo flow
- Pre-demo checklist (tests everything)
- The 10 discovery questions
- How it all fits together

**Use case:** Ground truth for the demo. Read this and you know what you're doing.

---

### 2. **DEMO_CHECKLIST.md** (Print This)
One page. Tickboxes. On your lap during the demo.
- Before you leave home (is OCR ready? API running?)
- During the demo (four segments, exact timing)
- Discovery questions (the 10, with what to listen for)
- If something breaks (quick fixes)
- After you leave (follow-up timeline)

**Use case:** Print this. Bring it. Tick boxes as you go.

---

### 3. **DEMO_TIMING.md** (Reference Tonight)
Exact timing for all 25–30 minutes. Stays on track.
- Setup (before they arrive)
- Demo breakdown (12–15 min)
- Questions breakdown (10–15 min)
- Red lights (when to shut it down)
- Watch-outs (REQ-0002 is blocked on purpose, etc.)

**Use case:** If you're worried about pacing, read this. It's your metronome.

---

## Tonight (Run This)

### **DEMO_SETUP.sh** (Automates Everything)
```bash
bash DEMO_SETUP.sh
```
Installs deps, seeds data, builds frontend, checks OCR.

One command. Takes 10 minutes. Tests everything.

**Do not skip this.** Do not hope it works tomorrow. Run it tonight.

---

## After Demo (Fill & Send)

### **NEEM_FOLLOWUP_TEMPLATE.md** (Email This)
A one-pager you fill in as you go.
- What we showed (4 segments)
- What you told us (table, empty today)
- What's built (checklist)
- What's coming (8 weeks out)
- Honest assessment (what's not ready)
- Next conversation (what to talk about)

**Use case:** Print one copy. Fill it in during/after the demo. Email by Thursday.

---

## Reference Docs (Already Exist)

These are in the codebase. You've read them. For reference only:

- **CLAUDE.md** — Project philosophy and architecture
- **SOUL.md** — Product beliefs and design system
- **ERP_ARCHITECTURE.md** — How the approval workflow works
- **test_extraction.py** — Why OCR matters (31 tests covering file handling)
- **test_engine_integration.py** — How receipt → requisition → payment works

**You don't need to re-read these before tomorrow.** They're background.

---

## Files Generated (For the Demo)

These auto-generate when you run DEMO_SETUP.sh:

- **demo_docs/** — 7 realistic documents to drag in live
  - 01_invoice_venue_hire.pdf (reads TOTAL, not SUBTOTAL)
  - 02_payment_voucher_training.xlsx (spreadsheets work)
  - 03_market_receipt_photo.png (OCR; the field story)
  - 04_transport_receipt_incomplete.txt (vendor blank, nothing invented)
  - 05_invoice_*_RESUBMITTED.pdf (duplicate detection)
  - 06_fuel_receipt_scan.pdf (OCR on scanned PDF)
  - 07_damaged_upload.pdf (says "damaged", not "vendor missing")

All fictional. Drag them in live during the demo to show versatility.

---

## The Reading Path (TL;DR)

**If you have 20 minutes:**
1. Read DEMO_PACK.md (the whole thing)
2. Print DEMO_CHECKLIST.md
3. Run DEMO_SETUP.sh tonight

**If you have 10 minutes:**
1. Read DEMO_PACK.md (the story + the four segments)
2. Skim DEMO_TIMING.md
3. Print and bring DEMO_CHECKLIST.md

**If you have 5 minutes:**
Just run DEMO_SETUP.sh tonight. Bring DEMO_CHECKLIST.md tomorrow. You'll be fine.

---

## The Pattern (Why This Works)

| Piece | Serves |
|-------|--------|
| DEMO_PACK.md | Thinking (what are we showing and why) |
| DEMO_CHECKLIST.md | Doing (tick boxes, stay on track) |
| DEMO_TIMING.md | Pacing (don't overstay any segment) |
| NEEM_FOLLOWUP_TEMPLATE.md | Close (what you send after) |
| DEMO_SETUP.sh | Confidence (everything tested tonight) |

Each one is lean, specific, printable. No fluff.

---

## After Tomorrow

1. Fill in NEEM_FOLLOWUP_TEMPLATE.md with their answers
2. Email by Thursday
3. Update CLAUDE.md with what you learned
4. Wait for their move

That's it. You're not chasing. You're building something real.

---

**Everything is ready. You've got this.**

Questions? Email faridmichika@gmail.com.

*(Created Sep 2, 2026)*
