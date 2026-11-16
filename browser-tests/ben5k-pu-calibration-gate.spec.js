// Stage 3B-2A Browser Regression — BEN5K PU Calibration Gate (DEC-213)
//
// Verifies that a BEN5K source in PU mode produces:
//   • perUnitStatus == "calibration_unavailable" (not "configured" or "base_required")
//   • display unit == "kV" (engineering unit, NOT "pu")
//   • the channel is NOT rendered on a ":pu"-suffixed axis panel
//
// Also covers the original-risk scenario (DEC-050 analogue for BEN5K):
//   PU mode is already active when the BEN5K channel is added —
//   the gate must fire on the initial fetch, not only on a mode switch.
//
// Uses synthetic_ben5k.ben (backend/tests/fixtures/ben/) — 1 analog channel VA
// (~10 kV, unverified calibration authority), 100 samples at 5000 Hz.
//
// Prerequisites:
//   • Backend running with BEN5K_EXPERIMENTAL_ENABLED=1
//   • Tests skip gracefully if the backend rejects the BEN5K upload
//     (flag not enabled in this environment).
//
// Run with BEN5K enabled:
//   BEN5K_EXPERIMENTAL_ENABLED=1 npx playwright test ben5k-pu-calibration-gate.spec.js

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
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(FIXTURE);
  await page.locator("#uploadModalSubmitBtn").click();

  // If BEN5K_EXPERIMENTAL_ENABLED is not set, the backend returns 400 and the
  // modal shows an error message; detect that and return null to trigger a skip.
  const outcome = await Promise.race([
    page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 15_000 }).then(() => "hidden"),
    page.locator("#uploadModalStatus").getByText(/not supported|unsupported_ben_variant|not currently supported/i)
      .waitFor({ timeout: 15_000 }).then(() => "rejected"),
  ]).catch(() => "timeout");

  if (outcome !== "hidden") return null;
  const tableRow = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(tableRow).toBeVisible({ timeout: 10_000 });
  return tableRow.getAttribute("data-source-id");
}

// Open source details in the channel list (expand if collapsed).
async function expandSource(page, sid) {
  const sourceDetails = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await sourceDetails.evaluate((el) => el.open))) {
    await sourceDetails.locator(":scope > summary").click();
  }
}

// Return the ww.displayed entry snapshot for a channel, or null.
function displayedEntry(page, sid, name) {
  return page.evaluate(({ sid, name }) => {
    const entry = ww.displayed.get(wwChannelKey(sid, name));
    if (!entry) return null;
    const { channel } = entry;
    return {
      status: channel.perUnitStatus,
      unit: channel.unit,
      valueCount: (channel.values || []).length,
      firstValue: (channel.values || [])[0] ?? null,
    };
  }, { sid, name });
}

// Return panel snapshot: array of {key, channels[]}.
function panelSnapshot(page) {
  return page.evaluate(() =>
    ww.panels.map((p) => ({ key: p.groupKey, channels: p.channels.map((c) => c.channelName) }))
  );
}

// ---------------------------------------------------------------------------
// Test 1: perUnitStatus and unit via ww.displayed map (ENG→PU switch)
// ---------------------------------------------------------------------------

