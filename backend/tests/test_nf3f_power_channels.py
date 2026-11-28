"""NF-3F (O-2) -- power channels take their frequency from the central nominal-frequency authority.

Owner decision (2026-11-28): single- and three-phase power channels use the effective nominal frequency of the recording that supplies their
inputs for the phasor window, the prerequisite gates and the stored `nominal_frequency_hz`; voltage and current must agree (one frequency,
never one chosen from several); disagreement is refused with HTTP 400 `nominal_frequency_mixed`; an unusable frequency keeps the existing
`invalid_nominal_frequency` refusal; a new channel is recording-following (NF-3E provenance and staleness) and stored values are never
recomputed. The power MATHEMATICS is unchanged.

Acceptance contract (owner, 2026-11-28)
* PRIMARY: the channel is bit-for-bit what the unmodified kernel returns when called directly with the intended frequency (section 5.1).
* 50 Hz recordings are bit-identical to the pre-migration behaviour (the no-authority path is the pre-migration code path).
* Independent oracle (the closed form, never the code under test): V = 100 kV peak, I = 1 kA peak, current lagging 30 degrees, so
  P = 43.3013 MW and Q = 25 Mvar. Integer samples per cycle: relative error <= 1e-9. Non-integer samples per cycle and the strict-xfail
  oracle of NF-3B: relative error <= 1e-3. The documented ripple of the non-integer cases is fixture evidence, not a requirement here.
"""

from __future__ import annotations

import ast
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.calculated_channel import (
    OP_ACTIVE_POWER,
    OP_REACTIVE_POWER,
    OP_THREE_PHASE_ACTIVE_POWER,
    OP_THREE_PHASE_REACTIVE_POWER,
    ChannelRef,
    evaluate_power_channel,
    evaluate_three_phase_power_channel,
)
from app.domain.channel_classification import WAVEFORM_FORM_UNKNOWN
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.main import create_app
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.calculated_channel_staleness import frequency_staleness
from app.services.errors import (
    InvalidNominalFrequencyError,
    MixedNominalFrequencyError,
    RmsRecordingTooShortError,
    RmsSamplingTooSparseError,
)
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests import nf3b_baseline_scenarios as scn
from tests import nf3d_baseline_scenarios as nf3d
from tests import nf3e_baseline_scenarios as nf3e
from tests.nf3c_access_support import access_for

APP_DIR = Path(__file__).resolve().parents[1] / "app"
WS = scn.WS
P_MW = 0.5 * 100e3 * 1e3 * math.cos(math.radians(30.0)) / 1e6          # 43.3013 MW
Q_MVAR = 0.5 * 100e3 * 1e3 * math.sin(math.radians(30.0)) / 1e6        # 25.0 Mvar
COMTRADE = {"source_format": "COMTRADE"}
ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}


# ------------------------------------------------------------------------------------------------------------------ fixtures
def single(source_id, nominal, f_sig, *, fs=4800.0, seconds=1.0, provenance=COMTRADE, with_voltage=True):
    return scn.build_source(source_id, nominal, provenance, f_sig, fs=fs, seconds=seconds, with_voltage=with_voltage)


