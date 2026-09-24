// Compliance & Capability -- Slice 3 (Reference Profiles, Reference
// Layers, and Static Curve Rendering), real-browser coverage. See
// browser-tests/compliance.spec.js for Slice 1's own workspace-shell
// coverage and browser-tests/compliance_measurement.spec.js for Slice
// 2's own Measurement coverage -- this file covers ONLY Reference
// Profiles/Reference Layers/the Comparison Chart's static reference-only
// rendering. Event Alignment, Results, and every evaluation/breach/
// tolerance concept remain out of scope and are not tested here (Slice
// 3's own explicit exclusion, task section 18/19).
//
// **Mid-conversation product requirement, the central thing this file
// proves**: Reference Profiles/Reference Layers/the Comparison Chart's
// static reference rendering all work in a workspace that has NEVER had
// a source uploaded. Several tests below deliberately never call
// uploadFixture() at all; one test uploads AFTER configuring references,
// specifically to prove upload does not disturb existing Reference
// Layer state.
//
// Every chart assertion inspects the real Plotly trace data
// (`#wwComplianceChartPlot`'s own `.data`/`.layout`), not just visible
// text or a screenshot (task section 20's own explicit instruction).

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");
const os = require("os");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

async function openCompliance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
}

async function currentWorkspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

async function uploadFixture(page, stem) {
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${stem}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${stem}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").last();
  await expect(row).toBeVisible();
  return row.getAttribute("data-source-id");
}

