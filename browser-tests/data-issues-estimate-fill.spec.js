// Missing-value fill/estimation enhancement (owner UAT, 2026-09-10)
// focused browser test: single-cell "Estimate Missing Value" and
// group-level "Fill / Estimate Missing Values" (Constant Value + the
// four algorithmic methods), against the real backend endpoints added
// in commit e60e830. Same conventions as data-issues-panel.spec.js
// (real backend + real frontend, no mocking; setup driven through the
// app's own existing functions via page.evaluate(), the actual new
// dialogs exercised through real clicks only) -- see that file's own
// header comment for the shared rationale.

const { test, expect } = require("@playwright/test");

// 10 rows: an isolated single-row missing gap (row 4, single-cell
// Estimate target) and a 3-row mixed missing/invalid gap (rows 7-9:
// blank / "abc" / blank) whose bulk Fill/Estimate preview must report
// matching_count (2, the empty cells alone) distinctly from
// affected_count (3, the full contiguous gap including the invalid
// middle cell) -- task sections 4/11's own required transparency.
const MIXED_GAP_CSV = [
  "2026-08-31 13:00:00,1.0",
  "2026-08-31 13:00:01,2.0",
  "2026-08-31 13:00:02,3.0",
  "2026-08-31 13:00:03,",
  "2026-08-31 13:00:04,5.0",
  "2026-08-31 13:00:05,6.0",
  "2026-08-31 13:00:06,",
  "2026-08-31 13:00:07,abc",
  "2026-08-31 13:00:08,",
  "2026-08-31 13:00:09,10.0",
].join("\n") + "\n";

