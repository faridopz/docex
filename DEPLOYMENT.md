# Deploying DOCex for a client

The runbook for putting a client's real money into this system, and for the
morning it goes wrong.

Written for one specific situation — NEEM, twenty users, real payments from day
one — but nothing here is NEEM-specific except the names.

---

## The gate

Client data does not enter until every line is ticked. Not "mostly ticked".
The whole list exists because each item, left undone, fails silently.

- [ ] `python3 verify_deployment.py https://<api>` — no failures
- [ ] **Data survived a redeploy** — the one check no script can do for you
- [ ] Paid plan; the instance does not sleep
- [ ] Nightly backup ran, and one has been **restored**
- [ ] `AUTH_SECRET` and `DOCEX_SIGNING_KEY` set, and saved in a password manager
- [ ] `ALLOWED_ORIGINS` is the exact production frontend origin
- [ ] Profile applied; the client's administrator can sign in
- [ ] Every account is the client's; no leftover demo logins
- [ ] Rollback read, not just written

---

## 1. Storage

Postgres, managed, wired by `render.yaml` — the app reads
`DOCEX_DATABASE_URL`.

Two failures this replaced, both silent:

**The app never read `DOCEX_DATABASE_URL`.** It only looked at `DOCEX_DB`. So a
correctly provisioned managed database would have been ignored, and every
record written to the container's local disk — which the platform replaces on
every deploy. Nothing errors, because writing a file always succeeds. The
symptom is arriving on Monday to an empty system.

`api/main.py` now refuses to boot when `DOCEX_ENV=production` and no durable
store is configured. A finance system that will not start is a bad morning; one
that starts and loses March is a lost client.

**PostgresStore opened a new connection per operation.** Measured against a
real PostgreSQL 16 on localhost: 6.5ms per read versus 0.54ms pooled — twelve
times slower with no network and no TLS in the way. Over a managed database's
network it is worse, and twenty users doing it at once walks into the
provider's connection cap. It is now a checked, bounded pool that retries once
when the provider restarts the database underneath it.

```bash
# Prove the adapter before trusting it. Skips cleanly with no URL.
DOCEX_TEST_PG_URL=postgresql://... python3 test_store_pg.py     # 43 checks
```

---

## 2. Secrets

Set in the host's secret manager. Never in git, never in the image.

| Variable | Why it matters if unset |
|---|---|
| `ANTHROPIC_API_KEY` | Document reading fails |
| `AUTH_SECRET` | Each container invents its own key — everyone is signed out on every deploy, and two instances never agree on a session |
| `DOCEX_SIGNING_KEY` | Signs the audit chain (see below) |
| `ALLOWED_ORIGINS` | The frontend cannot call the API at all |
| `DOCEX_ORG` | Records land under the wrong tenant |
| `DOCEX_ENV=production` | The storage and secret guards do not engage |
| `SENTRY_DSN` | You hear about crashes from the client |

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

> ### `DOCEX_SIGNING_KEY` must never be rotated
>
> It signs the hash-chained audit log. Change it and `verify_audit_chain()`
> fails on every historical record — the immutability guarantee, which is the
> product's entire claim to an auditor, evaporates in one edit. There is no
> recovery: the old records cannot be re-signed without destroying the property
> the chain exists to prove.
>
> Put it in a password manager **before** pasting it into the host. Losing it
> and rotating it are the same disaster.

---

## 3. Configure the client

```bash
export DOCEX_DATABASE_URL='postgresql://...'
export DOCEX_ORG=neem

python3 org_config.py validate profiles/neem.json     # before any write
python3 org_config.py apply    profiles/neem.json
python3 org_config.py describe                        # read it against their policy
```

Validation runs before anything is written, so an invalid profile cannot leave
an org half-configured — a step routed to a department that does not exist
strands payments where nobody can see them.

The bootstrap administrator is created with `must_change_password`. That is
deliberate: we choose that password, it goes through a shell history and a
message, and it must stop working the moment their administrator has used it.

Then check `_confirm_before_go_live` in the profile. Those are open questions,
not defaults. **A guessed threshold is worse than an empty one** — an empty one
gets asked about, a guessed one gets trusted.

---

## 4. The twenty accounts

`/settings/users`, signed in as the administrator.

Each person gets a one-time password shown exactly once. It is not stored in
readable form and no endpoint will tell you what it was. Pass it on; they
replace it on first sign-in; until they do, the API refuses every route except
seeing who they are, setting a password, and signing out.

