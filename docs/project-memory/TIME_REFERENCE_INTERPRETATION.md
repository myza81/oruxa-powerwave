# Time Reference Interpretation

Status: owner-approved rules, 2026-10-23. Session-scoped recording interpretation;
implementation uses the existing source/workspace and synchronization architecture.
This document supersedes the initial architecture checkpoint and explicit-sync draft.

## Owner-approved contract

1. Selection belongs to one recording in one active browser page session. It is not
   recorder configuration, a device default or a persistent source correction.
2. Original timestamp digits/precision, uploaded bytes and normalized record timing
   remain immutable. Waveform samples, sample count, intervals and trigger offsets
   do not change.
3. Selecting a fixed UTC offset immediately updates the central effective source
   timebase. UTC+08:00 interprets recorder digits in UTC+08:00 and SUBTRACTS eight
   hours to derive UTC; it never adds eight hours to the original clock.
4. Waveform and all analyser timing consumers automatically use that effective
   reference through the shared timing interface. No second synchronization action,
   button, per-analyser clock offset or parallel alignment engine is introduced.
5. Existing Time Groups, manual offsets and event origin t0 remain consistent.
   Manual offsets remain independent and are applied exactly once. Group-coordinate
   state is rebased when effective timing requires regrouping.
6. Preserve Raw Time removes the interpretation and restores original authority.
   Unknown BEN5K returns to no canonical UTC and elapsed-only timing. Verified
   sources keep the existing source timezone/declared-offset policy.
7. No interpretation is persisted to server disk, browser storage, database,
   exported files or original recording. Only transient active workspace/page state
   exists in memory. It is not written into `DisturbanceRecord` or provider metadata.
8. Reload/new page/new session/another computer requires a new selection. Existing
   workspace/source identity may survive a reload; its interpretation does not.
9. Original source authority is separate from user-assigned provenance. User UTC
   does not become OEM-verified time and proves nothing about clock accuracy.
10. GPTH/KTBR automatic alignment and reset must be tested through backend APIs and
    real plotted browser sample coordinates, not only formatted metadata.

## UI and timebase contract

Recording Details / Timing contains one compact dropdown for an unknown source:
Preserve Raw Time, UTC, and fixed offsets UTC-12:00 through UTC+14:00 in 15-minute
increments (including 30/45-minute offsets). Known SubBen/COMTRADE sources are not
silently overridden. Recordings/sidebar/details retain the raw recorder clock and
label the selected offset as user assigned; Details separately shows derived UTC.
There is no recorder-specific assumption, fixed GPTH correction or waveform decoder
change.

The existing `SourceMetadata` gains optional `time_reference_interpretation`
(offset minutes, UTC assignment time, `user_assigned` provenance) and a timing
revision. Original `start_time`, `trigger_time`, `time_basis` and `timing_reference`
retain their original meaning. Source summary and timebase responses expose the
same effective `start_time_utc` / `trigger_time_utc`,
`effective_timing_reference`, interpretation and revision. Unknown without an
interpretation has null UTC companions. A shared domain resolver performs Python
microsecond datetime arithmetic. JavaScript Date is not used to derive engineering
UTC instants or the GPTH/KTBR placement difference.

`PUT /api/v1/workspaces/{workspace_id}/sources/{source_id}/time-reference`
takes `{ "offset_minutes": 480 }` (UTC+08:00), `0` (UTC), or `null` (restore raw).
Missing, non-integer, out-of-range, conflicting and unsupported fields are rejected.
Known authority, conflicting aware raw clocks, missing clocks or datetime overflow
cannot be silently replaced. Validation failure leaves current state unchanged.

## Session lifecycle

The page creates a fresh random nonce in memory on each document load and attaches
`X-Powerwave-Session` to workspace API requests. It never stores this nonce or the
interpretation in localStorage/sessionStorage. A request-scoped context projects
page-specific timing metadata from the existing WorkspaceRegistry; original source
metadata and record objects are retained by reference. Every analyser sees the same
projection through the normal registry interface. An isolated request context
prevents another page from inheriting the interpretation, even when it uses the
same workspace/source ids. The nonce is an isolation key, not authentication.

