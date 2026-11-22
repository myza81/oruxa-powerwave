# D5A-UI-002 — Group Details redesign and Measurement-Group-level measurement side

**Branch:** `feature/d5a-ui-002-group-details-group-side` (from `feature/ui-rec-001-recording-info-redesign`, itself from the DEV-UAT baseline
`a1e8d68`). **Not pushed, merged or deployed.** PU, CT/VT, Overcurrent, Impedance and Distance numerics and every calculation consumer are untouched.
Authority: [DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model) Amendment 4.
This **supersedes the per-(recording, bay) Level 2 design** of D5A-2B2A/2B2B ([D5A_2B2A](D5A_2B2A_MEASUREMENT_SIDE_CONFIGURATION_2026-11-22.md),
[D5A_2B2B](D5A_2B2B_RECORDING_DETAILS_MEASUREMENT_SIDE_UI_2026-11-22.md)); those documents describe the model that existed until this slice.

## 1. Authority model

| Level | Owner | Stored key | Meaning |
|---|---|---|---|
| 1 | the recording | `(workspace, source)` | engineer correction of the recording-wide side (unchanged) |
| 2 | **one Measurement Group** (a Voltage *or* a Current group of one recording) | `(workspace, source, measurement_group_id)` | engineer override for **all phases of that group** |

Per channel, first match wins (the channel's own group is found through the Measurement Group registry; nothing is parsed from names):

1. group override — `engineer_group_override`
2. recording correction — `engineer_recording_correction`
3. the channel's own original P/S declaration — `recording_channel_declared`
4. recording default inferred from the sibling channels — `recording_default` (display only, **not strict-usable**)
5. `unresolved`

* **Voltage and Current are independent.** A bay's Voltage group and Current group are two groups, so Primary voltage with Secondary current (and the other
  three combinations) coexist and are never a conflict. Two groups of one kind in one bay are independent too.
* **Engineering Context plays no part.** No membership/status gate (the Confirm-bay step is no longer a prerequisite for a side), no per-bay value, no
  per-bay inheritance. Context membership, phases and Analysis input resolution are untouched (tested).
* **Inheritance.** A group without an override follows the recording correction / its channels' own declarations. Changing Level 1 moves every following group
  and none that is pinned; nothing is stored per group for the inherited value (one registry entry per engineer decision, tested).
* **No Reset.** Selecting a side clears the override only when, *without* the override, every channel of the group already resolves to that side on
  **reliable** evidence (its own declaration or an engineer recording correction). If any channel would only be inferred, unresolved, mixed, or would re-expose a
  contradicted declaration, the selection is kept — an engineer's confirmation or correction is never silently dropped.
* **Evidence is never rewritten.** `declared_side`, the original per-channel declarations, the engineer's note/time and the overridden-declaration list stay
  available; `GROUP_OVERRIDE_OVERRIDES_DECLARATION` / `ENGINEER_CORRECTION_OVERRIDES_DECLARATION` warnings are shown and never block.
* **Mixed declarations inside one group** are a `conflict` (`GROUP_MIXED_SIDES`): nothing is guessed and no side is highlighted until the engineer chooses.
* **Lifecycle.** An override is released with its group (group delete), recording (source delete) or workspace; re-uploading starts clean; changing a group's
  channel membership keeps the override with the group (a channel that moves takes the new group's setting). The registry stays in memory only.
* **Channels in no group** follow their recording (they have no Level 2 setting).
* **Consumers** (`resolve_effective_measurement_side`, `resolve_consumed_side`) keep their contracts; calculated channels remain deferred to D5A-2B2C.

## 2. API (replaces the bay endpoints; they were never used by a calculation consumer)

* `GET /api/v1/workspaces/{ws}/measurement-side` → `{recordings[], groups[]}` (the former `bays[]` is gone; `group_ids` replaces `bay_ids`).
* `GET|PUT /api/v1/workspaces/{ws}/sources/{source_id}/measurement-groups/{measurement_group_id}/measurement-side` (`PUT {side: primary|secondary}`; 404
  `measurement_group_not_found` when the group is not in that recording; 409 `group_has_no_measurement_channels`).
* Removed: `GET /engineering-contexts/{id}/measurement-side` and `GET|PUT /sources/{id}/engineering-contexts/{id}/measurement-side`.
* Channel responses carry `measurement_group_id` / `group_override_side` instead of `engineering_context_id` / `bay_membership` / `bay_override_side`.
* `/sources/{id}/measurement-side` and `/measurement-side/channel` keep their shapes.

**Compatibility:** the bay endpoints were present on the DEV UAT build `a1e8d68` only. All side configuration is in-memory and ephemeral, so no data
migration exists or is needed; any bay override created during that UAT disappears with the next deploy. The group-ownership diagnostics
(`GROUP_SPANS_BAYS*`, `conversion_authority`) are retired from the side API because the group is now the single owner of both the side and the CT/VT ratio, so
they can no longer disagree. The D5A-2B2C safeguard still stands unchanged: matching sides alone do not establish shared CT/VT conversion authority; the
consumer must verify the CT/VT authority of the actual consumed channel and its Measurement Group (shared busbar VTs remain supported; ambiguous ownership must
not produce an invented conversion).

## 3. Group Details UI

* One selected Measurement Group at a time. Voltage group: heading, channels, **Measurement Value**, **Voltage Base Configuration**, **Voltage Transformer
  (VT)**. Current group: heading, channels, **Measurement Value**, **Equipment Rating**, **Current Transformer (CT)**. Never both.
* Measurement Value: "Primary or secondary values for voltage/current.", one Primary | Secondary pill for all phases of the group (the Level 1 pill component).
  Nothing highlighted while the group is unresolved or in conflict; compact messages only for inferred / unresolved / conflict / manual-vs-declared.
  No Reset, no Confirm-bay form, no per-phase control.
* The existing sections keep their markup, ids, editors and behaviour; they are turned into pale-blue cards with icon tiles and aligned Edit buttons by
  `wwRdDecorateGroupCard()` (presentation only) and the `D5A-UI-002-CSS` block. The Measurement Groups list gets pill filters and a rounded selection row.
* Frontend state: the existing latest-wins request chain and sequence guards; optimistic choices are keyed `source|group`; a save or read for another
  recording or workspace is discarded; a late answer re-renders only the group on screen. The Recording Info tab is unchanged.

## 4. Files

Backend: `app/domain/measurement_side_config.py`, `app/services/measurement_side_{registry,service}.py`, `app/schemas/measurement_side.py`,
`app/api/v1/{measurement_side,measurement_groups,sources,engineering_contexts}.py`, `app/services/errors.py`.
Frontend: `frontend/index.html` (the `D5A-2B2B` block, the `D5A-UI-002-CSS` block, three one-line hooks).
Tests: `backend/tests/test_d5a_ui_002_group_measurement_side.py` (replaces the bay oracle suite), `backend/tests/test_frontend_d5a_2b2b_measurement_side.py`,
`browser-tests/d5a_ui_002_group_details.spec.js` (replaces `d5a_2b2b_measurement_side.spec.js`).

## 5. Verification

See the owner report and the commit messages for totals. Mutation checks confirmed the new tests fail when the group override is ignored, shared across
groups, or when an inferred side is allowed to clear an override, and when the page highlights an unresolved group.

## 6. Limitations before D5A-2B2C

* Calculated-channel side/lineage questions are unchanged (see D5A_2B2B §7).
* Recording Details no longer offers a Confirm-bay review; confirming an Engineering Context is still available through its own endpoint/workflow.
* The Per-unit Configuration card on Recording Info appears after the next re-render (pre-existing: groups load after the first draw).
