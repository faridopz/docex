# LIMA TECH — from here to sellable

Sequenced by **gate**, not by category. Each gate is a thing you cannot do
until the one before it is closed. A flat checklist hides that, and hiding it
is how people end up with a signed contract they cannot lawfully honour.

Not legal advice. This is the engineering and sequencing view, written so the
lawyer and the DPCO spend their time on judgement rather than on discovery.

---

## Two facts that shape everything below

**You will be a Data Processor of Major Importance.** The NDPC threshold is
processing the personal data of **more than 200 data subjects in six months**.
DOCex passes that almost immediately — a single multi-payee run carries up to
100 beneficiaries, plus NEEM's 20 staff, plus every vendor. Two payment runs
and you are over. That means **registration with the NDPC is an obligation,
not an option**, and 2026 is the year the Commission has signalled a shift
from education to enforcement. Budget for it and get it done rather than
hoping the threshold does not apply.

**A standard DPA requires something DOCex cannot currently do.** Every DPA
contains a return-or-delete clause: on termination, the processor returns or
securely deletes all personal data on the controller's instruction. DOCex has
**no deletion capability and no retention policy at all**. So this is not a
paperwork item — signing a normal DPA today would put you in breach of it on
day one. Deletion moves from "nice to have" to **blocking**, and it is on the
Gate 2 list below.

---

## How the DPA actually gets done

You do not write it, and you should not try. A DPA is a standard-shaped
instrument: the clause set is largely fixed, and the part that is specific to
you is an **annex describing the processing**. That annex is the work, and you
have already done most of it in `LIMA_TECH_DATA_FLOW.md`.

**The clauses your lawyer wraps around it** — the NDPA-specific ones to make
sure are present:

- **Roles.** States plainly that the customer is the Controller and LIMA TECH
  is the Processor, and that LIMA TECH processes only on documented
  instructions.
- **Sub-processing.** Names your subprocessors and requires the customer's
  prior written consent to add one, with each bound to equivalent obligations.
  Yours are Anthropic, Render, Vercel, Supabase, Paystack, and your mail
  provider.
- **International transfers.** Your API is in Frankfurt and document text goes
  to the United States. The DPA must state the conditions and safeguards for
  those transfers. This is the clause most likely to be negotiated.
- **Return or deletion on termination.** See above — build it before you sign
  it.
- **Audit rights.** The customer can verify your compliance.
- **Security measures.** A schedule of technical and organisational measures.
  Use the honest table in the data-flow document; claim nothing that is not
  already true.
- **Breach notification.** Who tells whom, how fast, with what information.
- **Assistance with data-subject requests.** Including your position on the
  erasure-versus-tamper-evident-audit-log conflict.

**What you supply, and in what order:**

1. `LIMA_TECH_DATA_FLOW.md` with every `[confirm]` closed.
2. A one-line role determination per data category — staff, vendors,
   beneficiaries — because beneficiaries may not resolve the same way as staff.
3. Your subprocessor register: name, purpose, country, and what each receives.
4. Your retention schedule, once the DPCO has set it.
5. The security schedule, ticking only what is true.

Then the lawyer drafts, and the DPCO reviews the annex and the transfer
assessment. Two professionals, one document, in that order.

---

## Gate 0 — can you legally trade? *(blocking everything)*

- [ ] CAC name search for LIMA TECH, with 2–3 backups ready
- [ ] Reserve the name
- [ ] Register as a private company limited by shares
- [ ] Business activity written broadly enough to own DOCex *and* future
      products, not "invoice checking"
- [ ] Incorporation documents received
- [ ] TIN registered
- [ ] Corporate bank account opened
- [ ] Domain and company email
- [ ] Ownership structure settled — you as sole shareholder for now; do not
      issue shares to friends who are helping, that is a vesting and
      shareholder-agreement conversation for later
- [ ] Bookkeeping set up from the first transaction, not retrospectively

---

## Gate 1 — can you sign a customer? *(needs Gate 0)*

- [ ] Lawyer briefed with the data-flow document, not a generic request
- [ ] Master Services Agreement
- [ ] Pilot agreement / order form — the short commercial document that names
      the price, term and scope
- [ ] Terms of Service
- [ ] IP provisions: **LIMA TECH owns the software; the customer owns its
      uploaded data; the customer's data is not yours to commercially exploit**
- [ ] NDA template
- [ ] Invoice template with your company details and TIN
- [ ] Offer letter for NEEM

Keep the commercial document separate from the DPA. Price is what they buy;
the DPA is how you are permitted to handle their information. Mixing them
makes both harder to agree.

---

## Gate 2 — can you accept production data? *(the real gate)*

Nothing real goes into the system until every one of these is done.

**Legal and privacy**

