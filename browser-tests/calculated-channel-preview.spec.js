// Owner UAT correction (2026-09-25, recorded on DEC-047): the Calculated
// Channels Preview renders EVERY calculated channel whose eye/visibility
// state is ON; row SELECTION only drives focus, the status line and the
// info strip. Selected != Visible.
//
// Real backend + real frontend, no mocks. Every assertion about what is
// plotted reads the live Plotly trace arrays of the Preview charts
// (#wwCcPreviewPanels .ww-cc-preview-chart .data), never only text.
//
// Fixture: line_to_line_multibay (see line-to-line-voltage.spec.js).

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "line_to_line_multibay";

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openBuilder(page) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
}

async function createAndWait(page) {
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// KPDN1 line-to-line: "AB" (single VAB) or "all_three".
async function createKpdn1LineToLine(page, output) {
  await openBuilder(page);
  await page.locator('.ww-cc-operation-card[data-operation="line_to_line_voltage"]').click();
  await expect(page.locator("#wwCcLlContextSelect")).toBeVisible();
  await expect(page.locator("#wwCcLlStatus")).toHaveAttribute("data-ll-status", "ready"); // KPDN1 default
  await page.locator(`#wwCcLlOutput_${output}`).check();
  await createAndWait(page);
}

// Unary operation on an existing channel, picked by its visible option label.
async function createUnary(page, operation, inputLabel) {
  await openBuilder(page);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
  const select = page.locator("#wwCcUnaryInputSelect");
  const value = await select.locator("option").evaluateAll(
    (options, label) => (options.find((o) => o.textContent.trim() === label || o.textContent.trim().startsWith(label + " (")) || {}).value,
    inputLabel,
  );
  expect(value, `input option ${inputLabel}`).toBeTruthy();
  await select.selectOption(value);
  await createAndWait(page);
}

function row(page, name) {
  return page.locator(".ww-cc-list-row").filter({ has: page.locator(".ww-cc-list-row-name", { hasText: new RegExp(`^${name.replace(/[()]/g, "\\$&")}$`) }) });
}

async function setVisible(page, name, visible) {
  const eye = row(page, name).locator('button[data-action="toggle-visibility"]');
  if ((await eye.getAttribute("aria-pressed")) !== String(visible)) await eye.click();
  await expect(eye).toHaveAttribute("aria-pressed", String(visible));
}

async function selectRow(page, name) {
  await row(page, name).locator(".ww-cc-list-row-name").click();
  await expect(row(page, name)).toHaveClass(/ww-cc-list-row--selected/);
}

// Live Preview state, read from the rendered Plotly charts.
async function previewTraces(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll("#wwCcPreviewPanels .ww-cc-preview-chart")).flatMap((chart) =>
    (chart.data || []).map((t) => ({
      uid: t.uid, name: (t.name || "").replace(/<[^>]+>/g, ""), rawName: t.name, color: t.line && t.line.color,
      panel: chart.closest(".ww-cc-preview-panel").querySelector(".ww-cc-preview-panel-title").textContent,
    }))
  ));
}

async function expectPreviewNames(page, names) {
  await expect.poll(async () => (await previewTraces(page)).map((t) => t.name).sort()).toEqual([...names].sort());
}

