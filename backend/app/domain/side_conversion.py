"""D5A-2B1: independent Voltage/Current measurement-side conversion (pure domain).

Each consumed quantity is converted directly into the requested output side, then Z = V / I is
formed once. A CT/VT ratio (primary / secondary) is applied only when the quantity's source side
differs from the output side; a quantity already on the output side is never touched.

    secondary -> primary :  value * ratio
    primary   -> secondary: value / ratio
    same side            :  value (identity, ratio never read)

No PU code is involved and nothing here infers a side from a ratio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_units import (
    ENGINEERING_QUANTITY_CURRENT,
    ENGINEERING_QUANTITY_VOLTAGE,
    scale_to_canonical,
)

SIDE_PRIMARY = "primary"
SIDE_SECONDARY = "secondary"
KNOWN_SIDES = (SIDE_PRIMARY, SIDE_SECONDARY)

MODE_LEGACY = "legacy"
MODE_INDEPENDENT_SIDES = "independent_sides"

# Machine-readable reason codes (stable contract); `needs_configuration` results carry one.
REASON_INVALID_IMPEDANCE_BASIS = "invalid_impedance_basis"
REASON_VOLTAGE_SIDE_REQUIRED = "voltage_side_required"
REASON_CURRENT_SIDE_REQUIRED = "current_side_required"
REASON_INVALID_VOLTAGE_SIDE = "invalid_voltage_side"
REASON_INVALID_CURRENT_SIDE = "invalid_current_side"
REASON_VOLTAGE_MIXED_SIDE = "voltage_mixed_side_within_quantity"
REASON_CURRENT_MIXED_SIDE = "current_mixed_side_within_quantity"
REASON_VOLTAGE_SIDE_UNAVAILABLE = "voltage_side_authority_unavailable"
REASON_CURRENT_SIDE_UNAVAILABLE = "current_side_authority_unavailable"
REASON_VOLTAGE_SIDE_CONTRADICTS = "voltage_side_contradicts_recording"
REASON_CURRENT_SIDE_CONTRADICTS = "current_side_contradicts_recording"
REASON_VT_AUTHORITY_UNAVAILABLE = "vt_authority_unavailable"
REASON_CT_AUTHORITY_UNAVAILABLE = "ct_authority_unavailable"
REASON_REQUEST_VT_CONFLICTS = "request_vt_conflicts_with_authority"
REASON_REQUEST_CT_CONFLICTS = "request_ct_conflicts_with_authority"
REASON_UNSUPPORTED_VOLTAGE_UNIT = "unsupported_voltage_unit"
REASON_UNSUPPORTED_CURRENT_UNIT = "unsupported_current_unit"
REASON_CHANNEL_MISMATCH = "side_plan_channel_mismatch"


def _normalise(magnitude: float, quantity: str, unit: str | None) -> float | None:
    """Magnitude in the quantity's canonical calculation unit, or None when the UNIT cannot be normalised.
    Decided by the shared unit layer only; a non-finite magnitude passes through for the caller's own guardrails."""
    scale = scale_to_canonical(quantity, unit)
    return None if scale is None else magnitude * scale


def normalise_to_volts(magnitude: float, unit: str | None) -> float | None:
    return _normalise(magnitude, ENGINEERING_QUANTITY_VOLTAGE, unit)


def normalise_to_amperes(magnitude: float, unit: str | None) -> float | None:
    return _normalise(magnitude, ENGINEERING_QUANTITY_CURRENT, unit)


def ratio_valid(ratio: float | None) -> bool:
    return ratio is not None and math.isfinite(ratio) and ratio > 0.0


def convert_to_side(value: float, source_side: str, output_side: str, ratio: float | None) -> float:
    """Convert one magnitude between sides. `ratio` is primary / secondary and is read only when a
    conversion is actually required; a missing/invalid ratio then raises (never a fabricated value)."""
    if source_side == output_side:
        return value
    if not ratio_valid(ratio):
        raise ValueError("A valid positive CT/VT ratio is required for a side conversion.")
    return value * ratio if (source_side == SIDE_SECONDARY and output_side == SIDE_PRIMARY) else value / ratio


@dataclass(frozen=True, slots=True)
class SideConversionInfo:
    """Echoed on a result: what the strict path used, or why it refused."""

    mode: str = MODE_INDEPENDENT_SIDES
    voltage_side: str | None = None
    current_side: str | None = None
    output_side: str | None = None
    vt_ratio_applied: float | None = None
    ct_ratio_applied: float | None = None
    voltage_group_ids: tuple[str, ...] = ()
    current_group_ids: tuple[str, ...] = ()
    block_code: str | None = None
    block_quantity: str | None = None
    block_detail: Mapping[str, str | float | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SideBlock:
    """The strict path refused: no conversion is performed and legacy is NOT used as a fallback."""

    code: str
    message: str
    quantity: str | None = None
    detail: Mapping[str, str | float | None] = field(default_factory=dict)
    voltage_side: str | None = None
    current_side: str | None = None
    output_side: str | None = None
    #: Channels that DID resolve for this analysis, keyed by role (e.g. "Va", "Ia"), with their unit metadata, so a
    #: blocked result can still identify the physical signals. Never populated for an unresolved role.
    role_refs: Mapping[str, ChannelRef] = field(default_factory=dict)
    role_units: Mapping[str, str | None] = field(default_factory=dict)

    @property
    def info(self) -> SideConversionInfo:
        return SideConversionInfo(
            voltage_side=self.voltage_side, current_side=self.current_side, output_side=self.output_side,
            block_code=self.code, block_quantity=self.quantity, block_detail=dict(self.detail),
        )


@dataclass(frozen=True, slots=True)
class SidePlan:
    """A validated strict-conversion plan. `validated` is False only when channel resolution was
    incomplete at planning time; the compute path then reports its own natural status."""

    voltage_side: str
    current_side: str
    output_side: str
    vt_ratio: float | None
    ct_ratio: float | None
    voltage_refs: tuple[ChannelRef, ...] = ()
    current_refs: tuple[ChannelRef, ...] = ()
    voltage_group_ids: tuple[str, ...] = ()
    current_group_ids: tuple[str, ...] = ()
    validated: bool = True

    @property
    def info(self) -> SideConversionInfo:
        return SideConversionInfo(
            voltage_side=self.voltage_side, current_side=self.current_side, output_side=self.output_side,
            vt_ratio_applied=self.vt_ratio if self.voltage_side != self.output_side else None,
            ct_ratio_applied=self.ct_ratio if self.current_side != self.output_side else None,
            voltage_group_ids=self.voltage_group_ids, current_group_ids=self.current_group_ids,
        )

    def scale_voltage(self, value: float) -> float:
        return convert_to_side(value, self.voltage_side, self.output_side, self.vt_ratio)

    def scale_current(self, value: float) -> float:
        return convert_to_side(value, self.current_side, self.output_side, self.ct_ratio)

    @property
    def current_scale(self) -> float:
        """|I_out| / |I_recorded|: lets the low-current guardrail keep judging the RECORDED current."""
        return self.scale_current(1.0)
