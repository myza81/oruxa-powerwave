# D5A-2B2B — Recording Details: measurement side (frontend and owner-review refinements)

> **Superseded in part (2026-11-22):** Level 2 is now per Measurement Group, not per bay — see [D5A_UI_002_GROUP_DETAILS_GROUP_LEVEL_SIDE_2026-11-22.md](D5A_UI_002_GROUP_DETAILS_GROUP_LEVEL_SIDE_2026-11-22.md) and DEC-216 Amendment 4. The bay-level API, bay overlay, Confirm-bay review and group-spans-bays diagnostics described below no longer exist.

**Branch:** `feature/d5a-2b2b-recording-details-side-ui` (stacked on `feature/d5a-2b2a-measurement-side-config`, from the accepted D5A UAT baseline
`a2b55eb`). **Not pushed, merged or deployed.** PU, Overcurrent, Impedance and Distance numerical behaviour and their existing input controls are untouched.
Authority and API: [D5A_2B2A_MEASUREMENT_SIDE_CONFIGURATION_2026-11-22.md](D5A_2B2A_MEASUREMENT_SIDE_CONFIGURATION_2026-11-22.md),
[DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model) (Amendments 1-3).

## 1. What the engineer sees

| Where | Control | Behaviour |
|---|---|---|
| **Recording Info → "Measurement side"** (Level 1) | One Primary / Secondary selector for the recording | Shows the side the recording declares ("From recording"). Choosing the other side is an engineer correction ("Set by engineer"). Choosing the side the recording declares again returns to it — there is **no Reset**. |
| **Group Details → "Bay measurement side"** (Level 2) | One Primary / Secondary selector **per bay of the selected group, within the selected recording** | A bay follows the recording ("Follows the recording") until the engineer picks a side ("Set manually"); a manual choice survives later Recording changes; choosing the side the bay inherits clears it. A voltage group and a current group of the same bay show the **same single setting** — there are no separate Voltage/Current group settings, and never per R/Y/B phase. A group in no bay says "not part of a bay, so it follows the recording" and offers no control. |
| **Confirm bay…** (in the bay row) | Explicit review, then **Confirm bay** | A suggested / needs-review bay cannot take a manual side (B2A-3). **Confirm bay…** opens a review listing the bay's channels, their phases and where each phase came from ("from channel name", "from recording metadata", "set by engineer", "not determined"; channels of another recording are marked); a `needs_review` bay is flagged "Automatic detection flagged this bay for review". It states that confirming only says the channels belong to the bay and changes no channel or phase. Cancel changes nothing. Confirm sends the existing Engineering Context `PATCH status=confirmed` only. Recording-level selection and normal inheritance never need it. |

Provenance is one discreet line per row. Contradictory or unresolved evidence is stated plainly and nothing is pre-selected: mixed declarations, no declaration, a partially declared
(inferred) recording, a voltage/current split ("Recorded: voltage primary, current secondary." — legitimate), a bay whose channels disagree within a quantity, and — whenever a correction or
bay choice overrides declarations — an amber note ("The recording declares Primary on 5 channels. The side set here is used; the original declarations are kept.", full channel list on hover).
A group whose channels sit in several bays is disclosed (§4).

## 2. Frontend architecture (no second authority)

`frontend/index.html`: one self-contained block (`D5A-2B2B-BLOCK-START/END`), CSS after `.ww-rd-section-divider`, and a few one-line hooks (`wwRdBuildRecordingInfoHtml`,
`wwRdBuildDetailsHtml`, `refreshAllSourceViews`, `wwRdOnPageEntered`, `wwRdSelectSource`). It renders `GET …/measurement-side` and sends the engineer's choice; it never reads a P/S marker,
channel name or CT/VT ratio and has no side model, no browser storage and no per-phase control. Latest wins: selections are sent one at a time in order, an older read can never replace a newer view,
every response is checked against the workspace and recording on screen, and the view is invalidated on source-set change, page entry and recording selection. Text uses the words "voltage"/"current"
(no electrical symbols). Waveform Analysis code is untouched.

