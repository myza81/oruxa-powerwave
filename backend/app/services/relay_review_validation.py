"""Review validation (Slice 8): re-evaluate a review from the user's decisions.

Stateless by design -- the platform keeps nothing between requests and import
data is ephemeral, so there is no session to look an interpretation up in. The
caller supplies the original interpretation (the review's *validation context*,
see `canonical_codec`) together with its decisions, and this returns the reviewed
state:

    original interpretation  +  decisions
        -> effective reviewed model          (the original is never edited)
        -> engine adapter, re-run
        -> review state: statuses, counts, blocking issues, readiness

The browser never decides readiness: it only holds the decisions and the
interpretation and asks. Nothing is stored, logged or applied to the Distance
Protection form.
"""

from __future__ import annotations

from app.domain.relay_import.canonical_codec import SnapshotError, decode_model
from app.domain.relay_import.raw_document import RawRelayDocument, SourceFormat
from app.domain.relay_import.review_state import ReviewDecisionError, ReviewDecisions, apply_review
from app.services.relay_extraction_review import ExtractionReview, build_extraction_review
from app.services.relay_interpretation_summary import engine_adaptation

__all__ = ["InvalidReviewError", "validate_review"]

#: The review state needs no source lines (the browser already holds them), so
#: the raw document is empty: item sources come back empty and are not used.
_NO_DOCUMENT = RawRelayDocument(SourceFormat.PDF)


class InvalidReviewError(ValueError):
    """The validation context or a decision is not acceptable. Safe to show."""


def validate_review(context: dict, decisions: ReviewDecisions) -> ExtractionReview:
    try:
        original = decode_model(context)
        effective = apply_review(original, decisions)
    except (SnapshotError, ReviewDecisionError) as exc:
        raise InvalidReviewError(str(exc)) from exc
    return build_extraction_review(effective, _NO_DOCUMENT, engine_adaptation(effective), not_interpreted=0)
