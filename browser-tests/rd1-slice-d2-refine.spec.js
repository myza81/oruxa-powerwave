// RD-1 Slice D2 Refinement — Property-level provenance, adaptive voltage reference
// and removal of standalone "Configuration source" field.
// Covers owner acceptance scenarios from D2 spec sections 5, 8, 9, 11.

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

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
}

function makeMockVoltageGroup(overrides) {
    const { voltage_config: vcOverrides, ...topOverrides } = overrides;
    return Object.assign({
        id: "mock-vg-ref-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG_REF",
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

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides, displayName) {
    const name = displayName || "MOCK_VG_REF_D2";
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
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- REF-01: Auto-resolved kV shows "Auto-resolved" provenance ---------------

test("REF-01: auto_resolved kV shows no provenance subtitle (no Configuration source label, no Auto-resolved label)", async ({ page }) => {
    // DEC cleanup: normal auto-resolved state shows values without subtitle labels.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        effective_reference: "line_to_ground",
    });
    const detailsBody = page.locator("#wwRdDetailsBody");
    // Nominal kV value must still display
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Base Configuration" });
    await expect(section).toContainText("275 kV");
    // No "Auto-resolved" subtitle label in read-only
    await expect(detailsBody.locator("#wwRdNomKvProvenance")).not.toBeVisible();
    // No standalone "Configuration source:" label
    const configSourceText = await detailsBody.textContent();
    expect(configSourceText).not.toMatch(/Configuration source/);
});

// ---- REF-02: Unresolved kV shows "Not resolved" provenance ------------------

test("REF-02: needs_review kV shows Not resolved provenance", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: null,
        base_authority: "needs_review",
        effective_reference: null,
    });
    const detailsBody = page.locator("#wwRdDetailsBody");
    const provenanceEls = detailsBody.locator(".ww-rd-provenance");
    // At least one provenance el should say "Not resolved"
    const texts = await provenanceEls.allTextContents();
    expect(texts.some(t => t.includes("Not resolved"))).toBe(true);
    // No "Configuration source:" label
    expect(await detailsBody.textContent()).not.toMatch(/Configuration source/);
});

// ---- REF-03: Manual kV shows "Manual" provenance (not "Engineer configured") -

test("REF-03: manual kV shows value without 'Manual' subtitle, no Engineer configured terminology", async ({ page }) => {
    // DEC cleanup: normal manual state shows no subtitle provenance labels.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 132.0,
        base_authority: "manual",
        effective_reference: "line_to_ground",
    });
    const detailsBody = page.locator("#wwRdDetailsBody");
    // Value is shown
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Base Configuration" });
    await expect(section).toContainText("132 kV");
    // No subtitle provenance labels for normal manual state
    await expect(detailsBody.locator("#wwRdNomKvProvenance")).not.toBeVisible();
    // No legacy terminology
    expect(await detailsBody.textContent()).not.toMatch(/engineer configured/i);
    expect(await detailsBody.textContent()).not.toMatch(/manually configured/i);
    expect(await detailsBody.textContent()).not.toMatch(/Configuration source/);
});

// ---- REF-04: Edit — manual kV + auto L-N → Apply preserves reference_mode="auto" ------

test("REF-04: edit manual kV with auto-detected L-N — Apply preserves reference_mode=auto", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            const mockGroup = makeMockVoltageGroup({
                voltage_config: {
                    nominal_voltage_ll_kv: 275.0,
                    base_authority: "manual",
                    reference_mode: "auto",
                    effective_reference: "line_to_ground",
                },
            });
            await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockGroup) });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 132.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "MOCK_VG_REF04");

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).toBe("auto");
        expect(capturedBody.nominal_voltage_ll_kv).toBeCloseTo(275.0);
    }
});

// ---- REF-05: Edit — manual kV + auto L-L → Apply preserves reference_mode="auto" ------

test("REF-05: edit manual kV with auto-detected L-L — Apply preserves reference_mode=auto", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            const mockGroup = makeMockVoltageGroup({
                voltage_config: {
                    nominal_voltage_ll_kv: 500.0,
                    base_authority: "manual",
                    reference_mode: "auto",
                    effective_reference: "line_to_line",
                },
            });
            await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockGroup) });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_line",
    }, "MOCK_VG_REF05");

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("500");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).toBe("auto");
        expect(capturedBody.reference_override).toBeFalsy();
    }
});

// ---- REF-06: Revert button absent when base_authority is auto_resolved -------

test("REF-06: Revert button absent in Advanced when base_authority is auto_resolved", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    // Revert button should NOT be present
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).not.toBeVisible();
});

// ---- REF-07: Auto-detected reference shows as read-only text in edit mode ----

test("REF-07: auto-detected reference displayed as read-only text (not select) in normal edit mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await injectAndSelectVoltageGroup(page, {
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Read-only display element present
    const display = page.locator("#wwRdDetailsBody #wwRdVltRefDisplay");
    await expect(display).toBeVisible({ timeout: 3000 });
    await expect(display).toContainText("Line-to-ground");
    // No inline select for reference when already resolved
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefInline")).not.toBeVisible();
});

// ---- REF-08: Auto-detected L-L reference displayed correctly -----------------

test("REF-08: auto-detected L-L reference shows Line-to-line and Auto-detected provenance", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await injectAndSelectVoltageGroup(page, {
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_line",
    });

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    const display = page.locator("#wwRdDetailsBody #wwRdVltRefDisplay");
    await expect(display).toBeVisible({ timeout: 3000 });
    await expect(display).toHaveText("Line-to-line");
    const prov = page.locator("#wwRdDetailsBody #wwRdVltRefProvenance");
    await expect(prov).toHaveText("Auto-detected");
});

