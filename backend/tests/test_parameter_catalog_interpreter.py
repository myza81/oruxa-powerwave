"""The generic matcher / transformer, on a synthetic relay that exists nowhere in Python.

Nothing here knows a real manufacturer: the "Acme X1" relay is defined only by the JSON-shaped
catalogs built below. Everything the matcher does -- exact matching by code / name / section,
type and unit validation, the transformation primitives, provenance, precedence, unmapped
preservation -- is therefore proven to come from the catalog and not from OEM code.
"""

from __future__ import annotations

import copy

import pytest

from app.domain.relay_import.canonical_codec import decode_model, encode_model
from app.domain.relay_import.canonical_distance import (
    CharacteristicType,
    GeometryMode,
    ImpedanceValue,
    SettingBasis,
    ZoneDirection,
    ZoneStatus,
)
from app.domain.relay_import.provenance import MappingAuthority, MappingStatus, UnresolvedCause
from tests.parameter_catalog_helpers import catalog_json, doc, interpret, mapping, parse


def z(model, zid="Z1"):
    return model.zone(zid)


def num(name, canonical, **kw):
    sel = {"name": name, "type": "number", "unit": kw.pop("unit", "ohm")}
    sel.update(kw.pop("selector", {}))
    return mapping(kw.pop("id", f"m.{canonical}"), canonical, zone=kw.pop("zone", "*"), source=sel, **kw)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class TestExactMatching:
    def test_a_setting_is_matched_by_name_ignoring_case_and_spacing(self):
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"))
        model = interpret(data, doc(("x   z1", "6.5", "0-100"), ("X Z2", "9", "0-100")))
        assert (z(model, "Z1").x_reach_ohm.value, z(model, "Z2").x_reach_ohm.value) == (6.5, 9.0)

    def test_zone_templates_select_each_zones_own_setting(self):
        data = catalog_json(num("Reach-{zone}", "distance.zone.x_reach"))
        model = interpret(data, doc(("Reach-Z2", "2"), ("Reach-Z1", "1")))
        assert [z(model, i).x_reach_ohm.value for i in ("Z1", "Z2")] == [1.0, 2.0]

    def test_a_setting_is_matched_by_code_and_its_name_must_agree(self):
        sel = {"code": "0a07", "name": "Phase CT Primary", "type": "number", "unit": "A"}
        data = catalog_json(mapping("ct", "ct_vt.ct_primary", source=sel))
        ok = interpret(data, doc(("Phase CT Primary", "1200", "1-30000", "0A07")))
        assert ok.transformers.ct_primary_a.value == 1200.0
        wrong = interpret(data, doc(("Something Else", "1200", "1-30000", "0A07")))
        ct = wrong.transformers.ct_primary_a
        assert not ct.is_resolved and ct.provenance.cause is UnresolvedCause.CONFLICT
        assert "differently" in " ".join(ct.provenance.notes)

    def test_a_code_alone_matches_whatever_the_document_calls_it(self):
        data = catalog_json(mapping("ct", "ct_vt.ct_primary", source={"code": "0A07", "type": "number", "unit": "A"}))
        assert interpret(data, doc(("Whatever", "5", None, "0A07"))).transformers.ct_primary_a.value == 5.0

    def test_a_name_pattern_and_a_section_filter_narrow_the_match(self):
        data = catalog_json(mapping("x", "distance.zone.x_reach", zone="Z1",
                                    source={"name_pattern": "^Reach$", "section": "Distance", "type": "number", "unit": "ohm"}))
        inside = interpret(data, doc(("Reach", "3"), section=("Distance Zones",)))
        outside = interpret(data, doc(("Reach", "3"), section=("Overcurrent",)))
        assert z(inside).x_reach_ohm.value == 3.0 and not z(outside).x_reach_ohm.is_resolved

    def test_a_pattern_in_text_reads_a_value_out_of_free_text(self):
        data = catalog_json(mapping("v", "ct_vt.ct_primary", source={"pattern_in_text": r"CT ratio\s+(\d+)/", "type": "number", "unit": "A"}))
        assert interpret(data, doc(("Note", "CT ratio 600/1"))).transformers.ct_primary_a.value == 600.0

    def test_an_absent_setting_is_missing_not_defaulted(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("Other", "1")))
        x = z(model).x_reach_ohm
        assert not x.is_resolved and x.provenance.cause is UnresolvedCause.MISSING and "not present" in " ".join(x.provenance.notes)


