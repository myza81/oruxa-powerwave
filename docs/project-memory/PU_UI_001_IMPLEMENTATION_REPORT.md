# PU-UI-001 Implementation Report — Final Cleanup: Remove Legacy Source Default and MG Configuration Interfaces

**Date:** 2026-11-21
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Status:** Implementation and regression testing complete. NOT pushed. NOT merged. Awaiting owner UAT.

---

## 1. Implementation summary

PU-UI-001 removes the two legacy Per-Unit configuration overlays from the
frontend — the Source Default modal (`#perUnitProfilesOverlay`) and the
Measurement Group modal/drawer (`#measurementGroupsOverlay` / `#wwMgDrawer`) —
and redirects all configuration entry points to Recording Details.

**Step A — Inventory and parity analysis:**
Confirmed that Recording Details already provides complete parity with both
removed surfaces: group creation/edit/save, voltage-config, current-config,
DEC-UA-002 auto-promotion, and the PU details popover. No gap requiring a
new RD feature was found before Steps B/C.

**Step B — Remove Source Default frontend interface (commit `be1e7e0`):**
- Removed `#perUnitProfilesOverlay` modal markup (~280 lines of HTML/CSS).
- Removed `#ww-rd-pu-source-default-link` from Recording Info.
- Removed all SD modal JS functions:
  `wwOpenPerUnitProfilesModal`, `wwClosePerUnitProfilesModal`,
  `wwPerUnitConfigToEditorState`, `wwPerUnitEditorResolvedCurrentBaseText`,
  `wwPerUnitDerivedCurrentBaseKa`, `wwRenderVoltageReferenceBlock`,
  `wwRenderPerUnitProfileEditor`, `wwRenderPerUnitSourceSelect`,
  `wwRenderPerUnitSourceStatusLine`, `wwApplyPerUnitProfileEditor`,
  `wwDeletePerUnitProfileEditor`, `wwWirePerUnitProfileFieldsEvents`,
  `wwFetchPerUnitSourceConfigs`, `wwPerUnitEffectiveVoltageBaseLines`.
- Removed `perUnitSourceConfigs` from `ww` state.
- Removed `/per-unit/sources` and `/per-unit/sources/` path strings.
- Removed SD-modal constants: `PER_UNIT_SQRT_3`, `LINE_TO_GROUND`, `LINE_TO_LINE`.
- Removed Hub overlay (`#perUnitSettingsOverlay`) and its toolbar button
  (`#wwOpenPerUnitSettingsBtn`) and coverage section (`#wwPuCoverageBody`).
- Retained: ENG/PU toggle buttons, `wwRenderChannelPerUnitResolution` popover,
  `wwNavigateToRdForPuConfiguration`, `ww.unitMode`, the PU config banner.

**Step C — Remove MG overlay/drawer, redirect Compliance to RD (commit `4161a63`):**
- Removed `#measurementGroupsOverlay` modal markup.
- Removed `#wwMgDrawer` and `#wwMgDrawerBackdrop` drawer markup.
- Removed all MG modal/drawer JS functions:
  `wwOpenMeasurementGroupsModal`, `wwCloseMeasurementGroupsModal`,
  `wwOpenMgDrawer`, `wwCloseMgDrawer`, `wwSaveMgDrawer`,
  `wwRenderMeasurementGroupsBody`, `wwLoadAndRenderMeasurementGroupsBody`,
  `wwMeasurementGroupsSourceSelectChange`, `wwSuggestMeasurementGroups`,
  `wwRenderMgDrawerVoltage`, `wwRenderMgDrawerCurrent`, `wwMgGroupToEditState`.
- Removed MG modal state variables:
  `wwMgSourcesList`, `wwMgSelectedSourceId`, `wwMgEditState`.
- Removed `wwMgLinkableVoltageGroups` helper.
- Removed Hub menu entry points and toolbar buttons:
  `#wwUnitModeMenu`, `#wwManageMeasurementGroupsBtn`, `#wwManagePerUnitBasesBtn`.
- Added `wwNavigateToRdForGroup(sourceId, groupId)` navigation helper.
- Rewired Compliance `wwComplianceOpenConfigureBase` and
  `wwComplianceOpenManageGroups` to call `wwNavigateToRdForGroup(...)` instead
  of opening the now-removed modals.
