# D5A-2B2C-1B on the WUI-001–004 DEV baseline — integration report

Date: 2026-11-24. Scope: owner-authorised **DEV-only** release. No `main` merge, no PROD, no PU-MIG
implementation, no D5A-2B2D.

## 1. Branches and commits

| Item | SHA |
|---|---|
| DEV baseline `uat/dev-d5a-20261121` (WUI-001–004) | `3ed200c02a845fe1cc09707feb268128d46b112c` |
| Previous engineering base (DEV-UAT-approved) | `f24f1d72f49cf694ac5f843d03fd102e7754320a` |
| D5A-2B2C-1B tip (`feature/d5a-2b2c-1b-impedance-distance-unified-side`) | `2144893c4028069c3dcd3df8068684ccba6a3f25` |
| Integration merge commit (`integration/d5a-2b2c-1b-on-wui-3ed200c`) | `0ed6f4ad4c1a449165548edfe7dfa9f0841dd95c` |

The integration merge `0ed6f4a` has parents `3ed200c` (first) and `2144893` (second). The seven 1B commits
(`3e9cc5f`..`2144893`) were authored on `f24f1d7`. The release candidate is this merge **plus the docs-only
commit that adds this report**; the final SHA is recorded in the delivery handoff, not here (a commit cannot
contain its own SHA).

## 2. Divergence and conflicts

- `3ed200c` is one WUI commit on `f24f1d7`; 1B is seven commits on `f24f1d7`.
- Files changed by both sides: `docs/project-memory/HANDOFF.md` and `frontend/index.html` only.
- Integration vs `3ed200c`: 74 files, +3882 / −1742. The code is confined to backend services/schemas/domain/API,
  backend tests, two browser specs, one diagnostics script, `frontend/index.html`, and docs/evidence.

| File | Result | Resolution |
|---|---|---|
| `docs/project-memory/HANDOFF.md` | textual conflict | Kept **both** sections (the WUI consolidation section and the 1B section). The 1B status line was changed from "committed locally, NOT pushed" to the integrated status; "Last updated" set to 2026-11-24. |
| `frontend/index.html` | auto-merged, no conflict | Verified at source level (below). Not overwritten from either side. |

### `frontend/index.html` preservation proof

Multiset comparison of the `-U0` +/- lines of each parent's delta against the merged result:

| Check | Expected | Actual | Missing | Extra |
|---|---|---|---|---|
| merged vs `3ed200c` equals the 1B delta — added | 211 | 211 | 0 | 0 |
| merged vs `3ed200c` equals the 1B delta — removed | 335 | 335 | 0 | 0 |
| merged vs `2144893` equals the WUI delta — added | 832 | 832 | 0 | 0 |
| merged vs `2144893` equals the WUI delta — removed | 508 | 508 | 0 | 0 |

Both deltas are fully preserved line-for-line; `node --check` of the extracted script passes.

## 3. Verification results

### Backend (full suite, candidate `0ed6f4a`)

`13701 passed, 405 skipped, 0 failed` (the 405 skipped equals the prior baseline skipped count).

Targeted D5A-2B2C-1A/1B files, run on the candidate:

| File | Result |
|---|---|
| `test_d5a_2b2c_1b_authority_enforcement.py` | 52 passed |
| `test_d5a_2b2c_1b_impedance_distance_oracles.py` | 34 passed |
| `test_d5a_2b2c_1b_zone_not_evaluated.py` | 18 passed |
| `test_frontend_d5a_2b2c_1b_protection_side.py` | 61 passed |
| `test_d5a_2b2c_1a_overcurrent_unified_side.py` | 34 passed |

### D5A-2B2C-1B numerical validation

- **2×2×2 impedance reference-side matrix** — `test_matrix_with_the_sides_the_recording_declares` covers
  all four (voltage side × current side) declarations, each evaluated at both output sides; the matching
  group-override matrix (4 cases) and the recording-correction matrix (2 cases) also pass.
  `test_the_eight_combination_numbers_are_the_hand_derived_ones_not_a_ratio_artifact` pins the eight results to
  hand-derived values.
- Group override beats recording correction per quantity; voltage and current groups are configured
  independently; declarations are never rewritten; only the quantity that must convert needs its transformer;
  nominal-derived VT keeps its provenance; V/kV and A/kA are normalised before the impedance is formed;
  unrecognised units are refused; the low-current floor judges recorded current whatever the output side; the
  zone boundary follows the converted impedance (primary 165 Ω, secondary 33 Ω).
