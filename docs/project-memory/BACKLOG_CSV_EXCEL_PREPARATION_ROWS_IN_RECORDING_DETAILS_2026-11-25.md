# Backlog item — CSV / Excel preparation rows are not listed in Recording Details

Recorded 2026-11-25 during PU-MIG P0 browser-test remediation. Status: **deferred, not an S2 blocker**
(owner decision, P0 remediation authorisation §8). No redesign of the CSV/Excel workflow is part of P0, no
production file was changed for it, and its failing tests were neither removed nor annotated.

## Observation

After a CSV or Excel upload the Recording Details recording list (`#wwRdRecordingList`) shows "No
recordings yet" instead of the preparation source. `preparationSourceAsRecordingRow()`
(`frontend/index.html`) has no caller, so a preparation source is never turned into a Recording Details row.
Identical behaviour on the deployed baseline `3ed200c` and on this branch (code of `e9c621c`): the issue is
pre-existing and unrelated to the PU migration. It is not a PU dependency: the per-unit test that prepares a
CSV (`per-unit-eligibility.spec.js`) prepares and converts the source through the API and then displays the
converted source in Waveform; it never needs the preparation row in Recording Details.

## Failing tests that carry the evidence (kept unchanged)

| File | Line | Test |
|---|---|---|
| `data-issues-estimate-fill.spec.js` | 2 tests | CSV preparation rows missing from the list |
| `data-preparation-sticky-header.spec.js` | 1 test | same |
| `sampling-rate-format.spec.js` | 1 test | same |

Evidence: the P0 baseline logs (`full_s1.txt`, `extra_b3ed.txt`, `extra_s1.txt` in the P0 scratch directory)
show the same first-error signature on `3ed200c` and on this branch.

## Not decided here

Whether preparation sources should appear in Recording Details (and how they are distinguished from
converted recordings), or whether the preparation workflow keeps its own entry point, is a product decision
for the owner. Do not infer it from the tests.
