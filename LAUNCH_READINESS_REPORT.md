# Launch Readiness Report — DOCex

**Audited:** 6 September 2026 · **Verdict: ❌ DO NOT LAUNCH**
**7 blockers.** Two of them can cost you money or lose client data on day one.

Everything below was checked against the code, not assumed. Where I could not
verify something myself it is marked **⚠️ REQUIRES HUMAN VERIFICATION**.

---

## 1. What this application actually is

| Layer | What | Status |
|---|---|---|
| Frontend | Next.js 14 · TypeScript · Tailwind · Vercel | ⚠️ |
| Backend | FastAPI (Python) · Render · Docker | ❌ free tier |
| Database | SQLite via `store_sql.py`; Postgres adapter **written, never run** | ❌ |
| Auth | Own — PBKDF2-HMAC-SHA256 200k iters, HMAC session tokens | ⚠️ |
| Payments (product) | Paystack — bank account *verification* only, **no money moves** | ✅ |
| Payments (billing) | **None.** No Stripe, no subscriptions, no card handling | ✅ n/a |
| Email | `notifications.py` — SMTP, **silently disabled if unconfigured** | ❌ |
| File storage | Local disk / SQLite blobs | ⚠️ |
| LLM | Anthropic — Sonnet 4.6 (compliance, knowledge), Haiku 4.5 (extraction) | ❌ uncapped |
| Analytics | **None found** | ✅ |
| Third-party SDKs | anthropic, fastapi, pydantic, PyMuPDF, pdfplumber, openpyxl, python-docx, tesseract/pytesseract, rapidfuzz, Paystack | ✅ |

**Not a mobile app.** Sections 17 (app store) and 18 (purchase restore) do not
apply. Section 19 (payment config) is largely n/a — see §5.

---

## 2. 🔴 BLOCKERS

### B1 · No rate limiting or spend quota — unbounded LLM bill
**Verified.** The only matches for "rate limit" in the codebase are *comments*.
There is no per-user rate limit, no per-org quota, no daily cap.

`max_tokens` is set per call (16,384 on compliance and extraction), which caps
one request — but nothing caps **the number of requests**. Any authenticated
user can loop `POST /compliance/check` and generate an unbounded Anthropic bill.

`usage.py` now *records* spend per org, but recording is not limiting.

> **Fix before launch:** per-org daily token quota enforced in `usage.py`, plus
> a request rate limit. Fail closed with a clear message.

### B2 · Free tier — client data is deleted on every redeploy
**Verified.** `render.yaml` line 32: `plan: free`. No `disk:` block. No
`DOCEX_DB` env var.

Storage falls back to JSON files inside the container. **Every deploy wipes
every payment record, receipt and audit trail.** The free instance also sleeps
after ~15 minutes.

> **Fix before launch:** paid plan + persistent disk + `DOCEX_DB`, then *prove*
> data survives a redeploy. **💰 Requires your approval — costs money.**

### B3 · No error monitoring anywhere
**Verified.** Zero references to Sentry or any equivalent in Python, TS or TSX.

If the app breaks in production your first signal is a client email. You cannot
answer "what failed, when, how many users".

> **Fix before launch:** Sentry on API and frontend, `send_default_pii=False`
> so vendor names and amounts never leave your infrastructure.

### B4 · Email silently disabled
**Verified.** `notifications.py`: *"If SMTP_HOST is unset, notifications are
silently skipped."*

Not configured anywhere. So: no notification when a payment reaches an
approver, and **no password reset is possible**. Combined with B5, a locked-out
user cannot recover their account.

No SPF/DKIM/DMARC because there is no sending domain yet.

> **Fix before launch:** SMTP on your own domain, SPF + DKIM + DMARC,
> verified end to end.

### B5 · No password reset, and no account deletion
**Verified.** `auth.py` has `create_user`, `authenticate`, `issue_token`,
`verify_token` — and nothing else. There is:

- ❌ no password reset
- ❌ no `delete_user`
- ❌ no email verification

A user who forgets their password is locked out permanently unless you run
`seed_admin.py` on the server. **Account deletion is a legal requirement in
most jurisdictions once you hold personal data.**

### B6 · No privacy policy or terms
**Verified.** No `/privacy`, `/terms` or `/legal` route exists.

You are about to hold Nigerian NGOs' financial records and staff names. You
need a published policy stating what is collected, that content is sent to
Anthropic for processing, retention, deletion rights and a contact address.

### B7 · Postgres adapter has never been run
**Verified.** `store_sql.PostgresStore` is written and marked
`# pragma: no cover - needs a live database`. It has never executed against a
real database.

