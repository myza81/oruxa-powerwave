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
own exact dispatch order. `status`/`reason` are read directly off that
resolution -- never independently re-derived -- so the displayed
explanation can never disagree with the actual calculation path.

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

from dataclasses import dataclass

from app.domain.calculated_channel import CalculatedChannel
from app.domain.channel_classification import (
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    VOLTAGE,
)
from app.domain.per_unit import (
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    PerUnitBaseProfile,
    PerUnitResolution,
    resolve_effective_voltage_reference,
    resolve_per_unit,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_group_aware_per_unit import resolve_calculated_group_aware_per_unit
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


def _reason_text(source_kind: str | None, raw_reason: str | None) -> str | None:
    if raw_reason is None:
        return None
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
    # BOTH scopes whenever status is "configured" (kV for Voltage, kA for
    # Current). For a Voltage Measurement Group this already reflects
    # the LL/LG-aware division; for Source Default it is the same raw
    # number `resolve_per_unit()` used directly, by construction.
    effective_base_amount: float | None
    effective_base_unit: str | None  # "kV" | "kA" | None
    # Current Measurement Group (equipment_rating method) only.
    equipment_rating_mva: float | None
    applicable_voltage_ll_kv: float | None


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
    convention. Only ever non-`None` when the resolution is actually
    `configured`."""
    if resolution.status != STATUS_CONFIGURED or resolution.base_amount is None:
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
        nominal_reference = view.voltage_config.effective_reference
    elif view is not None and view.current_config is not None:
        equipment_rating_mva = view.current_config.equipment_rating_mva
        applicable_voltage_ll_kv = view.current_config.applicable_voltage_ll_kv

    effective_base_amount, effective_base_unit = _effective_base(resolution)

    return PerUnitChannelProvenance(
        status=resolution.status,
        engineering_type=engineering_type,
        source_kind=SOURCE_KIND_MEASUREMENT_GROUP,
        reason=_reason_text(SOURCE_KIND_MEASUREMENT_GROUP, resolution.reason),
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
) -> PerUnitChannelProvenance:
    if resolution.status == STATUS_NOT_APPLICABLE:
        return _not_applicable_provenance(engineering_type)
    effective_base_amount, effective_base_unit = _effective_base(resolution)

    nominal_base_kv = None
    nominal_reference = None
    if engineering_type == VOLTAGE and resolution.status == STATUS_CONFIGURED and per_unit_profile is not None:
        # Slice 4 follow-up: the entered Source Default Voltage Base is
        # now uniformly the nominal SYSTEM LINE-TO-LINE voltage (see
        # resolve_per_unit()'s own VOLTAGE branch) -- expose it and the
        # channel's own effective reference via the SAME fields a
        # Measurement Group already uses. `nominal_reference` is
        # re-derived here via the SAME pure, deterministic
        # resolve_effective_voltage_reference() call resolve_per_unit()
        # itself already made internally to reach `STATUS_CONFIGURED` in
        # the first place -- a side-effect-free function given the same
        # inputs can never disagree with itself, so this stays faithful
        # to the "one source of truth" resolution without requiring
        # resolve_per_unit() to expose its own internal detection.
        nominal_base_kv = per_unit_profile.voltage_base_value
        detection = resolve_effective_voltage_reference(per_unit_profile, voltage_channel_names or [])
        nominal_reference = detection.reference

    return PerUnitChannelProvenance(
        status=resolution.status,
        engineering_type=engineering_type,
        source_kind=SOURCE_KIND_SOURCE_DEFAULT,
        reason=_reason_text(SOURCE_KIND_SOURCE_DEFAULT, resolution.reason),
        measurement_group_id=None,
        measurement_group_name=None,
        nominal_base_kv=nominal_base_kv,
        nominal_reference=nominal_reference,
        effective_base_amount=effective_base_amount,
        effective_base_unit=effective_base_unit,
        equipment_rating_mva=None,
        applicable_voltage_ll_kv=None,
    )


def build_source_channel_provenance(
    *,
    workspace_id: str,
    source_id: str,
    channel_name: str,
    engineering_type: str,
    engineering_quantity: str,
    per_unit_profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str],
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
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
        return _provenance_from_group(
            group_resolution.profile_id, group_resolution, workspace_id=workspace_id, engineering_type=engineering_type,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )

    legacy_resolution = resolve_per_unit(engineering_type, per_unit_profile, voltage_channel_names)
    return _provenance_from_legacy(
        legacy_resolution, engineering_type=engineering_type,
        per_unit_profile=per_unit_profile, voltage_channel_names=voltage_channel_names,
    )


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
) -> PerUnitChannelProvenance:
    """Mirrors `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel()`'s
    own exact dispatch order for a CALCULATED channel -- including
    DEC-052's own Voltage multi-input restriction, entirely via
    `resolve_calculated_group_aware_per_unit()` (never re-implemented
    here). A calculated channel never carries `engineering_quantity`
    (always "Undefined"), so no separate Angle guardrail applies --
    unaffected, per DEC-078's own documented scope."""
    group_resolution = resolve_calculated_group_aware_per_unit(
        workspace_id=workspace_id, channel=channel, calc_registry=calc_registry, group_registry=group_registry,
        voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
    )
    if group_resolution is not None:
        return _provenance_from_group(
            group_resolution.profile_id, group_resolution, workspace_id=workspace_id,
            engineering_type=channel.engineering_type, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )

    legacy_resolution = resolve_per_unit(channel.engineering_type, per_unit_profile, voltage_channel_names)
    return _provenance_from_legacy(
        legacy_resolution, engineering_type=channel.engineering_type,
        per_unit_profile=per_unit_profile, voltage_channel_names=voltage_channel_names,
    )
