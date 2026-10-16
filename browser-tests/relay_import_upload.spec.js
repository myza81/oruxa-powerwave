// Relay Import Slice 3/4/5/6 -- Import Relay Settings (ephemeral upload, generic
// text extraction summary, relay identification verdict, P441 interpretation
// SUMMARY) -- real-browser coverage. Interpreted is never applied: nothing here
// auto-populates the form. Runs against LOCAL code; no
// recording is needed (Distance Protection's Manual mode stands alone).
//
// frontend/config.js pins the API to :8000. When PW_BACKEND_PORT is set
// (isolated run, to avoid another worktree's servers) the config is
// re-pointed per page via request interception -- nothing is committed.

const { test, expect } = require("@playwright/test");
const { relaySheet } = require("./support/relay_import_helpers");

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
// A setting sheet whose scheme field names a relay (identification evidence).
const sheet = (scheme, ...more) =>
  buildPdf([[40, 800, `Scheme: ${scheme}`], ...more.map((t, i) => [40, 780 - 16 * i, t])]);
const SIEMENS_PDF = sheet("7SA6131_4AB02_3GA0", "R1 1.84");

test.beforeEach(async ({ page }) => {
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${BACKEND_PORT}", environment: "development", buildVersion: "local" };`,
    }),
  );
});

// Every catalogued relay family now has an active parameter catalog, so no real sheet is "identified but not
// interpreted" any more. That outcome is still a backend response (a catalogue entry without an active catalog),
// so its honest wording is exercised with the backend's own response shape.
async function pickIdentifiedOnly(page) {
  await page.route("**/api/v1/relay-import/upload", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        filename: "siemens.pdf", source_format: "pdf", size_bytes: 900, status: "accepted",
        extraction_status: "text_extracted", page_count: 1, pages_with_text: 1, raw_entry_count: 2,
        section_count: 0, extraction_warnings: [], identification_status: "identified",
        manufacturer: "Siemens", relay_family: "SIPROTEC 4 7SA6", model: "7SA613", profile_id: "siemens-7sa613",
        confidence: "high", identification_warnings: [], interpretation_status: "not_supported",
        profile_version: null, mapped_setting_count: 0, inferred_setting_count: 0, unresolved_setting_count: 0,
        not_interpreted_setting_count: 0, zone_count: 0, interpretation_warnings: [], review: null,
        catalog_id: null, catalog_version: null, catalog_coverage: null,
      }),
    }),
  );
  await pick(page, "siemens.pdf", SIEMENS_PDF);
  // the upload is sent after the file is picked: keep the response mocked until it has been rendered
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens · 7SA613");
  await page.unroute("**/api/v1/relay-import/upload");
}

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
  // The file is called "P441 settings" but its content names no relay: the
  // file name is never evidence.
  await expect(page.locator("#wwRelayImportIdentity")).toBeHidden();
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay model not recognised. You can continue with manual entry.");
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
  await pick(page, "p441.pdf", SIEMENS_PDF); // a catalogued relay: interpreted by its own catalog, never applied
  await expect(page.locator("#wwRelayImportDetail")).toContainText("Nothing has been applied to the form");
  await expect(page.locator("#wwDistanceZone1ReachInput")).toHaveValue(before);
});

test("an identified relay is named, with an honest 'not interpreted' message", async ({ page }) => {
  await openDistance(page);
  await pickIdentifiedOnly(page);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens · 7SA613");
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay identified. Settings have not been interpreted yet.");
  await expect(page.locator("#wwRelayImportStatus")).toContainText("raw entr");
  await expect(page.locator("#wwRelayImportCard, #wwRelayImportFile")).not.toContainText(/validated|supported relay/i);
  // Remove clears the identity as well.
  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("");
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
});

test("an unrecognised relay is not an error and manual entry stays available", async ({ page }) => {
  await openDistance(page);
  await pick(page, "other.pdf", sheet("XYZ9000_V1", "R1 1.84"));
  await expect(page.locator("#wwRelayImportIdentity")).toBeHidden();
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay model not recognised. You can continue with manual entry.");
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await expect(page.locator("#wwRelayImportFile")).toHaveAttribute("data-state", "accepted");
  await expect(page.locator("#wwDistanceZone1ReachInput")).toBeEditable();
});

