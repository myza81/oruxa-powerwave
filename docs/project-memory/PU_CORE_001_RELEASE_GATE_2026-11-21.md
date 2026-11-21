# PU-CORE-001 — Final Release-Gate Report for D5A Integration

**Date:** 2026-11-21  
**Baseline Branch:** `feature/vlt-ref-001-voltage-reference-safety` @ commit `c593a0b`  
**Verification Branch:** `chore/pu-core-001-verification`

---

## Executive Verdict

**D5A INTEGRATION READINESS: CONDITIONAL PASS** (no PU blocker; two owner actions remain)

Full integrated backend suite on `chore/pu-core-001-verification`: **13,397 tests — 12,968 passed, 7 failed, 422 skipped, 27 warnings** (JUnit XML, 858 s, no early termination). All 7 failures are stale frontend static-file tests that fail identically on the pre-work baseline `c593a0b`; none is a PU test. The 7 PU-related tests corrected in this work pass.

**Remaining owner actions (not PU defects):**
1. Authorise the integration of the verification branch into the feature branch (clean merge verified) — see "Integration recommendation".
2. Decide whether the 7 stale frontend tests are repaired by the PU-UI-001/Codex frontend track (they assert the pre-rename navigation and are outside PU scope).

**Correction notice:** an earlier revision of this report described the 7 failing tests as the previously corrected set and gave no totals. That was wrong. The corrected set (below) passes; the 7 failures listed under "Remaining failures" are a different, never-before-classified set.

---

## Task 1 — Full Regression Confirmation

### Targeted Verification (Complete) — 48/48 PASS

| Category | Count | Result |
|----------|-------|--------|
| Corrected baseline tests | 7 | ✅ ALL PASS |
| Independent math tests (C1–C10 contracts) | 33 | ✅ ALL PASS |
| F3 regression tests (group-aware Voltage ref-side) | 8 | ✅ ALL PASS |
| **Total targeted** | **48** | **✅ 48/48 PASS** |

**Corrected tests verified:**
- `test_per_unit_atomic_updates[body0]`: 275 kV (consistent with N275 COMTRADE evidence)
- `test_per_unit_atomic_updates[body1]`: 275 kV (consistent with N275 COMTRADE evidence)
- `test_a_base_that_is_not_applied_yet_plots_nothing` → `test_engineer_approved_base_on_suggested_group_plots_traces` (skip_status_gate active)
- `test_mg_modal_suggest_button_still_exists_for_compliance` → `test_pu_config_banner_exists_for_compliance_access` (Banner replaces MG modal)
- `test_mg_modal_suggest_function_still_exists_for_compliance` → `test_navigate_to_rd_for_pu_configuration_routes_to_recording_details_groups` (Function replaced)
- `test_full_main_nav_order_includes_calculator_after_compliance`: "Recordings" → "Recording Details"
- `test_per_unit_selection_still_only_calls_apply_unit_mode`: Boundary marker updated to "Waveform toolbar refinement"

### Full Backend Suite (Complete, integrated state)

| Metric | Count |
|--------|-------|
| Tests collected/run | 13,397 |
| Passed | 12,968 |
| Failed | 7 |
| Errors | 0 |
| Skipped | 422 |
| Warnings | 27 |

State under test: `chore/pu-core-001-verification` (contains F3 `c593a0b`, the 33 math tests, the 7 corrected tests). Browser-driven suites excluded (`test_browser_*`). The two guard tests in `test_pu_core_001_dispatch_registry_guard.py` were added after this run started and were run separately (2 passed).

**Baseline status of the 7 failures:** the four files containing them were run on the baseline worktree at `c593a0b` (before any PU-CORE-001 change): 7 failed / 317 passed — the identical 7. The verification branch changes no frontend file (`git diff c593a0b..HEAD -- frontend` is empty), so these cannot be regressions from this work.