Workspace responses use `Cache-Control: no-store`. Page exit makes a best-effort
`DELETE .../sources/time-reference/session` request releasing only that page's
clock/t0 projections. A missed unload request cannot restore authority on reload:
the new page nonce is different. Source/workspace removal drops associated overlays;
process restart loses all transient state. The registry retains its existing
single-process/explicit-cleanup limitations; no database/file storage is added.

## Time Groups and state transitions

The existing timestamp-overlap/connected-component grouping function consumes the
effective timing reference and UTC start. Interpretation can merge/re-origin groups;
reset can split them. This is the same grouping algorithm used by verified sources.
No manual clock correction or second synchronization engine is layered on top.

Before publishing a time-reference change, derive old/new group placements and map
an existing t0 through a common source's native elapsed coordinates:

`t0_new = t0_old - old_effective_alignment(source) + new_effective_alignment(source)`

Effective alignment remains timestamp placement plus the existing manual scalar.
Manual scalar storage is never rewritten by interpretation. t0 changes are an atomic
page-local projection in the existing SynchronizationRegistry; they cannot leak
rebased coordinates into a reloaded page's original timebase. Frontend Cursor A/B
use the same placement delta. Unaffected groups retain their state. For merging
cursor pairs, an enabled pair from the surviving origin is preferred, then another
enabled pair; times are rebased through the common source. Layout/viewport bounds
are refreshed through existing Waveform paths.

Two existing t0 values that map to different instants cannot both define one merged
coherent time domain. The implementation rejects that interpretation atomically
with an actionable local error; it never silently chooses or drops an origin. The
existing t0 controls can reconcile the conflict. Ordinary interpretation requires
no extra alignment action. This edge condition is covered by a regression test.

A source timing revision invalidates shared signal catalogue tokens, analyser
results/in-flight generations and waveform/metadata/related-waveform caches. Settings
and context selections are retained; existing analyser navigation reloads fresh
results. Event Reconstruction reads the same timebase, while its own explicit
membership and manual corrections retain their existing independent semantics.
Restoring raw time makes an unknown reconstruction member unavailable for absolute
placement without deleting its correction. Cross-source calculation/readiness still
requires proven matching sample instants; display alignment never adds resampling
or weakens those engineering guardrails.

## Retained derived results: Slice A hardening (2026-10-23)

The release audit reproduced two correctness defects: a cross-source calculated
channel remained readable after its non-reference input returned to unknown time,
and a different page session could retrieve the same retained arrays without the
interpretations that made creation valid. Creation-time alignment checks alone
were insufficient. Impedance's locus signature also omitted timing authority;
Impedance and Sequence were absent from interpretation-change invalidation.

`calculated_timing_service.get_calculated_result` is the shared request-time gate.
It traverses every original input through the immutable calculation dependency
DAG, validates each intermediate calculation with the existing
`timebases_aligned` rule, and reads source metadata through the requesting page's
workspace projection. A calculated parent's reference source cannot conceal its
other input recordings. No session-independent validity cache or revision-number
shortcut authorizes arrays. Missing dependencies and cycles fail conservatively.
Single-source operations remain valid with elapsed-only timing.

The gate covers calculated waveform, cursor, peak and annotation-anchor APIs,
per-unit resolution, calculation/RMS input resolution, shared analyser readiness,
Overcurrent, Phasor (also Impedance/Sequence/Distance), Compliance and Oscillation's
shared calculation input reader. Incompatible result requests return the existing
HTTP 400 `incompatible_time_base` error; shared readiness reports
`timebase_incompatible`. No stale arrays are returned. A batch containing an
incompatible result fails rather than leaking that result among valid items.

