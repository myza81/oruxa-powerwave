"""PU-CORE-001 Phase 3 — Independent mathematical verification matrix.

Expected values are pre-computed from first principles BEFORE calling any
production function.  Each expected value is derived from the governing formula
only; no production resolver is used to generate it.  Numerical equivalence
against the production result proves the domain code implements the contracts
correctly.

Governing formulas (from docs/project-memory/PER_UNIT_MEASUREMENT_MODEL.md
and owner-approved DECISIONS.md records; independent of this file):

Voltage PU (DEC-049 Slice 4 / DEC-050):
    nominal_voltage_ll_kv stored as kV LL
    LG reference: base_V = nominal_ll_kv * 1000 / sqrt(3)
    LL reference: base_V = nominal_ll_kv * 1000
    PU = (measured * unit_scale_V) / base_V

Current PU — Direct mode (DEC-049 / DEC-050):
    base_V  NOT involved; direct_base_kA only
    base_A = direct_base_kA * 1000
    PU = (measured * unit_scale_A) / base_A

Current PU — Derived mode (DEC-049 Slice 4 / DEC-050 Equipment Rating):
    Ibase_A = Sbase_MVA * 1e6 / (sqrt(3) * Vbase_LL_kV * 1000)
            = Sbase_MVA * 1e6 / (sqrt(3) * Vbase_LL_V)
    Vbase_LL_V is the NOMINAL LL voltage — NOT adjusted for LG reference
    (Slice 4 correction; see DEC-049 Addendum)
    PU = (measured * unit_scale_A) / Ibase_A

Voltage secondary path (Slice 5D-1):
    base_V = secondary_voltage_ll_v / sqrt(3)   (LG)
    base_V = secondary_voltage_ll_v              (LL)
    PU = (measured * unit_scale_V) / base_V

Unit scales (canonical):  V→V: 1.0,  kV→V: 1000.0
                           A→A: 1.0,  kA→A: 1000.0
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# Production imports — used ONLY to build fixtures and call the resolver.
# Expected values below are NEVER derived from these imports.
from app.domain.calculated_channel import ChannelRef, CalculatedChannel, OP_REVERSE_POLARITY, OP_RMS
from app.domain.channel_classification import CURRENT, VOLTAGE
from app.domain.measurement_group import KIND_CURRENT, KIND_VOLTAGE, STATUS_CONFIRMED, MeasurementGroup
from app.domain.per_unit import (
    PerUnitBaseProfile,
    STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE,
    convert_value_to_pu,
    resolve_conversion_eligibility,
    resolve_per_unit,
)
from app.services.calculated_channel_registry import CalculatedChannelRegistry
from app.services.calculated_channel_service import _resolve_effective_per_unit_for_calculated_channel
from app.services.current_group_config_registry import CurrentGroupConfigRegistry
from app.services.current_group_config_service import set_current_base_equipment_rating
from app.services.group_aware_per_unit import resolve_group_aware_per_unit
from app.services.measurement_group_registry import MeasurementGroupRegistry
from app.services.per_unit_registry import PerUnitRegistry
from app.services.voltage_group_config_registry import VoltageGroupConfigRegistry
from app.services.voltage_group_config_service import update_voltage_configuration
from app.services.workspace_registry import WorkspaceRegistry
from tests.test_per_unit_coverage_service import SOURCE, WORKSPACE, _active_source, _channel

# C10 tests must use the SOURCE/WORKSPACE IDs that _active_source() embeds,
# because _resolve_effective_per_unit_for_calculated_channel() looks up the
# source by workspace_id+reference_source_id for the calibration gate.
_C10_WS = WORKSPACE
_C10_SRC = SOURCE

# ---------------------------------------------------------------------------
# Shared mathematical constants (independent of domain code — computed here)
# ---------------------------------------------------------------------------

#: IEEE/IEC sqrt(3) = 1.7320508075688772935...
_SQRT3 = math.sqrt(3)

WS = "pu-core-001-math"
SRC = "src-math-01"


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------


def _profile(
    *,
    source_id: str = SRC,
    voltage_base_kv: float | None = None,
    voltage_reference_mode: str = "auto",
    voltage_reference_override: str | None = None,
    current_base_mode: str = "none",
    apparent_power_mva: float | None = None,
    direct_current_ka: float | None = None,
) -> PerUnitBaseProfile:
    return PerUnitBaseProfile(
        source_id=source_id, workspace_id=WS,
        voltage_base_value=voltage_base_kv,
        voltage_reference_mode=voltage_reference_mode,
        voltage_reference_override=voltage_reference_override,
        current_base_mode=current_base_mode,
        apparent_power_base_value=apparent_power_mva,
        direct_current_base_value=direct_current_ka,
    )


def _volt_names_lg() -> list[str]:
    """Three phase-to-ground channel names (auto-detects LG)."""
    return ["VR", "VY", "VB"]


def _volt_names_ll() -> list[str]:
    """Three line-to-line channel names (auto-detects LL)."""
    return ["VAB", "VBC", "VCA"]


def _make_mg(
    *,
    ws: str = WS,
    src: str = SRC,
    kind: str = KIND_VOLTAGE,
    group_id: str = "mg-v1",
    names: list[str] | None = None,
) -> MeasurementGroup:
    if names is None:
        names = ["VR", "VY", "VB"]
    return MeasurementGroup(
        id=group_id, workspace_id=ws, source_id=src,
        kind=kind, display_name="Test Group",
        channel_refs=[ChannelRef(kind="source", source_id=src, channel_name=n) for n in names],
        status=STATUS_CONFIRMED,
    )


# ===========================================================================
# CONTRACT C1 — DEC-049 Voltage PU: Line-to-Ground reference
# ===========================================================================


class TestC1VoltageDecLG:
    """Governing formula: base_V = nominal_ll_kv * 1000 / sqrt(3)
    PU = (measured_kV * 1000) / base_V = measured_kV / (nominal_ll_kv / sqrt(3))
    """

    def test_c1a_nominal_100kv_measured_phase_voltage_is_1pu(self):
        # Pre-computed: phase voltage of a 100 kV LL system = 100 / sqrt(3) kV
        nominal_ll_kv = 100.0
        measured_kv = 100.0 / _SQRT3                      # = 57.735... kV (1 pu phase)
        expected_base_v = nominal_ll_kv * 1000.0 / _SQRT3  # = 57,735... V
        expected_pu = (measured_kv * 1000.0) / expected_base_v  # = 1.0 exactly

        profile = _profile(
            voltage_base_kv=nominal_ll_kv,
            voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        # Domain base_amount must equal the pre-computed denominator.
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
        result = convert_value_to_pu(measured_kv, "kV", resolution, VOLTAGE)
        assert result == pytest.approx(expected_pu, rel=1e-9)

    def test_c1b_nominal_275kv_measured_nominal_phase_voltage_is_1pu(self):
        nominal_ll_kv = 275.0
        measured_kv = 275.0 / _SQRT3
        expected_base_v = 275.0 * 1000.0 / _SQRT3
        expected_pu = 1.0

        profile = _profile(
            voltage_base_kv=nominal_ll_kv,
            voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
        assert convert_value_to_pu(measured_kv, "kV", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c1c_measured_in_v_not_kv_same_pu(self):
        nominal_ll_kv = 132.0
        measured_v = 132.0 * 1000.0 / _SQRT3        # phase voltage in V
        expected_base_v = 132.0 * 1000.0 / _SQRT3
        expected_pu = 1.0

        profile = _profile(
            voltage_base_kv=nominal_ll_kv,
            voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert convert_value_to_pu(measured_v, "V", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c1d_half_nominal_voltage_gives_half_pu(self):
        nominal_ll_kv = 400.0
        measured_kv = (400.0 / _SQRT3) / 2.0   # 50 % of nominal phase voltage
        expected_pu = 0.5

        profile = _profile(
            voltage_base_kv=nominal_ll_kv,
            voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert convert_value_to_pu(measured_kv, "kV", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c1e_auto_detection_lg_matches_manual_lg_base(self):
        # Channel names "VR", "VY", "VB" auto-detect line_to_ground.
        nominal_ll_kv = 275.0
        expected_base_v = 275.0 * 1000.0 / _SQRT3
        profile = _profile(voltage_base_kv=nominal_ll_kv, voltage_reference_mode="auto")
        resolution = resolve_per_unit(VOLTAGE, profile, ["VR", "VY", "VB"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)


# ===========================================================================
# CONTRACT C2 — DEC-049 Voltage PU: Line-to-Line reference
# ===========================================================================


class TestC2VoltageDecLL:
    """Governing formula: base_V = nominal_ll_kv * 1000
    PU = (measured_kV * 1000) / base_V = measured_kV / nominal_ll_kv
    """

    def test_c2a_nominal_275kv_measured_nominal_ll_is_1pu(self):
        nominal_ll_kv = 275.0
        measured_kv = 275.0
        expected_base_v = 275.0 * 1000.0   # = 275,000 V
        expected_pu = 1.0

        profile = _profile(
            voltage_base_kv=nominal_ll_kv,
            voltage_reference_mode="manual",
            voltage_reference_override="line_to_line",
        )
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_ll())
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
        assert convert_value_to_pu(measured_kv, "kV", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c2b_ll_base_is_sqrt3_times_lg_base(self):
        # Mathematically: base_LL = nominal_kV * 1000
        #                 base_LG = nominal_kV * 1000 / sqrt(3)
        # So base_LL = base_LG * sqrt(3)
        nominal_ll_kv = 132.0
        profile_ll = _profile(voltage_base_kv=nominal_ll_kv, voltage_reference_mode="manual",
                               voltage_reference_override="line_to_line")
        profile_lg = _profile(voltage_base_kv=nominal_ll_kv, voltage_reference_mode="manual",
                               voltage_reference_override="line_to_ground")
        res_ll = resolve_per_unit(VOLTAGE, profile_ll, _volt_names_ll())
        res_lg = resolve_per_unit(VOLTAGE, profile_lg, _volt_names_lg())
        assert res_ll.status == STATUS_CONFIGURED
        assert res_lg.status == STATUS_CONFIGURED
        # Verify the sqrt(3) relationship between the two bases.
        ratio = res_ll.base_amount / res_lg.base_amount
        assert ratio == pytest.approx(_SQRT3, rel=1e-9)

    def test_c2c_auto_detection_ll_channels(self):
        nominal_ll_kv = 275.0
        expected_base_v = 275.0 * 1000.0
        profile = _profile(voltage_base_kv=nominal_ll_kv, voltage_reference_mode="auto")
        resolution = resolve_per_unit(VOLTAGE, profile, ["VAB", "VBC", "VCA"])
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)


# ===========================================================================
# CONTRACT C3 — DEC-049 Current PU: Direct base
# ===========================================================================


class TestC3CurrentDecDirect:
    """Governing formula: base_A = direct_base_kA * 1000
    PU = (measured * unit_scale_A) / base_A
    """

    def test_c3a_2ka_base_4000a_measured_gives_2pu(self):
        direct_base_ka = 2.0
        measured_a = 4000.0
        expected_base_a = 2.0 * 1000.0  # = 2000 A
        expected_pu = 4000.0 / 2000.0   # = 2.0

        profile = _profile(current_base_mode="direct", direct_current_ka=direct_base_ka)
        resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
        # Current resolution requires voltage reference to be known for derived mode,
        # but NOT for direct mode — direct base uses only direct_current_base_value.
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_a, rel=1e-9)
        assert convert_value_to_pu(measured_a, "A", resolution, CURRENT) == pytest.approx(expected_pu, rel=1e-9)

    def test_c3b_measured_in_ka_unit_normalized(self):
        direct_base_ka = 2.0
        measured_ka = 1.0
        expected_base_a = 2000.0
        expected_pu = (measured_ka * 1000.0) / expected_base_a  # 1000/2000 = 0.5

        profile = _profile(current_base_mode="direct", direct_current_ka=direct_base_ka)
        resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert convert_value_to_pu(measured_ka, "kA", resolution, CURRENT) == pytest.approx(expected_pu, rel=1e-9)

    def test_c3c_direct_base_independent_of_voltage_reference(self):
        # Slice 4 contract: direct current base is NOT affected by LG vs LL reference.
        direct_base_ka = 1.5
        measured_a = 1500.0
        expected_pu = 1500.0 / (1.5 * 1000.0)  # = 1.0

        for ref in ("line_to_ground", "line_to_line"):
            profile = _profile(
                voltage_base_kv=275.0, current_base_mode="direct", direct_current_ka=direct_base_ka,
                voltage_reference_mode="manual", voltage_reference_override=ref,
            )
            resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
            assert resolution.status == STATUS_CONFIGURED
            assert convert_value_to_pu(measured_a, "A", resolution, CURRENT) == pytest.approx(expected_pu, rel=1e-9)


# ===========================================================================
# CONTRACT C4 — DEC-049 Current PU: Derived (MVA / kV) base
# ===========================================================================


class TestC4CurrentDecDerived:
    """Governing formula (Slice 4 correction):
      Ibase_A = Sbase_MVA * 1e6 / (sqrt(3) * Vbase_LL_kV * 1000)
    Vbase_LL_kV is the nominal LL voltage, NOT adjusted for LG reference.
    """

    def test_c4a_1000mva_275kv_ibase_matches_formula(self):
        sbase_mva = 1000.0
        vbase_ll_kv = 275.0
        # Independent formula: I = S / (sqrt(3) * V)
        expected_ibase_a = (sbase_mva * 1e6) / (_SQRT3 * vbase_ll_kv * 1000.0)
        # Rounded to 4 sig figs: ≈ 2099.5 A
        assert expected_ibase_a == pytest.approx(2099.46, abs=0.01)  # sanity check

        profile = _profile(
            voltage_base_kv=vbase_ll_kv, current_base_mode="derived",
            apparent_power_mva=sbase_mva, voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_ibase_a, rel=1e-6)

    def test_c4b_derived_base_does_not_change_between_lg_and_ll_reference(self):
        # Slice 4 key rule: Vbase_LL is used directly in Ibase formula.
        # LG vs LL reference does NOT change the current base.
        sbase_mva = 500.0
        vbase_ll_kv = 132.0
        expected_ibase_a = (500.0 * 1e6) / (_SQRT3 * 132.0 * 1000.0)

        for ref in ("line_to_ground", "line_to_line"):
            profile = _profile(
                voltage_base_kv=vbase_ll_kv, current_base_mode="derived",
                apparent_power_mva=sbase_mva, voltage_reference_mode="manual",
                voltage_reference_override=ref,
            )
            resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
            assert resolution.status == STATUS_CONFIGURED
            assert resolution.base_amount == pytest.approx(expected_ibase_a, rel=1e-9), \
                f"ref={ref}: current base should be reference-independent"

    def test_c4c_1000mva_275kv_measured_at_full_load_is_1pu(self):
        sbase_mva = 1000.0
        vbase_ll_kv = 275.0
        ibase_a = (1000.0 * 1e6) / (_SQRT3 * 275.0 * 1000.0)
        expected_pu = 1.0

        profile = _profile(
            voltage_base_kv=vbase_ll_kv, current_base_mode="derived",
            apparent_power_mva=sbase_mva, voltage_reference_mode="manual",
            voltage_reference_override="line_to_ground",
        )
        resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
        assert resolution.status == STATUS_CONFIGURED
        assert convert_value_to_pu(ibase_a, "A", resolution, CURRENT) == pytest.approx(expected_pu, rel=1e-9)


# ===========================================================================
# CONTRACT C5 — DEC-050 Group-aware Voltage PU (MG resolver)
# ===========================================================================


class TestC5VoltageGroupAwareLG:
    """The MG resolver uses the SAME formula as DEC-049:
      base_V = nominal_ll_kv * 1000 / sqrt(3)
    but authority comes from VoltageBaseConfiguration, not PerUnitBaseProfile.
    """

    def _make_registries(self, nominal_ll_kv: float, ref_override: str | None = None):
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source(
            [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        ))
        group_registry = MeasurementGroupRegistry()
        group_registry.add(_make_mg())
        voltage_config_registry = VoltageGroupConfigRegistry()
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=nominal_ll_kv,
            reference_mode="manual" if ref_override else "auto",
            reference_override=ref_override,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
        )
        current_config_registry = CurrentGroupConfigRegistry()
        return source_registry, group_registry, voltage_config_registry, current_config_registry

    def test_c5a_mg_base_lg_275kv_matches_independent_formula(self):
        expected_base_v = 275.0 * 1000.0 / _SQRT3  # 158,771.3 V

        _, group_registry, voltage_config_registry, current_config_registry = self._make_registries(275.0, "line_to_ground")
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)

    def test_c5b_mg_base_lg_132kv_measured_phase_gives_1pu(self):
        nominal_ll_kv = 132.0
        measured_kv = 132.0 / _SQRT3                      # 1 pu phase voltage
        expected_base_v = 132.0 * 1000.0 / _SQRT3
        expected_pu = 1.0

        _, group_registry, voltage_config_registry, current_config_registry = self._make_registries(132.0, "line_to_ground")
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
        resolution = resolve_conversion_eligibility(resolution, "kV", VOLTAGE)
        assert convert_value_to_pu(measured_kv, "kV", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c5c_mg_base_ll_275kv_matches_independent_formula(self):
        expected_base_v = 275.0 * 1000.0  # 275,000 V

        _, group_registry, voltage_config_registry, current_config_registry = self._make_registries(275.0, "line_to_line")
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)

    def test_c5d_mg_base_sqrt3_ratio_between_ll_and_lg(self):
        _, grp_lg, vcfg_lg, ccfg_lg = self._make_registries(275.0, "line_to_ground")
        _, grp_ll, vcfg_ll, ccfg_ll = self._make_registries(275.0, "line_to_line")

        res_lg = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR", engineering_type=VOLTAGE,
            group_registry=grp_lg, voltage_config_registry=vcfg_lg, current_config_registry=ccfg_lg,
        )
        res_ll = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR", engineering_type=VOLTAGE,
            group_registry=grp_ll, voltage_config_registry=vcfg_ll, current_config_registry=ccfg_ll,
        )
        assert res_ll.base_amount / res_lg.base_amount == pytest.approx(_SQRT3, rel=1e-9)


# ===========================================================================
# CONTRACT C6 — DEC-050 Group-aware Current PU: Equipment rating
# ===========================================================================


class TestC6CurrentGroupAwareEquipmentRating:
    """Equipment rating uses the SAME formula as DEC-049 derived mode:
      Ibase_A = Sbase_MVA * 1e6 / (sqrt(3) * Vbase_LL_V)
    Vbase_LL_V comes from the LINKED Voltage group's nominal_voltage_ll_kv.
    """

    def _make_equipment_rating_registries(self, sbase_mva: float, vbase_ll_kv: float):
        source_registry = WorkspaceRegistry()
        channels = [
            _channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE),
            _channel("IR", CURRENT), _channel("IY", CURRENT), _channel("IB", CURRENT),
        ]
        source_registry.add(_active_source(channels))

        group_registry = MeasurementGroupRegistry()
        group_registry.add(_make_mg(group_id="mg-v1", names=["VR", "VY", "VB"]))
        group_registry.add(_make_mg(kind=KIND_CURRENT, group_id="mg-i1", names=["IR", "IY", "IB"]))

        voltage_config_registry = VoltageGroupConfigRegistry()
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=vbase_ll_kv,
            reference_mode="manual", reference_override="line_to_ground",
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )

        current_config_registry = CurrentGroupConfigRegistry()
        set_current_base_equipment_rating(
            workspace_id=WS, measurement_group_id="mg-i1",
            equipment_rating_mva=sbase_mva,
            linked_voltage_group_id="mg-v1",
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        return group_registry, voltage_config_registry, current_config_registry

    def test_c6a_1000mva_275kv_ibase_matches_independent_formula(self):
        sbase_mva = 1000.0
        vbase_ll_kv = 275.0
        # Independent formula — same as C4 (formula is shared):
        expected_ibase_a = (1000.0 * 1e6) / (_SQRT3 * 275.0 * 1000.0)
        # ≈ 2099.46 A

        group_registry, voltage_config_registry, current_config_registry = self._make_equipment_rating_registries(
            sbase_mva, vbase_ll_kv
        )
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="IR",
            engineering_type=CURRENT,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_ibase_a, rel=1e-6)

    def test_c6b_mg_equipment_rating_matches_dec049_derived(self):
        sbase_mva = 500.0
        vbase_ll_kv = 132.0
        expected_ibase_a = (500.0 * 1e6) / (_SQRT3 * 132.0 * 1000.0)

        group_registry, voltage_config_registry, current_config_registry = self._make_equipment_rating_registries(
            sbase_mva, vbase_ll_kv
        )
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="IR",
            engineering_type=CURRENT,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_ibase_a, rel=1e-9)


# ===========================================================================
# CONTRACT C7 — Slice 5D-1 Secondary voltage path
# ===========================================================================


class TestC7VoltageSecondaryPath:
    """Governing formula:
      LG: base_V = secondary_voltage_ll_v / sqrt(3)
      LL: base_V = secondary_voltage_ll_v
    """

    def _make_secondary_registries(self, secondary_voltage_ll_v: float, ref_override: str):
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source([_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]))
        group_registry = MeasurementGroupRegistry()
        group_registry.add(_make_mg())
        voltage_config_registry = VoltageGroupConfigRegistry()
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=275.0,            # primary nominal (not used as denominator here)
            base_reference_side="secondary",
            secondary_voltage_ll_v=secondary_voltage_ll_v,
            reference_mode="manual", reference_override=ref_override,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
        )
        current_config_registry = CurrentGroupConfigRegistry()
        return group_registry, voltage_config_registry, current_config_registry

    def test_c7a_secondary_1000v_ll_lg_base_v_over_sqrt3(self):
        secondary_ll_v = 1000.0
        expected_base_v = 1000.0 / _SQRT3  # ≈ 577.35 V

        group_registry, voltage_config_registry, current_config_registry = self._make_secondary_registries(
            secondary_ll_v, "line_to_ground"
        )
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)

    def test_c7b_secondary_phase_voltage_gives_1pu(self):
        secondary_ll_v = 1000.0
        measured_v = 1000.0 / _SQRT3   # phase voltage = 1 pu
        expected_pu = 1.0

        group_registry, voltage_config_registry, current_config_registry = self._make_secondary_registries(
            secondary_ll_v, "line_to_ground"
        )
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        resolution = resolve_conversion_eligibility(resolution, "V", VOLTAGE)
        assert convert_value_to_pu(measured_v, "V", resolution, VOLTAGE) == pytest.approx(expected_pu, rel=1e-9)

    def test_c7c_secondary_ll_base_is_secondary_voltage_itself(self):
        secondary_ll_v = 2000.0
        expected_base_v = 2000.0  # LL: base = secondary_ll_v directly

        group_registry, voltage_config_registry, current_config_registry = self._make_secondary_registries(
            secondary_ll_v, "line_to_line"
        )
        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)


# ===========================================================================
# CONTRACT C8 — Eligibility invariants
# ===========================================================================


class TestC8EligibilityInvariants:
    """Profile/status conditions that block PU conversion never produce a
    base_amount that could mislead the caller into performing wrong math."""

    def test_no_voltage_base_configured_is_base_required(self):
        profile = _profile(voltage_base_kv=None)
        resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.base_amount is None

    def test_no_current_base_configured_is_base_required(self):
        profile = _profile(current_base_mode="none")
        resolution = resolve_per_unit(CURRENT, profile, _volt_names_lg())
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.base_amount is None

    def test_no_profile_is_base_required(self):
        resolution = resolve_per_unit(VOLTAGE, None, _volt_names_lg())
        assert resolution.status == STATUS_BASE_REQUIRED

    def test_other_engineering_type_is_not_applicable(self):
        profile = _profile(voltage_base_kv=275.0)
        for etype in ("Power", "Frequency", "Undefined"):
            resolution = resolve_per_unit(etype, profile, _volt_names_lg())
            assert resolution.status == STATUS_NOT_APPLICABLE

    def test_reference_undetermined_blocks_voltage_pu(self):
        profile = _profile(voltage_base_kv=275.0, voltage_reference_mode="auto")
        # No recognizable channel names → undetermined reference
        resolution = resolve_per_unit(VOLTAGE, profile, ["UNKNOWN_A", "UNKNOWN_B"])
        assert resolution.status == STATUS_BASE_REQUIRED
        assert resolution.reason == "voltage_reference_undetermined"

    def test_configured_resolution_base_is_positive_finite(self):
        for nominal in (0.001, 1.0, 100.0, 275.0, 400.0, 1000.0):
            profile = _profile(
                voltage_base_kv=nominal,
                voltage_reference_mode="manual", voltage_reference_override="line_to_ground",
            )
            resolution = resolve_per_unit(VOLTAGE, profile, _volt_names_lg())
            assert resolution.status == STATUS_CONFIGURED
            assert resolution.base_amount is not None
            assert math.isfinite(resolution.base_amount)
            assert resolution.base_amount > 0


# ===========================================================================
# CONTRACT C9 — DEC-049/DEC-050 coexistence (DEC-051)
# ===========================================================================


class TestC9CoexistencePrecedence:
    """Grouped channel uses MG authority; ungrouped falls through to SD.
    A grouped channel never silently borrows the source-wide SD base."""

    def test_grouped_voltage_channel_uses_mg_base_not_sd(self):
        # MG configured at 132 kV; SD configured at 275 kV.
        # Grouped channel must resolve to 132 kV (MG), NOT 275 kV (SD).
        mg_kv = 132.0
        sd_kv = 275.0

        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source(
            [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        ))
        group_registry = MeasurementGroupRegistry()
        group_registry.add(_make_mg())
        voltage_config_registry = VoltageGroupConfigRegistry()
        update_voltage_configuration(
            workspace_id=WS, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=mg_kv,
            reference_mode="manual", reference_override="line_to_ground",
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        current_config_registry = CurrentGroupConfigRegistry()

        expected_mg_base_v = mg_kv * 1000.0 / _SQRT3    # MG-derived (132 kV)
        expected_sd_base_v = sd_kv * 1000.0 / _SQRT3    # SD-derived (275 kV)

        resolution = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert resolution is not None
        assert resolution.base_amount == pytest.approx(expected_mg_base_v, rel=1e-9)
        assert resolution.base_amount != pytest.approx(expected_sd_base_v, rel=1e-9)

    def test_ungrouped_voltage_channel_returns_none_from_mg_resolver(self):
        # An ungrouped channel returns None from resolve_group_aware_per_unit().
        # The caller must then use the DEC-049 SD path.
        empty_group_registry = MeasurementGroupRegistry()  # no groups
        voltage_config_registry = VoltageGroupConfigRegistry()
        current_config_registry = CurrentGroupConfigRegistry()

        result = resolve_group_aware_per_unit(
            workspace_id=WS, source_id=SRC, channel_name="VR",
            engineering_type=VOLTAGE,
            group_registry=empty_group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
        )
        assert result is None, "ungrouped channel must return None, never a fabricated base"


# ===========================================================================
# CONTRACT C10 — Calculated channel PU inheritance
# ===========================================================================


class TestC10CalculatedChannelInheritance:
    """Group-aware calculated channels inherit the group's base, not any
    SD profile.  The fix (PU-SSOT-001 F3) ensures the reference-side
    authority also comes from the MG voltage config, not the SD profile."""

    def _calc_registries(self, nominal_kv: float, ref_override: str):
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source(
            [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        ))
        group_registry = MeasurementGroupRegistry()
        group_registry.add(_make_mg(ws=_C10_WS, src=_C10_SRC))
        voltage_config_registry = VoltageGroupConfigRegistry()
        update_voltage_configuration(
            workspace_id=_C10_WS, measurement_group_id="mg-v1",
            nominal_voltage_ll_kv=nominal_kv,
            reference_mode="manual", reference_override=ref_override,
            group_registry=group_registry, voltage_config_registry=voltage_config_registry,
        )
        current_config_registry = CurrentGroupConfigRegistry()
        import datetime as _dt
        calc_registry = CalculatedChannelRegistry()
        calc = CalculatedChannel(
            id="calc-neg-vr", workspace_id=_C10_WS, name="calc-neg-vr", unit="kV",
            operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id=_C10_SRC, channel_name="VR")],
            parameters={}, dependency_ids=[],
            reference_source_id=_C10_SRC,
            time=np.array([0.0, 0.1, 0.2], dtype=float),
            values=np.array([100.0, 100.0, 100.0], dtype=float),
            created_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc),
            engineering_type=VOLTAGE,
        )
        calc_registry.add(calc)
        return calc, source_registry, group_registry, voltage_config_registry, current_config_registry, calc_registry

    def test_c10a_inherited_base_equals_mg_base_not_sd(self):
        # MG at 275 kV LG → base = 275000/sqrt(3) V
        expected_base_v = 275.0 * 1000.0 / _SQRT3
        # SD profile at a DIFFERENT nominal:
        profile = _profile(source_id=_C10_SRC, voltage_base_kv=132.0, voltage_reference_mode="manual",
                           voltage_reference_override="line_to_ground")

        calc, _, grp, vcfg, ccfg, calc_reg = self._calc_registries(275.0, "line_to_ground")
        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source(
            [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        ))
        resolution = _resolve_effective_per_unit_for_calculated_channel(
            calc, profile, ["VR", "VY", "VB"],
            workspace_id=_C10_WS,
            source_registry=source_registry,
            calc_registry=calc_reg,
            group_registry=grp,
            voltage_config_registry=vcfg,
            current_config_registry=ccfg,
            per_unit_registry=None,
        )
        assert resolution.status == STATUS_CONFIGURED
        # The base must come from the MG (275 kV), NOT from the SD profile (132 kV).
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
        assert resolution.base_amount != pytest.approx(132.0 * 1000.0 / _SQRT3, rel=1e-3)

    def test_c10b_sd_fallback_base_used_when_no_group(self):
        # No MG → SD profile provides the base
        expected_base_v = 275.0 * 1000.0 / _SQRT3
        profile = _profile(source_id=_C10_SRC, voltage_base_kv=275.0, voltage_reference_mode="manual",
                           voltage_reference_override="line_to_ground")

        import datetime as _dt
        calc = CalculatedChannel(
            id="calc-neg-vr", workspace_id=_C10_WS, name="calc-neg-vr", unit="kV",
            operation=OP_REVERSE_POLARITY,
            inputs=[ChannelRef(kind="source", source_id=_C10_SRC, channel_name="VR")],
            parameters={}, dependency_ids=[],
            reference_source_id=_C10_SRC,
            time=np.array([0.0, 0.1], dtype=float),
            values=np.array([100.0, 100.0], dtype=float),
            created_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc),
            engineering_type=VOLTAGE,
        )
        calc_registry = CalculatedChannelRegistry()
        calc_registry.add(calc)

        source_registry = WorkspaceRegistry()
        source_registry.add(_active_source(
            [_channel("VR", VOLTAGE), _channel("VY", VOLTAGE), _channel("VB", VOLTAGE)]
        ))
        empty_group_registry = MeasurementGroupRegistry()
        voltage_config_registry = VoltageGroupConfigRegistry()
        current_config_registry = CurrentGroupConfigRegistry()

        resolution = _resolve_effective_per_unit_for_calculated_channel(
            calc, profile, ["VR", "VY", "VB"],
            workspace_id=_C10_WS,
            source_registry=source_registry,
            calc_registry=calc_registry,
            group_registry=empty_group_registry,
            voltage_config_registry=voltage_config_registry,
            current_config_registry=current_config_registry,
            per_unit_registry=None,
        )
        assert resolution.status == STATUS_CONFIGURED
        assert resolution.base_amount == pytest.approx(expected_base_v, rel=1e-9)
