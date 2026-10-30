"""API-layer tests for POST /api/v1/calculator/power/single-phase.

These verify the HTTP contract (routing, request/response shape, validation)
and, for golden-vector checks, confirm the API result against the SAME
closed-form values used in test_power_calculation_domain.py. The domain
tests own the exhaustive mathematical verification; the API tests own the
HTTP contract.

All expected values are derived from first principles (not from the
implementation), identical to the approach in the domain tests.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

_TOL = 1e-4   # generous for HTTP-round-trip comparisons (still 4 sig figs)
_TOL_PF = 1e-6


@pytest.fixture
def client(settings):
    """TestClient with a properly configured in-process app."""
    with TestClient(create_app(settings)) as c:
        yield c


def post_vi(client, v_mag, v_ang, i_mag, i_ang):
    """POST with SI base-unit inputs and return JSON or raise."""
    return client.post(
        "/api/v1/calculator/power/single-phase",
        json={
            "v_magnitude_rms": v_mag,
            "v_angle_deg": v_ang,
            "i_magnitude_rms": i_mag,
            "i_angle_deg": i_ang,
        },
    )


# ---------------------------------------------------------------------------
# Standard lagging load
# V = 1000 V @ 0°, I = 100 A @ −30°
# P = 100 000 × cos(30°) = 50 000√3 ≈ 86 602.54 W
# Q = 100 000 × sin(30°) = 50 000 var
# S = 100 000 VA,  PF = √3/2 ≈ 0.866 (lagging)
# ---------------------------------------------------------------------------

class TestApiStandardLagging:
    @pytest.fixture(autouse=True)
    def response(self, client):  # noqa: F811
        self._r = post_vi(client, 1000.0, 0.0, 100.0, -30.0)
        self._j = self._r.json()

    def test_status_200(self):
        assert self._r.status_code == 200

    def test_p_watts(self):
        assert self._j["p_watts"] == pytest.approx(50_000.0 * math.sqrt(3), abs=_TOL)

    def test_q_var(self):
        assert self._j["q_var"] == pytest.approx(50_000.0, abs=_TOL)

    def test_s_va(self):
        assert self._j["s_va"] == pytest.approx(100_000.0, abs=_TOL)

    def test_power_factor(self):
        assert self._j["power_factor"] == pytest.approx(math.sqrt(3) / 2, abs=_TOL_PF)

    def test_power_factor_sign_lagging(self):
        assert self._j["power_factor_sign"] == "lagging"

    def test_power_angle_deg(self):
        assert self._j["power_angle_deg"] == pytest.approx(30.0, abs=_TOL)

    def test_provenance_fields(self):
        assert self._j["sign_convention"] == "passive"
        assert self._j["apparent_power_definition"] == "geometric_fundamental_complex"
        assert "algorithm_version" in self._j


# ---------------------------------------------------------------------------
# Leading / capacitive
# V = 1000 V @ 0°, I = 100 A @ +30° → Q = -50 000 var (leading)
# ---------------------------------------------------------------------------

class TestApiLeadingCapacitive:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 1000.0, 0.0, 100.0, 30.0).json()

    def test_q_var_negative(self):
        assert self._j["q_var"] == pytest.approx(-50_000.0, abs=_TOL)

    def test_power_factor_sign_leading(self):
        assert self._j["power_factor_sign"] == "leading"

    def test_p_still_positive(self):
        assert self._j["p_watts"] == pytest.approx(50_000.0 * math.sqrt(3), abs=_TOL)


# ---------------------------------------------------------------------------
# Unity power factor
# V = 1000 V @ 0°, I = 100 A @ 0° → P = 100 000 W, Q = 0
# ---------------------------------------------------------------------------

class TestApiUnityPf:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 1000.0, 0.0, 100.0, 0.0).json()

    def test_p_watts(self):
        assert self._j["p_watts"] == pytest.approx(100_000.0, abs=_TOL)

    def test_q_var_zero(self):
        assert self._j["q_var"] == pytest.approx(0.0, abs=_TOL)

    def test_power_factor_unity(self):
        assert self._j["power_factor"] == pytest.approx(1.0, abs=_TOL_PF)

    def test_power_factor_sign_unity(self):
        assert self._j["power_factor_sign"] == "unity"


# ---------------------------------------------------------------------------
# Reverse active power (generating / injection side)
# V = 1000 V @ 0°, I = 100 A @ 180° → P = -100 000 W (supplying power)
# ---------------------------------------------------------------------------

class TestApiReversePower:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 1000.0, 0.0, 100.0, 180.0).json()

    def test_p_watts_negative(self):
        assert self._j["p_watts"] == pytest.approx(-100_000.0, abs=_TOL)

    def test_q_var_near_zero(self):
        assert self._j["q_var"] == pytest.approx(0.0, abs=_TOL)

    def test_s_va_positive(self):
        assert self._j["s_va"] == pytest.approx(100_000.0, abs=_TOL)

    def test_power_factor_negative_one(self):
        # Signed PF: P < 0, S > 0 → PF = -1
        assert self._j["power_factor"] == pytest.approx(-1.0, abs=_TOL_PF)

    def test_power_factor_sign_unity(self):
        # Q = 0 → "unity" direction; reverse flow visible in signed PF
        assert self._j["power_factor_sign"] == "unity"


# ---------------------------------------------------------------------------
# Zero current (open circuit) — power factor undefined
# ---------------------------------------------------------------------------

class TestApiZeroCurrent:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 1000.0, 0.0, 0.0, 0.0).json()

    def test_p_zero(self):
        assert self._j["p_watts"] == pytest.approx(0.0, abs=_TOL)

    def test_s_zero(self):
        assert self._j["s_va"] == pytest.approx(0.0, abs=_TOL)

    def test_power_factor_none(self):
        assert self._j["power_factor"] is None

    def test_power_factor_sign_undefined(self):
        assert self._j["power_factor_sign"] == "undefined"


# ---------------------------------------------------------------------------
# Zero voltage (dead bus)
# ---------------------------------------------------------------------------

class TestApiZeroVoltage:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 0.0, 0.0, 100.0, -30.0).json()

    def test_s_zero(self):
        assert self._j["s_va"] == pytest.approx(0.0, abs=_TOL)

    def test_pf_none(self):
        assert self._j["power_factor"] is None


# ---------------------------------------------------------------------------
# Angle wrapping: V @ 370° is the same phasor as V @ 10°.
# With I @ 10° the phase difference is 0 (unity PF).
# V @ 370° with I @ 10° should give the same result as V @ 10° with I @ 10°.
# ---------------------------------------------------------------------------

class TestApiAngleWrapping:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j_wrapped = post_vi(client, 1000.0, 370.0, 100.0, 10.0).json()
        self._j_canon = post_vi(client, 1000.0, 10.0, 100.0, 10.0).json()

    def test_p_matches(self):
        assert self._j_wrapped["p_watts"] == pytest.approx(self._j_canon["p_watts"], abs=_TOL)

    def test_q_matches(self):
        assert self._j_wrapped["q_var"] == pytest.approx(self._j_canon["q_var"], abs=_TOL)

    def test_s_matches(self):
        assert self._j_wrapped["s_va"] == pytest.approx(self._j_canon["s_va"], abs=_TOL)

    def test_pf_sign_matches(self):
        assert self._j_wrapped["power_factor_sign"] == self._j_canon["power_factor_sign"]


# ---------------------------------------------------------------------------
# Engineering unit conversion at the API boundary.
# 11 kV = 11 000 V: callers must submit base-SI values.
# V = 11 000 V @ 0°, I = 100 A @ −30° → same proportional result as
# V = 1 000 V @ 0°, I = 100 A @ −30° but scaled by 11.
# ---------------------------------------------------------------------------

class TestApiEngineeringUnits:
    @pytest.fixture(autouse=True)
    def response(self, client):
        self._j = post_vi(client, 11_000.0, 0.0, 100.0, -30.0).json()

    def test_p_watts_scaled(self):
        expected_p = 11_000.0 * 100.0 * math.cos(math.radians(30.0))
        assert self._j["p_watts"] == pytest.approx(expected_p, abs=_TOL)

    def test_q_var_scaled(self):
        expected_q = 11_000.0 * 100.0 * math.sin(math.radians(30.0))
        assert self._j["q_var"] == pytest.approx(expected_q, abs=_TOL)

    def test_s_va_scaled(self):
        assert self._j["s_va"] == pytest.approx(11_000.0 * 100.0, abs=_TOL)

    def test_pf_unchanged_by_scale(self):
        # PF depends only on the angle, not the magnitudes
        assert self._j["power_factor"] == pytest.approx(math.sqrt(3) / 2, abs=_TOL_PF)


# ---------------------------------------------------------------------------
# Validation: invalid inputs must return 422
# ---------------------------------------------------------------------------

class TestApiValidation:
    def test_negative_voltage_rejected(self, client):
        r = post_vi(client, -1.0, 0.0, 100.0, 0.0)
        assert r.status_code == 422

    def test_negative_current_rejected(self, client):
        r = post_vi(client, 1000.0, 0.0, -1.0, 0.0)
        assert r.status_code == 422

    def test_missing_field_rejected(self, client):
        r = client.post(
            "/api/v1/calculator/power/single-phase",
            json={"v_magnitude_rms": 1000.0, "v_angle_deg": 0.0, "i_magnitude_rms": 100.0},
        )
        assert r.status_code == 422

    def test_non_numeric_field_rejected(self, client):
        r = client.post(
            "/api/v1/calculator/power/single-phase",
            json={
                "v_magnitude_rms": "not_a_number",
                "v_angle_deg": 0.0,
                "i_magnitude_rms": 100.0,
                "i_angle_deg": 0.0,
            },
        )
        assert r.status_code == 422

    def test_null_field_rejected(self, client):
        r = client.post(
            "/api/v1/calculator/power/single-phase",
            json={
                "v_magnitude_rms": None,
                "v_angle_deg": 0.0,
                "i_magnitude_rms": 100.0,
                "i_angle_deg": 0.0,
            },
        )
        assert r.status_code == 422

    def test_empty_body_rejected(self, client):
        r = client.post("/api/v1/calculator/power/single-phase", json={})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Response shape: required fields must always be present
# ---------------------------------------------------------------------------

class TestApiResponseShape:
    _REQUIRED = {
        "p_watts", "q_var", "s_va", "power_angle_deg",
        "power_factor", "power_factor_sign",
        "sign_convention", "apparent_power_definition", "algorithm_version",
    }

    def test_all_required_fields_present(self, client):
        j = post_vi(client, 1000.0, 0.0, 100.0, -30.0).json()
        for field in self._REQUIRED:
            assert field in j, f"Missing field: {field}"

    def test_power_factor_is_null_for_zero_current(self, client):
        j = post_vi(client, 1000.0, 0.0, 0.0, 0.0).json()
        assert j["power_factor"] is None
