// Relay Import Slice 8 bug fix -- the review's readiness/state lifecycle.
//
// UAT hit "Uncaught TypeError: Cannot read properties of undefined (reading
// 'status') at wwRrReadiness" from a review click. The render read
// `live.readiness.status` with no guard, so any review state without a usable
// readiness crashed it. These tests reproduce that and pin the contract: the
// review always renders (a pending check says "Re-evaluating…", an unusable one
// says "Not evaluated"), a stale answer never overwrites a newer decision, and
// nothing is applied to the manual form.

const { test, expect } = require("@playwright/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

const VALIDATE = "**/api/v1/relay-import/review/validate";
const UPLOAD = "**/api/v1/relay-import/upload";

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && /TypeError|undefined|NaN/.test(m.text())) problems.push("console: " + m.text()); });
});
test.afterEach(() => {
  expect(problems).toEqual([]); // no uncaught error, no console TypeError
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const chip = (page, key) => row(page, key).locator(".ww-rr-status").first();
const readiness = (page) => page.locator("#wwRelayReviewReadiness");

async function reviewP441(page, { mutateUpload, failValidate = false } = {}) {
  if (failValidate) {
    await page.route(VALIDATE, (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "internal_error", message: "The review could not be checked." } }) }));
  }
  if (mutateUpload) {
    await page.route(UPLOAD, async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      mutateUpload(body);
      await route.fulfill({ response: res, json: body });
    });
  }
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
  // the first open validates the review; wait for that (a healthy one ends in a real result)
  await expect(readiness(page)).not.toContainText("Re-evaluating");
}

async function expectNoBrokenText(page) {
  const text = await panel(page).innerText();
  expect(text).not.toMatch(/undefined|NaN|null/);
}

test("a review payload without readiness renders safely as Not evaluated when validation also fails (the UAT crash)", async ({ page }) => {
  await reviewP441(page, { mutateUpload: (b) => { delete b.review.readiness; }, failValidate: true });
  await expect(readiness(page)).toContainText("Readiness: Not evaluated");
  await expect(readiness(page)).not.toContainText("Ready to apply");
  await expectNoBrokenText(page);
  // closing and reopening re-renders from scratch: still safe
  await page.locator("#wwRelayReviewCloseBtn").click();
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Not evaluated");
});

for (const [name, mutate] of [
  ["null readiness", (b) => { b.review.readiness = null; }],
  ["unknown status", (b) => { b.review.readiness = { status: "bogus", pending_confirmations: 1, blocking_unresolved: 0 }; }],
  ["wrong type", (b) => { b.review.readiness = "ready"; }],
  ["missing counts and engine", (b) => { delete b.review.mapped_count; delete b.review.engine; delete b.review.blocking_issues; }],
]) {
  test(`a malformed review (${name}) never crashes or shows broken text`, async ({ page }) => {
    await reviewP441(page, { mutateUpload: mutate });
    await expect(readiness(page)).toBeVisible();
    await expect(readiness(page)).not.toContainText("Ready to apply");
    await expectNoBrokenText(page);
    await expect(page.locator("#wwRelayImportSummary")).not.toContainText(/undefined|NaN/);
  });
}

test("every decision type keeps the readiness defined: confirm, undo, confirm all, resolve, clear, leave", async ({ page }) => {
  await reviewP441(page);
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await button(page, "Undo confirmation of Zone 1 Reach").click();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(page.locator("#wwRelayReviewConfirmAll")).toHaveCount(0);
  await button(page, "Resolve Zone 1 Left Resistive Reach (−R)").click();
  const form = row(page, "zone.Z1.rr.reverse").locator("form.ww-rr-resolve");
  await form.locator("input").fill("2.5");
  await form.getByRole("button", { name: "Set value" }).click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Resolved manually");
  await button(page, "Clear the value of Zone 1 Left Resistive Reach (−R)").click();
  await expect(chip(page, "zone.Z1.rr.reverse")).toHaveText("Source value missing");
  await button(page, "Resolve Zone 1 Left Resistive Reach (−R)").click();
  await button(page, "Leave Zone 1 Left Resistive Reach (−R) unresolved").click();
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Left unresolved");
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expectNoBrokenText(page);
});