- **Distance "Not Evaluated"** (18 cases): valid impedance inside/outside a zone; output side does not change
  which zones operate; standard/dynamic zone configurations intact; blocked recorded distance reports no zone
  for each of side-undefined, current-side-undefined, vt-unavailable, mixed-group, mixed-legs; required CT
  unavailable; contradicting assertion; loop current below the floor; unavailable phasor; missing current
  channel; calculated channel; blocked→valid driven only by Recording Details; Manual mode unchanged; locus
  unchanged; response schema unchanged.

### Browser (Playwright, 1 worker, retries 0, against the candidate)

| Run | Spec files | Passed | Failed | Skipped |
|---|---|---|---|---|
| Affected selection (WUI, toolbar/pane controls, legends, Y labels, layouts, Per-Unit, Recording Details, Overcurrent, Impedance, Distance, Related Waveforms, calculated-channel safeguards) | 98 | 1058 | 101 | 8 |
| Additional PU / source / timing selection | 14 | 79 | 30 | 5 |
| **Total** | **112** | **1137** | **131** | **13** |

Passing on the candidate with **zero** failures: `d5a_2b2c_1b_protection_side` (17), `d5a_2b2c_1a_overcurrent_side`
(15), `d5a_ui_002_group_details` (19), Impedance specs (10), Distance specs (62), `waveform-legend*` (14),
`waveform-y*` (10), `waveform-pane*` (37), `waveform-axis-units` (ENG/PU switching incl. recording-side change),
`waveform-axis-unit-preservation`, `analysis_related_waveforms`, `calculated-current-manual-pu`,
`analyser-recording-detection` (upload → navigate → remove).

### Baseline comparison (exact `3ed200c`, same spec files, same runner settings)

| Selection | Failing on candidate | Failing on `3ed200c` | Difference |
|---|---|---|---|
| 33 files that failed in the affected run | 101 | 101 | none (sorted failing-test lists identical) |
| 8 files that failed in the additional run | 30 | 30 | none (sorted failing-test lists identical) |

**No browser failure is introduced by the integration.** All 131 failures reproduce identically, test for test,
on the deployed baseline `3ed200c`.

**These failures are not declared obsolete.** Common error signatures on the baseline run are: elements not
found/not visible (`#wwOpenPerUnitSettingsBtn`, `#wwUnitEngineeringBtn`, `#wwUnitPerUnitBtn`, `#workspaceRow`,
`#wwRdUploadBtn`, `#measurementGroupsOverlay`, analog channel toggle rows), the upload modal not closing within
30 s, and 30 s/90 s test timeouts. That is *consistent with* specs written against the pre-WUI toolbar/upload
flow, but it was **not proven**; each remains an open item against the baseline (see §6). Their functional areas
are covered by positive tests that pass (upload, ENG/PU switching, source lifecycle: see above and the backend
suite).

Test side effect: the browser run rewrote seven tracked evidence PNGs under
`docs/project-memory/evidence/rd1-d2-refine/`; they were restored (`git checkout`) and are **not** part of any
commit.

## 4. WUI-001–004 preservation

Beyond the line-level proof in §2, the toolbar, pane-local Y and ENG/PU controls, interactive legends (incl.
hidden-channel behaviour), per-axis Y unit labels, Grouped/Separate/Custom layouts, Time Group and source
ownership specs pass on the candidate except where the same test also fails on `3ed200c` (two
`waveform-top-toolbar-migration` Per-Unit-Settings-icon tests, plus the `waveform-toolbar-t0-sync-refinement`,
`waveform-measurement-values` and `waveform-empty-state` failures that are identical on the baseline).

## 5. Excluded

PU-MIG-001/S0 audit branches and the parked S0 reconciliation are **not** part of this release. No experimental
changes were included.

## 6. Known limitations / open items

1. 131 browser tests (41 spec files: 33 + 8) fail on `3ed200c` and on the
   candidate alike; root cause not established. Recommended follow-up: triage against the current WUI selectors.
2. 35 spec files of the 147 were not run (relay import, BEN5K GPTH/UAT/slow, calculator, display timezone, and
   similar areas untouched by this change). Their backend counterparts pass in the full backend suite.
3. The backend suite took 1:52:11 on a loaded machine (~19 min previously); timing only, no failures.
4. Deployment, DEV UAT and any `main`/PROD action remain with the owner.
