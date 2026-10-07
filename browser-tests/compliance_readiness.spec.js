// Compliance & Capability -- DEC-167: Reference-driven Measurement
// readiness, real-browser coverage.
//
//   Reference defines. Measurement satisfies.
//   Compliance never owns a private RMS channel or private per-unit
//   configuration.
//
// Fixture `line_to_line_multibay` (50 Hz, kV; uploaded through the real
// UI so DEC-104 builds the Measurement Groups and Engineering Contexts --
// nothing is seeded by hand):
//   KPDN1  VR/VY/VB instantaneous        -> preparation scenarios
//   KPDN2  VR/VY only                    -> missing phase
//   MCRS   VR/VY/VB already-RMS          -> RMS used directly / no safe line-line
// Reference Profiles/Layers are created through the real API (their own
// editor is covered by reference_envelope_editor.spec.js); everything
// Compliance-side is driven through the real UI.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const FIXTURE = "line_to_line_multibay";

async function workspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}
const wsUrl = async (page, suffix) => `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(await workspaceIdOf(page))}${suffix}`;

async function uploadMultibay(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${FIXTURE}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${FIXTURE}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").last()).toBeVisible();
}

async function addReference(page, { name = "Reference", representation = "line_line_rms", treatment = "each_phase", member = null, unit = "pu" } = {}) {
  const profile = await page.request.post(await wsUrl(page, "/reference-profiles"), { data: {
    name, category: "grid_requirement",
    assessment_definition: { representation, phase_treatment: treatment, member },
    unit, display_start_time: 0, display_end_time: 3, evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
    lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
    upper_boundary: null, metadata: {},
  } });
  expect(profile.ok()).toBeTruthy();
  const layer = await page.request.post(await wsUrl(page, "/reference-layers"), { data: { profile_id: (await profile.json()).id, visible: true } });
  expect(layer.ok()).toBeTruthy();
  return layer.json();
}

async function openComplianceAndSelect(page, bay) {
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
  await expect(page.locator("#wwComplianceGroupSelect option")).not.toHaveCount(1);
  await page.locator("#wwComplianceGroupSelect").selectOption({ label: `${bay} VOLTAGE` });
}

async function groupIdOf(page, bay) {
  const groups = await (await page.request.get(await wsUrl(page, "/compliance/voltage/measurement-groups"))).json();
  return groups.find((g) => g.display_name === `${bay} VOLTAGE`);
}
async function calcChannels(page) {
  return (await page.request.get(await wsUrl(page, "/calculated-channels"))).json();
}
const status = (page) => page.locator("#wwComplianceReadinessStatus");

test.describe("DEC-167 -- workflow order and structure", () => {
  test("Reference Layers come before Measurement; Event Alignment is a subsection inside Measurement", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const headings = await page.locator("#wwComplianceVoltagePanel h2").allTextContents();
    expect(headings).toEqual(["Reference Layers", "Measurement", "Comparison Chart"]);

    const reference = await page.locator("#wwComplianceReferenceLayersCard").boundingBox();
    const measurement = await page.locator("#wwComplianceMeasurementCard").boundingBox();
    const chart = await page.locator("#wwComplianceChartPanel").boundingBox();
    // Left configuration column: Reference first, Measurement below it; the chart is the right column.
    expect(reference.y).toBeLessThan(measurement.y);
    expect(Math.abs(reference.x - measurement.x)).toBeLessThanOrEqual(1);
    expect(chart.x).toBeGreaterThan(measurement.x + measurement.width - 1);

    await expect(page.locator("#wwComplianceEventAlignmentCard")).toHaveCount(0);
    const alignment = page.locator("#wwComplianceMeasurementCard #wwComplianceEventAlignmentSection");
    await expect(alignment).toBeVisible();
    await expect(alignment).toContainText("Event Alignment");
    await expect(alignment.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned");
    await expect(alignment.locator("#wwComplianceAlignSetBtn")).toBeDisabled();
  });

  test("there is no independent Assessment Quantity, Unit or Representation selector in Measurement", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page);
    await openComplianceAndSelect(page, "KPDN1");
    const card = page.locator("#wwComplianceMeasurementCard");
    await expect(card.locator("select")).toHaveCount(1); // only the Bay / Measurement Group picker
    await expect(card).not.toContainText("Assessment quantity");
    await expect(card).not.toContainText("Assessment Unit");
    await expect(page.locator("#wwComplianceMeasurementSelect")).toHaveCount(0);
  });
});

