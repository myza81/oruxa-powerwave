"""Slice 2: canonical model <-> existing Distance Protection engine.

Proves (1) the manual form routed through the canonical model + adapter gives
engine results identical to the legacy direct path, (2) canonical data the
engine cannot represent is refused explicitly without guessing or mutation,
and (3) the engine/adapter boundary stays free of relay-specific logic.
"""

from __future__ import annotations

import copy
import math
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.domain.distance_protection import (
    DEFAULT_ZONE4,
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    ZoneSettings,
    evaluate_manual_distance,
    evaluate_zone_state,
)
from app.domain.impedance import IMPEDANCE_BASIS_PRIMARY, IMPEDANCE_BASIS_SECONDARY, ImpedancePoint
from app.domain.phasor import ManualPhasorRoleInput
from app.domain.relay_import import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ImpedanceValue,
    InstrumentTransformers,
    MappingStatus,
    ProvenanceOrigin,
    RelayMetadata,
    ResidualCompensation,
    ResistiveReach,
    SettingBasis,
    SourceFormat,
    SourceRef,
    ZoneDirection,
    ZoneStatus,
    mapped,
    unresolved,
)
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.manual_entry import engine_zones_from_manual, manual_to_canonical

SEC = IMPEDANCE_BASIS_SECONDARY
PRI = IMPEDANCE_BASIS_PRIMARY
REF = (SourceRef("s1"),)


def m(value):
    return mapped(value, sources=REF, profile_id="t", profile_version="0")


def point(r, x):
    return ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r)))


GRID = [point(r, x) for r in (-30, -10, -2, 0, 1, 3, 5, 8, 12, 25) for x in (-20, -4, 0, 0.5, 2, 4, 6, 9, 15, 40)]

QUAD_ZONES = (
    ZoneSettings(True, None, 5.0, 4.0, 2.0, 80.0, 0.0),
    ZoneSettings(True, None, 10.0, 8.0, 3.0, 80.0, 0.4),
    ZoneSettings(False, None, 15.0, 12.0, 4.0, 75.0, 1.0),
)
MHO_ZONES = (
    ZoneSettings(True, 6.0, None, None, None, 75.0, 0.0),
    ZoneSettings(True, 12.0, None, None, None, 75.0, 0.4),
    ZoneSettings(True, 20.0, None, None, None, 70.0, 1.0),
)


def states(characteristic, zones):
    return [[evaluate_zone_state(p, characteristic=characteristic, zone=z) for p in GRID] for z in zones]


# --- equivalence ----------------------------------------------------------


