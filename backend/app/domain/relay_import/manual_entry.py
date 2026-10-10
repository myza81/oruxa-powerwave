"""Manual Distance Protection form -> canonical model -> engine input.

The manual form (and its API query parameters) is a set of four
`ZoneSettings` (three forward zones and the Reverse Zone slot), one
characteristic and one impedance basis. The canonical model itself is not
limited to four zones; four is only the manual presentation. This module maps
that shape into the OEM-neutral canonical model with `manual_entry`
provenance -- no document references, no relay profile -- so manual input
and relay-file import share one model and one engine adapter.

Manual semantics preserved exactly (they are the engine's own):
- the zone ohms are in the selected impedance basis (primary/secondary);
- zones are phase-phase only and carry their own direction (forward, or
  reverse for the fourth slot); the mho reach `|Z|` and the
  quadrilateral reactive reach are both distances along the zone's
  characteristic angle, so each is the polar reach `magnitude ∠ angle`;
- forward/reverse resistive reach map to phase-phase / reverse resistive;
- the single configured delay is the phase (phase-phase) timer.

Only the fields of the selected characteristic are carried (the engine reads
nothing else), so results are identical. Transitional boundary: the API still
receives flat form parameters and builds `ZoneSettings`; this module sits
directly behind that step.
"""

from __future__ import annotations

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    ZoneSettings,
)
from app.domain.impedance import IMPEDANCE_BASIS_PRIMARY, IMPEDANCE_BASIS_SECONDARY
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    DistanceZone,
    ImpedanceValue,
    InstrumentTransformers,
    RelayMetadata,
    ResistiveReach,
    SettingBasis,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.engine_adapter import EngineAdaptation, adapt_to_engine
from app.domain.relay_import.provenance import manual, manual_unresolved
from app.domain.relay_import.raw_document import SourceFormat

_BASIS = {IMPEDANCE_BASIS_PRIMARY: SettingBasis.PRIMARY, IMPEDANCE_BASIS_SECONDARY: SettingBasis.SECONDARY}
#: Unrecognised direction text becomes UNKNOWN so the adapter refuses it.
_DIRECTION = {DIRECTION_FORWARD: ZoneDirection.FORWARD, DIRECTION_REVERSE: ZoneDirection.REVERSE}
_TYPE = {
    CHARACTERISTIC_MHO: CharacteristicType.MHO,
    CHARACTERISTIC_QUADRILATERAL: CharacteristicType.QUADRILATERAL,
}


def _opt(value: float | None):
    return manual(value, raw_value=value) if value is not None else manual_unresolved()


def manual_to_canonical(
    *, characteristic: str, impedance_basis: str, zones: tuple[ZoneSettings, ...]
) -> CanonicalDistanceProtectionModel:
    """Never raises on odd form values: an unrecognised characteristic or
    basis becomes UNKNOWN / unresolved (raw text kept), so the adapter
    reports it rather than guessing."""
    ctype = _TYPE.get(characteristic)
    if ctype is not None:
        type_value = manual(ctype, raw_value=characteristic)
        char_spec = CharacteristicSpec(type=type_value)
    else:
        char_spec = CharacteristicSpec(
            type=manual(CharacteristicType.UNKNOWN, raw_value=characteristic),
            oem_description=str(characteristic),
        )
    basis = _BASIS.get(impedance_basis)
    setting_basis = manual(basis, raw_value=impedance_basis) if basis else manual_unresolved(impedance_basis)

    canonical_zones = []
    for index, z in enumerate(zones, start=1):
        angle = z.characteristic_angle_deg
        if ctype is CharacteristicType.MHO:
            reach_ohm = z.reach_ohm
            resistive = ResistiveReach()
        elif ctype is CharacteristicType.QUADRILATERAL:
            reach_ohm = z.reactive_reach_ohm
            resistive = ResistiveReach(
                phase_phase=_opt(z.resistive_reach_forward_ohm), reverse=_opt(z.resistive_reach_reverse_ohm)
            )
        else:
            reach_ohm, resistive = None, ResistiveReach()
        reach = (
            manual(ImpedanceValue(magnitude_ohm=reach_ohm, angle_deg=angle), raw_value=reach_ohm)
            if reach_ohm is not None
            else manual_unresolved()
        )
        canonical_zones.append(
            DistanceZone(
                zone_id=f"Z{index}",
                name=f"Zone {index}",
                status=manual(ZoneStatus.ENABLED if z.enabled else ZoneStatus.DISABLED, raw_value=z.enabled),
                direction=manual(_DIRECTION.get(z.direction, ZoneDirection.UNKNOWN), raw_value=z.direction),
                phase_phase_enabled=manual(True),
                phase_earth_enabled=manual(False),
                phase_timer_s=manual(z.delay_s, raw_value=z.delay_s),
                characteristic=char_spec,
                reach=reach,
                resistive_reach=resistive,
            )
        )
    return CanonicalDistanceProtectionModel(
        metadata=RelayMetadata(source_format=SourceFormat.OTHER),
        transformers=InstrumentTransformers(setting_basis=setting_basis),
        zones=tuple(canonical_zones),
        interpretation_notes=("manual entry",),
    )


def engine_zones_from_manual(
    *, characteristic: str, impedance_basis: str, zones: tuple[ZoneSettings, ...]
) -> tuple[ZoneSettings, ...]:
    """Route the manual zone settings through the canonical model and the
    engine adapter, returning the settings the engine should evaluate (same
    number of zones as supplied, so a three-zone caller gets three back).

    Blank fields stay absent (lenient adaptation). If the form carries a
    characteristic, basis or direction the model cannot represent (an
    unrecognised string), the original settings are passed through untouched
    -- exactly what happened before the canonical model existed -- so the
    downstream engine/service keeps reporting "not operated" / "needs
    configuration" as it always did.
    """
    model = manual_to_canonical(characteristic=characteristic, impedance_basis=impedance_basis, zones=zones)
    adaptation: EngineAdaptation = adapt_to_engine(model, engine_basis=impedance_basis, allow_incomplete_zones=True)
    return adaptation.zones[: len(zones)] if adaptation.supported else zones
