// Copy cleanup: the Zone P explanation is spaced like the rest of the review card, and nothing
// the review shows (including the accepted suggestion's provenance) names the product.
// Runs against LOCAL code.

const { test, expect } = require("./support/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const LEFT = "Left Resistive Reach (−R)";

async function review(page) {
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

for (const [name, width] of [["desktop", 1280], ["narrow", 400]]) {
  test(`Zone P note keeps clear of the card edges, the divider and the first row (${name})`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await review(page);
    const group = panel(page).locator('details[data-group="zone-ZP"]');
    await group.locator("> summary").click();
    const note = group.locator(".ww-rr-state-note");
    await expect(note).toHaveText(
      "Zone status was not explicitly decoded. The 10.0 s operating delay is interpreted as a defeated/inactive distance zone. Its extracted settings are kept for reference.",
    );
    const m = await page.evaluate(() => {
      const g = document.querySelector('#wwRelayReviewPanel details[data-group="zone-ZP"]');
      const note = g.querySelector(".ww-rr-state-note");
      const first = g.querySelector(".ww-rr-items li");
      const summary = g.querySelector(":scope > summary");
      const gb = g.getBoundingClientRect(), nb = note.getBoundingClientRect();
      const cs = getComputedStyle(note);
      return {
        left: nb.left - gb.left, right: gb.right - nb.right,
        padLeft: parseFloat(cs.paddingLeft), padTop: parseFloat(cs.paddingTop),
        gapAbove: nb.top - summary.getBoundingClientRect().bottom,
        gapBelow: first.getBoundingClientRect().top - nb.bottom,
        overflow: note.scrollWidth - note.clientWidth,
      };
    });
    expect(m.padLeft).toBeGreaterThanOrEqual(8);
    expect(m.padTop).toBeGreaterThanOrEqual(4);
    expect(m.left).toBeGreaterThanOrEqual(0);
    expect(m.right).toBeGreaterThanOrEqual(0);
    expect(m.gapAbove).toBeGreaterThanOrEqual(0);
    expect(m.gapBelow).toBeGreaterThanOrEqual(0);
    expect(m.overflow).toBeLessThanOrEqual(1);
  });
}

test("the review and an accepted suggestion's provenance carry no product name", async ({ page }) => {
  await review(page);
  expect(await panel(page).innerText()).not.toMatch(/oruxa/i);
  await panel(page).locator(`button[aria-label="Use 0.00 Ω for Zone 1 ${LEFT}"]`).click();
  const row = panel(page).locator('li[data-key="zone.Z1.rr.reverse"]');
  await row.getByRole("button", { name: /^Source of/ }).click();
  await expect(row).toContainText("Suggested value: 0.00 Ω");
  expect(await panel(page).innerText()).not.toMatch(/oruxa/i);
  expect(await page.locator("#wwDistancePanel").innerText()).not.toMatch(/oruxa/i);
});
