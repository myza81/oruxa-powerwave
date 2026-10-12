"""Explicit R/X quadrilateral geometry: a generic, relay-neutral capability of the canonical model,
the engine adapter, Apply Settings and the Distance Protection engine.

A quadrilateral can be stated two ways and the two coexist:

* **polar reach**  - a reach at a characteristic angle (the pre-existing form);
* **explicit R/X** - an X limit, a +R limit and a -R limit, with NO angle.

Nothing here knows a relay: the zones are built from plain numbers. The 7SA511 mapping onto this
capability is tested in ``test_relay_7sa511_profile.py`` / ``test_relay_7sa511_workflow.py``.
"""

from __future__ import annotations

import io
import json
import math
import re
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.distance_protection import (
    CHARACTERISTIC_MHO,
    CHARACTERISTIC_QUADRILATERAL,
    GEOMETRY_EXPLICIT_RX,
    GEOMETRY_POLAR,
    ZONE_STATE_NOT_OPERATED,
    ZONE_STATE_OPERATED,
    NamedZone,
    ZoneSettings,
    evaluate_zone_state,
    evaluate_zones,
    explicit_rx_quadrilateral_zone_operated,
    quadrilateral_zone_operated,
)
from app.domain.impedance import ImpedancePoint
from app.domain.relay_import import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    DistanceZone,
    ImpedanceValue,
    InstrumentTransformers,
    RelayMetadata,
    ResistiveReach,
    SettingBasis,
    SourceFormat,
    SourceRef,
    ZoneDirection,
    ZoneStatus,
    mapped,
    unresolved,
)
from app.domain.relay_import.apply_settings import build_apply_plan
from app.domain.relay_import.canonical_codec import decode_model, encode_model
from app.domain.relay_import.canonical_distance import GeometryMode, SourceNote, SourceNoteKind
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.manual_entry import engine_zones_from_manual, manual_to_canonical
from app.domain.relay_import.review_state import ReviewDecisions, apply_review
from app.main import create_app

SEC = "secondary"
REF = (SourceRef("s1"),)
MANUAL_URL = "/api/v1/workspaces/ws-rx/distance-protection-manual"
APP = Path(__file__).resolve().parents[1] / "app"


def m(value):
    return mapped(value, sources=REF, profile_id="t", profile_version="0")


def point(r, x):
    return ImpedancePoint(r, x, math.hypot(r, x), math.degrees(math.atan2(x, r)))


def explicit_zone(zone_id, *, x, right, left=0.0, direction=ZoneDirection.FORWARD, delay=0.0, **kw):
    return DistanceZone(
        zone_id=zone_id,
        name=f"Zone {zone_id}",
        status=m(ZoneStatus.ENABLED),
        direction=m(direction),
        phase_phase_enabled=m(True),
        phase_timer_s=m(delay),
        characteristic=CharacteristicSpec(
            type=m(CharacteristicType.QUADRILATERAL), geometry_mode=GeometryMode.EXPLICIT_RX
        ),
        x_reach_ohm=m(x) if x is not None else unresolved(),
        resistive_reach=ResistiveReach(
            phase_phase=m(right) if right is not None else unresolved(),
            reverse=m(left) if left is not None else unresolved(),
        ),
        **kw,
    )


def polar_zone(zone_id, *, reach, angle, right, left, direction=ZoneDirection.FORWARD, delay=0.0):
    return DistanceZone(
        zone_id=zone_id,
        name=f"Zone {zone_id}",
        status=m(ZoneStatus.ENABLED),
        direction=m(direction),
        phase_phase_enabled=m(True),
        phase_timer_s=m(delay),
        characteristic=CharacteristicSpec(type=m(CharacteristicType.QUADRILATERAL)),
        reach=m(ImpedanceValue(magnitude_ohm=reach, angle_deg=angle)),
        resistive_reach=ResistiveReach(phase_phase=m(right), reverse=m(left)),
    )


def model(*zones, characteristic=CharacteristicType.QUADRILATERAL):
    return CanonicalDistanceProtectionModel(
        metadata=RelayMetadata(source_format=SourceFormat.OTHER),
        transformers=InstrumentTransformers(setting_basis=m(SettingBasis.SECONDARY)),
        zones=tuple(zones),
    )


