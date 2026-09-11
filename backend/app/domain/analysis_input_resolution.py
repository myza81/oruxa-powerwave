"""Automatic Analysis Input Resolver -- pure resolution logic (Analysis
Guardrail Slice 2; see docs/project-memory/ANALYSIS_INPUT_GUARDRAILS.md).

Pure, framework-free role matching -- no registry, no I/O, no workspace
state. Given one `AnalysisRequirement` (`app.domain.analysis_requirements`)
and a flat list of `ResolvedCandidate`s (already-resolved engineering
metadata for one `EngineeringContext`'s own membership, assembled by
`app.services.analysis_input_resolution_service`), matches each required
role against candidates by `engineering_type` + canonical `phase` ONLY --
**never by channel name**. Persisted context/phase metadata is the sole
authority at resolution time; channel-name evidence may have helped an
earlier detection pass (`app.domain.engineering_context_detection`), but
plays no role here.

Timebase/cross-source alignment is deliberately NOT checked here -- that
requires real sample arrays (I/O), so it is layered on top by the
service after this pure function returns a `resolved` result (see that
module's own docstring for why).

**The one strict rule this module enforces absolutely**: a role is never
resolved by picking among more than one equally-valid candidate. More
than one candidate matching the exact same `(engineering_type, phase)`
is always `ambiguous`, regardless of channel kind (raw vs. calculated),
name, or detection provenance -- there is no tie-breaking heuristic
anywhere in this module, by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.analysis_requirements import AnalysisRequirement
from app.domain.calculated_channel import ChannelRef
from app.domain.phase_identity import PHASE_UNKNOWN

STATUS_RESOLVED = "resolved"
STATUS_NEEDS_CONFIGURATION = "needs_configuration"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NOT_APPLICABLE = "not_applicable"
KNOWN_RESOLUTION_STATUSES = (STATUS_RESOLVED, STATUS_NEEDS_CONFIGURATION, STATUS_AMBIGUOUS, STATUS_NOT_APPLICABLE)

#: Per-missing-role reason codes. `ROLE_MISSING` -- nothing in the
#: context matches this role's engineering_type+phase at all.
#: `PHASE_IDENTITY_MISSING` -- at least one context member has the right
#: engineering_type but an unresolved (`unknown`) phase, so the role is
#: potentially satisfiable once an engineer confirms that member's phase
#: (an actionable, more specific diagnostic than a bare "missing" --
#: owner instruction: "Return an actionable status... Do not guess from
#: the channel name at resolver time" -- this never guesses WHICH phase
#: it should be, only surfaces that a candidate needs configuration).
REASON_ROLE_MISSING = "role_missing"
REASON_PHASE_IDENTITY_MISSING = "phase_identity_missing"
REASON_AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
REASON_MULTIPLE_ISSUES = "multiple_issues"
REASON_TIMEBASE_INCOMPATIBLE = "timebase_incompatible"
REASON_EMPTY_REQUIREMENT = "empty_requirement"


@dataclass(frozen=True, slots=True)
class ResolvedCandidate:
    """One `EngineeringContext` member's own already-resolved engineering
    metadata -- the resolver's entire input alongside the requirement.
    Assembled by the service layer from live workspace state (a source
    channel's `AnalogChannelSummary`, or a calculated channel's own
    `CalculatedChannel` fields); this module never fetches anything
    itself. `unit` is used ONLY for `numerically_ready` (never to gate
    role identity -- a blank unit with a known `engineering_type` still
    matches a role; see module docstring / owner's own unit-handling
    instruction)."""

    channel_ref: ChannelRef
    engineering_type: str
    phase: str
    phase_source: str
    unit: str | None


@dataclass(slots=True)
class AnalysisInputResolution:
    """The reusable whole-analysis resolution result. Never persisted --
    always derived fresh from current context/channel state (owner
    instruction)."""

    status: str
    analysis_kind: str
    mode: str
    engineering_context_id: str
    required_roles: list[str] = field(default_factory=list)
    resolved_roles: dict[str, ChannelRef] = field(default_factory=dict)
    missing_roles: list[str] = field(default_factory=list)
    #: Per-missing-role diagnostic detail -- role_key -> reason code
    #: (`REASON_ROLE_MISSING`/`REASON_PHASE_IDENTITY_MISSING`). Only
    #: populated for roles present in `missing_roles`. An addition beyond
    #: the audit's own top-level sketch, needed to satisfy the owner's
    #: own "use precise role-level diagnostics" instruction -- a flat
    #: `missing_roles` list alone cannot distinguish "nothing plausible
    #: exists" from "a candidate exists but needs its phase confirmed".
    missing_role_reasons: dict[str, str] = field(default_factory=dict)
    ambiguous_roles: dict[str, list[ChannelRef]] = field(default_factory=dict)
    #: Whole-resolution readiness for actual numerical calculation --
    #: separate from role IDENTITY resolution (owner's own explicit
    #: "do not merge these concepts" instruction). Always `False` unless
    #: `status == STATUS_RESOLVED` AND every resolved role's own
    #: candidate carries a non-blank unit.
    numerically_ready: bool = False
    reason_code: str | None = None
    message: str = ""


def _candidates_for_role(role, candidates: list[ResolvedCandidate]) -> list[ResolvedCandidate]:
    return [c for c in candidates if c.engineering_type == role.engineering_type and c.phase == role.phase]


def _has_phase_identity_missing_candidate(role, candidates: list[ResolvedCandidate]) -> bool:
    return any(c.engineering_type == role.engineering_type and c.phase == PHASE_UNKNOWN for c in candidates)


def _summarize(
    *, missing_roles: list[str], missing_role_reasons: dict[str, str], ambiguous_roles: dict[str, list[ChannelRef]]
) -> tuple[str, str | None, str]:
    if ambiguous_roles:
        roles_text = ", ".join(sorted(ambiguous_roles))
        return (
            STATUS_AMBIGUOUS,
            REASON_AMBIGUOUS_CANDIDATES,
            f"More than one valid candidate exists for: {roles_text}. Manual confirmation required.",
        )
    if missing_roles:
        distinct_reasons = {missing_role_reasons[r] for r in missing_roles}
        reason_code = distinct_reasons.pop() if len(distinct_reasons) == 1 else REASON_MULTIPLE_ISSUES
        roles_text = ", ".join(missing_roles)
        return STATUS_NEEDS_CONFIGURATION, reason_code, f"Required role(s) not resolved: {roles_text}."
    return STATUS_RESOLVED, None, "All required roles resolved."


def resolve_requirement(
    requirement: AnalysisRequirement,
    candidates: list[ResolvedCandidate],
    *,
    engineering_context_id: str,
) -> AnalysisInputResolution:
    """The one pure resolution entry point. Matches every one of
    `requirement.required_roles` against `candidates` by
    `engineering_type` + canonical `phase` only. No completeness
    assumption: `requirement.required_roles` is whatever the caller's
    own selected analysis mode declares (a single-phase requirement has
    one role; a three-phase requirement has three) -- this function
    never requires anything beyond exactly those roles."""
    required_role_keys = [role.role_key for role in requirement.required_roles]
    if not requirement.required_roles:
        return AnalysisInputResolution(
            status=STATUS_NOT_APPLICABLE, analysis_kind=requirement.analysis_kind, mode=requirement.mode,
            engineering_context_id=engineering_context_id, required_roles=required_role_keys,
            reason_code=REASON_EMPTY_REQUIREMENT, message="This requirement declares no required roles.",
        )

    resolved_roles: dict[str, ChannelRef] = {}
    missing_roles: list[str] = []
    missing_role_reasons: dict[str, str] = {}
    ambiguous_roles: dict[str, list[ChannelRef]] = {}

    for role in requirement.required_roles:
        matches = _candidates_for_role(role, candidates)
        if len(matches) == 1:
            resolved_roles[role.role_key] = matches[0].channel_ref
        elif len(matches) > 1:
            ambiguous_roles[role.role_key] = [c.channel_ref for c in matches]
        else:
            missing_roles.append(role.role_key)
            missing_role_reasons[role.role_key] = (
                REASON_PHASE_IDENTITY_MISSING
                if _has_phase_identity_missing_candidate(role, candidates)
                else REASON_ROLE_MISSING
            )

    status, reason_code, message = _summarize(
        missing_roles=missing_roles, missing_role_reasons=missing_role_reasons, ambiguous_roles=ambiguous_roles
    )
    numerically_ready = status == STATUS_RESOLVED and all(
        next(c.unit for c in candidates if c.channel_ref == ref) for ref in resolved_roles.values()
    )

    return AnalysisInputResolution(
        status=status, analysis_kind=requirement.analysis_kind, mode=requirement.mode,
        engineering_context_id=engineering_context_id, required_roles=required_role_keys,
        resolved_roles=resolved_roles, missing_roles=missing_roles, missing_role_reasons=missing_role_reasons,
        ambiguous_roles=ambiguous_roles, numerically_ready=bool(numerically_ready),
        reason_code=reason_code, message=message,
    )
