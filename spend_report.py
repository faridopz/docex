#!/usr/bin/env python3
"""
Your spend dashboard. Not the clients'.

    python3 spend_report.py                        # every client, this month
    python3 spend_report.py --db ./neem.db ./eva.db
    python3 spend_report.py --month 2026-08
    python3 spend_report.py --html                 # opens a page in your browser

WHY THIS IS A LOCAL SCRIPT AND NOT A SCREEN IN THE APP
It reads ACROSS organisations, which is exactly what the product's isolation
model forbids. A cross-org route inside a client-facing app is one
authorisation bug away from a client seeing that other clients exist, what they
are called, and roughly what they cost you. There is no version of that which
ends well.

So this is a tool you run on your own machine, against whichever databases you
point it at. Nothing is served, nothing is exposed, and there is no endpoint to
get wrong.

WHAT IT ANSWERS
  · What am I spending this month, and where will it land?
  · Which client is driving it?
  · Is anyone trending up before it shows on a bill?
  · Is the prompt caching still working?
  · What is left after model spend on each client?

Costs are ESTIMATES from usage.py's rate table. Verify against your actual
Anthropic invoice before you price anything on them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

# What you charge each client per month. Used only to show margin — edit here,
# or set DOCEX_REVENUE="neem=450000,eva=600000".
DEFAULT_REVENUE_NGN: dict[str, float] = {
    "neem": 450_000,
    "eva": 600_000,
}


def _revenue() -> dict[str, float]:
    raw = os.environ.get("DOCEX_REVENUE", "").strip()
    if not raw:
        return dict(DEFAULT_REVENUE_NGN)
    out = dict(DEFAULT_REVENUE_NGN)
    for part in raw.split(","):
        if "=" in part:
            org, amount = part.split("=", 1)
            try:
                out[org.strip()] = float(amount)
            except ValueError:
                pass
    return out


def _this_month() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def _month_progress(month: str) -> tuple[int, int]:
    """(days elapsed, days in month) — for projecting where spend lands."""
    import calendar
    year, mon = (int(p) for p in month.split("-"))
    days_in = calendar.monthrange(year, mon)[1]
    today = dt.datetime.now(dt.timezone.utc).date()
    if (today.year, today.month) == (year, mon):
        return today.day, days_in
    return days_in, days_in          # a past month is complete


def _discover_dbs(explicit: list[str]) -> list[Path]:
    if explicit:
        return [Path(p) for p in explicit]
    here = Path(__file__).parent
    found = sorted(p for p in here.glob("*.db") if p.stat().st_size > 0)
    if not found:
        print("No .db files found. Point at one:  --db ./neem.db", file=sys.stderr)
    return found


def collect(db_paths: list[Path], month: str) -> list[dict]:
    """Per-org usage across every database given. Never mutates anything."""
    import store
    import store_sql
    import usage

    rows: list[dict] = []
    revenue = _revenue()

    for path in db_paths:
        if not path.exists():
            print(f"  (skipping {path} — not found)", file=sys.stderr)
            continue
        try:
            backend = store_sql.SqliteStore(str(path))
        except Exception as exc:
            print(f"  (skipping {path} — {exc})", file=sys.stderr)
            continue
        store.set_store(backend)

        # Every org that has ever recorded usage in this database.
        orgs: set[str] = set()
        try:
            with backend._connect() as conn:
                for (org,) in conn.execute(
                        "SELECT DISTINCT org_id FROM records WHERE collection = ?",
                        ("model_usage",)).fetchall():
                    orgs.add(org)
        except Exception:
            continue

        for org in sorted(orgs):
            try:
                s = usage.summary(org, month)
                daily = [d for d in usage.daily(org, month)]
            except Exception:
                continue
            if not s.calls:
                continue
            rows.append({
                "org": org,
                "db": path.name,
                "calls": s.calls,
                "input": s.input_tokens,
                "output": s.output_tokens,
                "cache_read": s.cache_read_tokens,
                "cache_hit": s.cache_hit_rate,
                "usd": s.cost_usd,
                "ngn": s.cost_ngn,
                "by_operation": s.by_operation,
                "by_model": s.by_model,
                "daily": daily,
                "revenue_ngn": revenue.get(org, 0.0),
            })
    return rows


# ─── terminal ───────────────────────────────────────────────────────────────


def _bar(value: float, peak: float, width: int = 22) -> str:
    if peak <= 0:
        return ""
    return "█" * max(1, int(value / peak * width)) if value > 0 else ""


def render_text(rows: list[dict], month: str) -> None:
    elapsed, total_days = _month_progress(month)
    print(f"\n\033[1mDOCex model spend — {month}\033[0m")
    print(f"day {elapsed} of {total_days}")
    print("─" * 74)

    if not rows:
        print("\nNo usage recorded. Either nothing has run, or you are pointed")
        print("at the wrong database (--db ./neem.db).\n")
        return

    total_usd = sum(r["usd"] for r in rows)
    total_ngn = sum(r["ngn"] for r in rows)
    projected = total_usd / elapsed * total_days if elapsed else total_usd

    print(f"\n  Spent so far   ${total_usd:>10,.2f}   ≈ ₦{total_ngn:>12,.0f}")
    print(f"  Month-end      ${projected:>10,.2f}   ≈ ₦{projected * (total_ngn / total_usd if total_usd else 0):>12,.0f}"
          if total_usd else "")
    print(f"  Clients        {len(rows)}")

    print(f"\n\033[1m  BY CLIENT\033[0m")
    print(f"  {'client':<12} {'calls':>7} {'cost':>10} {'≈ ₦':>11} {'cache':>7}  {'after AI':>9}")
    print("  " + "─" * 70)
    peak = max(r["usd"] for r in rows)
    for r in sorted(rows, key=lambda x: -x["usd"]):
        margin = ""
        if r["revenue_ngn"]:
            pct = (r["revenue_ngn"] - r["ngn"]) / r["revenue_ngn"] * 100
            colour = "\033[32m" if pct > 80 else ("\033[33m" if pct > 60 else "\033[31m")
            margin = f"{colour}{pct:>8.1f}%\033[0m"
        print(f"  {r['org']:<12} {r['calls']:>7,} ${r['usd']:>9,.2f} "
              f"₦{r['ngn']:>10,.0f} {r['cache_hit']:>6.0%}  {margin}")
        print(f"  {'':<12} {_bar(r['usd'], peak)}")

    # Where the money goes, not just who spent it.
    ops: dict[str, float] = {}
    models: dict[str, float] = {}
    for r in rows:
        for op, v in r["by_operation"].items():
            ops[op] = ops.get(op, 0.0) + v["cost_usd"]
        for m, v in r["by_model"].items():
            models[m] = models.get(m, 0.0) + v["cost_usd"]

    print(f"\n\033[1m  BY FEATURE\033[0m")
    for op, cost in sorted(ops.items(), key=lambda kv: -kv[1]):
        share = cost / total_usd * 100 if total_usd else 0
        print(f"  {op:<24} ${cost:>8,.2f}  {share:>5.1f}%  {_bar(cost, max(ops.values()), 16)}")

    print(f"\n\033[1m  BY MODEL\033[0m")
    for m, cost in sorted(models.items(), key=lambda kv: -kv[1]):
        print(f"  {m:<32} ${cost:>8,.2f}")

    # Trend — the thing that matters before it reaches a bill.
    print(f"\n\033[1m  DAILY\033[0m")
    by_day: dict[str, float] = {}
    for r in rows:
        for d in r["daily"]:
            by_day[d["day"]] = by_day.get(d["day"], 0.0) + d["cost_usd"]
    if by_day:
        peak_day = max(by_day.values())
        for day in sorted(by_day)[-14:]:
            print(f"  {day}  ${by_day[day]:>7,.2f}  {_bar(by_day[day], peak_day, 30)}")

        recent = [by_day[d] for d in sorted(by_day)[-3:]]
        earlier = [by_day[d] for d in sorted(by_day)[-7:-3]]
        if earlier and recent:
            r_avg, e_avg = sum(recent) / len(recent), sum(earlier) / len(earlier)
            if e_avg > 0 and r_avg > e_avg * 1.5:
                print(f"\n  \033[33m⚠ Trending up — last 3 days average ${r_avg:.2f}/day "
                      f"vs ${e_avg:.2f} before.\033[0m")

    # Caching is the cheapest lever available; a drop means something broke.
    weak = [r for r in rows if r["cache_hit"] < 0.3 and r["calls"] > 10]
    if weak:
        print(f"\n  \033[33m⚠ Low cache hit rate: {', '.join(r['org'] for r in weak)}\033[0m")
        print("    Repeated checks against one rulebook should be reusing the cache.")

    print("\n  'After AI' is revenue minus MODEL SPEND ONLY — it is not your margin.")
    print("  Hosting, support hours and overhead are not in this number.")
    print("  Costs are estimates from usage.py's rate table; verify against your")
    print("  Anthropic invoice before pricing anything.\n")


# ─── html ───────────────────────────────────────────────────────────────────


def render_html(rows: list[dict], month: str, out: Path) -> Path:
    elapsed, total_days = _month_progress(month)
    total_usd = sum(r["usd"] for r in rows)
    total_ngn = sum(r["ngn"] for r in rows)
    projected = total_usd / elapsed * total_days if elapsed else total_usd

    by_day: dict[str, float] = {}
    for r in rows:
        for d in r["daily"]:
            by_day[d["day"]] = by_day.get(d["day"], 0.0) + d["cost_usd"]
    peak = max(by_day.values()) if by_day else 1.0

    client_rows = ""
    for r in sorted(rows, key=lambda x: -x["usd"]):
        margin_cell = "—"
        if r["revenue_ngn"]:
            pct = (r["revenue_ngn"] - r["ngn"]) / r["revenue_ngn"] * 100
            colour = "#16a34a" if pct > 80 else ("#ca8a04" if pct > 60 else "#dc2626")
            margin_cell = f'<span style="color:{colour};font-weight:600">{pct:.1f}%</span>'
        client_rows += (
            f"<tr><td><b>{r['org']}</b></td><td class=n>{r['calls']:,}</td>"
            f"<td class=n>${r['usd']:,.2f}</td><td class=n>₦{r['ngn']:,.0f}</td>"
            f"<td class=n>{r['cache_hit']:.0%}</td><td class=n>{margin_cell}</td></tr>")

    bars = "".join(
        f'<div class=bar><span class=d>{d}</span>'
        f'<span class=f style="width:{by_day[d] / peak * 100:.1f}%"></span>'
        f'<span class=v>${by_day[d]:,.2f}</span></div>'
        for d in sorted(by_day)[-21:])

    html = f"""<!doctype html><meta charset=utf-8>
