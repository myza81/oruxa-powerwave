"""Generic catalog capabilities added for the remaining relay families (relay-neutral, synthetic data only).

* ``source_notes``      -- document notes about a zone become that zone's `SourceNote`s: provenance only.
* ``zone_preserved``    -- raw zone settings kept with their zone, uninterpreted (a visible capability gap).
* listed zone ``key``   -- a template token other than the zone id (``Z_PP1`` / ``Z_Rev``).
* blank setting cell    -- a cell the extractor established as blank is Missing, never Unreadable or a range.
* ``distance_scope.name_patterns`` -- codes written inside setting names classify leftovers.
* ``"manufacturer": null`` -- a manufacturer the project has not established is never asserted.
* CT / VT ratio         -- canonical fields for relays that state ratios, shown only when stated.
* selector ``note``     -- the catalog's own words when a source cannot be read.
"""

from __future__ import annotations

import copy

import pytest

from app.domain.parameter_catalog.catalog_first import overlay
from app.domain.parameter_catalog.coverage import compute_coverage
from app.domain.parameter_catalog.errors import CatalogValidationError
from app.domain.parameter_catalog.interpreter import ZONE_NOTES_STATEMENT, CatalogInterpreter
from app.domain.parameter_catalog.loader import canonical_registry, semantics_digest
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    DistanceZone,
    RelayMetadata,
    SourceNoteKind,
)
from app.domain.relay_import.provenance import UnresolvedCause
from app.domain.relay_import.raw_document import (
    ExtractionProvenance,
    RawRelayDocument,
    RawSetting,
    SettingRange,
    SourceFormat,
    SourceLocation,
)
from tests.parameter_catalog_helpers import catalog_json, doc, interpret, mapping, parse

NOTE_RULE = {
    "pattern": "^Zone\\s+(?P<zone>\\d+R?)\\s+(?:Forward|Reverse|Inactive)",
    "zone_id": "Z{zone}",
    "zone_ids": {"3R": "Z2"},
    "subjects": [
        {"subject": "timer", "pattern": "(?i)timer\\s+set\\s+to\\s+([0-9.]+)\\s*s\\b", "value": "{1} s"},
        {"subject": "status", "pattern": "(?i)\\binactive\\b", "value": "Inactive (out of service)"},
    ],
}

X_REACH = mapping("x", "distance.zone.x_reach", zone="*", source={"name": "{zone} X", "type": "number", "unit": "ohm"})
DELAY = mapping("t", "distance.zone.common_delay", zone="*", source={"name": "{zone} T", "type": "number", "unit": "s"})


def run(data, document):
    catalog = parse(data)
    return catalog, CatalogInterpreter(catalog, canonical_registry()).run(document)


class TestZoneDocumentNotes:
    DOC = doc(
        ("Z1 X", "4"), ("Z1 T", "0.4"), ("Z2 X", "8"),
        ("Zone 1 Forward direction timer set to 0.15s", None),
        ("Zone 3R", "Reverse direction timer set to 3s"),
        ("Zone 9 Forward direction timer set to 1s", None),
        ("Zone 2 Inactive (not in use)", None),
    )

    def test_notes_become_zone_source_notes_with_their_subject_and_source(self):
        model = interpret(catalog_json(X_REACH, DELAY, source_notes=[NOTE_RULE]), self.DOC)
        z1, z2 = model.zones
        assert [n.text for n in z1.source_notes] == ["Zone 1 Forward direction timer set to 0.15s"]
        note = z1.source_notes[0]
        assert (note.kind, note.subject, note.value_text) == (SourceNoteKind.PROPOSED_REQUIREMENT, "timer", "0.15 s")
        assert note.sources[0].setting_id == "s4" and note.sources[0].page == 1
        # an explicit token override and a name/value split row ("Zone 3R" | "Reverse ...")
        assert [n.text for n in z2.source_notes] == ["Zone 3R  Reverse direction timer set to 3s", "Zone 2 Inactive (not in use)"]
        assert [(n.subject, n.value_text) for n in z2.source_notes] == [("timer", "3 s"), ("status", "Inactive (out of service)")]
        assert ZONE_NOTES_STATEMENT in model.interpretation_notes

    def test_a_note_never_becomes_a_value_a_status_or_a_default(self):
        model = interpret(catalog_json(X_REACH, DELAY, source_notes=[NOTE_RULE]), self.DOC)
        z1, z2 = model.zones
        assert z1.common_timer_s.value == 0.4                                 # the setting, not the note's 0.15
        assert not z2.common_timer_s.is_resolved                              # the note's 3 s is never used
        assert not z2.status.is_resolved                                      # "Inactive" in a note is not a state

    def test_a_note_about_a_zone_the_document_does_not_have_stays_raw(self):
        model = interpret(catalog_json(X_REACH, DELAY, source_notes=[NOTE_RULE]), self.DOC)
        assert "s6" in {u.setting_id for u in model.unmapped_settings}
        assert "s4" not in {u.setting_id for u in model.unmapped_settings}
        assert {"s4", "s5", "s7"} <= model.referenced_setting_ids()

    def test_notes_are_counted_as_not_interpreted_never_as_mapped(self):
        catalog, run_ = run(catalog_json(X_REACH, DELAY, source_notes=[NOTE_RULE]), self.DOC)
        cov = compute_coverage(catalog, self.DOC, run_, run_.model)
        assert run_.note_ids == {"s4", "s5", "s7"}
        assert cov.catalog_mapped_settings == 3                               # Z1 X, Z1 T, Z2 X only
        assert cov.not_interpreted_settings + cov.outside_distance_settings == 4
        assert cov.catalog_recognised_settings + cov.unmapped_settings == cov.extracted_settings

    def test_without_rules_notes_are_ordinary_leftovers(self):
        model = interpret(catalog_json(X_REACH, DELAY), self.DOC)
        assert all(not z.source_notes for z in model.zones)
        assert ZONE_NOTES_STATEMENT not in model.interpretation_notes


