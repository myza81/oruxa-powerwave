"""Phasor Analysis orchestration layer -- selected-time only (Phasor
Analysis Slice 1; see docs/project-memory/PHASOR_ANALYSIS.md).

Sits above `app.domain.phasor`'s pure estimator exactly the way
`analysis_input_resolution_service.py` sits above its own pure domain
resolver: this is the only place that touches
`EngineeringContextRegistry`/`WorkspaceRegistry`/
`CalculatedChannelRegistry`, and the only place that decides anything
requiring live workspace state -- role resolution (delegated, never
reimplemented), reference-frequency selection/agreement,
waveform-form eligibility, and the shared absolute-time coordinate
every resolved role's own samples are projected onto before the pure
estimator ever sees them.

**Call order, and why**: `resolve_analysis_inputs()` (Slice 2, entirely
unchanged) runs FIRST. If it does not reach `resolved`, this module
never touches a single sample array -- the resolver's own status/
reason/message/missing-or-ambiguous-role detail is returned verbatim
(owner instruction: "do NOT search channels by name, remap phases, or
borrow channels from another context" -- there is nothing left for this
module to decide when the resolver itself could not). Only once every
required role maps to exactly one channel does this module fetch that
channel's own full sample arrays, engineering metadata, and grounding
source's `nominal_frequency`/`start_time`.

**The shared, source-independent time coordinate** (owner's own
"Critical angle convention" requirement -- absolute phasor angle must
be referenced to a common coordinate, never reset per sliding window):
every resolved role's own sample times are converted to TRUE ABSOLUTE
time (`source_start_epoch + elapsed_seconds`, the exact same quantity
`timebases_aligned()` itself already proves equal across sources when
needed), then all shifted by one shared, per-request constant --
`reference_epoch`, the smallest `start_epoch` among every resolved
role's own grounding source -- purely to keep floating-point precision
high (a raw Unix epoch value, `~1.7e9` seconds, is far too large for
`cos(2*pi*50*epoch)` to retain useful angular precision in a 64-bit
float; subtracting one shared reference restores that precision without
changing which physical instant `angle=0` represents). `reference_epoch`
is a property of the RESOLVED SOURCES for this request, never of
`analysis_time` itself, so it is identical across repeated calls with
an advancing `analysis_time` against the same context/requirement --
this is exactly what keeps a steady sinusoid's own reported angle
numerically stable as `analysis_time` advances (see
`backend/tests/test_phasor_domain.py::TestMovingAnalysisTimeStability`).

**`analysis_time` semantics**: elapsed seconds since the START of
whichever resolved role's source grounds the FIRST required role (the
"anchor" -- `AnalysisInputResolution.required_roles[0]`, e.g. `Va` for
every currently-defined three-phase requirement). For the overwhelming
common single-source case this is simply "elapsed seconds since this
recording's own start," identical in spirit to the existing
`cursor-values` endpoint's own per-source elapsed-time convention. For
a genuinely multi-source context, every OTHER role's own equivalent
elapsed time is derived via absolute-epoch arithmetic before slicing
its window -- never by assuming the same scalar applies unchanged
across sources with different start times.
"""

from __future__ import annotations

import math

from app.domain.analysis_input_resolution import (
    STATUS_AMBIGUOUS,
    STATUS_NEEDS_CONFIGURATION,
    STATUS_NOT_APPLICABLE,
    STATUS_RESOLVED,
)
from app.domain.analysis_requirements import (
    PHASOR_CURRENT_PHASE_A,
    PHASOR_CURRENT_PHASE_B,
    PHASOR_CURRENT_PHASE_C,
    PHASOR_VOLTAGE_PHASE_A,
    PHASOR_VOLTAGE_PHASE_B,
    PHASOR_VOLTAGE_PHASE_C,
)
from app.domain.calculated_channel import ChannelRef, nominal_frequency_valid, timebases_aligned
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_MAGNITUDE,
    WAVEFORM_FORM_RMS,
)
from app.domain.phasor import (
    PHASOR_DIAGRAM_CURRENT_REFERENCE_ROLE,
    PHASOR_DIAGRAM_ROLE_ORDER,
    PHASOR_DIAGRAM_VOLTAGE_REFERENCE_ROLE,
    PHASOR_STATUS_COMPUTED,
    REASON_INVALID_REFERENCE_FREQUENCY,
    REASON_REFERENCE_FREQUENCY_CONFLICT,
    REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
    ROLE_STATUS_AMBIGUOUS,
    ROLE_STATUS_AVAILABLE,
    ROLE_STATUS_MISSING,
    ROLE_STATUS_NEEDS_CONFIGURATION,
    ROLE_STATUS_NOT_ELIGIBLE,
    PhasorAnalysisResult,
    PhasorDiagramResult,
    PhasorDiagramRoleResult,
    PhasorEstimate,
    PhasorRoleResult,
    estimate_phasor,
    relative_angle_deg,
)
from app.domain.rms_detector import LIKELY_INSTANTANEOUS, LIKELY_MAGNITUDE_OR_RMS, classify_waveform_form
from app.domain.time_grouping import normalize_absolute_datetime
from app.services.analysis_input_resolution_service import resolve_analysis_inputs
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.engineering_context_registry import EngineeringContextRegistry
from app.services.workspace_registry import WorkspaceRegistry


