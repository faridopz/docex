"""
FastAPI routes for payment requisitions, approvals, and the audit view.

Endpoints:
  POST /requisitions                    — department raises a payment request
  GET  /requisitions                    — list (filter by status / step / grant)
  GET  /requisitions/pending            — "waiting on my department"
  GET  /requisitions/workflow           — the org's approval chain + spend policy
  PUT  /requisitions/workflow           — configure it (admin)
  GET  /requisitions/{id}               — full detail: checks, approvals, audit log
  POST /requisitions/{id}/decide        — approve / decline / return (+ override)
  POST /requisitions/{id}/resubmit      — submitter fixes a returned requisition
  POST /requisitions/{id}/pay           — record payment, freeze the transaction
  GET  /payments                        — completed payments
  GET  /payments/{id}                   — immutable transaction detail
  GET  /audit/summary                   — auditor's first screen

Every decision is attributed to the signed-in user: actor and department come
from the bearer token, never from the request body. Overrides require a written
reason and are authority-checked inside requisitions.py.

Route order matters — the literal paths /requisitions/pending and
/requisitions/workflow are declared BEFORE /requisitions/{req_id}, otherwise
FastAPI would match them as an id.
"""
from __future__ import annotations

import io
import json
import os
import uuid
from typing import Annotated, Literal, Optional

from fastapi import (
    APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel

import approval_tokens
import approval_webhook
import attachments
import auth
import audit_annexes
import audit_findings
import audit_report
import compliance
import fast_extract
import idempotency
import notifications
import org_config
import payee_import
import requisition_export
import requisitions as rq
import store
from models import PolicyRulebook
from notifications import looks_like_email
from .context import Ctx, request_context, require_role

router = APIRouter(tags=["requisitions"])

# Every field the frontend is allowed to set on a payee row. Built with
# **only these keys (never the raw parsed dict) so a client cannot smuggle
# an unexpected key into the Payee model — e.g. a future field added to the
# model for internal bookkeeping that should never be settable from a form.
_PAYEE_FIELDS = (
    "name", "account_number", "bank_name", "amount", "purpose",
    "tin", "phone_or_email", "payee_type",
)

# Every field the frontend is allowed to set on a budget-line row.
# `line_total` is deliberately absent — requisitions.py always recomputes it
# from quantity * frequency * unit_cost (DETERMINISTIC-FIRST), so a client
# value there is silently ignored rather than trusted.
_BUDGET_LINE_FIELDS = (
    "description", "unit", "budget_line", "quantity", "frequency", "unit_cost",
)


def _parse_payees(raw: str) -> list[rq.Payee]:
    """Decode the JSON array of payee rows the frontend posts for a
    multi-payee requisition. Empty/blank input means "not a batch" — the
    single-vendor fields apply instead — so it returns [] rather than
    raising, exactly like the comma-split helpers used for documents/receipts
    elsewhere in this file.

    A malformed payload (bad JSON, not a list, a row that is not an object)
    is a 400: this is data a human typed or a script generated, not something
    that should ever reach the policy engine silently reinterpreted as
    "no payees".
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"payees is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="payees must be a JSON array.")
    out: list[rq.Payee] = []
    for i, row in enumerate(parsed):
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail=f"payees[{i}] must be an object.")
        try:
            out.append(rq.Payee(**{k: row[k] for k in _PAYEE_FIELDS if k in row}))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"payees[{i}] is invalid: {exc}") from exc
    return out


def _parse_budget_lines(raw: str) -> list[rq.BudgetLine]:
    """Decode the JSON array of budget-line rows the frontend posts for the
    expense breakdown table (mirrors NEEM's memo item table). Same
    empty-means-none, malformed-is-a-400 treatment as _parse_payees above —
    this is data a human typed, so a bad payload should say so loudly rather
    than silently becoming "no breakdown"."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"budget_lines is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="budget_lines must be a JSON array.")
    out: list[rq.BudgetLine] = []
    for i, row in enumerate(parsed):
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail=f"budget_lines[{i}] must be an object.")
        try:
            out.append(rq.BudgetLine(**{k: row[k] for k in _BUDGET_LINE_FIELDS if k in row}))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"budget_lines[{i}] is invalid: {exc}") from exc
    return out


def _notify(ctx: Ctx, req: rq.Requisition, *, kind: str, department: str,
            title: str, body: str = "", to_user: Optional[str] = None) -> None:
    """Best-effort. The requisition or payment this fires after has already
    succeeded and been saved — a notification failing must never look like
    the underlying operation failed, so this swallows its own errors rather
    than raising past the caller.

    Mirrors the existing notify_transition() pattern used by vouchers and
    the legacy transaction flow: notifications are emitted from the route
    layer, right after the engine call that changed something, never from
    inside the engine itself.

    `to_user`, when given, additionally addresses this to one specific
    person (a named CC), independent of `department` — see
    notification_center.create().
    """
    try:
        import notification_center as nc
        # Department is allowed to be "" here — a pure named-person CC rule
        # (emails but no department) has nowhere sane to broadcast, and "" is
        # already this codebase's existing empty/none sentinel for a
        # department (see Ctx.department). It only means "not also broadcast
        # to a department queue" — to_user still delivers it to the named
        # person regardless.
        nc.create(req.ref, department, kind, title, body=body,
                  actor=ctx.user_id, org_id=ctx.org_id, to_user=to_user)
    except Exception:
        pass


def _notify_current_step(ctx: Ctx, req: rq.Requisition, wf: rq.RequisitionWorkflow) -> None:
    """Tell whichever department the requisition is now parked on that it's
    their turn. This did not exist for requisitions at all before — the
    in-app notification feed only ever fired for the older voucher/
    transaction flow, so nobody was actually told a requisition needed them
    unless they happened to check the list."""
    if not req.current_step:
        return
    step = next((s for s in wf.steps if s.key == req.current_step), None)
    if step is None or not step.department:
        return
    _notify(ctx, req, kind="assigned", department=step.department,
            title=f"{req.ref}: {step.label or step.key}",
            body=f"{req.vendor_name} — {req.amount:,.2f} {req.currency}.")


# ─── serialisers ────────────────────────────────────────────────────────────


def _check_out(c: rq.PolicyCheck) -> dict:
    return {
        "code": c.code,
        "name": c.name,
        "result": c.result.value,
        "policy_value": c.policy_value,
        "actual_value": c.actual_value,
        "message": c.message,
        "overridden": c.overridden,
        "override_by": c.override_by,
        "override_reason": c.override_reason,
        "override_authority": c.override_authority,
    }


def _approval_out(a: rq.Approval) -> dict:
    return {
        "step": a.step,
        "department": a.department,
        "actor": a.actor,
        "decision": a.decision.value,
        "notes": a.notes,
        "at": a.at,
        "overrides": a.overrides,
        # Proof that a signature exists, without publishing the full digest.
        "signature": (a.signature[:16] + "…") if a.signature else "",
    }


def _payee_out(p: rq.Payee) -> dict:
    return {
        "name": p.name,
        "account_number": p.account_number,
        "bank_name": p.bank_name,
        "amount": p.amount,
        "purpose": p.purpose,
        "tin": p.tin,
        "phone_or_email": p.phone_or_email,
        "payee_type": p.payee_type,
    }


def _budget_line_out(bl: rq.BudgetLine) -> dict:
    return {
        "description": bl.description,
        "unit": bl.unit,
        "budget_line": bl.budget_line,
        "quantity": bl.quantity,
        "frequency": bl.frequency,
        "unit_cost": bl.unit_cost,
        "line_total": bl.line_total,
    }


def _comment_out(c: rq.Comment) -> dict:
    return {"id": c.id, "author": c.author, "department": c.department,
            "text": c.text, "at": c.at}


def _attachment_out(a: rq.Attachment) -> dict:
    return {
        "id": a.id, "filename": a.filename, "content_type": a.content_type,
        "size": a.size, "uploaded_by": a.uploaded_by, "uploaded_at": a.uploaded_at,
        # storage_key deliberately excluded — it's an internal detail of
        # attachments.py, not something the frontend needs or should guess
        # at. Downloading goes through GET .../attachments/{id}, never a
        # direct storage_key.
    }


def _compliance_finding_out(f: rq.ComplianceFinding) -> dict:
    return {
        "rule_id": f.rule_id, "rule_description": f.rule_description,
        "verdict": f.verdict, "reasoning": f.reasoning,
        "policy_citation": f.policy_citation, "payment_evidence": f.payment_evidence,
        "applied_to_document": f.applied_to_document,
    }


