"""Tests for app.services.per_unit_registry (Phase 5C, DEC-049;
source-bound redesign following owner UAT): PerUnitRegistry's source-
keyed configuration storage, automatic source-channel resolution (no
assignment tracking needed at all), the calculated-channel assignment
index (decision 7's two-axis `mode`/`profile_id` model, unchanged), and
the inheritance-recompute cascade.

A recurring requirement, per the owner's own UAT: source A's own
configuration must apply ONLY to source A's own channels, source B must
remain completely independent, and two sources sharing the SAME
filename must never collide (source identity is the workspace_id +
source_id pair, never the filename) -- see TestSourceOwnershipIsolation
below.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.domain.calculated_channel import OP_ADDITION, OP_RMS, CalculatedChannel, ChannelRef
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.disturbance_record import DisturbanceRecord
from app.domain.metadata import RecordingMetadata
from app.domain.per_unit import PerUnitBaseProfile
from app.domain.source import ActiveSource, AnalogChannelSummary, SourceMetadata
from app.domain.timing import SamplingInformation, TimingInformation
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.per_unit_registry import PerUnitRegistry, recompute_inherited_per_unit_assignments
from app.services.workspace_registry import WorkspaceRegistry

import pandas as pd


def _profile(source_id: str, workspace_id: str = "ws-1", **overrides) -> PerUnitBaseProfile:
    defaults = dict(
        voltage_base_value=275.0,
        voltage_reference_mode="auto",
        voltage_reference_override=None,
        current_base_mode="none",
        apparent_power_base_value=None,
        direct_current_base_value=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return PerUnitBaseProfile(source_id=source_id, workspace_id=workspace_id, **defaults)


def _calc(calc_id: str, operation: str, inputs: list[ChannelRef], workspace_id: str = "ws-1") -> CalculatedChannel:
    n = 4
    return CalculatedChannel(
        id=calc_id,
        workspace_id=workspace_id,
        name=calc_id,
        unit="V",
        operation=operation,
        inputs=inputs,
        parameters={},
        dependency_ids=[ref.calculated_channel_id for ref in inputs if ref.kind == "calculated"],
        reference_source_id="src-1",
        time=np.arange(n, dtype=np.float64),
        values=np.ones(n, dtype=np.float64),
        created_at=datetime.now(timezone.utc),
    )


def _active_source(source_id: str, workspace_id: str, channel_names_and_types: list[tuple[str, str]]) -> ActiveSource:
    """Minimal ActiveSource fixture -- only `metadata.analog_channels` is
    actually consulted by the recompute engine's own engineering-type
    lookup, but `record` still needs to satisfy DisturbanceRecord's real
    constructor (mirrors tests/test_waveform_service.py's own
    `_active_source()` helper)."""
    now = datetime.now(timezone.utc)
    analog_channels = [
        AnalogChannelSummary(name=name, index=i, unit="V" if etype == VOLTAGE else "A", engineering_type=etype)
        for i, (name, etype) in enumerate(channel_names_and_types)
    ]
    columns = {"time": [0.0, 0.25, 0.5, 0.75]}
    for name, _etype in channel_names_and_types:
        columns[name] = [0.0, 1.0, 2.0, 3.0]
    record = DisturbanceRecord(
        metadata=RecordingMetadata(
            station_name="Station", recorder_name="Recorder", source_file=f"{source_id}.cfg",
            provider_type="COMTRADE", nominal_frequency=50.0,
        ),
        waveform_data=pd.DataFrame(columns),
        analog_channels=[], digital_channels=[],
        sampling_info=SamplingInformation(sampling_rates=[4.0], samples_per_rate=[4]),
        timing_info=TimingInformation(start_time=now, trigger_time=now),
    )
    metadata = SourceMetadata(
        source_id=source_id, workspace_id=workspace_id, provider_type="COMTRADE",
        original_filenames=(f"{source_id}.cfg",), created_at=now,
        station_name="Station", recorder_name="Recorder", nominal_frequency=50.0,
        timing_reference="absolute", start_time=now, trigger_time=now,
        sample_count=4, duration_seconds=0.75, elapsed_start_seconds=0.0, elapsed_end_seconds=0.75,
        sampling_rates=(4.0,), samples_per_rate=(4,), analog_channels=analog_channels, digital_channels=[],
    )
    return ActiveSource(metadata=metadata, record=record)


VA = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
VB = ChannelRef(kind="source", source_id="src-1", channel_name="VB")
IA = ChannelRef(kind="source", source_id="src-1", channel_name="IA")


class TestSourceConfigStorage:
    def test_upsert_and_get(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-a"))
        assert registry.get("ws-1", "src-a") is not None
        assert registry.get("ws-1", "unknown") is None

    def test_list_for_workspace_is_scoped(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-a", workspace_id="ws-1"))
        registry.upsert(_profile("src-b", workspace_id="ws-2"))
        assert [p.source_id for p in registry.list_for_workspace("ws-1")] == ["src-a"]

    def test_delete_is_idempotent(self):
        registry = PerUnitRegistry()
        assert registry.delete("ws-1", "does-not-exist") is False
        registry.upsert(_profile("src-a"))
        assert registry.delete("ws-1", "src-a") is True
        assert registry.get("ws-1", "src-a") is None
        assert registry.delete("ws-1", "src-a") is False  # already gone

    def test_remove_workspace_clears_profiles_and_calc_assignments(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-a"))
        registry.set_manual_assignment_for_calculated_channel("ws-1", "calc-1", "src-a")
        registry.remove_workspace("ws-1")
        assert registry.list_for_workspace("ws-1") == []
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") is None


class TestSourceOwnershipIsolation:
    """The owner's own explicit UAT requirement: source A's configuration
    applies ONLY to source A's channels; source B stays fully
    independent; two sources sharing a filename never collide (identity
    is workspace_id + source_id, never the filename -- this registry
    never even sees a filename, only source_id, which already proves
    the point structurally)."""

    def test_source_a_config_does_not_leak_to_source_b(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-a", voltage_base_value=275.0))
        registry.upsert(_profile("src-b", voltage_base_value=132.0))

        va_ref = ChannelRef(kind="source", source_id="src-a", channel_name="VA")
        vb_ref = ChannelRef(kind="source", source_id="src-b", channel_name="VA")  # same channel NAME, different source

        assert registry.profile_for_channel("ws-1", va_ref, VOLTAGE) == "src-a"
        assert registry.profile_for_channel("ws-1", vb_ref, VOLTAGE) == "src-b"
        assert registry.get("ws-1", "src-a").voltage_base_value == 275.0
        assert registry.get("ws-1", "src-b").voltage_base_value == 132.0

    def test_workspace_isolation(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-1", workspace_id="ws-a", voltage_base_value=275.0))
        registry.upsert(_profile("src-1", workspace_id="ws-b", voltage_base_value=132.0))  # same source_id, different workspace

        ref = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
        assert registry.profile_for_channel("ws-a", ref, VOLTAGE) == "src-1"
        assert registry.get("ws-a", "src-1").voltage_base_value == 275.0
        assert registry.get("ws-b", "src-1").voltage_base_value == 132.0

    def test_deleting_one_source_config_never_affects_another(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-a"))
        registry.upsert(_profile("src-b"))
        registry.delete("ws-1", "src-a")
        assert registry.get("ws-1", "src-a") is None
        assert registry.get("ws-1", "src-b") is not None


class TestAutomaticSourceChannelResolution:
    """Section 2: no per-channel assignment step exists any more -- every
    eligible channel of a configured source resolves automatically."""

    def test_voltage_channel_of_a_configured_source_resolves_automatically(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-1"))
        assert registry.profile_for_channel("ws-1", VA, VOLTAGE) == "src-1"

    def test_current_channel_of_a_configured_source_resolves_automatically(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-1"))
        assert registry.profile_for_channel("ws-1", IA, CURRENT) == "src-1"

    def test_non_voltage_current_engineering_type_never_resolves(self):
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-1"))
        freq_ref = ChannelRef(kind="source", source_id="src-1", channel_name="F")
        assert registry.profile_for_channel("ws-1", freq_ref, "Frequency") is None

    def test_unconfigured_source_resolves_to_none(self):
        registry = PerUnitRegistry()
        assert registry.profile_for_channel("ws-1", VA, VOLTAGE) is None

    def test_no_assignment_bookkeeping_needed_ever_for_source_channels(self):
        # There is no "assign"/"unassign" call for source channels at
        # all any more -- resolution follows purely from source_id +
        # engineering_type. Updating the source's own config immediately
        # changes what every one of its channels resolves to, with zero
        # separate reconciliation step.
        registry = PerUnitRegistry()
        registry.upsert(_profile("src-1", voltage_base_value=275.0))
        assert registry.profile_for_channel("ws-1", VA, VOLTAGE) == "src-1"
        registry.upsert(_profile("src-1", voltage_base_value=132.0))
        assert registry.profile_for_channel("ws-1", VA, VOLTAGE) == "src-1"  # still resolves; base value just changed
        assert registry.get("ws-1", "src-1").voltage_base_value == 132.0


class TestCalculatedChannelAssignment:
    def test_untouched_calculated_channel_has_no_record(self):
        registry = PerUnitRegistry()
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") is None
        assert registry.assignment_mode_for_calculated_channel("ws-1", "calc-1") is None

    def test_set_auto_assignment(self):
        registry = PerUnitRegistry()
        registry.set_auto_assignment_for_calculated_channel("ws-1", "calc-1", "src-a")
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") == "src-a"
        assert registry.assignment_mode_for_calculated_channel("ws-1", "calc-1") == "auto"

    def test_set_manual_assignment(self):
        registry = PerUnitRegistry()
        registry.set_manual_assignment_for_calculated_channel("ws-1", "calc-1", "src-a")
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") == "src-a"
        assert registry.assignment_mode_for_calculated_channel("ws-1", "calc-1") == "manual"

    def test_manual_unassignment_reaches_manual_plus_none(self):
        registry = PerUnitRegistry()
        registry.set_manual_assignment_for_calculated_channel("ws-1", "calc-1", "src-a")
        registry.set_manual_assignment_for_calculated_channel("ws-1", "calc-1", None)
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") is None
        assert registry.assignment_mode_for_calculated_channel("ws-1", "calc-1") == "manual"

    def test_remove_calculated_channel_deletes_the_record_entirely(self):
        registry = PerUnitRegistry()
        registry.set_manual_assignment_for_calculated_channel("ws-1", "calc-1", "src-a")
        registry.remove_calculated_channel("ws-1", "calc-1")
        assert registry.profile_for_calculated_channel("ws-1", "calc-1") is None
        assert registry.assignment_mode_for_calculated_channel("ws-1", "calc-1") is None  # no record, not manual+None


class TestInheritanceRecomputeCascade:
    def test_calculated_channel_inheritance_and_manual_override_lifecycle(self):
        """Decision 6/7 (unchanged by the source-bound redesign, per the
        owner's own explicit "do not redesign calculated-channel PU
        behaviour" instruction): auto-inheritance at creation, manual
        override always wins over a later recompute trigger, explicit
        unassignment permanently exempts a channel from re-inheriting,
        and a calculated channel's own MANUAL pointer survives a
        configuration's deletion (only its resolution, via
        `registry.get()`, goes stale -- `resolve_per_unit()` then
        reports `base_required`; the manual pointer itself is only ever
        cleared by an explicit user action, never by the pointed-at
        configuration's own deletion).

        Note: unlike the original profile-based design, a SOURCE channel
        can never "move" to a different configuration (its own
        `source_id` is fixed) -- the scenario below therefore exercises
        the actually-still-relevant part of decision 7: a CALCULATED
        channel's own inherited-vs-manual assignment lifecycle.
        """
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source("src-1", "ws-1", [("VA", VOLTAGE)]))
        pu_registry.upsert(_profile("src-1"))
        pu_registry.upsert(_profile("src-2"))
        calc_registry.add(_calc("rms-va", OP_RMS, [VA]))

        def recompute(changed_ids):
            recompute_inherited_per_unit_assignments(
                "ws-1", changed_ids, per_unit_registry=pu_registry, calc_registry=calc_registry, source_registry=source_registry
            )

        # RMS(VA) auto-inherits VA's own source's configuration at
        # "creation time" (simulated directly, matching what
        # create_calculated_channel() does).
        assert pu_registry.profile_for_channel("ws-1", VA, VOLTAGE) == "src-1"
        pu_registry.set_auto_assignment_for_calculated_channel("ws-1", "rms-va", "src-1")
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-va") == "src-1"

        # User manually assigns RMS(VA) to a DIFFERENT configuration
        # ("src-2") -- an explicit override.
        pu_registry.set_manual_assignment_for_calculated_channel("ws-1", "rms-va", "src-2")
        assert pu_registry.assignment_mode_for_calculated_channel("ws-1", "rms-va") == "manual"

        # A recompute trigger (e.g. src-1's own config just changed)
        # must never touch RMS(VA) -- manual is never auto-changed.
        recompute(["src-1"])
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-va") == "src-2"

        # User explicitly unassigns RMS(VA) -> manual + None.
        pu_registry.set_manual_assignment_for_calculated_channel("ws-1", "rms-va", None)
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-va") is None
        assert pu_registry.assignment_mode_for_calculated_channel("ws-1", "rms-va") == "manual"

        # A further recompute trigger must still leave it at manual+None
        # -- it never silently re-inherits.
        recompute(["src-1"])
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-va") is None
        assert pu_registry.assignment_mode_for_calculated_channel("ws-1", "rms-va") == "manual"

        # Re-point RMS(VA) manually at "src-2" again, then delete
        # src-2's own configuration -- the manual POINTER survives
        # (still "src-2"), but that configuration no longer exists, so
        # resolve_per_unit() (domain layer) would report base_required.
        pu_registry.set_manual_assignment_for_calculated_channel("ws-1", "rms-va", "src-2")
        assert pu_registry.delete("ws-1", "src-2") is True
        recompute(["src-2"])
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-va") == "src-2"
        assert pu_registry.get("ws-1", "src-2") is None

    def test_addition_only_inherits_when_both_inputs_share_a_source_config(self):
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source("src-1", "ws-1", [("VA", VOLTAGE), ("VB", VOLTAGE)]))
        pu_registry.upsert(_profile("src-1"))
        sum_ref_inputs = [VA, VB]
        calc_registry.add(_calc("sum-1", OP_ADDITION, sum_ref_inputs))
        sum_id = "sum-1"

        # Both VA and VB resolve to src-1's own config -> Sum inherits it.
        input_ids = [pu_registry.profile_for_channel("ws-1", ref, VOLTAGE) for ref in sum_ref_inputs]
        assert input_ids == ["src-1", "src-1"]
        pu_registry.set_auto_assignment_for_calculated_channel("ws-1", sum_id, "src-1")
        assert pu_registry.profile_for_calculated_channel("ws-1", sum_id) == "src-1"

        # Simulate VB now belonging to a DIFFERENT source (a fresh
        # ChannelRef with a different source_id) -- Sum must fall back
        # to None, never an arbitrary pick.
        vb_other_source = ChannelRef(kind="source", source_id="src-2", channel_name="VB")
        pu_registry.upsert(_profile("src-2"))
        other_calc = _calc("sum-2", OP_ADDITION, [VA, vb_other_source])
        calc_registry.add(other_calc)
        recompute_inherited_per_unit_assignments(
            "ws-1", ["src-1", "src-2"], per_unit_registry=pu_registry, calc_registry=calc_registry, source_registry=source_registry
        )
        assert pu_registry.profile_for_calculated_channel("ws-1", "sum-2") is None

    def test_cascade_propagates_through_calculated_from_calculated_chain(self):
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source("src-1", "ws-1", [("VA", VOLTAGE)]))
        pu_registry.upsert(_profile("src-1"))
        rms_ref = ChannelRef(kind="calculated", calculated_channel_id="rms-va")
        calc_registry.add(_calc("rms-va", OP_RMS, [VA]))
        rms_of_rms_ref = ChannelRef(kind="calculated", calculated_channel_id="rms-of-rms")
        calc_registry.add(_calc("rms-of-rms", OP_RMS, [rms_ref]))

        pu_registry.set_auto_assignment_for_calculated_channel("ws-1", "rms-va", "src-1")
        pu_registry.set_auto_assignment_for_calculated_channel("ws-1", "rms-of-rms", "src-1")

        pu_registry.upsert(_profile("src-2"))
        # Reassign rms-va's OWN input to a different source's config by
        # updating the underlying calc definition's input -- simplest
        # correct simulation: directly seed the cascade as if src-1's
        # config changed identity (delete+recreate under a new id is not
        # representable without a real source rename, so this test
        # instead proves propagation depth via a manual override break):
        pu_registry.set_manual_assignment_for_calculated_channel("ws-1", "rms-va", "src-2")
        recompute_inherited_per_unit_assignments(
            "ws-1", ["rms-va"], per_unit_registry=pu_registry, calc_registry=calc_registry, source_registry=source_registry
        )
        assert pu_registry.profile_for_calculated_channel("ws-1", "rms-of-rms") == "src-2"
