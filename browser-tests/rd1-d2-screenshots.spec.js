// One-off screenshot capture for RD-1 D2 refinement UAT evidence.
// Captures 5 screenshots: read-only (auto_resolved), read-only (needs_review),
// edit mode (auto-detected ref), edit mode (Advanced open + Clear btn), edit dark.
// Run once; committed screenshots go into docs/project-memory/evidence/rd1-d2-refine/

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const OUT_DIR = path.join(__dirname, "..", "docs", "project-memory", "evidence", "rd1-d2-refine");

const { mkdirSync } = require("fs");
mkdirSync(OUT_DIR, { recursive: true });

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
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
}

function makeMockVoltageGroup(overrides) {
    const { voltage_config: vcOverrides, ...topOverrides } = overrides;
    return Object.assign({
        id: "mock-vg-ss-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG_SS",
        kind: "voltage",
        status: "confirmed",
        channel_refs: [{ channel_name: "VA" }, { channel_name: "VB" }, { channel_name: "VC" }],
        pu_status: "configured",
        pu_reason: null,
        current_config: null,
        voltage_config: Object.assign({
            nominal_voltage_ll_kv: 275.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            secondary_voltage_ll_v: null,
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "detected_from_names",
            evidence_names: ["VA"],
            vt_primary_v: null,
            vt_secondary_v: null,
            vt_ratio: null,
            vt_authority: "not_configured",
            vt_provenance_note: null,
        }, vcOverrides || {}),
    }, topOverrides);
}

async function injectAndSelect(page, vcOverrides, displayName) {
    const name = displayName || "MOCK_VG_SS";
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockVoltageGroup({ display_name: name, voltage_config: vcOverrides || {} });
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    await selectFirstRecording(page);
    const item = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: name });
    await expect(item).toBeVisible({ timeout: 10000 });
    await item.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// SS-01: Read-only, auto_resolved — light theme
test("SS-01: screenshot read-only auto_resolved light", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelect(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
        detection_reason: "detected_from_names",
    }, "SS_AUTO_RESOLVED");
    await page.locator("#wwRdDetailsBody").screenshot({
        path: path.join(OUT_DIR, "1-readonly-auto-resolved-light.png"),
    });
});

// SS-02: Read-only, needs_review — light theme
test("SS-02: screenshot read-only needs_review light", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelect(page, {
        nominal_voltage_ll_kv: null,
        base_authority: "needs_review",
        reference_mode: "auto",
        effective_reference: null,
        detection_reason: null,
    }, "SS_NEEDS_REVIEW");
    await page.locator("#wwRdDetailsBody").screenshot({
        path: path.join(OUT_DIR, "2-readonly-needs-review-light.png"),
    });
});

// SS-03: Edit mode, auto-detected reference — light theme
test("SS-03: screenshot edit mode auto-detected reference light", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelect(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "SS_EDIT_AUTO");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody").screenshot({
        path: path.join(OUT_DIR, "3-edit-auto-detected-light.png"),
    });
});

// SS-04: Edit mode, Advanced expanded with Clear button — light theme
test("SS-04: screenshot edit mode advanced expanded clear button light", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelect(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "SS_EDIT_MANUAL");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody").screenshot({
        path: path.join(OUT_DIR, "4-edit-advanced-clear-light.png"),
    });
});

// SS-05: Edit mode, dark theme
test("SS-05: screenshot edit mode dark theme", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto("/index.html");
    await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("ww-theme", "dark"); } catch (e) {}
    });
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelect(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "SS_EDIT_DARK");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody").screenshot({
        path: path.join(OUT_DIR, "5-edit-dark-theme.png"),
    });
});
