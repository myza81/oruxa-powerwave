"""Strict schema + semantic validation of the canonical registry and of OEM catalogs.

Every rule the catalog validator enforces has a test here: an invalid catalog is refused before
use, every problem is reported, and none is silently ignored.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.domain.parameter_catalog.errors import CatalogValidationError, IssueCode
from app.domain.parameter_catalog.loader import CATALOG_ROOT, REGISTRY_FILE, canonical_registry
from app.domain.parameter_catalog.registry import parse_registry
from tests.parameter_catalog_helpers import catalog_json, mapping, parse


def codes_of(data) -> frozenset[str]:
    with pytest.raises(CatalogValidationError) as err:
        parse(data)
    return err.value.codes()


def x_reach(**kw):
    return mapping("m.x", "distance.zone.x_reach", zone="*", source={"name": "X{zone}", "type": "number", "unit": "ohm"}, **kw)


def registry_json():
    return json.loads((CATALOG_ROOT / REGISTRY_FILE).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The canonical registry
# ---------------------------------------------------------------------------


class TestCanonicalRegistry:
    def test_the_shipped_registry_loads_and_covers_the_initial_distance_scope(self):
        reg = canonical_registry()
        for canonical in (
            "ct_vt.ct_primary", "ct_vt.ct_secondary", "ct_vt.vt_primary", "ct_vt.vt_secondary", "ct_vt.impedance_basis",
            "ct_vt.voltage_base", "ct_vt.current_base", "line.length", "line.angle", "line.positive_sequence_impedance",
            "line.zero_sequence_impedance", "distance.zone.status", "distance.zone.direction", "distance.zone.characteristic",
            "distance.zone.geometry_mode", "distance.zone.reach", "distance.zone.reach_angle", "distance.zone.x_reach",
            "distance.zone.r_right", "distance.zone.r_left", "distance.zone.r_phase_earth", "distance.zone.phase_delay",
            "distance.zone.earth_delay", "distance.zone.pp_enabled", "distance.zone.pe_enabled",
            "distance.zone.comp.k0_magnitude", "distance.zone.comp.kr", "distance.zone.comp.re_rl",
            "relay.manufacturer", "relay.model", "relay.version",
        ):
            assert canonical in reg, canonical

    def test_every_parameter_carries_label_type_unit_group_order_and_engine_path(self):
        for p in canonical_registry().parameters:
            assert p.label and p.data_type and p.group in canonical_registry().groups and isinstance(p.order, int)
            assert p.engine_path or p.component_of, p.id

    def test_engine_path_distinguishes_zone_and_document_level(self):
        reg = canonical_registry()
        assert reg.get("distance.zone.r_right").engine_path == "zones[].resistive_reach.phase_phase"
        assert reg.get("ct_vt.ct_primary").engine_path == "transformers.ct_primary_a"
        assert reg.get("distance.zone.directional_angle_dir").extra_name == "directional_arg_dir"

    def test_a_label_can_depend_on_the_geometry_of_the_zone(self):
        r = canonical_registry().get("distance.zone.r_right")
        assert (r.label_for("polar_reach"), r.label_for("explicit_rx")) == ("Phase-Phase Resistive Reach", "Right Resistive Reach (+R)")

    def test_review_paths_resolve_to_their_canonical_parameter(self):
        reg = canonical_registry()
        assert reg.for_review_path("zones[Z3].resistive_reach.reverse").id == "distance.zone.r_left"
        assert reg.for_review_path("transformers.vt_primary_v").label == "VT Primary"
        assert reg.for_review_path("zones[Z1].characteristic.parameters[directional_arg_dir].value").id == "distance.zone.directional_angle_dir"
        assert reg.for_review_path("zones[Z1].nothing") is None

    @pytest.mark.parametrize("mutate,code", [
        (lambda d: d["parameters"][0].update(unit="furlong"), IssueCode.INVALID_UNIT),
        (lambda d: d["parameters"].append(copy.deepcopy(d["parameters"][0])), IssueCode.DUPLICATE),
        (lambda d: d["parameters"][0].update(engine_path="metadata.no_such_field"), IssueCode.MALFORMED),
        (lambda d: d["parameters"][0].update(engine_path="zones[].status"), IssueCode.MALFORMED),
        (lambda d: d["parameters"][0].update(label=""), IssueCode.MISSING_METADATA),
        (lambda d: d["parameters"][0].update(bogus=1), IssueCode.UNKNOWN_FIELD),
        (lambda d: d["parameters"][0].update(group="nowhere"), IssueCode.MALFORMED),
        (lambda d: d["parameters"][0].update(data_type="complex"), IssueCode.MALFORMED),
        (lambda d: d["parameters"][0].update(enum_type="ZoneStatus"), IssueCode.INVALID_ENUM),
        (lambda d: d["parameters"][1].update(engine_path=d["parameters"][0]["engine_path"]), IssueCode.DUPLICATE),
        (lambda d: d["parameters"][0].update(applies_when={"weather": "rain"}), IssueCode.UNKNOWN_FIELD),
        (lambda d: d.update(schema="other/1"), IssueCode.MALFORMED),
    ])
    def test_an_invalid_registry_is_refused(self, mutate, code):
        data = registry_json()
        mutate(data)
        with pytest.raises(CatalogValidationError) as err:
            parse_registry(data)
        assert code in err.value.codes()

    def test_an_extra_name_is_only_valid_on_a_tuple_of_extra_quantities(self):
        data = registry_json()
        param = next(p for p in data["parameters"] if p["id"] == "distance.zone.x_reach")
        param["engine_path"] = "zones[].x_reach_ohm{oops}"
        with pytest.raises(CatalogValidationError) as err:
            parse_registry(data)
        assert IssueCode.MALFORMED in err.value.codes()


# ---------------------------------------------------------------------------
# Catalog schema
# ---------------------------------------------------------------------------


class TestCatalogSchema:
    def test_a_minimal_valid_catalog_parses(self):
        cat = parse(catalog_json(x_reach()))
        assert (cat.catalog_id, cat.version, cat.lifecycle) == ("acme-x1", "1.0.0", "tested")
        assert cat.key == "acme-x1@1.0.0" and cat.profile_version == "acme-x1-v1.0.0" and cat.profile_id == "acme-x1"

    def test_a_non_object_is_refused(self):
        with pytest.raises(CatalogValidationError):
            parse([])

    @pytest.mark.parametrize("key", ["catalog_id", "version", "lifecycle", "applicability", "zones"])
    def test_missing_required_metadata_is_refused(self, key):
        data = catalog_json(x_reach())
        del data[key]
        assert IssueCode.MISSING_METADATA in codes_of(data)

    def test_applicability_needs_manufacturer_family_and_model(self):
        data = catalog_json(x_reach())
        del data["applicability"]["model"]
        assert IssueCode.MISSING_METADATA in codes_of(data)

    @pytest.mark.parametrize("version", ["1.0", "v1.0.0", "1.0.0-beta", ""])
    def test_a_version_must_be_major_minor_patch(self, version):
        assert codes_of(catalog_json(x_reach(), version=version)) & {IssueCode.INVALID_VERSION, IssueCode.MISSING_METADATA}

    def test_lifecycle_must_be_one_of_the_states(self):
        assert IssueCode.INVALID_LIFECYCLE in codes_of(catalog_json(x_reach(), lifecycle="published"))

    def test_unknown_keys_are_refused_not_ignored(self):
        assert IssueCode.UNKNOWN_FIELD in codes_of(catalog_json(x_reach(), surprise=True))
        bad = x_reach()
        bad["colour"] = "red"
        assert IssueCode.UNKNOWN_FIELD in codes_of(catalog_json(bad))

    def test_the_schema_marker_must_match(self):
        assert IssueCode.MALFORMED in codes_of(catalog_json(x_reach(), schema="oruxa.parameter-catalog/9"))

    def test_a_registry_major_version_mismatch_is_refused(self):
        assert IssueCode.INVALID_VERSION in codes_of(catalog_json(x_reach(), registry_version="2.0.0"))

    def test_a_catalog_past_draft_needs_mappings_but_a_draft_may_be_empty(self):
        assert IssueCode.MISSING_METADATA in codes_of(catalog_json())
        assert parse(catalog_json(lifecycle="draft")).mappings == ()

    def test_every_problem_is_reported_at_once(self):
        data = catalog_json(
            mapping("a", "no.such.parameter", zone="*", source={"name": "A"}),
            mapping("b", "distance.zone.x_reach", zone="Z9", source={"name": "B", "unit": "furlong"}),
            version="x",
        )
        with pytest.raises(CatalogValidationError) as err:
            parse(data)
        assert {IssueCode.UNKNOWN_CANONICAL, IssueCode.INVALID_ZONE, IssueCode.INVALID_UNIT, IssueCode.INVALID_VERSION} <= err.value.codes()
        assert len(err.value.issues) >= 4
        assert "validation issue" in str(err.value)


# ---------------------------------------------------------------------------
# Catalog semantics
# ---------------------------------------------------------------------------


class TestCanonicalTargets:
    def test_an_unknown_canonical_target_is_refused(self):
        assert IssueCode.UNKNOWN_CANONICAL in codes_of(catalog_json(mapping("m", "distance.zone.warp_factor", zone="*", source={"name": "W"})))

    def test_a_component_cannot_be_mapped_directly(self):
        assert IssueCode.UNKNOWN_CANONICAL in codes_of(
            catalog_json(mapping("m", "distance.zone.reach_angle", zone="*", source={"name": "A", "type": "number", "unit": "deg"})))

    def test_relay_identity_comes_from_the_catalog_header_not_a_mapping(self):
        assert IssueCode.UNKNOWN_CANONICAL in codes_of(catalog_json(mapping("m", "relay.model", source={"name": "Model"})))


class TestZoneTargets:
    def test_a_zone_parameter_needs_a_zone_target(self):
        assert IssueCode.INVALID_ZONE in codes_of(catalog_json(mapping("m", "distance.zone.x_reach", source={"name": "X", "type": "number", "unit": "ohm"})))

    def test_a_document_parameter_takes_no_zone(self):
        assert IssueCode.INVALID_ZONE in codes_of(catalog_json(mapping("m", "ct_vt.ct_primary", zone="Z1", source={"name": "CT", "type": "number", "unit": "A"})))

    def test_a_zone_the_catalog_does_not_define_is_refused(self):
        assert IssueCode.INVALID_ZONE in codes_of(catalog_json(mapping("m", "distance.zone.x_reach", zone="Z9", source={"name": "X", "type": "number", "unit": "ohm"})))

    def test_wildcard_cannot_be_mixed_with_ids(self):
        assert IssueCode.INVALID_ZONE in codes_of(catalog_json(mapping("m", "distance.zone.x_reach", zone=["*", "Z1"], source={"name": "X", "type": "number", "unit": "ohm"})))

    def test_discovered_zones_can_only_be_targeted_with_a_wildcard(self):
        data = catalog_json(
            mapping("m", "distance.zone.x_reach", zone="Z1", source={"name": "ZM{nn}-:X1", "type": "number", "unit": "ohm"}),
            zones={"discover": {"name_pattern": "^ZM(?P<n>\\d{2})-:", "id": "Z{n}", "name": "Zone {n}"}},
        )
        assert IssueCode.INVALID_ZONE in codes_of(data)

    def test_the_zone_templates_must_use_the_instance_number(self):
        data = catalog_json(x_reach(), zones={"discover": {"name_pattern": "^ZM(?P<n>\\d{2})-:", "id": "Zone", "name": "Zone {n}"}})
        assert IssueCode.INVALID_ZONE in codes_of(data)

    def test_the_discovery_pattern_needs_the_n_group(self):
        data = catalog_json(x_reach(), zones={"discover": {"name_pattern": "^ZM(\\d{2})-:", "id": "Z{n}", "name": "Zone {n}"}})
        assert IssueCode.INVALID_SELECTOR in codes_of(data)

    def test_duplicate_static_zone_ids_are_refused(self):
        data = catalog_json(x_reach(), zones={"static": [{"id": "Z1", "name": "a"}, {"id": "Z1", "name": "b"}]})
        assert IssueCode.DUPLICATE in codes_of(data)


class TestUnitsAndValueSources:
    def test_an_unknown_source_unit_is_refused(self):
        assert IssueCode.INVALID_UNIT in codes_of(catalog_json(
            mapping("m", "distance.zone.x_reach", zone="*", source={"name": "X", "type": "number", "unit": "furlong"})))

    def test_a_unit_with_no_listed_conversion_is_refused(self):
        assert IssueCode.INVALID_UNIT in codes_of(catalog_json(
            mapping("m", "distance.zone.x_reach", zone="*", source={"name": "X", "type": "number", "unit": "s"})))

    def test_a_listed_conversion_is_accepted(self):
        parse(catalog_json(mapping("m", "ct_vt.vt_primary", source={"name": "VT", "type": "number", "unit": "kV"})))

    def test_a_dimensionless_target_cannot_take_a_united_source(self):
        assert IssueCode.INVALID_UNIT in codes_of(catalog_json(
            mapping("m", "distance.zone.comp.k0_magnitude", zone="*", source={"name": "K", "type": "number", "unit": "ohm"})))

    @pytest.mark.parametrize("source", ["range", "default", "document_note"])
    def test_a_range_default_or_note_can_never_be_the_configured_setting(self, source):
        assert IssueCode.INVALID_VALUE_SOURCE in codes_of(catalog_json(x_reach(value_source=source)))

    def test_an_unknown_value_source_is_refused(self):
        assert IssueCode.INVALID_VALUE_SOURCE in codes_of(catalog_json(x_reach(value_source="gossip")))

    def test_authority_and_value_source_must_agree(self):
        assert IssueCode.INVALID_VALUE_SOURCE in codes_of(catalog_json(x_reach(authority="engineering_instruction")))
        assert IssueCode.INVALID_VALUE_SOURCE in codes_of(catalog_json(x_reach(authority="configured_setting", value_source="engineering_instruction")))

    def test_an_assumption_can_never_be_reported_as_mapped(self):
        assert IssueCode.INVALID_VALUE_SOURCE in codes_of(catalog_json(x_reach(authority="assumption", confidence="mapped")))
        parse(catalog_json(x_reach(authority="assumption", confidence="inferred")))


class TestTransforms:
    def test_an_unsupported_transformation_is_refused(self):
        bad = x_reach(transform={"type": "eval", "code": "__import__('os')"})
        assert IssueCode.UNSUPPORTED_TRANSFORM in codes_of(catalog_json(bad))

    def test_no_executable_code_can_ride_in_a_step(self):
        bad = x_reach(transform={"type": "divide", "by": 2, "python": "x/2"})
        assert IssueCode.INVALID_TRANSFORM in codes_of(catalog_json(bad))

    @pytest.mark.parametrize("step", [
        {"type": "divide", "by": 0},
        {"type": "divide"},
        {"type": "divide", "by": "two"},
        {"type": "unit_conversion", "from": "ohm", "to": "A"},
        {"type": "unit_conversion", "from": "parsec", "to": "A"},
        {"type": "scale", "factor": True},
        {"type": "percentage", "direction": "sideways"},
        {"type": "bitmask", "bit": 1, "mask": 2},
        {"type": "bitmask"},
        {"type": "regex", "pattern": "(unclosed"},
        {"type": "regex", "pattern": "no group"},
        {"type": "enum", "map": {}},
        {"type": "boolean", "true_values": "on"},
    ])
    def test_bad_parameters_are_refused(self, step):
        data = catalog_json(
            mapping("m", "distance.zone.x_reach", zone="*", source={"name": "X", "type": "number", "unit": "ohm"}, transform=step))
        assert codes_of(data) & {IssueCode.INVALID_TRANSFORM, IssueCode.UNSUPPORTED_TRANSFORM}

    def test_a_chain_is_type_checked(self):
        # enum reads text; the source here is a number
        data = catalog_json(mapping("m", "distance.zone.direction", zone="*", source={"name": "D", "type": "number"},
                                    transform={"type": "enum", "map": {"1": "forward"}}))
        assert IssueCode.INVALID_TRANSFORM in codes_of(data)

    def test_the_result_type_must_suit_the_canonical_parameter(self):
        data = catalog_json(mapping("m", "distance.zone.x_reach", zone="*", source={"name": "X"}, transform={"type": "boolean"}))
        assert IssueCode.INVALID_TRANSFORM in codes_of(data)

    def test_an_enum_parameter_needs_a_mapping_of_its_text(self):
        assert IssueCode.INVALID_TRANSFORM in codes_of(catalog_json(mapping("m", "distance.zone.direction", zone="*", source={"name": "D"})))

    def test_assembly_primitives_must_come_first_and_take_named_sources(self):
        data = catalog_json(mapping("m", "distance.zone.zero_sequence_reach", zone="*",
                                    source={"name": "R", "type": "number", "unit": "ohm"}, transform={"type": "impedance_rx"}))
        assert codes_of(data) & {IssueCode.MALFORMED, IssueCode.INVALID_TRANSFORM}
        data = catalog_json(mapping("m", "distance.zone.zero_sequence_reach", zone="*",
                                    sources={"r": {"name": "R", "type": "number", "unit": "ohm"}}, transform={"type": "impedance_rx"}))
        assert IssueCode.INVALID_TRANSFORM in codes_of(data)  # the x input is missing

    def test_a_describe_template_may_use_only_the_known_placeholders(self):
        bad = x_reach(transform={"type": "divide", "by": 2, "describe": "{secret} / 2"})
        assert IssueCode.INVALID_TRANSFORM in codes_of(catalog_json(bad))

    def test_a_constant_must_cite_evidence_unless_the_field_is_plain(self):
        bad = mapping("m", "distance.zone.characteristic", zone="*", transform={"type": "constant", "value": "quadrilateral"})
        assert IssueCode.INVALID_TRANSFORM in codes_of(catalog_json(bad))
        parse(catalog_json(mapping("g", "distance.zone.geometry_mode", zone="*", transform={"type": "constant", "value": "explicit_rx"})))


class TestEnumMappings:
    def test_an_enum_map_value_outside_the_canonical_enum_is_refused(self):
        data = catalog_json(mapping("m", "distance.zone.direction", zone="*", source={"name": "D"},
                                    transform={"type": "enum", "map": {"fwd": "sideways"}}))
        assert IssueCode.INVALID_ENUM in codes_of(data)

    def test_a_constant_outside_the_enum_is_refused(self):
        data = catalog_json(mapping("m", "distance.zone.geometry_mode", zone="*", transform={"type": "constant", "value": "squircle"}))
        assert IssueCode.INVALID_ENUM in codes_of(data)

    def test_a_decision_table_result_outside_the_enum_is_refused(self):
        data = catalog_json(mapping(
            "m", "distance.zone.status", zone="*", sources={"op": {"name": "Op"}},
            transform={"type": "decision_table", "rules": [{"when": {"op": "on"}, "value": "humming"}]}))
        assert IssueCode.INVALID_ENUM in codes_of(data)

    def test_a_boolean_parameter_rejects_text_literals(self):
        data = catalog_json(mapping("m", "distance.zone.pp_enabled", zone="*", source={"name": "PP"},
                                    transform={"type": "enum", "map": {"on": "yes"}}))
        assert IssueCode.INVALID_TRANSFORM in codes_of(data)


class TestSelectors:
    @pytest.mark.parametrize("selector", [
        {},
        {"name": "A", "name_pattern": "A"},
        {"name_pattern": "(unclosed"},
        {"pattern_in_text": "no group"},
        {"name": ""},
        {"code": 7},
        {"name": "A", "printed_unit": {"policy": "sometimes"}},
        {"name": "A", "validate": {"within_printed_range": "yes"}},
        {"name": "A", "allowed_text": "on"},
        {"name": "A", "type": "complex"},
        {"name": "A", "mystery": 1},
    ])
    def test_a_malformed_selector_is_refused(self, selector):
        data = catalog_json(mapping("m", "distance.zone.x_reach", zone="*", source=selector))
        assert codes_of(data) & {IssueCode.INVALID_SELECTOR, IssueCode.MALFORMED, IssueCode.UNKNOWN_FIELD}

    def test_a_template_variable_must_be_available_in_the_mapping_scope(self):
        assert IssueCode.INVALID_SELECTOR in codes_of(catalog_json(mapping("m", "ct_vt.ct_primary", source={"name": "CT{n}", "type": "number", "unit": "A"})))

    def test_instance_numbers_need_discovered_zones(self):
        assert IssueCode.INVALID_SELECTOR in codes_of(catalog_json(
            mapping("m", "distance.zone.x_reach", zone="*", source={"name": "X{nn}", "type": "number", "unit": "ohm"})))

    def test_an_indexed_family_needs_a_numbered_member_and_a_named_group(self):
        family = {"index": {"name_pattern": "^CH(?P<n>\\d+)$", "value_pattern": "IL"}, "member": "CTprim"}
        assert IssueCode.INVALID_SELECTOR in codes_of(catalog_json(
            mapping("m", "ct_vt.ct_primary", source={"indexed_family": family, "type": "number", "unit": "A"})))
        family = {"index": {"name_pattern": "^CH(\\d+)$", "value_pattern": "IL"}, "member": "CTprim{n}"}
        assert IssueCode.INVALID_SELECTOR in codes_of(catalog_json(
            mapping("m", "ct_vt.ct_primary", source={"indexed_family": family, "type": "number", "unit": "A"})))

    def test_a_zone_family_is_for_document_level_mappings_only(self):
        fam = {"member": "{zone}.IBase"}
        assert IssueCode.INVALID_SELECTOR in codes_of(catalog_json(
            mapping("m", "distance.zone.x_reach", zone="*", source={"zone_family": fam, "type": "number", "unit": "ohm"})))

    def test_a_code_with_its_expected_name_is_a_single_match(self):
        parse(catalog_json(mapping("m", "ct_vt.ct_primary", source={"code": "0A07", "name": "Phase CT Primary", "type": "number", "unit": "A"})))


class TestDuplicatesAndConflicts:
    def test_a_duplicate_mapping_id_is_refused(self):
        assert IssueCode.DUPLICATE in codes_of(catalog_json(x_reach(), mapping("m.x", "distance.zone.r_right", zone="*", source={"name": "R", "type": "number", "unit": "ohm"})))

    def test_the_same_mapping_twice_is_a_duplicate(self):
        a = x_reach()
        b = copy.deepcopy(a)
        b["id"] = "m.x2"
        assert IssueCode.DUPLICATE in codes_of(catalog_json(a, b))

    def test_two_different_sources_for_one_target_at_one_precedence_conflict(self):
        a = x_reach()
        b = mapping("m.x2", "distance.zone.x_reach", zone="*", source={"name": "OTHER", "type": "number", "unit": "ohm"})
        assert IssueCode.CONFLICT in codes_of(catalog_json(a, b))

    def test_a_wildcard_overlaps_an_explicit_zone(self):
        a = x_reach()
        b = mapping("m.x2", "distance.zone.x_reach", zone="Z1", source={"name": "OTHER", "type": "number", "unit": "ohm"})
        assert IssueCode.CONFLICT in codes_of(catalog_json(a, b))

    def test_alternatives_at_different_precedence_are_allowed(self):
        a = x_reach()
        b = mapping("m.x2", "distance.zone.x_reach", zone="*", source={"name": "OTHER", "type": "number", "unit": "ohm"},
                    authority="assumption", confidence="inferred")
        parse(catalog_json(a, b))

    def test_distinct_zones_do_not_conflict(self):
        a = mapping("a", "distance.zone.x_reach", zone="Z1", source={"name": "A", "type": "number", "unit": "ohm"})
        b = mapping("b", "distance.zone.x_reach", zone="Z2", source={"name": "B", "type": "number", "unit": "ohm"})
        parse(catalog_json(a, b))

    def test_mixed_residual_compensation_kinds_in_one_zone_conflict(self):
        a = mapping("a", "distance.zone.comp.k0_magnitude", zone="Z1", source={"name": "K0", "type": "number", "unit": ""})
        b = mapping("b", "distance.zone.comp.kr", zone="Z1", source={"name": "KR", "type": "number", "unit": ""})
        assert IssueCode.CONFLICT in codes_of(catalog_json(a, b))


class TestReferences:
    def test_a_dependency_must_be_mapped_before_it_is_used(self):
        later = mapping("c", "distance.zone.characteristic", zone="*", transform={"type": "constant", "value": "quadrilateral"},
                        evidence=[{"name": "HEAD"}], requires_resolved=["distance.zone.x_reach"])
        assert IssueCode.INVALID_REFERENCE in codes_of(catalog_json(later, x_reach()))
        parse(catalog_json(x_reach(), later))

    def test_a_dependency_on_an_unmapped_canonical_is_refused(self):
        c = mapping("c", "distance.zone.characteristic", zone="*", transform={"type": "constant", "value": "quadrilateral"},
                    evidence=[{"name": "HEAD"}], requires_resolved=["distance.zone.x_reach"])
        assert IssueCode.INVALID_REFERENCE in codes_of(catalog_json(c))

    def test_an_unknown_dependency_is_refused(self):
        c = mapping("c", "distance.zone.characteristic", zone="*", transform={"type": "constant", "value": "quadrilateral"},
                    evidence=[{"name": "HEAD"}], evidence_from=["nope.nothing"])
        assert IssueCode.UNKNOWN_CANONICAL in codes_of(catalog_json(c))

    def test_a_conditional_printed_unit_must_depend_on_an_earlier_document_value(self):
        sel = {"name": "R", "type": "number", "unit": "ohm",
               "printed_unit": {"policy": "required", "accept_if": [{"text": "/I1", "when": {"canonical": "ct_vt.ct_secondary", "equals": 1}}]}}
        z = mapping("r", "distance.zone.x_reach", zone="*", source=sel)
        ct = mapping("ct", "ct_vt.ct_secondary", source={"name": "CTsec", "type": "number", "unit": "A"})
        assert IssueCode.INVALID_REFERENCE in codes_of(catalog_json(z))          # the CT secondary is not mapped
        parse(catalog_json(ct, z))                                              # document level runs first
