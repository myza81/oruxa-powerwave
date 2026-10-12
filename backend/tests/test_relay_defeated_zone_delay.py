"""Pre-Slice-9 (DEC-187): a distance zone with no established status and a 10.0 s operating
delay is interpreted as Disabled (Assumption). The rule is vendor-neutral, applies to
distance zones only, never overrides an established status and never lives in an OEM profile
or in the distance characteristic engine."""

from __future__ import annotations

import io
import pathlib
import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.domain.relay_import.canonical_codec import encode_model
from app.domain.relay_import.canonical_distance import (
    CanonicalDistanceProtectionModel,
    DistanceZone,
    RelayMetadata,
    SourceFormat,
    ZoneStatus,
)
from app.domain.relay_import.defeated_zone import DEFEATED_ZONE_REASON, infer_defeated_zones
from app.domain.relay_import.engine_adapter import adapt_to_engine, zone_active
from app.domain.relay_import.provenance import (
    MappingStatus,
    ProvenanceOrigin,
    Sourced,
    SourceRef,
    inferred,
    mapped,
    unresolved,
)
from app.domain.relay_import.review_state import ReviewDecisions
from app.main import create_app
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.services.relay_review_validation import validate_review
from tests.relay_p441_fixtures import make_doc
from tests.test_relay_import_upload import _p441_pdf
from tests.test_relay_review_state import REVERSE, UPLOAD, VALIDATE, ZP_STATUS

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
Z123 = ("Z1", "Z2", "Z3")


def _timer(seconds: float) -> Sourced:
    return mapped(
        seconds, sources=(SourceRef("t-1", "TX", "Timer"),), profile_id="acme-dist", profile_version="1",
        raw_value=str(seconds),
    )


def _explicit(value: ZoneStatus) -> Sourced:
    return mapped(value, sources=(SourceRef("s-1", "ST", "Status"),), profile_id="acme-dist", profile_version="1")


def _zone(zone_id: str, *, delay: float | None, status: Sourced | None = None, name: str | None = None) -> DistanceZone:
    return DistanceZone(
        zone_id=zone_id,
        name=name,
        status=status or unresolved(),
        common_timer_s=_timer(delay) if delay is not None else unresolved(),
    )


def _model(*zones: DistanceZone) -> CanonicalDistanceProtectionModel:
    return CanonicalDistanceProtectionModel(metadata=RelayMetadata(source_format=SourceFormat.PDF), zones=zones)


def _status(model: CanonicalDistanceProtectionModel, zone_id: str) -> Sourced:
    return model.zone(zone_id).status


def _items(review) -> dict:
    return {i.item_id: i for g in review.groups for i in g.items if i.item_id and i.primary}