class TestNeverConfusingRangeWithValue:
    def test_a_blank_value_cell_with_a_range_is_unreadable_never_the_range(self):
        # the 7SA511 failure mode: a blank TAP SETTING cell beside a printed range column
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"))
        model = interpret(data, doc(("X Z1", "", "0-100"), ("X Z2", None, "0.1-3000")))
        for zid in ("Z1", "Z2"):
            x = z(model, zid).x_reach_ohm
            assert not x.is_resolved and x.provenance.cause is UnresolvedCause.UNREADABLE

    def test_a_value_outside_its_own_printed_range_is_a_conflict(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "500", "0-100")))
        x = z(model).x_reach_ohm
        assert not x.is_resolved and x.provenance.cause is UnresolvedCause.CONFLICT and x.provenance.raw_value == "500"

    def test_a_range_string_in_the_value_cell_is_not_a_number(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "0-100", "0-100")))
        assert z(model).x_reach_ohm.provenance.cause is UnresolvedCause.UNREADABLE

    def test_range_checking_can_be_declared_off_but_a_range_is_still_not_a_value(self):
        sel = {"validate": {"within_printed_range": False}}
        data = catalog_json(num("X {zone}", "distance.zone.x_reach", selector=sel))
        assert z(interpret(data, doc(("X Z1", "500", "0-100")))).x_reach_ohm.value == 500.0


class TestTypeAndUnitValidation:
    def test_a_non_numeric_value_is_unreadable(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "six", "0-100")))
        assert z(model).x_reach_ohm.provenance.cause is UnresolvedCause.UNREADABLE

    @pytest.mark.parametrize("printed,resolves", [("0-100 ohm", True), ("0-100 Ω", True), ("0-100", True), ("0-100 A", False)])
    def test_a_printed_unit_must_agree_when_printed(self, printed, resolves):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "5", printed)))
        x = z(model).x_reach_ohm
        assert x.is_resolved is resolves
        if not resolves:
            assert x.provenance.cause is UnresolvedCause.CONFLICT and "no unit conversion is applied" in " ".join(x.provenance.notes)

    def test_a_required_printed_unit_must_be_there(self):
        sel = {"printed_unit": {"policy": "required"}}
        data = catalog_json(num("X {zone}", "distance.zone.x_reach", selector=sel))
        assert not z(interpret(data, doc(("X Z1", "5", "0-100")))).x_reach_ohm.is_resolved
        assert z(interpret(data, doc(("X Z1", "5", "0-100 ohm")))).x_reach_ohm.value == 5.0

    def test_a_dimensionless_setting_rejects_a_printed_unit(self):
        sel = {"printed_unit": {"policy": "none"}}
        data = catalog_json(mapping("k", "distance.zone.comp.k0_magnitude", zone="*", source={"name": "K {zone}", "type": "number", "unit": "", **sel}))
        assert z(interpret(data, doc(("K Z1", "0.8", "0-4")))).compensation.k0_magnitude.value == 0.8
        bad = z(interpret(data, doc(("K Z1", "0.8", "0-4 ohm")))).compensation
        assert not bad.k0_magnitude.is_resolved

    def test_a_listed_printed_text_can_be_accepted_only_while_a_condition_holds(self):
        sel = {"printed_unit": {"policy": "required", "accept_if": [{"text": "/I1", "when": {"canonical": "ct_vt.ct_secondary", "equals": 1}}]}}
        data = catalog_json(
            mapping("sec", "ct_vt.ct_secondary", source={"name": "CT sec", "type": "number", "unit": "A", "validate": {"within_printed_range": False}}),
            num("X {zone}", "distance.zone.x_reach", selector=sel),
        )
        assert z(interpret(data, doc(("CT sec", "1"), ("X Z1", "5", "0-100 /I1")))).x_reach_ohm.value == 5.0
        assert not z(interpret(data, doc(("CT sec", "5"), ("X Z1", "5", "0-100 /I1")))).x_reach_ohm.is_resolved

    def test_allowed_values_and_a_printed_range_pattern_must_hold(self):
        sel = {"type": "number", "unit": "A", "validate": {"allowed_values": [1, 5], "printed_range_pattern": r"1\s*A\s*/\s*5\s*A"}}
        data = catalog_json(mapping("sec", "ct_vt.ct_secondary", source={"name": "CT sec", **sel}))
        assert interpret(data, doc(("CT sec", "5", "1A / 5A"))).transformers.ct_secondary_a.value == 5.0
        assert not interpret(data, doc(("CT sec", "2", "1A / 5A"))).transformers.ct_secondary_a.is_resolved
        assert not interpret(data, doc(("CT sec", "5", "0-10"))).transformers.ct_secondary_a.is_resolved

    def test_allowed_text_rejects_a_value_the_catalog_does_not_know(self):
        data = catalog_json(mapping("e", "distance.zone.direction", zone="*", source={"name": "Dir {zone}", "allowed_text": ["fwd", "rev"]},
                                    transform={"type": "enum", "map": {"fwd": "forward", "rev": "reverse"}}))
        d = z(interpret(data, doc(("Dir Z1", "sideways")))).direction
        assert not d.is_resolved and d.provenance.cause is UnresolvedCause.UNSUPPORTED and d.provenance.raw_value == "sideways"


