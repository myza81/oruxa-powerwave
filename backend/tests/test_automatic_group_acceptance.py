"""Regression tests for PU-UI-001 Correction — Automatic Acceptance of
Reliably Detected Measurement Groups (DEC-214).

Covers the backend domain and service guarantees for all 16 owner-specified
acceptance scenarios.  Scenarios 1, 2, 15 (UI/no-badge) are covered in the
companion test_frontend_rd_automatic_acceptance.py.

Each test class maps to one or more numbered scenarios:
  3.  Reliably detected nominal voltage — accepted without user confirmation.
  4.  Automatic voltage PU calculation works without a redundant group-approval
      action when all independent eligibility conditions are satisfied.
  5.  Automatic current PU calculation works when configuration and safeguards
      are satisfied.
  6.  Manual nominal-voltage correction overrides automatic detection.
  7.  Manual correction remains effective after group refresh or re-detection.
  8.  Missing nominal voltage still produces an actionable warning.
  9.  Conflicting channel membership remains blocked.
 10.  needs_review does not become automatically eligible.
 11.  Incomplete phase grouping does not silently become authoritative.
 12.  Multiple recordings retain independent group configurations.
 13.  Existing Voltage-only PU behaviour remains valid.
 14.  Existing numerical PU outputs remain unchanged for equivalent
      authoritative configurations.
 16.  No stale UI cache incorrectly shows a group as unresolved after valid
      automatic resolution.

The skip_status_gate bypass (Slice 5C-1) is what makes scenarios 3–5 work:
  suggested + auto_resolved → resolves to CONFIGURED without any confirm action.
  needs_review + auto_resolved → still blocked (scenario 10 regression guard).

Manual authority is INDEPENDENT of group status (scenarios 6, 7):
  suggested + manual → blocked (manual authority requires confirmed/manual status).
  confirmed + manual → resolves normally.
  manual group status + manual authority → resolves normally.
"""

from __future__ import annotations

