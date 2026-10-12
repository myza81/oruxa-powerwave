// DEC-190: ROCOF (Rate of Change of Frequency) calculated channel.
//
// Real backend + real frontend, no mocks. Fixture: a 100 Hz, 0.5 s ASCII
// COMTRADE with FREQ (Hz) falling linearly 50 -> 49.5 Hz (analytical
// ROCOF = -1 Hz/s) and VA (V), so the frequency-first input grouping and
// the explicit "Calculate anyway" fallback are both exercised. What is
// plotted is asserted from the live Plotly trace arrays, not only text.

const { test, expect } = require("@playwright/test");
const { routeConfig } = require("./support/relay_import_helpers");

const SAMPLES = 51;

function frequencyFixture() {
  const cfg = [
    "SYNTH_STATION,SYNTH_DEV,1999",
    "2,2A,0D",
    "1,FREQ,,,Hz,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VA,,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
    "50",
    "1",
    `100.0,${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const f = 50 - (0.5 * i) / (SAMPLES - 1);
    rows.push(`${i + 1},${i * 10000},${f.toFixed(6)},${(100 * Math.sin((2 * Math.PI * i) / 20)).toFixed(6)}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

async function uploadFixture(page) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = frequencyFixture();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "freq.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "freq.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openRocofBuilder(page) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="rocof"]').click();
  await expect(page.locator("#wwCcBuilderTitle")).toHaveText("ROCOF");
}

async function pickInput(page, label) {
  const select = page.locator("#wwCcUnaryInputSelect");
  const value = await select.locator("option").evaluateAll(
    (options, wanted) => (options.find((o) => o.textContent.includes(wanted)) || {}).value, label);
  expect(value, `input option ${label}`).toBeTruthy();
  await select.selectOption(value);
}

async function previewTraces(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll("#wwCcPreviewPanels .ww-cc-preview-chart")).flatMap((chart) =>
    (chart.data || []).map((t) => ({ name: (t.name || "").replace(/<[^>]+>/g, ""), y: Array.from(t.y || []), x: Array.from(t.x || []) }))));
}

