"""Catalog dry-run: what a catalog would do with an extracted relay sheet, without changing anything.

    catalog + extracted relay  ->  recognised / mapped / transformed / unmapped / conflicting

For an administrator adding or editing a catalog. It is a pure function of the catalog, the registry and
the document: no application state is read or written, no profile runs, nothing is applied -- it shows the
catalog's own reading only (a relay that still has a profile extension is reported without it).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.parameter_catalog.catalog_model import Catalog
from app.domain.parameter_catalog.coverage import CatalogCoverage, compute_coverage, outcome_state
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.registry import CanonicalRegistry
from app.domain.relay_import.canonical_distance import ImpedanceValue
from app.domain.relay_import.raw_document import RawRelayDocument

STATES = ("mapped", "assumption", "unsupported", "conflict", "unreadable", "missing", "unverified", "not_exposed")


@dataclass(frozen=True)
class DryRunSource:
    setting_id: str
    code: str | None
    name: str | None
    raw_value: str | None
    page: int | None
    line: int | None


@dataclass(frozen=True)
class DryRunEntry:
    canonical_id: str
    #: The application's own label for the target (never the OEM name).
    label: str
    zone: str
    #: mapped | assumption | unsupported | conflict | unreadable | missing
    state: str
    value: str | None
    raw_value: str | None
    #: How the printed value became the canonical one (``None`` when it was used as printed).
    transformation: str | None
    mapping_id: str
    authority: str | None
    notes: tuple[str, ...]
    sources: tuple[DryRunSource, ...]

    @property
    def transformed(self) -> bool:
        return self.transformation is not None


@dataclass(frozen=True)
class DryRunUnmapped:
    setting_id: str
    code: str | None
    name: str | None
    raw_value: str | None
    page: int | None
    line: int | None
    #: ``distance`` (retained, "Not interpreted") or ``outside`` (not a distance-protection setting).
    scope: str
    reason: str


@dataclass(frozen=True)
class DryRunReport:
    catalog_id: str
    catalog_version: str
    lifecycle: str
    coverage: CatalogCoverage
    entries: tuple[DryRunEntry, ...]
    unmapped: tuple[DryRunUnmapped, ...]
    notes: tuple[str, ...]

    def of(self, *states: str) -> tuple[DryRunEntry, ...]:
        return tuple(e for e in self.entries if e.state in states)

    @property
    def transformed(self) -> tuple[DryRunEntry, ...]:
        return tuple(e for e in self.entries if e.transformed)

    @property
    def conflicting(self) -> tuple[DryRunEntry, ...]:
        return self.of("conflict")

    def counts(self) -> dict[str, int]:
        return {state: len(self.of(state)) for state in STATES} | {"transformed": len(self.transformed)}


def _value_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, ImpedanceValue):
        return f"{value.r_ohm:g} + j{value.x_ohm:g} Ω" if not value.is_polar else f"{value.magnitude_ohm:g} Ω ∠ {value.angle_deg:g}°"
    return str(value)


def dry_run(catalog: Catalog, registry: CanonicalRegistry, document: RawRelayDocument) -> DryRunReport:
    """Interpret ``document`` with ``catalog`` alone and report every target and every leftover."""
    run = CatalogInterpreter(catalog, registry).run(document)
    raw = {s.setting_id: s for s in document.settings}
    entries = []
    for (canonical, zone_id), outcome in sorted(run.outcomes.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        param = registry.get(canonical)
        result = outcome.result
        prov = getattr(result, "provenance", None)
        sources = tuple(
            DryRunSource(
                r.setting_id, r.parameter_id, r.parameter_name,
                None if (s := raw.get(r.setting_id)) is None or s.raw_value is None else str(s.raw_value),
                r.page, s.location.line if s else None,
            )
            for r in (prov.sources if prov else ())
        )
        entries.append(DryRunEntry(
            canonical_id=canonical,
            label=param.label if param else canonical,
            zone=zone_id,
            state=outcome_state(outcome),
            value=_value_text(result.value) if result.is_resolved else None,
            raw_value=None if prov is None or prov.raw_value is None else str(prov.raw_value),
            transformation=prov.transformation if prov else None,
            mapping_id=outcome.mapping.id,
            authority=prov.authority.value if prov and prov.authority else None,
            notes=prov.notes if prov else (),
            sources=sources,
        ))
    unmapped = tuple(
        DryRunUnmapped(
            u.setting_id, (s := raw.get(u.setting_id)) and s.parameter_id, u.name,
            None if u.raw_value is None else str(u.raw_value),
            s.location.page if s else None, s.location.line if s else None,
            "outside" if u.out_of_scope else "distance", u.reason,
        )
        for u in run.model.unmapped_settings
    )
    return DryRunReport(
        catalog.catalog_id, catalog.version, catalog.lifecycle,
        compute_coverage(catalog, document, run, run.model), tuple(entries), unmapped, run.model.interpretation_notes,
    )


def render_text(report: DryRunReport, *, show_unmapped: int = 15) -> str:
    """A human-readable report for the command line."""
    c = report.coverage
    lines = [
        f"Dry run: {report.catalog_id} {report.catalog_version} ({report.lifecycle}) -- nothing was changed",
        "",
        f"Extracted settings:        {c.extracted_settings}",
        f"Catalog recognised:        {c.catalog_recognised_settings}"
        f"  (mapped {c.catalog_mapped_settings}, known unsupported {c.catalog_unsupported_settings},"
        f" unresolved {c.catalog_unresolved_settings})",
        f"Unmapped (not interpreted): {c.unmapped_settings}"
        f"  (distance-related {c.not_interpreted_settings}, outside distance protection {c.outside_distance_settings})",
        f"Canonical values:          {c.canonical_values_total}"
        f"  (mapped {c.canonical_values_mapped}, assumption {c.canonical_values_assumed},"
        f" unsupported {c.canonical_values_unsupported}, conflict {c.canonical_values_conflicting},"
        f" unreadable {c.canonical_values_unreadable}, missing {c.canonical_values_missing},"
        f" unverified {c.canonical_values_unverified}, not exposed {c.canonical_values_not_exposed})",
        f"Transformed:               {len(report.transformed)}",
        "",
    ]
    for state in STATES:
        group = report.of(state)
        if not group:
            continue
        lines.append(f"[{state}] {len(group)}")
        for e in group:
            where = f" @{e.zone}" if e.zone else ""
            shown = e.value if e.value is not None else "-"
            src = "; ".join(
                f"{s.code or s.name or s.setting_id}={s.raw_value}" + (f" (p{s.page} l{s.line})" if s.page else "")
                for s in e.sources
            ) or "no source"
            lines.append(f"  {e.canonical_id}{where} = {shown}   <- {src}   [{e.mapping_id}]")
            if e.transformation:
                lines.append(f"      transformation: {e.transformation}")
            if state in ("conflict", "unreadable", "unsupported", "missing", "assumption"):
                lines.extend(f"      note: {n}" for n in e.notes)
        lines.append("")
    lines.append(f"[unmapped] {len(report.unmapped)}")
    for u in report.unmapped[:show_unmapped]:
        lines.append(f"  {u.code or ''} {u.name or ''} = {u.raw_value}  ({u.scope}) {u.reason}".rstrip())
    if len(report.unmapped) > show_unmapped:
        lines.append(f"  ... {len(report.unmapped) - show_unmapped} more (use --json for all)")
    return "\n".join(lines)


def to_dict(report: DryRunReport) -> dict[str, Any]:
    from dataclasses import asdict

    return {
        "catalog_id": report.catalog_id, "catalog_version": report.catalog_version, "lifecycle": report.lifecycle,
        "coverage": report.coverage.as_dict(), "counts": report.counts(), "notes": list(report.notes),
        "entries": [asdict(e) | {"transformed": e.transformed} for e in report.entries],
        "unmapped": [asdict(u) for u in report.unmapped],
    }