def _source_start_epoch(active) -> float | None:
    """Mirrors `analysis_input_resolution_service._source_start_epoch()`
    (itself mirroring `calculated_channel_service`'s own) exactly --
    deliberately a separate, locally-owned copy per this codebase's own
    established convention (see `app.domain.engineering_context_
    detection`'s own docstring for the same reasoning)."""
    if active.metadata.start_time is None:
        return None
    return normalize_absolute_datetime(active.metadata.start_time).timestamp()


class _RoleCandidate:
    __slots__ = (
        "role_key", "channel_ref", "time", "values", "unit", "waveform_form", "start_epoch", "nominal_frequency",
        "reference_source_id",
    )

    def __init__(self, *, role_key, channel_ref, time, values, unit, waveform_form, start_epoch, nominal_frequency, reference_source_id):
        self.role_key = role_key
        self.channel_ref = channel_ref
        self.time = time
        self.values = values
        self.unit = unit
        self.waveform_form = waveform_form
        self.start_epoch = start_epoch
        self.nominal_frequency = nominal_frequency
        #: The grounding real source id `timebases_aligned()` itself
        #: needs for its own same-source short-circuit (never the
        #: display/channel_ref id -- for a calculated channel this is its
        #: own `reference_source_id`, never the calculated channel's own
        #: id). Only used by `compute_phasor_diagram()`'s own cross-role
        #: timebase check below -- `compute_phasor_analysis()` (the
        #: original single-requirement endpoint) never needed this
        #: itself, since a multi-role requirement's own timebase proof
        #: already happened inside `resolve_analysis_inputs()`.
        self.reference_source_id = reference_source_id


def _fetch_role_candidate(
    role_key: str, channel_ref: ChannelRef, *, workspace_id: str,
    source_registry: WorkspaceRegistry, calculated_channel_registry: CalculatedChannelRegistry,
) -> _RoleCandidate | None:
    """Fetches ONE resolved role's own full-resolution sample arrays and
    engineering metadata. Mirrors `calculated_channel_service._resolve_
    input()`'s own source/calculated-channel branching exactly (a
    locally-owned copy, not an import of that module's own private
    helper -- same established convention as elsewhere in this slice).
    Returns `None` only if the channel has vanished since the resolver
    itself just confirmed it exists (an unreachable race in practice,
    handled defensively rather than assumed impossible)."""
    if channel_ref.kind == "source":
        active = source_registry.get(workspace_id, channel_ref.source_id)
        if active is None:
            return None
        matching = next((ch for ch in active.metadata.analog_channels if ch.name == channel_ref.channel_name), None)
        if matching is None:
            return None
        waveform_data = active.record.waveform_data
        return _RoleCandidate(
            role_key=role_key, channel_ref=channel_ref,
            time=waveform_data["time"].to_numpy(), values=waveform_data[channel_ref.channel_name].to_numpy(),
            unit=matching.unit, waveform_form=matching.waveform_form,
            start_epoch=_source_start_epoch(active), nominal_frequency=active.metadata.nominal_frequency,
            reference_source_id=channel_ref.source_id,
        )
    calculated = calculated_channel_registry.get(workspace_id, channel_ref.calculated_channel_id)
    if calculated is None:
        return None
    reference_source = source_registry.get(workspace_id, calculated.reference_source_id)
    if reference_source is None:
        return None
    return _RoleCandidate(
        role_key=role_key, channel_ref=channel_ref,
        time=calculated.time, values=calculated.values,
        unit=calculated.unit, waveform_form=calculated.waveform_form,
        start_epoch=_source_start_epoch(reference_source), nominal_frequency=reference_source.metadata.nominal_frequency,
        reference_source_id=calculated.reference_source_id,
    )


