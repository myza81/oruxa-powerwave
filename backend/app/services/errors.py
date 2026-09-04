"""Structured service errors.

Originally "import errors" only (Phase 1); Phase 2A extends the same
taxonomy/base class to app.services.waveform_service's errors too, rather
than inventing a parallel hierarchy -- both are ImportServiceError
subclasses so app.api.v1.sources's single `_http_error()` mapping and
`_STATUS_BY_ERROR_CODE` table keep working unchanged for both.

Maps to the error taxonomy in docs/project-memory/MIGRATION_PLAN.md Sec 9,
extended with `upload_too_large` (not anticipated in the original Phase 0
taxonomy; added here to satisfy the size-limit requirement introduced for
this implementation task -- see docs/project-memory/MIGRATION_PLAN.md's
Phase 1 update).

Every error carries a `code` and a user-safe `message`. Internal exception
detail (the original traceback) is logged server-side by the API layer,
never included in the response body -- see
docs/project-memory/POWERWAVE_DISCOVERY.md's finding that powerwave's own
COMTRADE path leaks raw exception text, which this migration explicitly
does not preserve (docs/project-memory/MIGRATION_PLAN.md Sec 15).
"""

from __future__ import annotations


class ImportServiceError(Exception):
    """Base class for all structured import-service errors."""

    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileTypeError(ImportServiceError):
    code = "unsupported_file_type"


class InvalidFileError(ImportServiceError):
    code = "invalid_file"


class ParseError(ImportServiceError):
    code = "parse_error"


class MissingCompanionFileError(ImportServiceError):
    code = "missing_companion_file"


class UnsupportedComtradeVariantError(ImportServiceError):
    code = "unsupported_comtrade_variant"


class UploadTooLargeError(ImportServiceError):
    code = "upload_too_large"


class InvalidWorkspaceError(ImportServiceError):
    code = "invalid_workspace"


class SourceNotFoundError(ImportServiceError):
    code = "source_not_found"


class ChannelNotFoundError(ImportServiceError):
    """Requested channel name does not exist on this source (Phase 2A)."""

    code = "channel_not_found"


class ChannelNotAnalogError(ImportServiceError):
    """Requested channel exists but is digital, not analog (Phase 2A).

    The waveform endpoint only serves analog channels in Phase 2A -- see
    docs/project-memory/MIGRATION_PLAN.md's Phase 2 design, "No digital
    waveform implementation" (deliberately deferred, not an oversight).
    """

    code = "channel_not_analog"


class InvalidTimeRangeError(ImportServiceError):
    """start_time/end_time are malformed (e.g. start_time > end_time)."""

    code = "invalid_time_range"


class ChannelNotDigitalError(ImportServiceError):
    """Requested channel exists but is analog, not digital (Phase 4A).

    Symmetric with ChannelNotAnalogError -- the digital-waveform endpoint
    only serves digital channels, exactly as the analog waveform endpoint
    only serves analog ones.
    """

    code = "channel_not_digital"


# ---- Phase 5A: Calculated Channels (DEC-047) ----


class CalculatedChannelNotFoundError(ImportServiceError):
    """Requested calculated_channel_id does not exist in this workspace."""

    code = "calculated_channel_not_found"


class InvalidOperationArityError(ImportServiceError):
    """Wrong number of inputs for the requested operation (section 7/8)."""

    code = "invalid_operation_arity"


class InvalidConstantError(ImportServiceError):
    """Multiply-by-constant's own `constant` parameter is missing/non-finite (section 28/83)."""

    code = "invalid_constant"


class IncompatibleUnitError(ImportServiceError):
    """Multi-input operation's operands do not share a compatible unit (section 32/33)."""

    code = "incompatible_unit"


class IncompatibleTimeBaseError(ImportServiceError):
    """Multi-input operation's operands are not proven to share one authoritative
    synchronized sample-time axis (section 19-21 of Phase 5A, tightened by the
    owner's explicit time-alignment guardrail) -- never resolved via
    interpolation/resampling/cropping, only accepted or rejected outright."""

    code = "incompatible_time_base"


class DuplicateCalculatedChannelNameError(ImportServiceError):
    """A calculated channel with this display name already exists in the workspace (section 35)."""

    code = "duplicate_calculated_channel_name"


