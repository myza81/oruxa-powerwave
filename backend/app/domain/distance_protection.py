"""Distance Protection v1 -- phase-phase (AB/BC/CA) fault-loop impedance,
Mho and Quadrilateral zone characteristics, and Operated/Not-Operated
zone-element state (see
docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md).

**Product definition**: Powerwave calculates the fault-loop impedance a
distance relay would see for a selected phase-phase loop --

    Zab = (Va - Vb) / (Ia - Ib)
    Zbc = (Vb - Vc) / (Ib - Ic)
    Zca = (Vc - Va) / (Ic - Ia)

-- via full complex phasor subtraction and division (never derived from
scalar RMS magnitudes alone), then evaluates that loop impedance against
up to three independently-configured protection zones, each using
either a Mho (circular) or a Quadrilateral (polygonal) characteristic.
This is calculation + visualization only -- explicitly NOT full relay
logic. See module footer for the complete non-scope boundary.

## Conceptual separation from Impedance Locus (task's own explicit framing)

    Impedance Locus     -> what impedance did the system present? (Za/Zb/Zc, phase)
    Distance Protection  -> how does the configured distance characteristic
                             interpret that impedance? (Zab/Zbc/Zca, loop)

This module deliberately sits ALONGSIDE `app.domain.impedance`, never
inside it -- exactly the "reusable foundation for a future Distance
Protection analyzer" DEC-096 itself already documents: `app.domain.
impedance` never imports or references any zone/characteristic/fault-
loop concept, and this module never modifies it. It REUSES two of that
module's own functions verbatim, unchanged:

- `compute_impedance_point()` -- for the loop impedance's own `Z =
  Vloop/Iloop` division AND its own low-current guardrail (`MIN_CURRENT_A`
  applies identically to `|Iloop|` as it does to `|Iphase|` -- this
  module introduces no second guardrail, no second threshold).
- `convert_impedance_basis()` -- for the independent output Primary/
  Secondary impedance basis, the exact same VT/CT ratio formula
  Impedance Locus already established, never duplicated here.

The only genuinely NEW math this module contributes is (1) the phasor
SUBTRACTION that turns two phase phasors into one loop phasor (Vab =
Va - Vb, Iab = Ia - Ib) before handing off to `compute_impedance_point()`,
and (2) the zone-characteristic geometry (Mho circle / Quadrilateral
polygon) and Operated/Not-Operated membership test layered on TOP of
the resulting `ImpedancePoint`.

## Complex-number representation

Reuses `app.domain.sequence_components`'s own established convention
(the first module in this codebase to need genuine complex-number
arithmetic) rather than hand-rolling real/imaginary bookkeeping: stdlib
`complex`/`cmath` directly, via `cmath.rect()`/`cmath.polar()`. There is
exactly one subtraction per loop per analysis (never a per-sample
loop), so there is no performance reason to avoid it.

## Layered architecture (task's own explicit section 35 requirement)

    phasor input (compute_phasor_diagram(), unchanged)
        |
    loop impedance engine (THIS module: compute_loop_impedance(),
                            reusing compute_impedance_point()/
                            convert_impedance_basis() verbatim)
        |
    distance characteristic engine (THIS module: mho_zone_operated()/
                                     quadrilateral_zone_operated())
        |
    zone element state (THIS module: evaluate_zone_state() ->
                         Operated/Not Operated only, never latched,
                         never a timer, never a trip claim)
        |
    visualization (frontend -- reuses Impedance Locus's own equal-
                    scale R-X SVG coordinate transform verbatim)

Kept genuinely separate so a future enhancement (AG/BG/CG loops, k0/
residual-current compensation, memory/negative-sequence polarization,
load encroachment, power swing blocking, timer accumulation, trip
logic) can be added at its own layer without rewriting the loop-
impedance or characteristic-geometry engines here.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field

from app.domain.calculated_channel import ChannelRef
from app.domain.impedance import (
    IMPEDANCE_BASIS_PRIMARY,
    IMPEDANCE_BASIS_SECONDARY,
    KNOWN_IMPEDANCE_BASES,
    MIN_CURRENT_A,
    ImpedancePoint,
    compute_impedance_point,
    convert_impedance_basis,
    impedance_ratio_valid,
)
from app.domain.phasor import (
    ManualPhasorRoleInput,
    convert_manual_magnitude_to_secondary,
    manual_basis_valid,
    manual_magnitude_valid,
)
from app.domain.engineering_units import ENGINEERING_QUANTITY_CURRENT, ENGINEERING_QUANTITY_VOLTAGE

#: Bump ONLY when the calculation/interpretation itself changes -- never
#: for an unrelated refactor. Included unconditionally in every result.
ALGORITHM_VERSION = "distance_protection_v1"

#: Bumped only if Manual Distance Protection's own composition changes --
#: independent of `ALGORITHM_VERSION`, mirroring every other analyzer's
#: identical Manual/Recording version-independence.
MANUAL_ALGORITHM_VERSION = "distance_protection_manual_v1"

# ---------------------------------------------------------------------------
# Fault loops -- phase-phase only for v1 (task's own explicit scope: no
# AG/BG/CG ground loops, no residual-current/k0 compensation).
# ---------------------------------------------------------------------------

LOOP_AB = "AB"
LOOP_BC = "BC"
LOOP_CA = "CA"
KNOWN_LOOPS = (LOOP_AB, LOOP_BC, LOOP_CA)

#: Which two Voltage roles and two Current roles (in `compute_phasor_
#: diagram()`'s own `PHASOR_DIAGRAM_ROLE_ORDER` naming) a selected loop
#: needs -- e.g. AB needs Va+Vb+Ia+Ib, never Vc/Ic (task's own explicit
#: "do not require unrelated phase C values for AB calculation"
#: instruction). Order is (v1_role_key, v2_role_key, i1_role_key,
#: i2_role_key); the loop impedance is always `(X1 - X2)`, matching each
#: loop's own subscript order (Vab = Va - Vb, never Vb - Va).
LOOP_ROLE_KEYS = {
    LOOP_AB: ("Va", "Vb", "Ia", "Ib"),
    LOOP_BC: ("Vb", "Vc", "Ib", "Ic"),
    LOOP_CA: ("Vc", "Va", "Ic", "Ia"),
}

# Reuses the SAME five-value vocabulary compute_phasor_diagram()/
# app.domain.impedance/app.domain.sequence_components already return,
# never inventing a new one.
DISTANCE_STATUS_COMPUTED = "computed"
DISTANCE_STATUS_NEEDS_CONFIGURATION = "needs_configuration"
DISTANCE_STATUS_MISSING = "missing"
DISTANCE_STATUS_AMBIGUOUS = "ambiguous"
DISTANCE_STATUS_NOT_ELIGIBLE = "not_eligible"

REASON_LOOP_CURRENT_TOO_SMALL = "loop_current_too_small"
REASON_UNSUPPORTED_LOOP = "unsupported_loop"
REASON_INVALID_RATIO = "invalid_ratio"
REASON_INVALID_BASIS = "invalid_basis"
REASON_INVALID_MANUAL_MAGNITUDE = "invalid_manual_magnitude"
REASON_UNSUPPORTED_MANUAL_UNIT = "unsupported_manual_unit"


def _normalize_angle_deg(angle_deg: float) -> float:
    """Identical shape to `app.domain.phasor._normalize_angle_deg()`/
    `app.domain.impedance._normalize_angle_deg()` -- re-declared here
    rather than imported, matching this codebase's own established
    "each analyzer module owns its own tiny helper/tolerance constant"
    convention."""
    normalized = float(angle_deg) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def _to_complex(magnitude: float, angle_deg: float) -> complex:
    return cmath.rect(magnitude, math.radians(angle_deg))


def _to_magnitude_angle(value: complex) -> tuple[float, float]:
    magnitude, angle_rad = cmath.polar(value)
    return magnitude, _normalize_angle_deg(math.degrees(angle_rad))


def loop_ratio_valid(ratio_primary: float, ratio_secondary: float) -> bool:
    """VT/PT or CT ratio validity -- mirrors `app.domain.impedance.
    impedance_ratio_valid()`'s own exact shape. Defined independently
    here rather than imported, per this codebase's own established
    per-analyzer-module convention."""
    return (
        math.isfinite(ratio_primary) and math.isfinite(ratio_secondary)
        and ratio_primary > 0.0 and ratio_secondary > 0.0
    )


def compute_loop_impedance(
    v1_magnitude: float, v1_angle_deg: float, v2_magnitude: float, v2_angle_deg: float,
    i1_magnitude: float, i1_angle_deg: float, i2_magnitude: float, i2_angle_deg: float,
    *, min_current: float = MIN_CURRENT_A,
) -> ImpedancePoint | None:
    """The one loop-impedance entry point: `Vloop = X1 - X2` (complex
    phasor subtraction, NEVER scalar RMS subtraction) for both Voltage
    and Current, then `Zloop = Vloop / Iloop` via the EXISTING, UNCHANGED
    `compute_impedance_point()` -- this function's only original
    contribution is the subtraction; the division, R/X/angle
    decomposition, and low-current guardrail are all reused verbatim
    from `app.domain.impedance`. All four magnitude/angle pairs must
    already be on the SAME basis (both Primary or both Secondary) --
    basis normalization/conversion is a separate concern (`convert_
    impedance_basis()`, reused unchanged), never conflated here."""
    v1 = _to_complex(v1_magnitude, v1_angle_deg)
    v2 = _to_complex(v2_magnitude, v2_angle_deg)
    i1 = _to_complex(i1_magnitude, i1_angle_deg)
    i2 = _to_complex(i2_magnitude, i2_angle_deg)
    v_loop_magnitude, v_loop_angle_deg = _to_magnitude_angle(v1 - v2)
    i_loop_magnitude, i_loop_angle_deg = _to_magnitude_angle(i1 - i2)
    return compute_impedance_point(
        v_loop_magnitude, v_loop_angle_deg, i_loop_magnitude, i_loop_angle_deg, min_current=min_current,
    )


# ---------------------------------------------------------------------------
# Distance characteristic engine -- Mho (circular) and Quadrilateral
# (polygonal) zone geometry, and Operated/Not-Operated membership.
# Pure R-X-plane geometry, no knowledge of Voltage/Current/loops at all
# below this point -- operates entirely on an already-computed
# `ImpedancePoint`.
# ---------------------------------------------------------------------------

CHARACTERISTIC_MHO = "mho"
CHARACTERISTIC_QUADRILATERAL = "quadrilateral"
KNOWN_CHARACTERISTICS = (CHARACTERISTIC_MHO, CHARACTERISTIC_QUADRILATERAL)

ZONE_STATE_OPERATED = "operated"
ZONE_STATE_NOT_OPERATED = "not_operated"

#: Task's own section 16 recommendation: "boundary counts as Operated,
#: with numerical tolerance." A fixed, tiny absolute tolerance in ohms
#: -- large enough to absorb ordinary floating-point representation
#: noise at an exact geometric boundary, far too small to ever affect a
#: genuinely inside/outside point at any realistic zone reach. This is
#: purely a numerical-boundary-inclusion convention, never a relay
#: accuracy/security margin.
ZONE_BOUNDARY_TOLERANCE_OHM = 1e-6

ZONE_KEY_1 = "zone1"
ZONE_KEY_2 = "zone2"
ZONE_KEY_3 = "zone3"
ZONE_KEYS = (ZONE_KEY_1, ZONE_KEY_2, ZONE_KEY_3)


@dataclass(frozen=True, slots=True)
class ZoneSettings:
    """One zone's own configuration -- a single shape that carries
    BOTH characteristics' own fields (task's own section 18: switching
    characteristic must "preserve relevant shared settings where
    sensible"). Only the fields the currently-selected `characteristic`
    actually needs are read; the other characteristic's own fields are
    simply carried through unused, so switching back and forth never
    loses previously-entered values. `characteristic_angle_deg` is
    deliberately the ONE shared angle field for both characteristics
    (task's own "characteristic/directional angle **or equivalent**"
    wording for Quadrilateral) -- Mho's own classic characteristic
    angle and Quadrilateral's own reactance-line-tilt/directional angle
    are, by this module's own coherent choice (documented in
    `quadrilateral_zone_operated()` below), the SAME physical angle
    concept, never two separate settings."""

    enabled: bool = False
    reach_ohm: float | None = None
    reactive_reach_ohm: float | None = None
    resistive_reach_forward_ohm: float | None = None
    resistive_reach_reverse_ohm: float | None = None
    characteristic_angle_deg: float = 90.0
    delay_s: float = 0.0


def mho_zone_operated(point: ImpedancePoint, *, reach_ohm: float, characteristic_angle_deg: float) -> bool:
    """Standard forward mho (self-polarized) characteristic: a circle
    whose diameter runs from the origin (R=0, X=0 -- zero impedance, a
    fault at the relay's own location) to the reach vector `Z_reach =
    reach_ohm ∠ characteristic_angle_deg`. This is the textbook mho
    definition (never an "arbitrary centered circle," per the task's
    own explicit instruction) -- derived mathematically from reach and
    angle, not eyeballed:

        Z_reach = reach_ohm * exp(j * characteristic_angle_deg)
        center  = Z_reach / 2
        radius  = reach_ohm / 2

    A point operates when `|Z - center| <= radius` (boundary inclusive,
    within `ZONE_BOUNDARY_TOLERANCE_OHM`) -- exactly equivalent to the
    classical mho relay operating equation for a self-polarized
    characteristic. All four R-X quadrants are reachable by this test;
    a point diametrically opposite the reach vector (the "reverse-side"
    of the origin) is mathematically excluded by construction, never
    clamped after the fact."""
    if not (math.isfinite(reach_ohm) and reach_ohm > 0.0):
        return False
    angle_rad = math.radians(characteristic_angle_deg)
    half_reach = reach_ohm / 2.0
    center_r = half_reach * math.cos(angle_rad)
    center_x = half_reach * math.sin(angle_rad)
    radius = half_reach
    distance = math.hypot(point.resistance_ohm - center_r, point.reactance_ohm - center_x)
    return distance <= radius + ZONE_BOUNDARY_TOLERANCE_OHM


def quadrilateral_zone_operated(
    point: ImpedancePoint, *,
    reactive_reach_ohm: float, resistive_reach_forward_ohm: float, resistive_reach_reverse_ohm: float,
    characteristic_angle_deg: float,
) -> bool:
    """A generic, non-vendor-specific quadrilateral zone -- this
    module's own coherent, documented parameterization (task's own
    explicit "keep it generic, do not copy a vendor relay's proprietary
    setting model" instruction), built from a ROTATED coordinate frame
    aligned to `characteristic_angle_deg` (theta):

        x' =  R*cos(theta) + X*sin(theta)   (signed distance along the
                                              reach direction, i.e. the
                                              projection of Z onto the
                                              unit vector at angle theta)
        r' =  R*sin(theta) - X*cos(theta)   (signed distance along the
                                              perpendicular direction,
                                              the unit vector at angle
                                              theta - 90 deg)

    Four half-plane boundaries, ALL satisfied simultaneously for the
    zone to operate:

        0                       <= x' <= reactive_reach_ohm   (reach line, forward-only)
        -resistive_reach_reverse_ohm <= r' <= resistive_reach_forward_ohm

    At `characteristic_angle_deg = 90` this degenerates EXACTLY to the
    simplest, most classic textbook shape (x'=X, r'=R): a horizontal
    reactance line at X=reactive_reach_ohm, a directional line along the
    R-axis itself (X>=0, excluding reverse faults), and two vertical
    resistive blinders at R=+resistive_reach_forward_ohm/
    R=-resistive_reach_reverse_ohm -- confirmed algebraically, not
    merely asserted (see this module's own golden domain tests). For
    other angles the whole rectangle rotates rigidly around the origin,
    tilting the reach direction to match `characteristic_angle_deg` --
    the same coherent angle concept `mho_zone_operated()` uses,
    deliberately never a second, differently-defined angle parameter."""
    if not (
        math.isfinite(reactive_reach_ohm) and reactive_reach_ohm > 0.0
        and math.isfinite(resistive_reach_forward_ohm) and resistive_reach_forward_ohm > 0.0
        and math.isfinite(resistive_reach_reverse_ohm) and resistive_reach_reverse_ohm > 0.0
    ):
        return False
    theta = math.radians(characteristic_angle_deg)
    r, x = point.resistance_ohm, point.reactance_ohm
    x_prime = r * math.cos(theta) + x * math.sin(theta)
    r_prime = r * math.sin(theta) - x * math.cos(theta)
    tol = ZONE_BOUNDARY_TOLERANCE_OHM
    return (
        -tol <= x_prime <= reactive_reach_ohm + tol
        and -resistive_reach_reverse_ohm - tol <= r_prime <= resistive_reach_forward_ohm + tol
    )


def evaluate_zone_state(point: ImpedancePoint | None, *, characteristic: str, zone: ZoneSettings) -> str:
    """The one zone-element-state entry point -- INSTANTANEOUS geometric
    state only (task's own explicit section 25: "do not latch zone
    state across time"). A disabled zone, or no valid point at all
    (e.g. the loop-current guardrail blocked calculation), is always
    `ZONE_STATE_NOT_OPERATED` -- never a fabricated Operated state, and
    never an exception. Each zone is evaluated completely
    INDEPENDENTLY (task's own section 15: "do not force only one zone
    to operate" -- Zone 1/2/3 can legitimately all be `Operated`
    simultaneously for a nested characteristic set; this function has
    no knowledge of the other two zones at all)."""
    if point is None or not zone.enabled:
        return ZONE_STATE_NOT_OPERATED
    if characteristic == CHARACTERISTIC_MHO:
        if zone.reach_ohm is None:
            return ZONE_STATE_NOT_OPERATED
        operated = mho_zone_operated(point, reach_ohm=zone.reach_ohm, characteristic_angle_deg=zone.characteristic_angle_deg)
    elif characteristic == CHARACTERISTIC_QUADRILATERAL:
        if zone.reactive_reach_ohm is None or zone.resistive_reach_forward_ohm is None or zone.resistive_reach_reverse_ohm is None:
            return ZONE_STATE_NOT_OPERATED
        operated = quadrilateral_zone_operated(
            point, reactive_reach_ohm=zone.reactive_reach_ohm,
            resistive_reach_forward_ohm=zone.resistive_reach_forward_ohm,
            resistive_reach_reverse_ohm=zone.resistive_reach_reverse_ohm,
            characteristic_angle_deg=zone.characteristic_angle_deg,
        )
    else:
        return ZONE_STATE_NOT_OPERATED
    return ZONE_STATE_OPERATED if operated else ZONE_STATE_NOT_OPERATED


@dataclass(frozen=True, slots=True)
class ZoneResult:
    """One zone's own reported state -- `state` is PURE geometric
    element state (task's own section 13: `Operated` means "the
    calculated loop impedance satisfies/breaches the configured zone
    operating characteristic geometrically" -- it does NOT mean relay
    trip output asserted, breaker opened, or full relay logic
    completed). `delay_s` is configuration information only (task's own
    section 26 -- never accumulated, never declared elapsed, never used
    to assert a trip)."""

    zone_key: str
    enabled: bool
    state: str
    delay_s: float


# ---------------------------------------------------------------------------
# Recording mode -- a concrete, Distance-Protection-owned result shape
# (never persisted), mirroring `app.domain.impedance.
# ImpedanceAnalysisResult`'s own precedent, doubled for the two loop
# legs (V1/V2, I1/I2) and extended with the three independent zone
# results.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DistanceAnalysisResult:
    """`v1_channel_ref`/`v2_channel_ref`/`i1_channel_ref`/`i2_channel_ref`
    are populated whenever that leg's own role identity is known,
    independent of this result's own `status` -- mirrors
    `ImpedanceAnalysisResult`'s own "identity known, independent of
    overall status" precedent, so the shared Related Waveforms panel
    can always show the underlying source phase quantities for the
    selected loop even when the loop impedance itself could not be
    computed."""

    status: str
    engineering_context_id: str
    loop: str
    analysis_time: float
    recording_basis: str | None = None
    impedance_basis: str | None = None
    vt_primary: float | None = None
    vt_secondary: float | None = None
    ct_primary: float | None = None
    ct_secondary: float | None = None
    reference_frequency_hz: float | None = None
    window_seconds: float | None = None
    algorithm_version: str = ALGORITHM_VERSION
    v1_channel_ref: ChannelRef | None = None
    v2_channel_ref: ChannelRef | None = None
    i1_channel_ref: ChannelRef | None = None
    i2_channel_ref: ChannelRef | None = None
    voltage_unit: str | None = None
    current_unit: str | None = None
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    characteristic: str | None = None
    zone1: ZoneResult | None = None
    zone2: ZoneResult | None = None
    zone3: ZoneResult | None = None
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class DistanceLocusPoint:
    """One sampled point of the Recording-mode locus/trajectory --
    deliberately thin and self-contained, mirroring `app.domain.
    impedance.ImpedanceLocusPoint`'s own precedent verbatim. Zone state
    is intentionally NOT carried per locus point (task's own section 25:
    only the CURRENT Playback-driven point drives zone state; the
    static trajectory itself is measurement/visualization only)."""

    analysis_time: float
    status: str
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    reason_code: str | None = None


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode (Analysis Input Source = "manual") -- a
# standalone engineering-calculator path, fully decoupled from
# recordings/Engineering Context/Time Groups/Playback -- see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md's own governing invariant
# (DEC-095). Mirrors `app.domain.impedance`'s own Manual Input precedent
# closely, extended from ONE V/I pair to a LOOP's own two V/I pairs.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ManualDistanceResult:
    """Deliberately no `engineering_context_id`/`analysis_time`/
    `reference_frequency_hz`/`window_seconds` -- none of those concepts
    exist for a standalone manually-entered phasor set (mirrors
    `ManualImpedanceResult`'s own field-omission rationale). `loop_label`
    is carried through purely for display (e.g. "AB")."""

    status: str
    loop_label: str = LOOP_AB
    impedance_basis: str | None = None
    algorithm_version: str = MANUAL_ALGORITHM_VERSION
    v1_magnitude_secondary: float | None = None
    v2_magnitude_secondary: float | None = None
    i1_magnitude_secondary: float | None = None
    i2_magnitude_secondary: float | None = None
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    characteristic: str | None = None
    zone1: ZoneResult | None = None
    zone2: ZoneResult | None = None
    zone3: ZoneResult | None = None
    reason_code: str | None = None
    message: str = ""


def evaluate_manual_distance(
    v1_input: ManualPhasorRoleInput, v2_input: ManualPhasorRoleInput,
    i1_input: ManualPhasorRoleInput, i2_input: ManualPhasorRoleInput,
    *,
    loop_label: str,
    voltage_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    current_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    impedance_basis: str,
    characteristic: str,
    zone1: ZoneSettings,
    zone2: ZoneSettings,
    zone3: ZoneSettings,
) -> ManualDistanceResult:
    """Normalizes both Voltage legs and both Current legs to Secondary-
    canonical (reusing `convert_manual_magnitude_to_secondary()`
    verbatim, exactly like Impedance's own Manual mode -- never a
    duplicated VT/CT/unit-conversion formula), computes the loop
    impedance in that canonical basis via `compute_loop_impedance()`
    (this module's own function, itself reusing `compute_impedance_
    point()` unchanged), then converts the RESULT to the requested
    `impedance_basis`. A missing/invalid leg is reported directly
    (never a fabricated/partial loop impedance) -- a loop fundamentally
    needs all four legs together, mirroring Impedance's own "no
    partial-role tolerance" precedent for a V/I pair, extended to four
    legs here."""

    def _zone_out(key: str, settings: ZoneSettings, point: ImpedancePoint | None) -> ZoneResult:
        return ZoneResult(zone_key=key, enabled=settings.enabled, state=evaluate_zone_state(point, characteristic=characteristic, zone=settings), delay_s=settings.delay_s)

    def _missing_with_zones(status: str, reason_code: str | None = None, message: str = "") -> ManualDistanceResult:
        return ManualDistanceResult(
            status=status, loop_label=loop_label, reason_code=reason_code, message=message,
            characteristic=characteristic,
            zone1=_zone_out(ZONE_KEY_1, zone1, None), zone2=_zone_out(ZONE_KEY_2, zone2, None), zone3=_zone_out(ZONE_KEY_3, zone3, None),
        )

    if not (v1_input.enabled and v1_input.magnitude is not None and v2_input.enabled and v2_input.magnitude is not None
            and i1_input.enabled and i1_input.magnitude is not None and i2_input.enabled and i2_input.magnitude is not None):
        return _missing_with_zones(DISTANCE_STATUS_MISSING)

    if not manual_basis_valid(voltage_basis) or not manual_basis_valid(current_basis):
        return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_INVALID_BASIS)

    for role_input in (v1_input, v2_input, i1_input, i2_input):
        if not manual_magnitude_valid(role_input.magnitude) or role_input.angle_deg is None or not math.isfinite(role_input.angle_deg):
            return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_INVALID_MANUAL_MAGNITUDE)

    if voltage_basis == IMPEDANCE_BASIS_PRIMARY and (vt_primary is None or vt_secondary is None or not loop_ratio_valid(vt_primary, vt_secondary)):
        return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_INVALID_RATIO)
    if current_basis == IMPEDANCE_BASIS_PRIMARY and (ct_primary is None or ct_secondary is None or not loop_ratio_valid(ct_primary, ct_secondary)):
        return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_INVALID_RATIO)

    v1_secondary = convert_manual_magnitude_to_secondary(v1_input.magnitude, unit=v1_input.unit, engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE, basis=voltage_basis, ratio_primary=vt_primary, ratio_secondary=vt_secondary)
    v2_secondary = convert_manual_magnitude_to_secondary(v2_input.magnitude, unit=v2_input.unit, engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE, basis=voltage_basis, ratio_primary=vt_primary, ratio_secondary=vt_secondary)
    i1_secondary = convert_manual_magnitude_to_secondary(i1_input.magnitude, unit=i1_input.unit, engineering_quantity=ENGINEERING_QUANTITY_CURRENT, basis=current_basis, ratio_primary=ct_primary, ratio_secondary=ct_secondary)
    i2_secondary = convert_manual_magnitude_to_secondary(i2_input.magnitude, unit=i2_input.unit, engineering_quantity=ENGINEERING_QUANTITY_CURRENT, basis=current_basis, ratio_primary=ct_primary, ratio_secondary=ct_secondary)
    if v1_secondary is None or v2_secondary is None or i1_secondary is None or i2_secondary is None:
        return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_UNSUPPORTED_MANUAL_UNIT)

    point_secondary = compute_loop_impedance(
        v1_secondary, v1_input.angle_deg, v2_secondary, v2_input.angle_deg,
        i1_secondary, i1_input.angle_deg, i2_secondary, i2_input.angle_deg,
    )
    if point_secondary is None:
        result = _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_LOOP_CURRENT_TOO_SMALL, "Loop current too small for reliable impedance calculation.")
        result.v1_magnitude_secondary, result.v2_magnitude_secondary = v1_secondary, v2_secondary
        result.i1_magnitude_secondary, result.i2_magnitude_secondary = i1_secondary, i2_secondary
        return result

    if impedance_basis == IMPEDANCE_BASIS_PRIMARY and not (
        vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
        and loop_ratio_valid(vt_primary, vt_secondary) and loop_ratio_valid(ct_primary, ct_secondary)
    ):
        return _missing_with_zones(DISTANCE_STATUS_NEEDS_CONFIGURATION, REASON_INVALID_RATIO)

    point_out = convert_impedance_basis(
        point_secondary, from_basis=IMPEDANCE_BASIS_SECONDARY, to_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    return ManualDistanceResult(
        status=DISTANCE_STATUS_COMPUTED, loop_label=loop_label, impedance_basis=impedance_basis,
        v1_magnitude_secondary=v1_secondary, v2_magnitude_secondary=v2_secondary,
        i1_magnitude_secondary=i1_secondary, i2_magnitude_secondary=i2_secondary,
        resistance_ohm=point_out.resistance_ohm, reactance_ohm=point_out.reactance_ohm,
        magnitude_ohm=point_out.magnitude_ohm, angle_deg=point_out.angle_deg,
        characteristic=characteristic,
        zone1=_zone_out(ZONE_KEY_1, zone1, point_out), zone2=_zone_out(ZONE_KEY_2, zone2, point_out), zone3=_zone_out(ZONE_KEY_3, zone3, point_out),
        message="Manual loop impedance evaluated.",
    )


# ---------------------------------------------------------------------------
# Explicit non-scope boundary (owner instruction -- restated here, not
# just in the module docstring, since this is the single most important
# interpretive boundary of this feature):
#
#   Distance Protection v1 IS: phase-phase (AB/BC/CA) fault-loop
#   impedance calculation, Mho and Quadrilateral zone-characteristic
#   geometry, and INSTANTANEOUS Operated/Not-Operated geometric zone-
#   element state, for engineering study.
#
#   Distance Protection v1 is NOT: full relay logic. No AG/BG/CG ground
#   loops, residual-current (k0) compensation, zero-sequence
#   compensation, memory polarization, negative-sequence polarization,
#   load encroachment, power swing blocking, directional supervision
#   beyond the geometric characteristic itself, relay trip output,
#   breaker operation, timer accumulation, vendor-specific relay logic,
#   or fault classification exist anywhere in this module,
#   `distance_protection_analysis_service`, or the frontend Distance
#   Protection panel. `Operated` is a purely GEOMETRIC statement about
#   where the calculated loop impedance sits relative to a configured
#   characteristic -- it never means a relay tripped, a breaker opened,
#   or full relay logic completed. `delay_s` is configuration
#   information only -- never accumulated, never declared elapsed,
#   never used to assert a trip. These belong to a future, SEPARATE
#   enhancement built on top of this module's own loop-impedance/zone-
#   state foundation, never coupled into it here.
# ---------------------------------------------------------------------------
