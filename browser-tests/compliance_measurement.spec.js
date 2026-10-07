// Compliance & Capability -- the Measurement card's Bay / Measurement Group
// workflow, real-browser coverage. History: Slice 2 (Measurement
// Selection + Normalization Foundation), the 2026-09-20 Bay/Measurement
// Group UAT correction and the 2026-09-23 discovery/bootstrap correction.
//
// **DEC-167 superseded the Assessment Quantity half of this file.** The
// independent Assessment Quantity selector and its Input / Input Type /
// Derived As / Base / Assessment Unit rows are gone: the active Reference
// Layer(s) define the unit, representation and phase evaluation, and the
// card reports Measurement READINESS against them. The readiness
// behaviour itself is covered by browser-tests/compliance_readiness.spec.js;
// this file keeps what is still the Measurement card's own concern:
//   - Bay / Measurement Group selection (auto-select, explicit choice,
//     cross-bay duplicate channel names are NOT ambiguous),
//   - per-group readiness and base (the base comes from the group's own
//     shared Voltage Group configuration),
//   - responsive containment,
//   - isolation from Playback / Analysis,
//   - upload-driven group discovery, review-required groups and the
//     Manage action.
//
// Compliance still does not register as an Engineering Context consumer
// (DEC-100/101/102) -- the Bay/Measurement Group picker reuses the
// EXISTING `app.domain.measurement_group` model via Compliance-only
// endpoints.
//
// Fixtures (backend/tests/fixtures/comtrade/), all committed:
//   - compliance_smoke_three_phase: bare-role-named VA/VB/VC, a balanced
//     100 V RMS/50 Hz instantaneous three-phase sinusoid -- uploaded more
//     than once (each upload is its own source_id) to build distinct bays
//     that share channel names.
//   - compliance_smoke_rms_phase_a: a single already-RMS VA channel.
//   - compliance_smoke_multibay / compliance_smoke_review_required: the
//     DEC-104 discovery scenarios.
//
// Measurement Groups are seeded directly via the existing Measurement
// Group REST API; Reference Profiles/Layers via their REST API.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

async function openCompliance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
}

