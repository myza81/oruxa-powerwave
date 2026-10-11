"""Slice 8: review confirmation / resolution -- the session review overlay.

Domain behaviour (confirm, manual resolution, effective model, adapter
re-evaluation, blocking items, readiness), the stateless validation service and
endpoint, and the guarantees that nothing is persisted or applied.
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_codec import SnapshotError, decode_model, encode_model
from app.domain.relay_import.engine_adapter import adapt_to_engine
from app.domain.relay_import.provenance import MappingStatus, ProvenanceOrigin, ReviewStatus
from app.domain.relay_import.review_state import (
    Readiness,
    ReviewDecisionError,
    ReviewDecisions,
    apply_review,
    compute_readiness,
    resolution_spec,
)
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.services.relay_interpretation_summary import engine_adaptation
from app.services.relay_review_validation import InvalidReviewError, validate_review
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"
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


def _state(model, **decisions):
    review = validate_review(encode_model(model), ReviewDecisions(**decisions))
    return review, {i.item_id: i for g in review.groups for i in g.items if i.item_id and i.primary}


def _pending(model):
    review, items = _state(model)
    return frozenset(i for i, item in items.items() if item.review_status == "to_confirm")


def _p441_resolutions():
    """The reverse reach for every evaluated zone, plus Zone P disabled."""
    return {REVERSE.format(z): 2.5 for z in ("Z1", "Z2", "Z3")} | {ZP_STATUS: "disabled"}


class TestConfirmation:
    def test_an_inferred_value_can_be_confirmed_and_keeps_its_interpretation(self, model):
        path = "zones[Z1].reach"
        original = dict(model.iter_sourced())[path]
        effective = dict(apply_review(model, ReviewDecisions(confirmed=frozenset({path}))).iter_sourced())[path]
        assert original.provenance.status is MappingStatus.INFERRED and original.provenance.review is None
        assert effective.value == original.value
        # still inferred -- confirmation never pretends the value was deterministic
        assert effective.provenance.status is MappingStatus.INFERRED
        assert effective.provenance.sources == original.provenance.sources
        assert effective.provenance.notes == original.provenance.notes
        assert effective.provenance.raw_value == original.provenance.raw_value
        assert effective.provenance.profile_version == original.provenance.profile_version
        record = effective.provenance.review
        assert record.status is ReviewStatus.CONFIRMED and record.original_status is MappingStatus.INFERRED
        assert record.origin is ProvenanceOrigin.SESSION_REVIEW
        assert original.needs_confirmation and not effective.needs_confirmation

    def test_the_original_model_is_never_modified(self, model):
        before = encode_model(model)
        apply_review(model, ReviewDecisions(confirmed=_pending(model), manual=_p441_resolutions()))
        assert encode_model(model) == before
        assert all(s.provenance.review is None for _, s in model.iter_sourced())

    def test_undo_is_dropping_the_decision(self, model):
        _, with_confirm = _state(model, confirmed=frozenset({"zones[Z1].reach"}))
        review, undone = _state(model, confirmed=frozenset())
        assert with_confirm["zones[Z1].reach"].review_status == "confirmed"
        assert undone["zones[Z1].reach"].review_status == "to_confirm"
        assert undone["zones[Z1].reach"].status == "inferred"
        assert review.confirmed_count == 0 and review.to_confirm_count == 36

    def test_only_inferred_values_can_be_confirmed(self, model):
        mapped = "transformers.ct_primary_a"
        assert dict(model.iter_sourced())[mapped].provenance.status is MappingStatus.MAPPED
        for path in (mapped, ZP_STATUS, "zones[Nope].reach"):
            with pytest.raises(ReviewDecisionError):
                apply_review(model, ReviewDecisions(confirmed=frozenset({path})))

    def test_mapped_values_never_ask_for_confirmation(self, model):
        _, items = _state(model)
        mapped = [i for i in items.values() if i.review_status == "mapped"]
        assert mapped and all(i.status == "mapped" and i.resolution is None for i in mapped)

    def test_counts_move_from_to_confirm_to_confirmed(self, model):
        review, _ = _state(model, confirmed=_pending(model))
        assert (review.to_confirm_count, review.confirmed_count) == (0, 36)
        assert review.mapped_count == 32  # mapped values are untouched


class TestManualResolution:
    PATH = REVERSE.format("Z1")

    def _effective(self, model, value):
        return dict(apply_review(model, ReviewDecisions(manual={self.PATH: value})).iter_sourced())[self.PATH]

    def test_an_unresolved_value_stays_unresolved_unless_resolved(self, model):
        _, items = _state(model)
        assert items[self.PATH].review_status == "unresolved" and items[self.PATH].value_text is None
        effective = apply_review(model, ReviewDecisions(manual={REVERSE.format("Z2"): 1.0}))
        assert not dict(effective.iter_sourced())[self.PATH].is_resolved

    def test_a_number_resolves_with_its_unit_and_keeps_the_original_provenance(self, model):
        original = dict(model.iter_sourced())[self.PATH]
        resolved = self._effective(model, 2.5)
        assert resolved.value == 2.5 and resolved.provenance.status is MappingStatus.RESOLVED_MANUALLY
        assert resolved.provenance.origin is ProvenanceOrigin.SESSION_REVIEW
        record = resolved.provenance.review
        assert record.original_status is MappingStatus.UNRESOLVED and record.user_value_text == "2.5 Ω"
        assert resolved.provenance.sources == original.provenance.sources
        assert resolved.provenance.raw_value == original.provenance.raw_value
        assert resolved.provenance.notes == original.provenance.notes

    def test_source_value_stays_unavailable_and_the_user_value_is_shown_apart(self, model):
        _, items = _state(model, manual={self.PATH: 2.5})
        item = items[self.PATH]
        assert item.review_status == "resolved_manually" and item.status == "unresolved"
        assert item.value_text == "2.5 Ω" and item.user_value_text == "2.5 Ω"
        assert item.raw_value is None  # the source PDF value is not overwritten

    def test_an_explicit_zero_is_a_value_and_a_blank_is_not(self, model):
        assert self._effective(model, 0).value == 0.0
        assert self._effective(model, 0.0).provenance.review.user_value_text == "0 Ω"
        for blank in (None, "", " ", "abc", True, [], math.nan, math.inf, -1.0, 1e9):
            with pytest.raises(ReviewDecisionError):
                self._effective(model, blank)

    def test_only_unresolved_values_with_a_known_type_can_be_resolved(self, model):
        for path in ("zones[Z1].reach", "transformers.voltage_base_v", "metadata.version", "line.length", "zones[Nope].status"):
            with pytest.raises(ReviewDecisionError):
                apply_review(model, ReviewDecisions(manual={path: 1.0}))
        assert resolution_spec("transformers.voltage_base_v") is None  # unknown semantics stay unresolved
        assert resolution_spec("zones[ZP].status").options == (("enabled", "Enabled"), ("disabled", "Disabled"))
        assert resolution_spec(self.PATH).unit == "ohm" and resolution_spec("zones[Z1].common_timer_s").unit == "s"

    def test_a_choice_must_be_one_of_the_offered_values(self, model):
        for bad in ("on", "inactive", 1.0, ""):
            with pytest.raises(ReviewDecisionError):
                apply_review(model, ReviewDecisions(manual={ZP_STATUS: bad}))

    def test_one_item_cannot_carry_two_decisions(self, model):
        with pytest.raises(ReviewDecisionError):
            apply_review(model, ReviewDecisions(manual={self.PATH: 1.0}, left_unresolved=frozenset({self.PATH})))

    def test_only_unresolved_values_can_be_left_unresolved(self, model):
        with pytest.raises(ReviewDecisionError):
            apply_review(model, ReviewDecisions(left_unresolved=frozenset({"zones[Z1].reach"})))
        review, items = _state(model, left_unresolved=frozenset({self.PATH}))
        assert items[self.PATH].left_unresolved and items[self.PATH].review_status == "unresolved"
        assert items[self.PATH].blocking  # leaving it unresolved does not unblock the engine

    def test_nothing_is_defaulted_from_the_form_or_the_engine(self, model):
        effective = apply_review(model, ReviewDecisions(confirmed=_pending(model)))
        unresolved = [p for p, s in effective.iter_sourced() if not s.is_resolved]
        assert unresolved == [p for p, s in model.iter_sourced() if not s.is_resolved]


class TestBlockingAndReadiness:
    def test_p441_sample_is_not_ready_with_four_blocking_items(self, model):
        review, items = _state(model)
        assert review.readiness.status == "not_ready"
        assert review.blocking_count == 4
        blocking = {p for p, i in items.items() if i.blocking}
        assert blocking == {REVERSE.format(z) for z in ("Z1", "Z2", "Z3")} | {ZP_STATUS}

    def test_unresolved_items_are_classified_blocking_or_not(self, model):
        _, items = _state(model)
        non_blocking = {REVERSE.format("Z4"), REVERSE.format("ZP"), "metadata.version", "transformers.voltage_base_v"}
        for path in non_blocking:
            assert items[path].review_status == "unresolved" and not items[path].blocking, path

    def test_blocking_issues_come_from_the_adapter_reasons(self, model):
        review, _ = _state(model)
        messages = {i.message for i in review.blocking_issues}
        assert messages == {r.message for r in engine_adaptation(model).reasons}
        reverse = next(i for i in review.blocking_issues if "reverse" in i.message)
        assert set(reverse.zone_ids) == {"Z1", "Z2", "Z3"} and REVERSE.format("Z1") in reverse.item_ids

    def test_resolving_the_blockers_makes_it_ready_after_confirmation(self, model):
        review, _ = _state(model, manual=_p441_resolutions())
        assert review.engine.status == "ready" and review.blocking_count == 0
        assert review.readiness.status == "ready_after_confirmation"
        assert review.readiness.pending_confirmations == 36

    def test_confirming_everything_as_well_makes_it_ready(self, model):
        review, _ = _state(model, manual=_p441_resolutions(), confirmed=_pending(model))
        assert review.readiness.status == "ready" and review.to_confirm_count == 0
        assert (review.confirmed_count, review.resolved_manually_count) == (36, 4)

    def test_confirmation_alone_does_not_make_the_p441_ready(self, model):
        review, _ = _state(model, confirmed=_pending(model))
        assert review.readiness.status == "not_ready" and review.engine.status == "not_ready"

    def test_zone_p_enabled_is_not_ready_for_the_current_engine(self, model):
        manual = _p441_resolutions() | {ZP_STATUS: "enabled"}
        review, items = _state(model, manual=manual, confirmed=_pending(model))
        assert review.readiness.status == "not_ready" and review.engine.status == "not_ready"
        assert items[ZP_STATUS].review_status == "resolved_manually" and not items[ZP_STATUS].blocking
        too_many = next(i for i in review.blocking_issues if "ZP" in i.message)
        assert ZP_STATUS in too_many.item_ids  # the issue outlives the value that caused it
        assert review.blocking_count == 0  # no unresolved item remains; the engine itself is the limit

    def test_zone_p_disabled_lets_the_adapter_ignore_it_and_the_zone_is_kept(self, model):
        effective = apply_review(model, ReviewDecisions(manual=_p441_resolutions()))
        assert effective.zone("ZP") is not None and len(effective.zones) == 5
        adaptation = engine_adaptation(effective)
        assert adaptation.supported and adaptation.zone_ids == ("Z1", "Z2", "Z3", "Z4")
        assert [z.resistive_reach_reverse_ohm for z in adaptation.zones[:3]] == [2.5, 2.5, 2.5]

    def test_zone_p_disabled_alone_is_still_blocked_by_the_reverse_reach(self, model):
        review, _ = _state(model, manual={ZP_STATUS: "disabled"})
        assert review.readiness.status == "not_ready"
        assert [i.message for i in review.blocking_issues] == ["The reverse resistive reach is unresolved."]

    def test_the_reverse_reach_alone_is_still_blocked_by_zone_p(self, model):
        manual = {REVERSE.format(z): 2.5 for z in ("Z1", "Z2", "Z3")}
        review, _ = _state(model, manual=manual)
        assert review.readiness.status == "not_ready" and review.blocking_count == 1

    def test_manual_resolution_does_not_validate_the_profile(self, model):
        effective = apply_review(model, ReviewDecisions(manual=_p441_resolutions()))
        assert effective.metadata.profile_version == model.metadata.profile_version == "micom-p441-v1"
        assert effective.metadata == model.metadata

    def test_readiness_rule(self):
        assert compute_readiness(engine_supported=False, pending_confirmations=0, blocking_unresolved=0) is Readiness.NOT_READY
        assert compute_readiness(engine_supported=True, pending_confirmations=0, blocking_unresolved=1) is Readiness.NOT_READY
        assert compute_readiness(engine_supported=True, pending_confirmations=2, blocking_unresolved=0) is Readiness.READY_AFTER_CONFIRMATION
        assert compute_readiness(engine_supported=True, pending_confirmations=0, blocking_unresolved=0) is Readiness.READY

    def test_the_adapter_runs_again_for_every_evaluation(self, model):
        engine_basis = "secondary"
        base = adapt_to_engine(model, engine_basis=engine_basis)
        reviewed = adapt_to_engine(apply_review(model, ReviewDecisions(manual=_p441_resolutions())), engine_basis=engine_basis)
        assert not base.supported and reviewed.supported
        assert base.reasons and all(isinstance(r.paths, tuple) for r in base.reasons)


class TestSnapshot:
    def test_round_trips_through_json_exactly(self, model):
        decoded = decode_model(json.loads(json.dumps(encode_model(model))))
        assert decoded == replace(model, unmapped_settings=())

    def test_a_snapshot_with_a_review_overlay_round_trips(self, model):
        effective = apply_review(model, ReviewDecisions(confirmed=_pending(model), manual=_p441_resolutions()))
        assert decode_model(json.loads(json.dumps(encode_model(effective)))) == replace(effective, unmapped_settings=())

    @pytest.mark.parametrize(
        "bad",
        [
            None, [], "x", {}, {"_t": "os.system"}, {"_t": "Sourced", "evil": 1},
            {"_t": "RelayMetadata", "source_format": {"_e": "ZoneStatus", "v": "enabled"}},
            {"_e": "ZoneStatus", "v": "nonsense"},
            {"_t": "Sourced", "value": 1.0, "provenance": {"_t": "Provenance", "status": {"_e": "MappingStatus", "v": "mapped"}}},
        ],
    )
    def test_a_malformed_snapshot_is_rejected(self, bad):
        with pytest.raises(InvalidReviewError):
            validate_review(bad, ReviewDecisions())

    def test_decoding_enforces_domain_invariants(self):
        # an unresolved value carrying an engineering value is not a valid Sourced
        bad = {"_t": "Sourced", "value": 1.0, "provenance": {"_t": "Provenance", "status": {"_e": "MappingStatus", "v": "unresolved"}}}
        with pytest.raises(SnapshotError):
            decode_model(bad)


class TestEndpoint:
    def _context(self, client):
        r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
        assert r.status_code == 200
        return r.json()["review"]

    def test_upload_carries_the_context_and_the_initial_state(self, client):
        review = self._context(client)
        assert review["validation_context"]["_t"] == "CanonicalDistanceProtectionModel"
        assert review["readiness"]["status"] == "not_ready" and review["blocking_count"] == 4
        assert all(i["review_status"] in ("mapped", "to_confirm", "unresolved") for g in review["groups"] for i in g["items"])
        assert any(i["resolution"] for g in review["groups"] for i in g["items"])

    def test_validate_returns_the_reviewed_state(self, client):
        ctx = self._context(client)["validation_context"]
        body = {
            "validation_context": ctx,
            "confirmed": ["zones[Z1].reach"],
            "manual": [{"item_id": ZP_STATUS, "value": "disabled"}]
            + [{"item_id": REVERSE.format(z), "value": 2.5} for z in ("Z1", "Z2", "Z3")],
            "left_unresolved": [],
        }
        r = client.post(VALIDATE, json=body)
        assert r.status_code == 200
        state = r.json()
        assert state["confirmed_count"] == 1 and state["resolved_manually_count"] == 4
        assert state["readiness"]["status"] == "ready_after_confirmation" and state["engine"]["status"] == "ready"
        items = {i["item_id"]: i for i in state["items"]}
        assert items["zones[Z1].reach"]["review_status"] == "confirmed" and items["zones[Z1].reach"]["status"] == "inferred"
        assert items[REVERSE.format("Z1")]["user_value_text"] == "2.5 Ω"
        assert "groups" not in state and "validation_context" not in state

    def test_validate_without_decisions_matches_the_upload_state(self, client):
        review = self._context(client)
        state = client.post(VALIDATE, json={"validation_context": review["validation_context"]}).json()
        for key in ("mapped_count", "to_confirm_count", "unresolved_count", "blocking_count", "readiness"):
            assert state[key] == review[key], key

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda b: b.update(confirmed=["transformers.ct_primary_a"]),
            lambda b: b.update(confirmed=["nope"]),
            lambda b: b.update(manual=[{"item_id": REVERSE.format("Z1"), "value": -1}]),
            lambda b: b.update(manual=[{"item_id": REVERSE.format("Z1"), "value": 1}, {"item_id": REVERSE.format("Z1"), "value": 2}]),
            lambda b: b.update(validation_context={"_t": "nope"}),
        ],
    )
    def test_invalid_decisions_are_a_400_with_a_safe_message(self, client, mutate):
        body = {"validation_context": self._context(client)["validation_context"]}
        mutate(body)
        r = client.post(VALIDATE, json=body)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_review"
        assert "nope" not in r.json()["detail"]["message"]

    def test_a_blank_or_boolean_value_is_rejected_before_it_becomes_a_number(self, client):
        ctx = self._context(client)["validation_context"]
        for value in ("", "2.5", True, None):
            r = client.post(VALIDATE, json={"validation_context": ctx, "manual": [{"item_id": REVERSE.format("Z1"), "value": value}]})
            assert r.status_code in (400, 422), value
        ok = client.post(VALIDATE, json={"validation_context": ctx, "manual": [{"item_id": REVERSE.format("Z1"), "value": 0}]})
        assert ok.status_code == 200  # an explicit zero is a value

    def test_validation_keeps_no_state(self, client, tmp_path):
        ctx = self._context(client)["validation_context"]
        before = set(vars(client.app.state))
        first = client.post(VALIDATE, json={"validation_context": ctx, "confirmed": ["zones[Z1].reach"]}).json()
        second = client.post(VALIDATE, json={"validation_context": ctx}).json()
        assert first["confirmed_count"] == 1 and second["confirmed_count"] == 0  # nothing carried between requests
        assert set(vars(client.app.state)) == before
        assert list(tmp_path.iterdir()) == []


class TestNoPersistenceAndNoApply:
    MODULES = (
        BACKEND_APP / "domain" / "relay_import" / "review_state.py",
        BACKEND_APP / "domain" / "relay_import" / "canonical_codec.py",
        BACKEND_APP / "services" / "relay_review_validation.py",
        BACKEND_APP / "services" / "relay_extraction_review.py",
    )

    def test_review_modules_have_no_persistence_code(self):
        for path in self.MODULES:
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "psycopg", "sqlalchemy", "app.storage", "get_storage", "import tempfile", "open(", "write_bytes",
                "write_text", "mkdir", "STORAGE_PATH", "pickle", "shelve", "localStorage", "sessionStorage",
            ):
                assert forbidden not in text, (path.name, forbidden)

    def test_review_modules_name_no_relay(self):
        for path in self.MODULES:
            text = path.read_text(encoding="utf-8")
            for token in ("P441", "MiCOM", "7SA", "Siemens", "Schneider"):
                assert token not in text, (path.name, token)

    def test_the_review_schemas_have_no_apply_semantics(self):
        from app.schemas import relay_import as schemas

        names = {n for cls in (schemas.ExtractionReviewOut, schemas.ReviewStateOut, schemas.ReviewValidationIn) for n in cls.model_fields}
        assert not any(word in n for n in names for word in ("apply", "accept", "populate", "form"))

    def test_the_validation_endpoint_does_not_touch_distance_protection(self):
        text = (BACKEND_APP / "api" / "v1" / "relay_import.py").read_text(encoding="utf-8")
        assert "distance_protection" not in text.replace("Distance Protection form", "")

    def test_every_review_item_path_is_a_canonical_path(self, model):
        review, items = _state(model)
        canonical = {p for p, _ in model.iter_sourced()}
        assert set(items) <= canonical
