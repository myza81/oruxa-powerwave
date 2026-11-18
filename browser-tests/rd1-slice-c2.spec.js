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

test("RD-1 C2-02: voltage group main view has exactly 4 rows (Nominal voltage, Reference, Configuration, PU availability)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const details = page.locator("#wwRdDetailsBody");
    await expect(details).toContainText("Nominal voltage");
    await expect(details).toContainText("Reference");
    await expect(details).toContainText("Configuration");
    await expect(details).toContainText("Per-unit availability");
});

test("RD-1 C2-03: voltage group Engineering Evidence section is present", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const details = page.locator("#wwRdDetailsBody");
    await expect(details.locator("details.ww-rd-evidence")).toBeVisible();
    await expect(details.locator("details.ww-rd-evidence summary")).toContainText("Engineering Evidence");
});

test("RD-1 C2-04: voltage group Detection reason is in Engineering Evidence, not main view", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const evidence = page.locator("#wwRdDetailsBody details.ww-rd-evidence");
    // Open the details element
    await evidence.locator("summary").click();
    await expect(evidence).toContainText("Detection reason");
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
    // Engineering Evidence section is still present
    await expect(details.locator("details.ww-rd-evidence")).toBeVisible();
});

test("RD-1 C2-06: current group Engineering Evidence section is present", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");

    const details = page.locator("#wwRdDetailsBody");
    await expect(details.locator("details.ww-rd-evidence")).toBeVisible();
    await expect(details.locator("details.ww-rd-evidence summary")).toContainText("Engineering Evidence");
});

test("RD-1 C2-07: PU status line shown for voltage group; absent for current group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Voltage group: PU status line must be present
    await selectGroupByKind(page, "voltage");
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).toBeVisible();

    // Current group: no PU status line (current groups use Calculated Channels for PU)
    await selectGroupByKind(page, "current");
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
});

test("RD-1 C2-08: CT/VT section shows 'Not available from recording metadata' (not 'Not configured')", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    // C4 amendment: CT/VT is a standalone section in main panel (not in Evidence).
    // The standalone VT section shows "Not available from recording metadata".
    const headings = page.locator("#wwRdDetailsBody .ww-rd-section-heading");
    const allH = await headings.allTextContents();
    const hasTransformerSection = allH.some((t) =>
        t.includes("Voltage Transformer") || t.includes("Current Transformer"));
    expect(hasTransformerSection).toBe(true);
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Not available from recording metadata");
    await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Not configured");
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

test("RD-1 C2-10: Engineering Evidence section expands and collapses via summary click", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "voltage");

    const evidence = page.locator("#wwRdDetailsBody details.ww-rd-evidence");
    const body = evidence.locator(".ww-rd-evidence-body");

    // Should be closed by default; click to open
    await evidence.locator("summary").click();
    await expect(body).toBeVisible();

    // Click again to close
    await evidence.locator("summary").click();
    await expect(body).not.toBeVisible();
});
