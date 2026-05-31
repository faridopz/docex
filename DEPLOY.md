# DOCex — Deployment Guide

The path from `localhost:3000` to a public URL in ~45 minutes. Single biggest leverage move you can make right now.

## Architecture

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  Vercel                 │ ───────▶│  Railway                │
│  Next.js frontend       │  HTTPS  │  FastAPI backend        │
│  docex.vercel.app       │         │  docex-api.up.railway   │
│                         │         │                         │
│  Env:                   │         │  Env:                   │
│   NEXT_PUBLIC_API_URL   │         │   ANTHROPIC_API_KEY     │
│                         │         │   PAYSTACK_SECRET_KEY   │
│                         │         │   ALLOWED_ORIGINS       │
│                         │         │   ADMIN_SECRET (opt)    │
└─────────────────────────┘         └─────────────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────────┐
                                    │  Railway volume     │
                                    │  /app — persists    │
                                    │  rulebooks, checks, │
                                    │  verifications, etc │
                                    └─────────────────────┘
```

## Step 1 — Railway (backend), ~20 min

1. Sign up at https://railway.app with GitHub. Free tier covers pilot scale.
2. **New Project → Deploy from GitHub repo → pick the DOCex repo.**
3. Railway autodetects `railway.toml` at the repo root and builds from `api/Dockerfile`. Wait for the first build (~3-5 min).
4. **Add a persistent volume** (critical):
   - Settings → Volumes → New Volume → mount path `/app`. 1GB is plenty for now.
   - Without a volume, every redeploy wipes rulebooks / checks / verifications / decks.
5. **Set environment variables** (Variables tab):
   - `ANTHROPIC_API_KEY` = your sk-ant-... key
   - `PAYSTACK_SECRET_KEY` = your sk_test_... or sk_live_... key
   - `ALLOWED_ORIGINS` = leave empty for now (fill in Step 3 after Vercel)
   - `ADMIN_SECRET` = generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (optional but locks `/admin/diagnostics`)
6. Wait for redeploy. Copy the public URL Railway gives you (e.g. `docex-api-production-abc123.up.railway.app`).
7. **Verify**: curl `<RailwayURL>/health` → should return `{"status":"ok","version":"2.0.0"}`.

## Step 2 — Vercel (frontend), ~15 min

1. Sign up at https://vercel.com with GitHub. Free Hobby tier is fine for now.
2. **Add New → Project → Import the DOCex repo.**
3. **Set Root Directory to `web`** (Settings → Build & Development Settings). Vercel will autodetect Next.js from there.
4. **Set environment variables** (Settings → Environment Variables):
   - `NEXT_PUBLIC_API_URL` = the Railway URL from Step 1 (e.g. `https://docex-api-production-abc123.up.railway.app`)
5. Deploy. Wait ~2-3 min for first build.
6. Copy the Vercel URL (e.g. `docex-xyz.vercel.app`).

## Step 3 — Wire them together, ~5 min

1. Back in **Railway → Variables**, set `ALLOWED_ORIGINS` to the Vercel URL: `https://docex-xyz.vercel.app`
2. Railway redeploys automatically (~1 min).
3. Reload the Vercel URL — CORS should pass and the app loads end-to-end.

## Step 4 — Verify the full chain

Open `https://docex-xyz.vercel.app` in a browser. You should see:
- Landing page loads
- `/knowledge` shows the empty library state with a "Try with sample documents" prompt
- `/compliance` shows the **sample rulebook** in the list (seeded in the Docker image at `/app/rulebooks/sample-ngo-procurement.json`)
- `/admin/diagnostics` either works (if no `ADMIN_SECRET` set) or shows the secret-input form

If anything 500s, check Railway's logs tab — most issues are missing env vars.

## Step 5 (later) — Custom domain

1. Buy `docex.com` (or similar) from your registrar.
2. **Vercel**: Settings → Domains → Add Domain → follow DNS instructions.
3. **Railway**: Settings → Networking → Custom Domain → `api.docex.com` → follow DNS.
4. Update Railway's `ALLOWED_ORIGINS` to include `https://docex.com`.
5. Update Vercel's `NEXT_PUBLIC_API_URL` to `https://api.docex.com`.
6. Redeploy both.

## Cost expectations

- **Railway** free tier: $5 credit/month. Pilot scale fits under it. Beyond that, pay-as-you-go ~$5-15/month.
- **Vercel** Hobby: free for personal use. Pro is $20/month — only if you want commercial use or analytics.
- **Anthropic API**: pay-per-call. Pilot usage estimate ~$30-100/month at first.
- **Paystack**: free for `/bank/resolve`.
- **Total before scale**: ~$0-$15/month + Anthropic.

## Common issues

| Symptom | Cause | Fix |
|---|---|---|
| Frontend loads but every API call fails with CORS error | `ALLOWED_ORIGINS` on Railway doesn't include Vercel URL exactly | Add Vercel URL (including `https://`), comma-separate if multiple |
| Login to /admin/diagnostics gives 404 even with correct secret | `ADMIN_SECRET` env not set on Railway | Set the env var, redeploy |
| Decks / rulebooks vanish after redeploy | No persistent volume mounted | Add Railway volume at `/app` |
| Knowledge Hub uploads fail for large files | Default body limit hit | Add `--limit-max-requests 0` flag or upgrade Railway plan |
| Slow first request after idle | Free-tier cold start | Pro tier removes this |

## What's NOT in this deploy

- **Database** — still file-based JSON. Phase 2 with Supabase.
- **Authentication** — single-user. Anyone with the URL can use it. Phase 2.
- **Backups** — none automated. For pilot, run a weekly `curl <URL>/verify/batches > backup.json` etc.
- **Sentry / error reporting** — adopt after first paid pilot.
- **Custom domain** — see Step 5.

## After deploy: the first Loom

The whole point of getting a public URL is to share it. Record a Loom that opens `https://docex-xyz.vercel.app` in a browser (not localhost) — that single change makes the demo look real to a prospect. The Loom is the asset you send with the proposal email.
