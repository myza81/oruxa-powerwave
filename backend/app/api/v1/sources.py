"""Phase 1/2A COMTRADE source/channel/waveform API.

Domain-oriented, versioned, and deliberately small -- see
docs/project-memory/MIGRATION_PLAN.md Sec 7 (API contract) and Sec 8
(response-size discipline). The source/channel endpoints (upload, list,
get, delete, channels) never return waveform arrays, exactly as Phase 1
established. The Phase 2A addition, GET .../waveform, is the one
deliberate exception -- and even there, the response is always bounded
(full-resolution only when the requested range's raw sample count is
already <= the full-resolution display threshold; a peak-preserving
display representation otherwise) -- see app.services.waveform_service.

Upload interaction note (docs/project-memory/MIGRATION_PLAN.md Sec 16,
this phase's UAT candidate list): this endpoint takes two explicit named
parts (cfg_file, dat_file) -- Option B from that discussion, the simplest
bounded UI to prove the upload path. Whether the frontend instead
auto-pairs a single multi-file selection by filename stem (Option A)
remains open for hands-on UAT and does not require an API change either
way; both are one multipart POST to this same endpoint.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from app.config import Settings
from app.domain.channel_classification import VOLTAGE
from app.domain.source import ActiveSource
from app.schemas.annotation_anchor import AnnotationAnchorOut, AnnotationAnchorRequest
from app.schemas.cursor_values import CursorValuesOut, CursorValuesRequest
from app.schemas.digital_waveform import DigitalWaveformBatchOut, DigitalWaveformOut
from app.schemas.peak_value import PeakValueBatchOut, PeakValueBatchRequest, PeakValueResultOut
from app.schemas.source import ErrorOut, SourceChannelsOut, SourceSummaryOut
from app.schemas.table import SourceTableOut
from app.schemas.waveform import WaveformRangeOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import remove_calculated_channels_for_source
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import ImportServiceError, InvalidTimeRangeError
from app.services.import_service import import_comtrade_source
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_service import remove_measurement_groups_for_source
from app.services.per_unit_registry import PerUnitRegistry
from app.services.per_unit_service import delete_source_per_unit_config
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import remove_source_alignment
from app.services.table_service import TABLE_DEFAULT_LIMIT, TABLE_MAX_LIMIT, fetch_table_rows
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.waveform_service import (
    DEFAULT_POINT_BUDGET,
    FULL_RESOLUTION_DISPLAY_THRESHOLD,
    extract_cursor_values,
    extract_digital_waveform,
    extract_waveform_range,
    resolve_annotation_anchor,
    resolve_peak_value,
)
from app.services.workspace_registry import WorkspaceRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sources", tags=["sources"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "parse_error": status.HTTP_400_BAD_REQUEST,
    "missing_companion_file": status.HTTP_400_BAD_REQUEST,
    "unsupported_comtrade_variant": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "invalid_workspace": status.HTTP_400_BAD_REQUEST,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "channel_not_digital": status.HTTP_400_BAD_REQUEST,
    "invalid_time_range": status.HTTP_400_BAD_REQUEST,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_per_unit_registry(request: Request) -> PerUnitRegistry:
    return request.app.state.per_unit_registry


def get_measurement_group_registry(request: Request) -> MeasurementGroupRegistry:
    return request.app.state.measurement_group_registry


def get_voltage_group_config_registry(request: Request) -> VoltageGroupConfigRegistry:
    return request.app.state.voltage_group_config_registry


def get_current_group_config_registry(request: Request) -> CurrentGroupConfigRegistry:
    return request.app.state.current_group_config_registry


def get_synchronization_registry(request: Request) -> SynchronizationRegistry:
    return request.app.state.synchronization_registry


def _voltage_channel_names_for_active(active: ActiveSource) -> list[str]:
    """This source's own full list of Voltage-classified channel names --
    the input to automatic Voltage Reference detection (only consulted
    for a CURRENT channel under `current_base_mode == "derived"`, see
    app.domain.per_unit.resolve_per_unit's own docstring)."""
    return [ch.name for ch in active.metadata.analog_channels if ch.engineering_type == VOLTAGE]


def _validate_workspace_id(workspace_id: str) -> str:
    # Never used as a filesystem path (Phase 1 never persists anything to
    # disk keyed by workspace_id -- see app.services.import_service), so
    # this is a shape check, not a path-traversal guard.
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    return workspace_id


def _http_error(exc: ImportServiceError) -> HTTPException:
    status_code = _STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail=ErrorOut(code=exc.code, message=exc.message).model_dump())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SourceSummaryOut)
