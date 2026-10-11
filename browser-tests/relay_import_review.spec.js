// Relay Import Slice 8 -- Review Confirmation / Resolution, in a real browser.
//
// The owner can confirm inferred values and resolve (or leave) unresolved ones
// for this import session; the backend re-validates after every change, so the
// counts, blocking issues and readiness shown here are its answer. Nothing is
// applied: there is no Apply control, the manual Distance Protection form is
// never touched, and every decision disappears with Remove, a new upload or a
// refresh. Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { p441Pdf, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();

async function reviewP441(page) {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

// {mapped, "to confirm", confirmed, ...} from the summary chips.
async function counts(page) {
  return page.locator("#wwRelayReviewSummary .ww-rr-counts").evaluate((el) => {
    const out = {};
    el.querySelectorAll(".ww-rr-status").forEach((c) => {
      const m = c.textContent.match(/^(\d+) (.+)$/);
      if (m) out[m[2]] = Number(m[1]);
    });
    const blocking = el.querySelector(".ww-rr-blocking");
    out.blocking = blocking ? Number(blocking.textContent.match(/\d+/)[0]) : 0;
    return out;
  });
}
const readiness = (page) => page.locator("#wwRelayReviewReadiness");

// Resolve a numeric item through its inline editor.
async function resolveNumber(page, key, label, value) {
  await button(page, `Resolve ${label}`).click();
  const form = row(page, key).locator("form.ww-rr-resolve");
  await expect(form).toBeVisible();
  await form.locator("input").fill(String(value));
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form).toBeHidden();
}
async function resolveZoneP(page, choice) {
  // "Resolve" the first time, "Edit" once the user has already answered.
  await page.locator('#wwRelayReviewPanel button[aria-label="Resolve Zone P Status"], #wwRelayReviewPanel button[aria-label="Edit the value of Zone P Status"]').click();
  const form = row(page, "zone.ZP.status").locator("form.ww-rr-resolve");
  await form.locator("select").selectOption(choice);
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form).toBeHidden();
}
async function resolveAllBlockers(page, zoneP = "disabled") {
  for (const [z, n] of [["Z1", "Zone 1"], ["Z2", "Zone 2"], ["Z3", "Zone 3"]]) {
    await resolveNumber(page, `zone.${z}.rr.reverse`, `${n} Reverse Resistive Reach`, 2.5);
  }
  await resolveZoneP(page, zoneP);
}

