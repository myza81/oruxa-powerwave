// 7SL87 under DEC-198 (Amendment 3) through the unchanged generic review UI.
//
// Documented relay behaviour (Siemens C53000-G5040-C011-9, V07.50, version-dependent for the 7SL87_8.81 sheet) replaces
// the artificial "Missing" characteristic: a zone stated with the quadrilateral parameter set is a quadrilateral zone
// (SIPROTEC 5 has no selector). The loops stay Mapped from Function mode. Genuine gaps stay: the blank operate-delay
// cells are "Source value missing"; the resistance line inclined at the 82.7° distance characteristic angle is "not yet
// supported" by the engine (no vertical +R); the left / directional boundary is "not yet supported" with no 0.00 ohm
// offer; the phase-phase load cutout in use is "not yet supported" (its effect is not verified). Not ready, no Apply.
// The sheet is synthetic (the owner's real sheet is never committed). Nothing here uses a 7SL87-specific selector.
// Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { sl87Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  await openDistance(page);
  await pick(page, "document.pdf", sl87Pdf());
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

test("the characteristic reads as documented relay behaviour, cited to the Siemens manual; the loops stay Mapped", async ({ page }) => {
  await expect(chip(page, "zone.Z1.characteristic")).toHaveText("Documented relay behaviour");
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Quadrilateral");
  await expect(row(page, "zone.Z1.characteristic")).toHaveAttribute("data-blocking", "false");
  await source(page, "zone.Z1.characteristic").click();
  const char = row(page, "zone.Z1.characteristic");
  await expect(char).toContainText("C53000-G5040-C011-9");
  await expect(char).toContainText("— verified");
  await expect(char).toContainText("version-dependent");
  for (const key of ["zone.Z1.pp_enabled", "zone.Z1.pe_enabled"]) {
    await expect(chip(page, key)).toHaveText("Mapped");                               // a configured setting
    await expect(row(page, key)).toContainText("Enabled");
  }
});

test("the inclined +R and the left boundary are not yet supported, and no 0.00 Ω is offered", async ({ page }) => {
  const rr = row(page, "zone.Z1.rr.pp");
  await expect(chip(page, "zone.Z1.rr.pp")).toHaveText("Not yet supported");
  await expect(rr).toHaveAttribute("data-blocking", "true");
  await source(page, "zone.Z1.rr.pp").click();
  await expect(rr).toContainText("Dist. characteristic angle");                     // the angle is kept with the +R ...
  await expect(rr).toContainText("82.7");
  await expect(rr).toContainText("Rright(X) = R + X * cot(phi)");                   // ... with the documented relation
  await expect(rr).toContainText("not halved");

  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Not yet supported");
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-blocking", "true");
  await expect(row(page, "zone.Z1.rr.reverse").getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
  await expect(panel(page).getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
});

test("blank delay cells stay Source value missing; the load cutout in use is kept and blocks", async ({ page }) => {
  await expect(chip(page, "zone.Z1.timer.pp")).toHaveText("Source value missing");
  await expect(row(page, "zone.Z1.timer.pp")).not.toContainText("0.15 s");          // the note is never the setting
  const cutout = rawRow(page, "Use ph-ph load cutout");
  await expect(cutout.locator(".ww-rr-status").first()).toHaveText("Not yet supported");
  await expect(cutout).toHaveAttribute("data-blocking", "true");
});

test("7SL87 is not ready, lists every genuine blocker at once, and offers no Apply", async ({ page }) => {
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "not_ready");
  await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);
  const reasons = page.locator("#wwRelayReviewBlocking");
  await expect(reasons.locator("> li")).toHaveCount(4);
  await expect(reasons).toContainText("The zone delay is unresolved");
  await expect(reasons).toContainText("its resistive boundary is documented, but the current engine cannot represent that boundary exactly");
  await expect(reasons).toContainText("Left Resistive Reach");
  await expect(reasons).toContainText("what the setting does is not yet verified");      // the load cutout's effect
  await expect(reasons).not.toContainText("Characteristic type is unresolved");
  await expect(page.locator("#wwRelayImportSummary")).toContainText(/\d+ documented relay behaviour/);
});
