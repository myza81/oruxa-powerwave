# Per-Unit audit remediation — Slice 2

Date: 2026-11-02. Scope: PU-008 and PU-005. Based on current local
`cc72cc7`, after fetching origin and confirming a clean tracked worktree.
The existing Slice 1 implementation (`498e8cd`) and its test-maintenance
commits remain intact. The original `.audit/per-unit-2026-10-31/AUDIT_REPORT.md`
(audit baseline `944e98f`) remains unchanged historical evidence.

## Implementation

**PU-005 fixed.** `wwApplyUnitMode()` publishes the valid mode and updates
the buttons synchronously. Source Default metadata is optional and no longer
delays that publication. There is still one mode authority, `ww.unitMode`.
A mode generation prevents an obsolete asynchronous refresh from regrouping
the newer display. Metadata reads separately reject obsolete request,
workspace, reset-epoch and source-catalogue identities; failures cannot choose
a mode.

**PU-008 fixed.** Both mode changes and successful base saves use
`wwRefreshWaveformDisplayBasis()`. It invalidates the affected sources' cursor
generations, clears their cached values and immediately repaints the cells
with the existing unavailable marker. It retires the old presentation arrays,
requests the current viewport arrays and enabled cursors, and accepts only
cursor responses matching the current request, workspace, reset epoch,
mode, timing fingerprint, owning cursor state and A/B times. Hidden or removed
channels cannot be republished by an older batch.

Existing batched cursor endpoints remain authoritative. No conversion is
performed in JavaScript. Disabled cursors issue no measurement request.
Source Default saves/clears and Measurement Group saves identify the affected
source, including calculated descendants, rather than refetching every source.
Group refresh starts after successful persistence without waiting for the
nonessential configuration-list repaint. A rejected save does not invalidate
or change the current display.

Waveform callouts and peaks have their own value snapshots and also consume
the Waveform display basis. Their refresh now uses a per-source display
generation and the existing anchor/peak endpoints. Pending values are cleared;
obsolete creations or responses are rejected. A callout value-only refresh
preserves its sample index, elapsed anchor, text and box offset. Peak selection
continues to use the existing viewport and engine. A request generation also
prevents a refresh from undoing a newer callout drag.

Zoom/pan remains available during a transition. Each channel tracks its
current load promise, so regrouping waits for a newer range request that
superseded the transition's original request. This avoids tearing down a
panel while its replacement data is still being loaded. The reset/workspace
guard belongs to the Waveform wrapper `wwFetchChannelRange()`, preserving
DEC-127's state-free shared renderer contract and Event Reconstruction's
separate adapter/state.

## Numerical and browser evidence

The fixture records the same instantaneous sample at A=0.005 s and B=0.015 s.
Expected values are calculated independently from the nominal L-L base and
the physical sinusoid, not from the application's conversion helpers.

| Display basis | Cursor A / B (approximately) | Rendered A / B |
|---|---|---|
| Engineering | +224.536559755125 / −224.536559755125 kV | 224.5 / −224.5 |
| PU, 275 kV nominal | +1.414213562373095 / −1.414213562373095 pu | 1.4 / −1.4 |
| PU, 132 kV nominal | +2.946278254943948 / −2.946278254943948 pu | 2.9 / −2.9 |

No cursor movement triggers these updates. A-only, B-only and both-visible
cases pass; the time difference remains 10.000 ms. A round trip compares every
engineering sample and time, viewport, t0 and cursor positions with the
original state. Every PU sample is compared with the independently derived
phase denominator. Live unit/axis wording is checked as well as cursor text.

The linked Current test independently uses
`Ibase_kA = 1000 / (sqrt(3) * nominal_kV)`: the 4.2 kA peak changes from
approximately 2.000519 pu at 275 kV to 0.960249 pu at 132 kV. A separate
manual group remains 3/1.5 = 2 pu; another Voltage group retains its own
132 kV base. A different source keeps its values and receives zero waveform
or cursor requests during the first source's base edit.

Calculated unary Voltage and Current cursors follow their established bases.
The representative Active Power channel remains in MW with independently
checked power and input identities. No eligibility rule is relaxed.

Controlled routes hold completed real backend responses: metadata, waveform,
cursor, callout and peak replies. The cases cover ENG→PU→ENG and
ENG→PU→ENG→PU, optional metadata failure, pending/unavailable cursor text,
obsolete response release, source removal, workspace reset and zoom during
refresh. Real group and Source Default editors cover accepted base changes
and clearing. Cursor positions and annotation anchor identities remain fixed.

