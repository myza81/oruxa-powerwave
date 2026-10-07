"""Compliance Event Alignment -- workspace-scoped orchestration (DEC-170; see
`app.domain.compliance_alignment` for the model and the ownership rule).

This is the canonical home of the committed alignment so a later Compliance
evaluation can read the same offset the chart shows. It never touches
Waveform state: no `SynchronizationRegistry`, no Time Group, no t0, no Cursor A,
no playback, no recording timestamp.

Lifecycle (decided, not guessed):

- one alignment per workspace, for the selected Bay / Measurement Group; setting
  it for another group REPLACES it (the old timestamp may not exist on the new
  recording's time base), and a read for a different group sees "not aligned";
- changing the Reference Layers never touches it (the disturbance is a property
  of the measurement, not of the Reference);
- it is dropped when its group or source no longer exists, and by "Start New
  Workspace" (`ComplianceAlignmentRegistry.remove_workspace`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.compliance_alignment import (
    ComplianceAlignment,
    alignment_offset_s,
    require_finite_origin,
    snap_to_sample,
)
from app.domain.measurement_group import KIND_VOLTAGE
from app.services.compliance_alignment_registry import ComplianceAlignmentRegistry
from app.services.errors import (
    ComplianceMeasurementGroupNotVoltageKindError,
    InvalidComplianceAlignmentError,
    MeasurementGroupNotFoundError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.workspace_registry import WorkspaceRegistry


@dataclass(frozen=True, slots=True)
class AlignmentView:
    measurement_group_id: str
    aligned: bool
    measurement_event_origin_s: float | None = None
    #: The amount added to a measurement time to get comparison time (= -origin).
    alignment_offset_s: float | None = None
    source_id: str | None = None


def _voltage_group(workspace_id: str, measurement_group_id: str, group_registry: MeasurementGroupRegistry):
    group = group_registry.get(workspace_id, measurement_group_id)
    if group is None:
        raise MeasurementGroupNotFoundError(f"No measurement group '{measurement_group_id}' in this workspace.")
    if group.kind != KIND_VOLTAGE:
        raise ComplianceMeasurementGroupNotVoltageKindError(
            f"Measurement group '{measurement_group_id}' is a Current group, not a Voltage group."
        )
    return group


def current_alignment(
    workspace_id: str, measurement_group_id: str, *, registry: ComplianceAlignmentRegistry,
    group_registry: MeasurementGroupRegistry, source_registry: WorkspaceRegistry,
) -> ComplianceAlignment | None:
    """The alignment that applies to `measurement_group_id`, or `None`."""
    stored = registry.get(workspace_id)
    if stored is None:
        return None
    # A vanished group or source leaves nothing the offset could refer to.
    if (
        group_registry.get(workspace_id, stored.measurement_group_id) is None
        or source_registry.get(workspace_id, stored.source_id) is None
    ):
        registry.clear(workspace_id)
        return None
    return stored if stored.measurement_group_id == measurement_group_id else None


def view_of(alignment: ComplianceAlignment | None, measurement_group_id: str) -> AlignmentView:
    if alignment is None:
        return AlignmentView(measurement_group_id=measurement_group_id, aligned=False)
    return AlignmentView(
        measurement_group_id=measurement_group_id, aligned=True,
        measurement_event_origin_s=alignment.measurement_event_origin_s,
        alignment_offset_s=alignment_offset_s(alignment.measurement_event_origin_s), source_id=alignment.source_id,
    )


def get_alignment(
    workspace_id: str, measurement_group_id: str, *, registry: ComplianceAlignmentRegistry,
    group_registry: MeasurementGroupRegistry, source_registry: WorkspaceRegistry,
) -> AlignmentView:
    _voltage_group(workspace_id, measurement_group_id, group_registry)
    return view_of(
        current_alignment(
            workspace_id, measurement_group_id, registry=registry, group_registry=group_registry,
            source_registry=source_registry,
        ),
        measurement_group_id,
    )


def set_alignment(
    workspace_id: str, measurement_group_id: str, *, measurement_event_origin_s: float, snap: bool,
    registry: ComplianceAlignmentRegistry, group_registry: MeasurementGroupRegistry, source_registry: WorkspaceRegistry,
) -> AlignmentView:
    """Stores the recording time that is Reference t = 0. With `snap` the
    request is moved to the nearest actual sample (tie -> earlier); without it
    (fine shift) the exact value is kept."""
    group = _voltage_group(workspace_id, measurement_group_id, group_registry)
    try:
        origin = require_finite_origin(measurement_event_origin_s)
    except ValueError as exc:
        raise InvalidComplianceAlignmentError(str(exc)) from exc
    active = source_registry.get(workspace_id, group.source_id)
    if active is None:
        raise InvalidComplianceAlignmentError("The measurement's recording is no longer loaded.")
    if snap:
        try:
            origin = snap_to_sample(active.record.waveform_data["time"].to_numpy(), origin)
        except ValueError as exc:
            raise InvalidComplianceAlignmentError(str(exc)) from exc
    alignment = ComplianceAlignment(
        workspace_id=workspace_id, measurement_group_id=measurement_group_id, source_id=group.source_id,
        measurement_event_origin_s=origin,
    )
    registry.set(alignment)
    return view_of(alignment, measurement_group_id)


def clear_alignment(
    workspace_id: str, measurement_group_id: str, *, registry: ComplianceAlignmentRegistry,
    group_registry: MeasurementGroupRegistry,
) -> AlignmentView:
    """Back to the measurement's own recording time. Clears only an alignment
    that belongs to this group (another group's is left alone)."""
    _voltage_group(workspace_id, measurement_group_id, group_registry)
    stored = registry.get(workspace_id)
    if stored is not None and stored.measurement_group_id == measurement_group_id:
        registry.clear(workspace_id)
    return view_of(None, measurement_group_id)
