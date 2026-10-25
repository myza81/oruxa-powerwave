# Slice D - final three browser regressions

Baseline: local `main` at `9137afa`, clean after fetching origin, eleven commits
ahead of origin. Scope: the three Slice C assertion failures; no push, deployment,
VPS configuration or unrelated feature work. BEN documentation stash retained:
`2f39bdfbd7d2f3242825c42a9f9a20c5cb077c5a`.

## Compliance: ordered user intent over replacement semantics

The API `PUT /api/v1/workspaces/{id}/compliance/voltage/event-alignment` explicitly
replaces `measurement_event_origin_s`. `set_alignment` validates a supplied finite
absolute value and stores it; there is no backend increment or read-modify-write.
Two UI Later clicks previously read the same acknowledged frontend alignment and
submitted the same absolute replacement while the first acknowledgement was pending.
Both HTTP 200 responses were legitimate replacements, but one user intent was lost.

A held-success regression failed before correction: final origin was one step from
the initial value, instead of two, despite both requests returning HTTP 200. A
second deterministic case found delayed measurement-traces JSON could overwrite a
newer acknowledged alignment. Its initial network-idle barrier was insufficient;
awaiting the actual fetch/acceptance promise made the baseline failure reproducible.

Frontend mutations now share an ordered promise chain. Fine shifts derive their
absolute replacement only after the preceding mutation is acknowledged. Set/Clear
retain replacement semantics and order. Failed writes preserve acknowledged state,
report failure and do not poison subsequent operations. Workspace/group generation
checks reject obsolete acknowledgements; group cleanup follows already-sent writes.
Trace snapshots may initialize alignment only when no intervening mutation occurred
and no alignment write was pending at fetch start or acceptance. No endpoint, schema,
backend arithmetic, step size, Reference position or recording data changes.

## Event Reconstruction: current coordinates require current sample authority

The original grouped test waited only for truthy cursor-B objects. Old values from
previous cursor coordinates remained present until the next response arrived, so
that predicate could accept a stale genuine zero while cursor A was already outside
the recording. The backend correctly reported `sample_time: null` at the new native
time. This was stale frontend sample authority, not a zero/missing-value conversion.

The held-response reproduction first verifies B's genuine zero at its own first
sample, then moves A before B's start. The baseline displays the old zero while
the held response reports out-of-range. Changed cursor coordinates now invalidate
old values immediately, including throttled movement; requests also clear affected
values until acceptance. An unchanged coordinate keeps its existing cache. Request
identity and live cursor coordinates augment the existing sequence guard, preventing
pre-reset sequence reuse or a response arriving during the drag throttle window from
restoring old values. The backend's nearest-sample result remains authoritative:
valid zero stays `0.0`, a real null sample is `Unavailable`, out-of-range is
`No sample`, and pending/unshown values use the existing dash placeholder.

Regression coverage also moves a non-reference record beneath a fixed cursor using
its existing correction, resets it, and verifies no-sample/zero restoration. No new
synchronization layer, time-origin arithmetic, interpolation or sample changes.

## Playback: deterministic evidence, unchanged production controller

Untouched three-scenario baseline run: **7 passed, 2 failed**, three repeats/four
workers. Both failures were the mid-play speed case: a nominal-interval rate ratio
failed, and another run reached end-of-record before an asserted Pause state.
The old test assumed automation actions plus a 300 ms wait consumed identical wall
time in each segment. It did not measure those wall intervals and could exhaust the
four-second fixture. Background/loaded scheduling can delay frame delivery; there is
no separate visibility clock or visibility handler in the controller.

Inspection confirms one `requestAnimationFrame` chain and `performance.now` anchor,
with `currentTime = recordingAnchor + elapsedWallSeconds * speed`, end clamping,
and existing re-anchoring on speed change. These production semantics are unchanged.
The test-only `support/playback_clock.js` delivers controlled irregular frames to
the real mounted control handlers and the unchanged shared controller. It never
supplies a fabricated playback position or an engineering sample. Clock/rAF overrides
exist only inside one synchronous browser evaluation and restore in `finally`.