def three_phase(source_id, nominal, f_sig, *, fs=4800.0, seconds=1.0, provenance=COMTRADE):
    """VA/VB/VC at 100 kV peak, IA/IB/IC at 1 kA peak lagging 30 degrees, phases 120 degrees apart (a balanced load)."""
    t = np.arange(int(round(fs * seconds)) + 1) / fs
    channels, units, types = {}, {}, {}
    for k, phase in enumerate("ABC"):
        shift = math.radians(-120.0 * k)
        channels[f"V{phase}"] = 100e3 * np.cos(2 * np.pi * f_sig * t + shift)
        channels[f"I{phase}"] = 1e3 * np.cos(2 * np.pi * f_sig * t + shift - math.radians(30.0))
        units[f"V{phase}"], types[f"V{phase}"] = "V", "Voltage"
        units[f"I{phase}"], types[f"I{phase}"] = "A", "Current"
    record = DisturbanceRecord(
        metadata=RecordingMetadata(station_name="S", recorder_name="R", source_file="s.cfg", provider_type="COMTRADE",
                                   nominal_frequency=nominal),
        waveform_data=pd.DataFrame({"time": t, **channels}), analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(t)]),
        timing_info=TimingInformation(start_time=scn.START, trigger_time=scn.START))
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE", original_filenames=("s.cfg", "s.dat"), created_at=scn.START,
        station_name="S", recorder_name="R", nominal_frequency=nominal, timing_reference="absolute", start_time=scn.START,
        trigger_time=scn.START, sample_count=len(t), duration_seconds=float(t[-1] - t[0]), elapsed_start_seconds=float(t[0]),
        elapsed_end_seconds=float(t[-1]), sampling_rates=(1.0,), samples_per_rate=(len(t),),
        analog_channels=[AnalogChannelSummary(name=n, index=k, unit=units[n], engineering_type=types[n],
                                              waveform_form=WAVEFORM_FORM_UNKNOWN) for k, n in enumerate(channels)],
        digital_channels=[], preparation_provenance=dict(provenance))
    return ActiveSource(metadata=metadata, record=record)


def ref(source_id, name):
    return ChannelRef(kind="source", source_id=source_id, channel_name=name)


def make(sources, calcs, operation, inputs, access, name="P", **extra):
    return create_calculated_channel(
        workspace_id=WS, name=name, operation=operation, parameters={}, source_registry=sources, calc_registry=calcs,
        inputs=inputs, frequency_access=access, **extra)


def world(*specs):
    """`specs`: (source_id, source) pairs. Returns (sources, calcs, registry)."""
    sources, calcs, registry = WorkspaceRegistry(), CalculatedChannelRegistry(), NominalFrequencyRegistry()
    for _id, source in specs:
        sources.add(source)
    return sources, calcs, registry


def series(source, name):
    frame = source.record.waveform_data
    return np.asarray(frame["time"]), np.asarray(frame[name])


def kernel_single(source, operation, hz):
    """The UNMODIFIED kernel called directly with the intended frequency (section 5.1)."""
    t, v = series(source, "VA")
    _, i = series(source, "IA")
    return evaluate_power_channel(operation, v_time=t, v_values=v, v_scale_to_si=1.0, i_values=i, i_scale_to_si=1.0, nominal_frequency_hz=hz)


def steady(channel, source_time_min=0.1):
    t = np.asarray(channel.time)
    return np.isfinite(channel.values) & (t >= source_time_min)


def rel_error(values, expected):
    return np.abs(np.asarray(values) / expected - 1.0)