Do not migrate a live client onto it without running `test_store_sql.py`
against a real `DOCEX_DATABASE_URL` first.

---

## 3. 🟠 HIGH PRIORITY

| | Finding | Evidence |
|---|---|---|
| H1 | **`portfolio/node_modules` committed to git — 352 files** | `git ls-files \| grep node_modules` |
| H2 | **Personal email in tracked source** — `docs/build_product_pdf.py` | `git grep faridmichika@gmail` |
| H3 | **No support address on a real domain** — personal Gmail is the only contact | §15 |
| H4 | **Password minimum is 6 characters** (`auth.py:100`) — too weak for finance | verified |
| H5 | **12-hour session, no idle timeout** — shared office machines stay signed in | `auth.py:61` |
| H6 | **No upload size limit on field receipts** — only Knowledge caps at 50 MB | verified |
| H7 | **No backup job at all** — `SqliteStore.backup()` exists, nothing calls it | verified |
| H8 | **No kill switch** — cannot disable the LLM without a redeploy | §13 |
| H9 | **No staging environment** — changes go straight at whatever is live | §14 |

---

## 4. 🟡 POST-LAUNCH

- Two parallel money-flow systems (`ARCHITECTURE_REVIEW.md`) — vouchers and
  payroll bypass the audit chain. Structural, not a launch blocker, but it
  weakens the audit claim.
- `api/main.py:646` and `knowledge_routes.py:387` hardcode Sonnet instead of
  using `ai_config`, so those calls can't be tuned per deployment
- Phased rollout — with two clients, "NEEM then EVA" is sufficient
- Auditor export to Excel/PDF

---

## 5. 🟢 VERIFIED WORKING

These I tested, not assumed:

- ✅ **Auth is default-deny.** `test_auth_coverage.py` enumerates every route
  and asserts 401 without credentials. Currently green.
- ✅ **No SQL injection surface.** Every query in `store_sql.py` uses bound
  parameters; no f-string SQL anywhere.
- ✅ **Path traversal blocked.** `store._validate()` rejects `..` and anything
  outside `^[A-Za-z0-9][A-Za-z0-9_.-]*$`.
- ✅ **Passwords properly hashed** — PBKDF2-HMAC-SHA256, 200k iterations,
  per-user salt, `hmac.compare_digest` on verify. No plaintext anywhere.
- ✅ **CORS is allowlist-based**, driven by `ALLOWED_ORIGINS`.
- ✅ **Org isolation proven** — `test_org_config.py` runs two orgs side by side
  and asserts neither can see the other's departments, workflow, users or tokens.
- ✅ **Idempotency on create and pay** — a retry after a dropped connection
  replays rather than duplicating.
- ✅ **No secrets in tracked source.** The `sk-ant-` / `sk_test_` matches are
  placeholder strings inside error messages. `.env` is gitignored;
  `.env.example` only.
- ✅ **No analytics or tracking SDKs** — nothing phones home.
- ✅ **No billing/card handling** — Paystack is used only to *verify* bank
  account names. No money moves through this system. §18–19 largely n/a.
- ✅ **22 test suites green.**

---

## 6. 💰 COST RISKS

| Service | Risk | Cap today |
|---|---|---|
| **Anthropic** | 🔴 **Unbounded.** One user looping a check can spend without limit | `max_tokens` per call only |
| **Paystack** | 🟠 Per-lookup cost, no quota | none |
| **Render** | 🟢 Fixed plan | n/a |
| **Vercel** | 🟠 Bandwidth overage possible | free tier |

**The Anthropic exposure is the serious one**, and it is reachable by any
authenticated user.

---

## 7. 🔐 SECURITY & PRIVACY

**Good:** default-deny auth, parameterised SQL, path-traversal guard, strong
password hashing, org isolation, no secrets committed, no tracking SDKs.

**Concerns:**
- No rate limiting → brute-force login and cost abuse both open
- 6-character passwords on a finance system
- No idle session timeout
- No upload size limit on receipts (memory exhaustion)
- Client documents are sent to Anthropic — **true, and currently undisclosed**
- ⚠️ **REQUIRES HUMAN VERIFICATION:** git history for secrets in earlier
  commits (`git log -p | grep -iE 'sk-ant-|sk_live'`) — I checked the working
  tree, not the full history

---

## 8. 🚨 RECOVERY PLAN — currently inadequate

**If the production database disappeared tomorrow, you could not recover it.**
There are no backups running.

