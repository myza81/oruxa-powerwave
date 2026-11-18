# RD-1 Slice B — Implementation Plan
**Recording Details V2.9 — Dedicated Page Skeleton, Recording Browser, Search/Sort, Upload Integration**

Date: 2026-11-18  
Branch: `feature/vlt-ref-001-voltage-reference-safety`  
Status: **AWAITING OWNER APPROVAL — do not implement**

---

## 0. Scope

Slice B adds the dedicated `recording-details` page shell with:

1. A new top-level nav button — "Recording Details" — immediately after Recordings.
2. A three-panel flex layout: Recording Browser (left), Group Summary (centre), Details Stub (right).
3. A scoped `wwRdState` object (D2).
4. A recording browser that reuses `fetchSourcesList()` with client-side search/sort.
5. An "Upload New" button wired to the existing upload trigger.
6. A groups panel that calls `wwFetchMeasurementGroupsForSource` when a recording is selected (centre panel stub — full content in Slice C).
7. A right-panel placeholder ("Select a group…") for Slice C.
8. `wwRdOnPageEntered()` lifecycle hook wired into `shellSetCurrentPage()`.

**Out of scope for Slice B:**
- Editing any field (Slice D).
- Showing `manual_conflict_detected` warning UI (Slice C).
- PU invalidation chain (Slice D pre-flight, as requested by owner).
- Waveform navigation from Recording Details (D3 — verify integration point in Slice D or its own sub-slice).
- RD-2 (nominal-frequency editing), RD-3 (CT/VT conversion).

---

## 1. Navigation Approach

### 1.1 Nav button — position

Insert a new `<button>` **immediately after** `mainNavRecordingsBtn` (line ~9789) and before `mainNavWaveformBtn`:

```html
<button type="button" class="shell-nav-item" id="mainNavRecordingDetailsBtn" title="Recording Details">
    <span class="shell-nav-icon" data-ww-icon="PAGE_RECORDING_DETAILS"></span>
    <span class="shell-nav-label">Recording Details</span>
</button>
```

**Icon**: `PAGE_RECORDING_DETAILS` — the icon-hydration system in `index.html` maps `data-ww-icon` tokens to inline SVGs at DOMContentLoaded. A document-with-pencil SVG is appropriate (see existing `PAGE_RECORDINGS` for shape precedent). The exact SVG is defined where other icon tokens are hydrated (search `PAGE_RECORDINGS` to find the icon block, then add `PAGE_RECORDING_DETAILS` there).

### 1.2 `shellSetCurrentPage()` — whitelist (line ~16317)

Add `"recording-details"` to the guard:

```js
page !== "recording-details" &&
```

Add show/hide line in the body:

```js
document.getElementById("pageRecordingDetails").hidden = page !== "recording-details";
```

Add `setShellNavCurrent` call:

```js
setShellNavCurrent("mainNavRecordingDetailsBtn", page === "recording-details");
```

Add lifecycle hook call (same block as `wwErOnPageEntered`, `wwRenderCalculatedChannelsPage`):

```js
if (page === "recording-details") {
    wwRdOnPageEntered();
}
```

### 1.3 Event listener (line ~60111 vicinity)

After the existing `mainNavCalculatorBtn` listener:

```js
document.getElementById("mainNavRecordingDetailsBtn").addEventListener("click", () => shellSetCurrentPage("recording-details"));
```

---

## 2. Page Section DOM

### 2.1 Insertion point

Insert `<section id="pageRecordingDetails" …>` **after** `<section id="pageDataPreparation" …>` (line ~13505). `pageDataPreparation` is the last `<section>` before the JS `<script>` block; "Recording Details" is a new sibling at the same level.

### 2.2 HTML structure