# ================================================================================================================ the primary criterion
class TestBitIdenticalToTheKernelCalledDirectly:
    @pytest.mark.parametrize("operation", [OP_ACTIVE_POWER, OP_REACTIVE_POWER])
    @pytest.mark.parametrize("label,nominal,f_sig,fs,provenance", [
        ("50 Hz declared, 4800 Hz", 50.0, 50.0, 4800.0, COMTRADE),
        ("60 Hz declared, 4800 Hz", 60.0, 60.0, 4800.0, COMTRADE),
        ("60 Hz declared, 5000 Hz (non-integer cycle)", 60.0, 60.0, 5000.0, COMTRADE),
        ("60 Hz declared, 4096 Hz (non-integer cycle)", 60.0, 60.0, 4096.0, COMTRADE),
        ("50 Hz declared, 4096 Hz (non-integer cycle)", 50.0, 50.0, 4096.0, COMTRADE),
        ("assumed 50 Hz default", 50.0, 50.0, 4800.0, ASSUMED),
        ("declared 50 Hz on a 60 Hz signal", 50.0, 60.0, 4800.0, COMTRADE),
    ])
    def test_auto_frequency(self, operation, label, nominal, f_sig, fs, provenance):
        source = single("src", nominal, f_sig, fs=fs, provenance=provenance)
        sources, calcs, _ = world(("src", source))
        channel = make(sources, calcs, operation, [ref("src", "VA"), ref("src", "IA")], access_for(sources))
        assert channel.parameters["nominal_frequency_hz"] == nominal
        assert np.array_equal(channel.values, kernel_single(source, operation, nominal), equal_nan=True), label

    @pytest.mark.parametrize("recording_hz,manual_hz", [(50.0, 60.0), (60.0, 50.0)])
    def test_manual_frequency_is_the_one_used(self, recording_hz, manual_hz):
        source = single("src", recording_hz, recording_hz)
        sources, calcs, registry = world(("src", source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        access.set_manual(WS, "src", manual_hz)
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access)
        assert channel.parameters["nominal_frequency_hz"] == manual_hz
        assert (channel.parameters["nominal_frequency_origin"], channel.parameters["nominal_frequency_revision"]) == ("manual", 1)
        assert np.array_equal(channel.values, kernel_single(source, OP_ACTIVE_POWER, manual_hz), equal_nan=True)
        assert not np.array_equal(channel.values, kernel_single(source, OP_ACTIVE_POWER, recording_hz), equal_nan=True)

    @pytest.mark.parametrize("operation", [OP_THREE_PHASE_ACTIVE_POWER, OP_THREE_PHASE_REACTIVE_POWER])
    @pytest.mark.parametrize("nominal,fs", [(50.0, 4800.0), (60.0, 4800.0), (60.0, 5000.0)])
    def test_three_phase(self, operation, nominal, fs):
        source = three_phase("src", nominal, nominal, fs=fs)
        sources, calcs, _ = world(("src", source))
        names = ["VA", "IA", "VB", "IB", "VC", "IC"]
        channel = make(sources, calcs, operation, [ref("src", n) for n in names], access_for(sources))
        data = {n: series(source, n)[1] for n in names}
        direct = evaluate_three_phase_power_channel(
            operation, time=series(source, "VA")[0], v1_values=data["VA"], v1_scale_to_si=1.0, i1_values=data["IA"], i1_scale_to_si=1.0,
            v2_values=data["VB"], v2_scale_to_si=1.0, i2_values=data["IB"], i2_scale_to_si=1.0,
            v3_values=data["VC"], v3_scale_to_si=1.0, i3_values=data["IC"], i3_scale_to_si=1.0, nominal_frequency_hz=nominal)
        assert channel.parameters["nominal_frequency_hz"] == nominal
        assert np.array_equal(channel.values, direct, equal_nan=True)


class TestFiftyHertzIsPreserved:
    @pytest.mark.parametrize("operation", [OP_ACTIVE_POWER, OP_REACTIVE_POWER])
    @pytest.mark.parametrize("fs", [4800.0, 5000.0, 4096.0])
    def test_a_50hz_recording_is_bit_identical_to_the_pre_migration_path(self, operation, fs):
        # With no authority supplied the service takes the pre-migration path (the one sanctioned 50 Hz default): the reference
        # for "bit-identical to the frozen baseline" (the frozen JSON baselines are checked in test_nf3b_frozen_baselines too).
        source = single("src", 50.0, 50.0, fs=fs)
        sources, calcs, _ = world(("src", source))
        migrated = make(sources, calcs, operation, [ref("src", "VA"), ref("src", "IA")], access_for(sources), name="new")
        legacy = make(sources, calcs, operation, [ref("src", "VA"), ref("src", "IA")], None, name="legacy")
        assert np.array_equal(migrated.values, legacy.values, equal_nan=True)
        assert np.array_equal(migrated.time, legacy.time)

    def test_a_caller_without_the_authority_gets_the_historical_stored_shape(self):
        source = single("src", 60.0, 60.0)
        sources, calcs, _ = world(("src", source))
        legacy = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], None)
        assert legacy.parameters == {"nominal_frequency_hz": 50.0, "window_mode": "trailing", "sign_convention": "passive"}