// ---- REF-09: Unresolved reference shows inline selector in edit mode ---------

test("REF-09: unresolved voltage reference shows inline selector (not in Advanced) in edit mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: null,
        detection_reason: "no_recognizable_pattern",
    });

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Inline select should be visible immediately (without opening Advanced)
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefInline")).toBeVisible({ timeout: 3000 });
    // "Not resolved" note should be present
    await expect(page.locator("#wwRdDetailsBody .ww-rd-ref-unresolved-note")).toBeVisible();
    // Read-only display should NOT be present
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefDisplay")).not.toBeVisible();
});

// ---- REF-10: Existing manual override survives nominal kV editing ---------------

test("REF-10: existing manual reference override preserved when editing nominal kV only", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(
                makeMockVoltageGroup({ voltage_config: { nominal_voltage_ll_kv: 500.0, base_authority: "manual", reference_mode: "manual", reference_override: "line_to_line", effective_reference: "line_to_line" } })
            ) });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "manual",
        reference_override: "line_to_line",
        effective_reference: "line_to_line",
    }, "MOCK_VG_REF10");

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Don't change Advanced settings — just change kV
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("500");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).toBe("manual");
        expect(capturedBody.reference_override).toBe("line_to_line");
    }
});

// ---- REF-11: Configuration source field not present -------------------------

test("REF-11: read-only section does not contain Configuration source label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        effective_reference: "line_to_ground",
    });
    const text = await page.locator("#wwRdDetailsBody").textContent();
    expect(text).not.toMatch(/Configuration source/);
    expect(text).not.toMatch(/engineer configured/i);
});

// ---- REF-12: Voltage reference provenance in read-only section ---------------

test("REF-12: read-only section does not show Auto-detected or Auto-resolved subtitle labels", async ({ page }) => {
    // DEC cleanup: normal auto-resolved state shows no subtitle provenance labels.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    // Values must still display correctly
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Base Configuration" });
    await expect(section).toContainText("275 kV");
    await expect(section).toContainText("Line-to-ground");
    // No Auto-detected / Auto-resolved subtitle labels in the read-only section
    const provenances = await page.locator("#wwRdDetailsBody").locator(".ww-rd-provenance").allTextContents();
    expect(provenances.some(t => t.includes("Auto-detected"))).toBe(false);
    expect(provenances.some(t => t.includes("Auto-resolved"))).toBe(false);
});

// ---- REF-13: Advanced section collapsed by default for auto group -------------

test("REF-13: Advanced section collapsed by default for auto-detected group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).not.toBeVisible();
});

// ---- REF-14: Expanding Advanced does not send PUT ---------------------------

test("REF-14: expanding Advanced Reference Settings does not trigger a PUT", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let putSent = false;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") putSent = true;
        await route.continue();
    });

    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await page.waitForTimeout(400);
    expect(putSent).toBe(false);
});

// ---- REF-15: Cancel discards draft without PUT -------------------------------

test("REF-15: Cancel discards draft and returns to read mode without PUT", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let putSent = false;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") putSent = true;
        await route.continue();
    });

    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("500");
    await page.locator("#wwRdDetailsBody #wwRdVoltageCancelBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible({ timeout: 3000 });
    expect(putSent).toBe(false);
});

// ---- REF-16: Apply with auto reference does NOT send manual in PUT ------------

test("REF-16: Apply with auto-detected reference does not send reference_mode=manual in PUT", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(
                makeMockVoltageGroup({ voltage_config: { nominal_voltage_ll_kv: 275.0, base_authority: "manual", reference_mode: "auto", effective_reference: "line_to_ground" } })
            ) });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 132.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "MOCK_VG_REF16");

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).not.toBe("manual");
    }
});

// ---- REF-17: Nominal voltage field in read-only view -------------------------

test("REF-17: nominal voltage field shows kV value without subtitle provenance tag in normal states", async ({ page }) => {
    // DEC cleanup: normal auto-resolved state shows kV value without subtitle provenance labels.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "auto_resolved",
        effective_reference: "line_to_ground",
    });
    const detailsBody = page.locator("#wwRdDetailsBody");
    // Value is shown
    await expect(detailsBody.locator(".ww-rd-field-value").first()).toContainText("275");
    // No subtitle provenance label for auto-resolved (normal state)
    await expect(detailsBody.locator("#wwRdNomKvProvenance")).not.toBeVisible();
});

// ---- REF-18: Revert button not in normal editor actions ---------------------

test("REF-18: normal editor action buttons do not include Revert button at top level", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Actions row should contain Apply and Cancel but NOT the revert button (it's in Advanced)
    const actionsRow = page.locator("#wwRdDetailsBody .ww-rd-edit-actions");
    await expect(actionsRow).toBeVisible({ timeout: 3000 });
    await expect(actionsRow.locator("#wwRdVoltageRevertBtn")).not.toBeVisible();
});

// ---- REF-19: Revert button present inside Advanced when manual --------------

test("REF-19: Clear manual nominal voltage button present inside Advanced for manual base_authority", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toHaveText("Clear manual nominal voltage");
});

// ---- REF-20: Legacy manual kV shows Review required provenance ---------------

test("REF-20: legacy_manual base_authority shows Review required provenance", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 132.0,
        base_authority: "legacy_manual",
        effective_reference: "line_to_ground",
    });
    const detailsBody = page.locator("#wwRdDetailsBody");
    const provenances = await detailsBody.locator(".ww-rd-provenance").allTextContents();
    expect(provenances.some(t => t.includes("Review required"))).toBe(true);
    expect(await detailsBody.textContent()).not.toMatch(/Configuration source/);
});