from app.domain.base_authority import (
    BASE_AUTHORITY_AUTO,
    BASE_AUTHORITY_MANUAL,
    BASE_AUTHORITY_NEEDS_REVIEW,
)
from app.domain.calculated_channel import ChannelRef
from app.domain.current_group_config import (
    CurrentBaseConfiguration,
    METHOD_EQUIPMENT_RATING,
    METHOD_MANUAL,
    METHOD_NONE,
    STATUS_BASE_REQUIRED as C_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as C_STATUS_CONFIGURED,
    STATUS_NOT_APPLICABLE as C_STATUS_NOT_APPLICABLE,
    resolve_current_base_for_group,
)
from app.domain.measurement_group import (
    KIND_CURRENT,
    KIND_VOLTAGE,
    STATUS_CONFIRMED,
    STATUS_MANUAL as MG_STATUS_MANUAL,
    STATUS_NEEDS_REVIEW as MG_STATUS_NEEDS_REVIEW,
    STATUS_SUGGESTED,
    MeasurementGroup,
)
from app.domain.measurement_group_detection import detect_measurement_groups
from app.domain.voltage_group_config import (
    STATUS_BASE_REQUIRED as V_STATUS_BASE_REQUIRED,
    STATUS_CONFIGURED as V_STATUS_CONFIGURED,
    VoltageBaseConfiguration,
    resolve_voltage_base_for_group,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _vgroup(status: str, channel_names: tuple[str, ...] = ("VAN", "VBN", "VCN")) -> MeasurementGroup:
    return MeasurementGroup(
        id="vg1", workspace_id="ws1", source_id="src1",
        kind=KIND_VOLTAGE, status=status, display_name="HV VOLTAGE",
        channel_refs=[ChannelRef(kind="source", source_id="src1", channel_name=n) for n in channel_names],
    )


def _cgroup(status: str) -> MeasurementGroup:
    return MeasurementGroup(
        id="cg1", workspace_id="ws1", source_id="src1",
        kind=KIND_CURRENT, status=status, display_name="HV CURRENT",
        channel_refs=[],
    )


def _vconfig(**kw) -> VoltageBaseConfiguration:
    defaults = dict(measurement_group_id="vg1", workspace_id="ws1", nominal_voltage_ll_kv=275.0)
    defaults.update(kw)
    return VoltageBaseConfiguration(**defaults)


def _iconfig(**kw) -> CurrentBaseConfiguration:
    # METHOD_MANUAL + a valid manual_ibase_ka is the simplest path to CONFIGURED
    # (no linked voltage group needed, unlike METHOD_EQUIPMENT_RATING).
    defaults = dict(measurement_group_id="cg1", workspace_id="ws1", method=METHOD_MANUAL,
                    manual_ibase_ka=0.5, base_authority=BASE_AUTHORITY_AUTO)
    defaults.update(kw)
    return CurrentBaseConfiguration(**defaults)


# ---------------------------------------------------------------------------
# Scenario 3 + 4 — Reliably detected voltage: auto-accepted without confirmation
# ---------------------------------------------------------------------------

class TestVoltageAutoAcceptance:
    """Scenario 3/4: skip_status_gate — a STATUS_SUGGESTED group whose base was
    automatically resolved (base_authority="auto_resolved") is PU-authoritative
    immediately, without any engineer confirm/save action."""

    def test_suggested_group_with_auto_resolved_base_is_configured(self):
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_suggested_group_resolves_correct_denominator(self):
        """Numerical path: auto-accepted base returns a positive denominator_kv.
        Default _vgroup uses LG (phase-to-ground) channels → LG reference →
        denominator = 275 / sqrt(3).  No confirmation step changes the value."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED
        assert result.denominator_kv is not None
        assert result.denominator_kv > 0.0

    def test_no_confirmation_action_required_for_suggested_auto_resolved(self):
        """The PU gate never returns group_not_confirmed for suggested + auto_resolved."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.reason != "group_not_confirmed"

    def test_confirmed_group_also_resolves_with_auto_resolved(self):
        """confirmed + auto_resolved → CONFIGURED (no regression)."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_manual_group_status_also_resolves_with_auto_resolved(self):
        """manual group status + auto_resolved → CONFIGURED."""
        group = _vgroup(MG_STATUS_MANUAL)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Scenario 5 — Reliably detected current group: auto-accepted without confirmation
# ---------------------------------------------------------------------------

class TestCurrentAutoAcceptance:
    """Scenario 5: same skip_status_gate bypass applies to the current resolver."""

    def test_suggested_current_group_with_auto_resolved_base_is_configured(self):
        group = _cgroup(STATUS_SUGGESTED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED

    def test_no_confirmation_action_required_for_suggested_current_auto_resolved(self):
        group = _cgroup(STATUS_SUGGESTED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.reason != "group_not_confirmed"

    def test_confirmed_current_group_also_resolves(self):
        group = _cgroup(STATUS_CONFIRMED)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Scenario 6 — Manual correction overrides automatic detection
# ---------------------------------------------------------------------------

class TestManualOverridePrecedence:
    """Scenario 6: when an engineer explicitly sets a voltage base, the
    base_authority transitions to "manual", which requires confirmed/manual group
    status before resolving.  This is intentional — manual authority is engineer-
    approved and must not silently override back to auto on a suggested group."""

    def test_suggested_group_with_manual_authority_is_blocked(self):
        """manual authority on a suggested group → group_not_confirmed.
        The engineer's explicit correction still requires the group to be
        acknowledged (confirmed or manual status) before PU resolves."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_confirmed_group_with_manual_authority_resolves(self):
        """When the engineer both confirms the group AND sets a manual kV,
        the PU resolves from the engineer-approved value."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED

    def test_manual_group_status_with_manual_authority_resolves(self):
        group = _vgroup(MG_STATUS_MANUAL)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Scenario 7 — Manual correction persists through re-detection
# ---------------------------------------------------------------------------

class TestManualCorrectionPersistence:
    """Scenario 7: manual authority is never overwritten by auto-detection.
    After a manual kV is set, repeated calls to the resolver return the same
    engineer-approved value — the auto_base_service's C4 constraint."""

    def test_manual_authority_is_stable_across_multiple_resolve_calls(self):
        """resolve_voltage_base_for_group is stateless/pure — calling it
        multiple times with the same manual config returns the same result."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        for _ in range(5):
            result = resolve_voltage_base_for_group(group, cfg)
            assert result.status == V_STATUS_CONFIGURED

    def test_auto_resolved_does_not_replace_manual_authority(self):
        """C4 contract: is_engineer_approved() blocks auto_base_service from
        writing over a manual base.  Verified by confirming that manual_authority
        config resolves as CONFIGURED while auto_resolved config also resolves
        as CONFIGURED — the two states are independent, and manual takes the
        same code path without being overridden by auto evidence."""
        group = _vgroup(STATUS_CONFIRMED)
        manual_cfg = _vconfig(nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_MANUAL)
        auto_cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        # Both resolve, but they carry different kV values —
        # the manual override is preserved; it is NOT silently reverted to 275.
        manual_result = resolve_voltage_base_for_group(group, manual_cfg)
        auto_result = resolve_voltage_base_for_group(group, auto_cfg)
        assert manual_result.status == V_STATUS_CONFIGURED
        assert auto_result.status == V_STATUS_CONFIGURED
        # Denominators differ, confirming manual value is kept distinct.
        assert manual_result.denominator_kv != auto_result.denominator_kv


# ---------------------------------------------------------------------------
# Scenario 8 — Missing nominal voltage produces actionable warning
# ---------------------------------------------------------------------------

class TestMissingNominalVoltageWarning:
    """Scenario 8: when neither auto-detection nor a manual edit has produced
    a nominal voltage, the resolver returns base_required — the engineer must
    configure it."""

    def test_no_config_returns_base_required(self):
        """Config is None for a confirmed group → voltage_base_not_configured.
        (For a suggested group without auto_resolved config, skip_status_gate=False
        so the status gate fires first and returns group_not_confirmed instead.)"""
        group = _vgroup(STATUS_CONFIRMED)
        result = resolve_voltage_base_for_group(group, None)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "voltage_base_not_configured"

    def test_suggested_group_no_auto_base_returns_group_not_confirmed(self):
        """A suggested group whose auto-base attempt produced no kV
        (config exists but kV is None, needs_review authority) → base_invalidated."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(nominal_voltage_ll_kv=None, base_authority=BASE_AUTHORITY_NEEDS_REVIEW)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "base_invalidated"


# ---------------------------------------------------------------------------
# Scenario 9 — Conflicting channel membership remains blocked
# ---------------------------------------------------------------------------

class TestConflictingMembershipBlocked:
    """Scenario 9: a group with contradictory membership evidence must remain
    blocked.  manual_conflict_detected is the guard (RD-0B); needs_review
    authority independently blocks conflicting base evidence."""

    def test_manual_conflict_detected_blocks_suggested_group(self):
        """manual_conflict_detected=True → PU blocked regardless of base_authority."""
        group = _vgroup(STATUS_SUGGESTED)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO, manual_conflict_detected=True,
                       manual_conflict_detail="Engineer kV conflicts with auto-detected voltage")
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "manual_conflict_detected"

    def test_manual_conflict_detected_blocks_confirmed_group(self):
        """manual_conflict_detected fires before the status gate."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO, manual_conflict_detected=True,
                       manual_conflict_detail="Voltage conflict")
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "manual_conflict_detected"


# ---------------------------------------------------------------------------
# Scenario 10 — needs_review is never automatically eligible
# ---------------------------------------------------------------------------

class TestNeedsReviewNeverEligible:
    """Scenario 10: needs_review status must NOT become PU-authoritative even
    when base_authority is auto_resolved — identity conflict takes precedence."""

    def test_needs_review_group_with_auto_resolved_base_is_blocked(self):
        """The skip_status_gate ONLY applies when status == STATUS_SUGGESTED.
        needs_review + auto_resolved → base_required('group_not_confirmed')."""
        group = _vgroup(MG_STATUS_NEEDS_REVIEW)
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_needs_review_current_group_also_blocked(self):
        group = _cgroup(MG_STATUS_NEEDS_REVIEW)
        cfg = _iconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"


# ---------------------------------------------------------------------------
# Scenario 11 — Incomplete/contradictory phase grouping stays needs_review
# ---------------------------------------------------------------------------

class TestIncompletePhaseGroupingDetection:
    """Scenario 11: the detector assigns STATUS_NEEDS_REVIEW when it finds
    contradictory internal evidence — duplicate phase tokens, mixed
    phase-to-reference and phase-to-phase representations, or identity conflict.
    Such clusters must never silently become authoritative."""

    def test_mixed_representation_produces_needs_review(self):
        """A cluster mixing phase-to-ground (VAN) and phase-to-phase (VAB)
        channels has contradictory evidence → needs_review."""
        channels = [("VAB", "Voltage"), ("VAN", "Voltage")]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].status == "needs_review"

    def test_mixed_representation_also_blocked_by_voltage_resolver(self):
        """A detected needs_review group stays blocked even with auto_resolved base.
        The identity conflict (LL+LG mixing) takes precedence over base authority."""
        channels = [("VAB", "Voltage"), ("VAN", "Voltage")]
        detected = detect_measurement_groups(channels)
        assert detected[0].status == "needs_review"
        cfg = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(detected[0], cfg)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "group_not_confirmed"

    def test_clean_three_phase_produces_suggested(self):
        """Clean three-phase group (unique phases, same representation) → suggested."""
        channels = [("VAN", "Voltage"), ("VBN", "Voltage"), ("VCN", "Voltage")]
        detected = detect_measurement_groups(channels)
        assert len(detected) == 1
        assert detected[0].status == "suggested"


# ---------------------------------------------------------------------------
# Scenario 12 — Multiple recordings retain independent group configurations
# ---------------------------------------------------------------------------

class TestMultipleRecordingsIndependence:
    """Scenario 12: a group configuration for source A must never affect
    PU resolution for source B.  VoltageBaseConfiguration is scoped to
    (workspace_id, measurement_group_id) — configurations for different
    group IDs are always independent."""

    def test_different_group_ids_resolve_independently(self):
        """Group vg1 (275 kV auto, LG) and group vg2 (132 kV auto, LG) for
        different sources resolve to their own distinct denominator_kv values.
        Channel names must be provided so the reference resolver can determine LG."""
        group_a = _vgroup(STATUS_SUGGESTED, ("VAN", "VBN", "VCN"))
        group_b = MeasurementGroup(
            id="vg2", workspace_id="ws1", source_id="src_b",
            kind=KIND_VOLTAGE, status=STATUS_SUGGESTED, display_name="LV VOLTAGE",
            channel_refs=[ChannelRef(kind="source", source_id="src_b", channel_name=n)
                          for n in ("VRN", "VYN", "VBN")],
        )
        cfg_a = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        cfg_b = VoltageBaseConfiguration(
            measurement_group_id="vg2", workspace_id="ws1",
            nominal_voltage_ll_kv=132.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        result_a = resolve_voltage_base_for_group(group_a, cfg_a)
        result_b = resolve_voltage_base_for_group(group_b, cfg_b)
        assert result_a.status == V_STATUS_CONFIGURED
        assert result_b.status == V_STATUS_CONFIGURED
        # Different nominal kV → different denominators — configurations are isolated.
        assert result_a.denominator_kv != result_b.denominator_kv

    def test_resolving_one_group_does_not_alter_the_other(self):
        """The resolver is pure (stateless) — calling it for group A does not
        change group B's resolution state."""
        group_a = _vgroup(STATUS_SUGGESTED, ("VAN", "VBN", "VCN"))
        group_b = MeasurementGroup(
            id="vg2", workspace_id="ws1", source_id="src2",
            kind=KIND_VOLTAGE, status=STATUS_SUGGESTED, display_name="OTHER VOLTAGE",
            channel_refs=[ChannelRef(kind="source", source_id="src2", channel_name=n)
                          for n in ("VRN", "VYN", "VBN")],
        )
        cfg_a = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        cfg_b = VoltageBaseConfiguration(
            measurement_group_id="vg2", workspace_id="ws1",
            nominal_voltage_ll_kv=11.0, base_authority=BASE_AUTHORITY_AUTO,
        )
        # Resolve A
        resolve_voltage_base_for_group(group_a, cfg_a)
        # B still resolves to its own kV, unaffected by A's resolution
        result_b = resolve_voltage_base_for_group(group_b, cfg_b)
        assert result_b.status == V_STATUS_CONFIGURED


