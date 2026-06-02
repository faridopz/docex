# Demo Fixtures

Realistic-but-fake data used for demos, onboarding sample data, and
test runs. Every fixture is clearly labelled in-content as a sample
(e.g. "ACME Demo Org Ltd", "[SAMPLE]" in headers). Do NOT use real
customer data here.

## Packs

| Pack                  | Purpose                                       | Files                       |
| --------------------- | --------------------------------------------- | --------------------------- |
| `generic/`            | Lightweight smoke pack — 1 of each            | policy.md, voucher.md, schedule.csv |
| `ngo-procurement/`    | Full procurement compliance scenario          | policy.md, 3 vouchers, rulebook.json |
| `ngo-attendance/`     | Attendance Payment Co-Pilot scenario          | attendance.csv, payments.xlsx, rate-card.json |

## Scripts

- `seed.py` — loads a fixture pack into the local DOCex instance
- `wipe.py` — clears all data marked as demo (anything under user
  dir prefixed `demo-`)

## Usage

```bash
# Seed the generic pack
python demo_fixtures/seed.py generic

# Seed a full procurement demo
python demo_fixtures/seed.py ngo-procurement

# Wipe everything demo
python demo_fixtures/wipe.py --confirm
```

## Naming convention for fake data

- Orgs: `Acme Demo Foundation`, `Beta Demo Trust`, `Sample NGO Ltd`
- People: `Recipient A`, `Recipient B`, `Officer Demo`
- Banks: `Demo Bank PLC`, `Sample Microfinance`
- Money: round numbers in NGN/USD with "DEMO" prefix where possible

Everything must be obviously fake on visual inspection so a demo
viewer can't mistake it for real customer data.
