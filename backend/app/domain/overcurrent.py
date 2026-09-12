"""Overcurrent Analysis v1 -- IEC IDMT characteristic engine (see
docs/project-memory/OVERCURRENT_ANALYSIS.md).

**Product definition**: Powerwave evaluates a recorded event's own
one-cycle trailing RMS current, at a selected/Playback-driven instant,
against a CONFIGURED IEC IDMT (Inverse Definite Minimum Time) protection
characteristic. This is recorded-event analysis against a configured
characteristic -- it is explicitly NOT a claim to reproduce a physical
relay's own internal filters, timing accumulator, reset algorithm,
manufacturer tolerances, or proprietary logic. Powerwave never reports
"relay operated"/"relay tripped"/"relay should have tripped" -- only
"expected operating time" (a characteristic-derived, present-instant
figure) and "above-pickup duration" (an event-recording-derived
measurement), kept explicitly separate (see module footer).

Pure, framework-free, numpy-only -- zero registry/I/O access, mirroring
`app.domain.phasor`'s own layering (itself mirroring `app.domain.
calculated_channel.evaluate_rms()`). `app.services.overcurrent_
analysis_service` is the only caller, and owns everything this module
does not: input resolution, sample-array retrieval, reference-frequency
selection/agreement, and waveform-form eligibility (mirroring how
`phasor_analysis_service.py` owns those same concerns for Phasor).

## Standard/formulation

IEC 60255-151:2009 ("Measuring relays and protection equipment -- Part
151: Functional requirements for over/under current protection"), the
current edition of the dependent-time (IDMT) overcurrent characteristic
originally published as IEC 60255-3:1989 / equivalent to the older BS
142 curve definitions. The general dependent-time form:

    t = TMS * (k / ((I / Is)^alpha - 1) + c)

where `t` is the operating time (s), `TMS` the Time Multiplier Setting,
`I` the measured current, `Is` the pickup/current setting, and `k`/
`alpha`/`c` the curve-defining constants (`k`/`c` in seconds, `alpha`
dimensionless). For the three IEC IDMT curves this slice supports, `c =
0`. Constants (cross-verified against multiple independent secondary
sources describing the IEC 60255 curve table -- e.g. ABB and Siemens
relay technical manuals, and IDMT calculator references -- since the
primary IEC standard text itself is not freely reproducible here; see
this project's own final implementation report for the exact sources
consulted):

    Standard Inverse   (SI): k=0.14,  alpha=0.02
    Very Inverse       (VI): k=13.5,  alpha=1.0
    Extremely Inverse  (EI): k=80.0,  alpha=2.0

(IEC 60255-151 Annex A also defines Long Time Inverse, k=120, alpha=1.0,
and ANSI/IEEE C37.112 curves with their own constants -- both explicitly
OUT of this v1's scope; see "Not yet implemented" at the end of this
module.)

## Below-pickup semantics

`M = I / Is <= 1` has no finite theoretical operating time (the
characteristic's own denominator `M^alpha - 1` is non-positive) --
`evaluate_idmt_operating_time()` returns `None`, never `inf`/`NaN`/`0`.

## Extensibility

`OvercurrentCharacteristicDefinition` is a small, explicit, closed
registry (owner instruction: "a simple explicit registry/definition
model is sufficient... do not overengineer a plugin framework") -- each
entry names its own `family` (`"iec_idmt"` today) and constants; adding
a future characteristic is adding one more module-level constant here,
mirroring `app.domain.analysis_requirements`'s own registry precedent.
`evaluate_idmt_operating_time()` itself is specific to the IEC IDMT
formula shape above -- a future non-IEC-shaped family (e.g. definite
time, or a different dependent-time formulation) would need its own
evaluation function alongside a `family` discriminator, not a forced fit
into this one; that is an intentional, documented boundary, not an
oversight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.domain.calculated_channel import evaluate_rms as evaluate_rms_array

#: Bump ONLY when the estimation algorithm/interpretation itself changes
#: -- never for an unrelated refactor. Included, unconditionally, in
#: every computed result.
ALGORITHM_VERSION = "overcurrent_idmt_v1"

# ---------------------------------------------------------------------------
# Characteristic registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdmtConstants:
    """`k`/`c` in seconds, `alpha` dimensionless -- see module docstring
    for the formula these parameterize."""

    k: float
    alpha: float
    c: float = 0.0


@dataclass(frozen=True, slots=True)
class OvercurrentCharacteristicDefinition:
    id: str
    family: str
    display_name: str
    constants: IdmtConstants
    source: str


CHARACTERISTIC_IEC_STANDARD_INVERSE = "iec_standard_inverse"
CHARACTERISTIC_IEC_VERY_INVERSE = "iec_very_inverse"
CHARACTERISTIC_IEC_EXTREMELY_INVERSE = "iec_extremely_inverse"

_IEC_SOURCE = (
    "IEC 60255-151:2009 dependent-time (IDMT) overcurrent characteristic "
    "(successor to IEC 60255-3:1989 / BS 142); constants cross-verified "
    "against multiple independent secondary sources -- see this "
    "project's own implementation report."
)

IEC_STANDARD_INVERSE = OvercurrentCharacteristicDefinition(
    id=CHARACTERISTIC_IEC_STANDARD_INVERSE, family="iec_idmt", display_name="IEC Standard Inverse",
    constants=IdmtConstants(k=0.14, alpha=0.02, c=0.0), source=_IEC_SOURCE,
)
IEC_VERY_INVERSE = OvercurrentCharacteristicDefinition(
    id=CHARACTERISTIC_IEC_VERY_INVERSE, family="iec_idmt", display_name="IEC Very Inverse",
    constants=IdmtConstants(k=13.5, alpha=1.0, c=0.0), source=_IEC_SOURCE,
)
IEC_EXTREMELY_INVERSE = OvercurrentCharacteristicDefinition(
    id=CHARACTERISTIC_IEC_EXTREMELY_INVERSE, family="iec_idmt", display_name="IEC Extremely Inverse",
    constants=IdmtConstants(k=80.0, alpha=2.0, c=0.0), source=_IEC_SOURCE,
)

_KNOWN_CHARACTERISTICS: tuple[OvercurrentCharacteristicDefinition, ...] = (
    IEC_STANDARD_INVERSE, IEC_VERY_INVERSE, IEC_EXTREMELY_INVERSE,
)
_CHARACTERISTICS_BY_ID: dict[str, OvercurrentCharacteristicDefinition] = {c.id: c for c in _KNOWN_CHARACTERISTICS}


def get_characteristic(characteristic_id: str) -> OvercurrentCharacteristicDefinition | None:
    """Returns the matching characteristic, or `None` if unrecognized.
    Never raises -- the caller (service layer) decides how to translate
    an unrecognized id into a request error, mirroring `app.domain.
    analysis_requirements.get_requirement()`'s own precedent."""
    return _CHARACTERISTICS_BY_ID.get(characteristic_id)


