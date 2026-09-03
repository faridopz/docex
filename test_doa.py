"""
Delegation of Authority tests.

The failure modes that matter here are quiet ones: an amount that no band
covers (the requisition sits forever and nobody knows why), two bands claiming
the same amount (an argument in front of an auditor), and an approver taking a
turn that wasn't theirs. Boundary arithmetic gets its own section because
"which band is exactly ₦100,000 in?" is the question that gets asked.

Run: python test_doa.py
"""
from __future__ import annotations

import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="docex-doa-")

import store  # noqa: E402

store.set_store(store.JsonFileStore(_TMP))

import doa  # noqa: E402

_passed = _failed = 0


def check(label: str, cond: bool) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failed += 1
        print(f"  FAIL {label}")


def expect_error(label: str, fn) -> None:
    try:
        fn()
        check(label, False)
    except doa.DOAError:
        check(label, True)


def eva_matrix() -> doa.DOAMatrix:
    """EVA's shape: Compliance always, Finance always, TLFA raises and pays,
    ED authorises above a threshold."""
    return doa.DOAMatrix(
        org_id="eva", currency="NGN",
        final_authority="ed",
        bands=[
            doa.DOABand(label="Routine", min_amount=0, max_amount=500_000,
                        approvers=["compliance", "finance", "tlfa"]),
            doa.DOABand(label="Major", min_amount=500_000, max_amount=doa.UNBOUNDED,
                        approvers=["compliance", "finance", "tlfa"]),
        ],
    )


# ─── validation ─────────────────────────────────────────────────────────────


def test_valid_matrix_passes() -> None:
    print("\nA well-formed matrix validates")
    check("no problems", doa.validate(eva_matrix()) == [])


def test_gaps_are_caught() -> None:
    print("\nA gap between bands is caught — that amount would stall forever")
    m = doa.DOAMatrix(bands=[
        doa.DOABand(label="Low", min_amount=0, max_amount=100_000, approvers=["finance"]),
        doa.DOABand(label="High", min_amount=250_000, max_amount=doa.UNBOUNDED,
                    approvers=["finance", "ed"]),
    ])
    problems = doa.validate(m)
    check("gap reported", any("gap between" in p for p in problems))
    check("the gap range is named", any("100,000.00" in p and "250,000.00" in p for p in problems))


def test_overlaps_are_caught() -> None:
    print("\nOverlapping bands are caught — two chains for one amount")
    m = doa.DOAMatrix(bands=[
        doa.DOABand(label="A", min_amount=0, max_amount=200_000, approvers=["finance"]),
        doa.DOABand(label="B", min_amount=100_000, max_amount=doa.UNBOUNDED, approvers=["ed"]),
    ])
    check("overlap reported", any("overlaps" in p for p in doa.validate(m)))


def test_uncovered_extremes_are_caught() -> None:
    print("\nBoth ends of the range must be covered")
    m = doa.DOAMatrix(bands=[
        doa.DOABand(label="Middle", min_amount=1000, max_amount=5000, approvers=["finance"]),
    ])
    problems = doa.validate(m)
    check("nothing below the first band", any("below" in p for p in problems))
    check("nothing above the last band", any("at or above" in p for p in problems))


def test_structural_mistakes_are_caught() -> None:
    print("\nStructural mistakes in a band")
    check("empty matrix rejected", doa.validate(doa.DOAMatrix()) != [])

    m = doa.DOAMatrix(bands=[doa.DOABand(label="Empty", approvers=[],
                                         max_amount=doa.UNBOUNDED)])
    check("a band with no approvers is rejected",
          any("no approvers" in p for p in doa.validate(m)))

    m = doa.DOAMatrix(bands=[doa.DOABand(label="Backwards", min_amount=5000,
                                         max_amount=1000, approvers=["finance"])])
    check("max below min is rejected",
          any("must exceed min_amount" in p for p in doa.validate(m)))

    m = doa.DOAMatrix(bands=[doa.DOABand(label="Dup", max_amount=doa.UNBOUNDED,
                                         approvers=["finance", "finance"])])
    check("a repeated approver is rejected",
          any("appears twice" in p for p in doa.validate(m)))

    m = eva_matrix()
    problems = doa.validate(m, known_departments={"compliance", "finance"})
    check("an approver that isn't a department is rejected",
          any("'tlfa' is not a department" in p for p in problems))
    check("a bad final_authority is rejected",
          any("final_authority 'ed'" in p for p in problems))


# ─── boundaries ─────────────────────────────────────────────────────────────


