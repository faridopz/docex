# LIMA TECH — DATA FLOW

**Purpose.** The briefing document to hand a lawyer and a privacy/DPCO
professional *before* asking either of them to draft anything. It describes
what DOCex actually does with customer information, taken from the code rather
than from intention.

**Status of this document.** Items marked **[confirmed]** were read from the
running system or the source. Items marked **[confirm]** are genuinely unknown
to the author of this document and must be established before it is relied on.
Nothing here should be presented to a client as a commitment until the
[confirm] items are closed.

---

## 1. The map

```
                        CUSTOMER (NGO staff, in Nigeria)
                                    │
                                    ▼
                    FRONTEND — Vercel (global edge)
                          no data stored here
                                    │
                                    ▼
                    API — Render, Frankfurt (EU)  [confirmed]
                                    │
            ┌───────────────┬───────┴────────┬──────────────────┐
            ▼               ▼                ▼                  ▼
      PostgreSQL      Supabase Storage    Audit log        Outbound calls
   (structured data)   (uploaded files)  (in Postgres)          │
                                                     ┌──────────┴──────────┐
                                                     ▼                     ▼
                                          Anthropic API (US)      Paystack (Nigeria)
                                          document text for       account number →
                                          policy interpretation   account-name check
                                                     │
                                                     ▼
                                              SMTP provider
                                         approval + notification email
```

---

## 2. What is held, and where

### 2a. PostgreSQL — the structured record

| | |
|---|---|
| **What** | Staff accounts (name, work email, department, role, PBKDF2 password hash, session tokens). Vendor and payee records (name, **bank account number**, bank name, **Tax Identification Number**, phone/email). Payment requests (amount, category, project and grant codes, description, budget line items, payment type). Approvals, comments, hold reasons. The hash-chained audit log, including **IP addresses** captured on emailed sign-off. Frozen transaction records after payment. |
| **Why** | It is the record of the payment workflow. The audit log exists specifically so a donor's auditor can answer "why was this approved, and by whom". |
| **Where hosted** | Managed PostgreSQL reached over a connection pooler. **[confirm]** which provider and, critically, **which region** — this determines whether it is a second EU transfer or somewhere else again. |
| **Who can access** | Application code, org-scoped on every read and write. LIMA TECH holds the database credential and can therefore read customer data — this must be disclosed to the customer, not hidden. **[confirm]** who else holds it. |
| **Retention** | No automated deletion is implemented. Records persist indefinitely. **[confirm]** what retention the customer actually requires — for donor-funded work this is often 5–7 years after grant close. |
| **Encryption** | In transit, TLS. At rest, **[confirm]** with the provider. |
| **Leaves Nigeria** | **[confirm]** — almost certainly yes. |

### 2b. Supabase Storage — the uploaded files

| | |
|---|---|
| **What** | The actual documents: invoices, memos, receipts, vendor quotes, bank statements, signed policies, beneficiary payment schedules. Whatever a user attaches. |
| **Why** | Evidence. A policy check that cannot read the document is worthless, and an auditor needs the original. |
| **Where hosted** | Supabase object storage, bucket `requisition-attachments`. **[confirm]** region. |
| **Who can access** | The application, using a storage credential held by LIMA TECH. Downloads go through an authenticated route, never a public URL. |
| **Retention** | No automated deletion. Files persist until the bucket is cleared. |
| **Encryption** | **[confirm]** at rest with Supabase. |
| **Leaves Nigeria** | **[confirm]** — depends on bucket region. |

### 2c. Audit log

Lives inside PostgreSQL, hash-chained and append-only by design: entries are
never edited or deleted, and tampering is detectable. **This is a deliberate
conflict with an erasure request** and the lawyer must be told: a data subject
asking for deletion cannot have audit entries removed without breaking the
integrity guarantee the product is sold on. Needs an agreed position.

---

## 3. Third parties (subprocessors)

### Anthropic — AI document interpretation

| | |
|---|---|
| **What is sent** | Extracted **text** from uploaded documents, plus the customer's own policy rules. Not the files themselves. The system prompt explicitly instructs the model to return short evidence references rather than paste whole documents back. |
| **Why** | Semantic judgement only — "does this pack satisfy this policy". All arithmetic, thresholds and matching are done in code and never by the model. |
| **Where** | United States. **An international transfer.** |
| **Training** | **Customer content sent through the commercial API is not used to train models**, under Anthropic's Commercial Services Agreement. |
| **Retention** | API inputs and outputs are deleted within **30 days** by default. A **zero-data-retention** arrangement is available for eligible commercial customers. |
| **Action** | Worth pursuing zero data retention before production data arrives. It is the strongest single sentence LIMA TECH can put in a DPA, and most competitors cannot say it. |