class TestDuplicateEntries:
    def test_identical_duplicates_are_noted_and_still_resolve(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "5", "0-100"), ("X Z1", "5", "0-100")))
        x = z(model).x_reach_ohm
        assert x.value == 5.0 and "duplicate" in " ".join(x.provenance.notes)
        assert len(x.provenance.sources) == 2

    def test_conflicting_duplicates_are_a_conflict_and_which_applies_is_not_guessed(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc(("X Z1", "5", "0-100"), ("X Z1", "6", "0-100")))
        x = z(model).x_reach_ohm
        assert not x.is_resolved and x.provenance.cause is UnresolvedCause.CONFLICT and x.provenance.raw_value == "5 / 6"


# ---------------------------------------------------------------------------
# Transformation primitives
# ---------------------------------------------------------------------------


def run_one(transform, value, *, source=None, canonical="distance.zone.x_reach", extra_rows=(), **kw):
    sel = source or {"name": "S {zone}", "type": "number", "unit": "ohm"}
    data = catalog_json(mapping("t", canonical, zone="*", source=sel, transform=transform, **kw))
    return interpret(data, doc(("S Z1", value, None), *extra_rows))


class TestTransformationPrimitives:
    def test_direct_uses_the_value_as_printed_and_records_no_transformation(self):
        x = z(run_one(None, "7")).x_reach_ohm
        assert x.value == 7.0 and x.provenance.transformation is None

    def test_an_explicit_direct_step_is_the_same_as_no_step(self):
        x = z(run_one({"type": "direct"}, "7")).x_reach_ohm
        assert x.value == 7.0 and x.provenance.transformation is None

    def test_divide_halves_and_records_the_sentence(self):
        x = z(run_one({"type": "divide", "by": 2}, "7")).x_reach_ohm
        assert x.value == 3.5 and x.provenance.transformation == "7 ÷ 2 = 3.5" and x.provenance.raw_value == "7"

    def test_a_describe_template_replaces_the_default_sentence(self):
        x = z(run_one({"type": "divide", "by": 2, "describe": "RFPP {input} ohm/loop ÷ 2 = {result} ohm"}, "7")).x_reach_ohm
        assert x.provenance.transformation == "RFPP 7 ohm/loop ÷ 2 = 3.5 ohm"

    def test_scale_and_multiply(self):
        assert z(run_one({"type": "scale", "factor": 2, "offset": 1}, "3")).x_reach_ohm.value == 7.0
        assert z(run_one({"type": "multiply", "factor": 10}, "3")).x_reach_ohm.value == 30.0

    def test_percentage_both_ways(self):
        assert z(run_one({"type": "percentage", "direction": "to_fraction"}, "80")).x_reach_ohm.value == pytest.approx(0.8)
        assert z(run_one({"type": "percentage", "direction": "to_percent"}, "0.5")).x_reach_ohm.value == pytest.approx(50.0)

    def test_chained_steps_run_in_order(self):
        x = z(run_one([{"type": "divide", "by": 2}, {"type": "multiply", "factor": 10}], "7")).x_reach_ohm
        assert x.value == 35.0 and x.provenance.transformation == "7 ÷ 2 = 3.5; 3.5 × 10 = 35"

    def test_ratio_of_two_sources(self):
        data = catalog_json(mapping("r", "distance.zone.x_reach", zone="*",
                                    sources={"numerator": {"name": "A", "type": "number", "unit": "ohm"},
                                             "denominator": {"name": "B", "type": "number", "unit": "ohm"}},
                                    transform={"type": "ratio"}))
        assert z(interpret(data, doc(("A", "9"), ("B", "4")))).x_reach_ohm.value == 2.25
        zero = z(interpret(data, doc(("A", "9"), ("B", "0")))).x_reach_ohm
        assert not zero.is_resolved and zero.provenance.cause is UnresolvedCause.UNREADABLE

    def test_unit_conversion_is_applied_from_the_declared_source_unit(self):
        data = catalog_json(mapping("vt", "ct_vt.vt_primary", source={"name": "VT kV", "type": "number", "unit": "kV"}))
        vt = interpret(data, doc(("VT kV", "220"))).transformers.vt_primary_v
        assert vt.value == 220000.0 and vt.provenance.transformation == "220 kV → 220000 V" and vt.provenance.raw_value == "220"

    def test_an_explicit_unit_conversion_step(self):
        data = catalog_json(mapping("t", "distance.zone.common_delay", zone="*", source={"name": "T {zone}", "type": "number", "unit": "ms"},
                                    transform={"type": "unit_conversion", "from": "ms", "to": "s"}))
        d = z(interpret(data, doc(("T Z1", "150")))).common_timer_s
        assert d.value == pytest.approx(0.15) and "150 ms → 0.15 s" in d.provenance.transformation

    def test_enum_maps_text_to_a_canonical_value(self):
        data = catalog_json(mapping("e", "distance.zone.direction", zone="*", source={"name": "Dir {zone}"},
                                    transform={"type": "enum", "map": {"Fwd": "forward", "Rev": "reverse", "NonDir": "non_directional"}}))
        model = interpret(data, doc(("Dir Z1", "FWD"), ("Dir Z2", " rev ")))
        assert (z(model, "Z1").direction.value, z(model, "Z2").direction.value) == (ZoneDirection.FORWARD, ZoneDirection.REVERSE)
        assert z(model, "Z1").direction.provenance.status is MappingStatus.MAPPED

    def test_an_enum_value_the_map_lacks_is_unsupported_and_keeps_the_raw_text(self):
        data = catalog_json(mapping("e", "distance.zone.direction", zone="*", source={"name": "Dir {zone}"},
                                    transform={"type": "enum", "map": {"Fwd": "forward"}}))
        d = z(interpret(data, doc(("Dir Z1", "Bidirectional")))).direction
        assert not d.is_resolved and d.provenance.cause is UnresolvedCause.UNSUPPORTED and d.provenance.raw_value == "Bidirectional"

    def test_boolean_reads_on_off_and_refuses_anything_else(self):
        data = catalog_json(mapping("b", "distance.zone.pp_enabled", zone="*", source={"name": "PP {zone}"}, transform={"type": "boolean"}))
        model = interpret(data, doc(("PP Z1", "ON"), ("PP Z2", "perhaps")))
        assert z(model, "Z1").phase_phase_enabled.value is True
        assert z(model, "Z2").phase_phase_enabled.provenance.cause is UnresolvedCause.UNSUPPORTED

    def test_bitmask_extracts_a_flag(self):
        data = catalog_json(mapping("b", "distance.zone.pe_enabled", zone="*", source={"name": "Flags {zone}", "type": "number", "unit": ""},
                                    transform={"type": "bitmask", "bit": 2}))
        model = interpret(data, doc(("Flags Z1", "5"), ("Flags Z2", "2")))
        assert (z(model, "Z1").phase_earth_enabled.value, z(model, "Z2").phase_earth_enabled.value) == (True, False)

    def test_regex_extracts_text(self):
        data = catalog_json(mapping("r", "distance.zone.x_reach", zone="*", source={"name": "Z {zone}", "type": "text"},
                                    transform={"type": "regex", "pattern": r"X=([\d.]+)", "as": "number"}))
        assert z(interpret(data, doc(("Z Z1", "R=1 X=4.5")))).x_reach_ohm.value == 4.5
        assert not z(interpret(data, doc(("Z Z1", "no reach here")))).x_reach_ohm.is_resolved

    def test_explicit_rx_assembly_and_polar_assembly(self):
        rx = catalog_json(mapping("z0", "distance.zone.zero_sequence_reach", zone="*",
                                  sources={"r": {"name": "R0 {zone}", "type": "number", "unit": "ohm"},
                                           "x": {"name": "X0 {zone}", "type": "number", "unit": "ohm"}},
                                  transform={"type": "impedance_rx"}))
        value = z(interpret(rx, doc(("R0 Z1", "5"), ("X0 Z1", "18")))).zero_sequence_reach.value
        assert (value.r_ohm, value.x_ohm) == (5.0, 18.0)
        polar = catalog_json(mapping("rc", "distance.zone.reach", zone="*",
                                     sources={"magnitude": {"name": "Z {zone}", "type": "number", "unit": "ohm"},
                                              "angle": {"name": "Ang {zone}", "type": "number", "unit": "deg"}},
                                     transform={"type": "impedance_polar"}))
        reach = z(interpret(polar, doc(("Z Z1", "8"), ("Ang Z1", "75")))).reach.value
        assert isinstance(reach, ImpedanceValue) and (reach.magnitude_ohm, reach.angle_deg) == (8.0, 75.0)

    def test_an_assembly_with_a_missing_input_is_unresolved(self):
        rx = catalog_json(mapping("z0", "distance.zone.zero_sequence_reach", zone="*",
                                  sources={"r": {"name": "R0 {zone}", "type": "number", "unit": "ohm"},
                                           "x": {"name": "X0 {zone}", "type": "number", "unit": "ohm"}},
                                  transform={"type": "impedance_rx"}))
        zr = z(interpret(rx, doc(("R0 Z1", "5")))).zero_sequence_reach
        assert not zr.is_resolved and zr.provenance.cause is UnresolvedCause.MISSING

    def test_a_decision_table_uses_the_inputs_that_are_available(self):
        data = catalog_json(mapping(
            "s", "distance.zone.status", zone="*",
            sources={"op": {"name": "Op {zone}", "allowed_text": ["on", "off"]}, "dir": {"name": "Dir {zone}", "allowed_text": ["off", "fwd"]}},
            transform={"type": "decision_table", "rules": [
                {"when": {"op": "off"}, "value": "disabled"},
                {"when": {"dir": "off"}, "value": "disabled"},
                {"when": {"op": "on", "dir": "fwd"}, "value": "enabled"},
            ]}))
        model = interpret(data, doc(("Op Z1", "OFF"), ("Op Z2", "ON"), ("Dir Z2", "fwd")))
        assert z(model, "Z1").status.value is ZoneStatus.DISABLED       # decided by Operation alone
        assert z(model, "Z2").status.value is ZoneStatus.ENABLED
        undecided = interpret(data, doc(("Op Z1", "ON")))
        assert not z(undecided, "Z1").status.is_resolved


