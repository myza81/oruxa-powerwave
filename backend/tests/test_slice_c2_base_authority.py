"""Slice C-2: base_authority exposed in measurement group wire schema.

Verifies that VoltageGroupConfigView (and the Pydantic schema it maps to)
carries the authoritative base_authority value from the domain model, so
the frontend can distinguish needs_review from unavailable without inference.

Covers:
  1. auto_resolved group → base_authority "auto_resolved" in view
  2. manual group → base_authority "manual" in view
  3. needs_review group → base_authority "needs_review"; pu_reason "base_invalidated"
  4. unavailable group → base_authority "unavailable"; pu_reason "base_invalidated"
  5. manual + conflict → base_authority "manual"; manual_conflict_detected True; PU blocked
  6. current group → base_authority propagated through CurrentGroupConfigView
  7. No-config voltage group → base_authority defaults to "legacy_manual"
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_LEGACY,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
    BASE_AUTHORITY_UNAVAILABLE,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    CurrentBaseConfiguration,
    METHOD_NONE,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL,
    MeasurementGroup,
)
from app.domain.voltage_group_config import VoltageBaseConfiguration
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.measurement_group_view_service import build_group_view
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS = "ws-c2-auth"
SRC = "src-c2-auth"


def _vgroup(group_id: str, status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id,
        workspace_id=WS,
        source_id=SRC,
        kind=KIND_VOLTAGE,
        display_name=f"VG-{group_id}",
        channel_refs=[ChannelRef(kind="source", source_id=SRC, channel_name="VA")],
        status=status,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _cgroup(group_id: str) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id,
        workspace_id=WS,
        source_id=SRC,
        kind=KIND_CURRENT,
        display_name=f"CG-{group_id}",
        channel_refs=[ChannelRef(kind="source", source_id=SRC, channel_name="IA")],
        status=STATUS_CONFIRMED,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _build(group: MeasurementGroup, voltage_cfg=None, current_cfg=None):
    group_registry = MeasurementGroupRegistry()
    group_registry.add(group)
    v_registry = VoltageGroupConfigRegistry()
    if voltage_cfg is not None:
        v_registry.upsert(voltage_cfg)
    c_registry = CurrentGroupConfigRegistry()
    if current_cfg is not None:
        c_registry.upsert(current_cfg)
    return build_group_view(
        group,
        group_registry=group_registry,
        voltage_config_registry=v_registry,
        current_config_registry=c_registry,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVoltageBaseAuthorityInView:
    def test_auto_resolved_propagates(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g1",
            workspace_id=WS,
            nominal_voltage_ll_kv=132.0,
            base_authority=BASE_AUTHORITY_AUTO,
        )
        view = _build(_vgroup("g1"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "auto_resolved"
        assert view.pu_status == "configured"

    def test_manual_propagates(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g2",
            workspace_id=WS,
            nominal_voltage_ll_kv=275.0,
            base_authority=BASE_AUTHORITY_MANUAL,
        )
        view = _build(_vgroup("g2"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "manual"
        assert view.pu_status == "configured"
        assert view.pu_reason is None

    def test_needs_review_propagates_and_blocks_pu(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g3",
            workspace_id=WS,
            nominal_voltage_ll_kv=None,
            base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
        )
        view = _build(_vgroup("g3"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "needs_review"
        assert view.pu_status == "base_required"
        assert view.pu_reason == "base_invalidated"

    def test_unavailable_propagates_and_blocks_pu(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g4",
            workspace_id=WS,
            nominal_voltage_ll_kv=132.0,  # has a kV value but authority says unavailable
            base_authority=BASE_AUTHORITY_UNAVAILABLE,
        )
        view = _build(_vgroup("g4"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "unavailable"
        assert view.pu_status == "base_required"
        assert view.pu_reason == "base_invalidated"

    def test_manual_conflict_propagates(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g5",
            workspace_id=WS,
            nominal_voltage_ll_kv=66.0,
            base_authority=BASE_AUTHORITY_MANUAL,
            manual_conflict_detected=True,
            manual_conflict_detail="detected_132.0kv_conflicts_with_manual_66.0kv",
        )
        view = _build(_vgroup("g5"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "manual"
        assert view.voltage_config.manual_conflict_detected is True
        assert view.voltage_config.manual_conflict_detail is not None
        assert view.pu_status == "base_required"
        assert view.pu_reason == "manual_conflict_detected"

    def test_no_config_defaults_to_legacy_manual(self):
        view = _build(_vgroup("g6"), voltage_cfg=None)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "legacy_manual"

    def test_legacy_manual_propagates(self):
        cfg = VoltageBaseConfiguration(
            measurement_group_id="g7",
            workspace_id=WS,
            nominal_voltage_ll_kv=132.0,
            base_authority=BASE_AUTHORITY_LEGACY,
        )
        view = _build(_vgroup("g7"), voltage_cfg=cfg)
        assert view.voltage_config is not None
        assert view.voltage_config.base_authority == "legacy_manual"
        assert view.pu_status == "configured"


class TestCurrentBaseAuthorityInView:
    def test_current_no_config_defaults_to_legacy_manual(self):
        view = _build(_cgroup("cg1"), current_cfg=None)
        assert view.current_config is not None
        assert view.current_config.base_authority == "legacy_manual"

    def test_current_manual_propagates(self):
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg2",
            workspace_id=WS,
            method="manual",
            manual_ibase_ka=0.5,
            base_authority=BASE_AUTHORITY_MANUAL,
        )
        view = _build(_cgroup("cg2"), current_cfg=cfg)
        assert view.current_config is not None
        assert view.current_config.base_authority == "manual"

    def test_current_needs_review_propagates(self):
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg3",
            workspace_id=WS,
            method=METHOD_NONE,
            base_authority=BASE_AUTHORITY_NEEDS_REVIEW,
        )
        view = _build(_cgroup("cg3"), current_cfg=cfg)
        assert view.current_config is not None
        assert view.current_config.base_authority == "needs_review"


class TestPydanticSchemaIncludesBaseAuthority:
    """Verify the Pydantic OUT schema has base_authority field."""

    def test_voltage_config_out_has_base_authority_field(self):
        from app.schemas.measurement_group import VoltageGroupConfigOut
        fields = VoltageGroupConfigOut.model_fields
        assert "base_authority" in fields

    def test_current_config_out_has_base_authority_field(self):
        from app.schemas.measurement_group import CurrentGroupConfigOut
        fields = CurrentGroupConfigOut.model_fields
        assert "base_authority" in fields

    def test_voltage_config_out_serializes_base_authority(self):
        from app.schemas.measurement_group import VoltageGroupConfigOut
        out = VoltageGroupConfigOut(
            nominal_voltage_ll_kv=132.0,
            reference_mode="auto",
            reference_override=None,
            effective_reference="line_to_ground",
            evidence_names=["VA"],
            detection_reason="detected_line_to_ground",
            base_authority="auto_resolved",
        )
        d = out.model_dump()
        assert d["base_authority"] == "auto_resolved"

    def test_voltage_config_out_default_base_authority(self):
        from app.schemas.measurement_group import VoltageGroupConfigOut
        out = VoltageGroupConfigOut(
            nominal_voltage_ll_kv=None,
            reference_mode="auto",
            reference_override=None,
            effective_reference=None,
            evidence_names=[],
            detection_reason="no_evidence",
        )
        d = out.model_dump()
        assert d["base_authority"] == "legacy_manual"