```html
<!-- RD-1 Slice B: Recording Details — dedicated three-panel view.
     D1 decision: a first-class page, not a modal.
     D2 decision: wwRdState owns all state — never shares wwMgSelectedSourceId
     or wwMgEditState with the existing Measurement Groups modal. -->
<section id="pageRecordingDetails" aria-label="Recording Details" hidden>
    <div class="ww-rd-layout">

        <!-- Panel 1: Recording Browser -->
        <div class="ww-rd-panel ww-rd-panel--browser" id="wwRdBrowserPanel">
            <div class="ww-rd-panel-header">
                <h2 class="ww-rd-panel-title">Recordings</h2>
                <button type="button" class="ww-rd-upload-btn" id="wwRdUploadBtn">
                    Upload New
                </button>
            </div>
            <div class="ww-rd-search-row">
                <input type="search" class="ww-rd-search" id="wwRdSearch"
                    placeholder="Search recordings…" aria-label="Search recordings" autocomplete="off">
                <select class="ww-rd-sort" id="wwRdSort" aria-label="Sort recordings">
                    <option value="name-asc">Name A–Z</option>
                    <option value="name-desc">Name Z–A</option>
                    <option value="date-desc">Newest first</option>
                    <option value="date-asc">Oldest first</option>
                </select>
            </div>
            <div class="ww-rd-recording-list" id="wwRdRecordingList" role="listbox"
                aria-label="Recordings" aria-multiselectable="false">
                <!-- Populated by wwRdRenderBrowser() -->
            </div>
        </div>

        <!-- Panel 2: Group Summary (Slice C will fill this) -->
        <div class="ww-rd-panel ww-rd-panel--groups" id="wwRdGroupsPanel">
            <div class="ww-rd-panel-header">
                <h2 class="ww-rd-panel-title">Measurement Groups</h2>
            </div>
            <div class="ww-rd-groups-body" id="wwRdGroupsBody">
                <!-- Populated by wwRdRenderGroups() -->
            </div>
        </div>

        <!-- Panel 3: Details / Edit (Slice C/D) -->
        <div class="ww-rd-panel ww-rd-panel--details" id="wwRdDetailsPanel">
            <div class="ww-rd-panel-header">
                <h2 class="ww-rd-panel-title">Group Details</h2>
            </div>
            <div class="ww-rd-details-body" id="wwRdDetailsBody">
                <p class="ww-rd-placeholder">Select a group to view details.</p>
            </div>
        </div>

    </div>
</section>
```

---

## 3. CSS

All new rules go into the existing `<style>` block inside `index.html` (project uses a single-file convention). Insert near the `#pageRecordings` block (~line 569) for proximity.

```css
/* ---- Recording Details page (RD-1) ---- */
#pageRecordingDetails {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
}
#pageRecordingDetails[hidden] { display: none; }

.ww-rd-layout {
    flex: 1 1 auto;
    display: flex;
    flex-direction: row;
    min-height: 0;
    gap: 0;
}

.ww-rd-panel {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    background: var(--panel);
    border-right: 1px solid var(--panel-border);
}
.ww-rd-panel:last-child { border-right: none; }

.ww-rd-panel--browser { flex: 0 0 260px; }
.ww-rd-panel--groups  { flex: 0 0 300px; }
.ww-rd-panel--details { flex: 1 1 auto; }

.ww-rd-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px 16px 10px;
    border-bottom: 1px solid var(--panel-border);
    flex-shrink: 0;
}
.ww-rd-panel-title {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text);
}

/* Upload button — same visual weight as secondary buttons in recordings header */
.ww-rd-upload-btn {
    font-size: 0.72rem;
    padding: 4px 10px;
}

.ww-rd-search-row {
    display: flex;
    gap: 6px;
    padding: 8px 10px;
    flex-shrink: 0;
    border-bottom: 1px solid var(--panel-border);
}
.ww-rd-search {
    flex: 1 1 auto;
    font-size: 0.75rem;
    padding: 4px 8px;
    background: var(--bg);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius);
    color: var(--text);
    min-width: 0;
}
.ww-rd-sort {
    font-size: 0.72rem;
    padding: 4px 6px;
    background: var(--bg);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius);
    color: var(--text);
    flex-shrink: 0;
}

.ww-rd-recording-list {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 4px 0;
}

/* Recording browser row */
.ww-rd-recording-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--panel-border);
}
.ww-rd-recording-item:last-child { border-bottom: none; }
.ww-rd-recording-item:hover { background: var(--hover-tint); }
.ww-rd-recording-item[aria-selected="true"] {
    background: var(--surface-tint);
    outline: 2px solid var(--accent);
    outline-offset: -2px;
}
.ww-rd-recording-item:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
}
.ww-rd-recording-item-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text);
    overflow-wrap: anywhere;
}
.ww-rd-recording-item-meta {
    font-size: 0.65rem;
    color: var(--text-dim);
}

.ww-rd-groups-body,
.ww-rd-details-body {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 12px 16px;
}

.ww-rd-placeholder {
    font-size: 0.75rem;
    color: var(--text-dim);
    text-align: center;
    margin-top: 32px;
}
```

---

## 4. State Object

Defined in the JS initialisation section, alongside other page-scoped state blocks (near `wwMgSelectedSourceId` etc., ~line 35802):

