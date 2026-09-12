"""Analysis Requirement definitions (Analysis Guardrail Slice 2; see
docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md).

A small, closed set of explicit typed constants -- deliberately NOT a
general-purpose rules engine (owner instruction). Each
`AnalysisRequirement` declares the exact set of engineering ROLES
(`RoleSpec`) one analysis mode needs; the resolver (`app.domain.
analysis_input_resolution`) matches these against one
`EngineeringContext`'s own membership at request time. Adding a new
analysis mode later is adding one more module-level constant here, never
a schema/engine change.

**Phasor Analysis is the first planned consumer**, so these are its
input-role requirements ONLY -- they identify which WAVEFORM SAMPLES a
future phasor engine needs (Va, Vb, Vc, Ia, Ib, Ic), they do NOT
calculate a phasor. How a phasor is derived from waveform samples is
entirely a later feature's concern; this module only answers "which
signal role does this analysis need," never "what does it do with it."
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.phase_identity import PHASE_A, PHASE_B, PHASE_C

#: Deliberately the only representation Slice 2 recognizes. A plain
#: sampled waveform value -- NOT a claim that the underlying signal is
#: already a phasor, an RMS value, or any other derived representation.
#: `RoleSpec.representation` exists as a distinct field (not hard-coded
#: away) purely so a later representation (e.g. `phase_to_phase`, a
#: future sequence-component quantity) can be added as one more
#: recognized value without a `RoleSpec`/resolver shape change --
#: nothing beyond `"sampled"` is matched against in this slice, per the
#: owner's own "minimum vocabulary required today" instruction.
REPRESENTATION_SAMPLED = "sampled"
KNOWN_REPRESENTATIONS = (REPRESENTATION_SAMPLED,)


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """One required engineering role within an `AnalysisRequirement`.
    `role_key` is the human-facing label a resolution result uses to
    identify this role (e.g. `"Va"`) -- unique within its own
    `AnalysisRequirement.required_roles`, never used as a matching
    criterion itself (matching is purely `engineering_type` + `phase`,
    per the owner's own "do not use channel names during resolution"
    instruction -- `role_key` is not a channel name, but is kept
    deliberately uninvolved in matching all the same, so renaming a role
    key can never silently change which channels resolve)."""

    role_key: str
    engineering_type: str
    phase: str
    representation: str = REPRESENTATION_SAMPLED


@dataclass(frozen=True, slots=True)
class AnalysisRequirement:
    """One analysis mode's own full set of required roles.
    `(analysis_kind, mode)` is this requirement's own stable identity --
    used as the resolver's lookup key, never `role_key`s or a generated
    id."""

    analysis_kind: str
    mode: str
    required_roles: tuple[RoleSpec, ...]


def _voltage_role(role_key: str, phase: str) -> RoleSpec:
    return RoleSpec(role_key=role_key, engineering_type=VOLTAGE, phase=phase)


def _current_role(role_key: str, phase: str) -> RoleSpec:
    return RoleSpec(role_key=role_key, engineering_type=CURRENT, phase=phase)


#: Phasor Analysis's own input-role requirements -- single-phase A/B/C
#: and three-phase, for both Voltage and Current. Representative but
#: complete for this quantity/mode shape (trivial to enumerate fully;
#: the owner's own instruction was to avoid inventing PERMUTATIONS
#: merely to enlarge the registry, e.g. phase-to-phase Vab/Vbc/Vca modes
#: -- those are explicitly deferred, see `REPRESENTATION_SAMPLED`'s own
#: docstring and ANALYSIS_INPUT_GUARDRAILS.md).
PHASOR_VOLTAGE_PHASE_A = AnalysisRequirement("phasor", "voltage_phase_a", (_voltage_role("Va", PHASE_A),))
PHASOR_VOLTAGE_PHASE_B = AnalysisRequirement("phasor", "voltage_phase_b", (_voltage_role("Vb", PHASE_B),))
PHASOR_VOLTAGE_PHASE_C = AnalysisRequirement("phasor", "voltage_phase_c", (_voltage_role("Vc", PHASE_C),))
PHASOR_VOLTAGE_THREE_PHASE = AnalysisRequirement(
    "phasor", "voltage_three_phase",
    (_voltage_role("Va", PHASE_A), _voltage_role("Vb", PHASE_B), _voltage_role("Vc", PHASE_C)),
)
PHASOR_CURRENT_PHASE_A = AnalysisRequirement("phasor", "current_phase_a", (_current_role("Ia", PHASE_A),))
PHASOR_CURRENT_PHASE_B = AnalysisRequirement("phasor", "current_phase_b", (_current_role("Ib", PHASE_B),))
PHASOR_CURRENT_PHASE_C = AnalysisRequirement("phasor", "current_phase_c", (_current_role("Ic", PHASE_C),))
PHASOR_CURRENT_THREE_PHASE = AnalysisRequirement(
    "phasor", "current_three_phase",
    (_current_role("Ia", PHASE_A), _current_role("Ib", PHASE_B), _current_role("Ic", PHASE_C)),
)

#: Overcurrent Analysis v1's own input-role requirements -- the identical
#: single-phase-current role shape Phasor's own PHASOR_CURRENT_PHASE_A/B/C
#: already use (same `_current_role` helper, same role keys), just under
#: a distinct `analysis_kind` -- Overcurrent needs exactly ONE current
#: phase resolved per analysis (the engineer's own chosen phase), never a
#: three-phase requirement.
OVERCURRENT_CURRENT_PHASE_A = AnalysisRequirement("overcurrent", "current_phase_a", (_current_role("Ia", PHASE_A),))
OVERCURRENT_CURRENT_PHASE_B = AnalysisRequirement("overcurrent", "current_phase_b", (_current_role("Ib", PHASE_B),))
OVERCURRENT_CURRENT_PHASE_C = AnalysisRequirement("overcurrent", "current_phase_c", (_current_role("Ic", PHASE_C),))

_KNOWN_REQUIREMENTS: tuple[AnalysisRequirement, ...] = (
    PHASOR_VOLTAGE_PHASE_A, PHASOR_VOLTAGE_PHASE_B, PHASOR_VOLTAGE_PHASE_C, PHASOR_VOLTAGE_THREE_PHASE,
    PHASOR_CURRENT_PHASE_A, PHASOR_CURRENT_PHASE_B, PHASOR_CURRENT_PHASE_C, PHASOR_CURRENT_THREE_PHASE,
    OVERCURRENT_CURRENT_PHASE_A, OVERCURRENT_CURRENT_PHASE_B, OVERCURRENT_CURRENT_PHASE_C,
)

_REQUIREMENTS_BY_KEY: dict[tuple[str, str], AnalysisRequirement] = {
    (r.analysis_kind, r.mode): r for r in _KNOWN_REQUIREMENTS
}


def get_requirement(analysis_kind: str, mode: str) -> AnalysisRequirement | None:
    """Returns the matching requirement, or `None` if `(analysis_kind,
    mode)` is not recognized. Never raises -- the caller (service layer)
    decides how to translate an unrecognized pair into a request error."""
    return _REQUIREMENTS_BY_KEY.get((analysis_kind, mode))


def known_requirements() -> tuple[AnalysisRequirement, ...]:
    return _KNOWN_REQUIREMENTS
