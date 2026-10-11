"""Slice 8A: the review's uncertainty categories.

Mapped / Assumption / Missing / Conflict / Unsupported / Unreadable are a
*presentation* of three facts the model keeps apart -- the profile's
interpretation status, the recorded cause of an unresolved value (source /
extraction) and the engine adapter's verdict (capability). These tests pin the
classification of the P441 sample, each category's derivation, the rule that only
an Assumption is confirmable, and that readiness is unchanged by any of it.
"""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_codec import decode_model, encode_model
from app.domain.relay_import.canonical_distance import CharacteristicType
from app.domain.relay_import.provenance import MappingStatus, Sourced, UnresolvedCause
from app.domain.relay_import.review_state import ReviewDecisions, apply_review
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.services.relay_review_validation import InvalidReviewError, validate_review
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf

REVERSE = "zones[{}].resistive_reach.reverse"
ZP_STATUS = "zones[ZP].status"
UPLOAD = "/api/v1/relay-import/upload"
VALIDATE = "/api/v1/relay-import/review/validate"


@pytest.fixture(scope="module")
def model():
    return MicomP441Profile().interpret(make_doc())


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _review(model, **decisions):
    return validate_review(encode_model(model), ReviewDecisions(**decisions))


def _items(review):
    """Every listed row by key (a reach and its angle are two rows)."""
    return {i.key: i for g in review.groups for i in g.items}


def _by_path(review):
    return {i.item_id: i for g in review.groups for i in g.items if i.item_id and i.primary}


def _interpret(**doc_kwargs):
    return MicomP441Profile().interpret(make_doc(**doc_kwargs))


class TestP441Classification:
    """Every non-mapped value of the sample, classified by why it is uncertain."""

    def test_counts_use_the_new_categories(self, model):
        r = _review(model)
        assert (r.mapped_count, r.assumption_count, r.missing_count) == (32, 36, 10)
        assert (r.conflict_count, r.unsupported_count, r.unreadable_count) == (0, 4, 0)

    def test_every_inferred_value_is_an_assumption_with_its_reason(self, model):
        items = [i for i in _items(_review(model)).values() if i.status == "inferred"]
        assert len(items) > 36  # two rows for a reach and its angle
        for item in items:
            assert item.category == "assumption", item.key
            assert item.notes, item.key  # the profile's reason is carried, never dropped
        z1_direction = _items(_review(model))["zone.Z1.direction"]
        assert "forward-looking in the P441 family" in z1_direction.notes[0]

    def test_mapped_values_stay_mapped_and_ask_nothing(self, model):
        for item in _items(_review(model)).values():
            if item.status == "mapped":
                assert item.category == "mapped" and item.review_status == "mapped" and item.resolution is None

    def test_values_absent_from_the_sheet_are_missing(self, model):
        items = _items(_review(model))
        for key in (
            "zone.Z1.rr.reverse", "zone.Z2.rr.reverse", "zone.Z3.rr.reverse", "zone.Z4.rr.reverse", "zone.ZP.rr.reverse",
            "relay.version", "base.voltage", "base.current", "line.z1", "zone.ZP.status",
        ):
            assert items[key].category == "missing", key
            assert items[key].status == "unresolved", key

    def test_a_reverse_resistive_reach_is_missing_not_something_to_confirm(self, model):
        item = _items(_review(model))["zone.Z1.rr.reverse"]
        assert item.category == "missing" and item.blocking
        assert item.resolution is not None and item.resolution.kind == "number"  # canonical type/unit known

    def test_settings_the_profile_keeps_raw_are_unsupported(self, model):
        raw = [i for i in _items(_review(model)).values() if ".raw." in i.key]
        assert len(raw) == 4  # Z1m, Z1p, Z2/Zp tilt (Z2 and ZP share one)
        for item in raw:
            assert item.category == "unsupported" and item.status == "unresolved"
            assert item.resolution is None and item.item_id is None
            assert "tilt applies per fault-loop type" in item.notes[0]

    def test_zone_p_state_is_missing_and_carries_the_engine_limit(self, model):
        zp = _items(_review(model))["zone.ZP.status"]
        assert zp.category == "missing" and zp.blocking
        assert "ZP cannot be represented" in zp.engine_reason
        assert zp.resolution is not None  # disabling it is a legitimate answer

    def test_nothing_in_the_sample_is_a_conflict_or_unreadable(self, model):
        categories = {i.category for i in _items(_review(model)).values()}
        assert categories == {"mapped", "assumption", "missing", "unsupported"}

    def test_interpretation_status_is_not_replaced_by_the_category(self, model):
        r = _review(model)
        statuses = {(i.status, i.category) for i in _items(r).values()}
        assert statuses == {
            ("mapped", "mapped"), ("inferred", "assumption"), ("unresolved", "missing"), ("unresolved", "unsupported"),
        }


