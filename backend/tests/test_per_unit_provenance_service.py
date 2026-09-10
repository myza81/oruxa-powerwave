"""Tests for app.services.per_unit_provenance_service (Per-Unit Settings
hierarchy, Slice 3) -- the channel-level Per-Unit provenance/
traceability read model that must, per the task's own critical rule,
always agree with the exact effective resolution used to convert a
channel's own displayed value (DEC-051 source-channel precedence,
DEC-052 calculated-channel Voltage multi-input restriction).

Reuses the same minimal `_group()` fixture-construction pattern already
established in `tests/test_group_aware_per_unit_service.py`.
`build_source_channel_provenance()`/`build_calculated_channel_provenance()`
operate on already-extracted primitives (engineering type/quantity,
profile, channel refs) -- no `ActiveSource`/COMTRADE construction is
needed at this layer at all.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.domain.calculated_channel import (
    OP_ADDITION,
    OP_REVERSE_POLARITY,
    CalculatedChannel,
    ChannelRef,
)
from app.domain.channel_classification import (
    CURRENT,
    ENGINEERING_QUANTITY_CURRENT_ANGLE,
    ENGINEERING_QUANTITY_VOLTAGE_ANGLE,
    FREQUENCY,
    VOLTAGE,
)
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.per_unit import (
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    PerUnitBaseProfile,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_equipment_rating
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_provenance_service import (
    SOURCE_KIND_MEASUREMENT_GROUP,
    SOURCE_KIND_SOURCE_DEFAULT,
    build_calculated_channel_provenance,
    build_source_channel_provenance,
)
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import set_voltage_base

SQRT_3 = 1.7320508075688772
WORKSPACE = "ws-1"
SOURCE = "src-1"


def _group(group_id: str, kind: str, channel_names: tuple[str, ...], status: str = STATUS_CONFIRMED) -> MeasurementGroup:
    return MeasurementGroup(
        id=group_id, workspace_id=WORKSPACE, source_id=SOURCE, kind=kind, display_name=group_id.upper(),
        channel_refs=[ChannelRef(kind="source", source_id=SOURCE, channel_name=n) for n in channel_names],
        status=status,
    )


def _profile(**overrides) -> PerUnitBaseProfile:
    defaults = dict(
        voltage_base_value=None, voltage_reference_mode="auto", voltage_reference_override=None,
        current_base_mode="none", apparent_power_base_value=None, direct_current_base_value=None,
    )
    defaults.update(overrides)
    return PerUnitBaseProfile(source_id=SOURCE, workspace_id=WORKSPACE, **defaults)


def _calc(calc_id: str, operation: str, inputs: list[ChannelRef], engineering_type: str) -> CalculatedChannel:
    n = 4
    return CalculatedChannel(
        id=calc_id, workspace_id=WORKSPACE, name=calc_id, unit="V" if engineering_type == VOLTAGE else "A",
        operation=operation, inputs=inputs, parameters={},
        dependency_ids=[ref.calculated_channel_id for ref in inputs if ref.kind == "calculated"],
        reference_source_id=SOURCE, engineering_type=engineering_type,
        time=np.arange(n, dtype=np.float64), values=np.ones(n, dtype=np.float64),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def group_registry() -> MeasurementGroupRegistry:
    return MeasurementGroupRegistry()


@pytest.fixture
def voltage_config_registry() -> VoltageGroupConfigRegistry:
    return VoltageGroupConfigRegistry()


@pytest.fixture
def current_config_registry() -> CurrentGroupConfigRegistry:
    return CurrentGroupConfigRegistry()


@pytest.fixture
def calc_registry() -> CalculatedChannelRegistry:
    return CalculatedChannelRegistry()


def _build_source(
    channel_name, engineering_type, engineering_quantity="Undefined", *,
    profile=None, voltage_channel_names=None,
    group_registry=None, voltage_config_registry=None, current_config_registry=None,
):
    return build_source_channel_provenance(
        workspace_id=WORKSPACE, source_id=SOURCE, channel_name=channel_name,
        engineering_type=engineering_type, engineering_quantity=engineering_quantity,
        per_unit_profile=profile, voltage_channel_names=voltage_channel_names or [],
        group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        current_config_registry=current_config_registry,
    )


class TestGroupedConfiguredVoltageChannel:
    """Scenarios 1, 8, 9: grouped configured Voltage channel, LL group,
    and LG group with effective LL/sqrt(3) denominator."""

    def test_ll_group_nominal_equals_effective(self, group_registry, voltage_config_registry, current_config_registry):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VRY", "VYB", "VBR")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        prov = _build_source(
            "VRY", VOLTAGE, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.measurement_group_id == "mg-v"
        assert prov.measurement_group_name == "MG-V"
        assert prov.nominal_base_kv == 275.0
        assert prov.nominal_reference == "line_to_line"
        assert prov.effective_base_amount == pytest.approx(275.0, abs=1e-6)
        assert prov.effective_base_unit == "kV"

    def test_lg_group_effective_is_ll_over_sqrt3(self, group_registry, voltage_config_registry, current_config_registry):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        prov = _build_source(
            "VR", VOLTAGE, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.nominal_base_kv == 275.0
        assert prov.nominal_reference == "line_to_ground"
        assert prov.effective_base_amount == pytest.approx(275.0 / SQRT_3, abs=1e-4)
        assert prov.effective_base_unit == "kV"
        # Worked example from the task's own spec.
        assert prov.effective_base_amount == pytest.approx(158.77, abs=0.01)


class TestGroupedConfiguredCurrentChannel:
    """Scenario 2: grouped configured Current channel."""

    def test_equipment_rating_current_group(self, group_registry, voltage_config_registry, current_config_registry):
        group_registry.add(_group("mg-i", KIND_CURRENT, ("IR", "IY", "IB")))
        set_current_base_equipment_rating(
            workspace_id=WORKSPACE, measurement_group_id="mg-i", equipment_rating_mva=1000.0,
            linked_voltage_group_id=None, manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        prov = _build_source(
            "IR", CURRENT, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.equipment_rating_mva == 1000.0
        assert prov.applicable_voltage_ll_kv == 275.0
        assert prov.effective_base_amount == pytest.approx(1000.0 / (SQRT_3 * 275.0), abs=1e-6)
        assert prov.effective_base_unit == "kA"
        # Voltage-only fields must stay unset for a Current group.
        assert prov.nominal_base_kv is None
        assert prov.nominal_reference is None


class TestGroupedIncompleteChannel:
    """Scenario 3: grouped incomplete channel -- status + a useful,
    concise reason."""

    def test_confirmed_group_with_no_base_set(self, group_registry, voltage_config_registry, current_config_registry):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        prov = _build_source(
            "VR", VOLTAGE, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_BASE_REQUIRED
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.measurement_group_name == "MG-V"
        assert prov.reason == "Voltage base is not configured for this group."
        assert prov.effective_base_amount is None


class TestUngroupedSourceDefaultChannels:
    """Scenarios 4, 5: ungrouped Source Default Voltage/Current
    channels -- truthful, un-annotated single base amount."""

    def test_source_default_voltage(self, group_registry, voltage_config_registry, current_config_registry):
        profile = _profile(voltage_base_value=275.0)
        prov = _build_source(
            "V132", VOLTAGE, profile=profile, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_SOURCE_DEFAULT
        assert prov.measurement_group_id is None
        assert prov.measurement_group_name is None
        # Truthfulness requirement: no fabricated LL/LG split for Source
        # Default -- only the plain resolved amount, never a "nominal".
        assert prov.nominal_base_kv is None
        assert prov.nominal_reference is None
        assert prov.effective_base_amount == pytest.approx(275.0, abs=1e-6)
        assert prov.effective_base_unit == "kV"

    def test_source_default_current_direct(self, group_registry, voltage_config_registry, current_config_registry):
        profile = _profile(current_base_mode="direct", direct_current_base_value=2.0995)
        prov = _build_source(
            "LINEA_IR", CURRENT, profile=profile, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_SOURCE_DEFAULT
        assert prov.effective_base_amount == pytest.approx(2.0995, abs=1e-4)
        assert prov.effective_base_unit == "kA"


class TestUngroupedMissingSourceDefault:
    """Scenario 6: ungrouped channel with no usable Source Default."""

    def test_no_profile_at_all(self, group_registry, voltage_config_registry, current_config_registry):
        prov = _build_source(
            "VR", VOLTAGE, profile=None, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_BASE_REQUIRED
        assert prov.source_kind == SOURCE_KIND_SOURCE_DEFAULT
        assert prov.reason == "No usable source-wide per-unit base is configured."
        assert prov.effective_base_amount is None


class TestNotApplicableChannels:
    """Scenario 7: Voltage/Current Angle (and other non-Voltage/Current
    types) never show base information."""

    def test_voltage_angle_is_not_applicable_even_when_a_source_default_exists(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        profile = _profile(voltage_base_value=275.0)
        prov = _build_source(
            "VR_ANGLE", VOLTAGE, engineering_quantity=ENGINEERING_QUANTITY_VOLTAGE_ANGLE, profile=profile,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_NOT_APPLICABLE
        assert prov.source_kind is None
        assert prov.effective_base_amount is None
        assert prov.reason is None

    def test_current_angle_is_not_applicable_even_when_grouped(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        group_registry.add(_group("mg-i", KIND_CURRENT, ("IR_ANGLE",)))
        set_current_base_equipment_rating(
            workspace_id=WORKSPACE, measurement_group_id="mg-i", equipment_rating_mva=100.0,
            linked_voltage_group_id=None, manual_voltage_base_kv=132.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        prov = _build_source(
            "IR_ANGLE", CURRENT, engineering_quantity=ENGINEERING_QUANTITY_CURRENT_ANGLE,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_NOT_APPLICABLE
        assert prov.source_kind is None

    def test_frequency_channel_is_not_applicable(self, group_registry, voltage_config_registry, current_config_registry):
        prov = _build_source(
            "F1", FREQUENCY, group_registry=group_registry, voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_NOT_APPLICABLE
        assert prov.source_kind is None


class TestGroupedChannelNeverReportsSourceDefault:
    """Scenario 10: a grouped channel's provenance must never say Source
    Default, even when a fully usable one exists on the same source."""

    def test_grouped_incomplete_never_reports_source_default(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        profile = _profile(voltage_base_value=275.0)
        prov = _build_source(
            "VR", VOLTAGE, profile=profile, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.status == STATUS_BASE_REQUIRED

    def test_grouped_configured_never_reports_source_default(
        self, group_registry, voltage_config_registry, current_config_registry
    ):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY", "VB")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        profile = _profile(voltage_base_value=999.0)
        prov = _build_source(
            "VR", VOLTAGE, profile=profile, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.status == STATUS_CONFIGURED
        assert prov.effective_base_amount == pytest.approx(275.0 / SQRT_3, abs=1e-4)


class TestCalculatedChannelProvenance:
    """Scenarios 11, 12, 13: calculated-channel provenance must match
    DEC-052 exactly -- never simplified to "same as first input"."""

    def test_unary_calculated_channel_inherits_group_provenance(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR",)))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        calc = _calc(
            "calc-1", OP_REVERSE_POLARITY, [ChannelRef(kind="source", source_id=SOURCE, channel_name="VR")], VOLTAGE
        )
        calc_registry.add(calc)
        prov = build_calculated_channel_provenance(
            workspace_id=WORKSPACE, channel=calc, per_unit_profile=None, voltage_channel_names=[],
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.measurement_group_id == "mg-v"
        assert prov.effective_base_amount == pytest.approx(275.0 / SQRT_3, abs=1e-4)

    def test_multi_input_voltage_addition_never_inherits_group_per_dec_052(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        group_registry.add(_group("mg-v", KIND_VOLTAGE, ("VR", "VY")))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        calc = _calc(
            "calc-2", OP_ADDITION,
            [
                ChannelRef(kind="source", source_id=SOURCE, channel_name="VR"),
                ChannelRef(kind="source", source_id=SOURCE, channel_name="VY"),
            ],
            VOLTAGE,
        )
        calc_registry.add(calc)
        # No Source Default configured either -- DEC-052 says this must
        # resolve base_required, NEVER silently inherit the group.
        prov = build_calculated_channel_provenance(
            workspace_id=WORKSPACE, channel=calc, per_unit_profile=None, voltage_channel_names=[],
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_BASE_REQUIRED
        assert prov.source_kind == SOURCE_KIND_SOURCE_DEFAULT
        assert prov.measurement_group_id is None

    def test_multi_input_current_addition_does_inherit_group(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        group_registry.add(_group("mg-i", KIND_CURRENT, ("IR", "IY")))
        set_current_base_equipment_rating(
            workspace_id=WORKSPACE, measurement_group_id="mg-i", equipment_rating_mva=1000.0,
            linked_voltage_group_id=None, manual_voltage_base_kv=275.0,
            group_registry=group_registry, current_config_registry=current_config_registry,
            voltage_config_registry=voltage_config_registry,
        )
        calc = _calc(
            "calc-3", OP_ADDITION,
            [
                ChannelRef(kind="source", source_id=SOURCE, channel_name="IR"),
                ChannelRef(kind="source", source_id=SOURCE, channel_name="IY"),
            ],
            CURRENT,
        )
        calc_registry.add(calc)
        prov = build_calculated_channel_provenance(
            workspace_id=WORKSPACE, channel=calc, per_unit_profile=None, voltage_channel_names=[],
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_CONFIGURED
        assert prov.source_kind == SOURCE_KIND_MEASUREMENT_GROUP
        assert prov.measurement_group_id == "mg-i"

    def test_cross_group_calculated_channel_falls_back_to_legacy(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        group_registry.add(_group("mg-v1", KIND_VOLTAGE, ("VR",)))
        group_registry.add(_group("mg-v2", KIND_VOLTAGE, ("VY",)))
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v1", nominal_voltage_ll_kv=275.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        set_voltage_base(
            workspace_id=WORKSPACE, measurement_group_id="mg-v2", nominal_voltage_ll_kv=132.0,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        calc = _calc(
            "calc-4", OP_ADDITION,
            [
                ChannelRef(kind="source", source_id=SOURCE, channel_name="VR"),
                ChannelRef(kind="source", source_id=SOURCE, channel_name="VY"),
            ],
            VOLTAGE,
        )
        calc_registry.add(calc)
        # No Source Default configured -- cross-group AND (per DEC-052)
        # Voltage-multi-input both independently forbid inheritance, so
        # this must be an ungrouped-shaped base_required, never silently
        # picking one of the two candidate groups.
        prov = build_calculated_channel_provenance(
            workspace_id=WORKSPACE, channel=calc, per_unit_profile=None, voltage_channel_names=[],
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_BASE_REQUIRED
        assert prov.source_kind == SOURCE_KIND_SOURCE_DEFAULT
        assert prov.measurement_group_id is None

    def test_calculated_channel_not_applicable_type(
        self, group_registry, voltage_config_registry, current_config_registry, calc_registry
    ):
        calc = _calc("calc-5", OP_REVERSE_POLARITY, [ChannelRef(kind="source", source_id=SOURCE, channel_name="F1")], FREQUENCY)
        calc_registry.add(calc)
        prov = build_calculated_channel_provenance(
            workspace_id=WORKSPACE, channel=calc, per_unit_profile=None, voltage_channel_names=[],
            calc_registry=calc_registry, group_registry=group_registry,
            voltage_config_registry=voltage_config_registry, current_config_registry=current_config_registry,
        )
        assert prov.status == STATUS_NOT_APPLICABLE
