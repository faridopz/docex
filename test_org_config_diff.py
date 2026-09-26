"""
Before a profile is (re-)applied to a live client, show what it would change.

Found preparing NEEM's production update: its live settings were last written
on 16 Sep and lack every feature built since. Re-applying the profile is the
fix, but two things made that unsafe:

  * the CLI chose its database from DOCEX_DB only. Production is Postgres
    (DOCEX_DATABASE_URL), so `apply` would have written a healthy local JSON
    store, printed "Applied profile", and changed nothing live;
  * apply replaces the feature list wholesale, so a flag someone switched on
    by hand in production is silently switched off.

Run: python test_org_config_diff.py
"""
from __future__ import annotations

import copy
import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="docex-diff-")
os.environ["DOCEX_ORG"] = "acme"
os.environ.pop("DOCEX_DB", None)

import store  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


# Stand-in for Postgres: the CLI must pick the database the API uses, and in
# production that is DOCEX_DATABASE_URL. Installed before anything configures
# a store, exactly as a fresh CLI process starts.
import store_sql  # noqa: E402

_PG_ROOT = Path(_TMP) / "pg"


class FakePostgres(store.JsonFileStore):
    def __init__(self, url: str) -> None:
        super().__init__(_PG_ROOT)


store_sql.PostgresStore = FakePostgres  # type: ignore[misc]

import org_config  # noqa: E402

PROFILE = {
    "org_id": "acme",
    "currency": "NGN",
    "departments": [{"key": "program", "name": "Programmes"},
                    {"key": "finance", "name": "Finance", "is_final_authority": True}],
    "workflow": {"max_amount": 1000000, "required_documents": ["invoice"],
                 "steps": [{"key": "finance", "label": "Finance", "department": "finance"}]},
    "modules": ["compliance"],
    "features": {"voucher_export": True, "payee_account_check": True, "bank_reconciliation": False},
    "voucher_template": {"organisation_name": "Acme Relief"},
    # Stamped with org_id/updated_at when saved: a re-applied policy must
    # still read as unchanged (it didn't, the first time this ran on NEEM).
    "advance_policy": {"enabled": True, "retirement_days": 14},
}


def _cli(*argv: str) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = org_config._cli(list(argv))
    return rc, buf.getvalue()


def test_the_cli_writes_where_the_api_reads() -> None:
    print("\nDOCEX_DATABASE_URL set: the CLI uses that database, not local files")
    os.environ["DOCEX_DATABASE_URL"] = "postgresql://fake"
    rc, out = _cli("features", "--org", "acme", "hand_set_flag=on")
    check("command succeeded", rc == 0, out)
    check("the flag landed in the database the API reads",
          (_PG_ROOT / "acme").exists() and org_config.feature_enabled("acme", "hand_set_flag"), out)
    check("and says which database it used", "postgres" in out.lower(), out)


def test_diff_names_what_would_change() -> None:
    print("\nAn out-of-date live org: every difference is named")
    lines = org_config.diff_profile(PROFILE)
    text = "\n".join(lines)
    check("new flags the profile turns on", "payee_account_check" in text and "voucher_export" in text, text)
    check("a hand-set flag the profile would drop", "hand_set_flag" in text, text)
    check("the voucher template it would install", "voucher_template" in text, text)
    check("the spending ceiling it would change", "max_amount" in text, text)


def test_diff_after_apply_is_empty_apart_from_what_apply_cannot_touch() -> None:
    print("\nApplied: nothing left to report")
    org_config.set_features("acme", hand_set_flag=False)
    org_config.apply_profile(copy.deepcopy(PROFILE))
    lines = org_config.diff_profile(PROFILE)
    check("no differences", lines == [], "\n".join(lines))
    rc, out = _cli("diff", _write_profile(PROFILE))
    check("CLI says it's in step", rc == 0 and "matches" in out.lower(), out)


def test_apply_warns_when_it_switches_a_live_flag_off() -> None:
    print("\nA live flag the profile doesn't carry is not dropped silently")
    org_config.set_features("acme", hand_set_flag=True)
    res = org_config.apply_profile(copy.deepcopy(PROFILE))
    check("warning names the flag", any("hand_set_flag" in w for w in res.warnings), str(res.warnings))


def test_diff_exits_nonzero_when_out_of_step() -> None:
    print("\nCLI diff can gate a deploy script")
    changed = copy.deepcopy(PROFILE)
    changed["features"]["timesheets"] = True
    rc, out = _cli("diff", _write_profile(changed))
    check("exit 1 and names the flag", rc == 1 and "timesheets" in out, out)


def _write_profile(p: dict) -> str:
    path = Path(_TMP) / "profile.json"
    path.write_text(json.dumps(p))
    return str(path)


if __name__ == "__main__":
    print("org_config diff — see a live client's drift before re-applying")
    test_the_cli_writes_where_the_api_reads()
    test_diff_names_what_would_change()
    test_diff_after_apply_is_empty_apart_from_what_apply_cannot_touch()
    test_apply_warns_when_it_switches_a_live_flag_off()
    test_diff_exits_nonzero_when_out_of_step()
    print(f"\n{_passed} passed, {_failed} failed")
    raise SystemExit(1 if _failed else 0)
