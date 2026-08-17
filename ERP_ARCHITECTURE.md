# DOCex — AI-Native Smart ERP Architecture

DOCex evolves from a document checker into an **AI-native ERP** for donor/NGO
finance operations. Same founding law as the compliance engine:
**deterministic-first — code owns every number, match, and rule; AI reads, classifies,
interprets, and drafts.** The "AI-native" part is that each business function is a
**skill** executed by an **agent**, coordinated over a shared data + event backbone —
not a pile of hardcoded forms.

Anchored on the real TA Connect workflow: participants submit receipt bundles;
finance reconciles transport + per-diem against a schedule; a consolidated payment
voucher is raised; compliance and finance review and approve; everyone tracks status
live.

---

## 1. Skills vs Agents (how we mean it)

- **Skill** = a versioned capability package: instructions + the deterministic tools it
  may call + its I/O contract. Reusable, testable, swappable. (e.g.
  `per-diem-reconciliation`, `compliance-check`, `attendance-match`.)
- **Agent** = a runtime worker that executes one workflow step by invoking one or more
  skills, reading/writing shared data, and emitting events. Agents are cheap, single-
  purpose, and hand off to each other via the workflow state machine.
- **Deterministic core** = plain code the skills call for anything numeric or exact.
  The AI never asserts a number; it cites the source and lets the core compute.

---

## 2. Layered architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ PRESENTATION   Next.js · per-department dashboards · auth/RBAC │
│                live status timelines · notifications inbox     │
├──────────────────────────────────────────────────────────────┤
│ ORCHESTRATION  Workflow state machine · transaction refs       │
│                event bus ("Uber tracking") · agent router      │
├──────────────────────────────────────────────────────────────┤
│ AGENTS         Intake · Per-Diem/Travel · Compliance ·         │
│                Attendance · Voucher/Approval · Notification     │
├──────────────────────────────────────────────────────────────┤
│ SKILLS         classify-docs · extract-receipts ·              │
│                per-diem-reconciliation · compliance-check ·     │
│                attendance-match · voucher-build                 │
├──────────────────────────────────────────────────────────────┤
│ DETERMINISTIC  per-diem calc · transport tally · 3-way match · │
│ CORE           dedup · attendance-day counter · rules engine · │
│                reference generator                             │
├──────────────────────────────────────────────────────────────┤
│ DATA + EVENTS  Postgres (Supabase) · file storage (S3) ·       │
│                event log/audit trail · notification queue      │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. The agents

| Agent | Job | Skills it runs | AI vs code |
|-------|-----|----------------|------------|
| **Intake** | Ingest a participant's folder + schedule row; classify each file (receipt / voucher / attendance / context note); extract structured fields | `classify-docs`, `extract-receipts` | AI reads scans + notes; code stores structured records |
| **Travel & Per-Diem** | Match receipts ↔ claimed transport/printing/etc.; apply per-diem rules; flag gaps | `per-diem-reconciliation` | Code computes diem + totals; AI reads messy receipts + context note |
| **Compliance** | Check the payment bundle against the org rulebook (existing engine) | `compliance-check` | Deterministic rules in code; AI for semantic clauses only |
| **Attendance** | Match people on the payment schedule vs attendance records; verify days joined | `attendance-match` | Code counts/joins days; AI resolves name/ID fuzziness |
| **Voucher & Approval** | Consolidate approved participant lines into one payment voucher; drive the approval route | `voucher-build` | Code totals + generates; AI drafts summaries |
| **Notification** | Emit status updates on every state change; route to the right department | — (listens to event bus) | Code; AI optional for human-readable digests |

---

## 4. Travel & per-diem reconciliation (the new core workflow)

Inputs per participant: a **schedule row** (travel days, per-diem rate, transport/car
allowance, what the org already covers), a **receipt PDF bundle**, and a **context note**
("attended 3 meetings, paid for printing → refund").

Flow:
1. **Intake** classifies + extracts receipts into structured records
   (`{vendor, date, amount, currency, category, source_ref}`).
2. **Deterministic core** computes:
   - `transport_claimed` vs `sum(transport receipts)` — must reconcile within tolerance.
   - **Per-diem**: `days × rate`, with the org rule applied — e.g. **advance = 75% of
     daily diem when TA Connect already covers that cost** (food at the hotel, etc.).
     *(Exact rule table to be pinned down with finance — see open questions.)*
   - Reimbursables from the context note (printing, etc.) matched to receipts.
3. AI only interprets the **context note** and any **unreadable/ambiguous receipt** — it
   never sets the payable amount.
4. Output: a per-participant line — `payable`, `evidence[]`, `flags[]`, `confidence` —
   feeding the voucher.

Open question to lock with finance: the precise per-diem rule set (advance %, when the
75% applies, top-up vs deduction, currency handling).

---

## 5. Transaction references + workflow state machine

Every payment/check is a **transaction** with a human reference (e.g. `C24`) and a state:

```text
SUBMITTED → INTAKE → COMPLIANCE_REVIEW → FINANCE_REVIEW → APPROVAL → PAID
                └─────────── RETURNED (with reason) ──────────┘
```

Each transition writes an immutable audit event `{txn, from, to, actor, dept, note, ts}`.
The dashboard reads state directly: *"C24 — pending compliance, viewed by compliance."*
The reference is generated by the deterministic core, never by the AI.

---

## 6. Notifications — the "Uber tracking" model