# ================================================================================================================ independent oracle (5.5)
class TestGoldenVectors:
    """NF-3A section 5.5 against the closed form. The rows are signal frequency at window frequency."""

    @pytest.mark.parametrize("nominal,fs", [(50.0, 4800.0), (50.0, 5000.0), (60.0, 4800.0)])
    def test_integer_cycle_records_match_the_closed_form_to_1e_9(self, nominal, fs):
        source = single("src", nominal, nominal, fs=fs)
        sources, calcs, _ = world(("src", source))
        access = access_for(sources)
        p = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access, name="P")
        q = make(sources, calcs, OP_REACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access, name="Q")
        assert rel_error(np.asarray(p.values)[steady(p)], P_MW).max() <= 1e-9
        assert rel_error(np.asarray(q.values)[steady(q)], Q_MVAR).max() <= 1e-9

    @pytest.mark.parametrize("fs", [5000.0, 4096.0])
    def test_a_60hz_non_integer_cycle_record_is_within_the_accepted_1e_3(self, fs):
        source = single("src", 60.0, 60.0, fs=fs)
        sources, calcs, _ = world(("src", source))
        access = access_for(sources)
        p = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access, name="P")
        q = make(sources, calcs, OP_REACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access, name="Q")
        assert rel_error(np.asarray(p.values)[steady(p)], P_MW).max() < 1e-3 * 25      # the ripple allowance of a non-integer window
        assert abs(np.mean(np.asarray(p.values)[steady(p)]) / P_MW - 1.0) < 1e-3
        assert abs(np.mean(np.asarray(q.values)[steady(q)]) / Q_MVAR - 1.0) < 1e-3

    def test_the_documented_defect_row_is_what_the_old_fixed_window_gives_and_the_frequency_is_what_removes_it(self):
        # 60 Hz signal, 50 Hz window (what every 60 Hz recording received before NF-3F): P about -11.8 %, Q about -13.2 %.
        source = single("src", 60.0, 60.0, fs=4800.0)
        old_p = np.asarray(kernel_single(source, OP_ACTIVE_POWER, 50.0))
        old_q = np.asarray(kernel_single(source, OP_REACTIVE_POWER, 50.0))
        t = series(source, "VA")[0]
        mask = np.isfinite(old_p) & (t >= 0.1)
        assert -0.1195 < np.mean(old_p[mask]) / P_MW - 1.0 < -0.1165
        assert -0.1335 < np.mean(old_q[mask]) / Q_MVAR - 1.0 < -0.1305
        sources, calcs, _ = world(("src", source))
        new = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access_for(sources))
        assert rel_error(np.asarray(new.values)[steady(new)], P_MW).max() <= 1e-9

    @pytest.mark.parametrize("operation,expected", [(OP_THREE_PHASE_ACTIVE_POWER, 3 * P_MW), (OP_THREE_PHASE_REACTIVE_POWER, 3 * Q_MVAR)])
    @pytest.mark.parametrize("nominal", [50.0, 60.0])
    def test_three_phase_balanced_load_matches_the_closed_form(self, operation, expected, nominal):
        source = three_phase("src", nominal, nominal)
        sources, calcs, _ = world(("src", source))
        channel = make(sources, calcs, operation, [ref("src", n) for n in ("VA", "IA", "VB", "IB", "VC", "IC")], access_for(sources))
        assert rel_error(np.asarray(channel.values)[steady(channel)], expected).max() <= 1e-9


