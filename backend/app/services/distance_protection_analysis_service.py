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

from collections.abc import Sequence

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
    DistanceAnalysisResult,
    DistanceLocusPoint,
    ManualDistanceResult,
    NamedZone,
    ZoneSettings,
    collect_zones,
    compute_loop_impedance,
    evaluate_manual_distance,
    evaluate_zones,
)
from app.domain.impedance import MIN_CURRENT_A, convert_impedance_basis, impedance_ratio_valid
from app.domain.phasor import PhasorDiagramResult, ROLE_STATUS_AVAILABLE, ManualPhasorRoleInput
from app.domain.side_conversion import (
    REASON_CHANNEL_MISMATCH,
    REASON_UNSUPPORTED_CURRENT_UNIT,
    REASON_UNSUPPORTED_VOLTAGE_UNIT,
    SideBlock,
    SidePlan,
    normalise_to_amperes,
    normalise_to_volts,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.phasor_analysis_service import compute_phasor_diagram, evaluate_prepared_phasor_diagram, prepare_phasor_diagram
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
    zones: Sequence[NamedZone] | None = None,
    zone1: ZoneSettings | None = None,
    zone2: ZoneSettings | None = None,
    zone3: ZoneSettings | None = None,
    zone4: ZoneSettings | None = None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    side_plan: SidePlan | SideBlock | None = None,
) -> DistanceAnalysisResult:
    """Selected-time-only Recording-mode Distance Protection for ONE
    fault loop (`AB`/`BC`/`CA`). `recording_basis` describes the basis
    the RESOLVED Va/Vb/Vc/Ia/Ib/Ic channels' own `magnitude_rms` values
    already represent; `impedance_basis` is the INDEPENDENT desired
    OUTPUT basis (mirrors Impedance Locus's own precedent exactly).
    Ratios are only required, and only validated, when a genuine
    conversion is needed (`recording_basis != impedance_basis`).

    The zones are one generic collection (`zones`, any number, each under its own
    stable key); the standard `zone1`..`zone4` keywords are the same collection
    spelled the manual form's way."""
    evaluated_zones = collect_zones(zones, zone1, zone2, zone3, zone4)
    if isinstance(side_plan, SideBlock):
        keys = LOOP_ROLE_KEYS.get(loop, (None, None, None, None))
        ref = lambda k: side_plan.role_refs.get(k) if k else None       # noqa: E731
        unit = lambda k: side_plan.role_units.get(k) if k else None     # noqa: E731
        return _blocked_distance_result(
            side_plan, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zones=evaluated_zones,
            v1_channel_ref=ref(keys[0]), v2_channel_ref=ref(keys[1]), i1_channel_ref=ref(keys[2]), i2_channel_ref=ref(keys[3]),
            voltage_unit=unit(keys[0]), current_unit=unit(keys[2]),
        )
    diagram = compute_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz_override=reference_frequency_hz_override,
        context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
    )
    return _distance_analysis_from_diagram(
        diagram, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
        recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        characteristic=characteristic, zones=evaluated_zones, side_plan=side_plan,
    )


def _blocked_distance_result(
    block: SideBlock, *, engineering_context_id: str, loop: str, analysis_time: float, recording_basis, impedance_basis,
    vt_primary, vt_secondary, ct_primary, ct_secondary, characteristic: str, zones,
    v1_channel_ref=None, v2_channel_ref=None, i1_channel_ref=None, i2_channel_ref=None,
    voltage_unit=None, current_unit=None,
) -> DistanceAnalysisResult:
    """Independent-side mode refused: needs_configuration with a machine-readable reason; legacy is not a fallback.
    The channels that resolved (never an unresolved one) are still identified, so the physical signals stay plottable."""
    return DistanceAnalysisResult(
        status=DISTANCE_STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, loop=loop,
        analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        v1_channel_ref=v1_channel_ref, v2_channel_ref=v2_channel_ref, i1_channel_ref=i1_channel_ref,
        i2_channel_ref=i2_channel_ref, voltage_unit=voltage_unit, current_unit=current_unit,
        characteristic=characteristic, zones=evaluate_zones(None, characteristic=characteristic, zones=zones),
        reason_code=block.code, message=block.message, side_conversion=block.info,
    )


