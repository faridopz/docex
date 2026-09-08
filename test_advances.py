"""
Advance retirement — the clock, and the consequence.

Every organisation says advances must be retired. Almost none write down what
happens when they are not, which is why almost none of them are.

NEEM did write it down, and unusually precisely (Finance Processes deck,
slide 10): retire within 7 days or 5 working days; failure means no further
payment to that individual; a collective default blocks the project's next
activity; persisting to month end means recovery from salary.

These tests are that ladder, rung by rung — plus the one that matters most:
the block has to bite on a NEW requisition, because a rule enforced only in a
month-end report is a rule nobody changes their behaviour for.

Run: python test_advances.py
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-adv-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import advances as adv  # noqa: E402

ORG = "advtest"
_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def raises(label: str, fn, *, contains: str = "") -> None:
    try:
        fn()
    except adv.AdvanceError as exc:
        check(label, not contains or contains.lower() in str(exc).lower(), str(exc))
    except Exception as exc:                                 # noqa: BLE001
        check(f"{label} (wrong exception: {type(exc).__name__}: {exc})", False)
    else:
        check(f"{label} (nothing raised)", False)


def clear(org: str = ORG) -> None:
    for r in store.get_store().list(org, "advances"):
        store.get_store().delete(org, "advances", r["id"])
    # Config records are keyed by a known id and carry no "id" field of their
    # own, so they are removed by name rather than by scanning.
    for record_id in ("advance_policy", "features"):
        try:
            store.get_store().delete(org, "config", record_id)
        except Exception:
            pass


def neem_policy(**over):
    """NEEM's actual policy, from their own deck."""
    return adv.set_policy(ORG, adv.AdvancePolicy(
        enabled=True, retirement_days=7, working_days=5,
        use_working_days=True, warn_days_before=2,
        block_staff_after_days=0, block_project_after_days=0,
        collective_default_count=2, recover_at_month_end=True, **over))


# ─── nothing is assumed ─────────────────────────────────────────────────────


def test_off_by_default() -> None:
    print("\nAn organisation that has not set a window is not policed")
    clear()
    p = adv.get_policy(ORG)
    check("disabled until configured", p.enabled is False)
    a = adv.issue(ORG, staff_id="amina@org", amount=100_000, purpose="Field trip",
                  issued_at="2026-01-01")
    check("an advance can still be recorded", a.ref == "ADV-0001")
    check("but nothing escalates",
          adv.escalation_of(ORG, a, at=dt.date(2026, 6, 1)) == adv.Escalation.NONE)
    check("and nothing is blocked",
          adv.payment_block(ORG, staff_id="amina@org") is None)
    # EVA's policy states the requirement but names NO window — a gap in their
    # policy, which this default handles honestly rather than inventing one.


# ─── the clock ──────────────────────────────────────────────────────────────


def test_working_days_not_calendar_days() -> None:
    print("\nFive working days from Thursday is the following Thursday")
    thursday = dt.date(2026, 8, 6)
    check("weekends are skipped",
          adv.add_working_days(thursday, 5) == dt.date(2026, 8, 13))
    monday = dt.date(2026, 8, 3)
    check("and a Monday start lands on Monday",
          adv.add_working_days(monday, 5) == dt.date(2026, 8, 10))
    # Counting calendar days would make an advance issued on a Thursday
    # effectively two days shorter than one issued on a Monday.
    check("calendar counting would have been unfair",
          thursday + dt.timedelta(days=5) == dt.date(2026, 8, 11))


def test_the_clock_starts_when_it_should() -> None:
    print("\nDSA cannot be retired before the trip has happened")
    clear(); neem_policy()
    ordinary = adv.issue(ORG, staff_id="amina@org", amount=100_000,
                         purpose="Supplies", issued_at="2026-08-03")
    check("an ordinary advance runs from the day it was received",
          ordinary.due_at == "2026-08-10")

    travel = adv.issue(ORG, staff_id="amina@org", amount=200_000,
                       purpose="Field trip DSA", issued_at="2026-08-03",
                       activity_end="2026-08-14")
    check("a travel advance runs from the END of the trip",
          travel.due_at == "2026-08-21", travel.due_at)
    raises("an activity cannot end before the advance was issued",
           lambda: adv.issue(ORG, staff_id="x@org", amount=1, purpose="p",
                             issued_at="2026-08-10", activity_end="2026-08-01"),
           contains="cannot end before")


# ─── the ladder ─────────────────────────────────────────────────────────────