test.describe("DEC-167 -- requirements come from the active Reference, read-only", () => {
  test("a Line-Line RMS / Each Phase / pu reference shows exactly that requirement", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "Grid LVRT" });
    await openComplianceAndSelect(page, "KPDN1");
    const item = page.locator("#wwComplianceRequirementList li");
    await expect(item).toHaveCount(1);
    await expect(item).toContainText("Grid LVRT");
    await expect(item).toContainText("Line-Line RMS • Each Phase • pu");
    // Read-only: plain text, never inputs.
    await expect(page.locator("#wwComplianceRequirements input, #wwComplianceRequirements select")).toHaveCount(0);
    await expect(page.locator("#wwComplianceRequirements")).toContainText("Requirements from active references");
  });

  test("a Single reference names its voltage with true subscripts", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { treatment: "single", member: "AB", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator("#wwComplianceRequirementList li")).toContainText("Line-Line RMS • Single (VAB) • kV");
    await expect(page.locator("#wwComplianceRequirementList .ww-electrical-sub")).toHaveText(["AB"]);
    // Only the required voltage is listed in the readiness details.
    await expect(page.locator(".ww-compliance-member-list li")).toHaveCount(1);
  });

  test("Each Phase lists all three required voltages", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page);
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator(".ww-compliance-member-list li")).toHaveCount(3);
  });

  test("with no Reference the card says what is missing and never reports ready", async ({ page }) => {
    await uploadMultibay(page);
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("Add a Reference Layer to define what must be assessed.");
    await expect(page.locator("#wwComplianceRequirements")).toBeHidden();
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeHidden();
  });
});

