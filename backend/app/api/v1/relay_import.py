"""Relay Import Slice 3: ephemeral relay-setting file upload.

Accepts one file, validates and minimally inspects it, returns basic
metadata plus generic-extraction counts, and retains nothing -- no database, no StorageBackend, no
registry, no persistent directory. It deliberately takes no workspace id:
nothing about the upload is workspace state. Generic text extraction
(Slice 4), relay identification (Slice 5) and, for a relay with a profile,
interpretation (Slice 6) run request-scoped; only counts, the identification
verdict and an interpretation summary are returned. Nothing is applied to the
Distance Protection form.

Slice 8 adds ``POST /review/validate``: a *stateless* re-validation of the user's
review decisions. The request carries the original interpretation (the review's
validation context) and the decisions; the response is the reviewed state. No
server session, store or cache exists, and nothing is applied to the form.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import Settings
from app.domain.relay_import.review_state import ReviewDecisions
from app.schemas.relay_import import (
    ApplySettingsOut,
    ApplyZoneOut,
    ExtractionReviewOut,
    RelayImportUploadOut,
    ReviewItemStateOut,
    ReviewStateOut,
    ReviewValidationIn,
)
from app.schemas.source import ErrorOut
from app.services.errors import ImportServiceError
from app.services.relay_extraction_review import ExtractionReview
from app.services.relay_import_upload_service import inspect_relay_setting_upload
from app.domain.relay_import.apply_settings import ApplyRejectedError
from app.services.relay_apply_settings import ApplyNotReadyError, apply_reviewed_settings
from app.services.relay_review_validation import InvalidReviewError, validate_review

logger = logging.getLogger(__name__)

RELAY_IMPORT_UPLOAD_PATH = "/api/v1/relay-import/upload"
RELAY_IMPORT_REVIEW_VALIDATE_PATH = "/api/v1/relay-import/review/validate"
RELAY_IMPORT_REVIEW_APPLY_PATH = "/api/v1/relay-import/review/apply"

router = APIRouter(prefix="/api/v1/relay-import", tags=["relay-import"])

_STATUS_BY_ERROR_CODE: dict[str, int] = {
    "unsupported_file_type": status.HTTP_400_BAD_REQUEST,
    "invalid_file": status.HTTP_400_BAD_REQUEST,
    "empty_file": status.HTTP_400_BAD_REQUEST,
    "upload_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/upload", response_model=RelayImportUploadOut)
async def upload_relay_setting_file(
    file: UploadFile = File(..., description="Relay setting file (PDF)"),
    settings: Settings = Depends(get_settings_dep),
) -> RelayImportUploadOut:
    try:
        result = await inspect_relay_setting_upload(
            file, max_bytes=settings.max_relay_import_upload_size_bytes
        )
    except ImportServiceError as exc:
        # Code only: never the filename or any content.
        logger.info("Relay-setting upload rejected (%s)", exc.code)
        raise HTTPException(
            status_code=_STATUS_BY_ERROR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=ErrorOut(code=exc.code, message=exc.message).model_dump(),
        ) from exc
    except Exception:
        logger.exception("Unexpected error inspecting a relay-setting upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="The file could not be processed.").model_dump(),
        )
    ident = result.extraction.identification
    interp = result.extraction.interpretation
    return RelayImportUploadOut(
        filename=result.filename,
        source_format=result.source_format.value,
        size_bytes=result.size_bytes,
        status="accepted",
        extraction_status=result.extraction.status,
        page_count=result.extraction.page_count,
        pages_with_text=result.extraction.pages_with_text,
        raw_entry_count=result.extraction.raw_entry_count,
        section_count=result.extraction.section_count,
        extraction_warnings=list(result.extraction.warnings),
        identification_status=ident.status if ident else None,
        manufacturer=ident.manufacturer if ident else None,
        relay_family=ident.relay_family if ident else None,
        model=ident.model if ident else None,
        profile_id=ident.profile_id if ident else None,
        confidence=ident.confidence if ident else None,
        identification_warnings=list(ident.warnings) if ident else [],
        interpretation_status=interp.status.value if interp else None,
        profile_version=interp.profile_version if interp else None,
        mapped_setting_count=interp.mapped_setting_count if interp else 0,
        inferred_setting_count=interp.inferred_setting_count if interp else 0,
        unresolved_setting_count=interp.unresolved_setting_count if interp else 0,
        not_interpreted_setting_count=interp.not_interpreted_setting_count if interp else 0,
        zone_count=interp.zone_count if interp else 0,
        interpretation_warnings=list(interp.warnings) if interp else [],
        catalog_id=interp.catalog_id if interp else None,
        catalog_version=interp.catalog_version if interp else None,
        catalog_coverage=interp.catalog_coverage if interp else None,
        review=ExtractionReviewOut(**asdict(interp.review)) if interp and interp.review else None,
    )


def _review_state_out(review: ExtractionReview) -> ReviewStateOut:
    """The decision-dependent part of a review: one entry per canonical value."""
    full = ExtractionReviewOut(**asdict(review))
    items = [
        ReviewItemStateOut(
            item_id=item.item_id,
            status=item.status,
            review_status=item.review_status,
            value_text=item.value_text,
            blocking=item.blocking,
            left_unresolved=item.left_unresolved,
            user_value_text=item.user_value_text,
            category=item.category,
            engine_reason=item.engine_reason,
            suggestion=item.suggestion,
            resolution_origin=item.resolution_origin,
            not_required=item.not_required,
            not_required_reason=item.not_required_reason,
            approximation=item.approximation,
        )
        for group in full.groups
        for item in group.items
        if item.primary and item.item_id is not None
    ]
    return ReviewStateOut(
        **full.model_dump(include=set(ReviewStateOut.model_fields) - {"items"}),
        items=items,
    )


def _decisions(body: ReviewValidationIn) -> ReviewDecisions:
    manual = {entry.item_id: entry.value for entry in body.manual}
    if len(manual) != len(body.manual):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_review", message="An item cannot be resolved twice.").model_dump(),
        )
    return ReviewDecisions(
        confirmed=frozenset(body.confirmed),
        manual=manual,
        left_unresolved=frozenset(body.left_unresolved),
        suggested=frozenset(body.suggested),
    )


@router.post("/review/validate", response_model=ReviewStateOut)
def validate_relay_review(body: ReviewValidationIn) -> ReviewStateOut:
    decisions = _decisions(body)
    try:
        review = validate_review(body.validation_context, decisions)
    except InvalidReviewError as exc:
        # The message is a fixed domain phrase: never the context or any content.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_review", message=str(exc)).model_dump(),
        ) from exc
    except Exception:
        logger.exception("Unexpected error validating a relay review")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="The review could not be validated.").model_dump(),
        )
    return _review_state_out(review)


def _apply_zone_out(zone) -> ApplyZoneOut:
    """The wire name of the zone's stable canonical identity is ``id``."""
    fields = asdict(zone)
    fields["id"] = fields.pop("zone_id")
    return ApplyZoneOut(**fields)


