"""Parameter catalogs: data-driven meaning for relay settings.

    RawRelayDocument -> (OEM catalog JSON) -> generic matcher / transformer -> canonical model

The canonical registry (the application's own vocabulary) and the OEM catalogs are external,
validated JSON files; this package loads and validates them and interprets documents with them.
The Distance Protection engine never reads a catalog: it consumes only the canonical model.
"""

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogIssue, CatalogValidationError, IssueCode
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CatalogStore, load_store
from app.domain.parameter_catalog.profile import CatalogProfile, active_catalog_profiles
from app.domain.parameter_catalog.registry import CanonicalRegistry, load_registry

__all__ = [
    "CanonicalRegistry", "Catalog", "CatalogInterpreter", "CatalogIssue", "CatalogProfile", "CatalogStore",
    "CatalogValidationError", "IssueCode", "active_catalog_profiles", "load_registry", "load_store", "parse_catalog",
]