test("Confirm appears only on inferred rows; mapped rows have none", async ({ page }) => {
  await reviewP441(page);
  await expect(row(page, "ct.primary")).toHaveAttribute("data-review", "mapped");
  await expect(row(page, "ct.primary").getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  await expect(row(page, "ct.primary").getByRole("button", { name: /^(Resolve|Edit)/ })).toHaveCount(0);
  await expect(row(page, "zone.Z1.reach")).toHaveAttribute("data-review", "to_confirm");
  await expect(button(page, "Confirm Zone 1 Reach")).toHaveCount(1);
  // a reach and its angle are one setting: the control sits on the first row only
  await expect(row(page, "zone.Z1.reach.angle")).toHaveAttribute("data-review", "to_confirm");
  await expect(row(page, "zone.Z1.reach.angle").getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  // every mapped row, everywhere, is read-only
  const bad = await panel(page).locator('li[data-review="mapped"] .ww-rr-actions button').count();
  expect(bad).toBe(0);
});

test("manual resolution is offered only where the canonical type is known", async ({ page }) => {
  await reviewP441(page);
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-review", "unresolved");
  await expect(button(page, "Resolve Zone 1 Reverse Resistive Reach")).toHaveCount(1);
  await expect(button(page, "Resolve Zone P Status")).toHaveCount(1);
  // unknown semantics stay unresolved, with a reason and no editor
  for (const key of ["base.voltage", "base.current", "relay.version", "line.z1"]) {
    await expect(row(page, key)).toHaveAttribute("data-review", "unresolved");
    await expect(row(page, key).getByRole("button", { name: /^(Resolve|Edit|Confirm)/ })).toHaveCount(0);
  }
});

test("Confirm and Undo confirmation work, and the original assumption stays visible", async ({ page }) => {
  await reviewP441(page);
  const before = await counts(page);
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await expect(chip(page, "zone.Z1.reach.angle")).toHaveText("Confirmed");
  await expect(row(page, "zone.Z1.reach")).toHaveAttribute("data-status", "inferred"); // interpretation is not rewritten
  await expect(button(page, "Undo confirmation of Zone 1 Reach")).toHaveCount(1);
  const after = await counts(page);
  expect(after["to confirm"]).toBe(before["to confirm"] - 1);
  expect(after.confirmed).toBe(1);
  expect(after.mapped).toBe(before.mapped);
  expect(after.unresolved).toBe(before.unresolved);
  // provenance keeps the profile's reasoning, now labelled as the original inference
  await row(page, "zone.Z1.reach").getByRole("button", { name: "Source of Zone 1 Reach" }).click();
  await expect(row(page, "zone.Z1.reach")).toContainText("Originally inferred because");
  await expect(row(page, "zone.Z1.reach")).toContainText("Confirmed: by you, for this import session only");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("1 confirmed");

  await button(page, "Undo confirmation of Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("To confirm");
  expect(await counts(page)).toEqual(before);
  await expect(row(page, "zone.Z1.reach")).toContainText("Assumption");
});

test("Confirm all inferred values shows its count, changes only inferred rows, and can be undone", async ({ page }) => {
  await reviewP441(page);
  const before = await counts(page);
  const all = page.locator("#wwRelayReviewConfirmAll");
  await expect(all).toHaveText(`Confirm all inferred values (${before["to confirm"]})`);
  await all.click();
  await expect(all).toHaveCount(0);
  const after = await counts(page);
  expect(after).toMatchObject({ confirmed: before["to confirm"], mapped: before.mapped, unresolved: before.unresolved, blocking: before.blocking });
  expect(after["to confirm"]).toBe(0);
  await expect(panel(page).locator('li[data-review="to_confirm"]')).toHaveCount(0);
  // unresolved rows were not touched by the bulk action
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-review", "unresolved");
  await page.locator("#wwRelayReviewUndoAll").click();
  await expect(page.locator("#wwRelayReviewUndoAll")).toHaveCount(0); // the backend has answered
  expect(await counts(page)).toEqual(before);
});

test("a manual resolution keeps the source value unavailable and shows the user's value apart", async ({ page }) => {
  await reviewP441(page);
  const before = await counts(page);
  await button(page, "Resolve Zone 1 Reverse Resistive Reach").click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  // a blank is not a value
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form.locator(".ww-rr-resolve-error")).toContainText("Enter a value");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Unresolved");
  await form.locator("input").fill("2.5");
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Resolved manually");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-value")).toHaveText("2.5 Ω");
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-status", "unresolved");
  await row(page, "zone.Z1.rr.reverse").getByRole("button", { name: "Source of Zone 1 Reverse Resistive Reach" }).click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Source value: unavailable / unresolved");
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("User resolution: 2.5 Ω");
  const after = await counts(page);
  expect(after["resolved manually"]).toBe(1);
  expect(after.unresolved).toBe(before.unresolved - 1);
  expect(after.blocking).toBe(before.blocking - 1);
  // clear returns it to unresolved, never to a default
  await button(page, "Clear the value of Zone 1 Reverse Resistive Reach").click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Unresolved");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-value")).toHaveText("Unresolved");
  expect(await counts(page)).toEqual(before);
});

test("an explicit zero is a value; leaving an item unresolved is a decision of its own", async ({ page }) => {
  await reviewP441(page);
  await resolveNumber(page, "zone.Z4.rr.reverse", "Zone 4 Reverse Resistive Reach", 0);
  await expect(row(page, "zone.Z4.rr.reverse").locator(".ww-rr-value")).toHaveText("0 Ω");
  await expect(chip(page, "zone.Z4.rr.reverse")).toHaveText("Resolved manually");

  const before = await counts(page);
  await button(page, "Resolve Zone 1 Reverse Resistive Reach").click();
  await button(page, "Leave Zone 1 Reverse Resistive Reach unresolved").click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Left unresolved");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Unresolved");
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-blocking", "true"); // still blocks
  expect(await counts(page)).toEqual(before);
  await button(page, "Undo leaving Zone 1 Reverse Resistive Reach unresolved").click();
  await expect(row(page, "zone.Z1.rr.reverse")).not.toContainText("Left unresolved");
});

