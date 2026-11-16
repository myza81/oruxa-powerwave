"""Physical calibration authority domain contract and eligibility evaluator.

Stage 3A — foundation only. No calibration enforcement is activated in
this stage. No production BEN5K voltage or current correction is applied.

A per-channel PhysicalCalibrationAuthority describes whether the numerical
interpretation of a recorded measurement has adequate independent evidence
for its intended engineering use.

It is independent of:
  - binary sample decoding correctness
  - channel mapping to the right descriptor
  - missing-data validity
  - measurement reference side (Primary / Secondary / Unknown)
  - nominal voltage or current bases
  - per-unit configuration or channel classification

A correctly decoded, correctly mapped sample may still represent a
physically unverified engineering quantity if the numerical transform
(gain, offset, bit-packing convention) has not been independently validated
against an external reference.

Authority contract
------------------
An absent authority (``None`` on the channel) means NOT ASSESSED — this
preserves existing compatibility behaviour for all existing providers
(COMTRADE, CSV, SubBen/BEN32) and never counts as Verified.

Dependency propagation for calculated channels (Section 7 of the brief):
  1. Any Invalid leaf makes an authoritative result unavailable.
  2. Otherwise any explicitly Unverified leaf makes an authoritative
     result unavailable.
  3. A mix of Verified + not-assessed leaves cannot claim full Verified.
  4. All-Verified leaves are necessary (not sufficient) for eligibility.
  5. Not-assessed leaves alone preserve existing compatibility behaviour.

Stage 3B integration points (not activated in Stage 3A):
  - ben/legacy_ben5k/normalize.py
  - waveform_service._resolve_effective_per_unit()
  - calculated_channel_service._resolve_input()
  - phasor_analysis_service._fetch_role_candidate()
  - compliance_readiness_service

Change governance: do not modify this module's public API without an
approved DECISIONS.md entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence


# ---------------------------------------------------------------------------
# Calibration status
# ---------------------------------------------------------------------------

CalibrationStatus = Literal["verified", "unverified", "invalid"]

CALIBRATION_VERIFIED: CalibrationStatus = "verified"
CALIBRATION_UNVERIFIED: CalibrationStatus = "unverified"
CALIBRATION_INVALID: CalibrationStatus = "invalid"

KNOWN_CALIBRATION_STATUSES: tuple[CalibrationStatus, ...] = (
    CALIBRATION_VERIFIED,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_INVALID,
)


# ---------------------------------------------------------------------------
# Operation purposes
# ---------------------------------------------------------------------------

CalibrationOperationPurpose = Literal[
    "raw_inspection",          # waveform display; raw sample reading
    "exploratory_analysis",    # shape/magnitude investigation; limitation inherited
    "engineering_calculation", # authoritative RMS, phasor, power, sequence
    "compliance_assessment",   # relay/protection compliance verdict
]

PURPOSE_RAW_INSPECTION: CalibrationOperationPurpose = "raw_inspection"
PURPOSE_EXPLORATORY_ANALYSIS: CalibrationOperationPurpose = "exploratory_analysis"
PURPOSE_ENGINEERING_CALCULATION: CalibrationOperationPurpose = "engineering_calculation"
PURPOSE_COMPLIANCE_ASSESSMENT: CalibrationOperationPurpose = "compliance_assessment"

KNOWN_CALIBRATION_PURPOSES: tuple[CalibrationOperationPurpose, ...] = (
    PURPOSE_RAW_INSPECTION,
    PURPOSE_EXPLORATORY_ANALYSIS,
    PURPOSE_ENGINEERING_CALCULATION,
    PURPOSE_COMPLIANCE_ASSESSMENT,
)


# ---------------------------------------------------------------------------
# Availability reasons
# ---------------------------------------------------------------------------

REASON_AVAILABLE = "available"
REASON_UNVERIFIED = "physical_calibration_unverified"
REASON_INVALID = "physical_calibration_invalid"
REASON_NOT_ASSESSED = "not_assessed"
# Mix of Verified + not-assessed leaves — cannot claim full Verified.
REASON_NOT_FULLY_VERIFIED = "not_fully_verified"

KNOWN_AVAILABILITY_REASONS: tuple[str, ...] = (
    REASON_AVAILABLE,
    REASON_UNVERIFIED,
    REASON_INVALID,
    REASON_NOT_ASSESSED,
    REASON_NOT_FULLY_VERIFIED,
)

# Well-known machine-readable reason codes for authority objects.
# Adapters may supply additional codes; these are the canonical ones.
REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED = "ben5k_absolute_calibration_unverified"
REASON_CODE_BEN5K_TIME_BASIS_UNCONFIRMED = "ben5k_time_basis_unconfirmed"
REASON_CODE_VOLTAGE_LL_RMS_CROSSCHECK = "voltage_ll_rms_nominal_crosscheck"


# ---------------------------------------------------------------------------
# Immutable evidence reference
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Immutable pointer to calibration evidence.

    Does not embed raw recordings or private data. Identifies the evidence
    without reproducing it. Scope and method provide context for evaluating
    the evidence's applicability and limits.
    """

    description: str
    scope: str = ""
    method: str | None = None
    hash_ref: str | None = None


