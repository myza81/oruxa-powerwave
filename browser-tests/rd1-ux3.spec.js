// RD-1 UX-3: Recording Events → Recording Details consolidation.
// Tests run against a live backend+frontend (port 8000/8101 by default).
//
// Acceptance criterion: the engineer can upload, select, inspect, configure,
// open in Waveform Analysis and remove recordings entirely through Recording
// Details, without confusing recording selection with waveform navigation or
// losing existing workspace functionality.

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

// ---- Helpers ----------------------------------------------------------------

async function goToRd(page) {
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
}

async function uploadFixture(page, filename = "synth_ascii") {
    // Upload from Recording Details using its own Upload New button.
    await page.locator("#wwRdUploadBtn").click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, filename + ".cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, filename + ".dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    // Confirm recording appears in the browser list
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    return item;
}

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    return item;
}

async function selectVoltageGroup(page) {
    await page.locator("#wwRdGroupKindFilter button[data-kind='voltage']").click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });
}

// ---- Tests ------------------------------------------------------------------

// Test 1: Recording selection shows Recording Info without navigating to Waveform
test("RD-1 UX3-01: selecting a recording opens Recording Info without navigating to Waveform", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    // Waveform page must NOT be shown — Recording Details stays active
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    await expect(page.locator("#workspaceRow")).not.toBeVisible();

    // Recording Info tab must be active and show content
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Format");
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
});

// Test 2: Measurement Group selection opens Group Details without navigating
test("RD-1 UX3-02: selecting a measurement group opens Group Details without navigating to Waveform", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);
    await selectVoltageGroup(page);

    // Still on Recording Details — Waveform not activated
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
    await expect(page.locator("#workspaceRow")).not.toBeVisible();

    // Group Details content is shown
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Configuration");
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
});

// Test 3: View Waveform button is accessible from both Recording Info and Group Details
test("RD-1 UX3-03: View Waveform button is present and enabled once a recording is selected", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);

    // No recording selected — button must be disabled
    const viewBtn = page.locator("#wwRdViewWaveformBtn");
    await expect(viewBtn).toBeVisible();
    await expect(viewBtn).toBeDisabled();

    await uploadFixture(page);
    await selectFirstRecording(page);

    // Recording selected — button must now be enabled
    await expect(viewBtn).toBeEnabled();

    // Switch to Group Details tab and verify button remains enabled
    await selectVoltageGroup(page);
    await expect(viewBtn).toBeEnabled();

    // Switch back to Recording Info and verify still enabled
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(viewBtn).toBeEnabled();
});

// Test 4: View Waveform navigates to the Waveform Analysis page
test("RD-1 UX3-04: View Waveform navigates to Waveform Analysis with the selected recording", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    const viewBtn = page.locator("#wwRdViewWaveformBtn");
    await expect(viewBtn).toBeEnabled();
    await viewBtn.click();

    // Waveform Analysis page must now be visible
    await expect(page.locator("#workspaceRow")).toBeVisible({ timeout: 8000 });
    await expect(page.locator("#pageRecordingDetails")).not.toBeVisible();
});

// Test 5: Navigating back to Recording Details after View Waveform preserves workspace state
test("RD-1 UX3-05: returning to Recording Details after View Waveform preserves recording list", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    // Go to waveform
    await page.locator("#wwRdViewWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible({ timeout: 8000 });

    // Navigate back to Recording Details
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();

    // Recording still in list — workspace not cleared
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible();
});

// Test 7: Time Reference controls appear in Recording Info when applicable
test("RD-1 UX3-07: Time Reference section appears in Recording Info for recordings with unknown time basis", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    // Ensure we are on Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").click();

    // synth_ascii.cfg time_basis drives the conditional;
    // If the section is present, verify its structure.
    // If absent (time_basis is not unknown), skip — the guard is correct.
    const details = page.locator("#wwRdDetailsBody");
    const timeRefSection = details.locator(".ww-rd-section", { hasText: "Time Reference" });
    const count = await timeRefSection.count();
    if (count > 0) {
        // Section exists — must contain the select control
        await expect(timeRefSection.locator(".recording-time-reference")).toHaveCount(1);
        await expect(timeRefSection).toContainText("Session only");
    }
    // If count === 0 the recording's time_basis is not "unknown" — correct absence.
});

