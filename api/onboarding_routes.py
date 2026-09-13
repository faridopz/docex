"""
DOCex onboarding — configure a new organisation from inside the app.

WHAT THIS REPLACES
Until now, bringing up a client meant Farid hand-writing a JSON profile
(profiles/<client>.json) and running org_config.py from a terminal — a
developer had to be in the loop for something as basic as "add a fourth
approval step" or "we spend in a category you don't have." That is the
opposite of self-service, and it is the exact complaint the org settings
rebuild (see api/org_routes.py, api/requisition_routes.py) started fixing:
"the org settings page is rigid and doesn't let an org configure itself."

WHAT THIS IS NOT
This does not create a new tenant, provision a new database, or spin up a new
instance — DOCex today runs one organisation per deployment (see CLAUDE.md,
context.py's default_org()). This is the missing piece INSIDE that: the
admin of an already-deployed instance configures their departments and
approval chain themselves, in the app, instead of asking for a JSON file to
be edited on their behalf. True self-serve multi-tenant signup (a stranger
signs up on a marketing site and gets their own instance) is a bigger,
separate project.

  GET  /onboarding/status  — has this org configured itself yet?
  POST /onboarding/setup   — apply departments + approval chain in one step

Both admin-scoped in effect: status is safe for anyone (same reasoning as
GET /org/config — no policy numbers, just "is setup done"); setup requires
the admin role, same as PUT /requisitions/workflow and POST /departments.

WHY ONE ATOMIC ENDPOINT RATHER THAN THE WIZARD CALLING /departments and
/requisitions/workflow ITSELF
A wizard that calls N existing endpoints in sequence can succeed on
departments and then fail validation on the workflow step, leaving the org in
a half-configured, hard-to-explain state — exactly the kind of thing
org_config.validate_profile()'s "validate before any write" rule exists to
prevent for the CLI path. This mirrors that: validate the whole shape first,
write departments, then the workflow, and report clearly if the second step
fails (departments HAVE been saved at that point — see the response's
`partial` flag — so the wizard can tell the admin exactly what's still
needed rather than a bare 422).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

import departments as dept_mod  # noqa: E402
import requisitions as rq  # noqa: E402
from models import DepartmentDef  # noqa: E402

from .context import Ctx, request_context, require_role  # noqa: E402

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    configured: bool
    departments_configured: bool
    workflow_configured: bool
    department_count: int
    step_count: int


@router.get("/status", response_model=OnboardingStatus)
async def get_status(ctx: Ctx = Depends(request_context)) -> OnboardingStatus:
    """Has an admin actually set this org up, or is it still running on
    unpersisted defaults? Either half missing means the wizard should show."""
    depts_done = dept_mod.has_registry_configured(ctx.org_id)
    wf_done = rq.has_workflow_configured(ctx.org_id)
    reg = dept_mod.load(ctx.org_id)
    wf = rq.get_workflow(ctx.org_id)
    return OnboardingStatus(
        configured=depts_done and wf_done,
        departments_configured=depts_done,
        workflow_configured=wf_done,
        department_count=len(reg.departments),
        step_count=len(wf.steps),
    )


class DepartmentIn(BaseModel):
    name: str
    key: Optional[str] = None
    is_final_authority: bool = False


class StepIn(BaseModel):
    label: str
    department: str
    min_amount: float = 0.0
    can_override: bool = False
    override_limit: Optional[float] = None


class SetupRequest(BaseModel):
    """Everything the wizard collects, in one shape.

    `workflow_size` picks one of the engine's existing tested presets
    (default_workflow: small/medium/large — see requisitions.py) as a
    starting point; `custom_steps`, if given, overrides it entirely with the
    admin's own chain. This means "small/medium/large" is never a second,
    parallel definition of a chain — it's the exact same defaults every
    other onboarding path uses, just offered as a one-click starting point
    instead of typed out.
    """
    currency: str = "NGN"
    departments: list[DepartmentIn] = Field(default_factory=list)
    workflow_size: str = "medium"          # small | medium | large | custom
    custom_steps: list[StepIn] = Field(default_factory=list)
    max_amount: Optional[float] = None
    allowed_categories: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)


class SetupResult(BaseModel):
    ok: bool
    partial: bool = False           # departments saved, workflow rejected
    departments: int = 0
    steps: int = 0
    error: Optional[str] = None


@router.post("/setup", response_model=SetupResult)
async def setup(body: SetupRequest, ctx: Ctx = Depends(request_context)) -> SetupResult:
    require_role(ctx, "admin")

    if not body.departments:
        raise HTTPException(status_code=422, detail="At least one department is required.")
    seen_keys: set[str] = set()
    dept_defs: list[DepartmentDef] = []
    for i, d in enumerate(body.departments):
        name = d.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail=f"Department {i + 1} has no name.")
        key = dept_mod.slugify(d.key or name)
        if key in seen_keys:
            raise HTTPException(status_code=422, detail=f"Duplicate department '{key}'.")
        seen_keys.add(key)
        dept_defs.append(DepartmentDef(
            key=key, name=name, is_final_authority=d.is_final_authority,
        ))

    # Departments first — a workflow step can then legally reference them.
    try:
        dept_mod.replace_all(dept_defs, {}, org_id=ctx.org_id)
    except dept_mod.DepartmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Build the workflow: a preset, or the admin's own steps.
    if body.workflow_size == "custom":
        if not body.custom_steps:
            return SetupResult(ok=False, partial=True, departments=len(dept_defs),
                              error="Custom was chosen but no steps were provided. "
                                    "Departments are saved — add steps and try again.")
        steps = [
            rq.WorkflowStep(
                key=dept_mod.slugify(s.label), label=s.label, department=s.department,
                min_amount=s.min_amount, can_override=s.can_override,
                override_limit=s.override_limit,
            )
            for s in body.custom_steps
        ]
        wf = rq.RequisitionWorkflow(org_id=ctx.org_id, steps=steps)
    else:
        wf = rq.default_workflow(ctx.org_id, size=body.workflow_size)

    wf.currency = body.currency.strip().upper()[:3] or "NGN"
    wf.max_amount = body.max_amount
    wf.allowed_categories = [c.strip() for c in body.allowed_categories if c.strip()]
    wf.required_documents = [d.strip() for d in body.required_documents if d.strip()]

    try:
        rq.set_workflow(ctx.org_id, wf)
    except rq.RequisitionError as exc:
        # Departments are already saved at this point — say so, so the
        # wizard can go straight back to the workflow step rather than
        # making the admin redo everything.
        return SetupResult(ok=False, partial=True, departments=len(dept_defs),
                          error=str(exc))

    return SetupResult(ok=True, departments=len(dept_defs), steps=len(wf.steps))
