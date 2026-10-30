"""Complex power calculation domain module (DEC-PWR, Slice 0).

Provides the shared mathematical engine for MW / MVar / MVA power
calculations, serving both the Calculated Channels time-series path
(future Slice 3+) and the Calculator Page V-I Phasors tab (future
Slice 1). Pure, framework-free, stdlib-only (cmath + math + dataclasses
+ __future__) -- zero registry / I/O / NumPy access, mirroring
app.domain.sequence_components's own layering convention.

## Approved engineering decisions

### DEC-PWR-002 — Apparent power definition

Apparent power S is the GEOMETRIC magnitude of total fundamental complex
power:

    S = |S_total| = sqrt(P^2 + Q^2)

For three-phase:

    S_total = V_R * conj(I_R) + V_Y * conj(I_Y) + V_B * conj(I_B)
    P       = Re(S_total)
    Q       = Im(S_total)
    S       = |S_total| = sqrt(P^2 + Q^2)

This is the GEOMETRIC apparent power -- distinct from the IEEE 1459
arithmetic apparent power (S_A = |S_R| + |S_Y| + |S_B|, the sum of
per-phase apparent powers). S <= S_A by the triangle inequality; equality
holds only for perfectly balanced three-phase systems. Every result
carries an explicit `apparent_power_definition` field that names this
convention so consumers never need to infer which definition was used.

### DEC-PWR-003 — Sign convention

Passive sign convention throughout:

    S = V * conj(I) = P + jQ

Meanings under this convention:
  P > 0: element absorbs active power (load convention).
  P < 0: element supplies active power (generating / reverse flow).
  Q > 0: inductive load; current LAGS voltage (lagging power factor).
  Q < 0: capacitive load; current LEADS voltage (leading power factor).

Current reference direction: INTO the positive terminal of the element
(load / passive convention). Results are signed and never flipped
post-calculation. Every result carries an explicit `sign_convention`
field.

`power_factor_sign` ("lagging" / "leading" / "unity" / "undefined") is
derived solely from the sign of Q relative to S; it is independent of
the sign of P. Reverse active power (P < 0) with Q = 0 correctly
reports power_factor_sign = "unity" -- the sign of P is already visible
in `p_watts` and in the signed `power_factor` field (P / S).

`power_factor = P / S` -- a signed ratio in [-1, 1]; None when S = 0.
A negative power_factor indicates reverse active power flow; this is
intentionally preserved so callers are never forced to infer direction
from magnitude alone.

### DEC-PWR-005 — Eligible inputs (this slice)

Actual single-phase: one voltage phasor + one corresponding current
phasor (same terminal, same measurement point).

Actual three-phase: three voltage phasors + three corresponding current
phasors (one pair per phase: R, Y, B in that order). Each phase is the
SAME voltage / current measurement point for that phase; no cross-phase
V-I pairing.

DEFERRED: balanced three-phase estimation from one phase measurement
(requires explicit user selection and "Estimated" labeling -- pending
owner scope decision).

DEFERRED: RMS-phasor input from a precomputed magnitude/angle channel
(pending DEC-PWR-004 architecture decision).

### DEC-PWR-001 — Operation structure

MW, MVar and MVA are separate user-selectable outputs that share the
underlying calculation. This module returns composite result objects;
callers (the future Calculated Channels service and the Calculator Page)
extract the required scalar. No separate per-quantity entry point is
exposed here -- the single `single_phase_power()` / `three_phase_power()`
call computes all three at once and the caller takes what it needs.

## Input / output conventions

All magnitudes are RMS values in SI base units: volts (V), amperes (A).
All angles are in degrees.
All power results are in SI base units: watts (W), var, volt-amperes (VA).
Callers use app.domain.engineering_units for conversion from/to display
units (kV, MVA, etc.) before and after calling these functions.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Provenance constants (carried in every result, never omitted)
# ---------------------------------------------------------------------------

#: Bump ONLY when the algorithm / approved-decision interpretation itself
#: changes (not for a refactor or docstring update).
ALGORITHM_VERSION = "power_calculation_v1"

#: DEC-PWR-003: passive sign convention, S = V * conj(I) = P + jQ.
SIGN_CONVENTION_PASSIVE = "passive"

#: DEC-PWR-002: S = sqrt(P^2 + Q^2) -- geometric / fundamental-complex.
#: Distinct from IEEE 1459 arithmetic apparent power S_A = sum(|S_k|).
APPARENT_POWER_DEFINITION_GEOMETRIC = "geometric_fundamental_complex"

# ---------------------------------------------------------------------------
# Power-factor sign descriptors
# ---------------------------------------------------------------------------

#: Q > 0: inductive load; current lags voltage (DEC-PWR-003).
POWER_FACTOR_SIGN_LAGGING = "lagging"
#: Q < 0: capacitive load; current leads voltage (DEC-PWR-003).
POWER_FACTOR_SIGN_LEADING = "leading"
#: |Q| negligible relative to S; Q effectively zero.
POWER_FACTOR_SIGN_UNITY = "unity"
#: S = 0 (zero voltage or zero current); power factor not meaningful.
POWER_FACTOR_SIGN_UNDEFINED = "undefined"

KNOWN_POWER_FACTOR_SIGNS = (
    POWER_FACTOR_SIGN_LAGGING,
    POWER_FACTOR_SIGN_LEADING,
    POWER_FACTOR_SIGN_UNITY,
    POWER_FACTOR_SIGN_UNDEFINED,
)

#: Relative threshold for classifying Q as "effectively zero" for the
#: purpose of reporting `POWER_FACTOR_SIGN_UNITY`. Chosen well below any
#: physically meaningful power-factor distinction (a 0.9999 PF angle is
#: ~0.81 deg, implying Q/S ~ 0.014 -- four orders of magnitude above
#: this floor). Absorbs only genuine floating-point noise from a
#: multiply-add chain (2-3 ULP range for IEEE 754 double precision).
_UNITY_PF_Q_RELATIVE_THRESHOLD = 1e-9


# ---------------------------------------------------------------------------
# Input validation predicates (service layer calls these before invoking
# the computation functions below)
# ---------------------------------------------------------------------------

def voltage_magnitude_valid(v_magnitude_rms: float) -> bool:
    """True when the voltage RMS magnitude is finite and non-negative.
    Zero is valid: a de-energised bus has V = 0."""
    return math.isfinite(v_magnitude_rms) and v_magnitude_rms >= 0.0


def current_magnitude_valid(i_magnitude_rms: float) -> bool:
    """True when the current RMS magnitude is finite and non-negative.
    Zero is valid: an open circuit carries I = 0."""
    return math.isfinite(i_magnitude_rms) and i_magnitude_rms >= 0.0


def angle_deg_valid(angle_deg: float) -> bool:
    """True when the angle is a finite floating-point number. No range
    restriction: angles outside (-180, 180] are normalised internally."""
    return math.isfinite(angle_deg)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PerPhasePowerResult:
    """One phase's contribution within a ThreePhasePowerResult.

    Field semantics are identical to SinglePhasePowerResult except that
    provenance metadata (algorithm_version, sign_convention,
    apparent_power_definition) lives on the containing
    ThreePhasePowerResult only -- never duplicated per phase.
    """

    p_watts: float
    """Active power P = Re(V * conj(I)), signed (W).
    Positive: phase absorbs active power. Negative: phase supplies."""

    q_var: float
    """Reactive power Q = Im(V * conj(I)), signed (var).
    Positive: inductive (lagging). Negative: capacitive (leading)."""

    s_va: float
    """Per-phase apparent power |S_phase| = sqrt(P^2 + Q^2) (VA, >= 0).
    Note: sum of per-phase s_va values is the IEEE 1459 arithmetic S_A,
    which is >= the total S in ThreePhasePowerResult (geometric)."""

    power_angle_deg: float
    """Angle of the per-phase complex power S_phase = P + jQ in the PQ
    plane (degrees, normalised to (-180, 180]). Equals theta_V - theta_I
    for this phase pair under the passive sign convention."""

    power_factor: float | None
    """P / S, signed (range [-1, 1]). None when s_va = 0."""

    power_factor_sign: str
    """One of KNOWN_POWER_FACTOR_SIGNS based on the sign of q_var."""


@dataclass(frozen=True, slots=True)
class SinglePhasePowerResult:
    """Complex power from one voltage-current phasor pair.

    DEC-PWR-003: S = V * conj(I) = P + jQ (passive sign convention).
    DEC-PWR-002: s_va = |S| = sqrt(P^2 + Q^2) (geometric).
    All magnitudes in SI base units (W, var, VA).
    """

    p_watts: float
    """Active power P = Re(V * conj(I)), signed (W)."""

    q_var: float
    """Reactive power Q = Im(V * conj(I)), signed (var).
    Positive: inductive/lagging. Negative: capacitive/leading."""

    s_va: float
    """Apparent power |S| = sqrt(P^2 + Q^2) (VA, always >= 0)."""

    power_angle_deg: float
    """Angle of S = P + jQ in the PQ plane (degrees, (-180, 180]).
    Equals theta_V - theta_I under the passive sign convention."""

    power_factor: float | None
    """P / S, signed (range [-1, 1]). None when s_va = 0 (V or I is zero)."""

    power_factor_sign: str
    """One of KNOWN_POWER_FACTOR_SIGNS, derived from sign of q_var."""

    sign_convention: str
    """Always SIGN_CONVENTION_PASSIVE (DEC-PWR-003 provenance)."""

    apparent_power_definition: str
    """Always APPARENT_POWER_DEFINITION_GEOMETRIC (DEC-PWR-002 provenance)."""

    algorithm_version: str
    """Always ALGORITHM_VERSION."""


@dataclass(frozen=True, slots=True)
class ThreePhasePowerResult:
    """Three-phase complex power from three voltage-current phasor pairs.

    DEC-PWR-002: s_va = |S_total| = sqrt(P^2 + Q^2) where
        S_total = V_R*conj(I_R) + V_Y*conj(I_Y) + V_B*conj(I_B).
    This is the GEOMETRIC apparent power. The arithmetic apparent power
    (S_A = phase_r.s_va + phase_y.s_va + phase_b.s_va) is >= s_va, with
    equality only for perfectly balanced systems.

    DEC-PWR-003: passive sign convention; P and Q are signed sums of
    per-phase contributions.

    Phase order: R, Y, B. The three `phase_r`/`phase_y`/`phase_b`
    PerPhasePowerResult fields carry per-phase detail; the top-level
    p_watts, q_var and s_va are the total three-phase quantities.
    """

    p_watts: float
    """Total three-phase active power = Re(S_total) (W)."""

    q_var: float
    """Total three-phase reactive power = Im(S_total) (var)."""

    s_va: float
    """Geometric apparent power |S_total| = sqrt(P^2 + Q^2) (VA, >= 0).
    NOT the arithmetic sum of per-phase apparent powers (DEC-PWR-002)."""

    power_factor: float | None
    """P / S, signed. None when s_va = 0."""

    power_factor_sign: str
    """Lagging / leading / unity / undefined, from total q_var."""

    phase_r: PerPhasePowerResult
    """Phase R (canonical phase A) per-phase result."""

    phase_y: PerPhasePowerResult
    """Phase Y (canonical phase B) per-phase result."""

    phase_b: PerPhasePowerResult
    """Phase B (canonical phase C) per-phase result."""

    sign_convention: str
    """Always SIGN_CONVENTION_PASSIVE."""

    apparent_power_definition: str
    """Always APPARENT_POWER_DEFINITION_GEOMETRIC."""

    algorithm_version: str
    """Always ALGORITHM_VERSION."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_complex(magnitude_rms: float, angle_deg: float) -> complex:
    """Polar form (RMS magnitude, angle in degrees) to complex phasor.
    Uses cmath.rect -- identical shape to sequence_components._to_complex()."""
    return cmath.rect(magnitude_rms, math.radians(angle_deg))


