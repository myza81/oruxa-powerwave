"""PU-MIG S4 -- the production Current gate against the S1 independent oracle.

`per_unit_reference.apply_source_reference()` with `engineering_type="Current"` is where a raw Current base meets
`resolve_side_denominator()`. This module drives that production function with the frozen S1 oracle's Current rows
(`fixtures/pu_side_denominator/pu_side_denominator_expected.json`, produced by an oracle that imports no application code) and checks:

  * the number that reaches `PerUnitResolution.base_amount` is the oracle's denominator, and the CT is read only for a conversion;
  * every resolver refusal maps to the EXISTING Current vocabulary (`current_reference_side_incompatible`,
    `effective_base_not_representable`) with the resolver's own code and detail carried additively, and no number;
  * a base whose side is not declared is never assumed Primary: the historical gate keeps today's number, labelled
    `unverified_historical` (decision D-1, option R+) -- the oracle's `base_side_unknown` refusal is NOT what production shows there;
  * a sample side that is not strict-usable keeps the historical number, labelled; a known mismatch is never bypassed.
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
    REASON_CURRENT_SIDE_INCOMPATIBLE,
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
    base, sample, ratio = request["base"], request["sample"], request["ratio"]
    return (
        SideBase(kind=base["kind"], value=base["value"], declared_side=base["declared_side"]),
        SampleSide(side=sample["side"], problem=sample["problem"], authority=sample["authority"]),
        None if ratio is None else SideRatio(
            status=ratio["status"], value=ratio.get("value"), authority=ratio.get("authority"),
            group_ids=tuple(ratio.get("group_ids", ())),
        ),
    )


def _usable(row: dict) -> bool:
    request = row["request"]
    if request["quantity"] != "current" or request["sample"]["problem"] is not None or not _plain(request["base"]["value"]):
        return False
    ratio = request["ratio"]
    return ratio is None or ratio.get("value") is None or _plain(ratio["value"])


ROWS = [r for section in ("grid", "case_132_138", "extremes") for r in EXPECTED[section] if _usable(r)]
DECLARED = [r for r in ROWS if r["request"]["base"]["declared_side"] in ("primary", "secondary")]
UNDECLARED = [r for r in ROWS if r["request"]["base"]["declared_side"] == "unknown"]


def _production(request: dict, *, calls: list | None = None):
    base, sample, ratio = _decode(request)
    resolution = PerUnitResolution(
        status=STATUS_CONFIGURED, profile_id="g", base_amount=123.456, base_unit="A", reason=None, base_descriptor=base,
    )

    def ratio_for():
        if calls is not None:
            calls.append(1)
        return ratio

    return apply_source_reference(
        resolution, "Current", "unknown", group_config=None, profile=None,
        side_inputs=RawVoltageSideInputs(sample=sample, ratio_for=ratio_for),
    ), resolution


def test_the_oracle_current_rows_are_numerous_enough_to_mean_something():
    assert len(DECLARED) > 100 and UNDECLARED
    assert {r["expect"]["status"] for r in DECLARED} == {"resolved", "unavailable"}
    assert {r["request"]["base"]["kind"] for r in DECLARED} >= {"equipment_derived_primary", "manual_direct"}


@pytest.mark.parametrize("row", DECLARED, ids=[r["id"] for r in DECLARED])
def test_production_current_gate_matches_the_oracle(row):
    expect, request = row["expect"], row["request"]
    calls: list = []
    result, _ = _production(request, calls=calls)
    provenance = result.side_provenance
    assert provenance is not None
    same_side = request["base"]["declared_side"] == request["sample"]["side"]
    assert bool(calls) == (not same_side)          # the CT is read only for a conversion (property P3)

    if expect["status"] == "resolved":
        exact = Decimal(expect["denominator"])
        tolerance = Decimal(expect["rel_tol"]) * abs(exact) + Decimal(expect["abs_tol"])
        assert result.status == STATUS_CONFIGURED and result.reason is None
        assert result.base_amount is not None and abs(Decimal(result.base_amount) - exact) <= tolerance
        assert result.reference_compatibility == "compatible"
        assert provenance.conversion == expect["conversion"]
        assert provenance.verification_state == (VERIFIED_DIRECT if expect["conversion"] == "direct" else VERIFIED_CONVERTED)
        assert provenance.denominator_side == request["sample"]["side"] and result.measurement_side == request["sample"]["side"]
        assert result.base_reference_side == request["base"]["declared_side"]
        assert (provenance.ratio_applied is None) == (expect["ratio_applied"] is None)
        return

    assert result.status == STATUS_BASE_REQUIRED and result.base_amount is None
    assert provenance.verification_state == BLOCKED
    assert provenance.refusal_reason == expect["reason"] and provenance.refusal_detail == expect["detail"]
    if expect["reason"] == "ct_authority_unavailable":
        assert result.reason == REASON_CURRENT_SIDE_INCOMPATIBLE and result.reference_compatibility == "incompatible"
    elif expect["reason"] in ("denominator_not_representable", "invalid_base_value"):
        assert result.reason == REASON_BASE_NOT_REPRESENTABLE
    else:
        assert result.reason == expect["reason"]


@pytest.mark.parametrize("row", UNDECLARED, ids=[r["id"] for r in UNDECLARED])
def test_a_base_whose_side_is_not_declared_is_never_assumed_primary_and_keeps_the_historical_number(row):
    """The oracle refuses (`base_side_unknown`); production retains today's number, labelled (D-1 R+) -- and reads no CT."""
    calls: list = []
    result, before = _production(row["request"], calls=calls)
    assert not calls
    assert result.status == STATUS_CONFIGURED and result.base_amount == before.base_amount      # bit-identical
    assert result.side_provenance.verification_state == UNVERIFIED_HISTORICAL
    assert result.reference_compatibility == "unverified"
    assert result.side_provenance.ratio_applied is None and result.side_provenance.conversion is None


