// Compact label feature for power calculated channels (DEC-208 / DEC-202):
// wwPowerCompactLabel() produces concise labels like "P · SYNTH_POWER · VA"
// for both single- and three-phase power operations.
//
// Tested surfaces: CC manager list name, CC manager list summary row, waveform
// Plotly trace name, waveform legend chip, Waveform sidebar row.
// User alias always wins. Canonical calc.name is never modified.
//
// Fixtures:
//   power: SYNTH_POWER, VA (kV) + IA (kA) — single-phase power
//   threep: SYNTH_3P_LG, VA/VB/VC (kV) + IA/IB/IC (kA) — three-phase power

const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");

const SAMPLE_RATE = 1000.0;
const SAMPLES = 201;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function powerFixture() {
  const cfg = [
    "SYNTH_POWER,SYNTH_DEV,1999",
    "2,2A,0D",
    "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
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
    rows.push(`${i + 1},${Math.round(i * usps)},${(110 * Math.sin(t)).toFixed(6)},${(1.5 * Math.sin(t - 0.3)).toFixed(6)}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

function threePhaseFixture() {
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
  const spc = SAMPLE_RATE / 50;
  const usps = 1_000_000 / SAMPLE_RATE;
  const phi = 2 * Math.PI / 3;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    rows.push([
      `${i + 1}`, `${Math.round(i * usps)}`,
      (110 * Math.sin(t)).toFixed(6), (110 * Math.sin(t - phi)).toFixed(6), (110 * Math.sin(t + phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3)).toFixed(6), (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6), (1.5 * Math.sin(t - 0.3 + phi)).toFixed(6),
    ].join(","));
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function uploadAndGoToCC(page, { cfg, dat }, cfgName) {
  await routeConfig(page);
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: cfgName, mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: cfgName.replace(".cfg", ".dat"), mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function selectOptionByLabel(page, selectId, label) {
  const sel = page.locator(selectId);
  const value = await sel.locator("option").evaluateAll(
    (opts, wanted) => (opts.find((o) => o.textContent.includes(wanted)) || {}).value, label);
  expect(value, `option "${label}" in ${selectId}`).toBeTruthy();
  await sel.selectOption(value);
}

async function createSinglePhasePower(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
  // Voltage input
  await selectOptionByLabel(page, "#wwCcPowerVoltageSelect", "VA");
  // Current input
  await selectOptionByLabel(page, "#wwCcPowerCurrentSelect", "IA");
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

async function createThreePhasePower(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
  // Wait for set picker API response to resolve.
  await page.locator(
    "#wwCcThreePhaseSetSelect, .ww-cc-pair-notice, .ww-cc-pair-status.error, #wwCcThreePhaseV1"
  ).first().waitFor({ state: "visible", timeout: 8000 });
  // Select the first complete set.
  const select = page.locator("#wwCcThreePhaseSetSelect");
  const firstSetId = await select.locator("optgroup[label='Complete Sets'] option").first().getAttribute("value");
  expect(firstSetId, "At least one complete set must be present").toBeTruthy();
  await select.selectOption(firstSetId);
  // Wait for locked summary (Change button signals locked mode).
  await expect(page.locator("#wwCcThreePhaseChangeBtn")).toBeVisible({ timeout: 5000 });
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled({ timeout: 5000 });
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// Get the CC manager list row for a given compact display name.
const mgrRow = (page, display) =>
  page.locator(".ww-cc-list-row", { has: page.locator(".ww-cc-list-row-name", { hasText: display }) });

// Get all loaded Plotly trace names (plain text, HTML stripped).
async function plotlyTraceNames(page) {
  return page.evaluate(() =>
    ww.panels.flatMap((p) => ((p.chartEl && p.chartEl.data) || []).map((t) =>
      (t.name || "").replace(/<[^>]+>/g, ""))));
}

// ---------------------------------------------------------------------------
// Tests — single-phase power compact label
// ---------------------------------------------------------------------------

test.describe("Single-phase power compact label", () => {
  test("CC manager shows compact label 'P · SYNTH_POWER · VA' not the long generated name", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");

    // The canonical name is long (contains all inputs).
    const allCalcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()).map((c) => c.name));
    const canonicalName = allCalcs.find((n) => n.startsWith("P ("));
    expect(canonicalName, "canonical name not found").toBeTruthy();
    expect(canonicalName).toContain("VA");
    expect(canonicalName).toContain("IA");

    // The manager row uses the compact label, not the canonical name.
    await expect(mgrRow(page, "P · SYNTH_POWER · VA")).toBeVisible();
    await expect(page.locator(".ww-cc-list-row-name", { hasText: canonicalName })).toHaveCount(0);
  });

  test("CC manager summary row shows operation label + null policy, no input names", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");

    const row = mgrRow(page, "P · SYNTH_POWER · VA");
    await expect(row).toBeVisible();
    const summary = row.locator(".ww-cc-list-row-summary");
    // Operation label present
    await expect(summary).toContainText("Active Power");
    // Null policy present (wwCcNullPolicySummaryText format: "Null: Propagate")
    await expect(summary).toContainText("Null: Propagate");
    // No individual input channel names in the summary row
    const summaryText = await summary.textContent();
    expect(summaryText).not.toContain("VA·SYNTH_POWER");
    expect(summaryText).not.toContain("IA·SYNTH_POWER");
  });

  test("canonical name is untouched (calc.name never modified)", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");
    const calcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()));
    const power = calcs.find((c) => c.operation === "active_power");
    expect(power, "active_power calc not found").toBeTruthy();
    expect(power.name).toContain("P (");   // canonical form retained
    expect(power.name).toContain("VA");
    expect(power.name).toContain("IA");
  });

  test("user alias wins over compact label", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");
    const compactLabel = "P · SYNTH_POWER · VA";
    await expect(mgrRow(page, compactLabel)).toBeVisible();

    // Navigate to waveform to access the rename menu.
    await page.locator("#mainNavWaveformBtn").click();
    const calcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()));
    const power = calcs.find((c) => c.operation === "active_power");
    const canonicalName = power.name;
    const calcRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${canonicalName}"]`);
    await expect(calcRow).toBeVisible();

    // Rename via right-click context menu.
    await calcRow.click({ button: "right" });
    await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
    await page.locator("#wwChannelMenuRenameBtn").click();
    await expect(page.locator("#wwChannelRenameOverlay")).toBeVisible();
    await page.locator("#wwChannelRenameInput").fill("My Power Channel");
    await page.locator("#wwChannelRenameApplyBtn").click();
    await expect(page.locator("#wwChannelRenameOverlay")).toBeHidden();

    // Sidebar row now shows user alias.
    await expect(calcRow.locator(".channel-name-text")).toContainText("My Power Channel");

    // CC manager also shows user alias, not compact label.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator(".ww-cc-list-row-name", { hasText: "My Power Channel" })).toBeVisible();
    await expect(page.locator(".ww-cc-list-row-name", { hasText: compactLabel })).toHaveCount(0);
  });

  test("compact label appears in Plotly trace name; trace identity (meta) is unchanged", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");
    const calcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()));
    const power = calcs.find((c) => c.operation === "active_power");
    const canonicalName = power.name;

    await page.locator("#mainNavWaveformBtn").click();
    const calcRow = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${canonicalName}"]`);
    await calcRow.click();  // make visible
    await expect(calcRow).toHaveAttribute("aria-pressed", "true");

    // Wait for trace to appear.
    await expect.poll(async () => (await plotlyTraceNames(page)).length).toBeGreaterThan(0);
    const names = await plotlyTraceNames(page);
    const compactLabel = "P · SYNTH_POWER · VA";
    expect(names.some((n) => n.includes("P · SYNTH_POWER · VA")),
      `expected compact label in trace names: ${JSON.stringify(names)}`).toBe(true);

    // Trace identity (meta) still carries the canonical name, not the display label.
    const metaMatch = await page.evaluate((cn) =>
      ww.panels.flatMap((p) => ((p.chartEl && p.chartEl.data) || [])).find((t) => t.meta && t.meta.endsWith("::" + cn)),
      canonicalName);
    expect(metaMatch, "trace meta should reference canonical name").toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Tests — three-phase power compact label