Reproduction used two separate synthetic BEN5K imports with identical sample
instants, both interpreted as UTC+08:00 in page A, followed by an addition.
Resetting the second (non-reference) source previously left the retained waveform
GET at HTTP 200 although equivalent fresh creation rejected with HTTP 400.
Page B, with neither interpretation, also received HTTP 200. The initial two
regression tests failed on those exact assertions before the access gate; both
now receive HTTP 400. This is separate from the GPTH/KTBR display alignment
example: its 2.067 ms difference does not prove identical samples for calculation.

Affected API prefix: `/api/v1/workspaces/{workspace_id}/calculated-channels`.
Array/value access is `GET /{id}/waveform`, `POST /cursor-values`,
`POST /peak-values` and `POST /{id}/annotation-anchor`. The same gate protects
`GET /{id}/per-unit-resolution`, `POST /rms-eligibility` and calculated inputs
on `POST` creation. `GET` listing returns definitions plus live validity.
`inputs` supplies all operand references, `dependency_ids` supplies direct
calculated edges, and `reference_source_id` grounds the elapsed output axis;
the reference source alone never represents the complete dependency set.

Definitions remain listed and deletable. Additive catalogue fields are
`timing_status`, `timing_error`, `timing_source_ids` and `timing_fingerprint`.
The fingerprint includes every original source's effective UTC start, basis,
timing reference and revision. It is a cache token, never authorization.
Compatible interpretation restoration permits reuse of the original eager arrays:
operations never resample or change their elapsed sample axis, and matching sample
instants are proved again before access. No interpretation is stored in the
calculation definition or exported as new clock authority.

Frontend invalidation follows the changed recording and peers whose old/new Time
Group placement may change. It traverses calculated inputs, clears affected
Waveform/preview/related-waveform and Event Reconstruction trace caches, and
invalidates the existing request generations of Overcurrent, Phasor, Distance,
Impedance and Sequence. Impedance/Distance locus signatures include shared timing
fingerprints; calculated catalogue revisions include all original dependencies.
Source-specific fingerprints guard delayed waveform, annotation and metadata
responses. Analyser guards run before result and playback-cache writes. The existing busy
transport slot carries its owning request generation: an obsolete response can
release its own slot, including after a context change, but cannot clear a newer
request's busy state.
Compliance readiness/trace generations invalidate when their selected measurement
or reused calculated inputs depend on changed timing; its committed local event
origin is preserved. Oscillation uses the same catalogue revision guards for
derivations, spectra and comparison results. Independent manual analyser results
and request generations are retained even while hidden recording caches invalidate.
Reconstruction per-unit resolutions invalidate by affected key, preserving
unrelated cached resolutions and pending requests. Settings, definitions, manual
sync scalars and t0/cursor reconciliation use the existing architecture unchanged.
The global workspace epoch is not incremented for a recording interpretation;
unaffected contexts retain their cached results and request generations.

Regression evidence lives in `test_calculated_timing_authority.py` and
`timing-authority-invalidation.spec.js`: reset/restoration, cross-session access,
equal revision/different clock rejection, transitive inputs, single-source
compatibility, common analyser readers, UI trace clearing, late response rejection,
and unaffected cache stability. Existing GPTH/KTBR tests remain the automatic
2.067 ms alignment acceptance test in three browser timezones, including raw reset
and reload. Exact suite outcomes and remaining release blockers are in HANDOFF.

### Slice A regression evidence (2026-10-23)

- The original two calculated-access regressions failed before the backend fix:
  both stale/reset and other-session waveform requests returned HTTP 200.
- The obsolete-transport/context-change regression also failed before request
  ownership was added: its busy flag incorrectly remained set.
- New backend authority regressions: **16 passed** (including all result APIs,
  transitive inputs, equal revision/different clock sessions, restoration,
  single-source calculations and common analysis readers).
- Final focused browser run: **15 passed, 0 skipped**: 12 Slice A cases plus
  GPTH/KTBR alignment/reset/reload in UTC, New York and Kuala Lumpur.
- Full backend run with available owner PDFs: **10,399 passed, 167 skipped,
  3 failed, 10,569 total**. Two failures were structural assertions requiring
  the old no-argument refetch declaration / old transport guard text. Their
  expectations were updated for the scoped filter and stronger timing guard.
  The all-frontend-static plus authority follow-up passed **2,053 tests with
  17 platform skips**, including both corrected assertions and all 16 new
  backend cases (five of those were added after the full run collected).
