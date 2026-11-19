// RD-1 Slice D4 — CT/VT instrument-transformer configuration editing.
// Verifies VT editing on voltage groups and CT editing on current groups,
// including read mode display, edit mode entry, Apply (PUT), Cancel, and
// the update_ct_only=true backend contract.

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

function makeMockVoltageGroup(id, voltageConfigOverrides, sourceId) {
    return {
        id: id || "mock-vg-d4",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK VG D4",
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
        }, voltageConfigOverrides || {}),
    };
}

function makeMockCurrentGroup(currentConfigOverrides, sourceId) {
    return {
        id: "mock-cg-d4",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK CG D4",
        kind: "current",
        status: "confirmed",
        channel_refs: [{ channel_name: "IA" }],
        pu_status: "base_required",
        pu_reason: null,
        voltage_config: null,
        current_config: Object.assign({
            method: "none",
            equipment_rating_mva: null,
            linked_voltage_group_id: null,
            manual_voltage_base_kv: null,
            manual_ibase_ka: null,
            resolved_ibase_ka: null,
            applicable_voltage_ll_kv: null,
            base_reference_side: "unknown",
            base_authority: "legacy_manual",
            ct_primary_a: null,
            ct_secondary_a: null,
            ct_ratio: null,
            ct_authority: "not_configured",
            ct_provenance_note: null,
            equipment_mva: null,
            equipment_linked_voltage_group_id: null,
            equipment_rated_current_ka: null,
        }, currentConfigOverrides || {}),
    };
}

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides) {
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const sourceId = groups.length > 0 ? groups[0].source_id : "src-test";
        const mockGroup = makeMockVoltageGroup("mock-vg-d4", voltageConfigOverrides, sourceId);
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK VG D4" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

async function injectAndSelectCurrentGroup(page, currentConfigOverrides) {
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const sourceId = groups.length > 0 ? groups[0].source_id : "src-test";
        const mockGroup = makeMockCurrentGroup(currentConfigOverrides, sourceId);
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK CG D4" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- D4-01: VT section present for voltage group (not configured) -----------

test("D4-01: VT section is visible for a voltage group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toBeVisible({ timeout: 5000 });
});

// ---- D4-02: VT section shows "Not configured" when vt fields null ----------

test("D4-02: VT section shows Not configured when no VT is set", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { vt_primary_v: null, vt_secondary_v: null });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("Not configured");
});

// ---- D4-03: VT section shows primary kV, secondary V, ratio when configured

test("D4-03: VT section shows primary kV, secondary V and ratio when configured", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 275000,
        vt_secondary_v: 110,
        vt_ratio: 2500,
        vt_authority: "manual",
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("275");     // kV
    await expect(section).toContainText("110");     // V secondary
    await expect(section).toContainText("2500");    // ratio
});

// ---- D4-04: VT Edit button is visible in read mode -------------------------

test("D4-04: VT Edit button is visible in read mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const btn = page.locator("#wwRdDetailsBody #wwRdVtEditBtn");
    await expect(btn).toBeVisible({ timeout: 5000 });
    await expect(btn).toContainText("Edit");
});

// ---- D4-05: Clicking VT Edit enters edit mode with two inputs ---------------

test("D4-05: clicking VT Edit enters edit mode with primary kV and secondary V inputs", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVtSecondaryV")).toBeVisible({ timeout: 3000 });
});

// ---- D4-06: VT edit pre-fills existing values (kV from vt_primary_v) -------

test("D4-06: VT edit pre-fills existing vt_primary_v as kV", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 275000,
        vt_secondary_v: 110,
        vt_ratio: 2500,
        vt_authority: "manual",
    });
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    const primaryVal = await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").inputValue();
    // 275000 V / 1000 = 275 kV
    expect(parseFloat(primaryVal)).toBeCloseTo(275, 1);
    const secondaryVal = await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").inputValue();
    expect(parseFloat(secondaryVal)).toBeCloseTo(110, 1);
});

// ---- D4-07: VT Cancel returns to read mode without changing data ------------

test("D4-07: VT Cancel returns to read mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { vt_primary_v: 275000, vt_secondary_v: 110, vt_ratio: 2500, vt_authority: "manual" });
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVtCancelBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtEditBtn")).toBeVisible({ timeout: 3000 });
});

// ---- D4-08: VT Apply sends PUT to voltage-config endpoint ------------------

test("D4-08: VT Apply sends PUT to voltage-config with vt_primary_v converted from kV", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockVoltageGroup("mock-vg-d4", {
                    vt_primary_v: 275000,
                    vt_secondary_v: 110,
                    vt_ratio: 2500,
                    vt_authority: "manual",
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
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    // kV entered → V stored (275 * 1000 = 275000)
    expect(capturedBody.vt_primary_v).toBeCloseTo(275000, 0);
    expect(capturedBody.vt_secondary_v).toBeCloseTo(110, 1);
});

// ---- D4-09: VT Apply echoes reference fields (D2 safety) -------------------

test("D4-09: VT Apply echoes reference_mode in PUT body", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockVoltageGroup("mock-vg-d4", { vt_primary_v: 110000, vt_secondary_v: 110, vt_ratio: 1000, vt_authority: "manual" })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, { reference_mode: "auto" });
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    // reference_mode must be echoed — not defaulted to "auto" blindly
    expect(capturedBody.reference_mode).toBeDefined();
});