```js
// RD-1 (D2 decision): scoped state for the Recording Details page.
// NEVER share with wwMgSelectedSourceId or wwMgEditState.
const wwRdState = {
    selectedSourceId: null,   // string | null
    selectedGroupId: null,    // string | null
    searchQuery: "",          // string
    sortOrder: "name-asc",    // "name-asc"|"name-desc"|"date-desc"|"date-asc"
    sources: null,            // SourceSummaryOut[] | null — in-memory cache
    groupsLoading: false,     // bool — prevent double-fetch
};
```

**Lifecycle:** `wwRdState` is initialised once at page load and persists indefinitely. `shellSetCurrentPage("recording-details")` triggers `wwRdOnPageEntered()`, which refreshes `sources` from the cache (or re-fetches on first entry / after an upload). State survives navigation away and back — same "hide, don't destroy" lifecycle as every other page.

---

## 5. JavaScript Functions

### 5.1 `wwRdOnPageEntered()`

Called by `shellSetCurrentPage()` when navigating to Recording Details (see §1.2).

```js
async function wwRdOnPageEntered() {
    if (wwRdState.sources === null) {
        await wwRdRefreshSources();
    } else {
        wwRdRenderBrowser();  // re-render from cache (search/sort state preserved)
    }
}
```

### 5.2 `wwRdRefreshSources()`

```js
async function wwRdRefreshSources() {
    const sources = await fetchSourcesList();
    wwRdState.sources = sources || [];
    wwRdRenderBrowser();
}
```

### 5.3 `wwRdRenderBrowser()`

Applies client-side search/sort to `wwRdState.sources` and renders `.ww-rd-recording-item` rows into `#wwRdRecordingList`. Preserves `selectedSourceId` selection highlight. Shows "No recordings" placeholder if list is empty.

```js
function wwRdRenderBrowser() {
    const list = document.getElementById("wwRdRecordingList");
    if (!list) return;

    let items = wwRdState.sources || [];

    // Client-side search
    const q = wwRdState.searchQuery.trim().toLowerCase();
    if (q) {
        items = items.filter((s) => {
            const name = (s.recording_name || s.original_filenames?.[0] || "").toLowerCase();
            return name.includes(q);
        });
    }

    // Client-side sort
    items = items.slice().sort((a, b) => {
        const nameA = (a.recording_name || a.original_filenames?.[0] || "").toLowerCase();
        const nameB = (b.recording_name || b.original_filenames?.[0] || "").toLowerCase();
        switch (wwRdState.sortOrder) {
            case "name-desc": return nameB.localeCompare(nameA);
            case "date-desc": return (b.created_at || "").localeCompare(a.created_at || "");
            case "date-asc":  return (a.created_at || "").localeCompare(b.created_at || "");
            default:          return nameA.localeCompare(nameB); // "name-asc"
        }
    });

    if (items.length === 0) {
        list.innerHTML = '<p class="ww-rd-placeholder">' +
            (q ? "No recordings match your search." : "No recordings yet.") + '</p>';
        return;
    }

    list.innerHTML = items.map((s) => {
        const name = escapeHtml(recordingDisplayName(s));
        const meta = escapeHtml(formatRecordingStartTime(s) || "");
        const sel = s.id === wwRdState.selectedSourceId ? ' aria-selected="true"' : ' aria-selected="false"';
        return '<div class="ww-rd-recording-item" role="option" tabindex="0"' +
            sel + ' data-source-id="' + escapeHtml(s.id) + '">' +
            '<span class="ww-rd-recording-item-name">' + name + '</span>' +
            (meta ? '<span class="ww-rd-recording-item-meta">' + meta + '</span>' : '') +
            '</div>';
    }).join("");
}
```

**Note:** `recordingDisplayName(s)` and `formatRecordingStartTime(s)` are reused from the existing Recordings page (`renderRecordingsTable()`) — no duplication.

### 5.4 `wwRdSelectSource(sourceId)`

```js
async function wwRdSelectSource(sourceId) {
    wwRdState.selectedSourceId = sourceId;
    wwRdState.selectedGroupId = null;
    wwRdRenderBrowser();      // update selection highlight
    wwRdRenderGroups();       // show loading state immediately
    if (!sourceId) return;
    wwRdState.groupsLoading = true;
    const groups = await wwFetchMeasurementGroupsForSource(sourceId);
    wwRdState.groupsLoading = false;
    wwRdRenderGroups();       // render fetched groups
    wwRdRenderDetails();      // reset details panel
}
```

### 5.5 `wwRdRenderGroups()`

Slice B: shows loading indicator, "Select a recording…" empty state, or a minimal group list (name + kind badge only). Full group-detail content is Slice C.