test("while a check is pending the readiness says so, never a stale Ready, and rendering is safe", async ({ page }) => {
  await reviewP441(page);
  await page.locator("#wwRelayReviewConfirmAll").click();
  for (const [z, n] of [["Z1", "Zone 1"], ["Z2", "Zone 2"], ["Z3", "Zone 3"]]) {
    await button(page, `Resolve ${n} Left Resistive Reach (−R)`).click();
    const f = row(page, `zone.${z}.rr.reverse`).locator("form.ww-rr-resolve");
    await f.locator("input").fill("2.5");
    await f.getByRole("button", { name: "Set value" }).click();
    await expect(f).toBeHidden();
  }
  await button(page, "Resolve Zone P Status").click();
  const zp = row(page, "zone.ZP.status").locator("form.ww-rr-resolve");
  await zp.locator("select").selectOption("disabled");
  await zp.getByRole("button", { name: "Set value" }).click();
  await expect(readiness(page)).toContainText("Ready to apply");

  let release;
  const gate = new Promise((r) => { release = r; });
  await page.route(VALIDATE, async (route) => { await gate; await route.continue(); });
  await button(page, "Undo confirmation of Zone 1 Reach").click();
  await expect(readiness(page)).toContainText("Re-evaluating…");
  await expect(readiness(page)).not.toContainText("Ready to apply");
  // render while pending: close and reopen, toggle, still no crash and still pending
  await page.locator("#wwRelayReviewCloseBtn").click();
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Re-evaluating…");
  release();
  await expect(readiness(page)).toContainText("Ready after confirmation");
  await expectNoBrokenText(page);
});

test("a stale answer never overwrites a newer decision (a second decision while the first check is in flight)", async ({ page }) => {
  await reviewP441(page);
  let held;
  let calls = 0;
  const heldDone = new Promise((r) => { held = r; });
  await page.route(VALIDATE, async (route) => {
    calls += 1;
    if (calls === 1) {
      // the first answer (Z1 confirmed only) is real but delivered after the second check finished
      const res = await route.fetch();
      const body = await res.json();
      await heldDone;
      await route.fulfill({ response: res, json: body }).catch(() => {});
    } else {
      await route.continue();
    }
  });
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(readiness(page)).toContainText("Re-evaluating…");
  await button(page, "Confirm Zone 2 Reach").click(); // the first answer has not landed yet
  await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed");
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed"); // the newest answer carries both decisions
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  held(); // now the older answer (Z1 only) arrives
  await page.waitForTimeout(400);
  await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed"); // and is discarded
  await expect(readiness(page)).not.toContainText("Re-evaluating");
  expect(await page.locator("#wwRelayReviewSummary").innerText()).toMatch(/2 confirmed/i);
});

test("rapid successive decisions all land, in order, and readiness reflects the newest", async ({ page }) => {
  await reviewP441(page);
  await page.evaluate(() => {
    ["Zone 1", "Zone 2", "Zone 3"].forEach((z) => {
      document.querySelector(`#wwRelayReviewPanel button[aria-label="Confirm ${z} Reach"]`).click();
    });
  });
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed");
  await expect(chip(page, "zone.Z3.reach")).toHaveText("Confirmed");
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).not.toContainText("Re-evaluating");
  // confirm / undo / confirm in one tick: the last intent wins
  await page.evaluate(() => {
    const q = (l) => document.querySelector(`#wwRelayReviewPanel button[aria-label="${l}"]`);
    q("Confirm Zone 4 Reach").click();
    q("Undo confirmation of Zone 1 Reach").click();
  });
  await expect(chip(page, "zone.Z4.reach")).toHaveText("Confirmed");
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption");
  await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed");
});

for (const [name, fulfil] of [
  ["a server error", { status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "internal_error", message: "The review could not be validated." } }) }],
  ["a body without readiness", { status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) }],
  ["a non-JSON body", { status: 200, contentType: "text/plain", body: "oops" }],
]) {
  test(`${name} keeps the panel usable, says Not evaluated and keeps the last good decisions`, async ({ page }) => {
    await reviewP441(page);
    await button(page, "Confirm Zone 2 Reach").click();
    await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed");
    await page.route(VALIDATE, (route) => route.fulfill(fulfil));
    await button(page, "Confirm Zone 1 Reach").click();
    await expect(readiness(page)).toContainText("Readiness: Not evaluated");
    await expect(page.locator("#wwRelayReviewNotice")).not.toBeEmpty();
    await expect(chip(page, "zone.Z1.reach")).toHaveText("Assumption"); // the refused change is not kept
    await expect(chip(page, "zone.Z2.reach")).toHaveText("Confirmed"); // earlier accepted decision survives
    await expectNoBrokenText(page);
    // the panel still works once the backend answers again
    await page.unroute(VALIDATE);
    await button(page, "Confirm Zone 1 Reach").click();
    await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
    await expect(readiness(page)).toContainText("Readiness: Not ready");
    await expect(page.locator("#wwRelayReviewNotice")).toBeEmpty();
  });
}

test("a network failure is a concise notice, not a crash", async ({ page }) => {
  await reviewP441(page);
  await page.route(VALIDATE, (route) => route.abort());
  await button(page, "Confirm Zone 1 Reach").click();
  await expect(page.locator("#wwRelayReviewNotice")).toContainText("Could not reach the server");
  await expect(readiness(page)).toContainText("Not evaluated");
});

