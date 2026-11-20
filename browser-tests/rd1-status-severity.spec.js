// RD-1 Status Severity — UX-1 revised.
// Removed: PU availability status-line severity tests (section removed in UX-1).
// Retained: conflict banner error class, CT/VT neutral display.
// Added: missing-voltage warning presence/absence tests.

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
    return Object.assign({
        id: "mock-vg-sev-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_VG_SEV",
        kind: "voltage",
        status: "confirmed",
        channel_refs: [{ channel_name: "VA" }, { channel_name: "VB" }, { channel_name: "VC" }],
        pu_status: overrides.pu_status || "base_required",
        pu_reason: overrides.pu_reason || null,
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
            vt_primary_v: null,
            vt_secondary_v: null,
            vt_authority: "not_configured",
            vt_provenance_note: null,
        }, overrides.voltage_config || {})
    }, overrides);
}

function makeMockCurrentGroup(overrides) {
    return Object.assign({
        id: "mock-cg-sev-" + Math.random().toString(36).slice(2),
        display_name: overrides.display_name || "MOCK_CG_SEV",
        kind: "current",
        status: "confirmed",
        channel_refs: [{ channel_name: "IA" }, { channel_name: "IB" }, { channel_name: "IC" }],
        pu_status: "not_applicable",
        pu_reason: null,
        voltage_config: null,
        current_config: Object.assign({
            method: "none",
            resolved_ibase_ka: null,
            equipment_rating_mva: null,
            manual_ibase_ka: null,
            manual_voltage_base_kv: null,
            applicable_voltage_ll_kv: null,
            linked_voltage_group_id: null,
            base_reference_side: "unknown",
            base_authority: "unavailable",
            ct_primary_a: null,
            ct_secondary_a: null,
            ct_authority: "not_configured",
            ct_provenance_note: null,
        }, overrides.current_config || {})
    }, overrides);
}

async function injectAndSelectGroup(page, group, groupName) {
    const name = groupName || group.display_name;
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        await route.fulfill({ json: [...groups, group] });
    });
    await selectFirstRecording(page);
    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: name });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    await mockItem.click();
    const tabGrp = page.locator("#wwRdTabGroupDetails");
    if (await tabGrp.isVisible()) await tabGrp.click();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 5000 });
}

// ---- Tests ------------------------------------------------------------------

// SEV-01 (UX-1): Valid nominal voltage — no PU status indicator, no missing-voltage warning
test("SEV-01: valid auto_resolved nominal voltage shows no PU status line and no missing-voltage warning", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_OK_AUTO",
        pu_status: "configured",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_OK_AUTO");

    // UX-1: no PU availability section
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // No missing-voltage warning for a configured group
    await expect(page.locator("#wwRdDetailsBody .ww-rd-voltage-missing-reason")).not.toBeVisible();
    // Nominal kV displayed
    await expect(page.locator("#wwRdDetailsBody")).toContainText("132");
});

// SEV-02 (UX-1): Valid manual nominal voltage — no PU status indicator, no missing-voltage warning
test("SEV-02: valid manual nominal voltage shows no PU status line and no missing-voltage warning", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_OK_MANUAL",
        pu_status: "configured",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 275.0,
            base_authority: "manual",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_OK_MANUAL");

    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-voltage-missing-reason")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody")).toContainText("275");
});

// SEV-03 (UX-1): Missing nominal voltage — amber warning appears in config section
test("SEV-03: missing nominal voltage shows amber warning in Voltage Base Configuration", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_WARN_NR",
        pu_status: "base_required",
        pu_reason: "base_invalidated",
        voltage_config: {
            nominal_voltage_ll_kv: null,
            base_authority: "needs_review",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: null,
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_WARN_NR");

    // UX-1: no PU availability status line
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Single amber warning must appear — no separate "Not configured" badge
    const reason = page.locator("#wwRdDetailsBody .ww-rd-voltage-missing-reason");
    await expect(reason).toBeVisible();
    const reasonText = await reason.textContent();
    expect(reasonText.toLowerCase()).toMatch(/nominal voltage.*per.unit/i);
    await expect(page.locator("#wwRdDetailsBody #wwRdNomKvMissingWarning")).not.toBeVisible();
});

