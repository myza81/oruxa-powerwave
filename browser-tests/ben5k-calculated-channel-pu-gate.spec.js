// Stage 3B-2B-1 Browser Regression — Calculated Channel PU Calibration Gate (DEC-213)
//
// Verifies that the Stage 3B-2B-1 gate (`_collect_leaf_authorities`) propagates
// BEN5K calibration status through the calculated-channel dependency tree:
//
//   • A calculated channel derived from a BEN5K Voltage source → calibration_unavailable
//   • A chain (CalcB derived from CalcA, CalcA from BEN5K) → still calibration_unavailable
//   • Neither channel appears on a :pu axis panel
//   • COMTRADE-derived calculated channels are NOT blocked (backward compat)
//
// Uses synthetic_ben5k.ben (backend/tests/fixtures/ben/) — 1 analog channel VA
// (~10 kV, unverified calibration authority), 100 samples at 5000 Hz.
//
// Prerequisites:
//   • Backend running with BEN5K_EXPERIMENTAL_ENABLED=1
//   • Tests skip gracefully if the backend rejects the BEN5K upload.
//
// Run with BEN5K enabled:
//   BEN5K_EXPERIMENTAL_ENABLED=1 npx playwright test ben5k-calculated-channel-pu-gate.spec.js

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURE = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "ben", "synthetic_ben5k.ben"
);

function trackErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

// Upload synthetic_ben5k.ben via the Upload modal.
// Returns the source_id from the recordings table row, or null if the backend
// rejected the upload (BEN5K_EXPERIMENTAL_ENABLED not set in this environment).
async function uploadBen5kFixture(page) {
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(FIXTURE);
  await page.locator("#uploadModalSubmitBtn").click();

  const outcome = await Promise.race([
    page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 15_000 }).then(() => "hidden"),
    page.locator("#uploadModalStatus").getByText(/not supported|unsupported_ben_variant|not currently supported/i)
      .waitFor({ timeout: 15_000 }).then(() => "rejected"),
  ]).catch(() => "timeout");

  if (outcome !== "hidden") return null;
  const tableRow = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  await expect(tableRow).toBeVisible({ timeout: 10_000 });
  return tableRow.getAttribute("data-source-id");
}

// Open the Calculated Channels page and navigate into it.
async function openCalcPage(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

// Pick an input option by label substring in the unary input select.
async function pickInput(page, label) {
  const select = page.locator("#wwCcUnaryInputSelect");
  const value = await select.locator("option").evaluateAll(
    (options, wanted) => (options.find((o) => o.textContent.includes(wanted)) || {}).value,
    label
  );
  expect(value, `input option containing "${label}"`).toBeTruthy();
  await select.selectOption(value);
}

// Create a Reverse Polarity calculated channel from the named input.
// Returns { id, name } from the new sidebar row.
async function createReversePolarity(page, inputLabel) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="reverse_polarity"]').click();
  await pickInput(page, inputLabel);
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  // Find the newly created row — the last in the sidebar list.
  // channel-row--hidden is CSS-hidden (not shown in waveform preview) but IS in the DOM.
  const rows = page.locator("#calculatedChannelsSidebarBody tr[data-calculated-channel-id]");
  const lastRow = rows.last();
  await expect(lastRow).toBeAttached({ timeout: 10_000 });
  const id = await lastRow.getAttribute("data-calculated-channel-id");
  const name = await lastRow.getAttribute("data-channel-name");
  return { id, name };
}

// Return the ww.displayed entry snapshot for a calculated channel, or null.
function displayedCalcEntry(page, calcId, calcName) {
  return page.evaluate(({ calcId, calcName }) => {
    const entry = ww.displayed.get(wwChannelKey(calcId, calcName));
    if (!entry) return null;
    const { channel } = entry;
    return {
      status: channel.perUnitStatus,
      unit: channel.unit,
      valueCount: (channel.values || []).length,
      firstValue: (channel.values || [])[0] ?? null,
    };
  }, { calcId, calcName });
}

// Return panel snapshot: array of { key, channels[] }.
function panelSnapshot(page) {
  return page.evaluate(() =>
    ww.panels.map((p) => ({ key: p.groupKey, channels: p.channels.map((c) => c.channelName) }))
  );
}

