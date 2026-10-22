// Stage 8 — BEN5K GPTH 275kV Browser UAT
//
// Real-recording UAT using 261016_180314535_GPTH_275kV.ben.
// Verifies end-to-end: upload modal → recordings table → workspace →
// waveform rendering for analog and digital channels.
//
// Prerequisites:
//   • Backend running on port 8000 with BEN5K_EXPERIMENTAL_ENABLED=1
//   • GPTH .ben file accessible at GPTH_BEN_PATH (env or default below)
//
// Run from the browser-tests directory:
//   npx playwright test ben5k-gpth-uat.spec.js

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

// ── File path ─────────────────────────────────────────────────────────────────

const GPTH_BEN_PATH =
  process.env.GPTH_BEN_PATH ||
  "D:\\OneDrive - Tenaga Nasional Berhad\\WorkFiles\\Tripping Event\\2026\\20261016 132kV_KTBR\\BEN\\261016_180314535_GPTH_275kV.ben";

// ── Helpers ───────────────────────────────────────────────────────────────────

function trackErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

async function openBenUpload(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await expect(page.locator("#uploadModalFile_0")).toHaveAttribute("accept", ".ben,.BEN");
}

async function uploadBen(page, filePath) {
  await openBenUpload(page);
  await page.locator("#uploadModalFile_0").setInputFiles(filePath);
  await page.locator("#uploadModalSubmitBtn").click();
}

// ── Precondition check ────────────────────────────────────────────────────────

test("GPTH .ben file is present", async () => {
  expect(fs.existsSync(GPTH_BEN_PATH), `GPTH file not found at: ${GPTH_BEN_PATH}`).toBe(true);
  const size = fs.statSync(GPTH_BEN_PATH).size;
  expect(size).toBe(1629786);
});

// ── Section 1: Upload and recordings table ────────────────────────────────────

test("GPTH BEN5K uploads without error and appears in recordings table", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row).toContainText("GPTH 275kV - BEN5K");

  expect(errors, `Console errors on upload:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 2: Workspace opens with correct channel counts ────────────────────

test("GPTH workspace shows 35 analog channels and digital channels", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  // Verify 35 analog channel rows
  const analogRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
  await expect(analogRows).toHaveCount(35, { timeout: 10_000 });

  // Verify digital channels present
  const digitalRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"]');
  await expect(digitalRows).not.toHaveCount(0);

  expect(errors, `Console errors on workspace open:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 3: Key analog channel names ──────────────────────────────────────

test("GPTH workspace shows expected analog channel names", async ({ page }) => {
  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  for (const name of ["TBIN1 VR", "TBIN1 VY", "TBIN1 VB", "TBIN1 IR", "TBIN1 IY", "TBIN1 IB"]) {
    await expect(
      page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`)
    ).toBeVisible({ timeout: 5_000 });
  }
});

// ── Section 4: Analog waveform renders ───────────────────────────────────────

test("Enabling TBIN1 VR renders a waveform plot", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  const vrChannel = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="TBIN1 VR"]');
  await expect(vrChannel).toBeVisible();
  await vrChannel.click();
  await expect(vrChannel).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors after analog channel enable:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 5: 3-phase analog waveform ───────────────────────────────────────

test("TBIN1 3-phase voltages all render in a single waveform panel", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  for (const name of ["TBIN1 VR", "TBIN1 VY", "TBIN1 VB"]) {
    const ch = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
    await ch.click();
    await expect(ch).toHaveAttribute("aria-pressed", "true");
  }
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors on 3-phase voltage plot:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 6: Digital channel renders ───────────────────────────────────────

test("TBIN1 CB_R OPEN digital channel is present and can be enabled", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  // Enable an analog first to open the waveform panel
  const vrCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="TBIN1 VR"]');
  await vrCh.click();
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  // Digital channels (BEN5K) may start in a collapsed group section.
  // Verify the row is in the DOM with the correct attributes, then enable it.
  const cbROpen = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"][data-channel-name="TBIN1 CB_R OPEN"]');
  await expect(cbROpen).toHaveCount(1);
  await expect(cbROpen).toHaveAttribute("data-timing-reference", "relative_elapsed");

  // Digital channels with classification "never_triggered" are in a collapsed
  // group section in the channel list (channel-row--hidden). Use DOM dispatch
  // to enable the channel directly, bypassing the collapsed-container hide.
  await page.evaluate((channelName) => {
    const row = document.querySelector(
      `#channelGroups tr.channel-row--toggle[data-channel-kind="digital"][data-channel-name="${channelName}"]`
    );
    if (row) row.click();
  }, "TBIN1 CB_R OPEN");
  await expect(cbROpen).toHaveAttribute("aria-pressed", "true");

  expect(errors, `Console errors on digital channel enable:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 7: Timestamp safeguards — relative time axis ─────────────────────

test("GPTH waveform uses relative elapsed time axis, not absolute wall-clock", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  const vrCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="TBIN1 VR"]');
  await vrCh.click();
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  // The x-axis should show elapsed time (ms/s), not a wall-clock date.
  // Absolute UTC display would show a date like "2026-10-16" or "18:03:14"
  // on the Plotly axis. Elapsed mode shows values like "0", "200", "500" (ms).
  const axisLabels = await page.locator(".ww-chart .plotly .xaxislayer-above text").allTextContents();
  const hasAbsoluteDate = axisLabels.some(
    (t) => /20\d\d-\d\d-\d\d/.test(t) || /\d{2}:\d{2}:\d{2}/.test(t)
  );
  expect(hasAbsoluteDate, `Axis labels look like absolute timestamps: ${JSON.stringify(axisLabels)}`).toBe(false);

  expect(errors, `Console errors on timestamp axis check:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 8: API provenance check ──────────────────────────────────────────

test("GPTH source has timing_reference=relative_elapsed (timestamp safety)", async ({ request }) => {
  const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

  // Upload directly via request context (no frontend needed for this check)
  const fileBuffer = fs.readFileSync(GPTH_BEN_PATH);
  const wsId = "ws-ben5k-gpth-provenance-check";
  const resp = await request.post(`${BACKEND}/api/v1/workspaces/${wsId}/sources`, {
    multipart: {
      ben_file: {
        name: "261016_180314535_GPTH_275kV.ben",
        mimeType: "application/octet-stream",
        buffer: fileBuffer,
      },
    },
  });
  expect(resp.status()).toBe(201);
  const body = await resp.json();

  expect(body.provider_type).toBe("BEN");
  expect(body.status).toBe("ready");
  expect(body.station_name).toBe("GPTH 275kV - BEN5K");
  expect(body.analog_channel_count).toBe(35);
  expect(body.digital_channel_count).toBeGreaterThan(0);
  expect(body.sample_count).toBe(8262);
  expect(body.duration_seconds).toBeCloseTo(1.652, 2);
  expect(body.timing_reference).toBe("relative_elapsed");
  expect(body.timing_reference).not.toBe("absolute");
});

// ── Section 9: No console errors on full channel exploration ──────────────────

test("Enabling all TBIN1 channels produces no console errors", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GPTH_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  for (const name of ["TBIN1 VR", "TBIN1 VY", "TBIN1 VB", "TBIN1 IR", "TBIN1 IY", "TBIN1 IB", "TBIN1 IN"]) {
    const ch = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
    if (await ch.isVisible()) await ch.click();
  }
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  const cbR = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"][data-channel-name="TBIN1 CB_R OPEN"]');
  if (await cbR.isVisible()) await cbR.click();

  expect(errors, `Unexpected console/page errors:\n${errors.join("\n")}`).toEqual([]);
});
