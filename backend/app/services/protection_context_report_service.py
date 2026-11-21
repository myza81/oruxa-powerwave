"""D5A-2A: read-only authoritative CT/VT context report for one protection analysis.

Resolves the voltage and current channels an analysis would use (through the SAME
requirement and role mappings its compute path uses), looks up their Recording Details
Measurement Group CT/VT and declared measurement sides, and compares the request's own
CT/VT and recording-basis assumptions against that authority. Nothing is converted,
persisted or overridden.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.analysis_input_resolution import STATUS_RESOLVED
from app.domain.calculated_channel import ChannelRef
from app.domain.distance_protection import LOOP_ROLE_KEYS
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.overcurrent_analysis_service import _REQUIREMENT_BY_PHASE, _ROLE_KEY_BY_PHASE
from app.services.phasor_analysis_service import _DIAGRAM_REQUIREMENTS_BY_ROLE
from app.services.protection_instrument_context import (
    QUANTITY_CURRENT,
    QUANTITY_VOLTAGE,
    ChannelFacts,
    TransformerContext,
    resolve_channel_facts,
    resolve_transformer_context,
)
from app.services.protection_instrument_diagnostics import (
    ANALYSIS_DISTANCE,
    ANALYSIS_IMPEDANCE,
    ANALYSIS_OVERCURRENT,
    KNOWN_ANALYSES,
    Diagnostic,
    RequestAssumptions,
    build_diagnostics,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry


class InvalidProtectionContextRequest(ValueError):
    """Unknown analysis, or the phase/loop that analysis requires is missing or unknown."""


@dataclass(frozen=True, slots=True)
class RoleFacts:
    role_key: str
    facts: ChannelFacts


@dataclass(frozen=True, slots=True)
class ProtectionContextReport:
    analysis: str
    engineering_context_id: str
    phase: str | None
    loop: str | None
    channels: tuple[RoleFacts, ...]
    voltage: TransformerContext | None
    current: TransformerContext | None
    request: RequestAssumptions
    diagnostics: tuple[Diagnostic, ...]


def _role_plan(analysis: str, phase: str | None, loop: str | None) -> tuple[tuple[str, object], ...]:
    """(role_key, AnalysisRequirement) pairs, mirroring each analysis's own compute path."""
    if analysis not in KNOWN_ANALYSES:
        raise InvalidProtectionContextRequest(f"analysis must be one of {KNOWN_ANALYSES}.")
    if analysis == ANALYSIS_OVERCURRENT:
        if phase not in _REQUIREMENT_BY_PHASE:
            raise InvalidProtectionContextRequest("phase must be one of 'A', 'B', 'C' for overcurrent.")
        return ((_ROLE_KEY_BY_PHASE[phase], _REQUIREMENT_BY_PHASE[phase]),)
    if analysis == ANALYSIS_IMPEDANCE:
        if phase not in ("A", "B", "C"):
            raise InvalidProtectionContextRequest("phase must be one of 'A', 'B', 'C' for impedance.")
        keys = ("V" + phase.lower(), "I" + phase.lower())
    else:
        if loop not in LOOP_ROLE_KEYS:
            raise InvalidProtectionContextRequest(f"loop must be one of {tuple(LOOP_ROLE_KEYS)} for distance_protection.")
        keys = LOOP_ROLE_KEYS[loop]
    return tuple((key, _DIAGRAM_REQUIREMENTS_BY_ROLE[key]) for key in keys)


def build_protection_context_report(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis: str,
    phase: str | None,
    loop: str | None,
    request: RequestAssumptions,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
) -> ProtectionContextReport:
    plan = _role_plan(analysis, phase, loop)
    resolved: list[tuple[str, ChannelRef]] = []
    unresolved: list[tuple[str, str, str | None]] = []
    for role_key, requirement in plan:
        resolution = resolve_analysis_inputs(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            analysis_kind=requirement.analysis_kind, mode=requirement.mode, context_registry=context_registry,
            source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
        )
        if resolution.status == STATUS_RESOLVED:
            resolved.append((role_key, resolution.resolved_roles[role_key]))
        else:
            unresolved.append((role_key, resolution.status,
                               resolution.reason_code or resolution.missing_role_reasons.get(role_key)))

    def quantity_of(role_key: str) -> str:
        return QUANTITY_VOLTAGE if role_key.startswith("V") else QUANTITY_CURRENT

    lookup = dict(
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry, source_registry=source_registry,
    )
    channels = tuple(
        RoleFacts(role_key, resolve_channel_facts(
            workspace_id, ref, quantity_of(role_key), group_registry=group_registry, source_registry=source_registry))
        for role_key, ref in resolved
    )
    uses_voltage = analysis != ANALYSIS_OVERCURRENT
    voltage = resolve_transformer_context(
        workspace_id, [r for k, r in resolved if quantity_of(k) == QUANTITY_VOLTAGE], QUANTITY_VOLTAGE, **lookup,
    ) if uses_voltage else None
    current = resolve_transformer_context(
        workspace_id, [r for k, r in resolved if quantity_of(k) == QUANTITY_CURRENT], QUANTITY_CURRENT, **lookup,
    )
    diagnostics = build_diagnostics(
        analysis, voltage, current, request, unresolved_roles=tuple(unresolved),
    )
    return ProtectionContextReport(
        analysis=analysis, engineering_context_id=engineering_context_id, phase=phase, loop=loop,
        channels=channels, voltage=voltage, current=current, request=request, diagnostics=tuple(diagnostics),
    )
