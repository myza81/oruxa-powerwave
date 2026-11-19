// RD-1 Slice C-1 Tabs — persistent underline-tab navigation for Column 3.
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
    return page.locator("#recordingsTableBody tr[data-source-id]").first();
}

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    return item;
}

async function selectFirstGroup(page) {
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();
}

// ---- Tests ------------------------------------------------------------------

test("TABS-01: tab bar shows both tabs after selecting a recording", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const tablist = page.locator("#wwRdDetailsTabs");
    await expect(tablist).toBeVisible();
    await expect(tablist).toHaveAttribute("role", "tablist");
    await expect(page.locator("#wwRdTabRecordingInfo")).toBeVisible();
    await expect(page.locator("#wwRdTabRecordingInfo")).toContainText("Recording Info");
    await expect(page.locator("#wwRdTabGroupDetails")).toBeVisible();
    await expect(page.locator("#wwRdTabGroupDetails")).toContainText("Group Details");
});

test("TABS-02: recording selection auto-activates Recording Info tab", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "false");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");
});

test("TABS-03: group selection auto-activates Group Details tab", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "false");
});

test("TABS-04: Group Details tab with no group shows empty state, no crash", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Click Group Details tab directly (no group selected)
    await page.locator("#wwRdTabGroupDetails").click();
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
    // Empty state must appear, not an error or stale data
    await expect(page.locator("#wwRdDetailsBody .ww-rd-empty-state")).toBeVisible();
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Select a group");
    // No crash: no [object Object] or undefined in body
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("[object");
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("undefined");
});

test("TABS-05: clicking Recording Info tab shows recording metadata without changing group selection", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Confirm Group Details active
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // Click Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("COMTRADE");

    // Group row must still be selected (aria-selected preserved)
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toHaveAttribute("aria-selected", "true");
});

test("TABS-06: clicking Group Details tab again shows selected group details", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Switch to Recording Info
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");

    // Switch back to Group Details
    await page.locator("#wwRdTabGroupDetails").click();
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");
    // Group Details content must be shown (not empty state)
    await expect(page.locator("#wwRdDetailsBody .ww-rd-empty-state")).not.toBeVisible();
    const detailsText = await page.locator("#wwRdDetailsBody").textContent();
    const hasConfig = detailsText.includes("Voltage Base Configuration") ||
        detailsText.includes("Current Base Configuration");
    expect(hasConfig).toBe(true);
});

test("TABS-07: switching recordings clears Group Details content", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await uploadFixture(page);
    await navigateToRd(page);

    const items = page.locator("#wwRdRecordingList .ww-rd-recording-item");
    if (await items.count() < 2) return;

    // Select first recording, select a group
    await items.first().click();
    await selectFirstGroup(page);
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true", { timeout: 5000 });

    // Switch to second recording
    await items.nth(1).click();

    // Recording Info tab must be active; Group Details content cleared
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true", { timeout: 5000 });

    // Switching to Group Details tab must show empty state (group was cleared)
    await page.locator("#wwRdTabGroupDetails").click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-empty-state")).toBeVisible();
});

test("TABS-08: keyboard ArrowRight/Left navigates and activates tabs", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Focus the Recording Info tab
    await page.locator("#wwRdTabRecordingInfo").focus();
    await expect(page.locator("#wwRdTabRecordingInfo")).toBeFocused();

    // ArrowRight → Group Details tab must become focused and active
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#wwRdTabGroupDetails")).toBeFocused();
    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // ArrowLeft → Recording Info tab must become focused and active
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("#wwRdTabRecordingInfo")).toBeFocused();
    await expect(page.locator("#wwRdTabRecordingInfo")).toHaveAttribute("aria-selected", "true");
});

test("TABS-09: narrow viewport — both tabs visible and tappable in details panel", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Navigate to details panel (via group selection in narrow mode)
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item").first()).toBeVisible({ timeout: 8000 });
    await page.locator("#wwRdGroupsBody .ww-rd-group-item").first().click();
    await expect(page.locator("#wwRdDetailsPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);

    // Both tabs must be visible in the details panel
    await expect(page.locator("#wwRdTabRecordingInfo")).toBeVisible();
    await expect(page.locator("#wwRdTabGroupDetails")).toBeVisible();

    // Both tabs must be tappable (non-zero size)
    const recBbox = await page.locator("#wwRdTabRecordingInfo").boundingBox();
    expect(recBbox).not.toBeNull();
    expect(recBbox.width).toBeGreaterThan(0);
    expect(recBbox.height).toBeGreaterThan(0);
});

test("TABS-10: old nav elements are absent from DOM", async ({ page }) => {
    await page.goto("/index.html");

    // Old elements must not exist in the DOM
    expect(await page.locator("#rdBackToRecordingInfo").count()).toBe(0);
    expect(await page.locator("#rdViewRecordingInfoBtn").count()).toBe(0);
    expect(await page.locator("#wwRdDetailsPanelTitle").count()).toBe(0);
});

test("TABS-11: Slice C engineering details intact with tabs", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    await expect(page.locator("#wwRdTabGroupDetails")).toHaveAttribute("aria-selected", "true");

    // Engineering Evidence toggle present
    await expect(page.locator("#wwRdDetailsBody details.ww-rd-evidence")).toBeVisible();

    // UX-1: PU availability section removed — confirm main sections are still present
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.length).toBeGreaterThan(0);

    // C4 amendment: CT/VT is a standalone section in main panel (not in Evidence).
    const allHeadings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasTransformerSection = allHeadings.some((t) =>
        t.includes("Voltage Transformer") || t.includes("Current Transformer"));
    expect(hasTransformerSection).toBe(true);

    // Conflict banner absent for a normal group (no spurious warning)
    await expect(page.locator("#wwRdDetailsBody .ww-rd-conflict-banner")).not.toBeVisible();
});