- Retained: `ww.measurementGroups` Map (used by RD), `/measurement-groups` API
  paths, `.ww-mg-badge--recommended`/`--fallback` CSS (reused by RD group rows).

**Step D — Backend DEC-049 authority assessment:**
No code changes needed. Assessment findings:

- Single dispatch point: `_resolve_effective_per_unit()` in
  `backend/app/services/waveform_service.py` (line 143).
- DEC-051 fallback logic confirmed: grouped channels → group-aware DEC-050
  resolution; ungrouped channels → `resolve_per_unit()` with DEC-049
  `PerUnitBaseProfile`; non-V/I engineering types → `not_applicable`.
- `PerUnitRegistry` is in-memory and ephemeral (workspace-scoped, no
  persistent storage) — removing the frontend editor does not risk data loss.
- Backend DEC-049 path continues for ungrouped channels; no numerical behavior
  was changed.

**Step E — Regression test updates:**
Seven `test_frontend_*.py` files updated to reflect the post-removal state;
details in §3 below.

**CSS updates (commit `ed6692a`):**
- `.ww-rd-upload-btn`: `font-size: 0.8rem`, `padding: 10px 12px`,
  `border-radius: 15px`, `background: #d3e3ff`.
- `.ww-rd-analyze-btn`: `font-size: 0.8rem`, `padding: 10px 14px`,
  `background: #1097ab`.

---

## 2. Owner decisions honored

| Decision | Description | Implementation |
|----------|-------------|----------------|
| DEC-049  | Source-bound PU base profiles, ephemeral, workspace-scoped | Backend path preserved for ungrouped channels (DEC-051); frontend editor removed |
| DEC-050  | Measurement Group-aware PU resolution (authoritative for grouped channels) | Group-aware resolver untouched; RD is the sole configuration surface |
| DEC-051  | DEC-049/DEC-050 coexistence — group membership decides which resolver applies | `_resolve_effective_per_unit()` logic unchanged |
| DEC-214  | Frontend must be engineer-task-first, not backend-schema-first | Hub and modal-first flows retired; RD exposes the same configuration through engineer-oriented workflows |
| DEC-UA-002 | Manual correction auto-promotes groups (skip_status_gate for engineer-approved authority) | Preserved in RD; not affected by SD/MG modal removal |

---

## 3. Files changed

**Production code (1 file):**

- `frontend/index.html` (Steps B, C, CSS updates)
  - Removed: SD modal overlay, Hub overlay, MG modal overlay, MG drawer
  - Removed: all SD and MG JS functions listed in §1
  - Removed: SD/MG state variables and toolbar buttons
  - Added: `wwNavigateToRdForGroup(sourceId, groupId)` navigation helper
  - Rewired: Compliance open-configure and manage-groups to use
    `wwNavigateToRdForGroup`
  - Updated: `.ww-rd-upload-btn` and `.ww-rd-analyze-btn` CSS rules

**Test code (7 files):**

- `backend/tests/test_frontend_per_unit_source_default_voltage_reference.py`
  Replaced 3 SD-modal-arithmetic test classes with removal-contract assertions
  (overlay gone, link gone, all SD functions gone).

- `backend/tests/test_frontend_per_unit_source_default_voltage_traceability.py`
  Replaced SD modal editor-preview helper tests with removal assertions;
  retained popover presentation tests.

- `backend/tests/test_frontend_per_unit_mode.py`
  Removed 14 SD-modal-specific tests; added consolidated SD removal contract;
  updated state, `wwApplyUnitMode`, reset, toolbar, and click-handler boundary
  assertions.

- `backend/tests/test_frontend_per_unit_settings.py`
  Updated child-modal, precedence, stale-hint, and API-path tests; fixed
  click-handler boundary to use direct `addEventListener` anchor.

- `backend/tests/test_frontend_per_unit_coverage.py`
  Updated child-modal tests to assert both SD and MG modals removed; retained
  badge CSS and `/measurement-groups` path assertions.

- `backend/tests/test_frontend_measurement_groups.py`
  Extensive rewrite — modal/drawer markup, open/close/save/render functions,
  state variables all asserted removed; workspace reset, cross-source isolation,
  and suggest-function tests updated accordingly.

