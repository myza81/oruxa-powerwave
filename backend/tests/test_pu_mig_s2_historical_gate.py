"""PU-MIG S2 closeout -- the Voltage HISTORICAL gate over every input combination (108 cases), against an independent oracle.

The historical gate is what decides a raw Voltage result when the strict side-denominator resolver is NOT used: a base whose side is only a
label (a Source Default that stores `secondary` carries the nominal L-L voltage, never a Secondary denominator -- D-5) or a sample side that is
not strict. Owner rules (2026-11-26) checked here for every row:

  1. the denominator is never altered (`base_amount` identical);
  2. such a result is NEVER verified: no `verified_direct`, no `verified_converted`, no denominator side, no conversion, no ratio;
  3. a side that is not strict (unknown / inferred / unresolved / group conflict / no authority) behaves exactly as the raw-declaration gate;
  4. Recording Details' strict effective side may only ADD a block (a known mismatch with the base label); it never turns a result the
     raw declaration blocked into an allowed one, and never changes a compatible/unverified label into anything stronger.

The oracle below is written from the compatibility table (DEC-211) and does not import the code under test.
"""

from __future__ import annotations

import itertools

import pytest

from app.domain.per_unit import STATUS_BASE_REQUIRED, STATUS_CONFIGURED, PerUnitResolution
from app.domain.per_unit_reference import RawVoltageSideInputs, apply_source_reference
from app.domain.side_denominator import SampleSide, SideRatio

BASE_AMOUNT = 76210.2355330306
SIDES = ("primary", "secondary", "unknown")
SAMPLES = {
    "P": SampleSide("primary", None, "recording_declared"),
    "S": SampleSide("secondary", None, "recording_declared"),
    "unknown": SampleSide(None, "unresolved", None),
    "inferred": SampleSide(None, "inferred", "inferred"),
    "group_conflict": SampleSide(None, "group_conflict", None),
    "none": None,
}
STRICT = {"P": "primary", "S": "secondary"}
CASES = list(itertools.product((STATUS_CONFIGURED, STATUS_BASE_REQUIRED), SIDES, SIDES, SAMPLES))


def oracle_compatibility(measured: str, base: str) -> str:
    known = {s for s in (measured, base) if s != "unknown"}
    if known == {"primary", "secondary"}:
        return "incompatible"
    return "unverified" if "unknown" in (measured, base) else "compatible"


def resolution(status: str) -> PerUnitResolution:
    configured = status == STATUS_CONFIGURED
    return PerUnitResolution(
        status=status, profile_id="p", base_amount=BASE_AMOUNT if configured else None, base_unit="V",
        reason=None if configured else "not_configured",
    )                                                    # no base descriptor: the resolver is never used


def run(status: str, raw: str, base: str, sample: str):
    side = SAMPLES[sample]
    side_inputs = None if side is None else RawVoltageSideInputs(sample=side, ratio_for=lambda: SideRatio("not_configured", None, None, ()))
    return apply_source_reference(
        resolution(status), "Voltage", raw, voltage_group_config=type("G", (), {"base_reference_side": base})(), side_inputs=side_inputs)


def expected(status: str, raw: str, base: str, sample: str):
    """(status, compatibility, reported measurement side, verification state or None)"""
    by_raw = oracle_compatibility(raw, base)
    effective = STRICT.get(sample)
    blocked_by_effective = effective is not None and oracle_compatibility(effective, base) == "incompatible"
    compatibility = "incompatible" if blocked_by_effective else by_raw
    measurement_side = effective if blocked_by_effective else raw
    blocked = compatibility == "incompatible" and status == STATUS_CONFIGURED
    out_status = STATUS_BASE_REQUIRED if blocked else status
    state = None
    if status == STATUS_CONFIGURED and SAMPLES[sample] is not None:
        state = "blocked" if blocked else "unverified_historical"
    return out_status, compatibility, measurement_side, state


def test_there_are_108_cases():
    assert len(CASES) == 108


@pytest.mark.parametrize("status,raw,base,sample", CASES)
def test_the_historical_gate_equals_the_oracle(status, raw, base, sample):
    out = run(status, raw, base, sample)
    exp_status, exp_compat, exp_side, exp_state = expected(status, raw, base, sample)
    assert (out.status, out.reference_compatibility, out.measurement_side, out.base_reference_side) == (exp_status, exp_compat, exp_side, base)
    provenance = out.side_provenance
    assert (provenance.verification_state if provenance else None) == exp_state


@pytest.mark.parametrize("status,raw,base,sample", CASES)
def test_the_denominator_is_never_altered_and_a_historical_result_is_never_verified(status, raw, base, sample):
    out = run(status, raw, base, sample)
    assert out.base_amount == (BASE_AMOUNT if status == STATUS_CONFIGURED else None)
    provenance = out.side_provenance
    if provenance is not None:
        assert provenance.verification_state in ("blocked", "unverified_historical")
        assert provenance.denominator_side is None and provenance.conversion is None
        assert provenance.ratio_applied is None and provenance.ratio_authority is None


@pytest.mark.parametrize("status,raw,base,sample", CASES)
def test_nothing_the_raw_declaration_blocked_is_newly_allowed(status, raw, base, sample):
    if oracle_compatibility(raw, base) == "incompatible" and status == STATUS_CONFIGURED:
        assert run(status, raw, base, sample).status == STATUS_BASE_REQUIRED


@pytest.mark.parametrize("status,raw,base,sample", [c for c in CASES if c[3] not in STRICT])
def test_a_side_that_is_not_strict_behaves_exactly_as_the_raw_declaration_gate(status, raw, base, sample):
    out = run(status, raw, base, sample)
    assert out.reference_compatibility == oracle_compatibility(raw, base) and out.measurement_side == raw
    assert out.status == (STATUS_BASE_REQUIRED if (oracle_compatibility(raw, base) == "incompatible" and status == STATUS_CONFIGURED) else status)


def test_the_effective_side_can_block_but_never_allow_or_strengthen():
    newly_blocked = [c for c in CASES if c[0] == STATUS_CONFIGURED and oracle_compatibility(c[1], c[2]) != "incompatible"
                     and run(*c).status == STATUS_BASE_REQUIRED]
    assert newly_blocked and all(c[3] in STRICT and oracle_compatibility(STRICT[c[3]], c[2]) == "incompatible" for c in newly_blocked)
    for c in CASES:
        assert run(*c).reference_compatibility in ("incompatible", oracle_compatibility(c[1], c[2]))
