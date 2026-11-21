// RD-1 Slice D4-effective — automatic VT authority hierarchy.
// Verifies the 2-state VT section (effective / not-configured), authority-based
// display, editor prefill from vt_effective_*, Apply saving as manual, and live
// ratio display in the editor using the "X kV / Y V" format.

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

function makeMockVoltageGroup(id, voltageConfigOverrides, sourceId) {
    return {
        id: id || "mock-vg-eff",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK VG EFF",
        kind: "voltage",
        status: "confirmed",
        channel_refs: [{ channel_name: "VA" }],
        pu_status: "configured",
        pu_reason: null,
        current_config: null,
        voltage_config: Object.assign({
            nominal_voltage_ll_kv: 275.0,
            base_authority: "manual",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            secondary_voltage_ll_v: null,
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: null,
            evidence_names: [],
            vt_primary_v: null,
            vt_secondary_v: null,
            vt_ratio: null,
            vt_authority: "not_configured",
            vt_provenance_note: null,
            // D4-effective: auto_nominal derived from nominal voltage
            vt_effective_primary_v: 275000,
            vt_effective_secondary_v: 110,
            vt_effective_authority: "auto_nominal",
        }, voltageConfigOverrides || {}),
    };
}

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides) {
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const sourceId = groups.length > 0 ? groups[0].source_id : "src-test";
        const mockGroup = makeMockVoltageGroup("mock-vg-eff", voltageConfigOverrides, sourceId);
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK VG EFF" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- VE-01: auto_nominal VT shown immediately when nominal kV known ---------

test("VE-01: auto_nominal VT values are shown immediately when nominal kV is known", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toBeVisible({ timeout: 5000 });
    await expect(section).not.toContainText("Not configured");
    await expect(section).toContainText("275");
});

// ---- VE-02: auto_nominal shows "Auto-derived from nominal voltage" note ---------------

test("VE-02: auto_nominal state shows 'Auto-derived from nominal voltage' note", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("Auto-derived from nominal voltage");
});

// ---- VE-03: auto_nominal shows "Suggested" label is NOT present -------------

test("VE-03: auto_nominal state does NOT show a 'Suggested' label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).not.toContainText("Suggested");
});

// ---- VE-04: auto_nominal shows ratio as "275 kV / 110 V" --------------------

test("VE-04: auto_nominal state shows ratio as '275 kV / 110 V' (not colon notation)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("275 kV");
    await expect(section).toContainText("110");
    await expect(section).not.toContainText("2500:1");
});

// ---- VE-05: Edit prefills from auto_nominal effective values -----------------

test("VE-05: Edit button prefills primary kV and secondary V from auto_nominal effective values", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    const primaryVal = await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").inputValue();
    expect(parseFloat(primaryVal)).toBeCloseTo(275, 1);
    const secondaryVal = await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").inputValue();
    expect(parseFloat(secondaryVal)).toBeCloseTo(110, 1);
});

// ---- VE-06: manual VT shown without "Auto-derived from nominal voltage" note ---------

test("VE-06: manual VT shows values and no 'Auto-derived from nominal voltage' note", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 275000,
        vt_secondary_v: 110,
        vt_ratio: 275000 / 110,
        vt_authority: "manual",
        vt_effective_primary_v: 275000,
        vt_effective_secondary_v: 110,
        vt_effective_authority: "manual",
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("275");
    await expect(section).not.toContainText("Auto-derived from nominal voltage");
    await expect(section).not.toContainText("Not configured");
});

// ---- VE-07: Edit prefills from manual effective values ----------------------

test("VE-07: Edit prefills from manual effective values (vt_effective_primary_v / secondary_v)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 132000,
        vt_secondary_v: 100,
        vt_ratio: 1320,
        vt_authority: "manual",
        vt_effective_primary_v: 132000,
        vt_effective_secondary_v: 100,
        vt_effective_authority: "manual",
    });
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    const primaryVal = await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").inputValue();
    expect(parseFloat(primaryVal)).toBeCloseTo(132, 1);
    const secondaryVal = await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").inputValue();
    expect(parseFloat(secondaryVal)).toBeCloseTo(100, 1);
});

// ---- VE-08: unresolved nominal → "Not configured" ---------------------------

test("VE-08: unresolved nominal (no effective values) shows 'Not configured'", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: null,
        base_authority: "needs_review",
        vt_effective_primary_v: null,
        vt_effective_secondary_v: null,
        vt_effective_authority: "not_configured",
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("Not configured");
    await expect(section).not.toContainText("Auto-derived from nominal voltage");
});

// ---- VE-09: Apply saves as manual — no note shown after save ----------------

test("VE-09: applying VT saves as manual and 'Auto-derived from nominal voltage' note disappears", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockVoltageGroup("mock-vg-eff", {
                    vt_primary_v: 275000,
                    vt_secondary_v: 110,
                    vt_ratio: 275000 / 110,
                    vt_authority: "manual",
                    vt_effective_primary_v: 275000,
                    vt_effective_secondary_v: 110,
                    vt_effective_authority: "manual",
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtApplyBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtEditBtn")).toBeVisible({ timeout: 5000 });

    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).not.toContainText("Auto-derived from nominal voltage");
    await expect(section).toContainText("275");
});

// ---- VE-10: Remove button only appears in edit when vt_authority=manual -----

test("VE-10: 'Remove VT configuration' button appears in edit mode only when vt_authority is manual", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 275000,
        vt_secondary_v: 110,
        vt_ratio: 275000 / 110,
        vt_authority: "manual",
        vt_effective_primary_v: 275000,
        vt_effective_secondary_v: 110,
        vt_effective_authority: "manual",
    });
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtRemoveBtn")).toBeVisible({ timeout: 3000 });
});

// ---- VE-11: Remove button absent in edit when authority is auto_nominal -----

test("VE-11: 'Remove VT configuration' button is absent in edit mode when authority is auto_nominal", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});  // auto_nominal, vt_authority="not_configured"
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtRemoveBtn")).not.toBeVisible();
});

// ---- VE-12: Live ratio display in editor — "X kV / Y V" format --------------

test("VE-12: live ratio display shows 'X kV / Y V' format while editing", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").dispatchEvent("input");
    const liveRatio = page.locator("#wwRdDetailsBody #wwRdVtLiveRatio");
    await expect(liveRatio).toBeVisible({ timeout: 3000 });
    await expect(liveRatio).toContainText("110 kV");
    await expect(liveRatio).toContainText("110");
});
