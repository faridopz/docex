# DOCex — Demo Run-of-Show (v2)

_Scope: Compliance, Payment Requisition, and Payment Pipeline only. Keep this
open on your second screen._

---

## Access

- **Frontend:** https://docex-demo.vercel.app
- **Backend:** https://docex-production-e070.up.railway.app (`/health` should return 200)
- **Login:** `demo@docex.app` / `docex-demo`
- Front door is a demo gate, not real auth — fine for demos, don't call it "auth."

⚠️ `docs/DEPLOY_CHECKLIST.md` references a *different* Vercel project
(`docexdemodeploy.vercel.app`). Confirm which one is actually current before
seeding — see GO_NO_GO.md §0.

---

## The story (15s cold open)

"A payment requisition comes in. Someone has to check it against policy,
route it for sign-off, and keep a defensible record of every decision — all
before finance can pay it. Right now that's manual, in someone's inbox and
head. DOCex turns the policy into rules, runs every requisition against them,
and tracks it through to paid — with a citation for every verdict."

---

## Flow 1 — Compliance: the rulebook (2 min)

**Where:** `/compliance`

1. Open the TA Connect rulebook. "This came from a real procurement policy
   PDF — AI drafted the machine-checkable rules, a human reviewed and edited
   them." Point at rule count / last-updated.
2. Land the reusability point: "Upload once, run checks forever" — every
   requisition from here on is checked against this same rulebook.

---

## Flow 2 — Submit a Payment Requisition (3 min)

**Where:** `/compliance/submit`

1. "This is the form anyone in any department fills out — no rulebook
   knowledge required." Pick a payment type (e.g. **Procurement Payment**)
   and show the required-documents checklist appear automatically
   (PO, Invoice, Goods Received Note).
2. Drop in the pre-staged documents, add a label, submit.
3. DOCex auto-routes the bundle to the right rulebook and runs the check
   live. Land on the verdict.
4. Walk one clean requisition → **Approved**, and (switch to a pre-run
   example if needed) one **Flagged/Blocked** requisition — point at a
   specific rule, the policy citation, and the payment evidence side by
   side. "It doesn't just say no — it says which clause, and why."

---

## Flow 3 — Payment Pipeline board (3 min)

**Where:** `/compliance/board`

"This is where every requisition and voucher sits, end to end — mirrors the
real finance flow: request → finance → compliance → director → ED → paid."

Walk the columns left to right:

- **Needs attention** — blocked, flagged, or has an open risk
- **Requisition** — checked, before a PV (Payment Voucher) is raised
- **In approval (PV)** — voucher raised, moving through sign-off
- **Approved** — signed off, ready for payment
- **Paid** — payment executed

Click into one card mid-pipeline to show the stage label update live, and
click "Mark paid" on one card in **Approved** to show it move to **Paid**.

---

## Flow 4 — Saved check: audit trail & escalation (3 min)

**Where:** `/compliance/checks/[id]` (open from the board or Pending Inbox)

1. Open a flagged check. Show the **verdict screen** — per-rule pass/flag/
   block, each cited from both the policy and the requisition documents.
2. Show the **Risk & Actions panel** — severity, action taken, escalation,
   resolution status. "This is the officer's own report, not just the AI's."
3. Show **Escalate / Request clarification** — an email goes out (Outlook/
   Gmail), the reply comes back into the same thread, logged to the audit
   trail. "No more losing the thread in an Outlook chain."
4. Approve it. Point at the frozen rulebook snapshot: "Even if the policy
   changes next month, this record still shows exactly what it was checked
   against — defensible a year later." Export the audit history.
5. (Optional) Open `/compliance/pending` — "this is the officer's morning
   view: what needs a decision, and what's waiting on someone else's reply."

---

## Close

"A requisition that used to sit in someone's inbox for days now moves
through a visible pipeline, with every verdict cited and every decision
timestamped — from submission to paid."

---

## Golden rules

1. Drive from rehearsed inputs (the seeded requisitions/checks in GO_NO_GO.md);
   if handed a random document, "I'll run it live right after and send you
   the result."
2. Lead with the verdict and the pipeline board — not the upload form.
3. Say the citation out loud every time. That's the differentiator.
4. Be honest about what's next: durable persistence beyond the Railway
   volume isn't built yet (no real database), and the Power Automate/Outlook
   approval flow needs to be wired inside the client's own Microsoft 365
   tenant — the email magic-link flow is what's live today.

## Objection handling

- **"Isn't this just ChatGPT?"** → It turns a policy into a reusable
  rulebook, cites both sides of every verdict, and freezes an audit trail.
  A chat prompt can't give a team that consistency or defensibility.
- **"How do we trust the AI?"** → You don't have to — every verdict points
  to the source, and a human signs off. The AI does the first pass; the
  decision stays yours.
- **"What happens to a payment that's missing something?"** → It's flagged
  with the exact missing evidence, routed to Needs attention, and the
  officer can request clarification without leaving the thread.

## After the demo

- [ ] Ask for their real approval chain (roles + directory) and one real
  policy document (enables a tailored pilot)
- [ ] Log outcome + next action in the pilot tracker
