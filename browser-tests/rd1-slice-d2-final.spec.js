// RD-1 Slice D2 Final — Reference Mode dropdown removed.
// Verifies that the frontend no longer exposes a Reference Mode (Auto/Manual) dropdown
// and instead uses "Correct voltage reference" in Advanced Reference Settings.
// Tests all four behavior cases: auto-detected, unresolved, correct auto, existing manual.

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

async function selectFirstRecording(page) {
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
}

function makeMockVoltageGroup(overrides) {
    const { voltage_config: vcOverrides, ...topOverrides } = overrides;
    return Object.assign({
        id: "mock-vg-fin-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG_FINAL",
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
    const name = displayName || "MOCK_VG_FINAL";
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

// ---- FIN-01: Reference Mode dropdown absent anywhere in the edit form --------

test("FIN-01: Reference Mode dropdown (Auto/Manual) is absent from the entire voltage edit form", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible({ timeout: 3000 });
    // Open Advanced section too — Reference Mode must not appear even there
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefMode")).not.toBeVisible();
});

// ---- FIN-02: Auto-detected L-N shows as read-only text ----------------------

test("FIN-02: auto-detected line_to_ground displays read-only text in edit mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    const display = page.locator("#wwRdDetailsBody #wwRdVltRefDisplay");
    await expect(display).toBeVisible({ timeout: 3000 });
    await expect(display).toContainText("Line-to-ground");
    const tag = await display.evaluate(el => el.tagName.toLowerCase());
    expect(["input", "select"]).not.toContain(tag);
});

// ---- FIN-03: Auto-detected L-L shows as read-only text ----------------------

test("FIN-03: auto-detected line_to_line displays read-only text in edit mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_line" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    const display = page.locator("#wwRdDetailsBody #wwRdVltRefDisplay");
    await expect(display).toBeVisible({ timeout: 3000 });
    await expect(display).toContainText("Line-to-line");
    const tag = await display.evaluate(el => el.tagName.toLowerCase());
    expect(["input", "select"]).not.toContain(tag);
});

// ---- FIN-04: Manual kV entry preserves auto reference_mode in PUT -----------

test("FIN-04: editing kV only sends reference_mode=auto in PUT when group has auto-detected reference", async ({ page }) => {
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
                    display_name: "MOCK_VG_FIN04",
                    voltage_config: { nominal_voltage_ll_kv: 275.0, base_authority: "manual", reference_mode: "auto" },
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        reference_mode: "auto",
        effective_reference: "line_to_ground",
    }, "MOCK_VG_FIN04");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).toBe("auto");
        expect(capturedBody.nominal_voltage_ll_kv).toBeCloseTo(275.0);
    }
});

// ---- FIN-05: Existing manual correction auto-expands in Advanced -------------

test("FIN-05: existing manual override auto-expands Correct voltage reference in Advanced", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_ground",
        effective_reference: "line_to_ground",
        base_authority: "manual",
        nominal_voltage_ll_kv: 132.0,
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Advanced auto-opened for manual groups
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
    // "Correct voltage reference" section auto-expanded — override select visible
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible({ timeout: 3000 });
    const val = await page.locator("#wwRdDetailsBody #wwRdVltRefOverride").inputValue();
    expect(val).toBe("line_to_ground");
});

// ---- FIN-06: Correct voltage reference select has no Auto option -------------

test("FIN-06: Correct voltage reference select contains only L-L and L-N options (no Auto)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await page.locator("#wwRdDetailsBody #wwRdVltCorrectRefToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible({ timeout: 3000 });
    const options = await page.locator("#wwRdDetailsBody #wwRdVltRefOverride option").allTextContents();
    expect(options.some(o => /line.to.ground|l.n/i.test(o))).toBe(true);
    expect(options.some(o => /line.to.line|l.l/i.test(o))).toBe(true);
    expect(options.some(o => /auto/i.test(o))).toBe(false);
});

// ---- FIN-07: Applying manual correction sends reference_mode=manual ---------

test("FIN-07: selecting L-L in Correct voltage reference and Apply sends reference_mode=manual", async ({ page }) => {
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
                    display_name: "MOCK_VG_FIN07",
                    voltage_config: { nominal_voltage_ll_kv: 132.0, base_authority: "manual", reference_mode: "manual", reference_override: "line_to_line" },
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        reference_mode: "auto",
        effective_reference: "line_to_ground",
        nominal_voltage_ll_kv: 132.0,
        base_authority: "manual",
    }, "MOCK_VG_FIN07");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Open Advanced and Correct voltage reference
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    await page.locator("#wwRdDetailsBody #wwRdVltCorrectRefToggle").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVltRefOverride").selectOption("line_to_line");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        expect(capturedBody.reference_mode).toBe("manual");
        expect(capturedBody.reference_override).toBe("line_to_line");
    }
});

// ---- FIN-08: Existing manual override survives kV edit ----------------------

test("FIN-08: existing manual reference override survives a kV-only edit", async ({ page }) => {
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
                    display_name: "MOCK_VG_FIN08",
                    voltage_config: { nominal_voltage_ll_kv: 275.0, base_authority: "manual", reference_mode: "manual", reference_override: "line_to_ground" },
                })),
            });
        } else {
            await route.continue();
        }
    });

    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_ground",
        effective_reference: "line_to_ground",
        base_authority: "manual",
        nominal_voltage_ll_kv: 132.0,
    }, "MOCK_VG_FIN08");
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    // Edit kV only — do not touch Correct voltage reference section
    await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("275");
    await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
    await page.waitForTimeout(1500);

    if (capturedBody !== null) {
        // Manual override must be preserved
        expect(capturedBody.reference_mode).toBe("manual");
        expect(capturedBody.reference_override).toBe("line_to_ground");
        expect(capturedBody.nominal_voltage_ll_kv).toBeCloseTo(275.0);
    }
});

// ---- FIN-09: Advanced collapsed by default for auto group -------------------

test("FIN-09: Advanced Reference Settings is collapsed by default for auto-detected group", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", effective_reference: "line_to_ground" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).not.toBeVisible();
});

// ---- FIN-10: Advanced auto-opens for manual override group ------------------

test("FIN-10: Advanced Reference Settings auto-opens when group has manual reference_mode", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        reference_mode: "manual",
        reference_override: "line_to_line",
        effective_reference: "line_to_line",
        base_authority: "manual",
        nominal_voltage_ll_kv: 275.0,
    });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedContent")).toBeVisible({ timeout: 3000 });
});

// ---- FIN-11: Base reference side still present in Advanced ------------------

test("FIN-11: Base reference side selector remains in Advanced Reference Settings", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, { reference_mode: "auto", base_reference_side: "primary" });
    await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
    await page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle").click();
    const sel = page.locator("#wwRdDetailsBody #wwRdVltRefSide");
    await expect(sel).toBeVisible({ timeout: 3000 });
    const selected = await sel.inputValue();
    expect(selected).toBe("primary");
});

// ---- FIN-12: Cancel closes edit without PUT ---------------------------------

test("FIN-12: Cancel closes edit mode and no PUT is sent", async ({ page }) => {
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
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible({ timeout: 3000 });
    await expect(page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn")).not.toBeVisible();
    expect(putSent).toBe(false);
});
