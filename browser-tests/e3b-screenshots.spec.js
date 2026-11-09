/**
 * Phase E-3B screenshot capture spec.
 * Run: playwright test e3b-screenshots.spec.js
 * Output: test-results/e3b-screenshots/  (6 PNG files)
 */
const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");
const path = require("path");
const fs = require("fs");

const OUT = path.resolve(__dirname, "..", "test-results", "e3b-screenshots");
fs.mkdirSync(OUT, { recursive: true });

const SAMPLE_RATE = 1000.0;
const SAMPLES = 201;

function fixtureBuffers(channelLines, dataRowFn, numChannels) {
  const cfg = channelLines.join("\r\n") + "\r\n";
  const spc = SAMPLE_RATE / 50;
  const usps = 1_000_000 / SAMPLE_RATE;
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const t = (2 * Math.PI * i) / spc;
    rows.push(`${i + 1},${Math.round(i * usps)},${dataRowFn(t)}`);
  }
  return {
    cfg: Buffer.from(cfg, "latin1"),
    dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1"),
  };
}

function lgFixture() {
  const phi = (2 * Math.PI) / 3;
  return fixtureBuffers(
    [
      "SYNTH_3P_LG,SYNTH_DEV,1999",
      "6,6A,0D",
      "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "2,VB,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "3,VC,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "4,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "5,IB,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "6,IC,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "50", "1", `${SAMPLE_RATE},${SAMPLES}`,
      "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ],
    (t) => [
      (110 * Math.sin(t)).toFixed(6),
      (110 * Math.sin(t - phi)).toFixed(6),
      (110 * Math.sin(t + phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3)).toFixed(6),
      (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3 + phi)).toFixed(6),
    ].join(",")
  );
}

function unknownRefFixture() {
  const phi = (2 * Math.PI) / 3;
  return fixtureBuffers(
    [
      "SYNTH_3P_UNK,SYNTH_DEV,1999",
      "6,6A,0D",
      "1,VL1,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "2,VL2,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "3,VL3,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "4,IL1,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "5,IL2,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "6,IL3,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "50", "1", `${SAMPLE_RATE},${SAMPLES}`,
      "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ],
    (t) => [
      (110 * Math.sin(t)).toFixed(6),
      (110 * Math.sin(t - phi)).toFixed(6),
      (110 * Math.sin(t + phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3)).toFixed(6),
      (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3 + phi)).toFixed(6),
    ].join(",")
  );
}

function incompleteFixture() {
  const phi = (2 * Math.PI) / 3;
  return fixtureBuffers(
    [
      "SYNTH_3P_INC,SYNTH_DEV,1999",
      "4,4A,0D",
      "1,VA,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "2,VB,,,kV,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "3,IA,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "4,IB,,,kA,1.0,0.0,0,-999999,999999,1.0,1.0,P",
      "50", "1", `${SAMPLE_RATE},${SAMPLES}`,
      "06/03/2026,10:00:00.000000", "06/03/2026,10:00:00.000000", "ASCII", "1.0",
    ],
    (t) => [
      (110 * Math.sin(t)).toFixed(6),
      (110 * Math.sin(t - phi)).toFixed(6),
      (1.5 * Math.sin(t - 0.3)).toFixed(6),
      (1.5 * Math.sin(t - 0.3 - phi)).toFixed(6),
    ].join(",")
  );
}

async function uploadAndOpenCc(page, fixture) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = fixture;
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "test.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "test.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 15000 });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openThreePhase(page) {
  await page.locator("#wwCcNewChannelBtn").click();
  await page.locator('[data-operation="three_phase_active_power"]').click();
  await page.locator("#wwCcThreePhaseSetSelect, .ww-cc-pair-notice, #wwCcThreePhaseV1").first().waitFor({ state: "visible", timeout: 8000 });
}

async function selectFirstCompleteSet(page) {
  const select = page.locator("#wwCcThreePhaseSetSelect");
  const val = await select.locator("optgroup[label='Complete Sets'] option").first().getAttribute("value");
  await select.selectOption(val);
  await page.locator("#wwCcThreePhaseChangeBtn").waitFor({ state: "visible", timeout: 5000 });
}

// ---------------------------------------------------------------------------
// Screenshots
// ---------------------------------------------------------------------------

