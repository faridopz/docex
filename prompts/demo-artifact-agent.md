# Stream B4 — Demo Artifact Agent (Ephemeral Demo Sessions)

**Paste into a fresh Claude Code session in `/Users/faridabdurrahman/Desktop/docex`.**

---

Read: `/PLAN.md`, `/demo_fixtures/README.md`, this file.

## What this stream delivers

A scripted "demo mode" that:

1. Seeds a fresh demo workspace with anonymised but realistic data
   tailored to the prospect's vertical
2. Runs through 3 of the Co-Pilots end-to-end so the demo URL is
   pre-populated with results
3. Auto-deletes the demo workspace after 7 days (or on-demand)
4. Tracks which demo URLs have been viewed (so Farid knows engagement)

Farid uses this when he wants to send a prospect a link they can click
INSTEAD of doing a screen-share. "Here's DOCex running on your kind
of data — click around."

## Architecture

### 1. The Demo Session model

Add to `models.py`:

```python
class DemoSession(BaseModel):
    id: str                        # short unique slug, e.g. "neem-jun02"
    label: str                     # display name "Neem demo"
    prospect_org: str              # who it's for
    vertical: Literal["ngo-procurement", "ngo-attendance",
                       "ngo-subaward", "foundation-grants",
                       "procurement-vendor", "generic"]
    fixtures_seeded: list[str]     # which fixture packs got loaded
    expires_at: str                # ISO timestamp, default = created + 7d
    created_at: str
    last_viewed_at: Optional[str] = None
    view_count: int = 0
    notes: Optional[str] = None
```

Persisted to `demos/{id}.json`.

### 2. Seeding

`/scripts/seed_demo.py <id> <vertical>`:

- Creates a fresh user dir at `demo_users/{id}/`
- Copies the matching fixture pack from `/demo_fixtures/{vertical}/`
- Runs the relevant Co-Pilots end-to-end so results exist
- Returns a shareable URL: `https://docex.app/demo/{id}/login` (no
  credentials needed; demo session JWT auto-injected)

### 3. Demo login

`/web/app/demo/[id]/login/page.tsx`:

- Loads the DemoSession by ID
- Issues a short-lived JWT scoped to the demo user dir
- Redirects to the most interesting result page for that vertical
- Shows a small persistent banner: "You're in DOCex demo mode.
  This is sample data, expires {date}."

### 4. Auto-cleanup

`/scripts/wipe_expired_demos.py` runs daily:

- For each `demos/*.json` where `expires_at < now`:
  - Delete `demo_users/{id}/`
  - Delete the JSON file
  - Email Farid the wipe summary

### 5. Engagement tracking

Every page load while in demo mode hits `/api/demo/track` which
increments `view_count` and updates `last_viewed_at`. Farid can
check engagement in `/admin/demos`.

## Vertical fixture packs needed

Build one of each under `/demo_fixtures/{vertical}/`:

| Vertical             | Contents                                                  |
| -------------------- | --------------------------------------------------------- |
| ngo-procurement      | Procurement policy PDF (10 pages, fake) + 3 vouchers      |
| ngo-attendance       | Attendance log Excel + payment list + per-diem rate card  |
| ngo-subaward         | 10 applicant orgs, each with 5 docs                       |
| foundation-grants    | Grant policy + 5 grantee reports for review               |
| procurement-vendor   | Supplier evaluation rubric + 5 supplier proposals         |
| generic              | Lightweight: 1 policy, 1 voucher, 1 bank verify           |

(Generic + ngo-procurement ship in this session; rest get built as
needed.)

## Files

```
/models.py                                add DemoSession
/api/demo_routes.py                       NEW (login, track, list)
/scripts/seed_demo.py                     NEW
/scripts/wipe_expired_demos.py            NEW
/web/app/demo/[id]/login/page.tsx         NEW
/web/components/DemoBanner.tsx            NEW
/web/app/admin/demos/page.tsx             NEW
```

## Definition of done

- [ ] `python scripts/seed_demo.py neem-jun02 ngo-procurement` works
      end-to-end and returns a URL
- [ ] Visiting the URL drops the viewer into a pre-populated DOCex
      with the demo banner
- [ ] Daily wipe job removes expired demos
- [ ] Admin demos page shows engagement per session

## Out of scope

- Recording demo videos (use Loom for that)
- Tracking specific clicks (just view count is enough)
- Persistent demo accounts (intentionally ephemeral)

## Anti-patterns

- DON'T use real customer data in demos. Use fixtures only.
- DON'T let demo users hit prod Paystack — Bank Verify in demo mode
  uses the sandbox/mock mode.
- DON'T leave demos forever. The 7-day auto-wipe is non-negotiable.
