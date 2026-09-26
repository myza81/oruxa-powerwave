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
    ((panel.chartEl && panel.chartEl.data) || []).map((t) => ({ name: (t.name || "").replace(/<[^>]+>/g, ""), rawName: t.name, color: t.line && t.line.color }))
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
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("VAB = VA − VB (KPDN1_VR − KPDN1_VY)");
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("VCA = VC − VA (KPDN1_VB − KPDN1_VR)");
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
    // Display-only electrical notation: V<sub>AB</sub> etc. (names unchanged).
    await expect(result.locator(".ww-cc-ll-result-list li sub")).toHaveText(["AB", "BC", "CA"]);
    // ...yet three ordinary, individually listed calculated channels.
    await expect(page.locator(".ww-cc-list-row")).toHaveCount(3);
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText(["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA"]);
    await expect(page.locator(".ww-cc-list-row-expr").first()).toHaveText("VAB = VA − VB (KPDN1_VR − KPDN1_VY)");

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
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("VCA = VC − VA (KPDN1_VB − KPDN1_VR)");
    await page.locator("#wwCcNameInput").fill("Feeder VCA");
    await createAndWait(page);
    await expect(page.locator(".ww-cc-list-row-name")).toHaveText("Feeder VCA");
    await expect(page.locator(".ww-cc-list-row-expr")).toHaveText("VCA = VC − VA (KPDN1_VB − KPDN1_VR)");
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

