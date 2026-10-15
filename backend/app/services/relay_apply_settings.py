"""Apply Settings (Slice 9): backend-authoritative apply of a reviewed relay import.

Stateless, like review validation -- the caller sends the original interpretation
(the review's validation context) and the same decisions; nothing the browser
computed is trusted:

    original interpretation + decisions
        -> effective reviewed model, engine adapter re-run, readiness re-derived
        -> refused unless readiness is ``ready`` or ``ready_approximate`` (DEC-198)
        -> apply plan: only what the existing Distance Protection form can hold

Either a complete plan is returned or an error -- never a partial plan. Nothing is
stored, cached, logged or written to the analysis state here; the browser populates
its own form with the returned values.
"""

from __future__ import annotations

from app.domain.relay_import.apply_settings import ApplyPlan, ApplyRejectedError, build_apply_plan
from app.domain.relay_import.review_state import APPLICABLE_READINESS, Readiness, ReviewDecisions
from app.domain.relay_import.canonical_distance import SettingBasis
from app.services.relay_review_validation import reviewed_state

__all__ = ["ApplyNotReadyError", "ApplyRejectedError", "apply_reviewed_settings"]


class ApplyNotReadyError(ValueError):
    """The reviewed settings are not ready to apply. The message is a fixed phrase."""


_NOT_READY = {
    Readiness.NOT_READY.value: "The relay settings are not ready to apply. Resolve the blocking settings in the review first.",
    Readiness.READY_AFTER_CONFIRMATION.value: "Confirm the remaining assumptions in the review before applying.",
}


def apply_reviewed_settings(context: dict, decisions: ReviewDecisions) -> ApplyPlan:
    effective, adaptation, review = reviewed_state(context, decisions)
    if review.readiness.status not in {r.value for r in APPLICABLE_READINESS}:
        raise ApplyNotReadyError(_NOT_READY.get(review.readiness.status, _NOT_READY[Readiness.NOT_READY.value]))
    basis = effective.transformers.setting_basis
    if not basis.is_resolved or basis.value is SettingBasis.UNKNOWN:
        raise ApplyRejectedError("The primary/secondary basis of the impedance settings is unknown.")
    return build_apply_plan(effective, adaptation, impedance_basis=basis.value.value)
