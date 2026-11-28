# D5A-UI-003 — Restore the application's typography and spacing in Recording Details

**Branch:** `feature/d5a-ui-003-restore-typography-spacing` (from the deployed DEV build `d2ecc69`). **Not pushed, merged or deployed.**
CSS only. No script, markup, backend, measurement-side, CT/VT, Per-unit, Engineering Context, Overcurrent, Impedance or Distance change.

## Why

The owner's DEV review found that the Recording Info / Group Details redesign (UI-REC-001, D5A-UI-002) had enlarged type and spacing against the
application's own conventions: section headings 12 → 16 px, engineering values 11.2 → 15.2 px, the recording name 13.6 → 19.2 px, Edit and
Primary/Secondary buttons about 50 % taller, and card, body and row paddings larger. The two redesign CSS blocks had restated sizes that the existing
`.ww-rd-*` rules already define.

## Authority and method

The original UI (`a1e8d68`) is the authority. Its `.ww-rd-*` rules were read from the source and the real computed values were measured in a browser
for the same recording and screens on three builds: original `a1e8d68`, deployed `d2ecc69` and the corrected tree (1600, 1280 and 1000 px viewports; the
1000 px viewport gives the narrow third column of 388 px).

**Approach: delete, not override.** Instead of adding another layer of overrides, every size, weight, line-height and spacing declaration that the redesign
had added was removed, so the baseline rules apply again. What stays is only what the owner approved: the pale-blue gradient card surface, thin blue
border, 12 px rounded corners, icon tile, Primary/Secondary pill shape and colours, pill filter and Review buttons, the pill format badge, the two-column
metadata card, the card order and the independent Voltage / Current layouts. The blocks shrank by about 50 lines.

## Selectors and values changed

All inside the two blocks `UI-REC-001-CSS` and `D5A-UI-002-CSS` of `frontend/index.html` (measured at 1600 px, `a1e8d68` → `d2ecc69` → corrected).

| Component (selector) | Original | Deployed | Corrected |
|---|---|---|---|
| Recording name (`.ww-rd-recording-context-name`) | 13.6px / 600 | 19.2px / 700 | 13.6px / 600 |
| Analyze button (`.ww-rd-analyze-btn`) | 12.8px, pad 10 14 | 13.6px, pad 11 18 | 12.8px, pad 10 14 |
| Header bar (`.ww-rd-recording-action-bar`) | pad 8 12, h 51 | pad 12 18, h 61 | pad 8 12, h 51 |
| Tab (`.ww-rd-tab`) | 12px / 500, pad 9 12 | 13.6px / 700, pad 11 14 12 14 | 12px / 500, pad 9 12 |
| Third-column body (`.ww-rd-details-body`) | pad 12 16 | pad 16 18 20 18 | pad 12 16 |
| Section heading (`.ww-rd-section-heading`) | 12px / 600, mb 10 | 16px / 700, mb 4 | 12px / 600, mb 10 |
| Metadata rows (`.ww-rd-config-table`) | 12px, gap 4 / 10 | 12.8px, gap 7 / 14 | 12px, gap 4 / 10 |
| Note (`.ww-rd-side-note`) | 11.2px, m -4 0 8 | 12.8px, m 0 0 12 | 11.2px, m -4 0 8 |
| Primary / Secondary (`.ww-rd-side-btn`) | 11.2px, pad 6 12, h 23 | 13.6px, pad 10 14, h 34 | 11.2px, pad 6 12, h 23 |
| Per-unit warning (`.ww-rd-pu-config-issue`) | 11.2px | 13.6px, pad 10 14 | 11.2px, pad 8 10 |
| Review button (`.ww-rd-pu-review-btn`) | 11.2px, pad 4 10 | 13.6px, pad 8 18, h 33 | 11.2px, pad 4 10, h 22 |
| Group name (`.ww-rd-details-group-name`) | 13.6px / 600 | 18.4px / 700 | 13.6px / 600 |
| Channel list (`.ww-rd-details-channels`) | 11.52px | 12.8px | 11.52px |
| Edit button (`.ww-rd-edit-btn`) | 10.4px / 500, pad 1 7, h 21 | 12px / 600, pad 5 16, h 31 | 10.4px / 500, pad 1 7, h 21 |
| Field label (`.ww-rd-field-label`) | 10.88px | 12.48px | 10.88px |
| Field value (`.ww-rd-field-value`) | 11.2px / 500 | 15.2px / 700 | 11.2px / 500 |
| Field grid row gap (`.ww-rd-field-grid`) | 10 | 12 | 10 |
| Filter button (`.ww-rd-filter-btn`) | 10.4px, pad 4 8 | 12px, pad 6 14 | 10.4px, pad 4 8 |
| Group row (`.ww-rd-group-item`) | pad 7 12, h 31 | pad 6 12, h 34 | pad 7 12, h 32 (rounded transparent border) |
| Group row name (`.ww-rd-group-name`) | 11.2px / 400 | 12.48px / 600 | 11.2px / 400 |
| Group V/I badge (`.ww-rd-group-badge`) | 8px, pad 1 5 | 11.2px, pad 2 6 | 8px, pad 1 5 |

