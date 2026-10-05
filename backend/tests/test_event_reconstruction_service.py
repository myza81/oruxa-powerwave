"""Service-layer tests for Event Reconstruction (DEC-123, DEC-124,
DEC-128): records as independent members (timestamp overlap never merges
them), eligibility, definition/member validation, per-record
corrections, reference switching, large-gap warnings, stale records, the
record-level coordinate model, and isolation from Waveform Time Groups
and Synchronise Sources."""

from __future__ import annotations

import inspect
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import app.services.event_reconstruction_service as er_service
from app.config import DEFAULT_EVENT_RECONSTRUCTION_LARGE_GAP_WARNING_S
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.event_reconstruction import (
    RELATIONSHIP_FULL_OVERLAP,
    RELATIONSHIP_GAP,
    RELATIONSHIP_PARTIAL_OVERLAP,
)
from app.domain.metadata import RecordingMetadata
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.errors import (
    DuplicateReconstructionMemberError,
    InvalidReconstructionCorrectionError,
    InvalidReconstructionDefinitionError,
    ReconstructionMemberNotFoundError,
    ReconstructionMemberStaleError,
    ReconstructionNotDefinedError,
    ReconstructionReferenceNotMemberError,
    RecordNotEligibleError,
    SourceNotFoundError,
)
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import (
    MEMBER_STATUS_CURRENT,
    MEMBER_STATUS_STALE,
    RECONSTRUCTION_STATUS_READY,
    RECONSTRUCTION_STATUS_STALE,
    STALE_REASON_RECORD_REMOVED,
    WARNING_LARGE_GAP,
    clear_reconstruction,
    get_reconstruction,
    list_reconstruction_records,
    remove_workspace_event_reconstruction_state,
    reset_member_correction,
    set_member_correction,
    set_reconstruction_definition,
    set_reconstruction_reference,
)
from app.services.synchronization_registry import SynchronizationRegistry
from app.services.synchronization_service import (
    list_source_alignments,
    list_time_groups,
    set_source_alignment_offset,
)
from app.services.workspace_registry import WorkspaceRegistry

WS = "ws-er"
T0 = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)
#: The centrally configured default (app.config), never a domain literal.
THRESHOLD_S = DEFAULT_EVENT_RECONSTRUCTION_LARGE_GAP_WARNING_S


def _source(
    source_id: str, *, start: datetime | None = T0, duration_s: float = 1.0, rate_hz: float = 20.0,
    timing_reference: str = "absolute", time_of_day_s: float | None = None, workspace_id: str = WS,
) -> ActiveSource:
    n = int(round(duration_s * rate_hz)) + 1
    time = np.linspace(0.0, duration_s, n)
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame({"time": time, "VA": np.sin(time)}),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[rate_hz], samples_per_rate=[n]),
        timing_info=TimingInformation(start_time=start or T0, trigger_time=start or T0),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=T0,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference=timing_reference, start_time=start, trigger_time=start,
        sample_count=n, duration_seconds=duration_s,
        elapsed_start_seconds=0.0, elapsed_end_seconds=duration_s,
        sampling_rates=(rate_hz,), samples_per_rate=(n,),
        analog_channels=[AnalogChannelSummary(name="VA", index=0, unit="V", engineering_type="Voltage")],
        digital_channels=[], time_of_day_reference_seconds=time_of_day_s,
    )
    return ActiveSource(metadata=metadata, record=record)


class _Ctx:
    def __init__(self, threshold_s: float = THRESHOLD_S):
        self.sources = WorkspaceRegistry()
        self.sync = SynchronizationRegistry()
        self.er = EventReconstructionRegistry()
        self.threshold_s = threshold_s

    def add(self, *sources: ActiveSource) -> None:
        for source in sources:
            self.sources.add(source)

    def remove(self, source_id: str) -> None:
        self.sources.remove(WS, source_id)

    def _kw(self) -> dict:
        return {"workspace_id": WS, "registry": self.er, "source_registry": self.sources}

    def _view_kw(self) -> dict:
        return {**self._kw(), "large_gap_threshold_s": self.threshold_s}

    def records(self):
        return list_reconstruction_records(**self._kw())

    def define(self, record_ids, reference):
        return set_reconstruction_definition(record_ids=list(record_ids), reference_record_id=reference, **self._view_kw())

    def view(self):
        return get_reconstruction(**self._view_kw())

    def correct(self, record_id, value):
        return set_member_correction(record_id=record_id, correction_s=value, **self._view_kw())

    def reset(self, record_id):
        return reset_member_correction(record_id=record_id, **self._view_kw())

    def reference(self, record_id):
        return set_reconstruction_reference(record_id=record_id, **self._view_kw())