class TestRule:
    def test_unknown_status_and_exactly_10_s_is_disabled_assumption(self):
        out = infer_defeated_zones(_model(_zone("Z4", delay=10.0)))
        st = _status(out, "Z4")
        assert st.value is ZoneStatus.DISABLED and zone_active(out.zone("Z4")) is False
        assert st.provenance.status is MappingStatus.INFERRED  # never Mapped
        assert st.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION
        assert st.provenance.notes == (DEFEATED_ZONE_REASON,) and not st.needs_confirmation

    def test_the_original_timer_and_its_provenance_are_preserved(self):
        before = _zone("Z4", delay=10.0)
        out = infer_defeated_zones(_model(before)).zone("Z4")
        assert out.common_timer_s == before.common_timer_s
        assert out.status.provenance.sources == before.common_timer_s.provenance.sources

    def test_the_rule_names_no_zone_and_no_manufacturer(self):
        zones = (_zone("ZP", delay=10.0), _zone("Z5", delay=10.0), _zone("X", delay=10.0, name="Overreach"))
        out = infer_defeated_zones(_model(*zones))
        assert all(_status(out, z.zone_id).value is ZoneStatus.DISABLED for z in zones)

    @pytest.mark.parametrize("delay", [9.9, 9.999, 10.001, 0.0, 3.0, None])
    def test_any_other_delay_leaves_the_status_unresolved(self, delay):
        out = infer_defeated_zones(_model(_zone("ZP", delay=delay)))
        assert not _status(out, "ZP").is_resolved and zone_active(out.zone("ZP")) is None

    def test_explicit_enabled_with_10_s_stays_enabled(self):
        zone = _zone("Z4", delay=10.0, status=_explicit(ZoneStatus.ENABLED))
        assert infer_defeated_zones(_model(zone)).zone("Z4").status.value is ZoneStatus.ENABLED

    @pytest.mark.parametrize("delay", [0.0, 3.0, 10.0])
    def test_explicit_disabled_stays_disabled_and_mapped(self, delay):
        out = infer_defeated_zones(_model(_zone("Z4", delay=delay, status=_explicit(ZoneStatus.DISABLED))))
        assert out.zone("Z4").status.provenance.status is MappingStatus.MAPPED

    def test_an_inferred_status_is_not_replaced(self):
        st = inferred(ZoneStatus.ENABLED, sources=(SourceRef("s-1"),), profile_id="p", profile_version="1")
        assert infer_defeated_zones(_model(_zone("Z1", delay=10.0, status=st))).zone("Z1").status is st

    def test_a_model_with_nothing_to_infer_is_returned_unchanged(self):
        model = _model(_zone("Z1", delay=3.0))
        assert infer_defeated_zones(model) is model

    def test_other_zones_with_other_delays_are_not_affected(self):
        out = infer_defeated_zones(_model(_zone("Z1", delay=0.0), _zone("ZP", delay=10.0), _zone("Z2", delay=0.4)))
        assert [_status(out, z).is_resolved for z in ("Z1", "ZP", "Z2")] == [False, True, False]