def _waveform_form_eligible(candidate: _RoleCandidate, reference_frequency_hz: float) -> bool:
    """Trusted-metadata-first, algorithmic-fallback-second -- mirrors
    `calculated_channel_service.check_rms_eligibility()`'s own structure
    applied to a stricter Phasor policy: explicit `instantaneous` always
    passes; explicit `rms`/`magnitude` always fails, with NO override
    (unlike RMS creation, there is no legitimate reason to phasor-
    estimate a signal already proven non-oscillatory). For `unknown`
    metadata (the common case -- no current provider sets this field
    away from `unknown` for either raw or calculated channels), falls
    back to the same algorithmic detector RMS eligibility already uses
    (`app.domain.rms_detector.classify_waveform_form`, run once against
    the candidate's own FULL sample arrays, exactly like `check_rms_
    eligibility()` does -- never restricted to one phasor window, since
    waveform form is a property of the channel, not of one instant).

    **Deliberately stricter than RMS's own precedent for the
    `UNCERTAIN` detector outcome**: `check_rms_eligibility()` treats
    `UNCERTAIN` the same as `LIKELY_MAGNITUDE_OR_RMS` -- both block
    creation pending an explicit engineer override
    (`override_required=True`). Phasor Slice 1 has no override
    mechanism at all (no legitimate reason exists to force through an
    unconfirmed signal for a phasor estimate the way an engineer might
    knowingly want RMS-of-RMS for smoothing), so `UNCERTAIN` is
    REJECTED here too, consistently with what the real RMS precedent
    already does when no override is supplied -- not treated as
    "allow with a warning," which would not actually match the
    project's own established precedent despite superficially matching
    the audit's own earlier, since-reconsidered suggestion.
    """
    if candidate.waveform_form == WAVEFORM_FORM_INSTANTANEOUS:
        return True
    if candidate.waveform_form in (WAVEFORM_FORM_RMS, WAVEFORM_FORM_MAGNITUDE):
        return False
    detector_result = classify_waveform_form(candidate.time, candidate.values, reference_frequency_hz)
    if detector_result == LIKELY_INSTANTANEOUS:
        return True
    if detector_result == LIKELY_MAGNITUDE_OR_RMS:
        return False
    return False  # UNCERTAIN -- rejected, see docstring above.


def _short_circuit(status: str, *, analysis_kind: str, mode: str, engineering_context_id: str, analysis_time: float,
                    reason_code: str | None, message: str, role_reasons: dict[str, str] | None = None) -> PhasorAnalysisResult:
    return PhasorAnalysisResult(
        status=status, analysis_kind=analysis_kind, mode=mode, engineering_context_id=engineering_context_id,
        analysis_time=analysis_time, reason_code=reason_code, message=message, role_reasons=role_reasons or {},
    )


