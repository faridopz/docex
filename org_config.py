"""
Client profiles — one codebase, one config file per organisation.

WHY THIS EXISTS
DOCex is sold as a consulting engagement: each client gets a system fitted to
their departments, approval chain, spend policy and grants. The temptation is
to fork the code per client. That is how you end up maintaining five
half-different products and fixing every bug five times. Instead:

    the ENGINE is shared and tested once;
    the CLIENT is a data file.

A profile is a plain dict (loaded from JSON or YAML) describing everything
that differs between organisations. `apply_profile()` writes it into the
org-scoped store — departments, workflow, policy, grants, first admin — and
`describe_org()` reads the live configuration back so you can diff a running
instance against its profile.

Onboarding a new client is therefore:

    1. copy profiles/_template.json → profiles/<client>.json
    2. fill in their answers from the discovery call
    3. DOCEX_ORG=<client> python3 org_config.py apply profiles/<client>.json

Nothing in the engines changes. If a client needs behaviour the engine can't
express as config, that's a feature request for the engine — built once,
available to every client, and gated behind a `features` flag if only some
should see it.

PROFILE SHAPE  (see profiles/_template.json for a commented example)
{
  "org_id": "neem",
  "name": "NEEM",
  "currency": "NGN",
  "departments": [ {key, name, description?, order?, is_final_authority?} ],
  "state_owners": { "compliance_review": "compliance", ... },
  "workflow": {
      "steps": [ {key, label, department, min_amount?, can_override?, override_limit?} ],
      "max_amount": 5000000,
      "allowed_categories": [...], "required_documents": [...],
      "forbidden_vendors": [...], "approved_vendors": [...],
      "duplicate_window_days": 30
  },
  "grants": [ {project_code, donor, title?, value?, start_date, end_date} ],
  "admin": { "email": "...", "name": "...", "password": "...", "department": "finance" },
  "features": { "kobo_sync": false, "tin_verification": false, ... }
}

Every section is optional except org_id. A missing section leaves that part of
the org untouched, so you can apply a profile that only updates the workflow.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import store

_CONFIG = "config"
_PROFILE_ID = "profile"          # the applied profile, kept for describe/diff
_FEATURES_ID = "features"


class ProfileError(ValueError):
    """A profile is malformed or internally inconsistent. Raised BEFORE any
    write, so a bad file never leaves an org half-configured."""


# ─── loading ────────────────────────────────────────────────────────────────


def load_profile(path: Path | str) -> dict:
    """Read a JSON (or YAML, if PyYAML is installed) profile from disk."""
    p = Path(path)
    if not p.exists():
        raise ProfileError(f"Profile not found: {p}")
    text = p.read_text()
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ProfileError("YAML profiles need PyYAML: pip install pyyaml") from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ProfileError("Profile must be a JSON/YAML object at the top level.")
    return data


# ─── validation ─────────────────────────────────────────────────────────────


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_profile(profile: dict) -> ValidationReport:
    """Check the profile is internally consistent. Pure — touches no storage.

    The checks here are the ones whose failure mode in production is a stuck
    payment nobody can see: a workflow step routed to a department that
    doesn't exist, a state owner naming a missing department, an override
    limit below the amount the step engages at.
    """
    rep = ValidationReport()
    org_id = str(profile.get("org_id") or "").strip()
    if not org_id:
        rep.errors.append("org_id is required.")
    else:
        try:
            store.require_org(org_id)
        except store.StoreError as exc:
            rep.errors.append(str(exc))

    depts = profile.get("departments") or []
    dept_keys: set[str] = set()
    for i, d in enumerate(depts):
        key = str(d.get("key") or "").strip()
        if not key:
            rep.errors.append(f"departments[{i}] is missing 'key'.")
            continue
        if key in dept_keys:
            rep.errors.append(f"Duplicate department key '{key}'.")
        dept_keys.add(key)
        if not d.get("name"):
            rep.warnings.append(f"Department '{key}' has no display name; key will be used.")

    # If the profile doesn't define departments, steps must route to whatever
    # the org already has. We can't see that here without touching storage, so
    # only cross-check when both sides are in the profile.
    known = dept_keys if depts else None

    for state, owner in (profile.get("state_owners") or {}).items():
        if known is not None and owner not in known:
            rep.errors.append(f"state_owners['{state}'] → '{owner}' is not a defined department.")

    wf = profile.get("workflow") or {}
    steps = wf.get("steps") or []
    step_keys: set[str] = set()
    for i, s in enumerate(steps):
        key = str(s.get("key") or "").strip()
        if not key:
            rep.errors.append(f"workflow.steps[{i}] is missing 'key'.")
            continue
        if key in step_keys:
            rep.errors.append(f"Duplicate workflow step key '{key}'.")
        step_keys.add(key)
        dept = str(s.get("department") or "").strip()
        if not dept:
            rep.errors.append(f"Workflow step '{key}' has no department.")
        elif known is not None and dept not in known:
            rep.errors.append(f"Workflow step '{key}' routes to unknown department '{dept}'.")
        min_amt = float(s.get("min_amount") or 0)
        limit = s.get("override_limit")
        if s.get("can_override") and limit is not None and float(limit) < min_amt:
            rep.errors.append(
                f"Workflow step '{key}': override_limit ({limit}) is below min_amount "
                f"({min_amt}) — it could never override anything it sees."
            )
    if wf and not steps:
        rep.warnings.append("workflow has no steps; the org will fall back to defaults.")

    max_amount = wf.get("max_amount")
    if max_amount is not None and float(max_amount) <= 0:
        rep.errors.append("workflow.max_amount must be positive if set.")

    for i, g in enumerate(profile.get("grants") or []):
        if not g.get("project_code"):
            rep.errors.append(f"grants[{i}] is missing 'project_code'.")
        if not g.get("donor"):
            rep.errors.append(f"grants[{i}] is missing 'donor'.")
        sd, ed = g.get("start_date"), g.get("end_date")
        if sd and ed and str(ed) < str(sd):
            rep.errors.append(f"grants[{i}] ends before it starts ({sd} → {ed}).")

    admin = profile.get("admin")
    if admin:
        if "@" not in str(admin.get("email") or ""):
            rep.errors.append("admin.email must be a valid email.")
        if len(str(admin.get("password") or "")) < 6:
            rep.errors.append("admin.password must be at least 6 characters.")
        dept = str(admin.get("department") or "").strip()
        if not dept:
            rep.errors.append("admin.department is required.")
        elif known is not None and dept not in known:
            rep.errors.append(f"admin.department '{dept}' is not a defined department.")

    return rep


# ─── applying ───────────────────────────────────────────────────────────────


@dataclass
class ApplyResult:
    org_id: str
    departments: int = 0
    workflow: bool = False
    grants_added: int = 0
    grants_skipped: int = 0
    admin_created: bool = False
    admin_existing: bool = False
    features: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def apply_profile(profile: dict, *, dry_run: bool = False) -> ApplyResult:
    """Write a validated profile into the org's store.

    Idempotent where it can be: departments and workflow are replaced
    wholesale (the profile is the source of truth); grants are added only if
    no agreement with that project_code exists; the admin is created only if
    the email is new. Re-applying an unchanged profile is therefore a no-op.
    """
    rep = validate_profile(profile)
    if not rep.ok:
        raise ProfileError("Profile is invalid:\n  - " + "\n  - ".join(rep.errors))

    org_id = store.require_org(profile["org_id"])
    res = ApplyResult(org_id=org_id, warnings=list(rep.warnings))
    if dry_run:
        return res

    import departments
    import requisitions
    from models import DepartmentDef

    # 1. Departments + state routing.
    depts = profile.get("departments")
    if depts:
        defs = [DepartmentDef(
            key=d["key"], name=d.get("name") or d["key"],
            description=d.get("description", ""), order=int(d.get("order", 100)),
            is_final_authority=bool(d.get("is_final_authority", False)),
        ) for d in depts]
        owners = profile.get("state_owners") or departments._DEFAULT_STATE_OWNERS
        # Drop default owners that name departments this client doesn't have,
        # rather than failing — a client with no "program" dept still boots.
        keys = {d.key for d in defs}
        owners = {s: o for s, o in owners.items() if o in keys}
        departments.replace_all(defs, owners, org_id=org_id)
        res.departments = len(defs)

    # 2. Workflow + policy.
    wf = profile.get("workflow")
    if wf:
        steps = [requisitions.WorkflowStep(**s) for s in (wf.get("steps") or [])]
        current = requisitions.get_workflow(org_id)
        new = requisitions.RequisitionWorkflow(
            org_id=org_id,
            steps=steps or current.steps,
            currency=profile.get("currency") or wf.get("currency") or current.currency,
            max_amount=wf.get("max_amount", current.max_amount),
            allowed_categories=wf.get("allowed_categories", current.allowed_categories),
            forbidden_vendors=wf.get("forbidden_vendors", current.forbidden_vendors),
            approved_vendors=wf.get("approved_vendors", current.approved_vendors),
            required_documents=wf.get("required_documents", current.required_documents),
            duplicate_window_days=int(wf.get("duplicate_window_days", current.duplicate_window_days)),
        )
        bad = requisitions.unroutable_steps(org_id, new)
        if bad:
            raise ProfileError("Workflow routes to departments that don't exist: " + "; ".join(bad))
        requisitions.set_workflow(org_id, new)
        res.workflow = True

    # 3. Grants (add-only).
    grants_in = profile.get("grants") or []
    if grants_in:
        import grants
        existing = {a.project_code for a in grants.list_agreements(org_id)}
        for g in grants_in:
            if g["project_code"] in existing:
                res.grants_skipped += 1
                continue
            grants.add_agreement(
                org_id,
                donor=g["donor"], project_code=g["project_code"],
                title=g.get("title", ""), value=float(g.get("value") or 0),
                currency=g.get("currency") or profile.get("currency") or "NGN",
                start_date=g.get("start_date"), end_date=g.get("end_date"),
                status=g.get("status", "active"),
            )
            res.grants_added += 1

    # 4. First admin (create-only; never resets a password from a profile).
    admin = profile.get("admin")
    if admin:
        import auth
        if auth.get_by_email(admin["email"], org_id):
            res.admin_existing = True
        else:
            auth.create_user(
                email=admin["email"], name=admin.get("name", ""),
                password=admin["password"], department=admin["department"],
                role="admin", org_id=org_id,
            )
            res.admin_created = True

    # 5. Feature flags + the profile itself, for describe/diff later.
    features = dict(profile.get("features") or {})
    st = store.get_store()
    st.put(org_id, _CONFIG, _FEATURES_ID, {"features": features})
    safe = {k: v for k, v in profile.items() if k != "admin"}   # never persist a password
    st.put(org_id, _CONFIG, _PROFILE_ID, {"profile": safe})
    res.features = features
    return res


# ─── reading back ───────────────────────────────────────────────────────────


def feature_enabled(org_id: str, name: str, default: bool = False) -> bool:
    """Engines and routes gate client-specific behaviour on this. A feature
    that doesn't exist for an org is `default` — so new flags are opt-in."""
    raw = store.get_store().get(store.require_org(org_id), _CONFIG, _FEATURES_ID) or {}
    return bool((raw.get("features") or {}).get(name, default))