### Remaining failures (all baseline, all frontend static-file tests, none PU)
1. `test_frontend_event_reconstruction.py::TestEventReconstructionNavigation::test_full_main_nav_order` — "Recordings" vs "Recording Details" rename
2. `test_frontend_event_reconstruction.py::TestEventReconstructionNavigation::test_every_existing_page_is_still_switched` — pageRecordings vs pageRecordingDetails
3. `test_frontend_event_reconstruction.py::TestPowerwaveIconAssets::test_owner_supplied_icons_are_never_also_duplicated_inline` — PAGE_RECORDING_DETAILS icon manifest
4. `test_frontend_event_reconstruction.py::TestPowerwaveIconAssets::test_no_new_inline_svg_blocks_for_migrated_controls` — Element not found
5. `test_frontend_playback.py::TestPlaybackCursorIsAnalysisOwned::test_every_page_change_hides_every_playback_overlay` — Playback reference in comments
6. `test_frontend_split_view_toolbar_cleanup.py::TestMainSidebarMenuUnaffected::test_main_nav_waveform_btn_still_present_and_wired` — Waveform nav wiring
7. `test_frontend_time_group_toolbar.py::TestGlobalDuplicatesRemoved::test_deferred_global_controls_are_still_present_and_untouched` — recordingsUploadBtn not found

Classification: stale tests asserting pre-PU-UI-001 navigation ("Recordings" vs "Recording Details", `pageRecordings`, `recordingsUploadBtn`, `PAGE_RECORDING_DETAILS` icon manifest, an inline-comment match in the playback test). Same cause as the 7 corrected tests, different files. They overlap with Codex's concurrent frontend track, so they were deliberately not edited here.

---

## Task 2 — Source Default Authority Disposition

### Analysis Complete

**Question 1: Whether active production workflows still populate Source Default**

- **Frontend:** Zero calls to `PUT /per-unit/sources/{source_id}` in `frontend/index.html`. No UI client exists (removed in PU-UI-001 Step B).
- **API:** Endpoint is functional but unreachable from production UI.
- **Conclusion:** Only reachable via direct API calls or test clients. Not an active production data path.

**Question 2: Which ungrouped recording channels can consume the fallback**

- By DEC-051: Grouped channels always use DEC-050; fallback is NEVER used by grouped channels.
- Ungrouped channels use SD fallback only if the channel is NOT in a MeasurementGroup AND an SD profile exists for the source.
- **In a workspace where all V/I channels are assigned to MeasurementGroups, SD fallback is a dead path.**

**Question 3: Which calculated-channel operations depend on it**

| Operation | SD dependency |
|-----------|---------------|
| Unary ops on ungrouped source channel | Inherits ungrouped source channel's SD base |
| `OP_LINE_TO_LINE_VOLTAGE` | Inherits input group's base directly — NO SD dependency |
| Cross-group add/subtract where inputs share MG | Inherits if unanimous — NO SD dependency |
| Cross-group add/subtract spanning different MGs | Falls back to SD or `base_required` |
| Calculated Current with `mode="manual"` | Uses manually configured base (`PUT /{id}/per-unit-config`) — NO SD dependency |

**Question 4: Whether any hidden value can still influence PU calculations**

- No. The only influence point is through SD inheritance for ungrouped channels and cross-group fallback paths.
- All other PU behavior is deterministic and locked by DEC-049/DEC-050/DEC-051 rules.

**Question 5: Numerical consequences of disabling the fallback**

| Scenario | With SD fallback | After SD retirement |
|----------|-----------------|---------------------|
| Ungrouped V/I recording channel with SD set | `configured` — PU active | `base_required` — PU unavailable; waveform reverts to engineering units |
| Cross-group calculated Current via SD inheritance | `configured` via SD | `base_required` unless manual-base API used |
| All grouped recording channels | Unaffected | No change |
| `OP_LINE_TO_LINE_VOLTAGE` | Unaffected | No change |
| Generic cross-group Voltage | Already `base_required` | No change |

### Recommended Disposition

**Phase A (Operational, no code change):** Ensure all relevant V/I recording channels in active workspaces are assigned to MeasurementGroups. After this, SD fallback is a dead path operationally.

**Phase B (Documentation):** Document that `PUT /calculated-channels/{id}/per-unit-config` is the intended base-configuration path for cross-group calculated Current (replaces SD inheritance).

