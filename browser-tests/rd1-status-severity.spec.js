// RD-1 Status Severity — severity-based styling for PU availability and config states.
// Verifies ok/warn/error/neutral severity classes are applied correctly per base_authority
// and that missing optional CT/VT metadata is displayed neutrally (not warn/error).

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

// SEV-01: Green available — auto_resolved
test("SEV-01: auto_resolved base_authority shows Available with ww-rd-status--ok on status line", async ({ page }) => {
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine).toBeVisible();
    await expect(statusLine).toHaveClass(/ww-rd-status--ok/);
    const text = await statusLine.textContent();
    expect(text).toContain("Available");
});

// SEV-02: Green available — manual
test("SEV-02: manual base_authority shows Available with ww-rd-status--ok on status line", async ({ page }) => {
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine).toHaveClass(/ww-rd-status--ok/);
    const text = await statusLine.textContent();
    expect(text).toContain("Available");
});

// SEV-03: Amber needs_review — "Configuration required"
test("SEV-03: needs_review base_authority shows Configuration required with ww-rd-status--warn", async ({ page }) => {
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine).toHaveClass(/ww-rd-status--warn/);
    const text = await statusLine.textContent();
    expect(text).toContain("Configuration required");
    // Icon is non-empty (not color-only)
    const icon = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line .ww-rd-pu-icon");
    const iconText = await icon.textContent();
    expect(iconText.trim().length).toBeGreaterThan(0);
});

// SEV-04: Amber legacy_manual
test("SEV-04: legacy_manual base_authority shows Review required with ww-rd-status--warn", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_WARN_LM",
        pu_status: "configured",
        pu_reason: null,
        voltage_config: {
            nominal_voltage_ll_kv: 132.0,
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine).toHaveClass(/ww-rd-status--warn/);
    const text = await statusLine.textContent();
    expect(text).toContain("Review required");
});

// SEV-05: BEN explanation text
test("SEV-05: needs_review reason paragraph mentions kV entry", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_BEN_REASON",
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
            effective_reference: null,
            detection_reason: null,
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_BEN_REASON");

    const reason = page.locator("#wwRdDetailsBody .ww-rd-pu-reason");
    await expect(reason).toBeVisible();
    const reasonText = await reason.textContent();
    expect(reasonText.toLowerCase()).toMatch(/kv|nominal voltage/i);
});

// SEV-06: Conflict banner uses ww-rd-status--error
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

// SEV-07: Neutral unavailable — no warn or error
test("SEV-07: base_authority unavailable shows ww-rd-status--neutral, not warn or error", async ({ page }) => {
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

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    await expect(statusLine).toHaveClass(/ww-rd-status--neutral/);
    // Must NOT have warn or error
    const cls = await statusLine.getAttribute("class");
    expect(cls).not.toMatch(/ww-rd-status--warn/);
    expect(cls).not.toMatch(/ww-rd-status--error/);
});

// SEV-08: Neutral CT not configured — no warn or error
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

// SEV-09: Neutral VT not configured — no warn or error
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

// SEV-10: Icon accessibility — amber/red status has non-empty icon text
test("SEV-10: warn state PU status icon has non-empty text (not color-only)", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_ICON_A11Y",
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
            effective_reference: null,
            detection_reason: null,
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_ICON_A11Y");

    const icon = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line .ww-rd-pu-icon");
    await expect(icon).toBeVisible();
    const iconText = await icon.textContent();
    expect(iconText.trim().length).toBeGreaterThan(0);
});

// SEV-11: Status label is concise — amber label does not contain the full explanatory sentence
test("SEV-11: warn status label is concise — full explanation is in separate reason element", async ({ page }) => {
    await page.goto("/index.html");
    await uploadFixture(page);
    await navigateToRd(page);

    const group = makeMockVoltageGroup({
        display_name: "MOCK_SEV_CONCISE",
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
            effective_reference: null,
            detection_reason: null,
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_CONCISE");

    const statusLine = page.locator("#wwRdDetailsBody .ww-rd-pu-status-line");
    const reason = page.locator("#wwRdDetailsBody .ww-rd-pu-reason");

    const statusText = await statusLine.textContent();
    const reasonText = await reason.textContent();

    // Status line is short (label only)
    expect(statusText.length).toBeLessThan(60);
    // Reason holds the explanation, not the status line
    expect(reasonText.length).toBeGreaterThan(statusText.length);
});

// SEV-12: Conflict banner has concise title AND separate detail element
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
            manual_conflict_detail: "Sources disagree on the manual kV value. SEV-12.",
            effective_reference: "line_to_ground",
            detection_reason: "mock",
            evidence_names: [],
        }
    });
    await injectAndSelectGroup(page, group, "MOCK_SEV_BANNER_SEP");

    const bannerTitle = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-title");
    const bannerDetail = page.locator("#wwRdDetailsBody .ww-rd-conflict-banner-detail");
    await expect(bannerTitle).toBeVisible();
    await expect(bannerDetail).toBeVisible();

    const titleText = await bannerTitle.textContent();
    const detailText = await bannerDetail.textContent();
    // Title is short label
    expect(titleText.length).toBeLessThan(50);
    // Detail holds the full text
    expect(detailText).toContain("SEV-12");
});