class TestManualEquivalence:
    @pytest.mark.parametrize("characteristic,zones", [(CHARACTERISTIC_QUADRILATERAL, QUAD_ZONES), (CHARACTERISTIC_MHO, MHO_ZONES)])
    @pytest.mark.parametrize("basis", [SEC, PRI])
    def test_zone_state_grid_identical(self, characteristic, zones, basis):
        routed = engine_zones_from_manual(characteristic=characteristic, impedance_basis=basis, zones=zones)
        assert states(characteristic, routed) == states(characteristic, zones)

    def test_supported_fields_round_trip_exactly(self):
        routed = engine_zones_from_manual(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=QUAD_ZONES)
        for before, after in zip(QUAD_ZONES[:2], routed[:2]):
            assert after == before  # enabled, reactive, fwd, rev, angle, delay bit-identical
        assert routed[2].enabled is False and routed[2].delay_s == 1.0
        routed = engine_zones_from_manual(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=MHO_ZONES)
        assert routed == MHO_ZONES

    @pytest.mark.parametrize("characteristic,zones", [(CHARACTERISTIC_QUADRILATERAL, QUAD_ZONES), (CHARACTERISTIC_MHO, MHO_ZONES)])
    def test_full_manual_distance_result_identical(self, characteristic, zones):
        def run(z):
            ins = [
                ManualPhasorRoleInput(True, 63.5, "V", 0.0), ManualPhasorRoleInput(True, 63.5, "V", -120.0),
                ManualPhasorRoleInput(True, 10.0, "A", -75.0), ManualPhasorRoleInput(True, 10.0, "A", 165.0),
            ]
            return evaluate_manual_distance(
                *ins, loop_label="AB", voltage_basis=SEC, vt_primary=None, vt_secondary=None,
                current_basis=SEC, ct_primary=None, ct_secondary=None, impedance_basis=SEC,
                characteristic=characteristic, zone1=z[0], zone2=z[1], zone3=z[2],
            )

        routed = engine_zones_from_manual(characteristic=characteristic, impedance_basis=SEC, zones=zones)
        assert run(routed) == run(zones)

    def test_disabled_zone_stays_disabled_and_keeps_reported_delay(self):
        routed = engine_zones_from_manual(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=QUAD_ZONES)
        assert routed[2].enabled is False and routed[2].delay_s == 1.0
        assert all(s == "not_operated" for s in states(CHARACTERISTIC_QUADRILATERAL, routed)[2])

    def test_randomised_forms_incl_blank_and_garbage_values_match_legacy(self):
        rng = random.Random(20261010)

        def pick(*opts):
            return rng.choice(opts)

        for _ in range(400):
            characteristic = pick(CHARACTERISTIC_MHO, CHARACTERISTIC_QUADRILATERAL, CHARACTERISTIC_MHO, CHARACTERISTIC_QUADRILATERAL, "weird", "")
            basis = pick(SEC, PRI, SEC, PRI, "weird")
            zones = tuple(
                ZoneSettings(
                    enabled=pick(True, False),
                    reach_ohm=pick(None, rng.uniform(-2, 30), 0.0),
                    reactive_reach_ohm=pick(None, rng.uniform(-2, 30)),
                    resistive_reach_forward_ohm=pick(None, rng.uniform(-2, 30)),
                    resistive_reach_reverse_ohm=pick(None, rng.uniform(-2, 30)),
                    characteristic_angle_deg=pick(90.0, rng.uniform(-180, 180)),
                    delay_s=pick(0.0, rng.uniform(0, 3)),
                )
                for _ in range(3)
            )
            routed = engine_zones_from_manual(characteristic=characteristic, impedance_basis=basis, zones=zones)
            assert states(characteristic, routed) == states(characteristic, zones)
            assert [(z.enabled, z.delay_s) for z in routed] == [(z.enabled, z.delay_s) for z in zones]

    def test_unrecognised_characteristic_or_basis_passes_through_unchanged(self):
        assert engine_zones_from_manual(characteristic="weird", impedance_basis=SEC, zones=MHO_ZONES) == MHO_ZONES
        assert engine_zones_from_manual(characteristic=CHARACTERISTIC_MHO, impedance_basis="weird", zones=MHO_ZONES) == MHO_ZONES


class TestManualProvenance:
    def test_manual_values_are_manual_origin_mapped_without_document_refs(self):
        model = manual_to_canonical(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=QUAD_ZONES)
        resolved = [s for _, s in model.iter_sourced() if s.is_resolved]
        assert resolved
        for s in resolved:
            assert s.provenance.origin is ProvenanceOrigin.MANUAL_ENTRY
            assert s.provenance.status is MappingStatus.MAPPED
            assert s.provenance.sources == () and s.provenance.profile_id is None
        assert model.metadata.profile_id is None

    def test_blank_manual_field_is_unresolved_not_defaulted(self):
        zones = (ZoneSettings(True, 6.0, None, None, None, 75.0, 0.0),) * 3
        model = manual_to_canonical(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=zones)
        assert not model.zones[0].reach.is_resolved
        assert not model.zones[0].resistive_reach.phase_phase.is_resolved

    def test_manual_zone_is_forward_phase_phase_only(self):
        z = manual_to_canonical(characteristic=CHARACTERISTIC_MHO, impedance_basis=SEC, zones=MHO_ZONES).zones[0]
        assert z.direction.value is ZoneDirection.FORWARD
        assert z.phase_phase_enabled.value is True and z.phase_earth_enabled.value is False
        assert z.reach.value.magnitude_ohm == 6.0 and z.reach.value.angle_deg == 75.0