**Phase C (Backend, requires owner approval):** When owner confirms no active SD writes:
- Deprecate then remove `PUT /per-unit/sources/{source_id}` endpoint
- Remove `PerUnitRegistry.set()` recording-channel write path
- Remove dead code: `set_manual_assignment_for_calculated_channel()`
- Remove DEC-051 fallback branch from `resolve_per_unit()` (becomes dead code)

---

## Task 3 — D5A Integration Baseline

**Document:** See [PU_D5A_BASELINE_2026-11-21.md](PU_D5A_BASELINE_2026-11-21.md) for:

1. ✅ Exact commit and branch baseline
2. ✅ Approved PU formulas and numerical invariants
3. ✅ Measurement Group authority and eligibility rules
4. ✅ Reference-side handling and provenance
5. ✅ Calculated-channel base behavior
6. ✅ Known physical-calibration limitations
7. ✅ Interfaces that D5A may consume
8. ✅ PU functionality that D5A must not alter

---

## Final Regression Summary

Passed 12,968 · Failed 7 (all baseline, non-PU) · Skipped 422 · Warnings 27 · Errors 0 (of 13,397).

**New failures introduced by PU-CORE-001:** none. The F3 regression tests (8), math tests (33), corrected tests (7) and dispatch guard (2) all pass.

---

## Production call-path audit of `_resolve_effective_per_unit()`

The group registries are optional parameters (default `None`); omitting any silently resolves a grouped channel through DEC-049. Every production path was traced:

| Consumer | Registries supplied? |
|----------|----------------------|
| `waveform_service.extract_waveform_range` / `extract_cursor_values` / `resolve_annotation_anchor` / `resolve_peak_value` (4 internal call sites) | pass-through of the caller's registries |
| `sources.py` — the 4 waveform-family endpoints (range, cursor-values, annotation-anchor, peak-values) | all four supplied at every site |
| `compliance_series._raw` (`resolve()`) | all four supplied |
| `per_unit_provenance_service`, `per_unit_coverage_service` | required (non-optional) parameters; try group-aware first |
| Calculated channels (`calculated_channel_service`, `calculated_current_per_unit`) | separate dispatcher; grouped leaves resolve via the group before any Source Default read |

No production path omits the registries. Existing HTTP tests (`test_group_aware_per_unit_endpoints.py::TestDec051PrecedenceAcrossMigratedEndpoints`) prove, across all four endpoints, that a grouped-but-unresolved channel stays `base_required` even when a Source Default would convert it. What no test pinned was the structural risk of a future call site omitting the optional arguments, so `tests/test_pu_core_001_dispatch_registry_guard.py` was added: an AST guard that fails if any production call to the guarded functions drops one of the four keywords (with a self-test proving it detects an omission).

The only remaining production Source Default read for a *calculated* result is `calculated_current_per_unit.py:167` (the `legacy_manual` branch). It is reachable only for state written by `set_manual_assignment_for_calculated_channel()`, which has no callers (H2 dead code), so it is unreachable in practice.

---

## F3 Integration Confirmation

✅ **F3 fix integrated and verified**

Commit: `c593a0b` — fix(pu-ssot-001): pass voltage_group_config to apply_source_reference for group-aware calculated Voltage channels

Regression tests: 8/8 pass (`test_pu_ssot_001_calc_voltage_ref_side.py`)

Change: `apply_source_reference()` for group-aware calculated Voltage channels now reads `base_reference_side` from `VoltageBaseConfiguration` (DEC-050) instead of from the SD profile (DEC-049).

Impact: Affects only `reference_compatibility` metadata and `base_reference_side` provenance; does not change `base_amount` or `base_unit`.

---

## Outstanding Owner Decisions

| Item | Status | Decision needed |
|------|--------|-----------------|
| H1 — 7 obsolete PU tests | Done (corrected, passing, coverage preserved) | None |
| H2 — Dead code `set_manual_assignment_for_calculated_channel()` | Deferred per owner | None |
| H3 — Ephemeral Source Default | No persistence, per owner | None |
| H4 — RD-0B conflict gate | Preserved unchanged | None |
| 7 stale frontend tests (non-PU, baseline) | Not edited (Codex frontend overlap) | Who repairs them, and when |
| Integration of verification branch into feature branch | Clean merge verified (dry run) | Authorise the merge |
| Phase C — retire recording-channel fallback | NOT recommended before D5A (see compatibility exception) | Approve a later, separate change |

