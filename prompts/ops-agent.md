# Stream B3 — Operations Agent (Back-Office for the Founder)

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read: `/PLAN.md`, this file.

## What this stream delivers

A semi-autonomous agent for Farid's own back-office: invoicing,
contract drafts, pilot agreement generation, GitHub admin, expense
tracking. The stuff a solo founder would otherwise spend 4h/week on.

Different from the Sales Agent (B2) — that's outbound. This is inward-
facing: keep Farid's ops running while he builds product.

## Capabilities

### 1. Pilot agreement drafting

When a prospect moves to "Pilot scoping" in the Sales CRM:

- Read the prospect's research notes
- Generate a 2-page pilot agreement using the template in
  `/legal/pilot-agreement-template.md` (Farid to add)
- Save as Google Doc in DOCex > Sales > Pilot Proposals > {Org}
- Notion CRM gets updated with the doc URL

### 2. Invoice generation

When a pilot is signed and starts:

- Read the per-pilot scoped amount from the CRM "Pilot Amount" field
- Generate monthly invoice PDF using template + logo
- Save to Google Drive > DOCex > Customer Deliverables > {Org} > Invoices
- Email to the contact (DRAFT in Gmail, founder approves)

### 3. Expense tracking

Monthly:

- Read Farid's nominated expense email (forwarded receipts)
- Categorise: dev infra (Anthropic, Vercel, Railway, Supabase),
  sales (LinkedIn premium, Zoom), legal (Companies House), other
- Append to Notion > DOCex > Finance > Expenses database
- Generate monthly P&L summary

### 4. GitHub admin

Weekly:

- Read open issues with no triage label, suggest a label
- Identify stale PRs (>7d no activity)
- Generate a "this week in DOCex" changelog from git log

### 5. Customer success ping

Monthly per active pilot customer:

- Read their usage from analytics rollups
- Identify their top-used Co-Pilot
- Draft a personalised "thanks + here's what you accomplished this
  month" email
- Founder approves and sends

## Notion databases needed

| Database              | Schema                                                |
| --------------------- | ----------------------------------------------------- |
| Expenses              | Date, Amount (NGN/USD), Category, Vendor, Receipt URL |
| Invoices              | Date, Customer, Amount, Status, PDF URL               |
| Pilot Agreements      | Org, Stage, Start date, End date, Doc URL, Owner      |

(Build these as the agent needs them — don't over-engineer schemas.)

## Files

```
/agents/ops/draft_agreement.py        NEW
/agents/ops/generate_invoice.py       NEW
/agents/ops/track_expenses.py         NEW
/agents/ops/github_admin.py           NEW
/agents/ops/customer_ping.py          NEW
/legal/pilot-agreement-template.md    Farid to draft, agent fills
/legal/msa-template.md                Farid to draft
/templates/invoice-template.html      NEW (reportlab/weasyprint -> PDF)
```

## Definition of done

- [ ] Agreement generator produces a 2-page Google Doc per pilot
- [ ] Invoice generator produces a PDF + Gmail draft
- [ ] Expense tracker categorises forwarded receipts to Notion
- [ ] GitHub admin runs weekly digest to Notion
- [ ] Customer success ping drafts monthly emails

## Out of scope

- Payment processing (Paystack/Stripe handle that)
- Tax filing — accountant's job
- Hiring pipeline — defer until first hire
- Legal review — lawyer must approve every template before agent uses

## Anti-patterns

- DON'T send invoices automatically. Founder approves every one.
- DON'T draft contracts beyond the approved template. Custom terms
  go to a human lawyer.
- DON'T touch payment data directly. Read-only on financial sources.
