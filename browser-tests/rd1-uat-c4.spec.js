// RD-1 UAT-C4: Corrections for Slice C-3 owner UAT.
// UAT-C4-01: remove "N channels:" count prefix from group header.
// UAT-C4-02: Equipment Rating section for all current groups regardless of method.
// Also covers VT/CT section placement (group-type specific, main panel).

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

async function selectFirstGroup(page) {
    const group = page.locator("#wwRdGroupsBody .ww-rd-group-item").first();
    await expect(group).toBeVisible({ timeout: 5000 });
    await group.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

async function selectGroupByKind(page, kind) {
    await page.locator(`#wwRdGroupKindFilter button[data-kind='${kind}']`).click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

function makeMockCurrentGroup(overrides, ref) {
    return Object.assign({
        id: "mock-cg-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_CG",
        kind: "current",
        status: "confirmed",
        channel_refs: [{ channel_name: "IA" }, { channel_name: "IB" }, { channel_name: "IC" }],
        pu_status: overrides.pu_status || "base_required",
        pu_reason: overrides.pu_reason || "current_base_not_configured",
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
            base_authority: "legacy_manual"
        }, overrides.current_config || {})
    }, overrides);
}

// ---- UAT-C4-01 — channel count prefix removed --------------------------------

test("C4-01a: voltage group channel list has no 'N channels:' count prefix", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    const ch = page.locator("#wwRdDetailsBody .ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    // Must NOT contain "N channels:" or "N channel:" prefix
    expect(chText).not.toMatch(/\d+\s+channel/i);
});

test("C4-01b: channel identities visible in header (dot-separated)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    const ch = page.locator("#wwRdDetailsBody .ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    // Channel names are present (uses · separator or "No channels assigned")
    expect(chText.includes("·") || chText.includes("No channels assigned")).toBeTruthy();
});

// ---- UAT-C4-02 — Equipment Rating section for all current groups -------------

test("C4-02a: equipment_rating current group shows Equipment capacity label and MVA value", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockCurrentGroup({
            display_name: "MOCK_CG_EQUIP",
            pu_status: "configured",
            pu_reason: null,
            current_config: {
                method: "equipment_rating",
                equipment_rating_mva: 100,
                linked_voltage_group_id: null,
                manual_voltage_base_kv: null,
                manual_ibase_ka: null,
                resolved_ibase_ka: 0.4374,
                applicable_voltage_ll_kv: 132.0,
                base_reference_side: "primary",
                base_authority: "auto_resolved"
            }
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_CG_EQUIP" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
    expect(labels.some(l => l.includes("Equipment capacity"))).toBeTruthy();
    const values = await page.locator("#wwRdDetailsBody .ww-rd-field-value").allTextContents();
    expect(values.some(v => v.includes("MVA"))).toBeTruthy();
});

test("C4-02b: none-method current group shows Equipment Rating section (not error message)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockCurrentGroup({
            display_name: "MOCK_CG_NONE",
            pu_status: "base_required",
            pu_reason: "current_base_not_configured",
            current_config: {
                method: "none",
                equipment_rating_mva: null,
                linked_voltage_group_id: null,
                manual_voltage_base_kv: null,
                manual_ibase_ka: null,
                resolved_ibase_ka: null,
                applicable_voltage_ll_kv: null,
                base_reference_side: "unknown",
                base_authority: "legacy_manual"
            }
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_CG_NONE" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    // Equipment Rating section heading must be present
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Equipment Rating"))).toBeTruthy();

    // "Per-unit normalisation not configured" error message must NOT appear
    const bodyText = await page.locator("#wwRdDetailsBody").textContent();
    expect(bodyText).not.toContain("Per-unit normalisation not configured");
});

