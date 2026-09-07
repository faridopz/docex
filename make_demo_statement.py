#!/usr/bin/env python3
"""
Build a demo bank statement that matches the seeded demo data.

    DOCEX_ORG=neem DOCEX_DB=./docex.db python3 make_demo_statement.py

Why generate rather than hand-write a CSV: the statement has to agree with
whatever demo_seed.py actually created. A hard-coded file drifts the moment the
seed changes, and a reconciliation demo where the "matched" rows do not match
is worse than no demo. So this reads the real paid transactions out of the
store and builds the statement around them.

It then plants the exceptions that make the demo worth watching:

  * a transfer with NO requisition behind it — money out that nobody approved.
    This is the finding a manual reconciliation misses, because a person ticks
    their payment list off against the statement and never works backwards.
  * a bank charge, which is unmatched but entirely legitimate — so there is
    something real to explain, and the difference between "unexplained" and
    "explained" is visible rather than theoretical.
  * a grant receipt (money IN), to show credits are not treated as payments.
  * a payment recorded in DOCex but absent from the bank, if the seed has one.

The output deliberately looks like a Nigerian bank export: a title block above
the headers, "Value Date", separate Debit and Credit columns, amounts with
thousands separators, DD/MM/YYYY dates. That exercises the importer's real
work — skipping preamble rows, detecting columns, proving the date format —
rather than handing it a file we already know it likes.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import random
import sys

import store


def _fmt_amount(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_date(d: dt.date) -> str:
    # Day-first, like every Nigerian bank statement. At least one day above the
    # 12th appears in the file, which is what lets the importer PROVE the
    # format rather than assume it.
    return d.strftime("%d/%m/%Y")


def build(org_id: str, period: str | None = None) -> tuple[str, dict]:
    import requisitions as rq

    org = store.require_org(org_id)
    today = dt.date.today()
    period = period or today.strftime("%Y-%m")
    year, month = (int(p) for p in period.split("-"))
    start = dt.date(year, month, 1)
    end = min(today, (dt.date(year + (month == 12), (month % 12) + 1, 1)
                      - dt.timedelta(days=1)))

    paid = [t for t in rq.list_transactions(org)
            if start.isoformat() <= (t.paid_at or "")[:10] <= end.isoformat()]

    rows: list[tuple[dt.date, str, str, float, float]] = []
    for txn in paid:
        d = dt.date.fromisoformat(txn.paid_at[:10])
        rows.append((
            d,
            f"TRF TO {txn.vendor_name.upper()}",
            txn.bank_reference or "",
            abs(txn.amount),      # debit
            0.0,
        ))

    def somewhere_in_month(day_hint: int) -> dt.date:
        return dt.date(year, month, max(1, min(day_hint, end.day)))

    # ── the planted findings ────────────────────────────────────────────────
    # The one that matters. A round-number transfer to a vendor that appears
    # nowhere in the approval system.
    rows.append((
        somewhere_in_month(11),
        "TRF TO BRIGHTPATH SUPPLIES NIG LTD",
        "FT26090411902",
        750_000.00,
        0.0,
    ))

    # Legitimate, but still needs a human to say so.
    rows.append((somewhere_in_month(1), "COMMISSION ON TURNOVER", "COT", 2_150.00, 0.0))
    rows.append((somewhere_in_month(28), "SMS ALERT CHARGE", "CHG", 500.00, 0.0))

    # Money IN — must not be treated as a payment.
    rows.append((
        somewhere_in_month(6),
        "INFLOW GLOBAL FUND TB GRANT TRANCHE 3",
        "GF/TR3/2026",
        0.0,
        12_400_000.00,
    ))
    rows.append((somewhere_in_month(20), "CREDIT INTEREST", "INT", 0.0, 1_204.55))

    rows.sort(key=lambda r: r[0])

    # Written with csv.writer, not f-strings. "2,150.00" contains a comma, so
    # writing it raw splits the row into extra columns — which is precisely the
    # kind of malformed input the importer has to survive, but not something to
    # ship in a demo file. Real bank exports quote these fields; so does this.
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["FIRST TRUST BANK OF NIGERIA PLC"])
    w.writerow(["STATEMENT OF ACCOUNT"])
    w.writerow([f"Account Name: DEMO ORGANISATION  |  Account No: "
                f"30{random.randint(10**8, 10**9 - 1)}"])
    w.writerow([f"Period: {_fmt_date(start)} to {_fmt_date(end)}  |  Currency: NGN"])
    w.writerow([])
    w.writerow(["Value Date", "Narration", "Reference", "Debit", "Credit"])
    for d, narration, ref, debit, credit in rows:
        w.writerow([_fmt_date(d), narration, ref,
                    _fmt_amount(debit) if debit else "",
                    _fmt_amount(credit) if credit else ""])

    stats = {
        "period": period,
        "matched_payments": len(paid),
        "planted_unapproved": 750_000.00,
        "bank_charges": 2,
        "credits": 2,
        "rows": len(rows),
    }
    return buf.getvalue(), stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="demo_bank_statement.csv")
    ap.add_argument("--period", default=None, help="YYYY-MM (default: this month)")
    args = ap.parse_args()

    # Without this the script reads a perfectly healthy JSON store that simply
    # is not the one the app uses, and reports "0 payments" for a seeded demo.
    backend = store.configure_from_env()

    org = os.environ.get("DOCEX_ORG", "").strip()
    if not org:
        print("Set DOCEX_ORG (and DOCEX_DB) so this reads the same data the app "
              "does.\n  DOCEX_ORG=neem DOCEX_DB=./docex.db python3 "
              "make_demo_statement.py", file=sys.stderr)
        return 2

    csv_text, stats = build(org, args.period)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(csv_text)

    print(f"Wrote {args.out} — {stats['rows']} rows for {stats['period']}")
    print(f"  · read from {backend}, org '{org}'")
    print(f"  · {stats['matched_payments']} payment(s) that should match DOCex")
    print(f"  · 1 transfer of ₦{stats['planted_unapproved']:,.0f} with NO "
          "requisition — the finding to demo")
    print(f"  · {stats['bank_charges']} bank charges to explain, "
          f"{stats['credits']} credits that must NOT count as payments")
    if stats["matched_payments"] == 0:
        print("\n  ⚠️  No paid transactions found for this period. Run demo_seed.py "
              "first, or pass --period for the month they were paid in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
