"""Selected-time Phasor estimator (Phasor Analysis Slice 1; see
docs/project-memory/PHASOR_ANALYSIS.md).

**Product definition**: a Powerwave phasor is an RMS fundamental-
frequency phasor estimated from a sampled Voltage or Current waveform
over one trailing cycle at a FIXED reference frequency. It is NOT an
instantaneous sample, NOT frequency-tracked, NOT PMU/synchrophasor-
class, and NOT a precomputed vendor magnitude/angle channel.

Pure, framework-free, numpy-only -- zero registry/I/O access, mirroring
`app.domain.calculated_channel.evaluate_rms()`'s own layering (the
closest existing precedent this module deliberately reuses the window/
guardrail SHAPE of, never its own private code). `app.services.
phasor_analysis_service` is the only caller, and owns everything this
module does not: input resolution, sample-array retrieval, reference-
frequency selection/agreement, and waveform-form eligibility (mirroring
`check_rms_eligibility()`'s own service-layer placement, never
duplicated here).

## Estimator (explicit complex single-frequency projection)

For samples `x_n` at times `t_n` (seconds, on ONE common, source-
independent absolute-time-derived coordinate -- see below), within the
selected window:

    X = (sqrt(2) / N) * sum_n( x_n * exp(-j * 2*pi*f0*t_n) )

    magnitude_rms = abs(X)
    angle_rad     = arg(X)

**Proof of the RMS normalization** (never left implicit, per the
product definition above): for a sampled sinusoid `x(t) = A*cos(2*pi*f0*t
+ phi)` where `t_n` spans exactly one full period with samples that
integrate the fundamental exactly (the discrete-orthogonality property
of a pure single-frequency sinusoid sampled over an integer number of
its own periods), `sum_n(x_n * cos(2*pi*f0*t_n)) ~= (N/2)*A*cos(phi)`
and `sum_n(x_n * sin(2*pi*f0*t_n)) ~= -(N/2)*A*sin(phi)` (the DOUBLE-
frequency cross terms cancel over a full period; the fundamental-
frequency self terms integrate to one half their own amplitude -- the
standard Fourier-coefficient identity). Substituting:

    Re{X} = (sqrt(2)/N) * sum(x_n*cos(w*t_n)) ~= (sqrt(2)/N)*(N/2)*A*cos(phi) = (A/sqrt(2))*cos(phi)
    Im{X} = -(sqrt(2)/N) * sum(x_n*sin(w*t_n)) ~= (A/sqrt(2))*sin(phi)

so `X ~= (A/sqrt(2)) * exp(j*phi)` -- magnitude is exactly `A/sqrt(2)`,
the sinusoid's RMS value (never its peak amplitude), and the angle is
exactly `phi`, the sinusoid's own phase in `x(t) = A*cos(2*pi*f0*t +
phi)`. `angle = 0` therefore means "this waveform is at its positive
peak exactly at t=0 of the coordinate `t_n` is expressed in" -- see
"Angle reference" below for what that coordinate origin actually is.
Golden-vector tests (`backend/tests/test_phasor_domain.py`) prove this
numerically against independently hand-derived expected values, never
values re-derived from this same formula.

## Angle reference -- the common, source-independent coordinate

`t_n` must be expressed on ONE shared time coordinate across every
resolved role of one analysis, computed ONCE by the service (never
reset per-window) -- otherwise a sliding window would silently rotate
the reported angle merely because the window moved, and a three-phase
result's inter-phase angle differences would be meaningless whenever
roles come from different sources. This module never constructs that
coordinate itself (it has no source/registry access); it only ever
receives an already-common `time` array from the service. See
`app.services.phasor_analysis_service`'s own docstring for exactly how
that shared coordinate is derived (absolute epoch time, reduced by a
fixed per-request reference epoch purely to keep floating-point
precision high -- never changing which physical instant `angle=0`
means).

## Window

Exactly one trailing cycle at the reference frequency:
`window_seconds = 1 / reference_frequency_hz`, applied as the HALF-OPEN
interval `(analysis_time - window_seconds, analysis_time]` -- the exact
same boundary convention `evaluate_rms()` already established, and for
the identical reason: a CLOSED interval would double-count a sample
exactly one period before `analysis_time` (it shares the same
sinusoidal phase as the sample at `analysis_time` itself for a
perfectly periodic signal), biasing the correlation sum. Never
centered, never using future samples, never shortened/shifted near the
start of a recording -- see `estimate_phasor()`'s own guardrails below,
which return an explicit unavailable result instead.

## Fixed-frequency limitation (must never be hidden)

This estimator uses `reference_frequency_hz` directly -- it never
measures or tracks the actual instantaneous system frequency. If the
true signal frequency deviates from the reference value, both the
reported magnitude (understated) and angle (progressively drifting
across successive `analysis_time` calls) carry error proportional to
the deviation. This is NOT PMU/synchrophasor-class frequency-tracked
measurement, and must never be presented as one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_units import ENGINEERING_QUANTITY_VOLTAGE, convert_value_to_canonical

#: Bump ONLY when the estimation algorithm/interpretation itself
#: changes (e.g. a future frequency-tracked estimator) -- never for an
#: unrelated refactor. Included, unconditionally, in every result.
ALGORITHM_VERSION = "phasor_estimator_v1"

#: Minimum samples actually present within the selected one-cycle window
#: for the estimate to be trusted -- a Phasor-SPECIFIC threshold,
#: deliberately NOT copied from `calculated_channel.MIN_SAMPLES_PER_CYCLE`
#: (that constant was tuned for a *sliding* one-cycle RMS's own accuracy
#: needs, never validated against phasor MAGNITUDE and ANGLE error at a
#: single, generally window-misaligned, selected time). Chosen from
#: `backend/tests/test_phasor_domain.py::TestSamplingDensityStudy`'s own
#: empirical sweep across 4/8/16/32 samples/cycle -- see that test
#: module's own docstring for the measured error at each density and why
#: this specific value is the smallest one that keeps every golden
#: scenario (RMS magnitude, 30 deg/90 deg phase shift, balanced
#: three-phase) within a tight, pre-declared tolerance. Not claimed as an
#: industry/protection-relay standard -- an application guardrail based
#: on this estimator's own measured accuracy, nothing more.
PHASOR_MIN_SAMPLES_PER_CYCLE = 8

#: Absorbs ordinary floating-point representation noise at a window
#: boundary -- same value, same purpose, as
#: `calculated_channel._BOUNDARY_EPS` (re-declared here rather than
#: imported: this module has no other dependency on that module's own
#: private internals, matching this codebase's established "each module
#: owns its own tiny boundary-tolerance constant" convention).
_BOUNDARY_EPS = 1e-9

#: Sample-spacing regularity check -- identical tolerance to
#: `evaluate_rms()`'s own `np.allclose(diffs, median(diffs), ...)`
#: uniform-spacing test, reused verbatim rather than inventing a second
#: regularity threshold.
_SPACING_RTOL = 1e-6
_SPACING_ATOL = 1e-12

#: `PhasorEstimate.reason_code` values -- always populated together with
#: `available=False`, never alongside a numeric result.
REASON_NO_SAMPLES = "no_samples"
REASON_ANALYSIS_TIME_OUT_OF_RANGE = "analysis_time_out_of_range"
REASON_INSUFFICIENT_WINDOW_HISTORY = "insufficient_window_history"
REASON_INVALID_SAMPLES_IN_WINDOW = "invalid_samples_in_window"
REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED = "irregular_sampling_not_supported"
REASON_INSUFFICIENT_SAMPLING_DENSITY = "insufficient_sampling_density"


@dataclass(frozen=True, slots=True)
class PhasorEstimate:
    """One channel's own selected-time phasor result. `angle_deg` is
    ABSOLUTE -- referenced to `t=0` of whatever common time coordinate
    the caller's own `time` array is expressed in (see module docstring)
    -- normalized to `(-180, 180]`. Relative (Phase-A-referenced) angle
    is a service-layer, DISPLAY-level derivation from this absolute
    value, never computed here (mirrors how Per-Unit is a display
    transform layered on top of an authoritative engineering value,
    never baked into the raw computation)."""

    available: bool
    magnitude_rms: float | None = None
    angle_deg: float | None = None
    reason_code: str | None = None
    sample_count: int = 0


def _normalize_angle_deg(angle_deg: float) -> float:
    """Normalizes to `(-180, 180]` -- e.g. `180.0 -> 180.0`,
    `180.0001 -> -179.9999`, `-180.0 -> 180.0`, `0.0 -> 0.0`."""
    normalized = float(angle_deg) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _phasor_from_window(t_window: np.ndarray, x_window: np.ndarray, reference_frequency_hz: float) -> tuple[float, float]:
    """The estimator formula itself -- see module docstring for the full
    derivation/proof. Returns `(magnitude_rms, angle_rad)`."""
    n = t_window.shape[0]
    angle = 2.0 * np.pi * reference_frequency_hz * t_window
    cos_component = float(np.sum(x_window * np.cos(angle)))
    sin_component = float(np.sum(x_window * np.sin(angle)))
    scale = np.sqrt(2.0) / n
    real = scale * cos_component
    imag = -scale * sin_component
    magnitude_rms = float(np.hypot(real, imag))
    angle_rad = float(np.arctan2(imag, real))
    return magnitude_rms, angle_rad


def estimate_phasor(
    time: np.ndarray,
    values: np.ndarray,
    analysis_time: float,
    reference_frequency_hz: float,
    *,
    min_samples_per_cycle: int = PHASOR_MIN_SAMPLES_PER_CYCLE,
) -> PhasorEstimate:
    """The one estimator entry point. `time`/`values` are one channel's
    own full-resolution sample arrays (monotonic non-decreasing `time`,
    the same invariant every other reader of `waveform_data["time"]"`
    already relies on), `time` already expressed on the shared,
    source-independent coordinate the caller established (see module
    docstring). `analysis_time`/`reference_frequency_hz` are already
    validated by the caller (reference-frequency plausibility is a
    service-layer concern, mirroring `evaluate_rms()`'s own division of
    responsibility with `nominal_frequency_valid()`).

    Returns `available=False` with an explicit `reason_code` -- never a
    partial/shortened/shifted window, never a silently-dropped invalid
    sample, never a resampled/interpolated substitute -- for every
    guardrail this module is responsible for: insufficient window
    history (recording-start edge case, or `analysis_time` outside the
    recorded span entirely), a non-finite sample anywhere in the exact
    window, irregular (non-uniform) sample spacing within the window,
    or too few samples for the reference frequency's own one-cycle
    window to be trustworthy (`PHASOR_MIN_SAMPLES_PER_CYCLE`).
    """
    if time.shape[0] == 0:
        return PhasorEstimate(available=False, reason_code=REASON_NO_SAMPLES, sample_count=0)

    if analysis_time > time[-1] + _BOUNDARY_EPS or analysis_time < time[0] - _BOUNDARY_EPS:
        return PhasorEstimate(available=False, reason_code=REASON_ANALYSIS_TIME_OUT_OF_RANGE, sample_count=0)

    window_seconds = 1.0 / reference_frequency_hz
    if (analysis_time - time[0]) < (window_seconds - _BOUNDARY_EPS):
        return PhasorEstimate(available=False, reason_code=REASON_INSUFFICIENT_WINDOW_HISTORY, sample_count=0)

    window_start = analysis_time - window_seconds
    mask = (time > window_start + _BOUNDARY_EPS) & (time <= analysis_time + _BOUNDARY_EPS)
    t_window = time[mask]
    x_window = values[mask]
    n = t_window.shape[0]

    if n < 2:
        return PhasorEstimate(available=False, reason_code=REASON_INSUFFICIENT_WINDOW_HISTORY, sample_count=n)

    if not np.all(np.isfinite(x_window)):
        return PhasorEstimate(available=False, reason_code=REASON_INVALID_SAMPLES_IN_WINDOW, sample_count=n)

    diffs = np.diff(t_window)
    if not np.allclose(diffs, np.median(diffs), rtol=_SPACING_RTOL, atol=_SPACING_ATOL):
        return PhasorEstimate(available=False, reason_code=REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED, sample_count=n)

    if n < min_samples_per_cycle:
        return PhasorEstimate(available=False, reason_code=REASON_INSUFFICIENT_SAMPLING_DENSITY, sample_count=n)

    magnitude_rms, angle_rad = _phasor_from_window(t_window, x_window, reference_frequency_hz)
    angle_deg = _normalize_angle_deg(np.degrees(angle_rad))
    return PhasorEstimate(available=True, magnitude_rms=magnitude_rms, angle_deg=angle_deg, sample_count=n)


def relative_angle_deg(angle_deg: float, reference_angle_deg: float) -> float:
    """The Phase-A-referenced (or Current-Phase-A-referenced) DISPLAY
    angle: `angle_deg - reference_angle_deg`, normalized to `(-180,
    180]`. A pure, tiny helper -- kept here (not duplicated per-service-
    call-site) since both the three-phase Voltage and three-phase
    Current requirements need the identical derivation."""
    return _normalize_angle_deg(angle_deg - reference_angle_deg)


# ---------------------------------------------------------------------------
# Whole-analysis result -- a concrete, Phasor-owned shape (never persisted,
# never a generic cross-analysis framework; see
# app.services.phasor_analysis_service's own docstring for assembly).
# Lives here, alongside PhasorEstimate, mirroring
# app.domain.analysis_input_resolution's own precedent of keeping its
# result dataclass in the domain module the service populates.
# ---------------------------------------------------------------------------

#: A fully computed result -- every required role has an available
#: PhasorEstimate. The three OTHER possible `status` values
#: (`resolved`/`needs_configuration`/`ambiguous`/`not_applicable` minus
#: `resolved` itself, which always becomes either `computed` or
#: `needs_configuration` here) are never independently invented --
#: `needs_configuration`/`ambiguous`/`not_applicable` are always either a
#: verbatim pass-through of `app.domain.analysis_input_resolution`'s own
#: resolver status (the resolver itself did not reach `resolved`), or
#: (for `needs_configuration` only) a Phasor-specific guardrail failure
#: (reference-frequency conflict, waveform-form rejection, or an
#: unavailable estimation window) on an otherwise-resolved input set.
PHASOR_STATUS_COMPUTED = "computed"

REASON_REFERENCE_FREQUENCY_CONFLICT = "reference_frequency_conflict"
REASON_INVALID_REFERENCE_FREQUENCY = "invalid_reference_frequency"
REASON_WAVEFORM_FORM_NOT_ELIGIBLE = "waveform_form_not_eligible"


@dataclass(frozen=True, slots=True)
class PhasorRoleResult:
    channel_ref: ChannelRef
    magnitude_rms: float
    unit: str
    angle_deg_absolute: float
    angle_deg_relative: float | None


@dataclass(slots=True)
class PhasorAnalysisResult:
    """The reusable whole-analysis result. Never persisted -- always
    derived fresh from current context/channel state, exactly like
    `app.domain.analysis_input_resolution.AnalysisInputResolution`."""

    status: str
    analysis_kind: str
    mode: str
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None = None
    window_seconds: float | None = None
    algorithm_version: str = ALGORITHM_VERSION
    roles: dict[str, PhasorRoleResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    #: Per-role diagnostic detail for a `needs_configuration` result --
    #: role_key -> reason code. Only populated for roles that failed
    #: (mirrors `AnalysisInputResolution.missing_role_reasons`'s own
    #: precedent for precise, role-level diagnostics rather than one
    #: flat top-level reason when multiple roles are involved).
    role_reasons: dict[str, str] = field(default_factory=dict)
    reason_code: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Phasor Diagram result -- bay-centric aggregation (Phasor UAT redesign; see
# docs/project-memory/PHASOR_ANALYSIS.md's own "Bay-centric Phasor Diagram"
# section). Resolves ALL SIX supported single-phase roles (Va/Vb/Vc/Ia/Ib/Ic)
# for one Engineering Context independently -- never an all-or-nothing
# three-phase requirement -- so a partial bay (e.g. only Va+Ia) is exactly
# as valid a result as a complete one. Still a concrete, Phasor-owned
# shape, never a generic cross-analysis framework; still never persisted.
# ---------------------------------------------------------------------------

#: Per-ROLE status (distinct from `PhasorDiagramResult.status`, the WHOLE-
#: RESULT status below). One role's own missing/ambiguous/ineligible state
#: never blocks any OTHER role -- see `app.services.phasor_analysis_
#: service.compute_phasor_diagram()`'s own docstring for exactly which
#: conditions map to which of these five.
ROLE_STATUS_AVAILABLE = "available"
ROLE_STATUS_MISSING = "missing"
ROLE_STATUS_NEEDS_CONFIGURATION = "needs_configuration"
ROLE_STATUS_AMBIGUOUS = "ambiguous"
ROLE_STATUS_NOT_ELIGIBLE = "not_eligible"
KNOWN_ROLE_STATUSES = (
    ROLE_STATUS_AVAILABLE, ROLE_STATUS_MISSING, ROLE_STATUS_NEEDS_CONFIGURATION,
    ROLE_STATUS_AMBIGUOUS, ROLE_STATUS_NOT_ELIGIBLE,
)

#: The fixed Va/Vb/Vc/Ia/Ib/Ic role-key order every diagram result and its
#: own anchor-role selection uses -- Voltage before Current, A before B
#: before C within each family, matching the order the owner's own worked
#: examples use throughout.
PHASOR_DIAGRAM_ROLE_ORDER = ("Va", "Vb", "Vc", "Ia", "Ib", "Ic")
PHASOR_DIAGRAM_VOLTAGE_REFERENCE_ROLE = "Va"
PHASOR_DIAGRAM_CURRENT_REFERENCE_ROLE = "Ia"


@dataclass(frozen=True, slots=True)
class PhasorDiagramRoleResult:
    """One role's own result within the aggregated diagram. `channel_ref`
    is populated whenever role IDENTITY is known (`available` and
    `needs_configuration` both set it; `missing`/`ambiguous` never do,
    `not_eligible` always does since ineligibility can only be determined
    for a channel that was actually found). `angle_deg_absolute` is the
    ONLY angle ever used for shared-diagram vector GEOMETRY (owner's own
    explicit "must not destroy the true V-I angular relationship"
    requirement) -- `angle_deg_relative` (this role's own family
    reference role subtracted, `Va` for Voltage, `Ia` for Current) is
    secondary/table-only information, `None` whenever that family's own
    reference role is not itself `available`."""

    status: str
    channel_ref: ChannelRef | None = None
    magnitude_rms: float | None = None
    unit: str | None = None
    angle_deg_absolute: float | None = None
    angle_deg_relative: float | None = None
    reason_code: str | None = None


@dataclass(slots=True)
class PhasorDiagramResult:
    """The reusable, bay-centric, all-six-roles result. Never persisted --
    always derived fresh. `status` is deliberately only ever
    `PHASOR_STATUS_COMPUTED` or `STATUS_NEEDS_CONFIGURATION` (imported by
    the service from `app.domain.analysis_input_resolution`, reused
    rather than re-declared here) -- a MIXTURE of per-role outcomes
    (some available, some missing, some ambiguous) is still, at the
    WHOLE-RESULT level, `computed` (there is something useful to show);
    only a genuine cross-role blocking condition (reference-frequency
    conflict, timebase incompatibility, an invalid override, or no
    resolved source having a known absolute start time) ever produces
    `needs_configuration` at this level -- see the service's own
    docstring for the full precedence."""

    status: str
    engineering_context_id: str
    analysis_time: float
    reference_frequency_hz: float | None = None
    window_seconds: float | None = None
    algorithm_version: str = ALGORITHM_VERSION
    roles: dict[str, PhasorDiagramRoleResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode (Analysis Input Source = 'manual') --
# a standalone engineering-calculator path, fully decoupled from
# recordings/Engineering Context/Time Groups/Playback -- see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md's own governing invariant
# (DEC-095, extended to Phasor). Mirrors `app.domain.overcurrent`'s own
# Manual Input precedent, extended from Overcurrent's single current
# value/single basis to Phasor's six independent roles
# (Va/Vb/Vc/Ia/Ib/Ic) across TWO genuinely independent bases (Voltage,
# Current) -- see this module's own "canonical internal phasor
# representation" note on `convert_manual_magnitude_to_secondary()`
# below for why one shared conversion function serves both quantities.
# ---------------------------------------------------------------------------

#: Bumped only if Manual Phasor's own computation/interpretation itself
#: changes -- independent of `ALGORITHM_VERSION` above, since Manual
#: mode uses no estimator/window/reference-frequency concept at all (a
#: manually-entered magnitude+angle is not derived from any waveform).
MANUAL_ALGORITHM_VERSION = "phasor_manual_v1"

MANUAL_BASIS_PRIMARY = "primary"
MANUAL_BASIS_SECONDARY = "secondary"
KNOWN_MANUAL_BASES = (MANUAL_BASIS_PRIMARY, MANUAL_BASIS_SECONDARY)

REASON_INVALID_MANUAL_BASIS = "invalid_manual_basis"
REASON_INVALID_MANUAL_MAGNITUDE = "invalid_manual_magnitude"
REASON_UNSUPPORTED_MANUAL_UNIT = "unsupported_manual_unit"
REASON_INVALID_RATIO = "invalid_ratio"


def manual_basis_valid(basis: str) -> bool:
    return basis in KNOWN_MANUAL_BASES


def manual_magnitude_valid(magnitude: float) -> bool:
    """Manual Phasor's own guardrail for a directly-entered magnitude --
    `>= 0`, deliberately NOT `> 0` like Overcurrent's pickup/manual-
    current guardrails (a zero pickup or zero test current has no
    meaningful protection interpretation there) -- a genuinely
    zero-magnitude phasor (a de-energized phase, for instance) is a
    valid, if degenerate, Manual Phasor input here."""
    return math.isfinite(magnitude) and magnitude >= 0.0


def manual_ratio_valid(ratio_primary: float, ratio_secondary: float) -> bool:
    """VT/PT or CT ratio validity -- mirrors
    `app.domain.overcurrent.ct_values_valid()`'s own exact shape
    (finite, strictly positive). Defined independently here, never
    imported from Overcurrent's own analyzer-owned module, since Phasor
    needs the identical check for BOTH the Voltage (VT/PT) and Current
    (CT) ratio independently."""
    return (
        math.isfinite(ratio_primary) and math.isfinite(ratio_secondary)
        and ratio_primary > 0.0 and ratio_secondary > 0.0
    )


def convert_manual_magnitude_to_secondary(
    magnitude: float,
    *,
    unit: str,
    engineering_quantity: str,
    basis: str,
    ratio_primary: float | None,
    ratio_secondary: float | None,
) -> float | None:
    """Normalizes a manually-entered Voltage or Current magnitude to its
    Secondary-equivalent value, in the quantity's own canonical unit ('V'
    or 'A') -- Manual Phasor's chosen internal canonical basis (see
    docs/project-memory/ANALYSIS_INPUT_SOURCE.md's own "canonical
    internal phasor representation" section for why Secondary was
    chosen: it matches Overcurrent's own DEC-095 precedent, and Phasor's
    Recording-mode result carries no basis concept of its own to prefer
    one way or the other -- consistency across analyzers is the only
    real constraint here, not a Phasor-specific engineering reason).
    Mirrors `app.domain.overcurrent.convert_to_relay_secondary()`'s own
    two-step shape (engineering-unit normalization FIRST, then ratio
    scaling) but generalized over `engineering_quantity` so this ONE
    function serves both Voltage (VT/PT ratio) and Current (CT ratio) --
    Overcurrent never needed this generalization since it only ever
    deals with one quantity. Returns `None` (never a silently-wrong
    number) if `unit` cannot be normalized -- caller must treat that as
    a needs-configuration condition, never a silent fallback to treating
    the raw value as already canonical."""
    canonical = convert_value_to_canonical(magnitude, engineering_quantity, unit)
    if canonical is None:
        return None
    if basis == MANUAL_BASIS_SECONDARY:
        return canonical
    assert ratio_primary is not None and ratio_secondary is not None
    return canonical * (ratio_secondary / ratio_primary)


@dataclass(frozen=True, slots=True)
class ManualPhasorRoleInput:
    """One role's own raw manual input, before validation/conversion.
    `enabled=False` (or a `None` magnitude) means the engineer has not
    entered this role at all -- deliberately distinct from an
    entered-but-invalid value, which still has `enabled=True` (task's
    own "Va/Vb/Vc/Ia/Ib/Ic may be independently present" partial-input
    policy)."""

    enabled: bool
    magnitude: float | None = None
    unit: str = "A"
    angle_deg: float | None = None


@dataclass(frozen=True, slots=True)
class ManualPhasorDiagramResult:
    """Manual Input / Calculator mode's own result shape --
    deliberately has NO `engineering_context_id`/`analysis_time`/
    `reference_frequency_hz`/`window_seconds`, none of which exist for a
    standalone set of manually-entered phasors with no recording/time
    series (mirrors `app.domain.overcurrent.ManualOvercurrentAnalysisResult`'s
    own field-omission rationale). Reuses `PhasorDiagramRoleResult`
    VERBATIM for `roles` -- that dataclass carries no context-only
    required field, so it is genuinely shared, not duplicated, between
    the Recording-mode diagram and this Manual-mode one; the SAME
    frontend renderer consumes either result unmodified."""

    status: str
    algorithm_version: str = MANUAL_ALGORITHM_VERSION
    roles: dict[str, PhasorDiagramRoleResult] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


def evaluate_manual_phasor_role(
    role_input: ManualPhasorRoleInput,
    *,
    engineering_quantity: str,
    basis: str,
    ratio_primary: float | None,
    ratio_secondary: float | None,
) -> PhasorDiagramRoleResult:
    """One role's own fully independent evaluation -- an invalid or
    missing role NEVER blocks any other role (task's own "missing
    phasors do not block the whole diagram" / "invalid one-row input
    must not corrupt other valid phasors" requirement). An invalid
    Voltage basis or VT/PT ratio blocks every role in the VOLTAGE family
    only (never Current, and vice versa for CT) -- reuses the EXISTING
    `ROLE_STATUS_NEEDS_CONFIGURATION` role status for that family-level
    block, never a new whole-result-blocking concept; a role that is
    simply not entered reuses the EXISTING `ROLE_STATUS_MISSING` status
    the Recording-mode diagram already uses for the identical row-
    rendering treatment (no toggle, a plain status label) -- the shared
    frontend renderer needs zero new status vocabulary for Manual
    mode."""
    if not manual_basis_valid(basis):
        if not role_input.enabled or role_input.magnitude is None:
            return PhasorDiagramRoleResult(status=ROLE_STATUS_MISSING)
        return PhasorDiagramRoleResult(status=ROLE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_INVALID_MANUAL_BASIS)
    if not role_input.enabled or role_input.magnitude is None:
        return PhasorDiagramRoleResult(status=ROLE_STATUS_MISSING)
    if (
        not manual_magnitude_valid(role_input.magnitude)
        or role_input.angle_deg is None
        or not math.isfinite(role_input.angle_deg)
    ):
        return PhasorDiagramRoleResult(status=ROLE_STATUS_MISSING, reason_code=REASON_INVALID_MANUAL_MAGNITUDE)
    if basis == MANUAL_BASIS_PRIMARY:
        if ratio_primary is None or ratio_secondary is None or not manual_ratio_valid(ratio_primary, ratio_secondary):
            return PhasorDiagramRoleResult(status=ROLE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_INVALID_RATIO)
    magnitude_secondary = convert_manual_magnitude_to_secondary(
        role_input.magnitude, unit=role_input.unit, engineering_quantity=engineering_quantity,
        basis=basis, ratio_primary=ratio_primary, ratio_secondary=ratio_secondary,
    )
    if magnitude_secondary is None:
        return PhasorDiagramRoleResult(status=ROLE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_UNSUPPORTED_MANUAL_UNIT)
    canonical_unit = "V" if engineering_quantity == ENGINEERING_QUANTITY_VOLTAGE else "A"
    return PhasorDiagramRoleResult(
        status=ROLE_STATUS_AVAILABLE,
        magnitude_rms=magnitude_secondary,
        unit=canonical_unit,
        angle_deg_absolute=_normalize_angle_deg(role_input.angle_deg),
    )