# ================================================================================================================ gates use the frequency
class TestPrerequisitesUseTheEffectiveFrequency:
    def test_a_recording_shorter_than_one_50hz_cycle_but_not_one_60hz_cycle(self):
        # 0.018 s: shorter than 1/50 s (0.02 s), longer than 1/60 s (0.0167 s). Before NF-3F every recording was gated at 50 Hz.
        source = single("src", 60.0, 60.0, fs=4800.0, seconds=0.018)
        sources, calcs, registry = world(("src", source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access)
        assert channel.parameters["nominal_frequency_hz"] == 60.0
        access.set_manual(WS, "src", 50.0)
        with pytest.raises(RmsRecordingTooShortError):
            make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access, name="P2")

    def test_sampling_that_is_dense_enough_at_50hz_but_too_sparse_at_60hz(self):
        # The power gates are the RMS density gate (at least MIN_SAMPLES_PER_CYCLE = 4 samples per cycle). 220 Hz: 4.4 samples per cycle at
        # 50 Hz, 3.67 at 60 Hz. NF-3F adds no numeric gate; it evaluates the existing one at the effective frequency.
        slow60 = single("s60", 60.0, 60.0, fs=220.0)
        sources, calcs, _ = world(("s60", slow60))
        with pytest.raises(RmsSamplingTooSparseError):
            make(sources, calcs, OP_ACTIVE_POWER, [ref("s60", "VA"), ref("s60", "IA")], access_for(sources))
        slow50 = single("s50", 50.0, 50.0, fs=220.0)
        sources, calcs, _ = world(("s50", slow50))
        assert make(sources, calcs, OP_ACTIVE_POWER, [ref("s50", "VA"), ref("s50", "IA")], access_for(sources)).parameters[
            "nominal_frequency_hz"] == 50.0


