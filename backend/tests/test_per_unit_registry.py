"""Tests for app.services.per_unit_registry (Phase 5C, DEC-049):
PerUnitRegistry's profile storage, the channel-assignment reverse index
(decision 7's two-axis `mode`/`profile_id` model), decision 4's
conflict/reassignment rule, and the inheritance-recompute cascade.

A recurring theme, per the owner's own explicit requirement: after every
mutation path, `list_for_workspace()` (what `GET .../profiles` returns)
and `profile_for_channel()` must always agree about who owns what -- see
TestAssignedChannelsInvariant below, which checks this after every single
step of the owner's own locked A->G provenance sequence.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.domain.calculated_channel import OP_ADDITION, OP_RMS, CalculatedChannel, ChannelRef
from app.domain.per_unit import PerUnitBaseProfile, VOLTAGE_BASIS_LINE_TO_LINE
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.errors import ChannelAlreadyAssignedError, PerUnitProfileNotFoundError
from app.services.per_unit_registry import PerUnitRegistry, recompute_inherited_per_unit_assignments


def _profile(profile_id: str, workspace_id: str = "ws-1", name: str | None = None) -> PerUnitBaseProfile:
    return PerUnitBaseProfile(
        id=profile_id,
        workspace_id=workspace_id,
        name=name or profile_id,
        voltage_base_value=275.0,
        voltage_base_unit="kV",
        voltage_basis=VOLTAGE_BASIS_LINE_TO_LINE,
        apparent_power_base_value=None,
        apparent_power_base_unit=None,
        current_base_mode="none",
        direct_current_base_value=None,
        direct_current_base_unit=None,
        assigned_channels=[],
        created_at=datetime.now(timezone.utc),
    )


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


VA = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
VB = ChannelRef(kind="source", source_id="src-1", channel_name="VB")


def _assert_no_divergence(registry: PerUnitRegistry, workspace_id: str, channel_ref: ChannelRef) -> None:
    """The invariant the owner's amendment requires: whichever profile
    `profile_for_channel()` reports for a channel, that SAME profile's
    own `assigned_channels` (as `list_for_workspace()`/GET would return
    it) must list that channel -- and no OTHER profile in the workspace
    may also list it."""
    resolved_profile_id = registry.profile_for_channel(workspace_id, channel_ref)
    for profile in registry.list_for_workspace(workspace_id):
        is_listed = channel_ref in profile.assigned_channels
        if profile.id == resolved_profile_id:
            assert is_listed, f"{channel_ref} should be listed on {profile.id} but is not"
        else:
            assert not is_listed, f"{channel_ref} should NOT be listed on {profile.id} but is"


class TestProfileStorage:
    def test_add_and_get(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        assert registry.get("ws-1", "pu-a") is not None
        assert registry.get("ws-1", "unknown") is None

    def test_list_for_workspace_is_scoped(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a", workspace_id="ws-1"))
        registry.add(_profile("pu-b", workspace_id="ws-2"))
        assert [p.id for p in registry.list_for_workspace("ws-1")] == ["pu-a"]

    def test_remove_workspace_clears_profiles_and_assignments(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")
        registry.remove_workspace("ws-1")
        assert registry.list_for_workspace("ws-1") == []
        assert registry.profile_for_channel("ws-1", VA) is None


class TestManualAssignment:
    def test_set_manual_assignment_updates_both_sides(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")
        assert registry.profile_for_channel("ws-1", VA) == "pu-a"
        assert registry.assignment_mode_for_channel("ws-1", VA) == "manual"
        _assert_no_divergence(registry, "ws-1", VA)

    def test_reassigning_to_a_different_profile_moves_it_off_the_old_one(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.add(_profile("pu-b"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")
        registry.set_manual_assignment("ws-1", VA, "pu-b")
        assert registry.profile_for_channel("ws-1", VA) == "pu-b"
        _assert_no_divergence(registry, "ws-1", VA)

    def test_explicit_unassignment_reaches_manual_plus_none(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")
        registry.set_manual_assignment("ws-1", VA, None)
        assert registry.profile_for_channel("ws-1", VA) is None
        assert registry.assignment_mode_for_channel("ws-1", VA) == "manual"
        _assert_no_divergence(registry, "ws-1", VA)

    def test_untouched_channel_has_no_record(self):
        registry = PerUnitRegistry()
        assert registry.profile_for_channel("ws-1", VA) is None
        assert registry.assignment_mode_for_channel("ws-1", VA) is None


class TestAssignChannels:
    def test_rejects_conflicting_channel_without_flag_and_mutates_nothing(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a", name="Profile A"))
        registry.add(_profile("pu-b", name="Profile B"))
        registry.assign_channels("ws-1", "pu-a", [VA])

        with pytest.raises(ChannelAlreadyAssignedError) as excinfo:
            registry.assign_channels("ws-1", "pu-b", [VA])
        assert excinfo.value.conflicts[0]["profile_id"] == "pu-a"
        assert excinfo.value.conflicts[0]["profile_name"] == "Profile A"
        # Nothing changed.
        assert registry.profile_for_channel("ws-1", VA) == "pu-a"

    def test_accepts_conflicting_channel_with_flag_and_moves_it(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.add(_profile("pu-b"))
        registry.assign_channels("ws-1", "pu-a", [VA])

        changed = registry.assign_channels("ws-1", "pu-b", [VA], reassign_conflicting=True)
        assert VA in changed
        assert registry.profile_for_channel("ws-1", VA) == "pu-b"
        _assert_no_divergence(registry, "ws-1", VA)

    def test_omitted_channel_is_unassigned(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.assign_channels("ws-1", "pu-a", [VA, VB])
        registry.assign_channels("ws-1", "pu-a", [VA])  # VB omitted this time
        assert registry.profile_for_channel("ws-1", VB) is None
        assert registry.assignment_mode_for_channel("ws-1", VB) == "manual"
        _assert_no_divergence(registry, "ws-1", VB)

    def test_unknown_profile_raises_not_found(self):
        registry = PerUnitRegistry()
        with pytest.raises(PerUnitProfileNotFoundError):
            registry.assign_channels("ws-1", "does-not-exist", [VA])


class TestDeleteProfile:
    def test_preserves_manual_mode_as_manual_plus_none(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")

        affected = registry.delete_profile("ws-1", "pu-a")
        assert VA in affected
        assert registry.profile_for_channel("ws-1", VA) is None
        assert registry.assignment_mode_for_channel("ws-1", VA) == "manual"

    def test_preserves_auto_mode_as_auto_plus_none(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_auto_assignment("ws-1", VA, "pu-a")

        registry.delete_profile("ws-1", "pu-a")
        assert registry.profile_for_channel("ws-1", VA) is None
        assert registry.assignment_mode_for_channel("ws-1", VA) == "auto"

    def test_unknown_profile_raises_not_found(self):
        registry = PerUnitRegistry()
        with pytest.raises(PerUnitProfileNotFoundError):
            registry.delete_profile("ws-1", "does-not-exist")


class TestRemoveChannelEverywhere:
    def test_deletes_record_entirely_and_delists(self):
        registry = PerUnitRegistry()
        registry.add(_profile("pu-a"))
        registry.set_manual_assignment("ws-1", VA, "pu-a")

        registry.remove_channel_everywhere("ws-1", VA)
        assert registry.profile_for_channel("ws-1", VA) is None
        assert registry.assignment_mode_for_channel("ws-1", VA) is None  # no record at all, not manual+None
        profile = registry.get("ws-1", "pu-a")
        assert VA not in profile.assigned_channels


class TestInheritanceRecomputeCascade:
    def test_owner_locked_provenance_sequence_a_through_g(self):
        """The owner's own exact A->G scenario (plan Verification
        section), re-checking the assigned_channels/profile_for_channel
        invariant after every single step."""
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        pu_registry.add(_profile("A"))
        pu_registry.add(_profile("B"))
        pu_registry.add(_profile("C"))

        rms_ref = ChannelRef(kind="calculated", calculated_channel_id="rms-va")
        calc_registry.add(_calc("rms-va", OP_RMS, [VA]))

        # A. VA -> profile A; RMS(VA) auto-inherits A at "creation time"
        # (simulated directly via set_auto_assignment, matching what
        # create_calculated_channel() does).
        pu_registry.set_manual_assignment("ws-1", VA, "A")
        pu_registry.set_auto_assignment("ws-1", rms_ref, "A")
        assert pu_registry.profile_for_channel("ws-1", rms_ref) == "A"
        _assert_no_divergence(pu_registry, "ws-1", VA)
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # B. Move VA to profile B -> RMS(VA) automatically follows to B.
        changed = pu_registry.set_manual_assignment("ws-1", VA, "B")
        assert changed
        recompute_inherited_per_unit_assignments(
            "ws-1", [VA], per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", rms_ref) == "B"
        assert pu_registry.assignment_mode_for_channel("ws-1", rms_ref) == "auto"
        _assert_no_divergence(pu_registry, "ws-1", VA)
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # C. User manually assigns RMS(VA) to profile C.
        pu_registry.set_manual_assignment("ws-1", rms_ref, "C")
        assert pu_registry.profile_for_channel("ws-1", rms_ref) == "C"
        assert pu_registry.assignment_mode_for_channel("ws-1", rms_ref) == "manual"
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # D. Move VA again -> RMS(VA) stays on C (manual never auto-changed).
        pu_registry.set_manual_assignment("ws-1", VA, "A")
        recompute_inherited_per_unit_assignments(
            "ws-1", [VA], per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", rms_ref) == "C"
        _assert_no_divergence(pu_registry, "ws-1", VA)
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # E. User explicitly unassigns RMS(VA) -> manual + None.
        pu_registry.set_manual_assignment("ws-1", rms_ref, None)
        assert pu_registry.profile_for_channel("ws-1", rms_ref) is None
        assert pu_registry.assignment_mode_for_channel("ws-1", rms_ref) == "manual"
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # F. Move VA again -> RMS(VA) stays base_required (does not auto-inherit).
        pu_registry.set_manual_assignment("ws-1", VA, "B")
        recompute_inherited_per_unit_assignments(
            "ws-1", [VA], per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", rms_ref) is None
        assert pu_registry.assignment_mode_for_channel("ws-1", rms_ref) == "manual"
        _assert_no_divergence(pu_registry, "ws-1", VA)
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

        # G. Manually re-point RMS(VA) at C, then delete C -> RMS(VA)
        # becomes manual + None and does not unexpectedly re-inherit.
        pu_registry.set_manual_assignment("ws-1", rms_ref, "C")
        affected = pu_registry.delete_profile("ws-1", "C")
        assert rms_ref in affected
        recompute_inherited_per_unit_assignments(
            "ws-1", affected, per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", rms_ref) is None
        assert pu_registry.assignment_mode_for_channel("ws-1", rms_ref) == "manual"
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)

    def test_addition_only_inherits_when_both_inputs_share_a_profile(self):
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        pu_registry.add(_profile("A"))
        pu_registry.add(_profile("B"))
        sum_ref = ChannelRef(kind="calculated", calculated_channel_id="sum-1")
        calc_registry.add(_calc("sum-1", OP_ADDITION, [VA, VB]))

        pu_registry.set_manual_assignment("ws-1", VA, "A")
        pu_registry.set_manual_assignment("ws-1", VB, "A")
        pu_registry.set_auto_assignment("ws-1", sum_ref, "A")
        assert pu_registry.profile_for_channel("ws-1", sum_ref) == "A"

        # VB moves to a different profile -> Sum must fall back to None,
        # never an arbitrary pick.
        pu_registry.set_manual_assignment("ws-1", VB, "B")
        recompute_inherited_per_unit_assignments(
            "ws-1", [VB], per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", sum_ref) is None
        _assert_no_divergence(pu_registry, "ws-1", sum_ref)

    def test_cascade_propagates_through_calculated_from_calculated_chain(self):
        pu_registry = PerUnitRegistry()
        calc_registry = CalculatedChannelRegistry()
        pu_registry.add(_profile("A"))
        pu_registry.add(_profile("B"))
        rms_ref = ChannelRef(kind="calculated", calculated_channel_id="rms-va")
        calc_registry.add(_calc("rms-va", OP_RMS, [VA]))
        rms_of_rms_ref = ChannelRef(kind="calculated", calculated_channel_id="rms-of-rms")
        calc_registry.add(_calc("rms-of-rms", OP_RMS, [rms_ref]))

        pu_registry.set_manual_assignment("ws-1", VA, "A")
        pu_registry.set_auto_assignment("ws-1", rms_ref, "A")
        pu_registry.set_auto_assignment("ws-1", rms_of_rms_ref, "A")

        pu_registry.set_manual_assignment("ws-1", VA, "B")
        recompute_inherited_per_unit_assignments(
            "ws-1", [VA], per_unit_registry=pu_registry, calc_registry=calc_registry
        )
        assert pu_registry.profile_for_channel("ws-1", rms_ref) == "B"
        assert pu_registry.profile_for_channel("ws-1", rms_of_rms_ref) == "B"
        _assert_no_divergence(pu_registry, "ws-1", rms_ref)
        _assert_no_divergence(pu_registry, "ws-1", rms_of_rms_ref)
