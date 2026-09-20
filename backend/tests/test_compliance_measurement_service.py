"""Tests for `app.services.compliance_measurement_service` (Compliance &
Capability Slice 2) -- the orchestration layer that resolves which
workspace channels satisfy a Voltage assessment quantity's required
roles, classifies Instantaneous vs RMS input representation, and looks
up Per-Unit base display info, WITHOUT ever calling `estimate_phasor()`
or computing an actual value (see this module's own docstring for why).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.channel_classification import VOLTAGE, WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS, WAVEFORM_FORM_UNKNOWN
from app.domain.compliance_measurement import (
    QUANTITY_MAX_PHASE_LG_RMS,
    QUANTITY_MIN_PHASE_LG_RMS,
    QUANTITY_PHASE_A_LG_RMS,
    QUANTITY_PHASE_AB_LL_RMS,
    QUANTITY_POSITIVE_SEQUENCE_RMS,
    STATUS_AMBIGUOUS_METADATA,
    STATUS_AVAILABLE,
    STATUS_INVALID_BASE,
    STATUS_MISSING_INPUTS,
    STATUS_UNSUPPORTED_REPRESENTATION,
    VALUE_REPRESENTATION_DIRECT_RMS,
    VALUE_REPRESENTATION_FUNDAMENTAL_RMS,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.calculated_channel import ChannelRef
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE
from app.services.compliance_measurement_service import (
    INPUT_TYPE_INSTANTANEOUS,
    INPUT_TYPE_RMS,
    evaluate_voltage_measurement,
    resolve_voltage_role_catalogue,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import UnknownComplianceQuantityError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.workspace_registry import WorkspaceRegistry

SAMPLE_RATE_HZ = 5000.0
DURATION_S = 2.0
REF_START = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
WORKSPACE_ID = "ws-compliance-1"


def _sine_source(
    source_id: str,
    channels: list[tuple[str, float, float]],
    *,
    waveform_form: str = WAVEFORM_FORM_INSTANTANEOUS,
    duration_s: float = DURATION_S,
    nominal_frequency: float = 50.0,
) -> ActiveSource:
    """`channels`: list of (name, amp_peak_or_rms, phase_deg)."""
    n = int(round(duration_s * SAMPLE_RATE_HZ))
    t = np.arange(n) / SAMPLE_RATE_HZ
    analog_channels = []
    columns = {"time": t}
    for index, (name, amp, phase_deg) in enumerate(channels):
        columns[name] = amp * np.cos(2.0 * np.pi * nominal_frequency * t + np.radians(phase_deg))
        analog_channels.append(
            AnalogChannelSummary(name=name, index=index, unit="V", engineering_type=VOLTAGE, waveform_form=waveform_form)
        )
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=nominal_frequency,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[SAMPLE_RATE_HZ], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=REF_START, trigger_time=REF_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WORKSPACE_ID, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=REF_START,
        station_name="Station", recorder_name="Recorder", nominal_frequency=nominal_frequency,
        timing_reference="absolute", start_time=REF_START, trigger_time=REF_START,
        sample_count=n, duration_seconds=duration_s, elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(SAMPLE_RATE_HZ,), samples_per_rate=(n,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


@pytest.fixture
def registries():
    return {
        "source": WorkspaceRegistry(),
        "group": MeasurementGroupRegistry(),
        "voltage_config": VoltageGroupConfigRegistry(),
        "current_config": CurrentGroupConfigRegistry(),
    }


def _evaluate(registries, quantity_id: str) -> object:
    return evaluate_voltage_measurement(
        workspace_id=WORKSPACE_ID, quantity_id=quantity_id,
        source_registry=registries["source"], group_registry=registries["group"],
        voltage_config_registry=registries["voltage_config"], current_config_registry=registries["current_config"],
    )


class TestRoleCatalogueResolution:
    def test_bare_role_names_resolve_to_canonical_phases(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0), ("VC", 100.0, 120.0)]))
        catalogue = resolve_voltage_role_catalogue(workspace_id=WORKSPACE_ID, source_registry=registries["source"])
        assert set(catalogue.keys()) == {"A", "B", "C"}
        assert catalogue["A"].candidates[0].channel_name == "VA"

    def test_direct_pair_channel_resolves_to_pair_role(self, registries):
        registries["source"].add(_sine_source("s1", [("VAB", 173.0, 0.0), ("VBC", 173.0, -120.0), ("VCA", 173.0, 120.0)]))
        catalogue = resolve_voltage_role_catalogue(workspace_id=WORKSPACE_ID, source_registry=registries["source"])
        assert set(catalogue.keys()) == {"AB", "BC", "CA"}


class TestSinglePhaseLimitation:
    """task section 9: Va only -> Phase A valid, Positive Sequence
    unavailable, with an explicit reason naming what's missing."""

    def test_phase_a_available_positive_sequence_missing(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        phase_a = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert phase_a.status == STATUS_AVAILABLE
        assert phase_a.input_type == INPUT_TYPE_INSTANTANEOUS
        assert phase_a.value_representation == VALUE_REPRESENTATION_FUNDAMENTAL_RMS

        positive_sequence = _evaluate(registries, QUANTITY_POSITIVE_SEQUENCE_RMS)
        assert positive_sequence.status == STATUS_MISSING_INPUTS
        assert positive_sequence.missing == ("B", "C")
        assert "Vb, Vc" in positive_sequence.message


class TestCompleteThreePhase:
    """task section 10: Va/Vb/Vc -> min/max/positive-sequence all
    available (eligibility only -- no value is computed by this
    service)."""

    def test_min_max_and_positive_sequence_available(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0), ("VC", 100.0, 120.0)]))
        for quantity_id in (QUANTITY_MIN_PHASE_LG_RMS, QUANTITY_MAX_PHASE_LG_RMS, QUANTITY_POSITIVE_SEQUENCE_RMS):
            result = _evaluate(registries, quantity_id)
            assert result.status == STATUS_AVAILABLE, f"{quantity_id}: {result.message}"
            assert result.input_type == INPUT_TYPE_INSTANTANEOUS


