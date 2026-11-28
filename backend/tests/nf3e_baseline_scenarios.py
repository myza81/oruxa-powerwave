"""Scenario runner for the NF-3E Phase A characterisation baseline (stored calculated channels vs. a recording's nominal frequency).

Not a test module. Same discipline as the NF-3B/NF-3C/NF-3D runners: the committed outcomes were generated ONCE from the unmodified NF-3D tip
(`65390d3`) before any NF-3E change, and record what the code DID, defects and gaps included. They are not engineering oracles; the independent
closed-form oracles are in `test_nf3e_independent_oracles.py`.

The question NF-3E answers (O-4): after the engineer changes a recording's nominal frequency, what does the system say about the calculated
channels that were computed with the OLD frequency? The facts frozen here are the inputs to that answer:

* what a stored channel records about the frequency it used (`parameters`), per operation;
* whether the channel inventory, the waveform response or anything else says anything about staleness (it does not: nothing does);
* that a stored channel's values are never recomputed, overwritten or removed by a frequency change;
* what the central accessor reports for the frequency a channel "has" (`for_channel_ref`: the recording that grounds its time base);
* what the readiness identity (`find_equivalent_rms`) does after a change (a NEW step is proposed; the old channel is left untouched);
* how a derived channel (a DAG over RMS channels) and a channel that spans two recordings behave when only one recording's frequency changes;
* what happens to a mixed-recording channel when its non-reference or reference recording is removed (the existing "unavailable" signal);
* the power channels, which store a fixed 50.0 regardless of the recording (NF-3F).

Every scenario runs in its own workspace on the same recordings as NF-3D (a 1 s, 5 kHz, six-channel bay). The Manual gate is OPEN in the test
process (`nominal_frequency_manual_override_enabled=True`); the generator and the test build the application the same way.
"""

from __future__ import annotations

import numpy as np

from app.domain.calculated_channel import ChannelRef
from app.services.compliance_readiness_service import find_equivalent_rms
from tests import nf3d_baseline_scenarios as nf3d
from tests.nf3b_baseline_scenarios import WS, _round_tree, num

PREFIX = f"{WS}-e"


def src(sid: str, name: str) -> dict:
    return {"kind": "source", "source_id": sid, "channel_name": f"ALPHA1_{name}"}


def calc(cid: str) -> dict:
    return {"kind": "calculated", "calculated_channel_id": cid}


def ref(sid: str, name: str) -> ChannelRef:
    return ChannelRef(kind="source", source_id=sid, channel_name=f"ALPHA1_{name}")


def _json(response):
    return nf3d._snap(response)


def waveform_summary(client, ws: str, cid: str) -> dict:
    """Status, length and 12-digit statistics of the stored values over the whole record (NaN warm-up samples counted, not averaged)."""
    r = client.get(f"/api/v1/workspaces/{ws}/calculated-channels/{cid}/waveform", params={"point_budget": 100000})
    if r.status_code != 200:
        return nf3d._snap(r)
    body = r.json()
    values = np.array([np.nan if v is None else v for v in body["values"]], dtype=float)
    finite = values[np.isfinite(values)]
    return {"status": 200, "unit": body["unit"], "points": len(values), "nan": int(np.isnan(values).sum()),
            "min": num(finite.min()) if finite.size else None, "max": num(finite.max()) if finite.size else None,
            "mean": num(finite.mean()) if finite.size else None, "last": num(values[-1]) if len(values) else None}


def create(client, ws: str, name: str, operation: str, inputs: list, parameters: dict | None = None, **extra) -> dict:
    body = {"name": name, "operation": operation, "inputs": inputs, **({"parameters": parameters} if parameters is not None else {}), **extra}
    r = client.post(f"/api/v1/workspaces/{ws}/calculated-channels", json=body)
    return {"status": r.status_code, "id": r.json().get("id") if r.status_code == 201 else None, "body": _json(r)["body"]}


#: What the channel list tells a user about a stored channel, minus every run-specific identifier (ids, timestamps, fingerprints).
STABLE_KEYS = ("operation", "parameters", "unit", "sample_count", "timing_status", "voltage_representation", "waveform_form", "phase_member",
               "calibration_provenance_status", "null_policy")


def inventory_raw(client, ws: str) -> list:
    r = client.get(f"/api/v1/workspaces/{ws}/calculated-channels")
    return r.json() if r.status_code == 200 else []


def inventory(client, ws: str) -> dict:
    """The channel list as the API returns it, identifiers removed: the field NAMES a client can see and a stable view of each channel."""
    body = inventory_raw(client, ws)
    channels = {c["name"]: {k: _round_tree(c.get(k)) for k in STABLE_KEYS} | {"dependency_count": len(c["dependency_ids"])} for c in body}
    return {"fields": sorted(body[0]) if body else [], "names": sorted(channels), "channels": channels}