// ---- D4-10: After VT Apply, read mode shows updated values -----------------

test("D4-10: after VT Apply, read mode shows updated primary kV", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockVoltageGroup("mock-vg-d4", {
                    vt_primary_v: 110000,
                    vt_secondary_v: 110,
                    vt_ratio: 1000,
                    vt_authority: "manual",
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtApplyBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtEditBtn")).toBeVisible({ timeout: 5000 });
    // Response has vt_primary_v=110000V = 110kV; should display "110"
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("110");
});

// ---- D4-11: CT section present for current group (not configured) -----------

test("D4-11: CT section is visible for a current group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Current Transformer" });
    await expect(section).toBeVisible({ timeout: 5000 });
});

// ---- D4-12: CT section shows "Not configured" when CT fields null -----------

test("D4-12: CT section shows Not configured when no CT is set", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, { ct_primary_a: null, ct_secondary_a: null });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Current Transformer" });
    await expect(section).toContainText("Not configured");
});

// ---- D4-13: CT section shows primary A, secondary A, ratio when configured -

test("D4-13: CT section shows primary A, secondary A and ratio when configured", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {
        ct_primary_a: 2000,
        ct_secondary_a: 1,
        ct_ratio: 2000,
        ct_authority: "manual",
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Current Transformer" });
    await expect(section).toContainText("2000");   // primary A
    await expect(section).toContainText("1");      // secondary A
    // ratio 2000:1
    await expect(section).toContainText("2000");
});

// ---- D4-14: CT Edit button is visible in read mode -------------------------

test("D4-14: CT Edit button is visible in read mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {});
    const btn = page.locator("#wwRdDetailsBody #wwRdCtEditBtn");
    await expect(btn).toBeVisible({ timeout: 5000 });
    await expect(btn).toContainText("Edit");
});

// ---- D4-15: Clicking CT Edit enters edit mode with two inputs ---------------

test("D4-15: clicking CT Edit enters edit mode with primary A and secondary A inputs", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtPrimaryA")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdCtSecondaryA")).toBeVisible({ timeout: 3000 });
});

// ---- D4-16: CT edit pre-fills existing values ------------------------------

test("D4-16: CT edit pre-fills existing ct_primary_a and ct_secondary_a", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {
        ct_primary_a: 2000,
        ct_secondary_a: 1,
        ct_ratio: 2000,
        ct_authority: "manual",
    });
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtPrimaryA")).toBeVisible({ timeout: 3000 });
    const primaryVal = await page.locator("#wwRdDetailsBody #wwRdCtPrimaryA").inputValue();
    expect(parseFloat(primaryVal)).toBeCloseTo(2000, 0);
    const secondaryVal = await page.locator("#wwRdDetailsBody #wwRdCtSecondaryA").inputValue();
    expect(parseFloat(secondaryVal)).toBeCloseTo(1, 0);
});

// ---- D4-17: CT Cancel returns to read mode ---------------------------------

test("D4-17: CT Cancel returns to read mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, { ct_primary_a: 2000, ct_secondary_a: 1, ct_authority: "manual" });
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtPrimaryA")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdCtCancelBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtPrimaryA")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtEditBtn")).toBeVisible({ timeout: 3000 });
});

// ---- D4-18: CT Apply sends PUT with update_ct_only=true --------------------

test("D4-18: CT Apply sends PUT to current-config with update_ct_only=true", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/current-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockCurrentGroup({ ct_primary_a: 2000, ct_secondary_a: 1, ct_ratio: 2000, ct_authority: "manual" })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCtPrimaryA").fill("2000");
    await page.locator("#wwRdDetailsBody #wwRdCtSecondaryA").fill("1");
    await page.locator("#wwRdDetailsBody #wwRdCtApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody.update_ct_only).toBe(true);
});

// ---- D4-19: CT Apply sends correct ct_primary_a and ct_secondary_a ---------

test("D4-19: CT Apply sends correct ct_primary_a and ct_secondary_a values", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/current-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockCurrentGroup({ ct_primary_a: 1500, ct_secondary_a: 5, ct_ratio: 300, ct_authority: "manual" })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCtPrimaryA").fill("1500");
    await page.locator("#wwRdDetailsBody #wwRdCtSecondaryA").fill("5");
    await page.locator("#wwRdDetailsBody #wwRdCtApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody.ct_primary_a).toBeCloseTo(1500, 0);
    expect(capturedBody.ct_secondary_a).toBeCloseTo(5, 0);
});

// ---- D4-20: After CT Apply, read mode shows updated values -----------------

test("D4-20: after CT Apply, read mode shows updated ct_primary_a from response", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/current-config", async route => {
        if (route.request().method() === "PUT") {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockCurrentGroup({ ct_primary_a: 800, ct_secondary_a: 1, ct_ratio: 800, ct_authority: "manual" })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCtEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCtPrimaryA").fill("800");
    await page.locator("#wwRdDetailsBody #wwRdCtSecondaryA").fill("1");
    await page.locator("#wwRdDetailsBody #wwRdCtApplyBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCtEditBtn")).toBeVisible({ timeout: 5000 });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Current Transformer" });
    await expect(section).toContainText("800");
});
