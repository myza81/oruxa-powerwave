# P3 DEV UAT — peak, lower time ruler and measurement cursors

Owner-accepted correction on `fix/ben5k-gpth-slow-p3`, following approved decoder
commit `ff1209d98a3d9e8b43eab0bf068176cb69a4cba2`. On 2026-11-17 the owner
authorized local commit, push to the existing branch, PR #11 description update
and confirmation of CI for the new head. PR #11 must remain open/unmerged.
Owner DEV UAT is **not accepted** pending retest. DEV/PROD deployment, merge and
any further BEN stage remain unauthorized.

## Confirmed root causes

**Peak calculation is correct.** `waveform_service.resolve_peak_value()` reads
the stored full-resolution engineering column. `_peak_in_range()` clips the
requested visible interval inclusively, ignores non-finite samples and selects
the signed maximum/minimum, preferring the earliest exact tie. It does not select
maximum absolute magnitude. The default full view requests `[0, 70.05]` seconds.

The original SHA-pinned GPTH CFG/DAT independently gives a maximum at sample 382,
`19.100 s`, `-220.0586231772 MW`. Native import/API returns
`-220.05862319469452 MW`, within the established printed-coefficient tolerance.
The full record is negative. Thus `+Peak: -220.1 MW` has a correct number and a
misleading sign-like label. The minimum is sample 404, `20.200 s`,
`-493.5232864822 MW` independently / `-493.5232865214348 MW` natively.

The backend response carries the original sample index, elapsed seconds, signed
value and `MW` unit. `wwCreatePeakFromClick()` stores these unchanged. The shared
annotation projection uses the owning Time Group's ruler for X and the channel's
panel for Y. Browser tests place the peak by clicking the actual trace and check
the visible SVG marker against those rendered axes, as well as the callout text.
The existing one-decimal engineering formatter explains `-220.1`; no precision,
sign, power scaling, selection or peak-service change is required.

**The lower labels were minutes, not a normalized 0–1 domain.** The real lower
axis and waveform both had numeric domain `[0, 70.05]` seconds. For a view at
least 60 seconds long, `wwStickyRulerElapsedUnit()` alone divided tick text by 60:
ticks at 0/20/40/60 seconds became `0/0.333/0.667/1`. The main waveform remained
in seconds. `wwSyncTimeGroupRuler()` also supplied a plain-string `xaxis.title`
to the bundled Plotly, which requires `{text: ...}`; its resolved title was the
placeholder `Click to enter X axis title`, and no actual unit title was shown.
Both defects are shared presentation behavior and reproduce independently of
BEN decoding. The range slider's internal fractional positioning is intentional
and already converts through the true group bounds; it is unchanged.

**No A/B numerical defect was found.** Backend cursor resolution searches the
source's actual full-resolution time array and chooses the nearest real sample,
with earlier-sample ties. It never derives an index from a frontend nominal rate
or interpolates engineering values. Browser tests drag the actual A/B handles,
wait for the corresponding value response and assert rendered readouts, units
and sample values. A repeated formatted value at different samples is not treated
as proof that the asynchronous response has arrived.

## Before/after and time conventions

| Point | Elapsed time | Independent MW | Native MW |
|---|---:|---:|---:|
| Sample 0 | 0.000 s | -257.7002297733 | -257.700229793787 |
| Sample 382, full-record maximum | 19.100 s | -220.0586231772 | -220.058623194695 |
| Sample 404, full-record minimum | 20.200 s | -493.5232864822 | -493.523286521435 |
| Sample 1401 | 70.050 s | -397.6497927588 | -397.649792790413 |

| Presentation | Before | Local correction |
|---|---|---|
| Maximum header/value | `+PEAK` / `+Peak: -220.1 MW` | `MAXIMUM` / `Maximum: -220.1 MW` |
| Maximum time | `t = 19.100 s` | unchanged |
| Minimum wording | `-PEAK` / `-Peak` | `MINIMUM` / `Minimum` |
| Lower labels, full GPTH view | `0, 0.333, 0.667, 1`, unit absent | `0, 20, 40, 60`, visible `Time (s)` |
| Numeric X domain | `[0, 70.05]` seconds | unchanged |
| A/B engineering values and units | native recorded values, MW | unchanged |

The existing status/readout convention shows zero as `0.000 ms`; this is exactly
0 seconds, not an offset. Subsecond ruler views retain their explicitly labelled
milliseconds. Long elapsed/event views now retain seconds. Absolute/record-clock
mode keeps its existing clock labels and now displays the valid title.

GPTH's 400 pre-trigger samples correspond to 20 elapsed seconds, but do not
automatically redefine elapsed zero. The recorder clock remains UNKNOWN. Setting
event t0 explicitly uses the user's Cursor A position, which may lie between
samples; it does not snap or rebase the native arrays. Tests set/clear t0 through
the real toolbar, check the shifted axis, and confirm that the last sample still
resolves at native `70.050 s`. No alignment is inferred or invented.

## Exact implementation and coverage

Only `frontend/index.html` changes at runtime:

