"""Current measurement-group base configuration orchestration layer
(Slice 4 of DEC-050's measurement-group-aware Per-Unit redesign).

Sits above `CurrentGroupConfigRegistry` exactly the way
`voltage_group_config_service.py` sits above `VoltageGroupConfigRegistry`:
the registry stays pure storage; this module resolves the owning
`MeasurementGroup` (via `MeasurementGroupRegistry`), enforces that
current-base configuration is only ever meaningful for a `kind ==
KIND_CURRENT` group (canonical document section 23-equivalent -- reject
incorrect configuration explicitly, never silently accept or ignore
it), validates a linked Voltage group when one is submitted (task
section 4), translates domain validation into `ImportServiceError`
subclasses, and is the only place that constructs/replaces a
`CurrentBaseConfiguration`.

Internal-only in this slice -- no public API endpoint exists yet, same
"prefer internal domain/service coverage first" instruction Slice 1/3
already established. Every function here is exercised directly by
`backend/tests/test_current_group_config_service.py`.

One setter per method (`set_current_base_equipment_rating`/
`set_current_base_manual`/`set_current_base_none`), each fully replacing
the fields relevant to that method AND explicitly clearing every field
NOT relevant to it -- see `CurrentBaseConfiguration`'s own docstring for
why this is a deliberate design choice, not merely a convenience.
"""

from __future__ import annotations

