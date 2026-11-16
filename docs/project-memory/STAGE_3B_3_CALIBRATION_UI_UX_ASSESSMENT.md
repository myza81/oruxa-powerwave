# Stage 3B-3 — Calibration UI/UX Assessment

**Date:** 2026-11-14
**Branch:** `feature/vlt-ref-001-voltage-reference-safety`
**Status:** Implementation complete and committed as `81e7fb0`. All three slices
implemented in `frontend/index.html`. 25/25 Stage 3B-3 browser tests pass.
Full suite: 1391 passed / 2 skipped / 3 failed (pre-existing) / exit 0.
NOT pushed, deployed, or merged.

**Purpose:** Inventory the existing frontend calibration presentation, identify confirmed
gaps, and produce a minimal consistent presentation model so the owner can authorize an
implementation that is proportional to the gap.

---

## 1. Current frontend implementation inventory

The following calibration indicators already exist and are correct. They are summarized
here as the baseline against which gaps are measured.

### 1.1 Calculated POWER provenance badge

**Function:** `wwCalcChannelProvenanceBadgeHtml(calc)` — `frontend/index.html:33502`

Reads `calc.calibration_provenance_status` and returns:

| Status | Rendered output |
|---|---|
| `exploratory_unverified` | `⚠ exploratory` (amber, CSS `.ww-calc-provenance-badge--exploratory`) |
| `not_fully_verified` | `not fully verified` (grey, CSS `.ww-calc-provenance-badge--partial`) |
| `all_verified` | `""` (nothing shown) |
| `not_assessed` | `""` (nothing shown) |
| `blocked_invalid` | `""` (gate blocks evaluation before this point) |
| `blocked_structural` | `""` (gate blocks evaluation before this point) |

Inserted into two surfaces:
- Calculated channel manager list row: `frontend/index.html:42131`
- Waveform sidebar channel name cell: `frontend/index.html:42448`

### 1.2 Peak value annotation for exploratory POWER

**Function:** `wwPeakValueLineText(annotation)` — `frontend/index.html:36979`

Appends ` ⚠` (U+26A0) to the peak annotation text for `exploratory_unverified`
calculated channels. No annotation change for other provenance statuses.

### 1.3 Compliance calibration state

**Maps:** `WW_COMPLIANCE_READINESS_LABEL`, `WW_COMPLIANCE_MEMBER_STATE_LABEL` —
`frontend/index.html:54434–54451`

Both maps include an entry for `calibration_unavailable`. The readiness label is "Calibration
unavailable"; the member state label is also "Calibration unavailable".

**Guard:** `wwComplianceRepresentationRow(reference)` — `frontend/index.html:54529`

Prevents rendering "✓ Fundamental RMS available" when any compliance member state is
`calibration_unavailable`. The guard is in place and correct.

**CSS:** `.ww-compliance-readiness-status--calibration_unavailable { color: #a86a00; }` —
`frontend/index.html:7213` (amber).

### 1.4 Per-unit reference status (unverified reference)

**Function:** `wwPuReferenceStatus(status, compatibility)` — `frontend/index.html:32579`

Returns `{ label: "Unverified reference", detail: "..." }` when PU status is `configured`
and compatibility is `unverified`. The resulting badge is inserted by
`wwPuReferenceBadgeHtml(reference)` inside `analogChannelNameCellHtml()` — the source
channel name cell in the channel list tables.

This is a PU-domain indicator, not a physical calibration indicator. Its presence in
`analogChannelNameCellHtml()` is noted as the established badge-insertion pattern for
Section 5 (reuse strategy).

---

## 2. Confirmed UI/UX defects

### Defect 1 — Source channel list: no physical calibration indicator [HIGH]

**Location:** `analogChannelNameCellHtml()` — `frontend/index.html:29258`

**Finding:** `channel.calibration_authority` is returned by the backend API for every
source channel and is present in the channel objects passed to the channel list renderer.
Zero occurrences of the string `calibration_authority` exist anywhere in
`frontend/index.html`. The field is never read by any frontend function.