class TestGates:
    def gated(self, gate_value, value="0.15", *, gate_present=True):
        rows = [("T Z1", value, "0-60")] + ([("Timer Z1", gate_value, None)] if gate_present else [])
        data = catalog_json(mapping("t", "distance.zone.phase_delay", zone="Z1", source={"name": "T {zone}", "type": "number", "unit": "s"},
                                    requires=[{"source": {"name": "Timer {zone}", "allowed_text": ["on", "off"]}, "equals": ["on"],
                                               "off_note": "The Timer switch is OFF.", "missing_note": "The Timer switch was not found."}]))
        return z(interpret(data, doc(*rows))).phase_timer_s

    def test_an_open_gate_lets_the_value_through_and_cites_the_switch(self):
        t = self.gated("ON")
        assert t.value == 0.15 and {s.parameter_name for s in t.provenance.sources} == {"T Z1", "Timer Z1"}

    def test_a_closed_gate_leaves_the_value_unresolved_but_keeps_the_raw_text(self):
        t = self.gated("OFF")
        assert not t.is_resolved and t.provenance.raw_value == "0.15" and "OFF" in " ".join(t.provenance.notes)

    def test_a_missing_gate_does_not_establish_the_value(self):
        t = self.gated(None, gate_present=False)
        assert not t.is_resolved and "not found" in " ".join(t.provenance.notes)


