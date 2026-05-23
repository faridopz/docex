# Deploying DOCex

Step-by-step guide to put DOCex on the internet — frontend on Vercel,
backend on Railway. Cost: ~$5/month + Anthropic API usage.

## What you need before you start

- A GitHub account with the DOCex repo pushed up
- An Anthropic API key from https://console.anthropic.com
- A credit card (Vercel is free, Railway has a $5 starter tier)
- About 30 minutes

---

## Step 1 — Deploy the backend to Railway

1. Sign up at **https://railway.app** (use the GitHub login).
2. Click **New Project → Deploy from GitHub repo** and pick your DOCex repo.
3. Railway will auto-detect the `api/Dockerfile`. If it asks for a Dockerfile
   path, point it to `api/Dockerfile`.
4. Go to **Variables** and add:
   - `ANTHROPIC_API_KEY` — your key from console.anthropic.com
   - `ALLOWED_ORIGINS` — leave empty for now; we'll add the Vercel URL after Step 2
5. Go to **Settings → Volumes** and add a volume:
   - **Mount path:** `/app/rulebooks` (size 1GB is more than enough)
   - Add a second volume: **Mount path:** `/app/checks` (size 1GB)
   - Persistent volumes are what survive container restarts. Without them,
     rulebooks and checks vanish every time Railway redeploys.
6. Railway will build and deploy. You'll get a URL like
   `https://docex-production-abcd.up.railway.app`.
7. Test it:
   ```bash
   curl https://your-railway-url/health
   ```
   Should return `{"status":"ok","version":"2.0.0"}`.

---

## Step 2 — Deploy the frontend to Vercel

1. Sign up at **https://vercel.com** (GitHub login).
2. Click **Add New → Project**, import your DOCex repo.
3. Configure:
   - **Root Directory:** `web`
   - **Framework Preset:** Next.js (auto-detected)
   - **Build/Output settings:** leave defaults
4. Under **Environment Variables**, add:
   - `NEXT_PUBLIC_API_URL` — your Railway URL from Step 1 (no trailing slash)
5. Click **Deploy**. You'll get a URL like `https://docex-yourname.vercel.app`.
6. Test it: open the URL in a browser. You should see the landing page.

---

## Step 3 — Wire CORS so the frontend can talk to the backend

1. Copy your Vercel URL from Step 2.
2. Back in Railway → **Variables** → update `ALLOWED_ORIGINS`:
   ```
   https://docex-yourname.vercel.app
   ```
   (Multiple origins are comma-separated. Add a custom domain later when
   you set one up.)
3. Railway auto-redeploys when you change a variable.
4. Wait ~30 seconds, then test the full flow on your Vercel URL.

---

## Step 4 — Walk the full happy path on production

1. Visit your Vercel URL.
2. `/compliance` → "Upload your first policy" → drop in a real procurement
   policy (a public BMGF or USAID policy works as a stand-in).
3. Wait ~30-60s for interpretation. Verify the rulebook loads in the editor.
4. Toggle a rule, edit a description, save. Confirm it persists by reloading.
5. Run a check against a mock payment voucher. Confirm the verdict screen
   loads with policy citations + payment evidence.
6. Mark the check as approved. Confirm it shows up at `/compliance/checks`
   with the approved filter.
7. Copy the audit URL. Open it in an incognito window. Confirm the saved
   check still loads identically.

If anything breaks: check Railway logs (Deployments → View Logs) and
Vercel logs (Project → Deployments → click latest → View Function Logs).

---

## Step 5 — (Optional) Configure email notifications

DOCex can email the compliance officer automatically after each check.
Configuration is per-rulebook in the UI; the backend just needs an SMTP
provider plugged in.

**Pick a provider:**

| Provider | Best for | Setup |
|---|---|---|
| **Resend** | Quickest setup, great deliverability, free tier | Sign up at resend.com, get an API key |
| **Gmail** | Personal demo, no domain needed | Enable 2FA + create an [app password](https://myaccount.google.com/apppasswords) |
| **Office 365** | TA Connect (they're on Microsoft 365) | Use the user's email + their password (or an app password if MFA is on) |

**Add the env vars in Railway:**

For **Resend** (recommended):
```
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USERNAME=resend
SMTP_PASSWORD=re_xxxxxxxxxxxxxxxx       # your Resend API key
SMTP_FROM_ADDRESS=notifications@yourdomain.com  # must be verified in Resend
SMTP_FROM_NAME=DOCex
APP_URL=https://docex-yourname.vercel.app
```

For **Gmail**:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=youremail@gmail.com
SMTP_PASSWORD=abcdabcdabcdabcd         # the 16-char app password (no spaces)
SMTP_FROM_ADDRESS=youremail@gmail.com
SMTP_FROM_NAME=DOCex
APP_URL=https://docex-yourname.vercel.app
```

For **Office 365**:
```
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=compliance@taconnect.org
SMTP_PASSWORD=...
SMTP_FROM_ADDRESS=compliance@taconnect.org
SMTP_FROM_NAME=TA Connect DOCex
APP_URL=https://docex-yourname.vercel.app
```

Then in DOCex, open any rulebook → "Email notifications" card → set
recipient + trigger ("Flagged or blocked" is the sane default) → Save.

Test it: run a check that should produce flags, watch the inbox. The
audit URL in the email body links straight to the saved check.

If notifications don't fire: check the Railway logs for warnings starting
with `[DOCex]` or `Warning: notification send failed`. The most common
issues are unverified sender addresses (Resend) and wrong app passwords
(Gmail).

---

## Step 6 — Custom domain (optional but adds polish)

1. **Vercel:** Settings → Domains → add `docex.com` (or whatever you own).
   Vercel gives you DNS records to add at your registrar.
2. **Railway:** Settings → Networking → Custom Domain → add `api.docex.com`.
   Add a CNAME record at your registrar.
3. Update `NEXT_PUBLIC_API_URL` in Vercel to `https://api.docex.com`.
4. Update `ALLOWED_ORIGINS` in Railway to `https://docex.com,https://www.docex.com`.

---

## Cost ballpark

- **Vercel** Hobby tier: free for personal projects, $0/month
- **Railway** Starter tier: $5/month base + ~$0-3/month for our usage
- **Anthropic API:** pay-as-you-go
  - Per compliance check (one policy interpretation + one payment check):
    ~$0.03-0.10 depending on policy size and payment doc count
  - For TA Connect doing 200 PVs/month: ~$10-20/month
  - Caching halves the cost on batch runs against the same rulebook

Total to run DOCex with TA Connect's workload: **~$20-30/month** of
infrastructure costs. Charge them $5-15K/year and the margin is healthy.

---

## Local development still works

The localhost CORS allowlist is always on, so after deploying you can
still `npm run dev` against `localhost:8000` for development. Just
remember to swap `NEXT_PUBLIC_API_URL` in `web/.env.local` to localhost
when you're working locally — or set up two Vercel environments.

---

## Alternative: Fly.io instead of Railway

If you prefer Fly.io (cheaper at scale, more technical):

```bash
# Install flyctl
brew install flyctl

# From the project root
fly launch  # walks you through it, uses api/Dockerfile
fly volumes create docex_data --size 1
# Mount the volume to /app/rulebooks and /app/checks in fly.toml

fly secrets set ANTHROPIC_API_KEY=sk-ant-... ALLOWED_ORIGINS=https://...
fly deploy
```

Same Dockerfile, same env vars, just a different host.