async def upload_comtrade_source(
    workspace_id: str,
    cfg_file: UploadFile = File(..., description="COMTRADE .cfg configuration file"),
    dat_file: UploadFile = File(..., description="COMTRADE .dat data file"),
    settings: Settings = Depends(get_settings_dep),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)

    try:
        source = await import_comtrade_source(
            workspace_id=workspace_id,
            cfg_upload=cfg_file,
            dat_upload=dat_file,
            max_total_bytes=settings.max_event_upload_size_bytes,
            registry=registry,
        )
    except ImportServiceError as exc:
        # exc.message is user-safe by construction (app.services.errors);
        # the original exception, with full detail, is logged here for
        # engineering/debugging -- never returned to the client. See
        # docs/project-memory/MIGRATION_PLAN.md Sec 9 and Sec 31.
        logger.info("COMTRADE import rejected (%s): %s", exc.code, exc.message)
        raise _http_error(exc) from exc
    except Exception:
        logger.exception("Unexpected error importing COMTRADE source for workspace %s", workspace_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="Import failed unexpectedly.").model_dump(),
        )

    return SourceSummaryOut.from_domain(source)


@router.get("", response_model=list[SourceSummaryOut])
def list_sources(
    workspace_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> list[SourceSummaryOut]:
    workspace_id = _validate_workspace_id(workspace_id)
    sources = registry.list_for_workspace(workspace_id)
    return [SourceSummaryOut.from_domain(s.metadata) for s in sources]


def _get_or_404(registry: WorkspaceRegistry, workspace_id: str, source_id: str) -> ActiveSource:
    active = registry.get(workspace_id, source_id)
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorOut(
                code="source_not_found",
                message=f"No source '{source_id}' in workspace '{workspace_id}'.",
            ).model_dump(),
        )
    return active


@router.get("/{source_id}", response_model=SourceSummaryOut)
def get_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceSummaryOut:
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    return SourceSummaryOut.from_domain(active.metadata)


