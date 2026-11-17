# BPHE legacy BEN5K layout P2 — owner-accepted local correction

Branch: `fix/ben5k-bphe-layout-p2`, isolated from fetched
`origin/main=781b2b0ab978e7e472bf2f4742ca34db78744a3a` (PR #9 merged).
Owner confirmed GPTH/Permas P1 DEV UAT passed. On 2026-11-17 the owner accepted
this bounded P2 candidate and authorized its LOCAL COMMIT on the isolated branch.
No push, merge or deployment is authorized or performed. P2 integration and owner
DEV UAT must complete before another BEN correction stage starts.

**Result:** native BPHE import exposes **14 analog channels**; all **16,072**
engineering values match the original independent export. Both duplicate-name
occurrences retain distinct physical identities. All 62 accepted October channel
summaries, raw-column hashes and complete engineering-array hashes are identical
to the accepted P1 baseline.

The existing BEN-wide investigation, complete BPHE oracle and historical
`BEN5K_PHYSICAL_MAPPING_CORRECTION.md` were reused. The P1 BPHE fixture is identical
to the recovered full oracle; its source-manifest SHA-256 was rechecked. The P1
scaling investigation was not repeated.

## Exact root causes and correction

1. **Descriptor discovery started inside the wrong catalog.** `reader.py` used
   GPTH's `0xBBA` as a universal start, omitting all seven first-feeder BPHE
   descriptors, including its IN descriptor at `0xBB6`. BPHE is not a fixed-offset
   exception: the variable configuration tables independently locate its start.
2. **A logical selector was treated as a physical address under an inapplicable
   heuristic.** BPHE's second-feeder selectors 16/17/18/20/21/22/23 refer to
   physical 11/12/13/15/16/17/18. The October phantom/RMS correction cannot resolve
   these sparse positions. It has no independently established general packing
   contract for BPHE.

The new flat-region reader follows the actual prefix counts:

```text
n = feeder count at 0xED, repeated at 0xF6
s = sensor count at 0xF7
catalog_start = 0x12C + n*129 + s*20 + 6 + n*22 + 4
catalog_end   = payload_start - 10-byte configuration footer
```

The sequence is: fixed prefix, long feeder texts, sensor records, six-byte
separator, short feeder names, four-byte first-record prefix. Count agreement,
acquisition width, table boundaries, sensor entries and the exact footer are
checked before scanning. This yields:

| Configuration | n | s | Derived start |
|---|---:|---:|---:|
| BPHE | 2 | 12 | `0x354` |
| GPTH | 12 | 44 | `0xBBA` |
| Permas | 6 | 24 | `0x6A0` |

BPHE's bounded scan is `[0x354, 0x1C28)`; its payload starts at `0x1C32`.

For BPHE, complete 58-byte descriptors require coherent quantity/phase/unit,
printable padded name, finite coefficients/ranges, addressing marker and
terminator. All candidate starts are considered before accepting an inventory;
overlapping interpretations are rejected. Neither prefix text nor payload bytes
are scanned as descriptors. Duplicate names are retained, not used as keys.

**Mapping is deliberately bounded and evidence-backed.** The reviewed embedded
configuration SHA-256 is
`2fc25dfff1207c0a411c533a88adb96661e6c503ab89c430074bca43c05569fe`
(bytes `[0xDC, payload_start)`, as in P1). A complete explicit table validates each
descriptor offset, original selector, quantity and phase before assigning the
independently matched physical word. It bypasses the RMS heuristic. It is not a
universal minus-five rule, nor a new claim about hardware packing. An unreviewed
BPHE-style 2-feeder/12-sensor/24-word configuration is refused instead of falling
back to the old misaddressed import. Event-clock and sample changes alone do not
alter the configuration identity or addresses; zero/high/negative payload tests
confirm amplitude independence.

## All 14 descriptor identities and physical positions

Positions are zero-based. Source names are preserved verbatim.

| Source descriptor name | Occurrence | Phase seq | Descriptor byte | Logical → physical |
|---|---:|---:|---:|---:|
| YGPN/BBTU1 VR | 0 | 1 | `0x354` | 0 → 0 |
| YGPN/BBTU1 VY | 0 | 2 | `0x4C0` | 1 → 1 |
| YGPN/BBTU1 VB | 0 | 3 | `0x608` | 2 → 2 |
| YGPN/BBTU1 IR | 0 | 1 | `0x826` | 4 → 4 |
| YGPN/BBTU1 IY | 0 | 2 | `0x94A` | 5 → 5 |
| YGPN/BBTU1 IB | 0 | 3 | `0xA6E` | 6 → 6 |
| YGPN/BBTU1 IN | 0 | 4 | `0xBB6` | 7 → 7 |
| YGPN/BBTU2 VR | 0 | 1 | `0xEB6` | 16 → 11 |
| YGPN/BBTU2 VR | 1 | 2 | `0xFFE` | 17 → 12 |
| YGPN/BBTU2 VB | 0 | 3 | `0x116A` | 18 → 13 |
| YGPN/BBTU2 IR | 0 | 1 | `0x1388` | 20 → 15 |
| YGPN/BBTU2 IY | 0 | 2 | `0x14AC` | 21 → 16 |
| YGPN/BBTU2 IB | 0 | 3 | `0x15D0` | 22 → 17 |
| YGPN/BBTU2 IN | 0 | 4 | `0x1718` | 23 → 18 |

The second VR occurrence keeps its original name and phase metadata. Existing
shared normalization gives it API/trace identity `YGPN/BBTU2 VR_1`. Its native
channel ID, original descriptor bytes and physical word are distinct from the
first occurrence. BPHE descriptor bytes and an info-level descriptor/logical/
physical provenance diagnostic are retained; original sample words are untouched.

## Independent before/after examples

Actual native sample index 0, after P1 scaling in both revisions:

| Channel | Before P2 | After P2 | Independent CFG/DAT |
|---|---:|---:|---:|
| YGPN/BBTU1 VR | omitted | 23.937938903 kV | 23.937938842 kV |
| YGPN/BBTU1 IR | omitted | .211671209 kA | .211671206 kA |
| YGPN/BBTU2 VR, occurrence 0 | 3.799672842 kV (word 16) | 23.747955261 kV (word 11) | 23.747955200 kV |
| YGPN/BBTU2 VR, occurrence 1 | -5.509525620 kV (word 17) | -199.102856905 kV (word 12) | -199.102856397 kV |
| YGPN/BBTU2 IR | 3.386739346 kA (word 20) | .211671209 kA (word 15) | .211671206 kA |

All 14 × 1,148 values pass `rtol=3e-8, atol=1e-9`; maximum absolute discrepancy
is **6.448206306686188e-7 engineering units**, the same printed-CFG-coefficient
precision limit accepted in P1. The three original BEN/CFG/DAT SHA-256 values
remain pinned in the unchanged `ben5k_fast_ac_scaling.json` fixture. Expectations
come from complete original DAT columns, not a production conversion helper.

## Changed functions and files

- `legacy_ben5k/reader.py`: `read_descriptor_region()` and
  `_read_structured_descriptors()` implement bounded structural discovery;
  `read_channel_descriptors()` selects the reviewed BPHE path and returns its
  proven physical positions. Accepted October discovery remains unchanged.
- New `legacy_ben5k/bphe_layout.py`: `is_reviewed_bphe_configuration()` and
  `bphe_physical_words()` bound and validate the explicit export-backed table.
- `legacy_ben5k/channel_map.py`: `classify_channels()` accepts the complete map
  keyed by descriptor offset, rejects incomplete/conflicting addresses and
  bypasses the existing phantom heuristic for BPHE only.
- `legacy_ben5k/normalize.py`: `parse_ben5k()` passes that map, preserves the 58
  descriptor bytes and records the mapping provenance. No shared schema changed.
- Tests: new `test_ben5k_bphe_layout.py`, upgraded existing
  `test_ben5k_fast_ac_reference.py`, new `ben5k-bphe-layout.spec.js`.
- Evidence: [before](evidence/ben5k-bphe-p2-2026-11-17/before.json),
  [after](evidence/ben5k-bphe-p2-2026-11-17/after.json),
  [comparison/hashes](evidence/ben5k-bphe-p2-2026-11-17/comparison.json),
  [real browser screenshot](evidence/ben5k-bphe-p2-2026-11-17/bphe-waveform.png).
  The focused `scripts/diagnostics/ben5k_bphe_p2_native_summary.py` reproduces the
  summaries from each revision's `backend` directory with `--reference-root`
  and `--output`. The executed P1 baseline `eb67c52` has exactly main `781b2b0`'s
  tree `90a95859c6c24b4d4bbbd3db734c9016ee52a7a0`.

## Regression and end-to-end results

- **1,135 focused backend tests passed**, zero skips/failures/errors, including
  complete BPHE native parity, provider/import/stored arrays/API waveform/both
  cursors/min/max peaks, duplicate identities, descriptor bounds and ambiguity.
- **32 browser tests passed**, zero skips/failures: BPHE all 14 actual visible
  channels and full plotted arrays against independent exports, existing October
  plotted Voltage/Current checks, import and DEC-213 regression suites.
- **GPTH 35 / Permas 27:** all 62 original mapping goldens and 413 P1 scalar
  vectors pass. The before/after snapshots additionally assert identical full
  raw and engineering hashes, channel order, phase, units, gains and status.
- **BEN32 Fast/Slow:** original independent export parity and missing-data checks
  pass with all owner references enabled. **BEN6K:** all 103 original raw and
  engineering column hashes remain unchanged.
- **DEC-213:** all 14 BPHE channels remain Unverified; transform ID stays P1 v2.
  Real BPHE Voltage/Current PU requests return `calibration_unavailable`.
  Existing phasor/compliance/power browser and backend gates pass unchanged.

Reproduce backend selection: all `tests/test_ben*.py` plus
`test_physical_calibration.py`, `test_phasor_calibration_gate.py`,
`test_power_provenance.py`, `test_compliance_calibration_gate.py`, with
`--ben-reference-dir <owner root>`. Browser: the P1 seven suites plus
`ben5k-bphe-layout.spec.js`, experimental flag and three original BEN paths set.
Local JUnit: `.local-data/p2-final-regression.xml`, `.local-data/p2-browser.xml`.
The unrelated full backend suite was not repeated for this focused P2 candidate.
Local-commit verification rechecked both JUnit summaries, the evidence artifact
hashes, all 62 unchanged October channel summaries and the 16,072 BPHE matches.
Implementation, regression tests and numerical evidence are unchanged from the
accepted candidate; the existing test runs were retained without rerunning them.
The comparison manifest records Git-blob (LF) artifact hashes as well as the
original Windows (CRLF) snapshot hashes; Git changes only their line endings.

## Remaining limits and untouched contracts

- A general sparse acquisition map is **not proven**: prefix table counts locate
  descriptors, but no independently decoded configuration field establishes
  physical word assignment across other hardware/configurations. The BPHE table
  is valid only for the fingerprint above; expanding it needs independent column
  evidence. Digital addressing is not corrected or newly certified in P2.
- **Unresolved BEN-wide inventory issue — Permas configured entries**
  (`[OPEN]`, `[DECISION MODE: DEFER]`): the `0x6A0` derived start exposes four
  earlier `PGPS2 VR`, `PGPS2 VY`, `PGPS2 VB`, `PGPS2 IR` descriptors before the
  accepted `0xBBA` window. Promoting/reassigning them would change duplicate
  logical-slot selection and the owner's frozen 62-channel acceptance. P2 leaves
  Permas's accepted 27 channels unchanged and makes no claim of configured-inventory
  completeness. Later correction requires separate owner direction after P2
  integration and DEV UAT; see [CURRENT_STATE.md](CURRENT_STATE.md).
- P1 signed `>> 4`, `sqrt(2)`, gain/zero-offset contract and applicability are
  unchanged. BEN32/BEN6K, legacy Slow/earlier/other variant corrections, PU math,
  calibration framework, frontend display, warnings and deployment are untouched.
- Export parity is not physical instrument verification. DEC-213 restrictions
  and the existing BEN5K experimental opt-in remain; corrected BPHE values require
  a fresh import. No saved workspace or original recording is rewritten.