async function uploadFixture(page, stem) {
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

async function currentWorkspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

// DEC-104 (2026-09-23): upload also runs automatic Measurement Group
// discovery, which would collide with this suite's own hand-built groups on
// the same bare-role channel names (VA/VB/VC) -- this wrapper uploads, then
// clears whatever discovery created. The dedicated discovery suite below
// calls uploadFixture() directly instead.
async function uploadFixtureForManualGroups(page, stem) {
  const sourceId = await uploadFixture(page, stem);
  const workspaceId = await currentWorkspaceIdOf(page);
  const groupsUrl = `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups`;
  const existing = await (await page.request.get(groupsUrl)).json();
  for (const group of existing) {
    await page.request.delete(`${groupsUrl}/${encodeURIComponent(group.id)}`);
  }
  return sourceId;
}

async function createVoltageGroup(page, { workspaceId, sourceId, channelNames, displayName }) {
  const response = await page.request.post(
    `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups`,
    {
      data: {
        kind: "voltage", display_name: displayName, status: "confirmed",
        channel_refs: channelNames.map((channel_name) => ({ kind: "source", source_id: sourceId, channel_name })),
      },
    }
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function setVoltageBase(page, { workspaceId, sourceId, groupId, nominalLlKv, reference }) {
  const response = await page.request.put(
    `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups/${encodeURIComponent(groupId)}/voltage-config`,
    { data: { nominal_voltage_ll_kv: nominalLlKv, reference_mode: "manual", reference_override: reference } }
  );
  expect(response.ok()).toBeTruthy();
}

// The Reference every scenario below is assessed against. Phase-ground /
// Each Phase by default: the bare-role fixtures carry VA/VB/VC.
async function addReference(page, { workspaceId, unit = "kV", representation = "phase_ground_rms", treatment = "each_phase", member = null, name = "Reference" } = {}) {
  const profile = await page.request.post(`${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reference-profiles`, { data: {
    name, category: "grid_requirement", assessment_definition: { representation, phase_treatment: treatment, member },
    unit, display_start_time: 0, display_end_time: 3, evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
    lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
    upper_boundary: null, metadata: {},
  } });
  expect(profile.ok()).toBeTruthy();
  const layer = await page.request.post(`${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/reference-layers`, {
    data: { profile_id: (await profile.json()).id, visible: true },
  });
  expect(layer.ok()).toBeTruthy();
}

async function selectGroup(page, label) {
  await page.locator("#wwComplianceGroupSelect").selectOption({ label });
}

const readinessStatus = (page) => page.locator("#wwComplianceReadinessStatus");

test.describe("Compliance Measurement -- Bay / Measurement Group", () => {
  test("empty workspace: no groups available, nothing else shown, Manage action offered", async ({ page }) => {
    await openCompliance(page);
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toBeVisible();
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No Voltage Measurement Group is available for this workspace.");
    await expect(page.locator("#wwComplianceGroupField")).toBeHidden();
    await expect(page.locator("#wwComplianceRequirements")).toBeHidden();
    await expect(page.locator("#wwComplianceReadiness")).toBeHidden();
    await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeVisible();
    await expect(page.locator("#wwComplianceManageGroupsBtn")).toHaveText("Manage Measurement Groups");
  });

  test.describe("exactly one Measurement Group", () => {
    test("is automatically selected and its readiness is shown straight away", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      const group = await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });

      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue(group.id);
      await expect(page.locator("#wwComplianceReadiness")).toBeVisible();
      // No Reference yet: nothing is required, so nothing is "ready".
      await expect(readinessStatus(page)).toHaveText("Add a Reference Layer to define what must be assessed.");
    });
  });

  test.describe("two Measurement Groups sharing the same channel names", () => {
    test("the engineer must choose one explicitly", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" });

      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue("");
      await expect(page.locator("#wwComplianceReadiness")).toBeHidden();
      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("Select a Bay / Measurement Group to continue.");
    });

    test("each Bay is judged on its OWN channels: a duplicate VA in another bay is not an ambiguity", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" }); // no VC
      await addReference(page, { workspaceId });

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await expect(page.locator(".ww-compliance-member-list li")).toHaveCount(3);
      await expect(page.locator("#wwComplianceReadiness")).not.toContainText("Multiple");
      await expect(page.locator("#wwComplianceReadiness")).not.toContainText("across the loaded recordings");
      await expect(readinessStatus(page)).not.toHaveText("✕ Measurement cannot satisfy this reference");

      await selectGroup(page, "Bay B");
      // Switching Bay re-checks everything: Bay B has no VC.
      await expect(readinessStatus(page)).toHaveText("✕ Measurement cannot satisfy this reference");
      await expect(page.locator('.ww-compliance-readiness-row[data-row="incompatible"]')).toContainText("VC is missing");
      // The selection itself is never silently changed.
      await expect(page.locator("#wwComplianceGroupSelect option:checked")).toHaveText("Bay B");
    });

    test("switching Bay updates the base from that group's own shared configuration", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      const groupA = await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await setVoltageBase(page, { workspaceId, sourceId: sourceA, groupId: groupA.id, nominalLlKv: 275.0, reference: "line_to_ground" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB", "VC"], displayName: "Bay B" }); // no base
      await addReference(page, { workspaceId, unit: "pu" });

      await openCompliance(page);
      const unitRow = page.locator('.ww-compliance-readiness-row[data-row="unit"]');
      await selectGroup(page, "Bay A");
      await expect(unitRow).toHaveAttribute("data-state", "ready");
      await expect(unitRow).toContainText("275 kV L-G");

      await selectGroup(page, "Bay B");
      await expect(unitRow).toHaveAttribute("data-state", "action_required");
      await expect(unitRow).toContainText("Base not configured");
    });
  });

  test.describe("single-phase recording (Va only)", () => {
    test("phase-ground Single VA on an already-RMS channel is ready (used directly); Each Phase names the missing phases", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_rms_phase_a");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA"], displayName: "Bus A" });
      await addReference(page, { workspaceId, treatment: "single", member: "A", name: "Single VA" });
      await openCompliance(page);
      await expect(readinessStatus(page)).toHaveText("✓ Ready for assessment");
      await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("Source RMS channels used directly");
      // Unit kV: no base needed, never reported as a failure.
      await expect(page.locator('.ww-compliance-readiness-row[data-row="unit"]')).toHaveAttribute("data-state", "not_required");

      await addReference(page, { workspaceId, name: "Each phase" });
      await page.reload();
      await page.locator("#mainNavComplianceBtn").click();
      await expect(page.locator('.ww-compliance-reference-readiness[data-status="incompatible"]')).toContainText("VB is missing");
    });
  });

  for (const viewport of [{ width: 1366, height: 900 }, { width: 1024, height: 800 }, { width: 800, height: 800 }]) {
    test(`the Bay select and readiness stay contained within the Measurement card at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB", "VC"], displayName: "Bay B" });
      await addReference(page, { workspaceId, unit: "pu", representation: "line_line_rms" });

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await expect(page.locator("#wwComplianceReadiness")).toBeVisible();
      await expect(readinessStatus(page)).not.toHaveText("");

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);

      const cardBox = await page.locator("#wwComplianceMeasurementCard").boundingBox();
      const groupSelectBox = await page.locator("#wwComplianceGroupSelect").boundingBox();
      const readinessBox = await page.locator("#wwComplianceReadiness").boundingBox();
      expect(groupSelectBox.x + groupSelectBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
      expect(readinessBox.x + readinessBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
      // Never overlapping the Reference Layers card (it is the other column or stacked above).
      const referenceBox = await page.locator("#wwComplianceReferenceLayersCard").boundingBox();
      const overlapsHorizontally = groupSelectBox.x < referenceBox.x + referenceBox.width && groupSelectBox.x + groupSelectBox.width > referenceBox.x;
      const overlapsVertically = groupSelectBox.y < referenceBox.y + referenceBox.height && groupSelectBox.y + groupSelectBox.height > referenceBox.y;
      expect(overlapsHorizontally && overlapsVertically).toBe(false);
    });
  }

  test("opening Compliance still does not touch Playback, Analysis Input Source, or any analyzer state", async ({ page }) => {
    await page.goto("/index.html");
    const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
    const workspaceId = await currentWorkspaceIdOf(page);
    await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });
    await addReference(page, { workspaceId });

    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    // This fixture upload gives Phasor a real bay to auto-bootstrap, so it
    // legitimately settles on "recording" -- wait for context loading to
    // actually finish rather than asserting a specific mode.
    await expect(async () => {
      expect(await page.evaluate(() => wwPhasorState.contexts.length)).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
    const before = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await expect(page.locator("#wwComplianceReadiness")).toBeVisible();
    await expect(readinessStatus(page)).not.toHaveText("");

    const after = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));
    expect(after).toBe(before);
  });

  // 2026-09-23 UAT correction: a workspace containing obvious multi-bay
  // Voltage channel sets (KPDN1/KPDN2/SLKS, each a full VR/VY/VB triplet)
  // must not show "No Measurement Group is available" merely because the
  // engineer never visited Manage Measurement Groups -- discovery now
  // runs automatically (DEC-103/DEC-104).
  test.describe("Bay/Measurement Group bootstrap and discovery (2026-09-23 UAT correction)", () => {
    test("multi-bay workspace: going directly to Compliance discovers groups without visiting Manage Measurement Groups first", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_multibay");
      const workspaceId = await currentWorkspaceIdOf(page);
      await addReference(page, { workspaceId });

      await openCompliance(page);

      await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
      const options = await page.locator("#wwComplianceGroupSelect option").allTextContents();
      expect(new Set(options.slice(1))).toEqual(new Set(["KPDN1 VOLTAGE", "KPDN2 VOLTAGE", "SLKS VOLTAGE", "SGT1 VOLTAGE"]));
      // Four candidates -- not auto-selected, an explicit choice is required.
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue("");
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeHidden();

      await selectGroup(page, "KPDN1 VOLTAGE");
      await expect(page.locator("#wwComplianceReadiness")).toBeVisible();
      // DEC-118: an R/Y/B bay spells its phases V<sub>R</sub>/V<sub>Y</sub>/V<sub>B</sub>.
      await expect(page.locator(".ww-compliance-member-list li")).toHaveCount(3);
      await expect(page.locator(".ww-compliance-member-list li").first()).toContainText("VR");
      await expect(page.locator(".ww-compliance-member-list li").nth(1)).toContainText("VY");
      await expect(page.locator(".ww-compliance-member-list li").nth(2)).toContainText("VB");

      await selectGroup(page, "SLKS VOLTAGE");
      await expect(page.locator(".ww-compliance-member-list li").first()).toContainText("VR");
      await expect(readinessStatus(page)).not.toHaveText("");
    });

    test("re-visiting Compliance never duplicates the discovered groups", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_multibay");
      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupSelect option")).toHaveCount(5); // placeholder + 4 bays

      await page.locator("#mainNavRecordingsBtn").click();
      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupSelect option")).toHaveCount(5);
    });

    test("review-required case: clear message and an actionable Review action, no usable groups shown", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_review_required");
      await openCompliance(page);

      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText(
        "Voltage Measurement Groups were found, but they require review before use."
      );
      await expect(page.locator("#wwComplianceGroupField")).toBeHidden();
      await expect(page.locator("#wwComplianceReadiness")).toBeHidden();
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeVisible();
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toHaveText("Review Measurement Groups");

      await page.locator("#wwComplianceManageGroupsBtn").click();
      await expect(page.locator("#measurementGroupsOverlay")).toBeVisible();
      await expect(page.locator("#measurementGroupsOverlay")).toContainText("MCRS");
    });

    test("Manage Measurement Groups action opens the existing modal and returns to Compliance intact", async ({ page }) => {
      await page.goto("/index.html");
      await openCompliance(page);
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeVisible();

      await page.locator("#wwComplianceManageGroupsBtn").click();
      await expect(page.locator("#measurementGroupsOverlay")).toBeVisible();
      // Compliance itself is still the active page underneath -- an overlay, never a navigation.
      await expect(page.locator("#pageCompliance")).toBeVisible();

      await page.locator("#measurementGroupsCloseBtn").click();
      await expect(page.locator("#measurementGroupsOverlay")).toBeHidden();
      await expect(page.locator("#pageCompliance")).toBeVisible();
      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No Voltage Measurement Group is available for this workspace.");
    });

    test("reviewing and confirming a review-required group moves it from review-required to usable on return", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixture(page, "compliance_smoke_review_required");
      const workspaceId = await currentWorkspaceIdOf(page);
      await openCompliance(page);
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toHaveText("Review Measurement Groups");

      // The engineer reviews the ambiguous MCRS cluster and confirms it via the
      // existing Measurement Groups management endpoint (the confirm drawer
      // itself is Measurement Groups' own suite's job).
      const groupsResponse = await page.request.get(
        `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/compliance/voltage/measurement-groups`
      );
      const mcrs = (await groupsResponse.json()).find((g) => g.display_name === "MCRS VOLTAGE");
      expect(mcrs.status).toBe("needs_review");
      const patchResponse = await page.request.patch(
        `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/${encodeURIComponent(sourceId)}/measurement-groups/${encodeURIComponent(mcrs.id)}`,
        { data: { status: "confirmed" } }
      );
      expect(patchResponse.ok()).toBeTruthy();

      // Return to Compliance (re-fetches the group list fresh).
      await page.locator("#mainNavRecordingsBtn").click();
      await openCompliance(page);
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeHidden();
      await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue(mcrs.id); // sole usable group -- auto-selected
    });
  });
});
