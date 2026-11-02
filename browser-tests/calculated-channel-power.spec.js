// Phase A (V-I pairing): power arity calculated channels use type-aware
// dropdown grouping -- Voltage channels first in the Voltage dropdown,
// Current channels first in the Current dropdown, with Undefined channels
// clearly separated in both, and all remaining channels still accessible
// under "Other channels". No channel is hidden or silently reinterpreted.
//
// Real backend + real frontend, no mocks. Fixture: a 100 Hz, 1.0 s ASCII
// COMTRADE with three analog channels:
//   VA   (kV)  → classified Voltage
//   IA   (kA)  → classified Current
//   SIG  (pu)  → classified Undefined (unit "pu" does not match any known
//                base-unit pattern in channel_classification.py)

const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");

// 1000 Hz sample rate gives 20 samples/cycle at 50 Hz nominal, well above
// the MIN_SAMPLES_PER_CYCLE = 4 guard in calculated_channel_service.py.
const SAMPLE_RATE = 1000.0;
const SAMPLES = 201; // 0.2 s at 1000 Hz -- short but long enough for phasor

function powerFixture() {
  const cfg = [
    "SYNTH_POWER,SYNTH_DEV,1999",
    "3,3A,0D",
    "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "3,SIG,,,pu,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "50",
    "1",
    `${SAMPLE_RATE},${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";
  // 50 Hz sinusoids; 1000 samples/s → 20 samples/cycle.
  const samplesPerCycle = SAMPLE_RATE / 50;
  const usPerSample = 1_000_000 / SAMPLE_RATE;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const angle = (2 * Math.PI * i) / samplesPerCycle;
    const va = (110 * Math.sin(angle)).toFixed(6);
    const ia = (1.5 * Math.sin(angle - 0.3)).toFixed(6);
    const sig = (0.5 * Math.sin(angle)).toFixed(6);
    rows.push(`${i + 1},${Math.round(i * usPerSample)},${va},${ia},${sig}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

async function uploadFixture(page) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = powerFixture();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "power.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "power.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openPowerBuilder(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
  await expect(page.locator("#wwCcBuilderTitle")).toHaveText(
    operation === "active_power" ? "Active Power" :
    operation === "reactive_power" ? "Reactive Power" : "Apparent Power"
  );
}

async function selectByLabel(page, selectId, label) {
  const select = page.locator(selectId);
  const value = await select.locator("option").evaluateAll(
    (options, wanted) => (options.find((o) => o.textContent.includes(wanted)) || {}).value, label);
  expect(value, `option "${label}" in ${selectId}`).toBeTruthy();
  await select.selectOption(value);
}

function row(page, name) {
  return page.locator(".ww-cc-list-row").filter({
    has: page.locator(".ww-cc-list-row-name", { hasText: new RegExp(`^${name}$`) }),
  });
}

async function expectPowerRow(page, { glyph, operation, label, expression, unit }) {
  // Compact labels are display-only; the row still identifies the full calculation.
  const escapedGlyph = glyph.replace(/\|/g, "\\|");
  const createdRow = row(page, `${escapedGlyph} · SYNTH_POWER · VA`);
  await expect(createdRow).toBeVisible();
  await expect(createdRow.locator(".ww-cc-list-row-expr")).toHaveText(expression);
  await expect(createdRow.locator(".ww-cc-list-row-summary")).toHaveText(`${label} · Null: Propagate`);
  await expect(createdRow.locator(".ww-cc-list-row-class")).toHaveText("Power");
  await expect(createdRow.locator(".ww-cc-list-row-unit")).toHaveText(unit);
  const id = await createdRow.getAttribute("data-calculated-channel-id");
  const sourceId = await page.locator("#recordingsTableBody tr[data-source-id]").first().getAttribute("data-source-id");
  const calculation = await page.evaluate((calcId) => ww.calculatedChannels.get(calcId), id);
  expect(calculation).toMatchObject({
    id, name: `${glyph} (VA, IA)`, operation, unit, engineering_type: "Power",
    inputs: [
      { kind: "source", source_id: sourceId, channel_name: "VA" },
      { kind: "source", source_id: sourceId, channel_name: "IA" },
    ],
  });
}

test.describe("Power calculated channel: voltage/current dropdown grouping (Phase A)", () => {
  test("voltage dropdown: Voltage channels first, then Undefined, then Other", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    const groups = await page.locator("#wwCcPowerVoltageSelect optgroup").evaluateAll((els) =>
      els.map((g) => ({ label: g.label, options: Array.from(g.querySelectorAll("option")).map((o) => o.textContent.trim()) })));

    const groupLabels = groups.map((g) => g.label);
    // Voltage channels must appear as the first group.
    expect(groupLabels[0]).toBe("Voltage channels");
    // Undefined channels must appear as the second group.
    expect(groupLabels[1]).toBe("Undefined channels");

    // VA (kV → Voltage) is in the first group.
    expect(groups[0].options.join("|")).toContain("VA");
    // IA (kA → Current) does NOT belong in Voltage or Undefined groups.
    expect(groups[0].options.join("|")).not.toContain("IA");
    expect(groups[1].options.join("|")).not.toContain("IA");
    // SIG (pu → Undefined) is in the second group.
    expect(groups[1].options.join("|")).toContain("SIG");

    // IA is still accessible (in "Other channels"), not hidden.
    const allOptions = groups.flatMap((g) => g.options);
    expect(allOptions.join("|")).toContain("IA");
  });

  test("current dropdown: Current channels first, then Undefined, then Other", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    const groups = await page.locator("#wwCcPowerCurrentSelect optgroup").evaluateAll((els) =>
      els.map((g) => ({ label: g.label, options: Array.from(g.querySelectorAll("option")).map((o) => o.textContent.trim()) })));

    const groupLabels = groups.map((g) => g.label);
    // Current channels must appear as the first group.
    expect(groupLabels[0]).toBe("Current channels");
    // Undefined channels must appear as the second group.
    expect(groupLabels[1]).toBe("Undefined channels");

    // IA (kA → Current) is in the first group.
    expect(groups[0].options.join("|")).toContain("IA");
    // VA (kV → Voltage) does NOT belong in Current or Undefined groups.
    expect(groups[0].options.join("|")).not.toContain("VA");
    expect(groups[1].options.join("|")).not.toContain("VA");
    // SIG (pu → Undefined) is in the second group.
    expect(groups[1].options.join("|")).toContain("SIG");

    // VA is still accessible (in "Other channels"), not hidden.
    const allOptions = groups.flatMap((g) => g.options);
    expect(allOptions.join("|")).toContain("VA");
  });

  test("undefined channel is selectable in voltage dropdown without silent reinterpretation", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    // SIG appears in "Undefined channels" optgroup -- it is accessible for
    // manual selection and is not disabled.
    const sigOption = page.locator('#wwCcPowerVoltageSelect optgroup[label="Undefined channels"] option').filter({ hasText: "SIG" });
    await expect(sigOption).toHaveCount(1);
    await expect(sigOption).not.toHaveAttribute("disabled");
  });

  test("undefined channel is selectable in current dropdown without silent reinterpretation", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    const sigOption = page.locator('#wwCcPowerCurrentSelect optgroup[label="Undefined channels"] option').filter({ hasText: "SIG" });
    await expect(sigOption).toHaveCount(1);
    await expect(sigOption).not.toHaveAttribute("disabled");
  });

  test("create Active Power channel with Voltage + Current inputs", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    await selectByLabel(page, "#wwCcPowerVoltageSelect", "VA");
    await selectByLabel(page, "#wwCcPowerCurrentSelect", "IA");

    // Unit display is fixed to MW for Active Power regardless of input units.
    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("MW");
    // A name is auto-suggested.
    await expect(page.locator("#wwCcNameInput")).not.toHaveValue("");
    // Create button is enabled.
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    await expectPowerRow(page, {
      glyph: "P", operation: "active_power", label: "Active Power", unit: "MW",
      expression: "Re(V₁ × conj(I₁)) / 1e6 (VA, IA)",
    });
  });

  test("create Reactive Power channel with Voltage + Current inputs", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "reactive_power");

    await selectByLabel(page, "#wwCcPowerVoltageSelect", "VA");
    await selectByLabel(page, "#wwCcPowerCurrentSelect", "IA");

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("Mvar");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expectPowerRow(page, {
      glyph: "Q", operation: "reactive_power", label: "Reactive Power", unit: "Mvar",
      expression: "Im(V₁ × conj(I₁)) / 1e6 (VA, IA)",
    });
  });

  test("create Apparent Power channel with Voltage + Current inputs", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "apparent_power");

    await selectByLabel(page, "#wwCcPowerVoltageSelect", "VA");
    await selectByLabel(page, "#wwCcPowerCurrentSelect", "IA");

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("MVA");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expectPowerRow(page, {
      glyph: "|S|", operation: "apparent_power", label: "Apparent Power", unit: "MVA",
      expression: "|V₁ × conj(I₁)| / 1e6 (VA, IA)",
    });
  });

  test("voltage dropdown grouping is consistent across all three power operations", async ({ page }) => {
    await uploadFixture(page);
    for (const op of ["active_power", "reactive_power", "apparent_power"]) {
      await openPowerBuilder(page, op);
      const firstGroupLabel = await page.locator("#wwCcPowerVoltageSelect optgroup").first().getAttribute("label");
      expect(firstGroupLabel, `${op}: first group of voltage dropdown`).toBe("Voltage channels");
      // Close drawer before opening for next operation.
      await page.keyboard.press("Escape");
      await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    }
  });

  test("unary input dropdown for other operations is unaffected by power grouping", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await page.locator('.ww-cc-operation-card[data-operation="reverse_polarity"]').click();

    // Unary dropdown groups by source name, not by type.
    const groups = await page.locator("#wwCcUnaryInputSelect optgroup").evaluateAll((els) =>
      els.map((g) => g.label));
    // "Voltage channels" / "Current channels" must NOT appear here.
    expect(groups.join("|")).not.toContain("Voltage channels");
    expect(groups.join("|")).not.toContain("Current channels");
    expect(groups.join("|")).not.toContain("Undefined channels");
    // All three channels are accessible.
    const opts = await page.locator("#wwCcUnaryInputSelect option").evaluateAll((os) => os.map((o) => o.textContent));
    expect(opts.join("|")).toContain("VA");
    expect(opts.join("|")).toContain("IA");
    expect(opts.join("|")).toContain("SIG");
  });
});