def nominal(client, ws: str, sid: str) -> dict:
    return _round_tree(client.get(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency").json(), ("mode", "effective_hz", "usable", "origin", "revision"))


def put_manual(client, ws: str, sid: str, hz: float) -> dict:
    r = client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "manual", "value_hz": hz})
    return {"status": r.status_code, "body": _round_tree(r.json(), ("mode", "effective_hz", "usable", "origin", "revision"))}


def put_auto(client, ws: str, sid: str) -> dict:
    r = client.put(f"/api/v1/workspaces/{ws}/sources/{sid}/nominal-frequency", json={"mode": "auto"})
    return {"status": r.status_code, "body": _round_tree(r.json(), ("mode", "effective_hz", "usable", "origin", "revision"))}


def accessor_view(client, ws: str, sid_or_ref) -> dict:
    """The central accessor's answer for a channel ref (the recording that grounds it)."""
    access = client.app.state.nominal_frequency_access
    calc_registry = client.app.state.calculated_channel_registry
    try:
        f = access.for_channel_ref(ws, sid_or_ref, calc_registry=calc_registry)
    except Exception as exc:                                              # noqa: BLE001 - frozen as the exception class
        return {"raises": type(exc).__name__}
    return {"source_id_is_reference": True, "hz": f.hz, "origin": f.origin, "usable": f.usable, "revision": f.revision}


def equivalent_rms(client, ws: str, input_ref: ChannelRef, hz: float) -> str | None:
    found = find_equivalent_rms(client.app.state.calculated_channel_registry, ws, input_ref, hz)
    return found.name if found is not None else None


def stored(client, ws: str, cid: str) -> dict:
    channel = client.app.state.calculated_channel_registry.get(ws, cid)
    if channel is None:
        return {"present": False}
    return {"present": True, "operation": channel.operation, "parameters": _round_tree(dict(channel.parameters)),
            "reference_source_id_is_first_input_recording": True, "dependency_count": len(channel.dependency_ids)}


# ------------------------------------------------------------------------------------------------ scenarios
def scenario_rms_after_manual_change(client) -> dict:
    """An RMS channel at the recording's frequency, then a Manual change to 60 Hz, then back to Auto."""
    ws = f"{PREFIX}-rms"
    a = nf3d.upload(client, ws, "r50", 5000.0, 50.0, "50")
    out: dict = {"recording_before": nominal(client, ws, a)}
    made = create(client, ws, "rms_va_50", "rms", [src(a, "VA")], {"nominal_frequency_hz": 50})
    out["created_50"] = {"status": made["status"], "parameters": made["body"]["parameters"] if isinstance(made["body"], dict) else None,
                         "keys": sorted(made["body"]) if isinstance(made["body"], dict) else None}
    cid = made["id"]
    raw_before = inventory_raw(client, ws)
    out["before"] = {"inventory": inventory(client, ws), "waveform": waveform_summary(client, ws, cid), "stored": stored(client, ws, cid),
                     "accessor_for_channel": accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=cid)),
                     "equivalent_at_50": equivalent_rms(client, ws, ref(a, "VA"), 50.0), "equivalent_at_60": equivalent_rms(client, ws, ref(a, "VA"), 60.0)}
    out["put_manual_60"] = put_manual(client, ws, a, 60.0)
    out["inventory_unchanged_by_the_change"] = inventory_raw(client, ws) == raw_before
    out["after_manual_60"] = {"inventory": inventory(client, ws), "waveform": waveform_summary(client, ws, cid), "stored": stored(client, ws, cid),
                              "recording": nominal(client, ws, a),
                              "accessor_for_channel": accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=cid)),
                              "equivalent_at_50": equivalent_rms(client, ws, ref(a, "VA"), 50.0),
                              "equivalent_at_60": equivalent_rms(client, ws, ref(a, "VA"), 60.0)}
    new = create(client, ws, "rms_va_60", "rms", [src(a, "VA")], {"nominal_frequency_hz": 60})
    out["created_60_on_the_same_input"] = {"status": new["status"], "parameters": new["body"]["parameters"] if isinstance(new["body"], dict) else None}
    out["both_channels_afterwards"] = {"inventory": inventory(client, ws),
                                       "waveform_50": waveform_summary(client, ws, cid), "waveform_60": waveform_summary(client, ws, new["id"]),
                                       "equivalent_at_50": equivalent_rms(client, ws, ref(a, "VA"), 50.0),
                                       "equivalent_at_60": equivalent_rms(client, ws, ref(a, "VA"), 60.0)}
    out["put_auto"] = put_auto(client, ws, a)
    out["after_auto"] = {"inventory_names": inventory(client, ws)["names"], "recording": nominal(client, ws, a),
                         "waveform_50": waveform_summary(client, ws, cid),
                         "equivalent_at_50": equivalent_rms(client, ws, ref(a, "VA"), 50.0),
                         "equivalent_at_60": equivalent_rms(client, ws, ref(a, "VA"), 60.0)}
    return out


