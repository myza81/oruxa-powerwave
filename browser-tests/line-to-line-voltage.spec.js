// DEC-115: real-browser UAT coverage for the Line-to-Line Voltage
// calculated-channel operation. Real backend + real frontend (same
// harness as smoke.spec.js, no mocks).
//
// Fixture: backend/tests/fixtures/comtrade/line_to_line_multibay -- DEC-104
// upload-time preparation creates three Engineering Contexts:
//   KPDN1 -- instantaneous VR/VY/VB (unbalanced disturbance) -> All Three
//   KPDN2 -- VR/VY only                                       -> VAB only
//   MCRS  -- RMS-magnitude VR/VY/VB                           -> unsupported
//
// Each test gets a fresh browser context, so a fresh random workspace id.

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
}

async function openLineToLineBuilder(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="line_to_line_voltage"]').click();
  await expect(page.locator("#wwCcBuilderTitle")).toHaveText("Line-to-Line Voltage (L-L)");
  await expect(page.locator("#wwCcLlContextSelect")).toBeVisible();
}

async function selectBay(page, displayName) {
  const value = await page.locator("#wwCcLlContextSelect option").evaluateAll(
    (options, name) => (options.find((o) => o.textContent.startsWith(name + " — ")) || {}).value,
    displayName,
  );
  expect(value, `bay ${displayName} listed`).toBeTruthy();
  await page.locator("#wwCcLlContextSelect").selectOption(value);
}