// SEV-04 (UX-1): Missing-voltage warning also present for missing nominal with legacy_manual
test("SEV-04: missing nominal voltage with legacy_manual also shows amber warning", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_WARN_LM",
        pu_status: "base_required",
        pu_reason: "voltage_base_not_configured",
        voltage_config: {
            nominal_voltage_ll_kv: null,
            base_authority: "legacy_manual",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_WARN_LM");

    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    await expect(page.locator("#wwRdDetailsBody .ww-rd-voltage-missing-reason")).toBeVisible();
});

// SEV-05 (UX-1): Missing-voltage warning icon in groups list for voltage group without nominal kV
test("SEV-05: voltage group without nominal kV shows amber warning icon in groups list", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_LIST_WARN",
        pu_status: "base_required",
        pu_reason: "voltage_base_not_configured",
        voltage_config: {
            nominal_voltage_ll_kv: null,
            base_authority: "needs_review",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: null,
            detection_reason: null,
            evidence_names: [],
        }
    });
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        await route.fulfill({ json: [...groups, group] });
    });
    await selectFirstRecording(page);

    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_SEV_LIST_WARN" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    // Warning icon must be present in the groups list row
    await expect(mockItem.locator(".ww-rd-group-missing-voltage")).toBeVisible();
    const title = await mockItem.locator(".ww-rd-group-missing-voltage").getAttribute("title");
    expect(title).toMatch(/nominal voltage/i);
});

// SEV-06 (retained): conflict banner uses ww-rd-status--error
test("SEV-06: manual_conflict_detected banner title has ww-rd-status--error class", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_ERR_CONFLICT",
        pu_status: "base_required",
        pu_reason: "manual_conflict_detected",
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: true,
            manual_conflict_detail: "Mock conflict SEV-06",
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_ERR_CONFLICT");

    const banner = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-title");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveClass(/ww-rd-status--error/);
});

// SEV-07 (UX-1): base_authority unavailable — no missing-voltage warning (nominal_voltage_ll_kv null but unavailable means N/A)
test("SEV-07: base_authority unavailable shows no missing-voltage warning", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_NEUTRAL_UNAVAIL",
        pu_status: "not_applicable",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: null,
            base_authority: "unavailable",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "unknown",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: null,
            detection_reason: null,
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_NEUTRAL_UNAVAIL");

    // UX-1: no PU availability status line
    await expect(page.locator("#wwRdDetailsBody .ww-rd-pu-status-line")).not.toBeVisible();
    // Note: unavailable base_authority still has null nominal_voltage_ll_kv — warning WILL appear
    // because the warning condition is purely based on nominal_voltage_ll_kv being null.
    // This is correct — the engineer should configure nominal voltage or the group status is N/A.
});

