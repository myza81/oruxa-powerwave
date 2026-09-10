"""Per-Unit Configuration Slice 4: Source Default LL/LG voltage-base
interpretation fix.

Root cause (verified in Phase 1 of this slice's own audit): the DEC-049
Source Default resolver (`app.domain.per_unit.resolve_per_unit()`) used
to divide a measured Voltage channel directly by the raw entered
`voltage_base_value`, regardless of the channel's own effective
reference -- unlike `app.domain.voltage_group_config`'s already-correct
Measurement Group resolver, which always treats the entered value as
the nominal SYSTEM LINE-TO-LINE voltage and derives `Vbase_LL / sqrt(3)`
for a line-to-ground channel. This file locks in the corrected
arithmetic:

    L-L reference -> effective base = Vbase_LL (unchanged)
    L-G reference -> effective base = Vbase_LL / sqrt(3)   (the fix)

and separately proves the derived CURRENT base (`Ibase = Sbase /
(sqrt(3) x Vbase_LL)`) is UNCHANGED by this fix -- it always uses the
raw nominal `Vbase_LL` directly, exactly like
`app.domain.current_group_config`'s own equipment-rating resolver,
never the LG-adjusted denominator.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import VOLTAGE
from app.domain.per_unit import (
    CURRENT_BASE_MODE_DERIVED,
    CURRENT_BASE_MODE_DIRECT,
    STATUS_CONFIGURED,
    VOLTAGE_REFERENCE_MODE_AUTO,
    VOLTAGE_REFERENCE_MODE_MANUAL,
    PerUnitBaseProfile,
    convert_value_to_pu,
    derive_per_unit_profile_id,
    resolve_current_base_amps,
    resolve_per_unit,
)
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE
from app.main import create_app
from app.services.measurement_group_service import create_group
from app.services.voltage_group_config_service import set_voltage_base
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_MANUAL

SQRT_3 = 1.7320508075688772


def _profile(**overrides) -> PerUnitBaseProfile:
    defaults = dict(
        source_id="src-1",
        workspace_id="ws-1",
        voltage_base_value=None,
        voltage_reference_mode=VOLTAGE_REFERENCE_MODE_AUTO,
        voltage_reference_override=None,
        apparent_power_base_value=None,
        current_base_mode="none",
        direct_current_base_value=None,
    )
    defaults.update(overrides)
    return PerUnitBaseProfile(**defaults)


class TestVoltageLLUnaffected:
    """Scenario 1: nominal 275 kV, L-L reference, measured 275 kV -> 1.0 pu."""

    def test_ll_reference_uses_nominal_directly(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VAB", "VBC", "VCA"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(275_000.0)
        pu = convert_value_to_pu(275_000.0, "V", resolution, VOLTAGE)
        assert pu == pytest.approx(1.0)


class TestVoltageLGCorrected:
    """Scenarios 2, 3: nominal 275 kV L-L, L-G reference -- effective
    base is 275/sqrt(3), and a ~159 kV measured value now correctly
    reads ~1.0 pu (the exact worked example from the task's own problem
    statement)."""

    def test_lg_reference_divides_nominal_by_sqrt3(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(275_000.0 / SQRT_3)
        assert resolution.base_amount == pytest.approx(158_771.0, abs=1.0)

    def test_measured_159kv_lg_channel_reads_approximately_1_0_pu(self):
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        pu = convert_value_to_pu(159_000.0, "V", resolution, VOLTAGE)
        assert pu == pytest.approx(159_000.0 / (275_000.0 / SQRT_3))
        assert pu == pytest.approx(1.0015, abs=0.001)

    def test_old_incorrect_0_577_pu_no_longer_occurs(self):
        """Direct regression against the exact defect the owner reported:
        275 kV entered, ~159 kV L-G measured previously read ~0.578 pu
        (159/275) -- it must not any more."""
        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        pu = convert_value_to_pu(159_000.0, "V", resolution, VOLTAGE)
        old_incorrect_value = 159_000.0 / 275_000.0
        assert pu != pytest.approx(old_incorrect_value, rel=0.01)
        assert pu > 0.99


class TestAutoDetectedAndManualReference:
    """Scenarios 4, 5, 6: auto-detected L-G, manual override L-G, manual
    override L-L all resolve the correct effective base."""

    def test_auto_detected_lg(self):
        profile = _profile(voltage_base_value=275.0, voltage_reference_mode=VOLTAGE_REFERENCE_MODE_AUTO)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VA", "VB", "VC"])
        assert resolution.base_amount == pytest.approx(275_000.0 / SQRT_3)

    def test_manual_override_lg(self):
        profile = _profile(
            voltage_base_value=275.0, voltage_reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL,
            voltage_reference_override=LINE_TO_GROUND,
        )
        # Channel names would auto-detect as line-to-line -- the manual
        # override must win regardless (section 7's own "engineer
        # authority" principle, unchanged by this fix).
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VAB", "VBC", "VCA"])
        assert resolution.base_amount == pytest.approx(275_000.0 / SQRT_3)

    def test_manual_override_ll(self):
        profile = _profile(
            voltage_base_value=275.0, voltage_reference_mode=VOLTAGE_REFERENCE_MODE_MANUAL,
            voltage_reference_override=LINE_TO_LINE,
        )
        # Channel names would auto-detect as line-to-ground -- the manual
        # override must win regardless.
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        assert resolution.base_amount == pytest.approx(275_000.0)


class TestChangingReferenceChangesTheDenominator:
    """Scenarios 7, 8: switching the effective reference (auto-detection
    following a channel-name change, or a manual override edit) changes
    the resolved denominator accordingly -- it is always re-derived
    live, never cached (unchanged invariant)."""

    def test_lg_to_ll_increases_the_denominator(self):
        profile = _profile(voltage_base_value=275.0)
        lg = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        ll = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VRY", "VYB", "VBR"])
        assert ll.base_amount > lg.base_amount
        assert ll.base_amount == pytest.approx(lg.base_amount * SQRT_3)

    def test_ll_to_lg_decreases_the_denominator(self):
        profile = _profile(voltage_base_value=275.0)
        ll = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VAB", "VBC", "VCA"])
        lg = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VA", "VB", "VC"])
        assert lg.base_amount < ll.base_amount
        assert lg.base_amount == pytest.approx(ll.base_amount / SQRT_3)


class TestCurrentBasePreserved:
    """Scenarios 9, 10 (critical rule): the derived current base must
    keep using the raw nominal Vbase_LL, regardless of reference -- and
    the direct/manual current-base mode is untouched by any of this
    (it never reads voltage_base_value at all)."""

    def test_derived_current_base_uses_raw_nominal_ll_not_the_lg_denominator(self):
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0, apparent_power_base_value=1000.0,
        )
        amps, reason = resolve_current_base_amps(profile, LINE_TO_GROUND)
        assert reason is None
        expected_correct = 1_000_000_000.0 / (SQRT_3 * 275_000.0)  # Sbase / (sqrt3 * 275 kV)
        expected_wrong_if_using_lg_base = 1_000_000_000.0 / (SQRT_3 * (275_000.0 / SQRT_3))
        assert amps == pytest.approx(expected_correct)
        assert amps != pytest.approx(expected_wrong_if_using_lg_base, rel=0.01)
        assert amps == pytest.approx(2099.5, abs=0.5)  # matches the Measurement Group worked example exactly

    def test_derived_current_base_identical_for_ll_reference(self):
        """Confirms scenario 9's own "must not change" framing: for the
        SAME entered nominal value, current base is now identical
        regardless of reference (LL was already correct pre-fix; LG now
        matches it, rather than the old, separately-wrong LG behaviour)."""
        profile = _profile(
            current_base_mode=CURRENT_BASE_MODE_DERIVED, voltage_base_value=275.0, apparent_power_base_value=1000.0,
        )
        lg_amps, _ = resolve_current_base_amps(profile, LINE_TO_GROUND)
        ll_amps, _ = resolve_current_base_amps(profile, LINE_TO_LINE)
        assert lg_amps == pytest.approx(ll_amps)

    def test_direct_manual_current_base_unaffected(self):
        profile = _profile(current_base_mode=CURRENT_BASE_MODE_DIRECT, direct_current_base_value=2.0995)
        amps, reason = resolve_current_base_amps(profile, LINE_TO_GROUND)
        assert reason is None
        assert amps == pytest.approx(2099.5)
        # Reference is irrelevant to direct mode -- unchanged either way.
        amps_ll, _ = resolve_current_base_amps(profile, LINE_TO_LINE)
        assert amps_ll == pytest.approx(amps)


class TestCalculatedChannelInheritsCorrectedResolution:
    """Scenario 15: a calculated channel that falls back to DEC-049
    (ungrouped input) naturally inherits the corrected Source Default
    resolution -- `resolve_per_unit()` is the SAME function, so no
    separate calculated-channel correction is needed. Also confirms
    DEC-052-shaped inheritance itself (source_id composition) is
    unaffected by this arithmetic fix."""

    def test_unary_calculated_channel_source_default_inheritance_uses_corrected_arithmetic(self):
        # derive_per_unit_profile_id() is the exact, unchanged DEC-049
        # inheritance rule (decision 6) -- a unary op inherits its single
        # input's own resolved source_id verbatim.
        input_profile_id = "src-1"
        inherited = derive_per_unit_profile_id("reverse_polarity", [input_profile_id])
        assert inherited == "src-1"

        profile = _profile(voltage_base_value=275.0)
        resolution = resolve_per_unit(VOLTAGE, profile, voltage_channel_names=["VR", "VY", "VB"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(275_000.0 / SQRT_3)
        pu = convert_value_to_pu(159_000.0, "V", resolution, VOLTAGE)
        assert pu == pytest.approx(1.0015, abs=0.001)


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, workspace_id, comtrade_fixtures_dir, stem="synth_measurement_groups"):
    cfg = (comtrade_fixtures_dir / f"{stem}.cfg").read_bytes()
    dat = (comtrade_fixtures_dir / f"{stem}.dat").read_bytes()
    files = {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }
    resp = client.post(f"/api/v1/workspaces/{workspace_id}/sources", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["source_id"]


class TestMeasurementGroupArithmeticUnchangedLiveApi:
    """Scenarios 11, 12: Measurement Group L-L and L-G arithmetic is
    untouched by this slice -- verified live against the real API."""

    def test_measurement_group_ll_unchanged(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = create_group(
            workspace_id="ws-1", source_id=source_id, kind=KIND_VOLTAGE, display_name="E275 LINE",
            channel_refs=[
                ChannelRef(kind="source", source_id=source_id, channel_name=n)
                for n in ("E275_VRY", "E275_VYB", "E275_VBR")
            ],
            status=STATUS_MANUAL,
            registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry,
        )
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry,
        )
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution", params={"channel_name": "E275_VRY"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["effective_base_amount"] == pytest.approx(275.0)

    def test_measurement_group_lg_unchanged(self, client, comtrade_fixtures_dir):
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        group = create_group(
            workspace_id="ws-1", source_id=source_id, kind=KIND_VOLTAGE, display_name="BRDC 275 kV",
            channel_refs=[
                ChannelRef(kind="source", source_id=source_id, channel_name=n)
                for n in ("N275_VR", "N275_VY", "N275_VB")
            ],
            status=STATUS_MANUAL,
            registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry,
        )
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry,
        )
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution", params={"channel_name": "N275_VR"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_grouped_channel_still_ignores_source_default_dec051(self, client, comtrade_fixtures_dir):
        """Scenario 13, verified live: DEC-051 precedence is completely
        untouched by this arithmetic fix."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}", json={"voltage_base_value": 999.0})
        group = create_group(
            workspace_id="ws-1", source_id=source_id, kind=KIND_VOLTAGE, display_name="BRDC 275 kV",
            channel_refs=[
                ChannelRef(kind="source", source_id=source_id, channel_name=n)
                for n in ("N275_VR", "N275_VY", "N275_VB")
            ],
            status=STATUS_MANUAL,
            registry=client.app.state.measurement_group_registry, source_registry=client.app.state.workspace_registry,
        )
        set_voltage_base(
            workspace_id="ws-1", measurement_group_id=group.id, nominal_voltage_ll_kv=275.0,
            group_registry=client.app.state.measurement_group_registry,
            voltage_config_registry=client.app.state.voltage_group_config_registry,
        )
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution", params={"channel_name": "N275_VR"}
        )
        body = resp.json()
        assert body["source_kind"] == "measurement_group"
        assert body["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_ungrouped_channel_uses_corrected_source_default(self, client, comtrade_fixtures_dir):
        """Scenario 14, verified live end-to-end."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 275.0, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground"},
        )
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution", params={"channel_name": "S132_VR"}
        )
        body = resp.json()
        assert body["status"] == "configured"
        assert body["source_kind"] == "source_default"
        assert body["effective_base_amount"] == pytest.approx(275.0 / SQRT_3, abs=1e-3)

    def test_provenance_reports_the_corrected_effective_source_default_base(self, client, comtrade_fixtures_dir):
        """Scenario 17: Slice 3 provenance now shows the corrected
        effective base for a Source Default L-G Voltage channel."""
        source_id = _upload(client, "ws-1", comtrade_fixtures_dir)
        client.put(
            f"/api/v1/workspaces/ws-1/per-unit/sources/{source_id}",
            json={"voltage_base_value": 275.0, "voltage_reference_mode": "manual", "voltage_reference_override": "line_to_ground"},
        )
        resp = client.get(
            f"/api/v1/workspaces/ws-1/sources/{source_id}/per-unit-resolution", params={"channel_name": "S132_VR"}
        )
        body = resp.json()
        assert body["effective_base_amount"] == pytest.approx(158.77, abs=0.01)
        assert body["effective_base_unit"] == "kV"
        # Truthfulness requirement preserved: Source Default still never
        # fabricates a separate "nominal" field the way a Measurement
        # Group does -- only the single resolved effective amount.
        assert body["nominal_base_kv"] is None
        assert body["nominal_reference"] is None
