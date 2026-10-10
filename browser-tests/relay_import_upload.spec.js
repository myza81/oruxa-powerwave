// Relay Import Slice 3/4 -- Import Relay Settings (ephemeral upload + generic
// text extraction summary) -- real-browser coverage. No relay
// identification, interpretation or auto-population. Runs against LOCAL code; no
// recording is needed (Distance Protection's Manual mode stands alone).
//
// frontend/config.js pins the API to :8000. When PW_BACKEND_PORT is set
// (isolated run, to avoid another worktree's servers) the config is
// re-pointed per page via request interception -- nothing is committed.

const { test, expect } = require("@playwright/test");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";
// A real, tiny one-page text PDF (the backend now parses uploads).
function buildPdf(lines, { imageOnly = false } = {}) {
  const content = imageOnly
    ? "q 100 0 0 100 50 600 cm /Im1 Do Q"
    : "BT /F1 10 Tf\n" + lines.map(([x, y, t]) => `1 0 0 1 ${x} ${y} Tm (${t}) Tj`).join("\n") + "\nET";
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [5 0 R] >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\u0080\nendstream",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 3 0 R >> /XObject << /Im1 4 0 R >> >> /Contents 6 0 R >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];
  let out = "%PDF-1.4\n";
  const offsets = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}
const PDF = buildPdf([[40, 780, "R1"], [230, 780, "1.84"], [40, 764, "Zone 2"], [230, 764, "Forward"], [340, 764, "2.4"]]);
const SCANNED_PDF = buildPdf([], { imageOnly: true });

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
  await expect(page.locator("#wwRelayImportType")).toHaveText("PDF");
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Text extracted. Relay settings have not been interpreted yet.");
  await expect(page.locator("#wwRelayImportRemoveBtn")).toBeVisible();
  await expect(page.locator("#wwRelayImportError")).toBeHidden();

  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
  await expect(page.locator("#wwRelayImportFilename")).toHaveText("");
  await expect(page.locator("#wwRelayImportStatus")).toHaveText("");
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwRelayImportBtn")).toBeVisible();

  // The same file can be chosen again after Remove.
  await pick(page, "P441 settings.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
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
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
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
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
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

test("import and remove look like buttons; file card is bordered; empty state is compact", async ({ page }) => {
  await openDistance(page);
  const style = (sel) =>
    page.locator(sel).evaluate((el) => {
      const c = getComputedStyle(el);
      return { bg: c.backgroundColor, border: c.borderTopWidth, cursor: c.cursor, tag: el.tagName };
    });
  const imp = await style("#wwRelayImportBtn");
  expect(imp.tag).toBe("BUTTON");
  expect(imp.bg).not.toBe("rgba(0, 0, 0, 0)"); // filled, not plain text
  expect(imp.cursor).toBe("pointer");
  // Empty state: no card is rendered at all.
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();

  await pick(page, "p441.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
  const card = await page.locator("#wwRelayImportFile").evaluate((el) => {
    const c = getComputedStyle(el);
    return { border: c.borderTopWidth, radius: c.borderTopLeftRadius };
  });
  expect(card.border).toBe("1px");
  expect(card.radius).not.toBe("0px");
  const rm = await style("#wwRelayImportRemoveBtn");
  expect(rm.border).toBe("1px");
  expect(rm.cursor).toBe("pointer");

  await page.locator("#wwRelayImportBtn").focus();
  await page.keyboard.press("Shift"); // keyboard modality so :focus-visible applies
  const outline = await page.locator("#wwRelayImportBtn").evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).not.toBe("none");
});

test("very long filenames truncate with a tooltip and never cause horizontal scrolling", async ({ page }) => {
  const longName = "P441_Feeder_Protection_Setting_Sheet_" + "very-long-segment-".repeat(9) + "final.pdf";
  for (const width of [1280, 360]) {
    await page.setViewportSize({ width, height: 800 });
    await openDistance(page);
    const manualBefore = await page.locator("#wwDistanceZone1ReachInput").inputValue();
    await pick(page, longName, PDF);
    await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page · 2 raw entries");
    const name = page.locator("#wwRelayImportFilename");
    await expect(name).toHaveAttribute("title", longName);
    const m = await page.evaluate(() => {
      const n = document.getElementById("wwRelayImportFilename");
      const card = document.getElementById("wwRelayImportFile");
      const rm = document.getElementById("wwRelayImportRemoveBtn").getBoundingClientRect();
      return {
        truncated: n.scrollWidth > n.clientWidth,
        cardFits: n.getBoundingClientRect().right <= card.getBoundingClientRect().right,
        removeInView: rm.right <= window.innerWidth && rm.left >= 0,
        pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
      };
    });
    expect(m.truncated).toBe(true);
    expect(m.cardFits).toBe(true);
    expect(m.removeInView).toBe(true);
    expect(m.pageOverflow).toBe(false);
    await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue(manualBefore);
  }
});

test("error state is a distinct bordered message and Import is usable again", async ({ page }) => {
  await openDistance(page);
  await pick(page, "broken.pdf", Buffer.from("this is not a pdf"));
  const err = page.locator("#wwRelayImportError");
  await expect(err).toBeVisible();
  const border = await err.evaluate((el) => getComputedStyle(el).borderTopWidth);
  expect(border).toBe("1px");
  await expect(page.locator("#wwRelayImportBtn")).toBeEnabled();
});

test("scanned/image-only and encrypted outcomes are reported without calling the file corrupt", async ({ page }) => {
  await openDistance(page);
  await pick(page, "scan.pdf", SCANNED_PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("1 page");
  await expect(page.locator("#wwRelayImportStatus")).not.toContainText("raw entr");
  await expect(page.locator("#wwRelayImportDetail")).toHaveText(
    "PDF accepted, but no extractable text was found. OCR is not supported yet.",
  );
  await expect(page.locator("#wwRelayImportError")).toBeHidden();

  // Encrypted: the backend's exact response shape (real encrypted-file
  // handling is covered by the backend suite).
  await page.route("**/api/v1/relay-import/upload", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        filename: "locked.pdf", source_format: "pdf", size_bytes: 900, status: "accepted",
        extraction_status: "encrypted", page_count: 0, pages_with_text: 0, raw_entry_count: 0,
        section_count: 0, extraction_warnings: [],
      }),
    }),
  );
  await pick(page, "locked.pdf", PDF);
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("PDF is encrypted and cannot be read.");
  await page.unroute("**/api/v1/relay-import/upload");
});

test("extraction outcome never fills the Distance Protection form", async ({ page }) => {
  await openDistance(page);
  const before = await page.locator("#wwDistanceZone1ReachInput").inputValue();
  await pick(page, "p441.pdf", PDF);
  await expect(page.locator("#wwRelayImportDetail")).toContainText("have not been interpreted");
  await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue(before);
});