class InvalidCalculatedChannelNameError(ImportServiceError):
    """Calculated-channel name is empty/whitespace-only/too long (section 35)."""

    code = "invalid_calculated_channel_name"


class CalculatedChannelHasDependentsError(ImportServiceError):
    """Attempted to delete a calculated channel that another calculated
    channel still depends on (section 25/63) -- deletion is blocked, never
    a silent cascade, in Phase 5A."""

    code = "calculated_channel_has_dependents"


class CyclicDependencyError(ImportServiceError):
    """A calculated channel's own dependency graph would contain a cycle
    (section 24/85) -- structurally unreachable via the one-shot creation
    API today (calculated channels are immutable and every referenced
    dependency must already exist), but validated defensively anyway."""

    code = "cyclic_dependency"


class InvalidCalculatedOperationError(ImportServiceError):
    """Requested operation is not one of this project's supported
    calculated-channel operations."""

    code = "invalid_calculated_operation"


# ---- Phase 5B: RMS Calculated Channel (DEC-048) ----


class InvalidNominalFrequencyError(ImportServiceError):
    """RMS's own `nominal_frequency_hz` parameter is missing/non-finite/
    outside the sensible plausibility bound (owner section 30/41)."""

    code = "invalid_nominal_frequency"


class RmsRecordingTooShortError(ImportServiceError):
    """The input recording does not span even one full RMS window, so no
    output sample could ever be non-NaN (owner section 40) -- rejected
    outright rather than silently creating an all-NaN channel."""

    code = "rms_recording_too_short"


class RmsSamplingTooSparseError(ImportServiceError):
    """The input's sample spacing is too coarse relative to one RMS window
    to produce a meaningful one-cycle RMS (owner section 41)."""

    code = "rms_sampling_too_sparse"


class RmsOverrideRequiredError(ImportServiceError):
    """RMS eligibility came back non-`suitable` (trusted metadata already
    says RMS/magnitude, or the algorithmic detector is uncertain/negative)
    and the request did not set `override=True` (owner section 14/23/24/
    43): the backend never silently proceeds, and never trusts a client-
    supplied eligibility result -- it re-derives eligibility itself here,
    identically to the dedicated eligibility-check endpoint."""

    code = "rms_override_required"


# ---- Phase 5C: Global Per-Unit Measurement Mode (DEC-049; source-bound
# redesign following owner UAT -- PerUnitProfileNotFoundError/
# ChannelAlreadyAssignedError/InvalidChannelAssignmentError were retired
# with the old profile/channel-assignment workflow: a source-bound
# configuration has no separate identity to "not find" (PUT upserts by
# source_id, DELETE is idempotent) and no assignment conflict is
# possible any more (every eligible channel of a source uses that
# source's own configuration automatically, never explicitly assigned).
# ----


class InvalidPerUnitBaseError(ImportServiceError):
    """A submitted voltage/apparent-power/direct-current base value, or
    voltage-reference mode/override, is missing, non-finite, non-
    positive, or not a recognized value (app.domain.per_unit's own
    validators)."""

    code = "invalid_per_unit_base"


# ---- Slice 1 (DEC-050): Measurement Group domain foundation --
# internal scaffolding for the future measurement-group-aware Per-Unit
# redesign (docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md). Not
# exposed through any public API endpoint yet -- these are raised only
# by app.services.measurement_group_service, consumed directly by
# domain/service tests.
# ----


class MeasurementGroupNotFoundError(ImportServiceError):
    """Requested measurement_group_id does not exist in this workspace."""

    code = "measurement_group_not_found"


class MeasurementGroupAlreadyExistsError(ImportServiceError):
    """`MeasurementGroupRegistry.add()` was called with a
    (workspace_id, measurement_group_id) pair that already exists.
    `add()` is create-only -- an existing group's fields/membership can
    only be changed through `update()`, which already performs
    validation and de-index/re-index correctly. Raised before any
    mutation; the existing stored group and its reverse-index entries
    are left completely untouched (Slice 1 follow-up: the previous
    behaviour silently overwrote the stored group without releasing its
    old channel-index entries first, which would have left stale
    reverse-index entries for any channel present in the old membership
    but not the new one -- normal service-layer creation always
    generates a fresh UUID so this was unreachable through ordinary use,
    but Slice 2's deterministic/suggested grouping must not be allowed
    to rely on that accident)."""

    code = "measurement_group_already_exists"