<title>DOCex spend — {month}</title>
<style>
 body{{font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      max-width:860px;margin:40px auto;padding:0 20px;color:#18181b;background:#fafaf9}}
 h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#71717a;font-size:14px;margin-bottom:28px}}
 .cards{{display:flex;gap:14px;margin-bottom:28px;flex-wrap:wrap}}
 .card{{flex:1;min-width:150px;background:#fff;border:1px solid #e4e4e7;border-radius:10px;padding:16px}}
 .card .l{{font-size:12px;color:#71717a;text-transform:uppercase;letter-spacing:.04em}}
 .card .v{{font-size:24px;font-weight:650;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e4e4e7;border-radius:10px;overflow:hidden}}
 th{{text-align:left;font-size:12px;color:#71717a;text-transform:uppercase;
     letter-spacing:.04em;padding:10px 14px;border-bottom:1px solid #e4e4e7;background:#fafafa}}
 td{{padding:11px 14px;border-bottom:1px solid #f4f4f5}} .n{{text-align:right;font-variant-numeric:tabular-nums}}
 h2{{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#71717a;margin:32px 0 10px}}
 .bar{{display:flex;align-items:center;gap:10px;margin:3px 0;font-size:13px}}
 .bar .d{{width:88px;color:#71717a;font-variant-numeric:tabular-nums}}
 .bar .f{{height:16px;background:#2563eb;border-radius:3px;min-width:2px}}
 .bar .v{{color:#52525b;font-variant-numeric:tabular-nums}}
 .note{{margin-top:32px;font-size:13px;color:#71717a;border-top:1px solid #e4e4e7;padding-top:14px}}
</style>
<h1>Model spend — {month}</h1>
<div class=sub>Day {elapsed} of {total_days} · {len(rows)} client(s) · your view only</div>
<div class=cards>
 <div class=card><div class=l>Spent</div><div class=v>${total_usd:,.2f}</div></div>
 <div class=card><div class=l>Month-end</div><div class=v>${projected:,.2f}</div></div>
 <div class=card><div class=l>In naira</div><div class=v>₦{total_ngn:,.0f}</div></div>
</div>
<table><tr><th>Client</th><th class=n>Calls</th><th class=n>Cost</th>
<th class=n>≈ ₦</th><th class=n>Cache</th><th class=n>After AI</th></tr>{client_rows}</table>
<h2>Daily</h2>{bars}
<div class=note><b>&ldquo;After AI&rdquo; is revenue minus model spend only &mdash; it is
not your margin.</b> Hosting, support hours and overhead are not in it. Costs are
estimates from usage.py&rsquo;s rate table; verify against your Anthropic invoice
before pricing anything. Revenue figures come from spend_report.py or
DOCEX_REVENUE.</div>"""
    out.write_text(html)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Your DOCex model-spend dashboard.")
    ap.add_argument("--db", nargs="*", default=[], help="Database files (default: every *.db here)")
    ap.add_argument("--month", default=_this_month(), help="YYYY-MM (default: this month)")
    ap.add_argument("--html", action="store_true", help="Write an HTML page and open it")
    args = ap.parse_args()

    dbs = _discover_dbs(args.db)
    if not dbs:
        return 1
    rows = collect(dbs, args.month)

    if args.html:
        out = render_html(rows, args.month, Path(__file__).parent / "spend_report.html")
        print(f"Written to {out}")
        try:
            import webbrowser
            webbrowser.open(f"file://{out.resolve()}")
        except Exception:
            pass
        return 0

    render_text(rows, args.month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
