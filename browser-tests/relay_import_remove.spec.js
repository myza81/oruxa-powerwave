// Removing a relay import releases what it applied. An applied import owns the Distance Protection
// configuration it wrote (characteristic, output basis, zone collection); Remove returns that
// configuration to the defaults so no imported zone card, extra zone or R-X boundary outlives the
// import. Runs against LOCAL code.
//
// * Remove after Apply: import card, imported zone values, extra zones and boundaries all go.
// * Remove before Apply: the user's own (manual) Distance Protection settings are untouched.
// * Remove after a hand edit of the applied settings: the edited configuration is the user's and is kept.
// * A -> Apply -> Remove -> B -> Apply: B is exactly what applying B on a clean page gives.
// * An Apply answer arriving after Remove applies nothing.
// * A new upload, once ACCEPTED, releases the previous import's unedited state the same way; an
//   edited configuration is kept, and a failed upload changes nothing.

const { test, expect } = require("./support/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const applyStatus = (page) => page.locator("#wwRelayReviewApplyStatus");
const removeBtn = (page) => page.locator("#wwRelayImportRemoveBtn");
const LEFT = "Left Resistive Reach (−R)";
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const cards = (page) => page.locator("#wwDistancePanel .ww-dist-zone-card");
const extraCards = (page) => page.locator("#wwDistancePanel [data-zone-dynamic]");
const boundaries = (page) => page.locator("#wwDistanceSvg .ww-dist-zone-boundary");
const legendItems = (page) => page.locator("#wwDistanceZoneLegend .ww-dist-zone-legend-item");

const formSnapshot = (page) =>
  page.evaluate(() => {
    const els = [...document.querySelectorAll(
      "#wwDistancePanel input[id^='wwDistanceZone'], #wwDistanceCharacteristicSelect, #wwDistanceOutputBasisSelect",
    )];
    return els.map((el) => [el.id, el.type === "checkbox" ? el.checked : el.value]);
  });
const plotSnapshot = (page) =>
  page.evaluate(() => [...document.querySelectorAll("#wwDistanceSvg .ww-dist-zone-boundary")].map((el) => [
    el.getAttribute("data-zone-key"), el.getAttribute("points") || el.getAttribute("d") || el.getAttribute("r"),
  ]));

// Upload `pdf`, open the review and make it Ready to apply (the P441 sample's three Left reaches
// take the explicit 0.00 Ω suggestion, then every assumption is confirmed).
async function reviewReady(page, pdf = relaySheet("p441", { variant: "minimal" })) {
  await pick(page, "document.pdf", pdf);
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
  for (const n of ["1", "2", "3"]) {
    await panel(page).locator(`button[aria-label="Use 0.00 Ω for Zone ${n} ${LEFT}"]`).click();
  }
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
}
async function apply(page) {
  await applyBtn(page).click();
  await expect(applyStatus(page)).toHaveText("Relay settings applied to Distance Protection analysis.");
}

// The page's own clean starting configuration, as a fresh page shows it.
async function cleanSnapshot(page) {
  await openDistance(page);
  return { form: await formSnapshot(page), plot: await plotSnapshot(page) };
}

// A controlled apply payload with an enabled extra zone (shaped exactly like ApplySettingsOut).
const quad = (id, name, o = {}) => ({
  id, display_name: name, enabled: true, direction: "forward", delay_s: 0.5, characteristic_angle_deg: 80,
  reach_ohm: null, reactive_reach_ohm: 10, resistive_reach_forward_ohm: 6, resistive_reach_reverse_ohm: 2, ...o,
});
const withExtraZone = {
  characteristic: "quadrilateral", impedance_basis: "primary",
  zones: [
    quad("Z1", "Zone 1", { reactive_reach_ohm: 4, resistive_reach_forward_ohm: 3, delay_s: 0 }),
    quad("Z2", "Zone 2", { reactive_reach_ohm: 7, resistive_reach_forward_ohm: 5, delay_s: 0.3 }),
    quad("Z3", "Zone 3", { reactive_reach_ohm: 12, resistive_reach_forward_ohm: 8, delay_s: 3 }),
    quad("ZP", "Zone P", { reactive_reach_ohm: 15, resistive_reach_forward_ohm: 9 }),
  ],
};

test("Remove after Apply clears the import and everything it applied", async ({ page }) => {
  const clean = await cleanSnapshot(page);
  await reviewReady(page);
  await apply(page);
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");
  await expect(page.locator("#wwDistanceZone1Enabled")).toBeChecked();
  await expect(boundaries(page)).toHaveCount(3);

  await removeBtn(page).click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(panel(page)).toBeHidden();
  await expect(applyBtn(page)).toHaveCount(0);
  // The Distance Protection configuration is exactly the clean, nothing-applied one.
  for (const n of [1, 2, 3]) {
    await expect(page.locator(`#wwDistanceZone${n}Enabled`)).not.toBeChecked();
    await expect(input(page, n, "ReactiveReach")).toHaveValue("");
    await expect(input(page, n, "ResistiveForward")).toHaveValue("");
    await expect(input(page, n, "ResistiveReverse")).toHaveValue("");
  }
  await expect(boundaries(page)).toHaveCount(0);
  await expect(legendItems(page)).toHaveCount(0);
  expect(await formSnapshot(page)).toEqual(clean.form);
  expect(await plotSnapshot(page)).toEqual(clean.plot);
});

test("Remove after Apply drops the imported extra zones, their cards, boundaries and legend entries", async ({ page }) => {
  await openDistance(page);
  await reviewReady(page);
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(withExtraZone) }),
  );
  await apply(page);
  await expect(extraCards(page)).toHaveCount(1);
  await expect(boundaries(page)).toHaveCount(4);
  await expect(legendItems(page)).toHaveCount(4);
  await expect(page.locator("#wwDistanceOutputBasisSelect")).toHaveValue("primary");

  await removeBtn(page).click();
  await expect(extraCards(page)).toHaveCount(0);
  await expect(cards(page)).toHaveCount(4);
  await expect(boundaries(page)).toHaveCount(0);
  await expect(legendItems(page)).toHaveCount(0);
  await expect(page.locator("#wwDistanceZoneStateList")).not.toContainText("Zone P");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("mho");
  await expect(page.locator("#wwDistanceOutputBasisSelect")).toHaveValue("secondary");
});

