"""Apply Settings: the reviewed canonical model -> the zone collection the
Distance Protection analysis evaluates.

This is a *translation*, not a second model and not a second calculation: the
engine adapter has already turned the effective reviewed model into one engine
`ZoneSettings` per canonical zone; this module only reshapes those into a list of
zone DTOs, each under its canonical zone id.

Slice 10 removed the fixed four-slot assumption of Slice 9. The plan carries **every**
zone of the model, in order, identified by its stable canonical id and display name --
never by position, never truncated, never remapped into another zone's place:

* an **enabled** zone is applied with the geometry its characteristic needs;
* a **disabled** zone is preserved in the plan (``enabled=False``, no geometry, nothing
  fabricated) so the collection is complete; the analysis simply does not plot it.

Whether a model can be applied at all is decided only by the engine adapter (supported
characteristic, direction, geometry, timers, loop semantics) -- the number of zones plays
no part. Nothing here knows a relay family; nothing here persists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.distance_protection import CHARACTERISTIC_MHO, GEOMETRY_POLAR
from app.domain.relay_import.approximation import ApproximationRecord
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.engine_adapter import EngineAdaptation, zone_direction

__all__ = ["ApplyApproximation", "ApplyPlan", "ApplyRejectedError", "ApplyZone", "build_apply_plan", "model_approximations"]


class ApplyRejectedError(ValueError):
    """The effective model cannot be applied. The message is a fixed domain phrase
    and is safe to show."""


@dataclass(frozen=True)
class ApplyZone:
    """One zone of the applied collection. ``None`` = not configured; nothing is
    defaulted or invented."""

    #: The stable canonical zone id (e.g. ``Z1``, ``ZP``). The identity of the zone.
    zone_id: str
    #: The label to show: the source's own name for the zone, else its id.
    display_name: str
    enabled: bool
    #: ``forward`` / ``reverse``. ``None`` only for a *disabled* zone whose direction the
    #: source does not state (an enabled zone's direction is always known).
    direction: str | None
    delay_s: float | None
    characteristic_angle_deg: float | None
    reach_ohm: float | None
    reactive_reach_ohm: float | None
    resistive_reach_forward_ohm: float | None
    resistive_reach_reverse_ohm: float | None
    #: ``polar`` (reach at an angle) or ``explicit_rx`` (X and resistive limits, no angle).
    #: An explicit zone carries ``characteristic_angle_deg = None`` and its X in
    #: ``reactive_reach_ohm``; it is never converted to a polar reach.
    geometry_mode: str = GEOMETRY_POLAR


@dataclass(frozen=True)
class ApplyApproximation:
    """DEC-198: one engine approximation in the applied configuration (relay-neutral rule data only;
    nothing from the document)."""

    rule_id: str
    rule_version: str
    field: str
    classification: str
    description: str
    envelope: str | None = None
    zone_id: str | None = None


@dataclass(frozen=True)
class ApplyPlan:
    characteristic: str
    impedance_basis: str
    zones: tuple[ApplyZone, ...]
    #: DEC-198: the engine approximations the applied configuration contains (empty = exact).
    approximations: tuple[ApplyApproximation, ...] = ()


def model_approximations(model: CanonicalDistanceProtectionModel) -> tuple[ApproximationRecord, ...]:
    """Every approximation record carried by the model's values, in model order."""
    return tuple(
        sourced.provenance.approximation for _, sourced in model.iter_sourced()
        if sourced.provenance.approximation is not None
    )


def _finite(value: float | None, name: str, *, non_negative: bool = True) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ApplyRejectedError(f"A protection value ({name}) is not a finite number.")
    if non_negative and value < 0:
        raise ApplyRejectedError(f"A protection value ({name}) is negative.")
    return float(value)


def build_apply_plan(
    model: CanonicalDistanceProtectionModel, adaptation: EngineAdaptation, *, impedance_basis: str
) -> ApplyPlan:
    """The zone collection for an effective reviewed model the adapter accepted.

    Raises `ApplyRejectedError` (and returns nothing -- never a partial plan) if the
    adaptation is not supported or a value is not a valid finite protection value."""
    if not adaptation.supported or adaptation.zones is None or adaptation.characteristic is None:
        raise ApplyRejectedError("The reviewed settings cannot be represented by the Distance Protection analysis.")
    if len(adaptation.zones) != len(adaptation.zone_ids):
        raise ApplyRejectedError("The reviewed settings cannot be represented by the Distance Protection analysis.")
    mho = adaptation.characteristic == CHARACTERISTIC_MHO
    zones: list[ApplyZone] = []
    for settings, zone_id in zip(adaptation.zones, adaptation.zone_ids):
        zone = model.zone(zone_id)
        if zone is None:
            raise ApplyRejectedError("The reviewed settings cannot be represented by the Distance Protection analysis.")
        name = zone.name or zone.zone_id
        if not settings.enabled:
            # Preserved in the canonical model, not applied: no geometry and nothing
            # fabricated. A delay is carried only when the source actually states one.
            stated = any(t.is_resolved for t in (zone.common_timer_s, zone.phase_timer_s))
            zones.append(
                ApplyZone(
                    zone_id, name, False, zone_direction(zone),
                    _finite(settings.delay_s, "delay") if stated else None,
                    None, None, None, None, None,
                )
            )
            continue
        zones.append(
            ApplyZone(
                zone_id,
                name,
                True,
                settings.direction,
                _finite(settings.delay_s, "delay"),
                _finite(settings.characteristic_angle_deg, "angle", non_negative=False),
                _finite(settings.reach_ohm, "reach") if mho else None,
                None if mho else _finite(settings.reactive_reach_ohm, "reach"),
                None if mho else _finite(settings.resistive_reach_forward_ohm, "right resistive reach"),
                None if mho else _finite(settings.resistive_reach_reverse_ohm, "left resistive reach"),
                settings.geometry_mode,
            )
        )
    approximations = tuple(
        ApplyApproximation(
            r.rule_id, r.rule_version, r.field, r.classification.value, r.description,
            r.envelope.description if r.envelope else None, r.zone_id,
        )
        for r in model_approximations(model)
    )
    return ApplyPlan(adaptation.characteristic, impedance_basis, tuple(zones), approximations)
