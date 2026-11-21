"""D5A-OC-001: recorded Overcurrent takes its CT from the Recording Details Measurement Group that owns the
actual current channel.

The compute endpoint is unchanged and still driven by its own request parameters (the frontend feeds it the
authoritative CT, exactly as for Impedance/Distance). What this file pins is the authority the frontend reads and
the numerical contract it relies on:

* `protection-instrument-context?analysis=overcurrent` resolves the CT from the group of the phase's own current
  channel (never another group), reports the recording's declared side per channel, and never infers either from
  the CT ratio;
* a primary recording is converted once, a secondary recording never; a missing/invalid CT blocks only a conversion
  that is actually needed;
* a blocked result keeps the resolved channel identity (so Related Waveforms stay plottable) without any number.

Expected values are hand-derived, never taken from the production conversion:

    CT 1000 A : 5 A (ratio 200)          recorded 400 A primary  -> 400 * 5 / 1000 = 2.0 A relay-secondary
    recorded 2 A secondary  -> 2.0 A (unchanged: the CT ratio is NOT applied again; a double conversion would give
    2.0 * 5 / 1000 = 0.01 A)
    IEC standard inverse, TMS 0.1, M = 2.0 / 1.0 = 2:  t = 0.1 * 0.14 / (2**0.02 - 1)
"""

from __future__ import annotations

import pytest

from app.domain.measurement_group import KIND_CURRENT
from app.domain.analysis_input_resolution import STATUS_NEEDS_CONFIGURATION
from app.domain.overcurrent import OVERCURRENT_STATUS_COMPUTED
from app.services.overcurrent_analysis_service import compute_overcurrent_analysis
from tests.test_d5a2a_protection_instrument_context_api import _contexts, _clear, _ct, _ctx, _group, _ref
from tests.test_d5a2b1_independent_side_conversion import (  # noqa: F401  (client is the shared fixture)
    CT_P, CT_S, I_PRI, I_SEC, VT_P, VT_S, _bay, client,
)
from tests.test_overcurrent_analysis_service import (  # noqa: F401  (registries is the shared fixture)
    _add_context, _current_source, _member, registries,
)

RELAY_SECONDARY_A = I_PRI * CT_S / CT_P          # 2.0 A, hand-derived above
assert RELAY_SECONDARY_A == pytest.approx(I_SEC)
DOUBLE_CONVERSION_A = I_SEC * CT_S / CT_P        # 0.01 A: what applying the ratio to a secondary recording would give
IEC_SI_TIME_S = 0.1 * 0.14 / (2.0 ** 0.02 - 1.0)  # M = 2, TMS = 0.1


def _oc(client, ws, ctx, **params):
    q = {
        "phase": "A", "analysis_time": 1.5, "characteristic_id": "iec_standard_inverse", "tms": 0.1,
        "pickup_current_secondary": 1.0, "recording_basis": "secondary",
    }
    q.update(params)
    return client.get(f"{_contexts(ws)}/{ctx}/overcurrent", params=q)


