"""Line-to-Line Voltage calculated-channel operation -- pure domain rules
(DEC-115; see docs/project-memory/LINE_TO_LINE_VOLTAGE.md).

A dedicated ENGINEERING operation, deliberately not a generic Subtraction
preset: it derives phase-to-phase voltages VAB/VBC/VCA from one
Engineering Context's own phase-to-neutral voltages Va/Vb/Vc, and every
output it produces carries explicit line-to-line semantics
(`voltage_representation`/`phase_member`) so Per-Unit, Measurement
Groups, Analysis and Compliance never have to infer them from a name.

Frozen arithmetic convention (cyclic AB -> BC -> CA, never VAC):

    VAB = VA - VB
    VBC = VB - VC
    VCA = VC - VA

Always an exact difference of the two phase quantities -- NEVER
`sqrt(3) x VLN`, so the result stays correct during unbalanced
disturbances. The instantaneous path's pointwise subtraction reuses
`app.domain.calculated_channel.evaluate_subtraction()` unchanged.

This module is framework-free (domain-layer contract): it owns the pair
table, output-mode vocabulary, naming, and evaluation only. Resolving an
Engineering Context's roles, eligibility and atomic creation live in
`app.services.line_to_line_voltage_service`.
"""

from __future__ import annotations

import numpy as np

from app.domain.calculated_channel import evaluate_subtraction
from app.domain.phase_identity import (
    PHASE_A,
    PHASE_AB,
    PHASE_B,
    PHASE_BC,
    PHASE_C,
    PHASE_CA,
    PhaseDisplayConvention,
    phase_symbol_text,
)

#: The `CalculatedChannel.operation` value for every output of this
#: operation. Deliberately NOT a member of
#: `app.domain.calculated_channel.ALL_OPERATIONS`: the generic
#: `POST .../calculated-channels` endpoint must never be able to create a
#: line-to-line channel from two arbitrary inputs, bypassing the
#: Engineering Context role resolution and representation guardrails this
#: operation exists to enforce.
OP_LINE_TO_LINE_VOLTAGE = "line_to_line_voltage"

#: The phase-voltage role keys, identical to the Phasor requirement role
#: keys (`app.domain.analysis_requirements`) so readiness results read the
#: same way across Analysis and Calculated Channels.
ROLE_VA = "Va"
ROLE_VB = "Vb"
ROLE_VC = "Vc"
PHASE_ROLE_KEYS = (ROLE_VA, ROLE_VB, ROLE_VC)
ROLE_KEY_BY_PHASE = {PHASE_A: ROLE_VA, PHASE_B: ROLE_VB, PHASE_C: ROLE_VC}
PHASE_BY_ROLE_KEY = {role_key: phase for phase, role_key in ROLE_KEY_BY_PHASE.items()}

#: pair -> (minuend phase, subtrahend phase). The one place the frozen
#: convention is expressed; everything else reads it from here.
PAIR_OPERANDS: dict[str, tuple[str, str]] = {
    PHASE_AB: (PHASE_A, PHASE_B),
    PHASE_BC: (PHASE_B, PHASE_C),
    PHASE_CA: (PHASE_C, PHASE_A),
}
PAIR_ORDER = (PHASE_AB, PHASE_BC, PHASE_CA)

OUTPUT_ALL_THREE = "all_three"
KNOWN_OUTPUTS = PAIR_ORDER + (OUTPUT_ALL_THREE,)

#: Source-representation path an output was derived from. Only the
#: instantaneous path is implemented; `SOURCE_PATH_PHASOR` is recognized
#: vocabulary for the documented, deferred complex-phasor path (see the
#: design document) so the stored metadata contract does not change when
#: it lands.
SOURCE_PATH_INSTANTANEOUS = "instantaneous"
SOURCE_PATH_PHASOR = "phasor"


def output_valid(output: str) -> bool:
    return output in KNOWN_OUTPUTS


def pairs_for_output(output: str) -> tuple[str, ...]:
    """`"AB"` -> `("AB",)`; `"all_three"` -> `("AB", "BC", "CA")`.
    Raises `ValueError` for an unknown output (callers validate first)."""
    if output == OUTPUT_ALL_THREE:
        return PAIR_ORDER
    if output in PAIR_OPERANDS:
        return (output,)
    raise ValueError(f"Unknown line-to-line output {output!r}.")


def required_phases(output: str) -> tuple[str, ...]:
    """The phase-to-neutral phases an output needs, in A/B/C order --
    VAB needs A+B, VBC needs B+C, VCA needs C+A, All Three needs A+B+C."""
    needed = {phase for pair in pairs_for_output(output) for phase in PAIR_OPERANDS[pair]}
    return tuple(phase for phase in (PHASE_A, PHASE_B, PHASE_C) if phase in needed)


def default_output_name(
    context_display_name: str, pair: str, phase_display: PhaseDisplayConvention | None = None
) -> str:
    """Bay-aware default name in the bay's own phase display convention
    (DEC-118): `"MCRS VAB"` for an A/B/C bay, `"KPDN1 VRY"` for an R/Y/B
    bay. Only the NAME follows the convention; `phase_member` stays the
    canonical pair. Without a display convention the canonical spelling is
    used, exactly as before DEC-118."""
    return f"{context_display_name.strip()} {phase_symbol_text('V', pair, phase_display)}".strip()


def evaluate_line_to_line_instantaneous(minuend: np.ndarray, subtrahend: np.ndarray) -> np.ndarray:
    """Pointwise `v_from(t) - v_to(t)` over an already-aligned, already
    null-policy-applied pair of instantaneous phase-voltage arrays --
    delegates to the generic `evaluate_subtraction()` so there is exactly
    one subtraction implementation in the codebase."""
    return evaluate_subtraction([minuend, subtrahend])
