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

## Transport investigation remains open

Opt-in local diagnostics correlate browser/API requests, worker/context/cleanup
phases, Node HTTP socket reuse/local ports, ASGI response status, server peer ports,
keep-alive expiry and process lifecycle. They exclude headers, query strings,
session nonces, request/response bodies and uploaded contents. Application use and
cleanup are labeled separately. No retry, Connection: close or timeout/worker
change is introduced.

One server PID handled the 60-case run. Normal keep-alive expiry and browser
cancellation were observed; no application request exception or process restart.
A sampled backend working set was approximately 156 MB with 436 handles. This does
not establish a peak or rule out every resource issue. Playwright uses shared
keep-alive agents; a socket-idle race remains a hypothesis pending an actual failed
socket/server correlation. Slice B's eight controlled keep-alive observations were
negative and are not treated as proof of the cause.

The three transport failures are not classified as the same defect as the confirmed
HTTP-404 lifecycle race. Cause of each reset remains unknown pending further evidence.

## Validation and release

Normal-startup, full browser and backend regression validation remain pending.
Release remains **NO-GO**. Approved session-only interpretation, immutable recorder
timestamps/samples, shared timebase, offsets/t0, calculation authorization, source
isolation and relay production/shadow/Apply safeguards are unchanged.
