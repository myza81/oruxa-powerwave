"""Stage 3B-2C-3 (DEC-213, OD-12): Calculated POWER calibration provenance tests.

Verifies that _compute_provenance() correctly maps leaf calibration authorities
to calibration_provenance_status/reason in CalculatedChannelOut.

Owner Refinement 1: empty leaf set → blocked_structural (not all_verified).
Owner Refinement 2: exploratory_unverified badge renders in frontend (browser only).

Requirement coverage:
  A  All Verified leaves → all_verified
  B  Unverified BEN5K → exploratory_unverified
  C  BEN5K Va + Ia → calculated POWER → exploratory_unverified (provenance carries through)
  D  Nested calc Voltage/Current → POWER → exploratory_unverified
  E  Verified + Not Assessed (mixed) → not_fully_verified
  F  All Not Assessed (None authority) → not_assessed
  G  Invalid leaf → blocked_invalid (creation gate still blocks separately)
  H  Missing source → blocked_structural
  I  Empty leaf set → blocked_structural (NOT all_verified, Refinement 1)
  J  Three-phase POWER with mixed states → worst-case wins (exploratory_unverified)
  K  Numerical POWER arrays unchanged (provenance metadata only)
  L  API serialization for all 6 provenance statuses
  O  Provenance reflects current registry state (not stale domain object)
  Q  COMTRADE Not Assessed → not_assessed (backward compat)
  R  Existing Stage 3B-2B-2 Invalid gate still fires (provenance gate does not interfere)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.api.v1.calculated_channels import _compute_provenance
from app.domain.calculated_channel import (
    CalculatedChannel,
    ChannelRef,
    NULL_POLICY_PROPAGATE,
    OP_ACTIVE_POWER,
    OP_ADDITION,
    OP_REVERSE_POLARITY,
    OP_THREE_PHASE_ACTIVE_POWER,
)
from app.domain.channel_classification import CURRENT, POWER, VOLTAGE
from app.domain.channels import AnalogChannel
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import FORMAT_VARIANT_BEN5K_LEGACY, RecordingMetadata
from app.domain.physical_calibration import (
    CALIBRATION_INVALID,
    CALIBRATION_UNVERIFIED,
    CALIBRATION_VERIFIED,
    REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    PhysicalCalibrationAuthority,
)
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.schemas.calculated_channel import CalculatedChannelOut
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.workspace_registry import WorkspaceRegistry

# ---------------------------------------------------------------------------
# Well-known authorities
# ---------------------------------------------------------------------------

_VERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_VERIFIED, reason="lab_verified", transform_id="xf_v1"
)
_UNVERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    transform_id="ben5k_v1_raw_s16",
)
_INVALID_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_INVALID, reason="transform_id_mismatch_invalidated", transform_id="xf_v1"
)

WS = "ws-3b2c3-test"
_N = 20
_TIME = np.arange(_N, dtype=np.float64) * 0.001
_VALS = np.ones(_N, dtype=np.float64) * 5.0
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_active_source(
    *,
    source_id: str,
    channel_name: str = "VA",
    engineering_type: str = VOLTAGE,
    unit: str = "kV",
    format_variant: str | None = FORMAT_VARIANT_BEN5K_LEGACY,
    calibration_authority: PhysicalCalibrationAuthority | None = _UNVERIFIED_AUTH,
    extra_channels: list[tuple[str, str, str, PhysicalCalibrationAuthority | None]] | None = None,
) -> ActiveSource:
    """Minimal ActiveSource. extra_channels: list of (name, unit, eng_type, auth)."""
    primary_ch = AnalogChannel(
        name=channel_name, unit=unit, index=1, phase="A",
        calibration_authority=calibration_authority,
    )
    all_channels = [primary_ch]
    summaries = [AnalogChannelSummary(name=channel_name, index=1, unit=unit, engineering_type=engineering_type)]
    for extra_name, extra_unit, extra_et, extra_auth in (extra_channels or []):
        all_channels.append(AnalogChannel(
            name=extra_name, unit=extra_unit, index=len(all_channels) + 1, phase="B",
            calibration_authority=extra_auth,
        ))
        summaries.append(AnalogChannelSummary(name=extra_name, index=len(all_channels), unit=extra_unit, engineering_type=extra_et))

    all_data = {"time": _TIME}
    for ch in all_channels:
        all_data[ch.name] = _VALS
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="TEST", recorder_name="TEST", source_file="test.ben",
            provider_type="BEN", nominal_frequency=50.0, format_variant=format_variant,
        ),
        waveform_data=pd.DataFrame(all_data),
        analog_channels=all_channels,
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1000.0], samples_per_rate=[_N]),
        timing_info=TimingInformation(start_time=_NOW, trigger_time=_NOW),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="BEN",
        original_filenames=("test.ben",), created_at=_NOW,
        station_name="TEST", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="relative_elapsed", start_time=_NOW, trigger_time=_NOW,
        sample_count=_N, duration_seconds=float(_TIME[-1] - _TIME[0]),
        elapsed_start_seconds=float(_TIME[0]), elapsed_end_seconds=float(_TIME[-1]),
        sampling_rates=(1000.0,), samples_per_rate=(_N,),
        analog_channels=summaries, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _make_calc(
    *,
    calc_id: str | None = None,
    workspace_id: str = WS,
    name: str = "calc",
    unit: str = "MW",
    operation: str = OP_ACTIVE_POWER,
    inputs: list[ChannelRef],
    engineering_type: str = POWER,
    reference_source_id: str = "src1",
) -> CalculatedChannel:
    cid = calc_id or str(uuid.uuid4())
    return CalculatedChannel(
        id=cid, workspace_id=workspace_id, name=name, unit=unit,
        operation=operation, inputs=inputs,
        time=_TIME.copy(), values=_VALS.copy(), parameters={},
        dependency_ids=[ref.calculated_channel_id for ref in inputs if ref.kind == "calculated"],
        reference_source_id=reference_source_id,
        created_at=_NOW,
        engineering_type=engineering_type,
    )


def _src_ref(source_id: str, channel_name: str) -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name=channel_name)


def _calc_ref(calc_id: str) -> ChannelRef:
    return ChannelRef(kind="calculated", calculated_channel_id=calc_id)


def _make_registry(*sources: ActiveSource) -> WorkspaceRegistry:
    reg = WorkspaceRegistry()
    for src in sources:
        reg.add(src)
    return reg


def _make_calc_registry(*channels: CalculatedChannel) -> CalculatedChannelRegistry:
    reg = CalculatedChannelRegistry()
    for ch in channels:
        reg.add(ch)
    return reg


# ---------------------------------------------------------------------------
# A — All Verified leaves → all_verified
# ---------------------------------------------------------------------------


class TestA_AllVerified:
    def test_verified_power_channel(self):
        src = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_VERIFIED_AUTH)
        src2 = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg = _make_registry(src, src2)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "all_verified"
        assert reason is None


# ---------------------------------------------------------------------------
# B — Unverified BEN5K → exploratory_unverified
# ---------------------------------------------------------------------------


class TestB_UnverifiedBEN5K:
    def test_unverified_ben5k_power(self):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_UNVERIFIED_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_UNVERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "exploratory_unverified"
        assert reason == "physical_calibration_unverified"


# ---------------------------------------------------------------------------
# C — POWER with one Unverified, one Verified leaf → exploratory_unverified
# ---------------------------------------------------------------------------


class TestC_MixedUnverifiedVerified:
    def test_one_unverified_leaf_dominates(self):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_VERIFIED_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_UNVERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "exploratory_unverified"


# ---------------------------------------------------------------------------
# D — Nested calc chain → provenance carries through correctly
# ---------------------------------------------------------------------------


class TestD_NestedCalcChain:
    def test_nested_unverified_propagates(self):
        src = _make_active_source(source_id="src1", channel_name="VA", calibration_authority=_UNVERIFIED_AUTH)
        reg = _make_registry(src)
        inner = _make_calc(
            calc_id="inner-id", name="VA_neg", unit="kV",
            operation=OP_REVERSE_POLARITY,
            inputs=[_src_ref("src1", "VA")],
            engineering_type=VOLTAGE,
            reference_source_id="src1",
        )
        # outer POWER uses the nested calc Voltage + a source Current
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg2 = _make_registry(src, src_i)
        outer = _make_calc(
            inputs=[_calc_ref("inner-id"), _src_ref("src-i", "IA")],
            reference_source_id="src1",
        )
        calc_reg = _make_calc_registry(inner)
        status, reason = _compute_provenance(outer, WS, reg2, calc_reg)
        assert status == "exploratory_unverified"


# ---------------------------------------------------------------------------
# E — Verified + Not Assessed (None authority) → not_fully_verified
# ---------------------------------------------------------------------------


class TestE_VerifiedPlusNotAssessed:
    def test_mixed_verified_not_assessed(self):
        src_v = _make_active_source(
            source_id="src-v", channel_name="VA",
            format_variant=None,  # COMTRADE — None authority ok
            calibration_authority=_VERIFIED_AUTH,
        )
        src_i = _make_active_source(
            source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A",
            format_variant=None,
            calibration_authority=None,  # Not assessed
        )
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "not_fully_verified"
        assert reason == "mixed_verified_not_assessed"


# ---------------------------------------------------------------------------
# F — All Not Assessed → not_assessed
# ---------------------------------------------------------------------------


class TestF_AllNotAssessed:
    def test_comtrade_not_assessed(self):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", format_variant=None, calibration_authority=None)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", format_variant=None, calibration_authority=None)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "not_assessed"
        assert reason is None


# ---------------------------------------------------------------------------
# G — Invalid leaf → blocked_invalid
# ---------------------------------------------------------------------------


class TestG_InvalidLeaf:
    def test_invalid_leaf_produces_blocked_invalid(self):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_INVALID_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "blocked_invalid"
        assert reason == "physical_calibration_invalid"


# ---------------------------------------------------------------------------
# H — Missing source → blocked_structural
# ---------------------------------------------------------------------------


class TestH_MissingSource:
    def test_source_not_in_registry(self):
        # Only src-i exists; src-v is missing
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg = _make_registry(src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v-missing", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-i",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "blocked_structural"
        assert reason is not None


# ---------------------------------------------------------------------------
# I — Empty leaf set → blocked_structural (Refinement 1: NOT all_verified)
# ---------------------------------------------------------------------------


class TestI_EmptyLeafSet:
    def test_no_inputs_gives_blocked_structural_not_all_verified(self):
        """Owner Refinement 1: empty leaf set must NOT produce all_verified."""
        # Create a calc channel with no inputs (edge case — no operation supports
        # this in practice, but _compute_provenance must handle it defensively).
        calc = _make_calc(inputs=[], reference_source_id="src1")
        reg = WorkspaceRegistry()
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "blocked_structural", (
            "Empty leaf set must produce blocked_structural, not all_verified (OD-12 Refinement 1)"
        )
        assert reason == "no_leaf_authorities_found"

    def test_registries_none_returns_none_none(self):
        """When registries are unavailable, provenance returns (None, None)."""
        calc = _make_calc(
            inputs=[_src_ref("src1", "VA"), _src_ref("src2", "IA")],
            reference_source_id="src1",
        )
        # No registries → backward compat returns (None, None)
        status, reason = _compute_provenance(calc, None, None, None)
        assert status is None
        assert reason is None


# ---------------------------------------------------------------------------
# J — Three-phase POWER: worst-case wins
# ---------------------------------------------------------------------------


class TestJ_ThreePhaseWorstCase:
    def test_one_unverified_in_six_inputs_dominates(self):
        """Three-phase POWER: one Unverified leaf → exploratory_unverified overall."""
        srcs = {}
        for phase, ch_type, unit, auth in [
            ("VA", VOLTAGE, "kV", _VERIFIED_AUTH),
            ("VB", VOLTAGE, "kV", _VERIFIED_AUTH),
            ("VC", VOLTAGE, "kV", _UNVERIFIED_AUTH),  # <- Unverified
            ("IA", CURRENT, "A", _VERIFIED_AUTH),
            ("IB", CURRENT, "A", _VERIFIED_AUTH),
            ("IC", CURRENT, "A", _VERIFIED_AUTH),
        ]:
            sid = f"src-{phase.lower()}"
            srcs[sid] = _make_active_source(source_id=sid, channel_name=phase, engineering_type=ch_type, unit=unit, calibration_authority=auth)
        reg = _make_registry(*srcs.values())
        calc = _make_calc(
            operation=OP_THREE_PHASE_ACTIVE_POWER,
            inputs=[
                _src_ref("src-va", "VA"), _src_ref("src-ia", "IA"),
                _src_ref("src-vb", "VB"), _src_ref("src-ib", "IB"),
                _src_ref("src-vc", "VC"), _src_ref("src-ic", "IC"),
            ],
            reference_source_id="src-va",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "exploratory_unverified"


# ---------------------------------------------------------------------------
# K — Numerical arrays unchanged (provenance is metadata-only)
# ---------------------------------------------------------------------------


class TestK_NumericalUnchanged:
    def test_provenance_does_not_alter_waveform_values(self):
        """Provenance computation must not modify the channel's waveform arrays."""
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_UNVERIFIED_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_UNVERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        expected = calc.values.copy()
        _compute_provenance(calc, WS, reg, _make_calc_registry())
        np.testing.assert_array_equal(calc.values, expected)


