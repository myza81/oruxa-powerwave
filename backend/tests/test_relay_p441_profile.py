"""Relay Import Slice 6: MiCOM P441 engineering interpretation (micom-p441-v1).

Synthetic documents mirror the shape the generic extractor produces for the
owner's P441 sheet (code / name / value / printed range). The real sample is
exercised at the bottom when ``RELAY_SAMPLE_PDF_DIR`` is set (owner files are
not committed). Nothing here applies anything to the Distance Protection form.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.domain.relay_import.canonical_distance import (
    CharacteristicType,
    CompensationKind,
    ImpedanceValue,
    SettingBasis,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.identification import IdentificationStatus
from app.domain.relay_import.profile import MatchLevel
from app.domain.relay_import.provenance import MappingStatus, mapped
from app.domain.relay_import.raw_document import RawRelayDocument, SourceFormat
from app.relay_profiles import identification_catalogue as catalogue
from app.relay_profiles.micom_p441 import (
    PROFILE_ID,
    PROFILE_VERSION,
    VALIDATION_STATUS,
    MicomP441Profile,
)
from app.services.relay_interpretation_summary import (
    InterpretationStatus,
    count_model,
    summarize_interpretation,
)
from tests.relay_p441_fixtures import BASE, NOTES, make_doc

APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(scope="module")
def profile() -> MicomP441Profile:
    return MicomP441Profile()


@pytest.fixture(scope="module")
def doc() -> RawRelayDocument:
    return make_doc()


@pytest.fixture(scope="module")
def model(profile, doc):
    return profile.interpret(doc)


def zone(model, zone_id):
    z = model.zone(zone_id)
    assert z is not None, zone_id
    return z


def interpret(doc):
    return MicomP441Profile().interpret(doc)


# ---------------------------------------------------------------------------
# Identity, versioning, routing
# ---------------------------------------------------------------------------


class TestProfileIdentity:
    def test_explicit_version_and_validation_status(self, profile):
        assert PROFILE_VERSION == "micom-p441-v1" == profile.version
        assert PROFILE_ID == "schneider-micom-p441" == profile.profile_id
        # Awaiting owner UAT: never called Validated by this slice.
        assert VALIDATION_STATUS == "Implemented / Awaiting Validation"
        assert profile.validation_status == VALIDATION_STATUS
        assert "validated" not in VALIDATION_STATUS.replace("Awaiting Validation", "").lower()

    def test_profile_id_matches_the_identification_catalogue(self):
        assert PROFILE_ID in {d.profile_id for d in catalogue.IDENTIFICATION_DESCRIPTORS}

    def test_metadata_carries_the_profile_and_normalised_identity(self, model):
        m = model.metadata
        assert (m.profile_id, m.profile_version) == (PROFILE_ID, PROFILE_VERSION)
        assert m.source_format is SourceFormat.PDF
        assert (m.manufacturer.value, m.family.value, m.model.value) == ("Schneider Electric", "MiCOM P44x", "P441")
        assert m.scheme_name.value == "SE_P441?A1???038?JE"
        assert m.active_setting_group.value == "Group 1"

    def test_source_wording_is_kept_beside_the_normalised_identity(self, model):
        assert model.metadata.model.provenance.raw_value == "Scheme: SE_P441?A1???038?JE"
        assert model.metadata.scheme_name.provenance.raw_value == "Scheme: SE_P441?A1???038?JE"
        assert any("not named in the document" in n for n in model.metadata.manufacturer.provenance.notes)

    def test_firmware_is_not_claimed_from_a_free_text_marker(self):
        d = make_doc(notes=NOTES + ("To defeat Zone 4 for all P441 relay (Minor Ver.C2.13), connected to",))
        v = interpret(d).metadata.version
        assert not v.is_resolved and v.provenance.raw_value == "Minor Ver.C2.13" and v.provenance.sources

    def test_model_requires_the_scheme_field(self):
        m = interpret(make_doc(scheme=None)).metadata
        assert not m.model.is_resolved and not m.manufacturer.is_resolved


@pytest.fixture(scope="module")
def registry():
    return catalogue.build_registry()


class TestRouting:
    def _identify(self, registry, scheme):
        return registry.identify(make_doc(scheme=("LZOP", f"Scheme: {scheme}")))

    def test_only_an_identified_p441_reaches_the_profile(self, registry):
        ident = self._identify(registry, "SE_P441?A1???038?JE")
        assert ident.status is IdentificationStatus.IDENTIFIED
        assert registry.profile_for(ident).profile_id == PROFILE_ID

    @pytest.mark.parametrize("scheme", ["7SA6131_4AB02_3GA0", "7SA511_V3.2_1A", "GRL200_TNB", "REL670_V2", "RCS-941_V2"])
    def test_other_identified_families_are_not_routed_to_p441(self, registry, scheme):
        ident = self._identify(registry, scheme)
        assert ident.status is IdentificationStatus.IDENTIFIED and ident.profile_id != PROFILE_ID
        # An identified relay with its own interpretation profile (the 7SA511, Slice 11) reaches that
        # profile; an identification-only family reaches none. Neither ever reaches the P441 profile.
        routed = registry.profile_for(ident)
        assert routed is None or routed.profile_id == ident.profile_id != PROFILE_ID

    def test_unknown_and_ambiguous_documents_are_not_routed(self, registry):
        assert registry.profile_for(self._identify(registry, "XYZ9000_V1")) is None
        mixed = registry.identify(make_doc(scheme=("LZOP", "Scheme: P441_V1"), extra=((None, "Relay Type", "7SA6131", None),)))
        if mixed.status is not IdentificationStatus.IDENTIFIED:
            assert registry.profile_for(mixed) is None

    def test_match_confirms_only_a_p441_scheme(self, profile):
        assert profile.match(make_doc()).level is MatchLevel.CONFIRMED
        assert profile.match(make_doc(scheme=("LZOP", "Scheme: 7SA6131_4AB02"))).level is MatchLevel.NONE
        assert profile.match(make_doc(scheme=None)).level is MatchLevel.NONE

    def test_registry_interpret_does_not_read_other_relays_as_a_p441(self, registry):
        other = make_doc(scheme=("LZOP", "Scheme: 7SA6131_4AB02_3GA0"))
        m = registry.interpret(other)
        assert m.zones == () and m.metadata.profile_id is None and len(m.unmapped_settings) == len(other.settings)


# ---------------------------------------------------------------------------
# CT / VT / basis
# ---------------------------------------------------------------------------


class TestTransformersAndBasis:
    def test_ct_vt_ratios(self, model):
        t = model.transformers
        assert (t.ct_primary_a.value, t.ct_secondary_a.value) == (1200.0, 1.0)
        assert (t.vt_primary_v.value, t.vt_secondary_v.value) == (132000.0, 110.0)
        assert all(s.provenance.status is MappingStatus.MAPPED for s in (t.ct_primary_a, t.ct_secondary_a, t.vt_primary_v, t.vt_secondary_v))

    def test_no_voltage_or_current_base_is_invented(self, model):
        assert not model.transformers.voltage_base_v.is_resolved
        assert not model.transformers.current_base_a.is_resolved

    def test_basis_is_the_relay_setting_values_selection(self, model):
        b = model.transformers.setting_basis
        assert b.value is SettingBasis.SECONDARY and b.provenance.status is MappingStatus.MAPPED
        assert b.provenance.sources[0].parameter_id == "092E"

    def test_primary_selection_is_mapped_as_primary(self):
        d = make_doc(overrides={"092E": ("Setting Values", "Primary", "Sec'y/Primary")})
        assert interpret(d).transformers.setting_basis.value is SettingBasis.PRIMARY

    def test_measurement_display_selection_is_not_the_settings_basis(self):
        d = make_doc(drop=("092E",))  # 0D02 'Local Values = Primary' is still present
        assert not interpret(d).transformers.setting_basis.is_resolved

    @pytest.mark.parametrize("value", ["Sec/Pri", "Both", ""])
    def test_basis_ambiguity_is_unresolved(self, value):
        m = interpret(make_doc(overrides={"092E": ("Setting Values", value, "Sec'y/Primary")}))
        assert not m.transformers.setting_basis.is_resolved

    def test_conflicting_basis_entries_are_not_resolved_by_choosing_one(self):
        d = make_doc(extra=(("092E", "Setting Values", "Primary", "Sec'y/Primary"),))
        s = interpret(d).transformers.setting_basis
        assert not s.is_resolved and len(s.provenance.sources) == 2

    def test_unresolved_basis_makes_the_adapter_refuse(self):
        m = interpret(make_doc(drop=("092E",)))
        reasons = {r.code for r in adapt_to_engine(m, engine_basis="secondary").reasons}
        assert UnsupportedCode.BASIS_UNRESOLVED in reasons

    def test_kv_voltage_unit_is_not_scaled(self):
        d = make_doc(overrides={"0A01": ("Main VT Primary", "132", "0.1-1000kV")})
        v = interpret(d).transformers.vt_primary_v
        assert not v.is_resolved and v.provenance.raw_value == "132"  # raw kept, no x1000

    def test_ct_secondary_must_be_a_1a_5a_value(self):
        d = make_doc(overrides={"0A08": ("Phase CT Sec'y", "2", "1A/5A")})
        assert not interpret(d).transformers.ct_secondary_a.is_resolved

    def test_ct_note_disagreeing_with_the_settings_is_reported_not_resolved(self):
        d = make_doc(extra=((None, "a) To confirm CT ratio", "600/1", None),))
        m = interpret(d)
        assert m.transformers.ct_primary_a.value == 1200.0
        assert any("CT ratio" in n and "differs" in n for n in m.interpretation_notes)

    def test_no_conversion_note_when_secondary(self, model):
        assert any("no CT/VT conversion" in n for n in model.interpretation_notes)


# ---------------------------------------------------------------------------
# Protected line
# ---------------------------------------------------------------------------


class TestProtectedLine:
    def test_length_unit_and_angle(self, model):
        line = model.line
        assert (line.length.value, line.length_unit.value, line.line_angle_deg.value) == (7.03, "km", 80.0)
        assert {r.parameter_id for r in line.length.provenance.sources} == {"3002", "0D07"}

    def test_line_impedance_magnitude_is_kept_apart_from_the_angle(self, model):
        (extra,) = model.line.extras
        assert extra.name == "line_impedance_magnitude" and extra.value.value == 2.0
        assert not model.line.positive_sequence_impedance.is_resolved
        assert not model.line.zero_sequence_impedance.is_resolved

    def test_miles_are_kept_as_miles_not_converted(self):
        d = make_doc(overrides={"0D07": ("Distance Unit", "Miles", "Miles/km")})
        line = interpret(d).line
        assert (line.length.value, line.length_unit.value) == (7.03, "mile")

    def test_missing_distance_unit_leaves_the_length_unresolved(self):
        line = interpret(make_doc(drop=("0D07",))).line
        assert not line.length.is_resolved and line.length.provenance.raw_value == "7.03"
        assert not line.length_unit.is_resolved

    def test_unknown_distance_unit_is_unresolved(self):
        d = make_doc(overrides={"0D07": ("Distance Unit", "Furlongs", "Miles/km")})
        assert not interpret(d).line.length.is_resolved


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

EXPECTED = {
    # zone: (reach ohm, R phase, R earth, delay s)
    "Z1": (1.43, 2.11, 7.02, 0.0),
    "Z2": (2.13, 3.14, 10.47, 0.3),
    "Z3": (4.48, 6.34, 17.19, 3.0),
    "Z4": (0.36, 6.34, 17.19, 3.0),
}


class TestZones:
    def test_zone_collection_is_not_limited_to_four(self, model):
        assert [z.zone_id for z in model.zones] == ["Z1", "Z2", "Z3", "Z4", "ZP"]

    @pytest.mark.parametrize("zone_id", EXPECTED)
    def test_reach_resistive_reach_and_delay(self, model, zone_id):
        reach, r_ph, r_g, delay = EXPECTED[zone_id]
        z = zone(model, zone_id)
        assert z.reach.value == ImpedanceValue(magnitude_ohm=reach, angle_deg=80.0)
        assert z.resistive_reach.phase_phase.value == r_ph
        assert z.resistive_reach.phase_earth.value == r_g
        assert z.common_timer_s.value == delay
        assert z.characteristic.type.value is CharacteristicType.QUADRILATERAL

    def test_phase_earth_resistive_reach_is_never_folded_into_phase_phase(self, model):
        for zone_id in EXPECTED:
            rr = zone(model, zone_id).resistive_reach
            assert rr.phase_phase.value != rr.phase_earth.value
            assert not rr.common.is_resolved  # no single "common" value is invented

    def test_reach_is_inferred_because_the_angle_comes_from_the_line_angle(self, model):
        r = zone(model, "Z1").reach
        assert r.provenance.status is MappingStatus.INFERRED
        assert {s.parameter_id for s in r.provenance.sources} == {"300A", "3005"}

    def test_reverse_resistive_reach_is_unresolved_not_defaulted(self, model):
        for z in model.zones:
            assert not z.resistive_reach.reverse.is_resolved

    def test_directions(self, model):
        assert zone(model, "Z1").direction.value is ZoneDirection.FORWARD
        assert zone(model, "Z1").direction.provenance.status is MappingStatus.INFERRED
        for zid in ("Z2", "Z3"):  # the scheme notes state it
            assert zone(model, zid).direction.value is ZoneDirection.FORWARD
            assert zone(model, zid).direction.provenance.status is MappingStatus.MAPPED
        assert zone(model, "Z4").direction.value is ZoneDirection.REVERSE
        assert zone(model, "ZP").direction.value is ZoneDirection.FORWARD  # 'Directional Fwd'

    def test_zones_1_to_3_are_inferred_enabled_and_need_confirmation(self, model):
        for zid in ("Z1", "Z2", "Z3"):
            s = zone(model, zid).status
            assert s.value is ZoneStatus.ENABLED and s.provenance.status is MappingStatus.INFERRED

    def test_zone_p_status_is_unresolved_because_the_bit_string_is_not_decoded(self, model):
        s = zone(model, "ZP").status
        assert not s.is_resolved and s.provenance.raw_value == "01010"
        assert any("bit string" in n for n in model.interpretation_notes)

    def test_zone_p_numbers_are_preserved(self, model):
        z = zone(model, "ZP")
        assert z.reach.value.magnitude_ohm == 0.001 and z.common_timer_s.value == 10.0

    def test_loop_enablement_is_inferred_from_fault_type(self, model):
        z = zone(model, "Z2")
        assert z.phase_phase_enabled.value is True and z.phase_earth_enabled.value is True
        assert z.phase_phase_enabled.provenance.status is MappingStatus.INFERRED

    def test_unrecognised_fault_type_leaves_loops_unresolved(self):
        d = make_doc(overrides={"3103": ("Fault Type", "Phase Only", "44x Fault Type")})
        z = zone(interpret(d), "Z1")
        assert not z.phase_phase_enabled.is_resolved and not z.phase_earth_enabled.is_resolved

    def test_z1_extension_reach_is_a_zone_1_parameter_not_a_zone(self, model):
        (p,) = zone(model, "Z1").characteristic.parameters
        assert p.name == "z1_extension_reach" and p.value.value == 0.001

    def test_tilts_are_kept_raw_per_zone_group(self, model):
        assert {u.setting_id for u in zone(model, "Z1").unresolved_settings} == {s.setting_id for s in model_doc_by_code("3026", "3027")}
        assert {u.setting_id for u in zone(model, "Z2").unresolved_settings} == {s.setting_id for s in model_doc_by_code("3028")}
        assert all(not z.tilt_deg.is_resolved for z in model.zones)

    def test_zones_3_and_4_share_the_same_source_settings(self, model):
        def ids(zid):
            z = zone(model, zid)
            return (
                {r.setting_id for r in z.resistive_reach.phase_earth.provenance.sources},
                {r.setting_id for r in z.compensation.k0_magnitude.provenance.sources},
            )

        assert ids("Z3") == ids("Z4")


def model_doc_by_code(*codes):
    return tuple(s for s in make_doc().settings if s.parameter_id in codes)


class TestCompensation:
    def test_source_native_magnitude_and_angle_are_preserved_unconverted(self, model):
        c = zone(model, "Z1").compensation
        assert c.kind is CompensationKind.K0_MAGNITUDE_ANGLE
        assert (c.k0_magnitude.value, c.k0_angle_deg.value) == (0.718, -11.5)
        assert not (c.kr.is_resolved or c.kx.is_resolved or c.re_rl.is_resolved or c.xe_xl.is_resolved)

    def test_compensation_angle_is_not_mistaken_for_the_characteristic_angle(self, model):
        z = zone(model, "Z1")
        assert z.reach.value.angle_deg == 80.0  # line angle
        assert z.compensation.k0_angle_deg.value == -11.5

    def test_compensation_is_inferred_so_it_asks_for_confirmation(self, model):
        c = zone(model, "Z2").compensation
        assert c.k0_magnitude.provenance.status is MappingStatus.INFERRED
        assert any("never converted" in n for n in c.k0_magnitude.provenance.notes)


# ---------------------------------------------------------------------------
# Zone 4 / defeated logic
# ---------------------------------------------------------------------------


class TestZone4Defeated:
    def test_numeric_settings_do_not_make_zone_4_active(self, model):
        z4 = zone(model, "Z4")
        assert z4.status.value is ZoneStatus.DISABLED
        # ...and the numbers are all still there.
        assert z4.reach.value.magnitude_ohm == 0.36 and z4.common_timer_s.value == 3.0
        assert z4.resistive_reach.phase_phase.value == 6.34

    def test_status_cites_the_notes_and_the_zone_status_setting(self, model):
        s = zone(model, "Z4").status
        assert s.provenance.status is MappingStatus.INFERRED
        assert "Zone 4" in s.provenance.raw_value
        parameter_ids = {r.parameter_id for r in s.provenance.sources}
        assert "3007" in parameter_ids
        assert len(s.provenance.sources) >= 2  # the defeat statement and the Zone Status setting

    def test_without_a_defeat_statement_zone_4_is_unresolved_not_enabled(self):
        z4 = zone(interpret(make_doc(notes=())), "Z4")
        assert not z4.status.is_resolved
        assert z4.reach.value.magnitude_ohm == 0.36

    @pytest.mark.parametrize("text", ["Zone 4 Not Defeated", "Zone 4 undefeated", "Zone 40 Defeated"])
    def test_negated_or_lookalike_wording_does_not_defeat_zone_4(self, text):
        assert not zone(interpret(make_doc(notes=(text,))), "Z4").status.is_resolved

    def test_to_defeat_wording_is_recognised(self):
        d = make_doc(notes=("To defeat Zone 4 for all P441 relay, connected to",))
        assert zone(interpret(d), "Z4").status.value is ZoneStatus.DISABLED

    def test_contradictory_statements_are_left_unresolved(self):
        d = make_doc(notes=("Zone 4 Defeated", "Zone 4 enabled"))
        m = interpret(d)
        assert not zone(m, "Z4").status.is_resolved
        assert any("both" in n for n in m.interpretation_notes)

    def test_function_disabled_disables_every_zone(self):
        d = make_doc(overrides={"090D": ("Dist. Protection", "Disabled", "Enabled/Disabled")})
        m = interpret(d)
        assert all(z.status.value is ZoneStatus.DISABLED for z in m.zones)

    def test_function_enable_missing_leaves_zones_1_to_3_unresolved(self):
        m = interpret(make_doc(drop=("090D",)))
        assert all(not zone(m, zid).status.is_resolved for zid in ("Z1", "Z2", "Z3"))


# ---------------------------------------------------------------------------
# Dangerous inputs
# ---------------------------------------------------------------------------


class TestDangerousInputs:
    def test_missing_setting_is_unresolved_never_defaulted(self):
        m = interpret(make_doc(drop=("300A",)))
        z1 = zone(m, "Z1")
        assert not z1.reach.is_resolved
        assert any("300A" in n and "not present" in n for n in m.interpretation_notes)
        assert z1.resistive_reach.phase_phase.value == 2.11  # the rest is unaffected

    def test_missing_timer_is_unresolved(self):
        assert not zone(interpret(make_doc(drop=("3014",))), "Z2").common_timer_s.is_resolved

    def test_identical_duplicates_are_mapped_with_a_note(self):
        d = make_doc(extra=(("300A", "Z1", "1.43", "0.001-500 /I1"),))
        z1 = zone(interpret(d), "Z1")
        assert z1.reach.value.magnitude_ohm == 1.43
        assert len(z1.reach.provenance.sources) == 3  # both duplicates + the line angle
        assert any("duplicate" in n for n in z1.reach.provenance.notes)

    def test_conflicting_duplicates_are_not_silently_resolved(self):
        d = make_doc(extra=(("300A", "Z1", "1.60", "0.001-500 /I1"),))
        m = interpret(d)
        z1 = zone(m, "Z1")
        assert not z1.reach.is_resolved
        assert len(z1.reach.provenance.sources) >= 2
        assert any("conflicting" in n for n in m.interpretation_notes)
        # Other zones are untouched.
        assert zone(m, "Z2").reach.value.magnitude_ohm == 2.13

    @pytest.mark.parametrize("value", ["abc", "1,43", "1.4.3", "NaN", "inf", "-", "1e3", "1.43 ohm"])
    def test_invalid_numeric_content_is_unresolved_and_kept_raw(self, value):
        d = make_doc(overrides={"300A": ("Z1", value, "0.001-500 /I1")})
        z1 = zone(interpret(d), "Z1")
        assert not z1.reach.is_resolved and z1.reach.provenance.raw_value.startswith(value)

    def test_value_outside_the_printed_range_is_unresolved(self):
        d = make_doc(overrides={"300A": ("Z1", "900", "0.001-500 /I1")})
        assert not zone(interpret(d), "Z1").reach.is_resolved
        d = make_doc(overrides={"300D": ("R1Ph", "-1", "0-400 /I1")})
        assert not zone(interpret(d), "Z1").resistive_reach.phase_phase.is_resolved

    @pytest.mark.parametrize(
        "code,name,value,printed",
        [
            ("300E", "tZ1", "300", "0-10000 ms"),  # milliseconds are not scaled to seconds
            ("300A", "Z1", "1.43", "0.001-500 kohm"),
            ("300A", "Z1", "1.43", "0.001-500 /I5"),
            ("3005", "Line Angle", "80", "-90 to +90 rad"),
        ],
    )
    def test_unknown_or_unconfirmed_units_are_unresolved_with_a_note(self, code, name, value, printed):
        m = interpret(make_doc(overrides={code: (name, value, printed)}))
        assert any(code in n or "unit" in n for n in m.interpretation_notes)
        z1 = zone(m, "Z1")
        affected = {"300E": z1.common_timer_s, "300A": z1.reach, "3005": m.line.line_angle_deg}[code]
        assert not affected.is_resolved

    @pytest.mark.parametrize("printed", ["0.001-500 ohm", "0.001-500 Ohms", "0.001-500 Ω"])
    def test_explicit_ohm_unit_is_accepted(self, printed):
        d = make_doc(overrides={"300A": ("Z1", "1.43", printed)})
        assert zone(interpret(d), "Z1").reach.value.magnitude_ohm == 1.43

    def test_i1_ohm_marker_needs_a_1a_ct_secondary(self):
        d = make_doc(overrides={"0A08": ("Phase CT Sec'y", "5", "1A/5A")})
        z1 = zone(interpret(d), "Z1")
        assert not z1.reach.is_resolved  # '/I1' with a 5 A secondary is not established as ohms

    def test_known_code_under_a_different_name_is_not_trusted(self):
        d = make_doc(overrides={"300A": ("Zone 9 Reach", "1.43", "0.001-500 /I1")})
        m = interpret(d)
        assert not zone(m, "Z1").reach.is_resolved
        assert any("differently" in n for n in m.interpretation_notes)

    def test_one_bad_value_does_not_take_down_its_neighbours(self):
        d = make_doc(overrides={"300C": ("R1G", "oops", "0-400 /I1")})
        rr = zone(interpret(d), "Z1").resistive_reach
        assert not rr.phase_earth.is_resolved and rr.phase_phase.value == 2.11

    def test_resistive_phase_earth_stays_separate_when_phase_phase_is_missing(self):
        rr = zone(interpret(make_doc(drop=("300D",))), "Z1").resistive_reach
        assert not rr.phase_phase.is_resolved and rr.phase_earth.value == 7.02
        assert not rr.common.is_resolved  # the earth value is never promoted to phase-phase

    def test_a_document_without_the_distance_section_yields_no_values_but_loses_nothing(self):
        bare = make_doc(overrides={}, drop=tuple(c for c in BASE if c.startswith("30")), notes=())
        m = interpret(bare)
        assert all(not z.reach.is_resolved for z in m.zones)
        assert m.referenced_setting_ids() >= {s.setting_id for s in bare.settings}


# ---------------------------------------------------------------------------
# Provenance audit
# ---------------------------------------------------------------------------


def all_sourced(model):
    return list(model.iter_sourced())


class TestProvenanceAudit:
    def test_every_resolved_value_names_the_profile_version_and_real_sources(self, model, doc):
        resolved = [(p, s) for p, s in all_sourced(model) if s.is_resolved]
        assert len(resolved) > 60
        for path, s in resolved:
            pv = s.provenance
            assert pv.status in (MappingStatus.MAPPED, MappingStatus.INFERRED), path
            assert (pv.profile_id, pv.profile_version) == (PROFILE_ID, PROFILE_VERSION), path
            assert pv.sources, path
            for ref in pv.sources:
                raw = doc.by_id(ref.setting_id)
                assert raw is not None, (path, ref)
                assert (ref.parameter_id, ref.parameter_name) == (raw.parameter_id, raw.name), (path, ref)
                assert ref.page == raw.location.page and f"line {raw.location.line}" in ref.location, (path, ref)

    def test_inferred_values_always_explain_why(self, model):
        for path, s in all_sourced(model):
            if s.provenance.status is MappingStatus.INFERRED:
                assert s.provenance.notes, path

    def test_mapped_values_cite_the_text_the_sheet_printed(self, model, doc):
        for path, s in all_sourced(model):
            pv = s.provenance
            if pv.status is MappingStatus.MAPPED and pv.raw_value and path.startswith(("transformers", "zones")):
                texts = [(doc.by_id(r.setting_id).raw_value or doc.by_id(r.setting_id).name) for r in pv.sources]
                assert any(t and t.strip() in pv.raw_value for t in texts), (path, pv.raw_value, texts)

    def test_traceability_chain_for_sampled_values(self, model, doc):
        """canonical value -> profile interpretation -> RawSetting -> page / location / source text."""
        cases = [
            (zone(model, "Z1").resistive_reach.phase_earth, 7.02, "300C", "R1G", "7.02"),
            (zone(model, "Z2").common_timer_s, 0.3, "3014", "tZ2", "0.3"),
            (model.transformers.vt_primary_v, 132000.0, "0A01", "Main VT Primary", "132000"),
            (model.line.line_angle_deg, 80.0, "3005", "Line Angle", "80"),
        ]
        for sourced, value, code, name, raw in cases:
            assert sourced.value == value
            assert sourced.provenance.raw_value == raw
            assert (sourced.provenance.profile_id, sourced.provenance.profile_version) == (PROFILE_ID, PROFILE_VERSION)
            (ref,) = sourced.provenance.sources
            entry = doc.by_id(ref.setting_id)
            assert (entry.parameter_id, entry.name, entry.raw_value) == (code, name, raw)
            assert ref.page == entry.location.page and ref.location == f"page {entry.location.page}, line {entry.location.line}"
            assert code in entry.source_text and raw in entry.source_text

    def test_no_source_setting_is_silently_discarded(self, model, doc):
        assert model.referenced_setting_ids() == {s.setting_id for s in doc.settings}

    def test_outside_scope_settings_are_retained_but_flagged(self, model, doc):
        (vts,) = [u for u in model.unmapped_settings if u.name == "VTS Time Delay"]
        assert vts.out_of_scope and vts.raw_value == "5"

    def test_distance_related_leftovers_are_not_marked_out_of_scope(self):
        d = make_doc(extra=(("3109", "Unblocking Logic", "None", None),))
        m = interpret(d)
        (u,) = [u for u in m.unmapped_settings if u.name == "Unblocking Logic"]
        assert not u.out_of_scope and PROFILE_VERSION in u.reason

    def test_unresolved_values_carry_no_engineering_value_but_keep_their_raw_text(self, model):
        for path, s in all_sourced(model):
            if not s.is_resolved:
                assert s.value is None and s.provenance.status is MappingStatus.UNRESOLVED, path

    def test_interpretation_is_deterministic_and_does_not_mutate_the_document(self, profile, doc):
        before = doc.settings
        assert profile.interpret(doc) == profile.interpret(doc)
        assert doc.settings == before


# ---------------------------------------------------------------------------
# Counts, summary and the existing engine adapter
# ---------------------------------------------------------------------------


class TestSummary:
    def test_counts_for_the_synthetic_sheet(self, model):
        mapped_n, inferred_n, unresolved_n, not_interpreted = count_model(model)
        # unresolved: firmware marker absent here, so 5 (positive-sequence line impedance,
        # Zone P status, and the three raw tilt settings).
        assert (mapped_n, inferred_n, unresolved_n) == (33, 36, 5)
        assert not_interpreted == 0

    def test_interpreted_summary_for_a_p441(self):
        reg = catalogue.build_registry()
        d = make_doc()
        s = summarize_interpretation(reg, d, reg.identify(d))
        assert s.status is InterpretationStatus.INTERPRETED
        assert (s.profile_id, s.profile_version, s.zone_count) == (PROFILE_ID, PROFILE_VERSION, 5)
        assert s.mapped_setting_count > 0 and s.inferred_setting_count > 0 and s.unresolved_setting_count > 0

    def test_other_relays_are_not_supported(self):
        reg = catalogue.build_registry()
        d = make_doc(scheme=("LZOP", "Scheme: 7SA6131_4AB02_3GA0"))
        s = summarize_interpretation(reg, d, reg.identify(d))
        assert s == type(s)(InterpretationStatus.NOT_SUPPORTED)

    def test_a_p441_with_no_distance_zones_is_incomplete_only_if_no_zone_exists(self):
        reg = catalogue.build_registry()

        class Empty(MicomP441Profile):
            def interpret(self, document):
                return replace(super().interpret(document), zones=())

        registry = type(reg)(profiles=(Empty(),), identification_descriptors=catalogue.IDENTIFICATION_DESCRIPTORS)
        d = make_doc()
        assert summarize_interpretation(registry, d, registry.identify(d)).status is InterpretationStatus.INCOMPLETE

    def test_a_crashing_profile_cannot_fail_the_upload(self, caplog):
        class Boom(MicomP441Profile):
            def interpret(self, document):
                raise RuntimeError("secret setting value 1.43")

        reg = type(catalogue.build_registry())(profiles=(Boom(),), identification_descriptors=catalogue.IDENTIFICATION_DESCRIPTORS)
        d = make_doc()
        with caplog.at_level("WARNING"):
            s = summarize_interpretation(reg, d, reg.identify(d))
        assert s.status is InterpretationStatus.FAILED and s.zone_count == 0
        assert "1.43" not in caplog.text and "secret" not in caplog.text  # class name only
        assert all("1.43" not in w for w in s.warnings)

    def test_warnings_carry_no_document_values(self):
        reg = catalogue.build_registry()
        d = make_doc(overrides={"300A": ("Z1", "9.87", "0.001-500 /I1")}, extra=(("300B", "Z1X", "6.54", "0.001-500 /I1"),))
        warnings = summarize_interpretation(reg, d, reg.identify(d)).warnings
        assert warnings and not any(v in w for w in warnings for v in ("9.87", "6.54", "1.43"))


class TestEngineAdapterCompatibility:
    """The canonical model runs through the existing adapter unchanged."""

    def test_the_adapter_reports_what_it_cannot_yet_draw_and_why(self, model):
        a = adapt_to_engine(model, engine_basis="secondary")
        assert not a.supported
        codes = {(r.code, r.zone_id) for r in a.reasons}
        assert (UnsupportedCode.ZONE_STATUS_UNRESOLVED, "ZP") in codes  # Zone P: status not established
        for zid in ("Z1", "Z2", "Z3"):
            assert (UnsupportedCode.RESISTIVE_REACH_UNRESOLVED, zid) in codes  # no left-hand reach on the sheet
        assert all(r.zone_id != "Z4" for r in a.reasons)  # the defeated zone needs no geometry

    def test_phase_earth_and_compensation_are_warned_as_ignored(self, model):
        a = adapt_to_engine(model, engine_basis="secondary")
        assert any("phase-earth operation is preserved" in w and w.startswith("Z1") for w in a.warnings)
        assert any("residual compensation is preserved" in w and w.startswith("Z2") for w in a.warnings)

    def test_basis_mismatch_is_refused_not_converted(self, model):
        a = adapt_to_engine(model, engine_basis="primary")
        assert UnsupportedCode.BASIS_MISMATCH in {r.code for r in a.reasons}

    def test_engine_input_uses_phase_phase_values_only_once_the_gaps_are_filled(self, model):
        """Fill ONLY the two things the sheet does not state (a left-hand
        resistive reach and Zone P's status) to prove the rest of the mapping
        reaches the engine faithfully -- and that PP, not PE, resistance does."""

        def fill(z):
            rr = replace(z.resistive_reach, reverse=mapped(1.0, sources=z.reach.provenance.sources, profile_id="t", profile_version="t"))
            status = z.status
            if z.zone_id == "ZP":
                status = mapped(ZoneStatus.DISABLED, sources=z.reach.provenance.sources, profile_id="t", profile_version="t")
            return replace(z, resistive_reach=rr, status=status)

        filled = replace(model, zones=tuple(fill(z) for z in model.zones))
        a = adapt_to_engine(filled, engine_basis="secondary")
        assert a.supported, a.reasons
        assert a.characteristic == "quadrilateral"
        z1, z2, z3, z4, zp = a.zones
        assert a.zone_ids == ("Z1", "Z2", "Z3", "Z4", "ZP") and zp.enabled is False
        assert (z1.reactive_reach_ohm, z1.resistive_reach_forward_ohm, z1.delay_s, z1.characteristic_angle_deg) == (1.43, 2.11, 0.0, 80.0)
        assert (z2.reactive_reach_ohm, z2.resistive_reach_forward_ohm, z2.delay_s) == (2.13, 3.14, 0.3)
        assert (z3.reactive_reach_ohm, z3.resistive_reach_forward_ohm, z3.delay_s) == (4.48, 6.34, 3.0)
        assert z4.enabled is False
        assert all(z.resistive_reach_forward_ohm not in (7.02, 10.47, 17.19) for z in (z1, z2, z3))


# ---------------------------------------------------------------------------
# Architecture guards
# ---------------------------------------------------------------------------

_P441_NAMES = re.compile(r"p441|micom", re.IGNORECASE)
_ALLOWED = {
    APP / "relay_profiles" / "micom_p441.py",
    APP / "relay_profiles" / "identification_catalogue.py",  # registers the profile and describes the relay
}


class TestIsolation:
    def test_p441_knowledge_lives_only_in_the_profile_and_the_catalogue(self):
        offenders = []
        for path in APP.rglob("*.py"):
            if path in _ALLOWED:
                continue
            hit = _P441_NAMES.search(path.read_text(encoding="utf-8"))
            if hit:
                offenders.append(f"{path.relative_to(APP)}: {hit.group(0)}")
        assert not offenders, offenders

    def test_profile_does_not_touch_persistence_or_the_engine(self):
        text = (APP / "relay_profiles" / "micom_p441.py").read_text(encoding="utf-8")
        for forbidden in ("app.storage", "sqlalchemy", "fastapi", "app.services", "distance_protection", "open(", "pypdf"):
            assert forbidden not in text

    def test_the_p441_profile_is_registered_once_beside_the_other_interpretation_profiles(self):
        reg = catalogue.build_registry()
        ids = [p.profile_id for p in reg._profiles]
        assert ids.count(PROFILE_ID) == 1
        assert set(ids) == {PROFILE_ID, "siemens-7sa511", "hitachi-red670"}  # Slice 11 added the 7SA511, Slice 12 the RED670


# ---------------------------------------------------------------------------
# Real owner sample (not committed): RELAY_SAMPLE_PDF_DIR
# ---------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
needs_samples = pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")
OTHER_SAMPLES = ["7sa613", "7sl87", "grl200", "grz100", "rcs", "rel511", "rel670", "lfzp", "relz100"]  # (the RED670 has its own profile since Slice 12)


def real(name):
    from app.services.relay_pdf_extractor import extract_pdf

    path = Path(SAMPLE_DIR) / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"{path.name} not available")
    return extract_pdf(path.read_bytes()).document


@pytest.fixture(scope="module")
def rdoc():
    return real("p441")


@pytest.fixture(scope="module")
def rmodel(rdoc):
    reg = catalogue.build_registry()
    ident = reg.identify(rdoc)
    assert ident.status is IdentificationStatus.IDENTIFIED and ident.profile_id == PROFILE_ID
    return reg.profile_for(ident).interpret(rdoc)


@needs_samples
class TestRealP441Sample:
    def test_identified_and_metadata(self, rmodel):
        m = rmodel.metadata
        assert (m.manufacturer.value, m.model.value, m.profile_version) == ("Schneider Electric", "P441", PROFILE_VERSION)
        assert m.scheme_name.value == "SE_P441?A1???038?JE"

    def test_ct_vt_and_basis(self, rmodel):
        t = rmodel.transformers
        assert (t.ct_primary_a.value, t.ct_secondary_a.value, t.vt_primary_v.value, t.vt_secondary_v.value) == (1200.0, 1.0, 132000.0, 110.0)
        assert t.setting_basis.value is SettingBasis.SECONDARY

    def test_line(self, rmodel):
        assert (rmodel.line.length.value, rmodel.line.length_unit.value, rmodel.line.line_angle_deg.value) == (7.03, "km", 80.0)
        assert rmodel.line.extras[0].value.value == 2.0

    @pytest.mark.parametrize("zone_id", EXPECTED)
    def test_zone_reach_resistive_reach_and_timer(self, rmodel, zone_id):
        reach, r_ph, r_g, delay = EXPECTED[zone_id]
        z = zone(rmodel, zone_id)
        assert z.reach.value.magnitude_ohm == reach
        assert (z.resistive_reach.phase_phase.value, z.resistive_reach.phase_earth.value) == (r_ph, r_g)
        assert z.common_timer_s.value == delay

    def test_compensation_is_the_residual_pair_not_a_characteristic_angle(self, rmodel):
        c = zone(rmodel, "Z1").compensation
        assert (c.k0_magnitude.value, c.k0_angle_deg.value) == (0.718, -11.5)
        assert zone(rmodel, "Z1").reach.value.angle_deg == 80.0

    def test_zone_4_is_defeated_but_keeps_its_numbers(self, rmodel):
        z4 = zone(rmodel, "Z4")
        assert z4.status.value is ZoneStatus.DISABLED
        assert (z4.reach.value.magnitude_ohm, z4.common_timer_s.value) == (0.36, 3.0)

    def test_every_value_traces_to_a_raw_entry_and_nothing_is_discarded(self, rmodel, rdoc):
        assert rmodel.referenced_setting_ids() == {s.setting_id for s in rdoc.settings}
        for path, s in rmodel.iter_sourced():
            for ref in s.provenance.sources:
                raw = rdoc.by_id(ref.setting_id)
                assert raw is not None and ref.page == raw.location.page, path

    def test_interpretation_is_deterministic(self, rdoc):
        assert interpret(rdoc) == interpret(rdoc)

    def test_zone_4_status_cites_every_defeat_statement(self, rmodel):
        # 'To defeat Zone 4...', 'Zone 4 Defeated', the 3007 revision record and the 3007 setting itself.
        assert len(zone(rmodel, "Z4").status.provenance.sources) >= 4

    def test_adapter_verdict(self, rmodel):
        a = adapt_to_engine(rmodel, engine_basis="secondary")
        assert not a.supported
        assert {r.code for r in a.reasons} == {UnsupportedCode.ZONE_STATUS_UNRESOLVED, UnsupportedCode.RESISTIVE_REACH_UNRESOLVED}

    def test_counts(self, rmodel):
        mapped_n, inferred_n, unresolved_n, not_interpreted = count_model(rmodel)
        assert (mapped_n, inferred_n, unresolved_n) == (33, 36, 6)
        assert not_interpreted == 31


@needs_samples
class TestRealOtherFamiliesStayIdentificationOnly:
    @pytest.mark.parametrize("name", OTHER_SAMPLES)
    def test_not_routed_to_the_p441_profile(self, name):
        reg = catalogue.build_registry()
        d = real(name)
        ident = reg.identify(d)
        assert ident.profile_id != PROFILE_ID
        assert reg.profile_for(ident) is None
        assert summarize_interpretation(reg, d, ident).status is InterpretationStatus.NOT_SUPPORTED
        assert MicomP441Profile().match(d).level is MatchLevel.NONE
