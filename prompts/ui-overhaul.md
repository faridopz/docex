# Stream A5 — UI Overhaul (Spotify-Grade)

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read in order:
1. `/PLAN.md`
2. `/CLAUDE.md`
3. `/UI_DIRECTION.md` — the design direction document, READ THIS CAREFULLY
4. `/SOUL.md`
5. This file

## What this stream delivers

A consistent, opinionated UI across every page. The bar: a CTO doing
diligence opens DOCex, scrolls one page, and goes "okay, real product."
We currently look like a competent SaaS. We need to look like a
considered product.

## What already exists (changed by Farid on 2 June 2026)

- `/web/app/page.tsx` — landing was reframed to global/cohesive copy
  with a violet-amber gradient. Use it as the visual reference.
- Warm cream bg `#fafaf7` is the brand background everywhere.
- Geist font family already wired up.
- shadcn/ui for primitives.

## What to build

### 1. Component library expansion

Add these reusable components to `/web/components/ui/`:

| Component               | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `EmptyState.tsx`        | Reusable: icon, title, body, primary CTA, sample-data CTA |
| `Skeleton.tsx`          | Card/list/text skeletons (replace generic spinners)  |
| `KeyboardShortcut.tsx`  | Inline `⌘+Enter` chip                                |
| `Toast.tsx`             | Top-right transient notifications                    |
| `CommandPalette.tsx`    | `⌘+K` global jump (post-auth)                        |
| `DecisionCard.tsx`      | The opinionated single-decision result card (see §3) |
| `GradientBadge.tsx`     | Used for Assistant brief, "new" badges               |
| `Sidebar.tsx`           | Persistent left nav (post-auth)                      |

### 2. Page-by-page refresh (priority order)

Each page gets a refresh PR. Don't try to do them all at once.

1. **Compliance check detail** (`/web/app/compliance/checks/[id]/page.tsx`)
   - Adopt the DecisionCard pattern (big verdict at top, Assistant
     brief in card, action buttons, rule table collapsed)
   - This is the page customers see most — earn it
2. **Pending Inbox** (`/web/app/compliance/pending/page.tsx`)
   - List rows in Spotify-grade format (album-cover icon, big title,
     subtitle, chips, hover lift)
3. **Sub-award** (`/web/app/agents/sub-award/page.tsx`)
4. **Attendance Payment** (`/web/app/agents/attendance-payment/[id]/page.tsx`)
5. **Bank Verify results** (`/web/app/verify/[id]/page.tsx`)
6. **Knowledge Hub library** (`/web/app/knowledge/page.tsx`)
7. **Saved checks list** (`/web/app/compliance/checks/page.tsx`)

### 3. The DecisionCard pattern

The single most-important visual primitive. See `UI_DIRECTION.md §3`.

```tsx
<DecisionCard
  verdict="flagged"
  title="Voucher #PV-2026-0142"
  subtitle="12 of 15 rules pass · 2 flag · 1 block"
  assistantBrief="The vendor's CAC is missing but their previous voucher (last month) cleared with the same paperwork — likely an upload omission, not a compliance issue."
  primaryAction={{ label: "Approve", onClick: ..., requiresSignature: true }}
  secondaryActions={[
    { label: "Escalate", onClick: ... },
    { label: "Ask question", onClick: ... },
  ]}
  expandable={<RuleByRuleBreakdown rules={...} />}
/>
```

### 4. Navigation refresh (post-auth only)

Once auth is shipped, replace the top-bar with a persistent left
sidebar:

```
┌───────────┬─────────────────────────────┐
│ DOCex     │                             │
├───────────┤    [page content]           │
│ Inbox  ▸  │                             │
│ Co-Pilots │                             │
│   Sub-aw. │                             │
│   Prog.   │                             │
│   Compli. │                             │
│ Primitives│                             │
│   Verify  │                             │
│   Knowl.  │                             │
│ Account   │                             │
└───────────┴─────────────────────────────┘
```

Active state: full violet bar on the left of the active item +
brand-600 text.

### 5. Motion + microinteractions

- Page transitions: 200ms fade via `useTransition` from Next.js
- Card hover: shadow lift 150ms
- Tabular numbers on every count, with CSS flip animation on change
- `⌘+K` opens command palette anywhere (post-auth)
- `⌘+Enter` submits any form that has it labelled

### 6. Empty states

Every list/dashboard page gets an EmptyState component with:
- Title that names the state ("No checks yet")
- Body that teaches the next action
- Primary CTA — what to do
- Secondary CTA — "Try with sample data" (calls `demo_fixtures` seed)

## Files to touch

A lot. Roughly:

```
/web/components/ui/EmptyState.tsx           NEW
/web/components/ui/Skeleton.tsx             NEW
/web/components/ui/KeyboardShortcut.tsx     NEW
/web/components/ui/Toast.tsx                NEW
/web/components/ui/CommandPalette.tsx       NEW
/web/components/ui/DecisionCard.tsx         NEW
/web/components/ui/GradientBadge.tsx        NEW
/web/components/ui/Sidebar.tsx              NEW
/web/app/compliance/checks/[id]/page.tsx    refresh
/web/app/compliance/pending/page.tsx        refresh
/web/app/agents/sub-award/page.tsx          refresh
/web/app/agents/attendance-payment/[id]/page.tsx refresh
/web/app/verify/[id]/page.tsx               refresh
/web/app/knowledge/page.tsx                 refresh
/web/app/compliance/checks/page.tsx         refresh
/tailwind.config.ts                         add electric-violet, sunrise tokens
```

## Definition of done

- [ ] All 8 new components built and storybook-style example pages exist
- [ ] Top 5 result pages adopt DecisionCard or Spotify-row pattern
- [ ] Every empty state offers sample data
- [ ] `⌘+K` opens command palette (works on all pages)
- [ ] Sidebar nav live behind auth flag
- [ ] No regression — Self-Check passes 22/22

## Out of scope

- Dark mode (defer until 3 pilots shipped)
- Mobile-first redesign (desktop-first for now, mobile responsive only)
- Animation library (Framer Motion etc) — CSS transitions are enough
- Logo redesign — DOCex wordmark stays

## Anti-patterns to avoid

- DON'T copy-paste shadcn examples verbatim. Customise the type weight,
  the spacing, the colour.
- DON'T add a hero illustration. We're not a marketing agency.
- DON'T use the word "AI" in the UI more than necessary. Show, don't tell.
- DON'T pin a side panel that the user can't dismiss. Always allow collapse.
