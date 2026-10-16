// GRZ100 under DEC-198 (Amendment 7) through the unchanged generic review UI.
//
// Documented relay behaviour (Toshiba GRZ100 manual 6F2S0834-0 / brochure 6641-1, version-dependent) replaces the
// artificial "Missing" basis, direction and loop blockers; ZS-C / ZG-C stay exact configured selectors. The relay runs a
// site-specific PLC program, so no zone is Enabled or Disabled: its trip state is "not yet verified" (nothing to enter)
// while its configured geometry is still shown. The 75° right blinder, the polarised left boundary, the reverse zones'
// forward offset, the non-directional ZND and Zone 4 (command protection only) are not yet supported; no 0.00 Ω offer.
// Not ready, no Apply. The sheet is synthetic (the owner's real sheet is never committed). Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { grz100Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  await openDistance(page);
  await pick(page, "document.pdf", grz100Pdf({ zgC: "Quad" }));
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
const rawRow = (page, zone, name) => panel(page).locator(`li[data-key^="zone.${zone}.raw."]`, { hasText: name }).first();
const source = (page, key) => row(page, key).getByRole("button", { name: /Source/ }).first();

test("basis, directions and loops read as documented relay behaviour, cited to the Toshiba manual", async ({ page }) => {
  for (const key of ["basis", "zone.Z1.direction", "zone.ZR2.direction", "zone.Z1.pp_enabled", "zone.Z1.pe_enabled"]) {
    await expect(chip(page, key)).toHaveText("Documented relay behaviour");
    await expect(row(page, key)).toHaveAttribute("data-blocking", "false");
  }
  await expect(row(page, "basis")).toContainText("Secondary");
  await expect(row(page, "zone.ZR2.direction")).toContainText("Reverse");
  await source(page, "zone.Z1.direction").click();
  await expect(row(page, "zone.Z1.direction")).toContainText("6F2S0834-0");
  await expect(row(page, "zone.Z1.direction")).toContainText("Version-dependent");
  await expect(chip(page, "zone.Z1.characteristic")).toHaveText("Mapped");          // ZS-C / ZG-C: configured selectors
  await expect(row(page, "zone.Z1.x_reach")).toContainText("5.72 Ω");
});

test("each zone's trip state is not verified (site PLC) while its geometry is shown; nothing to enter", async ({ page }) => {
  await expect(chip(page, "zone.Z2.status")).toHaveText("Not yet supported");
  await expect(row(page, "zone.Z2.status")).toHaveAttribute("data-blocking", "true");
  await expect(row(page, "zone.Z2.status").locator("input, select")).toHaveCount(0);
  await expect(row(page, "zone.Z2.status")).not.toContainText("Source value missing");
  const header = panel(page).locator('details[data-group="zone-Z2"] > summary');
  await expect(header).not.toContainText("Enabled");                                   // no state invented
  await expect(header).not.toContainText("Disabled");
  await expect(row(page, "zone.Z2.x_reach")).toContainText("7.4 Ω");
  await expect(row(page, "zone.Z2.timer.pp")).toContainText("0.3 s");
  await expect(page.locator("#wwRelayReviewBlocking")).toContainText("depends on relay logic that is not verified");
});

test("BFRS, the left boundary and the reverse offset are not yet supported; no 0.00 Ω offer", async ({ page }) => {
  await expect(chip(page, "zone.Z1.rr.pp")).toHaveText("Not yet supported");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Not yet supported");
  await source(page, "zone.Z1.rr.pp").click();
  await expect(row(page, "zone.Z1.rr.pp")).toContainText("Rright(X) = BFRS + X * cot 75 deg");
  await expect(panel(page).getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
  const offset = rawRow(page, "ZR2", "ZR2BT");
  await expect(offset.locator(".ww-rr-status").first()).toHaveText("Not yet supported");
  await expect(offset).toHaveAttribute("data-blocking", "true");
  await expect(chip(page, "zone.ZND.direction")).toHaveText("Not yet supported");
  await expect(row(page, "zone.ZND.direction")).toContainText("Non directional");
  await expect(row(page, "zone.Z1.tilt")).toContainText("0°");                           // Z1S-angle1 0: exact
  await expect(chip(page, "zone.Z1.tilt")).toHaveText("Mapped");
});

test("Zone 4 is kept as a command-protection element and not drawn; the relay is not ready and offers no Apply", async ({ page }) => {
  await expect(chip(page, "zone.Z4.status")).toHaveText("Not yet supported");
  await expect(row(page, "zone.Z4.direction")).toContainText("Reverse");
  await expect(chip(page, "zone.Z4.timer.pp")).toHaveText("Not a relay setting");
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "not_ready");
  await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);
  const reasons = page.locator("#wwRelayReviewBlocking");
  await expect(reasons).toContainText("not a tripping zone");
  await expect(reasons).not.toContainText("basis");
  await expect(reasons).not.toContainText("Phase-phase operation is not established");
});
