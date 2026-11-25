"""NF-1 -- the recording-level nominal-frequency authority: resolver, registry, API and lifecycle.

Foundation only. No engineering consumer reads the new authority yet; `TestNoConsumerChange` freezes that.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import io
import threading
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import nominal_frequency as nf
from app.domain.metadata import DEFAULT_NOMINAL_FREQUENCY_HZ
from app.main import create_app
from app.services.nominal_frequency_registry import NominalFrequencyRegistry

from tests import comtrade_frequency_scenarios as scn

APP_DIR = Path(__file__).resolve().parents[1] / "app"
BEN_FIXTURE = Path(__file__).parent / "fixtures" / "ben" / "synthetic_fast.ben"
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

COMTRADE = {"source_format": "COMTRADE"}
ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}
CSV_ASSUMED = {"source_format": "CSV", "nominal_frequency_assumed": True}
BEN_SUPPLIED = {"source_format": "BEN", "nominal_frequency_assumed": False}
BEN_ASSUMED = {"source_format": "BEN", "nominal_frequency_assumed": True}

UNUSABLE = [0.0, -0.0, -50.0, float("nan"), float("inf"), float("-inf"), 0.5, 0.999, 1000.001, 1001.0, 1e308, 1e-9]


# ---------------------------------------------------------------------------------------------------- the resolver
class TestAutoResolution:
    @pytest.mark.parametrize("imported,prov,expected_hz,expected_origin", [
        (50.0, None, 50.0, nf.ORIGIN_RECORDING_METADATA),
        (60.0, COMTRADE, 60.0, nf.ORIGIN_RECORDING_METADATA),
        (25.0, COMTRADE, 25.0, nf.ORIGIN_RECORDING_METADATA),
        (16.7, COMTRADE, 16.7, nf.ORIGIN_RECORDING_METADATA),
        (400.0, COMTRADE, 400.0, nf.ORIGIN_RECORDING_METADATA),
        (1.0, COMTRADE, 1.0, nf.ORIGIN_RECORDING_METADATA),
        (1000.0, COMTRADE, 1000.0, nf.ORIGIN_RECORDING_METADATA),
        (50, COMTRADE, 50.0, nf.ORIGIN_RECORDING_METADATA),
        # the importer substituted the default
        (50.0, ASSUMED, 50.0, nf.ORIGIN_ASSUMED_DEFAULT),
        (50.0, CSV_ASSUMED, 50.0, nf.ORIGIN_ASSUMED_DEFAULT),
        (50.0, BEN_ASSUMED, 50.0, nf.ORIGIN_ASSUMED_DEFAULT),
        # metadata unavailable altogether -> the 50 Hz default
        (None, None, 50.0, nf.ORIGIN_ASSUMED_DEFAULT),
        (None, COMTRADE, 50.0, nf.ORIGIN_ASSUMED_DEFAULT),
        # BEN: the format declares none, the upload supplied it -- part of the automatic baseline, accurate origin
        (60.0, BEN_SUPPLIED, 60.0, nf.ORIGIN_IMPORT_SUPPLIED),
        (50.0, BEN_SUPPLIED, 50.0, nf.ORIGIN_IMPORT_SUPPLIED),
    ])
    def test_auto_value_and_origin(self, imported, prov, expected_hz, expected_origin):
        r = nf.resolve_nominal_frequency(imported, prov)
        assert (r.effective_hz, r.origin, r.mode) == (expected_hz, expected_origin, nf.MODE_AUTO)
        assert (r.auto_hz, r.auto_origin, r.manual_hz) == (expected_hz, expected_origin, None)
        assert r.usable

    def test_the_default_is_the_documented_50_hz(self):
        assert DEFAULT_NOMINAL_FREQUENCY_HZ == 50.0
        assert nf.resolve_nominal_frequency(None, None).effective_hz == 50.0

    @pytest.mark.parametrize("imported", UNUSABLE + [True, False, "50", [50]])
    def test_a_declared_but_invalid_value_is_preserved_and_not_usable(self, imported):
        r = nf.resolve_nominal_frequency(imported, COMTRADE)
        assert r.effective_hz is None and not r.usable
        assert (r.origin, r.mode, r.auto_hz, r.auto_origin) == (nf.ORIGIN_UNUSABLE, nf.MODE_AUTO, None, nf.ORIGIN_UNUSABLE)
        if isinstance(imported, float):
            assert repr(r.imported_hz) == repr(imported)         # preserved exactly, including nan/inf/-0.0

    @pytest.mark.parametrize("value", [1.0, 1000.0, 50.0, 0.1 + 0.9, 999.999999])
    def test_the_existing_1_to_1000_predicate_is_the_boundary(self, value):
        assert nf.valid_nominal_frequency(value)
        assert nf.resolve_nominal_frequency(value, COMTRADE).usable

    @pytest.mark.parametrize("value", UNUSABLE + [True, None, "60"])
    def test_the_predicate_rejects(self, value):
        assert not nf.valid_nominal_frequency(value)

    def test_the_predicate_is_the_existing_one(self):
        from app.domain.calculated_channel import nominal_frequency_valid
        for value in [0, 1, 50, 60, 1000, 1001, float("nan"), True]:
            assert nf.valid_nominal_frequency(value) == nominal_frequency_valid(value)


class TestManualOverride:
    @pytest.mark.parametrize("imported,prov", [
        (50.0, COMTRADE), (60.0, COMTRADE), (50.0, ASSUMED), (50.0, BEN_SUPPLIED), (None, None), (0.0, COMTRADE),
        (float("nan"), COMTRADE), (1001.0, COMTRADE),
    ])
    @pytest.mark.parametrize("manual", [1.0, 50.0, 60.0, 49.0, 1000.0])
    def test_a_valid_manual_value_wins_and_leaves_auto_untouched(self, imported, prov, manual):
        base = nf.resolve_nominal_frequency(imported, prov)
        r = nf.resolve_nominal_frequency(imported, prov, manual, revision=3)
        assert (r.effective_hz, r.origin, r.mode, r.manual_hz, r.revision) == (manual, nf.ORIGIN_MANUAL, nf.MODE_MANUAL, manual, 3)
        # Auto never depends on the manual value, and returning to Auto restores it exactly
        assert (r.auto_hz, r.auto_origin) == (base.auto_hz, base.auto_origin)
        assert repr(r.imported_hz) == repr(base.imported_hz)
        assert nf.resolve_nominal_frequency(imported, prov, None, revision=4).effective_hz == base.effective_hz

    def test_a_manual_value_equal_to_auto_is_still_manual(self):
        r = nf.resolve_nominal_frequency(50.0, COMTRADE, 50.0)
        assert (r.mode, r.origin, r.manual_hz, r.effective_hz) == (nf.MODE_MANUAL, nf.ORIGIN_MANUAL, 50.0, 50.0)

    def test_a_manual_value_corrects_an_unusable_declared_one(self):
        r = nf.resolve_nominal_frequency(0.0, COMTRADE, 50.0)
        assert (r.effective_hz, r.origin, r.auto_hz, r.auto_origin) == (50.0, nf.ORIGIN_MANUAL, None, nf.ORIGIN_UNUSABLE)

    @pytest.mark.parametrize("manual", UNUSABLE + [True])
    def test_an_invalid_stored_manual_value_is_never_trusted(self, manual):
        r = nf.resolve_nominal_frequency(60.0, COMTRADE, manual)
        assert (r.effective_hz, r.mode, r.origin) == (60.0, nf.MODE_AUTO, nf.ORIGIN_RECORDING_METADATA)

    def test_the_resolver_changes_none_of_its_inputs(self):
        prov = copy.deepcopy(ASSUMED)
        before = copy.deepcopy(prov)
        r = nf.resolve_nominal_frequency(50.0, prov, 60.0)
        assert prov == before
        with pytest.raises(Exception):
            r.effective_hz = 1.0                                   # frozen


# ---------------------------------------------------------------------------------------------------- the registry
class TestRegistry:
    def test_set_get_clear_and_revision(self):
        reg = NominalFrequencyRegistry()
        assert reg.snapshot("w", "s") == (None, 0)
        assert reg.set("w", "s", 60.0, NOW) is True
        m, rev = reg.snapshot("w", "s")
        assert (m.value_hz, m.set_at, rev) == (60.0, NOW, 1)
        assert reg.set("w", "s", 60.0, NOW) is False                # identical: nothing changed
        assert reg.revision("w", "s") == 1
        assert reg.set("w", "s", 50.0, NOW) is True and reg.revision("w", "s") == 2
        assert reg.clear("w", "s") is True and reg.revision("w", "s") == 3
        assert reg.clear("w", "s") is False and reg.revision("w", "s") == 3   # idempotent, no revision change
        assert reg.set("w", "s", 50.0, NOW) is True and reg.revision("w", "s") == 4

    def test_scoping_is_workspace_and_recording(self):
        reg = NominalFrequencyRegistry()
        reg.set("w1", "s1", 60.0, NOW)
        assert reg.get("w1", "s2") is None and reg.get("w2", "s1") is None
        reg.set("w1", "s2", 25.0, NOW)
        reg.set("w2", "s1", 16.7, NOW)
        assert [reg.get(w, s).value_hz for w, s in [("w1", "s1"), ("w1", "s2"), ("w2", "s1")]] == [60.0, 25.0, 16.7]
        assert reg.count() == 3

    def test_remove_source_and_workspace(self):
        reg = NominalFrequencyRegistry()
        for w, s, v in [("w1", "s1", 60.0), ("w1", "s2", 25.0), ("w2", "s1", 16.7)]:
            reg.set(w, s, v, NOW)
        assert reg.remove_source("w1", "s1") is True and reg.remove_source("w1", "s1") is False
        assert reg.snapshot("w1", "s1") == (None, 0)
        assert reg.get("w1", "s2").value_hz == 25.0 and reg.get("w2", "s1").value_hz == 16.7
        assert reg.remove_workspace("w1") == 1 and reg.remove_workspace("w1") == 0
        assert reg.count() == 1 and reg.get("w2", "s1").value_hz == 16.7
        assert reg.remove_workspace("nope") == 0

    @pytest.mark.parametrize("bad", UNUSABLE + [True, False, None, "60", [60]])
    def test_the_registry_itself_refuses_an_invalid_value(self, bad):
        reg = NominalFrequencyRegistry()
        with pytest.raises(ValueError):
            reg.set("w", "s", bad, NOW)
        assert reg.snapshot("w", "s") == (None, 0)                 # nothing stored, no revision moved
        reg.set("w", "s", 60.0, NOW)
        with pytest.raises(ValueError):
            reg.set("w", "s", float("nan"), NOW)
        assert reg.snapshot("w", "s")[0].value_hz == 60.0 and reg.revision("w", "s") == 1

    @pytest.mark.parametrize("bad", UNUSABLE + [True])
    def test_the_service_refuses_an_invalid_value_before_the_registry(self, client, bad):
        from app.services.errors import InvalidNominalFrequencyError
        from app.services.nominal_frequency_service import set_manual_nominal_frequency
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        registry = client.app.state.nominal_frequency_registry
        with pytest.raises(InvalidNominalFrequencyError):
            set_manual_nominal_frequency(
                ws, sid, bad, source_registry=client.app.state.workspace_registry, registry=registry,
                manual_override_enabled=True)
        assert registry.snapshot(ws, sid) == (None, 0)

    def test_records_are_frozen(self):
        reg = NominalFrequencyRegistry()
        reg.set("w", "s", 60.0, NOW)
        with pytest.raises(Exception):
            reg.get("w", "s").value_hz = 1.0

    def test_concurrent_writers_keep_one_consistent_state(self):
        reg = NominalFrequencyRegistry()
        values = [float(v) for v in range(10, 74)]
        threads = [threading.Thread(target=reg.set, args=("w", "s", v, NOW)) for v in values]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        manual, revision = reg.snapshot("w", "s")
        assert manual.value_hz in values and revision == len(values)   # every distinct value was a change


# ---------------------------------------------------------------------------------------------------- the API
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path_factory.mktemp("nf1")),
        cors_origins=("http://localhost:8101",), database_url=None, max_event_upload_size_mb=100,
        git_sha="local", version="local",
        nominal_frequency_manual_override_enabled=True,    # NF-3B (O-1): NF-1 exercises Manual mode, so the gate is opened explicitly
    )
    with TestClient(create_app(settings), raise_server_exceptions=True) as c:
        yield c


_COUNTER = iter(range(10_000))


def _ws() -> str:
    return f"ws-nf1-{next(_COUNTER)}"


def _upload_comtrade(client, ws: str, variant: str) -> str:
    text = scn.build_variants()[variant]
    files = {"cfg_file": ("e.cfg", text.encode("latin-1"), "application/octet-stream"),
             "dat_file": ("e.dat", scn._DAT.encode(), "application/octet-stream")}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        response = client.post(f"/api/v1/workspaces/{ws}/sources", files=files)
    assert response.status_code in (200, 201), response.text
    return response.json()["source_id"]


def _url(ws: str, sid: str) -> str:
    return f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency"


def _put(client, ws, sid, body):
    return client.put(_url(ws, sid), json=body)


class TestApiAuto:
    @pytest.mark.parametrize("variant,hz,origin", [
        ("declared_50", 50.0, "recording_metadata"),
        ("declared_60", 60.0, "recording_metadata"),
        ("declared_25", 25.0, "recording_metadata"),
        ("declared_1000", 1000.0, "recording_metadata"),
        ("unparseable_text", 50.0, "assumed_default"),
        ("unparseable_empty", 50.0, "assumed_default"),
        ("rev1991_unparseable", 50.0, "assumed_default"),
        ("rev2013_declared_60", 60.0, "recording_metadata"),
    ])
    def test_get_reports_the_automatic_value(self, client, variant, hz, origin):
        ws = _ws()
        sid = _upload_comtrade(client, ws, variant)
        body = client.get(_url(ws, sid)).json()
        assert (body["mode"], body["effective_hz"], body["origin"], body["usable"]) == ("auto", hz, origin, True)
        assert (body["auto_hz"], body["auto_origin"], body["manual_hz"], body["revision"]) == (hz, origin, None, 0)
        assert body["source_id"] == sid

    @pytest.mark.parametrize("variant,text", [
        ("declared_zero", "0.0"), ("declared_negative_50", "-50.0"), ("declared_nan", "nan"), ("declared_inf", "inf"),
        ("declared_negative_inf", "-inf"), ("declared_out_of_range_1001", "1001.0"), ("declared_out_of_range_0_5", "0.5"),
        ("declared_overflow_1e999", "inf"),
    ])
    def test_an_invalid_declared_value_is_preserved_unusable_and_never_a_500(self, client, variant, text):
        ws = _ws()
        sid = _upload_comtrade(client, ws, variant)
        response = client.get(_url(ws, sid))
        assert response.status_code == 200
        body = response.json()
        assert (body["mode"], body["usable"], body["effective_hz"], body["origin"]) == ("auto", False, None, "unusable")
        assert (body["auto_hz"], body["auto_origin"]) == (None, "unusable")
        assert body["imported_text"] == text                      # the declared value stays visible, unaltered
        assert (body["imported_hz"] is None) == (text in ("nan", "inf", "-inf"))

    def test_a_manual_correction_makes_an_unusable_recording_usable_and_reset_restores_it(self, client):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_zero")
        fixed = _put(client, ws, sid, {"mode": "manual", "value_hz": 50}).json()
        assert (fixed["effective_hz"], fixed["origin"], fixed["usable"], fixed["auto_origin"]) == (50.0, "manual", True, "unusable")
        assert fixed["imported_text"] == "0.0"
        back = _put(client, ws, sid, {"mode": "auto"}).json()
        assert (back["usable"], back["effective_hz"], back["origin"], back["mode"]) == (False, None, "unusable", "auto")

    def test_ben_upload_value_is_import_supplied_and_default_is_assumed(self, client):
        ws = _ws()
        data = BEN_FIXTURE.read_bytes()
        supplied = client.post(f"/api/v1/workspaces/{ws}/sources", data={"nominal_frequency_hz": "60"},
                               files={"ben_file": ("a.ben", io.BytesIO(data), "application/octet-stream")})
        assert supplied.status_code in (200, 201), supplied.text
        body = client.get(_url(ws, supplied.json()["source_id"])).json()
        assert (body["effective_hz"], body["origin"], body["mode"]) == (60.0, "import_supplied", "auto")
        plain = client.post(f"/api/v1/workspaces/{ws}/sources",
                            files={"ben_file": ("b.ben", io.BytesIO(data), "application/octet-stream")})
        body = client.get(_url(ws, plain.json()["source_id"])).json()
        assert (body["effective_hz"], body["origin"]) == (50.0, "assumed_default")


class TestApiManual:
    def test_set_change_reset_cycle_and_revisions(self, client):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        r = _put(client, ws, sid, {"mode": "manual", "value_hz": 60})
        assert r.status_code == 200
        b = r.json()
        assert (b["mode"], b["effective_hz"], b["origin"], b["manual_hz"], b["revision"]) == ("manual", 60.0, "manual", 60.0, 1)
        assert (b["imported_hz"], b["auto_hz"], b["auto_origin"]) == (50.0, 50.0, "recording_metadata")
        assert client.get(_url(ws, sid)).json() == b
        assert _put(client, ws, sid, {"mode": "manual", "value_hz": 60.0}).json()["revision"] == 1   # identical: no change
        assert _put(client, ws, sid, {"mode": "manual", "value_hz": 59.5}).json()["revision"] == 2
        back = _put(client, ws, sid, {"mode": "auto"}).json()
        assert (back["mode"], back["effective_hz"], back["origin"], back["manual_hz"], back["revision"]) == ("auto", 50.0, "recording_metadata", None, 3)
        assert _put(client, ws, sid, {"mode": "auto"}).json()["revision"] == 3                        # idempotent

    def test_a_manual_value_equal_to_auto_is_stored(self, client):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        b = _put(client, ws, sid, {"mode": "manual", "value_hz": 50}).json()
        assert (b["mode"], b["origin"], b["manual_hz"], b["revision"]) == ("manual", "manual", 50.0, 1)

    @pytest.mark.parametrize("raw", [
        '{"mode":"manual","value_hz":0}', '{"mode":"manual","value_hz":-1}', '{"mode":"manual","value_hz":0.5}',
        '{"mode":"manual","value_hz":1001}', '{"mode":"manual","value_hz":1e999}', '{"mode":"manual","value_hz":NaN}',
        '{"mode":"manual","value_hz":Infinity}', '{"mode":"manual","value_hz":-Infinity}',
        '{"mode":"manual"}', '{"mode":"manual","value_hz":null}', '{"mode":"auto","value_hz":50}',
    ])
    def test_invalid_requests_are_refused_with_the_existing_code_and_store_nothing(self, client, raw):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        response = client.put(_url(ws, sid), content=raw, headers={"content-type": "application/json"})
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["code"] == "invalid_nominal_frequency"
        after = client.get(_url(ws, sid)).json()
        assert (after["mode"], after["revision"], after["manual_hz"]) == ("auto", 0, None)

    @pytest.mark.parametrize("raw", [
        '{"mode":"manual","value_hz":"60"}', '{"mode":"manual","value_hz":true}', '{"mode":"manual","value_hz":[60]}',
        '{"mode":"sometimes"}', '{"mode":"manual","value_hz":60,"extra":1}', '{}', 'not json',
    ])
    def test_malformed_requests_are_422_never_500(self, client, raw):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        response = client.put(_url(ws, sid), content=raw, headers={"content-type": "application/json"})
        assert response.status_code == 422, response.text
        assert client.get(_url(ws, sid)).json()["revision"] == 0

    def test_unknown_recording_is_404_for_get_and_put(self, client):
        ws = _ws()
        for response in (client.get(_url(ws, "nope")), _put(client, ws, "nope", {"mode": "auto"}),
                         _put(client, ws, "nope", {"mode": "manual", "value_hz": 60})):
            assert response.status_code == 404
            assert response.json()["detail"]["code"] == "source_not_found"

    def test_recordings_and_workspaces_are_independent(self, client):
        ws1, ws2 = _ws(), _ws()
        a, b = _upload_comtrade(client, ws1, "declared_50"), _upload_comtrade(client, ws1, "declared_60")
        c = _upload_comtrade(client, ws2, "declared_50")
        _put(client, ws1, a, {"mode": "manual", "value_hz": 25})
        assert client.get(_url(ws1, a)).json()["effective_hz"] == 25.0
        assert client.get(_url(ws1, b)).json()["effective_hz"] == 60.0
        assert client.get(_url(ws2, c)).json()["effective_hz"] == 50.0
        # the same source id asked through another workspace is unknown, not shared
        assert client.get(_url(ws2, a)).status_code == 404


class TestNoNonFiniteStateAnywhere:
    """The surviving mutation of the first review (M14: raw NaN passed to the response model) was equivalent only
    because pydantic serialises NaN as null. These assertions do not depend on that: the model attribute itself is
    null, the registry cannot hold NaN, and the wire body never carries a NaN or Infinity token."""

    @pytest.mark.parametrize("imported", [float("nan"), float("inf"), float("-inf")])
    def test_the_response_model_never_carries_a_non_finite_number(self, imported):
        from app.schemas.nominal_frequency import NominalFrequencyOut
        out = NominalFrequencyOut.from_domain("s", nf.resolve_nominal_frequency(imported, COMTRADE))
        assert out.imported_hz is None and out.imported_text == repr(imported)
        assert out.effective_hz is None and out.auto_hz is None and out.manual_hz is None
        assert "NaN" not in out.model_dump_json() and "Infinity" not in out.model_dump_json()

    @pytest.mark.parametrize("variant", ["declared_nan", "declared_inf", "declared_negative_inf", "declared_overflow_1e999"])
    def test_the_wire_body_has_no_non_finite_token(self, client, variant):
        ws = _ws()
        sid = _upload_comtrade(client, ws, variant)
        for response in (client.get(_url(ws, sid)), _put(client, ws, sid, {"mode": "manual", "value_hz": 50}),
                         _put(client, ws, sid, {"mode": "auto"})):
            assert response.status_code == 200
            assert "NaN" not in response.text and "Infinity" not in response.text


class TestOriginalsAreNeverChanged:
    @staticmethod
    def _fingerprint(client, ws, sid) -> str:
        active = client.app.state.workspace_registry.get(ws, sid)
        h = hashlib.sha256()
        h.update(repr((active.metadata.nominal_frequency, active.metadata.preparation_provenance,
                       active.metadata.sampling_rates, active.metadata.samples_per_rate,
                       active.record.metadata.nominal_frequency)).encode())
        for name in sorted(active.record.waveform_data):
            h.update(name.encode())
            h.update(active.record.waveform_data[name].to_numpy().tobytes())
        return h.hexdigest()

    @pytest.mark.parametrize("variant", ["declared_60", "unparseable_text", "declared_zero", "declared_nan"])
    def test_set_change_and_clear_leave_metadata_provenance_and_samples_untouched(self, client, variant):
        ws = _ws()
        sid = _upload_comtrade(client, ws, variant)
        before = self._fingerprint(client, ws, sid)
        for body in ({"mode": "manual", "value_hz": 60}, {"mode": "manual", "value_hz": 50}, {"mode": "auto"}):
            assert _put(client, ws, sid, body).status_code == 200
            assert self._fingerprint(client, ws, sid) == before


class TestLifecycle:
    def test_removing_the_recording_removes_its_value(self, client):
        ws = _ws()
        sid = _upload_comtrade(client, ws, "declared_50")
        _put(client, ws, sid, {"mode": "manual", "value_hz": 60})
        registry = client.app.state.nominal_frequency_registry
        assert registry.get(ws, sid) is not None
        assert client.delete(f"/api/v1/workspaces/{ws}/sources/{sid}").status_code == 204
        assert registry.snapshot(ws, sid) == (None, 0)
        assert client.get(_url(ws, sid)).status_code == 404
        # the same file added again is a new recording and starts in Auto
        again = _upload_comtrade(client, ws, "declared_50")
        assert again != sid
        assert client.get(_url(ws, again)).json()["mode"] == "auto"

    def test_workspace_reset_clears_only_that_workspace(self, client):
        ws1, ws2 = _ws(), _ws()
        a, b = _upload_comtrade(client, ws1, "declared_50"), _upload_comtrade(client, ws2, "declared_50")
        _put(client, ws1, a, {"mode": "manual", "value_hz": 60})
        _put(client, ws2, b, {"mode": "manual", "value_hz": 25})
        registry = client.app.state.nominal_frequency_registry
        assert client.delete(f"/api/v1/workspaces/{ws1}").status_code == 204
        assert registry.get(ws1, a) is None
        assert client.get(_url(ws2, b)).json()["effective_hz"] == 25.0

    def test_the_delete_of_one_recording_keeps_the_others(self, client):
        ws = _ws()
        a, b = _upload_comtrade(client, ws, "declared_50"), _upload_comtrade(client, ws, "declared_60")
        _put(client, ws, a, {"mode": "manual", "value_hz": 25})
        _put(client, ws, b, {"mode": "manual", "value_hz": 40})
        client.delete(f"/api/v1/workspaces/{ws}/sources/{a}")
        assert client.get(_url(ws, b)).json()["effective_hz"] == 40.0


# ------------------------------------------------------------------------------- protected scope: no consumer change
#: The direct readers of `<x>.metadata.nominal_frequency` in the application (NF-001 inventory). NF-1 migrates none of
#: them; the numbers may only go DOWN as NF-3 migrates consumers, and no new direct reader may appear.
ALLOWED_DIRECT_READERS = {
    # NF-3C migrated compliance measurement (C-05) and readiness (C-04): removed.
    "services/import_service.py": 1,                   # import: provider metadata -> SourceMetadata
    "services/nominal_frequency_service.py": 1,        # the authority reads the immutable imported value
    # NF-3C migrated oscillation representation (C-06): removed.
    "services/overcurrent_analysis_service.py": 2,
    "services/phasor_analysis_service.py": 2,
    "services/synchronization_service.py": 1,           # NF-3C: C-03 migrated; one read left, echoing the DECLARED value when unusable (O-7)
}


def _direct_readers() -> dict[str, int]:
    found: dict[str, int] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        count = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "nominal_frequency" and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Attribute) and node.value.attr == "metadata"
        )
        if count:
            found[path.relative_to(APP_DIR).as_posix()] = count
    return found


class TestNoConsumerChange:
    def test_no_new_direct_reader_of_the_imported_frequency(self):
        found = _direct_readers()
        for path, count in found.items():
            assert path in ALLOWED_DIRECT_READERS, f"new direct reader of metadata.nominal_frequency: {path}"
            assert count <= ALLOWED_DIRECT_READERS[path], f"more direct reads in {path}"

    def test_nothing_but_the_authority_uses_the_resolver_yet(self):
        # NF-3B (reviewed change): the router no longer imports the service; the release-gated accessor is its only importer,
        # so the gate cannot be bypassed. Consumer isolation is enforced by test_nf3b_frequency_call_path_guard.py.
        users = sorted(
            p.relative_to(APP_DIR).as_posix() for p in APP_DIR.rglob("*.py")
            if p.name != "nominal_frequency_service.py" and "nominal_frequency_service" in p.read_text(encoding="utf-8")
        )
        assert users == ["services/nominal_frequency_access.py"]
