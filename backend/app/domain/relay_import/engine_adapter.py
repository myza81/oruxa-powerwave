"""Canonical Distance Protection model -> existing distance engine input.

A one-way, read-only *view*: the canonical model is never mutated or
simplified, and anything the current engine cannot represent is reported as
an explicit `UnsupportedReason` rather than dropped or approximated.

The adapter knows only canonical engineering concepts and the current
engine's capability. It contains no relay-family knowledge (that lives in
relay profiles) and the engine knows nothing about this module.

Current engine capability (see DISTANCE_PROTECTION_ANALYSIS.md):
- any number of zones, in the model's order. Zone count is not a capability
  limit: every zone is adapted by the same rules, identified by its canonical
  zone id (never by its position), and each carries its own explicit direction,
  forward or reverse (the engine ties no zone to a direction);
- ONE characteristic for the whole analysis (mho or quadrilateral);
- phase-phase loops only; forward and reverse directional geometry only --
  non-directional, unknown or unresolved directions are refused;
- one delay per zone; one shared characteristic angle per polar zone. A quadrilateral
  zone may instead state explicit R/X limits (``GeometryMode.EXPLICIT_RX``): an X reach and
  a right and left resistive reach, with no angle. Polar and explicit zones coexist;
- zone ohms are compared directly against the impedance in the chosen
  basis, so the settings' primary/secondary basis must already match it.

Nothing is ever defaulted to make a conversion succeed. The one deliberate,
reported exception: a zone that is disabled/inactive needs no geometry, and
its unavailable delay is reported as 0.0 in a warning.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from enum import StrEnum

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    GEOMETRY_EXPLICIT_RX,
    ZoneSettings,
)
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicType,
    DistanceZone,
    GeometryMode,
    SettingBasis,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.provenance import UnresolvedCause

#: Canonical path of the setting basis (see `UnsupportedReason.paths`).
BASIS_PATH = "transformers.setting_basis"


def zone_path(zone: DistanceZone, field: str) -> str:
    """The `iter_sourced` path of a zone value, e.g. ``zones[Z1].status``."""
    return f"zones[{zone.zone_id}].{field}"

_ENGINE_CHARACTERISTIC = {
    CharacteristicType.MHO: CHARACTERISTIC_MHO,
    CharacteristicType.QUADRILATERAL: CHARACTERISTIC_QUADRILATERAL,
}


class UnsupportedCode(StrEnum):
    NO_ZONES = "no_zones"
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
    GEOMETRY_UNSUPPORTED = "geometry_unsupported"
    RESISTIVE_REACH_UNRESOLVED = "resistive_reach_unresolved"
    RESISTIVE_REACH_CONFLICT = "resistive_reach_conflict"
    TILT_UNSUPPORTED = "tilt_unsupported"
    TIMER_UNRESOLVED = "timer_unresolved"
    TIMER_CONFLICT = "timer_conflict"
    #: DEC-198: an enabled zone carries a setting that may change its operation and whose meaning is
    #: not verified (a raw zone setting the interpretation marks as material). Nothing in the review can clear it.
    UNVERIFIED_SETTING = "unverified_setting"
    #: DEC-198: an enabled zone carries a geometry-affecting setting whose configured cell is blank, so its
    #: effect on the zone is unknown (a source-data gap; e.g. a load-cutout resistance).
    SETTING_MISSING = "setting_missing"
    #: DEC-198: an enabled zone carries a stated geometry-affecting setting the engine cannot apply.
    SETTING_UNSUPPORTED = "setting_unsupported"
    #: DEC-198: the zone's delay is set to infinity -- documented relay behaviour: it picks up but never
    #: trips on its own timer. The engine has no zone that only picks up.
    DELAY_INFINITE = "delay_infinite"


@dataclass(frozen=True)
class UnsupportedReason:
    code: UnsupportedCode
    message: str
    zone_id: str | None = None
    #: Canonical value paths (as `CanonicalDistanceProtectionModel.iter_sourced`
    #: yields them) whose resolution would address this reason. Empty when no
    #: single value does (e.g. no zones, mixed characteristics). Lets a review
    #: tell which unresolved items block the engine, without parsing messages.
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineAdaptation:
    """`supported` is True only when `zones` and `characteristic` are a
    faithful engine input for the canonical model."""

    supported: bool
    characteristic: str | None = None
    #: One engine setting per canonical zone, in the model's order.
    zones: tuple[ZoneSettings, ...] | None = None
    #: The canonical zone_id of each entry of `zones` (same length, same order).
    zone_ids: tuple[str, ...] = ()
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

    def fail(
        code: UnsupportedCode, message: str, zone: DistanceZone | None = None, paths: tuple[str, ...] = ()
    ) -> None:
        reasons.append(UnsupportedReason(code, message, zone.zone_id if zone else None, paths))

    # --- model level ------------------------------------------------------
    if not model.zones:
        fail(UnsupportedCode.NO_ZONES, "The canonical model contains no zones.")
    basis = model.transformers.setting_basis
    if not basis.is_resolved or basis.value is SettingBasis.UNKNOWN:
        fail(
            UnsupportedCode.BASIS_UNRESOLVED,
            # DEC-198: a basis whose meaning for this relay's setting format is not verified is not a missing row
            "The primary/secondary basis of the impedance settings has not yet been verified for this relay; it is not inferred."
            if basis.provenance.cause is UnresolvedCause.UNVERIFIED
            else "The primary/secondary basis of the impedance settings is unknown; it is not inferred.",
            paths=(BASIS_PATH,),
        )
    elif basis.value.value != engine_basis:
        fail(
            UnsupportedCode.BASIS_MISMATCH,
            f"Settings are in {basis.value.value} ohms but the engine basis is {engine_basis!r}; "
            "no CT/VT conversion is performed here.",
            paths=(BASIS_PATH,),
        )
    slots = model.zones

    # --- characteristic: one for the whole analysis -------------------------
    considered = [z for z in slots if _status(z) is True] or list(slots)
    chars = {z.zone_id: z.characteristic.type for z in considered}
    unresolved_chars = [zid for zid, c in chars.items() if not c.is_resolved]
    for z in considered:
        c = z.characteristic.type
        if not c.is_resolved:
            fail(
                UnsupportedCode.CHARACTERISTIC_UNRESOLVED, "Characteristic type is unresolved.", z,
                (zone_path(z, "characteristic.type"),),
            )
        elif c.value not in _ENGINE_CHARACTERISTIC:
            fail(
                UnsupportedCode.CHARACTERISTIC_UNSUPPORTED,
                f"A {c.value.value} characteristic is preserved in the canonical model "
                "but is not supported by the current Distance Protection engine.",
                z,
                (zone_path(z, "characteristic.type"),),
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

    return EngineAdaptation(
        True,
        characteristic=_ENGINE_CHARACTERISTIC[characteristic_type],
        zones=tuple(built),
        zone_ids=tuple(z.zone_id for z in slots),
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


def zone_active(zone: DistanceZone) -> bool | None:
    """Whether the zone is in service: True enabled, False authoritatively disabled /
    inactive, None not established. A disabled zone's own settings are not required by
    the engine; an unknown state is itself a blocker."""
    return _status(zone)


def zone_direction(zone: DistanceZone) -> str | None:
    """The zone's direction when the model states a forward or reverse one, else None."""
    d = zone.direction
    if d.is_resolved and d.value is ZoneDirection.FORWARD:
        return DIRECTION_FORWARD
    if d.is_resolved and d.value is ZoneDirection.REVERSE:
        return DIRECTION_REVERSE
    return None