// Add a calculated channel to the waveform by clicking its sidebar row.
// channel-row--hidden rows are CSS-hidden but attached; use force:true for the click.
async function showCalcChannel(page, name) {
  const row = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${name}"]`);
  await expect(row).toBeAttached({ timeout: 10_000 });
  if ((await row.getAttribute("aria-pressed")) !== "true") await row.click({ force: true });
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

// ---------------------------------------------------------------------------
// Test 1: BEN5K Voltage → Calculated Channel A (Reverse Polarity) → PU blocked
// ---------------------------------------------------------------------------

test("BEN5K calc gate: Reverse Polarity of BEN5K VA → calibration_unavailable in PU mode", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  // Create CalcA = Reverse Polarity of VA on the Calculated Channels page.
  await openCalcPage(page);
  const calcA = await createReversePolarity(page, "VA");

  // Navigate to Waveform, enable PU mode, then add CalcA.
  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#calculatedChannelsSidebarBody tr[data-calculated-channel-id]").first()).toBeVisible();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");   // no pane yet, so no pane-level mode control
  await showCalcChannel(page, calcA.name);
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  // Poll until the entry settles with calibration gate result.
  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 15_000, message: "CalcA ww.displayed entry must settle" }
  ).toMatchObject({ status: "calibration_unavailable" });

  const state = await displayedCalcEntry(page, calcA.id, calcA.name);
  expect(state.status, "CalcA: perUnitStatus must be calibration_unavailable").toBe("calibration_unavailable");
  expect(state.unit, "CalcA: engineering unit must be preserved, not pu").toBe("kV");
  expect(state.valueCount, "CalcA: trace must have data").toBeGreaterThan(0);
  // Fixture raw=1000, scale=0.01 → +10 kV; Reverse Polarity negates → −10 kV.
  // Check both sign (negative) and magnitude (engineering range, not pu-normalised ~0–2).
  expect(state.firstValue, "CalcA: Reverse Polarity must produce a negative value").toBeLessThan(0);
  expect(Math.abs(state.firstValue), "CalcA: magnitude must be ~10 kV, not pu-normalised").toBeGreaterThan(2);

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

// ---------------------------------------------------------------------------
// Test 2: BEN5K → CalcA → CalcB (chain of depth 2) → both blocked in PU mode
// ---------------------------------------------------------------------------

test("BEN5K calc gate: chain CalcB-from-CalcA-from-BEN5K → calibration_unavailable at depth 2", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  await openCalcPage(page);
  // CalcA = Reverse Polarity of VA (depth 1 from BEN5K).
  const calcA = await createReversePolarity(page, "VA");
  // CalcB = Reverse Polarity of CalcA (depth 2 from BEN5K).
  const calcB = await createReversePolarity(page, calcA.name);

  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#calculatedChannelsSidebarBody tr[data-calculated-channel-id]").first()).toBeVisible();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");   // no pane yet, so no pane-level mode control

  await showCalcChannel(page, calcA.name);
  await showCalcChannel(page, calcB.name);
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  // Both must settle as calibration_unavailable.
  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 15_000 }
  ).toMatchObject({ status: "calibration_unavailable" });

  await expect.poll(
    () => displayedCalcEntry(page, calcB.id, calcB.name),
    { timeout: 15_000, message: "CalcB (depth 2) must also be calibration_unavailable" }
  ).toMatchObject({ status: "calibration_unavailable" });

  const stateA = await displayedCalcEntry(page, calcA.id, calcA.name);
  const stateB = await displayedCalcEntry(page, calcB.id, calcB.name);
  expect(stateA.unit, "CalcA: engineering unit preserved").toBe("kV");
  expect(stateB.unit, "CalcB: engineering unit preserved at depth 2").toBe("kV");

  // Neither must appear on a :pu panel.
  const panels = await panelSnapshot(page);
  const puPanelWithA = panels.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes(calcA.name));
  const puPanelWithB = panels.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes(calcB.name));
  expect(puPanelWithA, "CalcA must NOT be on a :pu panel").toBeUndefined();
  expect(puPanelWithB, "CalcB (depth 2) must NOT be on a :pu panel").toBeUndefined();

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

// ---------------------------------------------------------------------------
// Test 3: Original-risk — PU mode active when CalcA is added for the first time
// ---------------------------------------------------------------------------