class TestConstantsAndGaps:
    def constant(self, **kw):
        return catalog_json(
            num("X {zone}", "distance.zone.x_reach"),
            mapping("c", "distance.zone.characteristic", zone="*", transform={"type": "constant", "value": "quadrilateral"},
                    evidence=[{"name": "Head {zone}"}], evidence_from=["distance.zone.x_reach"],
                    requires_resolved=["distance.zone.x_reach"], authority="documented_derivation", **kw))

    def test_a_constant_cites_its_evidence_and_the_values_it_depends_on(self):
        model = interpret(self.constant(), doc(("Head Z1", None), ("X Z1", "6", "0-100")))
        c = z(model).characteristic.type
        assert c.value is CharacteristicType.QUADRILATERAL and c.provenance.status is MappingStatus.MAPPED
        assert c.provenance.authority is MappingAuthority.DOCUMENTED_DERIVATION
        assert {s.parameter_name for s in c.provenance.sources} == {"Head Z1", "X Z1"}

    def test_without_its_evidence_a_constant_is_not_claimed(self):
        model = interpret(self.constant(unresolved_note="no heading"), doc(("X Z1", "6", "0-100")))
        c = z(model).characteristic.type
        assert not c.is_resolved and "no heading" in " ".join(c.provenance.notes)

    def test_without_the_required_value_a_constant_is_not_claimed(self):
        model = interpret(self.constant(), doc(("Head Z1", None)))
        assert not z(model).characteristic.type.is_resolved

    def test_a_plain_canonical_field_takes_a_constant_without_evidence(self):
        data = catalog_json(mapping("g", "distance.zone.geometry_mode", zone="*", transform={"type": "constant", "value": "explicit_rx"}))
        assert z(interpret(data, doc())).characteristic.geometry_mode is GeometryMode.EXPLICIT_RX

    def test_a_capability_gap_is_unsupported_and_keeps_its_evidence(self):
        data = catalog_json(mapping("gap", "distance.zone.r_left", zone="*", gap={
            "note": "Formed by the directional element ({evidence}).", "evidence": [{"name": "ArgDir"}, {"name": "ArgNeg"}]}))
        left = z(interpret(data, doc(("ArgDir", "15"), ("ArgNeg", "115")))).resistive_reach.reverse
        assert not left.is_resolved and left.provenance.cause is UnresolvedCause.UNSUPPORTED
        assert {s.parameter_name for s in left.provenance.sources} == {"ArgDir", "ArgNeg"}
        assert left.provenance.raw_value == "15 | 115" and "ArgDir = 15, ArgNeg = 115" in " ".join(left.provenance.notes)

    def test_a_system_basis_constant_is_a_document_level_enum(self):
        data = catalog_json(mapping("b", "ct_vt.impedance_basis", transform={"type": "constant", "value": "primary"}, evidence=[{"name": "IBase"}]))
        basis = interpret(data, doc(("IBase", "1200"))).transformers.setting_basis
        assert basis.value is SettingBasis.PRIMARY