# ================================================================================================================ unusable frequency
class TestUnusableFrequencyKeepsTheExistingRefusal:
    @pytest.mark.parametrize("declared", [0.0, -50.0, float("nan"), float("inf"), 1001.0, 0.5])
    def test_refused_with_invalid_nominal_frequency_and_nothing_is_written(self, declared):
        source = single("src", declared, 50.0)
        sources, calcs, _ = world(("src", source))
        with pytest.raises(InvalidNominalFrequencyError) as caught:
            make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access_for(sources))
        assert caught.value.code == "invalid_nominal_frequency"
        assert "Recording Details" in caught.value.message
        assert calcs.list_for_workspace(WS) == []

    def test_a_manual_value_makes_the_unusable_recording_usable(self):
        source = single("src", 0.0, 50.0)
        sources, calcs, registry = world(("src", source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        access.set_manual(WS, "src", 50.0)
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access)
        assert channel.parameters["nominal_frequency_hz"] == 50.0
        assert channel.parameters["nominal_frequency_origin"] == "manual"


# ================================================================================================================ V/I agreement
class TestVoltageAndCurrentMustAgree:
    @staticmethod
    def pair(v_hz, i_hz, *, manual=None):
        v_source = single("vsrc", v_hz, 50.0)
        i_source = single("isrc", i_hz, 50.0, with_voltage=False)
        sources, calcs, registry = world(("vsrc", v_source), ("isrc", i_source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        for source_id, value in (manual or {}).items():
            access.set_manual(WS, source_id, value)
        return sources, calcs, access

    def test_disagreement_is_refused_with_nominal_frequency_mixed_naming_each_input(self):
        sources, calcs, access = self.pair(50.0, 60.0)
        with pytest.raises(MixedNominalFrequencyError) as caught:
            make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access)
        assert caught.value.code == "nominal_frequency_mixed"
        message = caught.value.message
        assert "VA: 50 Hz" in message and "IA: 60 Hz" in message and "Recording Details" in message
        assert calcs.list_for_workspace(WS) == []                                       # nothing written

    def test_the_refusal_does_not_depend_on_which_recording_supplies_voltage(self):
        a = self.pair(50.0, 60.0)
        b = self.pair(60.0, 50.0)
        errors = []
        for sources, calcs, access in (a, b):
            with pytest.raises(MixedNominalFrequencyError) as caught:
                make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access)
            errors.append(caught.value)
        assert errors[0].code == errors[1].code == "nominal_frequency_mixed"

    def test_agreement_is_judged_on_the_effective_frequency_not_the_imported_one(self):
        # V recording declares 50, I recording declares 60; a Manual 60 on the first makes them agree at 60.
        sources, calcs, access = self.pair(50.0, 60.0, manual={"vsrc": 60.0})
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access)
        assert channel.parameters["nominal_frequency_hz"] == 60.0
        assert channel.parameters["nominal_frequency_origin"] == "manual"            # the voltage recording's origin, as for RMS

    def test_values_that_agree_within_the_accessor_tolerance_are_one_frequency(self):
        sources, calcs, access = self.pair(60.0, 60.0 + 1e-12)
        assert make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access).parameters["nominal_frequency_hz"] == 60.0

    def test_an_unusable_recording_is_invalid_not_mixed(self):
        sources, calcs, access = self.pair(50.0, 0.0)
        with pytest.raises(InvalidNominalFrequencyError):
            make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access)

    def test_the_http_contract_is_400_with_the_reason_code_and_an_actionable_message(self, tmp_path):
        settings = Settings(environment="development", storage_type="local", storage_path=str(tmp_path), cors_origins=("http://localhost:8101",),
                            database_url=None, max_event_upload_size_mb=100, git_sha="local", version="local",
                            nominal_frequency_manual_override_enabled=True)
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            ws = "ws-nf3f-http"
            v = nf3d.upload(client, ws, "v50", 5000.0, 50.0, "50")
            i = nf3d.upload(client, ws, "i60", 5000.0, 50.0, "60")
            made = nf3e.create(client, ws, "P", "active_power", [nf3e.src(v, "VA"), nf3e.src(i, "IA")])
            assert made["status"] == 400
            detail = made["body"]["detail"]
            assert detail["code"] == "nominal_frequency_mixed"
            assert "50 Hz" in detail["message"] and "60 Hz" in detail["message"]
            assert client.get(f"/api/v1/workspaces/{ws}/calculated-channels").json() == []

    def test_three_phase_inputs_from_two_recordings_must_agree(self):
        v_source = three_phase("vsrc", 50.0, 50.0)
        i_source = three_phase("isrc", 60.0, 50.0)
        sources, calcs, _ = world(("vsrc", v_source), ("isrc", i_source))
        inputs = [ref("vsrc", "VA"), ref("isrc", "IA"), ref("vsrc", "VB"), ref("isrc", "IB"), ref("vsrc", "VC"), ref("isrc", "IC")]
        with pytest.raises(MixedNominalFrequencyError):
            make(sources, calcs, OP_THREE_PHASE_ACTIVE_POWER, inputs, access_for(sources), phase_pairing_confirmed=True)
        assert calcs.list_for_workspace(WS) == []


