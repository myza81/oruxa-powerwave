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

// {mapped, assumptions, confirmed, missing, unsupported, ...} from the summary chips.
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
    await resolveNumber(page, `zone.${z}.rr.reverse`, `${n} Left Resistive Reach (−R)`, 2.5);
  }
  await resolveZoneP(page, zoneP);
}

test("Confirm appears only on Assumption rows; no other category offers it", async ({ page }) => {
  await reviewP441(page);
  await expect(row(page, "ct.primary")).toHaveAttribute("data-review", "mapped");
  await expect(row(page, "ct.primary")).toHaveAttribute("data-category", "mapped");
  await expect(row(page, "zone.Z1.reach")).toHaveAttribute("data-category", "assumption");
  // every Confirm button, anywhere, sits on an Assumption row
  const offenders = await panel(page).locator('li:not([data-category="assumption"]) button[aria-label^="Confirm"]').count();
  expect(offenders).toBe(0);
  for (const key of ["zone.Z1.rr.reverse", "zone.ZP.status", "relay.version", "base.voltage"]) {
    await expect(row(page, key).getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  }
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
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-category", "missing");
  await expect(button(page, "Resolve Zone 1 Left Resistive Reach (−R)")).toHaveCount(1);
  await expect(button(page, "Resolve Zone P Status")).toHaveCount(1);
  // unknown semantics stay missing, with a reason and no editor
  for (const key of ["base.voltage", "base.current", "relay.version", "line.z1"]) {
    await expect(row(page, key)).toHaveAttribute("data-review", "unresolved");
    await expect(row(page, key)).toHaveAttribute("data-category", "missing");
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
  expect(after.assumptions).toBe(before.assumptions - 1);
  expect(after.confirmed).toBe(1);
  expect(after.mapped).toBe(before.mapped);
  expect(after.missing).toBe(before.missing);
  // the category is not rewritten by the confirmation: it is still an assumption
  await expect(row(page, "zone.Z1.reach")).toHaveAttribute("data-category", "assumption");
  // provenance keeps the profile's reasoning, now labelled as the original assumption
  await row(page, "zone.Z1.reach").getByRole("button", { name: "Source of Zone 1 Reach" }).click();
  await expect(row(page, "zone.Z1.reach")).toContainText("Originally an assumption because");
  await expect(row(page, "zone.Z1.reach")).toContainText("the reach is set at the line angle");
  await expect(row(page, "zone.Z1.reach")).toContainText("Classified as: Assumption");
  await expect(row(page, "zone.Z1.reach")).toContainText("Confirmed: by you, for this import session only");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("1 confirmed");

  await button(page, "Undo confirmation of Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
  expect(await counts(page)).toEqual(before);
  await expect(row(page, "zone.Z1.reach")).toContainText("Assumption:");
});

test("Confirm all assumptions shows its count, changes only Assumption rows, and can be undone", async ({ page }) => {
  await reviewP441(page);
  const before = await counts(page);
  const all = page.locator("#wwRelayReviewConfirmAll");
  await expect(all).toHaveText(`Confirm all assumptions (${before.assumptions})`);
  await all.click();
  await expect(all).toHaveCount(0);
  const after = await counts(page);
  expect(after).toMatchObject({
    confirmed: before.assumptions, mapped: before.mapped, missing: before.missing,
    unsupported: before.unsupported, blocking: before.blocking,
  });
  expect(after.assumptions).toBe(0);
  await expect(panel(page).locator('li[data-review="to_confirm"]')).toHaveCount(0);
  // only Assumption rows were confirmed
  await expect(panel(page).locator('li[data-review="confirmed"]:not([data-category="assumption"])')).toHaveCount(0);
  // missing and unsupported rows were not touched by the bulk action
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-review", "unresolved");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  await page.locator("#wwRelayReviewUndoAll").click();
  await expect(page.locator("#wwRelayReviewUndoAll")).toHaveCount(0); // the backend has answered
  expect(await counts(page)).toEqual(before);
});

test("a manual resolution keeps the source value unavailable and shows the user's value apart", async ({ page }) => {
  await reviewP441(page);
  const before = await counts(page);
  await button(page, "Resolve Zone 1 Left Resistive Reach (−R)").click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  // a blank is not a value
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(form.locator(".ww-rr-resolve-error")).toContainText("Enter a value");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  await form.locator("input").fill("2.5");
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Resolved manually");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-value")).toHaveText("2.5 Ω");
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-status", "unresolved");
  await row(page, "zone.Z1.rr.reverse").getByRole("button", { name: "Source of Zone 1 Left Resistive Reach (−R)" }).click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Source value: unavailable / unresolved");
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("User resolution: 2.5 Ω");
  const after = await counts(page);
  expect(after["resolved manually"]).toBe(1);
  expect(after.missing).toBe(before.missing - 1);
  expect(after.blocking).toBe(before.blocking - 1);
  // the original classification stays traceable beside the user's decision
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Classified as: Missing");
  // clear returns it to missing, never to a default
  await button(page, "Clear the value of Zone 1 Left Resistive Reach (−R)").click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-value")).toHaveText("Not available");
  expect(await counts(page)).toEqual(before);
});

test("an explicit zero is a value; leaving an item unresolved is a decision of its own", async ({ page }) => {
  await reviewP441(page);
  await resolveNumber(page, "zone.Z4.rr.reverse", "Zone 4 Left Resistive Reach (−R)", 0);
  await expect(row(page, "zone.Z4.rr.reverse").locator(".ww-rr-value")).toHaveText("0 Ω");
  await expect(chip(page, "zone.Z4.rr.reverse")).toHaveText("Resolved manually");

  const before = await counts(page);
  await button(page, "Resolve Zone 1 Left Resistive Reach (−R)").click();
  await button(page, "Leave Zone 1 Left Resistive Reach (−R) unresolved").click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Left unresolved");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  await expect(row(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-blocking", "true"); // still blocks
  expect(await counts(page)).toEqual(before);
  await button(page, "Undo leaving Zone 1 Left Resistive Reach (−R) unresolved").click();
  await expect(row(page, "zone.Z1.rr.reverse")).not.toContainText("Left unresolved");
});

