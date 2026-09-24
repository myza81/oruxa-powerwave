"""Compliance & Capability -- Reference Profile / Reference Layer service
layer (Slice 3). Orchestrates `app.domain.reference_profile` (pure
validation/rendering), `app.domain.reference_profile_builtins` (the
read-only built-in catalogue), `app.services.reference_profile_registry`
(custom profiles) and `app.services.reference_layer_registry` (active
layers) -- no new domain semantics live here, only wiring + the one
piece of cross-cutting policy this task assigns to the service layer:
compatibility classification against an optionally-selected Measurement
quantity.

**Independent of any recording/Measurement/workspace source** (the mid-
conversation product requirement this slice was amended to satisfy):
every function here takes only a `workspace_id` plus the two Reference
registries -- never a `WorkspaceRegistry`/`MeasurementGroupRegistry`, and
`selected_quantity_id` (the one place a Measurement concept appears at
all, in `compute_layer_compatibility()`/`build_comparison_chart()`) is
always optional, defaulting to `None`. A workspace that has never had a
source uploaded can create/list/duplicate/import/export profiles and
add/toggle/remove layers exactly the same as one that has -- see this
module's own tests for the direct proof.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from app.domain.reference_layer import ReferenceLayer
from app.domain.reference_profile import (
    BoundaryPoint,
    ReferenceProfile,
    ReferenceProfileValidationError,
    UnsupportedReferenceProfileSchemaVersionError,
    boundary_to_render_points,
    profile_from_json_dict,
    profile_to_json_dict,
    validate_reference_profile,
)
from app.domain.reference_profile_builtins import load_builtin_profiles
from app.services.errors import (
    ReferenceLayerNotFoundError,
    ReferenceProfileIsBuiltInError,
    ReferenceProfileNotFoundError,
    ReferenceProfileValidationServiceError,
    UnsupportedReferenceProfileSchemaVersionServiceError,
)
from app.services.reference_layer_registry import ReferenceLayerRegistry
from app.services.reference_profile_registry import ReferenceProfileRegistry

SOURCE_BUILT_IN = "built_in"
SOURCE_CUSTOM = "custom"

#: Three-way compatibility vocabulary (mid-conversation amendment: "no
#: Measurement selected" must NEVER collapse into "incompatible" -- it
#: is its own distinct, non-blocking state, mirroring the Analysis
#: three-level compatibility precedent (DEC-106/DEC-107) at the concept
#: level, though this is a much simpler single check, not a three-level
#: model of its own).
COMPATIBILITY_COMPATIBLE = "compatible"
COMPATIBILITY_NOT_YET_APPLICABLE = "not_yet_applicable"
COMPATIBILITY_INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class ReferenceProfileEntry:
    profile: ReferenceProfile
    source: str  # SOURCE_BUILT_IN | SOURCE_CUSTOM


def _find_builtin(profile_id: str, builtin_profiles: list[ReferenceProfile]) -> ReferenceProfile | None:
    for profile in builtin_profiles:
        if profile.id == profile_id:
            return profile
    return None


def list_profiles_for_workspace(workspace_id: str, *, custom_registry: ReferenceProfileRegistry) -> list[ReferenceProfileEntry]:
    """Built-ins first (stable catalogue order), then custom profiles --
    the caller/API is not required to preserve this order, but it makes
    a byte-stable response for a workspace with nothing custom yet."""
    entries = [ReferenceProfileEntry(profile=p, source=SOURCE_BUILT_IN) for p in load_builtin_profiles()]
    entries += [ReferenceProfileEntry(profile=p, source=SOURCE_CUSTOM) for p in custom_registry.list_for_workspace(workspace_id)]
    return entries


def get_profile_entry(
    workspace_id: str, profile_id: str, *, custom_registry: ReferenceProfileRegistry,
    builtin_profiles: list[ReferenceProfile] | None = None,
) -> ReferenceProfileEntry | None:
    custom = custom_registry.get(workspace_id, profile_id)
    if custom is not None:
        return ReferenceProfileEntry(profile=custom, source=SOURCE_CUSTOM)
    builtin = _find_builtin(profile_id, builtin_profiles if builtin_profiles is not None else load_builtin_profiles())
    return ReferenceProfileEntry(profile=builtin, source=SOURCE_BUILT_IN) if builtin is not None else None


def get_profile_entry_or_404(workspace_id: str, profile_id: str, *, custom_registry: ReferenceProfileRegistry) -> ReferenceProfileEntry:
    entry = get_profile_entry(workspace_id, profile_id, custom_registry=custom_registry)
    if entry is None:
        raise ReferenceProfileNotFoundError(f"No reference profile {profile_id!r} in workspace {workspace_id!r}.")
    return entry


def _raise_validation_error(exc: ReferenceProfileValidationError) -> None:
    raise ReferenceProfileValidationServiceError(
        exc.message, reason_code=exc.reason_code, boundary=exc.boundary,
        segment_index=exc.segment_index, field_name=exc.field_name,
    ) from exc


def _reject_if_builtin(profile_id: str) -> None:
    if _find_builtin(profile_id, load_builtin_profiles()) is not None:
        raise ReferenceProfileIsBuiltInError(
            f"Reference profile {profile_id!r} is built-in and read-only -- duplicate it to create an editable copy."
        )


def create_custom_profile(workspace_id: str, profile: ReferenceProfile, *, custom_registry: ReferenceProfileRegistry) -> ReferenceProfile:
    """`profile.id`/`profile.metadata.built_in` are always overwritten --
    a create can never choose its own id (avoids any collision with a
    built-in's file-stem id) and can never mint itself as built-in."""
    new_profile = replace(profile, id=str(uuid.uuid4()), metadata=replace(profile.metadata, built_in=False))
    try:
        validate_reference_profile(new_profile)
    except ReferenceProfileValidationError as exc:
        _raise_validation_error(exc)
    custom_registry.add(workspace_id, new_profile)
    return new_profile


def update_custom_profile(
    workspace_id: str, profile_id: str, profile: ReferenceProfile, *, custom_registry: ReferenceProfileRegistry,
) -> ReferenceProfile:
    """Full replace (mirrors `MeasurementGroupRegistry.update()`'s own
    convention) -- never a partial patch. Rejects a built-in target
    distinctly from a genuinely unknown one."""
    if custom_registry.get(workspace_id, profile_id) is None:
        _reject_if_builtin(profile_id)
        raise ReferenceProfileNotFoundError(f"No custom reference profile {profile_id!r} in workspace {workspace_id!r}.")
    updated = replace(profile, id=profile_id, metadata=replace(profile.metadata, built_in=False))
    try:
        validate_reference_profile(updated)
    except ReferenceProfileValidationError as exc:
        _raise_validation_error(exc)
    custom_registry.update(workspace_id, updated)
    return updated


def duplicate_profile(
    workspace_id: str, profile_id: str, *, custom_registry: ReferenceProfileRegistry, name_suffix: str = " (Copy)",
) -> ReferenceProfile:
    """Works for BOTH a built-in and a custom source profile (task
    section 8: built-ins allow "View, Duplicate only") -- the result is
    always a brand-new, independent custom profile; editing the copy
    never touches the original."""
    entry = get_profile_entry_or_404(workspace_id, profile_id, custom_registry=custom_registry)
    duplicated = replace(
        entry.profile, id=str(uuid.uuid4()), name=entry.profile.name + name_suffix,
        metadata=replace(entry.profile.metadata, built_in=False),
    )
    validate_reference_profile(duplicated)  # defense-in-depth -- source entry was already valid
    custom_registry.add(workspace_id, duplicated)
    return duplicated


def delete_custom_profile(
    workspace_id: str, profile_id: str, *, custom_registry: ReferenceProfileRegistry, layer_registry: ReferenceLayerRegistry,
) -> int:
    """Deletes a custom profile AND every active layer in this workspace
    referencing it. Task section 10 frames layer REMOVAL as never
    deleting the profile; the converse -- deleting a profile that active
    layers still reference -- has no valid alternative state: a
    `layer.profile_id` pointing at nothing is worse than removing the
    layers that would otherwise dangle. Returns the number of layers
    removed as a side effect. Rejects a built-in target distinctly from
    a genuinely unknown one, exactly like `update_custom_profile()`."""
    if custom_registry.get(workspace_id, profile_id) is None:
        _reject_if_builtin(profile_id)
        raise ReferenceProfileNotFoundError(f"No custom reference profile {profile_id!r} in workspace {workspace_id!r}.")
    removed_layers = 0
    for layer in layer_registry.list_for_profile(workspace_id, profile_id):
        if layer_registry.remove(workspace_id, layer.id):
            removed_layers += 1
    custom_registry.remove(workspace_id, profile_id)
    return removed_layers


def export_profile(workspace_id: str, profile_id: str, *, custom_registry: ReferenceProfileRegistry) -> dict:
    entry = get_profile_entry_or_404(workspace_id, profile_id, custom_registry=custom_registry)
    return profile_to_json_dict(entry.profile)


def import_profile(workspace_id: str, envelope: dict, *, custom_registry: ReferenceProfileRegistry) -> ReferenceProfile:
    """Task section 17: parse -> validate schema -> validate domain ->
    create a NEW custom session profile. Always mints a fresh id (never
    trusts anything in the file as identity) and always forces
    `metadata.built_in = False`, regardless of what the imported file's
    own metadata claims -- importing a file that happens to carry
    `built_in: true` (e.g. re-importing an exported built-in) still
    produces an ordinary editable custom profile, never a second,
    unmanaged "built-in"."""
    new_id = str(uuid.uuid4())
    try:
        profile = profile_from_json_dict(envelope, profile_id=new_id)
    except UnsupportedReferenceProfileSchemaVersionError as exc:
        raise UnsupportedReferenceProfileSchemaVersionServiceError(exc.message) from exc
    except ReferenceProfileValidationError as exc:
        _raise_validation_error(exc)
        raise AssertionError("unreachable")  # _raise_validation_error always raises
    profile = replace(profile, metadata=replace(profile.metadata, built_in=False))
    custom_registry.add(workspace_id, profile)
    return profile


def compute_layer_compatibility(profile: ReferenceProfile, *, selected_quantity_id: str | None) -> tuple[str, str | None]:
    """DEC-110 architecture refinement: a profile's own `evaluation_
    quantity` string (which this comparison used to check for equality
    against `selected_quantity_id`) no longer exists -- `assessment_
    definition` states a general representation/phase-treatment/member
    convention that does not, in general, correspond to exactly one
    canonical Compliance Slice 2 quantity id (e.g. `representation=
    line_line_rms, phase_treatment=minimum` -- "minimum of VAB/VBC/VCA"
    -- has no equivalent single canonical quantity at all). Determining
    whether a SELECTED Measurement's quantity can actually satisfy a
    profile's own required assessment trace requires a measurement
    RESOLVER (Va/Vb/Vc -> VAB/VBC/VCA derivation, min/max aggregation,
    positive-sequence calculation, each-phase evaluation) that does not
    exist yet -- explicit future-slice work (task section 15).

    Task section 12's own explicit instruction: "Do not introduce false
    incompatibility merely because assessment_definition != canonical
    measurement selector." Until the resolver exists, this function
    ALWAYS returns `COMPATIBILITY_NOT_YET_APPLICABLE` -- never a false
    `COMPATIBILITY_COMPATIBLE` (which would claim a trace can be derived
    when nothing has actually checked that) and never a false
    `COMPATIBILITY_INCOMPATIBLE` (which would reject a profile that a
    future resolver might satisfy perfectly well). The three-way
    vocabulary itself (`COMPATIBILITY_COMPATIBLE`/`COMPATIBILITY_
    INCOMPATIBLE` module constants) is kept defined for API/UI stability
    and for the resolver slice to start from -- mirroring `app.domain.
    compliance_measurement.STATUS_INVALID_BASE`'s own "remains defined
    for vocabulary stability; nothing currently triggers it" precedent."""
    if not selected_quantity_id:
        return COMPATIBILITY_NOT_YET_APPLICABLE, "No Measurement is currently selected -- compatibility is not yet applicable."
    return (
        COMPATIBILITY_NOT_YET_APPLICABLE,
        "Measurement comparison is not implemented yet -- compatibility cannot be determined until a "
        "future slice can derive this profile's own required assessment trace from a real recording.",
    )


# ---------------------------------------------------------------------
# Reference Layers
# ---------------------------------------------------------------------

def list_layers_for_workspace(workspace_id: str, *, layer_registry: ReferenceLayerRegistry) -> list[ReferenceLayer]:
    return layer_registry.list_for_workspace(workspace_id)


def add_layer(
    workspace_id: str, profile_id: str, *, visible: bool = True,
    custom_registry: ReferenceProfileRegistry, layer_registry: ReferenceLayerRegistry,
) -> ReferenceLayer:
    """No maximum active-layer count is enforced (task section 11)."""
    get_profile_entry_or_404(workspace_id, profile_id, custom_registry=custom_registry)
    layer = ReferenceLayer(
        id=str(uuid.uuid4()), workspace_id=workspace_id, profile_id=profile_id,
        visible=visible, order=layer_registry.next_order(workspace_id),
    )
    layer_registry.add(layer)
    return layer


def set_layer_visibility(workspace_id: str, layer_id: str, visible: bool, *, layer_registry: ReferenceLayerRegistry) -> ReferenceLayer:
    existing = layer_registry.get(workspace_id, layer_id)
    if existing is None:
        raise ReferenceLayerNotFoundError(f"No reference layer {layer_id!r} in workspace {workspace_id!r}.")
    updated = replace(existing, visible=visible)
    layer_registry.update(updated)
    return updated


def remove_layer(workspace_id: str, layer_id: str, *, layer_registry: ReferenceLayerRegistry) -> None:
    """Never touches `ReferenceProfileRegistry` -- removing a layer must
    never delete the profile it referenced (task section 10)."""
    if not layer_registry.remove(workspace_id, layer_id):
        raise ReferenceLayerNotFoundError(f"No reference layer {layer_id!r} in workspace {workspace_id!r}.")


# ---------------------------------------------------------------------
# Comparison Chart assembly (static rendering only -- no measured
# waveform, no evaluation; task section 14/18)
# ---------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ComparisonChartTrace:
    layer_id: str
    profile_id: str
    profile_name: str
    category: str
    boundary: str  # "lower" | "upper"
    unit: str
    visible: bool
    #: Whether this trace is actually plotted on the CURRENT chart axis
    #: -- False for an invisible layer, or a visible layer whose own
    #: unit differs from `ComparisonChart.axis_unit` (mid-conversation
    #: amendment: handle a genuine unit mismatch EXPLICITLY, never by
    #: silently converting or hiding it -- the layer/trace entry itself
    #: still appears, `on_axis=False` plus `unit`/`ComparisonChart.
    #: axis_unit` together are enough for the frontend to render an
    #: explicit "different unit -- not plotted" note).
    on_axis: bool
    compatibility_status: str
    compatibility_reason: str | None
    points: list[BoundaryPoint]


@dataclass(frozen=True, slots=True)
class ComparisonChart:
    traces: list[ComparisonChartTrace]
    #: The unit every `on_axis=True` trace shares -- `None` when there is
    #: no visible layer at all. Chosen as the first VISIBLE layer's own
    #: unit, by insertion order (task's own "active reference layers
    #: must share a compatible unit/basis" -- the first one establishes
    #: the axis, never a recording).
    axis_unit: str | None
    #: X-axis range recommendation -- the union of every VISIBLE layer's
    #: own `display_start_time`/`display_end_time` (mid-conversation
    #: amendment: axes must be derivable from the active profiles alone,
    #: never from a recording). `None` when there is no visible layer.
    x_min: float | None
    x_max: float | None
    #: unit -> [layer_id, ...] membership for EVERY active layer
    #: (visible or not) -- informational, lets a caller explain a unit
    #: mismatch without a second request.
    unit_groups: dict[str, list[str]]


def build_comparison_chart(
    workspace_id: str, *, custom_registry: ReferenceProfileRegistry, layer_registry: ReferenceLayerRegistry,
    selected_quantity_id: str | None = None,
) -> ComparisonChart:
    builtin_profiles = load_builtin_profiles()
    layers = layer_registry.list_for_workspace(workspace_id)
    resolved: list[tuple[ReferenceLayer, ReferenceProfile]] = []
    for layer in layers:
        entry = get_profile_entry(workspace_id, layer.profile_id, custom_registry=custom_registry, builtin_profiles=builtin_profiles)
        # A layer whose own profile has vanished (e.g. deleted through a
        # path that somehow bypassed delete_custom_profile()'s cascade)
        # is skipped, never crashes the whole chart -- matches this
        # codebase's own "one stale id must never blank out the rest of
        # the batch" convention (see app.api.v1.calculated_channels's
        # cursor/peak-value batch endpoints).
        if entry is not None:
            resolved.append((layer, entry.profile))

    axis_unit: str | None = None
    for layer, profile in resolved:
        if layer.visible:
            axis_unit = profile.unit
            break

    unit_groups: dict[str, list[str]] = {}
    traces: list[ComparisonChartTrace] = []
    display_starts: list[float] = []
    display_ends: list[float] = []
    for layer, profile in resolved:
        unit_groups.setdefault(profile.unit, []).append(layer.id)
        status, reason = compute_layer_compatibility(profile, selected_quantity_id=selected_quantity_id)
        on_axis = layer.visible and profile.unit == axis_unit
        if layer.visible:
            display_starts.append(profile.display_start_time)
            display_ends.append(profile.display_end_time)
        for boundary_name, boundary in (("lower", profile.lower_boundary), ("upper", profile.upper_boundary)):
            if boundary is None:
                continue
            points = boundary_to_render_points(boundary) if on_axis else []
            traces.append(ComparisonChartTrace(
                layer_id=layer.id, profile_id=profile.id, profile_name=profile.name, category=profile.category,
                boundary=boundary_name, unit=profile.unit, visible=layer.visible, on_axis=on_axis,
                compatibility_status=status, compatibility_reason=reason, points=points,
            ))

    return ComparisonChart(
        traces=traces,
        axis_unit=axis_unit,
        x_min=min(display_starts) if display_starts else None,
        x_max=max(display_ends) if display_ends else None,
        unit_groups=unit_groups,
    )