class TestPrecedence:
    def alternatives(self):
        return catalog_json(
            num("Explicit X {zone}", "distance.zone.x_reach", id="a"),
            num("Fallback X {zone}", "distance.zone.x_reach", id="b", authority="assumption", confidence="inferred",
                note="a documented fallback"),
        )

    def test_the_strongest_authority_that_resolves_wins_and_its_provenance_is_recorded(self):
        model = interpret(self.alternatives(), doc(("Explicit X Z1", "6"), ("Fallback X Z1", "9")))
        x = z(model).x_reach_ohm
        assert x.value == 6.0 and x.provenance.status is MappingStatus.MAPPED
        assert x.provenance.authority is MappingAuthority.CONFIGURED_SETTING and x.provenance.sources[0].parameter_name == "Explicit X Z1"

    def test_a_weaker_alternative_is_used_only_when_the_stronger_does_not_resolve(self):
        model = interpret(self.alternatives(), doc(("Fallback X Z1", "9")))
        x = z(model).x_reach_ohm
        assert x.value == 9.0 and x.provenance.status is MappingStatus.INFERRED
        assert x.provenance.authority is MappingAuthority.ASSUMPTION and "a documented fallback" in x.provenance.notes

    def test_when_none_resolves_the_strongest_mappings_failure_is_reported(self):
        model = interpret(self.alternatives(), doc(("Explicit X Z1", "banana")))
        x = z(model).x_reach_ohm
        assert not x.is_resolved and x.provenance.cause is UnresolvedCause.UNREADABLE


