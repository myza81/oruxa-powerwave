"""Event Reconstruction Per-Unit Display (DEC-138): the backend paths Event
Reconstruction consumes -- never a second per-unit implementation.

Waveform owns per-unit configuration (Measurement Groups, Source Default);
Event Reconstruction reads each channel's RESOLVED basis (GET
.../per-unit-resolution) and its values in pu from the existing waveform /
cursor / peak / anchor endpoints (unit_mode="per_unit"). These tests pin:

- the additive `per_unit_display_axis_*` channel metadata is quantity-aware
  (Voltage (pu), Current (pu), ... never one "pu" axis);
- the L-L / L-G regression: a 275 kV L-L Measurement Group base on an L-G
  channel resolves 275/sqrt(3) kV, even with a conflicting legacy Source
  Default base on the same source, and every endpoint agrees;
- pu values are the engineering values over that one base -- full
  resolution and min/max envelope alike (order kept), the same samples;
- peaks / anchors / cursors find the SAME sample in either unit;
- calculated channels follow the existing inheritance rules (a unary
  operation inherits; generic Voltage subtraction stays base_required);
- Power stays not_applicable (Waveform keeps it in engineering units).
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.engineering_units import resolve_per_unit_display_axis
from app.main import create_app

WS = "ws-er-pu"
RATE_HZ = 5000
DURATION_S = 4.0
LL_BASE_KV = 275.0
LG_BASE_KV = LL_BASE_KV / math.sqrt(3)  # ~158.77 kV
LEGACY_SOURCE_DEFAULT_KV = 132.0  # the conflicting legacy setting
VA_PEAK_KV = 159.5  # ~1.0046 pu on the L-G base
IBASE_KA = 2.0

CHANNELS = [
    # (name, phase, unit, amplitude, frequency Hz, phase shift rad)
    ("VA", "A", "kV", VA_PEAK_KV, 50.0, 0.0),
    ("VB", "B", "kV", VA_PEAK_KV, 50.0, -2 * math.pi / 3),
    ("IA", "A", "A", 1500.0, 50.0, 0.3),
    ("P", "", "MW", 80.0, 0.5, 0.0),
]


def _synthetic_comtrade() -> tuple[bytes, bytes]:
    count = int(RATE_HZ * DURATION_S) + 1
    cfg = [
        "STN_PU,SYNTH_DEV,1999",
        f"{len(CHANNELS)},{len(CHANNELS)}A,0D",
        *[f"{i + 1},{name},{phase},,{unit},{amp / 30000},0.0,0,-32767,32767,1.0,1.0,P"
          for i, (name, phase, unit, amp, _, _) in enumerate(CHANNELS)],
        "50", "1", f"{RATE_HZ},{count}",
        "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ]
    rows = []
    for n in range(count):
        t = n / RATE_HZ
        raw = [round(math.sin(2 * math.pi * f * t + shift) * 30000) for (_, _, _, _, f, shift) in CHANNELS]
        rows.append(",".join(str(v) for v in [n + 1, round(t * 1e6), *raw]))
    return ("\r\n".join(cfg) + "\r\n").encode("latin1"), ("\r\n".join(rows) + "\r\n").encode("latin1")


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _api(path: str) -> str:
    return f"/api/v1/workspaces/{WS}{path}"


@pytest.fixture
def source_id(client) -> str:
    cfg, dat = _synthetic_comtrade()
    resp = client.post(_api("/sources"), files={
        "cfg_file": ("STN_PU.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": ("STN_PU.dat", io.BytesIO(dat), "application/octet-stream"),
    })
    assert resp.status_code == 201, resp.text
    sid = resp.json()["source_id"]
    groups_url = _api(f"/sources/{sid}/measurement-groups")
    for group in client.get(groups_url).json():
        client.delete(f"{groups_url}/{group['id']}")
    # The legacy source-wide setting the earlier confusion came from: a
    # Measurement Group member must never use it.
    resp = client.put(_api(f"/per-unit/sources/{sid}"), json={"voltage_base_value": LEGACY_SOURCE_DEFAULT_KV})
    assert resp.status_code == 200, resp.text
    refs = lambda *names: [{"kind": "source", "source_id": sid, "channel_name": n} for n in names]  # noqa: E731
    voltage = client.post(groups_url, json={"kind": "voltage", "display_name": "275 kV BUS", "status": "confirmed",
                                            "channel_refs": refs("VA", "VB")})
    assert voltage.status_code == 201, voltage.text
    resp = client.put(f"{groups_url}/{voltage.json()['id']}/voltage-config", json={"nominal_voltage_ll_kv": LL_BASE_KV})
    assert resp.status_code == 200, resp.text
    current = client.post(groups_url, json={"kind": "current", "display_name": "LINE CURRENT", "status": "confirmed",
                                            "channel_refs": refs("IA")})
    assert current.status_code == 201, current.text
    resp = client.put(f"{groups_url}/{current.json()['id']}/current-config", json={"method": "manual", "manual_ibase_ka": IBASE_KA})
    assert resp.status_code == 200, resp.text
    return sid


def _resolution(client, sid, name):
    resp = client.get(_api(f"/sources/{sid}/per-unit-resolution"), params={"channel_name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _waveform(client, sid, name, unit_mode, **params):
    resp = client.get(_api(f"/sources/{sid}/waveform"), params={"channel_name": name, "unit_mode": unit_mode, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPerUnitDisplayAxis:
    @pytest.mark.parametrize(("engineering_type", "quantity", "key", "title_quantity"), [
        ("Voltage", "Undefined", "Voltage|raw:pu", "Voltage"),
        ("Current", "Undefined", "Current|raw:pu", "Current"),
        ("Power", "Active Power", "Active Power|raw:pu", "Active Power"),
        ("Power", "Reactive Power", "Reactive Power|raw:pu", "Reactive Power"),
    ])
    def test_quantity_aware_never_one_pu_axis(self, engineering_type, quantity, key, title_quantity):
        axis = resolve_per_unit_display_axis(engineering_type, quantity)
        assert (axis.key, axis.quantity, axis.unit) == (key, title_quantity, "pu")

    def test_on_the_channel_apis_native_and_calculated(self, client, source_id):
        channels = {c["name"]: c for c in client.get(_api(f"/sources/{source_id}/channels")).json()["analog_channels"]}
        assert channels["VA"]["per_unit_display_axis_key"] == "Voltage|raw:pu"
        assert channels["IA"]["per_unit_display_axis_key"] == "Current|raw:pu"
        assert (channels["VA"]["per_unit_display_axis_quantity"], channels["VA"]["per_unit_display_axis_unit"]) == ("Voltage", "pu")
        # Existing engineering fields unchanged.
        assert channels["VA"]["display_axis_key"] == "Voltage|kV"
        calc = client.post(_api("/calculated-channels"), json={
            "name": "-VA", "operation": "reverse_polarity", "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
        }).json()
        # Native and calculated Voltage share one pu axis.
        assert calc["per_unit_display_axis_key"] == channels["VA"]["per_unit_display_axis_key"]


class TestResolvedBasisRegression:
    """275 kV L-L Measurement Group, L-G channel: base 275/sqrt(3) kV --
    the Measurement Group wins over the conflicting legacy Source Default,
    and no endpoint re-applies sqrt(3)."""

    def test_resolution(self, client, source_id):
        va = _resolution(client, source_id, "VA")
        assert va["status"] == "configured"
        assert va["source_kind"] == "measurement_group"
        assert va["nominal_base_kv"] == LL_BASE_KV
        assert va["nominal_reference"] == "line_to_ground"
        assert va["effective_base_amount"] == pytest.approx(LG_BASE_KV, rel=1e-12)
        assert va["effective_base_unit"] == "kV"
        assert _resolution(client, source_id, "IA")["status"] == "configured"
        # Waveform's rule: Power has no per-unit definition.
        assert _resolution(client, source_id, "P")["status"] == "not_applicable"

    def test_values_are_engineering_over_the_one_resolved_base(self, client, source_id):
        window = {"start_time": 0.1, "end_time": 0.12, "point_budget": 5000}
        eng = _waveform(client, source_id, "VA", "engineering", **window)
        pu = _waveform(client, source_id, "VA", "per_unit", **window)
        assert eng["representation"] == pu["representation"] == "full_resolution"
        assert pu["per_unit_status"] == "configured" and pu["unit"] == "pu" and eng["unit"] == "kV"
        assert pu["time"] == eng["time"]
        np.testing.assert_allclose(pu["values"], np.asarray(eng["values"]) / LG_BASE_KV, rtol=1e-12)
        # ~159.5 kV engineering -> ~1.0046 pu (never 159.5/275, never 159.5/132).
        assert max(eng["values"]) == pytest.approx(VA_PEAK_KV, rel=1e-3)
        assert max(pu["values"]) == pytest.approx(VA_PEAK_KV / LG_BASE_KV, rel=1e-3)
        assert 1.0 < max(pu["values"]) < 1.01

    def test_min_max_envelope_scales_directly(self, client, source_id):
        eng = _waveform(client, source_id, "VA", "engineering", point_budget=400)
        pu = _waveform(client, source_id, "VA", "per_unit", point_budget=400)
        assert eng["representation"] == pu["representation"] == "min_max_envelope"
        assert pu["time"] == eng["time"]
        np.testing.assert_allclose(pu["values"], np.asarray(eng["values"]) / LG_BASE_KV, rtol=1e-12)
        # Envelope pairs keep their min/max order (a positive base).
        e, p = np.asarray(eng["values"]), np.asarray(pu["values"])
        assert np.array_equal(np.sign(np.diff(e)), np.sign(np.diff(p)))

    def test_cursor_values_are_the_same_samples_in_pu(self, client, source_id):
        body = {"analog_channel_names": ["VA", "IA", "P"], "cursor_a_time": 0.1003, "cursor_b_time": 0.2507}
        eng = client.post(_api(f"/sources/{source_id}/cursor-values"), json={**body, "unit_mode": "engineering"}).json()
        pu = client.post(_api(f"/sources/{source_id}/cursor-values"), json={**body, "unit_mode": "per_unit"}).json()
        assert eng["cursor_a"]["sample_time"] == pu["cursor_a"]["sample_time"]
        assert eng["cursor_b"]["sample_time"] == pu["cursor_b"]["sample_time"]
        by_eng = {c["channel_name"]: c for c in eng["channels"]}
        by_pu = {c["channel_name"]: c for c in pu["channels"]}
        assert by_pu["VA"]["per_unit_status"] == "configured" and by_pu["VA"]["unit"] == "pu"
        assert by_pu["VA"]["a_value"] == pytest.approx(by_eng["VA"]["a_value"] / LG_BASE_KV, rel=1e-12)
        assert by_pu["IA"]["a_value"] == pytest.approx(by_eng["IA"]["a_value"] / (IBASE_KA * 1000), rel=1e-12)
        # Not applicable: the engineering value, as Waveform shows it.
        assert by_pu["P"]["per_unit_status"] == "not_applicable"
        assert by_pu["P"]["a_value"] == by_eng["P"]["a_value"] and by_pu["P"]["unit"] == "MW"

    def test_peaks_find_the_same_sample_in_either_unit(self, client, source_id):
        body = {"requests": [{"channel_name": "VA", "mode": "max"}, {"channel_name": "VA", "mode": "min"}],
                "start_time": 0.5, "end_time": 0.53}
        eng = client.post(_api(f"/sources/{source_id}/peak-values"), json={**body, "unit_mode": "engineering"}).json()["results"]
        pu = client.post(_api(f"/sources/{source_id}/peak-values"), json={**body, "unit_mode": "per_unit"}).json()["results"]
        for e, p in zip(eng, pu):
            assert p["sample_index"] == e["sample_index"]
            assert p["elapsed_seconds"] == e["elapsed_seconds"]
            assert p["value"] == pytest.approx(e["value"] / LG_BASE_KV, rel=1e-12)
            assert p["per_unit_status"] == "configured"

    def test_an_anchor_read_again_in_pu_is_the_same_sample(self, client, source_id):
        url = _api(f"/sources/{source_id}/annotation-anchor")
        eng = client.post(url, json={"channel_name": "VA", "approximate_elapsed_seconds": 0.3141, "unit_mode": "engineering"}).json()
        pu = client.post(url, json={"channel_name": "VA", "approximate_elapsed_seconds": eng["elapsed_seconds"], "unit_mode": "per_unit"}).json()
        assert pu["sample_index"] == eng["sample_index"]
        assert pu["value"] == pytest.approx(eng["value"] / LG_BASE_KV, rel=1e-12)
        assert pu["per_unit_status"] == "configured"


class TestCalculatedChannels:
    def _create(self, client, name, operation, inputs):
        resp = client.post(_api("/calculated-channels"), json={"name": name, "operation": operation, "inputs": inputs})
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_unary_inherits_the_group_base_generic_voltage_subtraction_does_not(self, client, source_id):
        src = lambda name: {"kind": "source", "source_id": source_id, "channel_name": name}  # noqa: E731
        negated = self._create(client, "-VA", "reverse_polarity", [src("VA")])
        difference = self._create(client, "VA-VB", "subtraction", [src("VA"), src("VB")])
        resolved = client.get(_api(f"/calculated-channels/{negated['id']}/per-unit-resolution")).json()
        assert resolved["status"] == "configured"
        assert resolved["effective_base_amount"] == pytest.approx(LG_BASE_KV, rel=1e-12)
        # DEC-052/DEC-116: never auto-resolved -- PU unavailable in Event
        # Reconstruction, never a guessed base.
        undetermined = client.get(_api(f"/calculated-channels/{difference['id']}/per-unit-resolution")).json()
        assert undetermined["status"] == "base_required"
        window = {"start_time": 0.1, "end_time": 0.11, "point_budget": 5000}
        pu = client.get(_api(f"/calculated-channels/{negated['id']}/waveform"), params={**window, "unit_mode": "per_unit"}).json()
        eng = client.get(_api(f"/calculated-channels/{negated['id']}/waveform"), params={**window, "unit_mode": "engineering"}).json()
        assert pu["per_unit_status"] == "configured"
        np.testing.assert_allclose(pu["values"], np.asarray(eng["values"]) / LG_BASE_KV, rtol=1e-12)
        unresolved = client.get(_api(f"/calculated-channels/{difference['id']}/waveform"), params={**window, "unit_mode": "per_unit"}).json()
        assert unresolved["per_unit_status"] == "base_required" and unresolved["unit"] != "pu"
