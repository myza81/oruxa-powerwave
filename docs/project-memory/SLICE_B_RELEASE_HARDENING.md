# Release hardening Slice B - browser lifecycle and regression closure

Baseline: local `main` at `60d1f0c`, three commits ahead of fetched `origin/main`.
Owner scope: browser stability and GRZ100 regression closure; no push, DEV/PROD
release, VPS changes or further features. The BEN documentation stash is retained.

## Confirmed defects and focused corrections

Two deterministic browser reproductions failed before the production fix:

- A channels response held after HTTP success could arrive after source DELETE
  and repopulate `sourceChannelsData` / `sourceChannelInventory`.
- A failed DELETE response was treated as success, clearing source selection and
  local state without informing the user.

The source lifecycle now checks DELETE success before local cleanup, reports
failure through the existing error surface, records successful source removal,
and invalidates dependent timing work. Source metadata acceptance requires the
same workspace, workspace epoch, source timing generation and a still-live source.
Event Reconstruction member metadata applies the same workspace/liveness checks.
Waveform fetch scheduling rejects already-removed dependencies before issuing a
new request. Five deterministic tests cover delayed metadata after removal, failed deletion,
delayed metadata after replacing the workspace, the DELETE response window and
failed workspace deletion recovery. Workspace deletion pauses playback and aborts
shared analysis transport before DELETE, restoring usable transport on failure.
The held successful DELETE response reproduced a third production defect before
this ordering correction: analysis could request already-deleted resources.

These checks do not suppress HTTP failures. They do not change raw timestamps,
sample arrays, session interpretation, shared timebase, grouping, offsets or t0.
Slice A timing regressions remain part of validation.

## Test infrastructure findings

Fresh Playwright contexts already isolate page/session state. The old suite did
not delete backend workspaces when those contexts closed: pagehide correctly
releases only the interpretation, preserving recordings for reload. A shared
fixture now closes the context and then deletes its observed UUID workspaces on
the configured local test backend, checking cleanup responses. Every spec uses
this fixture. Production reload persistence is unchanged; no global registry
reset or cross-worker cleanup is used. Resource retention is confirmed by the
old teardown implementation; its contribution to individual historical timeouts
is not asserted as proven.

Sequence manual tests previously waited for role labels that could predate the
final API response, then immediately inspected vectors. The helper now waits for
the final input parameters' response and acceptance into state. Impedance and
Distance playback tests wait for trail growth instead of a fixed 700 ms delay.
Phasor bootstrap now holds its real suggestion request until the transient
identification state is observed, replacing a fixed 400 ms delay.
Existing numerical and pause-stability assertions remain. Retries stay zero and
suite/expect timeouts are unchanged. Full release validation uses four workers;
serial diagnostic passes cannot authorize release.

## GRZ100 expectation evidence

The real-sheet conformance harness identified exactly four differences: identity
catalog/profile versions, coverage catalog version, and shadow zone metadata.
Catalog 1.2.0 predates approved DEC-199 Phase 2I (1.3.0 left blinder) and Phase 3A
(1.4.0 trip-capability metadata). Only these expectation fields and their
independent equation goldens are updated. No protection implementation changes.

The owner's sheet supplies BFRS = 20 ohm and BFLS angle = 120 degrees. Existing
catalog OEM evidence (Toshiba 6F2S0834-0, section 2.6.1 / Fig. 2.6.1.9 and settings
page 34) supports right R(X) = 20 + X*cot(75 degrees), left R(X) = X*cot(120 degrees).
These are the previously approved family-level static-equivalent boundaries;
exact owner firmware equivalence is not newly claimed. The five forward zones'
V2 shadow regions now include both boundaries and the top, with no lower limit.
Independent test-only equation goldens are regenerated from those stated inputs.
The conformance harness confirms production counts, readiness, blockers, offers,
approximations and Apply are unchanged. V1 remains authoritative; V2 stays shadow
only, production geometry unsupported, Apply returns 409.

## Validation

- RED: two source lifecycle reproductions failed on the baseline.
- GREEN: lifecycle + Slice A timing/interpretation: 17 passed, four workers.
- Sequence readiness + lifecycle: 35 passed, four workers.
- Broader timing/playback/navigation/analyser targets: 83 passed, four workers.
- Final lifecycle (including workspace replacement): 3 passed, four workers.
- Relay conformance with owner PDFs: 597 passed, 101 conditional skips, no failures.
- Workspace deletion cancellation/recovery + Playback: 32 passed, four workers.
- Deterministic Phasor bootstrap: 1 passed.
- Full backend and full four-worker browser results: pending; release remains NO-GO.
