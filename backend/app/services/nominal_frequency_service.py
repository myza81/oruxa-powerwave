"""NF-1: the one accessor for a recording's effective nominal frequency, and its two writers (set manual, return to Auto).

`effective_nominal_frequency()` is the single place a service or endpoint asks "what is this recording's nominal
frequency?". It reads the immutable imported value and provenance from the source, the engineer's value from
`NominalFrequencyRegistry`, and decides with `app.domain.nominal_frequency.resolve_nominal_frequency`. Nothing here
modifies `SourceMetadata`, the record, a sample or any calculated channel.

NF-1 deliberately changes no engineering consumer: nothing yet calls this accessor, so an override stored here has no
effect on any calculation until the consumers are migrated (NF-3).

NF-3B adds the release gate (owner decision O-1) at THIS layer, so no caller can bypass it: every function takes a required
`manual_override_enabled` keyword, deliberately without a default. While it is False a stored Manual value is never honoured
(the effective frequency is the Auto value), `set_manual_nominal_frequency` refuses with `ManualNominalFrequencyDisabledError`
before it validates or stores anything, and returning to Auto is always allowed. Callers do not decide the policy themselves:
the only importers of this module are `app.services.nominal_frequency_access` (the controlled accessor) and the tests
(`test_nf3b_frequency_call_path_guard.py` enforces it).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.nominal_frequency import (
    EffectiveNominalFrequency,
    resolve_nominal_frequency,
    valid_nominal_frequency,
)
from app.services.errors import InvalidNominalFrequencyError, ManualNominalFrequencyDisabledError, SourceNotFoundError
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry


def _active(workspace_id: str, source_id: str, source_registry: WorkspaceRegistry):
    active = source_registry.get(workspace_id, source_id)
    if active is None:
        raise SourceNotFoundError(f"Source {source_id!r} was not found in workspace {workspace_id!r}.")
    return active


def effective_nominal_frequency(
    workspace_id: str, source_id: str, *, source_registry: WorkspaceRegistry, registry: NominalFrequencyRegistry,
    manual_override_enabled: bool,
) -> EffectiveNominalFrequency:
    """The recording's effective nominal frequency. Raises `SourceNotFoundError` for an unknown recording. While the release
    gate is closed (`manual_override_enabled` False) a stored Manual value is ignored: the result is the Auto resolution."""
    active = _active(workspace_id, source_id, source_registry)
    manual, revision = registry.snapshot(workspace_id, source_id)
    return resolve_nominal_frequency(
        active.metadata.nominal_frequency, active.metadata.preparation_provenance,
        manual.value_hz if manual is not None and manual_override_enabled else None, revision,
    )


def set_manual_nominal_frequency(
    workspace_id: str, source_id: str, value_hz: float, *,
    source_registry: WorkspaceRegistry, registry: NominalFrequencyRegistry, manual_override_enabled: bool,
    now: datetime | None = None,
) -> EffectiveNominalFrequency:
    """Store a manual value for this recording. Refused first (nothing stored, nothing validated) while the release gate is
    closed; then rejected (nothing stored) unless it passes the recording-level validity predicate. A value equal to the
    automatic one is stored: an engineer's confirmation is not an assumption."""
    _active(workspace_id, source_id, source_registry)
    if not manual_override_enabled:
        raise ManualNominalFrequencyDisabledError(
            "A manual nominal frequency cannot be saved: the feature has not been released in this environment."
        )
    if not valid_nominal_frequency(value_hz):
        raise InvalidNominalFrequencyError(
            "The nominal frequency must be a finite number from 1 to 1000 Hz."
        )
    registry.set(workspace_id, source_id, float(value_hz), now or datetime.now(timezone.utc))
    return effective_nominal_frequency(
        workspace_id, source_id, source_registry=source_registry, registry=registry, manual_override_enabled=True)


def reset_nominal_frequency_to_auto(
    workspace_id: str, source_id: str, *, source_registry: WorkspaceRegistry, registry: NominalFrequencyRegistry,
    manual_override_enabled: bool,
) -> EffectiveNominalFrequency:
    """Remove the engineer's value; the effective frequency is the automatic one again. Idempotent, and allowed while the
    release gate is closed (it only ever removes a value)."""
    _active(workspace_id, source_id, source_registry)
    registry.clear(workspace_id, source_id)
    return effective_nominal_frequency(
        workspace_id, source_id, source_registry=source_registry, registry=registry,
        manual_override_enabled=manual_override_enabled)