class InvalidMeasurementGroupKindError(ImportServiceError):
    """A submitted group `kind` is not one of the known Slice 1 kinds
    (`voltage`/`current`)."""

    code = "invalid_measurement_group_kind"


class InvalidMeasurementGroupStatusError(ImportServiceError):
    """A submitted group `status` is not one of the known lifecycle
    states (`suggested`/`confirmed`/`needs_review`/`manual`)."""

    code = "invalid_measurement_group_status"


class UnsupportedChannelReferenceKindError(ImportServiceError):
    """A `ChannelRef` of kind `"calculated"` was submitted as group
    membership -- Slice 1 scope restricts measurement-group membership
    to real source channels only (calculated-channel membership is
    Slice 7 scope, canonical document section 19)."""

    code = "unsupported_channel_reference_kind"


class ChannelWrongSourceError(ImportServiceError):
    """A submitted channel does not belong to the same source as the
    measurement group it is being added to (canonical document's
    same-source invariant)."""

    code = "channel_wrong_source"


class ChannelWrongEngineeringTypeError(ImportServiceError):
    """A submitted channel's engineering type does not match the
    measurement group's own kind (e.g. a Current channel submitted to a
    Voltage group)."""

    code = "channel_wrong_engineering_type"


class ChannelAlreadyGroupedError(ImportServiceError):
    """A submitted channel already belongs to a different measurement
    group in this workspace. Initial Slice 1 policy is to reject this
    outright -- no explicit reassignment mechanism exists yet (unlike
    DEC-049's own now-retired channel-assignment-conflict workflow, this
    is not expected to need one, since group membership is expected to
    be edited through `update_group_membership`, not by fighting over
    ownership from a second group)."""

    code = "channel_already_grouped"


class DuplicateChannelReferenceError(ImportServiceError):
    """The same channel reference was submitted more than once within a
    single measurement group's own membership list."""

    code = "duplicate_channel_reference"


# ---- Slice 3 (DEC-050): Voltage measurement-group base configuration --
# internal scaffolding for the group-aware voltage PU resolver
# (app.domain.voltage_group_config). Not exposed through any public API
# endpoint yet -- raised only by
# app.services.voltage_group_config_service, consumed directly by
# domain/service tests.
# ----


class VoltageConfigurationNotApplicableError(ImportServiceError):
    """A voltage-base configuration operation was attempted against a
    measurement group whose `kind` is not `voltage` (e.g. a Current
    group). Voltage base configuration is only ever meaningful for a
    Voltage group -- rejected explicitly, never silently accepted or
    silently ignored (canonical document section 23's own
    "reject incorrect configuration explicitly" requirement)."""

    code = "voltage_configuration_not_applicable"


class InvalidVoltageBaseValueError(ImportServiceError):
    """A submitted nominal line-to-line voltage base value is missing,
    non-finite, or non-positive (app.domain.voltage_group_config's own
    `voltage_base_valid()`)."""

    code = "invalid_voltage_base_value"


class InvalidVoltageReferenceOverrideError(ImportServiceError):
    """A submitted manual voltage-reference override is not one of the
    known values (`line_to_ground`/`line_to_line`)."""

    code = "invalid_voltage_reference_override"


# ---- Slice 4 (DEC-050): Current measurement-group base configuration --
# internal scaffolding for the group-aware current PU resolver
# (app.domain.current_group_config). Not exposed through any public API
# endpoint yet -- raised only by
# app.services.current_group_config_service, consumed directly by
# domain/service tests.
# ----


class CurrentConfigurationNotApplicableError(ImportServiceError):
    """A current-base configuration operation was attempted against a
    measurement group whose `kind` is not `current` (e.g. a Voltage
    group). Current base configuration is only ever meaningful for a
    Current group -- rejected explicitly, never silently accepted or
    silently ignored (same "reject incorrect configuration explicitly"
    principle as `VoltageConfigurationNotApplicableError`)."""

    code = "current_configuration_not_applicable"


class InvalidEquipmentRatingValueError(ImportServiceError):
    """A submitted equipment rated apparent power (`equipment_rating_mva`)
    is missing, non-finite, or non-positive."""

    code = "invalid_equipment_rating_value"


class InvalidManualCurrentBaseValueError(ImportServiceError):
    """A submitted manual current base (`manual_ibase_ka`) is missing,
    non-finite, or non-positive."""

    code = "invalid_manual_current_base_value"