- The remaining backend failure is
  `test_relay_conformance.py::test_the_relay_import_matches_its_expectation[grz100.real]`:
  four snapshot differences, beginning with catalog version expected `1.2.0`
  versus actual `1.4.0`. The release audit reproduced this on untouched baseline
  `3d16604`; Slice A changes neither catalogs nor relay expectations.
- Backend skips: 49 missing external BEN reference fixtures; 17 require POSIX
  `sh` on this Windows host; 43 V1 Apply-refused samples; 34 sheet-specific
  Apply-refused samples; 10 without relevant preserved geometry; 4 without a
  catalog; 3 handwritten/catalog extensions; 6 without applicable per-zone
  selector semantics; 1 without sheet notes. **No missing-owner-PDF skips.**
- Full relevant browser run, four workers, no retries: **691 passed,
  11 assertion failures, 11 timeouts, 0 skipped; 713 total** in 39 files.
  All 12 new Slice A cases and all three GPTH/KTBR cases passed in this run.
  All 22 unsuccessful cases passed when rerun serially (11 assertion cases
  and 11 timeout cases, each selected explicitly from JUnit results). This does
  not prove all 22 are pre-existing, and does not make the parallel run clean.
  No browser stability fixes are included in Slice A.
- Final verification against the frozen code: **2,080 passed, 17 skipped**
  across every frontend static guard, all 16 backend authority regressions and
  the 27 existing time-reference tests. Both corrected structural assertions pass.
  The 17 skips require POSIX `sh`; no new skip was added.

The unsuccessful broad-browser cases were:

| File | Case | Broad-run outcome |
|---|---|---|
| `analysis_related_waveforms.spec.js` | switching context clears the old bay's traces and shows the new one's | timeout |
| `compliance_measurement.spec.js` | the Bay select and readiness stay contained within the Measurement card at 800px | timeout |
| `compliance_readiness.spec.js` | kV reference: no per-unit blocker, no Configure Base, the unit row is calm | timeout |
| `compliance_workspace.spec.js` | Single plots only the named voltage | timeout |
| `compliance_workspace.spec.js` | Minimum / Maximum: the single reduced trace shifts | timeout |
| `distance_protection_analysis.spec.js` | Related Waveforms: AB loop pushes Va/Vb/Ia/Ib before pressing Play, then updates on loop switch | assertion |
| `distance_protection_analysis.spec.js` | Play advances the marker and grows the visible trail; zones stay static while it moves | assertion |
| `event-reconstruction-active-yaxis.spec.js` | 4 axes: click/select each, toolbar label, Y Zoom only that axis, others and X unchanged | timeout |
| `event-reconstruction-annotations.spec.js` | Text Note: placed in a panel, edited in place, moved, Grouped/Combined, Relative/Absolute, persisted, deleted | timeout |
| `event-reconstruction-combined.spec.js` | Pan is X-only on every axis; Zoom In/Out and Fit All clamp; double-click resets | timeout |
| `event-reconstruction-combined.spec.js` | Autoscale Y is per axis and ignores traces without samples; an empty axis keeps its title but invents no values | timeout |
| `event-reconstruction-per-unit.spec.js` | L-L/L-G regression: 275 kV L-L group base on an L-G channel -> 275/sqrt(3) kV, as Waveform's endpoints; quantity-aware axes in Grouped and Combined | timeout |
| `event-reconstruction.spec.js` | a removed record's member keeps its correction unapplied and is only removed explicitly | assertion |
| `impedance_analysis.spec.js` | Play advances the marker and grows the visible trail; Pause stops it | assertion |
| `oscillation_setup.spec.js` | selected identity is the catalogue key + revisions, not just the name | timeout |
| `phasor_analysis.spec.js` | no contexts + loaded source -> automatic suggestion populates the Bay selector | assertion |
| `playback.spec.js` | Clearing the workspace while playing stops Playback with no stale errors | assertion |
| `sequence_components_analysis.spec.js` | all six roles (V1/V2/V0/I1/I2/I0) share the identical vector rendering path | assertion |
| `sequence_components_analysis.spec.js` | mixed case, all six roles visible together: every role resolves its OWN dedicated color simultaneously | assertion |
| `sequence_components_analysis.spec.js` | hiding the dominant V1 does not change V2/V0's own rendered scale/position | assertion |
| `sequence_components_analysis.spec.js` | an angle entered as 200 degrees displays normalized to -160 degrees, never a second convention | assertion |
| `sequence_components_analysis.spec.js` | a dominant vector pointing toward the legend's own corner never overlaps it at 1366px | assertion |