def describe_org(org_id: str) -> dict:
    """The org's LIVE configuration, in profile shape. Diff it against the
    profile file to see what was changed by hand since it was applied."""
    import departments
    import requisitions
    org = store.require_org(org_id)
    reg = departments.load(org)
    wf = requisitions.get_workflow(org)
    out: dict[str, Any] = {
        "org_id": org,
        "currency": wf.currency,
        "departments": [d.model_dump() for d in reg.departments],
        "state_owners": dict(reg.state_owners),
        "workflow": {
            "steps": [s.model_dump() for s in wf.steps],
            "max_amount": wf.max_amount,
            "allowed_categories": wf.allowed_categories,
            "required_documents": wf.required_documents,
            "forbidden_vendors": wf.forbidden_vendors,
            "approved_vendors": wf.approved_vendors,
            "duplicate_window_days": wf.duplicate_window_days,
        },
        "features": (store.get_store().get(org, _CONFIG, _FEATURES_ID) or {}).get("features", {}),
    }
    try:
        import grants
        out["grants"] = [{
            "project_code": a.project_code, "donor": a.donor, "title": a.title,
            "value": a.value, "start_date": a.start_date, "end_date": a.end_date,
            "status": a.status,
        } for a in grants.list_agreements(org)]
    except Exception:
        out["grants"] = []
    try:
        import auth
        out["users"] = len(auth.list_public(org))
    except Exception:
        out["users"] = None
    return out


