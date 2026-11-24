# RMS display mode — R1A: COMTRADE nominal-frequency provenance

**Date:** 2026-11-24
**Branch / worktree:** `feature/rms-display-r0-shared-authority`, `.local-data/rms-r0` (R1A stacks on the accepted R0 commits `2a7ddc1`, `fb5bb75`, `9bb5f38`)
**Status:** implemented and verified locally. **Not pushed, merged or deployed.** Stopped for owner review; R1 has not been started.
**Authority:** the owner's "R0 Acceptance and R1A Implementation Authorisation" (2026-11-24), which implements owner decision D6.

Labels follow the project convention: **[FACT]** verified, **[PROPOSAL]** not yet decided, **[OPEN]** needs an owner decision.

---

## 1. What R1A does

[FACT] A COMTRADE `lf` (nominal frequency) line that `float()` cannot parse is replaced by 50 Hz with only a Python warning, so a declared 50 Hz recording and a recording whose frequency the parser substituted were indistinguishable downstream. R1A records the substitution, with the provenance key BEN and CSV/Excel imports already use:

```
ComtradeProvider.load_with_provenance(...)  ->  {"source_format": "COMTRADE", "nominal_frequency_assumed": True}
```

(merged with `channel_renames` when both apply). It is stored in the source's `preparation_provenance` by the unchanged import service. The value, the warning, and which files are accepted are exactly as before. No RMS-specific frequency model was created.

Production change: `backend/app/providers/comtrade.py` only (one new defaulted field on the private `_CfgData`, one assignment in the existing fallback branch, and `load_with_provenance` builds the dict).

## 2. Verified pre-change behaviour (frozen in `5f932ec`, before any production change)

[FACT] Verified by running the parser, not assumed. Only an `lf` that `float()` rejects is a fallback:

| `lf` line | Effective frequency | Accepted | Warning | Provenance before | After R1A |
|---|---|---|---|---|---|
| `50`, `50.0`, `  50  `, `+50`, `5e1`, `5_0` | 50.0 | yes | none | none | none (declared) |
| `60`, `60.0` | 60.0 | yes | none | none | none (declared) |
| `25`, `16.7`, `400`, `1000` | as written | yes | none | none | none (declared) |
| `1001`, `0.5`, `1e-9`, `1e308` (outside the RMS 1–1000 Hz range) | as written | yes | none | none | none (declared) |
| `0`, `0.0`, `-0.0`, `-50` | as written | yes | none | none | none (declared, invalid) |
| `nan`, `inf`, `-inf`, `Infinity`, `1e999` | as written (NaN / ±inf) | yes | none | none | none (declared, invalid) |
| `abc`, `50Hz`, `50 Hz`, `50,60`, `50 60`, `50,`, `50,5`, `0x32`, `-`, `None`, `5²`, `,`, `50..0` | **50.0** | yes | `Cannot parse nominal frequency … defaulting to 50.0` | none | **`nominal_frequency_assumed: True`** |
| empty or whitespace-only line | **50.0** | yes | same | none | **`nominal_frequency_assumed: True`** |
| `lf` line absent (file truncated) | — | **rejected** `ProviderLoadError` (missing field) | — | — | unchanged |
| `lf` line removed, later lines shift up | — | **rejected** (`Cannot parse nrates`) | — | — | unchanged |

The same holds for the 1991, 1999 and 2013 layouts. An unrecognised or non-standard `rev_yr`, an unparseable `timemult`, a malformed `nrates` and `BINARY32` are other existing parser paths; none concerns frequency and none sets the flag by itself (an unparseable `lf` in a file that also has an unrecognised `rev_yr` is flagged, because of the `lf`).

[FACT] The earlier assumption that "all invalid frequency cases fall back to 50 Hz" was **wrong**: zero, negative, NaN, infinite and out-of-range values pass through untouched and the file is accepted. The upload endpoint does not validate the frequency either (HTTP 201 for all of them). R1A preserves this.

## 3. Existing provenance model (reused)

| Source | Where | Shape |
|---|---|---|
| BEN | `BenProvider.load_with_provenance` | `nominal_frequency_hz` and `nominal_frequency_assumed` (bool, **always written**) |
| CSV / Excel | `preparation_conversion_service` | `nominal_frequency_assumed: True` (always; no format declares a frequency) |
| COMTRADE (R1A) | `ComtradeProvider.load_with_provenance` | `nominal_frequency_assumed: True` **only when the parser substituted the default** |

All are stored in `SourceMetadata.preparation_provenance` and read with `.get("nominal_frequency_assumed")`.

[FACT] **COMTRADE writes the flag only when it is true** (absent means declared). BEN writes an explicit `False`. The reason is the owner's rule that existing tests stay unchanged: `test_comtrade_duplicate_names.py` asserts that an ordinary COMTRADE load returns `provenance is None` and that a rename-only load returns exactly `{source_format, channel_renames}`. Every reader treats an absent key as false, so the result is the same. [OPEN] If the owner wants an explicit `False` for COMTRADE, two existing assertions need a narrow additive amendment, separately approved.

[FACT] The flag says only "the parser substituted this value". It does **not** assert that a declared value is valid: a declared `0`, `-50`, `NaN` or `1001` is reported as declared (flag absent) with its value untouched, and `nominal_frequency_valid()` still judges it at the point of use. Nothing was invented to represent "declared but invalid".

