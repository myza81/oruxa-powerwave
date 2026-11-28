# UI-REC-001 — Recording Info tab redesign (third column)

**Branch:** `feature/ui-rec-001-recording-info-redesign` (from `uat/dev-d5a-20261121` @ `a1e8d68`). Not pushed, merged or deployed.
Presentation only. Backend, measurement-side authority, PU, CT/VT, Group Details and the Level 2 control are untouched.

## What changed

All of it is in `frontend/index.html`, localized as: one CSS block (`UI-REC-001-CSS-START/END`, scoped to `#wwRdDetailsPanel` /
`.ww-rd-details-body--info`), the Recording Info markup in `wwRdBuildRecordingInfoHtml`, and the Level 1 render inside the existing
`D5A-2B2B` block.

| Area | Result |
|---|---|
| Header and tabs | Larger name, pill format badge, pill Analyze Waveform, bolder tabs with a 3 px blue underline. Behaviour unchanged. |
| Metadata | One bordered card, two columns (Station / Recorder / Original file / Format / File size — Start / Trigger / Duration / Sample rate / Nominal frequency / Channels) with a vertical divider; reflows to one column when the card is narrower than 720 px. Real values only; the Trigger row is still omitted when it equals the start time. |
| Measurement Side | Pale-blue card, icon tile, heading, one-line description, pill Primary / Secondary. Removed: the "Recording" label and the normal-state status line. **Kept** (compact, below the control): inferred side, undeclared / mixed / voltage-current-split evidence, "Set by engineer" and the contradicted-declaration warning. |
| Per-unit Configuration | Card with icon tile, amber warning banner and an outline "Review affected groups" button. Shown only when a voltage group needs a base or has a conflict; text and navigation unchanged (now ends with a full stop, as in the mockup). |
| Time Reference | Same content; it takes the card surface so the tab reads as one set of cards. |

## Verification

* Node harness: 30 passed. New browser spec `ui_rec_001_recording_info.spec.js`: 11 passed. `d5a_2b2b_measurement_side.spec.js` passes.
* Recording Details regression (rd1-*, recording-details-toolbar, d5a_*, lifecycle, analyser detection, time-reference, notation and related): 363 passed, 20
  failed. The failing specs (post_upload_readiness, voltage-only-pu-display, time-reference-interpretation, stage3b3-source-badge, electrical-notation,
  phase-display-convention, sampling-rate-format, timing-authority-invalidation) fail **identically on the baseline frontend** (`a1e8d68`: 22 failed / 63 passed
  vs 22 failed / 81 passed with this change over the same files); they are environmental / pre-existing and none touches Recording Info.
  One test was adjusted: `rd1-ux3` D02b now expects the metadata card's two tables.

## Per-unit card on the first load (fixed in `b19f5de`, owner decision 2026-11-22)

The measurement groups load after Recording Info is first drawn and the details were not drawn again, so the Per-unit Configuration card appeared only after a
later redraw. `wwRdSelectSource` now redraws Recording Info once when the groups arrive — locally (no request, no loop) and only if the same recording is still
selected, Recording Info is still the view, and no control inside the panel has focus. Group Details and another recording are never overwritten. Tests: the card
is present on a first load with no tab switch and the draw count settles (fails on the code before the fix); late groups do not pull the engineer out of Group
Details. The request sequence is identical before and after the change.
