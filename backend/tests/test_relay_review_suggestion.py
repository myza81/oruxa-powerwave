"""Distance Protection UX fix: the neutral "0.00 Ω" suggestion for a missing
quadrilateral Left Resistive Reach (−R).

The suggestion is non-authoritative: offered only for that one missing item, never
applied automatically, and recorded as a user-accepted suggestion beside the
original Missing interpretation (never as a source or profile value).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.provenance import MappingStatus, ProvenanceOrigin, ReviewStatus
from app.domain.relay_import.review_state import (
    ReviewDecisionError,
    ReviewDecisions,
    apply_review,
    suggestion_spec,
)
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_review_state import REVERSE, UPLOAD, VALIDATE, ZP_STATUS, _pending, _state

Z123 = ("Z1", "Z2", "Z3")


@pytest.fixture(scope="module")
def model():
    return MicomP441Profile().interpret(make_doc())


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _suggested(*zones):
    return frozenset(REVERSE.format(z) for z in zones)


class TestOffer:
    def test_a_missing_left_reach_is_offered_exactly_zero_ohm(self, model):
        _, items = _state(model)
        for z in Z123:
            item = items[REVERSE.format(z)]
            assert item.category == "missing" and item.review_status == "unresolved"
            assert item.suggestion is not None and item.suggestion.value_text == "0.00 Ω"
            assert item.value_text is None and item.resolution_origin is None  # never auto-applied

    def test_the_label_is_the_vendor_neutral_left_reach(self, model):
        _, items = _state(model)
        assert items[REVERSE.format("Z1")].label == "Left Resistive Reach (−R)"
        assert "Reverse Resistive" not in items[REVERSE.format("Z1")].full_label

    def test_nothing_else_is_ever_suggested(self, model):
        _, items = _state(model)
        offered = {i for i, item in items.items() if item.suggestion}
        # Z4 is defeated in the sample: its Left reach is not required, so nothing is offered for it
        assert offered == {REVERSE.format(z) for z in ("Z1", "Z2", "Z3", "ZP")}
        assert items[REVERSE.format("Z4")].not_required and items[REVERSE.format("Z4")].suggestion is None
        assert items[ZP_STATUS].category == "missing" and items[ZP_STATUS].suggestion is None
        assert suggestion_spec("zones[Z1].resistive_reach.phase_phase") is None
        assert suggestion_spec("transformers.voltage_base_v") is None

    def test_without_a_decision_the_item_stays_missing_and_blocking(self, model):
        review, items = _state(model)
        assert all(items[REVERSE.format(z)].blocking for z in Z123)
        assert review.readiness.status == "not_ready"


class TestAcceptance:
    def test_accepting_creates_an_effective_zero_with_suggestion_provenance(self, model):
        path = REVERSE.format("Z1")
        original = dict(model.iter_sourced())[path]
        effective = dict(apply_review(model, ReviewDecisions(suggested=_suggested("Z1"))).iter_sourced())[path]
        assert effective.value == 0.0 and effective.is_resolved
        p = effective.provenance
        assert p.status is MappingStatus.RESOLVED_MANUALLY and p.origin is ProvenanceOrigin.SESSION_REVIEW
        assert p.review.status is ReviewStatus.SUGGESTION_ACCEPTED
        assert p.review.original_status is MappingStatus.UNRESOLVED
        assert p.review.user_value_text == "0.00 Ω"
        assert p.cause == original.provenance.cause  # the original Missing cause is kept
        assert original.provenance.review is None and not original.is_resolved  # original untouched

    def test_the_category_stays_missing_and_the_origin_is_the_suggestion(self, model):
        _, items = _state(model, suggested=_suggested("Z1"))
        item = items[REVERSE.format("Z1")]
        assert item.category == "missing" and item.status == "unresolved"
        assert item.review_status == "resolved_manually" and item.resolution_origin == "suggestion"
        assert item.user_value_text == "0.00 Ω" and item.suggestion is None and item.resolution is not None

    def test_a_typed_zero_stays_distinguishable_from_the_accepted_suggestion(self, model):
        _, items = _state(model, manual={REVERSE.format("Z1"): 0}, suggested=_suggested("Z2"))
        assert items[REVERSE.format("Z1")].resolution_origin == "manual"
        assert items[REVERSE.format("Z2")].resolution_origin == "suggestion"
        assert items[REVERSE.format("Z1")].user_value_text == "0 Ω"
        assert items[REVERSE.format("Z2")].user_value_text == "0.00 Ω"

    def test_manual_entry_of_another_value_still_works(self, model):
        _, items = _state(model, manual={REVERSE.format("Z1"): 2.5})
        assert items[REVERSE.format("Z1")].resolution_origin == "manual"
        assert items[REVERSE.format("Z1")].user_value_text == "2.5 Ω"

    def test_readiness_is_re_evaluated_and_clearing_restores_the_blocker(self, model):
        decisions = {"manual": {ZP_STATUS: "disabled"}}
        blocked, _ = _state(model, **decisions)
        assert blocked.readiness.status == "not_ready" and blocked.blocking_count == 3
        cleared, items = _state(model, suggested=_suggested(*Z123), **decisions)
        assert cleared.engine.status == "ready" and cleared.blocking_count == 0
        assert cleared.readiness.status == "ready_after_confirmation"
        assert not any(items[REVERSE.format(z)].blocking for z in Z123)
        restored, items = _state(model, **decisions)  # "Clear" = dropping the decision
        assert restored.readiness.status == "not_ready" and restored.blocking_count == 3
        assert all(items[REVERSE.format(z)].category == "missing" and items[REVERSE.format(z)].suggestion for z in Z123)

    def test_all_decisions_together_reach_ready(self, model):
        review, _ = _state(model, suggested=_suggested(*Z123), manual={ZP_STATUS: "disabled"}, confirmed=_pending(model))
        assert review.readiness.status == "ready"


class TestRefusals:
    @pytest.mark.parametrize(
        "path",
        [
            ZP_STATUS,
            "zones[Z1].resistive_reach.phase_phase",
            "zones[Z1].reach",
            "transformers.voltage_base_v",
            "zones[ZZ].resistive_reach.reverse",
        ],
    )
    def test_no_suggestion_exists_for_any_other_item(self, model, path):
        with pytest.raises(ReviewDecisionError):
            apply_review(model, ReviewDecisions(suggested=frozenset({path})))

    def test_a_suggestion_cannot_share_an_item_with_another_decision(self, model):
        path = REVERSE.format("Z1")
        with pytest.raises(ReviewDecisionError):
            apply_review(model, ReviewDecisions(suggested=frozenset({path}), manual={path: 1.0}))


class TestEndpoint:
    def _context(self, client):
        r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
        return r.json()["review"]

    def test_the_upload_offers_the_suggestion_and_applies_nothing(self, client):
        review = self._context(client)
        items = {i["item_id"]: i for g in review["groups"] for i in g["items"] if i["item_id"]}
        item = items[REVERSE.format("Z1")]
        assert item["suggestion"]["value_text"] == "0.00 Ω" and item["value_text"] is None
        assert item["category"] == "missing" and item["resolution_origin"] is None

    def test_validate_accepts_a_suggestion_and_reports_its_origin(self, client):
        ctx = self._context(client)["validation_context"]
        body = {
            "validation_context": ctx,
            "manual": [{"item_id": ZP_STATUS, "value": "disabled"}],
            "suggested": [REVERSE.format(z) for z in Z123],
        }
        state = client.post(VALIDATE, json=body).json()
        assert state["engine"]["status"] == "ready" and state["blocking_count"] == 0
        items = {i["item_id"]: i for i in state["items"]}
        assert items[REVERSE.format("Z1")]["resolution_origin"] == "suggestion"
        assert items[REVERSE.format("Z1")]["category"] == "missing"
        assert items[REVERSE.format("Z1")]["user_value_text"] == "0.00 Ω"
        assert items[ZP_STATUS]["resolution_origin"] == "manual"

    def test_validate_refuses_a_suggestion_for_another_item(self, client):
        ctx = self._context(client)["validation_context"]
        r = client.post(VALIDATE, json={"validation_context": ctx, "suggested": [ZP_STATUS]})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_review"