On unchanged production code, both deterministic rate cases passed all three repeats
(**6 passed**, four workers). Exact 1x/4x/1x rates, continuous position, unchanged
controller generation, unchanged frame chain on switching and one controller loop
are asserted. The original ratio (>2) and constant-rate bounds (2x..7x) remain;
exact rate checks add stricter evidence. Existing real-browser playback interaction,
pause/resume/seek and analyser coverage remain in the regression suite.

## Validation status

- Exact baseline frontend `9137afa` was served from a fresh temporary copy with
  unchanged assets and real local backend. All **five deterministic lifecycle tests
  failed on their intended assertions**: one lost step despite two successful writes,
  an old trace restoring the prior origin, stale genuine zero during out-of-range
  lookup, old pre-reset cursor values (69.2) accepted during a newer pending lookup,
  and old-group acknowledgement accepted after changing the Bay.
- First combined corrected target: **21 passed**, three repeats/four workers.
- Expanded corrected targets: **30 passed**, three repeats/four workers (1.5 min).
  They include the three original scenarios, all added lifecycle cases, failed-write
  recovery, synchronization correction/reset and exact playback rates.
- Relevant backend/domain/frontend architecture checks: **457 passed**, 3 warnings.
- Full backend regression with owner PDFs: **10,406 passed, 167 skipped,
  20 warnings** (23m25s).
- Selected timing/Waveform/Compliance/Playback browser rerun: **103 passed**,
  four workers and zero retries, after the approved Waveform readiness change.
- Complete isolated browser run: **1,159 passed, 1 failed, 0 skipped** out of
  1,160 cases, four workers, zero retries (42.8 min). The sole failure was the
  Overcurrent minor-grid default case below; the three named Slice D scenarios,
  their new lifecycle cases and the approved Waveform readiness case passed.
- Latest complete browser run on the approved adjacent test candidate:
  **1,158 passed, 2 failed, 0 skipped** out of 1,160 cases, four workers,
  zero retries (31.3 min). The exact two test-readiness failures are recorded
  below; neither involves a changed product calculation.
- The owner-approved Distance and per-unit readiness corrections passed
  **10/10** across five repeats/four workers. The next complete run finished
  **1,158 passed, 2 failed, 0 skipped** out of 1,160 cases, four workers,
  zero retries (27.7 min). Both corrected cases passed; Relay Apply viewport
  parity and GPTH/KTBR plot readiness failed as documented below. Those two
  cases passed **12/12** in a subsequent focused four-worker rerun.
- The approved Relay Apply and GPTH/KTBR readiness corrections passed
  **20/20** across five repeats/four workers. The next complete run finished
  **1,156 passed, 4 failed, 0 skipped** out of 1,160 (four workers, zero
  retries, 25.6 min). Both corrected cases passed; four separate failures
  are described below.
- Release remains **NO-GO** while the complete browser suite has a failure.

Invalid setup runs are excluded: one confirmation launched from the repository root
without its Playwright config; one first cursor test used an incorrectly encoded
dash literal before correction. An expanded-target run had **27 passed, 3 failed**
because the new cursor-reset fixture omitted its required start clock; upload was
correctly rejected, and the fixture was corrected without changing assertions.

Artifacts are local TEMP files prefixed `powerwave-slice-d-`. Completed results and
final Git state will be recorded before the final documentation commit. Session-only
time interpretation, immutable raw timestamps/waveforms, GPTH/KTBR placement,
manual offsets/global t0, calculation authorization and V1/V2/relay Apply authority
retain their approved contracts.


## Additional findings in broader validation (not silently cleared)

The relevant four-worker browser run completed **172 passed, 2 failed, 0 skipped**
(174 cases, 6.4 minutes). It overlapped backend regression work, using separate
local test processes/storage. All three named Slice D scenarios and new focused
cases passed. The complete browser run will be isolated from backend pytest load.

1. `event-reconstruction-time-display.spec.js:249`: the initial Waveform snapshot
   had `ticktext: undefined` and no Time Group viewport; the later snapshot had
   rendered labels and a viewport. Its fixed 500 ms initial wait did not establish
   plot readiness. The owner approved a focused test correction: the fixed wait
   is replaced by the existing plot/data/label/viewport readiness condition.
   Both strict state equality assertions remain. The corrected test passed five
   repeats with four workers (36.1 s). An initial patch had a syntax typo and
   collected no tests; it was fixed before this successful run.
