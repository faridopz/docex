"""Tests for the org-scoped store + the monthly compliance / grants engine.
Run: python test_grants.py"""
from __future__ import annotations

import tempfile
from pathlib import Path

import grants
import store

# Point storage at a temp dir — never touch real data.
store.set_store(store.JsonFileStore(Path(tempfile.mkdtemp(prefix="docex_store_"))))

_fail = 0


def check(name, got, want):
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) and isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_err(name, fn, exc=store.StoreError):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except exc:
        print(f"PASS  {name}: raised as expected")


EVA = "eva"
NEEM = "neem"

# ── multi-org isolation: the whole reason org_id exists ──
ag_eva = grants.add_agreement(EVA, donor="USAID", project_code="P-101",
                              title="Youth Health", value=10_000_000, currency="NGN",
                              signed_date="2026-01-15")
ag_neem = grants.add_agreement(NEEM, donor="Gates", project_code="N-1",
                               title="Other org project", value=5_000_000)
check("EVA sees only its own agreement", [a.project_code for a in grants.list_agreements(EVA)], ["P-101"])
check("Neem sees only its own agreement", [a.project_code for a in grants.list_agreements(NEEM)], ["N-1"])
check("record stamped with owning org", grants.list_agreements(EVA)[0].org_id, EVA)
expect_err("org_id is mandatory", lambda: grants.list_agreements(""))
expect_err("path traversal rejected", lambda: grants.list_agreements("../etc"))

# ── build a realistic schedule for EVA ──
# Expected: 3m in Feb, 3m in Mar, 4m in Apr
grants.add_tranche(EVA, ag_eva.id, "2026-02-01", 3_000_000, label="Q1")
grants.add_tranche(EVA, ag_eva.id, "2026-03-01", 3_000_000, label="Q2")
grants.add_tranche(EVA, ag_eva.id, "2026-04-01", 4_000_000, label="Q3")
# Requested
grants.record_request(EVA, ag_eva.id, "2026-02", 3_000_000, submitted_date="2026-01-20")
grants.record_request(EVA, ag_eva.id, "2026-03", 3_000_000, submitted_date="2026-02-20")
# Actually received: Feb in full, Mar short by 500k, Apr nothing yet
grants.record_inflow(EVA, ag_eva.id, "2026-02-05", 3_000_000, bank_ref="TRF-001",
                     allocated_project_code="P-101")
grants.record_inflow(EVA, ag_eva.id, "2026-03-07", 2_500_000, bank_ref="TRF-002",
                     allocated_project_code="P-101")

rows = grants.monthly_matrix(EVA)
by_period = {r.period: r for r in rows}

check("three active periods", sorted(by_period.keys()), ["2026-02", "2026-03", "2026-04"])
check("Feb expected", by_period["2026-02"].expected, 3_000_000)
check("Feb requested", by_period["2026-02"].requested, 3_000_000)
check("Feb received", by_period["2026-02"].received, 3_000_000)
check("Feb variance zero", by_period["2026-02"].variance, 0)
check("Feb 100% received", by_period["2026-02"].pct_received, 100.0)

check("Mar received short", by_period["2026-03"].received, 2_500_000)
check("Mar variance is the shortfall", by_period["2026-03"].variance, -500_000)
check("Mar cumulative shortfall", by_period["2026-03"].cumulative_shortfall, 500_000)

check("Apr expected but nothing received", by_period["2026-04"].received, 0)
check("Apr cumulative expected", by_period["2026-04"].cumulative_expected, 10_000_000)
check("Apr cumulative received", by_period["2026-04"].cumulative_received, 5_500_000)
check("Apr cumulative shortfall", by_period["2026-04"].cumulative_shortfall, 4_500_000)

# ── window filter keeps cumulative columns truthful ──
windowed = grants.monthly_matrix(EVA, period_from="2026-04")
check("window returns one row", len(windowed), 1)
check("windowed row still knows the full shortfall to date",
      windowed[0].cumulative_shortfall, 4_500_000)

# ── flags: currency mismatch + wrong project coding ──
grants.record_inflow(EVA, ag_eva.id, "2026-05-02", 1_000, currency="USD",
                     allocated_project_code="P-999")
may = {r.period: r for r in grants.monthly_matrix(EVA)}["2026-05"]
check("foreign-currency receipt flagged",
      any("excluded from the total" in f for f in may.flags), True)
check("foreign receipt NOT folded into the NGN total", may.received, 0)
check("foreign receipt tracked separately", may.received_other_currency, 1_000)
check("miscoded inflow flagged", any("coded to" in f for f in may.flags), True)

# ── aging: oldest-first coverage ──
late = grants.aging(EVA, as_of="2026-04-15")
# Feb fully covered; Mar short 500k; Apr fully outstanding 4m.
check("two overdue tranches", len(late), 2)
check("oldest outstanding is Q2", late[0].tranche_label, "Q2")
check("Q2 outstanding amount", late[0].outstanding, 500_000)
check("Q3 fully outstanding", late[1].outstanding, 4_000_000)
check("days late computed", late[1].days_late, 14)

# ── portfolio summary ──
summary = grants.portfolio_summary(EVA, as_of="2026-04-15")
check("summary counts agreements", summary["agreements"], 1)
check("summary overdue total", summary["overdue_total"], 4_500_000)
check("NGN totals present", summary["by_currency"]["NGN"]["received"], 5_500_000)

# ── other org still isolated after all that activity ──
check("Neem matrix unaffected", grants.monthly_matrix(NEEM), [])

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All grants + store checks passed.")
