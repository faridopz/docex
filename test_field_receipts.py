"""
Tests for field receipt validation and tracking.

Run: python test_field_receipts.py

Covers:
- Receipt upload + OCR extraction
- Policy validation (amounts, vendors, categories, duplicates)
- Data quality gates (missing vendor/date)
- Flag resolution (approve/reject)
- Org isolation
- Real-time flagging
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import field_receipts
import store

_base = Path(tempfile.mkdtemp(prefix="docex_receipts_"))
store.set_store(store.JsonFileStore(_base / "data"))

_fail = 0


def check(name, got, want):
    global _fail
    ok = abs(got - want) < 0.01 if isinstance(got, (int, float)) and isinstance(want, (int, float)) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def expect_err(name, fn):
    global _fail
    try:
        fn()
        print(f"FAIL  {name}: expected an error, none raised")
        _fail += 1
    except Exception:
        print(f"PASS  {name}: raised as expected")


# ─── setup ──────────────────────────────────────────────────────────────────

ORG = "neem"
OTHER_ORG = "ta-connect"

# Set a basic policy for NEEM: max 50k per receipt, no flagged vendors
field_receipts.set_policy(ORG, field_receipts.ReceiptPolicy(
    org_id=ORG,
    rules=[
        field_receipts.SpendPolicyRule(
            code="MAX_RECEIPT",
            name="Max single receipt",
            rule_type="max_amount",
            max_amount=50_000,
        ),
        field_receipts.SpendPolicyRule(
            code="BANNED_VENDORS",
            name="Unauthorized vendors",
            rule_type="forbidden_vendor",
            forbidden_vendors=["FakeCorp", "BlackMarket Inc"],
        ),
        field_receipts.SpendPolicyRule(
            code="ALLOWED_CATS",
            name="Allowed categories",
            rule_type="category",
            allowed_categories=["training", "supplies", "travel"],
        ),
    ],
    allow_missing_vendor=False,
    allow_missing_date=False,
    duplicate_window_days=7,
))

# ─── upload & extraction ────────────────────────────────────────────────────

# Fake receipt PDF bytes (just text, not a real PDF)
fake_receipt_bytes = b"""VENDOR: Quick Supplies Co
DATE: 2026-08-15
AMOUNT: 5000
ITEMS:
- Training materials 3000
- Office supplies 2000
TOTAL: 5000"""

receipt = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=fake_receipt_bytes,
    filename="receipt_aug15.pdf",
    amount_submitted=5000.0,
    project_code="P-101",
    category="training",
)

check("receipt uploaded", receipt.id.startswith("rcp"), True)
check("status is validated (no issues)", receipt.status, field_receipts.ReceiptStatus.VALIDATED)
check("vendor extracted", "Quick" in receipt.extracted.vendor_name, True)
check("amount submitted", receipt.amount_submitted, 5000.0)
check("project code stored", receipt.project_code, "P-101")
check("no flags on clean receipt", len(receipt.flags), 0)

# ─── data quality gates: missing vendor ──────────────────────────────────────

bad_receipt_1 = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"DATE: 2026-08-16\nAMOUNT: 1000",  # no vendor, but has date
    filename="no_vendor.pdf",
    amount_submitted=1000.0,
    project_code="P-101",
    category="supplies",
)

check("missing vendor flagged as error", bad_receipt_1.status, field_receipts.ReceiptStatus.FLAGGED)
check("missing vendor error present", any(f.type == field_receipts.ReceiptFlagType.MISSING_VENDOR for f in bad_receipt_1.flags), True)

# ─── data quality gates: missing date ────────────────────────────────────────

bad_receipt_2 = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: Supplier X\nAMOUNT: 2000\nRECEIPT_NO: 123",  # no DATE field
    filename="no_date.pdf",
    amount_submitted=2000.0,
    project_code="P-101",
    category="training",
)

check("missing date flagged as error", bad_receipt_2.status, field_receipts.ReceiptStatus.FLAGGED)
check("missing date error present", any(f.type == field_receipts.ReceiptFlagType.MISSING_DATE for f in bad_receipt_2.flags), True)

# ─── policy: max amount ──────────────────────────────────────────────────────

over_budget_receipt = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: BigStore\nDATE: 2026-08-20\nAMOUNT: 100000\nINVOICE: INV-001",
    filename="expensive.pdf",
    amount_submitted=100_000.0,
    project_code="P-101",
    category="supplies",
)

check("over budget flagged", over_budget_receipt.status, field_receipts.ReceiptStatus.FLAGGED)
check("policy violation flag present", any(f.type == field_receipts.ReceiptFlagType.POLICY_VIOLATION for f in over_budget_receipt.flags), True)

# ─── policy: forbidden vendor ────────────────────────────────────────────────

banned_vendor_receipt = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: FakeCorp\nDATE: 2026-08-20\nAMOUNT: 1000\nINVOICE: INV-002",
    filename="bad_vendor.pdf",
    amount_submitted=1000.0,
    project_code="P-101",
    category="training",
)

check("banned vendor flagged", banned_vendor_receipt.status, field_receipts.ReceiptStatus.FLAGGED)
check("unauthorized vendor flag present", any(f.type == field_receipts.ReceiptFlagType.UNAUTHORIZED_VENDOR for f in banned_vendor_receipt.flags), True)

# ─── policy: unsupported category ───────────────────────────────────────────

bad_category_receipt = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: Store\nDATE: 2026-08-20\nAMOUNT: 500\nINVOICE: INV-003",
    filename="bad_cat.pdf",
    amount_submitted=500.0,
    project_code="P-101",
    category="entertainment",  # not in allowed list
)

check("unsupported category flagged", bad_category_receipt.status, field_receipts.ReceiptStatus.FLAGGED)
check("unsupported category flag present", any(f.type == field_receipts.ReceiptFlagType.UNSUPPORTED_CATEGORY for f in bad_category_receipt.flags), True)

# ─── duplicate detection ────────────────────────────────────────────────────

dup_receipt_1 = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: Office Depot\nDATE: 2026-08-20\nAMOUNT: 3000\nINVOICE: INV-004",
    filename="dup1.pdf",
    amount_submitted=3000.0,
    project_code="P-101",
    category="supplies",
)

check("first duplicate receipt validated", dup_receipt_1.status, field_receipts.ReceiptStatus.VALIDATED)

# Upload again, same vendor + same amount
dup_receipt_2 = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: Office Depot\nDATE: 2026-08-20\nAMOUNT: 3000\nINVOICE: INV-005",
    filename="dup2.pdf",
    amount_submitted=3000.0,
    project_code="P-101",
    category="supplies",
)

check("second receipt flagged as duplicate", dup_receipt_2.status, field_receipts.ReceiptStatus.FLAGGED)
check("duplicate flag present", any(f.type == field_receipts.ReceiptFlagType.DUPLICATE_DETECTED for f in dup_receipt_2.flags), True)

# ─── amount mismatch ────────────────────────────────────────────────────────

mismatch_receipt = field_receipts.upload_receipt(
    org_id=ORG,
    uploaded_by="fieldworker@neem.org",
    file_content=b"VENDOR: Store\nDATE: 2026-08-20\nAMOUNT: 2500\nINVOICE: INV-006",  # OCR sees 2500
    filename="mismatch.pdf",
    amount_submitted=3000.0,  # but user said 3000
    project_code="P-101",
    category="supplies",
)

check("amount mismatch flagged as warning", mismatch_receipt.status, field_receipts.ReceiptStatus.FLAGGED)
check("amount mismatch flag present", any(f.type == field_receipts.ReceiptFlagType.AMOUNT_MISMATCH for f in mismatch_receipt.flags), True)

# ─── flag resolution: approve ────────────────────────────────────────────────

approved_receipt = field_receipts.resolve_flags(
    org_id=ORG,
    receipt_id=mismatch_receipt.id,
    decision="approved",
    reviewed_by="finance@neem.org",
    notes="Verified amount with fieldworker, correct amount is 3000.",
)

check("approved receipt status", approved_receipt.status, field_receipts.ReceiptStatus.APPROVED)
check("reviewed_by set", approved_receipt.reviewed_by, "finance@neem.org")
check("review_decision set", approved_receipt.review_decision, "approved")

# ─── flag resolution: reject ────────────────────────────────────────────────

rejected_receipt = field_receipts.resolve_flags(
    org_id=ORG,
    receipt_id=banned_vendor_receipt.id,
    decision="rejected",
    reviewed_by="finance@neem.org",
    notes="Vendor is not approved.",
)

check("rejected receipt status", rejected_receipt.status, field_receipts.ReceiptStatus.REJECTED)
check("rejected review_decision", rejected_receipt.review_decision, "rejected")

# ─── update flagged receipt ──────────────────────────────────────────────────

# Fieldworker corrects the bad_receipt_1 (missing vendor)
receipt_updated = field_receipts.get_receipt(ORG, bad_receipt_1.id)
receipt_updated.extracted.vendor_name = "Corrected Vendor Name"
receipt_updated = field_receipts.validate_receipt(ORG, receipt_updated)
store.get_store().put(ORG, field_receipts._RECEIPTS, receipt_updated.id, receipt_updated.model_dump())

check("corrected receipt validated after fix", receipt_updated.status, field_receipts.ReceiptStatus.VALIDATED)
check("no flags after correction", len(receipt_updated.flags), 0)

# ─── list receipts ──────────────────────────────────────────────────────────

all_receipts = field_receipts.list_receipts(ORG)
check("multiple receipts listed", len(all_receipts) > 5, True)

validated_only = field_receipts.list_receipts(ORG, status=field_receipts.ReceiptStatus.VALIDATED)
check("filter by validated status works", len(validated_only) > 0, True)

p101_receipts = field_receipts.list_receipts(ORG, project_code="P-101")
check("filter by project code works", len(p101_receipts) > 0, True)

# ─── org isolation ──────────────────────────────────────────────────────────

other_receipt = field_receipts.upload_receipt(
    org_id=OTHER_ORG,
    uploaded_by="user@ta-connect.org",
    file_content=b"VENDOR: Shop\nDATE: 2026-08-20\nAMOUNT: 1000\nINVOICE: INV-007",
    filename="other.pdf",
    amount_submitted=1000.0,
    project_code="APP-1",
    category="training",
)

neem_receipts = field_receipts.list_receipts(ORG)
ta_receipts = field_receipts.list_receipts(OTHER_ORG)

check("NEEM receipts don't include TA Connect", other_receipt.id in [r.id for r in neem_receipts], False)
check("TA Connect receipts isolated", len(ta_receipts), 1)
check("OTHER_ORG can retrieve their own receipt", field_receipts.get_receipt(OTHER_ORG, other_receipt.id) is not None, True)

# ─── error handling ──────────────────────────────────────────────────────────

expect_err("cannot resolve non-flagged receipt", lambda: field_receipts.resolve_flags(ORG, receipt.id, "approved"))

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All field receipt checks passed.")