# ---------------------------------------------------------------------------
# Unmapped settings, provenance, versions
# ---------------------------------------------------------------------------


class TestUnmappedSettingsArePreserved:
    def model(self):
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"),
                            distance_scope={"code_prefixes": ["30"], "section_contains": ["Distance"], "names": ["psb"]})
        return interpret(data, doc(
            ("X Z1", "6", "0-100"),
            ("Mystery", "42", None, "3001"),            # distance-scoped by code prefix
            ("Hostname", "relay-7", None, "9999"),      # outside Distance Protection
            ("PSB", "ON"),                              # distance-scoped by name
        ))

    def test_a_setting_the_catalog_does_not_map_is_kept_raw_and_not_interpreted(self):
        unmapped = {u.name: u for u in self.model().unmapped_settings}
        assert set(unmapped) == {"Mystery", "Hostname", "PSB"}
        assert unmapped["Mystery"].raw_value == "42" and "not interpreted" in unmapped["Mystery"].reason
        assert unmapped["Mystery"].out_of_scope is False and unmapped["PSB"].out_of_scope is False
        assert unmapped["Hostname"].out_of_scope is True and "outside Distance Protection" in unmapped["Hostname"].reason

    def test_a_mapped_setting_is_not_also_listed_as_unmapped(self):
        assert "X Z1" not in {u.name for u in self.model().unmapped_settings}

    def test_every_raw_setting_is_accounted_for(self):
        model = self.model()
        every = {"s1", "s2", "s3", "s4"}
        assert model.referenced_setting_ids() == every


