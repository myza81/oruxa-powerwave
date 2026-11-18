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

test("C3-01: group name visible and channels as dot-separated list with count prefix", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // Group name present
    await expect(page.locator("#wwRdDetailsBody .ww-rd-details-group-name").first()).toBeVisible();
    // Channel list present and uses · separator with count prefix
    const ch = page.locator("#wwRdDetailsBody .ww-rd-details-channels").first();
    await expect(ch).toBeVisible();
    const chText = await ch.textContent();
    // Should use "N channels: Ch1 · Ch2" or "No channels assigned"
    expect(chText.includes("·") || chText.includes("No channels assigned") || /\d+ channel/.test(chText)).toBeTruthy();
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

test("C3-04: Configuration source field present in Voltage Base Configuration section", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // Use voltage group specifically — Configuration source is a voltage-group field
    await selectGroupByKind(page, "voltage");

    const labels = await page.locator("#wwRdDetailsBody .ww-rd-field-label").allTextContents();
    const hasConfigSrc = labels.some(l => l.includes("Configuration source"));
    expect(hasConfigSrc).toBeTruthy();
});

test("C3-05: Per-unit availability section present for voltage group with status word and reason paragraph", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // Per-unit availability is only shown for voltage groups
    await selectGroupByKind(page, "voltage");

    // Section heading
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasPuHeading = headings.some(h => h.includes("Per-unit availability"));
    expect(hasPuHeading).toBeTruthy();
    // Status line icon+word
    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line").first();
    await expect(statusLine).toBeVisible();
    const statusText = await statusLine.textContent();
    // Contains one of the known status words
    const knownWords = ["Available", "Unavailable", "Blocked", "Review required", "Not applicable"];
    expect(knownWords.some(w => statusText.includes(w))).toBeTruthy();
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

    const statusText = await page.locator("#wwRdDetailsBody .ww-rd-pu-status-line").first().textContent();
    expect(statusText).toContain("Available");
    // Status word must be shown via .ww-rd-pu-word--eligible (not inside a .ww-rd-pu-pill)
    const eligibleWord = page.locator("#wwRdDetailsBody .ww-rd-pu-word--eligible");
    await expect(eligibleWord).toBeVisible();
    const pillCount = await page.locator("#wwRdDetailsBody .ww-rd-pu-pill .ww-rd-pu-word--eligible").count();
    expect(pillCount).toBe(0);
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine.first()).toBeVisible({ timeout: 5000 });
    const statusText = await statusLine.first().textContent();
    expect(statusText.trim()).toContain("Blocked");
    // The reason text "conflicts with" belongs in the reason paragraph, not the status word
    expect(statusText).not.toContain("conflicts with");
});

test("C3-08: No standalone CT/VT section; Instrument transformers in Engineering Evidence", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    await selectFirstGroup(page);

    // No standalone CT/VT section heading
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    const hasCTVTSection = headings.some(h => /^CT\s*\/\s*VT$/i.test(h.trim()));
    expect(hasCTVTSection).toBeFalsy();

    // Instrument transformers note exists inside Engineering Evidence
    const evidenceDetails = page.locator("#wwRdDetailsBody details.ww-rd-evidence").first();
    await evidenceDetails.locator("summary").click(); // open it
    await expect(evidenceDetails.locator(".ww-rd-evidence-body")).toBeVisible({ timeout: 3000 });
    await expect(evidenceDetails).toContainText("Instrument transformers");
});

test("C3-09: Current group shows Current Group section heading (new equipment-capacity design)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);
    await selectFirstRecording(page);
    // Use kind filter to select a current group
    await selectGroupByKind(page, "current");

    const details = page.locator("#wwRdDetailsBody");
    // Section heading is "Current Group" for all current group methods
    await expect(details).toContainText("Current Group");
    // Per-unit availability section must NOT appear (current groups use Calculated Channels)
    await expect(details.locator(".ww-rd-pu-status-line")).not.toBeVisible();
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
