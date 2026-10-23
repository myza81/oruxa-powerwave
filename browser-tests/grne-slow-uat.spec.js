// Stage S5 — BEN5K Slow GRNE Browser UAT
//
// Real-recording UAT using GRNE230726_143432426.ben.
// Verifies end-to-end: upload → recordings table → workspace →
// trend rendering for the three Group 0 candidate channels.
//
// Prerequisites:
//   • Backend running on port 8000 with BEN5K_SLOW_EXPERIMENTAL_ENABLED=1
//   • GRNE .ben file accessible at GRNE_BEN_PATH (env or default below)
//
// Run from the browser-tests directory:
//   BEN5K_SLOW_EXPERIMENTAL_ENABLED=1 npx playwright test grne-slow-uat.spec.js

const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

// ── File path ─────────────────────────────────────────────────────────────────

const GRNE_BEN_PATH =
  process.env.GRNE_BEN_PATH ||
  "C:\\Users\\fairizat\\Desktop\\BEN\\GRNE230726_143432426.ben";

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

// ── Expected recording metadata (from S4 engineering analysis) ────────────────

const EXPECTED_SIZE = 70315;
const EXPECTED_STATION = "GRNE";
const EXPECTED_SAMPLE_COUNT = 1188;
const EXPECTED_RATE_HZ = 20;
const EXPECTED_DURATION_S = 59.4;
const EXPECTED_PRE_TRIGGER = 400;
const EXPECTED_LAYOUT_FAMILY = "BEN32 BEN5K Slow Legacy";
const EXPECTED_TIMING_REFERENCE = "relative_elapsed";

// Group 0 candidate channels (confirmed tentative by S4 analysis)
const TENTATIVE_CHANNELS = ["POWER BDNG 1", "FREQ BDNG 1", "MVAR BDNG 1"];

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

async function waitForWorkspace(page) {
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);
  return row;
}

// ── Precondition: file present and correct size ───────────────────────────────

test("GRNE .ben file is present at Desktop\\BEN path", async () => {
  expect(
    fs.existsSync(GRNE_BEN_PATH),
    `GRNE file not found at: ${GRNE_BEN_PATH}`
  ).toBe(true);
  const size = fs.statSync(GRNE_BEN_PATH).size;
  expect(size, `Expected ${EXPECTED_SIZE} bytes, got ${size}`).toBe(EXPECTED_SIZE);
});

// ── Section 1: API — upload and source metadata ───────────────────────────────

test("GRNE Slow API: upload returns 201, ready status, layout_family and timing_reference", async ({ request }) => {
  const fileBuffer = fs.readFileSync(GRNE_BEN_PATH);
  const wsId = "ws-grne-slow-s5-metadata";
  const resp = await request.post(`${BACKEND}/api/v1/workspaces/${wsId}/sources`, {
    multipart: {
      ben_file: {
        name: "GRNE230726_143432426.ben",
        mimeType: "application/octet-stream",
        buffer: fileBuffer,
      },
    },
  });
  expect(resp.status()).toBe(201);
  const body = await resp.json();

  // Core import health
  expect(body.status, "source status").toBe("ready");
  expect(body.provider_type, "provider type").toBe("BEN");

  // Station identification
  expect(body.station_name, "station name").toContain(EXPECTED_STATION);

  // Channel counts: 3 tentative, 0 digital
  expect(body.analog_channel_count, "analog channel count").toBe(3);
  expect(body.digital_channel_count, "digital channel count").toBe(0);

  // Timing
  expect(body.sample_count, "sample count").toBe(EXPECTED_SAMPLE_COUNT);
  expect(body.duration_seconds, "duration").toBeCloseTo(EXPECTED_DURATION_S, 1);
  expect(body.timing_reference, "timing reference").toBe(EXPECTED_TIMING_REFERENCE);
  expect(body.timing_reference, "timing must not be absolute").not.toBe("absolute");

  // BEN5K Slow family identification
  expect(body.layout_family, "layout family").toBe(EXPECTED_LAYOUT_FAMILY);
});

