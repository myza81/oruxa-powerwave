"""Tests for app.services.measurement_group_registry (Slice 1 of
DEC-050): identity, storage CRUD, the channel-membership reverse index,
cross-group duplicate-membership rejection, create-only add() safety,
and workspace/source lifecycle -- registry-level only, no
WorkspaceRegistry/engineering-type validation involved (see
test_measurement_group_service.py for that layer, and
test_measurement_group_domain.py for the pure functions this registry
itself does not re-implement).
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_MANUAL, MeasurementGroup
from app.services.errors import (
    ChannelAlreadyGroupedError,
    DuplicateChannelReferenceError,
    MeasurementGroupAlreadyExistsError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry

VA = ChannelRef(kind="source", source_id="src-1", channel_name="VA")
VB = ChannelRef(kind="source", source_id="src-1", channel_name="VB")
IA = ChannelRef(kind="source", source_id="src-1", channel_name="IA")
OTHER_SRC_VA = ChannelRef(kind="source", source_id="src-2", channel_name="VA")


def _group(group_id: str, source_id: str = "src-1", workspace_id: str = "ws-1", kind: str = KIND_VOLTAGE, **overrides) -> MeasurementGroup:
    defaults = dict(display_name=group_id.upper(), channel_refs=[], status=STATUS_MANUAL)
    defaults.update(overrides)
    return MeasurementGroup(id=group_id, workspace_id=workspace_id, source_id=source_id, kind=kind, **defaults)


class TestIdentity:
    def test_two_groups_get_distinct_ids_even_with_the_same_display_name(self):
        registry = MeasurementGroupRegistry()
        a = _group("mg-a", display_name="NORTH BUS VOLTAGE")
        b = _group("mg-b", display_name="NORTH BUS VOLTAGE")
        registry.add(a)
        registry.add(b)
        assert registry.get("ws-1", "mg-a").id != registry.get("ws-1", "mg-b").id
        assert registry.get("ws-1", "mg-a").display_name == registry.get("ws-1", "mg-b").display_name

    def test_same_source_id_across_two_workspaces_does_not_collide(self):
        # Mirrors PerUnitRegistry's own filename/identity isolation test
        # -- two sources sharing an id string in different workspaces
        # must resolve to fully independent groups.
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", source_id="src-1", workspace_id="ws-a", display_name="A"))
        registry.add(_group("mg-1", source_id="src-1", workspace_id="ws-b", display_name="B"))
        assert registry.get("ws-a", "mg-1").display_name == "A"
        assert registry.get("ws-b", "mg-1").display_name == "B"


class TestOwnership:
    def test_group_belongs_to_exactly_one_source(self):
        registry = MeasurementGroupRegistry()
        group = _group("mg-1", source_id="src-1")
        registry.add(group)
        assert registry.get("ws-1", "mg-1").source_id == "src-1"

    def test_list_for_source_is_scoped_to_that_source_only(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", source_id="src-1"))
        registry.add(_group("mg-2", source_id="src-2"))
        assert [g.id for g in registry.list_for_source("ws-1", "src-1")] == ["mg-1"]

    def test_workspace_isolation(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", workspace_id="ws-a"))
        registry.add(_group("mg-1", workspace_id="ws-b"))
        assert registry.get("ws-a", "mg-1") is not None
        assert registry.get("ws-b", "mg-1") is not None
        assert [g.id for g in registry.list_for_workspace("ws-a")] == ["mg-1"]
        assert [g.id for g in registry.list_for_workspace("ws-b")] == ["mg-1"]


class TestDuplicateMembership:
    def test_same_channel_cannot_belong_to_two_voltage_groups_in_same_source(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", kind=KIND_VOLTAGE, channel_refs=[VA]))
        with pytest.raises(ChannelAlreadyGroupedError):
            registry.add(_group("mg-2", kind=KIND_VOLTAGE, channel_refs=[VA]))

    def test_same_channel_cannot_belong_to_two_current_groups_in_same_source(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", kind=KIND_CURRENT, channel_refs=[IA]))
        with pytest.raises(ChannelAlreadyGroupedError):
            registry.add(_group("mg-2", kind=KIND_CURRENT, channel_refs=[IA]))

    def test_duplicate_ref_within_same_group_rejected(self):
        registry = MeasurementGroupRegistry()
        with pytest.raises(DuplicateChannelReferenceError):
            registry.add(_group("mg-1", channel_refs=[VA, VA]))

    def test_a_failed_add_leaves_no_partial_state(self):
        registry = MeasurementGroupRegistry()
        with pytest.raises(DuplicateChannelReferenceError):
            registry.add(_group("mg-1", channel_refs=[VA, VA]))
        assert registry.get("ws-1", "mg-1") is None
        assert registry.group_for_channel("ws-1", VA) is None

    def test_different_source_same_channel_name_does_not_collide(self):
        # VA on src-1 and VA on src-2 are different ChannelRefs entirely
        # (ChannelRef equality includes source_id) -- must not be treated
        # as the same channel.
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", source_id="src-1", channel_refs=[VA]))
        registry.add(_group("mg-2", source_id="src-2", channel_refs=[OTHER_SRC_VA]))
        assert registry.group_for_channel("ws-1", VA) == "mg-1"
        assert registry.group_for_channel("ws-1", OTHER_SRC_VA) == "mg-2"


class TestAddIsCreateOnly:
    """Slice 1 follow-up: add() must never behave as an implicit upsert.
    A second add() under the same (workspace_id, id) is rejected before
    any mutation -- the existing group's own membership and reverse-
    index entries must survive completely untouched, and the channels
    the REJECTED attempt tried to introduce must never be indexed."""

    def test_second_add_under_the_same_id_is_rejected(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        with pytest.raises(MeasurementGroupAlreadyExistsError):
            registry.add(_group("mg-1", channel_refs=[IA]))

    def test_original_group_membership_is_unchanged_after_rejected_add(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        with pytest.raises(MeasurementGroupAlreadyExistsError):
            registry.add(_group("mg-1", channel_refs=[IA]))
        assert registry.get("ws-1", "mg-1").channel_refs == [VA, VB]

    def test_original_reverse_index_entries_survive_a_rejected_add(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        with pytest.raises(MeasurementGroupAlreadyExistsError):
            registry.add(_group("mg-1", channel_refs=[IA]))
        assert registry.group_for_channel("ws-1", VA) == "mg-1"
        assert registry.group_for_channel("ws-1", VB) == "mg-1"

    def test_rejected_attempts_own_channels_are_never_indexed(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        with pytest.raises(MeasurementGroupAlreadyExistsError):
            registry.add(_group("mg-1", channel_refs=[IA]))
        assert registry.group_for_channel("ws-1", IA) is None

    def test_count_and_listing_unchanged_after_rejected_add(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        with pytest.raises(MeasurementGroupAlreadyExistsError):
            registry.add(_group("mg-1", channel_refs=[IA]))
        assert registry.count() == 1
        assert [g.id for g in registry.list_for_workspace("ws-1")] == ["mg-1"]

    def test_same_group_id_in_different_workspaces_remains_isolated_and_valid(self):
        # Identity is (workspace_id, id) -- the same id string in a
        # DIFFERENT workspace is not a duplicate at all.
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", workspace_id="ws-a", channel_refs=[VA]))
        registry.add(_group("mg-1", workspace_id="ws-b", channel_refs=[VB]))  # must not raise
        assert registry.get("ws-a", "mg-1").channel_refs == [VA]
        assert registry.get("ws-b", "mg-1").channel_refs == [VB]
        assert registry.group_for_channel("ws-a", VA) == "mg-1"
        assert registry.group_for_channel("ws-b", VB) == "mg-1"

    def test_replacing_an_existing_group_still_works_via_update(self):
        # The create-only restriction applies to add() only -- update()
        # remains the correct, fully-validated replace/modify path.
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        replacement = registry.get("ws-1", "mg-1")
        replacement.channel_refs = [IA]
        registry.update(replacement)
        assert registry.get("ws-1", "mg-1").channel_refs == [IA]
        assert registry.group_for_channel("ws-1", VA) is None
        assert registry.group_for_channel("ws-1", VB) is None
        assert registry.group_for_channel("ws-1", IA) == "mg-1"


class TestGroupForChannelIndex:
    def test_group_for_channel_resolves_to_the_owning_group(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        assert registry.group_for_channel("ws-1", VA) == "mg-1"
        assert registry.group_for_channel("ws-1", VB) == "mg-1"

    def test_unclaimed_channel_resolves_to_none(self):
        registry = MeasurementGroupRegistry()
        assert registry.group_for_channel("ws-1", VA) is None

    def test_index_and_group_membership_never_diverge_across_every_mutation(self):
        """Invariant strategy (task section 21/22): prove the reverse
        index and each group's own channel_refs list agree after every
        mutation path -- add, update (both grow and shrink membership),
        and remove."""

        def assert_consistent(registry: MeasurementGroupRegistry, workspace_id: str):
            for group in registry.list_for_workspace(workspace_id):
                for ref in group.channel_refs:
                    assert registry.group_for_channel(workspace_id, ref) == group.id

        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA]))
        assert_consistent(registry, "ws-1")

        # Grow membership via update.
        grown = registry.get("ws-1", "mg-1")
        grown.channel_refs = [VA, VB]
        registry.update(grown)
        assert registry.group_for_channel("ws-1", VB) == "mg-1"
        assert_consistent(registry, "ws-1")

        # Shrink membership via update -- VA must be released, not left
        # dangling in the index.
        shrunk = registry.get("ws-1", "mg-1")
        shrunk.channel_refs = [VB]
        registry.update(shrunk)
        assert registry.group_for_channel("ws-1", VA) is None
        assert registry.group_for_channel("ws-1", VB) == "mg-1"
        assert_consistent(registry, "ws-1")

        # Remove the group entirely -- its last channel must be released.
        registry.remove("ws-1", "mg-1")
        assert registry.group_for_channel("ws-1", VB) is None

    def test_update_does_not_conflict_with_its_own_prior_membership(self):
        # A group keeping (or dropping) its OWN existing channel must
        # never be treated as "already grouped elsewhere".
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA]))
        same = registry.get("ws-1", "mg-1")
        same.channel_refs = [VA]  # unchanged membership
        registry.update(same)  # must not raise
        assert registry.group_for_channel("ws-1", VA) == "mg-1"

    def test_update_still_rejects_a_channel_owned_by_a_different_group(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA]))
        registry.add(_group("mg-2", channel_refs=[VB]))
        stealing = registry.get("ws-1", "mg-2")
        stealing.channel_refs = [VB, VA]
        with pytest.raises(ChannelAlreadyGroupedError):
            registry.update(stealing)
        # mg-1's own membership must be untouched by the failed update.
        assert registry.group_for_channel("ws-1", VA) == "mg-1"


class TestBasicCrud:
    def test_create_list_retrieve(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1"))
        assert registry.get("ws-1", "mg-1") is not None
        assert [g.id for g in registry.list_for_workspace("ws-1")] == ["mg-1"]

    def test_rename_display_metadata_via_update(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", display_name="OLD NAME"))
        renamed = registry.get("ws-1", "mg-1")
        renamed.display_name = "NEW NAME"
        registry.update(renamed)
        assert registry.get("ws-1", "mg-1").display_name == "NEW NAME"

    def test_delete(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1"))
        assert registry.remove("ws-1", "mg-1") is True
        assert registry.get("ws-1", "mg-1") is None

    def test_delete_is_idempotent(self):
        registry = MeasurementGroupRegistry()
        assert registry.remove("ws-1", "does-not-exist") is False

    def test_update_of_unknown_group_raises_key_error(self):
        registry = MeasurementGroupRegistry()
        with pytest.raises(KeyError):
            registry.update(_group("mg-ghost"))

    def test_count(self):
        registry = MeasurementGroupRegistry()
        assert registry.count() == 0
        registry.add(_group("mg-1"))
        registry.add(_group("mg-2", workspace_id="ws-2"))
        assert registry.count() == 2


class TestLifecycle:
    def test_deleting_group_clears_its_membership_from_the_index(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", channel_refs=[VA, VB]))
        registry.remove("ws-1", "mg-1")
        assert registry.group_for_channel("ws-1", VA) is None
        assert registry.group_for_channel("ws-1", VB) is None

    def test_remove_workspace_clears_every_group_and_index_entry(self):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-1", workspace_id="ws-1", channel_refs=[VA]))
        registry.add(_group("mg-2", workspace_id="ws-1", source_id="src-2", channel_refs=[OTHER_SRC_VA]))
        registry.add(_group("mg-3", workspace_id="ws-2"))
        removed = registry.remove_workspace("ws-1")
        assert removed == 2
        assert registry.list_for_workspace("ws-1") == []
        assert registry.group_for_channel("ws-1", VA) is None
        assert registry.group_for_channel("ws-1", OTHER_SRC_VA) is None
        # ws-2 is untouched.
        assert [g.id for g in registry.list_for_workspace("ws-2")] == ["mg-3"]

    def test_remove_workspace_is_idempotent(self):
        registry = MeasurementGroupRegistry()
        assert registry.remove_workspace("ws-empty") == 0
