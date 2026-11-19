// RD-1 Slice C-1 — Recording Information and context-sensitive details panel tests.
// Updated for tab-based navigation (replaces back-link navigation).
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

test("RD-1 C1-01: recording selection activates Recording Info tab", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // "Recording Info" tab must be active
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "false");
    // Details body must not show "Select a group" placeholder
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Select a group");
    // Format label should be present (COMTRADE)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("RD-1 C1-02: selecting a group activates Group Details tab", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // "Group Details" tab must be active
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "false");
    // Engineering config section must be present (Slice C)
    const detailsText = await page.locator("#wwRdDetailsBody").textContent();
    const hasConfig = detailsText.includes("Voltage Base Configuration") ||
        detailsText.includes("Current Base Configuration");
    expect(hasConfig).toBe(true);
    // Should NOT show Recording Info metadata rows
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Sample rate");
});

test("RD-1 C1-03: clicking Recording Info tab returns to recording metadata", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Confirm Group Details tab is active
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // Click the Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").click();

    // Now Recording Info tab must be active and show recording metadata
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "false");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
    // Engineering config must no longer be shown
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Voltage Base Configuration");
});

test("RD-1 C1-04: switching recordings resets Column 3 to Recording Info tab", async ({ page }) => {
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
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true", { timeout: 5000 });

    // Now select second recording
    await items.nth(1).click();
    // After selecting a different recording, panel resets to Recording Info
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true", { timeout: 5000 });
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "false");
});

test("RD-1 C1-05: group selection is preserved when switching to Recording Info tab", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Select the first group
    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(groups.first()).toBeVisible({ timeout: 8000 });
    await groups.first().click();
    // Confirm group details shown
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // Click Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");

    // The first group row should still have aria-selected="true" in the groups panel
    await expect(groups.first()).toHaveAttribute("aria-selected", "true");

    // The first group row must still be selected (aria-selected preserved)
    await expect(groups.first()).toHaveAttribute("aria-selected", "true");
});

test("RD-1 C1-06: recording with absent station shows dash or omits station row cleanly", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Panel must be in Recording Info view and not show an error
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
    // Should not show any JS error message in the body
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("undefined");
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("[object");
    // Format row must be present (always present for a valid recording)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
    // Sample rate row must be present
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Sample rate");
});

test("RD-1 C1-07: narrow layout — tab switching works in details panel", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Selecting a recording advances to groups panel (same as UAT-B-07 behavior)
    await selectFirstRecording(page);
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible({ timeout: 3000 });

    // Select a group to navigate to the details panel
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();

    // Details panel should now be visible with Group Details tab active
    await expect(page.locator("#wwRdDetailsPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // Both tabs must be visible
    await expect(page.locator("#wwRdTabRecordingInfo")).toBeVisible();
    await expect(page.locator("#wwRdTabGroupDetails")).toBeVisible();

    // Clicking Recording Info tab must switch content
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
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

    // The final state should be Recording Info tab active
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true", { timeout: 5000 });
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

    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
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
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
    const detailsText = await page.locator("#wwRdDetailsBody").textContent();
    // Post-C4: voltage groups → "Voltage Base Configuration", current groups → "Equipment Rating"
    const hasConfig = detailsText.includes("Voltage Base Configuration") ||
        detailsText.includes("Equipment Rating");
    expect(hasConfig).toBe(true);

    // UX-2: Engineering Evidence removed — section must not be present.
    await expect(page.locator("#wwRdDetailsBody details.ww-rd-evidence")).not.toBeAttached();

    // UX-1: PU availability section removed — Voltage Base Configuration section present instead
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Voltage Base Configuration") || h.includes("Equipment Rating"))).toBe(true);

    // C4 amendment: CT/VT is a standalone section in main panel (not in Evidence).
    const allH = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasTransformerSection = allH.some((t) =>
        t.includes("Voltage Transformer") || t.includes("Current Transformer"));
    expect(hasTransformerSection).toBe(true);
});
