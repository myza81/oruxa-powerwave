# Slice C - transport and source lifecycle investigation

Baseline: `main` at `d286b6c`, clean after fetching origin, eight local commits ahead.
Owner scope: investigate the four Slice B failures; no push, deployment or VPS change.
BEN documentation stash retained: `2f39bdfbd7d2f3242825c42a9f9a20c5cb077c5a`.

## Confirmed lifecycle cause and correction

A context-list response fetched before source deletion could be published afterward.
The existing workspace epoch does not change for source removal; that guard alone
cannot establish that context members remain live. Publishing the old list restarts
Phasor/Sequence computation and analyser readiness against the deleted context.

A deterministic held-response reproduction on the baseline recorded:

- Context-list GET completed HTTP 200 approximately 53 ms before source DELETE.
- Source DELETE completed HTTP 204 (time origin).
- Phasor, readiness and Sequence GETs began 252-273 ms AFTER deletion completed.
- Those GETs returned actual HTTP 404, not cancellation or socket errors.
- No workspace switch or backend restart occurred.

Exact route suffixes: `/engineering-contexts/{id}/phasor-diagram`,
`/engineering-contexts/{id}/sequence-components` and
`/engineering-contexts/{id}/input-readiness`. Additional held-readiness and held-
source-list reproductions issued readiness GET and source suggestion POST after
removal. These prove a lifecycle defect independently of transport resets. The
historical Slice B console-only record lacks its URL, so identity with that exact
historical request cannot be established retroactively.

The shared context lifecycle now captures the existing `wwTimingCatalogueGeneration`
when loading contexts, checking readiness or discovering uncovered sources. A
catalogue change rejects obsolete publication/continuation before another request.
There is no new timing model, analyser-specific timing logic or global HTTP-error
suppression. Source/workspace generation guards retain their existing roles.

All three new deterministic regressions FAIL against the exact `d286b6c` frontend
served from a temporary copy over normal localhost HTTP. The initial intercepted-
document comparison blocked browser API access and is excluded from RED evidence.

## Evidence so far

- Initial affected scenarios: **60 passed**, ten repeats, four workers, 3.3 minutes,
  default HttpToolsProtocol and five-second keep-alive. No reset/404 captured.
- Lifecycle + timing/authority initial target: **23 passed**, four workers, 60 seconds.
- Final deterministic cases and affected scenarios: **27 passed**, three repeats,
  four workers, 1.5 minutes. No unexpected HTTP failure or connection error.
- Prior Slice B full run: 1,142 passed, four unsuccessful, four workers, zero retries.
  One console 404; cleanup resets in BEN5K/ Oscillation; setup GET reset in Overcurrent.

## Confirmed transport mechanism

The API resets are separate from the HTTP-404 lifecycle defect. Pinned Playwright
1.62.1 uses process-shared keep-alive agents. Disposing and replacing an API context
does not empty that pool. Its free sockets had no bounded idle lifetime, while the
unchanged Uvicorn server expires idle connections after five seconds. A new request
can acquire a socket at the server's idle-expiry boundary and fail before ASGI sees it.

Controlled socket/server-correlated probes established:

- Default five-second server expiry: 4 resets in 20 GET operations, all reused sockets.
- Paired concurrent GET/DELETE comparison, same five-second server setting and load:
  policy absent **7/40 failures** (4 DELETE, 3 GET); policy present **0/40 failures**.
- Failed sockets correlate with server keep-alive expiry/connection loss. There is
  no ASGI request start for the failed operation and no process restart or app error.
- A shortened 30 ms probe produced 133/600 resets; this amplifies the race and is
  not an estimate of ordinary-suite failure frequency.
- The original 60-case target included 15 cleanup API contexts reusing existing
  sockets. A fresh API context therefore was not sufficient socket isolation.

This establishes a shared method-independent mechanism for the BEN5K cleanup
DELETE, Oscillation cleanup DELETE and Overcurrent setup contexts GET reset class.
Their historical Slice B logs did not capture socket identity, so each historical
connection cannot be reconstructed retroactively. Neither process exhaustion nor
application DELETE logic is needed to reproduce these failures. Slice B's earlier
negative eight-observation probe did not disprove this boundary race.

## Focused test infrastructure correction

`support/local_backend_transport.js` bounds FREE registered-loopback sockets to
four seconds, before the existing five-second server expiry. It decorates only the
observed Agent instance using Node's documented `keepSocketAlive` / `reuseSocket`
hooks. Active request timeout is restored on reuse; warm pooling remains enabled.
Other hosts/ports are unaffected. A monotonic pre-dispatch check retires overdue
free sockets when a busy worker has delayed timer delivery. It reads `freeSockets`
without mutating the pool; Node owns removal. No Playwright private bundle patch,
retry, Connection: close, request timeout increase or worker reduction is involved.