// All Three output names: one editable, pre-filled name per output.
test.describe("Line-to-Line Voltage -- All Three output names", () => {
  const nameInputs = (page) => ["AB", "BC", "CA"].map((p) => page.locator(`#wwCcLlName_${p}`));

  async function apiChannelNames(page) {
    return page.evaluate(async () => {
      const r = await fetch(apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/calculated-channels");
      return (await r.json()).map((c) => c.name).sort();
    });
  }

  test("single pair shows one name; All Three shows three pre-filled names", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");

    await page.locator("#wwCcLlOutput_AB").check();
    await expect(page.locator("#wwCcNameInput")).toBeVisible();
    await expect(page.locator("#wwCcNameInput")).toHaveValue("KPDN1 VAB");
    await expect(page.locator("#wwCcLlNamesFields")).toBeHidden();

    await page.locator("#wwCcLlOutput_all_three").check();
    await expect(page.locator("#wwCcNameInput")).toBeHidden();
    await expect(page.locator("#wwCcLlNamesFields")).toBeVisible();
    const [ab, bc, ca] = nameInputs(page);
    await expect(ab).toHaveValue("KPDN1 VAB");
    await expect(bc).toHaveValue("KPDN1 VBC");
    await expect(ca).toHaveValue("KPDN1 VCA");
    await expect(page.locator("#wwCcLlNamesFields .ww-cc-ll-name-pair sub")).toHaveText(["AB", "BC", "CA"]);
    await expect(page.locator("#wwCcUnitDisplay")).toHaveValue("kV"); // one shared unit field

    // Back to a single pair shows that pair's own default.
    await page.locator("#wwCcLlOutput_BC").check();
    await expect(page.locator("#wwCcNameInput")).toHaveValue("KPDN1 VBC");
    await expect(page.locator("#wwCcLlNamesFields")).toBeHidden();
  });

  test("edited names are exactly the names created", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_all_three").check();
    const [ab, bc, ca] = nameInputs(page);
    await ab.fill("KPDN1 BUS VAB");
    await bc.fill("KPDN1 BUS VBC");
    await ca.fill("KPDN1 BUS VCA");
    await expect(page.locator("#wwCcLlPlannedNames")).toHaveText(
      "Creates KPDN1 BUS VAB, KPDN1 BUS VBC, KPDN1 BUS VCA as one set — all three or none."
    );
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("VAB = VA − VB (KPDN1_VR − KPDN1_VY)");
    await createAndWait(page);

    expect(await apiChannelNames(page)).toEqual(["KPDN1 BUS VAB", "KPDN1 BUS VBC", "KPDN1 BUS VCA"]);
    await expect(page.locator("#wwCcLlResult .ww-cc-ll-result-list li")).toHaveText(["KPDN1 BUS VAB", "KPDN1 BUS VBC", "KPDN1 BUS VCA"]);
    // Pair metadata is unaffected by the names (VAB/VBC/VCA identity kept).
    const members = await page.evaluate(() => Array.from(ww.calculatedChannels.values()).map((c) => c.phase_member).sort());
    expect(members).toEqual(["AB", "BC", "CA"]);
  });

  test("an empty, duplicate or existing name blocks creation; nothing is created", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_all_three").check();
    const [ab, bc, ca] = nameInputs(page);

    await bc.fill("");
    await expect(page.locator("#wwCcLlNameError_BC")).toHaveText("Enter a name.");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    await bc.fill("KPDN1 VAB"); // same as VAB's name
    await expect(page.locator("#wwCcLlNameError_BC")).toHaveText("Each output needs a different name.");
    await expect(page.locator("#wwCcLlNameError_AB")).toHaveText("Each output needs a different name.");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    await bc.fill("KPDN1 VBC");
    await expect(page.locator("#wwCcLlNameError_BC")).toBeHidden();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    expect(await apiChannelNames(page)).toEqual([]); // zero partial channels

    // A name that already exists in the workspace is flagged on its own field.
    await page.locator("#wwCcDrawerCloseBtn").click();
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_CA").check();
    await createAndWait(page); // creates "KPDN1 VCA"
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_all_three").check();
    await expect(page.locator("#wwCcLlNameError_CA")).toHaveText("A calculated channel with this name already exists.");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
    expect(await apiChannelNames(page)).toEqual(["KPDN1 VCA"]);
    await nameInputs(page)[2].fill("KPDN1 VCA 2");
    await createAndWait(page);
    expect(await apiChannelNames(page)).toEqual(["KPDN1 VAB", "KPDN1 VBC", "KPDN1 VCA", "KPDN1 VCA 2"]);
  });

  test("changing Bay / Engineering Context regenerates the defaults", async ({ page }) => {
    await uploadFixture(page);
    // A second ready bay with a distinct name: upload the fixture again
    // and rename that upload's own KPDN1 context.
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(2);
    const renamed = await page.evaluate(async () => {
      const base = apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/engineering-contexts";
      const kpdn1 = (await (await fetch(base)).json()).filter((c) => c.display_name === "KPDN1");
      const second = kpdn1[kpdn1.length - 1];
      const r = await fetch(base + "/" + second.id, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: "KPDN9" }),
      });
      return kpdn1.length === 2 && r.ok;
    });
    expect(renamed).toBe(true);

    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_all_three").check();
    const [ab, bc, ca] = nameInputs(page);
    await ab.fill("edited name");
    await selectBay(page, "KPDN9");
    await expect(nameInputs(page)[0]).toHaveValue("KPDN9 VAB");
    await expect(nameInputs(page)[1]).toHaveValue("KPDN9 VBC");
    await expect(nameInputs(page)[2]).toHaveValue("KPDN9 VCA");
    await expect(page.locator("#wwCcLlPlannedNames")).toHaveText("Creates KPDN9 VAB, KPDN9 VBC, KPDN9 VCA as one set — all three or none.");
    await createAndWait(page);
    expect(await apiChannelNames(page)).toEqual(["KPDN9 VAB", "KPDN9 VBC", "KPDN9 VCA"]);
  });
});

