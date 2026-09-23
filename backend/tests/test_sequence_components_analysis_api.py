"""API-level tests for Sequence Components v1
(`GET .../sequence-components`, `GET .../sequence-components-manual`).
Exercises the real FastAPI app end-to-end via a real ASCII-COMTRADE
upload, mirroring `test_impedance_analysis_api.py`'s own
fixture-construction pattern. See
docs/project-memory/SEQUENCE_COMPONENTS_ANALYSIS.md.
"""

from __future__ import annotations

import io
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_TOL = 1.5  # percent-scale tolerance for magnitude/angle recovered from a sampled sine


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _build_ascii_comtrade(
    *, station: str, channels: list[tuple[str, str, float, float]], sample_rate_hz: float, duration_s: float,
    nominal_frequency_hz: float = 50.0,
) -> tuple[bytes, bytes]:
    n = int(round(duration_s * sample_rate_hz))
    dt_us = 1_000_000.0 / sample_rate_hz
    lines_cfg = [f"{station},SEQDEV,1999", f"{len(channels)},{len(channels)}A,0D"]
    for i, (name, unit, _amp, _phase) in enumerate(channels, start=1):
        lines_cfg.append(f"{i},{name},,,{unit},1.0,0.0,0,-99999999,99999999,1.0,1.0,P")
    lines_cfg.append(str(nominal_frequency_hz))
    lines_cfg.append("1")
    lines_cfg.append(f"{sample_rate_hz},{n}")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("06/03/2026,10:00:00.000000")
    lines_cfg.append("ASCII")
    lines_cfg.append("1.0")
    cfg_text = "\n".join(lines_cfg) + "\n"

    t = np.arange(n) / sample_rate_hz
    values = [
        amp * np.cos(2.0 * np.pi * nominal_frequency_hz * t + np.radians(phase_deg))
        for _name, _unit, amp, phase_deg in channels
    ]
    lines_dat = []
    for row in range(n):
        parts = [str(row + 1), f"{row * dt_us:.1f}"] + [f"{values[c][row]:.6f}" for c in range(len(channels))]
        lines_dat.append(",".join(parts))
    dat_text = "\n".join(lines_dat) + "\n"
    return cfg_text.encode("ascii"), dat_text.encode("ascii")


def _upload_sine_source(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="seq_ascii"):
    """DEC-104 (2026-09-23): upload now also runs automatic Engineering
    Context discovery, which would otherwise collide with this module's
    own hand-built contexts on the same channels -- clear whatever
    discovery created immediately after upload so every test below
    keeps constructing its own contexts from a clean slate."""
    source_id = _upload_sine_source_without_clearing(
        client, workspace_id, channels=channels, sample_rate_hz=sample_rate_hz,
        duration_s=duration_s, nominal_frequency_hz=nominal_frequency_hz, stem=stem,
    )
    for context in client.get(_contexts_url(workspace_id)).json():
        client.delete(f"{_contexts_url(workspace_id)}/{context['id']}")
    return source_id


def _upload_sine_source_without_clearing(client, workspace_id, *, channels, sample_rate_hz=1000.0, duration_s=3.0, nominal_frequency_hz=50.0, stem="seq_ascii"):
    cfg, dat = _build_ascii_comtrade(
        station="ZSTA", channels=channels, sample_rate_hz=sample_rate_hz, duration_s=duration_s,
        nominal_frequency_hz=nominal_frequency_hz,
    )
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


def _contexts_url(workspace_id):
    return f"/api/v1/workspaces/{workspace_id}/engineering-contexts"


def _ref(source_id, name):
    return {"kind": "source", "source_id": source_id, "channel_name": name}


