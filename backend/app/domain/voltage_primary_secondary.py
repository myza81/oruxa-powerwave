"""Primary/Secondary voltage reference model for Per-Unit calculations
(DEC-050 Slice 5C-2).

This module provides the pure-domain data contracts and computations for the
Primary/Secondary voltage reference distinction required when a recording may
contain measurements made at different electrical sides of a VT (instrument
transformer) — primary (high-voltage, system side) or secondary (low-voltage,
recorder/relay side).

The model handles five cases described in the Slice 5C-2 specification:

  Case A — Primary L-L measurement:   denominator = nominal_primary_ll_kv
  Case B — Primary L-G measurement:   denominator = nominal_primary_ll_kv / √3
  Case C — Secondary L-L measurement: denominator = secondary_ll_v (in V)
  Case D — Secondary L-G measurement: denominator = secondary_ll_v / √3
  Case E — Phase-winding VT ratio:    primary_ll_v = p_winding_v × √3
                                       secondary_ll_v = s_winding_v × √3

Key design principles (from Slice 5C-2 specification §3–§7):

  1. Never conflate nominal system voltage with secondary VT voltage.
  2. Explicitly distinguish VT winding ratings from independently established
     nominal system values.
  3. Do not silently round computed VT-derived equivalents to convenient values
     (e.g. 76,200 × √3 V ≠ exactly 132,000 V).
  4. Unknown measurement side must not be silently promoted to Primary or
     Secondary for automatic PU purposes (Case F).
  5. This module is NOT wired into the live resolver — it establishes the model
     and validates the computations. Connecting it to the existing
     resolve_voltage_base_for_group() is a controlled step for Slice 5D.
  6. No sample conversion, no CT/VT scaling, no frontend changes.

SQRT_3 is defined here independently for precision (same value as voltage_group_config.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

SQRT_3 = 1.7320508075688772

# ---------------------------------------------------------------------------
# VT winding reference — phase-referred vs L-L-referred
# ---------------------------------------------------------------------------

VtWindingRef = Literal["phase", "ll"]
VT_WINDING_PHASE: VtWindingRef = "phase"
VT_WINDING_LL: VtWindingRef = "ll"
KNOWN_VT_WINDING_REFS: tuple[VtWindingRef, ...] = (VT_WINDING_PHASE, VT_WINDING_LL)

# ---------------------------------------------------------------------------
# Measurement and base sides (mirror reference_side.py literals)
# ---------------------------------------------------------------------------

SIDE_PRIMARY = "primary"
SIDE_SECONDARY = "secondary"
SIDE_UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Voltage representation (mirror line_to_line / line_to_ground)
# ---------------------------------------------------------------------------

REPR_LINE_TO_LINE = "line_to_line"
REPR_LINE_TO_GROUND = "line_to_ground"
KNOWN_REPRESENTATIONS = (REPR_LINE_TO_LINE, REPR_LINE_TO_GROUND)

# ---------------------------------------------------------------------------
# VT ratio domain type
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class VtRatio:
    """Instrument transformer (VT) winding ratio.

    primary_winding_v / secondary_winding_v:
      - If winding_ref == "phase": values are phase-to-ground voltages.
        L-L equivalents are derived by multiplying by √3.
      - If winding_ref == "ll":    values are line-to-line voltages directly.

    Example (phase-referred): 76,200 V / 63.5 V
      primary_ll_v  = 76,200 × √3 = 131,982.27... V  (≠ exactly 132,000 V)
      secondary_ll_v = 63.5 × √3  = 109.985... V      (≠ exactly 110 V)

    Example (L-L-referred): 132,000 V / 110 V
      primary_ll_v  = 132,000 V
      secondary_ll_v = 110 V
    """

    primary_winding_v: float
    secondary_winding_v: float
    winding_ref: VtWindingRef


def vt_ratio_valid(ratio: VtRatio) -> bool:
    """True if the ratio carries finite, positive winding values and a known ref."""
    return (
        isinstance(ratio.primary_winding_v, (int, float))
        and not isinstance(ratio.primary_winding_v, bool)
        and math.isfinite(ratio.primary_winding_v)
        and ratio.primary_winding_v > 0
        and isinstance(ratio.secondary_winding_v, (int, float))
        and not isinstance(ratio.secondary_winding_v, bool)
        and math.isfinite(ratio.secondary_winding_v)
        and ratio.secondary_winding_v > 0
        and ratio.winding_ref in KNOWN_VT_WINDING_REFS
    )


def vt_primary_ll_v(ratio: VtRatio) -> float:
    """Derive the primary-side LINE-TO-LINE equivalent voltage in Volts.

    For phase-referred windings: multiply by √3.
    For L-L-referred windings: return directly.

    Does NOT silently round — 76,200 × √3 = 131,982.277... V, not 132,000 V.
    """
    if ratio.winding_ref == VT_WINDING_PHASE:
        return ratio.primary_winding_v * SQRT_3
    return ratio.primary_winding_v  # already L-L


def vt_secondary_ll_v(ratio: VtRatio) -> float:
    """Derive the secondary-side LINE-TO-LINE equivalent voltage in Volts.

    For phase-referred windings: multiply by √3.
    For L-L-referred windings: return directly.
    """
    if ratio.winding_ref == VT_WINDING_PHASE:
        return ratio.secondary_winding_v * SQRT_3
    return ratio.secondary_winding_v  # already L-L


def vt_turns_ratio(ratio: VtRatio) -> float:
    """The electrical turns ratio N = primary_winding_v / secondary_winding_v.
    Both in the same winding reference, so the ratio is correct regardless of
    whether phase-referred or L-L-referred.
    """
    return ratio.primary_winding_v / ratio.secondary_winding_v


# ---------------------------------------------------------------------------
# Primary/Secondary resolution result
# ---------------------------------------------------------------------------

# Resolution status values
PS_STATUS_CONFIGURED = "configured"
PS_STATUS_BASE_REQUIRED = "base_required"
PS_STATUS_UNVERIFIED = "unverified"

# Derivation source identifiers
DERIVATION_PRIMARY_NOMINAL = "primary_nominal"
DERIVATION_SECONDARY_CONFIGURED = "secondary_configured"
DERIVATION_SECONDARY_FROM_VT = "secondary_from_vt_ratio"
DERIVATION_UNKNOWN_UNVERIFIED = "unknown_unverified"


@dataclass(slots=True)
class VoltageReferenceSideResolution:
    """The outcome of resolving a voltage denominator for a known measurement side.

    Fields:
      status          — "configured" | "base_required" | "unverified"
      denominator_v   — effective PU denominator in Volts (None if not configured)
      denominator_kv  — denominator in kV (None if not configured)
      measurement_side — primary | secondary | unknown
      representation  — line_to_line | line_to_ground | None
      nominal_primary_ll_kv — the nominal primary system L-L voltage, in kV
      secondary_equivalent_ll_v — the secondary equivalent L-L voltage, in V
                                   (None if not established or not relevant)
      derivation      — how the denominator was obtained
      reason          — why base_required or unverified (None if configured)
    """

    status: str
    denominator_v: float | None
    denominator_kv: float | None
    measurement_side: str
    representation: str | None
    nominal_primary_ll_kv: float | None
    secondary_equivalent_ll_v: float | None
    derivation: str | None
    reason: str | None


# ---------------------------------------------------------------------------
# Core resolver: resolve_ps_voltage_denominator
# ---------------------------------------------------------------------------


def _denominator_from_ll_v(ll_v: float, representation: str) -> float:
    """Return the PU denominator in Volts for a given L-L voltage and representation."""
    if representation == REPR_LINE_TO_GROUND:
        return ll_v / SQRT_3
    return ll_v  # REPR_LINE_TO_LINE


def nominal_voltage_ll_v_valid(value: float | None) -> bool:
    """True if value is a finite, strictly positive number usable as a nominal kV (in kV units)."""
    if value is None or isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0.0


def secondary_voltage_ll_v_valid(value: float | None) -> bool:
    """True if value is a finite, strictly positive number usable as a secondary equivalent V."""
    if value is None or isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value) and value > 0.0


def resolve_ps_voltage_denominator(
    *,
    nominal_primary_ll_kv: float | None,
    secondary_equivalent_ll_v: float | None,
    measurement_side: str,
    representation: str,
) -> VoltageReferenceSideResolution:
    """Resolve the correct PU voltage denominator for a known measurement side.

    Given:
      nominal_primary_ll_kv     — the system nominal primary L-L voltage (in kV)
      secondary_equivalent_ll_v — established secondary equivalent L-L voltage (in V);
                                   None when not known
      measurement_side          — "primary" | "secondary" | "unknown"
      representation            — "line_to_line" | "line_to_ground"

    Returns a VoltageReferenceSideResolution:

    Primary side (Cases A, B):
      - Requires nominal_primary_ll_kv to be valid.
      - Denominator = nominal_primary_ll_kv × 1000 V (L-L) or ÷ √3 (L-G).

    Secondary side (Cases C, D):
      - Requires secondary_equivalent_ll_v to be valid.
      - Denominator = secondary_equivalent_ll_v V (L-L) or ÷ √3 (L-G).
      - Using nominal_primary_ll_kv as the denominator for a secondary measurement
        is WRONG and is NOT done here (see specification §3).

    Unknown side (Case F):
      - Returns "unverified" — the engine MUST NOT silently choose primary or
        secondary for authoritative automatic PU.
      - Existing legacy "unverified" compatibility behavior is preserved by
        the caller; this function never promotes unknown to primary/secondary.

    This function is PURE — no I/O, no registry access, no mutations.
    """
    if representation not in KNOWN_REPRESENTATIONS:
        return VoltageReferenceSideResolution(
            status=PS_STATUS_BASE_REQUIRED,
            denominator_v=None, denominator_kv=None,
            measurement_side=measurement_side,
            representation=representation,
            nominal_primary_ll_kv=nominal_primary_ll_kv,
            secondary_equivalent_ll_v=secondary_equivalent_ll_v,
            derivation=None,
            reason="representation_unknown",
        )

    if measurement_side == SIDE_PRIMARY:
        if not nominal_voltage_ll_v_valid(nominal_primary_ll_kv):
            return VoltageReferenceSideResolution(
                status=PS_STATUS_BASE_REQUIRED,
                denominator_v=None, denominator_kv=None,
                measurement_side=SIDE_PRIMARY,
                representation=representation,
                nominal_primary_ll_kv=nominal_primary_ll_kv,
                secondary_equivalent_ll_v=secondary_equivalent_ll_v,
                derivation=DERIVATION_PRIMARY_NOMINAL,
                reason="primary_nominal_not_configured",
            )
        primary_ll_v = nominal_primary_ll_kv * 1000.0
        denom_v = _denominator_from_ll_v(primary_ll_v, representation)
        return VoltageReferenceSideResolution(
            status=PS_STATUS_CONFIGURED,
            denominator_v=denom_v,
            denominator_kv=denom_v / 1000.0,
            measurement_side=SIDE_PRIMARY,
            representation=representation,
            nominal_primary_ll_kv=nominal_primary_ll_kv,
            secondary_equivalent_ll_v=secondary_equivalent_ll_v,
            derivation=DERIVATION_PRIMARY_NOMINAL,
            reason=None,
        )

    if measurement_side == SIDE_SECONDARY:
        if not secondary_voltage_ll_v_valid(secondary_equivalent_ll_v):
            return VoltageReferenceSideResolution(
                status=PS_STATUS_BASE_REQUIRED,
                denominator_v=None, denominator_kv=None,
                measurement_side=SIDE_SECONDARY,
                representation=representation,
                nominal_primary_ll_kv=nominal_primary_ll_kv,
                secondary_equivalent_ll_v=secondary_equivalent_ll_v,
                derivation=DERIVATION_SECONDARY_CONFIGURED,
                reason="secondary_equivalent_not_configured",
            )
        denom_v = _denominator_from_ll_v(secondary_equivalent_ll_v, representation)
        return VoltageReferenceSideResolution(
            status=PS_STATUS_CONFIGURED,
            denominator_v=denom_v,
            denominator_kv=denom_v / 1000.0,
            measurement_side=SIDE_SECONDARY,
            representation=representation,
            nominal_primary_ll_kv=nominal_primary_ll_kv,
            secondary_equivalent_ll_v=secondary_equivalent_ll_v,
            derivation=DERIVATION_SECONDARY_CONFIGURED,
            reason=None,
        )

    # measurement_side == "unknown" (or anything else) — unverified, never silently choose
    return VoltageReferenceSideResolution(
        status=PS_STATUS_UNVERIFIED,
        denominator_v=None, denominator_kv=None,
        measurement_side=SIDE_UNKNOWN,
        representation=representation,
        nominal_primary_ll_kv=nominal_primary_ll_kv,
        secondary_equivalent_ll_v=secondary_equivalent_ll_v,
        derivation=DERIVATION_UNKNOWN_UNVERIFIED,
        reason="measurement_side_unknown",
    )


def resolve_ps_voltage_denominator_from_vt_ratio(
    *,
    vt_ratio: VtRatio,
    measurement_side: str,
    representation: str,
    nominal_primary_ll_kv: float | None = None,
) -> VoltageReferenceSideResolution:
    """Resolve denominator when a VT ratio is the source of the secondary equivalent.

    Uses vt_secondary_ll_v() to derive the secondary equivalent from the VT ratio,
    then delegates to resolve_ps_voltage_denominator().

    For the primary side, uses vt_primary_ll_v() if no nominal_primary_ll_kv is
    provided, so the VT ratio informs both sides without silent rounding.

    This preserves the Case E distinction: 76,200/63.5 (phase-referred) produces:
      primary_ll_v  = 76,200 × √3 V (≠ 132,000 V)
      secondary_ll_v = 63.5 × √3 V  (≠ 110 V)
    """
    if not vt_ratio_valid(vt_ratio):
        return VoltageReferenceSideResolution(
            status=PS_STATUS_BASE_REQUIRED,
            denominator_v=None, denominator_kv=None,
            measurement_side=measurement_side,
            representation=representation,
            nominal_primary_ll_kv=nominal_primary_ll_kv,
            secondary_equivalent_ll_v=None,
            derivation=DERIVATION_SECONDARY_FROM_VT,
            reason="vt_ratio_invalid",
        )
    if representation not in KNOWN_REPRESENTATIONS:
        return VoltageReferenceSideResolution(
            status=PS_STATUS_BASE_REQUIRED,
            denominator_v=None, denominator_kv=None,
            measurement_side=measurement_side,
            representation=representation,
            nominal_primary_ll_kv=nominal_primary_ll_kv,
            secondary_equivalent_ll_v=None,
            derivation=DERIVATION_SECONDARY_FROM_VT,
            reason="representation_unknown",
        )

    derived_secondary_ll_v = vt_secondary_ll_v(vt_ratio)
    derived_primary_ll_v = vt_primary_ll_v(vt_ratio)
    effective_primary_ll_kv = nominal_primary_ll_kv if nominal_voltage_ll_v_valid(nominal_primary_ll_kv) else derived_primary_ll_v / 1000.0

    if measurement_side == SIDE_SECONDARY:
        denom_v = _denominator_from_ll_v(derived_secondary_ll_v, representation)
        return VoltageReferenceSideResolution(
            status=PS_STATUS_CONFIGURED,
            denominator_v=denom_v,
            denominator_kv=denom_v / 1000.0,
            measurement_side=SIDE_SECONDARY,
            representation=representation,
            nominal_primary_ll_kv=effective_primary_ll_kv,
            secondary_equivalent_ll_v=derived_secondary_ll_v,
            derivation=DERIVATION_SECONDARY_FROM_VT,
            reason=None,
        )

    if measurement_side == SIDE_PRIMARY:
        primary_ll_v = nominal_primary_ll_kv * 1000.0 if nominal_voltage_ll_v_valid(nominal_primary_ll_kv) else derived_primary_ll_v
        denom_v = _denominator_from_ll_v(primary_ll_v, representation)
        return VoltageReferenceSideResolution(
            status=PS_STATUS_CONFIGURED,
            denominator_v=denom_v,
            denominator_kv=denom_v / 1000.0,
            measurement_side=SIDE_PRIMARY,
            representation=representation,
            nominal_primary_ll_kv=effective_primary_ll_kv,
            secondary_equivalent_ll_v=derived_secondary_ll_v,
            derivation=DERIVATION_SECONDARY_FROM_VT,
            reason=None,
        )

    # Unknown side
    return VoltageReferenceSideResolution(
        status=PS_STATUS_UNVERIFIED,
        denominator_v=None, denominator_kv=None,
        measurement_side=SIDE_UNKNOWN,
        representation=representation,
        nominal_primary_ll_kv=effective_primary_ll_kv,
        secondary_equivalent_ll_v=derived_secondary_ll_v,
        derivation=DERIVATION_UNKNOWN_UNVERIFIED,
        reason="measurement_side_unknown",
    )
