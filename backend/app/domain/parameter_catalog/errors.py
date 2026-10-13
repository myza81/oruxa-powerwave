"""Validation issues for the parameter catalog.

A catalog is data that decides what a relay's settings *mean*, so a malformed one must be
refused before it is used -- loudly and completely (every problem listed, none silently
dropped). `CatalogIssue` is one problem; `CatalogValidationError` carries all of them.
"""

from __future__ import annotations

from dataclasses import dataclass


class IssueCode:
    """Stable codes for the checks the validators run (asserted by tests, quoted in docs)."""

    MALFORMED = "malformed"                      # not the right JSON shape / type
    MISSING_METADATA = "missing_metadata"        # a required field is absent or empty
    UNKNOWN_FIELD = "unknown_field"              # a key the schema does not define
    UNKNOWN_CANONICAL = "unknown_canonical"      # a mapping targets an id the registry does not define
    INVALID_UNIT = "invalid_unit"                # a unit the vocabulary does not know / no conversion exists
    DUPLICATE = "duplicate"                      # the same id / mapping defined twice
    CONFLICT = "conflict"                        # two mappings claim the same target at the same precedence
    UNSUPPORTED_TRANSFORM = "unsupported_transform"  # a transformation primitive that does not exist
    INVALID_TRANSFORM = "invalid_transform"      # a known primitive with bad parameters / types
    INVALID_ENUM = "invalid_enum"                # an enum map pointing outside the canonical enum
    INVALID_ZONE = "invalid_zone"                # a zone target the catalog's zone model does not define
    INVALID_SELECTOR = "invalid_selector"        # a source selector that cannot match anything
    INVALID_VALUE_SOURCE = "invalid_value_source"  # e.g. a printed range read as the configured value
    INVALID_LIFECYCLE = "invalid_lifecycle"
    INVALID_VERSION = "invalid_version"
    INVALID_REFERENCE = "invalid_reference"      # a dependency on a canonical value that is not available first


@dataclass(frozen=True)
class CatalogIssue:
    #: Where the problem is, e.g. ``mappings[3].transform[0]`` (JSON-pointer-like, human readable).
    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


class CatalogValidationError(ValueError):
    """A catalog (or the canonical registry) failed validation; ``issues`` lists every problem."""

    def __init__(self, source: str, issues: list[CatalogIssue]) -> None:
        self.source = source
        self.issues = tuple(issues)
        lines = "\n".join(f"  - {issue}" for issue in self.issues)
        super().__init__(f"{source}: {len(self.issues)} validation issue(s)\n{lines}")

    def codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)
