// Phase E-3B (DEC-208): Three-phase fundamental power calculated channels.
//
// Real backend + real frontend, no mocks.
//
// Fixture A (L-G complete set): VA/VB/VC (kV) + IA/IB/IC (kA) — ABC
// convention; single bare phase letters → detected as line_to_ground, no
// voltage-reference confirmation required.
//
// Fixture B (incomplete): VA/IA/VB/IB only — missing VC/IC → incomplete
// ABC set (C absent).
//
// Covered:
//   - Section-label cards appear in the operation picker (Single-Phase / Three-Phase Power)
//   - Complete set auto-detected and shown in set picker dropdown
//   - Selecting a set locks in six channels in the summary view
//   - L-G detection: no confirmation block, Create enabled immediately
//   - All three operations create successfully (active, reactive, apparent)
//   - Correct output units (MW / Mvar / MVA) and auto-suggested names
//   - Manual selection: __manual__ shows six phase channel dropdowns
//   - Manual mode: both confirmation checkboxes appear and gate Create
//   - Confirmation flags reset when any manual input changes
//   - Confirmation flags reset when set selection changes
//   - Incomplete set: notice shows with missing phase information
//   - Single-phase active_power regression (same fixture, existing behaviour)

const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");

const SAMPLE_RATE = 1000.0;
const SAMPLES = 201; // 0.2 s at 1000 Hz; enough for DFT phasor

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function threePhaseFixtureLG() {
  // VA / VB / VC (kV, line-to-ground by name) + IA / IB / IC (kA).
  // detect_voltage_reference: "A", "B", "C" ∈ _LG_SINGLE_TOKENS → line_to_ground.
  const cfg = [
    "SYNTH_3P_LG,SYNTH_DEV,1999",
    "6,6A,0D",
    "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VB,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "3,VC,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "4,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "5,IB,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "6,IC,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "50",
    "1",
    `${SAMPLE_RATE},${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";

  const spc = SAMPLE_RATE / 50; // samples per cycle
  const usps = 1_000_000 / SAMPLE_RATE;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    const phi = 2 * Math.PI / 3;
    const va = (110 * Math.sin(t)).toFixed(6);
    const vb = (110 * Math.sin(t - phi)).toFixed(6);
    const vc = (110 * Math.sin(t + phi)).toFixed(6);
    const ia = (1.5 * Math.sin(t - 0.3)).toFixed(6);
    const ib = (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6);
    const ic = (1.5 * Math.sin(t - 0.3 + phi)).toFixed(6);
    rows.push(`${i + 1},${Math.round(i * usps)},${va},${vb},${vc},${ia},${ib},${ic}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

function threePhaseFixtureIncomplete() {
  // VA / VB (kV) + IA / IB (kA) — only A and B phases, missing C.
  const cfg = [
    "SYNTH_3P_INC,SYNTH_DEV,1999",
    "4,4A,0D",
    "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VB,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "3,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "4,IB,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "50",
    "1",
    `${SAMPLE_RATE},${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";

  const spc = SAMPLE_RATE / 50;
  const usps = 1_000_000 / SAMPLE_RATE;
  const phi = 2 * Math.PI / 3;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    rows.push(
      `${i + 1},${Math.round(i * usps)},` +
      `${(110 * Math.sin(t)).toFixed(6)},` +
      `${(110 * Math.sin(t - phi)).toFixed(6)},` +
      `${(1.5 * Math.sin(t - 0.3)).toFixed(6)},` +
      `${(1.5 * Math.sin(t - 0.3 - phi)).toFixed(6)}`
    );
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function uploadAndOpenCc(page, fixture) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = fixture;
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "test.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "test.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openThreePhaseBuilder(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
  const expectedTitle = {
    three_phase_active_power: "Active Power (3φ)",
    three_phase_reactive_power: "Reactive Power (3φ)",
    three_phase_apparent_power: "Apparent Power (3φ)",
  }[operation];
  await expect(page.locator("#wwCcBuilderTitle")).toHaveText(expectedTitle);
}

// Wait for the set picker (or the "no sets" fallback) to resolve from API.
// Use .first() to avoid strict-mode failures when multiple matching elements
// are visible (e.g. when no complete sets are found the set picker AND the
// manual dropdowns are both rendered).
async function waitForSetPicker(page) {
  await page.locator(
    "#wwCcThreePhaseSetSelect, .ww-cc-pair-notice, .ww-cc-pair-status.error, #wwCcThreePhaseV1"
  ).first().waitFor({ state: "visible", timeout: 5000 });
}

// Select the first real complete set in the picker (not the placeholder).
async function selectFirstCompleteSet(page) {
  const select = page.locator("#wwCcThreePhaseSetSelect");
  const firstSetId = await select.locator("optgroup[label='Complete Sets'] option").first().getAttribute("value");
  expect(firstSetId, "At least one complete set must be present").toBeTruthy();
  await select.selectOption(firstSetId);
  // Wait for locked summary to appear (Change button signals locked mode).
  await expect(page.locator("#wwCcThreePhaseChangeBtn")).toBeVisible({ timeout: 3000 });
}

function ccRow(page, name) {
  return page.locator(".ww-cc-list-row").filter({
    has: page.locator(".ww-cc-list-row-name", { hasText: new RegExp(`^${name}$`) }),
  });
}

// ---------------------------------------------------------------------------
// Tests: operation card section labels
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: operation card section labels", () => {
  test("Single-Phase Power and Three-Phase Power section headers appear in the card list", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);

    const labels = await page.locator(".ww-cc-operation-section-label").allTextContents();
    expect(labels).toContain("Single-Phase Power");
    expect(labels).toContain("Three-Phase Power");
  });

  test("three-phase operation cards are present in the drawer", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);

    await expect(page.locator('[data-operation="three_phase_active_power"]')).toBeVisible();
    await expect(page.locator('[data-operation="three_phase_reactive_power"]')).toBeVisible();
    await expect(page.locator('[data-operation="three_phase_apparent_power"]')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Tests: automatic set detection and locked summary
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: automatic set detection (L-G fixture)", () => {
  test("set picker appears after opening three-phase builder", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await expect(page.locator("#wwCcThreePhaseSetSelect")).toBeVisible();
  });

  test("at least one complete set is listed in the picker", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    const setCount = await page.locator("#wwCcThreePhaseSetSelect optgroup[label='Complete Sets'] option").count();
    expect(setCount).toBeGreaterThanOrEqual(1);
  });

  test("selecting a complete set shows locked summary with three phase rows", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    // Three phase pair rows should be visible in the summary.
    const pairRows = await page.locator(".ww-cc-phase-pair-row").count();
    expect(pairRows).toBe(3);
  });

  test("L-G set: no confirmation block shown, Create button enabled", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    // No voltage confirmation checkbox should be required for L-G.
    await expect(page.locator("#wwCcVoltRefConfirm")).not.toBeVisible();
    // Create button enabled (no confirmation needed).
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("locked summary has a Change button to return to picker", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await page.locator("#wwCcThreePhaseChangeBtn").click();
    await expect(page.locator("#wwCcThreePhaseSetSelect")).toBeVisible();
  });

  test("set picker Cancel button restores locked summary", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await page.locator("#wwCcThreePhaseChangeBtn").click();
    await expect(page.locator("#wwCcThreePhaseCancelBtn")).toBeVisible();
    await page.locator("#wwCcThreePhaseCancelBtn").click();
    await expect(page.locator("#wwCcThreePhaseChangeBtn")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Tests: all three operations create successfully (L-G auto set)
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: create all three operations (L-G fixture)", () => {
  test("create Active Power (3φ): output unit MW, channel in list", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("MW");
    await expect(page.locator("#wwCcNameInput")).not.toHaveValue("");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    // Auto-suggested name contains P₃.
    await expect(page.locator(".ww-cc-list-row-name").first()).toContainText("P₃");
  });

  test("create Reactive Power (3φ): output unit Mvar, channel in list", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_reactive_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("Mvar");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expect(page.locator(".ww-cc-list-row-name").first()).toContainText("Q₃");
  });

  test("create Apparent Power (3φ): output unit MVA, channel in list", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_apparent_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("MVA");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expect(page.locator(".ww-cc-list-row-name").first()).toContainText("|S₃|");
  });
});

// ---------------------------------------------------------------------------
// Tests: manual selection
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: manual selection", () => {
  test("selecting __manual__ shows six phase channel dropdowns", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);

    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    for (const id of ["wwCcThreePhaseV1", "wwCcThreePhaseI1", "wwCcThreePhaseV2",
                      "wwCcThreePhaseI2", "wwCcThreePhaseV3", "wwCcThreePhaseI3"]) {
      await expect(page.locator(`#${id}`)).toBeVisible();
    }
  });

  test("manual voltage dropdowns group Voltage channels first", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    const groups = await page.locator("#wwCcThreePhaseV1 optgroup").evaluateAll((els) =>
      els.map((g) => g.label));
    expect(groups[0]).toBe("Voltage channels");
  });

  test("manual current dropdowns group Current channels first", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    const groups = await page.locator("#wwCcThreePhaseI1 optgroup").evaluateAll((els) =>
      els.map((g) => g.label));
    expect(groups[0]).toBe("Current channels");
  });

  test("manual mode: both confirmation checkboxes appear", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    await expect(page.locator("#wwCcVoltRefConfirm")).toBeVisible();
    await expect(page.locator("#wwCcPhasePairConfirm")).toBeVisible();
  });

  test("manual mode: Create disabled until both confirmation boxes are checked", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    // Select all 6 channels first (VA, IA, VB, IB, VC, IC in order).
    const selectIds = ["wwCcThreePhaseV1", "wwCcThreePhaseI1", "wwCcThreePhaseV2",
                       "wwCcThreePhaseI2", "wwCcThreePhaseV3", "wwCcThreePhaseI3"];
    const channelNames = ["VA", "IA", "VB", "IB", "VC", "IC"];
    for (let i = 0; i < 6; i++) {
      const sel = page.locator(`#${selectIds[i]}`);
      const val = await sel.locator("option").evaluateAll(
        (opts, name) => (opts.find((o) => o.textContent.includes(name)) || {}).value, channelNames[i]);
      if (val) await sel.selectOption(val);
      // After each manual change, confirmation flags reset — re-find dropdowns.
      // Wait for re-render to settle.
      await expect(page.locator(`#${selectIds[i]}`)).toBeVisible();
    }

    // Still disabled: neither box checked.
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    // Check only voltage reference → still disabled (phase pairing not confirmed).
    await page.locator("#wwCcVoltRefConfirm").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    // Check phase pairing too → now enabled.
    await page.locator("#wwCcPhasePairConfirm").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("manual mode: Create Active Power (3φ) succeeds after both confirmations", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    // Select all 6 channels (in phase order: V1,I1,V2,I2,V3,I3).
    const selectIds = ["wwCcThreePhaseV1", "wwCcThreePhaseI1", "wwCcThreePhaseV2",
                       "wwCcThreePhaseI2", "wwCcThreePhaseV3", "wwCcThreePhaseI3"];
    const channelNames = ["VA", "IA", "VB", "IB", "VC", "IC"];
    for (let i = 0; i < 6; i++) {
      const sel = page.locator(`#${selectIds[i]}`);
      const val = await sel.locator("option").evaluateAll(
        (opts, name) => (opts.find((o) => o.textContent.includes(name)) || {}).value, channelNames[i]);
      if (val) await sel.selectOption(val);
      await expect(page.locator(`#${selectIds[i]}`)).toBeVisible();
    }

    await page.locator("#wwCcVoltRefConfirm").check();
    await page.locator("#wwCcPhasePairConfirm").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expect(page.locator(".ww-cc-list-row-name").first()).toContainText("P₃");
  });
});

