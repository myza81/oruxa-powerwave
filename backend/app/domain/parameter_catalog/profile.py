"""A relay interpretation profile defined by a parameter catalog (catalog-first).

``RawRelayDocument -> CatalogProfile -> CanonicalDistanceProtectionModel``

`CatalogProfile` satisfies the generic `RelayProfile` protocol, so a relay described by an *active*
catalog goes through the same identification, review, readiness, Apply and engine pipeline as every
other relay.

* **Catalog only** (no ``extension``): no Python is written for the relay. The profile id is the
  catalog's ``profile_id``; ``profile_version`` is ``<catalog_id>-v<version>``.
* **Catalog + extension** (``extension`` = an existing hand-written profile with the same
  ``profile_id``): the catalog is authoritative for every canonical target it maps and the extension
  supplies only the semantics the catalog schema cannot yet express (see `catalog_first`). The
  extension's id and version are kept; each catalog-mapped value carries its own catalog id / version.

Either way every value interpreted by a catalog records the catalog id and version that produced it.
"""

from __future__ import annotations

import re

from app.domain.parameter_catalog.catalog_first import overlay
from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.coverage import CatalogCoverage, compute_coverage
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CatalogStore
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.identification import ParameterSignature, RelayIdentificationDescriptor
from app.domain.relay_import.profile import MatchLevel, ProfileMatch, RelayProfile
from app.domain.relay_import.raw_document import RawRelayDocument


class CatalogProfile:
    """``RelayProfile`` implementation backed by one catalog."""

    validation_status = "Catalog-defined / Awaiting Validation"

    def __init__(self, catalog: Catalog, store: CatalogStore, extension: RelayProfile | None = None) -> None:
        if extension is not None and extension.profile_id != catalog.profile_id:
            raise ValueError(f"extension {extension.profile_id!r} cannot extend catalog profile {catalog.profile_id!r}")
        self.catalog = catalog
        self.extension = extension
        self.profile_id = catalog.profile_id
        self.version = extension.version if extension is not None else catalog.profile_version
        self._registry = store.registry
        self._interpreter = CatalogInterpreter(catalog, store.registry)
        #: False when the relay is already described by a standalone identification descriptor.
        self.use_catalog_identification = True

    @property
    def catalog_id(self) -> str:
        return self.catalog.catalog_id

    @property
    def catalog_version(self) -> str:
        return self.catalog.version

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
        if self.extension is not None:
            return self.extension.match(document)
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
        return self.interpret_with_coverage(document)[0]

    def interpret_with_coverage(self, document: RawRelayDocument) -> tuple[CanonicalDistanceProtectionModel, CatalogCoverage]:
        """The canonical model (catalog first, extension for the rest) and how much of the sheet the
        catalog accounts for."""
        run = self._interpreter.run(document)
        if self.extension is None:
            model = run.model
        else:
            model = overlay(self.extension.interpret(document), run, self._registry, document, self.version)
        return model, compute_coverage(self.catalog, document, run, model)


def active_catalog_profiles(
    store: CatalogStore, extensions: tuple[RelayProfile, ...] = ()
) -> tuple[CatalogProfile, ...]:
    """A profile for every ``active`` catalog. A catalog whose profile id matches an ``extension`` profile
    is catalog-first for that relay (the extension keeps only what the catalog does not map); any other
    active catalog stands alone. Two profiles never share an id."""
    by_id = {p.profile_id: p for p in extensions}
    return tuple(CatalogProfile(catalog, store, by_id.get(catalog.profile_id)) for catalog in store.active())
