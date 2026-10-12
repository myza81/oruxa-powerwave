// Pre-Slice-9 -- settings of a disabled zone do not block readiness, and an optional
// Zone P that is genuinely absent from a readable relay sheet defaults to Disabled as
// an Assumption (DEC-186). Runs against LOCAL code.
//
// * Zone 4 is defeated in the sample sheet: its missing Left Resistive Reach stays
//   visible as Missing, reads "Not required while zone is disabled", is not Blocking
//   and is offered no 0.00 Ω suggestion.
// * Zone P with settings but no decoded state is NOT defaulted: it stays Missing and
//   blocking. Resolving it as Disabled makes its own missing values not required.
// * A sheet with no Zone P at all assumes it disabled: an Assumption (not Mapped), with
//   helper text, nothing to confirm, and no blocker.

const { test, expect } = require("@playwright/test");
const { p441Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();
const zoneP = (page) => page.locator('#wwRelayReviewPanel details[data-group="zone-ZP"]');
const NOT_REQUIRED = "Not required while zone is disabled";

async function review(page, options) {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf(options));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

test("a defeated zone's missing Left Resistive Reach is visible, not required, not blocking and has no suggestion", async ({ page }) => {
  await review(page);
  const z4 = row(page, "zone.Z4.rr.reverse");
  await expect(z4).toHaveAttribute("data-category", "missing");
  await expect(z4).toHaveAttribute("data-blocking", "false");
  await expect(z4).toHaveAttribute("data-not-required", "true");
  await expect(chip(page, "zone.Z4.rr.reverse")).toHaveText("Missing");
  await expect(z4.locator(".ww-rr-notreq")).toContainText(NOT_REQUIRED);
  await expect(z4.locator(".ww-rr-blocking")).toHaveCount(0);
  await expect(z4.locator(".ww-rr-offer")).toBeHidden();
  await expect(z4.getByRole("button", { name: /^Use / })).toHaveCount(0);
  // An enabled zone is unchanged: still required, blocking, and offered the suggestion.
  const z1 = row(page, "zone.Z1.rr.reverse");
  await expect(z1).toHaveAttribute("data-blocking", "true");
  await expect(z1).toHaveAttribute("data-not-required", "false");
  await expect(z1.locator(".ww-rr-offer")).toContainText("0.00 Ω");
  await expect(z1.locator(".ww-rr-notreq")).toHaveCount(0);
});

test("Zone P with settings but no decoded state is not defaulted: Missing and blocking until resolved", async ({ page }) => {
  await review(page);
  await expect(zoneP(page).locator("> summary")).toContainText("Status missing");
  await expect(zoneP(page)).not.toContainText("was not found in the uploaded relay settings");
  await expect(row(page, "zone.ZP.status")).toHaveAttribute("data-blocking", "true");
  await expect(chip(page, "zone.ZP.status")).toHaveText("Missing");
});

test("an absent Zone P is assumed Disabled: an Assumption with helper text, nothing to confirm, not blocking", async ({ page }) => {
  await review(page, { drop: ["301D", "3020", "3023"] });
  await expect(zoneP(page).locator("> summary")).toContainText("Zone P — Disabled · Assumption");
  await expect(zoneP(page).locator(".ww-rr-state-note")).toHaveText(
    "Zone P was not found in the uploaded relay settings. Oruxa assumes this optional zone is disabled.",
  );
  const status = row(page, "zone.ZP.status");
  await expect(status).toHaveAttribute("data-category", "assumption");
  await expect(status).toHaveAttribute("data-review", "assumed");
  await expect(status).toHaveAttribute("data-blocking", "false");
  await expect(chip(page, "zone.ZP.status")).toHaveText("Assumption");
  await expect(status.locator(".ww-rr-value")).toHaveText("Disabled");
  // It is not the relay file's own statement, and there is nothing for the user to confirm.
  await expect(status.getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  await expect(status.getByRole("button", { name: /^Resolve|^Enter/ })).toHaveCount(0);
  await status.getByRole("button", { name: "Source of Zone P Status" }).click();
  await expect(status).toContainText("Assumption: Zone P not found in uploaded relay settings");
  await expect(status).not.toContainText(/Defeated/);
  // The zone's own missing values stay visible but are not required.
  for (const key of ["zone.ZP.reach", "zone.ZP.timer"]) {
    await expect(row(page, key)).toHaveAttribute("data-not-required", "true");
    await expect(row(page, key)).toHaveAttribute("data-blocking", "false");
    await expect(row(page, key).locator(".ww-rr-notreq")).toContainText(NOT_REQUIRED);
  }
  // No Zone P blocker remains: only the enabled zones' Left Resistive Reach is open.
  await expect(page.locator("#wwRelayReviewBlocking")).not.toContainText("ZP");
});