def compute_phasor_analysis(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis_kind: str,
    mode: str,
    analysis_time: float,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> PhasorAnalysisResult:
    """The one service-layer entry point. Selected-time only -- computes
    a phasor at exactly one `analysis_time`, never a time series, never
    persisted. Raises `EngineeringContextNotFoundError`/
    `UnknownAnalysisRequirementError` exactly like `resolve_analysis_
    inputs()` itself does (propagated unchanged -- see that function's
    own docstring); every OTHER failure mode is returned as a
    `PhasorAnalysisResult` with an explicit `status`/`reason_code`,
    never an exception.
    """
    resolution = resolve_analysis_inputs(
        workspace_id=workspace_id, engineering_context_id=engineering_context_id,
        analysis_kind=analysis_kind, mode=mode,
        context_registry=context_registry, source_registry=source_registry,
        calculated_channel_registry=calculated_channel_registry,
    )
    if resolution.status != STATUS_RESOLVED:
        # Verbatim pass-through -- STATUS_NEEDS_CONFIGURATION/STATUS_AMBIGUOUS/
        # STATUS_NOT_APPLICABLE all reuse the resolver's own vocabulary
        # unchanged (owner instruction: return the resolver's own
        # actionable status/reason, never re-word it).
        assert resolution.status in (STATUS_NEEDS_CONFIGURATION, STATUS_AMBIGUOUS, STATUS_NOT_APPLICABLE)
        role_reasons = dict(resolution.missing_role_reasons)
        for role_key in resolution.ambiguous_roles:
            role_reasons.setdefault(role_key, "ambiguous_candidates")
        return _short_circuit(
            resolution.status, analysis_kind=analysis_kind, mode=mode, engineering_context_id=engineering_context_id,
            analysis_time=analysis_time, reason_code=resolution.reason_code, message=resolution.message,
            role_reasons=role_reasons,
        )

    candidates: dict[str, _RoleCandidate] = {}
    for role_key, ref in resolution.resolved_roles.items():
        candidate = _fetch_role_candidate(
            role_key, ref, workspace_id=workspace_id, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
        if candidate is None:
            return _short_circuit(
                STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
                engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                reason_code="channel_unavailable", message=f"Resolved channel for role '{role_key}' could not be read.",
                role_reasons={role_key: "channel_unavailable"},
            )
        candidates[role_key] = candidate

    # ---- Reference frequency: explicit override, else unanimous agreement ----
    if reference_frequency_hz_override is not None:
        if not nominal_frequency_valid(reference_frequency_hz_override):
            return _short_circuit(
                STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
                engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                reason_code=REASON_INVALID_REFERENCE_FREQUENCY,
                message="The supplied reference_frequency_hz is outside the plausible range.",
            )
        reference_frequency_hz = reference_frequency_hz_override
    else:
        declared = [c.nominal_frequency for c in candidates.values()]
        first = declared[0]
        if not all(math.isclose(f, first, rel_tol=1e-9, abs_tol=1e-9) for f in declared):
            return _short_circuit(
                STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
                engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                reason_code=REASON_REFERENCE_FREQUENCY_CONFLICT,
                message=(
                    "Resolved roles come from sources declaring different nominal frequencies; supply an explicit "
                    "reference_frequency_hz to proceed."
                ),
            )
        reference_frequency_hz = first

    # ---- Waveform-form eligibility, per role ----
    role_reasons: dict[str, str] = {}
    for role_key, candidate in candidates.items():
        if not _waveform_form_eligible(candidate, reference_frequency_hz):
            role_reasons[role_key] = REASON_WAVEFORM_FORM_NOT_ELIGIBLE
    if role_reasons:
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
            engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reason_code=REASON_WAVEFORM_FORM_NOT_ELIGIBLE,
            message="One or more resolved roles are not eligible sinusoidal waveform inputs for phasor estimation.",
            role_reasons=role_reasons,
        )

    # ---- Shared, source-independent absolute-time coordinate ----
    start_epochs = [c.start_epoch for c in candidates.values()]
    if any(epoch is None for epoch in start_epochs):
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
            engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reason_code="absolute_time_unavailable",
            message="One or more resolved sources have no known absolute start time.",
        )
    reference_epoch = min(start_epochs)

    anchor_role_key = resolution.required_roles[0]
    anchor_candidate = candidates[anchor_role_key]
    analysis_time_shared = (anchor_candidate.start_epoch - reference_epoch) + analysis_time

    window_seconds = 1.0 / reference_frequency_hz
    estimates: dict[str, PhasorEstimate] = {}
    for role_key, candidate in candidates.items():
        t_shared = (candidate.start_epoch - reference_epoch) + candidate.time
        estimates[role_key] = estimate_phasor(t_shared, candidate.values, analysis_time_shared, reference_frequency_hz)

    unavailable_reasons = {role_key: est.reason_code for role_key, est in estimates.items() if not est.available}
    if unavailable_reasons:
        distinct = set(unavailable_reasons.values())
        reason_code = next(iter(distinct)) if len(distinct) == 1 else "multiple_issues"
        return _short_circuit(
            STATUS_NEEDS_CONFIGURATION, analysis_kind=analysis_kind, mode=mode,
            engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reason_code=reason_code,
            message="One or more required roles could not be estimated at the requested analysis_time.",
            role_reasons=unavailable_reasons,
        )

    reference_angle = estimates[anchor_role_key].angle_deg
    is_multi_role = len(resolution.required_roles) > 1
    roles_out: dict[str, PhasorRoleResult] = {}
    for role_key, candidate in candidates.items():
        est = estimates[role_key]
        roles_out[role_key] = PhasorRoleResult(
            channel_ref=candidate.channel_ref, magnitude_rms=est.magnitude_rms, unit=candidate.unit,
            angle_deg_absolute=est.angle_deg,
            angle_deg_relative=relative_angle_deg(est.angle_deg, reference_angle) if is_multi_role else None,
        )

    return PhasorAnalysisResult(
        status=PHASOR_STATUS_COMPUTED, analysis_kind=analysis_kind, mode=mode,
        engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz=reference_frequency_hz, window_seconds=window_seconds,
        roles=roles_out, message="All required roles resolved and estimated.",
    )


