"""In-memory, ephemeral, workspace-scoped Measurement Group registry
(Slice 1 of DEC-050's measurement-group-aware Per-Unit redesign --
internal scaffolding only, see app.domain.measurement_group's own
module docstring for full scope boundaries).

Mirrors `WorkspaceRegistry`/`CalculatedChannelRegistry`'s own exact
shape (`add`/`get`/`list_for_workspace`/`remove`/`remove_workspace`/
`count`, same `(workspace_id, id)` keying, same lock-scoping policy)
rather than inventing a new registry convention, plus two natural
extensions a per-source, multi-group resource needs that a 1:1
per-source resource (like `PerUnitRegistry`) does not: `list_for_source`
and a channel-membership reverse index (`group_for_channel`).

**Invariant this registry alone is responsible for enforcing**: a
channel can belong to at most one measurement group at a time, across
the whole workspace (the "no channel silently belonging to incompatible
duplicate groups" requirement). `_channel_index` (a `dict[(workspace_id,
ChannelRef), group_id]`) and every stored group's own `channel_refs`
list are two views of the same ownership fact and are updated together,
atomically, under `self._lock`, in every mutating method below (`add`,
`update`, `remove`, `remove_workspace`) -- never left for callers to
reconcile separately, the exact same invariant discipline
`PerUnitRegistry`'s own `assigned_channels`/reverse-index pairing
established (and the exact class of bug the profile-based Per-Unit
design's own now-retired assignment workflow had to guard against).

**`MeasurementGroup` is a plain, mutable (`slots=True`, not `frozen`)
dataclass, unlike `PerUnitBaseProfile`/`CalculatedChannel`'s own
callers, which always construct a brand-new object before every
upsert/add.** To stop a caller who fetches a group via `get()` and
mutates its `channel_refs` in place from silently corrupting this
registry's own "previous membership" snapshot before `update()` can
diff against it (a real bug caught by this module's own tests during
development -- `update()` needs the OLD membership to correctly release
channels the new membership drops, and that old state must survive
independently of whatever the caller does to their own copy), every
group that crosses this registry's boundary (`add`/`update` on the way
in, `get`/`list_for_workspace`/`list_for_source` on the way out) is
defensively copied via `_copy_group()`. The registry's own internal
`self._groups` dict is therefore never the same object a caller holds,
in either direction.

Semantic validation that requires data this registry does not own
(a channel's own `engineering_type`, whether a `source_id` is real) is
NOT this registry's job -- that lives in
`app.services.measurement_group_service`, which resolves that data via
`WorkspaceRegistry` before calling into this registry, mirroring
`PerUnitRegistry`'s own division of responsibility with
`per_unit_service.py`. This registry only re-checks what it alone can
verify correctly: cross-group channel uniqueness and no-duplicate-
within-one-group's-own-list, both purely structural facts about its own
stored state.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import MeasurementGroup
from app.services.errors import ChannelAlreadyGroupedError, DuplicateChannelReferenceError


def _copy_group(group: MeasurementGroup) -> MeasurementGroup:
    """A shallow copy is sufficient: `channel_refs` holds frozen/hashable
    `ChannelRef` elements (immutable), so only the LIST container itself
    -- not its elements -- needs its own independent identity."""
    return replace(group, channel_refs=list(group.channel_refs))


class MeasurementGroupRegistry:
    """Thread-safe, in-memory store of MeasurementGroup keyed by
    (workspace_id, measurement_group_id), plus the channel-membership
    reverse index described in the module docstring above."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: dict[tuple[str, str], MeasurementGroup] = {}
        self._channel_index: dict[tuple[str, ChannelRef], str] = {}

    # ------------------------------------------------------------
    # Internal helpers -- always called with self._lock already held.
    # ------------------------------------------------------------

    def _assert_no_duplicates_within(self, channel_refs: list[ChannelRef]) -> None:
        seen: set[ChannelRef] = set()
        for ref in channel_refs:
            if ref in seen:
                raise DuplicateChannelReferenceError(
                    f"Channel reference {ref!r} appears more than once in the same measurement group."
                )
            seen.add(ref)

    def _assert_channels_unclaimed(self, workspace_id: str, channel_refs: list[ChannelRef], *, owning_group_id: str | None) -> None:
        """Raises if any of `channel_refs` is already indexed under a
        DIFFERENT group than `owning_group_id` (the group being
        written -- `None` for a brand-new group, which can never
        legitimately already own anything)."""
        for ref in channel_refs:
            existing_group_id = self._channel_index.get((workspace_id, ref))
            if existing_group_id is not None and existing_group_id != owning_group_id:
                raise ChannelAlreadyGroupedError(
                    f"Channel reference {ref!r} already belongs to measurement group {existing_group_id!r}."
                )

    def _index_channels(self, workspace_id: str, group_id: str, channel_refs: list[ChannelRef]) -> None:
        for ref in channel_refs:
            self._channel_index[(workspace_id, ref)] = group_id

    def _deindex_channels(self, workspace_id: str, channel_refs: list[ChannelRef]) -> None:
        for ref in channel_refs:
            self._channel_index.pop((workspace_id, ref), None)

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    def add(self, group: MeasurementGroup) -> None:
        """Stores a brand-new group. Raises `DuplicateChannelReferenceError`
        if `group.channel_refs` contains the same reference twice, or
        `ChannelAlreadyGroupedError` if any referenced channel already
        belongs to a different group in this workspace -- both are
        defensive re-checks of what the service layer is expected to
        have already validated, never the primary place that validation
        happens (see module docstring)."""
        with self._lock:
            self._assert_no_duplicates_within(group.channel_refs)
            self._assert_channels_unclaimed(group.workspace_id, group.channel_refs, owning_group_id=None)
            stored = _copy_group(group)
            self._groups[(group.workspace_id, group.id)] = stored
            self._index_channels(stored.workspace_id, stored.id, stored.channel_refs)

    def get(self, workspace_id: str, measurement_group_id: str) -> MeasurementGroup | None:
        with self._lock:
            group = self._groups.get((workspace_id, measurement_group_id))
            return _copy_group(group) if group is not None else None

    def list_for_workspace(self, workspace_id: str) -> list[MeasurementGroup]:
        with self._lock:
            return [_copy_group(group) for (wid, _gid), group in self._groups.items() if wid == workspace_id]

    def list_for_source(self, workspace_id: str, source_id: str) -> list[MeasurementGroup]:
        with self._lock:
            return [
                _copy_group(group)
                for (wid, _gid), group in self._groups.items()
                if wid == workspace_id and group.source_id == source_id
            ]

    def group_for_channel(self, workspace_id: str, channel_ref: ChannelRef) -> str | None:
        with self._lock:
            return self._channel_index.get((workspace_id, channel_ref))

    def update(self, group: MeasurementGroup) -> None:
        """Full replace of an existing group's own fields (display_name/
        status/channel_refs) -- there is no partial-update concept at
        this layer, mirroring `PerUnitRegistry.upsert()`'s own
        full-replace convention. Re-validates the NEW `channel_refs`
        exactly like `add()`, except a channel currently owned by
        THIS SAME group's own prior membership is correctly treated as
        unclaimed (an update is allowed to keep or drop its own existing
        channels; only a channel owned by a DIFFERENT group is a genuine
        conflict). Raises `MeasurementGroupNotFoundError`-shaped
        behaviour is the service layer's job (checking `get()` first);
        this method assumes the group already exists and raises a plain
        `KeyError` if it does not, since it is never meant to be called
        directly as a create path."""
        with self._lock:
            key = (group.workspace_id, group.id)
            if key not in self._groups:
                raise KeyError(f"No existing measurement group {group.id!r} in workspace {group.workspace_id!r} to update.")
            self._assert_no_duplicates_within(group.channel_refs)
            self._assert_channels_unclaimed(group.workspace_id, group.channel_refs, owning_group_id=group.id)
            previous = self._groups[key]  # the registry's OWN stored object -- never the caller's
            self._deindex_channels(group.workspace_id, previous.channel_refs)
            stored = _copy_group(group)
            self._groups[key] = stored
            self._index_channels(stored.workspace_id, stored.id, stored.channel_refs)

    def remove(self, workspace_id: str, measurement_group_id: str) -> bool:
        with self._lock:
            group = self._groups.pop((workspace_id, measurement_group_id), None)
            if group is None:
                return False
            self._deindex_channels(workspace_id, group.channel_refs)
            return True

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every group AND
        every channel-index entry owned by `workspace_id`. Safe and
        idempotent for a workspace with no measurement groups."""
        with self._lock:
            keys = [key for key in self._groups if key[0] == workspace_id]
            for key in keys:
                group = self._groups.pop(key)
                self._deindex_channels(workspace_id, group.channel_refs)
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._groups)
