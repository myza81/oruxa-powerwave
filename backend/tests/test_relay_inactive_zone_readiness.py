"""Pre-Slice-9: settings of a disabled zone never block readiness, and an optional
Zone P that is genuinely absent from a reliably read relay source defaults to Disabled
as an Assumption (DEC-186).

A setting blocks only when an enabled function needs it, or when it decides whether a
function is enabled. Absent Zone P is kept apart from "Zone P found, state unknown".
"""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_codec import encode_model
from app.domain.relay_import.canonical_distance import ZoneStatus
from app.domain.relay_import.engine_adapter import adapt_to_engine, zone_active
from app.domain.relay_import.provenance import (
    MappingStatus,
    Provenance,
    ProvenanceOrigin,
    Sourced,
    UnresolvedCause,
    unresolved,
)
from app.domain.relay_import.review_state import ReviewDecisionError, ReviewDecisions, apply_review
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.services.relay_review_validation import validate_review
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_review_state import REVERSE, UPLOAD, VALIDATE, ZP_STATUS
from tests.relay_review_tokens import review_ref, validate_model

#: Every Zone P-specific code (the Z2/Zp tilt is shared with Zone 2 and stays).
ZP_CODES = ("301D", "301E", "301F", "3020", "3021", "3022", "3023")
Z123 = ("Z1", "Z2", "Z3")
UNREAD = unresolved(cause=UnresolvedCause.MISSING)


@pytest.fixture(scope="module")
def sample():
    """The owner-style P441 sample: Z4 defeated, Zone P present with no decoded state."""
    return MicomP441Profile().interpret(make_doc())


@pytest.fixture(scope="module")
def absent_zp():
    """The same sheet with every Zone P setting removed (a healthy source without Zone P)."""
    return MicomP441Profile().interpret(make_doc(drop=ZP_CODES))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _review(model, **decisions):
    review = validate_model(model, ReviewDecisions(**decisions))
    return review, {i.item_id: i for g in review.groups for i in g.items if i.item_id and i.primary}


def _with_zone(model, zone_id, **changes):
    return replace(model, zones=tuple(replace(z, **changes) if z.zone_id == zone_id else z for z in model.zones))


def _mapped_status(status: ZoneStatus) -> Sourced:
    return Sourced(status, Provenance(MappingStatus.MAPPED, origin=ProvenanceOrigin.MANUAL_ENTRY))


def _left_reaches(*zones):
    return {REVERSE.format(z): 2.5 for z in zones}


def _blocking(items):
    return {path for path, item in items.items() if item.blocking}


