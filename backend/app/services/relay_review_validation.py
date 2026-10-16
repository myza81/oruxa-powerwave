"""Review validation (Slice 8): re-evaluate a review from the user's decisions.

Stateless by design -- the platform keeps nothing between requests and import
data is ephemeral, so there is no session to look an interpretation up in. The
caller supplies the signed *validation token* the upload issued (with the import
identity it is bound to) together with its decisions. The token is verified
before anything in it is used (DEC-198 Amendment 5, `relay_review_token`), and
this returns the reviewed state:

    verified original interpretation  +  decisions
        -> effective reviewed model          (the original is never edited)
        -> engine adapter, re-run
        -> review state: statuses, counts, blocking issues, readiness

The browser never decides readiness: it only holds the decisions and the
interpretation and asks. Nothing is stored, logged or applied to the Distance
Protection form.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.engine_adapter import EngineAdaptation
from app.domain.relay_import.raw_document import RawRelayDocument, SourceFormat
from app.domain.relay_import.review_state import ReviewDecisionError, ReviewDecisions, apply_review
from app.services.relay_extraction_review import ExtractionReview, build_extraction_review
from app.services.relay_interpretation_summary import engine_adaptation
from app.services.relay_review_token import Knowledge, ReviewTokenSigner, current_relay_knowledge

__all__ = ["InvalidReviewError", "manual_entry_paths", "reviewed_state", "validate_review"]

#: The review state needs no source lines (the browser already holds them), so
#: the raw document is empty: item sources come back empty and are not used.
_NO_DOCUMENT = RawRelayDocument(SourceFormat.PDF)


class InvalidReviewError(ValueError):
    """The validation context or a decision is not acceptable. Safe to show."""


def reviewed_state(
    token: str, import_id: str, decisions: ReviewDecisions, *, signer: ReviewTokenSigner,
    knowledge_for: Callable[[str], Knowledge | None] | None = None,
) -> tuple[CanonicalDistanceProtectionModel, EngineAdaptation, ExtractionReview]:
    """Re-derive everything from the verified original interpretation and the decisions:
    the effective model, the engine adaptation (re-run) and the review state.
    Nothing the browser computed is trusted. Shared by validation and Apply.

    DEC-198 Amendment 5: the original interpretation comes only from a token that verifies
    (signature, schema, expiry, import identity, relay knowledge) -- `ReviewTokenError` otherwise,
    before any engineering validation. Amendment 4: manual resolution authority is generated
    here, not taken from the client -- a manual value is accepted only for a path that the
    server-generated review of that interpretation offers an entry for."""
    # the relay knowledge the service interprets with *now* (looked up at call time, never cached)
    original = signer.verify(token, import_id=import_id, knowledge_for=knowledge_for or current_relay_knowledge)
    try:
        offered = manual_entry_paths(original) if decisions.manual else frozenset()
        effective = apply_review(original, decisions, offered_manual=offered)
    except ReviewDecisionError as exc:
        raise InvalidReviewError(str(exc)) from exc
    adaptation = engine_adaptation(effective)
    review = build_extraction_review(effective, _NO_DOCUMENT, adaptation, not_interpreted=0)
    _refuse_confirming_engine_limits(review, decisions)
    return effective, adaptation, review


def manual_entry_paths(original: CanonicalDistanceProtectionModel) -> frozenset[str]:
    """The exact paths the server-generated review of ``original`` (no decisions) offers a typed
    value for. A path the review does not show -- or shows without an entry -- is not in it."""
    review = build_extraction_review(original, _NO_DOCUMENT, engine_adaptation(original), not_interpreted=0)
    return frozenset(
        item.item_id for group in review.groups for item in group.items
        if item.item_id is not None and item.resolution is not None
    )


def validate_review(
    token: str, import_id: str, decisions: ReviewDecisions, *, signer: ReviewTokenSigner,
    knowledge_for: Callable[[str], Knowledge | None] | None = None,
) -> ExtractionReview:
    return reviewed_state(token, import_id, decisions, signer=signer, knowledge_for=knowledge_for)[2]


def _refuse_confirming_engine_limits(review: ExtractionReview, decisions: ReviewDecisions) -> None:
    """Only an Assumption is confirmable. A value the current engine cannot use
    (Unsupported) or that disagrees with another (Conflict) is not an engineering
    assumption the user can accept, so a confirmation of one is refused rather than
    silently counted."""
    refused = [
        item.item_id
        for group in review.groups
        for item in group.items
        if item.item_id in decisions.confirmed and item.category in ("unsupported", "conflict")
    ]
    if refused:
        raise InvalidReviewError("Only an assumption can be confirmed; this value is a limit of the current engine.")
