# KoboCollect Integration for DOCex Field Receipts

## Overview

DOCex now integrates with **KoboCollect**, the offline-first data collection platform used by UNICEF, Red Cross, WHO, and thousands of NGOs. Fieldworkers in low/no-signal areas can now:

1. Capture receipts offline (photos, amounts, vendor names, dates, project codes)
2. Sync instantly when signal is available
3. Have receipts logged immediately in DOCex (no lag, simple + scalable)
4. Complete incomplete data in the UI (expected behavior)
5. Enable compliance/finance to review and approve

## Architecture

### Field Worker → KoboCollect → DOCex

```
[Fieldworker in field]
        ↓
[KoboCollect mobile app - offline capable]
  • Captures photo of receipt
  • Enters amount, vendor, date, project code, grant code (EVA)
  • All data stored locally on device
        ↓
[WiFi/cellular available]
  • KoboCollect syncs to KoboCollect server
  • Webhook notifies DOCex backend
        ↓
[DOCex receipt logging]
  • Receives KoboCollect JSON payload
  • Extracts data + image reference
  • Logs receipt immediately (in-db, durable)
  • Validates against policy
  • Returns receipt ID + flags
        ↓
[Finance/fieldworker in DOCex UI]
  • Sees receipt with status: VALIDATED or FLAGGED
  • If flagged (missing vendor, date, etc.):
    - Can correct data directly in UI
    - Re-validation runs
  • Reviews, approves, or rejects
  • Feeds into payment voucher workflow
```

## KoboCollect Form Design

Minimal form for receipt capture:

```json
{
  "type": "text",
  "name": "receipt_vendor",
  "label": "Vendor/Merchant name",
  "required": false
}
{
  "type": "date",
  "name": "receipt_date",
  "label": "Receipt date",
  "required": false
}
{
  "type": "decimal",
  "name": "receipt_amount",
  "label": "Amount spent",
  "required": false
}
{
  "type": "text",
  "name": "project_code",
  "label": "Project code (e.g., P-EVA-001)",
  "required": true
}
{
  "type": "select_one",
  "name": "expense_category",
  "label": "Category",
  "choices": ["training", "supplies", "travel", "transport", "accommodation", "meals"],
  "required": false
}
{
  "type": "text",
  "name": "grant_code",
  "label": "Grant code (for repayment tracking)",
  "required": false
}
{
  "type": "image",
  "name": "receipt_image",
  "label": "Receipt photo",
  "required": false
}
{
  "type": "note",
  "name": "notes",
  "label": "Any additional notes",
  "required": false
}
```

## API Endpoint

### POST /field-receipts/from-kobo

Accept KoboCollect submissions and log them as receipts.

**Request:**

```bash
curl -X POST https://api.docex.app/field-receipts/from-kobo \
  -F "submission_json={...}" \
  -F "image_file=@receipt.jpg" \
  -F "api_key=optional_webhook_key"
```

**submission_json (required):**

```json
{
  "id": 12345,
  "org_id": "eva",
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
  "receipt_image": "uuid:12345678",
  "notes": "Training materials for field staff"
}
```

**Response:**

```json
{
  "success": true,
  "receipt_id": "rcp-a1b2c3d4",
  "status": "validated",
  "message": "Receipt logged successfully.",
  "flags": [],
  "grant_code": "GR-USAID-2024"
}
```

Or if data is incomplete:

```json
{
  "success": true,
  "receipt_id": "rcp-e5f6g7h8",
  "status": "flagged",
  "message": "Receipt logged: flagged. 2 issue(s) flagged.",
  "flags": [
    {
      "type": "missing_vendor",
      "severity": "error",
      "message": "Vendor name could not be extracted from receipt. Please review and correct."
    },
    {
      "type": "missing_date",
      "severity": "error",
      "message": "Receipt date could not be extracted. Please review and correct."
    }
  ],
  "grant_code": "GR-USAID-2024"
}
```

## KoboCollect Webhook Setup

1. **Create webhook in KoboCollect:**
   - Form settings → Webhooks
   - URL: `https://api.docex.app/field-receipts/from-kobo`
   - Event: "Form submission"

2. **Payload format:**
   - KoboCollect automatically sends form data as JSON
   - DOCex will parse it and extract receipt data

3. **Deduplication:**
   - KoboCollect's `meta.instanceID` is unique per submission
   - DOCex stores this to detect re-submissions (e.g., retry on network failure)
   - If same `instanceID` arrives twice, returns existing receipt ID

## Key Features

### Offline-First
- Fieldworkers capture receipts offline (no network needed)
- Data queued locally on mobile device
- Syncs automatically when signal available
- No lag, no lost data

### Immediate Logging
- Receipt logged to DOCex database within seconds of sync
- Durable storage (SQLite or Postgres)
- Audit trail from capture → sync → approval

### Incomplete Data Accepted
- Fieldworkers can submit receipts with missing vendor/date/amount
- System flags issues (not errors)
- Finance/fieldworker complete missing data in UI
- Expected behavior, not a failure mode

### Grant Code Tracking (EVA)
- Optional `grant_code` field on submission
- DOCex tracks which receipts come from which grants
- Enables:
  - Repayment reconciliation
  - Donor reporting (which receipts used which funds)
  - Budget availability checks before approval

### Policy Validation
- Receipts validated against org's spend policy
- Max amount per receipt
- Forbidden/required vendors
- Allowed expense categories
- Duplicate detection (same vendor + amount within 7 days)

### Org Isolation
- All receipt data scoped to submitting org
- EVA receipts never visible to TA Connect or NEEM
- Grant code indexes per org

## Integration with Payment Workflow

1. **Receipt logged via KoboCollect** → DRAFT or FLAGGED
2. **Finance reviews in DOCex UI** → corrects flags if needed → APPROVED
3. **Receipt feeds into voucher builder** → included in payment voucher
4. **Voucher routed to compliance/ED for approval** → PAID
5. **Bank platform records transaction** → reference linked to receipt

## Testing

Run the test suite:

```bash
python test_kobo_sync.py   # KoboCollect integration tests
python test_field_receipts.py  # Field receipt validation tests
```

## Known Limitations (Phase 1)

- **OCR accuracy:** Simple regex patterns for vendor/date extraction. Real PDFs with poor quality may need manual correction.
- **Image upload:** Image file is optional; receipts can be submitted as metadata-only and completed later.
- **Duplicate detection:** Keyed on `kobo_instance_id` to prevent re-submissions on network retry.
- **Async batch:** Not yet implemented; each submission processes immediately.

## Future Enhancements (Phase 2+)

- [ ] **Async batch processing** — queue submissions, process in batches for efficiency
- [ ] **Zoho CRM integration** — automatically create contacts/projects in Zoho from receipt data
- [ ] **Mobile app dashboard** — let fieldworkers see receipt status/flags in KoboCollect interface
- [ ] **OCR model upgrade** — switch to Claude Vision for accurate extraction of receipts
- [ ] **Multi-language support** — receipts in any language
- [ ] **Template per activity** — different forms for different activity types (training, procurement, etc.)

## Support

For issues or questions:
- Email: support@docex.app
- GitHub: github.com/faridabdurrahman/docex/issues
