"""Modelling/contract tests for the relay-import foundation (Slice 1).

These prove the canonical model can represent materially different relay
styles and that unknown relays fail safe. They are NOT parser tests: no PDF,
no extraction, no relay-specific parsing -- the "profiles" here are tiny
test doubles that hand-build models the way a real profile would.
"""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import pytest

from app.domain.relay_import import (
    CanonicalDistanceProtectionModel,
    CharacteristicSpec,
    CharacteristicType,
    CompensationKind,
    DistanceZone,
    ExtraQuantity,
    GenericFallbackProfile,
    ImpedanceValue,
    InstrumentTransformers,
    MappingStatus,
    MatchLevel,
    ProfileMatch,
    Provenance,
    ProtectedLine,
    RawRelayDocument,
    RawSetting,
    RelayMetadata,
    RelayProfile,
    RelayProfileRegistry,
    ResidualCompensation,
    ResistiveReach,
    SettingBasis,
    SettingRange,
    Sourced,
    SourceFormat,
    SourceLocation,
    SourceRef,
    UnresolvedSetting,
    ZoneDirection,
    ZoneStatus,
    inferred,
    mapped,
    unresolved,
)

PID, PVER = "test-profile", "0"
REF = (SourceRef("s1", parameter_name="test"),)


def m(value, raw=None):
    return mapped(value, sources=REF, profile_id=PID, profile_version=PVER, raw_value=raw)


def zone_enabled(zone_id: str, direction=ZoneDirection.FORWARD, **kw) -> DistanceZone:
    return DistanceZone(
        zone_id=zone_id,
        status=m(ZoneStatus.ENABLED),
        direction=m(direction),
        **kw,
    )


# --- raw document ----------------------------------------------------------


class TestRawRelayDocument:
    def test_preserves_loose_information_without_requiring_ids_or_tables(self):
        bare = RawSetting(setting_id="a", raw_value="Zone 1 reach 3.2 ohm", source_text="Zone 1 reach 3.2 ohm")
        rich = RawSetting(
            setting_id="b",
            name="Z1",
            parameter_id="0A.02",
            section_path=("Distance", "Zone 1"),
            raw_value="3.20",
            normalized_value=3.2,
            unit="ohm",
            setting_range=SettingRange(text="0.01 .. 500", minimum=0.01, maximum=500, step=0.01),
            location=SourceLocation(page=4, line=12),
            notes=("Sec",),
        )
        doc = RawRelayDocument(SourceFormat.PDF, (bare, rich), identification_hints=("MiCOM P441",))
        assert doc.by_id("b") is rich
        assert doc.by_parameter_id("0A.02") == (rich,)
        assert doc.in_section("Distance") == (rich,)
        assert doc.by_id("missing") is None

    @pytest.mark.parametrize("fmt", list(SourceFormat))
    def test_source_format_is_not_pdf_specific(self, fmt):
        assert RawRelayDocument(fmt).source_format is fmt

    def test_duplicate_setting_ids_rejected(self):
        with pytest.raises(ValueError):
            RawRelayDocument(SourceFormat.CSV, (RawSetting("x"), RawSetting("x")))


# --- provenance ------------------------------------------------------------


class TestProvenance:
    def test_unresolved_carries_no_value_but_keeps_raw_text(self):
        s = unresolved("Blinder 7.5", sources=REF)
        assert not s.is_resolved and s.value is None
        assert s.provenance.raw_value == "Blinder 7.5"

    def test_unresolved_value_with_a_value_is_rejected(self):
        with pytest.raises(ValueError):
            Sourced(1.0, Provenance(MappingStatus.UNRESOLVED))

    def test_resolved_status_without_value_is_rejected(self):
        with pytest.raises(ValueError):
            Sourced(None, Provenance(MappingStatus.MAPPED, REF))

    def test_mapped_or_inferred_must_cite_a_source(self):
        with pytest.raises(ValueError):
            Provenance(MappingStatus.MAPPED)
        with pytest.raises(ValueError):
            Provenance(MappingStatus.INFERRED)

    def test_inferred_needs_confirmation_mapped_does_not(self):
        inf = inferred(1.0, sources=REF, profile_id=PID, profile_version=PVER)
        assert inf.needs_confirmation and not m(1.0).needs_confirmation


# --- relay styles ----------------------------------------------------------