## 3. Backend changes made in this slice (all within DEC-216)

1. **B2A-1..5** (Amendment 1): V/I on different sides is resolved (info), `inferred` / `strict_usable`, `overridden_declarations`, Level 1 `voltage_current_differ`.
2. **Per-recording Level 2 scope (owner safety refinement).** One Engineering Context may hold channels of several recordings on different sides, so a bay setting now belongs to the bay
   *within one recording*: key `(workspace, context, source)`. A Level 2 change for recording A never reinterprets recording B; clear-on-equal compares with *that* recording's own Level 1; each Level 1
   reaches only its own non-overridden associations; nothing is inherited across recordings; the context endpoint lists one association per recording (`BAY_RECORDINGS_DISAGREE`, info, when they differ).
   The API is `GET/PUT /sources/{id}/engineering-contexts/{id}/measurement-side` (the unreleased context-level PUT was replaced). Overrides are released with the recording, the bay, or the membership that held them.
3. **CT/VT group ownership (focused diagnostics, no numerical change).** `GroupOwnership` classifies each Voltage/Current Measurement Group: `no_bay`, `single_bay`, `spans_bays` (several bays share one side:
   warning `GROUP_SPANS_BAYS` — a busbar VT legitimately serves several feeders, its ratio is the group's own) or `spans_bays_ambiguous` (the bays' sides differ or one is unresolved: conflict
   `GROUP_SPANS_BAYS_AMBIGUOUS`). `resolve_consumed_side()` then reports `conversion_authority = "ambiguous"` and `strict_usable = false` for a consumed channel of an ambiguous group, so a future consumer
   **blocks a side conversion through that group's ratio** instead of borrowing it; the side itself is still reported. No ratio is read, changed or borrowed, and no CT/VT formula was touched.
4. **Confirm bay is status-only (verified):** a test shows `PATCH status=confirmed` leaves members, phases, phase evidence and the Analysis input resolution identical; Analysis lists the same bay and re-reads contexts on every visit (only its
   status badge changes), so no availability or membership change results. Analysis never gated a bay on its status.

## 4. Groups spanning bays — what each consumer must do

| Group ownership | Side | Conversion through the group's ratio |
|---|---|---|
| `no_bay`, `single_bay` | the channel's own effective side | allowed (existing CT/VT authority rules) |
| `spans_bays` (all on one side) | that side | allowed; the ratio is the group's own; a warning is shown |
| `spans_bays_ambiguous` | still reported per channel | **must be blocked** (`conversion_authority = ambiguous`); resolve by confirming one side for the affected bays or splitting the group |

## 4a. Owner acceptance and D5A-2B2C safeguard (2026-11-22)

D5A-2B2B was approved for DEV UAT. A group spanning bays on one shared side stays warning-only. **Safeguard for D5A-2B2C:** matching measurement sides alone do not establish valid shared CT/VT conversion authority (two Primary-referenced bays may have different CT ratios). The consumer integration must verify the CT/VT authority of the *actual consumed channel* and its Measurement Group. Shared busbar VT arrangements remain supported; genuinely ambiguous transformer ownership must not produce an invented conversion. No production-code change is required for this in D5A-2B2B.

## 5. Verification

- **Full backend regression** (final tree): 13,490 passed / 405 skipped / 0 failed / 0 errors (13,895 collected, 2,372 s). The previous report was 13,474 passed; the delta is the new per-recording scope,
  group-ownership, lifecycle and Confirm-bay backend tests plus the enlarged Node-harness suite.
- **Backend focused** `test_d5a2b2a_measurement_side_config.py` (75): includes KPDN1 Primary in recording A / Secondary in recording B inside one Engineering Context (an A change never reinterprets B; each Level 1 reaches only its own
  non-overridden associations; clear-on-equal is per recording), membership/source/bay lifecycle, group ownership (single bay, shared side, different sides, unresolved sides, unrelated group unaffected, ratio untouched) and Confirm-bay-is-status-only.
  Mutation checks (each fails the suite): scoping key, ambiguity rule, consumed-channel ambiguity flag, per-recording clear-on-equal.