function referenceProfilesUrl(workspaceId) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reference-profiles`;
}
function referenceLayersUrl(workspaceId) {
  return `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reference-layers`;
}

// Seeds one custom profile directly via the real, already API-tested
// backend (mirrors compliance_measurement.spec.js's own "consumer is
// real, its own upstream data is seeded directly" convention) -- used by
// tests whose own focus is layer/chart BEHAVIOR, not profile creation
// itself (profile creation via the UI editor is its own dedicated test
// below).
async function createProfile(page, workspaceId, overrides = {}) {
  const body = {
    name: "Seeded Lower Envelope",
    category: "custom_reference",
    assessment_definition: { representation: "phase_ground_rms", phase_treatment: "single", member: "A" },
    unit: "pu",
    display_start_time: -0.5,
    display_end_time: 3.0,
    evaluation_start_time: 0.0,
    evaluation_end_time: 3.0,
    tolerance: 0.0,
    lower_boundary: { segments: [
      { start_time: -0.5, end_time: 3.0, start_value: 0.8, end_value: 0.8, segment_type: "constant" },
    ] },
    upper_boundary: null,
    metadata: {},
    ...overrides,
  };
  const response = await page.request.post(referenceProfilesUrl(workspaceId), { data: body });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function addLayer(page, workspaceId, profileId, visible = true) {
  const response = await page.request.post(referenceLayersUrl(workspaceId), { data: { profile_id: profileId, visible } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function chartPlotData(page) {
  return page.evaluate(() => {
    const el = document.getElementById("wwComplianceChartPlot");
    return el && el.data ? el.data.map((t) => ({
      layer_id: t.layer_id, profile_id: t.profile_id, boundary: t.boundary, category: t.category,
      name: t.name, x: t.x, y: t.y,
    })) : [];
  });
}

test.describe("Compliance Slice 3 -- Reference Profiles/Layers work without any uploaded recording", () => {
  test("fresh empty workspace: Add Reference is available with zero sources", async ({ page }) => {
    await openCompliance(page);
    const sourcesResponse = await page.request.get(`${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(await currentWorkspaceIdOf(page))}/sources`);
    expect(await sourcesResponse.json()).toEqual([]);

    await expect(page.locator("#wwComplianceAddReferenceBtn")).toBeEnabled();
    await expect(page.locator("#wwComplianceReferenceLayersEmptyState")).toHaveText("No reference layers added");
  });

  test("create a custom lower-only profile via the table-first editor, add it as a layer, curve appears in the Comparison Chart", async ({ page }) => {
    await openCompliance(page);

    await page.locator("#wwComplianceAddReferenceBtn").click();
    await expect(page.locator("#wwRefAddOverlay")).toBeVisible();
    await page.locator("#wwRefAddNewProfileBtn").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();

    await page.locator("#wwRefEditorName").fill("UAT Lower Envelope");
    await page.locator("#wwRefEditorCategory").selectOption("custom_reference");
    await page.locator("#wwRefEditorUnit").selectOption("pu");
    await page.locator("#wwRefEditorDisplayStart").fill("-0.5");
    await page.locator("#wwRefEditorDisplayEnd").fill("3.0");

    // One default lower-boundary row already exists -- edit it directly
    // rather than adding a second one (table-first numeric entry, task
    // section 13 -- no freehand dragging anywhere on this page).
    const lowerRow = page.locator("#wwRefEditorLowerBody tr").first();
    await lowerRow.locator(".ww-ref-seg-start-time").fill("-0.5");
    await lowerRow.locator(".ww-ref-seg-end-time").fill("3.0");
    await lowerRow.locator(".ww-ref-seg-start-value").fill("0.85");
    await lowerRow.locator(".ww-ref-seg-end-value").fill("0.85");
    await lowerRow.locator(".ww-ref-seg-type").selectOption("constant");
    await expect(page.locator("#wwRefEditorUpperEnabled")).not.toBeChecked();

    await page.locator("#wwRefEditorSaveBtn").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeHidden();

    // Back in the Add Reference dialog -- the new profile is listed and addable.
    await expect(page.locator("#wwRefAddList")).toContainText("UAT Lower Envelope");
    await page.locator("#wwRefAddList button:has-text('Add')").first().click();
    await expect(page.locator("#wwRefAddList button:has-text('Added')").first()).toBeVisible();
    await page.locator("#wwRefAddCloseFooterBtn").click();

    await expect(page.locator("#wwRefLayerList")).toContainText("UAT Lower Envelope");
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();

    const traces = await chartPlotData(page);
    expect(traces.length).toBe(1);
    expect(traces[0].boundary).toBe("lower");
    expect(traces[0].x).toEqual([-0.5, 3.0]);
    expect(traces[0].y).toEqual([0.85, 0.85]);
  });
});

test.describe("Compliance Slice 3 -- multiple layers, toggling, and removal without deleting the profile", () => {
  test("add a second profile, both render, toggle one off/on, remove a layer without deleting its profile, then re-add it", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);

    const profileA = await createProfile(page, workspaceId, { name: "Profile A" });
    const profileB = await createProfile(page, workspaceId, {
      name: "Profile B",
      lower_boundary: null,
      upper_boundary: { segments: [{ start_time: -0.5, end_time: 3.0, start_value: 1.15, end_value: 1.15, segment_type: "constant" }] },
    });
    await addLayer(page, workspaceId, profileA.id);
    const layerB = await addLayer(page, workspaceId, profileB.id);

    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    await expect(page.locator("#wwRefLayerList")).toContainText("Profile A");
    await expect(page.locator("#wwRefLayerList")).toContainText("Profile B");
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    let traces = await chartPlotData(page);
    expect(traces.length).toBe(2);
    expect(new Set(traces.map((t) => t.boundary))).toEqual(new Set(["lower", "upper"]));

    // Toggle Profile B off -- its trace disappears from the chart, but
    // the layer row itself remains (dimmed), never deleted. The chart
    // refetch is a separate async request from the layer-list DOM
    // update, so poll rather than reading it exactly once immediately
    // after the DOM attribute settles (this raced under full-suite load
    // -- a real flake in this test, not in the product).
    const layerBCheckbox = page.locator(`#wwRefLayerVis-${layerB.id}`);
    await layerBCheckbox.uncheck();
    await expect(page.locator(`.ww-ref-layer-row[data-layer-id="${layerB.id}"]`)).toHaveAttribute("data-visible", "false");
    await expect.poll(async () => (await chartPlotData(page)).length).toBe(1);
    traces = await chartPlotData(page);
    expect(traces[0].profile_id).toBe(profileA.id);

    // Toggle it back on.
    await layerBCheckbox.check();
    await expect(page.locator(`.ww-ref-layer-row[data-layer-id="${layerB.id}"]`)).toHaveAttribute("data-visible", "true");
    await expect.poll(async () => (await chartPlotData(page)).length).toBe(2);

    // Remove the layer entirely -- the underlying profile must survive.
    await page.locator(`#wwRefLayerRemove-${layerB.id}`).click();
    await expect(page.locator("#wwRefLayerList")).not.toContainText("Profile B");
    await expect.poll(async () => (await chartPlotData(page)).length).toBe(1);

    const profileStillExists = await page.request.get(`${referenceProfilesUrl(workspaceId)}/${encodeURIComponent(profileB.id)}`);
    expect(profileStillExists.ok()).toBeTruthy();

    // Re-add it via the Add Reference dialog.
    await page.locator("#wwComplianceAddReferenceBtn").click();
    await page.locator("#wwRefAddList .ww-ref-picker-item", { hasText: "Profile B" }).locator("button:has-text('Add')").click();
    await page.locator("#wwRefAddCloseFooterBtn").click();
    await expect(page.locator("#wwRefLayerList")).toContainText("Profile B");
    await expect.poll(async () => (await chartPlotData(page)).length).toBe(2);
  });
});