# ---------------------------------------------------------------------------------- the historical (not strict) path
BASE = SideBase(kind="manual_direct", value=1200.0, declared_side="primary")


class _Profile:
    current_base_mode = "direct"

    def __init__(self, side):
        self.current_base_reference_side = side


def _historical(problem, raw_side, stored_side):
    resolution = PerUnitResolution(
        status=STATUS_CONFIGURED, profile_id="s", base_amount=1200.0, base_unit="A", reason=None, base_descriptor=BASE)
    sample = SampleSide(side=None, problem=problem, authority=None)
    return resolution, apply_source_reference(
        resolution, "Current", raw_side, profile=_Profile(stored_side),
        side_inputs=RawVoltageSideInputs(sample=sample, ratio_for=lambda: pytest.fail("a historical result reads no CT")),
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
    _, after = _historical(problem, raw, stored)
    assert after.status == STATUS_BASE_REQUIRED and after.reason == REASON_CURRENT_SIDE_INCOMPATIBLE
    assert after.reference_compatibility == "incompatible" and after.side_provenance.verification_state == BLOCKED


def test_without_the_side_authority_the_gate_is_exactly_the_historical_gate():
    resolution = PerUnitResolution(status=STATUS_CONFIGURED, profile_id="s", base_amount=5.0, base_unit="A", reason=None, base_descriptor=BASE)
    after = apply_source_reference(resolution, "Current", "primary", profile=_Profile("primary"))
    assert after.base_amount == 5.0 and after.side_provenance is None and after.reference_compatibility == "compatible"


def _no_descriptor(base_side):
    """A configured Current base the resolver cannot place (no descriptor): only the historical gate can decide it."""
    return PerUnitResolution(status=STATUS_CONFIGURED, profile_id="s", base_amount=1200.0, base_unit="A", reason=None, base_descriptor=None)


def _strict(side):
    return RawVoltageSideInputs(sample=SampleSide(side=side, problem=None, authority="engineer_recording_correction"),
                                ratio_for=lambda: pytest.fail("the historical gate reads no CT"))


@pytest.mark.parametrize("raw,effective,stored", [
    ("primary", "primary", "primary"), ("secondary", "secondary", "secondary"),       # label == both sides: compatible, STILL never verified
    ("unknown", "primary", "primary"), ("unknown", "secondary", "secondary"),
])
def test_a_historical_current_result_is_never_verified_whatever_the_labels_say(raw, effective, stored):
    """S2 correction applied to Current: a compatible / strict reference-side label does not prove the denominator is on that side."""
    resolution = _no_descriptor(stored)
    after = apply_source_reference(resolution, "Current", raw, profile=_Profile(stored), side_inputs=_strict(effective))
    assert after.status == STATUS_CONFIGURED and after.base_amount == 1200.0                       # the historical number, unchanged
    provenance = after.side_provenance
    assert provenance.verification_state == UNVERIFIED_HISTORICAL
    assert provenance.denominator_side is None and provenance.conversion is None and provenance.ratio_applied is None


def test_the_effective_side_can_only_add_a_block_to_the_historical_current_gate():
    resolution = _no_descriptor("primary")
    # raw declaration allows (primary/primary); a strict Secondary side from Recording Details contradicts the label -> blocked (DEC-210/216)
    blocked = apply_source_reference(resolution, "Current", "primary", profile=_Profile("primary"), side_inputs=_strict("secondary"))
    assert blocked.status == STATUS_BASE_REQUIRED and blocked.reason == REASON_CURRENT_SIDE_INCOMPATIBLE
    assert blocked.side_provenance.verification_state == BLOCKED
    # raw declaration blocks (secondary vs a primary label): a strict effective Primary side must NOT unblock it
    still = apply_source_reference(resolution, "Current", "secondary", profile=_Profile("primary"), side_inputs=_strict("primary"))
    assert still.status == STATUS_BASE_REQUIRED and still.reason == REASON_CURRENT_SIDE_INCOMPATIBLE
    assert still.side_provenance.verification_state == BLOCKED


def test_a_resolver_placed_manual_base_is_still_verified_only_through_the_resolver():
    """The configured Manual base (descriptor, declared side) keeps its verified states -- but only because the resolver placed it."""
    base = SideBase(kind="manual_direct", value=5.0, declared_side="secondary")
    resolution = PerUnitResolution(status=STATUS_CONFIGURED, profile_id="s", base_amount=5.0, base_unit="A", reason=None, base_descriptor=base)
    direct = apply_source_reference(resolution, "Current", "secondary", profile=_Profile("secondary"), side_inputs=_strict("secondary"))
    assert direct.base_amount == 5.0 and direct.side_provenance.verification_state == VERIFIED_DIRECT
    assert direct.side_provenance.denominator_side == "secondary" and direct.side_provenance.conversion == "direct"
    converted = apply_source_reference(
        resolution, "Current", "primary", profile=_Profile("secondary"),
        side_inputs=RawVoltageSideInputs(sample=SampleSide(side="primary", problem=None, authority="recording_channel_declared"),
                                         ratio_for=lambda: SideRatio(status="configured", value=240.0, authority="manual", group_ids=("g",))))
    assert converted.base_amount == pytest.approx(1200.0) and converted.side_provenance.verification_state == VERIFIED_CONVERTED
