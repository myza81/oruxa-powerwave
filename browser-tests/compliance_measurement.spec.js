// Compliance & Capability -- Slice 2 (Measurement Selection +
// Normalization Foundation) + the 2026-09-20 Bay/Measurement Group UAT
// correction, real-browser coverage. See browser-tests/compliance.spec.js
// for Slice 1's own workspace-shell coverage (menu order, page
// lifecycle, responsive layout) -- this file covers ONLY the Measurement
// section: Bay/Measurement Group selection, Assessment Quantity
// selection WITHIN that group, group/quantity switching, availability/
// guardrail messages, and the Input/Input Type/Derived As/Base/
// Assessment Unit summary. Reference Layers/Event Alignment/Comparison
// Chart/Results logic remains out of scope and is not tested here.
//
// **UAT correction (2026-09-20): role resolution is now scoped to an
// explicitly SELECTED Measurement Group.** A bare Assessment Quantity
// selector was ambiguous once more than one bay/Measurement Group
// exists in the workspace (several valid Va/Vb/Vab etc. may exist
// across different bays) -- the corrected workflow is Bay/Measurement
// Group first, then Assessment Quantity within it. Compliance still
// does not register as an Engineering Context consumer (DEC-100/
// DEC-101/DEC-102) -- the Bay/Measurement Group picker reuses the
// EXISTING `app.domain.measurement_group` model via new, Compliance-
// only endpoints, never Engineering Context.
//
// Fixtures (backend/tests/fixtures/comtrade/), both committed, hand-
// verified end-to-end against the real backend before use:
//   - compliance_smoke_three_phase(.cfg/.dat): bare-role-named VA/VB/VC,
//     a known balanced 100 V RMS/50 Hz three-phase sinusoid -- uploaded
//     more than once in this file (each upload is its own independent
//     source_id) to build genuinely distinct bays that happen to share
//     channel names, exercising the cross-bay-duplication-is-not-
//     ambiguous correction directly.
//   - compliance_smoke_rms_phase_a(.cfg/.dat): a single VA channel with
//     a smooth, always-positive, slowly-varying envelope -- the RMS
//     scenario (verified directly to classify LIKELY_MAGNITUDE_OR_RMS
//     via the real algorithmic detector before being committed).
//
// Measurement Groups are seeded directly via the existing, already-
// tested Measurement Group REST API (no Measurement Group configuration
// UI is exercised by this Compliance-focused suite) -- the same
// "consumer is real, its own upstream data is seeded directly" pattern
// phasor_analysis.spec.js's own header comment already establishes for
// Engineering Context.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

const QUANTITY_LABELS = [
  "Phase A Voltage", "Phase B Voltage", "Phase C Voltage",
  "Line-Line AB Voltage", "Line-Line BC Voltage", "Line-Line CA Voltage",
  "Minimum Three-Phase Voltage", "Maximum Three-Phase Voltage",
  "Positive Sequence Voltage",
];

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

// DEC-104 (2026-09-23): upload now also runs automatic Measurement Group
// discovery, which would otherwise collide with this suite's own hand-
// built groups on the same bare-role channel names (VA/VB/VC) -- this
// wrapper uploads, then clears whatever discovery created, so every test
// that goes on to build its OWN groups via createVoltageGroup() keeps
// doing so against a clean slate. The dedicated "Bay/Measurement Group
// bootstrap and discovery" suite further below calls uploadFixture()
// directly instead (never this wrapper) -- it specifically exercises the
// upload-driven auto-discovered groups themselves, so clearing them
// would defeat the point of those tests.
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

async function selectGroup(page, label) {
  await page.locator("#wwComplianceGroupSelect").selectOption({ label });
}

async function selectQuantity(page, label) {
  await page.locator("#wwComplianceMeasurementSelect").selectOption({ label });
}

