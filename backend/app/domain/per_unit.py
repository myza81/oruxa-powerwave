"""Per-Unit Measurement Mode domain model (Phase 5C, DEC-049; source-
bound redesign, DEC-049 addendum, following owner UAT).

A per-unit base configuration is a workspace-scoped set of Voltage/
Current/apparent-power bases owned by exactly ONE source (never a
separate, independently-named "profile" the engineer creates/assigns --
owner UAT on the original design found that workflow too complex). Every
Voltage/Current channel belonging to that source automatically uses its
own source's configuration -- no per-channel assignment step exists or
is needed. This module owns the pure, framework-free pieces: the config
record, its own validators, base-derivation math (including the
current-base-from-Vbase/Sbase formula and the Ibase = Sbase / (sqrt(3) x
Vbase_LL) formula's own voltage-reference dependency), the per-channel
eligibility+resolution decision, the actual value/array conversion, and
the calculated-channel inheritance rule. Zero framework dependencies,
matching every other app.domain module's own layering contract.

Base VALUES are stored in a single canonical unit each (Voltage Base:
kV, Direct Current Base: kA, Apparent Power Base: MVA) -- the owner's
own UAT feedback explicitly preferred a non-editable unit suffix over an
unnecessary unit dropdown once the domain always accepts one canonical
unit. This is UNRELATED to a MEASURED channel's own declared unit (which
may still be V, kV, A, or kA) -- see convert_value_to_pu()/
convert_array_to_pu() below, completely unchanged by this addendum.

Orchestration (resolving a channel's owning source's configuration
against the live `PerUnitRegistry`, wiring `unit_mode` into the display/
measurement endpoints, running the calculated-channel inheritance-
recompute cascade) lives in app.services.per_unit_registry -- this
module never touches a registry or raises an HTTP-mappable error itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.domain.calculated_channel import (
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
)
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.voltage_reference import (
    KNOWN_VOLTAGE_REFERENCES,
    LINE_TO_GROUND,
    REASON_MANUAL_OVERRIDE,
    VoltageReferenceDetection,
    detect_voltage_reference,
)

SQRT_3 = 1.7320508075688772

#: "none" is a configuration's initial state -- Current channels of that
#: source stay `base_required` until a current base mode is actually
#: chosen. Renamed for the setup UI (owner UAT, section 11) to "Voltage
#: only" / "Enter current base manually" / "Calculate from apparent
#: power" -- the backend values themselves are unchanged, only their
#: presentation.
CURRENT_BASE_MODE_NONE = "none"
CURRENT_BASE_MODE_DERIVED = "derived"
CURRENT_BASE_MODE_DIRECT = "direct"
KNOWN_CURRENT_BASE_MODES = (CURRENT_BASE_MODE_NONE, CURRENT_BASE_MODE_DERIVED, CURRENT_BASE_MODE_DIRECT)

VOLTAGE_REFERENCE_MODE_AUTO = "auto"
VOLTAGE_REFERENCE_MODE_MANUAL = "manual"
KNOWN_VOLTAGE_REFERENCE_MODES = (VOLTAGE_REFERENCE_MODE_AUTO, VOLTAGE_REFERENCE_MODE_MANUAL)

STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_CONFIGURED = "configured"
STATUS_BASE_REQUIRED = "base_required"

#: Section 23 (unchanged) -- the minimal explicit unit-normalization set
#: for a MEASURED channel's own declared unit. Anything else (a measured
#: unit outside these keys) is never guessed; convert_value_to_pu()/
#: convert_array_to_pu() return None for it. NOT used for the base
#: fields themselves any more (those are canonical, see module
#: docstring) -- still used here for the measured-channel side of the
#: division, unchanged from the original DEC-049 implementation.
VOLTAGE_UNIT_SCALE: dict[str, float] = {"v": 1.0, "kv": 1000.0}
CURRENT_UNIT_SCALE: dict[str, float] = {"a": 1.0, "ka": 1000.0}


@dataclass(slots=True)
class PerUnitBaseProfile:
    """One source's own Per-Unit base configuration -- keyed 1:1 by
    `source_id` (never a separate, independently-assigned identity; see
    module docstring). No `assigned_channels` field exists any more --
    every Voltage/Current channel OF this source automatically resolves
    to it (app.services.per_unit_registry.profile_for_channel()), so
    there is nothing to keep in sync/no denormalized ownership list to
    diverge.
    """

    source_id: str
    workspace_id: str
    voltage_base_value: float | None  # kV, canonical
    voltage_reference_mode: str  # "auto" | "manual"
    voltage_reference_override: str | None  # only meaningful when mode == "manual"
    current_base_mode: str
    apparent_power_base_value: float | None  # MVA, canonical
    direct_current_base_value: float | None  # kA, canonical
    created_at: datetime | None = None


def voltage_base_valid(value: float | None) -> bool:
    """A configured voltage base must be a finite, strictly positive
    number (canonical kV). `None` (not yet configured) is a separate,
    valid state -- callers check for that first; this only validates an
    attempt to actually set one."""
    if value is None:
        return False
    return bool(not isinstance(value, bool) and isinstance(value, (int, float)) and np.isfinite(value) and value > 0)


def apparent_power_base_valid(value: float | None) -> bool:
    """Same shape as voltage_base_valid(), for the "Three-Phase MVA Base
    (Sbase)" field (canonical MVA)."""
    return voltage_base_valid(value)