What exists: `SqliteStore.backup()` — a consistent online backup method that
nothing calls.

**Required before launch:**
1. Daily automated backup to object storage, separate from the instance
2. 30 daily + 12 monthly retention
3. **One restore actually performed** into a scratch instance, with the date
   recorded
4. Written procedure: how to roll back, how to restore, who to call

---

## 9. 🚀 LAUNCH CHECKLIST

**Blockers — all must be true:**

- [ ] B1 Per-org LLM quota + rate limit, failing closed
- [ ] B2 Paid plan, persistent disk, `DOCEX_DB` — **data verified to survive a redeploy**
- [ ] B3 Sentry live on API and frontend, `send_default_pii=False`
- [ ] B4 SMTP on your domain, SPF + DKIM + DMARC, test email received
- [ ] B5 Password reset + account deletion built and tested
- [ ] B6 Privacy policy and terms published and reachable
- [ ] B7 Postgres verified, or explicitly staying on SQLite

**High priority:**

- [ ] H1 Purge `portfolio/node_modules` from git
- [ ] H2 Remove personal email from source
- [ ] H3 `support@yourdomain` everywhere
- [ ] H4 Password minimum 12 characters
- [ ] H5 Session idle timeout
- [ ] H6 Upload size limit on receipts
- [ ] H7 Backups running, **one restore performed**
- [ ] H8 Kill switch for LLM features
- [ ] H9 Staging environment

**Secrets to set explicitly in production:**

- [ ] `ANTHROPIC_API_KEY`
- [ ] `AUTH_SECRET`
- [ ] `DOCEX_SIGNING_KEY` — **signs the audit chain. Set once, back it up, NEVER rotate.**
- [ ] `ALLOWED_ORIGINS`
- [ ] `SENTRY_DSN`
- [ ] `DOCEX_ORG`, `DOCEX_DB`

**Final gates:**

- [ ] Fresh-email signup → verify → login → use → logout → reset → delete
- [ ] `curl $API/compliance/checks` returns **401** on the deployed instance
- [ ] `python3 demo_check.py` green against production config
- [ ] **Not a Friday**

---

## 10. What I recommend

**Do not launch this week.** B1 and B2 alone are enough — one can cost you
money without limit, the other deletes client records on every deploy.

**A realistic order:**

**Days 1–2 (infrastructure, needs your approval to spend):** paid plan +
persistent disk + `DOCEX_DB` + verify survival · Sentry · backups + one restore

**Days 3–4 (code, no approval needed):** LLM quota + rate limit · password
reset · account deletion · password minimum · idle timeout · upload cap ·
kill switch

**Day 5 (content):** privacy policy · terms · support address · SMTP + DNS

**Day 6:** fresh-account beta run, end to end

**Day 7:** launch to NEEM only. EVA after a week of clean logs.

---

## 11. Beta test checklist — for a real tester, not you

Give this to someone with an email that has never touched the system.

```
ACCOUNT
□ Sign up with a brand-new email
□ Receive the verification email          (does it land in spam?)
□ Verify, then log in
□ Log out, log back in
□ Reset password from the login screen
□ Log in with the new password
□ Delete the account
□ Confirm you cannot log in afterwards
□ Sign up again with the same email

CORE
□ Upload a clear receipt photo            (vendor + amount read correctly?)
□ Upload a blurry/incomplete one          (flagged, or invented?)
□ Upload a non-receipt (holiday photo)    (graceful, or crash?)
□ Upload a 100 MB file                    (rejected cleanly?)
□ Raise a requisition under the threshold
□ Raise one over it                       (route shows the extra approver?)
□ Save a draft, close the tab, come back
□ Submit, approve, record payment
□ Open the audit screen

FAILURE
□ Turn wifi off mid-submit
□ Double-click Submit                     (one requisition or two?)
□ Refresh during approval
□ Leave it 13 hours, then click something (session expiry handled?)
□ Paste 50,000 characters into a text field
□ Open on a phone                         (usable?)

Report: what you did · what you expected · what happened · screenshot
```

⚠️ **REQUIRES HUMAN VERIFICATION** — every item above. I can test the API
in-process; I cannot test a real browser, a real inbox, or a real phone.

---

## 12. What I could not verify

- Git history for secrets in old commits
- Whether email actually delivers (nothing is configured)
- Real browser behaviour, mobile responsiveness
- Actual Render/Vercel/Anthropic account settings and any existing spend caps
- Whether a restore works — no backup exists to restore
- Current provider pricing (verify before quoting anyone)