# The three zones of the motivating relay, as plain numbers.
Z1 = dict(x=2.74, right=1.84)
Z2 = dict(x=4.47, right=2.12)
Z3 = dict(x=0.69, right=0.46)


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------


class TestEngine:
    def test_zone_settings_default_to_polar_so_every_existing_construction_is_unchanged(self):
        z = ZoneSettings(True, None, 5.0, 4.0, 2.0, 80.0, 0.0)
        assert z.geometry_mode == GEOMETRY_POLAR and z.characteristic_angle_deg == 80.0

    @pytest.mark.parametrize("zid,spec", [("Z1", Z1), ("Z2", Z2)])
    def test_forward_zone_boundaries_are_the_x_limit_and_the_right_limit(self, zid, spec):
        x, right = spec["x"], spec["right"]
        zone = ZoneSettings(True, None, x, right, 0.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)

        def state(r, xx):
            return evaluate_zone_state(point(r, xx), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone)

        assert state(right - 0.01, x - 0.01) == ZONE_STATE_OPERATED
        assert state(right + 0.01, x - 0.01) == ZONE_STATE_NOT_OPERATED  # beyond +R
        assert state(right - 0.01, x + 0.01) == ZONE_STATE_NOT_OPERATED  # beyond X
        assert state(0.5, -0.01) == ZONE_STATE_NOT_OPERATED  # below the R axis: forward zones are directional
        assert state(-0.01, 0.5) == ZONE_STATE_NOT_OPERATED  # beyond the 0 ohm left limit

    def test_the_left_limit_extends_the_zone_to_negative_r(self):
        zone = ZoneSettings(True, None, 4.0, 3.0, 2.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)
        in_left = evaluate_zone_state(point(-1.9, 1.0), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone)
        beyond = evaluate_zone_state(point(-2.1, 1.0), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone)
        assert (in_left, beyond) == (ZONE_STATE_OPERATED, ZONE_STATE_NOT_OPERATED)

    def test_reverse_is_the_whole_characteristic_rotated_180_degrees(self):
        zone = ZoneSettings(True, None, Z3["x"], Z3["right"], 0.0, None, 3.0, "reverse", GEOMETRY_EXPLICIT_RX)

        def state(r, x):
            return evaluate_zone_state(point(r, x), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone)

        assert state(-(Z3["right"] - 0.01), -(Z3["x"] - 0.01)) == ZONE_STATE_OPERATED
        assert state(-(Z3["right"] + 0.01), -(Z3["x"] - 0.01)) == ZONE_STATE_NOT_OPERATED
        assert state(-(Z3["right"] - 0.01), -(Z3["x"] + 0.01)) == ZONE_STATE_NOT_OPERATED
        assert state(Z3["right"] - 0.01, Z3["x"] - 0.01) == ZONE_STATE_NOT_OPERATED  # the forward side is not this zone

    def test_explicit_geometry_is_the_orthogonal_special_case_of_the_polar_maths(self):
        # One set of maths: an explicit zone behaves exactly like a polar zone at 90 degrees.
        pts = [point(r, x) for r in (-4, -1, 0, 0.7, 1.84, 2.5) for x in (-3, 0, 0.4, 2.74, 3.5)]
        for direction in ("forward", "reverse"):
            for p in pts:
                a = explicit_rx_quadrilateral_zone_operated(
                    p, x_reach_ohm=2.74, right_resistive_reach_ohm=1.84, left_resistive_reach_ohm=0.5, direction=direction
                )
                b = quadrilateral_zone_operated(
                    p, reactive_reach_ohm=2.74, resistive_reach_forward_ohm=1.84,
                    resistive_reach_reverse_ohm=0.5, characteristic_angle_deg=90.0, direction=direction,
                )
                assert a is b

    def test_an_explicit_zone_needs_no_angle_but_a_polar_zone_still_does(self):
        explicit = ZoneSettings(True, None, 4.0, 3.0, 1.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)
        polar = ZoneSettings(True, None, 4.0, 3.0, 1.0, None, 0.0)
        p = point(1.0, 1.0)
        assert evaluate_zone_state(p, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=explicit) == ZONE_STATE_OPERATED
        assert evaluate_zone_state(p, characteristic=CHARACTERISTIC_QUADRILATERAL, zone=polar) == ZONE_STATE_NOT_OPERATED

    def test_an_incomplete_explicit_zone_does_not_operate(self):
        for missing in ("reactive", "right", "left", "delay"):
            kw = dict(reactive_reach_ohm=4.0, resistive_reach_forward_ohm=3.0, resistive_reach_reverse_ohm=1.0, delay_s=0.0)
            kw[{"reactive": "reactive_reach_ohm", "right": "resistive_reach_forward_ohm",
                "left": "resistive_reach_reverse_ohm", "delay": "delay_s"}[missing]] = None
            zone = ZoneSettings(True, characteristic_angle_deg=None, geometry_mode=GEOMETRY_EXPLICIT_RX, **kw)
            assert evaluate_zone_state(point(1, 1), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zone) == ZONE_STATE_NOT_OPERATED

    def test_explicit_limits_are_never_read_as_a_mho(self):
        zone = ZoneSettings(True, 5.0, 4.0, 3.0, 1.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)
        assert evaluate_zone_state(point(1, 1), characteristic=CHARACTERISTIC_MHO, zone=zone) == ZONE_STATE_NOT_OPERATED

    def test_polar_and_explicit_zones_coexist_in_one_evaluation(self):
        zones = [
            NamedZone("polar", ZoneSettings(True, None, 5.0, 4.0, 2.0, 75.0, 0.0)),
            NamedZone("explicit", ZoneSettings(True, None, 5.0, 4.0, 2.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)),
        ]
        # Inside the orthogonal box (R -2..4, X 0..5) but behind the 75 degree rotated one (x' = -0.2 < 0).
        results = {r.zone_key: r.state for r in evaluate_zones(point(-1.5, 0.2), characteristic=CHARACTERISTIC_QUADRILATERAL, zones=zones)}
        assert results == {"polar": ZONE_STATE_NOT_OPERATED, "explicit": ZONE_STATE_OPERATED}

    def test_the_polar_quadrilateral_is_numerically_unchanged(self):
        # Golden values of the polar form at a tilted angle (the pre-existing behaviour).
        z = ZoneSettings(True, None, 5.0, 4.0, 2.0, 80.0, 0.0)
        got = [evaluate_zone_state(point(r, x), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=z)
               for r, x in ((1, 3), (3.9, 0.5), (-1.0, 4), (4.5, 1), (0, 5.2), (-2.2, 2))]
        assert got == [ZONE_STATE_OPERATED, ZONE_STATE_OPERATED, ZONE_STATE_OPERATED, ZONE_STATE_NOT_OPERATED,
                       ZONE_STATE_NOT_OPERATED, ZONE_STATE_NOT_OPERATED]


