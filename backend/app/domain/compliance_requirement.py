"""Compliance & Capability -- the measurement REQUIREMENT a Reference
Profile imposes (DEC-167). Pure, framework-free domain layer.

> **Reference defines. Measurement satisfies.**

A Reference Profile owns the unit, the voltage representation and the
phase evaluation of an assessment (DEC-110/DEC-166). The Measurement side
of Compliance never chooses any of those independently -- it derives, from
the active Reference, exactly what the recording has to be able to
provide, and then checks (service layer) whether it can:

```text
ReferenceProfile (unit + AssessmentDefinition)
   -> resolve_requirement() -> MeasurementRequirement
        required_members   which phases/pairs must be assessed
        requires_rms       an RMS representation is demanded
        requires_per_unit  unit == "pu" -> a configured voltage base is demanded
```

Nothing here reads a registry or a waveform, and nothing here is a
default: RMS is required only because the Reference's representation is an
RMS representation, and a per-unit base only because its unit is `pu`.
`kV`/`V` references never need a base.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.assessment_definition import (
    MEMBER_A,
    MEMBER_AB,
    MEMBER_B,
    MEMBER_BC,
    MEMBER_C,
    MEMBER_CA,
    PHASE_TREATMENT_EACH_PHASE,
    PHASE_TREATMENT_MAXIMUM,
    PHASE_TREATMENT_MINIMUM,
    PHASE_TREATMENT_SINGLE,
    PHASE_TREATMENT_UNSPECIFIED,
    REPRESENTATION_LINE_LINE_RMS,
    REPRESENTATION_PHASE_GROUND_RMS,
    REPRESENTATION_POSITIVE_SEQUENCE_RMS,
    REPRESENTATION_UNSPECIFIED,
    AssessmentDefinition,
)
from app.domain.reference_profile import UNIT_PER_UNIT

#: Overall readiness vocabulary of the Measurement card.
READINESS_READY = "ready"
READINESS_ACTION_REQUIRED = "action_required"
READINESS_INCOMPATIBLE = "incompatible"
#: No active Reference Layer: nothing is required yet, so nothing can be ready.
READINESS_NO_REFERENCE = "no_reference"

#: Representations that are RMS representations. Every representation the
#: Assessment Definition can express today is one; the set (not a constant
#: `True`) is what decides, so a future non-RMS representation needs no
#: change to the consumers.
RMS_REPRESENTATIONS = frozenset({
    REPRESENTATION_LINE_LINE_RMS,
    REPRESENTATION_PHASE_GROUND_RMS,
    REPRESENTATION_POSITIVE_SEQUENCE_RMS,
})

LINE_LINE_MEMBERS = (MEMBER_AB, MEMBER_BC, MEMBER_CA)
PHASE_GROUND_MEMBERS = (MEMBER_A, MEMBER_B, MEMBER_C)
#: The single quantity of a positive-sequence representation.
MEMBER_POSITIVE_SEQUENCE = "1"

AGGREGATE_TREATMENTS = (PHASE_TREATMENT_EACH_PHASE, PHASE_TREATMENT_MINIMUM, PHASE_TREATMENT_MAXIMUM)


@dataclass(frozen=True, slots=True)
class MeasurementRequirement:
    """What one Reference imposes on the measurement. `required_members`
    is empty (and `unresolved_reason` set) when the Reference does not
    state enough to know -- Powerwave does not guess a convention."""

    representation: str
    phase_treatment: str
    member: str | None
    unit: str
    required_members: tuple[str, ...]
    requires_rms: bool
    requires_per_unit: bool
    unresolved_reason: str | None = None


def resolve_requirement(definition: AssessmentDefinition, unit: str) -> MeasurementRequirement:
    """Reference unit/representation/phase evaluation -> Measurement
    requirement. Never raises: an under-specified Reference yields a
    requirement with `unresolved_reason`, which the readiness layer reports
    as INCOMPATIBLE (the engineer fixes it in the Reference Profile)."""
    representation = definition.representation
    treatment = definition.phase_treatment
    requires_rms = representation in RMS_REPRESENTATIONS
    requires_per_unit = unit == UNIT_PER_UNIT

    def build(members: tuple[str, ...], reason: str | None = None) -> MeasurementRequirement:
        return MeasurementRequirement(
            representation=representation, phase_treatment=treatment, member=definition.member, unit=unit,
            required_members=members, requires_rms=requires_rms, requires_per_unit=requires_per_unit,
            unresolved_reason=reason,
        )

    if representation == REPRESENTATION_UNSPECIFIED:
        return build((), "The Reference does not state a voltage representation.")
    if representation == REPRESENTATION_POSITIVE_SEQUENCE_RMS:
        return build((MEMBER_POSITIVE_SEQUENCE,))
    all_members = LINE_LINE_MEMBERS if representation == REPRESENTATION_LINE_LINE_RMS else PHASE_GROUND_MEMBERS
    if treatment == PHASE_TREATMENT_UNSPECIFIED:
        return build((), "The Reference does not state how the phases are evaluated.")
    if treatment in AGGREGATE_TREATMENTS:
        return build(all_members)
    if treatment == PHASE_TREATMENT_SINGLE:
        if definition.member in all_members:
            return build((definition.member,))
        return build((), "The Reference selects a single voltage but does not name it.")
    return build((), f"Unknown phase evaluation {treatment!r}.")