class TestCategoryCauses:
    """The recorded cause of an unresolved value, from the P441 profile."""

    def _item(self, model, key):
        return _items(_review(model))[key]

    def test_an_absent_code_is_missing(self):
        item = self._item(_interpret(drop=("300D",)), "zone.Z1.rr.pp")
        assert item.status == "unresolved" and item.category == "missing"
        assert "not present in the document" in item.notes[0]

    def test_conflicting_duplicates_are_a_conflict_and_nothing_is_chosen(self):
        model = _interpret(extra=(("300E", "tZ1", "0.4", "0-10.0 s"),))
        item = self._item(model, "zone.Z1.timer")
        assert item.status == "unresolved" and item.category == "conflict" and item.value_text is None
        assert "conflicting duplicate entries" in item.notes[0]
        assert item.resolution is None  # the competing choices are not offered as a typed value
        assert _review(model).conflict_count == 1

    def test_a_value_outside_its_printed_range_is_a_conflict(self):
        model = _interpret(overrides={"300E": ("tZ1", "99", "0-10.0 s")})
        assert self._item(model, "zone.Z1.timer").category == "conflict"

    def test_text_that_is_not_a_number_is_unreadable(self):
        model = _interpret(overrides={"300A": ("Z1", "1,43", "0.001-500 /I1")})
        item = self._item(model, "zone.Z1.reach")
        assert item.status == "unresolved" and item.category == "unreadable"
        assert item.raw_value == "1,43" and item.value_text is None
        assert _review(model).unreadable_count >= 1

    def test_an_empty_value_cell_is_unreadable(self):
        model = _interpret(overrides={"300A": ("Z1", "", "0.001-500 /I1")})
        assert self._item(model, "zone.Z1.reach").category == "unreadable"

    def test_a_value_the_profile_does_not_recognise_is_unsupported(self):
        model = _interpret(overrides={"301D": ("ZoneP - Direct", "Sideways", "Directional FWD/REV")})
        item = self._item(model, "zone.ZP.direction")
        assert item.status == "unresolved" and item.category == "unsupported"

    def test_the_strongest_cause_wins(self):
        # a conflict (duplicate) outranks an unreadable value on the same setting
        model = _interpret(overrides={"300A": ("Z1", "1,43", "0.001-500 /I1")}, extra=(("300A", "Z1", "1.50", "0.001-500 /I1"),))
        assert self._item(model, "zone.Z1.reach").category == "conflict"

    def test_the_cause_survives_the_snapshot_and_a_manual_resolution(self, model):
        decoded = decode_model(encode_model(model))
        assert dict(decoded.iter_sourced())[ZP_STATUS].provenance.cause is UnresolvedCause.MISSING
        resolved = apply_review(decoded, ReviewDecisions(manual={ZP_STATUS: "disabled"}))
        assert dict(resolved.iter_sourced())[ZP_STATUS].provenance.cause is UnresolvedCause.MISSING

    def test_an_unclassified_unresolved_value_is_presented_as_missing(self, model):
        # a placeholder the profile never touched has no recorded cause
        reverse = dict(model.iter_sourced())[REVERSE.format("Z1")]
        assert reverse.provenance.cause is None
        assert _items(_review(model))["zone.Z1.rr.reverse"].category == "missing"


