"""RD-1 Slice D3 — independent equipment-rating metadata tests.

Verifies that update_equipment_rating_metadata() persists equipment_mva
and equipment_linked_voltage_group_id independently of the PU current-base
method.  The three method invariants (OQ-D3-1 Option C):

- method="none" stays "none" after MVA entry.
- method="manual" stays "manual" and manual_ibase_ka is preserved exactly.
- method="equipment_rating" stays "equipment_rating"; existing method-coupled
  fields are not changed by this call.

Also verifies:
- equipment_rated_current_ka uses the correct formula.
- equipment_rated_current_ka is distinct from resolved_ibase_ka for method="manual".
- Invalid MVA values are rejected with appropriate errors.
- Invalid linked group references are rejected.
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import equipment_rating_ibase_ka
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import (
    set_current_base_equipment_rating,
    set_current_base_manual,
    update_equipment_rating_metadata,
)
from app.services.errors import (
    InvalidEquipmentRatingValueError,
    InvalidLinkedVoltageGroupError,
)
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base

WS = "ws-d3"
SRC = "src-d3"
VG_ID = "vg-d3"
CG_ID = "cg-d3"
CG2_ID = "cg-d3-2"
OTHER_SRC_VG_ID = "vg-other-src"


def _make_ref(name: str) -> ChannelRef:
    return ChannelRef(kind="source", source_id=SRC, channel_name=name)


def _make_registries():
    mr = MeasurementGroupRegistry()
    vcr = VoltageGroupConfigRegistry()
    ccr = CurrentGroupConfigRegistry()

    # Voltage group
    mr.add(MeasurementGroup(
        id=VG_ID, workspace_id=WS, source_id=SRC, kind=KIND_VOLTAGE,
        display_name="TEST VOLTAGE", channel_refs=[_make_ref("VA")], status=STATUS_CONFIRMED,
    ))
    set_voltage_base(
        workspace_id=WS, measurement_group_id=VG_ID,
        nominal_voltage_ll_kv=275.0,
        group_registry=mr, voltage_config_registry=vcr,
    )

    # Primary current group (default method=none)
    mr.add(MeasurementGroup(
        id=CG_ID, workspace_id=WS, source_id=SRC, kind=KIND_CURRENT,
        display_name="TEST CURRENT", channel_refs=[_make_ref("IA")], status=STATUS_CONFIRMED,
    ))

    # Second current group (for kind-rejection test)
    mr.add(MeasurementGroup(
        id=CG2_ID, workspace_id=WS, source_id=SRC, kind=KIND_CURRENT,
        display_name="TEST CURRENT 2", channel_refs=[_make_ref("IB")], status=STATUS_CONFIRMED,
    ))

    # Voltage group from a different source (for cross-source rejection)
    mr.add(MeasurementGroup(
        id=OTHER_SRC_VG_ID, workspace_id=WS, source_id="other-src", kind=KIND_VOLTAGE,
        display_name="OTHER VOLTAGE", channel_refs=[_make_ref("VB")], status=STATUS_CONFIRMED,
    ))
    set_voltage_base(
        workspace_id=WS, measurement_group_id=OTHER_SRC_VG_ID,
        nominal_voltage_ll_kv=132.0,
        group_registry=mr, voltage_config_registry=vcr,
    )

    return mr, vcr, ccr


def _update(mr, vcr, ccr, **kwargs):
    return update_equipment_rating_metadata(
        workspace_id=WS, measurement_group_id=CG_ID,
        group_registry=mr, current_config_registry=ccr, voltage_config_registry=vcr,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. method="none" stays "none" after MVA entry
# ---------------------------------------------------------------------------

def test_none_method_preserved_after_mva_entry():
    mr, vcr, ccr = _make_registries()
    cfg = _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=VG_ID)
    assert cfg.method == "none"
    assert cfg.equipment_mva == 100.0
    assert cfg.equipment_linked_voltage_group_id == VG_ID
    # method-coupled fields untouched
    assert cfg.equipment_rating_mva is None
    assert cfg.linked_voltage_group_id is None
    assert cfg.manual_ibase_ka is None


# ---------------------------------------------------------------------------
# 2. method="manual" stays "manual"; manual_ibase_ka preserved exactly
# ---------------------------------------------------------------------------

def test_manual_method_preserved_and_ibase_untouched():
    mr, vcr, ccr = _make_registries()
    set_current_base_manual(
        workspace_id=WS, measurement_group_id=CG_ID,
        manual_ibase_ka=0.42,
        group_registry=mr, current_config_registry=ccr,
    )
    cfg = _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=VG_ID)
    assert cfg.method == "manual"
    assert cfg.manual_ibase_ka == pytest.approx(0.42)
    assert cfg.equipment_mva == 100.0
    assert cfg.equipment_linked_voltage_group_id == VG_ID


# ---------------------------------------------------------------------------
# 3. method="equipment_rating" stays; method-coupled fields preserved
# ---------------------------------------------------------------------------

def test_equipment_rating_method_preserved():
    mr, vcr, ccr = _make_registries()
    set_current_base_equipment_rating(
        workspace_id=WS, measurement_group_id=CG_ID,
        equipment_rating_mva=50.0,
        linked_voltage_group_id=VG_ID,
        group_registry=mr, current_config_registry=ccr, voltage_config_registry=vcr,
    )
    cfg = _update(mr, vcr, ccr, equipment_mva=200.0, equipment_linked_voltage_group_id=VG_ID)
    assert cfg.method == "equipment_rating"
    # method-coupled fields still intact from set_current_base_equipment_rating
    assert cfg.equipment_rating_mva == 50.0
    assert cfg.linked_voltage_group_id == VG_ID
    # independent fields updated
    assert cfg.equipment_mva == 200.0


# ---------------------------------------------------------------------------
# 4. Association stored independently for method="none"
# ---------------------------------------------------------------------------

def test_association_stored_for_none_method():
    mr, vcr, ccr = _make_registries()
    cfg = _update(mr, vcr, ccr, equipment_mva=None, equipment_linked_voltage_group_id=VG_ID)
    assert cfg.equipment_linked_voltage_group_id == VG_ID
    assert cfg.method == "none"


# ---------------------------------------------------------------------------
# 5. Cross-source linked group rejected
# ---------------------------------------------------------------------------

def test_cross_source_linked_group_rejected():
    mr, vcr, ccr = _make_registries()
    with pytest.raises(InvalidLinkedVoltageGroupError, match="different source"):
        _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=OTHER_SRC_VG_ID)


# ---------------------------------------------------------------------------
# 6. kind="current" as linked group rejected
# ---------------------------------------------------------------------------

def test_current_kind_linked_group_rejected():
    mr, vcr, ccr = _make_registries()
    with pytest.raises(InvalidLinkedVoltageGroupError, match="kind"):
        _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=CG2_ID)


# ---------------------------------------------------------------------------
# 7. Invalid MVA: zero
# ---------------------------------------------------------------------------

def test_zero_mva_rejected():
    mr, vcr, ccr = _make_registries()
    with pytest.raises(InvalidEquipmentRatingValueError):
        _update(mr, vcr, ccr, equipment_mva=0.0, equipment_linked_voltage_group_id=VG_ID)


# ---------------------------------------------------------------------------
# 8. Invalid MVA: negative
# ---------------------------------------------------------------------------

def test_negative_mva_rejected():
    mr, vcr, ccr = _make_registries()
    with pytest.raises(InvalidEquipmentRatingValueError):
        _update(mr, vcr, ccr, equipment_mva=-50.0, equipment_linked_voltage_group_id=VG_ID)


# ---------------------------------------------------------------------------
# 9. Invalid MVA: non-finite
# ---------------------------------------------------------------------------

def test_nonfinite_mva_rejected():
    mr, vcr, ccr = _make_registries()
    with pytest.raises(InvalidEquipmentRatingValueError):
        _update(mr, vcr, ccr, equipment_mva=float("inf"), equipment_linked_voltage_group_id=VG_ID)


# ---------------------------------------------------------------------------
# 10. equipment_rated_current_ka uses correct formula
# ---------------------------------------------------------------------------

def test_equipment_rated_current_ka_correct_formula():
    mr, vcr, ccr = _make_registries()
    cfg = _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=VG_ID)
    expected = equipment_rating_ibase_ka(100.0, 275.0)
    computed = cfg.compute_equipment_rated_current_ka(275.0)
    assert computed == pytest.approx(expected)
    assert computed == pytest.approx(0.2099, rel=1e-3)


# ---------------------------------------------------------------------------
# 11. equipment_rated_current_ka = None when no association or no MVA
# ---------------------------------------------------------------------------

def test_equipment_rated_current_ka_none_without_association():
    mr, vcr, ccr = _make_registries()
    cfg = _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=None)
    assert cfg.compute_equipment_rated_current_ka(None) is None


def test_equipment_rated_current_ka_none_without_mva():
    mr, vcr, ccr = _make_registries()
    cfg = _update(mr, vcr, ccr, equipment_mva=None, equipment_linked_voltage_group_id=VG_ID)
    assert cfg.compute_equipment_rated_current_ka(275.0) is None


# ---------------------------------------------------------------------------
# 12. equipment_rated_current_ka distinct from resolved_ibase_ka for method="manual"
# ---------------------------------------------------------------------------

def test_equipment_rated_current_distinct_from_manual_ibase():
    mr, vcr, ccr = _make_registries()
    set_current_base_manual(
        workspace_id=WS, measurement_group_id=CG_ID,
        manual_ibase_ka=0.42,
        group_registry=mr, current_config_registry=ccr,
    )
    cfg = _update(mr, vcr, ccr, equipment_mva=100.0, equipment_linked_voltage_group_id=VG_ID)
    rated = cfg.compute_equipment_rated_current_ka(275.0)
    assert cfg.manual_ibase_ka == pytest.approx(0.42)
    assert rated == pytest.approx(0.2099, rel=1e-3)
    # They must be meaningfully different — this is the core D3 requirement
    assert abs(rated - cfg.manual_ibase_ka) > 0.1