**Consequence:** An engineer looking at the channel list cannot distinguish:
- BEN5K Verified sources (physical calibration confirmed)
- BEN5K Unverified sources (physical calibration NOT confirmed — ENG values are
  uncorrected by √2/16 or equivalent factor; phasor analysis is blocked)
- BEN5K Invalid sources (blocked entirely for analysis and calculated channels)
- COMTRADE Not-Assessed sources (backward compat; no calibration claim at all)

This is the most engineer-critical gap. All downstream calibration gates (Stages 3B-2A
through 3B-2C) fire correctly, but the source channel list gives no indication of WHY
a phasor role is blocked or why compliance shows `calibration_unavailable`.

### Defect 2 — Phasor role status label: missing `calibration_unavailable` [MEDIUM]

**Location:** `wwPhasorRoleStatusLabel(status)` — `frontend/index.html:55306`

**Finding:** The function's label map contains four entries: `missing`, `needs_configuration`,
`ambiguous`, `not_eligible`. It has no entry for `calibration_unavailable`. The fallback
returns the raw string `"calibration_unavailable"`.

**Consequence:** When a phasor role is blocked by DEC-213, the role status chip in the
phasor panel shows the raw key `calibration_unavailable` instead of a human-readable
label. The raw string is legible but inconsistent with the polished labels for all
other statuses.

### Defect 3 — Phasor reason codes: four DEC-213 codes missing [MEDIUM]

**Location:** `WW_PHASOR_REASON_TEXT` constant — `frontend/index.html:52966`

**Finding:** `WW_PHASOR_REASON_TEXT` maps reason codes to human-readable explanations for
phasor role and diagram blocking. It currently has 12 entries. Four DEC-213 calibration
reason codes are absent:

| Missing code | Expected explanation |
|---|---|
| `physical_calibration_unverified` | Physical calibration has not been verified for this source. This channel cannot be used for authoritative phasor analysis. |
| `physical_calibration_invalid` | Physical calibration is explicitly invalid for this source. This channel is blocked from all analysis. |
| `ben5k_authority_absent` | No calibration authority record was found for this BEN5K channel. |
| `channel_not_found_ben5k` | The channel name was not found in the BEN5K recording's analog channel list. |

**Consequence:** When these reason codes appear in phasor role cards (returned by the
backend as `reason_code` on a blocked role result), `wwPhasorReasonText()` falls through to
its `|| code` fallback, displaying the raw machine-readable string. The underlying behavior
is correct; the presentation is not.

### Defect 4 — Cursor value cells: no calibration qualifier for exploratory POWER [MEDIUM]

**Location:** `wwCurValueText(sourceId, channelName, kind)` — `frontend/index.html:46442`

**Finding:** `wwCurValueText()` returns `wwFormatEngineeringValue(entry.aValue)` — a plain
formatted number with no calibration indication. When a calculated POWER channel with
`calibration_provenance_status = "exploratory_unverified"` is active, the cursor A/B
cells show a bare number, with no visual qualifier to indicate the value is exploratory.

**Consequence:** An engineer reading cursor A and cursor B values for a POWER channel
derived from BEN5K sources cannot distinguish exploratory from authoritative cursor
readings in the cursor column alone. The existing sidebar badge (`⚠ exploratory`)
provides the signal in the channel name cell, but the cursor value cell is unmarked.

Whether this constitutes a required change or whether the sidebar badge is sufficient
is an owner decision (see Section 10).

---

## 3. Existing functionality to preserve

The following must be preserved exactly across any Stage 3B-3 implementation:

