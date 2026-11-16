# Legacy BEN5K Fast AC — local P1 corrective candidate

**Branch:** `fix/ben5k-fast-ac-scaling-p1`

**Base:** current `origin/main`, `dfdab785eed1da9109dc046d239ba42fd95212af`

**Status:** owner accepted the bounded candidate and authorized its local commit
on 2026-11-17. No push, merge or deployment is authorized; P2 has not begun.
The original dirty investigation checkout and other worktrees are preserved.
Implementation was authorized on 2026-11-16; runtime code and evidence fixtures
are unchanged from the reviewed candidate. The next milestone is DEV waveform
UAT on GPTH/Permas after PR and CI approval and deployment authorization.

## Correction and exact code boundary

The legacy adapter previously defined a packed word as a full signed int16
measurement and passed its unadjusted descriptor gain into the shared linear
projection. It therefore retained the low nibble, overstated the ADC count by
about 16, and omitted the independently evidenced AC representation factor.

The candidate implements exactly:

```text
engineering = (signed_int16_word >> 4) * descriptor_gain * sqrt(2)
```

The right shift is arithmetic on signed int32, followed by float64 multiplication.
It preserves negative sign and discards the low nibble. It does not divide by 16,
change units, infer a CT/VT ratio or modify a PU base.

Changed functions:

| File | Function / change |
|---|---|
| `backend/app/providers/ben/legacy_ben5k/engineering.py` (new) | `fast_ac_engineering_values()` implements signed extraction and the one-time AC conversion; rejects nonzero offsets, nonfinite gain and inputs outside signed int16 |
| Same module | `has_supported_fast_ac_configuration()` and `is_supported_fast_ac_descriptor()` bound applicability; `Ben5kRecord.engineering_values()` supplies the legacy-only projection while inherited raw access stays unchanged |
| `legacy_ben5k/normalize.py` | `parse_ben5k()` selects eligible channels and returns the legacy record subtype; existing physical slot mapping is retained verbatim |
| `legacy_ben5k/decoder.py` | `decode_samples()` uses the same conversion for eligible channels; retains its existing float32 diagnostic return contract |
| `ben/normalize.py` | `to_disturbance_record()` retains Unverified authority and its reason; describes corrected channels with transform ID `ben5k_v2_fast_ac_s12_gain_sqrt2_zero_offset` |

**Shared `BenRecord.engineering_values()` is unchanged.** The legacy subtype
preserves original `sample_words`, `raw_values()`, coefficient metadata, units,
timing and diagnostics. The normalized arrays use corrected values once;
neither waveform services nor the frontend perform another multiplication.

## Explicit applicability

The legacy catalog has no independently established general AC/DC selector.
This **bounded local candidate** recognizes complete embedded configuration
fingerprints from the three reviewed recordings. These fingerprints cover bytes
`[0xDC, payload_start)`; they exclude event clock and sample data. They are
evidence identities, not machine paths or physical-calibration claims.

| Reviewed configuration | SHA-256 of embedded configuration |
|---|---|
| BPHE 2022 Fast | `2fc25dfff1207c0a411c533a88adb96661e6c503ab89c430074bca43c05569fe` |
| GPTH October 2026 Fast | `56c4c52597ccb28fd3f266b6aac5ba7dd2e7723adf75b5b8a53cac33237f6543` |
| Permas October 2026 Fast | `550ad948004d29c2210ad352939c2b37599c41c24c0ec3b7632a8cd26a69db77` |

In addition, the complete legacy signature/generation must match, the original
class flag must be Fast (`0`), and each eligible descriptor must have zero offset,
finite gain, a V/I quantity, a phase/neutral identity and matching `KV`/`KA`
metadata. The legacy projection also checks the canonical channel metadata.
Names, nominal voltage and waveform magnitude do not select the formula.

Changed/unrecognized configurations, unidentified representations and nonzero
offsets retain their previous raw diagnostic projection and Unverified status;
they are not silently assigned this AC contract. Generalizing beyond these
reviewed configurations requires further AC/DC interpretation evidence. This is
the deliberate applicability limit of the candidate, not a claim of general
legacy-family support.

BPHE's missing descriptors and wrong physical addresses are unchanged. The
numeric function is tested against all 14 independently identified physical
columns, separately from its still-faulty native mapping. P1 does not make BPHE
end-to-end import correct.

## Before / after

Zero-based sample index 0; original descriptor gains and zero offsets retained:

| Recording / quantity | Before | P1 value | Independent target / scope |
|---|---:|---:|---|
| BPHE YGPN/BBTU1 VR, correct physical slot | 272.841943637 kV | 23.937938903 kV | Export 23.937938842 kV; numeric-only test, channel remains omitted by current mapping |
| BPHE YGPN/BBTU1 IR, correct physical slot | 2.675425384 kA | .211671209 kA | Export .211671206 kA; numeric-only test |
| GPTH TBIN1 VR | -2545.126972944 kV | -225.137682949 kV | Owner-approved bounded same-family application |
| GPTH TBIN1 IR | 11.057177637 kA | .952520441 kA | Same scope |
| Permas PLTG1 VR | -2483.104690582 kV | -219.655658337 kV | Same scope |
| Permas PLTG1 IR | -4.808281984 kA | -.449801319 kA | Same scope |
| Permas KTBR2 IR | -14.144207630 kA | -1.270027318 kA | Its own .01496741548 gain is retained |

