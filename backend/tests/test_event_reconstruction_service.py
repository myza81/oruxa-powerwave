"""Service-layer tests for Event Reconstruction (DEC-123/DEC-124):
eligibility listing, definition/member validation, per-group
corrections, reference switching, large-gap warnings, stale membership,
and isolation from Waveform Time Groups and Synchronise Sources."""

from __future__ import annotations

import inspect
import math
import re
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
    membership_fingerprint,
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
    TimeGroupNotEligibleError,
    TimeGroupNotFoundError,
)
from app.services.event_reconstruction_registry import EventReconstructionRegistry
from app.services.event_reconstruction_service import (
    MEMBER_STATUS_CURRENT,
    MEMBER_STATUS_STALE,
    RECONSTRUCTION_STATUS_READY,
    RECONSTRUCTION_STATUS_STALE,
    STALE_REASON_MEMBERSHIP_CHANGED,
    STALE_REASON_SOURCES_REMOVED,
    WARNING_LARGE_GAP,
    clear_reconstruction,
    get_reconstruction,
    list_reconstruction_time_groups,
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
#: The centrally configured default (app.config), never a domain literal.
THRESHOLD_S = DEFAULT_EVENT_RECONSTRUCTION_LARGE_GAP_WARNING_S
T0 = datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc)


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


class _WriteForbiddenSynchronizationRegistry(SynchronizationRegistry):
    """Fails the test on any write -- Event Reconstruction may only read
    Synchronise Sources state."""

    def _forbidden(self, *args, **kwargs):
        raise AssertionError("Event Reconstruction must never write SynchronizationRegistry")

    set_offset = reset_offset = remove_source = remove_workspace = _forbidden
    set_t0 = clear_t0 = clear_all_t0_for_workspace = _forbidden


class _Ctx:
    def __init__(self, sync: SynchronizationRegistry, threshold_s: float = THRESHOLD_S):
        self.sources = WorkspaceRegistry()
        self.sync = sync
        self.er = EventReconstructionRegistry()
        self.threshold_s = threshold_s

    def add(self, *sources: ActiveSource) -> None:
        for source in sources:
            self.sources.add(source)

    def remove(self, source_id: str) -> None:
        self.sources.remove(WS, source_id)

    def _kw(self) -> dict:
        return {"workspace_id": WS, "registry": self.er, "source_registry": self.sources, "synchronization_registry": self.sync}

    def _view_kw(self) -> dict:
        return {**self._kw(), "large_gap_threshold_s": self.threshold_s}

    def groups(self):
        return list_reconstruction_time_groups(**self._kw())

    def define(self, group_ids, reference):
        return set_reconstruction_definition(group_ids=list(group_ids), reference_group_id=reference, **self._view_kw())

    def view(self):
        return get_reconstruction(**self._view_kw())

    def correct(self, member_id, value):
        return set_member_correction(member_id=member_id, correction_s=value, **self._view_kw())

    def reset(self, member_id):
        return reset_member_correction(member_id=member_id, **self._view_kw())

    def reference(self, member_id):
        return set_reconstruction_reference(member_id=member_id, **self._view_kw())


@pytest.fixture
def ctx() -> _Ctx:
    return _Ctx(_WriteForbiddenSynchronizationRegistry())


def _fp(*source_ids: str) -> str:
    return membership_fingerprint(source_ids)


def _member(view, member_id):
    return next(m for m in view.members if m.member_id == member_id)


# ==============================================================================