def _compliance_out(c: rq.ComplianceSummary) -> dict:
    return {
        "rulebook_id": c.rulebook_id, "rulebook_name": c.rulebook_name,
        "overall_verdict": c.overall_verdict, "overall_summary": c.overall_summary,
        "results": [_compliance_finding_out(f) for f in c.results],
        "document_count": c.document_count,
        "checked_by": c.checked_by, "checked_at": c.checked_at,
    }


def _audit_out(e: rq.AuditEntry) -> dict:
    return {
        "seq": e.seq, "at": e.at, "actor": e.actor,
        "department": e.department, "event": e.event, "detail": e.detail,
    }


def _summary_out(r: rq.Requisition) -> dict:
    return {
        "id": r.id,
        "ref": r.ref,
        "vendor_name": r.vendor_name,
        "amount": r.amount,
        "currency": r.currency,
        "category": r.category,
        "project_code": r.project_code,
        "grant_code": r.grant_code,
        "department": r.department,
        "submitted_by": r.submitted_by,
        "submitted_at": r.submitted_at,
        "status": r.status.value,
        "current_step": r.current_step,
        "blocking_count": len(rq.blocking_checks(r)),
        "warning_count": len([c for c in r.checks if c.result == rq.CheckResult.WARNING]),
        "updated_at": r.updated_at,
    }


def _detail_out(r: rq.Requisition) -> dict:
    return {
        **_summary_out(r),
        "vendor_account": r.vendor_account,
        "vendor_bank_name": r.vendor_bank_name,
        "vendor_tin": r.vendor_tin,
        "vendor_phone_or_email": r.vendor_phone_or_email,
        "payment_type": r.payment_type,
        "budget_lines": [_budget_line_out(bl) for bl in r.budget_lines],
        "amount_in_words": rq.amount_in_words(r.amount, r.currency),
        "description": r.description,
        "receipt_ids": r.receipt_ids,
        "documents": r.documents,
        "payees": [_payee_out(p) for p in r.payees],
        "hold_reason": r.hold_reason,
        "held_by": r.held_by,
        "held_at": r.held_at,
        "transaction_id": r.transaction_id,
        "checks": [_check_out(c) for c in r.checks],
        "approvals": [_approval_out(a) for a in r.approvals],
        "comments": [_comment_out(c) for c in r.comments],
        "attachments": [_attachment_out(a) for a in r.attachments],
        "compliance": _compliance_out(r.compliance) if r.compliance else None,
        "audit_log": [_audit_out(e) for e in r.audit_log],
        "audit_chain_valid": rq.verify_audit_chain(r),
    }


def _txn_out(t: rq.TransactionRecord) -> dict:
    return {
        "id": t.id,
        "requisition_id": t.requisition_id,
        "requisition_ref": t.requisition_ref,
        "vendor_name": t.vendor_name,
        "vendor_account": t.vendor_account,
        "amount": t.amount,
        "currency": t.currency,
        "category": t.category,
        "project_code": t.project_code,
        "grant_code": t.grant_code,
        "bank_reference": t.bank_reference,
        "paid_by": t.paid_by,
        "paid_at": t.paid_at,
        "payees": [_payee_out(p) for p in t.payees],
        "exceptions_count": t.exceptions_count,
        "locked": t.locked,
        "checks": [_check_out(c) for c in t.checks],
        "approvals": [_approval_out(a) for a in t.approvals],
        "audit_log": [_audit_out(e) for e in t.audit_log],
    }


# ─── raise a requisition ────────────────────────────────────────────────────


@router.post("/requisitions")
async def create_requisition_endpoint(
    vendor_name: Annotated[str, Form(description="Who is being paid")],
    amount: Annotated[float, Form(description="Amount to pay")],
    category: Annotated[str, Form(description="Spend category")] = "",
    project_code: Annotated[str, Form(description="Project / cost centre")] = "",
    grant_code: Annotated[str, Form(description="Grant being charged")] = "",
    vendor_account: Annotated[str, Form(description="Vendor bank account")] = "",
    vendor_bank_name: Annotated[str, Form(description="Vendor's bank")] = "",
    vendor_tin: Annotated[str, Form(description="Vendor's Tax Identification Number")] = "",
    vendor_phone_or_email: Annotated[str, Form(description="Vendor phone or email")] = "",
    payment_type: Annotated[str, Form(
        description="full, advance, or balance — matches the org's own memo wording")] = "full",
    budget_lines: Annotated[str, Form(
        description="JSON array of expense-breakdown rows (description, unit, "
                    "budget_line, quantity, frequency, unit_cost). Totals are "
                    "always server-computed. Omit or send '[]' for none.")] = "",
    description: Annotated[str, Form(description="What this is for")] = "",
    receipt_ids: Annotated[str, Form(description="Comma-separated field receipt IDs")] = "",
    documents: Annotated[str, Form(description="Comma-separated document labels")] = "",
    payees: Annotated[str, Form(
        description="JSON array of payee rows for a multi-payee batch. Omit "
                    "or send '[]' for an ordinary single-vendor requisition.")] = "",
    currency: Annotated[str, Form()] = "NGN",
    submit: Annotated[bool, Form(
        description="False saves a draft instead of submitting for approval")] = True,
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    ctx: Ctx = Depends(request_context),
):
    """
    A department raises a payment requisition.

    Policy checks run immediately, so the submitter sees any failure or warning
    before an approver ever opens it.

    Pass `submit=false` to save a DRAFT — checks still run, so the person
    filling the form gets the same immediate feedback, but nothing enters
    anyone's approval queue and the amount is not treated as committed.

    Send an `Idempotency-Key` header and a retry after a dropped connection
    replays the original requisition instead of raising a duplicate.
    """
    payee_rows = _parse_payees(payees)
    budget_line_rows = _parse_budget_lines(budget_lines)
    try:
        with idempotency.guard(ctx.org_id, "requisition.create", idempotency_key) as slot:
            if slot.replayed:
                return slot.result

            try:
                req = rq.create_requisition(
                    ctx.org_id,
                    submitted_by=ctx.user_id,
                    department=ctx.department,
                    vendor_name=vendor_name,
                    amount=amount,
                    category=category,
                    project_code=project_code,
                    grant_code=grant_code.strip() or None,
                    vendor_account=vendor_account,
                    vendor_bank_name=vendor_bank_name,
                    vendor_tin=vendor_tin,
                    vendor_phone_or_email=vendor_phone_or_email,
                    payment_type=payment_type,
                    budget_lines=budget_line_rows or None,
                    description=description,
                    receipt_ids=[s.strip() for s in receipt_ids.split(",") if s.strip()],
                    documents=[s.strip() for s in documents.split(",") if s.strip()],
                    payees=payee_rows or None,
                    currency=currency,
                    submit=submit,
                )
            except rq.RequisitionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=422, detail=f"Could not raise requisition: {exc}"
                ) from exc

            wf = rq.get_workflow(ctx.org_id)
            _notify_current_step(ctx, req, wf)
            # CC fires once, here, at submission — not on every later step
            # change. NEEM's own process adds the AED/Director of Operations
            # to the copy list once, when a pack is forwarded; it does not
            # re-notify them at every intermediate review.
            for rule in rq.cc_recipients(wf, req.amount):
                cc_body = (f"{req.vendor_name} — {req.amount:,.2f} {req.currency}. "
                           f"{rule.label or rule.department or 'You'} "
                           f"{'is' if not rule.emails or rule.department else 'are'} copied "
                           f"because this is at or above {rule.min_amount:,.0f}.")
                # A department gets ONE broadcast notification — everyone in
                # it shares that department's feed, so firing one per person
                # would just duplicate it for anyone who happens to log in.
                if rule.department:
                    _notify(ctx, req, kind="cc", department=rule.department,
                            title=f"{req.ref}: copied on a new requisition", body=cc_body)
                # Each named individual gets their OWN notification, addressed
                # to them personally (to_user) — they see it regardless of
                # which department they're in, or whether they're in one at
                # all. Deliberately not deduplicated against the department
                # loop above: NEEM's own ask was "the AED, by name", which
                # this makes true even for someone outside the CC'd department.
                for email in rule.emails:
                    _notify(ctx, req, kind="cc", department=rule.department,
                            title=f"{req.ref}: copied on a new requisition", body=cc_body,
                            to_user=email.strip().lower())

            return slot.store(_detail_out(req))
    except idempotency.IdempotencyConflict as exc:
        # 409: the first attempt is still running. Retrying shortly is correct;
        # submitting again with a new key would create the duplicate.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─── list / pending ─────────────────────────────────────────────────────────


