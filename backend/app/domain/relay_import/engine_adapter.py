"""Canonical Distance Protection model -> existing distance engine input.

A one-way, read-only *view*: the canonical model is never mutated or
simplified, and anything the current engine cannot represent is reported as
an explicit `UnsupportedReason` rather than dropped or approximated.

The adapter knows only canonical engineering concepts and the current
engine's capability. It contains no relay-family knowledge (that lives in
relay profiles) and the engine knows nothing about this module.

Current engine capability (see DISTANCE_PROTECTION_ANALYSIS.md):
- exactly three zones, in order (zone1..zone3);
- ONE characteristic for the whole analysis (mho or quadrilateral);
- phase-phase loops only; forward geometry only (no direction concept);
- one delay per zone; one shared characteristic angle per zone;
- zone ohms are compared directly against the impedance in the chosen
  basis, so the settings' primary/secondary basis must already match it.

Nothing is ever defaulted to make a conversion succeed. The one deliberate,
reported exception: a zone that is disabled/inactive needs no geometry, and
its unavailable delay is reported as 0.0 in a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    ZoneSettings,
)
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicType,
    DistanceZone,
    SettingBasis,
    ZoneDirection,
    ZoneStatus,
)

#: The engine evaluates exactly this many zones.
ENGINE_ZONE_COUNT = 3

_ENGINE_CHARACTERISTIC = {
    CharacteristicType.MHO: CHARACTERISTIC_MHO,
    CharacteristicType.QUADRILATERAL: CHARACTERISTIC_QUADRILATERAL,
}


class UnsupportedCode(StrEnum):
    NO_ZONES = "no_zones"
    TOO_MANY_ZONES = "too_many_zones"
    BASIS_UNRESOLVED = "basis_unresolved"
    BASIS_MISMATCH = "basis_mismatch"
    CHARACTERISTIC_UNRESOLVED = "characteristic_unresolved"
    CHARACTERISTIC_UNSUPPORTED = "characteristic_unsupported"
    CHARACTERISTIC_MIXED = "characteristic_mixed"
    ZONE_STATUS_UNRESOLVED = "zone_status_unresolved"
    DIRECTION_UNSUPPORTED = "direction_unsupported"
    LOOP_TYPE_UNSUPPORTED = "loop_type_unsupported"
    REACH_UNRESOLVED = "reach_unresolved"
    REACH_REPRESENTATION = "reach_representation"
    RESISTIVE_REACH_UNRESOLVED = "resistive_reach_unresolved"
    RESISTIVE_REACH_CONFLICT = "resistive_reach_conflict"
    TILT_UNSUPPORTED = "tilt_unsupported"
    TIMER_UNRESOLVED = "timer_unresolved"
    TIMER_CONFLICT = "timer_conflict"


@dataclass(frozen=True)
class UnsupportedReason:
    code: UnsupportedCode
    message: str
    zone_id: str | None = None


@dataclass(frozen=True)
class EngineAdaptation:
    """`supported` is True only when `zones` and `characteristic` are a
    faithful engine input for the canonical model."""

    supported: bool
    characteristic: str | None = None
    zones: tuple[ZoneSettings, ZoneSettings, ZoneSettings] | None = None
    #: Canonical zone_id feeding each engine slot (None = unused slot).
    zone_ids: tuple[str | None, ...] = ()
    reasons: tuple[UnsupportedReason, ...] = ()
    #: Canonical information preserved in the model but not used by the
    #: engine (e.g. earth timer, compensation) -- informational only.
    warnings: tuple[str, ...] = ()


def adapt_to_engine(
    model: CanonicalDistanceProtectionModel,
    *,
    engine_basis: str,
    allow_incomplete_zones: bool = False,
) -> EngineAdaptation:
    """Adapt `model` to engine input.

    `engine_basis` is the impedance basis the engine will compare zone ohms
    in; the model must state the same basis (no hidden CT/VT conversion).

    `allow_incomplete_zones` is for the manual form only: a blank reach /
    resistive field is passed to the engine as absent (None), which the
    engine already treats as "Not Operated". Imports use the default
    (False), where a missing required value makes the result unsupported.
    """
    reasons: list[UnsupportedReason] = []
    warnings: list[str] = []

    def fail(code: UnsupportedCode, message: str, zone: DistanceZone | None = None) -> None:
        reasons.append(UnsupportedReason(code, message, zone.zone_id if zone else None))

    # --- model level ------------------------------------------------------
    if not model.zones:
        fail(UnsupportedCode.NO_ZONES, "The canonical model contains no zones.")
    basis = model.transformers.setting_basis
    if not basis.is_resolved or basis.value is SettingBasis.UNKNOWN:
        fail(
            UnsupportedCode.BASIS_UNRESOLVED,
            "The primary/secondary basis of the impedance settings is unknown; it is not inferred.",
        )
    elif basis.value.value != engine_basis:
        fail(
            UnsupportedCode.BASIS_MISMATCH,
            f"Settings are in {basis.value.value} ohms but the engine basis is {engine_basis!r}; "
            "no CT/VT conversion is performed here.",
        )
    extra_enabled = [z for z in model.zones[ENGINE_ZONE_COUNT:] if _status(z) is not False]
    if extra_enabled:
        fail(
            UnsupportedCode.TOO_MANY_ZONES,
            f"The engine evaluates {ENGINE_ZONE_COUNT} zones; "
            f"{', '.join(z.zone_id for z in extra_enabled)} cannot be represented.",
        )
    slots = model.zones[:ENGINE_ZONE_COUNT]

    # --- characteristic: one for the whole analysis -------------------------
    considered = [z for z in slots if _status(z) is True] or list(slots)
    chars = {z.zone_id: z.characteristic.type for z in considered}
    unresolved_chars = [zid for zid, c in chars.items() if not c.is_resolved]
    for z in considered:
        c = z.characteristic.type
        if not c.is_resolved:
            fail(UnsupportedCode.CHARACTERISTIC_UNRESOLVED, "Characteristic type is unresolved.", z)
        elif c.value not in _ENGINE_CHARACTERISTIC:
            fail(
                UnsupportedCode.CHARACTERISTIC_UNSUPPORTED,
                f"A {c.value.value} characteristic is preserved in the canonical model "
                "but is not supported by the current Distance Protection engine.",
                z,
            )
    resolved_types = {c.value for c in chars.values() if c.is_resolved and c.value in _ENGINE_CHARACTERISTIC}
    if len(resolved_types) > 1:
        fail(
            UnsupportedCode.CHARACTERISTIC_MIXED,
            "The engine applies one characteristic to all zones; the model mixes "
            + ", ".join(sorted(t.value for t in resolved_types)) + ".",
        )
    characteristic_type = next(iter(resolved_types)) if len(resolved_types) == 1 and not unresolved_chars else None

    # --- per zone -----------------------------------------------------------
    built: list[ZoneSettings] = []
    for zone in slots:
        built.append(_adapt_zone(zone, characteristic_type, allow_incomplete_zones, fail, warnings.append))

    if reasons:
        return EngineAdaptation(False, reasons=tuple(reasons), warnings=tuple(warnings))

    while len(built) < ENGINE_ZONE_COUNT:
        built.append(ZoneSettings())  # engine's own disabled default slot
    zone_ids = tuple(z.zone_id for z in slots) + (None,) * (ENGINE_ZONE_COUNT - len(slots))
    return EngineAdaptation(
        True,
        characteristic=_ENGINE_CHARACTERISTIC[characteristic_type],
        zones=(built[0], built[1], built[2]),
        zone_ids=zone_ids,
        warnings=tuple(warnings),
    )


def _status(zone: DistanceZone) -> bool | None:
    """True enabled, False disabled/inactive, None unresolved/unknown."""
    st = zone.status.value if zone.status.is_resolved else None
    if st is ZoneStatus.ENABLED:
        return True
    if st in (ZoneStatus.DISABLED, ZoneStatus.INACTIVE):
        return False
    if zone.direction.is_resolved and zone.direction.value is ZoneDirection.INACTIVE and st is None:
        return False
    return None


def _adapt_zone(zone, ctype, allow_incomplete, fail, warn) -> ZoneSettings:
    status = _status(zone)
    if status is None:
        fail(UnsupportedCode.ZONE_STATUS_UNRESOLVED, "Zone enabled/disabled status is unresolved.", zone)
        return ZoneSettings()

    delay = _delay(zone, status, fail, warn)

    if status is False:
        # No geometry is evaluated for a disabled/inactive zone.
        return ZoneSettings(enabled=False, delay_s=delay)

    # direction: the engine has only forward geometry.
    d = zone.direction
    if not d.is_resolved or d.value is not ZoneDirection.FORWARD:
        shown = d.value.value if d.is_resolved else "unresolved"
        fail(
            UnsupportedCode.DIRECTION_UNSUPPORTED,
            f"Zone direction '{shown}' is not supported; the engine models forward zones only.",
            zone,
        )
    # loop type: the engine evaluates phase-phase loops only.
    if not (zone.phase_phase_enabled.is_resolved and zone.phase_phase_enabled.value is True):
        fail(
            UnsupportedCode.LOOP_TYPE_UNSUPPORTED,
            "Phase-phase operation is not established for this zone; the engine evaluates "
            "phase-phase loops only (phase-earth characteristics are preserved but not drawable).",
            zone,
        )
    if zone.phase_earth_enabled.is_resolved and zone.phase_earth_enabled.value is True:
        warn(f"{zone.zone_id}: phase-earth operation is preserved in the model but not evaluated by the engine.")
    if zone.tilt_deg.is_resolved:
        fail(UnsupportedCode.TILT_UNSUPPORTED, "A separate tilt is not representable by the engine's single angle.", zone)
    if zone.earth_timer_s.is_resolved:
        warn(f"{zone.zone_id}: earth timer is preserved in the model but not used by the phase-phase engine.")
    if zone.compensation is not None:
        warn(f"{zone.zone_id}: residual compensation is preserved in the model but not used by the engine.")
    if ctype is None:
        return ZoneSettings()

    reach_ohm = None
    angle = None
    reach = zone.reach
    if reach.is_resolved:
        z = reach.value
        if not z.is_polar:
            fail(
                UnsupportedCode.REACH_REPRESENTATION,
                "Reach is given as R/X; the engine needs a magnitude and angle and no conversion is guessed.",
                zone,
            )
            return ZoneSettings()
        reach_ohm, angle = z.magnitude_ohm, z.angle_deg
    elif not allow_incomplete:
        fail(UnsupportedCode.REACH_UNRESOLVED, "The zone reach is unresolved.", zone)
        return ZoneSettings()

    angle_kw = {} if angle is None else {"characteristic_angle_deg": angle}  # absent only for blank manual reach
    if ctype is CharacteristicType.MHO:
        return ZoneSettings(enabled=True, reach_ohm=reach_ohm, delay_s=delay, **angle_kw)

    forward = _forward_resistive(zone, fail)
    if forward is _CONFLICT:
        return ZoneSettings()
    rr = zone.resistive_reach
    if forward is None and not allow_incomplete:
        fail(UnsupportedCode.RESISTIVE_REACH_UNRESOLVED, "The forward resistive reach is unresolved.", zone)
        return ZoneSettings()
    if not rr.reverse.is_resolved and not allow_incomplete:
        fail(UnsupportedCode.RESISTIVE_REACH_UNRESOLVED, "The reverse resistive reach is unresolved.", zone)
        return ZoneSettings()
    return ZoneSettings(
        enabled=True,
        reactive_reach_ohm=reach_ohm,
        resistive_reach_forward_ohm=forward,
        resistive_reach_reverse_ohm=rr.reverse.value if rr.reverse.is_resolved else None,
        delay_s=delay,
        **angle_kw,
    )


_CONFLICT = object()


def _forward_resistive(zone: DistanceZone, fail):
    """Phase-phase resistive reach for the (phase-phase) engine: the
    dedicated phase-phase value, else the common one; two different
    values are a conflict, phase-earth alone is not usable."""
    rr = zone.resistive_reach
    pp, common = rr.phase_phase, rr.common
    if pp.is_resolved and common.is_resolved and pp.value != common.value:
        fail(
            UnsupportedCode.RESISTIVE_REACH_CONFLICT,
            "Common and phase-phase resistive reaches differ; which applies is not guessed.",
            zone,
        )
        return _CONFLICT
    if pp.is_resolved:
        return pp.value
    if common.is_resolved:
        return common.value
    if rr.phase_earth.is_resolved:
        fail(
            UnsupportedCode.LOOP_TYPE_UNSUPPORTED,
            "Only a phase-earth resistive reach is available; the engine evaluates phase-phase loops only.",
            zone,
        )
        return _CONFLICT
    return None


def _delay(zone: DistanceZone, status: bool, fail, warn) -> float:
    """One delay: the common timer, else the phase timer (the engine is
    phase-phase, so that is the semantically matching one). Differing
    candidates are a conflict."""
    candidates = [t.value for t in (zone.common_timer_s, zone.phase_timer_s) if t.is_resolved]
    if len(set(candidates)) > 1:
        fail(UnsupportedCode.TIMER_CONFLICT, "Common and phase timers differ; which applies is not guessed.", zone)
        return 0.0
    if candidates:
        return candidates[0]
    if status is False:
        warn(f"{zone.zone_id}: no delay available for a disabled zone; reported as 0.0 s.")
    else:
        fail(UnsupportedCode.TIMER_UNRESOLVED, "The zone delay is unresolved.", zone)
    return 0.0