# ---------------------------------------------------------------------------
# Immutable per-channel calibration authority
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PhysicalCalibrationAuthority:
    """Immutable calibration authority for one analog channel.

    Fields
    ------
    status       — CALIBRATION_VERIFIED, CALIBRATION_UNVERIFIED, or
                   CALIBRATION_INVALID.
    reason       — machine-readable reason code (non-empty string).
    transform_id — versioned identifier for the numerical transform
                   (raw word → engineering value). Prevents double-scaling:
                   a consumer that is about to apply the same transform
                   can check this identifier. Must not independently trigger
                   scaling; it only describes what transform was already
                   applied or is assumed.
    evidence_refs — immutable tuple of evidence references. May be empty
                   for Unverified channels (no evidence established yet).

    Renaming or regrouping a channel does not alter this object — it is
    bound to the source channel identity and transform version, not to
    display labels or measurement groups.
    """

    status: CalibrationStatus
    reason: str
    transform_id: str
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in KNOWN_CALIBRATION_STATUSES:
            raise ValueError(
                f"Invalid calibration status {self.status!r}. "
                f"Must be one of {KNOWN_CALIBRATION_STATUSES}."
            )
        if not self.reason:
            raise ValueError("reason must be a non-empty string.")
        if not self.transform_id:
            raise ValueError("transform_id must be a non-empty string.")


# ---------------------------------------------------------------------------
# Eligibility result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CalibrationEligibility:
    """Result of evaluating calibration eligibility for one operation.

    Fields
    ------
    eligible               — True when this operation may proceed under the
                             calibration contract (subject to other domain
                             checks the evaluator does not perform).
    reason                 — REASON_* constant describing the outcome.
    has_invalid_leaves     — at least one contributing leaf is invalid.
    has_unverified_leaves  — at least one contributing leaf is unverified
                             (and no invalid leaves).
    has_not_assessed_leaves — at least one contributing leaf has no authority
                              object (not assessed).
    all_verified           — every leaf carries an explicit Verified authority
                             and there are no not-assessed leaves. Only when
                             True may downstream services claim Verified.
    limiting_transform_ids — transform_ids of leaves that caused a limitation.
                             Empty when all leaves are verified or not-assessed.
    """

    eligible: bool
    reason: str
    has_invalid_leaves: bool
    has_unverified_leaves: bool
    has_not_assessed_leaves: bool
    all_verified: bool
    limiting_transform_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Eligibility evaluator
# ---------------------------------------------------------------------------

def evaluate_calibration_eligibility(
    leaf_authorities: Sequence[PhysicalCalibrationAuthority | None],
    purpose: CalibrationOperationPurpose,
) -> CalibrationEligibility:
    """Evaluate whether the given leaf channel authorities permit an operation.

    Parameters
    ----------
    leaf_authorities:
        One entry per contributing source leaf channel. ``None`` means the
        channel has no calibration authority (not assessed). Pass a single-
        element sequence for a direct source channel; pass the full resolved
        leaf list for a calculated channel.
    purpose:
        Intended use of the result.

    Returns
    -------
    CalibrationEligibility
        Structured eligibility result. Pure computation — no waveform
        decoding, numerical scaling, per-unit conversion or calculation.

    Policy
    ------
    Invalid leaf dominates all others.
    Unverified leaf dominates not-assessed.
    A mix of Verified + not-assessed cannot claim full Verified status.
    An empty leaf list (no inputs) is treated as all-Verified — no known
    calibration limitation. **This is a vacuous truth, not physical certification
    evidence.** Callers responsible for calculated-channel provenance must
    independently verify that at least one required physical-leaf authority is
    present (e.g. via ``_collect_leaf_authorities()``) before calling this
    function; passing the result of ``all_verified=True`` from an empty list
    as evidence of physical calibration is incorrect.

    ``eligible=True`` with ``reason=not_assessed`` preserves existing
    compatibility behaviour; it does NOT grant Verified status and must
    not be treated as equivalent to ``reason=available``.
    """
    if purpose not in KNOWN_CALIBRATION_PURPOSES:
        raise ValueError(
            f"Unknown calibration purpose {purpose!r}. "
            f"Must be one of {KNOWN_CALIBRATION_PURPOSES}."
        )

    has_invalid = False
    has_unverified = False
    has_not_assessed = False
    has_verified = False
    limiting: list[str] = []

    for auth in leaf_authorities:
        if auth is None:
            has_not_assessed = True
        elif auth.status == CALIBRATION_INVALID:
            has_invalid = True
            limiting.append(auth.transform_id)
        elif auth.status == CALIBRATION_UNVERIFIED:
            has_unverified = True
            limiting.append(auth.transform_id)
        else:
            has_verified = True

    limiting_tuple = tuple(limiting)

    if has_invalid:
        return _result_for_invalid(
            purpose, limiting_tuple, has_unverified, has_not_assessed,
        )
    if has_unverified:
        return _result_for_unverified(
            purpose, limiting_tuple, has_not_assessed, has_verified,
        )
    if has_not_assessed:
        return _result_for_not_assessed(purpose, has_verified)

    # All leaves are explicitly Verified, or list is empty.
    return CalibrationEligibility(
        eligible=True,
        reason=REASON_AVAILABLE,
        has_invalid_leaves=False,
        has_unverified_leaves=False,
        has_not_assessed_leaves=False,
        all_verified=True,
        limiting_transform_ids=(),
    )