def direct_current_base_valid(value: float | None) -> bool:
    """Same shape, for the Direct current-base mode (canonical kA)."""
    return voltage_base_valid(value)


def voltage_base_volts(profile: PerUnitBaseProfile) -> float | None:
    """The source's own declared voltage base, normalized to volts.
    `None` if no voltage base is configured yet."""
    if profile.voltage_base_value is None:
        return None
    return profile.voltage_base_value * 1000.0


def apparent_power_base_va(profile: PerUnitBaseProfile) -> float | None:
    """The source's own declared three-phase apparent power base,
    normalized to volt-amperes. `None` if not configured."""
    if profile.apparent_power_base_value is None:
        return None
    return profile.apparent_power_base_value * 1_000_000.0


def resolve_effective_voltage_reference(
    profile: PerUnitBaseProfile | None, voltage_channel_names: list[str]
) -> VoltageReferenceDetection:
    """Section 7/8 of the owner's UAT spec: in `"manual"` mode, the
    engineer's own explicit override is authoritative -- no detection
    ever runs. In `"auto"` mode (the default, including when no
    configuration exists yet at all), the reference is NEVER a stored
    value -- it is re-derived live from the source's own CURRENT Voltage
    channel names every time it is needed, so "Return to Auto" (section
    8) always reruns/reapplies the algorithm rather than resurrecting a
    stale cached result.
    """
    if profile is not None and profile.voltage_reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL:
        if profile.voltage_reference_override in KNOWN_VOLTAGE_REFERENCES:
            return VoltageReferenceDetection(
                reference=profile.voltage_reference_override, evidence_names=[], reason=REASON_MANUAL_OVERRIDE
            )
    return detect_voltage_reference(voltage_channel_names)


def voltage_base_ll_volts(profile: PerUnitBaseProfile, effective_reference: str | None) -> float | None:
    """Decision 3 (unchanged invariant): the source's own voltage base
    normalized to line-to-line volts -- applies `x sqrt(3)` ONLY here,
    when a line-to-ground base must be converted for the `Ibase = Sbase
    / (sqrt(3) x Vbase_LL)` derivation below. This is NEVER applied to a
    measured channel's own per-unit division, which is always a direct
    `measured / base` (see convert_value_to_pu())."""
    volts = voltage_base_volts(profile)
    if volts is None:
        return None
    if effective_reference == LINE_TO_GROUND:
        return volts * SQRT_3
    return volts


