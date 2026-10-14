// Remaining relay families -- interpreted by validated JSON parameter catalogs only, through the unchanged generic
// relay-import UI (no relay-specific control or script).
//
// REL670 (catalog-only, READY FOR OWNER UAT): upload -> identify -> generic review -> accept the 0.00 ohm Left (-R)
// visualization approximation (the real boundary is the ZDRDIR directional element) -> confirm assumptions -> Apply ->
// Distance Protection cards -> R-X plot, Zone 4 enabled in reverse.
// 7SL87 / GRZ100 (PARTIALLY SUPPORTED): the review is useful but stays Not ready -- blank timer cells are Missing (never the
// Infinity printed in the range column), tilt / inclined boundaries / blinders are preserved as capability gaps, CT / VT
// ratios are shown as ratios. Synthetic sheets with invented numbers; the owner's real sheets are never committed.
// Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { rel670Pdf, sl87Pdf, grz100Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

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
const zoneGroup = (page, id) => panel(page).locator(`details[data-group="zone-${id}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const LEFT = "Left Resistive Reach (−R)";
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const boundary = (page, key) => page.locator(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${key}"]`);

async function openReview(page, pdf, zones) {
  await openDistance(page);
  await pick(page, "document.pdf", pdf);
  await expect(page.locator("#wwRelayImportSummary")).toContainText(`${zones} zones found`);
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

test("REL670: identified and reviewed through its catalog, with Zone 4 enabled in reverse from its own settings", async ({ page }) => {
  await openReview(page, rel670Pdf(), 4);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Hitachi Energy · REL670");
  await expect(row(page, "zone.Z4.status")).toContainText("Enabled");
  await expect(row(page, "zone.Z4.status")).toContainText("Mapped");
  await expect(row(page, "zone.Z4.direction")).toContainText("Reverse");
  // bare IL1..IL3 channel labels (no ChannelType rows): the phase CTs, never the IN channel
  await expect(row(page, "ct.primary")).toContainText("900 A");
  await row(page, "ct.primary").getByRole("button", { name: /Source/ }).first().click();
  await expect(row(page, "ct.primary")).toContainText("CTprim1");
  await expect(row(page, "ct.primary")).not.toContainText("CTprim4");
  // RFPP is a loop value: halved, with the printed value, the transformation and the catalog in Source
  const pp = row(page, "zone.Z1.rr.pp");
  await expect(pp).toContainText("4 Ω");
  await pp.getByRole("button", { name: /Source/ }).first().click();
  await expect(pp).toContainText("Raw: 8");
  await expect(pp).toContainText("÷ 2");
  await expect(pp).toContainText("hitachi-rel670-catalog");
  // the ZDRDIR left boundary is a capability gap, offered only as a worded approximation
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Unsupported");
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("not the relay's geometry");
  // the scheme requirement is a document note beside the zone, never the value
  await expect(zoneGroup(page, "Z1").locator("[data-source-notes]")).toContainText("Zone 1 timer requirement: 0.15 s");
  await expect(row(page, "zone.Z1.timer.pp")).toContainText("0.15 s");
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("REL670: Ready to apply after the approximation and confirmations; Apply plots all four zones", async ({ page }) => {
  await openReview(page, rel670Pdf(), 4);
  for (const n of ["1", "2", "3", "4"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");
  await expect(input(page, 1, "ReactiveReach")).toHaveValue("6");
  await expect(input(page, 1, "ResistiveForward")).toHaveValue("4"); // RFPP 8 ohm/loop / 2, never RFPE = 12
  await expect(input(page, 1, "ResistiveReverse")).toHaveValue("0");
  await expect(page.locator("#wwDistanceZone1Geometry")).toHaveText("Geometry: Explicit R/X");
  for (const key of ["zone1", "zone2", "zone3", "zone4"]) await expect(boundary(page, key)).toHaveCount(1);
  // the reverse Zone 4 lies on the other side of the origin from Zone 1
  const cy = (key) => page.evaluate((k) => { const r = document.querySelector(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${k}"]`).getBoundingClientRect(); return (r.top + r.bottom) / 2; }, key);
  expect(await cy("zone4")).toBeGreaterThan(await cy("zone1"));
});

test("7SL87: blank timer cells are Missing (not the Infinity range), basis from Edit mode, tilt and inclined boundary preserved", async ({ page }) => {
  await openReview(page, sl87Pdf(), 2);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens · 7SL87");
  await expect(row(page, "basis")).toContainText("Primary");
  await expect(row(page, "basis")).toContainText("Mapped");
  const timer = row(page, "zone.Z1.timer.pp");
  await expect(timer).toContainText("Missing");
  await expect(timer).not.toContainText("Infinity s");
  await timer.getByRole("button", { name: /Source/ }).first().click();
  await expect(timer).toContainText("blank");
  await expect(zoneGroup(page, "Z1").locator("[data-source-notes]")).toContainText("Zone 1 timer requirement: 0.15 s");
  await expect(row(page, "zone.Z1.x_reach")).toContainText("4.7 Ω");
  await expect(row(page, "zone.Z1.rr.pp")).toContainText("3.1 Ω");
  await expect(row(page, "zone.Z1.tilt")).toContainText("Unsupported");
  await expect(zoneGroup(page, "Z1")).toContainText("Dist. characteristic angle");
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Missing"); // not named by the sheet: not assumed
  await page.locator("#wwRelayReviewConfirmAll").click().catch(() => {});
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("GRZ100: CT / VT ratios, a phase / earth characteristic mismatch and blinders are shown honestly", async ({ page }) => {
  await openReview(page, grz100Pdf(), 8);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Toshiba · GRZ100");
  await expect(row(page, "ct.ratio")).toContainText("CT Ratio");
  await expect(row(page, "ct.ratio")).toContainText("1200");
  await expect(row(page, "vt.ratio")).toContainText("1200");
  await expect(row(page, "ct.primary")).toContainText("Missing"); // a ratio is never split into primary / secondary
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Unsupported"); // Quad phase vs Mho earth
  await expect(zoneGroup(page, "Z1")).toContainText("BFRS");
  await expect(zoneGroup(page, "Z1")).toContainText("BFLS-angle");
  await expect(row(page, "zone.Z1.status")).toContainText("Missing"); // no zone switch: not invented
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("0.3 s");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("no relay-family-specific control or script exists in the page", async ({ page }) => {
  await openReview(page, rel670Pdf(), 4);
  const ids = await page.evaluate(() => [...document.querySelectorAll("[id]")].map((e) => e.id));
  expect(ids.filter((i) => /rel670|rel511|7sl87|7sa613|grz100|grl200|rcs941|lfzp|relz/i.test(i))).toEqual([]);
  expect(await page.locator("script").evaluateAll((s) => s.map((x) => x.textContent).join("\n"))).not.toMatch(/REL670|REL511|7SL87|7SA613|GRZ100|GRL200|RCS-?941|LFZP|RELZ/);
});
