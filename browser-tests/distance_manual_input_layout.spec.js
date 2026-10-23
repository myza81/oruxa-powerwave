// Distance Protection -- Manual Input card layout polish (UI only).
// * every magnitude input shares a row with its unit selector;
// * VT / CT / angle inputs use the same control style as the settings grid;
// * no horizontal overflow, wide or narrow. Runs against LOCAL code.

const { test, expect } = require("./support/test");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";

test.beforeEach(async ({ page }) => {
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${BACKEND_PORT}", environment: "development", buildVersion: "local" };`,
    }),
  );
});

async function openDistance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
  await expect(page.locator("#wwDistanceManualInputSection")).toBeVisible();
}

const KEYS = ["V1", "V2", "I1", "I2"];

test("value and unit share one row for every voltage and current magnitude", async ({ page }) => {
  await openDistance(page);
  for (const k of KEYS) {
    const input = page.locator(`#wwDistanceManual${k}MagnitudeInput`);
    const unit = page.locator(`#wwDistanceManual${k}UnitSelect`);
    await expect(input.locator("xpath=..")).toHaveClass(/ww-oc-manual-input-row/);
    const [a, b] = [await input.boundingBox(), await unit.boundingBox()];
    expect(Math.abs(a.y - b.y), `${k} top`).toBeLessThan(2);
    expect(Math.abs(a.height - b.height), `${k} height`).toBeLessThan(2);
    expect(a.width, `${k} value stays dominant`).toBeGreaterThan(b.width);
  }
});

test("VT / CT / magnitude / angle controls share one control style", async ({ page }) => {
  await openDistance(page);
  const style = (sel, withHeight = true) =>
    page.locator(sel).evaluate((el, h) => {
      const c = getComputedStyle(el);
      return [h ? c.height : "", c.borderTopLeftRadius, c.borderTopColor, c.paddingTop, c.paddingLeft, c.fontSize].join("|");
    }, withHeight);
  const reference = await style("#wwDistanceManualV1MagnitudeInput");
  const ids = [
    "ManualVtPrimaryInput", "ManualVtSecondaryInput", "ManualCtPrimaryInput", "ManualCtSecondaryInput",
    "ManualV1AngleInput", "ManualV2AngleInput", "ManualI1AngleInput", "ManualI2AngleInput",
    "ManualV2MagnitudeInput", "ManualI1MagnitudeInput", "ManualI2MagnitudeInput",
    "ManualV1UnitSelect", "ManualVoltageBasisSelect", "ManualCurrentBasisSelect",
  ];
  for (const id of ids) expect(await style(`#wwDistance${id}`), id).toBe(reference);
  // and matches the settings-grid controls above it (radius, border, padding, font)
  expect(await style("#wwDistanceLoopSelect", false)).toBe(await style("#wwDistanceManualV1MagnitudeInput", false));
});

for (const width of [1280, 420, 320]) {
  test(`no horizontal overflow in the Manual Input card at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openDistance(page);
    const section = page.locator("#wwDistanceManualInputSection");
    const overflow = await section.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const bad = [...el.querySelectorAll("input, select, label")].filter((c) => {
        const r = c.getBoundingClientRect();
        return r.width > 0 && (r.right > box.right + 1 || r.left < box.left - 1);
      }).map((c) => c.id || c.tagName);
      return { scroll: el.scrollWidth - el.clientWidth, bad };
    });
    expect(overflow.scroll).toBeLessThanOrEqual(1);
    expect(overflow.bad).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    // the value and unit remain side by side even when narrow
    const a = await page.locator("#wwDistanceManualV1MagnitudeInput").boundingBox();
    const b = await page.locator("#wwDistanceManualV1UnitSelect").boundingBox();
    expect(Math.abs(a.y - b.y)).toBeLessThan(2);
  });
}