def _report(client, ws, ctx, phase="A", **params):
    resp = _ctx(client, ws, ctx, analysis="overcurrent", phase=phase, **params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _src_ref(src, name):
    return {"kind": "source", "source_id": src, "channel_name": name, "calculated_channel_id": None}


NUMBERS = (
    "measured_rms_current", "relay_secondary_current", "multiple_of_pickup", "expected_operating_time_seconds",
    "above_pickup_duration_seconds",
)


def _blocked(body, reason):
    assert body["status"] == "needs_configuration" and body["reason_code"] == reason, body
    assert all(body[k] is None for k in NUMBERS), body


# =========================================================================== the authority the page reads


def test_the_report_is_current_only_and_names_the_group_that_owns_the_phase_channel(client):
    ws = "ocauth-owner"
    src, ctx = _bay(client, ws)
    body = _report(client, ws, ctx)
    assert body["voltage"] is None
    assert [c["role_key"] for c in body["channels"]] == ["Ia"]
    channel = body["channels"][0]
    assert channel["channel"] == _src_ref(src, "ZBAY_IA")
    assert channel["measurement_group_id"] == f"ig-{src}" and channel["measurement_group_kind"] == "current"
    current = body["current"]
    assert (current["ratio_status"], current["ratio_consumable"]) == ("configured", True)
    assert (current["primary"], current["secondary"], current["ratio"]) == (CT_P, CT_S, CT_P / CT_S)
    assert current["authority"] == "manual" and current["group_ids"] == [f"ig-{src}"]
    assert current["ratio_origin"] == "recording_details_measurement_group"


def test_each_phase_reads_the_ct_of_its_own_group_never_another(client):
    ws = "ocauth-groups"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_CURRENT, ("IA", "IC"), "ig-ac")
    _group(client, ws, src, KIND_CURRENT, ("IB",), "ig-b")
    _ct(client, ws, "ig-ac", 1000.0, 5.0)
    _ct(client, ws, "ig-b", 2000.0, 1.0)
    for phase, group, pair in (("A", "ig-ac", (1000.0, 5.0)), ("B", "ig-b", (2000.0, 1.0)), ("C", "ig-ac", (1000.0, 5.0))):
        current = _report(client, ws, ctx, phase)["current"]
        assert current["group_ids"] == [group], phase
        assert (current["primary"], current["secondary"]) == pair, phase


def test_a_ct_held_by_an_unrelated_group_is_never_borrowed(client):
    ws = "ocauth-unrelated"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_CURRENT, ("IA",), "ig-a")        # phase A's own group: no CT
    _group(client, ws, src, KIND_CURRENT, ("IB", "IC"), "ig-bc")
    _ct(client, ws, "ig-bc", 1000.0, 5.0)
    body = _report(client, ws, ctx, "A", recording_basis="primary")
    current = body["current"]
    assert current["ratio_status"] == "not_configured" and current["ratio_consumable"] is False
    assert current["primary"] is None and current["secondary"] is None and current["ratio"] is None
    assert current["group_ids"] == ["ig-a"]
    assert "CT_AUTHORITY_MISSING" in [d["code"] for d in body["diagnostics"]]
    assert "CONVERSION_REQUESTED_WITHOUT_AUTHORITY" in [d["code"] for d in body["diagnostics"]]


def test_an_ungrouped_current_channel_has_no_ct_authority(client):
    ws = "ocauth-nogroup"
    _src, ctx = _bay(client, ws, groups=False)
    current = _report(client, ws, ctx)["current"]
    assert (current["ratio_status"], current["ratio_consumable"], current["ratio"]) == ("no_group", False, None)


@pytest.mark.parametrize("authority", ["manual", "recording_metadata"])
def test_manual_and_recording_metadata_ct_are_consumable_with_their_provenance(client, authority):
    ws = f"ocauth-auth-{authority}"
    src, ctx = _bay(client, ws)
    _ct(client, ws, f"ig-{src}", 600.0, 1.0, authority=authority, note="from the recording")
    current = _report(client, ws, ctx)["current"]
    assert current["ratio_consumable"] is True and current["authority"] == authority
    assert (current["primary"], current["secondary"]) == (600.0, 1.0)
    assert current["provenance_note"] == "from the recording"


def test_an_untrusted_ct_authority_is_not_consumable(client):
    ws = "ocauth-untrusted"
    src, ctx = _bay(client, ws)
    _ct(client, ws, f"ig-{src}", 1000.0, 5.0, authority="auto_nominal")
    current = _report(client, ws, ctx)["current"]
    assert (current["ratio_status"], current["ratio_consumable"], current["ratio"]) == ("untrusted_authority", False, None)


@pytest.mark.parametrize("pair", [(0.0, 5.0), (1000.0, 0.0), (-1000.0, 5.0)])
def test_an_invalid_stored_ct_is_never_consumable(client, pair):
    ws = f"ocauth-invalid-{pair[0]}-{pair[1]}"
    src, ctx = _bay(client, ws)
    _ct(client, ws, f"ig-{src}", *pair)
    current = _report(client, ws, ctx)["current"]
    assert (current["ratio_status"], current["ratio_consumable"], current["ratio"]) == ("invalid", False, None)


