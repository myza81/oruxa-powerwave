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

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.calculated_channel import ChannelRefIn, ChannelRefOut

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


class CurrentGroupConfigOut(BaseModel):
    """Only present on a `kind="current"` group's own `current_config`
    field. `resolved_ibase_ka`/`applicable_voltage_ll_kv` are read-only
    DERIVED information (Slice 4's own resolver) -- the frontend must
    never recompute `Ibase = Sbase / (sqrt(3) * Vbase_LL)` itself."""

    method: CurrentBaseMethod
    equipment_rating_mva: float | None
    linked_voltage_group_id: str | None
    manual_voltage_base_kv: float | None
    manual_ibase_ka: float | None
    resolved_ibase_ka: float | None
    applicable_voltage_ll_kv: float | None


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
    the group's existing base value untouched (there is no "clear"
    operation, matching `set_voltage_base()`'s own always-required-value
    contract). `reference_mode="manual"` requires `reference_override`;
    `reference_mode="auto"` (default) always returns the group to
    live auto-detection, clearing any previous override."""

    nominal_voltage_ll_kv: float | None = None
    reference_mode: VoltageReferenceMode = "auto"
    reference_override: VoltageReferenceValue | None = None


class CurrentGroupConfigUpdateRequest(BaseModel):
    """PUT body for a Current group's own configuration. Exactly one
    request shape per `method`, dispatched server-side to the matching
    Slice 4 setter -- the API never partially applies a method's own
    fields the way DEC-049's single flat PUT can; see
    `app.services.current_group_config_service`'s own per-method setter
    docstrings for the exact field requirements/mutual exclusivity this
    endpoint enforces (never re-validated here, only passed through)."""

    method: CurrentBaseMethod
    equipment_rating_mva: float | None = None
    linked_voltage_group_id: str | None = None
    manual_voltage_base_kv: float | None = None
    manual_ibase_ka: float | None = None


class SuggestGroupsRequest(BaseModel):
    """Empty body -- POST .../measurement-groups/suggest takes no
    parameters; a dedicated request model exists only so the endpoint
    has a documented, explicit action shape (never triggered implicitly
    -- task section 20)."""