def _result_for_invalid(
    purpose: CalibrationOperationPurpose,
    limiting: tuple[str, ...],
    has_unverified: bool,
    has_not_assessed: bool,
) -> CalibrationEligibility:
    """Policy when at least one leaf is explicitly Invalid."""
    # Raw inspection: diagnostic only — eligible but reason signals limitation.
    # All other purposes: blocked.
    eligible = purpose == PURPOSE_RAW_INSPECTION
    return CalibrationEligibility(
        eligible=eligible,
        reason=REASON_INVALID,
        has_invalid_leaves=True,
        has_unverified_leaves=has_unverified,
        has_not_assessed_leaves=has_not_assessed,
        all_verified=False,
        limiting_transform_ids=limiting,
    )


def _result_for_unverified(
    purpose: CalibrationOperationPurpose,
    limiting: tuple[str, ...],
    has_not_assessed: bool,
    has_verified: bool,
) -> CalibrationEligibility:
    """Policy when at least one leaf is explicitly Unverified (no Invalid)."""
    # Raw inspection: allowed with limitation.
    # Exploratory analysis: conditionally allowed; limitation inherited by result.
    # Engineering calculation, compliance assessment: blocked.
    eligible = purpose in (PURPOSE_RAW_INSPECTION, PURPOSE_EXPLORATORY_ANALYSIS)
    return CalibrationEligibility(
        eligible=eligible,
        reason=REASON_UNVERIFIED,
        has_invalid_leaves=False,
        has_unverified_leaves=True,
        has_not_assessed_leaves=has_not_assessed,
        all_verified=False,
        limiting_transform_ids=limiting,
    )


def _result_for_not_assessed(
    purpose: CalibrationOperationPurpose,
    has_verified: bool,
) -> CalibrationEligibility:
    """Policy when leaves include not-assessed channels (no Invalid or Unverified).

    Preserves existing compatibility behaviour. Never claims Verified status.
    A mix of Verified + not-assessed uses REASON_NOT_FULLY_VERIFIED so
    callers can distinguish it from a pure not-assessed set.
    """
    del purpose  # not_assessed behaviour is purpose-independent (compat preserved)
    reason = REASON_NOT_FULLY_VERIFIED if has_verified else REASON_NOT_ASSESSED
    return CalibrationEligibility(
        eligible=True,
        reason=reason,
        has_invalid_leaves=False,
        has_unverified_leaves=False,
        has_not_assessed_leaves=True,
        all_verified=False,
        limiting_transform_ids=(),
    )


# ---------------------------------------------------------------------------
# Convenience predicates
# ---------------------------------------------------------------------------

def is_eligible(result: CalibrationEligibility) -> bool:
    """True when the operation may proceed under the calibration contract."""
    return result.eligible


def is_fully_verified(result: CalibrationEligibility) -> bool:
    """True when every contributing leaf is explicitly Verified with no
    not-assessed leaves.  Only then may a downstream service claim that
    the result is physically calibration-verified.
    """
    return result.all_verified


def is_blocked_by_calibration(result: CalibrationEligibility) -> bool:
    """True when the operation is blocked due to calibration limitations."""
    return not result.eligible


def is_compatibility_mode(result: CalibrationEligibility) -> bool:
    """True when the result preserves existing compatibility behaviour
    (not-assessed leaves only, no Verified claim, not blocked).
    """
    return (
        result.eligible
        and not result.all_verified
        and not result.has_invalid_leaves
        and not result.has_unverified_leaves
    )