| Surface | Implementation | Preserve |
|---|---|---|
| Calc channel provenance badge | `wwCalcChannelProvenanceBadgeHtml()` | Do not widen/narrow badge conditions |
| Peak annotation ⚠ | `wwPeakValueLineText()` exploratory check | Exact glyph, exact condition |
| Compliance `calibration_unavailable` state | `WW_COMPLIANCE_READINESS_LABEL`, `WW_COMPLIANCE_MEMBER_STATE_LABEL`, guard in `wwComplianceRepresentationRow()` | No wording change without owner approval |
| PU "Unverified reference" badge | `wwPuReferenceStatus()`, `wwPuReferenceBadgeHtml()` | These are PU-domain; Stage 3B-3 must not alter their semantics |
| Compliance CSS token | `.ww-compliance-readiness-status--calibration_unavailable { color: #a86a00; }` | Preserve amber token; Stage 3B-3 may reuse this color for consistency |
| Calc provenance badge CSS | `.ww-calc-provenance-badge--exploratory`, `.ww-calc-provenance-badge--partial` | Existing CSS tokens; new source badges should not override these |

---

## 4. Recommended calibration presentation vocabulary

The vocabulary below is proposed for consistency across all calibration indicators.
All wording is subject to owner approval (Section 10).

### 4.1 Source channel calibration badge text

| Calibration authority status | Proposed badge label | Tooltip / detail |
|---|---|---|
| Verified | *(no badge — normal state)* | n/a |
| Unverified | `⚠ Unverified` | Physical calibration has not been verified. Engineering values may require a correction factor. Phasor analysis is blocked. |
| Invalid | `✕ Invalid calibration` | Physical calibration is explicitly invalid. This channel is blocked from analysis and calculated channels. |
| Not Assessed (None) | *(no badge — backward compat)* | n/a |

Rationale for not showing Verified: the channel list is already the undecorated state. Adding
a "✓ Verified" badge to every BEN5K Verified channel would add visual noise with no
engineer action required. Only states that require engineer attention are signalled.

Rationale for not showing Not Assessed: existing COMTRADE and CSV channels all have no
authority record. Badging every COMTRADE channel as "Not Assessed" would swamp the list
with low-value indicators. The existing PU "Unverified reference" convention already
handles the COMTRADE PU case.

### 4.2 Phasor role status label

| Status | Proposed label |
|---|---|
| `calibration_unavailable` | `Physical calibration unavailable` |

### 4.3 Phasor reason code text

| Reason code | Proposed text |
|---|---|
| `physical_calibration_unverified` | Physical calibration has not been verified for this source. This channel cannot be used for authoritative phasor analysis. |
| `physical_calibration_invalid` | Physical calibration is explicitly invalid for this source. This channel is blocked from all analysis. |
| `ben5k_authority_absent` | No calibration authority record was found for this BEN5K channel. |
| `channel_not_found_ben5k` | The channel name was not found in the BEN5K recording's analog channel list. |

### 4.4 Electrical notation compliance

The source calibration badge text does not include phase names (it qualifies the whole channel,
not a phase-labelled quantity). DEC-117/DEC-118 (`wwElectricalSymbol*()` / `wwRichLabelHtml()`)
does NOT apply to the badge text itself. DEC-117/DEC-118 would apply only if a badge or
tooltip rendered phase-subscripted symbols (e.g. V<sub>A</sub>). None of the proposed
vocabulary in Sections 4.1–4.3 includes such symbols.

---

## 5. Minimal component/helper reuse strategy

### 5.1 Source calibration badge

**Pattern to reuse:** `wwPuReferenceBadgeHtml(reference)` and the `wwDisplayedReference()`
helper alongside it.

`analogChannelNameCellHtml()` already inserts the PU badge at the end of the name cell
span (`frontend/index.html:29280`). The new source calibration badge follows the same
pattern:

```
analogChannelNameCellHtml()
  └─ wwPuReferenceBadgeHtml(reference)      ← existing, PU domain
  └─ wwSourceCalibrationBadgeHtml(channel)  ← NEW, physical calibration domain
```

`wwSourceCalibrationBadgeHtml(channel)` reads `channel.calibration_authority` and returns
either a compact `<span class="ww-source-calibration-badge hint" ...>` or `""`.

The `hint` CSS class already exists in this codebase (used by the PU badge); it provides
the visual styling and tooltip affordance without introducing a new CSS primitive.

### 5.2 Phasor additions

