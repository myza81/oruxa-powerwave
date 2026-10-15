"""Equipment Loading -> equivalent primary current (balanced three-phase).

An INPUT-CONVERSION capability only (see docs/project-memory/
OVERCURRENT_ANALYSIS.md, "Equipment Loading input method"): it turns an
equipment rating, a loading percentage and a nominal line-to-line system
voltage into the equivalent primary line current an analyzer can then
evaluate through its OWN existing pipeline. It never evaluates a
protection characteristic, never applies a CT ratio, and never knows
which analyzer consumes it -- Overcurrent's Manual Input mode is the first
consumer, routing the result through the unchanged
`convert_to_relay_secondary()` / `evaluate_multiple_and_operating_time()`
path exactly like a directly-entered primary current.

    S_actual_MVA = S_rated_MVA * Loading_Percent / 100
    I_primary_A  = (S_actual_MVA * 1000) / (sqrt(3) * V_LL_kV)

`MVA / kV` yields kA (`MVA = sqrt(3) * kV * kA`), hence the `* 1000` to
amperes. Balanced three-phase loading is assumed; the result is the line
current magnitude. Loading above 100 % is deliberately allowed (overload
studies are the point of the feature) -- only blank/NaN/Infinity/
negative/zero inputs are rejected.

Kept separate from `app.domain.current_group_config.equipment_rating_
ibase_ka()`, which applies the same S/(sqrt(3) V) relation to derive a
Per-Unit CURRENT BASE: that module belongs to the Per-Unit measurement
model and its own governance, and a protection what-if conversion must
not couple to (or be changed by) Per-Unit base resolution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SQRT_3 = math.sqrt(3.0)


def positive_finite(value: float) -> bool:
    return math.isfinite(value) and value > 0.0


@dataclass(frozen=True, slots=True)
class EquipmentLoadingCurrent:
    """The echoed inputs plus the two derived quantities. Never
    persisted."""

    equipment_rating_mva: float
    loading_percent: float
    system_voltage_kv: float
    actual_loading_mva: float
    primary_current_a: float


def actual_loading_mva(equipment_rating_mva: float, loading_percent: float) -> float:
    return equipment_rating_mva * loading_percent / 100.0


def three_phase_line_current_a(apparent_power_mva: float, system_voltage_ll_kv: float) -> float:
    return apparent_power_mva * 1000.0 / (SQRT_3 * system_voltage_ll_kv)


def equipment_loading_to_primary_current(
    equipment_rating_mva: float, loading_percent: float, system_voltage_kv: float,
) -> EquipmentLoadingCurrent:
    """Caller validates every input with `positive_finite()` first."""
    actual_mva = actual_loading_mva(equipment_rating_mva, loading_percent)
    return EquipmentLoadingCurrent(
        equipment_rating_mva=equipment_rating_mva,
        loading_percent=loading_percent,
        system_voltage_kv=system_voltage_kv,
        actual_loading_mva=actual_mva,
        primary_current_a=three_phase_line_current_a(actual_mva, system_voltage_kv),
    )