class TestDisabledZoneReadiness:
    def test_a_disabled_zone_with_a_missing_left_reach_does_not_block(self, sample):
        assert zone_active(sample.zone("Z4")) is False
        review, items = _review(sample, manual=_left_reaches(*Z123) | {ZP_STATUS: "disabled"})
        z4 = items[REVERSE.format("Z4")]
        # still visible, still Missing, but not a blocker
        assert z4.category == "missing" and z4.review_status == "unresolved"
        assert z4.not_required and not z4.blocking
        assert z4.not_required_reason == "Not required while zone is disabled"
        assert review.blocking_count == 0 and review.engine.status == "ready"

    def test_a_disabled_zone_with_several_missing_fields_does_not_block(self, sample):
        gutted = _with_zone(
            sample, "Z4", reach=UNREAD, direction=UNREAD, common_timer_s=UNREAD,
            characteristic=replace(sample.zone("Z4").characteristic, type=UNREAD),
            resistive_reach=replace(sample.zone("Z4").resistive_reach, phase_phase=UNREAD, phase_earth=UNREAD),
        )
        review, items = _review(gutted, manual=_left_reaches(*Z123) | {ZP_STATUS: "disabled"})
        for field in ("reach", "direction", "common_timer_s", "characteristic.type", "resistive_reach.phase_phase"):
            item = items[f"zones[Z4].{field}"]
            assert item.review_status == "unresolved" and item.not_required and not item.blocking, field
        assert review.blocking_count == 0 and review.engine.status == "ready"
        assert review.not_required_count >= 6

    def test_an_enabled_zone_with_the_same_missing_fields_blocks(self, sample):
        gutted = _with_zone(
            sample, "Z2", reach=UNREAD, common_timer_s=UNREAD,
            resistive_reach=replace(sample.zone("Z2").resistive_reach, phase_phase=UNREAD),
        )
        review, items = _review(gutted, manual={ZP_STATUS: "disabled"})
        # the adapter reports the first thing an enabled zone lacks; none is waved through
        assert items["zones[Z2].reach"].blocking
        for field in ("reach", "common_timer_s", "resistive_reach.phase_phase", "resistive_reach.reverse"):
            assert not items[f"zones[Z2].{field}"].not_required, field
        assert review.engine.status == "not_ready" and review.blocking_count > 0

    def test_an_unknown_zone_state_blocks_through_the_state_itself(self, sample):
        assert zone_active(sample.zone("ZP")) is None
        review, items = _review(sample, manual=_left_reaches(*Z123))
        assert items[ZP_STATUS].blocking and not items[ZP_STATUS].not_required
        # the zone's other (present) values are not hidden behind the unknown state
        assert not items["zones[ZP].reach"].not_required
        assert review.readiness.status == "not_ready"

    def test_the_status_of_a_zone_is_never_not_required(self, sample):
        _, items = _review(_with_zone(sample, "Z4", status=UNREAD))
        assert not items["zones[Z4].status"].not_required and items["zones[Z4].status"].blocking

    def test_a_value_an_enabled_function_needs_still_blocks_when_a_disabled_zone_shares_it(self):
        """Zones 3 and 4 are fed by one pair of resistive reaches in the P441 sheet. Z4 is
        disabled, Z3 enabled: the shared value is missing for both, and only Z3 -- which the
        enabled function needs -- blocks. Decided by canonical dependency, not by section."""
        model = MicomP441Profile().interpret(make_doc(drop=("3019",)))
        _, items = _review(model, manual={ZP_STATUS: "disabled"})
        z3, z4 = "zones[{}].resistive_reach.phase_phase".format("Z3"), "zones[{}].resistive_reach.phase_phase".format("Z4")
        assert items[z3].blocking and not items[z3].not_required
        assert items[z4].not_required and not items[z4].blocking

    def test_a_blocking_path_is_never_marked_not_required(self, sample):
        """Even inside a disabled zone's group, a path the adapter reports as a dependency blocks."""
        from app.services import relay_extraction_review as svc

        builder = svc._Builder(
            make_doc(), frozenset({"zones[Z4].reach"}), None, frozenset({"Z4"})
        )
        assert not builder._not_required("zones[Z4].reach", UNREAD)
        assert builder._not_required("zones[Z4].common_timer_s", UNREAD)


class TestSuggestionInteraction:
    def test_no_suggestion_is_offered_for_a_disabled_zone(self, sample):
        _, items = _review(sample)
        z4 = items[REVERSE.format("Z4")]
        assert z4.suggestion is None and z4.not_required
        # an enabled zone still gets it
        assert items[REVERSE.format("Z1")].suggestion.value_text == "0.00 Ω"

    def test_a_suggestion_cannot_be_used_to_clear_a_disabled_zone(self, sample):
        with pytest.raises(ReviewDecisionError, match="not required"):
            apply_review(sample, ReviewDecisions(suggested=frozenset({REVERSE.format("Z4")})))

    def test_the_suggestion_returns_where_a_left_reach_is_required(self, sample):
        """Resolving Zone P as enabled does not make Z4 required, and Z1-3 keep the offer."""
        _, items = _review(sample, manual={ZP_STATUS: "disabled"})
        assert all(items[REVERSE.format(z)].suggestion for z in Z123)
        assert items[REVERSE.format("Z4")].suggestion is None