def _explicit_zero_tilt(zone: DistanceZone) -> bool:
    """A stated tilt of exactly 0 degrees on explicit R/X limits: "no inclination", which is
    exactly the horizontal X limit the engine draws, so it is a valid setting, not a refusal.
    Any other tilt stays refused, as does a zero tilt on a polar reach (there the engine's
    single angle already inclines the reactance line, so what a separate 0 is measured from
    is not established)."""
    v = zone.tilt_deg.value
    return (
        zone.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
        and isinstance(v, (int, float)) and not isinstance(v, bool)
        and v == 0.0  # NaN and infinities are never equal to 0
    )


def _adapt_zone(zone, ctype, allow_incomplete, fail, warn) -> ZoneSettings:
    status = _status(zone)
    if status is None:
        fail(
            UnsupportedCode.ZONE_STATUS_UNRESOLVED, "Zone enabled/disabled status is unresolved.", zone,
            (zone_path(zone, "status"), zone_path(zone, "direction")),
        )
        return ZoneSettings()

    delay = _delay(zone, status, fail, warn, allow_incomplete)

    if status is False:
        # No geometry is evaluated for a disabled/inactive zone; its
        # direction is carried only when it is a direction the engine knows.
        return ZoneSettings(enabled=False, delay_s=delay, direction=zone_direction(zone) or DIRECTION_FORWARD)

    # direction: the engine models forward and reverse directional geometry.
    # Non-directional, unknown and unresolved directions are refused, never
    # guessed.
    direction = zone_direction(zone)
    if direction is None:
        d = zone.direction
        shown = d.value.value if d.is_resolved else "unresolved"
        fail(
            UnsupportedCode.DIRECTION_UNSUPPORTED,
            f"Zone direction '{shown}' is not supported; the engine models forward and reverse directional zones only.",
            zone,
            (zone_path(zone, "direction"),),
        )
        direction = DIRECTION_FORWARD  # placeholder only; the adaptation fails
    # loop type: the engine evaluates phase-phase loops only.
    if not (zone.phase_phase_enabled.is_resolved and zone.phase_phase_enabled.value is True):
        fail(
            UnsupportedCode.LOOP_TYPE_UNSUPPORTED,
            "Phase-phase operation is not established for this zone; the engine evaluates "
            "phase-phase loops only (phase-earth characteristics are preserved but not drawable).",
            zone,
            (zone_path(zone, "phase_phase_enabled"),),
        )
    if zone.phase_earth_enabled.is_resolved and zone.phase_earth_enabled.value is True:
        warn(f"{zone.zone_id}: phase-earth operation is preserved in the model but not evaluated by the engine.")
    if zone.tilt_deg.is_resolved and not _explicit_zero_tilt(zone):
        fail(
            UnsupportedCode.TILT_UNSUPPORTED, "A separate tilt is not representable by the engine's single angle.", zone,
            (zone_path(zone, "tilt_deg"),),
        )
    if zone.earth_timer_s.is_resolved:
        warn(f"{zone.zone_id}: earth timer is preserved in the model but not used by the phase-phase engine.")
    if zone.compensation is not None:
        warn(f"{zone.zone_id}: residual compensation is preserved in the model but not used by the engine.")
    causes = {u.material_cause for u in zone.unresolved_settings if u.material}
    if "unverified" in causes:
        fail(
            UnsupportedCode.UNVERIFIED_SETTING,
            "A setting that may change this zone's operation has a meaning that is not yet verified.", zone,
        )
    if "missing" in causes:
        fail(
            UnsupportedCode.SETTING_MISSING,
            "A setting that can change this zone's boundary has no configured value in the source.", zone,
        )
    if "unsupported" in causes:
        fail(
            UnsupportedCode.SETTING_UNSUPPORTED,
            "A setting that changes this zone's boundary cannot yet be represented by the engine.", zone,
        )

    # DEC-198: one review gives the complete picture. Explicit R/X limits describe a quadrilateral, so
    # their reach and resistive limits are still checked while the characteristic is unresolved, and a
    # missing X limit does not hide a missing resistive limit. Nothing is returned for such a zone.
    explicit = zone.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
    if ctype is None and not explicit:
        return ZoneSettings()
    incomplete = ctype is None
    if explicit and ctype not in (None, CharacteristicType.QUADRILATERAL):
        fail(
            UnsupportedCode.GEOMETRY_UNSUPPORTED,
            "Explicit R/X limits describe a quadrilateral; they are not a mho reach and no reach is derived from them.",
            zone,
            (zone_path(zone, "characteristic.type"),),
        )
        return ZoneSettings()

    reach_ohm = None
    angle = None
    reach = zone.x_reach_ohm if explicit else zone.reach
    if explicit:
        # No polar reach exists: the X limit is the reach and there is no angle to carry.
        if reach.is_resolved:
            reach_ohm = reach.value
        elif not allow_incomplete:
            fail(
                UnsupportedCode.REACH_UNRESOLVED, "The Reactive Reach (X) is unresolved.", zone,
                (zone_path(zone, "x_reach_ohm"),),
            )
            incomplete = True
    elif reach.is_resolved:
        z = reach.value
        if not z.is_polar:
            fail(
                UnsupportedCode.REACH_REPRESENTATION,
                "Reach is given as R/X; the engine needs a magnitude and angle and no conversion is guessed.",
                zone,
                (zone_path(zone, "reach"),),
            )
            return ZoneSettings()
        reach_ohm, angle = z.magnitude_ohm, z.angle_deg
    elif not allow_incomplete:
        fail(UnsupportedCode.REACH_UNRESOLVED, "The zone reach is unresolved.", zone, (zone_path(zone, "reach"),))
        return ZoneSettings()

    angle_kw = {} if angle is None else {"characteristic_angle_deg": angle}  # absent only for blank manual reach
    if explicit:
        angle_kw = {"characteristic_angle_deg": None, "geometry_mode": GEOMETRY_EXPLICIT_RX}
    if ctype is CharacteristicType.MHO:
        return ZoneSettings(enabled=True, reach_ohm=reach_ohm, delay_s=delay, direction=direction, **angle_kw)

    forward = _forward_resistive(zone, fail)
    rr = zone.resistive_reach
    if forward is _CONFLICT:
        incomplete = True
    elif forward is None and not allow_incomplete:
        fail(
            UnsupportedCode.RESISTIVE_REACH_UNRESOLVED, "The Right Resistive Reach (+R) is unresolved.", zone,
            (zone_path(zone, "resistive_reach.phase_phase"), zone_path(zone, "resistive_reach.common")),
        )
        incomplete = True
    if not rr.reverse.is_resolved and not allow_incomplete:
        fail(
            UnsupportedCode.RESISTIVE_REACH_UNRESOLVED, "The Left Resistive Reach (−R) is unresolved.", zone,
            (zone_path(zone, "resistive_reach.reverse"),),
        )
        incomplete = True
    if incomplete:
        return ZoneSettings()
    return ZoneSettings(
        enabled=True,
        reactive_reach_ohm=reach_ohm,
        resistive_reach_forward_ohm=forward,
        resistive_reach_reverse_ohm=rr.reverse.value if rr.reverse.is_resolved else None,
        delay_s=delay,
        direction=direction,
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
            (zone_path(zone, "resistive_reach.phase_phase"), zone_path(zone, "resistive_reach.common")),
        )
        return _CONFLICT
    if pp.is_resolved:
        return pp.value
    if common.is_resolved:
        return common.value
    if pp.provenance.cause is UnresolvedCause.UNVERIFIED:
        # The source states a fault-resistance setting, but how it becomes the plotted boundary is not
        # established (DEC-198): say so, rather than that only a phase-earth value exists.
        fail(
            UnsupportedCode.RESISTIVE_REACH_UNRESOLVED,
            "A source fault-resistance setting is available, but its conversion to the plotted resistive "
            "boundary has not yet been verified.",
            zone,
            (zone_path(zone, "resistive_reach.phase_phase"), zone_path(zone, "resistive_reach.common")),
        )
        return _CONFLICT
    if (pp.provenance.cause is UnresolvedCause.UNSUPPORTED and pp.provenance.sources
            and any(ref.verified for ref in pp.provenance.references)):
        # The source states a fault-resistance setting and a verified reference documents the boundary it
        # forms, but the engine cannot draw that boundary exactly (DEC-198): an engine limitation, not a
        # semantic unknown, and not "only a phase-earth value".
        fail(
            UnsupportedCode.RESISTIVE_REACH_UNRESOLVED,
            "A source fault-resistance setting is available and its resistive boundary is documented, but the "
            "current engine cannot represent that boundary exactly.",
            zone,
            (zone_path(zone, "resistive_reach.phase_phase"), zone_path(zone, "resistive_reach.common")),
        )
        return _CONFLICT
    if rr.phase_earth.is_resolved:
        fail(
            UnsupportedCode.LOOP_TYPE_UNSUPPORTED,
            "Only a phase-earth resistive reach is available; the engine evaluates phase-phase loops only.",
            zone,
            (zone_path(zone, "resistive_reach.phase_phase"), zone_path(zone, "resistive_reach.common")),
        )
        return _CONFLICT
    return None


