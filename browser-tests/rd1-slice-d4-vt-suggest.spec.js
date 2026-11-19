// RD-1 Slice D4-suggest — non-persisted VT suggestions from nominal voltage.
// Verifies the 3-state VT section (Suggested / Configured / Not-configured),
// editor prefill from suggestions, Apply saving as manual, and live ratio
// display in the editor using the "X kV / Y V" format.

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
        id: id || "mock-vg-suggest",
        workspace_id: "ws-test",
        source_id: sourceId || "src-test",
        display_name: "MOCK VG SUGGEST",
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
            vt_suggested_primary_v: 275000,
            vt_suggested_secondary_v: 110,
            vt_suggested_ratio: 275000 / 110,
        }, voltageConfigOverrides || {}),
    };
}

async function injectAndSelectVoltageGroup(page, voltageConfigOverrides) {
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const sourceId = groups.length > 0 ? groups[0].source_id : "src-test";
        const mockGroup = makeMockVoltageGroup("mock-vg-suggest", voltageConfigOverrides, sourceId);
        await route.fulfill({ json: [...groups, mockGroup] });
    });
    const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
    await expect(item).toBeVisible({ timeout: 8000 });
    await item.click();
    await expect(page.locator("#wwRdGroupsBody .ww-rd-placeholder")).not.toBeVisible({ timeout: 8000 });
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK VG SUGGEST" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- VS-01: "Suggested" label shown when nominal kV known, VT not configured -

test("VS-01: Suggested label is shown when VT not configured but nominal kV is known", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("Suggested");
});

// ---- VS-02: Suggested section shows 275 kV primary ---------------------------

test("VS-02: Suggested state shows 275 kV primary value", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("275");
});

// ---- VS-03: Suggested section shows ratio as "275 kV / 110 V" ----------------

test("VS-03: Suggested state shows ratio as '275 kV / 110 V' (not colon notation)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("275 kV");
    await expect(section).toContainText("110");
    // Must not show colon-ratio format
    await expect(section).not.toContainText("2500:1");
});

// ---- VS-04: Edit prefills from suggestion (275 kV, 110 V) --------------------

test("VS-04: Edit button prefills primary kV and secondary V from suggestion", async ({ page }) => {
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

// ---- VS-05: Apply saves as manual, "Suggested" label disappears --------------

test("VS-05: applying suggestion saves as manual and removes Suggested label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/voltage-config", async route => {
        if (route.request().method() === "PUT") {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(makeMockVoltageGroup("mock-vg-suggest", {
                    vt_primary_v: 275000,
                    vt_secondary_v: 110,
                    vt_ratio: 275000 / 110,
                    vt_authority: "manual",
                    vt_suggested_primary_v: null,
                    vt_suggested_secondary_v: null,
                    vt_suggested_ratio: null,
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
    await expect(section).not.toContainText("Suggested");
    await expect(section).toContainText("275");
});

// ---- VS-06: Configured VT (275 kV / 100 V) → no "Suggested" label ----------

test("VS-06: existing configured VT shows no Suggested label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        vt_primary_v: 275000,
        vt_secondary_v: 100,
        vt_ratio: 2750,
        vt_authority: "manual",
        vt_suggested_primary_v: null,
        vt_suggested_secondary_v: null,
        vt_suggested_ratio: null,
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).not.toContainText("Suggested");
    await expect(section).toContainText("100");  // secondary V shown
});

// ---- VS-07: Unresolved nominal → "Not configured" (no suggestion) -----------

test("VS-07: unresolved nominal shows Not configured with no Suggested label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {
        nominal_voltage_ll_kv: null,
        base_authority: "needs_review",
        vt_suggested_primary_v: null,
        vt_suggested_secondary_v: null,
        vt_suggested_ratio: null,
    });
    const section = page.locator("#wwRdDetailsBody .ww-rd-section", { hasText: "Voltage Transformer" });
    await expect(section).toContainText("Not configured");
    await expect(section).not.toContainText("Suggested");
});

// ---- VS-08: Live ratio display in editor — "110 kV / 110 V" after typing ----

test("VS-08: live ratio display shows 'X kV / Y V' format while editing", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await injectAndSelectVoltageGroup(page, {});
    await page.locator("#wwRdDetailsBody #wwRdVtEditBtn").click();
    await expect(page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv")).toBeVisible({ timeout: 3000 });
    await page.locator("#wwRdDetailsBody #wwRdVtPrimaryKv").fill("110");
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").fill("110");
    // Trigger input events so live ratio updates
    await page.locator("#wwRdDetailsBody #wwRdVtSecondaryV").dispatchEvent("input");
    const liveRatio = page.locator("#wwRdDetailsBody #wwRdVtLiveRatio");
    await expect(liveRatio).toBeVisible({ timeout: 3000 });
    await expect(liveRatio).toContainText("110 kV");
    await expect(liveRatio).toContainText("110");
});
