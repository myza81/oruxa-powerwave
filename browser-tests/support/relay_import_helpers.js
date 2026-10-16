// Shared helpers for the Relay Import browser specs: synthetic relay setting sheets, opening Distance
// Protection, and picking a file.
//
// The synthetic sheets are DATA, not JavaScript: backend/tests/relay_conformance/sheets/<id>.json (DEC-199) is the
// single source shared with the backend tests, and the PDF is built only by the backend's sheet builder (one escaping
// and layout implementation, deterministic bytes), through the backend interpreter the browser suite already runs.
//
// frontend/config.js pins the API to :8000. When PW_BACKEND_PORT is set the
// config is re-pointed per page via request interception -- nothing is committed.

const { expect } = require("@playwright/test");
const { execFileSync } = require("child_process");
const path = require("path");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";
const PYTHON = process.env.PW_PYTHON || "python3";
const BACKEND_DIR = path.resolve(__dirname, "..", "..", "backend");
const sheetCache = new Map();

// A synthetic relay sheet as PDF bytes: `id` names a sheet spec; `overrides` are the spec's overrides
// ({ variant, drop, set, set_range, insert_after, append, notes } -- see backend/tests/relay_conformance/sheet_spec.py).
function relaySheet(id, overrides) {
  const arg = overrides ? JSON.stringify(overrides) : "";
  const key = `${id}|${arg}`;
  if (!sheetCache.has(key)) {
    const args = ["-m", "tests.relay_conformance.sheet_cli", id];
    if (arg) args.push(arg);
    sheetCache.set(key, execFileSync(PYTHON, args, { cwd: BACKEND_DIR, maxBuffer: 16 * 1024 * 1024 }));
  }
  return sheetCache.get(key);
}

async function routeConfig(page) {
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${BACKEND_PORT}", environment: "development", buildVersion: "local" };`,
    }),
  );
}

async function openDistance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
}

const pick = (page, name, buffer) =>
  page.locator("#wwRelayImportFileInput").setInputFiles({ name, mimeType: "application/pdf", buffer });

module.exports = { BACKEND_PORT, relaySheet, routeConfig, openDistance, pick };