@router.get("/{source_id}/channels", response_model=SourceChannelsOut)
def get_source_channels(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceChannelsOut:
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    return SourceChannelsOut.from_domain(active.metadata)


@router.get("/{source_id}/table", response_model=SourceTableOut)
def get_source_table(
    workspace_id: str,
    source_id: str,
    offset: int = Query(0, ge=0, description="0-based row offset -- the first returned row is this source's own row `offset`."),
    limit: int = Query(
        TABLE_DEFAULT_LIMIT, gt=0, le=TABLE_MAX_LIMIT,
        description=f"Maximum rows to return, bounded server-side at {TABLE_MAX_LIMIT} regardless of what is requested.",
    ),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> SourceTableOut:
    """Canonical Table View (DEC-079): one bounded page of this source's
    OWN exact canonical rows -- never the `/waveform` endpoint's own
    point-budget/min-max-envelope reduction (that exists purely for
    chart display performance, see `extract_waveform_range`'s own
    docstring; this endpoint always returns exact, unreduced samples).
    Format-independent -- reads only `ActiveSource.metadata`/`.record`,
    identical for COMTRADE and converted CSV/Excel sources; there is no
    branch on `provider_type` anywhere in this endpoint or
    `app.services.table_service`. Shows this source's own canonical
    source time (elapsed seconds, or absolute wall-clock when
    `timing_reference == "absolute"`) -- never a workspace
    synchronization/alignment-adjusted time. One recording at a time by
    design: this endpoint never merges rows from more than one source;
    a multi-recording Table View is a frontend-only source SELECTOR
    that calls this endpoint again for a different `source_id`, never a
    combined backend query.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    result = fetch_table_rows(active, offset=offset, limit=limit)
    return SourceTableOut.from_result(result)


@router.get("/{source_id}/waveform", response_model=WaveformRangeOut)
def get_source_waveform(
    workspace_id: str,
    source_id: str,
    channel_name: str = Query(..., description="Analog channel name, as returned by GET .../channels."),
    start_time: float | None = Query(
        None, description="Elapsed seconds on the source's native time axis. Omit for the record start."
    ),
    end_time: float | None = Query(
        None, description="Elapsed seconds on the source's native time axis. Omit for the record end."
    ),
    point_budget: int = Query(
        DEFAULT_POINT_BUDGET,
        gt=0,
        description=(
            "Display-response budget, not an engineering-resolution setting. "
            f"If the requested range has <= {FULL_RESOLUTION_DISPLAY_THRESHOLD} raw samples, "
            "the full-resolution range is returned unchanged; otherwise a peak-preserving "
            "min/max envelope is returned using the requested budget -- see "
            "app.domain.waveform_reduction."
        ),
    ),
    unit_mode: str = Query(
        "engineering",
        description="Phase 5C (DEC-049): \"engineering\" (default) or \"per_unit\".",
    ),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> WaveformRangeOut:
    """Phase 2A waveform range endpoint -- see docs/project-memory/MIGRATION_PLAN.md's
    Phase 2A implementation record for the full API contract and its rationale.

    Analog channels only in Phase 2A (digital waveform delivery is
    deliberately deferred -- see app.services.errors.ChannelNotAnalogError).

    Slice 5 (DEC-050): when `unit_mode="per_unit"`, a channel that
    belongs to a `MeasurementGroup` is converted using that group's own
    Voltage/Current base configuration instead of this source's DEC-049
    profile -- see app.services.group_aware_per_unit's own module
    docstring for the exact precedence rule (DEC-051). An ungrouped
    channel's behaviour is completely unchanged.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    per_unit_profile = per_unit_registry.get(workspace_id, source_id) if unit_mode == "per_unit" else None
    try:
        result = extract_waveform_range(
            active,
            channel_name=channel_name,
            start_time=start_time,
            end_time=end_time,
            point_budget=point_budget,
            unit_mode=unit_mode,
            per_unit_profile=per_unit_profile,
            voltage_channel_names=_voltage_channel_names_for_active(active),
            workspace_id=workspace_id,
            group_registry=measurement_group_registry,
            voltage_config_registry=voltage_group_config_registry,
            current_config_registry=current_group_config_registry,
        )
    except ImportServiceError as exc:
        logger.info(
            "Waveform range request rejected (%s) for workspace %s source %s: %s",
            exc.code,
            workspace_id,
            source_id,
            exc.message,
        )
        raise _http_error(exc) from exc
    return WaveformRangeOut.from_result(result)


@router.get("/{source_id}/digital-waveform", response_model=DigitalWaveformBatchOut)
def get_source_digital_waveform(
    workspace_id: str,
    source_id: str,
    channel_names: list[str] = Query(
        ...,
        description=(
            "One or more digital channel names, as returned by GET .../channels "
            "(repeat the query parameter for a batch: "
            "?channel_names=A&channel_names=B). Batched deliberately -- a "
            "source may carry hundreds of digital channels, and N separate "
            "requests for N channels would be wasteful (see "
            "docs/project-memory/MIGRATION_PLAN.md's Phase 4A record)."
        ),
    ),
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
) -> DigitalWaveformBatchOut:
    """Phase 4A batched digital-waveform endpoint.

    Digital channels only (mirrors GET .../waveform's analog-only
    contract, symmetrically) -- see
    app.services.errors.ChannelNotDigitalError. Always returns the full
    record's transition list per channel; no start_time/end_time/
    point_budget parameters -- see extract_digital_waveform's own
    docstring for why.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    results: list[DigitalWaveformOut] = []
    for channel_name in channel_names:
        try:
            result = extract_digital_waveform(active, channel_name=channel_name)
        except ImportServiceError as exc:
            logger.info(
                "Digital waveform request rejected (%s) for workspace %s source %s "
                "channel %s: %s",
                exc.code,
                workspace_id,
                source_id,
                channel_name,
                exc.message,
            )
            raise _http_error(exc) from exc
        results.append(DigitalWaveformOut.from_result(result))
    return DigitalWaveformBatchOut(channels=results)


@router.post("/{source_id}/cursor-values", response_model=CursorValuesOut)
def get_source_cursor_values(
    workspace_id: str,
    source_id: str,
    body: CursorValuesRequest,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> CursorValuesOut:
    """Batched A/B cursor-measurement endpoint (Phase 4C1 analog, Phase
    4C2 digital).

    One request per source (never per channel -- section 8/9; Phase 4C2
    section 16/17): every channel in `body.analog_channel_names` and
    `body.digital_channel_names` is resolved against the SAME two
    already-computed nearest-sample indices (see
    app.services.waveform_service.extract_cursor_values's own docstring)
    -- a source with both analog and digital channels displayed still
    costs exactly one request, one pair of index lookups, covering both
    kinds together. POST (not GET) because the request body naturally
    carries channel lists alongside two independent optional cursor
    times -- the same shape choice this project already made for
    multipart uploads, just JSON here since there is no file involved.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    per_unit_profile = per_unit_registry.get(workspace_id, source_id) if body.unit_mode == "per_unit" else None
    result = extract_cursor_values(
        active,
        analog_channel_names=body.analog_channel_names,
        digital_channel_names=body.digital_channel_names,
        cursor_a_time=body.cursor_a_time,
        cursor_b_time=body.cursor_b_time,
        unit_mode=body.unit_mode,
        per_unit_profile=per_unit_profile,
        voltage_channel_names=_voltage_channel_names_for_active(active),
        workspace_id=workspace_id,
        group_registry=measurement_group_registry,
        voltage_config_registry=voltage_group_config_registry,
        current_config_registry=current_group_config_registry,
    )
    return CursorValuesOut.from_result(result)


@router.post("/{source_id}/annotation-anchor", response_model=AnnotationAnchorOut)
def resolve_source_annotation_anchor(
    workspace_id: str,
    source_id: str,
    body: AnnotationAnchorRequest,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> AnnotationAnchorOut:
    """Phase 4F Callout annotation anchor resolution (DEC-045).

    Resolves ONE authoritative full-resolution sample anchor for one
    analog channel -- called exactly ONCE, at Callout creation time; the
    frontend never calls this again for the same Callout (no re-
    resolution on drag/zoom/pan/box-move, see
    app.services.waveform_service.resolve_annotation_anchor's own
    docstring). Reuses the exact same analog-channel validation and
    nearest-sample/tie-break logic `.../cursor-values` already uses --
    deliberately not a second nearest-sample implementation. Analog
    channels only this phase (`channel_not_analog` for a digital name,
    matching GET .../waveform's own existing analog-only contract).
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    per_unit_profile = per_unit_registry.get(workspace_id, source_id) if body.unit_mode == "per_unit" else None
    try:
        result = resolve_annotation_anchor(
            active,
            channel_name=body.channel_name,
            approximate_elapsed_seconds=body.approximate_elapsed_seconds,
            unit_mode=body.unit_mode,
            per_unit_profile=per_unit_profile,
            voltage_channel_names=_voltage_channel_names_for_active(active),
            workspace_id=workspace_id,
            group_registry=measurement_group_registry,
            voltage_config_registry=voltage_group_config_registry,
            current_config_registry=current_group_config_registry,
        )
    except ImportServiceError as exc:
        logger.info(
            "Annotation anchor request rejected (%s) for workspace %s source %s: %s",
            exc.code,
            workspace_id,
            source_id,
            exc.message,
        )
        raise _http_error(exc) from exc
    return AnnotationAnchorOut.from_result(result)


@router.post("/{source_id}/peak-values", response_model=PeakValueBatchOut)
def resolve_source_peak_values(
    workspace_id: str,
    source_id: str,
    body: PeakValueBatchRequest,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
) -> PeakValueBatchOut:
    """Phase 4G Maximum/Minimum Peak annotation resolution (DEC-046).

    Batched per source (one request, every requested channel/mode pair for
    ONE shared time interval -- section 33/34): called once at each +Peak/
    -Peak's creation (a single-item batch), and again, for every active
    dynamic peak annotation anchored to this source together, whenever the
    engineer's X viewport genuinely changes (zoom/pan/step-zoom/Reset Time
    View -- never on Y-range, Absolute/Elapsed, or box-drag, section 6/39/
    40/55, enforced entirely on the frontend side that calls this).

    `start_time`/`end_time` are the current visible X viewport -- never the
    whole recording (section 4/75).

    Deliberately one item at a time internally (never a second batch-level
    nearest-extremum algorithm): each requested channel/mode pair is
    resolved via `resolve_peak_value`, reusing the SAME analog-channel
    validation `resolve_annotation_anchor`/`extract_waveform_range` already
    use. An unknown/digital channel name in ONE item degrades that ONE
    result to `available=False` rather than failing the whole batch
    (section 12/67 -- one stale/renamed channel must never blank out every
    other channel's otherwise-valid peak) -- the SAME resilience philosophy
    `extract_cursor_values` already documents for its own per-channel
    lookups, just surfaced as an explicit `available` flag here rather than
    silent omission, since each item's position in the response list must
    stay aligned with the request for the frontend to update the right
    annotation.

    `start_time > end_time` for the whole batch's shared interval IS a
    genuine client error (`invalid_time_range`, 400) -- this is the one
    thing that fails the whole request, since every item in the batch
    shares the identical interval.
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    if body.start_time > body.end_time:
        raise _http_error(
            InvalidTimeRangeError(f"start_time ({body.start_time}) must not be greater than end_time ({body.end_time}).")
        )

    per_unit_profile = per_unit_registry.get(workspace_id, source_id) if body.unit_mode == "per_unit" else None
    voltage_channel_names = _voltage_channel_names_for_active(active)
    results: list[PeakValueResultOut] = []
    for item in body.requests:
        try:
            result = resolve_peak_value(
                active,
                channel_name=item.channel_name,
                mode=item.mode,
                start_time=body.start_time,
                end_time=body.end_time,
                unit_mode=body.unit_mode,
                per_unit_profile=per_unit_profile,
                voltage_channel_names=voltage_channel_names,
                workspace_id=workspace_id,
                group_registry=measurement_group_registry,
                voltage_config_registry=voltage_group_config_registry,
                current_config_registry=current_group_config_registry,
            )
        except ImportServiceError as exc:
            logger.info(
                "Peak value request item rejected (%s) for workspace %s source %s channel %s: %s",
                exc.code,
                workspace_id,
                source_id,
                item.channel_name,
                exc.message,
            )
            results.append(
                PeakValueResultOut(
                    channel_name=item.channel_name,
                    mode=item.mode,
                    available=False,
                    sample_index=None,
                    elapsed_seconds=None,
                    value=None,
                    unit=None,
                )
            )
            continue
        results.append(PeakValueResultOut.from_result(result))

    return PeakValueBatchOut(
        source_id=source_id,
        start_time=body.start_time,
        end_time=body.end_time,
        results=results,
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    workspace_id: str,
    source_id: str,
    registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    per_unit_registry: PerUnitRegistry = Depends(get_per_unit_registry),
    measurement_group_registry: MeasurementGroupRegistry = Depends(get_measurement_group_registry),
    voltage_group_config_registry: VoltageGroupConfigRegistry = Depends(get_voltage_group_config_registry),
    current_group_config_registry: CurrentGroupConfigRegistry = Depends(get_current_group_config_registry),
    synchronization_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> None:
    """Phase 5A (DEC-047, section 64): removing a source also removes
    every calculated channel grounded on it, directly or transitively --
    see remove_calculated_channels_for_source's own docstring for why a
    flat filter on `reference_source_id` is sufficient (no separate graph
    walk needed).

    Phase 5C (DEC-049; source-bound redesign): also releases this
    source's own Per-Unit configuration, if any -- since every eligible
    channel of this source used it automatically (no per-channel
    assignment record to separately clean up any more). If a calculated
    channel was auto-inheriting from it, the recompute cascade reacts
    here too (on top of the one `remove_calculated_channels_for_source`
    below drives for any calculated channel this removal itself
    deletes).

    Slice 1 (DEC-050): also releases every measurement group owned by
    this source -- internal scaffolding, not yet visible through any API
    response, but a group must never survive as orphaned state once its
    owning source is gone.

    Slice 3 (DEC-050): also releases each removed group's own Voltage
    base configuration, the same way.

    Slice 4 (DEC-050): also releases each removed group's own Current
    base configuration, the same way.

    Slice 1 of waveform time synchronization: also releases this
    source's own manual alignment offset, if any (task section 10:
    "removing a source removes its synchronization state").
    """
    workspace_id = _validate_workspace_id(workspace_id)
    active = _get_or_404(registry, workspace_id, source_id)
    registry.remove(workspace_id, source_id)
    remove_calculated_channels_for_source(
        workspace_id=workspace_id, source_id=source_id, calc_registry=calc_registry,
        per_unit_registry=per_unit_registry,
    )
    delete_source_per_unit_config(
        workspace_id=workspace_id, source_id=source_id,
        registry=per_unit_registry, source_registry=registry, calc_registry=calc_registry,
    )
    remove_measurement_groups_for_source(
        workspace_id=workspace_id, source_id=source_id, registry=measurement_group_registry,
        voltage_config_registry=voltage_group_config_registry,
        current_config_registry=current_group_config_registry,
    )
    remove_source_alignment(workspace_id=workspace_id, source_id=source_id, registry=synchronization_registry)