// ---------------------------------------------------------------------------
// Tests: confirmation flag resets
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: confirmation flag resets", () => {
  test("changing a manual input unchecks both confirmation boxes", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    // Check both boxes.
    await expect(page.locator("#wwCcVoltRefConfirm")).toBeVisible();
    await page.locator("#wwCcVoltRefConfirm").check();
    await page.locator("#wwCcPhasePairConfirm").check();
    await expect(page.locator("#wwCcVoltRefConfirm")).toBeChecked();
    await expect(page.locator("#wwCcPhasePairConfirm")).toBeChecked();

    // Change one input — this re-renders the fields with both flags reset.
    const sel = page.locator("#wwCcThreePhaseV1");
    const val = await sel.locator("option").evaluateAll(
      (opts) => (opts.find((o) => o.value && !o.value.startsWith("--")) || {}).value);
    if (val) await sel.selectOption(val);

    // After re-render, both boxes must be unchecked.
    await expect(page.locator("#wwCcVoltRefConfirm")).not.toBeChecked();
    await expect(page.locator("#wwCcPhasePairConfirm")).not.toBeChecked();
  });

  test("switching set selection resets confirmation flags", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);

    // Select first complete set, then change to __manual__ (simulating a set re-select).
    await selectFirstCompleteSet(page);
    await page.locator("#wwCcThreePhaseChangeBtn").click();

    // Switch to manual — flags should be clear.
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");
    await expect(page.locator("#wwCcVoltRefConfirm")).not.toBeChecked();
    await expect(page.locator("#wwCcPhasePairConfirm")).not.toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// Tests: incomplete set notice
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: incomplete set notice", () => {
  test("incomplete set notice appears when a phase is missing", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureIncomplete());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);

    // No complete sets; incomplete notice should be visible.
    await expect(page.locator(".ww-cc-pair-notice")).toBeVisible({ timeout: 5000 });
    const noticeText = await page.locator(".ww-cc-pair-notice").textContent();
    expect(noticeText).toContain("incomplete");
  });

  test("incomplete set notice mentions the missing phase (C)", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureIncomplete());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await expect(page.locator(".ww-cc-pair-notice")).toBeVisible({ timeout: 5000 });

    const noticeText = await page.locator(".ww-cc-pair-notice").textContent();
    expect(noticeText).toContain("C");
  });

  test("incomplete fixture: six manual dropdowns still accessible for manual entry", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureIncomplete());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);

    // With no complete sets, the set picker should still exist (for __manual__).
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");
    for (const id of ["wwCcThreePhaseV1", "wwCcThreePhaseI1", "wwCcThreePhaseV2",
                      "wwCcThreePhaseI2", "wwCcThreePhaseV3", "wwCcThreePhaseI3"]) {
      await expect(page.locator(`#${id}`)).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Regression: single-phase power still works (same fixture channels)
// ---------------------------------------------------------------------------

test.describe("Single-phase power regression (Phase A, same fixture)", () => {
  test("single-phase Active Power channel still creates successfully", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await page.locator('[data-operation="active_power"]').click();
    await expect(page.locator("#wwCcBuilderTitle")).toHaveText("Active Power");

    // Wait for single-phase pair picker.
    await expect(page.locator("#wwCcPairSelect")).toBeVisible({ timeout: 5000 });

    // Pick the VA/IA automatic pair.
    const pairSel = page.locator("#wwCcPairSelect");
    const vaIaVal = await pairSel.locator("option").evaluateAll(
      (opts) => (opts.find((o) => o.textContent.includes("VA") && o.textContent.includes("IA")) || {}).value);
    if (vaIaVal) {
      await pairSel.selectOption(vaIaVal);
      await expect(page.locator("#wwCcThreePhaseChangeBtn")).not.toBeVisible();
      await expect(page.locator("#wwCcPairChangeBtn")).toBeVisible();
    } else {
      // Fallback: manual pair with VA/IA.
      const vSel = page.locator("#wwCcPowerVoltageSelect");
      const iSel = page.locator("#wwCcPowerCurrentSelect");
      if (await vSel.isVisible()) {
        const vVal = await vSel.locator("option").evaluateAll(
          (opts) => (opts.find((o) => o.textContent.includes("VA")) || {}).value);
        if (vVal) await vSel.selectOption(vVal);
        const iVal = await iSel.locator("option").evaluateAll(
          (opts) => (opts.find((o) => o.textContent.includes("IA")) || {}).value);
        if (iVal) await iSel.selectOption(iVal);
      }
    }

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("MW");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expect(ccRow(page, "P \\(VA, IA\\)")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Fixture C: VL1/VL2/VL3 + IL1/IL2/IL3 — L123 convention, unknown voltage
// reference (no phase-naming evidence → voltage_reference = null,
// voltage_reference_confirmation_required = true)
// ---------------------------------------------------------------------------

function threePhaseFixtureUnknownRef() {
  const cfg = [
    "SYNTH_3P_UNK,SYNTH_DEV,1999",
    "6,6A,0D",
    "1,VL1,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VL2,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "3,VL3,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "4,IL1,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "5,IL2,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "6,IL3,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "50",
    "1",
    `${SAMPLE_RATE},${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";

  const spc = SAMPLE_RATE / 50;
  const usps = 1_000_000 / SAMPLE_RATE;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    const phi = 2 * Math.PI / 3;
    rows.push(
      `${i + 1},${Math.round(i * usps)},` +
      `${(110 * Math.sin(t)).toFixed(6)},` +
      `${(110 * Math.sin(t - phi)).toFixed(6)},` +
      `${(110 * Math.sin(t + phi)).toFixed(6)},` +
      `${(1.5 * Math.sin(t - 0.3)).toFixed(6)},` +
      `${(1.5 * Math.sin(t - 0.3 - phi)).toFixed(6)},` +
      `${(1.5 * Math.sin(t - 0.3 + phi)).toFixed(6)}`
    );
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

// ---------------------------------------------------------------------------
// Fixture D: VA/VB/VC + VRY + IA/IB/IC — ABC auto set (L-G, no confirm),
// plus VRY as a line-to-line channel accessible in manual voltage dropdowns.
// ---------------------------------------------------------------------------

function threePhaseFixtureLGWithLL() {
  const cfg = [
    "SYNTH_3P_LG_LL,SYNTH_DEV,1999",
    "7,7A,0D",
    "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VB,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "3,VC,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "4,VRY,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "5,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "6,IB,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "7,IC,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "50",
    "1",
    `${SAMPLE_RATE},${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";

  const spc = SAMPLE_RATE / 50;
  const usps = 1_000_000 / SAMPLE_RATE;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    const phi = 2 * Math.PI / 3;
    const va = (110 * Math.sin(t)).toFixed(6);
    const vb = (110 * Math.sin(t - phi)).toFixed(6);
    const vc = (110 * Math.sin(t + phi)).toFixed(6);
    const vry = (110 * Math.sqrt(3) * Math.sin(t + Math.PI / 6)).toFixed(6);
    const ia = (1.5 * Math.sin(t - 0.3)).toFixed(6);
    const ib = (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6);
    const ic = (1.5 * Math.sin(t - 0.3 + phi)).toFixed(6);
    rows.push(`${i + 1},${Math.round(i * usps)},${va},${vb},${vc},${vry},${ia},${ib},${ic}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

// ---------------------------------------------------------------------------
// Tests: unknown voltage reference — confirmation gate
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: voltage-reference confirmation (unknown reference)", () => {
  test("VL1/VL2/VL3 set: voltage-reference confirmation block appears", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureUnknownRef());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    // Confirmation checkbox must be present (voltage reference is unknown).
    await expect(page.locator("#wwCcVoltRefConfirm")).toBeVisible();
    // Create must be disabled before confirmation.
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
  });

  test("VL1/VL2/VL3 set: Create enabled only after voltage-reference confirmation", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureUnknownRef());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    // Still disabled without confirmation.
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    // Check the confirmation box.
    await page.locator("#wwCcVoltRefConfirm").check();

    // Now Create should be enabled.
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("VL1/VL2/VL3: Create succeeds after voltage-reference confirmation", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureUnknownRef());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);

    await page.locator("#wwCcVoltRefConfirm").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    // Channel should now be listed.
    await expect(page.locator(".ww-cc-list-row-name").first()).toContainText("P₃");
  });
});

// ---------------------------------------------------------------------------
// Tests: L-L voltage backend rejection (manual mode)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Tests: source-removal invalidation
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: source-removal invalidation", () => {
  test("removing recording source resets three-phase selection and clears confirmation flags", async ({ page }) => {
    // 1. Upload L-G fixture and select a complete three-phase set.
    await uploadAndOpenCc(page, threePhaseFixtureLG());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);
    await selectFirstCompleteSet(page);
    // Locked summary is active.
    await expect(page.locator("#wwCcThreePhaseChangeBtn")).toBeVisible();

    // 2. Close the drawer and navigate to Recordings.
    await page.locator("#wwCcDrawerCloseBtn").click();
    await page.locator("#mainNavRecordingsBtn").click();

    // 3. Remove the recording source.
    await page.locator('#recordingsTableBody button[data-action="remove"]').first().click();
    await expect(page.locator("#confirmOverlay")).toBeVisible();
    await page.locator("#confirmRemoveBtn").click();
    await page.locator("#confirmOverlay").waitFor({ state: "hidden", timeout: 10000 });

    // 4. Navigate back to Calculated Channels and re-open the builder.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
    await page.locator("#wwCcNewChannelBtn").click();
    await page.locator('[data-operation="three_phase_active_power"]').click();

    // 5. The set picker must appear (not the locked summary).
    await page.locator("#wwCcThreePhaseSetSelect").waitFor({ state: "visible", timeout: 8000 });
    // No locked summary (selection was cleared).
    await expect(page.locator("#wwCcThreePhaseChangeBtn")).not.toBeVisible();
    // No complete sets (no sources remain in workspace).
    await expect(page.locator("#wwCcThreePhaseSetSelect optgroup[label='Complete Sets']")).not.toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// Tests: L-L voltage backend rejection (manual mode)
// ---------------------------------------------------------------------------

test.describe("Three-Phase Power: L-L voltage backend rejection (manual mode)", () => {
  test("selecting a L-L named voltage in manual mode shows backend rejection error", async ({ page }) => {
    await uploadAndOpenCc(page, threePhaseFixtureLGWithLL());
    await openThreePhaseBuilder(page, "three_phase_active_power");
    await waitForSetPicker(page);

    // Switch to manual mode.
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");

    // Select VRY (L-L named) as V1.
    const v1Sel = page.locator("#wwCcThreePhaseV1");
    const vryVal = await v1Sel.locator("option").evaluateAll(
      (opts) => (opts.find((o) => o.textContent.includes("VRY")) || {}).value);
    expect(vryVal, "VRY must be available in the voltage dropdown").toBeTruthy();
    await v1Sel.selectOption(vryVal);
    await expect(v1Sel).toBeVisible();

    // Select L-G channels for the remaining slots.
    const selectIds = ["wwCcThreePhaseV2", "wwCcThreePhaseV3", "wwCcThreePhaseI1", "wwCcThreePhaseI2", "wwCcThreePhaseI3"];
    const channelNames = ["VA", "VB", "IA", "IB", "IC"];
    for (let i = 0; i < selectIds.length; i++) {
      const sel = page.locator(`#${selectIds[i]}`);
      const val = await sel.locator("option").evaluateAll(
        (opts, name) => (opts.find((o) => o.textContent.includes(name)) || {}).value, channelNames[i]);
      if (val) await sel.selectOption(val);
      await expect(sel).toBeVisible();
    }

    // Check both confirmation boxes — user (incorrectly) claims VRY is L-G.
    await page.locator("#wwCcVoltRefConfirm").check();
    await page.locator("#wwCcPhasePairConfirm").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    // Submit — backend rejects unconditionally for L-L.
    await page.locator("#wwCcCreateBtn").click();

    // Error element must become visible with a rejection message.
    await expect(page.locator("#wwCcError")).toBeVisible({ timeout: 5000 });
    const errorText = await page.locator("#wwCcError").textContent();
    expect(errorText).toMatch(/line.to.line|L.L|VRY/i);
  });
});
