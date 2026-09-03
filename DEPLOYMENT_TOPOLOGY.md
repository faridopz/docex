# Deployment Topology — what each client actually gets

**Yes: separate URLs, separate servers, separate databases. One codebase.**

---

## What exists per client

Each client gets **four things of their own**, and shares nothing but the code:

| | NEEM | EVA |
|---|---|---|
| Frontend URL | `neem.docex.app` | `eva.docex.app` |
| API URL | `api.neem.docex.app` | `api.eva.docex.app` |
| Database | their own | their own |
| Config | `profiles/neem.json` | `profiles/eva.json` |

```
                 ONE CODEBASE — github.com/faridopz/docex
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
   ┌──────────▼──────────┐               ┌────────────▼────────┐
   │  neem.docex.app     │               │  eva.docex.app      │
   │  (Vercel build #1)  │               │  (Vercel build #2)  │
   └──────────┬──────────┘               └────────────┬────────┘
              │                                       │
   ┌──────────▼──────────┐               ┌────────────▼────────┐
   │ api.neem.docex.app  │               │ api.eva.docex.app   │
   │ DOCEX_ORG=neem      │               │ DOCEX_ORG=eva       │
   │ own SQLite volume   │               │ own SQLite volume   │
   └─────────────────────┘               └─────────────────────┘
```

They cannot reach each other. Different servers, different databases, different
credentials.

---

## ⚠️ The gotcha that will bite you

**`NEXT_PUBLIC_API_URL` is baked in at BUILD time, not read at runtime.**

Next.js compiles `NEXT_PUBLIC_*` variables into the JavaScript bundle. You
cannot point one frontend build at a different API by changing an environment
variable afterwards.

**Consequence: each client needs their own frontend build.** In Vercel that
means a separate project per client, each with its own `NEXT_PUBLIC_API_URL`.

If you forget this, NEEM's frontend will happily call EVA's API — and get 401s,
because their tokens are org-stamped. Confusing to debug, trivial to avoid.

**Also:** each API's `ALLOWED_ORIGINS` must list its own frontend URL and no
other. `api.neem.docex.app` should not accept requests from `eva.docex.app`.

---

## Setting up a new client (about 30 minutes)

### 1. API service

```bash
# New Render service from the same repo
Name:     docex-api-<client>
Branch:   demo-release
Plan:     Starter or above       # persistence needs a paid plan
Disk:     /data, 5GB

# Environment
DOCEX_ORG=<client>
DOCEX_DB=/data/docex.db
ANTHROPIC_API_KEY=...
AUTH_SECRET=<unique per client>
DOCEX_SIGNING_KEY=<unique per client — NEVER rotate>
ALLOWED_ORIGINS=https://<client>.docex.app
SENTRY_DSN=...
```

> **`AUTH_SECRET` and `DOCEX_SIGNING_KEY` must be different per client.** Shared
> secrets mean a token minted for one client is cryptographically valid at
> another. Generate fresh, store them somewhere you will still have in three
> years.

### 2. Frontend project

```bash
# New Vercel project, same repo, root directory ./web
NEXT_PUBLIC_API_URL=https://api.<client>.docex.app
Domain: <client>.docex.app
```

### 3. Apply their config

```bash
DOCEX_ORG=<client> DOCEX_DB=/data/docex.db \
  python3 org_config.py apply profiles/<client>.json
```

### 4. Verify before anyone logs in

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.<client>.docex.app/health
# 200

curl -s -o /dev/null -w "%{http_code}\n" https://api.<client>.docex.app/compliance/checks
# 401 — if this is 200, STOP
```

Then create a record, redeploy, confirm it survived.

---

## Shipping an improvement — the part that makes this worth it

**One push updates every client.**

```
    git push
        │
        ├──→ docex-api-neem     rebuilds, redeploys
        ├──→ docex-api-eva      rebuilds, redeploys
        └──→ (every future client)
```

But **each client still sees only their own features**, because the flags live
in their config, not in the code. Build EVA's statutory deductions and NEEM's
system is unchanged — until you flip one flag in `profiles/neem.json` and
re-apply. No deploy, no build.

That is the whole model working. One improvement, every client benefits, nobody
sees anything they did not buy.

## But do not let both auto-deploy blindly

Auto-deploy on every push is fine with one demo client. With two paying clients
it means an untested change lands on both simultaneously.

**Use a staging instance and promote:**

```
push → staging          smoke test: login → requisition → approve → audit
         ↓ passes
       client A         watch Sentry for 15 minutes
         ↓ clean
       client B
```

At two clients this is a few minutes of care. It becomes essential at five.

**Practically:** turn `autoDeploy` off on client services and deploy them
manually from the Render dashboard after staging passes. One extra click,
and it prevents shipping a bad build to a live finance team.

---

## What the client experiences

**NEEM signs in at `neem.docex.app`** and sees: Requisitions, Payments, Audit,
Field Receipts. Four departments. Their ₦250k override limit. TIN validation on.
No payroll — the flag is off, so the nav item does not exist for them.

**EVA signs in at `eva.docex.app`** and sees: the same requisitions engine, five
departments plus the Board, their ₦300k / ₦10m thresholds, the ED approval step.
Once built: payroll, procurement bands, statutory deductions.

**Neither knows the other exists.** Same code in both.

---

## Cost per client

| | Monthly |
|---|---|
| API service (paid, no sleeping) | ₦12–40k |
| Database / persistent disk | ₦12–30k |
| Frontend (Vercel) | usually free at this scale |
| Monitoring share | ₦8–14k |
| **Infrastructure per client** | **₦35–85k** |

Against ₦450–600k revenue that is 6–15%. **Hosting is not your constraint** —
support time and model spend are.

⚠️ Verify current provider pricing before quoting; these are planning estimates.

---

## Why not one shared instance

The code supports it — `org_id` is part of every storage key, and
`test_org_config.py` proves two organisations on one instance cannot see each
other. Separate instances is a **deployment choice**, and it is reversible.

Three reasons it is right now:

1. **Blast radius.** A bad deploy takes down one client, not all.
2. **The compliance story.** *"Your data is on your own server, your own
   database"* ends a conversation that *"we isolate by tenant key"* starts.
3. **Data residency.** Some donors require data in-country; separate instances
   let you place clients in different regions.

The shared option stays open for a future low-cost tier — small NGOs at ₦150k
where a dedicated instance would eat 40% of the fee.

---

## Domain setup

Buy **one domain** (`docex.app` or similar) and give each client a subdomain.
Costs very little annually, and it matters: `neem.docex.app` reads as *their
system*; `docex-neem-prod.onrender.com` reads as a side project.

```
docex.app                 marketing / landing
neem.docex.app            NEEM frontend
api.neem.docex.app        NEEM API
eva.docex.app             EVA frontend
api.eva.docex.app         EVA API
staging.docex.app         staging
```

Both Vercel and Render take a custom domain in a few minutes.
