# NEEM Follow-Up — Sept 10 Test Run Plan

**Meeting:** Initial demo + scoping  
**Next:** Test run with real docs + processes  
**Price:** ₦400k/month (consultant model)

---

## What NEEM Told Us

### Core Workflow
- **20 users** across finance, program, compliance
- **~100 payments/month** (estimate)
- **Field expenses + vendor invoices** (no staff payroll yet)
- **Multiple grants** (need grant period enforcement)
- **Audit-heavy** (frequent auditor visits, compliance-focused)

### Pain Points (Prioritized)
1. **Field receipts** — missing info, slow turnaround, no audit trail
2. **Approval delays** — payments stuck in someone's inbox
3. **Audit prep** — manual hunt for justification of exceptions

### Their Process
- Fieldworkers send WhatsApp photos + manual notes
- Finance manually logs in Excel, checks against policy
- Approvers email back yes/no (often lost)
- Auditor asks for everything; they scramble to assemble docs

---

## Features They Asked For (New)

### 1. Vendor Tax ID Verification ⭐
**What they need:** Validate vendor TIN against FIRS registry before payment

**Use case:** Audit requirement. Prove vendor is legitimate + registered.

**How to build:**
- Manual entry + validation (easy, 1 day)
  - User enters TIN, system checks format
  - Flag if unregistered vendors are used
  - Report shows all vendors + their registration status
- FIRS API integration (harder, 3-5 days)
  - Real-time lookup against FIRS database
  - Automatic blocking of unregistered vendors (or warning)

**Recommendation for Sep 10:** Start with manual validation (validate format, store TIN, report on it). FIRS API as phase 2 if they want.

**Cost:** Included in ₦400k if manual validation. +₦50k/month if FIRS API integration.

---

### 2. End-of-Month Payment Reconciliation ⭐

**What they need:** Match requisitions (what we promised to pay) vs. actual bank transactions (what we paid)

**Use case:** Monthly close. Prove all approvals resulted in actual payments. Catch stuck/missing payments.

**How to build:**
- Import bank statement (CSV from their bank)
- Match requisitions to bank transactions by:
  - Vendor name (fuzzy match)
  - Amount
  - Date (within 3-day window)
- Flag unmatched:
  - Requisitions not yet paid
  - Bank payments with no requisition (rogue transactions?)
- Report: reconciliation status, gaps, exceptions

**Recommendation for Sep 10:** Design this together using their actual bank statement format. Build in phase 2 (after core system is live).

**Cost:** ₦150k to build. Included in ₦400k after first month.

---

### 3. Timesheet Integration ⭐

**What they need:** Link staff timesheets to per-diem payments / advance tracking

**Use case:** Prove staff worked the days they claimed per-diem for. Audit trail for advances.

**How to build:**
- Store basic timesheet data (staff, date, hours, project)
- When advance is submitted, check: "Did this person work on that project that week?"
- Link per-diem reimbursement to timesheet entry
- Audit trail shows: "Advance of ₦X approved for Y on [date], backed by timesheet entry for 8 hrs"

**Recommendation for Sep 10:** Understand their current timesheet process (do they have one? digital or paper?). Maybe it's out of scope for now.

**Cost:** Depends on their system. If they have digital timesheets, ₦200k to integrate. If paper, ₦50k to manually log. Phase 2 (nice-to-have, not blocking).

---

## What You're Building (For Sep 10)

**Confirm scope with them:**

| Feature | Status | Sep 10 Plan |
|---------|--------|-----------|
| Field receipts (photos + OCR) | ✅ Built | Test with their real docs |
| Requisition + approval workflow | ✅ Built | Test with their real process |
| Policy checks (amounts, grant periods) | ✅ Built | Tune to their thresholds |
| Audit trail (immutable, role-based) | ✅ Built | Verify meets auditor requirements |
| **Vendor tax ID verification** | 🟡 Design | Build manual version (phase 1) |
| **Payment reconciliation** | 🟡 Design | Understand their bank format (phase 2) |
| **Timesheet integration** | 🟡 Design | Understand their process (phase 2) |

---

## Sep 10 Agenda (Structure)

**1. Review their documents (30 min)**
- Bring sample field receipts (photos, handwritten, incomplete)
- Bring sample invoices (PDF, Excel, damaged)
- Bring sample bank statement (CSV format)
- Bring their most recent audit report

**2. Walk through your system with their data (30 min)**
- Upload a real field receipt, watch it process
- Create a requisition with their real approval chain
- Show policy checks fire correctly for their grant periods
- Show the audit trail

**3. Design the three new features (30 min)**
- **Vendor TIN:** Show a mockup of TIN validation. Confirm format + rules.
- **Reconciliation:** Review a bank statement. Understand their format. Map the logic together.
- **Timesheet:** Ask about their timesheet system. Confirm if it's blocking.

**4. Confirm the build plan (15 min)**
- Phase 1 (Weeks 1-4): Core system + manual TIN validation + training
- Phase 2 (Weeks 5-8): Payment reconciliation + any other quick wins
- Phase 3 (Weeks 9+): Timesheet integration + FIRS API (if they want)

**5. Lock in timeline & next steps (5 min)**
- Start date?
- Go-live target?
- Who's the point person on their end?

---

## Questions to Ask Sep 10

**On their process:**
- "Walk us through one real payment from receipt to bank. What steps? Who touches it?"
- "What does your auditor ask for first?"
- "Have you ever had a vendor who wasn't registered? What happened?"

**On the features:**
- "For vendor TIN — is this a blocker, or nice-to-have?"
- "For reconciliation — how often do you need this? Monthly? Weekly?"
- "For timesheets — do you have a system already? Digital or paper?"

**On the build:**
- "When do you want to go live?"
- "Who will be the day-to-day contact for testing and questions?"
- "Do you have a IT person who can help with database setup + backups?"

---

## Your Prep (Before Sep 10)

- [ ] Read their audit report (if they share it)
- [ ] Understand FIRS vendor verification (quick research)
- [ ] Look up common bank statement formats in Nigeria
- [ ] Design a simple TIN validation UI
- [ ] Create a reconciliation mockup (just draw it on paper)
- [ ] Have sample field receipts + invoices ready to test with

---

## Pricing Note

**₦400k/month covers:**
- Core system (requisitions + approvals + audit trail)
- Manual vendor TIN validation
- 3 months of support
- Training + handoff

**Does NOT cover (quote separately):**
- FIRS API integration (+₦50k/month)
- Payment reconciliation (₦150k build, then included)
- Timesheet integration (₦50–200k depending on their system)
- Emergency support (+₦50k/month)
- Custom integrations (KoboCollect, bank API)

**So: ₦400k is solid for the base build. You'll upsell other features as needs become clear.**