- **Node-harness frontend tests** `test_frontend_d5a_2b2b_measurement_side.py` (29): rendering of every state in both sections, request order, stale/foreign responses, recording-scoped bay choices, the confirmation review (two steps, status-only
  PATCH, cancel, failed review), no Reset / per-phase / second-authority code. Mutation checks: review gate, recording scope of the association lookup, group-to-bay filter.
- **Focused browser spec** `d5a_2b2b_measurement_side.spec.js` (13, real backend): Level 1; Level 2 in Group Details shared by the voltage and current groups; explicit Confirm bay (review, cancel, confirm, members/phases unchanged, Analysis still lists the bay);
  bay conflict/override disclosure; group in no bay; KPDN1 across two recordings; a group spanning two bays (shared then ambiguous); races; isolation and workspace reset with re-upload; 1280-wide and 600-wide layouts.
- **Existing browser regression** (all Recording Details `rd1-*`, `recording-details-toolbar`, `d5a_*` incl. the new spec, `lifecycle-hardening`, `analyser-recording-detection`): 280 passed / 0 failed, isolated backend :8200 / frontend :8102.
  Not run: the remaining ~1,000 browser specs, which touch no Recording Details code.
- Visual check: screenshots of Group Details (review panel; two bays on one group, ambiguous) at 1280x800 reviewed.
- Not changed: PU mathematics, Overcurrent / Impedance / Distance algorithms and their controls, CT/VT formulas (an existing-results snapshot test still requires identical responses).

## 6. Decisions taken that the owner may want to revisit

- Overview `bays` is now a list of (bay, recording) associations; a bay of several recordings appears once per recording. Group Details lists the associations of the *selected recording* only.
- A group spanning bays on the *same* side is a warning, not a block (a shared busbar VT is normal); only differing or unresolved sides block. Say if a stricter rule is wanted.
- Level-1 selection is a segmented Primary/Secondary control; when nothing is resolved neither segment is highlighted and the first choice is stored as a correction.

## 7. Calculated channels — deferred to D5A-2B2C (lineage and reference-side questions)

Nothing assigns a measurement side to a calculated channel today (`CALCULATED_CHANNEL_NOT_RESOLVED`), and none must be assigned merely because its inputs belong to the same recording. Questions to resolve in 2B2C before any
calculated channel resolves a side:

1. **Lineage.** Which input channels (transitively, through other calculated channels) determine the result's side? Is the side a property of the *operation* (e.g. RMS and angle shift preserve it, V×I power mixes quantities, V/I impedance changes
   the quantity entirely) or of its inputs only?
2. **Same-side requirement per operation.** Which operations require all inputs on one side (sum, difference, phase-to-phase from phase voltages) and must block or refuse mixed-side inputs, versus operations that legitimately combine
   voltage and current on different sides (impedance, power) and need an explicit conversion?
3. **Cross-recording inputs.** Inputs from recordings on different sides (or from different recordings of one bay, each with its own Level 1 / Level 2) — is the result unresolved, blocked, or does the engineer choose the reference side?
4. **Cross-group inputs.** Inputs from different Measurement Groups, bays or CT/VT groups: whose ratio may a conversion use, and is a group spanning bays (`spans_bays_ambiguous`) an automatic block for every calculated channel that reads it?
5. **Effective-side change propagation.** A Recording- or bay-level change must invalidate calculated channels that depend on it (and any cached results), consistent with the existing recompute cascade.
6. **Provenance and display.** How is an inferred versus engineer-confirmed input side shown on the result; is a result `strict_usable` only if every input is?
7. **Manual / constant inputs.** How do constants and Manual-mode inputs (no recording) take part — as side-neutral, or as a declared side?
8. **PU interaction.** Calculated-channel PU policies (DEC-211/213, calculated-current manual PU) currently rest on their own reference-side rules; their relation to the effective side belongs to the PU migration slice.

## 8. Remaining open questions

All of the owner's nine original questions now have an answer or a documented deferral: #3 and #7 resolved here, #6 deferred (§7). New for review: the two bullets in §6.
