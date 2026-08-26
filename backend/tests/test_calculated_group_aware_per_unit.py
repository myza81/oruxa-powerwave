"""Unit tests for app.services.calculated_group_aware_per_unit (DEC-050
Slice 7) -- the pure resolver level, without going through the FastAPI
app (see test_calculated_group_aware_per_unit_endpoints.py for live-
endpoint integration coverage).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.domain.calculated_channel import (
    OP_ABSOLUTE_VALUE,
    OP_ADDITION,
    OP_MULTIPLY_CONSTANT,
    OP_REVERSE_POLARITY,
    OP_RMS,
    OP_SUBTRACTION,
    CalculatedChannel,
    ChannelRef,
)
from app.domain.channel_classification import CURRENT, FREQUENCY, UNDEFINED, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, STATUS_SUGGESTED, MeasurementGroup
from app.domain.per_unit import STATUS_BASE_REQUIRED, STATUS_CONFIGURED
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_group_aware_per_unit import (
    resolve_calculated_group_aware_per_unit,
    resolve_inherited_measurement_group_id,
)
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_equipment_rating, set_current_base_manual
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772
WS = "ws-1"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _group(group_id, kind, source_id="src-1", channel_names=("A", "B", "C"), status=STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id=WS, source_id=source_id, kind=kind, display_name=group_id.upper(),
        channel_refs=[ChannelRef(kind="source", source_id=source_id, channel_name=n) for n in channel_names],
        status=status,
    )


def _calc(
    calc_id: str,
    *,
    operation: str,
    inputs: list[ChannelRef],
    engineering_type: str = VOLTAGE,
    unit: str = "V",
) -> CalculatedChannel:
    n = 5
    return CalculatedChannel(
        id=calc_id, workspace_id=WS, name=calc_id, unit=unit, operation=operation, inputs=inputs,
        parameters={}, dependency_ids=[ref.calculated_channel_id for ref in inputs if ref.kind == "calculated"],
        reference_source_id="src-1", time=np.arange(n, dtype=float), values=np.ones(n, dtype=float),
        created_at=_NOW, engineering_type=engineering_type,
    )


def _source_ref(source_id: str, name: str) -> ChannelRef:
    return ChannelRef(kind="source", source_id=source_id, channel_name=name)


def _calc_ref(calc_id: str) -> ChannelRef:
    return ChannelRef(kind="calculated", calculated_channel_id=calc_id)


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    registry = MeasurementGroupRegistry()
    registry.add(_group("mg-v1", KIND_VOLTAGE, source_id="src-1", channel_names=("VR", "VY", "VB")))
    registry.add(_group("mg-v2", KIND_VOLTAGE, source_id="src-1", channel_names=("VX", "VZ")))
    registry.add(_group("mg-i1", KIND_CURRENT, source_id="src-1", channel_names=("IR", "IY", "IB")))
    registry.add(_group("mg-i2", KIND_CURRENT, source_id="src-1", channel_names=("IHV",)))
    registry.add(_group("mg-i3", KIND_CURRENT, source_id="src-1", channel_names=("ILV",)))
    # A second source with identically-named channels/groups -- proves
    # cross-source inheritance is refused via id, not name/value equality.
    registry.add(_group("mg-v1-src2", KIND_VOLTAGE, source_id="src-2", channel_names=("VR", "VY", "VB")))
    return registry


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


@pytest.fixture
def current_config_registry() -> CurrentGroupConfigRegistry:
    return CurrentGroupConfigRegistry()


@pytest.fixture
def calc_registry() -> CalculatedChannelRegistry:
    return CalculatedChannelRegistry()


def _configure_voltage(group_id, group_registry, voltage_config_registry, *, nominal_kv=275.0):
    set_voltage_base(
        workspace_id=WS, measurement_group_id=group_id, nominal_voltage_ll_kv=nominal_kv,
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
    )


def _configure_current_manual(group_id, group_registry, current_config_registry, *, ibase_ka=1.0):
    set_current_base_manual(
        workspace_id=WS, measurement_group_id=group_id, manual_ibase_ka=ibase_ka,
        group_registry=group_registry, current_config_registry=current_config_registry,
    )


class TestSameGroupUnaryInheritance:
    def test_reverse_polarity_inherits_voltage_group(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        _configure_voltage("mg-v1", group_registry, voltage_config_registry)
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=VOLTAGE)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-v1"
        # VR/VY/VB is LG-detected: denominator is nominal_LL/sqrt(3), in volts.
        assert result.base_amount == pytest.approx((275.0 / SQRT_3) * 1000.0, abs=0.1)

    def test_absolute_value_inherits_current_group(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        _configure_current_manual("mg-i1", group_registry, current_config_registry, ibase_ka=2.5)
        channel = _calc("c1", operation=OP_ABSOLUTE_VALUE, inputs=[_source_ref("src-1", "IR")], engineering_type=CURRENT, unit="A")
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-i1"
        assert result.base_amount == pytest.approx(2500.0, abs=0.1)

    def test_multiply_constant_and_rms_also_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        _configure_voltage("mg-v1", group_registry, voltage_config_registry)
        for op in (OP_MULTIPLY_CONSTANT, OP_RMS):
            channel = _calc("c-" + op, operation=op, inputs=[_source_ref("src-1", "VR")], engineering_type=VOLTAGE)
            result = resolve_calculated_group_aware_per_unit(
                workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
                group_registry=group_registry, voltage_config_registry=voltage_config_registry,
                current_config_registry=current_config_registry,
            )
            assert result is not None and result.status == STATUS_CONFIGURED and result.profile_id == "mg-v1"


class TestSameGroupMultiInputInheritance:
    def test_addition_inherits_current_group(self, group_registry, voltage_config_registry, current_config_registry):
        _configure_current_manual("mg-i1", group_registry, current_config_registry, ibase_ka=1.5)
        channel = _calc(
            "c1", operation=OP_ADDITION,
            inputs=[_source_ref("src-1", "IR"), _source_ref("src-1", "IY")], engineering_type=CURRENT, unit="A",
        )
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-i1"

    def test_subtraction_inherits_current_group(self, group_registry, voltage_config_registry, current_config_registry):
        _configure_current_manual("mg-i1", group_registry, current_config_registry, ibase_ka=1.5)
        channel = _calc(
            "c1", operation=OP_SUBTRACTION,
            inputs=[_source_ref("src-1", "IR"), _source_ref("src-1", "IY")], engineering_type=CURRENT, unit="A",
        )
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None and result.status == STATUS_CONFIGURED

    def test_addition_from_same_voltage_group_does_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        """Conservative LG/LL restriction (see module docstring): a
        Voltage group's own resolved denominator may not remain the
        correct reference for an Addition/Subtraction result (e.g.
        VR - VY is numerically phase-to-phase even though VR/VY are
        each phase-to-ground) -- this codebase has no metadata to prove
        otherwise, so Voltage multi-input arithmetic never inherits,
        unanimous group agreement notwithstanding."""
        _configure_voltage("mg-v1", group_registry, voltage_config_registry)
        channel = _calc(
            "c1", operation=OP_SUBTRACTION,
            inputs=[_source_ref("src-1", "VR"), _source_ref("src-1", "VY")], engineering_type=VOLTAGE,
        )
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None


class TestCrossGroupAndCrossSource:
    def test_cross_group_same_kind_does_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        """VR_A - VR_B (both Voltage, DIFFERENT groups) must not
        silently pick either group's base."""
        _configure_voltage("mg-v1", group_registry, voltage_config_registry, nominal_kv=275.0)
        _configure_voltage("mg-v2", group_registry, voltage_config_registry, nominal_kv=275.0)
        channel = _calc(
            "c1", operation=OP_SUBTRACTION,
            inputs=[_source_ref("src-1", "VR"), _source_ref("src-1", "VX")], engineering_type=VOLTAGE,
        )
        gid = resolve_inherited_measurement_group_id(
            WS, channel, calc_registry=CalculatedChannelRegistry(), group_registry=group_registry
        )
        assert gid is None
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_transformer_hv_lv_cross_group_current_does_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        _configure_current_manual("mg-i2", group_registry, current_config_registry, ibase_ka=2.1015)
        _configure_current_manual("mg-i3", group_registry, current_config_registry, ibase_ka=4.375)
        channel = _calc(
            "c1", operation=OP_ADDITION,
            inputs=[_source_ref("src-1", "IHV"), _source_ref("src-1", "ILV")], engineering_type=CURRENT, unit="A",
        )
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_cross_source_identical_group_names_do_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        """Two sources each have their own 'mg-v1'-shaped group with
        IDENTICAL channel names (VR/VY/VB) -- group identity is keyed on
        measurement_group_id, never on name or (source, channel_name)
        coincidence."""
        _configure_voltage("mg-v1", group_registry, voltage_config_registry, nominal_kv=275.0)
        _configure_voltage("mg-v1-src2", group_registry, voltage_config_registry, nominal_kv=275.0)
        channel = _calc(
            "c1", operation=OP_SUBTRACTION,
            inputs=[_source_ref("src-1", "VR"), _source_ref("src-2", "VR")], engineering_type=VOLTAGE,
        )
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None