class TestRelayStyles:
    def test_p441_style_magnitude_reach_with_separate_phase_and_ground_resistance(self):
        z1 = zone_enabled(
            "Z1",
            characteristic=CharacteristicSpec(type=m(CharacteristicType.QUADRILATERAL)),
            reach=m(ImpedanceValue(magnitude_ohm=6.0, angle_deg=80.0), raw="6.00 ohm"),
            resistive_reach=ResistiveReach(phase_phase=m(8.0), phase_earth=m(12.0)),
            compensation=ResidualCompensation(
                CompensationKind.K0_MAGNITUDE_ANGLE, k0_magnitude=m(0.66), k0_angle_deg=m(-5.0)
            ),
            tilt_deg=m(-3.0),
            common_timer_s=m(0.0),
        )
        assert z1.reach.value.is_polar and not z1.reach.value.is_rectangular
        assert z1.resistive_reach.phase_phase.value != z1.resistive_reach.phase_earth.value
        assert z1.compensation.kind is CompensationKind.K0_MAGNITUDE_ANGLE

    def test_7sa613_style_explicit_rx_with_re_rl_compensation(self):
        z1 = zone_enabled(
            "Z1",
            reach=m(ImpedanceValue(r_ohm=1.2, x_ohm=4.5)),
            resistive_reach=ResistiveReach(common=m(1.2)),
            compensation=ResidualCompensation(
                CompensationKind.RE_RL_XE_XL, re_rl=m(0.85), xe_xl=m(0.78)
            ),
            phase_timer_s=m(0.0),
        )
        assert z1.reach.value.is_rectangular
        assert z1.compensation.re_rl.value == 0.85

    def test_rel670_style_sequence_impedances_and_independent_timers(self):
        line = ProtectedLine(
            length=m(42.0),
            length_unit=m("km"),
            positive_sequence_impedance=m(ImpedanceValue(r_ohm=0.03, x_ohm=0.32)),
            zero_sequence_impedance=m(ImpedanceValue(r_ohm=0.2, x_ohm=1.0)),
        )
        z2 = zone_enabled(
            "Z2",
            reach=m(ImpedanceValue(r_ohm=2.1, x_ohm=19.0)),
            zero_sequence_reach=m(ImpedanceValue(r_ohm=12.0, x_ohm=60.0)),
            resistive_reach=ResistiveReach(phase_phase=m(20.0), phase_earth=m(30.0)),
            phase_timer_s=m(0.4),
            earth_timer_s=m(0.5),
            phase_phase_enabled=m(True),
            phase_earth_enabled=m(True),
        )
        assert z2.phase_timer_s.value != z2.earth_timer_s.value
        assert z2.zero_sequence_reach.value.to_rectangular() == (12.0, 60.0)
        assert line.zero_sequence_impedance.value.x_ohm == 1.0

    def test_reverse_zone(self):
        z = zone_enabled("Z4", direction=ZoneDirection.REVERSE, reach=m(ImpedanceValue(magnitude_ohm=3, angle_deg=75)))
        assert z.direction.value is ZoneDirection.REVERSE

    def test_inactive_zone_keeps_status_without_inventing_geometry(self):
        z = DistanceZone("Z5", status=m(ZoneStatus.INACTIVE), direction=m(ZoneDirection.INACTIVE))
        assert z.status.value is ZoneStatus.INACTIVE
        assert not z.reach.is_resolved

    def test_non_directional_zone(self):
        z = zone_enabled("Z3", direction=ZoneDirection.NON_DIRECTIONAL)
        assert z.direction.value is ZoneDirection.NON_DIRECTIONAL

    def test_more_than_four_zones_including_special_zone(self):
        zones = tuple(zone_enabled(f"Z{i}") for i in range(1, 8)) + (zone_enabled("Z1B"),)
        model = CanonicalDistanceProtectionModel(RelayMetadata(SourceFormat.PDF), zones=zones)
        assert len(model.zones) == 8
        assert model.zone("Z1B") is not None and model.zone("Z7") is not None

    def test_duplicate_zone_ids_rejected(self):
        with pytest.raises(ValueError):
            CanonicalDistanceProtectionModel(
                RelayMetadata(SourceFormat.PDF), zones=(DistanceZone("Z1"), DistanceZone("Z1"))
            )

    @pytest.mark.parametrize(
        "ctype", [CharacteristicType.MHO, CharacteristicType.LENTICULAR, CharacteristicType.QUADRILATERAL]
    )
    def test_characteristic_types(self, ctype):
        z = zone_enabled("Z1", characteristic=CharacteristicSpec(type=m(ctype)))
        assert z.characteristic.type.value is ctype

    def test_polygon_custom_needs_three_vertices(self):
        ok = CharacteristicSpec(
            type=m(CharacteristicType.POLYGON_CUSTOM), polygon_vertices_ohm=((0, 0), (5, 0), (5, 5), (0, 5))
        )
        assert len(ok.polygon_vertices_ohm) == 4
        with pytest.raises(ValueError):
            CharacteristicSpec(polygon_vertices_ohm=((0, 0), (1, 1)))

    def test_unknown_characteristic_is_representable_and_keeps_oem_text(self):
        z = zone_enabled(
            "Z1",
            characteristic=CharacteristicSpec(
                type=m(CharacteristicType.UNKNOWN), oem_description="OEM 'Z-Shape 3' blinders"
            ),
            unresolved_settings=(UnresolvedSetting("s9", "Blinder", "7.5", "ohm", "geometry unknown"),),
        )
        assert z.characteristic.type.value is CharacteristicType.UNKNOWN
        assert z.unresolved_settings[0].raw_value == "7.5"

    def test_unresolved_characteristic_type_is_distinct_from_unknown(self):
        z = DistanceZone("Z1")
        assert not z.characteristic.type.is_resolved