def known_characteristics() -> tuple[OvercurrentCharacteristicDefinition, ...]:
    return _KNOWN_CHARACTERISTICS


# ---------------------------------------------------------------------------
# IDMT evaluation
# ---------------------------------------------------------------------------


def evaluate_idmt_operating_time(constants: IdmtConstants, tms: float, multiple_of_pickup: float) -> float | None:
    """`t = TMS * (k / (M^alpha - 1) + c)`. Returns `None` (never `inf`/
    `NaN`/`0`) for `M <= 1` -- there is no finite theoretical operating
    time at or below pickup (owner instruction: never fabricate one)."""
    if not math.isfinite(multiple_of_pickup) or multiple_of_pickup <= 1.0:
        return None
    denominator = multiple_of_pickup ** constants.alpha - 1.0
    if denominator <= 0.0:
        return None  # defensive; unreachable for alpha > 0 given the M <= 1 guard above.
    return tms * (constants.k / denominator + constants.c)


def generate_idmt_curve_points(
    constants: IdmtConstants, tms: float, *, m_min: float = 1.01, m_max: float = 20.0, num_points: int = 60,
) -> list[tuple[float, float]]:
    """The characteristic curve itself -- log-spaced multiples of pickup
    from just above 1 (M=1 has no finite time) to `m_max`, each paired
    with its own operating time. Depends only on `constants`/`tms` --
    the caller (frontend) recomputes this ONLY when the characteristic
    or TMS setting changes, never on every Playback tick (owner
    instruction: "avoid shipping thousands of redundant curve points on
    every Playback tick... only update the dynamic operating point where
    practical")."""
    m_values = np.geomspace(m_min, m_max, num=num_points)
    points: list[tuple[float, float]] = []
    for m in m_values:
        t = evaluate_idmt_operating_time(constants, tms, float(m))
        if t is not None:
            points.append((float(m), t))
    return points


