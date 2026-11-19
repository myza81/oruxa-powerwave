// RD-1 Slice D3 — Independent equipment-rating metadata.
// Verifies that equipment_mva and equipment_linked_voltage_group_id are stored
// and edited independently of the PU current-base method.

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

function makeMockVoltageGroup(id, kv, sourceId) {
    return {
        id: id || "mock-vg-d3",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK VG D3",
        kind: "voltage",
        status: "confirmed",
        channel_refs: [{ channel_name: "VA" }],
        pu_status: "configured",
        pu_reason: null,
        current_config: null,
        voltage_config: {
            nominal_voltage_ll_kv: kv != null ? kv : 275.0,
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
        },
    };
}

function makeMockCurrentGroup(currentConfigOverrides, sourceId) {
    return Object.assign({
        id: "mock-cg-d3",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK CG D3",
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
            // D3 independent fields
            equipment_mva: null,
            equipment_linked_voltage_group_id: null,
            equipment_rated_current_ka: null,
        }, currentConfigOverrides || {}),
    }, {});
}

async function injectAndSelectCurrentGroup(page, currentConfigOverrides, includeVoltageGroup) {
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        // Copy source_id from the real groups so ww.measurementGroups.get(g.source_id) works
        const sourceId = groups.length > 0 ? groups[0].source_id : "src-test";
        const extras = [makeMockCurrentGroup(currentConfigOverrides, sourceId)];
        if (includeVoltageGroup) extras.push(makeMockVoltageGroup("mock-vg-d3", 275.0, sourceId));
        await route.fulfill({ json: [...groups, ...extras] });
    });
    // Select first recording
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    // Select the mock current group
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK CG D3" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- D3-01: Equipment Rating section present for current group in read mode ---

test("D3-01: Equipment Rating section is visible for a current group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Equipment Rating" });
    await expect(section).toBeVisible({ timeout: 5000 });
});

// ---- D3-02: Edit button present in Equipment Rating heading ------------------

test("D3-02: Edit button is present in the Equipment Rating section heading", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {});
    const btn = page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn");
    await expect(btn).toBeVisible({ timeout: 5000 });
    await expect(btn).toContainText("Edit");
});

// ---- D3-03: Edit mode shows MVA input and voltage group selector -------------

test("D3-03: clicking Edit enters edit mode with MVA input and voltage group selector", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {}, true);
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCurMva")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdCurVoltageGroup")).toBeVisible({ timeout: 3000 });
});

// ---- D3-04: Edit mode pre-fills existing equipment_mva ----------------------

test("D3-04: edit mode pre-fills equipment_mva from current group state", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, { equipment_mva: 150.0 });
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCurMva")).toBeVisible({ timeout: 3000 });
    const val = await page.locator("#wwRdDetailsBody #wwRdCurMva").inputValue();
    expect(val).toBe("150");
});

// ---- D3-05: Edit mode pre-fills existing equipment_linked_voltage_group_id ---

test("D3-05: edit mode pre-selects equipment_linked_voltage_group_id in the voltage group selector", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {
        equipment_mva: 100.0,
        equipment_linked_voltage_group_id: "mock-vg-d3",
    }, true);
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCurVoltageGroup")).toBeVisible({ timeout: 3000 });
    const val = await page.locator("#wwRdDetailsBody #wwRdCurVoltageGroup").inputValue();
    expect(val).toBe("mock-vg-d3");
});

// ---- D3-06: Cancel returns to read mode without changing data ----------------

test("D3-06: Cancel exits edit mode and returns to read mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, { equipment_mva: 80.0 });
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdCurMva")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdCurrentCancelBtn").click();
    // Edit inputs gone
    await expect(page.locator("#wwRdDetailsBody #wwRdCurMva")).not.toBeVisible();
    // Read mode heading with Edit button returns
    await expect(page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn")).toBeVisible({ timeout: 3000 });
    // Value unchanged
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Equipment Rating" })).toContainText("80");
});

// ---- D3-07: Apply sends PUT with update_equipment_metadata_only=true ---------

test("D3-07: Apply sends PUT with update_equipment_metadata_only=true", async ({ page }) => {
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
                body: JSON.stringify(makeMockCurrentGroup({
                    equipment_mva: 100.0,
                    equipment_linked_voltage_group_id: null,
                    equipment_rated_current_ka: 0.2099,
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCurMva").fill("100");
    await page.locator("#wwRdDetailsBody #wwRdCurrentApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody.update_equipment_metadata_only).toBe(true);
});

// ---- D3-08: Apply sends correct equipment_mva value -------------------------

test("D3-08: Apply sends correct equipment_mva value in PUT body", async ({ page }) => {
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
                body: JSON.stringify(makeMockCurrentGroup({ equipment_mva: 250.0 })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCurMva").fill("250");
    await page.locator("#wwRdDetailsBody #wwRdCurrentApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody.equipment_mva).toBeCloseTo(250.0);
});

// ---- D3-09: Apply sends equipment_linked_voltage_group_id from selector -----

test("D3-09: Apply sends equipment_linked_voltage_group_id from the voltage group selector", async ({ page }) => {
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
                body: JSON.stringify(makeMockCurrentGroup({
                    equipment_mva: 100.0,
                    equipment_linked_voltage_group_id: "mock-vg-d3",
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {}, true);
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCurMva").fill("100");
    await page.locator("#wwRdDetailsBody #wwRdCurVoltageGroup").selectOption("mock-vg-d3");
    await page.locator("#wwRdDetailsBody #wwRdCurrentApplyBtn").click();
    await page.waitForTimeout(1500);

    expect(capturedBody).not.toBeNull();
    expect(capturedBody.equipment_linked_voltage_group_id).toBe("mock-vg-d3");
});

// ---- D3-10: After Apply, read mode shows updated values ---------------------

test("D3-10: after successful Apply, read mode shows updated equipment_mva from response", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/current-config", async route => {
        if (route.request().method() === "PUT") {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockCurrentGroup({ equipment_mva: 320.0 })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectCurrentGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdCurMva").fill("320");
    await page.locator("#wwRdDetailsBody #wwRdCurrentApplyBtn").click();
    // Edit mode clears and read mode returns
    await expect(page.locator("#wwRdDetailsBody #wwRdCurrentEditBtn")).toBeVisible({ timeout: 5000 });
    // Displayed value includes 320
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Equipment Rating" });
    await expect(section).toContainText("320");
});

// ---- D3-11: equipment_rated_current_ka shown in read mode -------------------

test("D3-11: equipment_rated_current_ka is displayed in read mode when non-null", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, {
        equipment_mva: 100.0,
        equipment_linked_voltage_group_id: "mock-vg-d3",
        equipment_rated_current_ka: 0.2099,
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Equipment Rating" });
    await expect(section).toContainText("0.2099");
    await expect(section).toContainText("kA");
});

// ---- D3-12: "Not specified" shown for equipment_mva=null --------------------

test("D3-12: read mode shows 'Not specified' when equipment_mva is null", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectCurrentGroup(page, { equipment_mva: null });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Equipment Rating" });
    await expect(section).toContainText("Not specified");
});
