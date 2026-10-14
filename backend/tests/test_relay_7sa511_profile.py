"""Siemens SIPROTEC 7SA511 interpretation profile (Relay Import Slice 11).

Synthetic-sheet tests run everywhere (the sheet is built as a real PDF and read through
the real extractor). The owner's real sheet is never committed; its class at the bottom runs
only when ``RELAY_SAMPLE_PDF_DIR`` points at a folder holding ``7sa511.pdf``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.domain.relay_import.canonical_distance import (
    CharacteristicType,
    CompensationKind,
    GeometryMode,
    ImpedanceValue,
    SettingBasis,
    SourceNoteKind,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.defeated_zone import DEFEATED_ZONE_REASON, infer_defeated_zones
from app.domain.relay_import.engine_adapter import adapt_to_engine
from app.domain.relay_import.identification import IdentificationStatus
from app.domain.relay_import.profile import MatchLevel
from app.domain.relay_import.provenance import MappingStatus, UnresolvedCause
from app.relay_profiles import identification_catalogue as catalogue
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.relay_profiles.siemens_7sa511 import (
    PROFILE_ID,
    PROFILE_VERSION,
    Siemens7SA511Profile,
)
from app.services.relay_interpretation_summary import InterpretationStatus, summarize_interpretation
from tests.relay_7sa511_fixtures import BASE, FINITE_TIMERS, INFINITY_IN_VALUE_COLUMN, make_doc

APP = Path(__file__).resolve().parents[1] / "app"
SECONDS = ("phase_timer_s", "earth_timer_s", "common_timer_s")
ZONE_IDS = ["Z1", "Z2", "Z3", "Z4", "Z1B", "Z1L"]


def zone(model, zone_id):
    return model.zone(zone_id)


def interpret(**kw):
    return Siemens7SA511Profile().interpret(make_doc(**kw))


@pytest.fixture(scope="module")
def doc():
    return make_doc()


@pytest.fixture(scope="module")
def model(doc):
    return Siemens7SA511Profile().interpret(doc)


@pytest.fixture(scope="module")
def finite():
    return interpret(overrides=FINITE_TIMERS)


# ---------------------------------------------------------------------------
# 1. identification and routing (the existing framework; thresholds untouched)
# ---------------------------------------------------------------------------


class TestIdentificationAndRouting:
    def test_identified_as_siemens_7sa511_by_the_existing_framework(self, doc):
        ident = catalogue.build_registry().identify(doc)
        assert ident.status is IdentificationStatus.IDENTIFIED
        assert (ident.manufacturer, ident.relay_family, ident.model, ident.profile_id) == (
            "Siemens", "SIPROTEC 7SA5", "7SA511", PROFILE_ID,
        )

    def test_an_identified_7sa511_reaches_its_profile_and_only_it(self, doc):
        reg = catalogue.build_registry()
        assert reg.profile_for(reg.identify(doc)).profile_id == PROFILE_ID

    def test_match_confirms_only_a_7sa511_scheme(self, doc):
        assert Siemens7SA511Profile().match(doc).level is MatchLevel.CONFIRMED
        other = make_doc(header=(("LZOP: x", "Scheme: 7SA6131_4AB02_3GA0"),))
        assert Siemens7SA511Profile().match(other).level is MatchLevel.NONE

    def test_the_p441_profile_does_not_claim_a_7sa511_sheet(self, doc):
        assert MicomP441Profile().match(doc).level is MatchLevel.NONE

    def test_a_7sa511_sheet_under_another_relays_scheme_is_not_interpreted(self):
        doc = make_doc(header=(("LZOP: x", "Scheme: GRL200_TNB"),))
        reg = catalogue.build_registry()
        profile = reg.profile_for(reg.identify(doc))
        assert profile is not None and profile.profile_id == "toshiba-grl200"      # its own catalog, never the 7SA511
        s = summarize_interpretation(reg, doc, reg.identify(doc))
        assert s.profile_version != PROFILE_VERSION
        assert Siemens7SA511Profile().match(doc).level.name == "NONE"

    def test_identification_and_interpretation_stay_separate_stages(self, doc):
        reg = catalogue.build_registry()
        ident = reg.identify(doc)  # never calls the profile
        assert ident.status is IdentificationStatus.IDENTIFIED
        s = summarize_interpretation(reg, doc, ident)
        assert s.status is InterpretationStatus.INTERPRETED and s.profile_version == PROFILE_VERSION
        assert s.zone_count == 6


# ---------------------------------------------------------------------------
# metadata / CT / VT / basis / line
# ---------------------------------------------------------------------------


class TestMetadataTransformersBasisLine:
    def test_relay_metadata(self, model):
        m = model.metadata
        assert (m.manufacturer.value, m.family.value, m.model.value) == ("Siemens", "SIPROTEC 7SA5", "7SA511")
        assert m.scheme_name.value == "7SA511_V3.2_1A" and m.version.value == "V3.2"
        assert (m.profile_id, m.profile_version) == (PROFILE_ID, PROFILE_VERSION)
        assert all(s.provenance.status is MappingStatus.MAPPED for s in (m.manufacturer, m.model, m.scheme_name, m.version))

    def test_ct_ratio_comes_from_the_current_setting_and_the_nominal_current_tap(self, model):
        t = model.transformers
        assert (t.ct_primary_a.value, t.ct_secondary_a.value) == (800.0, 1.0)
        assert t.ct_primary_a.provenance.sources[0].parameter_id == "1105"
        assert t.ct_secondary_a.provenance.sources[0].parameter_name == "IN"
        assert t.ct_secondary_a.provenance.status is MappingStatus.MAPPED

    def test_vt_ratio_is_converted_from_the_printed_kv_only(self, model):
        t = model.transformers
        assert (t.vt_primary_v.value, t.vt_secondary_v.value) == (110000.0, 100.0)
        assert any("kV" in n for n in t.vt_primary_v.provenance.notes)

    def test_the_active_group_header_is_not_read_as_a_parameter_set(self, model):
        g = model.metadata.active_setting_group
        assert not g.is_resolved and g.provenance.raw_value.startswith("Active Group:")

    def test_voltage_and_current_base_are_not_invented(self, model):
        assert not model.transformers.voltage_base_v.is_resolved
        assert not model.transformers.current_base_a.is_resolved

    def test_impedance_basis_is_an_assumption_never_mapped(self, model):
        basis = model.transformers.setting_basis
        assert basis.value is SettingBasis.SECONDARY
        assert basis.provenance.status is MappingStatus.INFERRED and basis.needs_confirmation
        assert "without saying primary or secondary" in basis.provenance.notes[0]

    def test_basis_is_not_inferred_from_magnitude(self):
        # The same sheet with very large and very small impedance numbers has the same basis verdict.
        big = interpret(overrides={"1301": ("R1", "60", "0.05-65 ohms"), "1302": ("X1", "120", "0.05-130 ohms")})
        small = interpret(overrides={"1301": ("R1", "0.06", "0.05-65 ohms"), "1302": ("X1", "0.06", "0.05-130 ohms")})
        assert big.transformers.setting_basis.value is small.transformers.setting_basis.value is SettingBasis.SECONDARY
        assert big.transformers.setting_basis.provenance.status is MappingStatus.INFERRED

    def test_line_data(self, model):
        line = model.line
        assert (line.length.value, line.length_unit.value) == (25.0, "km")
        extras = {e.name: e.value.value for e in line.extras}
        assert extras == {"reactance_per_length": 0.4, "mutual_compensation_rm_rl": 0.0, "mutual_compensation_xm_xl": 0.0}
        # nothing the sheet does not state is claimed
        assert not line.line_angle_deg.is_resolved and not line.positive_sequence_impedance.is_resolved

    def test_a_restated_ct_ratio_that_disagrees_is_reported_not_resolved(self):
        m = interpret(notes=(("a) To confirm CT ratio", "600/1"),))
        assert m.transformers.ct_primary_a.value == 800.0  # the setting is used
        assert any("CT ratio" in n for n in m.interpretation_notes)


# ---------------------------------------------------------------------------
# zones: identity, status, direction, characteristic, reach, resistive reach
# ---------------------------------------------------------------------------


class TestZoneModel:
    def test_every_zone_the_sheet_defines_is_preserved_under_its_own_id(self, model):
        assert [z.zone_id for z in model.zones] == ZONE_IDS
        assert [z.name for z in model.zones] == ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 1B", "Zone 1L"]

    def test_a_zone_the_sheet_does_not_contain_is_not_fabricated(self):
        m = interpret(drop=tuple(c for c in BASE if c.startswith(("1401", "1402", "1403", "1404", "1405", "1406"))))
        assert [z.zone_id for z in m.zones] == ["Z1", "Z2", "Z3", "Z4", "Z1L"]

    def test_zone_identity_and_direction_are_independent(self, model):
        directions = {z.zone_id: z.direction.value for z in model.zones}
        assert directions == {
            "Z1": ZoneDirection.FORWARD, "Z2": ZoneDirection.FORWARD, "Z3": ZoneDirection.REVERSE,
            "Z4": ZoneDirection.FORWARD, "Z1B": ZoneDirection.FORWARD, "Z1L": ZoneDirection.NON_DIRECTIONAL,
        }
        assert all(zone(model, z).direction.provenance.status is MappingStatus.MAPPED for z in ZONE_IDS)

    def test_the_reverse_zone_is_zone_3_not_a_fourth_slot(self, model):
        assert zone(model, "Z3").direction.value is ZoneDirection.REVERSE
        assert zone(model, "Z4").direction.value is ZoneDirection.FORWARD

    def test_the_zones_use_explicit_rx_geometry_not_a_polar_reach(self, model):
        for zid in ("Z1", "Z2", "Z3", "Z1B", "Z1L"):
            z = zone(model, zid)
            assert z.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
            assert not z.reach.is_resolved  # no polar reach exists for this zone
        assert zone(model, "Z4").characteristic.geometry_mode is GeometryMode.POLAR_REACH  # no geometry claimed

    def test_the_reactive_reach_is_the_sheets_x_setting_mapped_directly(self, model):
        x = zone(model, "Z2").x_reach_ohm
        assert x.value == 5.0 and x.provenance.status is MappingStatus.MAPPED
        assert (x.provenance.sources[0].parameter_id, x.provenance.sources[0].parameter_name) == ("1312", "X2")

    def test_no_reach_angle_is_invented_anywhere_in_the_model(self, model):
        # The sheet states no angle: no polar (magnitude, angle) value, no 90 degrees, no tilt, no line angle.
        for path, sourced in model.iter_sourced():
            assert not isinstance(sourced.value, ImpedanceValue), path
        for z in model.zones:
            assert not z.tilt_deg.is_resolved
        assert not model.line.line_angle_deg.is_resolved
        assert all("90" not in " ".join(sourced.provenance.notes) for _, sourced in model.iter_sourced())

    def test_characteristic_is_an_assumption_and_never_mho(self, model):
        for zid in ("Z1", "Z2", "Z3", "Z1B", "Z1L"):
            c = zone(model, zid).characteristic.type
            assert c.value is CharacteristicType.QUADRILATERAL and c.provenance.status is MappingStatus.INFERRED

    def test_zone_4_is_the_fault_detection_stage_and_claims_no_geometry(self, model):
        z4 = zone(model, "Z4")
        assert not z4.reach.is_resolved and not z4.characteristic.type.is_resolved and not z4.x_reach_ohm.is_resolved
        assert z4.reach.provenance.cause is UnresolvedCause.MISSING
        assert {s.parameter_id for s in z4.reach.provenance.sources} == {"1621", "1622", "1623"}
        assert z4.compensation is None

    def test_left_resistive_reach_is_missing_never_defaulted(self, model):
        for zid in ZONE_IDS:
            assert not zone(model, zid).resistive_reach.reverse.is_resolved

    def test_phase_phase_and_phase_earth_resistive_reach_stay_distinct(self, model):
        z1 = zone(model, "Z1").resistive_reach
        assert (z1.phase_phase.value, z1.phase_earth.value) == (2.0, 6.0)  # R1 (+R) and R1E, never swapped
        assert not z1.common.is_resolved
        assert z1.phase_phase.provenance.status is z1.phase_earth.provenance.status is MappingStatus.INFERRED
        assert "does not label the loop" in z1.phase_phase.provenance.notes[0]

    def test_loop_enables_come_from_the_relay_wide_fault_type_selection(self, model):
        for z in model.zones:
            assert z.phase_phase_enabled.value is True and z.phase_earth_enabled.value is True
            assert z.phase_phase_enabled.provenance.status is MappingStatus.INFERRED
            assert z.phase_phase_enabled.provenance.sources[0].parameter_id == "1704"
            assert z.phase_earth_enabled.provenance.sources[0].parameter_id == "1705"

    def test_an_unrecognised_loop_selection_is_unsupported_not_guessed(self):
        m = interpret(overrides={"1705": ("1PH FAULTS", "PHASE-PHASE", "PE,PP")})
        assert not zone(m, "Z1").phase_earth_enabled.is_resolved
        assert zone(m, "Z1").phase_earth_enabled.provenance.cause is UnresolvedCause.UNSUPPORTED

    def test_compensation_keeps_the_re_rl_xe_xl_definition_and_is_never_converted(self, model):
        for zid in ("Z1", "Z2", "Z3", "Z1B", "Z1L"):
            c = zone(model, zid).compensation
            assert c.kind is CompensationKind.RE_RL_XE_XL
            assert (c.re_rl.value, c.xe_xl.value) == (0.7, 0.4)
            assert not c.k0_magnitude.is_resolved and not c.kr.is_resolved
            assert c.re_rl.provenance.status is MappingStatus.MAPPED


# ---------------------------------------------------------------------------
# zone status and timers
# ---------------------------------------------------------------------------


class TestStatusAndTimers:
    """The sheet's TAP SETTING cell of an operating timer is BLANK; ``Infinity`` is printed in the
    range / allowed-values column. That is not the configured delay."""

    def test_the_range_column_infinity_is_not_the_timer(self, model, doc):
        raw = next(r for r in doc.settings if r.parameter_id == "1315")
        assert raw.raw_value is None and raw.setting_range.text == "Infinity"  # the extractor kept the columns apart
        t = zone(model, "Z2").earth_timer_s
        assert not t.is_resolved and t.provenance.cause is UnresolvedCause.MISSING
        assert t.provenance.raw_value is None  # nothing was stated; "Infinity" is not echoed as the value
        assert "blank" in t.provenance.notes[0] and "not the configured delay" in " ".join(t.provenance.notes)

    def test_every_zone_timer_stays_missing(self, model):
        for zid in ZONE_IDS:
            for attr in SECONDS:
                t = getattr(zone(model, zid), attr)
                assert not t.is_resolved and t.value is None
                assert t.provenance.raw_value is None
                if t.provenance.sources:  # a timer the zone has
                    assert t.provenance.cause is UnresolvedCause.MISSING

    def test_infinity_is_not_a_zone_state_either(self, model):
        for zid in ZONE_IDS:
            assert zone(model, zid).status.value is None

    def test_an_infinity_in_the_setting_column_is_still_never_a_delay(self):
        m = interpret(overrides=INFINITY_IN_VALUE_COLUMN)
        t = zone(m, "Z2").phase_timer_s
        assert not t.is_resolved and t.provenance.raw_value == "Infinity" and t.provenance.cause is UnresolvedCause.MISSING
        assert "none is assumed" in t.provenance.notes[0]
        assert not zone(m, "Z2").status.is_resolved

    def test_the_page_notes_are_source_notes_not_settings(self, model):
        z = {zid: zone(model, zid).source_notes for zid in ZONE_IDS}
        assert [(n.subject, n.value_text) for n in z["Z1"]] == [("timer", "0.15 s")]
        assert [(n.subject, n.value_text) for n in z["Z2"]] == [("timer", "0.45 s")]
        assert [(n.subject, n.value_text) for n in z["Z3"]] == [("timer", "3 s")]
        assert [(n.subject, n.value_text) for n in z["Z4"]] == [("timer", "3 s")]
        assert z["Z1L"] == ()
        note = z["Z1"][0]
        assert note.kind is SourceNoteKind.PROPOSED_REQUIREMENT and "0.15s" in note.text
        assert note.sources and note.sources[0].setting_id  # provenance of the note's own line

    def test_the_notes_are_not_cited_by_the_timer_they_would_contradict(self, model):
        note_ids = {r.setting_id for n in zone(model, "Z1").source_notes for r in n.sources}
        for attr in SECONDS:
            assert not note_ids & {r.setting_id for r in getattr(zone(model, "Z1"), attr).provenance.sources}

    def test_finite_delays_map_to_the_loop_they_belong_to(self, finite):
        z1, z3 = zone(finite, "Z1"), zone(finite, "Z3")
        assert z1.phase_timer_s.value == 0.15 and z1.earth_timer_s.value == 0.1
        assert z1.phase_timer_s.provenance.status is MappingStatus.INFERRED  # multi-phase -> phase-phase loop
        assert z3.common_timer_s.value == 3.0 and z3.common_timer_s.provenance.status is MappingStatus.MAPPED
        assert zone(finite, "Z4").common_timer_s.value == 3.0

    def test_overall_distance_protection_on_does_not_enable_any_zone(self, model, finite):
        # 1201 DIST.PROT. = ON is the state of the whole function; the 7SA511 has no per-zone enable,
        # and a finite delay is not a state either.
        for m in (model, finite):
            for zid in ZONE_IDS:
                assert not zone(m, zid).status.is_resolved
                assert zone(m, zid).status.provenance.cause is UnresolvedCause.MISSING
                assert "no per-zone enable" in zone(m, zid).status.provenance.notes[0]

    def test_zone_1_2_3_statuses_are_unresolved_and_their_directions_stay_mapped(self, model):
        for zid, d in (("Z1", ZoneDirection.FORWARD), ("Z2", ZoneDirection.FORWARD), ("Z3", ZoneDirection.REVERSE)):
            z = zone(model, zid)
            assert not z.status.is_resolved
            assert z.direction.value is d and z.direction.provenance.status is MappingStatus.MAPPED

    def test_the_zone_1b_inactive_note_is_not_a_current_state(self, model):
        z1b = zone(model, "Z1B")
        assert not z1b.status.is_resolved
        note = z1b.source_notes[0]
        assert (note.subject, note.value_text) == ("status", "Inactive (out of service)")
        assert note.text.startswith("Zone 1B Inactive")

    def test_a_note_in_any_wording_changes_no_state(self):
        for text in ("Zone 1B not inactive: timer to be set", "Zone 2 out of service for the backup scheme"):
            m = interpret(notes=((text,),))
            assert all(not z.status.is_resolved for z in m.zones)

    def test_function_off_disables_every_zone(self):
        m = interpret(overrides={"1201": ("DIST.PROT.", "OFF", "ON,OFF")})
        assert all(z.status.value is ZoneStatus.DISABLED for z in m.zones)
        n = interpret(overrides={"7812": ("DIST. PROT.", "NOEXIST", "EXIST,NOEXIST")})
        assert all(z.status.value is ZoneStatus.DISABLED for z in n.zones)

    def test_an_unreadable_function_state_leaves_status_unresolved(self):
        m = interpret(overrides={"1201": ("DIST.PROT.", "MAYBE", "ON,OFF")})
        assert not zone(m, "Z2").status.is_resolved

    def test_the_interpretation_says_the_notes_are_not_settings(self, model):
        assert any("not current settings" in n and "not applied" in n for n in model.interpretation_notes)


# ---------------------------------------------------------------------------
# the vendor-neutral defeated-zone rule is reused, not duplicated
# ---------------------------------------------------------------------------


class TestGenericDefeatedZoneRuleIsNotDuplicated:
    TEN = {"1305": ("T1 1PHASE", "10", "0.00-32.00 s"), "1306": ("T1 >1PHASE", "10", "0.00-32.00 s")}

    def test_unknown_status_and_every_delay_10_s_is_disabled_by_the_generic_rule(self):
        doc = make_doc(overrides=self.TEN)
        raw = Siemens7SA511Profile().interpret(doc)
        assert not zone(raw, "Z1").status.is_resolved  # the profile decides nothing
        reg = catalogue.build_registry()
        via_registry = reg.interpret(doc)
        z1 = zone(via_registry, "Z1")
        assert z1.status.value is ZoneStatus.DISABLED and z1.status.provenance.notes == (DEFEATED_ZONE_REASON,)
        assert z1.status.provenance.status is MappingStatus.INFERRED

    def test_the_summary_pipeline_applies_it_too(self):
        doc = make_doc(overrides=self.TEN)
        reg = catalogue.build_registry()
        s = summarize_interpretation(reg, doc, reg.identify(doc))
        assert s.review is not None  # review is built on the already-defeated model
        z1 = next(g for g in s.review.groups if g.id == "zone-Z1")
        assert z1.state_label == "Disabled"

    def test_one_10_s_delay_alone_does_not_defeat_a_zone(self):
        m = infer_defeated_zones(interpret(overrides={"1305": ("T1 1PHASE", "10", "0.00-32.00 s"), "1306": ("T1 >1PHASE", "0.15", "0.00-32.00 s")}))
        assert not zone(m, "Z1").status.is_resolved

    def test_the_zone_1b_note_does_not_stand_in_for_a_state_so_the_generic_rule_still_applies(self):
        # The "inactive" statement is a note; with two 10 s delays the generic rule (not the note) decides.
        m = infer_defeated_zones(interpret(overrides={"1405": ("T1B 1PHASE", "10", "0.00-32.00 s"), "1406": ("T1B >1PHASE", "10", "0.00-32.00 s")}))
        z1b = zone(m, "Z1B").status
        assert z1b.value is ZoneStatus.DISABLED and z1b.provenance.notes == (DEFEATED_ZONE_REASON,)

    def test_the_profile_contains_no_copy_of_the_rule(self):
        import ast

        tree = ast.parse((APP / "relay_profiles" / "siemens_7sa511.py").read_text(encoding="utf-8"))
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "app.domain.relay_import.defeated_zone" not in imports
        numbers = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))}
        assert 10 not in numbers and 10.0 not in numbers  # no copy of the 10.0 s threshold in executable code


# ---------------------------------------------------------------------------
# unresolved values stay unresolved; nothing guessed
# ---------------------------------------------------------------------------


class TestUnresolvedStaysUnresolved:
    def test_a_known_address_under_another_name_is_a_conflict(self):
        m = interpret(overrides={"1302": ("X1 NEW", "3", "0.05-130 ohms")})
        reach = zone(m, "Z1").x_reach_ohm
        assert not reach.is_resolved and reach.provenance.cause is UnresolvedCause.CONFLICT

    def test_a_non_numeric_cell_is_unreadable(self):
        m = interpret(overrides={"1301": ("R1", "2,5", "0.05-65 ohms")})
        r = zone(m, "Z1").resistive_reach.phase_phase
        assert not r.is_resolved and r.provenance.cause is UnresolvedCause.UNREADABLE and r.provenance.raw_value == "2,5"

    def test_a_value_outside_the_printed_range_is_a_conflict(self):
        m = interpret(overrides={"1302": ("X1", "500", "0.05-130 ohms")})
        assert zone(m, "Z1").x_reach_ohm.provenance.cause is UnresolvedCause.CONFLICT

    def test_a_wrong_printed_unit_is_not_converted(self):
        m = interpret(overrides={"1105": ("In PRIMARY", "800", "10-5000 kA")})
        assert not m.transformers.ct_primary_a.is_resolved
        v = interpret(overrides={"1104": ("Un SECOND.", "100", "80-125 kV")})
        assert not v.transformers.vt_secondary_v.is_resolved  # kV is only accepted for the primary, never scaled elsewhere

    def test_a_missing_address_is_missing(self):
        m = interpret(drop=("1124",))
        assert not m.line.length.is_resolved

    def test_conflicting_duplicates_are_not_chosen(self):
        m = interpret(extra=(("1301", "R1", "9", "0.05-65 ohms"),))
        r = zone(m, "Z1").resistive_reach.phase_phase
        assert not r.is_resolved and r.provenance.cause is UnresolvedCause.CONFLICT

    def test_a_missing_nominal_current_tap_leaves_the_ct_secondary_unresolved(self):
        m = interpret(header=(("LZOP: x", "Scheme: 7SA511_V3.2_1A"),))
        assert not m.transformers.ct_secondary_a.is_resolved

    def test_a_contradicting_tap_range_is_a_conflict(self):
        m = interpret(header=(("LZOP: x", "Scheme: 7SA511_V3.2_1A"), ("IN", "1", "5 AMP")))
        assert not m.transformers.ct_secondary_a.is_resolved

    def test_two_different_schemes_leave_the_model_unidentified(self):
        m = interpret(header=(("LZOP: x", "Scheme: 7SA511_V3.2_1A"), ("LZOP: y", "Scheme: 7SA511_V4.0_5A")))
        assert not m.metadata.model.is_resolved


# ---------------------------------------------------------------------------
# provenance discipline
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_every_value_traces_to_a_raw_entry_and_nothing_is_discarded(self, model, doc):
        assert model.referenced_setting_ids() == {s.setting_id for s in doc.settings}
        for path, s in model.iter_sourced():
            for ref in s.provenance.sources:
                raw = doc.by_id(ref.setting_id)
                assert raw is not None and ref.page == raw.location.page, path

    def test_mapped_values_cite_a_source_and_unresolved_ones_carry_no_value(self, model):
        for path, s in model.iter_sourced():
            if s.provenance.status is MappingStatus.MAPPED:
                assert s.provenance.sources and s.provenance.profile_id == PROFILE_ID, path
            if s.provenance.status is MappingStatus.UNRESOLVED:
                assert s.value is None, path

    def test_nothing_resting_on_family_knowledge_is_mapped(self, model):
        inferred_paths = [
            "transformers.setting_basis",
            "zones[Z1].characteristic.type",
            "zones[Z1].resistive_reach.phase_phase", "zones[Z1].resistive_reach.phase_earth",
            "zones[Z1].phase_phase_enabled", "zones[Z1].phase_earth_enabled",
        ]
        by_path = dict(model.iter_sourced())
        for path in inferred_paths:
            assert by_path[path].provenance.status is MappingStatus.INFERRED, path
            assert by_path[path].provenance.notes, path  # the reason for the assumption is recorded

    def test_the_original_setting_name_and_code_and_raw_text_are_kept(self, model):
        src = zone(model, "Z2").x_reach_ohm.provenance.sources[0]
        assert (src.parameter_id, src.parameter_name) == ("1312", "X2") and src.page and src.location
        assert zone(model, "Z2").x_reach_ohm.provenance.raw_value == "5"

    def test_out_of_scope_settings_are_retained_and_marked(self, model):
        out = {u.name: u.out_of_scope for u in model.unmapped_settings}
        assert out["BINARY INPUT 1"] is True
        assert out["P/S PROGR."] is False  # power swing is distance-related, retained, not interpreted
        assert out["TRIP 1P Z2"] is False

    def test_interpretation_notes_carry_no_document_values(self, model):
        text = " ".join(model.interpretation_notes)
        for value in ("0.15", "0.45", "800", "110", "0.371", "2.74"):
            assert value not in text

    def test_deterministic(self, doc):
        assert Siemens7SA511Profile().interpret(doc) == Siemens7SA511Profile().interpret(doc)


# ---------------------------------------------------------------------------
# what the unchanged engine adapter makes of it (PP vs PE; Unsupported never approximated)
# ---------------------------------------------------------------------------


def _with_status(model, **statuses):
    from app.domain.relay_import.review_state import ReviewDecisions, apply_review

    return apply_review(model, ReviewDecisions(manual={f"zones[{z}].status": v for z, v in statuses.items()}))


class TestEngineAdapterView:
    def test_the_adapter_uses_the_phase_phase_loop_and_never_the_earth_one(self, finite):
        from app.domain.relay_import.review_state import ReviewDecisions, apply_review

        decisions = ReviewDecisions(
            manual={"zones[Z1].status": "enabled", "zones[Z2].status": "enabled", "zones[Z3].status": "enabled",
                    "zones[Z4].status": "disabled", "zones[Z1L].status": "disabled", "zones[Z1B].status": "disabled",
                    **{f"zones[{z}].resistive_reach.reverse": 0 for z in ("Z1", "Z2", "Z3")}},
        )
        eff = apply_review(finite, decisions)
        ad = adapt_to_engine(eff, engine_basis="secondary")
        # confirmable assumptions are not required by the adapter itself
        assert ad.supported, [r.message for r in ad.reasons]
        z1 = ad.zones[ad.zone_ids.index("Z1")]
        assert (z1.reactive_reach_ohm, z1.resistive_reach_forward_ohm) == (3.0, 2.0)
        assert z1.geometry_mode == "explicit_rx" and z1.characteristic_angle_deg is None  # no synthetic angle
        assert z1.resistive_reach_forward_ohm != 6.0  # the phase-earth 6.0 ohm is preserved, not plotted
        assert any("phase-earth operation is preserved" in w for w in ad.warnings)
        assert any("residual compensation is preserved" in w for w in ad.warnings)
        z3 = ad.zones[ad.zone_ids.index("Z3")]
        assert z3.direction == "reverse" and z3.delay_s == 3.0

    def test_an_enabled_non_directional_zone_is_refused_not_approximated(self, finite):
        eff = _with_status(finite, Z1L="enabled")
        ad = adapt_to_engine(eff, engine_basis="secondary")
        assert any(r.zone_id == "Z1L" and r.code.value == "direction_unsupported" for r in ad.reasons)

    def test_an_enabled_zone_4_is_refused_because_its_reach_is_not_decoded(self, finite):
        eff = _with_status(finite, Z4="enabled")
        ad = adapt_to_engine(eff, engine_basis="secondary")
        assert any(r.zone_id == "Z4" for r in ad.reasons)


# ---------------------------------------------------------------------------
# architecture guards
# ---------------------------------------------------------------------------

_SIEMENS_NAMES = re.compile(r"7sa5|7sa6|siprotec|siemens|digsi", re.IGNORECASE)
_ALLOWED = {
    APP / "relay_profiles" / "siemens_7sa511.py",
    APP / "relay_profiles" / "identification_catalogue.py",  # registers the profile and describes the relay
}


class TestIsolation:
    def test_siemens_knowledge_lives_only_in_the_profile_and_the_catalogue(self):
        offenders = []
        for path in APP.rglob("*.py"):
            rel = path.relative_to(APP).as_posix()
            # the relay-import pipeline and the distance engine (unrelated domains may cite vendors in prose)
            if path in _ALLOWED or not ("relay" in rel or "distance" in rel):
                continue
            hit = _SIEMENS_NAMES.search(path.read_text(encoding="utf-8"))
            if hit:
                offenders.append(f"{path.relative_to(APP)}: {hit.group(0)}")
        assert not offenders, offenders

    def test_the_frontend_has_no_siemens_branch(self):
        text = (APP.parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
        for token in ("7SA", "Siemens", "siemens", "SIPROTEC", "siemens-7sa511"):
            assert token not in text

    def test_profile_does_not_touch_persistence_or_the_engine(self):
        text = (APP / "relay_profiles" / "siemens_7sa511.py").read_text(encoding="utf-8")
        for forbidden in ("app.storage", "sqlalchemy", "fastapi", "app.services", "distance_protection", "open(", "pypdf"):
            assert forbidden not in text

    def test_no_family_base_class_exists_yet(self):
        text = (APP / "relay_profiles" / "siemens_7sa511.py").read_text(encoding="utf-8")
        assert not re.search(r"class\s+\w+\(\s*\w*Siemens", text)
        assert not list((APP / "relay_profiles").glob("siemens_7sa_*.py")) and not (APP / "relay_profiles" / "siemens_family.py").exists()

    def test_registered_beside_the_p441_profile_only_through_the_catalogue(self):
        ids = [p.profile_id for p in catalogue.build_registry()._profiles]
        # Slice 12 added the RED670; the remaining families follow as catalog-only profiles
        assert ids[:3] == ["schneider-micom-p441", PROFILE_ID, "hitachi-red670"]
        assert set(ids[3:]) == {"hitachi-rel670", "hitachi-rel511", "siemens-siprotec5-7sl87", "siemens-7sa613", "toshiba-grz100", "toshiba-grl200", "nr-rcs941", "lfzp111", "relz100"}


# ---------------------------------------------------------------------------
# Real owner sample (not committed): RELAY_SAMPLE_PDF_DIR
# ---------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
needs_sample = pytest.mark.skipif(not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run")


def real_doc():
    from app.services.relay_pdf_extractor import extract_pdf

    path = Path(SAMPLE_DIR) / "7sa511.pdf"
    if not path.exists():
        pytest.skip("7sa511.pdf not available")
    return extract_pdf(path.read_bytes()).document


@pytest.fixture(scope="module")
def rdoc():
    return real_doc()


@pytest.fixture(scope="module")
def rmodel(rdoc):
    reg = catalogue.build_registry()
    ident = reg.identify(rdoc)
    assert ident.status is IdentificationStatus.IDENTIFIED and ident.profile_id == PROFILE_ID
    return reg.profile_for(ident).interpret(rdoc)


@needs_sample
class TestRealSample:
    def test_identified(self, rdoc):
        ident = catalogue.build_registry().identify(rdoc)
        assert (ident.manufacturer, ident.relay_family, ident.model) == ("Siemens", "SIPROTEC 7SA5", "7SA511")
        assert ident.confidence.value == "high"

    def test_metadata_ct_vt_and_basis(self, rmodel):
        m, t = rmodel.metadata, rmodel.transformers
        assert (m.model.value, m.version.value, m.scheme_name.value) == ("7SA511", "V3.2", "7SA511_V3.2_1A")
        assert (t.ct_primary_a.value, t.ct_secondary_a.value) == (600.0, 1.0)
        assert (t.vt_primary_v.value, t.vt_secondary_v.value) == (132000.0, 110.0)
        assert t.setting_basis.value is SettingBasis.SECONDARY and t.setting_basis.provenance.status is MappingStatus.INFERRED

    def test_line(self, rmodel):
        assert (rmodel.line.length.value, rmodel.line.length_unit.value) == (18.0, "km")
        assert {e.name: e.value.value for e in rmodel.line.extras}["reactance_per_length"] == 0.371

    EXPECTED = {  # zone -> (X reach, R phase-phase, R phase-earth, direction)
        "Z1": (2.74, 1.84, 9.14, ZoneDirection.FORWARD),
        "Z2": (4.47, 2.12, 9.96, ZoneDirection.FORWARD),
        "Z3": (0.69, 0.46, 2.29, ZoneDirection.REVERSE),
        "Z1B": (4.47, 2.12, 9.96, ZoneDirection.FORWARD),
        "Z1L": (130.0, 65.0, 130.0, ZoneDirection.NON_DIRECTIONAL),
    }

    def test_all_six_zones_are_preserved(self, rmodel):
        assert [z.zone_id for z in rmodel.zones] == ZONE_IDS

    @pytest.mark.parametrize("zone_id", EXPECTED)
    def test_reach_resistive_reach_and_direction(self, rmodel, zone_id):
        x, rpp, rpe, direction = self.EXPECTED[zone_id]
        z = zone(rmodel, zone_id)
        assert z.x_reach_ohm.value == x and not z.reach.is_resolved
        assert z.characteristic.geometry_mode is GeometryMode.EXPLICIT_RX
        assert (z.resistive_reach.phase_phase.value, z.resistive_reach.phase_earth.value) == (rpp, rpe)
        assert z.direction.value is direction
        assert not z.resistive_reach.reverse.is_resolved

    def test_compensation(self, rmodel):
        c = zone(rmodel, "Z1").compensation
        assert (c.re_rl.value, c.xe_xl.value) == (0.59, 0.48) and c.kind is CompensationKind.RE_RL_XE_XL

    def test_the_range_column_infinity_is_not_a_timer_and_every_delay_stays_missing(self, rmodel):
        for zid in ZONE_IDS:
            z = zone(rmodel, zid)
            for attr in SECONDS:
                t = getattr(z, attr)
                assert not t.is_resolved
                assert t.provenance.raw_value is None  # the TAP SETTING cell is blank

    def test_the_page_5_requirements_are_notes_only(self, rmodel):
        figures = {zid: [n.value_text for n in zone(rmodel, zid).source_notes] for zid in ("Z1", "Z2", "Z3", "Z4")}
        assert figures == {"Z1": ["0.15 s"], "Z2": ["0.45 s"], "Z3": ["3 s"], "Z4": ["3 s"]}
        assert [n.subject for n in zone(rmodel, "Z1B").source_notes] == ["status"]
        for zid in ZONE_IDS:
            assert all(getattr(zone(rmodel, zid), a).value is None for a in SECONDS)

    def test_no_zone_state_is_assumed(self, rmodel):
        for zid in ZONE_IDS:
            assert not zone(rmodel, zid).status.is_resolved

    def test_the_phase_earth_values_stay_distinct_from_the_phase_phase_ones(self, rmodel):
        assert [zone(rmodel, z).resistive_reach.phase_earth.value for z in ("Z1", "Z2", "Z3")] == [9.14, 9.96, 2.29]
        assert [zone(rmodel, z).resistive_reach.phase_phase.value for z in ("Z1", "Z2", "Z3")] == [1.84, 2.12, 0.46]
        assert not any(zone(rmodel, z).resistive_reach.reverse.is_resolved for z in ZONE_IDS)  # no left reach invented

    def test_every_raw_entry_is_accounted_for(self, rmodel, rdoc):
        assert rmodel.referenced_setting_ids() == {s.setting_id for s in rdoc.settings}

    def test_the_real_values_reach_the_apply_plan_and_the_engine_as_explicit_rx(self, rmodel):
        from app.domain.distance_protection import (
            CHARACTERISTIC_QUADRILATERAL,
            ZONE_STATE_NOT_OPERATED,
            ZONE_STATE_OPERATED,
            evaluate_zone_state,
        )
        from app.domain.impedance import ImpedancePoint
        from app.domain.relay_import.apply_settings import build_apply_plan
        from app.domain.relay_import.review_state import ReviewDecisions, apply_review

        manual = {f"zones[{z}].status": "enabled" for z in ("Z1", "Z2", "Z3")}
        manual |= {f"zones[{z}].status": "disabled" for z in ("Z4", "Z1B", "Z1L")}
        manual |= {f"zones[{z}].resistive_reach.reverse": 0 for z in ("Z1", "Z2", "Z3")}
        manual |= {"zones[Z1].phase_timer_s": 0.15, "zones[Z2].phase_timer_s": 0.45, "zones[Z3].common_timer_s": 3}
        eff = apply_review(rmodel, ReviewDecisions(manual=manual))
        ad = adapt_to_engine(eff, engine_basis="secondary")
        assert ad.supported, [r.message for r in ad.reasons]
        plan = build_apply_plan(eff, ad, impedance_basis="secondary")
        z1, z2, z3 = plan.zones[:3]
        assert (z1.reactive_reach_ohm, z1.resistive_reach_forward_ohm) == (2.74, 1.84)
        assert (z2.reactive_reach_ohm, z2.resistive_reach_forward_ohm) == (4.47, 2.12)
        assert (z3.reactive_reach_ohm, z3.resistive_reach_forward_ohm, z3.direction) == (0.69, 0.46, "reverse")
        assert all(z.geometry_mode == "explicit_rx" and z.characteristic_angle_deg is None for z in (z1, z2, z3))
        assert [z.delay_s for z in (z1, z2, z3)] == [0.15, 0.45, 3.0]  # the user's, not the page-5 notes' (equal here by choice)

        def state(zid, r, x):
            zs = ad.zones[ad.zone_ids.index(zid)]
            return evaluate_zone_state(ImpedancePoint(r, x, 0.0, 0.0), characteristic=CHARACTERISTIC_QUADRILATERAL, zone=zs)

        assert (state("Z1", 1.83, 2.73), state("Z1", 1.85, 2.0), state("Z1", 1.0, 2.75)) == (
            ZONE_STATE_OPERATED, ZONE_STATE_NOT_OPERATED, ZONE_STATE_NOT_OPERATED)
        assert (state("Z2", 2.11, 4.46), state("Z2", 2.13, 4.0)) == (ZONE_STATE_OPERATED, ZONE_STATE_NOT_OPERATED)
        assert (state("Z3", -0.45, -0.68), state("Z3", 0.45, 0.68), state("Z3", -0.47, -0.3)) == (
            ZONE_STATE_OPERATED, ZONE_STATE_NOT_OPERATED, ZONE_STATE_NOT_OPERATED)