class TestZonePreservedSettings:
    DOC = doc(("Z1 X", "4"), ("Z2 X", "8"), ("Z1 Blinder", "20"), ("Z2 Blinder", "25"), ("Common Angle", "75"),
              ("Hostname", "relay-1"))
    RULES = [
        {"zone": "*", "names": ["{zone} Blinder"], "reason": "blinder geometry cannot be represented"},
        {"zone": "*", "names": ["Common Angle"], "reason": "the boundary angle cannot be represented"},
    ]

    def test_raw_zone_settings_are_kept_with_their_zone_and_reason(self):
        model = interpret(catalog_json(X_REACH, zone_preserved=self.RULES), self.DOC)
        z1, z2 = model.zones
        assert [(u.name, u.raw_value, u.reason) for u in z1.unresolved_settings] == [
            ("Z1 Blinder", "20", "blinder geometry cannot be represented"),
            ("Common Angle", "75", "the boundary angle cannot be represented"),
        ]
        assert [u.name for u in z2.unresolved_settings] == ["Z2 Blinder", "Common Angle"]   # a shared setting, each zone
        assert {u.setting_id for u in model.unmapped_settings} == {"s6"}

    def test_a_pattern_is_templated_and_escaped_per_zone(self):
        rules = [{"zone": ["Z2"], "name_pattern": "^{zone} B", "reason": "kept"}]
        model = interpret(catalog_json(X_REACH, zone_preserved=rules), self.DOC)
        assert [u.name for u in model.zones[1].unresolved_settings] == ["Z2 Blinder"]
        assert not model.zones[0].unresolved_settings

    def test_a_mapped_setting_is_never_taken(self):
        rules = [{"zone": "*", "names": ["{zone} X"], "reason": "should not apply"}]
        model = interpret(catalog_json(X_REACH, zone_preserved=rules), self.DOC)
        assert all(not z.unresolved_settings for z in model.zones)
        assert model.zones[0].x_reach_ohm.value == 4.0

    def test_preserved_settings_count_as_recognised_unsupported(self):
        catalog, run_ = run(catalog_json(X_REACH, zone_preserved=self.RULES), self.DOC)
        cov = compute_coverage(catalog, self.DOC, run_, run_.model)
        assert run_.preserved_ids == {"s3", "s4", "s5"}
        assert (cov.catalog_mapped_settings, cov.catalog_unsupported_settings) == (2, 3)
        assert cov.catalog_recognised_settings + cov.unmapped_settings == cov.extracted_settings


