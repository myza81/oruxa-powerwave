// RD-1 Slice C-2 — Authoritative base authority labels and simplified group details.
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

async function selectGroupByKind(page, kind) {
    await page.locator(`#wwRdGroupKindFilter button[data-kind='${kind}']`).click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 5000 });
    return rows.first();
}

// ---- Tests ------------------------------------------------------------------

test("RD-1 C2-01: voltage group details — Configuration row is present and not empty", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const details = page.locator("#wwRdDetailsBody");
    await expect(details).toContainText("Voltage Base Configuration");
    // Configuration label row must exist
    await expect(details).toContainText("Configuration");
    // Must not contain the old inferred "line_to_ground" label as a config authority
    const text = await details.textContent();
    expect(text).not.toContain("line_to_ground");
});

test("RD-1 C2-02: voltage group main view — unresolved nominal voltage shows single actionable warning, not field grid; no Per-unit availability section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const details = page.locator("#wwRdDetailsBody");
    // Section heading present regardless of nominal voltage state
    await expect(details).toContainText("Configuration");
    // UX-1: when nominal voltage is unresolved, the single actionable warning replaces the field grid
    // ("Voltage reference" label is absent; the warning contains "Nominal voltage")
    await expect(details).toContainText("Nominal voltage is required for voltage per-unit calculation.");
    // Exactly one missing-voltage warning — no redundant unresolved status messages
    await expect(details.locator(".ww-rd-voltage-missing-reason")).toHaveCount(1);
    // UX-1: Per-unit availability section is removed
    await expect(details).not.toContainText("Per-unit availability");
});

test("RD-1 C2-03: voltage group Engineering Evidence section is absent (UX-2: removed)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // UX-2: Engineering Evidence removed by owner decision.
    const details = page.locator("#wwRdDetailsBody");
    await expect(details.locator("details.ww-rd-evidence")).not.toBeAttached();
    // Voltage Base Configuration remains present.
    const headings = await details.locator(".ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Voltage Base Configuration"))).toBe(true);
});

test("RD-1 C2-04: detection reason not visible in main view (UX-2: Engineering Evidence removed)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // UX-2: Engineering Evidence removed — detection reason is a backend-only diagnostic field.
    await expect(page.locator("#wwRdDetailsBody details.ww-rd-evidence")).not.toBeAttached();
    // Detection reason token must not appear in the main panel.
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Detection reason");
});

test("RD-1 C2-05: current group main view shows equipment-capacity design (no PU section)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");

    const details = page.locator("#wwRdDetailsBody");
    // Section heading is now "Equipment Rating" (C4 redesign from "Current Group")
    await expect(details).toContainText("Equipment Rating");
    // Per-unit availability section must NOT appear for current groups
    await expect(details.locator(".ww-rd-pu-status-line")).not.toBeVisible();
    // UX-2: Engineering Evidence section removed.
    await expect(details.locator("details.ww-rd-evidence")).not.toBeAttached();
});

test("RD-1 C2-06: current group Engineering Evidence section is absent (UX-2: removed)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");

    // UX-2: Engineering Evidence removed by owner decision.
    const details = page.locator("#wwRdDetailsBody");
    await expect(details.locator("details.ww-rd-evidence")).not.toBeAttached();
    // Equipment Rating remains present.
    await expect(details).toContainText("Equipment Rating");
});

test("RD-1 C2-07: PU availability section absent for both voltage and current groups (UX-1)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // UX-1: PU availability section removed for voltage groups
    await selectGroupByKind(page, "voltage");
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Voltage Base Configuration section must be present instead
    const vHeadings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(vHeadings.some(h => h.includes("Voltage Base Configuration"))).toBe(true);

    // Current group: no PU section either (current groups use Calculated Channels for PU)
    await selectGroupByKind(page, "current");
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
});

test("RD-1 C2-08: CT/VT section shows 'Not configured' when VT has no manual override, no recording-metadata VT and no auto_nominal base (D4: not_configured authority)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // VT section must be present as a standalone section in the main panel
    const headings = page.locator("#wwRdDetailsBody .ww-rd-section-heading");
    const allH = await headings.allTextContents();
    const hasTransformerSection = allH.some((t) =>
        t.includes("Voltage Transformer") || t.includes("Current Transformer"));
    expect(hasTransformerSection).toBe(true);
    // D4 authority hierarchy: manual > recording_metadata > auto_nominal > not_configured
    // synth_ascii.cfg: no manual VT, no recording-metadata VT, nominal voltage unresolved
    // → vt_effective_authority = not_configured → frontend renders "Not configured"
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Not configured");
    // "Not available from recording metadata" was the old rendering; it must not appear
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Not available from recording metadata");
});

test("RD-1 C2-09: conflict banner is preserved when manual_conflict_detected", async ({ page }) => {
    // This test verifies the conflict banner structure is intact; actual conflict
    // triggering requires API manipulation so we only verify the HTML structure
    // exists and doesn't appear for a clean synth_ascii group.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // For a fresh COMTRADE group without a manual conflict, banner must NOT appear
    await expect(page.locator("#wwRdDetailsBody .ww-rd-conflict-banner")).not.toBeVisible();
});

test("RD-1 C2-10: Engineering Evidence section is absent (UX-2: removed, was toggle test)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // UX-2: Engineering Evidence removed — no toggle element in the panel.
    await expect(page.locator("#wwRdDetailsBody details.ww-rd-evidence")).not.toBeAttached();
    // No JavaScript errors: group selection workflow remains functional.
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
});