class InvalidManualVoltageBaseValueError(ImportServiceError):
    """A submitted manual applicable voltage base
    (`manual_voltage_base_kv`) for an equipment-rated Current group is
    missing, non-finite, or non-positive."""

    code = "invalid_manual_voltage_base_value"


class AmbiguousCurrentVoltageSourceError(ImportServiceError):
    """Both `linked_voltage_group_id` and `manual_voltage_base_kv` were
    submitted together for an equipment-rated Current group. The
    applicable voltage base must come from exactly one source -- this
    codebase prefers rejecting ambiguous input over defining a silent
    precedence between the two (task section 8)."""

    code = "ambiguous_current_voltage_source"


class MissingCurrentVoltageSourceError(ImportServiceError):
    """Neither `linked_voltage_group_id` nor `manual_voltage_base_kv` was
    submitted for an equipment-rated Current group -- exactly one
    applicable-voltage-base source is required for this method."""

    code = "missing_current_voltage_source"


class InvalidLinkedVoltageGroupError(ImportServiceError):
    """A submitted `linked_voltage_group_id` exists but fails one of the
    link-validity requirements (task section 4): different source,
    wrong kind (not `voltage`), or no usable nominal LL voltage base
    configured. A `linked_voltage_group_id` that does not exist at all
    raises `MeasurementGroupNotFoundError` instead (same distinction
    `voltage_group_config_service._get_voltage_group()` already makes
    between "not found" and "wrong kind"). Never silently falls back to
    a manual value when raised (task section 4's own explicit
    instruction)."""

    code = "invalid_linked_voltage_group"


# ---- Slice 1 of waveform time synchronization: manual per-source
# alignment offsets (app.domain.synchronization,
# app.services.synchronization_registry/_service). ----


class InvalidAlignmentOffsetError(ImportServiceError):
    """A submitted `alignment_offset_s` is missing/non-finite/non-numeric
    (app.domain.synchronization.alignment_offset_valid)."""

    code = "invalid_alignment_offset"


class ReferenceSourceAlignmentError(ImportServiceError):
    """An attempt was made to set a non-zero alignment offset on the
    workspace's own reference source. The reference source's offset is
    always `0` by construction (task section 9: "the reference offset is
    always 0; other sources are shifted relative to it") -- rejected
    outright rather than silently ignored or silently re-normalizing
    every other source's offset around a new reference."""

    code = "reference_source_alignment_not_allowed"


# ---- Slice 2 of waveform time synchronization: one workspace-wide
# event origin, t0 (app.domain.synchronization, app.services.
# synchronization_registry/_service). ----


class InvalidT0Error(ImportServiceError):
    """A submitted `t0_workspace_time` is missing/non-finite/non-numeric
    (app.domain.synchronization.alignment_offset_valid, reused for t0 --
    see that function's own docstring for why)."""

    code = "invalid_t0"


# ---- Slice 3 of waveform time synchronization: assisted event-origin
# detection (app.domain.event_detection, app.services.
# synchronization_service.detect_event_candidate). ----


class InvalidDetectionSensitivityError(ImportServiceError):
    """A submitted `sensitivity` is not one of the three supported tiers
    (app.domain.event_detection.VALID_SENSITIVITIES) -- task section 8:
    a deliberately small, closed set, never a free-text/raw-parameter
    field."""

    code = "invalid_sensitivity"


# ---- CSV/Excel ingestion Slice 2 (DEC-072): Excel upload/worksheet
# discovery (app.services.preparation_import_service). No new severity
# model here -- these reuse the exact same binary
# ImportServiceError/HTTP-status taxonomy Slice 1's CSV path already
# uses (see app.api.v1.preparation_sources's own module docstring). ----


class AmbiguousPreparationUploadError(ImportServiceError):
    """Neither `csv_file` nor `excel_file` was submitted, or both were --
    exactly one file field is required per request (section: "format-
    aware upload handling" evolved from Slice 1's single `csv_file`
    field without breaking it -- see the API's own docstring)."""

    code = "ambiguous_preparation_upload"


class WorkbookParseError(ImportServiceError):
    """The uploaded bytes could not be opened as a valid Excel workbook
    (corrupt, malformed, or not actually an .xlsx container at all --
    e.g. a renamed non-Excel file). Mirrors
    app.services.errors.ParseError's role for COMTRADE -- reuses the
    existing runtime/import-error model verbatim, never a new severity
    tier (that is Slice 6 scope, not this one)."""

    code = "workbook_parse_error"


