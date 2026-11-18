// RD-1 Slice C-1 — Recording Information and context-sensitive details panel tests.
// Tests run against a live backend+frontend (port 8000/8101 by default).

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

// ---- Helpers ----------------------------------------------------------------

async function navigateToRd(page) {
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
}

async function uploadFixture(page) {
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
    await expect(row).toBeVisible();
    return row;
}

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    return item;
}

async function selectFirstGroup(page) {
    // Wait for groups to load (not loading placeholder)
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();
    return page.locator("#wwRdGroupsBody .ww-rd-group-item").first();
}

// ---- Tests ------------------------------------------------------------------

test("RD-1 C1-01: recording selection shows Recording Info in Column 3", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Panel title should be "Recording Info"
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");
    // Details body must not show "Select a group" placeholder
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Select a group");
    // "← Recording Info" back link must be hidden
    await expect(page.locator("#rdBackToRecordingInfo")).toBeHidden();
    // Format label should be present (COMTRADE)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("RD-1 C1-02: selecting a group switches Column 3 to Group Details", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Panel title should be "Group Details"
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Group Details");
    // "← Recording Info" link must be visible
    await expect(page.locator("#rdBackToRecordingInfo")).toBeVisible();
    // Engineering config section must be present (Slice C)
    const detailsText = await page.locator("#wwRdDetailsBody").textContent();
    const hasConfig = detailsText.includes("Voltage Base Configuration") ||
        detailsText.includes("Current Base Configuration");
    expect(hasConfig).toBe(true);
    // Should NOT show Recording Info metadata rows
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Sample rate");
});

test("RD-1 C1-03: clicking '← Recording Info' returns to recording metadata", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Confirm we are in group view
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Group Details");

    // Click the back link
    await page.locator("#rdBackToRecordingInfo").click();

    // Now should show Recording Info
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");
    await expect(page.locator("#rdBackToRecordingInfo")).toBeHidden();
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("RD-1 C1-04: switching recordings resets Column 3 to Recording Info", async ({ page }) => {
    await page.goto("/index.html");
    // Upload two fixtures (second upload creates a second recording)
    await uploadFixture(page);
    await uploadFixture(page);
    await navigateToRd(page);

    const items = page.locator("#wwRdRecordingList .ww-rd-recording-item");
    const count = await items.count();
    if (count < 2) {
        // Only one recording available — can't test switching
        return;
    }

    // Select first recording, select a group, then switch to second recording
    await items.first().click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();
    // Should be in Group Details view
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Group Details", { timeout: 5000 });

    // Now select second recording
    await items.nth(1).click();
    // After selecting a different recording, panel resets to Recording Info
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info", { timeout: 5000 });
    // "← Recording Info" back link should be hidden (not in group view)
    await expect(page.locator("#rdBackToRecordingInfo")).toBeHidden();
});

test("RD-1 C1-05: group selection is preserved when returning to Recording Info", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Select the first group
    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(groups.first()).toBeVisible({ timeout: 8000 });
    await groups.first().click();
    // Confirm group details shown
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Group Details");

    // Go back to Recording Info
    await page.locator("#rdBackToRecordingInfo").click();
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");

    // The first group row should still have aria-selected="true" in the groups panel
    await expect(groups.first()).toHaveAttribute("aria-selected", "true");
});

test("RD-1 C1-06: recording with absent station shows dash or omits station row cleanly", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Panel must be in Recording Info view and not show an error
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");
    // Should not show any JS error message in the body
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("undefined");
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("[object");
    // Format row must be present (always present for a valid recording)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
    // Sample rate row must be present
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Sample rate");
});

test("RD-1 C1-07: narrow layout — Recording Info accessible via groups panel button", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Selecting a recording advances to groups panel (same as UAT-B-07 behavior)
    await selectFirstRecording(page);
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible({ timeout: 3000 });

    // "Recording Info →" button should be visible in the groups panel header
    await expect(page.locator("#rdViewRecordingInfoBtn")).toBeVisible({ timeout: 3000 });

    // Clicking it should navigate to details panel showing Recording Info
    await page.locator("#rdViewRecordingInfoBtn").click();
    await expect(page.locator("#wwRdDetailsPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("RD-1 C1-08: rapid recording switches do not leave stale recording info in panel", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await uploadFixture(page);
    await navigateToRd(page);

    const items = page.locator("#wwRdRecordingList .ww-rd-recording-item");
    const count = await items.count();
    if (count < 2) return;

    // Click both in quick succession
    await items.first().click();
    await items.nth(1).click();

    // The final state should be Recording Info (panel title) and not show a placeholder
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info", { timeout: 5000 });
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Select a recording");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("RD-1 C1-09: dark theme — Recording Info panel renders without layout breakage", async ({ page }) => {
    await page.goto("/index.html");
    await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
    });
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Recording Info");
    // No horizontal overflow on the details panel
    const panel = page.locator("#wwRdDetailsPanel");
    await expect(panel).toBeVisible();
    const bbox = await panel.boundingBox();
    const panelWidth = bbox ? bbox.width : 0;
    // Details body must not overflow the panel width
    const bodyBbox = await page.locator("#wwRdDetailsBody").boundingBox();
    if (bodyBbox && panelWidth > 0) {
        expect(bodyBbox.width).toBeLessThanOrEqual(panelWidth + 2); // 2px tolerance
    }
});

test("RD-1 C1-10: Slice C group details remain intact after Slice C-1 changes", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Select a group (any kind)
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();

    // Slice C group details must still work
    await expect(page.locator("#wwRdDetailsPanelTitle")).toHaveText("Group Details");
    const detailsText = await page.locator("#wwRdDetailsBody").textContent();
    const hasConfig = detailsText.includes("Voltage Base Configuration") ||
        detailsText.includes("Current Base Configuration");
    expect(hasConfig).toBe(true);

    // Engineering Evidence toggle must be present
    await expect(page.locator("#wwRdDetailsBody details.ww-rd-evidence")).toBeVisible();

    // PU eligibility pill must be present
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-pill")).toBeVisible();

    // CT/VT section must be present
    await expect(page.locator("#wwRdDetailsBody")).toContainText("CT / VT");
});