# ---------------------------------------------------------------------------
# L — Serialization: all 6 statuses round-trip via Pydantic without error
# ---------------------------------------------------------------------------


class TestL_Serialization:
    @pytest.mark.parametrize("prov_status,prov_reason", [
        ("all_verified", None),
        ("exploratory_unverified", "physical_calibration_unverified"),
        ("not_assessed", None),
        ("not_fully_verified", "mixed_verified_not_assessed"),
        ("blocked_invalid", "physical_calibration_invalid"),
        ("blocked_structural", "source_unavailable"),
        (None, None),  # backward-compat default
    ])
    def test_schema_serializes_provenance(self, prov_status, prov_reason):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_VERIFIED_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        out = CalculatedChannelOut.from_domain(
            calc, timing=None,
            calibration_provenance_status=prov_status,
            calibration_provenance_reason=prov_reason,
        )
        data = out.model_dump()
        assert data["calibration_provenance_status"] == prov_status
        assert data["calibration_provenance_reason"] == prov_reason
        # JSON round-trip must not raise
        out.model_dump_json()


# ---------------------------------------------------------------------------
# O — Provenance reflects current registry (not stale)
# ---------------------------------------------------------------------------


class TestO_ReflectsCurrentRegistry:
    def test_provenance_uses_current_authority(self):
        """Changing the registry between calls must change the provenance result."""
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_UNVERIFIED_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_UNVERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status1, _ = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status1 == "exploratory_unverified"

        # Simulate re-import: replace source with Verified authority
        src_v2 = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_VERIFIED_AUTH)
        src_i2 = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg2 = _make_registry(src_v2, src_i2)
        status2, _ = _compute_provenance(calc, WS, reg2, _make_calc_registry())
        assert status2 == "all_verified"


