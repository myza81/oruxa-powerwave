"""The review DTO stays OEM-neutral: its terms come from the canonical registry, never from a relay.

The frontend table is generated from the review items. Each item's label is the canonical registry's
label for its parameter (a standard term such as "Reactive Reach (X)"); the OEM's own names and codes
appear only under Source. These tests hold that line for both hand-written profiles.
"""

from __future__ import annotations

import pytest

from app.domain.parameter_catalog.loader import canonical_registry
from app.relay_profiles.identification_catalogue import default_registry
from app.services.relay_interpretation_summary import summarize_interpretation
from tests.relay_p441_fixtures import make_doc as p441_doc
from tests.relay_red670_fixtures import make_doc as red670_doc

STANDARD_TERMS = {
    "CT Primary", "CT Secondary", "VT Primary", "VT Secondary", "Setting Values Basis", "Voltage Base", "Current Base",
    "Status", "Direction", "Characteristic", "Reactive Reach (X)", "Right Resistive Reach (+R)", "Phase-Phase Resistive Reach",
    "Left Resistive Reach (−R)", "Earth Resistive Reach", "Time Delay", "Phase Time Delay", "Earth Time Delay",
    "Phase-Phase Faults", "Earth Faults", "Tilt Angle",
}


def review_of(document):
    registry = default_registry()
    summary = summarize_interpretation(registry, document, registry.identify(document))
    assert summary.review is not None
    return summary.review


def items(review):
    return [i for g in review.groups for i in g.items]


@pytest.fixture(params=["p441", "red670"])
def review(request):
    return review_of(p441_doc() if request.param == "p441" else red670_doc())


class TestLabelsComeFromTheRegistry:
    def test_every_registered_item_carries_the_registry_label(self, review):
        reg = canonical_registry()
        checked = 0
        for group in review.groups:
            geometry = "explicit_rx" if any(i.label == "Reactive Reach (X)" for i in group.items) else "polar_reach"
            for item in group.items:
                if item.item_id and item.primary and reg.for_review_path(item.item_id):
                    param = reg.for_review_path(item.item_id)
                    expected = param.label_for(geometry if group.kind == "zone" else None)
                    if group.kind == "compensation":
                        assert item.label.endswith(expected), (item.item_id, item.label)
                    elif item.item_id.endswith(("positive_sequence_impedance", "zero_sequence_impedance", "reach", "zero_sequence_reach", "earth_reach")):
                        assert item.label.startswith(expected), (item.item_id, item.label)         # R / X / Angle rows extend it
                    else:
                        assert item.label == expected, (item.item_id, item.label, expected)
                    checked += 1
        assert checked > 20

    def test_the_standard_terms_are_what_the_frontend_shows(self, review):
        zone_labels = {i.label for g in review.groups if g.kind == "zone" for i in g.items}
        assert zone_labels & STANDARD_TERMS >= {"Status", "Direction", "Characteristic", "Time Delay" if "Time Delay" in zone_labels else "Phase Time Delay"}

    def test_the_geometry_decides_the_right_resistive_reach_wording(self):
        red = {i.label for g in review_of(red670_doc()).groups if g.kind == "zone" for i in g.items}
        p441 = {i.label for g in review_of(p441_doc()).groups if g.kind == "zone" for i in g.items}
        assert "Right Resistive Reach (+R)" in red and "Phase-Phase Resistive Reach" not in red
        assert "Phase-Phase Resistive Reach" in p441 and "Right Resistive Reach (+R)" not in p441


class TestOemTerminologyStaysInSource:
    OEM_TERMS = ("RFPP", "RFPE", "ZM0", "ZMQPDIS", "X1", "OperationDir", "ArgDir", "ArgNegRes", "CTprim", "VTprim", "IBase", "UBase",
                 "R1Ph", "R1G", "tZ1", "Z1X", "Phase CT Primary", "Main VT Primary")

    def test_no_primary_label_is_an_oem_name(self, review):
        for item in items(review):
            if item.item_id is None:
                continue                                                                    # a retained raw setting keeps its own name
            for term in self.OEM_TERMS:
                assert term not in item.label and term not in item.full_label, (item.item_id, item.label)

    def test_the_oem_names_and_codes_are_in_the_sources(self, review):
        source_names = {s.name for i in items(review) for s in i.sources if s.name}
        assert source_names & {"ZM01-:X1", "ZM01-:RFPP", "R1Ph", "Phase CT Primary", "CTprim1"}


class TestRawAndTransformedValuesBothSurvive:
    def test_the_red670_review_shows_the_halved_value_with_the_raw_rfpp_in_source(self):
        review = review_of(red670_doc())
        by_id = {i.item_id: i for i in items(review) if i.item_id}
        pp = by_id["zones[Z2].resistive_reach.phase_phase"]
        assert pp.value_text == "5 Ω" and pp.raw_value == "10" and pp.transformation == "RFPP 10 ohm/loop ÷ 2 = 5 ohm (phase-phase boundary)"
        assert pp.authority == "documented_derivation" and pp.sources[0].raw_value == "10" and pp.sources[0].name == "ZM02-:RFPP"
        pe = by_id["zones[Z2].resistive_reach.phase_earth"]
        assert pe.value_text == "20 Ω" and pe.transformation is None

    def test_a_catalog_owned_value_carries_the_catalog_identity_and_an_extension_value_does_not(self):
        review = review_of(p441_doc())
        by_id = {i.item_id: i for i in items(review) if i.item_id}
        ct = by_id["transformers.ct_primary_a"]                                  # migrated: the catalog owns it
        assert (ct.catalog_id, ct.catalog_version, ct.canonical_id) == ("schneider-micom-p44x-catalog", "1.0.0", "ct_vt.ct_primary")
        line_length = by_id["line.length"]                                    # not migrated: the extension reads it
        assert line_length.catalog_id is None and line_length.canonical_id is None


class TestRegistryDrivesPresentationOrder:
    def test_registered_items_appear_in_the_registrys_display_order_within_each_zone(self, review):
        reg = canonical_registry()
        for group in review.groups:
            if group.kind != "zone":
                continue
            orders = []
            for item in group.items:
                param = reg.for_review_path(item.item_id) if item.item_id and item.primary else None
                if param is not None and not param.id.startswith("distance.zone.comp."):
                    orders.append((param.order, param.id))
            assert orders == sorted(orders), (group.title, orders)

    def test_the_transformer_group_follows_the_registrys_order_and_units(self, review):
        reg = canonical_registry()
        group = next(g for g in review.groups if g.kind == "transformers")
        params = [reg.for_review_path(i.item_id) for i in group.items if i.item_id]
        assert [p.order for p in params] == sorted(p.order for p in params)
        for item, param in zip((i for i in group.items if i.item_id), params):
            if item.value_text and param.unit in ("A", "V"):
                assert item.value_text.endswith(param.unit), (item.item_id, item.value_text)
