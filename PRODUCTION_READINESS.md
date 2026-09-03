# Production Readiness — from demo to a system worth ₦450k/month

**Status:** the engine is production-grade. **The deployment is not.**
**Blocking issue:** `render.yaml` runs `plan: free` with no `DOCEX_DB` and no
persistent disk. Every redeploy wipes every client's data.

This document is the gap list, in the order it must be closed.

---

## The honest current state

| | Demo (today) | Production (required) |
|---|---|---|
| Storage | JSON files, ephemeral | SQLite/Postgres on a persistent volume |
| Uptime | Sleeps after 15 min, 30–50s cold start | Always warm, health-checked |
| Backups | None | Daily, offsite, **restore tested** |
| Monitoring | Terminal logs | Sentry + uptime alerts to your phone |
| Secrets | `.env` on a laptop | Host secret manager, rotatable |
| Deploys | Push to `demo-release`, hope | Staging → verify → production, with rollback |
| Sessions | 12h, no idle timeout | Idle timeout, password policy |
| Incidents | Client emails you | You know first, with a comms path |

The engine work is done — 17 test suites, durable storage adapters, org
isolation, hash-chained audit. What's missing is **operations**, and no amount
of clean code substitutes for it.

---

## P0 — before NEEM touches it with real data

Nothing below is optional. A finance system that loses a payment record has
failed at the only thing it promised — and one that hands it to a stranger has
failed worse.

### 0. Authentication — FIXED, and worth knowing how it broke

**What was wrong:** roughly ninety routes had no authentication at all. The
newer routers (requisitions, departments, field receipts, org config) gate every
endpoint; the older demo-era ones never did. Verified live with no credentials:
`GET /compliance/rulebooks`, `/compliance/checks` and `/compliance/org-profile`
all returned **200**. Two separate risks — client financial data readable by
anyone with the URL, and endpoints that spend real money (Claude, Paystack) open
to anyone who felt like spending it.

**The fix:** `api/security.py` — default-deny middleware. Nothing reaches a
handler without a valid session except a short, commented allowlist: health,
login, register, status, docs, and the token-bearing public links for
self-check-in and emailed approvals. Decorators would have fixed it once;
default-deny fixes it for every route added from here.

`test_auth_coverage.py` enumerates every route the live app serves, calls it
with no credentials, and fails if anything not on the allowlist answers
something other than 401. **That test is the thing that stops this recurring.**

**Lesson for the checklist below:** this document originally checked durability
and never checked auth coverage. When adding a client, verify both.

### 1. Durable storage — the other blocker

`render.yaml` today: `plan: free`, no disk, no `DOCEX_DB`. Storage falls back
to JSON files inside the container and **resets on every deploy.**

Two options, both fine:

**A. SQLite on a persistent disk** *(simpler — start here)*
```yaml
services:
  - type: web
    name: docex-neem
    plan: starter                  # persistence needs a paid plan
    disk:
      name: docex-data
      mountPath: /data
      sizeGB: 5
    envVars:
      - key: DOCEX_DB
        value: /data/docex.db
      - key: DOCEX_ORG
        value: neem
```

**B. Managed Postgres** *(when you outgrow one node)*
Set `DOCEX_DATABASE_URL` and wire `PostgresStore`.
⚠️ **`PostgresStore` is written but has never run against a live database.**
Run `test_store_sql.py` with a real `DOCEX_DATABASE_URL` before trusting it.
Do not discover this during a client migration.

**Verify it worked** — do this, don't assume:
```bash
# create data → redeploy → confirm it's still there
curl -H "Authorization: Bearer $TOK" $API/requisitions | jq '.[].ref'
# trigger a deploy, wait, run the same command. Same refs = durable.
```

### 2. Paid plan — no sleeping

Free tier sleeps after ~15 minutes. A finance officer opening the app to a
40-second white screen concludes the system is broken. The keep-warm workflow
is a patch on the wrong problem; on a paid plan you delete it.

