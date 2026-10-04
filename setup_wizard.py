"""
The setup wizard: six plain questions that set up any organisation's
payment approvals, with no settings file and no developer.

    load_answers(org)          what the org's current setup looks like, as answers
    preview(org, answers)      the route and documents those answers produce,
                               plus anything that would stop them being saved
    apply(org, answers, actor) save them (all or nothing)

The six questions, each pre-filled with the most common NGO arrangement:

  1. Your organisation     name, currency, letterhead address
  2. Your departments      Programmes, Finance, Admin & HR, Executive Director
  3. Who approves first?   the requester's own manager (budget holder),
                           one fixed department, or nobody
  4. Who checks it against policy?   usually Finance; may they release a
                           failing check with a written reason, up to what?
  5. Who signs off after that, in order, and from what amount?
  6. What paperwork?       standard documents, quotes from an amount (for
                           purchases), a tender from a higher amount

What the wizard deliberately does NOT own, and therefore never touches:
per-category document packs, the category list of an org that has one, copy
rules, grants, feature switches (except a new org's first set), the advance
policy, voucher numbering and signature lines. Re-running the wizard on an
organisation set up another way (NEEM's settings file) changes only what the
six questions cover. That rule is what makes it safe to hand to any admin.

One engine, one config per client: this writes the same records a profile
does, through the same models, and never names a client.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import store

_NUM_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
QUOTE_DOC = re.compile(r"^(two|three|four|five|six)_quotes$")
TENDER_DOC = "tender_minutes"

# A new organisation's starting point. Suggestions the admin confirms, not
# policy: no spending limit and no release authority is switched on for them.
DEFAULT_DEPARTMENTS = [
    {"key": "program", "name": "Programmes"},
    {"key": "finance", "name": "Finance"},
    {"key": "admin", "name": "Admin & HR"},
    {"key": "ed", "name": "Executive Director"},
]
DEFAULT_CATEGORIES = [
    "supplies", "equipment", "venue", "consultancy", "training", "transport",
    "advance", "dsa", "per_diem", "stipends", "utilities", "rent", "other",
]
# Things that are bought from a supplier, and so normally need quotes.
DEFAULT_PURCHASE_CATEGORIES = ["supplies", "equipment", "venue", "consultancy", "training", "transport"]
DEFAULT_DOCUMENTS = ["memo", "invoice"]
# The switches a new organisation starts with: the payment-request workflow
# itself. Everything else stays off until an admin turns it on in Settings.
NEW_ORG_FEATURES = {
    "requisition_attachments": True, "requisition_hold": True, "requisition_export": True,
    "voucher_export": True, "payee_schedule_export": True, "multi_payee_requisitions": True,
    "documents_require_files": True, "vendor_register": True,
    "projects": True, "expense_claims": True,
}


class WizardError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def default_answers() -> dict:
    return {
        "org_name": "",
        "currency": "NGN",
        "address_lines": [],
        "rc_number": "",
        "departments": copy.deepcopy(DEFAULT_DEPARTMENTS),
        "first_approver": "budget_holder",     # budget_holder | department | none
        "first_department": "",
        "policy_department": "finance",
        "policy_can_release": False,
        "policy_release_limit": None,
        "signoffs": [{"department": "ed", "from_amount": 0, "can_release": False, "release_limit": None}],
        "documents": list(DEFAULT_DOCUMENTS),
        "quotes_count": 3,
        "quotes_from": None,
        "tender_from": None,
        "quote_categories": list(DEFAULT_PURCHASE_CATEGORIES),
        "max_amount": None,
    }


# ─── reading the current setup back as answers ───────────────────────────────


def load_answers(org_id: str) -> dict:
    """The org's setup as wizard answers, so an admin edits what they have.

    A brand-new organisation (nothing saved yet) gets the defaults."""
    import departments
    import payment_voucher
    import requisitions as rq

    org = store.require_org(org_id)
    if not (departments.has_registry_configured(org) and rq.has_workflow_configured(org)):
        return default_answers()

    a = default_answers()
    wf = rq.get_workflow(org)
    a["currency"] = wf.currency
    a["max_amount"] = wf.max_amount
    a["departments"] = [{"key": d.key, "name": d.name} for d in departments.list_departments(org)]
    raw_t = store.get_store().get(org, payment_voucher._CONFIG, payment_voucher._TEMPLATE_ID) or {}
    head = raw_t.get("letterhead") or {}
    a["org_name"] = head.get("org_name") or ""
    a["address_lines"] = list(head.get("address_lines") or [])
    a["rc_number"] = head.get("rc_number") or ""

    steps = list(wf.steps)
    a["first_approver"], a["first_department"] = "none", ""
    if steps and steps[0].requester_department:
        a["first_approver"] = "budget_holder"
        steps = steps[1:]
    elif len(steps) >= 2 and not steps[0].can_override and steps[1].can_override:
        # A fixed first approver ahead of the step that holds release authority.
        a["first_approver"], a["first_department"] = "department", steps[0].department
        steps = steps[1:]
    if steps:
        p = steps[0]
        a["policy_department"] = p.department
        a["policy_can_release"] = p.can_override
        a["policy_release_limit"] = p.override_limit if p.can_override else None
        a["signoffs"] = [{"department": s.department, "from_amount": s.min_amount,
                          "can_release": s.can_override,
                          "release_limit": s.override_limit if s.can_override else None}
                         for s in steps[1:]]
    else:
        a["signoffs"] = []

    a["documents"] = list(wf.required_documents)
    a["quotes_from"] = a["tender_from"] = None
    for band in wf.documents_by_amount:
        if len(band.documents) != 1:
            continue                     # a combined band belongs to another setup; kept as it is
        for d in band.documents:
            m = QUOTE_DOC.match(d)
            if m and a["quotes_from"] is None:
                a["quotes_from"] = band.min_amount
                a["quotes_count"] = next(n for n, w in _NUM_WORDS.items() if w == m.group(1))
                a["quote_categories"] = list(band.categories)
            elif d == TENDER_DOC and a["tender_from"] is None:
                a["tender_from"] = band.min_amount
    if a["quotes_from"] is None:
        cats = wf.allowed_categories or DEFAULT_CATEGORIES
        a["quote_categories"] = [c for c in DEFAULT_PURCHASE_CATEGORIES if c in cats]
    return a


# ─── turning answers into a setup ────────────────────────────────────────────


@dataclass
class Plan:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    departments: list = field(default_factory=list)       # DepartmentDef
    workflow: Any = None                                   # RequisitionWorkflow
    letterhead: dict = field(default_factory=dict)
    new_org: bool = False


def _money(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _fmt(amount: float, currency: str) -> str:
    sym = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€", "KES": "KSh ", "GHS": "GH₵"}.get(currency, currency + " ")
    return f"{sym}{amount:,.0f}"


def _plan(org_id: str, answers: dict) -> Plan:
    import departments
    import requisitions as rq
    from models import DepartmentDef

    org = store.require_org(org_id)
    a = {**default_answers(), **(answers or {})}
    plan = Plan(new_org=not (departments.has_registry_configured(org) and rq.has_workflow_configured(org)))
    err = plan.errors.append

    currency = (str(a.get("currency") or "NGN").strip().upper() or "NGN")[:3]

    # 2. departments — keys kept for existing ones, made from the name for new ones
    existing = {d.key: d for d in departments.list_departments(org)} if not plan.new_org else {}
    by_name: dict[str, str] = {}
    seen: set[str] = set()
    for i, d in enumerate(a.get("departments") or []):
        name = str((d or {}).get("name") or "").strip()
        if not name:
            err(f"Department {i + 1} needs a name.")
            continue
        try:
            key = departments.slugify(str(d.get("key") or "") or name)
        except Exception:
            err(f"'{name}' can't be used as a department name.")
            continue
        if key in seen:
            err(f"Two departments are called '{name}'.")
            continue
        seen.add(key)
        by_name[name.lower()] = key
        old = existing.get(key)
        plan.departments.append(DepartmentDef(
            key=key, name=name, order=(old.order if old else 10 * (i + 1)),
            description=(old.description if old else ""),
            is_final_authority=bool(old.is_final_authority) if old else False))
    if not plan.departments:
        err("Add at least one department.")

    def dept(ref: str, what: str) -> str:
        ref = str(ref or "").strip()
        if not ref:
            err(f"Choose {what}.")
            return ""
        if ref in seen:
            return ref
        if ref.lower() in by_name:
            return by_name[ref.lower()]
        err(f"{what[0].upper() + what[1:]}: '{ref}' is not one of your departments.")
        return ""

    # 3–5. the approval route, reusing the keys and labels of steps that already exist
    cur = rq.get_workflow(org)
    old_steps = list(cur.steps) if not plan.new_org else []
    used: set[str] = set()

    def reuse(match, key: str, label: str) -> tuple[str, str]:
        for s in old_steps:
            if s.key not in used and match(s):
                used.add(s.key)
                return s.key, s.label or label
        k, n = key, 2
        while k in used or any(s.key == k for s in old_steps):
            k, n = f"{key}-{n}", n + 1
        used.add(k)
        return k, label

    names = {d.key: d.name for d in plan.departments}
    steps: list = []
    first = str(a.get("first_approver") or "none")
    if first == "budget_holder":
        k, lab = reuse(lambda s: s.requester_department, "budget-holder", "Budget holder approval")
        steps.append(rq.WorkflowStep(key=k, label=lab, requester_department=True))
    elif first == "department":
        d = dept(a.get("first_department"), "who approves first")
        if d:
            k, lab = reuse(lambda s, d=d: not s.requester_department and s.department == d and s.min_amount == 0
                           and not s.can_override, d, f"{names.get(d, d)} approval")
            steps.append(rq.WorkflowStep(key=k, label=lab, department=d))
    elif first != "none":
        err("Choose who approves first.")

    pol = dept(a.get("policy_department"), "who checks requests against policy")
    if pol:
        can = bool(a.get("policy_can_release"))
        lim = _money(a.get("policy_release_limit")) if can else None
        if can and lim is not None and lim <= 0:
            err("The policy check's release limit must be more than zero, or left blank for no limit.")
        k, lab = reuse(lambda s: not s.requester_department and s.department == pol, pol,
                       f"{names.get(pol, pol)} review")
        steps.append(rq.WorkflowStep(key=k, label=lab, department=pol, can_override=can, override_limit=lim))

    last_from = 0.0
    for i, so in enumerate(a.get("signoffs") or []):
        d = dept((so or {}).get("department"), f"sign-off {i + 1}")
        frm = _money(so.get("from_amount")) or 0.0
        if frm < 0:
            err(f"Sign-off {i + 1}: the amount can't be negative.")
        if frm < last_from:
            err(f"Sign-off {i + 1} starts at a lower amount than the one before it; list them from smallest to largest.")
        last_from = max(last_from, frm)
        can = bool(so.get("can_release"))
        lim = _money(so.get("release_limit")) if can else None
        if can and lim is not None and lim < frm:
            err(f"Sign-off {i + 1}: the release limit is below the amount it starts at, so it could never be used.")
        if not d:
            continue
        k, lab = reuse(lambda s, d=d: not s.requester_department and s.department == d, d,
                       f"{names.get(d, d)} approval")
        steps.append(rq.WorkflowStep(key=k, label=lab, department=d, min_amount=frm,
                                     can_override=can, override_limit=lim))

    if plan.new_org and steps and not steps[-1].requester_department:
        for d in plan.departments:
            d.is_final_authority = d.key == steps[-1].department

    depts_in_steps = [s.department for s in steps if not s.requester_department]
    if len(depts_in_steps) != len(set(depts_in_steps)):
        err("A department appears twice in the approval route. Each department can hold one step.")
    if first == "department" and steps and pol and steps[0].department == pol:
        err("The first approver and the policy check are the same department; choose 'Nobody' for the first question instead.")

    # 6. paperwork
    wf = copy.deepcopy(cur) if not plan.new_org else rq.RequisitionWorkflow(org_id=org)
    wf.steps = steps
    wf.currency = currency
    wf.max_amount = _money(a.get("max_amount"))
    if wf.max_amount is not None and wf.max_amount <= 0:
        err("The largest single payment must be more than zero, or left blank.")
    docs = []
    for d in a.get("documents") or []:
        d = re.sub(r"[^a-z0-9]+", "_", str(d).strip().lower()).strip("_")
        if d and d not in docs:
            docs.append(d)
    wf.required_documents = docs
    if not wf.allowed_categories:
        wf.allowed_categories = list(DEFAULT_CATEGORIES)

    # Only the wizard's own bands are replaced; any other band (a committee
    # recommendation, say) set up another way is kept exactly as it was.
    def is_ours(b) -> bool:
        return len(b.documents) == 1 and bool(QUOTE_DOC.match(b.documents[0]) or b.documents[0] == TENDER_DOC)
    kept = [b for b in wf.documents_by_amount if not is_ours(b)]
    old_ours = [b for b in wf.documents_by_amount if is_ours(b)]

    def label_for(docs: list[str], frm: float, cats: list[str], fallback: str) -> str:
        # Unchanged band: keep the organisation's own wording.
        for b in old_ours:
            if b.documents == docs and b.min_amount == frm and b.categories == cats and b.label:
                return b.label
        return fallback
    ours = []
    qcount = int(a.get("quotes_count") or 3)
    if qcount not in _NUM_WORDS:
        err("Number of quotes must be between 2 and 6.")
        qcount = 3
    qfrom, tfrom = _money(a.get("quotes_from")), _money(a.get("tender_from"))
    cats = [c for c in (a.get("quote_categories") or []) if c]
    unknown = [c for c in cats if wf.allowed_categories and c not in wf.allowed_categories]
    if unknown:
        err("Quotes are set for categories you don't have: " + ", ".join(unknown) + ".")
    if qfrom is not None:
        if qfrom <= 0:
            err("Quotes: the amount must be more than zero.")
        qdocs = [f"{_NUM_WORDS[qcount]}_quotes"]
        ours.append(rq.AmountDocuments(min_amount=qfrom, documents=qdocs, categories=cats,
                                       label=label_for(qdocs, qfrom, cats,
                                                       f"{qcount} quotations from {_fmt(qfrom, currency)}")))
    if tfrom is not None:
        if qfrom is not None and tfrom <= qfrom:
            err("The tender amount must be higher than the quotes amount.")
        ours.append(rq.AmountDocuments(min_amount=tfrom, documents=[TENDER_DOC], categories=cats,
                                       label=label_for([TENDER_DOC], tfrom, cats,
                                                       f"Competitive tender from {_fmt(tfrom, currency)}")))
    wf.documents_by_amount = sorted(kept + ours, key=lambda b: b.min_amount)
    plan.workflow = wf

    # 1. letterhead
    org_name = str(a.get("org_name") or "").strip()
    if not org_name:
        err("Enter your organisation's name.")
    plan.letterhead = {"org_name": org_name,
                       "address_lines": [str(x).strip() for x in (a.get("address_lines") or []) if str(x).strip()],
                       "rc_number": str(a.get("rc_number") or "").strip()}

    # ── would saving this strand anything? ──
    if not plan.new_org:
        import auth
        removed = set(existing) - seen
        for k in sorted(removed):
            people = [u for u in auth.list_public(org) if getattr(u, "department", None) == k]
            if people:
                err(f"'{existing[k].name}' still has {len(people)} people in it. Move them to another "
                    "department in Settings → People first.")
        keys_now = {s.key for s in steps}
        waiting = [r for r in rq.list_requisitions(org)
                   if r.status in (rq.ReqStatus.IN_REVIEW, rq.ReqStatus.ON_HOLD)
                   and r.current_step and r.current_step not in keys_now]
        if waiting:
            gone = sorted({r.current_step for r in waiting})
            err(f"{len(waiting)} request(s) are waiting at a step this would remove ({', '.join(gone)}): "
                + ", ".join(r.ref for r in waiting[:5]) + ". Finish or return them first.")

    if not steps:
        plan.warnings.append("No approval steps: every request would be approved the moment it is sent.")
    elif not any(s.can_override for s in steps):
        plan.warnings.append("Nobody can release a failing check, so any request that fails one must be "
                             "returned and fixed. That's the strictest setting, and a fine one.")
    return plan


def _route_lines(plan: Plan) -> list[dict]:
    """The route for each amount band, in words."""
    import requisitions as rq
    wf = plan.workflow
    if wf is None:
        return []
    names = {d.key: d.name for d in plan.departments}
    edges = sorted({0.0, *[s.min_amount for s in wf.steps if s.min_amount]})
    out = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] - 1 if i + 1 < len(edges) else None
        chain = []
        for s in rq._steps_for(wf, lo):
            who = "The requester's own manager" if s.requester_department else names.get(s.department, s.department)
            chain.append({"label": s.label or s.key, "who": who,
                          "may_release": bool(s.can_override),
                          "release_limit": s.override_limit})
        span = (f"From {_fmt(lo, wf.currency)}" if hi is None else
                f"Up to {_fmt(hi, wf.currency)}" if lo == 0 else
                f"{_fmt(lo, wf.currency)} to {_fmt(hi, wf.currency)}")
        if len(edges) == 1:
            span = "Every request"
        out.append({"from": lo, "to": hi, "span": span, "steps": chain})
    return out


def _document_lines(plan: Plan) -> list[str]:
    import requisitions as rq
    wf = plan.workflow

    def lab(d: str) -> str:
        t = rq._doc_label(d)
        return t[:1].upper() + t[1:]
    if wf is None:
        return []
    out = []
    if wf.required_documents:
        out.append("Every request: " + ", ".join(lab(d) for d in wf.required_documents) + ".")
    for b in wf.documents_by_amount:
        scope = (" (" + ", ".join(c.replace("_", " ") for c in b.categories) + ")") if b.categories else ""
        out.append(f"From {_fmt(b.min_amount, wf.currency)}{scope}: "
                   + ", ".join(lab(d) for d in b.documents) + ".")
    return out


def preview(org_id: str, answers: dict) -> dict:
    plan = _plan(org_id, answers)
    return {"ok": not plan.errors, "errors": plan.errors, "warnings": plan.warnings,
            "route": _route_lines(plan), "documents": _document_lines(plan),
            "new_org": plan.new_org}


def apply(org_id: str, answers: dict, *, actor: str = "") -> dict:
    """Save the answers. Everything is checked first; nothing is written if
    any of it would fail."""
    import departments
    import org_config
    import payment_voucher
    import requisitions as rq

    org = store.require_org(org_id)
    plan = _plan(org, answers)
    if plan.errors:
        raise WizardError(plan.errors)
    reg = departments.load(org) if not plan.new_org else None
    owners = dict(reg.state_owners) if reg else {}
    keys = {d.key for d in plan.departments}
    owners = {s: d for s, d in owners.items() if d in keys}
    departments.replace_all(plan.departments, owners, org_id=org)
    rq.set_workflow(org, plan.workflow)

    raw_t = store.get_store().get(org, payment_voucher._CONFIG, payment_voucher._TEMPLATE_ID) or {}
    tpl = dict(raw_t)
    tpl["letterhead"] = {**(raw_t.get("letterhead") or {}), **plan.letterhead}
    if not raw_t:
        policy = next((s for s in plan.workflow.steps if s.can_override or not s.requester_department), None)
        roles = [{"label": "Prepared by", "source": "submitter"}]
        if policy is not None:
            roles.append({"label": "Checked by", "source": policy.department})
        for s in plan.workflow.steps:
            if not s.requester_department and s is not policy:
                roles.append({"label": "Approved by", "source": s.department})
        roles.append({"label": "Received by", "source": ""})
        tpl["signature_roles"] = roles
        tpl.setdefault("title", "Payment Voucher")
        initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", plan.letterhead["org_name"]))[:4].upper()
        tpl.setdefault("pv_org_prefix", initials or "PV")
        tpl.setdefault("pv_number_format", "{org}/{MONYY}/PV/{seq}")
    payment_voucher.set_template(org, tpl)

    if plan.new_org and not store.get_store().get(org, "config", "features"):
        # A new organisation gets the payment-approval product; the document
        # screening tools stay off until someone asks for them.
        org_config.set_features(org, **NEW_ORG_FEATURES)
        org_config.set_modules(org, ["compliance"])
        # People who release money sign in with a second factor from day one
        # (30 Sep audit, M3), with a week's grace to set it up. Existing
        # organisations keep whatever their administrator chose.
        import mfa
        mfa.set_policy(org, enabled=True, grace_days=7)

    store.get_store().put(org, "config", "setup_wizard", {
        "org_id": org, "saved_by": actor, "saved_at": rq._now_iso(), "answers": answers})
    return preview(org, answers) | {"saved": True}