There is no password-reset email. That is a decision, not a gap: reset links
need a mail provider, a token store, and a domain nobody can spoof, and each is
a way to lose an approver's account to whoever controls the mailbox. A named
administrator issuing a one-time password is weaker against a careless
administrator and stronger against everything else.

A reset also clears a lockout, so eight wrong guesses does not mean fifteen
minutes standing at a colleague's desk.

**When someone leaves:** deactivate, never delete. Sessions die immediately.
The record stays, because the approval trail must still be able to say who
authorised a payment in March about someone who left in April.

---

## 5. Backups

Nightly, off this infrastructure, verified by restoring.

```bash
python3 backup.py create --verify    # take one and immediately restore it
python3 backup.py list               # warns if the newest is over 36h old
python3 backup.py verify             # restore the latest into a scratch database
```

`.github/workflows/backup.yml` runs at 02:30 UTC and keeps artefacts 90 days.
It needs one secret: `DOCEX_DATABASE_URL`. Without it the job fails loudly
rather than reporting green for work it did not do.

The output is JSON Lines — one record per line, readable in any text editor in
a decade. The provider's own snapshots are faster for restoring into the same
provider; they cannot answer *"can we read our records without you"*, which is
the question a client's auditor actually asks.

**Download one a month and keep it somewhere you control.** Ninety days covers
the month end; it does not cover the auditor asking in October about March.

### Restore log

An untested backup is a belief. Record every restore here — the auditor will
ask when you last did one, and "we have backups" is not an answer.

| Date | Backup | Records | Result | By |
|---|---|---|---|---|
| 2026-09-08 | dev verification, SQLite + Postgres | 2 / 273 | verified — restored, both paths | pre-launch |

---

## 6. Deploy

```
PRE
  □ every suite green locally
  □ smoke-tested on staging: sign in → requisition → approve → audit
  □ client warned if anything user-visible changed

GO
  □ merge to demo-release
  □ watch the build; wait for the health check
  □ python3 verify_deployment.py https://<api> --email … --password …
  □ confirm data survived — the same references as before

AFTER
  □ Sentry clear for 15 minutes
  □ note it in the change log below
```

---

## 7. Rollback

Read this now, not while it is happening.

**Roll back first. Restore only if the data itself is gone.** Almost every bad
deploy is bad code over good data; rolling back fixes it in two minutes.
Restoring a backup over a healthy database throws away every record created
since it was taken, which turns a bad afternoon into a bad quarter.

1. **Render → the failing service → Deploys → the last green one → Rollback.**
   Two minutes. The database is untouched.
2. **Tell the client before they tell you.** "We have rolled back a change from
   this morning; nothing was lost; here is what happened." A client who hears
   it from you has a supplier. One who discovers it has a problem.
3. **Only if data is corrupt or gone:**
   ```bash
   python3 backup.py list
   python3 backup.py verify <file>                     # check before you commit
   python3 backup.py restore <file> --into "$DOCEX_DATABASE_URL"
   ```
   Restoring upserts by (org, collection, id): records in the backup overwrite
   their counterparts and anything created since is left alone. Sign in before
   telling anyone it worked.
4. **Write it up the same day**, while you still remember the order things
   happened in. See `docex-incident`.

**Never** roll back a migration by editing the database by hand. **Never**
rotate `DOCEX_SIGNING_KEY` to make an audit-chain error go away — that error is
the chain doing its job.

---

## 8. Still open

Honest list. None blocks Wednesday; all are owed.

- **Staging.** A second instance on the same image with throwaway data. Not yet
  built. Until it exists, every change is tested on a laptop and then on the
  client — which works until the day it does not.
- **Uptime monitoring from outside.** Sentry catches crashes. Nothing currently
  notices the instance being unreachable. A one-minute `/health` check that
  alerts to a phone is an hour's work.
- **Engines still writing raw files** — `notification_center.py`,
  `transactions.py`, `vouchers.py`, and directory storage in several
  `api/*_routes.py`. Durable for requisitions, users, departments and payments;
  not yet for notifications and vouchers. Same fix `auth` and `departments`
  already had.
- **PV reference format.** They use `NF/HQ/B24/CARE/SEP23/PV/01`; we generate
  `REQ-0001`.

---

## Change log

| Date | What | By |
|---|---|---|
| 2026-09-08 | Production hardening: Postgres wired and pooled, boot guards, user management with forced password change, verified backups | pre-launch |