```js
function wwRdRenderGroups() {
    const body = document.getElementById("wwRdGroupsBody");
    if (!body) return;
    if (!wwRdState.selectedSourceId) {
        body.innerHTML = '<p class="ww-rd-placeholder">Select a recording to view groups.</p>';
        return;
    }
    if (wwRdState.groupsLoading) {
        body.innerHTML = '<p class="ww-rd-placeholder">Loading…</p>';
        return;
    }
    const groups = ww.measurementGroups.get(wwRdState.selectedSourceId) || [];
    if (groups.length === 0) {
        body.innerHTML = '<p class="ww-rd-placeholder">No measurement groups configured.</p>';
        return;
    }
    body.innerHTML = groups.map((g) => {
        const sel = g.id === wwRdState.selectedGroupId ? ' aria-selected="true"' : ' aria-selected="false"';
        return '<div class="ww-rd-group-item" role="option" tabindex="0"' +
            sel + ' data-group-id="' + escapeHtml(g.id) + '">' +
            '<span class="ww-rd-group-name">' + escapeHtml(g.display_name) + '</span>' +
            '<span class="ww-rd-group-kind">' + escapeHtml(g.kind) + '</span>' +
            '</div>';
    }).join("");
}
```

### 5.6 `wwRdRenderDetails()`

Slice B: placeholder only.

```js
function wwRdRenderDetails() {
    const body = document.getElementById("wwRdDetailsBody");
    if (!body) return;
    if (!wwRdState.selectedGroupId) {
        body.innerHTML = '<p class="ww-rd-placeholder">Select a group to view details.</p>';
        return;
    }
    // Slice C will populate actual content here.
    body.innerHTML = '<p class="ww-rd-placeholder">Details coming in Slice C.</p>';
}
```

### 5.7 Event wiring (DOMContentLoaded block)

```js
// RD-1 Slice B: Recording Details page
document.getElementById("mainNavRecordingDetailsBtn").addEventListener("click", () => shellSetCurrentPage("recording-details"));

document.getElementById("wwRdSearch").addEventListener("input", (e) => {
    wwRdState.searchQuery = e.target.value;
    wwRdRenderBrowser();
});

document.getElementById("wwRdSort").addEventListener("change", (e) => {
    wwRdState.sortOrder = e.target.value;
    wwRdRenderBrowser();
});

document.getElementById("wwRdRecordingList").addEventListener("click", (e) => {
    const item = e.target.closest(".ww-rd-recording-item[data-source-id]");
    if (item) wwRdSelectSource(item.dataset.sourceId);
});
document.getElementById("wwRdRecordingList").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
        const item = e.target.closest(".ww-rd-recording-item[data-source-id]");
        if (item) { e.preventDefault(); wwRdSelectSource(item.dataset.sourceId); }
    }
});

document.getElementById("wwRdGroupsBody").addEventListener("click", (e) => {
    const item = e.target.closest(".ww-rd-group-item[data-group-id]");
    if (item) {
        wwRdState.selectedGroupId = item.dataset.groupId;
        wwRdRenderGroups();
        wwRdRenderDetails();
    }
});
document.getElementById("wwRdGroupsBody").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
        const item = e.target.closest(".ww-rd-group-item[data-group-id]");
        if (item) {
            e.preventDefault();
            wwRdState.selectedGroupId = item.dataset.groupId;
            wwRdRenderGroups();
            wwRdRenderDetails();
        }
    }
});

document.getElementById("wwRdUploadBtn").addEventListener("click", () => {
    // Reuse the existing upload trigger used by the Recordings page
    // (the same button function used by #recordingsUploadBtn).
    wwTriggerUpload();
});
```

**Note on `wwTriggerUpload()`:** The existing Recordings page upload button at `#recordingsUploadBtn` calls a function (find it by searching for `recordingsUploadBtn` click handler) — the same function should be called here. The exact function name must be confirmed at implementation time by reading that handler; `wwTriggerUpload()` is a placeholder name.

---

## 6. Files to Modify

**Only `frontend/index.html`.**  No other production file is touched in Slice B.

| Location | Change |
|---|---|
| `<style>` block (~line 569 vicinity) | Add new CSS block (§3) |
| Nav rail (~line 9789) | Insert `mainNavRecordingDetailsBtn` button |
| Icon hydration block | Add `PAGE_RECORDING_DETAILS` SVG entry |
| `~line 13505` (after `pageDataPreparation`) | Insert `<section id="pageRecordingDetails">` (§2.2) |
| `shellSetCurrentPage()` guard (~line 16317) | Add `"recording-details"` to whitelist |
| `shellSetCurrentPage()` body (~line 16328) | Add show/hide and `setShellNavCurrent` lines |
| `shellSetCurrentPage()` lifecycle block (~line 16413) | Add `wwRdOnPageEntered()` call |
| State section (~line 35802) | Add `wwRdState` const |
| JS functions section | Add `wwRdOnPageEntered`, `wwRdRefreshSources`, `wwRdRenderBrowser`, `wwRdSelectSource`, `wwRdRenderGroups`, `wwRdRenderDetails` |
| DOMContentLoaded listeners (~line 60111) | Add `mainNavRecordingDetailsBtn` click + all panel event wiring |

