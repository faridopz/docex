"""
The tests an auditor actually runs, run continuously instead of once a year.

The audit screen showed counts and a list of overridden checks. Counts are a
dashboard; an audit is a set of TESTS, each looking for a specific way money
goes wrong. This module runs those tests over an organisation's own records
and returns findings.

Every test here is DETERMINISTIC — arithmetic and pattern matching over stored
records, no model call anywhere. That is deliberate and it is the point: a
finding that an auditor cannot reproduce by hand is a finding they cannot put
in a report. Each one names the exact records it is about so it can be checked.

WHAT IS DELIBERATELY NOT HERE
=============================
Round-amount detection. Suspiciously round figures are a classic fraud
indicator in commercial AP, and in NGO work they are simply what a stipend is
— ₦20,000 each to forty participants. A test that is usually wrong teaches
people to ignore findings, which costs more than the test is worth.

Nothing here BLOCKS anything. These are observations for a human, not
controls. The controls are the deterministic policy checks on the requisition
itself, which run before money moves; this runs after, over the whole
population, looking for patterns a single payment cannot show.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import requisitions as rq
import store

Severity = Literal["high", "medium", "low"]

# How close to an approval threshold counts as "just under it". Five per cent
# is tight enough that ordinary pricing rarely trips it and loose enough to
# catch deliberate shaving.
_PROXIMITY_BAND = 0.05

# Outside these hours (in the org's own local time) an approval is worth a
# second look. Wide on purpose — finance teams work late at month end, and a
# test that fires on every 7pm approval is noise.
_WORK_START_HOUR = 6
_WORK_END_HOUR = 21


@dataclass
class Finding:
    code: str
    title: str
    severity: Severity
    detail: str                       # what was found, in plain words
    why: str                          # why an auditor cares
    refs: list[str] = field(default_factory=list)   # the records involved
    amount: float = 0.0               # value involved, where meaningful


@dataclass
class AuditReport:
    org_id: str
    generated_at: str
    requisitions_examined: int
    transactions_examined: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def by_severity(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    @property
    def clean(self) -> bool:
        return not self.findings


def _local(iso: str, offset_minutes: int) -> Optional[dt.datetime]:
    """Stored timestamps are UTC. Tests about working hours only mean anything
    in the org's own time, so the caller passes its offset — the same
    convention the period export uses (JavaScript's getTimezoneOffset sign)."""
    if not iso:
        return None
    try:
        stamp = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.replace(tzinfo=None) + (stamp.utcoffset() or dt.timedelta())
    return stamp - dt.timedelta(minutes=offset_minutes)


def _thresholds(wf: rq.RequisitionWorkflow) -> list[tuple[float, str]]:
    """Every amount at which this org's approval requirement changes."""
    out = [(float(s.min_amount), s.label or s.key)
           for s in wf.steps if float(s.min_amount or 0) > 0]
    if wf.max_amount:
        out.append((float(wf.max_amount), "the spend ceiling"))
    return sorted(set(out))


# ─── the tests ──────────────────────────────────────────────────────────────


def _test_chain_integrity(reqs: list[rq.Requisition]) -> list[Finding]:
    """The most serious thing this system can report: a record whose history
    has been altered outside the application."""
    broken = [r for r in reqs if not rq.verify_audit_chain(r)]
    if not broken:
        return []
    return [Finding(
        code="CHAIN_BROKEN",
        title="Audit trail does not verify",
        severity="high",
        detail=f"{len(broken)} requisition(s) have a hash chain that no longer verifies.",
        why=("The audit log is append-only and hash-chained, so this means the "
             "stored history was changed by something other than this application. "
             "Nothing else in this report can be relied on for these records."),
        refs=[r.ref for r in broken],
        amount=round(sum(r.amount for r in broken), 2),
    )]


def _test_unexplained_exceptions(txns: list[rq.TransactionRecord]) -> list[Finding]:
    """A blocking check released without a written reason."""
    bad: list[rq.TransactionRecord] = []
    value = 0.0
    for txn in txns:
        for c in txn.checks:
            if c.overridden and not (c.override_reason or "").strip():
                bad.append(txn)
                value += txn.amount
                break
    if not bad:
        return []
    return [Finding(
        code="UNEXPLAINED_EXCEPTION",
        title="Policy exception with no written reason",
        severity="high",
        detail=f"{len(bad)} payment(s) released a blocking policy check without a reason.",
        why=("Every exception has to survive a question twelve months later. One "
             "without a written justification is the finding an auditor writes up "
             "first, because there is nothing to evaluate."),
        refs=[t.requisition_ref for t in bad],
        amount=round(value, 2),
    )]


def _test_segregation_of_duties(reqs: list[rq.Requisition]) -> list[Finding]:
    """One person approving at more than one stage of the same requisition.

    The engine already refuses to let someone approve their OWN requisition,
    and refuses an approver from the wrong department. Neither stops the same
    individual signing at two different stages of one chain — which defeats
    the point of having stages, and is a standard segregation-of-duties
    finding.
    """
    hits: list[tuple[str, str, int]] = []
    for req in reqs:
        by_actor: dict[str, set[str]] = {}
        for a in req.approvals:
            if a.decision != rq.Decision.APPROVED or not a.actor:
                continue
            by_actor.setdefault(a.actor, set()).add(a.step)
        for actor, steps in by_actor.items():
            if len(steps) > 1:
                hits.append((req.ref, actor, len(steps)))
    if not hits:
        return []
    who = ", ".join(sorted({f"{actor} ({n} stages)" for _, actor, n in hits})[:5])
    return [Finding(
        code="SOD_SAME_APPROVER",
        title="One person approved at multiple stages",
        severity="high",
        detail=f"{len(hits)} requisition(s) were approved at more than one stage by "
               f"the same person: {who}.",
        why=("Separate approval stages exist so more than one person sees the "
             "payment. When one individual signs two of them the control is "
             "nominal — it should be a delegation on the record, or a different "
             "approver."),
        refs=sorted({ref for ref, _, _ in hits}),
    )]


def _test_shared_bank_accounts(reqs: list[rq.Requisition]) -> list[Finding]:
    """One bank account receiving money under more than one payee name.

    Occasionally legitimate — a trader using a personal account, a spouse
    collecting for a beneficiary. Always worth an explanation, because it is
    also exactly what a fabricated beneficiary list looks like.
    """
    names_by_account: dict[str, set[str]] = {}
    refs_by_account: dict[str, set[str]] = {}
    for req in reqs:
        rows = [(p.name, p.account_number) for p in req.payees]
        if req.vendor_account:
            rows.append((req.vendor_name, req.vendor_account))
        for name, account in rows:
            account = (account or "").strip()
            name = (name or "").strip().lower()
            if not account or not name:
                continue
            names_by_account.setdefault(account, set()).add(name)
            refs_by_account.setdefault(account, set()).add(req.ref)

    shared = {acct: names for acct, names in names_by_account.items() if len(names) > 1}
    if not shared:
        return []
    refs: set[str] = set()
    for acct in shared:
        refs |= refs_by_account.get(acct, set())
    example = next(iter(shared.items()))
    return [Finding(
        code="SHARED_BANK_ACCOUNT",
        title="One account paid under several names",
        severity="high",
        detail=(f"{len(shared)} bank account(s) received payments under more than one "
                f"payee name — for example account ending {example[0][-4:]} paid "
                f"{len(example[1])} different names."),
        why=("A single account collecting for several people is how a fabricated "
             "payee list is usually built. It is sometimes genuine, and it should "
             "always have been explained before payment rather than after."),
        refs=sorted(refs),
    )]


def _test_threshold_proximity(
    reqs: list[rq.Requisition], wf: rq.RequisitionWorkflow,
) -> list[Finding]:
    """Payments landing just under the amount that would have required more
    approval. The clearest signal of a chain being worked around, and the one
    thing a spreadsheet will never surface on its own."""
    thresholds = _thresholds(wf)
    if not thresholds:
        return []
    hits: list[tuple[str, float, str]] = []
    for req in reqs:
        for value, label in thresholds:
            floor = value * (1 - _PROXIMITY_BAND)
            if floor <= req.amount < value:
                hits.append((req.ref, req.amount, label))
                break
    if not hits:
        return []
    return [Finding(
        code="THRESHOLD_PROXIMITY",
        title="Payments sitting just below an approval threshold",
        severity="medium",
        detail=(f"{len(hits)} payment(s) fall within {int(_PROXIMITY_BAND * 100)}% "
                "below a threshold that would have required further approval."),
        why=("Amounts clustering just under a limit is the standard pattern for "
             "avoiding an approval stage. Individually each is compliant, which is "
             "exactly why it only shows up when the whole population is examined."),
        refs=[ref for ref, _, _ in hits],
        amount=round(sum(a for _, a, _ in hits), 2),
    )]


def _test_split_payments(
    reqs: list[rq.Requisition], wf: rq.RequisitionWorkflow,
) -> list[Finding]:
    """The same payee paid several times in a short window, where the total
    would have crossed a threshold that no single payment did."""
    thresholds = _thresholds(wf)
    if not thresholds:
        return []
    window = dt.timedelta(days=wf.duplicate_window_days or 30)

    by_vendor: dict[str, list[rq.Requisition]] = {}
    for req in reqs:
        key = (req.vendor_name or "").strip().lower()
        if key:
            by_vendor.setdefault(key, []).append(req)

    hits: list[tuple[str, list[str], float, str]] = []
    for vendor, group in by_vendor.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda r: r.submitted_at or "")
        for i, anchor in enumerate(ordered):
            start = _local(anchor.submitted_at, 0)
            if start is None:
                continue
            cluster = [anchor]
            for other in ordered[i + 1:]:
                when = _local(other.submitted_at, 0)
                if when is None or when - start > window:
                    break
                cluster.append(other)
            if len(cluster) < 2:
                continue
            total = sum(r.amount for r in cluster)
            largest = max(r.amount for r in cluster)
            crossed = next((lbl for val, lbl in thresholds if largest < val <= total), None)
            if crossed:
                hits.append((vendor, [r.ref for r in cluster], total, crossed))
                break                       # one finding per vendor is enough
    if not hits:
        return []
    refs: list[str] = []
    for _, group_refs, _, _ in hits:
        refs.extend(group_refs)
    return [Finding(
        code="SPLIT_PAYMENT",
        title="Payments to one payee that together cross a threshold",
        severity="medium",
        detail=(f"{len(hits)} payee(s) received several payments within "
                f"{wf.duplicate_window_days or 30} days which individually stayed "
                "below an approval threshold but together exceeded it."),
        why=("Splitting one purchase into several smaller payments is the most "
             "common way an approval limit is circumvented. Each payment passes "
             "its own checks, so only looking across them finds it."),
        refs=refs,
        amount=round(sum(total for _, _, total, _ in hits), 2),
    )]