- `backend/tests/test_frontend_compliance.py`
  Fixed nav label (`Recording Details`); updated configure-base and
  manage-groups tests to assert RD navigation instead of modal open; fixed
  `async` function-signature check and modal-close assertions.

---

## 4. Test results

**Step C regression fix (commit `1c92716`):**
Full backend suite run discovered that `wwSyncOffsetToMsDisplay` and
`wwSyncMsToOffsetSeconds` were accidentally removed in Step C: they were
defined inside the MG modal section even though an inline comment marked
them as shared utilities. Restored immediately before the Event Reconstruction
formatting section where they are called.

**Targeted regression suite (Steps B, C, E + fix):**

| File | Tests | Result |
|------|-------|--------|
| test_frontend_compliance.py | 27 | 27 pass |
| test_frontend_measurement_groups.py | 29 | 29 pass |
| test_frontend_per_unit_coverage.py | 11 | 11 pass |
| test_frontend_per_unit_mode.py | 15 | 15 pass |
| test_frontend_per_unit_settings.py | 29 | 29 pass |
| test_frontend_per_unit_source_default_voltage_reference.py | 36 | 36 pass |
| test_frontend_per_unit_source_default_voltage_traceability.py | 39 | 39 pass |
| test_frontend_synchronization.py | (subset) | pass |
| test_frontend_time_group_sync.py | (subset) | pass |
| **Total (9 files)** | **204** | **204 pass** |

**Pre-existing failures in full suite (not caused by this work):**
- `test_frontend_time_group_toolbar.py::TestGlobalDuplicatesRemoved::test_deferred_global_controls_are_still_present_and_untouched`:
  checks for `id="recordingsUploadBtn"` which was absent before Step B.
- `test_per_unit_atomic_updates.py::test_voltage_valid_save_and_omitted_fields[body0/body1]`:
  backend numerical test expecting waveform values in PU form; unrelated to
  frontend changes; test file unchanged since before Step B; likely related to
  the BEN wide-scaling investigation (`BEN_WIDE_SCALING_ROOT_CAUSE_2026-11-16.md`).

Browser tests: not run as part of Steps B–E (no frontend logic was changed,
only markup/function removal and navigation wiring). Owner UAT required.

---

## 5. Architecture note

Recording Details is now the **single configuration entry point** for all
Per-Unit work:
- Measurement Group creation, editing and saving.
- Voltage base and current base configuration.
- DEC-UA-002 manual-correction auto-promotion.
- PU details popover access.

The backend DEC-049/DEC-050/DEC-051 resolution chain is unchanged. The
`PerUnitRegistry` continues to hold in-memory source-wide base profiles for
ungrouped channels. No persistent storage is affected by the frontend removal.

---

## 6. Items NOT implemented (scope guardrails confirmed)

The following are explicitly not included in this work:

- D5A CT/VT integration (explicitly deferred — owner instruction).
- Backend DEC-049 numerical migration (requires explicit authorization).
- Any change to `_resolve_effective_per_unit()` logic or DEC-051 fallback.
- Any change to `PerUnitRegistry` backend storage or API endpoints.
- Any change to Recording Details' own group-edit or save logic.
- Any modification to Compliance calculation logic.
- Push, merge, or deploy.

---

## 7. Owner decisions required

None outstanding. All implementation decisions follow directly from DEC-049/050/
051 and the PU-UI-001 specification. Navigation wiring (`wwNavigateToRdForGroup`)
was the minimum viable replacement for the removed modal entry points.

**Outstanding for owner UAT:**
- Verify that Recording Details correctly replaces the SD modal and MG modal/
  drawer for all PU configuration workflows under real recording data.
- Verify Compliance "Configure Base" and "Manage Groups" buttons navigate
  correctly to RD and that RD returns to Compliance cleanly.
- Confirm `.ww-rd-upload-btn` and `.ww-rd-analyze-btn` button styling is
  acceptable.

---

## 8. Governance compliance

- Not pushed. Not merged. Not deployed.
- D5A CT/VT integration: not started.
- Numerical backend migration: not started.
- Historical Source Default data: preserved (PerUnitRegistry is ephemeral —
  no persistent data existed to protect).
- All prior DEC-213, PULU, and Stage 3B-2B commits preserved exactly.
- BEN decoding, PU mathematics, and waveform numerical operations: not modified.
