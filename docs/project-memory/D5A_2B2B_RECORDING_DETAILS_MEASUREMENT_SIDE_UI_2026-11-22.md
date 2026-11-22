# D5A-2B2B — Recording Details: measurement side (frontend)

**Branch:** `feature/d5a-2b2b-recording-details-side-ui` (stacked on `feature/d5a-2b2a-measurement-side-config`, from the accepted D5A UAT baseline
`a2b55eb`). **Not pushed, merged or deployed.** Frontend plus the small backend refinements below. PU, Overcurrent, Impedance and Distance
numerical behaviour and their existing input controls are untouched. Authority and API: [D5A_2B2A_MEASUREMENT_SIDE_CONFIGURATION_2026-11-22.md](D5A_2B2A_MEASUREMENT_SIDE_CONFIGURATION_2026-11-22.md),
[DEC-216](DECISIONS.md#dec-216--recording-details-is-the-single-authority-for-recorded-measurement-side-d5a-2b2-unified-model).

## 1. What the engineer sees (Recording Details → Recording Info → "Measurement side")

| Control | Behaviour |
|---|---|
| **Recording** (Level 1) | One Primary / Secondary selector. Shows the side the recording declares (provenance "From recording"). Choosing the other side is an engineer correction ("Set by engineer"). Choosing the side the recording declares again simply returns to it — there is **no Reset**. |
| **Bays** (Level 2) | One selector per bay (an Engineering Context that uses this recording); never per R/Y/B phase. A bay follows the recording ("Follows the recording") until the engineer picks a side ("Set manually"). A manual choice survives later Recording changes. Choosing the side the bay inherits clears the override (back to "Follows the recording"). |
| **Confirm bay** | A bay that is only suggested / needs review cannot take a manual side (B2A-3). Its selector is disabled, it follows the recording, and a small **Confirm bay** link promotes it (existing Engineering Context `PATCH status=confirmed`). Recording-level selection and normal inheritance never require this. |

Provenance is discreet (one dim line per row). Contradictory or unresolved evidence is stated plainly and nothing is pre-selected:
mixed channel declarations ("… declare different sides (5 Primary, 1 Secondary). Select the side to use."), no declaration ("The recording does not
declare a measurement side. Select it."), a partially declared recording ("Inferred from the recording's declared channels (N declare no side). Select it to
confirm." — selecting the shown side confirms it), a voltage/current split ("Recorded: voltage primary, current secondary." — legitimate, not a warning), a bay whose
channels disagree within a quantity, and — whenever a correction or bay choice overrides declarations — an amber note ("The recording declares Primary on 5 channels.
The side set here is used; the original declarations are kept.", full channel list on hover).

## 2. Frontend architecture (no second authority)

`frontend/index.html`, one self-contained block (`D5A-2B2B-BLOCK-START/END`, before `wwRdCurrentConfigHtml`) plus CSS after `.ww-rd-section-divider` and four one-line hooks
(`wwRdBuildRecordingInfoHtml`, `refreshAllSourceViews`, `wwRdOnPageEntered`, `wwRdSelectSource`). It renders `GET …/measurement-side` and sends the engineer's choice
(`PUT …/sources/{id}/measurement-side`, `PUT …/engineering-contexts/{id}/measurement-side`); it never reads a P/S marker, channel name or CT/VT ratio and has no
side model, no browser storage and no per-phase control.

- **Latest wins.** Selections are sent one at a time in the order made; the view is re-read once after the last settles; the engineer's choice shows immediately
  (optimistic) until then. Every read carries a sequence number, so an older read can never replace a newer view; every response is checked against the
  workspace and recording still on screen (a workspace reset aborts reads; a recording switch invalidates in-flight work).
- **Lifecycle.** The view is invalidated whenever the source set changes, on page entry (bays may have changed elsewhere) and on recording selection.
- A refused save shows the backend's message and re-reads the truth.
- Electrical notation: the text uses the words "voltage"/"current" (no symbols), so no formatter is involved.
- Only the Recording Info panel changed; Waveform Analysis code, the analyzers and their inputs are untouched (one block + four hook lines in the shared file).

## 3. Backend refinements made in this slice (all within DEC-216 / B2A-1..5)

1. **Level 1 split:** Primary voltage with Secondary current is `recording_derived.status = "voltage_current_differ"` (info `RECORDING_VOLTAGE_CURRENT_SIDES_DIFFER`, with
   `voltage_side` / `current_side`), not `mixed`. Only disagreement within one quantity is `mixed` (conflict). No single recording-wide side exists; every channel keeps its own declaration.
2. **Disclosure:** the recording view's `overridden_declarations` is a property of the correction (declaration vs engineer value), so it stays visible even when a bay setting later takes over every channel.

## 4. Verification

- **Full backend regression** (final tree): 13,474 passed / 405 skipped / 0 failed / 0 errors (13,879 collected, 2,353 s). The D5A-2B2A report was 13,448 passed; the delta is 5 added
  backend tests (67 in `test_d5a2b2a_measurement_side_config.py`) plus the 21 new Node-harness tests.
- **Node-harness frontend tests** `test_frontend_d5a_2b2b_measurement_side.py` (21): rendering of every state, request order, stale/foreign responses, no Reset / per-phase / second-authority code. Mutation checks (each fails the suite):
  removing the older-read guard (2), removing the "re-read only after the last selection" rule (1), allowing a manual choice on an unconfirmed bay (1).
- **Focused browser spec** `d5a_2b2b_measurement_side.spec.js` (9, real backend): Level 1 (correction, disclosure, return to the recorded side), mixed / undeclared / split recordings, inferred confirmation,
  Level 2 (follow, manual survives, clear-on-inherited, no Reset, no phase selectors), bay conflict and override disclosure, quick second choice wins, slow read for another recording, isolation and workspace reset with re-upload, 1280-wide and 600-wide layouts.
- **Existing browser regression** (all Recording Details `rd1-*`, `recording-details-toolbar`, `d5a_*` incl. the new spec, `lifecycle-hardening`, `analyser-recording-detection`): 276 passed / 0 failed, on an isolated backend :8200 / frontend :8102.
  Not run: the remaining ~1,000 browser specs, which touch no Recording Details code (the shared `index.html` change is one new block plus four hook lines).
- Visual check: screenshots of the unconfirmed-bay and override states at 1280x800 reviewed.

## 5. Decisions taken that the owner may want to revisit

- **Confirm bay** is a small link in the bay row, because Engineering Contexts created at upload are `suggested` and no other page promotes them. It changes only the bay's status.
- Level-1 selection is a segmented Primary/Secondary control (not a dropdown): two mutually exclusive values, one click, state visible.
- When nothing is resolved (mixed / none / split) neither segment is highlighted; the engineer's first choice is stored as a correction.

## 6. Remaining open questions from the original nine (D5A-2B2A §9)

3. A bay spanning recordings with different Level 1 sides has no single inherited value, so any choice there is a manual override (nothing to clear to). The UI lists such a bay under each recording it uses.
6. Calculated channels are not resolved by the shared resolver (follow their inputs; PU / consumer slices).
7. A CT/VT group spanning two bays with different sides is not diagnosed; decide whether Recording Details should flag it.
New: the Analysis pages still show suggested bays as before; confirming a bay here changes its status for them too (status only; no membership change).
