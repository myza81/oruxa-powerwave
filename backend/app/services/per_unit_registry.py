"""In-memory, ephemeral, workspace-scoped Per-Unit Base configuration
registry (Phase 5C, DEC-049; source-bound redesign following owner UAT).

A sibling registry to `WorkspaceRegistry`/`CalculatedChannelRegistry`
(same `threading` + `dict[(workspace_id, id), T]` shape) -- see those
modules' own docstrings for the shared locking-policy rationale,
unchanged here. Keyed by `(workspace_id, source_id)` -- a configuration
IS the source's own configuration, 1:1, never a separately-identified
"profile" the engineer creates or assigns (owner UAT on the original
profile-based design found that workflow too complex).

Every Voltage/Current SOURCE channel automatically resolves to its own
owning source's configuration -- `profile_for_channel()` computes this
directly (source_id + engineering_type), with no per-channel assignment
record to create, store, or keep in sync. This is the single biggest
simplification over the original design: there is no more reverse
index/denormalized-list-divergence invariant to maintain for source
channels at all.

CALCULATED channels are the one place a per-channel assignment record
still exists (the owner's own explicit instruction: "Do not redesign
calculated-channel PU behaviour in this task" -- decision 6/7's
two-axis `{mode, profile_id}` model and its live recompute-on-parent-
change cascade are preserved verbatim; only the "profile_id" flowing
through them is now always literally a `source_id`, since a "profile"
and a "source's own configuration" are now the same thing).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import CURRENT, UNDEFINED, VOLTAGE
from app.domain.per_unit import PerUnitBaseProfile, derive_per_unit_profile_id
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.workspace_registry import WorkspaceRegistry

AssignmentMode = Literal["auto", "manual"]


@dataclass(slots=True)
class ChannelAssignment:
    """Decision 7's two independent axes, scoped to CALCULATED channels
    only under the source-bound redesign (a source channel has no
    inheritance concept -- see module docstring). Absence of a record (no
    key in `_calc_assignments`) means "never touched"; a calculated
    channel's own record is created the instant it is created and
    persists for its whole lifetime, never absent again afterward."""

    mode: AssignmentMode
    profile_id: str | None  # always a source_id, or None


class PerUnitRegistry:
    """Thread-safe, in-memory store of PerUnitBaseProfile keyed by
    (workspace_id, source_id), plus the calculated-channel assignment
    index described in the module docstring above."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[tuple[str, str], PerUnitBaseProfile] = {}
        self._calc_assignments: dict[tuple[str, str], ChannelAssignment] = {}

    # ------------------------------------------------------------
    # Source configuration storage
    # ------------------------------------------------------------

    def upsert(self, profile: PerUnitBaseProfile) -> None:
        """Create-or-replace this source's own configuration entirely --
        there is no partial-update concept (the API layer always submits
        the full configuration, mirroring every other PUT in this
        codebase)."""
        with self._lock:
            self._profiles[(profile.workspace_id, profile.source_id)] = profile

    def get(self, workspace_id: str, source_id: str) -> PerUnitBaseProfile | None:
        with self._lock:
            return self._profiles.get((workspace_id, source_id))

    def list_for_workspace(self, workspace_id: str) -> list[PerUnitBaseProfile]:
        with self._lock:
            return [profile for (wid, _sid), profile in self._profiles.items() if wid == workspace_id]

    def delete(self, workspace_id: str, source_id: str) -> bool:
        """Clears this source's own configuration. Idempotent (returns
        False, not an error, for an unconfigured/unknown source_id) --
        matching this codebase's own established idempotent-DELETE
        convention (app.api.v1.workspaces.delete_workspace). The caller
        (app.services.per_unit_service) runs the recompute cascade,
        seeded with `source_id`, when this returns True -- any
        calculated channel auto-inheriting from this source must react."""
        with self._lock:
            return self._profiles.pop((workspace_id, source_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every
        configuration AND every calculated-channel assignment record
        owned by `workspace_id`."""
        with self._lock:
            profile_keys = [key for key in self._profiles if key[0] == workspace_id]
            for key in profile_keys:
                del self._profiles[key]
            assignment_keys = [key for key in self._calc_assignments if key[0] == workspace_id]
            for key in assignment_keys:
                del self._calc_assignments[key]
            return len(profile_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)

    # ------------------------------------------------------------
    # Per-channel resolution
    # ------------------------------------------------------------

    def profile_for_channel(self, workspace_id: str, channel_ref: ChannelRef, engineering_type: str) -> str | None:
        """The ONE read accessor every display/measurement endpoint and
        the recompute cascade use. A SOURCE channel resolves
        automatically -- no assignment record involved at all: eligible
        (Voltage/Current) channels of a configured source always use
        that source's own configuration; anything else is `None`. A
        CALCULATED channel reads its own tracked auto/manual assignment
        record (decision 7, unchanged)."""
        if channel_ref.kind == "source":
            if engineering_type not in (VOLTAGE, CURRENT):
                return None
            profile = self.get(workspace_id, channel_ref.source_id)
            return profile.source_id if profile is not None else None
        return self.profile_for_calculated_channel(workspace_id, channel_ref.calculated_channel_id)

    # ------------------------------------------------------------
    # Calculated-channel assignment (decision 6/7, unchanged)
    # ------------------------------------------------------------

    def profile_for_calculated_channel(self, workspace_id: str, calculated_channel_id: str) -> str | None:
        with self._lock:
            record = self._calc_assignments.get((workspace_id, calculated_channel_id))
            return record.profile_id if record is not None else None

    def assignment_mode_for_calculated_channel(self, workspace_id: str, calculated_channel_id: str) -> AssignmentMode | None:
        with self._lock:
            record = self._calc_assignments.get((workspace_id, calculated_channel_id))
            return record.mode if record is not None else None

    def set_manual_assignment_for_calculated_channel(
        self, workspace_id: str, calculated_channel_id: str, profile_id: str | None
    ) -> bool:
        """The ONLY entry point that ever writes `mode="manual"`. Used by
        the setup UI's explicit assign/unassign action on a calculated
        channel (out of scope for THIS redesign pass -- preserved as-is
        per the owner's own "do not redesign calculated-channel PU
        behaviour" instruction). Returns True if the resolved
        `profile_id` actually changed."""
        with self._lock:
            key = (workspace_id, calculated_channel_id)
            existing = self._calc_assignments.get(key)
            changed = existing is None or existing.profile_id != profile_id
            self._calc_assignments[key] = ChannelAssignment(mode="manual", profile_id=profile_id)
            return changed

    def set_auto_assignment_for_calculated_channel(
        self, workspace_id: str, calculated_channel_id: str, profile_id: str | None
    ) -> bool:
        """The ONLY entry point that ever writes `mode="auto"`. Used by
        calculated-channel creation (initializing the record for the
        first time) and by the recompute cascade below."""
        with self._lock:
            key = (workspace_id, calculated_channel_id)
            existing = self._calc_assignments.get(key)
            changed = existing is None or existing.profile_id != profile_id
            self._calc_assignments[key] = ChannelAssignment(mode="auto", profile_id=profile_id)
            return changed

    def remove_calculated_channel(self, workspace_id: str, calculated_channel_id: str) -> None:
        """Calculated-channel removal lifecycle: deletes its own
        assignment record entirely -- the channel itself is gone, so
        there is nothing left to preserve a mode for."""
        with self._lock:
            self._calc_assignments.pop((workspace_id, calculated_channel_id), None)


def _engineering_type_for_input(
    channel_ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry, calc_registry: CalculatedChannelRegistry
) -> str:
    """Same "look up the already-classified channel" pattern
    app.services.calculated_channel_service's own `_resolve_input` uses
    -- deliberately lightweight (no array data touched) since the
    recompute cascade may walk many calculated channels' own inputs."""
    if channel_ref.kind == "source":
        active = source_registry.get(workspace_id, channel_ref.source_id)
        if active is None:
            return UNDEFINED
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_ref.channel_name), None)
        return matching.engineering_type if matching is not None else UNDEFINED
    calc = calc_registry.get(workspace_id, channel_ref.calculated_channel_id)
    return calc.engineering_type if calc is not None else UNDEFINED


def recompute_inherited_per_unit_assignments(
    workspace_id: str,
    changed_ids: list[str],
    *,
    per_unit_registry: PerUnitRegistry,
    calc_registry: CalculatedChannelRegistry,
    source_registry: WorkspaceRegistry,
) -> None:
    """Decision 7's inheritance cascade (unchanged rule, source-bound
    identities). Whenever any SOURCE's own configuration changes
    (created/updated/deleted) or any CALCULATED channel's own resolved
    profile changes, every calculated channel that directly depends on
    it must react -- unless that dependent's own assignment is
    `mode="manual"`, which is never auto-changed. `changed_ids` are
    source_ids and/or calculated_channel_ids (both id spaces are walked
    identically -- a dependent's `inputs` list already distinguishes
    which kind each entry is).

    An iterative queue (never recursive), using the EXISTING
    `CalculatedChannel.inputs` list as the only graph data needed -- the
    same composition trick `derive_engineering_type()` already relies on
    for transitive chains.
    """
    queue: list[str] = list(changed_ids)
    while queue:
        changed_id = queue.pop()
        for channel in calc_registry.list_for_workspace(workspace_id):
            depends_on_changed = any(
                (inp.kind == "source" and inp.source_id == changed_id)
                or (inp.kind == "calculated" and inp.calculated_channel_id == changed_id)
                for inp in channel.inputs
            )
            if not depends_on_changed:
                continue
            mode = per_unit_registry.assignment_mode_for_calculated_channel(workspace_id, channel.id)
            if mode == "manual":
                continue  # decision 7's hard rule: manual is never auto-changed.
            input_profile_ids = [
                per_unit_registry.profile_for_channel(
                    workspace_id, inp,
                    _engineering_type_for_input(inp, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry),
                )
                for inp in channel.inputs
            ]
            new_profile_id = derive_per_unit_profile_id(channel.operation, input_profile_ids)
            current_profile_id = per_unit_registry.profile_for_calculated_channel(workspace_id, channel.id)
            if new_profile_id != current_profile_id:
                per_unit_registry.set_auto_assignment_for_calculated_channel(workspace_id, channel.id, new_profile_id)
                queue.append(channel.id)