No new function or component required:
- `wwPhasorRoleStatusLabel()` — add one key/value to the `labels` map.
- `WW_PHASOR_REASON_TEXT` — add four key/value entries to the existing constant.

Both are single-line additions within existing data structures.

### 5.3 CSS tokens

New CSS class naming should follow the existing DEC-213 pattern:

```css
.ww-source-calibration-badge--unverified { color: #a86a00; }  /* amber — same as compliance */
.ww-source-calibration-badge--invalid    { color: var(--warn, #c0392b); }  /* red */
```

No new CSS primitives needed; both colors already exist in the codebase.

### 5.4 Cursor cell calibration qualifier (Defect 4 — if authorized)

If the owner authorizes a cursor calibration qualifier for Defect 4, the minimal approach
is to append ` ⚠` to the return value of `wwCurValueText()` when
`ww.displayed.get(wwChannelKey(sourceId, channelName))?.channel?.calibration_provenance_status`
equals `"exploratory_unverified"`. No new helper is needed; the lookup mirrors the
existing `wwIsAnalogChannelVisible()` pattern. This is a medium-effort change contingent
on owner decision OD-S3B3-4 (Section 10).

---

## 6. Required changes by frontend subsystem

### 6.1 Source channel list subsystem

**Files:** `frontend/index.html`

**Change:** Add `wwSourceCalibrationBadgeHtml(channel)` helper function. Insert call inside
`analogChannelNameCellHtml()` after `wwPuReferenceBadgeHtml(reference)`.

**CSS:** Add `.ww-source-calibration-badge--unverified` and
`.ww-source-calibration-badge--invalid` to the CSS block near line 7213.

**Data availability:** `channel.calibration_authority` is in the backend API response
for source channels. The field is returned on the `AnalogChannelOut` schema and is
already present in the channel objects that reach `analogChannelNameCellHtml()`. No
additional API call or schema change is required.

**Surfaces affected:**
- Recording channel table (Channels tab, `frontend/index.html:17932`)
- Waveform sidebar channel table (sections 13/15/16/25)
- Engineering Context configuration channel picker (`frontend/index.html:29075`)
- Any surface that calls `analogChannelNameCellHtml()`

### 6.2 Phasor panel subsystem

**Files:** `frontend/index.html`

**Change A:** In `wwPhasorRoleStatusLabel()` (line 55306), add:
```js
calibration_unavailable: "Physical calibration unavailable",
```

**Change B:** In `WW_PHASOR_REASON_TEXT` (line 52966), add four entries for
`physical_calibration_unverified`, `physical_calibration_invalid`,
`ben5k_authority_absent`, `channel_not_found_ben5k` (see vocabulary, Section 4.3).

**Data availability:** Both are static maps. The reason codes are already returned by the
backend as `reason_code` on blocked phasor role results; the frontend already passes them
through `wwPhasorReasonText()`. No schema or API change is required.

### 6.3 Cursor value subsystem (conditional — awaiting owner decision OD-S3B3-4)

**Files:** `frontend/index.html`

**Change (if authorized):** In `wwCurValueText()` (line 46442), after the value is
formatted but before it is returned, append ` ⚠` when the channel is a calculated
channel with `calibration_provenance_status === "exploratory_unverified"`.

**Risk:** `ww.displayed` caches the channel object including `calibration_provenance_status`.
The status is set at channel load time and updated when channels are refreshed. No
additional fetch is required. The main risk is that the cursor cell update path
(`wwUpdateCursorValueCellsForChannels()`) re-calls `wwCurValueText()` on every cursor
drag; the lookup is O(1) from the existing `ww.displayed` map — no performance concern.

---

## 7. Proposed implementation slices

### Slice 3B-3-A — Phasor label polish (lowest risk)

**Scope:**
- Add `calibration_unavailable: "Physical calibration unavailable"` to
  `wwPhasorRoleStatusLabel()`.
- Add 4 DEC-213 reason code entries to `WW_PHASOR_REASON_TEXT`.

