// The generic relay-import browser workflow (Relay Scalability Phase 0, DEC-199): one parameterised test per relay sheet,
// driven only by data -- the synthetic sheet (backend/tests/relay_conformance/sheets) and its expectation
// (backend/tests/relay_conformance/expectations/<sheet>.json, the same file the backend conformance suite checks).
//
// For each sheet the real review UI must show what the backend expectation states: the zone count, the readiness,
// no Apply while not ready, every canonical value's category, blocking flag and value text, a documented value's Source
// citing its catalog reference, and no 0.00 Ω offer where none is expected. Adding a relay adds data, not a spec.
// Relay-specific UI interactions (Apply, approximation acceptance, notes disclosure ...) keep their own specs.

const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

const BACKEND = path.resolve(__dirname, "..", "backend");
const EXPECTATIONS = path.join(BACKEND, "tests", "relay_conformance", "expectations");
const CATALOGS = path.join(BACKEND, "app", "data", "parameter_catalog");

function load(file) {
  return JSON.parse(fs.readFileSync(path.join(EXPECTATIONS, file), "utf8"));
}
// every synthetic sheet and scenario variant whose review needs no typed value (manual entries are backend-only)
const SAMPLES = fs.readdirSync(EXPECTATIONS).filter((f) => f.endsWith(".json") && !f.endsWith(".real.json"))
  .map((f) => [f.replace(/\.json$/, ""), load(f)])
  .filter(([, e]) => e.sample.kind === "synthetic" && !e.sample.manual);

function catalogReferences(catalogId) {
  const files = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((d) =>
    d.isDirectory() ? walk(path.join(dir, d.name)) : d.name.endsWith(".json") && files.push(path.join(dir, d.name)));
  walk(CATALOGS);
  for (const f of files) {
    const data = JSON.parse(fs.readFileSync(f, "utf8"));
    if (data.catalog_id === catalogId) return Object.fromEntries((data.references || []).map((r) => [r.id, r]));
  }
  return {};
}

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
});
test.afterEach(() => {
  expect(problems).toEqual([]);
});

for (const [name, e] of SAMPLES) {
  test(`${name}: the review UI shows what the relay's expectation states`, async ({ page }) => {
    await openDistance(page);
    await pick(page, "document.pdf", relaySheet(e.sample.sheet, e.sample.overrides));
    await expect(page.locator("#wwRelayImportSummary")).toContainText(`${e.identity.zone_count} zones found`);
    await page.locator("#wwRelayReviewBtn").click();
    const panel = page.locator("#wwRelayReviewPanel");
    await expect(panel).toBeVisible();
    await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", e.readiness.initial);
    if (e.readiness.initial !== "ready") await expect(page.locator("#wwRelayReviewApply")).toHaveCount(0);

    // every canonical value, as rendered (first row of a value shown as two rows)
    const rendered = await page.evaluate(() => {
      const out = {};
      for (const li of document.querySelectorAll("#wwRelayReviewPanel li[data-item-id]")) {
        if (!(li.dataset.itemId in out)) out[li.dataset.itemId] = { category: li.dataset.category, blocking: li.dataset.blocking, text: li.textContent };
      }
      return out;
    });
    const mismatches = [];
    for (const [itemId, [valueText, category]] of Object.entries(e.values)) {
      if (!/^(zones\[|transformers\.|line\.)/.test(itemId)) continue;
      const row = rendered[itemId];
      if (!row) { mismatches.push(`${itemId}: not rendered`); continue; }
      if (row.category !== category) mismatches.push(`${itemId}: category ${row.category} != ${category}`);
      const blocking = itemId in e.blocking ? "true" : "false";
      if (row.blocking !== undefined && row.blocking !== blocking) mismatches.push(`${itemId}: blocking ${row.blocking} != ${blocking}`);
      if (valueText !== null && !row.text.includes(valueText.split(" · ")[0])) mismatches.push(`${itemId}: text lacks ${valueText}`);
    }
    // every preserved zone setting (no canonical meaning): its category and whether it blocks
    const raw = await page.evaluate(() => {
      const out = [];
      for (const li of document.querySelectorAll('#wwRelayReviewPanel li[data-key*=".raw."]')) {
        out.push({ zone: li.dataset.key.split(".")[1], text: li.textContent, category: li.dataset.category, blocking: li.dataset.blocking });
      }
      return out;
    });
    for (const [key, [, category, blocking]] of Object.entries(e.preserved || {})) {
      const [zone, label] = [key.slice(0, key.indexOf("/")), key.slice(key.indexOf("/") + 1)];
      const row = raw.find((r) => r.zone === zone && r.text.includes(label));
      if (!row) { mismatches.push(`${key}: preserved row not rendered`); continue; }
      if (row.category !== category) mismatches.push(`${key}: category ${row.category} != ${category}`);
      if (row.blocking !== undefined && row.blocking !== String(blocking)) mismatches.push(`${key}: blocking ${row.blocking} != ${blocking}`);
    }
    expect(mismatches).toEqual([]);

    // a documented value's Source cites its catalog reference
    const documented = Object.entries(e.provenance || {}).find(([id, p]) => p.references && e.values[id] && e.values[id][1] === "documented");
    if (documented) {
      const [itemId, prov] = documented;
      const ref = catalogReferences(e.identity.catalog_id)[prov.references[0]];
      const row = panel.locator(`li[data-item-id="${itemId}"]`).first();
      await row.getByRole("button", { name: /Source/ }).first().click();
      await expect(row).toContainText(ref.document);
    }
    if (!e.offers.suggestions.length) await expect(panel.getByRole("button", { name: /Use 0\.00/ })).toHaveCount(0);
  });
}