def test_band_boundaries_are_unambiguous() -> None:
    print("\nBoundaries: half-open ranges, so no amount is in two bands")
    m = eva_matrix()
    just_under = doa.resolve_with(m, 499_999.99)
    exactly = doa.resolve_with(m, 500_000)
    just_over = doa.resolve_with(m, 500_000.01)
    check("just under lands in Routine", just_under.band_label == "Routine")
    check("EXACTLY at the threshold lands in Major", exactly.band_label == "Major")
    check("just over lands in Major", just_over.band_label == "Major")
    check("zero is covered", doa.resolve_with(m, 0).band_label == "Routine")
    check("a very large amount is covered",
          doa.resolve_with(m, 9_999_999_999).band_label == "Major")


def test_no_band_is_a_loud_error() -> None:
    print("\nAn uncovered amount raises, and never returns an empty chain")
    # An empty chain downstream would read as "no approval needed", which is
    # the worst possible failure in a payments system.
    m = doa.DOAMatrix(bands=[
        doa.DOABand(label="Only", min_amount=1000, max_amount=2000, approvers=["finance"]),
    ])
    expect_error("below every band raises", lambda: doa.resolve_with(m, 10))
    expect_error("above every band raises", lambda: doa.resolve_with(m, 999_999))
    try:
        doa.resolve_with(m, 10)
    except doa.DOAError as exc:
        check("the message names the amount", "10.00" in str(exc))


# ─── chains ─────────────────────────────────────────────────────────────────


def test_final_authority_is_always_last_and_once() -> None:
    print("\nThe final authority ends every chain, exactly once")
    d = doa.resolve_with(eva_matrix(), 750_000)
    check("chain order", d.chain == ["compliance", "finance", "tlfa", "ed"])
    check("ED is last", d.final == "ed")
    check("compliance is first", d.first == "compliance")

    # ED already mid-chain: it must move to the end, not appear twice.
    m = doa.DOAMatrix(final_authority="ed", bands=[
        doa.DOABand(label="Odd", max_amount=doa.UNBOUNDED,
                    approvers=["ed", "finance"]),
    ])
    d = doa.resolve_with(m, 100)
    check("ED moved to the end", d.chain == ["finance", "ed"])
    check("ED appears once", d.chain.count("ed") == 1)

    # No final authority configured — the chain is exactly what the band says.
    m = doa.DOAMatrix(bands=[
        doa.DOABand(label="Plain", max_amount=doa.UNBOUNDED, approvers=["finance"]),
    ])
    check("no final authority leaves the chain alone",
          doa.resolve_with(m, 100).chain == ["finance"])


def test_payment_type_scoping() -> None:
    print("\nA payment type can demand a different chain at the same amount")
    # EVA's advance policies are separate documents from procurement for
    # exactly this reason: ₦300k of advance ≠ ₦300k of invoice.
    m = doa.DOAMatrix(final_authority="ed", bands=[
        doa.DOABand(label="General", min_amount=0, max_amount=doa.UNBOUNDED,
                    approvers=["finance"]),
        doa.DOABand(label="Advances", min_amount=0, max_amount=doa.UNBOUNDED,
                    payment_types=["advance"], approvers=["compliance", "finance", "tlfa"]),
    ])
    generic = doa.resolve_with(m, 300_000)
    advance = doa.resolve_with(m, 300_000, "advance")
    check("generic payment uses the general band", generic.band_label == "General")
    check("an advance uses the specific band", advance.band_label == "Advances")
    check("the advance chain is longer", len(advance.chain) > len(generic.chain))
    check("payment type is case-insensitive",
          doa.resolve_with(m, 300_000, "ADVANCE").band_label == "Advances")
    check("an unlisted type falls back to general",
          doa.resolve_with(m, 300_000, "invoice").band_label == "General")


# ─── enforcement ────────────────────────────────────────────────────────────


def test_approval_order_is_enforced() -> None:
    print("\nApprovers cannot take a turn that isn't theirs")
    d = doa.resolve_with(eva_matrix(), 750_000)   # compliance → finance → tlfa → ed

    ok, _ = doa.can_approve(d, "compliance", [])
    check("compliance can go first", ok)

    ok, why = doa.can_approve(d, "ed", [])
    check("ED cannot skip to the front", not ok)
    check("the refusal names who is next", "compliance" in why)

    ok, why = doa.can_approve(d, "tlfa", ["compliance"])
    check("TLFA cannot jump finance", not ok and "finance" in why)

    ok, _ = doa.can_approve(d, "finance", ["compliance"])
    check("finance goes second", ok)
    ok, _ = doa.can_approve(d, "ed", ["compliance", "finance", "tlfa"])
    check("ED goes last", ok)

    ok, why = doa.can_approve(d, "program", [])
    check("a department outside the chain is refused", not ok and "not in the approval chain" in why)

    ok, why = doa.can_approve(d, "", [])
    check("a blank department is refused", not ok)

    ok, why = doa.can_approve(d, "ed", ["compliance", "finance", "tlfa", "ed"])
    check("a completed chain accepts nobody", not ok and "already completed" in why)