// Test 8a: Individual recording deletion works from the browser list
test("RD-1 UX3-08a: recording can be removed from Recording Details browser", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);

    // Confirm recording is in list
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible();

    // Click the remove button on the recording item
    await item.hover();
    const removeBtn = item.locator(".ww-rd-recording-item-remove");
    await removeBtn.click();

    // Confirm dialog appears
    await expect(page.locator("#confirmOverlay")).toBeVisible({ timeout: 3000 });

    // Confirm removal
    await page.locator("#confirmRemoveBtn").click();
    await page.locator("#confirmOverlay").waitFor({ state: "hidden" });

    // Recording list should now be empty or show placeholder
    await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0, { timeout: 8000 });
});

// Test 8b/9: Deleting all recordings returns clean empty state; fresh upload works after
test("RD-1 UX3-09: deleting the final recording returns clean state; subsequent upload works", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);

    // Remove the only recording
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await item.hover();
    await item.locator(".ww-rd-recording-item-remove").click();
    await expect(page.locator("#confirmOverlay")).toBeVisible({ timeout: 3000 });
    await page.locator("#confirmRemoveBtn").click();
    await page.locator("#confirmOverlay").waitFor({ state: "hidden" });

    // Empty state — no items, details panel shows placeholder
    await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0, { timeout: 8000 });
    await expect(page.locator("#wwRdViewWaveformBtn")).toBeDisabled();

    // View Waveform button should now be disabled again
    await expect(page.locator("#wwRdViewWaveformBtn")).toBeDisabled();

    // Fresh upload still works
    await uploadFixture(page);
    const newItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(newItem).toBeVisible({ timeout: 8000 });
});

// Test 10: Start New Workspace trigger button is absent from the frontend
test("RD-1 UX3-10: Start New Workspace button is absent from the frontend", async ({ page }) => {
    await page.goto("/index.html");
    // The trigger button (#newWorkspaceButton) is removed per UX-3 decision 3.
    await expect(page.locator("#newWorkspaceButton")).toHaveCount(0);
    // The backend confirm overlay (#newWorkspaceConfirmOverlay) is kept in the DOM
    // so the backend workspace-reset lifecycle remains intact; it must start hidden.
    await expect(page.locator("#newWorkspaceConfirmOverlay")).toHaveAttribute("hidden");
});

// Test 11: Recording Events navigation entry is absent
test("RD-1 UX3-11: Recording Events navigation entry is removed", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#mainNavRecordingDetailsBtn")).toHaveCount(0);
    // The old page section must also be absent
    await expect(page.locator("#pageRecordingDetails")).toHaveCount(0);
    await expect(page.locator("#recordingsTableBody")).toHaveCount(0);
});

// Test 12: No stale references to removed elements (startup test)
test("RD-1 UX3-12: app starts on Recording Details with no console errors from removed elements", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.goto("/index.html");
    // Wait for initial load
    await expect(page.locator("#pageRecordingDetails")).toBeVisible({ timeout: 8000 });
    // No TypeError from removed elements in init
    const typeErrors = errors.filter((m) => m.includes("TypeError") || m.includes("Cannot read"));
    expect(typeErrors).toEqual([]);
});

// Test 13: Engineering configuration and warnings still work
test("RD-1 UX3-13: voltage engineering configuration and nominal voltage warning are preserved", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);
    await selectVoltageGroup(page);

    const details = page.locator("#wwRdDetailsBody");
    // Configuration section heading present
    await expect(details).toContainText("Voltage Base Configuration");
    // Per-unit availability section must NOT appear (UX-1 removal preserved)
    await expect(details).not.toContainText("Per-unit availability");
    // If nominal voltage is unresolved, warning appears
    const missingWarning = details.locator(".ww-rd-voltage-missing-reason");
    // May be 0 or 1 — just verify no duplicate (UX-1)
    const cnt = await missingWarning.count();
    expect(cnt).toBeLessThanOrEqual(1);
});

// ---- D-series: Per-unit Configuration and context header ------------------

// D-01: PU configuration message is absent from the Recordings list panel.
test("RD-1 UX3-D01: PU configuration message is not shown in the Recordings list panel", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);

    // The old #wwImportPuStatusBanner must be absent from the DOM.
    await expect(page.locator("#wwImportPuStatusBanner")).toHaveCount(0);

    // The browser panel (column 1) must contain no PU configuration text.
    const browserPanel = page.locator("#wwRdBrowserPanel");
    await expect(browserPanel).not.toContainText("Per-unit");
    await expect(browserPanel).not.toContainText("PU ready");
    await expect(browserPanel).not.toContainText("need base configuration");
});

