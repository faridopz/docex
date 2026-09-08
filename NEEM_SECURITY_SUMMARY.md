# DOCex — security and data handling

**Prepared for NEEM Foundation · September 2026**

You are about to put payment records into a system run by a small supplier.
This document answers the questions your auditor will eventually ask, including
the ones with uncomfortable answers.

Written plainly. Where something is not yet done, it says so.

---

## Where your data lives

A managed PostgreSQL database in Oregon (United States), operated by Render, on
infrastructure you can inspect: <https://render.com/security>.

Every record — requisitions, approvals, payments, the audit log, user accounts
— is stored under NEEM's organisation identifier. That identifier is part of
the storage key itself, not a filter applied afterwards. The distinction
matters: a filter can be forgotten in one query and leak another client's data.
A key cannot be. There is no query in DOCex that returns records without
naming the organisation they belong to.

**Documents you upload** are processed to extract text and are not retained
beyond the record they belong to.

---

## Who can see it

| Who | What they can see |
|---|---|
| Your staff | Only what their role allows (below) |
| Your administrator | All NEEM records; can create and remove accounts |
| DOCex (the supplier) | Full database access — see the section below |
| Anthropic | Document text sent for extraction only. Not used to train models. |
| Render | Infrastructure operator; encrypted at rest and in transit |
| Anyone else | Nothing. There is no route that returns data without a valid session. |

### The uncomfortable one

**DOCex staff can technically read your data.** Someone has to hold the
database credentials to operate, back up and repair the system, and today that
is one person. We are not going to claim otherwise.

What limits it: DOCex has no ability to *approve* anything. Approvals are
recorded against named user accounts in a hash-chained log, so a payment cannot
be authorised without a NEEM account doing it, and any tampering with history
is detectable (below). If you require technical separation beyond that — a
database only you hold the key to, or hosting inside your own cloud account —
that is a different arrangement, and it is worth discussing before you scale up
rather than after.

---

## Roles

| Role | Can |
|---|---|
| Viewer | See work. Change nothing. |
| Reviewer | Move work along. **Cannot release payment.** |
| Approver | Authorise payment within their step's limit. |
| Administrator | The above, plus accounts, departments and settings. |

Enforced on the server, from the signed-in session — not from anything the
browser sends. A reviewer cannot approve a payment by editing the page.

---

## Accounts and passwords

- Passwords are hashed (PBKDF2-HMAC-SHA256, 200,000 iterations, unique salt per
  user). **We cannot see your password.** Not in the database, not in logs, not
  if you ask us.
- Minimum ten characters with some variety. The common ones — `password123` and
  its relatives — are refused outright. A six-character minimum is the wrong
  policy for a system where one guessed password releases money.
- Your administrator creates accounts. DOCex generates a **one-time password**
  shown once. Until the person replaces it, their session can reach nothing
  except the password screen.
- Eight wrong attempts locks the account for fifteen minutes. Your
  administrator can clear it immediately.
- Signing out ends the session **on every device**, not just the one in front
  of you. So does changing your password. If you think someone has your
  password, changing it actually stops them.
- **When someone leaves**, your administrator deactivates them. Their sessions
  die immediately. Their record is kept, because your audit trail must still be
  able to say who authorised a payment in March about someone who left in
  April.

There is no "forgot password" email. That is a decision, not an oversight:
reset links depend on a mail provider and a mailbox, and whoever controls the
mailbox controls the account. Your administrator issuing a one-time password
keeps the recovery path inside your organisation.

---

## The audit trail

Every state change is appended to a log that is **never edited**. Each entry is
cryptographically chained to the one before it, so altering or removing a past
entry breaks the chain and the system says so.

What this gives you: if someone asks in October who approved a payment in
March, on what authority, and whether the record has been touched since — DOCex
answers all three, and can prove the third.

Payments are frozen at the moment they are made. The `/payments` screen shows
the checks **as they were applied**, not recomputed against today's policy. A
threshold changed in June does not silently rewrite what happened in March.

---

## Backups

- **Nightly**, automatically, stored outside the servers that run DOCex.
- **Verified by restoring.** Every backup is restored into a scratch database
  and checked. A backup nobody has restored is a belief, not a backup.
- Retained 90 days, plus monthly copies kept longer.
- Format is plain JSON Lines — one record per line, readable in a text editor.
  Deliberately not a proprietary snapshot, so **you can read your own records
  without DOCex and without Render**.
- Render additionally keeps its own database snapshots.

Last verified restore: **8 September 2026**. Ask us for this date at any time;
it is recorded in our deployment log and refreshed quarterly.

**If you want your own copy**, we will hand you an export on request, in that
same readable format. It is your data.

---

## In transit

HTTPS everywhere. The API accepts requests only from NEEM's DOCex address; a
page on any other site cannot call it with your session.

---

## Errors and monitoring

When something breaks, the error report carries the fault, not your data.
Vendor names, amounts, staff names, payment references and credentials are
stripped before anything leaves the system. The message you see quotes a
reference number to give us, rather than internal detail that would help
somebody attack it.

---

## What is NOT in place yet

Listed because you should decide with the real picture.

- **No staging environment.** Changes are tested by us and then deployed. A
  second instance for rehearsing changes is next; until then we deploy
  cautiously and can roll back within minutes.
- **No external uptime monitoring.** We are alerted to crashes, not yet to the
  system being unreachable. Being built.
- **Notifications and vouchers are not yet on durable storage.** Requisitions,
  approvals, payments, the audit log and user accounts all are. Notifications
  and vouchers are still written as files and could be lost in a redeploy. They
  are working records, not financial ones, and the fix is scheduled.
- **Tax ID checking is a format check.** DOCex verifies a TIN is well-formed,
  not that it is registered. There is no free official lookup — the Joint Tax
  Board became the Joint Revenue Board in January 2026 and the portals are web
  forms. Live verification needs a paid provider and we will wire it to
  whichever you choose. **Bank account verification is real** — DOCex confirms
  an account number resolves to the name you expect, which is the check that
  catches diverted payments.
- **Payroll is switched off for NEEM.** We do not have your confirmed PAYE
  bands or pension rate, and running payroll without them would produce
  confidently wrong numbers. It stays off until you supply them.
- **One person operates DOCex.** If continuity matters to you — and for a
  finance system it should — ask us about escrow of the source code and a
  standing data export. Both are reasonable and neither is expensive.

---

## If something goes wrong

- **You notice a problem:** contact us. We aim to acknowledge within one
  working day and treat anything touching money or the audit trail as urgent.
- **We notice first:** we tell you, before you find it.
- **Data loss:** we restore from the most recent verified backup and tell you
  exactly what window was affected.
- **A security incident:** we tell you what happened, what was accessed, and
  what we changed — in writing, the same week.

---

## If you leave

Your data is yours. On request we provide a complete export in a readable
format and delete our copies. No notice period, no fee, no export charge.

We would rather you stayed because it works.

---

*Questions about anything in this document are welcome, including the parts
that say "not yet". Those are the ones worth asking about.*
