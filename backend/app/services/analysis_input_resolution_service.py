"""Automatic Analysis Input Resolver -- orchestration layer (Analysis
Guardrail Slice 2; see docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md).

Sits above the pure `app.domain.analysis_input_resolution.
resolve_requirement()` exactly the way `measurement_group_service.py`
sits above its own domain module: this layer is the only place that
touches `EngineeringContextRegistry`/`WorkspaceRegistry`/
`CalculatedChannelRegistry`, resolves each context member's own live
engineering metadata (`ResolvedCandidate`), and -- the one piece of
resolution logic that genuinely needs I/O and therefore cannot live in
the pure domain module -- proves cross-source TIMEBASE compatibility
among the roles the pure resolver already matched, reusing
`app.domain.calculated_channel.timebases_aligned()` unchanged (never a
new alignment rule, never resampling/interpolation).

**Why the timebase check is layered on AFTER the pure match, not
folded into it**: `resolve_requirement()` only needs each candidate's
already-known `engineering_type`/`phase`/`unit` (all metadata, already
in memory) to decide role identity; genuine timebase PROOF needs actual
sample arrays plus each source's own absolute start time -- I/O this
service intentionally defers until AFTER role matching has already
narrowed things down to at most one candidate per role, so the (small,
cheap) array fetch only ever happens for the handful of candidates a
requirement actually needs, never for every context member.

**Input resolution is configuration/selection work, evaluated on
demand -- never subscribed to Playback, never re-run at animation-frame
frequency** (owner's own explicit separation). This module has no
notion of a "current time" at all.
"""

from __future__ import annotations

import numpy as np

from app.domain.analysis_input_resolution import (
    REASON_TIMEBASE_INCOMPATIBLE,
    STATUS_NEEDS_CONFIGURATION,
    STATUS_RESOLVED,
    AnalysisInputResolution,
    ResolvedCandidate,
    resolve_requirement,
)
from app.domain.analysis_requirements import get_requirement
from app.domain.calculated_channel import ChannelRef, timebases_aligned
from app.domain.time_grouping import normalize_absolute_datetime
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.errors import EngineeringContextNotFoundError, UnknownAnalysisRequirementError
from app.services.workspace_registry import WorkspaceRegistry


def _source_start_epoch(active) -> float | None:
    """Mirrors `calculated_channel_service._source_start_epoch()`
    exactly (same naive-datetime-ambiguity fix, same
    `normalize_absolute_datetime()` call) -- deliberately a separate,
    locally-owned copy rather than importing that module's own private
    helper, matching this codebase's own established convention of each
    module owning its small resolution helpers (see
    `app.domain.engineering_context_detection`'s own docstring for the
    same reasoning applied to phase-suffix vocabulary)."""
    if active.metadata.start_time is None:
        return None
    return normalize_absolute_datetime(active.metadata.start_time).timestamp()


def _resolve_candidate_metadata(
    member, *, workspace_id: str, source_registry: WorkspaceRegistry, calculated_channel_registry: CalculatedChannelRegistry
) -> ResolvedCandidate | None:
    """Resolves ONE Engineering Context member's own live engineering
    metadata -- engineering_type/unit only, never full sample arrays
    (those are fetched separately, only for roles the pure resolver
    actually matched, and only when a cross-source timebase proof is
    genuinely needed -- see module docstring). Returns `None` for a
    member whose channel no longer exists (defensive; Slice 1's own
    write-path validation already keeps this unreachable in practice --
    a stale member is simply excluded from candidates rather than
    raising, so a resolution request never 500s over an unrelated,
    already-pruned member)."""
    ref = member.channel_ref
    if ref.kind == "source":
        active = source_registry.get(workspace_id, ref.source_id)
        if active is None:
            return None
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == ref.channel_name), None)
        if matching is None:
            return None
        return ResolvedCandidate(
            channel_ref=ref, engineering_type=matching.engineering_type,
            phase=member.phase, phase_source=member.phase_source, unit=matching.unit,
        )
    calculated = calculated_channel_registry.get(workspace_id, ref.calculated_channel_id)
    if calculated is None:
        return None
    return ResolvedCandidate(
        channel_ref=ref, engineering_type=calculated.engineering_type,
        phase=member.phase, phase_source=member.phase_source, unit=calculated.unit,
    )


