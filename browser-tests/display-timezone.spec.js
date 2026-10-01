// DEC-122: engineering timestamps display in ONE display timezone
// (Asia/Kuala_Lumpur) whatever their format or source timezone.
//
// Fixture pair (backend/tests/ben/make_fixtures.py): a synthetic BEN
// record (stored UTC, start 2024-03-05 06:07:08.023456Z) and its
// BEN32-style COMTRADE export (stored naive local, 14:07:08.023456) --
// the same recording, so both must read 14:07:08.023456 and share one
// Time Group at 0.0 s.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "ben");
const LOCAL_START = "2024-03-05 14:07:08.023456";

function trackErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

// Each source's channels sit in its own native <details> in the sidebar;
// only the first-opened one starts expanded.
async function showChannel(page, sourceId, channelName) {
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sourceId}"]`);
  if (!(await details.evaluate((el) => el.open))) await details.locator("summary").first().click();
  const row = page.locator(
    `#channelGroups tr.channel-row--toggle[data-source-id="${sourceId}"][data-channel-name="${channelName}"]`
  );
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

async function upload(page, format, files) {
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption(format);
  for (let i = 0; i < files.length; i++) {
    await page.locator(`#uploadModalFile_${i}`).setInputFiles(path.join(FIXTURES, files[i]));
  }
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

test("display helper converts canonical instants to the display timezone", async ({ page }) => {
  await page.goto("/index.html");
  const results = await page.evaluate(() => ({
    zone: wwDisplayTimezone(),
    lgngBen: wwFormatEngineeringTimestamp("2026-01-16T05:54:22.729783Z"),
    alreadyLocal: wwFormatEngineeringTimestamp("2026-01-16T13:54:22.729783+08:00"),
    pmjyBen: wwFormatEngineeringTimestamp("2022-07-27T04:41:29.926317Z"),
    wholeSecond: wwFormatEngineeringTimestamp("2026-03-06T02:00:00Z"),
    rollover: wwFormatEngineeringTimestamp("2026-12-31T16:00:00.000001Z"),
    otherOffset: wwFormatEngineeringTimestamp("2026-01-16T00:30:00.5-05:30"),
    naive: wwFormatEngineeringTimestamp("2026-01-16T13:54:22.729783"),
  }));
  expect(results).toEqual({
    zone: "Asia/Kuala_Lumpur",
    lgngBen: "2026-01-16 13:54:22.729783",
    alreadyLocal: "2026-01-16 13:54:22.729783", // no double conversion
    pmjyBen: "2022-07-27 12:41:29.926317",
    wholeSecond: "2026-03-06 10:00:00",
    rollover: "2027-01-01 00:00:00.000001",
    otherOffset: "2026-01-16 14:00:00.5",
    naive: null, // never guesses a source timezone in the browser
  });
});

test("a BEN record and its BEN32 COMTRADE export show the same local time", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/index.html");
  await upload(page, "comtrade", ["synthetic_fast_export.cfg", "synthetic_fast_export.dat"]);
  await upload(page, "ben", ["synthetic_fast.ben"]);

  // ---- Recording Events: identical Start Time, no UTC "Z" ----
  const rows = page.locator("#recordingsTableBody tr[data-source-id]");
  await expect(rows).toHaveCount(2);
  const cells = page.locator("#recordingsTableBody tr[data-source-id] .recording-start-time-cell");
  await expect(cells.nth(0)).toHaveText(LOCAL_START);
  await expect(cells.nth(1)).toHaveText(LOCAL_START);
  await expect(cells.nth(1)).not.toContainText("Z");
  await expect(cells.nth(0)).toHaveAttribute("title", "Shown in Asia/Kuala_Lumpur");
  await expect(rows.nth(0)).toContainText("COMTRADE");
  await expect(rows.nth(1)).toContainText("BEN");
  const comtradeId = await rows.nth(0).getAttribute("data-source-id");
  const benId = await rows.nth(1).getAttribute("data-source-id");

  // ---- Canonical placement is unchanged: 0.0 s for both ----
  const placements = await page.evaluate(async () => {
    const resp = await fetch(apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/synchronization/sources");
    return (await resp.json()).map((row) => row.timestamp_placement_offset_s);
  });
  expect(placements).toEqual([0, 0]);

  // ---- One Time Group, labelled in the display timezone ----
  await rows.nth(1).click(); // open the BEN recording
  await expect.poll(() => page.evaluate(() => document.getElementById("workspaceRow").hidden)).toBe(false);
  await showChannel(page, benId, "LINE1 VR");
  await showChannel(page, comtradeId, "LINE1 VR");

  const canvases = page.locator("#wwTimeGroupCanvases .ww-time-group-canvas");
  await expect(canvases).toHaveCount(1);
  const meta = canvases.first().locator(".ww-tg-header-meta");
  await expect(meta).toContainText("05 Mar 2024 · 14:07:08");
  await expect(meta).toContainText("2 sources");
  await expect(meta).not.toContainText("06:07:08");

  // The ruler's Absolute labels are display-timezone clock times.
  const ruler = canvases.first().locator(".ww-tg-ruler");
  await expect(ruler).toBeVisible();
  await expect(ruler).toContainText("14:07:08");
  await expect(ruler).not.toContainText("06:07:08");

  expect(errors, `Unexpected console/page errors:\n${errors.join("\n")}`).toEqual([]);
});
