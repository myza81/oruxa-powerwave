"""Shared builders for the parameter-catalog tests: raw documents, tiny catalogs, the shipped registry."""

from __future__ import annotations

import copy
from typing import Any

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import canonical_registry
from app.domain.relay_import.raw_document import (
    RawRelayDocument,
    RawSetting,
    SettingRange,
    SourceFormat,
    SourceLocation,
)

Row = tuple  # (name, value[, range[, code]])


def doc(*rows: Row, section: tuple[str, ...] = ()) -> RawRelayDocument:
    """A raw document from ``(name, value, printed_range, parameter_id)`` rows (trailing items optional)."""
    settings = []
    for i, row in enumerate(rows, start=1):
        name, value = row[0], row[1]
        rng = row[2] if len(row) > 2 else None
        code = row[3] if len(row) > 3 else None
        settings.append(RawSetting(
            setting_id=f"s{i}", name=name, parameter_id=code, raw_value=value,
            setting_range=SettingRange(text=rng) if rng else None, section_path=section,
            location=SourceLocation(page=1, line=i),
        ))
    return RawRelayDocument(SourceFormat.PDF, tuple(settings))


BASE: dict[str, Any] = {
    "schema": "oruxa.parameter-catalog/1",
    "catalog_id": "acme-x1",
    "version": "1.0.0",
    "lifecycle": "tested",
    "applicability": {"manufacturer": "Acme", "family": "X-Series", "model": "X1"},
    "identification": {"model_patterns": ["X-?1"], "scheme_model_pattern": "(?<![A-Za-z0-9])X-?1(?![A-Za-z0-9])"},
    "zones": {"static": [{"id": "Z1", "name": "Zone 1"}, {"id": "Z2", "name": "Zone 2"}]},
    "mappings": [],
}


def catalog_json(*mappings: dict, **overrides: Any) -> dict[str, Any]:
    data = copy.deepcopy(BASE)
    data["mappings"] = list(copy.deepcopy(mappings))
    data.update(copy.deepcopy(overrides))
    return data


def parse(data: dict[str, Any]):
    return parse_catalog(data, canonical_registry(), source="test")


def interpret(data: dict[str, Any], document: RawRelayDocument):
    return CatalogInterpreter(parse(data), canonical_registry()).interpret(document)


def interpret_catalog(catalog, document: RawRelayDocument):
    return CatalogInterpreter(catalog, canonical_registry()).interpret(document)


def mapping(mid: str, canonical: str, **kw: Any) -> dict[str, Any]:
    return {"id": mid, "canonical": canonical, **kw}
