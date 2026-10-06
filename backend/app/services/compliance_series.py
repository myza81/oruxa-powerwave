"""Compliance -- reading one measurement series and putting it in the
Reference's unit (DEC-169). Shared by the readiness check
(`compliance_readiness_service`) and the trace builder
(`compliance_trace_service`), so "Ready" and "plotted" can never disagree.

Nothing here computes a new engineering quantity. It only READS an
already-existing shared array (a source channel that is already RMS, or an
ordinary Calculated Channel) and converts its unit through the existing
shared per-unit machinery:

- per-unit (`pu`): the SAME resolvers Waveform uses --
  `waveform_service._resolve_effective_per_unit` for a source channel,
  `calculated_channel_service._resolve_effective_per_unit_for_calculated_channel`
  for a calculated channel -- applied with `apply_per_unit_to_array`. A
  conversion that does not report `configured` is refused, never silently
  plotted in engineering units.
- `kV` / `V`: the channel's own unit, with the one exact V <-> kV scaling.
  Any other unit pairing is refused (no unit conversion is invented).

The Reference's unit is authoritative; it is never inferred from the data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import UNDEFINED
from app.domain.per_unit import STATUS_CONFIGURED, apply_per_unit_to_array
from app.domain.reference_profile import UNIT_KILOVOLT, UNIT_PER_UNIT, UNIT_VOLT
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import _resolve_effective_per_unit_for_calculated_channel
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.per_unit_service import voltage_channel_names_for_source
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.waveform_service import _analog_channel_engineering_type, _resolve_effective_per_unit
from app.services.workspace_registry import WorkspaceRegistry


@dataclass(slots=True)
class Registries:
    """The shared registries a series read needs -- bundled so the two
    callers pass one object."""

    source: WorkspaceRegistry
    calc: CalculatedChannelRegistry
    per_unit: PerUnitRegistry
    group: MeasurementGroupRegistry
    voltage_config: VoltageGroupConfigRegistry
    current_config: CurrentGroupConfigRegistry


@dataclass(slots=True)
class Series:
    time: np.ndarray            # the grounding source's own elapsed seconds
    values: np.ndarray          # already in the Reference's unit
    unit: str
    source_id: str              # the source whose time axis `time` is on
    name: str


#: Exact scalings between the two engineering voltage units.
_ENGINEERING_SCALE = {("V", "kV"): 1e-3, ("kV", "V"): 1e3, ("V", "V"): 1.0, ("kV", "kV"): 1.0}


def _normalise_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    text = unit.strip()
    return {"v": "V", "kv": "kV"}.get(text.lower(), text)


def _raw(ref: ChannelRef, *, workspace_id: str, reg: Registries):
    """`(time, values, unit, engineering_type, source_id, name, resolve)` of
    the shared array behind `ref`, or `None` when it no longer exists.
    `resolve()` returns the per-unit resolution for that array."""
    if ref.kind == "calculated":
        channel = reg.calc.get(workspace_id, ref.calculated_channel_id)
        if channel is None:
            return None
        profile_source = reg.per_unit.profile_for_calculated_channel(workspace_id, channel.id)
        profile = reg.per_unit.get(workspace_id, profile_source) if profile_source else None
        names = voltage_channel_names_for_source(reg.source, workspace_id, profile.source_id) if profile is not None else []

        def resolve():
            return _resolve_effective_per_unit_for_calculated_channel(
                channel, profile, names, workspace_id=workspace_id, calc_registry=reg.calc,
                group_registry=reg.group, voltage_config_registry=reg.voltage_config,
                current_config_registry=reg.current_config,
            )

        return channel.time, channel.values, channel.unit, channel.engineering_type, channel.reference_source_id, channel.name, resolve

    active = reg.source.get(workspace_id, ref.source_id)
    if active is None:
        return None
    data = active.record.waveform_data
    if ref.channel_name not in data.columns:
        return None
    meta = next((ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None)
    unit = meta.unit if meta is not None else None
    engineering_type = _analog_channel_engineering_type(active, ref.channel_name)
    profile = reg.per_unit.get(workspace_id, ref.source_id)

    def resolve():
        return _resolve_effective_per_unit(
            active, ref.channel_name, engineering_type, profile,
            [ch.name for ch in active.metadata.analog_channels if ch.engineering_type == "voltage"],
            workspace_id=workspace_id, group_registry=reg.group, voltage_config_registry=reg.voltage_config,
            current_config_registry=reg.current_config,
        )

    return (
        data["time"].to_numpy(), data[ref.channel_name].to_numpy(), unit, engineering_type, ref.source_id,
        ref.channel_name, resolve,
    )


def unit_problem(
    ref: ChannelRef, reference_unit: str, *, workspace_id: str, reg: Registries,
) -> str | None:
    """Why `ref` cannot be shown in `reference_unit`, or `None`. Cheap: no
    array is converted (a one-element probe checks the per-unit resolution),
    so the readiness check can call it without touching the data."""
    raw = _raw(ref, workspace_id=workspace_id, reg=reg)
    if raw is None:
        return "The measurement channel no longer exists."
    _, _, unit, engineering_type, _, name, resolve = raw
    return _convert_probe(np.asarray([1.0]), unit, engineering_type, reference_unit, name, resolve)[1]


def _convert_probe(values, unit, engineering_type, reference_unit, name, resolve):
    """`(converted values, problem)` -- the single conversion routine used
    for both the cheap probe and the real arrays."""
    if reference_unit == UNIT_PER_UNIT:
        resolution = resolve()
        converted, out_unit, status = apply_per_unit_to_array(values, unit, engineering_type or UNDEFINED, resolution)
        if status != STATUS_CONFIGURED or out_unit != "pu":
            reason = getattr(resolution, "reason", None)
            if reason == "group_not_confirmed":
                return None, (
                    "The Measurement Group's voltage base is set but the group has not been confirmed, so the shared "
                    "per-unit configuration is not applied yet. Open Configure Base and save to confirm it."
                )
            return None, (
                f"{name} cannot be shown in per-unit: the shared per-unit configuration does not apply to it "
                f"(status: {status or 'not configured'})."
            )
        return converted, None
    if reference_unit in (UNIT_KILOVOLT, UNIT_VOLT):
        factor = _ENGINEERING_SCALE.get((_normalise_unit(unit), reference_unit))
        if factor is None:
            return None, (
                f"{name} is in {unit or 'no unit'}, which cannot be shown in {reference_unit} "
                "(only V and kV are scaled; no other unit conversion exists)."
            )
        return values * factor, None
    return None, f"Unsupported Reference unit {reference_unit!r}."


def timebase_key(ref: ChannelRef, *, workspace_id: str, reg: Registries) -> tuple[str, int] | None:
    """`(grounding source id, sample count)` -- members that share this key
    sit on one time base and can be reduced sample-by-sample (minimum /
    maximum). Cheap; the trace builder re-proves it on the real arrays."""
    raw = _raw(ref, workspace_id=workspace_id, reg=reg)
    if raw is None:
        return None
    time, _, _, _, source_id, _, _ = raw
    return source_id, int(len(time))


def load_series(
    ref: ChannelRef, reference_unit: str, *, workspace_id: str, reg: Registries,
) -> tuple[Series | None, str | None]:
    """The full-resolution series behind `ref`, in the Reference's unit --
    or `(None, reason)`."""
    raw = _raw(ref, workspace_id=workspace_id, reg=reg)
    if raw is None:
        return None, "The measurement channel no longer exists."
    time, values, unit, engineering_type, source_id, name, resolve = raw
    converted, problem = _convert_probe(np.asarray(values, dtype=float), unit, engineering_type, reference_unit, name, resolve)
    if converted is None:
        return None, problem
    return Series(time=np.asarray(time), values=converted, unit=reference_unit, source_id=source_id, name=name), None