test("Remove before Apply leaves the user's own Distance Protection settings untouched", async ({ page }) => {
  await openDistance(page);
  await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
  await page.locator("#wwDistanceZone1Enabled").check();
  for (const [id, value] of [["ReactiveReach", "4"], ["ResistiveForward", "3"], ["ResistiveReverse", "1"], ["Angle", "80"]]) {
    await input(page, 1, id).fill(value);
    await input(page, 1, id).dispatchEvent("change");
  }
  await expect(boundaries(page)).toHaveCount(1);
  const form = await formSnapshot(page);
  const plot = await plotSnapshot(page);

  await reviewReady(page); // reviewed, never applied
  await removeBtn(page).click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  expect(await formSnapshot(page)).toEqual(form);
  expect(await plotSnapshot(page)).toEqual(plot);
});

test("Remove after a hand edit of the applied settings keeps the edited configuration", async ({ page }) => {
  await openDistance(page);
  await reviewReady(page);
  await apply(page);
  await input(page, 1, "ReactiveReach").fill("0.5");
  await input(page, 1, "ReactiveReach").dispatchEvent("change");
  const form = await formSnapshot(page);
  const plot = await plotSnapshot(page);

  await removeBtn(page).click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  // The configuration became the user's work with the edit: it is not erased.
  expect(await formSnapshot(page)).toEqual(form);
  expect(await plotSnapshot(page)).toEqual(plot);
  await expect(input(page, 1, "ReactiveReach")).toHaveValue("0.5");
});