2. `event-reconstruction-navigation.spec.js:327`, failing `zoomTo` at line 358:
   viewport never matched the requested [4.5, 5.5] within the existing assertion
   budget after resetting a correction. Its cause is not established. No navigation
   or synchronization correction is included, and no scheduling/resource hypothesis
   is promoted to a confirmed root cause. Both adjacent cases passed all six
   baseline comparison cases (three repeats/four workers, 40.5 s). This does not
   prove that the navigation failure pre-existed Slice D. The navigation case
   passed in the later 103-case rerun and full 1,160-case run. A separate
   temporary diagnostic held its reset DELETE before sending it; the original
   viewport wait was already satisfied while Event Reconstruction was busy and
   B still had its old 2.005 s offset (1/1 probe passed). This proves the test
   can advance before reset completion. It is a plausible cause of the earlier
   lost zoom, though the earlier failed request was not captured at that exact
   instant. A proposed test-only fix waits for B's 2.000 s offset before the
   next zoom. The owner approved this test-only correction; five repeats at four
   workers passed after the change.

The later full run's sole failure was
`overcurrent_analysis.spec.js:1345`: after values loaded and minor toggles were
unchecked, an immediate `count()` found zero major SVG gridlines. The page
snapshot showed the selected ALPHA1 context and numeric values, so the values
readiness helper had completed; it does not await SVG rendering. The adjacent
axis test already waits for major-gridline render. A proposed test-only change
polls the same `> 0` gridline assertion without loosening it. The owner
approved this test-only correction; five repeats at four workers passed after
the change. No Overcurrent product code was changed or engineering result
declared wrong from this snapshot.

The two approved adjacent cases passed together in **10/10** repeated runs at
four workers (1.4 min). A subsequent full attempt stopped externally at
**655/1,160** when the session was interrupted; it is not a completed-suite
result. Before interruption it recorded four different failures:

- `analysis_related_waveforms.spec.js:116` had an invalid no-active-roles
  premise. Upload-time discovery selected an ALPHA1 context with six plotted
  roles. The owner approved clearing that disposable fixture's contexts using
  the existing test helper; all empty-state assertions remain.
- The next Related Waveforms case timed out in `page.goto` before making an
  application API request. It ran in a replacement worker after the first
  failure. No page-load cause was proven.
- Two Event Reconstruction annotation cases reached the 30-second test limit
  before their engineering assertions completed. In the first, the final
  definition GET started at 29.85 s, returned HTTP 200 during teardown, and
  its response object was disposed; the longest captured request was about
  1.3 s. The second timed out before clicking a channel row. No annotation
  result was shown incorrect, and no timeout/retry change was made.

After the owner-approved Related Waveforms fixture correction, these four
cases plus the approved navigation and Overcurrent readiness cases passed
**18/18** in three repeats/four workers (1.7 min). A fresh complete browser
run with standard test services finished **1,158 passed, 2 failed, 0 skipped**
out of 1,160 cases, four workers, zero retries (31.3 min). All three named
Slice D cases and the approved adjacent readiness/fixture cases passed.

The two final-run failures are separate test-readiness defects outside the
named Slice D scope. The owner approved both test-only patches; they passed
**10/10** together across five repeats/four workers (47.4 s):

1. `distance_protection_analysis.spec.js:212`: the manual phasor input fields
   showed the intended golden values, but the result still displayed an older
   `110.0 Ω`, `+30.00°`. The test's wait regex for `10.0 Ω` also matches the
   tail of `110.0 Ω`, allowing it to advance before the golden result arrives.
   The applied patch waits for the `|Z|` row to show `10.0 Ω` and the Angle
   row to show `+20.00°` in the same retry. V1 calculation code is untouched.
2. `event-reconstruction-per-unit.spec.js:296`: `zoomTo(1.2, 2.6)` did not
   retain the requested viewport after clicking a 7 ms correction on STN_B.
   That click starts an asynchronous mutation. The earlier held-request probe
   proved this architecture can expose the old viewport while a correction is
   still pending; the applied patch waits for B's authoritative 1.007 s
   offset before zooming. This is a test setup readiness change only; the
   ENG/PU timing invariants and product timebase remain unchanged.