def _timebase_identity(
    channel_ref: ChannelRef, *, workspace_id: str, source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> tuple[str, np.ndarray, float | None] | None:
    """Returns `(reference_source_id, elapsed_time_array, start_epoch)`
    for one resolved role's own channel -- the exact three facts
    `timebases_aligned()` needs. `None` if the channel can no longer be
    resolved (same defensive posture as `_resolve_candidate_metadata`)."""
    if channel_ref.kind == "source":
        active = source_registry.get(workspace_id, channel_ref.source_id)
        if active is None:
            return None
        elapsed = active.record.waveform_data["time"].to_numpy()
        return channel_ref.source_id, elapsed, _source_start_epoch(active)
    calculated = calculated_channel_registry.get(workspace_id, channel_ref.calculated_channel_id)
    if calculated is None:
        return None
    reference_source = source_registry.get(workspace_id, calculated.reference_source_id)
    start_epoch = _source_start_epoch(reference_source) if reference_source is not None else None
    return calculated.reference_source_id, calculated.time, start_epoch


def _apply_timebase_check(
    result: AnalysisInputResolution, *, workspace_id: str, source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> AnalysisInputResolution:
    """Only ever called when `result.status == STATUS_RESOLVED` (one
    candidate per role already). Proves every resolved role's own
    channel shares one aligned timebase with every other, reusing
    `timebases_aligned()` pairwise against a single reference role --
    transitive by construction (see that function's own docstring: same
    `reference_source_id` is instantly `True`; a different one requires
    proven identical absolute sample instants). Same-source roles are
    the overwhelmingly common case and short-circuit immediately via the
    `reference_source_id` equality check inside `timebases_aligned()`
    itself -- no array comparison is performed unless two roles
    genuinely differ in `reference_source_id` (owner's own "do not
    unnecessarily perform expensive alignment work" instruction).
    Downgrades `status` to `needs_configuration` with
    `reason_code="timebase_incompatible"` on any incompatibility --
    never resamples, never interpolates, never silently drops a role."""
    refs = list(result.resolved_roles.values())
    if len(refs) <= 1:
        return result

    identities = []
    for ref in refs:
        identity = _timebase_identity(
            ref, workspace_id=workspace_id, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
        if identity is None:
            # A resolved role's own channel vanished between metadata
            # resolution and this check (only reachable under concurrent
            # mutation) -- conservatively treat as incompatible rather
            # than silently proceeding.
            identities.append(None)
        else:
            identities.append(identity)

    if any(identity is None for identity in identities):
        result.status = STATUS_NEEDS_CONFIGURATION
        result.reason_code = REASON_TIMEBASE_INCOMPATIBLE
        result.message = "Required roles resolved individually but their timebases could not be verified."
        return result

    first_ref_id, first_elapsed, first_epoch = identities[0]
    for ref_id, elapsed, epoch in identities[1:]:
        if not timebases_aligned(first_ref_id, first_elapsed, first_epoch, ref_id, elapsed, epoch):
            result.status = STATUS_NEEDS_CONFIGURATION
            result.reason_code = REASON_TIMEBASE_INCOMPATIBLE
            result.message = (
                "Required roles resolved individually but their timebases are not proven compatible; "
                "resampling/interpolation is never performed automatically."
            )
            return result
    return result


def resolve_analysis_inputs(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis_kind: str,
    mode: str,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> AnalysisInputResolution:
    """The one service-layer entry point. Fetches the requested
    Engineering Context and Analysis Requirement, resolves each member's
    own live metadata, delegates role matching to the pure
    `resolve_requirement()`, then (only for an otherwise-fully-resolved
    result) proves timebase compatibility. Result is always derived
    fresh -- never cached or persisted."""
    context = context_registry.get(workspace_id, engineering_context_id)
    if context is None:
        raise EngineeringContextNotFoundError(f"No Engineering Context '{engineering_context_id}' in this workspace.")

    requirement = get_requirement(analysis_kind, mode)
    if requirement is None:
        raise UnknownAnalysisRequirementError(
            f"No analysis requirement known for analysis_kind={analysis_kind!r}, mode={mode!r}."
        )

    candidates = [
        candidate
        for candidate in (
            _resolve_candidate_metadata(
                member, workspace_id=workspace_id, source_registry=source_registry,
                calculated_channel_registry=calculated_channel_registry,
            )
            for member in context.members
        )
        if candidate is not None
    ]

    result = resolve_requirement(requirement, candidates, engineering_context_id=engineering_context_id)
    if result.status == STATUS_RESOLVED:
        result = _apply_timebase_check(
            result, workspace_id=workspace_id, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
    return result
