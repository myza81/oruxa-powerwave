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
from app.domain.base_authority import BASE_AUTHORITY_MANUAL
from app.domain.voltage_primary_secondary import secondary_voltage_ll_v_valid
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

# Sentinel distinguishing "secondary not given" from "explicitly clear to None".
_SECONDARY_NOT_GIVEN: object = object()
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


def update_voltage_configuration(
    *, workspace_id: str, measurement_group_id: str,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    nominal_voltage_ll_kv: float | None = None,
    reference_mode: str | None = None,
    reference_override: str | None = None,
    base_reference_side: str | None = None,
    secondary_voltage_ll_v: object = _SECONDARY_NOT_GIVEN,
) -> VoltageBaseConfiguration:
    """Validate the entire requested edit before one registry replacement.

    None nominal means preserve the base. None mode (individual service
    setters only) preserves the reference pair; the API supplies its existing
    default 'auto'. Auto clears overrides, manual requires a valid override.
    None base_reference_side preserves the existing side declaration.
    No live configuration object is modified while validating.

    Authority rule (Slice 5C-1): an accepted nominal_voltage_ll_kv value
    atomically establishes base_authority="manual", regardless of the
    previous state (including auto_resolved, needs_review, or unavailable).
    Reference-only changes (nominal_voltage_ll_kv=None) leave authority
    unchanged. base_authority is NOT a parameter — it is derived internally
    to prevent callers from injecting automatic states (auto_resolved may
    only be set by the future auto-resolution service).

    Secondary reference rule (Slice 5D-1): when nominal_voltage_ll_kv is
    being changed and secondary_voltage_ll_v is not explicitly supplied, the
    existing secondary_voltage_ll_v is cleared. This prevents a stale
    secondary reference from remaining authoritative after the primary nominal
    is updated. To preserve secondary while changing primary, supply both.
    To explicitly clear secondary, pass secondary_voltage_ll_v=None with the
    sentinel sentinel distinguished from "not given" by using this function's
    own _SECONDARY_NOT_GIVEN default.
    """
    from app.domain.reference_side import REFERENCE_SIDES
    _get_voltage_group(workspace_id, measurement_group_id, group_registry=group_registry)
    if nominal_voltage_ll_kv is not None and not voltage_base_valid(nominal_voltage_ll_kv):
        raise InvalidVoltageBaseValueError(
            f"nominal_voltage_ll_kv={nominal_voltage_ll_kv!r} must be a finite, positive number."
        )
    if reference_mode is not None and reference_mode not in KNOWN_VOLTAGE_REFERENCE_MODES:
        raise InvalidVoltageReferenceOverrideError(f"Unknown voltage reference mode {reference_mode!r}.")
    if reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL and not voltage_reference_value_valid(reference_override):
        raise InvalidVoltageReferenceOverrideError(f"Unknown voltage reference {reference_override!r}.")
    if base_reference_side is not None and base_reference_side not in REFERENCE_SIDES:
        raise InvalidVoltageBaseValueError(
            f"base_reference_side={base_reference_side!r} must be one of {REFERENCE_SIDES}."
        )
    # Validate and resolve secondary_voltage_ll_v update intent.
    sec_given = secondary_voltage_ll_v is not _SECONDARY_NOT_GIVEN
    sec_value = secondary_voltage_ll_v if sec_given else None
    if sec_given and sec_value is not None and not secondary_voltage_ll_v_valid(sec_value):
        raise InvalidVoltageBaseValueError(
            f"secondary_voltage_ll_v={sec_value!r} must be a finite, positive number."
        )
    # Stale-secondary clearing: if primary nominal is being updated without an explicit secondary
    # value, invalidate any previously stored secondary_voltage_ll_v.
    if not sec_given and nominal_voltage_ll_kv is not None:
        sec_given = True
        sec_value = None
    # Derive authority from the content of the edit — never from caller-supplied value.
    effective_authority = BASE_AUTHORITY_MANUAL if nominal_voltage_ll_kv is not None else None
    return voltage_config_registry.update_fields(
        workspace_id, measurement_group_id, nominal_voltage_ll_kv=nominal_voltage_ll_kv,
        reference_mode=reference_mode,
        reference_override=reference_override if reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL else None,
        base_reference_side=base_reference_side,
        base_authority=effective_authority,
        secondary_voltage_ll_v=sec_value,
        update_secondary=sec_given,
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
    return update_voltage_configuration(
        workspace_id=workspace_id, measurement_group_id=measurement_group_id,
        nominal_voltage_ll_kv=nominal_voltage_ll_kv,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
    )


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
    return update_voltage_configuration(
        workspace_id=workspace_id, measurement_group_id=measurement_group_id,
        reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL, reference_override=reference,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
    )


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
    return update_voltage_configuration(
        workspace_id=workspace_id, measurement_group_id=measurement_group_id,
        reference_mode=VOLTAGE_REFERENCE_MODE_AUTO,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
    )


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