**Risk:** Minimal — data-only additions to existing static maps. No behavior change.
Existing tests are unaffected. No new CSS.

**Test:** Targeted browser test: upload BEN5K Unverified recording, navigate to Phasor
Diagram panel, assert that the blocked role card displays "Physical calibration
unavailable" (not the raw key) and that the reason text matches one of the new entries.

**Prerequisite:** None. Can be authorized and implemented independently of Slice 3B-3-B.

### Slice 3B-3-B — Source channel calibration badge (main gap)

**Scope:**
- New `wwSourceCalibrationBadgeHtml(channel)` helper.
- Insert into `analogChannelNameCellHtml()`.
- CSS tokens for Unverified (amber) and Invalid (red).

**Risk:** Medium-low. `analogChannelNameCellHtml()` is a high-frequency render function
called for every channel row. The badge reads one field that is already in the channel
object — no additional API call, no additional map lookup. The pattern mirrors the
existing PU badge insertion, which has been stable across multiple UAT cycles.

**Test:** Browser test: upload `synthetic_ben5k_phasor.ben` (Unverified source), navigate
to channel list, assert `.ww-source-calibration-badge--unverified` is present on the
expected channel row. Verify no badge on COMTRADE source (Not-Assessed backward compat).

**Prerequisite:** Owner approval of badge vocabulary (OD-S3B3-1) and badge scope
(OD-S3B3-2) in Section 10.

### Slice 3B-3-C — Cursor calibration qualifier (optional/deferred)

**Scope:**
- Modify `wwCurValueText()` to append ` ⚠` for exploratory POWER channels.

**Risk:** Medium. `wwCurValueText()` is in the hot path of cursor drag. The lookup is
O(1) but adds a branch to a function that runs on every rendered cursor cell on every
cursor move. The ⚠ glyph is already used in the peak annotation — consistent.

**Prerequisite:** Owner decision OD-S3B3-4 (Section 10).

**Default recommendation:** Defer Slice 3B-3-C unless the owner decides the sidebar
badge alone is insufficient. The existing `⚠ exploratory` badge in the sidebar channel
name cell is visible alongside the cursor columns and provides adequate signal for the
typical engineering workflow.

---

## 8. Browser regression and owner UAT plan

### 8.1 Existing regression suites (must pass, no soft-skips)

| Suite | Scenarios | Covers |
|---|---|---|
| `ben5k-phasor-calibration-gate.spec.js` | K, G, H, I (COMTRADE) | Phasor gate backward compat |
| `compliance-calibration-gate.spec.js` | A, B, C×2 | Compliance gate; `calibration_unavailable` |
| `power-provenance.spec.js` | A–H | POWER provenance badge, peak ⚠, sidebar badge |

All existing suites must pass with 0 failures and 0 soft-skips after any Stage 3B-3
implementation.

### 8.2 New browser tests required by slice

**Slice 3B-3-A test (`phasor-calibration-labels.spec.js`):**

| Scenario | Assertion |
|---|---|
| A — BEN5K Unverified → phasor role status chip | Assert text is "Physical calibration unavailable", not the raw key |
| B — BEN5K Unverified → phasor role reason text | Assert reason text contains the human-readable expansion for `physical_calibration_unverified`, not the raw code |
| C — COMTRADE (Not Assessed) → phasor role status | Assert no `calibration_unavailable` status present (backward compat) |

**Slice 3B-3-B test (`source-calibration-badge.spec.js`):**

| Scenario | Assertion |
|---|---|
| A — BEN5K Unverified source uploaded | Channel list contains `.ww-source-calibration-badge--unverified` on that source's channels |
| B — COMTRADE source uploaded | Channel list does NOT contain any `.ww-source-calibration-badge` element (Not-Assessed produces no badge) |
| C — Unverified badge tooltip/aria | Badge `title` or `aria-label` contains the agreed detail text |
| D — No JS errors throughout | `page.on("pageerror")` accumulator empty after all interactions |

### 8.3 Owner UAT checkpoints