class TestNoOemOrEngineLogic:
    def test_no_oem_profile_contains_a_10_second_rule(self):
        offenders = [
            p.name
            for p in (APP / "relay_profiles").glob("*.py")
            if re.search(r"DEFEATED_ZONE|defeated_zone|[=<>]=? ?10(\.0)?\b", p.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    def test_only_the_relay_import_layer_references_the_rule(self):
        users = {
            p.relative_to(APP).as_posix()
            for p in APP.rglob("*.py")
            if "DEFEATED_ZONE_DELAY_S" in p.read_text(encoding="utf-8")
        }
        assert users == {"domain/relay_import/defeated_zone.py"}


class TestP441Sample:
    @pytest.fixture(scope="class")
    def raw(self):
        return MicomP441Profile().interpret(make_doc())

    @pytest.fixture(scope="class")
    def model(self, raw):
        return infer_defeated_zones(raw)

    def test_the_profile_itself_leaves_zone_p_unresolved(self, raw):
        assert not raw.zone("ZP").status.is_resolved  # the rule is not in the OEM profile

    def test_zone_p_with_a_10_s_delay_is_disabled_assumption(self, model):
        st = model.zone("ZP").status
        assert st.value is ZoneStatus.DISABLED and st.provenance.origin is ProvenanceOrigin.DEFAULT_ASSUMPTION
        assert st.provenance.status is MappingStatus.INFERRED and DEFEATED_ZONE_REASON in st.provenance.notes
        assert st.provenance.profile_id == "schneider-micom-p441"
        assert model.zone("ZP").common_timer_s.value == 10.0

    def test_other_zones_are_untouched(self, raw, model):
        for zid in ("Z1", "Z2", "Z3", "Z4"):
            assert model.zone(zid).status == raw.zone(zid).status

    def test_a_p441_zone_with_another_delay_stays_unresolved(self):
        doc = make_doc(overrides={"3023": ("tZp", "9.9", "0-10.0 s")})
        assert not infer_defeated_zones(MicomP441Profile().interpret(doc)).zone("ZP").status.is_resolved

    def test_zone_p_no_longer_blocks_and_its_missing_settings_are_not_required(self, model):
        review = validate_review(encode_model(model), ReviewDecisions(manual={REVERSE.format(z): 2.5 for z in Z123}))
        items = _items(review)
        assert not items[ZP_STATUS].blocking and items[ZP_STATUS].category == "assumption"
        assert items[REVERSE.format("ZP")].not_required and not items[REVERSE.format("ZP")].blocking
        assert items[REVERSE.format("ZP")].suggestion is None  # no 0.00 ohm offer for a disabled zone
        assert items["zones[ZP].reach"].value_text is not None  # extracted values are kept
        assert review.blocking_count == 0 and review.engine.status == "ready"

    def test_the_0_ohm_suggestion_is_still_offered_to_enabled_zones(self, model):
        items = _items(validate_review(encode_model(model), ReviewDecisions()))
        assert items[REVERSE.format("Z1")].suggestion is not None
        assert items[REVERSE.format("ZP")].suggestion is None

    def test_overriding_zone_p_to_enabled_restores_validation(self, model):
        manual = {REVERSE.format(z): 2.5 for z in Z123} | {ZP_STATUS: "enabled"}
        review = validate_review(encode_model(model), ReviewDecisions(manual=manual))
        items = _items(review)
        assert items[ZP_STATUS].review_status == "resolved_manually"
        assert not items["zones[ZP].reach"].not_required
        assert not items[REVERSE.format("ZP")].not_required  # required again, shown as missing
        assert review.engine.status == "not_ready" and review.readiness.status == "not_ready"
        # Slice 10: Zone P is held to the same rules as every zone -- it is blocked for the value it
        # lacks (its Left Resistive Reach), never because it is a fifth zone.
        assert any("Left Resistive Reach" in i.message and i.zone_ids == ("ZP",) for i in review.blocking_issues)
        assert not any("cannot be represented" in i.message for i in review.blocking_issues)

    def test_an_enabled_fifth_zone_is_refused_only_for_what_it_lacks(self, model):
        zp = replace(model.zone("ZP"), status=_explicit(ZoneStatus.ENABLED))
        enabled = replace(model, zones=tuple(zp if z.zone_id == "ZP" else z for z in model.zones))
        a = adapt_to_engine(enabled, engine_basis="secondary")
        assert not a.supported and {r.zone_id for r in a.reasons} <= {"ZP", "Z1", "Z2", "Z3"}
        assert not any("cannot be represented" in r.message for r in a.reasons)

    def test_canonical_model_keeps_all_five_zones_and_arbitrary_extras(self, model):
        assert [z.zone_id for z in model.zones] == ["Z1", "Z2", "Z3", "Z4", "ZP"]
        extra = tuple(DistanceZone(zone_id=f"Z{n}") for n in range(5, 9))
        assert len(replace(model, zones=model.zones + extra).zones) == 9


class TestAbsentZoneIsUnchanged:
    def test_a_relay_without_zone_p_keeps_the_absence_assumption(self):
        from tests.test_relay_inactive_zone_readiness import ZP_CODES

        model = infer_defeated_zones(MicomP441Profile().interpret(make_doc(drop=ZP_CODES)))
        assert model.zone("ZP").status.provenance.notes == ("Zone P not found in uploaded relay settings",)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


class TestApi:
    def test_the_upload_reports_zone_p_disabled_as_an_assumption(self, client):
        r = client.post(UPLOAD, files={"file": ("sheet.pdf", io.BytesIO(_p441_pdf()), "application/pdf")})
        assert r.status_code == 200
        review = r.json()["review"]
        zp = next(g for g in review["groups"] if g["id"] == "zone-ZP")
        assert zp["state_label"] == "Disabled"
        status = next(i for i in zp["items"] if i["item_id"] == ZP_STATUS)
        assert status["category"] == "assumption" and not status["blocking"]
        assert any("10.0 s operating delay" in n for n in status["notes"])
        ctx = review["validation_context"]
        out = client.post(VALIDATE, json={"validation_context": ctx, "manual": [{"item_id": ZP_STATUS, "value": "enabled"}]})
        assert out.status_code == 200 and out.json()["readiness"]["status"] == "not_ready"
