"""DEC-050 Slice 6: read-model builder combining a `MeasurementGroup`
with its own type-specific configuration and resolved PU status into
ONE view object -- the shape `app/api/v1/measurement_groups.py` needs
for its list/get endpoints.

Mirrors `app.services.per_unit_service`'s own `SourcePerUnitConfigView`/
`get_source_per_unit_config()` pattern: a dedicated read-model type,
built by the service layer (never the API layer), so the API module
stays a thin translation to/from Pydantic. Purely a composition of
already-proven Slice 1/3/4 functions -- no new validation, no new
conversion math, no new registry.

Performance (task section 27): building one view resolves at most three
registry reads per group (the group itself, its own config, and -- only
for an equipment-rating Current group with a link -- the linked
Voltage group + its own config) -- the same bounded, per-group cost
`group_aware_per_unit.resolve_group_aware_per_unit()` already has for
the live display endpoints. `build_group_views_for_source()` is the
single call the list endpoint uses to build every row in one pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.current_group_config import (
    METHOD_EQUIPMENT_RATING,
    STATUS_CONFIGURED as _CURRENT_STATUS_CONFIGURED,
    CurrentBaseConfiguration,
    resolve_current_base_for_group,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, MeasurementGroup
from app.domain.per_unit import STATUS_NOT_APPLICABLE
from app.domain.voltage_group_config import (
    STATUS_CONFIGURED as _VOLTAGE_STATUS_CONFIGURED,
    VoltageBaseConfiguration,
    resolve_effective_voltage_reference_for_group,
    resolve_voltage_base_for_group,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


@dataclass(slots=True)
class VoltageGroupConfigView:
    nominal_voltage_ll_kv: float | None
    reference_mode: str
    reference_override: str | None
    effective_reference: str | None
    evidence_names: list[str]
    detection_reason: str


@dataclass(slots=True)
class CurrentGroupConfigView:
    method: str
    equipment_rating_mva: float | None
    linked_voltage_group_id: str | None
    manual_voltage_base_kv: float | None
    manual_ibase_ka: float | None
    resolved_ibase_ka: float | None
    applicable_voltage_ll_kv: float | None


@dataclass(slots=True)
class MeasurementGroupView:
    group: MeasurementGroup
    voltage_config: VoltageGroupConfigView | None
    current_config: CurrentGroupConfigView | None
    pu_status: str
    pu_reason: str | None


def _build_voltage_view(
    group: MeasurementGroup, config: VoltageBaseConfiguration | None
) -> tuple[VoltageGroupConfigView, str, str | None]:
    effective = resolve_effective_voltage_reference_for_group(group, config)
    resolution = resolve_voltage_base_for_group(group, config)
    view = VoltageGroupConfigView(
        nominal_voltage_ll_kv=config.nominal_voltage_ll_kv if config is not None else None,
        reference_mode=config.reference_mode if config is not None else "auto",
        reference_override=config.reference_override if config is not None else None,
        effective_reference=effective.reference,
        evidence_names=list(effective.evidence_names),
        detection_reason=effective.reason,
    )
    pu_status = "configured" if resolution.status == _VOLTAGE_STATUS_CONFIGURED else resolution.status
    return view, pu_status, resolution.reason


def _build_current_view(
    group: MeasurementGroup,
    config: CurrentBaseConfiguration | None,
    *,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> tuple[CurrentGroupConfigView, str, str | None]:
    linked_voltage_group = None
    linked_voltage_config = None
    if (
        config is not None
        and config.method == METHOD_EQUIPMENT_RATING
        and config.linked_voltage_group_id is not None
    ):
        linked_voltage_group = group_registry.get(group.workspace_id, config.linked_voltage_group_id)
        linked_voltage_config = voltage_config_registry.get(group.workspace_id, config.linked_voltage_group_id)
    resolution = resolve_current_base_for_group(
        group, config, linked_voltage_group=linked_voltage_group, linked_voltage_config=linked_voltage_config
    )
    view = CurrentGroupConfigView(
        method=config.method if config is not None else "none",
        equipment_rating_mva=config.equipment_rating_mva if config is not None else None,
        linked_voltage_group_id=config.linked_voltage_group_id if config is not None else None,
        manual_voltage_base_kv=config.manual_voltage_base_kv if config is not None else None,
        manual_ibase_ka=config.manual_ibase_ka if config is not None else None,
        resolved_ibase_ka=resolution.ibase_ka if resolution.status == _CURRENT_STATUS_CONFIGURED else None,
        applicable_voltage_ll_kv=resolution.applicable_voltage_ll_kv if resolution.status == _CURRENT_STATUS_CONFIGURED else None,
    )
    pu_status = "configured" if resolution.status == _CURRENT_STATUS_CONFIGURED else resolution.status
    return view, pu_status, resolution.reason


def build_group_view(
    group: MeasurementGroup,
    *,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> MeasurementGroupView:
    if group.kind == KIND_VOLTAGE:
        config = voltage_config_registry.get(group.workspace_id, group.id)
        voltage_view, pu_status, pu_reason = _build_voltage_view(group, config)
        return MeasurementGroupView(group=group, voltage_config=voltage_view, current_config=None, pu_status=pu_status, pu_reason=pu_reason)
    if group.kind == KIND_CURRENT:
        config = current_config_registry.get(group.workspace_id, group.id)
        current_view, pu_status, pu_reason = _build_current_view(
            group, config, group_registry=group_registry, voltage_config_registry=voltage_config_registry
        )
        return MeasurementGroupView(group=group, voltage_config=None, current_config=current_view, pu_status=pu_status, pu_reason=pu_reason)
    # Defensive only -- Slice 1 restricts `kind` to voltage/current at
    # creation time; no other kind can exist.
    return MeasurementGroupView(group=group, voltage_config=None, current_config=None, pu_status=STATUS_NOT_APPLICABLE, pu_reason=None)


def build_group_views_for_source(
    *,
    workspace_id: str,
    source_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> list[MeasurementGroupView]:
    groups = group_registry.list_for_source(workspace_id, source_id)
    return [
        build_group_view(
            group, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        for group in groups
    ]