# ---------------------------------------------------------------------------
# Selected-time trailing RMS estimator -- mirrors `app.domain.phasor.
# estimate_phasor()`'s own window/guardrail SHAPE (never its own private
# code): identical half-open trailing window `(analysis_time - window,
# analysis_time]`, `window = 1/reference_frequency_hz`, the same boundary-
# epsilon/regular-spacing/minimum-density guardrails -- but computes
# `sqrt(mean(x^2))` (true RMS) instead of a phasor correlation, since
# Overcurrent needs a scalar CURRENT MAGNITUDE at one selected instant,
# never a magnitude+angle. `app.domain.calculated_channel.evaluate_rms()`
# was inspected first (see this module's own implementation report) and
# confirmed to already use the IDENTICAL window definition -- but its own
# interface is a whole-array SLIDING-window evaluator (one output per
# INPUT sample), not a selected-single-time evaluator for an arbitrary
# continuous Playback-driven `analysis_time` that generally falls BETWEEN
# samples -- exactly the gap `estimate_phasor()` already solved for
# Phasor, so this function reuses ITS interface shape instead.
# ---------------------------------------------------------------------------

#: Minimum samples actually present within the selected one-cycle window
#: for the RMS estimate to be trusted -- reuses `app.domain.
#: calculated_channel.MIN_SAMPLES_PER_CYCLE`'s own value (4), NOT
#: Phasor's stricter `PHASOR_MIN_SAMPLES_PER_CYCLE` (8) -- this is a
#: plain RMS magnitude at one instant, the same accuracy shape
#: `evaluate_rms()` itself already accepts, never a phasor correlation
#: (which needed the stricter bound for angle accuracy).
OVERCURRENT_MIN_SAMPLES_PER_CYCLE = 4

#: Same value, same purpose, as `app.domain.phasor._BOUNDARY_EPS` --
#: re-declared here rather than imported, matching this codebase's
#: established "each module owns its own tiny boundary-tolerance
#: constant" convention.
_BOUNDARY_EPS = 1e-9
_SPACING_RTOL = 1e-6
_SPACING_ATOL = 1e-12

REASON_NO_SAMPLES = "no_samples"
REASON_ANALYSIS_TIME_OUT_OF_RANGE = "analysis_time_out_of_range"
REASON_INSUFFICIENT_WINDOW_HISTORY = "insufficient_window_history"
REASON_INVALID_SAMPLES_IN_WINDOW = "invalid_samples_in_window"
REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED = "irregular_sampling_not_supported"
REASON_INSUFFICIENT_SAMPLING_DENSITY = "insufficient_sampling_density"


@dataclass(frozen=True, slots=True)
class RmsEstimate:
    available: bool
    value: float | None = None
    reason_code: str | None = None
    sample_count: int = 0


