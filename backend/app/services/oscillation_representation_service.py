"""Oscillation Analysis -- analysis-representation service (DEC-173
[APPROVED]).

Turns one raw (or calculated) Voltage/Current channel into the
analysis-ready magnitude series Oscillation Analysis will consume, on
demand, from the authoritative full-resolution arrays. It is a read-only
derivation: it NEVER creates a calculated channel, writes to a registry, or
caches the series. The engineering is the existing RMS engine
(`app.domain.calculated_channel.evaluate_rms`, via
`app.domain.oscillation_representation`); the existing metadata-first RMS
eligibility hierarchy (`check_rms_eligibility`) decides whether the input is
an instantaneous waveform at all, so an already-RMS/magnitude channel is
never RMS'd a second time.

`derive_analysis_representation()` returns the arrays (for the future
spectral stage, in-process); the REST layer exposes only `describe()`'s
metadata -- no sample data crosses the wire in this slice.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.calculated_channel import ChannelRef, nominal_frequency_valid
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.oscillation_representation import (
    IMPLEMENTED_REPRESENTATIONS,
    REPORTING_EVERY_SOURCE_SAMPLE,
    REPRESENTATION_RMS_MAGNITUDE,
    WINDOW_ALIGNMENT_TRAILING,
    DerivedMagnitude,
    derive_rms_magnitude,
    representation_unavailable_reason,
    rms_bandwidth_limit_hz,
    rms_half_power_frequency_hz,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE,
    RMS_STATUS_SUITABLE,
    _resolve_input,
    check_rms_eligibility,
)
from app.services.errors import ImportServiceError, SourceNotFoundError
from app.services.workspace_registry import WorkspaceRegistry

STATUS_READY = "ready"
STATUS_UNAVAILABLE = "unavailable"

NOMINAL_FREQUENCY_RECORDING_METADATA = "recording_metadata"
NOMINAL_FREQUENCY_ASSUMED_DEFAULT = "assumed_default"


class UnsupportedRepresentationError(ImportServiceError):
    code = "unsupported_representation"


@dataclass(frozen=True, slots=True)
class AnalysisRepresentation:
    """Metadata of a derived series, plus (service-internal) the series."""

    status: str
    representation: str
    reason_code: str | None = None
    message: str | None = None
    nominal_frequency_hz: float | None = None
    nominal_frequency_origin: str | None = None
    derived: DerivedMagnitude | None = None
    source_sample_count: int = 0
    source_start_s: float | None = None
    source_end_s: float | None = None
    source_sample_rate_hz: float | None = None


def _timing_source_id(ref: ChannelRef, workspace_id: str, calc_registry: CalculatedChannelRegistry) -> str:
    """The recording that grounds the channel -- its own source, or a
    calculated channel's reference source."""
    if ref.kind == "source":
        return ref.source_id
    calc = calc_registry.get(workspace_id, ref.calculated_channel_id)
    return calc.reference_source_id  # _resolve_input already proved it exists


def _nominal_frequency(active) -> tuple[float, str]:
    """From the recording's own metadata (COMTRADE `lf`, BEN upload value,
    CSV/Excel preparation). Never a fixed 50 Hz inside this feature; where
    an upstream stage had to ASSUME the default, that is surfaced."""
    provenance = active.metadata.preparation_provenance or {}
    origin = (
        NOMINAL_FREQUENCY_ASSUMED_DEFAULT if provenance.get("nominal_frequency_assumed")
        else NOMINAL_FREQUENCY_RECORDING_METADATA
    )
    return float(active.metadata.nominal_frequency), origin