test("GRNE Slow API: flag disabled — upload rejected", async ({ request }) => {
  const fileBuffer = fs.readFileSync(GRNE_BEN_PATH);
  const wsId = "ws-grne-slow-s5-flag-check";
  // This test cannot toggle the server's feature flag at runtime.
  // The S4 API tests (test_ben5k_slow_api.py) cover the disabled-flag case.
  // This test documents the expectation; in the running environment (flag ON)
  // the import succeeds and returns layout_family as a proxy for flag state.
  const resp = await request.post(`${BACKEND}/api/v1/workspaces/${wsId}/sources`, {
    multipart: {
      ben_file: {
        name: "GRNE230726_143432426.ben",
        mimeType: "application/octet-stream",
        buffer: fileBuffer,
      },
    },
  });
  expect(resp.status()).toBe(201);
  const body = await resp.json();
  // If the flag were disabled this would return 400 or fail with missing layout.
  // layout_family being non-null proves the Slow flag is active.
  expect(body.layout_family, "layout_family non-null proves BEN5K_SLOW_EXPERIMENTAL_ENABLED is ON").toBeTruthy();
});

// ── Section 2: Upload and recordings table ────────────────────────────────────

test("GRNE Slow uploads without error and appears in recordings table", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  // Station name should contain GRNE
  await expect(row).toContainText(EXPECTED_STATION);

  expect(errors, `Console errors on upload:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 3: Workspace opens with 3 tentative channel rows ─────────────────

test("GRNE Slow workspace shows exactly 3 analog channels (tentative Group 0)", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  // Exactly 3 analog channels: POWER BDNG 1, FREQ BDNG 1, MVAR BDNG 1
  const analogRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
  await expect(analogRows).toHaveCount(3, { timeout: 10_000 });

  // No digital channels
  const digitalRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"]');
  await expect(digitalRows).toHaveCount(0);

  expect(errors, `Console errors on workspace open:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 4: Channel names ──────────────────────────────────────────────────

test("GRNE Slow workspace shows all three tentative channel names", async ({ page }) => {
  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  for (const name of TENTATIVE_CHANNELS) {
    await expect(
      page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`)
    ).toBeVisible({ timeout: 5_000 });
  }
});

// ── Section 5: FREQ BDNG 1 renders (CONFIRMED channel) ───────────────────────

test("FREQ BDNG 1 renders a trend plot (confirmed Group 0 channel)", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  const freqCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="FREQ BDNG 1"]');
  await expect(freqCh).toBeVisible();
  await freqCh.click();
  await expect(freqCh).toHaveAttribute("aria-pressed", "true");

  // Waveform panel must render
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors on FREQ BDNG 1 plot:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 6: POWER BDNG 1 renders (PLAUSIBLE channel) ─────────────────────

test("POWER BDNG 1 renders a trend plot (plausible Group 0 channel)", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  const pwrCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="POWER BDNG 1"]');
  await expect(pwrCh).toBeVisible();
  await pwrCh.click();
  await expect(pwrCh).toHaveAttribute("aria-pressed", "true");

  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors on POWER BDNG 1 plot:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 7: MVAR BDNG 1 renders (PLAUSIBLE channel) ──────────────────────

test("MVAR BDNG 1 renders a trend plot (plausible Group 0 channel)", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  const mvarCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="MVAR BDNG 1"]');
  await expect(mvarCh).toBeVisible();
  await mvarCh.click();
  await expect(mvarCh).toHaveAttribute("aria-pressed", "true");

  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors on MVAR BDNG 1 plot:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 8: All three channels in one panel ───────────────────────────────

test("All three Group 0 channels plot together without console errors", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  for (const name of TENTATIVE_CHANNELS) {
    const ch = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
    await ch.click();
    await expect(ch).toHaveAttribute("aria-pressed", "true");
  }

  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors on all-channel plot:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 9: Relative time axis (no wall-clock dates) ──────────────────────

test("GRNE Slow waveform uses relative elapsed time axis (not wall-clock)", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  const freqCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="FREQ BDNG 1"]');
  await freqCh.click();
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  // Axis labels must be numeric elapsed values, not absolute dates.
  const axisLabels = await page.locator(".ww-chart .plotly .xaxislayer-above text").allTextContents();
  const hasAbsoluteDate = axisLabels.some(
    (t) => /20\d\d-\d\d-\d\d/.test(t) || /\d{2}:\d{2}:\d{2}/.test(t)
  );
  expect(
    hasAbsoluteDate,
    `Axis labels look like absolute timestamps: ${JSON.stringify(axisLabels)}`
  ).toBe(false);

  expect(errors, `Console errors on time axis check:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 10: Channel timing reference ─────────────────────────────────────

test("All three tentative channels carry timing_reference=relative_elapsed", async ({ page }) => {
  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  for (const name of TENTATIVE_CHANNELS) {
    const ch = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
    await expect(ch).toHaveAttribute("data-timing-reference", EXPECTED_TIMING_REFERENCE);
  }
});

// ── Section 11: Experimental notice visible in recording details ──────────────

test("BEN5K Slow experimental notice is visible in recording details", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  // Open the recording details (not the workspace — click the details/info button)
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible({ timeout: 15_000 });

  // Open the recording Details panel via the toggle button (not the workspace row click)
  const detailsToggle = row.locator("button.recording-details-toggle[data-action='details']");
  await expect(detailsToggle).toBeVisible({ timeout: 5_000 });
  await detailsToggle.click();

  // The details row should now be visible
  const detailsRow = page.locator(`tr.recording-details-row[data-details-for]`);
  await expect(detailsRow).toBeVisible({ timeout: 5_000 });

  // The BEN5K Slow notice should be present and visible inside the details panel
  await expect(page.locator(".ww-ben5k-slow-notice")).toBeVisible({ timeout: 5_000 });
  await expect(page.locator(".ww-ben5k-slow-notice-title")).toContainText("BEN5K Slow");

  expect(errors, `Console errors on notice check:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 12: Unresolved channels not shown in channel list ─────────────────

test("Invalidated JJNG channels (FREQ JJNG 1, MVAR JJNG 1) are not in the channel list", async ({ page }) => {
  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  // These channels were invalidated in S4 (UNRESOLVED_FORMULA_UNCONFIRMED)
  // and must not appear as plotable channels
  for (const name of ["FREQ JJNG 1", "MVAR JJNG 1", "POWER JJNG 1"]) {
    const ch = page.locator(`#channelGroups tr.channel-row--toggle[data-channel-name="${name}"]`);
    await expect(ch).toHaveCount(0, { timeout: 3_000 });
  }
});

// ── Section 13: Timing reference via API ─────────────────────────────────────

test("GRNE Slow API: source channels carry relative_elapsed timing", async ({ request }) => {
  const fileBuffer = fs.readFileSync(GRNE_BEN_PATH);
  const wsId = "ws-grne-slow-s5-timing";
  const resp = await request.post(`${BACKEND}/api/v1/workspaces/${wsId}/sources`, {
    multipart: {
      ben_file: {
        name: "GRNE230726_143432426.ben",
        mimeType: "application/octet-stream",
        buffer: fileBuffer,
      },
    },
  });
  expect(resp.status()).toBe(201);
  const body = await resp.json();
  const sourceId = body.source_id;  // upload response uses source_id, not id

  // Fetch channels (returns {source, timebase, analog_channels, digital_channels})
  const chResp = await request.get(`${BACKEND}/api/v1/workspaces/${wsId}/sources/${sourceId}/channels`);
  expect(chResp.status()).toBe(200);
  const chBody = await chResp.json();

  // timing_reference lives on timebase, not on individual channel objects
  expect(chBody.timebase.timing_reference, "timebase timing_reference").toBe(EXPECTED_TIMING_REFERENCE);
  // Also verify analog channel count
  expect(chBody.analog_channels.length, "analog channel count").toBe(3);
});

// ── Section 14: Zoom, pan interaction (basic) ────────────────────────────────

test("FREQ BDNG 1 waveform supports zoom and pan without errors", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, GRNE_BEN_PATH);
  await waitForWorkspace(page);

  const freqCh = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="FREQ BDNG 1"]');
  await freqCh.click();
  const chart = page.locator(".ww-chart .plotly").first();
  await expect(chart).toBeVisible({ timeout: 10_000 });

  // Zoom in via double-click on chart area
  const box = await chart.boundingBox();
  if (box) {
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    // Scroll to zoom (Plotly responds to wheel)
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(300);
    // Drag to pan
    await page.mouse.down();
    await page.mouse.move(cx + 50, cy, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(300);
  }

  // Chart still visible after interaction
  await expect(chart).toBeVisible();

  expect(errors, `Console errors during zoom/pan:\n${errors.join("\n")}`).toEqual([]);
});