# ---------------------------------------------------------------------------
# adapter
# ---------------------------------------------------------------------------


class TestAdapter:
    def test_an_explicit_zone_adapts_without_a_synthetic_angle(self):
        ad = adapt_to_engine(model(explicit_zone("Z1", **Z1, left=0.0)), engine_basis=SEC)
        assert ad.supported, [r.message for r in ad.reasons]
        z = ad.zones[0]
        assert z.geometry_mode == GEOMETRY_EXPLICIT_RX and z.characteristic_angle_deg is None
        assert (z.reactive_reach_ohm, z.resistive_reach_forward_ohm, z.resistive_reach_reverse_ohm) == (2.74, 1.84, 0.0)
        assert z.reach_ohm is None

    def test_a_polar_zone_adapts_exactly_as_before(self):
        ad = adapt_to_engine(model(polar_zone("P", reach=5.0, angle=80.0, right=4.0, left=2.0)), engine_basis=SEC)
        z = ad.zones[0]
        assert ad.supported and z.geometry_mode == GEOMETRY_POLAR and z.characteristic_angle_deg == 80.0
        assert (z.reactive_reach_ohm, z.resistive_reach_forward_ohm, z.resistive_reach_reverse_ohm) == (5.0, 4.0, 2.0)

    def test_polar_and_explicit_zones_adapt_together_each_in_its_own_mode(self):
        ad = adapt_to_engine(
            model(polar_zone("P", reach=5.0, angle=80.0, right=4.0, left=2.0), explicit_zone("E", **Z2, left=0.0)),
            engine_basis=SEC,
        )
        assert ad.supported
        assert [z.geometry_mode for z in ad.zones] == [GEOMETRY_POLAR, GEOMETRY_EXPLICIT_RX]
        assert [z.characteristic_angle_deg for z in ad.zones] == [80.0, None]

    def test_direction_stays_independent_of_the_geometry(self):
        ad = adapt_to_engine(model(explicit_zone("Z3", **Z3, direction=ZoneDirection.REVERSE)), engine_basis=SEC)
        assert ad.zones[0].direction == "reverse" and ad.zones[0].geometry_mode == GEOMETRY_EXPLICIT_RX

    def test_an_unresolved_x_limit_blocks_and_names_its_path(self):
        ad = adapt_to_engine(model(explicit_zone("Z1", x=None, right=1.84)), engine_basis=SEC)
        assert not ad.supported
        r = next(r for r in ad.reasons if r.code is UnsupportedCode.REACH_UNRESOLVED)
        assert r.message == "The Reactive Reach (X) is unresolved." and r.paths == ("zones[Z1].x_reach_ohm",)

    def test_an_unresolved_left_limit_is_not_invented(self):
        ad = adapt_to_engine(model(explicit_zone("Z1", **Z1, left=None)), engine_basis=SEC)
        assert not ad.supported
        assert any("Left Resistive Reach" in r.message and r.paths == ("zones[Z1].resistive_reach.reverse",) for r in ad.reasons)

    def test_explicit_limits_on_a_mho_are_refused_not_converted(self):
        z = replace(
            explicit_zone("Z1", **Z1),
            characteristic=CharacteristicSpec(type=m(CharacteristicType.MHO), geometry_mode=GeometryMode.EXPLICIT_RX),
        )
        ad = adapt_to_engine(model(z), engine_basis=SEC)
        assert not ad.supported and any(r.code is UnsupportedCode.GEOMETRY_UNSUPPORTED for r in ad.reasons)
        from app.domain.relay_import.review_state import engine_limits

        kind, _ = engine_limits(ad)["zones[Z1].characteristic.type"]
        assert kind == "unsupported"  # an engine limit, shown as such by the review

    def test_the_review_can_resolve_a_missing_x_limit_by_hand(self):
        eff = apply_review(model(explicit_zone("Z1", x=None, right=1.84)), ReviewDecisions(manual={"zones[Z1].x_reach_ohm": 2.74}))
        assert eff.zone("Z1").x_reach_ohm.value == 2.74
        assert adapt_to_engine(eff, engine_basis=SEC).supported

    def test_lenient_manual_adaptation_keeps_a_blank_x_absent(self):
        ad = adapt_to_engine(model(explicit_zone("Z1", x=None, right=1.84)), engine_basis=SEC, allow_incomplete_zones=True)
        assert ad.supported and ad.zones[0].reactive_reach_ohm is None and ad.zones[0].geometry_mode == GEOMETRY_EXPLICIT_RX


