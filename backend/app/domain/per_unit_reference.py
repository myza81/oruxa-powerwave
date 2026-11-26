"""Current and Voltage reference proof only: never scales samples or chooses a base.

PU-MIG S2 (raw Voltage): when the caller supplies the consumed channel's Recording Details side authority
(`RawVoltageSideInputs`) AND the base resolver handed on an established base (`PerUnitResolution.base_descriptor`), the
denominator is placed on the sample's side by `side_denominator.resolve_side_denominator()` -- the one arithmetic authority.
This module neither chooses a base (that stays with the base resolvers, D-4/D-5) nor decides a side or a ratio (those are
read from Recording Details by the caller) nor scales samples. A sample side that is not strict-usable keeps the historical
gate unchanged and is labelled `unverified_historical` (D-1, option R+).
"""
from dataclasses import dataclass, replace
from typing import Callable, Literal

from app.domain.per_unit import STATUS_CONFIGURED, STATUS_BASE_REQUIRED, PerUnitResolution
from app.domain.reference_side import configured_base_side
from app.domain.side_denominator import (
    QUANTITY_VOLTAGE,
    REASON_DENOMINATOR_NOT_REPRESENTABLE,
    REASON_INVALID_BASE_VALUE,
    REASON_VT_AUTHORITY_UNAVAILABLE,
    SIDE_PRIMARY,
    SIDE_SECONDARY,
    SampleSide,
    SideRatio,
    resolve_side_denominator,
)

#: D-1 (R+): one explicit verification state, read by every PU surface. Values are fixed by the S0 reconciliation.
VERIFIED_DIRECT = "verified_direct"
VERIFIED_CONVERTED = "verified_converted"
UNVERIFIED_HISTORICAL = "unverified_historical"
BLOCKED = "blocked"
VERIFICATION_STATES = (VERIFIED_DIRECT, VERIFIED_CONVERTED, UNVERIFIED_HISTORICAL, BLOCKED)

#: N-2: the resolver's refusals reuse the existing production vocabulary -- a required VT that is not authoritative is the
#: existing `voltage_reference_side_incompatible` PU reason (known Primary/Secondary mismatch with nothing to reconcile
#: it), a non-representable denominator is the existing `effective_base_not_representable`. The resolver's own code and
#: detail travel additively in `SideProvenance.refusal_*`.
REASON_SIDE_INCOMPATIBLE = "voltage_reference_side_incompatible"
REASON_BASE_NOT_REPRESENTABLE = "effective_base_not_representable"


@dataclass(frozen=True, slots=True)
class SideProvenance:
    """Verification and conversion provenance of one raw Voltage result. Echoes what the resolver used; carries no number
    of its own and never replaces `PerUnitResolution.base_amount`."""

    verification_state: str
    conversion: str | None = None
    effective_side: str | None = None
    side_authority: str | None = None
    ratio_applied: float | None = None
    ratio_authority: str | None = None
    ratio_group_ids: tuple[str, ...] = ()
    denominator_side: str | None = None
    base_kind: str | None = None
    base_side: str | None = None
    refusal_reason: str | None = None
    refusal_detail: str | None = None


@dataclass(frozen=True, slots=True)
class RawVoltageSideInputs:
    """What Recording Details says about the consumed raw Voltage channel. `ratio_for` is called only when the base side
    differs from the sample side (the ratio is never read for a same-side result) and returns the VT of the channel's own
    Measurement Group, or None when the caller cannot establish one."""

    sample: SampleSide
    ratio_for: Callable[[], SideRatio | None]

ReferenceCompatibility = Literal["compatible", "incompatible", "unverified"]


def apply_current_reference(
    resolution: PerUnitResolution, measurement_sides, base_sides, *,
    strict: bool = False, cross_authority: bool = False,
) -> PerUnitResolution:
    """Retain legacy Unknown numerics only where explicitly permitted.

    Keep known conflicts before Unknown aggregation: mixed P/S leaves cannot
    become an unverified-but-available result. Distinct Secondary authorities
    require an unimplemented common reference, even with matching side labels.
    Existing unrelated unavailability reasons retain their precedence.
    """
    measured, bases = set(measurement_sides) or {"unknown"}, set(base_sides) or {"unknown"}
    known = (measured | bases) - {"unknown"}
    reason = None
    if known == {"primary", "secondary"}:
        compatibility = "incompatible"
        reason = "current_reference_side_incompatible"
    elif "unknown" in measured | bases:
        compatibility = "unverified"
        if strict:
            reason = "current_reference_side_unknown"
    elif cross_authority and known == {"secondary"}:
        compatibility = "unverified"
        reason = "current_secondary_reference_unestablished"
    else:
        compatibility = "compatible"
    updated = replace(
        resolution, reference_compatibility=compatibility,
        measurement_side=next(iter(measured)) if len(measured) == 1 else "unknown",
        base_reference_side=next(iter(bases)) if len(bases) == 1 else "unknown",
    )
    if reason and updated.status == STATUS_CONFIGURED:
        updated = replace(updated, status=STATUS_BASE_REQUIRED, reason=reason)
    return updated


