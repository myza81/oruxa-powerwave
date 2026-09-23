"""In-memory, ephemeral, workspace-scoped registry for Reference Layers
(Compliance Slice 3) -- mirrors `MeasurementGroupRegistry`'s /
`ReferenceProfileRegistry`'s own exact shape (`add`/`get`/
`list_for_workspace`/`update`/`remove`/`remove_workspace`/`count`, same
lock-scoping policy, same CREATE-ONLY `add()` contract).

No artificial maximum on active layers is enforced here (task section
11) -- `add()` never rejects on count.
"""

from __future__ import annotations

import threading

from app.domain.reference_layer import ReferenceLayer
from app.services.errors import ReferenceLayerAlreadyExistsError


class ReferenceLayerRegistry:
    """Thread-safe, in-memory store of `ReferenceLayer` objects keyed by
    `(workspace_id, layer_id)`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._layers: dict[tuple[str, str], ReferenceLayer] = {}
        #: Next insertion-order value to hand out per workspace -- never
        #: reused even after removals, so ordering stays stable across a
        #: remove-then-re-add of the same profile (task's own "remove a
        #: layer without deleting the profile, then add it back"
        #: acceptance scenario places the re-added layer LAST, matching
        #: how an engineer would expect a freshly re-added layer to
        #: behave, not silently reclaiming its old position).
        self._next_order: dict[str, int] = {}

    def add(self, layer: ReferenceLayer) -> None:
        with self._lock:
            key = (layer.workspace_id, layer.id)
            if key in self._layers:
                raise ReferenceLayerAlreadyExistsError(
                    f"Reference layer {layer.id!r} already exists in workspace {layer.workspace_id!r}."
                )
            self._layers[key] = layer

    def next_order(self, workspace_id: str) -> int:
        with self._lock:
            order = self._next_order.get(workspace_id, 0)
            self._next_order[workspace_id] = order + 1
            return order

    def get(self, workspace_id: str, layer_id: str) -> ReferenceLayer | None:
        with self._lock:
            return self._layers.get((workspace_id, layer_id))

    def list_for_workspace(self, workspace_id: str) -> list[ReferenceLayer]:
        with self._lock:
            layers = [layer for (wid, _lid), layer in self._layers.items() if wid == workspace_id]
        return sorted(layers, key=lambda layer: layer.order)

    def list_for_profile(self, workspace_id: str, profile_id: str) -> list[ReferenceLayer]:
        """Every layer (in this workspace) currently referencing
        `profile_id` -- used by the profile-deletion cascade (see
        `app.domain.reference_layer`'s own module docstring)."""
        with self._lock:
            return [
                layer for (wid, _lid), layer in self._layers.items()
                if wid == workspace_id and layer.profile_id == profile_id
            ]

    def update(self, layer: ReferenceLayer) -> None:
        with self._lock:
            key = (layer.workspace_id, layer.id)
            if key not in self._layers:
                raise KeyError(f"No existing reference layer {layer.id!r} in workspace {layer.workspace_id!r} to update.")
            self._layers[key] = layer

    def remove(self, workspace_id: str, layer_id: str) -> bool:
        with self._lock:
            return self._layers.pop((workspace_id, layer_id), None) is not None

    def remove_workspace(self, workspace_id: str) -> int:
        with self._lock:
            keys = [key for key in self._layers if key[0] == workspace_id]
            for key in keys:
                del self._layers[key]
            self._next_order.pop(workspace_id, None)
            return len(keys)

    def count(self) -> int:
        with self._lock:
            return len(self._layers)