# --- compensation ----------------------------------------------------------


class TestCompensation:
    def test_kr_kx_and_oem_specific_representable(self):
        ResidualCompensation(CompensationKind.KR_KX, kr=m(0.7), kx=m(0.6))
        oem = ResidualCompensation(
            CompensationKind.OEM_SPECIFIC, oem_values=(ExtraQuantity("kZN-ratio", m(0.9), None),)
        )
        assert oem.oem_values[0].name == "kZN-ratio"

    def test_components_of_a_different_definition_are_rejected(self):
        with pytest.raises(ValueError):
            ResidualCompensation(CompensationKind.KR_KX, kr=m(0.7), k0_magnitude=m(0.66))
        with pytest.raises(ValueError):
            ResidualCompensation(CompensationKind.K0_MAGNITUDE_ANGLE, oem_values=(ExtraQuantity("x", m(1.0)),))

    def test_no_silent_conversion_between_definitions(self):
        comp = ResidualCompensation(CompensationKind.RE_RL_XE_XL, re_rl=m(0.85), xe_xl=m(0.78))
        assert not comp.k0_magnitude.is_resolved and not comp.kr.is_resolved
        assert not any(hasattr(comp, n) for n in ("to_k0", "to_kr_kx", "convert"))


# --- impedance representation ---------------------------------------------


class TestImpedanceValue:
    def test_form_is_preserved_and_conversion_is_explicit(self):
        z = ImpedanceValue(magnitude_ohm=10.0, angle_deg=60.0)
        r, x = z.to_rectangular()
        assert (z.r_ohm, z.x_ohm) == (None, None)
        assert math.isclose(r, 5.0) and math.isclose(x, 10 * math.sin(math.radians(60)))

    @pytest.mark.parametrize(
        "kw", [{}, {"r_ohm": 1.0}, {"magnitude_ohm": 1.0}, {"x_ohm": 1.0, "magnitude_ohm": 2.0}]
    )
    def test_incomplete_forms_rejected(self, kw):
        with pytest.raises(ValueError):
            ImpedanceValue(**kw)


# --- metadata / transformers ------------------------------------------------


def test_metadata_and_bases_default_to_unresolved_not_guessed():
    md = RelayMetadata(SourceFormat.EXCEL)
    tr = InstrumentTransformers()
    assert not md.manufacturer.is_resolved and md.profile_id is None
    assert not tr.setting_basis.is_resolved and not tr.ct_primary_a.is_resolved
    ok = InstrumentTransformers(setting_basis=m(SettingBasis.SECONDARY), ct_primary_a=m(1200.0))
    assert ok.setting_basis.value is SettingBasis.SECONDARY


