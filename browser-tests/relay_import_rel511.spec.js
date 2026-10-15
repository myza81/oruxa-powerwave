// REL511 under DEC-198 through the unchanged generic review UI.
//
// Documented relay behaviour (ABB 1MDB06309-YN; ABB REL 511 2.3 / 2.5 manuals, verified) replaces the artificial
// "Missing" characteristic and loop blockers and the unverified basis / RFNZn: Secondary basis, RFNZn as printed
// (phase-earth, ohm/loop). RFZn's documented inclined boundary is "not yet supported" by the engine (an engine limit,
// not an unknown); ZnBlock = On on the enabled zone stays not yet verified; the left / directional boundary has no
// 0.00 ohm offer. Not ready, no Apply. The sheet is synthetic (the owner's real sheet is never committed). Nothing here uses a REL511-specific
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

test("the basis and RFNZn read as documented relay behaviour, cited to the ABB REL 511 manuals", async ({ page }) => {
  await expect(chip(page, "basis")).toHaveText("Documented relay behaviour");
  await expect(row(page, "basis")).toContainText("Secondary");
  await expect(row(page, "basis")).toHaveAttribute("data-blocking", "false");
  await source(page, "basis").click();
  await expect(row(page, "basis")).toContainText("1MRK 506 109-UEN");
  await expect(row(page, "basis")).toContainText("Not inferred from the CT / VT ratios");

  const pe = row(page, "zone.Z1.rr.pe");
  await expect(chip(page, "zone.Z1.rr.pe")).toHaveText("Documented relay behaviour");
  await expect(pe).toContainText("15");
  await expect(pe).toHaveAttribute("data-blocking", "false");
  await source(page, "zone.Z1.rr.pe").click();
  await expect(pe).toContainText("not converted into a phase-phase reach");
});

test("RFZn is documented but not yet supported by the engine; ZnBlock = On stays not yet verified; both block", async ({ page }) => {
  const rf = row(page, "zone.Z1.rr.pp");
  await expect(chip(page, "zone.Z1.rr.pp")).toHaveText("Not yet supported");
  await expect(rf).toHaveAttribute("data-blocking", "true");
  await source(page, "zone.Z1.rr.pp").click();
  await expect(rf).toContainText("RFZ1");                                     // the source setting is preserved ...
  await expect(rf).toContainText("4.6");
  await expect(rf).toContainText("Rright(X) = R1Z1 * X / X1Z1 + RFZ1 / 2");   // ... with its documented boundary
  await expect(rf).toContainText("1MRK 506 109-UEN");
  await expect(rf).not.toContainText("has not yet been verified");

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
  await expect(reasons.locator("> li")).toHaveCount(3);
  await expect(reasons).toContainText("its resistive boundary is documented, but the current engine cannot represent that boundary exactly");
  await expect(reasons).not.toContainText("has not yet been verified");               // neither the basis nor RFZn
  await expect(reasons).toContainText("what the setting does is not yet verified");      // ZnBlock: not an engine limit
  await expect(reasons).not.toContainText("Characteristic type is unresolved");
  await expect(reasons).not.toContainText("Only a phase-earth resistive reach");
  await expect(page.locator("#wwRelayImportSummary")).toContainText(/\d+ documented relay behaviour/);
});