class TestQuantityCompatibility:
    def test_non_voltage_current_type_never_looks_up_a_group(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=FREQUENCY)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_undefined_engineering_type_does_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=UNDEFINED)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None


class TestUngroupedAndUnresolvedGroups:
    def test_ungrouped_source_input_does_not_inherit(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "SPARE")], engineering_type=VOLTAGE)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_grouped_but_unconfigured_group_resolves_base_required(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        """The group exists and the channel is unambiguously a member,
        but the group's own Voltage Base was never configured --
        base_required, never a silent fallback to any other base."""
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=VOLTAGE)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED
        assert result.profile_id == "mg-v1"

    def test_current_method_none_resolves_base_required(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        channel = _calc("c1", operation=OP_ABSOLUTE_VALUE, inputs=[_source_ref("src-1", "IR")], engineering_type=CURRENT, unit="A")
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED

    def test_suggested_group_status_resolves_base_required_not_configured(
        self, voltage_config_registry, current_config_registry
    ):
        registry = MeasurementGroupRegistry()
        registry.add(_group("mg-v1", KIND_VOLTAGE, channel_names=("VR", "VY", "VB"), status=STATUS_SUGGESTED))
        _configure_voltage("mg-v1", registry, voltage_config_registry)
        channel = _calc("c1", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=VOLTAGE)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=channel, calc_registry=CalculatedChannelRegistry(),
            group_registry=registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_BASE_REQUIRED


class TestCalculatedOnCalculated:
    def test_chain_of_unary_operations_propagates_inherited_group(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        """A = -VR (inherits mg-v1); B = abs(A) (inherits from A, i.e.
        transitively from mg-v1) -- composes with no separate recursive
        algorithm, mirroring DEC-049's own source-id-level composition."""
        _configure_voltage("mg-v1", group_registry, voltage_config_registry)
        a = _calc("calc-a", operation=OP_REVERSE_POLARITY, inputs=[_source_ref("src-1", "VR")], engineering_type=VOLTAGE)
        calc_registry.add(a)
        b = _calc("calc-b", operation=OP_ABSOLUTE_VALUE, inputs=[_calc_ref("calc-a")], engineering_type=VOLTAGE)
        calc_registry.add(b)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=b, calc_registry=calc_registry,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-v1"

    def test_chain_where_addition_combines_two_same_group_calculated_inputs(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        """A = IR + IY (inherits mg-i1); B = A - IB (IB also mg-i1) ->
        still mg-i1, all paths converge to the same group id."""
        _configure_current_manual("mg-i1", group_registry, current_config_registry, ibase_ka=1.5)
        a = _calc(
            "calc-a", operation=OP_ADDITION,
            inputs=[_source_ref("src-1", "IR"), _source_ref("src-1", "IY")], engineering_type=CURRENT, unit="A",
        )
        calc_registry.add(a)
        b = _calc(
            "calc-b", operation=OP_SUBTRACTION,
            inputs=[_calc_ref("calc-a"), _source_ref("src-1", "IB")], engineering_type=CURRENT, unit="A",
        )
        calc_registry.add(b)
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=b, calc_registry=calc_registry,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is not None
        assert result.status == STATUS_CONFIGURED
        assert result.profile_id == "mg-i1"

    def test_chain_where_a_calculated_input_is_already_ambiguous_stays_ambiguous(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        """A = VR - VX (cross-group Voltage -> no context, decision-9
        rule); B = abs(A) must NOT magically regain a group context just
        because its own operation is unary/inheriting-verbatim."""
        _configure_voltage("mg-v1", group_registry, voltage_config_registry)
        _configure_voltage("mg-v2", group_registry, voltage_config_registry)
        a = _calc(
            "calc-a", operation=OP_SUBTRACTION,
            inputs=[_source_ref("src-1", "VR"), _source_ref("src-1", "VX")], engineering_type=VOLTAGE,
        )
        calc_registry.add(a)
        b = _calc("calc-b", operation=OP_ABSOLUTE_VALUE, inputs=[_calc_ref("calc-a")], engineering_type=VOLTAGE)
        calc_registry.add(b)
        gid = resolve_inherited_measurement_group_id(
            WS, b, calc_registry=calc_registry, group_registry=group_registry
        )
        assert gid is None
        result = resolve_calculated_group_aware_per_unit(
            workspace_id=WS, channel=b, calc_registry=calc_registry,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None

    def test_missing_calculated_input_is_treated_as_no_context(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        """Defensive: a ChannelRef pointing at a calculated channel id
        that no longer exists in the registry resolves as unresolved,
        never a crash."""
        b = _calc("calc-b", operation=OP_ABSOLUTE_VALUE, inputs=[_calc_ref("does-not-exist")], engineering_type=VOLTAGE)
        gid = resolve_inherited_measurement_group_id(
            WS, b, calc_registry=calc_registry, group_registry=group_registry
        )
        assert gid is None