@pytest.fixture
def ctx() -> _Ctx:
    return _Ctx()


def _member(view, record_id):
    return next(m for m in view.members if m.record_id == record_id)


def _waveform_groups(ctx):
    return sorted(sorted(g.source_ids) for g in list_time_groups(workspace_id=WS, source_registry=ctx.sources))


# ==============================================================================


class TestIndependentRecords:
    """The UAT regression (DEC-128): timestamp overlap never merges Event
    Reconstruction records, while Waveform keeps its own Time Groups."""

    def test_identical_timestamps_stay_two_records(self, ctx):
        ctx.add(_source("BAHS"), _source("BTGH"))
        assert _waveform_groups(ctx) == [["BAHS", "BTGH"]]  # Waveform: one Time Group
        records = ctx.records()
        assert [r.record_id for r in records] == ["BAHS", "BTGH"]
        assert all(r.eligible and r.source_ids == [r.record_id] for r in records)
        view = ctx.define(["BAHS", "BTGH"], "BAHS")
        assert [m.record_id for m in view.members] == ["BAHS", "BTGH"]
        assert _member(view, "BTGH").reconstruction_offset_s == 0.0
        [relation] = view.relationships
        assert relation.kind == RELATIONSHIP_FULL_OVERLAP and relation.overlap_s == pytest.approx(1.0)
        assert view.warnings == []

    def test_partially_overlapping_records_stay_separate(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=0.5)))
        assert _waveform_groups(ctx) == [["A", "B"]]
        view = ctx.define(["A", "B"], "A")
        assert len(view.members) == 2
        assert _member(view, "B").reconstruction_offset_s == pytest.approx(0.5)
        assert view.relationships[0].kind == RELATIONSHIP_PARTIAL_OVERLAP

    def test_contained_record_stays_separate(self, ctx):
        ctx.add(_source("LONG", duration_s=10.0), _source("SHORT", start=T0 + timedelta(seconds=2)))
        assert _waveform_groups(ctx) == [["LONG", "SHORT"]]
        view = ctx.define(["LONG", "SHORT"], "LONG")
        assert len(view.members) == 2
        assert view.relationships[0].kind == RELATIONSHIP_FULL_OVERLAP

    def test_uat_example_three_records(self, ctx):
        ctx.add(
            _source("AGJH", start=T0 - timedelta(seconds=30)),
            _source("BAHS"), _source("BTGH"),
        )
        view = ctx.define(["AGJH", "BAHS", "BTGH"], "AGJH")
        assert [m.record_id for m in view.members] == ["AGJH", "BAHS", "BTGH"]
        assert [m.source_ids for m in view.members] == [["AGJH"], ["BAHS"], ["BTGH"]]

    def test_overlapping_upload_does_not_stale_an_existing_member(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.add(_source("A_OVERLAP", start=T0 + timedelta(seconds=0.5)))  # joins A's Waveform Time Group
        view = ctx.view()
        assert view.status == RECONSTRUCTION_STATUS_READY
        assert all(m.status == MEMBER_STATUS_CURRENT for m in view.members)
        assert {r.record_id for r in ctx.records()} == {"A", "B", "A_OVERLAP"}

    def test_each_record_owns_its_correction(self, ctx):
        ctx.add(_source("BAHS"), _source("BTGH"))
        ctx.define(["BAHS", "BTGH"], "BAHS")
        view = ctx.correct("BTGH", 0.004)
        assert _member(view, "BTGH").reconstruction_offset_s == pytest.approx(0.004)
        assert _member(view, "BAHS").reconstruction_offset_s == 0.0
        view = ctx.correct("BAHS", -0.002)  # the reference's own clock
        assert _member(view, "BTGH").reconstruction_offset_s == pytest.approx(0.006)
        assert _member(view, "BTGH").correction_s == 0.004

    def test_gaps_are_between_records_not_merged_extents(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=0.5)))
        ctx.define(["A", "B"], "A")
        [warning] = ctx.correct("B", 7200.0).warnings  # only possible with independent records
        assert (warning.before_record_id, warning.after_record_id) == ("A", "B")
        assert warning.gap_s == pytest.approx(7200.0 + 0.5 - 1.0)