test("no Apply control exists in any state, and the manual Distance Protection form is untouched", async ({ page }) => {
  await openDistance(page);
  const inputs = ["#wwDistanceZone1ReachInput", "#wwDistanceZone2ReachInput", "#wwDistanceZone2DelayInput"];
  const before = [];
  for (const sel of inputs) before.push(await page.locator(sel).inputValue());
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await page.locator("#wwRelayReviewBtn").click();
  await page.route(VALIDATE, (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await button(page, "Confirm Zone 1 Reach").click(); // failure state
  await expect(readiness(page)).toContainText("Not evaluated");
  for (const label of await page.locator("#wwRelayImportPanel button").allTextContents()) {
    expect(label).not.toMatch(/apply|populate|generate|plot|auto-?fill|use these/i);
  }
  const after = [];
  for (const sel of inputs) after.push(await page.locator(sel).inputValue());
  expect(after).toEqual(before);
});

// ---------------------------------------------------------------------------
// Initial review validation: a review is checked by the backend when it first
// opens, so "Not evaluated" is an abnormal state, never the ordinary start.
// ---------------------------------------------------------------------------

test("a healthy first open shows the backend's initial result, never 'Not evaluated'", async ({ page }) => {
  await openDistance(page);
  const inputs = ["#wwDistanceZone1ReachInput", "#wwDistanceZone2ReachInput", "#wwDistanceZone2DelayInput"];
  const before = [];
  for (const sel of inputs) before.push(await page.locator(sel).inputValue());
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.evaluate(() => {
    window.__readinessTexts = [];
    new MutationObserver(() => {
      const el = document.getElementById("wwRelayReviewReadiness");
      if (el) window.__readinessTexts.push(el.innerText);
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).toContainText("Blocking settings: 3");
  await expect(page.locator("#wwRelayReviewBlocking")).toContainText("Left Resistive Reach (−R) is unresolved");
  await expect(page.locator("#wwRelayReviewBlocking")).not.toContainText("ZP");
  const seen = await page.evaluate(() => window.__readinessTexts);
  expect(seen.length).toBeGreaterThan(0);
  expect(seen.join("|")).not.toContain("Not evaluated");
  expect(seen.join("|")).not.toContain("Ready to apply");
  for (const label of await page.locator("#wwRelayImportPanel button").allTextContents()) {
    expect(label).not.toMatch(/apply|populate|generate|plot|auto-?fill|use these/i);
  }
  const after = [];
  for (const sel of inputs) after.push(await page.locator(sel).inputValue());
  expect(after).toEqual(before);
});

test("while the initial validation is pending the readiness says Re-evaluating…", async ({ page }) => {
  let release;
  const gate = new Promise((r) => { release = r; });
  await page.route(VALIDATE, async (route) => { await gate; await route.continue(); });
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Re-evaluating…");
  await expect(readiness(page)).not.toContainText("Not ready");
  release();
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).not.toContainText("Re-evaluating");
});

test("a failed initial validation is Not evaluated, and reopening retries it", async ({ page }) => {
  await reviewP441(page, { failValidate: true });
  await expect(readiness(page)).toContainText("Readiness: Not evaluated");
  await expect(page.locator("#wwRelayReviewNotice")).not.toBeEmpty();
  await page.unroute(VALIDATE);
  await page.locator("#wwRelayReviewCloseBtn").click();
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(page.locator("#wwRelayReviewNotice")).toBeEmpty();
});

test("closing and reopening keeps a valid live result without validating again", async ({ page }) => {
  let calls = 0;
  await page.route(VALIDATE, (route) => { calls += 1; return route.continue(); });
  await reviewP441(page);
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  expect(calls).toBe(1);
  await page.locator("#wwRelayReviewCloseBtn").click();
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Readiness: Not ready");
  await expect(readiness(page)).not.toContainText("Re-evaluating");
  expect(calls).toBe(1);
});

test("a decision made while the initial validation is pending is honoured", async ({ page }) => {
  let release;
  const gate = new Promise((r) => { release = r; });
  let first = true;
  await page.route(VALIDATE, async (route) => {
    if (first) { first = false; await gate; }
    await route.continue().catch(() => {});
  });
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await page.locator("#wwRelayReviewBtn").click();
  await expect(readiness(page)).toContainText("Re-evaluating…");
  await button(page, "Confirm Zone 1 Reach").click(); // queued under the request-version mechanism
  release();
  await expect(chip(page, "zone.Z1.reach")).toHaveText("Confirmed");
  await expect(readiness(page)).toContainText("Readiness: Not ready");
});