Primary reference: [Node 24 Agent hooks](https://nodejs.org/docs/latest-v24.x/api/http.html#agentkeepsocketalivesocket).

The timer-only draft failed a deterministic blocked-client-loop test; adding the
pre-dispatch deadline check made it pass. Five transport regressions cover warm
reuse/other ports, idle retirement, active headers/body budgets, original request
deadline without retry, and delayed timer delivery. An initial combined target
had two new-test readiness assumptions fail under concurrent backend load: expecting
100 ms warm reuse, and assuming a 200 ms deadline always reaches the server. Tests
now gate active responses and accept zero or one server invocation while retaining
the exact original timeout assertion. These were harness-test assumptions, not
application failures. Final combined evidence below supersedes that attempt.

Opt-in `PW_DIAGNOSTICS_DIR` diagnostics correlate browser/API requests, worker and
context phases, socket ports/reuse/FIN/close, ASGI status, idle expiry and PID lifetime.
They exclude headers, query strings, nonces, body contents and uploaded files.
Normal startup without that flag still uses the original Uvicorn factory command;
explicit five-second keep-alive documents its unchanged default.

## Validation and release

- Three deterministic lifecycle cases fail against the baseline and pass corrected.
- Diagnostics-off lifecycle + timing/authority targets: **25 passed**, four workers.
- Final combined lifecycle/transport/four affected scenarios: **42 passed**, three
  repeats, four workers, zero retries (1.6 minutes).
- Full backend with owner PDFs: **10,406 passed, 167 skipped, 20 warnings** (1232.59 s).
  Skips: 49 unavailable BEN-reference directory, 17 POSIX-only, 101 relay applicability.
- Full browser candidate `0b9f295`: **1,151 passed, 3 failed, 0 skipped**, four
  workers, zero retries, unchanged assertions, **2320.747 s / 38.7 minutes**.
  All four original failure scenarios passed (six cases including three BEN5K zones).
  All eight added lifecycle/transport cases passed. The complete timing interpretation
  and authority tests also passed. One backend start/PID was observed, with no ASGI
  request exception, Node HTTP error, or API ECONNRESET/socket-hang-up event captured.
- The three failures are the additional Compliance, Event Reconstruction and playback
  blockers detailed below. Release remains **NO-GO**; there is no full regression
  closure or deployment authorization. No serial rerun is used to clear them.
- Local artifacts: TEMP `powerwave-slice-c-browser-full.xml`, `.log`, and
  `powerwave-slice-c-browser-full-diagnostics/`; backend report
  `powerwave-slice-c-backend-full.xml`. Committed summaries preserve the findings
  independently of these temporary machine-local files.

Implementation commits: `bf67e3c` (shared context lifecycle) and `0b9f295` (local
transport ownership and diagnostics). The final report commit changes documentation
only. Workspace route prefix for the lifecycle endpoints above is
`/api/v1/workspaces/{workspace_id}`; suggestion requests use
`/sources/{source_id}/engineering-contexts/suggest` under that prefix.

Approved session-only interpretation, immutable recorder timestamps/samples,
shared timebase, offsets/t0, calculation authorization, source isolation and relay
production/shadow/Apply safeguards are unchanged. No push, deployment or VPS change.


## Newly observed release blocker outside the four Slice C failures

[FACT] The full four-worker run failed `compliance_workspace.spec.js:508` at line
523: two consecutive Later clicks should display `0.547 s`, but display `0.548 s`.
All four alignment PUTs returned HTTP 200; there was no reset or HTTP failure.
The final two PUT requests began at epoch 1792829265.429 and .477; their responses
arrived at .508 and .578. Thus the second request began before the first response.
`wwComplianceFineShift` derives an absolute origin from the current acknowledged
`wwComplianceState.alignment` and starts `wwComplianceCommitAlignment` without
serializing mutations. The observed overlap and one-step result are consistent
with both clicks using the same old origin. Diagnostics deliberately omit bodies,
so no request-body equality is claimed from the trace alone.

Issue: rapid Compliance fine shifts can lose a step while an update is in flight.
Evidence: exact unchanged assertion above, overlapping successful PUT lifecycle,
and the existing read/derive/async-commit code at `wwComplianceFineShift`.
Proposal (not implemented or approved): serialize fine-shift intents and derive each
origin after the previous update is acknowledged, with a deterministic held-response
regression. Benefits: preserve every requested step and ordered UI/backend state.
Risks: must handle failure, group changes and cancellation without applying an intent
to another alignment. Expected impact: Compliance alignment mutation lifecycle only;
no recorder interpretation or waveform timing change. This is outside the four
requested Slice C corrections and remains a separate owner-scoped follow-up.


[OPEN] The same full run also failed `event-reconstruction-grouped.spec.js:204`
at line 229: STN_B cursor A displayed `0.0` instead of `No sample`. Its diagnostic
record contains 53 browser request starts and 53 responses, no HTTP-error status
and no API transport error; workspace cleanup succeeded. The assertion reads
cursor row values after a predicate that checks presence of cursor B objects.
The available trace does not establish whether the unexpected value originated
in timing resolution, cursor sampling, or acceptance/readiness. No root cause is
asserted and no Event Reconstruction correction is included. This remains an
additional release blocker requiring a separately bounded investigation.


[OPEN] `playback.spec.js:916` also failed at line 948: `delta4x` was
1.7265999999761568, while the required lower bound `delta1xAgain * 2` was
2.9808000000000057. API setup/cleanup succeeded; no HTTP-error status or API reset
was captured for this test. The existing test places automation actions and fixed
300 ms waits between time reads, but does not measure the actual wall duration of
each segment. This observation does not prove whether engine rate or test scheduling
caused the ratio failure. No playback code, assertion or wait was changed; the
cause remains unconfirmed and release remains blocked.
