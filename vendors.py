"""
Vendor register — who we are allowed to pay, and whether we have checked them.

NEEM asked for two things by name: verify a vendor's tax identification number,
and verify that a bank account belongs to who we think it belongs to. Both are
the same underlying control: **before money moves, confirm the payee is real
and is who the invoice says they are.**

Two very different kinds of check, and the difference matters:

BANK ACCOUNT — verifiable, live, free.
    Paystack's /bank/resolve returns the account holder name registered with
    the bank. Compare it to the vendor name on file. This is a genuine external
    verification: a diverted-payment fraud, where an invoice arrives with an
    altered account number, fails it. bank_verify.py already does this well and
    is reused here rather than reimplemented.

TAX ID — NOT verifiable for free, and this module refuses to pretend otherwise.
    There is no free official API. Nigeria's Joint Tax Board became the Joint
    Revenue Board in January 2026; the FIRS and JTB portals are web forms, not
    developer endpoints, and the commercial KYB providers (Dojah, YouVerify and
    similar) charge per lookup. So a TIN check here has two levels, and they
    are labelled differently on purpose:

      * FORMAT  — offline. The number is structurally capable of being a TIN.
                  This catches a typo, a phone number typed into the wrong
                  field, and a blank pretending to be a value. It does NOT mean
                  the TIN exists or belongs to this vendor, and the verdict
                  says so in those words.
      * LOOKUP  — a real check against a provider, when one is configured.
                  Off by default. Costs money per call.

    Reporting a format check as "verified" would be the single most dangerous
    thing this module could do: an auditor asking "did you verify their TIN"
    would get a yes that means nothing. So the format verdict is
    `format_ok`, never `verified`, and the distinction survives all the way to
    the screen.

Storage is org-scoped. No LLM: a name comparison is fuzzy string matching, and
a tax number is a regular expression.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

import store

_VENDORS = "vendors"


class VerificationStatus(str, Enum):
    UNCHECKED = "unchecked"
    # Bank: the bank's own record matches the name we hold.
    VERIFIED = "verified"
    # Bank: resolved, but the names differ enough to need a human.
    MISMATCH = "mismatch"
    # Bank: names differ in a way that is probably just formatting.
    WARNING = "warning"
    # Could not reach the bank / no key configured / invalid account.
    UNVERIFIABLE = "unverifiable"
    # TIN only: structurally valid. NOT a confirmation that it exists.
    FORMAT_OK = "format_ok"
    # TIN or bank: definitely wrong.
    INVALID = "invalid"


class VendorError(ValueError):
    """Invalid vendor record — callers map this to HTTP 4xx."""


class BankCheck(BaseModel):
    status: VerificationStatus = VerificationStatus.UNCHECKED
    account_number: str = ""
    bank_code: str = ""
    bank_name: str = ""
    resolved_name: str = ""          # what the bank says
    match_score: float = 0.0         # 0–100 similarity to the vendor name
    checked_at: str = ""
    checked_by: str = ""
    message: str = ""


class TaxIdCheck(BaseModel):
    status: VerificationStatus = VerificationStatus.UNCHECKED
    tin: str = ""
    # "format" or the name of the provider that answered. Kept separate from
    # `status` so nobody can read a format check as an external confirmation.
    method: str = ""
    registered_name: str = ""        # only ever set by a real lookup
    checked_at: str = ""
    checked_by: str = ""
    message: str = ""

    @property
    def externally_verified(self) -> bool:
        """True only when a provider confirmed it. A format check is False."""
        return (self.status == VerificationStatus.VERIFIED
                and self.method not in ("", "format"))


class Vendor(BaseModel):
    id: str
    org_id: str = ""
    name: str
    trading_name: str = ""
    tin: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    category: str = ""
    active: bool = True
    blocked: bool = False
    blocked_reason: str = ""

    bank: BankCheck = Field(default_factory=BankCheck)
    tax: TaxIdCheck = Field(default_factory=TaxIdCheck)

    created_at: str = ""
    created_by: str = ""
    updated_at: str = ""

    @property
    def fully_verified(self) -> bool:
        """Bank account confirmed AND a tax id that was actually looked up.

        A format-checked TIN does not count. That is the whole point of the
        distinction — see the module docstring.
        """
        return (self.bank.status == VerificationStatus.VERIFIED
                and self.tax.externally_verified)

    @property
    def payment_ready(self) -> bool:
        """The bar for releasing money: not blocked, and the account confirmed.

        Deliberately does NOT require an externally verified TIN, because for
        most organisations no provider is configured and requiring one would
        block every payment. The tax position is reported separately so a
        client can tighten it when they are ready to pay for lookups.
        """
        return (not self.blocked and self.active
                and self.bank.status == VerificationStatus.VERIFIED)


# ─── helpers ────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _norm_name(s: str) -> str:
    """Strip the noise that makes two spellings of one company look different."""
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    noise = {"LTD", "LIMITED", "PLC", "NIG", "NIGERIA", "ENTERPRISES",
             "ENTERPRISE", "COMPANY", "CO", "AND", "THE", "INTL",
             "INTERNATIONAL", "SERVICES", "SERVICE", "VENTURES", "GLOBAL",
             "RESOURCES", "CONCEPTS"}
    words = [w for w in s.split() if w and w not in noise]
    return " ".join(words)


# ─── tax identification number ──────────────────────────────────────────────
#
# Nigerian TINs are issued in a few shapes and the format has changed over
# time. Rather than assert one canonical pattern (and reject valid numbers),
# this accepts the shapes actually seen and rejects what is definitely not a
# TIN: too short, too long, all-identical digits, or a phone number.

_TIN_PATTERNS = (
    re.compile(r"^\d{10}$"),                 # 10-digit JTB/JRB style
    re.compile(r"^\d{8}-\d{4}$"),            # 8 digits + branch suffix
    re.compile(r"^\d{12}$"),                 # 12-digit variant
    re.compile(r"^\d{11}$"),                 # 11-digit variant
)


def normalise_tin(raw: str) -> str:
    """Strip spaces and stray punctuation, keep digits and a single hyphen."""
    s = re.sub(r"[^0-9-]", "", (raw or "").strip())
    return re.sub(r"-{2,}", "-", s).strip("-")


def check_tin_format(raw: str) -> TaxIdCheck:
    """Offline structural check. Never claims the number exists.

    Explicitly rejects a Nigerian mobile number, which is the most common thing
    typed into a TIN field by mistake — 11 digits starting 070/080/081/090/091
    is a phone, and would otherwise sail through the 11-digit pattern.
    """
    tin = normalise_tin(raw)
    now = _now_iso()

    if not tin:
        # Distinguish "nobody entered one" from "someone entered something that
        # is not a number at all". Normalising strips letters, so a TIN field
        # containing a company name would otherwise come back as "none on
        # file" — quietly reporting the user's mistake as an absence, which is
        # how a bad value survives into a payment.
        if (raw or "").strip():
            return TaxIdCheck(
                status=VerificationStatus.INVALID, tin="", method="format",
                checked_at=now,
                message=(f"'{raw.strip()}' contains no digits, so it cannot be "
                         "a tax ID."))
        return TaxIdCheck(status=VerificationStatus.UNCHECKED, tin="",
                          method="format", checked_at=now,
                          message="No tax identification number on file.")

    digits = tin.replace("-", "")
    if re.match(r"^0(70|80|81|90|91)\d{8}$", digits):
        return TaxIdCheck(
            status=VerificationStatus.INVALID, tin=tin, method="format",
            checked_at=now,
            message="This is a Nigerian mobile number, not a tax ID.")
    if len(set(digits)) == 1:
        return TaxIdCheck(
            status=VerificationStatus.INVALID, tin=tin, method="format",
            checked_at=now,
            message="Every digit is the same — this is a placeholder, not a TIN.")
    if not any(p.match(tin) for p in _TIN_PATTERNS):
        return TaxIdCheck(
            status=VerificationStatus.INVALID, tin=tin, method="format",
            checked_at=now,
            message=(f"'{tin}' is not a recognised TIN format. Expected 10, 11 "
                     "or 12 digits, or 8 digits with a 4-digit branch suffix."))

    return TaxIdCheck(
        status=VerificationStatus.FORMAT_OK, tin=tin, method="format",
        checked_at=now,
        message=("Format is valid. This has NOT been checked against the tax "
                 "authority — it confirms the number is well-formed, not that "
                 "it exists or belongs to this vendor."))


def tin_lookup_available() -> bool:
    """True when a paid TIN lookup provider is configured."""
    return bool(os.environ.get("DOCEX_TIN_PROVIDER", "").strip()
                and os.environ.get("DOCEX_TIN_API_KEY", "").strip())


def verify_tin(raw: str, *, checked_by: str = "") -> TaxIdCheck:
    """Format-check always; a real lookup only when a provider is configured.

    The provider call is deliberately left as an explicit integration point
    rather than a guessed implementation: each vendor's request and response
    shape differs, and inventing one would produce code that looks finished and
    fails on first contact. When a client wants live lookups, wire the provider
    here against their documentation and their key.
    """
    result = check_tin_format(raw)
    result.checked_by = checked_by
    if result.status == VerificationStatus.INVALID or not result.tin:
        return result

    if not tin_lookup_available():
        return result

    provider = os.environ["DOCEX_TIN_PROVIDER"].strip()
    result.message = (
        f"Format is valid. Live lookup via '{provider}' is configured but not "
        "implemented — see vendors.verify_tin(). Until it is, treat this as a "
        "format check only.")
    return result


# ─── bank account ───────────────────────────────────────────────────────────


def verify_bank_account(
    vendor_name: str,
    account_number: str,
    bank_code: str,
    *,
    checked_by: str = "",
    bank_name: str = "",
) -> BankCheck:
    """Ask the bank who owns this account, and compare it to the vendor.

    This is the control that catches diverted-payment fraud: an invoice arrives
    from a real supplier with an altered account number, and the bank's own
    record shows a different name. Nothing else in the approval chain would
    notice, because every other field is genuine.
    """
    now = _now_iso()
    account_number = re.sub(r"\D", "", account_number or "")
    if len(account_number) != 10:
        return BankCheck(
            status=VerificationStatus.INVALID, account_number=account_number,
            bank_code=bank_code, bank_name=bank_name, checked_at=now,
            checked_by=checked_by,
            message="A Nigerian account number is 10 digits.")

    try:
        import bank_verify
        from rapidfuzz import fuzz
    except ImportError as exc:                              # pragma: no cover
        return BankCheck(
            status=VerificationStatus.UNVERIFIABLE, account_number=account_number,
            bank_code=bank_code, bank_name=bank_name, checked_at=now,
            checked_by=checked_by,
            message=f"Bank verification is unavailable: {exc}")

    resolved, error = bank_verify.resolve_account(account_number, bank_code)
    if resolved is None:
        return BankCheck(
            status=VerificationStatus.UNVERIFIABLE, account_number=account_number,
            bank_code=bank_code, bank_name=bank_name, checked_at=now,
            checked_by=checked_by,
            message=error or "The bank could not resolve this account.")

    score = float(fuzz.token_sort_ratio(_norm_name(vendor_name),
                                        _norm_name(resolved)))
    if score >= 85:
        status, msg = (VerificationStatus.VERIFIED,
                       f"The bank's record matches '{vendor_name}'.")
    elif score >= 65:
        status, msg = (
            VerificationStatus.WARNING,
            f"The bank has this account as '{resolved}', which is close to "
            f"'{vendor_name}' but not the same. Confirm before paying.")
    else:
        status, msg = (
            VerificationStatus.MISMATCH,
            f"The bank has this account as '{resolved}', NOT '{vendor_name}'. "
            "Do not pay until this is explained — an altered account number on "
            "a genuine invoice looks exactly like this.")

    return BankCheck(status=status, account_number=account_number,
                     bank_code=bank_code, bank_name=bank_name,
                     resolved_name=resolved, match_score=round(score, 1),
                     checked_at=now, checked_by=checked_by, message=msg)


# ─── register ───────────────────────────────────────────────────────────────


def create(org_id: str, *, name: str, tin: str = "", created_by: str = "",
           **fields) -> Vendor:
    """Add a vendor. The TIN is format-checked immediately — free, instant, and
    it stops a typo entering the register in the first place."""
    org = store.require_org(org_id)
    if not (name or "").strip():
        raise VendorError("A vendor needs a name.")

    existing = find_by_name(org, name)
    if existing is not None:
        raise VendorError(
            f"'{existing.name}' is already in the register. Edit that record "
            "rather than creating a second — two records for one supplier is "
            "how duplicate payments happen.")

    v = Vendor(id=uuid.uuid4().hex[:12], org_id=org, name=name.strip(),
               tin=normalise_tin(tin), created_by=created_by,
               created_at=_now_iso(), updated_at=_now_iso(),
               **{k: val for k, val in fields.items() if k in Vendor.model_fields})
    if v.tin:
        v.tax = check_tin_format(v.tin)
        v.tax.checked_by = created_by
    return _save(org, v)


def run_checks(org_id: str, vendor_id: str, *, account_number: str = "",
               bank_code: str = "", bank_name: str = "",
               checked_by: str = "") -> Vendor:
    """Re-run both checks and store the results on the vendor."""
    org = store.require_org(org_id)
    v = get(org, vendor_id)
    if v is None:
        raise VendorError(f"Vendor '{vendor_id}' not found.")

    if v.tin:
        v.tax = verify_tin(v.tin, checked_by=checked_by)

    account = account_number or v.bank.account_number
    code = bank_code or v.bank.bank_code
    if account and code:
        v.bank = verify_bank_account(v.name, account, code,
                                     checked_by=checked_by,
                                     bank_name=bank_name or v.bank.bank_name)
    return _save(org, v)


def block(org_id: str, vendor_id: str, *, reason: str, actor: str = "") -> Vendor:
    """Stop payments to this vendor. A reason is required and kept."""
    if not (reason or "").strip():
        raise VendorError("Blocking a vendor requires a written reason.")
    org = store.require_org(org_id)
    v = get(org, vendor_id)
    if v is None:
        raise VendorError(f"Vendor '{vendor_id}' not found.")
    v.blocked = True
    v.blocked_reason = f"{reason.strip()} — {actor or 'unknown'} on {_now_iso()[:10]}"
    return _save(org, v)


def unblock(org_id: str, vendor_id: str) -> Vendor:
    org = store.require_org(org_id)
    v = get(org, vendor_id)
    if v is None:
        raise VendorError(f"Vendor '{vendor_id}' not found.")
    v.blocked = False
    v.blocked_reason = ""
    return _save(org, v)


def _save(org_id: str, v: Vendor) -> Vendor:
    v.updated_at = _now_iso()
    store.get_store().put(org_id, _VENDORS, v.id, v.model_dump())
    return v


def get(org_id: str, vendor_id: str) -> Optional[Vendor]:
    raw = store.get_store().get(store.require_org(org_id), _VENDORS, vendor_id)
    return Vendor.model_validate(raw) if raw else None


def list_vendors(org_id: str, *, active_only: bool = False) -> list[Vendor]:
    org = store.require_org(org_id)
    out: list[Vendor] = []
    for raw in store.get_store().list(org, _VENDORS):
        try:
            v = Vendor.model_validate(raw)
        except Exception:
            continue
        if active_only and not v.active:
            continue
        out.append(v)
    return sorted(out, key=lambda v: v.name.lower())


def find_by_name(org_id: str, name: str) -> Optional[Vendor]:
    """Match on the normalised name, so 'Acme Ltd' finds 'ACME LIMITED'."""
    target = _norm_name(name)
    if not target:
        return None
    return next((v for v in list_vendors(org_id)
                 if _norm_name(v.name) == target), None)


def register_summary(org_id: str) -> dict:
    """What a finance lead needs to know about the register at a glance."""
    vendors = list_vendors(org_id)
    return {
        "total": len(vendors),
        "blocked": len([v for v in vendors if v.blocked]),
        "bank_verified": len([v for v in vendors
                              if v.bank.status == VerificationStatus.VERIFIED]),
        "bank_mismatch": len([v for v in vendors
                              if v.bank.status == VerificationStatus.MISMATCH]),
        "bank_unchecked": len([v for v in vendors
                               if v.bank.status == VerificationStatus.UNCHECKED]),
        "tin_present": len([v for v in vendors if v.tin]),
        "tin_invalid": len([v for v in vendors
                            if v.tax.status == VerificationStatus.INVALID]),
        "tin_externally_verified": len([v for v in vendors
                                        if v.tax.externally_verified]),
        "payment_ready": len([v for v in vendors if v.payment_ready]),
        # Said plainly so nobody reads "TIN checked" as "TIN confirmed".
        "tin_lookup_configured": tin_lookup_available(),
    }