class TestProvenanceAndVersioning:
    def test_every_mapped_value_records_source_catalog_canonical_and_authority(self):
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"), version="2.3.1")
        x = z(interpret(data, doc(("X Z1", "6", "0-100")))).x_reach_ohm
        p = x.provenance
        assert p.raw_value == "6" and p.sources[0].parameter_name == "X Z1" and (p.sources[0].page, p.sources[0].location) == (1, "page 1, line 1")
        assert (p.catalog_id, p.catalog_version, p.canonical_id) == ("acme-x1", "2.3.1", "distance.zone.x_reach")
        assert p.authority is MappingAuthority.CONFIGURED_SETTING
        assert (p.profile_id, p.profile_version) == ("acme-x1", "acme-x1-v2.3.1")

    def test_an_unresolved_value_still_says_which_catalog_failed_to_read_it(self):
        x = z(interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), doc())).x_reach_ohm
        assert (x.provenance.catalog_id, x.provenance.catalog_version, x.provenance.canonical_id) == ("acme-x1", "1.0.0", "distance.zone.x_reach")

    def test_the_interpretation_retains_the_catalog_version_that_produced_it(self):
        scheme_doc = doc(("Header", "Scheme: X1_V3.1_demo"), ("X Z1", "6", "0-100"))
        v1 = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach")), scheme_doc)
        v2 = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach"), version="1.1.0"), scheme_doc)
        assert (v1.metadata.profile_version, v2.metadata.profile_version) == ("acme-x1-v1.0.0", "acme-x1-v1.1.0")
        assert v1.metadata.scheme_name.provenance.catalog_version == "1.0.0" and v2.metadata.scheme_name.provenance.catalog_version == "1.1.0"

    def test_relay_identity_comes_from_the_catalog_and_cites_the_documents_scheme_field(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach"),
                                       identification={"scheme_model_pattern": "X-?1", "version_pattern": "(V\\d+(?:\\.\\d+)*)"}),
                          doc(("Header", "Scheme: X1_V3.1_demo")))
        m = model.metadata
        assert (m.manufacturer.value, m.family.value, m.model.value, m.version.value) == ("Acme", "X-Series", "X1", "V3.1")
        assert m.scheme_name.value == "X1_V3.1_demo" and m.model.provenance.sources[0].parameter_name == "Header"

    def test_a_scheme_naming_another_relay_leaves_identity_unclaimed(self):
        model = interpret(catalog_json(num("X {zone}", "distance.zone.x_reach"), identification={"scheme_model_pattern": "^X-?1"}),
                          doc(("Header", "Scheme: Q9_other")))
        assert not model.metadata.model.is_resolved and model.metadata.scheme_name.value == "Q9_other"

    def test_the_model_survives_the_review_context_round_trip(self):
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"),
                            mapping("d", "distance.zone.r_right", zone="*", source={"name": "R {zone}", "type": "number", "unit": "ohm"},
                                    transform={"type": "divide", "by": 2}, authority="documented_derivation", confidence="inferred"))
        model = interpret(data, doc(("X Z1", "6"), ("R Z1", "7")))
        again = decode_model(encode_model(model))
        r = z(again).resistive_reach.phase_phase.provenance
        assert (r.catalog_id, r.catalog_version, r.canonical_id, r.transformation) == ("acme-x1", "1.0.0", "distance.zone.r_right", "7 ÷ 2 = 3.5")
        assert r.authority is MappingAuthority.DOCUMENTED_DERIVATION

    def test_interpretation_does_not_mutate_the_catalog_or_the_document(self):
        data = catalog_json(num("X {zone}", "distance.zone.x_reach"))
        snapshot = copy.deepcopy(data)
        interpret(data, doc(("X Z1", "6")))
        assert data == snapshot and parse(data) == parse(snapshot)


class TestZoneDiscovery:
    def test_zones_are_discovered_from_the_document_by_the_catalogs_pattern(self):
        data = catalog_json(num("ZM{nn}-:X1", "distance.zone.x_reach"),
                            zones={"discover": {"name_pattern": "^ZM(?P<n>\\d{2})-:", "id": "Z{n}", "name": "Zone {n}"}})
        model = interpret(data, doc(("ZM01-:X1", "6"), ("ZM03-:X1", "20"), ("ZM12-:X1", "99")))
        assert [(zz.zone_id, zz.name) for zz in model.zones] == [("Z1", "Zone 1"), ("Z3", "Zone 3"), ("Z12", "Zone 12")]
        assert [zz.x_reach_ohm.value for zz in model.zones] == [6.0, 20.0, 99.0]

    def test_a_document_without_zones_yields_none(self):
        data = catalog_json(num("ZM{nn}-:X1", "distance.zone.x_reach"),
                            zones={"discover": {"name_pattern": "^ZM(?P<n>\\d{2})-:", "id": "Z{n}", "name": "Zone {n}"}})
        assert interpret(data, doc(("Other", "1"))).zones == ()