def _normalize_angle_deg(angle_deg: float) -> float:
    """Normalise to (-180, 180] -- identical shape to phasor.py and
    sequence_components.py conventions (each module declares its own tiny
    copy rather than importing a private helper from another)."""
    normalized = float(angle_deg) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _power_factor_sign_from_q(q_var: float, s_va: float) -> str:
    """Classify the power-factor direction from signed Q and |S|.

    When s_va = 0 exactly (zero V or zero I), power factor is undefined.
    When |Q| / S < _UNITY_PF_Q_RELATIVE_THRESHOLD, Q is treated as zero
    (unity PF). Otherwise lagging (Q > 0) or leading (Q < 0).
    s_va is always non-negative (math.hypot result).
    """
    if s_va <= 0.0:
        return POWER_FACTOR_SIGN_UNDEFINED
    if abs(q_var) <= s_va * _UNITY_PF_Q_RELATIVE_THRESHOLD:
        return POWER_FACTOR_SIGN_UNITY
    return POWER_FACTOR_SIGN_LAGGING if q_var > 0.0 else POWER_FACTOR_SIGN_LEADING


def _compute_power_from_complex(v: complex, i: complex) -> tuple[float, float, float, float]:
    """Core single-pair complex power computation.

    Returns (p_watts, q_var, s_va, power_angle_deg).
    S = V * conj(I) -- DEC-PWR-003 passive sign convention.
    s_va = |S| = sqrt(P^2 + Q^2) -- DEC-PWR-002 geometric definition.
    power_angle_deg = arg(S) = theta_V - theta_I, normalised to (-180, 180].
    """
    s_complex = v * i.conjugate()
    p = s_complex.real
    q = s_complex.imag
    s = math.hypot(p, q)
    power_angle_deg = _normalize_angle_deg(math.degrees(cmath.phase(s_complex)))
    return p, q, s, power_angle_deg


