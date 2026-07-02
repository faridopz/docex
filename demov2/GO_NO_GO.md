# DOCex — Go/No-Go & Seeding (v2)

_Run this the morning of. Scope: Compliance / Payment Requisition / Payment
Pipeline only. ~15 min._

---

## 0. Environment: Vercel + Railway

- [x] Environment chosen: **Vercel (frontend) + Railway (backend)** — not AWS
- Frontend: https://docex-demo.vercel.app
- Backend: https://docex-production-e070.up.railway.app

⚠️ **Unresolved discrepancy:** `docs/DEPLOY_CHECKLIST.md` sets up a
*different* Vercel project (`docexdemodeploy.vercel.app`) pointed at the same
Railway backend. Before seeding, open both Vercel URLs and confirm which one
is actually wired to the live backend (check Network tab → calls should go
to the Railway URL, not `localhost`, and return 200 with no CORS errors — see
`docs/DEPLOY_CHECKLIST.md` Part D). Seed and demo from the **same** one you
verify. If both are live, retire the one you're not using so this doesn't
bite the next demo too.

- [ ] Confirmed which Vercel project is live and correctly wired
- [ ] **Railway volume check** — Settings → Volumes → mount path is `/app`.
  Without this, the *next* redeploy silently wipes rulebooks, requisitions,
  checks, and the audit trail (per `docs/DEPLOY_CHECKLIST.md`). Confirm this
  BEFORE seeding, not after.
- [ ] No `git push` to `demo-release` planned between seeding and the demo
  (even with the volume mounted, a mid-seed redeploy is just extra risk)

---

## 1. Go / No-Go (~10 min)

- [ ] `docex-production-e070.up.railway.app/health` returns `{"status":"ok"}`
- [ ] Sign in at the confirmed Vercel URL → lands on `/home`, no red errors
- [ ] `/compliance` loads and shows the TA Connect rulebook
- [ ] `/compliance/submit` loads, payment types populate, required-documents
  checklist appears when you pick a type
- [ ] `/compliance/board` loads with cards in more than one column (not all
  empty, not all in one bucket)
- [ ] `/compliance/pending` shows at least one awaiting-decision item
- [ ] Loom fallback of the flow open in a hidden tab (connectivity insurance)
- [ ] Notifications off, browser full-screen, extra tabs closed

---

## 2. Seed the instance (do once, before first demo)

On the **live** environment you chose above:

1. Confirm the TA Connect rulebook is loaded (or create it: New policy set →
   upload the procurement policy).
2. Submit **3–4 requisitions** through `/compliance/submit` so the pipeline
   board isn't empty and spans multiple columns:
   - 1 clean **Procurement Payment** → should land Approved-ish / low in the
     pipeline
   - 1 **flagged** requisition (e.g. missing GRN) → sits in Needs attention
   - 1 requisition you deliberately move to **In approval (PV)**
   - 1 you mark **Paid** (via the board's "Mark paid" action) so the Paid
     column isn't empty
3. On the flagged check, actually use **Request clarification** once and
   reply to it, so the query thread + audit trail aren't empty on screen.
4. Log one entry in the **Risk & Actions** panel on the flagged check.

---

## 3. Known gaps — be ready to answer honestly if asked

- **No real database yet.** Persistence today is a single Railway volume,
  not S3 + a managed database (Phase 2). Fine for a pilot demo, not a
  multi-tenant production answer if asked.
- **Outlook/Teams approvals (Power Automate)** — the DOCex side is built
  (`approval_webhook.py`, `/compliance/approval-callback`), but the 3-step
  flow itself has to be built inside the client's Microsoft 365 tenant.
  Today's live path is the email magic-link, which works end to end.
- **Single demo login, no real multi-tenant auth yet** (Supabase auth is
  Phase 2).

---

## 4. After

- [ ] Note anything that broke or felt shaky — feed it back into
  `docs/DEMO_READINESS_CHECKLIST.md` for the next round.
