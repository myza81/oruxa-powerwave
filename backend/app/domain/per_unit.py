"""Per-Unit Measurement Mode domain model (Phase 5C, DEC-049).

A per-unit base profile is a workspace-scoped set of Voltage/Current/
apparent-power bases an engineer assigns to Voltage and Current channels
so the Waveform page can display measured values as a fraction of that
base (`measured / base`) instead of raw engineering units. This module
owns the pure, framework-free pieces: the profile record, its own
validators, base-derivation math (including the current-base-from-Vbase/
Sbase formula), the per-channel eligibility+resolution decision, the
actual value/array conversion, and the calculated-channel inheritance
rule. Zero framework dependencies, matching every other app.domain
module's own layering contract.

Orchestration (resolving a channel's assigned profile against the live
`PerUnitRegistry`, wiring `unit_mode` into the display/measurement
endpoints, running the inheritance-recompute cascade when a dependency's
own profile changes) lives in app.services.per_unit_registry -- this
module never touches a registry or raises an HTTP-mappable error itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.domain.calculated_channel import (
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
    ChannelRef,
)
from app.domain.channel_classification import CURRENT, VOLTAGE

SQRT_3 = 1.7320508075688772

VOLTAGE_BASIS_LINE_TO_LINE = "line_to_line"
VOLTAGE_BASIS_LINE_TO_NEUTRAL = "line_to_neutral"
KNOWN_VOLTAGE_BASES = (VOLTAGE_BASIS_LINE_TO_LINE, VOLTAGE_BASIS_LINE_TO_NEUTRAL)

#: "none" is a profile's initial state -- Voltage/Current channels may
#: still be assigned to it (decision 4 does not gate assignment on a
#: configured base), but every such channel resolves `base_required`
#: until a current base mode is actually chosen (section 16-19).
CURRENT_BASE_MODE_NONE = "none"
CURRENT_BASE_MODE_DERIVED = "derived"
CURRENT_BASE_MODE_DIRECT = "direct"
KNOWN_CURRENT_BASE_MODES = (CURRENT_BASE_MODE_NONE, CURRENT_BASE_MODE_DERIVED, CURRENT_BASE_MODE_DIRECT)

#: Section 23 -- the minimal explicit unit-normalization set. Anything
#: else (a measured or base unit outside these keys) is never guessed;
#: convert_value_to_pu()/convert_array_to_pu() return None for it.
VOLTAGE_UNIT_SCALE: dict[str, float] = {"v": 1.0, "kv": 1000.0}
CURRENT_UNIT_SCALE: dict[str, float] = {"a": 1.0, "ka": 1000.0}
APPARENT_POWER_UNIT_SCALE: dict[str, float] = {"mva": 1_000_000.0}

STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_CONFIGURED = "configured"
STATUS_BASE_REQUIRED = "base_required"


@dataclass(slots=True)
class PerUnitBaseProfile:
    """One workspace-scoped base profile (section 6-19 of the owner's
    spec). `assigned_channels` is this profile's own denormalized view of
    channel ownership -- see app.services.per_unit_registry's own module
    docstring for the invariant that this list and the registry's reverse
    index must never diverge.
    """

    id: str
    workspace_id: str
    name: str
    voltage_base_value: float | None
    voltage_base_unit: str | None
    voltage_basis: str
    apparent_power_base_value: float | None
    apparent_power_base_unit: str | None
    current_base_mode: str
    direct_current_base_value: float | None
    direct_current_base_unit: str | None
    assigned_channels: list[ChannelRef] = field(default_factory=list)
    created_at: datetime | None = None


def voltage_base_valid(value: float | None, unit: str | None) -> bool:
    """Section 15: a configured voltage base must be a finite, strictly
    positive number in a recognized unit. `None`/`None` (not yet
    configured) is a separate, valid state -- callers check for that
    first; this only validates an attempt to actually set one."""
    if value is None or unit is None:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        return False
    return unit.strip().lower() in VOLTAGE_UNIT_SCALE


def apparent_power_base_valid(value: float | None, unit: str | None) -> bool:
    """Section 17: same shape as voltage_base_valid(), for the
    "Three-Phase MVA Base (Sbase)" field."""
    if value is None or unit is None:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        return False
    return unit.strip().lower() in APPARENT_POWER_UNIT_SCALE


def direct_current_base_valid(value: float | None, unit: str | None) -> bool:
    """Section 18: same shape, for the Direct current-base mode."""
    if value is None or unit is None:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        return False
    return unit.strip().lower() in CURRENT_UNIT_SCALE


def voltage_base_volts(profile: PerUnitBaseProfile) -> float | None:
    """The profile's own declared voltage base, normalized to volts.
    `None` if no voltage base is configured yet."""
    if profile.voltage_base_value is None or profile.voltage_base_unit is None:
        return None
    scale = VOLTAGE_UNIT_SCALE.get(profile.voltage_base_unit.strip().lower())
    if scale is None:
        return None
    return profile.voltage_base_value * scale


def apparent_power_base_va(profile: PerUnitBaseProfile) -> float | None:
    """The profile's own declared three-phase apparent power base,
    normalized to volt-amperes. `None` if not configured."""
    if profile.apparent_power_base_value is None or profile.apparent_power_base_unit is None:
        return None
    scale = APPARENT_POWER_UNIT_SCALE.get(profile.apparent_power_base_unit.strip().lower())
    if scale is None:
        return None
    return profile.apparent_power_base_value * scale


def voltage_base_ll_volts(profile: PerUnitBaseProfile) -> float | None:
    """Decision 3: the profile's own voltage base normalized to
    line-to-line volts -- applies `x sqrt(3)` ONLY here, when a
    line-to-neutral base must be converted for the `Ibase = Sbase /
    (sqrt(3) x Vbase_LL)` derivation below. This is never applied to a
    measured channel's own per-unit division, which is always a direct
    `measured / base` (see convert_value_to_pu())."""
    volts = voltage_base_volts(profile)
    if volts is None:
        return None
    if profile.voltage_basis == VOLTAGE_BASIS_LINE_TO_NEUTRAL:
        return volts * SQRT_3
    return volts


def resolve_current_base_amps(profile: PerUnitBaseProfile) -> tuple[float | None, str | None]:
    """Resolve this profile's own current base, in amps -- `(amps, None)`
    on success, `(None, reason)` when the current base cannot yet be
    resolved (section 16-19: never a guess, always an explicit reason a
    caller can surface as "Base required")."""
    if profile.current_base_mode == CURRENT_BASE_MODE_NONE:
        return None, "current_base_not_configured"
    if profile.current_base_mode == CURRENT_BASE_MODE_DIRECT:
        if not direct_current_base_valid(profile.direct_current_base_value, profile.direct_current_base_unit):
            return None, "current_base_not_configured"
        scale = CURRENT_UNIT_SCALE[profile.direct_current_base_unit.strip().lower()]
        return profile.direct_current_base_value * scale, None
    # CURRENT_BASE_MODE_DERIVED: Ibase = Sbase / (sqrt(3) x Vbase_LL).
    sbase_va = apparent_power_base_va(profile)
    vbase_ll = voltage_base_ll_volts(profile)
    if sbase_va is None or vbase_ll is None:
        return None, "current_base_not_configured"
    return sbase_va / (SQRT_3 * vbase_ll), None


@dataclass(slots=True)
class PerUnitResolution:
    """The outcome of resolving one channel's per-unit eligibility+base --
    the SOLE authority every display/measurement endpoint consults
    (section 55/56: one shared function, never duplicated per endpoint)."""

    status: str  # STATUS_NOT_APPLICABLE | STATUS_CONFIGURED | STATUS_BASE_REQUIRED
    profile_id: str | None
    profile_name: str | None
    base_amount: float | None
    base_unit: str | None
    reason: str | None


def resolve_per_unit(engineering_type: str, profile: PerUnitBaseProfile | None) -> PerUnitResolution:
    """Section 20-24: Voltage/Current channels only in this phase --
    every other engineering_type is `not_applicable`, unaffected by
    per-unit mode regardless of profile assignment. An eligible channel
    with no assigned profile, or an assigned profile whose relevant base
    is not yet configured, is `base_required` -- never silently left in
    engineering units without saying so."""
    if engineering_type not in (VOLTAGE, CURRENT):
        return PerUnitResolution(
            status=STATUS_NOT_APPLICABLE, profile_id=None, profile_name=None,
            base_amount=None, base_unit=None, reason=None,
        )
    if profile is None:
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=None, profile_name=None,
            base_amount=None, base_unit=None, reason="no_profile_assigned",
        )
    if engineering_type == VOLTAGE:
        amount = voltage_base_volts(profile)
        if amount is None:
            return PerUnitResolution(
                status=STATUS_BASE_REQUIRED, profile_id=profile.id, profile_name=profile.name,
                base_amount=None, base_unit=None, reason="voltage_base_not_configured",
            )
        return PerUnitResolution(
            status=STATUS_CONFIGURED, profile_id=profile.id, profile_name=profile.name,
            base_amount=amount, base_unit="V", reason=None,
        )
    # CURRENT
    amount, reason = resolve_current_base_amps(profile)
    if amount is None:
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=profile.id, profile_name=profile.name,
            base_amount=None, base_unit=None, reason=reason,
        )
    return PerUnitResolution(
        status=STATUS_CONFIGURED, profile_id=profile.id, profile_name=profile.name,
        base_amount=amount, base_unit="A", reason=None,
    )


def _measured_unit_scale(engineering_type: str, measured_unit: str | None) -> float | None:
    if not measured_unit:
        return None
    key = measured_unit.strip().lower()
    if engineering_type == VOLTAGE:
        return VOLTAGE_UNIT_SCALE.get(key)
    if engineering_type == CURRENT:
        return CURRENT_UNIT_SCALE.get(key)
    return None


def convert_value_to_pu(
    value: float | None, measured_unit: str | None, resolution: PerUnitResolution, engineering_type: str
) -> float | None:
    """`measured / base`, always a direct division -- decision 3: never
    an automatic sqrt(3) factor here, regardless of the profile's own
    voltage basis (that basis only ever affects how Ibase is DERIVED, in
    voltage_base_ll_volts() above). Returns `None` (never guesses) when
    the value is missing/non-finite, the resolution is not `configured`,
    or the measured unit is not one of the minimal recognized set
    (section 23) -- a caller must fall back to the engineering value in
    every such case."""
    if value is None or not np.isfinite(value):
        return None
    if resolution.status != STATUS_CONFIGURED or resolution.base_amount is None:
        return None
    scale = _measured_unit_scale(engineering_type, measured_unit)
    if scale is None:
        return None
    return (value * scale) / resolution.base_amount


def convert_array_to_pu(
    values: np.ndarray, measured_unit: str | None, resolution: PerUnitResolution, engineering_type: str
) -> np.ndarray | None:
    """Array counterpart of convert_value_to_pu() -- same unit-
    normalization/eligibility rules, vectorized. Non-finite input samples
    remain non-finite (NaN) after conversion, never coerced."""
    if resolution.status != STATUS_CONFIGURED or resolution.base_amount is None:
        return None
    scale = _measured_unit_scale(engineering_type, measured_unit)
    if scale is None:
        return None
    return (values.astype(np.float64) * scale) / resolution.base_amount


def apply_per_unit_to_value(
    value: float | None, measured_unit: str | None, engineering_type: str, resolution: PerUnitResolution | None
) -> tuple[float | None, str | None, str | None]:
    """Section 55/56: the ONE place a display/measurement endpoint decides
    what to actually show for one scalar value -- `(display_value,
    display_unit, per_unit_status)`. `resolution=None` means "per-unit
    mode was not requested" -- passes the engineering value/unit through
    unchanged, with a `None` status (distinct from `not_applicable`,
    which means "per-unit mode IS active but this channel type is
    exempt"). When `resolution.status == STATUS_CONFIGURED` but the
    measured channel's own unit is not one of the minimal recognized set
    (decision 5), conversion silently fails closed: the display falls
    back to the engineering value/unit with status downgraded to
    `STATUS_BASE_REQUIRED` (decision 5's "treated as base_required-
    equivalent"), never a partially-converted or fabricated result.

    Deliberately determines `display_unit`/`per_unit_status` from the
    MEASURED UNIT alone, never from whether `value` itself happens to be
    present/finite -- a batch endpoint (A/B cursor values, where cursor B
    may simply not have been requested) must report the SAME status for
    a channel regardless of which of two sibling calls (A, then B) a
    caller happens to make; only the returned number itself is `None`/
    unconverted when `value` is missing.
    """
    if resolution is None:
        return value, measured_unit, None
    if resolution.status != STATUS_CONFIGURED:
        return value, measured_unit, resolution.status
    scale = _measured_unit_scale(engineering_type, measured_unit)
    if scale is None:
        return value, measured_unit, STATUS_BASE_REQUIRED
    if value is None or not np.isfinite(value):
        return None, "pu", STATUS_CONFIGURED
    return (value * scale) / resolution.base_amount, "pu", STATUS_CONFIGURED


def apply_per_unit_to_array(
    values: np.ndarray, measured_unit: str | None, engineering_type: str, resolution: PerUnitResolution | None
) -> tuple[np.ndarray, str | None, str | None]:
    """Array counterpart of apply_per_unit_to_value() -- same fallback
    rules, for a whole waveform-range response."""
    if resolution is None:
        return values, measured_unit, None
    if resolution.status != STATUS_CONFIGURED:
        return values, measured_unit, resolution.status
    converted = convert_array_to_pu(values, measured_unit, resolution, engineering_type)
    if converted is None:
        return values, measured_unit, STATUS_BASE_REQUIRED
    return converted, "pu", STATUS_CONFIGURED


#: Decision 6 -- unary operations whose output verbatim-inherits the
#: single input's own resolved profile (including `None`).
_INHERIT_VERBATIM_OPERATIONS = frozenset(
    {OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS}
)
#: Multi-input operations that inherit only when every input resolves to
#: the exact same known profile id.
_INHERIT_IF_UNANIMOUS_OPERATIONS = frozenset({OP_ADDITION, OP_SUBTRACTION})


def derive_per_unit_profile_id(operation: str, input_profile_ids: list[str | None]) -> str | None:
    """Decision 6, locked before Slice F: the calculated-channel
    per-unit-profile inheritance rule.

    - Reverse Polarity, Absolute Value, Multiply by Constant, RMS: the
      single input's own resolved profile, verbatim (including `None`).
    - Addition, Subtraction: the shared profile ONLY when every input
      resolves to the exact same known (non-`None`) profile id;
      otherwise `None` -- never an arbitrary pick among candidates.
    - Calculated-from-calculated inputs pass their own already-resolved
      profile id straight in here, so this composes transitively through
      arbitrarily deep chains with no separate recursive logic (same
      trick as derive_engineering_type()).

    Called once, at calculated-channel creation time, to seed that
    channel's `mode="auto"` assignment record (decision 7) -- never
    called again for that same creation; subsequent changes are handled
    by the recompute-on-parent-change cascade in
    app.services.per_unit_registry.
    """
    if operation in _INHERIT_VERBATIM_OPERATIONS:
        return input_profile_ids[0] if input_profile_ids else None
    if operation in _INHERIT_IF_UNANIMOUS_OPERATIONS:
        if not input_profile_ids or input_profile_ids[0] is None:
            return None
        first = input_profile_ids[0]
        return first if all(p == first for p in input_profile_ids) else None
    return None