class TestListedZoneKey:
    def test_a_key_stands_for_the_zone_token_in_names(self):
        data = catalog_json(
            mapping("t", "distance.zone.common_delay", zone="*", source={"name": "t_{key}", "type": "number", "unit": "s"}),
            zones={"static": [{"id": "Z1", "name": "Zone 1", "key": "1"}, {"id": "ZR", "name": "Reverse Zone", "key": "Rev"}]},
        )
        model = interpret(data, doc(("t_1", "0.2"), ("t_Rev", "3")))
        assert [z.common_timer_s.value for z in model.zones] == [0.2, 3.0]

    def test_without_a_key_the_token_is_the_zone_id(self):
        data = catalog_json(mapping("t", "distance.zone.common_delay", zone="*", source={"name": "t_{key}", "type": "number", "unit": "s"}))
        assert interpret(data, doc(("t_Z1", "0.2"))).zones[0].common_timer_s.value == 0.2

    def test_a_key_is_refused_with_discovered_zones(self):
        data = catalog_json(
            mapping("t", "distance.zone.common_delay", zone="*", source={"name": "t_{key}", "type": "number", "unit": "s"}),
            zones={"discover": {"name_pattern": "^Z(?P<n>\\d) X$", "id": "Z{n}", "name": "Zone {n}"}},
        )
        with pytest.raises(CatalogValidationError, match="key"):
            parse(data)


def _blank_row(setting_id: str, name: str, rng: str) -> RawSetting:
    return RawSetting(
        setting_id=setting_id, name=name, raw_value=None, setting_range=SettingRange(text=rng),
        location=SourceLocation(page=1, line=1),
        extraction=ExtractionProvenance("generic_pdf_text", "2", notes=("row:blank_value_range",)),
    )


class TestBlankSettingCell:
    def test_a_cell_the_extractor_established_as_blank_is_missing_and_the_range_is_not_a_value(self):
        document = RawRelayDocument(SourceFormat.PDF, (_blank_row("s1", "Z1 T", "Infinity"),))
        timer = interpret(catalog_json(DELAY), document).zones[0].common_timer_s
        assert not timer.is_resolved and timer.provenance.cause is UnresolvedCause.MISSING
        assert any("configured setting cell is blank" in n and "Infinity" in n and "not a setting" in n for n in timer.provenance.notes)
        assert timer.provenance.sources[0].setting_id == "s1"               # the row stays cited

    def test_an_empty_value_without_that_evidence_is_still_unreadable(self):
        timer = interpret(catalog_json(DELAY), doc(("Z1 T", ""))).zones[0].common_timer_s
        assert not timer.is_resolved and timer.provenance.cause is UnresolvedCause.UNREADABLE

    def test_an_infinity_setting_is_unreadable_never_a_delay_and_carries_the_catalogs_note(self):
        delay = copy.deepcopy(DELAY)
        delay["source"]["note"] = "an 'Infinity' setting is not a finite delay"
        timer = interpret(catalog_json(delay), doc(("Z1 T", "Infinity"))).zones[0].common_timer_s
        assert not timer.is_resolved and timer.provenance.cause is UnresolvedCause.UNREADABLE
        assert any("not a plain number -- an 'Infinity' setting is not a finite delay" in n for n in timer.provenance.notes)


class TestDistanceScopeNamePatterns:
    def test_codes_inside_names_mark_leftovers_as_distance_related(self):
        data = catalog_json(X_REACH, distance_scope={"name_patterns": ["^21\\.901\\."]})
        model = interpret(data, doc(("Z1 X", "4"), ("21.901.2311.107 Dist. characteristic angle", "82.7"), ("81.791 Record", "on")))
        scope = {u.name: u.out_of_scope for u in model.unmapped_settings}
        assert scope == {"21.901.2311.107 Dist. characteristic angle": False, "81.791 Record": True}

    def test_an_invalid_pattern_is_refused(self):
        with pytest.raises(CatalogValidationError):
            parse(catalog_json(X_REACH, distance_scope={"name_patterns": ["(unclosed"]}))


class TestUnassertedManufacturer:
    def test_an_explicit_null_manufacturer_is_never_asserted(self):
        data = catalog_json(X_REACH, applicability={"manufacturer": None, "family": "X-Series", "model": "X1"})
        model = interpret(data, doc(("Header", "Scheme: X1_V2"), ("Z1 X", "4")))
        assert model.metadata.model.value == "X1"
        assert not model.metadata.manufacturer.is_resolved
        assert "not asserted" in model.metadata.manufacturer.provenance.notes[0]

    def test_a_missing_manufacturer_key_is_still_an_error(self):
        with pytest.raises(CatalogValidationError):
            parse(catalog_json(X_REACH, applicability={"family": "X-Series", "model": "X1"}))


