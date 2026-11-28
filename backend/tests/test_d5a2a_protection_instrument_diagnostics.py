"""D5A-2A: pure unit tests of the diagnostics rules, one per reason code, with hand-built contexts."""

from __future__ import annotations

import pytest

from app.services.protection_instrument_context import (
    RATIO_CONFIGURED,
    RATIO_NO_CHANNELS,
    RATIO_NOT_CONFIGURED,
    SIDE_DECLARED,
    SIDE_MIXED,
    SIDE_UNKNOWN,
    TransformerContext,
)
from app.services.protection_instrument_diagnostics import (
    ANALYSIS_DISTANCE,
    ANALYSIS_IMPEDANCE,
    ANALYSIS_OVERCURRENT,
    RequestAssumptions,
    build_diagnostics,
)


def _ctx(quantity: str, *, primary=None, secondary=None, side="unknown", side_status=SIDE_UNKNOWN,
         status=None, nominal=None, nominal_refused=None) -> TransformerContext:
    configured = primary is not None
    return TransformerContext(
        quantity=quantity, ratio_status=status or (RATIO_CONFIGURED if configured else RATIO_NOT_CONFIGURED),
        primary=primary, secondary=secondary, authority="manual" if configured else "not_configured",
        side=side, side_status=side_status, nominal_ll_kv=nominal, nominal_refused_reason=nominal_refused,
    )


V = lambda **k: _ctx("voltage", **k)   # noqa: E731
I = lambda **k: _ctx("current", **k)   # noqa: E731
DECL = dict(side_status=SIDE_DECLARED)


def _codes(analysis, voltage, current, request=RequestAssumptions(), **kw):
    return [d.code for d in build_diagnostics(analysis, voltage, current, request, **kw)]


def test_clean_request_has_no_findings():
    v = V(primary=132000.0, secondary=110.0, side="secondary", **DECL)
    c = I(primary=1200.0, secondary=5.0, side="secondary", **DECL)
    req = RequestAssumptions(recording_basis="secondary", impedance_basis="secondary",
                             vt_primary=13200.0, vt_secondary=11.0, ct_primary=240.0, ct_secondary=1.0)
    assert _codes(ANALYSIS_IMPEDANCE, v, c, req) == []


def test_no_request_assumptions_report_only_context_gaps():
    assert _codes(ANALYSIS_IMPEDANCE, V(), I()) == [
        "VT_AUTHORITY_MISSING", "VOLTAGE_SIDE_UNKNOWN", "CT_AUTHORITY_MISSING", "CURRENT_SIDE_UNKNOWN"]


def test_overcurrent_ignores_voltage_entirely():
    codes = _codes(ANALYSIS_OVERCURRENT, None, I(primary=1200.0, secondary=5.0, side="primary", **DECL),
                   RequestAssumptions(recording_basis="primary", ct_primary=1200.0, ct_secondary=5.0))
    assert codes == []


def test_overcurrent_secondary_basis_needs_no_conversion_authority():
    codes = _codes(ANALYSIS_OVERCURRENT, None, I(), RequestAssumptions(recording_basis="secondary"))
    assert "CONVERSION_REQUESTED_WITHOUT_AUTHORITY" not in codes


def test_overcurrent_primary_basis_without_ct_is_flagged():
    codes = _codes(ANALYSIS_OVERCURRENT, None, I(), RequestAssumptions(recording_basis="primary"))
    assert "CONVERSION_REQUESTED_WITHOUT_AUTHORITY" in codes and "CONVERSION_REQUESTED_WITH_UNKNOWN_SIDE" in codes


def test_impedance_conversion_needs_both_ratios():
    req = RequestAssumptions(recording_basis="primary", impedance_basis="secondary")
    findings = build_diagnostics(ANALYSIS_IMPEDANCE, V(primary=132000.0, secondary=110.0, side="primary", **DECL), I(), req)
    conv = [d for d in findings if d.code == "CONVERSION_REQUESTED_WITHOUT_AUTHORITY"]
    assert [d.quantity for d in conv] == ["current"]


