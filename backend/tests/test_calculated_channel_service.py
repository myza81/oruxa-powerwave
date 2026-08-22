"""Service-level tests for app.services.calculated_channel_service (Phase
5A, DEC-047). Builds ActiveSource fixtures directly, same established
pattern as tests/test_peak_value_service.py / test_annotation_anchor_service.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app.domain.calculated_channel import (
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
    ChannelRef,
)
from app.domain.channel_classification import (
    WAVEFORM_FORM_INSTANTANEOUS,
    WAVEFORM_FORM_RMS,
    WAVEFORM_FORM_UNKNOWN,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
    RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE,
    RMS_STATUS_SUITABLE,
    check_rms_eligibility,
    create_calculated_channel,
    delete_calculated_channel,
    extract_calculated_cursor_values,
    extract_calculated_waveform_range,
    remove_calculated_channels_for_source,
    resolve_calculated_annotation_anchor,
    resolve_calculated_peak_value,
)
from app.services.errors import (
    CalculatedChannelHasDependentsError,
    DuplicateCalculatedChannelNameError,
    IncompatibleTimeBaseError,
    IncompatibleUnitError,
    InvalidCalculatedChannelNameError,
    InvalidConstantError,
    InvalidNominalFrequencyError,
    InvalidOperationArityError,
    RmsOverrideRequiredError,
    RmsRecordingTooShortError,
    RmsSamplingTooSparseError,
)
from app.services.waveform_service import REPRESENTATION_MIN_MAX_ENVELOPE
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-1"
BASE_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _active_source(
    *,
    source_id: str,
    time: np.ndarray,
    channels: dict[str, np.ndarray],
    units: dict[str, str] | None = None,
    start_time: datetime | None = BASE_START,
    digital: dict[str, np.ndarray] | None = None,
    # Phase 5A-UAT4: per-channel engineering_type override, defaulting to
    # "Voltage" (this fixture's own pre-existing, unconditional default)
    # so every pre-existing call site is completely unaffected -- only
    # tests that explicitly need a different classification pass this.
    engineering_types: dict[str, str] | None = None,
    # Phase 5B: per-channel waveform_form override, defaulting to
    # WAVEFORM_FORM_UNKNOWN (matching every real provider's current
    # behavior) -- only RMS-eligibility tests that need explicit trusted
    # metadata pass this.
    waveform_forms: dict[str, str] | None = None,
) -> ActiveSource:
    units = units or {}
    digital = digital or {}
    engineering_types = engineering_types or {}
    waveform_forms = waveform_forms or {}
    col_data = {"time": time, **channels}
    col_data.update(digital)

    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="SYNTH", recorder_name="TEST", source_file="synthetic.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(col_data),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[1.0], samples_per_rate=[len(time)]),
        timing_info=TimingInformation(start_time=BASE_START, trigger_time=BASE_START),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=WS, provider_type="COMTRADE",
        original_filenames=("synthetic.cfg", "synthetic.dat"), created_at=BASE_START,
        station_name="SYNTH", recorder_name="TEST", nominal_frequency=50.0,
        timing_reference="absolute", start_time=start_time, trigger_time=start_time,
        sample_count=len(time), duration_seconds=float(time[-1] - time[0]) if len(time) else 0.0,
        elapsed_start_seconds=float(time[0]) if len(time) else 0.0,
        elapsed_end_seconds=float(time[-1]) if len(time) else 0.0,
        sampling_rates=(1.0,), samples_per_rate=(len(time),),
        analog_channels=[
            AnalogChannelSummary(
                name=name, index=i, unit=units.get(name, "V"),
                engineering_type=engineering_types.get(name, "Voltage"),
                waveform_form=waveform_forms.get(name, WAVEFORM_FORM_UNKNOWN),
            )
            for i, name in enumerate(channels)
        ],
        digital_channels=[
            DigitalChannelSummary(name=name, index=i, normal_state=0) for i, name in enumerate(digital)
        ],
    )
    return ActiveSource(metadata=metadata, record=record)


@pytest.fixture
def registries():
    source_registry = WorkspaceRegistry()
    calc_registry = CalculatedChannelRegistry()
    return source_registry, calc_registry


def _add_source(source_registry, active):
    source_registry.add(active)
    return active


class TestReversePolarity:
    def test_creates_negated_channel(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1, 0.2]),
            channels={"VA": np.array([1.0, -2.0, 3.0])}, units={"VA": "kV"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="-VA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [-1.0, 2.0, -3.0]
        assert channel.unit == "kV"
        assert channel.time.tolist() == [0.0, 0.1, 0.2]
        assert channel.reference_source_id == "src1"


class TestAbsoluteValue:
    def test_creates_absolute_channel(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1, 0.2]),
            channels={"IA": np.array([-1.0, 2.0, -3.0])}, units={"IA": "A"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Abs(IA)", operation=OP_ABSOLUTE_VALUE,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="IA")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [1.0, 2.0, 3.0]
        assert channel.unit == "A"


class TestMultiplyConstant:
    def test_valid_constant(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"VA": np.array([1.0, 2.0])}, units={"VA": "V"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="2xVA", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"constant": 2.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [2.0, 4.0]
        assert channel.unit == "V"  # dimensionless constant -- unit unchanged (section 29)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), "two", None, True])
    def test_non_finite_or_non_numeric_constant_rejected(self, registries, bad):
        # Section 83.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"VA": np.array([1.0, 2.0])},
        ))
        with pytest.raises(InvalidConstantError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_MULTIPLY_CONSTANT,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"constant": bad}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestAddition:
    def test_n_inputs_greater_than_two(self, registries):
        # Section 78.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"A": np.array([1.0, 2.0]), "B": np.array([10.0, 20.0]), "C": np.array([100.0, 200.0])},
            units={"A": "kV", "B": "kV", "C": "kV"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
                ChannelRef(kind="source", source_id="src1", channel_name="C"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [111.0, 222.0]
        assert channel.unit == "kV"

    def test_duplicate_input_a_plus_a(self, registries):
        # Section 80.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"A": np.array([5.0])}, units={"A": "kV"},
        ))
        ref = ChannelRef(kind="source", source_id="src1", channel_name="A")
        channel = create_calculated_channel(
            workspace_id=WS, name="A+A", operation=OP_ADDITION, inputs=[ref, ref],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [10.0]

    def test_single_input_rejected_for_arity(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0])},
        ))
        with pytest.raises(InvalidOperationArityError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestSubtraction:
    def test_n_inputs_order_matters(self, registries):
        # Section 79.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"A": np.array([100.0, 200.0]), "B": np.array([10.0, 20.0]), "C": np.array([1.0, 2.0])},
            units={"A": "MW", "B": "MW", "C": "MW"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="A-B-C", operation=OP_SUBTRACTION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
                ChannelRef(kind="source", source_id="src1", channel_name="C"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [89.0, 178.0]


class TestUnitCompatibility:
    def test_incompatible_units_rejected(self, registries):
        # Section 81: kV + A must reject.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]),
            channels={"V": np.array([1.0]), "I": np.array([1.0])},
            units={"V": "kV", "I": "A"},
        ))
        with pytest.raises(IncompatibleUnitError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="src1", channel_name="V"),
                    ChannelRef(kind="source", source_id="src1", channel_name="I"),
                ],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestTimeBaseCompatibility:
    def test_same_source_allowed(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"A": np.array([1.0, 2.0]), "B": np.array([1.0, 2.0])}, units={"A": "V", "B": "V"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="A+B", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [2.0, 4.0]

    def test_different_source_different_timing_rejected(self, registries):
        # Section 82.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"A": np.array([1.0, 2.0])},
            units={"A": "V"}, start_time=BASE_START,
        ))
        _add_source(source_registry, _active_source(
            source_id="src2", time=np.array([0.0, 0.1]), channels={"B": np.array([1.0, 2.0])},
            units={"B": "V"}, start_time=BASE_START + timedelta(seconds=5),  # different start -> different absolute instants
        ))
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="src1", channel_name="A"),
                    ChannelRef(kind="source", source_id="src2", channel_name="B"),
                ],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_different_source_identical_absolute_timing_allowed(self, registries):
        # [B]/[G] proven-equivalent absolute timelines across sources.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"A": np.array([1.0, 2.0])},
            units={"A": "V"}, start_time=BASE_START,
        ))
        _add_source(source_registry, _active_source(
            source_id="src2", time=np.array([0.0, 0.1]), channels={"B": np.array([10.0, 20.0])},
            units={"B": "V"}, start_time=BASE_START,
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="A+B", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src2", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.values.tolist() == [11.0, 22.0]

    def test_different_sample_rate_rejected(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.arange(10) / 5000.0, channels={"A": np.arange(10, dtype=float)},
            units={"A": "V"}, start_time=BASE_START,
        ))
        _add_source(source_registry, _active_source(
            source_id="src2", time=np.arange(10) / 1000.0, channels={"B": np.arange(10, dtype=float)},
            units={"B": "V"}, start_time=BASE_START,
        ))
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="source", source_id="src1", channel_name="A"),
                    ChannelRef(kind="source", source_id="src2", channel_name="B"),
                ],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestNameValidation:
    def test_empty_name_rejected(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0])}))
        with pytest.raises(InvalidCalculatedChannelNameError):
            create_calculated_channel(
                workspace_id=WS, name="   ", operation=OP_REVERSE_POLARITY,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_duplicate_name_rejected(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0])}))
        ref = ChannelRef(kind="source", source_id="src1", channel_name="A")
        create_calculated_channel(
            workspace_id=WS, name="Neg A", operation=OP_REVERSE_POLARITY, inputs=[ref],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        with pytest.raises(DuplicateCalculatedChannelNameError):
            create_calculated_channel(
                workspace_id=WS, name="Neg A", operation=OP_REVERSE_POLARITY, inputs=[ref],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestCalculatedDependency:
    def test_sum_scaled_absscaled_chain(self, registries):
        # Section 84: Sum = A+B; Scaled = Sum*2; AbsScaled = abs(Scaled).
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"A": np.array([1.0, -5.0]), "B": np.array([2.0, -3.0])}, units={"A": "kV", "B": "kV"},
        ))
        summed = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert summed.values.tolist() == [3.0, -8.0]

        scaled = create_calculated_channel(
            workspace_id=WS, name="Scaled", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=summed.id)],
            parameters={"constant": 2.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert scaled.values.tolist() == [6.0, -16.0]
        assert scaled.dependency_ids == [summed.id]
        assert scaled.reference_source_id == "src1"

        abs_scaled = create_calculated_channel(
            workspace_id=WS, name="AbsScaled", operation=OP_ABSOLUTE_VALUE,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=scaled.id)],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert abs_scaled.values.tolist() == [6.0, 16.0]

    def test_calculated_input_combined_with_incompatible_timeline_rejected(self, registries):
        # [H]: a calculated channel combined with a channel from a
        # different, unaligned timebase must still be rejected.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"A": np.array([1.0, 2.0])},
            units={"A": "V"}, start_time=BASE_START,
        ))
        _add_source(source_registry, _active_source(
            source_id="src2", time=np.array([0.0, 0.1]), channels={"C": np.array([9.0, 9.0])},
            units={"C": "V"}, start_time=BASE_START + timedelta(seconds=99),
        ))
        neg = create_calculated_channel(
            workspace_id=WS, name="NegA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        with pytest.raises(IncompatibleTimeBaseError):
            create_calculated_channel(
                workspace_id=WS, name="bad", operation=OP_ADDITION,
                inputs=[
                    ChannelRef(kind="calculated", calculated_channel_id=neg.id),
                    ChannelRef(kind="source", source_id="src2", channel_name="C"),
                ],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )


class TestDependencyAwareDelete:
    def test_delete_blocked_while_dependent_exists(self, registries):
        # Section 86.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0]), "B": np.array([2.0])}, units={"A": "V", "B": "V"},
        ))
        summed = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        create_calculated_channel(
            workspace_id=WS, name="Scaled", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=summed.id)],
            parameters={"constant": 2.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        with pytest.raises(CalculatedChannelHasDependentsError) as exc_info:
            delete_calculated_channel(workspace_id=WS, calculated_channel_id=summed.id, calc_registry=calc_registry)
        assert "Scaled" in exc_info.value.message

    def test_delete_succeeds_once_dependents_removed(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0]), "B": np.array([2.0])}, units={"A": "V", "B": "V"},
        ))
        summed = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        scaled = create_calculated_channel(
            workspace_id=WS, name="Scaled", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=summed.id)],
            parameters={"constant": 2.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        delete_calculated_channel(workspace_id=WS, calculated_channel_id=scaled.id, calc_registry=calc_registry)
        delete_calculated_channel(workspace_id=WS, calculated_channel_id=summed.id, calc_registry=calc_registry)
        assert calc_registry.list_for_workspace(WS) == []


class TestSourceRemovalCascade:
    def test_removes_directly_and_transitively_dependent_channels(self, registries):
        # Section 87.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"A": np.array([1.0]), "B": np.array([2.0])}, units={"A": "V", "B": "V"},
        ))
        _add_source(source_registry, _active_source(
            source_id="src2", time=np.array([0.0]), channels={"C": np.array([9.0])}, units={"C": "V"},
        ))
        summed = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="A"),
                ChannelRef(kind="source", source_id="src1", channel_name="B"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        scaled = create_calculated_channel(
            workspace_id=WS, name="Scaled", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=summed.id)],
            parameters={"constant": 2.0}, source_registry=source_registry, calc_registry=calc_registry,
        )
        other = create_calculated_channel(
            workspace_id=WS, name="NegC", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src2", channel_name="C")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )

        removed = remove_calculated_channels_for_source(workspace_id=WS, source_id="src1", calc_registry=calc_registry)

        assert set(removed) == {summed.id, scaled.id}
        assert calc_registry.get(WS, summed.id) is None
        assert calc_registry.get(WS, scaled.id) is None
        assert calc_registry.get(WS, other.id) is not None  # untouched -- different source


class TestImmutability:
    def test_original_source_arrays_unchanged_after_calculation(self, registries):
        # Section 88.
        source_registry, calc_registry = registries
        original_values = np.array([1.0, -2.0, 3.0])
        active = _active_source(source_id="src1", time=np.array([0.0, 0.1, 0.2]), channels={"A": original_values.copy()})
        _add_source(source_registry, active)
        before = active.record.waveform_data["A"].to_numpy().copy()

        create_calculated_channel(
            workspace_id=WS, name="NegA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )

        after = active.record.waveform_data["A"].to_numpy()
        assert after.tolist() == before.tolist()
        assert after.tolist() == original_values.tolist()


class TestCalculatedWaveformCursorPeakAnchor:
    def _sum_channel(self, source_registry, calc_registry, n=20_000):
        time = np.arange(n, dtype=np.float64) / 10_000.0
        values = np.sin(np.arange(n, dtype=np.float64) * 0.01) * 5.0
        _add_source(source_registry, _active_source(source_id="src1", time=time, channels={"A": values}, units={"A": "kV"}))
        return create_calculated_channel(
            workspace_id=WS, name="Big", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )

    def test_waveform_range_reduces_for_broad_view(self, registries):
        # Section 102: adaptive resolution.
        source_registry, calc_registry = registries
        channel = self._sum_channel(source_registry, calc_registry)
        result = extract_calculated_waveform_range(channel, start_time=None, end_time=None, point_budget=50)
        assert result.representation == REPRESENTATION_MIN_MAX_ENVELOPE
        assert len(result.time) < channel.time.shape[0]

    def test_cursor_values_use_full_resolution_nearest_sample(self, registries):
        # Section 99/54.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1, 0.2, 0.3]), channels={"A": np.array([10.0, 20.0, 30.0, 40.0])},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="NegA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        results = extract_calculated_cursor_values([channel], cursor_a_time=0.14, cursor_b_time=0.25)
        assert results[0].a_value == pytest.approx(-20.0)  # nearest to 0.14 is 0.1 -> value 20 -> negated -20
        assert results[0].b_value == pytest.approx(-30.0)  # nearest to 0.25 is 0.2 or 0.3(tie->earlier=0.2)->30->-30

    def test_peak_value_uses_full_resolution_within_viewport(self, registries):
        # Section 100.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 1.0, 2.0, 2.4, 2.8, 3.0]),
            channels={"A": np.array([0.0, 100.0, 50.0, 70.0, 60.0, 65.0])},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="NegA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        # NegA values: [0,-100,-50,-70,-60,-65]; max within [2,3] window.
        result = resolve_calculated_peak_value(channel, mode="max", start_time=2.0, end_time=3.0)
        assert result.available is True
        assert result.value == pytest.approx(-50.0)
        assert result.elapsed_seconds == pytest.approx(2.0)

    def test_annotation_anchor_resolves_nearest_full_resolution_sample(self, registries):
        # Section 101/56 (Callout).
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1, 0.2, 0.3]), channels={"A": np.array([10.0, 20.0, 30.0, 40.0])},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="NegA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="A")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        result = resolve_calculated_annotation_anchor(channel, approximate_elapsed_seconds=0.14)
        assert result is not None
        assert result.sample_index == 1
        assert result.value == pytest.approx(-20.0)

    def test_annotation_anchor_out_of_bounds_returns_none(self, registries):
        source_registry, calc_registry = registries
        channel = self._sum_channel(source_registry, calc_registry, n=100)
        result = resolve_calculated_annotation_anchor(channel, approximate_elapsed_seconds=999.0)
        assert result is None


class TestEngineeringTypeInheritance:
    """Phase 5A-UAT4 (DEC-047 clarification): a calculated channel's own
    engineering_type is inherited from its input(s), never guessed from
    the (user-editable) output name. Sections 23/24/25 of the owner's
    task."""

    def test_reverse_polarity_inherits_input_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"VA": np.array([1.0, 2.0])},
            engineering_types={"VA": "Voltage"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="-VA", operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Voltage"

    def test_absolute_value_inherits_input_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"IA": np.array([-1.0, 2.0])},
            engineering_types={"IA": "Current"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Abs(IA)", operation=OP_ABSOLUTE_VALUE,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="IA")],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Current"

    def test_multiply_constant_inherits_input_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]), channels={"P": np.array([1.0, 2.0])},
            engineering_types={"P": "Power"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Px0.5", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="P")],
            parameters={"constant": 0.5}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Power"

    def test_unary_operations_preserve_undefined_input_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]), channels={"CH1": np.array([1.0])},
            engineering_types={"CH1": "Undefined"},
        ))
        for name, op in [("-CH1", OP_REVERSE_POLARITY), ("Abs(CH1)", OP_ABSOLUTE_VALUE)]:
            channel = create_calculated_channel(
                workspace_id=WS, name=name, operation=op,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="CH1")],
                parameters={}, source_registry=source_registry, calc_registry=calc_registry,
            )
            assert channel.engineering_type == "Undefined"

    def test_addition_inherits_common_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"VA": np.array([1.0, 2.0]), "VB": np.array([3.0, 4.0]), "VC": np.array([5.0, 6.0])},
            units={"VA": "kV", "VB": "kV", "VC": "kV"},
            engineering_types={"VA": "Voltage", "VB": "Voltage", "VC": "Voltage"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="SumABC", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                ChannelRef(kind="source", source_id="src1", channel_name="VB"),
                ChannelRef(kind="source", source_id="src1", channel_name="VC"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Voltage"

    def test_subtraction_inherits_common_type(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"IA": np.array([1.0, 2.0]), "IB": np.array([3.0, 4.0]), "IC": np.array([5.0, 6.0])},
            units={"IA": "A", "IB": "A", "IC": "A"},
            engineering_types={"IA": "Current", "IB": "Current", "IC": "Current"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="SubABC", operation=OP_SUBTRACTION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="IA"),
                ChannelRef(kind="source", source_id="src1", channel_name="IB"),
                ChannelRef(kind="source", source_id="src1", channel_name="IC"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Current"

    def test_addition_of_two_power_inputs(self, registries):
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]),
            channels={"P1": np.array([1.0]), "P2": np.array([2.0])},
            units={"P1": "W", "P2": "W"},
            engineering_types={"P1": "Power", "P2": "Power"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Ptotal", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="P1"),
                ChannelRef(kind="source", source_id="src1", channel_name="P2"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Power"

    def test_addition_falls_back_to_undefined_when_any_input_type_unknown(self, registries):
        # Section 7/24: units are otherwise valid (both "V"), but one
        # input's own type is Undefined -- the conservative result is
        # Undefined, never a guess, and the calculation itself still
        # succeeds (classification never blocks eligibility).
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0]),
            channels={"VA": np.array([1.0]), "CH1": np.array([2.0])},
            units={"VA": "V", "CH1": "V"},
            engineering_types={"VA": "Voltage", "CH1": "Undefined"},
        ))
        channel = create_calculated_channel(
            workspace_id=WS, name="Mixed", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                ChannelRef(kind="source", source_id="src1", channel_name="CH1"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.engineering_type == "Undefined"
        assert channel.values.tolist() == [3.0], "classification never blocked or altered the calculation itself"

    def test_calculated_from_calculated_propagates_type_transitively(self, registries):
        # Section 25: Sum = VA+VB (Voltage) -> Scaled = Sum*0.5 (Voltage)
        # -> AbsScaled = abs(Scaled) (Voltage), verified through TWO
        # levels of calculated-from-calculated.
        source_registry, calc_registry = registries
        _add_source(source_registry, _active_source(
            source_id="src1", time=np.array([0.0, 0.1]),
            channels={"VA": np.array([1.0, 2.0]), "VB": np.array([3.0, 4.0])},
            units={"VA": "kV", "VB": "kV"},
            engineering_types={"VA": "Voltage", "VB": "Voltage"},
        ))
        sum_channel = create_calculated_channel(
            workspace_id=WS, name="Sum", operation=OP_ADDITION,
            inputs=[
                ChannelRef(kind="source", source_id="src1", channel_name="VA"),
                ChannelRef(kind="source", source_id="src1", channel_name="VB"),
            ],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert sum_channel.engineering_type == "Voltage"

        scaled_channel = create_calculated_channel(
            workspace_id=WS, name="Scaled", operation=OP_MULTIPLY_CONSTANT,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=sum_channel.id)],
            parameters={"constant": 0.5}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert scaled_channel.engineering_type == "Voltage"

        abs_scaled_channel = create_calculated_channel(
            workspace_id=WS, name="AbsScaled", operation=OP_ABSOLUTE_VALUE,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=scaled_channel.id)],
            parameters={}, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert abs_scaled_channel.engineering_type == "Voltage"


def _sinusoid_source(source_registry, *, source_id="src1", channel_name="VA", fs=5000.0, f0=50.0,
                      duration=0.5, unit="kV", waveform_form=WAVEFORM_FORM_UNKNOWN, engineering_type="Voltage"):
    """A synthetic 50Hz sinusoid, dense/long enough to be both a valid RMS
    input (>1 window, well above MIN_SAMPLES_PER_CYCLE) and confidently
    classified `likely_instantaneous` by the algorithmic detector when its
    waveform_form is left unknown."""
    n = int(round(fs * duration))
    time = np.arange(n, dtype=np.float64) / fs
    values = np.sin(2 * np.pi * f0 * time)
    _add_source(source_registry, _active_source(
        source_id=source_id, time=time, channels={channel_name: values},
        units={channel_name: unit}, waveform_forms={channel_name: waveform_form},
        engineering_types={channel_name: engineering_type},
    ))
    return time, values


class TestNoEngineeringTypeHardFilter:
    """Permanent regression test (owner section 63): RMS eligibility must
    NEVER be gated by engineering_type -- only by waveform_form metadata
    and the detector. This is what proves CSV/Excel-compatible behavior
    (a future importer may know waveform_form without knowing engineering
    type, or vice versa)."""

    def test_undefined_engineering_type_with_instantaneous_metadata_is_still_eligible(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(
            source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS, engineering_type="Undefined",
        )
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.waveform_form == WAVEFORM_FORM_RMS
        assert channel.engineering_type == "Undefined"  # unrelated to RMS eligibility, unaffected

    def test_voltage_engineering_type_with_rms_metadata_is_not_silently_eligible(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(
            source_registry, waveform_form=WAVEFORM_FORM_RMS, engineering_type="Voltage",
        )
        with pytest.raises(RmsOverrideRequiredError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry, override=False,
            )


class TestRmsOperation:
    """Phase 5B (DEC-048): trailing one-cycle true RMS, metadata-first
    eligibility, and backend-enforced override."""

    def test_creates_rms_channel_when_unknown_form_classified_suitable(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert channel.operation == OP_RMS
        assert channel.waveform_form == WAVEFORM_FORM_RMS
        assert channel.parameters == {
            "nominal_frequency_hz": 50.0, "window_mode": "trailing", "rms_kind": "true_rms",
        }
        steady = channel.values[-100:]
        assert np.all(np.isfinite(steady))
        assert np.mean(steady) == pytest.approx(1.0 / np.sqrt(2.0), abs=1e-3)

    def test_time_and_reference_source_id_inherited_verbatim(self, registries):
        source_registry, calc_registry = registries
        time, _ = _sinusoid_source(source_registry)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert np.array_equal(channel.time, time)
        assert channel.reference_source_id == "src1"
        assert channel.time.shape == channel.values.shape

    def test_explicit_instantaneous_metadata_allows_without_override(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry, override=False,
        )
        assert channel.waveform_form == WAVEFORM_FORM_RMS

    def test_explicit_rms_metadata_blocks_without_override(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_RMS)
        with pytest.raises(RmsOverrideRequiredError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(RMS(VA))", operation=OP_RMS,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry, override=False,
            )

    def test_explicit_rms_metadata_allowed_with_override(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_RMS)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(RMS(VA))", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry, override=True,
        )
        assert channel.waveform_form == WAVEFORM_FORM_RMS

    def test_rms_of_rms_blocked_then_allowed_with_override(self, registries):
        # Section 32/51: RMS(VA) is itself waveform_form=rms -- selecting
        # it again as an RMS input must be immediately blocked from
        # TRUSTED metadata (no detector re-run), and only proceed with an
        # explicit override.
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        rms_channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        assert rms_channel.waveform_form == WAVEFORM_FORM_RMS

        with pytest.raises(RmsOverrideRequiredError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(RMS(VA))", operation=OP_RMS,
                inputs=[ChannelRef(kind="calculated", calculated_channel_id=rms_channel.id)],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry, override=False,
            )

        doubled = create_calculated_channel(
            workspace_id=WS, name="RMS(RMS(VA))2", operation=OP_RMS,
            inputs=[ChannelRef(kind="calculated", calculated_channel_id=rms_channel.id)],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry, override=True,
        )
        assert doubled.waveform_form == WAVEFORM_FORM_RMS

    def test_invalid_nominal_frequency_rejected(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        for bad in (float("nan"), 0.0, -50.0, 5000.0, "fifty", None, True):
            with pytest.raises(InvalidNominalFrequencyError):
                create_calculated_channel(
                    workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
                    inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                    parameters={"nominal_frequency_hz": bad},
                    source_registry=source_registry, calc_registry=calc_registry,
                )

    def test_recording_shorter_than_one_window_rejected(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS, duration=0.005)
        with pytest.raises(RmsRecordingTooShortError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_sparse_sampling_rejected(self, registries):
        source_registry, calc_registry = registries
        # 100 Hz sampling for a 50 Hz window -- only ~2 samples/cycle.
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS, fs=100.0, duration=1.0)
        with pytest.raises(RmsSamplingTooSparseError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry,
            )

    def test_short_and_sparse_checks_are_never_overridable(self, registries):
        # Section 40/41: unlike eligibility, these are hard data-quality
        # constraints -- override=True must NOT bypass them.
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS, duration=0.005)
        with pytest.raises(RmsRecordingTooShortError):
            create_calculated_channel(
                workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
                inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
                parameters={"nominal_frequency_hz": 50.0},
                source_registry=source_registry, calc_registry=calc_registry, override=True,
            )

    def test_peak_value_in_warmup_only_range_is_unavailable(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        # First 100 samples (0..0.0198s) are all warm-up NaN at 5kHz/50Hz.
        result = resolve_calculated_peak_value(channel, mode="max", start_time=0.0, end_time=0.01)
        assert result.available is False
        assert result.value is None

    def test_cursor_value_in_warmup_region_is_none_not_nan(self, registries):
        # Regression test for the NaN-serialization finding: FastAPI's
        # default JSONResponse rejects raw NaN (allow_nan=False) -- a
        # warm-up-region cursor must resolve to None, matching the
        # existing "cursor outside the recording" contract, never a raw
        # float("nan") that would 500 the response.
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        results = extract_calculated_cursor_values([channel], cursor_a_time=0.001, cursor_b_time=0.3)
        assert results[0].a_value is None
        assert results[0].b_value is not None
        assert np.isfinite(results[0].b_value)

    def test_annotation_anchor_value_in_warmup_region_is_none_not_nan(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        channel = create_calculated_channel(
            workspace_id=WS, name="RMS(VA)", operation=OP_RMS,
            inputs=[ChannelRef(kind="source", source_id="src1", channel_name="VA")],
            parameters={"nominal_frequency_hz": 50.0},
            source_registry=source_registry, calc_registry=calc_registry,
        )
        result = resolve_calculated_annotation_anchor(channel, approximate_elapsed_seconds=0.001)
        assert result is not None
        assert result.value is None
        assert result.sample_index is not None
        assert result.elapsed_seconds is not None


class TestRmsEligibility:
    def test_instantaneous_metadata_is_suitable_without_running_detector(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_INSTANTANEOUS)
        eligibility = check_rms_eligibility(
            workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src1", channel_name="VA"),
            nominal_frequency_hz=50.0, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert eligibility.status == RMS_STATUS_SUITABLE
        assert eligibility.override_required is False

    def test_rms_metadata_requires_override(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_RMS)
        eligibility = check_rms_eligibility(
            workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src1", channel_name="VA"),
            nominal_frequency_hz=50.0, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert eligibility.status == RMS_STATUS_LIKELY_ALREADY_RMS_OR_MAGNITUDE
        assert eligibility.override_required is True

    def test_unknown_metadata_falls_back_to_detector(self, registries):
        source_registry, calc_registry = registries
        _sinusoid_source(source_registry, waveform_form=WAVEFORM_FORM_UNKNOWN)
        eligibility = check_rms_eligibility(
            workspace_id=WS, input_ref=ChannelRef(kind="source", source_id="src1", channel_name="VA"),
            nominal_frequency_hz=50.0, source_registry=source_registry, calc_registry=calc_registry,
        )
        assert eligibility.status == RMS_STATUS_SUITABLE
        assert eligibility.override_required is False
