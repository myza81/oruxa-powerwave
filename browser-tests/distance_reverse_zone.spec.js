// Distance Protection -- the fourth manual slot, the Reverse Zone. Real-
// browser coverage of: the zone card, backend evaluation of a reverse-
// direction zone in Manual mode, the drawn geometry (the forward
// characteristic rotated 180 degrees about the origin), and Fit Zones.
// A reverse-direction zone is NOT the quadrilateral's "Resistive reach
// reverse" field; both appear on the same card here and are kept apart.
//
// Manual mode needs no recording. Golden loop: Zab = 10 /_ 20 deg with the
// currents as entered; adding 180 deg to both currents reverses the
// current direction and gives Zab = 10 /_ 200 deg (third quadrant).
//
// frontend/config.js pins the API to :8000; PW_BACKEND_PORT re-points it
// per page (same approach as relay_import_upload.spec.js).

const { test, expect } = require("@playwright/test");

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

async function leg(page, key, magnitude, unit, angleDeg) {
  await page.locator(`#wwDistanceManual${key}UnitSelect`).selectOption(unit);
  await page.locator(`#wwDistanceManual${key}MagnitudeInput`).fill(String(magnitude));
  await page.locator(`#wwDistanceManual${key}MagnitudeInput`).dispatchEvent("change");
  await page.locator(`#wwDistanceManual${key}AngleInput`).fill(String(angleDeg));
  await page.locator(`#wwDistanceManual${key}AngleInput`).dispatchEvent("change");
}

async function enterLoop(page, currentOffsetDeg) {
  await page.locator("#wwDistanceManualVoltageBasisSelect").selectOption("secondary");
  await page.locator("#wwDistanceManualCurrentBasisSelect").selectOption("secondary");
  await leg(page, "V1", 100, "V", 0);
  await leg(page, "V2", 100, "V", -120);
  await leg(page, "I1", 10, "A", -20 + currentOffsetDeg);
  await leg(page, "I2", 10, "A", -140 + currentOffsetDeg);
}

async function setZone(page, n, { enabled = true, reach, angle = 20, delay }) {
  const part = `#wwDistanceZone${n}`;
  if (enabled) await page.locator(`${part}Enabled`).check();
  else await page.locator(`${part}Enabled`).uncheck();
  if (reach !== undefined) {
    await page.locator(`${part}ReachInput`).fill(String(reach));
    await page.locator(`${part}ReachInput`).dispatchEvent("change");
  }
  await page.locator(`${part}AngleInput`).fill(String(angle));
  await page.locator(`${part}AngleInput`).dispatchEvent("change");
  if (delay !== undefined) {
    await page.locator(`${part}DelayInput`).fill(String(delay));
    await page.locator(`${part}DelayInput`).dispatchEvent("change");
  }
}

const zoneRow = (page, label) => page.locator("#wwDistanceZoneStateList .ww-oc-value-row", { hasText: label });

test("the Reverse Zone card is the fourth zone, clearly labelled, and disabled by default", async ({ page }) => {
  await openDistance(page);
  const cards = page.locator(".ww-dist-zone-card");
  await expect(cards).toHaveCount(4);
  await expect(cards.nth(3).locator(".ww-dist-zone-card-title")).toHaveText("Reverse Zone");
  await expect(page.locator("#wwDistanceZone4Direction")).toHaveText("Direction: Reverse");
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();
  for (const n of [1, 2, 3]) await expect(cards.nth(n - 1).locator(".ww-dist-zone-card-title")).toHaveText(`Zone ${n}`);
  await expect(zoneRow(page, "Reverse Zone")).toContainText("Not Operated");
  await expect(zoneRow(page, "Reverse Zone")).toContainText("(disabled)");
});

test("a reverse-direction impedance operates the Reverse Zone, and a forward one does not", async ({ page }) => {
  await openDistance(page);
  await setZone(page, 4, { reach: 15, angle: 20, delay: 0.7 });
  await setZone(page, 1, { reach: 15, angle: 20 });

  await enterLoop(page, 180); // Zab = 10 /_ 200 deg
  await expect(zoneRow(page, "Reverse Zone")).toContainText("Operated");
  await expect(zoneRow(page, "Reverse Zone")).not.toContainText("Not Operated");
  await expect(zoneRow(page, "Reverse Zone")).toContainText("delay 0.70s");
  await expect(zoneRow(page, "Zone 1")).toContainText("Not Operated");

  await enterLoop(page, 0); // Zab = 10 /_ 20 deg
  await expect(zoneRow(page, "Zone 1")).not.toContainText("Not Operated");
  await expect(zoneRow(page, "Reverse Zone")).toContainText("Not Operated");

  await page.locator("#wwDistanceZone4Enabled").uncheck();
  await enterLoop(page, 180);
  await expect(zoneRow(page, "Reverse Zone")).toContainText("(disabled)");
  await expect(zoneRow(page, "Reverse Zone")).toContainText("Not Operated");
});