- `wwAnnotationCategoryLabel()`, `wwPeakValueLineText()` and `wwPeakBodyHtml()`
  use Maximum/Minimum wording. The existing shared Event Reconstruction consumer,
  menu aliases and error labels use the same wording; annotation types, IDs and
  requests remain `peak_max`/`peak_min` and `max`/`min`.
  `wwErPeakValueLine()`, `wwErCreatePeak()` and `wwCreatePeakFromClick()` change
  their matching display/error wording only; request and sample logic is intact.
- `wwStickyRulerElapsedUnit()` retains seconds for views of at least one second,
  including views longer than a minute. Subsecond millisecond labels are retained.
- `wwSyncTimeGroupRuler()` uses `{text: title}` at creation and
  `xaxis.title.text` on updates. Coordinates and tick locations do not change.

Focused regression coverage:

- New `browser-tests/waveform-measurement-values.spec.js`: nine real interaction
  scenarios covering the pinned GPTH Slow export, GPTH/Permas/BPHE Fast, BEN32
  Fast/Slow, and COMTRADE at 5 kHz / 0.2 s, 20 Hz / 70.05 s, 1 Hz / 180 s.
  Positive-only, negative-only and bipolar fixtures assert both signed extrema,
  earliest ties, the backend sample/index, actual callout/marker, visible lower
  tick glyphs/title, A/B endpoint values, absolute mode and manual t0 behavior.
- `test_ben5k_gpth_slow.py` adds an original-export UAT check for both A/B
  sample 0/382/1401 and the full-record maximum. Existing complete raw/engineering
  and binary-state parity is retained.
- Existing Event Reconstruction and PU display browser assertions are updated
  only for the shared wording. Its static menu parity guard is updated likewise.
- **375 focused backend checks passed**, plus **267 preservation/authority
  checks passed**, all without failures or skips. This includes native P3
  **28,040/28,040 engineering samples and 28,040/28,040 binary states**, original
  BEN32 Fast/Slow export parity and missing data, BEN6K controls and DEC-213 gates.
- All 14 BPHE / 16,072 values and all 62 GPTH/Permas raw/engineering arrays remain
  identical to P2/P1. The freshly generated complete Fast summary matches the
  existing baseline exactly; canonical SHA-256
  `403e35ee419d0091ffe274361d73b25594e55a51039379d6be526a8ec3694165`.
- **83 distinct browser scenarios have passing final results**, including all
  nine new interaction scenarios and the prior P3/P1/P2, shared annotation/PU and
  DEC-213 cases. The primary run passed 81/83; two assertions still expected the
  old ±Peak wording. The affected annotation spec (6 tests) and provenance case
  (1 test) were corrected and rerun successfully. The warning-glyph assertions
  remain intact. The evidence records each raw run and the final per-scenario
  result; this is not a claim that the primary run had zero failures.

Final shared-consumer browser results and review screenshots are recorded in the
[evidence directory](evidence/ben5k-gpth-slow-uat-2026-11-17/):
[sample comparisons](evidence/ben5k-gpth-slow-uat-2026-11-17/values.json),
[regression rollup](evidence/ben5k-gpth-slow-uat-2026-11-17/regressions.json),
[before](evidence/ben5k-gpth-slow-uat-2026-11-17/before.png),
[corrected callout](evidence/ben5k-gpth-slow-uat-2026-11-17/maximum-callout.png),
[corrected cursor/ruler](evidence/ben5k-gpth-slow-uat-2026-11-17/elapsed-cursors.png).
The screenshots were visually inspected. Local JUnit files:
`.local-data/p3-uat-backend.xml`, `p3-uat-controls.xml`,
`p3-uat-browser-regression.xml`, `p3-uat-annotation-rerun.xml` and
`p3-uat-provenance-rerun.xml`. The full backend suite was not repeated.

## Remaining limits and release state

This is numerical/export agreement and corrected presentation, not physical
instrument verification. The exact P3 configuration fingerprint and experimental
opt-in remain unchanged. Ten constant `0x0800` arrays retain their original values
without an active/valid-measurement claim. GRNE/other unsupported layouts and
the previously recorded P2 limitations remain unresolved.

No BEN adapter, waveform/peak/cursor service, PU mathematics, DEC-213 calibration
authority or stored/original data changed. There is no evidence of a residual
numeric defect in the reported sample/maximum/cursor paths. Controlled GitHub
integration is authorized; deployment and owner DEV retest still require separate
authorization before any merge.

## Controlled integration verification (2026-11-17)

All 18 reviewed candidate files matched their preserved SHA-256 hashes before
integration. Runtime code, regression tests and numerical evidence remain as
reviewed; only documentation is updated to record the owner's integration decision.
The pinned JUnit hashes/counts confirm 642 backend passes and 83 distinct browser
scenarios with passing final results, retaining the original two wording failures
and their successful targeted reruns. The complete Fast control summary remains
identical to the P1/P2 baseline. The full local backend/browser suites were not
repeated. New-head GitHub CI must be checked independently of decoder CI #426.

The correction is a new child commit of `ff1209d98a3d9e8b43eab0bf068176cb69a4cba2`;
the original P3 decoding commit is preserved. The separate product-identity cleanup
worktree and the original checkout are excluded from this correction.