def test_mixed_side_reason_codes_and_no_proposed_basis():
    codes = _codes(ANALYSIS_DISTANCE, V(primary=1.0, secondary=1.0, side_status=SIDE_MIXED),
                   I(primary=1.0, secondary=1.0, side_status=SIDE_MIXED))
    assert "VOLTAGE_SIDE_MIXED" in codes and "CURRENT_SIDE_MIXED" in codes


@pytest.mark.parametrize("vp,vs,code", [
    (None, 110.0, "REQUEST_VT_INCOMPLETE"), (132000.0, None, "REQUEST_VT_INCOMPLETE"),
    (0.0, 110.0, "REQUEST_VT_INVALID"), (float("nan"), 110.0, "REQUEST_VT_INVALID"), (132000.0, -5.0, "REQUEST_VT_INVALID"),
])
def test_request_vt_shape_findings(vp, vs, code):
    assert code in _codes(ANALYSIS_IMPEDANCE, V(primary=132000.0, secondary=110.0), I(),
                          RequestAssumptions(vt_primary=vp, vt_secondary=vs))


def test_request_ratio_without_authority_is_unverified_not_different():
    codes = _codes(ANALYSIS_IMPEDANCE, V(), I(), RequestAssumptions(vt_primary=132000.0, vt_secondary=110.0,
                                                                   ct_primary=1200.0, ct_secondary=5.0))
    assert "REQUEST_VT_NOT_VERIFIED_BY_AUTHORITY" in codes and "REQUEST_CT_NOT_VERIFIED_BY_AUTHORITY" in codes
    assert not [c for c in codes if c.endswith("DIFFERS_FROM_AUTHORITY")]


def test_ratio_tolerance_is_relative_and_tight():
    v = V(primary=132000.0, secondary=110.0)
    assert "REQUEST_VT_DIFFERS_FROM_AUTHORITY" not in _codes(
        ANALYSIS_IMPEDANCE, v, I(), RequestAssumptions(vt_primary=132000.0 * (1 + 1e-9), vt_secondary=110.0))
    assert "REQUEST_VT_DIFFERS_FROM_AUTHORITY" in _codes(
        ANALYSIS_IMPEDANCE, v, I(), RequestAssumptions(vt_primary=132000.0 * 1.001, vt_secondary=110.0))


def test_a_nominal_that_cannot_yield_a_vt_is_reported_with_the_reason():
    findings = build_diagnostics(ANALYSIS_IMPEDANCE, V(nominal=275.0, nominal_refused="manual_conflict"), I(), RequestAssumptions())
    notice = next(d for d in findings if d.code == "VT_NOMINAL_NOT_USABLE")
    assert (notice.severity, notice.detail["nominal_ll_kv"], notice.detail["reason"]) == ("warning", 275.0, "manual_conflict")


def test_a_usable_nominal_produces_no_notice():
    # The auto-derived VT is valid configuration: nothing is flagged about it.
    ctx = _ctx("voltage", primary=275000.0, secondary=110.0, nominal=275.0)
    codes = [d.code for d in build_diagnostics(ANALYSIS_IMPEDANCE, ctx, I(), RequestAssumptions())]
    assert "VT_NOMINAL_NOT_USABLE" not in codes and "VT_AUTHORITY_MISSING" not in codes


def test_no_channels_context_is_not_reported_as_missing_authority():
    ctx = TransformerContext(quantity="current", ratio_status=RATIO_NO_CHANNELS)
    findings = build_diagnostics(ANALYSIS_OVERCURRENT, None, ctx, RequestAssumptions(recording_basis="primary"),
                                 unresolved_roles=(("Ia", "needs_configuration", "role_missing"),))
    assert [d.code for d in findings] == ["CHANNEL_UNRESOLVED"]


def test_every_finding_is_machine_readable_and_non_blocking():
    findings = build_diagnostics(
        ANALYSIS_IMPEDANCE, V(side_status=SIDE_MIXED), I(), RequestAssumptions(
            recording_basis="primary", impedance_basis="secondary", vt_primary=1.0, ct_primary=1.0))
    assert findings
    for d in findings:
        assert d.code.isupper() and d.severity in ("warning", "info") and isinstance(d.message, str) and d.message