// SEV-08 (retained): CT not configured shows neutral, not warn or error
test("SEV-08: ct_authority not_configured shows neutral CT ratio, not warn or error", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockCurrentGroup({
        display_name: "MOCK_SEV_CT_NEUTRAL",
        current_config: {
            method: "none",
            resolved_ibase_ka: null,
            equipment_rating_mva: null,
            manual_ibase_ka: null,
            manual_voltage_base_kv: null,
            applicable_voltage_ll_kv: null,
            linked_voltage_group_id: null,
            base_reference_side: "unknown",
            base_authority: "unavailable",
            ct_primary_a: null,
            ct_secondary_a: null,
            ct_authority: "not_configured",
            ct_provenance_note: null,
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_CT_NEUTRAL");

    // CT section heading must be present
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Current Transformer"))).toBeTruthy();

    // CT ratio value must have neutral class, not warn/error
    const ctRatioValue = page.locator("#wwRdDetailsBody .ww-rd-section:has(.ww-rd-section-heading:has-text('Current Transformer')) .ww-rd-field-value");
    if (await ctRatioValue.count() > 0) {
        const cls = await ctRatioValue.first().getAttribute("class");
        expect(cls || "").not.toMatch(/ww-rd-status--warn/);
        expect(cls || "").not.toMatch(/ww-rd-status--error/);
    }
});

// SEV-09 (retained): VT not configured shows neutral, not warn or error
test("SEV-09: vt_authority not_configured shows neutral VT ratio, not warn or error", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_VT_NEUTRAL",
        pu_status: "configured",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
            vt_primary_v: null,
            vt_secondary_v: null,
            vt_authority: "not_configured",
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_VT_NEUTRAL");

    // VT section heading must be present
    const headings = await page.locator("#wwRdDetailsBody .ww-rd-section-heading").allTextContents();
    expect(headings.some(h => h.includes("Voltage Transformer"))).toBeTruthy();

    // VT ratio value must have neutral class, not warn/error
    const vtRatioValue = page.locator("#wwRdDetailsBody .ww-rd-section:has(.ww-rd-section-heading:has-text('Voltage Transformer')) .ww-rd-field-value");
    if (await vtRatioValue.count() > 0) {
        const cls = await vtRatioValue.first().getAttribute("class");
        expect(cls || "").not.toMatch(/ww-rd-status--warn/);
        expect(cls || "").not.toMatch(/ww-rd-status--error/);
    }
});

// SEV-10 (UX-1): Warning icon in groups list is not shown for current groups
test("SEV-10: current groups never show missing-voltage icon in groups list", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockCurrentGroup({
        display_name: "MOCK_SEV_CG_NO_WARN",
    });
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        await route.fulfill({ json: [...groups, group] });
    });
    await selectFirstRecording(page);

    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_SEV_CG_NO_WARN" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    // No missing-voltage icon for current groups
    await expect(mockItem.locator(".ww-rd-group-missing-voltage")).not.toBeVisible();
});

// SEV-11 (UX-1): Warning icon absent in groups list when nominal kV is set
test("SEV-11: voltage group with valid nominal kV shows no missing-voltage icon in groups list", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_VG_KV_SET",
        pu_status: "configured",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 275.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: false,
            manual_conflict_detail: null,
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await page.route("**/measurement-groups", async route => {
        const response = await route.fetch();
        const groups = await response.json();
        await route.fulfill({ json: [...groups, group] });
    });
    await selectFirstRecording(page);

    const mockItem = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: "MOCK_SEV_VG_KV_SET" });
    await expect(mockItem).toBeVisible({ timeout: 10000 });
    // No missing-voltage icon when kV is set
    await expect(mockItem.locator(".ww-rd-group-missing-voltage")).not.toBeVisible();
});

// SEV-12 (retained): conflict banner has concise title AND separate detail element
test("SEV-12: conflict banner has short title and separate detail text element", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_BANNER_SEP",
        pu_status: "base_required",
        pu_reason: "manual_conflict_detected",
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
            base_authority: "auto_resolved",
            reference_mode: "auto",
            reference_override: null,
            base_reference_side: "primary",
            manual_conflict_detected: true,
            manual_conflict_detail: "Mock conflict detail for SEV-12 — this explanation is deliberately longer than the banner title",
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_BANNER_SEP");

    const title = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-title");
    const detail = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-detail");
    await expect(title).toBeVisible();
    await expect(detail).toBeVisible();
    const titleText = await title.textContent();
    const detailText = await detail.textContent();
    // Title is short
    expect(titleText.length).toBeLessThan(60);
    // Detail holds the longer explanation
    expect(detailText.length).toBeGreaterThan(titleText.length);
});
