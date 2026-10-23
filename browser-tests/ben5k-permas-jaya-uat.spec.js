// Stage 11 Section B — Permas Jaya BEN5K compatibility UAT
//
// Prerequisites:
//   • Backend running on port 8200 (or PW_BACKEND_PORT) with BEN5K_EXPERIMENTAL_ENABLED=1
//   • Permas Jaya .ben file accessible at PERMAS_BEN_PATH (env or default below)
//
// Run from the browser-tests directory:
//   PW_BACKEND_PORT=8200 npx playwright test ben5k-permas-jaya-uat.spec.js
//
// Expected results (confirmed by Stage 11 Section B):
//   • station_name:          "Permas Jaya"
//   • analog_channel_count:  27 (one phantom detected at wi=15; PLTG1 IN/KTBR1 IN)
//   • digital_channel_count: 82 (all verified; no constant-placeholder in this file)
//   • timing_reference:      "relative_elapsed" (timestamp safeguard active)
//   • sample_count:          7719
//   • duration_seconds:      ~1.544 s at 5000 Hz

const { test, expect } = require("./support/test");
const fs = require("fs");
const path = require("path");

const PERMAS_BEN_PATH =
  process.env.PERMAS_BEN_PATH ||
  "D:\\OneDrive - Tenaga Nasional Berhad\\WorkFiles\\Tripping Event\\2026\\20261016 132kV_KTBR\\BEN\\261016_175827403_Permas_Jaya.ben";

// ── helpers ──────────────────────────────────────────────────────────────────

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

async function uploadBen(page, benPath) {
  await openBenUpload(page);
  await page.locator("#uploadModalFile_0").setInputFiles(benPath);
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 30_000 });
}

// ── Section 1: file presence ──────────────────────────────────────────────────

test("Permas Jaya .ben file is present", () => {
  expect(fs.existsSync(PERMAS_BEN_PATH), `BEN file not found: ${PERMAS_BEN_PATH}`).toBe(true);
  const size = fs.statSync(PERMAS_BEN_PATH).size;
  expect(size).toBe(941793);
});

// ── Section 2: API provenance — channel count + timestamp safety ───────────────

test("Permas Jaya source: 27 analog, 82 digital, relative_elapsed timing", async ({ request }) => {
  const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

  const fileBuffer = fs.readFileSync(PERMAS_BEN_PATH);
  const wsId = "ws-ben5k-permas-provenance";
  const resp = await request.post(`${BACKEND}/api/v1/workspaces/${wsId}/sources`, {
    multipart: {
      ben_file: {
        name: "261016_175827403_Permas_Jaya.ben",
        mimeType: "application/octet-stream",
        buffer: fileBuffer,
      },
    },
  });
  expect(resp.status()).toBe(201);
  const body = await resp.json();

  expect(body.provider_type).toBe("BEN");
  expect(body.status).toBe("ready");
  expect(body.station_name).toBe("Permas Jaya");
  // 27 not 28: one phantom (PLTG1 IN wi=15 reads voltage-strength 11 421 counts)
  expect(body.analog_channel_count).toBe(27);
  // All 82 digital channels are verified (no constant-0x0800 placeholder feeders)
  expect(body.digital_channel_count).toBe(82);
  expect(body.sample_count).toBe(7719);
  expect(body.duration_seconds).toBeCloseTo(1.544, 2);
  // Timestamp safeguard: relative elapsed time axis enforced
  expect(body.timing_reference).toBe("relative_elapsed");
  expect(body.timing_reference).not.toBe("absolute");
});

// ── Section 3: upload & workspace (browser path) ─────────────────────────────

test("Permas Jaya uploads without error and appears in recordings table", async ({ page }) => {
  const errors = trackErrors(page);
  await uploadBen(page, PERMAS_BEN_PATH);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible({ timeout: 10_000 });
  expect(errors, `Console errors on upload:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 4: channel count in workspace ─────────────────────────────────────

test("Permas Jaya workspace shows 27 analog and ≥1 digital channels", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, PERMAS_BEN_PATH);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  const analogRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
  await expect(analogRows).toHaveCount(27, { timeout: 10_000 });

  const digitalRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"]');
  await expect(digitalRows).not.toHaveCount(0);

  expect(errors, `Console errors on workspace open:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 5: key channel names ──────────────────────────────────────────────

test("Permas Jaya workspace shows expected analog channel names", async ({ page }) => {
  await uploadBen(page, PERMAS_BEN_PATH);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  // These channels must be present (spanning multiple feeders)
  for (const name of ["PLTG1 VR", "PLTG1 VY", "PLTG1 VB", "KTBR2 VR", "PGPS1 IR"]) {
    await expect(
      page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`)
    ).toBeVisible({ timeout: 5_000 });
  }

  // PLTG1 IN must NOT be present (it is the phantom at wi=15)
  await expect(
    page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="PLTG1 IN"]`)
  ).toHaveCount(0);
});

// ── Section 6: waveform renders ───────────────────────────────────────────────

test("Enabling PLTG1 VR renders a waveform plot", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, PERMAS_BEN_PATH);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  const vrCh = page.locator(
    '#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="PLTG1 VR"]'
  );
  await expect(vrCh).toBeVisible();
  await vrCh.click();
  await expect(vrCh).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  expect(errors, `Console errors after waveform enable:\n${errors.join("\n")}`).toEqual([]);
});

// ── Section 7: relative time axis ────────────────────────────────────────────

test("Permas Jaya waveform uses relative elapsed time axis, not absolute wall-clock", async ({ page }) => {
  const errors = trackErrors(page);

  await uploadBen(page, PERMAS_BEN_PATH);
  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await row.click();
  await expect.poll(
    () => page.evaluate(() => document.getElementById("workspaceRow")?.hidden),
    { timeout: 15_000 }
  ).toBe(false);

  const vrCh = page.locator(
    '#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="PLTG1 VR"]'
  );
  await vrCh.click();
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 10_000 });

  const axisLabels = await page.locator(".ww-chart .plotly .xaxislayer-above text").allTextContents();
  const hasAbsoluteDate = axisLabels.some(
    (t) => /20\d\d-\d\d-\d\d/.test(t) || /\d{2}:\d{2}:\d{2}/.test(t)
  );
  expect(hasAbsoluteDate, `Axis labels look absolute: ${JSON.stringify(axisLabels)}`).toBe(false);

  expect(errors, `Console errors on time-axis check:\n${errors.join("\n")}`).toEqual([]);
});
