"""Shared post-upload workspace/source preparation (DEC-104).

**New application-wide invariant (owner UAT, 2026-09-23)**: once a
source is successfully registered in a workspace, every shared
metadata/discovery step that ANY top-level function might depend on
should already be ready -- no top-level page (Waveform, Analysis,
Compliance, Table, Calculated Channels) may depend on another page
having been opened first merely to materialize shared metadata.

**Investigation finding this module fixes**: two existing, already-
tested, already-idempotent detection mechanisms --
`app.services.measurement_group_service.generate_suggested_groups_
for_source()` and `app.services.engineering_context_service.generate_
suggested_contexts_for_source()` -- have never had ANY automatic
trigger anywhere in this codebase. Each was only ever reachable through
an explicit, page-owned user action: "Manage Measurement Groups" ->
Suggest, or Analysis's own `wwAnalysisDiscoverUncoveredSources()`
(itself only ever called when the Analysis page opens). Compliance's
own commit `9ee9905` added a THIRD, Compliance-specific lazy bootstrap
to compensate for the same underlying gap -- a real fix for
Compliance's own independence, but not the STRONGER, application-wide
lifecycle the owner has now established: preparation should be
workspace/source-lifecycle-owned, not page-owned.

**This module is the ONE authoritative choke point** -- called from
BOTH source-registration paths that exist in this codebase
(`app.services.import_service.import_comtrade_source()`'s own caller in
`app.api.v1.sources.upload_comtrade_source()`, and `app.services.
preparation_conversion_service.convert_preparation_source()`'s own
caller in `app.api.v1.preparation_sources.post_convert_preparation_
source()`), immediately after `WorkspaceRegistry.add()` succeeds.
**No new detection algorithm was written** -- both calls below are the
EXACT same functions the pre-existing page-owned triggers already call;
only the WHEN moved, from "whenever a page happens to be opened" to
"the moment the source exists."

**Never turns discovery uncertainty, or a discovery failure, into an
upload failure** (task section 4/14): both calls below are wrapped
independently, so one failing never blocks the other, and neither ever
propagates to the caller -- the source registration this module is
called after has ALREADY succeeded and is never rolled back. A
`needs_review` group/context is a completely normal, valid outcome, not
an error; only a genuine exception during detection itself
(unexpected, not the documented uncertain-evidence path) is logged and
reported as `*_error` in the returned result, purely for
observability -- no caller in this codebase currently surfaces these
fields to the end user, since the EXISTING per-item `status` field on
each created `MeasurementGroup`/`EngineeringContext` (queried live by
whichever page needs it, e.g. Compliance's own group-list endpoint) is
already sufficient to answer "is shared preparation complete / did it
need review" (task section 15's own explicit "avoid inventing a second
global readiness state if existing per-component status is enough").

**Idempotent by construction** (task section 5): both underlying
functions already guarantee "a detected cluster is skipped entirely if
even one of its own channels already belongs to any existing group/
context, of any status" -- calling this module twice for the same
source (a page's own fallback bootstrap re-running, a retried request,
a test re-registering the same source) is always safe and never
duplicates.

**Synchronous by design** (task section 10): both underlying detection
functions are pure, framework-free pattern matching over one source's
own channel NAMES -- no I/O, no network call, no heavy computation
(typically well under a millisecond for a realistic channel count).
Running them synchronously, in the same request that already parsed
the file, means the upload response's own moment of success is also
the moment shared metadata is already queryable by any other page --
no polling, no eventual-consistency window, no separate "is preparation
done yet" endpoint needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.engineering_context_service import generate_suggested_contexts_for_source
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_service import generate_suggested_groups_for_source
from app.services.workspace_registry import WorkspaceRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkspaceSourcePreparationResult:
    """Observability only -- no caller currently surfaces these fields
    to the end user (see this module's own docstring for why that is
    intentional, not an oversight)."""

    measurement_groups_created: int = 0
    measurement_groups_error: str | None = None
    engineering_contexts_created: int = 0
    engineering_contexts_error: str | None = None


def prepare_workspace_source(
    *,
    workspace_id: str,
    source_id: str,
    source_registry: WorkspaceRegistry,
    group_registry: MeasurementGroupRegistry,
    context_registry: EngineeringContextRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> WorkspaceSourcePreparationResult:
    """Runs every existing, already-tested, single-source-scoped
    discovery mechanism this newly-registered source is eligible for.
    Never raises -- see this module's own docstring."""
    measurement_groups_created = 0
    measurement_groups_error: str | None = None
    try:
        new_groups = generate_suggested_groups_for_source(
            workspace_id=workspace_id, source_id=source_id,
            registry=group_registry, source_registry=source_registry,
        )
        measurement_groups_created = len(new_groups)
    except Exception:
        measurement_groups_error = "measurement_group_discovery_failed"
        logger.exception(
            "Shared post-upload preparation: Measurement Group discovery failed for workspace %s source %s "
            "-- the upload itself is unaffected; 'Manage Measurement Groups > Suggest' remains available as a "
            "manual retry.",
            workspace_id, source_id,
        )

    engineering_contexts_created = 0
    engineering_contexts_error: str | None = None
    try:
        new_contexts = generate_suggested_contexts_for_source(
            workspace_id=workspace_id, source_id=source_id, registry=context_registry,
            source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
        )
        engineering_contexts_created = len(new_contexts)
    except Exception:
        engineering_contexts_error = "engineering_context_discovery_failed"
        logger.exception(
            "Shared post-upload preparation: Engineering Context discovery failed for workspace %s source %s "
            "-- the upload itself is unaffected.",
            workspace_id, source_id,
        )

    return WorkspaceSourcePreparationResult(
        measurement_groups_created=measurement_groups_created,
        measurement_groups_error=measurement_groups_error,
        engineering_contexts_created=engineering_contexts_created,
        engineering_contexts_error=engineering_contexts_error,
    )
