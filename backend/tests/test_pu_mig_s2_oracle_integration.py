"""PU-MIG S2 -- the production gate against the S1 independent oracle.

`per_unit_reference.apply_source_reference()` is the one place raw Voltage meets `resolve_side_denominator()`. This module drives
that production function with the frozen S1 oracle rows (`fixtures/pu_side_denominator/pu_side_denominator_expected.json`, produced
by an oracle that imports no application code) and checks two things the pure resolver's own tests cannot:

  * the number that reaches `PerUnitResolution.base_amount` is the oracle's denominator, and the sample is never touched;
  * every resolver refusal maps to the production outcome decision N-2 requires: the EXISTING reason vocabulary
    (`voltage_reference_side_incompatible`, `effective_base_not_representable`) with the resolver's own code and detail carried
    additively, and no number.

It also pins the historical (not strict-usable) path: bit-identical numbers, explicitly labelled `unverified_historical` (D-1, R+).
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.per_unit import STATUS_BASE_REQUIRED, STATUS_CONFIGURED, PerUnitResolution
from app.domain.per_unit_reference import (
    BLOCKED,
    REASON_BASE_NOT_REPRESENTABLE,
    REASON_SIDE_INCOMPATIBLE,
    UNVERIFIED_HISTORICAL,
    VERIFIED_CONVERTED,
    VERIFIED_DIRECT,
    RawVoltageSideInputs,
    apply_source_reference,
)
from app.domain.side_denominator import SampleSide, SideBase, SideRatio

EXPECTED = json.loads((Path(__file__).parent / "fixtures" / "pu_side_denominator" / "pu_side_denominator_expected.json").read_text())


def _plain(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _decode(request: dict):
    base = request["base"]
    sample = request["sample"]
    ratio = request["ratio"]
    return (
        SideBase(kind=base["kind"], value=base["value"], declared_side=base["declared_side"]),
        SampleSide(side=sample["side"], problem=sample["problem"], authority=sample["authority"]),
        None if ratio is None else SideRatio(
            status=ratio["status"], value=ratio.get("value"), authority=ratio.get("authority"),
            group_ids=tuple(ratio.get("group_ids", ())),
        ),
        request["representation"],
    )


def _usable(row: dict) -> bool:
    request = row["request"]
    if request["quantity"] != "voltage" or request["sample"]["problem"] is not None:
        return False
    if not _plain(request["base"]["value"]):
        return False
    ratio = request["ratio"]
    return ratio is None or ratio.get("value") is None or _plain(ratio["value"])


ROWS = [r for section in ("grid", "case_132_138", "extremes") for r in EXPECTED[section] if _usable(r)]


def _production(request: dict, *, calls: list | None = None):
    base, sample, ratio, representation = _decode(request)
    resolution = PerUnitResolution(
        status=STATUS_CONFIGURED, profile_id="g", base_amount=123.456, base_unit="V", reason=None,
        base_descriptor=base, representation=representation,
    )

    def ratio_for():
        if calls is not None:
            calls.append(1)
        return ratio

    return apply_source_reference(
        resolution, "Voltage", "unknown", voltage_group_config=None,
        side_inputs=RawVoltageSideInputs(sample=sample, ratio_for=ratio_for),
    )


def test_the_oracle_voltage_rows_are_numerous_enough_to_mean_something():
    assert len(ROWS) > 100
    assert {r["expect"]["status"] for r in ROWS} == {"resolved", "unavailable"}


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_production_gate_matches_the_oracle(row):
    expect, request = row["expect"], row["request"]
    calls: list = []
    result = _production(request, calls=calls)
    provenance = result.side_provenance
    assert provenance is not None
    same_side = request["base"]["declared_side"] == request["sample"]["side"]
    # The ratio is read only for a conversion (property P3 of the S0 contract) -- never for a same-side result.
    assert bool(calls) == (not same_side)

    if expect["status"] == "resolved":
        exact = Decimal(expect["denominator"])
        tolerance = Decimal(expect["rel_tol"]) * abs(exact) + Decimal(expect["abs_tol"])
        assert result.status == STATUS_CONFIGURED and result.reason is None
        assert result.base_amount is not None and abs(Decimal(result.base_amount) - exact) <= tolerance
        assert result.reference_compatibility == "compatible"
        assert provenance.conversion == expect["conversion"]
        assert provenance.verification_state == (VERIFIED_DIRECT if expect["conversion"] == "direct" else VERIFIED_CONVERTED)
        assert provenance.denominator_side == request["sample"]["side"]
        assert result.measurement_side == request["sample"]["side"]
        assert result.base_reference_side == request["base"]["declared_side"]
        assert (provenance.ratio_applied is None) == (expect["ratio_applied"] is None)
        return

    # A refusal carries no number, the resolver's own reason, and the production reason N-2 maps it to.
    assert result.status == STATUS_BASE_REQUIRED and result.base_amount is None
    assert provenance.verification_state == BLOCKED
    assert provenance.refusal_reason == expect["reason"] and provenance.refusal_detail == expect["detail"]
    if expect["reason"] == "vt_authority_unavailable":
        assert result.reason == REASON_SIDE_INCOMPATIBLE and result.reference_compatibility == "incompatible"
    elif expect["reason"] in ("denominator_not_representable", "invalid_base_value"):
        assert result.reason == REASON_BASE_NOT_REPRESENTABLE
    else:
        assert result.reason == expect["reason"]


# ---------------------------------------------------------------------------------- the historical (not strict) path
BASE = SideBase(kind="nominal_ll_primary", value=132000.0, declared_side="primary")


def _historical(problem, raw_side, stored_side):
    resolution = PerUnitResolution(
        status=STATUS_CONFIGURED, profile_id="g", base_amount=132000.0 / math.sqrt(3), base_unit="V", reason=None,
        base_descriptor=BASE, representation="line_to_ground",
    )

    class Group:
        base_reference_side = stored_side

    sample = SampleSide(side=None, problem=problem, authority=None)
    return resolution, apply_source_reference(
        resolution, "Voltage", raw_side, voltage_group_config=Group(),
        side_inputs=RawVoltageSideInputs(sample=sample, ratio_for=lambda: pytest.fail("a historical result reads no ratio")),
    )


@pytest.mark.parametrize("problem", ["unresolved", "inferred", "group_conflict", "calculated"])
@pytest.mark.parametrize("raw,stored", [("unknown", "primary"), ("unknown", "unknown"), ("primary", "unknown"), ("primary", "primary")])
def test_a_side_that_is_not_strict_keeps_the_historical_number_and_is_qualified(problem, raw, stored):
    before, after = _historical(problem, raw, stored)
    assert after.status == STATUS_CONFIGURED and after.base_amount == before.base_amount        # bit-identical (D-1)
    assert after.side_provenance.verification_state == UNVERIFIED_HISTORICAL
    assert after.side_provenance.conversion is None and after.side_provenance.ratio_applied is None


@pytest.mark.parametrize("problem", ["unresolved", "inferred", "group_conflict"])
@pytest.mark.parametrize("raw,stored", [("primary", "secondary"), ("secondary", "primary")])
def test_a_known_incompatible_declaration_is_never_bypassed_by_the_historical_exception(problem, raw, stored):
    """D-1: the exception retains numbers; it does not turn a known Primary/Secondary mismatch into one."""
    _, after = _historical(problem, raw, stored)
    assert after.status == STATUS_BASE_REQUIRED          # the historical gate, unchanged: it never produced a PU value here
    assert after.reason == REASON_SIDE_INCOMPATIBLE and after.reference_compatibility == "incompatible"
    assert after.side_provenance.verification_state == BLOCKED


def test_without_the_side_authority_the_gate_is_exactly_the_historical_gate():
    resolution = PerUnitResolution(status=STATUS_CONFIGURED, profile_id="g", base_amount=5.0, base_unit="V", reason=None,
                                   base_descriptor=BASE, representation="line_to_line")
    after = apply_source_reference(resolution, "Voltage", "primary", voltage_group_config=None)
    assert after.base_amount == 5.0 and after.side_provenance is None and after.reference_compatibility == "unverified"


def test_a_resolution_that_is_not_configured_is_never_given_a_number():
    resolution = PerUnitResolution(status=STATUS_BASE_REQUIRED, profile_id="g", base_amount=None, base_unit=None,
                                   reason="group_not_confirmed", base_descriptor=BASE, representation="line_to_ground")
    sample = SampleSide(side="primary", problem=None, authority="recording_channel_declared")
    after = apply_source_reference(
        resolution, "Voltage", "primary", voltage_group_config=None,
        side_inputs=RawVoltageSideInputs(sample=sample, ratio_for=lambda: None),
    )
    assert after.status == STATUS_BASE_REQUIRED and after.base_amount is None and after.reason == "group_not_confirmed"
