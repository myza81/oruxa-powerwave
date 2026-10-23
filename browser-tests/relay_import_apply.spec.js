// Slice 9 / 10 -- Apply Settings: the reviewed P441 sample is copied into the Distance Protection
// analysis (its complete zone collection) and the normal R-X rendering path draws it. Runs against
// LOCAL code. Extra/dynamic zones are covered by distance_dynamic_zones.spec.js.
//
// * Apply Settings exists only while the backend-derived readiness is "Ready to apply".
// * The values land in the same inputs/state manual entry uses; Zone 4 (defeated) and the
//   disabled Zone P are not applied and not drawn.
// * A left reach of 0.00 Ω draws a boundary through R = 0.
// * Later manual edits behave normally; Apply again overwrites them; a failed Apply changes nothing.
// * Applied settings are page state only: a reload starts clean.

const { test, expect } = require("./support/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const LEFT = "Left Resistive Reach (−R)";
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const polygon = (page, n) => page.locator(`#wwDistanceSvg polygon.ww-dist-zone-boundary--zone${n}`);
const points = (page, n) =>
  polygon(page, n).evaluate((el) => el.getAttribute("points").split(" ").map((p) => p.split(",").map(Number)));

async function review(page) {
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

async function makeReady(page) {
  for (const n of ["1", "2", "3"]) {
    await panel(page).locator(`button[aria-label="Use 0.00 Ω for Zone ${n} ${LEFT}"]`).click();
  }
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
}

async function applied(page) {
  await review(page);
  await makeReady(page);
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
}

const formSnapshot = (page) =>
  page.evaluate(() => {
    const ids = [...document.querySelectorAll("#wwDistancePanel input[id^='wwDistanceZone'], #wwDistanceCharacteristicSelect")];
    return ids.map((el) => [el.id, el.type === "checkbox" ? el.checked : el.value]);
  });

test("Apply Settings appears only when the backend says Ready to apply", async ({ page }) => {
  await review(page);
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
  for (const n of ["1", "2", "3"]) {
    await panel(page).locator(`button[aria-label="Use 0.00 Ω for Zone ${n} ${LEFT}"]`).click();
  }
  await expect(readiness(page)).toContainText("Ready after confirmation");
  await expect(applyBtn(page)).toHaveCount(0);
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
  await expect(applyBtn(page)).toBeVisible();
  // Undoing a confirmation withdraws readiness, and the button with it.
  await page.locator("#wwRelayReviewUndoAll").click();
  await expect(readiness(page)).not.toHaveAttribute("data-readiness", "ready");
  await expect(applyBtn(page)).toHaveCount(0);
  // Nothing was applied to the form by any of this.
  await expect(page.locator("#wwDistanceZone1Enabled")).not.toBeChecked();
});

test("Apply populates Zones 1-3, keeps Zone 4 and Zone P out, and redraws the R-X plane", async ({ page }) => {
  await review(page);
  await makeReady(page);
  await expect(polygon(page, 1)).toHaveCount(0);
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");
  for (const n of [1, 2, 3]) {
    await expect(page.locator(`#wwDistanceZone${n}Enabled`)).toBeChecked();
    // Reach (Ω), Right (+R, Ω), Left (−R, Ω) and the reach angle (°) are four distinct inputs.
    expect(parseFloat(await input(page, n, "ReactiveReach").inputValue())).toBeGreaterThan(0);
    expect(parseFloat(await input(page, n, "ResistiveForward").inputValue())).toBeGreaterThan(0);
    await expect(input(page, n, "ResistiveReverse")).toHaveValue("0");
    expect(parseFloat(await input(page, n, "Angle").inputValue())).toBeGreaterThan(0);
    await expect(polygon(page, n)).toHaveCount(1); // drawn without any further click
  }
  await expect(input(page, 2, "Delay")).toHaveValue("0.3");
  await expect(input(page, 3, "Delay")).toHaveValue("3");
  // The defeated Zone 4 (the Reverse Zone slot) and the disabled Zone P are not applied or drawn.
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();
  await expect(polygon(page, 4)).toHaveCount(0);
  await expect(page.locator("#wwDistanceSvg polygon.ww-dist-zone-boundary")).toHaveCount(3);
  // the disabled Zone P is preserved by the backend but gets no card: the form keeps its four standard cards
  await expect(page.locator("#wwDistancePanel .ww-dist-zone-card")).toHaveCount(4);
  await expect(page.locator("#wwDistancePanel [data-zone-dynamic]")).toHaveCount(0);
  await expect(input(page, 4, "ResistiveReverse")).toHaveValue("");
});

test("an applied 0 Ω left reach draws the left boundary through the origin", async ({ page }) => {
  await applied(page);
  const pts = await points(page, 1);
  expect(pts).toHaveLength(4);
  // Corner 0 is (r' = -left, x' = 0): with left = 0 it is the origin itself.
  expect(Math.abs(pts[0][0])).toBeLessThan(0.01);
  expect(Math.abs(pts[0][1])).toBeLessThan(0.01);
});

test("applied settings and the same values typed by hand give the same R-X geometry", async ({ page }) => {
  await applied(page);
  const values = {};
  for (const n of [1, 2, 3]) {
    values[n] = {};
    for (const id of ["ReactiveReach", "ResistiveForward", "ResistiveReverse", "Angle", "Delay"]) {
      values[n][id] = await input(page, n, id).inputValue();
    }
  }
  const imported = [await points(page, 1), await points(page, 2), await points(page, 3)];

  await openDistance(page); // a fresh page: nothing imported
  await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
  for (const n of [1, 2, 3]) {
    await page.locator(`#wwDistanceZone${n}Enabled`).check();
    for (const [id, value] of Object.entries(values[n])) {
      await input(page, n, id).fill(value);
      await input(page, n, id).dispatchEvent("change");
    }
  }
  const manual = [await points(page, 1), await points(page, 2), await points(page, 3)];
  expect(manual).toEqual(imported);
});

test("editing after Apply behaves normally; Apply again overwrites those edits", async ({ page }) => {
  await applied(page);
  const original = await points(page, 1);
  const originalReach = await input(page, 1, "ReactiveReach").inputValue();
  await input(page, 1, "ReactiveReach").fill("0.5");
  await input(page, 1, "ReactiveReach").dispatchEvent("change");
  expect(await points(page, 1)).not.toEqual(original);
  await expect(input(page, 1, "ReactiveReach")).not.toHaveAttribute("readonly", /.*/);
  // The review keeps its state and is not changed by the manual edit.
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
  await applyBtn(page).click();
  await expect(input(page, 1, "ReactiveReach")).toHaveValue(originalReach);
  expect(await points(page, 1)).toEqual(original);
});

test("a failed Apply leaves the form and the R-X plot exactly as they were", async ({ page }) => {
  await applied(page);
  await input(page, 2, "ReactiveReach").fill("1.25");
  await input(page, 2, "ReactiveReach").dispatchEvent("change");
  const before = await formSnapshot(page);
  const plot = [await points(page, 1), await points(page, 2), await points(page, 3)];
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "apply_not_ready", message: "The relay settings are not ready to apply. Resolve the blocking settings in the review first." } }),
    }),
  );
  await applyBtn(page).click();
  const status = page.locator("#wwRelayReviewApplyStatus");
  await expect(status).toContainText("not ready to apply");
  await expect(status).toContainText("Nothing was changed.");
  await expect(status).toHaveAttribute("data-kind", "error");
  expect(await formSnapshot(page)).toEqual(before);
  expect([await points(page, 1), await points(page, 2), await points(page, 3)]).toEqual(plot);
});

test("a malformed apply payload is rejected whole and changes nothing", async ({ page }) => {
  await applied(page);
  const before = await formSnapshot(page);
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ characteristic: "quadrilateral", impedance_basis: "secondary", zones: [{ id: "Z1", display_name: "Zone 1", enabled: true, direction: "forward", reactive_reach_ohm: "x" }] }),
    }),
  );
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveAttribute("data-kind", "error");
  expect(await formSnapshot(page)).toEqual(before);
});

test("applied settings are page state only: a reload starts clean", async ({ page }) => {
  await applied(page);
  await expect(page.locator("#wwDistanceZone1Enabled")).toBeChecked();
  await page.reload();
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistanceZone1Enabled")).not.toBeChecked();
  await expect(input(page, 1, "ReactiveReach")).toHaveValue("");
  await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);
  // The app keeps unrelated UI preferences; nothing about the import or the applied settings.
  const keys = await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)]);
  expect(keys.filter((k) => /relay|distance|apply|zone/i.test(k))).toEqual([]);
});
