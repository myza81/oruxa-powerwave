# Built-in Reference Profiles

This directory is the production built-in Reference Profile catalogue
loaded by `app.domain.reference_profile_builtins.load_builtin_profiles()`
(Compliance Slice 3/4, DEC-109/DEC-110/DEC-111).

**It is intentionally empty.**

**Powerwave Compliance is jurisdiction-neutral, utility-neutral, and
OEM-neutral by architecture (DEC-111).** An engineer in Malaysia,
England, Australia, or anywhere else sees the same generic product —
Powerwave does not automatically bundle a "home country" grid code
merely because of where the application happens to have been developed.
Grid codes, OEM capability envelopes, project requirements, and custom
curves all share the exact same portable `ReferenceProfile` JSON schema;
none of them are ever hardcoded as a calculation branch in production
domain/service code (enforced directly by
`backend/tests/test_reference_profile_jurisdiction_neutrality.py`).

Separately, and *also* true today: built-in reference profiles must
never be fabricated from memory, prior chat history, assumptions, or
generic industry curves (Compliance Slice 3's own governing constraint,
DEC-109). The Malaysia Grid Code LVRT/HVRT values (and any other named
grid code or OEM equipment-capability curve) are not present anywhere in
this repository as an authoritative, verified source, so no production
built-in profile for any of them has been created. Even once a verified
source exists for one jurisdiction's requirement, bundling it here does
not change the point above: production still ships **zero** built-in
profiles by default, and adding one for e.g. Malaysia would never imply
or require adding one for every other jurisdiction — a future deployment
is free to bundle exactly the profiles relevant to its own customer base
(`reference_profiles/malaysia_grid_code_2025.json` in one deployment,
`gb_grid_code_xxx.json` in another), all validated through this exact
same, unchanged parser.

Adding a real built-in profile here requires an authoritative, verified
source document for its exact values (e.g. a cited grid code clause, an
OEM datasheet) — once that source exists, add a version-controlled
`<id>.json` file here in the same schema
`app.domain.reference_profile.profile_from_json_dict()` accepts for
import (`{"schema_version": 2, "profile": {...}}` — see
`app.domain.assessment_definition` for the `assessment_definition`
object this schema now requires instead of a bare `evaluation_quantity`
string), with `profile.metadata.built_in` set to `true` and, once the
source has been checked, `profile.metadata.verified` set to `true`, plus
`profile.metadata.jurisdiction`/`authority`/`document_title`/
`document_revision`/`effective_date`/`source_section`/`source_page`
naming that source precisely enough that an engineer can tell exactly
which requirement/revision they are looking at (a later revision of the
same jurisdiction's requirement is added as an independent profile, not
a replacement — see DEC-111).

The loader itself (directory scan, JSON parse, schema/domain validation,
`built_in` flag enforcement) is fully exercised by
`backend/tests/test_reference_profile_builtins.py` against a separate,
clearly-labeled developer/test-only fixture directory — never against
this directory — so the engine is proven ready for a verified profile to
be dropped in here later without this directory needing to contain any
placeholder content today.