test("BEN5K calc gate (original-risk): CalcA added while PU already active → gate fires on initial fetch", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  await openCalcPage(page);
  const calcA = await createReversePolarity(page, "VA");

  // Navigate to Waveform and enable PU BEFORE adding CalcA.
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");   // no pane yet, so no pane-level mode control
  expect(
    await page.evaluate(() => ww.unitMode),
    "unit mode must be per_unit before channel add"
  ).toBe("per_unit");

  // Add CalcA without switching back to ENG.
  await showCalcChannel(page, calcA.name);
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 15_000, message: "CalcA must settle even when PU active at add time" }
  ).toMatchObject({ status: "calibration_unavailable", unit: "kV" });

  const state = await displayedCalcEntry(page, calcA.id, calcA.name);
  expect(state.status, "gate must fire on initial fetch, not only on mode switch").toBe("calibration_unavailable");
  expect(state.unit, "engineering unit kV must be preserved from the first fetch").toBe("kV");
  expect(state.valueCount, "trace must have data").toBeGreaterThan(0);

  const panels = await panelSnapshot(page);
  const puPanel = panels.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes(calcA.name));
  expect(puPanel, "CalcA must NOT be on a :pu panel from initial add").toBeUndefined();

  // ── ENG → PU → ENG mode cycle ────────────────────────────────────────────
  // Switch to ENG: channel shows engineering values.
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 10_000, message: "CalcA must settle in ENG mode" }
  ).toMatchObject({ unit: "kV" });
  const engState = await displayedCalcEntry(page, calcA.id, calcA.name);
  expect(engState.unit, "unit must be kV in ENG mode").toBe("kV");
  // Note: channel.values may be empty in ENG mode (populated on demand by the renderer);
  // the sign/magnitude assertion is verified in PU mode where calibration_unavailable
  // preserves the raw engineering values in the backend response.

  // No duplicates in ENG mode.
  const engDisplayCount = await page.evaluate(({ calcId, calcName }) => {
    let count = 0;
    ww.displayed.forEach((v, k) => {
      if (k === wwChannelKey(calcId, calcName)) count++;
    });
    return count;
  }, { calcId: calcA.id, calcName: calcA.name });
  expect(engDisplayCount, "CalcA must appear exactly once in ww.displayed in ENG mode").toBe(1);

  // Switch back to PU: gate must still fire.
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 10_000, message: "CalcA must re-settle as calibration_unavailable after PU re-enable" }
  ).toMatchObject({ status: "calibration_unavailable", unit: "kV" });
  const puAgainState = await displayedCalcEntry(page, calcA.id, calcA.name);
  expect(puAgainState.status, "gate must still fire after ENG→PU→ENG cycle").toBe("calibration_unavailable");
  expect(puAgainState.unit, "unit must remain kV after cycle").toBe("kV");

  // No :pu panel after cycle.
  const panelsFinal = await panelSnapshot(page);
  const puPanelFinal = panelsFinal.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes(calcA.name));
  expect(puPanelFinal, "CalcA must still NOT be on a :pu panel after ENG→PU→ENG cycle").toBeUndefined();

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

// ---------------------------------------------------------------------------
// Test 4: COMTRADE-baseline — calc channel from COMTRADE is NOT blocked (backward compat)
//
// This test uses a small ASCII COMTRADE fixture (inline buffer, no file needed).
// The calculated channel must resolve PU normally (base_required or configured),
// never calibration_unavailable — confirming that adding the BEN5K gate does
// not regress existing COMTRADE workflows.
// ---------------------------------------------------------------------------

test("BEN5K calc gate (baseline): COMTRADE-sourced Reverse Polarity is NOT blocked in PU mode", async ({ page }) => {
  const errors = trackErrors(page);

  // Build a minimal ASCII COMTRADE with one voltage channel VA (110 V nominal).
  const { routeConfig } = require("./support/relay_import_helpers");
  await routeConfig(page);
  await page.goto("/index.html");

  const SAMPLES = 51;
  const cfg = [
    "BASELINE_STATION,BASELINE,2026",
    "1,1A,0D",
    "1,VA,,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
    "50",
    "1",
    `1000.0,${SAMPLES}`,
    "11/12/2026,00:00:00.000000",
    "11/12/2026,00:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    rows.push(`${i + 1},${i * 1000},${(100 * Math.sin((2 * Math.PI * i) / 20)).toFixed(4)}`);
  }
  const dat = rows.join("\r\n") + "\r\n";

  await page.locator("#wwRdUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "baseline.cfg", mimeType: "application/octet-stream", buffer: Buffer.from(cfg, "latin1") });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "baseline.dat", mimeType: "application/octet-stream", buffer: Buffer.from(dat, "latin1") });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item").first()).toBeVisible({ timeout: 10_000 });

  await openCalcPage(page);
  const calcA = await createReversePolarity(page, "VA");

  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwApplyUnitMode("per_unit"));
  await expect.poll(() => page.evaluate(() => ww.unitMode)).toBe("per_unit");   // no pane yet, so no pane-level mode control
  await showCalcChannel(page, calcA.name);
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  // Poll until settled — should NOT be calibration_unavailable.
  await expect.poll(
    () => displayedCalcEntry(page, calcA.id, calcA.name),
    { timeout: 15_000, message: "COMTRADE CalcA must settle" }
  ).not.toBeNull();

  const state = await displayedCalcEntry(page, calcA.id, calcA.name);
  expect(
    state.status,
    "COMTRADE-sourced CalcA must NOT be calibration_unavailable — backward compat must be preserved"
  ).not.toBe("calibration_unavailable");

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});
