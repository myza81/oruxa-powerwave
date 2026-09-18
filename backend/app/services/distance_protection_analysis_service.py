"""Distance Protection orchestration layer (see
docs/project-memory/DISTANCE_PROTECTION_ANALYSIS.md).

**Recording mode reuses `app.services.phasor_analysis_service.
compute_phasor_diagram()` verbatim** -- the same bay-centric aggregator
Impedance Locus's own Recording mode and Sequence Components' own
Recording mode already use. Extracts whichever four roles (two Voltage,
two Current) the selected fault loop needs and hands them to
`app.domain.distance_protection.compute_loop_impedance()` -- never a
second FFT/DFT/RMS estimator, never a second `resolve_analysis_inputs()`
call (mirrors Impedance's own established precedent of bypassing the
resolver entirely once `compute_phasor_diagram()` has already resolved
every role).

Never persisted -- every result is derived fresh from current
context/channel state, exactly like Phasor/Overcurrent/Impedance/
Sequence Components.
"""

from __future__ import annotations

from app.domain.distance_protection import (
    DISTANCE_STATUS_AMBIGUOUS,
    DISTANCE_STATUS_COMPUTED,
    DISTANCE_STATUS_MISSING,
    DISTANCE_STATUS_NEEDS_CONFIGURATION,
    DISTANCE_STATUS_NOT_ELIGIBLE,
    LOOP_ROLE_KEYS,
    REASON_LOOP_CURRENT_TOO_SMALL,
    REASON_INVALID_RATIO,
    REASON_UNSUPPORTED_LOOP,
    ZONE_KEY_1,
    ZONE_KEY_2,
    ZONE_KEY_3,
    DistanceAnalysisResult,
    DistanceLocusPoint,
    ManualDistanceResult,
    ZoneResult,
    ZoneSettings,
    compute_loop_impedance,
    evaluate_manual_distance,
    evaluate_zone_state,
)
from app.domain.impedance import convert_impedance_basis, impedance_ratio_valid
from app.domain.phasor import ROLE_STATUS_AVAILABLE, ManualPhasorRoleInput
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.phasor_analysis_service import compute_phasor_diagram
from app.services.workspace_registry import WorkspaceRegistry

#: Worst-role-status precedence -- identical shape to `app.services.
#: impedance_analysis_service._ROLE_STATUS_PRECEDENCE`, generalized here
#: to FOUR roles (a full loop -- two Voltage legs, two Current legs)
#: instead of two.
_ROLE_STATUS_PRECEDENCE = (
    DISTANCE_STATUS_NEEDS_CONFIGURATION, DISTANCE_STATUS_AMBIGUOUS, DISTANCE_STATUS_NOT_ELIGIBLE, DISTANCE_STATUS_MISSING,
)


def _worst_role_status(roles) -> tuple[str, str | None]:
    statuses = {r.status for r in roles}
    for status in _ROLE_STATUS_PRECEDENCE:
        if status in statuses:
            reason = next((r.reason_code for r in roles if r.status == status), None)
            return status, reason
    return DISTANCE_STATUS_MISSING, None


def _zone_result(key: str, settings: ZoneSettings, characteristic: str, point) -> ZoneResult:
    return ZoneResult(zone_key=key, enabled=settings.enabled, state=evaluate_zone_state(point, characteristic=characteristic, zone=settings), delay_s=settings.delay_s)


def _zone_results(characteristic: str, zone1: ZoneSettings, zone2: ZoneSettings, zone3: ZoneSettings, point) -> tuple[ZoneResult, ZoneResult, ZoneResult]:
    return (
        _zone_result(ZONE_KEY_1, zone1, characteristic, point),
        _zone_result(ZONE_KEY_2, zone2, characteristic, point),
        _zone_result(ZONE_KEY_3, zone3, characteristic, point),
    )