class EmptyWorkbookError(ImportServiceError):
    """A workbook opened successfully but contains zero worksheets --
    structurally invalid as a preparation source (mirrors
    app.services.errors.InvalidFileError's "empty file" role for
    CSV/COMTRADE)."""

    code = "empty_workbook"


class WorksheetSelectionNotApplicableError(ImportServiceError):
    """A worksheet-selection request (PATCH) was made against a
    preparation source that has no worksheet concept at all (a CSV
    source) -- rejected explicitly, never silently ignored, matching
    this codebase's established "reject incorrect configuration
    explicitly" convention (see e.g.
    VoltageConfigurationNotApplicableError)."""

    code = "worksheet_selection_not_applicable"


class InvalidWorksheetIndexError(ImportServiceError):
    """A submitted `selected_worksheet_index` is missing, non-integer, or
    outside this workbook's own discovered worksheet range -- never
    silently clamped to a valid index."""

    code = "invalid_worksheet_index"


# ---- CSV/Excel ingestion Slice 3 (DEC-072): paged raw-data preview
# (app.services.preparation_preview_service). `offset`/`limit`
# themselves are validated by FastAPI's own Query(ge=..., le=...)
# constraints at the API layer (matching
# app.api.v1.sources.get_source_waveform's own `point_budget: int =
# Query(..., gt=0)` precedent) -- no separate service-level "invalid
# range" error class was needed, since that precedent already fully
# covers "reject negative offsets / non-positive or excessive limits"
# with a single, simple bound per field. ----


class WorksheetNotSelectedError(ImportServiceError):
    """A row-preview request was made against an Excel preparation
    source that has worksheets but no `selected_worksheet_index` yet
    (a multi-worksheet workbook the user has not chosen a sheet for) --
    the preview endpoint never guesses which sheet to show."""

    code = "worksheet_not_selected"


# ---- CSV/Excel ingestion Slice 4 (DEC-072): Working Dataset / non-
# destructive overlay (app.domain.working_overlay,
# app.services.working_overlay_service). Still no severity model here
# -- ordinary request/runtime errors, exactly like every prior slice
# (task's own explicit "do NOT introduce Slice 6 severity findings
# yet"). ----


class InvalidWorkingCoordinateError(ImportServiceError):
    """A submitted `row_number`/`column_index` is out of range -- either
    structurally invalid (`row_number < 1`, `column_index < 0`) or
    outside this source's own known raw dimensions (checked against
    `PreparationSession.cached_row_count`/`cached_column_count` for CSV,
    or the selected worksheet's own `WorksheetInfo.row_count`/
    `column_count` for Excel -- only enforced when that total is
    actually known; a `None`/unknown total is never treated as "no
    limit," but a *missing best-effort* total for Excel is not
    fabricated into a false bound either). Never silently clamped."""

    code = "invalid_working_coordinate"


class InvalidWorkingCellValueError(ImportServiceError):
    """A submitted cell working value exceeds
    `app.domain.working_overlay`'s own maximum length -- a sanity bound
    against a pathological/accidental paste, not an engineering-content
    validation (task's own "do not infer engineering types" guardrail
    stays fully intact; any string within the length bound is accepted
    verbatim)."""

    code = "invalid_working_cell_value"


# ---- CSV/Excel ingestion Slice 5 (DEC-072): Header/Data Region + Column
# Role Mapping (app.domain.working_overlay, app.services.
# working_overlay_service). A submitted header/data-region row_number
# outside this source's own known dimensions reuses
# InvalidWorkingCoordinateError above (it is the same "row_number out of
# range" check, not a distinct failure mode) -- only the two genuinely
# new failure modes below get their own error class. Still no severity
# model -- ordinary request/runtime errors, per this slice's own
# explicit "do NOT introduce readiness severity yet" guardrail. ----


class InvalidDataRegionError(ImportServiceError):
    """A submitted data-region `start_row`/`end_row` pair is internally
    inconsistent (`start_row > end_row`) -- a semantic error distinct
    from either bound being out of this source's own known dimensions
    (that case raises `InvalidWorkingCoordinateError` instead)."""

    code = "invalid_data_region"


