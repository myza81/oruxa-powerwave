"""Tests for TripCapability classification (DEC-199 Phase 3A).

Covers the generic capability_rules interpreter, 7SA613 and GRZ100 proof cases,
backward compatibility of existing catalogs, and the production-isolation contract
(no Apply-eligibility change, no pickup-only plotting, DELAY_INFINITE blocker
unchanged, GRZ100 still Not Ready).
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.domain.parameter_catalog.catalog_validation import parse_catalog
from app.domain.parameter_catalog.errors import CatalogValidationError
from app.domain.parameter_catalog.interpreter import CatalogInterpreter
from app.domain.parameter_catalog.loader import CATALOG_ROOT, canonical_registry, default_store
from app.domain.relay_import.canonical_distance import TripCapability
from app.domain.relay_import.engine_adapter import UnsupportedCode, adapt_to_engine
from app.domain.relay_import.provenance import MappingStatus, ProvenanceOrigin
from app.services.relay_pdf_extractor import extract_pdf
from tests.relay_conformance.sheet_spec import sheet_pdf

SA613_JSON = CATALOG_ROOT / "siemens" / "siprotec4_7sa613.json"
GRZ_JSON = CATALOG_ROOT / "toshiba" / "grz100.json"


def model_of(catalog_id: str, pdf: bytes):
    return CatalogInterpreter(default_store().get(catalog_id), canonical_registry()).interpret(
        extract_pdf(pdf).document
    )


@pytest.fixture(scope="module")
def sa613_model():
    return model_of("siemens-7sa613-catalog", sheet_pdf("7sa613"))


@pytest.fixture(scope="module")
def sa613_delays_model():
    """7SA613 with finite delays set for Z1 — exercises TIMED_TRIP classification."""
    return model_of(
        "siemens-7sa613-catalog",
        sheet_pdf("7sa613", {"set": {"1305 T1-1phase": "0.05", "1306 T1-multi-phase": "0.15"}}),
    )


@pytest.fixture(scope="module")
def grz_model():
    return model_of("toshiba-grz100-catalog", sheet_pdf("grz100", {"set": {"ZG-C": "Quad"}}))


# ---------------------------------------------------------------------------
# TripCapability enum
# ---------------------------------------------------------------------------

class TestTripCapabilityEnum:
    def test_all_values_are_defined(self):
        values = {c.value for c in TripCapability}
        assert values == {"timed_trip", "pickup_only", "scheme_dependent", "signalling_only", "unverified", "unknown"}

    def test_trip_capability_is_a_str_enum(self):
        assert TripCapability.TIMED_TRIP == "timed_trip"


# ---------------------------------------------------------------------------
# 7SA613 proof case: PICKUP_ONLY
# ---------------------------------------------------------------------------

class TestSA613PickupOnly:
    """Z1B with infinite timer → PICKUP_ONLY in the default sheet."""

    def test_z1b_with_infinite_timer_is_pickup_only(self, sa613_model):
        z1b = sa613_model.zone("Z1B")
        assert z1b.trip_capability.is_resolved
        assert z1b.trip_capability.value == TripCapability.PICKUP_ONLY

    def test_pickup_only_provenance_is_default_assumption(self, sa613_model):
        z1b = sa613_model.zone("Z1B")
        prov = z1b.trip_capability.provenance
        assert prov.status == MappingStatus.MAPPED
        assert prov.origin == ProvenanceOrigin.DEFAULT_ASSUMPTION

    def test_pickup_only_provenance_carries_oem_reference(self, sa613_model):
        z1b = sa613_model.zone("Z1B")
        assert z1b.trip_capability.provenance.references

    def test_z4_no_rule_applies_without_matching_condition(self, sa613_model):
        # Z4 has infinite timer but is not listed in any capability rule → unresolved
        z4 = sa613_model.zone("Z4")
        assert not z4.trip_capability.is_resolved

    def test_z5_infinite_timer_no_matching_rule(self, sa613_model):
        # Z5 has infinite timer in the default sheet, but no "infinite" rule covers it
        z5 = sa613_model.zone("Z5")
        assert not z5.trip_capability.is_resolved


# ---------------------------------------------------------------------------
# 7SA613 proof case: TIMED_TRIP (requires finite delays on Z1)
# ---------------------------------------------------------------------------

class TestSA613TimedTrip:
    """Z1 with a finite timer → TIMED_TRIP."""

    def test_z1_with_finite_timer_is_timed_trip(self, sa613_delays_model):
        z1 = sa613_delays_model.zone("Z1")
        assert z1.trip_capability.is_resolved
        assert z1.trip_capability.value == TripCapability.TIMED_TRIP

    def test_z1b_stays_pickup_only_when_finite_z1_rule_also_applies(self, sa613_delays_model):
        # Z1B still has infinite timers even in the delays variant → PICKUP_ONLY wins (rule order)
        z1b = sa613_delays_model.zone("Z1B")
        assert z1b.trip_capability.is_resolved
        assert z1b.trip_capability.value == TripCapability.PICKUP_ONLY

    def test_timed_trip_provenance_is_default_assumption(self, sa613_delays_model):
        z1 = sa613_delays_model.zone("Z1")
        prov = z1.trip_capability.provenance
        assert prov.status == MappingStatus.MAPPED
        assert prov.origin == ProvenanceOrigin.DEFAULT_ASSUMPTION


# ---------------------------------------------------------------------------
# GRZ100 proof case
# ---------------------------------------------------------------------------

class TestGRZ100TripCapability:
    """Z4 → SIGNALLING_ONLY; remaining zones → SCHEME_DEPENDENT."""

    def test_z4_is_signalling_only(self, grz_model):
        z4 = grz_model.zone("Z4")
        assert z4.trip_capability.is_resolved
        assert z4.trip_capability.value == TripCapability.SIGNALLING_ONLY

    @pytest.mark.parametrize("zone_id", ["Z1", "Z1X", "Z2", "ZF", "Z3", "ZR1", "ZR2", "ZND"])
    def test_scheme_dependent_zones(self, grz_model, zone_id):
        zone = grz_model.zone(zone_id)
        assert zone.trip_capability.is_resolved
        assert zone.trip_capability.value == TripCapability.SCHEME_DEPENDENT

    def test_signalling_only_does_not_imply_trip_authorization(self, grz_model):
        # SIGNALLING_ONLY is about relay function, not site trip authorization
        z4 = grz_model.zone("Z4")
        assert z4.trip_capability.value != TripCapability.TIMED_TRIP
        assert z4.trip_capability.value != TripCapability.PICKUP_ONLY

    def test_scheme_dependent_does_not_imply_trip_authorization(self, grz_model):
        z1 = grz_model.zone("Z1")
        assert z1.trip_capability.value == TripCapability.SCHEME_DEPENDENT
        assert z1.trip_capability.value != TripCapability.TIMED_TRIP


# ---------------------------------------------------------------------------
# Production isolation: trip_capability excluded from iter_sourced
# ---------------------------------------------------------------------------

class TestProductionIsolation:
    def test_trip_capability_not_in_items_needing_confirmation(self, sa613_model):
        items = sa613_model.items_needing_confirmation()
        assert not any("trip_capability" in path for path in items)

    def test_trip_capability_not_in_unresolved_paths(self, sa613_model):
        paths = sa613_model.unresolved_paths()
        assert not any("trip_capability" in path for path in paths)

    def test_grz100_remains_blocked_by_existing_issues(self, grz_model):
        # SCHEME_DEPENDENT does not grant Apply — GRZ100 still blocked by geometry
        z1 = grz_model.zone("Z1")
        result = adapt_to_engine(replace(grz_model, zones=(z1,)), engine_basis="secondary")
        assert result.reasons  # still blocked; trip_capability doesn't remove blockers

    def test_delay_infinite_blocker_unchanged_for_z1b(self, sa613_model):
        z1b = sa613_model.zone("Z1B")
        result = adapt_to_engine(replace(sa613_model, zones=(z1b,)), engine_basis="secondary")
        codes = {r.code for r in result.reasons}
        assert UnsupportedCode.DELAY_INFINITE in codes

    def test_pickup_only_does_not_remove_delay_infinite_blocker(self, sa613_model):
        # PICKUP_ONLY is stored only; it must not suppress the DELAY_INFINITE engine blocker
        z1b = sa613_model.zone("Z1B")
        assert z1b.trip_capability.value == TripCapability.PICKUP_ONLY
        result = adapt_to_engine(replace(sa613_model, zones=(z1b,)), engine_basis="secondary")
        codes = {r.code for r in result.reasons}
        assert UnsupportedCode.DELAY_INFINITE in codes


# ---------------------------------------------------------------------------
# Backward compatibility: existing catalogs unaffected
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    @pytest.mark.parametrize("catalog_id", [
        "hitachi-red670-catalog",
        "hitachi-rel511-catalog",
        "schneider-micom-p44x-catalog",
    ])
    def test_existing_catalog_has_no_capability_rules(self, catalog_id):
        cat = default_store().get(catalog_id)
        assert cat.capability_rules == ()

    def test_existing_catalog_zones_have_unresolved_trip_capability(self):
        cat = default_store().get("hitachi-rel511-catalog")
        pdf = sheet_pdf("rel511")
        model = CatalogInterpreter(cat, canonical_registry()).interpret(extract_pdf(pdf).document)
        for zone in model.zones:
            assert not zone.trip_capability.is_resolved


# ---------------------------------------------------------------------------
# Catalog validation: capability_rules section
# ---------------------------------------------------------------------------

class TestCapabilityRuleValidation:
    def _load_sa613(self):
        return json.loads(SA613_JSON.read_text(encoding="utf-8"))

    def test_unknown_zone_id_in_rule_is_rejected(self):
        data = self._load_sa613()
        data["capability_rules"][0]["zones"] = list(data["capability_rules"][0]["zones"]) + ["Z99_NONEXISTENT"]
        with pytest.raises(CatalogValidationError, match="Z99_NONEXISTENT"):
            parse_catalog(data, canonical_registry(), source="7sa613")

    def test_invalid_capability_value_is_rejected(self):
        data = self._load_sa613()
        data["capability_rules"][0]["capability"] = "trips_sometimes"
        with pytest.raises(CatalogValidationError):
            parse_catalog(data, canonical_registry(), source="7sa613")

    def test_invalid_timer_condition_is_rejected(self):
        data = self._load_sa613()
        data["capability_rules"][0]["timer_condition"] = "sometimes"
        with pytest.raises(CatalogValidationError):
            parse_catalog(data, canonical_registry(), source="7sa613")

    def test_valid_timer_conditions_are_accepted(self):
        for cond in ("finite", "infinite", None):
            data = self._load_sa613()
            data["capability_rules"][0]["timer_condition"] = cond
            cat = parse_catalog(data, canonical_registry(), source="7sa613")
            assert cat.capability_rules[0].timer_condition == cond

    def test_catalog_without_capability_rules_key_loads(self):
        data = self._load_sa613()
        del data["capability_rules"]
        cat = parse_catalog(data, canonical_registry(), source="7sa613")
        assert cat.capability_rules == ()

    def test_duplicate_rule_id_is_rejected(self):
        data = self._load_sa613()
        dup = dict(data["capability_rules"][0])
        data["capability_rules"].append(dup)
        with pytest.raises(CatalogValidationError):
            parse_catalog(data, canonical_registry(), source="7sa613")