def _test_skipped_stages(reqs: list[rq.Requisition]) -> list[Finding]:
    """A stage passed over by an escalation and never decided."""
    hits = [r for r in reqs
            if any(e.event == "rerouted" and "skipping" in (e.detail or "")
                   for e in r.audit_log)]
    if not hits:
        return []
    return [Finding(
        code="SKIPPED_STAGE",
        title="Approval stages passed over by an escalation",
        severity="medium",
        detail=f"{len(hits)} requisition(s) were escalated past a stage that never decided them.",
        why=("Escalation is legitimate and each one carries a written reason, but a "
             "stage that never saw the payment did not perform its check. Worth "
             "reading the reasons together rather than one at a time."),
        refs=[r.ref for r in hits],
        amount=round(sum(r.amount for r in hits), 2),
    )]


def _test_out_of_hours(
    reqs: list[rq.Requisition], offset_minutes: int,
) -> list[Finding]:
    """Approvals recorded at night or at the weekend, in the org's own time."""
    hits: list[str] = []
    for req in reqs:
        for a in req.approvals:
            when = _local(a.at, offset_minutes)
            if when is None:
                continue
            if when.weekday() >= 5 or not (_WORK_START_HOUR <= when.hour < _WORK_END_HOUR):
                hits.append(req.ref)
                break
    if not hits:
        return []
    return [Finding(
        code="OUT_OF_HOURS",
        title="Approvals recorded outside working hours",
        severity="low",
        detail=f"{len(hits)} requisition(s) were approved at a weekend or outside "
               f"{_WORK_START_HOUR}:00–{_WORK_END_HOUR}:00.",
        why=("Usually nothing — finance teams work late at month end. It matters "
             "when it correlates with something else in this report, which is why "
             "it is listed rather than hidden."),
        refs=sorted(set(hits)),
    )]