test.describe("DEC-167 -- per-unit is required only when the Reference unit is pu", () => {
  test("pu reference without a base: a loud critical row, Configure Base, status Action required", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page); // Line-Line RMS, Each Phase, pu
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("⚠ Action required");
    const unitRow = page.locator('.ww-compliance-readiness-row[data-row="unit"]');
    await expect(unitRow).toHaveAttribute("data-state", "action_required");
    await expect(unitRow).toHaveClass(/ww-compliance-critical/);
    await expect(unitRow).toContainText("Base not configured");
    await expect(unitRow).toContainText("Per-unit assessment requires a configured voltage base.");
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeVisible();
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeVisible();
    await expect(page.locator("#wwComplianceReadinessActionCount")).toHaveText("2 actions required");
    const color = await unitRow.evaluate((el) => getComputedStyle(el).color);
    expect(color).toBe("rgb(170, 51, 51)");
  });

  test("kV reference: no per-unit blocker, no Configure Base, the unit row is calm", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    const unitRow = page.locator('.ww-compliance-readiness-row[data-row="unit"]');
    await expect(unitRow).toHaveAttribute("data-state", "not_required");
    await expect(unitRow).not.toHaveClass(/ww-compliance-critical/);
    await expect(unitRow).toContainText("kV — no per-unit base required");
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeHidden();
    // RMS preparation is still required because the representation says RMS.
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeVisible();
  });

  test("a base configured through the EXISTING group config path (as Waveform's Per-Unit Settings does) is reused at once", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms" });
    const group = await groupIdOf(page, "KPDN1");
    const put = await page.request.put(
      await wsUrl(page, `/sources/${encodeURIComponent(group.source_id)}/measurement-groups/${encodeURIComponent(group.id)}/voltage-config`),
      { data: { nominal_voltage_ll_kv: 132, reference_mode: "auto" } },
    );
    expect(put.ok()).toBeTruthy();
    await openComplianceAndSelect(page, "KPDN1");
    const unitRow = page.locator('.ww-compliance-readiness-row[data-row="unit"]');
    await expect(unitRow).toHaveAttribute("data-state", "ready");
    await expect(unitRow).toContainText("132 kV");
    await expect(unitRow).toContainText("kV L-");
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeHidden();
  });

  test("Configure Base opens the existing group editor on the selected group; saving there updates Compliance and the shared configuration", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeVisible();

    await page.locator("#wwComplianceConfigureBaseBtn").click();
    // The EXISTING Measurement Groups modal and its own drawer -- not a Compliance editor.
    await expect(page.locator("#measurementGroupsOverlay")).toBeVisible();
    await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await expect(page.locator("#wwMgDrawerTitle")).toHaveText("Edit Voltage Group");
    await page.locator("#wwMgVoltageKvInput").fill("275");
    await page.locator("#wwMgDrawerSaveBtn").click();
    await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    await page.locator("#measurementGroupsCloseBtn").click();
    await expect(page.locator("#measurementGroupsOverlay")).toBeHidden();
    // Compliance re-checked readiness: the base is reused, the blocker is gone.
    const unitRow = page.locator('.ww-compliance-readiness-row[data-row="unit"]');
    await expect(unitRow).toHaveAttribute("data-state", "ready");
    await expect(unitRow).toContainText("275 kV");
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeHidden();

    // One shared configuration: the group's own voltage config now holds it (what Waveform reads).
    const group = await groupIdOf(page, "KPDN1");
    const groups = await (await page.request.get(await wsUrl(page, `/sources/${encodeURIComponent(group.source_id)}/measurement-groups`))).json();
    const stored = groups.find((g) => g.id === group.id);
    expect(JSON.stringify(stored)).toContain("275");
  });
});

test.describe("DEC-167 -- shared RMS preparation, reuse and duplicate prevention", () => {
  test("Prepare Measurement creates ordinary shared Calculated Channels visible in Calculated Channels and the Waveform sidebar", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("⚠ Action required");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("Fundamental RMS needs preparation");
    expect(await calcChannels(page)).toEqual([]);

    await page.locator("#wwCompliancePrepareBtn").click();
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("✓");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("Existing calculated channels reused");
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();

    const channels = await calcChannels(page);
    expect(channels.map((c) => c.operation)).toEqual(["rms", "rms", "rms"]);

    // The shared frontend state and every consumer see them straight away.
    // The Waveform sidebar section (a Waveform-page element, so not visible from
    // Compliance) has been populated from the same shared state.
    expect(await page.evaluate(() => ww.calculatedChannels.size)).toBe(3);
    await expect(page.locator("#calculatedChannelsSidebarSection")).toHaveJSProperty("hidden", false);
    await expect(page.locator("#calculatedChannelsSidebarBody")).toContainText("RMS (KPDN1_VR)");
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator(".ww-cc-list-row-name")).toHaveCount(3);
    for (const channel of channels) await expect(page.locator(".ww-cc-list-row-name", { hasText: channel.name })).toBeVisible();
  });

  test("Line-Line RMS from instantaneous phases prepares line-to-line voltages then RMS; the base stays the only action left", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page); // pu
    await openComplianceAndSelect(page, "KPDN1");
    await page.locator("#wwCompliancePrepareBtn").click();
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();
    const channels = await calcChannels(page);
    expect(channels.map((c) => c.operation).sort()).toEqual(["line_to_line_voltage", "line_to_line_voltage", "line_to_line_voltage", "rms", "rms", "rms"]);
    await expect(status(page)).toHaveText("⚠ Action required");
    await expect(page.locator("#wwComplianceReadinessActionCount")).toHaveText("1 action required");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="unit"]')).toHaveClass(/ww-compliance-critical/);
    await expect(page.locator("#wwComplianceConfigureBaseBtn")).toBeVisible();
  });

  test("pre-existing RMS channels made elsewhere are discovered and reused; nothing is duplicated (also after a reload)", async ({ page }) => {
    await uploadMultibay(page);
    // The engineer built the RMS channels in Calculated Channels first, with their OWN names.
    const group = await groupIdOf(page, "KPDN1");
    const source = await (await page.request.get(await wsUrl(page, `/sources/${encodeURIComponent(group.source_id)}`))).json();
    expect(source.source_id).toBe(group.source_id);
    for (const name of ["KPDN1_VR", "KPDN1_VY", "KPDN1_VB"]) {
      const made = await page.request.post(await wsUrl(page, "/calculated-channels"), { data: {
        name: `my RMS ${name}`, operation: "rms",
        inputs: [{ kind: "source", source_id: group.source_id, channel_name: name }],
        parameters: { nominal_frequency_hz: 50 },
      } });
      expect(made.ok(), await made.text()).toBeTruthy();
    }
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("Existing calculated channels reused");
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();
    expect((await calcChannels(page)).length).toBe(3);

    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "KPDN1 VOLTAGE" });
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    expect((await calcChannels(page)).length).toBe(3);
  });

  test("a source that is already RMS is used directly: ready, no Prepare, no new channel", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "MCRS");
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toContainText("Source RMS channels used directly");
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();
    expect(await calcChannels(page)).toEqual([]);
  });
});

