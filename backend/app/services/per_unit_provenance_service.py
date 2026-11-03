"""Per-Unit Settings hierarchy, Slice 3: channel-level Per-Unit
provenance/traceability read model -- answers "which configuration is
controlling this channel's per-unit value, and what effective base is
actually being used?" without re-implementing DEC-051 (source-channel
precedence) or DEC-052 (calculated-channel Voltage multi-input
restriction).

**One source of truth (the task's own critical rule)**: every provenance
object returned here is built FROM the exact same `PerUnitResolution`
object that would be used to convert the channel's own displayed value --
`resolve_group_aware_per_unit()`/`resolve_calculated_group_aware_per_unit()`
first, falling through to the DEC-049 `resolve_per_unit()` only when
ungrouped/uninherited, mirroring `waveform_service._resolve_effective_per_unit()`'s
and `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`'s
own exact dispatch order. The resulting base is checked against the channel's
measured unit and numerical bounds by `resolve_conversion_eligibility()`, also used by scalar/array
conversion. Its `status`/`reason` describe conversion readiness; resolved base
metadata remains available even when the measured unit prevents conversion.

The richer display-only fields a bare `PerUnitResolution` does not carry
(a Measurement Group's own nominal LL voltage / effective reference /
equipment rating) are obtained by calling
`app.services.measurement_group_view_service.build_group_view()` --
the SAME read model Slice 6's Measurement Groups modal already renders
rows from -- keyed by the `measurement_group_id` the resolution itself
already reports (`PerUnitResolution.profile_id`, repurposed by
`group_aware_per_unit.py`/`calculated_group_aware_per_unit.py` to carry
a group id for exactly this reason). No new resolution math is
introduced anywhere in this module.

**Source Default Voltage truthfulness (updated for the Slice 4
follow-up enhancement)**: since Slice 4 corrected
`app.domain.per_unit.resolve_per_unit()` to treat the entered Source
Default Voltage Base as the nominal SYSTEM LINE-TO-LINE voltage (never
a phase-derived number), that field now has a fixed, known engineering
meaning -- exactly like a Measurement Group's own
`nominal_voltage_ll_kv`. It is therefore now truthful (and required by
this follow-up) to expose it via the SAME `nominal_base_kv`/
`nominal_reference` fields a Measurement Group already uses, rather
than inventing a second, Source-Default-specific structure. This is
UNCHANGED for Source Default CURRENT, which has no equivalent "nominal"
concept (`resolve_current_base_amps()`'s own Ibase formula has no
reference-aware adjustment to expose) -- only Voltage gains these two
fields for the Source Default scope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from app.domain.reference_side import ReferenceSide, configured_base_side
from app.services.calculated_current_per_unit import resolve_calculated_current_per_unit, CURRENT_REASON_COPY

import numpy as np

from app.domain.calculated_channel import CalculatedChannel
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    VOLTAGE, CURRENT,
)
from app.domain.per_unit import (
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    PerUnitBaseProfile,
    PerUnitResolution,
    resolve_conversion_eligibility,
    resolve_effective_voltage_reference,
    resolve_per_unit,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_group_aware_per_unit import (
    VOLTAGE_REPRESENTATION_UNDETERMINED_MESSAGE,
    resolve_calculated_group_aware_per_unit,
    voltage_representation_undetermined,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.group_aware_per_unit import resolve_group_aware_per_unit
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_view_service import build_group_view
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

SOURCE_KIND_MEASUREMENT_GROUP = "measurement_group"
SOURCE_KIND_SOURCE_DEFAULT = "source_default"

#: Reuses the ALREADY-STRUCTURED reason codes each pure domain resolver
#: already produces (never a new low-level error string) -- these two
#: maps only translate an existing code into a concise, engineering-
#: facing sentence, chosen by which SCOPE (group vs source-wide)
#: produced it, since the identical code can mean a subtly different
#: thing in each scope (task's own worked examples: "...for this
#: group." vs "...source-wide...").
_MEASUREMENT_GROUP_REASON_COPY: dict[str, str] = {
    "group_not_confirmed": "This Measurement Group has not been confirmed yet.",
    "voltage_base_not_configured": "Voltage base is not configured for this group.",
    "voltage_reference_undetermined": "This group's voltage reference (L-G/L-L) could not be determined.",
    "current_base_not_configured": "No current base method is configured for this group.",
    "manual_ibase_not_configured": "A manual current base value has not been set for this group.",
    "equipment_rating_not_configured": "Equipment rating (MVA) is not configured for this group.",
    "applicable_voltage_base_not_configured": (
        "The linked/manual voltage base required to derive this group's current base is missing."
    ),
    "invalid_current_base_method": "This group's current base configuration is invalid.",
    "group_kind_mismatch": "This channel's engineering type does not match its Measurement Group.",
}
_DEFAULT_MEASUREMENT_GROUP_REASON = "This Measurement Group's configuration is incomplete."

_SOURCE_DEFAULT_REASON_COPY: dict[str, str] = {
    "not_configured": "No usable source-wide per-unit base is configured.",
    "voltage_base_not_configured": "No usable source-wide per-unit base is configured.",
    "current_base_not_configured": "No usable source-wide per-unit base is configured.",
    "voltage_reference_undetermined": (
        "The channel's voltage reference (L-G/L-L) could not be determined, so the current base cannot be derived."
    ),
}
_DEFAULT_SOURCE_DEFAULT_REASON = "No usable source-wide per-unit base is configured."

_MEASURED_UNIT_REASON_COPY = {
    "effective_base_not_representable": "The effective base cannot be represented as a finite, positive denominator.",
    "per_unit_result_not_representable": "This channel contains finite measurements whose per-unit results cannot be represented.",
    "measured_unit_missing": (
        "The measured unit is missing; per-unit conversion requires V/kV for Voltage or A/kA for Current."
    ),
    "measured_unit_unsupported": (
        "The measured unit is unsupported for this quantity; per-unit conversion requires V/kV for Voltage or A/kA for Current."
    ),
}


def _reason_text(source_kind: str | None, raw_reason: str | None) -> str | None:
    if raw_reason is None:
        return None
    if raw_reason in _MEASURED_UNIT_REASON_COPY:
        return _MEASURED_UNIT_REASON_COPY[raw_reason]
    if source_kind == SOURCE_KIND_MEASUREMENT_GROUP:
        return _MEASUREMENT_GROUP_REASON_COPY.get(raw_reason, _DEFAULT_MEASUREMENT_GROUP_REASON)
    if source_kind == SOURCE_KIND_SOURCE_DEFAULT:
        return _SOURCE_DEFAULT_REASON_COPY.get(raw_reason, _DEFAULT_SOURCE_DEFAULT_REASON)
    return None


@dataclass(slots=True)
class PerUnitChannelProvenance:
    """One channel's own Per-Unit provenance -- derived fresh per
    request, never stored. Every field beyond `status`/`engineering_type`
    is `None` unless the channel's own effective resolution scope
    actually carries it (see module docstring's own field-by-field
    truthfulness note)."""

    status: str  # STATUS_CONFIGURED | STATUS_BASE_REQUIRED | STATUS_NOT_APPLICABLE
    engineering_type: str
    source_kind: str | None  # SOURCE_KIND_MEASUREMENT_GROUP | SOURCE_KIND_SOURCE_DEFAULT | None
    reason: str | None
    measurement_group_id: str | None
    measurement_group_name: str | None
    # The user-entered nominal LINE-TO-LINE base and the channel's own
    # effective reference (the "channel interpretation" the UI shows) --
    # populated for a Voltage Measurement Group (from that group's own
    # configuration) AND, since the Slice 4 follow-up, for Source
    # Default Voltage too (from the source's own profile -- see module
    # docstring). Never populated for Current, in either scope (Current
    # has no equivalent "nominal LL, reference-adjusted" concept).
    nominal_base_kv: float | None
    nominal_reference: str | None  # "line_to_ground" | "line_to_line" | None
    # The actual resolved denominator used for division -- populated for
    # BOTH scopes whenever a base resolves (kV for Voltage, kA for Current),
    # including when the measured unit prevents conversion. For a Voltage
    # Measurement Group this reflects the LL/LG-aware division; Source Default
    # reports the same denominator `resolve_per_unit()` actually resolved.
    effective_base_amount: float | None
    effective_base_unit: str | None  # "kV" | "kA" | None
    # Current Measurement Group (equipment_rating method) only.
    equipment_rating_mva: float | None
    applicable_voltage_ll_kv: float | None
    resolution_origin: str | None = None
    measurement_side: ReferenceSide = "unknown"
    base_reference_side: ReferenceSide = "unknown"


def _not_applicable_provenance(engineering_type: str) -> PerUnitChannelProvenance:
    return PerUnitChannelProvenance(
        status=STATUS_NOT_APPLICABLE, engineering_type=engineering_type, source_kind=None, reason=None,
        measurement_group_id=None, measurement_group_name=None,
        nominal_base_kv=None, nominal_reference=None,
        effective_base_amount=None, effective_base_unit=None,
        equipment_rating_mva=None, applicable_voltage_ll_kv=None,
    )


def _effective_base(resolution: PerUnitResolution) -> tuple[float | None, str | None]:
    """`PerUnitResolution.base_amount` is always volts/amps (that type's
    own established convention, unchanged) -- converted here to the
    canonical kV/kA this provenance schema displays throughout,
    matching every other Slice 6/Slice 2 read model's own kV/kA
    convention. A resolved base remains useful metadata even when the
    channel's measured unit prevents conversion; status decides readiness."""
    if resolution.base_amount is None:
        return None, None
    unit = "kV" if resolution.base_unit == "V" else "kA"
    return resolution.base_amount / 1000.0, unit