def _test_reference_gaps(reqs: list[rq.Requisition]) -> list[Finding]:
    """Missing numbers in the requisition sequence."""
    numbers: list[int] = []
    for req in reqs:
        match = re.search(r"(\d+)\s*$", req.ref or "")
        if match:
            numbers.append(int(match.group(1)))
    if len(numbers) < 2:
        return []
    numbers.sort()
    present = set(numbers)
    missing = [n for n in range(numbers[0], numbers[-1] + 1) if n not in present]

    # A gap at the START of the sequence is invisible to a min-to-max scan —
    # if REQ-0001 was discarded, the lowest surviving number is 2 and nothing
    # looks wrong. The counter always begins at 1, so a sequence that does not
    # is itself the finding. Reported as a count rather than enumerated,
    # because an instance seeded with historical data could legitimately start
    # at 500 and listing 499 "missing" numbers would be worse than useless.
    leading = numbers[0] - 1 if numbers[0] > 1 else 0

    if not missing and not leading:
        return []

    parts: list[str] = []
    if missing:
        shown = ", ".join(str(n) for n in missing[:10])
        parts.append(
            f"{len(missing)} reference number(s) missing between {numbers[0]} and "
            f"{numbers[-1]}: {shown}{'…' if len(missing) > 10 else ''}"
        )
    if leading:
        parts.append(
            f"the sequence starts at {numbers[0]} rather than 1, so {leading} "
            "earlier number(s) are unaccounted for"
        )

    return [Finding(
        code="REFERENCE_GAP",
        title="Gaps in the requisition sequence",
        severity="low",
        detail="; ".join(parts) + ".",
        why=("Normally a draft that was discarded before submission, which is "
             "fine. An auditor checking completeness will ask anyway, and having "
             "the answer ready is the difference between a query and a finding."),
    )]


# ─── the entry point ────────────────────────────────────────────────────────


def run_audit_tests(org_id: str, *, tz_offset_minutes: int = 0) -> AuditReport:
    """Run every test over this organisation's records.

    Findings come back ordered by severity, because an auditor reads from the
    top and a broken hash chain must never sit below a weekend approval.
    """
    org = store.require_org(org_id)
    reqs = rq.list_requisitions(org)
    txns = rq.list_transactions(org)
    wf = rq.get_workflow(org)

    findings: list[Finding] = []
    findings += _test_chain_integrity(reqs)
    findings += _test_unexplained_exceptions(txns)
    findings += _test_segregation_of_duties(reqs)
    findings += _test_shared_bank_accounts(reqs)
    findings += _test_threshold_proximity(reqs, wf)
    findings += _test_split_payments(reqs, wf)
    findings += _test_skipped_stages(reqs)
    findings += _test_out_of_hours(reqs, tz_offset_minutes)
    findings += _test_reference_gaps(reqs)

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f.severity, 3))

    return AuditReport(
        org_id=org,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        requisitions_examined=len(reqs),
        transactions_examined=len(txns),
        findings=findings,
    )