test.describe("Compliance & Capability -- Slice 2 Measurement", () => {
  test("Assessment Quantity dropdown lists all nine quantities in order (independent of group state)", async ({ page }) => {
    await openCompliance(page);
    const options = page.locator("#wwComplianceMeasurementSelect option");
    await expect(options).toHaveText(["Select a quantity…", ...QUANTITY_LABELS]);
  });

  test("empty workspace: no groups available, both selects stay hidden, Manage action offered", async ({ page }) => {
    await openCompliance(page);
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toBeVisible();
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No Voltage Measurement Group is available for this workspace.");
    await expect(page.locator("#wwComplianceGroupField")).toBeHidden();
    await expect(page.locator("#wwComplianceMeasurementField")).toBeHidden();
    await expect(page.locator("#wwComplianceMeasurementSummary")).toBeHidden();
    await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeVisible();
    await expect(page.locator("#wwComplianceManageGroupsBtn")).toHaveText("Manage Measurement Groups");
  });

  test.describe("exactly one Measurement Group", () => {
    test("is automatically selected; quantity resolves normally", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      const group = await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });

      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue(group.id);
      await expect(page.locator("#wwComplianceMeasurementField")).toBeVisible();
      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No assessment quantity selected");

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA");
    });

    test("clearing the quantity selection returns to the neutral empty state", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA"], displayName: "Bus A" });

      await openCompliance(page);
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementSummary")).toBeVisible();
      await page.locator("#wwComplianceMeasurementSelect").selectOption({ value: "" });
      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No assessment quantity selected");
      await expect(page.locator("#wwComplianceMeasurementSummary")).toBeHidden();
    });
  });

  test.describe("two Measurement Groups sharing the same channel name (Va)", () => {
    test("before selecting a group, the engineer must choose one explicitly", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" });

      await openCompliance(page);
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue("");
      await expect(page.locator("#wwComplianceMeasurementField")).toBeHidden();
      await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("Select a Bay / Measurement Group to continue.");
    });

    test("selecting Bay A resolves only Bay A's own Va -- no cross-bay ambiguity", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" });

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA");
      // The old "Multiple channels match... across the loaded recordings"
      // wording must never appear -- a duplicate Va in a DIFFERENT bay is
      // not a naming conflict once a group is selected.
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).not.toContainText("across the loaded recordings");
    });

    test("switching to Bay B resolves Bay B's own Va and updates the whole summary", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      const groupA = await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await setVoltageBase(page, { workspaceId, sourceId: sourceA, groupId: groupA.id, nominalLlKv: 275.0, reference: "line_to_ground" });
      const groupB = await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" });
      await setVoltageBase(page, { workspaceId, sourceId: sourceB, groupId: groupB.id, nominalLlKv: 132.0, reference: "line_to_ground" });

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("275 kV L-G");

      await selectGroup(page, "Bay B");
      // Base, Input, Input Type, Derived As, and Status must all update
      // to reflect the newly selected group (task section 16 "Group
      // switch" scenario).
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("132 kV L-G");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA");
      await expect(page.locator("#wwComplianceMeasurementInputType")).toHaveText("Instantaneous");
      await expect(page.locator("#wwComplianceMeasurementDerivedAs")).toHaveText("Fundamental RMS");
    });

    test("group with a missing phase reports Missing Inputs -- kept selection, no silent quantity switch", async ({ page }) => {
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB"], displayName: "Bay B" }); // no VC

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText(/^Compatible$/);

      await selectGroup(page, "Bay B");
      // The quantity selection itself must be preserved -- the select's
      // own value never silently changes to something else.
      await expect(page.locator("#wwComplianceMeasurementSelect")).toHaveValue("positive_sequence_rms");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toContainText("Missing: VC");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveClass(/ww-phasor-status--needs-configuration/);
    });
  });

  test.describe("single-phase recording (Va only)", () => {
    test("Phase A Voltage is available; Positive Sequence Voltage names the missing phases", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_rms_phase_a");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA"], displayName: "Bus A" });
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA");

      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toContainText("Missing: VB, VC");
    });

    test("RMS input reports Input Type RMS and Derived As Direct RMS", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_rms_phase_a");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA"], displayName: "Bus A" });
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInputType")).toHaveText("RMS (Source-defined / unspecified)");
      await expect(page.locator("#wwComplianceMeasurementDerivedAs")).toHaveText("Direct RMS (Source-defined / unspecified)");
      // No base configured on this group -- a normal, non-error state
      // (task section 16), never "Invalid Base".
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("Not configured");
      await expect(page.locator("#wwComplianceMeasurementUnit")).toHaveText("Engineering Units");
    });
  });

  test.describe("complete three-phase recording (Va/Vb/Vc), single bay", () => {
    test("Min/Max/Positive Sequence are all available with Instantaneous/Fundamental RMS", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });
      await openCompliance(page);

      for (const label of ["Minimum Three-Phase Voltage", "Maximum Three-Phase Voltage", "Positive Sequence Voltage"]) {
        await selectQuantity(page, label);
        await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
        await expect(page.locator("#wwComplianceMeasurementInputType")).toHaveText("Instantaneous");
        await expect(page.locator("#wwComplianceMeasurementDerivedAs")).toHaveText("Fundamental RMS");
      }
    });

    test("Positive Sequence Voltage input lists Va, Vb, Vc", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });
      await openCompliance(page);
      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA, VB — VB, VC — VC");
    });

    test("quantity switching updates the summary each time, never showing a stale result", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });
      await openCompliance(page);

      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA");

      await selectQuantity(page, "Line-Line AB Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VA — VA, VB — VB");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");

      await selectQuantity(page, "Phase C Voltage");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VC — VC");
    });

    test("Base metadata: a confirmed Measurement Group with a nominal base shows kV/L-G and pu", async ({ page }) => {
      await page.goto("/index.html");
      const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      const group = await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });
      await setVoltageBase(page, { workspaceId, sourceId, groupId: group.id, nominalLlKv: 275.0, reference: "line_to_ground" });

      await openCompliance(page);
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementBase")).toHaveText("275 kV L-G");
      await expect(page.locator("#wwComplianceMeasurementUnit")).toHaveText("pu");
    });
  });

  for (const viewport of [{ width: 1366, height: 900 }, { width: 1024, height: 800 }, { width: 800, height: 800 }]) {
    test(`both selects stay contained within the Measurement card at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/index.html");
      const sourceA = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const sourceB = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
      const workspaceId = await currentWorkspaceIdOf(page);
      // Two groups (never auto-selected) so #wwComplianceGroupSelect is
      // genuinely visible and populated at every tested width, not just
      // the quantity select.
      await createVoltageGroup(page, { workspaceId, sourceId: sourceA, channelNames: ["VA", "VB", "VC"], displayName: "Bay A" });
      await createVoltageGroup(page, { workspaceId, sourceId: sourceB, channelNames: ["VA", "VB", "VC"], displayName: "Bay B" });

      await openCompliance(page);
      await selectGroup(page, "Bay A");
      await selectQuantity(page, "Positive Sequence Voltage");
      await expect(page.locator("#wwComplianceMeasurementSummary")).toBeVisible();

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);

      const cardBox = await page.locator("#wwComplianceMeasurementCard").boundingBox();
      const groupSelectBox = await page.locator("#wwComplianceGroupSelect").boundingBox();
      const quantitySelectBox = await page.locator("#wwComplianceMeasurementSelect").boundingBox();
      expect(groupSelectBox.x + groupSelectBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
      expect(quantitySelectBox.x + quantitySelectBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);

      const referenceLayersBox = await page.locator("#wwComplianceReferenceLayersCard").boundingBox();
      expect(groupSelectBox.x + groupSelectBox.width).toBeLessThanOrEqual(referenceLayersBox.x + 1);
      expect(quantitySelectBox.x + quantitySelectBox.width).toBeLessThanOrEqual(referenceLayersBox.x + 1);
    });
  }

  test("opening Compliance still does not touch Playback, Analysis Input Source, or any analyzer state", async ({ page }) => {
    await page.goto("/index.html");
    const sourceId = await uploadFixtureForManualGroups(page, "compliance_smoke_three_phase");
    const workspaceId = await currentWorkspaceIdOf(page);
    await createVoltageGroup(page, { workspaceId, sourceId, channelNames: ["VA", "VB", "VC"], displayName: "Bus A" });

    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    // Unlike Slice 1's own equivalent test (an empty workspace, where
    // Phasor's own no-recording fallback settles on "manual"), this
    // fixture upload gives Phasor a real bay to auto-bootstrap via its
    // bare-role-only detection fallback, so it legitimately settles on
    // "recording" instead -- wait for context loading to actually
    // finish (a real Engineering Context id assigned) rather than
    // asserting either specific mode.
    await expect(async () => {
      expect(await page.evaluate(() => wwPhasorState.contexts.length)).toBeGreaterThan(0);
    }).toPass({ timeout: 5000 });
    const before = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await selectQuantity(page, "Positive Sequence Voltage");
    await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");

    const after = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state, inputSource: wwPhasorState.inputSource,
    }));
    expect(after).toBe(before);
  });

  // 2026-09-23 UAT correction: reproduces the exact owner-reported
  // scenario -- a workspace containing obvious multi-bay Voltage
  // channel sets (KPDN1/KPDN2/SLKS, each a full VR/VY/VB triplet) still
  // showed "No Measurement Group is available for this workspace." on
  // Compliance because Measurement Group detection has never had ANY
  // automatic trigger anywhere in this codebase -- an engineer had to
  // visit "Manage Measurement Groups" and click "Suggest" first.
  // wwComplianceLoadGroups() now runs the same existing detection
  // bootstrap automatically. Fixtures:
  //   - compliance_smoke_multibay(.cfg/.dat): KPDN1/KPDN2/SLKS/SGT1,
  //     each VR/VY/VB, verified directly against the real
  //     detect_measurement_groups() to produce 4 clean STATUS_SUGGESTED
  //     groups with zero manual intervention.
  //   - compliance_smoke_review_required(.cfg/.dat): one bay (MCRS)
  //     with deliberately mixed single+pair phase representation
  //     (VR/VB alongside VRY), verified directly to produce
  //     STATUS_NEEDS_REVIEW -- a workspace with review-required groups
  //     ONLY (zero usable groups).
  test.describe("Bay/Measurement Group bootstrap and discovery (2026-09-23 UAT correction)", () => {
    test("multi-bay workspace: going directly to Compliance discovers groups without visiting Manage Measurement Groups first", async ({ page }) => {
      await page.goto("/index.html");
      await uploadFixture(page, "compliance_smoke_multibay");

      // Straight to Compliance -- never opens "Manage Measurement
      // Groups" first (the exact owner-reported workflow).
      await openCompliance(page);

      await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
      const options = await page.locator("#wwComplianceGroupSelect option").allTextContents();
      expect(new Set(options.slice(1))).toEqual(new Set(["KPDN1 VOLTAGE", "KPDN2 VOLTAGE", "SLKS VOLTAGE", "SGT1 VOLTAGE"]));
      // Four candidates -- not auto-selected, an explicit choice is required.
      await expect(page.locator("#wwComplianceGroupSelect")).toHaveValue("");
      await expect(page.locator("#wwComplianceManageGroupsBtn")).toBeHidden();

      await selectGroup(page, "KPDN1 VOLTAGE");
      await selectQuantity(page, "Phase A Voltage");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VR — KPDN1_VR"); // DEC-118: R/Y/B group -> V<sub>R</sub>

      await selectGroup(page, "SLKS VOLTAGE");
      await expect(page.locator("#wwComplianceMeasurementInput")).toHaveText("VR — SLKS_VR");
      await expect(page.locator("#wwComplianceMeasurementStatusRow")).toHaveText("Compatible");
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
      await expect(page.locator("#wwComplianceMeasurementField")).toBeHidden();
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
      // Compliance itself is still the active page underneath -- this
      // is an overlay, never a navigation.
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

      // The engineer reviews the ambiguous MCRS cluster and confirms it
      // via the existing Measurement Groups management endpoint (no
      // need to drive the confirm-drawer UI pixel-by-pixel here -- that
      // workflow is Measurement Groups' own test suite's job; this test
      // is about Compliance's own reaction to the resulting state
      // change, not about how the confirmation itself happens).
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
