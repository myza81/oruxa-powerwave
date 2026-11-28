"""The explicitly approved NF-3E behaviour changes, as data, applied to frozen historical baselines (never edited).

Same discipline as `nf3c_approved_changes.py`: a historical baseline records what the code did; an intentional change is one visible entry
here (the path, the frozen value it must still have, the new value, the owner decision that approved it), and the comparison tests require
current output == history + these changes. Every unchanged value is therefore proved unchanged.

Changes (owner, 2026-11-27, NF-3E Phase B):

* **O-10** -- an invalid user-supplied nominal frequency is a typed client error (400 `invalid_nominal_frequency`) at the RMS eligibility
  pre-check, as it already is at creation. It was an unhandled HTTP 500 for 0 (division by zero) and a 200 classification for -50, 0.5 and
  1001 Hz. Valid frequencies are unchanged.
* **O-6 / provenance** -- a new RMS channel created through the API records `nominal_frequency_basis` (the caller-declared intent; omitted =
  `explicit`) and the recording's `nominal_frequency_origin` and `nominal_frequency_revision`; every calculated-channel response carries
  the derived, read-only `frequency_staleness` object. Additive: no existing field changes and no value is recomputed.
* **PU-MIG S5 (NF integration, 2026-11-28)** -- every per-unit response object carries the additive `per_unit_verification_state` field
  that PU-MIG S5 added on `main` (owner-accepted, DEV UAT 2026-11-27). It is `null` for these calculated-channel scenarios (no verification
  claim is made for them). The R0 baseline was frozen before S5 existed, so the field is applied here as one visible, additive entry; the
  frozen history is not edited and nothing else in any of these payloads changes (proved by a leaf-level diff at integration time).
"""

from __future__ import annotations

import copy

_INVALID_FREQUENCY_MESSAGE = "Nominal frequency must be a finite number in a sensible range (e.g. 50 or 60)."
ELIGIBILITY_400 = {"body": {"detail": {"code": "invalid_nominal_frequency", "message": _INVALID_FREQUENCY_MESSAGE}}, "status": 400}
SERVICE_RAISES = {"ok": False, "error": {"type": "InvalidNominalFrequencyError", "message": _INVALID_FREQUENCY_MESSAGE,
                                         "code": "invalid_nominal_frequency"}}

#: (group, key, frozen value (checked), new value, reason)
R0_API_CHANGES = [
    ("rms-eligibility/instantaneous/0", {"body": "Internal Server Error", "status": 500}, "O-10: a zero frequency is a 400, not an HTTP 500"),
    ("rms-eligibility/instantaneous/-50", None, "O-10: a negative frequency is invalid input (was a 200 classification)"),
    ("rms-eligibility/instantaneous/0.5", None, "O-10: below the 1-1000 Hz range (was a 200 classification)"),
    ("rms-eligibility/instantaneous/1001", None, "O-10: above the 1-1000 Hz range (was a 200 classification)"),
]
R0_SERVICE_CHANGES = [
    ("frequency", "eligibility/frequency=0.5", {"eligibility": {"override_required": False,
     "reason": "Input is explicitly marked instantaneous. Input appears suitable for RMS.", "status": "suitable"}, "ok": True},
     "O-10: the eligibility authority validates the frequency range exactly as creation does"),
]

_CHANNEL_KEYS = {"operation", "parameters", "dependency_ids", "reference_source_id"}
#: What an RMS channel created through the API on the R0 recordings (frequency declared 50 Hz, recording_metadata, revision 0, no Manual)
#: records and reports under NF-3E. `explicit`: the R0 callers pass only the number.
_STAMP = {"nominal_frequency_basis": "explicit", "nominal_frequency_origin": "recording_metadata", "nominal_frequency_revision": 0}
_STALENESS = {"assessment": "inherited_only", "causes": [], "state": "current"}


def _stamp_channels(node):
    if isinstance(node, dict):
        if _CHANNEL_KEYS <= set(node) and node["operation"] == "rms":
            assert "nominal_frequency_basis" not in node["parameters"], "the historical record already carries the NF-3E stamp"
            node["parameters"] |= _STAMP
            node["frequency_staleness"] = copy.deepcopy(_STALENESS)
        for value in node.values():
            _stamp_channels(value)
    elif isinstance(node, list):
        for value in node:
            _stamp_channels(value)


