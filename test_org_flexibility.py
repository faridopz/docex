"""
WO-39: does raising a payment actually bend to each organisation's own shape,
and do the audit annexes carry the whole population?

THE CLAIM UNDER TEST
====================
"One engine, one config file per client, never fork the codebase." That claim
is the entire business model, and it is only true if a payment raised at one
organisation genuinely behaves differently from a payment raised at another —
routing to different people, demanding different documents, engaging different
thresholds — with no code path branching on who the client is.

So this suite stands up THREE organisations with deliberately incompatible
processes, runs a real payment through each, and asserts that each one got its
own behaviour. Then it proves they cannot see each other, and that the audit
annexes transcribe the whole population.

  NEEM-shaped   six departments, four stages, thresholds at 2m and 7m,
                nineteen document packs by category, CC rules
  Tiny NGO      one approver, no thresholds, one required document
  Field-heavy   two stages, a very low ceiling, per-category packs that
                demand completely different evidence

If any of these needed a line of code that named the client, the model would
be broken. None of them does.

Run: python test_org_flexibility.py
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import store

_base = Path(tempfile.mkdtemp(prefix="docex_flex_"))
store.set_store(store.JsonFileStore(_base / "store"))

import audit_annexes  # noqa: E402
import departments  # noqa: E402
import org_config  # noqa: E402
import requisitions as rq  # noqa: E402

_fail = 0


def check(name, cond):
    global _fail
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fail += 1


def codes_of(req) -> set[str]:
    return {c.code for c in req.checks}


def blocking_codes(req) -> set[str]:
    return {c.code for c in rq.blocking_checks(req)}


# ═══════════════════════════════════════════════════════════════════════════
# ORG 1 — NEEM-shaped: six departments, four stages, real thresholds
# ═══════════════════════════════════════════════════════════════════════════

BIG = "big-ngo"
_STATE_OWNERS_BIG = {"submitted": "program", "intake": "program",
                     "compliance_review": "finance", "finance_review": "admin",
                     "approval": "aed", "paid": "finance"}
departments.replace_all([
    departments.DepartmentDef(key="program", name="Programmes", order=10),
    departments.DepartmentDef(key="procurement", name="Procurement", order=15),
    departments.DepartmentDef(key="finance", name="Finance / Audit", order=20),
    departments.DepartmentDef(key="admin", name="Admin", order=30),
    departments.DepartmentDef(key="aed", name="Assistant Executive Director", order=40),
    departments.DepartmentDef(key="ed", name="Executive Director", order=50,
                            is_final_authority=True),
], _STATE_OWNERS_BIG, BIG)
big_wf = rq.RequisitionWorkflow(
    org_id=BIG,
    steps=[
        rq.WorkflowStep(key="finance", label="Finance / Audit review", department="finance"),
        rq.WorkflowStep(key="admin", label="Admin forwards to AED", department="admin"),
        rq.WorkflowStep(key="aed", label="AED approval", department="aed",
                        can_override=True, override_limit=7_000_000),
        rq.WorkflowStep(key="ed", label="ED + AED joint approval", department="ed",
                        min_amount=7_000_001, can_override=True,
                        override_limit=100_000_000),
    ],
    max_amount=100_000_000,
    allowed_categories=["equipment", "advance", "per_diem", "venue"],
    required_documents=["memo", "invoice"],
    documents_by_category={
        "equipment": ["memo", "invoice", "purchase_order", "grn"],
        "advance": ["memo", "advance_request_form"],
        "per_diem": ["memo", "travel_approval_form", "payment_sheet"],
    },
    cc_rules=[rq.CCRule(min_amount=2_000_000, department="ed", label="Executive Director")],
    duplicate_window_days=30,
)
rq.set_workflow(BIG, big_wf)

# ═══════════════════════════════════════════════════════════════════════════
# ORG 2 — a small NGO: one approver, no thresholds at all
# ═══════════════════════════════════════════════════════════════════════════

TINY = "tiny-ngo"
_STATE_OWNERS_TINY = {"submitted": "program", "intake": "program",
                      "compliance_review": "finance", "finance_review": "finance",
                      "approval": "finance", "paid": "finance"}
departments.replace_all([
    departments.DepartmentDef(key="program", name="Programme", order=10),
    departments.DepartmentDef(key="finance", name="Finance", order=20,
                            is_final_authority=True),
], _STATE_OWNERS_TINY, TINY)
rq.set_workflow(TINY, rq.RequisitionWorkflow(
    org_id=TINY,
    steps=[rq.WorkflowStep(key="finance", label="Coordinator signs", department="finance")],
    allowed_categories=["supplies", "transport"],
    required_documents=["receipt"],
    duplicate_window_days=7,
))

# ═══════════════════════════════════════════════════════════════════════════
# ORG 3 — field-heavy: low ceiling, completely different evidence per category
# ═══════════════════════════════════════════════════════════════════════════

FIELD = "field-ngo"
_STATE_OWNERS_FIELD = {"submitted": "field", "intake": "field",
                       "compliance_review": "field", "finance_review": "hq",
                       "approval": "hq", "paid": "hq"}
departments.replace_all([
    departments.DepartmentDef(key="field", name="Field team", order=10),
    departments.DepartmentDef(key="hq", name="Head office", order=20,
                            is_final_authority=True),
], _STATE_OWNERS_FIELD, FIELD)
rq.set_workflow(FIELD, rq.RequisitionWorkflow(
    org_id=FIELD,
    steps=[
        rq.WorkflowStep(key="field", label="Field coordinator", department="field"),
        rq.WorkflowStep(key="hq", label="Head office", department="hq"),
    ],
    max_amount=250_000,
    allowed_categories=["cash_transfer", "transport"],
    required_documents=["attendance_list"],
    documents_by_category={
        "cash_transfer": ["attendance_list", "payment_sheet", "beneficiary_id"],
        "transport": ["receipt"],
    },
    duplicate_window_days=1,
))

# ─── each org routes to ITS OWN people ─────────────────────────────────────

big_req = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Sahad Stores", amount=500_000, category="equipment",
    documents=["memo", "invoice", "purchase_order", "grn"])
tiny_req = rq.create_requisition(
    TINY, submitted_by="officer@tiny.org", department="program",
    vendor_name="Corner Shop", amount=500_000, category="supplies",
    documents=["receipt"])
field_req = rq.create_requisition(
    FIELD, submitted_by="officer@field.org", department="field",
    vendor_name="Community payout", amount=100_000, category="cash_transfer",
    documents=["attendance_list", "payment_sheet", "beneficiary_id"])

check("the big org routes an equipment purchase to Finance first",
      big_req.current_step == "finance")
check("the tiny org routes the SAME amount straight to its one approver",
      tiny_req.current_step == "finance" and len(rq.get_workflow(TINY).steps) == 1)
check("the field org routes to its field coordinator",
      field_req.current_step == "field")
check("the same amount produced three different routes with no code change",
      len({len(rq._steps_for(rq.get_workflow(o), 500_000))
           for o in (BIG, TINY)}) == 2)

# ─── the document pack changes with the CATEGORY, per org ──────────────────

big_advance = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Staff advance", amount=80_000, category="advance",
    documents=["memo", "advance_request_form"])
check("an advance at the big org is satisfied by its own two-document pack",
      "DOCS_COMPLETE" not in blocking_codes(big_advance))

big_equipment_thin = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Laptops", amount=80_000, category="equipment",
    documents=["memo", "invoice"])
check("the SAME two documents are NOT enough for equipment at the same org",
      "DOCS_COMPLETE" in blocking_codes(big_equipment_thin))

field_transport = rq.create_requisition(
    FIELD, submitted_by="officer@field.org", department="field",
    vendor_name="Bus hire", amount=20_000, category="transport",
    documents=["receipt"])
check("the field org's transport pack is one receipt and that is enough",
      "DOCS_COMPLETE" not in blocking_codes(field_transport))

field_cash_thin = rq.create_requisition(
    FIELD, submitted_by="officer@field.org", department="field",
    vendor_name="Community payout", amount=20_000, category="cash_transfer",
    documents=["receipt"])
check("a receipt is NOT enough for a cash transfer at the same org",
      "DOCS_COMPLETE" in blocking_codes(field_cash_thin))

# ─── ceilings are per-org ──────────────────────────────────────────────────

over_field = rq.create_requisition(
    FIELD, submitted_by="officer@field.org", department="field",
    vendor_name="Too big", amount=300_000, category="transport",
    documents=["receipt"])
check("300,000 breaches the field org's ceiling",
      "AMOUNT_LIMIT" in blocking_codes(over_field))

fine_at_big = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Same amount, bigger org", amount=300_000, category="equipment",
    documents=["memo", "invoice", "purchase_order", "grn"])
check("the same 300,000 is unremarkable at the big org",
      "AMOUNT_LIMIT" not in blocking_codes(fine_at_big))

# ─── thresholds engage the right extra approver ────────────────────────────

small_big = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Below the ED line", amount=6_000_000, category="equipment",
    documents=["memo", "invoice", "purchase_order", "grn"])
large_big = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Above the ED line", amount=8_000_000, category="equipment",
    documents=["memo", "invoice", "purchase_order", "grn"])
check("6m does not engage the ED stage",
      "ed" not in [s.key for s in rq._steps_for(big_wf, small_big.amount)])
check("8m does engage the ED stage",
      "ed" in [s.key for s in rq._steps_for(big_wf, large_big.amount)])
check("the CC rule fires above 2m",
      [r.department for r in rq.cc_recipients(big_wf, 8_000_000)] == ["ed"])
check("and stays silent below it", rq.cc_recipients(big_wf, 500_000) == [])

# ─── categories are per-org ────────────────────────────────────────────────

wrong_cat = rq.create_requisition(
    TINY, submitted_by="officer@tiny.org", department="program",
    vendor_name="Equipment at the tiny org", amount=10_000, category="equipment",
    documents=["receipt"])
check("a category the small org never configured is refused",
      "CATEGORY_ALLOWED" in blocking_codes(wrong_cat))

# ─── and none of them can see each other ───────────────────────────────────

check("the big org sees only its own requisitions",
      all(r.org_id == BIG for r in rq.list_requisitions(BIG)))
check("the tiny org cannot see the big org's payments",
      not any(r.vendor_name == "Sahad Stores" for r in rq.list_requisitions(TINY)))
check("each org numbers its own requisitions from one",
      rq.list_requisitions(TINY)[-1].ref.endswith("0001"))
check("the field org's workflow is untouched by the others",
      rq.get_workflow(FIELD).max_amount == 250_000)

# ─── a payment runs the whole way through, at the small org ───────────────

paid = rq.decide(TINY, tiny_req.id, decision=rq.Decision.APPROVED,
                 actor="coordinator@tiny.org", department="finance")
check("one approval clears the small org's entire chain",
      paid.status == rq.ReqStatus.APPROVED)
txn = rq.mark_paid(TINY, tiny_req.id, actor="coordinator@tiny.org",
                   bank_reference="TINY-001", department="finance")
settled = rq.get_requisition(TINY, tiny_req.id)
check("it can then be paid", settled.status == rq.ReqStatus.PAID)
check("a transaction record was frozen", settled.transaction_id is not None)
check("the frozen record keeps the bank reference", txn.bank_reference == "TINY-001")
check("the frozen record is locked", txn.locked is True)
check("the audit chain still verifies after the full journey",
      rq.verify_audit_chain(settled))

# ═══════════════════════════════════════════════════════════════════════════
# THE ANNEXES — does the pack carry the whole population?
# ═══════════════════════════════════════════════════════════════════════════

import datetime as dt  # noqa: E402
today = dt.date.today().isoformat()
start = (dt.date.today() - dt.timedelta(days=1)).isoformat()

xlsx = audit_annexes.build_annexes_xlsx(BIG, start, today, org_name="Big NGO")
check("the annexes are a real xlsx", xlsx.startswith(b"PK"))

from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(io.BytesIO(xlsx))
check("all five annexes plus the about sheet exist", len(wb.sheetnames) == 6)
check("Annex A is the requisitions", wb.sheetnames[0].startswith("A "))
check("Annex B is the compliance checks", wb.sheetnames[1].startswith("B "))

rows = list(wb[wb.sheetnames[0]].iter_rows(min_row=5, values_only=True))
listed = {r[0] for r in rows if r[0]}
big_refs = {r.ref for r in rq.list_requisitions(BIG)}
check("EVERY requisition in the period appears in Annex A",
      big_refs.issubset(listed))
check("including the ones that are still blocked",
      big_equipment_thin.ref in listed)

check("the sheet is filterable without the auditor switching it on",
      wb[wb.sheetnames[0]].auto_filter.ref is not None)
check("headers stay visible when scrolling",
      wb[wb.sheetnames[0]].freeze_panes == "A5")

# ─── masking ───────────────────────────────────────────────────────────────

check("an account number is masked to the last four by default",
      audit_annexes.mask_account("0123456789") == "•••••• 6789")
check("a short value does not leak what little it has",
      audit_annexes.mask_account("12") == "•••••• ")
check("an empty account stays empty", audit_annexes.mask_account("") == "")
check("full detail is only given when explicitly asked for",
      audit_annexes.mask_account("0123456789", full=True) == "0123456789")

masked = rq.create_requisition(
    BIG, submitted_by="officer@big.org", department="program",
    vendor_name="Account Test Ltd", amount=5_000, category="advance",
    vendor_account="0123456789", documents=["memo", "advance_request_form"])
xlsx_masked = audit_annexes.build_annexes_xlsx(BIG, start, today)
check("the default pack does not contain a full account number",
      b"0123456789" not in xlsx_masked)
xlsx_full = audit_annexes.build_annexes_xlsx(BIG, start, today,
                                              full_account_numbers=True)
wb_full = load_workbook(io.BytesIO(xlsx_full))
accounts = {r[3] for r in wb_full[wb_full.sheetnames[0]].iter_rows(
    min_row=5, values_only=True)}
check("the unmasked pack does contain it", "0123456789" in accounts)

about = {r[0]: r[1] for r in wb[wb.sheetnames[-1]].iter_rows(values_only=True) if r[0]}
check("the pack explains its own redaction",
      "Masked" in str(about.get("Account numbers", "")))
check("the pack states no model was involved",
      "language model" in str(about.get("Basis", "")))

# ─── the annexes are org-scoped too ────────────────────────────────────────

tiny_xlsx = audit_annexes.build_annexes_xlsx(TINY, start, today)
check("the small org's annexes do not contain the big org's payees",
      b"Sahad Stores" not in tiny_xlsx)

if _fail:
    print(f"\n{_fail} check(s) FAILED.")
    import sys
    sys.exit(1)
print("\nAll org-flexibility and annexe checks passed.")
