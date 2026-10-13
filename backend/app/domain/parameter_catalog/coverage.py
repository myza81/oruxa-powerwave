"""How much of a relay's setting sheet a catalog accounts for.

Raw settings and review rows are different things: a sheet of 350 extracted settings may yield a
review of a few dozen rows, because many settings feed one canonical value and most are not
distance-protection settings at all. Coverage therefore counts **raw settings** (each in exactly one
bucket, so the buckets add up to ``extracted_settings``) and, separately, **canonical values** (one
per catalog target and zone).

    extracted_settings
      = catalog_mapped + catalog_unsupported + catalog_unresolved      (the catalog recognised them)
      + extension_interpreted                                          (read by a profile extension)
      + not_interpreted + outside_distance                             (retained, never used)

A setting is in the strongest bucket that applies: mapped > unresolved > unsupported.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.interpreter import CatalogRun, Outcome
from app.domain.relay_import.canonical_distance import CanonicalDistanceProtectionModel
from app.domain.relay_import.provenance import MappingStatus, UnresolvedCause
from app.domain.relay_import.raw_document import RawRelayDocument


@dataclass(frozen=True)
class CatalogCoverage:
    catalog_id: str
    catalog_version: str
    #: Raw settings the extractor produced (section headings included) -- not review rows.
    extracted_settings: int
    #: Cited by a canonical value the catalog resolved.
    catalog_mapped_settings: int
    #: Recognised by the catalog, which states the model cannot represent them (a capability gap).
    catalog_unsupported_settings: int
    #: Recognised by the catalog, but every value they feed is conflicting, unreadable or missing.
    catalog_unresolved_settings: int
    #: Not the catalog's: read by the profile extension that still owns this relay's remaining semantics.
    extension_interpreted_settings: int
    #: Distance-related, retained raw and marked "Not interpreted"; never enters the engine.
    not_interpreted_settings: int
    #: Not a distance-protection setting; retained raw, not interpreted.
    outside_distance_settings: int
    #: Canonical values (a catalog target in a zone), by outcome.
    canonical_values_mapped: int
    canonical_values_assumed: int
    canonical_values_unsupported: int
    canonical_values_conflicting: int
    canonical_values_unreadable: int
    canonical_values_missing: int

    @property
    def catalog_recognised_settings(self) -> int:
        return self.catalog_mapped_settings + self.catalog_unsupported_settings + self.catalog_unresolved_settings

    @property
    def unmapped_settings(self) -> int:
        return self.not_interpreted_settings + self.outside_distance_settings

    @property
    def canonical_values_total(self) -> int:
        return (self.canonical_values_mapped + self.canonical_values_assumed + self.canonical_values_unsupported
                + self.canonical_values_conflicting + self.canonical_values_unreadable + self.canonical_values_missing)

    def as_dict(self) -> dict[str, int | str]:
        return {
            **asdict(self),
            "catalog_recognised_settings": self.catalog_recognised_settings,
            "unmapped_settings": self.unmapped_settings,
            "canonical_values_total": self.canonical_values_total,
        }


def outcome_state(outcome: Outcome) -> str:
    """``mapped`` / ``assumption`` / ``unsupported`` / ``conflict`` / ``unreadable`` / ``missing``."""
    result = outcome.result
    if result.is_resolved:
        prov = getattr(result, "provenance", None)
        return "assumption" if prov is not None and prov.status is MappingStatus.INFERRED else "mapped"
    cause = result.provenance.cause
    return {
        UnresolvedCause.UNSUPPORTED: "unsupported",
        UnresolvedCause.CONFLICT: "conflict",
        UnresolvedCause.UNREADABLE: "unreadable",
    }.get(cause, "missing")


def compute_coverage(
    catalog: Catalog, document: RawRelayDocument, run: CatalogRun, final: CanonicalDistanceProtectionModel
) -> CatalogCoverage:
    """Coverage of ``document`` by ``catalog``; ``final`` is the model actually produced (the catalog's own
    model in a dry run, the catalog-first merge in production) -- its ``unmapped_settings`` are the
    settings that were retained as "Not interpreted"."""
    states = {"mapped": 0, "assumption": 0, "unsupported": 0, "conflict": 0, "unreadable": 0, "missing": 0}
    mapped_ids: set[str] = set()
    unresolved_ids: set[str] = set()
    unsupported_ids: set[str] = set()
    for outcome in run.outcomes.values():
        state = outcome_state(outcome)
        states[state] += 1
        prov = getattr(outcome.result, "provenance", None)
        ids = {ref.setting_id for ref in prov.sources} if prov is not None else set()
        if state in ("mapped", "assumption"):
            mapped_ids |= ids
        elif state == "unsupported":
            unsupported_ids |= ids
        else:
            unresolved_ids |= ids
    unresolved_ids -= mapped_ids
    unsupported_ids -= mapped_ids | unresolved_ids
    # the scheme / template field the relay identity is cited to is consumed by the catalog without being a target
    mapped_ids |= run.consumed - mapped_ids - unresolved_ids - unsupported_ids
    recognised = mapped_ids | unresolved_ids | unsupported_ids
    unmapped = {u.setting_id: u for u in final.unmapped_settings}
    all_ids = {s.setting_id for s in document.settings}
    rest = all_ids - recognised
    not_interpreted = {i for i in rest if i in unmapped and not unmapped[i].out_of_scope}
    outside = {i for i in rest if i in unmapped and unmapped[i].out_of_scope}
    extension = rest - not_interpreted - outside
    return CatalogCoverage(
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.version,
        extracted_settings=len(all_ids),
        catalog_mapped_settings=len(mapped_ids & all_ids),
        catalog_unsupported_settings=len(unsupported_ids & all_ids),
        catalog_unresolved_settings=len(unresolved_ids & all_ids),
        extension_interpreted_settings=len(extension),
        not_interpreted_settings=len(not_interpreted),
        outside_distance_settings=len(outside),
        canonical_values_mapped=states["mapped"],
        canonical_values_assumed=states["assumption"],
        canonical_values_unsupported=states["unsupported"],
        canonical_values_conflicting=states["conflict"],
        canonical_values_unreadable=states["unreadable"],
        canonical_values_missing=states["missing"],
    )
