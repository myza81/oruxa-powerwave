# GPTH legacy Slow P3 — owner-accepted bounded local correction

Branch: `fix/ben5k-gpth-slow-p3`, based on fetched main
`856c74b23b56b60a20fabae712687273293780c5`. On 2026-11-17 the owner accepted
this bounded candidate and authorized its LOCAL COMMIT. No P3 push, merge or
deployment is authorized. Prior dirty work and every earlier worktree are preserved.

**Result:** native import now exposes all **20 calculated channels** (10 Hz,
10 MW) and **20 binary indications**. The complete original export comparison
passes for **28,040/28,040 signed raw and engineering samples**, plus
**28,040/28,040 binary states**. Ten calculated arrays contain constant `0x0800`;
numeric export parity does not establish that they are active measurements.

## P2 operational closure

PR #10 merge `856c74b23b56b60a20fabae712687273293780c5` and owner BPHE DEV UAT
are accepted. Post-merge [CI #424](https://github.com/myza81/oruxa-powerwave/actions/runs/44010122459) passed.
[Automatic DEV deployment](https://github.com/myza81/oruxa-powerwave/actions/runs/44011270803) and job
`133798574462` succeeded. Its log identifies that exact merge SHA and records
backend health success and "Deployment successful" at 03:35:46 UTC on 2026-11-17.
This was observed, not dispatched by P3. P2's mapping remains fingerprint-bounded;
general sparse packing and the additional Permas entries remain unresolved.
[Closure evidence](evidence/ben5k-gpth-slow-p3-2026-11-17/p2_operational_closure.json).

## Evidence recovered; GRNE kept separate

Reused the existing BEN-wide root-cause report, its pinned manifest and GPTH
Slow oracle identity. The recovered identity's SHA-256 matches that manifest.
The exact-event BEN/CFG/DAT hashes, station/recorder, 20 Hz, 1,402 samples,
400 pre-trigger samples, and recorder trigger `2022-07-27 12:41:49.878483` agree.
The start clock is `12:41:29.878483`; agreement does not establish UTC authority.

Recovered the [frozen GRNE S1–S6 study](https://github.com/myza81/oruxa-powerwave/blob/914875775999a8ec53146f06b6dd4345f519472f/docs/project-memory/BEN5K_SLOW_COMPATIBILITY_INVESTIGATION.md).
Its `29 ff`/`05 00` recording uses 252-byte groups, 28-byte slots and unresolved
selectors. Its nominal-derived frequency divisor and plausible MW/Mvar gains
were never independently confirmed. No GRNE code, selectors or gain assumptions
were transferred to GPTH. Original studies remain frozen and untouched.
[Recovery identities](evidence/ben5k-gpth-slow-p3-2026-11-17/recovery_manifest.json).

## Actual root causes and smallest correction

1. `parser._is_ben5k()` checked layout/generation but ignored the class byte.
   GPTH has `28 ff 03 00 6e 00 ca 00 / 05 00`, exactly like the supported Fast
   family, but **byte `0x3C` is 1 (Slow)**, rather than 0 (Fast). Its 20 Hz rate
   corroborates the class; sampling rate is not used to guess record class.
2. The Fast reader starts at `0xBBA` and recognizes Fast analog descriptors.
   GPTH Slow instead contains `0x1300` acquisition frames starting at `0x7DC`,
   interleaving calculated and indication records. Fast discovery/classification
   found zero supported channels and returned a successful empty record.
3. The Slow sample/coefficient contract is distinct. Applying either the old Fast
   full-word gain or P1's signed-upper-12-bit/sqrt(2) conversion would be wrong.

The candidate dispatches legacy class 1 to one bounded Slow reader. Direct Fast
entry rejects non-Fast classes; an empty Fast result is rejected instead of
silently presenting zero channels. Unknown class values are rejected.

## Native catalog, physical addressing and conversion

The sample payload starts at `0xE88` (3,720):
`68,212 - 1,402 × 23 × 2`. Every row is **23 big-endian 16-bit words**.
Catalog bounds exclude the ten-byte configuration footer. The reader identifies
the first framed physical word 0 and consumes all 23 consecutive addressed
frames through that footer, rejecting missing/conflicting/truncated frames.

Each frame starts with little-endian `u16 0x1300, u16 physical_word`.
Calculated frames are 60 bytes: record tag at +4, original channel ID +6,
native quantity/unit flags +10/+11, original 16-byte name +12, literal unit +28,
f32 gain/offset/ranges +36/+40/+44/+48 and selector bytes +52. All 60 original
bytes remain available. Names, selectors and waveform magnitude never determine
the physical column. Indication words 7, 14 and 20 contain 10, 6 and 4 separate
24-byte descriptors, each naming its source channel ID and bit. Active-low
polarity matches all original DAT states, including transitions.

For this reviewed profile only:

```text
raw = full big-endian signed_int16_word
engineering = raw × (catalog_gain / 16) + catalog_offset
```

No sample shift, nibble masking or sqrt(2) is used. The independent CFG contains
the catalog gain divided by 16, with the offset unchanged. Frequency stores
gain `0.0078125` and offset **50**, giving effective gain `0.00048828125` Hz/count.
MW uses stored gains `5.1475701332092285`, `2.059030055999756` or
`2.0590200424194336`, divided by 16. These relationships come from the independent
coefficients and all samples, not nominal-frequency or plausible-power fitting.
General firmware meaning of this gain representation remains unproven.

## All 20 calculated identities

Physical words are zero-based; CFG analog columns are one-based. Native physical
frame order and independent export order differ; comparison uses explicit identities.

| Native ID | Original calculated name | Unit | Frame byte | Physical word | CFG column |
|---|---|---|---|---:|---:|
| 143 | `POWER TBIN 1` | MW | `0x854` | 2 | 1 |
| 148 | `FREQ UR TBIN 1` | Hz | `0xAEC` | 10 | 2 |
| 144 | `POWER SDAI 1` | MW | `0x890` | 3 | 3 |
| 149 | `FREQ UY SDAI 1` | Hz | `0xA74` | 8 | 4 |
| 145 | `POWER SDNK 1` | MW | `0x8CC` | 4 | 5 |
| 150 | `FREQ UB SDNK 1` | Hz | `0xAB0` | 9 | 6 |
| 151 | `FREQ UR TBIN 2` | Hz | `0x7DC` | 0 | 7 |
| 146 | `POWER TBIN 2` | MW | `0x908` | 5 | 8 |
| 152 | `FREQ UY SDAI 2` | Hz | `0x818` | 1 | 9 |
| 147 | `POWER SDAI 2` | MW | `0x944` | 6 | 10 |
| 238 | `POWER SDNK 2` | MW | `0xB2B` | 11 | 11 |
| 241 | `FREQ UB SDNK 2` | Hz | `0xCEB` | 17 | 12 |
| 239 | `POWER HV TX1` | MW | `0xB67` | 12 | 13 |
| 242 | `FREQ UR HV TX1` | Hz | `0xC73` | 15 | 14 |
| 240 | `POWER HV TX2` | MW | `0xBA3` | 13 | 15 |
| 243 | `FREQ UY HV TX2` | Hz | `0xCAF` | 16 | 16 |
| 298 | `POWER PLNG 1` | MW | `0xD2A` | 18 | 17 |
| 300 | `FREQ UR PLNG 1` | Hz | `0xE42` | 22 | 18 |
| 299 | `POWER PLNG 2` | MW | `0xD66` | 19 | 19 |
| 301 | `FREQ UY  PLNG 2` | Hz | `0xE06` | 21 | 20 |

The extra internal space in `FREQ UY  PLNG 2` is preserved. The binary descriptor
`POWER HV TX2 ` retains its original trailing space in the native model; existing
shared normalization trims and suffixes duplicate value/binary names normally.
No display names or frontend behavior were rewritten.

## Independent before/after comparisons

Before P3 all calculated values below were absent. Examples from the original
DAT, using its independently printed coefficients:

| Channel | Sample | Signed raw | Before P3 | Candidate | Independent export |
|---|---:|---:|---|---:|---:|
| `POWER TBIN 1` | 0 | -801 | omitted | -257.700229793787 MW | -257.700229773300 MW |
| `FREQ UR TBIN 1` | 0 | -78 | omitted | 49.961914062500 Hz | 49.961914058600 Hz |
| `POWER SDAI 1` | 0 | 22 | omitted | 7.077908933163 MW | 7.077908932600 MW |
| `FREQ UR TBIN 2` | 0 | -78 | omitted | 49.961914062500 Hz | 49.961914058600 Hz |

Every channel's complete 1,402-sample raw column is exactly equal to its DAT
column. Maximum engineering discrepancy: **1.032500023256944e-07** units.
Acceptance bounds coefficient printing: `abs(error) <= abs(raw) × 5e-11 + 1e-9`
(CFG coefficients print ten decimal places). Independent expected raw and
engineering digests and original scalar vectors are pinned in
`backend/tests/fixtures/ben/gpth_2022_legacy_slow.json`; expected values are not
derived from a production conversion helper.
[Complete per-channel comparison](evidence/ben5k-gpth-slow-p3-2026-11-17/parity.json).

## Changed functions and regression results

- `parser.py::parse_ben_experimental()`: explicit 0/1 class dispatch; reject others.
- `legacy_ben5k/normalize.py::parse_ben5k()`: reject non-Fast direct entry and empty
  decoded records. Existing Fast arithmetic, discovery and mapping are unchanged.
- New `legacy_ben5k/gpth_slow.py`: `parse_gpth_slow()`, `_read_catalog()`, `_name()`;
  profile check, bounded catalog, explicit addresses and calculated coefficients.
- New focused backend/browser tests, fixture, diagnostic reproduction script and
  these memory/evidence updates. No shared model, schema, setting or frontend edit.

Exact 17-file local-commit scope:

```text
backend/app/providers/ben/legacy_ben5k/gpth_slow.py
backend/app/providers/ben/legacy_ben5k/normalize.py
backend/app/providers/ben/parser.py
backend/tests/fixtures/ben/gpth_2022_legacy_slow.json
backend/tests/test_ben5k_gpth_slow.py
browser-tests/ben5k-gpth-slow.spec.js
docs/project-memory/BEN5K_BPHE_P2_CHANGE_REPORT_2026-11-17.md
docs/project-memory/BEN5K_GPTH_SLOW_P3_CHANGE_REPORT_2026-11-17.md
docs/project-memory/CURRENT_STATE.md
docs/project-memory/DECISIONS.md
docs/project-memory/HANDOFF.md
docs/project-memory/evidence/ben5k-gpth-slow-p3-2026-11-17/gpth-slow-waveform.png
docs/project-memory/evidence/ben5k-gpth-slow-p3-2026-11-17/p2_operational_closure.json
docs/project-memory/evidence/ben5k-gpth-slow-p3-2026-11-17/parity.json
docs/project-memory/evidence/ben5k-gpth-slow-p3-2026-11-17/recovery_manifest.json
docs/project-memory/evidence/ben5k-gpth-slow-p3-2026-11-17/regression_summary.json
scripts/diagnostics/ben5k_gpth_slow_p3_evidence.py
```

**1,172 focused backend tests passed**, zero failures/errors/skips. Includes the
37 P3 checks, complete original GPTH export, native provider/import/stored arrays,
all API waveforms, both cursors, min/max peaks, sign and low-bit boundaries,
nonzero frequency offsets, distinct physical columns, opt-in and malformed inputs.
Initial sandbox run passed 1,171 with only BEN6K original-file access denied;
the final focused run with authorized access passed all 1,172 in 61.44 seconds.
Local-commit confirmation reran only the 37 P3 checks: all passed, no skips or
failures. Implementation, tests and evidence artifacts are unchanged from review.

**33 browser tests passed**, zero failures/skips: all 20 GPTH Slow visible/plotted
arrays against original CFG/DAT, all prior 32 BPHE/October/import/DEC-213 cases.
[Actual Hz/negative-MW screenshot](evidence/ben5k-gpth-slow-p3-2026-11-17/gpth-slow-waveform.png)
was visually inspected; original source metadata shows 20 analog/20 digital at 20 Hz.

- **BPHE:** all 14/16,072 native export comparisons pass, full summary unchanged.
- **GPTH Fast 35 / Permas Fast 27:** all complete raw/engineering array hashes,
  inventories and magnitudes remain identical to P2/P1; mapping goldens pass.
- **BEN32 Fast/Slow:** all original independent export and missing-data checks pass.
- **BEN6K-labelled SubBen:** all 103 raw and engineering column hashes unchanged.
- **DEC-213:** Slow channels remain Unverified with existing full-s16 linear
  transform identity; engineering eligibility is blocked. Existing PU, calculated,
  phasor, compliance and power safeguards pass. Recorder clock stays UNKNOWN.

[Regression summary](evidence/ben5k-gpth-slow-p3-2026-11-17/regression_summary.json).
The unrelated full backend suite was not repeated. Local JUnit:
`.local-data/p3-final-regression.xml`, `.local-data/p3-browser.xml`.
Local-commit confirmation: `.local-data/p3-commit-check.xml`.

## Exact applicability and remaining limits

- Only family `01 00 04 00`, legacy `28 ff 03 00 6e 00 ca 00`, generation `05 00`,
  class flag 1, 23-word rows, 20 Hz, complete reviewed catalog and configuration
  SHA-256 `3caff3c4cccef555d7521da101ff722bcb162200afdcf5ba1941e1457addff38`
  over `[0xDC, payload_start)` acquire this Slow contract. Unsupported profiles
  fail explicitly. It is not general support for every legacy Slow recording.
- Ten calculated channels carry constant `0x0800` in both native and independent
  export. Their distinct addresses come from the physical frame headers; identical
  waveform columns alone cannot prove that assignment. All numeric export values
  are retained, including this pattern, without asserting active/valid physical
  measurements or inventing a missing-value sentinel. Broader availability/status
  interpretation needs independent evidence. SubBen's missing marker is untouched.
- Numerical/export parity is not physical instrument verification. DEC-213
  authority/gates are unchanged; the existing BEN5K experimental opt-in still
  applies. Fresh import is required; original files and saved data are not rewritten.
- GRNE `29 ff`, earlier `28 ff 02`, unsupported Slow profiles, P2 generalized
  sparse mapping and the additional Permas inventory remain outside this candidate.
  Fast P1/P2, BEN32, BEN6K, PU mathematics, calibration framework and UI are preserved.

The next milestone is separately authorized PR/CI, followed by authorized DEV
deployment and owner GPTH Slow UAT before merging to main. No further BEN stage
is authorized.

Reproduce the parity artifact from this repository root:

```text
python scripts/diagnostics/ben5k_gpth_slow_p3_evidence.py --reference-root <owner-root> --output <parity.json>
```

Backend: all `tests/test_ben*.py` plus physical calibration, phasor calibration,
power provenance and compliance calibration gates, with `--ben-reference-dir`.
Browser: the P2 eight suites plus `ben5k-gpth-slow.spec.js`, the existing
experimental flag and original BPHE/GPTH/Permas paths, plus `GPTH_SLOW_BEN_PATH`.
No original BEN/CFG/DAT payload is copied into version control. The fixture keeps
header/configuration bytes, pinned identities, scalar references and column hashes.