Card chrome now uses the baseline section padding (12 14) and the baseline vertical gap (10 px: heading, field grid and divider already use it).
Icon tile 40 → 32 px (icon 22 → 18 px, gap 18 → 12 px) so the tile matches the height of the compact heading plus note; this is the only dimension that
is not copied from a baseline rule, because the baseline has no icon tile. The Per-unit warning icon is 14 px (the baseline Analyze icon size).

Other corrections: the Ratio field of the Current Transformer card no longer keeps a left divider when the card collapses to one column; the last card
border and the removed `:last-child` rule are now covered by the card rule itself; redundant `#wwRdDetailsPanel` ID-qualified selectors were dropped
(no new specificity was added).

## Isolation

Every selector in the blocks begins with `#wwRd` or `.ww-rd-`; a static test enforces it. The diff touches only the two blocks (old lines 1440–1613), so
no shared or global rule changed and other pages (Overcurrent, Impedance Locus, Waveform Analysis, calculators) cannot be affected.
`backend/tests/test_frontend_d5a_ui_003_typography.py` also fails if the blocks ever restate `font-size`, `font-weight`, `line-height`,
`letter-spacing` or `min-height` (it fails 2 of its 3 checks on the deployed `d2ecc69` CSS).

## Verification

* Browser measurement at 1600 / 1280 / 1000 px for Recording Info, a Voltage group and a Current group: font sizes, weights and line heights equal the
  original; **no horizontal overflow in any of the nine views** and the third-column content height equals the original (739 / 639 / 639 px); the narrow
  column no longer scrolls (the deployed build needed 735 / 812 px of scroll height in a 622 px body).
* Frontend static and Node tests plus the group backend suite: 2,282 passed, 0 failed; the new guard adds 3 passed.
* Browser, Recording Details set (33 spec files): 364 passed, 16 failed. All 16 are in the five spec files that already fail on the untouched original
  frontend (`electrical-notation`, `phase-display-convention`, `post_upload_readiness`, `time-reference-interpretation`, `voltage-only-pu-display`;
  17 failures on `a1e8d68`); the failing test titles were compared and **none fails only on the corrected build**. None of those specs was edited or weakened.
* Affected specs on the final CSS (`ui_rec_001_recording_info`, `d5a_ui_002_group_details`, `rd1-responsive`, `rd1-ux3`): 60 passed, 0 failed.

Evidence: [evidence/d5a-ui-003/](evidence/d5a-ui-003/) — `original-*` (a1e8d68, 1600 px), `before-*` (deployed d2ecc69) and `after-*` (corrected), each for
`info`, `voltage`, `current` at 1600, 1280 and 1000 px (`-panel.png` = third column; a few `-page.png` full-window views of the corrected build).

## Not done / notes

* The Recording Info header and tabs are now exactly the original ones, so the UI-REC-001 bolder tab labels and 3 px underline are gone; the pill format
  badge and pill Analyze button shape remain. The filename keeps the approved sans-serif face at the table's size (the original used monospace 11.5 px).
* Card corner radius (12 px) and the pill shapes were approved and are unchanged.
