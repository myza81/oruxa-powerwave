// Slice 11 -- Siemens 7SA511 through the unchanged generic relay-import UI.
//
// Upload -> identify -> generic Extraction Review -> resolve the required Missing/Assumption items ->
// Ready to apply -> Apply Settings -> dynamic Distance Protection cards -> R-X plot -> Fit Zones.
// The sheet is a synthetic 7SA511-shaped PDF (the owner's real sheet is never committed). Nothing here
// uses a relay-specific selector: the review, the Apply button and the cards are the P441 ones.
// Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { siemens7sa511Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

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
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const LEFT = "Left Resistive Reach (−R)";
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const boundary = (page, key) => page.locator(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${key}"]`);
const legendItems = (page) => page.locator("#wwDistanceZoneLegend .ww-dist-zone-legend-item");

async function openReview(page, pdfOptions) {
  await openDistance(page);
  await pick(page, "document.pdf", siemens7sa511Pdf(pdfOptions));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

async function resolveChoice(page, label, key, value) {
  await button(page, `Resolve ${label}`).click();
  const form = row(page, key).locator("form.ww-rr-resolve");
  await form.locator("select").selectOption(value);
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form).toBeHidden();
}

async function resolveNumber(page, label, key, value) {
  await button(page, `Resolve ${label}`).click();
  const form = row(page, key).locator("form.ww-rr-resolve");
  await form.locator("input").fill(String(value));
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form).toBeHidden();
}

// What an engineer does: state which zones are in service (the sheet has no per-zone enable), give each a
// delay (the sheet leaves the timer cells blank), take the 0.00 ohm suggestion for the Left (-R) reach, confirm the assumptions.
async function makeReady(page, { extra = false } = {}) {
  await resolveChoice(page, "Zone 1 Status", "zone.Z1.status", "enabled");
  await resolveChoice(page, "Zone 2 Status", "zone.Z2.status", "enabled");
  await resolveChoice(page, "Zone 3 Status", "zone.Z3.status", "enabled");
  await resolveChoice(page, "Zone 4 Status", "zone.Z4.status", "disabled");
  await resolveChoice(page, "Zone 1L Status", "zone.Z1L.status", "disabled");
  await resolveChoice(page, "Zone 1B Status", "zone.Z1B.status", extra ? "enabled" : "disabled");
  await resolveNumber(page, "Zone 1 Phase Time Delay", "zone.Z1.timer.pp", 0.15);
  await resolveNumber(page, "Zone 2 Phase Time Delay", "zone.Z2.timer.pp", 0.45);
  await resolveNumber(page, "Zone 3 Time Delay", "zone.Z3.timer", 3);
  if (extra) await resolveNumber(page, "Zone 1B Phase Time Delay", "zone.Z1B.timer.pp", 0.5);
  for (const n of extra ? ["1", "2", "3", "1B"] : ["1", "2", "3"]) {
    await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  }
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
}