def test_next_approver_walks_the_chain() -> None:
    print("\nnext_approver reports whose turn it is")
    d = doa.resolve_with(eva_matrix(), 750_000)
    check("nothing done -> compliance", doa.next_approver(d, []) == "compliance")
    check("one done -> finance", doa.next_approver(d, ["compliance"]) == "finance")
    check("three done -> ed",
          doa.next_approver(d, ["compliance", "finance", "tlfa"]) == "ed")
    check("all done -> None",
          doa.next_approver(d, ["compliance", "finance", "tlfa", "ed"]) is None)


# ─── persistence ────────────────────────────────────────────────────────────


def test_storage_refuses_a_broken_matrix() -> None:
    print("\nAn invalid matrix is never stored")
    broken = doa.DOAMatrix(bands=[
        doa.DOABand(label="Low", min_amount=0, max_amount=100, approvers=["finance"]),
        doa.DOABand(label="High", min_amount=5000, max_amount=doa.UNBOUNDED,
                    approvers=["finance"]),
    ])
    expect_error("set_matrix rejects a gap",
                 lambda: doa.set_matrix("brokenorg", broken, check_departments=False))
    check("nothing was written", doa.get_matrix("brokenorg") is None)


def test_round_trip_and_isolation() -> None:
    print("\nStores, reloads, and never leaks between orgs")
    doa.set_matrix("eva", eva_matrix(), check_departments=False)
    loaded = doa.get_matrix("eva")
    check("matrix round-trips", loaded is not None and len(loaded.bands) == 2)
    check("final authority survives", loaded.final_authority == "ed")
    check("resolves from storage", doa.resolve("eva", 750_000).final == "ed")

    check("another org has none", doa.get_matrix("neem") is None)
    expect_error("resolving without a matrix raises", lambda: doa.resolve("neem", 1000))

    other = doa.DOAMatrix(bands=[
        doa.DOABand(label="Flat", max_amount=doa.UNBOUNDED, approvers=["finance"]),
    ])
    doa.set_matrix("neem", other, check_departments=False)
    check("eva unchanged by neem's matrix", doa.resolve("eva", 750_000).chain[-1] == "ed")
    check("neem has its own", doa.resolve("neem", 750_000).chain == ["finance"])


def test_describe_is_readable() -> None:
    print("\ndescribe() is something a UI or an auditor can read")
    d = doa.describe("eva")
    check("configured", d["configured"] is True)
    check("bands sorted by amount", d["bands"][0]["label"] == "Routine")
    check("unbounded shown as null", d["bands"][-1]["max_amount"] is None)
    check("an unconfigured org says so", doa.describe("nobody")["configured"] is False)


def test_is_active_needs_both_flag_and_matrix() -> None:
    print("\nis_active() requires the flag AND a matrix")
    import org_config
    check("matrix without flag is inactive", doa.is_active("eva") is False)
    org_config.apply_profile({"org_id": "eva", "features": {"doa_matrix": True}})
    check("flag + matrix is active", doa.is_active("eva") is True)
    org_config.apply_profile({"org_id": "flagonly", "features": {"doa_matrix": True}})
    check("flag without matrix is inactive", doa.is_active("flagonly") is False)


def main() -> int:
    print("=" * 64)
    print("Delegation of Authority — who signs, at what amount")
    print("=" * 64)
    test_valid_matrix_passes()
    test_gaps_are_caught()
    test_overlaps_are_caught()
    test_uncovered_extremes_are_caught()
    test_structural_mistakes_are_caught()
    test_band_boundaries_are_unambiguous()
    test_no_band_is_a_loud_error()
    test_final_authority_is_always_last_and_once()
    test_payment_type_scoping()
    test_approval_order_is_enforced()
    test_next_approver_walks_the_chain()
    test_storage_refuses_a_broken_matrix()
    test_round_trip_and_isolation()
    test_describe_is_readable()
    test_is_active_needs_both_flag_and_matrix()
    print("\n" + "=" * 64)
    print(f"{_passed} passed, {_failed} failed")
    print("=" * 64)
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
