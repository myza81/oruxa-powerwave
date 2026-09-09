// DEC-084 (Slice 4) focused browser test: Raw Data Preview Data Quality
// summary + Data Issues side panel. Same conventions as smoke.spec.js
// (real backend + real frontend, no mocking) -- see that file's own
// header comment for the shared rationale.
//
// Setup (CSV upload, column roles, Time Axis save) is driven through the
// APP'S OWN already-existing functions via page.evaluate() rather than
// clicking through the full Time Axis wizard UI step by step -- this
// keeps the test focused on the NEW Data Issues panel behavior (the
// actual subject of this slice) instead of re-proving the unrelated,
// already-covered Time Axis configuration UI. Every one of those calls
// is a REAL function this same page already defines and every other
// user-facing button already calls -- never a parallel/simulated path.
// The Data Issues panel itself (open/close, coordinate click, page
// navigation, Mark as Null, Undo/Redo, Time Axis guardrail) is exercised
// through real clicks only.

const { test, expect } = require("@playwright/test");

const CSV_CONTENT = [
  "2026-08-31 13:00:00,10.0",
  "2026-08-31 13:00:01,",
  "2026-08-31 13:00:02,ERR",
  "2026-08-31 13:00:03,13.0",
].join("\n") + "\n";

test("Data Preparation: Data Quality summary + Data Issues panel", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Setup - upload a CSV with one blank and one invalid waveform cell", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "issues.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(CSV_CONTENT),
    });
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    const row = page.locator('#recordingsTableBody tr[data-source-id][data-recording-kind="csv"]').first();
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.locator("#pageDataPreparation")).toBeVisible();
  });

  await test.step("Setup - column roles + Time Axis via the app's own existing functions", async () => {
    // Column 0 = Time Axis, column 1 = Waveform -- reuses
    // wwDataPrepSetColumnRole(), the SAME function the Column Roles
    // <select>'s own change handler already calls.
    await page.evaluate(async () => {
      await wwDataPrepSetColumnRole(0, "time_axis");
      await wwDataPrepSetColumnRole(1, "waveform");
    });
    // Time Axis save -- the exact PUT .../working/time-axis body a real
    // Save click sends for an unambiguous absolute_datetime column.
    await page.evaluate(async () => {
      // wwDataPrep/wwDataPrepSourceUrl/wwDataPrepFetchPreview are all
      // top-level `const`/`function` bindings in the page's own single
      // classic <script> -- visible here as bare identifiers in this
      // same realm (a `const` never becomes a `window.*` property, so
      // `window.wwDataPrep` would be undefined; the bare name is what
      // actually resolves).
      const response = await fetch(
        wwDataPrepSourceUrl("/working/time-axis"),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            column_indices: [0], interpreter_id: "absolute_datetime",
            unit: null, interval_seconds: null, options: {}, confirmed: true,
          }),
        }
      );
      if (!response.ok) throw new Error("Time Axis save failed: " + (await response.text()));
      wwDataPrep.timeAxisSummary = await response.json();
      await wwDataPrepFetchPreview();
    });
    // Data Quality summary now reflects the real backend readiness scan
    // (never a second frontend validator) -- 2 unresolved cells: the
    // blank on row 2, the invalid "ERR" on row 3.
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/2 unresolved cells/);
  });

  await test.step("Data Issues panel opens via Review Issues, stays open, shows grouped coordinates", async () => {
    const panel = page.locator("#wwDataIssuesPanel");
    await expect(panel).toHaveAttribute("data-open", "false");
    await page.locator("#wwDataQualityReviewBtn").click();
    await expect(panel).toHaveAttribute("data-open", "true");
    await expect(page.locator("#wwDataIssuesPanelToggleBtn")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#wwDataIssuesPanelCount")).toHaveText("2");
    // Grouped under "Empty cells" (B2) and "Invalid values" (B3) --
    // exact coordinate text, never a generic "row 2" label.
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|2|1"]')).toHaveText("B2");
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]')).toContainText("B3");
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]')).toContainText("ERR");
  });

  await test.step("The blank cell is visually highlighted as unresolved in the table", async () => {
    const cell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="2"][data-col="1"]');
    await expect(cell).toHaveClass(/ww-data-prep-cell-issue-missing/);
  });

  await test.step("Clicking a coordinate jumps to that cell and keeps the panel open", async () => {
    await page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]').click();
    const cell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="3"][data-col="1"]');
    await expect(cell).toBeVisible();
    await expect(cell).toHaveClass(/ww-data-prep-cell-issue-selected/);
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");
    // The action area now targets row 3 / column 1, and (a Waveform
    // cell) DOES offer Mark as Null.
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="mark-null"]')).toBeVisible();
  });

  await test.step("Mark as Null resolves the cell: it disappears from the issue list, count decrements, cell shows NULL", async () => {
    await page.locator('#wwDataIssuesActionArea [data-issue-action="mark-null"]').click();
    await expect(page.locator("#wwDataIssuesPanelCount")).toHaveText("1");
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/1 unresolved cell\b/);
    const cell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="3"][data-col="1"]');
    await expect(cell).toHaveClass(/ww-data-prep-cell-explicit-null/);
    await expect(cell.locator(".ww-data-prep-null-badge")).toHaveText("NULL");
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]')).toHaveCount(0);
  });

  await test.step("Undo restores the issue; Redo resolves it again", async () => {
    await page.locator("#wwDataPrepUndoBtn").click();
    await expect(page.locator("#wwDataIssuesPanelCount")).toHaveText("2");
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]')).toBeVisible();

    await page.locator("#wwDataPrepRedoBtn").click();
    await expect(page.locator("#wwDataIssuesPanelCount")).toHaveText("1");
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|3|1"]')).toHaveCount(0);
  });

  await test.step("Time Axis issue never exposes Mark as Null", async () => {
    // Explicit-null the Time Axis cell directly via the API (Slice 1) so
    // a real time_value_missing cell issue exists to select -- this is
    // the one state the normal UI can never itself create (this slice's
    // own guardrail), so it is seeded here purely to prove the panel's
    // OWN rendering rule holds even for it.
    await page.evaluate(async () => {
      const response = await fetch(
        wwDataPrepSourceUrl("/working/cells/1/0"),
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "null" }) }
      );
      if (!response.ok) throw new Error("Time Axis null seed failed: " + (await response.text()));
      await wwDataPrepFetchPreview();
    });
    const timeAxisCoordinate = page.locator('.ww-data-issue-coordinate[data-issue-key$="|1|0"]');
    await expect(timeAxisCoordinate).toBeVisible();
    await timeAxisCoordinate.click();
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="mark-null"]')).toHaveCount(0);
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="fill-manually"]')).toBeVisible();
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="configure-time-axis"]')).toBeVisible();
  });

  await test.step("No bulk-action controls exist anywhere in the panel", async () => {
    await expect(page.locator("#wwDataIssuesPanel")).not.toContainText("Mark all as Null");
    await expect(page.locator("#wwDataIssuesPanel").locator('input[type="checkbox"]')).toHaveCount(0);
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
