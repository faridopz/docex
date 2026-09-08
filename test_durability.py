"""
Does it survive a redeploy?

The failure this suite exists to prevent is the quietest one in the product.
Writing a file always succeeds, so an engine that persists to the container's
local disk looks perfectly healthy — right up until the platform replaces that
disk on the next deploy and the records are simply gone. No error, no log line,
nothing to notice until a user asks where their work went.

Requisitions, approvals, payments, users and the audit log were moved onto
durable storage earlier. Notifications, transactions and vouchers were not, and
this suite is what proves they now are.

"Redeploy" is simulated the only honest way: write through one store instance,
throw the process state away, open a NEW store against the same database, and
look for the records. Anything held in a module-level cache or a file beside
the code fails that.

Run: python test_durability.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_DIR = Path(tempfile.mkdtemp(prefix="docex-durable-"))
_DB = _DIR / "docex.db"

import store  # noqa: E402
import store_sql  # noqa: E402

store.set_store(store_sql.SqliteStore(_DB))
os.environ["DOCEX_ORG"] = "durable"
ORG = "durable"

import departments  # noqa: E402

departments.save(departments.default_registry(), ORG)

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def redeploy() -> None:
    """Everything the process was holding is discarded; the database is not.

    A new SqliteStore against the same file is exactly what a fresh container
    does on boot. If a record was only ever in memory, or in a file that the
    platform replaced, it does not come back from this.
    """
    store.set_store(store_sql.SqliteStore(_DB))


# ─── the three engines that used to lose their records ──────────────────────


def test_notifications_survive() -> None:
    print("\nA department's inbox is still there after a deploy")
    import notification_center as nc

    nc.create("C24", "finance", "assigned",
              "Payment awaiting your review", "Zenith Ltd — ₦450,000", org_id=ORG)
    nc.create("C25", "finance", "assigned", "Second item", org_id=ORG)
    nc.create("C26", "program", "approved", "For programmes", org_id=ORG)
    check("three notifications written", nc.unread_count("finance", ORG) == 2)

    redeploy()

    check("finance inbox survived", nc.unread_count("finance", ORG) == 2)
    check("programmes inbox survived", nc.unread_count("program", ORG) == 1)
    items = nc.list_for("finance", org_id=ORG)
    check("the content came back intact",
          any("₦450,000" in (n.body or "") for n in items))
    check("the naira sign is not mangled",
          any("₦" in (n.body or "") for n in items))

    # Read state must survive too — otherwise every deploy marks the whole
    # organisation's inbox unread again, which is its own kind of noise.
    nc.mark_read(items[0].id, ORG)
    redeploy()
    check("marking one read survived", nc.unread_count("finance", ORG) == 1)


def test_transactions_survive() -> None:
    print("\nA payment in flight is still in flight after a deploy")
    import transactions as tx

    t = tx.create("voucher", "Q3 workshop — 42 participants",
                  amount=1_800_000, org_id=ORG)
    ref = t.ref
    check("a transaction was opened", bool(ref))

    t = tx.transition(t, "compliance_review", department="program", org_id=ORG)
    redeploy()

    again = tx.load_by_ref(ref, ORG)
    check("it is found by its reference", again.ref == ref)
    check("its state survived", again.state == "compliance_review")
    check("the amount is exact", again.amount == 1_800_000)
    check("its history survived", len(again.history) == len(t.history))


def test_the_reference_counter_does_not_reset() -> None:
    print("\nTHE ONE THAT WOULD HURT: references must not start again at 1")
    import transactions as tx

    first = tx.create("compliance_check", "Before the deploy", org_id=ORG)
    redeploy()
    second = tx.create("compliance_check", "After the deploy", org_id=ORG)

    check(f"a new reference was issued ({first.ref} → {second.ref})",
          first.ref != second.ref)

    def number(ref: str) -> int:
        return int("".join(c for c in ref if c.isdigit()) or 0)

    check("and it counted UP, not back to 1",
          number(second.ref) > number(first.ref),
          f"{first.ref} then {second.ref}")

    refs = [t.ref for t in tx._iter_all(ORG)]
    check("no two transactions share a reference", len(refs) == len(set(refs)),
          f"{len(refs) - len(set(refs))} duplicate(s)")
    # This is the failure worth the loudest test. The old counter was a file
    # beside the code; when the deploy wiped it, numbering restarted and a
    # second payment could be issued a voucher reference that already existed.
    # Two payments sharing one voucher number is exactly what an auditor finds.


def test_vouchers_survive() -> None:
    print("\nA voucher is still there after a deploy")
    import vouchers
    from models import Voucher, VoucherLine

    v = Voucher(
        id="v-durable-1",
        event_name="Kano training",
        currency="NGN",
        lines=[VoucherLine(participant_name="Amina Bello", amount=45_000),
               VoucherLine(participant_name="Tunde Okoro", amount=45_000)],
        total=90_000,
        participant_count=2,
    )
    vouchers._save(v, ORG)
    redeploy()

    back = vouchers.load("v-durable-1", ORG)
    check("the voucher came back", back.event_name == "Kano training")
    check("its total is exact", back.total == 90_000)
    check("its lines came back", len(back.lines) == 2)
    check("it appears in the list", any(s.id == "v-durable-1"
                                        for s in vouchers.list_all(ORG)))


# ─── and the ones that were already durable, so we notice a regression ──────


def test_the_rest_is_still_durable() -> None:
    print("\nThe engines that were already durable, still are")
    import auth
    import requisitions as rq

    auth.create_user("durable@neem.org", "Durable", "DurablePass2026!",
                     "finance", "admin", ORG)
    rq.set_workflow(ORG, rq.default_workflow(ORG, size="small"))
    req = rq.create_requisition(ORG, submitted_by="durable@neem.org",
                                department="finance", vendor_name="Zenith Ltd",
                                amount=250_000, category="services",
                                description="Durability suite")

    redeploy()

    check("the user can still be found",
          auth.get_by_email("durable@neem.org", ORG) is not None)
    check("the password still verifies",
          auth.authenticate("durable@neem.org", "DurablePass2026!", ORG) is not None)
    stored = rq.get_requisition(ORG, req.id)
    check("the requisition survived", stored is not None)
    check("its amount is exact", stored.amount == 250_000)
    check("its audit chain still verifies", rq.verify_audit_chain(stored))


def test_nothing_leaks_between_organisations() -> None:
    print("\nAnd none of it leaks into another organisation")
    import notification_center as nc
    import transactions as tx

    departments.save(departments.default_registry(), "otherorg")
    nc.create("X1", "finance", "assigned", "Belongs to the other org",
              org_id="otherorg")
    tx.create("voucher", "Other org voucher", amount=1, org_id="otherorg")

    redeploy()

    check("the other org sees only its own notification",
          nc.unread_count("finance", "otherorg") == 1)
    check("and ours is unchanged", nc.unread_count("finance", ORG) == 1)
    ours = {t.id for t in tx._iter_all(ORG)}
    theirs = {t.id for t in tx._iter_all("otherorg")}
    check("no transaction appears in both", not (ours & theirs))


if __name__ == "__main__":
    try:
        test_notifications_survive()
        test_transactions_survive()
        test_the_reference_counter_does_not_reset()
        test_vouchers_survive()
        test_the_rest_is_still_durable()
        test_nothing_leaks_between_organisations()
        print(f"\n{_passed} passed, {_failed} failed")
    finally:
        shutil.rmtree(_DIR, ignore_errors=True)
    raise SystemExit(1 if _failed else 0)