def _make_per_phase(p: float, q: float, s: float, pa_deg: float) -> PerPhasePowerResult:
    """Construct a PerPhasePowerResult from pre-computed scalars."""
    pf = p / s if s > 0.0 else None
    return PerPhasePowerResult(
        p_watts=p,
        q_var=q,
        s_va=s,
        power_angle_deg=pa_deg,
        power_factor=pf,
        power_factor_sign=_power_factor_sign_from_q(q, s),
    )


# ---------------------------------------------------------------------------
# Public calculation functions
# ---------------------------------------------------------------------------

def single_phase_power(
    v_magnitude_rms: float,
    v_angle_deg: float,
    i_magnitude_rms: float,
    i_angle_deg: float,
) -> SinglePhasePowerResult:
    """Complex power from one voltage-current phasor pair.

    S = V * conj(I) = P + jQ  (passive sign convention, DEC-PWR-003)
    S_va = |S| = sqrt(P^2 + Q^2)  (geometric, DEC-PWR-002)

    Parameters
    ----------
    v_magnitude_rms : float
        Voltage RMS magnitude in volts (SI). Must satisfy
        voltage_magnitude_valid(); the caller is responsible for
        validation and unit conversion before calling.
    v_angle_deg : float
        Voltage phasor angle in degrees.
    i_magnitude_rms : float
        Current RMS magnitude in amperes (SI). Must satisfy
        current_magnitude_valid().
    i_angle_deg : float
        Current phasor angle in degrees. Defined as the angle of I
        flowing INTO the positive terminal (passive/load convention).

    Returns
    -------
    SinglePhasePowerResult
        All values in SI base units (W, var, VA). See class docstring for
        full field documentation.
    """
    v = _to_complex(v_magnitude_rms, v_angle_deg)
    i = _to_complex(i_magnitude_rms, i_angle_deg)
    p, q, s, power_angle_deg = _compute_power_from_complex(v, i)
    pf = p / s if s > 0.0 else None
    return SinglePhasePowerResult(
        p_watts=p,
        q_var=q,
        s_va=s,
        power_angle_deg=power_angle_deg,
        power_factor=pf,
        power_factor_sign=_power_factor_sign_from_q(q, s),
        sign_convention=SIGN_CONVENTION_PASSIVE,
        apparent_power_definition=APPARENT_POWER_DEFINITION_GEOMETRIC,
        algorithm_version=ALGORITHM_VERSION,
    )