@router.get("/requisitions")
async def list_requisitions_endpoint(
    status: Optional[str] = Query(
        None, description="draft, submitted, in_review, approved, paid, declined, returned"),
    step: Optional[str] = Query(None, description="Workflow step key, e.g. compliance"),
    department: Optional[str] = None,
    grant_code: Optional[str] = None,
    ctx: Ctx = Depends(request_context),
):
    status_enum = None
    if status:
        try:
            status_enum = rq.ReqStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}") from None

    rows = rq.list_requisitions(
        ctx.org_id, status=status_enum, step=step,
        department=department, grant_code=grant_code,
    )
    return {"total": len(rows), "requisitions": [_summary_out(r) for r in rows]}


@router.post("/requisitions/payees/preview")
async def preview_payee_import_endpoint(
    file: Annotated[UploadFile, File(description="CSV, TSV or Excel payee schedule")],
    ctx: Ctx = Depends(request_context),
):
    """Read a payee schedule out of a spreadsheet and say what is in it.

    CREATES NOTHING. It parses, validates and returns rows plus per-row
    problems, so the person can see all eleven mistakes at once and fix the
    source file rather than discovering them one upload at a time.

    The rows then go through POST /requisitions exactly as typed ones do, so
    an imported batch gets the same deterministic policy checks, the same
    approval chain, the same compliance check and the same audit log. There
    is deliberately no bulk-create endpoint: a second way to create a payment
    is a second thing that drifts from the first, and this codebase has just
    spent a week removing one of those.

    Declared above /requisitions/{req_id} for the same reason
    /requisitions/pending is — a literal path after the id pattern would
    never match.
    """
    if not org_config.feature_enabled(ctx.org_id, "multi_payee_requisitions"):
        raise HTTPException(
            status_code=400,
            detail="This organisation has not enabled multi-payee requisitions "
                   "('multi_payee_requisitions' feature flag).",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="That file is empty.")

    try:
        result = payee_import.parse_payee_file(file.filename or "", content)
    except payee_import.PayeeImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:                                    # pragma: no cover
        raise HTTPException(status_code=422, detail=f"Could not read that file: {exc}") from exc

    cap = rq.get_workflow(ctx.org_id).max_payees or 100
    valid = result.valid_rows

    return {
        "filename": file.filename,
        "detected_columns": result.detected_columns,
        "headers_found": result.headers_found,
        "total_rows": len(result.rows),
        "valid_count": len(valid),
        "problem_count": len(result.problem_rows),
        "total_amount": result.total_amount,
        "max_payees": cap,
        # Reported rather than refused: the person may want to import what
        # fits and split the rest, and that is their call to make on a screen
        # showing the numbers, not ours to make behind an error.
        "over_cap": len(valid) > cap,
        "rows": [
            {
                "row_number": r.row_number,
                "name": r.name,
                "account_number": r.account_number,
                "bank_name": r.bank_name,
                "amount": r.amount,
                "purpose": r.purpose,
                "tin": r.tin,
                "phone_or_email": r.phone_or_email,
                "payee_type": r.payee_type,
                "ok": r.ok,
                "errors": r.errors,
                "warnings": r.warnings,
            }
            for r in result.rows
        ],
    }


@router.get("/audit/findings")
async def audit_findings_endpoint(
    tz_offset_minutes: int = Query(
        0, description="The caller's UTC offset, JavaScript getTimezoneOffset "
                       "convention. Only affects the working-hours test."),
    ctx: Ctx = Depends(request_context),
):
    """Run the audit tests over this organisation's records.

    Not a dashboard — a set of deterministic tests, each looking for one
    specific way money goes wrong: a broken hash chain, an exception with no
    reason, one person signing two stages, one account paid under several
    names, amounts shaved just under a threshold, a purchase split across
    several payments, a stage escalated past, approvals at 3am, gaps in the
    reference sequence.

    Readable by any signed-in user, like the rest of the audit surface: an
    organisation that hides its own control findings from its own staff is
    not running a control.
    """
    report = audit_findings.run_audit_tests(
        ctx.org_id, tz_offset_minutes=tz_offset_minutes,
    )
    return {
        "org_id": report.org_id,
        "generated_at": report.generated_at,
        "requisitions_examined": report.requisitions_examined,
        "transactions_examined": report.transactions_examined,
        "clean": report.clean,
        "by_severity": report.by_severity,
        "findings": [
            {
                "code": f.code, "title": f.title, "severity": f.severity,
                "detail": f.detail, "why": f.why, "refs": f.refs, "amount": f.amount,
            }
            for f in report.findings
        ],
    }


_REPORTS = "audit_reports"


@router.get("/audit/report.pdf")
async def audit_report_endpoint(
    start: str = Query(..., description="Period start, inclusive, YYYY-MM-DD"),
    end: str = Query(..., description="Period end, inclusive, YYYY-MM-DD"),
    label: str = Query("", description="How the period is named, e.g. 'September 2026'"),
    refresh: bool = Query(False, description="Rewrite the narrative even if one is stored"),
    tz_offset_minutes: int = Query(0),
    ctx: Ctx = Depends(request_context),
):
    """The month-end or quarter-end audit report, as a filed PDF.

    Every figure is computed in Python from stored records. One small model
    call writes the prose around those figures, and it is shown the finished
    summary rather than the population — so the cost is the same whether the
    period held ten payments or four hundred.

    The narrative is STORED per period. Re-opening a closed month returns the
    same report rather than paying to reword it, because a period that has
    ended cannot produce new figures. `refresh=true` forces a rewrite.
    """
    _export_gate(ctx)
    import datetime as _dt
    try:
        start_d = _dt.date.fromisoformat(start)
        end_d = _dt.date.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc
    if end_d < start_d:
        raise HTTPException(status_code=400, detail="'end' cannot be before 'start'.")

    data = audit_report.build_period_data(
        ctx.org_id, start, end, label=label, tz_offset_minutes=tz_offset_minutes,
    )

    key = f"{start}_{end}"
    narrative = None
    if not refresh:
        stored = store.get_store().get(ctx.org_id, _REPORTS, key)
        # Only reuse a narrative written against the same figures. If anything
        # in the period changed — a late payment, a released exception — the
        # prose could now contradict the tables beside it, and a report that
        # disagrees with itself is worse than one that cost a fraction of a
        # penny to rewrite.
        if stored and stored.get("fingerprint") == _period_fingerprint(data):
            narrative = stored.get("narrative")

    if narrative is None:
        narrative = audit_report.narrate(data)
        try:
            store.get_store().put(ctx.org_id, _REPORTS, key, {
                "fingerprint": _period_fingerprint(data),
                "narrative": narrative,
                "generated_at": data.generated_at,
            })
        except Exception as exc:                                # pragma: no cover
            print(f"[audit_report] could not store the narrative: {exc}")

    org_name = ""
    try:
        org_name = (org_config.describe(ctx.org_id) or {}).get("name", "") or ""
    except Exception:
        pass

    content = audit_report.audit_report_pdf(data, narrative, org_name=org_name)
    filename = f"audit-report_{start}_to_{end}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit/annexes.xlsx")
async def audit_annexes_endpoint(
    start: str = Query(..., description="Period start, inclusive, YYYY-MM-DD"),
    end: str = Query(..., description="Period end, inclusive, YYYY-MM-DD"),
    full_account_numbers: bool = Query(
        False, description="Show payee account numbers in full. Recorded on the "
                           "audit trail when used."),
    ctx: Ctx = Depends(request_context),
):
    """The annexes to the period report: every requisition, every compliance
    check, every approval, every exception and every supporting document, one
    sheet each, filtered and frozen ready to work with.

    Account numbers are masked to the last four digits unless explicitly
    asked for. This pack is a personal-data export — beneficiary names,
    account numbers, phone numbers — and it leaves the system as a file that
    gets emailed around. The last four digits match a line on a bank
    statement, which is what an annex is for; the full number is what lets
    someone pay it.
    """
    _export_gate(ctx)
    import datetime as _dt
    try:
        _dt.date.fromisoformat(start)
        end_d = _dt.date.fromisoformat(end)
        if end_d < _dt.date.fromisoformat(start):
            raise HTTPException(status_code=400, detail="'end' cannot be before 'start'.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc

    if full_account_numbers:
        # Unmasking is a deliberate act, so it leaves a trace. An auditor
        # asking "who pulled a full list of beneficiary bank details, and
        # when" should not have to take anyone's word for it.
        try:
            import notification_center as nc
            nc.create("audit-annexes", "", "export",
                      "Full account numbers exported",
                      body=f"{ctx.user_id} exported the {start}–{end} audit annexes "
                           "with payee account numbers unmasked.",
                      actor=ctx.user_id, org_id=ctx.org_id)
        except Exception:
            pass

    org_name = ""
    try:
        org_name = (org_config.describe(ctx.org_id) or {}).get("name", "") or ""
    except Exception:
        pass

    content = audit_annexes.build_annexes_xlsx(
        ctx.org_id, start, end, org_name=org_name,
        full_account_numbers=full_account_numbers,
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="audit-annexes_{start}_to_{end}.xlsx"'},
    )


def _period_fingerprint(data) -> str:
    """What the narrative was written against. Any change here means the
    stored prose is stale."""
    import hashlib
    parts = [
        data.raised_count, data.raised_value, data.paid_count, data.paid_value,
        data.outstanding_count, data.declined_count,
        sorted(data.by_status.items()), sorted(data.by_category.items()),
        len(data.exceptions),
        sorted((f.code, f.detail) for f in data.findings),
    ]
    return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]


