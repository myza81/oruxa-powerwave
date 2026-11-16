# BEN confirmed-defect corrections — assessment and local verification

Date: 2026-11-11. **Owner-approved corrections A/B committed locally in
isolation. Not pushed, merged or deployed.** Baseline:
`bb370678bec4ae3ce2ae1b1a334dccaa1790e6d0`,
branch `feature/vlt-ref-001-voltage-reference-safety`; fetched upstream was
0 ahead / 0 behind. Existing PULU changes and all prior evidence are preserved.

The owner accepted the BEN-wide audit as the engineering basis for this
bounded stage. Only two confirmed defects are corrected locally. No √2/16,
other calibration factor, unit reassignment, nominal detection, side authority,
PU mathematics, Fast/Slow native binary decoding or Slice 6D change is made.
The separate calibration-authority proposal is **unapproved and not
implemented**. This document is the scoped continuation/handoff; existing
`CURRENT_STATE.md` and `HANDOFF.md` edits were protected and excluded.

## A. Legacy BEN5K physical sample mapping

The previously prepared patch remains unchanged: preserve the classifier's
`physical_word_index` when constructing `BenSampleSlot` in the legacy adapter.
The logical descriptor index remains in the original file; no matrix
rearrangement, classifier/scaling change or shared API extension is needed.
Shared normalization, provider import, waveform/cursor/peak consumers and
calculated channels subsequently read the correct physical column.

Golden coverage pins the original Permas Jaya and GPTH files by size/SHA-256,
all descriptor offsets and all 62 accepted physical-column identities/hashes.
Independent scalar binary reads compare every sample at the physical payload
address, not expectations computed by the classifier being tested:

| Recording | Active value channels | Shifted channels | Payload words checked |
|---|---:|---:|---:|
| Permas Jaya October | 27 | 14 | 208,413 |
| GPTH October | 35 | 21 | 289,170 |
| Total | 62 | 35 | 497,583 |

All 35 affected channels and their logical/physical indices are listed in the
preserved [mapping correction report](BEN5K_PHYSICAL_MAPPING_CORRECTION.md).
The earlier test-first result was 41 failures / 28 passes before correction,
then all 69 passed after correction. This stage reruns those 69 tests as part
of the targeted regressions; no implementation work is repeated.

This is **mapping evidence, not absolute calibration evidence**. The existing
packed-word gain/offset formula and kV/kA labels remain unchanged. In particular
unshifted Permas PLTG1 VR still evaluates −19,505 × 0.13435986638069153 =
−2,620.6891937553883 in the current labelled kV output. No nominal matching
or implied primary/secondary reassignment is used to make that look correct.
Existing live imported arrays are not rewritten; mapping correction requires
re-import through the corrected adapter.

## B. BEN32 Slow ASCII export missing data

The five failures were reproduced independently through `ComtradeProvider`:

| Exact export | Channel | Before | After |
|---|---|---|---|
| PMJY Slow | FREQ SGT1 VB_HV | 1,401 values at 99.9995 Hz | 1,401 nulls |
| PMJY Slow | FREQ SGT1 VY_LV | 1,401 values at 99.9995 Hz | 1,401 nulls |
| PMJY Slow | FREQ SGT2 VR_HV | 1,401 values at 99.9995 Hz | 1,401 nulls |
| PMJY Slow | FREQ SGT2 VB_LV | 1,401 values at 99.9995 Hz | 1,401 nulls |
| BTGH Slow | FREQ TMGR VB | 1,401 values at 99.9995 Hz | 1,401 nulls |

Native Slow raw `-32768` is already an unavailable calculated result. These
exact BEN32 exports write the ASCII analog code `99999`, which the old
COMTRADE path treated as a real sample: `99999 × .0005 + 50 = 99.9995 Hz`.
Original files, file hashes and all non-missing data remain unchanged.
Like the mapping correction, this import-time fix does not rewrite existing
live workspace arrays; re-import is required to replace a previously decoded
99.9995 Hz series. No background repair or original-file mutation is added.

### Authoritative rule and scope

