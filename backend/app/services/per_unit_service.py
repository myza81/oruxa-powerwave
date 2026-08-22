"""Per-Unit Base Profile orchestration (Phase 5C, DEC-049).

Validates submitted base fields against app.domain.per_unit's own
validators, resolves `ChannelRef`s against the live source/calculated-
channel registries (existence + Voltage/Current eligibility, section
20-24), drives `PerUnitRegistry.assign_channels()`'s conflict/
reassignment rule (decision 4), and runs the inheritance-recompute
cascade (decision 7) after any mutation that could change a channel's
own resolved profile.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.per_unit import (
    PerUnitBaseProfile,
    apparent_power_base_valid,
    direct_current_base_valid,
    voltage_base_valid,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import InvalidChannelAssignmentError, InvalidPerUnitBaseError, PerUnitProfileNotFoundError
from app.services.per_unit_registry import PerUnitRegistry, recompute_inherited_per_unit_assignments
from app.services.workspace_registry import WorkspaceRegistry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_base_fields(
    *,
    voltage_base_value: float | None,
    voltage_base_unit: str | None,
    apparent_power_base_value: float | None,
    apparent_power_base_unit: str | None,
    current_base_mode: str,
    direct_current_base_value: float | None,
    direct_current_base_unit: str | None,
) -> None:
    """Each base field pair is either fully unset (`None`/`None` -- the
    valid "not yet configured" state) or a validly-shaped value+unit
    pair -- never a partial pair, and never an invalid one."""
    if (voltage_base_value is not None or voltage_base_unit is not None) and not voltage_base_valid(
        voltage_base_value, voltage_base_unit
    ):
        raise InvalidPerUnitBaseError("Voltage base must be a finite, positive number in V or kV.")
    if (apparent_power_base_value is not None or apparent_power_base_unit is not None) and not apparent_power_base_valid(
        apparent_power_base_value, apparent_power_base_unit
    ):
        raise InvalidPerUnitBaseError("Three-phase MVA base must be a finite, positive number in MVA.")
    if current_base_mode == "direct" and not direct_current_base_valid(
        direct_current_base_value, direct_current_base_unit
    ):
        raise InvalidPerUnitBaseError("Direct current base must be a finite, positive number in A or kA.")


def _engineering_type_for_channel_ref(
    ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry
) -> str | None:
    """`None` if the ref does not resolve to any real/calculated channel
    in this workspace at all -- distinct from a channel that resolves
    but is not Voltage/Current (caller decides what to do with each)."""
    if ref.kind == "source":
        active = source_registry.get(workspace_id, ref.source_id)
        if active is None:
            return None
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None)
        return matching.engineering_type if matching is not None else None
    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    return calc.engineering_type if calc is not None else None


def _validate_assignable_channels(
    channel_refs: list[ChannelRef],
    *,
    workspace_id: str,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> None:
    """Section 20-24: only Voltage/Current channels may be assigned to a
    per-unit base profile -- an unknown ref, or one resolving to any
    other engineering_type, is rejected outright."""
    for ref in channel_refs:
        engineering_type = _engineering_type_for_channel_ref(
            ref, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry
        )
        if engineering_type is None:
            raise InvalidChannelAssignmentError("One or more assigned channels do not exist in this workspace.")
        if engineering_type not in (VOLTAGE, CURRENT):
            raise InvalidChannelAssignmentError(
                "Only Voltage and Current channels may be assigned to a per-unit base profile."
            )


def create_per_unit_profile(
    *,
    workspace_id: str,
    name: str,
    voltage_base_value: float | None,
    voltage_base_unit: str | None,
    voltage_basis: str,
    apparent_power_base_value: float | None,
    apparent_power_base_unit: str | None,
    current_base_mode: str,
    direct_current_base_value: float | None,
    direct_current_base_unit: str | None,
    registry: PerUnitRegistry,
) -> PerUnitBaseProfile:
    """A brand-new profile always starts with `assigned_channels=[]` --
    it can never conflict with anything (decision 4's conflict check only
    ever matters on a later PUT)."""
    _validate_base_fields(
        voltage_base_value=voltage_base_value, voltage_base_unit=voltage_base_unit,
        apparent_power_base_value=apparent_power_base_value, apparent_power_base_unit=apparent_power_base_unit,
        current_base_mode=current_base_mode,
        direct_current_base_value=direct_current_base_value, direct_current_base_unit=direct_current_base_unit,
    )
    profile = PerUnitBaseProfile(
        id="pu-" + uuid4().hex,
        workspace_id=workspace_id,
        name=name.strip(),
        voltage_base_value=voltage_base_value,
        voltage_base_unit=voltage_base_unit,
        voltage_basis=voltage_basis,
        apparent_power_base_value=apparent_power_base_value,
        apparent_power_base_unit=apparent_power_base_unit,
        current_base_mode=current_base_mode,
        direct_current_base_value=direct_current_base_value,
        direct_current_base_unit=direct_current_base_unit,
        assigned_channels=[],
        created_at=_utc_now(),
    )
    registry.add(profile)
    return profile


def update_per_unit_profile(
    *,
    workspace_id: str,
    profile_id: str,
    name: str,
    voltage_base_value: float | None,
    voltage_base_unit: str | None,
    voltage_basis: str,
    apparent_power_base_value: float | None,
    apparent_power_base_unit: str | None,
    current_base_mode: str,
    direct_current_base_value: float | None,
    direct_current_base_unit: str | None,
    assigned_channels: list[ChannelRef],
    reassign_conflicting: bool,
    registry: PerUnitRegistry,
    calc_registry: CalculatedChannelRegistry,
    source_registry: WorkspaceRegistry,
) -> PerUnitBaseProfile:
    """Full replace of one profile's base fields + channel assignment
    (decision 4). Base-field validation and channel-eligibility
    validation both happen BEFORE any registry mutation -- an invalid
    request never partially applies."""
    _validate_base_fields(
        voltage_base_value=voltage_base_value, voltage_base_unit=voltage_base_unit,
        apparent_power_base_value=apparent_power_base_value, apparent_power_base_unit=apparent_power_base_unit,
        current_base_mode=current_base_mode,
        direct_current_base_value=direct_current_base_value, direct_current_base_unit=direct_current_base_unit,
    )
    profile = registry.get(workspace_id, profile_id)
    if profile is None:
        raise PerUnitProfileNotFoundError(f"No per-unit profile '{profile_id}' in this workspace.")
    _validate_assignable_channels(
        assigned_channels, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry
    )

    # assign_channels() raises ChannelAlreadyAssignedError (mutating
    # nothing) before any base field below is written, unless the caller
    # already confirmed reassign_conflicting=True.
    changed = registry.assign_channels(
        workspace_id, profile_id, assigned_channels, reassign_conflicting=reassign_conflicting
    )

    profile.name = name.strip()
    profile.voltage_base_value = voltage_base_value
    profile.voltage_base_unit = voltage_base_unit
    profile.voltage_basis = voltage_basis
    profile.apparent_power_base_value = apparent_power_base_value
    profile.apparent_power_base_unit = apparent_power_base_unit
    profile.current_base_mode = current_base_mode
    profile.direct_current_base_value = direct_current_base_value
    profile.direct_current_base_unit = direct_current_base_unit

    if changed:
        recompute_inherited_per_unit_assignments(
            workspace_id, changed, per_unit_registry=registry, calc_registry=calc_registry
        )
    return profile


def delete_per_unit_profile(
    *, workspace_id: str, profile_id: str, registry: PerUnitRegistry, calc_registry: CalculatedChannelRegistry
) -> None:
    affected = registry.delete_profile(workspace_id, profile_id)
    if affected:
        recompute_inherited_per_unit_assignments(
            workspace_id, affected, per_unit_registry=registry, calc_registry=calc_registry
        )
