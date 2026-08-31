# Review the new screens locally

Everything is committed on `demo-release` but **not pushed** — nothing has
deployed. Run it on your machine, click through, then we push.

## 1. Start the API (terminal 1)

```bash
cd ~/Desktop/docex
uvicorn api.main:app --reload --port 8000
```

Your `ANTHROPIC_API_KEY` is already in `.env`. Storage defaults to the local
JSON store at `./data/` (now gitignored), so nothing you click here can reach
the live demo.

Check it came up: <http://localhost:8000/health>

## 2. Start the frontend (terminal 2)

```bash
cd ~/Desktop/docex/web
npm run build   # <- the one thing I could NOT finish in my sandbox
npm run dev
```

Run `npm run build` first. `tsc --noEmit` passed clean on my side, so types are
sound, but the webpack bundle and route prerender never completed — the sandbox
CPU ran it past 15 minutes. If it builds here, it'll build on Vercel.

Then open <http://localhost:3000>.

## 3. Sign in

If this is a fresh `./data/`, the app will send you to `/setup` to create the
first admin. Give yourself `department: finance` and `role: admin` so you can
approve *and* pay.

## 4. What to click, in order

**a. Raise one that's clean** — `/requisitions/new`
Small amount, fill in category and project code. Submit.
→ You should land on a green "every policy check passed" result with the ref.

**b. Raise one that breaks policy** — same form, amount above your ceiling
(if no ceiling is configured yet, leave the vendor name as something odd or
skip the required documents).
→ Red banner, and the blocking checks listed. This is the moment that matters:
the submitter sees the problem *now*, not three days later on a bounce-back.

**c. Try to approve it** — open it from `/requisitions`
→ **Approve should be disabled.** Hover it — the tooltip tells you why.
Now tick the blocking check, write a reason, name an authority.
→ Approve enables. That's the rule the whole product rests on.

**d. Pay it** — the Record payment card appears once it's fully approved.
→ Freezes the transaction. Go to `/payments/[id]`: everything is locked, and
the checks shown are *as applied*, not recomputed.

**e. Open `/audit`**
→ Your override from step (c) is listed with your reason and authority. If you
had somehow released one without a reason, the verdict at the top would read
"N unexplained" in red instead of "Audit ready".

**f. The queue** — `/requisitions`, "Waiting on me" tab
→ Should show what's sitting with your department, with aging in red past 3
days.

## 5. Things I'd like your eye on

- **Wording on the override panel.** It's deliberately blunt ("recorded against
  your name and read at audit"). Too much for a colleague, or about right?
- **Is "Waiting on me" the right default tab**, or do your users want "All"?
- **The purple treatment for a released FAIL.** It's a third colour on purpose —
  neither green nor red. Does it read clearly to you?
- **Amount input** is a plain text field, not a formatted currency input. Fine
  for now, or do you want thousands separators as you type?

## 6. When you're happy

```bash
git push origin demo-release
```

That triggers the Render + Vercel auto-deploy. Tell me and I'll do it.
