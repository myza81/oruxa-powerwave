// DEC-190: ROCOF (Rate of Change of Frequency) calculated channel -- a
// CENTERED measurement window T (100/200/500/1000/2000 ms), rolling
// frequency difference (default) or rolling linear regression.
//
// Real backend + real frontend, no mocks. Fixture: a 100 Hz, 1.5 s ASCII
// COMTRADE with FREQ (Hz) falling linearly 50 -> 48.5 Hz (analytical
// ROCOF = -1 Hz/s) and VA (V), so the frequency-first input grouping and
// the explicit "Calculate anyway" fallback are both exercised. What is
// plotted is asserted from the live Plotly trace arrays, not only text.

const { test, expect } = require("@playwright/test");
const { routeConfig } = require("./support/relay_import_helpers");

const SAMPLES = 151;

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
    const f = 50 - i / 100;
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

async function createRocof(page, { windowMs, method } = {}) {
  await openRocofBuilder(page);
  await pickInput(page, "FREQ");
  if (method) await page.locator("#wwCcRocofMethodSelect").selectOption(method);
  if (windowMs) await page.locator("#wwCcRocofWindowSelect").selectOption(String(windowMs));
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

function row(page, name) {
  return page.locator(".ww-cc-list-row").filter({ has: page.locator(".ww-cc-list-row-name", { hasText: new RegExp(`^${name.replace(/[()]/g, "\\$&")}$`) }) });
}

async function showTrace(page, name) {
  const eye = row(page, name).locator('button[data-action="toggle-visibility"]');
  await expect(eye).toBeVisible();
  if ((await eye.getAttribute("aria-pressed")) !== "true") await eye.click();
}

async function previewTraces(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll("#wwCcPreviewPanels .ww-cc-preview-chart")).flatMap((chart) =>
    (chart.data || []).map((t) => ({ name: (t.name || "").replace(/<[^>]+>/g, ""), y: Array.from(t.y || []), x: Array.from(t.x || []) }))));
}