from app.domain.current_group_config import (
    CurrentBaseConfiguration,
    CurrentBaseResolution,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
    equipment_rating_mva_valid,
    manual_ibase_ka_valid,
    manual_voltage_base_kv_valid,
    resolve_current_base_for_group,
    voltage_base_valid,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, MeasurementGroup
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import (
    AmbiguousCurrentVoltageSourceError,
    CurrentConfigurationNotApplicableError,
    InvalidEquipmentRatingValueError,
    InvalidLinkedVoltageGroupError,
    InvalidManualCurrentBaseValueError,
    InvalidManualVoltageBaseValueError,
    MeasurementGroupNotFoundError,
    MissingCurrentVoltageSourceError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


def _get_current_group(
    workspace_id: str, measurement_group_id: str, *, group_registry: MeasurementGroupRegistry
) -> MeasurementGroup:
    """Resolves the owning group and enforces the one invariant this
    entire module exists to enforce: current-base configuration is only
    ever applicable to a `kind == KIND_CURRENT` group. Raises
    `MeasurementGroupNotFoundError`/`CurrentConfigurationNotApplicableError`
    -- never silently accepts a Voltage group's id."""
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    if group.kind != KIND_CURRENT:
        raise CurrentConfigurationNotApplicableError(
            f"Measurement group '{measurement_group_id}' has kind {group.kind!r}; "
            "current base configuration only applies to kind='current' groups."
        )
    return group


def _existing_or_default_config(
    workspace_id: str, measurement_group_id: str, *, current_config_registry: CurrentGroupConfigRegistry
) -> CurrentBaseConfiguration:
    existing = current_config_registry.get(workspace_id, measurement_group_id)
    if existing is not None:
        return existing
    return CurrentBaseConfiguration(measurement_group_id=measurement_group_id, workspace_id=workspace_id, method=METHOD_NONE)


def _validate_linked_voltage_group(
    *,
    workspace_id: str,
    source_id: str,
    linked_voltage_group_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> None:
    """Task section 4's full link-validation checklist. A missing group
    raises `MeasurementGroupNotFoundError` (the same "does this id exist
    at all" concept every other lookup in this codebase uses); every
    other rejection reason raises `InvalidLinkedVoltageGroupError` --
    never silently falls back to a manual value (there is none to fall
    back to; see `CurrentBaseConfiguration`'s own mutual-exclusivity
    note)."""
    linked_group = group_registry.get(workspace_id, linked_voltage_group_id)
    if linked_group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{linked_voltage_group_id}' in this workspace.")
    if linked_group.source_id != source_id:
        raise InvalidLinkedVoltageGroupError(
            f"Linked voltage group '{linked_voltage_group_id}' belongs to a different source than this current group."
        )
    if linked_group.kind != KIND_VOLTAGE:
        raise InvalidLinkedVoltageGroupError(
            f"Linked group '{linked_voltage_group_id}' has kind {linked_group.kind!r}; expected 'voltage'."
        )
    linked_config = voltage_config_registry.get(workspace_id, linked_voltage_group_id)
    if linked_config is None or not voltage_base_valid(linked_config.nominal_voltage_ll_kv):
        raise InvalidLinkedVoltageGroupError(
            f"Linked voltage group '{linked_voltage_group_id}' has no usable nominal LL voltage base configured."
        )


def set_current_base_equipment_rating(
    *,
    workspace_id: str,
    measurement_group_id: str,
    equipment_rating_mva: float,
    linked_voltage_group_id: str | None = None,
    manual_voltage_base_kv: float | None = None,
    group_registry: MeasurementGroupRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> CurrentBaseConfiguration:
    """Configures this Current group for `method="equipment_rating"`.
    Exactly one of `linked_voltage_group_id`/`manual_voltage_base_kv`
    must be supplied (task section 3/8: "exactly one applicable voltage
    source... prefer rejecting ambiguous input") -- both raises
    `AmbiguousCurrentVoltageSourceError`, neither raises
    `MissingCurrentVoltageSourceError`. Clears `manual_ibase_ka` (not
    relevant to this method) and whichever of
    `linked_voltage_group_id`/`manual_voltage_base_kv` was not supplied."""
    group = _get_current_group(workspace_id, measurement_group_id, group_registry=group_registry)
    if not equipment_rating_mva_valid(equipment_rating_mva):
        raise InvalidEquipmentRatingValueError(f"equipment_rating_mva={equipment_rating_mva!r} must be a finite, positive number.")

    has_link = linked_voltage_group_id is not None
    has_manual = manual_voltage_base_kv is not None
    if has_link and has_manual:
        raise AmbiguousCurrentVoltageSourceError(
            "Both linked_voltage_group_id and manual_voltage_base_kv were supplied; exactly one is required."
        )
    if not has_link and not has_manual:
        raise MissingCurrentVoltageSourceError(
            "One of linked_voltage_group_id or manual_voltage_base_kv is required for method='equipment_rating'."
        )

    if has_link:
        _validate_linked_voltage_group(
            workspace_id=workspace_id, source_id=group.source_id, linked_voltage_group_id=linked_voltage_group_id,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
    else:
        if not manual_voltage_base_kv_valid(manual_voltage_base_kv):
            raise InvalidManualVoltageBaseValueError(
                f"manual_voltage_base_kv={manual_voltage_base_kv!r} must be a finite, positive number."
            )

    config = _existing_or_default_config(workspace_id, measurement_group_id, current_config_registry=current_config_registry)
    config.method = METHOD_EQUIPMENT_RATING
    config.equipment_rating_mva = equipment_rating_mva
    config.linked_voltage_group_id = linked_voltage_group_id
    config.manual_voltage_base_kv = manual_voltage_base_kv
    config.manual_ibase_ka = None
    current_config_registry.upsert(config)
    return config


def set_current_base_manual(
    *,
    workspace_id: str,
    measurement_group_id: str,
    manual_ibase_ka: float,
    group_registry: MeasurementGroupRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> CurrentBaseConfiguration:
    """Configures this Current group for `method="manual"`. Requires
    only `manual_ibase_ka` -- no Sbase, no linked/manual voltage source
    (task section 6). Clears every equipment-rating-only field."""
    _get_current_group(workspace_id, measurement_group_id, group_registry=group_registry)
    if not manual_ibase_ka_valid(manual_ibase_ka):
        raise InvalidManualCurrentBaseValueError(f"manual_ibase_ka={manual_ibase_ka!r} must be a finite, positive number.")

    config = _existing_or_default_config(workspace_id, measurement_group_id, current_config_registry=current_config_registry)
    config.method = METHOD_MANUAL
    config.manual_ibase_ka = manual_ibase_ka
    config.equipment_rating_mva = None
    config.linked_voltage_group_id = None
    config.manual_voltage_base_kv = None
    current_config_registry.upsert(config)
    return config


def set_current_base_none(
    *,
    workspace_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> CurrentBaseConfiguration:
    """Configures this Current group for `method="none"` -- no PU
    current normalization available (task section 7). Clears every
    numeric/link field so none of them can silently influence a later
    resolution (`CurrentBaseConfiguration`'s own documented behaviour)."""
    _get_current_group(workspace_id, measurement_group_id, group_registry=group_registry)
    config = _existing_or_default_config(workspace_id, measurement_group_id, current_config_registry=current_config_registry)
    config.method = METHOD_NONE
    config.equipment_rating_mva = None
    config.linked_voltage_group_id = None
    config.manual_voltage_base_kv = None
    config.manual_ibase_ka = None
    current_config_registry.upsert(config)
    return config


def resolve_group_current_base(
    *,
    workspace_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> CurrentBaseResolution:
    """The one group-level Ibase resolution authority exposed at the
    service layer -- resolves the group + its configuration (if any),
    resolves the linked Voltage group + its own configuration (if a
    link is configured), and delegates to `resolve_current_base_for_group()`
    (pure domain logic).

    Deliberately does NOT reject a non-Current group the way the
    configuration mutators above do (`_get_current_group()`) -- a
    RESOLUTION query is read-only and should gracefully report
    `STATUS_NOT_APPLICABLE` for a Voltage group, mirroring
    `voltage_group_config_service.resolve_group_voltage_base()`'s own
    asymmetric contract."""
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    config = current_config_registry.get(workspace_id, measurement_group_id)

    linked_voltage_group = None
    linked_voltage_config = None
    if config is not None and config.method == METHOD_EQUIPMENT_RATING and config.linked_voltage_group_id is not None:
        linked_voltage_group = group_registry.get(workspace_id, config.linked_voltage_group_id)
        linked_voltage_config = voltage_config_registry.get(workspace_id, config.linked_voltage_group_id)

    return resolve_current_base_for_group(
        group, config, linked_voltage_group=linked_voltage_group, linked_voltage_config=linked_voltage_config
    )