The next complete browser run finished **1,158 passed, 2 failed, 0 skipped**
out of 1,160 cases (four workers, zero retries, 27.7 min). Both approved
Distance and per-unit cases passed. The two different failures were:

1. `relay_import_apply.spec.js:114`: equal applied and manually entered zone
   values produced SVG `polygon.points` differing by about 20 times. The test
   reads pixel positions in the automatic R-X viewport, whose scale includes
   the current analysis result as well as zone reach. It did not establish the
   same viewport before comparing pixels. The captured manual page had the
   expected secondary basis and zone settings. No production geometry defect
   has been established.
2. `time-reference-interpretation.spec.js:19` under Asia/Kuala_Lumpur:
   canonical and interpreted API timestamps and the 2.067 ms placement passed;
   the later Waveform first-sample difference was `NaN`. The test read plot
   arrays while on Recordings after interpretation without waiting for the
   rebuilt Waveform plot. The captured page showed correct recorder-clock
   presentation and user-assigned UTC+08:00 interpretation. No wrong
   alignment value was observed.

Both cases passed in a focused **12/12** four-worker, zero-retry rerun (three
repeats per case/timezone variant, 1.0 min), so the failures remain sensitive
to full-suite timing. The owner approved two focused test-only corrections:
Relay Apply now invokes the existing Fit Zones action before each SVG snapshot,
fixing the comparison viewport while preserving exact polygon equality; the
GPTH/KTBR test waits for finite first samples from both recordings after
interpretation before asserting the same 2.067 ms plotted separation. No
product code or engineering assertion changed. The corrected target passed
**20/20** across five repeats/four workers, zero retries (1.2 min). Both
corrected cases passed in the next complete browser run.

That complete browser run finished **1,156 passed, 4 failed, 0 skipped** out
of 1,160 cases (four workers, zero retries, 25.6 min). Both newly approved
cases passed. The four different failures were:

1. `distance_protection_analysis.spec.js:532`: the R-X geometry test waited
   for `/10.0+ Ω/` without checking the golden +20° angle. The regex also
   accepts `110.0 Ω`. It then read a point that did not have the golden R/X
   ratio, so its golden-coordinate cross-product failed. The captured assertion
   does not identify which partial phasor result was displayed.
2. `event-reconstruction-fit-record.spec.js:294`: backend member extent had
   advanced to 3.5 s, but Fit Record used the browser's still-old 3.0 s
   definition. The existing helper's axis wait accepts any internally
   consistent viewport, including the old one. This reproduced once in a
   three-repeat/four-worker comparison (14/15 passed overall).
3. `event-reconstruction.spec.js:816`: a console error reported HTTP 404
   after source removal, but that console-only message did not identify its
   request path or initiation sequence. Twenty focused repeats with existing
   path-only transport diagnostics passed without a 404. Its cause remains
   unknown; there is no 404 suppression or speculative fix.
4. `sequence_components_analysis.spec.js:401`: the captured page had Manual
   selected and Va=77 V/5° entered, but the Values list displayed complete
   Recording sequences instead of the incomplete Manual result. The Manual
   result request had completed. Inspection found that an already-in-flight
   Recording analysis response can still call `wwSequenceRenderResult(result)`
   after the input source changes; it does not check the live input source at
   acceptance. This is an application result-lifecycle defect, not proof that
   the sequence calculation itself is wrong.

The full-suite result remains **NO-GO**. No correction for these four cases is
included without the owner approval required by Change governance.

The interrupted attempt's three timeout symptoms were
also absent from both completed full runs, but their exact causes were not
established. Release remains **NO-GO**; no claim of complete browser regression
closure is made.

The first issue is not evidence of Event Reconstruction mutating a completed
Waveform plot; the before snapshot was explicitly incomplete. The held-request
probe identifies a real navigation test readiness gap, while the precise
sequence in the earlier failed run remains unobserved. Neither targeted passes
nor a later full-run pass erase the recorded earlier failure.
