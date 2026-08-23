"""Voltage measurement-group base configuration orchestration layer
(Slice 3 of DEC-050's measurement-group-aware Per-Unit redesign).

Sits above `VoltageGroupConfigRegistry` exactly the way
`measurement_group_service.py` sits above `MeasurementGroupRegistry`:
the registry stays pure storage; this module resolves the owning
`MeasurementGroup` (via `MeasurementGroupRegistry`), enforces that
voltage-base configuration is only ever meaningful for a `kind ==
KIND_VOLTAGE` group (canonical document section 23 -- reject
incorrect configuration explicitly, never silently accept or ignore
it), translates domain validation into `ImportServiceError` subclasses,
and is the only place that constructs/replaces a
`VoltageBaseConfiguration`.

Internal-only in this slice -- no public API endpoint exists yet, per
the same "prefer internal domain/service coverage first" instruction
Slice 1 already established. Every function here is exercised directly
by `backend/tests/test_voltage_group_config_service.py`.

Sufficient internal operations to satisfy section 13's own list:
configure the nominal LL base (`set_voltage_base`), set a manual
reference override (`set_manual_voltage_reference`), return to auto
(`return_voltage_reference_to_auto`), obtain the live effective
reference (`get_effective_voltage_reference`), and resolve the
applicable denominator (`resolve_group_voltage_base`). Group
confirmation itself is NOT a new function here -- it is Slice 1's own
pre-existing `measurement_group_service.update_group_metadata(status=
STATUS_CONFIRMED)`, reused verbatim (canonical document section 9: the
engineer's own act of reviewing/configuring/saving is what promotes a
group from `suggested` to `confirmed`; configuring a voltage base and
confirming the group are two independent actions, not one new
combined operation).
"""

from __future__ import annotations