test("A -> Apply -> Remove -> B -> Apply shows B exactly as on a clean page, with nothing left of A", async ({ page }) => {
  // B on a clean page: the reference.
  await openDistance(page);
  await reviewReady(page);
  await apply(page);
  const bForm = await formSnapshot(page);
  const bPlot = await plotSnapshot(page);

  // A: a different configuration, with an extra zone and another basis.
  await openDistance(page);
  await reviewReady(page);
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(withExtraZone) }),
  );
  await apply(page);
  await expect(extraCards(page)).toHaveCount(1);
  await removeBtn(page).click();
  await page.unroute("**/api/v1/relay-import/review/apply");

  // B, after A was applied and removed.
  await reviewReady(page);
  await apply(page);
  await expect(extraCards(page)).toHaveCount(0);
  await expect(legendItems(page)).toHaveCount(3);
  await expect(page.locator("#wwDistanceZoneStateList")).not.toContainText("Zone P");
  expect(await formSnapshot(page)).toEqual(bForm);
  expect(await plotSnapshot(page)).toEqual(bPlot);
});

// ---- a new accepted upload supersedes the previous import -----------------------------------

test("A Apply -> B accepted clears A's unedited state and shows B's review", async ({ page }) => {
  const clean = await cleanSnapshot(page);
  await reviewReady(page);
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(withExtraZone) }),
  );
  await apply(page);
  await expect(extraCards(page)).toHaveCount(1);
  await expect(boundaries(page)).toHaveCount(4);

  await pick(page, "b.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportFilename")).toHaveText("b.pdf");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await expect(extraCards(page)).toHaveCount(0);
  await expect(boundaries(page)).toHaveCount(0);
  await expect(legendItems(page)).toHaveCount(0);
  expect(await formSnapshot(page)).toEqual(clean.form);
  // B's own review is there, not applied.
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
  await expect(applyBtn(page)).toHaveCount(0);
  // Removing B afterwards has nothing left to clear and changes nothing.
  await removeBtn(page).click();
  expect(await formSnapshot(page)).toEqual(clean.form);
});

test("A Apply -> hand edit -> B accepted keeps the edited configuration", async ({ page }) => {
  await openDistance(page);
  await reviewReady(page);
  await apply(page);
  await input(page, 1, "ReactiveReach").fill("0.5");
  await input(page, 1, "ReactiveReach").dispatchEvent("change");
  const form = await formSnapshot(page);
  const plot = await plotSnapshot(page);

  await pick(page, "b.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  expect(await formSnapshot(page)).toEqual(form);
  expect(await plotSnapshot(page)).toEqual(plot);
  await expect(input(page, 1, "ReactiveReach")).toHaveValue("0.5");
});

test("A Apply -> B upload fails keeps A's state; a later accepted upload still releases it", async ({ page }) => {
  const clean = await cleanSnapshot(page);
  await reviewReady(page);
  await apply(page);
  const form = await formSnapshot(page);
  const plot = await plotSnapshot(page);

  // A server-side failure ...
  await page.route("**/api/v1/relay-import/upload", (route) =>
    route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: { code: "unreadable_pdf", message: "The PDF could not be read." } }) }),
  );
  await pick(page, "broken.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportError")).toHaveText("The PDF could not be read.");
  expect(await formSnapshot(page)).toEqual(form);
  expect(await plotSnapshot(page)).toEqual(plot);
  // ... and a file the browser refuses before uploading change nothing.
  await pick(page, "notes.txt", Buffer.from("not a pdf"));
  await expect(page.locator("#wwRelayImportError")).toContainText("Only PDF");
  expect(await formSnapshot(page)).toEqual(form);
  expect(await plotSnapshot(page)).toEqual(plot);

  // A's applied state is still A's: the next ACCEPTED upload releases it.
  await page.unroute("**/api/v1/relay-import/upload");
  await pick(page, "c.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  expect(await formSnapshot(page)).toEqual(clean.form);
  await expect(boundaries(page)).toHaveCount(0);
});

test("an Apply answer that arrives after Remove applies nothing", async ({ page }) => {
  const clean = await cleanSnapshot(page);
  await reviewReady(page);
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  await page.route("**/api/v1/relay-import/review/apply", async (route) => {
    await held;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(withExtraZone) });
  });
  const answered = page.waitForResponse("**/api/v1/relay-import/review/apply");
  await applyBtn(page).click();
  await removeBtn(page).click();
  release();
  await answered;
  await page.evaluate(() => new Promise((r) => setTimeout(r, 50))); // let the late answer be handled
  expect(await formSnapshot(page)).toEqual(clean.form);
  await expect(boundaries(page)).toHaveCount(0);
  await expect(extraCards(page)).toHaveCount(0);
});
