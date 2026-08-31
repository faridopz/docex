#!/usr/bin/env python3
"""
Create or reset a local admin account, so you can sign in and click around.

    python seed_admin.py                      # prompts for everything
    python seed_admin.py you@example.com      # prompts for the password only
    python seed_admin.py you@example.com --password 'somethinglong'

If the email already exists, this resets that account's password and promotes
it to admin rather than failing — which is what you actually want when you've
forgotten what you set last week.

This is a LOCAL developer tool. It needs shell access to the machine running
DOCex, which is the same access that could read the user files anyway, so it
opens no door that wasn't already open. It is deliberately not an API endpoint
and not reachable over the network. Nothing here weakens the sign-in path:
passwords still go through the same PBKDF2 hashing every other account uses.

To seed a throwaway account without touching your real one:

    DOCEX_USERS_DIR=/tmp/docex-users python seed_admin.py demo@docex.app
"""
from __future__ import annotations

import argparse
import getpass
import sys

import auth


def _pick_department() -> str:
    """Offer the org's configured departments; fall back to 'finance'."""
    try:
        import departments

        defined = departments.list_departments()
        keys = [d.key for d in defined] if defined else []
    except Exception:
        keys = []

    if not keys:
        return "finance"

    # Finance can both approve and pay, which is what you want for a walkthrough.
    default = "finance" if "finance" in keys else keys[0]

    print("\nDepartments configured on this instance:")
    for i, k in enumerate(keys, 1):
        marker = "  (default)" if k == default else ""
        print(f"  {i}. {k}{marker}")

    raw = input(f"\nDepartment [{default}]: ").strip()
    if not raw:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(keys):
        return keys[int(raw) - 1]
    if raw in keys:
        return raw
    print(f"  '{raw}' isn't one of those — using {default}.")
    return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or reset a local DOCex admin account."
    )
    parser.add_argument("email", nargs="?", help="Email to sign in with")
    parser.add_argument("--password", help="Password (prompted if omitted)")
    parser.add_argument("--name", help="Display name (defaults to the email handle)")
    parser.add_argument("--department", help="Department key, e.g. finance")
    args = parser.parse_args()

    print(f"Accounts directory: {auth._user_dir()}")

    email = (args.email or input("Email: ")).strip().lower()
    if "@" not in email:
        print("error: that doesn't look like an email address.", file=sys.stderr)
        return 1

    existing = auth.get_by_email(email)

    password = args.password
    if not password:
        password = getpass.getpass("Password (min 6 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("error: those two passwords don't match.", file=sys.stderr)
            return 1
    if len(password) < 6:
        print("error: password must be at least 6 characters.", file=sys.stderr)
        return 1

    if existing:
        # Reset rather than refuse. Forgetting the password you set while
        # testing is the single most likely reason to be running this.
        pw_hash, pw_salt = auth.hash_password(password)
        existing.password_hash = pw_hash
        existing.password_salt = pw_salt
        existing.role = "admin"
        existing.active = True
        auth._save(existing)
        print(f"\n✓ Reset the password for {email} and confirmed admin role.")
        print(f"  Department: {existing.department}")
    else:
        department = args.department or _pick_department()
        try:
            user = auth.create_user(
                email=email,
                name=args.name or "",
                password=password,
                department=department,
                role="admin",
            )
        except auth.AuthError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"\n✓ Created admin {user.email} in {user.department}.")

    print("\nNow sign in at http://localhost:3000/login")
    print("(admin + finance lets you approve AND record payment, so you can")
    print(" walk a requisition end to end on your own.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