from app.domain.measurement_group import KIND_VOLTAGE, MeasurementGroup
from app.domain.voltage_group_config import (
    KNOWN_VOLTAGE_REFERENCE_MODES,
    VOLTAGE_REFERENCE_MODE_AUTO,
    VOLTAGE_REFERENCE_MODE_MANUAL,
    VoltageBaseConfiguration,
    VoltageBaseResolution,
    resolve_effective_voltage_reference_for_group,
    resolve_voltage_base_for_group,
    voltage_base_valid,
    voltage_reference_value_valid,
)
from app.domain.voltage_reference import VoltageReferenceDetection
from app.services.errors import (
    InvalidVoltageBaseValueError,
    InvalidVoltageReferenceOverrideError,
    MeasurementGroupNotFoundError,
    VoltageConfigurationNotApplicableError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry


def _get_voltage_group(
    workspace_id: str, measurement_group_id: str, *, group_registry: MeasurementGroupRegistry
) -> MeasurementGroup:
    """Resolves the owning group and enforces the one invariant this
    entire module exists to enforce: voltage-base configuration is only
    ever applicable to a `kind == KIND_VOLTAGE` group. Raises
    `MeasurementGroupNotFoundError`/`VoltageConfigurationNotApplicableError`
    -- never silently accepts a Current group's id."""
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    if group.kind != KIND_VOLTAGE:
        raise VoltageConfigurationNotApplicableError(
            f"Measurement group '{measurement_group_id}' has kind {group.kind!r}; "
            "voltage base configuration only applies to kind='voltage' groups."
        )
    return group


def _existing_or_default_config(
    workspace_id: str, measurement_group_id: str, *, voltage_config_registry: VoltageGroupConfigRegistry
) -> VoltageBaseConfiguration:
    existing = voltage_config_registry.get(workspace_id, measurement_group_id)
    if existing is not None:
        return existing
    return VoltageBaseConfiguration(
        measurement_group_id=measurement_group_id, workspace_id=workspace_id, nominal_voltage_ll_kv=None,
        reference_mode=VOLTAGE_REFERENCE_MODE_AUTO, reference_override=None,
    )


def set_voltage_base(
    *,
    workspace_id: str,
    measurement_group_id: str,
    nominal_voltage_ll_kv: float,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> VoltageBaseConfiguration:
    """Configures (or reconfigures) this Voltage group's own nominal
    line-to-line base value -- the canonical, user-facing quantity
    (section 4/21): the engineer enters the familiar nominal system LL
    voltage (e.g. "275") directly, never a phase-derived number. Leaves
    the group's own `reference_mode`/`reference_override` untouched if a
    configuration already exists (this is a partial update of one
    field, mirroring `measurement_group_service.update_group_metadata()`'s
    own partial-update shape), or defaults to `auto`/`None` for a
    brand-new configuration."""
    _get_voltage_group(workspace_id, measurement_group_id, group_registry=group_registry)
    if not voltage_base_valid(nominal_voltage_ll_kv):
        raise InvalidVoltageBaseValueError(
            f"nominal_voltage_ll_kv={nominal_voltage_ll_kv!r} must be a finite, positive number."
        )
    config = _existing_or_default_config(workspace_id, measurement_group_id, voltage_config_registry=voltage_config_registry)
    config.nominal_voltage_ll_kv = nominal_voltage_ll_kv
    voltage_config_registry.upsert(config)
    return config


def set_manual_voltage_reference(
    *,
    workspace_id: str,
    measurement_group_id: str,
    reference: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> VoltageBaseConfiguration:
    """Switches this group to `reference_mode="manual"` with an explicit
    override -- the engineer's own authority always wins over automatic
    detection (canonical document section 7/16)."""
    _get_voltage_group(workspace_id, measurement_group_id, group_registry=group_registry)
    if not voltage_reference_value_valid(reference):
        raise InvalidVoltageReferenceOverrideError(f"Unknown voltage reference {reference!r}.")
    config = _existing_or_default_config(workspace_id, measurement_group_id, voltage_config_registry=voltage_config_registry)
    config.reference_mode = VOLTAGE_REFERENCE_MODE_MANUAL
    config.reference_override = reference
    voltage_config_registry.upsert(config)
    return config


def return_voltage_reference_to_auto(
    *,
    workspace_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> VoltageBaseConfiguration:
    """Returns this group to `reference_mode="auto"`, clearing the
    manual override entirely -- never leaves a stale override sitting
    invisibly in the record (canonical document section 15's own
    explicit requirement). Because `resolve_effective_voltage_reference_for_group()`
    always re-derives the auto result live from the group's own CURRENT
    channel membership rather than reading a cached value, this alone
    is sufficient to make "Return to Auto" correct -- there is no
    separate re-detection step to remember to run."""
    _get_voltage_group(workspace_id, measurement_group_id, group_registry=group_registry)
    config = _existing_or_default_config(workspace_id, measurement_group_id, voltage_config_registry=voltage_config_registry)
    config.reference_mode = VOLTAGE_REFERENCE_MODE_AUTO
    config.reference_override = None
    voltage_config_registry.upsert(config)
    return config


def get_effective_voltage_reference(
    *,
    workspace_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> VoltageReferenceDetection:
    """Live effective reference for this group -- auto-detected from its
    own current channel membership, or the manual override, per
    `resolve_effective_voltage_reference_for_group()`'s own contract."""
    group = _get_voltage_group(workspace_id, measurement_group_id, group_registry=group_registry)
    config = voltage_config_registry.get(workspace_id, measurement_group_id)
    return resolve_effective_voltage_reference_for_group(group, config)


def resolve_group_voltage_base(
    *,
    workspace_id: str,
    measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
) -> VoltageBaseResolution:
    """The one group-level PU-denominator resolution authority exposed
    at the service layer -- resolves the group + its configuration (if
    any) and delegates to `resolve_voltage_base_for_group()` (pure
    domain logic, see that function's own docstring for the full
    four-step resolution order, including the `confirmed`/`manual`-only
    authoritative-status gate).

    Deliberately does NOT reject a non-Voltage group the way the
    configuration mutators above do (`_get_voltage_group()`) -- a
    RESOLUTION query is read-only and should gracefully report
    `STATUS_NOT_APPLICABLE` for a Current group, mirroring
    `per_unit.resolve_per_unit()`'s own "not_applicable, never an
    error" contract for an ineligible engineering type. CONFIGURING a
    Current group, by contrast, is a genuine caller mistake and is
    rejected loudly (section 23) -- the two are intentionally
    asymmetric."""
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    config = voltage_config_registry.get(workspace_id, measurement_group_id)
    return resolve_voltage_base_for_group(group, config)
