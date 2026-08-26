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