// ---------------------------------------------------------------------------
// Phase D (DEC-207): Hybrid Automatic-Manual V-I Pairing UI
//
// Fixture: same COMTRADE with VA (kV), IA (kA), SIG (pu).
// VA + IA → one automatic pair (same source, unambiguous, null context).
// SIG → no role token; never appears in the pair picker.
// ---------------------------------------------------------------------------

// Wait for the pair picker select to appear and settle (API response may be
// slightly async; selector appears only after the API resolves with pairs).
async function waitForPairPicker(page) {
  await expect(page.locator("#wwCcPairSelect")).toBeVisible({ timeout: 5000 });
}

// Select an option in #wwCcPairSelect by matching partial label text.
async function selectPairByLabel(page, labelFragment) {
  const select = page.locator("#wwCcPairSelect");
  const value = await select.locator("option").evaluateAll(
    (opts, wanted) => (opts.find((o) => o.textContent.includes(wanted)) || {}).value,
    labelFragment
  );
  expect(value, `pair option "${labelFragment}"`).toBeTruthy();
  await select.selectOption(value);
}

test.describe("Phase D: Hybrid V-I Pair Picker", () => {
  test("pair picker appears after source with VA+IA is loaded", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);

    // The picker must have an "Automatic" optgroup with VA · IA.
    const groups = await page.locator("#wwCcPairSelect optgroup").evaluateAll((els) =>
      els.map((g) => ({ label: g.label, options: Array.from(g.querySelectorAll("option")).map((o) => o.textContent.trim()) })));
    const autoGroup = groups.find((g) => g.label === "Automatic");
    expect(autoGroup, "Automatic optgroup must exist").toBeTruthy();
    const autoText = autoGroup.options.join("|");
    expect(autoText).toContain("VA");
    expect(autoText).toContain("IA");
  });

  test("pair picker also shows Manual option", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);

    const groups = await page.locator("#wwCcPairSelect optgroup").evaluateAll((els) =>
      els.map((g) => g.label));
    expect(groups).toContain("Manual");
  });

  test("selecting an auto pair shows locked summary with Change button", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);

    await selectPairByLabel(page, "VA");

    // Summary panel must be visible; picker must be gone.
    await expect(page.locator(".ww-cc-pair-summary")).toBeVisible();
    await expect(page.locator("#wwCcPairChangeBtn")).toBeVisible();
    await expect(page.locator("#wwCcPairSelect")).not.toBeVisible();

    // Summary text must contain the voltage and current channel names.
    const summaryText = await page.locator(".ww-cc-pair-summary-text").textContent();
    expect(summaryText).toContain("VA");
    expect(summaryText).toContain("IA");
  });

  test("locked pair enables the Create button (inputs are set)", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);
    await selectPairByLabel(page, "VA");

    await expect(page.locator(".ww-cc-pair-summary")).toBeVisible();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("Change button reopens the pair picker", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);
    await selectPairByLabel(page, "VA");

    await expect(page.locator("#wwCcPairChangeBtn")).toBeVisible();
    await page.locator("#wwCcPairChangeBtn").click();

    // Picker must reappear; summary must be gone.
    await expect(page.locator("#wwCcPairSelect")).toBeVisible();
    await expect(page.locator(".ww-cc-pair-summary")).not.toBeVisible();
    // Cancel button must be visible when editing.
    await expect(page.locator("#wwCcPairCancelBtn")).toBeVisible();
  });

  test("Cancel button from editing returns to locked summary", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);
    await selectPairByLabel(page, "VA");
    await page.locator("#wwCcPairChangeBtn").click();
    await expect(page.locator("#wwCcPairCancelBtn")).toBeVisible();
    await page.locator("#wwCcPairCancelBtn").click();

    // Summary must be restored.
    await expect(page.locator(".ww-cc-pair-summary")).toBeVisible();
    await expect(page.locator("#wwCcPairChangeBtn")).toBeVisible();
    await expect(page.locator("#wwCcPairSelect")).not.toBeVisible();
  });

  test("selecting Manual shows voltage and current dropdowns", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);

    await selectPairByLabel(page, "Manual selection");

    await expect(page.locator("#wwCcPowerVoltageSelect")).toBeVisible();
    await expect(page.locator("#wwCcPowerCurrentSelect")).toBeVisible();
    // Picker still visible above manual dropdowns.
    await expect(page.locator("#wwCcPairSelect")).toBeVisible();
  });

  test("create Active Power channel via auto pair selection", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");
    await waitForPairPicker(page);
    await selectPairByLabel(page, "VA");

    await expect(page.locator(".ww-cc-pair-summary")).toBeVisible();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    // Channel appears in the list with V and I names.
    const rows = page.locator(".ww-cc-list-row");
    const rowTexts = await rows.evaluateAll((els) => els.map((el) => el.textContent));
    const matched = rowTexts.some((t) => t.includes("VA") && t.includes("IA"));
    expect(matched, "created channel row must mention VA and IA").toBeTruthy();
  });

  test("pair picker is consistent across all three power operations", async ({ page }) => {
    await uploadFixture(page);
    for (const op of ["active_power", "reactive_power", "apparent_power"]) {
      await openPowerBuilder(page, op);
      await waitForPairPicker(page);
      // Check the Automatic optgroup exists in the picker and contains a VA/IA option.
      const autoGroupCount = await page.locator('#wwCcPairSelect optgroup[label="Automatic"]').count();
      expect(autoGroupCount, `${op}: Automatic optgroup must exist`).toBe(1);
      const autoText = await page.locator('#wwCcPairSelect optgroup[label="Automatic"] option').evaluateAll(
        (opts) => opts.map((o) => o.textContent).join("|")
      );
      expect(autoText, `${op}: auto option must mention VA`).toContain("VA");
      await page.keyboard.press("Escape");
      await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    }
  });

  test("manual dropdowns shown immediately while pair API is pending (no deadlock)", async ({ page }) => {
    await uploadFixture(page);
    await openPowerBuilder(page, "active_power");

    // Immediately after opening (before API resolves), manual dropdowns must
    // already be visible -- the engineer must never be blocked.
    await expect(page.locator("#wwCcPowerVoltageSelect")).toBeVisible();
    await expect(page.locator("#wwCcPowerCurrentSelect")).toBeVisible();
  });

  test("pair picker does not appear for a source with no V or I channels", async ({ page }) => {
    await routeConfig(page);
    await page.goto("/index.html");

    // Upload a COMTRADE with only SIG (pu) -- no voltage, no current.
    const cfg = [
      "SYNTH_NOPAIR,SYNTH_DEV,1999",
      "1,1A,0D",
      "1,SIG,,,pu,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "50",
      "1",
      "200.0,5",
      "06/03/2026,10:00:00.000000",
      "06/03/2026,10:00:00.000000",
      "ASCII",
      "1.0",
    ].join("\r\n") + "\r\n";
    const dat = ["1,0,0.0", "2,5000,0.1", "3,10000,0.2", "4,15000,0.3", "5,20000,0.4"].join("\r\n") + "\r\n";
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await page.locator("#uploadModalFile_0").setInputFiles({ name: "nopair.cfg", mimeType: "application/octet-stream", buffer: Buffer.from(cfg, "latin1") });
    await page.locator("#uploadModalFile_1").setInputFiles({ name: "nopair.dat", mimeType: "application/octet-stream", buffer: Buffer.from(dat, "latin1") });
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await openPowerBuilder(page, "active_power");

    // Wait for the API to resolve (picker either appears or not).
    await page.waitForTimeout(2000);

    // No pair picker: API returned no pairs.
    await expect(page.locator("#wwCcPairSelect")).not.toBeVisible();

    // Manual dropdowns must still be shown.
    await expect(page.locator("#wwCcPowerVoltageSelect")).toBeVisible();
    await expect(page.locator("#wwCcPowerCurrentSelect")).toBeVisible();
  });
});