test.describe("Compliance Slice 3 -- reference-only Comparison Chart rendering semantics", () => {
  test("negative time, a discontinuity connector, and a genuine gap render exactly as the domain model specifies", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);

    const profile = await createProfile(page, workspaceId, {
      name: "Discontinuity And Gap Profile",
      display_start_time: -1.0,
      display_end_time: 3.0,
      lower_boundary: { segments: [
        { start_time: -1.0, end_time: 0.15, start_value: 0.9, end_value: 0.9, segment_type: "constant" },
        { start_time: 0.15, end_time: 1.0, start_value: 0.2, end_value: 0.9, segment_type: "linear" },
        { start_time: 2.0, end_time: 3.0, start_value: 1.0, end_value: 1.0, segment_type: "constant" },
      ] },
    });
    await addLayer(page, workspaceId, profile.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const traces = await chartPlotData(page);
    expect(traces.length).toBe(1);
    // Right-continuity discontinuity connector at t=0.15: the previous
    // segment's own end_value (0.9) then the NEW segment's own
    // start_value (0.2) at the exact same time instant.
    expect(traces[0].x).toEqual([-1.0, 0.15, 0.15, 1.0, 1.0, 2.0, 3.0]);
    expect(traces[0].y[1]).toBe(0.9);
    expect(traces[0].y[2]).toBe(0.2);
    // Genuine gap between t=1.0 and t=2.0 -- a null break, never a
    // straight line silently bridging the two segments.
    expect(traces[0].y[4]).toBeNull();
  });

  test("an upper-only profile produces exactly one upper-boundary trace; an envelope profile produces both", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);

    const upperOnly = await createProfile(page, workspaceId, {
      name: "Upper Only Profile", lower_boundary: null,
      upper_boundary: { segments: [{ start_time: -0.5, end_time: 3.0, start_value: 1.1, end_value: 1.1, segment_type: "constant" }] },
    });
    await addLayer(page, workspaceId, upperOnly.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    let traces = await chartPlotData(page);
    expect(traces.map((t) => t.boundary)).toEqual(["upper"]);

    const envelope = await createProfile(page, workspaceId, {
      name: "Envelope Profile",
      upper_boundary: { segments: [{ start_time: -0.5, end_time: 3.0, start_value: 1.1, end_value: 1.1, segment_type: "constant" }] },
    });
    await addLayer(page, workspaceId, envelope.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    traces = await chartPlotData(page);
    const envelopeTraces = traces.filter((t) => t.profile_id === envelope.id);
    expect(new Set(envelopeTraces.map((t) => t.boundary))).toEqual(new Set(["lower", "upper"]));
  });
});

