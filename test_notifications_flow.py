"""End-to-end check: a transaction moving stages fans out the right in-app
notifications to the right departments. Run: python test_notifications_flow.py"""
from __future__ import annotations

import os
import tempfile

import store

# Install an isolated backend BEFORE importing the engines.
#
# This used to reassign tx._TXN_DIR and nc._NOTIF_DIR — module-level paths that
# no longer exist, because transactions and notifications now persist through
# the store layer so they survive a redeploy. Left as it was, the suite wrote
# into the developer's real data/ directory and counted notifications left over
# from the previous run, which showed up as an off-by-one that had nothing to
# do with the code under test.
store.set_store(store.JsonFileStore(tempfile.mkdtemp(prefix="docex_notif_")))
os.environ["DOCEX_ORG"] = "notiftest"

import notification_center as nc  # noqa: E402
import transactions as tx  # noqa: E402

_fail = 0


def check(name, got, want):
    global _fail
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        _fail += 1


def move(txn, to, **kw):
    txn = tx.transition(txn, to, **kw)
    nc.notify_transition(txn, txn.history[-1])
    return txn


# Open a voucher transaction and walk it through the pipeline.
t = tx.create("voucher", "Q3 Workshop voucher (42 participants)", amount=1_800_000)

t = move(t, "compliance_review", department="program")
check("compliance notified on assignment", nc.unread_count("compliance"), 1)
check("finance not yet notified", nc.unread_count("finance"), 0)

t = move(t, "finance_review", department="compliance")
check("finance notified after compliance passes it on", nc.unread_count("finance"), 1)

t = move(t, "approval", department="finance")
check("management notified for approval", nc.unread_count("management"), 1)

t = move(t, "paid", department="management")
check("finance notified of payment", nc.unread_count("finance"), 2)

# Inbox content sanity.
fin_inbox = nc.list_for("finance")
check("finance inbox newest-first is the paid one", fin_inbox[0].kind, "paid")
check("notification references the txn", fin_inbox[0].txn_ref, t.ref)

# Returned path notifies the fixer (program).
t2 = tx.create("compliance_check", "Voucher batch B")
t2 = move(t2, "compliance_review", department="program")
before = nc.unread_count("program")
t2 = move(t2, "returned", department="compliance", note="missing CAC certificate")
check("program notified of return", nc.unread_count("program"), before + 1)
prog_latest = nc.list_for("program")[0]
check("return note carried through", "missing CAC" in prog_latest.body, True)

# mark-all-read clears the badge.
nc.mark_all_read("finance")
check("finance inbox cleared", nc.unread_count("finance"), 0)

print()
if _fail:
    raise SystemExit(f"{_fail} check(s) failed")
print("All notification-flow checks passed.")
