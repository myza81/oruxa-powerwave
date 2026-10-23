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
- First full backend with owner PDFs: 10,405 passed, 167 skipped, one failed
  (Event Reconstruction's strict module-boundary guard), 33m59.91s.
- First complete browser run: 1,132 passed, 12 failed, zero skips, four workers,
  zero retries, 38.6 minutes. Backend regressions also ran on the host during
  part of this run; final browser validation will run separately.

## Follow-up closure (2026-10-24)

The first browser run's twelve failures comprise five request transport failures
(ECONNRESET / socket hang-up, including two cleanup DELETEs), two test timeouts,
four readiness gaps and one late workspace GET returning 404. The connection
resets affect ordinary test GET/POST as well as cleanup; no backend traceback
establishes their cause. Playwright's local source uses shared keep-alive agents,
but an idle-socket race is only a hypothesis, not a confirmed root cause. No
request retry, timeout increase or failure suppression is introduced.

The architecture guard is corrected by capturing Event Reconstruction's own
`loadSeq`, preserving its boundary from Waveform state. Its full 165-test static
suite passes. Impedance pause checks now await the final accepted sample-time
fetch before testing stability. Event Reconstruction's isolation test awaits
initialized Waveform samples, axes and viewport before its before-state snapshot.
Post-upload Analysis checks await the populated Bay options; Data Issues clicks
use Locator's normal re-resolution rather than retaining a detached row during
an explicit scroll. Numerical, isolation and visibility assertions remain.

A three-repeat/four-worker targeted run passed 19 cases but reproduced the late
404 twice. Improved diagnostics identify the actual URL as a source `/channels`
GET. Pausing Playback and aborting only Analysis was insufficient: source metadata
uses a separate fetch. The existing session-header fetch wrapper now supplies a
workspace read lifetime to workspace GETs, composed with each caller's AbortSignal.
Start New Workspace aborts those reads before DELETE; successful deletion leaves
the old workspace blocked, failed deletion re-enables reads and preserves state.
No writes are retried or cancelled by this read-lifetime mechanism. The original
success/failure handling, immutable samples and effective timebase are unchanged.

Two additional lifecycle regressions cover an intercepted metadata GET and caller
cancellation. All lifecycle/cancellation cases including the previous flaky clear
while playing pass three repeats with four workers: **24 passed**. Final lifecycle + Slice A timing/interpretation: **22 passed**, four
workers. Full backend and isolated full four-worker browser results are pending. Release
remains NO-GO until final evidence is reviewed.