class InvalidColumnRoleError(ImportServiceError):
    """A submitted column `role` is not one of
    `app.domain.working_overlay.KNOWN_COLUMN_ROLES` -- a deliberately
    small, closed set (task section: "use stable internal enum-like
    values"), never a free-text field."""

    code = "invalid_column_role"


class InvalidEngineeringQuantityError(ImportServiceError):
    """A submitted `engineering_quantity` is not one of
    `app.domain.channel_classification.KNOWN_ENGINEERING_QUANTITIES` --
    a deliberately closed set (DEC-077), never a free-text field."""

    code = "invalid_engineering_quantity"


# ---- CSV/Excel ingestion Slice 7 (DEC-072): Time-Axis interpretation
# FRAMEWORK (app.domain.time_axis, app.services.time_axis_service). Still
# no promotion into the Slice 6 severity/PreparationIssue model -- these
# are ordinary request/runtime validation errors, exactly like every
# prior slice's own configuration-input errors above. ----


class InvalidTimeAxisConfigurationError(ImportServiceError):
    """A submitted Time-Axis configuration is structurally or
    referentially invalid: `column_indices` is empty, contains a
    duplicate, or references a column index outside this source's own
    known dimensions; one or more referenced columns does not currently
    carry the Time Axis column role (task section N -- a
    `TimeAxisConfiguration` may only reference columns presently marked
    Time Axis); `family`/`provenance` is not one of the known closed
    sets (`app.domain.time_axis.KNOWN_TIME_FAMILIES`/
    `KNOWN_PROVENANCES`); or a submitted `interval_seconds` is present
    but not finite/positive. One consolidated error class for every one
    of these input-shape failures, matching this file's own established
    "minimal evolution" precedent for a single configuration object
    (`InvalidDataRegionError`) rather than one class per field."""

    code = "invalid_time_axis_configuration"


class UnknownTimeAxisInterpreterError(ImportServiceError):
    """A submitted `interpreter_id` is not registered in
    `app.services.time_axis_service`'s own explicit interpreter
    registry. Kept distinct from `InvalidTimeAxisConfigurationError`
    because it names a specific, separately-documented registry lookup
    failure (task sections F/G: "interpreter id exists" is its own
    schema-validation requirement), not a malformed configuration
    shape."""

    code = "unknown_time_axis_interpreter"


# ---- CSV/Excel ingestion Slice 10 (DEC-072): canonical conversion ----
# Every one of these is a RUNTIME/capability failure, never a
# `PreparationIssue` (task section U's own explicit "do not blur
# readiness issues with runtime exceptions" rule) -- readiness policy
# (blocking/warning/info) stays entirely `app.services.readiness_
# service`'s job; these classes only ever fire from
# `app.services.preparation_conversion_service`, at the moment an
# actual `POST .../convert` request cannot be honored.


class ConversionNotReadyError(ImportServiceError):
    """Readiness was re-checked at conversion time (task's own explicit
    "never trust stale frontend state" rule) and at least one BLOCKING
    issue is present. Distinct from a stale readiness read on the
    frontend -- this is the backend's own authoritative, freshly
    recomputed verdict, always evaluated again immediately before
    conversion, never assumed from an earlier request."""

    code = "conversion_not_ready"


class ConversionRequiresIntervalError(ImportServiceError):
    """The active Time Axis is `sample_index` with no real interval/rate
    (`provenance=index_only`) -- an explicit, owner-approved CONVERSION
    capability constraint (task section 2), distinct from Slice 9's own
    readiness policy: `index_only` is legitimately Preparation-Ready
    (a WARNING, not blocking), but it is NOT canonical-seconds-ready --
    converting it would mean pretending `sample 5 = 5 seconds`, which
    this codebase never does. The user can return to Time Axis
    configuration and supply a real interval/rate, or accept a
    different interpreter, then retry conversion."""

    code = "conversion_requires_interval"


class ConversionUnsupportedInterpreterError(ImportServiceError):
    """The active Time Axis resolved to `manual` (or `unsupported`) --
    an interpreter that never parses real per-row values from the
    source columns at all (see `app.services.time_axis_service`'s own
    `_ManualInterpreter`). Slice 10 must not infer anything new (task's
    own explicit rule) -- there is nothing for conversion to honestly
    consume from a manual family/provenance declaration alone. The user
    must assign a real, sample-based interpreter (Absolute Datetime,
    Elapsed Time, Sample Index, Date + Time, or Repeated Timestamp)
    before conversion can proceed."""

    code = "conversion_unsupported_interpreter"