# --- canonical import-style models through the adapter ---------------------


def import_zone(zone_id="Z1", *, char=CharacteristicType.QUADRILATERAL, **kw) -> DistanceZone:
    base = dict(
        zone_id=zone_id,
        status=m(ZoneStatus.ENABLED),
        direction=m(ZoneDirection.FORWARD),
        phase_phase_enabled=m(True),
        phase_timer_s=m(0.15),
        characteristic=CharacteristicSpec(type=m(char)),
        reach=m(ImpedanceValue(magnitude_ohm=6.0, angle_deg=80.0)),
        resistive_reach=ResistiveReach(phase_phase=m(4.0), reverse=m(2.0)),
    )
    base.update(kw)
    return DistanceZone(**base)


def model_of(*zones, basis=SettingBasis.SECONDARY) -> CanonicalDistanceProtectionModel:
    return CanonicalDistanceProtectionModel(
        RelayMetadata(SourceFormat.PDF),
        transformers=InstrumentTransformers(setting_basis=m(basis) if basis else unresolved()),
        zones=zones,
    )


def codes(adaptation):
    return {r.code for r in adaptation.reasons}


class TestSupportedImport:
    def test_supported_quadrilateral_import(self):
        a = adapt_to_engine(model_of(import_zone("Z1"), import_zone("Z2")), engine_basis=SEC)
        assert a.supported and a.characteristic == CHARACTERISTIC_QUADRILATERAL
        assert a.zones[0] == ZoneSettings(True, None, 6.0, 4.0, 2.0, 80.0, 0.15)
        assert a.zones[2] == ZoneSettings()  # unused slot
        assert a.zones[3] == DEFAULT_ZONE4  # unused fourth slot: disabled, reverse-facing
        assert a.zone_ids == ("Z1", "Z2", None, None)

    def test_supported_mho_import(self):
        z = import_zone(char=CharacteristicType.MHO)
        a = adapt_to_engine(model_of(z), engine_basis=SEC)
        assert a.supported and a.characteristic == CHARACTERISTIC_MHO
        assert a.zones[0].reach_ohm == 6.0 and a.zones[0].characteristic_angle_deg == 80.0

    def test_extra_disabled_zones_are_allowed_and_enabled_extras_refused(self):
        zs = [import_zone(f"Z{i}") for i in range(1, 5)]
        off = import_zone("Z5", status=m(ZoneStatus.INACTIVE), direction=m(ZoneDirection.INACTIVE))
        assert adapt_to_engine(model_of(*zs, off), engine_basis=SEC).supported
        a = adapt_to_engine(model_of(*zs, import_zone("Z5")), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.TOO_MANY_ZONES in codes(a)

    def test_earth_only_data_is_preserved_and_reported_not_used(self):
        z = import_zone(
            phase_earth_enabled=m(True),
            earth_timer_s=m(0.30),
            compensation=ResidualCompensation(CompensationKind.K0_MAGNITUDE_ANGLE, k0_magnitude=m(0.7), k0_angle_deg=m(-5.0)),
        )
        a = adapt_to_engine(model_of(z), engine_basis=SEC)
        assert a.supported and a.zones[0].delay_s == 0.15
        assert any("earth timer" in w for w in a.warnings) and any("compensation" in w for w in a.warnings)


class TestUnsupportedFailsSafe:
    @pytest.mark.parametrize("ctype", [CharacteristicType.LENTICULAR, CharacteristicType.POLYGON_CUSTOM, CharacteristicType.UNKNOWN])
    def test_unsupported_geometry(self, ctype):
        a = adapt_to_engine(model_of(import_zone(char=ctype)), engine_basis=SEC)
        assert not a.supported and a.zones is None and a.characteristic is None
        assert UnsupportedCode.CHARACTERISTIC_UNSUPPORTED in codes(a)
        assert "not supported by the current Distance Protection engine" in a.reasons[0].message

    def test_unresolved_characteristic(self):
        a = adapt_to_engine(model_of(import_zone(characteristic=CharacteristicSpec())), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.CHARACTERISTIC_UNRESOLVED in codes(a)

    def test_mixed_characteristics(self):
        a = adapt_to_engine(model_of(import_zone("Z1"), import_zone("Z2", char=CharacteristicType.MHO)), engine_basis=SEC)
        assert UnsupportedCode.CHARACTERISTIC_MIXED in codes(a)

    def test_phase_earth_only_zone(self):
        z = import_zone(phase_phase_enabled=m(False), phase_earth_enabled=m(True))
        a = adapt_to_engine(model_of(z), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.LOOP_TYPE_UNSUPPORTED in codes(a)

    def test_phase_earth_only_resistive_reach(self):
        z = import_zone(resistive_reach=ResistiveReach(phase_earth=m(9.0), reverse=m(2.0)))
        a = adapt_to_engine(model_of(z), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.LOOP_TYPE_UNSUPPORTED in codes(a)

    def test_unresolved_phase_phase_operation_is_not_assumed(self):
        a = adapt_to_engine(model_of(import_zone(phase_phase_enabled=unresolved())), engine_basis=SEC)
        assert UnsupportedCode.LOOP_TYPE_UNSUPPORTED in codes(a)

    @pytest.mark.parametrize("direction", [ZoneDirection.NON_DIRECTIONAL, ZoneDirection.UNKNOWN])
    def test_non_directional_or_unknown_direction(self, direction):
        a = adapt_to_engine(model_of(import_zone(direction=m(direction))), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.DIRECTION_UNSUPPORTED in codes(a)

    def test_unresolved_reach(self):
        a = adapt_to_engine(model_of(import_zone(reach=unresolved("n/a"))), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.REACH_UNRESOLVED in codes(a)

    def test_rectangular_reach_is_not_converted_by_guess(self):
        a = adapt_to_engine(model_of(import_zone(reach=m(ImpedanceValue(r_ohm=1.0, x_ohm=6.0)))), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.REACH_REPRESENTATION in codes(a)

    def test_unresolved_resistive_reach(self):
        a = adapt_to_engine(model_of(import_zone(resistive_reach=ResistiveReach(reverse=m(2.0)))), engine_basis=SEC)
        assert UnsupportedCode.RESISTIVE_REACH_UNRESOLVED in codes(a)

    def test_conflicting_resistive_reach(self):
        z = import_zone(resistive_reach=ResistiveReach(common=m(3.0), phase_phase=m(4.0), reverse=m(2.0)))
        assert UnsupportedCode.RESISTIVE_REACH_CONFLICT in codes(adapt_to_engine(model_of(z), engine_basis=SEC))

    def test_conflicting_or_missing_timers(self):
        z = import_zone(common_timer_s=m(0.5))
        assert UnsupportedCode.TIMER_CONFLICT in codes(adapt_to_engine(model_of(z), engine_basis=SEC))
        z = import_zone(phase_timer_s=unresolved())
        assert UnsupportedCode.TIMER_UNRESOLVED in codes(adapt_to_engine(model_of(z), engine_basis=SEC))

    def test_separate_tilt_not_representable(self):
        a = adapt_to_engine(model_of(import_zone(tilt_deg=m(-3.0))), engine_basis=SEC)
        assert UnsupportedCode.TILT_UNSUPPORTED in codes(a)

    def test_unresolved_zone_status(self):
        a = adapt_to_engine(model_of(import_zone(status=unresolved())), engine_basis=SEC)
        assert UnsupportedCode.ZONE_STATUS_UNRESOLVED in codes(a)

    def test_no_zones(self):
        assert UnsupportedCode.NO_ZONES in codes(adapt_to_engine(model_of(), engine_basis=SEC))

    def test_unknown_basis_is_rejected_not_inferred(self):
        assert UnsupportedCode.BASIS_UNRESOLVED in codes(adapt_to_engine(model_of(import_zone(), basis=None), engine_basis=SEC))
        a = adapt_to_engine(model_of(import_zone(), basis=SettingBasis.UNKNOWN), engine_basis=SEC)
        assert UnsupportedCode.BASIS_UNRESOLVED in codes(a)

    def test_basis_mismatch_does_no_conversion(self):
        a = adapt_to_engine(model_of(import_zone(), basis=SettingBasis.PRIMARY), engine_basis=SEC)
        assert not a.supported and UnsupportedCode.BASIS_MISMATCH in codes(a)

    def test_all_problems_are_reported_together(self):
        z = import_zone(direction=m(ZoneDirection.NON_DIRECTIONAL), reach=unresolved(), phase_timer_s=unresolved())
        assert len(adapt_to_engine(model_of(z), engine_basis=SEC).reasons) >= 3

    def test_reasons_name_the_zone(self):
        a = adapt_to_engine(model_of(import_zone("Z2", direction=m(ZoneDirection.NON_DIRECTIONAL))), engine_basis=SEC)
        assert a.reasons[0].zone_id == "Z2"

    def test_incomplete_allowed_only_when_requested(self):
        z = import_zone(reach=unresolved())
        assert not adapt_to_engine(model_of(z), engine_basis=SEC).supported
        a = adapt_to_engine(model_of(z), engine_basis=SEC, allow_incomplete_zones=True)
        assert a.supported and a.zones[0].reactive_reach_ohm is None

    def test_adaptation_does_not_mutate_the_canonical_model(self):
        z = import_zone(
            phase_earth_enabled=m(True), earth_timer_s=m(0.3),
            compensation=ResidualCompensation(CompensationKind.KR_KX, kr=m(0.7), kx=m(0.6)),
        )
        mod = model_of(z, import_zone("Z2", char=CharacteristicType.LENTICULAR))
        before = copy.deepcopy(mod)
        adapt_to_engine(mod, engine_basis=SEC)
        adapt_to_engine(model_of(z), engine_basis=SEC)
        assert mod == before

    def test_zone_order_preserved(self):
        a = adapt_to_engine(
            model_of(import_zone("A", phase_timer_s=m(0.1)), import_zone("B", phase_timer_s=m(0.2)), import_zone("C", phase_timer_s=m(0.3))),
            engine_basis=SEC,
        )
        assert [z.delay_s for z in a.zones[:3]] == [0.1, 0.2, 0.3] and a.zone_ids == ("A", "B", "C", None)


# --- architecture guards ----------------------------------------------------

_APP = Path(__file__).resolve().parents[1] / "app"
_RELAY_NAMES = re.compile(r"p44\d|7sa\d|7sl|rel[56]\d\d|red670|grz|grl2|lfzp|rcs-?9|relz|micom|siemens|hitachi|toshiba", re.I)


def test_engine_adapter_and_manual_mapper_have_no_relay_specific_names():
    for name in ("engine_adapter.py", "manual_entry.py"):
        text = (_APP / "domain" / "relay_import" / name).read_text(encoding="utf-8")
        assert _RELAY_NAMES.search(text) is None, name


def test_engine_does_not_import_relay_import():
    text = (_APP / "domain" / "distance_protection.py").read_text(encoding="utf-8")
    assert "relay_import" not in text
    svc = (_APP / "services" / "distance_protection_analysis_service.py").read_text(encoding="utf-8")
    assert "relay_import" not in svc


def test_adapter_and_mapper_stay_free_of_framework_and_storage():
    banned = re.compile(r"^\s*(?:from|import)\s+(?:pydantic|fastapi|sqlalchemy|app\.storage|app\.services|app\.api)", re.M)
    for name in ("engine_adapter.py", "manual_entry.py"):
        assert banned.search((_APP / "domain" / "relay_import" / name).read_text(encoding="utf-8")) is None