---

## 7. Regression Risks

| Risk | Mitigation |
|---|---|
| `shellSetCurrentPage` guard change — invalid page key accepted | The new key is an additive string literal; all 8 existing keys remain unchanged. Guard still rejects any other value. |
| `wwMgSelectedSourceId` / `wwMgEditState` contamination | `wwRdState` is a completely separate object declared with `const`. `wwFetchMeasurementGroupsForSource` is called with `wwRdState.selectedSourceId` and writes into `ww.measurementGroups` (the shared cache) — this is by design, same as the existing Measurement Groups modal. The only risk is a render triggered by `wwMgGroupsForSelectedSource()` which reads `ww.measurementGroups.get(wwMgSelectedSourceId)` — this is unaffected because it uses `wwMgSelectedSourceId` not `wwRdState.selectedSourceId`. |
| Upload trigger reuse — may refresh Recordings page but not Recording Details browser | `wwRdOnPageEntered()` / `wwRdRefreshSources()` refresh pattern. After upload completes, call `wwRdState.sources = null` to force re-fetch on next `wwRdOnPageEntered()`. Confirm the exact upload completion hook at implementation time. |
| New `<section>` hidden attribute — wrong default | `hidden` attribute present in HTML; `shellSetCurrentPage()` controls visibility. No CSS `display` rule applied directly to it (only `#pageRecordingDetails[hidden] { display: none; }` to match other page pattern). |
| Icon hydration — missing token | The hydration loop skips unknown tokens silently. Worst case: empty icon. Nav button still works. |

---

## 8. Proposed Acceptance Tests (Slice B)

Manual (Playwright test suite added in Slice E):

1. **Navigation**: Click "Recording Details" nav button — page shows, nav button has `aria-current="page"`, all other pages are hidden.
2. **State persistence**: Navigate away to Recordings and back — `searchQuery` and `sortOrder` state preserved; recording list not refetched.
3. **Recording browser — empty state**: Fresh workspace (no recordings) — "No recordings yet." placeholder shown.
4. **Recording browser — with recordings**: Upload one COMTRADE event, navigate to Recording Details — recording name appears in browser list.
5. **Search**: Type into search field — list filters immediately; clear field — list restores.
6. **Sort**: Change sort order — list reorders without a network call.
7. **Recording selection**: Click a recording row — row gets `aria-selected="true"` outline, groups panel loads (shows "Loading…" then group rows or "No measurement groups configured.").
8. **Keyboard selection**: Tab to recording row, press Enter — same behaviour as click.
9. **Groups panel selection**: Click a group row — row gets `aria-selected="true"`, details panel shows placeholder text.
10. **Upload button**: Click "Upload New" — same upload modal opens as on the Recordings page.
11. **No cross-contamination**: Open Measurement Groups modal (from waveform PU settings), change source — `wwRdState.selectedSourceId` unchanged.
12. **Waveform page unaffected**: Open Waveform page — no visible change, no JS errors.

---

## 9. Open Questions Before Implementation

1. **`wwTriggerUpload()` exact name**: Confirm the function called by `#recordingsUploadBtn` click handler (grep for `recordingsUploadBtn` click listener).
2. **Upload completion callback**: Confirm how the existing Recordings page clears/refreshes its source list after an upload completes — apply same mechanism to `wwRdState.sources = null` invalidation.
3. **`PAGE_RECORDING_DETAILS` SVG**: Identify where the existing icon-hydration block is and what SVG to use (a document-with-gear or document-with-list is appropriate).
4. **D3 (Waveform navigation)**: The owner approved including Waveform navigation in RD-1. The integration point (a button in the details panel that calls `shellSetCurrentPage("waveform")` and loads the selected recording) will be confirmed as part of Slice D scoping, not Slice B.

---

## 10. Slice B → Slice C Handoff

After Slice B is approved and implemented, Slice C will:
- Replace `wwRdRenderGroups()` stub with the full Group Details panel (read-only: voltage base, authority badge, channel list, `manual_conflict_detected` warning — closing the RD-0B frontend gap).
- Replace `wwRdRenderDetails()` stub with the full Group Details read-only view.
- No state structure or navigation changes are expected in Slice C.