class TestZonePAbsent:
    def test_an_absent_zone_p_defaults_to_disabled(self, absent_zp):
        zp = absent_zp.zone("ZP")
        assert zp.status.value is ZoneStatus.DISABLED
        assert zone_active(zp) is False

    def test_the_default_is_an_assumption_not_mapped(self, absent_zp):
        p = absent_zp.zone("ZP").status.provenance
        assert p.status is MappingStatus.INFERRED and p.status is not MappingStatus.MAPPED
        assert p.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION
        assert p.notes == ("Zone P not found in uploaded relay settings",)
        assert p.sources == ()  # nothing in the file said it
        _, items = _review(absent_zp)
        status = items[ZP_STATUS]
        assert status.category == "assumption" and status.status == "inferred"
        assert status.review_status == "assumed"
        assert status.value_text == "Disabled"  # not "Defeated": the relay file did not say so

    def test_the_default_is_non_blocking_and_needs_no_confirmation(self, absent_zp):
        review, items = _review(absent_zp, manual=_left_reaches(*Z123))
        assert not items[ZP_STATUS].blocking
        assert ZP_STATUS not in {i for i, item in items.items() if item.review_status == "to_confirm"}
        assert items[ZP_STATUS].resolution is not None  # the user may override the assumption
        assert review.blocking_count == 0 and review.engine.status == "ready"
        pending = frozenset(i for i, item in items.items() if item.review_status == "to_confirm")
        done, _ = _review(absent_zp, manual=_left_reaches(*Z123), confirmed=pending)
        assert done.readiness.status == "ready"  # without ever confirming Zone P

    def test_the_review_group_explains_the_assumption(self, absent_zp):
        review, _ = _review(absent_zp)
        group = next(g for g in review.groups if g.id == "zone-ZP")
        assert group.state_label == "Disabled" and group.state_review_status == "assumed"
        assert group.state_note == (
            "Zone P was not found in the uploaded relay settings. This optional zone is assumed to be disabled."
        )
        # the findings are preserved (Missing) but none is a blocker
        zp_items = [i for i in group.items if i.item_id and i.primary and i.item_id != ZP_STATUS]
        assert zp_items and all(i.not_required and not i.blocking for i in zp_items if i.review_status == "unresolved")

    def test_an_explicit_state_wins_no_assumption_is_added(self, sample):
        assert sample.zone("Z4").status.provenance.origin is ProvenanceOrigin.RELAY_DOCUMENT
        assert all(
            s.provenance.origin is not ProvenanceOrigin.DEFAULT_ASSUMPTION
            for path, s in sample.iter_sourced()
        )

    def test_the_assumption_survives_the_review_round_trip(self, absent_zp):
        _, items = _review(absent_zp, confirmed=frozenset({ZP_STATUS}))
        assert items[ZP_STATUS].category == "assumption"  # a confirmation never rewrites the category


class TestZonePObservedOrUnreliable:
    def test_zone_p_settings_with_unknown_state_are_not_defaulted(self, sample):
        zp = sample.zone("ZP")
        assert not zp.status.is_resolved and zp.status.provenance.cause is UnresolvedCause.MISSING
        _, items = _review(sample)
        assert items[ZP_STATUS].category == "missing" and items[ZP_STATUS].blocking
        assert items[ZP_STATUS].review_status == "unresolved"

    @pytest.mark.parametrize("keep", ZP_CODES)
    def test_any_single_observed_zone_p_row_means_it_is_not_absent(self, keep):
        kept = MicomP441Profile().interpret(make_doc(drop=tuple(c for c in ZP_CODES if c != keep)))
        assert not kept.zone("ZP").status.is_resolved

    def test_a_textual_mention_of_zone_p_means_it_is_not_absent(self):
        model = MicomP441Profile().interpret(
            make_doc(drop=ZP_CODES, extra=((None, "Zone P timer set to 1s", None, None),))
        )
        assert not model.zone("ZP").status.is_resolved

    def test_an_unreadable_distance_function_does_not_establish_absence(self):
        model = MicomP441Profile().interpret(make_doc(drop=(*ZP_CODES, "090D")))
        assert not model.zone("ZP").status.is_resolved

    def test_missing_neighbouring_zones_do_not_establish_absence(self):
        """If the zone tables themselves were not read, a missing Zone P proves nothing."""
        model = MicomP441Profile().interpret(make_doc(drop=(*ZP_CODES, "3011")))
        assert not model.zone("ZP").status.is_resolved

    def test_an_extraction_warning_does_not_establish_absence(self):
        doc = replace(make_doc(drop=ZP_CODES), warnings=("page 4 could not be read",))
        assert not MicomP441Profile().interpret(doc).zone("ZP").status.is_resolved

    def test_an_empty_or_failed_extraction_does_not_establish_absence(self):
        empty = replace(make_doc(), settings=())
        assert not MicomP441Profile().interpret(empty).zone("ZP").status.is_resolved

    def test_a_conflicting_zone_row_does_not_establish_absence(self):
        model = MicomP441Profile().interpret(
            make_doc(drop=ZP_CODES, extra=(("3011", "Z2", "9.99", "0.001-500 /I1"),))  # duplicate, differing value
        )
        assert not model.zone("ZP").status.is_resolved