def _provenance_from_group(
    measurement_group_id: str,
    resolution: PerUnitResolution,
    *,
    workspace_id: str,
    engineering_type: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    explicit_voltage_reference: str | None = None,
) -> PerUnitChannelProvenance:
    group = group_registry.get(workspace_id, measurement_group_id)
    view = (
        build_group_view(
            group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        if group is not None
        else None
    )
    nominal_base_kv = None
    nominal_reference = None
    equipment_rating_mva = None
    applicable_voltage_ll_kv = None
    if view is not None and view.voltage_config is not None:
        nominal_base_kv = view.voltage_config.nominal_voltage_ll_kv
        # DEC-115: a channel declaring its own representation reports THAT
        # reference (the one its denominator was actually derived from),
        # never the group's own member reference.
        nominal_reference = explicit_voltage_reference or view.voltage_config.effective_reference
    elif view is not None and view.current_config is not None:
        equipment_rating_mva = view.current_config.equipment_rating_mva
        applicable_voltage_ll_kv = view.current_config.applicable_voltage_ll_kv

    effective_base_amount, effective_base_unit = _effective_base(resolution)

    return PerUnitChannelProvenance(
        status=resolution.status,
        engineering_type=engineering_type,
        source_kind=SOURCE_KIND_MEASUREMENT_GROUP,
        reason=_reason_text(SOURCE_KIND_MEASUREMENT_GROUP, resolution.reason),
        base_reference_side=view.current_config.base_reference_side if view and view.current_config else "unknown",
        measurement_group_id=measurement_group_id,
        measurement_group_name=group.display_name if group is not None else None,
        nominal_base_kv=nominal_base_kv,
        nominal_reference=nominal_reference,
        effective_base_amount=effective_base_amount,
        effective_base_unit=effective_base_unit,
        equipment_rating_mva=equipment_rating_mva,
        applicable_voltage_ll_kv=applicable_voltage_ll_kv,
    )


def _provenance_from_legacy(
    resolution: PerUnitResolution,
    *,
    engineering_type: str,
    per_unit_profile: PerUnitBaseProfile | None = None,
    voltage_channel_names: list[str] | None = None,
    explicit_voltage_reference: str | None = None,
) -> PerUnitChannelProvenance:
    if resolution.status == STATUS_NOT_APPLICABLE:
        return _not_applicable_provenance(engineering_type)
    effective_base_amount, effective_base_unit = _effective_base(resolution)

    nominal_base_kv = None
    nominal_reference = None
    if engineering_type == VOLTAGE and resolution.base_amount is not None and per_unit_profile is not None:
        # Slice 4 follow-up: the entered Source Default Voltage Base is
        # now uniformly the nominal SYSTEM LINE-TO-LINE voltage (see
        # resolve_per_unit()'s own VOLTAGE branch) -- expose it and the
        # channel's own effective reference via the SAME fields a
        # Measurement Group already uses. `nominal_reference` is
        # re-derived here via the SAME pure, deterministic
        # resolve_effective_voltage_reference() call resolve_per_unit()
        # itself already made internally to resolve the base in
        # the first place -- a side-effect-free function given the same
        # inputs can never disagree with itself, so this stays faithful
        # to the "one source of truth" resolution without requiring
        # resolve_per_unit() to expose its own internal detection.
        nominal_base_kv = per_unit_profile.voltage_base_value
        if explicit_voltage_reference is not None:
            # DEC-115: mirrors resolve_per_unit()'s own explicit override.
            nominal_reference = explicit_voltage_reference
        else:
            detection = resolve_effective_voltage_reference(per_unit_profile, voltage_channel_names or [])
            nominal_reference = detection.reference

    return PerUnitChannelProvenance(
        status=resolution.status,
        engineering_type=engineering_type,
        source_kind=SOURCE_KIND_SOURCE_DEFAULT,
        reason=_reason_text(SOURCE_KIND_SOURCE_DEFAULT, resolution.reason),
        base_reference_side=configured_base_side(per_unit_profile.current_base_mode, per_unit_profile.current_base_reference_side) if per_unit_profile and engineering_type == CURRENT else "unknown",
        measurement_group_id=None,
        measurement_group_name=None,
        nominal_base_kv=nominal_base_kv,
        nominal_reference=nominal_reference,
        effective_base_amount=effective_base_amount,
        effective_base_unit=effective_base_unit,
        equipment_rating_mva=None,
        applicable_voltage_ll_kv=None,
    )


def _build_source_channel_provenance(
    *,
    workspace_id: str,
    source_id: str,
    channel_name: str,
    engineering_type: str,
    engineering_quantity: str,
    measured_unit: str | None,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str],
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    values: np.ndarray | None = None,
) -> PerUnitChannelProvenance:
    """Mirrors `waveform_service._resolve_effective_per_unit()`'s own
    exact dispatch order for a SOURCE channel: the DEC-078 Angle
    guardrail first (unconditionally, before either resolver runs),
    then group-aware resolution, falling through to DEC-049 only when
    ungrouped."""
    if engineering_quantity in (ENGINEERING_QUANTITY_VOLTAGE_ANGLE, ENGINEERING_QUANTITY_CURRENT_ANGLE):
        return _not_applicable_provenance(engineering_type)

    group_resolution = resolve_group_aware_per_unit(
        workspace_id=workspace_id, source_id=source_id, channel_name=channel_name, engineering_type=engineering_type,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )
    if group_resolution is not None:
        group_resolution = resolve_conversion_eligibility(group_resolution, measured_unit, engineering_type, values)
        return _provenance_from_group(
            group_resolution.profile_id, group_resolution, workspace_id=workspace_id, engineering_type=engineering_type,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )

    legacy_resolution = resolve_per_unit(engineering_type, per_unit_profile, voltage_channel_names)
    legacy_resolution = resolve_conversion_eligibility(legacy_resolution, measured_unit, engineering_type, values)
    return _provenance_from_legacy(
        legacy_resolution, engineering_type=engineering_type,
        per_unit_profile=per_unit_profile, voltage_channel_names=voltage_channel_names,
    )


