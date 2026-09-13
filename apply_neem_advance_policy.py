#!/usr/bin/env python3
"""
One-off, surgical fix for a live NEEM instance: apply the advance/retirement
escalation ladder from profiles/neem.json WITHOUT touching anything else.

Why this exists rather than re-running `org_config.py apply profiles/neem.json`:
apply_profile() replaces departments and the approval workflow WHOLESALE from
the profile file. If anything has been edited live since NEEM went live (e.g.
via the Org Settings screen), a full re-apply would silently overwrite that
back to whatever's committed in profiles/neem.json. This script touches
exactly one thing: the advance policy, which apply_profile() never actually
wired up until now (see the "apply_profile() never actually applied
advance_policy" commit) — so advance_retirement has been showing as an
enabled feature in the nav while doing nothing underneath: no ageing, no
block, no escalation.

Run against production:
    DOCEX_DATABASE_URL='postgresql://...' python3 apply_neem_advance_policy.py

Safe to run more than once (it just sets the policy to these exact values).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import store

store.configure_from_env()

import advances  # noqa: E402

PROFILE = json.loads((Path(__file__).parent / "profiles" / "neem.json").read_text())
ORG_ID = PROFILE["org_id"]
POLICY = PROFILE["advance_policy"]


def main() -> int:
    print(f"Applying advance policy to org '{ORG_ID}':")
    for k, v in POLICY.items():
        if not k.startswith("_"):
            print(f"  {k}: {v}")

    before = advances.get_policy(ORG_ID)
    print(f"\nBefore: enabled={before.enabled}")

    policy = advances.AdvancePolicy.model_validate(POLICY)
    saved = advances.set_policy(ORG_ID, policy)

    print(f"After:  enabled={saved.enabled}, retirement_days={saved.retirement_days}, "
          f"working_days={saved.working_days}, use_working_days={saved.use_working_days}, "
          f"collective_default_count={saved.collective_default_count}, "
          f"recover_at_month_end={saved.recover_at_month_end}")

    if not saved.enabled:
        print("\nFAIL — policy did not save as enabled.")
        return 1
    print("\nDone. The retirement clock and escalation ladder are now live for NEEM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
