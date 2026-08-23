"""Current measurement-group base configuration and PU resolution
(Slice 4 of DEC-050's measurement-group-aware Per-Unit redesign; see
docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md sections 9-12 and
21/24).

Deliberately a SEPARATE domain object from `MeasurementGroup` itself and
from `VoltageBaseConfiguration` (`app.domain.voltage_group_config`) --
per the canonical document's own refined domain model (section 18's
"avoid one generic base object with many unrelated nullable fields"), a
Voltage group must never carry Current-only fields and vice versa.
`CurrentBaseConfiguration` exists only for `kind == KIND_CURRENT` groups,
stored in a sibling registry
(`app.services.current_group_config_registry`) keyed by the owning
group's own id, mirroring `VoltageGroupConfigRegistry`'s exact shape.

**This module is a NEW, group-aware current resolver -- deliberately
independent of `app.domain.per_unit`'s existing source-wide resolver**,
the same architectural choice Slice 3 made for
`app.domain.voltage_group_config` (see that module's own docstring for
the full reasoning, not repeated here). The currently deployed DEC-049
source-wide `/per-unit/sources` API and frontend modal continue to call
`app.domain.per_unit.resolve_per_unit()` completely unchanged. This
module's own resolver is proven correct by its own tests and is not
wired into any existing display/measurement endpoint yet -- that
integration is Slice 5's job.

**Initial current-base methods (canonical document section 10, DEC-050's
2026-08-23 addendum item 5) -- deliberately only three, CT-primary
reference explicitly excluded (section 11)**:

- `equipment_rating`: `Ibase = Sbase / (sqrt(3) * Vbase_LL)`, where
  `Vbase_LL` is obtained either by linking to an existing Voltage
  measurement group's own `nominal_voltage_ll_kv`, or from an
  independent manual value (section 9's "flexible, not forced" applicable-
  voltage-base requirement).
- `manual`: the engineer supplies `Ibase` directly -- no Sbase, no
  voltage source of any kind required.
- `none`: no PU current normalization is available for this group --
  never an invented default, never a silent CT-ratio fallback.

**Critical distinction (section 5 of the Slice 4 task, and section 9's
own worked IBT1-HV example): equipment-rated current-base derivation
ALWAYS uses the raw nominal LINE-TO-LINE voltage, never a phase
(line-to-ground) value** -- even when the linked Voltage group's own
effective reference is line-to-ground. This is why this module reads a
linked Voltage group's `VoltageBaseConfiguration.nominal_voltage_ll_kv`
field directly, rather than calling
`voltage_group_config.resolve_voltage_base_for_group()` (whose own
`denominator_kv` is reference-aware and would incorrectly divide by
`sqrt(3)` for an LG-reference linked group). The two resolvers ask
different physical questions: "what should a VOLTAGE CHANNEL in this
group be divided by to read correctly in pu" (Slice 3, reference-aware)
versus "what is this equipment's own rated nominal system voltage"
(this module, always the raw LL number) -- deliberately never merged.
One direct consequence, verified by this module's own tests: two
otherwise-identical linked Voltage groups that differ only in
`reference_mode`/effective reference produce the exact SAME Ibase for
an equipment-rated Current group linked to either one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.measurement_group import (
    KIND_CURRENT,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    MeasurementGroup,
)
from app.domain.voltage_group_config import VoltageBaseConfiguration, voltage_base_valid

SQRT_3 = 1.7320508075688772

#: Initial target current-base methods (canonical document section 10).
#: CT-primary reference is deliberately NOT in this list -- section 11,
#: and must not be added without a separate, explicit owner approval.
METHOD_EQUIPMENT_RATING = "equipment_rating"
METHOD_MANUAL = "manual"
METHOD_NONE = "none"
KNOWN_CURRENT_BASE_METHODS = (METHOD_EQUIPMENT_RATING, METHOD_MANUAL, METHOD_NONE)

#: Same authoritative-status gate Slice 3 established for Voltage groups
#: (canonical document section 9/25): a `suggested`/`needs_review` group
#: may still be CONFIGURED (that is how it gets promoted), but never
#: resolves as authoritative for PU purposes until confirmed/manual.
AUTHORITATIVE_GROUP_STATUSES = (STATUS_CONFIRMED, STATUS_MANUAL)

#: Mirrors `voltage_group_config`'s own three-status shape for
#: consistency, but is a completely separate, group-scoped result type.
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_CONFIGURED = "configured"
STATUS_BASE_REQUIRED = "base_required"


def current_base_method_valid(method: str) -> bool:
    return method in KNOWN_CURRENT_BASE_METHODS


def _positive_finite(value: float | None) -> bool:
    """Shared validator shape for every numeric field in this module --
    same rules as `voltage_group_config.voltage_base_valid()`: rejects
    `None`, rejects `bool`, requires a finite, strictly positive
    number."""
    if value is None:
        return False
    return bool(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0)


def equipment_rating_mva_valid(value: float | None) -> bool:
    return _positive_finite(value)


def manual_voltage_base_kv_valid(value: float | None) -> bool:
    return _positive_finite(value)


def manual_ibase_ka_valid(value: float | None) -> bool:
    return _positive_finite(value)


@dataclass(slots=True)
class CurrentBaseConfiguration:
    """One Current measurement group's own base configuration -- exists
    ONLY for `kind == KIND_CURRENT` groups (enforced by the service
    layer, `app.services.current_group_config_service`, never by this
    plain dataclass itself).

    Exactly the shape the canonical document's section 18 domain-model
    sketch specifies. `linked_voltage_group_id` and
    `manual_voltage_base_kv` are mutually exclusive (enforced by the
    service layer's setters, never by this dataclass) -- at most one is
    ever non-`None` for a given configuration, so the resolver below
    never needs to choose between two simultaneously-present voltage
    sources (section 8's "prefer rejecting ambiguous input").

    **Chosen internal behaviour for unused fields (task section 8's own
    "document the chosen internal behaviour" instruction)**: every
    `set_current_base_*` service-layer setter CLEARS every field not
    relevant to the method it is setting (never merely ignores them).
    A `method="none"` configuration therefore always has all four
    optional fields `None` -- there is never stale numeric data sitting
    in a configuration that could silently resurface if the resolver's
    own method-dispatch logic were ever refactored. This is a stronger
    guarantee than "the resolver happens to ignore them today"."""

    measurement_group_id: str
    workspace_id: str
    method: str = METHOD_NONE
    equipment_rating_mva: float | None = None
    linked_voltage_group_id: str | None = None
    manual_voltage_base_kv: float | None = None
    manual_ibase_ka: float | None = None


def equipment_rating_ibase_ka(equipment_rating_mva: float, applicable_voltage_ll_kv: float) -> float:
    """`Ibase = Sbase / (sqrt(3) * Vbase_LL)`, with `Sbase` in MVA and
    `Vbase_LL` in kV, yielding `Ibase` directly in kA (dimensionally
    consistent: `MVA = sqrt(3) * kV * kA`). Verified worked examples
    (canonical document section 10, task section 5):

    - 1000 MVA / 500 kV  -> ~1.1547 kA
    - 1000 MVA / 275 kV  -> ~2.0995 kA
    - 1000 MVA / 132 kV  -> ~4.3739 kA
    """
    return equipment_rating_mva / (SQRT_3 * applicable_voltage_ll_kv)


@dataclass(slots=True)
class CurrentBaseResolution:
    """The outcome of resolving one Current group's own applicable PU
    Ibase -- the sole authority any future group-aware display/
    measurement code should consult (mirrors
    `voltage_group_config.VoltageBaseResolution`'s own role, but is a
    distinct type)."""

    status: str  # STATUS_NOT_APPLICABLE | STATUS_CONFIGURED | STATUS_BASE_REQUIRED
    ibase_ka: float | None
    applicable_voltage_ll_kv: float | None
    reason: str | None


def _resolve_applicable_voltage_ll_kv(
    config: CurrentBaseConfiguration,
    linked_voltage_group: MeasurementGroup | None,
    linked_voltage_config: VoltageBaseConfiguration | None,
) -> float | None:
    """Section 3/4's "flexible applicable voltage base" resolution,
    preferring the linked Voltage group when present. Deliberately reads
    `linked_voltage_config.nominal_voltage_ll_kv` DIRECTLY -- see module
    docstring for why this must never go through
    `resolve_voltage_base_for_group()`'s own reference-aware denominator.

    Because `linked_voltage_group_id`/`manual_voltage_base_kv` are
    enforced mutually exclusive at write time (the service layer's own
    setters), there is never a scenario where a link is present but
    invalid/unavailable AND a manual value is also present to silently
    fall back to (task section 4's explicit "do not silently fall back
    to manual Vbase when an invalid link was explicitly supplied" is
    satisfied structurally, not just by this function's own control
    flow: `config.manual_voltage_base_kv` is always `None` whenever
    `config.linked_voltage_group_id` is not `None`)."""
    if config.linked_voltage_group_id is not None:
        if linked_voltage_group is None or linked_voltage_config is None:
            return None
        if not voltage_base_valid(linked_voltage_config.nominal_voltage_ll_kv):
            return None
        return linked_voltage_config.nominal_voltage_ll_kv
    if config.manual_voltage_base_kv is not None and manual_voltage_base_kv_valid(config.manual_voltage_base_kv):
        return config.manual_voltage_base_kv
    return None


def resolve_current_base_for_group(
    group: MeasurementGroup,
    config: CurrentBaseConfiguration | None,
    *,
    linked_voltage_group: MeasurementGroup | None = None,
    linked_voltage_config: VoltageBaseConfiguration | None = None,
) -> CurrentBaseResolution:
    """The one group-level resolution authority (canonical document
    section 10, task section 15). Resolves, in order:

    1. Is this even a Current group? A Voltage (or any other kind) group
       is `not_applicable`.
    2. Is this group's own status authoritative for PU purposes yet
       (`confirmed`/`manual`, same gate as Slice 3's Voltage resolver)?
    3. Is a configuration present at all, and is its `method` something
       other than `none`? `method="none"` (or no configuration at all)
       is always `base_required` -- never an invented default, never a
       CT-ratio fallback (section 7).
    4. Method-specific resolution:
       - `manual`: requires a valid `manual_ibase_ka` -- no Sbase, no
         voltage source of any kind needed (section 6).
       - `equipment_rating`: requires a valid `equipment_rating_mva` AND
         a resolvable applicable Vbase_LL (linked group or manual,
         section 3/4) -- `Ibase = Sbase / (sqrt(3) * Vbase_LL)`.

    `linked_voltage_group`/`linked_voltage_config` are pre-resolved by
    the caller (the service layer) exactly like `voltage_group_config`'s
    own pure-domain functions never touch a registry directly -- this
    function stays a plain, dependency-free resolver, easy for Slice 5
    to call efficiently without repeated registry scans (task section
    28: resolution is group/config-level, not a source-wide scan)."""
    if group.kind != KIND_CURRENT:
        return CurrentBaseResolution(status=STATUS_NOT_APPLICABLE, ibase_ka=None, applicable_voltage_ll_kv=None, reason=None)

    if group.status not in AUTHORITATIVE_GROUP_STATUSES:
        return CurrentBaseResolution(
            status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None, reason="group_not_confirmed"
        )

    if config is None or config.method == METHOD_NONE:
        return CurrentBaseResolution(
            status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None, reason="current_base_not_configured"
        )

    if config.method == METHOD_MANUAL:
        if not manual_ibase_ka_valid(config.manual_ibase_ka):
            return CurrentBaseResolution(
                status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None, reason="manual_ibase_not_configured"
            )
        return CurrentBaseResolution(
            status=STATUS_CONFIGURED, ibase_ka=config.manual_ibase_ka, applicable_voltage_ll_kv=None, reason=None
        )

    if config.method == METHOD_EQUIPMENT_RATING:
        if not equipment_rating_mva_valid(config.equipment_rating_mva):
            return CurrentBaseResolution(
                status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None, reason="equipment_rating_not_configured"
            )
        applicable_kv = _resolve_applicable_voltage_ll_kv(config, linked_voltage_group, linked_voltage_config)
        if applicable_kv is None:
            return CurrentBaseResolution(
                status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None,
                reason="applicable_voltage_base_not_configured",
            )
        ibase_ka = equipment_rating_ibase_ka(config.equipment_rating_mva, applicable_kv)
        return CurrentBaseResolution(status=STATUS_CONFIGURED, ibase_ka=ibase_ka, applicable_voltage_ll_kv=applicable_kv, reason=None)

    # Unreachable through any validly-constructed configuration (the
    # service layer never persists an unknown method) -- defensive only.
    return CurrentBaseResolution(
        status=STATUS_BASE_REQUIRED, ibase_ka=None, applicable_voltage_ll_kv=None, reason="invalid_current_base_method"
    )


#: Canonical unit-normalization set for a MEASURED current channel's own
#: declared unit -- same "how many kA is one unit" shape as
#: `voltage_group_config._VOLTAGE_UNIT_TO_KV`.
_CURRENT_UNIT_TO_KA = {"a": 0.001, "ka": 1.0}


def convert_current_to_pu(measured_value: float | None, measured_unit: str | None, resolution: CurrentBaseResolution) -> float | None:
    """`Ipu = Imeasured / Ibase`, both normalized to kA first -- a direct
    division. Returns `None` (never guesses) when the value is missing/
    non-finite, the resolution is not `STATUS_CONFIGURED`, or the
    measured unit is not recognized -- a caller must fall back to the
    engineering value in every such case, exactly like
    `voltage_group_config.convert_voltage_to_pu()`'s own contract. Not
    wired into any live endpoint this slice (task section 15/24) --
    provided so Slice 5 has a ready-made, already-tested conversion
    primitive rather than needing to invent one."""
    if measured_value is None or not math.isfinite(measured_value):
        return None
    if resolution.status != STATUS_CONFIGURED or resolution.ibase_ka is None:
        return None
    key = (measured_unit or "").strip().lower()
    scale = _CURRENT_UNIT_TO_KA.get(key)
    if scale is None:
        return None
    measured_ka = measured_value * scale
    return measured_ka / resolution.ibase_ka