@router.post("/review/apply", response_model=ApplySettingsOut)
def apply_relay_review(body: ReviewValidationIn) -> ApplySettingsOut:
    """Slice 9 / 10. Stateless and backend-authoritative: the effective reviewed model is
    re-derived from the original interpretation and the decisions, readiness and the
    engine adapter are re-run, and the complete zone collection (any number of zones) is
    returned. Nothing is stored; the browser populates its own Distance Protection analysis
    with the result."""
    decisions = _decisions(body)
    try:
        plan = apply_reviewed_settings(body.validation_context, decisions)
    except InvalidReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorOut(code="invalid_review", message=str(exc)).model_dump(),
        ) from exc
    except ApplyNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ErrorOut(code="apply_not_ready", message=str(exc)).model_dump(),
        ) from exc
    except ApplyRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ErrorOut(code="apply_unsupported", message=str(exc)).model_dump(),
        ) from exc
    except Exception:
        logger.exception("Unexpected error applying relay settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorOut(code="internal_error", message="The settings could not be applied.").model_dump(),
        )
    return ApplySettingsOut(
        characteristic=plan.characteristic,
        impedance_basis=plan.impedance_basis,
        zones=[_apply_zone_out(zone) for zone in plan.zones],
        approximations=[asdict(a) for a in plan.approximations],
    )
