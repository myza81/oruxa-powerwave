// Distance Protection UX fix -- quadrilateral resistive-reach terminology and the
// explicit, non-authoritative "0.00 Ω" suggestion for a missing Left Resistive
// Reach (−R). Runs against LOCAL code.
//
// * Manual form: only the labels change (Right (+R) / Left (−R)); the old
//   Forward/Reverse resistive wording is gone, the Reverse Zone keeps its name,
//   and the left-hand field is never prefilled.
// * Relay review: the imported P441 sheet states no left-hand reach, so it is
//   Missing and blocking. a 0.00 Ω value is offered; nothing is applied until the user
//   chooses "Use 0.00 Ω". The accepted suggestion keeps the Missing cause visible,
//   is not a source/profile value, and Clear restores Missing / blocking.

const { test, expect } = require("@playwright/test");
const { p441Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();
const LEFT = "Left Resistive Reach (−R)";
const readiness = (page) => page.locator("#wwRelayReviewReadiness");

async function reviewP441(page) {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

test("manual form: Right (+R) / Left (−R) labels in every zone, no Forward/Reverse resistive wording, left never prefilled", async ({ page }) => {
  await openDistance(page);
  await page.locator("#wwDistanceCharacteristicSelect").selectOption("quadrilateral");
  for (const n of [1, 2, 3, 4]) {
    const right = page.locator(`#wwDistanceZone${n}ResistiveForwardField`);
    const left = page.locator(`#wwDistanceZone${n}ResistiveReverseField`);
    await expect(right).toContainText("Right Resistive Reach (+R)");
    await expect(left).toContainText("Left Resistive Reach (−R)");
    await expect(right).toHaveAttribute("title", "Right-hand resistive boundary of the quadrilateral.");
    await expect(left).toHaveAttribute("title", /does not mean the zone is reverse-directional/);
    await expect(right).not.toContainText(/forward/i);
    await expect(left).not.toContainText(/reverse/i);
    // Engineering defaults are unchanged: the Reverse Zone slot stays blank (no prefill).
    if (n === 4) await expect(page.locator("#wwDistanceZone4ResistiveReverseInput")).toHaveValue("");
  }
  // A genuine Reverse Zone keeps its name.
  await expect(page.locator("#wwDistancePanel")).toContainText(/Reverse Zone/);
  // The old field labels do not appear anywhere in the Distance panel.
  const text = await page.locator("#wwDistancePanel").innerText();
  expect(text).not.toMatch(/Resistive reach (forward|reverse)/i);
  expect(text).not.toMatch(/(Forward|Reverse) Resistive Reach/i);
});

test("review: the missing left reach is Missing, blocking, and offers 0.00 Ω without applying it", async ({ page }) => {
  await reviewP441(page);
  const z1 = row(page, "zone.Z1.rr.reverse");
  await expect(z1.locator(".ww-rr-label")).toHaveText(LEFT);
  await expect(z1.locator(".ww-rr-label")).toHaveAttribute("title", /does not mean the zone is reverse-directional/);
  await expect(z1).toHaveAttribute("data-category", "missing");
  await expect(z1).toHaveAttribute("data-blocking", "true");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  await expect(z1.locator(".ww-rr-value")).toHaveText("Not available");
  await expect(z1.locator(".ww-rr-offer")).toContainText("This value was not found in the relay setting file.");
  await expect(z1.locator(".ww-rr-offer")).toContainText("Suggested for visualization: 0.00 Ω");
  await expect(button(page, "Use 0.00 Ω for Zone 1 " + LEFT)).toHaveText("Use 0.00 Ω");
  await expect(row(page, "zone.Z1.rr.reverse").locator("button.ww-rr-btn", { hasText: "Enter manually" })).toHaveCount(1);
  await expect(readiness(page)).toContainText("Not ready");
  // The old wording is gone from the review.
  await expect(panel(page)).not.toContainText(/Reverse Resistive Reach/i);
});

test("review: the suggestion is offered only for the left reach, never for Zone P or other missing items", async ({ page }) => {
  await reviewP441(page);
  const offers = panel(page).locator(".ww-rr-offer:visible");
  for (const key of ["zone.ZP.status", "relay.version", "base.voltage"]) {
    await expect(row(page, key).locator(".ww-rr-offer")).toBeHidden();
    await expect(row(page, key).getByRole("button", { name: /^Use / })).toHaveCount(0);
  }
  for (const text of await offers.allInnerTexts()) expect(text).toContain("0.00 Ω");
  // Only the left-reach rows a function needs (Zones 1-3) carry an offer; Zones 4 and P are
  // defeated (10 s delay), so their Left Resistive Reach is not required.
  await expect(panel(page).getByRole("button", { name: /^Use / })).toHaveCount(3);
});

test("review: accepting the suggestion resolves it as Suggested, keeps Missing in the Source, and Clear restores it", async ({ page }) => {
  await reviewP441(page);
  const key = "zone.Z1.rr.reverse";
  await button(page, "Use 0.00 Ω for Zone 1 " + LEFT).click();
  await expect(chip(page, key)).toHaveText("Resolved · Suggested");
  await expect(row(page, key)).toHaveAttribute("data-review", "resolved_manually");
  await expect(row(page, key)).toHaveAttribute("data-blocking", "false");
  await expect(row(page, key).locator(".ww-rr-value")).toContainText("0");
  await expect(row(page, key).locator(".ww-rr-offer")).toBeHidden();
  await button(page, "Source of Zone 1 " + LEFT).click();
  const prov = row(page, key).locator(".ww-rr-prov");
  await expect(prov).toContainText("Suggested value: 0.00 Ω");
  await expect(prov).toContainText("accepted by you");
  await expect(prov).toContainText("Source value: unavailable / missing");
  await expect(prov).toContainText("Classified as: Missing");
  await expect(prov).toContainText("the relay's setting, and not mapped from a profile");
  await expect(prov).not.toContainText("User resolution");
  // Clear returns to Missing / blocking and offers the suggestion again.
  await button(page, "Clear the value of Zone 1 " + LEFT).click();
  await expect(chip(page, key)).toHaveText("Missing");
  await expect(row(page, key)).toHaveAttribute("data-blocking", "true");
  await expect(row(page, key).locator(".ww-rr-offer")).toBeVisible();
});

test("review: accepting all three suggestions clears the blockers; the backend decides readiness", async ({ page }) => {
  await reviewP441(page);
  await expect(readiness(page)).toContainText("Not ready");
  for (const n of ["1", "2", "3"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await expect(row(page, "zone.Z3.rr.reverse")).toHaveAttribute("data-blocking", "false");
  await expect(readiness(page)).toContainText("Ready after confirmation"); // Zone P is an inferred Disabled, not a blocker
});

test("review: a typed 0 stays a manual resolution, distinct from the accepted suggestion", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Resolve Zone 1 " + LEFT).click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  await form.locator("input").fill("0");
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Resolved manually");
  await button(page, "Use 0.00 Ω for Zone 2 " + LEFT).click();
  await expect(chip(page, "zone.Z2.rr.reverse")).toHaveText("Resolved · Suggested");
  await button(page, "Source of Zone 1 " + LEFT).click();
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-prov")).toContainText("User resolution: 0 Ω");
});

test("review: choosing Enter manually and typing a value replaces an accepted suggestion", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Use 0.00 Ω for Zone 1 " + LEFT).click();
  await button(page, "Edit the value of Zone 1 " + LEFT).click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  await form.locator("input").fill("2.5");
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Resolved manually");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-value")).toContainText("2.5");
});