def estimate_trailing_rms_at_time(
    time: np.ndarray, values: np.ndarray, analysis_time: float, reference_frequency_hz: float,
    *, min_samples_per_cycle: int = OVERCURRENT_MIN_SAMPLES_PER_CYCLE,
) -> RmsEstimate:
    """The one selected-time RMS estimator entry point -- `time`/`values`
    are one channel's own full-resolution sample arrays (monotonic
    non-decreasing `time`). Returns `available=False` with an explicit
    `reason_code` -- never a partial/shortened/shifted window, never a
    silently-dropped invalid sample, never a resampled substitute -- for
    every guardrail this module is responsible for (mirrors `estimate_
    phasor()`'s own guardrail set exactly)."""
    if time.shape[0] == 0:
        return RmsEstimate(available=False, reason_code=REASON_NO_SAMPLES, sample_count=0)

    if analysis_time > time[-1] + _BOUNDARY_EPS or analysis_time < time[0] - _BOUNDARY_EPS:
        return RmsEstimate(available=False, reason_code=REASON_ANALYSIS_TIME_OUT_OF_RANGE, sample_count=0)

    window_seconds = 1.0 / reference_frequency_hz
    if (analysis_time - time[0]) < (window_seconds - _BOUNDARY_EPS):
        return RmsEstimate(available=False, reason_code=REASON_INSUFFICIENT_WINDOW_HISTORY, sample_count=0)

    window_start = analysis_time - window_seconds
    mask = (time > window_start + _BOUNDARY_EPS) & (time <= analysis_time + _BOUNDARY_EPS)
    t_window = time[mask]
    x_window = values[mask]
    n = t_window.shape[0]

    if n < 2:
        return RmsEstimate(available=False, reason_code=REASON_INSUFFICIENT_WINDOW_HISTORY, sample_count=n)

    if not np.all(np.isfinite(x_window)):
        return RmsEstimate(available=False, reason_code=REASON_INVALID_SAMPLES_IN_WINDOW, sample_count=n)

    diffs = np.diff(t_window)
    if not np.allclose(diffs, np.median(diffs), rtol=_SPACING_RTOL, atol=_SPACING_ATOL):
        return RmsEstimate(available=False, reason_code=REASON_IRREGULAR_SAMPLING_NOT_SUPPORTED, sample_count=n)

    if n < min_samples_per_cycle:
        return RmsEstimate(available=False, reason_code=REASON_INSUFFICIENT_SAMPLING_DENSITY, sample_count=n)

    rms_value = float(np.sqrt(np.mean(x_window.astype(np.float64) ** 2)))
    return RmsEstimate(available=True, value=rms_value, sample_count=n)


# ---------------------------------------------------------------------------
# Continuous above-pickup duration -- a MEASUREMENT from the recording,
# deliberately separate from the characteristic-derived expected operating
# time above (owner instruction: keep these two concepts explicitly
# distinct; see module footer). Reuses `evaluate_rms()`'s own ARRAY form
# directly (not the selected-time estimator above) -- this sub-problem
# genuinely needs the RMS value at EVERY sample up to `analysis_time` to
# find where the current last crossed below pickup, exactly the shape
# `evaluate_rms()` already provides; the selected-time estimator above
# answers a different question ("the RMS AT this one instant").
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AbovePickupDuration:
    available: bool
    duration_seconds: float | None = None
    reason_code: str | None = None