def compute_distance_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    loop: str,
    analysis_time: float,
    reference_frequency_hz_override: float | None,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
    characteristic: str,
    zone1: ZoneSettings,
    zone2: ZoneSettings,
    zone3: ZoneSettings,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> DistanceAnalysisResult:
    """Selected-time-only Recording-mode Distance Protection for ONE
    fault loop (`AB`/`BC`/`CA`). `recording_basis` describes the basis
    the RESOLVED Va/Vb/Vc/Ia/Ib/Ic channels' own `magnitude_rms` values
    already represent; `impedance_basis` is the INDEPENDENT desired
    OUTPUT basis (mirrors Impedance Locus's own precedent exactly).
    Ratios are only required, and only validated, when a genuine
    conversion is needed (`recording_basis != impedance_basis`)."""
    diagram = compute_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz_override=reference_frequency_hz_override,
        context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
    )

    def _short_circuit(status: str, *, reason_code: str | None, message: str, point=None) -> DistanceAnalysisResult:
        z1, z2, z3 = _zone_results(characteristic, zone1, zone2, zone3, point)
        return DistanceAnalysisResult(
            status=status, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            characteristic=characteristic, zone1=z1, zone2=z2, zone3=z3,
            reason_code=reason_code, message=message,
        )

    if diagram.status != "computed":
        return _short_circuit(diagram.status, reason_code=diagram.reason_code, message=diagram.message)

    role_keys = LOOP_ROLE_KEYS.get(loop)
    if role_keys is None:
        return _short_circuit(DISTANCE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_UNSUPPORTED_LOOP, message="Unsupported fault loop.")

    v1_key, v2_key, i1_key, i2_key = role_keys
    v1_role, v2_role, i1_role, i2_role = diagram.roles.get(v1_key), diagram.roles.get(v2_key), diagram.roles.get(i1_key), diagram.roles.get(i2_key)
    if v1_role is None or v2_role is None or i1_role is None or i2_role is None:
        return _short_circuit(DISTANCE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_UNSUPPORTED_LOOP, message="Unsupported fault loop.")

    roles = (v1_role, v2_role, i1_role, i2_role)
    v1_ref, v2_ref, i1_ref, i2_ref = v1_role.channel_ref, v2_role.channel_ref, i1_role.channel_ref, i2_role.channel_ref
    if any(r.status != ROLE_STATUS_AVAILABLE for r in roles):
        status, reason = _worst_role_status(roles)
        z1, z2, z3 = _zone_results(characteristic, zone1, zone2, zone3, None)
        return DistanceAnalysisResult(
            status=status, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
            characteristic=characteristic, zone1=z1, zone2=z2, zone3=z3,
            reason_code=reason, message="One or more required phasors are not available for this fault loop.",
        )

    needs_ratios = recording_basis != impedance_basis
    if needs_ratios and not (
        vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
        and impedance_ratio_valid(vt_primary, vt_secondary) and impedance_ratio_valid(ct_primary, ct_secondary)
    ):
        return _short_circuit(
            DISTANCE_STATUS_NEEDS_CONFIGURATION, reason_code=REASON_INVALID_RATIO,
            message="Valid VT and CT ratios are required to convert between Recording and Impedance basis.",
        )

    point = compute_loop_impedance(
        v1_role.magnitude_rms, v1_role.angle_deg_absolute, v2_role.magnitude_rms, v2_role.angle_deg_absolute,
        i1_role.magnitude_rms, i1_role.angle_deg_absolute, i2_role.magnitude_rms, i2_role.angle_deg_absolute,
    )
    if point is None:
        z1, z2, z3 = _zone_results(characteristic, zone1, zone2, zone3, None)
        return DistanceAnalysisResult(
            status=DISTANCE_STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, loop=loop,
            analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
            v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
            voltage_unit=v1_role.unit, current_unit=i1_role.unit,
            characteristic=characteristic, zone1=z1, zone2=z2, zone3=z3,
            reason_code=REASON_LOOP_CURRENT_TOO_SMALL, message="Loop current too small for reliable impedance calculation.",
        )

    point_out = convert_impedance_basis(
        point, from_basis=recording_basis, to_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    z1, z2, z3 = _zone_results(characteristic, zone1, zone2, zone3, point_out)

    return DistanceAnalysisResult(
        status=DISTANCE_STATUS_COMPUTED, engineering_context_id=engineering_context_id, loop=loop,
        analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
        v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
        voltage_unit=v1_role.unit, current_unit=i1_role.unit,
        resistance_ohm=point_out.resistance_ohm, reactance_ohm=point_out.reactance_ohm,
        magnitude_ohm=point_out.magnitude_ohm, angle_deg=point_out.angle_deg,
        characteristic=characteristic, zone1=z1, zone2=z2, zone3=z3,
        message="Distance protection loop impedance computed.",
    )


#: Hard cap on locus sample count -- identical to `app.services.
#: impedance_analysis_service.MAX_LOCUS_POINTS`. A caller-requested
#: `point_count` above this is clamped, never rejected outright.
MAX_LOCUS_POINTS = 300


def compute_distance_locus(
    *,
    workspace_id: str,
    engineering_context_id: str,
    loop: str,
    start_time: float,
    end_time: float,
    point_count: int,
    reference_frequency_hz_override: float | None,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
    characteristic: str,
    zone1: ZoneSettings,
    zone2: ZoneSettings,
    zone3: ZoneSettings,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> list[DistanceLocusPoint]:
    """The static loop-impedance locus/trajectory -- deterministic,
    independent of Playback speed, mirrors `app.services.
    impedance_analysis_service.compute_impedance_locus()`'s own even-
    sampling algorithm exactly. `point_count` evenly samples
    `[start_time, end_time]` inclusive; a single-point range degenerates
    to one point, never a division by zero. Each sample independently
    calls `compute_distance_analysis()` -- never a second estimator --
    so a point outside the recording's own valid window is reported
    with whatever `status`/`reason_code` that call naturally produces,
    never silently dropped."""
    count = max(1, min(int(point_count), MAX_LOCUS_POINTS))
    if count == 1 or end_time <= start_time:
        sample_times = [start_time]
    else:
        step = (end_time - start_time) / (count - 1)
        sample_times = [start_time + i * step for i in range(count)]

    points: list[DistanceLocusPoint] = []
    for t in sample_times:
        result = compute_distance_analysis(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id, loop=loop, analysis_time=t,
            reference_frequency_hz_override=reference_frequency_hz_override,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zone1=zone1, zone2=zone2, zone3=zone3,
            context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
        )
        points.append(DistanceLocusPoint(
            analysis_time=t, status=result.status,
            resistance_ohm=result.resistance_ohm, reactance_ohm=result.reactance_ohm,
            magnitude_ohm=result.magnitude_ohm, angle_deg=result.angle_deg, reason_code=result.reason_code,
        ))
    return points


# ---------------------------------------------------------------------------
# Manual Input / Calculator mode -- Analysis Input Source = "manual" (see
# docs/project-memory/ANALYSIS_INPUT_SOURCE.md). No registry/resolver/
# workspace access at all -- a standalone engineering-calculator path,
# thin orchestration wrapper mirroring `impedance_analysis_service.
# compute_impedance_manual()`'s own placement.
# ---------------------------------------------------------------------------


def compute_distance_manual(
    *,
    loop_label: str,
    voltage_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    current_basis: str,
    ct_primary: float | None,
    ct_secondary: float | None,
    impedance_basis: str,
    characteristic: str,
    zone1: ZoneSettings,
    zone2: ZoneSettings,
    zone3: ZoneSettings,
    v1_input: ManualPhasorRoleInput,
    v2_input: ManualPhasorRoleInput,
    i1_input: ManualPhasorRoleInput,
    i2_input: ManualPhasorRoleInput,
) -> ManualDistanceResult:
    return evaluate_manual_distance(
        v1_input, v2_input, i1_input, i2_input, loop_label=loop_label,
        voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        impedance_basis=impedance_basis, characteristic=characteristic, zone1=zone1, zone2=zone2, zone3=zone3,
    )