class TestEngineLimits:
    """Engine capability is its own fact: it decides Unsupported / Conflict for a
    value that was read and interpreted perfectly well."""

    def test_zone_p_enabled_becomes_unsupported_and_stays_resolvable(self, model):
        before = _review(model)
        r = _review(model, manual={ZP_STATUS: "enabled"})
        zp = _items(r)["zone.ZP.status"]
        assert zp.category == "unsupported" and zp.review_status == "resolved_manually" and zp.value_text == "Enabled"
        assert "ZP cannot be represented" in zp.engine_reason
        assert zp.resolution is not None  # the user can change their mind
        assert (r.unsupported_count, r.missing_count) == (before.unsupported_count + 1, before.missing_count - 1)
        assert r.readiness.status == "not_ready"  # engine decides; the category is only how it is shown
        # the other answer clears it again
        assert _items(_review(model, manual={ZP_STATUS: "disabled"}))["zone.ZP.status"].category == "missing"

    def test_an_unsupported_characteristic_is_unsupported_not_an_assumption(self, model):
        r = _review(_with_lenticular(model))
        item = _by_path(r)["zones[Z1].characteristic.type"]
        assert item.status == "inferred" and item.category == "unsupported"
        assert "not supported by the current Distance Protection engine" in item.engine_reason
        # an Assumption it no longer counts as, so it cannot inflate the bulk action
        assert r.assumption_count == 35 and r.unsupported_count == 5

    def test_resolved_values_that_disagree_are_a_conflict(self, model):
        zone = model.zones[0]
        pp = zone.resistive_reach.phase_phase
        common = Sourced(pp.value + 1.0, pp.provenance)
        clashing = replace(model, zones=(replace(zone, resistive_reach=replace(zone.resistive_reach, common=common)), *model.zones[1:]))
        r = _review(clashing)
        by_path = _by_path(r)
        assert by_path["zones[Z1].resistive_reach.phase_phase"].category == "conflict"
        assert by_path["zones[Z1].resistive_reach.common"].category == "conflict"
        # the mapped phase-phase reach moves out of Mapped; the added common value was never mapped
        assert r.conflict_count == 2 and r.mapped_count == 31


def _with_lenticular(model):
    zone = model.zones[0]
    lenticular = Sourced(CharacteristicType.LENTICULAR, zone.characteristic.type.provenance)
    assert lenticular.provenance.status is MappingStatus.INFERRED
    return replace(model, zones=(replace(zone, characteristic=replace(zone.characteristic, type=lenticular)), *model.zones[1:]))


class TestConfirmation:
    def _pending_assumptions(self, model):
        return frozenset(
            path for path, i in _by_path(_review(model)).items() if i.category == "assumption" and i.review_status == "to_confirm"
        )

    def test_bulk_confirmation_of_assumptions_touches_only_assumptions(self, model):
        before = _review(model)
        pending = self._pending_assumptions(model)
        assert len(pending) == before.assumption_count == 36
        r = _review(model, confirmed=pending)
        assert (r.confirmed_count, r.assumption_count) == (36, 0)
        assert (r.mapped_count, r.missing_count, r.unsupported_count) == (before.mapped_count, before.missing_count, before.unsupported_count)
        assert all(i.category == "assumption" for i in _items(r).values() if i.review_status == "confirmed")

    def test_a_confirmed_assumption_is_still_traceable_as_one(self, model):
        path = "zones[Z1].reach"
        r = _review(model, confirmed=frozenset({path}))
        item = _by_path(r)[path]
        assert item.review_status == "confirmed"
        assert item.category == "assumption" and item.status == "inferred"
        assert "the reach is set at the line angle" in item.notes[0]  # what was assumed is still shown
        assert item.resolution is None

    def test_only_an_assumption_can_be_confirmed(self, model):
        # mapped, missing and an engine-limited value are all refused
        for path in ("transformers.ct_primary_a", REVERSE.format("Z1"), ZP_STATUS):
            with pytest.raises(Exception):
                _review(model, confirmed=frozenset({path}))

    def test_an_unsupported_value_cannot_be_confirmed_away(self, model):
        lenticular = _with_lenticular(model)
        path = "zones[Z1].characteristic.type"
        assert _by_path(_review(lenticular))[path].review_status == "to_confirm"
        with pytest.raises(InvalidReviewError, match="Only an assumption can be confirmed"):
            _review(lenticular, confirmed=frozenset({path}))

    def test_a_conflicting_value_cannot_be_confirmed(self, model):
        zone = model.zones[0]
        pp = zone.resistive_reach.phase_phase
        clashing = replace(
            model,
            zones=(replace(zone, resistive_reach=replace(zone.resistive_reach, common=Sourced(pp.value + 1.0, pp.provenance))), *model.zones[1:]),
        )
        with pytest.raises(Exception):
            _review(clashing, confirmed=frozenset({"zones[Z1].resistive_reach.common"}))

    def test_a_missing_value_can_still_be_resolved_where_its_type_is_known(self, model):
        r = _review(model, manual={REVERSE.format("Z1"): 2.5})
        item = _by_path(r)[REVERSE.format("Z1")]
        assert item.review_status == "resolved_manually" and item.user_value_text == "2.5 Ω"
        assert item.category == "missing"  # the original classification stays traceable
        assert r.missing_count == 9 and r.blocking_count == 3


