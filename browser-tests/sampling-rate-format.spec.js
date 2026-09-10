// Real-browser regression for the Recording Events "Sampling Rate(s)"
// display fix (owner UAT, 2026-09-10): a CSV/Excel source with a genuine
// 60-second sample interval showed "0.0166666666667 Hz" -- audited and
// confirmed NOT a derivation bug (1/60 Hz is the mathematically correct
// rate for 60s-spaced samples; see
// backend/tests/test_preparation_conversion_service.py::TestSamplingMetadata::test_sixty_second_interval_source_derives_one_sixtieth_hz).
// Only the frontend's own formatSamplingRate() needed a display-precision
// fix (frontend/index.html). See data-issues-panel.spec.js's own header
// comment for the shared setup convention this reuses (CSV upload +
// column roles + Time Axis save driven through the app's own existing
// functions, not the full wizard UI, to keep this test focused on the
// actual subject).

const { test, expect } = require("@playwright/test");

const CSV_CONTENT = [
  "2026-08-31 13:00:00,0",
  "2026-08-31 13:01:00,1",
  "2026-08-31 13:02:00,2",
  "2026-08-31 13:03:00,3",
  "2026-08-31 13:04:00,4",
].join("\n") + "\n";

test("Recording Events Sampling Rate(s): a genuine 1/60 Hz rate renders cleanly, without a floating-point tail", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  let sourceId;

  await test.step("Upload a CSV with a genuine 60s sample interval", async () => {
    await page.goto("/index.html");
    await expect(page.locator("#pageRecordings")).toBeVisible();

    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFormatSelect").selectOption("csv");
    await page.locator("#uploadModalFile_0").setInputFiles({
      name: "sixty-second-interval.csv",
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

  await test.step("Configure column roles + Time Axis via the app's own existing functions", async () => {
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
    await expect(page.locator("#wwDataPrepConvertBtn")).toBeEnabled();
  });

  await test.step("Convert to a real Powerwave source", async () => {
    // wwDataPrepConvert() itself navigates into the Waveform page on
    // success (openRecordingForAnalysis()) -- POST directly and read the
    // real source_id back, the same call the Convert button's own click
    // handler makes, then apply the SAME post-success side effects
    // (refreshAllSourceViews + navigate) so this is not a second,
    // divergent conversion path.
    sourceId = await page.evaluate(async () => {
      const response = await fetch(wwDataPrepSourceUrl("/convert"), { method: "POST" });
      if (!response.ok) throw new Error("Convert failed: " + (await response.text()));
      const body = await response.json();
      await refreshAllSourceViews();
      openRecordingForAnalysis(body.source_id);
      return body.source_id;
    });
    expect(sourceId).toBeTruthy();
    await expect(page.locator("#workspaceRow")).toBeVisible();
  });

  await test.step("Back on Recordings: the Sampling Rate(s) cell shows a clean value, no floating-point tail", async () => {
    await page.locator("#mainNavRecordingsBtn").click();
    await expect(page.locator("#pageRecordings")).toBeVisible();

    const row = page.locator(`#recordingsTableBody tr[data-source-id="${sourceId}"]`);
    await expect(row).toBeVisible();

    const cell = row.locator("td.recording-sampling-rates-cell");
    await expect(cell).toHaveText("0.01667 Hz");
    const text = await cell.textContent();
    // The actual reported bug: a raw floating-point tail this long.
    expect(text).not.toContain("0.0166666666667");
    expect(text.replace(" Hz", "").replace(/^\d*\.?/, "").length).toBeLessThanOrEqual(5);
  });

  await test.step("An integer-like COMTRADE rate still renders cleanly alongside it", async () => {
    // Reuses the existing synth_ascii COMTRADE fixture (4000 Hz, exact) --
    // proves the fix does not regress the already-correct integer path.
    const path = require("path");
    const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
    await page.locator("#recordingsUploadBtn").click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });

    // .last() -- newly uploaded/converted rows are appended, and our
    // already-converted CSV source now ALSO carries
    // data-recording-kind="comtrade" (every real registered source does,
    // regardless of original format; only a not-yet-converted
    // "Needs Preparation" row keeps its own csv/excel kind).
    const row = page.locator('#recordingsTableBody tr[data-source-id][data-recording-kind="comtrade"]').last();
    await expect(row).toBeVisible();
    await expect(row.locator("td.recording-sampling-rates-cell")).toHaveText("4000 Hz");
  });

  await test.step("Zero unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