def derive_analysis_representation(
    *,
    workspace_id: str,
    input_ref: ChannelRef,
    representation: str,
    source_registry: WorkspaceRegistry,
    calc_registry: CalculatedChannelRegistry,
) -> AnalysisRepresentation:
    """Expected non-derivable outcomes (not V/I, already magnitude, form
    unconfirmed, too short/sparse) are returned as `status="unavailable"`
    with a reason; only missing sources/channels or an unknown
    representation raise."""
    if representation not in IMPLEMENTED_REPRESENTATIONS:
        raise UnsupportedRepresentationError(f"Analysis representation '{representation}' is not implemented.")

    resolved = _resolve_input(
        input_ref, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry
    )
    active = source_registry.get(workspace_id, _timing_source_id(input_ref, workspace_id, calc_registry))
    if active is None:
        raise SourceNotFoundError(f"No source '{resolved.reference_source_id}' in workspace '{workspace_id}'.")

    nominal_hz, origin = _nominal_frequency(active)
    time = np.asarray(resolved.time, dtype=np.float64)
    base = dict(
        representation=representation, nominal_frequency_hz=nominal_hz, nominal_frequency_origin=origin,
        source_sample_count=int(time.shape[0]),
        source_start_s=float(time[0]) if time.shape[0] else None,
        source_end_s=float(time[-1]) if time.shape[0] else None,
        source_sample_rate_hz=(
            float(1.0 / np.median(np.diff(time))) if time.shape[0] >= 2 and np.median(np.diff(time)) > 0 else None
        ),
    )

    def unavailable(code: str, message: str) -> AnalysisRepresentation:
        return AnalysisRepresentation(status=STATUS_UNAVAILABLE, reason_code=code, message=message, **base)

    if resolved.engineering_type not in (VOLTAGE, CURRENT):
        return unavailable("not_voltage_or_current", "Only Voltage and Current signals use an RMS magnitude representation.")
    if not nominal_frequency_valid(nominal_hz):
        return unavailable("invalid_nominal_frequency", "The recording's nominal frequency is missing or outside a sensible range.")

    eligibility = check_rms_eligibility(
        workspace_id=workspace_id, input_ref=input_ref, nominal_frequency_hz=nominal_hz,
        source_registry=source_registry, calc_registry=calc_registry,
    )
    if eligibility.status == RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE:
        return unavailable("already_magnitude", eligibility.reason)
    if eligibility.status != RMS_STATUS_SUITABLE:
        return unavailable("form_unconfirmed", eligibility.reason)

    blocked = representation_unavailable_reason(time, nominal_hz)
    if blocked is not None:
        return unavailable(*blocked)

    derived = derive_rms_magnitude(time, np.asarray(resolved.values, dtype=np.float64), nominal_hz)
    if derived.valid_count == 0:
        return unavailable("no_valid_samples", "No complete, finite RMS window exists in this recording.")
    return AnalysisRepresentation(status=STATUS_READY, derived=derived, **base)


def describe(result: AnalysisRepresentation) -> dict:
    """The wire-safe description: rates, counts, ranges and bandwidth."""
    out: dict = {
        "status": result.status,
        "representation": result.representation,
        "source_form": "instantaneous" if result.status == STATUS_READY else None,
        "reason_code": result.reason_code,
        "message": result.message,
        "nominal_frequency_hz": result.nominal_frequency_hz,
        "nominal_frequency_origin": result.nominal_frequency_origin,
        "source_sample_count": result.source_sample_count,
        "source_sample_rate_hz": result.source_sample_rate_hz,
        "source_start_s": result.source_start_s,
        "source_end_s": result.source_end_s,
    }
    d = result.derived
    if d is None:
        return out
    t = d.time
    first, last = d.first_valid_index, d.last_valid_index
    out.update({
        "reporting": REPORTING_EVERY_SOURCE_SAMPLE,
        "representation_sample_rate_hz": result.source_sample_rate_hz,
        "derived_sample_count": d.valid_count,
        "window_s": d.window_s,
        "window_alignment": WINDOW_ALIGNMENT_TRAILING,
        "group_delay_s": d.group_delay_s,
        "valid_start_s": float(t[first]),
        "valid_end_s": float(t[last]),
        "boundary_loss_start_s": float(t[first] - t[0]),
        "boundary_loss_end_s": float(t[-1] - t[last]),
        "bandwidth_half_power_hz": rms_half_power_frequency_hz(d.nominal_frequency_hz),
        "bandwidth_limit_hz": rms_bandwidth_limit_hz(d.nominal_frequency_hz),
    })
    return out