def _delay(zone: DistanceZone, status: bool, fail, warn, allow_incomplete: bool = False) -> float | None:
    """One delay: the common timer, else the phase timer (the engine is
    phase-phase, so that is the semantically matching one). Differing
    candidates are a conflict."""
    candidates = [t.value for t in (zone.common_timer_s, zone.phase_timer_s) if t.is_resolved]
    if any(math.isinf(c) for c in candidates if isinstance(c, (int, float))):
        # DEC-198: "infinity" is a configured value -- the zone picks up but never trips on its own timer.
        if status is False:
            warn(f"{zone.zone_id}: the delay is set to infinity (no timed trip); no delay is carried for a disabled zone.")
            return None
        fail(
            UnsupportedCode.DELAY_INFINITE,
            "The zone delay is set to infinity: the zone picks up but does not trip on its own timer. The "
            "current engine cannot represent a zone that only picks up.",
            zone,
            (zone_path(zone, "common_timer_s"), zone_path(zone, "phase_timer_s")),
        )
        return 0.0
    if len(set(candidates)) > 1:
        fail(
            UnsupportedCode.TIMER_CONFLICT, "Common and phase timers differ; which applies is not guessed.", zone,
            (zone_path(zone, "common_timer_s"), zone_path(zone, "phase_timer_s")),
        )
        return 0.0
    if candidates:
        return candidates[0]
    if allow_incomplete:
        # Manual form only: a delay that was never entered stays absent (None)
        # and the engine treats an enabled zone without one as not ready.
        return None
    if status is False:
        warn(f"{zone.zone_id}: no delay available for a disabled zone; reported as 0.0 s.")
    else:
        fail(
            UnsupportedCode.TIMER_UNRESOLVED, "The zone delay is unresolved.", zone,
            (zone_path(zone, "common_timer_s"), zone_path(zone, "phase_timer_s")),
        )
    return 0.0