def continuous_duration_above_pickup(
    time: np.ndarray, relay_secondary_values: np.ndarray, analysis_time: float,
    reference_frequency_hz: float, pickup_current_secondary: float,
) -> AbovePickupDuration:
    """How long the analyzed (already relay-secondary-converted) current
    has continuously remained above `pickup_current_secondary`
    immediately up to `analysis_time` -- a pure function of `analysis_
    time` and the full recorded array, so it is DETERMINISTIC for any
    seek (never path-dependent on "how long Play has been pressed", never
    affected by Playback speed -- owner's own explicit requirement).
    Resets to `0.0` the instant the current is at or below pickup.

    Cannot claim a duration further back than there is trailing-RMS data
    for (the recording's own first `1/reference_frequency_hz` seconds
    have no complete window) -- in that edge case, the earliest sample
    with a valid RMS value is treated as the onset of an already-ongoing
    above-pickup episode, never silently extended further back than the
    data actually supports.
    """
    if time.shape[0] == 0:
        return AbovePickupDuration(available=False, reason_code=REASON_NO_SAMPLES)
    if analysis_time < time[0] - _BOUNDARY_EPS:
        return AbovePickupDuration(available=False, reason_code=REASON_ANALYSIS_TIME_OUT_OF_RANGE)

    mask = time <= analysis_time + _BOUNDARY_EPS
    t = time[mask]
    v = relay_secondary_values[mask]
    if t.shape[0] == 0:
        return AbovePickupDuration(available=False, reason_code=REASON_NO_SAMPLES)

    rms_array = evaluate_rms_array(t, v, reference_frequency_hz)
    last_idx = t.shape[0] - 1
    current_rms = rms_array[last_idx]
    if not np.isfinite(current_rms) or current_rms <= pickup_current_secondary:
        return AbovePickupDuration(available=True, duration_seconds=0.0)

    onset_idx = last_idx
    while onset_idx > 0:
        prev_rms = rms_array[onset_idx - 1]
        if not np.isfinite(prev_rms) or prev_rms <= pickup_current_secondary:
            break
        onset_idx -= 1

    onset_time = float(t[onset_idx])
    duration = float(analysis_time) - onset_time
    return AbovePickupDuration(available=True, duration_seconds=max(0.0, duration))


# ---------------------------------------------------------------------------
# CT conversion / settings validation
# ---------------------------------------------------------------------------

RECORDING_BASIS_PRIMARY = "primary"
RECORDING_BASIS_SECONDARY = "secondary"
KNOWN_RECORDING_BASES = (RECORDING_BASIS_PRIMARY, RECORDING_BASIS_SECONDARY)

#: A typical/practical Time Multiplier Setting range commonly cited
#: across IDMT relay manufacturer documentation -- an APPLICATION
#: guardrail, never claimed as an IEC 60255-151-mandated numeric bound
#: (mirroring how `app.domain.phasor.PHASOR_MIN_SAMPLES_PER_CYCLE` is
#: honestly framed as an application guardrail, not a claimed industry
#: standard). See this module's own implementation report for the
#: sources cross-checked.
MIN_TMS = 0.025
MAX_TMS = 1.2


def tms_valid(tms: float) -> bool:
    return math.isfinite(tms) and MIN_TMS <= tms <= MAX_TMS


def pickup_valid(pickup_current_secondary: float) -> bool:
    return math.isfinite(pickup_current_secondary) and pickup_current_secondary > 0.0


def ct_values_valid(ct_primary: float, ct_secondary: float) -> bool:
    return (
        math.isfinite(ct_primary) and math.isfinite(ct_secondary)
        and ct_primary > 0.0 and ct_secondary > 0.0
    )


def convert_to_relay_secondary(
    recorded_current: float, *, recording_basis: str, ct_primary: float | None, ct_secondary: float | None,
) -> float:
    """`recording_basis="secondary"` -- no conversion needed, the
    recording already IS what the relay would see. `recording_basis=
    "primary"` -- `relay_secondary = recorded_primary * (ct_secondary /
    ct_primary)`. `ct_primary`/`ct_secondary` must already be expressed
    in the SAME base unit as the resolved current channel's own declared
    `unit` (mirrors how Phasor never separately re-units a channel's own
    magnitude_rms -- see this module's own implementation report for why
    no additional kA/A normalization happens here). Caller (service
    layer) is responsible for having already validated `ct_primary`/
    `ct_secondary` via `ct_values_valid()` before calling this for the
    primary case."""
    if recording_basis == RECORDING_BASIS_SECONDARY:
        return recorded_current
    assert ct_primary is not None and ct_secondary is not None
    return recorded_current * (ct_secondary / ct_primary)


