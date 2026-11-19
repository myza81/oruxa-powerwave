"""Wire shapes for the DEC-050 Slice 6 Measurement Group configuration
API -- thin exposure of the already-approved Slice 1/3/4 domain/service
behaviour (`app.services.measurement_group_service`/
`voltage_group_config_service`/`current_group_config_service`), never a
reimplementation of their validation.

Source-scoped (mirrors `app.api.v1.sources`'s own router shape): every
group belongs to exactly one `source_id`, itself scoped to one
`workspace_id`. Human-facing `display_name` is a label only -- every
request/response identifies a group by its own opaque `id`
(`measurement_group_id`), never by name (canonical document section 18).

`MeasurementGroupOut` embeds its own type-specific configuration
(`voltage_config` XOR `current_config`, matching `kind`) AND its own
resolved PU status (`pu_status`/`pu_reason`) in the SAME object the list
endpoint returns -- this is what lets the frontend load a source's
entire configuration workspace in one request (task section 27's own
explicit "load group list once" performance requirement), rather than
issuing a follow-up request per row.
"""

from __future__ import annotations
from app.domain.reference_side import ReferenceSide

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator

from app.schemas.calculated_channel import ChannelRefIn, ChannelRefOut


def _reject_boolean_base(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("A per-unit base must be numeric, not a boolean.")
    return value


# Preserve float/int/numeric-string coercion; only JSON booleans must be
# rejected before Pydantic turns them into 1.0/0.0 (audit PU-007).
PerUnitBaseNumber = Annotated[float, BeforeValidator(_reject_boolean_base)]

GroupKind = Literal["voltage", "current"]
GroupStatus = Literal["suggested", "confirmed", "needs_review", "manual"]
VoltageReferenceMode = Literal["auto", "manual"]
VoltageReferenceValue = Literal["line_to_ground", "line_to_line"]
CurrentBaseMethod = Literal["equipment_rating", "manual", "none"]
PuStatus = Literal["not_applicable", "configured", "base_required"]


class VoltageGroupConfigOut(BaseModel):
    """Only present on a `kind="voltage"` group's own `voltage_config`
    field. `effective_reference`/`evidence_names`/`detection_reason`
    are the LIVE result of `resolve_effective_voltage_reference_for_group()`
    -- re-derived from the group's own current channel membership every
    time, never a stale cached value (Slice 3)."""

    nominal_voltage_ll_kv: float | None
    reference_mode: VoltageReferenceMode
    reference_override: VoltageReferenceValue | None
    effective_reference: VoltageReferenceValue | None
    evidence_names: list[str]
    detection_reason: str
    base_reference_side: ReferenceSide = "unknown"
    secondary_voltage_ll_v: float | None = None
    # RD-0B Option A: manual-base conflict flag.  True when membership-change
    # detection resolved a different voltage than the engineer's manual kV.
    # PU is blocked while True.  False is the safe, no-conflict default.
    manual_conflict_detected: bool = False
    manual_conflict_detail: str | None = None
    # Slice C-2: authoritative base authority state from the domain model.
    # Exposed so the frontend can distinguish needs_review from unavailable
    # without inferring authority from reference_mode / detection_reason.
    # One of: "auto_resolved", "manual", "legacy_manual", "needs_review", "unavailable".
    base_authority: str = "legacy_manual"
    # D1: Voltage Transformer (VT) instrument-transformer metadata.
    vt_primary_v: float | None = None
    vt_secondary_v: float | None = None
    vt_ratio: float | None = None
    vt_authority: str = "not_configured"
    vt_provenance_note: str | None = None


class CurrentGroupConfigOut(BaseModel):
    """Only present on a `kind="current"` group's own `current_config`
    field. `resolved_ibase_ka`/`applicable_voltage_ll_kv` are read-only
    DERIVED information (Slice 4's own resolver) -- the frontend must
    never recompute `Ibase = Sbase / (sqrt(3) * Vbase_LL)` itself."""

    base_reference_side: ReferenceSide = "unknown"
    method: CurrentBaseMethod
    equipment_rating_mva: float | None
    linked_voltage_group_id: str | None
    manual_voltage_base_kv: float | None
    manual_ibase_ka: float | None
    resolved_ibase_ka: float | None
    applicable_voltage_ll_kv: float | None
    # Slice C-2: authoritative base authority for current groups.
    base_authority: str = "legacy_manual"
    # D1: Current Transformer (CT) instrument-transformer metadata.
    ct_primary_a: float | None = None
    ct_secondary_a: float | None = None
    ct_ratio: float | None = None
    ct_authority: str = "not_configured"
    ct_provenance_note: str | None = None
    # D3: Independent equipment-rating metadata (method-independent).
    equipment_mva: float | None = None
    equipment_linked_voltage_group_id: str | None = None
    equipment_rated_current_ka: float | None = None


class MeasurementGroupOut(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    kind: GroupKind
    display_name: str
    channel_refs: list[ChannelRefOut]
    status: GroupStatus
    created_at: datetime | None
    voltage_config: VoltageGroupConfigOut | None = None
    current_config: CurrentGroupConfigOut | None = None
    pu_status: PuStatus
    pu_reason: str | None


class MeasurementGroupCreateRequest(BaseModel):
    kind: GroupKind
    display_name: str
    channel_refs: list[ChannelRefIn]
    status: GroupStatus = "manual"


class MeasurementGroupUpdateRequest(BaseModel):
    """Partial update -- only supplied fields change, mirroring
    `update_group_metadata()`'s own partial-update contract.
    `channel_refs`, if supplied, is a FULL replace of membership
    (`update_group_membership()`'s own contract), never a merge."""

    display_name: str | None = None
    status: GroupStatus | None = None
    channel_refs: list[ChannelRefIn] | None = None


class VoltageGroupConfigUpdateRequest(BaseModel):
    """PUT body for a Voltage group's own configuration. `nominal_voltage_ll_kv`
    is the familiar nominal system LINE-TO-LINE voltage -- the engineer
    never enters a phase-derived number (Slice 3). Omitting it leaves
    the group's existing base value untouched. `clear_nominal_voltage=True`
    clears the manual kV (sets base_authority to needs_review and re-runs
    auto-detection); must not be combined with nominal_voltage_ll_kv.
    `reference_mode="manual"` requires `reference_override`;
    `reference_mode="auto"` (default) always returns the group to
    live auto-detection, clearing any previous override.
    `base_reference_side` declares whether the configured nominal voltage
    is a primary or secondary equipment rating (default "unknown" for
    backward compatibility with existing configurations)."""

    nominal_voltage_ll_kv: PerUnitBaseNumber | None = None
    reference_mode: VoltageReferenceMode = "auto"
    reference_override: VoltageReferenceValue | None = None
    base_reference_side: ReferenceSide = "unknown"
    secondary_voltage_ll_v: float | None = None
    # D2: revert-to-auto flag. Clears nominal_voltage_ll_kv, sets
    # base_authority=needs_review; must not be combined with nominal_voltage_ll_kv.
    # secondary_voltage_ll_v is preserved (independent metadata, Gate 1).
    clear_nominal_voltage: bool = False
    # D1: Voltage Transformer instrument-transformer configuration.
    # Partial pair (primary without secondary or vice versa) is 422.
    # clear_vt=True removes any existing VT configuration; must not
    # be combined with vt_primary_v or vt_secondary_v.
    vt_primary_v: float | None = None
    vt_secondary_v: float | None = None
    vt_provenance_note: str | None = None
    clear_vt: bool = False


class CurrentGroupConfigUpdateRequest(BaseModel):
    """PUT body for a Current group's own configuration.

    Two dispatch paths:

    1. ``update_equipment_metadata_only=True`` (D3): updates only the
       independent ``equipment_mva`` / ``equipment_linked_voltage_group_id``
       fields without touching the PU current-base method.  ``method`` must
       not be supplied in this path; existing method/manual_ibase_ka/etc are
       preserved exactly.

    2. ``update_equipment_metadata_only=False`` (default): dispatches to
       exactly one of Slice 4's three method setters based on ``body.method``
       -- existing behavior completely unchanged.
    """

    # D3 independent equipment-metadata path (method-safe).
    update_equipment_metadata_only: bool = False
    equipment_mva: PerUnitBaseNumber | None = None
    equipment_linked_voltage_group_id: str | None = None
    clear_equipment_mva: bool = False

    # Existing method-setter fields (used when update_equipment_metadata_only=False).
    base_reference_side: ReferenceSide = "unknown"
    method: CurrentBaseMethod = "none"
    equipment_rating_mva: PerUnitBaseNumber | None = None
    linked_voltage_group_id: str | None = None
    manual_voltage_base_kv: PerUnitBaseNumber | None = None
    manual_ibase_ka: PerUnitBaseNumber | None = None
    # D1: Current Transformer instrument-transformer configuration.
    # Partial pair (primary without secondary or vice versa) is 422.
    # clear_ct=True removes any existing CT configuration; must not
    # be combined with ct_primary_a or ct_secondary_a.
    ct_primary_a: float | None = None
    ct_secondary_a: float | None = None
    ct_provenance_note: str | None = None
    clear_ct: bool = False


class SuggestGroupsRequest(BaseModel):
    """Empty body -- POST .../measurement-groups/suggest takes no
    parameters; a dedicated request model exists only so the endpoint
    has a documented, explicit action shape (never triggered implicitly
    -- task section 20)."""