// Owner UAT: the operation picker is name-only, compact, two columns with
// Line-to-Line full width. Cosmetic only -- selection behaviour unchanged.
test.describe("Calculated Channel operation picker", () => {
  test("seven name-only cards; selection and the L-L workflow still work", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);

    const cards = page.locator("#wwCcOperationCards .ww-cc-operation-card");
    await expect(cards).toHaveText([
      "Reverse Polarity", "Absolute Value", "Multiply by Constant", "RMS",
      "Addition", "Subtraction", "Line-to-Line Voltage (L-L)",
    ]);
    await expect(cards.locator("*")).toHaveCount(0); // no description/arity lines
    await expect(page.locator("#wwCcDrawer")).not.toContainText("Define the operation and inputs");
    await expect(page.locator("#wwCcOperationCards")).not.toContainText("1-cycle true RMS");
    await expect(page.locator('#wwCcOperationCards [aria-pressed="true"]')).toHaveCount(0); // default unchanged

    // Layout: compact height, two columns, L-L spans both, no overflow.
    const boxes = await cards.evaluateAll((els) => els.map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height, clipped: el.scrollWidth > el.clientWidth };
    }));
    for (const b of boxes) {
      expect(b.h).toBeGreaterThanOrEqual(52);
      expect(b.h).toBeLessThanOrEqual(58);
      expect(b.clipped).toBe(false);
    }
    expect(boxes[0].y).toBe(boxes[1].y);
    expect(boxes[1].x).toBeGreaterThan(boxes[0].x);
    expect(boxes[6].w).toBeGreaterThan(boxes[0].w * 1.9);
    const drawerBody = page.locator("#wwCcDrawer .ww-cc-drawer-body");
    expect(await drawerBody.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);

    // Narrow drawer: still two columns on a phone, stacked below 360px;
    // never clipped or horizontally scrolling.
    for (const [width, columns] of [[390, 2], [320, 1]]) {
      await page.setViewportSize({ width, height: 800 });
      const narrow = await cards.evaluateAll((els) => els.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.x), clipped: el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight };
      }));
      expect(new Set(narrow.map((b) => b.x)).size, `${width}px columns`).toBe(columns);
      expect(narrow.every((b) => !b.clipped), `${width}px no clipping`).toBe(true);
      expect(await drawerBody.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    }
    await page.setViewportSize({ width: 1280, height: 720 });

    await cards.nth(1).click();
    await expect(cards.nth(1)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('#wwCcOperationCards [aria-pressed="true"]')).toHaveCount(1);
    await expect(page.locator("#wwCcBuilderTitle")).toHaveText("Absolute Value");

    await cards.nth(6).focus();
    await page.keyboard.press("Enter");
    await expect(cards.nth(6)).toHaveAttribute("aria-pressed", "true");
    await expect(cards.nth(1)).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwCcBuilderTitle")).toHaveText("Line-to-Line Voltage (L-L)");
    await expect(page.locator("#wwCcLlContextSelect")).toBeVisible();
  });
});

