"""Apply Settings (Slice 9): the reviewed canonical model -> what the existing
Distance Protection form can hold.

This is a *translation*, not a second model and not a second calculation: the
engine adapter has already turned the effective reviewed model into the engine's
four `ZoneSettings`; this module only reshapes those into the form's fields and
states the extra limits of the form itself.

The manual analysis form represents exactly four slots: Zone 1, Zone 2, Zone 3
(forward) and the Reverse Zone (its direction is fixed to reverse). The canonical
model may carry any number of zones, so

* a zone that is **disabled** is preserved in the model and simply not applied;
* an **enabled** zone the form cannot show (a fifth zone such as Zone P, or a zone
  whose direction contradicts its slot) makes the model *not representable* -- it
  is reported as an `UnsupportedReason` so readiness blocks Apply. It is never
  dropped and never moved into another slot.

Nothing here knows a relay family; nothing here persists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.distance_protection import CHARACTERISTIC_MHO, DIRECTION_FORWARD, DIRECTION_REVERSE
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.engine_adapter import (
    ENGINE_ZONE_COUNT,
    EngineAdaptation,
    UnsupportedCode,
    UnsupportedReason,
    zone_active,
    zone_path,
)

__all__ = [
    "APPLY_SLOTS",
    "ApplyPlan",
    "ApplyRejectedError",
    "ApplyZone",
    "build_apply_plan",
    "form_slot_reasons",
]

#: The form's slots in order: (form key, canonical zone id it shows, direction it is fixed to).
APPLY_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("zone1", "Z1", DIRECTION_FORWARD),
    ("zone2", "Z2", DIRECTION_FORWARD),
    ("zone3", "Z3", DIRECTION_FORWARD),
    ("zone4", "Z4", DIRECTION_REVERSE),
)
_SLOT_NAMES = {"zone1": "Zone 1", "zone2": "Zone 2", "zone3": "Zone 3", "zone4": "the Reverse Zone"}


class ApplyRejectedError(ValueError):
    """The effective model cannot be applied to the form. The message is a fixed
    domain phrase and is safe to show."""


@dataclass(frozen=True)
class ApplyZone:
    """One form slot. ``None`` = not configured; nothing is defaulted or invented."""

    slot: str
    #: The canonical zone shown in this slot (``None`` for an unused slot).
    zone_id: str | None
    enabled: bool
    direction: str
    delay_s: float | None
    characteristic_angle_deg: float | None
    reach_ohm: float | None
    reactive_reach_ohm: float | None
    resistive_reach_forward_ohm: float | None
    resistive_reach_reverse_ohm: float | None


@dataclass(frozen=True)
class ApplyPlan:
    characteristic: str
    impedance_basis: str
    zones: tuple[ApplyZone, ApplyZone, ApplyZone, ApplyZone]


def form_slot_reasons(model: CanonicalDistanceProtectionModel) -> tuple[UnsupportedReason, ...]:
    """Why the form cannot show the model's *active* zones in its four slots.

    Only a zone that is in service matters. The slot is chosen by canonical zone id,
    so a fifth/extra zone is never remapped into the Reverse Zone merely because a
    slot exists, and an engine-compatible zone whose direction contradicts its fixed
    slot direction is refused rather than flipped."""
    reasons: list[UnsupportedReason] = []
    for index, zone in enumerate(model.zones[:ENGINE_ZONE_COUNT]):
        if zone_active(zone) is not True:
            continue
        key, expected_id, expected_direction = APPLY_SLOTS[index]
        if zone.zone_id != expected_id:
            reasons.append(
                UnsupportedReason(
                    UnsupportedCode.ZONE_SLOT_UNSUPPORTED,
                    f"The Distance Protection form shows Zone 1, Zone 2, Zone 3 and the Reverse Zone; "
                    f"{zone.zone_id} cannot be shown as {_SLOT_NAMES[key]}.",
                    zone.zone_id,
                    (zone_path(zone, "status"),),
                )
            )
            continue
        if zone.direction.is_resolved and zone.direction.value.value in ("forward", "reverse"):
            direction = DIRECTION_FORWARD if zone.direction.value.value == "forward" else DIRECTION_REVERSE
            if direction != expected_direction:
                reasons.append(
                    UnsupportedReason(
                        UnsupportedCode.ZONE_SLOT_UNSUPPORTED,
                        f"{zone.zone_id} faces {direction}, but {_SLOT_NAMES[key]} in the form is fixed to "
                        f"{expected_direction}.",
                        zone.zone_id,
                        (zone_path(zone, "direction"),),
                    )
                )
    return tuple(reasons)


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
    """The form's values for an effective reviewed model the adapter accepted.

    Raises `ApplyRejectedError` (and returns nothing -- never a partial plan) if the
    adaptation is not supported, the form cannot show an active zone, or a value is
    not a valid finite protection value."""
    if not adaptation.supported or adaptation.zones is None or adaptation.characteristic is None:
        raise ApplyRejectedError("The reviewed settings cannot be represented by the Distance Protection analysis.")
    if form_slot_reasons(model):
        raise ApplyRejectedError("An active zone cannot be shown in the Distance Protection form.")
    mho = adaptation.characteristic == CHARACTERISTIC_MHO
    zones: list[ApplyZone] = []
    for (key, _, slot_direction), settings, zone_id in zip(APPLY_SLOTS, adaptation.zones, adaptation.zone_ids):
        zone = model.zone(zone_id) if zone_id is not None else None
        if not settings.enabled:
            # Preserved in the canonical model, not applied: no geometry and nothing
            # fabricated. A delay is carried only when the source actually states one.
            stated = zone is not None and any(
                t.is_resolved for t in (zone.common_timer_s, zone.phase_timer_s)
            )
            zones.append(
                ApplyZone(
                    key, zone_id, False, slot_direction,
                    _finite(settings.delay_s, "delay") if stated else None,
                    None, None, None, None, None,
                )
            )
            continue
        zones.append(
            ApplyZone(
                key,
                zone_id,
                True,
                slot_direction,
                _finite(settings.delay_s, "delay"),
                _finite(settings.characteristic_angle_deg, "angle", non_negative=False),
                _finite(settings.reach_ohm, "reach") if mho else None,
                None if mho else _finite(settings.reactive_reach_ohm, "reach"),
                None if mho else _finite(settings.resistive_reach_forward_ohm, "right resistive reach"),
                None if mho else _finite(settings.resistive_reach_reverse_ohm, "left resistive reach"),
            )
        )
    return ApplyPlan(adaptation.characteristic, impedance_basis, (zones[0], zones[1], zones[2], zones[3]))