# ---------------------------------------------------------------------------
# Apply Settings
# ---------------------------------------------------------------------------


class TestApply:
    def test_the_plan_preserves_the_geometry_mode_and_carries_no_angle(self):
        mdl = model(explicit_zone("Z1", **Z1), polar_zone("P", reach=5.0, angle=80.0, right=4.0, left=2.0))
        plan = build_apply_plan(mdl, adapt_to_engine(mdl, engine_basis=SEC), impedance_basis=SEC)
        explicit, polar = plan.zones
        assert (explicit.geometry_mode, explicit.characteristic_angle_deg) == ("explicit_rx", None)
        assert (explicit.reactive_reach_ohm, explicit.resistive_reach_forward_ohm, explicit.resistive_reach_reverse_ohm) == (2.74, 1.84, 0.0)
        assert (polar.geometry_mode, polar.characteristic_angle_deg, polar.reactive_reach_ohm) == ("polar", 80.0, 5.0)

    def test_the_wire_payload_names_the_mode(self):
        from app.schemas.relay_import import ApplyZoneOut

        out = ApplyZoneOut(id="Z1", display_name="Zone 1", enabled=True, direction="forward", delay_s=0.0,
                           geometry_mode="explicit_rx", reactive_reach_ohm=2.74, resistive_reach_forward_ohm=1.84,
                           resistive_reach_reverse_ohm=0.0)
        assert out.model_dump()["geometry_mode"] == "explicit_rx" and out.model_dump()["characteristic_angle_deg"] is None
        assert ApplyZoneOut(id="Z", display_name="Z", enabled=False).geometry_mode == "polar"


