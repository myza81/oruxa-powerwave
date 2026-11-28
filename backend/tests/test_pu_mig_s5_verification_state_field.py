"""PU-MIG S5 -- the backend's own verification state reaches the presentation layer on every response the channel badge is built from.

The badge used to be keyed off `per_unit_reference_compatibility` alone, which is `compatible` both for a result the resolver verified and
for a historical result whose side LABELS merely match (the Source Default counterexample: a 132 kV base labelled Secondary on rated
Secondary samples reads 1/1200 pu). The label never proves the denominator is on that side, so the response now carries the engine's
`verification_state` next to it; the frontend shows it and never derives it. The value is read from the resolution that produced the
numbers (`PerUnitResolution.verification_state`), so it cannot disagree with `GET .../per-unit-resolution`.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from tests.test_per_unit_voltage_reference_safety import (  # noqa: F401  (client is the shared fixture)
    NO_NOMINAL, SECONDARY_V, VNAMES, checked, client, cursor_status, peak_status, provenance, recording, setup_voltage_base, wave_status, ROOT,
)
from tests.test_pu_mig_s2_d7_closeout import source_default
from tests.test_pu_mig_s2_raw_voltage_side import provenance as source_provenance, wave


def test_the_counterexample_reports_unverified_historical_beside_a_compatible_label(client):
    sid = source_default(client, flag="S", stored_side="secondary", value_kv=132.0)
    body, p = wave(client, sid), source_provenance(client, sid)
    assert body["per_unit_reference_compatibility"] == "compatible"                  # the labels match ...
    assert body["per_unit_verification_state"] == "unverified_historical"           # ... which verifies nothing
    assert body["per_unit_verification_state"] == p["verification_state"]


@pytest.mark.parametrize("marker,base_side,nominal,state", [
    ("P", "primary", 275, "verified_direct"),
    ("S", "primary", 275, "verified_converted"),
    ("S", "secondary", 275, "verified_direct"),
    ("P", "secondary", NO_NOMINAL, "blocked"),
])
def test_the_waveform_response_carries_the_state_the_resolution_reports(client, comtrade_fixtures_dir, marker, base_side, nominal, state):
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_voltage_base(client, sid, base_side, scope="group", secondary_v=SECONDARY_V, nominal=nominal)
    body = wave_status(client, sid, VNAMES[0])
    assert body["per_unit_verification_state"] == provenance(client, sid, VNAMES[0])["verification_state"] == state


@pytest.mark.parametrize("marker,base_side,state", [("S", "primary", "verified_converted"), ("S", "secondary", "verified_direct")])
def test_cursor_and_peak_responses_carry_the_same_state(client, comtrade_fixtures_dir, marker, base_side, state):
    sid = recording(client, comtrade_fixtures_dir, marker)
    setup_voltage_base(client, sid, base_side, scope="group", secondary_v=SECONDARY_V)
    assert cursor_status(client, sid, VNAMES[0])["per_unit_verification_state"] == state
    assert peak_status(client, sid, VNAMES[0])["per_unit_verification_state"] == state


def test_the_calculated_waveform_carries_the_inherited_state(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    made = checked(client.post(f"{ROOT}/calculated-channels", json={
        "name": "Reversed", "operation": "reverse_polarity",
        "inputs": [{"kind": "source", "source_id": sid, "channel_name": VNAMES[0]}]}), 201)
    body = checked(client.get(f"{ROOT}/calculated-channels/{made['id']}/waveform", params={"unit_mode": "per_unit"}))
    assert body["per_unit_verification_state"] == checked(client.get(f"{ROOT}/calculated-channels/{made['id']}/per-unit-resolution"))["verification_state"] == "verified_converted"


def test_engineering_mode_reports_no_state(client, comtrade_fixtures_dir):
    sid = recording(client, comtrade_fixtures_dir, "S")
    setup_voltage_base(client, sid, "primary", scope="group", secondary_v=SECONDARY_V)
    body = checked(client.get(f"{ROOT}/sources/{sid}/waveform", params={"channel_name": VNAMES[0]}))
    assert body["per_unit_status"] is None and body["per_unit_verification_state"] is None


@pytest.mark.parametrize("module", ["waveform", "calculated_channel", "peak_value", "cursor_values", "annotation_anchor"])
def test_every_response_model_that_exposes_the_compatibility_also_exposes_the_state(module):
    """The badge is built from the pair on every surface (rows, legends, hover, annotations); one without the state would show a
    label-compatible historical result as clean."""
    mod = importlib.import_module(f"app.schemas.{module}")
    models = [m for _, m in inspect.getmembers(mod, inspect.isclass) if hasattr(m, "model_fields") and "per_unit_reference_compatibility" in m.model_fields]
    assert models
    for model in models:
        assert "per_unit_verification_state" in model.model_fields, model.__name__