def apply_voltage_reference(
    resolution: PerUnitResolution, measurement_side: str, base_side: str,
) -> PerUnitResolution:
    """Voltage equivalent of apply_current_reference.

    Known Primary/Secondary mismatch blocks Voltage PU. Unknown sides are
    permitted but classified as unverified. No cross-authority or strict modes:
    Voltage has no calculated-channel aggregation across authority boundaries.
    Existing unrelated unavailability reasons retain their precedence.
    """
    measured = measurement_side or "unknown"
    base = base_side or "unknown"
    known = {s for s in (measured, base) if s != "unknown"}
    reason = None
    if known == {"primary", "secondary"}:
        compatibility = "incompatible"
        reason = "voltage_reference_side_incompatible"
    elif "unknown" in (measured, base):
        compatibility = "unverified"
    else:
        compatibility = "compatible"
    updated = replace(
        resolution, reference_compatibility=compatibility,
        measurement_side=measured,
        base_reference_side=base,
    )
    if reason and updated.status == STATUS_CONFIGURED:
        updated = replace(updated, status=STATUS_BASE_REQUIRED, reason=reason)
    return updated


def apply_strict_voltage_reference(
    resolution: PerUnitResolution, side_inputs: RawVoltageSideInputs, measurement_side: str, base_side: str,
) -> PerUnitResolution:
    """Raw Voltage with a strict-usable sample side: place the established base on that side (S2).

    Preconditions are checked by the caller (`apply_source_reference`): the resolution is configured, carries a base
    descriptor and a representation, and the sample side is strict-usable."""
    descriptor, sample = resolution.base_descriptor, side_inputs.sample
    ratio = side_inputs.ratio_for() if descriptor.declared_side != sample.side else None
    result = resolve_side_denominator(
        QUANTITY_VOLTAGE, descriptor, sample, ratio, representation=resolution.representation,
    )
    provenance = SideProvenance(
        verification_state=BLOCKED, effective_side=sample.side, side_authority=sample.authority,
        base_kind=descriptor.kind, base_side=descriptor.declared_side,
    )
    if result.resolved:
        direct = result.ratio_applied is None
        return replace(
            resolution, base_amount=result.denominator, reference_compatibility="compatible",
            measurement_side=sample.side, base_reference_side=descriptor.declared_side,
            side_provenance=replace(
                provenance, verification_state=VERIFIED_DIRECT if direct else VERIFIED_CONVERTED,
                conversion=result.conversion, ratio_applied=result.ratio_applied, ratio_authority=result.ratio_authority,
                ratio_group_ids=result.ratio_group_ids, denominator_side=result.denominator_side,
            ),
        )
    if result.reason == REASON_VT_AUTHORITY_UNAVAILABLE:
        reason, compatibility = REASON_SIDE_INCOMPATIBLE, "incompatible"
    elif result.reason in (REASON_DENOMINATOR_NOT_REPRESENTABLE, REASON_INVALID_BASE_VALUE):
        reason, compatibility = REASON_BASE_NOT_REPRESENTABLE, "compatible"
    else:  # an invalid request is a defect of the caller, never a number
        reason, compatibility = result.reason, "unverified"
    return replace(
        resolution, status=STATUS_BASE_REQUIRED, base_amount=None, reason=reason, reference_compatibility=compatibility,
        measurement_side=sample.side, base_reference_side=descriptor.declared_side,
        side_provenance=replace(provenance, refusal_reason=result.reason, refusal_detail=result.detail),
    )


def _strict_sample(side_inputs: RawVoltageSideInputs | None) -> bool:
    return (
        side_inputs is not None and side_inputs.sample.problem is None
        and side_inputs.sample.side in (SIDE_PRIMARY, SIDE_SECONDARY)
    )


def apply_source_reference(
    resolution, engineering_type, measurement_side="unknown", *,
    group_config=None, profile=None, voltage_group_config=None, side_inputs: RawVoltageSideInputs | None = None,
):
    """Shared raw-channel gate after group/default authority has been selected."""
    if engineering_type == "Current":
        side = configured_base_side(group_config.method, group_config.base_reference_side) if group_config else (
            configured_base_side(profile.current_base_mode, profile.current_base_reference_side) if profile else "unknown")
        return apply_current_reference(resolution, [measurement_side], [side])
    if engineering_type == "Voltage":
        if voltage_group_config is not None:
            base_side = voltage_group_config.base_reference_side
        elif profile is not None:
            base_side = profile.voltage_base_reference_side
        else:
            base_side = "unknown"
        if (
            _strict_sample(side_inputs) and resolution.status == STATUS_CONFIGURED
            and resolution.base_descriptor is not None and resolution.representation is not None
        ):
            return apply_strict_voltage_reference(resolution, side_inputs, measurement_side, base_side)
        # The historical gate decides without the resolver (a base it cannot place: a Source Default that stores `secondary`, or a
        # side that is not strict). When Recording Details HAS established the sample side (DEC-216), that side -- not the
        # recording's raw declaration -- is the one compared with the base side, so an engineer's correction can neither be ignored
        # nor produce a "compatible" result against a known mismatch. Numbers are unchanged: this gate never alters a denominator.
        strict = _strict_sample(side_inputs)
        historical = apply_voltage_reference(
            resolution, side_inputs.sample.side if strict else measurement_side, base_side,
        )
        if side_inputs is not None and resolution.status == STATUS_CONFIGURED:
            # D-1 (R+): the historical result is kept bit-for-bit and explicitly qualified.
            if historical.status != STATUS_CONFIGURED:
                state = BLOCKED
            elif strict and historical.reference_compatibility == "compatible":
                state = VERIFIED_DIRECT          # both sides are established and equal: same side, no conversion
            else:
                state = UNVERIFIED_HISTORICAL
            historical = replace(historical, side_provenance=SideProvenance(
                verification_state=state, effective_side=side_inputs.sample.side,
                side_authority=side_inputs.sample.authority, base_side=base_side,
                denominator_side=side_inputs.sample.side if state == VERIFIED_DIRECT else None,
                conversion="direct" if state == VERIFIED_DIRECT else None,
                refusal_reason=historical.reason if state == BLOCKED else None,
            ))
        return historical
    return resolution
