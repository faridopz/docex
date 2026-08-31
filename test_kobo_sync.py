"""
Tests for KoboCollect integration.

Run: python test_kobo_sync.py

Covers:
- Parsing KoboCollect JSON
- Syncing submissions to receipts
- Grant code tracking (EVA)
- Deduplication (kobo instance ID)
- Placeholder receipt creation for incomplete submissions
- Org isolation
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import kobo_sync
import store

_base = Path(tempfile.mkdtemp(prefix="docex_kobo_"))
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

ORG = "eva"
OTHER_ORG = "neem"

# ─── parse kobo json ────────────────────────────────────────────────────────

kobo_json_str = json.dumps({
    "id": 12345,
    "org_id": ORG,
    "submitted_by": "fieldworker@eva.org",
    "meta": {
        "instanceID": "uuid:5f3db8c1-9e2a-4f7a-bcde-1234567890ab",
        "timeend": "2026-08-29T14:30:00Z"
    },
    "receipt_amount": 5000.0,
    "receipt_vendor": "Supply Store Ltd",
    "receipt_date": "2026-08-25",
    "project_code": "P-EVA-001",
    "grant_code": "GR-USAID-2024",
    "expense_category": "training",
    "notes": "Training materials for field staff",
})

submission = kobo_sync.parse_kobo_json(kobo_json_str)
check("kobo id parsed", submission.id, 12345)
check("vendor parsed", submission.receipt_vendor, "Supply Store Ltd")
check("amount parsed", submission.receipt_amount, 5000.0)
check("grant code parsed", submission.grant_code, "GR-USAID-2024")
check("kobo instance ID parsed", submission.kobo_instance_id, "uuid:5f3db8c1-9e2a-4f7a-bcde-1234567890ab")

# ─── sync kobo submission (no image) ─────────────────────────────────────────

result = kobo_sync.sync_kobo_submission(ORG, submission)
check("sync succeeded", result.success, True)
check("receipt ID created", len(result.receipt_id) > 0, True)
check("status is VALIDATED or FLAGGED", result.status in ["validated", "flagged"], True)

receipt_id = result.receipt_id

# ─── grant code stored ──────────────────────────────────────────────────────

stored_grant = kobo_sync.get_grant_code(ORG, receipt_id)
check("grant code stored", stored_grant, "GR-USAID-2024")

# ─── list receipts by grant code ────────────────────────────────────────────

receipts_for_grant = kobo_sync.list_receipts_by_grant_code(ORG, "GR-USAID-2024")
check("receipt found for grant code", receipt_id in receipts_for_grant, True)

# ─── deduplication ──────────────────────────────────────────────────────────

# Verify kobo instance ID was stored (used by endpoint for deduplication)
kobo_id = submission.kobo_instance_id
if kobo_id:
    stored_receipt = kobo_sync.get_receipt_by_kobo_instance_id(ORG, kobo_id)
    check("kobo instance stored for deduplication", stored_receipt == receipt_id, True)

# ─── incomplete submission (minimal data) ───────────────────────────────────

minimal_json = json.dumps({
    "id": 12346,
    "org_id": ORG,
    "submitted_by": "fieldworker2@eva.org",
    "meta": {
        "instanceID": "uuid:6g4ec9d2-0f3b-5g8b-cdef-2345678901bc",
        "timeend": "2026-08-29T15:00:00Z"
    },
    "receipt_amount": None,  # missing amount
    "receipt_vendor": "",    # missing vendor
    "receipt_date": None,    # missing date
    "project_code": "P-EVA-002",
})

minimal_submission = kobo_sync.parse_kobo_json(minimal_json)
result3 = kobo_sync.sync_kobo_submission(ORG, minimal_submission)
check("incomplete submission logged", result3.success, True)
check("incomplete submission flagged", result3.status, "flagged")
check("missing vendor flagged", any(f["type"] == "missing_vendor" for f in result3.flags), True)
check("missing date flagged", any(f["type"] == "missing_date" for f in result3.flags), True)

# ─── with grant code ────────────────────────────────────────────────────────

another_json = json.dumps({
    "id": 12347,
    "org_id": ORG,
    "submitted_by": "fieldworker3@eva.org",
    "meta": {
        "instanceID": "uuid:7h5fd0e3-1g4c-6h9c-defg-3456789012cd",
        "timeend": "2026-08-29T16:00:00Z"
    },
    "receipt_amount": 2500.0,
    "receipt_vendor": "Vendor B",
    "receipt_date": "2026-08-26",
    "project_code": "P-EVA-003",
    "grant_code": "GR-GRANT-PARTNER-2024",
})

another_submission = kobo_sync.parse_kobo_json(another_json)
result4 = kobo_sync.sync_kobo_submission(ORG, another_submission)
check("second receipt logged", result4.success, True)
check("second receipt grant code", result4.grant_code, "GR-GRANT-PARTNER-2024")

# ─── list receipts by grant code (second grant) ─────────────────────────────

receipts_for_grant2 = kobo_sync.list_receipts_by_grant_code(ORG, "GR-GRANT-PARTNER-2024")
check("second receipt found for new grant", result4.receipt_id in receipts_for_grant2, True)

# ─── org isolation ──────────────────────────────────────────────────────────

other_org_json = json.dumps({
    "id": 12348,
    "org_id": OTHER_ORG,
    "submitted_by": "fieldworker@neem.org",
    "meta": {
        "instanceID": "uuid:8i6ge1f4-2h5d-7i0d-efgh-4567890123de",
        "timeend": "2026-08-29T17:00:00Z"
    },
    "receipt_amount": 1000.0,
    "receipt_vendor": "NEEM Supplier",
    "receipt_date": "2026-08-27",
    "project_code": "NEEM-001",
})

other_submission = kobo_sync.parse_kobo_json(other_org_json)
result5 = kobo_sync.sync_kobo_submission(OTHER_ORG, other_submission)
check("other org receipt logged", result5.success, True)

# Check isolation
eva_grants = kobo_sync.list_receipts_by_grant_code(ORG, "GR-USAID-2024")
check("EVA receipts not in NEEM", result5.receipt_id in eva_grants, False)

# ─── placeholder receipt (no image data) ────────────────────────────────────

placeholder_bytes = kobo_sync._kobo_placeholder_receipt(submission)
check("placeholder is bytes", isinstance(placeholder_bytes, bytes), True)
check("placeholder contains vendor", b"Supply Store Ltd" in placeholder_bytes, True)
check("placeholder contains grant code", b"GR-USAID-2024" in placeholder_bytes, True)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All KoboCollect sync tests passed.")
