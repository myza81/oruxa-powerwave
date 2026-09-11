"""In-memory, ephemeral, workspace-scoped Engineering Context registry
(Analysis Guardrail Slice 1).

Mirrors `MeasurementGroupRegistry`'s own exact shape (`add`/`get`/
`list_for_workspace`/`update`/`remove`/`remove_workspace`/`count`, same
`(workspace_id, id)` keying, same lock-scoping policy, same channel-
membership reverse index) -- see that module's own docstring for the
full rationale, reused here unchanged. The one structural difference:
`EngineeringContext` has no `source_id` (a context may span multiple
sources, per its own domain-model docstring), so there is no
`list_for_source` here.

**Invariant this registry alone is responsible for enforcing**: a
channel can belong to at most one Engineering Context at a time, across
the whole workspace -- mirrors `MeasurementGroupRegistry`'s own "no
channel silently belonging to incompatible duplicate groups" invariant,
applied to contexts (a channel playing a role in two different physical
bays at once would be a contradiction, not a legitimate state).

Semantic validation that requires data this registry does not own (does
a channel/calculated channel actually exist, what workspace state
justifies a phase assignment) is NOT this registry's job -- that lives
in `app.services.engineering_context_service`, mirroring
`measurement_group_service`'s own division of responsibility.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from app.domain.calculated_channel import ChannelRef
from app.domain.engineering_context import EngineeringContext, EngineeringContextMember
from app.services.errors import (
    ChannelAlreadyInContextError,
    DuplicateChannelReferenceInContextError,
    EngineeringContextAlreadyExistsError,
)


def _copy_context(context: EngineeringContext) -> EngineeringContext:
    """Shallow copy sufficient for the same reason
    `measurement_group_registry._copy_group` gives: `ChannelRef` is
    frozen/hashable, so only the containing lists (`members`, and each
    member's own mutable dataclass) need independent identity."""
    return replace(
        context,
        members=[replace(member) for member in context.members],
    )


class EngineeringContextRegistry:
    """Thread-safe, in-memory store of EngineeringContext keyed by
    (workspace_id, engineering_context_id), plus the channel-membership
    reverse index described in the module docstring above."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._contexts: dict[tuple[str, str], EngineeringContext] = {}
        self._channel_index: dict[tuple[str, ChannelRef], str] = {}

    # ------------------------------------------------------------
    # Internal helpers -- always called with self._lock already held.
    # ------------------------------------------------------------

    def _assert_no_duplicates_within(self, members: list[EngineeringContextMember]) -> None:
        seen: set[ChannelRef] = set()
        for member in members:
            if member.channel_ref in seen:
                raise DuplicateChannelReferenceInContextError(
                    f"Channel reference {member.channel_ref!r} appears more than once in the same "
                    "Engineering Context."
                )
            seen.add(member.channel_ref)

    def _assert_channels_unclaimed(
        self, workspace_id: str, members: list[EngineeringContextMember], *, owning_context_id: str | None
    ) -> None:
        for member in members:
            existing_context_id = self._channel_index.get((workspace_id, member.channel_ref))
            if existing_context_id is not None and existing_context_id != owning_context_id:
                raise ChannelAlreadyInContextError(
                    f"Channel reference {member.channel_ref!r} already belongs to Engineering Context "
                    f"{existing_context_id!r}."
                )

    def _index_channels(self, workspace_id: str, context_id: str, members: list[EngineeringContextMember]) -> None:
        for member in members:
            self._channel_index[(workspace_id, member.channel_ref)] = context_id

    def _deindex_channels(self, workspace_id: str, members: list[EngineeringContextMember]) -> None:
        for member in members:
            self._channel_index.pop((workspace_id, member.channel_ref), None)

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    def add(self, context: EngineeringContext) -> None:
        """Stores a brand-new context. CREATE-ONLY: raises
        `EngineeringContextAlreadyExistsError` if `(workspace_id, id)`
        already exists. Also raises `DuplicateChannelReferenceInContextError`
        / `ChannelAlreadyInContextError` -- both defensive re-checks of
        what the service layer is expected to have already validated.
        Every check runs BEFORE any mutation."""
        with self._lock:
            key = (context.workspace_id, context.id)
            if key in self._contexts:
                raise EngineeringContextAlreadyExistsError(
                    f"Engineering Context {context.id!r} already exists in workspace {context.workspace_id!r}; "
                    "use update() to replace an existing context."
                )
            self._assert_no_duplicates_within(context.members)
            self._assert_channels_unclaimed(context.workspace_id, context.members, owning_context_id=None)
            stored = _copy_context(context)
            self._contexts[key] = stored
            self._index_channels(stored.workspace_id, stored.id, stored.members)

    def get(self, workspace_id: str, engineering_context_id: str) -> EngineeringContext | None:
        with self._lock:
            context = self._contexts.get((workspace_id, engineering_context_id))
            return _copy_context(context) if context is not None else None

    def list_for_workspace(self, workspace_id: str) -> list[EngineeringContext]:
        with self._lock:
            return [_copy_context(ctx) for (wid, _cid), ctx in self._contexts.items() if wid == workspace_id]

    def context_for_channel(self, workspace_id: str, channel_ref: ChannelRef) -> str | None:
        with self._lock:
            return self._channel_index.get((workspace_id, channel_ref))

    def update(self, context: EngineeringContext) -> None:
        """Full replace of an existing context's own fields
        (display_name/status/members) -- mirrors
        `MeasurementGroupRegistry.update()`'s own full-replace contract
        and correct de-index/re-index sequencing. Raises a plain
        `KeyError` if the context does not already exist -- the service
        layer is responsible for the not-found -> structured-error
        translation, exactly like its Measurement Group counterpart."""
        with self._lock:
            key = (context.workspace_id, context.id)
            if key not in self._contexts:
                raise KeyError(
                    f"No existing Engineering Context {context.id!r} in workspace {context.workspace_id!r} to update."
                )
            self._assert_no_duplicates_within(context.members)
            self._assert_channels_unclaimed(context.workspace_id, context.members, owning_context_id=context.id)
            previous = self._contexts[key]
            self._deindex_channels(context.workspace_id, previous.members)
            stored = _copy_context(context)
            self._contexts[key] = stored
            self._index_channels(stored.workspace_id, stored.id, stored.members)

    def remove(self, workspace_id: str, engineering_context_id: str) -> bool:
        with self._lock:
            context = self._contexts.pop((workspace_id, engineering_context_id), None)
            if context is None:
                return False
            self._deindex_channels(workspace_id, context.members)
            return True

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every context AND
        every channel-index entry owned by `workspace_id`. Safe and
        idempotent for a workspace with no Engineering Contexts."""
        with self._lock:
            keys = [key for key in self._contexts if key[0] == workspace_id]
            for key in keys:
                context = self._contexts.pop(key)
                self._deindex_channels(workspace_id, context.members)
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._contexts)