# ─── CLI ────────────────────────────────────────────────────────────────────


def _cli(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Apply or inspect a DOCex client profile.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="validate + write a profile into the org")
    a.add_argument("profile")
    a.add_argument("--dry-run", action="store_true", help="validate only")
    v = sub.add_parser("validate", help="check a profile without touching storage")
    v.add_argument("profile")
    d = sub.add_parser("describe", help="print an org's live config as JSON")
    d.add_argument("org_id", nargs="?", default=None)
    args = p.parse_args(argv)

    # Same backend selection as api/main.py, so the CLI writes where the API reads.
    db = os.environ.get("DOCEX_DB", "").strip()
    if db:
        import store_sql
        store.set_store(store_sql.SqliteStore(db))

    if args.cmd in ("apply", "validate"):
        try:
            profile = load_profile(args.profile)
        except ProfileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        rep = validate_profile(profile)
        for w in rep.warnings:
            print(f"warning: {w}")
        for e in rep.errors:
            print(f"error: {e}")
        if not rep.ok:
            return 1
        if args.cmd == "validate":
            print(f"OK — profile for '{profile.get('org_id')}' is valid.")
            return 0
        try:
            res = apply_profile(profile, dry_run=args.dry_run)
        except ProfileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"OK — would apply to org '{res.org_id}'.")
            return 0
        print(f"Applied profile to org '{res.org_id}':")
        print(f"  departments : {res.departments or 'unchanged'}")
        print(f"  workflow    : {'updated' if res.workflow else 'unchanged'}")
        print(f"  grants      : +{res.grants_added} ({res.grants_skipped} already present)")
        if res.admin_created:
            print("  admin       : created")
        elif res.admin_existing:
            print("  admin       : already exists (password NOT changed)")
        if res.features:
            print(f"  features    : {', '.join(k for k, v in res.features.items() if v) or 'none on'}")
        return 0

    org = args.org_id or os.environ.get("DOCEX_ORG") or "default"
    print(json.dumps(describe_org(org), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