def _create_bay(client, workspace_id, source_id, *, prefix="SBAY", members=("Va", "Vb", "Vc", "Ia", "Ib", "Ic")):
    role_to_suffix = {"Va": "VA", "Vb": "VB", "Vc": "VC", "Ia": "IA", "Ib": "IB", "Ic": "IC"}
    role_to_phase = {"Va": "A", "Vb": "B", "Vc": "C", "Ia": "A", "Ib": "B", "Ic": "C"}
    resp = client.post(_contexts_url(workspace_id), json={
        "display_name": "Sbay 1", "status": "manual", "members": [
            {
                "channel_ref": _ref(source_id, f"{prefix}_{role_to_suffix[role]}"),
                "phase": role_to_phase[role], "phase_source": "engineer_confirmed",
            }
            for role in members
        ],
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _sequence(client, workspace_id, context_id, *, analysis_time=1.5, **extra):
    params = {"analysis_time": analysis_time}
    params.update(extra)
    return client.get(f"{_contexts_url(workspace_id)}/{context_id}/sequence-components", params=params)


def _sequence_manual(client, workspace_id, **params):
    defaults = dict(voltage_basis="secondary", current_basis="secondary")
    defaults.update(params)
    query = {k: v for k, v in defaults.items() if v is not None}
    return client.get(f"/api/v1/workspaces/{workspace_id}/sequence-components-manual", params=query)


class TestRecordingSequenceViaHttp:
    def _bay(self, client, channels, workspace_id="ws-seq-1", prefix="SBAY", members=("Va", "Vb", "Vc", "Ia", "Ib", "Ic")):
        source_id = _upload_sine_source(client, workspace_id, channels=channels)
        context = _create_bay(client, workspace_id, source_id, prefix=prefix, members=members)
        return workspace_id, context["id"]

    def test_golden_balanced_positive_sequence_via_http(self, client):
        workspace_id, context_id = self._bay(client, channels=[
            ("SBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("SBAY_VB", "V", 100.0 * math.sqrt(2), -120.0), ("SBAY_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("SBAY_IA", "A", 40.0 * math.sqrt(2), 0.0), ("SBAY_IB", "A", 40.0 * math.sqrt(2), -120.0), ("SBAY_IC", "A", 40.0 * math.sqrt(2), 120.0),
        ])
        resp = _sequence(client, workspace_id, context_id)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        v = body["voltage_sequences"]
        assert v["status"] == "computed"
        assert v["positive_sequence_magnitude"] == pytest.approx(100.0, rel=1e-2)
        assert v["positive_sequence_angle_deg"] == pytest.approx(0.0, abs=_TOL)
        assert v["negative_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)
        assert v["zero_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)
        i = body["current_sequences"]
        assert i["status"] == "computed"
        assert i["positive_sequence_magnitude"] == pytest.approx(40.0, rel=1e-2)
        assert i["negative_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)
        assert i["zero_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)

    def test_pure_zero_sequence_via_http(self, client):
        workspace_id, context_id = self._bay(client, channels=[
            ("SBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("SBAY_VB", "V", 100.0 * math.sqrt(2), 0.0), ("SBAY_VC", "V", 100.0 * math.sqrt(2), 0.0),
            ("SBAY_IA", "A", 10.0 * math.sqrt(2), 0.0), ("SBAY_IB", "A", 10.0 * math.sqrt(2), 0.0), ("SBAY_IC", "A", 10.0 * math.sqrt(2), 0.0),
        ])
        resp = _sequence(client, workspace_id, context_id)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["zero_sequence_magnitude"] == pytest.approx(100.0, rel=1e-2)
        assert v["positive_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)
        assert v["negative_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)

    def test_pure_negative_sequence_via_http(self, client):
        workspace_id, context_id = self._bay(client, channels=[
            ("SBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("SBAY_VB", "V", 100.0 * math.sqrt(2), 120.0), ("SBAY_VC", "V", 100.0 * math.sqrt(2), -120.0),
            ("SBAY_IA", "A", 10.0 * math.sqrt(2), 0.0), ("SBAY_IB", "A", 10.0 * math.sqrt(2), 120.0), ("SBAY_IC", "A", 10.0 * math.sqrt(2), -120.0),
        ])
        resp = _sequence(client, workspace_id, context_id)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["negative_sequence_magnitude"] == pytest.approx(100.0, rel=1e-2)
        assert v["positive_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)
        assert v["zero_sequence_magnitude"] == pytest.approx(0.0, abs=_TOL)

    def test_sequence_ratios_are_present_and_descriptive(self, client):
        """A balanced (dominant-positive-sequence) recording has a
        well-defined, small negative-/zero-sequence ratio -- the
        near-zero-|X1| guardrail itself is exercised at the exact-math
        level (`test_sequence_components_domain.py`) and via Manual mode
        below, since a real waveform-ESTIMATED phasor never lands at
        exact mathematical zero the way a directly-entered Manual value
        does (estimator noise sits well above the guardrail's own
        numerical-validity floor)."""
        workspace_id, context_id = self._bay(client, channels=[
            ("SBAY_VA", "V", 100.0 * math.sqrt(2), 0.0), ("SBAY_VB", "V", 100.0 * math.sqrt(2), -120.0), ("SBAY_VC", "V", 100.0 * math.sqrt(2), 120.0),
            ("SBAY_IA", "A", 10.0 * math.sqrt(2), 0.0), ("SBAY_IB", "A", 10.0 * math.sqrt(2), -120.0), ("SBAY_IC", "A", 10.0 * math.sqrt(2), 120.0),
        ])
        resp = _sequence(client, workspace_id, context_id)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["negative_sequence_ratio_percent"] is not None
        assert v["negative_sequence_ratio_percent"] == pytest.approx(0.0, abs=_TOL)
        assert v["zero_sequence_ratio_percent"] is not None
        assert v["zero_sequence_ratio_percent"] == pytest.approx(0.0, abs=_TOL)

    def test_channel_refs_populated_for_related_waveforms(self, client):
        workspace_id, context_id = self._bay(client, channels=[
            ("SBAY_VA", "V", 100.0, 0.0), ("SBAY_VB", "V", 100.0, -120.0), ("SBAY_VC", "V", 100.0, 120.0),
            ("SBAY_IA", "A", 10.0, 0.0), ("SBAY_IB", "A", 10.0, -120.0), ("SBAY_IC", "A", 10.0, 120.0),
        ])
        resp = _sequence(client, workspace_id, context_id)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["phase_a_channel_ref"]["channel_name"] == "SBAY_VA"
        assert v["phase_b_channel_ref"]["channel_name"] == "SBAY_VB"
        assert v["phase_c_channel_ref"]["channel_name"] == "SBAY_VC"
        i = body["current_sequences"]
        assert i["phase_a_channel_ref"]["channel_name"] == "SBAY_IA"
        assert i["phase_b_channel_ref"]["channel_name"] == "SBAY_IB"
        assert i["phase_c_channel_ref"]["channel_name"] == "SBAY_IC"

    def test_incomplete_current_family_does_not_block_voltage(self, client):
        """Task's own section 8 worked example: Va/Vb/Vc complete,
        Ia/Ib incomplete (Ic never joined the context) -> Voltage
        sequences calculated, Current sequences report Missing."""
        workspace_id = "ws-seq-incomplete-current"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("SBAY_VA", "V", 100.0, 0.0), ("SBAY_VB", "V", 100.0, -120.0), ("SBAY_VC", "V", 100.0, 120.0),
            ("SBAY_IA", "A", 10.0, 0.0), ("SBAY_IB", "A", 10.0, -120.0),
        ])
        context = _create_bay(client, workspace_id, source_id, members=("Va", "Vb", "Vc", "Ia", "Ib"))
        resp = _sequence(client, workspace_id, context["id"])
        body = resp.json()
        assert body["status"] == "computed"
        assert body["voltage_sequences"]["status"] == "computed"
        assert body["current_sequences"]["status"] in ("missing", "needs_configuration")
        assert body["current_sequences"]["positive_sequence_magnitude"] is None
        # Voltage was never fabricated/blocked by Current's own incompleteness.
        assert body["voltage_sequences"]["positive_sequence_magnitude"] is not None

    def test_incomplete_voltage_family_does_not_block_current(self, client):
        workspace_id = "ws-seq-incomplete-voltage"
        source_id = _upload_sine_source(client, workspace_id, channels=[
            ("SBAY_VA", "V", 100.0, 0.0),
            ("SBAY_IA", "A", 10.0, 0.0), ("SBAY_IB", "A", 10.0, -120.0), ("SBAY_IC", "A", 10.0, 120.0),
        ])
        context = _create_bay(client, workspace_id, source_id, members=("Va", "Ia", "Ib", "Ic"))
        resp = _sequence(client, workspace_id, context["id"])
        body = resp.json()
        assert body["voltage_sequences"]["status"] in ("missing", "needs_configuration")
        assert body["current_sequences"]["status"] == "computed"

    def test_unknown_context_404s(self, client):
        resp = _sequence(client, "ws-seq-1", "ec-missing")
        assert resp.status_code == 404


class TestManualSequenceViaHttp:
    def _role_params(self, prefix, va, vb, vc):
        params = {}
        for suffix, (mag, ang) in zip(("a", "b", "c"), (va, vb, vc)):
            params[f"{prefix}{suffix}_enabled"] = True
            params[f"{prefix}{suffix}_magnitude"] = mag
            params[f"{prefix}{suffix}_unit"] = "V" if prefix == "v" else "A"
            params[f"{prefix}{suffix}_angle_deg"] = ang
        return params

    def test_golden_balanced_positive_sequence_via_manual(self, client):
        params = {}
        params.update(self._role_params("v", (100, 0), (100, -120), (100, 120)))
        params.update(self._role_params("i", (40, 0), (40, -120), (40, 120)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "computed"
        v = body["voltage_sequences"]
        assert v["status"] == "computed"
        assert v["positive_sequence_magnitude"] == pytest.approx(100.0, abs=1e-6)
        assert v["negative_sequence_magnitude"] == pytest.approx(0.0, abs=1e-6)
        assert v["zero_sequence_magnitude"] == pytest.approx(0.0, abs=1e-6)
        i = body["current_sequences"]
        assert i["positive_sequence_magnitude"] == pytest.approx(40.0, abs=1e-6)

    def test_pure_zero_sequence_via_manual(self, client):
        params = {}
        params.update(self._role_params("v", (100, 0), (100, 0), (100, 0)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["zero_sequence_magnitude"] == pytest.approx(100.0, abs=1e-6)
        assert v["positive_sequence_magnitude"] == pytest.approx(0.0, abs=1e-6)

    def test_near_zero_positive_sequence_ratio_is_unavailable_via_manual(self, client):
        """Task's own section 18 guardrail, exercised end-to-end: a
        directly-entered pure negative-sequence set has an exactly
        (to floating-point precision) zero positive sequence, so
        |X2|/|X1| and |X0|/|X1| must report an explicit unavailable
        (`None`), never Infinity/NaN."""
        params = {}
        params.update(self._role_params("v", (100, 0), (100, 120), (100, -120)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["negative_sequence_magnitude"] == pytest.approx(100.0, abs=1e-6)
        assert v["negative_sequence_ratio_percent"] is None
        assert v["zero_sequence_ratio_percent"] is None

    def test_mixed_basis_voltage_primary_current_secondary(self, client):
        """Task's own section 16/6 requirement -- Voltage and Current
        each carry their own independent basis; a Primary-basis Voltage
        family and Secondary-basis Current family both normalize to the
        same canonical Secondary basis before the transform."""
        params = dict(voltage_basis="primary", vt_primary=132000, vt_secondary=110, current_basis="secondary")
        params.update(self._role_params("v", (132000, 0), (132000, -120), (132000, 120)))
        for k in list(params):
            if k.startswith("v") and k.endswith("_unit"):
                params[k] = "V"
        params.update(self._role_params("i", (1, 0), (1, -120), (1, 120)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        v = body["voltage_sequences"]
        assert v["status"] == "computed"
        # Primary 132000 V normalized to Secondary via VT 132000/110 -> 110 V.
        assert v["positive_sequence_magnitude"] == pytest.approx(110.0, rel=1e-6)
        i = body["current_sequences"]
        assert i["positive_sequence_magnitude"] == pytest.approx(1.0, abs=1e-6)

    def test_no_recording_only_fields_in_response(self, client):
        params = {}
        params.update(self._role_params("v", (100, 0), (100, -120), (100, 120)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        body = resp.json()
        assert "engineering_context_id" not in body
        assert "analysis_time" not in body
        assert "reference_frequency_hz" not in body

    def test_incomplete_family_reports_missing_without_blocking_other(self, client):
        params = {}
        params.update(self._role_params("v", (100, 0), (100, -120), (100, 120)))
        # Only Ia entered -> Current family incomplete.
        params["ia_enabled"] = True
        params["ia_magnitude"] = 10
        params["ia_unit"] = "A"
        params["ia_angle_deg"] = 0
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        body = resp.json()
        assert body["voltage_sequences"]["status"] == "computed"
        assert body["current_sequences"]["status"] == "missing"

    def test_no_input_at_all_reports_missing_for_both_families(self, client):
        resp = _sequence_manual(client, "ws-seq-manual-1")
        body = resp.json()
        assert body["voltage_sequences"]["status"] == "missing"
        assert body["current_sequences"]["status"] == "missing"

    def test_invalid_voltage_basis_ratio_blocks_only_voltage(self, client):
        params = dict(voltage_basis="primary")  # missing vt_primary/vt_secondary
        params.update(self._role_params("v", (100, 0), (100, -120), (100, 120)))
        params.update(self._role_params("i", (10, 0), (10, -120), (10, 120)))
        resp = _sequence_manual(client, "ws-seq-manual-1", **params)
        body = resp.json()
        assert body["voltage_sequences"]["status"] == "needs_configuration"
        assert body["current_sequences"]["status"] == "computed"
