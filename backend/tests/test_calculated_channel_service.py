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
    OP_SUBTRACTION,
    ChannelRef,
)
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, DigitalChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import (
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
    InvalidOperationArityError,
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
) -> ActiveSource:
    units = units or {}
    digital = digital or {}
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
            AnalogChannelSummary(name=name, index=i, unit=units.get(name, "V"), engineering_type="Voltage")
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