test("the Reverse Mho circle is the forward circle rotated 180 degrees, and Fit Zones includes it", async ({ page }) => {
  await openDistance(page);
  await setZone(page, 1, { reach: 10, angle: 60 });
  await setZone(page, 4, { reach: 10, angle: 60 });
  const circle = async (n) =>
    page.locator(`#wwDistanceSvg circle.ww-dist-zone-boundary--zone${n}`).evaluate((el) => ({
      cx: parseFloat(el.getAttribute("cx")), cy: parseFloat(el.getAttribute("cy")), r: parseFloat(el.getAttribute("r")),
    }));
  const fwd = await circle(1);
  const rev = await circle(4);
  // Point reflection through the origin (default view is origin-centred).
  expect(rev.cx).toBeCloseTo(-fwd.cx, 1);
  expect(rev.cy).toBeCloseTo(-fwd.cy, 1);
  expect(rev.r).toBeCloseTo(fwd.r, 1);
  expect(fwd.cx).toBeGreaterThan(0); // forward reach 10 /_ 60 -> centre in the first quadrant
  expect(fwd.cy).toBeLessThan(0);    // (SVG y grows downward)

  // Fit Zones with only the reverse zone must frame its negative extent.
  await page.locator("#wwDistanceZone1Enabled").uncheck();
  await page.locator("#wwDistanceFitZonesBtn").click();
  const box = await page.evaluate(() => {
    const svg = document.getElementById("wwDistanceSvg");
    const c = svg.querySelector("circle.ww-dist-zone-boundary--zone4");
    const b = c.getBoundingClientRect();
    const s = svg.getBoundingClientRect();
    return { l: b.left - s.left, r: s.right - b.right, t: b.top - s.top, bt: s.bottom - b.bottom, w: b.width, h: b.height };
  });
  expect(Math.min(box.l, box.r, box.t, box.bt)).toBeGreaterThanOrEqual(-0.5); // fully inside the plot
  expect(Math.abs(box.w - box.h)).toBeLessThan(0.5); // 1:1 R/X scale (a circle stays a circle)
});

test("the Reverse Quadrilateral is the forward polygon rotated 180 degrees; resistive reach reverse stays a separate field", async ({ page }) => {
  await openDistance(page);
  await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
  const quad = async (n, { x, rf, rr, angle }) => {
    await page.locator(`#wwDistanceZone${n}Enabled`).check();
    for (const [id, value] of [["ReactiveReach", x], ["ResistiveForward", rf], ["ResistiveReverse", rr], ["Angle", angle]]) {
      await page.locator(`#wwDistanceZone${n}${id}Input`).fill(String(value));
      await page.locator(`#wwDistanceZone${n}${id}Input`).dispatchEvent("change");
    }
  };
  await quad(1, { x: 10, rf: 6, rr: 2, angle: 75 });
  await quad(4, { x: 10, rf: 6, rr: 2, angle: 75 });
  const points = async (n) =>
    page.locator(`#wwDistanceSvg polygon.ww-dist-zone-boundary--zone${n}`).evaluate((el) =>
      el.getAttribute("points").split(" ").map((p) => p.split(",").map(Number)),
    );
  const f = await points(1);
  const r = await points(4);
  expect(f).toHaveLength(4);
  for (let i = 0; i < 4; i++) {
    expect(r[i][0]).toBeCloseTo(-f[i][0], 1);
    expect(r[i][1]).toBeCloseTo(-f[i][1], 1);
  }
  // The reverse card still has its own quadrilateral 'Resistive reach reverse' input.
  await expect(page.locator("#wwDistanceZone4ResistiveReverseInput")).toBeVisible();
  await expect(page.locator("#wwDistanceZone4ResistiveReverseField")).toContainText("Resistive reach reverse");
});