def resolve_current_base_amps(
    profile: PerUnitBaseProfile, effective_reference: str | None
) -> tuple[float | None, str | None]:
    """Resolve this source's own current base, in amps -- `(amps, None)`
    on success, `(None, reason)` when the current base cannot yet be
    resolved (never a guess, always an explicit reason a caller can
    surface as "Base required"). `effective_reference` is resolved by
    the caller via resolve_effective_voltage_reference() -- this function
    stays a pure consumer of an already-decided reference, never running
    detection itself."""
    if profile.current_base_mode == CURRENT_BASE_MODE_NONE:
        return None, "current_base_not_configured"
    if profile.current_base_mode == CURRENT_BASE_MODE_DIRECT:
        if not direct_current_base_valid(profile.direct_current_base_value):
            return None, "current_base_not_configured"
        return profile.direct_current_base_value * 1000.0, None
    # CURRENT_BASE_MODE_DERIVED: Ibase = Sbase / (sqrt(3) x Vbase_LL).
    if effective_reference not in KNOWN_VOLTAGE_REFERENCES:
        return None, "voltage_reference_undetermined"
    sbase_va = apparent_power_base_va(profile)
    vbase_ll = voltage_base_ll_volts(profile, effective_reference)
    if sbase_va is None or vbase_ll is None:
        return None, "current_base_not_configured"
    return sbase_va / (SQRT_3 * vbase_ll), None


@dataclass(slots=True)
class PerUnitResolution:
    """The outcome of resolving one channel's per-unit eligibility+base --
    the SOLE authority every display/measurement endpoint consults (one
    shared function, never duplicated per endpoint). `profile_id` here is
    always a `source_id` (the source whose configuration applies) --
    kept as `profile_id` rather than renamed, since it is also what a
    calculated channel's own inherited value composes through
    (derive_per_unit_profile_id() below), unchanged from the original
    DEC-049 implementation."""

    status: str  # STATUS_NOT_APPLICABLE | STATUS_CONFIGURED | STATUS_BASE_REQUIRED
    profile_id: str | None
    base_amount: float | None
    base_unit: str | None
    reason: str | None


def resolve_per_unit(
    engineering_type: str,
    profile: PerUnitBaseProfile | None,
    voltage_channel_names: list[str] | None = None,
) -> PerUnitResolution:
    """Voltage/Current channels only in this phase -- every other
    engineering_type is `not_applicable`, unaffected by per-unit mode
    regardless of configuration. An eligible channel whose owning source
    has no configuration, or whose configuration's relevant base is not
    yet resolvable, is `base_required` -- never silently left in
    engineering units without saying so.

    `voltage_channel_names` is the OWNING SOURCE's own full list of
    Voltage-classified channel names -- only consulted for `CURRENT`
    channels under `current_base_mode == "derived"`, to resolve the
    effective voltage reference (auto-detected or manually overridden).
    Callers resolve this once per source per request (see
    app.api.v1.sources/app.api.v1.calculated_channels), not per channel.
    """
    if engineering_type not in (VOLTAGE, CURRENT):
        return PerUnitResolution(status=STATUS_NOT_APPLICABLE, profile_id=None, base_amount=None, base_unit=None, reason=None)
    if profile is None:
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=None, base_amount=None, base_unit=None, reason="not_configured"
        )
    if engineering_type == VOLTAGE:
        amount = voltage_base_volts(profile)
        if amount is None:
            return PerUnitResolution(
                status=STATUS_BASE_REQUIRED, profile_id=profile.source_id, base_amount=None, base_unit=None,
                reason="voltage_base_not_configured",
            )
        return PerUnitResolution(status=STATUS_CONFIGURED, profile_id=profile.source_id, base_amount=amount, base_unit="V", reason=None)
    # CURRENT
    detection = resolve_effective_voltage_reference(profile, voltage_channel_names or [])
    amount, reason = resolve_current_base_amps(profile, detection.reference)
    if amount is None:
        return PerUnitResolution(
            status=STATUS_BASE_REQUIRED, profile_id=profile.source_id, base_amount=None, base_unit=None, reason=reason
        )
    return PerUnitResolution(status=STATUS_CONFIGURED, profile_id=profile.source_id, base_amount=amount, base_unit="A", reason=None)


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
    an automatic sqrt(3) factor here, regardless of the source's own
    voltage reference (that reference only ever affects how Ibase is
    DERIVED, in voltage_base_ll_volts() above). Returns `None` (never
    guesses) when the value is missing/non-finite, the resolution is not
    `configured`, or the measured unit is not one of the minimal
    recognized set -- a caller must fall back to the engineering value
    in every such case. Unchanged from the original DEC-049
    implementation."""
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
    remain non-finite (NaN) after conversion, never coerced. Unchanged
    from the original DEC-049 implementation."""
    if resolution.status != STATUS_CONFIGURED or resolution.base_amount is None:
        return None
    scale = _measured_unit_scale(engineering_type, measured_unit)
    if scale is None:
        return None
    return (values.astype(np.float64) * scale) / resolution.base_amount


