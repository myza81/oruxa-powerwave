// Relay Import Slice 3 -- Import Relay Settings (ephemeral upload) -- real-
// browser coverage. Upload + minimal validation only: no extraction, no
// relay identification, no auto-population. Runs against LOCAL code; no
// recording is needed (Distance Protection's Manual mode stands alone).
//
// frontend/config.js pins the API to :8000. When PW_BACKEND_PORT is set
// (isolated run, to avoid another worktree's servers) the config is
// re-pointed per page via request interception -- nothing is committed.

const { test, expect } = require("@playwright/test");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n");

test.beforeEach(async ({ page }) => {
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${BACKEND_PORT}", environment: "development", buildVersion: "local" };`,
    }),
  );
});

async function openDistance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavAnalysisBtn").click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
}

const pick = (page, name, buffer, mimeType = "application/pdf") =>
  page.locator("#wwRelayImportFileInput").setInputFiles({ name, mimeType, buffer });

test("entry point, privacy wording and manual workflow are all visible together", async ({ page }) => {
  await openDistance(page);
  await expect(page.locator("#wwRelayImportBtn")).toHaveText("Import Relay Settings");
  await expect(page.locator("#wwRelayImportPrivacy")).toContainText("Files are processed temporarily and are not permanently stored.");
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwDistanceBody")).toBeVisible();
  await expect(page.locator("#wwDistanceZone1ReachInput")).toBeVisible();
});

test("a valid PDF shows filename and returned metadata, and Remove resets everything", async ({ page }) => {
  await openDistance(page);
  await pick(page, "P441 settings.pdf", PDF);
  await expect(page.locator("#wwRelayImportFilename")).toHaveText("P441 settings.pdf");
  await expect(page.locator("#wwRelayImportStatus")).toContainText("PDF");
  await expect(page.locator("#wwRelayImportStatus")).toContainText("File accepted");
  await expect(page.locator("#wwRelayImportError")).toBeHidden();

  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(page.locator("#wwRelayImportFilename")).toHaveText("");
  await expect(page.locator("#wwRelayImportStatus")).toHaveText("");
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwRelayImportBtn")).toBeVisible();

  // The same file can be chosen again after Remove.
  await pick(page, "P441 settings.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("File accepted");
});

test("upload errors are shown clearly and never disturb manual form state", async ({ page }) => {
  await openDistance(page);
  await page.locator("#wwDistanceZone1ReachInput").fill("12.5");
  await page.locator("#wwDistanceZone2DelayInput").fill("0.45");

  // Client-side: wrong type, empty.
  await pick(page, "settings.xlsx", Buffer.from("x"), "application/vnd.ms-excel");
  await expect(page.locator("#wwRelayImportError")).toContainText("Unsupported file type");
  await pick(page, "empty.pdf", Buffer.alloc(0));
  await expect(page.locator("#wwRelayImportError")).toContainText("empty");
  // Server-side: malformed PDF.
  await pick(page, "broken.pdf", Buffer.from("this is not a pdf"));
  await expect(page.locator("#wwRelayImportError")).toContainText(/not a readable PDF/);
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  // Server-side: oversized. The real limit is enforced and tested in the
  // backend suite; here the UI is shown the backend's real 413 error shape
  // (sending 20+ MB through the browser would only slow this test down).
  await page.route("**/api/v1/relay-import/upload", (route) =>
    route.fulfill({
      status: 413,
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "upload_too_large", message: "Combined upload size exceeds the 20 MB limit." } }),
    }),
  );
  await pick(page, "huge.pdf", PDF);
  await expect(page.locator("#wwRelayImportError")).toContainText(/exceeds the 20 MB limit/);
  await page.unroute("**/api/v1/relay-import/upload");
  // No filesystem path ever reaches the UI.
  await expect(page.locator("#wwRelayImportError")).not.toContainText(/[A-Za-z]:\\|\/tmp\/|Traceback/);

  await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue("12.5");
  await expect(page.locator("#wwDistanceZone2DelayInput")).toHaveValue("0.45");

  // Recovery: a valid file after errors clears the error.
  await pick(page, "ok.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("File accepted");
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue("12.5");
});

test("backend unreachable shows an error and leaves manual entry usable", async ({ page }) => {
  await openDistance(page);
  await page.route("**/api/v1/relay-import/upload", (route) => route.abort());
  await pick(page, "ok.pdf", PDF);
  await expect(page.locator("#wwRelayImportError")).toContainText("Could not reach the server");
  await page.locator("#wwDistanceZone1ReachInput").fill("3");
  await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue("3");
});

test("import state uses no browser storage and a hard refresh starts clean", async ({ page }) => {
  await openDistance(page);
  const snapshot = () =>
    page.evaluate(async () => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
      idb: indexedDB.databases ? (await indexedDB.databases()).map((d) => d.name).sort() : [],
      cookies: document.cookie,
    }));
  const before = await snapshot();
  await pick(page, "P441 settings.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("File accepted");
  const after = await snapshot();
  expect(after).toEqual(before);
  expect(JSON.stringify(after)).not.toContain("P441");

  await page.reload();
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwRelayImportFilename")).toHaveText("");
});

test("removing while a request is in flight discards its late result", async ({ page }) => {
  await openDistance(page);
  await page.route("**/api/v1/relay-import/upload", async (route) => {
    await new Promise((r) => setTimeout(r, 800));
    await route.continue().catch(() => {});
  });
  await pick(page, "slow.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toHaveText("Processing…");
  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await page.waitForTimeout(1200);
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
});
