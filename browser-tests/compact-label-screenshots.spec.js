// Screenshot evidence for the power compact label feature.
// Documents the key display surfaces before and after compact-label activation.

const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");
const path = require("path");
const fs = require("fs");

const SAMPLE_RATE = 1000.0;
const SAMPLES = 201;
const OUTDIR = path.join(__dirname, "..", ".slice1-evidence", "compact-label");

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
  if (value) await sel.selectOption(value);
  return !!value;
}

function save(page, name) {
  fs.mkdirSync(OUTDIR, { recursive: true });
  return page.screenshot({ path: path.join(OUTDIR, name), fullPage: false });
}

test("compact-label: CC manager list — single-phase power", async ({ page }) => {
  await uploadAndGoToCC(page, powerFixture(), "power.cfg");

  // Create Active Power
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="active_power"]').click();
  await selectOptionByLabel(page, "#wwCcPowerVoltageSelect", "VA");
  await selectOptionByLabel(page, "#wwCcPowerCurrentSelect", "IA");
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  // Create Reactive Power
  await page.locator("#wwCcNewChannelBtn").click();
  await page.locator('.ww-cc-operation-card[data-operation="reactive_power"]').click();
  await selectOptionByLabel(page, "#wwCcPowerVoltageSelect", "VA");
  await selectOptionByLabel(page, "#wwCcPowerCurrentSelect", "IA");
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  await save(page, "01-cc-list-single-phase.png");
});

test("compact-label: CC manager list — three-phase power", async ({ page }) => {
  await uploadAndGoToCC(page, threePhaseFixture(), "threep.cfg");

  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="three_phase_active_power"]').click();
  await page.locator("#wwCcThreePhaseSetSelect, .ww-cc-pair-notice, #wwCcThreePhaseV1").first().waitFor({ state: "visible", timeout: 8000 });
  const select = page.locator("#wwCcThreePhaseSetSelect");
  const firstSetId = await select.locator("optgroup[label='Complete Sets'] option").first().getAttribute("value");
  await select.selectOption(firstSetId);
  await expect(page.locator("#wwCcThreePhaseChangeBtn")).toBeVisible({ timeout: 5000 });
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  await save(page, "02-cc-list-three-phase.png");
});

test("compact-label: waveform trace and legend — single-phase power", async ({ page }) => {
  await uploadAndGoToCC(page, powerFixture(), "power.cfg");
  await page.locator("#wwCcNewChannelBtn").click();
  await page.locator('.ww-cc-operation-card[data-operation="active_power"]').click();
  await selectOptionByLabel(page, "#wwCcPowerVoltageSelect", "VA");
  await selectOptionByLabel(page, "#wwCcPowerCurrentSelect", "IA");
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  const calcs = await page.evaluate(() => Array.from(ww.calculatedChannels.values()));
  const power = calcs.find((c) => c.operation === "active_power");
  await page.locator("#mainNavWaveformBtn").click();
  const calcRow = page.locator(`#calculatedChannelsSidebarBody tr[data-channel-name="${power.name}"]`);
  await expect(calcRow).toBeVisible();
  await calcRow.click();
  await expect(calcRow).toHaveAttribute("aria-pressed", "true");
  await expect.poll(async () =>
    page.evaluate(() => ww.panels.flatMap((p) => ((p.chartEl && p.chartEl.data) || [])).length)
  ).toBeGreaterThan(0);
  await page.waitForTimeout(500);
  await save(page, "03-waveform-legend-single-phase.png");
});
