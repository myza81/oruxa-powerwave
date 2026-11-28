"""PU-MIG S3 closeout -- the compliance-series consumer follows the calculated Voltage side authority.

`compliance_series.load_series(ref, "pu")` is what the compliance trace and readiness services call for a calculated Voltage member. It must
return exactly the numbers the calculated waveform display returns (same refusal, same verification), because both reach the one
dispatch `_resolve_effective_per_unit_for_calculated_channel` with the same `RecordedAuthority`. The Registries bundle is built exactly as the
production routes build it (`api/v1/compliance.py`).
"""

from __future__ import annotations

import pytest

from app.domain.calculated_channel import ChannelRef
from app.services.compliance_series import Registries, load_series
from app.services.recorded_side_authority import RecordedAuthority
from tests.test_current_effective_base_inheritance import ROOT, checked, client  # noqa: F401  (client is the shared fixture)
from tests.test_pu_mig_s2_raw_voltage_side import D_PRIMARY_LG, D_SECONDARY_LG, build
from tests.test_pu_mig_s3_calculated_voltage_side import cprov, cwave, engineering, make, source_default

WSID = ROOT.split("/workspaces/")[1]


def registries(client, with_authority=True):
    s = client.app.state
    return Registries(
        source=s.workspace_registry, calc=s.calculated_channel_registry, per_unit=s.per_unit_registry, group=s.measurement_group_registry,
        voltage_config=s.voltage_group_config_registry, current_config=s.current_group_config_registry,
        side_authority=RecordedAuthority.from_app_state(s) if with_authority else None,
    )


def series(client, cid, **kw):
    return load_series(ChannelRef(kind="calculated", calculated_channel_id=cid), "pu", workspace_id=WSID, reg=registries(client, **kw))


def test_a_converted_calculated_series_is_the_displayed_per_unit_values(client):
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    cid = make(client, sid, "reverse_polarity")
    loaded, problem = series(client, cid)
    assert problem is None and loaded.unit == "pu"
    assert list(loaded.values) == pytest.approx([v / D_SECONDARY_LG for v in engineering(client, cid)], rel=1e-12, abs=1e-15)
    assert list(loaded.values) == pytest.approx(cwave(client, cid)["values"], rel=1e-12, abs=1e-15)
    assert cprov(client, cid)["verification_state"] == "verified_converted"


def test_the_same_result_without_the_authority_is_the_historical_unconverted_number(client):
    """Proves the authority is what the compliance series consumes: without it the Secondary samples are divided by the Primary base
    (the historical ~0.0008 pu hazard class); with it they are the converted 1.0 pu."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, stored_side="primary", vt=(132000.0, 110.0))
    cid = make(client, sid, "reverse_polarity")
    converted, problem = series(client, cid)
    assert problem is None and max(abs(v) for v in converted.values) == pytest.approx(1.0, rel=1e-12)
    historical, problem = series(client, cid, with_authority=False)
    assert problem is None
    assert max(abs(v) for v in historical.values) == pytest.approx(D_SECONDARY_LG / (132000.0 / 3 ** 0.5), rel=1e-12)


def test_a_primary_calculated_series_is_direct_and_bit_identical_to_the_display(client):
    sid, _ = build(client, flag="P", stored_side="primary")
    cid = make(client, sid, "absolute_value")
    loaded, problem = series(client, cid)
    assert problem is None and list(loaded.values) == cwave(client, cid)["values"]
    assert cprov(client, cid)["verification_state"] == "verified_direct"


def test_a_refused_calculated_series_agrees_with_the_display_refusal_and_provenance(client):
    """A Source Default base has no ratio authority: the display refuses (blocked, ENG kept) and so does the compliance series."""
    sid, _ = build(client, flag="S", amplitude=D_SECONDARY_LG, group=False)
    source_default(client, sid, "primary")
    cid = make(client, sid, "reverse_polarity")
    body, p = cwave(client, cid), cprov(client, cid)
    assert body["per_unit_status"] == "base_required" and p["verification_state"] == "blocked"
    loaded, problem = series(client, cid)
    assert loaded is None and "cannot be shown in per-unit" in problem and "base_required" in problem


def test_a_historical_unverified_calculated_series_keeps_the_historical_numbers(client):
    sid, _ = build(client, flag="", amplitude=D_PRIMARY_LG, stored_side="primary")
    cid = make(client, sid, "reverse_polarity")
    assert cprov(client, cid)["verification_state"] == "unverified_historical"
    loaded, problem = series(client, cid)
    assert problem is None and list(loaded.values) == cwave(client, cid)["values"]
