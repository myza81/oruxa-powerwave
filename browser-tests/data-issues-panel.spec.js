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

  await test.step("Single-cell action area still has no bulk/checkbox controls of its own", async () => {
    // The per-cell action area (Selected: <coordinate> -- ...) predates
    // Slice 5's SEPARATE column-group-level bulk buttons (covered in
    // their own dedicated test below) and never grows a checkbox/
    // selection mechanism of its own.
    await expect(page.locator("#wwDataIssuesActionArea").locator('input[type="checkbox"]')).toHaveCount(0);
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});

// DEC-084 (Slice 5) focused browser test: bulk explicit-null resolution.
// Same setup convention as the Slice 4 test above (real backend + real
// frontend, column roles/Time Axis wired through the app's own existing
// functions via page.evaluate(), the actual bulk UI exercised through
// real clicks only). 35 blank Waveform cells deliberately exceeds
// WW_DATA_ISSUES_INITIAL_VISIBLE (30) so the group's own displayed
// coordinate list is capped while the bulk button's own count must still
// be the true, uncapped 35 (task section 21/34's own "a group whose
// total count exceeds the displayed coordinate list" scenario) -- a
// single explicit-null Time Axis cell (Slice 1: stays permanently
// BLOCKING/unresolved, unlike a Waveform explicit null -- the same
// technique the Slice 4 test above already uses to seed a real
// time_value_missing cell issue) proves the guardrail holds for a real,
// backend-classified group too, not just a hypothetical one.
test("Data Preparation: bulk explicit-null resolution (DEC-084 Slice 5)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  const lines = [];
  for (let i = 0; i < 41; i++) {
    const minute = String(i).padStart(2, "0");
    const value = i < 35 ? "" : `${i}.0`; // rows 1-35 blank Waveform, rows 36-41 real
    lines.push(`2026-08-31 13:${minute}:00,${value}`);
  }
  const BULK_CSV_CONTENT = lines.join("\n") + "\n";

  await test.step("Setup - upload a CSV with 35 blank Waveform cells", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "bulk-issues.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(BULK_CSV_CONTENT),
    });
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    const row = page.locator('#recordingsTableBody tr[data-source-id][data-recording-kind="csv"]').first();
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.locator("#pageDataPreparation")).toBeVisible();

    await page.evaluate(async () => {
      await wwDataPrepSetColumnRole(0, "time_axis");
      await wwDataPrepSetColumnRole(1, "waveform");
    });
    await page.evaluate(async () => {
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
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/35 unresolved cells/);
  });

  await test.step("Seed one real Time Axis cell issue via explicit null (Slice 1: stays permanently blocking)", async () => {
    // Same technique the Slice 4 test above uses -- a Time Axis explicit
    // null is the one way the normal UI can create a genuine, still-
    // unresolved time_value_missing cell issue (unlike a Waveform
    // explicit null, which resolves/clears its own issue).
    await page.evaluate(async () => {
      const response = await fetch(
        wwDataPrepSourceUrl("/working/cells/41/0"),
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "null" }) }
      );
      if (!response.ok) throw new Error("Time Axis null seed failed: " + (await response.text()));
      await wwDataPrepFetchPreview();
    });
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/36 unresolved cells/);
  });

  await test.step("Bulk button appears on the eligible Waveform group with the authoritative, uncapped count", async () => {
    await page.locator("#wwDataQualityReviewBtn").click();
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");

    const bulkBtn = page.locator('.ww-data-issues-bulk-null-btn[data-bulk-null-issue-code="waveform_value_missing"]');
    await expect(bulkBtn).toBeVisible();
    // The button starts as a placeholder, then resolves to the real,
    // AUTHORITATIVE backend count once the background preview fetch
    // returns -- never the (here, capped-at-30) displayed coordinate list length.
    await expect(bulkBtn).toHaveText("Mark all 35 as Null");
    await expect(page.locator('.ww-data-issue-coordinate')).toHaveCount(30 + 1); // 30 waveform + 1 time-axis
    await expect(page.locator('.ww-data-issues-load-more')).toBeVisible();
  });

  await test.step("The Time Axis group (blank time cell) has no bulk-null button", async () => {
    const timeAxisGroup = page.locator('.ww-data-issues-column-group', {
      has: page.locator('.ww-data-issue-coordinate[data-issue-key$="|41|0"]'),
    });
    await expect(timeAxisGroup).toBeVisible();
    await expect(timeAxisGroup.locator('.ww-data-issues-bulk-null-btn')).toHaveCount(0);
  });

  await test.step("Confirmation dialog shows the column, issue type, and authoritative count", async () => {
    await page.locator('.ww-data-issues-bulk-null-btn[data-bulk-null-issue-code="waveform_value_missing"]').click();
    const overlay = page.locator("#wwDataIssuesBulkNullOverlay");
    await expect(overlay).toBeVisible();
    await expect(page.locator("#wwDataIssuesBulkNullTitle")).toContainText("B");
    await expect(page.locator("#wwDataIssuesBulkNullCount")).toContainText("35 empty cells");
    await expect(page.locator("#wwDataIssuesBulkNullCount")).toContainText(
      "Other valid cells in the same rows will not be changed."
    );
    await expect(page.locator("#wwDataIssuesBulkNullConfirmBtn")).toHaveText("Mark 35 as Null");
  });

  await test.step("Cancel performs no mutation", async () => {
    await page.locator("#wwDataIssuesBulkNullCancelBtn").click();
    await expect(page.locator("#wwDataIssuesBulkNullOverlay")).toBeHidden();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/36 unresolved cells/);
  });

  await test.step("Escape closes the dialog with no mutation", async () => {
    await page.locator('.ww-data-issues-bulk-null-btn[data-bulk-null-issue-code="waveform_value_missing"]').click();
    await expect(page.locator("#wwDataIssuesBulkNullOverlay")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#wwDataIssuesBulkNullOverlay")).toBeHidden();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/36 unresolved cells/);
  });

  await test.step("Confirm resolves the whole group, the panel stays open, count updates", async () => {
    await page.locator('.ww-data-issues-bulk-null-btn[data-bulk-null-issue-code="waveform_value_missing"]').click();
    await expect(page.locator("#wwDataIssuesBulkNullConfirmBtn")).toHaveText("Mark 35 as Null");
    await page.locator("#wwDataIssuesBulkNullConfirmBtn").click();
    await expect(page.locator("#wwDataIssuesBulkNullOverlay")).toBeHidden();

    // Only the 1 blank Time Axis cell remains unresolved -- the whole
    // Waveform group is gone, and the panel is still open (task section 18).
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/1 unresolved cell\b/);
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");
    await expect(page.locator('.ww-data-issues-bulk-null-btn[data-bulk-null-issue-code="waveform_value_missing"]')).toHaveCount(0);
    // Every one of the 35 cells shows the resolved NULL badge.
    const nullCell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="1"][data-col="1"]');
    await expect(nullCell).toHaveClass(/ww-data-prep-cell-explicit-null/);
  });

  await test.step("Undo restores the whole group in one press; Redo resolves it again", async () => {
    await page.locator("#wwDataPrepUndoBtn").click();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/36 unresolved cells/);
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|1|1"]')).toBeVisible();

    await page.locator("#wwDataPrepRedoBtn").click();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/1 unresolved cell\b/);
  });

  await test.step("<=820px: Reset All confirmation renders above the open Data Issues panel and stays clickable", async () => {
    // Post-Slice-5 review finding: the Data Issues panel is its own
    // position: fixed overlay (z-index: 40) at this breakpoint, and it is
    // still open (data-open="true") from the earlier steps -- Reset All's
    // own confirmation dialog previously shared .confirm-overlay's plain
    // z-index: 10 and would render BENEATH the panel here, exactly like
    // the bulk-null dialog originally did. #wwDataPrepResetAllOverlay now
    // has the same scoped z-index: 41 fix.
    await page.setViewportSize({ width: 820, height: 900 });
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");

    await page.locator("#wwDataPrepResetAllBtn").click();
    const overlay = page.locator("#wwDataPrepResetAllOverlay");
    await expect(overlay).toBeVisible();

    // Cancel must actually be clickable -- not intercepted by the panel
    // sitting on top of it -- and must perform no mutation.
    await page.locator("#wwDataPrepResetAllCancelBtn").click();
    await expect(overlay).toBeHidden();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/1 unresolved cell\b/);

    // Confirm is also reachable/clickable from behind the drawer, and the
    // real Reset All action completes: every working change (including
    // the bulk-resolved explicit nulls and the column role assignments
    // themselves) is discarded, so no cell-level issues remain to report.
    await page.locator("#wwDataPrepResetAllBtn").click();
    await expect(overlay).toBeVisible();
    await page.locator("#wwDataPrepResetAllConfirmBtn").click();
    await expect(overlay).toBeHidden();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText("No unresolved data-cell issues");
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