class TestCtVtRatio:
    def test_ratios_map_to_their_own_canonical_fields(self):
        data = catalog_json(
            mapping("ct", "ct_vt.ct_ratio", source={"name": "CT", "type": "number", "unit": ""}),
            mapping("vt", "ct_vt.vt_ratio", source={"name": "VT", "type": "number", "unit": ""}),
        )
        model = interpret(data, doc(("CT", "1200", "1-20000"), ("VT", "1200", "1-20000")))
        assert (model.transformers.ct_ratio.value, model.transformers.vt_ratio.value) == (1200.0, 1200.0)
        assert not model.transformers.ct_primary_a.is_resolved                    # never split into primary / secondary

    def test_the_review_shows_ratio_rows_only_when_the_relay_states_them(self):
        from app.services.relay_extraction_review import _Builder, _transformer_group  # noqa: PLC2701

        document = doc(("CT", "1200"))
        stated = interpret(catalog_json(mapping("ct", "ct_vt.ct_ratio", source={"name": "CT", "type": "number", "unit": ""})), document)
        plain = CanonicalDistanceProtectionModel(metadata=RelayMetadata(source_format=SourceFormat.PDF), zones=(DistanceZone("Z1"),))
        labels = lambda m: [i.label for i in _transformer_group(_Builder(document), m).items]  # noqa: E731
        assert labels(plain) == ["CT Primary", "CT Secondary", "VT Primary", "VT Secondary", "Setting Values Basis",
                                 "Voltage Base", "Current Base"]
        assert labels(stated) == ["CT Primary", "CT Secondary", "CT Ratio", "VT Primary", "VT Secondary",
                                  "Setting Values Basis", "Voltage Base", "Current Base"]


class TestLockDigestIsStable:
    def test_a_catalog_without_the_new_sections_keeps_its_digest(self):
        data = catalog_json(X_REACH)
        keys = ("applicability", "profile_id", "identification", "zones", "distance_scope", "mappings", "interpretation_notes")
        import hashlib
        import json

        legacy = hashlib.sha256(json.dumps({k: data.get(k) for k in keys}, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        assert semantics_digest(data) == legacy

    def test_the_new_sections_are_part_of_the_meaning(self):
        data = catalog_json(X_REACH)
        assert semantics_digest(data) != semantics_digest({**data, "source_notes": [NOTE_RULE]})
        assert semantics_digest(data) != semantics_digest({**data, "zone_preserved": TestZonePreservedSettings.RULES})


class TestValidation:
    @pytest.mark.parametrize("rule", [
        {"pattern": "^Zone (\\d+)"},                                                   # no named group "zone"
        {"pattern": "^Zone (?P<zone>\\d+)", "zone_id": "Z{n}"},                         # wrong template
        {"pattern": "^Zone (?P<zone>\\d+)", "subjects": [{"subject": "colour", "pattern": "x", "value": "y"}]},
        {"pattern": "^Zone (?P<zone>\\d+)", "unknown": 1},
    ])
    def test_malformed_note_rules_are_refused(self, rule):
        with pytest.raises(CatalogValidationError):
            parse(catalog_json(X_REACH, source_notes=[rule]))

    @pytest.mark.parametrize("rule", [
        {"zone": "*", "names": ["{zone} B"]},                                        # no reason
        {"zone": "*", "names": ["{zone} B"], "name_pattern": "B", "reason": "r"},   # both
        {"zone": "Z9", "names": ["B"], "reason": "r"},                               # unknown zone
        {"zone": "*", "name_pattern": "(", "reason": "r"},                           # bad regex
    ])
    def test_malformed_preserved_rules_are_refused(self, rule):
        with pytest.raises(CatalogValidationError):
            parse(catalog_json(X_REACH, zone_preserved=[rule]))


class TestCatalogFirstOverlay:
    def test_a_catalog_with_an_extension_keeps_its_own_notes_and_preserved_settings(self):
        document = doc(("Z1 X", "4"), ("Z1 Blinder", "20"), ("Zone 1 Forward direction timer set to 0.15s", None))
        catalog, run_ = run(catalog_json(X_REACH, source_notes=[NOTE_RULE], zone_preserved=TestZonePreservedSettings.RULES[:1]), document)
        base = CanonicalDistanceProtectionModel(metadata=RelayMetadata(source_format=SourceFormat.PDF),
                                                zones=(DistanceZone("Z1"), DistanceZone("Z2")))
        merged = overlay(base, run_, canonical_registry(), document, "ext-v1")
        z1 = merged.zones[0]
        assert [n.text for n in z1.source_notes] == ["Zone 1 Forward direction timer set to 0.15s"]
        assert [u.name for u in z1.unresolved_settings] == ["Z1 Blinder"]
        assert z1.x_reach_ohm.value == 4.0
