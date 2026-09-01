# NEEM demo — runbook

## Read this first

**Demo from your laptop, not the live URL.** Three reasons, in order of how
badly each would hurt:

1. **The live site does not have any of this work.** The push never completed —
   remote is still on the old commit. No requisitions, no payments, no audit,
   no OCR.
2. Render's free tier sleeps after ~15 minutes. A 30–50 second blank screen
   while someone watches you is the worst possible moment for it.
3. Venue wifi. Local needs no network at all.

Deploying tonight is possible but it means an unverified Vercel build a few
hours before you present. Local is the safe call. If they ask whether it's
deployed, "it runs in the cloud, I'm showing you locally so we're not at the
mercy of the wifi" is a completely normal thing to say.

---

## Setup (10 minutes, do it tonight)

```bash
cd ~/Desktop/docex

# 1. dependencies — pymupdf and tesseract matter for the receipt demo
pip install -r requirements.txt
brew install tesseract          # macOS. Without it, OCR silently does nothing.

# 2. confirm OCR is actually live
python -c "import fast_extract; print('OCR ready:', fast_extract.ocr_available())"

# 3. seed the demo data + your login
python demo_seed.py --reset

# 4. build the frontend NOW, not tomorrow
cd web && npm run build && cd ..
```

Then two terminals:

```bash
# terminal 1
uvicorn api.main:app --reload --port 8000

# terminal 2
cd web && npm run dev
```

Sign in at <http://localhost:3000/login> as `demo@neem.org`.

**Do a full dry run tonight.** Every step below, start to finish. Do not let
tomorrow be the first time.

---

## What the seed puts in front of you

| Screen | Content |
|---|---|
| Requisitions → Waiting on me | REQ-0001 clean ₦96,000 · **REQ-0002 blocked ₦140,000** |
| Payments | Two paid — one clean, one carrying an exception |
| Audit | 1 explained exception, verdict "Audit ready" |
| Field receipts | 3, including a **photographed** market receipt and one with no vendor |

REQ-0002 is deliberately left blocked and sitting in your queue, at an amount
your login has authority to release. That is the live moment.

---

## The demo (12–15 minutes)

### 1. Their pain point first (3 min) — field receipts

Open the field receipts list. Point at the **photographed market receipt**.

> "Amina photographs a handwritten receipt in a market. No signal, no typing.
> The system reads the vendor, the date and the total off the photograph."

Then the one with **no vendor**:

> "This one came in incomplete — which is normal, and the system says so
> rather than rejecting it. It doesn't invent a vendor to fill the gap. The
> blank is the honest answer, and finance can see exactly what's missing."

That is their stated problem, answered in ninety seconds.

### 2. Raise a payment (3 min)

Requisitions → New. Fill it in, submit.

> "Policy checks run the moment it's submitted — not three days later when an
> approver bounces it back. Whoever raised it sees the problem while the
> invoice is still open in front of them."

### 3. The blocking check — the important part (5 min)

Open **REQ-0002, Northern Logistics, ₦140,000**.

> "This one is charged to a grant that closed in December 2024. Donor rules
> only allow costs incurred inside the agreement period, and charging outside
> it is one of the most common audit findings there is. The system caught it
> by comparing two dates."

Now try to Approve. **The button is disabled.** Hover it.

> "I can't approve this, and neither can anyone else, until three things
> exist: the specific check ticked, a written reason, and the authority it's
> being released under."

Tick the check. Write a reason. Name the authority. Approve.

> "That's now permanently attached to the payment, against my name."

Record payment with any bank reference.

### 4. Audit (3 min) — close on this

Open Audit.

> "This is what your auditor opens. Every exception, who released it, why, and
> under what authority. The verdict at the top is the whole product: if a
> single payment went out over a failing check with no explanation, this reads
> 'N unexplained' in red and you fix it before the auditor arrives, not after."

> "Most systems record an override. This one refuses an unexplained one."

---

## If they ask

**"Does it work offline?"**
Yes — that's the KoboCollect integration. The backend is built and tested;
the field app connection is still being finished. Fieldworkers capture on
KoboCollect offline as they already do, and receipts log automatically as soon
as a phone gets signal. Honest, and it's genuinely close.

**"Can it read our Excel vouchers / PDF invoices?"**
Yes — Excel, Word, PDF, CSV, photos, scans. Offer to drop one of *their* files
in live. It handles a scanned PDF and a phone photo through OCR.

*(If you do this: it reads the labelled TOTAL, and correctly ignores SUBTOTAL —
that was a real bug found and fixed this week. But don't promise perfection on
an unseen document. "Let's see" is a strong answer; being wrong in front of
them is not.)*

**"What happens if two people submit the same invoice?"**
Duplicate detection on vendor + amount inside a configurable window. And a
receipt can only back one payment — attach it to a second and it blocks.

**"Is our data safe / where does it live?"**
Runs in the cloud, one instance per organisation, your data never mixes with
another org's. Durable Postgres storage is the next infrastructure piece.
Don't overclaim here.

**"How much?"**
₦250,000/month for an org their size. Anchor on prevention: one audit finding
costs vastly more than a year of this.

---

## Do not demo these

- **Onboarding wizard** — doesn't exist. Configuration is manual today.
- **Auditor export** — the Audit screen is on-screen only, no Excel/PDF export.
- **Bank reconciliation** — not built.
- **Procurement quote rules** — required documents is one flat list today, not
  banded by amount. If they ask about three-quote rules, say it's next up.
  It's the honest answer and it's genuinely the next thing.
- **Anything above ₦250,000** — routes to Executive Approval, a department with
  no user logged in, so it will sit there. Keep demo amounts under ₦150,000.

---

## If something breaks

**Blank screen / API errors** — check both terminals are running. The frontend
talks to `localhost:8000`.

**Can't sign in** — `python demo_seed.py` again, it resets the password.

**Data looks wrong after you've clicked around** — `python demo_seed.py --reset`
rebuilds it in about five seconds. You can do this between meetings.

**OCR shows nothing on the photo** — tesseract isn't installed. `brew install
tesseract`, restart the API. Check tonight, not tomorrow.

**Worst case, everything is broken** — talk through the Audit screen from a
screenshot. Take screenshots of all four screens tonight and keep them in your
phone. Five minutes of insurance.