class TestEligibilityListing:
    def test_absolute_groups_are_eligible_with_utc_extents(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10), duration_s=2.0))
        groups = {g.group_id: g for g in ctx.groups()}
        assert set(groups) == {"A", "B"}
        a, b = groups["A"], groups["B"]
        assert a.eligible and b.eligible
        assert a.reason_code is None and a.reason_message is None
        assert a.time_reference_type == "recorded_absolute"
        assert a.start_time_utc == T0
        assert a.end_time_utc == T0 + timedelta(seconds=1)
        assert b.start_time_utc == T0 + timedelta(seconds=10)
        assert b.duration_s == pytest.approx(2.0)
        assert a.membership_fingerprint == _fp("A")
        assert a.reconstruction_member_id is None

    def test_time_of_day_group_is_ineligible_without_inventing_a_date(self, ctx):
        ctx.add(_source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=3600.0))
        [group] = ctx.groups()
        assert group.time_reference_type == "time_of_day"
        assert group.eligible is False
        assert group.reason_code == "time_of_day_not_supported"
        assert group.start_time_utc is None and group.end_time_utc is None
        assert group.duration_s == pytest.approx(1.0)

    def test_elapsed_only_group_is_ineligible(self, ctx):
        ctx.add(_source("EL", start=None, timing_reference="relative_elapsed"))
        [group] = ctx.groups()
        assert group.time_reference_type == "elapsed_only"
        assert group.eligible is False
        assert group.reason_code == "no_absolute_time_reference"
        assert group.start_time_utc is None

    def test_sampling_rate_has_no_effect_on_eligibility(self, ctx):
        ctx.add(
            _source("FAST", rate_hz=5000.0, duration_s=1.3),
            _source("SLOW", start=T0 + timedelta(seconds=100), rate_hz=1.0, duration_s=600.0),
        )
        assert all(g.eligible for g in ctx.groups())

    def test_listing_follows_existing_time_groups_exactly(self, ctx):
        ctx.add(_source("A"), _source("A2", start=T0 + timedelta(seconds=0.5)), _source("B", start=T0 + timedelta(seconds=10)))
        expected = list_time_groups(workspace_id=WS, source_registry=ctx.sources)
        listed = ctx.groups()
        assert [g.group_id for g in listed] == [g.group_id for g in expected]
        assert [g.source_ids for g in listed] == [list(g.source_ids) for g in expected]

    def test_member_id_is_reported_once_selected(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        assert {g.group_id: g.reconstruction_member_id for g in ctx.groups()} == {"A": _fp("A"), "B": _fp("B")}

    def test_group_extent_uses_existing_within_group_synchronization(self):
        ctx = _Ctx(SynchronizationRegistry())
        ctx.add(_source("A"), _source("A2", start=T0 + timedelta(seconds=0.5)))
        set_source_alignment_offset(
            workspace_id=WS, source_id="A2", alignment_offset_s=2.0, registry=ctx.sync, source_registry=ctx.sources
        )
        [group] = ctx.groups()
        # A2: recorded +0.5 s, manual +2.0 s -> group time 2.5 .. 3.5
        assert group.duration_s == pytest.approx(3.5)
        assert group.end_time_utc == T0 + timedelta(seconds=3.5)


class TestDefinition:
    def test_undefined_reconstruction_reads_as_not_defined(self, ctx):
        view = ctx.view()
        assert view.defined is False
        assert view.members == [] and view.warnings == []
        assert view.large_gap_warning_threshold_s == THRESHOLD_S

    def test_two_groups_form_one_reconstruction_on_recorded_placement(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        view = ctx.define(["A", "B"], "A")
        assert view.defined and view.status == RECONSTRUCTION_STATUS_READY
        assert view.placements_available
        assert view.reference_member_id == _fp("A")
        assert view.reference_origin_start_time_utc == T0
        a, b = _member(view, _fp("A")), _member(view, _fp("B"))
        assert a.is_reference and not b.is_reference
        assert (a.status, b.status) == (MEMBER_STATUS_CURRENT, MEMBER_STATUS_CURRENT)
        assert a.reconstruction_offset_s == 0.0
        assert b.recorded_placement_s == pytest.approx(10.0)
        assert b.reconstruction_offset_s == pytest.approx(10.0)
        assert (b.start_s, b.end_s) == (pytest.approx(10.0), pytest.approx(11.0))
        assert a.correction_s == b.correction_s == 0.0
        [relation] = view.relationships
        assert relation.kind == RELATIONSHIP_GAP and relation.gap_s == pytest.approx(9.0)
        assert view.warnings == []

    def test_member_order_follows_selection(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        view = ctx.define(["B", "A"], "A")
        assert [m.member_id for m in view.members] == [_fp("B"), _fp("A")]

    def test_owner_reference_example(self, ctx):
        ctx.add(
            _source("A", duration_s=0.05),
            _source("B", start=T0 + timedelta(milliseconds=100), duration_s=0.05),
            _source("C", start=T0 + timedelta(milliseconds=300), duration_s=0.05),
        )
        view = ctx.define(["A", "B", "C"], "A")
        assert [m.reconstruction_offset_s for m in view.members] == pytest.approx([0.0, 0.1, 0.3], abs=1e-12)
        view = ctx.reference(_fp("B"))
        assert [m.reconstruction_offset_s for m in view.members] == pytest.approx([-0.1, 0.0, 0.2], abs=1e-12)

    @pytest.mark.parametrize(
        ("group_ids", "reference", "error"),
        [
            ([], "A", InvalidReconstructionDefinitionError),
            (["A", "A"], "A", DuplicateReconstructionMemberError),
            (["A", "missing"], "A", TimeGroupNotFoundError),
            (["A", "TOD"], "A", TimeGroupNotEligibleError),
            (["A", "EL"], "A", TimeGroupNotEligibleError),
            (["A", "B"], "C", ReconstructionReferenceNotMemberError),
        ],
    )
    def test_invalid_definitions_are_rejected_and_nothing_is_stored(self, ctx, group_ids, reference, error):
        ctx.add(
            _source("A"), _source("B", start=T0 + timedelta(seconds=10)),
            _source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=100.0),
            _source("EL", start=None, timing_reference="relative_elapsed"),
        )
        with pytest.raises(error):
            ctx.define(group_ids, reference)
        assert ctx.er.get(WS) is None

    def test_ineligible_error_names_the_reason(self, ctx):
        ctx.add(_source("A"), _source("TOD", start=None, timing_reference="time_of_day", time_of_day_s=100.0))
        with pytest.raises(TimeGroupNotEligibleError, match="time_of_day_not_supported"):
            ctx.define(["A", "TOD"], "A")

    def test_redefinition_keeps_corrections_of_retained_members_only(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)), _source("C", start=T0 + timedelta(seconds=20)))
        ctx.define(["A", "B"], "A")
        ctx.correct(_fp("B"), 0.25)
        ctx.correct(_fp("A"), 0.5)
        view = ctx.define(["B", "C"], "B")
        assert {m.member_id: m.correction_s for m in view.members} == {_fp("B"): 0.25, _fp("C"): 0.0}
        view = ctx.define(["A", "B"], "A")
        assert _member(view, _fp("A")).correction_s == 0.0  # dropped earlier, so not remembered


