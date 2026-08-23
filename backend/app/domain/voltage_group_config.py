"""Voltage measurement-group base configuration and PU resolution
(Slice 3 of DEC-050's measurement-group-aware Per-Unit redesign; see
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md sections 8-10 and
21/25).

Deliberately a SEPARATE domain object from `MeasurementGroup` itself
(`app.domain.measurement_group`), not a field bolted onto it -- per the
canonical document's own refined domain model (section 18's "avoid one
generic base object with many unrelated nullable fields"), a Current
group must never carry Voltage-only fields. `VoltageBaseConfiguration`
exists only for `kind == KIND_VOLTAGE` groups, stored in a sibling
registry (`app.services.voltage_group_config_registry`) keyed by the
owning group's own id -- a Current group simply never has an entry,
structurally, rather than carrying a permanently-`None` Voltage field.

**This module is the NEW, group-aware voltage resolver -- deliberately
independent of `app.domain.per_unit`'s existing source-wide resolver.**
The two are NOT merged in this slice (see this module's own docstring
note under `resolve_voltage_base_for_group()`, and
docs/project-memory/HANDOFF.md's Slice 3 entry for the full
architectural reasoning): the currently deployed DEC-049 source-wide
`/per-unit/sources` API and frontend modal continue to call
`app.domain.per_unit.resolve_per_unit()` completely unchanged. This
module's own resolver is proven correct by its own tests and is not
wired into any existing display/measurement endpoint yet -- that
integration is Slice 5's job, once group-aware resolution needs to
become visible.

**Corrected voltage PU mathematics (the reason this slice exists)**: the
user-facing Vbase is always the familiar NOMINAL SYSTEM LINE-TO-LINE
voltage (e.g. "275 kV") -- the engineer never enters a phase-derived
number. The applicable denominator for a channel's own PU division
depends on that group's own EFFECTIVE VOLTAGE REFERENCE:

- Line-to-Line group: `Vbase_applicable = nominal_voltage_ll_kv`,
  `Vpu = Vmeasured_LL / Vbase_LL` (direct, unchanged from the old rule).
- Line-to-Ground group: `Vbase_applicable = nominal_voltage_ll_kv /
  sqrt(3)`, `Vpu = Vmeasured_LG / (Vbase_LL / sqrt(3))`.

This supersedes the old blanket "never apply sqrt(3) to measured
voltage division" statement (per_unit.py's own decision 3) -- not by
reversing it, but by refining it: the measured value itself is still
NEVER multiplied/divided by sqrt(3) to fabricate an LL-equivalent
reading from an LG measurement (that intent survives unchanged); what
was missing is that the DENOMINATOR itself must be resolved in the same
electrical reference as the measurement. The corrected governing
principle: "the PU denominator must match the electrical reference of
the measured channel."
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.measurement_group import (
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    MeasurementGroup,
)
from app.domain.voltage_reference import (
    KNOWN_VOLTAGE_REFERENCES,
    LINE_TO_GROUND,
    LINE_TO_LINE,
    REASON_MANUAL_OVERRIDE,
    VoltageReferenceDetection,
    detect_voltage_reference,
)

SQRT_3 = 1.7320508075688772

#: Deliberately a fresh, locally-owned copy of the "auto"/"manual"
#: vocabulary rather than importing `app.domain.per_unit`'s own
#: `VOLTAGE_REFERENCE_MODE_*` constants -- see module docstring for why
#: the two resolvers are kept independent this slice. Same string
#: values, so nothing is lost by not sharing the identifiers.
VOLTAGE_REFERENCE_MODE_AUTO = "auto"
VOLTAGE_REFERENCE_MODE_MANUAL = "manual"
KNOWN_VOLTAGE_REFERENCE_MODES = (VOLTAGE_REFERENCE_MODE_AUTO, VOLTAGE_REFERENCE_MODE_MANUAL)

#: Group statuses that may authoritatively resolve a voltage base for
#: PU purposes (canonical document section 9/25's own explicit
#: instruction: "at minimum, confirmed, manual may be authoritative...
#: for suggested, be conservative"). A `suggested` or `needs_review`
#: group's configuration may still be SET (an engineer configuring a
#: still-suggested group is exactly how it gets promoted to confirmed,
#: per the Slice 2 lifecycle), but `resolve_voltage_base_for_group()`
#: below will not treat it as authoritative until its own `status`
#: reaches one of these two values.
AUTHORITATIVE_GROUP_STATUSES = (STATUS_CONFIRMED, STATUS_MANUAL)

#: Mirrors `app.domain.per_unit`'s own three-status shape
#: (`not_applicable`/`configured`/`base_required`) for consistency, but
#: is a completely separate, group-scoped result type -- see module
#: docstring.
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_CONFIGURED = "configured"
STATUS_BASE_REQUIRED = "base_required"


def voltage_base_valid(value: float | None) -> bool:
    """Same validator shape as `per_unit.voltage_base_valid()`: rejects
    `None`, rejects `bool` (a `bool` is technically an `int` in Python),
    requires a finite, strictly positive number."""
    if value is None:
        return False
    return bool(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0)


def voltage_reference_mode_valid(mode: str) -> bool:
    return mode in KNOWN_VOLTAGE_REFERENCE_MODES


def voltage_reference_value_valid(reference: str) -> bool:
    return reference in KNOWN_VOLTAGE_REFERENCES


@dataclass(slots=True)
class VoltageBaseConfiguration:
    """One Voltage measurement group's own base configuration -- exists
    ONLY for `kind == KIND_VOLTAGE` groups (enforced by the service
    layer, `app.services.voltage_group_config_service`, never by this
    plain dataclass itself).

    `nominal_voltage_ll_kv` is always the canonical, user-facing
    NOMINAL SYSTEM LINE-TO-LINE voltage in kV (never a phase-derived
    number the engineer would have to compute themselves) -- mirrors
    `PerUnitBaseProfile.voltage_base_value`'s own "one canonical unit,
    fixed suffix" convention.

    `reference_mode`/`reference_override` mirror
    `PerUnitBaseProfile.voltage_reference_mode`/
    `voltage_reference_override`'s own exact two-field shape: in
    `"auto"` mode, `reference_override` is always `None` and the
    effective reference is ALWAYS re-derived live from the group's own
    current channel membership (never cached) -- this is what makes
    "Return to Auto" correct by construction (there is no stale value to
    accidentally keep)."""

    measurement_group_id: str
    workspace_id: str
    nominal_voltage_ll_kv: float | None
    reference_mode: str = VOLTAGE_REFERENCE_MODE_AUTO
    reference_override: str | None = None


def resolve_effective_voltage_reference_for_group(
    group: MeasurementGroup, config: VoltageBaseConfiguration | None
) -> VoltageReferenceDetection:
    """Group-scoped counterpart of `per_unit.resolve_effective_voltage_reference()`
    -- section 8's own explicit requirement: detection runs against
    THIS GROUP's own `channel_refs` only, never the whole source's
    Voltage channels, so two Voltage groups in the same source (e.g. a
    275 kV bus and a 132 kV bus) can carry two independently-resolved
    references. In `"manual"` mode, the engineer's own override is
    authoritative -- no detection ever runs. Otherwise (including when
    `config` is `None`, i.e. not yet configured at all), the reference
    is re-derived live via `detect_voltage_reference()` -- the SAME
    detection authority `per_unit.py`'s own source-wide resolver uses,
    now just given a group's own channel names instead of a source's
    full voltage-channel list."""
    if config is not None and config.reference_mode == VOLTAGE_REFERENCE_MODE_MANUAL:
        if config.reference_override in KNOWN_VOLTAGE_REFERENCES:
            return VoltageReferenceDetection(
                reference=config.reference_override, evidence_names=[], reason=REASON_MANUAL_OVERRIDE
            )
    voltage_channel_names = [ref.channel_name for ref in group.channel_refs]
    return detect_voltage_reference(voltage_channel_names)


def voltage_base_ll_kv(nominal_voltage_ll_kv: float) -> float:
    """The nominal LL base, unchanged -- the applicable denominator for
    an explicit Line-to-Line measurement group."""
    return nominal_voltage_ll_kv


def voltage_base_phase_kv(nominal_voltage_ll_kv: float) -> float:
    """The applicable PHASE (line-to-ground) base, derived from the
    user-entered nominal LL voltage -- `Vbase_LL / sqrt(3)`. This is the
    one place `sqrt(3)` is ever applied in this module, and it is
    applied to the BASE, never to a measured sample (see module
    docstring's own corrected-principle note)."""
    return nominal_voltage_ll_kv / SQRT_3


@dataclass(slots=True)
class VoltageBaseResolution:
    """The outcome of resolving one Voltage group's own applicable PU
    denominator -- the sole authority any future group-aware
    display/measurement code should consult (mirrors
    `per_unit.PerUnitResolution`'s own role for the source-wide path,
    but is a distinct type -- see module docstring)."""

    status: str  # STATUS_NOT_APPLICABLE | STATUS_CONFIGURED | STATUS_BASE_REQUIRED
    denominator_kv: float | None
    effective_reference: str | None
    reason: str | None


def resolve_voltage_base_for_group(
    group: MeasurementGroup, config: VoltageBaseConfiguration | None
) -> VoltageBaseResolution:
    """The one group-level resolution authority (canonical document
    section 10). Resolves, in order:

    1. Is this even a Voltage group? A Current (or any other kind)
       group is `not_applicable` -- this function is never the place
       Current-group base resolution happens (Slice 4).
    2. Is this group's own status authoritative for PU purposes yet?
       Per section 9/25, only `confirmed`/`manual` groups resolve a
       real denominator -- a `suggested` or `needs_review` group is
       `base_required`, even if it already has a fully valid
       configuration attached (configuring is allowed at any status;
       resolving as authoritative is not, until the group itself is
       confirmed).
    3. Is `nominal_voltage_ll_kv` actually configured and valid?
    4. Does the group's own effective voltage reference resolve
       confidently (auto-detected or manually overridden)? An
       unresolved/conflicting reference (`effective.reference is None`)
       never silently guesses -- `base_required` with a distinct
       reason, exactly like `per_unit.py`'s own
       `voltage_reference_undetermined` case.

    Only when all four resolve does this return `STATUS_CONFIGURED` with
    the correct denominator: `nominal_voltage_ll_kv` directly for
    Line-to-Line, `nominal_voltage_ll_kv / sqrt(3)` for Line-to-Ground.
    """
    if group.kind != KIND_VOLTAGE:
        return VoltageBaseResolution(status=STATUS_NOT_APPLICABLE, denominator_kv=None, effective_reference=None, reason=None)

    if group.status not in AUTHORITATIVE_GROUP_STATUSES:
        return VoltageBaseResolution(
            status=STATUS_BASE_REQUIRED, denominator_kv=None, effective_reference=None, reason="group_not_confirmed"
        )

    if config is None or not voltage_base_valid(config.nominal_voltage_ll_kv):
        return VoltageBaseResolution(
            status=STATUS_BASE_REQUIRED, denominator_kv=None, effective_reference=None, reason="voltage_base_not_configured"
        )

    effective = resolve_effective_voltage_reference_for_group(group, config)
    if effective.reference not in KNOWN_VOLTAGE_REFERENCES:
        return VoltageBaseResolution(
            status=STATUS_BASE_REQUIRED, denominator_kv=None, effective_reference=None, reason="voltage_reference_undetermined"
        )

    if effective.reference == LINE_TO_LINE:
        denominator_kv = voltage_base_ll_kv(config.nominal_voltage_ll_kv)
    else:  # LINE_TO_GROUND
        denominator_kv = voltage_base_phase_kv(config.nominal_voltage_ll_kv)

    return VoltageBaseResolution(
        status=STATUS_CONFIGURED, denominator_kv=denominator_kv, effective_reference=effective.reference, reason=None
    )


#: Canonical unit-normalization set for a MEASURED voltage channel's own
#: declared unit -- deliberately a fresh, locally-owned copy of
#: `per_unit.VOLTAGE_UNIT_SCALE`'s own minimal V/kV set (see module
#: docstring for why the two resolvers stay independent), expressed
#: directly in "how many kV is one unit" terms so it composes directly
#: with `denominator_kv` above without an intermediate volts step.
_VOLTAGE_UNIT_TO_KV = {"v": 0.001, "kv": 1.0}


def convert_voltage_to_pu(measured_value: float | None, measured_unit: str | None, resolution: VoltageBaseResolution) -> float | None:
    """`measured / denominator`, both normalized to kV first -- a direct
    division, always (decision 3's own surviving intent: the MEASURED
    value is never itself multiplied/divided by sqrt(3); only the
    denominator resolved above ever involves it). Returns `None` (never
    guesses) when the value is missing/non-finite, the resolution is not
    `STATUS_CONFIGURED`, or the measured unit is not recognized -- a
    caller must fall back to the engineering value in every such case,
    exactly like `per_unit.convert_value_to_pu()`'s own contract."""
    if measured_value is None or not math.isfinite(measured_value):
        return None
    if resolution.status != STATUS_CONFIGURED or resolution.denominator_kv is None:
        return None
    key = (measured_unit or "").strip().lower()
    scale = _VOLTAGE_UNIT_TO_KV.get(key)
    if scale is None:
        return None
    measured_kv = measured_value * scale
    return measured_kv / resolution.denominator_kv
