"""Compliance & Capability -- Assessment Definition (Slice 4 architecture
refinement, DEC-110). Pure, framework-free domain layer -- no registry
access, no waveform fetch, no dependency on `app.domain.reference_profile`
(kept deliberately independent to avoid a circular import -- that module
imports FROM this one, never the reverse; see this module's own
`AssessmentDefinitionValidationError`, a distinct exception type from
`app.domain.reference_profile.ReferenceProfileValidationError`, which
translates errors raised here at the `ReferenceProfile` boundary).

**Owner UAT finding this decision answers**: `ReferenceProfile.
evaluation_quantity` (Slice 3) conflated two genuinely different
concepts. A grid-code/utility/OEM requirement usually specifies ONE
voltage-time boundary curve, but the CONVENTION for deriving a
comparable measured value from a three-phase recording varies by
jurisdiction/document and is sometimes not specified at all:

```text
Reference Profile      = what boundary/curve is required
Assessment Definition  = how the measured voltage is derived for comparison
```

This module owns ONLY the second concept. It does not derive, resolve,
or compute anything from a real waveform -- it defines the SEMANTICS and
VALIDATES sensible combinations only; an actual measurement resolver
(Va/Vb/Vc -> VAB/VBC/VCA derivation, min/max aggregation, positive-
sequence calculation, each-phase evaluation) is explicit future-slice
work (task section 15).

**`unspecified` is a first-class state, not an error** (task section 8):
when a requirement genuinely does not specify enough detail (e.g. "voltage
at the connection point" with no L-L/L-N or aggregation convention
stated), Powerwave must not guess -- `AssessmentDefinition()` (every
field at its own `..._UNSPECIFIED`/`None` default) is a fully valid,
meaningful state representing "this requires human confirmation later",
never silently resolved to a default engineering assumption.

**Deliberately NOT an open enum universe** (task section 3's own "do not
overbuild" instruction): five narrow, closed axes for v1
(`quantity_family`, `representation`, `phase_treatment`,
`measurement_location`, `provenance`), plus one optional `member` for the
genuinely member-specific case (task section 7). Extending this later
(e.g. a `current` quantity_family, a `zero_sequence_rms` representation)
means adding a new constant to the relevant closed tuple -- never a
schema rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: v1 supports only Voltage -- the SAME quantity_family Compliance Slice
#: 2's own canonical catalogue exists for. Not overbuilt with a `current`
#: member until Compliance actually needs one.
QUANTITY_FAMILY_VOLTAGE = "voltage"
KNOWN_QUANTITY_FAMILIES = (QUANTITY_FAMILY_VOLTAGE,)

#: What ELECTRICAL representation the assessment trace is (task section 3
#: minimum v1 support) -- deliberately mirrors the vocabulary
#: `app.domain.compliance_measurement`'s own `VOLTAGE_REPRESENTATION_*`
#: constants use conceptually, WITHOUT importing that module (this stays
#: a standalone domain concept a future measurement resolver bridges,
#: never a hard dependency in either direction).
REPRESENTATION_LINE_LINE_RMS = "line_line_rms"
REPRESENTATION_PHASE_GROUND_RMS = "phase_ground_rms"
REPRESENTATION_POSITIVE_SEQUENCE_RMS = "positive_sequence_rms"
REPRESENTATION_UNSPECIFIED = "unspecified"
KNOWN_REPRESENTATIONS = (
    REPRESENTATION_LINE_LINE_RMS,
    REPRESENTATION_PHASE_GROUND_RMS,
    REPRESENTATION_POSITIVE_SEQUENCE_RMS,
    REPRESENTATION_UNSPECIFIED,
)

#: HOW multiple phases/pairs combine into one assessment trace.
PHASE_TREATMENT_MINIMUM = "minimum"
PHASE_TREATMENT_MAXIMUM = "maximum"
PHASE_TREATMENT_EACH_PHASE = "each_phase"
PHASE_TREATMENT_SINGLE = "single"
PHASE_TREATMENT_UNSPECIFIED = "unspecified"
KNOWN_PHASE_TREATMENTS = (
    PHASE_TREATMENT_MINIMUM,
    PHASE_TREATMENT_MAXIMUM,
    PHASE_TREATMENT_EACH_PHASE,
    PHASE_TREATMENT_SINGLE,
    PHASE_TREATMENT_UNSPECIFIED,
)

#: WHERE the requirement is measured -- informational only in this
#: slice (no code path reads it to change behaviour), carried so a later
#: slice/report can state it without a schema change.
LOCATION_CONNECTION_POINT = "connection_point"
LOCATION_EQUIPMENT_TERMINAL = "equipment_terminal"
LOCATION_PROJECT_DEFINED = "project_defined"
LOCATION_UNSPECIFIED = "unspecified"
KNOWN_MEASUREMENT_LOCATIONS = (
    LOCATION_CONNECTION_POINT,
    LOCATION_EQUIPMENT_TERMINAL,
    LOCATION_PROJECT_DEFINED,
    LOCATION_UNSPECIFIED,
)

#: WHERE this assessment convention came from -- informational only,
#: same reasoning as `measurement_location`.
PROVENANCE_EXPLICIT_STANDARD = "explicit_standard"
PROVENANCE_UTILITY_CLARIFICATION = "utility_clarification"
PROVENANCE_PROJECT_AGREEMENT = "project_agreement"
PROVENANCE_USER_DEFINED = "user_defined"
PROVENANCE_UNSPECIFIED = "unspecified"
KNOWN_PROVENANCES = (
    PROVENANCE_EXPLICIT_STANDARD,
    PROVENANCE_UTILITY_CLARIFICATION,
    PROVENANCE_PROJECT_AGREEMENT,
    PROVENANCE_USER_DEFINED,
    PROVENANCE_UNSPECIFIED,
)

#: Named members -- only meaningful for a `single`-treatment line-line/
#: phase-ground assessment that names one specific phase/pair (task
#: section 7). Never required for `minimum`/`maximum`/`each_phase`
#: (those are aggregate treatments by definition) or for
#: `positive_sequence_rms` (which has no per-member concept at all).
MEMBER_A = "A"
MEMBER_B = "B"
MEMBER_C = "C"
MEMBER_AB = "AB"
MEMBER_BC = "BC"
MEMBER_CA = "CA"
KNOWN_MEMBERS = (MEMBER_A, MEMBER_B, MEMBER_C, MEMBER_AB, MEMBER_BC, MEMBER_CA)
_PHASE_GROUND_MEMBERS = (MEMBER_A, MEMBER_B, MEMBER_C)
_LINE_LINE_MEMBERS = (MEMBER_AB, MEMBER_BC, MEMBER_CA)


class AssessmentDefinitionValidationError(ValueError):
    """Raised by `validate_assessment_definition()`. Kept as its OWN
    exception type (never `app.domain.reference_profile.
    ReferenceProfileValidationError`) so this module has zero dependency
    on that one -- `app.domain.reference_profile.validate_reference_
    profile()` catches this and re-raises its own error type, prefixing
    `field_name` with `"assessment_definition."` so a caller sees one
    unified error surface at the `ReferenceProfile` boundary."""

    def __init__(self, message: str, *, reason_code: str, field_name: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
        self.field_name = field_name


@dataclass(frozen=True, slots=True)
class AssessmentDefinition:
    """Every field defaults to its own `unspecified`/`None` state --
    `AssessmentDefinition()` (all defaults) is the fully-unspecified
    state (task section 8), always valid on its own.

    `legacy_quantity_hint` preserves an old Slice 3 `evaluation_quantity`
    value that could not be mapped unambiguously (or, for full
    traceability, is preserved alongside a value that WAS mapped) --
    never re-interpreted or displayed as if it were an active field
    (task section 6); purely an audit trail.
    """

    quantity_family: str = QUANTITY_FAMILY_VOLTAGE
    representation: str = REPRESENTATION_UNSPECIFIED
    phase_treatment: str = PHASE_TREATMENT_UNSPECIFIED
    member: str | None = None
    measurement_location: str = LOCATION_UNSPECIFIED
    provenance: str = PROVENANCE_UNSPECIFIED
    legacy_quantity_hint: str | None = None


def validate_assessment_definition(definition: AssessmentDefinition) -> None:
    """Raises `AssessmentDefinitionValidationError` on the first
    structural/semantic violation. Engineering-semantics validation
    (task section 14), never merely field-presence checking:

    - Every enum field must be one of its own known values.
    - An aggregate treatment (`minimum`/`maximum`/`each_phase`) must
      NEVER carry a specific `member` -- a member contradicts the very
      idea of an aggregate.
    - `positive_sequence_rms` has no per-member concept at all -- V1 is
      inherently the whole three-phase set's own positive-sequence
      component, never one named member.
    - `phase_treatment=single` with `representation` in
      (`line_line_rms`, `phase_ground_rms`) REQUIRES an explicit
      `member` -- "single" alone is ambiguous about WHICH one.
    - `phase_treatment=each_phase` is not (yet) supported for
      `representation=line_line_rms` (task section 14's own explicit
      "likely invalid wording/combination unless explicitly modeled as
      each line-pair" -- not modeled in v1; use `phase_ground_rms`, or a
      specific `member` with `phase_treatment=single` per line-pair).
    - A `member`, if present, must belong to the representation's own
      member set (`A`/`B`/`C` for `phase_ground_rms`,
      `AB`/`BC`/`CA` for `line_line_rms`), and requires a specific
      (non-`unspecified`) representation to be meaningful at all.

    When genuinely uncertain, this function prefers rejecting an
    over-specific/contradictory combination over inventing meaning
    (task section 14's own closing instruction) -- `unspecified` is
    always the safe fallback a caller can choose instead."""
    if definition.quantity_family not in KNOWN_QUANTITY_FAMILIES:
        raise AssessmentDefinitionValidationError(
            f"Unknown quantity_family {definition.quantity_family!r} (must be one of {KNOWN_QUANTITY_FAMILIES}).",
            reason_code="unknown_quantity_family", field_name="quantity_family",
        )
    if definition.representation not in KNOWN_REPRESENTATIONS:
        raise AssessmentDefinitionValidationError(
            f"Unknown representation {definition.representation!r} (must be one of {KNOWN_REPRESENTATIONS}).",
            reason_code="unknown_representation", field_name="representation",
        )
    if definition.phase_treatment not in KNOWN_PHASE_TREATMENTS:
        raise AssessmentDefinitionValidationError(
            f"Unknown phase_treatment {definition.phase_treatment!r} (must be one of {KNOWN_PHASE_TREATMENTS}).",
            reason_code="unknown_phase_treatment", field_name="phase_treatment",
        )
    if definition.measurement_location not in KNOWN_MEASUREMENT_LOCATIONS:
        raise AssessmentDefinitionValidationError(
            f"Unknown measurement_location {definition.measurement_location!r} "
            f"(must be one of {KNOWN_MEASUREMENT_LOCATIONS}).",
            reason_code="unknown_measurement_location", field_name="measurement_location",
        )
    if definition.provenance not in KNOWN_PROVENANCES:
        raise AssessmentDefinitionValidationError(
            f"Unknown provenance {definition.provenance!r} (must be one of {KNOWN_PROVENANCES}).",
            reason_code="unknown_provenance", field_name="provenance",
        )
    if definition.member is not None and definition.member not in KNOWN_MEMBERS:
        raise AssessmentDefinitionValidationError(
            f"Unknown member {definition.member!r} (must be one of {KNOWN_MEMBERS}, or omitted).",
            reason_code="unknown_member", field_name="member",
        )

    rep = definition.representation
    treatment = definition.phase_treatment
    member = definition.member

    if treatment in (PHASE_TREATMENT_MINIMUM, PHASE_TREATMENT_MAXIMUM, PHASE_TREATMENT_EACH_PHASE) and member is not None:
        raise AssessmentDefinitionValidationError(
            f"phase_treatment={treatment!r} is an aggregate treatment and must not specify a single "
            f"member (got member={member!r}).",
            reason_code="member_not_applicable_for_aggregate_treatment", field_name="member",
        )

    if rep == REPRESENTATION_POSITIVE_SEQUENCE_RMS and member is not None:
        raise AssessmentDefinitionValidationError(
            "representation='positive_sequence_rms' has no per-member concept; member must not be set.",
            reason_code="member_not_applicable_for_positive_sequence", field_name="member",
        )

    if treatment == PHASE_TREATMENT_SINGLE and rep in (REPRESENTATION_LINE_LINE_RMS, REPRESENTATION_PHASE_GROUND_RMS) and member is None:
        raise AssessmentDefinitionValidationError(
            f"phase_treatment='single' with representation={rep!r} requires an explicit member.",
            reason_code="member_required_for_single_treatment", field_name="member",
        )

    if treatment == PHASE_TREATMENT_EACH_PHASE and rep == REPRESENTATION_LINE_LINE_RMS:
        raise AssessmentDefinitionValidationError(
            "phase_treatment='each_phase' is not supported for representation='line_line_rms' in v1 "
            "(each line-pair independently is not yet modeled) -- use representation='phase_ground_rms', "
            "or a specific member with phase_treatment='single' for one named line-pair.",
            reason_code="each_phase_not_supported_for_line_line", field_name="phase_treatment",
        )

    if member is not None:
        if rep == REPRESENTATION_UNSPECIFIED:
            raise AssessmentDefinitionValidationError(
                "member requires an explicit representation (line_line_rms or phase_ground_rms); "
                "it cannot be set alongside representation='unspecified'.",
                reason_code="member_requires_specific_representation", field_name="member",
            )
        if rep == REPRESENTATION_PHASE_GROUND_RMS and member not in _PHASE_GROUND_MEMBERS:
            raise AssessmentDefinitionValidationError(
                f"member={member!r} is not a valid phase-ground member (must be one of {_PHASE_GROUND_MEMBERS}).",
                reason_code="member_representation_mismatch", field_name="member",
            )
        if rep == REPRESENTATION_LINE_LINE_RMS and member not in _LINE_LINE_MEMBERS:
            raise AssessmentDefinitionValidationError(
                f"member={member!r} is not a valid line-line member (must be one of {_LINE_LINE_MEMBERS}).",
                reason_code="member_representation_mismatch", field_name="member",
            )


#: Task section 6/5: unambiguous mapping from a Slice 3 v1
#: `evaluation_quantity` id (`app.domain.compliance_measurement.
#: VOLTAGE_QUANTITIES`) to its equivalent `AssessmentDefinition`. Every
#: v1 canonical quantity maps cleanly (each one already implies exactly
#: one representation/phase_treatment/member combination) -- there is no
#: "cannot map without guessing" case for a value that is genuinely one
#: of these nine ids; an id OUTSIDE this table (a typo, a future
#: addition this table has not caught up with) is the only case that
#: falls back to `unspecified` (see `assessment_definition_from_legacy_
#: quantity()` below).
_LEGACY_QUANTITY_MAPPING: dict[str, AssessmentDefinition] = {
    "phase_a_lg_rms": AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_A),
    "phase_b_lg_rms": AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_B),
    "phase_c_lg_rms": AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_C),
    "phase_ab_ll_rms": AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_AB),
    "phase_bc_ll_rms": AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_BC),
    "phase_ca_ll_rms": AssessmentDefinition(representation=REPRESENTATION_LINE_LINE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE, member=MEMBER_CA),
    "min_phase_lg_rms": AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_MINIMUM),
    "max_phase_lg_rms": AssessmentDefinition(representation=REPRESENTATION_PHASE_GROUND_RMS, phase_treatment=PHASE_TREATMENT_MAXIMUM),
    "positive_sequence_rms": AssessmentDefinition(representation=REPRESENTATION_POSITIVE_SEQUENCE_RMS, phase_treatment=PHASE_TREATMENT_SINGLE),
}


def assessment_definition_from_legacy_quantity(quantity_id: str | None) -> AssessmentDefinition:
    """Task section 6: migrates a Slice 3 v1 profile's own
    `evaluation_quantity` string into an equivalent `AssessmentDefinition`.
    A recognized canonical id maps directly (still stamped with
    `legacy_quantity_hint` for traceability); an unrecognized one becomes
    fully `unspecified` EXCEPT for `legacy_quantity_hint`, which
    preserves the original value rather than discarding it -- "if an old
    quantity cannot be mapped without guessing... preserve the legacy
    value for traceability" (task section 6). Never raises -- there is no
    input this function cannot represent, by construction."""
    if not quantity_id:
        return AssessmentDefinition()
    mapped = _LEGACY_QUANTITY_MAPPING.get(quantity_id)
    if mapped is not None:
        return replace(mapped, legacy_quantity_hint=quantity_id)
    return AssessmentDefinition(legacy_quantity_hint=quantity_id)


def assessment_definition_to_dict(definition: AssessmentDefinition) -> dict:
    return {
        "quantity_family": definition.quantity_family,
        "representation": definition.representation,
        "phase_treatment": definition.phase_treatment,
        "member": definition.member,
        "measurement_location": definition.measurement_location,
        "provenance": definition.provenance,
        "legacy_quantity_hint": definition.legacy_quantity_hint,
    }


def assessment_definition_from_dict(data: object) -> AssessmentDefinition:
    """Parses a v2 profile JSON's own `assessment_definition` object.
    Raises a plain `(TypeError, ValueError)` on structurally malformed
    input -- callers (`app.domain.reference_profile.profile_from_json_dict()`)
    already catch that broadly for the rest of the profile body; semantic
    validity (not just shape) is a separate, later
    `validate_assessment_definition()` call, never performed here."""
    data = data if isinstance(data, dict) else {}
    member = data.get("member")
    legacy_hint = data.get("legacy_quantity_hint")
    return AssessmentDefinition(
        quantity_family=str(data.get("quantity_family", QUANTITY_FAMILY_VOLTAGE)),
        representation=str(data.get("representation", REPRESENTATION_UNSPECIFIED)),
        phase_treatment=str(data.get("phase_treatment", PHASE_TREATMENT_UNSPECIFIED)),
        member=str(member) if member is not None else None,
        measurement_location=str(data.get("measurement_location", LOCATION_UNSPECIFIED)),
        provenance=str(data.get("provenance", PROVENANCE_UNSPECIFIED)),
        legacy_quantity_hint=str(legacy_hint) if legacy_hint is not None else None,
    )
