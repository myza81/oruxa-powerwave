# BEN5K physical-channel mapping correction

Date: 2026-11-10; approval follow-up: 2026-11-11. Owner-authorized scope:
physical mapping only. Local changes
based on `bb370678bec4ae3ce2ae1b1a334dccaa1790e6d0`, branch
`feature/vlt-ref-001-voltage-reference-safety`. Owner approved an isolated
local mapping commit; no push, merge or deployment is authorized.

## Mechanism and limits

The existing classifier correctly returns phantom-corrected
`physical_word_index`, and the standalone decoder uses it. The legacy
normalizer instead constructed a shared `BenSampleSlot` with logical
`word_index`. `BenRecord.raw_values()` and all normalized consumers then read
the original column, including later voltage phases or digital words.

The production change is one field assignment, with a comment, in
`backend/app/providers/ben/legacy_ben5k/normalize.py`:

```python
slot = BenSampleSlot(word_index=ch.physical_word_index, bit=0, slot_kind=0)
```

The descriptor's logical index and original bytes remain in the source file;
the shared sample slot now addresses its actual payload. No shared model/API
extension, classifier change, matrix rearrangement or transaction mechanism is
needed. Existing shared normalization, provider, waveform and calculation
services consume the corrected slot automatically.

**Absolute calibration is not corrected or certified.** The packed-word
formula `signed16 * descriptor_coefficient + offset`, unit assignment, nominal
detection, side authority and PU rules are unchanged. The proposed √2/16 factor
is not implemented. Permas PLTG1 VR is unshifted and still has the previously
observed −2620.6891937553883 value labeled kV. Correct mapping does not make
these engineering amplitudes reliable.

Existing imported live sources retain their previously decoded arrays. A
re-import through the corrected code is required; no existing workspace,
original recording or stored configuration is rewritten.

## Reproduction and golden coverage

Before the adapter correction, the new backend tests produced **41 failures
and 28 passes**: 35 shifted real-channel slot failures, four synthetic
mapping/consumer failures and two real provider/API failures. All 27 unshifted
real channels and the synthetic no-phantom case passed.

After correction, the same **69 tests pass**. The golden manifest pins all
27 Permas and 35 GPTH active analog channels, including descriptor addresses,
logical/physical indices and packed-column SHA-256 hashes. Files are located
by exact name/size/SHA-256 under `--ben-reference-dir`; binaries are not
committed. The exact originals and identities are listed in the
[parity specification](BEN5K_EXACT_EVENT_COMTRADE_PARITY_SPEC.md).

Expected samples are read independently with scalar `struct.unpack('>h', ...)`
at pinned physical addresses, not produced by the classifier under test.
Every sample is compared with the raw BEN model, shared normalized record,
provider and imported waveform API. Cursor A/B and both peak values are checked
for every real channel; affected Current channels also feed calculated polarity
results. Synthetic CI coverage exercises zero/one/two phantoms, duplicate
descriptors, negative values, a nonzero offset and unchanged digital states.

An independent verification CSV confirms **497,583 packed samples across all
62 channels**, including **281,568 samples across the 35 affected channels**.
These are mapping/formula goldens, not physical-calibration or OEM parity
goldens. The classifier's broader applicability and future file variants remain
subject to their own evidence.

## Every corrected channel

| Recording | Channel | Old logical slot | Correct physical slot |
|---|---|---:|---:|
| Permas Jaya | KTBR2 VR | 16 | 15 |
| Permas Jaya | KTBR2 VY | 17 | 16 |
| Permas Jaya | KTBR2 VB | 18 | 17 |
| Permas Jaya | KTBR2 IR | 20 | 19 |
| Permas Jaya | KTBR2 IY | 21 | 20 |
| Permas Jaya | KTBR2 IB | 22 | 21 |
| Permas Jaya | KTBR2 IN | 23 | 22 |
| Permas Jaya | PGPS1 VR | 24 | 23 |
| Permas Jaya | PGPS1 VY | 25 | 24 |
| Permas Jaya | PGPS1 VB | 26 | 25 |
| Permas Jaya | PGPS1 IR | 28 | 27 |
| Permas Jaya | PGPS1 IY | 29 | 28 |
| Permas Jaya | PGPS1 IB | 30 | 29 |
| Permas Jaya | PGPS1 IN | 31 | 30 |
| GPTH | SDNK1 VR | 16 | 15 |
| GPTH | SDNK1 VY | 17 | 16 |
| GPTH | SDNK1 VB | 18 | 17 |
| GPTH | SDNK1 IR | 20 | 19 |
| GPTH | SDNK1 IY | 21 | 20 |
| GPTH | SDNK1 IB | 22 | 21 |
| GPTH | SDNK1 IN | 23 | 22 |
| GPTH | TBIN2 VR | 24 | 23 |
| GPTH | TBIN2 VY | 25 | 24 |
| GPTH | TBIN2 VB | 26 | 25 |
| GPTH | TBIN2 IR | 28 | 26 |
| GPTH | TBIN2 IY | 29 | 27 |
| GPTH | TBIN2 IB | 30 | 28 |
| GPTH | TBIN2 IN | 31 | 29 |
| GPTH | SDAI2 VR | 32 | 30 |
| GPTH | SDAI2 VY | 33 | 31 |
| GPTH | SDAI2 VB | 34 | 32 |
| GPTH | SDAI2 IR | 36 | 34 |
| GPTH | SDAI2 IY | 37 | 35 |
| GPTH | SDAI2 IB | 38 | 36 |
| GPTH | SDAI2 IN | 39 | 37 |

