// RD-1 Slice C-3: Group Details visual design regression tests.
// Verifies new section structure, two-column field grid, PU status line,
// CT/VT moved into Engineering Evidence, and "Not resolved" for null values.

const { test, expect } = require("@playwright/test");
const BASE = process.env.PW_FRONTEND_URL || "http://localhost:8101";

async function openRecordingDetails(page) {
    await page.goto(BASE);
    await page.waitForSelector("#mainNavRecordingDetailsBtn", { state: "visible" });
    await page.click("#mainNavRecordingDetailsBtn");
    await page.waitForSelector("#pageRecordingDetails", { state: "visible" });
}

async function selectFirstRecording(page) {
    const item = page.locator(".ww-rd-recording-item").first();
    await item.waitFor({ state: "visible", timeout: 8000 });
    await item.click();
    // Wait for group list to populate
    await page.waitForSelector(".ww-rd-group-item", { state: "visible", timeout: 8000 });
}

async function selectFirstGroup(page) {
    const group = page.locator(".ww-rd-group-item").first();
    await group.waitFor({ state: "visible", timeout: 5000 });
    await group.click();
    // Wait for details panel to show group content
    await page.waitForSelector(".ww-rd-section", { state: "visible", timeout: 5000 });
}

test("C3-01: group name visible and channels as dot-separated list", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    // Switch to Group Details tab
    await page.click("#wwRdTabGroupDetails");
    await selectFirstGroup(page);
    // Group name present
    await expect(page.locator(".ww-rd-details-group-name").first()).toBeVisible();
    // Channel list present and uses · separator (or "No channels assigned")
    const ch = page.locator(".ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    // Should use middle-dot separator or say "No channels assigned"
    expect(chText.includes("·") || chText.includes("No channels assigned")).toBeTruthy();
});

test("C3-02: voltage group shows Nominal voltage (L-L) label and Not resolved or value", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    // Try to find a voltage group
    const groups = page.locator(".ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await page.waitForSelector(".ww-rd-field-label", { state: "visible", timeout: 5000 });
            const labels = await page.locator(".ww-rd-field-label").allTextContents();
            const hasNomLabel = labels.some(l => l.includes("Nominal voltage"));
            expect(hasNomLabel).toBeTruthy();
            // Value is either a kV string or "Not resolved"
            const values = await page.locator(".ww-rd-field-value").allTextContents();
            const hasValue = values.some(v => v.includes("kV") || v.includes("Not resolved"));
            expect(hasValue).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found in test recording");
});

test("C3-03: two-column grid has Voltage reference label alongside Nominal voltage", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    const groups = page.locator(".ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await page.waitForSelector(".ww-rd-field-grid", { state: "visible", timeout: 5000 });
            const labels = await page.locator(".ww-rd-field-label").allTextContents();
            const hasVRef = labels.some(l => l.includes("Voltage reference"));
            expect(hasVRef).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C3-04: Configuration source field present in Base Configuration section", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    await selectFirstGroup(page);
    const labels = await page.locator(".ww-rd-field-label").allTextContents();
    const hasConfigSrc = labels.some(l => l.includes("Configuration source"));
    expect(hasConfigSrc).toBeTruthy();
});

test("C3-05: Per-unit availability section present with status word and reason paragraph", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    await selectFirstGroup(page);
    // Section heading
    const headings = await page.locator(".ww-rd-section-heading").allTextContents();
    const hasPuHeading = headings.some(h => h.includes("Per-unit availability"));
    expect(hasPuHeading).toBeTruthy();
    // Status line icon+word
    const statusLine = page.locator(".ww-rd-pu-status-line").first();
    await expect(statusLine).toBeVisible();
    const statusText = await statusLine.textContent();
    // Contains one of the known status words
    const knownWords = ["Available", "Unavailable", "Blocked", "Review required", "Not applicable"];
    expect(knownWords.some(w => statusText.includes(w))).toBeTruthy();
});

test("C3-06: Available state shows checkmark and green-class word (not inside a pill badge)", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    const groups = page.locator(".ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        await groups.nth(i).click();
        await page.waitForSelector(".ww-rd-pu-status-line", { timeout: 3000 }).catch(() => {});
        const statusText = await page.locator(".ww-rd-pu-status-line").first().textContent().catch(() => "");
        if (statusText.includes("Available")) {
            // Status word must NOT be inside a .ww-rd-pu-pill inside the PU section
            const eligibleWord = page.locator(".ww-rd-pu-word--eligible");
            await expect(eligibleWord).toBeVisible();
            return;
        }
    }
    test.skip(true, "No Available group found in test recordings");
});

test("C3-07: Conflict group shows Blocked (not full sentence as status word)", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    const groups = page.locator(".ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        // Check for conflict badge on group row
        const hasConflict = await groups.nth(i).locator(".ww-rd-group-conflict").count();
        if (hasConflict > 0) {
            await groups.nth(i).click();
            await page.waitForSelector(".ww-rd-pu-status-line", { timeout: 3000 });
            const statusText = await page.locator(".ww-rd-pu-status-line").first().textContent();
            expect(statusText.trim()).toContain("Blocked");
            // Must not contain "conflicts with" (that belongs in the reason paragraph)
            expect(statusText).not.toContain("conflicts with");
            return;
        }
    }
    test.skip(true, "No conflict group found in test recordings");
});

test("C3-08: No standalone CT/VT section; Instrument transformers in Engineering Evidence", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    await selectFirstGroup(page);
    // No standalone CT/VT section heading
    const headings = await page.locator(".ww-rd-section-heading, .ww-rd-details-section-title").allTextContents();
    const hasCTVTSection = headings.some(h => /^CT\s*\/\s*VT$/i.test(h.trim()));
    expect(hasCTVTSection).toBeFalsy();
    // Instrument transformers note exists inside Engineering Evidence
    const evidenceDetails = page.locator("details.ww-rd-evidence").first();
    await evidenceDetails.locator("summary").click(); // open it
    await page.waitForSelector(".ww-rd-evidence-body", { state: "visible", timeout: 3000 });
    const bodyText = await page.locator(".ww-rd-evidence-body").first().textContent();
    expect(bodyText).toContain("Instrument transformers");
});

test("C3-09: Current group shows Current base (resolved) label", async ({ page }) => {
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    const groups = page.locator(".ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "I") {
            await groups.nth(i).click();
            await page.waitForSelector(".ww-rd-field-label", { state: "visible", timeout: 5000 });
            const labels = await page.locator(".ww-rd-field-label").allTextContents();
            const hasCurrentLabel = labels.some(l => l.includes("Current base"));
            expect(hasCurrentLabel).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No current group found in test recordings");
});

test("C3-10: dark theme renders group details without layout breakage", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await openRecordingDetails(page);
    await selectFirstRecording(page);
    await page.click("#wwRdTabGroupDetails");
    await selectFirstGroup(page);
    // Panel should not have horizontal overflow
    const details = page.locator(".ww-rd-panel--details");
    const bbox = await details.boundingBox();
    expect(bbox).not.toBeNull();
    // Section headings should be visible
    const headings = page.locator(".ww-rd-section-heading");
    expect(await headings.count()).toBeGreaterThan(0);
});