const summaryCounts = (page) =>
  page.locator("#wwRelayReviewSummary .ww-rr-counts").evaluate((el) => {
    const out = {};
    el.querySelectorAll(".ww-rr-status").forEach((c) => {
      const m = c.textContent.match(/^(\d+) (.+)$/);
      if (m) out[m[2]] = Number(m[1]);
    });
    return out;
  });

test("review: three accepted 0.00 Ω suggestions show 3 suggested and no resolved manually", async ({ page }) => {
  await reviewP441(page);
  for (const n of ["1", "2", "3"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-status[data-status='suggested']")).toHaveText("3 suggested");
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-status[data-status='resolved']")).toHaveCount(0);
  await expect(page.locator("#wwRelayImportSummary")).toContainText("3 suggested");
  await expect(page.locator("#wwRelayImportSummary")).not.toContainText("resolved manually");
});

test("review: typed and suggested resolutions are counted separately, and Clear updates the right counter", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Resolve Zone 1 " + LEFT).click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  await form.locator("input").fill("2.5");
  await form.getByRole("button", { name: "Set value" }).click();
  for (const n of ["2", "3"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  
  await expect.poll(async () => { const c = await summaryCounts(page); return [c["resolved manually"], c.suggested]; }).toEqual([1, 2]);
  await button(page, "Clear the value of Zone 2 " + LEFT).click();
  await expect.poll(async () => { const c = await summaryCounts(page); return [c["resolved manually"], c.suggested]; }).toEqual([1, 1]);
  await button(page, "Clear the value of Zone 1 " + LEFT).click();
  await expect.poll(async () => { const c = await summaryCounts(page); return [c["resolved manually"], c.suggested]; }).toEqual([undefined, 1]);
});

test("review: Ready explanation names the required active settings while non-blocking Missing/Unsupported remain", async ({ page }) => {
  await reviewP441(page);
  for (const n of ["1", "2", "3"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toContainText("Ready to apply");
  await expect(readiness(page)).toContainText("required active setting");
  await expect(readiness(page)).not.toContainText("Every value");
  const c = await summaryCounts(page);
  expect((c.missing || 0) + (c.unsupported || 0)).toBeGreaterThan(0); // non-blocking leftovers coexist with Ready
});

test("review: accepting the suggestion applies nothing to the manual Distance Protection form", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Use 0.00 Ω for Zone 1 " + LEFT).click();
  await expect(page.locator("#wwDistanceZone1ResistiveReverseInput")).toHaveValue("");
});
