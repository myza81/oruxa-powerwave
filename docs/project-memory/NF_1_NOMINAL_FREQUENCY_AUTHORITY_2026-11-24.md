# NF-1 — Recording nominal-frequency authority (backend foundation)

**Date:** 2026-11-24 · **Decision:** [DEC-217](DECISIONS.md) · **Branch:** `feature/nf-1-nominal-frequency-authority`, worktree `.local-data/nf-1`
**Baseline:** `0aa3562` = published DEV `e9c621c` + the accepted R0 and R1A commits (`2a7ddc1`, `fb5bb75`, `9bb5f38`, `5f932ec`, `9267ca4`, `9f45913`) merged unchanged (SHAs preserved).
**Status:** implemented and verified locally. **Not pushed, merged or deployed.** NF-2 and NF-3 are not started.

## What it does

A recording has one nominal frequency. `resolve_nominal_frequency()` (pure, `domain/nominal_frequency.py`) decides it from the immutable imported value, the import provenance and an optional manual value; `services/nominal_frequency_service.effective_nominal_frequency()` is the one accessor. **No engineering consumer reads it yet**, so a stored manual value changes no calculation until NF-3.

| Situation | Effective value | Origin |
|---|---|---|
| Valid value declared by the file (COMTRADE `lf`) | as declared | `recording_metadata` |
| BEN, value supplied at upload | as supplied | `import_supplied` (part of Auto; accurate origin) |
| Value missing, or the importer flagged `nominal_frequency_assumed` | **50 Hz** | `assumed_default` |
| Declared but not valid (0, negative, NaN, ±inf, outside 1–1000 Hz) | **none** — preserved as imported, reported unusable | `unusable` |
| Manual value stored (valid) | the manual value | `manual` |

Auto is recomputed on every read and never stored, so returning to Auto restores it exactly. Validity is the existing `nominal_frequency_valid` (1–1000 Hz, finite, not a bool); algorithms keep their own extra prerequisites. A manual value equal to Auto is stored (D9). An absent COMTRADE flag means "declared" (D5).

## Registry and API

* `NominalFrequencyRegistry` (`services/`): in-memory, `(workspace_id, source_id) → {value_hz, set_at}` plus a `revision` that moves only when the stored state changes (a new or different value, a removal). Removed with the recording (`DELETE /sources/{id}`) and with the workspace (`DELETE /workspaces/{id}`).
* `GET|PUT /api/v1/workspaces/{ws}/sources/{id}/nominal-frequency`. GET returns `mode, effective_hz, usable, origin, imported_hz, imported_text, auto_hz, auto_origin, manual_hz, revision`. PUT takes `{"mode":"manual","value_hz":60}` or `{"mode":"auto"}`.
* Errors: unknown recording → 404 `source_not_found`; invalid or missing value, or `value_hz` with `auto` → 400 `invalid_nominal_frequency` (nothing stored); wrong types or unknown fields → 422. `imported_text` keeps an unusable declared value visible (`nan`, `0.0`).
* `SourceSummaryOut.nominal_frequency` is unchanged (still the imported value).

## Files

New: `domain/nominal_frequency.py`, `services/nominal_frequency_registry.py`, `services/nominal_frequency_service.py`, `schemas/nominal_frequency.py`, `api/v1/nominal_frequency.py`, `tests/test_nf1_nominal_frequency_authority.py`. Edited (wiring only): `main.py`, `api/v1/sources.py`, `api/v1/workspaces.py`, and one inventory line in `tests/test_comtrade_nominal_frequency_provenance.py`.

## Verification

* `test_nf1_nominal_frequency_authority.py`: 163 tests (resolver table, registry, API, validation and no-500, lifecycle, isolation, originals hashed before/after, consumer-inventory tripwire).
* 13 of 14 mutations killed (manual precedence, unusable→50, assumed flag, BEN origin, predicate, revision, cleanup ×2, validation, reset, metadata write, workspace key); the survivor is behaviourally equivalent (pydantic already serialises NaN as null).
* Full backend suite: **14 446 passed, 405 skipped, 1 failed** in 40 min. The one failure was the R1A reader-inventory tripwire, which requires a new reader of `nominal_frequency_assumed` to be reviewed; the resolver is that intended reader and was added to the list (no assertion relaxed). The 497 tests of the four related modules pass after the change; the full suite was not re-run after that one-line list entry.
* Protected files (RMS, detectors, PU, CT/VT, side conversion, providers, import, every current consumer service): 38 of 38 byte-identical to `0aa3562`. Samples, `SourceMetadata` and provenance are hashed unchanged across set/change/clear.

## Limits and next steps

* No consumer honours the override; the nine direct readers of `metadata.nominal_frequency` remain (frozen by a tripwire that may only shrink) — NF-3.
* No UI (NF-2). A manual value is silent if wrong (a 60 Hz value on a 50 Hz signal gives no error); origin and revision are available for later provenance.
* Calculated channels already created keep their stored frequency; staleness and provenance recording are NF-3/NF-5.
* Ready for NF-2 (Recording Details Auto/Manual row) against this API. The owner's rule stands: the control is not released for normal use before NF-3.
