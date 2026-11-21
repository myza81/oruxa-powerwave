"""D5A-1: authoritative CT/VT and measurement-side lookup for protection analyses.

Read-only contract. Given the voltage/current channels an analysis resolved,
report (a) the CT/VT ratio configured on the owning Measurement Groups in
Recording Details and (b) the physical measurement side each quantity's
recording declares. The two are independent and never inferred from each other:
a configured ratio is configuration data, not evidence of the measurement side.

Deliberate limits (no numerical policy is introduced here):
  * Nothing is converted and no analysis consumes this yet.
  * Only the raw stored configuration is read. The synthesised `auto_nominal`
    VT of `measurement_group_view_service` (nominal kV over an assumed 110 V)
    is an assumption, not evidence, and is not consumable.
  * Only `manual` and `recording_metadata` ratio authorities are consumable.
  * Voltage and Current sides are resolved independently and may differ.
  * An unknown or mixed side yields no proposed basis; it is never defaulted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

QUANTITY_VOLTAGE = "voltage"
QUANTITY_CURRENT = "current"

RATIO_CONFIGURED = "configured"
RATIO_NO_CHANNELS = "no_channels"
RATIO_NO_GROUP = "no_group"
RATIO_NOT_CONFIGURED = "not_configured"
RATIO_UNTRUSTED_AUTHORITY = "untrusted_authority"
RATIO_INVALID = "invalid"
RATIO_CONFLICT = "conflict"

SIDE_DECLARED = "recording_declared"
SIDE_UNKNOWN = "unknown"
SIDE_MIXED = "mixed"

CONSUMABLE_AUTHORITIES = ("manual", "recording_metadata")


@dataclass(frozen=True, slots=True)
class TransformerContext:
    """CT (current) or VT (voltage) configuration plus declared measurement side."""

    quantity: str
    ratio_status: str
    group_ids: tuple[str, ...] = ()
    primary: float | None = None
    secondary: float | None = None
    authority: str = "not_configured"
    reason: str | None = None
    side: str = "unknown"
    side_status: str = SIDE_UNKNOWN
    provenance_note: str | None = None
    # Voltage only: a nominal kV exists on the group but no VT does. Reported so the display-only
    # nominal is visibly NOT used; never a ratio.
    ignored_nominal_kv: float | None = None

    @property
    def ratio_consumable(self) -> bool:
        return self.ratio_status == RATIO_CONFIGURED

    @property
    def ratio(self) -> float | None:
        """primary / secondary, the codebase's CT/VT ratio convention; None unless consumable."""
        if not self.ratio_consumable or self.primary is None or not self.secondary:
            return None
        return self.primary / self.secondary

    @property
    def declared_basis(self) -> str | None:
        """'primary'/'secondary' only when the recording declares it; otherwise None."""
        if self.side_status == SIDE_DECLARED and self.side in ("primary", "secondary"):
            return self.side
        return None


@dataclass(frozen=True, slots=True)
class ProtectionInstrumentContext:
    voltage: TransformerContext
    current: TransformerContext


def _valid_pair(primary: float | None, secondary: float | None) -> bool:
    return (
        isinstance(primary, (int, float)) and isinstance(secondary, (int, float))
        and not isinstance(primary, bool) and not isinstance(secondary, bool)
        and math.isfinite(primary) and math.isfinite(secondary) and primary > 0 and secondary > 0
    )


def _declared_side(workspace_id: str, ref: ChannelRef, source_registry: WorkspaceRegistry) -> tuple[str, str | None]:
    """(side, provider_type) as the recording declares it; anything else is 'unknown'."""
    if ref.kind != "source":
        return "unknown", None
    active = source_registry.get(workspace_id, ref.source_id)
    if active is None:
        return "unknown", None
    channel = next((c for c in active.metadata.analog_channels if c.name == ref.channel_name), None)
    side = channel.measurement_side if channel is not None else "unknown"
    return (side if side in ("primary", "secondary") else "unknown"), active.metadata.provider_type


@dataclass(frozen=True, slots=True)
class ChannelFacts:
    """What the recording and Recording Details say about ONE channel."""

    ref: ChannelRef
    quantity: str
    group_id: str | None
    group_kind: str | None
    declared_side: str
    provider_type: str | None


def resolve_channel_facts(
    workspace_id: str,
    ref: ChannelRef,
    quantity: str,
    *,
    group_registry: MeasurementGroupRegistry,
    source_registry: WorkspaceRegistry,
) -> ChannelFacts:
    group_id = group_registry.group_for_channel(workspace_id, ref) if ref.kind == "source" else None
    group = group_registry.get(workspace_id, group_id) if group_id is not None else None
    side, provider_type = _declared_side(workspace_id, ref, source_registry)
    return ChannelFacts(
        ref=ref, quantity=quantity, group_id=group.id if group else None, group_kind=group.kind if group else None,
        declared_side=side, provider_type=provider_type,
    )


def resolve_channel_unit(
    workspace_id: str, ref: ChannelRef, *, source_registry: WorkspaceRegistry, calculated_channel_registry,
) -> str | None:
    """The unit the channel itself declares (None if it cannot be found); never guessed."""
    if ref.kind == "source":
        active = source_registry.get(workspace_id, ref.source_id)
        if active is None:
            return None
        channel = next((c for c in active.metadata.analog_channels if c.name == ref.channel_name), None)
        return channel.unit if channel is not None else None
    calculated = calculated_channel_registry.get(workspace_id, ref.calculated_channel_id)
    return calculated.unit if calculated is not None else None


