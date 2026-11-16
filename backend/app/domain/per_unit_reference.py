"""Current and Voltage reference proof only: never scales samples or chooses a base."""
from dataclasses import replace
from typing import Literal

from app.domain.per_unit import STATUS_CONFIGURED, STATUS_BASE_REQUIRED, PerUnitResolution
from app.domain.reference_side import configured_base_side

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


def apply_source_reference(
    resolution, engineering_type, measurement_side="unknown", *,
    group_config=None, profile=None, voltage_group_config=None,
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
        return apply_voltage_reference(resolution, measurement_side, base_side)
    return resolution
