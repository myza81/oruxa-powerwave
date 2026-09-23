"""Compliance & Capability -- built-in Reference Profile catalogue
loader (Slice 3, task section 9).

**Governing constraint (task section 9, owner instruction, verbatim in
intent): do NOT hard-code Malaysia Grid Code LVRT/HVRT values, or any
other named official requirement, from memory, prior chats, assumptions,
or generic industry curves. If this repository does not already contain
an authoritative verified source for those exact values, no production
"Malaysia Grid Code" (or any other named grid code / OEM capability)
built-in profile may be created.**

This module resolves that constraint by making built-in profiles
**data, not code**: it loads zero or more version-controlled JSON files
(the same envelope shape `app.domain.reference_profile.
profile_from_json_dict()` already parses for import) from a directory,
validates each one exactly like an import, and returns them as read-only
`ReferenceProfile` objects. **The production directory
(`app/data/reference_profiles/builtin/`) ships with zero profile files**
-- see that directory's own `README.md` for why. The loader itself is
fully exercised by this module's own tests against a *test-only* fixture
directory (`backend/tests/fixtures/reference_profiles/`), proving the
load path is correct and "ready for verified profiles later" (task
section 9's own closing requirement) without ever exposing a fabricated
or unverified curve through the live application.

Every loaded file's `metadata.built_in` must be explicitly `true` --
enforced here, not merely a convention -- so a file that is missing this
flag (e.g. accidentally copied from an export) is rejected rather than
silently entering the built-in catalogue.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.reference_profile import (
    ReferenceProfile,
    ReferenceProfileValidationError,
    UnsupportedReferenceProfileSchemaVersionError,
    profile_from_json_dict,
)

#: The production built-in directory -- ships empty (task section 9).
DEFAULT_BUILTIN_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "reference_profiles" / "builtin"


class BuiltinReferenceProfileLoadError(ValueError):
    """Raised when a file under the built-in directory fails to parse/
    validate, or is missing the required `metadata.built_in: true` flag.
    A defect in a committed built-in file is a real bug -- this is
    intentionally NOT swallowed/skipped, so a broken built-in fails
    application startup loudly rather than silently vanishing from the
    catalogue."""


def load_builtin_profiles(directory: Path | None = None) -> list[ReferenceProfile]:
    """Loads every `*.json` file directly under `directory` (default:
    `DEFAULT_BUILTIN_DIRECTORY`) as a built-in `ReferenceProfile`. The
    profile's own stable `id` is the file's stem (e.g.
    `dev_fixture_flat_envelope.json` -> id `dev_fixture_flat_envelope`)
    -- never a value trusted from inside the file, so the id a caller
    references is always exactly the checked-in filename, and two files
    can never silently collide on an id neither of them declared.

    Returns an empty list for a directory that does not exist or
    contains no `*.json` files (the normal production state today) --
    that is not an error, per this module's own governing constraint.
    Returns profiles sorted by `name` for a deterministic catalogue
    order.
    """
    directory = directory if directory is not None else DEFAULT_BUILTIN_DIRECTORY
    if not directory.is_dir():
        return []
    profiles: list[ReferenceProfile] = []
    for path in sorted(directory.glob("*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BuiltinReferenceProfileLoadError(f"Built-in reference profile file {path.name!r} is not valid JSON: {exc}") from exc
        try:
            profile = profile_from_json_dict(envelope, profile_id=path.stem)
        except (ReferenceProfileValidationError, UnsupportedReferenceProfileSchemaVersionError) as exc:
            raise BuiltinReferenceProfileLoadError(f"Built-in reference profile file {path.name!r} is invalid: {exc.message}") from exc
        if not profile.metadata.built_in:
            raise BuiltinReferenceProfileLoadError(
                f"Built-in reference profile file {path.name!r} must set metadata.built_in = true."
            )
        profiles.append(profile)
    return sorted(profiles, key=lambda p: p.name)