def test_the_escalation_ladder() -> None:
    print("\nNEEM's three rungs, in order")
    clear(); neem_policy()
    a = adv.issue(ORG, staff_id="amina@org", staff_name="Amina Bello",
                  amount=150_000, purpose="Kano training",
                  project_code="B24", issued_at="2026-08-03")
    check("due five working days later", a.due_at == "2026-08-10")

    for day, expect, why in [
        (dt.date(2026, 8, 4),  adv.Escalation.NONE,          "well inside the window"),
        (dt.date(2026, 8, 9),  adv.Escalation.DUE_SOON,      "inside the warning period"),
        (dt.date(2026, 8, 11), adv.Escalation.STAFF_BLOCKED, "one day overdue"),
        (dt.date(2026, 9, 2),  adv.Escalation.RECOVERY,      "month end has passed"),
    ]:
        got = adv.escalation_of(ORG, a, at=day)
        check(f"{day} → {expect.name.lower()} ({why})", got == expect,
              f"got {got.name}")


def test_one_persons_lateness_is_not_a_collective_default() -> None:
    print("\nA collective default is a property of the project, not a person")
    clear(); neem_policy()
    adv.issue(ORG, staff_id="amina@org", amount=100_000, purpose="a",
              project_code="B24", issued_at="2026-08-03")
    late = dt.date(2026, 8, 20)

    a = adv.list_advances(ORG)[0]
    check("one overdue advance blocks the PERSON",
          adv.escalation_of(ORG, a, at=late) >= adv.Escalation.STAFF_BLOCKED)
    check("but not the project",
          adv.payment_block(ORG, project_code="B24", at=late) is None)

    adv.issue(ORG, staff_id="tunde@org", amount=80_000, purpose="b",
              project_code="B24", issued_at="2026-08-03")
    block = adv.payment_block(ORG, project_code="B24", at=late)
    check("two overdue on one project IS a collective default", bool(block))
    check("and the reason says so", "collective default" in block["reason"])
    check("naming the count", block["count"] == 2)


# ─── the block that bites ───────────────────────────────────────────────────


def test_the_block_stops_a_new_requisition() -> None:
    print("\nTHE POINT: the policy costs you the thing you want, when you want it")
    clear(); neem_policy()
    store.get_store().put(ORG, "config", "features",
                          {"modules": ["compliance"],
                           "features": {"advance_retirement": True}})

    import requisitions as rq
    rq.set_workflow(ORG, rq.RequisitionWorkflow(
        org_id=ORG, steps=[rq.WorkflowStep(key="finance", department="finance")],
        allowed_categories=["supplies"]))

    adv.issue(ORG, staff_id="amina@org", staff_name="Amina Bello",
              amount=150_000, purpose="Kano training", project_code="B24",
              issued_at="2026-01-05")            # long overdue

    req = rq.Requisition(id="r1", org_id=ORG, submitted_by="amina@org",
                         vendor_name="Sahel Catering", amount=96_000,
                         category="supplies", project_code="B24")
    checks = rq.run_policy_checks(ORG, req)
    c = next((x for x in checks if x.code == "ADVANCE_OUTSTANDING"), None)
    check("the check fired", c is not None)
    check("and it BLOCKS", c.result == rq.CheckResult.FAIL)
    check("naming the advance", "ADV-0001" in c.message)
    check("and the policy consequence",
          "no further payment" in c.message.lower())

    clean = rq.Requisition(id="r2", org_id=ORG, submitted_by="someone-else@org",
                           vendor_name="Sahel Catering", amount=96_000,
                           category="supplies", project_code="B99")
    check("somebody with no advance is unaffected",
          not [x for x in rq.run_policy_checks(ORG, clean)
               if x.code == "ADVANCE_OUTSTANDING"])


def test_the_check_is_silent_when_not_adopted() -> None:
    print("\nAn organisation without the feature sees nothing")
    store.get_store().put("quiet-org", "config", "features",
                          {"modules": ["compliance"], "features": {}})
    import requisitions as rq
    req = rq.Requisition(id="x", org_id="quiet-org", submitted_by="anyone@org",
                         vendor_name="V", amount=10_000, category="supplies")
    check("no advance check at all",
          not [c for c in rq.run_policy_checks("quiet-org", req)
               if c.code == "ADVANCE_OUTSTANDING"])


# ─── the morning list ───────────────────────────────────────────────────────