class TestRecordListing:
    def test_records_are_sources_with_utc_extents(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10), duration_s=2.0))
        records = {r.record_id: r for r in ctx.records()}
        a, b = records["A"], records["B"]
        assert a.eligible and b.eligible
        assert a.reason_code is None and a.time_reference_type == "recorded_absolute"
        assert a.start_time_utc == T0 and a.end_time_utc == T0 + timedelta(seconds=1)
        assert b.start_time_utc == T0 + timedelta(seconds=10) and b.duration_s == pytest.approx(2.0)
        assert a.in_reconstruction is False

    def test_eligible_records_chronological_then_ineligible(self, ctx):
        ctx.add(
            _source("LATE", start=T0 + timedelta(seconds=20)), _source("EL", start=None, timing_reference="relative_elapsed"),
            _source("EARLY"),
        )
        assert [r.record_id for r in ctx.records()] == ["EARLY", "LATE", "EL"]

    def test_time_of_day_record_is_ineligible_without_inventing_a_date(self, ctx):
        ctx.add(_source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=3600.0))
        [record] = ctx.records()
        assert record.eligible is False and record.reason_code == "time_of_day_not_supported"
        assert record.start_time_utc is None and record.duration_s == pytest.approx(1.0)

    def test_elapsed_only_record_is_ineligible(self, ctx):
        ctx.add(_source("EL", start=None, timing_reference="relative_elapsed"))
        [record] = ctx.records()
        assert record.eligible is False and record.reason_code == "no_absolute_time_reference"

    def test_sampling_rate_has_no_effect_on_eligibility(self, ctx):
        ctx.add(_source("FAST", rate_hz=5000.0, duration_s=1.3), _source("SLOW", rate_hz=1.0, duration_s=600.0))
        assert all(r.eligible for r in ctx.records())

    def test_in_reconstruction_flag(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)), _source("C", start=T0 + timedelta(seconds=20)))
        ctx.define(["A", "B"], "A")
        assert {r.record_id: r.in_reconstruction for r in ctx.records()} == {"A": True, "B": True, "C": False}


class TestDefinition:
    def test_undefined_reconstruction_reads_as_not_defined(self, ctx):
        view = ctx.view()
        assert view.defined is False and view.members == []
        assert view.large_gap_warning_threshold_s == THRESHOLD_S

    def test_two_records_on_recorded_placement(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        view = ctx.define(["A", "B"], "A")
        assert view.defined and view.status == RECONSTRUCTION_STATUS_READY and view.placements_available
        assert view.reference_record_id == "A" and view.reference_origin_start_time_utc == T0
        a, b = _member(view, "A"), _member(view, "B")
        assert a.is_reference and not b.is_reference
        assert b.recorded_placement_s == pytest.approx(10.0) and b.reconstruction_offset_s == pytest.approx(10.0)
        assert (b.start_s, b.end_s) == (pytest.approx(10.0), pytest.approx(11.0))
        [relation] = view.relationships
        assert relation.kind == RELATIONSHIP_GAP and relation.gap_s == pytest.approx(9.0)

    def test_member_order_follows_selection(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        assert [m.record_id for m in ctx.define(["B", "A"], "A").members] == ["B", "A"]

    @pytest.mark.parametrize(
        ("record_ids", "reference", "error"),
        [
            ([], "A", InvalidReconstructionDefinitionError),
            (["A", "A"], "A", DuplicateReconstructionMemberError),
            (["A", "missing"], "A", SourceNotFoundError),
            (["A", "TOD"], "A", RecordNotEligibleError),
            (["A", "EL"], "A", RecordNotEligibleError),
            (["A", "B"], "C", ReconstructionReferenceNotMemberError),
        ],
    )
    def test_invalid_definitions_are_rejected_and_nothing_is_stored(self, ctx, record_ids, reference, error):
        ctx.add(
            _source("A"), _source("B", start=T0 + timedelta(seconds=10)),
            _source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=100.0),
            _source("EL", start=None, timing_reference="relative_elapsed"),
        )
        with pytest.raises(error):
            ctx.define(record_ids, reference)
        assert ctx.er.get(WS) is None

    def test_ineligible_error_names_the_reason(self, ctx):
        ctx.add(_source("A"), _source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=100.0))
        with pytest.raises(RecordNotEligibleError, match="time_of_day_not_supported"):
            ctx.define(["A", "TOD"], "A")

    def test_redefinition_keeps_corrections_of_retained_records_only(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)), _source("C", start=T0 + timedelta(seconds=20)))
        ctx.define(["A", "B"], "A")
        ctx.correct("B", 0.25)
        ctx.correct("A", 0.5)
        view = ctx.define(["B", "C"], "B")
        assert {m.record_id: m.correction_s for m in view.members} == {"B": 0.25, "C": 0.0}
        assert _member(ctx.define(["A", "B"], "A"), "A").correction_s == 0.0