class ConversionRevisionChangedError(ImportServiceError):
    """The preparation source's own `WorkingOverlay.revision` changed
    between when conversion began (readiness re-check, canonical
    construction) and the moment it was about to register the result
    (task section V's own explicit revision-race protection). Never
    converts "half from one revision and half from another" -- the
    entire attempt is discarded and the preparation state is left
    completely untouched; the user simply retries."""

    code = "conversion_revision_changed"


class ConversionValidationError(ImportServiceError):
    """Canonical `DisturbanceRecord` construction produced a record that
    fails `DisturbanceRecord.validate()`'s own consistency checks --
    an UNEXPECTED contradiction Slice 9's readiness policy should
    already have prevented (task section E's own "readiness should
    already guarantee this, but conversion must still fail defensively"
    instruction). Never silently repaired (no sorting, no coercion) --
    the attempt is discarded and preparation state is left untouched."""

    code = "conversion_validation_failed"


# ---- CSV/Excel ingestion Slice 12 (DEC-072): cleaned data export ----


class ExportRevisionChangedError(ImportServiceError):
    """The preparation source's own `WorkingOverlay.revision` changed
    while a cleaned export was being built (task section W's own
    explicit revision-race protection, mirroring Slice 10's
    `ConversionRevisionChangedError` exactly). Export never persists or
    registers anything, so there is no partial state to leave behind
    either way -- this simply refuses to hand back a ZIP that may mix
    rows/manifest fields from two different working-overlay states. The
    user simply retries."""

    code = "export_revision_changed"


# ---- UAT enhancement (2026-09-04, DEC-074): export the resolved/
# configured Time Axis -- cleaned export now serializes a normalized
# Time column instead of the original source Time Axis cell text, so a
# usable, resolved Time Axis is now a REQUIRED precondition (previously
# export was available regardless of readiness at all). These three
# mirror Slice 10's own `ConversionNotReadyError`/
# `ConversionRequiresIntervalError`/`ConversionUnsupportedInterpreterError`
# almost exactly, for the identical underlying reason: a reusable,
# standardized Time column can only be built from an already-resolved,
# sample-based interpretation, never from an unconfigured/unresolved/
# manual/index-only-without-a-real-interval one.


class ExportNotReadyError(ImportServiceError):
    """Readiness was checked at export time and at least one BLOCKING
    issue is present -- unlike the earlier Slice 12 policy (export
    always available regardless of readiness), a reusable cleaned
    export now REQUIRES a usable Time Axis and at least one Waveform
    Channel, since every current readiness `blocking` issue is already
    exactly a Time-Axis or Waveform-Channel finding (see
    `app.services.readiness_service`'s own module docstring) -- this
    reuses that verdict directly rather than re-deriving a second,
    narrower "export readiness" policy."""

    code = "export_not_ready"


class ExportRequiresIntervalError(ImportServiceError):
    """The active Time Axis is `sample_index` with no real interval/rate
    (`provenance=index_only`) -- legitimately Preparation-Ready (a
    WARNING, not blocking), but not reusable-export-ready: a
    standardized `Time (s)` column can only honestly be built from a
    real interval/rate, never by pretending `sample 5 = 5 seconds`.
    Mirrors `ConversionRequiresIntervalError` exactly, for the same
    reason."""

    code = "export_requires_interval"


class ExportUnsupportedInterpreterError(ImportServiceError):
    """The active Time Axis resolved to `manual` (or `unsupported`) --
    an interpreter that never parses a real per-row value from the
    source's own columns at all, so there is nothing to standardize
    into a resolved Time column. Mirrors
    `ConversionUnsupportedInterpreterError` exactly, for the same
    reason."""

    code = "export_unsupported_interpreter"


class ExportTimeAxisValueError(ImportServiceError):
    """Resolved Time Axis construction produced a row Slice 9's own
    readiness pass should already have prevented from reaching here
    (an unparseable/missing interpreted value, or a mix of timezone-
    aware and naive absolute timestamps) -- an UNEXPECTED defensive
    failure, mirroring `ConversionValidationError` exactly. Never
    silently repaired; the export attempt is discarded."""

    code = "export_time_axis_invalid"