def scenario_dag(client) -> dict:
    """RMS -> Add -> Abs: a derived channel stores no frequency of its own; the walk goes through `dependency_ids`."""
    ws = f"{PREFIX}-dag"
    a = nf3d.upload(client, ws, "r50", 5000.0, 50.0, "50")
    rms = create(client, ws, "rms_va", "rms", [src(a, "VA")], {"nominal_frequency_hz": 50})
    add = create(client, ws, "add", "addition", [calc(rms["id"]), calc(rms["id"])])
    ab = create(client, ws, "abs", "absolute_value", [calc(add["id"])])
    out = {"created": {"rms": rms["status"], "add": add["status"], "abs": ab["status"]},
           "stored": {"rms": stored(client, ws, rms["id"]), "add": stored(client, ws, add["id"]), "abs": stored(client, ws, ab["id"])}}
    before = inventory_raw(client, ws)
    out["put_manual_60"] = put_manual(client, ws, a, 60.0)
    out["inventory_identical_after_change"] = inventory_raw(client, ws) == before
    out["inventory_fields"] = inventory(client, ws)["fields"]
    out["accessor_for_top_of_dag"] = accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=ab["id"]))
    out["waveforms_after"] = {n: waveform_summary(client, ws, i) for n, i in (("rms", rms["id"]), ("add", add["id"]), ("abs", ab["id"]))}
    delete = client.delete(f"/api/v1/workspaces/{ws}/calculated-channels/{rms['id']}")
    out["delete_of_an_input_is_blocked_while_a_dependent_exists"] = {"status": delete.status_code, "code": _json(delete)["body"]}
    return out


def scenario_two_recordings(client) -> dict:
    """An Add of RMS channels grounded in two recordings; only the NON-reference recording's frequency changes, then it is removed."""
    ws = f"{PREFIX}-mix"
    a = nf3d.upload(client, ws, "r50-a", 5000.0, 50.0, "50")
    b = nf3d.upload(client, ws, "r50-b", 5000.0, 50.0, "50")
    ra = create(client, ws, "rms_a", "rms", [src(a, "VA")], {"nominal_frequency_hz": 50})
    rb = create(client, ws, "rms_b", "rms", [src(b, "VA")], {"nominal_frequency_hz": 50})
    add = create(client, ws, "sum_ab", "addition", [calc(ra["id"]), calc(rb["id"])])
    out = {"created": {"rms_a": ra["status"], "rms_b": rb["status"], "sum": add["status"]},
           "reference_source_is_the_first_input_recording": client.app.state.calculated_channel_registry.get(ws, add["id"]).reference_source_id == a}
    out["put_manual_60_on_b_only"] = put_manual(client, ws, b, 60.0)
    out["accessor_for_sum"] = accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=add["id"]))
    access = client.app.state.nominal_frequency_access
    combined = access.for_sources(ws, [a, b])
    out["recordings_combined"] = {"status": combined.status, "common_hz": combined.common_hz, "distinct_hz": list(combined.distinct_hz)}
    out["inventory_after_change"] = inventory(client, ws)["names"]
    out["waveform_after_change"] = waveform_summary(client, ws, add["id"])
    removed = client.delete(f"/api/v1/workspaces/{ws}/sources/{b}")
    out["remove_non_reference_recording"] = {"status": removed.status_code}
    out["after_removal"] = {"inventory_names": inventory(client, ws)["names"], "waveform_of_sum": waveform_summary(client, ws, add["id"]),
                            "waveform_of_rms_a": waveform_summary(client, ws, ra["id"]),
                            "accessor_for_sum": accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=add["id"]))}
    return out


def scenario_remove_reference_recording(client) -> dict:
    ws = f"{PREFIX}-ref"
    a = nf3d.upload(client, ws, "r50-a", 5000.0, 50.0, "50")
    b = nf3d.upload(client, ws, "r50-b", 5000.0, 50.0, "50")
    ra = create(client, ws, "rms_a", "rms", [src(a, "VA")], {"nominal_frequency_hz": 50})
    rb = create(client, ws, "rms_b", "rms", [src(b, "VA")], {"nominal_frequency_hz": 50})
    add = create(client, ws, "sum_ab", "addition", [calc(ra["id"]), calc(rb["id"])])
    removed = client.delete(f"/api/v1/workspaces/{ws}/sources/{a}")
    return {"remove_reference_recording": {"status": removed.status_code},
            "inventory_names": inventory(client, ws)["names"],
            "waveform_of_rms_b": waveform_summary(client, ws, rb["id"]),
            "sum_still_present": client.app.state.calculated_channel_registry.get(ws, add["id"]) is not None}


