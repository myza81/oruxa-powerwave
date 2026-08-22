"""In-memory, ephemeral, workspace-scoped Per-Unit Base Profile registry
(Phase 5C, DEC-049).

A sibling registry to `WorkspaceRegistry`/`CalculatedChannelRegistry`
(same `threading` + `dict[(workspace_id, id), T]` shape, same
`add`/`get`/`list_for_workspace`/`remove_workspace`/`count` surface) --
see those modules' own docstrings for the shared locking-policy
rationale, unchanged here.

This registry additionally owns the per-channel assignment reverse index
(decision 7's `ChannelAssignment{mode, profile_id}`) and the
inheritance-recompute cascade that keeps a calculated channel's
automatically-inherited profile in sync with its own inputs.

**Invariant, enforced by every mutating method in this module**:
`PerUnitBaseProfile.assigned_channels` (the list surfaced on
`PerUnitProfileOut`, per profile) and the internal reverse index
(`dict[(workspace_id, ChannelRef), ChannelAssignment]`) are two views of
the exact same ownership fact and must never diverge. Every mutation
path -- manual assignment, explicit unassignment, confirmed
reassignment, automatic inherited reassignment, profile deletion, and
channel removal -- updates both sides atomically, under this registry's
own lock, in the same call. No method may touch one side without the
other.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from app.domain.calculated_channel import ChannelRef
from app.domain.per_unit import PerUnitBaseProfile, derive_per_unit_profile_id
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ChannelAlreadyAssignedError, PerUnitProfileNotFoundError

AssignmentMode = Literal["auto", "manual"]


@dataclass(slots=True)
class ChannelAssignment:
    """Decision 7's two independent axes. Absence of a record (no key in
    the reverse index) means "never touched" -- unambiguous for a source
    channel (which has no `"auto"` state to distinguish from) and only
    ever true for a calculated channel in the instant before its own
    creation call initializes this record (see
    `PerUnitRegistry.set_auto_assignment`'s call site in
    `create_calculated_channel`) -- never a steady-state a calculated
    channel is left in afterward."""

    mode: AssignmentMode
    profile_id: str | None


class PerUnitRegistry:
    """Thread-safe, in-memory store of PerUnitBaseProfile keyed by
    (workspace_id, profile_id), plus the channel-assignment reverse
    index described in the module docstring above."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[tuple[str, str], PerUnitBaseProfile] = {}
        self._assignments: dict[tuple[str, ChannelRef], ChannelAssignment] = {}

    # ------------------------------------------------------------
    # Profile storage
    # ------------------------------------------------------------

    def add(self, profile: PerUnitBaseProfile) -> None:
        with self._lock:
            self._profiles[(profile.workspace_id, profile.id)] = profile

    def get(self, workspace_id: str, profile_id: str) -> PerUnitBaseProfile | None:
        with self._lock:
            return self._profiles.get((workspace_id, profile_id))

    def list_for_workspace(self, workspace_id: str) -> list[PerUnitBaseProfile]:
        with self._lock:
            return [
                profile for (wid, _pid), profile in self._profiles.items() if wid == workspace_id
            ]

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every profile AND
        every channel-assignment record owned by `workspace_id`."""
        with self._lock:
            profile_keys = [key for key in self._profiles if key[0] == workspace_id]
            for key in profile_keys:
                del self._profiles[key]
            assignment_keys = [key for key in self._assignments if key[0] == workspace_id]
            for key in assignment_keys:
                del self._assignments[key]
            return len(profile_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)

    def delete_profile(self, workspace_id: str, profile_id: str) -> list[ChannelRef]:
        """Delete one profile. Every channel that pointed at it has its
        `profile_id` cleared to `None` **with `mode` left exactly as it
        was** (decision 7 -- a manually-assigned channel becomes
        `manual + None`, permanently unassigned; an auto one becomes
        `auto + None`, still eligible to resolve again later). Returns
        the affected `ChannelRef`s so the caller can run the recompute
        cascade from each of them (a channel whose profile just changed
        may itself have dependents)."""
        with self._lock:
            profile = self._profiles.pop((workspace_id, profile_id), None)
            if profile is None:
                raise PerUnitProfileNotFoundError(f"No per-unit profile '{profile_id}' in this workspace.")
            affected = list(profile.assigned_channels)
            for ref in affected:
                key = (workspace_id, ref)
                existing = self._assignments.get(key)
                if existing is not None:
                    self._assignments[key] = ChannelAssignment(mode=existing.mode, profile_id=None)
            return affected

    # ------------------------------------------------------------
    # Channel assignment reverse index
    # ------------------------------------------------------------

    def profile_for_channel(self, workspace_id: str, channel_ref: ChannelRef) -> str | None:
        with self._lock:
            record = self._assignments.get((workspace_id, channel_ref))
            return record.profile_id if record is not None else None

    def assignment_mode_for_channel(self, workspace_id: str, channel_ref: ChannelRef) -> AssignmentMode | None:
        with self._lock:
            record = self._assignments.get((workspace_id, channel_ref))
            return record.mode if record is not None else None

    def _reassign_locked(self, workspace_id: str, channel_ref: ChannelRef, mode: AssignmentMode, profile_id: str | None) -> bool:
        """Must be called with `self._lock` already held. Updates the
        reverse index AND both profiles' own `assigned_channels` lists
        (old owner loses it, new owner gains it) in one place, so the
        two representations can never diverge (see module docstring).
        Returns True if the channel's own resolved `profile_id` actually
        changed."""
        key = (workspace_id, channel_ref)
        existing = self._assignments.get(key)
        old_profile_id = existing.profile_id if existing is not None else None

        if old_profile_id is not None and old_profile_id != profile_id:
            old_profile = self._profiles.get((workspace_id, old_profile_id))
            if old_profile is not None and channel_ref in old_profile.assigned_channels:
                old_profile.assigned_channels.remove(channel_ref)

        if profile_id is not None and profile_id != old_profile_id:
            new_profile = self._profiles.get((workspace_id, profile_id))
            if new_profile is not None and channel_ref not in new_profile.assigned_channels:
                new_profile.assigned_channels.append(channel_ref)

        self._assignments[key] = ChannelAssignment(mode=mode, profile_id=profile_id)
        return profile_id != old_profile_id

    def set_manual_assignment(self, workspace_id: str, channel_ref: ChannelRef, profile_id: str | None) -> bool:
        """The ONLY entry point that ever writes `mode="manual"`. Used by
        `assign_channels()` for every channel explicitly listed (or
        explicitly omitted) in a profile PUT, and by the setup UI's
        explicit "unassign this channel" action (`profile_id=None`) --
        this is what makes `manual + None` reachable, distinct from a
        record that was simply never created."""
        with self._lock:
            return self._reassign_locked(workspace_id, channel_ref, "manual", profile_id)

    def set_auto_assignment(self, workspace_id: str, channel_ref: ChannelRef, profile_id: str | None) -> bool:
        """The ONLY entry point that ever writes `mode="auto"`. Used by
        calculated-channel creation (initializing the record for the
        first time) and by the recompute cascade below. Callers are
        responsible for having already confirmed the target is eligible
        for automatic recomputation (mode `"auto"`, or brand new) --
        this does not re-check."""
        with self._lock:
            return self._reassign_locked(workspace_id, channel_ref, "auto", profile_id)

    def assign_channels(
        self,
        workspace_id: str,
        profile_id: str,
        channel_refs: list[ChannelRef],
        *,
        reassign_conflicting: bool = False,
    ) -> list[ChannelRef]:
        """Decision 4's full-replace reconciliation for one profile's own
        PUT. Computes which of `channel_refs` are currently owned by a
        *different* profile (regardless of that owner's mode); if any
        exist and `reassign_conflicting` is False, raises
        `ChannelAlreadyAssignedError` and mutates nothing. Otherwise,
        every channel in `channel_refs` is set to manual+this profile,
        every channel that was previously on this profile but is now
        omitted is set to manual+None (explicit unassignment -- decision
        7's rule: touching a channel's assignment in this modal is
        always a manual act), and the list of every `ChannelRef` whose
        resolved `profile_id` actually changed is returned, for the
        caller to drive the recompute cascade.
        """
        with self._lock:
            profile = self._profiles.get((workspace_id, profile_id))
            if profile is None:
                raise PerUnitProfileNotFoundError(f"No per-unit profile '{profile_id}' in this workspace.")

            new_set = list(dict.fromkeys(channel_refs))  # de-duplicated, order-preserving
            conflicts: list[tuple[ChannelRef, str, str]] = []
            for ref in new_set:
                owner_id = self.profile_for_channel(workspace_id, ref)
                if owner_id is not None and owner_id != profile_id:
                    owner_profile = self._profiles.get((workspace_id, owner_id))
                    owner_name = owner_profile.name if owner_profile is not None else owner_id
                    conflicts.append((ref, owner_id, owner_name))

            if conflicts and not reassign_conflicting:
                raise ChannelAlreadyAssignedError(
                    "One or more channels are already assigned to a different per-unit base profile.",
                    conflicts=[
                        {"channel": ref, "profile_id": owner_id, "profile_name": owner_name}
                        for ref, owner_id, owner_name in conflicts
                    ],
                )

            previously_assigned = set(profile.assigned_channels)
            to_unassign = previously_assigned - set(new_set)

            changed: list[ChannelRef] = []
            for ref in to_unassign:
                if self._reassign_locked(workspace_id, ref, "manual", None):
                    changed.append(ref)
            for ref in new_set:
                if self._reassign_locked(workspace_id, ref, "manual", profile_id):
                    changed.append(ref)
            return changed

    def remove_channel_everywhere(self, workspace_id: str, channel_ref: ChannelRef) -> None:
        """Source/calculated-channel removal lifecycle: deletes the
        assignment record entirely (not just its `profile_id`) -- the
        channel itself is gone, so there is nothing left to preserve a
        mode for. Also strips it out of whichever profile's own
        `assigned_channels` list currently references it."""
        with self._lock:
            key = (workspace_id, channel_ref)
            existing = self._assignments.pop(key, None)
            if existing is not None and existing.profile_id is not None:
                profile = self._profiles.get((workspace_id, existing.profile_id))
                if profile is not None and channel_ref in profile.assigned_channels:
                    profile.assigned_channels.remove(channel_ref)


def recompute_inherited_per_unit_assignments(
    workspace_id: str,
    changed_channel_refs: list[ChannelRef],
    *,
    per_unit_registry: PerUnitRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> None:
    """Decision 7's inheritance cascade, made live rather than a
    one-time creation-time snapshot. Whenever any channel's resolved
    `profile_id` changes (a manual reassignment, an explicit
    unassignment, or a profile deletion clearing everyone who pointed at
    it), every calculated channel that directly depends on it must react
    -- unless that dependent's own assignment is `mode="manual"`, which
    is never auto-changed.

    An iterative queue (never recursive), using the EXISTING
    `CalculatedChannel.inputs` list as the only graph data needed -- the
    same composition trick `derive_engineering_type()` already relies on
    for transitive chains, so a change several calculated-from-calculated
    layers deep still propagates correctly with no separate dependency
    graph structure.
    """
    queue: list[ChannelRef] = list(changed_channel_refs)
    while queue:
        changed_ref = queue.pop()
        for channel in calc_registry.list_for_workspace(workspace_id):
            if changed_ref not in channel.inputs:
                continue
            own_ref = ChannelRef(kind="calculated", calculated_channel_id=channel.id)
            mode = per_unit_registry.assignment_mode_for_channel(workspace_id, own_ref)
            if mode == "manual":
                continue  # decision 7's hard rule: manual is never auto-changed.
            input_profile_ids = [
                per_unit_registry.profile_for_channel(workspace_id, input_ref) for input_ref in channel.inputs
            ]
            new_profile_id = derive_per_unit_profile_id(channel.operation, input_profile_ids)
            current_profile_id = per_unit_registry.profile_for_channel(workspace_id, own_ref)
            if new_profile_id != current_profile_id:
                per_unit_registry.set_auto_assignment(workspace_id, own_ref, new_profile_id)
                queue.append(own_ref)