def test_a_ct_is_never_derived_from_the_recording_or_from_voltage_configuration(client):
    ws = "ocauth-noderive"
    src, ctx = _bay(client, ws, groups=False)
    _group(client, ws, src, KIND_CURRENT, ("IA", "IB", "IC"), "ig-1")     # grouped, nothing configured
    current = _report(client, ws, ctx)["current"]
    assert (current["ratio_status"], current["primary"], current["secondary"], current["ratio"]) == ("not_configured", None, None, None)
    assert current["authority"] == "not_configured"


def test_a_change_made_in_recording_details_is_visible_to_the_next_read(client):
    ws = "ocauth-change"
    src, ctx = _bay(client, ws)
    assert _report(client, ws, ctx)["current"]["ratio"] == CT_P / CT_S
    _ct(client, ws, f"ig-{src}", 2000.0, 1.0, authority="manual")
    after = _report(client, ws, ctx)["current"]
    assert (after["primary"], after["secondary"], after["ratio"]) == (2000.0, 1.0, 2000.0)
    _clear_ct = client.app.state.current_group_config_registry
    _clear_ct.delete(ws, f"ig-{src}")
    assert _report(client, ws, ctx)["current"]["ratio_status"] == "not_configured"


def test_workspaces_never_share_ct_configuration(client):
    a_src, a_ctx = _bay(client, "ocauth-ws-a", ct=(1000.0, 5.0))
    b_src, b_ctx = _bay(client, "ocauth-ws-b", ct=(3000.0, 1.0))
    assert _report(client, "ocauth-ws-a", a_ctx)["current"]["ratio"] == 200.0
    assert _report(client, "ocauth-ws-b", b_ctx)["current"]["ratio"] == 3000.0


# =========================================================================== measurement side (never from the ratio)


@pytest.mark.parametrize("flag,expected", [("P", "primary"), ("S", "secondary")])
def test_the_declared_side_of_the_current_channel_is_reported_per_channel(client, flag, expected):
    ws = f"ocauth-side-{flag}"
    _src, ctx = _bay(client, ws, ps={"IA": flag})
    body = _report(client, ws, ctx)
    assert body["channels"][0]["declared_side"] == expected
    assert (body["current"]["side_status"], body["current"]["declared_basis"]) == ("recording_declared", expected)


def test_an_undeclared_side_stays_unknown_whatever_the_ct_ratio_is(client):
    ws = "ocauth-side-unknown"
    _src, ctx = _bay(client, ws, ps={"IA": ""}, ct=(1000.0, 5.0))
    body = _report(client, ws, ctx)
    assert body["channels"][0]["declared_side"] == "unknown"
    assert (body["current"]["side_status"], body["current"]["declared_basis"]) == ("unknown", None)
    assert "CURRENT_SIDE_UNKNOWN" in [d["code"] for d in body["diagnostics"]]


def test_a_request_basis_that_contradicts_the_declared_side_is_reported_and_never_applied(client):
    ws = "ocauth-side-contradict"
    _src, ctx = _bay(client, ws, i_side="secondary")
    body = _report(client, ws, ctx, recording_basis="primary")
    assert "REQUEST_RECORDING_BASIS_CONTRADICTS_CURRENT_SIDE" in [d["code"] for d in body["diagnostics"]]


# =========================================================================== numerics: one conversion, never two


def test_a_primary_recording_is_converted_once_with_the_authoritative_ct(client):
    ws = "ocnum-primary"
    _src, ctx = _bay(client, ws, i_side="primary")
    ct = _report(client, ws, ctx)["current"]
    body = _oc(client, ws, ctx, recording_basis="primary", ct_primary=ct["primary"], ct_secondary=ct["secondary"]).json()
    assert body["status"] == OVERCURRENT_STATUS_COMPUTED
    assert body["measured_rms_current"] == pytest.approx(I_PRI, rel=1e-4)
    assert body["relay_secondary_current"] == pytest.approx(RELAY_SECONDARY_A, rel=1e-4)
    assert body["multiple_of_pickup"] == pytest.approx(2.0, rel=1e-4)
    assert body["expected_operating_time_seconds"] == pytest.approx(IEC_SI_TIME_S, rel=1e-3)