class TestZonePExplicitState:
    def test_an_explicitly_disabled_zone_p_with_missing_geometry_does_not_block(self):
        doc = make_doc(drop=("3020", "3022", "3021", "3023", "301E", "301F"))  # direction row only
        model = MicomP441Profile().interpret(doc)
        assert not model.zone("ZP").status.is_resolved  # observed, so not defaulted
        review, items = _review(model, manual=_left_reaches(*Z123) | {ZP_STATUS: "disabled"})
        assert items["zones[ZP].reach"].review_status == "unresolved" and items["zones[ZP].reach"].not_required
        assert not items["zones[ZP].reach"].blocking and not items[ZP_STATUS].blocking
        assert review.blocking_count == 0 and review.engine.status == "ready"

    def test_an_explicitly_enabled_zone_p_is_validated_like_any_zone(self, sample):
        review, items = _review(sample, manual=_left_reaches(*Z123) | {ZP_STATUS: "enabled"})
        assert review.engine.status == "not_ready" and review.readiness.status == "not_ready"
        # blocked for the value it lacks, never for being a fifth zone
        assert any("Left Resistive Reach" in issue.message and issue.zone_ids == ("ZP",) for issue in review.blocking_issues)
        assert not any("cannot be represented" in issue.message for issue in review.blocking_issues)
        # the zone is required, not waved through
        assert not items["zones[ZP].reach"].not_required

    def test_an_enabled_zone_p_with_its_left_reach_resolved_is_applicable(self, sample):
        """Slice 10: nothing but missing values stands between an enabled fifth zone and Apply."""
        review, _ = _review(sample, manual=_left_reaches(*Z123, "ZP") | {ZP_STATUS: "enabled"})
        assert review.engine.status == "ready" and review.blocking_count == 0

    def test_an_explicit_zone_p_state_from_the_file_is_not_replaced_by_the_default(self, sample):
        enabled = _with_zone(sample, "ZP", status=_mapped_status(ZoneStatus.ENABLED))
        assert zone_active(enabled.zone("ZP")) is True
        a = adapt_to_engine(enabled, engine_basis="secondary")
        assert not a.supported and not any("cannot be represented" in r.message for r in a.reasons)

    def test_the_adapter_still_treats_none_and_zero_left_reach_as_before(self, sample):
        """DEC-185 engine rule (5102cc7) is untouched: None = not configured, 0.0 = valid."""
        review, _ = _review(sample, manual={ZP_STATUS: "disabled"} | _left_reaches("Z2", "Z3"), suggested=frozenset({REVERSE.format("Z1")}))
        assert review.blocking_count == 0


class TestApi:
    def _upload(self, client, **kwargs):
        r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf(**kwargs)), "application/pdf")})
        assert r.status_code == 200, r.text
        return r.json()["review"]

    def test_the_upload_marks_the_defeated_zone_values_not_required(self, client):
        review = self._upload(client)
        items = {i["item_id"]: i for g in review["groups"] for i in g["items"] if i["item_id"]}
        z4 = items[REVERSE.format("Z4")]
        assert z4["category"] == "missing" and z4["not_required"] and not z4["blocking"] and z4["suggestion"] is None
        assert z4["not_required_reason"] == "Not required while zone is disabled"
        assert review["not_required_count"] == 2  # Z4 (defeated) and Zone P (10 s delay)
        assert not items[ZP_STATUS]["blocking"]

    def test_validate_reports_the_flag_and_refuses_a_suggestion_for_it(self, client):
        ctx = review_ref(self._upload(client))
        ok = client.post(VALIDATE, json={**ctx}).json()
        z4 = next(i for i in ok["items"] if i["item_id"] == REVERSE.format("Z4"))
        assert z4["not_required"] and not z4["blocking"]
        bad = client.post(VALIDATE, json={**ctx, "suggested": [REVERSE.format("Z4")]})
        assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_review"

    def test_a_manually_disabled_zone_p_makes_its_values_not_required(self, client):
        ctx = review_ref(self._upload(client))
        state = client.post(
            VALIDATE, json={**ctx, "manual": [{"item_id": ZP_STATUS, "value": "disabled"}]}
        ).json()
        zp = {i["item_id"]: i for i in state["items"]}
        assert zp[ZP_STATUS]["review_status"] == "resolved_manually" and not zp[ZP_STATUS]["not_required"]
        assert zp[REVERSE.format("ZP")]["not_required"] and zp[REVERSE.format("ZP")]["suggestion"] is None