test("blocking settings are told apart from missing values that do not block", async ({ page }) => {
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
  await expect(issues).toContainText("Left Resistive Reach (−R) is unresolved");
  await expect(issues).toContainText("Needs: Zone 1 Left Resistive Reach (−R)");
  await expect(issues).toContainText("ZP cannot be represented");
});

test("blocking settings and blocking reasons are counted and worded apart", async ({ page }) => {
  await reviewP441(page);
  // 4 settings the engine needs, explained by 2 engine reasons: never worded as one number
  await expect(page.locator("#wwRelayReviewBlockingSettings")).toHaveText("4 blocking settings");
  await expect(readiness(page)).toContainText("Blocking settings: 4");
  await expect(page.locator("#wwRelayReviewEngine .ww-rr-sub")).toHaveText("Blocking reasons (2)");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("4 blocking settings");
  await expect(page.locator("#wwRelayReviewPanel")).not.toContainText("Blocking issues");
  await expect(page.locator("#wwRelayReviewPanel")).not.toContainText("4 blocking items");
});

test("the summary names the uncertainty categories; conflict and unreadable appear only when present", async ({ page }) => {
  await reviewP441(page);
  const summary = page.locator("#wwRelayReviewSummary .ww-rr-counts");
  await expect(summary).toContainText("30 assumptions");
  await expect(summary).toContainText("21 missing");
  await expect(summary).toContainText("0 unsupported"); // this sheet has no per-loop tilt rows
  await expect(summary).not.toContainText("to confirm");
  await expect(summary).not.toContainText("unresolved");
  await expect(summary).not.toContainText("conflict");
  await expect(summary).not.toContainText("unreadable");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("30 assumptions · 21 missing · 4 blocking settings");
});

test("each uncertain row is classified by why it is uncertain, with the reason in its Source", async ({ page }) => {
  await reviewP441(page);
  const expected = {
    "ct.primary": "Mapped", "zone.Z1.reach": "Assumption", "zone.Z1.direction": "Assumption",
    "zone.Z1.rr.reverse": "Missing", "base.voltage": "Missing", "zone.ZP.status": "Missing",
  };
  for (const [key, label] of Object.entries(expected)) await expect(chip(page, key)).toHaveText(label);
  // the full reason sits in the Source disclosure, under a label that names the category
  const open = async (key, label) => row(page, key).getByRole("button", { name: `Source of ${label}` }).click();
  await open("zone.Z1.direction", "Zone 1 Direction");
  await expect(row(page, "zone.Z1.direction")).toContainText("Assumption: Zones 1-3 are forward-looking in the P441 family");
  await open("zone.Z1.rr.reverse", "Zone 1 Left Resistive Reach (−R)");
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Why missing: No value is stated in the document.");
  await open("zone.ZP.status", "Zone P Status");
  await expect(row(page, "zone.ZP.status")).toContainText("Why missing:");
  await expect(row(page, "zone.ZP.status")).toContainText("Current engine: The engine evaluates 4 zones; ZP cannot be represented.");
});