def test_a_secondary_recording_is_never_converted_again(client):
    ws = "ocnum-secondary"
    _src, ctx = _bay(client, ws, i_side="secondary")
    assert _report(client, ws, ctx)["current"]["declared_basis"] == "secondary"
    body = _oc(client, ws, ctx, recording_basis="secondary").json()
    assert body["status"] == OVERCURRENT_STATUS_COMPUTED
    assert body["measured_rms_current"] == pytest.approx(I_SEC, rel=1e-4)
    assert body["relay_secondary_current"] == pytest.approx(RELAY_SECONDARY_A, rel=1e-4)
    assert body["relay_secondary_current"] != pytest.approx(DOUBLE_CONVERSION_A, rel=0.5)
    assert body["expected_operating_time_seconds"] == pytest.approx(IEC_SI_TIME_S, rel=1e-3)


def test_a_secondary_recording_ignores_a_ct_that_accompanies_the_request(client):
    ws = "ocnum-secondary-ct"
    _src, ctx = _bay(client, ws, i_side="secondary")
    body = _oc(client, ws, ctx, recording_basis="secondary", ct_primary=CT_P, ct_secondary=CT_S).json()
    assert body["relay_secondary_current"] == pytest.approx(RELAY_SECONDARY_A, rel=1e-4)


def test_primary_and_secondary_recordings_of_the_same_physical_current_agree(client):
    ws = "ocnum-agree"
    _s1, primary_ctx = _bay(client, ws + "-p", i_side="primary")
    _s2, secondary_ctx = _bay(client, ws + "-s", i_side="secondary")
    p = _oc(client, ws + "-p", primary_ctx, recording_basis="primary", ct_primary=CT_P, ct_secondary=CT_S).json()
    s = _oc(client, ws + "-s", secondary_ctx, recording_basis="secondary").json()
    assert p["relay_secondary_current"] == pytest.approx(s["relay_secondary_current"], rel=1e-4)
    assert p["expected_operating_time_seconds"] == pytest.approx(s["expected_operating_time_seconds"], rel=1e-3)


@pytest.mark.parametrize("ct,expected", [((1000.0, 5.0), 2.0), ((2000.0, 1.0), 0.2), ((400.0, 1.0), 1.0), ((800.0, 5.0), 2.5)])
def test_the_relay_secondary_current_follows_the_ct_ratio_of_the_group(client, ct, expected):
    ws = f"ocnum-ratio-{ct[0]}-{ct[1]}"
    _src, ctx = _bay(client, ws, i_side="primary", ct=ct)
    stored = _report(client, ws, ctx)["current"]
    body = _oc(client, ws, ctx, recording_basis="primary", ct_primary=stored["primary"], ct_secondary=stored["secondary"]).json()
    assert body["relay_secondary_current"] == pytest.approx(I_PRI * ct[1] / ct[0], rel=1e-4)
    assert body["relay_secondary_current"] == pytest.approx(expected, rel=1e-4)


# =========================================================================== blocked results keep the channel identity


def test_a_primary_request_without_ct_is_blocked_but_still_identifies_the_channel(client):
    ws = "ocblock-missing"
    src, ctx = _bay(client, ws, groups=False)
    body = _oc(client, ws, ctx, recording_basis="primary").json()
    _blocked(body, "invalid_ct_values")
    assert body["message"] == "CT primary and CT secondary current must both be finite numbers greater than zero."
    assert body["channel_ref"] == _src_ref(src, "ZBAY_IA") and body["measured_rms_current_unit"] == "A"


