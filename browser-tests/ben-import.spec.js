// BEN import smoke (DEC-120): a .ben record goes through the existing
// Upload Recording modal and reaches the normal post-import workflow --
// Recordings row, Waveform page, a rendered trace -- with no BEN-specific
// screen. Fixtures are synthetic (backend/tests/ben/make_fixtures.py).

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "ben");

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
  await expect(page.locator("#uploadModalFile_1")).toHaveCount(0);
}

async function uploadBen(page, file) {
  await openBenUpload(page);
  await page.locator("#uploadModalFile_0").setInputFiles(file);
  await page.locator("#uploadModalSubmitBtn").click();
}

test("Fast BEN uploads and opens like any recording", async ({ page }) => {
  const errors = trackErrors(page);
  await uploadBen(page, path.join(FIXTURES, "synthetic_fast.ben"));
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("BEN");
  await expect(row).toContainText("SYNTH BEN FAST");

  await row.click();
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);
  const analog = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="LINE1 VR"]');
  await expect(analog).toBeVisible();
  await analog.click();
  await expect(analog).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
  await expect(page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="digital"]')).not.toHaveCount(0);

  expect(errors, `Unexpected console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

test("Slow BEN imports frequency/power channels, unavailable samples included", async ({ page }) => {
  const errors = trackErrors(page);
  await uploadBen(page, path.join(FIXTURES, "synthetic_slow.ben"));
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

  const row = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(row).toContainText("SYNTH BEN SLOW");
  await row.click();
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);

  for (const name of ["POWER LINE1", "FREQ LINE1 VR", "FREQ LINE2 VY"]) {
    await expect(
      page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`)
    ).toBeVisible();
  }
  // Partly unavailable (leading NaN) frequency renders a trace.
  const freq = page.locator('#channelGroups tr.channel-row--toggle[data-channel-name="FREQ LINE1 VR"]');
  await freq.click();
  await expect(freq).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible();
  // A never-available channel can be displayed without errors.
  const never = page.locator('#channelGroups tr.channel-row--toggle[data-channel-name="FREQ LINE2 VY"]');
  await never.click();
  await expect(never).toHaveAttribute("aria-pressed", "true");

  expect(errors, `Unexpected console/page errors:\n${errors.join("\n")}`).toEqual([]);
});

test("unsupported BEN layout and non-BEN .ben files show the import error", async ({ page }) => {
  const legacy = Buffer.from(fs.readFileSync(path.join(FIXTURES, "synthetic_fast.ben")));
  legacy[4] = 0x28; // the older BEN layout discriminator (BPHE/GPTH)
  await uploadBen(page, { name: "legacy.ben", mimeType: "application/octet-stream", buffer: legacy });
  await expect(page.locator("#uploadModalStatus")).toContainText("BEN layout that is not currently supported");
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();

  await page.locator("#uploadModalFile_0").setInputFiles({
    name: "renamed.ben",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("1,STATION,1999\n2,1A,1D\n".repeat(20)),
  });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalStatus")).toContainText("not a recognized BEN record");
  await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(0);
});