@router.get("/requisitions/pending")
async def pending_for_me_endpoint(ctx: Ctx = Depends(request_context)):
    """Everything currently waiting on the signed-in user's department."""
    wf = rq.get_workflow(ctx.org_id)
    my_steps = {s.key for s in wf.steps if s.department == ctx.department}

    rows = [
        r for r in rq.list_requisitions(ctx.org_id, status=rq.ReqStatus.IN_REVIEW)
        if r.current_step in my_steps
    ]
    return {
        "department": ctx.department,
        "steps": sorted(my_steps),
        "total": len(rows),
        "requisitions": [_summary_out(r) for r in rows],
    }


# ─── log export (audit sweep) ───────────────────────────────────────────────
#
# Declared here, ahead of /requisitions/{req_id}, for the same reason
# /requisitions/pending is — a literal path after the {req_id} pattern would
# never match; FastAPI would try to load a requisition literally named
# "export".


def _export_gate(ctx: Ctx) -> None:
    try:
        import org_config
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Exports are not available.")
    if not org_config.feature_enabled(ctx.org_id, "requisition_export"):
        raise HTTPException(
            status_code=400,
            detail="This organisation has not enabled requisition exports "
                   "('requisition_export' feature flag).",
        )


@router.get("/requisitions/export/log.xlsx")
async def export_requisition_log_endpoint(
    start: str = Query(..., description="Start date, inclusive, YYYY-MM-DD"),
    end: str = Query(..., description="End date, inclusive, YYYY-MM-DD"),
    tz_offset_minutes: int = Query(
        0, description="minutes to ADD to the naive local start/end to reach "
                       "UTC (JavaScript Date.getTimezoneOffset()'s own sign — "
                       "e.g. -60 for WAT/UTC+1). Defaults to 0 (UTC) for any "
                       "caller that doesn't send it."),
    ctx: Ctx = Depends(request_context),
):
    """The weekly/monthly audit sweep: every requisition raised in [start,
    end], one row each, as an .xlsx. No role gate beyond being signed in —
    matches GET /requisitions/{id}'s own visibility (org-wide, see the
    requisition_visibility toggle); exporting what you can already see
    grants no new access.

    `start`/`end` are calendar dates as the person running the export means
    them — their own local "today", not UTC's. `submitted_at` is always
    stored in UTC (see requisitions._now_iso), so comparing a naive
    UTC-midnight boundary against it silently drops anything raised in the
    gap between local midnight and UTC midnight for any org east of UTC —
    for NEEM/TA Connect (WAT, UTC+1) that is the first hour of every day.
    `tz_offset_minutes` closes that gap without inventing per-org timezone
    config: the browser already knows the caller's offset
    (Date.getTimezoneOffset()), so the frontend sends it and this shifts the
    boundary to match, no matter which org or which timezone is asking.
    """
    _export_gate(ctx)
    import datetime as _dt
    try:
        start_d = _dt.date.fromisoformat(start)
        end_d = _dt.date.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc
    if end_d < start_d:
        raise HTTPException(status_code=400, detail="'end' cannot be before 'start'.")

    offset = _dt.timedelta(minutes=tz_offset_minutes)
    from_utc = _dt.datetime.combine(start_d, _dt.time.min) + offset
    to_utc = _dt.datetime.combine(end_d, _dt.time.max) + offset
    submitted_from = from_utc.isoformat()
    submitted_to = to_utc.isoformat()

    reqs = rq.list_requisitions(
        ctx.org_id, submitted_from=submitted_from, submitted_to=submitted_to,
    )
    if not reqs:
        raise HTTPException(
            status_code=404,
            detail=f"No requisitions raised between {start} and {end}.",
        )
    txns_by_id = {
        r.transaction_id: rq.get_transaction(ctx.org_id, r.transaction_id)
        for r in reqs if r.transaction_id
    }
    txns_by_id = {k: v for k, v in txns_by_id.items() if v is not None}

    content = requisition_export.requisition_log_xlsx(
        reqs, org_name=ctx.org_id, start=start, end=end, transactions_by_id=txns_by_id,
    )
    filename = f"requisition-log_{start}_to_{end}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── workflow config ────────────────────────────────────────────────────────


@router.get("/requisitions/workflow")
async def get_workflow_endpoint(ctx: Ctx = Depends(request_context)):
    """The org's approval chain + spend policy, as configured at onboarding."""
    return rq.get_workflow(ctx.org_id).model_dump()


@router.put("/requisitions/workflow")
async def set_workflow_endpoint(
    body: Annotated[dict, Body()],
    ctx: Ctx = Depends(request_context),
):
    """Configure the org's approval chain + spend policy (admin only)."""
    require_role(ctx, "admin")
    try:
        wf = rq.RequisitionWorkflow.model_validate(body)
        wf = rq.set_workflow(ctx.org_id, wf)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid workflow: {exc}") from exc
    return wf.model_dump()


# ─── detail ─────────────────────────────────────────────────────────────────


@router.get("/requisitions/{req_id}")
async def get_requisition_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")
    return _detail_out(req)


@router.get("/requisitions/{req_id}/export.pdf")
async def export_requisition_pdf_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    """The printable packet — everything this screen shows, laid out to
    file or email. No role gate beyond being signed in, same as viewing
    the requisition itself: exporting what you can already see grants no
    new access."""
    _export_gate(ctx)
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")
    content = requisition_export.requisition_pdf(req)
    return Response(
        content=content, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{req.ref}.pdf"'},
    )


@router.get("/requisitions/{req_id}/export.xlsx")
async def export_requisition_xlsx_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    """The same content as the PDF, one sheet per section — for pasting
    into a working file rather than filing as-is."""
    _export_gate(ctx)
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")
    content = requisition_export.requisition_xlsx(req)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{req.ref}.xlsx"'},
    )


# ─── decide ─────────────────────────────────────────────────────────────────


@router.put("/requisitions/{req_id}/draft")
async def update_draft_endpoint(
    req_id: str,
    vendor_name: Annotated[Optional[str], Form()] = None,
    amount: Annotated[Optional[float], Form()] = None,
    category: Annotated[Optional[str], Form()] = None,
    project_code: Annotated[Optional[str], Form()] = None,
    grant_code: Annotated[Optional[str], Form()] = None,
    vendor_account: Annotated[Optional[str], Form()] = None,
    vendor_bank_name: Annotated[Optional[str], Form()] = None,
    vendor_tin: Annotated[Optional[str], Form()] = None,
    vendor_phone_or_email: Annotated[Optional[str], Form()] = None,
    payment_type: Annotated[Optional[str], Form()] = None,
    budget_lines: Annotated[Optional[str], Form(
        description="JSON array of expense-breakdown rows. Send '[]' to clear it.")] = None,
    description: Annotated[Optional[str], Form()] = None,
    receipt_ids: Annotated[Optional[str], Form()] = None,
    documents: Annotated[Optional[str], Form()] = None,
    payees: Annotated[Optional[str], Form(
        description="JSON array of payee rows. Send '[]' to convert a batch "
                    "draft back into a single-vendor one.")] = None,
    currency: Annotated[Optional[str], Form()] = None,
    ctx: Ctx = Depends(request_context),
):
    """Edit a draft. Policy checks re-run on every save, so the consequence of a
    change is visible immediately rather than at submit.

    Drafts only. A submitted requisition may already be in front of an
    approver, and changing the amount underneath them is exactly what the audit
    trail exists to prevent — return it first.
    """
    fields = {
        "vendor_name": vendor_name, "amount": amount, "category": category,
        "project_code": project_code, "vendor_account": vendor_account,
        "vendor_bank_name": vendor_bank_name, "vendor_tin": vendor_tin,
        "vendor_phone_or_email": vendor_phone_or_email, "payment_type": payment_type,
        "description": description, "currency": currency,
    }
    if grant_code is not None:
        fields["grant_code"] = grant_code.strip() or None
    for key, raw in (("receipt_ids", receipt_ids), ("documents", documents)):
        if raw is not None:
            fields[key] = [s.strip() for s in raw.split(",") if s.strip()]
    if payees is not None:
        fields["payees"] = _parse_payees(payees)
    if budget_lines is not None:
        fields["budget_lines"] = _parse_budget_lines(budget_lines)
    try:
        req = rq.update_draft(ctx.org_id, req_id, actor=ctx.user_id, **fields)
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail_out(req)


