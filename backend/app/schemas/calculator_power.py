"""Wire shapes for the Calculator Power endpoint (DEC-PWR Slice 1).

POST /api/v1/calculator/power/single-phase — thin, stateless wrapper over
app.domain.power_calculation.single_phase_power(). No workspace scope.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SinglePhasePowerIn(BaseModel):
    """Request body: RMS phasors in SI base units (volts, amperes, degrees).

    Unit conversion from display units (kV, mA, …) is the caller's
    responsibility before submitting to this endpoint. The validation
    predicates `voltage_magnitude_valid`, `current_magnitude_valid` and
    `angle_deg_valid` from the domain module define the accepted ranges.
    """

    v_magnitude_rms: float = Field(
        ...,
        ge=0.0,
        description="Voltage RMS magnitude in volts (SI). Zero is valid (dead bus).",
    )
    v_angle_deg: float = Field(
        ...,
        description="Voltage phasor angle in degrees. No range restriction.",
    )
    i_magnitude_rms: float = Field(
        ...,
        ge=0.0,
        description="Current RMS magnitude in amperes (SI). Zero is valid (open circuit).",
    )
    i_angle_deg: float = Field(
        ...,
        description=(
            "Current phasor angle in degrees. "
            "Defined as the angle of I flowing INTO the positive terminal "
            "(passive / load sign convention, DEC-PWR-003)."
        ),
    )


class SinglePhasePowerOut(BaseModel):
    """Response: computed complex power quantities and provenance metadata.

    All power values are in SI base units: watts, var, volt-amperes.
    Provenance fields (sign_convention, apparent_power_definition,
    algorithm_version) are always present so consumers never need to
    infer which definition was applied (DEC-PWR-002, DEC-PWR-003).
    """

    p_watts: float
    """Active power P = Re(V × conj(I)), signed (W). Positive = absorbed."""

    q_var: float
    """Reactive power Q = Im(V × conj(I)), signed (var).
    Positive = inductive/lagging. Negative = capacitive/leading."""

    s_va: float
    """Apparent power |S| = √(P² + Q²) (VA, always ≥ 0). Geometric."""

    power_angle_deg: float
    """arg(S) = θV − θI, normalised to (−180, 180] degrees."""

    power_factor: float | None
    """P / S, signed (range [−1, 1]). None when s_va = 0."""

    power_factor_sign: str
    """lagging / leading / unity / undefined (from sign of q_var)."""

    sign_convention: str
    """Always 'passive' (DEC-PWR-003)."""

    apparent_power_definition: str
    """Always 'geometric_fundamental_complex' (DEC-PWR-002)."""

    algorithm_version: str
    """Implementation version tag from the domain module."""