Also: **set the `DOCEX_API_URL` repo variable** or keep-warm silently no-ops.
(It has been no-op'ing.)

### 3. Backups, with a tested restore

`SqliteStore.backup()` already exists and does a consistent online backup.
Wrap it in a scheduled job that writes to object storage (S3/Spaces), keep 30
daily + 12 monthly.

> **A backup you have never restored is not a backup.** Restore into a scratch
> instance and log in. Do it before go-live, then quarterly. Put the date in
> `MASTER_CONTEXT.md` — the auditor will ask.

### 4. Error tracking

Sentry on the API and the frontend. Without it, your first signal is a client
email, which means the client is doing your monitoring.

```python
# api/main.py, guarded so a missing DSN never blocks boot
_dsn = os.environ.get("SENTRY_DSN", "").strip()
if _dsn:
    import sentry_sdk
    sentry_sdk.init(dsn=_dsn, traces_sample_rate=0.1,
                    environment=os.environ.get("DOCEX_ENV", "production"),
                    send_default_pii=False)   # never ship client finance data
```

`send_default_pii=False` is deliberate: crash reports must not carry vendor
names or amounts to a third party.

### 5. Uptime monitoring

Ping `/health` every minute from outside your infrastructure. Alert to your
phone. UptimeRobot's free tier is enough.

### 6. Secrets discipline

`ANTHROPIC_API_KEY`, `AUTH_SECRET`, `DOCEX_SIGNING_KEY`, `SENTRY_DSN` live in
the host's environment, never in git.

**Set `AUTH_SECRET` and `DOCEX_SIGNING_KEY` explicitly in production.** Both
currently fall back to generated or dev values. `DOCEX_SIGNING_KEY` signs the
audit chain — if it changes, `verify_audit_chain()` fails and your immutability
guarantee evaporates. **Set it once, back it up, never rotate it.**

### 7. Session hardening

Tokens are 12h with no idle timeout. For finance software on shared office
machines: reduce to 8h, add idle expiry, enforce password length ≥ 12 for new
accounts.

---

## P1 — first month live

8. **Staging environment** — a second instance on the same image with throwaway
   data. Every change goes there first. Non-negotiable once real money moves.
9. **Rollback plan** — Render keeps previous deploys; know the button. Write
   down: how to roll back, how to restore a backup, who you call.
10. **Status page** — a static page you update during an incident. Prevents six
    "is it down?" messages while you're fixing it.
11. **Log retention** — access logs already carry request IDs (`X-Request-ID`).
    Keep 30 days; it's how you answer "it broke at 2:14pm".
12. **Security & Compliance Summary** — the one-pager from `MASTER_CONTEXT.md`
    §7. Hand it over at go-live, before their auditor asks.

---

## P2 — before client three

13. **Move the remaining engines onto the store layer** —
    `notification_center.py`, `transactions.py`, `vouchers.py`, and the
    directory storage in several `api/*_routes.py`. They still write raw files:
    same durability and tenancy gap `auth`/`departments` just had. **A
    notification lost on redeploy means a payment nobody was told about.**
14. **Verify `PostgresStore`** against a live database.
15. **Penetration test + security audit** (~₦150k).
16. **Automated restore drill** in CI, not a manual habit.

---

## The hosting decision

### One instance per client, or one shared instance?

You now have real multi-org isolation — `org_id` is part of the storage key,
tokens carry the org, and `test_org_config.py` proves two clients can't see
each other. So both are technically viable.

**Choose one instance per client anyway.** Three reasons:

1. **Blast radius.** A bad deploy takes down one client, not all of them.
2. **The compliance story.** *"Your data is on your own instance, your own
   database"* ends a conversation that *"we isolate by tenant key"* starts.
3. **Data residency.** Some donors require data in-country. Per-client
   instances let you place NEEM in one region and a UK charity in another.

The cost is roughly linear per client, but you're charging ₦450k+ and hosting
is well under 15% of that. Buy the simplicity.

Multi-org on one instance stays available for a future low-cost tier — small
NGOs at ₦150k/month where per-client infrastructure wouldn't pay for itself.
**That's why the isolation work was worth doing now.**

### Which host

**Now → client 2: Render, paid plan.** You already have `render.yaml` and a
working Docker build. Moving to AWS today buys complexity you don't need and
costs you the week NEEM needs. Add a persistent disk, upgrade the plan, done.

**From client 3 (~mid-2027): AWS.** Justified then because compliance work
costs ₦300–500k regardless, larger clients expect enterprise hosting, and one
platform scales cleanly to ten instances. Not before — this is a distraction
until it's a requirement.

⚠️ **Verify current prices before quoting.** The figures in `render.yaml`'s
comments and in the cost documents are estimates from earlier planning, not
today's price list. Check Render's and AWS's current pricing pages before
putting a number in a client proposal.

---

## Deployment runbook

Write this down properly once and follow it every time.

```
PRE-DEPLOY
  □ all 17 suites green locally
  □ deployed to staging, smoke-tested (login, create requisition, approve, audit)
  □ client told if there's any user-visible change

DEPLOY
  □ merge to demo-release (autoDeploy picks it up)
  □ watch the build; wait for the health check to pass
  □ smoke test production: login, list requisitions, open audit
  □ confirm data survived — same references as before the deploy

POST-DEPLOY
  □ Sentry clear for 15 minutes
  □ note the deploy in the change log

IF IT BREAKS
  □ roll back to the previous deploy in Render
  □ tell the client before they tell you
  □ restore from backup only if data is corrupt, never as a first move
  □ write up what happened, same day
```

---

## Go / no-go for NEEM

Do not put real client data in until every one of these is true:

- [x] **Auth: default-deny middleware live, `test_auth_coverage.py` green**
- [ ] Confirm on the deployed instance: `curl $API/compliance/checks` returns 401
- [ ] `DOCEX_DB` set, on a persistent disk, **verified to survive a redeploy**
- [ ] Paid plan — no sleeping
- [ ] Backups running daily, **one restore actually tested**
- [ ] Sentry live and receiving events
- [ ] Uptime monitor alerting to your phone
- [ ] `AUTH_SECRET` and `DOCEX_SIGNING_KEY` set explicitly and backed up
- [ ] `ALLOWED_ORIGINS` correct for the production frontend
- [ ] `DOCEX_ORG=neem`, profile applied, admin can log in
- [ ] Staging exists
- [ ] Security & Compliance Summary written
- [ ] Rollback procedure written and understood

**Estimate: 2–3 focused days.** Most of it is configuration, not code — the
engine is ready. Do it before Sep 10 and you can run the follow-up against the
real deployment rather than a laptop.