test("blocking items are told apart from unresolved items that do not block", async ({ page }) => {
  await reviewP441(page);
  for (const key of ["zone.Z1.rr.reverse", "zone.Z2.rr.reverse", "zone.Z3.rr.reverse", "zone.ZP.status"]) {
    await expect(row(page, key)).toHaveAttribute("data-blocking", "true");
    await expect(row(page, key)).toContainText("Blocking");
  }
  for (const key of ["zone.Z4.rr.reverse", "zone.ZP.rr.reverse", "relay.version", "base.voltage"]) {
    await expect(row(page, key)).toHaveAttribute("data-review", "unresolved");
    await expect(row(page, key)).toHaveAttribute("data-blocking", "false");
  }
  expect((await counts(page)).blocking).toBe(4);
  const issues = page.locator("#wwRelayReviewBlocking");
  await expect(issues).toContainText("reverse resistive reach is unresolved");
  await expect(issues).toContainText("Needs: Zone 1 Reverse Resistive Reach");
  await expect(issues).toContainText("ZP cannot be represented");
});

test("readiness moves Not ready -> Ready after confirmation -> Ready to apply, live", async ({ page }) => {
  await reviewP441(page);
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).toContainText("4 blocking items are unresolved.");
  // confirming alone does not make this relay ready
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await resolveAllBlockers(page);
  await expect(readiness(page)).toContainText("Readiness: Ready to apply");
  await expect(readiness(page)).toContainText("Nothing has been applied. Applying settings is not available yet.");
  await expect(page.locator("#wwRelayReviewEngine")).toContainText("Compatible with the current engine");
  expect((await counts(page)).blocking).toBe(0);
  // undoing one confirmation drops it back to waiting on confirmation
  await button(page, "Undo confirmation of Zone 1 Reach").click();
  await expect(readiness(page)).toContainText("Readiness: Ready after confirmation");
  await expect(readiness(page)).toContainText("1 inferred value still needs confirmation.");
  await expect(page.locator("#wwRelayImportSummary")).not.toContainText("blocking");
});

test("Zone P enabled is accepted as an answer but leaves the import not ready for the current engine", async ({ page }) => {
  await reviewP441(page);
  await page.locator("#wwRelayReviewConfirmAll").click();
  await resolveAllBlockers(page, "enabled");
  await expect(chip(page, "zone.ZP.status")).toHaveText("Resolved manually");
  await expect(row(page, "zone.ZP.status").locator(".ww-rr-value")).toHaveText("Enabled");
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).toContainText("cannot take these settings yet");
  await expect(page.locator("#wwRelayReviewBlocking")).toContainText("No value in this review can clear it");
  // the zone is kept; its header follows the answer
  await expect(page.locator('#wwRelayReviewPanel details[data-group="zone-ZP"] > summary')).toContainText("Zone P — Enabled");
  // and the user can change their mind
  await resolveZoneP(page, "disabled");
  await expect(readiness(page)).toContainText("Readiness: Ready to apply");
  await expect(page.locator('#wwRelayReviewPanel details[data-group="zone-ZP"] > summary')).toContainText("Disabled");
});

test("the card summary line follows the live counts", async ({ page }) => {
  await reviewP441(page);
  const summary = page.locator("#wwRelayImportSummary");
  await expect(summary).toContainText("to confirm");
  await expect(summary).toContainText("4 blocking");
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(summary).toContainText("confirmed");
  await expect(summary).not.toContainText("to confirm");
  await resolveAllBlockers(page);
  await expect(summary).toContainText("4 resolved manually");
  await expect(summary).not.toContainText("blocking");
});

test("decisions survive closing and reopening the review, and the panel keeps its place", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Confirm Zone 2 Reach").click();
  await page.locator("#wwRelayReviewCloseBtn").click();
  await page.locator("#wwRelayReviewBtn").click();
  await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed");
  // an open source disclosure stays open while other decisions change
  await row(page, "zone.Z3.reach").getByRole("button", { name: "Source of Zone 3 Reach" }).click();
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await expect(row(page, "zone.Z3.reach").locator(".ww-rr-prov")).toBeVisible();
});

