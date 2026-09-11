"""Tests for app.domain.phase_identity (Analysis Guardrail Slice 1):
canonical phase normalization, convention inference, and phase-source
provenance/overwrite authority. Pure domain logic -- no registry, no
service, no I/O.
"""

from __future__ import annotations

from app.domain.phase_identity import (
    CONVENTION_ABC,
    CONVENTION_L123,
    CONVENTION_RYB,
    KNOWN_PHASE_SOURCES,
    KNOWN_PHASES,
    PHASE_A,
    PHASE_AB,
    PHASE_B,
    PHASE_C,
    PHASE_CA,
    PHASE_N,
    PHASE_SOURCE_DETECTED_FROM_NAME,
    PHASE_SOURCE_ENGINEER_CONFIRMED,
    PHASE_SOURCE_MANUAL,
    PHASE_SOURCE_STRUCTURED_METADATA,
    PHASE_SOURCE_UNKNOWN,
    PHASE_UNKNOWN,
    infer_phase_convention,
    may_overwrite_phase_assignment,
    normalize_phase_token,
    phase_source_authority,
    phase_source_valid,
    phase_valid,
)


class TestPhaseValidity:
    def test_all_known_phases_valid(self):
        for phase in KNOWN_PHASES:
            assert phase_valid(phase)

    def test_unknown_string_invalid(self):
        assert not phase_valid("Z")
        assert not phase_valid("")

    def test_all_known_phase_sources_valid(self):
        for source in KNOWN_PHASE_SOURCES:
            assert phase_source_valid(source)

    def test_unknown_phase_source_invalid(self):
        assert not phase_source_valid("guessed")


class TestConventionInference:
    def test_abc_evidence_from_a(self):
        assert infer_phase_convention(["A"]) == CONVENTION_ABC

    def test_abc_evidence_from_c(self):
        assert infer_phase_convention(["C"]) == CONVENTION_ABC

    def test_ryb_evidence_from_r(self):
        assert infer_phase_convention(["R"]) == CONVENTION_RYB

    def test_ryb_evidence_from_y(self):
        assert infer_phase_convention(["Y"]) == CONVENTION_RYB

    def test_l123_evidence(self):
        assert infer_phase_convention(["L1"]) == CONVENTION_L123

    def test_bare_b_alone_is_ambiguous(self):
        """The critical guardrail: "B" alone proves nothing -- it means
        canonical B under A/B/C but canonical C under R/Y/B."""
        assert infer_phase_convention(["B"]) is None

    def test_b_plus_a_resolves_to_abc(self):
        assert infer_phase_convention(["A", "B"]) == CONVENTION_ABC

    def test_b_plus_r_resolves_to_ryb(self):
        assert infer_phase_convention(["R", "B"]) == CONVENTION_RYB

    def test_conflicting_evidence_is_ambiguous(self):
        """Both "R" (RYB-exclusive) and "A" (ABC-exclusive) present at
        once is a genuine conflict -- never guessed."""
        assert infer_phase_convention(["R", "A"]) is None

    def test_no_evidence_at_all(self):
        assert infer_phase_convention([]) is None

    def test_neutral_bare_n_contributes_no_evidence(self):
        assert infer_phase_convention(["N"]) is None


class TestNormalizePhaseToken:
    def test_abc_identity(self):
        assert normalize_phase_token("A", CONVENTION_ABC) == PHASE_A
        assert normalize_phase_token("B", CONVENTION_ABC) == PHASE_B
        assert normalize_phase_token("C", CONVENTION_ABC) == PHASE_C

    def test_ryb_mapping(self):
        assert normalize_phase_token("R", CONVENTION_RYB) == PHASE_A
        assert normalize_phase_token("Y", CONVENTION_RYB) == PHASE_B
        # The explicit guardrail example: under R/Y/B, raw "B" means
        # canonical C, never canonical B.
        assert normalize_phase_token("B", CONVENTION_RYB) == PHASE_C

    def test_l123_mapping(self):
        assert normalize_phase_token("L1", CONVENTION_L123) == PHASE_A
        assert normalize_phase_token("L2", CONVENTION_L123) == PHASE_B
        assert normalize_phase_token("L3", CONVENTION_L123) == PHASE_C

    def test_bare_n_always_neutral_regardless_of_convention(self):
        assert normalize_phase_token("N", CONVENTION_ABC) == PHASE_N
        assert normalize_phase_token("N", CONVENTION_RYB) == PHASE_N
        assert normalize_phase_token("N", None) == PHASE_N

    def test_no_convention_is_unknown(self):
        assert normalize_phase_token("B", None) == PHASE_UNKNOWN
        assert normalize_phase_token("A", None) == PHASE_UNKNOWN

    def test_pair_tokens(self):
        assert normalize_phase_token("AB", CONVENTION_ABC) == PHASE_AB
        assert normalize_phase_token("RY", CONVENTION_RYB) == PHASE_AB
        assert normalize_phase_token("BR", CONVENTION_RYB) == PHASE_CA

    def test_wrong_convention_token_is_unknown(self):
        # "R" is not a recognized token under the ABC convention.
        assert normalize_phase_token("R", CONVENTION_ABC) == PHASE_UNKNOWN

    def test_blank_token_is_unknown(self):
        assert normalize_phase_token("", CONVENTION_ABC) == PHASE_UNKNOWN

    def test_case_insensitive(self):
        assert normalize_phase_token("a", CONVENTION_ABC) == PHASE_A
        assert normalize_phase_token("l1", CONVENTION_L123) == PHASE_A


class TestPhaseSourceAuthorityAndOverwrite:
    def test_authority_ordering(self):
        assert (
            phase_source_authority(PHASE_SOURCE_ENGINEER_CONFIRMED)
            == phase_source_authority(PHASE_SOURCE_MANUAL)
            > phase_source_authority(PHASE_SOURCE_STRUCTURED_METADATA)
            > phase_source_authority(PHASE_SOURCE_DETECTED_FROM_NAME)
            > phase_source_authority(PHASE_SOURCE_UNKNOWN)
        )

    def test_locked_assignment_never_overwritten_by_automatic_candidate(self):
        assert not may_overwrite_phase_assignment(
            existing_source=PHASE_SOURCE_ENGINEER_CONFIRMED, candidate_source=PHASE_SOURCE_STRUCTURED_METADATA
        )
        assert not may_overwrite_phase_assignment(
            existing_source=PHASE_SOURCE_MANUAL, candidate_source=PHASE_SOURCE_STRUCTURED_METADATA
        )

    def test_higher_authority_candidate_may_overwrite_unlocked(self):
        assert may_overwrite_phase_assignment(
            existing_source=PHASE_SOURCE_DETECTED_FROM_NAME, candidate_source=PHASE_SOURCE_STRUCTURED_METADATA
        )

    def test_lower_authority_candidate_may_not_overwrite(self):
        assert not may_overwrite_phase_assignment(
            existing_source=PHASE_SOURCE_STRUCTURED_METADATA, candidate_source=PHASE_SOURCE_DETECTED_FROM_NAME
        )

    def test_equal_authority_refresh_allowed(self):
        assert may_overwrite_phase_assignment(
            existing_source=PHASE_SOURCE_DETECTED_FROM_NAME, candidate_source=PHASE_SOURCE_DETECTED_FROM_NAME
        )
