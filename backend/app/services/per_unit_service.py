"""Per-Unit Base configuration orchestration (Phase 5C, DEC-049;
source-bound redesign following owner UAT).

Every real source currently in the workspace is a candidate for its own
Per-Unit configuration -- this module lists them all (configured or
not), validates and stores one source's own configuration on
create/update, and runs the calculated-channel inheritance-recompute
cascade whenever a source's configuration is created, updated, or
deleted (its own resolved profile -- always a source_id under this
redesign -- may have just changed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.channel_classification import VOLTAGE
from app.domain.per_unit import (
    KNOWN_CURRENT_BASE_MODES,
    KNOWN_VOLTAGE_REFERENCE_MODES,
    PerUnitBaseProfile,
    apparent_power_base_valid,
    direct_current_base_valid,
    resolve_current_base_amps,
    resolve_effective_voltage_reference,
    voltage_base_valid,
)
from app.domain.voltage_reference import KNOWN_VOLTAGE_REFERENCES
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import InvalidPerUnitBaseError, SourceNotFoundError
from app.services.per_unit_registry import PerUnitRegistry, recompute_inherited_per_unit_assignments
from app.services.workspace_registry import WorkspaceRegistry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def voltage_channel_names_for_source(source_registry: WorkspaceRegistry, workspace_id: str, source_id: str) -> list[str]:
    """The owning source's own full list of Voltage-classified channel
    names -- the input to automatic Voltage Reference detection
    (app.domain.voltage_reference.detect_voltage_reference)."""
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        return []
    return [ch.name for ch in active.metadata.analog_channels if ch.engineering_type == VOLTAGE]


@dataclass(slots=True)
class SourcePerUnitConfigView:
    """One source's own Per-Unit configuration, as the setup UI needs to
    render it -- whether or not it has actually been configured yet
    (`configured=False` sources still carry a live voltage-reference
    detection preview, section 1's own "show each loaded source
    automatically" requirement)."""

    source_id: str
    configured: bool
    voltage_base_value: float | None
    voltage_reference_mode: str
    voltage_reference_override: str | None
    effective_voltage_reference: str | None
    voltage_reference_evidence: list[str]
    voltage_reference_reason: str
    current_base_mode: str
    apparent_power_base_value: float | None
    direct_current_base_value: float | None
    resolved_current_base_amps: float | None
    created_at: datetime | None


def _view_for_source(
    *, workspace_id: str, source_id: str, profile: PerUnitBaseProfile | None, source_registry: WorkspaceRegistry
) -> SourcePerUnitConfigView:
    voltage_names = voltage_channel_names_for_source(source_registry, workspace_id, source_id)
    detection = resolve_effective_voltage_reference(profile, voltage_names)
    resolved_amps: float | None = None
    if profile is not None:
        resolved_amps, _reason = resolve_current_base_amps(profile, detection.reference)
    return SourcePerUnitConfigView(
        source_id=source_id,
        configured=profile is not None,
        voltage_base_value=profile.voltage_base_value if profile else None,
        voltage_reference_mode=profile.voltage_reference_mode if profile else "auto",
        voltage_reference_override=profile.voltage_reference_override if profile else None,
        effective_voltage_reference=detection.reference,
        voltage_reference_evidence=detection.evidence_names,
        voltage_reference_reason=detection.reason,
        current_base_mode=profile.current_base_mode if profile else "none",
        apparent_power_base_value=profile.apparent_power_base_value if profile else None,
        direct_current_base_value=profile.direct_current_base_value if profile else None,
        resolved_current_base_amps=resolved_amps,
        created_at=profile.created_at if profile else None,
    )


def list_source_per_unit_configs(
    *, workspace_id: str, registry: PerUnitRegistry, source_registry: WorkspaceRegistry
) -> list[SourcePerUnitConfigView]:
    """Section 1: every source currently loaded in the workspace appears
    automatically -- configured or not -- so the engineer never has to
    "create" anything to see their file listed."""
    views = []
    for active in source_registry.list_for_workspace(workspace_id):
        source_id = active.metadata.source_id
        profile = registry.get(workspace_id, source_id)
        views.append(_view_for_source(workspace_id=workspace_id, source_id=source_id, profile=profile, source_registry=source_registry))
    return views


def get_source_per_unit_config(
    *, workspace_id: str, source_id: str, registry: PerUnitRegistry, source_registry: WorkspaceRegistry
) -> SourcePerUnitConfigView:
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    profile = registry.get(workspace_id, source_id)
    return _view_for_source(workspace_id=workspace_id, source_id=source_id, profile=profile, source_registry=source_registry)


def _validate_base_fields(
    *,
    voltage_base_value: float | None,
    voltage_reference_mode: str,
    voltage_reference_override: str | None,
    current_base_mode: str,
    apparent_power_base_value: float | None,
    direct_current_base_value: float | None,
) -> None:
    if voltage_base_value is not None and not voltage_base_valid(voltage_base_value):
        raise InvalidPerUnitBaseError("Voltage Base must be a finite, positive number of kV.")
    if voltage_reference_mode not in KNOWN_VOLTAGE_REFERENCE_MODES:
        raise InvalidPerUnitBaseError(f"voltage_reference_mode must be one of {KNOWN_VOLTAGE_REFERENCE_MODES}.")
    if voltage_reference_mode == "manual" and voltage_reference_override not in KNOWN_VOLTAGE_REFERENCES:
        raise InvalidPerUnitBaseError(f"voltage_reference_override must be one of {KNOWN_VOLTAGE_REFERENCES} in manual mode.")
    if current_base_mode not in KNOWN_CURRENT_BASE_MODES:
        raise InvalidPerUnitBaseError(f"current_base_mode must be one of {KNOWN_CURRENT_BASE_MODES}.")
    if current_base_mode == "derived" and apparent_power_base_value is not None and not apparent_power_base_valid(apparent_power_base_value):
        raise InvalidPerUnitBaseError("Three-Phase MVA Base must be a finite, positive number of MVA.")
    if current_base_mode == "direct" and direct_current_base_value is not None and not direct_current_base_valid(direct_current_base_value):
        raise InvalidPerUnitBaseError("Direct current base must be a finite, positive number of kA.")


def upsert_source_per_unit_config(
    *,
    workspace_id: str,
    source_id: str,
    voltage_base_value: float | None,
    voltage_reference_mode: str,
    voltage_reference_override: str | None,
    current_base_mode: str,
    apparent_power_base_value: float | None,
    direct_current_base_value: float | None,
    registry: PerUnitRegistry,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> SourcePerUnitConfigView:
    """Create-or-replace ONE source's own Per-Unit configuration
    (section 1: no separate profile identity, no channel-assignment
    step -- every eligible channel of this source starts using it
    automatically the moment this call returns). Runs the calculated-
    channel inheritance-recompute cascade afterward, since any
    calculated channel auto-inheriting from this source may now resolve
    differently."""
    if source_registry.get(workspace_id, source_id) is None:
        raise SourceNotFoundError(f"No source '{source_id}' in workspace '{workspace_id}'.")
    _validate_base_fields(
        voltage_base_value=voltage_base_value,
        voltage_reference_mode=voltage_reference_mode,
        voltage_reference_override=voltage_reference_override,
        current_base_mode=current_base_mode,
        apparent_power_base_value=apparent_power_base_value,
        direct_current_base_value=direct_current_base_value,
    )
    existing = registry.get(workspace_id, source_id)
    profile = PerUnitBaseProfile(
        source_id=source_id,
        workspace_id=workspace_id,
        voltage_base_value=voltage_base_value,
        voltage_reference_mode=voltage_reference_mode,
        voltage_reference_override=voltage_reference_override if voltage_reference_mode == "manual" else None,
        current_base_mode=current_base_mode,
        apparent_power_base_value=apparent_power_base_value if current_base_mode == "derived" else None,
        direct_current_base_value=direct_current_base_value if current_base_mode == "direct" else None,
        created_at=existing.created_at if existing is not None else _utc_now(),
    )
    registry.upsert(profile)
    recompute_inherited_per_unit_assignments(
        workspace_id, [source_id], per_unit_registry=registry, calc_registry=calc_registry, source_registry=source_registry
    )
    return _view_for_source(workspace_id=workspace_id, source_id=source_id, profile=profile, source_registry=source_registry)


def delete_source_per_unit_config(
    *,
    workspace_id: str,
    source_id: str,
    registry: PerUnitRegistry,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> None:
    existed = registry.delete(workspace_id, source_id)
    if existed:
        recompute_inherited_per_unit_assignments(
            workspace_id, [source_id], per_unit_registry=registry, calc_registry=calc_registry, source_registry=source_registry
        )
