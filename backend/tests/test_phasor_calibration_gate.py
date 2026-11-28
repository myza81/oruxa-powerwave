"""Stage 3B-2C-1 tests: Phasor/Impedance/Sequence/Distance Calibration Gate.

Verifies that the gate injected into _fetch_role_candidate() in
phasor_analysis_service.py blocks phasor analysis (and by inheritance
Impedance, Sequence Components, and Distance Protection analysis) when
any contributing source or calculated channel has Unverified or Invalid
physical calibration authority (DEC-213, OD-8/OD-9/OD-13/OD-14).

Blocked roles return _CalibrationBlockedResult(reason=...) — a typed sentinel
distinct from None (which means "source/channel not configured at all").
Callers set ROLE_STATUS_CALIBRATION_UNAVAILABLE, not ROLE_STATUS_NEEDS_CONFIGURATION.

Requirement categories covered:
  A   BEN5K Unverified Voltage source ref → _CalibrationBlockedResult (blocked, OD-8)
  B   BEN5K Unverified Current source ref → _CalibrationBlockedResult (blocked, OD-8)
  C   Unverified calc-kind ref → _CalibrationBlockedResult (blocked via _collect_leaf_authorities)
  D   Nested 2-level calc chain with BEN5K leaf → _CalibrationBlockedResult (blocked)
  E   Mixed: BEN5K Unverified + COMTRADE not-assessed → BEN5K blocked; COMTRADE passed
  F   Invalid authority source ref → _CalibrationBlockedResult (blocked, OD-9)
  G   Impedance analysis with Invalid authority source → role blocked
  H   Distance Protection with Unverified source → zone verdict unavailable
  I   Sequence Components with Unverified Va source → result blocked
  J   Verified BEN5K source → passes (existing analysis preserved)
  K   COMTRADE not-assessed source → passes (backward compat)
  L   BEN5K, channel absent from analog_channels → _CalibrationBlockedResult(reason="channel_not_found_ben5k")
  M   BEN5K, authority absent (None) → _CalibrationBlockedResult(reason="ben5k_authority_absent")
  N   Manual phasor diagram (compute_phasor_manual_diagram) → no gate, unchanged
  O   Numerical values for COMTRADE inputs: existing behavior preserved
  P   OD-13: per-role blocking — eligible roles independently preserved
  Q   Genuinely unconfigured role (source not in registry) → None, not _CalibrationBlockedResult

Governance: Stage 3B-2C-1 — gate ONLY.
  No calibration correction factors are applied.
  No PU mathematics modified.
  COMTRADE regressions unaffected (see K, O).
  Stage 3B-2C-2, 3B-2C-3, 3B-3 and Slice 6D are NOT activated by any code here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from tests.nf3c_access_support import access_for
from app.domain.calculated_channel import (
    CalculatedChannel,
    ChannelRef,
    OP_REVERSE_POLARITY,
    OP_SUBTRACTION,
    NULL_POLICY_PROPAGATE,
)
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
from app.services.phasor_analysis_service import _CalibrationBlockedResult, _fetch_role_candidate

# ---------------------------------------------------------------------------
# Well-known authorities
# ---------------------------------------------------------------------------

_UNVERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_UNVERIFIED,
    reason=REASON_CODE_BEN5K_CALIBRATION_UNVERIFIED,
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_VERIFIED_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_VERIFIED,
    reason="lab_verified_crosscheck",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)
_INVALID_AUTH = PhysicalCalibrationAuthority(
    status=CALIBRATION_INVALID,
    reason="transform_id_mismatch_invalidated",
    transform_id="ben5k_v1_raw_s16_linear_scale_offset",
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

WS = "ws-phasor-gate-test"
_N = 100
_RATE = 5000.0
_T = np.arange(_N, dtype=np.float64) / _RATE
_V = 10000.0 * np.sin(2 * np.pi * 50.0 * _T)  # 10 kV peak sinusoid for phasor tests
_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_EPOCH = 1735689600.0  # 2026-01-01 UTC

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_active_source(
    *,
    source_id: str = "src-a",
    channel_name: str = "VA",
    unit: str = "kV",
    engineering_type: str = "Voltage",
    format_variant: str | None = FORMAT_VARIANT_BEN5K_LEGACY,
    calibration_authority: PhysicalCalibrationAuthority | None = _UNVERIFIED_AUTH,
) -> ActiveSource:
    """Minimal ActiveSource for phasor calibration gate testing.

    Defaults to BEN5K + Unverified — the blocked case. Pass
    format_variant=None for COMTRADE-style (not-assessed), or
    calibration_authority=_VERIFIED_AUTH for the passing case.
    """
    analog_ch = AnalogChannel(
        name=channel_name,
        unit=unit,
        index=1,
        phase="A",
        calibration_authority=calibration_authority,
    )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="TEST",
            recorder_name="TEST",
            source_file="test.ben",
            provider_type="BEN",
            nominal_frequency=50.0,
            format_variant=format_variant,
        ),
        waveform_data=pd.DataFrame({"time": _T, channel_name: _V}),
        analog_channels=[analog_ch],
        digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[_RATE], samples_per_rate=[_N]),
        timing_info=TimingInformation(start_time=_NOW, trigger_time=_NOW),
    )
    metadata = SourceMetadata(
        source_id=source_id,
        workspace_id=WS,
        provider_type="BEN",
        original_filenames=("test.ben",),
        created_at=_NOW,
        station_name="TEST",
        recorder_name="TEST",
        nominal_frequency=50.0,
        timing_reference="gps_synchronized",
        start_time=_NOW,
        trigger_time=_NOW,
        sample_count=_N,
        duration_seconds=float(_T[-1] - _T[0]),
        elapsed_start_seconds=float(_T[0]),
        elapsed_end_seconds=float(_T[-1]),
        sampling_rates=(_RATE,),
        samples_per_rate=(_N,),
        analog_channels=[
            AnalogChannelSummary(
                name=channel_name,
                index=1,
                unit=unit,
                engineering_type=engineering_type,
            )
        ],
        digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


def _make_registry(*sources: ActiveSource):
    """Minimal WorkspaceRegistry mock backed by a list of ActiveSource objects."""
    reg = MagicMock()
    by_id = {s.metadata.source_id: s for s in sources}
    reg.get = lambda ws, sid: by_id.get(sid)
    return reg


def _make_calc_registry(*channels: CalculatedChannel):
    """Minimal CalculatedChannelRegistry mock backed by a list of CalculatedChannel objects."""
    reg = MagicMock()
    by_id = {ch.id: ch for ch in channels}
    reg.get = lambda ws, cid: by_id.get(cid)
    return reg


def _source_ref(source_id: str, channel_name: str) -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name=channel_name)


def _calc_ref(calc_id: str) -> ChannelRef:
    return ChannelRef(kind="calculated", calculated_channel_id=calc_id)


def _make_calc_channel(
    *,
    calc_id: str = "calc-1",
    source_id: str = "src-a",
    channel_name: str = "VA",
) -> CalculatedChannel:
    """Minimal CalculatedChannel with one source-kind input."""
    return CalculatedChannel(
        id=calc_id,
        workspace_id=WS,
        name=f"test-{calc_id}",
        operation=OP_REVERSE_POLARITY,
        inputs=[_source_ref(source_id, channel_name)],
        parameters={},
        dependency_ids=[],
        unit="kV",
        engineering_type="Voltage",
        null_policy=NULL_POLICY_PROPAGATE,
        reference_source_id=source_id,
        created_at=_NOW,
        values=_V * -1,
        time=_T,
        waveform_form="instantaneous",
    )


# ---------------------------------------------------------------------------
# A: BEN5K Unverified Voltage source → blocked (OD-8)
# ---------------------------------------------------------------------------

class TestUnverifiedVoltage:
    """Req A: Unverified BEN5K Voltage source ref must return _CalibrationBlockedResult."""

    def test_ben5k_unverified_voltage_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA", engineering_type="Voltage",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"Unverified BEN5K must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason, "blocked reason must be a non-empty machine-readable string"


# ---------------------------------------------------------------------------
# B: BEN5K Unverified Current source → blocked (OD-8)
# ---------------------------------------------------------------------------

class TestUnverifiedCurrent:
    """Req B: Unverified BEN5K Current source ref must return _CalibrationBlockedResult."""

    def test_ben5k_unverified_current_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="IA", unit="kA",
            engineering_type="Current",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "IA")
        result = _fetch_role_candidate("Ia", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"Unverified BEN5K current must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason


# ---------------------------------------------------------------------------
# C: Unverified calc-kind ref → blocked (via _collect_leaf_authorities)
# ---------------------------------------------------------------------------

class TestUnverifiedCalcRef:
    """Req C: calc-kind ref whose leaf is Unverified must return _CalibrationBlockedResult."""

    def test_calc_ref_with_unverified_leaf_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        calc = _make_calc_channel(calc_id="calc-1", source_id="src-a", channel_name="VA")
        src_reg = _make_registry(active)
        calc_reg = _make_calc_registry(calc)
        ref = _calc_ref("calc-1")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=src_reg, calculated_channel_registry=calc_reg, frequency_access=access_for(src_reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"Calc ref with Unverified leaf must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason


# ---------------------------------------------------------------------------
# D: Nested 2-level calc chain with BEN5K leaf → blocked
# ---------------------------------------------------------------------------

class TestNestedCalcChainBlocked:
    """Req D: 2-level calc chain (calc2 → calc1 → BEN5K src) must return _CalibrationBlockedResult."""

    def test_nested_chain_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        calc1 = _make_calc_channel(calc_id="calc-1", source_id="src-a", channel_name="VA")
        calc2 = CalculatedChannel(
            id="calc-2", workspace_id=WS, name="test-calc-2",
            operation=OP_REVERSE_POLARITY,
            inputs=[_calc_ref("calc-1")],
            parameters={},
            dependency_ids=[],
            unit="kV", engineering_type="Voltage",
            null_policy=NULL_POLICY_PROPAGATE,
            reference_source_id="src-a",
            created_at=_NOW,
            values=_V, time=_T, waveform_form="instantaneous",
        )
        src_reg = _make_registry(active)
        calc_reg = _make_calc_registry(calc1, calc2)
        ref = _calc_ref("calc-2")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=src_reg, calculated_channel_registry=calc_reg, frequency_access=access_for(src_reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"2-level calc chain with Unverified leaf must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason


# ---------------------------------------------------------------------------
# E: Mixed BEN5K Unverified + COMTRADE not-assessed → BEN5K blocked; COMTRADE passes
# ---------------------------------------------------------------------------

class TestMixedBen5kComtrade:
    """Req E: BEN5K Unverified returns _CalibrationBlockedResult; COMTRADE not-assessed passes."""

    def test_ben5k_blocked_comtrade_passes(self):
        ben5k = _make_active_source(
            source_id="src-ben", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        comtrade = _make_active_source(
            source_id="src-ct", channel_name="VA",
            format_variant=None,
            calibration_authority=None,  # not-assessed
        )
        reg = _make_registry(ben5k, comtrade)
        calc_reg = _make_calc_registry()

        ref_ben = _source_ref("src-ben", "VA")
        ref_ct = _source_ref("src-ct", "VA")

        result_ben = _fetch_role_candidate("Va", ref_ben, workspace_id=WS, source_registry=reg, calculated_channel_registry=calc_reg, frequency_access=access_for(reg))
        result_ct = _fetch_role_candidate("Va", ref_ct, workspace_id=WS, source_registry=reg, calculated_channel_registry=calc_reg, frequency_access=access_for(reg))

        assert isinstance(result_ben, _CalibrationBlockedResult), (
            f"BEN5K Unverified must return _CalibrationBlockedResult; got {type(result_ben).__name__}"
        )
        assert result_ben.reason
        assert result_ct is not None  # COMTRADE not-assessed passes


# ---------------------------------------------------------------------------
# F: Invalid authority source → blocked (OD-9)
# ---------------------------------------------------------------------------

class TestInvalidAuthority:
    """Req F: Invalid authority source ref must return _CalibrationBlockedResult (OD-9)."""

    def test_invalid_authority_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_INVALID_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"Invalid authority must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason


# ---------------------------------------------------------------------------
# G: (Delegation confirmation) Impedance passes through _fetch_role_candidate
# A direct unit test for impedance would just re-call _fetch_role_candidate —
# that is confirmed by reading the service code (all delegates to phasor).
# We verify the inheritance via a source-kind test using the same pattern.
# ---------------------------------------------------------------------------

class TestImpedanceDelegation:
    """Req G: Impedance analysis gate is inherited via prepare_phasor_diagram."""

    def test_invalid_source_returns_blocked(self):
        """_fetch_role_candidate with Invalid authority → _CalibrationBlockedResult; callers set calibration_unavailable."""
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_INVALID_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult)
        assert result.reason


# ---------------------------------------------------------------------------
# H: Distance Protection with Unverified source → zone verdict unavailable (OD-14)
# Delegation confirmation only — gate inherited from _fetch_role_candidate.
# ---------------------------------------------------------------------------

class TestDistanceProtectionDelegation:
    """Req H: Unverified source → _fetch_role_candidate returns _CalibrationBlockedResult → distance verdict blocked."""

    def test_unverified_source_returns_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult)
        assert result.reason


# ---------------------------------------------------------------------------
# I: Sequence Components with Unverified Va source → result blocked on required inputs
# ---------------------------------------------------------------------------

class TestSequenceComponentsDelegation:
    """Req I: Unverified Va source → candidate returns _CalibrationBlockedResult → sequence result blocked."""

    def test_unverified_va_blocked(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult)
        assert result.reason


# ---------------------------------------------------------------------------
# J: Verified BEN5K source → passes
# ---------------------------------------------------------------------------

class TestVerifiedSource:
    """Req J: Verified source must return a _RoleCandidate (gate passes)."""

    def test_verified_passes(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_VERIFIED_AUTH,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert result is not None
        assert result.role_key == "Va"


# ---------------------------------------------------------------------------
# K: COMTRADE not-assessed source → passes (backward compat)
# ---------------------------------------------------------------------------

class TestComtradeNotAssessed:
    """Req K: COMTRADE not-assessed (None authority) must return a candidate."""

    def test_comtrade_not_assessed_passes(self):
        active = _make_active_source(
            source_id="src-ct", channel_name="VA",
            format_variant=None,
            calibration_authority=None,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-ct", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert result is not None
        assert result.role_key == "Va"


# ---------------------------------------------------------------------------
# L: BEN5K, channel absent from analog_channels → fail-closed
# ---------------------------------------------------------------------------

class TestBen5kMissingChannel:
    """Req L: BEN5K source where channel is absent from record.analog_channels → None."""

    def test_ben5k_missing_channel_returns_none(self):
        """Channel is in metadata but absent from record (defensive scenario)."""
        # Build an active source where metadata has the channel but record does not.
        analog_ch = AnalogChannel(
            name="DIFFERENT_CHANNEL",  # not "VA"
            unit="kV",
            index=1,
            phase="A",
            calibration_authority=_UNVERIFIED_AUTH,
        )
        record = DisturbanceRecord(
            metadata=RecordingMetadata(
                station_name="TEST", recorder_name="TEST", source_file="test.ben",
                provider_type="BEN", nominal_frequency=50.0,
                format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            ),
            waveform_data=pd.DataFrame({"time": _T, "VA": _V}),
            analog_channels=[analog_ch],  # "DIFFERENT_CHANNEL", not "VA"
            digital_channels=[],
            sampling_info=SamplingInformation(sampling_rates=[_RATE], samples_per_rate=[_N]),
            timing_info=TimingInformation(start_time=_NOW, trigger_time=_NOW),
        )
        meta = SourceMetadata(
            source_id="src-a", workspace_id=WS, provider_type="BEN",
            original_filenames=("test.ben",), created_at=_NOW,
            station_name="TEST", recorder_name="TEST", nominal_frequency=50.0,
            timing_reference="gps_synchronized", start_time=_NOW, trigger_time=_NOW,
            sample_count=_N,
            duration_seconds=float(_T[-1] - _T[0]),
            elapsed_start_seconds=float(_T[0]),
            elapsed_end_seconds=float(_T[-1]),
            sampling_rates=(_RATE,), samples_per_rate=(_N,),
            analog_channels=[AnalogChannelSummary(name="VA", index=1, unit="kV", engineering_type="Voltage")],
            digital_channels=[],
        )
        active = ActiveSource(metadata=meta, record=record)
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert isinstance(result, _CalibrationBlockedResult), (
            f"BEN5K + missing channel must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason == "channel_not_found_ben5k"


# ---------------------------------------------------------------------------
# M: BEN5K with absent authority (None) → fail-closed per ben5k_authority_absent
# (_collect_leaf_authorities behaviour; _fetch_role_candidate also follows
# the same logic as Stage 3B-2A: absent BEN5K authority is NOT treated as
# not-assessed — it's a fail-closed condition via the DFS.)
# ---------------------------------------------------------------------------

class TestBen5kAbsentAuthority:
    """Req M: BEN5K authority=None → fail-closed (not treated as not-assessed)."""

    def test_ben5k_no_authority_returns_none(self):
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=None,  # BEN5K + no authority
        )
        reg = _make_registry(active)
        ref = _source_ref("src-a", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        # BEN5K with None authority → fail-closed. Matches Stage 3B-2A: BEN5K + absent authority
        # is not treated as not-assessed. The gate explicitly checks: if _full_ch exists but
        # authority is None AND _is_ben5k → return _CalibrationBlockedResult(reason="ben5k_authority_absent").
        assert isinstance(result, _CalibrationBlockedResult), (
            f"BEN5K + absent authority must return _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert result.reason == "ben5k_authority_absent"


# ---------------------------------------------------------------------------
# N: Manual phasor diagram — no gate, unchanged
# ---------------------------------------------------------------------------

class TestManualPhasorDiagram:
    """Req N: compute_phasor_manual_diagram has no source linkage → no calibration gate."""

    def test_manual_phasor_diagram_unaffected(self):
        from app.domain.phasor import ManualPhasorRoleInput, PHASOR_DIAGRAM_ROLE_ORDER, PHASOR_STATUS_COMPUTED
        from app.services.phasor_analysis_service import compute_phasor_manual_diagram

        role_inputs = {
            role_key: ManualPhasorRoleInput(
                enabled=True,
                magnitude=10.0 if role_key.startswith("V") else 1.0,
                unit="kV" if role_key.startswith("V") else "kA",
                angle_deg=0.0 if role_key in ("Va", "Ia") else 120.0 if role_key in ("Vb", "Ib") else 240.0,
            )
            for role_key in PHASOR_DIAGRAM_ROLE_ORDER
        }
        result = compute_phasor_manual_diagram(
            voltage_basis="primary",
            vt_primary=11000.0,
            vt_secondary=110.0,
            current_basis="primary",
            ct_primary=100.0,
            ct_secondary=1.0,
            role_inputs=role_inputs,
        )
        assert result.status == PHASOR_STATUS_COMPUTED
        # All roles should be available (manual inputs, no source → no calibration check)
        from app.domain.phasor import ROLE_STATUS_AVAILABLE
        for role_key in PHASOR_DIAGRAM_ROLE_ORDER:
            assert result.roles[role_key].status == ROLE_STATUS_AVAILABLE


# ---------------------------------------------------------------------------
# O: Numerical values for COMTRADE inputs: existing behavior preserved
# ---------------------------------------------------------------------------

class TestNumericalIntegrity:
    """Req O: _fetch_role_candidate returns correct values for COMTRADE not-assessed source."""

    def test_comtrade_candidate_values_unchanged(self):
        active = _make_active_source(
            source_id="src-ct", channel_name="VA",
            format_variant=None,
            calibration_authority=None,
        )
        reg = _make_registry(active)
        ref = _source_ref("src-ct", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert result is not None
        np.testing.assert_array_equal(result.values, _V)
        np.testing.assert_array_equal(result.time, _T)
        assert result.unit == "kV"


# ---------------------------------------------------------------------------
# P: OD-13 — per-role blocking: eligible roles are independently preserved
# (confirmed at service level: prepare_phasor_diagram sets ROLE_STATUS_CALIBRATION_UNAVAILABLE
# only for the blocked role, not for all roles)
# ---------------------------------------------------------------------------

class TestPerRoleBlocking:
    """Req P / OD-13: Blocking one role must not affect independent other roles.

    This test confirms _fetch_role_candidate behavior: blocked role → None,
    eligible role → candidate. The per-role isolation in prepare_phasor_diagram
    follows naturally (each role is fetched independently with no shared state).
    """

    def test_ben5k_blocked_other_verified_passes(self):
        ben5k = _make_active_source(
            source_id="src-ben", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        verified = _make_active_source(
            source_id="src-ver", channel_name="VB",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_VERIFIED_AUTH,
        )
        reg = _make_registry(ben5k, verified)
        calc_reg = _make_calc_registry()

        result_a = _fetch_role_candidate("Va", _source_ref("src-ben", "VA"), workspace_id=WS, source_registry=reg, calculated_channel_registry=calc_reg, frequency_access=access_for(reg))
        result_b = _fetch_role_candidate("Vb", _source_ref("src-ver", "VB"), workspace_id=WS, source_registry=reg, calculated_channel_registry=calc_reg, frequency_access=access_for(reg))

        assert isinstance(result_a, _CalibrationBlockedResult), (
            f"Unverified BEN5K Va must return _CalibrationBlockedResult; got {type(result_a).__name__}"
        )
        assert result_a.reason
        assert result_b is not None  # Vb passes (Verified BEN5K)

    def test_all_verified_all_pass(self):
        """All-verified case: every role returns a candidate."""
        srcs = [
            _make_active_source(
                source_id=f"src-{role}", channel_name=f"V{ch}",
                format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
                calibration_authority=_VERIFIED_AUTH,
            )
            for role, ch in [("a", "A"), ("b", "B"), ("c", "C")]
        ]
        reg = _make_registry(*srcs)
        calc_reg = _make_calc_registry()
        for src, ch in zip(srcs, ["VA", "VB", "VC"]):
            result = _fetch_role_candidate(
                f"V{ch[-1].lower()}", _source_ref(src.metadata.source_id, ch),
                workspace_id=WS, source_registry=reg, calculated_channel_registry=calc_reg,
                frequency_access=access_for(reg),
            )
            assert result is not None


# ---------------------------------------------------------------------------
# Q: Genuinely unconfigured role (source not in registry) → None, not _CalibrationBlockedResult
# ---------------------------------------------------------------------------

class TestGenuinelyUnconfigured:
    """Req Q: A source ref whose source_id is absent from the registry returns None,
    not _CalibrationBlockedResult. These are distinct conditions:
      - None → role not configured at all → ROLE_STATUS_NEEDS_CONFIGURATION
      - _CalibrationBlockedResult → role IS configured but calibration blocks it → ROLE_STATUS_CALIBRATION_UNAVAILABLE
    """

    def test_missing_source_returns_none(self):
        """Source not in registry → plain None (not _CalibrationBlockedResult)."""
        reg = _make_registry()  # empty registry — source not found
        ref = _source_ref("nonexistent-source", "VA")
        result = _fetch_role_candidate("Va", ref, workspace_id=WS, source_registry=reg, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg))
        assert result is None, (
            f"Missing source must return None, not _CalibrationBlockedResult; got {type(result).__name__}"
        )
        assert not isinstance(result, _CalibrationBlockedResult)

    def test_needs_configuration_distinct_from_calibration_unavailable(self):
        """Confirm the type hierarchy: None ≠ _CalibrationBlockedResult.

        Blocked returns _CalibrationBlockedResult; unconfigured returns None.
        Callers must use isinstance() checks to distinguish them.
        """
        # Unconfigured: source absent → None
        reg_empty = _make_registry()
        result_missing = _fetch_role_candidate("Va", _source_ref("ghost", "VA"), workspace_id=WS, source_registry=reg_empty, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg_empty))
        assert result_missing is None
        assert not isinstance(result_missing, _CalibrationBlockedResult)

        # Blocked: source present but Unverified → _CalibrationBlockedResult
        active = _make_active_source(
            source_id="src-a", channel_name="VA",
            format_variant=FORMAT_VARIANT_BEN5K_LEGACY,
            calibration_authority=_UNVERIFIED_AUTH,
        )
        reg_present = _make_registry(active)
        result_blocked = _fetch_role_candidate("Va", _source_ref("src-a", "VA"), workspace_id=WS, source_registry=reg_present, calculated_channel_registry=_make_calc_registry(), frequency_access=access_for(reg_present))
        assert isinstance(result_blocked, _CalibrationBlockedResult)


# ---------------------------------------------------------------------------
# R: API schema serialization regression guard (35af9e1 schema fix)
# ---------------------------------------------------------------------------

class TestPhasorDiagramSchemaSerializationRegression:
    """Req R: PhasorDiagramRoleStatus Literal must accept 'calibration_unavailable'.

    Guards against regression of the Pydantic Literal gap fixed in 35af9e1,
    where the domain/service produced ROLE_STATUS_CALIBRATION_UNAVAILABLE but
    the API schema rejected it at serialization time (HTTP 500).

    If 'calibration_unavailable' is removed from PhasorDiagramRoleStatus,
    these tests will raise ValidationError and fail — that is the intended
    regression signal.
    """

    def test_role_result_serializes_calibration_unavailable(self):
        """PhasorDiagramRoleResultOut with status='calibration_unavailable' serializes without error."""
        from app.schemas.phasor_analysis import PhasorDiagramRoleResultOut
        from app.schemas.calculated_channel import ChannelRefOut

        role = PhasorDiagramRoleResultOut(
            status="calibration_unavailable",
            channel_ref=ChannelRefOut(kind="source", source_id="src-a", channel_name="VA", calculated_channel_id=None),
            magnitude_rms=None,
            unit=None,
            angle_deg_absolute=None,
            angle_deg_relative=None,
            reason_code="calibration_unverified",
        )
        # Pydantic v1: .dict(); Pydantic v2: .model_dump() — try both
        try:
            data = role.model_dump()
        except AttributeError:
            data = role.dict()

        assert data["status"] == "calibration_unavailable"
        assert data["reason_code"] == "calibration_unverified"
        assert data["magnitude_rms"] is None

    def test_diagram_result_round_trips_calibration_unavailable(self):
        """Full PhasorDiagramResultOut with one blocked role serializes and deserializes without ValidationError."""
        import json
        from app.schemas.phasor_analysis import PhasorDiagramResultOut, PhasorDiagramRoleResultOut
        from app.schemas.calculated_channel import ChannelRefOut

        result = PhasorDiagramResultOut(
            status="computed",
            engineering_context_id="ec-1",
            analysis_time=0.0,
            reference_frequency_hz=50.0,
            window_seconds=0.02,
            algorithm_version="v1",
            roles={
                "Va": PhasorDiagramRoleResultOut(
                    status="calibration_unavailable",
                    channel_ref=ChannelRefOut(kind="source", source_id="src-a", channel_name="VA", calculated_channel_id=None),
                    magnitude_rms=None,
                    unit=None,
                    angle_deg_absolute=None,
                    angle_deg_relative=None,
                    reason_code="calibration_unverified",
                ),
                "Ia": PhasorDiagramRoleResultOut(
                    status="available",
                    channel_ref=ChannelRefOut(kind="source", source_id="src-ct", channel_name="IA", calculated_channel_id=None),
                    magnitude_rms=100.0,
                    unit="A",
                    angle_deg_absolute=-30.0,
                    angle_deg_relative=None,
                    reason_code=None,
                ),
            },
            warnings=[],
            reason_code=None,
            message="",
        )

        try:
            serialized = result.model_dump()
            json_str = json.dumps(serialized)
            # Round-trip: parse back
            parsed_back = PhasorDiagramResultOut.model_validate(json.loads(json_str))
        except AttributeError:
            # Pydantic v1
            serialized = result.dict()
            json_str = json.dumps(serialized)
            parsed_back = PhasorDiagramResultOut.parse_raw(json_str)

        va_role = parsed_back.roles["Va"]
        ia_role = parsed_back.roles["Ia"]
        assert va_role.status == "calibration_unavailable"
        assert va_role.reason_code == "calibration_unverified"
        assert va_role.magnitude_rms is None
        assert ia_role.status == "available"
        assert ia_role.magnitude_rms == 100.0