test.describe("Phase E-3B screenshots", () => {
  test("screenshot 1 — automatic set picker", async ({ page }) => {
    await uploadAndOpenCc(page, lgFixture());
    await openThreePhase(page);
    await page.screenshot({ path: path.join(OUT, "1-auto-set-picker.png") });
  });

  test("screenshot 2 — three-row locked summary", async ({ page }) => {
    await uploadAndOpenCc(page, lgFixture());
    await openThreePhase(page);
    await selectFirstCompleteSet(page);
    const panel = page.locator("#wwCcBuilderPanel");
    await panel.scrollIntoViewIfNeeded();
    await panel.screenshot({ path: path.join(OUT, "2-locked-summary.png") });
  });

  test("screenshot 3 — manual six-channel selection", async ({ page }) => {
    await uploadAndOpenCc(page, lgFixture());
    await openThreePhase(page);
    await page.locator("#wwCcThreePhaseSetSelect").selectOption("__manual__");
    await page.locator("#wwCcThreePhaseV1").waitFor({ state: "visible" });
    // Scroll to builder title (top of builder section) so Phase 1 is visible.
    await page.locator("#wwCcBuilderTitle").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "3-manual-six-channel.png") });
  });

  test("screenshot 4 — voltage-reference confirmation (VL1/VL2/VL3)", async ({ page }) => {
    await uploadAndOpenCc(page, unknownRefFixture());
    await openThreePhase(page);
    await selectFirstCompleteSet(page);
    await page.locator("#wwCcVoltRefConfirm").waitFor({ state: "visible" });
    const panel = page.locator("#wwCcBuilderPanel");
    await panel.scrollIntoViewIfNeeded();
    await panel.screenshot({ path: path.join(OUT, "4-voltage-ref-confirmation.png") });
  });

  test("screenshot 5 — incomplete-set notification", async ({ page }) => {
    await uploadAndOpenCc(page, incompleteFixture());
    await openThreePhase(page);
    const notice = page.locator(".ww-cc-pair-notice");
    await notice.waitFor({ state: "visible", timeout: 8000 });
    await notice.scrollIntoViewIfNeeded();
    await notice.screenshot({ path: path.join(OUT, "5-incomplete-notice.png") });
  });

  test("screenshot 6 — narrow 360px readability", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 860 });
    await uploadAndOpenCc(page, lgFixture());
    await openThreePhase(page);
    await selectFirstCompleteSet(page);
    const panel = page.locator("#wwCcBuilderPanel");
    await panel.scrollIntoViewIfNeeded();
    await page.screenshot({ fullPage: true, path: path.join(OUT, "6-narrow-360px.png") });
  });

  test("screenshot 7 — CC list with P₃ and Q₃ compact labels", async ({ page }) => {
    await uploadAndOpenCc(page, lgFixture());
    // Create P₃ channel.
    await openThreePhase(page);
    await selectFirstCompleteSet(page);
    await page.locator("#wwCcCreateBtn").click();
    // Wait for the drawer to close (--open class removed).
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/, { timeout: 10000 });
    // Create Q₃ channel.
    await page.locator("#wwCcNewChannelBtn").click();
    await page.locator('[data-operation="three_phase_reactive_power"]').click();
    await page.locator("#wwCcThreePhaseSetSelect, .ww-cc-pair-notice, #wwCcThreePhaseV1").first().waitFor({ state: "visible", timeout: 8000 });
    await page.locator("#wwCcThreePhaseSetSelect").waitFor({ state: "visible", timeout: 5000 });
    const val2 = await page.locator("#wwCcThreePhaseSetSelect optgroup[label='Complete Sets'] option").first().getAttribute("value");
    await page.locator("#wwCcThreePhaseSetSelect").selectOption(val2);
    await page.locator("#wwCcThreePhaseChangeBtn").waitFor({ state: "visible", timeout: 5000 });
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/, { timeout: 10000 });
    // Capture CC list showing P₃ · SYNTH_3P_LG · VA and Q₃ · SYNTH_3P_LG · VA.
    await expect(page.locator(".ww-cc-list-row-name").first()).toBeVisible();
    await page.screenshot({ path: path.join(OUT, "7-cc-list-p3-q3.png") });
  });

  test("screenshot 8 — Output Name field visible with autogenerated value", async ({ page }) => {
    await uploadAndOpenCc(page, lgFixture());
    await openThreePhase(page);
    await selectFirstCompleteSet(page);
    const nameInput = page.locator("#wwCcNameInput");
    await nameInput.waitFor({ state: "visible" });
    const panel = page.locator("#wwCcBuilderPanel");
    await panel.scrollIntoViewIfNeeded();
    await panel.screenshot({ path: path.join(OUT, "8-output-name-field.png") });
  });
});