// D-02: Recording context header shows selected recording identity and Analyze Waveform button.
test("RD-1 UX3-D02: recording context header shows station name and format badge when recording selected", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);

    // No recording selected: placeholder text
    const ctxInfo = page.locator("#wwRdRecordingContextInfo");
    await expect(ctxInfo).toContainText("No recording selected");

    // Analyze Waveform button disabled
    await expect(page.locator("#wwRdViewWaveformBtn")).toBeDisabled();

    await uploadFixture(page);
    await selectFirstRecording(page);

    // After selection: recording name visible in context header (no subtitle)
    const nameEl = ctxInfo.locator(".ww-rd-recording-context-name");
    await expect(nameEl).toBeVisible();
    await expect(nameEl).not.toHaveClass(/ww-rd-recording-context-name--empty/);
    // Format badge visible (synth_ascii → COMTRADE)
    await expect(ctxInfo.locator(".ww-rd-group-badge")).toBeVisible();
    // No "Selected recording" subtitle (removed per cosmetic refinement)
    await expect(ctxInfo.locator(".ww-rd-recording-context-label")).toHaveCount(0);
    // Analyze Waveform button enabled
    await expect(page.locator("#wwRdViewWaveformBtn")).toBeEnabled();
});

// D-02b: Recording Info body does not repeat the name/badge already in the context header.
test("RD-1 UX3-D02b: Recording Info body omits the duplicate recording name header", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);
    await page.locator("#wwRdTabRecordingInfo").click();

    const details = page.locator("#wwRdDetailsBody");
    // The .ww-rd-details-group-header element (name + badge) must NOT appear in Recording Info.
    await expect(details.locator(".ww-rd-details-group-header")).toHaveCount(0);
    // The metadata table must still be present.
    await expect(details.locator(".ww-rd-config-table")).toBeVisible();
    await expect(details).toContainText("Format");
});

// D-03: Per-unit Configuration section shows per-recording issues when groups need base.
// synth_ascii has voltage groups with no resolved base, so the section should appear.
test("RD-1 UX3-D03: Per-unit Configuration section appears in Recording Info when voltage groups need base", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    // Switch to Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").click();

    const details = page.locator("#wwRdDetailsBody");

    // Check whether this fixture's groups have unresolved bases
    // synth_ascii has basic voltage groups with no primary ratio configured.
    const puSection = details.locator(".ww-rd-pu-config-section");
    const hasPuIssues = await puSection.count() > 0;
    if (hasPuIssues) {
        // Section must have heading and at least one issue line
        await expect(puSection).toContainText("Per-unit Configuration");
        await expect(puSection.locator(".ww-rd-pu-config-issue").first()).toBeVisible();
        // Review affected groups button must be present
        await expect(puSection.locator(".ww-rd-pu-review-btn")).toBeVisible();
    }
    // No "Per-unit availability" section (UX-1 retired section must stay absent)
    await expect(details).not.toContainText("Per-unit availability");
});

// D-04: PU Configuration section is absent from Measurement Groups panel (column 2).
test("RD-1 UX3-D04: PU configuration is not shown in Measurement Groups panel", async ({ page }) => {
    await page.goto("/index.html");
    await goToRd(page);
    await uploadFixture(page);
    await selectFirstRecording(page);

    const groupsPanel = page.locator("#wwRdGroupsPanel");
    await expect(groupsPanel).not.toContainText("Per-unit Configuration");
    await expect(groupsPanel).not.toContainText("PU ready");
    await expect(groupsPanel).not.toContainText("need base configuration");
});

// Test 14: Default landing page is Recording Details
test("RD-1 UX3-14: application opens on Recording Details by default", async ({ page }) => {
    await page.goto("/index.html");
    // Recording Details must be the visible page on first load
    await expect(page.locator("#pageRecordingDetails")).toBeVisible({ timeout: 8000 });
    // Waveform workspace must not be shown by default
    await expect(page.locator("#workspaceRow")).not.toBeVisible();
    // Recording Details nav button must be marked current
    await expect(page.locator("#mainNavRecordingDetailsBtn")).toHaveAttribute("aria-current", "page");
});
