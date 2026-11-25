"""PU-MIG S2, decision D-4 (option P5): a read-only diagnostic for a stored secondary base that disagrees with the one
derivable from the group's nominal voltage and its VT.

`secondary_voltage_ll_v` (a stored base) and `nominal_voltage_ll_kv x 1000 / VT ratio` (a derived one) can describe different
voltages (for example a VT rating written by the auto-base service against an engineer's nominal). P5 reports the difference and
changes nothing: the stored value is never replaced, no base is selected here, and no denominator is computed from the result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.auto_nominal_vt import AUTO_NOMINAL_VT_SECONDARY_V
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.domain.voltage_primary_secondary import secondary_voltage_ll_v_valid

#: Relative difference below which two secondary bases are the same voltage (float noise, never an engineering tolerance).
DISCREPANCY_RELATIVE_THRESHOLD = 1e-6
DIAGNOSTIC_STORED_SECONDARY_DIFFERS = "stored_secondary_differs_from_derived"


@dataclass(frozen=True, slots=True)
class SecondaryBaseDiscrepancy:
    code: str
    stored_secondary_ll_v: float
    derived_secondary_ll_v: float
    relative_difference: float
    #: Where the ratio the derived value uses comes from: `stored_vt` or `auto_nominal` (110 V secondary default).
    derivation: str


def secondary_base_discrepancy(config: VoltageBaseConfiguration | None) -> SecondaryBaseDiscrepancy | None:
    """The stored-versus-derived discrepancy of one Voltage group, or None when there is nothing to compare or they agree.
    Pure; reads the configuration only."""
    if config is None or not secondary_voltage_ll_v_valid(config.secondary_voltage_ll_v):
        return None
    nominal = config.nominal_voltage_ll_kv
    if not isinstance(nominal, (int, float)) or isinstance(nominal, bool) or not math.isfinite(nominal) or nominal <= 0:
        return None
    ratio = config.vt_ratio
    if ratio is not None and math.isfinite(ratio) and ratio > 0:
        derived, derivation = nominal * 1000.0 / ratio, "stored_vt"
    else:
        derived, derivation = AUTO_NOMINAL_VT_SECONDARY_V, "auto_nominal"
    stored = float(config.secondary_voltage_ll_v)
    if not (math.isfinite(derived) and derived > 0):
        return None
    difference = abs(stored - derived) / derived
    if difference <= DISCREPANCY_RELATIVE_THRESHOLD:
        return None
    return SecondaryBaseDiscrepancy(DIAGNOSTIC_STORED_SECONDARY_DIFFERS, stored, derived, difference, derivation)