# ---------------------------------------------------------------------------
# Phasor Diagram aggregation -- bay-centric UAT redesign.
# ---------------------------------------------------------------------------

#: One single-phase requirement per supported role, in the fixed
#: `PHASOR_DIAGRAM_ROLE_ORDER` -- reused UNCHANGED from Slice 2's own
#: `analysis_requirements.py`; this module never defines its own role-
#: matching rules, it only calls `resolve_analysis_inputs()` once per
#: requirement below, exactly the way any other caller would.
_DIAGRAM_REQUIREMENTS_BY_ROLE = {
    "Va": PHASOR_VOLTAGE_PHASE_A, "Vb": PHASOR_VOLTAGE_PHASE_B, "Vc": PHASOR_VOLTAGE_PHASE_C,
    "Ia": PHASOR_CURRENT_PHASE_A, "Ib": PHASOR_CURRENT_PHASE_B, "Ic": PHASOR_CURRENT_PHASE_C,
}

#: reason_code used for every role still only IDENTITY-known (a
#: `_RoleCandidate` exists) at the moment a whole-result BLOCKING
#: condition is detected -- see `_blocked_diagram_result()`'s own
#: docstring for why these roles get `needs_configuration` rather than
#: being left without any status at all.
_REASON_CHANNEL_UNAVAILABLE = "channel_unavailable"


def _diagram_role_status_for_resolution(role_key: str, resolution) -> tuple[str, str | None]:
    """Maps ONE single-role `AnalysisInputResolution` (never `resolved`
    here -- the caller only reaches this branch when it wasn't) to this
    module's own 5-value role-status vocabulary. A single-role
    requirement can only ever produce `ambiguous` or `needs_configuration`
    (`role_missing`/`phase_identity_missing`) from the resolver itself --
    `timebase_incompatible`/`reference_frequency_conflict`/
    `not_applicable` are not reachable for a ONE-role requirement (see
    `resolve_requirement()`'s own docstring: those need >= 2 roles or a
    Phasor-specific check this function's own caller performs
    separately), so this function's own mapping is deliberately narrow,
    not a generic status translator."""
    if resolution.status == STATUS_AMBIGUOUS:
        return ROLE_STATUS_AMBIGUOUS, "ambiguous_candidates"
    reason = resolution.missing_role_reasons.get(role_key)
    if reason == "phase_identity_missing":
        return ROLE_STATUS_NEEDS_CONFIGURATION, reason
    return ROLE_STATUS_MISSING, reason or "role_missing"


