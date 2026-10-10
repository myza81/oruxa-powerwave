"""Oscillation Analysis -- analysis-representation REST exposure (DEC-173
[APPROVED]). Thin translation only: one stateless, side-effect-free POST
into `app.services.oscillation_representation_service`. Deliberately its own
router; it creates no calculated channel and stores nothing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.oscillation import (
    OscillationCrossSignalOut,
    OscillationCrossSignalRequest,
    CoherenceRequest,
    InterpretationRequest,
    ModeShapeRequest,
    OscillationCoherenceOut,
    OscillationModeShapeOut,
    OscillationDampingOut,
    OscillationInterpretationOut,
    OscillationDampingRequest,
    OscillationRepresentationOut,
    OscillationRepresentationRequest,
    OscillationSpectrogramOut,
    OscillationSpectrogramRequest,
    OscillationSpectrumOut,
    OscillationSpectrumRequest,
)
from app.schemas.source import ErrorOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ImportServiceError
from app.services.oscillation_coherence_service import compute_coherence
from app.services.oscillation_cross_signal_service import compute_cross_signal
from app.services.oscillation_damping_service import compute_damping
from app.services.oscillation_interpretation_service import compute_interpretation
from app.services.oscillation_mode_shape_service import compute_mode_shape
from app.services.oscillation_representation_service import derive_analysis_representation, describe
from app.services.oscillation_spectrogram_service import compute_spectrogram
from app.services.oscillation_spectrum_service import compute_spectrum
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.workspace_registry import WorkspaceRegistry

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/oscillation-analysis", tags=["oscillation-analysis"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_found": status.HTTP_404_NOT_FOUND,
    "channel_not_analog": status.HTTP_400_BAD_REQUEST,
    "calculated_channel_not_found": status.HTTP_404_NOT_FOUND,
    "unsupported_representation": status.HTTP_400_BAD_REQUEST,
    "invalid_analysis_window": status.HTTP_400_BAD_REQUEST,
    "invalid_frequency_range": status.HTTP_400_BAD_REQUEST,
    "representation_unavailable": status.HTTP_409_CONFLICT,
    "representation_mismatch": status.HTTP_409_CONFLICT,
    "insufficient_samples": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "non_finite_samples": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "non_uniform_sampling": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_welch_configuration": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_spectrogram_configuration": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "candidate_mismatch": status.HTTP_409_CONFLICT,
}


def get_workspace_registry(request: Request) -> WorkspaceRegistry:
    return request.app.state.workspace_registry


def get_calculated_channel_registry(request: Request) -> CalculatedChannelRegistry:
    return request.app.state.calculated_channel_registry


def get_synchronization_registry(request: Request) -> SynchronizationRegistry:
    return request.app.state.synchronization_registry


@router.post("/representation", response_model=OscillationRepresentationOut)
def get_analysis_representation(
    workspace_id: str,
    body: OscillationRepresentationRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationRepresentationOut:
    """Describes (and proves derivable) the analysis representation of one
    signal. Computed on demand from the full-resolution record; nothing is
    persisted and no samples are returned."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = derive_analysis_representation(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationRepresentationOut(**describe(result))


