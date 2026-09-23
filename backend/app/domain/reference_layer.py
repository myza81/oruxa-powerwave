"""Compliance & Capability -- Reference Layer domain model (Slice 3).

A `ReferenceLayer` is the thin, workspace-owned association between one
Reference Profile (built-in or custom -- `profile_id` alone does not say
which; the service layer resolves that) and the Compliance page's own
active Comparison Chart configuration: is it currently active, and is it
currently visible. It owns no curve data itself (that stays entirely on
the referenced `ReferenceProfile`) and no compatibility/rendering state
(computed fresh on every request by the service layer, never cached
here) -- this dataclass is pure identity + the two pieces of state an
engineer actually toggles.

**Deliberately a separate action from profile deletion** (task section
10: "Profile deletion and layer removal are DIFFERENT actions -- removing
a layer must never delete the profile"). Removing a `ReferenceLayer`
never touches the `ReferenceProfileRegistry`; conversely, deleting a
custom profile the service layer already knows has active layers
referencing it removes those layers too (there is no valid state where a
layer's own `profile_id` points at nothing -- see
`app.services.reference_profile_service.delete_custom_profile()`'s own
docstring for that cascade).

**Independent of any recording/Measurement** (the mid-conversation
product requirement this slice was amended to satisfy): nothing on this
dataclass references a `source_id`, a Measurement Group, or an assessment
quantity. A layer can be created, listed, toggled and removed in a
workspace that has never had any source uploaded at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceLayer:
    id: str
    workspace_id: str
    profile_id: str
    visible: bool
    #: Stable, monotonically-increasing insertion order within a
    #: workspace -- used only for deterministic list/chart ordering
    #: (first-added layer first), never exposed as meaningful business
    #: data.
    order: int