test("an ambiguous document asks for confirmation and picks no relay", async ({ page }) => {
  await openDistance(page);
  await pick(page, "mixed.pdf", sheet("7SA511_V3.2_1A", "Relay Type: 7SA6131"));
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay identification needs confirmation.");
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens"); // both candidates agree on this only
  await expect(page.locator("#wwRelayImportFile")).not.toContainText("7SA613");
  await expect(page.locator("#wwRelayImportFile")).not.toContainText("7SA511");
});

test("a relay without a recorded manufacturer shows just its model", async ({ page }) => {
  await openDistance(page);
  await pick(page, "old.pdf", sheet("LFZP111_1A", "KZ1 1"));
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("LFZP111");
});

// ---------------------------------------------------------------------------
// Slice 6 -- P441 interpretation summary (interpreted, never applied)
// ---------------------------------------------------------------------------

// A P441-shaped setting sheet (backend/tests/relay_conformance/sheets/p441.json, DEC-199): the minimal variant
// without Zone P (an absent optional zone).
const p441Pdf = () => relaySheet("p441", { variant: "minimal", drop: ["301D", "3020", "3023"] });
// Slice 8/8A: the line is the live review count by category, so confirmed / resolved / blocking
// parts appear as they become non-zero and zero parts are dropped.
const P441_SUMMARY =
  /^\d+ zones found · \d+ settings mapped( · \d+ assumptions?)?( · \d+ confirmed)?( · \d+ resolved manually)?( · \d+ suggested)?( · \d+ missing)?( · \d+ conflicts?)?( · \d+ not yet supported)?( · \d+ unreadable)?( · \d+ blocking settings?)?$/;

test("a P441 is interpreted, summarised, and NOTHING is applied to the form", async ({ page }) => {
  await openDistance(page);
  const inputs = ["#wwDistanceZone1ReachInput", "#wwDistanceZone2ReachInput", "#wwDistanceZone2DelayInput"];
  const before = [];
  for (const sel of inputs) before.push(await page.locator(sel).inputValue());
  await pick(page, "document.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Schneider Electric · P441");
  await expect(page.locator("#wwRelayImportDetail")).toHaveText(
    "Relay identified and settings interpreted. Review is required before applying. Nothing has been applied to the form.",
  );
  await expect(page.locator("#wwRelayImportSummary")).toHaveText(P441_SUMMARY);
  await expect(page.locator("#wwRelayImportSummary")).toContainText("5 zones found");
  // Interpreted, but never applied: the manual form is exactly as it was.
  for (let i = 0; i < inputs.length; i++) await expect(page.locator(inputs[i])).toHaveValue(before[i]);
  await expect(page.locator("#wwRelayImportFile")).not.toContainText(/validated/i);
  await expect(page.locator("#wwRelayImportPanel").getByRole("button", { name: /apply/i })).toHaveCount(0);
  // No settings value leaks into the card.
  const card = await page.locator("#wwRelayImportFile").innerText();
  for (const value of ["1.43", "7.02", "17.19", "132000"]) expect(card).not.toContain(value);

  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayImportSummary")).toHaveText("");
  await expect(page.locator("#wwRelayImportFile")).toBeHidden();
});

