"""PU-MIG S1: the pure side-denominator resolver (domain only; NOT connected to any consumer).

Given ONE already-established engineering base and the measurement side of the samples it will be divided into, this module
answers a single arithmetic question: what number, in the unit of the SAMPLES' side, is 1.0 per unit?  Samples are never scaled,
modified or even passed in -- `pu = sample / denominator` stays the caller's job.

    rho = 1 / sqrt(3)   for a line-to-ground Voltage, else 1
    same side                          D = B * rho                  the CT/VT ratio is NOT read
    base Primary,   samples Secondary  D = B * rho / r              conversion "base_divided_by_ratio"
    base Secondary, samples Primary    D = B * rho * r              conversion "base_multiplied_by_ratio"
    r = primary / secondary of the consumed channel's OWN Measurement Group (VT for Voltage, CT for Current)

What this function is NOT
-------------------------
* It does not choose a base. Selecting between a stored `secondary_voltage_ll_v` and a nominal-derived value (decision D-4), what
  activates the legacy secondary path (D-5) and any other precedence belong to a separately reviewed integration policy. It is
  handed one base and resolves that base on its own terms.
* It does not decide a measurement side, and infers nothing from a ratio, a magnitude, a name or a sibling channel. A side that
  is not strict-usable (calculated, unresolved, inferred, group conflict) yields no number.
* It does not retain, label or remove historical "Unverified" results (decision D-1). It has no notion of them.
* The Secondary-base-on-Primary-samples case (`base_multiplied_by_ratio`) is arithmetic only. Converting such a base is an
  integration policy that is **pending** (D-6) and NOT approved behaviour; nothing in the application calls this function.
* It owns no wording, no API shape and no registry. Reason codes are proposals pending decision N-2.

Refusal precedence (the first match wins, so the answer is deterministic and a refusal never carries a number):
    1. invalid request            2. sample side not strict-usable      3. base side unknown (never assumed Primary)
    4. a conversion is needed and the ratio is not authoritative       5. denominator not representable
When the sides already match, the ratio is never read: a missing, invalid, untrusted or conflicting ratio changes nothing.

Numerics follow `app.domain.per_unit_numerics`: the same-side path performs the existing arithmetic (`value / SQRT_3` for
line-to-ground, otherwise the value unchanged) so Primary/Primary denominators are bit-identical to today's; a conversion uses the
same operation order and falls back to one exponent-separated evaluation only when an intermediate or the result would not be a
normal float. A result must be finite and nonzero; a subnormal result is valid, overflow and underflow to zero are refused.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

from app.domain.per_unit_numerics import SQRT_3, positive_finite

# ------------------------------------------------------------------------------------------------------- vocabulary
QUANTITY_VOLTAGE = "voltage"
QUANTITY_CURRENT = "current"
QUANTITIES = (QUANTITY_VOLTAGE, QUANTITY_CURRENT)

REPRESENTATION_LINE_TO_LINE = "line_to_line"
REPRESENTATION_LINE_TO_GROUND = "line_to_ground"
REPRESENTATIONS = (REPRESENTATION_LINE_TO_LINE, REPRESENTATION_LINE_TO_GROUND)

SIDE_PRIMARY = "primary"
SIDE_SECONDARY = "secondary"
SIDE_UNKNOWN = "unknown"
BASE_SIDES = (SIDE_PRIMARY, SIDE_SECONDARY, SIDE_UNKNOWN)

#: What the base IS, which fixes the side it is expressed on where the meaning decides it.
BASE_NOMINAL_LL_PRIMARY = "nominal_ll_primary"                    # Voltage: nominal system L-L volts, Primary by meaning
BASE_LEGACY_SECONDARY_VOLTAGE_LL = "legacy_secondary_voltage_ll"  # Voltage: a secondary L-L volts base, Secondary
BASE_EQUIPMENT_DERIVED_PRIMARY = "equipment_derived_primary"      # Current: Ibase = S / (sqrt(3) V_LL), Primary (DEC-209)
BASE_MANUAL_DIRECT = "manual_direct"                               # Current: an engineer's base with its own declared side
BASE_RESULT_MANUAL = "result_manual"                               # Current: a calculated result's own base, its own side
_KINDS_BY_QUANTITY = {
    QUANTITY_VOLTAGE: (BASE_NOMINAL_LL_PRIMARY, BASE_LEGACY_SECONDARY_VOLTAGE_LL),
    QUANTITY_CURRENT: (BASE_EQUIPMENT_DERIVED_PRIMARY, BASE_MANUAL_DIRECT, BASE_RESULT_MANUAL),
}
_PRIMARY_ONLY_KINDS = (BASE_NOMINAL_LL_PRIMARY, BASE_EQUIPMENT_DERIVED_PRIMARY)
_SECONDARY_ONLY_KINDS = (BASE_LEGACY_SECONDARY_VOLTAGE_LL,)

#: Why the sample side cannot be consumed. The values mirror `app.services.recorded_side_authority.PROBLEM_*`
#: (a domain module may not import a service; a test keeps the two in step).
PROBLEM_CALCULATED = "calculated"
PROBLEM_UNRESOLVED = "unresolved"
PROBLEM_INFERRED = "inferred"
PROBLEM_GROUP_CONFLICT = "group_conflict"

#: Ratio status, mirroring `app.services.protection_instrument_context.RATIO_*` (kept in step by a test).
RATIO_CONFIGURED = "configured"
RATIO_NO_CHANNELS = "no_channels"
RATIO_NO_GROUP = "no_group"
RATIO_NOT_CONFIGURED = "not_configured"
RATIO_UNTRUSTED_AUTHORITY = "untrusted_authority"
RATIO_INVALID = "invalid"
RATIO_CONFLICT = "conflict"
RATIO_STATUSES = (RATIO_CONFIGURED, RATIO_NO_CHANNELS, RATIO_NO_GROUP, RATIO_NOT_CONFIGURED,
                  RATIO_UNTRUSTED_AUTHORITY, RATIO_INVALID, RATIO_CONFLICT)
#: The authorities a configured ratio may carry and still be consumed (DEC-215: the nominal-derived VT is one; `mixed` is the
#: aggregate of several consumable authorities). Anything else is not authoritative.
RATIO_AUTHORITIES = ("manual", "recording_metadata", "auto_nominal", "mixed")
RATIO_DETAIL_NOT_PROVIDED = "not_provided"

STATUS_RESOLVED = "resolved"
STATUS_UNAVAILABLE = "unavailable"

CONVERSION_DIRECT = "direct"
CONVERSION_BASE_DIVIDED_BY_RATIO = "base_divided_by_ratio"
CONVERSION_BASE_MULTIPLIED_BY_RATIO = "base_multiplied_by_ratio"

# Reason codes -- PROPOSALS pending decision N-2. The sample and ratio names reuse existing vocabulary
# (`overcurrent`/`side_conversion`/`protection_instrument_context`); the others are new.
REASON_INVALID_QUANTITY = "invalid_quantity"
REASON_INVALID_REPRESENTATION = "invalid_representation"
REASON_INVALID_BASE_DECLARATION = "invalid_base_declaration"
REASON_INVALID_BASE_VALUE = "invalid_base_value"
REASON_INVALID_SAMPLE_SIDE = "invalid_sample_side"
REASON_SAMPLE_CALCULATED = "calculated_channel_side_unavailable"
REASON_SAMPLE_UNRESOLVED = "measurement_side_unresolved"
REASON_SAMPLE_INFERRED = "measurement_side_inferred"
REASON_SAMPLE_GROUP_CONFLICT = "measurement_group_side_conflict"
REASON_BASE_SIDE_UNKNOWN = "base_side_unknown"
REASON_VT_AUTHORITY_UNAVAILABLE = "vt_authority_unavailable"
REASON_CT_AUTHORITY_UNAVAILABLE = "ct_authority_unavailable"
REASON_DENOMINATOR_NOT_REPRESENTABLE = "denominator_not_representable"
_SAMPLE_PROBLEM_REASON = {
    PROBLEM_CALCULATED: REASON_SAMPLE_CALCULATED,
    PROBLEM_UNRESOLVED: REASON_SAMPLE_UNRESOLVED,
    PROBLEM_INFERRED: REASON_SAMPLE_INFERRED,
    PROBLEM_GROUP_CONFLICT: REASON_SAMPLE_GROUP_CONFLICT,
}
_RATIO_REASON = {QUANTITY_VOLTAGE: REASON_VT_AUTHORITY_UNAVAILABLE, QUANTITY_CURRENT: REASON_CT_AUTHORITY_UNAVAILABLE}


# ----------------------------------------------------------------------------------------------------------- inputs
@dataclass(frozen=True, slots=True)
class SideBase:
    """An already-established engineering base. `value` is SI: volts (L-L) for Voltage, amperes for Current; finite and > 0.
    `declared_side` is the side the base is expressed on. Equipment-derived and nominal bases are Primary by meaning and the
    legacy secondary Voltage base is Secondary; a manual/direct or result-owned base carries its own declared side, and
    `unknown` is never treated as Primary."""

    kind: str
    value: float
    declared_side: str


@dataclass(frozen=True, slots=True)
class SampleSide:
    """The measurement-side result for the consumed channel. Strict-usable means `side` is `primary` or `secondary` and
    `problem` is None; otherwise `side` is None and `problem` is one of the PROBLEM_* values. `authority` is an opaque
    provenance echo (for example `engineer_group_override`) and is never interpreted."""

    side: str | None
    problem: str | None = None
    authority: str | None = None


@dataclass(frozen=True, slots=True)
class SideRatio:
    """The transformation ratio of the consumed channel's own Measurement Group, as already established by the caller.
    `value` is primary / secondary and is meaningful only when `status` is `configured`; for any other status the value is
    ignored (the status is the authority). `authority` is one of RATIO_AUTHORITIES when configured."""

    status: str
    value: float | None = None
    authority: str | None = None
    group_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------------------------------------- result
@dataclass(frozen=True, slots=True)
class SideDenominator:
    """`status == "resolved"`: `denominator` is the number (in the sample side's unit) that equals 1.0 pu, with the conversion
    that produced it. `status == "unavailable"`: `reason` says why and no number is carried. Provenance fields echo what was
    used; `ratio_*` are populated only when a ratio was actually applied (never for a direct result)."""

    status: str
    reason: str | None = None
    #: For a ratio refusal: the ratio status (or `not_provided` / `invalid` / `untrusted_authority`) that made it non-authoritative.
    detail: str | None = None
    denominator: float | None = None
    denominator_side: str | None = None
    conversion: str | None = None
    ratio_applied: float | None = None
    ratio_authority: str | None = None
    ratio_group_ids: tuple[str, ...] = ()
    quantity: str | None = None
    representation: str | None = None
    representation_factor: float | None = None
    sample_side: str | None = None
    sample_authority: str | None = None
    base_kind: str | None = None
    base_side: str | None = None

    @property
    def resolved(self) -> bool:
        return self.status == STATUS_RESOLVED


def _refuse(reason: str, *, detail: str | None = None, quantity=None, representation=None, base=None, sample=None) -> SideDenominator:
    return SideDenominator(
        status=STATUS_UNAVAILABLE, reason=reason, detail=detail,
        quantity=quantity if quantity in QUANTITIES else None,
        representation=representation if representation in REPRESENTATIONS else None,
        base_kind=base.kind if isinstance(base, SideBase) and isinstance(base.kind, str) else None,
        base_side=base.declared_side if isinstance(base, SideBase) and base.declared_side in BASE_SIDES else None,
        sample_side=sample.side if isinstance(sample, SampleSide) and sample.side in (SIDE_PRIMARY, SIDE_SECONDARY) else None,
        sample_authority=sample.authority if isinstance(sample, SampleSide) and isinstance(sample.authority, str) else None,
    )


# --------------------------------------------------------------------------------------------------------- numerics
def _exponent_separated(base: float, line_to_ground: bool, ratio: float, multiply: bool) -> float | None:
    """`base * rho * ratio` (or `/ ratio`) with no intermediate that need be representable; one rounding at the end."""
    mantissa, exponent = math.frexp(base)
    if line_to_ground:
        m_root, e_root = math.frexp(SQRT_3)
        mantissa /= m_root
        exponent -= e_root
    m_ratio, e_ratio = math.frexp(ratio)
    if multiply:
        mantissa *= m_ratio
        exponent += e_ratio
    else:
        mantissa /= m_ratio
        exponent -= e_ratio
    try:
        result = math.ldexp(mantissa, exponent)
    except OverflowError:
        return None
    return result if positive_finite(result) else None


def _converted(base: float, line_to_ground: bool, ratio: float, multiply: bool) -> float | None:
    scaled = base / SQRT_3 if line_to_ground else base
    result = scaled * ratio if multiply else scaled / ratio
    if math.isfinite(result) and result >= sys.float_info.min and scaled >= sys.float_info.min:
        return result
    return _exponent_separated(base, line_to_ground, ratio, multiply)


# --------------------------------------------------------------------------------------------------------- resolver
def resolve_side_denominator(
    quantity: str, base: SideBase, sample: SampleSide, ratio: SideRatio | None, *, representation: str | None = None,
) -> SideDenominator:
    """Resolve the denominator of `base` in the unit of `sample`'s side. Pure; never raises for any input: an unusable request is
    an `unavailable` result carrying one reason. `representation` is required for Voltage (`line_to_line` / `line_to_ground`,
    never defaulted) and must be None for Current."""
    echo = dict(quantity=quantity, representation=representation, base=base, sample=sample)

    # 1. invalid request ------------------------------------------------------------------------------------------
    if not isinstance(quantity, str) or quantity not in QUANTITIES:
        return _refuse(REASON_INVALID_QUANTITY, **echo)
    if (quantity == QUANTITY_VOLTAGE and not (isinstance(representation, str) and representation in REPRESENTATIONS)) \
            or (quantity == QUANTITY_CURRENT and representation is not None):
        return _refuse(REASON_INVALID_REPRESENTATION, **echo)
    if (
        not isinstance(base, SideBase) or not isinstance(base.kind, str)
        or base.kind not in _KINDS_BY_QUANTITY[quantity]
        or not isinstance(base.declared_side, str) or base.declared_side not in BASE_SIDES
        or (base.kind in _PRIMARY_ONLY_KINDS and base.declared_side != SIDE_PRIMARY)
        or (base.kind in _SECONDARY_ONLY_KINDS and base.declared_side != SIDE_SECONDARY)
    ):
        return _refuse(REASON_INVALID_BASE_DECLARATION, **echo)
    if not positive_finite(base.value):
        return _refuse(REASON_INVALID_BASE_VALUE, **echo)
    if not isinstance(sample, SampleSide) or not (
        (sample.problem is None and isinstance(sample.side, str) and sample.side in (SIDE_PRIMARY, SIDE_SECONDARY))
        or (sample.side is None and isinstance(sample.problem, str) and sample.problem in _SAMPLE_PROBLEM_REASON)
    ):
        return _refuse(REASON_INVALID_SAMPLE_SIDE, **echo)

    # 2. the sample side must be strict-usable ----------------------------------------------------------------------
    if sample.problem is not None:
        return _refuse(_SAMPLE_PROBLEM_REASON[sample.problem], **echo)

    # 3. an Unknown base side is never assumed Primary ----------------------------------------------------------------
    if base.declared_side == SIDE_UNKNOWN:
        return _refuse(REASON_BASE_SIDE_UNKNOWN, **echo)

    line_to_ground = quantity == QUANTITY_VOLTAGE and representation == REPRESENTATION_LINE_TO_GROUND
    value = float(base.value)
    common = dict(
        quantity=quantity, representation=representation, representation_factor=(1.0 / SQRT_3) if line_to_ground else 1.0,
        sample_side=sample.side, sample_authority=sample.authority, base_kind=base.kind, base_side=base.declared_side,
        denominator_side=sample.side,
    )

    # direct: the ratio is not read ------------------------------------------------------------------------------------
    if base.declared_side == sample.side:
        denominator = value / SQRT_3 if line_to_ground else value
        if not positive_finite(denominator):
            return _refuse(REASON_DENOMINATOR_NOT_REPRESENTABLE, **echo)
        return SideDenominator(status=STATUS_RESOLVED, denominator=denominator, conversion=CONVERSION_DIRECT, **common)

    # 4. a conversion is needed: only an authoritative ratio may be used ---------------------------------------------
    reason = _RATIO_REASON[quantity]
    if ratio is None:
        return _refuse(reason, detail=RATIO_DETAIL_NOT_PROVIDED, **echo)
    if not isinstance(ratio, SideRatio) or not isinstance(ratio.status, str) or ratio.status not in RATIO_STATUSES:
        return _refuse(reason, detail=RATIO_INVALID, **echo)
    if ratio.status != RATIO_CONFIGURED:
        return _refuse(reason, detail=ratio.status, **echo)
    if not positive_finite(ratio.value):
        return _refuse(reason, detail=RATIO_INVALID, **echo)
    if not isinstance(ratio.authority, str) or ratio.authority not in RATIO_AUTHORITIES:
        return _refuse(reason, detail=RATIO_UNTRUSTED_AUTHORITY, **echo)

    # 5. apply the ratio exactly once --------------------------------------------------------------------------------
    multiply = base.declared_side == SIDE_SECONDARY          # Secondary base on Primary samples (arithmetic only; D-6 pending)
    r = float(ratio.value)
    denominator = _converted(value, line_to_ground, r, multiply)
    if denominator is None:
        return _refuse(REASON_DENOMINATOR_NOT_REPRESENTABLE, **echo)
    try:
        group_ids = tuple(ratio.group_ids)
    except TypeError:
        group_ids = ()
    return SideDenominator(
        status=STATUS_RESOLVED, denominator=denominator, ratio_applied=r, ratio_authority=ratio.authority,
        ratio_group_ids=group_ids,
        conversion=CONVERSION_BASE_MULTIPLIED_BY_RATIO if multiply else CONVERSION_BASE_DIVIDED_BY_RATIO, **common,
    )