The following items require hands-on owner review before implementation is merged; they
cannot be verified by automated browser tests alone:

1. **Badge placement in channel list:** owner to confirm the badge sits correctly to the
   right of the PU badge (or the channel name when no PU badge exists), and that the row
   height is not distorted on representative recordings.
2. **Badge wording approval:** owner to confirm "⚠ Unverified" and "✕ Invalid calibration"
   as the displayed badge text, or propose alternatives (OD-S3B3-1).
3. **Phasor reason text legibility:** owner to confirm all four DEC-213 reason code
   expansions are actionable and clear to the target engineering audience.
4. **No regression on COMTRADE recordings:** owner to confirm existing COMTRADE recordings
   show no badge and no change in behavior.

---

## 9. Performance considerations

**`analogChannelNameCellHtml()` badge insertion (Slice 3B-3-B):**
This function is called on every channel row render, including live updates after cursor
drags and visibility toggles. The proposed `wwSourceCalibrationBadgeHtml(channel)` reads
`channel.calibration_authority.status` — a single property access on an already-loaded
object. No additional API call, no DOM query, no map lookup. Cost is effectively zero.
The existing PU badge insertion uses the same pattern and has never been a performance
concern.

**`WW_PHASOR_REASON_TEXT` additions (Slice 3B-3-A):**
These are static constant additions. Zero runtime cost. The object is initialized once
at page load.

**Cursor cell qualifier (Slice 3B-3-C, if authorized):**
`wwCurValueText()` runs on every cursor drag for every visible channel. The proposed
addition reads one field from `ww.displayed` — a `Map` keyed by channel key, O(1).
On a typical recording with 20–30 channels and 2 cursors, this adds 60 Map lookups per
drag event. Each lookup is nanosecond-level. No measurable impact expected; no
optimization required before implementation.

---

## 10. Decisions requiring owner approval

The following decisions must be resolved before any Slice 3B-3 implementation begins.
They are enumerated here as OD-S3B3-1 through OD-S3B3-5.

### OD-S3B3-1 — Source badge vocabulary (REQUIRED before Slice 3B-3-B)

**Question:** Approve the proposed badge wording from Section 4.1:
- Unverified: `⚠ Unverified`
- Invalid: `✕ Invalid calibration`
- Verified: (no badge)
- Not Assessed: (no badge)

or propose alternative wording.

**Impact:** Badge label text and the tooltip detail text. No implementation decision
depends on this beyond the string literals in `wwSourceCalibrationBadgeHtml()`.

### OD-S3B3-2 — Source badge scope: show Verified badge? (REQUIRED before Slice 3B-3-B)

**Question:** Should BEN5K Verified channels show a positive confirmation badge (e.g.
`✓ Verified`)? The Section 4.1 recommendation is NO (suppress the badge for Verified
channels; only signal states that require engineer attention).

**Impact:** One conditional branch in `wwSourceCalibrationBadgeHtml()`. The recommendation
is to suppress it. Owner should confirm this is acceptable or request a Verified badge.

### OD-S3B3-3 — Phasor label and reason text wording (REQUIRED before Slice 3B-3-A)

**Question:** Approve the specific wording for:
- `calibration_unavailable` role status label: `"Physical calibration unavailable"`
- 4 reason code expansions in Section 4.3

or propose alternative wording.

**Impact:** String literals in `wwPhasorRoleStatusLabel()` and `WW_PHASOR_REASON_TEXT`.
No structural change.

### OD-S3B3-4 — Cursor calibration qualifier (required before Slice 3B-3-C)

**Question:** Is the existing `⚠ exploratory` sidebar badge sufficient for cursor
context, or is a ` ⚠` suffix required in the cursor A/B value cells when the channel
is `exploratory_unverified`?

**Default recommendation:** The sidebar badge is sufficient. The cursor column value
qualifies the magnitude; the adjacent channel name cell already carries the exploratory
badge. Adding ` ⚠` to cursor values introduces visual noise in the cursor columns that
may distract from the numerical value itself.

