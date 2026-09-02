# NEEM Demo Checklist — Print This

**Farid · September 2, 2026**

---

## Before You Leave Home

- [ ] Run DEMO_SETUP.sh (takes 15 min, tests everything)
- [ ] Verify OCR: `python3 -c "import fast_extract; print(fast_extract.ocr_available())"`
- [ ] Both terminals running locally (API on :8000, frontend on :3000)
- [ ] Signed in to http://localhost:3000 as demo@neem.org
- [ ] Laptop charged + charger in bag
- [ ] Phone has screenshots of all four screens (Field Receipts, Requisitions, Payments, Audit)
- [ ] Printed: this checklist + DEMO_PACK.md + NEEM_FOLLOWUP_TEMPLATE.md
- [ ] Water. You'll need it.

---

## During Setup (Venue)

- [ ] Laptop plugged in (not battery)
- [ ] WiFi checked (local demo, no network dependency, but you might need to send email after)
- [ ] Presentation screen / projector works with your laptop
- [ ] API and frontend terminals still running (test by visiting localhost:3000)
- [ ] Demo account still logged in
- [ ] Backup phone ready (screenshots accessible)

---

## The Demo (12–15 min)

**Segment 1: Field Receipts (2 min)**
- [ ] Navigate to Requisitions → Field Receipts
- [ ] Point at photographed market receipt
- [ ] Point at incomplete receipt (no vendor)
- Narrative: *"Amina photographs. No signal, no typing. System reads vendor, date, total off photo. Doesn't invent data."*

**Segment 2: New Requisition (2 min)**
- [ ] Navigate to Requisitions → New
- [ ] Fill in (Vendor, Amount ₦100k, Grant Code, Receipt)
- [ ] Submit
- [ ] Show policy checks pass
- Narrative: *"Policy checks fire instantly, not three days later."*

**Segment 3: Blocked Payment (5 min)** ⭐ This is the big one
- [ ] Navigate to Requisitions → Waiting on Me
- [ ] Open REQ-0002 (Northern Logistics, ₦140k, BLOCKED)
- [ ] Explain: "Charged to grant that closed Dec 2024. Donor rules block it."
- [ ] Try to Approve → Button is DISABLED
- [ ] Tick the check
- [ ] Write reason
- [ ] Name authority (e.g., "Finance Director")
- [ ] Approve
- [ ] Record payment
- Narrative: *"Can't override without: check ticked + reason written + authority named. Permanent record."*

**Segment 4: Audit (2 min)**
- [ ] Navigate to Audit
- [ ] Show verdict (audit-ready or N unexplained)
- [ ] Point out exception (the override you just made)
- [ ] Show who, why, authority all recorded
- Narrative: *"Auditor opens this. Every exception visible. Most systems record overrides. This one refuses unexplained ones."*

**Close (1 min)**
- No more clicks. Just talk.
- *"Code owns the numbers. Governance isn't optional."*

---

## Discovery Questions (10 min) — Ask ~8 of These

1. **"Walk me through the last payment that went wrong."** (Let them talk, 2 min)
2. "How many payments/month?"
3. "Field vs. vendor vs. payroll split?"
4. "Finance team size? Who approves what?"
5. "How do receipts move today?" (WhatsApp? Folder? Carrier pigeon?)
6. "What docs are required? Does that change by amount?"
7. "Do staff take cash advances? How long to retire?"
8. "Last audit findings? Unsupported? Missing docs?"
9. "Are thresholds written down or understood?"
10. **"If we built ONE thing for you in a month, what would it be?"** (Stop talking. Listen.)

---

## If They Ask

- **"Does it work offline?"** — Yes, KoboCollect backend built, field app connection finishing.
- **"Read our Excel / PDF?"** — Yes, offer to drop one in live.
- **"Duplicates?"** — Detected on vendor+amount, and receipt can only back one payment.
- **"Data safe?"** — Cloud, one instance per org, data never mixes.
- **"Price?"** — ₦250k/month. Anchor: one audit finding costs more.

---

## If Something Breaks

| Problem | Fix | Backup |
|---------|-----|--------|
| Blank screen | Check both terminals running | Show screenshot |
| Can't sign in | `python3 demo_seed.py` | Skip to backup slides |
| Data wrong | `python3 demo_seed.py --reset` | Show screenshot |
| OCR failed | Tesseract issue, but show photo anyway | Show screenshot |
| API slow | Say "local demo, no network dependency" | Keep going |
| Total meltdown | Use phone screenshots for all four screens | Don't panic, talk through it |

---

## After Demo

- [ ] Hand them NEEM_FOLLOWUP_TEMPLATE.md (fill in their answers as they talk)
- [ ] Get their email
- [ ] Say: *"I'll send this over by EOD. We can do a 30-min working session next week to config your org."*
- [ ] Say: *"I'll follow up by Thursday."*

---

## After You Leave

- [ ] Email them the filled one-pager WITHIN 24 HOURS
- [ ] Subject: "NEEM — DOCex Demo Summary (Sept 2)"
- [ ] Include: what they told you + how DOCex addresses it + next steps + your email
- [ ] Wait for their move. Don't chase.
- [ ] Update CLAUDE.md with how it went.

---

## Tone Reminders

✅ Confident (the system works)  
✅ Specific (not vague promises)  
✅ Honest ("KoboCollect is finishing, not done")  
✅ Listen more than talk  
✅ Let them want more

❌ Don't oversell  
❌ Don't demo features not built  
❌ Don't promise a date unless you mean it  
❌ Don't talk over them during Q10

---

## Your Backpocket

If they seem hesitant or want to dig deeper:

> *"Next week I can do a 30-minute session — walk through your grant codes, your approval chain, your required documents. That's where you see if this actually fits your org."*

That's the move. You're not selling. You're letting them test.

---

## Good Luck

You've tested this. The code works. The questions are sharp. Walk in calm.

The system is real. The story is theirs. You're just showing them how to stop losing money.

**Go build something great with them.**

---

*(Saved: Sept 2, 2026 · Contact: faridmichika@gmail.com)*