test.describe("ROCOF calculated channel", () => {
  test("builder: frequency-first input, labels, fixed Hz/s unit, raw default", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);

    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("Hz/s");
    await expect(page.locator("#wwCcBuilderFields")).toContainText("Input: Frequency (Hz)");

    const groups = await page.locator("#wwCcUnaryInputSelect optgroup").evaluateAll((els) =>
      els.map((g) => ({ label: g.label, options: Array.from(g.querySelectorAll("option")).map((o) => o.textContent) })));
    expect(groups.map((g) => g.label)).toEqual(["Frequency channels (Hz)", "Other channels (not identified as frequency)"]);
    expect(groups[0].options.join("|")).toContain("FREQ");
    expect(groups[0].options.join("|")).not.toContain("VA");
    expect(groups[1].options.join("|")).toContain("VA");

    await pickInput(page, "FREQ");
    await expect(page.locator("#wwCcRocofStatus")).toContainText("identified as a frequency channel");
    await expect(page.locator("#wwCcRocofOverrideRow")).toBeHidden();
    await expect(page.locator("#wwCcNameInput")).toHaveValue("ROCOF (FREQ)");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = ROCOF (FREQ, raw)");
    await expect(page.locator("#wwCcRocofSmoothingSelect")).toHaveValue("none");
    await expect(page.locator("#wwCcRocofWindowInput")).toHaveCount(0);
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("smoothing: window appears, is labelled in name/preview, validated, and Treat Null as Zero is unavailable", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);
    await pickInput(page, "FREQ");

    await page.locator("#wwCcRocofSmoothingSelect").selectOption("centered_moving_average");
    await expect(page.locator("#wwCcRocofWindowInput")).toHaveValue("100");
    await expect(page.locator("#wwCcNameInput")).toHaveValue("ROCOF (FREQ, 100 ms avg)");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = ROCOF (FREQ, 100 ms centered moving average)");

    await page.locator("#wwCcRocofWindowInput").fill("0");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
    await page.locator("#wwCcRocofWindowInput").fill("200");
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("200 ms centered moving average");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await expect(page.locator('#wwCcNullPolicySelect option[value="treat_null_as_zero"]')).toHaveJSProperty("disabled", true);

    // Backend range validation surfaces as an inline error (window longer than the 0.5 s record).
    await page.locator("#wwCcRocofWindowInput").fill("5000");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcError")).toContainText("longer than the recording");
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  });

  test("raw ROCOF of a 50 -> 49.5 Hz ramp plots -1 Hz/s; lifecycle and timebase", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);
    await pickInput(page, "FREQ");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    const row = page.locator(".ww-cc-list-row").filter({ has: page.locator(".ww-cc-list-row-name", { hasText: /^ROCOF \(FREQ\)$/ }) });
    await expect(row).toBeVisible();
    await expect(row.locator(".ww-cc-list-row-unit")).toHaveText("Hz/s");
    await expect(row.locator(".ww-cc-type-badge")).toHaveText("ROCOF");

    const eye = row.locator('button[data-action="toggle-visibility"]');
    if ((await eye.getAttribute("aria-pressed")) !== "true") await eye.click();
    await expect.poll(async () => (await previewTraces(page)).length).toBe(1);
    const [trace] = await previewTraces(page);
    expect(trace.name).toBe("ROCOF (FREQ) (Hz/s)");
    expect(trace.y).toHaveLength(SAMPLES);
    for (const v of trace.y) expect(v).toBeCloseTo(-1, 5);
    expect(trace.x[0]).toBeCloseTo(0, 9);
    expect(trace.x[SAMPLES - 1]).toBeCloseTo(0.5, 9);

    await expect(page.locator("#wwCcPreviewInfoStrip")).toContainText("ROCOF (FREQ, raw)");

    // Timebase: grounded on the source recording, so it follows that source's sync / t=0 placement.
    const grounding = await page.evaluate(async () => {
      const ws = currentWorkspaceId();
      const list = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + ws + "/calculated-channels")).json();
      const src = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + ws + "/sources")).json();
      const sourceIds = (Array.isArray(src) ? src : src.sources || []).map((s) => s.source_id);
      return { reference: list[0].reference_source_id, sourceIds, parameters: list[0].parameters };
    });
    expect(grounding.sourceIds).toContain(grounding.reference);
    expect(grounding.parameters).toMatchObject({ smoothing: "none", smoothing_window_ms: null });

    // Delete -> gone from the manager and the preview.
    await row.locator(".ww-cc-menu summary").click();
    await row.locator('button[data-action="delete"]').click();
    await expect(row).toHaveCount(0);
    await expect.poll(async () => (await previewTraces(page)).length).toBe(0);
  });

  test("smoothed channel is labelled as smoothed and keeps the same ramp", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);
    await pickInput(page, "FREQ");
    await page.locator("#wwCcRocofSmoothingSelect").selectOption("centered_moving_average");
    await page.locator("#wwCcRocofWindowInput").fill("100");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    const row = page.locator(".ww-cc-list-row").filter({ has: page.locator(".ww-cc-list-row-name", { hasText: "ROCOF (FREQ, 100 ms avg)" }) });
    await expect(row).toBeVisible();
    await row.locator(".ww-cc-list-row-name").click();
    await expect(page.locator("#wwCcPreviewInfoStrip")).toContainText("ROCOF (FREQ, 100 ms centered moving average)");
  });

  test("non-frequency input needs the explicit Calculate anyway acknowledgement", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);
    await pickInput(page, "VA");

    await expect(page.locator("#wwCcRocofStatus")).toContainText("classified as Voltage, not Frequency");
    await expect(page.locator("#wwCcRocofOverrideRow")).toBeVisible();
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    await page.locator("#wwCcRocofOverrideCheckbox").check();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    // Switching the input clears the acknowledgement.
    await pickInput(page, "FREQ");
    await expect(page.locator("#wwCcRocofOverrideRow")).toBeHidden();
    await pickInput(page, "VA");
    await expect(page.locator("#wwCcRocofOverrideCheckbox")).not.toBeChecked();
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
  });
});
