"""D5A-2B2C-1B: test support for recorded Impedance / Distance fixtures.

The recorded sides and the VT/CT of a recorded calculation come from Recording Details, never from the request. The older
fixtures upload hand-built ASCII recordings whose channels are all flagged `P` (Primary), and their tests mean "this recording is
on the secondary side". `declare_sides` says so the way an engineer does -- a Level 1 recording correction (and, where a
conversion is needed, the VT/CT of the Measurement Groups that own the channels) -- instead of passing a request parameter.
"""

from __future__ import annotations


def declare_sides(client, workspace_id, source_id, side="secondary", *, ratios=None):
    """Declare the recorded side of `source_id` (Level 1) and, with `ratios=(vt_primary, vt_secondary, ct_primary, ct_secondary)`,
    the VT and CT of its Voltage and Current Measurement Groups (re-using the groups upload already created)."""
    # Imported here: the test modules these helpers live in import the very fixtures that call this one.
    from tests.test_d5a2a_protection_instrument_context_api import _ct, _group, _vt
    from tests.test_d5a_ui_002_group_measurement_side import _set_rec

    _set_rec(client, workspace_id, source_id, side, "test recording side")
    if ratios is None:
        return
    groups = client.app.state.measurement_group_registry.list_for_source(workspace_id, source_id)
    by_kind = {g.kind: g.id for g in groups}
    for kind, names in (("voltage", ("VA", "VB", "VC")), ("current", ("IA", "IB", "IC"))):
        if kind not in by_kind:
            by_kind[kind] = f"{kind[:1]}g-{source_id}"
            _group(client, workspace_id, source_id, kind, names, by_kind[kind])
    _vt(client, workspace_id, by_kind["voltage"], ratios[0], ratios[1], note="test VT")
    _ct(client, workspace_id, by_kind["current"], ratios[2], ratios[3], note="test CT")