test.describe("ROCOF calculated channel", () => {
  test("builder: frequency-first input, approved defaults, measurement window is not smoothing", async ({ page }) => {
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

    // Approved defaults: Rolling Frequency Difference, 500 ms, centered.
    await expect(page.locator("#wwCcRocofMethodSelect")).toHaveValue("rolling_frequency_difference");
    await expect(page.locator("#wwCcRocofMethodSelect option")).toHaveText(["Rolling Frequency Difference", "Rolling Linear Regression"]);
    await expect(page.locator("#wwCcRocofWindowSelect")).toHaveValue("500");
    await expect(page.locator("#wwCcRocofWindowSelect option")).toHaveText(["100 ms", "200 ms", "500 ms", "1000 ms", "2000 ms"]);
    await expect(page.locator("#wwCcBuilderFields")).toContainText("Time Alignment");
    await expect(page.locator('#wwCcBuilderFields input[readonly][value="Centered"]')).toHaveCount(1);
    // No separate smoothing stage.
    await expect(page.locator("#wwCcBuilderFields")).not.toContainText(/smooth/i);
    await expect(page.locator("#wwCcRocofSmoothingSelect")).toHaveCount(0);

    await pickInput(page, "FREQ");
    await expect(page.locator("#wwCcRocofStatus")).toContainText("identified as a frequency channel");
    await expect(page.locator("#wwCcRocofOverrideRow")).toBeHidden();
    await expect(page.locator("#wwCcNameInput")).toHaveValue("ROCOF (FREQ, 500 ms)");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = ROCOF (FREQ, rolling frequency difference, 500 ms, centered)");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  test("method and window drive the name and preview; Treat Null as Zero is unavailable; a too-long window is reported", async ({ page }) => {
    await uploadFixture(page);
    await openRocofBuilder(page);
    await pickInput(page, "FREQ");

    await page.locator("#wwCcRocofMethodSelect").selectOption("rolling_linear_regression");
    await page.locator("#wwCcRocofWindowSelect").selectOption("200");
    await expect(page.locator("#wwCcNameInput")).toHaveValue("ROCOF (FREQ, regression 200 ms)");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = ROCOF (FREQ, rolling linear regression, 200 ms, centered)");

    await expect(page.locator('#wwCcNullPolicySelect option[value="treat_null_as_zero"]')).toHaveJSProperty("disabled", true);

    // The 1.5 s record cannot hold a complete 2000 ms centered window: the backend says so, nothing is created.
    await page.locator("#wwCcRocofWindowSelect").selectOption("2000");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcError")).toContainText("2000 ms");
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  });

  test("default ROCOF of a -1 Hz/s ramp plots -1 with the incomplete edge windows blank; lifecycle and timebase", async ({ page }) => {
    await uploadFixture(page);
    await createRocof(page);

    const name = "ROCOF (FREQ, 500 ms)";
    await expect(row(page, name)).toBeVisible();
    await expect(row(page, name).locator(".ww-cc-list-row-unit")).toHaveText("Hz/s");
    await expect(row(page, name).locator(".ww-cc-type-badge")).toHaveText("ROCOF");

    await showTrace(page, name);
    await expect.poll(async () => (await previewTraces(page)).length).toBe(1);
    const [trace] = await previewTraces(page);
    expect(trace.name).toBe("ROCOF (FREQ, 500 ms) (Hz/s)");
    expect(trace.y).toHaveLength(SAMPLES);
    // 250 ms (25 samples) at each end: no complete window -> blank (never shortened)
    expect(trace.y.slice(0, 25).every((v) => v === null)).toBe(true);
    expect(trace.y.slice(-25).every((v) => v === null)).toBe(true);
    for (const v of trace.y.slice(25, SAMPLES - 25)) expect(v).toBeCloseTo(-1, 5);
    expect(trace.x[0]).toBeCloseTo(0, 9);
    expect(trace.x[SAMPLES - 1]).toBeCloseTo(1.5, 9);

    await expect(page.locator("#wwCcPreviewInfoStrip")).toContainText("ROCOF (FREQ, rolling frequency difference, 500 ms, centered)");

    // UAT refinement: the preview names both axes, the full expression is never cut off, and the
    // measurement window the channel was calculated with is stated.
    const chart = page.locator("#wwCcPreviewPanels .ww-cc-preview-chart");
    await expect(chart.locator(".g-xtitle")).toHaveText("Time (s)");
    await expect(chart.locator(".g-ytitle")).toHaveText("ROCOF (Hz/s)");
    const expression = page.locator("#wwCcPreviewInfoStrip .ww-cc-preview-info-value--wrap").first();
    await expect(expression).toHaveAttribute("title", "ROCOF (FREQ, rolling frequency difference, 500 ms, centered)");
    expect(await expression.evaluate((el) => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1)).toBe(true);
    for (const [label, value] of [["ROCOF Method", "Rolling Frequency Difference"], ["Measurement Window", "500 ms"], ["Time Alignment", "Centered"]]) {
      await expect(page.locator("#wwCcPreviewInfoStrip div").filter({ hasText: label })).toContainText(value);
    }
    await expect(page.locator("#wwCcPreviewInfoStrip")).toContainText("blank within 250 ms of the ends and of any gap");

    // Timebase: grounded on the source recording, so it follows that source's sync / t=0 placement.
    const grounding = await page.evaluate(async () => {
      const ws = currentWorkspaceId();
      const list = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + ws + "/calculated-channels")).json();
      const src = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + ws + "/sources")).json();
      const sourceIds = (Array.isArray(src) ? src : src.sources || []).map((s) => s.source_id);
      return { reference: list[0].reference_source_id, sourceIds, parameters: list[0].parameters };
    });
    expect(grounding.sourceIds).toContain(grounding.reference);
    expect(grounding.parameters).toMatchObject({
      method: "rolling_frequency_difference", window_ms: 500, alignment: "centered",
    });

    // Delete -> gone from the manager and the preview.
    await row(page, name).locator(".ww-cc-menu summary").click();
    await row(page, name).locator('button[data-action="delete"]').click();
    await expect(row(page, name)).toHaveCount(0);
    await expect.poll(async () => (await previewTraces(page)).length).toBe(0);
  });

  test("the measurement window genuinely changes the result: 100 ms vs 500 ms availability, regression on the same ramp", async ({ page }) => {
    await uploadFixture(page);
    await createRocof(page, { windowMs: 100 });
    await createRocof(page, { windowMs: 500 });
    await createRocof(page, { windowMs: 200, method: "rolling_linear_regression" });

    const names = ["ROCOF (FREQ, 100 ms)", "ROCOF (FREQ, 500 ms)", "ROCOF (FREQ, regression 200 ms)"];
    for (const n of names) await showTrace(page, n);
    await expect.poll(async () => (await previewTraces(page)).length).toBe(3);
    const traces = Object.fromEntries((await previewTraces(page)).map((t) => [t.name.replace(" (Hz/s)", ""), t.y]));
    const finite = (y) => y.filter((v) => v !== null);
    expect(finite(traces[names[0]])).toHaveLength(141); // t in [0.05, 1.45]
    expect(finite(traces[names[1]])).toHaveLength(101); // t in [0.25, 1.25]
    expect(finite(traces[names[2]])).toHaveLength(131); // t in [0.10, 1.40]
    for (const n of names) for (const v of finite(traces[n])) expect(v).toBeCloseTo(-1, 5);
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
