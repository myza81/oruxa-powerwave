// RD-1 Slice C — Read-only engineering Group Details panel tests.
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
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    return item;
}

async function selectGroupByKind(page, kind) {
    // kind: "voltage" | "current"
    if (kind !== "all") {
        await page.locator(`#wwRdGroupKindFilter button[data-kind='${kind}']`).click();
    }
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });
    return rows.first();
}

// ---- Tests ------------------------------------------------------------------

test("RD-1 C-01: voltage group details — Voltage Base Configuration section is shown", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Select a voltage group
    await page.locator("#wwRdGroupKindFilter button[data-kind='voltage']").click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count === 0) {
        // No voltage groups in this fixture — skip gracefully
        return;
    }
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Voltage Base Configuration section must be present
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Voltage Base Configuration");
    // No "Details coming in Slice C" stub text
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Slice C");
});

test("RD-1 C-02: current group details — Current Base Configuration section is shown", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    await page.locator("#wwRdGroupKindFilter button[data-kind='current']").click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count === 0) {
        return;
    }
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Current Base Configuration section must be present (not Voltage Base)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Current Base Configuration");
    // Must NOT show Voltage Base section for a current group
    const titles = page.locator("#wwRdDetailsBody .ww-rd-details-section-title");
    const allTitles = await titles.allTextContents();
    const hasVoltageSection = allTitles.some((t) => t.toLowerCase().includes("voltage base configuration"));
    expect(hasVoltageSection).toBe(false);
});

test("RD-1 C-03: group identity header shows name, badge, and channel list", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Group name in header
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name")).toBeVisible();
    // Badge (V or I)
    const badge = page.locator("#wwRdDetailsBody .ww-rd-group-badge").first();
    await expect(badge).toBeVisible();
    const badgeText = await badge.textContent();
    expect(["V", "I"]).toContain(badgeText.trim());
    // Channel count line
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-channels")).toBeVisible();
    const channelText = await page.locator("#wwRdDetailsBody .ww-rd-details-channels").textContent();
    expect(channelText).toMatch(/\d+ channel/);
});

test("RD-1 C-04: PU eligible badge shown for configured voltage group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Try to find a voltage group that is PU-configured (pu_status === "configured")
    await page.locator("#wwRdGroupKindFilter button[data-kind='voltage']").click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count === 0) return;

    for (let i = 0; i < count; i++) {
        await rows.nth(i).click();
        await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 3000 });
        const eligible = page.locator("#wwRdDetailsBody .ww-rd-pu-eligible");
        const isEligible = await eligible.count();
        if (isEligible > 0) {
            // Found a configured group — verify badge shows "Eligible"
            await expect(eligible.first()).toContainText("Eligible");
            return;
        }
    }
    // If no configured voltage group found, verify at least a pill is shown
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-pill")).toBeVisible();
});

test("RD-1 C-05: no conflict banner for ordinary auto-resolved base", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    await page.locator("#wwRdGroupKindFilter button[data-kind='voltage']").click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count === 0) return;

    // Check each voltage group — if it has no conflict icon in the list,
    // its details panel should show no conflict banner
    for (let i = 0; i < count; i++) {
        const row = rows.nth(i);
        const hasConflictIcon = await row.locator(".ww-rd-group-conflict").count();
        if (hasConflictIcon === 0) {
            await row.click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 3000 });
            // No conflict banner should appear
            await expect(page.locator("#wwRdDetailsBody .ww-rd-conflict-banner")).toHaveCount(0);
            return;
        }
    }
});

test("RD-1 C-06: Engineering Evidence section is present and toggleable", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Evidence details element is present
    const evidenceEl = page.locator("#wwRdDetailsBody details.ww-rd-evidence");
    await expect(evidenceEl).toBeAttached();

    // Summary is visible
    const summary = evidenceEl.locator("summary");
    await expect(summary).toBeVisible();
    await expect(summary).toContainText("Engineering Evidence");

    // Closed by default: body not expanded
    const isOpen = await evidenceEl.evaluate((el) => el.open);
    expect(isOpen).toBe(false);

    // Click to open
    await summary.click();
    const isNowOpen = await evidenceEl.evaluate((el) => el.open);
    expect(isNowOpen).toBe(true);

    // Body content is visible
    await expect(evidenceEl.locator(".ww-rd-evidence-body")).toBeVisible();
});

test("RD-1 C-07: CT/VT section shows Not configured", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // CT/VT section must appear
    const titles = await page.locator("#wwRdDetailsBody .ww-rd-details-section-title").allTextContents();
    const hasCTVT = titles.some((t) => t.match(/CT\s*\/\s*VT/i));
    expect(hasCTVT).toBe(true);

    // Values must show "Not configured"
    const notConfigured = page.locator("#wwRdDetailsBody .ww-rd-not-configured");
    await expect(notConfigured.first()).toBeVisible();
    const notConfigText = await notConfigured.first().textContent();
    expect(notConfigText).toContain("Not configured");
});

test("RD-1 C-08: group switching — details update to new group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count < 2) return;

    // Select first group
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });
    const firstName = await page.locator("#wwRdDetailsBody .ww-rd-details-group-name").textContent();

    // Select second group
    await rows.nth(1).click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 3000 });
    const secondName = await page.locator("#wwRdDetailsBody .ww-rd-details-group-name").textContent();

    // Names should differ (groups are different)
    expect(firstName).not.toBe(secondName);
});

test("RD-1 C-09: selecting a recording clears the details panel", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Now select the same recording again (re-click it in the browser panel)
    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await recItem.click();
    // After selecting a source, selectedGroupId is cleared and details shows placeholder
    // (groups reload, but group selection is lost)
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).toBeVisible({ timeout: 5000 });
});

test("RD-1 C-10: details panel renders without layout breakage in dark theme", async ({ page }) => {
    await page.goto("/index.html");
    // Switch to dark theme
    await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("ww-theme", "dark"); } catch (e) {}
    });

    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });

    // Panel should not overflow horizontally
    const hasOverflow = await page.evaluate(() => {
        const body = document.getElementById("wwRdDetailsBody");
        return body ? body.scrollWidth > body.clientWidth + 1 : false;
    });
    expect(hasOverflow).toBe(false);

    // Key elements visible
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name")).toBeVisible();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-pill")).toBeVisible();
});

test("RD-1 C-11: narrow layout — selecting group navigates to details panel with content", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Select recording (narrow: advances to groups panel)
    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });

    // Select a group (narrow: advances to details panel)
    const groupRows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(groupRows.first()).toBeVisible({ timeout: 5000 });
    await groupRows.first().click();
    await expect(page.locator("#wwRdDetailsPanel")).toBeVisible({ timeout: 3000 });

    // Details content visible
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-pill")).toBeVisible();

    // Back button visible
    await expect(page.locator("#rdBackToGroups")).toBeVisible();
});