Local JUnit evidence (under the test host's temporary directory, not committed):
`powerwave-slice-a-backend-full.xml`, `powerwave-slice-a-final-checks.xml`,
`powerwave-slice-a-browser-final-focused.xml`,
`powerwave-slice-a-browser-regression-final.xml`,
`powerwave-slice-a-browser-serial.xml` and
`powerwave-slice-a-browser-timeouts-serial.xml`.

Reproduction uses the existing test entrypoints; enable BEN5K on the local
browser-test backend (`BEN5K_EXPERIMENTAL_ENABLED=1`) and set `PW_PYTHON` to the
local environment's Python executable. Owner PDFs require the existing
`RELAY_SAMPLE_PDF_DIR` fixture setting; no deployment environment is changed.

```text
backend: python -m pytest
backend targeted: python -m pytest tests/test_calculated_timing_authority.py tests/test_time_reference_interpretation.py
browser targeted: npx playwright test timing-authority-invalidation.spec.js time-reference-interpretation.spec.js --workers=1
browser relevant: npx playwright test 'time-reference|timing-authority|ben5k-timezone|display-timezone|signal_catalogue|calculated-channel|analysis_related_waveforms|impedance_analysis|sequence_components_analysis|phasor_|overcurrent_analysis|distance_protection_analysis|event-reconstruction|oscillation_setup|waveform|playback|compliance' --workers=4
```

The owner explicitly authorized committing the focused correction with baseline
failures documented if Slice A regressions pass. This is not release approval:
Slice B, push, DEV/PROD deployment and VPS configuration changes remain excluded.

## GPTH / KTBR acceptance evidence

- GPTH raw trigger: `2026-10-16 18:03:14.535400` (timezone unverified).
- User selection UTC+08:00: effective `2026-10-16 10:03:14.535400Z`.
- KTBR verified UTC trigger: `2026-10-16 10:03:14.537467Z`.
- Both pre-trigger intervals: 2500 samples / 5000 Hz = 0.5 s.
- GPTH start: effective `10:03:14.035400Z`; KTBR start `10:03:14.037467Z`.
- Existing grouping chooses GPTH as earlier origin: GPTH placement 0, KTBR placement
  +0.002067 s. Relative to KTBR, GPTH is -0.002067 s. This is 2.067 ms, with no
  eight-hour manual correction.
- Preserve Raw Time restores GPTH's unknown authority and elapsed-only group.

This arithmetic and similar disturbance evidence do not verify GPTH's configured
timezone, clock synchronization, clock accuracy or same-event identity. Future
verified recorder metadata may establish original source authority separately.

## Validation and release

Backend tests cover offset ranges/fractions, rollover/microseconds, immutable record
and arrays, API validation, independent sessions, reload semantics, no-store/release,
shared epoch consumers, automatic grouping/reset, t0 rebasing, manual offsets once,
conflicting origins and Event Reconstruction compatibility. Browser tests cover
actual automatic Waveform positions, canonical metadata, Cursor A/t0, reset and
reload in UTC, America/New_York and Asia/Kuala_Lumpur. Actual GPTH/KTBR files were
also checked through isolated local API imports, with hashes unchanged.

Final full-suite counts and commit are recorded in HANDOFF. Commit and report first;
no push or combined DEV deployment is authorized by the final implementation ticket.