### Paystack — bank account verification

Sends an **account number and bank code**, receives the **account name** the
bank holds. Nigerian company, so likely no cross-border issue, but it is a
disclosed subprocessor and the customer should know their payee account numbers
are checked against a third party. Currently **[confirm]** whether the key is
set in production — the feature is inert without it.

### Render / Vercel — hosting

Render runs the API in **Frankfurt, EU [confirmed]**. Vercel serves the
frontend from a global edge network but stores no customer data. Both are
subprocessors.

### SMTP provider — outbound email

Approval requests and notifications. The body includes the payment reference,
payee name, amount and purpose, and a signed approval link. **[confirm]** which
provider, and where it sits.

---

## 4. The two findings that matter most

**Cross-border transfer is unavoidable and is not currently documented.**
Customer data leaves Nigeria the moment it is entered: the API is in Frankfurt,
and document text goes to the United States for interpretation. This is a
lawful-basis and transfer-mechanism question under the NDPA, not a technical
one, and it needs a real answer before production data arrives. Do not let a
privacy professional discover it after drafting.

**The system holds personal data about people who are not the customer's
staff.** Multi-payee payment runs carry beneficiary names, bank account
numbers, phone numbers and TINs — up to 100 per requisition. For an NGO working
with conflict-affected communities these are vulnerable data subjects who have
no relationship with LIMA TECH and have not consented to anything. This is the
highest-sensitivity category in the system and it should be the first thing the
privacy professional is pointed at.

---

## 5. Security posture — honest current state

Tick nothing on a client-facing schedule that is not **Yes** here.

| Control | State |
|---|---|
| Tenant isolation | **Yes** — every store read and write is org-scoped; covered by tests. |
| Role-based permissions | **Yes** — roles plus a department boundary on every approval action. |
| Audit logging | **Yes** — append-only, hash-chained, tamper-evident. |
| Password security | **Yes** — PBKDF2 hashing, HMAC session tokens, forced change on first login. |
| MFA | **Built, currently off.** Do not claim it until it is switched on. |
| Encryption in transit | **Yes** — TLS throughout. |
| Encryption at rest | **[confirm]** with each provider. |
| Secrets management | Environment variables in Render/Vercel. No secrets in git. |
| Backups | Nightly, off-host, with a verified restore. **[confirm]** the last verified restore date before stating it. |
| Data export | **Yes** — PDF, Excel and a full readable copy of the customer's records. |
| Data deletion | **No automated deletion or retention policy exists.** Needs building. |
| Rate limiting | **[confirm]** — quota tiers exist in code; enforcement unverified. |
| Vulnerability testing | **No** formal testing has been done. |
| AI data minimisation | **Partial** — text only, never files, and evidence references rather than whole documents. Not formally reviewed. |
| Durable storage | **Yes** — PostgreSQL. Previously ephemeral; this was fixed. |
| Uptime | **Weak** — hosting is still on a free tier that sleeps. Fix before go-live. |

---

## 6. What to ask each professional

**The lawyer.** Master Services Agreement, Data Processing Agreement, Terms of
Service, Privacy Policy, security schedule, breach notification, and IP
provisions establishing that LIMA TECH owns the software while the customer
owns its uploaded data and that the data is not LIMA TECH's to commercially
exploit. Give them section 3 of this document and ask specifically: *the
platform sends document text to a third-party AI provider in the United States
for interpretation — advise on NDPA implications, subprocessor requirements,
international transfer mechanism and the contractual protections we need.*

**The privacy/DPCO professional.** Give them sections 2 and 4. Ask for the
NDPA role determination (processor or controller, and for which categories),
the lawful basis for beneficiary data, the cross-border transfer assessment,
a retention and deletion policy the audit-log design can actually honour, and
the data-subject request process — including an agreed answer to the erasure
versus tamper-evident-audit-log conflict in section 2c.

---

## 7. Before this document is used

Close every **[confirm]**. Most are single questions to a hosting dashboard and
none of them should be guessed, because each one becomes a sentence in a
contract that a donor's auditor may one day test.