test("a setting the profile keeps raw (a per-loop tilt) is Unsupported and cannot be confirmed", async ({ page }) => {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf({ extraRows: [["3026", "Z1m Tilt Angle", "0", "-90 to +90 deg."]] }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  const tilt = panel(page).locator("li", { hasText: "Z1m Tilt Angle" });
  await expect(tilt.locator(".ww-rr-status").first()).toHaveText("Unsupported");
  await expect(tilt.getByRole("button", { name: /^(Confirm|Resolve|Edit)/ })).toHaveCount(0);
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText(/1 unsupported/);
  await tilt.getByRole("button", { name: /^Source of/ }).click();
  await expect(tilt).toContainText("Why unsupported: tilt applies per fault-loop type");
  await expect(tilt).toContainText("limit of the current software, not something to confirm");
  // the bulk action does not touch it
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(page.locator("#wwRelayReviewConfirmAll")).toHaveCount(0);
  await expect(tilt.locator(".ww-rr-status").first()).toHaveText("Unsupported");
});

test("a conflicting source value is a Conflict: no Confirm, no typed value, and nothing is chosen", async ({ page }) => {
  await openDistance(page);
  // the same setting printed twice with different values
  await pick(page, "document.pdf", p441Pdf({ extraRows: [["300E", "tZ1", "0.4", "0-10.0 s"]] }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText(/1 conflict/);
  await expect(chip(page, "zone.Z1.timer")).toHaveText("Conflict");
  await expect(row(page, "zone.Z1.timer")).toHaveAttribute("data-category", "conflict");
  await expect(row(page, "zone.Z1.timer").getByRole("button", { name: /^(Confirm|Resolve|Edit)/ })).toHaveCount(0);
  await row(page, "zone.Z1.timer").getByRole("button", { name: "Source of Zone 1 Time Delay" }).click();
  await expect(row(page, "zone.Z1.timer")).toContainText("Why conflicting: 300E tZ1: conflicting duplicate entries");
  await expect(row(page, "zone.Z1.timer")).toContainText("Oruxa did not choose between the conflicting source values.");
});

test("a value that could not be read is Unreadable: no Confirm, and the row suggests a clearer source", async ({ page }) => {
  await openDistance(page);
  await pick(page, "document.pdf", p441Pdf({ overrides: { "300A": "1,43" } }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText(/\d+ unreadable/);
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Unreadable");
  await expect(row(page, "zone.Z1.reach").getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  await row(page, "zone.Z1.reach").getByRole("button", { name: "Source of Zone 1 Reach" }).click();
  await expect(row(page, "zone.Z1.reach")).toContainText("Why unreadable:");
  await expect(row(page, "zone.Z1.reach")).toContainText("Provide a clearer source document");
});

test("readiness moves Not ready -> Ready after confirmation -> Ready to apply, live", async ({ page }) => {
  await reviewP441(page);
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).toContainText("Blocking settings: 4");
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
  await expect(readiness(page)).toContainText("1 assumption still needs confirmation.");
  await expect(page.locator("#wwRelayImportSummary")).not.toContainText("blocking");
});

test("Zone P enabled is accepted as an answer but leaves the import not ready for the current engine", async ({ page }) => {
  await reviewP441(page);
  await page.locator("#wwRelayReviewConfirmAll").click();
  await resolveAllBlockers(page, "enabled");
  // an answer the engine cannot take is shown as Unsupported, not as a settled "Resolved manually"
  await expect(chip(page, "zone.ZP.status")).toHaveText("Unsupported");
  await expect(row(page, "zone.ZP.status").locator(".ww-rr-value")).toHaveText("Enabled");
  await expect(row(page, "zone.ZP.status").getByRole("button", { name: /^Confirm/ })).toHaveCount(0);
  await expect(page.locator("#wwRelayReviewSummary .ww-rr-counts")).toContainText("1 unsupported");
  await row(page, "zone.ZP.status").getByRole("button", { name: "Source of Zone P Status" }).click();
  await expect(row(page, "zone.ZP.status")).toContainText("Why unsupported: The engine evaluates 4 zones; ZP cannot be represented.");
  await expect(row(page, "zone.ZP.status")).toContainText("User resolution: Enabled");
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
  await expect(summary).toContainText("assumptions");
  await expect(summary).toContainText("4 blocking settings");
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(summary).toContainText("confirmed");
  await expect(summary).not.toContainText("assumptions");
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
  await resolveNumber(page, "zone.Z1.rr.reverse", "Zone 1 Left Resistive Reach (−R)", 2.5);
  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(panel(page)).toBeHidden();
  // new upload: nothing carried over
  await pick(page, "document.pdf", p441Pdf());
  await page.locator("#wwRelayReviewBtn").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Missing");
  // replacing the file with another upload also starts clean
  await button(page, "Confirm Zone 1 Reach").click();
  await pick(page, "document.pdf", p441Pdf());
  await page.locator("#wwRelayReviewBtn").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
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
    route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: { code: "invalid_review", message: "Only an assumption can be confirmed." } }) }),
  );
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(page.locator("#wwRelayReviewNotice")).toHaveText("Only an assumption can be confirmed.");
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
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
  await button(page, "Resolve Zone 1 Left Resistive Reach (−R)").click();
  await expect(row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  const box = await panel(page).boundingBox();
  expect(box.x + box.width).toBeLessThanOrEqual(360);
});