class TestReadinessIsUnchanged:
    def test_the_sample_reads_exactly_as_before(self, model):
        r = _review(model)
        assert r.readiness.status == "not_ready" and r.readiness.pending_confirmations == 36
        assert r.blocking_count == 4 and len(r.blocking_issues) == 2  # settings vs reasons: different numbers
        assert r.to_confirm_count == 36 and r.unresolved_count == 14 and r.engine.status == "not_ready"

    def test_confirming_assumptions_alone_never_makes_it_ready(self, model):
        pending = frozenset(p for p, i in _by_path(_review(model)).items() if i.category == "assumption")
        assert _review(model, confirmed=pending).readiness.status == "not_ready"

    def test_a_confirmed_assumption_plus_resolved_blockers_is_ready(self, model):
        pending = frozenset(p for p, i in _by_path(_review(model)).items() if i.category == "assumption")
        manual = {REVERSE.format(z): 2.5 for z in ("Z1", "Z2", "Z3")} | {ZP_STATUS: "disabled"}
        assert _review(model, manual=manual).readiness.status == "ready_after_confirmation"
        assert _review(model, confirmed=pending, manual=manual).readiness.status == "ready"

    def test_zone_p_enabled_is_still_not_ready(self, model):
        pending = frozenset(p for p, i in _by_path(_review(model)).items() if i.category == "assumption")
        manual = {REVERSE.format(z): 2.5 for z in ("Z1", "Z2", "Z3")} | {ZP_STATUS: "enabled"}
        assert _review(model, confirmed=pending, manual=manual).readiness.status == "not_ready"


class TestApi:
    def _upload_review(self, client):
        r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
        assert r.status_code == 200
        return r.json()["review"]

    def test_the_upload_review_carries_the_categories_and_counts(self, client):
        review = self._upload_review(client)
        for key in ("assumption_count", "missing_count", "conflict_count", "unsupported_count", "unreadable_count"):
            assert isinstance(review[key], int), key
        assert review["assumption_count"] == review["to_confirm_count"]
        items = [i for g in review["groups"] for i in g["items"]]
        assert {i["category"] for i in items} <= {"mapped", "assumption", "missing", "conflict", "unsupported", "unreadable"}
        # the interpretation status is unchanged beside it
        assert all(i["status"] in ("mapped", "inferred", "unresolved") for i in items)
        assert {i["category"] for i in items if i["status"] == "inferred"} == {"assumption"}

    def test_the_validation_state_repeats_category_and_engine_reason_per_item(self, client):
        review = self._upload_review(client)
        state = client.post(
            VALIDATE,
            json={"validation_context": review["validation_context"], "manual": [{"item_id": ZP_STATUS, "value": "enabled"}]},
        ).json()
        zp = next(i for i in state["items"] if i["item_id"] == ZP_STATUS)
        assert zp["category"] == "unsupported" and "ZP cannot be represented" in zp["engine_reason"]
        for key in ("assumption_count", "missing_count", "conflict_count", "unsupported_count", "unreadable_count"):
            assert key in state
        assert state["unsupported_count"] == review["unsupported_count"] + 1

    def test_validation_without_decisions_matches_the_upload_categories(self, client):
        review = self._upload_review(client)
        state = client.post(VALIDATE, json={"validation_context": review["validation_context"]}).json()
        for key in ("assumption_count", "missing_count", "conflict_count", "unsupported_count", "unreadable_count"):
            assert state[key] == review[key], key

    def test_confirming_an_engine_limited_value_is_a_400(self, client, model):
        path = "zones[Z1].characteristic.type"
        r = client.post(VALIDATE, json={"validation_context": encode_model(_with_lenticular(model)), "confirmed": [path]})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "invalid_review"
        assert "Only an assumption can be confirmed" in r.json()["detail"]["message"]