# ---------------------------------------------------------------------------
# manual form path / API
# ---------------------------------------------------------------------------


class TestManualAndApi:
    def test_the_manual_path_keeps_an_explicit_zone_explicit(self):
        zones = (ZoneSettings(True, None, 2.74, 1.84, 0.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX),)
        out = engine_zones_from_manual(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=zones)
        assert out[0].geometry_mode == GEOMETRY_EXPLICIT_RX and out[0].characteristic_angle_deg is None
        assert (out[0].reactive_reach_ohm, out[0].resistive_reach_forward_ohm) == (2.74, 1.84)

    def test_a_polar_manual_zone_is_untouched(self):
        zones = (ZoneSettings(True, None, 5.0, 4.0, 2.0, 80.0, 0.0), ZoneSettings(True, None, 5.0, 4.0, 2.0, None, 0.0))
        out = engine_zones_from_manual(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC, zones=zones)
        assert out[0] == zones[0] and out[1].characteristic_angle_deg is None and out[1].geometry_mode == GEOMETRY_POLAR

    def test_manual_to_canonical_marks_only_explicit_quadrilateral_zones(self):
        explicit = ZoneSettings(True, None, 2.74, 1.84, 0.0, None, 0.0, "forward", GEOMETRY_EXPLICIT_RX)
        mdl = manual_to_canonical(characteristic=CHARACTERISTIC_QUADRILATERAL, impedance_basis=SEC,
                                  zones=(explicit, ZoneSettings(True, None, 5.0, 4.0, 2.0, 80.0, 0.0)))
        z1, z2 = mdl.zones
        assert z1.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX and z1.x_reach_ohm.value == 2.74 and not z1.reach.is_resolved
        assert z2.characteristic.geometry_mode is GeometryMode.POLAR_REACH and z2.reach.value.angle_deg == 80.0

    @pytest.fixture
    def client(self, settings):
        with TestClient(create_app(settings)) as c:
            yield c

    def _get(self, client, zones, *, current):
        q = dict(
            loop_label="AB", voltage_basis=SEC, current_basis=SEC, impedance_basis=SEC, characteristic="quadrilateral",
            v1_enabled=True, v1_magnitude=100, v1_unit="V", v1_angle_deg=0, v2_enabled=True, v2_magnitude=100, v2_unit="V",
            v2_angle_deg=-120, i1_enabled=True, i1_magnitude=current[0], i1_unit="A", i1_angle_deg=current[1],
            i2_enabled=True, i2_magnitude=current[0], i2_unit="A", i2_angle_deg=current[1] - 120, zones=json.dumps(zones),
        )
        return client.get(MANUAL_URL, params=q)

    @staticmethod
    def _current_for(r, x):
        """Phase current (A, deg) that puts the loop impedance at r + jx for 100 V phase voltages."""
        return 100.0 / math.hypot(r, x), -math.degrees(math.atan2(x, r))

    def test_the_api_evaluates_explicit_and_polar_zones_in_one_request(self, client):
        zones = [
            {"key": "E", "enabled": True, "geometry_mode": "explicit_rx", "reactive_reach_ohm": 2.74,
             "resistive_reach_forward_ohm": 1.84, "resistive_reach_reverse_ohm": 0, "delay_s": 0},
            {"key": "P", "enabled": True, "reactive_reach_ohm": 2.74, "resistive_reach_forward_ohm": 1.84,
             "resistive_reach_reverse_ohm": 0, "characteristic_angle_deg": 60, "delay_s": 0},
        ]
        r = self._get(client, zones, current=self._current_for(0.2, 2.5))
        assert r.status_code == 200
        states = {z["zone_key"]: z["state"] for z in r.json()["zones"]}
        assert states == {"E": "operated", "P": "not_operated"}  # (0.2, 2.5): inside the orthogonal box, r' = -1.08 outside the 60 degree one

    def test_an_explicit_zone_without_an_angle_still_operates_through_the_api(self, client):
        zones = [{"key": "Z1", "enabled": True, "geometry_mode": "explicit_rx", "reactive_reach_ohm": 2.74,
                  "resistive_reach_forward_ohm": 1.84, "resistive_reach_reverse_ohm": 0, "delay_s": 0}]
        inside = {z["zone_key"]: z["state"] for z in self._get(client, zones, current=self._current_for(1.0, 2.0)).json()["zones"]}
        beyond_r = {z["zone_key"]: z["state"] for z in self._get(client, zones, current=self._current_for(2.0, 1.0)).json()["zones"]}
        beyond_x = {z["zone_key"]: z["state"] for z in self._get(client, zones, current=self._current_for(1.0, 3.0)).json()["zones"]}
        assert (inside["Z1"], beyond_r["Z1"], beyond_x["Z1"]) == ("operated", "not_operated", "not_operated")

    def test_an_unknown_geometry_mode_is_a_422(self, client):
        zones = [{"key": "Z1", "enabled": True, "geometry_mode": "tilted"}]
        assert self._get(client, zones, current=(100, 0)).status_code == 422

    def test_a_request_without_a_mode_is_polar_as_before(self, client):
        zones = [{"key": "Z1", "enabled": True, "reactive_reach_ohm": 5, "resistive_reach_forward_ohm": 4,
                  "resistive_reach_reverse_ohm": 2, "characteristic_angle_deg": 80, "delay_s": 0}]
        r = self._get(client, zones, current=self._current_for(1.0, 2.0))
        assert r.status_code == 200 and r.json()["zones"][0]["state"] == "operated"


