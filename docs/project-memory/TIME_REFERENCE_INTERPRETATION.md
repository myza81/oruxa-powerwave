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