def scenario_power_channels(client) -> dict:
    """Power channels store a fixed 50.0, on a recording of any frequency (NF-3F). Under 'stale = stored differs from effective' a 60 Hz
    recording's power channel would be stale at birth: the fact that matters for the staleness definition."""
    ws = f"{PREFIX}-pw"
    out = {}
    for key, fs, f, lf in (("r50", 5000.0, 50.0, "50"), ("r60", 5000.0, 60.0, "60")):
        sid = nf3d.upload(client, ws, key, fs, f, lf)
        made = create(client, ws, f"p_{key}", "active_power", [src(sid, "VA"), src(sid, "IA")])
        out[key] = {"status": made["status"], "stored": stored(client, ws, made["id"]) if made["id"] else None,
                    "recording": nominal(client, ws, sid),
                    "accessor": accessor_view(client, ws, ref(sid, "VA"))}
    return out


def scenario_frequency_independent_operations(client) -> dict:
    """Operations that do not use the frequency store none, so they can never be stale on their own account."""
    ws = f"{PREFIX}-ind"
    a = nf3d.upload(client, ws, "r50", 5000.0, 50.0, "50")
    out = {}
    for label, op, inputs, params, extra in (
        ("addition", "addition", [src(a, "VA"), src(a, "VB")], None, {}),
        ("subtraction", "subtraction", [src(a, "VA"), src(a, "VB")], None, {}),
        ("absolute_value", "absolute_value", [src(a, "VA")], None, {}),
        ("multiply_constant", "multiply_constant", [src(a, "VA")], {"constant": 2.0}, {}),
        ("reverse_polarity", "reverse_polarity", [src(a, "VA")], None, {}),
        ("rocof_override_not_given", "rocof", [src(a, "VA")], None, {}),
        ("rocof_with_override", "rocof", [src(a, "VA")], None, {"override": True}),
    ):
        made = create(client, ws, label, op, inputs, params, **extra)
        out[label] = {"status": made["status"],
                      "stored_parameters": stored(client, ws, made["id"])["parameters"] if made["id"] else made["body"]}
    return out


def scenario_unusable_recording(client) -> dict:
    """An RMS channel on a recording whose declared frequency is unusable: creation takes the explicit parameter; the accessor refuses."""
    ws = f"{PREFIX}-bad"
    sid = nf3d.upload(client, ws, "declared_zero", 5000.0, 50.0, "0")
    made = create(client, ws, "rms_bad", "rms", [src(sid, "VA")], {"nominal_frequency_hz": 50})
    out = {"recording": nominal(client, ws, sid), "created_with_explicit_50": {"status": made["status"]},
           "accessor_for_channel": accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=made["id"])) if made["id"] else None,
           "equivalent_rms_at_50": equivalent_rms(client, ws, ref(sid, "VA"), 50.0)}
    out["put_manual_60"] = put_manual(client, ws, sid, 60.0)
    out["after_manual"] = {"accessor_for_channel": accessor_view(client, ws, ChannelRef(kind="calculated", calculated_channel_id=made["id"])) if made["id"] else None,
                           "equivalent_rms_at_50": equivalent_rms(client, ws, ref(sid, "VA"), 50.0),
                           "equivalent_rms_at_60": equivalent_rms(client, ws, ref(sid, "VA"), 60.0)}
    return out


def scenario_rms_frequency_parameter_validation(client) -> dict:
    """Creation validates the explicit frequency (1-1000 Hz finite): frozen so NF-3E's builder work cannot loosen it."""
    ws = f"{PREFIX}-val"
    sid = nf3d.upload(client, ws, "r50", 5000.0, 50.0, "50")
    out = {}
    for label, value in (("missing", None), ("zero", 0), ("negative", -50), ("below_range", 0.5), ("above_range", 1001), ("string", "50"), ("bool", True), ("valid_60", 60)):
        params = {} if value is None else {"nominal_frequency_hz": value}
        made = create(client, ws, f"rms_{label}", "rms", [src(sid, "VA")], params)
        out[label] = {"status": made["status"], "code": made["body"].get("detail", {}).get("code") if isinstance(made["body"], dict) and isinstance(made["body"].get("detail"), dict) else None}
    return out


def run_all(client) -> dict:
    return {
        "rms_after_manual_change": scenario_rms_after_manual_change(client),
        "dag": scenario_dag(client),
        "two_recordings": scenario_two_recordings(client),
        "remove_reference_recording": scenario_remove_reference_recording(client),
        "power_channels": scenario_power_channels(client),
        "frequency_independent_operations": scenario_frequency_independent_operations(client),
        "unusable_recording": scenario_unusable_recording(client),
        "rms_frequency_parameter_validation": scenario_rms_frequency_parameter_validation(client),
    }