test("a second upload replaces the P441 summary and a non-interpreted relay shows none", async ({ page }) => {
  await openDistance(page);
  await pick(page, "p441.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toHaveText(P441_SUMMARY);
  await pickIdentifiedOnly(page);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens · 7SA613");
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay identified. Settings have not been interpreted yet.");
  await expect(page.locator("#wwRelayImportSummary")).toHaveText("");
  await expect(page.locator("#wwRelayImportSummary")).toBeHidden();
});

test("a second upload replaces the P441 summary with the next relay's own catalog interpretation", async ({ page }) => {
  await openDistance(page);
  await pick(page, "p441.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toHaveText(P441_SUMMARY);
  await pick(page, "siemens.pdf", SIEMENS_PDF);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Siemens · 7SA613");
  await expect(page.locator("#wwRelayImportDetail")).toContainText("Relay identified and settings interpreted.");
  await expect(page.locator("#wwRelayImportSummary")).toContainText("6 zones found"); // the 7SA613 catalog's zones
});

test("summary wording for each interpretation outcome (backend response shapes)", async ({ page }) => {
  const reply = (extra) => (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        filename: "p441.pdf", source_format: "pdf", size_bytes: 900, status: "accepted",
        extraction_status: "text_extracted", page_count: 5, pages_with_text: 5, raw_entry_count: 361,
        section_count: 3, extraction_warnings: [], identification_status: "identified",
        manufacturer: "Schneider Electric", relay_family: "MiCOM P44x", model: "P441",
        profile_id: "schneider-micom-p441", confidence: "high", identification_warnings: [],
        interpretation_warnings: [], ...extra,
      }),
    });
  const respondWith = async (extra) => {
    await page.unroute("**/api/v1/relay-import/upload").catch(() => {});
    await page.route("**/api/v1/relay-import/upload", reply(extra));
    await pick(page, "p441.pdf", p441Pdf());
  };
  await openDistance(page);
  await respondWith({
    interpretation_status: "interpreted", profile_version: "micom-p441-v1", zone_count: 1,
    mapped_setting_count: 1, inferred_setting_count: 0, unresolved_setting_count: 0,
  });
  await expect(page.locator("#wwRelayImportSummary")).toHaveText("1 zone found · 1 setting mapped");

  await respondWith({
    interpretation_status: "interpreted", profile_version: "micom-p441-v1", zone_count: 4,
    mapped_setting_count: 32, inferred_setting_count: 7, unresolved_setting_count: 3,
  });
  await expect(page.locator("#wwRelayImportSummary")).toHaveText("4 zones found · 32 settings mapped · 7 assumptions · 3 unresolved");

  await respondWith({ interpretation_status: "incomplete", profile_version: "micom-p441-v1", zone_count: 0 });
  await expect(page.locator("#wwRelayImportDetail")).toHaveText(
    "Relay identified, but no distance zones could be interpreted. You can continue with manual entry.",
  );
  await expect(page.locator("#wwRelayImportSummary")).toHaveText("");

  await respondWith({ interpretation_status: "failed", profile_version: "micom-p441-v1" });
  await expect(page.locator("#wwRelayImportDetail")).toHaveText(
    "Relay identified, but its settings could not be interpreted. You can continue with manual entry.",
  );
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
  await page.unroute("**/api/v1/relay-import/upload");
});

test("the interpretation summary never causes horizontal scrolling on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openDistance(page);
  await pick(page, "p441.pdf", p441Pdf());
  await expect(page.locator("#wwRelayImportSummary")).toHaveText(P441_SUMMARY);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});

// ---------------------------------------------------------------------------
// Slice 7 -- Extraction Review (read-only). Reviewed, never applied.
// ---------------------------------------------------------------------------

// Enough non-distance settings to need pagination in "Other extracted settings".
const OTHER_ROWS = Array.from({ length: 40 }, (_, i) => [`5${String(i).padStart(3, "0")}`, `Recorder Channel ${i + 1}`, "Enabled", "Enabled/Disabled"]);

async function reviewP441(page) {
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal_with_tilt", append: OTHER_ROWS }));
  await expect(page.locator("#wwRelayImportSummary")).toHaveText(P441_SUMMARY);
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
}
const group = (page, id) => page.locator(`#wwRelayReviewPanel details[data-group="${id}"]`);
const item = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);

test("Review button shows only for an interpreted relay", async ({ page }) => {
  await openDistance(page);
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await pick(page, "unknown.pdf", PDF);
  await expect(page.locator("#wwRelayImportStatus")).toContainText("raw entries");
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await pickIdentifiedOnly(page); // identified, but not interpreted
  await expect(page.locator("#wwRelayImportDetail")).toHaveText("Relay identified. Settings have not been interpreted yet.");
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await pick(page, "p441.pdf", p441Pdf());
  await expect(page.locator("#wwRelayReviewBtn")).toBeVisible();
  await expect(page.locator("#wwRelayReviewBtn")).toHaveText("Review Extracted Settings");
  await expect(page.locator("#wwRelayReviewPanel")).toBeHidden(); // closed until asked for
});

