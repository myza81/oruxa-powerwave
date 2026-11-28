// UAT-B-02 regression: Recording Browser search input must render as a
// full-width usable field, not a narrow collapsed rectangle.
//
// Root cause: global input[type="search"] { flex:1 } fought the flex
// layout when search and sort shared one row; the two-row toolbar fix
// uses width:100%;display:block on .ww-rd-search so the global rule
// cannot collapse it.
//
// Verified dimensions: 1366 × 768, light and dark themes.

const { test, expect } = require("./support/test");
const path = require("path");

const SCREENSHOTS = path.join(__dirname, "..", "docs", "project-memory", "evidence", "recording-details-toolbar");

test.use({ viewport: { width: 1366, height: 768 } });

test("Recording Details toolbar: search input is full-width, not collapsed", async ({ page }) => {
  await page.goto("/index.html");

  // Navigate to Recording Details page via the sidebar nav button.
  await page.locator("#mainNavRecordingDetailsBtn").click();

  // Panel must be visible.
  await expect(page.locator("#pageRecordingDetails")).toBeVisible();

  // The toolbar elements must exist.
  const searchInput = page.locator("#wwRdSearch");
  const sortSelect = page.locator("#wwRdSort");
  await expect(searchInput).toBeVisible();
  await expect(sortSelect).toBeVisible();

  // Measure rendered bounding boxes.
  const searchBox = await searchInput.boundingBox();
  const sortBox = await sortSelect.boundingBox();

  // Search input must be wider than 100 px (collapsed state was ~40–60 px).
  expect(searchBox.width).toBeGreaterThan(100);

  // Search input must occupy most of the browser panel width (~260 px).
  // Allow ≥180 px to stay robust across minor padding differences.
  expect(searchBox.width).toBeGreaterThan(180);

  // Sort select must be below the search input (two-row layout: search Y < sort Y).
  expect(sortBox.y).toBeGreaterThan(searchBox.y);

  // The two elements must NOT share the same Y-baseline (would indicate one-row layout).
  expect(sortBox.y).not.toBeCloseTo(searchBox.y, 0);

  // Light-theme screenshot for UAT evidence.
  const fs = require("fs");
  fs.mkdirSync(SCREENSHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SCREENSHOTS, "toolbar-light.png"), fullPage: false });
});

test("Recording Details toolbar: search input is full-width in dark theme", async ({ page }) => {
  // Force dark theme via the data-theme attribute (matches app's theme toggle).
  await page.goto("/index.html");
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));

  await page.locator("#mainNavRecordingDetailsBtn").click();
  await expect(page.locator("#pageRecordingDetails")).toBeVisible();

  const searchInput = page.locator("#wwRdSearch");
  const sortSelect = page.locator("#wwRdSort");
  await expect(searchInput).toBeVisible();
  await expect(sortSelect).toBeVisible();

  const searchBox = await searchInput.boundingBox();
  const sortBox = await sortSelect.boundingBox();

  expect(searchBox.width).toBeGreaterThan(180);
  expect(sortBox.y).toBeGreaterThan(searchBox.y);

  const fs = require("fs");
  const { mkdirSync } = fs;
  mkdirSync(SCREENSHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SCREENSHOTS, "toolbar-dark.png"), fullPage: false });
});