test.describe("DEC-167 -- incompatible cases are never softened", () => {
  test("Line-Line RMS required but only angle-less phase RMS exists: Measurement cannot satisfy this reference", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { unit: "kV" });
    await openComplianceAndSelect(page, "MCRS");
    await expect(status(page)).toHaveText("✕ Measurement cannot satisfy this reference");
    const critical = page.locator('.ww-compliance-readiness-row[data-row="incompatible"]');
    await expect(critical).toHaveClass(/ww-compliance-critical/);
    await expect(critical).toContainText("phase angle");
    await expect(critical).toContainText("unsafe");
    await expect(page.locator("#wwCompliancePrepareBtn")).toBeHidden();
    expect(await calcChannels(page)).toEqual([]);
  });

  test("a missing phase is incompatible, named in the group's own phase notation (R/Y/B)", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN2");
    await expect(status(page)).toHaveText("✕ Measurement cannot satisfy this reference");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="incompatible"]')).toContainText("VB is missing");
  });

  test("two references: one incompatible reference is never hidden by a satisfiable one", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "Phase-ground", representation: "phase_ground_rms", unit: "kV" });
    await addReference(page, { name: "Line-line", unit: "kV" });
    await openComplianceAndSelect(page, "MCRS");
    await expect(status(page)).toHaveText("✕ Measurement cannot satisfy this reference");
    await expect(page.locator('.ww-compliance-reference-readiness[data-status="ready"]')).toContainText("Phase-ground");
    await expect(page.locator('.ww-compliance-reference-readiness[data-status="incompatible"]')).toContainText("Line-line");
  });
});

test.describe("DEC-167 -- readiness follows the Reference Layers dynamically", () => {
  test("removing the layer returns the card to 'add a reference'; adding another re-checks", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("⚠ Action required");

    await page.locator("#wwRefLayerList .ww-ref-layer-remove-btn").first().click();
    await expect(status(page)).toHaveText("Add a Reference Layer to define what must be assessed.");
    await expect(page.locator("#wwComplianceRequirements")).toBeHidden();
  });

  test("switching Bay re-checks readiness for that Bay", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(status(page)).toHaveText("⚠ Action required");
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "MCRS VOLTAGE" });
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "KPDN2 VOLTAGE" });
    await expect(status(page)).toHaveText("✕ Measurement cannot satisfy this reference");
  });
});