def test_the_aging_list() -> None:
    print("\nWhat finance chases this morning, worst first")
    clear(); neem_policy()
    adv.issue(ORG, staff_id="amina@org", staff_name="Amina", amount=150_000,
              purpose="Kano", project_code="B24", issued_at="2026-01-05")
    adv.issue(ORG, staff_id="tunde@org", staff_name="Tunde", amount=80_000,
              purpose="Abuja", project_code="B24", issued_at="2026-01-05")
    adv.issue(ORG, staff_id="ngozi@org", staff_name="Ngozi", amount=50_000,
              purpose="Fresh", project_code="B9", issued_at="2026-08-10")

    a = adv.aging(ORG, at=dt.date(2026, 8, 12))
    check("three outstanding", a["outstanding"] == 3)
    check("valued correctly", a["outstanding_value"] == 280_000.0)
    check("two overdue", a["overdue"] == 2)
    check("worst first", a["rows"][0]["escalation"] >= a["rows"][-1]["escalation"])
    check("two people blocked", len(a["blocked_staff"]) == 2)
    check("B24 in collective default", a["blocked_projects"] == ["B24"])
    check("the recovery list is populated", len(a["for_recovery"]) == 2)
    check("every row says what happens now",
          all(r["consequence"] for r in a["rows"]))
    check("in words someone can act on",
          "retired" in a["rows"][0]["consequence"].lower())


# ─── settling ───────────────────────────────────────────────────────────────


def test_retiring() -> None:
    print("\nRetiring stops the clock and names who owes whom")
    clear(); neem_policy()
    a = adv.issue(ORG, staff_id="amina@org", amount=150_000, purpose="Kano",
                  issued_at="2026-08-03")

    done = adv.retire(ORG, a.id, spent=120_000, actor="finance@org",
                      receipt_ids=["r1", "r2"])
    check("status is retired", done.status == adv.AdvanceStatus.RETIRED)
    check("balance computed", done.balance == 30_000.0)
    check("direction names who owes whom", done.direction == "recover")
    check("receipts are linked", done.receipt_ids == ["r1", "r2"])
    check("no longer outstanding", adv.aging(ORG)["outstanding"] == 0)
    check("and it no longer blocks",
          adv.payment_block(ORG, staff_id="amina@org") is None)

    raises("it cannot be retired twice",
           lambda: adv.retire(ORG, a.id, spent=1, actor="x"),
           contains="already retired")

    over = adv.issue(ORG, staff_id="tunde@org", amount=100_000, purpose="Trip",
                     issued_at="2026-08-03")
    spent_more = adv.retire(ORG, over.id, spent=130_000, actor="finance@org")
    check("an overspend is owed back to the traveller",
          spent_more.direction == "reimburse" and spent_more.balance == -30_000.0)


def test_recovery_and_write_off() -> None:
    print("\nThe last two rungs are their own facts, not 'retired'")
    clear(); neem_policy()
    a = adv.issue(ORG, staff_id="amina@org", amount=150_000, purpose="Kano",
                  issued_at="2026-01-05")
    rec = adv.mark_recovered(ORG, a.id, actor="hr@org", reason="August payroll")
    check("recovered is its own status", rec.status == adv.AdvanceStatus.RECOVERED)
    check("the full amount is owed", rec.balance == 150_000.0)
    check("and it says who and why",
          "hr@org" in rec.notes[-1] and "August payroll" in rec.notes[-1])

    b = adv.issue(ORG, staff_id="gone@org", amount=90_000, purpose="Left",
                  issued_at="2026-01-05")
    raises("a write-off without a reason is refused",
           lambda: adv.write_off(ORG, b.id, actor="ed@org", reason="  "),
           contains="written reason")
    off = adv.write_off(ORG, b.id, actor="ed@org",
                        reason="Staff member left; no forwarding address")
    check("written off", off.status == adv.AdvanceStatus.WRITTEN_OFF)
    check("permanently, with the reason",
          "WRITTEN OFF by ed@org" in off.notes[-1])


def test_org_scoping() -> None:
    print("\nOne org cannot see another's advances")
    clear(); clear("other-org")
    adv.issue(ORG, staff_id="mine@org", amount=1000, purpose="mine")
    adv.issue("other-org", staff_id="theirs@org", amount=2000, purpose="theirs")
    check("scoped", [a.purpose for a in adv.list_advances(ORG)] == ["mine"])


def main() -> int:
    print("=" * 68)
    print("Advance retirement — the clock, and the consequence")
    print("=" * 68)
    for fn in (
        test_off_by_default,
        test_working_days_not_calendar_days,
        test_the_clock_starts_when_it_should,
        test_the_escalation_ladder,
        test_one_persons_lateness_is_not_a_collective_default,
        test_the_block_stops_a_new_requisition,
        test_the_check_is_silent_when_not_adopted,
        test_the_aging_list,
        test_retiring,
        test_recovery_and_write_off,
        test_org_scoping,
    ):
        fn()
    print("\n" + "=" * 68)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 68)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
