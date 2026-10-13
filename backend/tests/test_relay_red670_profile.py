"""Slice 12 -- Hitachi Energy RED670 interpretation profile (``hitachi-red670-v1``).

Synthetic RED670-shaped sheets (built as real PDFs and read through the real extractor) cover the
rules; the owner's real sheet is exercised at the bottom only when ``RELAY_SAMPLE_PDF_DIR`` points at
a folder holding ``red670.pdf`` (never committed).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.domain.relay_import.canonical_distance import (
    CharacteristicType,
    GeometryMode,
    SettingBasis,
    SourceNoteKind,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.identification import IdentificationStatus
from app.domain.relay_import.provenance import MappingStatus, UnresolvedCause
from app.relay_profiles import hitachi_red670 as red670
from app.relay_profiles import identification_catalogue as catalogue
from tests.relay_red670_fixtures import default_sections, make_doc, zone_rows

PROFILE_ID = "hitachi-red670"


def interpret(doc):
    reg = catalogue.build_registry()
    ident = reg.identify(doc)
    assert ident.status is IdentificationStatus.IDENTIFIED and ident.profile_id == PROFILE_ID
    return reg.profile_for(ident).interpret(doc)


@pytest.fixture(scope="module")
def doc():
    return make_doc()


@pytest.fixture(scope="module")
def model(doc):
    return interpret(doc)


def status(sourced) -> MappingStatus:
    return sourced.provenance.status


def zone(model, zid):
    return model.zone(zid)


def sections_with(zone_overrides: dict[int, dict]):
    """The default sheet with some zone sections regenerated with different arguments."""
    out = []
    for label, rows in default_sections():
        n = next((k for k in zone_overrides if label.endswith(f"ZMQPDIS:{k}")), None)
        out.append((label, zone_rows(n, **zone_overrides[n]) if n else rows))
    return out


# ---------------------------------------------------------------------------
# 1-2. Identification and metadata
# ---------------------------------------------------------------------------


class TestIdentificationAndMetadata:
    def test_identified_from_the_scheme_field(self, doc):
        ident = catalogue.build_registry().identify(doc)
        assert (ident.manufacturer, ident.relay_family, ident.model) == ("Hitachi Energy", "Relion 670", "RED670")
        assert ident.confidence.value == "high" and ident.profile_id == PROFILE_ID

    def test_only_a_red670_identification_selects_the_profile(self):
        # a REL670 scheme is a different catalogued line: no RED670 interpretation
        doc = make_doc(header=(("LZOP: x", "Scheme: REL670_V1.2_21"), ("Utility ID: 1", "Active Group: g")))
        reg = catalogue.build_registry()
        ident = reg.identify(doc)
        assert ident.profile_id == "hitachi-rel670" and reg.profile_for(ident) is None
        assert red670.HitachiRed670Profile().match(doc).level.name == "NONE"

    def test_metadata(self, model):
        m = model.metadata
        assert (m.manufacturer.value, m.family.value, m.model.value) == ("Hitachi Energy", "Relion 670", "RED670")
        assert m.scheme_name.value == "RED670_V1.2_21_F11L" and m.version.value == "V1.2"
        assert m.active_setting_group.value == "SET-TEST-R1"
        assert (m.profile_id, m.profile_version) == (PROFILE_ID, "hitachi-red670-v1")
        # the manufacturer is not in the sheet: normalised from the catalogue, and says so
        assert any("not named in the document" in n for n in m.manufacturer.provenance.notes)

    def test_version_is_unresolved_without_a_marker(self):
        doc = make_doc(header=(("LZOP: x", "Scheme: RED670_21"), ("Utility ID: 1", "Active Group: g")))
        assert not interpret(doc).metadata.version.is_resolved


# ---------------------------------------------------------------------------
# 3-5. CT, VT, basis
# ---------------------------------------------------------------------------


class TestTransformers:
    def test_ct_from_the_phase_current_channels_only(self, model):
        t = model.transformers
        assert (t.ct_primary_a.value, t.ct_secondary_a.value) == (1200.0, 1.0)
        assert status(t.ct_primary_a) is MappingStatus.MAPPED
        # CH1-CH3 only: the residual channel (CH4_IN) and the unused defaults (99999) are not read
        assert {s.parameter_name for s in t.ct_primary_a.provenance.sources} == {"CTprim1", "CTprim2", "CTprim3"}

    def test_vt_unit_is_an_assumption_and_kv_becomes_volts(self, model):
        t = model.transformers
        assert (t.vt_primary_v.value, t.vt_secondary_v.value) == (220000.0, 110.0)
        assert status(t.vt_primary_v) is MappingStatus.INFERRED and status(t.vt_secondary_v) is MappingStatus.INFERRED
        assert {s.parameter_name for s in t.vt_primary_v.provenance.sources} == {"VTprim7", "VTprim8", "VTprim9"}
        assert any("prints no unit" in n for n in t.vt_primary_v.provenance.notes)

    def test_bases_come_from_the_zones_in_service(self, model):
        t = model.transformers
        assert t.current_base_a.value == 1200.0 and status(t.current_base_a) is MappingStatus.MAPPED
        assert t.voltage_base_v.value == 220000.0 and status(t.voltage_base_v) is MappingStatus.INFERRED
        # Zone 4 is disabled: its placeholder IBase = 1 / UBase = 0.05 are not a conflict and not cited
        cited = {s.parameter_name for s in t.current_base_a.provenance.sources}
        assert "ZM04-:IBase" not in cited and cited == {"ZM01-:IBase", "ZM02-:IBase", "ZM03-:IBase"}

    def test_basis_is_primary_and_an_assumption_never_taken_from_magnitude(self, model):
        basis = model.transformers.setting_basis
        assert basis.value is SettingBasis.PRIMARY and status(basis) is MappingStatus.INFERRED
        assert "primary ohms" in " ".join(basis.provenance.notes)

    def test_phase_channels_that_disagree_are_a_conflict_not_a_pick(self):
        doc = make_doc(overrides={"CTprim2": ("1500", "1-99999")})
        ct = interpret(doc).transformers.ct_primary_a
        assert not ct.is_resolved and ct.provenance.cause is UnresolvedCause.CONFLICT

    def test_a_missing_phase_channel_is_not_filled_from_another(self):
        doc = make_doc(drop=("NAMECH3", "ChannelType3", "CTsec3", "CTprim3"))
        assert not interpret(doc).transformers.ct_primary_a.is_resolved


# ---------------------------------------------------------------------------
# 6-9. Zones: count, activation, direction, characteristic
# ---------------------------------------------------------------------------


class TestZonesAndActivation:
    def test_zone_count_follows_the_function_instances(self, model):
        assert [z.zone_id for z in model.zones] == ["Z1", "Z2", "Z3", "Z4"]
        assert [z.name for z in model.zones] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4"]

    def test_any_number_of_instances_is_read(self):
        sections = default_sections()
        sections.insert(5, ("IMP_PROT/DistanceZones/ZMQPDIS:5", zone_rows(5, x1="30", direction="Reverse")))
        m = interpret(make_doc(sections=sections))
        assert [z.zone_id for z in m.zones] == ["Z1", "Z2", "Z3", "Z4", "Z5"]
        assert zone(m, "Z5").direction.value is ZoneDirection.REVERSE

    def test_activation_is_read_from_the_zones_own_parameters(self, model):
        for zid in ("Z1", "Z2", "Z3"):
            z = zone(model, zid)
            assert z.status.value is ZoneStatus.ENABLED and status(z.status) is MappingStatus.MAPPED
            assert {s.parameter_name for s in z.status.provenance.sources} == {f"ZM0{zid[1]}-:Operation", f"ZM0{zid[1]}-:OperationDir"}
        z4 = zone(model, "Z4")
        assert z4.status.value is ZoneStatus.DISABLED and status(z4.status) is MappingStatus.MAPPED

    def test_operation_off_or_direction_off_each_disable_a_zone(self):
        m = interpret(make_doc(sections=sections_with({1: dict(operation="OFF"), 2: dict(direction="Off")})))
        assert zone(m, "Z1").status.value is ZoneStatus.DISABLED
        assert zone(m, "Z2").status.value is ZoneStatus.DISABLED

    def test_unreadable_activation_stays_unresolved(self):
        m = interpret(make_doc(overrides={"ZM01-:Operation": ("MAYBE", ON_OFF)}))
        z = zone(m, "Z1")
        assert not z.status.is_resolved and z.status.provenance.cause is UnresolvedCause.UNSUPPORTED

    def test_a_missing_activation_parameter_is_missing_not_enabled(self):
        m = interpret(make_doc(drop=("ZM01-:Operation",)))
        z = zone(m, "Z1")
        assert not z.status.is_resolved and z.status.provenance.cause is UnresolvedCause.MISSING

    def test_the_scheme_notes_never_decide_a_state(self):
        # no activation parameters at all: the "Zone 4 Inactive" note must not disable Zone 4
        m = interpret(make_doc(drop=("ZM04-:Operation", "ZM04-:OperationDir")))
        assert not zone(m, "Z4").status.is_resolved

    def test_direction_is_per_zone_and_covers_every_option(self):
        sections = sections_with({1: dict(direction="Forward"), 2: dict(direction="Reverse"), 3: dict(direction="Non-dir")})
        m = interpret(make_doc(sections=sections))
        assert [zone(m, z).direction.value for z in ("Z1", "Z2", "Z3", "Z4")] == [
            ZoneDirection.FORWARD, ZoneDirection.REVERSE, ZoneDirection.NON_DIRECTIONAL, ZoneDirection.INACTIVE,
        ]
        assert all(status(zone(m, z).direction) is MappingStatus.MAPPED for z in ("Z1", "Z2", "Z3", "Z4"))

    def test_the_characteristic_is_a_labelled_assumption_citing_the_function_block(self, model):
        c = zone(model, "Z1").characteristic
        assert c.type.value is CharacteristicType.QUADRILATERAL and status(c.type) is MappingStatus.INFERRED
        assert c.geometry_mode is GeometryMode.EXPLICIT_RX
        cited = {s.parameter_name for s in c.type.provenance.sources}
        assert "IMP_PROT/DistanceZones/ZMQPDIS:1" in cited and "ZM01-:X1" in cited
        assert "does not name the characteristic" in " ".join(c.type.provenance.notes)

    def test_without_the_function_block_heading_the_characteristic_is_not_claimed(self):
        sections = [(label.replace("ZMQPDIS:1", "SOMETHING:1"), rows) for label, rows in default_sections()]
        m = interpret(make_doc(sections=sections))
        assert not zone(m, "Z1").characteristic.type.is_resolved


# ---------------------------------------------------------------------------
# 10-13. Geometry, PP / PE, timers, compensation
# ---------------------------------------------------------------------------


class TestGeometryLoopsTimersCompensation:
    def test_geometry_is_explicit_rx_with_no_angle_and_no_polar_reach(self, model):
        for z in model.zones:
            assert z.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
            assert not z.reach.is_resolved and not z.tilt_deg.is_resolved
        z1 = zone(model, "Z1")
        assert z1.x_reach_ohm.value == 6.0 and status(z1.x_reach_ohm) is MappingStatus.MAPPED
        assert z1.x_reach_ohm.provenance.sources[0].parameter_name == "ZM01-:X1"

    def test_phase_phase_and_phase_earth_resistive_reaches_stay_distinct(self, model):
        rr = zone(model, "Z2").resistive_reach
        assert (rr.phase_phase.value, rr.phase_earth.value) == (10.0, 20.0)
        assert rr.phase_phase.provenance.sources[0].parameter_name == "ZM02-:RFPP"
        assert rr.phase_earth.provenance.sources[0].parameter_name == "ZM02-:RFPE"
        assert not rr.common.is_resolved
        # the per-loop reading is an assumption with its reason; the value is not scaled
        assert status(rr.phase_phase) is MappingStatus.INFERRED and "ohm/loop" in " ".join(rr.phase_phase.provenance.notes)

    def test_the_left_resistive_reach_is_missing_and_cites_the_directional_element(self, model):
        rev = zone(model, "Z1").resistive_reach.reverse
        assert not rev.is_resolved and rev.provenance.cause is UnresolvedCause.MISSING
        assert {s.parameter_name for s in rev.provenance.sources} == {"ZD01-:ArgDir", "ZD01-:ArgNegRes"}
        assert "directional element" in " ".join(rev.provenance.notes)

    def test_loop_enables_are_per_zone_and_per_loop(self):
        m = interpret(make_doc(sections=sections_with({2: dict(pe="OFF")})))
        z2 = zone(m, "Z2")
        assert z2.phase_phase_enabled.value is True and z2.phase_earth_enabled.value is False
        assert zone(m, "Z1").phase_earth_enabled.value is True

    def test_timers_come_from_the_actual_setting_fields(self, model):
        for zid, value in (("Z1", 0.15), ("Z2", 0.45), ("Z3", 3.0)):
            z = zone(model, zid)
            assert z.phase_timer_s.value == value and z.earth_timer_s.value == value
            assert status(z.phase_timer_s) is MappingStatus.MAPPED and not z.common_timer_s.is_resolved
            names = {s.parameter_name for s in z.phase_timer_s.provenance.sources}
            assert names == {f"ZM0{zid[1]}-:Timer tPP", f"ZM0{zid[1]}-:tPP"}

    def test_pp_and_pe_timers_are_independent(self):
        m = interpret(make_doc(overrides={"ZM01-:tPE": ("0.3", "0-60")}))
        z1 = zone(m, "Z1")
        assert (z1.phase_timer_s.value, z1.earth_timer_s.value) == (0.15, 0.3)

    def test_a_timer_that_is_switched_off_is_missing_and_keeps_the_raw_value(self):
        m = interpret(make_doc(sections=sections_with({1: dict(timer_gate="OFF")})))
        t = zone(m, "Z1").phase_timer_s
        assert not t.is_resolved and t.provenance.cause is UnresolvedCause.MISSING and t.provenance.raw_value == "0.15"
        assert "switch is OFF" in " ".join(t.provenance.notes)

    def test_notes_are_not_used_as_timers(self):
        # the page-end note says 0.45 s; the setting field says 0.8 s -- the field wins, the note stays a note
        m = interpret(make_doc(overrides={"ZM02-:tPP": ("0.8", "0-60")}))
        z2 = zone(m, "Z2")
        assert z2.phase_timer_s.value == 0.8
        assert [n.value_text for n in z2.source_notes] == ["0.45 s"]

    def test_a_missing_timer_field_stays_missing_even_though_a_note_states_one(self):
        m = interpret(make_doc(drop=("ZM03-:tPP", "ZM03-:Timer tPP")))
        z3 = zone(m, "Z3")
        assert not z3.phase_timer_s.is_resolved and z3.source_notes[0].value_text == "3 s"

    def test_residual_compensation_is_not_invented(self, model):
        z1 = zone(model, "Z1")
        assert z1.compensation is None
        zr = z1.zero_sequence_reach
        assert zr.value.r_ohm == 5.0 and zr.value.x_ohm == 18.0 and status(zr) is MappingStatus.MAPPED
        assert {s.parameter_name for s in zr.provenance.sources} == {"ZM01-:R0", "ZM01-:X0"}
        r1 = z1.characteristic.parameters[0]
        assert r1.name == "positive_sequence_resistance_r1" and r1.value.value == 1.0
        assert any("Earth-fault compensation" in n for n in model.interpretation_notes)


# ---------------------------------------------------------------------------
# 14. Provenance, notes and completeness
# ---------------------------------------------------------------------------


class TestProvenanceAndCompleteness:
    def test_every_value_cites_page_line_and_profile(self, model):
        for path, s in model.iter_sourced():
            if s.provenance.status is MappingStatus.UNRESOLVED:
                continue
            assert s.provenance.profile_id == PROFILE_ID and s.provenance.profile_version == "hitachi-red670-v1", path
            assert s.provenance.sources, path
            assert all(ref.page and ref.location for ref in s.provenance.sources), path

    def test_source_notes_are_document_notes_with_their_source(self, model):
        z4 = zone(model, "Z4")
        (note,) = z4.source_notes
        assert note.kind is SourceNoteKind.PROPOSED_REQUIREMENT
        assert (note.subject, note.value_text) == ("status", "Inactive (out of service)")
        assert note.sources and note.sources[0].parameter_name == "Zone 4"
        z1 = zone(model, "Z1")
        assert (z1.source_notes[0].subject, z1.source_notes[0].value_text) == ("timer", "0.15 s")

    def test_every_raw_setting_is_accounted_for(self, doc, model):
        assert {s.setting_id for s in doc.settings} <= model.referenced_setting_ids()

    def test_distance_related_leftovers_are_open_and_the_rest_out_of_scope(self, model):
        by_name = {u.name: u for u in model.unmapped_settings}
        assert by_name["ZM01-:IMinOpPP"].out_of_scope is False and "not interpreted" in by_name["ZM01-:IMinOpPP"].reason
        assert by_name["IEC61850:Operation"].out_of_scope is True
        assert by_name["NAMECH4"].out_of_scope is True

    def test_the_line_is_read_from_the_fault_locator_with_honest_gaps(self, model):
        line = model.line
        assert line.length.value == 30.0 and status(line.length) is MappingStatus.MAPPED
        assert not line.length_unit.is_resolved  # km or miles: the sheet prints neither
        z1 = line.positive_sequence_impedance.value
        assert (z1.r_ohm, z1.x_ohm) == (1.2, 9.0) and status(line.positive_sequence_impedance) is MappingStatus.INFERRED
        z0 = line.zero_sequence_impedance.value
        assert (z0.r_ohm, z0.x_ohm) == (8.0, 26.0)
        assert not line.line_angle_deg.is_resolved  # not stated, not derived from R1L / X1L

    def test_unreadable_and_out_of_range_values_stay_unresolved(self):
        m = interpret(make_doc(overrides={"ZM01-:X1": ("6,5", "0.1-3000"), "ZM02-:X1": ("9999", "0.1-3000")}))
        x1, x2 = zone(m, "Z1").x_reach_ohm, zone(m, "Z2").x_reach_ohm
        assert not x1.is_resolved and x1.provenance.cause is UnresolvedCause.UNREADABLE and x1.provenance.raw_value == "6,5"
        assert not x2.is_resolved and x2.provenance.cause is UnresolvedCause.CONFLICT

    def test_conflicting_duplicates_are_not_resolved(self):
        m = interpret(make_doc(extra=(("ZM01-:X1", "7", "0.1-3000"),)))
        x = zone(m, "Z1").x_reach_ohm
        assert not x.is_resolved and x.provenance.cause is UnresolvedCause.CONFLICT

    def test_interpretation_is_deterministic(self, doc):
        assert interpret(doc) == interpret(doc)


# ---------------------------------------------------------------------------
# Real owner sample (not committed): RELAY_SAMPLE_PDF_DIR
# ---------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
needs_sample = pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")


def real_doc():
    from app.services.relay_pdf_extractor import extract_pdf

    path = Path(SAMPLE_DIR) / "red670.pdf"
    if not path.exists():
        pytest.skip("red670.pdf not available")
    return extract_pdf(path.read_bytes()).document


@pytest.fixture(scope="module")
def rdoc():
    return real_doc()


@pytest.fixture(scope="module")
def rmodel(rdoc):
    return interpret(rdoc)


@needs_sample
class TestRealSample:
    def test_identified(self, rdoc):
        ident = catalogue.build_registry().identify(rdoc)
        assert (ident.manufacturer, ident.relay_family, ident.model) == ("Hitachi Energy", "Relion 670", "RED670")
        assert ident.confidence.value == "high"

    def test_metadata_ct_vt_and_basis(self, rmodel):
        m, t = rmodel.metadata, rmodel.transformers
        assert (m.model.value, m.version.value, m.scheme_name.value) == ("RED670", "V1.2", "RED670_V1.2_21_F11L")
        assert (t.ct_primary_a.value, t.ct_secondary_a.value) == (1500.0, 1.0)
        assert (t.vt_primary_v.value, t.vt_secondary_v.value) == (275000.0, 110.0)
        assert (t.current_base_a.value, t.voltage_base_v.value) == (1500.0, 275000.0)
        assert t.setting_basis.value is SettingBasis.PRIMARY and status(t.setting_basis) is MappingStatus.INFERRED

    def test_four_zones_with_the_sheets_own_activation(self, rmodel):
        assert [z.zone_id for z in rmodel.zones] == ["Z1", "Z2", "Z3", "Z4"]
        assert [z.status.value for z in rmodel.zones] == [ZoneStatus.ENABLED] * 3 + [ZoneStatus.DISABLED]
        assert [z.direction.value for z in rmodel.zones] == [ZoneDirection.FORWARD] * 3 + [ZoneDirection.INACTIVE]

    def test_reaches_resistive_reaches_and_timers(self, rmodel):
        expected = {  # X1, RFPP, RFPE, tPP, tPE
            "Z1": (7.87, 7.79, 20.2, 0.15, 0.15),
            "Z2": (13.63, 11.67, 25.84, 0.45, 0.45),
            "Z3": (24.97, 21.91, 33.83, 3.0, 3.0),
        }
        for zid, (x, pp, pe, tpp, tpe) in expected.items():
            z = zone(rmodel, zid)
            assert (z.x_reach_ohm.value, z.resistive_reach.phase_phase.value, z.resistive_reach.phase_earth.value) == (x, pp, pe)
            assert (z.phase_timer_s.value, z.earth_timer_s.value) == (tpp, tpe)
            assert z.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
            assert not z.resistive_reach.reverse.is_resolved

    def test_zone_4_timers_are_missing_because_its_timer_switches_are_off(self, rmodel):
        z4 = zone(rmodel, "Z4")
        assert not z4.phase_timer_s.is_resolved and not z4.earth_timer_s.is_resolved

    def test_the_page_16_notes_are_notes_and_every_setting_is_accounted_for(self, rdoc, rmodel):
        assert [n.value_text for n in zone(rmodel, "Z1").source_notes] == ["0.15 s"]
        assert zone(rmodel, "Z4").source_notes[0].subject == "status"
        assert {s.setting_id for s in rdoc.settings} <= rmodel.referenced_setting_ids()

    def test_line_data(self, rmodel):
        assert rmodel.line.length.value == 36.5
        z1 = rmodel.line.positive_sequence_impedance.value
        assert (z1.r_ohm, z1.x_ohm) == (1.411, 10.488)


ON_OFF = "OFF/ON"