class TestCorrections:
    @pytest.fixture
    def pair(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        return ctx

    def test_correction_can_create_partial_and_full_overlap(self, pair):
        assert pair.correct("B", -9.5).relationships[0].kind == RELATIONSHIP_PARTIAL_OVERLAP
        assert pair.correct("B", -10.0).relationships[0].kind == RELATIONSHIP_FULL_OVERLAP

    def test_sub_millisecond_correction_is_kept_exactly(self, pair):
        b = _member(pair.correct("B", 0.000123456), "B")
        assert b.correction_s == 0.000123456
        assert b.reconstruction_offset_s == pytest.approx(10.000123456, abs=1e-12)

    def test_reset_restores_recorded_timestamp_placement(self, pair):
        pair.correct("B", -3.0)
        b = _member(pair.reset("B"), "B")
        assert b.correction_s == 0.0 and b.reconstruction_offset_s == pytest.approx(b.recorded_placement_s)

    def test_reference_may_carry_a_correction(self, pair):
        view = pair.correct("A", 0.5)
        assert _member(view, "A").reconstruction_offset_s == 0.0
        assert _member(view, "B").reconstruction_offset_s == pytest.approx(9.5)
        assert _member(view, "B").correction_relative_to_reference_s == -0.5

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_correction_is_rejected_without_change(self, pair, value):
        with pytest.raises(InvalidReconstructionCorrectionError):
            pair.correct("B", value)
        assert pair.er.get(WS).member("B").correction_s == 0.0

    def test_unknown_member_and_undefined_reconstruction(self, ctx):
        ctx.add(_source("A"), _source("Z", start=T0 + timedelta(seconds=10)))
        with pytest.raises(ReconstructionNotDefinedError):
            ctx.correct("A", 1.0)
        ctx.define(["A"], "A")
        with pytest.raises(ReconstructionMemberNotFoundError):
            ctx.correct("Z", 1.0)
        with pytest.raises(ReconstructionMemberNotFoundError):
            ctx.reference("Z")


class TestReferenceSwitching:
    def test_owner_reference_example(self, ctx):
        ctx.add(
            _source("A", duration_s=0.05),
            _source("B", start=T0 + timedelta(milliseconds=100), duration_s=0.05),
            _source("C", start=T0 + timedelta(milliseconds=300), duration_s=0.05),
        )
        view = ctx.define(["A", "B", "C"], "A")
        assert [m.reconstruction_offset_s for m in view.members] == pytest.approx([0.0, 0.1, 0.3], abs=1e-12)
        view = ctx.reference("B")
        assert [m.reconstruction_offset_s for m in view.members] == pytest.approx([-0.1, 0.0, 0.2], abs=1e-12)

    def test_switching_preserves_alignment_and_stored_corrections(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10, microseconds=250)), _source("C"))
        ctx.define(["A", "B", "C"], "A")
        ctx.correct("A", 0.0021)
        ctx.correct("C", -0.0004)
        before = {m.record_id: m.start_s for m in ctx.view().members}
        stored = ctx.er.get(WS).members
        for reference in ("B", "C", "A"):
            view = ctx.reference(reference)
            starts = {m.record_id: m.start_s for m in view.members}
            assert _member(view, reference).reconstruction_offset_s == 0.0
            for a in starts:
                for b in starts:
                    assert starts[a] - starts[b] == pytest.approx(before[a] - before[b], abs=1e-9)
            assert ctx.er.get(WS).members == stored

    def test_reference_change_needs_a_definition(self, ctx):
        ctx.add(_source("A"))
        with pytest.raises(ReconstructionNotDefinedError):
            ctx.reference("A")


