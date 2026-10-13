"""A relay interpretation profile defined entirely by a parameter catalog.

``RawRelayDocument -> CatalogProfile -> CanonicalDistanceProtectionModel``

`CatalogProfile` satisfies the generic `RelayProfile` protocol, so a relay described only by an
*active* catalog goes through the same identification, review, readiness, Apply and engine
pipeline as the hand-written profiles -- with no Python written for it. The profile id is the
catalog's ``profile_id``; the interpretation's ``profile_version`` is ``<catalog_id>-v<version>``,
so every import records which catalog version produced it.
"""

from __future__ import annotations

import logging
import re

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CatalogStore
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.identification import ParameterSignature, RelayIdentificationDescriptor
from app.domain.relay_import.profile import MatchLevel, ProfileMatch
from app.domain.relay_import.raw_document import RawRelayDocument

log = logging.getLogger(__name__)


class CatalogProfile:
    """``RelayProfile`` implementation backed by one catalog."""

    validation_status = "Catalog-defined / Awaiting Validation"

    def __init__(self, catalog: Catalog, store: CatalogStore) -> None:
        self.catalog = catalog
        self.profile_id = catalog.profile_id
        self.version = catalog.profile_version
        self._interpreter = CatalogInterpreter(catalog, store.registry)
        #: False when the relay is already described by a standalone identification descriptor.
        self.use_catalog_identification = True

    @property
    def identification(self) -> RelayIdentificationDescriptor | None:
        """The catalog's identification block as the identifier's descriptor (``None`` without model
        patterns, or when a standalone descriptor already identifies this relay)."""
        ident, app = self.catalog.identification, self.catalog.applicability
        if not ident.model_patterns or not self.use_catalog_identification:
            return None
        return RelayIdentificationDescriptor(
            profile_id=self.catalog.profile_id,
            relay_family=app.family,
            manufacturer=app.manufacturer,
            model=app.model,
            model_patterns=ident.model_patterns,
            family_markers=ident.family_markers,
            parameter_signatures=tuple(
                ParameterSignature(
                    sig["name"], sig["pattern"], sig.get("target", "name"), int(sig.get("min_matches", 1)),
                    bool(sig.get("ignore_case", False)),
                )
                for sig in ident.parameter_signatures
            ),
        )

    def match(self, document: RawRelayDocument) -> ProfileMatch:
        """CONFIRMED only when the document's own scheme field names this relay."""
        ident = self.catalog.identification
        if not ident.scheme_model_pattern:
            return ProfileMatch(MatchLevel.NONE)
        scheme = re.compile(ident.scheme_pattern, re.IGNORECASE)
        for s in document.settings:
            for text in (s.raw_value, s.name):
                m = scheme.search(str(text)) if text else None
                if m and re.search(ident.scheme_model_pattern, m.group(1), re.IGNORECASE):
                    return ProfileMatch(MatchLevel.CONFIRMED, (f"scheme field names a {self.catalog.applicability.model}",))
        return ProfileMatch(MatchLevel.NONE)

    def interpret(self, document: RawRelayDocument) -> CanonicalDistanceProtectionModel:
        return self._interpreter.interpret(document)


def active_catalog_profiles(store: CatalogStore, taken_profile_ids: frozenset[str] = frozenset()) -> tuple[CatalogProfile, ...]:
    """A profile for every ``active`` catalog. A catalog whose profile id is already taken by another
    profile is skipped with a warning -- two definitions of one relay are never both used."""
    out = []
    for catalog in store.active():
        if catalog.profile_id in taken_profile_ids:
            log.warning("active catalog %s not used: profile id %r is already registered", catalog.key, catalog.profile_id)
            continue
        out.append(CatalogProfile(catalog, store))
    return tuple(out)