test.describe("Compliance Slice 3 -- no Measurement selected is NEVER incompatible", () => {
  test("a reference layer's compatibility badge reads 'Not yet applicable' with no Measurement selected, never 'Incompatible'", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const profile = await createProfile(page, workspaceId, { name: "Compatibility Probe Profile" });
    await addLayer(page, workspaceId, profile.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();

    const row = page.locator(".ww-ref-layer-row", { hasText: "Compatibility Probe Profile" });
    await expect(row.locator(".ww-ref-badge--compat-not_yet_applicable")).toHaveText("Not yet applicable");
    await expect(row.locator(".ww-ref-badge--compat-incompatible")).toHaveCount(0);
    await expect(row.locator(".ww-ref-badge--compat-compatible")).toHaveCount(0);
  });

  test("DEC-110: compatibility stays 'Not yet applicable' even via the API's own quantity_id query param (no measurement resolver exists yet)", async ({ page, request }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const profile = await createProfile(page, workspaceId, {
      name: "Resolver Probe Profile",
      assessment_definition: { representation: "phase_ground_rms", phase_treatment: "single", member: "A" },
    });
    await addLayer(page, workspaceId, profile.id);
    const response = await request.get(`${referenceLayersUrl(workspaceId)}?quantity_id=phase_a_lg_rms`);
    const layers = await response.json();
    expect(layers[0].compatibility.status).toBe("not_yet_applicable");
  });
});

test.describe("Compliance Slice 3 -- uploading a recording never disturbs existing Reference Layer state", () => {
  test("configure Reference Layers first, upload a recording afterward -- layers remain present, Measurement becomes available", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const profile = await createProfile(page, workspaceId, { name: "Pre-Upload Profile" });
    await addLayer(page, workspaceId, profile.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwRefLayerList")).toContainText("Pre-Upload Profile");
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toBeVisible();

    await uploadFixture(page, "compliance_smoke_three_phase");
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    // Reference Layers survived the upload, unchanged.
    await expect(page.locator("#wwRefLayerList")).toContainText("Pre-Upload Profile");
    const traces = await chartPlotData(page);
    expect(traces.length).toBe(1);

    // Measurement became available (a usable Bay/Measurement Group now exists).
    await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
  });
});

test.describe("Compliance Slice 3 -- profile management (custom profiles)", () => {
  test("Manage Profiles: duplicate, export, edit, and remove a custom profile", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    await createProfile(page, workspaceId, { name: "Manageable Profile" });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();

    await page.locator("#wwRefManageProfilesBtn").click();
    await expect(page.locator("#wwRefManageOverlay")).toBeVisible();
    await expect(page.locator("#wwRefManageList")).toContainText("Manageable Profile");

    const rows = page.locator("#wwRefManageList .ww-ref-picker-item");
    const copyRow = () => rows.filter({ hasText: "(Copy)" });
    const originalRow = () => rows.filter({ hasNotText: "(Copy)" });

    // Duplicate (only one row exists at this point -- unambiguous).
    await rows.first().locator("button:has-text('Duplicate')").click();
    await expect(page.locator("#wwRefManageList")).toContainText("Manageable Profile (Copy)");
    await expect(copyRow()).toHaveCount(1);

    // Export triggers a real download.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      copyRow().locator("button:has-text('Export')").click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.json$/);

    // Edit the original (the one WITHOUT "(Copy)" in its name).
    await originalRow().locator("button:has-text('Edit')").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();
    await page.locator("#wwRefEditorName").fill("Renamed Profile");
    await page.locator("#wwRefEditorSaveBtn").click();
    await expect(page.locator("#wwRefManageList")).toContainText("Renamed Profile");

    // Remove the duplicate.
    page.once("dialog", (dialog) => dialog.accept());
    await copyRow().locator("button:has-text('Remove')").click();
    await expect(page.locator("#wwRefManageList")).not.toContainText("(Copy)");
  });

  test("import/export round trip: export a profile, import it back as an independent copy", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const original = await createProfile(page, workspaceId, { name: "Round Trip Profile" });
    const exportResponse = await page.request.get(`${referenceProfilesUrl(workspaceId)}/${encodeURIComponent(original.id)}/export`);
    const envelope = await exportResponse.json();
    expect(envelope.schema_version).toBe(2);

    const importResponse = await page.request.post(`${referenceProfilesUrl(workspaceId)}/import`, { data: envelope });
    expect(importResponse.ok()).toBeTruthy();
    const imported = await importResponse.json();
    expect(imported.id).not.toBe(original.id);
    expect(imported.name).toBe("Round Trip Profile");
  });
});