For BPHE second-feeder IR, the correct physical word is 15 while native mapping
still reads word 20. Correcting the arithmetic of word 20 does not change its
identity into word 15; the test explicitly asserts that discrepancy remains.

## Independent parity and regression evidence

The existing recovered artifacts were reused as frozen scalar fixtures and
full-record comparison authorities. No root-cause reinvestigation was performed.

- **BPHE:** all **14 × 1,148 = 16,072** values match independent CFG/DAT engineering
  values, including Voltage, phase Current and neutral Current. Maximum absolute
  discrepancy is **6.448206306686188e-7** engineering units, from the printed CFG
  gain precision. Original three-file hashes and descriptor bytes are pinned.
- **GPTH/Permas:** **413 reviewed scalar vectors** plus all **62 mapping goldens /
  497,583 original words**. Signed negatives, low-nibble transitions, positive and
  negative int16 boundaries and zero measurement with nonzero low nibble are
  covered. Existing raw-column hashes and physical indices are unchanged.
- **BEN32 Fast/Slow:** original independent export parity and missing-value tests
  run with owner references enabled. Shared model code and the original
  **3,472,999 available analog values / 7,005 missing positions** are preserved.
- **BEN6K-labelled SubBen:** all **103 raw and engineering column hashes** in
  Tanjung Bin match the recovered initial-parser (`c2f7f2a`) baseline bit for bit.
- **End-to-end:** both October files import through the real provider/API.
  Every accepted channel's stored array, waveform response, both cursors and
  min/max peaks match corrected physical-slot expectations, including Current.
  Exploratory Current polarity calculations use the same corrected input.
- **DEC-213:** corrected channels remain **Unverified**, with the same limitation
  reason and existing PU/phasor/compliance/power eligibility rules. Real October
  Current PU requests still return `calibration_unavailable`. The transform ID
  describes arithmetic only; it does not upgrade authority.

| Validation | Result |
|---|---|
| Focused BEN and DEC-213 backend regression, owner references enabled | **1,112 passed**, zero failures/skips; 109.31 seconds |
| Local-commit confirmation, 2026-11-17: same focused BEN and DEC-213 selection | **1,112 passed**, zero failures/skips; 63.71 seconds |
| Full backend suite, owner BEN references enabled | **12,873 passed, 271 skipped**, zero failures/errors; 1,343.11 seconds |
| Real browser import/mapping and DEC-213 regression (7 suites) | **31 passed**, zero failures/skips |

Full-suite skips comprise 17 POSIX-shell checks unavailable on Windows, 153
relay-PDF checks without the optional owner PDFs, and 101 relay-profile cases
explicitly marked inapplicable by their fixtures. **No required BEN evidence
check was skipped.** No unrelated behavior was changed to alter these skips.

Backend runs used `python -m pytest tests --ben-reference-dir "<owner BEN root>"`
(the focused run selected BEN and calibration-gate test modules). Browser suites:
`ben5k-physical-mapping`, `ben-import`, `ben5k-pu-calibration-gate`,
`ben5k-calculated-channel-pu-gate`, `ben5k-phasor-calibration-gate`,
`compliance-calibration-gate` and `power-provenance`. Their existing experimental
flag and original GPTH/Permas owner-file paths were supplied for local testing.
Local JUnit results are in `.local-data/p1-regression.xml`,
`.local-data/p1-full-regression.xml` and `.local-data/p1-browser.xml` in this
candidate worktree. `git diff --check` also passes.

Local-commit confirmation reused the same original references and frozen fixtures;
BPHE complete export parity, GPTH/Permas vectors and mapping regressions, BEN32
Fast/Slow parity/missing-data checks, BEN6K hashes and DEC-213 tests all remain
passing. Its JUnit result is `.local-data/p1-commit-confirmation.xml`. The full
backend and browser suites were not repeated; their reviewed results above are
retained. Only owner-acceptance and confirmation documentation changed afterward.

Test additions: `test_ben5k_fast_ac_scaling.py`,
`test_ben5k_fast_ac_reference.py`, frozen BPHE/October vectors and BEN6K hashes.
The existing real mapping tests and real-browser array expectations now use the
approved P1 formula. No physical-column goldens, missing masks or gate assertions
were relaxed.

## Untouched formats and remaining limits

- BEN32 Fast and Slow SubBen, including BEN6K-labelled files: full-int16 contract.
- Legacy Slow `29 ff` (GRNE), and `28 ff` Slow (GPTH 2022): no P1 AC conversion;
  existing support limitations remain.
- Earlier `28 ff 02` and unsupported layouts: no decoding change.
- Other legacy configurations, nonzero offsets and unidentified DC channels:
  no P1 transform.
- COMTRADE and CSV/Excel providers, PU formulas, calibration evaluator/gates,
  frontend code, deployment and storage: unchanged.

P2 mapping remains a blocker for correct BPHE native import and was not started.
Exact-event independent amplitude exports for October and physical instrument /
reference-side verification remain separate evidence limits. Existing imported
workspaces are not rewritten; corrected candidate values require re-import.
No additional calibration framework or UI was introduced.
