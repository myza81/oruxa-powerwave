"""Relay interpretation (Slice 6): run the matching profile and reduce the
result to a summary the upload response can carry.

Routing is by the identification verdict only: a document is interpreted when
the identifier says ``identified`` AND a registered profile has exactly that
profile id. Every other relay -- identified or not -- is ``not_supported`` and
keeps today's identification-only behaviour. The canonical model is built and
dropped inside the request; only counts and fixed phrases leave this module
(no setting names, values or document text), and nothing is applied to the
Distance Protection form.

The existing engine adapter is run over the model so the summary can say
whether the settings could later be drawn, and why not; it is a read-only
check and does not change the model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import StrEnum

from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel, SettingBasis
from app.domain.relay_import.engine_adapter import EngineAdaptation, adapt_to_engine
from app.domain.relay_import.defeated_zone import infer_defeated_zones
from app.domain.relay_import.identification import RelayIdentification
from app.domain.relay_import.profile import RelayProfileRegistry
from app.domain.relay_import.provenance import MappingStatus
from app.domain.relay_import.raw_document import RawRelayDocument
from app.services.relay_extraction_review import ExtractionReview, build_extraction_review
from app.services.relay_review_token import relay_knowledge

logger = logging.getLogger(__name__)


class InterpretationStatus(StrEnum):
    #: A profile ran and found at least one distance zone.
    INTERPRETED = "interpreted"
    #: A profile ran but found no distance zone.
    INCOMPLETE = "incomplete"
    #: No interpretation profile exists for this relay (or it was not identified).
    NOT_SUPPORTED = "not_supported"
    #: The profile raised; identification and extraction results still stand.
    FAILED = "failed"


@dataclass(frozen=True)
class RelayInterpretationSummary:
    status: InterpretationStatus
    profile_id: str | None = None
    profile_version: str | None = None
    #: Canonical values the profile mapped deterministically.
    mapped_setting_count: int = 0
    #: Canonical values that rest on profile knowledge the sheet does not state
    #: (confirmation recommended).
    inferred_setting_count: int = 0
    #: Values the profile looked for or saw but could not resolve, plus
    #: settings it read but declined to interpret as one value.
    unresolved_setting_count: int = 0
    #: Distance-related settings retained raw because this profile version
    #: does not interpret them (scheme logic, power swing, ...).
    not_interpreted_setting_count: int = 0
    zone_count: int = 0
    warnings: tuple[str, ...] = ()
    #: Slice 7. Read-only review view; present only for an ``interpreted`` relay.
    review: ExtractionReview | None = None
    #: DEC-195. The catalog behind the interpretation and its coverage of the sheet (counts only).
    catalog_id: str | None = None
    catalog_version: str | None = None
    catalog_coverage: dict | None = None
    #: DEC-198 Amendment 5. The reviewed interpretation and the relay knowledge it was made with, kept
    #: only so the upload can seal them into the signed validation token; never serialised as such.
    model: CanonicalDistanceProtectionModel | None = field(default=None, repr=False, compare=False)
    knowledge: dict | None = field(default=None, repr=False, compare=False)


def count_model(model: CanonicalDistanceProtectionModel) -> tuple[int, int, int, int]:
    """(mapped, inferred, unresolved, not_interpreted) -- see the summary."""
    mapped = inferred = 0
    touched = 0
    for _, sourced in model.iter_sourced():
        status = sourced.provenance.status
        if status is MappingStatus.MAPPED:
            mapped += 1
        elif status is MappingStatus.INFERRED:
            # An Oruxa assumption (absent or defeated zone) is not an interpretation the
            # user is asked to confirm, so it is not counted with them.
            if sourced.needs_confirmation:
                inferred += 1
        elif sourced.provenance.sources or sourced.provenance.raw_value is not None or sourced.provenance.notes:
            # Looked for or seen but not resolved. An untouched placeholder
            # (a field this relay simply does not have) is not counted.
            touched += 1
    declined = {u.setting_id for z in model.zones for u in z.unresolved_settings if not u.out_of_scope}
    not_interpreted = sum(1 for u in model.unmapped_settings if not u.out_of_scope)
    return mapped, inferred, touched + len(declined), not_interpreted


def engine_adaptation(model: CanonicalDistanceProtectionModel) -> EngineAdaptation:
    """The existing engine adapter run read-only against the model's own basis. Review
    readiness and Apply Settings both read this one result, so they can never disagree
    (Slice 10: there is no longer a separate form-slot check -- the zones the analysis
    receives are exactly the zones the adapter accepted, whatever their number)."""
    basis = model.transformers.setting_basis
    engine_basis = basis.value.value if basis.is_resolved and basis.value is not SettingBasis.UNKNOWN else "secondary"
    return adapt_to_engine(model, engine_basis=engine_basis)


def _engine_warnings(adaptation: EngineAdaptation) -> tuple[str, ...]:
    """Why the existing engine could not draw this model today (fixed adapter
    wording, zone ids only)."""
    if adaptation.supported:
        return ()
    return tuple(
        f"Engine: {reason.zone_id + ': ' if reason.zone_id else ''}{reason.message}" for reason in adaptation.reasons
    )


def summarize_interpretation(
    registry: RelayProfileRegistry, document: RawRelayDocument, identification: RelayIdentification
) -> RelayInterpretationSummary:
    profile = registry.profile_for(identification)
    if profile is None:
        return RelayInterpretationSummary(InterpretationStatus.NOT_SUPPORTED)
    coverage = None
    try:
        if hasattr(profile, "interpret_with_coverage"):          # a catalog-first profile
            raw_model, coverage = profile.interpret_with_coverage(document)
        else:
            raw_model = profile.interpret(document)
        model = infer_defeated_zones(raw_model)
        mapped, inferred, unresolved, not_interpreted = count_model(model)
        adaptation = engine_adaptation(model)
        warnings = (*model.interpretation_notes, *_engine_warnings(adaptation))
    except Exception as exc:  # a profile bug must never fail the upload
        logger.warning("Relay interpretation failed (%s)", type(exc).__name__)  # class only: never content
        return RelayInterpretationSummary(
            InterpretationStatus.FAILED,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            warnings=("Settings could not be interpreted. Manual entry is still available.",),
        )
    review = None
    if model.zones:
        try:
            review = build_extraction_review(model, document, adaptation, not_interpreted=not_interpreted)
            # Slice 8 / DEC-198 Amendment 5: the original interpretation travels with the review --
            # sealed in a signed validation token the upload issues -- so the backend can re-validate the
            # user's decisions without keeping state.
            review = replace(
                review,
                catalog_id=coverage.catalog_id if coverage else None,
                catalog_version=coverage.catalog_version if coverage else None,
                catalog_coverage=coverage.as_dict() if coverage else None,
            )
        except Exception as exc:  # the review is optional: never fail the upload for it
            logger.warning("Extraction review could not be built (%s)", type(exc).__name__)
    return RelayInterpretationSummary(
        status=InterpretationStatus.INTERPRETED if model.zones else InterpretationStatus.INCOMPLETE,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        mapped_setting_count=mapped,
        inferred_setting_count=inferred,
        unresolved_setting_count=unresolved,
        not_interpreted_setting_count=not_interpreted,
        zone_count=len(model.zones),
        warnings=warnings,
        review=review,
        catalog_id=coverage.catalog_id if coverage else None,
        catalog_version=coverage.catalog_version if coverage else None,
        catalog_coverage=coverage.as_dict() if coverage else None,
        model=model if review is not None else None,
        knowledge=relay_knowledge(profile) if review is not None else None,
    )