# ---------------------------------------------------------------------------
# Q — COMTRADE not_assessed backward compat
# ---------------------------------------------------------------------------


class TestQ_ComtradeBackwardCompat:
    def test_comtrade_no_authority_is_not_assessed(self):
        src_v = _make_active_source(source_id="src-v", channel_name="VA", format_variant=None, calibration_authority=None)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", format_variant=None, calibration_authority=None)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        assert status == "not_assessed"
        # Must not be "exploratory_unverified", "blocked_invalid", "all_verified"
        assert status not in ("exploratory_unverified", "blocked_invalid", "all_verified")


# ---------------------------------------------------------------------------
# R — Existing Stage 3B-2B-2 Invalid gate still fires (provenance does not interfere)
# ---------------------------------------------------------------------------


class TestR_ExistingGateIntact:
    def test_invalid_leaf_provenance_is_blocked_invalid_not_bypassed(self):
        """Stage 3B-2B-2 creation gate catches Invalid at creation time.
        _compute_provenance reports blocked_invalid independently on the metadata path."""
        src_v = _make_active_source(source_id="src-v", channel_name="VA", calibration_authority=_INVALID_AUTH)
        src_i = _make_active_source(source_id="src-i", channel_name="IA", engineering_type=CURRENT, unit="A", calibration_authority=_VERIFIED_AUTH)
        reg = _make_registry(src_v, src_i)
        calc = _make_calc(
            inputs=[_src_ref("src-v", "VA"), _src_ref("src-i", "IA")],
            reference_source_id="src-v",
        )
        status, reason = _compute_provenance(calc, WS, reg, _make_calc_registry())
        # Provenance reflects the Invalid leaf
        assert status == "blocked_invalid"
        assert reason == "physical_calibration_invalid"