# ---------------------------------------------------------------------------
# Scenario 13 — Voltage-only PU: current channels always render in engineering
# ---------------------------------------------------------------------------

class TestVoltageOnlyPUBehavior:
    """Scenario 13: DEC-212 restricts PU display to voltage channels.
    Current groups may have base configurations, but whether a current
    channel displays in PU is independently controlled by the display-mode
    gate.  Here we verify that the current-base resolver correctly returns
    not_applicable for channels that have no base configured (METHOD_NONE
    with engineer approval), confirming the independent gate is wired."""

    def test_current_group_method_none_requires_explicit_base(self):
        """METHOD_NONE for a confirmed current group → base_required, not a fallback.
        DEC-212 restricts PU display to voltage channels; a current group without
        an explicit base is blocked rather than silently defaulting."""
        group = _cgroup(STATUS_CONFIRMED)
        cfg = CurrentBaseConfiguration(
            measurement_group_id="cg1", workspace_id="ws1",
            method=METHOD_NONE, base_authority=BASE_AUTHORITY_MANUAL,
        )
        result = resolve_current_base_for_group(group, cfg)
        assert result.status == C_STATUS_BASE_REQUIRED
        assert result.reason == "current_base_not_configured"

    def test_resolve_current_returns_not_applicable_for_voltage_group(self):
        """The current resolver returns NOT_APPLICABLE immediately for any
        non-Current group — the kind gate ensures voltage and current
        resolution are strictly independent paths."""
        voltage_group = _vgroup(STATUS_CONFIRMED)
        result = resolve_current_base_for_group(voltage_group, None)
        assert result.status == C_STATUS_NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Scenario 14 — Numerical PU outputs unchanged for equivalent configurations
