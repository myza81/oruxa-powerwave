"""In-memory, ephemeral, workspace-scoped registry for CUSTOM Reference
Profiles (Compliance Slice 3). Mirrors `MeasurementGroupRegistry`'s own
exact shape (`add`/`get`/`list_for_workspace`/`update`/`remove`/
`remove_workspace`/`count`, same lock-scoping policy, same CREATE-ONLY
`add()` contract) rather than inventing a new registry convention.

**Only CUSTOM profiles ever live here.** Built-in profiles
(`app.domain.reference_profile_builtins.load_builtin_profiles()`) are
workspace-agnostic, read-only, version-controlled data -- they are never
written to this registry, and this registry's own `id` space is
independent of the built-in catalogue's `id` space (the service layer,
`app.services.reference_profile_service`, is what merges both into one
list for a workspace and is responsible for keeping ids from colliding,
e.g. by namespacing custom ids as UUIDs, which cannot collide with a
built-in file's stem-derived id).

`ReferenceProfile` itself (see `app.domain.reference_profile`) carries no
`workspace_id` field -- it is a portable value object, not workspace-
owned state (that is the whole point of JSON export/import). This
registry is therefore the ONE place workspace scoping is applied, purely
via the `(workspace_id, id)` dict key -- unlike `MeasurementGroupRegistry`,
there is no reverse channel-membership index to maintain here, since a
profile claims no channel/source ownership at all.
"""

from __future__ import annotations

import threading

from app.domain.reference_profile import ReferenceProfile
from app.services.errors import ReferenceProfileAlreadyExistsError


class ReferenceProfileRegistry:
    """Thread-safe, in-memory store of custom `ReferenceProfile` objects
    keyed by `(workspace_id, profile_id)`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profiles: dict[tuple[str, str], ReferenceProfile] = {}

    def add(self, workspace_id: str, profile: ReferenceProfile) -> None:
        """CREATE-ONLY: raises `ReferenceProfileAlreadyExistsError` if
        `(workspace_id, profile.id)` already exists -- never an implicit
        upsert. Use `update()` to replace an existing custom profile."""
        with self._lock:
            key = (workspace_id, profile.id)
            if key in self._profiles:
                raise ReferenceProfileAlreadyExistsError(
                    f"Reference profile {profile.id!r} already exists in workspace {workspace_id!r}; "
                    "use update() to replace an existing profile."
                )
            self._profiles[key] = profile

    def get(self, workspace_id: str, profile_id: str) -> ReferenceProfile | None:
        with self._lock:
            return self._profiles.get((workspace_id, profile_id))

    def list_for_workspace(self, workspace_id: str) -> list[ReferenceProfile]:
        with self._lock:
            return [profile for (wid, _pid), profile in self._profiles.items() if wid == workspace_id]

    def update(self, workspace_id: str, profile: ReferenceProfile) -> None:
        """Full replace of an existing custom profile's own fields.
        Raises `KeyError` if it does not already exist -- the service
        layer is responsible for the caller-facing 404 (checking `get()`
        first), mirroring `MeasurementGroupRegistry.update()`'s own
        contract."""
        with self._lock:
            key = (workspace_id, profile.id)
            if key not in self._profiles:
                raise KeyError(f"No existing custom reference profile {profile.id!r} in workspace {workspace_id!r} to update.")
            self._profiles[key] = profile

    def remove(self, workspace_id: str, profile_id: str) -> bool:
        with self._lock:
            return self._profiles.pop((workspace_id, profile_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        """"Start New Workspace" counterpart -- releases every custom
        profile owned by `workspace_id`. Safe and idempotent for a
        workspace with none."""
        with self._lock:
            keys = [key for key in self._profiles if key[0] == workspace_id]
            for key in keys:
                del self._profiles[key]
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)
