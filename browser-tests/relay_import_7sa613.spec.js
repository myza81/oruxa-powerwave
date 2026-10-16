// 7SA613 under DEC-198 (Amendment 6) through the unchanged generic review UI.
//
// Documented relay behaviour (Siemens 7SA6 manuals C53000-G1176-C156-2 / -7, version-dependent) replaces the artificial
// "Missing" characteristic, loop and basis blockers: polygon, phase-phase / phase-earth loops of every zone in service,
// Secondary basis. An explicit "Infinity" delay is a configured value ("∞ (no timed trip)"), never Unreadable; on a zone in
// service it is an engine limitation. Genuine gaps stay: blank delay cells and a blank R load (ph-ph) are "Source value
// missing"; the inclined resistive edges and the non-directional Zone 5 are "not yet supported"; no 0.00 ohm offer. Not
// ready, no Apply. The sheet is synthetic (the owner's real sheet is never committed). Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { sa613Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  await openDistance(page);
  await pick(page, "document.pdf", sa613Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
});
test.afterEach(() => {
  expect(problems).toEqual([]);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();
const rawRow = (page, name) => panel(page).locator("li", { hasText: name }).first();
const source = (page, key) => row(page, key).getByRole("button", { name: /Source/ }).first();

test("characteristic, loops and basis read as documented relay behaviour, cited to the Siemens 7SA6 manuals", async ({ page }) => {
  for (const key of ["zone.Z1.characteristic", "zone.Z1.pp_enabled", "zone.Z1.pe_enabled", "basis"]) {
    await expect(chip(page, key)).toHaveText("Documented relay behaviour");
    await expect(row(page, key)).toHaveAttribute("data-blocking", "false");
  }
  await expect(row(page, "basis")).toContainText("Secondary");
  await source(page, "zone.Z1.characteristic").click();
  await expect(row(page, "zone.Z1.characteristic")).toContainText("C53000-G1176-C156");
  await expect(row(page, "zone.Z1.characteristic")).toContainText("version-dependent");
  // an inactive zone has no such selector: "Not a relay setting", never "Source value missing"
  await expect(chip(page, "zone.Z4.characteristic")).toHaveText("Not a relay setting");
});

test("an Infinity delay is a configured value; on a zone in service it is not yet supported, never unreadable", async ({ page }) => {
  await expect(row(page, "zone.Z4.timer")).toContainText("∞ (no timed trip)");
  await expect(row(page, "zone.Z4.timer")).toHaveAttribute("data-blocking", "false");
  await expect(row(page, "zone.Z5.timer")).toContainText("∞ (no timed trip)");
  await expect(chip(page, "zone.Z5.timer")).toHaveText("Not yet supported");
  await expect(panel(page)).not.toContainText("Unreadable");
  await expect(chip(page, "zone.Z1.timer.pp")).toHaveText("Source value missing");   // a blank cell stays a source gap
});

test("the inclined edges, the left boundary and the non-directional Zone 5 are not yet supported; no 0.00 Ω offer", async ({ page }) => {
  await expect(chip(page, "zone.Z1.rr.pp")).toHaveText("Not yet supported");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Not yet supported");
  await source(page, "zone.Z1.rr.reverse").click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Rleft(X) = -R + X * cot(phi)");
  await expect(panel(page).getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
  await expect(chip(page, "zone.Z5.direction")).toHaveText("Not yet supported");
  await expect(row(page, "zone.Z5.direction")).toContainText("Non directional");
  await expect(row(page, "zone.Z1.tilt")).toContainText("0°");                           // Zone Reduction 0: exact
  await expect(chip(page, "zone.Z1.tilt")).toHaveText("Mapped");
});

test("a blank load-cutout resistance blocks as a source gap; the relay is not ready and offers no Apply", async ({ page }) => {
  const rload = rawRow(page, "R load (ph-ph)");
  await expect(rload.locator(".ww-rr-status").first()).toHaveText("Source value missing");
  await expect(rload).toHaveAttribute("data-blocking", "true");
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "not_ready");
  await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);
  const reasons = page.locator("#wwRelayReviewBlocking");
  await expect(reasons).toContainText("has no configured value in the source");
  await expect(reasons).toContainText("does not trip on its own timer");
  await expect(reasons).not.toContainText("Characteristic type is unresolved");
  await expect(reasons).not.toContainText("basis");
});
