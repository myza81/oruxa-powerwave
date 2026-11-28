# NF-1 through NF-3E integration against accepted main — record

Date: 2026-11-28. Status: **local integration candidate, verified, awaiting owner acceptance.** Not pushed, merged or deployed. No feature gate was changed.

## 1. Sources and baselines

| Item | Value |
|---|---|
| Accepted main baseline | `885bf8d` (merge of PR #14); `origin/main` verified equal to it on 2026-11-28; DEV runs `885bf8d` |
| Frozen NF source | branch `feature/nf-3e-calculated-channel-staleness`, functional `00387aa`, documentation tip `edf18b2` (frozen worktree `.local-data/nf-3e`, clean, untouched) |
| Merge base | `e9c621c` (main side 43 commits, NF side 50 commits; 12 files edited by both) |
| Integration branch / worktree | `feature/nf-integration` / `.local-data/nf-integration` (new; created from `885bf8d`) |
| Candidate commits | merge `e7f39ce`; test fix `ae5dfd9` (the only post-merge change). **Functional candidate: `ae5dfd9`** |

All seven NF worktrees (`nf-1`, `nf-2`, `nf-3a` to `nf-3e`) were clean before the merge and were not modified.

## 2. Strategy

One history-preserving merge (`--no-ff`) of the frozen NF branch onto `885bf8d`. No cherry-pick, squash, rebase or history rewrite. The NF lineage includes six RMS-display R0/R1A commits (golden vectors, shared RMS prerequisites extraction, COMTRADE assumed-frequency provenance) because NF-1 was built on that branch; the owner approved their inclusion (2026-11-28). No RMS kernel, RMS display or Waveform-toggle code changed.

## 3. Conflicts and resolutions

Six textual conflicts; each resolved by keeping both workstreams' additive changes.

| File | Conflict | Resolution |
|---|---|---|
| `api/v1/compliance.py` (2 hunks) | PU-MIG S2 `side_authority` vs NF-3E `frequency_access` passed to the same calls | Both passed |
| `services/compliance_series.py` | Two new `Registries` fields | Both fields kept |
| `services/compliance_readiness_service.py` (2 hunks) | Same two parameters at `Registries(...)` and the preparation `evaluate_readiness` call | Union of both parameters at both sites |
| `browser-tests/playwright.config.js` | Test backend env: BEN5K flag vs Manual nominal-frequency gate | `env` opens both (test backend only; each keeps its comment) |
| `docs/project-memory/DECISIONS.md` | PU appended Amendment 7, DEC-218, DEC-219; NF appended DEC-217 at the same position | All kept; DEC-217 placed ahead of DEC-218. No decision text edited |
| `docs/project-memory/CURRENT_STATE.md` | Two workstream sections at the same position | Both kept; updated in section 9 below |

Line endings (CRLF) were preserved. Auto-merged files edited on both sides were audited for shared functions (none in `calculated_channel_service.py`, `calculated_channels.py`, `sources.py`, `schemas/calculated_channel.py`) and are covered by the regressions below. `frontend/index.html` and `HANDOFF.md` merged cleanly.

## 4. One integration seam fixed (`ae5dfd9`)

The frozen RMS R0 service-behaviour baseline (written before PU-MIG S5) failed three calculated-channel API scenarios (`calculated-channels/waveform`, `cursor-values`, `peak-values`). A leaf-level diff proved the **only** difference in all three was the additive key `per_unit_verification_state: null` that PU-MIG S5 put on main. It is recorded as one documented additive entry in `backend/tests/nf3e_approved_changes.py` (the established approved-changes overlay). The frozen baseline JSON was not edited or regenerated and no expected value was altered.

## 5. Decisions preserved (no policy changed)

DEC-217 and DEC-218 applied. PU: S1–S6 shared denominator authority, DEC-209/210, DEC-212, DEC-213, DEC-215, DEC-216, DEC-219 (nominal is the Primary base; Voltage Base Reference Side selector and the Advanced reference container remain retired; Auto VT Secondary 110 V with Manual override), historical Secondary-base compatibility, verification states. NF: single effective-frequency authority, Auto/Manual, immutable original metadata, fallback/provenance policy, recording-following vs explicit frequency, direct and inherited staleness, no automatic recomputation, typed stale-input refusal, compliance/oscillation/phasor/overcurrent guards, NF-2 refresh event, minimal stale marker. These are all covered by the protected test sets, which pass.

## 6. Verification

**Phase A (focused, on `e7f39ce`):** app import and startup (130 OpenAPI paths = main 129 + 1 NF path); static frontend checks; 8,524 backend tests (NF, PU, calculated channel, compliance, phasor, overcurrent, oscillation and all 71 static frontend suites) passed, 5 skipped, 3 xfailed, 0 failed; 554 targeted browser specs passed, 1 skipped (the gated NF-2 screenshot spec), 0 failed.

**Phase B:**

| Suite | Result |
|---|---|
| Full backend, first run on `e7f39ce` | 16,757 passed, 410 skipped, 3 xfailed, **3 failed** (the S5 field seam in section 4) |
| **Full backend, final run on `ae5dfd9`** | **16,760 passed, 410 skipped, 3 xfailed, 0 failed** (13 min 54 s) |
| BEN owner-reference files (all `test_*ben*`) with `--ben-reference-dir` | 1,015 passed, 0 skipped (without the directory: 871 passed, 144 skipped by design; the `ben_reference` marker alone selects 151) |
| Numerical oracle suites | Included in the full backend run (NF-3B/3D/3E independent oracles, RMS golden vectors, PU math); 312 targeted re-runs after the fix passed |
| **Full browser, on `ae5dfd9`** | **1,882 passed, 9 failed, 9 skipped; 0 flaky; 0 retries** (1 h 02 min, 1 worker) |

The 3 xfails are the strict NF-3F (2) and NF-3G (1) oracles; they must flip when those slices land. The 410 skips equal main's.

### Browser baseline reconciliation

Accepted main baseline (`885bf8d` record): 1,812 passed / 7 failed / 8 skipped. The older NF branch alone had 167 failures (163 distinct titles) / 17 skipped; the integrated tree has 9 (the failures that were inherited from the pre-PU/WUI lineage clear once that lineage is combined). Not every one of the 167 was individually re-checked; the claim is the totals and the reconciliation table below.

| Failure now | Disposition |
|---|---|
| 6 CSV/Excel: `data-issues-estimate-fill` (2), `data-issues-panel` (2), `data-preparation-sticky-header`, `sampling-rate-format` | **Identical to the six documented baseline failures.** Unchanged |
| `waveform-legend-visibility.spec.js:9` Grouped and Custom | **Not an integration regression.** Run against a pristine `885bf8d` copy and the candidate, 6 runs each, the same two tests fail intermittently on both (baseline 5 of 6 runs, candidate 6 of 6; one run passed all 17 on the baseline). This is the documented non-reproducible legend-visibility timing qualification. The baseline record named a different test in the same file (`legend hide/show preserves physical samples…`, `:87`); that one passed here |
| `waveform-pane-drawer-clearance.spec.js:5` Separate | **One observation, not reproduced.** Failed once in the full run (the "before" chart widths read `[0,0]` before layout, then `[616,616]`: a measurement race in the test, not a product assertion). Passed in all 12 isolated runs and in 8 more full-run-order repeats (4 on each tree). Not present in the baseline record. It is reported as an unreproduced timing observation, not as proven flaky on the baseline |

Skips (9): the eight documented owner-recording skips (4 BEN5K, 4 waveform-measurement) plus the NF-2 screenshot-gallery spec, which is gated by design. Seven tracked evidence PNGs rewritten by the run were restored with `git checkout` and are not committed.

## 7. Feature-gate verification (closed)

- `Settings.nominal_frequency_manual_override_enabled = False` by default; a deployed build refuses `NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED` (`config.py`).
- `Settings.ben5k_experimental_enabled = False` by default.
- Frontend `WW_NF_CONSUMERS_MIGRATED = false` (`index.html`).
- No compose, workflow, script or Dockerfile sets either environment flag; the static gate tests pass in the final backend run.
- Both flags are opened only in the throw-away test backend defined in `browser-tests/playwright.config.js`.

## 8. Files changed

181 files vs `885bf8d` (+68,942 / −405): 74 backend test files, 53 backend app files, 46 project-memory documents, 2 diagnostics scripts, `frontend/index.html`, `playwright.config.js` and three browser specs. Against the frozen NF tip, 24 application and test files differ (the main-side changes brought in by the merge, plus the seam fix), before this record and the two status documents.

## 9. Project-memory updates

`CURRENT_STATE.md` and `HANDOFF.md` carry the integration status. `DECISIONS.md` is unchanged except for position. DEC-218's historical note that DEC-217 "is reserved on the NF branches" remains accurate history; DEC-217 is now present on this branch.

## 10. Remaining limitations

1. Candidate is local only: not pushed, merged to `main`, or deployed.
2. The `waveform-legend-visibility` Grouped/Custom timing flake and the one unreproduced drawer-clearance failure are carried as qualifications of the browser result; the browser result is **not** an unconditional pass.
3. NF gates stay closed; the Manual override and `WW_NF_CONSUMERS_MIGRATED` are not in effect for normal use.
4. Open NF limitations carry over unchanged: power channels keep the fixed 50 Hz (NF-3F); the mixed-recording first-member rule (NF-3G); the silent 50 Hz defaults (NF-3H); Auto Base evidence (C-17) belongs to the PU workstream (O-3); F-1 is untouched.

## 11. Recommended next step

Owner review and formal acceptance of `ae5dfd9`. The owner has already approved O-2, O-9 and a consolidated NF-3F/G/H cycle (2026-11-28); that work starts from a new worktree off the accepted SHA only after this acceptance. NF-3I (gate activation) remains separately authorised.

## 12. Governance compliance (DEC-218)

Documents consulted: AGENTS.md, CLAUDE.md, project-memory README, DEC-217/218/219, the NF-3A to NF-3E records, and the PU final-acceptance record. Established decisions preserved; no existing policy has changed; no decision was reopened. No mathematical kernel, RMS display, WUI or PU denominator code was changed. The one test-overlay change (section 4) is an additive documentation of an owner-accepted API field. No unresolved policy conflict arose. Scope deviation: none; NF-3F/G/H, NF-3I, push, merge, deploy and PROD were not touched.
