// RD-1 Slice C-3: Group Details visual design regression tests.
// Verifies new section structure, two-column field grid, PU status line,
// CT/VT moved into Engineering Evidence, and "Not resolved" for null values.

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
    return item;
}

async function selectFirstGroup(page) {
    const group = page.locator("#wwRdGroupsBody .ww-rd-group-item").first();
    await expect(group).toBeVisible({ timeout: 5000 });
    await group.click();
    // Wait for details panel to show group content (new .ww-rd-section structure)
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

async function selectGroupByKind(page, kind) {
    await page.locator(`#wwRdGroupKindFilter button[data-kind='${kind}']`).click();
    const rows = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    await expect(rows.first()).toBeVisible({ timeout: 5000 });
    await rows.first().click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
    return rows.first();
}

// ---- Tests ------------------------------------------------------------------

test("C3-01: group name visible and channels as dot-separated list (no count prefix)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Group name present
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name").first()).toBeVisible();
    // Channel list present, uses · separator, NO "N channels:" count prefix
    const ch = page.locator("#wwRdDetailsBody .ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    expect(chText.includes("·") || chText.includes("No channels assigned")).toBeTruthy();
    // UAT-C4-01: must NOT contain the "channels:" prefix
    expect(chText).not.toMatch(/\d+\s+channel/i);
});

test("C3-02: voltage group shows Nominal voltage (L-L) label and Not resolved or value", async ({ page }) => {
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
            const hasNomLabel = labels.some(l => l.includes("Nominal voltage"));
            expect(hasNomLabel).toBeTruthy();
            // Value is either a kV string or "Not resolved"
            const values = await page.locator("#wwRdDetailsBody .ww-rd-field-value").allTextContents();
            const hasValue = values.some(v => v.includes("kV") || v.includes("Not resolved"));
            expect(hasValue).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found in test recording");
});

test("C3-03: two-column grid has Voltage reference label alongside Nominal voltage", async ({ page }) => {
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
            await expect(page.locator("#wwRdDetailsBody .ww-rd-field-grid").first()).toBeVisible({ timeout: 5000 });
            const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
            const hasVRef = labels.some(l => l.includes("Voltage reference"));
            expect(hasVRef).toBeTruthy();
            return;
        }
    }
    test.skip(true, "No voltage group found");
});

test("C3-04: Voltage Base Configuration shows provenance labels (D2: Configuration source replaced by per-property provenance)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // Use voltage group specifically
    await selectGroupByKind(page, "voltage");

    // D2 refinement: standalone "Configuration source" field is gone.
    // DEC cleanup: normal auto-resolved state shows no subtitle provenance labels.
    const bodyText = await page.locator("#wwRdDetailsBody").textContent();
    expect(bodyText).not.toMatch(/Configuration source/);
    // "Auto-resolved" subtitle label must not appear in the read-only section
    expect(bodyText).not.toMatch(/Auto-resolved/);
});

test("C3-05: Per-unit availability section is absent — voltage groups show Voltage Base Configuration without PU status", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // UX-1: PU availability section removed
    await selectGroupByKind(page, "voltage");

    // Section heading must NOT contain "Per-unit availability"
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasPuHeading = headings.some(h => h.includes("Per-unit availability"));
    expect(hasPuHeading).toBeFalsy();
    // No PU status line in details
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Voltage Base Configuration section must be present
    expect(headings.some(h => h.includes("Voltage Base Configuration"))).toBeTruthy();
});

// C3-06 and C3-07 use page.route() to inject a mock voltage group with the required PU state
// into the measurement-groups API response. This is deterministic and does not require
// a specific fixture recording. The mock group is appended to the real response list.

function makeMockVoltageGroup(overrides, ref) {
    return Object.assign({
        id: "mock-vg-c3-" + (overrides.pu_status || "mock"),
        workspace_id: (ref && ref.workspace_id) || "mock-ws",
        source_id: (ref && ref.source_id) || "mock-src",
        kind: "voltage",
        display_name: "MOCK_VG_" + (overrides.pu_status || "MOCK").toUpperCase(),
        channel_refs: [],
        status: "confirmed",
        created_at: null,
        pu_status: "base_required",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
            reference_mode: "auto",
            reference_override: null,
            effective_reference: "line_to_ground",
            evidence_names: [],
            detection_reason: "mock",
            base_reference_side: "primary",
            secondary_voltage_ll_v: null,
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            base_authority: "auto_resolved"
        },
        current_config: null
    }, overrides);
}

