"""Sequence Components v1 -- positive/negative/zero-sequence symmetrical
components computed from three-phase Voltage and Current phasors (see
docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md).

**Product definition**: Powerwave calculates the classical Fortescue
symmetrical-component transform from a three-phase set of phasors
(Va/Vb/Vc for Voltage, Ia/Ib/Ic for Current, each family evaluated
independently):

    a = exp(j*2*pi/3)                        (the 120 deg rotation operator)

    X0 = (Xa + Xb + Xc) / 3                  (zero sequence)
    X1 = (Xa + a*Xb + a^2*Xc) / 3             (positive sequence)
    X2 = (Xa + a^2*Xb + a*Xc) / 3             (negative sequence)

This is calculation + visualization only -- explicitly NOT protection
interpretation: no unbalance limits, negative-sequence relay operation,
ground-fault analysis, or fault classification exist anywhere in this
module (see module footer).

Pure, framework-free -- zero registry/I/O access, mirroring
`app.domain.impedance`'s own layering. `app.services.
sequence_components_analysis_service` is the only caller for Recording
mode, and owns resolving Va/Vb/Vc/Ia/Ib/Ic (by reusing the existing,
unchanged `compute_phasor_diagram()` -- never a second phasor estimator).

## Angle convention

`Xa`/`Xb`/`Xc` are built from each phasor's own ABSOLUTE angle
(`angle_deg_absolute`, the identical convention Impedance Locus's own
`theta_Z = theta_V - theta_I` and Phasor's own combined-diagram vector
geometry already use) -- never independently zero-referenced, which
would destroy the true inter-phase angular relationship this transform
depends on entirely.

## Complex-number representation

This is the first module in this codebase to need genuine complex-number
arithmetic (a linear combination of three rotated phasors) -- rather
than hand-rolling real/imaginary-part bookkeeping (`app.domain.phasor`'s
own style, chosen there to keep a hot per-sample estimation loop
simple), this module uses the stdlib `complex`/`cmath` directly: there is
exactly one of these transforms per analysis (never a per-sample loop),
so there is no performance reason to avoid it, and the native complex
type keeps the implementation directly checkable against the textbook
definition above.

## Complete-phase-set requirement

Unlike Phasor's own six-independent-role diagram (where one role's own
status never affects another), a sequence-component transform is
mathematically meaningless without all three phases of ONE family
present. `app.services.sequence_components_analysis_service` requires
Va+Vb+Vc (or Ia+Ib+Ic) all `available` before calling
`compute_symmetrical_components()` for that family; an incomplete family
is reported `missing`/`needs_configuration`/`ambiguous`/`not_eligible`
(the worst of the three roles' own statuses), never a fabricated missing
phase. Voltage and Current families are evaluated completely
independently -- one family's own incompleteness never affects the
other's.

## Sequence ratios -- numerical validity, not a protection threshold

`|X2|/|X1|` and `|X0|/|X1|` are purely descriptive (task's own explicit
"these ratios are descriptive only, never compare against protection
thresholds in v1" instruction). `MIN_POSITIVE_SEQUENCE_MAGNITUDE` guards
the division only -- when `|X1|` is effectively zero, the ratio is
reported unavailable (`None`), never `Infinity`/`NaN`.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field

from app.domain.calculated_channel import ChannelRef

#: Bump ONLY when the transform/interpretation itself changes -- never
#: for an unrelated refactor. Included unconditionally in every result.
ALGORITHM_VERSION = "sequence_components_v1"

#: Bumped only if Manual Sequence Components' own composition changes --
#: independent of `ALGORITHM_VERSION`, since Manual mode uses no
#: waveform/Phasor-estimation concept at all (mirrors `app.domain.
#: impedance.MANUAL_ALGORITHM_VERSION`'s own independence).
MANUAL_ALGORITHM_VERSION = "sequence_components_manual_v1"

#: Reuses the SAME five-value vocabulary `compute_phasor_diagram()`/
#: `app.domain.impedance` already return per role/result, never
#: inventing a new one.
SEQUENCE_STATUS_COMPUTED = "computed"
SEQUENCE_STATUS_NEEDS_CONFIGURATION = "needs_configuration"
SEQUENCE_STATUS_MISSING = "missing"
SEQUENCE_STATUS_AMBIGUOUS = "ambiguous"
SEQUENCE_STATUS_NOT_ELIGIBLE = "not_eligible"
KNOWN_SEQUENCE_STATUSES = (
    SEQUENCE_STATUS_COMPUTED, SEQUENCE_STATUS_NEEDS_CONFIGURATION, SEQUENCE_STATUS_MISSING,
    SEQUENCE_STATUS_AMBIGUOUS, SEQUENCE_STATUS_NOT_ELIGIBLE,
)

#: One family (Voltage or Current) has fewer than three `available`
#: phases -- the complete-phase-set guardrail's own reason code.
REASON_INCOMPLETE_PHASE_SET = "incomplete_phase_set"

#: Numerical-validity floor for the |X2|/|X1| and |X0|/|X1| ratios only
#: -- guards the division, never a protection/unbalance threshold (task's
#: own section 18). Deliberately tiny (this only needs to exclude
#: genuine floating-point-zero, unlike e.g. `app.domain.impedance.
#: MIN_CURRENT_A`, which excludes a whole physically-meaningless
#: measurement range for a different purpose).
MIN_POSITIVE_SEQUENCE_MAGNITUDE = 1e-9

#: `a = 1 /_ 120 deg`, the symmetrical-component rotation operator.
_ALPHA = cmath.exp(1j * 2.0 * math.pi / 3.0)
_ALPHA_SQUARED = _ALPHA * _ALPHA


def _normalize_angle_deg(angle_deg: float) -> float:
    """Identical shape to `app.domain.phasor._normalize_angle_deg()` --
    re-declared here rather than imported, matching this codebase's own
    established "each analyzer module owns its own tiny helper/tolerance
    constant" convention (see `app.domain.impedance._normalize_angle_deg()`
    for the same precedent)."""
    normalized = float(angle_deg) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _to_complex(magnitude: float, angle_deg: float) -> complex:
    return cmath.rect(magnitude, math.radians(angle_deg))


def _to_magnitude_angle(value: complex) -> tuple[float, float]:
    magnitude, angle_rad = cmath.polar(value)
    return magnitude, _normalize_angle_deg(math.degrees(angle_rad))


@dataclass(frozen=True, slots=True)
class SequenceComponentTriplet:
    """One family's own zero/positive/negative sequence result --
    always mathematically defined for any three finite complex values
    (the complete-phase-set GUARDRAIL, deciding whether it is meaningful
    to call this at all, is the caller's own responsibility -- see
    `app.services.sequence_components_analysis_service`)."""

    zero_magnitude: float
    zero_angle_deg: float
    positive_magnitude: float
    positive_angle_deg: float
    negative_magnitude: float
    negative_angle_deg: float


def compute_symmetrical_components(
    magnitude_a: float, angle_a_deg: float,
    magnitude_b: float, angle_b_deg: float,
    magnitude_c: float, angle_c_deg: float,
) -> SequenceComponentTriplet:
    """The one transform entry point -- `X0 = (Xa+Xb+Xc)/3`, `X1 =
    (Xa+a*Xb+a^2*Xc)/3`, `X2 = (Xa+a^2*Xb+a*Xc)/3`, `a = exp(j*120deg)`.
    Always succeeds numerically for any finite inputs (a genuinely
    unbalanced or degenerate set of phasors is a normal, valid result --
    e.g. `Xb`/`Xc` both zero still produces a well-defined X0/X1/X2).
    Callers are responsible for validating the three inputs are actually
    available/meaningful BEFORE calling this."""
    xa = _to_complex(magnitude_a, angle_a_deg)
    xb = _to_complex(magnitude_b, angle_b_deg)
    xc = _to_complex(magnitude_c, angle_c_deg)

    x0 = (xa + xb + xc) / 3.0
    x1 = (xa + _ALPHA * xb + _ALPHA_SQUARED * xc) / 3.0
    x2 = (xa + _ALPHA_SQUARED * xb + _ALPHA * xc) / 3.0

    zero_magnitude, zero_angle_deg = _to_magnitude_angle(x0)
    positive_magnitude, positive_angle_deg = _to_magnitude_angle(x1)
    negative_magnitude, negative_angle_deg = _to_magnitude_angle(x2)
    return SequenceComponentTriplet(
        zero_magnitude=zero_magnitude, zero_angle_deg=zero_angle_deg,
        positive_magnitude=positive_magnitude, positive_angle_deg=positive_angle_deg,
        negative_magnitude=negative_magnitude, negative_angle_deg=negative_angle_deg,
    )


def sequence_ratio_percent(numerator_magnitude: float, positive_sequence_magnitude: float) -> float | None:
    """`numerator / |X1| * 100`, guarded against a near-zero positive-
    sequence denominator (task's own section 18 -- numerical validity
    only, never a protection threshold). Returns `None` (never
    `Infinity`/`NaN`) when `|X1|` is effectively zero."""
    if not math.isfinite(positive_sequence_magnitude) or positive_sequence_magnitude < MIN_POSITIVE_SEQUENCE_MAGNITUDE:
        return None
    return (numerator_magnitude / positive_sequence_magnitude) * 100.0


# ---------------------------------------------------------------------------
# Recording mode -- a concrete, Sequence-Components-owned result shape
# (never persisted, never a generic cross-analysis framework), mirroring
# `app.domain.impedance.ImpedanceAnalysisResult`'s own precedent, doubled
# for the two independent families (Voltage, Current).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SequenceFamilyResult:
    """One family's (Voltage or Current) own sequence-component result.
    `phase_a_channel_ref`/`phase_b_channel_ref`/`phase_c_channel_ref` are
    populated whenever that phase's own role identity is known
    (Recording mode only -- Manual mode never has a channel identity),
    regardless of this family's own `status` -- mirrors
    `ImpedanceAnalysisResult.voltage_channel_ref`'s own "identity known,
    independent of overall status" precedent, so the shared Related
    Waveforms panel can always show the underlying Va/Vb/Vc (or
    Ia/Ib/Ic) source waveforms even when the sequence transform itself
    could not be computed."""

    status: str
    zero_sequence_magnitude: float | None = None
    zero_sequence_angle_deg: float | None = None
    positive_sequence_magnitude: float | None = None
    positive_sequence_angle_deg: float | None = None
    negative_sequence_magnitude: float | None = None
    negative_sequence_angle_deg: float | None = None
    negative_sequence_ratio_percent: float | None = None
    zero_sequence_ratio_percent: float | None = None
    unit: str | None = None
    phase_a_channel_ref: ChannelRef | None = None
    phase_b_channel_ref: ChannelRef | None = None
    phase_c_channel_ref: ChannelRef | None = None
    reason_code: str | None = None
    message: str = ""


def _missing_family() -> SequenceFamilyResult:
    return SequenceFamilyResult(status=SEQUENCE_STATUS_MISSING)


@dataclass(slots=True)
class SequenceAnalysisResult:
    """The reusable Recording-mode result -- always derived fresh,
    never persisted. `status` mirrors `PhasorDiagramResult.status`'s own
    precedent: `computed` even when one or both families are individually
    `missing`/`needs_configuration`/`ambiguous`/`not_eligible` (there is
    still something useful to show); only a genuine whole-diagram
    blocking condition (reference-frequency conflict, timebase
    incompatibility) -- surfaced by the underlying `compute_phasor_
    diagram()` call this reuses -- ever produces `needs_configuration` at
    THIS level, in which case both families report it uniformly."""

    status: str
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None = None
    window_seconds: float | None = None
    algorithm_version: str = ALGORITHM_VERSION
    voltage_sequences: SequenceFamilyResult = field(default_factory=_missing_family)
    current_sequences: SequenceFamilyResult = field(default_factory=_missing_family)
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode (Analysis Input Source = "manual") -- a
# standalone engineering-calculator path, fully decoupled from
# recordings/Engineering Context/Time Groups/Playback -- see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md's own governing invariant
# (DEC-095). Reuses the SAME six-role, two-independent-basis Manual
# Phasor architecture verbatim (`app.domain.phasor.
# evaluate_manual_phasor_role()`/`convert_manual_magnitude_to_secondary()`)
# -- the actual per-role evaluation happens in `app.services.
# sequence_components_analysis_service`, which then reuses the identical
# family-evaluation path Recording mode uses, since both produce the
# same `PhasorDiagramRoleResult` shape.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SequenceManualResult:
    """Deliberately no `engineering_context_id`/`analysis_time`/
    `reference_frequency_hz`/`window_seconds` -- none of those concepts
    exist for a standalone set of manually-entered phasors with no
    recording/time series (mirrors `ManualImpedanceResult`'s own
    field-omission rationale)."""

    status: str
    algorithm_version: str = MANUAL_ALGORITHM_VERSION
    voltage_sequences: SequenceFamilyResult = field(default_factory=_missing_family)
    current_sequences: SequenceFamilyResult = field(default_factory=_missing_family)
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Explicit non-scope boundary (owner instruction -- restated here, not
# just in the module docstring, since this is the single most important
# interpretive boundary of this feature):
#
#   Sequence Components v1 IS: positive-, negative-, and zero-sequence
#   Voltage and Current calculation and visualization, for engineering
#   study.
#
#   Sequence Components v1 is NOT: protection interpretation. No
#   unbalance limits, negative-sequence relay operation claims,
#   ground-fault analysis, fault classification, sequence-network
#   diagrams, or sequence impedance exist anywhere in this module,
#   `sequence_components_analysis_service`, or the frontend Sequence
#   Components panel. A future analyzer (unbalance assessment,
#   negative-sequence protection, ground-fault analysis, system
#   disturbance studies) may consume V0/V1/V2/I0/I1/I2 as its own INPUT,
#   built on top of this module, never coupled into it here.
# ---------------------------------------------------------------------------
