// DEC-198 foundation -- Relay Import Assistance for Non-Expert Users, in the browser.
//
// * Documented relay behaviour has its own chip (never "Mapped"), and the normal UI never shows internal terms.
// * A value the engine cannot represent reads "Not yet supported"; a missing source value "Source value missing".
// * Apply carries `approximations` (empty for every relay today); an approximate configuration says so in the
//   R-X legend, and the import's ownership rules (Remove / new import / hand edit) release it like the zones.
// * A payload with an unbounded approximation is refused and changes nothing.
// Runs against LOCAL code.

const { test, expect } = require("./support/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
});
test.afterEach(() => {
  expect(problems).toEqual([]);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const applyStatus = (page) => page.locator("#wwRelayReviewApplyStatus");
const removeBtn = (page) => page.locator("#wwRelayImportRemoveBtn");
const approxNote = (page) => page.locator('#wwDistanceZoneLegend [data-legend-note="approximate"]');
const boundaries = (page) => page.locator("#wwDistanceSvg .ww-dist-zone-boundary");
const LEFT = "Left Resistive Reach (−R)";

async function openReview(page, pdf) {
  await openDistance(page);
  await pick(page, "document.pdf", pdf);
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}
// The P441 sample made Ready to apply: the three Left reaches take the explicit 0.00 Ω suggestion,
// then every assumption is confirmed (the unchanged confirmation workflow).
async function p441Ready(page) {
  await openReview(page, relaySheet("p441", { variant: "minimal" }));
  for (const n of ["1", "2", "3"]) {
    await panel(page).locator(`button[aria-label="Use 0.00 Ω for Zone ${n} ${LEFT}"]`).click();
  }
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
}
const appliedApproximations = (page) => page.evaluate(() => wwDistanceState.appliedApproximations);

const quad = (id, name, o = {}) => ({
  id, display_name: name, enabled: true, direction: "forward", delay_s: 0, characteristic_angle_deg: 80,
  reach_ohm: null, reactive_reach_ohm: 4, resistive_reach_forward_ohm: 3, resistive_reach_reverse_ohm: 0, ...o,
});
const BOUNDED = {
  rule_id: "test-left-boundary-at-zero", rule_version: "1.0.0", field: "zones[Z1].resistive_reach.reverse",
  classification: "bounded", description: "The left boundary is drawn at R = 0.",
  envelope: "up to 0.5 × X at the upper-left corner", zone_id: "Z1",
};
const approximatePayload = (approximations = [BOUNDED]) => ({
  characteristic: "quadrilateral", impedance_basis: "primary",
  zones: [quad("Z1", "Zone 1"), quad("Z2", "Zone 2", { reactive_reach_ohm: 7, resistive_reach_forward_ohm: 5 })],
  approximations,
});
async function applyRouted(page, payload) {
  await page.route("**/api/v1/relay-import/review/apply", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) }));
  await applyBtn(page).click();
}

test("documented relay behaviour has its own chip, and the normal review shows no internal terms", async ({ page }) => {
  await openReview(page, relaySheet("red670"));
  // ZMQPDIS -> quadrilateral is documented relay behaviour, not a setting the sheet states
  await expect(chip(page, "zone.Z1.characteristic")).toHaveText("Documented relay behaviour");
  await expect(chip(page, "zone.Z1.characteristic")).toHaveAttribute("data-category", "documented");
  await expect(chip(page, "zone.Z1.status")).toHaveText("Mapped");
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText(/\d+ documented relay behaviour/);
  await expect(page.locator("#wwRelayImportSummary")).toContainText(/\d+ documented relay behaviour/);
  // the directional-element boundary is understood but not representable: "Not yet supported"
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Not yet supported");
  // the Source disclosure explains where the documented value comes from
  await row(page, "zone.Z1.characteristic").getByRole("button", { name: /Source/ }).first().click();
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Basis: derived from documented relay semantics");
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Not a setting stated in the file");
  await row(page, "zone.Z1.characteristic").getByRole("button", { name: /Source/ }).first().click();
  // internal vocabulary never reaches the normal (non-disclosure) UI
  const visible = await panel(page).evaluate((el) => el.innerText);
  for (const term of ["canonical gap", "geometry_mode", "UNVERIFIED", "unverified", "not_exposed", "engine adapter"]) {
    expect(visible).not.toContain(term);
  }
});

test("a missing source value reads 'Source value missing'", async ({ page }) => {
  await openReview(page, relaySheet("p441", { variant: "minimal" }));
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Source value missing");
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText(/\d+ not yet supported/);
});

test("a real Apply carries an empty approximations list and the plot is not marked approximate", async ({ page }) => {
  await p441Ready(page);
  await applyBtn(page).click();
  await expect(applyStatus(page)).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(boundaries(page)).toHaveCount(3);
  expect(await appliedApproximations(page)).toEqual([]);
  await expect(approxNote(page)).toHaveCount(0);
});

test("an approximate configuration says so in the R-X legend, and Remove releases it with the zones", async ({ page }) => {
  await p441Ready(page);
  await applyRouted(page, approximatePayload());
  await expect(applyStatus(page)).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(boundaries(page)).toHaveCount(2);
  await expect(approxNote(page)).toHaveText("Approximate plot");
  await expect(approxNote(page)).toHaveAttribute("title", /up to 0\.5 × X.*The relay settings are unchanged\./);
  expect((await appliedApproximations(page)).map((a) => [a.ruleId, a.classification, a.zoneId])).toEqual(
    [["test-left-boundary-at-zero", "bounded", "Z1"]]);

  await removeBtn(page).click();
  await expect(boundaries(page)).toHaveCount(0);
  await expect(approxNote(page)).toHaveCount(0);
  expect(await appliedApproximations(page)).toEqual([]);
});

test("a newly accepted import releases the earlier approximate configuration", async ({ page }) => {
  await p441Ready(page);
  await applyRouted(page, approximatePayload());
  await expect(approxNote(page)).toHaveCount(1);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await expect(boundaries(page)).toHaveCount(0);
  expect(await appliedApproximations(page)).toEqual([]);
});

test("a hand-edited approximate configuration is the user's: Remove keeps it and its approximate marking", async ({ page }) => {
  await p441Ready(page);
  await applyRouted(page, approximatePayload());
  await expect(approxNote(page)).toHaveCount(1);
  const reach = page.locator("#wwDistanceZone2ReactiveReachInput");
  await reach.fill("8");
  await reach.dispatchEvent("change");
  await removeBtn(page).click();
  await expect(boundaries(page)).toHaveCount(2);
  await expect(approxNote(page)).toHaveCount(1);
});

test("an Apply payload with an unbounded approximation is refused and nothing changes", async ({ page }) => {
  await p441Ready(page);
  const before = await page.evaluate(() => JSON.stringify(wwDistanceState.zones));
  await applyRouted(page, approximatePayload([{ ...BOUNDED, classification: "unbounded" }]));
  await expect(applyStatus(page)).toHaveText("The settings could not be applied. Nothing was changed.");
  expect(await page.evaluate(() => JSON.stringify(wwDistanceState.zones))).toEqual(before);
  await expect(boundaries(page)).toHaveCount(0);
  expect(await appliedApproximations(page)).toEqual([]);
  // a bounded approximation without its error envelope is just as invalid
  expect(await page.evaluate((p) => wwDistanceApplyImportedSettings(p, 1), approximatePayload([{ ...BOUNDED, envelope: null }]))).toBe(false);
});