class TestLargeGapWarning:
    @pytest.mark.parametrize(("gap_s", "warns"), [(THRESHOLD_S - 0.5, False), (THRESHOLD_S, True), (THRESHOLD_S * 24, True)])
    def test_threshold_is_inclusive_and_advisory(self, ctx, gap_s, warns):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=1.0 + gap_s)))
        view = ctx.define(["A", "B"], "A")
        assert view.status == RECONSTRUCTION_STATUS_READY
        if warns:
            [warning] = view.warnings
            assert warning.code == WARNING_LARGE_GAP and warning.gap_s == pytest.approx(gap_s)
            assert warning.threshold_s == THRESHOLD_S
            assert (warning.before_record_id, warning.after_record_id) == ("A", "B")
        else:
            assert view.warnings == []

    def test_configured_threshold_is_the_one_applied_and_reported(self):
        ctx = _Ctx(threshold_s=60.0)
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=61)))
        view = ctx.define(["A", "B"], "A")
        assert view.large_gap_warning_threshold_s == 60.0
        assert view.warnings[0].threshold_s == 60.0

    def test_identical_records_have_zero_gap(self, ctx):
        ctx.add(_source("BAHS"), _source("BTGH"))
        assert ctx.define(["BAHS", "BTGH"], "BAHS").warnings == []


