// REL511 under DEC-198 through the unchanged generic review UI.
//
// Documented relay behaviour (ABB 1MDB06309-YN, verified) replaces the artificial "Missing" characteristic and loop
// blockers; the genuine unknowns stay visible and blocking: the impedance basis and the RFZn conversion (not yet
// verified), ZnBlock = On on the enabled zone, and the left / directional boundary (no 0.00 ohm offer). Not ready,
// no Apply. The sheet is synthetic (the owner's real sheet is never committed). Nothing here uses a REL511-specific
// selector. Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { rel511Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  await openDistance(page);
  await pick(page, "document.pdf", rel511Pdf());
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

test("characteristic and fault loops read as documented relay behaviour, cited to the ABB reference", async ({ page }) => {
  await expect(chip(page, "zone.Z1.characteristic")).toHaveText("Documented relay behaviour");
  await expect(row(page, "zone.Z1.characteristic")).toContainText("Quadrilateral");
  for (const key of ["zone.Z1.pp_enabled", "zone.Z1.pe_enabled"]) {
    await expect(chip(page, key)).toHaveText("Documented relay behaviour");
    await expect(row(page, key)).toContainText("Enabled");
  }
  await source(page, "zone.Z1.characteristic").click();
  const char = row(page, "zone.Z1.characteristic");
  await expect(char).toContainText("Reference: Line distance protection terminal REL 511");
  await expect(char).toContainText("1MDB06309-YN");
  await expect(char).toContainText("Fig. 1 · p. 2-3");
  await expect(char).toContainText("— verified");
  await expect(char).toContainText("not on a confirmed firmware-version match");
  // a switched-off zone has no such selector: "Not a relay setting", never "Source value missing"
  await expect(chip(page, "zone.Z2.characteristic")).toHaveText("Not a relay setting");
  await expect(chip(page, "zone.Z2.pp_enabled")).toHaveText("Not a relay setting");
});

test("basis, RFZn conversion and ZnBlock = On stay visible as not yet verified, and block", async ({ page }) => {
  await expect(chip(page, "basis")).toHaveText("Not yet supported");
  await expect(row(page, "basis")).toHaveAttribute("data-blocking", "true");
  await source(page, "basis").click();
  await expect(row(page, "basis")).toContainText("has not yet been verified");

  const rf = row(page, "zone.Z1.rr.pp");
  await expect(chip(page, "zone.Z1.rr.pp")).toHaveText("Not yet supported");
  await expect(rf).toHaveAttribute("data-blocking", "true");
  await source(page, "zone.Z1.rr.pp").click();
  await expect(rf).toContainText("RFZ1");                                     // the source setting exists ...
  await expect(rf).toContainText("4.6");
  await expect(rf).toContainText("conversion to the plotted resistive boundary"); // ... its conversion is not verified

  const block = rawRow(page, "Z1Block");
  await expect(block.locator(".ww-rr-status").first()).toHaveText("Not yet supported");
  await expect(block).toHaveAttribute("data-blocking", "true");
  const offBlock = rawRow(page, "Z2Block");
  await expect(offBlock).toHaveAttribute("data-blocking", "false");           // Off on a switched-off zone: no blocker
});

test("the left boundary is not yet supported and is never offered as 0.00 Ω", async ({ page }) => {
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Not yet supported");
  await expect(row(page, "zone.Z1.rr.reverse").getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
  await expect(panel(page).getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
});

test("REL511 is not ready, lists every genuine blocker at once, and offers no Apply", async ({ page }) => {
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "not_ready");
  await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);
  const reasons = page.locator("#wwRelayReviewBlocking");
  await expect(reasons.locator("> li")).toHaveCount(4);
  await expect(reasons).toContainText("has not yet been verified for this relay");
  await expect(reasons).toContainText("its conversion to the plotted resistive boundary has not yet been verified");
  await expect(reasons).toContainText("what the setting does is not yet verified");      // ZnBlock: not an engine limit
  await expect(reasons).not.toContainText("Characteristic type is unresolved");
  await expect(reasons).not.toContainText("Only a phase-earth resistive reach");
  await expect(page.locator("#wwRelayImportSummary")).toContainText(/\d+ documented relay behaviour/);
});