def apply_per_unit_to_value(
    value: float | None, measured_unit: str | None, engineering_type: str, resolution: PerUnitResolution | None
) -> tuple[float | None, str | None, str | None]:
    """The ONE place a display/measurement endpoint decides what to
    actually show for one scalar value -- `(display_value, display_unit,
    per_unit_status)`. `resolution=None` means "per-unit mode was not
    requested" -- passes the engineering value/unit through unchanged,
    with a `None` status (distinct from `not_applicable`, which means
    "per-unit mode IS active but this channel type is exempt"). When
    `resolution.status == STATUS_CONFIGURED` but the measured channel's
    own unit is not one of the minimal recognized set, conversion
    silently fails closed: the display falls back to the engineering
    value/unit with status downgraded to `STATUS_BASE_REQUIRED`, never a
    partially-converted or fabricated result. Unchanged from the
    original DEC-049 implementation.

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
    rules, for a whole waveform-range response. Unchanged from the
    original DEC-049 implementation."""
    if resolution is None:
        return values, measured_unit, None
    if resolution.status != STATUS_CONFIGURED:
        return values, measured_unit, resolution.status
    converted = convert_array_to_pu(values, measured_unit, resolution, engineering_type)
    if converted is None:
        return values, measured_unit, STATUS_BASE_REQUIRED
    return converted, "pu", STATUS_CONFIGURED


#: Decision 6 (unchanged, per the owner's own explicit "do not redesign
#: calculated-channel PU behaviour" instruction) -- unary operations
#: whose output verbatim-inherits the single input's own resolved
#: profile/source id (including `None`).
_INHERIT_VERBATIM_OPERATIONS = frozenset(
    {OP_REVERSE_POLARITY, OP_ABSOLUTE_VALUE, OP_MULTIPLY_CONSTANT, OP_RMS}
)
#: Multi-input operations that inherit only when every input resolves to
#: the exact same known profile/source id.
_INHERIT_IF_UNANIMOUS_OPERATIONS = frozenset({OP_ADDITION, OP_SUBTRACTION})


def derive_per_unit_profile_id(operation: str, input_profile_ids: list[str | None]) -> str | None:
    """Decision 6, UNCHANGED by the source-bound redesign (the owner's
    own explicit instruction: "Preserve current behaviour" for
    calculated channels). `input_profile_ids` are now always source ids
    (or `None`) rather than a separate profile-id space, but the
    inheritance RULE itself is identical:

    - Reverse Polarity, Absolute Value, Multiply by Constant, RMS: the
      single input's own resolved source id, verbatim (including `None`).
    - Addition, Subtraction: the shared source id ONLY when every input
      resolves to the exact same known (non-`None`) source id;
      otherwise `None` -- never an arbitrary pick among candidates.
    - Calculated-from-calculated inputs pass their own already-resolved
      id straight in here, so this composes transitively through
      arbitrarily deep chains with no separate recursive logic.
    """
    if operation in _INHERIT_VERBATIM_OPERATIONS:
        return input_profile_ids[0] if input_profile_ids else None
    if operation in _INHERIT_IF_UNANIMOUS_OPERATIONS:
        if not input_profile_ids or input_profile_ids[0] is None:
            return None
        first = input_profile_ids[0]
        return first if all(p == first for p in input_profile_ids) else None
    return None
