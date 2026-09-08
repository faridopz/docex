# Running DOCex securely and reliably

The standing rules, not the one-off deploy. `DEPLOYMENT.md` gets it live;
this keeps it safe once it is.

Written for one person operating a finance system for a real organisation with
no colleague to catch mistakes. Every rule below exists because breaking it
fails quietly.

---

## The five rules

**1. The signing key is never rotated.**
`DOCEX_SIGNING_KEY` signs the audit chain. Changing it makes
`verify_audit_chain()` fail on every historical record — not because anything
was tampered with, but because the proof was thrown away. It is the product's
entire claim to an auditor. Password manager, today, before anything else.

**2. Nothing goes in until a redeploy has been survived.**
Create a requisition, note the reference, redeploy, look for it. Storage
failures are silent because writing always succeeds. This is the only test that
catches it and no script can do it for you.

**3. A backup is not a backup until it has been restored.**
The nightly job restores every backup it takes. If it goes red, that is a
production incident, not a chore.

**4. Never edit the database by hand to fix something.**
Every write must go through the application, because that is what writes the
audit entry. A hand-edited record is a record with no explanation, and it is
the exact thing DOCex exists to make impossible.

**5. When something breaks, roll back — do not restore.**
Almost every bad morning is bad code over good data. Rolling back takes two
minutes and touches nothing. Restoring a backup over a healthy database
destroys everything written since it was taken.

---

## Supabase specifically

We use Supabase as a plain Postgres. It is more than that, and the difference
is where the risk is.

### The table is not in `public` — deliberately

Supabase publishes **every table in the `public` schema** as an HTTPS REST
endpoint, readable with the project's `anon` key. That key is *designed* to be
public: it ships inside frontend bundles and sits in the dashboard.

A `public.records` table would put every requisition, approval, vendor bank
detail and payment amount one HTTP request away from anyone who learned the
project URL — no password, no session, and **no entry in our audit log**,
because the request would never reach our application.

So DOCex creates its table in a `docex` schema, which the Data API does not
expose, and additionally:

- revokes all access from the `anon` and `authenticated` roles
- enables row-level security with no policies, so even an accidental exposure
  denies every read
- refuses to start if you set `DOCEX_PG_SCHEMA=public`
- **warns loudly on boot if a `public.records` table exists** — if you ever see
  that message, drop that table

Verified by `test_store_pg.py`, which creates a role with Supabase's default
grants and tries to read a payment. It gets permission denied.

### Do this once in the Supabase dashboard

- [ ] **Settings → API → Data API:** confirm exposed schemas is `public` only,
      and ideally disable the Data API entirely. We do not use it.
- [ ] **Settings → Database:** note the connection string. Prefer the **session
      pooler (5432)**. The transaction pooler (6543) works — DOCex detects it
      and disables server-side prepared statements, which that mode cannot
      support — but session mode has fewer surprises.
- [ ] **Save the database password** where you will find it. It is inside the
      connection string and cannot be read back.
- [ ] **Enable 2FA on the Supabase account.** It holds every client record.
- [ ] Same for GitHub and Render. Your accounts are the real perimeter — not
      the application.
- [ ] The `service_role` key is a **full bypass of every access control**. We
      do not use it. Never put it in a frontend, a repo, or a support message.

### The free tier's actual limits

| | |
|---|---|
| 500 MB database | DOCex records are small; monitor when NEEM adds documents |
| Pauses after **7 days** of no activity | Daily client use never reaches this |
| **No provider backups** | Which is why ours are not optional |
| Connection cap | `DOCEX_PG_POOL_MAX=5` keeps us well under |

If the project ever does pause, data is retained — you resume it from the
dashboard. It is downtime, not loss.

---

## Weekly, ten minutes

- [ ] GitHub → Actions → **backup** is green all week. Red is an incident.
- [ ] Sentry: any error you have not seen before.
- [ ] Supabase → Database → size, against 500 MB.
- [ ] `/settings/users`: anyone who left still active? Anyone who **never
      signed in** and should have?