def test_walk_reports_confirmation_and_unresolved_items():
    zone = zone_enabled(
        "Z1",
        reach=inferred(
            ImpedanceValue(magnitude_ohm=5, angle_deg=75),
            sources=REF,
            profile_id=PID,
            profile_version=PVER,
        ),
    )
    model = CanonicalDistanceProtectionModel(RelayMetadata(SourceFormat.PDF), zones=(zone,))
    assert model.items_needing_confirmation() == ("zones[Z1].reach",)
    assert "zones[Z1].tilt_deg" in model.unresolved_paths()
    assert "metadata.manufacturer" in model.unresolved_paths()


# --- profile interface / fail-safe -----------------------------------------


class _FakeProfile:
    def __init__(self, profile_id: str, level: MatchLevel):
        self.profile_id, self.version, self._level = profile_id, "1", level

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        return ProfileMatch(self._level)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        return CanonicalDistanceProtectionModel(
            RelayMetadata(document.source_format, profile_id=self.profile_id, profile_version=self.version),
            zones=(zone_enabled("Z1"),),
        )


def _doc() -> RawRelayDocument:
    return RawRelayDocument(
        SourceFormat.PDF,
        (
            RawSetting("a", name="Mystery 1", raw_value="3.7", unit="x"),
            RawSetting("b", name="Mystery 2", raw_value="ON"),
        ),
        identification_hints=("Unknown Relay 9000",),
    )


class TestProfiles:
    def test_fake_profile_satisfies_protocol(self):
        assert isinstance(_FakeProfile("p", MatchLevel.NONE), RelayProfile)

    def test_unknown_relay_falls_back_retaining_raw_and_inventing_nothing(self):
        model = RelayProfileRegistry().interpret(_doc())
        assert model.zones == ()
        assert model.metadata.profile_id is None
        assert [u.raw_value for u in model.unmapped_settings] == ["3.7", "ON"]
        assert all(not s.is_resolved for _, s in model.iter_sourced())
        assert model.items_needing_confirmation() == ()

    def test_single_confirmed_profile_is_used(self):
        reg = RelayProfileRegistry((_FakeProfile("a", MatchLevel.POSSIBLE), _FakeProfile("b", MatchLevel.CONFIRMED)))
        assert reg.interpret(_doc()).metadata.profile_id == "b"

    def test_possible_match_alone_is_not_enough(self):
        reg = RelayProfileRegistry((_FakeProfile("a", MatchLevel.POSSIBLE),))
        assert reg.interpret(_doc()).zones == ()

    def test_ambiguous_confirmed_matches_fail_safe(self):
        reg = RelayProfileRegistry((_FakeProfile("a", MatchLevel.CONFIRMED), _FakeProfile("b", MatchLevel.CONFIRMED)))
        model = reg.interpret(_doc())
        assert model.zones == () and any("ambiguous" in n for n in model.interpretation_notes)

    def test_duplicate_profile_id_rejected(self):
        reg = RelayProfileRegistry((_FakeProfile("a", MatchLevel.NONE),))
        with pytest.raises(ValueError):
            reg.register(_FakeProfile("a", MatchLevel.NONE))

    def test_generic_fallback_handles_empty_document(self):
        model = GenericFallbackProfile().interpret(RawRelayDocument(SourceFormat.XML))
        assert model.unmapped_settings == () and model.zones == ()


# --- architecture guards ----------------------------------------------------

_APP = Path(__file__).resolve().parents[1] / "app"
_RELAY_NAMES = re.compile(r"p44\d|7sa\d|7sl|rel[56]\d\d|red670|grz|grl2|lfzp|rcs-?9|relz|micom", re.IGNORECASE)


def test_generic_engine_and_relay_import_contain_no_relay_specific_logic():
    sources = [_APP / "domain" / "distance_protection.py", *sorted((_APP / "domain" / "relay_import").glob("*.py"))]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        hit = _RELAY_NAMES.search(text)
        assert hit is None, f"{path.name} mentions relay-specific name {hit.group(0)!r}"


def test_relay_import_stays_pure_and_never_touches_persistence():
    banned = re.compile(r"^\s*(?:from|import)\s+(?:pydantic|fastapi|sqlalchemy|app\.storage|app\.services|app\.api)", re.M)
    for path in (_APP / "domain" / "relay_import").glob("*.py"):
        assert banned.search(path.read_text(encoding="utf-8")) is None, path.name


def test_models_are_immutable():
    z = DistanceZone("Z1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        z.zone_id = "Z2"