test("review opens and closes, and a new upload or Remove discards it", async ({ page }) => {
  await reviewP441(page);
  await expect(page.locator("#wwRelayReviewBtn")).toHaveAttribute("aria-expanded", "true");
  await page.locator("#wwRelayReviewCloseBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeHidden();
  await expect(page.locator("#wwRelayReviewBtn")).toHaveAttribute("aria-expanded", "false");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
  await page.locator("#wwRelayReviewBtn").click(); // the entry button toggles too
  await expect(page.locator("#wwRelayReviewPanel")).toBeHidden();
  await page.locator("#wwRelayReviewBtn").click();
  await page.locator("#wwRelayImportRemoveBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeHidden();
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await expect(page.locator("#wwRelayReviewBody")).toBeEmpty();
});

test("review summary names the relay, profile, zones and counts", async ({ page }) => {
  await reviewP441(page);
  const summary = page.locator("#wwRelayReviewSummary");
  await expect(summary).toContainText("Schneider Electric · MiCOM P44x · P441");
  await expect(summary).toContainText("Profile micom-p441-v1 · 5 zones");
  await expect(summary).toContainText(/\d+ mapped/);
  await expect(summary).toContainText(/\d+ assumptions/);
  await expect(summary).toContainText(/\d+ missing/);
  await expect(summary).toContainText(/\d+ not yet supported/);
  await expect(summary).toContainText(/\d+ not interpreted/);
});

test("engine compatibility is separate from interpretation quality and explains the blockers", async ({ page }) => {
  await reviewP441(page);
  const engine = page.locator("#wwRelayReviewEngine");
  await expect(engine).toContainText("Interpretation: Complete enough for review");
  await expect(engine).toContainText("Current engine compatibility: Not ready to apply");
  await expect(engine).toContainText("Interpretation succeeded, but the current Distance Protection engine cannot fully apply this scheme yet.");
  await expect(engine).toContainText(/Left Resistive Reach \(−R\) is unresolved/);
  // It is a note in the review, never an upload error.
  await expect(page.locator("#wwRelayImportError")).toBeHidden();
});

test("P441 review shows CT/VT, line data and a section per zone", async ({ page }) => {
  await reviewP441(page);
  await expect(item(page, "ct.primary")).toContainText("1200 A");
  await expect(item(page, "ct.secondary")).toContainText("1 A");
  await expect(item(page, "vt.primary")).toContainText("132000 V");
  await expect(item(page, "vt.secondary")).toContainText("110 V");
  await expect(item(page, "basis")).toContainText("Secondary");
  await expect(item(page, "line.length")).toContainText("7.03 km");
  await expect(item(page, "line.angle")).toContainText("80°");
  await expect(item(page, "line.line_impedance_magnitude")).toContainText("2 Ω");
  const titles = await page.locator("#wwRelayReviewPanel details.ww-rr-group > summary").allInnerTexts();
  for (const t of ["Relay / source information", "CT / VT", "Protected line", "Residual compensation", "Other extracted settings"]) {
    expect(titles.some((x) => x.startsWith(t)), t).toBeTruthy();
  }
  for (const id of ["Z1", "Z2", "Z3", "Z4", "ZP"]) await expect(group(page, `zone-${id}`)).toBeVisible();
  await expect(item(page, "zone.Z1.reach")).toContainText("1.43 Ω");
  await expect(item(page, "zone.Z1.rr.pe")).toContainText("7.02 Ω");
  await expect(item(page, "zone.Z1.rr.pp")).toContainText("2.11 Ω");
  await expect(item(page, "zone.Z2.timer")).toContainText("0.3 s");
  await expect(item(page, "zone.Z3.reach")).toContainText("4.48 Ω");
  await expect(item(page, "comp.Z1.k0_magnitude")).toContainText("0.718");
});

test("mapped, assumption and missing states are all visible", async ({ page }) => {
  await reviewP441(page);
  await expect(item(page, "ct.primary")).toContainText("Mapped");
  await expect(item(page, "zone.Z1.reach")).toContainText("Assumption");
  await expect(item(page, "zone.Z1.reach.angle")).toContainText("Assumption");
  await expect(item(page, "zone.Z1.rr.reverse")).toContainText("Source value missing");
  await expect(item(page, "zone.Z1.rr.reverse")).toHaveAttribute("data-status", "unresolved");
  await expect(item(page, "ct.primary")).toHaveAttribute("data-status", "mapped");
  await expect(item(page, "zone.Z1.reach")).toHaveAttribute("data-status", "inferred");
});

test("Zone 4 shows disabled / defeated while keeping its numbers; Zone P is an inferred Disabled assumption", async ({ page }) => {
  await reviewP441(page);
  await expect(group(page, "zone-Z4").locator("summary")).toHaveText("Zone 4 — Disabled / Defeated");
  await expect(item(page, "zone.Z4.status")).toContainText("Disabled / Defeated");
  await expect(item(page, "zone.Z4.reach")).toContainText("0.36 Ω");
  await expect(item(page, "zone.Z4.timer")).toContainText("3 s");
  await expect(item(page, "zone.Z4.rr.pe")).toContainText("17.19 Ω");
  // the 10 s delay defeats Zone P: no decoded state, so Disabled is inferred (an Assumption)
  await expect(group(page, "zone-ZP").locator("summary")).toHaveText("Zone P — Disabled · Assumption");
  await expect(item(page, "zone.ZP.status")).toContainText("Assumption");
  await expect(item(page, "zone.ZP.status")).toHaveAttribute("data-status", "inferred");
  await expect(item(page, "zone.ZP.reach")).toContainText("0.001 Ω");
  await expect(item(page, "zone.ZP.timer")).toContainText("10 s");
});

test("provenance is collapsed by default and opens in place", async ({ page }) => {
  await reviewP441(page);
  const row = item(page, "zone.Z1.rr.pe");
  const toggle = row.getByRole("button", { name: "Source of Zone 1 Earth Resistive Reach" });
  const prov = row.locator(".ww-rr-prov");
  await expect(prov).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(prov).toBeVisible();
  await expect(prov).toContainText("Zone 1 Earth Resistive Reach — 7.02 Ω — Mapped");
  await expect(prov).toContainText("300C · R1G");
  await expect(prov).toContainText(/Page \d+ · line \d+/);
  await expect(prov).toContainText("Raw: 7.02");
  // DEC-195: the phase-earth reach is catalog-owned, so the catalog version is its provenance
  await expect(prov).toContainText("Profile: schneider-micom-p44x-catalog-v1.0.0");
  await expect(prov).toContainText("Canonical: distance.zone.r_phase_earth");
  await expect(prov).not.toContainText(/[A-Za-z]:\\|\/tmp\//);
  await toggle.click();
  await expect(prov).toBeHidden();
  // The page did not navigate and the review is still open.
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
});

test("inferred and unresolved items explain themselves in their provenance", async ({ page }) => {
  await reviewP441(page);
  const inferred = item(page, "zone.Z1.reach");
  await inferred.getByRole("button", { name: /Source of/ }).click();
  await expect(inferred.locator(".ww-rr-prov")).toContainText(/Assumption: .*line angle/);
  await expect(inferred.locator(".ww-rr-prov")).toContainText("300A · Z1");
  await expect(inferred.locator(".ww-rr-prov")).toContainText("3005 · Line Angle");
  const zp = item(page, "zone.ZP.status");
  await zp.getByRole("button", { name: /Source of/ }).click();
  await expect(zp.locator(".ww-rr-prov")).toContainText("Assumption: No explicit zone status was available.");
  await expect(zp.locator(".ww-rr-prov")).toContainText("defeated/inactive distance zone");
  await expect(zp.locator(".ww-rr-prov")).toContainText("Raw: 10");
  const reverse = item(page, "zone.Z1.rr.reverse");
  await reverse.getByRole("button", { name: /Source of/ }).click();
  await expect(reverse.locator(".ww-rr-prov")).toContainText("No value is stated in the document.");
});

test("tilt settings are preserved as unsupported, and other settings stay secondary and paginated", async ({ page }) => {
  await reviewP441(page);
  await expect(group(page, "zone-Z1").locator("li", { hasText: "Z1m Tilt Angle" })).toContainText("Not yet supported");
  const other = page.locator("#wwRelayReviewOther");
  await expect(other).not.toHaveAttribute("open", "");
  await expect(other.locator(".ww-rr-other-row")).toHaveCount(0); // closed: nothing dumped into view
  await other.locator("summary").click();
  const outside = other.locator('[data-list="out_of_scope"]');
  await expect(outside.locator(".ww-rr-other-row")).toHaveCount(25);
  const first = outside.locator(".ww-rr-other-row").first();
  await expect(first).toContainText(/\d{4}/);
  await expect(first).toContainText(/Page \d+ · line \d+/);
  await outside.getByRole("button", { name: /Show more/ }).click();
  expect(await outside.locator(".ww-rr-other-row").count()).toBeGreaterThan(25);
  await expect(outside.locator(".ww-rr-other-row", { hasText: "Recorder Channel 1" }).first()).toBeVisible();
});

test("the review is read-only: no Apply, Accept or Populate, and the manual form is untouched", async ({ page }) => {
  await openDistance(page);
  const inputs = ["#wwDistanceZone1ReachInput", "#wwDistanceZone2ReachInput", "#wwDistanceZone2DelayInput"];
  const before = [];
  for (const sel of inputs) before.push(await page.locator(sel).inputValue());
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal_with_tilt" }));
  await page.locator("#wwRelayReviewBtn").click();
  await expect(page.locator("#wwRelayReviewPanel")).toBeVisible();
  await page.locator("#wwRelayReviewPanel").getByRole("button", { name: "Source of Zone 1 Reach", exact: true }).click();
  const buttons = await page.locator("#wwRelayImportPanel button").allInnerTexts();
  for (const text of buttons) expect(text).not.toMatch(/apply|accept|populate|generate|auto-?fill|use these/i);
  await expect(page.locator("#wwRelayReviewPanel input, #wwRelayReviewPanel select, #wwRelayReviewPanel textarea")).toHaveCount(0);
  for (let i = 0; i < inputs.length; i++) await expect(page.locator(inputs[i])).toHaveValue(before[i]);
  // The review content is plain text, never parsed as HTML.
  expect(await page.locator("#wwRelayReviewBody script, #wwRelayReviewBody img").count()).toBe(0);
});

test("review state is in tab memory only and disappears on refresh", async ({ page }) => {
  await reviewP441(page);
  const snapshot = () =>
    page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage }, cookies: document.cookie }));
  const stored = await snapshot();
  for (const value of ["1200", "7.02", "132000", "R1G", "micom"]) expect(stored).not.toContain(value);
  await page.reload();
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeDistanceBtn").click();
  await expect(page.locator("#wwDistancePanel")).toBeVisible();
  await expect(page.locator("#wwRelayReviewBtn")).toBeHidden();
  await expect(page.locator("#wwRelayReviewPanel")).toBeHidden();
  await expect(page.locator("#wwRelayReviewBody")).toBeEmpty();
});

test("review layout is contained, readable and has no horizontal overflow at narrow width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await reviewP441(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const box = await page.locator("#wwRelayReviewPanel").boundingBox();
  expect(box.width).toBeLessThanOrEqual(390);
  const panelOverflow = await page.locator("#wwRelayReviewPanel").evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(panelOverflow).toBeLessThanOrEqual(1);
});

test("review is legible in light and dark themes", async ({ page }) => {
  await reviewP441(page);
  for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    const contrast = await page.locator("#wwRelayReviewPanel").evaluate((panel) => {
      const parse = (c) => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
      const lum = ([r, g, b]) => {
        const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      };
      const label = panel.querySelector(".ww-rr-value");
      const fg = lum(parse(getComputedStyle(label).color));
      const bg = lum(parse(getComputedStyle(panel).backgroundColor));
      return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
    });
    expect(contrast, theme).toBeGreaterThan(4.5);
  }
});