```bash
python3 backup.py list       # warns if the newest is over 36h old
```

## Monthly, thirty minutes

- [ ] **Download one backup artefact and keep it somewhere you control.**
      GitHub keeps 90 days; an auditor asks in October about March.
- [ ] `python3 backup.py verify <that file>` — restore it, confirm an active
      admin comes back, **write the date in DEPLOYMENT.md**.
- [ ] `python3 verify_deployment.py https://<api>` — 51 routes, CORS, error
      leaks, login throttling.
- [ ] Re-read the profile's `_confirm_before_go_live`. Have any been answered?

## Before every deploy

```bash
for t in test_*.py; do python3 "$t" >/dev/null || echo "FAILED $t"; done
cd web && npx tsc --noEmit
```

Then deploy, then `verify_deployment.py`, then confirm a reference from
*before* the deploy is still there.

Never deploy on a Friday. Never deploy in the two days around a client's month
end — for NEEM, that is when the payment schedule and the reconciliation both
happen, and it is the worst possible week to need a rollback.

---

## What is already enforced, so you need not remember it

Useful to know because it is also what you can honestly tell a client.

| Control | Behaviour |
|---|---|
| Default-deny auth | A new route is protected the moment it exists. Making one public is a deliberate edit to an allowlist, covered by a test. |
| Forced password change | Enforced in middleware, so it covers routes not yet written. A one-time password reaches three paths and nothing else. |
| Role enforcement | Server-side, from the signed-in session. A reviewer cannot approve by editing the page. |
| Session revocation | Sign-out, password change, admin reset and deactivation each kill **every** session that account holds. |
| Brute force | Eight failures locks for 15 minutes. Counted per email, not per IP — one office behind one NAT address must not lock out the whole team. |
| Account enumeration | A wrong password for a real account is indistinguishable from one for an account that does not exist. |
| Org isolation | The org id is part of the storage key, not a filter. A filter can be forgotten in one query; a key cannot. |
| Error responses | No stack traces, file paths, or connection strings. A reference number instead. |
| Crash reports | Vendor names, amounts and credentials stripped before anything leaves. |
| Audit chain | Append-only, HMAC-chained, tamper-evident. |
| Payment records | Frozen at payment. Shown as applied, never recomputed against today's policy. |
| Boot guards | Production refuses to start without durable storage, `AUTH_SECRET` and `DOCEX_SIGNING_KEY`. |

---

## If you think something has gone wrong

**Suspected compromised account** — deactivate it in `/settings/users`. Every
session dies immediately. Then reset and reactivate.

**You pasted a secret somewhere public** — rotate `AUTH_SECRET` (everyone signs
in again), the Supabase password, the Anthropic key. **Not the signing key.**
If the signing key leaked, that is a conversation, not a rotation: it lets
someone forge an audit entry, so the honest move is to tell the client and
re-chain from a known-good backup.

**Numbers look wrong** — do not correct the database. Reproduce it, find the
code path, fix the code, and tell the client what was wrong and for how long.
Deterministic-first exists so that money bugs are findable in code rather than
argued about.

**Client says data is missing** — check the audit log before assuming loss. It
is more often a filter, a permission, or the wrong org than a real deletion.

The full incident procedure is the `docex-incident` skill; rollback is in
`DEPLOYMENT.md`.

---

## The honest gaps

Say these plainly. Each is more credible than a hedge.

- **One person operates this**, and that person can read the database. It is in
  `NEEM_SECURITY_SUMMARY.md` because they will work it out anyway.
- **No staging.** Changes are tested locally and then on production.
- **No external uptime alerting.** You hear about crashes, not unreachability.
- **Notifications and vouchers still write files** and are lost on redeploy.
  Requisitions, approvals, payments, users and the audit log are all durable.
- **The first click after a quiet spell is slow** on the free tier.

Fix in that order. The first two are the ones that will actually bite.
