"""Calculator API — stateless mathematical operations (DEC-PWR Slice 1).

No workspace scope. No persistence. Pure domain-function wrappers that let
the frontend reuse Python domain logic without reimplementing formulas in
JavaScript.

Current endpoints
-----------------
POST /api/v1/calculator/power/single-phase
    Single-phase complex power from two RMS phasors (DEC-PWR-001 through -003,
    DEC-PWR-005). Wraps app.domain.power_calculation.single_phase_power().
"""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, status

from app.domain.power_calculation import (
    angle_deg_valid,
    current_magnitude_valid,
    single_phase_power,
    voltage_magnitude_valid,
)
from app.schemas.calculator_power import SinglePhasePowerIn, SinglePhasePowerOut

router = APIRouter(prefix="/api/v1/calculator", tags=["calculator"])


@router.post(
    "/power/single-phase",
    response_model=SinglePhasePowerOut,
    summary="Single-phase complex power from V and I phasors",
    description=(
        "Computes P, Q, S, power angle and power factor from one voltage "
        "and one current RMS phasor pair. Passive sign convention "
        "(DEC-PWR-003): S = V × conj(I) = P + jQ. Apparent power is the "
        "geometric magnitude |S| = √(P² + Q²) (DEC-PWR-002). "
        "All magnitudes must be in SI base units (V, A). "
        "Angle wrapping and zero-current / zero-voltage conditions are "
        "handled gracefully."
    ),
)
def compute_single_phase_power(body: SinglePhasePowerIn) -> SinglePhasePowerOut:
    """Validate inputs and delegate to the domain module."""
    if not voltage_magnitude_valid(body.v_magnitude_rms):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voltage magnitude must be finite and non-negative.",
        )
    if not current_magnitude_valid(body.i_magnitude_rms):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Current magnitude must be finite and non-negative.",
        )
    if not angle_deg_valid(body.v_angle_deg):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voltage angle must be a finite number.",
        )
    if not angle_deg_valid(body.i_angle_deg):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Current angle must be a finite number.",
        )

    result = single_phase_power(
        body.v_magnitude_rms,
        body.v_angle_deg,
        body.i_magnitude_rms,
        body.i_angle_deg,
    )

    # Guard: domain result must be finite (defence against edge-case overflow).
    if not all(math.isfinite(x) for x in (result.p_watts, result.q_var, result.s_va, result.power_angle_deg)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Result is out of range for the given inputs.",
        )

    return SinglePhasePowerOut(
        p_watts=result.p_watts,
        q_var=result.q_var,
        s_va=result.s_va,
        power_angle_deg=result.power_angle_deg,
        power_factor=result.power_factor,
        power_factor_sign=result.power_factor_sign,
        sign_convention=result.sign_convention,
        apparent_power_definition=result.apparent_power_definition,
        algorithm_version=result.algorithm_version,
    )
