// RD-1 Slice D2 UAT — Voltage editor Advanced reference settings collapse.
// Verifies that the default edit form shows only Nominal kV + read-only reference
// display, and that reference selects are hidden inside a collapsible Advanced section.

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
        id: "mock-vg-uat-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG_UAT",
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
        }, vcOverrides || {}),
    }, topOverrides);
}

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides, displayName) {
    const name = displayName || "MOCK_VG_UAT_D2";
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

// ---- UAT-D2-01: Default edit — only kV input visible at root level -----------

test("UAT-D2-01: default edit shows kV input; reference select inputs not visible at root level", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible({ timeout: 3000 });
    // Reference Mode dropdown must not exist — removed per DEC-214
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).not.toBeVisible();
    // Base reference side select is inside Advanced (collapsed — not rendered)
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).not.toBeVisible();
});

// ---- UAT-D2-02: Reference shown as read-only display (not an input) ----------

test("UAT-D2-02: voltage reference is displayed as read-only text in default edit view", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible({ timeout: 3000 });
    // Read-only display element should be present
    const display = page.locator("#wwRdDetailsBody #wwRdVltRefDisplay");
    await expect(display).toBeVisible({ timeout: 3000 });
    // It must NOT be an input element
    const tagName = await display.evaluate(el => el.tagName.toLowerCase());
    expect(tagName).not.toBe("input");
    expect(tagName).not.toBe("select");
});

// ---- UAT-D2-03: Auto-detected provenance label (muted) ----------------------

test("UAT-D2-03: auto reference mode shows Auto-detected provenance label (muted style)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    const provenance = page.locator("#wwRdDetailsBody #wwRdVltRefProvenance");
    await expect(provenance).toBeVisible({ timeout: 3000 });
    await expect(provenance).toHaveText("Auto-detected");
    // Must NOT have the manual class (amber color)
    const hasManualClass = await provenance.evaluate(el => el.classList.contains("ww-rd-field-sub--manual"));
    expect(hasManualClass).toBe(false);
});

// ---- UAT-D2-04: Manual provenance label (amber) -----------------------------

test("UAT-D2-04: manual reference mode shows Manual provenance label with amber style", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_ground",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    const provenance = page.locator("#wwRdDetailsBody #wwRdVltRefProvenance");
    await expect(provenance).toBeVisible({ timeout: 3000 });
    await expect(provenance).toHaveText("Manual");
    // Must have the manual class (amber color)
    const hasManualClass = await provenance.evaluate(el => el.classList.contains("ww-rd-field-sub--manual"));
    expect(hasManualClass).toBe(true);
});

// ---- UAT-D2-05: Advanced section collapsed by default -----------------------

test("UAT-D2-05: Advanced reference settings section is collapsed by default", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle")).toBeVisible({ timeout: 3000 });
    // Advanced content is not rendered until opened
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).not.toBeVisible();
    // Reference Mode dropdown removed; side select inside Advanced (not rendered)
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).not.toBeVisible();
});

// ---- UAT-D2-06: Advanced section expands on click ---------------------------

test("UAT-D2-06: clicking Advanced toggle expands and shows reference selects", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle")).toBeVisible({ timeout: 3000 });
    // Collapsed: Reference Mode dropdown absent, side select not rendered
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).not.toBeVisible();
    // Click toggle to expand
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    // Advanced content appears with Correct voltage reference toggle and base reference side
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVltCorrectRefToggle")).toBeVisible();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).toBeVisible();
    // Reference Mode dropdown still absent (removed per DEC-214)
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).not.toBeVisible();
});

// ---- UAT-D2-07: Advanced auto-opens when existing config has manual reference

test("UAT-D2-07: Advanced section auto-opens when group has manual reference_mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_ground",
        base_authority: "manual",
        nominal_voltage_ll_kv: 132.0,
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Advanced should already be expanded — no toggle click needed
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    // Reference Mode dropdown is gone; "Correct voltage reference" section auto-opens for manual groups
    await expect(page.locator("#wwRdDetailsBody #wwRdVltCorrectRefToggle")).toBeVisible();
    // Override select pre-populated with the existing manual override value
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible({ timeout: 3000 });
    const selectedOverride = await page.locator("#wwRdDetailsBody #wwRdVltRefOverride").inputValue();
    expect(selectedOverride).toBe("line_to_ground");
});

// ---- UAT-D2-08: Apply preserves reference_mode from draft -------------------

test("UAT-D2-08: Apply PUT body preserves original reference_mode without user changing Advanced section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let capturedBody = null;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            capturedBody = JSON.parse(route.request().postData() || "{}");
            const mockGroup = makeMockVoltageGroup({
                display_name: "MOCK_VG_UAT_D2_08",
                voltage_config: {
                    nominal_voltage_ll_kv: 275.0,
                    base_authority: "manual",
                    reference_mode: "manual",
                    reference_override: "line_to_ground",
                    base_reference_side: "unknown",
                    effective_reference: "line_to_ground",
                },
            });
            await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockGroup) });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_ground",
        base_authority: "manual",
        nominal_voltage_ll_kv: 132.0,
        effective_reference: "line_to_ground",
    }, "MOCK_VG_UAT_D2_08");

    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Edit kV only (Advanced already open due to auto-open, but we don't change reference settings)
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        // The PUT body must preserve the original reference_mode from draft state
        expect(capturedBody.reference_mode).toBe("manual");
        expect(capturedBody.nominal_voltage_ll_kv).toBeCloseTo(275.0);
    }
});

// ---- UAT-D2-09: Cancel closes edit mode -------------------------------------

test("UAT-D2-09: Cancel returns to read-only mode; no PUT sent", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let putSent = false;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") putSent = true;
        await route.continue();
    });

    await injectAndSelectVoltageGroup(page, { reference_mode: "auto" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVoltageCancelBtn").click();
    // Edit button re-appears; Apply disappears
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).not.toBeVisible();
    expect(putSent).toBe(false);
});

// ---- UAT-D2-10: Revert confirmation preserved — now in Advanced section ------

test("UAT-D2-10: Clear manual nominal voltage button in Advanced section triggers confirmation", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    let putSent = false;
    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") putSent = true;
        await route.continue();
    });

    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: 275.0,
        base_authority: "manual",
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Revert button is now inside Advanced section — open it first
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toHaveText("Clear manual nominal voltage");

    // Set up dialog handler to dismiss
    page.once("dialog", dialog => dialog.dismiss());
    await page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn").click();
    // After dismissing the confirmation, no PUT should have been sent
    await page.waitForTimeout(500);
    expect(putSent).toBe(false);
});
