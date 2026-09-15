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

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, Form, Header, HTTPException, Query

import idempotency
import requisitions as rq
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
        "description": description, "currency": currency,
    }
    if grant_code is not None:
        fields["grant_code"] = grant_code.strip() or None
    for key, raw in (("receipt_ids", receipt_ids), ("documents", documents)):
        if raw is not None:
            fields[key] = [s.strip() for s in raw.split(",") if s.strip()]
    if payees is not None:
        fields["payees"] = _parse_payees(payees)
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