@router.post("/spectrum", response_model=OscillationSpectrumOut)
def get_frequency_spectrum(
    workspace_id: str,
    body: OscillationSpectrumRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationSpectrumOut:
    """Welch PSD of one signal over the selected window and frequency range
    (DEC-174 [PROPOSAL]). The signal is resolved from workspace state and the
    PSD computed on demand; only the compact band-limited spectrum and the
    exact parameters used are returned. Nothing is stored."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = compute_spectrum(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            window_start_s=body.window_start_s, window_end_s=body.window_end_s,
            f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationSpectrumOut(**result)


@router.post("/spectrogram", response_model=OscillationSpectrogramOut)
def get_spectrogram(
    workspace_id: str,
    body: OscillationSpectrogramRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationSpectrogramOut:
    """STFT spectrogram of one signal over the selected window and frequency
    range (DEC-176 [APPROVED]). Same request identity and validation as the
    spectrum; a window too short for a useful picture is a 200 `unavailable`
    result. Nothing is stored."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = compute_spectrogram(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            signal_revision=body.signal_revision, window_start_s=body.window_start_s, window_end_s=body.window_end_s,
            f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationSpectrogramOut(**result)


@router.post("/damping", response_model=OscillationDampingOut)
def get_damping(
    workspace_id: str,
    body: OscillationDampingRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationDampingOut:
    """Ringdown damping behaviour of the accepted spectral candidates of one setup
    (DEC-177 [PROPOSAL]). The setup is re-validated and the candidates re-derived
    by the backend; weak evidence is a 200 `insufficient_evidence` per candidate.
    Nothing is stored."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    try:
        result = compute_damping(
            workspace_id=workspace_id, input_ref=body.input.to_domain(), representation=body.representation,
            signal_revision=body.signal_revision, window_start_s=body.window_start_s, window_end_s=body.window_end_s,
            f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            candidate_frequencies_hz=body.candidate_frequencies_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationDampingOut(**result)


@router.post("/cross-signal", response_model=OscillationCrossSignalOut)
def get_cross_signal(
    workspace_id: str,
    body: OscillationCrossSignalRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationCrossSignalOut:
    """Cross-signal evidence for an explicit set of signals (DEC-178 [APPROVED]): every signal is
    re-resolved and re-validated from workspace state, analysed with the accepted spectrum / candidate /
    spectrogram / damping chain and the candidates grouped deterministically. A signal that cannot be
    analysed is reported `excluded`; nothing is stored and nothing is classified."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    entries = [
        {"input_ref": s.input.to_domain(), "representation": s.representation, "signal_revision": s.signal_revision,
         "window_start_s": s.window_start_s, "window_end_s": s.window_end_s, "offset_s": s.offset_s, "label": s.label}
        for s in body.signals
    ]
    try:
        result = compute_cross_signal(
            workspace_id=workspace_id, entries=entries, f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationCrossSignalOut(**result)


@router.post("/interpretation", response_model=OscillationInterpretationOut)
def get_interpretation(
    workspace_id: str,
    body: InterpretationRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
) -> OscillationInterpretationOut:
    """Oscillation interpretation (DEC-179 [APPROVED]): the cross-signal evidence of one signal or an explicit set, plus a deterministic
    behaviour / probable-type interpretation of every component with structured supporting and limiting evidence. Every signal is
    re-resolved and re-validated from workspace state; nothing is stored; no AI, no probability."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    entries = [
        {"input_ref": s.input.to_domain(), "representation": s.representation, "signal_revision": s.signal_revision,
         "window_start_s": s.window_start_s, "window_end_s": s.window_end_s, "offset_s": s.offset_s, "label": s.label}
        for s in body.signals
    ]
    try:
        result = compute_interpretation(
            workspace_id=workspace_id, entries=entries, f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            source_registry=source_registry, calc_registry=calc_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationInterpretationOut(**result)


@router.post("/mode-shape", response_model=OscillationModeShapeOut)
def get_mode_shape(
    workspace_id: str,
    body: ModeShapeRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    sync_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> OscillationModeShapeOut:
    """Mode shape / relative phase of the cross-signal components (DEC-180 [PROPOSAL]): the components are re-derived by the backend from
    workspace state, the alignment comes from the synchronization model (no client offset or phase is accepted) and every comparable
    quantity group is projected onto one common frequency over one common interval. Nothing is stored and nothing is classified."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    entries = [
        {"input_ref": s.input.to_domain(), "representation": s.representation, "signal_revision": s.signal_revision,
         "window_start_s": s.window_start_s, "window_end_s": s.window_end_s, "label": s.label}
        for s in body.signals
    ]
    try:
        result = compute_mode_shape(
            workspace_id=workspace_id, entries=entries, f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            component_frequency_hz=body.component_frequency_hz,
            source_registry=source_registry, calc_registry=calc_registry, sync_registry=sync_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationModeShapeOut(**result)


@router.post("/coherence", response_model=OscillationCoherenceOut)
def get_coherence(
    workspace_id: str,
    body: CoherenceRequest,
    source_registry: WorkspaceRegistry = Depends(get_workspace_registry),
    calc_registry: CalculatedChannelRegistry = Depends(get_calculated_channel_registry),
    sync_registry: SynchronizationRegistry = Depends(get_synchronization_registry),
) -> OscillationCoherenceOut:
    """Magnitude-squared coherence between a reference and the other members of each cross-signal component (DEC-181 [PROPOSAL]): the
    components are re-derived by the backend from workspace state, the alignment comes from the synchronization model (no client offset or
    result is accepted), and an estimate with too few averaged segments is refused rather than returned. Nothing is stored or classified."""
    if not workspace_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_workspace", message="workspace_id must not be blank.").model_dump(),
        )
    entries = [
        {"input_ref": s.input.to_domain(), "representation": s.representation, "signal_revision": s.signal_revision,
         "window_start_s": s.window_start_s, "window_end_s": s.window_end_s, "label": s.label}
        for s in body.signals
    ]
    try:
        result = compute_coherence(
            workspace_id=workspace_id, entries=entries, f_min_hz=body.frequency_min_hz, f_max_hz=body.frequency_max_hz,
            component_frequency_hz=body.component_frequency_hz,
            source_registry=source_registry, calc_registry=calc_registry, sync_registry=sync_registry,
        )
    except ImportServiceError as exc:
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    return OscillationCoherenceOut(**result)
