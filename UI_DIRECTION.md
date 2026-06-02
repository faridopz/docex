# DOCex — UI Direction
*Last updated: 2 June 2026 · Owner: Farid*

The current UI is functional, clean, and boring. Anthropic-grade type
choices but Linear-level component complexity. We want it to feel like
**a product you remember** — not a SaaS form-filler.

This doc sets the direction. The actual rebuild gets its own task
(`prompts/ui-overhaul.md`). The landing + compliance hub get a partial
refresh this session as proof.

---

## 1. The bar

Three reference products. Each contributes one specific thing.

| Product   | What we copy                                                                |
| --------- | --------------------------------------------------------------------------- |
| Spotify   | Confidence in big type. Mood-led colour. Cards with personality.            |
| Linear    | Density done right. Keyboard shortcuts. Status as colour, not chrome.       |
| Notion    | Empty states that teach. Inline editing. No modal-heavy flows.              |
| Vercel    | Marketing pages with depth. Real screenshots, not stock illustrations.      |

We do NOT copy: heavy animation (Stripe), illustration-led marketing
(Loom), dashboard-first (Datadog). DOCex is a *tool* you visit briefly
to make a decision, then leave. UI should respect that.

---

## 2. Foundations

### Type
- **Display:** Geist (current) at 700/600 weight, tracking-tight. Use it BIG.
  - Landing hero: `text-7xl font-semibold tracking-tight`
  - Section headers: `text-4xl font-semibold leading-[1.1]`
- **Body:** Geist regular. Line-height generous (1.6+) for long copy.
- **UI:** Geist Mono for IDs, timestamps, file sizes. Keep it rare.
- Never: serif fonts, italic body, all-caps headings (except eyebrow labels).

### Colour
Keep the warm-cream `#fafaf7` background — it's already distinctive. But
push the accent palette wider:

| Token             | Hex         | Use                                       |
| ----------------- | ----------- | ----------------------------------------- |
| `brand-600`       | `#2563eb`   | Primary CTA, links, "approved" state      |
| `warm-cream`      | `#fafaf7`   | Page background                           |
| `ink-900`         | `#111827`   | Body text                                 |
| `emerald-500`     | (current)   | Pass / found / approved                   |
| `amber-500`       | (current)   | Flag / inferred / pending                 |
| `rose-500`        | (current)   | Block / not-found / rejected              |
| `electric-violet` | `#7c3aed`   | NEW — Co-Pilot brand. Used for agent UI   |
| `sunrise`         | `#f97316`   | NEW — Highlight / "new" badges            |

Add ONE bold gradient — diagonal `amber-50 → cream → violet-50` — used
sparingly on the hero, on result-page hero cards, and on the Assistant
brief. Never on small components.

### Motion
Currently zero. Add this much, no more:
- Page transitions: 200ms fade (Next.js `useTransition`)
- Card hover: `transition-shadow` + 1px shadow lift, 150ms
- Number changes (e.g. "12 → 13 checks today"): tabular-nums + CSS
  flip (`@keyframes slot-flip`)
- Loading: keep the spinner BUT show a skeleton card with the right
  layout, not a blank box

### Shape
- Cards: `rounded-2xl` or `rounded-3xl` consistently. No squared corners.
- Borders: `border-gray-100` is too faint. Use `border-gray-200` and let
  the cream bg do the contrast work.
- Shadows: barely-there. `shadow-sm` for elevation 1, `shadow-md` for 2.
  Never `shadow-lg`.

---

## 3. Layout patterns

### The "decision card"
Currently most result pages dump a table. Replace with a "decision card":

```
┌────────────────────────────────────────────────┐
│ Verdict pill · Voucher #PV-2026-0142           │
│                                                │
│   12 of 15 rules pass · 2 flag · 1 block       │
│                                                │
│ ┌──────────────────────────────────────────┐   │
│ │ Assistant brief (the Claude one-liner)   │   │
│ └──────────────────────────────────────────┘   │
│                                                │
│ [ Approve ]  [ Escalate ]  [ Ask question ]    │
└────────────────────────────────────────────────┘
```

Big, opinionated, single-decision. The table goes BELOW, collapsed
behind a "See rule-by-rule breakdown" affordance. Most users will never
expand it.

### The "queue" (pending inbox, sub-award)
Spotify-grade list rows. Each row earns its space:
- Album-cover-equivalent: a coloured tile with the verdict icon
- Big title (voucher number / applicant name)
- Medium subtitle (Assistant one-liner)
- Right side: chips for who-it's-with, last-event, age
- Hover: row lifts 2px, accent column appears on the left edge

### Navigation
Currently flat. Move to a left-sidebar persistent nav once we have
auth. Pre-auth, keep the top-bar but make it CONTEXTUAL:
- Inside Compliance → only show Compliance subpages
- Inside Sub-award → only show Sub-award subpages
- A single "Switch app" pill in the top-right takes you across primitives

### Empty states
Every empty state should teach the next action AND have a "Try with
sample data" button. The sample data is real fixtures from
`demo_fixtures/`. Click → seeded → user immediately sees what a
populated state looks like.

---

## 4. Marketing pages

The landing is the only marketing page right now. After auth:

- `/` — landing (rewritten this session)
- `/pricing` — three tiers (Free / Pro / Enterprise) with switch toggle
  (per-month vs per-year)
- `/customers` — case studies (once we have one)
- `/security` — SOC-2 talk (when we get there)
- `/docs` — API docs once anyone asks

Hero pattern (already mostly there): eyebrow chip → BIG type headline →
warm subtitle → two CTAs (primary + secondary text-link).

Avoid: illustrated heroes, stock photos, fake browser screenshots,
"Trusted by [logo soup]" before we have real logos.

---

## 5. Component library

Today: shadcn/ui base + a few custom ones. Add over time:

| Component        | Status   | Notes                                          |
| ---------------- | -------- | ---------------------------------------------- |
| Button           | Have     | Add `ghost-violet` variant for Co-Pilot CTAs   |
| Card             | Have     | Add `decision-card` variant (see §3)           |
| Pill / Badge     | Have     | Add `gradient` variant for Assistant brief     |
| EmptyState       | Need     | One reusable, takes title/body/CTA/sampleData  |
| Skeleton         | Need     | Replace generic spinners on every list page    |
| KeyboardShortcut | Need     | Tiny `kbd` chips for `⌘+Enter` etc             |
| Toast            | Need     | Replace inline error blocks where transient    |
| CommandPalette   | Need     | `⌘+K` to jump between agents (post-auth)       |

---

## 6. Concrete first-pass changes (today)

1. **Landing** — rewritten this session. Generic framing, gradient hero,
   restructured trust section.
2. **Compliance hub** — header chip stays "Your internal auditor,
   automated" (already strong), but stat cards get the gradient treatment.
3. **Decision card** — proof-of-concept on the compliance check detail
   page. Other pages follow in the dedicated task.

Everything else is in `prompts/ui-overhaul.md`.

---

## 7. Anti-patterns to avoid

- Don't add a chatbot widget. We HAVE Claude in the UI as the Assistant
  brief. A separate widget is noise.
- Don't add tooltips for the obvious. If a button needs a tooltip, the
  label is wrong.
- Don't gate features behind "Coming soon" badges. Either ship or hide.
- Don't add dark mode until we've shipped 3 pilots. It doubles design
  work for zero pilot value.
- Don't add product analytics beacons that send keystrokes. The
  self-learning system reads OUR data (sessions, checks, errors), not
  the user's content.