test("BEN5K PU gate: VA has perUnitStatus=calibration_unavailable and unit=kV after ENG→PU switch", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  // Open workspace, navigate to Waveform.
  await page.locator(`#recordingsTableBody tr[data-source-id="${sid}"]`).click();
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);
  await page.locator("#mainNavWaveformBtn").click();

  // Add VA in ENG mode first.
  await expandSource(page, sid);
  const vaRow = page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`);
  await expect(vaRow).toBeVisible({ timeout: 10_000 });
  await vaRow.click();
  await expect(vaRow).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  // Switch to PU mode.
  await page.locator("#wwUnitPerUnitBtn").click();

  // Poll and assert calibration gate fired with the correct status and unit.
  await expect.poll(
    () => displayedEntry(page, sid, "VA"),
    { timeout: 15_000 }
  ).toMatchObject({ status: "calibration_unavailable", unit: "kV" });

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

// ---------------------------------------------------------------------------
// Test 2: VA channel NOT in a :pu axis panel
// ---------------------------------------------------------------------------

test("BEN5K PU gate: VA is not rendered on a :pu axis panel", async ({ page }) => {
  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  await page.locator(`#recordingsTableBody tr[data-source-id="${sid}"]`).click();
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);
  await page.locator("#mainNavWaveformBtn").click();

  await expandSource(page, sid);
  const vaRow = page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`);
  await vaRow.click();
  await expect(vaRow).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  await page.locator("#wwUnitPerUnitBtn").click();

  // Wait for VA to settle as calibration_unavailable.
  await expect.poll(
    () => page.evaluate(({ sid }) => {
      const entry = ww.displayed.get(wwChannelKey(sid, "VA"));
      return entry ? entry.channel.perUnitStatus : null;
    }, { sid }),
    { timeout: 15_000 }
  ).toBe("calibration_unavailable");

  // No :pu panel may contain VA.
  const panels = await panelSnapshot(page);
  const puPanel = panels.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes("VA"));
  expect(puPanel, "VA must NOT be in a :pu panel when calibration_unavailable").toBeUndefined();
});

// ---------------------------------------------------------------------------
// Test 3: Original-risk scenario — PU mode already active at channel-add time
//
// Reproduces the DEC-050 category of risk for BEN5K: the user enables PU mode
// and THEN adds a BEN5K channel without switching to ENG first. The gate must
// fire on the initial fetch (not only on a subsequent mode switch), and the
// channel must never land on a :pu panel or show PU-converted values.
// ---------------------------------------------------------------------------

test("BEN5K PU gate (original-risk): channel added while PU mode is already active never lands on :pu panel", async ({ page }, info) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  // Open workspace and navigate to Waveform.
  await page.locator(`#recordingsTableBody tr[data-source-id="${sid}"]`).click();
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);
  await page.locator("#mainNavWaveformBtn").click();

  // ── Enable PU mode BEFORE adding any channel ────────────────────────────
  await page.locator("#wwUnitPerUnitBtn").click();
  expect(
    await page.evaluate(() => ww.unitMode),
    "unit mode must be per_unit before channel add"
  ).toBe("per_unit");

  // ── Add VA channel without switching back to ENG ─────────────────────────
  await expandSource(page, sid);
  const vaRow = page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`);
  await expect(vaRow).toBeVisible({ timeout: 10_000 });
  await vaRow.click();
  await expect(vaRow).toHaveAttribute("aria-pressed", "true");

  // Plotly chart must render.
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });

  // ── Wait for the waveform fetch to settle ────────────────────────────────
  // Poll until the entry has status and unit, then fetch the settled value.
  await expect.poll(
    () => displayedEntry(page, sid, "VA"),
    { timeout: 15_000, message: "VA ww.displayed entry must settle" }
  ).toMatchObject({ status: "calibration_unavailable", unit: "kV" });

  const channelState = await displayedEntry(page, sid, "VA");

  await page.screenshot({ path: info.outputPath("ben5k-pu-gate-original-risk-after-add.png") });

  // ── Core assertions: calibration gate fired on initial fetch ────────────
  expect(channelState.status, "perUnitStatus must be calibration_unavailable on first add").toBe("calibration_unavailable");
  expect(channelState.unit, "engineering unit kV must be preserved, not pu").toBe("kV");
  expect(channelState.valueCount, "trace must have data samples").toBeGreaterThan(0);
  // Fixture raw=1000, scale=0.01 → ~10 kV; value must be in engineering range, not pu (≈0..2).
  expect(Math.abs(channelState.firstValue), "first sample must be ~10 kV, not pu-normalised").toBeGreaterThan(2);

  // ── No :pu panel ─────────────────────────────────────────────────────────
  const panelsAfterAdd = await panelSnapshot(page);
  const puPanel = panelsAfterAdd.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes("VA"));
  expect(puPanel, "VA must NOT be in a :pu panel").toBeUndefined();

  // ── No duplicates ─────────────────────────────────────────────────────────
  const vaEntriesCount = await page.evaluate(({ sid }) => {
    let count = 0;
    ww.displayed.forEach((v, k) => {
      if (k === wwChannelKey(sid, "VA")) count++;
    });
    return count;
  }, { sid });
  expect(vaEntriesCount, "VA must appear exactly once in ww.displayed").toBe(1);

  // ── ENG → PU → ENG mode cycle ────────────────────────────────────────────
  // Switch to ENG: channel should show engineering values (no perUnitStatus).
  await page.locator("#wwUnitEngineeringBtn").click();
  // Poll until settled, then fetch the value for assertions.
  await expect.poll(
    () => page.evaluate(({ sid }) => {
      const entry = ww.displayed.get(wwChannelKey(sid, "VA"));
      return entry ? { status: entry.channel.perUnitStatus ?? null, unit: entry.channel.unit } : null;
    }, { sid }),
    { timeout: 10_000, message: "VA must settle in ENG mode" }
  ).toMatchObject({ unit: "kV" });
  const engState = await page.evaluate(({ sid }) => {
    const entry = ww.displayed.get(wwChannelKey(sid, "VA"));
    return entry ? { status: entry.channel.perUnitStatus ?? null, unit: entry.channel.unit } : null;
  }, { sid });
  expect(engState.unit, "unit must be kV in ENG mode").toBe("kV");
  // perUnitStatus may be "calibration_unavailable" even in ENG mode (the backend
  // pre-computes PU eligibility for informational purposes). What matters is that
  // unit == "kV", not that perUnitStatus is null.

  // Switch back to PU: gate must still fire (calibration_unavailable persists).
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(
    () => displayedEntry(page, sid, "VA"),
    { timeout: 10_000, message: "VA must re-settle as calibration_unavailable after PU re-enable" }
  ).toMatchObject({ status: "calibration_unavailable", unit: "kV" });
  const puStateAgain = await displayedEntry(page, sid, "VA");
  expect(puStateAgain.status, "perUnitStatus must be calibration_unavailable after PU re-enable").toBe("calibration_unavailable");
  expect(puStateAgain.unit, "unit must remain kV after PU re-enable").toBe("kV");

  // ── No panel state corruption ─────────────────────────────────────────────
  const panelsFinal = await panelSnapshot(page);
  const puPanelFinal = panelsFinal.find((p) => p.key && p.key.endsWith(":pu") && p.channels.includes("VA"));
  expect(puPanelFinal, "VA must still NOT be in a :pu panel after ENG→PU→ENG cycle").toBeUndefined();

  expect(errors, `Console/page errors:\n${errors.join("\n")}`).toEqual([]);
});