# ---------------------------------------------------------------------------
# Whole-analysis result -- a concrete, Overcurrent-owned shape (never
# persisted, never a generic cross-analysis framework), mirroring `app.
# domain.phasor.PhasorAnalysisResult`'s own precedent.
# ---------------------------------------------------------------------------

OVERCURRENT_STATUS_COMPUTED = "computed"

REASON_UNKNOWN_CHARACTERISTIC = "unknown_characteristic"
REASON_INVALID_TMS = "invalid_tms"
REASON_INVALID_PICKUP = "invalid_pickup"
REASON_INVALID_CT_VALUES = "invalid_ct_values"
REASON_INVALID_REFERENCE_FREQUENCY = "invalid_reference_frequency"
REASON_WAVEFORM_FORM_NOT_ELIGIBLE = "waveform_form_not_eligible"
REASON_CHANNEL_UNAVAILABLE = "channel_unavailable"


@dataclass(slots=True)
class OvercurrentAnalysisResult:
    """The reusable whole-analysis result. Never persisted -- always
    derived fresh from current context/channel state and the supplied
    settings, exactly like `PhasorAnalysisResult`.

    `measured_rms_current`/`measured_rms_current_unit` are in the
    resolved channel's own RECORDED basis/unit (never silently
    converted) -- `relay_secondary_current` is always in relay-secondary
    amperes (identical numeric value to `measured_rms_current` when
    `recording_basis="secondary"`, so the caller never misleadingly
    implies a CT conversion occurred that didn't). `expected_operating_
    time_seconds` is `None` whenever `multiple_of_pickup <= 1` (below
    pickup -- see module docstring for why this is never a fabricated
    number). `threshold_exceeded` is a QUALIFIED characteristic-analysis
    observation only -- never a relay-operation claim (see module
    footer)."""

    status: str
    engineering_context_id: str
    phase: str
    analysis_time: float
    characteristic_id: str | None = None
    tms: float | None = None
    pickup_current_secondary: float | None = None
    recording_basis: str | None = None
    ct_primary: float | None = None
    ct_secondary: float | None = None
    reference_frequency_hz: float | None = None
    window_seconds: float | None = None
    algorithm_version: str = ALGORITHM_VERSION
    channel_ref: ChannelRef | None = None
    measured_rms_current: float | None = None
    measured_rms_current_unit: str | None = None
    relay_secondary_current: float | None = None
    multiple_of_pickup: float | None = None
    expected_operating_time_seconds: float | None = None
    above_pickup_duration_seconds: float | None = None
    threshold_exceeded: bool = False
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Explicit non-emulation boundary (owner instruction -- restated here,
# not just in the module docstring, since this is the single most
# important interpretive boundary of the whole feature):
#
#   "Expected operating time"     -- CHARACTERISTIC-derived, computed at
#                                     the PRESENT measured RMS current
#                                     only. Never accumulates/integrates
#                                     across a variable-current history.
#   "Above-pickup duration"       -- EVENT-RECORDING-derived, a plain
#                                     measurement of how long the
#                                     recorded current has continuously
#                                     stayed above pickup.
#   threshold_exceeded            -- a QUALIFIED comparison of those two
#                                     numbers at the PRESENT operating
#                                     point only. It is NOT: "the relay
#                                     operated", "the relay should have
#                                     operated", or "the relay failed to
#                                     operate" -- Powerwave does not know
#                                     a real relay's own internal
#                                     filters/timing accumulator/reset
#                                     algorithm/manufacturer tolerances/
#                                     proprietary logic, and does not
#                                     attempt to emulate them.
#
# Not yet implemented (future slices, explicitly out of this v1's scope):
# ANSI/IEEE curves, definite time, instantaneous/high-set stages,
# earth-fault elements, multiple relay coordination curves,
# manufacturer-specific curves, relay tolerance bands, reset
# characteristics, thermal memory, actual relay trip-state emulation,
# dynamic accumulation estimation under variable current, protection
# grading studies, and every other real protection analysis (Distance/
# Differential/Sequence Components).
# ---------------------------------------------------------------------------
