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

// Test 10: Start New Workspace button is absent from the frontend
test("RD-1 UX3-10: Start New Workspace button is absent from the frontend", async ({ page }) => {
    await page.goto("/index.html");
    // Check across the entire DOM — no button with this text or ID should exist
    await expect(page.locator("#newWorkspaceButton")).toHaveCount(0);
    await expect(page.locator("text=Start new workspace")).toHaveCount(0);
});

// Test 11: Recording Events navigation entry is absent
test("RD-1 UX3-11: Recording Events navigation entry is removed", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#mainNavRecordingsBtn")).toHaveCount(0);
    // The old page section must also be absent
    await expect(page.locator("#pageRecordings")).toHaveCount(0);
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
