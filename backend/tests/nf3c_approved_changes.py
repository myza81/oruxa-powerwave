"""The explicitly approved Auto-mode behaviour changes of NF-3C, as data.

`tests/fixtures/nf3b_baselines/nf3b_frozen_baselines.json` (2,971 values, NF-3B) and
`tests/fixtures/nf3c_baselines/nf3c_pre_migration_baseline.json` (NF-3C Phase A) are HISTORICAL records of what the code did. They are
never edited. NF-3C changes some of those outputs on purpose (the owner's O-6/O-7/O-11 decisions and the NF-3C before/after matrix); each
such change is one entry here: the path in the baseline, the frozen value, the new value, and the matrix row that approved it. The
comparison tests apply these entries to the historical record and require the current outputs to equal the result, so

* every value NOT listed here must be exactly what it was (unchanged outputs are proved, not assumed);
* every change that IS listed is visible, reasoned and reviewable;
* an entry whose frozen value no longer matches the historical record fails loudly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).parent / "fixtures"
_NF3B = "nf3b_frozen_baselines"
_NF3C = "nf3c_pre_migration_baseline"
_R1A = "comtrade_frequency_baseline"
_HISTORY = {
    _NF3B: json.loads((_FIXTURES / "nf3b_baselines" / "nf3b_frozen_baselines.json").read_text(encoding="utf-8"))["outcomes"],
    _NF3C: json.loads((_FIXTURES / "nf3c_baselines" / "nf3c_pre_migration_baseline.json").read_text(encoding="utf-8"))["outcomes"],
    _R1A: json.loads((_FIXTURES / "comtrade_frequency" / "comtrade_frequency_baseline.json").read_text(encoding="utf-8"))["outcomes"],
}

#: (baseline key, path inside "outcomes", frozen value, new value, matrix row / reason)
Change = tuple[str, str, Any, Any, str]


def _at(baseline: str, path: str) -> Any:
    node: Any = _HISTORY[baseline]
    for part in path.split("/"):
        node = node[part]
    return copy.deepcopy(node)


#: `before` value of an entry that ADDS a field the historical record does not have.
ABSENT = object()

APPROVED_CHANGES: list[Change] = []

# --- OC-1 / OC-2: an unusable declaration is never handed to the form detector -----------------------------------------------------------
# The shared input classifier answers "do not guess" (None) instead of raising (0, NaN, +/-infinity) or classifying a value outside the
# NF-1 range (1001 Hz). The measurement and readiness endpoints therefore give EXACTLY the answer they already gave for a declared -50 or
# 0.5 Hz (the unresolved/incompatible state), not an HTTP 500 and not an "available" classification.
_UNUSABLE = {
    "declared_zero": ("raises", "ZeroDivisionError"),
    "declared_nan": ("raises", "ValueError"),
    "declared_inf": ("raises", "ZeroDivisionError"),
}
for _recording, (_kind, _cls) in _UNUSABLE.items():
    APPROVED_CHANGES.append((
        _NF3B, f"in_process/{_recording}/compliance_measurement_input_type", {"raises": _cls}, {"returns": None},
        "OC-1: the classifier no longer raises for an unusable declared frequency; it answers 'do not guess'"))
APPROVED_CHANGES.append((
    _NF3B, "in_process/declared_1001/compliance_measurement_input_type", {"returns": "rms"}, {"returns": None},
    "OC-2: 1001 Hz is outside the NF-1 range (1-1000 Hz) and is no longer classified"))

for _group in ("compliance_measurement_http", "compliance_readiness_http"):
    for _recording in ("declared_zero", "declared_nan", "declared_inf", "declared_1001"):
        APPROVED_CHANGES.append((
            _NF3C, f"{_group}/{_recording}", _at(_NF3C, f"{_group}/{_recording}"), _at(_NF3C, f"{_group}/declared_negative_50"),
            "OC-1/OC-2: an unusable declaration now behaves exactly as the already-unresolved declared -50 Hz (HTTP 200, 'unresolved'/'incompatible')"))


# --- OC-7 / OC-8 / O-6: the oscillation origin carries the NF-1 provenance, and results carry the revision ------------------------------------
# `nominal_frequency_origin` (owner decision O-6, option A): an unusable declaration is `unusable` (it used to be labelled recording_metadata);
# a BEN upload-supplied value is `import_supplied` (the owner's "Supplied at import"). The reported frequency, status and reason code of every
# recording are unchanged. `nominal_frequency_revision` is a new additive field (0: no engineer value has ever been stored).
_UNUSABLE_OSC = ("declared_zero", "declared_nan", "declared_inf", "declared_negative_50", "declared_0_5", "declared_1001")
for _recording in ("declared_zero", "declared_nan", "declared_inf", "declared_negative_50", "declared_0_5", "declared_1001"):
    if _recording in _HISTORY[_NF3B]["in_process"]:
        APPROVED_CHANGES.append((
            _NF3B, f"in_process/{_recording}/oscillation_representation/returns/nominal_frequency_origin", "recording_metadata", "unusable",
            "OC-8/O-6: an unusable declaration is labelled `unusable`, not `recording_metadata`"))
for _recording, _entry in _HISTORY[_NF3C]["oscillation_representation_http"].items():
    if _recording in _UNUSABLE_OSC:
        APPROVED_CHANGES.append((
            _NF3C, f"oscillation_representation_http/{_recording}/body/nominal_frequency_origin", "recording_metadata", "unusable",
            "OC-8/O-6: an unusable declaration is labelled `unusable`"))
    APPROVED_CHANGES.append((
        _NF3C, f"oscillation_representation_http/{_recording}/body/nominal_frequency_revision", ABSENT, 0,
        "O-6: additive nominal_frequency_revision (0 = no engineer value stored)"))
for _label, _entry in _HISTORY[_NF3C]["ben_import_supplied_http"].items():
    if _label.startswith("supplied"):
        APPROVED_CHANGES.append((
            _NF3C, f"ben_import_supplied_http/{_label}/oscillation_representation/body/nominal_frequency_origin", "recording_metadata", "import_supplied",
            "OC-7/O-6: a BEN upload-supplied frequency is `import_supplied` (the owner's label: Supplied at import)"))
    APPROVED_CHANGES.append((
        _NF3C, f"ben_import_supplied_http/{_label}/oscillation_representation/body/nominal_frequency_revision", ABSENT, 0,
        "O-6: additive nominal_frequency_revision"))


# --- the R1A COMTRADE baseline: the oscillation analysis's recorded (frequency, origin) pair --------------------------------------------
# Only the ORIGIN of an unusable declaration changes (`recording_metadata` -> `unusable`); the recorded frequency never does.
def _usable(text: str) -> bool:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return False
    return 1.0 <= value <= 1000.0 and value == value


for _key, _entry in _HISTORY[_R1A]["api"].items():
    _pair = _entry.get("oscillation_frequency_and_origin")
    if _pair and _pair[1] == "recording_metadata" and not _usable(_pair[0]):
        APPROVED_CHANGES.append((
            _R1A, f"api/{_key}/oscillation_frequency_and_origin", list(_pair), [_pair[0], "unusable"],
            "OC-8/O-6: an unusable declaration is labelled `unusable`; the recorded frequency is unchanged"))


NF3D_MANIFEST = _FIXTURES / "nf3d_baselines" / "nf3d_approved_changes.json"


def nf3d_entries(baseline: str) -> list[dict]:
    """The NF-3D approved changes for one baseline (path tuples, before/after, kind, matrix row); empty before the manifest exists."""
    if not NF3D_MANIFEST.exists():
        return []
    return json.loads(NF3D_MANIFEST.read_text(encoding="utf-8"))["changes"].get(baseline, [])


def apply_approved(document: dict, baseline: str, *, include_nf3d: bool = True) -> dict:
    """A copy of `document["outcomes"]` with this baseline's approved changes applied.

    NF-3C entries apply to the historical record first; NF-3D entries (`nf3d_approved_changes.json`, recorded against the record AFTER the
    NF-3C overlay) apply second, so each slice's changes stay separately reviewable."""
    outcomes = _apply_nf3c(document, baseline)
    if include_nf3d:
        from tests.nf3d_diff_tools import apply_entries
        outcomes = apply_entries(outcomes, nf3d_entries(baseline))
    return outcomes


def _apply_nf3c(document: dict, baseline: str) -> dict:
    outcomes = copy.deepcopy(document["outcomes"])
    for key, path, before, after, _reason in APPROVED_CHANGES:
        if key != baseline:
            continue
        *parents, leaf = path.split("/")
        node = outcomes
        for part in parents:
            node = node[part]
        if before is ABSENT:
            if leaf in node:
                raise AssertionError(f"approved change {path!r} adds a field the historical record already has")
        elif node[leaf] != before:
            raise AssertionError(f"approved change {path!r}: the historical value is {node[leaf]!r}, not {before!r}")
        node[leaf] = copy.deepcopy(after)
    return outcomes


def changes_for(baseline: str) -> list[Change]:
    return [c for c in APPROVED_CHANGES if c[0] == baseline]
