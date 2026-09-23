"""Tests for `app.services.compliance_measurement_service` (Compliance &
Capability Slice 2 + the 2026-09-20 Bay/Measurement Group UAT
correction) -- the orchestration layer that resolves which channels
WITHIN A SELECTED MEASUREMENT GROUP satisfy a Voltage assessment
quantity's required roles, classifies Instantaneous vs RMS input
representation, and looks up that group's own Per-Unit base display
info, WITHOUT ever calling `estimate_phasor()` or computing an actual
value (see this module's own docstring for why).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.channel_classification import VOLTAGE, WAVEFORM_FORM_INSTANTANEOUS, WAVEFORM_FORM_RMS, WAVEFORM_FORM_UNKNOWN
from app.domain.compliance_measurement import (
    QUANTITY_MAX_PHASE_LG_RMS,
    QUANTITY_MIN_PHASE_LG_RMS,
    QUANTITY_PHASE_A_LG_RMS,
    QUANTITY_PHASE_AB_LL_RMS,
    QUANTITY_POSITIVE_SEQUENCE_RMS,
    STATUS_AMBIGUOUS_METADATA,
    STATUS_AVAILABLE,
    STATUS_MISSING_INPUTS,
    STATUS_UNSUPPORTED_REPRESENTATION,
    VALUE_REPRESENTATION_DIRECT_RMS,
    VALUE_REPRESENTATION_FUNDAMENTAL_RMS,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.measurement_group import KIND_VOLTAGE, STATUS_CONFIRMED, STATUS_NEEDS_REVIEW, STATUS_SUGGESTED, MeasurementGroup
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.domain.voltage_reference import LINE_TO_GROUND, LINE_TO_LINE
from app.services.compliance_measurement_service import (
    INPUT_TYPE_INSTANTANEOUS,
    INPUT_TYPE_RMS,
    evaluate_voltage_measurement,
    list_compliance_voltage_groups,
    resolve_voltage_role_catalogue_for_group,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.errors import (
    ComplianceMeasurementGroupNotVoltageKindError,
    MeasurementGroupNotFoundError,
    UnknownComplianceQuantityError,
)
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


def _make_group(
    registries, *, group_id: str, source_id: str, channel_names: list[str], status: str = STATUS_CONFIRMED
) -> MeasurementGroup:
    group = MeasurementGroup(
        id=group_id, workspace_id=WORKSPACE_ID, source_id=source_id, kind=KIND_VOLTAGE,
        display_name=group_id,
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=name) for name in channel_names],
        status=status,
    )
    registries["group"].add(group)
    return group


def _set_voltage_base(registries, *, group_id: str, nominal_ll_kv: float, reference: str) -> None:
    registries["voltage_config"].upsert(
        VoltageBaseConfiguration(
            measurement_group_id=group_id, workspace_id=WORKSPACE_ID, nominal_voltage_ll_kv=nominal_ll_kv,
            reference_mode="manual", reference_override=reference,
        )
    )


def _evaluate(registries, *, group_id: str, quantity_id: str) -> object:
    return evaluate_voltage_measurement(
        workspace_id=WORKSPACE_ID, measurement_group_id=group_id, quantity_id=quantity_id,
        source_registry=registries["source"], group_registry=registries["group"],
        voltage_config_registry=registries["voltage_config"], current_config_registry=registries["current_config"],
    )


class TestListComplianceVoltageGroups:
    def test_includes_every_status_but_excludes_current_kind(self, registries):
        """2026-09-23 UAT correction: needs_review groups are no longer
        excluded at this layer -- a genuinely review-required workspace
        must never look identical to a truly empty one (task section
        10). Current-kind groups are still never a Voltage candidate."""
        _make_group(registries, group_id="mg-confirmed", source_id="s1", channel_names=["VA"], status=STATUS_CONFIRMED)
        _make_group(registries, group_id="mg-suggested", source_id="s1", channel_names=["VB"], status=STATUS_SUGGESTED)
        _make_group(registries, group_id="mg-needs-review", source_id="s1", channel_names=["VC"], status=STATUS_NEEDS_REVIEW)
        # A Current-kind group must never appear in the Voltage Bay picker.
        current_group = MeasurementGroup(
            id="mg-current", workspace_id=WORKSPACE_ID, source_id="s1", kind="current",
            display_name="Current Group", channel_refs=[], status=STATUS_CONFIRMED,
        )
        registries["group"].add(current_group)

        groups = list_compliance_voltage_groups(workspace_id=WORKSPACE_ID, group_registry=registries["group"])
        ids = {g.id for g in groups}
        assert ids == {"mg-confirmed", "mg-suggested", "mg-needs-review"}


class TestGroupScopedRoleResolution:
    def test_group_scopes_detection_to_its_own_membership_only(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        catalogue = resolve_voltage_role_catalogue_for_group(group, workspace_id=WORKSPACE_ID, source_registry=registries["source"])
        # VB exists in the source but is NOT a member of this group -- must not appear.
        assert set(catalogue.keys()) == {"A"}

    def test_group_may_span_multiple_sources(self, registries):
        # "VC" (not "VB") deliberately -- "B" alone is genuinely ambiguous
        # between the ABC and RYB conventions with no other phase letter
        # present as evidence (app.domain.phase_identity's own documented
        # convention-safety rule), so a lone-channel-per-source fixture
        # needs an ABC/RYB-EXCLUSIVE letter ("A"/"C") to resolve
        # unambiguously on its own.
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        registries["source"].add(_sine_source("s2", [("VC", 100.0, 120.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        # Manually extend membership across sources -- MeasurementGroup itself
        # doesn't forbid cross-source refs at the domain-object level; the
        # existing service-layer invariant (same-source-per-add) is a
        # create-time concern this test's own direct registry manipulation
        # deliberately bypasses to exercise the "may span sources" contract
        # (task section 11) that resolve_voltage_role_catalogue_for_group()
        # itself must honor regardless of how membership was assembled.
        group.channel_refs.append(ChannelRef(kind="source", source_id="s2", channel_name="VC"))
        registries["group"].update(group)
        catalogue = resolve_voltage_role_catalogue_for_group(group, workspace_id=WORKSPACE_ID, source_registry=registries["source"])
        assert set(catalogue.keys()) == {"A", "C"}


class TestCrossBayDuplicationIsNotAmbiguous:
    """task section 7/17: a duplicate Va across DIFFERENT groups is a
    normal, expected situation once a group is selected -- never an
    ambiguity."""

    def test_same_channel_name_in_two_groups_resolves_independently(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        registries["source"].add(_sine_source("s2", [("VA", 110.0, 5.0)]))
        bay_a = _make_group(registries, group_id="mg-bay-a", source_id="s1", channel_names=["VA"])
        bay_b = _make_group(registries, group_id="mg-bay-b", source_id="s2", channel_names=["VA"])

        result_a = _evaluate(registries, group_id=bay_a.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result_a.status == STATUS_AVAILABLE
        assert result_a.resolved_roles["A"].source_id == "s1"

        result_b = _evaluate(registries, group_id=bay_b.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result_b.status == STATUS_AVAILABLE
        assert result_b.resolved_roles["A"].source_id == "s2"


class TestSameGroupDuplicationIsStillAmbiguous:
    """task section 7/17: two DIFFERENTLY-NAMED member channels of the
    SAME group that both parse to the same phase remain ambiguous --
    this is a real, if unusual, grouping situation, never silently
    picked from."""

    def test_two_channels_in_one_group_both_matching_phase_a(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("ALPHA1_VA", 100.0, 0.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA", "ALPHA1_VA"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AMBIGUOUS_METADATA
        assert "within the selected Measurement Group" in result.message


class TestSinglePhaseLimitationWithinGroup:
    def test_bay_with_only_va_reports_missing_for_positive_sequence(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])

        phase_a = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert phase_a.status == STATUS_AVAILABLE

        positive_sequence = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_POSITIVE_SEQUENCE_RMS)
        assert positive_sequence.status == STATUS_MISSING_INPUTS
        assert positive_sequence.missing == ("B", "C")
        assert "requires Va, Vb, Vc" in positive_sequence.message
        assert "Missing: Vb, Vc" in positive_sequence.message


class TestCompleteThreePhaseWithinGroup:
    def test_min_max_and_positive_sequence_available(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0), ("VC", 100.0, 120.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA", "VB", "VC"])
        for quantity_id in (QUANTITY_MIN_PHASE_LG_RMS, QUANTITY_MAX_PHASE_LG_RMS, QUANTITY_POSITIVE_SEQUENCE_RMS):
            result = _evaluate(registries, group_id=group.id, quantity_id=quantity_id)
            assert result.status == STATUS_AVAILABLE, f"{quantity_id}: {result.message}"
            assert result.input_type == INPUT_TYPE_INSTANTANEOUS


class TestRmsDirectInput:
    def test_already_rms_channel_reports_direct_rms(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 158.77, 0.0)], waveform_form=WAVEFORM_FORM_RMS))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.input_type == INPUT_TYPE_RMS
        assert result.value_representation == VALUE_REPRESENTATION_DIRECT_RMS


class TestUnsupportedRepresentation:
    def test_derived_line_line_from_rms_only_inputs_is_unsupported(self, registries):
        registries["source"].add(
            _sine_source("s1", [("VA", 120.0, 0.0), ("VB", 118.0, -120.0)], waveform_form=WAVEFORM_FORM_RMS)
        )
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA", "VB"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_AB_LL_RMS)
        assert result.status == STATUS_UNSUPPORTED_REPRESENTATION
        assert result.used_direct_pair is False


class TestDirectPairPreferredOverDerivation:
    def test_direct_vab_channel_used_even_when_va_vb_also_present(self, registries):
        registries["source"].add(
            _sine_source("s1", [("VA", 100.0, 0.0), ("VB", 100.0, -120.0), ("VAB", 173.0, 30.0)])
        )
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA", "VB", "VAB"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_AB_LL_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.used_direct_pair is True
        assert result.resolved_roles["AB"].channel_name == "VAB"


class TestAmbiguousMetadata:
    def test_uncertain_waveform_form_is_not_guessed(self, registries):
        registries["source"].add(
            _sine_source("s1", [("VA", 100.0, 0.0)], waveform_form=WAVEFORM_FORM_UNKNOWN, duration_s=0.01)
        )
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AMBIGUOUS_METADATA


class TestUnknownQuantityAndGroup:
    def test_raises_unknown_compliance_quantity_error(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        with pytest.raises(UnknownComplianceQuantityError):
            _evaluate(registries, group_id=group.id, quantity_id="not_a_real_quantity")

    def test_raises_measurement_group_not_found_error(self, registries):
        with pytest.raises(MeasurementGroupNotFoundError):
            _evaluate(registries, group_id="does-not-exist", quantity_id=QUANTITY_PHASE_A_LG_RMS)

    def test_raises_not_voltage_kind_error_for_a_current_group(self, registries):
        current_group = MeasurementGroup(
            id="mg-current", workspace_id=WORKSPACE_ID, source_id="s1", kind="current",
            display_name="Current Group", channel_refs=[], status=STATUS_CONFIRMED,
        )
        registries["group"].add(current_group)
        with pytest.raises(ComplianceMeasurementGroupNotVoltageKindError):
            _evaluate(registries, group_id="mg-current", quantity_id=QUANTITY_PHASE_A_LG_RMS)


class TestBaseInfoControlledBySelectedGroup:
    def test_no_config_reports_engineering_unit_not_an_error(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.base is None
        assert result.assessment_unit == "engineering_unit"

    def test_configured_group_reports_base_and_pu_unit(self, registries):
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        group = _make_group(registries, group_id="mg-1", source_id="s1", channel_names=["VA"])
        _set_voltage_base(registries, group_id=group.id, nominal_ll_kv=275.0, reference=LINE_TO_GROUND)
        result = _evaluate(registries, group_id=group.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result.status == STATUS_AVAILABLE
        assert result.base is not None
        assert result.base.nominal_voltage_ll_kv == pytest.approx(275.0)
        assert result.base.effective_reference == LINE_TO_GROUND
        assert result.assessment_unit == "pu"

    def test_two_bays_with_different_bases_never_conflict(self, registries):
        """Selecting a different group naturally selects a different
        base -- there is no longer a cross-group base-conflict state to
        detect (structurally unreachable now that resolution is
        group-scoped)."""
        registries["source"].add(_sine_source("s1", [("VA", 100.0, 0.0)]))
        registries["source"].add(_sine_source("s2", [("VA", 100.0, 0.0)]))
        bay_a = _make_group(registries, group_id="mg-bay-a", source_id="s1", channel_names=["VA"])
        bay_b = _make_group(registries, group_id="mg-bay-b", source_id="s2", channel_names=["VA"])
        _set_voltage_base(registries, group_id=bay_a.id, nominal_ll_kv=275.0, reference=LINE_TO_GROUND)
        _set_voltage_base(registries, group_id=bay_b.id, nominal_ll_kv=132.0, reference=LINE_TO_GROUND)

        result_a = _evaluate(registries, group_id=bay_a.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result_a.base.nominal_voltage_ll_kv == pytest.approx(275.0)
        result_b = _evaluate(registries, group_id=bay_b.id, quantity_id=QUANTITY_PHASE_A_LG_RMS)
        assert result_b.base.nominal_voltage_ll_kv == pytest.approx(132.0)