@router.post("/requisitions/{req_id}/submit")
async def submit_draft_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    """Send a draft into the approval chain.

    Checks re-run first: a draft written last week may have gone stale — a
    grant can close, a vendor can be blocked, an identical invoice can arrive
    in between. An approver should never be shown a stale verdict.
    """
    try:
        req = rq.submit_draft(ctx.org_id, req_id, actor=ctx.user_id)
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail_out(req)


@router.delete("/requisitions/{req_id}/draft")
async def discard_draft_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    """Delete a draft. Only ever a draft — anything submitted is part of the
    record and gets declined, never removed."""
    try:
        deleted = rq.discard_draft(ctx.org_id, req_id, actor=ctx.user_id)
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="No such draft.")
    return {"deleted": True, "id": req_id}


@router.post("/requisitions/{req_id}/decide")
async def decide_endpoint(
    req_id: str,
    decision: Annotated[str, Form(description="approved | declined | returned")],
    notes: Annotated[str, Form(description="Why — shown to the next approver and the auditor")] = "",
    overrides: Annotated[str, Form(description="Comma-separated policy check codes to release")] = "",
    override_reason: Annotated[str, Form(description="Required when overriding")] = "",
    override_authority: Annotated[str, Form(description="Authority relied on, e.g. 'ED (DOA up to 200k)'")] = "",
    ctx: Ctx = Depends(request_context),
):
    """
    Record the signed-in user's decision at the current step.

    Approving over a failing check requires `overrides` plus a written
    `override_reason`; the engine refuses if the step lacks the authority or
    the amount is above that step's override limit.
    """
    require_role(ctx, "reviewer", "approver", "admin")

    try:
        dec = rq.Decision(decision)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="decision must be 'approved', 'declined', or 'returned'."
        ) from None

    try:
        req = rq.decide(
            ctx.org_id, req_id,
            decision=dec,
            actor=ctx.user_id,
            department=ctx.department,
            notes=notes,
            overrides=[s.strip() for s in overrides.split(",") if s.strip()],
            override_reason=override_reason,
            override_authority=override_authority,
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.status == rq.ReqStatus.IN_REVIEW:
        _notify_current_step(ctx, req, rq.get_workflow(ctx.org_id))
    elif req.status in {rq.ReqStatus.DECLINED, rq.ReqStatus.RETURNED}:
        _notify(ctx, req, kind="returned", department=req.department,
                title=f"{req.ref}: {req.status.value}",
                body=notes or f"{decision} at the {dec.value} step.")

    return _detail_out(req)


# ─── hold / release ─────────────────────────────────────────────────────────


@router.post("/requisitions/{req_id}/hold")
async def place_on_hold_endpoint(
    req_id: str,
    reason: Annotated[str, Form(description="Required — why this is paused")],
    ctx: Ctx = Depends(request_context),
):
    """Pause a requisition at its current step. Does not decide it — the same
    approver (or anyone else in that department) picks it back up later with
    /release-hold. Requires org.requisition_hold and a written reason."""
    require_role(ctx, "reviewer", "approver", "admin")
    try:
        req = rq.place_on_hold(
            ctx.org_id, req_id, actor=ctx.user_id, department=ctx.department, reason=reason,
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _notify(ctx, req, kind="held", department=req.department,
            title=f"{req.ref}: on hold",
            body=req.hold_reason or "")
    return _detail_out(req)


@router.post("/requisitions/{req_id}/release-hold")
async def release_hold_endpoint(
    req_id: str,
    notes: Annotated[str, Form(description="Optional — what changed")] = "",
    ctx: Ctx = Depends(request_context),
):
    """Resume a held requisition at the same step it was paused on."""
    require_role(ctx, "reviewer", "approver", "admin")
    try:
        req = rq.release_hold(
            ctx.org_id, req_id, actor=ctx.user_id, department=ctx.department, notes=notes,
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Back in front of an approver — same "your turn" notification any other
    # arrival at a step gets, not a special case.
    _notify_current_step(ctx, req, rq.get_workflow(ctx.org_id))
    return _detail_out(req)


# ─── comments ────────────────────────────────────────────────────────────


@router.post("/requisitions/{req_id}/comments")
async def add_comment_endpoint(
    req_id: str,
    text: Annotated[str, Form(description="The comment")],
    ctx: Ctx = Depends(request_context),
):
    """Add a message to the requisition's discussion thread. Not role-gated
    and not restricted by status — see requisitions.add_comment()."""
    try:
        req = rq.add_comment(ctx.org_id, req_id, actor=ctx.user_id,
                              department=ctx.department, text=text)
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Tell whoever is closest to needing to see it: the submitter's own
    # department, and, if it's still moving, whoever it's currently with —
    # skipping the commenter's own department either way, and skipping a
    # duplicate if both happen to be the same department.
    current_dept = _step_department(ctx, req) if req.current_step else ""
    notify_depts = {req.department, current_dept} - {"", ctx.department}
    for dept in notify_depts:
        _notify(ctx, req, kind="mention", department=dept,
                title=f"{req.ref}: new comment",
                body=text.strip()[:200])

    return _detail_out(req)


def _step_department(ctx: Ctx, req: rq.Requisition) -> str:
    if not req.current_step:
        return ""
    wf = rq.get_workflow(ctx.org_id)
    step = next((s for s in wf.steps if s.key == req.current_step), None)
    return step.department if step else ""


# ─── attachments ────────────────────────────────────────────────────────────


@router.post("/requisitions/{req_id}/attachments")
async def upload_attachment_endpoint(
    req_id: str,
    file: Annotated[UploadFile, File(description="The file to attach")],
    ctx: Ctx = Depends(request_context),
):
    """Attach a real file — the invoice, a signed memo, a photo of a
    receipt — as opposed to `documents`, which only ticks off a label.
    Requires org.requisition_attachments. Not role-gated: attaching
    evidence moves no money and grants no authority, same as a comment.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(content) > attachments.MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"File is {len(content):,} bytes — this instance's limit is "
                     f"{attachments.MAX_ATTACHMENT_BYTES:,} bytes."),
        )

    # Fail before touching storage if the flag is off or the requisition
    # doesn't exist — no point uploading bytes that will just be discarded.
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")
    try:
        import org_config
        if not org_config.feature_enabled(ctx.org_id, "requisition_attachments"):
            raise HTTPException(
                status_code=400,
                detail="This organisation has not enabled file attachments on "
                       "requisitions ('requisition_attachments' feature flag).",
            )
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Attachments are not available.")

    attachment_id = uuid.uuid4().hex
    try:
        storage_key = attachments.get_backend().put(
            ctx.org_id, req_id, attachment_id, file.filename or "file",
            content, file.content_type or "application/octet-stream",
        )
    except attachments.AttachmentError as exc:
        raise HTTPException(status_code=502, detail=f"Could not store the file: {exc}") from exc

    try:
        req = rq.add_attachment(
            ctx.org_id, req_id, actor=ctx.user_id,
            filename=file.filename or "file",
            content_type=file.content_type or "application/octet-stream",
            size=len(content), storage_key=storage_key, attachment_id=attachment_id,
        )
    except rq.RequisitionError as exc:
        # The file is already in the bucket at this point but the metadata
        # write was refused (e.g. the flag was switched off between the
        # check above and here, or the per-requisition cap was hit by a
        # concurrent upload). The orphaned object is harmless — nothing
        # references its key — and is cheaper to accept than to build a
        # cross-backend rollback for a race this narrow.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _detail_out(req)


@router.get("/requisitions/{req_id}/attachments/{attachment_id}")
async def download_attachment_endpoint(
    req_id: str, attachment_id: str, ctx: Ctx = Depends(request_context),
):
    """Fetch one attached file. Redirects to a short-lived signed URL when
    the backend supports one (Supabase Storage in production); streams the
    bytes directly when it doesn't (local disk in dev — see
    attachments.LocalDiskAttachmentBackend)."""
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")
    att = next((a for a in req.attachments if a.id == attachment_id), None)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    backend = attachments.get_backend()
    try:
        url = backend.url(att.storage_key)
    except attachments.AttachmentError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch the file: {exc}") from exc
    if url:
        return RedirectResponse(url)

    if isinstance(backend, attachments.LocalDiskAttachmentBackend):
        try:
            content = backend.read(att.storage_key)
        except attachments.AttachmentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(
            content=content, media_type=att.content_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{att.filename}"'},
        )

    raise HTTPException(status_code=502, detail="Storage backend returned no way to fetch this file.")


# ─── compliance check ───────────────────────────────────────────────────────


def _requisition_payment_record(req) -> dict:
    """The requisition's own facts, shaped for compliance.build_payment_record_block.

    Read straight off the stored record — nothing recomputed, nothing inferred.
    Money is rendered WITH its currency so the model compares like with like;
    an invoice in USD against a request in NGN is a finding, and it can only
    be one if the model knows which is which.

    Bank account and tax ID are included deliberately. A redirected payment —
    real payee, real work, substituted account — is the highest-frequency
    fraud in accounts payable, and the account number printed on the vendor's
    own invoice is the evidence against it.
    """
    cur = (getattr(req, "currency", "") or "NGN").strip()

    def money(value) -> str:
        return f"{cur} {float(value or 0):,.2f}"

    record: dict = {
        "reference": req.ref,
        "date": (getattr(req, "created_at", "") or "")[:10],
        "payment_type": getattr(req, "payment_type", "") or "",
        "category": req.category or "",
        "amount": money(req.amount) if req.amount else "",
        "payee": req.vendor_name or "",
        "payee_account": getattr(req, "vendor_account", "") or "",
        "payee_bank": getattr(req, "vendor_bank_name", "") or "",
        "payee_tin": getattr(req, "vendor_tin", "") or "",
        "project_code": getattr(req, "project_code", "") or "",
        "grant_code": getattr(req, "grant_code", "") or "",
        "purpose": (getattr(req, "description", "") or "").strip(),
        "payee_count": len(getattr(req, "payees", []) or []),
    }

    record["budget_lines"] = [
        {
            "description": bl.description,
            "quantity": bl.quantity or "",
            "unit_cost": money(bl.unit_cost) if bl.unit_cost else "",
            "line_total": money(bl.line_total) if bl.line_total else "",
        }
        for bl in (getattr(req, "budget_lines", []) or [])
    ]
    return record


@router.post("/requisitions/{req_id}/compliance-check")
async def run_compliance_check_endpoint(
    req_id: str,
    rulebook_id: Annotated[Optional[str], Form(
        description="Explicit rulebook to check this requisition against — "
                    "overrides the workflow's default rulebook_id for this "
                    "one run. Omit to use the workflow's configured default.",
    )] = None,
    ctx: Ctx = Depends(request_context),
):
    """Check this requisition's real attachments (WO-22) against a compliance
    rulebook — the AI-assisted semantic layer (compliance.py) alongside,
    never instead of, the deterministic PolicyCheck list this engine already
    runs on every requisition. A code-level PolicyCheck FAIL is never
    softened by a clean compliance verdict, or vice versa; the two are shown
    side by side, not merged.

    Which rulebook: an explicit `rulebook_id` on this request wins; otherwise
    falls back to the workflow's configured default (Settings → Workflow).
    Not every requisition should be judged against the same policy document
    — a travel claim and an equipment purchase read against different
    rulebooks in practice — so whoever is running the check, not just
    whoever configured the workflow months ago, decides which one applies
    here. The chosen rulebook is recorded on the saved ComplianceSummary
    (rulebook_id/rulebook_name) exactly as before, so the audit trail always
    shows which policy a given verdict was actually checked against.

    Requires org.requisition_compliance_check AND a rulebook, one way or the
    other. NOT role-gated — any signed-in user who can already see the
    requisition can run this, the same visibility rule as attaching a file
    or posting a comment: it moves no money and grants no authority, a
    submitter checking their own request before an approver ever opens it is
    exactly the point. The API cost this incurs is controlled at the org
    level, by the feature flag itself — an org that finds this too expensive
    to run freely turns the flag off, rather than this route picking which
    roles are trusted to spend money.
    """
    try:
        import org_config
        if not org_config.feature_enabled(ctx.org_id, "requisition_compliance_check"):
            raise HTTPException(
                status_code=400,
                detail="This organisation has not enabled compliance-rulebook "
                       "checks on requisitions ('requisition_compliance_check' "
                       "feature flag).",
            )
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Compliance checks are not available.")

    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")

    wf = rq.get_workflow(ctx.org_id)
    chosen_rulebook_id = (rulebook_id or "").strip() or (wf.rulebook_id or "").strip()
    if not chosen_rulebook_id:
        raise HTTPException(
            status_code=400,
            detail="No compliance rulebook was chosen for this check, and this "
                   "organisation has no default configured under Settings → "
                   "Workflow. Pick one when running the check, or set a default.",
        )

    # Read straight from the shared "rulebooks" store collection rather than
    # through compliance_routes.py's private loaders — that module owns the
    # legacy checks/policy-interpretation UI, not rulebook storage itself,
    # and this keeps the requisition engine from depending on another
    # router's internals for something both already reach via store.py.
    raw_rulebook = store.get_store().get(ctx.org_id, "rulebooks", chosen_rulebook_id)
    if raw_rulebook is None:
        raise HTTPException(
            status_code=404,
            detail=f"The rulebook '{chosen_rulebook_id}' no longer exists.",
        )
    try:
        rulebook = PolicyRulebook.model_validate(raw_rulebook)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not load the chosen rulebook: {exc}"
        ) from exc

    if not req.attachments:
        raise HTTPException(
            status_code=400,
            detail="Attach at least one file before running a compliance check.",
        )

    # Read + extract text from every attachment. One unreadable file (a
    # storage hiccup, a genuinely corrupt upload) shouldn't block a check
    # the rest of the bundle can still support — skip it, don't fail the
    # whole request; only fail if NOTHING readable came out of any of them.
    backend = attachments.get_backend()
    docs: list[tuple[str, str]] = []
    for att in req.attachments:
        try:
            content = backend.read(att.storage_key)
        except attachments.AttachmentError as exc:
            print(f"[DOCex] Could not read attachment {att.id} for compliance check: {exc}")
            continue
        text = fast_extract.extract_text(att.filename, content).strip()
        if text:
            docs.append((att.filename, text))

    if not docs:
        raise HTTPException(
            status_code=422,
            detail="No readable text in the attached files — scanned images "
                   "need OCR before a compliance check can read them.",
        )

    # WO-40. The model is about to be asked to reconcile these documents
    # against the payment voucher. In DOCex the voucher is this requisition,
    # so unless we hand it over the check can only judge the documents against
    # each other — it cannot see that a ₦620,000 invoice is attached to a
    # ₦562,500 request. Gated, because it adds tokens to every check and an
    # org should be able to decline that cost.
    payment_record = None
    if org_config.feature_enabled(ctx.org_id, "compliance_payment_record"):
        payment_record = _requisition_payment_record(req)

    result = compliance.check_payment_safe(
        docs, rulebook, payment_label=req.ref, payment_record=payment_record,
    )

    summary = rq.ComplianceSummary(
        rulebook_id=rulebook.id,
        rulebook_name=rulebook.name,
        overall_verdict=result.overall_verdict,
        overall_summary=result.overall_summary,
        results=[
            rq.ComplianceFinding(
                rule_id=r.rule_id, rule_description=r.rule_description,
                verdict=r.verdict, reasoning=r.reasoning,
                policy_citation=r.policy_citation, payment_evidence=r.payment_evidence,
                applied_to_document=r.applied_to_document,
            )
            for r in result.results
        ],
        document_count=len(docs),
    )
    try:
        req = rq.record_compliance_result(
            ctx.org_id, req_id, actor=ctx.user_id, summary=summary,
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _detail_out(req)


@router.post("/requisitions/{req_id}/route")
async def route_requisition_endpoint(
    req_id: str,
    target_step: Annotated[str, Form(description="Which stage to send it to")],
    reason: Annotated[str, Form(description="Why — required, and read at audit")] = "",
    ctx: Ctx = Depends(request_context),
):
    """Send a requisition up or down the approval chain.

    The fourth move, alongside approve / return / decline. Escalating forward
    skips the stages in between and says so on the audit trail; sending it
    back hands it to an earlier stage without bouncing it to the submitter,
    so the reviews already done are not thrown away.

    Not role-gated beyond the department boundary the engine enforces: only
    whoever the requisition is actually sitting with can move it, which is
    the same rule that governs deciding it and putting it on hold.
    """
    try:
        req = rq.route_to(
            ctx.org_id, req_id, target_step=target_step,
            actor=ctx.user_id, department=ctx.department, reason=reason,
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Tell whoever it just landed on. Escalating to someone who never finds
    # out is the same stall the escalation was meant to break.
    wf = rq.get_workflow(ctx.org_id)
    _notify_current_step(ctx, req, wf)
    return _detail_out(req)


# ─── emailed sign-off: escalate, delegate, or send to someone outside ──────
#
# Requisitions are approved in-app by signed-in people, and that remains the
# normal path. This is the other one: the AED is travelling, a board member
# has to see a large payment, an auditor wants to sign something off, and the
# chain would otherwise stop dead until someone gets to a laptop.
#
# The capability already existed — but only on compliance checks, which are
# the SEPARATE, parallel system this codebase is consolidating away from. It
# belongs on the payment spine, so it now lives here.
#
# How authority works, since the recipient may have no DOCex account at all:
# minting the link is itself an authenticated, audited act by someone already
# in the system, who names the step and the person. That act is the
# delegation. The recipient then acts FOR that step, and everything the
# engine already enforces still applies — the request must be at that step,
# the self-approval rule still bites, and the audit chain records the
# decision against their email with the time and the IP it came from.
#
# One thing emailed sign-off deliberately CANNOT do: release a blocking
# policy check. An override needs a named authority and an amount inside that
# step's limit, checked against a real account. A link in an inbox is not
# that, so overrides stay in-app.


@router.get("/requisitions/{req_id}/send-options")
async def send_options_endpoint(req_id: str, ctx: Ctx = Depends(request_context)):
    """Who this requisition can be sent to, and how.

    The old screen asked someone to type an email address from memory into a
    box — for a person the system already knows, at a step whose owning
    department it also knows. This answers the question properly so the UI
    can offer names instead of an empty field.

    Three kinds of destination, which the caller should not have to
    distinguish between up front:

      stage   another stage of this org's own chain — escalate it forward or
              hand it back, with a reason
      person  someone with an account in the department that owns a stage.
              They get it in their queue; no link, no email needed
      email   anyone else, including people with no account at all

    Deliberately narrower than /auth/users, which is admin-only and returns
    everything about everyone. This returns a name, an email and a department
    for people who could actually act on THIS requisition, which is what a
    submitter legitimately needs to route their own payment.
    """
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")

    wf = rq.get_workflow(ctx.org_id)
    engaged = rq._steps_for(wf, req.amount)
    engaged_keys = [s.key for s in engaged]
    current_index = engaged_keys.index(req.current_step) if req.current_step in engaged_keys else -1

    stages = []
    for i, step in enumerate(engaged):
        if step.key == req.current_step:
            continue
        stages.append({
            "key": step.key,
            "label": step.label or step.key,
            "department": step.department,
            "direction": ("forward" if current_index >= 0 and i > current_index else "back"),
        })

    # People who could act, newest-relevant first: the department that owns
    # the current step, then the departments owning other stages, then anyone
    # else in the organisation.
    owning = {s.department for s in engaged if s.department}
    current_dept = next((s.department for s in engaged if s.key == req.current_step), "")
    people = []
    try:
        for u in auth.list_public(ctx.org_id):
            if not u.active or u.email == req.submitted_by:
                continue                   # the submitter cannot approve their own
            people.append({
                "email": u.email, "name": u.name, "department": u.department,
                "role": u.role,
                "owns_current_step": u.department == current_dept,
                "in_chain": u.department in owning,
            })
    except Exception as exc:                                    # pragma: no cover
        print(f"[signoff] could not list people ({exc}) — the picker falls back to email.")
    people.sort(key=lambda p: (not p["owns_current_step"], not p["in_chain"], p["name"]))

    return {
        "current_step": req.current_step,
        "current_step_label": next(
            (s.label or s.key for s in engaged if s.key == req.current_step), ""),
        "current_department": current_dept,
        "can_move": req.status == rq.ReqStatus.IN_REVIEW and bool(req.current_step),
        "stages": stages,
        "people": people,
        # So the UI can tell the truth rather than promising an email that
        # will never arrive. When this is false the link is the product, not
        # a fallback, and the screen should say so.
        "email_configured": notifications.is_smtp_configured(),
    }


class _SignoffRequestIn(BaseModel):
    step: str
    approver_email: str
    note: str = ""


@router.post("/requisitions/{req_id}/request-signoff")
async def request_requisition_signoff(
    req_id: str, body: _SignoffRequestIn, ctx: Ctx = Depends(request_context),
):
    """Email someone a unique, expiring link to sign off this requisition.

    Returns the link as well as whether the email went out — deliberately, so
    it can be copied and sent by hand when SMTP isn't configured. A demo where
    the link is unreachable teaches people the feature doesn't work.
    """
    req = rq.get_requisition(ctx.org_id, req_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Requisition not found.")

    email = (body.approver_email or "").strip().lower()
    if not looks_like_email(email):
        raise HTTPException(status_code=422, detail="A valid approver email is required.")

    step_key = (body.step or "").strip() or (req.current_step or "")
    if not step_key:
        raise HTTPException(
            status_code=400,
            detail=f"{req.ref} is not sitting at an approval step, so there is "
                   "nothing to sign off.",
        )
    wf = rq.get_workflow(ctx.org_id)
    step = next((s for s in wf.steps if s.key == step_key), None)
    if step is None:
        raise HTTPException(status_code=404, detail=f"No approval step '{step_key}'.")

    token = approval_tokens.make_token(
        req.id, step_key, email, org=ctx.org_id, kind="requisition",
    )
    code = _short_code(token, org=ctx.org_id, req_id=req.id, created_by=ctx.user_id)
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    link = f"{app_url}/approve/r/{code}" if app_url else f"/approve/r/{code}"

    # Recorded BEFORE the email goes anywhere: who delegated what, to whom.
    # If the send then fails, the delegation is still on the record — which is
    # the right way round for an audit trail.
    rq.note_event(
        ctx.org_id, req.id, actor=ctx.user_id, department=ctx.department,
        event="signoff_requested",
        detail=f"{step.label or step_key} sign-off requested from {email}"
               + (f" — {body.note.strip()}" if body.note.strip() else ""),
    )

    emitted = approval_webhook.emit_approval_request({
        "requisition_id": req.id, "requisition_ref": req.ref, "org": ctx.org_id,
        "step": step_key, "approver_email": email,
        "amount": req.amount, "currency": req.currency, "payee": req.vendor_name,
        "requested_by": ctx.user_id, "deep_link": link,
    })

    emailed = False
    try:
        emailed = notifications.send_raw_email(
            email,
            f"[DOCex] Sign-off needed — {req.ref} ({req.vendor_name})",
            "\n".join([
                f"{ctx.user_id} has asked you to sign off a payment request as "
                f"{step.label or step_key}.",
                "",
                f"  Reference : {req.ref}",
                f"  Payee     : {req.vendor_name}",
                f"  Amount    : {req.currency} {req.amount:,.2f}",
                f"  Purpose   : {req.description or '—'}",
                *( [f"  Note      : {body.note.strip()}"] if body.note.strip() else [] ),
                "",
                "Open your unique, secure link to review it in full and approve "
                "or send it back:",
                f"  {link}",
                "",
                "The link expires in 7 days and only works from this email "
                "address. Every sign-off is recorded with your email, the time, "
                "and the address it came from.",
            ]),
        )
    except Exception as exc:                                    # pragma: no cover
        print(f"[DOCex] Sign-off email to {email} failed: {exc}")

    return {
        "sent": emailed,
        "webhook": emitted,
        "link": link,
        "step": step_key,
        "approver_email": email,
    }


_SIGNOFF_LINKS = "signoff_links"


def _short_code(token: str, *, org: str, req_id: str, created_by: str) -> str:
    """Store the signed token behind a short code, and hand back the code.

    The token itself is ~400 characters of base64. It is correct, it is
    unforgeable, and nobody is pasting it into WhatsApp — which is how an
    approval actually gets chased here. The code is eight url-safe characters
    in front of the same token, so the link is short enough to read out over
    the phone.

    The code is a lookup key, never the credential: it resolves to the signed
    token, and that token is still verified, still bound to one org, one
    requisition, one step and one email, and still expires. A guessed code
    gets someone a token they cannot use for anything they were not already
    the named approver of.
    """
    import secrets
    # The code carries its own organisation, separated by "~" — a character
    # base64url never produces, so a code can never be mistaken for a token.
    # Without it, resolving a code would mean scanning every tenant's store
    # for a match, and "search all organisations" is not a thing this
    # codebase should ever learn to do.
    suffix = secrets.token_urlsafe(6)[:8]
    try:
        store.get_store().put(org, _SIGNOFF_LINKS, suffix, {
            "token": token, "requisition_id": req_id,
            "created_by": created_by, "created_at": rq._now_iso(),
        })
    except Exception as exc:                                    # pragma: no cover
        print(f"[signoff] could not store the short link ({exc}) — using the raw token.")
        return token
    return f"{org}~{suffix}"


def _resolve_token(token_or_code: str) -> str:
    """Accept either a short code or a raw signed token.

    Raw tokens still work. Links sent before short codes existed are sitting
    in people's inboxes, and an approval link that stops working because the
    product improved is an approval that does not happen.
    """
    value = (token_or_code or "").strip()
    if "~" not in value:
        return value                       # a raw signed token
    org, _, suffix = value.partition("~")
    try:
        record = store.get_store().get(org, _SIGNOFF_LINKS, suffix)
    except Exception:
        return value
    if record and record.get("token"):
        return record["token"]
    return value                           # let verify_token produce the error


def _signoff_token(token: str) -> tuple[dict, rq.Requisition, rq.WorkflowStep]:
    """Shared by the two PUBLIC routes below. Resolves a token to the exact
    requisition and step it was minted for, refusing anything stale."""
    try:
        payload = approval_tokens.verify_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.get("kind") != "requisition":
        raise HTTPException(status_code=400, detail="This is not a requisition link.")
    org = (payload.get("org") or "").strip()
    if not org:
        raise HTTPException(status_code=400, detail="This approval link is invalid.")

    req = rq.get_requisition(org, payload["cid"])
    if req is None:
        raise HTTPException(status_code=404, detail="This payment request no longer exists.")
    step_key = payload["stage"]
    step = next((s for s in rq.get_workflow(org).steps if s.key == step_key), None)
    if step is None:
        raise HTTPException(
            status_code=409,
            detail="The approval step this link was created for no longer exists "
                   "in this organisation's workflow.",
        )
    return payload, req, step


@router.get("/requisitions/approve/verify/{token}")
async def verify_requisition_signoff(token: str):
    """PUBLIC. Validate a sign-off link and return enough of the requisition
    for the approver to actually make a decision — not just its reference.
    Someone asked to authorise money should see the amount, the payee, the
    purpose, and every policy check, before they click anything."""
    payload, req, step = _signoff_token(_resolve_token(token))
    return {
        "requisition_ref": req.ref,
        "payee": req.vendor_name,
        "amount": req.amount,
        "currency": req.currency,
        "amount_in_words": rq.amount_in_words(req.amount, req.currency),
        "category": req.category,
        "description": req.description,
        "payment_type": req.payment_type,
        "submitted_by": req.submitted_by,
        "submitted_at": req.submitted_at,
        "step": step.key,
        "step_label": step.label or step.key,
        "approver_email": payload["email"],
        "status": req.status.value,
        "checks": [_check_out(c) for c in req.checks],
        "blocking_count": len(rq.blocking_checks(req)),
        "attachment_count": len(req.attachments),
        "compliance": _compliance_out(req.compliance) if req.compliance else None,
        # Whether this link can still be acted on, and if not, why — answered
        # here so the page can say so plainly instead of failing on submit.
        "actionable": req.status == rq.ReqStatus.IN_REVIEW and req.current_step == step.key,
        "already_moved": req.current_step != step.key,
    }


class _SignoffActIn(BaseModel):
    action: Literal["approve", "return", "decline"]
    note: str = ""


@router.post("/requisitions/approve/{token}")
async def act_on_requisition_signoff(token: str, body: _SignoffActIn, request: Request):
    """PUBLIC. Record a decision from the approver's unique link.

    Routed through rq.decide() rather than writing an Approval directly, so an
    emailed sign-off is held to exactly the same rules as one made in-app: the
    request must still be at this step, the submitter still cannot approve
    their own, and the decision still joins the hash-chained audit log.
    """
    payload, req, step = _signoff_token(_resolve_token(token))
    org = payload["org"]
    email = payload["email"]

    if req.current_step != step.key:
        raise HTTPException(
            status_code=409,
            detail=f"{req.ref} has moved on since this link was sent — it is now "
                   f"{'with ' + req.current_step if req.current_step else req.status.value}. "
                   "No action was taken.",
        )

    decision = {
        "approve": rq.Decision.APPROVED,
        "return": rq.Decision.RETURNED,
        "decline": rq.Decision.DECLINED,
    }[body.action]

    ip = request.client.host if request.client else "unknown"
    note = (body.note or "").strip()
    try:
        updated = rq.decide(
            org, req.id,
            decision=decision,
            actor=email,
            department=step.department,
            notes=(f"{note} " if note else "") + f"[signed off by email from {ip}]",
        )
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "recorded": True,
        "action": body.action,
        "requisition_ref": updated.ref,
        "status": updated.status.value,
        "current_step": updated.current_step,
    }


@router.post("/requisitions/{req_id}/resubmit")
async def resubmit_endpoint(
    req_id: str,
    notes: Annotated[str, Form(description="What was fixed")] = "",
    ctx: Ctx = Depends(request_context),
):
    """Submitter fixed a returned requisition — re-run checks and re-route it."""
    try:
        req = rq.resubmit(ctx.org_id, req_id, actor=ctx.user_id, notes=notes)
    except rq.RequisitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail_out(req)


# ─── payment ────────────────────────────────────────────────────────────────


@router.post("/requisitions/{req_id}/pay")
async def pay_endpoint(
    req_id: str,
    bank_reference: Annotated[str, Form(description="Bank confirmation reference")] = "",
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    ctx: Ctx = Depends(request_context),
):
    """
    Record that the payment left the account. Freezes an immutable transaction
    record holding copies of every check, approval, and audit line.

    Send an `Idempotency-Key` header: a retried call replays the original
    transaction rather than freezing a second record against one debit.
    """
    require_role(ctx, "approver", "admin")
    try:
        with idempotency.guard(ctx.org_id, "requisition.pay", idempotency_key) as slot:
            if slot.replayed:
                return slot.result

            try:
                txn = rq.mark_paid(
                    ctx.org_id, req_id,
                    actor=ctx.user_id,
                    bank_reference=bank_reference,
                    department=ctx.department or "finance",
                )
            except rq.RequisitionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            paid_req = rq.get_requisition(ctx.org_id, req_id)
            if paid_req is not None:
                _notify(ctx, paid_req, kind="paid", department=paid_req.department,
                        title=f"{paid_req.ref}: paid",
                        body=f"{txn.amount:,.2f} {txn.currency} — ref {txn.bank_reference or '(none)'}.")

            return slot.store(_txn_out(txn))
    except idempotency.IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─── payments (immutable transaction records) ───────────────────────────────────────────────────────────


@router.get("/payments")
async def list_transactions_endpoint(
    grant_code: Optional[str] = None,
    project_code: Optional[str] = None,
    ctx: Ctx = Depends(request_context),
):
    rows = rq.list_transactions(ctx.org_id, grant_code=grant_code, project_code=project_code)
    return {
        "total": len(rows),
        "value": round(sum(t.amount for t in rows), 2),
        "transactions": [
            {
                "id": t.id, "requisition_ref": t.requisition_ref,
                "vendor_name": t.vendor_name, "amount": t.amount, "currency": t.currency,
                "category": t.category, "project_code": t.project_code,
                "grant_code": t.grant_code, "paid_at": t.paid_at,
                "exceptions_count": t.exceptions_count,
            }
            for t in rows
        ],
    }


@router.get("/payments/{txn_id}")
async def get_transaction_endpoint(txn_id: str, ctx: Ctx = Depends(request_context)):
    """Immutable transaction detail — the screen an auditor opens."""
    txn = rq.get_transaction(ctx.org_id, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _txn_out(txn)


# ─── audit ──────────────────────────────────────────────────────────────────


@router.get("/audit/summary")
async def audit_summary_endpoint(ctx: Ctx = Depends(request_context)):
    """
    The auditor's first screen: totals, every policy exception, and whether
    each one carries a written reason and a named authority.
    """
    return rq.audit_summary(ctx.org_id)
