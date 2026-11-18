// RD-1 Slice C-3: Group Details visual design regression tests.
// Verifies new section structure, two-column field grid, PU status line,
// CT/VT moved into Engineering Evidence, and "Not resolved" for null values.

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

async function selectFirstGroup(page) {
    const group = page.locator("#wwRdGroupsBody .ww-rd-group-item").first();
    await expect(group).toBeVisible({ timeout: 5000 });
    await group.click();
    // Wait for details panel to show group content (new .ww-rd-section structure)
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

async function selectGroupByKind(page, kind) {
    await page.locator(`#wwRdGroupKindFilter button[data-kind='${kind}']`).click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
    return rows.first();
}

// ---- Tests ------------------------------------------------------------------

test("C3-01: group name visible and channels as dot-separated list with count prefix", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Group name present
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name").first()).toBeVisible();
    // Channel list present and uses · separator with count prefix
    const ch = page.locator("#wwRdDetailsBody .ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    // Should use "N channels: Ch1 · Ch2" or "No channels assigned"
    expect(chText.includes("·") || chText.includes("No channels assigned") || /\d+ channel/.test(chText)).toBeTruthy();
});

test("C3-02: voltage group shows Nominal voltage (L-L) label and Not resolved or value", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
            const hasNomLabel = labels.some(l => l.includes("Nominal voltage"));
            expect(hasNomLabel).toBeTruthy();
            // Value is either a kV string or "Not resolved"
            const values = await page.locator("#wwRdDetailsBody .ww-rd-field-value").allTextContents();
            const hasValue = values.some(v => v.includes("kV") || v.includes("Not resolved"));
            expect(hasValue).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found in test recording");
});

test("C3-03: two-column grid has Voltage reference label alongside Nominal voltage", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-field-grid").first()).toBeVisible({ timeout: 5000 });
            const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
            const hasVRef = labels.some(l => l.includes("Voltage reference"));
            expect(hasVRef).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C3-04: Configuration source field present in Base Configuration section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
    const hasConfigSrc = labels.some(l => l.includes("Configuration source"));
    expect(hasConfigSrc).toBeTruthy();
});

test("C3-05: Per-unit availability section present with status word and reason paragraph", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Section heading
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasPuHeading = headings.some(h => h.includes("Per-unit availability"));
    expect(hasPuHeading).toBeTruthy();
    // Status line icon+word
    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line").first();
    await expect(statusLine).toBeVisible();
    const statusText = await statusLine.textContent();
    // Contains one of the known status words
    const knownWords = ["Available", "Unavailable", "Blocked", "Review required", "Not applicable"];
    expect(knownWords.some(w => statusText.includes(w))).toBeTruthy();
});

test("C3-06: Available state shows checkmark and green-class word (not inside a pill badge)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        await groups.nth(i).click();
        await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
        const statusText = await page.locator("#wwRdDetailsBody .ww-rd-pu-status-line").first().textContent().catch(() => "");
        if (statusText.includes("Available")) {
            // Status word must be shown via .ww-rd-pu-word--eligible (not inside a .ww-rd-pu-pill)
            const eligibleWord = page.locator("#wwRdDetailsBody .ww-rd-pu-word--eligible");
            await expect(eligibleWord).toBeVisible();
            // Must NOT be inside a .ww-rd-pu-pill in the PU section
            const pillCount = await page.locator("#wwRdDetailsBody .ww-rd-pu-pill .ww-rd-pu-word--eligible").count();
            expect(pillCount).toBe(0);
            return;
        }
    }
    test.skip(true, "No Available group found in test recordings");
});

test("C3-07: Conflict group shows Blocked (not full sentence as status word)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        // Check for conflict badge on group row
        const hasConflict = await groups.nth(i).locator(".ww-rd-group-conflict").count();
        if (hasConflict > 0) {
            await groups.nth(i).click();
            const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
            await expect(statusLine.first()).toBeVisible({ timeout: 3000 });
            const statusText = await statusLine.first().textContent();
            expect(statusText.trim()).toContain("Blocked");
            // Must not contain "conflicts with" (that belongs in the reason paragraph)
            expect(statusText).not.toContain("conflicts with");
            return;
        }
    }
    test.skip(true, "No conflict group found in test recordings");
});

test("C3-08: No standalone CT/VT section; Instrument transformers in Engineering Evidence", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // No standalone CT/VT section heading
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasCTVTSection = headings.some(h => /^CT\s*\/\s*VT$/i.test(h.trim()));
    expect(hasCTVTSection).toBeFalsy();

    // Instrument transformers note exists inside Engineering Evidence
    const evidenceDetails = page.locator("#wwRdDetailsBody details.ww-rd-evidence").first();
    await evidenceDetails.locator("summary").click(); // open it
    await expect(evidenceDetails.locator(".ww-rd-evidence-body")).toBeVisible({ timeout: 3000 });
    await expect(evidenceDetails).toContainText("Instrument transformers");
});

test("C3-09: Current group shows Current base field label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "I") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
            const hasCurrentLabel = labels.some(l => l.includes("Current base"));
            expect(hasCurrentLabel).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No current group found in test recordings");
});

test("C3-10: dark theme renders group details without layout breakage", async ({ page }) => {
    await page.goto("/index.html");
    await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("ww-theme", "dark"); } catch (e) {}
    });
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Panel should not have horizontal overflow
    const hasOverflow = await page.evaluate(() => {
        const body = document.getElementById("wwRdDetailsBody");
        return body ? body.scrollWidth > body.clientWidth + 1 : false;
    });
    expect(hasOverflow).toBe(false);

    // Section headings should be visible
    const headings = page.locator("#wwRdDetailsBody .ww-rd-section-heading");
    expect(await headings.count()).toBeGreaterThan(0);
});