- [ ] Every `[confirm]` in the data-flow document closed
- [ ] NDPA role determination per data category
- [ ] Lawful basis for **beneficiary** data — the hardest one, and the one to
      raise first
- [ ] Cross-border transfer assessment (Frankfurt, and the US for AI)
- [ ] Subprocessor register written down
- [ ] Retention and deletion schedule agreed
- [ ] Data-subject request process, including the erasure/audit-log position
- [ ] Breach response process with named responsibilities and timings
- [ ] Privacy Policy published
- [ ] **NDPC registration** as a processor of major importance
- [ ] DPA signed with the customer
- [ ] Zero-data-retention arrangement pursued with Anthropic

**Software — the blocking ones**

- [ ] **Data deletion and retention.** Does not exist. Required by the DPA you
      are about to sign. Build it: delete an organisation's data on
      instruction, and enforce a retention period.
- [ ] **Customer data export on demand.** Partly there — PDF, Excel and a
      readable copy. Make it one deliberate action that produces everything.
- [ ] **Switch MFA on.** Built and currently off. Do not claim it until it is.
- [ ] **Leave the free hosting tier.** It sleeps and cold-starts. A finance
      officer meeting a blank screen concludes the system is broken.
- [ ] **Confirm encryption at rest** with each provider, in writing.
- [ ] **Verify a restore.** Not "backups run" — an actual restore, dated.
- [ ] **Vendor bank-account comparison.** The register verifies an account and
      the payment can still go elsewhere; the two numbers are never compared.
      This is the fraud that actually happens, and you are selling a control
      product.
- [ ] Rate limiting verified, not assumed
- [ ] Secrets rotated after all the sharing that happens during a build

---

## Gate 3 — can you charge with a straight face? *(product credibility)*

These are not legal blockers. They are what makes ₦450,000 a month obviously
fair rather than arguable.

- [ ] The three-quotes-above-₦200,001 rule actually enforced — it is currently
      a comment in NEEM's profile and checked nowhere, and it is the band most
      of their spending sits in
- [ ] Resolve the threshold conflict with NEEM (signed policy says three quotes
      from ₦200,001; the staff deck says memo-only to ₦499,999)
- [ ] SLA reminders and escalation — their second-ranked pain point, and
      nothing currently chases a stalled approval
- [ ] Vendor autofill from the register, so bank details are not retyped per
      payment
- [ ] The remaining six unanswered questions from the meeting brief: WHT rates,
      PAYE bands, GAPS debit structure, a real bank statement, the chart of
      accounts, and the definition of a collective default
- [ ] Field receipts — their **first**-ranked pain point, with nothing switched
      on for them today
- [ ] An independent audit of the codebase (`AUDIT_PROMPT.md` is written)

---

## Gate 4 — can you sell to client two without rebuilding? *(the business)*

- [ ] Onboarding runbook: policies in, profile out, live — with a real elapsed
      time attached to it
- [ ] Priced menu: what is included, what is configuration, what is custom and
      quoted separately
- [ ] A reference case study from NEEM, with their permission
- [ ] Support model written down — response times you can actually hit solo
- [ ] Unit economics per client: model spend, hosting, and the number that
      actually matters, support hours
- [ ] Price for client two and three set deliberately higher than NEEM's
      founding rate
- [ ] Staging environment, so a change is not tested in a client's production
- [ ] A second pair of hands identified before the support load arrives

---

## The shortest honest path

Gate 0 and the lawyer brief can start today and run in parallel. Gate 2's
software items — deletion, MFA, paid hosting, the vendor account fix — are a
few days of work and can happen while the legal drafting runs. Gate 3 is what
you do between signing NEEM and their first real payment run.

The one sequencing error to avoid: **do not let NEEM put real data in before
Gate 2 is closed.** It is the most tempting shortcut available, they are family
and they are keen, and it is the one that converts an ordinary commercial risk
into a regulatory one.

---

## Sources

- [NDPC guidance notice on registration of controllers and processors of major importance](https://ndpc.gov.ng/wp-content/uploads/2025/07/Updated-Guidance-Notice-on-Registtration-2024.pdf) · [KPMG summary](https://kpmg.com/ng/en/home/insights/2024/03/nigeria-data-protection-commissions-guidance-notice-on-registration-of-data-processors-controllers-of-major-importance.html) · [Registration guide](https://www.afriwise.com/blog/a-guide-on-the-registration-of-data-controllers-and-data-processors-of-major-importance-with-the-nigeria-data-protection-commission)
- [Drafting a compliant DPA in Nigeria](https://www.thestructurehq.com/publications/draft-data-processing-agreements-global-ndpa-compliance) · [DPA guide for Nigerian businesses](https://cacregister.com.ng/blog/data-processing-agreement) · [NDPA overview](https://securiti.ai/overview-of-nigeria-data-protection-act/)
- [Anthropic API data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
