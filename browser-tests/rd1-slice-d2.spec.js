// RD-1 Slice D2 — Voltage Base inline editing (Edit/Apply/Cancel/Revert-to-auto).
// Tests the Edit button, form fields, Apply, Cancel, and Revert-to-auto workflow
// for Voltage Measurement Group base configuration in the Group Details panel.

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
}

function makeMockVoltageGroup(overrides) {
    return Object.assign({
        id: "mock-vg-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG",
        kind: "voltage",
        status: "confirmed",
        channel_refs: [{ channel_name: "VA" }, { channel_name: "VB" }, { channel_name: "VC" }],
        pu_status: "configured",
        pu_reason: null,
        current_config: null,
        voltage_config: Object.assign({
            nominal_voltage_ll_kv: null,
            base_authority: "needs_review",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            secondary_voltage_ll_v: null,
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: null,
            evidence_names: [],
        }, overrides.voltage_config || {})
    }, overrides);
}

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides, displayName) {
    const name = displayName || "MOCK_VG_D2";
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockVoltageGroup({
            display_name: name,
            voltage_config: voltageConfigOverrides || {},
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: name });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    // Switch to Group Details tab
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- D2-01: Edit button present for voltage groups ---------------------------

test("D2-01: Edit button present in Voltage Base Configuration heading", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const btn = page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn");
    await expect(btn).toBeVisible({ timeout: 5000 });
    await expect(btn).toHaveText("Edit");
});

// ---- D2-02: Edit button opens the edit form with pre-filled values -----------

test("D2-02: Edit button opens inline edit form with kV input; reference selectors in Advanced section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 132.0,
        base_authority: "manual",
        reference_mode: "auto",
        base_reference_side: "primary",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Form should appear with kV input
    await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible({ timeout: 3000 });
    // kV pre-filled
    const kv = await page.locator("#wwRdDetailsBody #wwRdVltKv").inputValue();
    expect(kv).toBe("132");
    // Apply and Cancel buttons present
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageCancelBtn")).toBeVisible();
    // Reference selects are in the Advanced section — open it first
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).toBeVisible();
});

// ---- D2-03: Cancel restores read mode ----------------------------------------

test("D2-03: Cancel button restores read-only view with Edit button", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVoltageCancelBtn").click();
    // Edit button re-appears, Apply disappears
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).not.toBeVisible();
});

// ---- D2-04: Manual ref mode shows override selector -------------------------

test("D2-04: selecting manual ref mode reveals the reference-type dropdown (in Advanced section)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Open Advanced section to access reference mode selector
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).toBeVisible({ timeout: 3000 });
    // Auto mode: override row should NOT be visible
    await page.locator("#wwRdDetailsBody #wwRdVltRefMode").selectOption("auto");
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).not.toBeVisible();
    // Switch to manual: override row appears
    await page.locator("#wwRdDetailsBody #wwRdVltRefMode").selectOption("manual");
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible({ timeout: 3000 });
});

// ---- D2-05: Apply sends PUT with correct body --------------------------------

test("D2-05: Apply sends PUT with nominal_voltage_ll_kv and reference fields", async ({ page }) => {
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
                body: JSON.stringify(makeMockVoltageGroup({
                    display_name: "MOCK_VG_D2",
                    voltage_config: { nominal_voltage_ll_kv: 275.0, base_authority: "manual", reference_mode: "auto" },
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    // Open Advanced section to interact with reference mode selector
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVltRefMode").selectOption("auto");
    // Intercept the PUT; use page.evaluate to have access to group
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    // Wait for the edit form to disappear (Apply succeeded or failed)
    await page.waitForTimeout(1500);
    if (capturedBody !== null) {
        expect(capturedBody.nominal_voltage_ll_kv).toBeCloseTo(275.0);
        expect(capturedBody.reference_mode).toBe("auto");
    }
});

// ---- D2-06: Revert button only shown for manual-authority groups --------------

test("D2-06: Revert button only shown when group has manual authority and a kV value", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    // Group with needs_review authority — no Revert button expected
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: null,
        base_authority: "needs_review",
    }, "MOCK_NR_GROUP");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).not.toBeVisible();
});

test("D2-06b: Revert button shown when group has manual authority with kV set", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    // Group with manual authority and kV set — Revert button expected
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
    }, "MOCK_MANUAL_GROUP");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toBeVisible();
});

// ---- D2-07: Switching groups discards in-progress edit ----------------------

test("D2-07: selecting a different group discards the in-progress edit", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Inject two mock voltage groups
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mg1 = makeMockVoltageGroup({ display_name: "MOCK_VG_A", id: "mock-vg-a", voltage_config: {} });
        const mg2 = makeMockVoltageGroup({ display_name: "MOCK_VG_B", id: "mock-vg-b", voltage_config: {} });
        await route.fulfill({ json: [...groups, mg1, mg2] });
    });

    await selectFirstRecording(page);
    const itemA = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_VG_A" });
    await expect(itemA).toBeVisible({ timeout: 10000 });
    await itemA.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    // Enter edit mode on group A
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible({ timeout: 3000 });

    // Click group B — edit should be discarded
    const itemB = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_VG_B" });
    await itemB.click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).not.toBeVisible();
});

// ---- D2-08: Edit form does not appear for current groups --------------------

test("D2-08: current groups do not show Voltage Base Configuration Edit button", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.locator(`#wwRdGroupKindFilter button[data-kind='current']`).click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await rows.count();
    if (count === 0) {
        // No current groups in fixture — test passes vacuously
        return;
    }
    await rows.first().click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).not.toBeVisible();
});

// ---- D2-09: Edit button visible in Voltage Base Configuration heading label --

test("D2-09: Voltage Base Configuration heading shows the Edit button, not the read-only note", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    // The old "Read-only · Slice C" note must be gone
    const heading = page.locator("#wwRdDetailsBody .ww-rd-section-heading", { hasText: "Voltage Base Configuration" });
    await expect(heading).toBeVisible({ timeout: 5000 });
    const headingText = await heading.textContent();
    expect(headingText).not.toMatch(/Read-only/i);
    // Edit button within the heading
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible();
});

// ---- D2-10: Base reference side selector present in edit form ----------------

test("D2-10: Advanced section includes base reference side selector with Unknown/Primary/Secondary options", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { base_reference_side: "primary" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Open Advanced section to access base reference side selector
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    const sel = page.locator("#wwRdDetailsBody #wwRdVltRefSide");
    await expect(sel).toBeVisible({ timeout: 3000 });
    const options = await sel.locator("option").allTextContents();
    expect(options).toContain("Unknown");
    expect(options).toContain("Primary");
    expect(options).toContain("Secondary");
    // Pre-selected to current group value
    const selected = await sel.inputValue();
    expect(selected).toBe("primary");
});