def _resolve_side(
    workspace_id: str, refs: tuple[ChannelRef, ...], source_registry: WorkspaceRegistry,
) -> tuple[str, str]:
    sides: set[str] = set()
    for ref in refs:
        sides.add(_declared_side(workspace_id, ref, source_registry)[0])
    if sides == {"primary"}:
        return "primary", SIDE_DECLARED
    if sides == {"secondary"}:
        return "secondary", SIDE_DECLARED
    if sides == {"primary", "secondary"}:
        return "unknown", SIDE_MIXED
    return "unknown", SIDE_UNKNOWN


def resolve_transformer_context(
    workspace_id: str,
    refs: Iterable[ChannelRef],
    quantity: str,
    *,
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    source_registry: WorkspaceRegistry,
) -> TransformerContext:
    if quantity not in (QUANTITY_VOLTAGE, QUANTITY_CURRENT):
        raise ValueError(f"quantity must be 'voltage' or 'current', not {quantity!r}")
    refs = tuple(refs)
    if not refs:
        return TransformerContext(quantity=quantity, ratio_status=RATIO_NO_CHANNELS, reason="no channels resolved")
    side, side_status = _resolve_side(workspace_id, refs, source_registry)
    kind = KIND_VOLTAGE if quantity == QUANTITY_VOLTAGE else KIND_CURRENT

    def blocked(status: str, reason: str, group_ids: tuple[str, ...] = (), authority: str = "not_configured",
                ignored_nominal_kv: float | None = None):
        return TransformerContext(
            quantity=quantity, ratio_status=status, group_ids=group_ids, authority=authority,
            reason=reason, side=side, side_status=side_status, ignored_nominal_kv=ignored_nominal_kv,
        )

    group_ids: list[str] = []
    pairs: list[tuple[float, float]] = []
    authority = "not_configured"
    note: str | None = None
    for ref in refs:
        label = ref.channel_name if ref.kind == "source" else f"calculated:{ref.calculated_channel_id}"
        group_id = group_registry.group_for_channel(workspace_id, ref) if ref.kind == "source" else None
        group = group_registry.get(workspace_id, group_id) if group_id is not None else None
        if group is None or group.kind != kind:
            return blocked(RATIO_NO_GROUP, f"{label} is not in a {quantity} Measurement Group")
        if quantity == QUANTITY_VOLTAGE:
            config = voltage_config_registry.get(workspace_id, group.id)
            primary, secondary = (config.vt_primary_v, config.vt_secondary_v) if config else (None, None)
            authority = config.vt_authority if config else "not_configured"
            note = (config.vt_provenance_note if config else None) or note
        else:
            config = current_config_registry.get(workspace_id, group.id)
            primary, secondary = (config.ct_primary_a, config.ct_secondary_a) if config else (None, None)
            authority = config.ct_authority if config else "not_configured"
            note = (config.ct_provenance_note if config else None) or note
        group_ids.append(group.id)
        if config is None or authority == "not_configured":
            nominal = getattr(config, "nominal_voltage_ll_kv", None) if quantity == QUANTITY_VOLTAGE else None
            nominal = float(nominal) if isinstance(nominal, (int, float)) and not isinstance(nominal, bool) \
                and math.isfinite(nominal) and nominal > 0 else None
            return blocked(RATIO_NOT_CONFIGURED, f"group {group.id} has no {quantity} transformer ratio",
                           tuple(group_ids), ignored_nominal_kv=nominal)
        if authority not in CONSUMABLE_AUTHORITIES:
            return blocked(RATIO_UNTRUSTED_AUTHORITY, f"group {group.id} ratio authority {authority!r} is not consumable",
                           tuple(group_ids), authority)
        if not _valid_pair(primary, secondary):
            return blocked(RATIO_INVALID, f"group {group.id} ratio is not a finite positive pair", tuple(group_ids), authority)
        pairs.append((float(primary), float(secondary)))

    first = pairs[0]
    if any(not math.isclose(p / s, first[0] / first[1], rel_tol=1e-9) for p, s in pairs[1:]):
        return blocked(RATIO_CONFLICT, "resolved channels belong to groups with different ratios",
                       tuple(dict.fromkeys(group_ids)), authority)
    return TransformerContext(
        quantity=quantity, ratio_status=RATIO_CONFIGURED, group_ids=tuple(dict.fromkeys(group_ids)),
        primary=first[0], secondary=first[1], authority=authority, side=side, side_status=side_status,
        provenance_note=note,
    )


def resolve_protection_instrument_context(
    workspace_id: str,
    *,
    voltage_refs: Iterable[ChannelRef],
    current_refs: Iterable[ChannelRef],
    group_registry: MeasurementGroupRegistry,
    voltage_config_registry: VoltageGroupConfigRegistry,
    current_config_registry: CurrentGroupConfigRegistry,
    source_registry: WorkspaceRegistry,
) -> ProtectionInstrumentContext:
    shared = dict(
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry, source_registry=source_registry,
    )
    return ProtectionInstrumentContext(
        voltage=resolve_transformer_context(workspace_id, voltage_refs, QUANTITY_VOLTAGE, **shared),
        current=resolve_transformer_context(workspace_id, current_refs, QUANTITY_CURRENT, **shared),
    )
