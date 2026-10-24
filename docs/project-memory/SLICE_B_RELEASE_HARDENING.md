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

## Final validation and release status (2026-10-24)

**NO-GO. Focused fixes are committed; Slice B regression closure is not achieved.**
No push, deployment, VPS/configuration change or subsequent feature work occurred.

### Backend

- Full suite with `RELAY_SAMPLE_PDF_DIR=C:\Users\fairizat\Desktop`:
  **10,406 passed, 167 skipped, zero failures**, 1,606.51 seconds (26m46s).
- Skips: 49 require an unconfigured BEN reference directory, 17 require POSIX
  `sh`, 101 are relay-sheet/catalog applicability conditions. No new skips and no
  PDF-availability skips.
- All frontend guards plus backend timing/authority tests were checked after the
  final cancellation-wrapper refinement: **2,080 passed, 17 POSIX-shell skips**,
  201.88 seconds. Subsequent changes are test-only and documentation.
- Relay conformance with owner PDFs: **597 passed, 101 conditional skips**.
- Initial full backend: 10,405 passed, 167 skipped, one strict Event Reconstruction
  module-boundary failure. Using ER's own `loadSeq` instead of Waveform `epoch`
  corrected that boundary; the final full backend result above is green.

### Complete browser runs

Every run used four workers, zero retries and unchanged test/expect timeouts.

| Run | Passed | Failed | Skipped | Total | Duration |
| --- | ---: | ---: | ---: | ---: | --- |
| Initial | 1,132 | 12 | 0 | 1,144 | 38.6 min |
| Isolated follow-up | 1,140 | 6 | 0 | 1,146 | 37.3 min |
| Final candidate `5915223` | **1,142** | **4** | **0** | **1,146** | **2,010.92 s / 33.5 min** |

The initial run overlapped backend regression work for part of its duration.
The latter two ran independently against fresh local backend/frontend processes.
Two added cancellation tests account for the total changing to 1,146. JUnit labels
one final failure as `failure` and three as `error`; all four count as unsuccessful.
A shorter duration is not claimed as a controlled product-performance improvement.

Final full-run failures:

1. `analyser-recording-detection.spec.js:167`: upload/navigation/removal and
   re-navigation produced a console HTTP 404. Its exact request path was not
   captured by the original assertion. This is an unresolved lifecycle finding;
   the narrower deterministic metadata regressions do not establish full closure.
2. `ben5k-timezone.spec.js:43`, UTC case: application assertions passed; cleanup
   `DELETE /api/v1/workspaces/{id}` failed with `ECONNRESET`.
3. `oscillation_setup.spec.js:256`, raw V/I eligibility: application assertions
   passed; cleanup workspace DELETE failed with `socket hang up`.
4. `overcurrent_analysis.spec.js:1378`, independent minor-grid toggles: setup
   `GET /api/v1/workspaces/{id}/engineering-contexts` failed with `ECONNRESET`.

All five corrected follow-up readiness cases passed in the final full run:
Distance refused Apply, annotation movement, PU numeric comparison, Combined
Y-axis reset and Oscillation's strict global no-backend-request assertion.
GPTH/KTBR interpretation/alignment, Slice A authority/invalidation, Sequence and
new lifecycle/cancellation cases also passed. This does not override the four
failures or authorize release.

### Targeted regression evidence

- Lifecycle + timing/interpretation: **22 passed**, four workers, after final
  cancellation/body-consumption refinement.
- Lifecycle/workspace cancellation including the formerly flaky clear-while-
  playing case: **24 passed**, three repeats, four workers.
- Follow-up readiness cases: **15 passed**, three repeats of all five cases,
  four workers, 89 seconds. Intermediate test-barrier failures were corrected;
  inactive Phasor need not compute its desired playback time to finish transport.
- Source-removal diagnostic: **5 passed**, five repeats, four workers, 44.2 seconds.
  Failed-response method/path/status now appear in that test's assertion message.
  The 404 did not recur; this targeted success does not clear the full-run failure.
- Earlier wider timing/playback/navigation/analyser targets: **83 passed**.

### Follow-up corrections and performance evidence

The initial browser run exposed a late source `/channels` GET returning 404 during
workspace deletion. Pausing playback and aborting only Analysis was insufficient:
metadata uses separate transport. The existing session-header fetch wrapper now
composes caller cancellation with a workspace GET lifetime using native
`AbortSignal.any`, retained through response-body consumption. Reset aborts reads
before DELETE. Successful deletion leaves old reads blocked; failure restores
usable transport and preserves workspace state. No writes are cancelled or retried.
Expected metadata body `AbortError` means no cache update; other parsing failures
still propagate. Pre-request and post-header caller cancellation are tested.

The isolated follow-up's six failures additionally revealed premature Distance
snapshots, annotation redraw lag, expensive PU/axis polling and unrelated analyser
bootstrap overlapping Oscillation's request observation. Tests now wait for the
matching accepted Distance result, rendered annotation coordinates, axis metadata,
and existing bootstrap promises/transport completion. They do not issue extra
bootstrap queries. Numerical, pause, visibility, isolation and no-request assertions
remain intact.

A temporary Playwright benchmark of two 4,001-sample comparisons measured
11,762.58 ms for individual instrumented `toBeCloseTo` matchers versus 12.34 ms
for one maximum pointwise error assertion. Every sample and array length is still
checked at the same strict error bound `< 0.5e-9`. No PU calculation, setting or
measurement-model semantics changed. Polling readiness no longer copies complete
waveform arrays solely to inspect pending-axis flags.

### Unresolved causes and next closure steps

Intermittent API transport resets remain unexplained. They affect ordinary GETs,
POSTs in earlier runs, and cleanup DELETEs; a cleanup-only defect is not established.
No backend application traceback establishes their cause. A static-file server
`ConnectionAbortedError` in the final log describes a client disconnect and is not
proof of a backend API failure mechanism.

Local Playwright source uses shared keep-alive agents, but that is only a hypothesis.
A controlled local health-request probe, with server keep-alive TTLs of 1 and 5
seconds, returned 200 for both pooled and `Connection: close` clients in all eight
observations. It did not reproduce the reset. No retry, header workaround, timeout
increase or failure suppression was added.

Before another release check: capture the failing source-removal request using the
new path diagnostic; correlate API connection resets with server/request/socket
lifetimes; correct only reproduced causes and rerun the complete four-worker suite.
Five repeated diagnostic passes and serial reruns cannot authorize release.

### Commits and artifacts

Focused correction commits:

- `3c6495b`: source lifecycle, browser workspace cleanup/readiness, GRZ100 expectation.
- `e048cb4`: workspace metadata-read cancellation before deletion and follow-up readiness.
- `772de6a`: cancellation through response bodies and caller-signal coverage.
- `5915223`: accepted-result/render/bootstrap readiness and numeric assertion overhead.

The final report commit adds path diagnostics and current project-memory results.
Local JUnit/log artifacts are in the Windows temporary directory, named
`powerwave-slice-b-backend-final`, `powerwave-slice-b-browser-candidate`,
`powerwave-slice-b-readiness-confirm` and `powerwave-slice-b-removal-diagnostic`
(`.xml` / `.log`). These committed summaries are the durable evidence; temporary
artifacts are not required to interpret the result.

The unrelated BEN documentation stash remains
`2f39bdfbd7d2f3242825c42a9f9a20c5cb077c5a`. Approved session-only interpretation,
immutable raw data/samples, shared timebase, precision, grouping, offsets/t0,
V1 production authority and V2 shadow-only status remain unchanged.