async function createAndWait(page) {
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// Every trace currently drawn on the Waveform page, with its real Plotly
// line color -- read from the rendered chart, never from app state alone.
async function waveformTraces(page) {
  return page.evaluate(() => ww.panels.flatMap((panel) =>
    ((panel.chartEl && panel.chartEl.data) || []).map((t) => ({ name: t.name, color: t.line && t.line.color }))
  ));
}

async function lineToLineTraceColors(page) {
  const traces = await waveformTraces(page);
  const byPair = {};
  for (const pair of ["VAB", "VBC", "VCA"]) {
    const trace = traces.find((t) => t.name === `KPDN1 ${pair}`);
    byPair[pair] = trace ? trace.color : null;
  }
  return byPair;
}

async function goToWaveform(page) {
  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#workspaceRow")).toBeVisible();
}

test.describe("Line-to-Line Voltage", () => {
  test("bay selector lists every bay with explicit readiness", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);

    const optionTexts = await page.locator("#wwCcLlContextSelect option").allTextContents();
    expect(optionTexts).toHaveLength(3); // no bay hidden
    expect(optionTexts.find((t) => t.startsWith("KPDN1 — "))).toBe("KPDN1 — Ready for All Three");
    expect(optionTexts.find((t) => t.startsWith("KPDN2 — "))).toContain("Vc missing");
    expect(optionTexts.find((t) => t.startsWith("MCRS — "))).toContain("RMS magnitudes alone are insufficient");

    // Default selection is the bay ready for All Three.
    await expect(page.locator("#wwCcLlStatus")).toHaveAttribute("data-ll-status", "ready");
    await expect(page.locator("#wwCcLlOutput_all_three")).toBeChecked();
    await expect(page.locator("#wwCcLlPlannedNames")).toContainText("KPDN1 VAB, KPDN1 VBC, KPDN1 VCA");
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("VAB = KPDN1_VR − KPDN1_VY");
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("VCA = KPDN1_VB − KPDN1_VR");
    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("kV");

    // Unsupported representation: nothing can be chosen or created.
    await selectBay(page, "MCRS");
    await expect(page.locator("#wwCcLlStatus")).toHaveAttribute("data-ll-status", "unsupported_representation");
    for (const output of ["AB", "BC", "CA", "all_three"]) {
      await expect(page.locator(`#wwCcLlOutput_${output}`)).toBeDisabled();
    }
    await expect(page.locator("#wwCcLlOutputReason")).toContainText("RMS magnitudes alone are insufficient");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
  });

  test("All Three on KPDN1 -> Create -> Plot All: three distinct, stable colors", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_all_three").check();
    await createAndWait(page);

    // One logical result set in the immediate workflow.
    const result = page.locator("#wwCcLlResult");
    await expect(result).toBeVisible();
    await expect(result.locator(".ww-cc-ll-result-list li")).toHaveText(["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA"]);
    // ...yet three ordinary, individually listed calculated channels.
    await expect(page.locator(".ww-cc-list-row")).toHaveCount(3);
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText(["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA"]);
    await expect(page.locator(".ww-cc-list-row-expr").first()).toHaveText("VAB = KPDN1_VR − KPDN1_VY");

    await page.locator("#wwCcLlPlotAllBtn").click();
    await expect(page.locator("#wwCcLlPlotAllBtn")).toBeDisabled(); // all shown

    await goToWaveform(page);
    await expect.poll(async () => (await waveformTraces(page)).filter((t) => /KPDN1 V(AB|BC|CA)$/.test(t.name)).length).toBe(3);
    const colors = await lineToLineTraceColors(page);
    expect(Object.values(colors).every(Boolean)).toBe(true);
    expect(new Set(Object.values(colors)).size).toBe(3); // distinct

    // Labels clearly identify AB/BC/CA (trace names, and sidebar dots
    // carry the same colors).
    const sidebarDots = await page.evaluate(() => {
      const out = {};
      document.querySelectorAll("#calculatedChannelsSidebarBody tr[data-calculated-channel-id]").forEach((row) => {
        const dot = row.querySelector(".channel-color-dot");
        out[row.getAttribute("data-channel-name")] = dot ? getComputedStyle(dot).backgroundColor : null;
      });
      return out;
    });
    expect(Object.keys(sidebarDots).sort()).toEqual(["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA"]);
    expect(new Set(Object.values(sidebarDots)).size).toBe(3);

    // Hide/show VBC: identity preserved.
    const vbcRow = page.locator('#calculatedChannelsSidebarBody tr[data-channel-name="KPDN1 VBC"]');
    await vbcRow.click();
    await expect.poll(async () => (await lineToLineTraceColors(page)).VBC).toBeNull();
    await vbcRow.click();
    await expect.poll(async () => (await lineToLineTraceColors(page)).VBC).toBe(colors.VBC);
    expect(await lineToLineTraceColors(page)).toEqual(colors);

    // Zoom: identity preserved.
    await page.locator(".ww-tg-zoom-in-btn").first().click();
    expect(await lineToLineTraceColors(page)).toEqual(colors);

    // Redraw via layout switch (Separate re-creates every panel/legend) and back.
    await page.locator("#layoutModeSeparateBtn").click();
    await expect.poll(async () => lineToLineTraceColors(page)).toEqual(colors);
    const legendColors = await page.evaluate(() => ww.panels.flatMap((p) => p.channels.map((c) => [c.channelName, c.color])));
    expect(Object.fromEntries(legendColors.filter(([n]) => /^KPDN1 V/.test(n)))).toEqual({
      "KPDN1 VAB": colors.VAB, "KPDN1 VBC": colors.VBC, "KPDN1 VCA": colors.VCA,
    });
    await page.locator("#layoutModeGroupedBtn").click();
    await expect.poll(async () => lineToLineTraceColors(page)).toEqual(colors);

    // Page revisit: identity preserved.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await goToWaveform(page);
    expect(await lineToLineTraceColors(page)).toEqual(colors);

    // Full reload (same workspace): Plot All from the manager's row menu
    // re-derives the SAME colors deterministically.
    await page.reload();
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator(".ww-cc-list-row")).toHaveCount(3);
    const row = page.locator(".ww-cc-list-row").nth(1);
    await row.locator(".ww-cc-menu summary").click();
    await row.locator('button[data-action="plot-batch"]').click();
    await goToWaveform(page);
    await expect.poll(async () => lineToLineTraceColors(page)).toEqual(colors);
  });

  test("single pair on an incomplete bay: VAB available, others unavailable with reason", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN2");

    await expect(page.locator("#wwCcLlStatus")).toHaveAttribute("data-ll-status", "incomplete");
    await expect(page.locator('#wwCcLlStatus li[data-ll-role="Vc"]')).toHaveAttribute("data-ll-role-status", "missing");
    await expect(page.locator("#wwCcLlOutput_AB")).toBeEnabled();
    await expect(page.locator("#wwCcLlOutput_AB")).toBeChecked(); // All Three unavailable -> first available pair
    for (const output of ["BC", "CA", "all_three"]) {
      await expect(page.locator(`#wwCcLlOutput_${output}`)).toBeDisabled();
    }
    await expect(page.locator("#wwCcNameInput")).toHaveValue("KPDN2 VAB");
    await createAndWait(page);

    await expect(page.locator(".ww-cc-list-row")).toHaveCount(1);
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText("KPDN2 VAB");
    await expect(page.locator("#wwCcLlResult .ww-cc-ll-result-list li")).toHaveText(["KPDN2 VAB"]);
    await expect(page.locator("#wwCcLlPlotAllBtn")).toHaveText("Plot");
    // A lone pair has no set, so no "Plot All" row action.
    await page.locator(".ww-cc-list-row .ww-cc-menu summary").click();
    await expect(page.locator('.ww-cc-list-row button[data-action="plot-batch"]')).toHaveCount(0);
  });

  test("single pair on a complete bay with a custom name", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_CA").check();
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("VCA = KPDN1_VB − KPDN1_VR");
    await page.locator("#wwCcNameInput").fill("Feeder VCA");
    await createAndWait(page);
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText("Feeder VCA");
    await expect(page.locator(".ww-cc-list-row-expr")).toHaveText("VCA = KPDN1_VB − KPDN1_VR");
  });

  test("deleting one member keeps the rest of the set", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await createAndWait(page); // defaults: KPDN1, All Three
    await expect(page.locator(".ww-cc-list-row")).toHaveCount(3);
    const vab = page.locator(".ww-cc-list-row").first();
    await vab.locator(".ww-cc-menu summary").click();
    await vab.locator('button[data-action="delete"]').click();
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText(["KPDN1 VBC", "KPDN1 VCA"]);
    await expect(page.locator("#wwCcLlResult .ww-cc-ll-result-list li")).toHaveText(["KPDN1 VBC", "KPDN1 VCA"]);
  });
});