class TestStaleRecords:
    def test_removed_record_is_stale_and_frozen(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.correct("B", 0.75)
        ctx.remove("B")
        view = ctx.view()
        assert view.status == RECONSTRUCTION_STATUS_STALE
        b = _member(view, "B")
        assert b.status == MEMBER_STATUS_STALE and b.stale_reason == STALE_REASON_RECORD_REMOVED
        assert b.correction_s == 0.75
        assert b.reconstruction_offset_s is None and b.start_s is None and b.source_timings is None
        for action in (lambda: ctx.correct("B", 1.0), lambda: ctx.reset("B"), lambda: ctx.reference("B")):
            with pytest.raises(ReconstructionMemberStaleError):
                action()
        assert ctx.er.get(WS).member("B").correction_s == 0.75
        assert ctx.define(["A"], "A").status == RECONSTRUCTION_STATUS_READY

    def test_stale_reference_withholds_every_placement(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.remove("A")
        view = ctx.view()
        assert view.placements_available is False and view.reference_record_id == "A"
        assert all(m.start_s is None and m.source_timings is None for m in view.members)
        assert _member(ctx.reference("B"), "B").start_s == 0.0

    def test_reuploaded_recording_is_a_new_record(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.correct("B", 0.3)
        ctx.remove("B")
        ctx.add(_source("B2", start=T0 + timedelta(seconds=10)))
        view = ctx.define(["A", "B2"], "A")
        assert _member(view, "B2").correction_s == 0.0  # never transferred


class TestCoordinateModel:
    """Absolute time enters exactly once (the recorded-start difference);
    Waveform Synchronise Sources corrections are never applied."""

    REF = T0 + timedelta(seconds=5)

    @pytest.fixture
    def workspace(self, ctx):
        ctx.add(_source("R", start=self.REF), _source("R2", start=self.REF + timedelta(seconds=0.4)), _source("A"))
        return ctx

    def test_zero_corrections_reproduce_recorded_absolute_time(self, workspace):
        view = workspace.define(["R", "R2", "A"], "R")
        for active in workspace.sources.list_for_workspace(WS):
            expected = (active.metadata.start_time - self.REF).total_seconds()
            assert _member(view, active.metadata.source_id).reconstruction_offset_s == pytest.approx(expected, abs=1e-9)

    def test_synchronise_sources_correction_never_moves_a_record(self, workspace):
        before = {m.record_id: m.reconstruction_offset_s for m in workspace.define(["R", "R2", "A"], "R").members}
        set_source_alignment_offset(workspace_id=WS, source_id="R2", alignment_offset_s=0.25, registry=workspace.sync, source_registry=workspace.sources)
        after = {m.record_id: m.reconstruction_offset_s for m in workspace.view().members}
        assert after == before

    def test_reconstruction_correction_shifts_its_record_exactly_once(self, workspace):
        base = workspace.define(["R", "R2", "A"], "R")
        moved = workspace.correct("R2", 0.0125)
        assert _member(moved, "R2").reconstruction_offset_s - _member(base, "R2").reconstruction_offset_s == pytest.approx(0.0125, abs=1e-12)
        for rid in ("R", "A"):
            assert _member(moved, rid).reconstruction_offset_s == _member(base, rid).reconstruction_offset_s


class TestIsolation:
    def test_service_has_no_time_group_or_synchronization_dependency(self):
        imports = "\n".join(
            line for line in inspect.getsource(er_service).splitlines() if line.startswith(("import ", "from "))
        )
        # Only the pure timestamp helpers of time_grouping are shared; no
        # group derivation and no Synchronise Sources state.
        for forbidden in ("synchronization_service", "synchronization_registry", "SynchronizationRegistry", "TimeGroup"):
            assert forbidden not in imports
        code = inspect.getsource(er_service)
        for forbidden in ("list_time_groups(", "list_source_alignments(", "derive_time_groups("):
            assert forbidden not in code

    def test_time_groups_synchronization_and_source_data_are_unchanged(self, ctx):
        ctx.add(_source("A"), _source("A2", start=T0 + timedelta(seconds=0.5)), _source("B", start=T0 + timedelta(seconds=10)))
        set_source_alignment_offset(workspace_id=WS, source_id="A2", alignment_offset_s=0.003, registry=ctx.sync, source_registry=ctx.sources)
        groups_before = list_time_groups(workspace_id=WS, source_registry=ctx.sources)
        placement_before = list_source_alignments(workspace_id=WS, registry=ctx.sync, source_registry=ctx.sources)
        sync_before = ctx.sync.list_for_workspace(WS)
        times_before = {a.metadata.source_id: a.record.waveform_data["time"].to_numpy().copy() for a in ctx.sources.list_for_workspace(WS)}
        starts_before = {a.metadata.source_id: a.metadata.start_time for a in ctx.sources.list_for_workspace(WS)}

        ctx.define(["A", "A2", "B"], "A")
        ctx.correct("A2", -9.99)
        ctx.reference("B")
        ctx.reset("A2")

        assert list_time_groups(workspace_id=WS, source_registry=ctx.sources) == groups_before
        assert list_source_alignments(workspace_id=WS, registry=ctx.sync, source_registry=ctx.sources) == placement_before
        assert ctx.sync.list_for_workspace(WS) == sync_before
        for active in ctx.sources.list_for_workspace(WS):
            sid = active.metadata.source_id
            assert active.metadata.start_time == starts_before[sid]
            np.testing.assert_array_equal(active.record.waveform_data["time"].to_numpy(), times_before[sid])

    def test_clear_and_teardown_remove_only_this_workspace(self, ctx):
        ctx.add(_source("A"))
        ctx.define(["A"], "A")
        ctx.er.put("other", ctx.er.get(WS))
        clear_reconstruction(workspace_id=WS, registry=ctx.er)
        assert ctx.view().defined is False
        clear_reconstruction(workspace_id=WS, registry=ctx.er)
        remove_workspace_event_reconstruction_state(workspace_id="other", registry=ctx.er)
        assert ctx.er.get("other") is None