## Verification

| Run | Passed | Failed/errors | Skipped |
|---|---:|---:|---:|
| Original five-case browser reproduction against frozen `cc72cc7` HTML | 0 | 5 | 0 |
| Independent base-edit reproduction with a correctly seeded PU cursor | 0 | 1 | 0 |
| Initial corrected five-case browser run | 5 | 0 | 0 |
| Focused final numerical/annotation/zoom cases | 5 | 0 | 0 |
| Final relevant browser suite, 27 explicitly selected files | 334 | 0 | 0 |
| New-case evidence rerun after adding explicit JSON output files | 26 | 0 | 0 |
| Full backend suite | 10,835 | 0 | 320 |

The new browser file contains 26 cases; all pass within the 334-case run.
Its final 26/26 evidence rerun retains JSON files containing full-precision cached
values, rendered strings, units, expected values and cursor times. These runs
overlap; their counts are not additive unique-test totals. Browser runs use
two configured workers, zero retries. Both untracked screenshot scripts are
excluded. The full repository browser suite was not run.

All 45 Slice 1 atomicity cases pass within the complete backend run. The
backend run includes 2,084 frontend static cases: 2,067 pass and 17 are
POSIX-only skips. There are 21 warnings. The 320 total skips comprise 153
unavailable owner-PDF references, 49 unavailable BEN references, 17 POSIX-only
checks and 101 relay applicability/metadata conditions. Exact reasons are
retained in `backend-skip-reasons.json`.

Intermediate verification is retained honestly: an expanded 20-case run had
two new-test formatting/selector mistakes; a 23-case run had two new-test
surface expectations; an initial 333-case run passed 331 and failed two
callout assertions that looked for numbers in the free-text note instead of
the annotation drawer. Their numerical cache checks already passed. Final
assertions check the correct surfaces with specific numbers and units.
The first all-frontend run found three contract checks: a shared helper read
Waveform state, its request-guard shape changed, and added code displaced a
fixed-width source assertion. The lifecycle guard was moved into the Waveform
wrapper, the shared contract restored, and the added code repositioned.
The directly relevant contract selection then passed 74/74. An earlier full
backend attempt was stopped after those discoveries; it is not counted as a
completed regression run. The final complete backend run exits 0.

Local evidence is in the isolated OS TEMP directory with prefix
`oruxa-pu-slice2-20261102-7ly356gz`: JUnit XML, runner logs, selected-file list,
final source hashes, numerical JSON and protected-file snapshots. Historical
audit/evidence directories are not test-output destinations. Windows
Playwright server teardown required stopping only each completed run's
verified temporary server descendants after its test workers exited; no
reported test was interrupted by that teardown.

## Compatibility, performance and limits

No backend production code, physical samples, PU formula, nominal-base
derivation, Measurement Group policy, Source Default precedence, legacy
configuration, calculated-channel mathematics, Sliding Phasor or Power
calculation changes. DEC-050/051/052/115/116 remain authoritative and unchanged.
Event Reconstruction already has its own synchronous mode switch, clears its
own cursor cache on unit-key changes and re-reads bases on page entry.
Compliance's existing post-save readiness refresh remains. Their regression
tests pass; neither feature is coupled to the Waveform mode.

Added requests are one existing batched cursor request per affected displayed
raw source, or the existing calculated-channel request per pseudo-source,
when cursors are enabled. There are no such requests when disabled. Existing
viewport-bounded waveform requests remain; no full-record reload is added.
Sources with peaks use their existing peak batch; callouts use their existing
anchor endpoint. The existing regrouping pass is retained, and obsolete mode
continuations cannot perform it. The backend's 500,000-sample regression
benchmarks pass their existing thresholds. No controlled before/after browser
latency benchmark or sustained load test was performed.

Refresh granularity is the affected recording and its calculated descendants.
Different Measurement Groups within that recording share the refresh; a new
frontend base/dependency resolver was deliberately not introduced. Existing
configuration callbacks trigger refreshes; no server-push observation of
external API writers is added. These limits do not change engineering results.
The conditional skips and unexecuted wider browser suite limit verification
as stated above. No unresolved introduced defect was found.

## Delivery and stop boundary

Only the frontend synchronization code, its directly relevant browser/static
tests and project-memory updates belong to this slice. Existing untracked
files and original audit evidence remain intact. Delivery is a dedicated
local commit; no push, merge or DEV/PROD deployment is authorized. Stop after
Slice 2 for owner review. No Slice 3 or other audit remediation is started.
