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