def _strict_distance_result(
    plan: SidePlan, roles, *, diagram: PhasorDiagramResult, engineering_context_id: str, loop: str, analysis_time: float,
    recording_basis, impedance_basis, vt_primary, vt_secondary, ct_primary, ct_secondary, characteristic: str, zones,
) -> DistanceAnalysisResult:
    """Independent-side conversion: every leg goes directly to `impedance_basis`, then the loop quantities
    (V1 - V2, I1 - I2) and Z = Vloop / Iloop are formed once."""
    v1_role, v2_role, i1_role, i2_role = roles
    echo = dict(
        engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
        recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        characteristic=characteristic, zones=zones,
    )

    def refuse(code: str, message: str, quantity: str | None = None) -> DistanceAnalysisResult:
        block = SideBlock(code=code, message=message, quantity=quantity, voltage_side=plan.voltage_side,
                          current_side=plan.current_side, output_side=plan.output_side)
        return _blocked_distance_result(
            block, **echo, v1_channel_ref=v1_role.channel_ref, v2_channel_ref=v2_role.channel_ref,
            i1_channel_ref=i1_role.channel_ref, i2_channel_ref=i2_role.channel_ref,
            voltage_unit=v1_role.unit, current_unit=i1_role.unit,
        )

    if (not plan.validated or set(plan.voltage_refs) != {v1_role.channel_ref, v2_role.channel_ref}
            or set(plan.current_refs) != {i1_role.channel_ref, i2_role.channel_ref}):
        return refuse(REASON_CHANNEL_MISMATCH, "The validated channels do not match the channels this analysis consumed.")
    volts = [normalise_to_volts(r.magnitude_rms, r.unit) for r in (v1_role, v2_role)]
    if any(v is None for v in volts):
        return refuse(REASON_UNSUPPORTED_VOLTAGE_UNIT, "A voltage unit cannot be normalized to volts.", "voltage")
    amps = [normalise_to_amperes(r.magnitude_rms, r.unit) for r in (i1_role, i2_role)]
    if any(a is None for a in amps):
        return refuse(REASON_UNSUPPORTED_CURRENT_UNIT, "A current unit cannot be normalized to amperes.", "current")

    common = dict(
        reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
        v1_channel_ref=v1_role.channel_ref, v2_channel_ref=v2_role.channel_ref,
        i1_channel_ref=i1_role.channel_ref, i2_channel_ref=i2_role.channel_ref,
        voltage_unit=v1_role.unit, current_unit=i1_role.unit, side_conversion=plan.info,
    )
    point = compute_loop_impedance(
        plan.scale_voltage(volts[0]), v1_role.angle_deg_absolute, plan.scale_voltage(volts[1]), v2_role.angle_deg_absolute,
        plan.scale_current(amps[0]), i1_role.angle_deg_absolute, plan.scale_current(amps[1]), i2_role.angle_deg_absolute,
        min_current=MIN_CURRENT_A * plan.current_scale,
    )
    if point is None:
        return DistanceAnalysisResult(
            status=DISTANCE_STATUS_NEEDS_CONFIGURATION,
            **{**echo, "zones": evaluate_zones(None, characteristic=characteristic, zones=zones)}, **common,
            reason_code=REASON_LOOP_CURRENT_TOO_SMALL, message="Loop current too small for reliable impedance calculation.",
        )
    return DistanceAnalysisResult(
        status=DISTANCE_STATUS_COMPUTED, **{**echo, "zones": evaluate_zones(point, characteristic=characteristic, zones=zones)},
        **common, resistance_ohm=point.resistance_ohm, reactance_ohm=point.reactance_ohm,
        magnitude_ohm=point.magnitude_ohm, angle_deg=point.angle_deg,
        message="Distance protection loop impedance computed.",
    )


