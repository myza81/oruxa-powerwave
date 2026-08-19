"""COMTRADE import orchestration.

Owns the upload -> validate -> ephemeral-parse -> metadata-extract ->
registry lifecycle described in docs/project-memory/MIGRATION_PLAN.md's
Phase 1 update. Nothing here persists an uploaded file:

  1. Bytes are read from the incoming UploadFile parts (already received
     and, for parts over Starlette's 1MB spool threshold, already written
     once to an OS-managed, unlinked temporary file by Starlette itself --
     see docs/project-memory/HANDOFF.md / this phase's final report for the
     full investigation).
  2. This service writes those bytes a second time into its own
     tempfile.TemporaryDirectory(), because ComtradeProvider.load() and its
     internal _find_dat_file() require a real filesystem path with a
     same-directory, same-stem .dat companion (see
     app/providers/comtrade.py's module docstring). The provider's parsing
     algorithm was intentionally not rewritten to accept in-memory buffers
     -- see docs/project-memory/MIGRATION_PLAN.md Sec 9/15.
  3. The temporary directory is always removed (context manager, runs even
     on exception) before this function returns -- the *file* is never
     retained (DEC-015, unaffected by point 4 below).
  4. Phase 2A update (DEC-019): the parsed `DisturbanceRecord` -- full
     resolution, including its `waveform_data` DataFrame -- is now kept
     alongside the lightweight `SourceMetadata`, paired as an
     `ActiveSource`, in the caller-supplied WorkspaceRegistry. This
     supersedes Phase 1's original design here ("never the
     DisturbanceRecord"); see app.domain.source.ActiveSource's docstring
     for why and app.services.waveform_service for the only consumer of
     the retained record.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.domain.channel_classification import classify_analog_channel
from app.domain.digital_classification import classify_digital_channel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.source import (
    ActiveSource,
    AnalogChannelSummary,
    DigitalChannelSummary,
    SourceMetadata,
    utc_now,
)
from app.providers.base import ProviderLoadError
from app.providers.comtrade import ComtradeProvider
from app.services.errors import (
    InvalidFileError,
    MissingCompanionFileError,
    ParseError,
    UnsupportedComtradeVariantError,
    UnsupportedFileTypeError,
    UploadTooLargeError,
)
from app.services.workspace_registry import WorkspaceRegistry

_CFG_SUFFIXES = {".cfg", ".comtrade"}
_DAT_SUFFIXES = {".dat"}
_READ_CHUNK_BYTES = 1024 * 1024  # 1 MiB


async def _read_bounded(upload: UploadFile, *, max_bytes: int, already_read: int) -> bytes:
    """Read *upload* fully, aborting as soon as the combined total would exceed max_bytes.

    Does not trust upload.size alone (the caller already used it as a fast
    pre-check, but a missing/zero Content-Length can leave it unset) --
    this is the authoritative check, based on bytes actually read.
    """
    chunks: list[bytes] = []
    total = already_read
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(
                f"Combined upload size exceeds the {max_bytes // (1024 * 1024)} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_suffix(filename: str | None, allowed: set[str], role: str) -> str:
    if not filename:
        raise UnsupportedFileTypeError(f"{role} file must have a filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise UnsupportedFileTypeError(
            f"{role} file '{filename}' has an unsupported extension "
            f"(expected one of {sorted(allowed)})."
        )
    return filename


async def import_comtrade_source(
    *,
    workspace_id: str,
    cfg_upload: UploadFile,
    dat_upload: UploadFile,
    max_total_bytes: int,
    registry: WorkspaceRegistry,
) -> SourceMetadata:
    """Validate, stage, and parse one COMTRADE .cfg + .dat pair.

    Raises app.services.errors.ImportServiceError subclasses on any failure.
    Never writes to StorageBackend or any persistent location.
    """
    cfg_filename = _validate_suffix(cfg_upload.filename, _CFG_SUFFIXES, "CFG")
    dat_filename = _validate_suffix(dat_upload.filename, _DAT_SUFFIXES, "DAT")

    # Fast pre-check using Starlette's already-known part sizes (populated
    # once the multipart body has been received) -- cheaper than reading
    # again, but not solely relied upon: _read_bounded below is the
    # authoritative check based on bytes actually read.
    known_size = (cfg_upload.size or 0) + (dat_upload.size or 0)
    if known_size > max_total_bytes:
        raise UploadTooLargeError(
            f"Combined upload size ({known_size} bytes) exceeds the "
            f"{max_total_bytes // (1024 * 1024)} MB limit."
        )

    cfg_bytes = await _read_bounded(cfg_upload, max_bytes=max_total_bytes, already_read=0)
    dat_bytes = await _read_bounded(
        dat_upload, max_bytes=max_total_bytes, already_read=len(cfg_bytes)
    )

    if not cfg_bytes:
        raise InvalidFileError("CFG file is empty.")
    if not dat_bytes:
        raise InvalidFileError("DAT file is empty.")

    source_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory(prefix="oruxa-comtrade-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Fixed, sanitized names -- the caller-supplied filenames are never
        # used to construct a filesystem path (no path-traversal surface).
        # ComtradeProvider._find_dat_file() requires matching stems in the
        # same directory, which "event.cfg" / "event.dat" satisfies.
        cfg_path = tmp_path / "event.cfg"
        dat_path = tmp_path / "event.dat"
        cfg_path.write_bytes(cfg_bytes)
        dat_path.write_bytes(dat_bytes)

        try:
            record = ComtradeProvider().load(cfg_path)
        except ProviderLoadError as exc:
            raise _classify_provider_error(exc) from exc
        # temp dir (and both files) is removed here, on the way out of this
        # `with` block, whether load() succeeded, raised, or something else
        # went wrong -- including if an exception propagates past this point.

    metadata = _build_source_metadata(
        record=record,
        workspace_id=workspace_id,
        source_id=source_id,
        original_filenames=(cfg_filename, dat_filename),
    )
    # record is retained by reference (never copied here) alongside the
    # lightweight metadata -- see ActiveSource's docstring and DEC-019.
    # record.waveform_data is never mutated anywhere in this module or
    # downstream (app.services.waveform_service).
    registry.add(ActiveSource(metadata=metadata, record=record))
    return metadata


def _classify_provider_error(exc: ProviderLoadError) -> Exception:
    """Map a ProviderLoadError's message onto the structured error taxonomy.

    ComtradeProvider itself only raises one exception type with a
    descriptive message (see app/providers/comtrade.py) -- it was not
    modified to raise a richer exception hierarchy, per the "preserve
    behaviour, do not rewrite proven engineering logic" principle
    (docs/project-memory/MIGRATION_PLAN.md Sec 9/15). This function
    classifies by message content purely for API error-code purposes; it
    does not change parsing behaviour.
    """
    text = str(exc)
    if "DAT file not found" in text:
        return MissingCompanionFileError(
            "The DAT file could not be matched to the uploaded CFG file."
        )
    if "BINARY32" in text:
        return UnsupportedComtradeVariantError(
            "BINARY32 (COMTRADE 2013 float32) COMTRADE files are not supported yet."
        )
    return ParseError(f"Could not parse the COMTRADE record: {text}")


def _build_source_metadata(
    *,
    record: DisturbanceRecord,
    workspace_id: str,
    source_id: str,
    original_filenames: tuple[str, str],
) -> SourceMetadata:
    analog = [
        AnalogChannelSummary(
            name=ch.name,
            index=ch.index,
            unit=ch.unit,
            engineering_type=classify_analog_channel(
                parameter_type=ch.parameter_type, unit=ch.unit
            ),
            phase=ch.phase,
            scale=ch.scale,
            offset=ch.offset,
            primary_ratio=ch.primary_ratio,
            secondary_ratio=ch.secondary_ratio,
        )
        for ch in record.analog_channels
    ]
    # Phase 4A: Triggered/Never Triggered/Spare classification, computed
    # once here (at import time) from the full-record digital sample
    # array -- never re-scanned per request/render (see
    # digital_classification.py's own module docstring for the exact
    # precedence rule).
    digital = [
        DigitalChannelSummary(
            name=ch.name,
            index=ch.index,
            normal_state=ch.normal_state,
            classification=classify_digital_channel(
                name=ch.name, values=record.waveform_data[ch.name]
            ),
        )
        for ch in record.digital_channels
    ]

    return SourceMetadata(
        source_id=source_id,
        workspace_id=workspace_id,
        provider_type=record.metadata.provider_type,
        original_filenames=original_filenames,
        created_at=utc_now(),
        station_name=record.metadata.station_name,
        recorder_name=record.metadata.recorder_name,
        nominal_frequency=record.metadata.nominal_frequency,
        timing_reference=record.timing_info.timing_reference,
        start_time=record.timing_info.start_time,
        trigger_time=record.timing_info.trigger_time,
        sample_count=record.sample_count(),
        duration_seconds=record.duration_seconds(),
        elapsed_start_seconds=record.elapsed_start_seconds(),
        elapsed_end_seconds=record.elapsed_end_seconds(),
        sampling_rates=tuple(record.sampling_info.sampling_rates),
        samples_per_rate=tuple(record.sampling_info.samples_per_rate),
        analog_channels=analog,
        digital_channels=digital,
    )
