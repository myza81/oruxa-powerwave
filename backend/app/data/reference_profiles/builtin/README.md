# Built-in Reference Profiles

This directory is the production built-in Reference Profile catalogue
loaded by `app.domain.reference_profile_builtins.load_builtin_profiles()`
(Compliance Slice 3).

**It is intentionally empty.**

Per Compliance Slice 3's own explicit governing constraint (task section
9, owner instruction): built-in reference profiles must never be
fabricated from memory, prior chat history, assumptions, or generic
industry curves. The Malaysia Grid Code LVRT/HVRT values (and any other
named grid code or OEM equipment-capability curve) are not present
anywhere in this repository as an authoritative, verified source, so no
production built-in profile for any of them has been created.

Adding a real built-in profile here requires an authoritative, verified
source document for its exact values (e.g. a cited grid code clause, an
OEM datasheet) — once that source exists, add a version-controlled
`<id>.json` file here in the same schema
`app.domain.reference_profile.profile_from_json_dict()` accepts for
import (`{"schema_version": 1, "profile": {...}}`), with
`profile.metadata.built_in` set to `true` and, once the source has been
checked, `profile.metadata.verified` set to `true`, plus
`profile.metadata.source_document`/`source_revision` naming that source.

The loader itself (directory scan, JSON parse, schema/domain validation,
`built_in` flag enforcement) is fully exercised by
`backend/tests/test_reference_profile_builtins.py` against a separate,
clearly-labeled developer/test-only fixture directory — never against
this directory — so the engine is proven ready for a verified profile to
be dropped in here later without this directory needing to contain any
placeholder content today.