def compute_phasor_diagram(
    *,
    workspace_id: str,
    engineering_context_id: str,
    analysis_time: float,
    reference_frequency_hz_override: float | None,
    context_registry: EngineeringContextRegistry,
    source_registry: WorkspaceRegistry,
    calculated_channel_registry: CalculatedChannelRegistry,
) -> PhasorDiagramResult:
    """The bay-centric aggregation entry point -- resolves and estimates
    ALL SIX supported roles (`PHASOR_DIAGRAM_ROLE_ORDER`) for one
    Engineering Context independently, at one selected `analysis_time`.
    Never an all-or-nothing three-phase assumption: a context with only
    `Va`+`Ia` returns exactly those two as `available` and the other
    four as `missing`, never a whole-result failure.

    **Per-role vs. whole-result status** (owner's own explicit
    separation): a role being `missing`/`ambiguous`/`not_eligible` NEVER
    blocks any OTHER role's own computation -- each of the six single-
    phase requirements is resolved via `resolve_analysis_inputs()`
    (Slice 2, entirely unchanged) INDEPENDENTLY, so one role's own
    identity failure has zero effect on the others. Only a condition
    that would make the COMBINED diagram itself misleading blocks
    EVERY role's own numeric result at once, reported as the whole-
    result `status=needs_configuration`:

    - an invalid explicit `reference_frequency_hz` override;
    - resolved candidates' own sources declaring CONFLICTING nominal
      frequencies with no override supplied (identical policy to
      `compute_phasor_analysis()`'s own single-requirement version);
    - a resolved candidate with no known absolute source start time;
    - a genuine TIMEBASE incompatibility among the roles that would
      otherwise be drawn together (`timebases_aligned()`, reused
      unchanged -- this module's own addition, since six INDEPENDENT
      single-role resolutions never trigger the resolver's own internal
      three-phase timebase check the way `PHASOR_VOLTAGE_THREE_PHASE`
      does).

    When blocked, every role whose channel IDENTITY was already known
    (would otherwise have been estimated) is reported as
    `needs_configuration` with the SAME blocking reason -- never left
    without a status, never given a fabricated numeric result.

    **Angle convention for the shared diagram**: `angle_deg_absolute` is
    the ONLY angle this function's own geometry-relevant output ever
    treats as authoritative (owner's own explicit "must not destroy the
    true V-I angular relationship" requirement) -- `angle_deg_relative`
    is computed per family (`Va` for Voltage, `Ia` for Current) purely as
    secondary table information, `None` whenever that family's own
    reference role is not itself `available`.

    **`analysis_time` semantics**: identical in kind to
    `compute_phasor_analysis()`'s own convention -- elapsed seconds since
    the start of whichever role is the "anchor." Here the anchor is
    whichever role is FIRST in `PHASOR_DIAGRAM_ROLE_ORDER`
    (`Va`/`Vb`/`Vc`/`Ia`/`Ib`/`Ic`) among the roles that end up eligible
    for estimation -- for the common full-bay case this is `Va`, exactly
    matching the original single-requirement endpoint's own anchor for
    `PHASOR_VOLTAGE_THREE_PHASE`.

    Raises `EngineeringContextNotFoundError` exactly like
    `resolve_analysis_inputs()` itself does (propagated unchanged); every
    OTHER failure mode is returned as a `PhasorDiagramResult`, never an
    exception. Never persisted -- always derived fresh.
    """
    role_statuses: dict[str, str] = {}
    role_reason_codes: dict[str, str | None] = {}
    candidates: dict[str, _RoleCandidate] = {}

    for role_key in PHASOR_DIAGRAM_ROLE_ORDER:
        requirement = _DIAGRAM_REQUIREMENTS_BY_ROLE[role_key]
        resolution = resolve_analysis_inputs(
            workspace_id=workspace_id, engineering_context_id=engineering_context_id,
            analysis_kind=requirement.analysis_kind, mode=requirement.mode,
            context_registry=context_registry, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
        if resolution.status != STATUS_RESOLVED:
            status, reason_code = _diagram_role_status_for_resolution(role_key, resolution)
            role_statuses[role_key] = status
            role_reason_codes[role_key] = reason_code
            continue

        ref = resolution.resolved_roles[role_key]
        candidate = _fetch_role_candidate(
            role_key, ref, workspace_id=workspace_id, source_registry=source_registry,
            calculated_channel_registry=calculated_channel_registry,
        )
        if candidate is None:
            role_statuses[role_key] = ROLE_STATUS_NEEDS_CONFIGURATION
            role_reason_codes[role_key] = _REASON_CHANNEL_UNAVAILABLE
            continue
        candidates[role_key] = candidate

    if not candidates:
        return PhasorDiagramResult(
            status=PHASOR_STATUS_COMPUTED, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            roles=_assemble_identity_only_roles(role_statuses, role_reason_codes, {}),
            message="No supported Phasor roles are currently resolvable for this Engineering Context.",
        )

    # ---- Reference frequency: explicit override, else unanimous agreement ----
    # Computed across every IDENTITY-resolved candidate (not just the
    # eventually-eligible ones) -- identical ordering/policy to
    # `compute_phasor_analysis()`'s own single-requirement version, see
    # that function's own comment for why (waveform-form eligibility
    # itself needs a reference frequency as an input, so it cannot be
    # computed only from the post-eligibility subset).
    if reference_frequency_hz_override is not None:
        if not nominal_frequency_valid(reference_frequency_hz_override):
            return _blocked_diagram_result(
                engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                reason_code=REASON_INVALID_REFERENCE_FREQUENCY,
                message="The supplied reference_frequency_hz is outside the plausible range.",
                role_statuses=role_statuses, role_reason_codes=role_reason_codes, candidates=candidates,
            )
        reference_frequency_hz = reference_frequency_hz_override
    else:
        declared = [c.nominal_frequency for c in candidates.values()]
        first = declared[0]
        if not all(math.isclose(f, first, rel_tol=1e-9, abs_tol=1e-9) for f in declared):
            return _blocked_diagram_result(
                engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                reason_code=REASON_REFERENCE_FREQUENCY_CONFLICT,
                message=(
                    "Resolved roles come from sources declaring different nominal frequencies; supply an explicit "
                    "reference_frequency_hz to compute a combined diagram."
                ),
                role_statuses=role_statuses, role_reason_codes=role_reason_codes, candidates=candidates,
            )
        reference_frequency_hz = first

    # ---- Waveform-form eligibility, per role -- never blocks others ----
    eligible_candidates: dict[str, _RoleCandidate] = {}
    for role_key, candidate in candidates.items():
        if _waveform_form_eligible(candidate, reference_frequency_hz):
            eligible_candidates[role_key] = candidate
        else:
            role_statuses[role_key] = ROLE_STATUS_NOT_ELIGIBLE
            role_reason_codes[role_key] = REASON_WAVEFORM_FORM_NOT_ELIGIBLE

    if not eligible_candidates:
        return PhasorDiagramResult(
            status=PHASOR_STATUS_COMPUTED, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reference_frequency_hz=reference_frequency_hz,
            roles=_assemble_identity_only_roles(role_statuses, role_reason_codes, candidates),
            message="No eligible Phasor roles could be estimated for this Engineering Context.",
        )

    # ---- Shared, source-independent absolute-time coordinate ----
    start_epochs = [c.start_epoch for c in eligible_candidates.values()]
    if any(epoch is None for epoch in start_epochs):
        return _blocked_diagram_result(
            engineering_context_id=engineering_context_id, analysis_time=analysis_time,
            reason_code="absolute_time_unavailable", message="One or more resolved sources have no known absolute start time.",
            role_statuses=role_statuses, role_reason_codes=role_reason_codes, candidates=candidates,
        )
    reference_epoch = min(start_epochs)

    # ---- Cross-role timebase compatibility (this module's own check --
    # six INDEPENDENT single-role resolutions never trigger the
    # resolver's own internal check, unlike a real multi-role
    # requirement) ----
    eligible_items = list(eligible_candidates.items())
    if len(eligible_items) > 1:
        first_key, first_candidate = eligible_items[0]
        for role_key, candidate in eligible_items[1:]:
            if not timebases_aligned(
                first_candidate.reference_source_id, first_candidate.time, first_candidate.start_epoch,
                candidate.reference_source_id, candidate.time, candidate.start_epoch,
            ):
                return _blocked_diagram_result(
                    engineering_context_id=engineering_context_id, analysis_time=analysis_time,
                    reason_code="timebase_incompatible",
                    message="Resolved roles are not proven to share a common sample time; a combined diagram is unavailable.",
                    role_statuses=role_statuses, role_reason_codes=role_reason_codes, candidates=candidates,
                )

    anchor_role_key = next(role_key for role_key in PHASOR_DIAGRAM_ROLE_ORDER if role_key in eligible_candidates)
    anchor_candidate = eligible_candidates[anchor_role_key]
    analysis_time_shared = (anchor_candidate.start_epoch - reference_epoch) + analysis_time

    window_seconds = 1.0 / reference_frequency_hz
    estimates: dict[str, PhasorEstimate] = {}
    for role_key, candidate in eligible_candidates.items():
        t_shared = (candidate.start_epoch - reference_epoch) + candidate.time
        estimates[role_key] = estimate_phasor(t_shared, candidate.values, analysis_time_shared, reference_frequency_hz)

    for role_key, est in estimates.items():
        if not est.available:
            role_statuses[role_key] = ROLE_STATUS_NEEDS_CONFIGURATION
            role_reason_codes[role_key] = est.reason_code

    # ---- Per-family relative-angle reference (secondary/table info only) ----
    voltage_reference_angle = (
        estimates[PHASOR_DIAGRAM_VOLTAGE_REFERENCE_ROLE].angle_deg
        if PHASOR_DIAGRAM_VOLTAGE_REFERENCE_ROLE in estimates and estimates[PHASOR_DIAGRAM_VOLTAGE_REFERENCE_ROLE].available
        else None
    )
    current_reference_angle = (
        estimates[PHASOR_DIAGRAM_CURRENT_REFERENCE_ROLE].angle_deg
        if PHASOR_DIAGRAM_CURRENT_REFERENCE_ROLE in estimates and estimates[PHASOR_DIAGRAM_CURRENT_REFERENCE_ROLE].available
        else None
    )

    roles_out: dict[str, PhasorDiagramRoleResult] = {}
    for role_key in PHASOR_DIAGRAM_ROLE_ORDER:
        if role_key in estimates and estimates[role_key].available:
            est = estimates[role_key]
            candidate = eligible_candidates[role_key]
            family_reference_angle = voltage_reference_angle if role_key.startswith("V") else current_reference_angle
            roles_out[role_key] = PhasorDiagramRoleResult(
                status=ROLE_STATUS_AVAILABLE, channel_ref=candidate.channel_ref,
                magnitude_rms=est.magnitude_rms, unit=candidate.unit, angle_deg_absolute=est.angle_deg,
                angle_deg_relative=(
                    relative_angle_deg(est.angle_deg, family_reference_angle) if family_reference_angle is not None else None
                ),
            )
        else:
            roles_out[role_key] = PhasorDiagramRoleResult(
                status=role_statuses.get(role_key, ROLE_STATUS_MISSING),
                channel_ref=candidates[role_key].channel_ref if role_key in candidates else None,
                reason_code=role_reason_codes.get(role_key),
            )

    return PhasorDiagramResult(
        status=PHASOR_STATUS_COMPUTED, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        reference_frequency_hz=reference_frequency_hz, window_seconds=window_seconds,
        roles=roles_out, message="Available Phasor roles resolved and estimated.",
    )


def _assemble_identity_only_roles(
    role_statuses: dict[str, str], role_reason_codes: dict[str, str | None], candidates: dict[str, _RoleCandidate],
) -> dict[str, PhasorDiagramRoleResult]:
    """Builds the per-role result dict for a request that never reached
    the estimation stage at all (no candidate was identity-resolved, or
    none turned out waveform-form eligible) -- every role gets whatever
    status/reason it already earned during resolution/eligibility, never
    a numeric result."""
    return {
        role_key: PhasorDiagramRoleResult(
            status=role_statuses.get(role_key, ROLE_STATUS_MISSING),
            channel_ref=candidates[role_key].channel_ref if role_key in candidates else None,
            reason_code=role_reason_codes.get(role_key),
        )
        for role_key in PHASOR_DIAGRAM_ROLE_ORDER
    }


def _blocked_diagram_result(
    *, engineering_context_id: str, analysis_time: float, reason_code: str, message: str,
    role_statuses: dict[str, str], role_reason_codes: dict[str, str | None], candidates: dict[str, _RoleCandidate],
) -> PhasorDiagramResult:
    """Assembles the WHOLE-RESULT-blocked response: every role whose
    channel identity was already known (a `_RoleCandidate` exists) is
    reported as `needs_configuration` with the SAME blocking reason
    (never left without a status, never given a fabricated numeric
    result); roles that were already `missing`/`ambiguous`/`not_eligible`
    before the block was detected keep their own, more specific status."""
    roles_out: dict[str, PhasorDiagramRoleResult] = {}
    for role_key in PHASOR_DIAGRAM_ROLE_ORDER:
        if role_key in candidates and role_key not in role_statuses:
            roles_out[role_key] = PhasorDiagramRoleResult(
                status=ROLE_STATUS_NEEDS_CONFIGURATION, channel_ref=candidates[role_key].channel_ref, reason_code=reason_code,
            )
        else:
            roles_out[role_key] = PhasorDiagramRoleResult(
                status=role_statuses.get(role_key, ROLE_STATUS_MISSING),
                channel_ref=candidates[role_key].channel_ref if role_key in candidates else None,
                reason_code=role_reason_codes.get(role_key),
            )
    return PhasorDiagramResult(
        status=STATUS_NEEDS_CONFIGURATION, engineering_context_id=engineering_context_id, analysis_time=analysis_time,
        roles=roles_out, reason_code=reason_code, message=message,
    )