# ================================================================================================================ provenance and staleness
class TestRecordingFollowingProvenanceAndStaleness:
    @pytest.fixture()
    def one(self):
        source = single("src", 60.0, 60.0)
        sources, calcs, registry = world(("src", source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], access)
        return sources, calcs, access, channel

    def stale(self, channel, calcs, access):
        return frequency_staleness(channel, workspace_id=WS, calc_registry=calcs, frequency_access=access)

    def test_a_new_power_channel_records_basis_origin_and_revision(self, one):
        _, _, _, channel = one
        p = channel.parameters
        assert (p["nominal_frequency_basis"], p["nominal_frequency_origin"], p["nominal_frequency_revision"]) == (
            "recording", "recording_metadata", 0)

    def test_it_is_current_stale_and_current_again_with_the_recording_and_values_are_never_recomputed(self, one):
        sources, calcs, access, channel = one
        before = np.array(channel.values, copy=True)
        stored_before = dict(channel.parameters)
        state = self.stale(channel, calcs, access)
        assert (state.state, state.assessment) == ("current", "frequency_aware")
        access.set_manual(WS, "src", 50.0)
        state = self.stale(channel, calcs, access)
        assert state.stale and state.causes[0].reason == "recording_frequency_changed"
        assert (state.causes[0].stored_hz, state.causes[0].effective_hz, state.causes[0].operation) == (60.0, 50.0, OP_ACTIVE_POWER)
        assert np.array_equal(channel.values, before, equal_nan=True) and channel.parameters == stored_before     # historical values preserved
        access.reset_to_auto(WS, "src")
        assert not self.stale(channel, calcs, access).stale

    def test_a_dependant_inherits_the_staleness_and_a_new_calculation_on_it_is_refused_with_a_power_remedy(self, one):
        from app.services.errors import StaleCalculatedInputError
        sources, calcs, access, channel = one
        access.set_manual(WS, "src", 50.0)
        with pytest.raises(StaleCalculatedInputError) as caught:
            create_calculated_channel(
                workspace_id=WS, name="2P", operation="addition", parameters={}, source_registry=sources, calc_registry=calcs,
                inputs=[ChannelRef(kind="calculated", calculated_channel_id=channel.id)] * 2, frequency_access=access)
        assert "Create a new power channel" in caught.value.message and "60" in caught.value.message and "50" in caught.value.message

    def test_voltage_and_current_from_two_recordings_are_stale_if_either_changes(self):
        v_source = single("vsrc", 60.0, 60.0)
        i_source = single("isrc", 60.0, 60.0, with_voltage=False)
        sources, calcs, registry = world(("vsrc", v_source), ("isrc", i_source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        channel = make(sources, calcs, OP_ACTIVE_POWER, [ref("vsrc", "VA"), ref("isrc", "IA")], access)
        state = lambda: frequency_staleness(channel, workspace_id=WS, calc_registry=calcs, frequency_access=access)    # noqa: E731
        assert not state().stale
        access.set_manual(WS, "isrc", 50.0)                                       # only the CURRENT recording changes
        assert state().stale
        access.reset_to_auto(WS, "isrc")
        access.set_manual(WS, "vsrc", 50.0)                                       # only the VOLTAGE recording changes
        assert state().stale
        access.reset_to_auto(WS, "vsrc")
        assert not state().stale

    def test_a_channel_stored_before_nf_3f_is_not_changed_by_a_frequency_change(self):
        # the pre-migration path stores 50.0 and no basis: it is explicit, never flagged, and its values never move
        source = single("src", 60.0, 60.0)
        sources, calcs, registry = world(("src", source))
        access = access_for(sources, manual_override_enabled=True, registry=registry)
        legacy = make(sources, calcs, OP_ACTIVE_POWER, [ref("src", "VA"), ref("src", "IA")], None)
        before = np.array(legacy.values, copy=True)
        access.set_manual(WS, "src", 50.0)
        assert not frequency_staleness(legacy, workspace_id=WS, calc_registry=calcs, frequency_access=access).stale
        assert np.array_equal(legacy.values, before, equal_nan=True) and legacy.parameters["nominal_frequency_hz"] == 50.0


# ================================================================================================================ call paths
class TestEveryProductionCallerSuppliesTheAuthority:
    def test_every_production_call_of_create_calculated_channel_passes_frequency_access(self):
        calls = []
        for path in APP_DIR.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "create_calculated_channel":
                    calls.append((path.name, {k.arg for k in node.keywords}))
        assert {name for name, _ in calls} == {"calculated_channels.py", "compliance_readiness_service.py"}
        assert all("frequency_access" in keywords for _, keywords in calls), calls

    def test_the_power_service_has_no_literal_fifty_hertz(self):
        source = (APP_DIR / "services" / "calculated_channel_service.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                    and not isinstance(n.value, bool) and n.value in (50, 60, 0.02)]
        assert literals == []