def three_phase_power(
    v_r_magnitude_rms: float,
    v_r_angle_deg: float,
    i_r_magnitude_rms: float,
    i_r_angle_deg: float,
    v_y_magnitude_rms: float,
    v_y_angle_deg: float,
    i_y_magnitude_rms: float,
    i_y_angle_deg: float,
    v_b_magnitude_rms: float,
    v_b_angle_deg: float,
    i_b_magnitude_rms: float,
    i_b_angle_deg: float,
) -> ThreePhasePowerResult:
    """Three-phase complex power from three voltage-current phasor pairs.

    S_total = V_R*conj(I_R) + V_Y*conj(I_Y) + V_B*conj(I_B)
    P       = Re(S_total)  (W)
    Q       = Im(S_total)  (var)
    S       = |S_total| = sqrt(P^2 + Q^2)  (VA, DEC-PWR-002 geometric)

    Phase order is R, Y, B (canonical A, B, C; display convention follows
    Engineering Context per DEC-118 -- never hard-coded here). Each pair
    (V_k, I_k) must be the voltage and current of the SAME measurement
    point for phase k; cross-phase pairing (e.g. V_R with I_Y) produces
    a physically meaningless result and is the caller's responsibility to
    prevent.

    Parameters
    ----------
    v_r_magnitude_rms, v_r_angle_deg : Phase R voltage (V, degrees).
    i_r_magnitude_rms, i_r_angle_deg : Phase R current (A, degrees).
    v_y_magnitude_rms, v_y_angle_deg : Phase Y voltage.
    i_y_magnitude_rms, i_y_angle_deg : Phase Y current.
    v_b_magnitude_rms, v_b_angle_deg : Phase B voltage.
    i_b_magnitude_rms, i_b_angle_deg : Phase B current.
        All magnitudes in SI base units; all validation by the caller.

    Returns
    -------
    ThreePhasePowerResult
        Total P, Q, S plus per-phase PerPhasePowerResult for R, Y, B.
    """
    # Per-phase complex phasors
    v_r = _to_complex(v_r_magnitude_rms, v_r_angle_deg)
    i_r = _to_complex(i_r_magnitude_rms, i_r_angle_deg)
    v_y = _to_complex(v_y_magnitude_rms, v_y_angle_deg)
    i_y = _to_complex(i_y_magnitude_rms, i_y_angle_deg)
    v_b = _to_complex(v_b_magnitude_rms, v_b_angle_deg)
    i_b = _to_complex(i_b_magnitude_rms, i_b_angle_deg)

    # Per-phase power components
    p_r, q_r, s_r, pa_r = _compute_power_from_complex(v_r, i_r)
    p_y, q_y, s_y, pa_y = _compute_power_from_complex(v_y, i_y)
    p_b, q_b, s_b, pa_b = _compute_power_from_complex(v_b, i_b)

    # Total three-phase power (DEC-PWR-002: sum of complex powers, then |.|)
    p_total = p_r + p_y + p_b
    q_total = q_r + q_y + q_b
    s_total = math.hypot(p_total, q_total)

    pf_total = p_total / s_total if s_total > 0.0 else None

    return ThreePhasePowerResult(
        p_watts=p_total,
        q_var=q_total,
        s_va=s_total,
        power_factor=pf_total,
        power_factor_sign=_power_factor_sign_from_q(q_total, s_total),
        phase_r=_make_per_phase(p_r, q_r, s_r, pa_r),
        phase_y=_make_per_phase(p_y, q_y, s_y, pa_y),
        phase_b=_make_per_phase(p_b, q_b, s_b, pa_b),
        sign_convention=SIGN_CONVENTION_PASSIVE,
        apparent_power_definition=APPARENT_POWER_DEFINITION_GEOMETRIC,
        algorithm_version=ALGORITHM_VERSION,
    )