**Impact:** Determines whether Slice 3B-3-C is implemented at all.

### OD-S3B3-5 — Not-Assessed badge for COMTRADE channels (REQUIRED before Slice 3B-3-B)

**Question:** Should COMTRADE (Not-Assessed / `None` authority) channels show any
calibration badge?

**Default recommendation:** NO badge for Not-Assessed. The existing behavior produces
no badge and no PU reference badge for a plain COMTRADE channel. Introducing a "Not
assessed" badge for every COMTRADE channel would add pervasive low-value visual noise
to recordings that have always worked without any calibration context.

**Impact:** One conditional branch in `wwSourceCalibrationBadgeHtml()`. Owner should
confirm the no-badge recommendation is acceptable.

---

## Approved owner decisions (2026-11-14)

| Decision | Approved |
|---|---|
| OD-S3B3-1 | Unverified source → `⚠ Calibration unverified` (amber). Invalid source → `✕ Calibration invalid` (red). |
| OD-S3B3-2 | Suppress Verified badges. Do not infer Verified from badge absence. |
| OD-S3B3-3 | `calibration_unavailable` phasor role status → "Calibration unavailable". |
| OD-S3B3-4 | Implement cursor qualifier in Slice 3B-3-C (not deferred). |
| OD-S3B3-5 | Not Assessed — suppress persistent badge; status accessible in details. |

## Implementation notes (2026-11-14)

### Data-flow correction (Slice B)

The owner's implementation template used `channel.calibration_authority.status` with
uppercase `"CALIBRATION_UNVERIFIED"`. The actual API schema (`AnalogChannelOut`,
`backend/app/schemas/source.py:57`) exposes `calibration_status: str | None` (top-level
field, lowercase values `"verified"`, `"unverified"`, `"invalid"`, `null`). Implementation
uses `channel.calibration_status` with lowercase comparisons accordingly.

### Phasor reason code verification

All four reason codes in `WW_PHASOR_REASON_TEXT` additions are confirmed against backend
source constants in `backend/app/domain/physical_calibration.py`:
- `physical_calibration_unverified` = `REASON_UNVERIFIED` (line 100)
- `physical_calibration_invalid` = `REASON_INVALID` (line 101)
- `ben5k_authority_absent` — hardcoded in `phasor_analysis_service.py:202`
- `channel_not_found_ben5k` — hardcoded in `phasor_analysis_service.py:198`
All four match exactly.

### Cursor qualifier mechanism (Slice C)

`wwCurValueText(sourceId, channelName, kind)` now checks `wwIsCalculatedSourceId(sourceId)`
and looks up `ww.calculatedChannels.get(sourceId)?.calibration_provenance_status`. If
`"exploratory_unverified"`, appends `" ⚠"` after the formatted value. The lookup is O(1)
from the existing `ww.calculatedChannels` Map — no new API calls, no additional fetch.

### Changed files

- `frontend/index.html` only. One file changed, three slices.

### Test results

| Suite | Tests | Result |
|---|---|---|
| `stage3b3-source-badge.spec.js` (NEW) | 6 | PASS |
| `ben5k-phasor-calibration-gate.spec.js` (+1 phasor label test) | 7 | PASS |
| `compliance-calibration-gate.spec.js` | 4 | PASS |
| `power-provenance.spec.js` | 8 | PASS |
| **Total** | **25** | **25 passed / 0 failed / 0 skipped** |

---

## Governance compliance

- `frontend/index.html` modified (3 slices).
- `browser-tests/stage3b3-source-badge.spec.js` added (6 scenarios).
- `browser-tests/ben5k-phasor-calibration-gate.spec.js` extended (+1 phasor label test).
- No backend code modified.
- Committed as `81e7fb0` on `feature/vlt-ref-001-voltage-reference-safety`.
- Not pushed, merged, or deployed.
- All prior DEC-213 commits (`35af9e1` through `d03dbdb`) preserved.
- BEN numerical calibration correction not in scope.
- PU mathematics not in scope.
- Slice 6D not in scope.