test.describe("Compliance Slice 4 (DEC-110) -- Assessment Definition", () => {
  test("create a profile via the editor with an explicit Voltage representation/phase treatment, verify it round-trips through the API", async ({ page }) => {
    await openCompliance(page);

    await page.locator("#wwComplianceAddReferenceBtn").click();
    await page.locator("#wwRefAddNewProfileBtn").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();

    await page.locator("#wwRefEditorName").fill("Minimum Line-Line Requirement");
    await page.locator("#wwRefEditorRepresentation").selectOption("line_line_rms");
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("minimum");
    // Member field must be hidden for an aggregate treatment (minimum).
    await expect(page.locator("#wwRefEditorMemberField")).toBeHidden();
    await page.locator("#wwRefEditorMeasurementLocation").selectOption("connection_point");

    const lowerRow = page.locator("#wwRefEditorLowerBody tr").first();
    await lowerRow.locator(".ww-ref-seg-start-time").fill("-0.5");
    await lowerRow.locator(".ww-ref-seg-end-time").fill("3.0");
    await lowerRow.locator(".ww-ref-seg-start-value").fill("0.85");
    await lowerRow.locator(".ww-ref-seg-end-value").fill("0.85");

    await page.locator("#wwRefEditorSaveBtn").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeHidden();

    await expect(page.locator("#wwRefAddList")).toContainText("Assessment: Minimum Line-Line RMS at Connection Point");
    await page.locator("#wwRefAddList .ww-ref-picker-item", { hasText: "Minimum Line-Line Requirement" }).locator("button:has-text('Add')").click();
    await page.locator("#wwRefAddCloseFooterBtn").click();

    await expect(page.locator(".ww-ref-layer-summary")).toContainText("Assessment: Minimum Line-Line RMS at Connection Point");
  });

  test("create a profile with an explicit single line-line member (VAB), member field shows and is required", async ({ page }) => {
    await openCompliance(page);
    await page.locator("#wwComplianceAddReferenceBtn").click();
    await page.locator("#wwRefAddNewProfileBtn").click();

    await page.locator("#wwRefEditorName").fill("VAB Single Member Requirement");
    await page.locator("#wwRefEditorRepresentation").selectOption("line_line_rms");
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("single");
    await expect(page.locator("#wwRefEditorMemberField")).toBeVisible();
    await page.locator("#wwRefEditorMember").selectOption("AB");

    const lowerRow = page.locator("#wwRefEditorLowerBody tr").first();
    await lowerRow.locator(".ww-ref-seg-start-value").fill("0.85");
    await lowerRow.locator(".ww-ref-seg-end-value").fill("0.85");
    await page.locator("#wwRefEditorSaveBtn").click();
    await expect(page.locator("#wwRefEditorOverlay")).toBeHidden();

    await expect(page.locator("#wwRefAddList")).toContainText("Line-Line RMS (AB)");
  });

  test("an invalid combination (line-line + each-phase) is rejected inline with an actionable error, never saved", async ({ page }) => {
    await openCompliance(page);
    await page.locator("#wwComplianceAddReferenceBtn").click();
    await page.locator("#wwRefAddNewProfileBtn").click();

    await page.locator("#wwRefEditorName").fill("Invalid Combination Profile");
    await page.locator("#wwRefEditorRepresentation").selectOption("line_line_rms");
    await page.locator("#wwRefEditorPhaseTreatment").selectOption("each_phase");
    const lowerRow = page.locator("#wwRefEditorLowerBody tr").first();
    await lowerRow.locator(".ww-ref-seg-start-value").fill("0.85");
    await lowerRow.locator(".ww-ref-seg-end-value").fill("0.85");
    await page.locator("#wwRefEditorSaveBtn").click();

    await expect(page.locator("#wwRefEditorOverlay")).toBeVisible();
    await expect(page.locator("#wwRefEditorError")).toBeVisible();
    await expect(page.locator("#wwRefEditorError")).toContainText("each_phase");
  });

  test("a profile with a fully unspecified assessment definition still renders in the reference-only Comparison Chart", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const profile = await createProfile(page, workspaceId, {
      name: "Unspecified Convention Profile",
      assessment_definition: {},
    });
    await addLayer(page, workspaceId, profile.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const traces = await chartPlotData(page);
    expect(traces.length).toBe(1);
    await expect(page.locator(".ww-ref-layer-summary")).toContainText("Assessment convention not specified");
  });

  test("importing a legacy (pre-DEC-110) v1 profile migrates evaluation_quantity into an Assessment Definition, editable afterward", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const v1Envelope = {
      schema_version: 1,
      profile: {
        name: "Legacy Positive Sequence Profile", category: "custom_reference", evaluation_quantity: "positive_sequence_rms",
        unit: "pu", display_start_time: -0.5, display_end_time: 3.0, evaluation_start_time: 0.0, evaluation_end_time: 3.0,
        tolerance: 0.0,
        lower_boundary: { segments: [{ start_time: -0.5, end_time: 3.0, start_value: 0.8, end_value: 0.8, segment_type: "constant" }] },
        upper_boundary: null, metadata: {},
      },
    };
    const importResponse = await page.request.post(`${referenceProfilesUrl(workspaceId)}/import`, { data: v1Envelope });
    expect(importResponse.ok()).toBeTruthy();
    const imported = await importResponse.json();
    expect(imported.assessment_definition.representation).toBe("positive_sequence_rms");
    expect(imported.assessment_definition.legacy_quantity_hint).toBe("positive_sequence_rms");

    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await page.locator("#wwRefManageProfilesBtn").click();
    await page.locator("#wwRefManageList .ww-ref-picker-item", { hasText: "Legacy Positive Sequence Profile" }).locator("button:has-text('Edit')").click();
    await expect(page.locator("#wwRefEditorRepresentation")).toHaveValue("positive_sequence_rms");
    await expect(page.locator("#wwRefEditorLegacyHintNote")).toBeVisible();
    await expect(page.locator("#wwRefEditorLegacyHintNote")).toContainText("positive_sequence_rms");
  });
});

