# NF-2 — Recording Details nominal-frequency control (release-gated)

**Date:** 2026-11-24 · **Decision:** [DEC-217](DECISIONS.md) · **Branch:** `feature/nf-2-recording-details-nominal-frequency`, worktree `.local-data/nf-2`
**Baseline:** the verified NF-1 candidate (`0c4abba`; its verification record `c5cec0b` is merged in). The complete ancestry is local and unpublished: published DEV `e9c621c` → accepted R0/R1A commits (`2a7ddc1`, `fb5bb75`, `9bb5f38`, `5f932ec`, `9267ca4`, `9f45913`, merged as `0aa3562`) → NF-1 (`d917622`, `c2e79bb`, `628ffd5`, `0c4abba`) → NF-2.
**Status:** implemented and verified locally. **Not pushed, merged or deployed.** NF-3 is not started. The control is **off for every user** until the release gate is switched on.

## What it does

Recording Details → Recording Info → the existing **Nominal frequency** row. It reads and writes only the NF-1 endpoint `GET|PUT /api/v1/workspaces/{ws}/sources/{id}/nominal-frequency`; it decides nothing itself and creates no second frequency authority.

| State | What the row shows |
|---|---|
| Declared and valid | plain `60 Hz`, Auto selected, no label; tooltip `Imported 60.0 Hz · recording metadata` |
| Assumed 50 Hz (missing/unparseable value, CSV, BEN without a value) | `50 Hz` with a visible **Assumed default** flag |
| Declared but unusable (0, negative, NaN, ±inf, outside 1–1000 Hz) | `—`, an explicit notice naming the declared value, "Waveform viewing is unaffected", Auto selected; choosing Manual lets the engineer enter a value |
| Manual | the manual value, Manual selected, **Edit** link, and a line `Auto: 50 Hz · recording metadata. Imported 50.0 Hz.` |
| Editing | compact input + Hz + Apply / Cancel; Enter applies, Escape cancels |

* **Manual equal to Auto is kept as Manual** (the server stores it; the UI shows the server's mode).
* **Return to Auto** sends `{"mode":"auto"}`; the imported metadata is never written (verified against the source summary and by the NF-1 hashes).
* **Validation:** the editor refuses an empty value, a non-number, and anything outside 1–1000 Hz before sending; the server remains the authority. A server rejection (400 with its message) or a network failure keeps the editor open on the engineer's text with the message, and changes nothing. A failed Auto reverts the display to the server's state with a message.
* **Revisions and stale answers:** the client keeps the highest revision seen for the recording and never applies an older answer (it re-reads, at most twice); reads are tagged and only the newest read for the current recording and workspace is applied; changes are sent in the order made and the server's view is re-read only after the last one settles, so a quick Manual → Auto → Manual sequence ends on the last choice (revision 3).
* Provenance is shown where it informs (assumed, unusable, Manual, tooltip), not as a permanent label on a normal declared value, following the NF-001 design; the owner asked for imported frequency and provenance to be available, which this satisfies without adding a configuration card.

## Release gate

`window.POWERWAVE_CONFIG.featureFlags.nominalFrequencyOverride === true` — absent by default; only the boolean `true` opens it.

* The checked-in `frontend/config.js` and the container entrypoint do not set it (a static test fails if either ever does), so no deployment enables it by accident.
* **Gate off:** the row is the original read-only row (its code path is unchanged); nothing is requested.
* **Gate on:** besides the control, a persistent note reads **"Preview: calculations do not use this setting yet."** (`WW_NF_CONSUMERS_MIGRATED = false`, flipped by NF-3).
* Browser tests switch the gate on by serving a modified `/config.js`; to try it by hand, add `window.POWERWAVE_CONFIG.featureFlags = { nominalFrequencyOverride: true };` to a local `config.js`.

## Files

| File | Change |
|---|---|
| `frontend/index.html` | +385 / −1: NF-2 CSS (own block), the client block (`wwRdNf*`), one gated call replacing the Nominal frequency row, three invalidation hooks |
| `browser-tests/nf2_recording_details_nominal_frequency.spec.js` | new, 38 tests (37 run, 1 screenshot test runs only with `NF2_SCREENSHOT_DIR`) |
| `backend/tests/test_frontend_nf2_release_gate.py` | new, 8 static gate tests |
| `docs/project-memory/evidence/nf-2-2026-11-24/*.png` | 9 owner-review screenshots |
| `docs/project-memory/NF_1_…md`, `NF_2_…md`, `HANDOFF.md` | records |

No file under `backend/app` is changed. Protected code (RMS, detectors, phasor, power, PU, CT/VT, side conversion, protection, providers, import, every consumer service, and the NF-1 resolver/registry/service/API): **39 of 39 byte-identical** to the NF-1 final commit. The calculated-channel builder still reads the imported value from the source inventory.

## Verification

* **Browser, `nf2_recording_details_nominal_frequency.spec.js`: 38 passed** (37 without `NF2_SCREENSHOT_DIR`, plus the screenshot test): gate off/on and non-boolean flag values; declared, assumed and unusable (0, nan) states; Auto ⇄ Manual; same-value Manual preserved (also after reload); Edit; return to Auto with originals untouched; correction of an unusable recording; Cancel/Escape; every client validation case; server rejection, network failure and failed Auto; save and reload; recording removal (value removed, same file re-added starts in Auto); workspace reset; two recordings independent; a slow answer for the previous recording never landing in the new one; rapid changes applied in order; a reordered older answer ignored; metadata card/tab regression; keyboard and live-region announcements; no console errors.
* **Static gate tests: 8 passed.**
* **Recording Details regression with the gate off: 297 passed, 0 failed** (run again after the CSS move: still 297/0) (`rd1-*`, `d5a-*`, `ui_rec_001`, `analyser-recording-detection`, 23 spec files).
* **UI mutation checks: 14 of 14 killed** (gate always on, loosely truthy, preview note removed, older answer accepted, validation bypassed, stale-read guard removed, Auto sending a manual value, Manual-equal-to-Auto dropped, recording switch keeping state, unusable notice removed, assumed flag removed, rejected save closing the editor, writes not gated, recording/workspace guard removed).
* **Full backend suite on the final NF-2 code commit `543ae50`: **14 492 passed, 405 skipped, 0 failed** (20 min). A first run on the preceding commit `e097f7f` found one failure, the D5A-UI-003 typography guard (the NF-2 pill rules had been placed inside the guarded UI-REC-001 CSS block); the rules now live in their own `NF-2-CSS-START/END` block and nothing else changed.**
* Visual UAT evidence (light, dark, narrow): `docs/project-memory/evidence/nf-2-2026-11-24/`.

## Limits and next steps

* The control is a **preview**: no calculation reads the override (the nine direct readers of `metadata.nominal_frequency` remain, frozen by the NF-1 tripwire). NF-3 migrates them, flips `WW_NF_CONSUMERS_MIGRATED`, and only then may the gate be opened for normal use.
* Existing calculated channels keep their stored frequency; the staleness advisory from the mock is not built (NF-3/NF-5).
* A wrong manual value is silent (60 Hz on a 50 Hz signal gives no error).
* The WUI-001–004 pane controls were not touched; the browser regression covered Recording Details only, not the Waveform page.
* Owner visual UAT of the control (gate on) is still to be done before NF-3.