class TestRmsDirectInput:
    def test_already_rms_channel_reports_direct_rms(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 158.77, 0.0)], waveform_form=WAVEFORM_FORM_RMS))
        result = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.input_type == INPUT_TYPE_RMS
        assert result.value_representation == VALUE_REPRESENTATION_DIRECT_RMS


class TestUnsupportedRepresentation:
    """task section 8/10: deriving a line-line/positive-sequence quantity
    from already-RMS, angle-less phase channels is rejected."""

    def test_derived_line_line_from_rms_only_inputs_is_unsupported(self, registries):
        registries["source"].add(
            _sine_source("s1", [("VA", 120.0, 0.0), ("VB", 118.0, -120.0)], waveform_form=WAVEFORM_FORM_RMS)
        )
        result = _evaluate(registries, QUANTITY_PHASE_AB_LL_RMS)
        assert result.status == STATUS_UNSUPPORTED_REPRESENTATION
        assert result.used_direct_pair is False


class TestDirectPairPreferredOverDerivation:
    def test_direct_vab_channel_used_even_when_va_vb_also_present(self, registries):
        registries["source"].add(
            _sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0), ("VAB", 173.0, 30.0)])
        )
        result = _evaluate(registries, QUANTITY_PHASE_AB_LL_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.used_direct_pair is True
        assert result.resolved_roles["AB"].channel_name == "VAB"


class TestAmbiguousMetadata:
    def test_uncertain_waveform_form_is_not_guessed(self, registries):
        # Too few samples for classify_waveform_form() to reach a
        # confident verdict (MIN_CYCLES_FOR_DETECTION) -- metadata is
        # WAVEFORM_FORM_UNKNOWN so the detector fallback runs and must
        # return UNCERTAIN, never a guess.
        registries["source"].add(
            _sine_source("s1", [("VA", 100.0, 0.0)], waveform_form=WAVEFORM_FORM_UNKNOWN, duration_s=0.01)
        )
        result = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AMBIGUOUS_METADATA

    def test_ambiguous_name_collision_across_sources(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        registries["source"].add(_sine_source("s2", [("VA", 100.0, 0.0)]))
        result = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AMBIGUOUS_METADATA


class TestUnknownQuantity:
    def test_raises_unknown_compliance_quantity_error(self, registries):
        with pytest.raises(UnknownComplianceQuantityError):
            _evaluate(registries, "not_a_real_quantity")


def _confirm_voltage_group(registries, *, group_id: str, channel_names: list[str], nominal_ll_kv: float, reference: str) -> None:
    group = MeasurementGroup(
        id=group_id, workspace_id=WORKSPACE_ID, source_id="s1", kind=KIND_VOLTAGE,
        display_name=group_id, channel_refs=[ChannelRef(kind="source", source_id="s1", channel_name=name) for name in channel_names],
        status=STATUS_CONFIRMED,
    )
    registries["group"].add(group)
    registries["voltage_config"].upsert(
        VoltageBaseConfiguration(
            measurement_group_id=group_id, workspace_id=WORKSPACE_ID, nominal_voltage_ll_kv=nominal_ll_kv,
            reference_mode="manual", reference_override=reference,
        )
    )


class TestBaseInfo:
    def test_no_group_reports_engineering_unit_not_an_error(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        result = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.base is None
        assert result.assessment_unit == "engineering_unit"

    def test_confirmed_group_reports_base_and_pu_unit(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        _confirm_voltage_group(registries, group_id="mg-1", channel_names=["VA"], nominal_ll_kv=275.0, reference=LINE_TO_GROUND)
        result = _evaluate(registries, QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.base is not None
        assert result.base.nominal_voltage_ll_kv == pytest.approx(275.0)
        assert result.base.effective_reference == LINE_TO_GROUND
        assert result.assessment_unit == "pu"

    def test_roles_spanning_two_different_groups_is_invalid_base(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0)]))
        _confirm_voltage_group(registries, group_id="mg-a", channel_names=["VA"], nominal_ll_kv=275.0, reference=LINE_TO_GROUND)
        _confirm_voltage_group(registries, group_id="mg-b", channel_names=["VB"], nominal_ll_kv=132.0, reference=LINE_TO_GROUND)
        result = _evaluate(registries, QUANTITY_PHASE_AB_LL_RMS)
        assert result.status == STATUS_INVALID_BASE
        assert "ambiguous" in result.message.lower()