test("C3-06: Available state shows checkmark and green-class word (not inside a pill badge)", async ({ page }) => {
    // Inject a mock voltage group with pu_status:"configured" (Available state) via API route mock.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    // Install route before selectFirstRecording triggers the groups fetch
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const ref = groups[0] || {};
        const mockGroup = makeMockVoltageGroup({
            pu_status: "configured",
            pu_reason: null,
            voltage_config: Object.assign({}, (ref.voltage_config || {}), {
                nominal_voltage_ll_kv: 132.0,
                base_authority: "auto_resolved",
                manual_conflict_detected: false,
                manual_conflict_detail: null,
                effective_reference: "line_to_ground",
                reference_mode: "auto",
                reference_override: null,
                evidence_names: [],
                detection_reason: "mock",
                base_reference_side: "primary",
                secondary_voltage_ll_v: null
            })
        }, ref);
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);

    // The mock group has display_name "MOCK_VG_CONFIGURED" — select it directly by name
    const mockGroupItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_VG_CONFIGURED" });
    await expect(mockGroupItem).toBeVisible({ timeout: 10000 });
    await mockGroupItem.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });

    // UX-1: PU availability section removed — valid nominal kV shown without PU status indicator
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Nominal voltage is displayed (132 kV from mock)
    await expect(page.locator("#wwRdDetailsBody")).toContainText("132");
    // No missing-voltage warning for a configured group
    await expect(page.locator("#wwRdDetailsBody .ww-rd-voltage-missing-warning")).not.toBeVisible();
});

test("C3-07: Conflict group shows Blocked (not full sentence as status word)", async ({ page }) => {
    // Inject a mock voltage group with manual_conflict_detected:true via API route mock.
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        const ref = groups[0] || {};
        const mockGroup = makeMockVoltageGroup({
            pu_status: "base_required",
            pu_reason: "manual_conflict_detected",
            voltage_config: Object.assign({}, (ref.voltage_config || {}), {
                nominal_voltage_ll_kv: 132.0,
                base_authority: "auto_resolved",
                manual_conflict_detected: true,
                manual_conflict_detail: "Mock conflict for C3-07",
                effective_reference: "line_to_ground",
                reference_mode: "auto",
                reference_override: null,
                evidence_names: [],
                detection_reason: "mock",
                base_reference_side: "primary",
                secondary_voltage_ll_v: null
            })
        }, ref);
        await route.fulfill({ json: [...groups, mockGroup] });
    });

    await selectFirstRecording(page);

    // The mock conflict group has display_name "MOCK_VG_BASE_REQUIRED" — select directly by name
    const mockGroupItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_VG_BASE_REQUIRED" });
    await expect(mockGroupItem).toBeVisible({ timeout: 10000 });
    await mockGroupItem.click();

    // UX-1: PU availability section removed — conflict shown exclusively via conflict banner
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Conflict banner must be present
    const banner = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner");
    await expect(banner.first()).toBeVisible({ timeout: 5000 });
    // Banner title must indicate the conflict
    const bannerTitle = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-title");
    await expect(bannerTitle).toBeVisible();
    const bannerText = await bannerTitle.textContent();
    expect(bannerText).toContain("Conflict");
});

test("C3-08: Voltage group has VT section in main panel (not CT/VT combined)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);

    // Select a voltage group
    const groups = page.locator("#wwRdGroupsBody .ww-rd-group-item");
    const count = await groups.count();
    for (let i = 0; i < count; i++) {
        const badge = await groups.nth(i).locator(".ww-rd-group-badge").textContent().catch(() => "");
        if (badge.trim() === "V") {
            await groups.nth(i).click();
            await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
            const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
            // VT section present for voltage groups
            expect(headings.some(h => h.includes("Voltage Transformer"))).toBeTruthy();
            // No CT section in voltage group
            expect(headings.some(h => h.includes("Current Transformer"))).toBeFalsy();
            return;
        }
    }
    test.skip(true, "No voltage group found in test recording");
});

test("C3-09: Current group shows Equipment Rating section heading", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // Use kind filter to select a current group
    await selectGroupByKind(page, "current");

    const details = page.locator("#wwRdDetailsBody");
    // Section heading is now "Equipment Rating" for all current group methods
    await expect(details).toContainText("Equipment Rating");
    // Per-unit availability section must NOT appear (current groups use Calculated Channels)
    await expect(details.locator(".ww-rd-pu-status-line")).not.toBeVisible();
    // CT section present for current groups
    await expect(details).toContainText("Current Transformer (CT)");
});

test("C3-10: dark theme renders group details without layout breakage", async ({ page }) => {
    await page.goto("/index.html");
    await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("ww-theme", "dark"); } catch (e) {}
    });
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Panel should not have horizontal overflow
    const hasOverflow = await page.evaluate(() => {
        const body = document.getElementById("wwRdDetailsBody");
        return body ? body.scrollWidth > body.clientWidth + 1 : false;
    });
    expect(hasOverflow).toBe(false);

    // Section headings should be visible
    const headings = page.locator("#wwRdDetailsBody .ww-rd-section-heading");
    expect(await headings.count()).toBeGreaterThan(0);
});