// DEC-117: app-wide Line-to-Line electrical notation (display only).
test.describe("Line-to-Line Voltage -- electrical notation (DEC-117)", () => {
  const subs = (locator) => locator.locator(".ww-ll-sub");

  async function apiChannels(page) {
    return page.evaluate(async () => {
      const r = await fetch(apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/calculated-channels");
      return (await r.json()).map((c) => ({ name: c.name, phase_member: c.phase_member })).sort((a, b) => (a.name < b.name ? -1 : 1));
    });
  }

  test("system-generated notation on every surface; internal/API values stay plain", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    // Output selectors, All Three labels, formula preview. (The operation
    // card itself is name-only since the operation-picker cleanup.)
    await expect(page.locator('.ww-cc-operation-card[data-operation="line_to_line_voltage"]')).toHaveText("Line-to-Line Voltage (L-L)");
    for (const pair of ["AB", "BC", "CA"]) {
      await expect(subs(page.locator(`label:has(#wwCcLlOutput_${pair})`))).toHaveText([pair]);
      await expect(page.locator(`#wwCcLlOutput_${pair}`)).toHaveValue(pair); // internal value plain
    }
    await expect(subs(page.locator("#wwCcLlNamesFields .ww-cc-ll-name-pair"))).toHaveText(["AB", "BC", "CA"]);
    await expect(subs(page.locator("#wwCcLlPlannedNames"))).toHaveText(["AB", "BC", "CA"]);
    await expect(subs(page.locator("#wwCcExpressionPreview"))).toHaveText(["AB", "A", "B", "BC", "B", "C", "CA", "C", "A"]);
    await expect(page.locator("#wwCcLlName_AB")).toHaveValue("KPDN1 VAB"); // editable value plain
    await createAndWait(page);

    // Created banner, manager list name + formula, preview status.
    await expect(subs(page.locator("#wwCcLlResult"))).toHaveText(["AB", "BC", "CA"]);
    const firstRow = page.locator(".ww-cc-list-row").first();
    await expect(subs(firstRow.locator(".ww-cc-list-row-name"))).toHaveText(["AB"]);
    await expect(subs(firstRow.locator(".ww-cc-list-row-expr"))).toHaveText(["AB", "A", "B"]);
    await expect(firstRow.locator(".ww-cc-list-row-name")).toHaveText("KPDN1 VAB"); // plain text meaning
    await expect(subs(page.locator("#wwCcPreviewStatus"))).toHaveText(["AB"]);
    await firstRow.locator(".ww-cc-menu summary").click();
    const plotAll = firstRow.locator('button[data-action="plot-batch"]');
    await expect(subs(plotAll)).toHaveText(["AB", "BC", "CA"]);
    await expect(plotAll).toHaveAttribute("aria-label", "Plot All (VAB, VBC, VCA)");
    await plotAll.click();

    // Waveform: sidebar names and Plotly trace names (identity in meta).
    await page.locator("#mainNavWaveformBtn").click();
    await expect(subs(page.locator('#calculatedChannelsSidebarBody tr[data-channel-name="KPDN1 VBC"] .channel-name-text'))).toHaveText(["BC"]);
    await expect.poll(async () => (await waveformTraces(page)).map((t) => t.rawName).sort()).toEqual(
      ["KPDN1 V<sub>AB</sub>", "KPDN1 V<sub>BC</sub>", "KPDN1 V<sub>CA</sub>"]
    );
    const metas = await page.evaluate(() => ww.panels.flatMap((p) => ((p.chartEl && p.chartEl.data) || []).map((t) => t.meta)));
    expect(metas.every((m) => /^calc-[0-9a-f]+::KPDN1 V(AB|BC|CA)$/.test(m))).toBe(true);

    // Internal/API values are unchanged.
    expect(await apiChannels(page)).toEqual([
      { name: "KPDN1 VAB", phase_member: "AB" }, { name: "KPDN1 VBC", phase_member: "BC" }, { name: "KPDN1 VCA", phase_member: "CA" },
    ]);
  });

  test("custom names containing VAB are shown exactly as typed", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_AB").check();
    await page.locator("#wwCcNameInput").fill("Backup VAB Check");
    await createAndWait(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "KPDN1");
    await page.locator("#wwCcLlOutput_BC").check();
    await page.locator("#wwCcNameInput").fill("Feeder VBC"); // ends in the pair token, but is not the system default
    await createAndWait(page);

    for (const name of ["Backup VAB Check", "Feeder VBC"]) {
      const row = page.locator(".ww-cc-list-row").filter({ hasText: name });
      await expect(row.locator(".ww-cc-list-row-name")).toHaveText(name);
      await expect(subs(row.locator(".ww-cc-list-row-name"))).toHaveCount(0);
      // The formula is system notation regardless of the channel's name.
      await expect(subs(row.locator(".ww-cc-list-row-expr")).first()).toBeVisible();
    }
    await expect(subs(page.locator("#wwCcLlResult .ww-cc-ll-result-list li"))).toHaveCount(0);

    await page.locator(".ww-cc-list-row").filter({ hasText: "Backup VAB Check" }).locator('button[data-action="toggle-visibility"]').click();
    await page.locator("#mainNavWaveformBtn").click();
    await expect.poll(async () => (await waveformTraces(page)).map((t) => t.rawName)).toEqual(["Backup VAB Check"]);
    expect(await apiChannels(page)).toEqual([
      { name: "Backup VAB Check", phase_member: "AB" }, { name: "Feeder VBC", phase_member: "BC" },
    ]);
  });
});