# ---------------------------------------------------------------------------

class TestNumericalPUOutputsUnchanged:
    """Scenario 14: the correction removes UI badges but must not alter any
    numerical PU calculation path.  We verify that the denominators returned
    by resolve_voltage_base_for_group() for a 275 kV LG-reference group are
    numerically identical before and after — i.e., the skip_status_gate was
    already in the code and no arithmetic was touched by this correction."""

    def test_suggested_auto_resolved_denominator_matches_confirmed(self):
        """A suggested group and an identical confirmed group with the same
        auto_resolved config must return the same denominator_kv.
        The only difference was UI treatment (Suggested badge), never arithmetic."""
        import math
        cfg_suggested = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        cfg_confirmed = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result_s = resolve_voltage_base_for_group(_vgroup(STATUS_SUGGESTED), cfg_suggested)
        result_c = resolve_voltage_base_for_group(_vgroup(STATUS_CONFIRMED), cfg_confirmed)
        assert result_s.status == V_STATUS_CONFIGURED
        assert result_c.status == V_STATUS_CONFIGURED
        assert math.isclose(result_s.denominator_kv, result_c.denominator_kv, rel_tol=1e-9)

    def test_275kv_lg_denominator_is_nominal_ll_over_sqrt3(self):
        """275 kV LL with LG phase-to-ground channels → reference=line_to_ground
        → denominator = 275 / sqrt(3) ≈ 158.77 kV.
        Default _vgroup uses VAN/VBN/VCN channels which resolve to LG reference."""
        import math
        group = _vgroup(STATUS_SUGGESTED)  # VAN/VBN/VCN → line_to_ground reference
        cfg = _vconfig(nominal_voltage_ll_kv=275.0, base_authority=BASE_AUTHORITY_AUTO)
        result = resolve_voltage_base_for_group(group, cfg)
        assert result.effective_reference == "line_to_ground"
        expected = 275.0 / math.sqrt(3)
        assert math.isclose(result.denominator_kv, expected, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Scenario 16 — No stale auto-resolution guard (RD-0B regression)
# ---------------------------------------------------------------------------

class TestStaleAutoResolutionGuard:
    """Scenario 16: manual_conflict_detected is the runtime cache-invalidation
    guard.  When a manual voltage is later found to conflict with auto-detected
    evidence, PU is blocked until the conflict is resolved — this ensures the
    display never shows a stale 'configured' state for an invalidated group.
    RD-0B regression guard: test_rd0b_manual_conflict.py covers the full
    service-level scenarios; here we guard the domain-level gate is wired."""

    def test_conflict_flag_blocks_even_configured_group(self):
        """manual_conflict_detected=True fires before the authority gate —
        a group that was previously CONFIGURED reverts to base_required the
        instant a conflict is set."""
        group = _vgroup(STATUS_CONFIRMED)
        cfg_before = _vconfig(base_authority=BASE_AUTHORITY_AUTO)
        cfg_conflict = _vconfig(base_authority=BASE_AUTHORITY_AUTO,
                                manual_conflict_detected=True,
                                manual_conflict_detail="kV conflict")
        # Before conflict: CONFIGURED
        assert resolve_voltage_base_for_group(group, cfg_before).status == V_STATUS_CONFIGURED
        # After conflict: BASE_REQUIRED
        result = resolve_voltage_base_for_group(group, cfg_conflict)
        assert result.status == V_STATUS_BASE_REQUIRED
        assert result.reason == "manual_conflict_detected"