test.describe("Compliance Slice 4/5 (DEC-111) -- portable JSON lifecycle, jurisdiction-neutral local-file workflow", () => {
  test("real download then real upload round trip: Export Reference downloads a file, Import Reference re-uploads that exact file from disk", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    await createProfile(page, workspaceId, {
      name: "Local File Round Trip Profile",
      metadata: { jurisdiction: "Malaysia", document_revision: "2025" },
    });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await page.locator("#wwRefManageProfilesBtn").click();
    await expect(page.locator("#wwRefManageOverlay")).toBeVisible();

    // Real download -- the browser actually writes a file to disk.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#wwRefManageList .ww-ref-picker-item", { hasText: "Local File Round Trip Profile" }).locator("button:has-text('Export')").click(),
    ]);
    const downloadedPath = path.join(os.tmpdir(), `ww-ref-download-${Date.now()}.json`);
    await download.saveAs(downloadedPath);
    const downloadedJson = JSON.parse(fs.readFileSync(downloadedPath, "utf8"));
    expect(downloadedJson.schema_version).toBe(2);
    expect(downloadedJson.profile.metadata.jurisdiction).toBe("Malaysia");
    expect(downloadedJson.profile).not.toHaveProperty("id");

    // Real upload -- the browser's own <input type="file"> receives the
    // exact file just downloaded, exercising app.services.reference_
    // profile_service.import_profile() through the real UI file picker,
    // never page.request.post() directly.
    await page.locator("#wwRefManageImportInput").setInputFiles(downloadedPath);
    await expect(page.locator("#wwRefManageList")).toContainText("Local File Round Trip Profile");
    // The original custom profile + the freshly re-imported copy --
    // FileReader.onload/the import request/the re-render are all async,
    // so poll rather than reading .count() exactly once.
    await expect(page.locator("#wwRefManageList .ww-ref-picker-item", { hasText: "Local File Round Trip Profile" })).toHaveCount(2);

    fs.unlinkSync(downloadedPath);
  });

  test("importing a malformed local JSON file is rejected inline, never silently coerced", async ({ page }) => {
    await openCompliance(page);
    await page.locator("#wwRefManageProfilesBtn").click();
    const malformedPath = path.join(os.tmpdir(), `ww-ref-malformed-${Date.now()}.json`);
    fs.writeFileSync(malformedPath, "{ not valid json ");
    await page.locator("#wwRefManageImportInput").setInputFiles(malformedPath);
    await expect(page.locator("#wwRefManageError")).toBeVisible();
    await expect(page.locator("#wwRefManageError")).toContainText("not valid JSON");
    fs.unlinkSync(malformedPath);
  });

  test("importing a real local v1-schema JSON file (as if kept from before DEC-110) still migrates correctly through the real file picker", async ({ page }) => {
    await openCompliance(page);
    const v1Envelope = {
      schema_version: 1,
      profile: {
        name: "Locally Kept Legacy Profile", category: "custom_reference", evaluation_quantity: "phase_ab_ll_rms",
        unit: "pu", display_start_time: -0.5, display_end_time: 3.0, evaluation_start_time: 0.0, evaluation_end_time: 3.0,
        tolerance: 0.0,
        lower_boundary: { segments: [{ start_time: -0.5, end_time: 3.0, start_value: 0.8, end_value: 0.8, segment_type: "constant" }] },
        upper_boundary: null, metadata: {},
      },
    };
    const v1Path = path.join(os.tmpdir(), `ww-ref-v1-${Date.now()}.json`);
    fs.writeFileSync(v1Path, JSON.stringify(v1Envelope));
    await page.locator("#wwRefManageProfilesBtn").click();
    await page.locator("#wwRefManageImportInput").setInputFiles(v1Path);
    await expect(page.locator("#wwRefManageList")).toContainText("Locally Kept Legacy Profile");
    await page.locator("#wwRefManageList .ww-ref-picker-item", { hasText: "Locally Kept Legacy Profile" }).locator("button:has-text('Edit')").click();
    await expect(page.locator("#wwRefEditorRepresentation")).toHaveValue("line_line_rms");
    await expect(page.locator("#wwRefEditorMember")).toHaveValue("AB");
    fs.unlinkSync(v1Path);
  });

  test("two document revisions of the same jurisdiction coexist as independent Reference Layers", async ({ page }) => {
    await openCompliance(page);
    const workspaceId = await currentWorkspaceIdOf(page);
    const revision2025 = await createProfile(page, workspaceId, {
      name: "Coexisting Grid Code", metadata: { jurisdiction: "Malaysia", document_revision: "2025" },
    });
    const revision2027 = await createProfile(page, workspaceId, {
      name: "Coexisting Grid Code", metadata: { jurisdiction: "Malaysia", document_revision: "2027" },
    });
    await addLayer(page, workspaceId, revision2025.id);
    await addLayer(page, workspaceId, revision2027.id);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const traces = await chartPlotData(page);
    const profileIds = new Set(traces.map((t) => t.profile_id));
    expect(profileIds.has(revision2025.id)).toBe(true);
    expect(profileIds.has(revision2027.id)).toBe(true);
  });

  test("empty Reference Library state reads as an intentional product state, never a loading failure", async ({ page }) => {
    await openCompliance(page);
    await page.locator("#wwRefManageProfilesBtn").click();
    await expect(page.locator("#wwRefManageList")).toContainText("No reference profiles loaded");
  });
});