Permas has one phantom (logical 15), GPTH two (logical 15 and 27). GPTH SDAI2
IB/IN must read physical 36/37 rather than digital words 38/39. The remaining
13 Permas and 14 GPTH analog channels retain their original slots and values.
The manifest checks every active channel, not only this table.

## Permas nominal-voltage discrepancy — bounded assessment

[FACT] BEN5K_ENGINEERING_VALIDATION.md §10 calls the station 132 kV and says
the values are “nominal 132 kV secondary.” Those descriptions do not cite an
independent wiring/calibration oracle and are not sufficient reference-side or
nominal authority. The historical report is preserved unchanged.

[FACT] All 12 recorded Permas Voltage descriptors contain `KV` and limits
±158.77000427246094. These are compatible with a 275/√3 magnitude, but their
display-range semantics and Primary/Secondary authority have not been proven.
The previously hypothesized approximately 159 kV RMS is not used as a nominal
detector or acceptance target.

[FACT] Independent first-party project records describe Permas Jaya as a
275/132 kV installation: PESTEC's own SCS/IEC-61850 project lists that Voltage
level and completion in 2018; Mega Linear's own portfolio identifies a
275/132 kV Permas extension with two 275 kV OHL feeders.
[PESTEC project](https://pestec-international.com/node/1019),
[Mega Linear portfolio](https://megalinear.com.my/pastprojects).
These establish station-level corroboration, not the identity/reference of
the October channel terminals.

[FACT] The local BEN database has a recorder-488 directory and matching bay
labels. Read-only inspection of PARAM_HD.0A, PARAM_M.0, PARAM_HD.1A, PARAM_M.1
and param_s found no exact copy of the October embedded configuration.
Their names/parameters were not promoted to event-date authority; their format
was not assumed identical to the embedded 58-byte descriptors. A bounded
assessment JSON retains file hashes and selected non-secret channel text.

[FACT] Stronger independent evidence is available in the same owner event
folder: `SOE PMJY.pdf`, pp.1–2, identifies the 16 October 2026 network devices
`PMJY LN 275 KV FEEDER PLTG1`, `PLTG2`, `PGPS1`, `PGPS2`, `KTBR1` and `KTBR2`.
It separately identifies MAJD1/2 and KPTR1/2 as 132 kV feeders, the 275 kV
north/south buses, 132 kV main/reserve buses and 275/132 kV SGT1/2. In particular,
all four recorded Voltage-group bay names (PLTG1, PLTG2, PGPS1, KTBR2) have
an independently documented 275 kV network context. This uses the SOE device
identity text, not its timing as proof of synchronization with the BEN file.
The private source remains at
`D:/OneDrive - Tenaga Nasional Berhad/WorkFiles/Tripping Event/2026/20261016 132kV_KTBR/SOE PMJY.pdf`;
its SHA-256 and extracted matching lines are retained in the isolated
`permas-soe-assessment.json`. PDF SHA-256:
`1b9e44901e798eb63ca9dcb5eeae9615a015ae1ebfa18f1e4f8d1dbf126d3955`.
Neither PDF nor full SOE text is committed.

[INFERENCE] The historical blanket “132 kV” description is inappropriate for
these named bays: **275 kV is independently corroborated as their network
nominal**, without using the approximately 159 kV candidate RMS. The recorder's
terminal-to-bay mapping, Primary/Secondary side, actual gain and instantaneous
versus RMS-equivalent convention still need exact-event BEN32/configuration/VT
evidence. A network nominal does not certify any of those properties. No
nominal detector, Vbase, scale factor or side metadata is changed by this
assessment.

## Validation and preservation

The completed A/B assessment records the full backend result: **12,065 passed,
271 skipped, zero failures/errors**, with owner references enabled. That run
preceded the final browser-path and conditional-copy adjustments; it is not
claimed as a new full-suite execution after those adjustments. Fresh affected
regressions and local commit identities are recorded in
[the A/B handoff](BEN_CONFIRMED_DEFECTS_ASSESSMENT_2026-11-11.md).

The mapping browser spec now reads only `GPTH_BEN_PATH` / `PERMAS_BEN_PATH`.
It explicitly skips an unset or unavailable private reference; an available
file must still match the original hash and every plotted sample assertion.
Private recordings are not embedded in tests or committed. The exact-event
parity specification is prepared separately; parity has not been run because
the exact October exports have not been supplied.

Protected evidence and the pre-existing PULU browser-spec edit are not part of
this change. Outputs use a new isolated temporary evidence directory. No
push, merge, deployment, calibration implementation or Slice 6D work. The
mapping correction does not resolve the separately reproduced baseline PULU
panel-unit defect or intermittent TBIN1 Plotly error; see the A/B assessment.
