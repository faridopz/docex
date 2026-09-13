#!/usr/bin/env python3
"""
Locked out of the NEEM admin account? This issues a fresh one-time password
the same way an admin resetting another user's password does — it does NOT
set a password for you; it prints a temporary one you use once, then the
app forces you to choose your own on first login (the same flow every NEEM
user goes through).

Run against production:
    DOCEX_DATABASE_URL='postgresql://...' python3 reset_neem_admin_password.py [email]

Defaults to admin@neem.org (the address in profiles/neem.json) if no email
is given.
"""
from __future__ import annotations

import sys

import store

store.configure_from_env()

import auth  # noqa: E402

ORG_ID = "neem"


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else "admin@neem.org"

    user = auth.get_by_email(email, ORG_ID)
    if user is None:
        print(f"No user '{email}' found in org '{ORG_ID}'.")
        print("Check the email, or list accounts another way if you're unsure "
              "which address the admin used.")
        return 1

    if not user.active:
        print(f"'{email}' exists but is deactivated. Reactivate it first "
              "(this script only resets a password, it doesn't reactivate).")
        return 1

    _, temp_password = auth.reset_password(user.id, ORG_ID, reset_by="reset_neem_admin_password.py")

    print(f"Reset for {email} ({user.role}, {user.department}).")
    print(f"\nTemporary password: {temp_password}")
    print("\nThis works once. Sign in with it, and you'll be forced to set your "
          "own password immediately — same as every user's first login. Any "
          "session that account had is now ended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
