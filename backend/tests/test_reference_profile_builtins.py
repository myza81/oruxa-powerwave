"""Tests for `app.domain.reference_profile_builtins.load_builtin_profiles()`
(Compliance Slice 3, task section 9's own governing constraint: no
production Malaysia Grid Code / OEM built-in may be fabricated).

Exercises the loader against clearly-labeled, test-only fixture
directories under `backend/tests/fixtures/reference_profiles/` -- NEVER
against the real production directory, whose own emptiness is asserted
directly here as the one thing this module guarantees about production
behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.reference_profile_builtins import (
    BuiltinReferenceProfileLoadError,
    DEFAULT_BUILTIN_DIRECTORY,
    load_builtin_profiles,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "reference_profiles"


class TestProductionCatalogueIsEmpty:
    """Task section 9: "do not create a production 'Malaysia Grid Code'
    built-in yet [...] Instead create either no built-in production
    profile, or a clearly developer/test-only fixture that cannot be
    mistaken for an official requirement." This repository chose the
    former -- these tests are the guardrail that keeps it that way."""

    def test_default_directory_loads_to_an_empty_list(self):
        assert load_builtin_profiles() == []

    def test_default_directory_points_at_the_real_production_path(self):
        assert DEFAULT_BUILTIN_DIRECTORY.name == "builtin"
        assert DEFAULT_BUILTIN_DIRECTORY.parent.name == "reference_profiles"

    def test_a_nonexistent_directory_is_not_an_error(self, tmp_path):
        assert load_builtin_profiles(tmp_path / "does-not-exist") == []


class TestLoaderAgainstTestOnlyFixtures:
    def test_valid_fixture_loads_and_is_flagged_built_in(self):
        profiles = load_builtin_profiles(FIXTURES_DIR / "valid")
        assert len(profiles) == 1
        profile = profiles[0]
        assert profile.id == "dev_fixture_flat_envelope_test_only"
        assert profile.metadata.built_in is True
        assert "NOT an Official Requirement" in profile.name

    def test_profile_id_is_the_filename_stem_never_trusted_from_file_content(self):
        profiles = load_builtin_profiles(FIXTURES_DIR / "valid")
        assert profiles[0].id == "dev_fixture_flat_envelope_test_only"

    def test_missing_built_in_flag_is_rejected(self):
        with pytest.raises(BuiltinReferenceProfileLoadError, match="built_in"):
            load_builtin_profiles(FIXTURES_DIR / "missing_built_in_flag")

    def test_domain_invalid_file_is_rejected_loudly_not_skipped(self):
        with pytest.raises(BuiltinReferenceProfileLoadError):
            load_builtin_profiles(FIXTURES_DIR / "malformed")

    def test_empty_directory_loads_to_an_empty_list(self, tmp_path):
        assert load_builtin_profiles(tmp_path) == []
