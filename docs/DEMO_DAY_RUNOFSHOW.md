# DOCex — Demo Day Run-of-Show

One page to run a demo from. Consolidates the link, credentials, go/no-go,
the flow, and objection handling. Keep this open on your second screen.

---

## Access

- **Demo URL:** https://docex-demo.vercel.app
- **Login:** `demo@docex.app` / `docex-demo`
- **Backend:** https://docex-production-e070.up.railway.app (`/health` should be 200)
- Front door is a demo gate, not security — fine for demos, don't call it "auth".

---

## Go / No-Go (run the morning of, ~10 min)

- [ ] `docex-production-e070.up.railway.app/health` returns `{"status":"ok"}`
- [ ] Sign in at the demo URL → lands on `/home`, no red errors
- [ ] Compliance page loads (rulebook list renders — empty is fine if not seeded)
- [ ] **Live instance is seeded** (see "Seed the instance" below) — the #1 thing that makes or breaks the demo
- [ ] Bank Verify: have the pre-computed colour-coded Excel open (don't burn the 3/day Paystack test cap live)
- [ ] Loom fallback of the main flow open in a hidden tab (wifi insurance)
- [ ] Notifications off, browser full-screen, noisy tabs closed

---

## Seed the instance (do once, before first demo)

The Railway volume starts empty. Before demoing, on the **live** site:
1. Create your TA Connect rulebook (New policy set → upload the procurement policy).
2. Load 2–3 demo documents into Knowledge / Extract.
3. Run one **clean** voucher and one **flagged/blocked** voucher so Saved Checks
   and the audit log aren't empty on screen.

---

## The flow — TA Connect / sub-award track (8–10 min)

**Cold open (15s):** "You receive documents in bulk and a human reads every one
to answer the same questions and check the same rules. DOCex does that for you —
with the answer, the source, the exact quote, and an audit trail."

1. **Extraction (lead with this — strongest, go live).**
   Show the question set ("Is this org registered with CAC?", "What states do
   they work in?", "Have they managed donor funds before?"). Upload one
   applicant's docs, run it. Walk a row: answer → confidence chip → **source doc
   + page + verbatim quote**. Show a `not_found` row: "It didn't guess — that's
   what auditors need." Switch to batch view → one row per applicant → Export.

2. **Compliance (the wedge).**
   Open a rulebook: "This was generated from a policy PDF, then a human edits it
   — the policy becomes machine-checkable rules." Run a clean voucher → APPROVED,
   per-rule verdicts cited from both sides. Run a problem voucher → FLAGGED/
   BLOCKED with the named rule. Land the **decision log + verified sign-off**:
   "Every check, escalation, and signature is timestamped and frozen — defensible
   a year later."

3. **Bank Verify (show pre-computed Excel).**
   Point at a 92 (typo caught), a 67 (warning), a 61 (mismatch). "Catches the
   typo and the genuinely wrong account."

**Close:** "Screening a 200-applicant cycle goes from weeks of reading to an
afternoon of review — every answer cited, every approval defensible."

---

## Golden rules

1. Drive from rehearsed inputs; if handed a random doc, "I'll run it live right
   after and send you the result."
2. Lead with the verdict, not the upload.
3. Every answer is cited — say it out loud. That's the differentiator.
4. Be honest about Phase 2 (logins/multi-org): "That's the next build, and your
   pilot is what we design it around."

---

## Objection handling (from the agentic-compliance research)

- **"Isn't this just ChatGPT?"** → It turns a policy into a reusable rulebook,
  cites both sides of every verdict, and freezes an audit trail. A chat prompt
  can't give a team that consistency or defensibility.
- **"The Big Four have AI now."** → Exactly — they proved the model (policy-as-
  rules, flag-the-risk, human-signs-off, full audit trail). DOCex brings the same
  pattern to the sub-award and procurement teams the Big Four will never serve,
  at a price they can adopt.
- **"How do we trust the AI?"** → You don't have to trust it — every answer
  points to the source, and a human verifies and signs off. The AI does the
  first pass; the decision stays yours.

---

## After the demo

- [ ] Ask for their standard question set + one real policy (enables a tailored pilot)
- [ ] Log outcome + next action in the pilot tracker