test("Data Issues: single-cell Estimate Missing Value + mixed-gap transparency + Time Axis guardrail", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Setup - upload a CSV with an isolated gap and a mixed missing/invalid gap", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "estimate.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(MIXED_GAP_CSV),
    });
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    const row = page.locator('#recordingsTableBody tr[data-source-id][data-recording-kind="csv"]').first();
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.locator("#pageDataPreparation")).toBeVisible();
  });

  await test.step("Setup - column roles + Time Axis via the app's own existing functions", async () => {
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
    // 4 unresolved cells: row 4 (blank), row 7 (blank), row 8 (invalid), row 9 (blank).
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/4 unresolved cells/);
  });

  await test.step("Open Data Issues and select the isolated missing cell (row 4)", async () => {
    await page.locator("#wwDataQualityReviewBtn").click();
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");
    await page.locator('.ww-data-issue-coordinate[data-issue-key$="|4|1"]').click();
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="estimate"]')).toBeVisible();
  });

  await test.step("Estimate Missing Value: Linear, preview shows the exact count, Apply", async () => {
    await page.locator('#wwDataIssuesActionArea [data-issue-action="estimate"]').click();
    const overlay = page.locator("#wwDataIssuesEstimateOverlay");
    await expect(overlay).toBeVisible();
    await expect(page.locator("#wwDataIssuesEstimateCellLabel")).toHaveText("Cell B4");
    await page.locator("#wwDataIssuesEstimateMethodSelect").selectOption("linear");
    await page.locator("#wwDataIssuesEstimateMaxGapInput").fill("3");
    await expect(page.locator("#wwDataIssuesEstimateCount")).toContainText("Matching issue cells: 1");
    await expect(page.locator("#wwDataIssuesEstimateCount")).toContainText("Values that will be estimated: 1");
    const confirmBtn = page.locator("#wwDataIssuesEstimateConfirmBtn");
    await expect(confirmBtn).toBeEnabled();
    await expect(confirmBtn).toHaveText("Estimate 1 Value");
    await confirmBtn.click();
    await expect(overlay).toBeHidden();
  });

  await test.step("The issue disappears and the cell visibly shows the Estimated state", async () => {
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|4|1"]')).toHaveCount(0);
    const cell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="4"][data-col="1"]');
    await expect(cell).toHaveClass(/ww-data-prep-cell-estimated/);
    await expect(cell.locator(".ww-data-prep-estimated-badge")).toHaveText("Estimated");
  });

  await test.step("Undo restores the issue; Redo restores the Estimated state", async () => {
    await page.locator("#wwDataPrepUndoBtn").click();
    const cell = page.locator('#wwDataPrepTable td.ww-data-prep-cell[data-row="4"][data-col="1"]');
    await expect(cell).not.toHaveClass(/ww-data-prep-cell-estimated/);
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|4|1"]')).toBeVisible();

    await page.locator("#wwDataPrepRedoBtn").click();
    await expect(cell).toHaveClass(/ww-data-prep-cell-estimated/);
    await expect(page.locator('.ww-data-issue-coordinate[data-issue-key$="|4|1"]')).toHaveCount(0);
  });

  await test.step("Bulk Fill / Estimate from the Empty values group: mixed gap reports matching != affected", async () => {
    const bulkFillBtn = page.locator('.ww-data-issues-bulk-fill-btn[data-bulk-fill-issue-code="waveform_value_missing"]').first();
    await expect(bulkFillBtn).toBeVisible();
    await bulkFillBtn.click();
    const overlay = page.locator("#wwDataIssuesBulkFillOverlay");
    await expect(overlay).toBeVisible();
    await page.locator("#wwDataIssuesBulkFillMethodSelect").selectOption("linear");
    await page.locator("#wwDataIssuesBulkFillMaxGapInput").fill("3");
    // Only the 3-row mixed gap remains at this point (row 4 was already
    // resolved above): matching (2 empty cells: rows 7 and 9) must
    // differ from affected (3, the full gap including invalid row 8),
    // and the dialog must show BOTH, plus the explanatory note --
    // never silently expanding scope (task section 11).
    await expect(page.locator("#wwDataIssuesBulkFillCount")).toContainText("Matching empty cells: 2");
    await expect(page.locator("#wwDataIssuesBulkFillCount")).toContainText("Values in the full contiguous gap: 3");
    await expect(page.locator("#wwDataIssuesBulkFillCount")).toContainText("Values eligible for estimation: 3");
    await expect(page.locator("#wwDataIssuesBulkFillCount")).toContainText("Values that will remain unresolved: 0");
    await expect(page.locator("#wwDataIssuesBulkFillGapNote")).toBeVisible();
    await page.locator("#wwDataIssuesBulkFillConfirmBtn").click();
    await expect(overlay).toBeHidden();
  });

  await test.step("The full mixed gap -- including the invalid cell -- is estimated together, no cells left unresolved", async () => {
    for (const row of [7, 8, 9]) {
      const cell = page.locator(`#wwDataPrepTable td.ww-data-prep-cell[data-row="${row}"][data-col="1"]`);
      await expect(cell).toHaveClass(/ww-data-prep-cell-estimated/);
      await expect(cell.locator(".ww-data-prep-estimated-badge")).toHaveText("Estimated");
    }
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText("No unresolved data-cell issues");
  });

  await test.step("Time Axis issue never offers Estimate/Fill/Mark-as-Null", async () => {
    // Explicit-null the Time Axis cell directly via the API (same
    // established technique data-issues-panel.spec.js already uses) so
    // a real time_value_missing cell issue exists to select -- the one
    // state the normal UI can never itself create.
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
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="estimate"]')).toHaveCount(0);
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="mark-null"]')).toHaveCount(0);
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="fill-manually"]')).toBeVisible();
    await expect(page.locator('#wwDataIssuesActionArea [data-issue-action="configure-time-axis"]')).toBeVisible();
    // No group-level bulk button for the Time Axis group either.
    const timeAxisGroup = page.locator(".ww-data-issues-column-group", {
      has: page.locator('.ww-data-issue-coordinate[data-issue-key$="|1|0"]'),
    });
    await expect(timeAxisGroup.locator(".ww-data-issues-bulk-fill-btn")).toHaveCount(0);
    await expect(timeAxisGroup.locator(".ww-data-issues-bulk-null-btn")).toHaveCount(0);
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});

// A simple isolated 2-row missing gap -- no mixed classification, so
// Constant Value's own strictly issue-scoped eligible_count (task
// section 10) trivially equals the gap size here; the mixed-gap
// non-expansion distinction itself is locked at the backend level
// (backend/tests/test_missing_value_estimation.py::TestMixedMissingAndInvalidGap)
// and structurally at the frontend level
// (test_frontend_data_issues_panel.py::TestConstantValueStaysIssueScoped) --
// this browser test's own job is the end-to-end Constant Value UI flow
// and the responsive dialog check, not re-proving that distinction again.
const SIMPLE_GAP_CSV = [
  "2026-08-31 14:00:00,1.0",
  "2026-08-31 14:00:01,2.0",
  "2026-08-31 14:00:02,",
  "2026-08-31 14:00:03,",
  "2026-08-31 14:00:04,5.0",
].join("\n") + "\n";