## 4. Downstream consumers

[FACT] Consumers of the **value** (`metadata.nominal_frequency`, `sampling_info.nominal_frequency`) are unaffected because the value is identical: Calculated Channels and RMS eligibility, phasor analysis, power channels, protection and overcurrent analysis, event detection and synchronization, compliance measurement, Recording Details. The only consumers of `preparation_provenance` are:

| Consumer | Reads | Effect for a COMTRADE source with an unparseable `lf` |
|---|---|---|
| `oscillation_representation_service._nominal_frequency` | `nominal_frequency_assumed` | origin becomes `assumed_default` (was `recording_metadata`); the oscillation spectrum/damping/cross-signal outputs carry the existing `nominal_frequency_assumed` warning, and classification lists it as limiting evidence |
| `schemas/source.py` | `interpreter_id` only | none (the API response shape is unchanged; frozen) |

[FACT] This is the one **intended behaviour change**: the oscillation analysis now discloses an assumed 50 Hz for COMTRADE exactly as it already does for BEN and CSV/Excel. It happens only for the previously silent substitution case; every other source is byte-identical. A tripwire test lists the nine `app` modules that mention `nominal_frequency_assumed`, so a new reader must be reviewed.

## 5. Verification

| Check | Result |
|---|---|
| Frozen pre-change baseline | commit `5f932ec`; 132 scenarios (55 synthetic CFG variants, each through the parser and through the upload endpoint, plus the 22 checked-in fixtures, 3 of which are rejected today for lack of a DAT); regenerated twice and byte-identical before writing |
| Parity after R1A | all scenarios reproduce the frozen value, acceptance/rejection, exception text, warnings, whole-record fingerprint (samples, timestamps, channel descriptors, sampling and timing), upload status, response keys and stored frequency; provenance fields compared exactly for every non-fallback scenario |
| New provenance tests | `test_comtrade_nominal_frequency_provenance.py`, 149 tests |
| R0 golden vectors (38), R0 behavioural baseline (148), R0 shared-authority tests (37), COMTRADE, BEN import, oscillation and slice-11 suites | 778 passed, 56 skipped, unchanged |
| Doc-scanning suites (29 files) with this report present | 1,601 passed |
| Full backend suite, accepted R0 baseline | 13,870 passed, 405 skipped, 0 failed |
| Full backend suite, after R1A | **14,167 passed, 405 skipped, 0 failed** (+148 frozen-baseline tests +149 provenance tests; identical skips) |
| Existing tests | none modified (`git diff --name-status` over `backend/tests` shows only additions) |
| Sensitivity (12 injected regressions in an out-of-tree copy: flag never/always set, fallback value 60, new fallback for 0, new fallback for NaN, warning dropped, flag written False, wrong key, renames dropped, a declared exponent form rejected, provenance dict always returned, missing `lf` turned into a fallback) | all caught (one mutant I first wrote turned out to be equivalent and was replaced) |

## 6. Remaining limitations

- [FACT] The flag is a bool, not a record of *why* (unparseable text versus empty line) or of the original text; the Python warning still carries that and is unchanged.
- [FACT] Nothing in the application shows the flag to the user yet: Recording Details does not surface it (an existing gap recorded in `RECORDING_METADATA_AUTODETECTION_AUDIT.md`). R1A is metadata only.
- [OPEN] **Explicit-invalid versus substituted is still a policy question.** The parser keeps accepting `0`, negative, NaN, inf and out-of-range frequencies, and keeps replacing unparseable text by 50 Hz. Any change of that resolution policy is for separate owner review, as the authorisation requires.
- [FACT] The unvalidated frequency on `POST .../calculated-channels/rms-eligibility` (HTTP 500 for `0`, `ValueError`/`IndexError` for other odd values) was **not** touched and remains tracked separately (see the R0 report, section 4).

## 7. Mandatory requirements recorded for R1 (not implemented)

- Validate the nominal frequency **before** waveform-form classification.
- Distinguish missing, assumed and explicitly invalid frequency (the three states now observable for COMTRADE: absent `lf` is rejected at import; assumed is flagged; declared-invalid passes through and must be checked with `nominal_frequency_valid`).
- Preserve a valid assumed frequency, including non-50 Hz where supported.
- Do not inherit the existing eligibility endpoint's unhandled exceptions.
- Use the accepted R0 shared prerequisites and classifier.
- Do not invent trusted versus operation-derived provenance.
- Do not write detector classifications back into authoritative metadata.
- Conservative display eligibility, no override.
- Match the existing physical-calibration safeguards.
- Prevent RMS-of-RMS conversion.
- Bound any batch eligibility workload before exposing it.
- Preserve the existing detector mathematics.

## 8. Proposed documentation updates (not applied; existing project-memory documents were not modified)

- `CURRENT_STATE.md`: a short R1A paragraph (COMTRADE now flags a substituted nominal frequency).
- `HANDOFF.md`: this slice's outcome and the stop point.
- `RECORDING_METADATA_AUTODETECTION_AUDIT.md`: the "BEN assumed flag" row can note COMTRADE now uses the same key.
- `DECISIONS.md`: **no number is reserved here**; to be numbered at owner approval after re-checking parallel branches.

## 9. Next step

Owner review of this slice. R1 starts only on explicit approval.