// ---------------------------------------------------------------------------

test.describe("Three-phase power compact label", () => {
  test("CC manager shows compact label 'P₃ · SYNTH_3P_LG · VA' not the long generated name", async ({ page }) => {
    await uploadAndGoToCC(page, threePhaseFixture(), "threep.cfg");
    await createThreePhasePower(page, "three_phase_active_power");

    const allCalcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()).map((c) => c.name));
    const canonicalName = allCalcs.find((n) => n.startsWith("P₃ ("));
    expect(canonicalName, "3φ canonical name not found").toBeTruthy();

    const compactLabel = "P₃ · SYNTH_3P_LG · VA";
    await expect(mgrRow(page, compactLabel)).toBeVisible();
    await expect(page.locator(".ww-cc-list-row-name", { hasText: canonicalName })).toHaveCount(0);
  });

  test("three-phase summary row has no input names", async ({ page }) => {
    await uploadAndGoToCC(page, threePhaseFixture(), "threep.cfg");
    await createThreePhasePower(page, "three_phase_active_power");

    const compactLabel = "P₃ · SYNTH_3P_LG · VA";
    const row = mgrRow(page, compactLabel);
    await expect(row).toBeVisible();
    const summary = row.locator(".ww-cc-list-row-summary");
    await expect(summary).toContainText("Active Power (3φ)");
    // Null policy present
    await expect(summary).toContainText("Null: Propagate");
    const summaryText = await summary.textContent();
    expect(summaryText).not.toContain("VA·SYNTH_3P_LG");
  });
});

// ---------------------------------------------------------------------------
// Tests — non-power operation (L-L voltage) unchanged
// ---------------------------------------------------------------------------

test.describe("Non-power operations unaffected", () => {
  test("compact label does not apply to non-power calcs; full calc.name shown", async ({ page }) => {
    await uploadAndGoToCC(page, powerFixture(), "power.cfg");
    await createSinglePhasePower(page, "active_power");

    // The power channel gets compact label.
    await expect(mgrRow(page, "P · SYNTH_POWER · VA")).toBeVisible();

    // Now create a non-power channel (Reverse Polarity of VA).
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await page.locator('.ww-cc-operation-card[data-operation="reverse_polarity"]').click();
    await selectOptionByLabel(page, "#wwCcUnaryInputSelect", "VA");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    // The reverse-polarity channel shows its canonical name, not a compact label.
    await expect(page.locator(".ww-cc-list-row-name", { hasText: "-VA" })).toBeVisible();
    // The power channel still shows its compact label (unchanged).
    await expect(mgrRow(page, "P · SYNTH_POWER · VA")).toBeVisible();
  });
});