# ---------------------------------------------------------------------------
# snapshot codec / architecture
# ---------------------------------------------------------------------------


class TestCodecAndIsolation:
    def test_the_review_snapshot_round_trips_the_geometry_mode_and_source_notes(self):
        note = SourceNote(SourceNoteKind.PROPOSED_REQUIREMENT, "Zone 1 timer 0.15s", "timer", "0.15 s", REF)
        z = explicit_zone("Z1", **Z1, source_notes=(note,))
        back = decode_model(encode_model(model(z))).zone("Z1")
        assert back.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX and back.x_reach_ohm.value == 2.74
        assert back.source_notes == (note,)

    def test_an_old_snapshot_without_the_new_fields_decodes_as_polar(self):
        data = encode_model(model(polar_zone("P", reach=5.0, angle=80.0, right=4.0, left=2.0)))
        zone = data["zones"][0]
        zone.pop("x_reach_ohm"), zone.pop("source_notes"), zone["characteristic"].pop("geometry_mode")
        back = decode_model(data).zone("P")
        assert back.characteristic.geometry_mode is GeometryMode.POLAR_REACH and back.source_notes == ()

    def test_source_notes_are_accounted_for_in_the_referenced_settings(self):
        note = SourceNote(SourceNoteKind.PROPOSED_REQUIREMENT, "t", sources=(SourceRef("note-1"),))
        assert "note-1" in model(explicit_zone("Z1", **Z1, source_notes=(note,))).referenced_setting_ids()

    def test_no_relay_specific_geometry_logic_in_the_generic_layers(self):
        names = re.compile(r"7sa|siemens|siprotec|digsi|micom|p441|schneider", re.IGNORECASE)
        sources = [
            APP / "domain" / "distance_protection.py",
            APP / "services" / "relay_extraction_review.py",
            APP / "services" / "relay_pdf_extractor.py",
            APP / "schemas" / "relay_import.py",
            APP / "schemas" / "distance_protection_analysis.py",
            *sorted((APP / "domain" / "relay_import").glob("*.py")),
        ]
        for path in sources:
            hit = names.search(path.read_text(encoding="utf-8"))
            assert hit is None or path.name == "identification.py", f"{path.name}: {hit.group(0)}"
        frontend = (APP.parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
        assert not re.search(r"7SA511|siemens-7sa511", frontend)
