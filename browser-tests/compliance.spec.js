// Compliance & Capability -- Slice 1 (workspace shell only) real-browser
// coverage. Deliberately independent of the Analysis page's own fixture/
// upload machinery: Compliance has no Engineering Context lifecycle, no
// Playback, no backend data dependency of any kind in this slice -- every
// test here starts from a plain, empty workspace.

const { test, expect } = require("@playwright/test");

async function openCompliance(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
}

test.describe("Compliance & Capability -- Slice 1 workspace shell", () => {
  test("Compliance appears after Analysis in the main sidebar", async ({ page }) => {
    await page.goto("/index.html");
    const labels = page.locator("#mainSidebarMenu .shell-nav-list .shell-nav-label");
    await expect(labels).toHaveText([
      "Recordings",
      "Waveform",
      "Table",
      "Calculated Channels",
      "Analysis",
      "Compliance",
    ]);
  });

  test("Compliance opens the correct workspace, replacing Analysis", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await expect(page.locator("#pageAnalysis")).toBeHidden();
    await expect(page.locator("#mainNavComplianceBtn")).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#mainNavAnalysisBtn")).not.toHaveAttribute("aria-current", "page");
  });

  test("Voltage is the current (and only) Compliance sub-function", async ({ page }) => {
    await openCompliance(page);
    const voltageBtn = page.locator("#wwComplianceTypeVoltageBtn");
    await expect(voltageBtn).toBeVisible();
    await expect(voltageBtn).toHaveClass(/active/);
    await expect(voltageBtn).toHaveAttribute("aria-current", "true");
    await expect(page.locator(".ww-analysis-type-nav[aria-label='Compliance function'] .ww-analysis-type-item")).toHaveCount(1);
    await expect(page.locator("#wwComplianceVoltagePanel")).toBeVisible();
    await expect(page.locator("#wwComplianceVoltagePanel .ww-compliance-heading")).toHaveText("Voltage Compliance & Capability");
  });

  test("all five workflow sections exist, in the intended order, with neutral empty states", async ({ page }) => {
    await openCompliance(page);
    const panel = page.locator("#wwComplianceVoltagePanel");
    const headings = panel.locator("h2");
    await expect(headings).toHaveText([
      "Measurement",
      "Reference Layers",
      "Event Alignment",
      "Comparison Chart",
      "Results",
    ]);

    // 2026-09-20 UAT correction: on a fresh empty workspace there is no
    // Measurement Group yet, so this is now the FIRST empty state shown
    // -- selecting a quantity is a later step (see
    // compliance_measurement.spec.js for the full Bay/Measurement Group
    // -> Assessment Quantity workflow coverage).
    await expect(page.locator("#wwComplianceMeasurementEmptyState")).toHaveText("No Measurement Group is available for this workspace.");
    await expect(page.locator("#wwComplianceReferenceLayersEmptyState")).toHaveText("No reference layers added");
    await expect(page.locator("#wwComplianceAddReferenceBtn")).toBeDisabled();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("No event reference set");
    await expect(page.locator("#wwComplianceChartEmptyState")).toHaveText("No voltage assessment configured");
    await expect(page.locator("#wwComplianceResultsEmptyState")).toContainText("Results will appear after a measurement");
    // Never a fabricated compliance verdict in the empty state.
    await expect(page.locator("#wwComplianceResultsPanel")).not.toContainText("Compliant");
    await expect(page.locator("#wwComplianceResultsPanel")).not.toContainText("Boundary Breached");
    await expect(page.locator("#wwComplianceResultsPanel")).not.toContainText("Within Capability");
  });

  test("Comparison Chart is present and visually dominant (largest section)", async ({ page }) => {
    await openCompliance(page);
    const chartWrap = page.locator("#wwComplianceChartWrap");
    await expect(chartWrap).toBeVisible();
    const chartBox = await chartWrap.boundingBox();
    const measurementBox = await page.locator("#wwComplianceMeasurementCard").boundingBox();
    const resultsBox = await page.locator("#wwComplianceResultsPanel").boundingBox();
    expect(chartBox.height).toBeGreaterThan(200);
    expect(chartBox.width).toBeGreaterThan(measurementBox.width);
    expect(chartBox.height).toBeGreaterThan(measurementBox.height);
    expect(chartBox.height).toBeGreaterThan(resultsBox.height);
  });

  test("switching back to Analysis works, no stale Compliance panel remains visible", async ({ page }) => {
    await openCompliance(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#pageCompliance")).toBeHidden();
    await expect(page.locator("#wwComplianceVoltagePanel")).not.toBeInViewport();
  });

  test("switching to other main pages works, no stale Compliance panel remains visible", async ({ page }) => {
    await openCompliance(page);

    await page.locator("#mainNavRecordingsBtn").click();
    await expect(page.locator("#pageRecordings")).toBeVisible();
    await expect(page.locator("#pageCompliance")).toBeHidden();

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    await expect(page.locator("#pageCompliance")).toBeHidden();

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
    await expect(page.locator("#pageCompliance")).toBeHidden();
  });

  test("opening Compliance does not touch Playback, Analysis Input Source, or any analyzer state", async ({ page }) => {
    // Establishes a real Playback/Phasor state first, then confirms
    // opening Compliance leaves it completely untouched -- Compliance's
    // own render hook must never call wwPlaybackReset()/wwAnalysisLoadContexts()/
    // any analyzer's own bootstrap merely because the page opened.
    await page.goto("/index.html");
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    // Phasor's own pre-existing "no recording available" auto-fallback
    // (wwPhasorUpdateInputSourceAvailability()) settles asynchronously
    // from "recording" to "manual" on a fresh empty workspace -- wait
    // for that unrelated, already-established behavior to finish before
    // taking the baseline snapshot, so this test measures only what
    // opening Compliance itself does, not a pre-existing Phasor race.
    await expect(async () => {
      expect(await page.evaluate(() => wwPhasorState.inputSource)).toBe("manual");
    }).toPass({ timeout: 5000 });
    const beforeState = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state,
      playbackSpeed: wwPlaybackState().speed,
      inputSource: wwPhasorState.inputSource,
    }));

    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();

    const afterState = await page.evaluate(() => JSON.stringify({
      playbackState: wwPlaybackState().state,
      playbackSpeed: wwPlaybackState().speed,
      inputSource: wwPhasorState.inputSource,
    }));
    expect(afterState).toBe(beforeState);
  });

  for (const viewport of [{ width: 1366, height: 900 }, { width: 1024, height: 800 }]) {
    test(`no horizontal overflow at ${viewport.width}px`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await openCompliance(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1); // sub-pixel rounding tolerance only
      // The three configuration cards must not have collapsed to zero
      // width or wrapped in a broken way -- each stays reasonably sized
      // at both target widths.
      const measurementBox = await page.locator("#wwComplianceMeasurementCard").boundingBox();
      expect(measurementBox.width).toBeGreaterThan(120);
    });
  }

  // Owner UAT fix (2026-09-20, commit 3447f24): #wwComplianceMeasurementSelect
  // used to overflow the Measurement card and encroach into Reference
  // Layers at narrower widths. This file's own tests intentionally never
  // upload anything (see this file's own header comment), and as of the
  // 2026-09-20 Bay/Measurement Group UAT correction, both
  // #wwComplianceGroupSelect and #wwComplianceMeasurementSelect start
  // `hidden` until a real Measurement Group exists -- there is nothing
  // to measure a bounding box of on a bare empty workspace any more.
  // The real containment verification for BOTH selects (with a genuine
  // group + quantity selected) now lives in
  // browser-tests/compliance_measurement.spec.js's own
  // "no overflow with the Measurement summary visible" scenarios.
});
