"""Relay Import Slice 5: relay identification framework.

Identification names the relay a document most likely belongs to. These tests
assert identity, evidence, ambiguity and unknown handling -- never an
engineering value, because none is read.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from app.domain.relay_import import (
    DEFAULT_RULES,
    EvidenceKind,
    IdentificationConfidence,
    IdentificationStatus,
    ManufacturerAliases,
    ParameterSignature,
    RawRelayDocument,
    RawSetting,
    RelayIdentificationDescriptor,
    RelayIdentifier,
    RelayProfileRegistry,
    SourceFormat,
)
from app.relay_profiles import identification_catalogue as catalogue
from app.relay_profiles.identification_catalogue import (
    IDENTIFICATION_DESCRIPTORS,
    MANUFACTURER_ALIASES,
    build_registry,
)

I = IdentificationStatus
APP = Path(__file__).resolve().parents[1] / "app"


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def _doc(*entries, hints: tuple[str, ...] = ()) -> RawRelayDocument:
    """entries: a text line, or a (name, value) pair."""
    settings = []
    for i, entry in enumerate(entries, start=1):
        if isinstance(entry, tuple):
            name, value = entry
            text = f"{name}    {value}"
        else:
            name, value, text = entry, None, entry
        settings.append(RawSetting(setting_id=f"s{i}", name=name, raw_value=value, source_text=text))
    return RawRelayDocument(SourceFormat.PDF, tuple(settings), identification_hints=hints)


def _header(scheme: str | None, *rest) -> list:
    """A setting-sheet header like the project's: the scheme sits on the same
    line as other text, separated by a wide gap."""
    lines = ["Issued By:     Date:     Checked by:"]
    if scheme is not None:
        lines.append(f"LZOP: 132kV AAAA - BBBB No. 1          Scheme: {scheme}")
    lines.extend(rest)
    return lines


GENERIC_DISTANCE_TEXT = [
    "Distance Protection",
    ("Zone 1 reach", "2.4"),
    ("R1", "1.84"),
    ("X1", "3.20"),
    ("K0", "0.67"),
    ("CT primary", "1200"),
    ("VT primary", "132"),
    ("Directional mode", "Forward"),
]


@pytest.fixture(scope="module")
def registry() -> RelayProfileRegistry:
    return build_registry()


# --------------------------------------------------------------------------
# Result model and rules
# --------------------------------------------------------------------------


class TestRulesAndModel:
    def test_scoring_constants_are_documented_and_stable(self):
        r = DEFAULT_RULES
        assert (r.scheme_model, r.labelled_model, r.model_mention, r.family_marker) == (100, 90, 10, 25)
        assert (r.parameter_signature, r.manufacturer_name) == (20, 10)
        assert (r.identify_threshold, r.ambiguity_margin) == (60, 30)

    def test_strong_evidence_outweighs_weak_by_construction(self):
        r = DEFAULT_RULES
        assert r.scheme_model >= r.identify_threshold and r.labelled_model >= r.identify_threshold
        # no single weak kind, at its cap, reaches the threshold on its own
        for cap in (r.model_mention_cap, r.family_marker_cap, r.parameter_signature_cap, r.manufacturer_name_cap):
            assert cap < r.identify_threshold

    def test_identified_result_carries_every_documented_field(self, registry):
        r = registry.identify(_doc(*_header("7SA6131_4AB02_3GA0")))
        assert r.status is I.IDENTIFIED and r.confidence is IdentificationConfidence.HIGH
        assert (r.manufacturer, r.relay_family, r.model) == ("Siemens", "SIPROTEC 4 7SA6", "7SA613")
        assert r.profile_id == "siemens-7sa613"
        assert r.scheme_name == "7SA6131_4AB02_3GA0"
        assert r.evidence and r.score == sum(e.points for e in r.evidence)
        assert r.candidates[0].profile_id == r.profile_id

    def test_models_are_immutable(self, registry):
        import dataclasses

        r = registry.identify(_doc("nothing"))
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.status = I.IDENTIFIED  # type: ignore[misc]


# --------------------------------------------------------------------------
# Evidence-based identification
# --------------------------------------------------------------------------

#: scheme string in the style of each catalogued line -> expected profile
SCHEMES = [
    ("SE_P441?A1???038?JE", "schneider-micom-p441"),
    ("7SA511_V3.2_1A", "siemens-7sa511"),
    ("7SA6131_4AB02_3GA0", "siemens-7sa613"),
    ("7SL87_8.81", "siemens-siprotec5-7sl87"),
    ("GRL200_TNB", "toshiba-grl200"),
    ("GRZ100_201A_Ver2.1", "toshiba-grz100"),
    ("RCS-941_MY_1A", "nr-rcs941"),
    ("RED670_V1.2_21_F11L", "hitachi-red670"),
    ("REL511_V1.2_TNB", "hitachi-rel511"),
    ("REL670_V1.2_21", "hitachi-rel670"),
    ("LFZP111_1A", "lfzp111"),
    ("RELZ100_3.0_OPS_A1", "relz100"),
]


class TestEvidenceBasedIdentification:
    @pytest.mark.parametrize("scheme, profile_id", SCHEMES)
    def test_scheme_model_token_identifies_each_catalogued_line(self, registry, scheme, profile_id):
        r = registry.identify(_doc(*_header(scheme), *GENERIC_DISTANCE_TEXT))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, profile_id)
        assert r.confidence is IdentificationConfidence.HIGH
        top = r.evidence[0]
        assert top.kind is EvidenceKind.SCHEME_MODEL and top.points == 100
        assert top.matched_text.lower() in scheme.lower()
        assert r.scheme_name == scheme

    def test_a_labelled_model_field_identifies_without_any_scheme(self, registry):
        r = registry.identify(_doc(("DEVICE INFORMATION", None), ("Type", "7SL87"), ("Serial Number", "At site")))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "siemens-siprotec5-7sl87")
        assert r.evidence[0].kind is EvidenceKind.LABELLED_MODEL

    def test_inline_labelled_model_field(self, registry):
        r = registry.identify(_doc("Relay Type: GRZ100", *GENERIC_DISTANCE_TEXT))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "toshiba-grz100")

    def test_product_code_field_carries_the_model(self, registry):
        r = registry.identify(_doc(("Product Code", "7SL87-JAAA-AA0-008810-AE2111")))
        assert r.profile_id == "siemens-siprotec5-7sl87"
        assert r.evidence[0].kind is EvidenceKind.LABELLED_MODEL

    def test_hints_are_searched_too(self, registry):
        r = registry.identify(_doc("Description    line 1", hints=("Scheme: RELZ100_3.0",)))
        assert r.profile_id == "relz100"

    def test_every_evidence_item_explains_itself(self, registry):
        r = registry.identify(_doc(*_header("GRL200_TNB"), *[(f"OP Mode ID{i}", "X") for i in range(1, 6)]))
        kinds = {e.kind for e in r.evidence}
        assert {EvidenceKind.SCHEME_MODEL, EvidenceKind.PARAMETER_SIGNATURE} <= kinds
        for e in r.evidence:
            assert e.points > 0 and e.matched_text and e.detail

    def test_indirect_evidence_combines_to_a_medium_confidence_identification(self, registry):
        doc = _doc(
            ("3007 Zone Status", "01010 P441 Zone Status"),
            ("310A SOTF/TOR Mode", "0000 P441 SOTF/TOR Mode"),
            ("320B Blocking Zones", "10111 P441 Blocking Zones"),
            ("DDB 991-960", "1111"),
            ("DDB 1022-992", "1111"),
            "MiCOM relay settings",
        )
        r = registry.identify(doc)
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "schneider-micom-p441")
        assert r.confidence is IdentificationConfidence.MEDIUM
        assert not any(e.kind in (EvidenceKind.SCHEME_MODEL, EvidenceKind.LABELLED_MODEL) for e in r.evidence)
        assert any("indirect evidence" in w for w in r.warnings)

    def test_model_token_inside_scheme_is_not_double_counted_as_a_mention(self, registry):
        r = registry.identify(_doc(*_header("RELZ100_3.0")))
        assert [e.kind for e in r.evidence] == [EvidenceKind.SCHEME_MODEL]

    def test_repetition_is_capped(self, registry):
        r = registry.identify(_doc(*[f"GRL200_Event Level {i}" for i in range(50)]))
        mentions = [e for e in r.candidates[0].evidence if e.kind is EvidenceKind.MODEL_MENTION]
        assert sum(e.points for e in mentions) == DEFAULT_RULES.model_mention_cap
        assert r.status is I.UNKNOWN  # 50 repetitions of a name are still only weak evidence


# --------------------------------------------------------------------------
# Distinguishing close relatives
# --------------------------------------------------------------------------


class TestSimilarModelsAreDistinguished:
    def test_7sa511_vs_7sa613(self, registry):
        assert registry.identify(_doc(*_header("7SA511_V3.2_1A"))).profile_id == "siemens-7sa511"
        assert registry.identify(_doc(*_header("7SA6131_4AB02_3GA0"))).profile_id == "siemens-7sa613"

    def test_grl200_vs_grz100(self, registry):
        assert registry.identify(_doc(*_header("GRL200_TNB"))).profile_id == "toshiba-grl200"
        assert registry.identify(_doc(*_header("GRZ100_201A_Ver2.1"))).profile_id == "toshiba-grz100"

    def test_red670_rel511_rel670(self, registry):
        ids = {
            s: registry.identify(_doc(*_header(s))).profile_id
            for s in ("RED670_V1.2_21_F11L", "REL511_V1.2_TNB", "REL670_V1.2_21")
        }
        assert list(ids.values()) == ["hitachi-red670", "hitachi-rel511", "hitachi-rel670"]

    def test_incidental_sibling_mentions_do_not_override_the_scheme(self, registry):
        """A RED670 sheet quotes REL670 in range cells; the scheme still decides."""
        rows = [(f"TOC{i}-:Characterist{i}", "IEC Norm. inv. REL670") for i in range(1, 7)]
        r = registry.identify(_doc(*_header("RED670_V1.2_21_F11L"), *rows))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "hitachi-red670")
        assert [c.profile_id for c in r.alternatives] == [] or r.alternatives[0].score < r.score - 30
        assert r.candidates[1].profile_id == "hitachi-rel670" and r.candidates[1].score < r.score - 30

    def test_other_family_members_in_a_sibling_sheet_do_not_override(self, registry):
        """A SIPROTEC 5 sheet names 7SA86 parameters; the 7SL87 scheme decides."""
        rows = [("CT connection", "3-phase + IN 7SA86 CT connection")] * 3
        r = registry.identify(_doc(*_header("7SL87_8.81"), ("Type", "7SL87"), *rows))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "siemens-siprotec5-7sl87")

    def test_model_token_must_be_a_whole_run(self, registry):
        for text in ("XP441Z", "P4410", "AP441", "7SA5110", "GRZ1000"):
            r = registry.identify(_doc(*_header(text)))
            assert r.status is I.UNKNOWN and not r.candidates, text

    def test_model_token_is_case_insensitive_and_tolerates_separators(self, registry):
        assert registry.identify(_doc(*_header("rcs941_my"))).profile_id == "nr-rcs941"
        assert registry.identify(_doc(*_header("grl-200_tnb"))).profile_id == "toshiba-grl200"


# --------------------------------------------------------------------------
# Unknown, weak, generic
# --------------------------------------------------------------------------


class TestUnknownIsAValidOutcome:
    def test_generic_distance_text_alone_is_unknown(self, registry):
        r = registry.identify(_doc(*GENERIC_DISTANCE_TEXT))
        assert r.status is I.UNKNOWN and r.confidence is IdentificationConfidence.NONE
        assert r.profile_id is None and r.manufacturer is None and not r.candidates

    def test_generic_vocabulary_never_scores(self, registry):
        words = ["Distance Protection", "Zone 1", "Zone 2", "R1", "X1", "K0", "CT", "VT", "Reach", "Z1 Forward"]
        r = registry.identify(_doc(*(w for w in words)))
        assert not r.candidates

    def test_one_weak_keyword_is_not_enough(self, registry):
        r = registry.identify(_doc("Comment    previously a P441 installation", *GENERIC_DISTANCE_TEXT))
        assert r.status is I.UNKNOWN and r.profile_id is None
        assert r.candidates[0].profile_id == "schneider-micom-p441" and r.candidates[0].score == 10
        assert any("weak evidence" in w for w in r.warnings)

    def test_manufacturer_name_alone_is_not_enough(self, registry):
        r = registry.identify(_doc("Prepared for ABB review", *GENERIC_DISTANCE_TEXT))
        assert r.status is I.UNKNOWN and r.manufacturer is None

    def test_relay_outside_the_catalogue_is_unknown(self, registry):
        r = registry.identify(_doc(*_header("XYZ9000_V1"), *GENERIC_DISTANCE_TEXT))
        assert r.status is I.UNKNOWN
        assert r.scheme_name == "XYZ9000_V1"  # still reported as document metadata

    def test_family_sibling_outside_the_catalogue_is_not_claimed(self, registry):
        r = registry.identify(_doc(*_header("P442_X"), *GENERIC_DISTANCE_TEXT))
        assert r.status is I.UNKNOWN

    def test_empty_document_is_unknown_with_a_reason(self, registry):
        r = registry.identify(RawRelayDocument(SourceFormat.PDF))
        assert r.status is I.UNKNOWN and r.confidence is IdentificationConfidence.NONE
        assert r.warnings

    def test_unknown_leaves_the_raw_document_intact_and_usable(self, registry):
        doc = _doc(*_header("XYZ9000_V1"), *GENERIC_DISTANCE_TEXT)
        before = (doc, doc.settings, doc.identification_hints)
        assert registry.identify(doc).status is I.UNKNOWN
        assert (doc, doc.settings, doc.identification_hints) == before
        model = registry.interpret(doc)  # later handling still works
        assert len(model.unmapped_settings) == len(doc.settings)
        assert "relay not recognised" in model.interpretation_notes[0]


# --------------------------------------------------------------------------
# Ambiguity
# --------------------------------------------------------------------------


class TestAmbiguity:
    def test_two_explicit_models_in_the_document_are_ambiguous(self, registry):
        r = registry.identify(_doc(*_header("7SA511_V3.2_1A", "Relay Type: 7SA6131")))
        assert r.status is I.AMBIGUOUS and r.confidence is IdentificationConfidence.LOW
        assert r.profile_id is None and r.model is None
        assert {c.profile_id for c in r.alternatives} == {"siemens-7sa511", "siemens-7sa613"}
        assert r.manufacturer == "Siemens"  # every tied candidate agrees
        assert r.relay_family is None  # they do not
        assert any("No relay was selected" in w for w in r.warnings)

    def test_ambiguity_across_manufacturers_names_none(self, registry):
        r = registry.identify(_doc(*_header("GRL200_TNB", "Model: P441")))
        assert r.status is I.AMBIGUOUS and r.manufacturer is None

    def test_candidate_list_and_evidence_are_preserved(self, registry):
        r = registry.identify(_doc(*_header("RED670_V1", "Type: REL670")))
        assert r.status is I.AMBIGUOUS
        assert [c.profile_id for c in r.candidates][:2] == ["hitachi-red670", "hitachi-rel670"]
        assert all(c.evidence for c in r.candidates)

    def test_a_rival_inside_the_margin_blocks_identification(self):
        a = RelayIdentificationDescriptor("a", "A", model="AAA1", model_patterns=("AAA1",))
        b = RelayIdentificationDescriptor("b", "B", model="BBB1", model_patterns=("BBB1",))
        ident = RelayIdentifier((a, b))
        close = ident.identify(_doc("Scheme: AAA1", "Type: BBB1"))  # 100 vs 90
        assert close.status is I.AMBIGUOUS
        far = ident.identify(_doc("Scheme: AAA1", "Type: AAA1", "Type: BBB1"))  # 190 vs 90
        assert far.status is I.IDENTIFIED and far.profile_id == "a"
        assert far.alternatives[0].profile_id == "b"
        assert any("also references" in w for w in far.warnings)

    def test_margin_is_exactly_the_documented_one(self):
        a = RelayIdentificationDescriptor("a", "A", model_patterns=("AAA1",))
        b = RelayIdentificationDescriptor("b", "B", model_patterns=("BBB1",))
        rules = replace(DEFAULT_RULES, labelled_model=70)
        ident = RelayIdentifier((a, b), rules=rules)
        assert ident.identify(_doc("Scheme: AAA1", "Type: BBB1")).status is I.IDENTIFIED  # 100 - 70 == 30
        assert ident.identify(_doc("Scheme: AAA1", "Type: BBB1")).profile_id == "a"
        rules = replace(DEFAULT_RULES, labelled_model=71)
        assert RelayIdentifier((a, b), rules=rules).identify(_doc("Scheme: AAA1", "Type: BBB1")).status is I.AMBIGUOUS

    def test_indirect_evidence_needs_a_wider_lead_than_an_explicit_field(self):
        shared = (ParameterSignature("foo", r"^Foo\d$", min_matches=2), ParameterSignature("bar", r"^Bar\d$", min_matches=2))
        a = RelayIdentificationDescriptor("a", "A", model_patterns=("AAA1",), parameter_signatures=shared)
        b = RelayIdentificationDescriptor("b", "B", model_patterns=("BBB1",), parameter_signatures=shared)
        ident = RelayIdentifier((a, b))
        rows = ["Foo1", "Foo2", "Bar1", "Bar2"]
        # a: three mentions (30) + two shared signatures (40) = 70; b: 40 -> lead 30
        indirect = ident.identify(_doc(*rows, "x AAA1", "y AAA1", "z AAA1"))
        assert indirect.status is I.AMBIGUOUS  # a lead of 30 is not enough without an explicit field
        # the same lead behind an explicit scheme field is enough: a: 100 + 40 = 140; b: 40
        explicit = ident.identify(_doc(*rows, "Scheme: AAA1"))
        assert (explicit.status, explicit.profile_id) == (I.IDENTIFIED, "a")

    def test_threshold_is_exactly_the_documented_one(self):
        a = RelayIdentificationDescriptor("a", "A", model_patterns=("AAA1",))
        low = RelayIdentifier((a,), rules=replace(DEFAULT_RULES, scheme_model=59))
        assert low.identify(_doc("Scheme: AAA1")).status is I.UNKNOWN
        ok = RelayIdentifier((a,), rules=replace(DEFAULT_RULES, scheme_model=60))
        assert ok.identify(_doc("Scheme: AAA1")).status is I.IDENTIFIED


# --------------------------------------------------------------------------
# Manufacturer normalisation
# --------------------------------------------------------------------------


class TestManufacturerAliases:
    @pytest.mark.parametrize(
        "name, canonical",
        [
            ("Areva T&D", "Schneider Electric"),
            ("ALSTOM Grid", "Schneider Electric"),
            ("schneider", "Schneider Electric"),
            ("ABB", "Hitachi Energy"),
            ("ABB Power Grids", "Hitachi Energy"),
            ("Hitachi ABB Power Grids", "Hitachi Energy"),
            ("Hitachi Energy", "Hitachi Energy"),
            ("Siemens AG", "Siemens"),
            ("Toshiba Energy Systems & Solutions", "Toshiba"),
            ("NARI", "NR Electric"),
        ],
    )
    def test_known_brand_transitions_normalise(self, name, canonical):
        assert MANUFACTURER_ALIASES.normalize(name) == canonical

    def test_unknown_name_is_not_normalised(self):
        assert MANUFACTURER_ALIASES.normalize("Acme Relays") is None
        assert MANUFACTURER_ALIASES.normalize("") is None

    def test_source_spelling_is_preserved_next_to_the_normalised_name(self, registry):
        r = registry.identify(_doc(*_header("P441_X", "Manufacturer: AREVA T&D")))
        assert r.status is I.IDENTIFIED
        assert r.manufacturer == "Schneider Electric"
        assert r.manufacturer_source_name == "AREVA T&D"
        assert any(e.kind is EvidenceKind.MANUFACTURER_NAME for e in r.evidence)

    def test_older_brand_resolves_to_the_current_identity(self, registry):
        r = registry.identify(_doc(*_header("REL511_V1.2_TNB", "Manufacturer: ABB")))
        assert (r.manufacturer, r.manufacturer_source_name) == ("Hitachi Energy", "ABB")

    def test_a_longer_word_containing_an_alias_is_not_the_alias(self, registry):
        # "ABBA" is a station code; it must not look like the manufacturer ABB
        r = registry.identify(_doc(*_header("RED670_V1", "Plant Reference    ABBA_SRDN132_1")))
        assert r.status is I.IDENTIFIED and r.manufacturer == "Hitachi Energy"
        assert r.manufacturer_source_name is None
        assert not any(e.kind is EvidenceKind.MANUFACTURER_NAME for e in r.evidence)

    def test_manufacturer_without_a_recorded_identity_is_not_guessed(self, registry):
        r = registry.identify(_doc(*_header("LFZP111_1A")))
        assert r.status is I.IDENTIFIED and r.manufacturer is None and r.model == "LFZP111"

    def test_identified_manufacturer_comes_from_the_descriptor_not_the_text(self, registry):
        r = registry.identify(_doc(*_header("7SA511_V3.2_1A", "Manufacturer: Toshiba")))
        assert r.profile_id == "siemens-7sa511" and r.manufacturer == "Siemens"


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------


class TestVersion:
    def test_explicit_version_marker_in_scheme(self, registry):
        r = registry.identify(_doc(*_header("7SA511_V3.2_1A")))
        assert (r.version, r.version_source) == ("3.2", "scheme name")
        assert registry.identify(_doc(*_header("GRZ100_201A_Ver2.1"))).version == "2.1"

    def test_labelled_firmware_field_wins(self, registry):
        r = registry.identify(_doc(*_header("GRZ100_201A_Ver2.1"), ("Main software", "GS1ZM1-29-G")))
        assert (r.version, r.version_source) == ("GS1ZM1-29-G", "labelled field 'Main software'")

    def test_version_is_never_guessed(self, registry):
        assert registry.identify(_doc(*_header("7SL87_8.81"))).version is None
        assert registry.identify(_doc(*_header("SE_P441?A1???038?JE"))).version is None

    def test_unidentified_documents_carry_no_version(self, registry):
        assert registry.identify(_doc(*_header("XYZ_V9"))).version is None


# --------------------------------------------------------------------------
# Determinism and robustness
# --------------------------------------------------------------------------


class TestDeterminismAndRobustness:
    def test_repeat_identification_is_identical(self, registry):
        doc = _doc(*_header("RED670_V1.2"), ("Type", "REL670"), ("HW Configuration/BIM3", None), ("HW Configuration/BOM4", None))
        assert registry.identify(doc) == registry.identify(doc)

    def test_fresh_registries_agree(self):
        doc = _doc(*_header("GRZ100_201A_Ver2.1"), *GENERIC_DISTANCE_TEXT)
        assert build_registry().identify(doc) == build_registry().identify(doc)

    def test_descriptor_registration_order_does_not_matter(self):
        doc = _doc(*_header("RED670_V1"), ("Type", "REL670"))
        forward = RelayProfileRegistry(
            identification_descriptors=IDENTIFICATION_DESCRIPTORS, manufacturer_aliases=MANUFACTURER_ALIASES
        ).identify(doc)
        backward = RelayProfileRegistry(
            identification_descriptors=tuple(reversed(IDENTIFICATION_DESCRIPTORS)), manufacturer_aliases=MANUFACTURER_ALIASES
        ).identify(doc)
        assert forward == backward

    def test_entry_order_and_unrelated_entries_do_not_change_the_verdict(self, registry):
        base = [*_header("7SA6131_4AB02_3GA0"), *GENERIC_DISTANCE_TEXT]
        a = registry.identify(_doc(*base))
        b = registry.identify(_doc(*reversed(base)))
        c = registry.identify(_doc(*base, *[(f"Filler {i}", str(i)) for i in range(500)]))
        assert (a.status, a.profile_id) == (b.status, b.profile_id) == (c.status, c.profile_id)
        assert a.score == b.score == c.score

    def test_file_name_is_not_an_input(self, registry):
        """Identification sees a RawRelayDocument only; there is nowhere for a
        file name to enter."""
        import inspect

        assert list(inspect.signature(registry.identify).parameters) == ["document"]
        assert "filename" not in {f.name for f in RawRelayDocument.__dataclass_fields__.values()}

    def test_identification_does_not_depend_on_pdf_parsing(self):
        text = (APP / "domain" / "relay_import" / "identification.py").read_text(encoding="utf-8")
        for forbidden in ("pypdf", "relay_pdf_extractor", "PdfReader", "SourceFormat.PDF"):
            assert forbidden not in text

    def test_non_pdf_source_formats_use_the_same_layer(self, registry):
        doc = RawRelayDocument(
            SourceFormat.CSV, (RawSetting("r1", name="Scheme", raw_value="GRZ100_201A"),)
        )
        assert registry.identify(doc).profile_id == "toshiba-grz100"


# --------------------------------------------------------------------------
# Signatures
# --------------------------------------------------------------------------


class TestParameterSignatures:
    def test_signature_needs_min_matches(self):
        d = RelayIdentificationDescriptor(
            "x", "X", model_patterns=(), parameter_signatures=(ParameterSignature("s", r"^Foo\d+$", min_matches=3),)
        )
        ident = RelayIdentifier((d,), rules=replace(DEFAULT_RULES, identify_threshold=10))
        assert ident.identify(_doc("Foo1", "Foo2")).status is I.UNKNOWN
        assert ident.identify(_doc("Foo1", "Foo2", "Foo3")).status is I.IDENTIFIED

    def test_signature_targets_name_parameter_id_or_text(self):
        for target, doc in (
            ("name", RawRelayDocument(SourceFormat.PDF, (RawSetting("a", name="Foo1"),))),
            ("parameter_id", RawRelayDocument(SourceFormat.PDF, (RawSetting("a", parameter_id="Foo1"),))),
            ("text", RawRelayDocument(SourceFormat.PDF, (RawSetting("a", source_text="x Foo1 y"),))),
        ):
            pattern = r"Foo1" if target == "text" else r"^Foo1$"
            d = RelayIdentificationDescriptor("x", "X", parameter_signatures=(ParameterSignature("s", pattern, target=target),))
            r = RelayIdentifier((d,), rules=replace(DEFAULT_RULES, identify_threshold=10)).identify(doc)
            assert r.status is I.IDENTIFIED, target

    def test_invalid_signature_or_descriptor_is_rejected_early(self):
        with pytest.raises(ValueError):
            ParameterSignature("s", "x", target="nope")
        with pytest.raises(ValueError):
            ParameterSignature("s", "x", min_matches=0)
        with pytest.raises(Exception):
            ParameterSignature("s", "(")
        with pytest.raises(ValueError):
            RelayIdentificationDescriptor("", "X")

    def test_duplicate_descriptor_ids_are_rejected(self):
        d = RelayIdentificationDescriptor("x", "X")
        with pytest.raises(ValueError):
            RelayIdentifier((d, d))


# --------------------------------------------------------------------------
# Registry and catalogue integration
# --------------------------------------------------------------------------


class _ExplodingProfile:
    profile_id = "exploding"
    version = "1"
    identification = RelayIdentificationDescriptor("exploding", "Boom", model="ZZZ1", model_patterns=("ZZZ1",))

    def match(self, document):
        raise AssertionError("identification must not call profile.match")

    def interpret(self, document):
        raise AssertionError("identification must not call profile.interpret")


class TestRegistryIntegration:
    def test_identify_never_calls_profile_logic(self):
        reg = RelayProfileRegistry((_ExplodingProfile(),))
        r = reg.identify(_doc("Scheme: ZZZ1_V1"))
        assert (r.status, r.profile_id) == (I.IDENTIFIED, "exploding")

    def test_profile_and_standalone_descriptors_are_both_exposed(self):
        extra = RelayIdentificationDescriptor("extra", "E")
        reg = RelayProfileRegistry((_ExplodingProfile(),), identification_descriptors=(extra,))
        assert [d.profile_id for d in reg.identification_descriptors()] == ["extra", "exploding"]

    def test_duplicate_descriptor_registration_is_rejected(self):
        reg = RelayProfileRegistry(identification_descriptors=(RelayIdentificationDescriptor("x", "X"),))
        with pytest.raises(ValueError):
            reg.register_identification_descriptor(RelayIdentificationDescriptor("x", "Y"))

    def test_registering_after_use_takes_effect(self):
        reg = RelayProfileRegistry()
        assert reg.identify(_doc("Scheme: QQQ1")).status is I.UNKNOWN
        reg.register_identification_descriptor(RelayIdentificationDescriptor("q", "Q", model_patterns=("QQQ1",)))
        assert reg.identify(_doc("Scheme: QQQ1")).profile_id == "q"

    def test_interpretation_behaviour_is_unchanged(self):
        """Identification metadata does not turn a recognised relay into a
        supported one: without an interpretation profile (or active catalog) for
        it, interpretation still falls back to the generic profile."""
        registry = RelayProfileRegistry(identification_descriptors=catalogue.IDENTIFICATION_DESCRIPTORS)
        doc = _doc(*_header("7SA6131_4AB02_3GA0"), ("1313 X(Z2)", "3.6"))
        assert registry.identify(doc).status is I.IDENTIFIED
        model = registry.interpret(doc)
        assert model.zones == () and len(model.unmapped_settings) == len(doc.settings)

    def test_default_registry_is_shared_and_identifies(self):
        assert catalogue.default_registry() is catalogue.default_registry()
        assert catalogue.default_registry().identify(_doc("Scheme: RELZ100")).profile_id == "relz100"


class TestCatalogue:
    EXPECTED = {
        "schneider-micom-p441", "siemens-7sa511", "siemens-7sa613", "siemens-siprotec5-7sl87",
        "toshiba-grl200", "toshiba-grz100", "nr-rcs941", "hitachi-red670", "hitachi-rel511",
        "hitachi-rel670", "lfzp111", "relz100",
    }

    def test_catalogue_covers_exactly_the_known_sample_families(self):
        assert {d.profile_id for d in IDENTIFICATION_DESCRIPTORS} == self.EXPECTED
        assert len(IDENTIFICATION_DESCRIPTORS) == len(self.EXPECTED)

    def test_every_entry_can_be_identified_by_its_own_model(self):
        for d in IDENTIFICATION_DESCRIPTORS:
            assert d.model and d.model_patterns and d.relay_family

    def test_catalogue_entries_are_identification_only(self):
        fields = set(RelayIdentificationDescriptor.__dataclass_fields__)
        assert fields == {
            "profile_id", "relay_family", "manufacturer", "model", "model_patterns", "family_markers", "parameter_signatures",
        }

    def test_manufacturers_are_normalised_names_known_to_the_alias_table(self):
        canonical = {name for name, _ in MANUFACTURER_ALIASES.table}
        for d in IDENTIFICATION_DESCRIPTORS:
            assert d.manufacturer is None or d.manufacturer in canonical

    def test_relay_knowledge_lives_in_the_catalogue_not_the_identifier(self):
        source = (APP / "domain" / "relay_import" / "identification.py").read_text(encoding="utf-8")
        for d in IDENTIFICATION_DESCRIPTORS:
            assert d.model is None or d.model.lower() not in source.lower(), d.model
        assert not re.search(r"if\s+[\"'][A-Za-z0-9-]+[\"']\s+in\s+text", source)

    def test_catalogue_stays_out_of_the_engine_and_persistence(self):
        text = (APP / "relay_profiles" / "identification_catalogue.py").read_text(encoding="utf-8")
        for forbidden in ("app.storage", "sqlalchemy", "app.services", "fastapi", "distance_protection"):
            assert forbidden not in text


# --------------------------------------------------------------------------
# Real sample corpus (owner files are not committed)
# --------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get("RELAY_SAMPLE_PDF_DIR")
REAL_SAMPLES = {
    "p441": ("schneider-micom-p441", "P441"),
    "7sa511": ("siemens-7sa511", "7SA511"),
    "7sa613": ("siemens-7sa613", "7SA613"),
    "7sl87": ("siemens-siprotec5-7sl87", "7SL87"),
    "grl200": ("toshiba-grl200", "GRL200"),
    "grz100": ("toshiba-grz100", "GRZ100"),
    "rcs": ("nr-rcs941", "RCS-941"),
    "red670": ("hitachi-red670", "RED670"),
    "rel511": ("hitachi-rel511", "REL511"),
    "rel670": ("hitachi-rel670", "REL670"),
    "lfzp": ("lfzp111", "LFZP111"),
    "relz100": ("relz100", "RELZ100"),
}


def _real_document(name: str) -> RawRelayDocument:
    from app.services.relay_pdf_extractor import extract_pdf

    path = Path(SAMPLE_DIR) / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"{path.name} not available")
    return extract_pdf(path.read_bytes()).document


needs_samples = pytest.mark.skipif(
    not SAMPLE_DIR, reason="owner sample PDFs are not committed; set RELAY_SAMPLE_PDF_DIR to run"
)


@needs_samples
class TestRealSamples:
    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_each_sample_is_identified_with_meaningful_evidence(self, registry, name):
        profile_id, model = REAL_SAMPLES[name]
        r = registry.identify(_real_document(name))
        assert (r.status, r.profile_id, r.model) == (I.IDENTIFIED, profile_id, model.replace("-", "-"))
        assert r.confidence is IdentificationConfidence.HIGH
        explicit = [e for e in r.evidence if e.kind in (EvidenceKind.SCHEME_MODEL, EvidenceKind.LABELLED_MODEL)]
        assert explicit, "identified without an explicit model field"
        assert re.sub(r"[-_]", "", model).lower() in re.sub(r"[-_]", "", explicit[0].matched_text).lower()
        assert explicit[0].setting_id and explicit[0].page == 1
        assert r.scheme_name

    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_no_rival_reaches_the_ambiguity_margin(self, registry, name):
        r = registry.identify(_real_document(name))
        for rival in r.candidates[1:]:
            assert r.score - rival.score >= DEFAULT_RULES.ambiguity_margin

    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_removing_the_scheme_line_never_misidentifies(self, registry, name):
        doc = _real_document(name)
        kept = tuple(s for s in doc.settings if "scheme" not in (s.source_text or "").lower())
        r = registry.identify(replace(doc, settings=kept))
        assert r.profile_id in (None, REAL_SAMPLES[name][0])

    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_dropping_entries_and_reordering_keeps_the_verdict(self, registry, name):
        doc = _real_document(name)
        thinned = replace(doc, settings=tuple(s for i, s in enumerate(doc.settings) if i % 3 or "scheme" in (s.source_text or "").lower()))
        assert registry.identify(thinned).profile_id == REAL_SAMPLES[name][0]
        assert registry.identify(replace(doc, settings=tuple(reversed(doc.settings)))).profile_id == REAL_SAMPLES[name][0]

    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_repeat_identification_is_identical(self, registry, name):
        doc = _real_document(name)
        assert registry.identify(doc) == registry.identify(doc)

    def test_the_7sl87_sheet_is_identified_from_its_device_information_too(self, registry):
        doc = _real_document("7sl87")
        kept = tuple(s for s in doc.settings if "scheme" not in (s.source_text or "").lower())
        r = registry.identify(replace(doc, settings=kept))
        assert r.profile_id == "siemens-siprotec5-7sl87"
        assert r.evidence[0].kind is EvidenceKind.LABELLED_MODEL

    def test_the_red670_sheet_that_quotes_rel670_is_not_ambiguous(self, registry):
        r = registry.identify(_real_document("red670"))
        assert r.profile_id == "hitachi-red670"
        assert "hitachi-rel670" in {c.profile_id for c in r.candidates}

    def test_a_station_code_that_starts_with_abb_is_not_a_manufacturer(self, registry):
        r = registry.identify(_real_document("p441"))  # station "ABBA"
        assert not any(e.kind is EvidenceKind.MANUFACTURER_NAME for e in r.evidence)
        assert r.manufacturer == "Schneider Electric" and r.manufacturer_source_name is None


@needs_samples
class TestRealSamplesThroughTheUploadEndpoint:
    @pytest.mark.parametrize("name", REAL_SAMPLES)
    def test_endpoint_reports_the_identity_whatever_the_file_is_called(self, settings, name):
        import io

        from fastapi.testclient import TestClient

        from app.main import create_app

        path = Path(SAMPLE_DIR) / f"{name}.pdf"
        if not path.exists():
            pytest.skip(f"{path.name} not available")
        profile_id, model = REAL_SAMPLES[name]
        with TestClient(create_app(settings)) as client:
            # a misleading name must not matter: use another relay's name
            misleading = "p441.pdf" if name != "p441" else "7sa613.pdf"
            for upload_name in ("document.pdf", misleading):
                r = client.post(
                    "/api/v1/relay-import/upload",
                    files={"file": (upload_name, io.BytesIO(path.read_bytes()), "application/pdf")},
                )
                body = r.json()
                assert r.status_code == 200
                assert (body["identification_status"], body["profile_id"], body["confidence"]) == ("identified", profile_id, "high")
                assert body["model"].replace("-", "") == model.replace("-", "")
