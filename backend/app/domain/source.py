"""Lightweight, ephemeral source/channel metadata, plus (Phase 2A) the
active workspace's ownership of the authoritative full-resolution record.

`SourceMetadata` is what the Phase 1 channel-browse API needs -- never
waveform sample arrays. `ActiveSource` (Phase 2A, DEC-019) pairs that
lightweight metadata with the authoritative, full-resolution
`DisturbanceRecord` it was built from, so the active workspace can serve
waveform range requests without re-parsing the COMTRADE file. This
supersedes Phase 1's original design note (below, corrected rather than
silently rewritten) that the `DisturbanceRecord` was always discarded
after upload -- see DEC-019 in docs/project-memory/DECISIONS.md for why
that changed and what it does/doesn't affect (DEC-015's "never
persistently retain the uploaded *file*" guarantee is untouched; this is
about retaining an already-parsed in-memory object, not the file).

Zero framework dependencies, per the domain/ layer contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.channel_classification import UNDEFINED, WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord


@dataclass(slots=True)
class AnalogChannelSummary:
    name: str
    index: int
    unit: str
    engineering_type: str
    phase: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    primary_ratio: float | None = None
    secondary_ratio: float | None = None
    # Phase 5B (DEC-048): trailing, fully additive field -- no current
    # provider (COMTRADE is the only one implemented) ever sets this away
    # from UNKNOWN; exists so a future CSV/Excel importer has somewhere
    # trustworthy to record "instantaneous"/"rms"/"magnitude" (see
    # app.domain.channel_classification's own module docstring for the
    # taxonomy). Zero behavior change to any existing code path.
    waveform_form: str = WAVEFORM_FORM_UNKNOWN
    # Engineering Quantity enhancement (DEC-077): trailing, fully additive
    # field, same non-invasive pattern as waveform_form above -- COMTRADE
    # (import_service.py) is never touched to populate this; its channels'
    # own AnalogChannel.parameter_type stays None, so
    # channel_classification.canonical_engineering_quantity(None) always
    # resolves UNDEFINED here, by construction, with zero lines changed in
    # that provider. Only app.services.preparation_conversion_service (the
    # CSV/Excel path) ever passes a non-default value. See
    # app.domain.channel_classification's own "Engineering Quantity"
    # section for the full taxonomy and its broad_engineering_type()
    # backward-compatibility mapping.
    engineering_quantity: str = UNDEFINED


@dataclass(slots=True)
class DigitalChannelSummary:
    name: str
    index: int
    normal_state: int = 0
    # Phase 4A: presentation-group classification (Triggered/Never
    # Triggered/Spare), computed once at import time from the full-record
    # digital sample array (see app.domain.digital_classification and
    # import_service.py's own call site) -- never re-derived per request,
    # never changes when the user zooms/pans a viewport.
    classification: str = "never_triggered"


@dataclass(slots=True)
class SourceMetadata:
    """Everything the Phase 1 API needs to answer channel-list requests.

    Deliberately excludes waveform_data / any sample array -- see the module
    docstring. This is the object the in-memory WorkspaceRegistry stores.
    """

    source_id: str
    workspace_id: str
    provider_type: str
    original_filenames: tuple[str, ...]
    created_at: datetime

    station_name: str
    recorder_name: str
    nominal_frequency: float

    timing_reference: str
    start_time: datetime | None
    trigger_time: datetime | None

    sample_count: int
    duration_seconds: float
    elapsed_start_seconds: float
    elapsed_end_seconds: float
    sampling_rates: tuple[float, ...]
    samples_per_rate: tuple[int, ...]

    analog_channels: list[AnalogChannelSummary] = field(default_factory=list)
    digital_channels: list[DigitalChannelSummary] = field(default_factory=list)
    # Slice 1 (CSV/Excel ingestion, DEC-072): the combined byte size of
    # every originally-uploaded file for this source (cfg+dat for
    # COMTRADE) -- captured once at upload time in import_service.py,
    # since the temporary upload bytes themselves are never retained
    # past the request (DEC-015). Additive, defaulted field (backward-
    # compatible with every existing direct SourceMetadata construction
    # in the test suite) -- every live provider path sets it explicitly;
    # only a pre-existing test helper that never expected this field
    # would ever observe the `0` default.
    file_size_bytes: int = 0

    # Slice 10 (CSV/Excel ingestion, DEC-072): a small, generic, JSON-
    # safe provenance bag -- `None` for every EXISTING provider
    # (COMTRADE never sets this; zero behavior change to any current
    # source). Populated only by `app.services.preparation_conversion_
    # service` for a CSV/Excel source converted into a canonical
    # DisturbanceRecord, so a later question ("where did this waveform
    # come from, and how was its time axis established?") is always
    # answerable without inventing a second, CSV/Excel-specific
    # metadata model -- see that module's own docstring for the exact
    # keys it writes. Mirrors `waveform_form`'s own established
    # "additive, defaulted, no current provider sets it away from the
    # default" precedent above.
    preparation_provenance: dict[str, Any] | None = None

    # Time of Day (CSV/Excel ingestion, additive): mirrors
    # `TimingInformation.time_of_day_reference_seconds` verbatim -- the
    # date-neutral, seconds-since-midnight clock position corresponding
    # to this source's own elapsed=0 origin, set ONLY when
    # `timing_reference == "time_of_day"`. `None` for every other source
    # (every COMTRADE recording, and every other CSV/Excel time family)
    # -- used exclusively by `app.domain.time_grouping.derive_time_groups()`
    # for Time-of-Day-vs-Time-of-Day overlap; never combined with a real
    # calendar date.
    time_of_day_reference_seconds: float | None = None


@dataclass(slots=True)
class ActiveSource:
    """Everything the active workspace owns for one imported source (Phase 2A).

    `metadata` is the same lightweight summary the Phase 1 channel-browse
    API has always served (unchanged shape/behaviour). `record` is the
    authoritative, full-resolution `DisturbanceRecord` produced by the
    provider at upload time -- retained here, by reference (never copied),
    for the life of the source, so a later waveform range request
    (app.services.waveform_service) can slice it directly instead of
    re-parsing the COMTRADE file. `record.waveform_data` must never be
    mutated in place -- see DisturbanceRecord's own docstring and DEC-015.

    This is the single object app.services.workspace_registry.WorkspaceRegistry
    stores per (workspace_id, source_id); dropping this object (on source
    Remove or whole-workspace reset) drops the process's only reference to
    both the metadata and the full-resolution record, which is sufficient
    for the record to become eligible for garbage collection -- no
    separate waveform-memory registry exists or is needed (see DEC-019).
    """

    metadata: SourceMetadata
    record: DisturbanceRecord


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
