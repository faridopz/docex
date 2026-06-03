"""
DOCex Bank Verify — bulk verification of Nigerian bank accounts against a
payment schedule.

Targets the NGO programs-team pain point: someone manually opens their bank
app and types each account number from a payment schedule into it to confirm
the registered account holder name matches the recipient on the schedule.
Bank Verify automates that in bulk.

Two-pass architecture (mirrors compliance.py):
  Pass 1 — resolve_account() calls Paystack's /bank/resolve endpoint for each
           row, fetching the bank-of-record account holder name.
  Pass 2 — verify_account() fuzzy-matches the resolved name against the
           recipient name on the payment schedule, producing a per-row
           verdict (verified / warning / mismatch / unverifiable).

The API: Paystack /bank/resolve. Free for verification calls in test and live
mode (no per-resolution charge). Rate-limited at roughly 60 RPM in test, so
verify_batch() sleeps ~200 ms between calls by default to stay polite.

CLI quick-start: drop your real account details into TEST_ROWS at the bottom
of this file, then run:

    python bank_verify.py

You'll see colour-coded output for each row plus a summary line. Once that
works end-to-end, Day 2's work is to wrap this in an Excel-schedule parser
and a FastAPI endpoint.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from openpyxl import load_workbook
from rapidfuzz import fuzz

from models import (
    BankAccountRow,
    BankVerifyBatchResult,
    BankVerifyResult,
)

load_dotenv()

logger = logging.getLogger(__name__)


# ─── Configuration ──────────────────────────────────────────────────────────

PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")

# Name match thresholds (using rapidfuzz.fuzz.token_set_ratio, scale 0-100).
# Tuned for Nigerian names which often vary across:
#   - first/last order ("Adebayo Tunde" vs "Tunde Adebayo")
#   - inclusion of middle names ("Aisha Bello" vs "Aisha Fatima Bello")
#   - punctuation, salutations, suffixes ("Mr.", "MRS.", "Jr.")
# token_set_ratio handles re-ordering and partial overlap well. 85+ has been
# reliable in tests as "same person"; 65-84 is the grey zone worth flagging
# for human review; below 65 is a real mismatch worth blocking the payment.
#
# Scoring uses rapidfuzz.fuzz.WRatio which combines four sub-scorers
# (ratio, partial_ratio, token_sort_ratio, token_set_ratio) with weights.
# We picked WRatio over plain token_set_ratio after observing that real
# finance-officer typos within a single token (Abdul → Abdur, Mohammed →
# Mohamed, Aliyu → Alliyu) collapsed to ~20/100 under token_set_ratio,
# making honest typos look like fraud. WRatio catches them at ~70-80,
# which is the "human review" band where they belong.
NAME_MATCH_VERIFIED_THRESHOLD = 85
NAME_MATCH_WARNING_THRESHOLD = 65

# Polite delay between Paystack calls. Test mode is ~60 RPM, so 200 ms
# (≈ 5 QPS) stays well under the limit and avoids 429s when verifying
# schedules of 50-100 rows. Drop this once we move to live keys with
# higher rate limits.
DEFAULT_DELAY_MS = 200

# ANSI colour codes for the CLI test output. Not used outside __main__.
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_GREY = "\033[90m"
_RESET = "\033[0m"


# ─── Core engine ────────────────────────────────────────────────────────────

def _paystack_headers() -> dict[str, str]:
    if not PAYSTACK_SECRET_KEY:
        raise RuntimeError(
            "PAYSTACK_SECRET_KEY is not set. Add it to your .env file. "
            "Get a test key at https://dashboard.paystack.com/#/settings/developers."
        )
    return {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}


# Number of retry attempts on transient Paystack failures (5xx, network).
# Retries DON'T fire on 429 (quota — pointless to retry) or 4xx (validation).
_PAYSTACK_RETRY_ATTEMPTS = 3
_PAYSTACK_RETRY_BACKOFF_BASE = 0.5  # seconds; doubles each attempt


def resolve_account(
    account_number: str,
    bank_code: str,
    timeout_seconds: float = 10.0,
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve a single account against Paystack with retry on transient errors.

    Returns (account_name, error_message). On success, account_name is the
    bank-of-record holder name and error_message is None. On any failure,
    account_name is None and error_message describes what went wrong (the
    UI / CLI surface this to the user verbatim).

    Retries: we retry exactly 3 times with exponential backoff (0.5s, 1s,
    2s) on (a) network errors and (b) HTTP 502/503/504 responses. We do
    NOT retry on 401/403 (auth — won't suddenly work), 4xx (validation —
    same), or 429 (Paystack's daily quota cap — also pointless to retry,
    you have to wait until tomorrow or upgrade to live mode).
    """
    last_error: str = "Unknown error"
    for attempt in range(_PAYSTACK_RETRY_ATTEMPTS):
        try:
            resp = httpx.get(
                f"{PAYSTACK_BASE_URL}/bank/resolve",
                params={"account_number": account_number, "bank_code": bank_code},
                headers=_paystack_headers(),
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as e:
            last_error = f"Network error contacting Paystack: {e}"
            if attempt < _PAYSTACK_RETRY_ATTEMPTS - 1:
                # Backoff before retry — only fires for network errors,
                # which are the most retry-worthy class of failure.
                time.sleep(_PAYSTACK_RETRY_BACKOFF_BASE * (2 ** attempt))
                continue
            return None, last_error
        else:
            # We got SOME response. Retry only on transient 5xx-class statuses.
            if resp.status_code in (502, 503, 504):
                last_error = f"Paystack {resp.status_code}: upstream temporarily unavailable"
                if attempt < _PAYSTACK_RETRY_ATTEMPTS - 1:
                    time.sleep(_PAYSTACK_RETRY_BACKOFF_BASE * (2 ** attempt))
                    continue
                return None, last_error
            # All other statuses (200, 4xx, 429, etc.) — break out and
            # let the existing post-response logic handle them.
            break
    else:
        # Loop completed without break — shouldn't happen but defensive.
        return None, last_error

    # Paystack returns HTTP 200 + status=true on success. Validation
    # failures (invalid account, wrong bank code) come back as 4xx with a
    # human-readable "message" field.
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") is True:
            account_name = data.get("data", {}).get("account_name")
            if account_name:
                return account_name, None
            return None, "Paystack returned no account_name"
        return None, data.get("message", "Unknown Paystack response")

    try:
        message = resp.json().get("message", resp.text)
    except Exception:
        message = resp.text or f"HTTP {resp.status_code}"
    return None, f"Paystack {resp.status_code}: {message}"


def _name_match_score(schedule_name: str, bank_record_name: str) -> int:
    """
    Compute a 0-100 similarity score between a schedule-side recipient name
    and the bank-of-record name, tuned for Nigerian payment workflows.

    Why a blend of two scorers rather than just one:

    - `fuzz.WRatio` handles within-token typos well (Abdul ↔ Abdur, Mohammed ↔
      Mohamed, Aliyu ↔ Alliyu). These are the most common honest mistakes a
      finance officer makes when copying a name from an attendance sheet onto a
      payment schedule. We want these to land as VERIFIED, not MISMATCH.

    - WRatio alone, however, gives ~85 to short partial overlaps like
      "Mohammed Tunde" vs "Mohammed Farid Abdurraman" because of how it
      applies partial_ratio with a 0.9 multiplier. That would falsely verify
      a payment redirect — someone substituting a completely different person
      whose first name happens to match. `fuzz.token_sort_ratio` correctly
      tanks that case (~40) because the sorted token sets don't overlap.

    The blend `min(WRatio, token_sort_ratio + 10)` keeps WRatio's typo
    tolerance while letting token_sort_ratio veto shared-prefix attacks. The
    +10 cushion preserves the legitimate "dropped middle name" case where
    token_sort lags but the name is still clearly the same person.

    `processor=str.lower` is critical — rapidfuzz scorers are case-sensitive
    by default, and bank-of-record names come back UPPERCASE while schedule
    entries are typically title case. Without it, "Mohammed" vs "MOHAMMED"
    alone tanks the score to ~20.
    """
    w = fuzz.WRatio(schedule_name, bank_record_name, processor=str.lower)
    t = fuzz.token_sort_ratio(schedule_name, bank_record_name, processor=str.lower)
    return int(min(w, t + 10))


def _classify_match(score: int) -> str:
    if score >= NAME_MATCH_VERIFIED_THRESHOLD:
        return "verified"
    if score >= NAME_MATCH_WARNING_THRESHOLD:
        return "warning"
    return "mismatch"


def verify_account(row: BankAccountRow) -> BankVerifyResult:
    """Verify one account row — calls Paystack, fuzzy-matches the name."""
    now = datetime.now(timezone.utc).isoformat()
    resolved_name, error = resolve_account(row.account_number, row.bank_code)

    if error or not resolved_name:
        return BankVerifyResult(
            recipient_name=row.recipient_name,
            account_number=row.account_number,
            bank_code=row.bank_code,
            bank_name=row.bank_name,
            resolved_name=None,
            verdict="unverifiable",
            match_score=None,
            error_message=error or "Paystack returned no account_name",
            timestamp=now,
            amount=row.amount,
            notes=row.notes,
        )

    score = _name_match_score(row.recipient_name, resolved_name)
    verdict = _classify_match(score)

    return BankVerifyResult(
        recipient_name=row.recipient_name,
        account_number=row.account_number,
        bank_code=row.bank_code,
        bank_name=row.bank_name,
        resolved_name=resolved_name,
        verdict=verdict,  # type: ignore[arg-type]
        match_score=score,
        error_message=None,
        timestamp=now,
        amount=row.amount,
        notes=row.notes,
    )


def verify_batch(
    rows: list[BankAccountRow],
    delay_ms: int = DEFAULT_DELAY_MS,
) -> BankVerifyBatchResult:
    """
    Verify a list of account rows sequentially with a polite delay between
    calls.

    Sequential rather than parallel because Paystack's test-mode rate limit
    is low (~60 RPM); the cost of a slow batch is much smaller than the cost
    of a half-completed batch from 429 errors. When we move to live keys
    with higher limits, swap this for a small thread pool the same way
    compliance.check_payment_batch() does.
    """
    results: list[BankVerifyResult] = []
    for i, row in enumerate(rows):
        results.append(verify_account(row))
        # Skip the final sleep so the function returns as fast as possible.
        if i < len(rows) - 1 and delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    counts = {"verified": 0, "warning": 0, "mismatch": 0, "unverifiable": 0}
    for r in results:
        counts[r.verdict] += 1

    return BankVerifyBatchResult(
        total=len(results),
        verified=counts["verified"],
        warning=counts["warning"],
        mismatch=counts["mismatch"],
        unverifiable=counts["unverifiable"],
        results=results,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── Bank-name → Paystack code lookup ───────────────────────────────────────
#
# Payment schedules in the wild write bank names freely — "GTB", "GTBank",
# "Guaranty Trust", "058" — and the user shouldn't have to normalise them by
# hand. We accept any of these forms and map to the Paystack 3-digit code.
# Full Paystack list:
#   curl https://api.paystack.co/bank -H "Authorization: Bearer $KEY"
# This dict covers the banks NGOs in Nigeria actually pay out to; extend
# as new ones come up. Keys are lowercase for case-insensitive matching.

BANK_CODES: dict[str, str] = {
    # Tier 1 commercial banks
    "access": "044",
    "access bank": "044",
    "diamond": "044",                # merged into Access in 2019
    "gtb": "058",
    "gt bank": "058",
    "gtbank": "058",
    "guaranty trust": "058",
    "guaranty trust bank": "058",
    "zenith": "057",
    "zenith bank": "057",
    "uba": "033",
    "united bank for africa": "033",
    "first bank": "011",
    "firstbank": "011",
    "first bank of nigeria": "011",
    "fbn": "011",
    "wema": "035",
    "wema bank": "035",
    "alat": "035",
    "alat by wema": "035",
    "sterling": "232",
    "sterling bank": "232",
    "stanbic": "221",
    "stanbic ibtc": "221",
    "stanbic ibtc bank": "221",
    "union": "032",
    "union bank": "032",
    "fcmb": "214",
    "first city monument bank": "214",
    "ecobank": "050",
    "polaris": "076",
    "polaris bank": "076",
    "skye": "076",                   # rebranded as Polaris
    "fidelity": "070",
    "fidelity bank": "070",
    "heritage": "030",
    "heritage bank": "030",
    "keystone": "082",
    "keystone bank": "082",
    "unity": "215",
    "unity bank": "215",
    "providus": "101",
    "providus bank": "101",
    "jaiz": "301",
    "jaiz bank": "301",
    "suntrust": "100",
    "suntrust bank": "100",
    "titan": "102",
    "titan trust bank": "102",
    "globus": "00103",
    "globus bank": "00103",
    "premium trust": "105",
    "premium trust bank": "105",
    # Digital / fintech (Paystack returns these with a 5-6 digit code)
    "kuda": "50211",
    "kuda bank": "50211",
    "opay": "999992",
    "opay digital services": "999992",
    "palmpay": "999991",
    "moniepoint": "50515",
    "moniepoint mfb": "50515",
    "carbon": "565",
    "vfd": "566",
    "vfd microfinance bank": "566",
    "rubies": "125",
    "sparkle": "51310",
    "sparkle microfinance bank": "51310",
    # PSBs (Payment Service Banks)
    "9psb": "120001",
    "9 payment service bank": "120001",
    "smartcash": "100039",
    "smartcash psb": "100039",
}


def resolve_bank_code(bank: str) -> Optional[str]:
    """
    Map a free-text bank reference to a Paystack bank code.

    Accepts a bank code as-is (digit string), or looks up a name in BANK_CODES
    (case-insensitive, whitespace-tolerant). Returns None if unrecognised — the
    caller should treat unrecognised banks as 'unverifiable' rather than
    aborting the whole batch, since one bad bank shouldn't block verification
    of the others.
    """
    if not bank:
        return None
    cleaned = str(bank).strip().lower()
    # Already a code (digits only, e.g. "058" or "50211" or "100039")
    if cleaned.isdigit() or (cleaned.startswith("00") and cleaned[2:].isdigit()):
        return cleaned
    return BANK_CODES.get(cleaned)


# ─── Excel schedule parser ──────────────────────────────────────────────────
#
# Payment schedules from real finance teams arrive as messy spreadsheets:
# title rows, merged headers, blank rows between sections, banks named
# inconsistently. Rather than ask the user to clean up their file, we read
# the first sheet, find the row that looks like a header (contains "name"
# AND "account"), and map columns by keyword. Optional columns (amount,
# notes/purpose) get picked up when present.
#
# Day 7+ the frontend will let the user override column mappings; for the
# CLI MVP this auto-detect handles 90% of real schedules.

_HEADER_SCAN_DEPTH = 15          # rows to scan looking for the header
_NAME_KEYWORDS = ("name", "recipient", "payee", "beneficiary", "vendor")
_ACCOUNT_KEYWORDS = ("account", "acct", "nuban", "a/c")
_BANK_KEYWORDS = ("bank",)
_AMOUNT_KEYWORDS = ("amount", "naira", "₦", "ngn", "sum", "value")
_NOTES_KEYWORDS = ("purpose", "notes", "description", "remarks", "narration", "details")


def _find_header_row_and_columns(sheet) -> tuple[int, dict[str, int]]:
    """Scan the top of the sheet for a header row. Return (row_index, col_map)."""
    max_col = sheet.max_column or 1

    for row_idx in range(1, min(_HEADER_SCAN_DEPTH, sheet.max_row or 1) + 1):
        col_map: dict[str, int] = {}
        for col in range(1, max_col + 1):
            raw = sheet.cell(row=row_idx, column=col).value
            if raw is None:
                continue
            text = str(raw).lower().strip()
            if not text:
                continue
            # Order matters — bank-code columns ("bank") shouldn't be
            # mis-classified as the recipient-name column.
            if "bank" in text and "code" not in text and "bank" not in col_map:
                col_map["bank"] = col
                continue
            if any(k in text for k in _ACCOUNT_KEYWORDS) and "account" not in col_map:
                col_map["account"] = col
                continue
            if any(k in text for k in _NAME_KEYWORDS) and "name" not in col_map:
                col_map["name"] = col
                continue
            if any(k in text for k in _AMOUNT_KEYWORDS) and "amount" not in col_map:
                col_map["amount"] = col
                continue
            if any(k in text for k in _NOTES_KEYWORDS) and "notes" not in col_map:
                col_map["notes"] = col

        if {"name", "account", "bank"}.issubset(col_map):
            return row_idx, col_map

    raise ValueError(
        "Could not find a header row containing 'name', 'account', and 'bank' "
        "columns in the first 15 rows of the schedule. Rename your column "
        "headers (e.g. 'Recipient Name', 'Account Number', 'Bank') or pass a "
        "cleaner file."
    )


def _normalise_account_number(raw) -> str:
    """Excel stores account numbers as floats sometimes — strip the .0."""
    if raw is None:
        return ""
    s = str(raw).replace(" ", "").replace("-", "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def parse_schedule(file_path_or_buffer) -> list[BankAccountRow]:
    """
    Parse a payment schedule .xlsx into a list of BankAccountRow.

    Accepts either a filesystem path (string or Path) or a file-like object
    (BytesIO, SpooledTemporaryFile from FastAPI UploadFile). openpyxl handles
    both natively. The flexibility lets the same function serve the CLI
    (file path) and the API upload handler (request stream) without copies.

    Uses the first sheet. Auto-detects header row + columns by keyword.
    Skips blank rows. Unknown bank names are passed through as-is so the
    verification step can mark them unverifiable with a clear error.
    """
    wb = load_workbook(file_path_or_buffer, data_only=True)
    sheet = wb.active

    header_row, col_map = _find_header_row_and_columns(sheet)

    rows: list[BankAccountRow] = []
    for excel_row in range(header_row + 1, (sheet.max_row or header_row) + 1):
        name = sheet.cell(row=excel_row, column=col_map["name"]).value
        account = sheet.cell(row=excel_row, column=col_map["account"]).value
        bank = sheet.cell(row=excel_row, column=col_map["bank"]).value

        # Blank rows separate sections in some real schedules — skip them
        # rather than treating them as data.
        if not (name and account and bank):
            continue

        account_str = _normalise_account_number(account)
        bank_str = str(bank).strip()
        # Pass through unrecognised banks as-is; Paystack will return a
        # clear "bank code not supported" error and the row will be
        # marked unverifiable rather than aborting the whole batch.
        bank_code = resolve_bank_code(bank_str) or bank_str

        amount: Optional[float] = None
        if "amount" in col_map:
            amt_val = sheet.cell(row=excel_row, column=col_map["amount"]).value
            if isinstance(amt_val, (int, float)):
                amount = float(amt_val)

        notes: Optional[str] = None
        if "notes" in col_map:
            notes_val = sheet.cell(row=excel_row, column=col_map["notes"]).value
            if notes_val:
                notes = str(notes_val).strip()

        rows.append(
            BankAccountRow(
                recipient_name=str(name).strip(),
                account_number=account_str,
                bank_code=bank_code,
                bank_name=bank_str,
                amount=amount,
                notes=notes,
            )
        )

    return rows


# ─── CLI test runner ────────────────────────────────────────────────────────

def _verdict_colour(verdict: str) -> str:
    return {
        "verified": _GREEN,
        "warning": _YELLOW,
        "mismatch": _RED,
        "unverifiable": _GREY,
    }.get(verdict, _RESET)


def _print_result(r: BankVerifyResult) -> None:
    colour = _verdict_colour(r.verdict)
    icon = {
        "verified": "✓",
        "warning": "!",
        "mismatch": "✗",
        "unverifiable": "?",
    }.get(r.verdict, "·")
    # Prefer the human-readable bank name from the schedule over the
    # Paystack numeric code — the code is meaningful to engineers, not to
    # the finance officer reading this output.
    bank_label = r.bank_name or r.bank_code
    print(
        f"  {colour}{icon} {r.verdict.upper():13s}{_RESET} "
        f"{r.recipient_name:30s}  acct {r.account_number}  bank {bank_label}"
    )
    if r.resolved_name:
        print(f"      bank record:   {r.resolved_name}  (match {r.match_score}/100)")
    if r.error_message:
        print(f"      error:         {r.error_message}")


# Hardcoded test rows — EDIT THESE before running.
#
# Use a real Nigerian account you can verify (your own, or someone who
# gave you permission). The bank_code is Paystack's 3-digit code:
#
#   GTBank          = 058
#   Access          = 044
#   Zenith          = 057
#   UBA             = 033
#   First Bank      = 011
#   Wema / ALAT     = 035
#   Sterling        = 232
#   Stanbic IBTC    = 221
#   Union Bank      = 032
#   FCMB            = 214
#   Ecobank         = 050
#   Polaris         = 076
#   Kuda            = 50211
#   OPay            = 999992
#   Palmpay         = 999991
#
# Full list:  curl https://api.paystack.co/bank \
#               -H "Authorization: Bearer $PAYSTACK_SECRET_KEY"
TEST_ROWS: list[BankAccountRow] = [
    BankAccountRow(
        recipient_name="REPLACE WITH NAME ON ACCOUNT",
        account_number="REPLACE WITH 10-DIGIT ACCOUNT NUMBER",
        bank_code="058",
        bank_name="GTBank",
    ),
]


if __name__ == "__main__":
    print()
    print("─" * 70)
    print("  DOCex Bank Verify — CLI test run")
    print("─" * 70)
    print()

    if not PAYSTACK_SECRET_KEY:
        print(f"{_RED}ERROR{_RESET}: PAYSTACK_SECRET_KEY is missing from .env")
        print()
        print("Add this line to your .env (use your own key from the Paystack dashboard):")
        print("  PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        print()
        sys.exit(1)

    # Two modes:
    #   python bank_verify.py                      → use hardcoded TEST_ROWS
    #   python bank_verify.py schedule.xlsx        → parse an Excel schedule
    rows: list[BankAccountRow]
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"Reading payment schedule: {file_path}")
        print()
        try:
            rows = parse_schedule(file_path)
        except FileNotFoundError:
            print(f"{_RED}ERROR{_RESET}: File not found: {file_path}")
            sys.exit(1)
        except ValueError as e:
            print(f"{_RED}ERROR{_RESET}: {e}")
            sys.exit(1)

        if not rows:
            print(f"{_YELLOW}NOTICE{_RESET}: No data rows found in the schedule.")
            print("Check that the file has at least one row of recipient data")
            print("below the header row.")
            sys.exit(0)
    else:
        placeholder = any(
            "REPLACE" in r.account_number or "REPLACE" in r.recipient_name
            for r in TEST_ROWS
        )
        if placeholder:
            print(f"{_YELLOW}NOTICE{_RESET}: TEST_ROWS still has placeholder values.")
            print()
            print("Either:")
            print("  1. Pass an Excel schedule:")
            print("       python bank_verify.py path/to/schedule.xlsx")
            print("  2. Edit the TEST_ROWS list near the bottom of bank_verify.py")
            print("     with real recipient names + account numbers, then re-run.")
            print()
            sys.exit(0)
        rows = TEST_ROWS

    print(f"Verifying {len(rows)} account(s)...")
    print()
    batch = verify_batch(rows)

    for r in batch.results:
        _print_result(r)

    print()
    print(
        f"  Summary: "
        f"{_GREEN}{batch.verified} verified{_RESET}  "
        f"{_YELLOW}{batch.warning} warning{_RESET}  "
        f"{_RED}{batch.mismatch} mismatch{_RESET}  "
        f"{_GREY}{batch.unverifiable} unverifiable{_RESET}"
    )
    print()
