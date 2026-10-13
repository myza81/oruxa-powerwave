"""Loading, selecting and locking parameter catalogs.

The catalogs live as external JSON files under ``backend/app/data/parameter_catalog/``::

    canonical/distance_protection.json     the canonical registry (the application's own vocabulary)
    <manufacturer>/<family>.json           OEM catalogs (one file = one catalog version)

`load_store` validates every file; a file that does not validate is **rejected with its issues**
(never partially used, never silently skipped: the rejection list is part of the result and is
logged). Lifecycle is ``draft -> validated -> tested -> active``; only an ``active`` catalog is
ever used to interpret a document in production, so adding or editing a catalog can be staged
safely. Validated / tested / active catalogs are *locked*: their semantic digest is recorded in
``catalog.lock.json`` and a change to the meaning of a locked version without a new version number
is reported (`check_lock`), so prior interpretations are never silently re-defined.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogIssue, CatalogValidationError, IssueCode
from app.domain.parameter_catalog.registry import CanonicalRegistry, load_registry

log = logging.getLogger(__name__)

CATALOG_ROOT = Path(__file__).resolve().parents[2] / "data" / "parameter_catalog"
REGISTRY_FILE = Path("canonical") / "distance_protection.json"
LOCK_FILE = "catalog.lock.json"
#: Lifecycle states whose meaning is locked (a draft may still change freely).
LOCKED_LIFECYCLES = ("validated", "tested", "active")


@dataclass(frozen=True)
class RejectedCatalog:
    path: str
    issues: tuple[CatalogIssue, ...]

    def __str__(self) -> str:
        return f"{self.path}: " + "; ".join(str(i) for i in self.issues)


@dataclass(frozen=True)
class CatalogStore:
    registry: CanonicalRegistry
    catalogs: tuple[Catalog, ...]
    rejected: tuple[RejectedCatalog, ...] = ()
    #: ``catalog_id@version`` -> semantic digest of the catalog as loaded.
    digests: dict[str, str] = field(default_factory=dict)

    def get(self, catalog_id: str, version: str | None = None) -> Catalog | None:
        matches = [c for c in self.catalogs if c.catalog_id == catalog_id and (version is None or c.version == version)]
        return max(matches, key=lambda c: _semver(c.version), default=None)

    def active(self) -> tuple[Catalog, ...]:
        return tuple(c for c in self.catalogs if c.lifecycle == "active")

    def select(self, manufacturer: str, family: str, model: str, version: str | None = None,
               lifecycles: tuple[str, ...] = ("active",)) -> Catalog | None:
        """The catalog that applies to a relay: manufacturer / family / model equal (case-insensitive),
        the firmware ``version`` (when given) matching one of the catalog's version patterns, and a
        lifecycle in ``lifecycles``. The highest catalog version wins; only ``active`` is used by
        default, so a draft or merely validated catalog can never interpret a real import."""
        def norm(text: str) -> str:
            return " ".join(text.split()).casefold()

        fits = [
            c for c in self.catalogs
            if c.lifecycle in lifecycles
            and norm(c.applicability.manufacturer) == norm(manufacturer)
            and norm(c.applicability.family) == norm(family)
            and norm(c.applicability.model) == norm(model)
            and (version is None or any(fnmatch.fnmatchcase(version, p) for p in c.applicability.versions))
        ]
        return max(fits, key=lambda c: _semver(c.version), default=None)


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def semantics_digest(data: dict[str, Any]) -> str:
    """Digest of everything that defines a catalog's *meaning* (not its lifecycle or description)."""
    keys = ("applicability", "profile_id", "identification", "zones", "distance_scope", "mappings", "interpretation_notes")
    canonical = json.dumps({k: data.get(k) for k in keys}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_store(root: Path = CATALOG_ROOT) -> CatalogStore:
    """Load and validate the canonical registry (a failure here is fatal) and every OEM catalog
    under ``root`` (a failing file is rejected and reported)."""
    registry = load_registry(root / REGISTRY_FILE)
    catalogs: list[Catalog] = []
    rejected: list[RejectedCatalog] = []
    digests: dict[str, str] = {}
    seen: dict[str, str] = {}
    active_ids: dict[str, str] = {}
    canonical_dir = root / REGISTRY_FILE.parent
    for path in sorted(root.rglob("*.json")):
        if path.parent == canonical_dir or path.name == LOCK_FILE:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            catalog = parse_catalog(data, registry, source=rel, source_path=rel)
            problems: list[CatalogIssue] = []
            if catalog.key in seen:
                problems.append(CatalogIssue("catalog_id", IssueCode.DUPLICATE, f"{catalog.key} is already defined in {seen[catalog.key]}"))
            if catalog.lifecycle == "active" and catalog.catalog_id in active_ids:
                problems.append(CatalogIssue(
                    "lifecycle", IssueCode.CONFLICT,
                    f"{catalog.catalog_id} already has an active version ({active_ids[catalog.catalog_id]}); only one may be active",
                ))
            if problems:
                raise CatalogValidationError(rel, problems)
        except (OSError, json.JSONDecodeError) as exc:
            rejected.append(RejectedCatalog(rel, (CatalogIssue("$", IssueCode.MALFORMED, f"cannot read catalog: {exc}"),)))
            continue
        except CatalogValidationError as exc:
            rejected.append(RejectedCatalog(rel, exc.issues))
            continue
        seen[catalog.key] = rel
        if catalog.lifecycle == "active":
            active_ids[catalog.catalog_id] = rel
        digests[catalog.key] = semantics_digest(data)
        catalogs.append(catalog)
    for item in rejected:
        log.warning("parameter catalog rejected: %s", item)
    return CatalogStore(registry, tuple(catalogs), tuple(rejected), digests)


@lru_cache(maxsize=1)
def default_store() -> CatalogStore:
    """The shipped catalogs, loaded and validated once. Read-only: do not mutate."""
    return load_store(CATALOG_ROOT)


@lru_cache(maxsize=1)
def canonical_registry() -> CanonicalRegistry:
    """The shipped canonical registry (loaded once). The review labels its items from it."""
    return load_registry(CATALOG_ROOT / REGISTRY_FILE)


def load_lock(root: Path = CATALOG_ROOT) -> dict[str, str]:
    path = root / LOCK_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def check_lock(store: CatalogStore, lock: dict[str, str]) -> list[str]:
    """Problems with the lock: a locked catalog whose meaning changed without a new version, or one
    that is locked in lifecycle but missing from the lock. Empty when consistent."""
    problems = []
    for catalog in store.catalogs:
        if catalog.lifecycle not in LOCKED_LIFECYCLES:
            continue
        locked = lock.get(catalog.key)
        digest = store.digests[catalog.key]
        if locked is None:
            problems.append(f"{catalog.key} ({catalog.lifecycle}) is not in {LOCK_FILE}; record its digest {digest}")
        elif locked != digest:
            problems.append(
                f"{catalog.key} changed its meaning without a new version (digest {digest} != locked {locked}); "
                "bump the version instead of editing a locked one"
            )
    return problems


def write_lock(store: CatalogStore, root: Path = CATALOG_ROOT) -> None:
    """Record the digest of every locked catalog version (existing entries are never rewritten)."""
    lock = load_lock(root)
    for catalog in store.catalogs:
        if catalog.lifecycle in LOCKED_LIFECYCLES:
            lock.setdefault(catalog.key, store.digests[catalog.key])
    (root / LOCK_FILE).write_text(json.dumps(dict(sorted(lock.items())), indent=2) + "\n", encoding="utf-8")