test("Remove, a new upload and a refresh each discard every decision", async ({ page }) => {
  await reviewP441(page);
  await button(page, "Confirm Zone 1 Reach").click();
  await resolveNumber(page, "zone.Z1.rr.reverse", "Zone 1 Reverse Resistive Reach", 2.5);
  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(panel(page)).toBeHidden();
  // new upload: nothing carried over
  await pick(page, "document.pdf", p441Pdf());
  await page.locator("#wwRelayReviewBtn").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("To confirm");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Unresolved");
  // replacing the file with another upload also starts clean
  await button(page, "Confirm Zone 1 Reach").click();
  await pick(page, "document.pdf", p441Pdf());
  await page.locator("#wwRelayReviewBtn").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("To confirm");
  // a hard refresh leaves nothing in the page, in any browser storage
  await button(page, "Confirm Zone 1 Reach").click();
  // (the app keeps its own unrelated preferences in localStorage: look for review data, not for emptiness)
  const stored = await page.evaluate(async () => ({
    text: JSON.stringify([localStorage, sessionStorage].map((s) => Object.entries(s))) + document.cookie,
    idb: (await indexedDB.databases()).length,
  }));
  for (const needle of ["zones[", "validation_context", "confirmed", "resolution", "2.5", "P441", "relay"]) {
    expect(stored.text).not.toContain(needle);
  }
  expect(stored.idb).toBe(0);
  await page.reload();
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await expect(page.locator("#wwRelayReviewBody")).toBeEmpty();
});

test("the browser asks the backend; it sends the decisions with the original interpretation and stores nothing", async ({ page }) => {
  await reviewP441(page);
  const request = page.waitForRequest((r) => r.url().endsWith("/api/v1/relay-import/review/validate"));
  await button(page, "Confirm Zone 1 Reach").click();
  const body = (await request).postDataJSON();
  expect(body.confirmed).toEqual(["zones[Z1].reach"]);
  expect(body.manual).toEqual([]);
  expect(body.validation_context._t).toBe("CanonicalDistanceProtectionModel");
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
});

test("a refused decision is rolled back and says so", async ({ page }) => {
  await reviewP441(page);
  await page.route("**/api/v1/relay-import/review/validate", (route) =>
    route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: { code: "invalid_review", message: "Only an inferred value can be confirmed." } }) }),
  );
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(page.locator("#wwRelayReviewNotice")).toHaveText("Only an inferred value can be confirmed.");
  await expect(chip(page, "zone.Z1.reach")).toHaveText("To confirm");
  await page.unroute("**/api/v1/relay-import/review/validate");
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await expect(page.locator("#wwRelayReviewNotice")).toBeEmpty();
});

test("there is no Apply anywhere, and the manual Distance Protection form is never touched", async ({ page }) => {
  await openDistance(page);
  const inputs = ["#wwDistanceZone1ReachInput", "#wwDistanceZone2ReachInput", "#wwDistanceZone2DelayInput"];
  const before = [];
  for (const sel of inputs) before.push(await page.locator(sel).inputValue());
  await pick(page, "document.pdf", p441Pdf());
  await page.locator("#wwRelayReviewBtn").click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await resolveAllBlockers(page);
  await expect(readiness(page)).toContainText("Readiness: Ready to apply");
  const labels = await page.locator("#wwRelayImportPanel button").allTextContents();
  expect(labels.length).toBeGreaterThan(5);
  for (const label of labels) expect(label).not.toMatch(/apply|populate|generate|plot|auto-?fill|use these/i);
  const after = [];
  for (const sel of inputs) after.push(await page.locator(sel).inputValue());
  expect(after).toEqual(before);
});

test("the review stays contained at narrow width with an editor open", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await reviewP441(page);
  await button(page, "Resolve Zone 1 Reverse Resistive Reach").click();
  await expect(row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  const box = await panel(page).boundingBox();
  expect(box.x + box.width).toBeLessThanOrEqual(360);
});