def _add_pu_verification_state(node):
    """PU-MIG S5: the additive `per_unit_verification_state` (null for calculated-channel responses) beside the reference compatibility."""
    if isinstance(node, dict):
        if "per_unit_reference_compatibility" in node:
            assert "per_unit_verification_state" not in node, "the historical record already carries the PU-MIG S5 field"
            node["per_unit_verification_state"] = None
        for value in node.values():
            _add_pu_verification_state(value)
    elif isinstance(node, list):
        for value in node:
            _add_pu_verification_state(value)


def apply_r0(outcomes: dict) -> dict:
    """The R0 behavioural baseline's `outcomes` with the NF-3E approved changes applied (a deep copy; the history is untouched)."""
    out = copy.deepcopy(outcomes)
    for key, frozen, _reason in R0_API_CHANGES:
        if frozen is not None:
            assert out["api"][key] == frozen, f"{key}: the historical value is no longer what the approved change expects"
        out["api"][key] = copy.deepcopy(ELIGIBILITY_400)
    for group, key, frozen, _reason in R0_SERVICE_CHANGES:
        assert out["service"][group][key] == frozen, f"{group}/{key}: the historical value is no longer what the approved change expects"
        out["service"][group][key] = copy.deepcopy(SERVICE_RAISES)
    _stamp_channels(out["api"])
    _add_pu_verification_state(out["api"])
    return out


# ---------------------------------------------------------------------------------------------------- Phase A baseline (NF-3E)
#: The Phase A record was frozen before these additive changes. Its channels are created with an explicit `nominal_frequency_hz` only, so
#: they are `explicit` (never stale); a channel created after the Manual change records the Manual origin and revision.
_PHASE_A_RMS_KEYS = {"nominal_frequency_hz", "rms_kind", "window_mode"}


def _stamp_phase_a(node, stamp):
    if isinstance(node, dict):
        if _PHASE_A_RMS_KEYS <= set(node) and "nominal_frequency_basis" not in node:
            node |= stamp
        for value in node.values():
            _stamp_phase_a(value, stamp)
    elif isinstance(node, list):
        for value in node:
            _stamp_phase_a(value, stamp)


def _add_staleness_field(node):
    if isinstance(node, dict):
        if "inventory_fields" in node:
            node["inventory_fields"] = sorted(node["inventory_fields"] + ["frequency_staleness"])
        if {"fields", "names", "channels"} <= set(node) and node["fields"]:
            node["fields"] = sorted(node["fields"] + ["frequency_staleness"])
        for value in node.values():
            _add_staleness_field(value)
    elif isinstance(node, list):
        for value in node:
            _add_staleness_field(value)


def apply_phase_a(outcomes: dict, *, include_nf3f: bool = True) -> dict:
    """The NF-3E Phase A baseline's `outcomes` with the approved additive changes applied (a deep copy); the NF-3F power-channel entries
    (O-2, `nf3f_approved_changes.json`) apply last."""
    out = copy.deepcopy(outcomes)
    manual = {"nominal_frequency_basis": "explicit", "nominal_frequency_origin": "manual", "nominal_frequency_revision": 1}
    after_manual = out["rms_after_manual_change"]
    created_60 = after_manual["created_60_on_the_same_input"]["parameters"]
    created_60 |= manual
    for channel in after_manual["both_channels_afterwards"]["inventory"]["channels"].values():
        if channel["parameters"].get("nominal_frequency_hz") == 60.0:
            channel["parameters"] |= manual
    _stamp_phase_a(out, _STAMP)
    # the list/create response gains the derived `frequency_staleness` object: every field list and the created channel's key list
    _add_staleness_field(out)
    keys = after_manual["created_50"]["keys"]
    after_manual["created_50"]["keys"] = sorted(keys + ["frequency_staleness"])
    if include_nf3f:
        from tests.nf3c_approved_changes import nf3f_entries
        from tests.nf3d_diff_tools import apply_entries
        out = apply_entries(out, nf3f_entries("nf3e_phase_a_baseline"))
    return out
