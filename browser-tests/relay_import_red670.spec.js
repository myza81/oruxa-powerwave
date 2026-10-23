// Slice 12 -- Hitachi Energy RED670 through the unchanged generic relay-import UI.
//
// Upload -> identify -> generic Extraction Review -> accept the 0.00 ohm Left (-R) visualization approximation (the
// relay's real left boundary is the ZDRDIR directional element, an Unsupported capability gap) and confirm the
// assumptions -> Ready to apply -> Apply Settings -> dynamic Distance Protection cards -> R-X plot -> Fit Zones.
// The sheet is a synthetic RED670-shaped PDF (the owner's real sheet is never committed). Nothing here uses a
// relay-specific selector: the review, the Apply button and the cards are the P441 / 7SA511 ones. The RED670 states
// every zone's activation itself, so unlike the 7SA511 nothing about zone state or delay is asked of the user.
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
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const LEFT = "Left Resistive Reach (−R)";
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const boundary = (page, key) => page.locator(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${key}"]`);
const legendItems = (page) => page.locator("#wwDistanceZoneLegend .ww-dist-zone-legend-item");

async function openReview(page, pdfOptions) {
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("red670", pdfOptions));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

// What an engineer does: accept the explicit 0.00 ohm visualization approximation for each unsupported Left (-R) reach,
// then confirm the assumptions. No zone state and no delay is asked for: the RED670 states them itself.
async function makeReady(page, zones = ["1", "2", "3"]) {
  for (const n of zones) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
}

test("a RED670 sheet is identified and opens the generic review with every zone", async ({ page }) => {
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("red670"));
  const card = page.locator("#wwRelayImportFile");
  await expect(card).toContainText("Hitachi Energy");
  await expect(card).toContainText("RED670");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("4 zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
  for (const title of ["Zone 1", "Zone 2", "Zone 3", "Zone 4"]) {
    await expect(panel(page).locator("details", { hasText: title }).first()).toBeVisible();
  }
  await expect(page.locator("#wwRelayImportSummary")).toContainText("assumptions");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("missing");
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
  // activation is stated by the sheet: mapped, not asked for
  await expect(row(page, "zone.Z1.status")).toContainText("Enabled");
  await expect(row(page, "zone.Z1.status")).toContainText("Mapped");
  await expect(panel(page).locator('details[data-group="zone-Z4"]')).toContainText("Disabled");
  // explicit R/X: a Reactive Reach (X) row and no polar Reach / Reach Angle rows at all
  await expect(row(page, "zone.Z2.x_reach")).toContainText("Reactive Reach (X)");
  await expect(row(page, "zone.Z2.reach")).toHaveCount(0);
  await expect(row(page, "zone.Z2.reach.angle")).toHaveCount(0);
  await expect(row(page, "zone.Z2.rr.pp")).toContainText("Right Resistive Reach (+R)");
  await expect(row(page, "zone.Z2.rr.pe")).toContainText("Earth Resistive Reach");
  await expect(row(page, "zone.Z2.characteristic")).toContainText("Explicit R/X");
  // ZMQPDIS is the quadrilateral function: authoritative family semantics -- not an Assumption, and
  // presented as documented relay behaviour rather than a setting the sheet states (DEC-198)
  await expect(row(page, "zone.Z2.characteristic").locator(".ww-rr-status")).toHaveText("Documented relay behaviour");
  // timers are the actual tPP / tPE settings
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("0.45");
  await expect(row(page, "zone.Z2.timer.pe")).toContainText("0.45");
  // provenance: the original instance-prefixed setting name beside the value
  await row(page, "zone.Z2.x_reach").getByRole("button", { name: /Source/ }).first().click();
  await expect(row(page, "zone.Z2.x_reach")).toContainText("ZM02-:X1");
});

test("the Left (−R) reach is Unsupported (a capability gap), keeps its ZDRDIR source, and is the only thing blocking", async ({ page }) => {
  await openReview(page);
  const left = row(page, "zone.Z1.rr.reverse");
  await expect(left).toContainText("Not yet supported");
  await expect(left).not.toContainText("Source value missing");
  // the offered value is worded concisely as an optional visualization approximation, never a mapped setting
  await expect(left.locator(".ww-rr-offer")).toHaveText(
    "Relay directional boundary is not yet representable. 0.00 Ω is an optional visualization approximation only and is not a mapped relay setting.");
  await expect(left).not.toContainText("cannot be represented yet");
  await expect(left).not.toContainText("Suggested for visualization");
  await left.getByRole("button", { name: /Source/ }).first().click();
  await expect(left).toContainText("ZD01-:ArgDir");
  await expect(left).toContainText("ZD01-:ArgNegRes");
  await expect(left).toContainText("capability gap");
  await expect(page.locator("#wwRelayReviewBlockingSettings")).toHaveText("3 blocking"); // Zones 1-3 only
  await expect(panel(page)).toContainText("The Left Resistive Reach (−R) is unresolved.");
  // the ZDRDIR angles are preserved with the zone, as stated
  await expect(row(page, "zone.Z1.char.directional_arg_dir")).toContainText("15");
  await expect(row(page, "zone.Z1.char.directional_arg_neg_res")).toContainText("115");
  // the disabled Zone 4's left reach does not block
  await expect(row(page, "zone.Z4.rr.reverse")).toContainText("Not yet supported");
});

test("accepting the approximation reads as a suggestion, not as the relay's setting", async ({ page }) => {
  await openReview(page);
  const left = row(page, "zone.Z1.rr.reverse");
  await button(page, `Use 0.00 Ω for Zone 1 ${LEFT}`).click();
  await expect(left).toContainText("Resolved · Suggested");
  await left.getByRole("button", { name: /Source/ }).first().click();
  await expect(left).toContainText("accepted by you, for this import session only");
  await expect(left).toContainText("the relay's setting, and not mapped from a profile");
  await button(page, `Clear the value of Zone 1 ${LEFT}`).click();
  await expect(left).toContainText("Not yet supported");
});

test("the loop-value RFPP is shown halved with the OEM value and transformation kept in Source", async ({ page }) => {
  await openReview(page);
  const pp = row(page, "zone.Z2.rr.pp");
  await expect(pp).toContainText("5 Ω"); // RFPP = 10 ohm/loop
  await pp.getByRole("button", { name: /Source/ }).first().click();
  await expect(pp).toContainText("ZM02-:RFPP");
  await expect(pp).toContainText("Raw: 10");
  await expect(pp).toContainText("Transformation: RFPP 10 ohm/loop ÷ 2 = 5 ohm");
  const pe = row(page, "zone.Z2.rr.pe");
  await expect(pe).toContainText("20 Ω"); // RFPE is its own quantity, used as printed
});

test("the scheme-requirement lines are document notes beside the zone, not settings", async ({ page }) => {
  await openReview(page);
  const notes = panel(page).locator('details[data-group="zone-Z1"] details[data-source-notes]');
  const note = notes.locator(".ww-rr-source-note");
  await expect(note).toHaveCount(1);
  await expect(notes.locator(".ww-rr-source-notes-label")).toHaveText("Document note");
  await expect(note).toBeHidden(); // collapsed by default
  await notes.locator(":scope > summary").click();
  await expect(note).toContainText("Forward direction timer set to 0.15s");
  await expect(note).toContainText(/Source: Page \d+ · line \d+/);
  await expect(notes).toContainText("Not used as the configured setting.");
  const z4 = panel(page).locator('details[data-group="zone-Z4"] details[data-source-notes]');
  await expect(z4).toContainText("Inactive (Having duplicated BB Protection)");
});

test("Apply Settings fills the dynamic cards and draws only the enabled zones on the R-X plane", async ({ page }) => {
  await openReview(page);
  await makeReady(page);
  await expect(boundary(page, "zone1")).toHaveCount(0); // nothing is drawn until Apply
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");

  await expect(input(page, 1, "ReactiveReach")).toHaveValue("6");
  await expect(input(page, 1, "ResistiveForward")).toHaveValue("3.5"); // RFPP 7 ohm/loop / 2 (phase-phase), not RFPE = 15
  await expect(input(page, 1, "ResistiveReverse")).toHaveValue("0");
  await expect(page.locator("#wwDistanceZone1AngleField")).toBeHidden(); // explicit R/X: no reach angle exists
  await expect(page.locator("#wwDistanceZone1Geometry")).toHaveText("Geometry: Explicit R/X");
  await expect(input(page, 1, "Delay")).toHaveValue("0.15");
  await expect(input(page, 2, "ReactiveReach")).toHaveValue("11");
  await expect(input(page, 2, "ResistiveForward")).toHaveValue("5");
  await expect(input(page, 2, "Delay")).toHaveValue("0.45");
  await expect(input(page, 3, "ReactiveReach")).toHaveValue("20");
  await expect(input(page, 3, "Delay")).toHaveValue("3");

  // Zones 1-3 are drawn; the switched-off Zone 4 is not.
  for (const key of ["zone1", "zone2", "zone3"]) await expect(boundary(page, key)).toHaveCount(1);
  await expect(page.locator("#wwDistanceSvg .ww-dist-zone-boundary")).toHaveCount(3);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3"]);
  await expect(page.locator("#wwDistancePanel [data-zone-dynamic]")).toHaveCount(0);
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();
  // Zone 1 is drawn as its X / +R / -R box: an upright rectangle in the orthogonal frame (no tilt)
  const points = await page.evaluate(() => document.querySelector('#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="zone1"]').getAttribute("points"));
  const pts = points.trim().split(/\s+/).map((p) => p.split(",").map(Number));
  expect(new Set(pts.map((p) => p[0].toFixed(0))).size).toBe(2);
  expect(new Set(pts.map((p) => p[1].toFixed(0))).size).toBe(2);
  // the nested boxes grow with the reaches
  const width = (key) => page.evaluate((k) => document.querySelector(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${k}"]`).getBoundingClientRect().width, key);
  expect(await width("zone2")).toBeGreaterThan(await width("zone1"));
  expect(await width("zone3")).toBeGreaterThan(await width("zone2"));
});

test("Fit Zones brings every drawn zone inside the plot", async ({ page }) => {
  await openReview(page);
  await makeReady(page);
  await applyBtn(page).click();
  await expect(boundary(page, "zone3")).toHaveCount(1);
  await page.locator("#wwDistanceFitZonesBtn").click();
  const inside = await page.evaluate(() => {
    const svg = document.getElementById("wwDistanceSvg").getBoundingClientRect();
    return [...document.querySelectorAll("#wwDistanceSvg .ww-dist-zone-boundary")].every((el) => {
      const r = el.getBoundingClientRect();
      return r.left >= svg.left - 1 && r.right <= svg.right + 1 && r.top >= svg.top - 1 && r.bottom <= svg.bottom + 1;
    });
  });
  expect(inside).toBe(true);
});

test("an enabled fifth ZMQPDIS instance becomes a dynamic card, is plotted and fitted (no fixed zone count)", async ({ page }) => {
  await openReview(page, { variant: "fifth_zone" });
  await expect(page.locator("#wwRelayImportSummary")).toContainText("5 zones found");
  await makeReady(page, ["1", "2", "3", "5"]);
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  const extra = page.locator("#wwDistancePanel [data-zone-dynamic]");
  await expect(extra).toHaveCount(1);
  await expect(extra.locator(".ww-dist-zone-card-title")).toHaveText("Zone 5");
  await expect(boundary(page, "z_z5")).toHaveCount(1);
  await page.locator("#wwDistanceFitZonesBtn").click();
  const inside = await page.evaluate(() => {
    const svg = document.getElementById("wwDistanceSvg").getBoundingClientRect();
    const r = document.querySelector('#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="z_z5"]').getBoundingClientRect();
    return r.left >= svg.left - 1 && r.right <= svg.right + 1 && r.top >= svg.top - 1 && r.bottom <= svg.bottom + 1;
  });
  expect(inside).toBe(true);
  // the reverse zone sits on the opposite side of the origin from Zone 1
  const cx = (key) => page.evaluate((k) => { const r = document.querySelector(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${k}"]`).getBoundingClientRect(); return (r.top + r.bottom) / 2; }, key);
  expect(await cx("z_z5")).toBeGreaterThan(await cx("zone1"));
});

test("a zone switched off by its own Operation parameter is preserved but not applied or drawn", async ({ page }) => {
  await openReview(page, { set: { "ZM01-:Operation": "OFF" } });
  await expect(panel(page).locator('details[data-group="zone-Z1"]')).toContainText("Disabled");
  await makeReady(page, ["2", "3"]);
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(boundary(page, "zone1")).toHaveCount(0);
  await expect(boundary(page, "zone2")).toHaveCount(1);
  await expect(page.locator("#wwDistanceZone1Enabled")).not.toBeChecked();
});

test("an enabled non-directional zone the engine cannot draw keeps the review Not ready (nothing is approximated)", async ({ page }) => {
  await openReview(page, { set: { "ZM03-:OperationDir": "Non-dir" } });
  await button(page, `Use 0.00 Ω for Zone 1 ${LEFT}`).click();
  await expect(readiness(page)).toContainText("Not ready");
  await expect(panel(page)).toContainText("is not supported");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("no RED670-specific control exists in the page", async ({ page }) => {
  await openReview(page);
  const ids = await page.evaluate(() => [...document.querySelectorAll("[id]")].map((e) => e.id));
  expect(ids.filter((i) => /red670|hitachi|relion|zmqpdis/i.test(i))).toEqual([]);
  expect(await page.locator("script").evaluateAll((s) => s.map((x) => x.textContent).join("\n"))).not.toMatch(/RED670|Hitachi|Relion|ZMQPDIS/);
});
