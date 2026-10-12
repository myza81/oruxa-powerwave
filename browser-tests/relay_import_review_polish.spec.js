// Relay import UI polish: card status border (blocking > issue > clear), vertical action
// stack, compact typography and the findings-card hierarchy. Presentation only: the card
// colour is derived from the backend's review summary, never from the file or relay.

const { test, expect } = require("@playwright/test");
const { p441Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const card = (page) => page.locator("#wwRelayImportFile");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const LEFT = "Left Resistive Reach (−R)";

async function reviewP441(page) {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
}

async function resolveBlockers(page) {
  for (const n of ["1", "2", "3"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator('#wwRelayReviewPanel button[aria-label="Resolve Zone P Status"]').click();
  const form = row(page, "zone.ZP.status").locator("form.ww-rr-resolve");
  await form.locator("select").selectOption("disabled");
  await form.getByRole("button", { name: "Set value" }).click();
}

const borderColor = (page) => card(page).evaluate((el) => getComputedStyle(el).borderLeftColor);

test("card is red while any setting blocks, amber with only non-blocking issues, and red wins", async ({ page }) => {
  await reviewP441(page);
  await expect(card(page)).toHaveAttribute("data-review", "blocking"); // blocking AND non-blocking issues exist
  const red = await borderColor(page);
  await resolveBlockers(page);
  await expect(page.locator("#wwRelayReviewReadiness")).toContainText("Ready after confirmation");
  await expect(card(page)).toHaveAttribute("data-review", "issue"); // missing/unsupported remain, none blocking
  const amber = await borderColor(page);
  expect(amber).not.toBe(red);
  // Clearing one suggestion makes a setting block again: precedence returns to red.
  await button(page, `Clear the value of Zone 1 ${LEFT}`).click();
  await expect(card(page)).toHaveAttribute("data-review", "blocking");
  expect(await borderColor(page)).toBe(red);
});

test("card is green only when the backend reports nothing blocking and nothing outstanding", async ({ page }) => {
  // A clean authoritative answer is substituted for the real one; the card must follow it.
  await page.route("**/api/v1/relay-import/review/validate", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    Object.assign(body, {
      to_confirm_count: 0, assumption_count: 0, missing_count: 0, conflict_count: 0, unsupported_count: 0,
      unreadable_count: 0, unresolved_count: 0, blocking_count: 0,
      readiness: { status: "ready", pending_confirmations: 0, blocking_unresolved: 0 },
      engine: { status: "ready", warnings: [] },
    });
    await route.fulfill({ response, json: body });
  });
  await reviewP441(page);
  await expect(card(page)).toHaveAttribute("data-review", "blocking");
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(card(page)).toHaveAttribute("data-review", "clear");
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("Review and Remove are a vertical stack, Review primary and Remove secondary", async ({ page }) => {
  await reviewP441(page);
  const review = await page.locator("#wwRelayReviewBtn").boundingBox();
  const remove = await page.locator("#wwRelayImportRemoveBtn").boundingBox();
  expect(remove.y).toBeGreaterThanOrEqual(review.y + review.height - 1);
  expect(Math.abs(remove.x - review.x)).toBeLessThan(2);
  expect(Math.abs(remove.width - review.width)).toBeLessThan(2);
  await expect(page.locator("#wwRelayImportRemoveBtn")).toHaveClass(/secondary/);
  await expect(page.locator("#wwRelayReviewBtn")).not.toHaveClass(/secondary/);
  const cardBox = await card(page).boundingBox();
  expect(review.x + review.width).toBeGreaterThan(cardBox.x + cardBox.width - 24); // right side
});

test("findings card order is header, statuses, explanation, action; secondary info stays quiet", async ({ page }) => {
  await reviewP441(page);
  const box = page.locator("#wwRelayReviewSummary");
  await expect(page.locator("#wwRelayReviewReadiness")).toContainText("Not ready"); // initial validation settled
  const top = await page.evaluate(() => {
    const at = (sel) => document.querySelector("#wwRelayReviewSummary " + sel).getBoundingClientRect().top;
    return { identity: at(".ww-rr-identity"), counts: at(".ww-rr-counts"), explain: at(".ww-rr-explain"), bulk: at(".ww-rr-bulk") };
  });
  const { identity, counts, explain, bulk } = top;
  expect(identity).toBeLessThan(counts);
  expect(counts).toBeLessThan(explain);
  expect(explain).toBeLessThan(bulk);
  // The bulk action is not in the chip row; the secondary "not interpreted" count is not a chip.
  await expect(box.locator(".ww-rr-counts #wwRelayReviewConfirmAll")).toHaveCount(0);
  await expect(box.locator(".ww-rr-counts")).not.toContainText("not interpreted");
  await expect(box.locator(".ww-rr-identity + .ww-rr-dim")).toContainText("not interpreted");
  await expect(box.locator(".ww-rr-counts")).toContainText("4 blocking");
  await expect(box.locator(".ww-rr-explain")).toContainText("Assumption = source value was read");
  await expect(box.locator(".ww-rr-bulk")).toContainText("Only Assumption items are affected.");
  // Detailed wording is unchanged.
  await expect(page.locator("#wwRelayReviewReadiness")).toContainText("Blocking settings: 4");
  await expect(page.locator("#wwRelayReviewEngine .ww-rr-sub")).toHaveText("Blocking reasons (2)");
});

test(".ww-rr-dim is 0.65rem and the overcurrent-style zoom button 0.6rem", async ({ page }) => {
  await reviewP441(page);
  const sizes = await page.evaluate(() => {
    const root = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const dim = parseFloat(getComputedStyle(document.querySelector(".ww-rr-dim")).fontSize);
    const zoom = parseFloat(getComputedStyle(document.querySelector("#wwDistanceFitZonesBtn")).fontSize);
    return { root, dim, zoom };
  });
  expect(sizes.dim).toBeCloseTo(sizes.root * 0.65, 1);
  expect(sizes.zoom).toBeCloseTo(sizes.root * 0.6, 1);
});

test("narrow layout keeps the stack usable with no horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openDistance(page);
  await pick(page, "a-very-long-relay-settings-file-name-that-must-truncate-safely-2026-10-12-final-v3.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
  for (const id of ["#wwRelayReviewBtn", "#wwRelayImportRemoveBtn"]) {
    const b = await page.locator(id).boundingBox();
    expect(b.x).toBeGreaterThanOrEqual(0);
    expect(b.x + b.width).toBeLessThanOrEqual(390);
  }
  await expect(page.locator("#wwRelayReviewBtn")).toHaveText("Review Extracted Settings");
  const review = await page.locator("#wwRelayReviewBtn").boundingBox();
  const remove = await page.locator("#wwRelayImportRemoveBtn").boundingBox();
  expect(remove.y).toBeGreaterThan(review.y);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const name = page.locator("#wwRelayImportFilename");
  expect(await name.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true); // truncated, not wrapped
  const counts = await page.locator("#wwRelayReviewSummary .ww-rr-counts").boundingBox();
  expect(counts.x + counts.width).toBeLessThanOrEqual(390);
});