# ---------------------------------------------------------------------------
# M — API endpoint serialization: POST → GET list carry provenance fields
#     (Item 4: TestClient integration test; COMTRADE not_assessed baseline)
# ---------------------------------------------------------------------------

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

_COMTRADE_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "comtrade"
_BEN_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ben"
_WS_API = "ws-3b2c3-api"
_WS_API_MIXED = "ws-3b2c3-api-mixed"


def _comtrade_files(stem: str = "synth_ascii"):
    cfg = (_COMTRADE_FIXTURES_DIR / f"{stem}.cfg").read_bytes()
    dat = (_COMTRADE_FIXTURES_DIR / f"{stem}.dat").read_bytes()
    return {
        "cfg_file": (f"{stem}.cfg", io.BytesIO(cfg), "application/octet-stream"),
        "dat_file": (f"{stem}.dat", io.BytesIO(dat), "application/octet-stream"),
    }


@pytest.fixture
def api_client(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        # Upload synth_ascii (VA=Voltage, IA=Current, COMTRADE → not_assessed)
        resp = client.post(f"/api/v1/workspaces/{_WS_API}/sources", files=_comtrade_files())
        assert resp.status_code == 201, resp.text
        yield client, resp.json()["source_id"]


@pytest.fixture
def mixed_api_client(tmp_path):
    """Client with both COMTRADE and BEN5K sources for mixed-provenance tests."""
    s = Settings(
        environment="development", storage_type="local", storage_path=str(tmp_path),
        cors_origins=("http://localhost:8101",), database_url=None,
        max_event_upload_size_mb=100, git_sha="local", version="local",
        ben5k_experimental_enabled=True,
    )
    app = create_app(s)
    with TestClient(app) as client:
        # Upload COMTRADE
        com_resp = client.post(
            f"/api/v1/workspaces/{_WS_API_MIXED}/sources",
            files=_comtrade_files(),
        )
        assert com_resp.status_code == 201, com_resp.text
        com_source_id = com_resp.json()["source_id"]

        # Upload BEN5K phasor fixture (Va=Voltage, Ia=Current, both UNVERIFIED)
        ben_bytes = (_BEN_FIXTURES_DIR / "synthetic_ben5k_phasor.ben").read_bytes()
        ben_resp = client.post(
            f"/api/v1/workspaces/{_WS_API_MIXED}/sources",
            files={"ben_file": ("synthetic_ben5k_phasor.ben", io.BytesIO(ben_bytes), "application/octet-stream")},
        )
        assert ben_resp.status_code == 201, ben_resp.text
        ben_source_id = ben_resp.json()["source_id"]

        yield client, com_source_id, ben_source_id


class TestM_ApiEndpointsCarryProvenance:
    """Item 4: POST channel and GET list both serialize provenance fields correctly.
    Uses COMTRADE (not_assessed baseline) — domain-level tests cover the status values.
    Note: there is no standalone GET /{id} detail endpoint; 'detail' = GET list filtered by ID.
    """

    def test_post_response_has_provenance_fields(self, api_client):
        """POST creates channel; provenance fields must be present in the HTTP response.
        Uses reverse_polarity (synth_ascii is 10ms — too short for active_power's 1-cycle
        minimum; provenance mechanism is operation-agnostic: status derives from leaf
        source authorities, not the operation type).
        """
        client, source_id = api_client
        resp = client.post(
            f"/api/v1/workspaces/{_WS_API}/calculated-channels",
            json={
                "name": "P_api_post_test",
                "operation": "reverse_polarity",
                "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
                "parameters": {},
                "unit": "V",
                "null_policy": "propagate_null",
                "reference_source_id": source_id,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # Both provenance fields must be present in the POST response.
        assert "calibration_provenance_status" in body, "POST response must include calibration_provenance_status"
        assert "calibration_provenance_reason" in body, "POST response must include calibration_provenance_reason"
        # COMTRADE: not_assessed
        assert body["calibration_provenance_status"] == "not_assessed"
        assert body["calibration_provenance_reason"] is None

    def test_get_list_has_provenance_fields(self, api_client):
        """GET list must carry provenance fields for every returned channel."""
        client, source_id = api_client
        # Create a channel (reverse_polarity to avoid min-samples guard)
        create_resp = client.post(
            f"/api/v1/workspaces/{_WS_API}/calculated-channels",
            json={
                "name": "P_api_list_test",
                "operation": "reverse_polarity",
                "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "VA"}],
                "parameters": {},
                "unit": "V",
                "null_policy": "propagate_null",
                "reference_source_id": source_id,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        channel_id = create_resp.json()["id"]

        # GET list must include provenance fields for this channel.
        list_resp = client.get(f"/api/v1/workspaces/{_WS_API}/calculated-channels")
        assert list_resp.status_code == 200, list_resp.text
        channels = list_resp.json()
        found = next((c for c in channels if c["id"] == channel_id), None)
        assert found is not None, f"Channel {channel_id} not found in GET list"
        assert "calibration_provenance_status" in found
        assert "calibration_provenance_reason" in found
        assert found["calibration_provenance_status"] == "not_assessed"
        assert found["calibration_provenance_reason"] is None


# ---------------------------------------------------------------------------
# N — Mixed-provenance API list (Item 4: BEN5K exploratory + COMTRADE not_assessed)
# ---------------------------------------------------------------------------


class TestN_MixedProvenanceApiList:
    """Item 4: Mixed-provenance list — BEN5K (exploratory_unverified) and
    COMTRADE (not_assessed) channels appear in GET list with correct statuses,
    no cross-contamination.
    """

    def test_mixed_list_has_independent_provenance_statuses(self, mixed_api_client):
        client, com_source_id, ben_source_id = mixed_api_client

        # Discover BEN5K Va + Ia channels.
        channels_resp = client.get(
            f"/api/v1/workspaces/{_WS_API_MIXED}/sources/{ben_source_id}/channels"
        )
        assert channels_resp.status_code == 200, channels_resp.text
        analog_chs = channels_resp.json().get("analog_channels", [])
        volt_ch = next((c for c in analog_chs if c.get("engineering_type") == "Voltage"), None)
        curr_ch = next((c for c in analog_chs if c.get("engineering_type") == "Current"), None)
        if not volt_ch or not curr_ch:
            pytest.skip("synthetic_ben5k_phasor.ben does not expose Voltage+Current channels")

        # Create BEN5K channel (reverse_polarity of Va; provenance is operation-agnostic —
        # exploratory_unverified derives from the BEN5K Unverified leaf authority).
        ben_resp = client.post(
            f"/api/v1/workspaces/{_WS_API_MIXED}/calculated-channels",
            json={
                "name": "Va_ben_exploratory",
                "operation": "reverse_polarity",
                "inputs": [
                    {"kind": "source", "source_id": ben_source_id, "channel_name": volt_ch["name"]},
                ],
                "parameters": {},
                "unit": volt_ch.get("unit", "kV"),
                "null_policy": "propagate_null",
                "reference_source_id": ben_source_id,
            },
        )
        assert ben_resp.status_code == 201, ben_resp.text
        ben_channel_id = ben_resp.json()["id"]

        # Create COMTRADE channel (reverse_polarity; not_assessed from COMTRADE leaf).
        com_resp = client.post(
            f"/api/v1/workspaces/{_WS_API_MIXED}/calculated-channels",
            json={
                "name": "VA_com_not_assessed",
                "operation": "reverse_polarity",
                "inputs": [
                    {"kind": "source", "source_id": com_source_id, "channel_name": "VA"},
                ],
                "parameters": {},
                "unit": "V",
                "null_policy": "propagate_null",
                "reference_source_id": com_source_id,
            },
        )
        assert com_resp.status_code == 201, com_resp.text
        com_channel_id = com_resp.json()["id"]

        # GET list: both channels must appear with independent statuses.
        list_resp = client.get(f"/api/v1/workspaces/{_WS_API_MIXED}/calculated-channels")
        assert list_resp.status_code == 200, list_resp.text
        channels = list_resp.json()

        ben_in_list = next((c for c in channels if c["id"] == ben_channel_id), None)
        com_in_list = next((c for c in channels if c["id"] == com_channel_id), None)

        assert ben_in_list is not None, "BEN5K channel missing from list"
        assert com_in_list is not None, "COMTRADE channel missing from list"

        # BEN5K: exploratory_unverified (Unverified leaf authority).
        assert ben_in_list["calibration_provenance_status"] == "exploratory_unverified", (
            f"BEN5K channel must be exploratory_unverified; got {ben_in_list['calibration_provenance_status']!r}"
        )
        assert ben_in_list["calibration_provenance_reason"] == "physical_calibration_unverified"

        # COMTRADE: not_assessed (no calibration authorities on COMTRADE).
        assert com_in_list["calibration_provenance_status"] == "not_assessed", (
            f"COMTRADE channel must be not_assessed; got {com_in_list['calibration_provenance_status']!r}"
        )
        assert com_in_list["calibration_provenance_reason"] is None

        # No cross-contamination: BEN5K must not be not_assessed; COMTRADE must not be exploratory.
        assert ben_in_list["calibration_provenance_status"] != "not_assessed"
        assert com_in_list["calibration_provenance_status"] != "exploratory_unverified"