An **event bus** sits under the state machine. Every transition publishes an event; the
**Notification agent** fans it to the relevant department's inbox (in-app) and email.
So *compliance approves → finance is notified instantly*, and each transaction has a live
timeline the way you watch an Uber order progress. Notifications are event-driven and
deterministic; AI is optional only for turning a batch of events into a readable digest.

---

## 7. Departments, logins, dashboards (RBAC)

- **Departments/roles:** Compliance, Finance, Program/M&E, Approvers/Management — each user
  belongs to a department with a role (viewer / reviewer / approver / admin).
- **One platform, isolated views:** per-department dashboards (my queue, pending on me,
  what I approved, SLA/aging), row-level security so a department sees only what it should.
- **Attendance ↔ payment matching** lives in the Program/M&E + Finance shared view: confirm
  each participant joined for the days being paid before the voucher clears.

---

## 8. Data models (new)

```text
Participant     id, name, org, bank_ref
Event           id, code, title, dates, per_diem_rate, org_covers[]
Attendance      participant_id, event_id, days_present[], source_ref
ScheduleRow     participant_id, event_id, travel_days, transport_claimed, notes
Receipt         id, participant_id, vendor, date, amount, currency, category, source_ref
TravelClaim     participant_id, event_id, transport_payable, per_diem_payable,
                reimbursables[], evidence[], flags[], confidence
Voucher         id, ref, event_id, lines[TravelClaim], total, status
Transaction     ref (C24), type, state, dept_owner, history[Event], created_by
Approval        txn_ref, dept, actor, decision, note, ts
Notification     id, txn_ref, to_dept, kind, body, read, ts
User / Dept / Role   RBAC
```

---

## 9. Where AI is allowed vs never

**AI does:** classify documents, OCR/read messy scans, interpret free-text context notes,
resolve fuzzy name/ID matches for attendance, judge genuinely semantic policy clauses,
draft human summaries/digests.

**AI never:** compute a payable, sum receipts, apply the per-diem %, count attendance days,
decide a hard threshold rule, generate a reference, or set a final verdict. A code result
always overrides the model.

---

## 10. Build phases (re-sequenced)

- **Phase A — Backbone:** auth + departments/RBAC, transaction reference + state machine,
  event bus + notifications, per-department dashboard shell. *(Nothing works without the
  spine and the tracking.)*
- **Phase B — Travel/per-diem engine:** deterministic per-diem calculator + transport/receipt
  reconciliation, `classify-docs` + `extract-receipts` + `per-diem-reconciliation` skills,
  Intake + Travel agents. Excel import of the finance schedule, Excel export of results.
- **Phase C — Voucher + approval routing:** `voucher-build`, Voucher/Approval agent, the
  cross-department approval flow with notifications.
- **Phase D — Attendance matching:** `attendance-match` skill + agent; block/flag vouchers
  where paid days ≠ attended days.
- **Phase E — Compliance integration:** fold the existing compliance-check engine in as a
  first-class agent on the same state machine (reuse `PERF_ROADMAP.md` optimisations).

---

## 11. Open questions to lock before coding

1. Exact **per-diem rule table** (advance %, when 75% applies, top-up vs deduction, currency).
2. **Approval chain** — who approves after finance (single approver, threshold-based, board)?
3. **Attendance source of truth** — sign-in sheets (scanned), a register, or an external system?
4. **Notification channels** — in-app only first, or email/WhatsApp too?
5. **Deployment reality check** — `CLAUDE.md` says AWS ECS; the perf notes referenced Render.
   Confirm the live target before infra work.

---

*Deterministic-first is the moat. The AI makes the ERP fast to build and forgiving of messy
real-world documents; the deterministic core makes it trustworthy with money.*

---

## Build status (as of 2026-08-13)

**Backend — built & tested (all suites green):**
- `per_diem.py` — per-diem entitlement (coverage-weighted; food covered → 75%) + combined
  participant payable. Data-driven from the rate card. `test_per_diem.py`.
- `RateCard` extended with the per-diem policy (component split + advance %); rate-card
  routes expose it; `api/per_diem_routes.py` `POST /per-diem/compute`.
- `transactions.py` — reference generator (C24/P/V/T), state machine, append-only audit,
  locked monotonic counter. `test_transactions.py`.
- `notification_center.py` — in-app, event-driven per-department feed; `notify_transition`
  fans each state change to the department that must act. `test_notifications_flow.py`.
- `vouchers.py` — consolidate payables → voucher → submit opens a routed transaction.
  `test_vouchers.py`.
- `auth.py` — users/departments/roles, PBKDF2 hashes, HMAC sessions; `api/auth_routes.py`
  login/register/me/users + `GET /dashboard` aggregation + RBAC deps. `test_auth.py`.
- `api/transaction_routes.py`, `api/voucher_routes.py` wired into `api/main.py`.
- `test_integration_erp.py` — full HTTP flow: register→login→voucher→submit→compliance→
  finance→dashboard, incl. 401/403/409 paths.
- Runtime dirs (`transactions/ notifications/ users/ vouchers/`) + secrets
  (`.auth_secret`, `.approval_secret`) gitignored.

**Remaining — frontend (task #6):** rewire `web/lib/auth.tsx` (demo front door → real
`/auth/login` with token + department/role); add `lib/api.ts` calls for the new endpoints;
build the per-department dashboard, notification bell, transaction status timeline, and the
voucher/per-diem entry screens.
