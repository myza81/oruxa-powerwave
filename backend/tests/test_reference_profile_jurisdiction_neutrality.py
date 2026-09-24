"""Architecture-invariant tests for Compliance's own jurisdiction-
neutrality guarantee (DEC-111): *"Powerwave Compliance is jurisdiction-
neutral. Reference requirements are portable data, not engine code."*

**What this file proves, precisely**: no PRODUCTION domain/service/API
source file for Reference Profiles contains a jurisdiction/utility/OEM
name as part of actual CODE (an identifier, a branch condition, a
dict/constant key) -- as opposed to a comment or docstring EXPLAINING
this very constraint (which legitimately names examples like "Malaysia
Grid Code" to describe what must never be hardcoded -- see this
project's own `docs/project-memory/COMPLIANCE_CAPABILITY.md` and
`backend/app/data/reference_profiles/builtin/README.md`, both of which
say "Malaysia" repeatedly as documentation, never as a code branch).

**Deliberately NOT a brittle whole-repo string ban** (task section 26's
own explicit instruction): a plain substring grep across the whole
repository would immediately flag this project's own legitimate,
intentional explanatory comments/docstrings/docs (including this very
file, and DEC-109/DEC-110/DEC-111's own architecture text) as false
positives. Instead, this module tokenizes each target PRODUCTION source
file with Python's own `tokenize` module and strips every COMMENT and
STRING token before checking for banned terms in what remains --
STRING tokens cover both regular string literals AND docstrings (Python
does not distinguish the two at the tokenizer level), so this
necessarily also permits a banned term to appear inside an ordinary
runtime string VALUE. That is intentional and correct: task section 5's
own "bundled profile != hardcoded requirement" distinction means a
profile's own DATA (a name, a jurisdiction field, a JSON fixture) may
legitimately say "Malaysia Grid Code 2025" -- what must never exist is a
CODE IDENTIFIER or BRANCH keyed on a jurisdiction name (e.g. `if
jurisdiction == "Malaysia": ...`), which is exactly the class of thing
that survives this stripping and gets checked.

Also confirms the second, complementary, already-established (DEC-109)
guarantee directly: the production built-in catalogue directory itself
ships with zero files.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

from app.domain.reference_profile_builtins import DEFAULT_BUILTIN_DIRECTORY, load_builtin_profiles

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: Every production source file that touches Reference Profiles/
#: Assessment Definitions -- deliberately a named list (task section 26:
#: "target the production domain/service paths"), never a whole-repo
#: walk that would also sweep test files, fixtures, and documentation
#: where these names are legitimately used.
PRODUCTION_REFERENCE_PROFILE_FILES = (
    BACKEND_ROOT / "app" / "domain" / "reference_profile.py",
    BACKEND_ROOT / "app" / "domain" / "reference_profile_builtins.py",
    BACKEND_ROOT / "app" / "domain" / "assessment_definition.py",
    BACKEND_ROOT / "app" / "domain" / "reference_layer.py",
    BACKEND_ROOT / "app" / "services" / "reference_profile_registry.py",
    BACKEND_ROOT / "app" / "services" / "reference_layer_registry.py",
    BACKEND_ROOT / "app" / "services" / "reference_profile_service.py",
    BACKEND_ROOT / "app" / "schemas" / "reference_profile.py",
    BACKEND_ROOT / "app" / "api" / "v1" / "reference_profiles.py",
)

#: Named jurisdictions/grid codes/OEMs this test proves never appear as
#: CODE (identifiers/branches) in the files above. Deliberately a short,
#: representative list (task's own examples), not an attempt at an
#: exhaustive world-wide registry -- the tokenizer-based mechanism
#: itself is what generalizes, not this specific list.
BANNED_JURISDICTION_OR_OEM_TERMS = (
    "Malaysia",
    "GBGridCode",  # "GB Grid Code" has no code-legal spacing; check the identifier-safe form
    "ENTSOE",
    "ENTSO_E",
    "AEMO",
    "Huawei",
)


def _code_tokens_excluding_comments_and_strings(path: Path) -> str:
    """Returns the source file's own token stream with every COMMENT and
    STRING token (docstrings included -- see this module's own docstring
    for why that is the correct scope) removed, re-joined with spaces.
    This is what a `banned term not in ...` check runs against."""
    source_bytes = path.read_bytes()
    tokens = tokenize.tokenize(io.BytesIO(source_bytes).readline)
    kept: list[str] = []
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.ENCODING):
            continue
        kept.append(tok.string)
    return " ".join(kept)


class TestNoJurisdictionSpecificCodeInProductionReferenceProfilePaths:
    @pytest.mark.parametrize("path", PRODUCTION_REFERENCE_PROFILE_FILES, ids=lambda p: p.name)
    def test_file_exists(self, path: Path):
        # A guard against this test silently checking nothing if a file
        # gets renamed/moved without this list being updated.
        assert path.is_file(), f"Expected production file not found: {path}"

    @pytest.mark.parametrize("path", PRODUCTION_REFERENCE_PROFILE_FILES, ids=lambda p: p.name)
    def test_no_jurisdiction_or_oem_identifier_in_code(self, path: Path):
        code_only = _code_tokens_excluding_comments_and_strings(path)
        # Case-sensitive on purpose: an incidental lowercase substring
        # match (e.g. a variable containing "malaysia" as part of an
        # unrelated word) would be a false positive this test must not
        # produce; every real jurisdiction/OEM name in task section 26's
        # own list is properly-cased.
        for term in BANNED_JURISDICTION_OR_OEM_TERMS:
            assert term not in code_only, (
                f"{path.name} appears to reference {term!r} as part of actual code "
                "(outside comments/docstrings/string literals) -- Compliance must stay "
                "jurisdiction-neutral; see DEC-111."
            )

    def test_the_stripping_mechanism_itself_is_proven_by_this_files_own_docstring(self):
        """This file's OWN module docstring says "Malaysia" several
        times as documentation -- proving the tokenizer-based stripping
        approach does not merely get lucky on the production files (it
        genuinely ignores comments/docstrings, confirmed by ignoring its
        own)."""
        this_file = Path(__file__)
        code_only = _code_tokens_excluding_comments_and_strings(this_file)
        assert "Malaysia" not in code_only


class TestProductionBuiltInCatalogueShipsEmpty:
    """Complementary, already-established (DEC-109) guarantee: zero
    jurisdiction-specific profiles are bundled by default -- confirmed
    directly against the REAL production directory, never a copy."""

    def test_production_built_in_directory_has_no_json_files(self):
        assert not list(DEFAULT_BUILTIN_DIRECTORY.glob("*.json"))

    def test_loading_the_real_production_catalogue_yields_zero_profiles(self):
        assert load_builtin_profiles() == []
