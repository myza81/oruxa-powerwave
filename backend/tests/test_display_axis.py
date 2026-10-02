"""Display axis (DEC-131): which channels may share one Y axis in the Event
Reconstruction Grouped Measurement View -- resolved from engineering
metadata through the closed, quantity-aware unit table, never from a
channel name -- and its additive exposure on the channel APIs."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.domain.engineering_units import resolve_display_axis
from app.main import create_app
from app.schemas.calculated_channel import CalculatedChannelOut
from app.schemas.source import AnalogChannelOut


@pytest.mark.parametrize(
    ("engineering_type", "engineering_quantity", "unit", "key", "quantity", "axis_unit"),
    [
        # Voltage: aliases normalize, display units are NOT converted.
        ("Voltage", "Undefined", "kV", "Voltage|kV", "Voltage", "kV"),
        ("Voltage", "Undefined", "KV", "Voltage|kV", "Voltage", "kV"),
        ("Voltage", "Undefined", " kv ", "Voltage|kV", "Voltage", "kV"),
        ("Voltage", "Undefined", "V", "Voltage|V", "Voltage", "V"),
        ("Voltage", "Undefined", "MV", "Voltage|MV", "Voltage", "MV"),
        ("Current", "Undefined", "kA", "Current|kA", "Current", "kA"),
        ("Current", "Undefined", "A", "Current|A", "Current", "A"),
        # Broad "Power" resolves by unit family only.
        ("Power", "Undefined", "MW", "Active Power|MW", "Active Power", "MW"),
        ("Power", "Undefined", "mw", "Active Power|MW", "Active Power", "MW"),
        ("Power", "Undefined", "Mvar", "Reactive Power|Mvar", "Reactive Power", "Mvar"),
        ("Power", "Undefined", "MVAR", "Reactive Power|Mvar", "Reactive Power", "Mvar"),
        ("Power", "Undefined", "MVA", "Apparent Power|MVA", "Apparent Power", "MVA"),
        ("Frequency", "Undefined", "Hz", "Frequency|Hz", "Frequency", "Hz"),
        ("ROCOF", "Undefined", "Hz/s", "ROCOF|Hz/s", "ROCOF", "Hz/s"),
        # A classified quantity wins over the broad type.
        ("Power", "Reactive Power", "kvar", "Reactive Power|kvar", "Reactive Power", "kvar"),
        # Outside the table: exact unit string only, never merged with a
        # normalized unit.
        ("Voltage", "Undefined", "pu", "Voltage|raw:pu", "Voltage", "pu"),
        ("Voltage", "Voltage Angle", "deg", "Voltage Angle|raw:deg", "Voltage Angle", "deg"),
        # An unknown quantity is titled deliberately; its key keeps the
        # classification sentinel, so grouping is unchanged.
        ("Undefined", "Undefined", "bar", "Undefined|raw:bar", "Unknown quantity", "bar"),
        ("", "Undefined", "bar", "Undefined|raw:bar", "Unknown quantity", "bar"),
        ("Power", "Undefined", "MWh", "Power|raw:MWh", "Power", "MWh"),
    ],
)
def test_resolved_axes(engineering_type, engineering_quantity, unit, key, quantity, axis_unit):
    axis = resolve_display_axis(engineering_type, engineering_quantity, unit)
    assert (axis.key, axis.quantity, axis.unit) == (key, quantity, axis_unit)


@pytest.mark.parametrize("unit", ["", "   ", None])
def test_a_blank_unit_never_shares_an_axis(unit):
    assert resolve_display_axis("Voltage", "Undefined", unit).key is None
    assert resolve_display_axis("Undefined", "Undefined", unit).key is None


def test_unvalidated_ben_reactive_power_unit_is_an_unknown_quantity_not_undefined():
    """The UAT case: BEN32 R.POWER channels use BEN unit code 63, which the
    validated BEN unit table does not list, so the import leaves the unit
    blank and the type Undefined. The axis is titled "Unknown quantity" --
    never the sentinel "Undefined", and never guessed as Reactive Power."""
    axis = resolve_display_axis("Undefined", "Undefined", "")
    assert (axis.key, axis.quantity, axis.unit) == (None, "Unknown quantity", "")
    channel = AnalogChannelOut(name="R.POWER  GSU 12UBF", index=0, unit="", engineering_type="Undefined", scale=1, offset=0)
    dumped = channel.model_dump()
    assert (dumped["display_axis_key"], dumped["display_axis_quantity"], dumped["display_axis_unit"]) == (None, "Unknown quantity", "")


def test_a_broad_power_type_without_a_recognised_unit_is_never_guessed():
    for unit in ("", "MWh", "pu"):
        axis = resolve_display_axis("Power", "Undefined", unit)
        assert axis.quantity == "Power"
        assert axis.quantity not in ("Active Power", "Reactive Power", "Apparent Power")


@pytest.mark.parametrize("engineering_type", ["Voltage", "Current", "Power", "Frequency", "ROCOF", "Undefined", ""])
@pytest.mark.parametrize("unit", ["", " ", "kV", "V", "kA", "A", "MW", "Mvar", "MVA", "Hz", "Hz/s", "pu", "deg", "bar", "MWh"])
def test_every_axis_has_a_real_title_quantity(engineering_type, unit):
    axis = resolve_display_axis(engineering_type, "Undefined", unit)
    assert isinstance(axis.quantity, str) and axis.quantity.strip()
    assert axis.quantity != "Undefined"
    assert "undefined" not in axis.quantity.lower()


def test_compatibility_is_quantity_and_normalized_unit():
    key = lambda t, u: resolve_display_axis(t, "Undefined", u).key  # noqa: E731
    assert key("Voltage", "kV") == key("Voltage", "KV")  # same axis
    assert key("Voltage", "kV") != key("Voltage", "V")  # different scale
    assert key("Voltage", "kV") != key("Voltage", "pu")  # different interpretation
    assert key("Power", "MW") != key("Power", "Mvar")  # different quantity
    assert key("Voltage", "V") != key("Current", "A")


def test_channel_name_plays_no_part():
    a = AnalogChannelOut(name="FREQ MW V IA", index=0, unit="kV", engineering_type="Voltage", scale=1, offset=0)
    b = AnalogChannelOut(name="anything", index=1, unit="kV", engineering_type="Voltage", scale=1, offset=0)
    assert a.display_axis_key == b.display_axis_key == "Voltage|kV"


def test_fields_are_additive_on_the_wire():
    dumped = AnalogChannelOut(name="P", index=0, unit="MW", engineering_type="Power", scale=1, offset=0).model_dump()
    assert {"name", "unit", "engineering_type", "engineering_quantity"} <= set(dumped)
    assert dumped["display_axis_key"] == "Active Power|MW"
    assert dumped["display_axis_quantity"] == "Active Power"
    assert dumped["display_axis_unit"] == "MW"


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_channel_and_calculated_apis_expose_the_axis(client, comtrade_fixtures_dir):
    ws = "ws-display-axis"
    files = {
        "cfg_file": ("s.cfg", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.cfg").read_bytes()), "application/octet-stream"),
        "dat_file": ("s.dat", io.BytesIO((comtrade_fixtures_dir / "synth_ascii.dat").read_bytes()), "application/octet-stream"),
    }
    source_id = client.post(f"/api/v1/workspaces/{ws}/sources", files=files).json()["source_id"]
    channels = client.get(f"/api/v1/workspaces/{ws}/sources/{source_id}/channels").json()["analog_channels"]
    axes = {c["name"]: (c["display_axis_key"], c["display_axis_quantity"], c["display_axis_unit"]) for c in channels}
    assert axes == {
        "VA": ("Voltage|V", "Voltage", "V"),
        "VB": ("Voltage|V", "Voltage", "V"),
        "IA": ("Current|A", "Current", "A"),
    }
    calc = client.post(f"/api/v1/workspaces/{ws}/calculated-channels", json={
        "name": "-VA", "operation": "reverse_polarity",
        "inputs": [{"kind": "source", "source_id": source_id, "channel_name": "VA"}], "parameters": {},
    })
    assert calc.status_code == 201, calc.text
    body = calc.json()
    assert (body["display_axis_key"], body["display_axis_quantity"], body["display_axis_unit"]) == ("Voltage|V", "Voltage", "V")
    listed = client.get(f"/api/v1/workspaces/{ws}/calculated-channels").json()
    assert listed[0]["display_axis_key"] == "Voltage|V"


def test_calculated_schema_uses_type_and_unit():
    fields = CalculatedChannelOut.model_fields
    assert "display_axis_key" not in fields  # computed, not stored
    assert "display_axis_key" in CalculatedChannelOut.model_computed_fields