@pytest.mark.parametrize("ct", [
    dict(ct_primary=CT_P), dict(ct_secondary=CT_S), dict(ct_primary=0.0, ct_secondary=CT_S),
    dict(ct_primary=CT_P, ct_secondary=-5.0),
], ids=["missing-secondary", "missing-primary", "zero-primary", "negative-secondary"])
def test_an_incomplete_or_invalid_ct_blocks_with_the_same_reason_and_keeps_the_phase_channel(client, ct):
    ws = "ocblock-invalid-" + "-".join(sorted(ct)) + str(sorted(ct.values()))
    src, ctx = _bay(client, ws)
    for phase in ("A", "B", "C"):
        body = _oc(client, ws, ctx, phase=phase, recording_basis="primary", **ct).json()
        _blocked(body, "invalid_ct_values")
        assert body["channel_ref"] == _src_ref(src, f"ZBAY_I{phase}") and body["measured_rms_current_unit"] == "A"


def test_a_secondary_request_needs_no_ct_even_when_none_is_configured(client):
    ws = "ocblock-unneeded"
    _src, ctx = _bay(client, ws, groups=False, i_side="secondary")
    body = _oc(client, ws, ctx, recording_basis="secondary").json()
    assert body["status"] == OVERCURRENT_STATUS_COMPUTED
    assert body["relay_secondary_current"] == pytest.approx(RELAY_SECONDARY_A, rel=1e-4)


def test_an_unresolved_channel_is_never_given_an_identity(client):
    ws = "ocblock-unresolved"
    _src, ctx = _bay(client, ws, members=("VA", "VB", "VC"))          # no current channels in the context
    body = _oc(client, ws, ctx, recording_basis="primary").json()
    _blocked(body, "invalid_ct_values")
    assert body["channel_ref"] is None and body["measured_rms_current_unit"] is None


def test_an_unknown_context_still_reports_the_ct_block_not_an_error(client):
    body = _oc(client, "ocblock-nocontext", "no-such-context", recording_basis="primary").json()
    _blocked(body, "invalid_ct_values")
    assert body["channel_ref"] is None


def test_an_unsupported_unit_keeps_the_channel_identity(registries):
    registries["source"].add(_current_source("src-1", "ws-1", "ALPHA1_IA", rms_amps=2.4, unit="furlongs"))
    _add_context(registries["context"], "ec-1", "ws-1", [_member("src-1", "ALPHA1_IA", "A")])
    result = compute_overcurrent_analysis(
        workspace_id="ws-1", engineering_context_id="ec-1", phase="A", analysis_time=1.5,
        characteristic_id="iec_standard_inverse", tms=0.1, pickup_current_secondary=1.0,
        recording_basis="secondary", ct_primary=None, ct_secondary=None, reference_frequency_hz_override=None,
        context_registry=registries["context"], source_registry=registries["source"],
        calculated_channel_registry=registries["calc"],
    )
    assert (result.status, result.reason_code) == (STATUS_NEEDS_CONFIGURATION, "unsupported_current_unit")
    assert result.channel_ref is not None and result.channel_ref.channel_name == "ALPHA1_IA"
    assert result.measured_rms_current_unit == "furlongs"
    assert result.relay_secondary_current is None and result.expected_operating_time_seconds is None


# =========================================================================== the read-only report never changes a calculation


def test_reading_the_report_leaves_the_compute_endpoint_unchanged(client):
    ws = "ocnum-readonly"
    _src, ctx = _bay(client, ws, i_side="primary")
    request = dict(recording_basis="primary", ct_primary=1234.0, ct_secondary=5.0)    # deliberately not the group's CT
    before = _oc(client, ws, ctx, **request).json()
    report = _report(client, ws, ctx, **request)
    after = _oc(client, ws, ctx, **request).json()
    assert before == after
    assert after["ct_primary"] == 1234.0 and after["ct_secondary"] == 5.0           # the request's own values, never overwritten
    assert report["current"]["primary"] == CT_P                                     # while the authority still says 1000
    assert "REQUEST_CT_DIFFERS_FROM_AUTHORITY" in [d["code"] for d in report["diagnostics"]]