## Source Default: temporary compatibility exception

**Recommendation: a documented temporary exception, not a pre-D5A Phase C correction.**

- *Populated how:* only by a direct `PUT /per-unit/sources/{id}` API call. No frontend caller exists and none may be added; there is no persistence (registry is in memory), so nothing survives a restart.
- *Consumed by:* only recording channels that belong to **no** Measurement Group (and calculated results whose leaves are ungrouped). A grouped channel can never reach it (DEC-051, enforced by the dispatcher, HTTP tests and the new guard).
- *D5A data-flow impact:* none. D5A consumes grouped-channel PU via Measurement Groups; the exception is a read-only compatibility branch for ungrouped channels and is not on that path. Disabling it would turn ungrouped channels with a configured SD from `configured` to `base_required` (engineering units only); it changes no grouped-channel number.
- *Limits:* no UI, no persistence, no new writers, no extension to grouped channels, no new consumers.
- *Retirement requirements (separate owner-approved change):* (1) confirm no external API client calls the PUT; (2) show ungrouped-channel coverage via Recording Details/Measurement Groups is acceptable to users; (3) handle the calculated-current `legacy_manual` branch together with H2 dead code; (4) remove the PUT, the fallback branch and `resolve_per_unit` SD dependence together, with updated tests; (5) document the ungrouped-channel numerical change (configured → `base_required`).

## Integration recommendation

Merge `chore/pu-core-001-verification` into `feature/vlt-ref-001-voltage-reference-safety` (owner-authorised, no push). A `git merge-tree` dry run is clean. It contains `c593a0b` plus 33 math tests, 7 corrected tests, the dispatch guard and the three docs, and changes no frontend file, so Codex's frontend work is untouched. The feature branch's only extra commit is `3308ccd` (a docs-only copy whose three files are byte-identical to the verification branch's), so use a normal merge (not rebase) to avoid rewriting it. Re-run the PU test files after the merge before treating it as the D5A baseline.

---

## Baseline Commits for D5A

| Purpose | Branch | Commit | Description |
|---------|--------|--------|-------------|
| Feature | `feature/vlt-ref-001-voltage-reference-safety` | `c593a0b` | F3 fix: group-aware calculated Voltage ref-side |
| Math tests | `chore/pu-core-001-verification` | `6e8f5b2` | 33 independent mathematical verification tests |
| Report | `chore/pu-core-001-verification` | `46591ea` | PU-CORE-001 report (Phase 1–8) |
| Test corrections | `chore/pu-core-001-verification` | `4eca68b` | 7 PU tests corrected |
| Release-gate docs | `chore/pu-core-001-verification` | `e36f097` | Release gate + D5A baseline |
| Dispatch guard | `chore/pu-core-001-verification` | `491f736` | AST guard for registry omission |
| Corrected report | `chore/pu-core-001-verification` | final commit of this branch (see `git log -1`) | Suite totals, call-path audit, exception, integration |

Single integrated baseline = the tip of `chore/pu-core-001-verification`; it contains everything above. The full-suite run covered the tree up to `e36f097` (the guard was run separately).

---

## Final Verdict

**D5A READINESS: CONDITIONAL PASS**

Evidence: full integrated suite 12,968 passed / 7 failed / 422 skipped / 27 warnings; the 7 failures are baseline, non-PU frontend tests; F3, 33 math tests, 7 corrected tests and the dispatch guard pass together on one branch; no production call path can let a grouped channel fall back to DEC-049.

Actual blockers for D5A: **none in the PU backend.** Owner actions: authorise the branch integration; decide ownership of the 7 stale frontend tests; later, approve Phase C as a separate change.

---

## Do Not

- Push, merge to main, or deploy
- Change CT/VT mathematics or physical calibration
- Alter DEC-051 coexistence or DEC-049/DEC-050 formulas without approval
- Weaken RD-0B conflict gate or authority eligibility rules
- Restore Source Default UI
- Begin D5A without owner approval

---

**Next steps:** Await owner review and decisions on Phase C and outstanding items H1–H4.
