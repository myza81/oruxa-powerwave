"""Candidate failures and overlapping writes at the two registry boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from threading import Event, current_thread

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.measurement_group import MeasurementGroup
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.services.errors import InvalidVoltageReferenceOverrideError
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import (
    set_manual_voltage_reference,
    set_voltage_base,
    update_voltage_configuration,
)


def _registries(initial=True):
    groups, configs = MeasurementGroupRegistry(), VoltageGroupConfigRegistry()
    groups.add(MeasurementGroup(
        id="mg-v", workspace_id="ws", source_id="source", kind="voltage",
        display_name="Original", status="needs_review",
        channel_refs=[ChannelRef(kind="source", source_id="source", channel_name="VA")],
    ))
    if initial:
        configs.upsert(VoltageBaseConfiguration("mg-v", "ws", 275))
    return groups, configs


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("reference", [None, "invalid"])
def test_invalid_service_candidate_never_publishes_any_field(initial, reference):
    groups, configs = _registries(initial)
    before = [asdict(c) for c in configs.list_for_workspace("ws")]
    with pytest.raises(InvalidVoltageReferenceOverrideError):
        update_voltage_configuration(
            workspace_id="ws", measurement_group_id="mg-v", nominal_voltage_ll_kv=132,
            reference_mode="manual", reference_override=reference,
            group_registry=groups, voltage_config_registry=configs,
        )
    assert [asdict(c) for c in configs.list_for_workspace("ws")] == before


@pytest.mark.parametrize("initial", [False, True])
def test_voltage_publication_copy_failure_preserves_original_or_absence(monkeypatch, initial):
    from app.services import voltage_group_config_registry as module

    groups, configs = _registries(initial)
    before = configs.get("ws", "mg-v")
    original_copy = module._copy_config

    def fail_new_candidate(config):
        if config.nominal_voltage_ll_kv == 132:
            raise RuntimeError("candidate copy failed")
        return original_copy(config)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_copy_config", fail_new_candidate)
        with pytest.raises(RuntimeError, match="candidate copy failed"):
            update_voltage_configuration(
                workspace_id="ws", measurement_group_id="mg-v", nominal_voltage_ll_kv=132,
                reference_mode="manual", reference_override="line_to_line",
                group_registry=groups, voltage_config_registry=configs,
            )
    assert configs.get("ws", "mg-v") == before


def test_index_staging_failure_preserves_group_and_reverse_index():
    groups, _ = _registries()
    before = groups.get("ws", "mg-v")
    before_index = dict(groups._channel_index)

    class FailingIndex(dict):
        def copy(self):
            raise RuntimeError("index allocation failed")

    groups._channel_index = FailingIndex(groups._channel_index)
    candidate = groups.get("ws", "mg-v")
    candidate.channel_refs = []
    candidate.status = "confirmed"
    with pytest.raises(RuntimeError, match="index allocation failed"):
        groups.update(candidate)
    assert groups.get("ws", "mg-v") == before
    assert dict(groups._channel_index) == before_index


def test_overlapping_group_edits_preserve_latest_omitted_fields(monkeypatch):
    from app.services.measurement_group_service import update_group_metadata

    groups, _ = _registries()
    captured, release = Event(), Event()
    original_get = groups.get

    def held_get(workspace, group_id):
        snapshot = original_get(workspace, group_id)
        if current_thread().name.startswith("held-edit"):
            captured.set()
            assert release.wait(10), "test did not release the earlier read"
        return snapshot

    monkeypatch.setattr(groups, "get", held_get)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="held-edit") as pool:
        earlier = pool.submit(update_group_metadata, workspace_id="ws", measurement_group_id="mg-v",
                              registry=groups, display_name="Renamed")
        try:
            assert captured.wait(10)
            update_group_metadata(workspace_id="ws", measurement_group_id="mg-v", registry=groups, status="confirmed")
        finally:
            release.set()
        earlier.result(timeout=10)
    saved = original_get("ws", "mg-v")
    assert (saved.display_name, saved.status) == ("Renamed", "confirmed")


def test_overlapping_voltage_setters_preserve_the_other_accepted_field(monkeypatch):
    groups, configs = _registries()
    captured, release = Event(), Event()
    original_update = configs.update_fields

    def held_update(*args, **kwargs):
        if kwargs.get("nominal_voltage_ll_kv") == 132:
            captured.set()
            assert release.wait(10)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(configs, "update_fields", held_update)
    common = dict(workspace_id="ws", measurement_group_id="mg-v",
                  group_registry=groups, voltage_config_registry=configs)
    with ThreadPoolExecutor(max_workers=1) as pool:
        earlier = pool.submit(set_voltage_base, nominal_voltage_ll_kv=132, **common)
        try:
            assert captured.wait(10)
            set_manual_voltage_reference(reference="line_to_line", **common)
        finally:
            release.set()
        earlier.result(timeout=10)
    saved = configs.get("ws", "mg-v")
    assert (saved.nominal_voltage_ll_kv, saved.reference_mode, saved.reference_override) == (132, "manual", "line_to_line")
