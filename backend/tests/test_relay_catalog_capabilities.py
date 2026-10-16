"""Primitive-specific tests for generic relay-catalog and engine-adapter capabilities (DEC-198 Amendments 6-7).

These test reusable capabilities, not a relay: the catalog validator's option rules (``infinity``, the three
material preserved-setting options) and the engine adapter's handling of an infinite delay and of an Unverified /
documented-Unsupported zone status. A shipped catalog or synthetic sheet is only the test vehicle. Each relay's own
behaviour is covered by the generic conformance suite (``tests/test_relay_conformance.py``, DEC-199).
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry, default_store
from app.domain.relay_import.approximation import APPROVED_RULES
from app.domain.relay_import.engine_adapter import (
    UnsupportedCode,
    adapt_to_engine,
    status_unverified,
    zone_geometry_reviewed,
)
from app.domain.relay_import.provenance import DocumentReference, UnresolvedCause, unresolved
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import sheet_pdf

SA613_JSON = CATALOG_ROOT / "siemens" / "siprotec4_7sa613.json"
GRZ_JSON = CATALOG_ROOT / "toshiba" / "grz100.json"


def model_of(catalog_id: str, pdf: bytes):
    return CatalogInterpreter(default_store().get(catalog_id), canonical_registry()).interpret(extract_pdf(pdf).document)


@pytest.fixture(scope="module")
def sa613_model():
    return model_of("siemens-7sa613-catalog", sheet_pdf("7sa613"))


@pytest.fixture(scope="module")
def grz_model():
    return model_of("toshiba-grz100-catalog", sheet_pdf("grz100", {"set": {"ZG-C": "Quad"}}))


def test_no_approximation_rule_is_approved():
    assert APPROVED_RULES == ()


class TestInfinityOption:
    def test_infinity_is_only_for_number_sources(self):
        bad = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        next(m for m in bad["mappings"] if m["id"] == "7sa613.line_length_unit")["source"]["infinity"] = True
        with pytest.raises(CatalogValidationError):
            parse_catalog(bad, canonical_registry(), source="7sa613")

    def test_a_source_without_the_infinity_option_still_refuses_infinity(self):
        plain = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        next(m for m in plain["mappings"] if m["id"] == "7sa613.delay_z4")["source"].pop("infinity")
        catalog = parse_catalog(plain, canonical_registry(), source="7sa613")
        z4 = CatalogInterpreter(catalog, canonical_registry()).interpret(extract_pdf(sheet_pdf("7sa613")).document).zone("Z4")
        assert not z4.common_timer_s.is_resolved and z4.common_timer_s.provenance.cause is UnresolvedCause.UNREADABLE

    def test_a_disabled_zone_with_an_infinite_delay_carries_no_delay_and_is_not_refused(self, sa613_model):
        adaptation = adapt_to_engine(replace(sa613_model, zones=(sa613_model.zone("Z4"),)), engine_basis="secondary")
        assert any("Z4: the delay is set to infinity (no timed trip); no delay is carried" in w for w in adaptation.warnings)
        assert not any("infinity" in r.message for r in adaptation.reasons)


class TestMaterialPreservedOptions:
    def test_unverified_when_and_material_unless_are_exclusive(self):
        bad = json.loads(SA613_JSON.read_text(encoding="utf-8"))
        rule = next(p for p in bad["zone_preserved"] if p["names"] == ["R load (ph-ph)"])
        rule["unverified_when"] = ["x"]
        with pytest.raises(CatalogValidationError):
            parse_catalog(bad, canonical_registry(), source="7sa613")

    def test_always_material_is_exclusive_and_boolean(self):
        data = json.loads(GRZ_JSON.read_text(encoding="utf-8"))
        rule_index = next(k for k, p in enumerate(data["zone_preserved"]) if p.get("always_material"))
        for extra in ({"material_unless": ["x"]}, {"unverified_when": ["x"]}, {"always_material": "yes"}):
            bad = copy.deepcopy(data)
            bad["zone_preserved"][rule_index].update(extra)
            with pytest.raises(CatalogValidationError):
                parse_catalog(bad, canonical_registry(), source="grz100")


class TestZoneStatusCapabilities:
    def test_an_unverified_status_keeps_the_geometry_under_review_and_fails(self, grz_model):
        z1 = grz_model.zone("Z1")
        assert status_unverified(z1) and zone_geometry_reviewed(z1)
        codes = {r.code for r in adapt_to_engine(replace(grz_model, zones=(z1,)), engine_basis="secondary").reasons}
        assert UnsupportedCode.ZONE_STATUS_UNVERIFIED in codes
        assert UnsupportedCode.RESISTIVE_REACH_UNRESOLVED in codes and UnsupportedCode.ZONE_STATUS_UNRESOLVED not in codes

    def test_an_unrecognised_status_value_is_not_a_documented_zone_function(self, grz_model):
        # an Unsupported status without a verified reference (e.g. a selector text the catalog does not know) still
        # reads as an unresolved status, never as a documented non-tripping element
        bare = replace(grz_model.zone("Z2"), status=unresolved(cause=UnresolvedCause.UNSUPPORTED))
        codes = {r.code for r in adapt_to_engine(replace(grz_model, zones=(bare,)), engine_basis="secondary").reasons}
        assert UnsupportedCode.ZONE_STATUS_UNRESOLVED in codes and UnsupportedCode.ZONE_STATUS_UNSUPPORTED not in codes
        ref = DocumentReference("r", "t", "verified", "d", "s", "1", "scope")
        documented = replace(bare, status=unresolved(cause=UnresolvedCause.UNSUPPORTED, references=(ref,)))
        codes = {r.code for r in adapt_to_engine(replace(grz_model, zones=(documented,)), engine_basis="secondary").reasons}
        assert codes == {UnsupportedCode.ZONE_STATUS_UNSUPPORTED}