test.describe("Calculated Channels Preview -- Visible drives traces, Selected drives details", () => {
  test("owner UAT: VAB + RMS(VAB) both visible, RMS selected -> both plotted, distinct colors", async ({ page }) => {
    await uploadFixture(page);
    await createKpdn1LineToLine(page, "AB");
    await createUnary(page, "rms", "KPDN1 VAB");
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText(["KPDN1 VAB", "RMS(KPDN1 VAB)"]);

    await setVisible(page, "KPDN1 VAB", true);
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await selectRow(page, "RMS(KPDN1 VAB)");

    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    const traces = await previewTraces(page);
    // Instantaneous and RMS of the same kV quantity share ONE Voltage panel.
    expect(new Set(traces.map((t) => t.panel))).toEqual(new Set(["Calculated - Voltage"]));
    expect(new Set(traces.map((t) => t.uid)).size).toBe(2);
    expect(traces.every((t) => t.color)).toBe(true);
    expect(traces[0].color).not.toBe(traces[1].color);

    // Status names the selection without implying it is the only trace;
    // the info strip describes the selected channel.
    await expect(page.locator("#wwCcPreviewStatus")).toHaveText("Selected: RMS(KPDN1 VAB)2 visible");
    await expect(page.locator("#wwCcPreviewInfoStrip")).toContainText("RMS(KPDN1 VAB, 50 Hz, 1 cycle)");
  });

  test("0 / 1 / 2 visible, selection changes never change the trace set, hide all -> empty state", async ({ page }) => {
    await uploadFixture(page);
    await createKpdn1LineToLine(page, "AB");
    await createUnary(page, "rms", "KPDN1 VAB");

    // New channels are hidden by default (DEC-038): nothing plotted.
    await expectPreviewNames(page, []);
    await expect(page.locator("#wwCcPreviewEmpty")).toBeVisible();
    await expect(page.locator("#wwCcPreviewEmpty")).toHaveText(/No calculated channels are visible/);
    await expect(page.locator("#wwCcPreviewPanels")).toBeHidden();

    await setVisible(page, "KPDN1 VAB", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)"]);
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);

    await selectRow(page, "KPDN1 VAB");
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    await expect(page.locator("#wwCcPreviewStatus")).toHaveText("Selected: KPDN1 VAB2 visible");
    await selectRow(page, "RMS(KPDN1 VAB)");
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);

    await setVisible(page, "KPDN1 VAB", false);
    await expectPreviewNames(page, ["RMS(KPDN1 VAB) (kV)"]);
    await setVisible(page, "KPDN1 VAB", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);

    // A hidden SELECTED row stays selected and described, but is not plotted.
    await setVisible(page, "RMS(KPDN1 VAB)", false);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)"]);
    await expect(page.locator("#wwCcPreviewStatus")).toHaveText("Selected: RMS(KPDN1 VAB) (hidden)1 visible");

    await setVisible(page, "KPDN1 VAB", false);
    await expectPreviewNames(page, []);
    await expect(page.locator("#wwCcPreviewPanels")).toBeHidden();
    await expect(page.locator("#wwCcPreviewEmpty")).toBeVisible();
    await expect(page.locator("#wwCcPreviewStatus")).toHaveText("Selected: RMS(KPDN1 VAB) (hidden)0 visible");
  });

  test("Plot All -> exactly VAB/VBC/VCA in Preview; + RMS(VAB) -> four distinct colors", async ({ page }) => {
    await uploadFixture(page);
    await createKpdn1LineToLine(page, "all_three");
    await page.locator("#wwCcLlPlotAllBtn").click();
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "KPDN1 VBC (kV)", "KPDN1 VCA (kV)"]);
    const three = await previewTraces(page);
    expect(new Set(three.map((t) => t.color)).size).toBe(3);

    await createUnary(page, "rms", "KPDN1 VAB");
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "KPDN1 VBC (kV)", "KPDN1 VCA (kV)", "RMS(KPDN1 VAB) (kV)"]);
    const four = await previewTraces(page);
    expect(new Set(four.map((t) => t.color)).size).toBe(4);
    // DEC-115 pair colors unchanged by adding the RMS trace.
    for (const t of three) expect(four.find((f) => f.uid === t.uid).color).toBe(t.color);
    // Same colors as the main Waveform page uses (one color authority).
    await page.locator("#mainNavWaveformBtn").click();
    const waveformColors = await page.evaluate(() => Object.fromEntries(ww.panels.flatMap((p) =>
      ((p.chartEl && p.chartEl.data) || []).map((t) => [(t.name || "").replace(/<[^>]+>/g, ""), t.line && t.line.color]))));
    expect(waveformColors["KPDN1 VAB"]).toBe(four.find((t) => t.name === "KPDN1 VAB (kV)").color);
    expect(waveformColors["RMS(KPDN1 VAB)"]).toBe(four.find((t) => t.name === "RMS(KPDN1 VAB) (kV)").color);
  });

  test("different engineering types render in separate panels", async ({ page }) => {
    await uploadFixture(page);
    await createKpdn1LineToLine(page, "AB");
    await createUnary(page, "reverse_polarity", "LLMULTIBAY — KPDN1_IR");
    await setVisible(page, "KPDN1 VAB", true);
    await setVisible(page, "-KPDN1_IR", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "-KPDN1_IR (kA)"]);
    const panels = (await previewTraces(page)).reduce((m, t) => ({ ...m, [t.name]: t.panel }), {});
    expect(panels).toEqual({ "KPDN1 VAB (kV)": "Calculated - Voltage", "-KPDN1_IR (kA)": "Calculated - Current" });
  });

  test("colors and zoom stay stable through selection, hide/show, revisit and reload", async ({ page }) => {
    await uploadFixture(page);
    await createKpdn1LineToLine(page, "AB");
    await createUnary(page, "rms", "KPDN1 VAB");
    await setVisible(page, "KPDN1 VAB", true);
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    const colorsOf = async () => Object.fromEntries((await previewTraces(page)).map((t) => [t.name, t.color]));
    const colors = await colorsOf();

    // Zoom the Preview, then change selection and visibility: the zoom
    // survives (constant uirevision) and colors never move.
    await page.evaluate(() => Plotly.relayout(document.querySelector("#wwCcPreviewPanels .ww-cc-preview-chart"), { "xaxis.range": [0.4, 0.6] }));
    const xRange = () => page.evaluate(() => document.querySelector("#wwCcPreviewPanels .ww-cc-preview-chart").layout.xaxis.range.map((v) => Math.round(v * 1000) / 1000));
    await selectRow(page, "KPDN1 VAB");
    await setVisible(page, "RMS(KPDN1 VAB)", false);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)"]);
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    expect(await xRange()).toEqual([0.4, 0.6]);
    expect(await colorsOf()).toEqual(colors);

    // Autoscale (Plotly's own autorange) and page revisit.
    await page.evaluate(() => Plotly.relayout(document.querySelector("#wwCcPreviewPanels .ww-cc-preview-chart"), { "xaxis.autorange": true, "yaxis.autorange": true }));
    await page.locator("#mainNavWaveformBtn").click();
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    expect(await colorsOf()).toEqual(colors);

    // Full reload: same workspace, channels re-fetched; visibility is
    // session state, so re-show both -- colors are re-derived identically.
    await page.reload();
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator(".ww-cc-list-row")).toHaveCount(2);
    await setVisible(page, "RMS(KPDN1 VAB)", true);
    await setVisible(page, "KPDN1 VAB", true);
    await expectPreviewNames(page, ["KPDN1 VAB (kV)", "RMS(KPDN1 VAB) (kV)"]);
    expect(await colorsOf()).toEqual(colors);
  });
});
