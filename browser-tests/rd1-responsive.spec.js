// RD-1 Slice B UAT-B-06/07 — compact group rows and responsive layout.
// Tests run on a fresh backend workspace per the shared workspaceCleanup fixture.

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

// ---- Helpers ----------------------------------------------------------------

async function navigateToRd(page) {
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#pageRecordingDetails")).toBeVisible();
}

async function uploadFixture(page) {
    await page.locator("#wwRdUploadBtn").click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    return item;
}

// ---- Tests ------------------------------------------------------------------

test("RD-1 B-06: group rows are single-line — no .ww-rd-group-subline in DOM", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Select the uploaded recording so groups load
    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();

    // Wait for groups to load (placeholder text disappears)
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });

    // UAT-B-06: no subline element should exist in group rows
    const sublines = page.locator("#wwRdGroupsBody .ww-rd-group-subline");
    await expect(sublines).toHaveCount(0);

    // Each group row must have a name span and a badge span
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    for (let i = 0; i < rowCount; i++) {
        const row = rows.nth(i);
        await expect(row.locator(".ww-rd-group-name")).toBeVisible();
        await expect(row.locator(".ww-rd-group-badge")).toBeVisible();
        // Badge must be V or I (synth_ascii has voltage and current groups)
        const badgeText = await row.locator(".ww-rd-group-badge").textContent();
        expect(["V", "I"]).toContain(badgeText.trim());
    }
});

test("RD-1 B-06: group row height is compact (≤40px)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });

    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    const bbox = await rows.first().boundingBox();
    expect(bbox.height).toBeLessThanOrEqual(40);
});

test("RD-1 B-06: filter buttons work after compact-row change", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });

    const allCount = await page.locator("#wwRdGroupsBody .ww-rd-group-item").count();
    expect(allCount).toBeGreaterThan(0);

    // Click Voltage filter
    await page.locator("#wwRdGroupKindFilter button[data-kind='voltage']").click();
    await expect(page.locator("#wwRdGroupKindFilter button[data-kind='voltage']")).toHaveAttribute("aria-pressed", "true");
    const voltageRows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const voltageCount = await voltageRows.count();
    if (voltageCount > 0) {
        for (let i = 0; i < voltageCount; i++) {
            const badge = await voltageRows.nth(i).locator(".ww-rd-group-badge").textContent();
            expect(badge.trim()).toBe("V");
        }
    }

    // Reset to All
    await page.locator("#wwRdGroupKindFilter button[data-kind='all']").click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-group-item")).toHaveCount(allCount);
});

test("RD-1 B-07: wide layout (1366×768) — all three panels visible simultaneously", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await navigateToRd(page);

    await expect(page.locator("#wwRdBrowserPanel")).toBeVisible();
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible();
    await expect(page.locator("#wwRdDetailsPanel")).toBeVisible();

    // No panel should have the narrow-hidden class
    await expect(page.locator("#wwRdBrowserPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);
    await expect(page.locator("#wwRdGroupsPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);
    await expect(page.locator("#wwRdDetailsPanel")).not.toHaveClass(/ww-rd-narrow-hidden/);
});

test("RD-1 B-07: wide layout has no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await navigateToRd(page);

    const hasHScroll = await page.evaluate(() => {
        const layout = document.querySelector(".ww-rd-layout");
        return layout ? layout.scrollWidth > layout.clientWidth : false;
    });
    expect(hasHScroll).toBe(false);
});

test("RD-1 B-07: medium layout (1024×768) — no horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/index.html");
    await navigateToRd(page);

    // All panels should still be visible (grid layout, not hidden)
    await expect(page.locator("#wwRdBrowserPanel")).toBeVisible();
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible();
    await expect(page.locator("#wwRdDetailsPanel")).toBeVisible();

    const hasHScroll = await page.evaluate(() => {
        const layout = document.querySelector(".ww-rd-layout");
        return layout ? layout.scrollWidth > layout.clientWidth : false;
    });
    expect(hasHScroll).toBe(false);
});

test("RD-1 B-07: narrow layout (390×844) — only one panel visible at a time", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await navigateToRd(page);

    // Initially: browser panel visible, others hidden
    await expect(page.locator("#wwRdBrowserPanel")).toBeVisible();
    await expect(page.locator("#wwRdGroupsPanel")).toBeHidden();
    await expect(page.locator("#wwRdDetailsPanel")).toBeHidden();

    // Back button in groups panel should be in DOM (even if panel hidden)
    await expect(page.locator("#rdBackToRecordings")).toBeAttached();
    await expect(page.locator("#rdBackToGroups")).toBeAttached();
});

test("RD-1 B-07: narrow layout navigation — recording selection shows groups panel with back button", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Wait for recording list to populate
    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });

    // Select a recording — should advance to groups panel
    await recItem.click();
    await expect(page.locator("#wwRdBrowserPanel")).toBeHidden({ timeout: 3000 });
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible();
    await expect(page.locator("#wwRdDetailsPanel")).toBeHidden();

    // Back button should be visible in the groups panel
    await expect(page.locator("#rdBackToRecordings")).toBeVisible();
});

test("RD-1 B-07: narrow layout back navigation returns to recordings panel", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();

    // Now on groups panel
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible({ timeout: 3000 });

    // Click back button
    await page.locator("#rdBackToRecordings").click();

    // Should return to browser panel
    await expect(page.locator("#wwRdBrowserPanel")).toBeVisible();
    await expect(page.locator("#wwRdGroupsPanel")).toBeHidden();
});

test("RD-1 B-07: selection state preserved when back-navigating in narrow layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const recItem = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(recItem).toBeVisible({ timeout: 8000 });
    await recItem.click();

    // Now on groups panel — selection is active
    await expect(page.locator("#wwRdGroupsPanel")).toBeVisible({ timeout: 3000 });

    // Navigate back to recordings panel
    await page.locator("#rdBackToRecordings").click();
    await expect(page.locator("#wwRdBrowserPanel")).toBeVisible();

    // The previously selected recording row should still be aria-selected="true"
    await expect(recItem).toHaveAttribute("aria-selected", "true");
});
