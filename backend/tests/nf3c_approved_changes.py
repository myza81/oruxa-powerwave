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
from typing import Any

#: (baseline key, path inside "outcomes", frozen value, new value, matrix row / reason)
Change = tuple[str, str, Any, Any, str]

APPROVED_CHANGES: list[Change] = []


def apply_approved(document: dict, baseline: str) -> dict:
    """A copy of `document["outcomes"]` with this baseline's approved changes applied."""
    outcomes = copy.deepcopy(document["outcomes"])
    for key, path, before, after, _reason in APPROVED_CHANGES:
        if key != baseline:
            continue
        *parents, leaf = path.split("/")
        node = outcomes
        for part in parents:
            node = node[part]
        if node[leaf] != before:
            raise AssertionError(f"approved change {path!r}: the historical value is {node[leaf]!r}, not {before!r}")
        node[leaf] = after
    return outcomes


def changes_for(baseline: str) -> list[Change]:
    return [c for c in APPROVED_CHANGES if c[0] == baseline]
