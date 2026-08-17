"""Deterministic checks for per_diem.py. Run: python test_per_diem.py"""
from __future__ import annotations

from models import ReceiptItem
from per_diem import (
    DayCoverage,
    PerDiemComponents,
    PerDiemPolicy,
    build_participant_payable,
    compute_per_diem,
    uniform_days,
)

_fail = 0


def check(name: str, got, want) -> None:
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


# ── TA Connect rule: food covered every day => pay 75% of the daily per-diem ──
policy = PerDiemPolicy(rate_per_day=20_000)  # default split lodging .5 / meals .25 / incid .25
r = compute_per_diem(policy, uniform_days(3, covered=["meals"]))
check("3 days, food covered, full", r.full_entitlement, 60_000)
check("3 days, food covered, deduction", r.coverage_deduction, 15_000)   # 3 * 20k * .25
check("3 days, food covered, entitlement", r.entitlement, 45_000)        # the 75% rule
check("per-day payable is 75%", r.day_lines[0].payable, 15_000)

# ── No coverage => full rate ──
r2 = compute_per_diem(policy, uniform_days(3))
check("3 days, nothing covered", r2.entitlement, 60_000)

# ── Food + lodging covered => only incidentals (25%) ──
r3 = compute_per_diem(policy, uniform_days(2, covered=["meals", "lodging"]))
check("2 days, food+lodging covered", r3.entitlement, 10_000)            # 2 * 20k * .25

# ── Mixed days: day 1 full, day 2 food covered, day 3 all covered ──
mixed = [
    DayCoverage(label="Day 1", covered=[]),
    DayCoverage(label="Day 2", covered=["meals"]),
    DayCoverage(label="Day 3", covered=["meals", "lodging", "incidentals"]),
]
r4 = compute_per_diem(policy, mixed)
check("mixed days entitlement", r4.entitlement, 20_000 + 15_000 + 0)

# ── Weights that don't sum to 1.0 are flagged ──
bad = PerDiemPolicy(rate_per_day=10_000,
                    components=PerDiemComponents(lodging=0.6, meals=0.3, incidentals=0.3))
r5 = compute_per_diem(bad, uniform_days(1))
check("bad weights flagged", any(f.rule_id == "PD-WEIGHTS" for f in r5.flags), True)

# ── Combined payable: per-diem + transport/printing receipts ──
receipts = [
    ReceiptItem(filename="taxi1.jpg", amount=5_000, category="transport"),
    ReceiptItem(filename="taxi2.jpg", amount=3_000, category="transport"),
    ReceiptItem(filename="printing.jpg", amount=2_000, category="other"),
    ReceiptItem(filename="hotel.jpg", amount=40_000, category="lodging"),   # NOT reimbursable (org paid)
    ReceiptItem(filename="blurry.jpg", amount=None, category="transport"),  # unreadable
]
p = build_participant_payable(
    "Farid", policy, uniform_days(3, covered=["meals"]), receipts, event_name="Q3 Workshop")
check("reimbursable total (transport+other, readable)", p.reimbursable_total, 10_000)
check("reimbursable count", p.reimbursable_count, 3)
check("unreadable flagged", p.unreadable_receipt_count, 1)
check("total payable = per-diem 45k + reimb 10k", p.total_payable, 55_000)

print()
print("SUMMARY:", p.summary)
print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All checks passed.")