New primary-source research resolves an uncertainty in the earlier audit:
this need not be a vendor-filename heuristic. The IEEE PSRC H5-c report,
printed pp4–5, quotes COMTRADE-1999's reserved ASCII analog missing code
`99999`; its valid positive analog range ends at `99998`.
[IEEE PSRC H5-c, 2008](https://www.pes-psrc.org/kb/report/068.pdf).
The PSRC conformity report also distinguishes pre-2013 ASCII missing-value
representation from later formats.
[IEEE PSRC H26, 2015](https://www.pes-psrc.org/kb/report/071.pdf).

The implemented rule is therefore narrowly tied to **declared COMTRADE-1999
ASCII analog raw fields**, before gain/offset. Existing supported aliases
2001 and 2005 continue using their already established 1999 interpretation;
both affected real exports declare 2005. This is not a general rule that an
engineering value of 99999 or any out-of-range value is absent.

The private CFG container now retains `declared_rev_yr` separately from the
parser's existing fallback revision. Missing/unrecognized revision strings
cannot acquire new sentinel semantics merely because the parser defaults to
1999. No public schema/API or new configuration control is introduced.

| Case | Behavior in this candidate |
|---|---|
| Declared 1999 ASCII raw analog `99999` | NaN before `a*x+b` |
| Declared supported 2001/2005 aliases | Same established 1999 interpretation |
| 1991 / 2013 numeric `99999` | Existing behavior preserved; no new rule |
| Absent/unknown revision falling back to 1999 | Existing behavior preserved; no inferred sentinel |
| Valid 1999 raw −99999 / +99998 | Preserved |
| Valid engineering result 99999 from another raw code | Preserved |
| Sample numbers, timestamps, digital fields | Not inspected or changed by this rule |
| Binary COMTRADE / native BEN payloads | Unchanged |

Other revisions' empty-field handling, binary missing markers, unsupported
variants and general CFG range validation are deliberately outside this
correction. Do not extend the rule from library behavior or a guessed vendor
fingerprint. A header falsely claiming 1999 while using its reserved raw
code as data is nonconforming; entering a plausible nominal base cannot
disambiguate it. Such a file needs an independently justified import contract.

### Reproduction and preservation evidence

The first 20 new backend tests produced **13 failures / 7 passes**, including
all five real failures, then **20 passes** with the correction. Three further
cases exercise leading, trailing and wholly unavailable intervals; all 23
new cases pass in the targeted run.

Independent baseline/current provider runs compare all 24 value channels /
33,624 samples in both exact Slow exports. The 7,005 sentinel positions now
match native BEN's missing mask. All 26,619 available samples are **bitwise
unchanged** relative to the baseline COMTRADE importer; native/export decimal
rounding tolerance remains unchanged. Valid data, digital states, sample
count, time axis, units, coefficients, offsets and P/S metadata are preserved.
The synthetic API test checks gaps through waveform JSON, both cursor values,
min/max handling and nested polarity calculations under `propagate_null`,
without mutating source arrays or filling neighboring valid samples.
An additional actual-file API probe uploads both exact CFG/DAT pairs and
checks all five channels: 7,005 waveform nulls, no available/fabricated peak,
and 7,005 nulls in calculated polarity results. All five probes pass.

Two new real-browser tests verify plotted null positions, no gap bridging,
Hz identity/units, preservation of an engineering result equal to 99999, and
preserved 2013 numeric behavior. No production frontend change is included.

## Browser failure classification against unchanged HEAD

The baseline was extracted with `git archive` to a fresh TEMP directory, not
a second Git worktree. Baseline backend/frontend source is exact HEAD, with
only temporary frontend endpoint configuration. A second frozen copy differs
only in the existing BEN5K mapping adapter. Browser outputs/storage are new
TEMP paths. Diagnostic stack/state logging adds observation, not weaker
assertions or altered user interactions.

### TBIN1 Plotly error — existing intermittent product defect

The original test passed 3/3 times on both variants in the initial serial
comparison. A 12-repeat/four-worker diagnostic run reproduced the **same**
`gd.data must be an array.` exception on unchanged baseline (1/12) and the
mapping variant (3/12). Both stacks are:

```text
Plotly.addTraces
  wwAddTraceToPanel      frontend/index.html:34664
  wwAddSelectedChannels frontend/index.html:38913
```

Baseline stress totals were 7 pass / 5 fail: one Plotly error and four
connection-refused-only failures. Mapping stress totals were 9 pass / 3 fail:
all three had the Plotly error, one also a connection refusal. The transport
noise is reported separately; it is not counted as five baseline Plotly
reproductions. The exception-only baseline case establishes that the renderer
defect does not require the mapping patch or a transport error.

The asynchronous add path fetches a batch, checks workspace epoch, then calls
`addTraces` on a panel retained across that await. The failing call finds no
Plotly data array. This points to panel initialization/lifecycle ownership
during overlapping adds; the exact interleaving is not established by the
stack alone. A future bounded fix should await initialization and fence stale
panel ownership, with all seven TBIN1 channel identities and the digital
trace asserted. Suppressing errors or manufacturing an empty `gd.data` would
not be a justified fix. **No renderer code or existing test was changed.**

### PULU-07 — existing engineering display defect, not outdated expectations

PULU-07 is in the pre-existing uncommitted PULU test addition, not HEAD's
six-test committed PULU suite. The same added test was applied as a TEMP
diagnostic against unchanged HEAD product code and the mapping-only variant.
It failed 3/3 on each, at the initial panel separation check, **before Save**.
It therefore cannot establish the subsequent Save behavior.

An additional read-only baseline state capture confirms:

| Channel | Backend/displayed unit and status | Computed panel key | Actual retained panel |
|---|---|---|---|
| SGT1 VR_HV | pu / configured | `…::Voltage:pu` | `…::Voltage` |
| SGT1 VR_LV | kV / base_required | `…::Voltage:base_required` | `…::Voltage` |

Both live traces use Plotly axis `y`; that axis is titled **pu**, with a range
around ±176.4. The calculated grouping keys are correct, but the retained
layout is stale. This genuinely mixes pu and kV on one displayed axis, not
merely an assertion about internal labels. The existing product code itself
documents that these states must be separated. The test's instrumentation
array remained empty, so it does not establish the precise missing/awaiting
call or justify a one-line timing fix. A future PULU correction must make
generation-fenced mode refresh/regrouping complete before presenting the new
basis and must exercise the real UI Save flow after valid initial separation.
The protected PULU edit and production frontend remain unchanged.

These are owner-review issues outside A/B. They are not silently fixed here,
not classified as harmless flaky expectations, and not attributed to BEN
calibration or the COMTRADE sentinel correction. The initial fixture uses
ordinary synthetic analog codes, not the missing sentinel.

## Calibration-authority proposal and remaining engineering limitation

See [the separate proposal](PHYSICAL_CALIBRATION_AUTHORITY_PROPOSAL_2026-11-11.md).
It proposes independent, evidence-scoped per-channel calibration authority,
centralized leaf/dependency enforcement for PU, source-backed power and
Compliance, no upgrade from manual bases/known side/group confirmation, and
explicit manual-Calculator provenance limits. It requires owner approval;
there is no new gate, UI, storage or source-side inference in this patch.

**BEN5K absolute engineering values remain unverified and the current product
has not yet implemented the proposed physical-calibration gate.** A/B fixes
do not make those values safe for authoritative PU, power or Compliance.
Exact-event calibration/representation evidence and owner decisions remain
necessary. No √2/16 factor is authorized or implemented.

## Verification status

- Targeted backend: **277 passed, 0 failed, 0 skipped**, 154 warnings,
  101.55 s. Includes A's 69 mapping cases, B's 23 new cases, existing
  COMTRADE parity/provider/duplicate-name, BEN parser/reference, calculated
  channel API, peak and annotation integration tests with the owner corpus.
- New browser regressions: **2 passed**, 22.2 s.
- Controlled baseline/browser diagnostics: results above; failures retained.
- Relevant browser regression: **75 passed, 1 failed, 0 skipped**, 76 tests,
  1.6 minutes. The sole failure is the separately confirmed baseline PULU-07
  defect; no browser expectations were weakened. Nine exact files were
  selected: new COMTRADE ASCII gaps, BEN import, BEN5K mapping, GPTH UAT,
  Permas UAT, calculated null handling, calculated power, PULU and
  Voltage-only PU display. Other untracked browser specs were not selected.
- Full backend: **12,065 passed, 271 skipped, 0 failed, 0 errors**, 170
  warnings, 934.42 s (15m34s), 12,336 collected. The owner BEN corpus was
  enabled. Existing skips include optional unavailable relay-reference PDFs
  and not-applicable relay geometry cases; no new correction tests skipped.

All test output is isolated under:
`C:/Users/fairizat/AppData/Local/Temp/oruxa-ben-correction-assessment-20261111-a1d271de151d4073b44d199cbc48a1c0`.
Key evidence: `red.xml`, `green.xml`, `targeted.xml`,
`five-channel-before-after.csv`, `slow-correction-verification.json`,
`real-five-channel-api.json`,
`browser-new.xml`, `browser-baseline.xml`, `browser-mapping.xml`,
`stress-baseline-verified.xml`, `stress-mapping-verified.xml`,
`pulu-baseline-state.json` and corresponding logs.

## Change ownership and local commit handoff

| Scoped file | Purpose | Ownership |
|---|---|---|
| `backend/app/providers/ben/legacy_ben5k/normalize.py` | Retain corrected physical slot | Carried forward unchanged |
| `backend/app/providers/comtrade.py` | Declared-revision authority and ASCII missing-code decoding | New bounded B correction |
| `backend/tests/fixtures/ben/ben5k_physical_mapping.json` | Exact original identities and physical-column goldens | Carried forward unchanged |
| `backend/tests/test_ben5k_physical_mapping.py` | Five synthetic/consumer mapping checks | Carried forward unchanged |
| `backend/tests/test_ben5k_reference_mapping.py` | 62 real channel goldens plus two integration checks | Carried forward unchanged |
| `backend/tests/test_comtrade_ascii_missing_data.py` | 23 preservation, gap, API/calculation and real-export checks | New |
| `browser-tests/ben5k-physical-mapping.spec.js` | Two original-payload plotted-array checks | Private paths now environment-only; assertions preserved |
| `browser-tests/comtrade-ascii-missing-data.spec.js` | Two actual plot/identity/unit/preservation checks | New |
| `docs/project-memory/BEN_CONFIRMED_DEFECTS_ASSESSMENT_2026-11-11.md` | This assessment, evidence and limits | New |
| `docs/project-memory/PHYSICAL_CALIBRATION_AUTHORITY_PROPOSAL_2026-11-11.md` | Separate, unimplemented owner-review design | New |

The initial assessment preserved 2,278 files by content hash and mtime and
did not commit anything. Those results and its patch bundle remain unchanged
in the earlier evidence directory. The owner subsequently approved isolated
local A/B commits, with the final adjustments and reruns below.

### Final approval conditions and fresh verification

1. The mapping browser spec uses only existing `GPTH_BEN_PATH` and
   `PERMAS_BEN_PATH`; no personal directory or implicit fallback remains.
   An unset/nonexistent private file explicitly skips the corresponding test.
   Available files retain exact SHA-256, identity, full plotted-array and
   browser-error assertions. Without both variables, **2 tests skip explicitly**;
   with the originals enabled, both pass within the 69-test browser run.
2. The COMTRADE guard computes a missing-code mask and copies the analog array
   only when the mask contains a missing value. A separate probe retains a
   read-only loader array: no-gap output shares its unchanged buffer; gap
   output is detached and decoded correctly while the original remains intact.
   Revision selection, decoding, scaling and downstream behavior are unchanged
   by this allocation improvement.
3. The only production paths changed are the legacy adapter and private
   COMTRADE parser. Native Fast/Slow binary decoding, units, scale formulas,
   nominal detection, side authority, PU and calibration policy are unchanged.

Fresh outputs are isolated at:
`C:/Users/fairizat/AppData/Local/Temp/oruxa-ben-ab-local-commits-20261111-dd7aa91e464b4aa29c3372e1de2ac280`.

| Fresh check after the two adjustments | Result |
|---|---|
| Targeted backend, explicit owner corpus enabled | **277 passed, 0 failed/errors/skipped**, 55.676 s |
| Existing BEN reader/decoder/channel-map/normalizer/API/import/fixture tests | **151 passed, 0 failed/errors/skipped**, 16.021 s |
| Eight selected browser files, owner originals enabled | **69 passed, 0 failed/skipped**, 1.4 minutes |
| Mapping browser without private-file variables | **2 explicit skips**, no failure |
| Retained read-only loader-buffer probe, valid and missing paths | **2 cases passed**, original buffers unchanged |

The initial targeted invocation supplied the reference environment variable
but not the CLI option required by the new fixtures: 206 passed / 71 skipped.
It was rerun with explicit `--ben-reference-dir`; all 277 passed. Two early
browser-runner attempts ended before tests (PowerShell treated an existing
warning as fatal; its abandoned server then occupied that port). Correcting
only the temporary runner's logging and choosing fresh ports resolved these
harness issues; no test or application assertion was weakened.

The eight selected specs were `comtrade-ascii-missing-data.spec.js`,
`ben-import.spec.js`, `ben5k-physical-mapping.spec.js`,
`ben5k-gpth-uat.spec.js`, `ben5k-permas-jaya-uat.spec.js`,
`calculated-channel-null-handling.spec.js`, `calculated-channel-power.spec.js`
and `voltage-only-pu-display.spec.js`. The actively edited PULU spec was not
rerun during this final commit pass. Its earlier unchanged-product baseline
classification above remains separate; it is not claimed as a current pass.
The TBIN1 case passed this run, without invalidating its earlier reproduced
baseline race. The previously completed **12,065 passed / 271 skipped** full
backend result predates these two final adjustments; the full suite was not
repeated in this pass. The fresh affected regressions total 428 backend passes.

### Exact local commit inventories

Every staged diff was inspected and checked for whitespace errors before
commit; an index guard checked the exact allowlist and equality with the
reviewed working files. Staged patches and blob hashes are retained in the
fresh evidence directory.

**A — `b623e54d9fa1bdd7d3732cee5d7f48d9920c810a`**
(`fix(ben): preserve BEN5K physical channel mapping`):

- `backend/app/providers/ben/legacy_ben5k/normalize.py`
- `backend/tests/fixtures/ben/ben5k_physical_mapping.json`
- `backend/tests/test_ben5k_physical_mapping.py`
- `backend/tests/test_ben5k_reference_mapping.py`
- `browser-tests/ben5k-physical-mapping.spec.js`
- `docs/project-memory/BEN5K_PHYSICAL_MAPPING_CORRECTION.md`
- `docs/project-memory/BEN5K_EXACT_EVENT_COMTRADE_PARITY_SPEC.md`

**B — `71a34299e16385dea7decb4082f604c2ecd17e81`**
(`fix(comtrade): honor declared 1999 ASCII missing data`):

- `backend/app/providers/comtrade.py`
- `backend/tests/test_comtrade_ascii_missing_data.py`
- `browser-tests/comtrade-ascii-missing-data.spec.js`

This assessment and
`docs/project-memory/PHYSICAL_CALIBRATION_AUTHORITY_PROPOSAL_2026-11-11.md`
are recorded in a separate documentation-only follow-up. Recording the
proposal does not approve its design or implement any safety gate.

### Protection, remaining limits and stop condition

The new protection manifest covers 2,271 files, excluding the now-approved
A/B and documentation files. **2,270 retain their original content hashes and
mtimes**, including prior audit evidence, backup data, test logs and the
protected CURRENT_STATE/HANDOFF edits. The one exception is an externally
edited PULU browser spec: it advanced from 239 to 255 added lines while this
task ran. Its observed SHA-256 changed from
`124cfcdd4067d4cf3cffe7041a9b84b12566d5c6efaf2d3026907e57a7c39df2`
to `42f76c948137e805fa25f4836ac437f7b96cd2b220466f53ae8c81a41e0ae515`.
Codex neither wrote, staged nor committed that file; the advanced edits remain
in place. No existing evidence was overwritten. No reset, stash, clean,
checkout/rebase, push, merge or deployment was performed.

**A and the five confirmed B cases meet their bounded local acceptance
checks.** The existing PULU unit-axis defect and intermittent Plotly race
remain separate owner-review issues. Absolute BEN5K calibration and the
proposed authority gate remain open; √2/16 is not implemented. Re-import is
required for previously decoded live sources. This is not overall release
readiness or engineering-reliability sign-off. Stop for owner review; no
Slice 6D work is authorized.