class TestCorrections:
    @pytest.fixture
    def pair(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        return ctx

    def test_correction_is_stored_per_group_and_can_create_partial_overlap(self, pair):
        view = pair.correct(_fp("B"), -9.5)
        b = _member(view, _fp("B"))
        assert b.correction_s == -9.5
        assert (b.start_s, b.end_s) == (pytest.approx(0.5), pytest.approx(1.5))
        assert view.relationships[0].kind == RELATIONSHIP_PARTIAL_OVERLAP
        assert view.relationships[0].overlap_s == pytest.approx(0.5)
        assert pair.er.get(WS).member(_fp("B")).correction_s == -9.5

    def test_correction_can_create_full_overlap(self, pair):
        view = pair.correct(_fp("B"), -10.0)
        assert view.relationships[0].kind == RELATIONSHIP_FULL_OVERLAP

    def test_sub_millisecond_correction_is_kept_exactly(self, pair):
        view = pair.correct(_fp("B"), 0.000123456)
        b = _member(view, _fp("B"))
        assert b.correction_s == 0.000123456
        assert b.reconstruction_offset_s == pytest.approx(10.000123456, abs=1e-12)

    def test_reset_restores_recorded_timestamp_placement(self, pair):
        pair.correct(_fp("B"), -3.0)
        view = pair.reset(_fp("B"))
        b = _member(view, _fp("B"))
        assert b.correction_s == 0.0
        assert b.reconstruction_offset_s == pytest.approx(b.recorded_placement_s)

    def test_reference_may_carry_a_correction(self, pair):
        view = pair.correct(_fp("A"), 0.5)
        a, b = _member(view, _fp("A")), _member(view, _fp("B"))
        assert a.reconstruction_offset_s == 0.0
        assert b.reconstruction_offset_s == pytest.approx(9.5)
        assert b.correction_relative_to_reference_s == -0.5

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_correction_is_rejected_without_change(self, pair, value):
        with pytest.raises(InvalidReconstructionCorrectionError):
            pair.correct(_fp("B"), value)
        assert pair.er.get(WS).member(_fp("B")).correction_s == 0.0

    def test_unknown_member_and_undefined_reconstruction(self, ctx):
        ctx.add(_source("A"))
        with pytest.raises(ReconstructionNotDefinedError):
            ctx.correct(_fp("A"), 1.0)
        ctx.define(["A"], "A")
        with pytest.raises(ReconstructionMemberNotFoundError):
            ctx.correct("tgm1-unknown", 1.0)
        with pytest.raises(ReconstructionMemberNotFoundError):
            ctx.reference("tgm1-unknown")


class TestReferenceSwitching:
    def test_switching_reference_preserves_alignment_and_stored_corrections(self, ctx):
        ctx.add(
            _source("A"), _source("B", start=T0 + timedelta(seconds=10, microseconds=250)),
            _source("C", start=T0 - timedelta(seconds=30)),
        )
        ctx.define(["A", "B", "C"], "A")
        ctx.correct(_fp("A"), 0.0021)
        ctx.correct(_fp("B"), -0.0004)
        before = {m.member_id: m.start_s for m in ctx.view().members}
        stored_before = ctx.er.get(WS).members
        for reference in ("B", "C", "A"):
            view = ctx.reference(_fp(reference))
            starts = {m.member_id: m.start_s for m in view.members}
            assert _member(view, _fp(reference)).reconstruction_offset_s == 0.0
            for a in starts:
                for b in starts:
                    assert starts[a] - starts[b] == pytest.approx(before[a] - before[b], abs=1e-9)
            assert ctx.er.get(WS).members == stored_before

    def test_reference_change_needs_a_definition(self, ctx):
        with pytest.raises(ReconstructionNotDefinedError):
            ctx.reference(_fp("A"))


class TestLargeGapWarning:
    @pytest.mark.parametrize(
        ("gap_s", "warns"),
        [(THRESHOLD_S - 0.5, False), (THRESHOLD_S, True), (THRESHOLD_S * 24, True)],
    )
    def test_threshold_is_inclusive_and_advisory(self, ctx, gap_s, warns):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=1.0 + gap_s)))
        view = ctx.define(["A", "B"], "A")
        assert view.status == RECONSTRUCTION_STATUS_READY  # never rejected
        assert all(m.start_s is not None for m in view.members)
        if warns:
            [warning] = view.warnings
            assert warning.code == WARNING_LARGE_GAP
            assert warning.gap_s == pytest.approx(gap_s)
            assert warning.threshold_s == THRESHOLD_S
            assert (warning.before_member_id, warning.after_member_id) == (_fp("A"), _fp("B"))
            assert "apart" in warning.message
        else:
            assert view.warnings == []

    def test_configured_threshold_is_the_one_applied_and_reported(self):
        ctx = _Ctx(_WriteForbiddenSynchronizationRegistry(), threshold_s=60.0)
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=61)))
        view = ctx.define(["A", "B"], "A")
        assert view.large_gap_warning_threshold_s == 60.0
        [warning] = view.warnings
        assert warning.threshold_s == 60.0 and warning.gap_s == pytest.approx(60.0)
        assert view.status == RECONSTRUCTION_STATUS_READY

    def test_a_correction_can_add_or_remove_the_warning(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        assert len(ctx.correct(_fp("B"), 4000.0).warnings) == 1
        assert ctx.correct(_fp("B"), 0.0).warnings == []


class TestCoordinateModel:
    """Guards against double counting absolute time. `source_time` is a
    source's own elapsed time (0 = its recorded start_time); absolute time
    enters only through the two groups' ORIGIN start difference. With
    every correction 0, reconstruction time must map each sample back to
    its true recorded absolute instant relative to the reference origin."""

    REF_ORIGIN = T0 + timedelta(seconds=5)

    @pytest.fixture
    def workspace(self):
        ctx = _Ctx(SynchronizationRegistry())
        ctx.add(
            # Reference group: R (origin) + R2; not the earliest overall.
            _source("R", start=self.REF_ORIGIN),
            _source("R2", start=self.REF_ORIGIN + timedelta(seconds=0.4)),
            # Other group: A (origin) + A2, recorded 5 s before R.
            _source("A", start=T0),
            _source("A2", start=T0 + timedelta(seconds=0.3), duration_s=1.2),
        )
        return ctx

    @staticmethod
    def _reconstruction_start(ctx, view, source_id):
        """Reconstruction time of a source's first sample (elapsed 0):
        source_time + effective within-group offset + member offset."""
        effective = {
            v.source_id: v.effective_alignment_offset_s
            for v in list_source_alignments(workspace_id=WS, registry=ctx.sync, source_registry=ctx.sources)
        }
        member = next(m for m in view.members if source_id in m.source_ids)
        return 0.0 + effective[source_id] + member.reconstruction_offset_s

    def test_zero_corrections_reproduce_recorded_absolute_time(self, workspace):
        view = workspace.define(["R", "A"], "R")
        for active in workspace.sources.list_for_workspace(WS):
            expected = (active.metadata.start_time - self.REF_ORIGIN).total_seconds()
            actual = self._reconstruction_start(workspace, view, active.metadata.source_id)
            assert actual == pytest.approx(expected, abs=1e-9)
        # Member extents are the union of their sources in the same frame.
        assert _member(view, _fp("A", "A2")).start_s == pytest.approx(-5.0, abs=1e-9)
        assert _member(view, _fp("A", "A2")).end_s == pytest.approx(-5.0 + 0.3 + 1.2, abs=1e-9)
        assert _member(view, _fp("R", "R2")).end_s == pytest.approx(1.4, abs=1e-9)

    def test_reconstruction_correction_shifts_its_group_exactly_once(self, workspace):
        base = workspace.define(["R", "A"], "R")
        moved = workspace.correct(_fp("A", "A2"), 0.0125)
        for sid in ("A", "A2"):
            delta = self._reconstruction_start(workspace, moved, sid) - self._reconstruction_start(workspace, base, sid)
            assert delta == pytest.approx(0.0125, abs=1e-12)
        for sid in ("R", "R2"):
            assert self._reconstruction_start(workspace, moved, sid) == self._reconstruction_start(workspace, base, sid)

    def test_synchronise_sources_offset_shifts_only_its_source_exactly_once(self, workspace):
        base = workspace.define(["R", "A"], "R")
        before = {sid: self._reconstruction_start(workspace, base, sid) for sid in ("R", "R2", "A", "A2")}
        set_source_alignment_offset(
            workspace_id=WS, source_id="A2", alignment_offset_s=0.002, registry=workspace.sync,
            source_registry=workspace.sources,
        )
        after_view = workspace.view()
        after = {sid: self._reconstruction_start(workspace, after_view, sid) for sid in before}
        assert after["A2"] - before["A2"] == pytest.approx(0.002, abs=1e-12)
        assert {sid: after[sid] for sid in ("R", "R2", "A")} == {sid: before[sid] for sid in ("R", "R2", "A")}
        # A within-group sync never changes the group's own reconstruction offset.
        assert (
            _member(after_view, _fp("A", "A2")).reconstruction_offset_s
            == _member(base, _fp("A", "A2")).reconstruction_offset_s
        )

    def test_reference_switch_moves_only_the_zero_point(self, workspace):
        from_r = workspace.define(["R", "A"], "R")
        from_a = workspace.reference(_fp("A", "A2"))
        shift = self._reconstruction_start(workspace, from_a, "R") - self._reconstruction_start(workspace, from_r, "R")
        assert shift == pytest.approx(5.0, abs=1e-9)
        for sid in ("R2", "A", "A2"):
            moved = self._reconstruction_start(workspace, from_a, sid) - self._reconstruction_start(workspace, from_r, sid)
            assert moved == pytest.approx(shift, abs=1e-9)


class TestStaleMembership:
    def test_merge_marks_the_member_stale_and_freezes_its_correction(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "B")
        ctx.correct(_fp("A"), 0.75)
        ctx.add(_source("A2", start=T0 + timedelta(seconds=0.5)))  # joins A's Time Group

        view = ctx.view()
        assert view.status == RECONSTRUCTION_STATUS_STALE
        a = _member(view, _fp("A"))
        assert a.status == MEMBER_STATUS_STALE
        assert a.stale_reason == STALE_REASON_MEMBERSHIP_CHANGED
        assert a.candidate_group_ids == ["A"]
        assert a.current_group_id is None
        assert a.correction_s == 0.75  # kept, never applied
        assert a.reconstruction_offset_s is None and a.start_s is None
        b = _member(view, _fp("B"))
        assert b.status == MEMBER_STATUS_CURRENT and b.start_s == 0.0
        assert view.relationships == [] and view.warnings == []

    def test_stale_correction_is_never_applied_to_the_changed_group(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "B")
        ctx.correct(_fp("A"), 0.75)
        ctx.add(_source("A2", start=T0 + timedelta(seconds=0.5)))
        with pytest.raises(ReconstructionMemberStaleError):
            ctx.correct(_fp("A"), 1.0)
        with pytest.raises(ReconstructionMemberStaleError):
            ctx.reset(_fp("A"))
        with pytest.raises(ReconstructionMemberStaleError):
            ctx.reference(_fp("A"))
        assert ctx.er.get(WS).member(_fp("A")).correction_s == 0.75

        # Re-confirmation starts a fresh member for the new membership.
        view = ctx.define(["A", "B"], "B")
        assert view.status == RECONSTRUCTION_STATUS_READY
        new_member = _member(view, _fp("A", "A2"))
        assert new_member.correction_s == 0.0
        assert all(m.member_id != _fp("A") for m in view.members)

    def test_stale_reference_withholds_every_placement(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.add(_source("A2", start=T0 + timedelta(seconds=0.5)))
        view = ctx.view()
        assert view.placements_available is False
        assert view.reference_member_id == _fp("A")
        assert view.reference_origin_start_time_utc is None
        assert all(m.start_s is None and m.reconstruction_offset_s is None for m in view.members)
        assert _member(view, _fp("B")).status == MEMBER_STATUS_CURRENT
        # A current member can become the reference to recover placements.
        view = ctx.reference(_fp("B"))
        assert view.placements_available and _member(view, _fp("B")).start_s == 0.0

    def test_split_reports_every_group_the_sources_now_belong_to(self, ctx):
        ctx.add(
            _source("X"), _source("BRIDGE", start=T0 + timedelta(seconds=0.5), duration_s=2.0),
            _source("Y", start=T0 + timedelta(seconds=2.0)),
        )
        ctx.define(["X"], "X")
        ctx.remove("BRIDGE")
        member = ctx.view().members[0]
        assert member.status == MEMBER_STATUS_STALE
        assert member.stale_reason == STALE_REASON_MEMBERSHIP_CHANGED
        assert member.candidate_group_ids == ["X", "Y"]

    def test_removing_every_source_reports_sources_removed(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.remove("B")
        b = _member(ctx.view(), _fp("B"))
        assert b.stale_reason == STALE_REASON_SOURCES_REMOVED
        assert b.candidate_group_ids == []

    def test_unrelated_new_group_does_not_stale_existing_members(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.define(["A", "B"], "A")
        ctx.add(_source("C", start=T0 + timedelta(seconds=100)))
        assert ctx.view().status == RECONSTRUCTION_STATUS_READY


class TestIsolation:
    def test_full_flow_never_writes_synchronization_state(self, ctx):
        ctx.add(_source("A"), _source("B", start=T0 + timedelta(seconds=10)))
        ctx.groups()
        ctx.define(["A", "B"], "A")
        ctx.correct(_fp("B"), -1.25)
        ctx.reference(_fp("B"))
        ctx.reset(_fp("B"))
        ctx.view()
        clear_reconstruction(workspace_id=WS, registry=ctx.er)
        remove_workspace_event_reconstruction_state(workspace_id=WS, registry=ctx.er)
        # _WriteForbiddenSynchronizationRegistry would have failed on any write.

    def test_time_groups_waveform_placement_and_source_data_are_unchanged(self):
        ctx = _Ctx(SynchronizationRegistry())
        ctx.add(
            _source("A"), _source("A2", start=T0 + timedelta(seconds=0.5)),
            _source("B", start=T0 + timedelta(seconds=10)),
        )
        set_source_alignment_offset(
            workspace_id=WS, source_id="A2", alignment_offset_s=0.003, registry=ctx.sync, source_registry=ctx.sources
        )
        groups_before = list_time_groups(workspace_id=WS, source_registry=ctx.sources)
        placement_before = list_source_alignments(workspace_id=WS, registry=ctx.sync, source_registry=ctx.sources)
        sync_offsets_before = ctx.sync.list_for_workspace(WS)
        metadata_before = {a.metadata.source_id: (a.metadata.start_time, a.metadata.elapsed_start_seconds, a.metadata.elapsed_end_seconds) for a in ctx.sources.list_for_workspace(WS)}
        times_before = {a.metadata.source_id: a.record.waveform_data["time"].to_numpy().copy() for a in ctx.sources.list_for_workspace(WS)}

        ctx.define(["A", "B"], "A")
        ctx.correct(_fp("B"), -9.99)
        ctx.correct(_fp("A", "A2"), 3.0)
        ctx.reference(_fp("B"))

        assert list_time_groups(workspace_id=WS, source_registry=ctx.sources) == groups_before
        assert list_source_alignments(workspace_id=WS, registry=ctx.sync, source_registry=ctx.sources) == placement_before
        assert ctx.sync.list_for_workspace(WS) == sync_offsets_before
        for active in ctx.sources.list_for_workspace(WS):
            sid = active.metadata.source_id
            assert (active.metadata.start_time, active.metadata.elapsed_start_seconds, active.metadata.elapsed_end_seconds) == metadata_before[sid]
            np.testing.assert_array_equal(active.record.waveform_data["time"].to_numpy(), times_before[sid])

    def test_service_has_no_synchronization_write_path(self):
        source = inspect.getsource(er_service)
        assert not re.search(r"synchronization_registry\.\w+\(", source)
        for forbidden in ("set_source_alignment_offset", "reset_source_alignment_offset", "reset_all_alignment_offsets", "set_t0", "clear_t0"):
            assert forbidden not in source

    def test_clear_and_teardown_remove_only_this_workspace(self, ctx):
        ctx.add(_source("A"))
        ctx.define(["A"], "A")
        ctx.er.put("other", ctx.er.get(WS))
        clear_reconstruction(workspace_id=WS, registry=ctx.er)
        assert ctx.view().defined is False
        clear_reconstruction(workspace_id=WS, registry=ctx.er)  # idempotent
        remove_workspace_event_reconstruction_state(workspace_id="other", registry=ctx.er)
        assert ctx.er.get("other") is None
