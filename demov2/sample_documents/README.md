# Sample Documents — for seeding & live demo

Four draft requisition bundles, built to match TA Connect's real payment
types and required-documents checklist from `org_profile.json`. All fake
data (vendors, names, amounts) — safe to upload to the demo instance.

| # | Folder | Payment type | Intended outcome | Use for |
|---|--------|-------------|-------------------|---------|
| 1 | `1_procurement_clean/` | Procurement Payment | **Approved** — PO, Invoice, and GRN all match (vendor, amounts, items) | Flow 2 "clean" walkthrough; seed as the requisition you later move to Approved/Paid |
| 2 | `2_procurement_flagged/` | Procurement Payment | **Flagged** — PO + Invoice only, GRN deliberately missing (no proof of delivery) | Flow 2 "flagged" walkthrough; seed as the Needs Attention card; use for the Request Clarification demo |
| 3 | `3_vendor_blocked/` | Vendor Payment | **Blocked** — vendor (QuickFix Ventures) not on the approved vendor list, no PO | Optional third example if you want a hard block, not just a flag |
| 4 | `4_consultant_clean/` | Consultant Payment | **Approved** — signed contract, invoice, and deliverables report all consistent | Seed as a second, different-looking card so the Pipeline board isn't all one payment type |

## What's in each folder (document chain)

Each bundle (except #3) now starts with the **Payment Requisition Form** —
the internal document that actually kicks off a payment: who's asking, which
donor's funds, why, and who approved the request itself, *before* Finance
raises a PO or voucher. This is the `payment_subject` artifact TA Connect
calls a "Payment requisition," and it's what populates the requisition
context (date, donor, purpose, items requested, requested/approved by) on
the compliance check record.

- `1_procurement_clean/` — **0** Requisition → **1** PO → **2** Invoice → **3** GRN
- `2_procurement_flagged/` — **0** Requisition → **1** PO → **2** Invoice *(no GRN)*
- `3_vendor_blocked/` — **1** Invoice → **2** Proof of Service *(no requisition, no PO — that's the point, see Notes)*
- `4_consultant_clean/` — **0** Requisition → **1** Contract → **2** Invoice → **3** Deliverables Report

| # | Folder | Payment type | Intended outcome | Use for |
|---|--------|-------------|-------------------|---------|
| 1 | `1_procurement_clean/` | Procurement Payment | **Approved** — requisition, PO, Invoice, and GRN all match (vendor, amounts, items) | Flow 2 "clean" walkthrough; seed as the requisition you later move to Approved/Paid |
| 2 | `2_procurement_flagged/` | Procurement Payment | **Flagged** — requisition + PO + Invoice only, GRN deliberately missing (no proof of delivery) | Flow 2 "flagged" walkthrough; seed as the Needs Attention card; use for the Request Clarification demo |
| 3 | `3_vendor_blocked/` | Vendor Payment | **Blocked** — vendor (QuickFix Ventures) not on the approved vendor list, no requisition, no PO | Optional third example if you want a hard block, not just a flag |
| 4 | `4_consultant_clean/` | Consultant Payment | **Approved** — requisition, signed contract, invoice, and deliverables report all consistent | Seed as a second, different-looking card so the Pipeline board isn't all one payment type |

## How to use with RUN_OF_SHOW.md / GO_NO_GO.md

1. On `/compliance/submit`, pick the matching **Payment Type** from the
   dropdown (Procurement Payment / Vendor Payment / Consultant Payment) —
   the required-documents checklist will match what's in each folder.
2. Upload **every file** in that bundle's folder, including the `0_Payment_
   Requisition_*.pdf` where present — it's not one of the payment type's
   "required documents" per `org_profile.json`, but it's what the officer
   would actually have received first, and it's the source for the
   requisition-context fields on the check record.
3. Give it a label, e.g. "Greenline Office Supplies — June restock" for
   bundle 1, and submit.
4. Repeat for each bundle you want seeded (see GO_NO_GO.md §2 for which
   ones to move to which pipeline stage).

## Notes

- Bundle 2 is missing its GRN **on purpose** — that's what should trigger a
  flag/insufficient-evidence verdict citing missing proof of delivery.
- Bundle 3 has no requisition, no PO, and an unapproved vendor **on
  purpose** — it's framed as an emergency direct engagement with nothing on
  file, which is the block case per the org's "must be from the approved
  vendor list" rule.
- Bundles 1 and 4 are internally consistent end to end (requisition →
  final document all agree) — good for the "here's what a boring, correct
  requisition looks like" beat before you show a flagged one.
- The Payment Requisition Form's context fields (donor, purpose, requested/
  approved by) aren't rendered in the check-detail UI yet — the data model
  captures them, but no component displays them today. Including the form
  is still worthwhile for realism and for whatever the extraction engine
  picks up, just don't expect a dedicated "requisition context" panel on
  screen when you show it.
- These are demo-only fabrications, not real TA Connect vendors or staff.
