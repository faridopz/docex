# Demo Quickstart

**Setup: 3 commands. Verified working.**

---

## Setup (do this before, not during)

Paste one line at a time. `DOCEX_DB` matters — without it the seeder and the API
write to different places and login fails with a 401.

```bash
cd ~/Desktop/docex
```

```bash
DOCEX_DB=./demo.db DOCEX_ORG=default python3 demo_seed.py --reset --password 'DemoPass2026'
```

```bash
python3 make_demo_docs.py
```

**Check OCR is live** — without tesseract the photographed receipt shows nothing:

```bash
python3 -c "import fast_extract; print('OCR:', fast_extract.ocr_available())"
```

Must print `True`. If not: `brew install tesseract`.

## Run it — two terminals

**Terminal 1:**
```bash
cd ~/Desktop/docex && DOCEX_DB=./demo.db DOCEX_ORG=default uvicorn api.main:app --reload --port 8000
```

**Terminal 2:**
```bash
cd ~/Desktop/docex/web && npm run dev
```

**Sign in:** <http://localhost:3000/login> · `demo@neem.org` / `DemoPass2026`

> `DOCEX_DB` must be set on the **API terminal too**. Miss it there and the API
> reads an empty store — you'll log in fine and see nothing.

---

## What's waiting for you

| Screen | Content |
|---|---|
| Requisitions | REQ-0001 clean ₦96,000 · **REQ-0002 BLOCKED ₦140,000** |
| Payments | REQ-0003 ₦47,500 · REQ-0004 ₦95,000, both paid |
| Audit | 1 explained exception · verdict **audit-ready** |
| Field receipts | 3, including a **photographed** one OCR'd to ₦47,500 |

`demo_docs/` holds seven files to drag in **live** — far more convincing than
rows that were already on screen.

| File | Shows |
|---|---|
| `01_invoice_venue_hire.pdf` | Reads TOTAL ₦129,000, not SUBTOTAL ₦120,000 |
| `02_payment_voucher_training.xlsx` | Spreadsheets read too |
| `03_market_receipt_photo.png` | **OCR off a photo** — the field story |
| `04_transport_receipt_incomplete.txt` | Vendor blank + flagged, nothing invented |
| `05_invoice_..._RESUBMITTED.pdf` | Duplicate of 01 |
| `06_fuel_receipt_scan.pdf` | OCR off a scanned PDF |
| `07_damaged_upload.pdf` | Says "damaged", not "vendor missing" |

---

## The run-through (12–15 min)

### 1 · Field receipts — their problem, answered (3 min)

Point at the **photographed** receipt.

> "Someone photographs a handwritten receipt in a market. No signal, no typing.
> The system reads the vendor, the date and the total off the photograph."

Then the one with **no vendor**:

> "This came in incomplete — which is normal, and the system says so rather than
> inventing a supplier to fill the gap. The blank is the honest answer, and
> finance can see exactly what's missing."

**Then ask:** *"How do receipts reach your finance team today?"*

### 2 · Raise a payment (3 min)

Requisitions → New. Keep it **under ₦250,000**.

> "Policy checks run the moment it's submitted — not three days later when an
> approver bounces it back. Whoever raised it sees the problem while the invoice
> is still open in front of them."

**Then ask:** *"Which of these rules matter most to you?"*

### 3 · The blocked payment — ⭐ the moment (5 min)

Open **REQ-0002 · Northern Logistics · ₦140,000**.

> "This is charged to a grant that closed in December 2024. Donor rules only
> allow costs inside the agreement period, and charging outside it is one of the
> most common audit findings there is. The system caught it by comparing two
> dates — code, not a model."

**Try to Approve. The button is disabled.** Hover it.

> "I can't approve this, and neither can anyone else, until three things exist:
> the specific check ticked, a written reason, and the authority it's being
> released under."

Tick the check. Write a reason. Name the authority. Approve. Record payment.

> "That's now permanently attached, against my name."

**Then ask:** *"When did someone last release an exception? Where is that
recorded?"*

The answer is usually *"in an email somewhere"* or *"nowhere"*. **That is your
product, in their words.**

### 4 · Audit — close here (2 min)

> "This is what your auditor opens. Every exception, who released it, why, and
> under what authority. If a payment went out over a failing check with no
> explanation, this reads 'N unexplained' in red — and you fix it before the
> auditor arrives, not after."

**Close on:**

> "Most systems record an override. This one refuses an unexplained one."

---

## Guardrails

- **Keep amounts under ₦250,000.** Above that routes to Executive Approval,
  where nobody is signed in, and it will sit there.
- **Demo from the laptop.** Not a live URL — cold starts and venue wifi are
  risks you don't need.
- **Screenshots of all four screens on your phone** before you leave. Five
  minutes of insurance.

## If something breaks

| Problem | Fix |
|---|---|
| Login 401 | `DOCEX_DB` missing on one of the terminals — both need it |
| Blank screen | Check both terminals are running |
| Data looks wrong | Re-run the seed command; takes seconds |
| OCR shows nothing | `brew install tesseract`, restart the API |
| Total meltdown | Phone screenshots. Talk through the audit screen. |

## Reset between meetings

```bash
DOCEX_DB=./demo.db DOCEX_ORG=default python3 demo_seed.py --reset --password 'DemoPass2026'
```

Seconds, and the blocked payment is back for the next run-through.