def build_source_channel_provenance(*, measurement_side: ReferenceSide = "unknown", **kwargs) -> PerUnitChannelProvenance:
    return replace(_build_source_channel_provenance(**kwargs), measurement_side=measurement_side)


def build_calculated_channel_provenance(
    *,
    workspace_id: str,
    channel: CalculatedChannel,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str],
    calc_registry: CalculatedChannelRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    source_registry=None,
    per_unit_registry=None,
) -> PerUnitChannelProvenance:
    """Mirrors `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`'s
    own exact dispatch order for a CALCULATED channel -- including
    DEC-052's own Voltage multi-input restriction, entirely via
    `resolve_calculated_group_aware_per_unit()` (never re-implemented
    here). A calculated channel never carries `engineering_quantity`
    (always "Undefined"), so no separate Angle guardrail applies --
    unaffected, per DEC-078's own documented scope.

    DEC-116: the undetermined-representation rule is checked first,
    exactly like the display dispatcher, so provenance never explains a
    base the display path would refuse."""
    if channel.engineering_type == CURRENT and source_registry is not None and per_unit_registry is not None:
        inherited = resolve_calculated_current_per_unit(
            workspace_id=workspace_id, channel=channel, source_registry=source_registry,
            per_unit_registry=per_unit_registry, calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry)
        if inherited is not None:
            resolution = inherited.resolution
            if inherited.source_kind == SOURCE_KIND_MEASUREMENT_GROUP:
                provenance = _provenance_from_group(
                    resolution.profile_id, resolution, workspace_id=workspace_id,
                    engineering_type=CURRENT, group_registry=group_registry,
                    voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry)
            elif inherited.source_kind == SOURCE_KIND_SOURCE_DEFAULT:
                provenance = _provenance_from_legacy(resolution, engineering_type=CURRENT,
                    per_unit_profile=per_unit_registry.get(workspace_id, resolution.profile_id))
            else:
                amount, unit = _effective_base(resolution)
                reason = CURRENT_REASON_COPY.get(resolution.reason) or _MEASURED_UNIT_REASON_COPY.get(resolution.reason)
                if resolution.reason and reason is None:
                    reason = _reason_text(SOURCE_KIND_MEASUREMENT_GROUP, resolution.reason)
                provenance = replace(_not_applicable_provenance(CURRENT), status=resolution.status,
                    reason=reason, effective_base_amount=amount, effective_base_unit=unit,
                    resolution_origin="automatic_common_base")
            return replace(provenance, measurement_side=inherited.measurement_side,
                           base_reference_side=inherited.base_reference_side)
    if voltage_representation_undetermined(workspace_id, channel, calc_registry=calc_registry):
        return PerUnitChannelProvenance(
            status=STATUS_BASE_REQUIRED, engineering_type=channel.engineering_type, source_kind=None,
            reason=VOLTAGE_REPRESENTATION_UNDETERMINED_MESSAGE,
            measurement_group_id=None, measurement_group_name=None,
            nominal_base_kv=None, nominal_reference=None,
            effective_base_amount=None, effective_base_unit=None,
            equipment_rating_mva=None, applicable_voltage_ll_kv=None,
        )
    group_resolution = resolve_calculated_group_aware_per_unit(
        workspace_id=workspace_id, channel=channel, calc_registry=calc_registry, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
    if group_resolution is not None:
        group_resolution = resolve_conversion_eligibility(group_resolution, channel.unit, channel.engineering_type, channel.values)
        return _provenance_from_group(
            group_resolution.profile_id, group_resolution, workspace_id=workspace_id,
            engineering_type=channel.engineering_type, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
            explicit_voltage_reference=channel.voltage_representation,
        )

    legacy_resolution = resolve_per_unit(
        channel.engineering_type, per_unit_profile, voltage_channel_names,
        explicit_voltage_reference=channel.voltage_representation,
    )
    legacy_resolution = resolve_conversion_eligibility(legacy_resolution, channel.unit, channel.engineering_type, channel.values)
    return _provenance_from_legacy(
        legacy_resolution, engineering_type=channel.engineering_type,
        per_unit_profile=per_unit_profile, voltage_channel_names=voltage_channel_names,
        explicit_voltage_reference=channel.voltage_representation,
    )