test("Data Issues: bulk Fill / Estimate Missing Values -- Constant Value + responsive dialog", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Setup - upload a CSV with an isolated 2-row missing gap", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "constant-fill.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(SIMPLE_GAP_CSV),
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
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/2 unresolved cells/);
  });

  await test.step("Open Fill / Estimate Missing Values -- Constant Value is the default method", async () => {
    await page.locator("#wwDataQualityReviewBtn").click();
    await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");
    const bulkFillBtn = page.locator('.ww-data-issues-bulk-fill-btn[data-bulk-fill-issue-code="waveform_value_missing"]').first();
    await expect(bulkFillBtn).toBeVisible();
    await bulkFillBtn.click();
    const overlay = page.locator("#wwDataIssuesBulkFillOverlay");
    await expect(overlay).toBeVisible();
    await expect(page.locator("#wwDataIssuesBulkFillMethodSelect")).toHaveValue("constant");
    await expect(page.locator("#wwDataIssuesBulkFillConstantInput")).toBeVisible();
    await expect(page.locator("#wwDataIssuesBulkFillMaxGapInput")).toHaveCount(0);
  });

  await test.step("Enter a value, preview the exact matching count, Apply", async () => {
    await page.locator("#wwDataIssuesBulkFillConstantInput").fill("0");
    await expect(page.locator("#wwDataIssuesBulkFillCount")).toContainText("Matching empty cells: 2");
    await page.locator("#wwDataIssuesBulkFillConfirmBtn").click();
    await expect(page.locator("#wwDataIssuesBulkFillOverlay")).toBeHidden();
  });

  await test.step("The matching issue group disappears and cells show the Filled (never Estimated) state", async () => {
    await expect(page.locator(".ww-data-issues-bulk-fill-btn")).toHaveCount(0);
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText("No unresolved data-cell issues");
    for (const row of [3, 4]) {
      const cell = page.locator(`#wwDataPrepTable td.ww-data-prep-cell[data-row="${row}"][data-col="1"]`);
      await expect(cell).toHaveClass(/ww-data-prep-cell-constant-fill/);
      await expect(cell).not.toHaveClass(/ww-data-prep-cell-estimated/);
      await expect(cell.locator(".ww-data-prep-filled-badge")).toHaveText("Filled");
      await expect(cell.locator(".ww-data-prep-estimated-badge")).toHaveCount(0);
    }
  });

  await test.step("Undo restores the original blank cells and unresolved issues", async () => {
    // Reset All would ALSO discard the column-role/Time-Axis
    // assignments made in Setup (existing, established behavior --
    // see data-issues-panel.spec.js's own Reset All step), leaving no
    // Waveform column to detect issues against at all. Undo reverts
    // only the one grouped constant-fill operation, exactly like the
    // single-cell test above.
    await page.locator("#wwDataPrepUndoBtn").click();
    await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/2 unresolved cells/);
  });

  await test.step("<=820px and <=390px: the bulk dialog renders above the open Data Issues panel and stays clickable", async () => {
    // Same scoped z-index: 41 fix as #wwDataIssuesBulkNullOverlay/
    // #wwDataPrepResetAllOverlay (task section 27) -- proven here the
    // same way data-issues-panel.spec.js proves it for Reset All: a
    // REAL click on Cancel must actually land on the dialog, not be
    // intercepted by the position:fixed panel sitting on top of it.
    for (const width of [820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator("#wwDataIssuesPanel")).toHaveAttribute("data-open", "true");
      const bulkFillBtn = page.locator('.ww-data-issues-bulk-fill-btn[data-bulk-fill-issue-code="waveform_value_missing"]').first();
      await bulkFillBtn.scrollIntoViewIfNeeded();
      await bulkFillBtn.click();
      const overlay = page.locator("#wwDataIssuesBulkFillOverlay");
      await expect(overlay).toBeVisible();
      await page.locator("#wwDataIssuesBulkFillCancelBtn").click();
      await expect(overlay).toBeHidden();
      await expect(page.locator("#wwDataQualitySummaryDetail")).toHaveText(/2 unresolved cells/);
    }
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
