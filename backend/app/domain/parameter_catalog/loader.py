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


def applicabilities_overlap(a: Catalog, b: Catalog) -> bool:
    """True when two catalogs claim the same relay (manufacturer / family / model, case- and
    spacing-insensitive) for at least one common firmware version."""
    def norm(text: str) -> str:
        return " ".join(text.split()).casefold()

    pa, pb = a.applicability, b.applicability
    if (norm(pa.manufacturer), norm(pa.family), norm(pa.model)) != (norm(pb.manufacturer), norm(pb.family), norm(pb.model)):
        return False
    return any(fnmatch.fnmatchcase(x, y) or fnmatch.fnmatchcase(y, x) for x in pa.versions for y in pb.versions)


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
    active_catalogs: list[tuple[Catalog, str]] = []
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
            if catalog.lifecycle == "active":
                for other, other_rel in active_catalogs:
                    if other.catalog_id != catalog.catalog_id and applicabilities_overlap(catalog, other):
                        problems.append(CatalogIssue(
                            "applicability", IssueCode.CONFLICT,
                            f"{other.key} ({other_rel}) is already active for the same relay and firmware; "
                            "two active catalogs may not interpret one relay",
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
            active_catalogs.append((catalog, rel))
        digests[catalog.key] = semantics_digest(data)
        catalogs.append(catalog)
    for item in rejected:
        log.warning("parameter catalog rejected: %s", item)
    return CatalogStore(registry, tuple(catalogs), tuple(rejected), digests)


@lru_cache(maxsize=1)
def default_store() -> CatalogStore:
    """The shipped catalogs, loaded and validated once. Read-only: do not mutate."""
    return load_store(CATALOG_ROOT)


@dataclass(frozen=True)
class FileValidation:
    """The result of validating one catalog file against a catalog tree (``validate-catalog``)."""

    path: str
    catalog: Catalog | None
    issues: tuple[CatalogIssue, ...]
    #: ``mappings[i]`` -> that mapping's own id, so an issue can name the entry it is about.
    mapping_ids: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.catalog is not None and not self.issues

    def locate(self, issue: CatalogIssue) -> str:
        """``mappings[3].transform[0]`` -> ``mappings[3] (vendor.x_reach).transform[0]``."""
        head = issue.path.split(".", 1)[0].split("[", 1)
        key = head[0] + "[" + head[1] if len(head) == 2 else issue.path
        mid = self.mapping_ids.get(key)
        return issue.path.replace(key, f"{key} ({mid})", 1) if mid else issue.path


def validate_catalog_file(path: Path, root: Path = CATALOG_ROOT) -> FileValidation:
    """Validate one catalog file as the application would load it, **without activating or changing
    anything**: JSON and schema, canonical targets, transformations, units, enums, duplicate / conflicting
    mappings, relay / model / firmware applicability against the catalogs already in ``root`` (a second
    active catalog for the same relay, a duplicate version) and the semantic lock (a locked version whose
    meaning changed)."""
    registry = load_registry(root / REGISTRY_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return FileValidation(str(path), None, (CatalogIssue("$", IssueCode.MALFORMED, f"cannot read the file: {exc}"),))
    except json.JSONDecodeError as exc:
        return FileValidation(str(path), None, (CatalogIssue(f"line {exc.lineno}, column {exc.colno}", IssueCode.MALFORMED, f"not valid JSON: {exc.msg}"),))
    mappings = data.get("mappings") if isinstance(data, dict) else None
    mapping_ids = {
        f"mappings[{i}]": m["id"] for i, m in enumerate(mappings or []) if isinstance(m, dict) and isinstance(m.get("id"), str)
    }
    try:
        catalog = parse_catalog(data, registry, source=path.name, source_path=path.name)
    except CatalogValidationError as exc:
        return FileValidation(str(path), None, exc.issues, mapping_ids)
    issues: list[CatalogIssue] = []
    here = path.resolve()
    others = [
        (c, p) for p in sorted(root.rglob("*.json"))
        if p.resolve() != here and p.parent != root / REGISTRY_FILE.parent and p.name != LOCK_FILE
        for c in [_try_parse(p, registry)] if c is not None
    ]
    for other, other_path in others:
        if other.key == catalog.key:
            issues.append(CatalogIssue("catalog_id", IssueCode.DUPLICATE, f"{catalog.key} is already defined in {other_path.name}"))
        if catalog.lifecycle == "active" and other.lifecycle == "active" and other.catalog_id != catalog.catalog_id                 and applicabilities_overlap(catalog, other):
            issues.append(CatalogIssue(
                "applicability", IssueCode.CONFLICT,
                f"{other.key} ({other_path.name}) is already active for the same relay and firmware",
            ))
        if catalog.lifecycle == "active" and other.lifecycle == "active" and other.catalog_id == catalog.catalog_id:
            issues.append(CatalogIssue("lifecycle", IssueCode.CONFLICT, f"{other.key} ({other_path.name}) is already the active version of {catalog.catalog_id}"))
    locked = load_lock(root).get(catalog.key)
    if catalog.lifecycle in LOCKED_LIFECYCLES and locked is not None and locked != semantics_digest(data):
        issues.append(CatalogIssue("version", IssueCode.CONFLICT, f"{catalog.key} is locked and its meaning changed; bump the version"))
    return FileValidation(str(path), catalog if not issues else None, tuple(issues), mapping_ids)


def _try_parse(path: Path, registry: CanonicalRegistry) -> Catalog | None:
    try:
        return parse_catalog(json.loads(path.read_text(encoding="utf-8")), registry, source=path.name, source_path=path.name)
    except (OSError, json.JSONDecodeError, CatalogValidationError):
        return None


class CatalogLoadError(RuntimeError):
    """The shipped catalogs failed validation: the application must not start on partly valid data."""


def verify_shipped_catalogs() -> CatalogStore:
    """The shipped store, or `CatalogLoadError` naming every rejected catalog and issue. Called at
    application start-up: an invalid catalog is never partly activated, and never silently skipped
    -- the service refuses to start and says exactly what to fix (``validate-catalog <file>``)."""
    store = default_store()
    problems = check_lock(store, load_lock())
    if store.rejected or problems:
        lines = [f"  - {r}" for r in store.rejected] + [f"  - {p}" for p in problems]
        raise CatalogLoadError(
            "parameter catalogs failed validation; refusing to start with a partly valid catalog set:\n" + "\n".join(lines)
        )
    return store


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

