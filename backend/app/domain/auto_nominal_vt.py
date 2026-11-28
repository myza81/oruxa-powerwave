"""Automatic VT derivation from the accepted nominal voltage (owner decision, D5A, 2026-11-21).

When a Voltage Measurement Group has no stored VT ratio, Recording Details derives one from the accepted
nominal system line-to-line voltage: primary = nominal kV x 1000, secondary = 110 V. The derived ratio is
valid engineering configuration, consistent with the existing Per-Unit nominal-voltage policy: it needs no
engineer confirmation, and every consumer (Recording Details, the protection-instrument context, the
Impedance and Distance analyzers) reads it through THIS function so the rule has exactly one definition.

Precedence (unchanged): manual > recording_metadata > auto_nominal > not_configured. A stored VT of any
authority always wins; this derivation only ever applies when no VT is stored. It records its provenance
as `auto_nominal` and is never relabelled `manual` or `recording_metadata`.

Refused (never guessed) when the nominal itself is not an accepted value: a missing, non-finite or
non-positive nominal, a nominal the channel evidence contradicts (`manual_conflict_detected`), or a base
whose authority is `needs_review` / `unavailable`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.base_authority import BASE_AUTHORITY_NEEDS_REVIEW, BASE_AUTHORITY_UNAVAILABLE
from app.domain.voltage_group_config import VoltageBaseConfiguration

AUTHORITY_AUTO_NOMINAL = "auto_nominal"
#: The secondary a nominal-derived VT defaults to (V, line-to-line).
AUTO_NOMINAL_VT_SECONDARY_V = 110.0

REFUSED_NO_NOMINAL = "no_nominal"
REFUSED_INVALID_NOMINAL = "invalid_nominal"
REFUSED_MANUAL_CONFLICT = "manual_conflict"
REFUSED_BASE_NOT_ACCEPTED = "base_not_accepted"


@dataclass(frozen=True, slots=True)
class AutoNominalVt:
    """Result of the derivation: either a (primary, secondary) pair or the reason it was refused.

    `nominal_ll_kv` is set whenever a nominal exists (so a refusal can still name it)."""

    primary_v: float | None = None
    secondary_v: float | None = None
    nominal_ll_kv: float | None = None
    refused_reason: str | None = None

    @property
    def derived(self) -> bool:
        return self.primary_v is not None

    @property
    def provenance_note(self) -> str | None:
        if not self.derived:
            return None
        return f"Auto-derived from nominal voltage {self.nominal_ll_kv:g} kV; secondary {self.secondary_v:g} V default"


def derive_auto_nominal_vt(config: VoltageBaseConfiguration | None) -> AutoNominalVt:
    """The nominal-derived VT of a group, or why none can be derived. Pure; ignores any stored VT
    (callers apply precedence: a stored VT is checked first)."""
    if config is None:
        return AutoNominalVt(refused_reason=REFUSED_NO_NOMINAL)
    nominal = config.nominal_voltage_ll_kv
    if nominal is None:
        return AutoNominalVt(refused_reason=REFUSED_NO_NOMINAL)
    if (not isinstance(nominal, (int, float)) or isinstance(nominal, bool)
            or not math.isfinite(nominal) or nominal <= 0):
        return AutoNominalVt(refused_reason=REFUSED_INVALID_NOMINAL)
    nominal = float(nominal)
    if config.manual_conflict_detected:
        return AutoNominalVt(nominal_ll_kv=nominal, refused_reason=REFUSED_MANUAL_CONFLICT)
    if config.base_authority in (BASE_AUTHORITY_NEEDS_REVIEW, BASE_AUTHORITY_UNAVAILABLE):
        return AutoNominalVt(nominal_ll_kv=nominal, refused_reason=REFUSED_BASE_NOT_ACCEPTED)
    return AutoNominalVt(primary_v=nominal * 1000.0, secondary_v=AUTO_NOMINAL_VT_SECONDARY_V, nominal_ll_kv=nominal)