def _distance_analysis_from_diagram(
    diagram: PhasorDiagramResult,
    *,
    engineering_context_id: str,
    loop: str,
    analysis_time: float,
    recording_basis: str,
    impedance_basis: str,
    vt_primary: float | None,
    vt_secondary: float | None,
    ct_primary: float | None,
    ct_secondary: float | None,
    characteristic: str,
    zones: Sequence[NamedZone],
    side_plan: SidePlan | None = None,
) -> DistanceAnalysisResult:
    """DEC-114: the `diagram`-consuming remainder of
    `compute_distance_analysis()`'s own work, factored out so a locus
    caller (`compute_distance_locus()`) can supply an already-EVALUATED
    diagram (from a `PreparedPhasorDiagram` prepared once for the whole
    locus, via `app.services.phasor_analysis_service.
    evaluate_prepared_phasor_diagram()`) instead of re-running
    `compute_phasor_diagram()`'s entire role-resolution/candidate-fetch/
    reference-frequency/waveform-form-eligibility pipeline for every
    sample time. `compute_distance_analysis()` itself still calls
    `compute_phasor_diagram()` directly -- its own external behavior for
    a single selected time is unchanged. Mirrors `app.services.
    impedance_analysis_service._impedance_analysis_from_diagram()`'s own
    placement."""

    def _short_circuit(status: str, *, reason_code: str | None, message: str, point=None) -> DistanceAnalysisResult:
        return DistanceAnalysisResult(
            status=status, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            characteristic=characteristic, zones=evaluate_zones(point, characteristic=characteristic, zones=zones),
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

    def _blocked_with_channels(reason_code: str, message: str) -> DistanceAnalysisResult:
        """A configuration block where every leg IS available: same status/reason/message as before, but the resolved
        channels and their units are kept so the signals can still be shown (identity is not a result)."""
        return DistanceAnalysisResult(
            status=DISTANCE_STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, loop=loop,
            analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
            v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
            voltage_unit=v1_role.unit, current_unit=i1_role.unit,
            characteristic=characteristic, zones=evaluate_zones(None, characteristic=characteristic, zones=zones),
            reason_code=reason_code, message=message,
        )

    if any(r.status != ROLE_STATUS_AVAILABLE for r in roles):
        status, reason = _worst_role_status(roles)
        return DistanceAnalysisResult(
            status=status, engineering_context_id=engineering_context_id, loop=loop, analysis_time=analysis_time,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
            characteristic=characteristic, zones=evaluate_zones(None, characteristic=characteristic, zones=zones),
            reason_code=reason, message="One or more required phasors are not available for this fault loop.",
        )

    if side_plan is not None:
        return _strict_distance_result(
            side_plan, roles, diagram=diagram, engineering_context_id=engineering_context_id, loop=loop,
            analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zones=zones,
        )

    needs_ratios = recording_basis != impedance_basis
    if needs_ratios and not (
        vt_primary is not None and vt_secondary is not None and ct_primary is not None and ct_secondary is not None
        and impedance_ratio_valid(vt_primary, vt_secondary) and impedance_ratio_valid(ct_primary, ct_secondary)
    ):
        return _blocked_with_channels(
            REASON_INVALID_RATIO, "Valid VT and CT ratios are required to convert between Recording and Impedance basis.",
        )

    # D5A-UNIT-001: the loop impedance is formed only from consistent SI quantities. Normalise every leg to volts /
    # amperes through the shared unit layer (the 1 mA floor is then judged in amperes) and refuse an unrecognised unit
    # instead of dividing raw magnitudes and labelling the result ohms.
    volts = [normalise_to_volts(r.magnitude_rms, r.unit) for r in (v1_role, v2_role)]
    if any(v is None for v in volts):
        return _blocked_with_channels(
            REASON_UNSUPPORTED_VOLTAGE_UNIT,
            "A voltage unit cannot be normalized to volts; loop impedance in ohms is not available.",
        )
    amps = [normalise_to_amperes(r.magnitude_rms, r.unit) for r in (i1_role, i2_role)]
    if any(a is None for a in amps):
        return _blocked_with_channels(
            REASON_UNSUPPORTED_CURRENT_UNIT,
            "A current unit cannot be normalized to amperes; loop impedance in ohms is not available.",
        )
    point = compute_loop_impedance(
        volts[0], v1_role.angle_deg_absolute, volts[1], v2_role.angle_deg_absolute,
        amps[0], i1_role.angle_deg_absolute, amps[1], i2_role.angle_deg_absolute,
    )
    if point is None:
        return DistanceAnalysisResult(
            status=DISTANCE_STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, loop=loop,
            analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
            v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
            voltage_unit=v1_role.unit, current_unit=i1_role.unit,
            characteristic=characteristic, zones=evaluate_zones(None, characteristic=characteristic, zones=zones),
            reason_code=REASON_LOOP_CURRENT_TOO_SMALL, message="Loop current too small for reliable impedance calculation.",
        )

    point_out = convert_impedance_basis(
        point, from_basis=recording_basis, to_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
    )
    return DistanceAnalysisResult(
        status=DISTANCE_STATUS_COMPUTED, engineering_context_id=engineering_context_id, loop=loop,
        analysis_time=analysis_time, recording_basis=recording_basis, impedance_basis=impedance_basis,
        vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
        reference_frequency_hz=diagram.reference_frequency_hz, window_seconds=diagram.window_seconds,
        v1_channel_ref=v1_ref, v2_channel_ref=v2_ref, i1_channel_ref=i1_ref, i2_channel_ref=i2_ref,
        voltage_unit=v1_role.unit, current_unit=i1_role.unit,
        resistance_ohm=point_out.resistance_ohm, reactance_ohm=point_out.reactance_ohm,
        magnitude_ohm=point_out.magnitude_ohm, angle_deg=point_out.angle_deg,
        characteristic=characteristic, zones=evaluate_zones(point_out, characteristic=characteristic, zones=zones),
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
    zones: Sequence[NamedZone] | None = None,
    zone1: ZoneSettings | None = None,
    zone2: ZoneSettings | None = None,
    zone3: ZoneSettings | None = None,
    zone4: ZoneSettings | None = None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
    side_plan: SidePlan | SideBlock | None = None,
) -> list[DistanceLocusPoint]:
    """The static loop-impedance locus/trajectory -- deterministic,
    independent of Playback speed, mirrors `app.services.
    impedance_analysis_service.compute_impedance_locus()`'s own even-
    sampling algorithm exactly. `point_count` evenly samples
    `[start_time, end_time]` inclusive; a single-point range degenerates
    to one point, never a division by zero. Each sample independently
    evaluates the SAME phasor preparation -- never a second estimator --
    so a point outside the recording's own valid window is reported
    with whatever `status`/`reason_code` that evaluation naturally
    produces, never silently dropped.

    DEC-114: identical rationale to `app.services.
    impedance_analysis_service.compute_impedance_locus()`'s own
    docstring -- role resolution/candidate fetch/reference-frequency
    agreement/waveform-form eligibility/shared-time-coordinate/timebase
    checks are STATIC for the whole locus, so `prepare_phasor_diagram()`
    runs once and each sample time only runs the per-time `evaluate_
    prepared_phasor_diagram()` plus the Distance-specific loop-impedance/
    zone evaluation. Any static/whole-request failure is reported
    identically for every sample point, exactly as before."""
    evaluated_zones = collect_zones(zones, zone1, zone2, zone3, zone4)
    count = max(1, min(int(point_count), MAX_LOCUS_POINTS))
    if count == 1 or end_time <= start_time:
        sample_times = [start_time]
    else:
        step = (end_time - start_time) / (count - 1)
        sample_times = [start_time + i * step for i in range(count)]

    if isinstance(side_plan, SideBlock):
        return [
            DistanceLocusPoint(analysis_time=t, status=DISTANCE_STATUS_NEEDS_CONFIGURATION, reason_code=side_plan.code)
            for t in sample_times
        ]

    prepared = prepare_phasor_diagram(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        reference_frequency_hz_override=reference_frequency_hz_override,
        context_registry=context_registry, source_registry=source_registry, calculated_channel_registry=calculated_channel_registry,
    )

    points: list[DistanceLocusPoint] = []
    for t in sample_times:
        diagram = evaluate_prepared_phasor_diagram(prepared, t)
        result = _distance_analysis_from_diagram(
            diagram, engineering_context_id=engineering_context_id, loop=loop, analysis_time=t,
            recording_basis=recording_basis, impedance_basis=impedance_basis,
            vt_primary=vt_primary, vt_secondary=vt_secondary, ct_primary=ct_primary, ct_secondary=ct_secondary,
            characteristic=characteristic, zones=evaluated_zones, side_plan=side_plan,
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
    zones: Sequence[NamedZone] | None = None,
    zone1: ZoneSettings | None = None,
    zone2: ZoneSettings | None = None,
    zone3: ZoneSettings | None = None,
    zone4: ZoneSettings | None = None,
    v1_input: ManualPhasorRoleInput,
    v2_input: ManualPhasorRoleInput,
    i1_input: ManualPhasorRoleInput,
    i2_input: ManualPhasorRoleInput,
) -> ManualDistanceResult:
    return evaluate_manual_distance(
        v1_input, v2_input, i1_input, i2_input, loop_label=loop_label,
        voltage_basis=voltage_basis, vt_primary=vt_primary, vt_secondary=vt_secondary,
        current_basis=current_basis, ct_primary=ct_primary, ct_secondary=ct_secondary,
        impedance_basis=impedance_basis, characteristic=characteristic,
        zones=collect_zones(zones, zone1, zone2, zone3, zone4),
    )
