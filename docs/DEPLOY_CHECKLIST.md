# DOCex — Railway + Vercel Deploy Checklist

Repo: `github.com/faridopz/Docex` · Branch: `demo-release`
Goal: backend on Railway, frontend on Vercel, wired together via 2 env vars.
Do the parts **in order** — the backend URL is needed before Vercel, and the
Vercel URL is needed before CORS.

---

## Before you start
- [ ] Push the latest fix: `git push origin demo-release` (the lazy-init boot fix must be in the branch both platforms build).

---

## PART A — Backend on Railway (do this first)

1. [ ] railway.app → **New Project** → **Deploy from GitHub repo** → pick `faridopz/Docex`.
2. [ ] Settings → **Branch** = `demo-release`. Railway auto-detects `railway.toml` and builds `api/Dockerfile`.
3. [ ] **Variables** tab — add:
   - [ ] `ANTHROPIC_API_KEY` = your Claude key ✅ (already set)
   - [ ] `PAYSTACK_SECRET_KEY` = your Paystack test key
   - [ ] `ADMIN_SECRET` = any long random string (locks /admin/diagnostics)
   - [ ] `ALLOWED_ORIGINS` = *leave blank for now* — you'll fill it in Part C
4. [ ] **Volumes** — add a volume, **mount path `/app`**. (Without this, every redeploy wipes rulebooks, checks, and the audit trail.)
5. [ ] Deploy. When green, copy the public URL → e.g. `https://docex-api-production.up.railway.app`.
6. [ ] Verify: open `https://<railway-url>/health` → must return `{"status":"ok",...}`.

---

## PART B — Frontend on Vercel

1. [ ] Your project already exists (`docexdemodeploy.vercel.app`). Settings → **Git** → confirm Production Branch = `demo-release`, Root Directory = `web`.
2. [ ] Settings → **Environment Variables** → add:
   - [ ] `NEXT_PUBLIC_API_URL` = `https://<railway-url>` (from A.5, **no trailing slash**)
3. [ ] **Redeploy** (Deployments → ⋯ → Redeploy). ⚠️ Required — `NEXT_PUBLIC_*` vars are baked in at build time, so saving the var alone does nothing until a rebuild.

---

## PART C — Wire CORS (connect the two)

1. [ ] Back in Railway → Variables → set:
   - [ ] `ALLOWED_ORIGINS` = `https://docexdemodeploy.vercel.app` (exact, no trailing slash)
2. [ ] Redeploy the Railway service so it picks up the new origin.

---

## PART D — Verify on the live URL (not localhost)

1. [ ] Open `https://docexdemodeploy.vercel.app`.
2. [ ] Open DevTools → **Network** tab, reload, click into Compliance.
   - Calls go to the **Railway URL** and return 200 → ✅ working.
   - Calls go to **localhost:8000** → Part B var not built in (redeploy Vercel).
   - Calls to Railway fail with **CORS** error → Part C mismatch (fix `ALLOWED_ORIGINS`, redeploy backend).
3. [ ] Compliance page loads with **no rulebooks** (empty, not red error) → backend is reachable. Expected: a fresh volume is empty.

---

## PART E — Seed the demo instance (so it's not empty)
- [ ] Create the TA Connect rulebook on the **live** site (New policy set → upload your procurement policy), or import one.
- [ ] Load a few demo documents into Knowledge / Extract.
- [ ] Run one clean + one flagged voucher so Saved Checks isn't empty during the demo.

---

## Common first-deploy gremlins
- **502 on first request** → backend still booting, or volume mount path isn't `/app`.
- **Data vanishes after redeploy** → volume not mounted at `/app`.
- **Anthropic 401** → key wrong/missing in Railway (note: the app now still boots; only AI calls fail).
- **CORS error** → `ALLOWED_ORIGINS` doesn't exactly match the Vercel origin (scheme + host, no trailing slash).
- **Knowledge / big extraction times out** → expected on large batches; keep deployed demo batches small.