test("C4-02c: none-method current group shows 'Not specified' for equipment capacity", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockCurrentGroup({
            display_name: "MOCK_CG_NONE2",
            current_config: { method: "none", equipment_rating_mva: null }
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_CG_NONE2" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    const values = await page.locator("#wwRdDetailsBody .ww-rd-field-value").allTextContents();
    expect(values.some(v => v.includes("Not specified"))).toBeTruthy();
});

test("C4-02d: manual-method current group shows 'Not derived from equipment rating'", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockCurrentGroup({
            display_name: "MOCK_CG_MANUAL",
            pu_status: "configured",
            pu_reason: null,
            current_config: {
                method: "manual",
                equipment_rating_mva: null,
                manual_ibase_ka: 0.5,
                resolved_ibase_ka: 0.5,
                applicable_voltage_ll_kv: null,
                linked_voltage_group_id: null,
                base_authority: "manual"
            }
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_CG_MANUAL" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    // resolved_ibase_ka comes from manual entry — must NOT show as derived rated current
    const values = await page.locator("#wwRdDetailsBody .ww-rd-field-value").allTextContents();
    expect(values.some(v => v.includes("Not derived from equipment rating"))).toBeTruthy();
});

test("C4-02e: equipment_rating current group shows Derived rated current label", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const mockGroup = makeMockCurrentGroup({
            display_name: "MOCK_CG_DERIVED",
            current_config: {
                method: "equipment_rating",
                equipment_rating_mva: 50,
                resolved_ibase_ka: 0.2187,
                applicable_voltage_ll_kv: 132.0,
                linked_voltage_group_id: "some-vg-id",
                base_authority: "auto_resolved"
            }
        });
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_CG_DERIVED" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
    expect(labels.some(l => l.includes("Derived rated current"))).toBeTruthy();
});

test("C4-02f: voltage group still shows Nominal voltage, Reference, Configuration source, PU availability", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
            expect(labels.some(l => l.includes("Nominal voltage"))).toBeTruthy();
            expect(labels.some(l => l.includes("Voltage reference"))).toBeTruthy();
            expect(labels.some(l => l.includes("Configuration source"))).toBeTruthy();
            // PU availability section present (voltage groups only)
            const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
            expect(headings.some(h => h.includes("Per-unit availability"))).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found in test recording");
});

test("C4-02g: current group main section has no Per-unit availability heading", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");

    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Per-unit availability"))).toBeFalsy();
});

// ---- CT/VT sections (group-type specific, main panel) -----------------------

test("C4-03a: Voltage Group panel shows 'Voltage Transformer (VT)' section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            await expect(page.locator("#wwRdDetailsBody")).toContainText("Voltage Transformer (VT)");
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C4-03b: Current Group panel shows 'Current Transformer (CT)' section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Current Transformer (CT)");
});

test("C4-03c: Voltage Group panel does NOT show 'Current Transformer'", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            const bodyText = await page.locator("#wwRdDetailsBody").textContent();
            expect(bodyText).not.toContain("Current Transformer");
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C4-03d: Current Group panel does NOT show 'Voltage Transformer'", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectGroupByKind(page, "current");
    const bodyText = await page.locator("#wwRdDetailsBody").textContent();
    expect(bodyText).not.toContain("Voltage Transformer");
});

test("C4-03e: VT section shows neutral 'Not configured' when VT ratio is absent", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            // VT ratio field shows neutral "Not configured" text (not warn/error)
            await expect(page.locator("#wwRdDetailsBody")).toContainText("Not configured");
            // The VT ratio value must carry ww-rd-status--neutral (not warn or error)
            const vtSection = page.locator("#wwRdDetailsBody .ww-rd-section:has(.ww-rd-section-heading:has-text('Voltage Transformer'))");
            const vtValue = vtSection.locator(".ww-rd-field-value");
            if (await vtValue.count() > 0) {
                const cls = await vtValue.first().getAttribute("class") || "";
                expect(cls).not.toMatch(/ww-rd-status--warn/);
                expect(cls).not.toMatch(/ww-rd-status--error/);
            }
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C4-narrow: narrow viewport current group equipment rating readable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.locator("#wwRdRecordingList .ww-rd-recording-item").first().click();
    // In narrow mode, navigate to details panel via group selection
    await page.locator(`#wwRdGroupKindFilter button[data-kind='current']`).click();
    const group = page.locator("#wwRdGroupsBody .ww-rd-group-item").first();
    await expect(group).toBeVisible({ timeout: 5000 });
    await group.click();

    // Equipment Rating section must be visible in narrow layout
    await expect(page.locator("#wwRdDetailsBody")).toContainText("Equipment Rating");
    const detailsPanel = page.locator("#wwRdDetailsPanel");
    await expect(detailsPanel).toBeVisible();
    const bbox = await detailsPanel.boundingBox();
    expect(bbox).not.toBeNull();
    expect(bbox.width).toBeGreaterThan(100);
});
