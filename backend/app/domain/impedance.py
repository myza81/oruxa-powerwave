"""Impedance Locus v1 -- apparent phase impedance from Voltage/Current
phasors, visualized on an R-X plane (see
docs/project-memory/IMPEDANCE_LOCUS_ANALYSIS.md).

**Product definition**: Powerwave calculates apparent phase impedance
`Z = V / I = R + jX` directly from a Voltage and a Current phasor's own
magnitude and angle -- `Za = Va/Ia`, `Zb = Vb/Ib`, `Zc = Vc/Ic`. This is
explicitly measurement/visualization only -- it is NOT Distance
Protection: no protection zones, mho/quadrilateral characteristics,
fault loops, residual-current/k0 compensation, phase-to-phase loops,
directional logic, or trip evaluation exist anywhere in this module (see
module footer). Those belong to a future, separate Distance Protection
analyzer built ON TOP of this same `ImpedancePoint`/R-X-plane foundation
(task's own explicit "reusable foundation for future Distance
Protection" requirement) -- this module never imports or references any
zone/characteristic concept.

Pure, framework-free -- zero registry/I/O access, mirroring `app.domain.
phasor`/`app.domain.overcurrent`'s own layering. `app.services.
impedance_analysis_service` is the only caller for Recording mode, and
owns resolving Va/Vb/Vc/Ia/Ib/Ic (by reusing the existing, unchanged
`compute_phasor_diagram()` -- never a second phasor estimator, per the
task's own explicit "reuse the authoritative Phasor calculation
primitives" instruction).

## Mathematical convention

Direct phasor division, never an RMS-scalar approximation (task's own
explicit "do not approximate R/X from RMS scalar values without phase
angle" requirement):

    Z = V / I = |V|/|I| * exp(j*(theta_V - theta_I))
    R = |Z| * cos(theta_Z)
    X = |Z| * sin(theta_Z)

`theta_V`/`theta_I` are each phasor's own ABSOLUTE angle
(`angle_deg_absolute` in Recording mode, reusing the exact same
convention Phasor's own combined-diagram vector geometry already uses --
see `docs/project-memory/PHASOR_ANALYSIS.md`'s own "Angle reference"
section) -- never independently zero-referenced, which would destroy the
true V-I angular relationship this calculation depends on entirely.

## Low-current guardrail (numerical validity, NOT a relay pickup threshold)

`Z = V/I` is numerically unstable/unbounded as `|I| -> 0`.
`MIN_CURRENT_A` is a fixed floor (in amperes, on whatever basis `I` is
actually expressed) below which a result is reported
`REASON_CURRENT_TOO_SMALL` rather than an arbitrarily large/misleading
`|Z|`. Chosen as `1 mA` (`1e-3 A`): at 1 mA, `|Z| = |V| / 0.001` already
produces at least `100,000 Ohm` for any realistic recorded voltage (a
few hundred V secondary up to several hundred kV primary), i.e. the
result is already meaningless for plotting well before genuine
floating-point instability would set in -- this is a deliberate safety
margin above the floating-point noise floor, not a value tuned to any
protection-relay pickup/sensitivity specification. See task's own
section 20: this is numerical validity, never an invented relay pickup
threshold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.domain.calculated_channel import ChannelRef
from app.domain.phasor import (
    ManualPhasorRoleInput,
    convert_manual_magnitude_to_secondary,
    manual_basis_valid,
    manual_magnitude_valid,
)
from app.domain.engineering_units import ENGINEERING_QUANTITY_CURRENT, ENGINEERING_QUANTITY_VOLTAGE

#: Bump ONLY when the calculation/interpretation itself changes -- never
#: for an unrelated refactor. Included unconditionally in every result.
ALGORITHM_VERSION = "impedance_locus_v1"

#: See module docstring's own "Low-current guardrail" section for the
#: full rationale -- a numerical-validity floor, never a relay pickup
#: value.
MIN_CURRENT_A = 1e-3

IMPEDANCE_BASIS_PRIMARY = "primary"
IMPEDANCE_BASIS_SECONDARY = "secondary"
KNOWN_IMPEDANCE_BASES = (IMPEDANCE_BASIS_PRIMARY, IMPEDANCE_BASIS_SECONDARY)

IMPEDANCE_STATUS_COMPUTED = "computed"
IMPEDANCE_STATUS_NEEDS_CONFIGURATION = "needs_configuration"
IMPEDANCE_STATUS_MISSING = "missing"
IMPEDANCE_STATUS_AMBIGUOUS = "ambiguous"
IMPEDANCE_STATUS_NOT_ELIGIBLE = "not_eligible"

REASON_CURRENT_TOO_SMALL = "current_too_small"
REASON_INVALID_RATIO = "invalid_ratio"
REASON_INVALID_BASIS = "invalid_basis"
REASON_INVALID_MANUAL_MAGNITUDE = "invalid_manual_magnitude"
REASON_UNSUPPORTED_MANUAL_UNIT = "unsupported_manual_unit"


def _normalize_angle_deg(angle_deg: float) -> float:
    """Identical shape to `app.domain.phasor._normalize_angle_deg()` --
    re-declared here rather than imported, matching this codebase's own
    established "each analyzer module owns its own tiny helper/tolerance
    constant" convention (see `app.domain.phasor`'s own `_BOUNDARY_EPS`
    docstring note for the precedent)."""
    normalized = float(angle_deg) % 360.0
    if normalized > 180.0:
        normalized -= 360.0
    return normalized


def impedance_ratio_valid(ratio_primary: float, ratio_secondary: float) -> bool:
    """VT/PT or CT ratio validity -- mirrors `app.domain.phasor.
    manual_ratio_valid()`'s own exact shape (finite, strictly positive).
    Defined independently here rather than imported, per this codebase's
    own established per-analyzer-module convention."""
    return (
        math.isfinite(ratio_primary) and math.isfinite(ratio_secondary)
        and ratio_primary > 0.0 and ratio_secondary > 0.0
    )


@dataclass(frozen=True, slots=True)
class ImpedancePoint:
    """One computed `R + jX` point -- the reusable core value this whole
    feature (and a future Distance Protection analyzer built on top of
    it) revolves around. Never clamped -- all four quadrants are valid
    (task's own explicit "do not clamp negative R or X" requirement)."""

    resistance_ohm: float
    reactance_ohm: float
    magnitude_ohm: float
    angle_deg: float


def compute_impedance_point(
    voltage_magnitude: float, voltage_angle_deg: float, current_magnitude: float, current_angle_deg: float,
    *, min_current: float = MIN_CURRENT_A,
) -> ImpedancePoint | None:
    """The one calculation entry point: `Z = V/I` via direct phasor
    division (never an RMS-scalar approximation -- see module docstring).
    `voltage_magnitude`/`current_magnitude` and the two angles must
    already be on the SAME basis (both Primary or both Secondary) --
    basis normalization/conversion is this module's own separate concern
    (`convert_impedance_basis()` below), never conflated into this
    function. Returns `None` (the low-current guardrail) whenever
    `current_magnitude < min_current` -- never an arbitrarily large or
    infinite `magnitude_ohm`."""
    if not math.isfinite(current_magnitude) or current_magnitude < min_current:
        return None
    if not (math.isfinite(voltage_magnitude) and math.isfinite(voltage_angle_deg) and math.isfinite(current_angle_deg)):
        return None
    magnitude_ohm = voltage_magnitude / current_magnitude
    angle_deg = _normalize_angle_deg(voltage_angle_deg - current_angle_deg)
    angle_rad = math.radians(angle_deg)
    resistance_ohm = magnitude_ohm * math.cos(angle_rad)
    reactance_ohm = magnitude_ohm * math.sin(angle_rad)
    return ImpedancePoint(
        resistance_ohm=resistance_ohm, reactance_ohm=reactance_ohm, magnitude_ohm=magnitude_ohm, angle_deg=angle_deg,
    )


def convert_impedance_basis(
    point: ImpedancePoint,
    *,
    from_basis: str,
    to_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
) -> ImpedancePoint:
    """Converts an already-computed impedance between Primary and
    Secondary basis using the actual VT/CT transformation ratios (task's
    own section 12, verified against this codebase's own established
    ratio convention -- `app.domain.overcurrent.convert_to_relay_
    secondary()` already treats `ct_secondary/ct_primary` as the
    primary-to-secondary scale factor for a CURRENT, i.e.
    `ct_ratio := ct_primary/ct_secondary` and `I_secondary = I_primary /
    ct_ratio`; this module's own VT ratio follows the identical
    convention: `vt_ratio := vt_primary/vt_secondary`,
    `V_secondary = V_primary / vt_ratio`). Combining both:

        Z_secondary = V_secondary / I_secondary
                    = (V_primary / vt_ratio) / (I_primary / ct_ratio)
                    = Z_primary * (ct_ratio / vt_ratio)

        Z_primary = Z_secondary * (vt_ratio / ct_ratio)

    -- exactly the formula the task specifies, confirmed here (not
    blindly adopted) against this codebase's own existing ratio
    direction. A no-op (`from_basis == to_basis`) never requires/reads
    the ratio arguments at all, and never introduces floating-point
    drift from an unnecessary round trip."""
    if from_basis == to_basis:
        return point
    assert vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
    vt_ratio = vt_primary / vt_secondary
    ct_ratio = ct_primary / ct_secondary
    if to_basis == IMPEDANCE_BASIS_PRIMARY:
        factor = vt_ratio / ct_ratio
    else:
        factor = ct_ratio / vt_ratio
    return ImpedancePoint(
        resistance_ohm=point.resistance_ohm * factor,
        reactance_ohm=point.reactance_ohm * factor,
        magnitude_ohm=point.magnitude_ohm * factor,
        angle_deg=point.angle_deg,
    )


# ---------------------------------------------------------------------------
# Recording mode -- a concrete, Impedance-owned result shape (never
# persisted, never a generic cross-analysis framework), mirroring
# `app.domain.overcurrent.OvercurrentAnalysisResult`'s own precedent: ONE
# phase's own result, not a per-role dict (unlike Phasor's own bay-centric
# `PhasorDiagramResult`) -- Impedance Locus v1 always analyzes exactly one
# selected phase at a time (task's own section 8 phase selector).
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ImpedanceAnalysisResult:
    """`voltage_channel_ref`/`current_channel_ref` are populated whenever
    that quantity's own role resolved to a known channel identity
    (`available` OR the whole-result-blocked `needs_configuration` case
    below, mirroring `PhasorDiagramRoleResult.channel_ref`'s own
    "identity known" precedent) -- this is what lets the shared Related
    Waveforms panel (`wwAnalysisSetRelatedWaveformRoles()`) know WHICH
    channel to fetch for this phase's Voltage/Current traces. Without
    these, the frontend has no channel identity to push, which is
    exactly the root cause of a real UAT-reported bug: Related Waveforms
    rendered empty axes with no trace, because every pushed role's own
    `channelRef` was `undefined` (see docs/project-memory/
    IMPEDANCE_LOCUS_ANALYSIS.md's own "Related Waveforms" section for the
    full incident record)."""

    status: str
    engineering_context_id: str
    phase: str
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
    voltage_channel_ref: ChannelRef | None = None
    voltage_magnitude_rms: float | None = None
    voltage_unit: str | None = None
    current_channel_ref: ChannelRef | None = None
    current_magnitude_rms: float | None = None
    current_unit: str | None = None
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    warnings: list[str] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class ImpedanceLocusPoint:
    """One sampled point of the Recording-mode locus/trajectory (task's
    own section 18) -- deliberately a thin, self-contained record (never
    referencing `ImpedanceAnalysisResult` itself) since a locus is a list
    of many of these, most of which will be `status != computed` outside
    the recording's own valid span."""

    analysis_time: float
    status: str
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    reason_code: str | None = None


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode (Analysis Input Source = "manual") -- a
# standalone engineering-calculator path, fully decoupled from recordings/
# Engineering Context/Time Groups/Playback -- see docs/project-memory/
# ANALYSIS_INPUT_SOURCE.md's own governing invariant (DEC-095). Mirrors
# `app.domain.phasor`'s own Manual Input precedent closely: TWO
# independent bases (Voltage/VT, Current/CT) for the INPUT, reusing
# `convert_manual_magnitude_to_secondary()` verbatim for each (task's own
# explicit "reuse Manual Phasor normalization" instruction) -- plus one
# more concept Phasor's own manual mode never needed: an independent
# OUTPUT basis (`impedance_basis`) for the CALCULATED impedance, per the
# task's own explicit "Impedance basis is an output basis, independent of
# the entered Voltage/Current input bases" requirement (section 11).
# ---------------------------------------------------------------------------

MANUAL_ALGORITHM_VERSION = "impedance_manual_v1"


@dataclass(slots=True)
class ManualImpedanceResult:
    """Deliberately has no `engineering_context_id`/`phase`/
    `analysis_time`/`reference_frequency_hz`/`window_seconds` -- none of
    those concepts exist for a standalone manually-entered V/I pair
    (mirrors `ManualPhasorDiagramResult`'s own field-omission rationale).
    `phase_label` is carried through purely for display (e.g. "Za") --
    Manual mode still lets the engineer label which phase they are
    hypothetically evaluating, per the task's own section 8/9 UI, but
    this label plays no role in the calculation itself."""

    status: str
    phase_label: str = "A"
    impedance_basis: str | None = None
    algorithm_version: str = MANUAL_ALGORITHM_VERSION
    voltage_magnitude_secondary: float | None = None
    current_magnitude_secondary: float | None = None
    resistance_ohm: float | None = None
    reactance_ohm: float | None = None
    magnitude_ohm: float | None = None
    angle_deg: float | None = None
    reason_code: str | None = None
    message: str = ""


def evaluate_manual_impedance(
    voltage_input: ManualPhasorRoleInput,
    current_input: ManualPhasorRoleInput,
    *,
    phase_label: str,
    voltage_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    current_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    impedance_basis: str,
) -> ManualImpedanceResult:
    """Normalizes Voltage and Current to Secondary-canonical (reusing
    `convert_manual_magnitude_to_secondary()` verbatim, exactly like
    Phasor's own Manual mode -- never a duplicated VT/CT/unit-conversion
    formula), computes `Z = V/I` in that canonical basis, then converts
    the RESULT to the requested `impedance_basis` -- proving the task's
    own required example valid by construction: Voltage entered Primary,
    Current entered Secondary, Impedance requested Primary all work
    independently, since normalization to Secondary happens per-quantity
    BEFORE the division, and the output conversion happens once, after.

    Missing/invalid Voltage or Current is reported directly (never a
    fabricated/partial impedance) -- there is no "one role missing,
    still show something" case here the way Phasor's own six-independent-
    role diagram has, since impedance fundamentally needs BOTH V and I
    together."""
    if not voltage_input.enabled or voltage_input.magnitude is None or not current_input.enabled or current_input.magnitude is None:
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_MISSING, phase_label=phase_label)

    if not manual_basis_valid(voltage_basis) or not manual_basis_valid(current_basis):
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_INVALID_BASIS)

    if (
        not manual_magnitude_valid(voltage_input.magnitude) or voltage_input.angle_deg is None or not math.isfinite(voltage_input.angle_deg)
        or not manual_magnitude_valid(current_input.magnitude) or current_input.angle_deg is None or not math.isfinite(current_input.angle_deg)
    ):
        return ManualImpedanceResult(
            status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_INVALID_MANUAL_MAGNITUDE,
        )

    if voltage_basis == "primary" and (vt_primary is None or vt_secondary is None or not impedance_ratio_valid(vt_primary, vt_secondary)):
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_INVALID_RATIO)
    if current_basis == "primary" and (ct_primary is None or ct_secondary is None or not impedance_ratio_valid(ct_primary, ct_secondary)):
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_INVALID_RATIO)

    voltage_secondary = convert_manual_magnitude_to_secondary(
        voltage_input.magnitude, unit=voltage_input.unit, engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE,
        basis=voltage_basis, ratio_primary=vt_primary, ratio_secondary=vt_secondary,
    )
    current_secondary = convert_manual_magnitude_to_secondary(
        current_input.magnitude, unit=current_input.unit, engineering_quantity=ENGINEERING_QUANTITY_CURRENT,
        basis=current_basis, ratio_primary=ct_primary, ratio_secondary=ct_secondary,
    )
    if voltage_secondary is None or current_secondary is None:
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_UNSUPPORTED_MANUAL_UNIT)

    point_secondary = compute_impedance_point(voltage_secondary, voltage_input.angle_deg, current_secondary, current_input.angle_deg)
    if point_secondary is None:
        return ManualImpedanceResult(
            status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_CURRENT_TOO_SMALL,
            voltage_magnitude_secondary=voltage_secondary, current_magnitude_secondary=current_secondary,
            message="Current too small for reliable impedance calculation.",
        )

    if impedance_basis == IMPEDANCE_BASIS_PRIMARY and not (
        vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
        and impedance_ratio_valid(vt_primary, vt_secondary) and impedance_ratio_valid(ct_primary, ct_secondary)
    ):
        return ManualImpedanceResult(status=IMPEDANCE_STATUS_NEEDS_CONFIGURATION, phase_label=phase_label, reason_code=REASON_INVALID_RATIO)

    point_out = convert_impedance_basis(
        point_secondary, from_basis=IMPEDANCE_BASIS_SECONDARY, to_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    return ManualImpedanceResult(
        status=IMPEDANCE_STATUS_COMPUTED, phase_label=phase_label, impedance_basis=impedance_basis,
        voltage_magnitude_secondary=voltage_secondary, current_magnitude_secondary=current_secondary,
        resistance_ohm=point_out.resistance_ohm, reactance_ohm=point_out.reactance_ohm,
        magnitude_ohm=point_out.magnitude_ohm, angle_deg=point_out.angle_deg,
        message="Manual impedance evaluated.",
    )


# ---------------------------------------------------------------------------
# Explicit non-scope boundary (owner instruction -- restated here, not
# just in the module docstring, since this is the single most important
# interpretive boundary of this feature):
#
#   Impedance Locus v1 IS: apparent phase impedance measurement and R-X
#   visualization (Za/Zb/Zc only), for engineering study.
#
#   Impedance Locus v1 is NOT: Distance Protection. No mho/quadrilateral
#   characteristics, protection zones (Z1/Z2/Z3), fault loops, ground/
#   residual-current (k0) compensation, phase-to-phase loops (Zab/Zbc/
#   Zca), fault classification, load encroachment, power swing detection,
#   directional logic, or trip-decision claims exist anywhere in this
#   module, `impedance_analysis_service`, or the frontend Impedance Locus
#   panel. These belong to a future, SEPARATE Distance Protection
#   analyzer, built on top of this module's own `ImpedancePoint`/R-X-plane
#   foundation, never coupled into it here.
# ---------------------------------------------------------------------------
