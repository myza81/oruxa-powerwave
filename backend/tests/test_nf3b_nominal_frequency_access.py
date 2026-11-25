"""NF-3B -- the controlled nominal-frequency accessor (`app.services.nominal_frequency_access`).

Independent of every engineering consumer (none uses it yet). The accessor must resolve through the NF-1 authority, say plainly
when no usable frequency exists, never invent a number, never lend a stored Manual value to a consumer while the release gate is
closed, keep recordings and workspaces apart, leave the imported metadata and samples untouched, and give a multi-recording
calculation an order-independent answer that never silently picks "the first recording's" frequency.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import math

import numpy as np
import pytest

from app.domain.calculated_channel import OP_ACTIVE_POWER, ChannelRef
from app.domain.nominal_frequency import (
    MODE_AUTO, MODE_MANUAL, ORIGIN_ASSUMED_DEFAULT, ORIGIN_IMPORT_SUPPLIED, ORIGIN_MANUAL, ORIGIN_RECORDING_METADATA,
    ORIGIN_UNUSABLE,
)
from app.services import nominal_frequency_access as acc
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import create_calculated_channel
from app.services.errors import (
    CalculatedChannelNotFoundError, InvalidNominalFrequencyError, ManualNominalFrequencyDisabledError, SourceNotFoundError,
)
from app.services.nominal_frequency_registry import NominalFrequencyRegistry
from app.services.workspace_registry import WorkspaceRegistry
from tests import nf3b_baseline_scenarios as scn

WS = scn.WS
COMTRADE = {"source_format": "COMTRADE"}
ASSUMED = {"source_format": "COMTRADE", "nominal_frequency_assumed": True}
BEN = {"source_format": "BEN", "nominal_frequency_assumed": False}


def make(*, enabled: bool, sources: dict | None = None):
    """An accessor over fresh registries. `sources`: id -> (declared nominal, provenance)."""
    source_registry, registry = WorkspaceRegistry(), NominalFrequencyRegistry()
    for sid, (nominal, provenance) in (sources or {}).items():
        source_registry.add(scn.build_source(sid, nominal, provenance, 50.0, fs=2000.0, seconds=0.2))
    return acc.NominalFrequencyAccess(source_registry, registry, manual_override_enabled=enabled), source_registry, registry


# ------------------------------------------------------------------------------------------------------ one recording
class TestSingleRecordingOutcome:
    @pytest.mark.parametrize("nominal,prov,hz,origin,assumed", [
        (50.0, COMTRADE, 50.0, ORIGIN_RECORDING_METADATA, False),
        (60.0, COMTRADE, 60.0, ORIGIN_RECORDING_METADATA, False),
        (25.0, COMTRADE, 25.0, ORIGIN_RECORDING_METADATA, False),
        (16.7, COMTRADE, 16.7, ORIGIN_RECORDING_METADATA, False),
        (400.0, COMTRADE, 400.0, ORIGIN_RECORDING_METADATA, False),
        (60.0, BEN, 60.0, ORIGIN_IMPORT_SUPPLIED, False),
        (50.0, ASSUMED, 50.0, ORIGIN_ASSUMED_DEFAULT, True),
        (60.0, ASSUMED, 50.0, ORIGIN_ASSUMED_DEFAULT, True),      # the importer's flag wins: the declared value was not real
    ])
    def test_usable_recordings_carry_value_origin_and_assumption(self, nominal, prov, hz, origin, assumed):
        access, *_ = make(enabled=False, sources={"s": (nominal, prov)})
        r = access.for_source(WS, "s")
        assert (r.usable, r.hz, r.origin, r.assumed, r.status) == (True, hz, origin, assumed, acc.STATUS_USABLE)
        assert (r.mode, r.manual, r.revision, r.source_id) == (MODE_AUTO, False, 0, "s")

    @pytest.mark.parametrize("bad", [0.0, -50.0, float("nan"), float("inf"), float("-inf"), 0.5, 0.999, 1000.001, 1001.0])
    def test_an_unusable_declared_value_is_reported_unavailable_never_replaced_by_a_default(self, bad):
        access, *_ = make(enabled=False, sources={"s": (bad, COMTRADE)})
        r = access.for_source(WS, "s")
        assert r.usable is False and r.hz is None and r.status == acc.STATUS_UNUSABLE
        assert r.origin == ORIGIN_UNUSABLE and r.assumed is False
        assert repr(r.imported_hz) == repr(bad)                      # the imported value stays visible, exactly as imported

    def test_a_missing_declared_value_is_the_documented_default_and_is_marked_assumed(self):
        access, *_ = make(enabled=False, sources={"s": (None, COMTRADE)})
        r = access.for_source(WS, "s")
        assert (r.hz, r.origin, r.assumed, r.imported_hz) == (50.0, ORIGIN_ASSUMED_DEFAULT, True, None)

    def test_an_unknown_recording_is_not_found_not_a_fallback(self):
        access, *_ = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        with pytest.raises(SourceNotFoundError):
            access.for_source(WS, "nope")

    def test_the_outcome_is_immutable(self):
        access, *_ = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        r = access.for_source(WS, "s")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.hz = 60.0


# ------------------------------------------------------------------------------------------------------ the release gate
class TestReleaseGate:
    def test_gate_open_a_manual_value_is_the_effective_frequency_with_its_origin_and_revision(self):
        access, *_ = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        access.set_manual(WS, "s", 60.0)
        r = access.for_source(WS, "s")
        assert (r.hz, r.origin, r.mode, r.manual, r.revision, r.manual_override_enabled) == (60.0, ORIGIN_MANUAL, MODE_MANUAL, True, 1, True)

    def test_gate_open_a_manual_value_corrects_an_unusable_declared_one_and_reset_restores_it(self):
        access, *_ = make(enabled=True, sources={"s": (0.0, COMTRADE)})
        assert not access.for_source(WS, "s").usable
        access.set_manual(WS, "s", 60.0)
        assert access.for_source(WS, "s").hz == 60.0
        access.reset_to_auto(WS, "s")
        r = access.for_source(WS, "s")
        assert not r.usable and r.revision == 2

    def test_gate_open_a_manual_value_equal_to_auto_is_still_manual(self):
        access, *_ = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        access.set_manual(WS, "s", 50.0)
        r = access.for_source(WS, "s")
        assert (r.hz, r.origin, r.manual) == (50.0, ORIGIN_MANUAL, True)

    def test_gate_closed_a_manual_value_is_refused_and_nothing_is_stored(self):
        access, _, registry = make(enabled=False, sources={"s": (50.0, COMTRADE)})
        with pytest.raises(ManualNominalFrequencyDisabledError):
            access.set_manual(WS, "s", 60.0)
        assert registry.snapshot(WS, "s") == (None, 0)
        r = access.for_source(WS, "s")
        assert (r.hz, r.origin, r.revision, r.manual_override_enabled) == (50.0, ORIGIN_RECORDING_METADATA, 0, False)

    @pytest.mark.parametrize("value", [60.0, 0.0, float("nan"), -1.0, True, None])
    def test_gate_closed_refusal_does_not_depend_on_the_value(self, value):
        access, _, registry = make(enabled=False, sources={"s": (50.0, COMTRADE)})
        with pytest.raises(ManualNominalFrequencyDisabledError):
            access.set_manual(WS, "s", value)
        assert registry.snapshot(WS, "s") == (None, 0)

    def test_gate_closed_the_recording_is_still_checked_first(self):
        access, *_ = make(enabled=False)
        with pytest.raises(SourceNotFoundError):
            access.set_manual(WS, "missing", 60.0)

    @pytest.mark.parametrize("nominal,prov,hz,origin", [
        (60.0, COMTRADE, 60.0, ORIGIN_RECORDING_METADATA), (50.0, ASSUMED, 50.0, ORIGIN_ASSUMED_DEFAULT), (0.0, COMTRADE, None, ORIGIN_UNUSABLE)])
    def test_gate_closed_a_value_stored_earlier_never_reaches_a_consumer(self, nominal, prov, hz, origin):
        """The registry can hold a value (stored while the gate was open, or written directly). A closed gate must make it
        invisible to every consumer: the accessor reports the Auto resolution."""
        access, _, registry = make(enabled=False, sources={"s": (nominal, prov)})
        from datetime import datetime, timezone
        registry.set(WS, "s", 33.0, datetime(2026, 11, 25, tzinfo=timezone.utc))
        r = access.for_source(WS, "s")
        assert (r.hz, r.origin, r.mode, r.manual) == (hz, origin, MODE_AUTO, False)
        assert access.effective(WS, "s").manual_hz is None
        multi = access.for_sources(WS, ["s"])
        assert multi.any_manual is False

    def test_gate_closed_returning_to_auto_is_always_allowed_and_idempotent(self):
        access, *_ = make(enabled=False, sources={"s": (60.0, COMTRADE)})
        assert access.reset_to_auto(WS, "s").effective_hz == 60.0
        assert access.reset_to_auto(WS, "s").revision == 0

    def test_the_gate_is_a_property_of_the_accessor_not_of_a_call(self):
        assert make(enabled=True)[0].manual_override_enabled is True
        assert make(enabled=False)[0].manual_override_enabled is False

    @pytest.mark.parametrize("bad", [0, 0.0, -50.0, float("nan"), float("inf"), 0.5, 1001.0, True, "60", None])
    def test_gate_open_validation_is_not_weakened(self, bad):
        access, _, registry = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        with pytest.raises(InvalidNominalFrequencyError):
            access.set_manual(WS, "s", bad)
        assert registry.snapshot(WS, "s") == (None, 0)

    @pytest.mark.parametrize("good", [1.0, 16.7, 25, 50.0, 60.0, 400.0, 1000.0])
    def test_gate_open_the_whole_valid_range_is_accepted(self, good):
        access, *_ = make(enabled=True, sources={"s": (50.0, COMTRADE)})
        assert access.set_manual(WS, "s", good).effective_hz == float(good)


# ---------------------------------------------------------------------------------------------------- isolation, lifecycle
class TestIsolationAndLifecycle:
    def test_recordings_are_independent(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (60.0, COMTRADE)})
        access.set_manual(WS, "a", 25.0)
        assert (access.for_source(WS, "a").hz, access.for_source(WS, "b").hz) == (25.0, 60.0)
        assert access.for_source(WS, "b").revision == 0

    def test_workspaces_are_independent(self):
        access, sources, _ = make(enabled=True, sources={"a": (50.0, COMTRADE)})
        other = dataclasses.replace(sources.get(WS, "a"), metadata=dataclasses.replace(sources.get(WS, "a").metadata, workspace_id="ws-other"))
        sources.add(other)
        access.set_manual(WS, "a", 25.0)
        assert access.for_source("ws-other", "a").hz == 50.0
        with pytest.raises(SourceNotFoundError):
            access.for_source("ws-third", "a")

    def test_a_recording_removed_from_the_workspace_is_not_found_whatever_was_stored(self):
        access, sources, registry = make(enabled=True, sources={"a": (50.0, COMTRADE)})
        access.set_manual(WS, "a", 25.0)
        sources.remove(WS, "a")
        registry.remove_source(WS, "a")
        with pytest.raises(SourceNotFoundError):
            access.for_source(WS, "a")

    def test_re_adding_a_recording_after_removal_starts_from_auto_again(self):
        access, sources, registry = make(enabled=True, sources={"a": (50.0, COMTRADE)})
        access.set_manual(WS, "a", 25.0)
        sources.remove(WS, "a")
        registry.remove_source(WS, "a")
        sources.add(scn.build_source("a", 60.0, COMTRADE, 60.0, fs=2000.0, seconds=0.2))
        r = access.for_source(WS, "a")
        assert (r.hz, r.origin, r.revision) == (60.0, ORIGIN_RECORDING_METADATA, 0)

    def test_a_workspace_reset_clears_the_values_of_that_workspace_only(self):
        access, sources, registry = make(enabled=True, sources={"a": (50.0, COMTRADE)})
        other = dataclasses.replace(sources.get(WS, "a"), metadata=dataclasses.replace(sources.get(WS, "a").metadata, workspace_id="ws-other"))
        sources.add(other)
        access.set_manual(WS, "a", 25.0)
        access.set_manual("ws-other", "a", 40.0)
        sources.remove_workspace(WS)
        registry.remove_workspace(WS)
        with pytest.raises(SourceNotFoundError):
            access.for_source(WS, "a")
        assert access.for_source("ws-other", "a").hz == 40.0

    def test_the_imported_metadata_provenance_and_samples_are_never_modified(self):
        access, sources, _ = make(enabled=True, sources={"s": (0.0, ASSUMED | {"extra": 1})})

        def fingerprint():
            active = sources.get(WS, "s")
            frame = active.record.waveform_data
            digest = hashlib.sha256(np.ascontiguousarray(frame.to_numpy(dtype=np.float64)).tobytes()).hexdigest()
            return (repr(active.metadata), dict(active.metadata.preparation_provenance), active.record.metadata.nominal_frequency, digest)

        before = fingerprint()
        access.set_manual(WS, "s", 60.0)
        access.for_source(WS, "s")
        access.set_manual(WS, "s", 40.0)
        access.reset_to_auto(WS, "s")
        with pytest.raises(InvalidNominalFrequencyError):
            access.set_manual(WS, "s", float("nan"))
        assert fingerprint() == before


# ------------------------------------------------------------------------------------------------ calculated channels
class TestChannelRefInheritance:
    def _with_calculated(self):
        access, sources, _ = make(enabled=True, sources={"a": (60.0, COMTRADE)})
        calcs = CalculatedChannelRegistry()
        channel = create_calculated_channel(
            workspace_id=WS, name="P", operation=OP_ACTIVE_POWER, parameters={}, source_registry=sources, calc_registry=calcs,
            inputs=[ChannelRef(kind="source", source_id="a", channel_name="VA"), ChannelRef(kind="source", source_id="a", channel_name="IA")])
        return access, calcs, channel

    def test_a_source_channel_resolves_to_its_own_recording(self):
        access, calcs, _ = self._with_calculated()
        assert access.for_channel_ref(WS, ChannelRef(kind="source", source_id="a", channel_name="VA"), calc_registry=calcs).hz == 60.0

    def test_a_calculated_channel_inherits_the_frequency_of_the_recording_that_grounds_it(self):
        access, calcs, channel = self._with_calculated()
        ref = ChannelRef(kind="calculated", calculated_channel_id=channel.id)
        assert access.for_channel_ref(WS, ref, calc_registry=calcs).hz == 60.0
        access.set_manual(WS, "a", 40.0)
        r = access.for_channel_ref(WS, ref, calc_registry=calcs)
        assert (r.hz, r.origin, r.source_id) == (40.0, ORIGIN_MANUAL, "a")          # follows the recording, not a stored copy

    def test_an_unknown_calculated_channel_is_an_error_not_a_default(self):
        access, calcs, _ = self._with_calculated()
        with pytest.raises(CalculatedChannelNotFoundError):
            access.for_channel_ref(WS, ChannelRef(kind="calculated", calculated_channel_id="ghost"), calc_registry=calcs)


# ------------------------------------------------------------------------------------------------ several recordings
class TestMultiSourceContract:
    def test_no_recordings(self):
        access, *_ = make(enabled=True)
        m = access.for_sources(WS, [])
        assert (m.status, m.common_hz, m.distinct_hz, m.unusable_source_ids, m.any_assumed, m.any_manual) == (acc.AGREEMENT_EMPTY, None, (), (), False, False)

    def test_agreeing_recordings_give_the_common_value(self):
        access, *_ = make(enabled=True, sources={"a": (60.0, COMTRADE), "b": (60.0, BEN)})
        m = access.for_sources(WS, ["a", "b"])
        assert (m.status, m.common_hz, m.distinct_hz) == (acc.AGREEMENT_AGREED, 60.0, (60.0,))

    def test_the_agreement_tolerance_is_the_one_the_phasor_family_already_uses(self):
        assert (acc.AGREEMENT_REL_TOL, acc.AGREEMENT_ABS_TOL) == (1e-9, 1e-9)
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (50.0 + 1e-10, COMTRADE), "c": (50.001, COMTRADE)})
        assert access.for_sources(WS, ["a", "b"]).status == acc.AGREEMENT_AGREED
        assert access.for_sources(WS, ["a", "c"]).status == acc.AGREEMENT_MIXED

    def test_different_recordings_are_mixed_and_no_value_is_chosen(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (60.0, COMTRADE)})
        m = access.for_sources(WS, ["a", "b"])
        assert (m.status, m.common_hz, m.distinct_hz) == (acc.AGREEMENT_MIXED, None, (50.0, 60.0))

    def test_an_unusable_recording_makes_the_whole_unavailable_and_is_named(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (0.0, COMTRADE), "c": (60.0, COMTRADE)})
        m = access.for_sources(WS, ["a", "b", "c"])
        assert (m.status, m.common_hz, m.unusable_source_ids) == (acc.AGREEMENT_UNAVAILABLE, None, ("b",))
        assert m.distinct_hz == (50.0, 60.0)                        # what the usable ones say stays visible

    def test_the_answer_never_depends_on_the_order_of_the_recordings(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (60.0, COMTRADE), "c": (50.0, ASSUMED), "d": (0.0, COMTRADE)})
        for ids in (["a", "b"], ["a", "c"], ["a", "b", "c"], ["a", "c", "d"], ["b", "c"]):
            answers = {(m.status, m.common_hz, m.distinct_hz, tuple(sorted(m.unusable_source_ids)))
                       for m in (access.for_sources(WS, list(p)) for p in itertools.permutations(ids))}
            assert len(answers) == 1, ids

    def test_flags_and_revisions_travel_with_the_members(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, ASSUMED), "b": (60.0, COMTRADE)})
        access.set_manual(WS, "b", 50.0)
        m = access.for_sources(WS, ["a", "b"])
        assert (m.status, m.common_hz, m.any_assumed, m.any_manual) == (acc.AGREEMENT_AGREED, 50.0, True, True)
        assert m.revisions == (("a", 0), ("b", 1))

    def test_duplicates_collapse_and_order_of_first_mention_is_kept(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (50.0, COMTRADE)})
        assert [x.source_id for x in access.for_sources(WS, ["b", "a", "b"]).members] == ["b", "a"]

    def test_a_manual_value_on_one_recording_resolves_a_disagreement(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE), "b": (60.0, COMTRADE)})
        assert access.for_sources(WS, ["a", "b"]).status == acc.AGREEMENT_MIXED
        access.set_manual(WS, "b", 50.0)
        assert access.for_sources(WS, ["a", "b"]).status == acc.AGREEMENT_AGREED

    def test_with_the_gate_closed_a_dormant_manual_value_cannot_resolve_or_create_a_disagreement(self):
        from datetime import datetime, timezone
        access, _, registry = make(enabled=False, sources={"a": (50.0, COMTRADE), "b": (60.0, COMTRADE)})
        registry.set(WS, "b", 50.0, datetime(2026, 11, 25, tzinfo=timezone.utc))
        assert access.for_sources(WS, ["a", "b"]).status == acc.AGREEMENT_MIXED

    def test_one_unknown_recording_is_an_error_for_the_whole_request(self):
        access, *_ = make(enabled=True, sources={"a": (50.0, COMTRADE)})
        with pytest.raises(SourceNotFoundError):
            access.for_sources(WS, ["a", "ghost"])

    def test_combine_is_pure_and_matches_the_contract_for_hand_built_members(self):
        def member(sid, hz):
            return acc.SourceFrequency(source_id=sid, hz=hz, origin=ORIGIN_RECORDING_METADATA if hz else ORIGIN_UNUSABLE, mode=MODE_AUTO,
                                       revision=0, imported_hz=hz, manual_override_enabled=False)
        assert acc.combine([member("x", 50.0), member("y", 50.0)]).common_hz == 50.0
        assert acc.combine([member("x", 50.0), member("y", None)]).status == acc.AGREEMENT_UNAVAILABLE
        assert acc.combine([member("x", 50.0), member("y", 60.0)]).common_hz is None
        assert math.isclose(acc.combine([member("x", 60.0), member("y", 60.0 + 1e-12)]).common_hz, 60.0)