test("a 7SA511 sheet is identified and opens the generic review with every zone", async ({ page }) => {
  await openDistance(page);
  await pick(page, "document.pdf", siemens7sa511Pdf());
  const card = page.locator("#wwRelayImportFile");
  await expect(card).toContainText("Siemens");
  await expect(card).toContainText("7SA511");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("6 zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
  for (const title of ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 1B", "Zone 1L"]) {
    await expect(panel(page).locator("details", { hasText: title }).first()).toBeVisible();
  }
  // counts use the generic taxonomy; the sheet's own labels are kept; nothing is ready yet
  await expect(page.locator("#wwRelayImportSummary")).toContainText("assumptions");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("missing");
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
  // explicit R/X: a Reactive Reach (X) row and no polar Reach / Reach Angle rows at all
  await expect(row(page, "zone.Z2.x_reach")).toContainText("Reactive Reach (X)");
  await expect(row(page, "zone.Z2.reach")).toHaveCount(0);
  await expect(row(page, "zone.Z2.reach.angle")).toHaveCount(0);
  await expect(row(page, "zone.Z2.rr.pp")).toContainText("Right Resistive Reach (+R)");
  await expect(row(page, "zone.Z2.characteristic")).toContainText("Explicit R/X");
  // the timer cell is blank: Missing, never the "Infinity" printed in the range column
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("Source value missing");
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("Not available"); // no delay value is shown
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("not the configured delay");
  await expect(row(page, "zone.Z3.direction")).toContainText("Reverse");
  // provenance: the original setting name / code / raw text, available beside the value
  await row(page, "zone.Z2.x_reach").getByRole("button", { name: /Source/ }).first().click();
  await expect(row(page, "zone.Z2.x_reach")).toContainText("1312");
  await expect(row(page, "zone.Z2.x_reach")).toContainText("X2");
});

test("the sheet's page notes are shown as document notes beside the zone, not as settings", async ({ page }) => {
  await openReview(page);
  const z1 = panel(page).locator('details[data-group="zone-Z1"]');
  const notes = z1.locator("details[data-source-notes]");
  const note = notes.locator(".ww-rr-source-note");
  await expect(note).toHaveCount(1);
  // a collapsed, secondary disclosure: the note's words are hidden until the user asks for them
  await expect(notes.locator(".ww-rr-source-notes-label")).toHaveText("Document note");
  await expect(note).toBeHidden();
  await notes.locator(":scope > summary").click();
  await expect(note).toBeVisible();
  await expect(note).toContainText("Forward direction timer set to 0.15s (Delayed Zone 1)");
  await expect(note).toContainText(/Source: Page \d+ · line \d+/);
  await expect(notes).toContainText("Not used as the configured setting.");
  // the timer the note talks about is still Missing -- the note filled nothing in
  await expect(row(page, "zone.Z1.timer.pp")).toContainText("Source value missing");
  await expect(row(page, "zone.Z1.timer.pp")).not.toContainText("0.15");
  const z1b = panel(page).locator('details[data-group="zone-Z1B"] details[data-source-notes]');
  await expect(z1b).toContainText("Zone 1B Inactive timer set to oos (Infinity)");
  await expect(row(page, "zone.Z1B.status")).toContainText("Source value missing"); // the "inactive" note is not the zone's state
});

test("the zone state of the 7SA511 is never assumed: the user states it, then it is Ready to apply", async ({ page }) => {
  await openReview(page);
  await expect(row(page, "zone.Z1.status")).toContainText("Source value missing");
  await expect(row(page, "zone.Z1B.status")).toContainText("Source value missing"); // the sheet's "inactive" line is a note, not a setting
  await expect(row(page, "zone.Z2.status")).toContainText("Source value missing"); // DIST.PROT. = ON is the function, not a zone
  await makeReady(page);
  await expect(applyBtn(page)).toBeVisible();
});

test("Apply Settings fills the dynamic cards and draws only the enabled zones on the R-X plane", async ({ page }) => {
  await openReview(page);
  await makeReady(page);
  await expect(boundary(page, "zone1")).toHaveCount(0); // nothing is drawn until Apply
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");

  await expect(input(page, 1, "ReactiveReach")).toHaveValue("3");
  await expect(input(page, 1, "ResistiveForward")).toHaveValue("2"); // R1 (phase-phase), not R1E = 6
  await expect(input(page, 1, "ResistiveReverse")).toHaveValue("0");
  // explicit R/X: no reach angle exists, so none is shown or sent
  await expect(page.locator("#wwDistanceZone1AngleField")).toBeHidden();
  await expect(page.locator("#wwDistanceZone1Geometry")).toHaveText("Geometry: Explicit R/X");
  await expect(input(page, 1, "Delay")).toHaveValue("0.15");
  await expect(input(page, 2, "ReactiveReach")).toHaveValue("5");
  await expect(input(page, 2, "Delay")).toHaveValue("0.45");
  await expect(input(page, 3, "Delay")).toHaveValue("3");

  // Zones 1-3 are drawn; the disabled Zone 4, Zone 1B and Zone 1L are not.
  for (const key of ["zone1", "zone2", "zone3"]) await expect(boundary(page, key)).toHaveCount(1);
  await expect(page.locator("#wwDistanceSvg .ww-dist-zone-boundary")).toHaveCount(3);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3 · Reverse"]);
  await expect(page.locator("#wwDistancePanel .ww-dist-zone-card")).toHaveCount(4);
  await expect(page.locator("#wwDistancePanel [data-zone-dynamic]")).toHaveCount(0);
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();
  // Zone 1 is drawn as its X / +R / -R box: reach 3, +R 2, -R 0 (no tilt)
  const corners = await page.evaluate(() => document.querySelector('#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="zone1"]').getAttribute("points"));
  const pts = corners.trim().split(/\s+/).map((p) => p.split(",").map(Number));
  const xs = new Set(pts.map((p) => p[0].toFixed(0))), ys = new Set(pts.map((p) => p[1].toFixed(0)));
  expect(xs.size).toBe(2); // an upright rectangle: two distinct x, two distinct y -- axis-aligned
  expect(ys.size).toBe(2);
});

test("an enabled Zone 1B becomes a dynamic card with the sheet's own label, is plotted and fitted", async ({ page }) => {
  await openReview(page, { notes: false });
  await expect(row(page, "zone.Z1B.status")).toContainText("Source value missing");
  await makeReady(page, { extra: true });
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  const extra = page.locator("#wwDistancePanel [data-zone-dynamic]");
  await expect(extra).toHaveCount(1);
  await expect(extra.locator(".ww-dist-zone-card-title")).toHaveText("Zone 1B");
  await expect(boundary(page, "z_z1b")).toHaveCount(1);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3 · Reverse", "Zone 1B"]);
  await page.locator("#wwDistanceFitZonesBtn").click();
  const inside = await page.evaluate(() => {
    const svg = document.getElementById("wwDistanceSvg").getBoundingClientRect();
    const r = document.querySelector('#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="z_z1b"]').getBoundingClientRect();
    return r.left >= svg.left - 1 && r.right <= svg.right + 1 && r.top >= svg.top - 1 && r.bottom <= svg.bottom + 1;
  });
  expect(inside).toBe(true);
  // a re-Apply of the first reviewed state is not needed to remove it: disabling the card removes the boundary
  await page.locator("#wwDistanceZ_z1bEnabled").uncheck();
  await expect(boundary(page, "z_z1b")).toHaveCount(0);
});

test("an enabled zone the engine cannot draw keeps the review Not ready (nothing is approximated)", async ({ page }) => {
  await openReview(page);
  await resolveChoice(page, "Zone 1L Status", "zone.Z1L.status", "enabled");
  await expect(readiness(page)).toContainText("Not ready");
  await expect(panel(page)).toContainText("Zone direction 'non_directional' is not supported");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("no Siemens-specific control exists in the page", async ({ page }) => {
  await openReview(page);
  const html = await page.content();
  const ids = await page.evaluate(() => [...document.querySelectorAll("[id]")].map((e) => e.id));
  expect(ids.filter((i) => /siemens|7sa|siprotec/i.test(i))).toEqual([]);
  expect(await page.locator("script").evaluateAll((s) => s.map((x) => x.textContent).join("\n"))).not.toMatch(/7SA|Siemens|SIPROTEC/);
  expect(html.length).toBeGreaterThan(0);
});
