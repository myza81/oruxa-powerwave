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
- Full browser four-worker, zero-retry validation is running; release remains **NO-GO**
  pending its outcome. Local artifacts: TEMP `powerwave-slice-c-browser-full.xml`,
  `.log`, and `powerwave-slice-c-browser-full-diagnostics/`; backend report
  `powerwave-slice-c-backend-full.xml`.

Approved session-only interpretation, immutable recorder timestamps/samples,
shared timebase, offsets/t0, calculation authorization, source isolation and relay
production/shadow/Apply safeguards are unchanged. No push, deployment or VPS change.
