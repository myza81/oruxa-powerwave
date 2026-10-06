// Composed-label word spacing (owner UAT, 2026-09-27): "Default
// ContextV<sub>AB</sub>" in the created-success banner and "RMS(" in
// readable operation text.
//
// Root cause: a name built as ordinary text + a rich symbol
// ("Default Context " + <span class="ww-electrical-symbol">) placed as bare
// children of a flex/grid container -- each text run becomes its own
// anonymous flex item and its edge whitespace is trimmed. The DOM text still
// reads "Default Context VAB", so textContent assertions passed. Fix: every
// label mixing words with rich markup is ONE inline unit, wwRichLabelHtml().
//
// Everything here is measured on rendered GLYPHS (support/
// text_spacing_helpers.js), never only on textContent. Real backend + real
// frontend, no mocks.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { expectTrueSubscripts } = require("./support/electrical_notation_helpers");
const {
  wordBoundaryGeometry, expectWordSpacingPreserved, findFlexWhitespaceLoss, expectNoFlexWhitespaceLoss,
} = require("./support/text_spacing_helpers");
const { ensureContextSelected } = require("./support/engineering_context_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

async function upload(page, cfg, dat) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, cfg));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, dat));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}
// Bare VA/VB/VC -> one rootless bay, "Default Context" (A/B/C).
const uploadDefaultContext = (page) => upload(page, "phasor_bare_three_phase.cfg", "phasor_smoke_three_phase.dat");
// KPDN1 (R/Y/B), MCRS (A/B/C) and a lone AMBG_VB in one file (DEC-118).
const uploadMixedConventions = (page) => upload(page, "phase_convention_mixed.cfg", "phase_convention_mixed.dat");

async function openCalculatedChannels(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function openOperation(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`#wwCcOperationCards .ww-cc-operation-card[data-operation="${operation}"]`).click();
}

async function selectOptionStartingWith(page, selector, prefix) {
  await expect.poll(() => page.locator(`${selector} option`).evaluateAll(
    (options, p) => options.some((o) => o.textContent.startsWith(p)), prefix)).toBe(true);
  const value = await page.locator(`${selector} option`).evaluateAll(
    (options, p) => options.find((o) => o.textContent.startsWith(p)).value, prefix);
  await page.locator(selector).selectOption(value);
}

async function createAndWait(page) {
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

async function createAllThree(page, bay) {
  await openOperation(page, "line_to_line_voltage");
  await selectOptionStartingWith(page, "#wwCcLlContextSelect", `${bay} — `);
  await page.locator("#wwCcLlOutput_all_three").check();
  await createAndWait(page);
}

async function openUnary(page, operation, inputPrefix) {
  await openOperation(page, operation);
  await selectOptionStartingWith(page, "#wwCcUnaryInputSelect", inputPrefix);
}

// The rendered boundary whose left-hand text ends with `before` and whose
// next glyph is `after` -- e.g. ("Context", "V") or ("RMS", "(").
async function boundary(locator, before, after) {
  const [measured] = await wordBoundaryGeometry(locator);
  // context = "<up to 14 chars before>|<next glyph>"
  const b = measured.boundaries.find((x) => x.context.slice(-1) === after && x.context.slice(-2, -1) === "|" &&
    x.context.slice(0, -2).trimEnd().endsWith(before));
  expect(b, `${measured.text}: boundary "${before}|${after}"`).toBeTruthy();
  return b;
}
async function expectSpaceBetween(locator, before, after) {
  const b = await boundary(locator, before, after);
  expect(b.spaced, `DOM space before "${after}"`).toBe(true);
  expect(b.gapSpaces, `"${before} ${after}" renders one space`).toBeGreaterThan(0.6);
  expect(b.gapSpaces, `"${before} ${after}" not an oversized gap`).toBeLessThan(1.6);
}

test.describe("Composed labels keep their word spacing", () => {
  test("shared helper: one inline unit that keeps spaces in inline, flex, inline-flex, grid, field, banner and card contexts", async ({ page }) => {
    await page.goto("/index.html");
    const out = await page.evaluate(() => {
      const ryb = { convention: "RYB", status: "established", symbols: { A: "R", B: "Y", C: "B", AB: "RY", BC: "YB", CA: "BR" } };
      const abcLl = { id: "calc-spacing-abc", operation: "line_to_line_voltage", phase_member: "AB", name: "Default Context VAB",
        parameters: { engineering_context_name: "Default Context" }, inputs: [] };
      const rybLl = { id: "calc-spacing-ryb", operation: "line_to_line_voltage", phase_member: "AB", name: "KPDN1 VRY",
        parameters: { engineering_context_name: "KPDN1", phase_display: ryb }, inputs: [] };
      ww.calculatedChannels.set(abcLl.id, abcLl);
      ww.calculatedChannels.set(rybLl.id, rybLl);
      const rms = (id) => ({ operation: "rms", inputs: [{ kind: "calculated", calculated_channel_id: id }], parameters: { nominal_frequency_hz: 50 } });
      const labels = {
        abcName: wwCalculatedChannelNameHtml(abcLl),
        rybName: wwCalculatedChannelNameHtml(rybLl),
        abcRms: wwCcExpressionHtmlFor(rms(abcLl.id)),
        rybRms: wwCcExpressionHtmlFor(rms(rybLl.id)),
        formula: wwLineToLineFormulaHtml("AB", ryb),
        sequence: wwRichLabelHtml("Voltage " + wwRoleLabelHtml("V1") + " / Current " + wwRoleLabelHtml("I2")),
        phase: wwRichLabelHtml("KPDN1 " + wwPhaseVoltageHtml("A", ryb)),
      };
      const text = {
        abcRms: wwCcExpressionTextFor(rms(abcLl.id)),
        rybRms: wwCcExpressionTextFor(rms(rybLl.id)),
        abcName: wwCalculatedChannelNamePlotly(abcLl),
      };
      // Every container shape a label is rendered into across the app.
      const hosts = {
        inline: (h) => `<p>${h}</p>`,
        flex: (h) => `<div style="display:flex; align-items:center">${h}</div>`,
        inlineFlexBanner: (h) => `<ul class="ww-cc-ll-result-list"><li><span class="channel-color-dot"></span>${h}</li></ul>`,
        grid: (h) => `<div style="display:grid; grid-template-columns:auto">${h}</div>`,
        ccField: (h) => `<label class="ww-cc-field"><span>${h}</span></label>`,
        listRow: (h) => `<div class="ww-cc-list-row-name"><span>${h}</span></div>`,
        card: (h) => `<button type="button" class="ww-cc-menu-item" style="display:inline-flex">${h}</button>`,
        ellipsis: (h) => `<div style="display:flex"><span class="channel-name-text">${h}</span></div>`,
      };
      const harness = document.createElement("div");
      harness.id = "spacingHarness";
      harness.style.cssText = "position:fixed; left:0; top:0; width:900px; z-index:99999; background:var(--bg, #fff); font-size:14px;";
      let html = "";
      for (const [hostName, host] of Object.entries(hosts)) {
        for (const [labelName, label] of Object.entries(labels)) {
          html += `<div data-case="${hostName}:${labelName}">${host(label)}</div>`;
        }
      }
      // Negative control: the pre-fix composition (bare text + symbol).
      html += `<div data-control="unwrapped">${hosts.inlineFlexBanner(escapeHtml("Default Context ") + wwLineToLinePairHtml("AB"))}</div>`;
      harness.innerHTML = html;
      document.body.appendChild(harness);
      ww.calculatedChannels.delete(abcLl.id);
      ww.calculatedChannels.delete(rybLl.id);
      return { labels, text };
    });

    // Plain text and the stored name are untouched; no entities, no underscore.
    expect(out.text.abcRms).toBe("RMS (Default Context VAB, 50 Hz, 1 cycle)");
    expect(out.text.rybRms).toBe("RMS (KPDN1 VRY, 50 Hz, 1 cycle)");
    expect(out.text.abcName).toBe("Default Context V<sub>AB</sub>");
    for (const html of Object.values(out.labels)) {
      expect(html.startsWith('<span class="ww-rich-label">')).toBe(true);
      expect(html).not.toMatch(/&nbsp;|&#160;| |V_/);
    }
    await expect(page.locator('[data-case$=":abcName"]').first()).toHaveText("Default Context VAB");

    const cases = page.locator("#spacingHarness [data-case]");
    const count = await cases.count();
    expect(count).toBe(8 * 7);
    for (let i = 0; i < count; i += 1) {
      const c = cases.nth(i);
      const name = await c.getAttribute("data-case");
      await test.step(name, async () => {
        await expectWordSpacingPreserved(c, { count: 1 });
        if (/Name$/.test(name)) await expectSpaceBetween(c, /ryb/.test(name) ? "KPDN1" : "Context", "V");
        if (/Rms$/.test(name)) {
          await expectSpaceBetween(c, "RMS", "(");
          await expectSpaceBetween(c, /ryb/.test(name) ? "KPDN1" : "Context", "V");
        }
      });
    }
    await expectTrueSubscripts(page.locator("#spacingHarness [data-case] .ww-electrical-symbol"));
    await expectNoFlexWhitespaceLoss(page, "#spacingHarness [data-case]");

    // The detectors really catch the defect: the unwrapped pre-fix shape
    // renders "Default ContextV<sub>AB</sub>".
    const control = page.locator('#spacingHarness [data-control="unwrapped"]');
    await expect(control).toHaveText("Default Context VAB"); // the DOM still has the space...
    const joined = await boundary(control, "Context", "V");
    expect(joined.spaced).toBe(true);
    expect(joined.gapSpaces).toBeLessThan(0.2); // ...but it is not rendered
    expect((await findFlexWhitespaceLoss(page, '#spacingHarness [data-control="unwrapped"]')).length).toBe(1);
  });

  test("Calculated Channels, A/B/C Default Context: owner screenshots -- success banner, RMS builder, list and Preview", async ({ page }) => {
    await uploadDefaultContext(page);
    await openCalculatedChannels(page);
    await createAllThree(page, "Default Context");

    // Created-success banner (inline-flex rows) -- owner screenshot 3.
    const banner = page.locator("#wwCcLlResult li");
    await expect(banner).toHaveText(["Default Context VAB", "Default Context VBC", "Default Context VCA"]);
    await expectWordSpacingPreserved(banner, { count: 3 });
    for (let i = 0; i < 3; i += 1) await expectSpaceBetween(banner.nth(i), "Context", "V");
    await expectTrueSubscripts(banner.locator(".ww-electrical-symbol"), 3);

    // RMS over Default Context VAB -- owner screenshot 2.
    await openUnary(page, "rms", "Default Context VAB");
    const preview = page.locator("#wwCcExpressionPreview");
    await expect(preview).toHaveText("Result = RMS (Default Context VAB, 50 Hz, 1 cycle)");
    await expectWordSpacingPreserved(preview, { count: 1 });
    await expectSpaceBetween(preview, "RMS", "(");
    await expectSpaceBetween(preview, "Context", "V");
    await expect(page.locator("#wwCcNameInput")).toHaveValue("RMS (Default Context VAB)"); // editable: plain
    await expectNoFlexWhitespaceLoss(page, "#wwCcDrawer");
    await createAndWait(page);

    const row = page.locator(".ww-cc-list-row").filter({ hasText: "RMS (Default Context VAB)" });
    await expect(row.locator(".ww-cc-list-row-expr")).toHaveText("RMS (Default Context VAB, 50 Hz, 1 cycle)");
    await expect(row.locator(".ww-cc-list-row-summary")).toHaveText("RMS · Default Context VAB · Null: Propagate");
    for (const part of [".ww-cc-list-row-name", ".ww-cc-list-row-expr", ".ww-cc-list-row-summary"]) {
      await expectWordSpacingPreserved(row.locator(part), { count: 1 });
    }
    await expectSpaceBetween(row.locator(".ww-cc-list-row-expr"), "RMS", "(");
    await expectSpaceBetween(row.locator(".ww-cc-list-row-expr"), "Context", "V");
    await expectWordSpacingPreserved(page.locator(".ww-cc-list-row-name"), { count: 4 }); // L-L names too

    // Preview: Selected line, Expression and Source rows.
    await row.locator(".ww-cc-list-row-name").click();
    const status = page.locator("#wwCcPreviewStatus > .ww-rich-label");
    await expect(status).toHaveText("Selected: RMS (Default Context VAB) (hidden)");
    await expectWordSpacingPreserved(status, { count: 1 });
    const infoValues = page.locator("#wwCcPreviewInfoStrip .ww-cc-preview-info-value");
    await expect(infoValues.first()).toHaveText("RMS (Default Context VAB, 50 Hz, 1 cycle)");
    await expectWordSpacingPreserved(infoValues.first(), { count: 1 });
    await expectSpaceBetween(infoValues.first(), "Context", "V");
    await page.locator(".ww-cc-list-row").first().locator(".ww-cc-list-row-name").click();
    await expect(page.locator("#wwCcPreviewStatus > .ww-rich-label")).toHaveText("Selected: Default Context VAB (hidden)");
    await expectSpaceBetween(page.locator("#wwCcPreviewStatus > .ww-rich-label"), "Context", "V");
    await expectNoFlexWhitespaceLoss(page, "#pageCalculatedChannels");
  });

  test("Calculated Channels, R/Y/B KPDN1: every operation -- defaults, formula, list, menu, Waveform sidebar and legend", async ({ page }) => {
    await uploadMixedConventions(page);
    await openCalculatedChannels(page);
    await createAllThree(page, "KPDN1");
    await expect(page.locator("#wwCcLlResult li")).toHaveText(["KPDN1 VRY", "KPDN1 VYB", "KPDN1 VBR"]);
    await expectWordSpacingPreserved(page.locator("#wwCcLlResult li"), { count: 3 });
    await expectSpaceBetween(page.locator("#wwCcLlResult li").first(), "KPDN1", "V");

    // Readable operation words take "Name ("; symbolic forms are unchanged.
    const cases = [
      ["rms", "RMS (KPDN1 VRY)", "Result = RMS (KPDN1 VRY, 50 Hz, 1 cycle)", "RMS (KPDN1 VRY, 50 Hz, 1 cycle)"],
      ["absolute_value", "Abs (KPDN1 VRY)", "Result = |KPDN1 VRY|", "|KPDN1 VRY|"],
      ["reverse_polarity", "-KPDN1 VRY", "Result = −KPDN1 VRY", "-1 × KPDN1 VRY"],
      // The builder preview keeps "k" until the constant field re-renders it
      // (pre-existing, not a spacing matter) -- either spelling is accepted.
      ["multiply_constant", "2 × KPDN1 VRY", /^Result = (k|2) × KPDN1 VRY$/, "2 × KPDN1 VRY"],
    ];
    for (const [operation, defaultName, previewText, listExpr] of cases) {
      await openUnary(page, operation, "KPDN1 VRY");
      if (operation === "multiply_constant") await page.locator("#wwCcConstantInput").fill("2");
      await expect(page.locator("#wwCcNameInput")).toHaveValue(defaultName);
      await expect(page.locator("#wwCcExpressionPreview")).toHaveText(previewText);
      await expectWordSpacingPreserved(page.locator("#wwCcExpressionPreview"), { count: 1 });
      await createAndWait(page);
      const expr = page.locator(".ww-cc-list-row").filter({ hasText: defaultName }).first().locator(".ww-cc-list-row-expr");
      await expect(expr).toHaveText(listExpr);
      await expectWordSpacingPreserved(expr, { count: 1 });
    }

    // KPDN1 VRY + another channel, then a nested RMS over that sum.
    await openOperation(page, "addition");
    for (const name of ["KPDN1 VRY", "KPDN1 VYB"]) {
      await selectOptionStartingWith(page, "#wwCcAddInputSelect", name);
      await page.locator("#wwCcAddInputBtn").click();
    }
    await expect(page.locator("#wwCcNameInput")).toHaveValue("KPDN1 VRY + KPDN1 VYB");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = KPDN1 VRY + KPDN1 VYB");
    await expectWordSpacingPreserved(page.locator("#wwCcExpressionPreview"), { count: 1 });
    await createAndWait(page);
    await openUnary(page, "rms", "KPDN1 VRY + KPDN1 VYB");
    await expect(page.locator("#wwCcNameInput")).toHaveValue("RMS (KPDN1 VRY + KPDN1 VYB)");
    await expect(page.locator("#wwCcExpressionPreview")).toHaveText("Result = RMS (KPDN1 VRY + KPDN1 VYB, 50 Hz, 1 cycle)");
    await expectSpaceBetween(page.locator("#wwCcExpressionPreview"), "RMS", "(");
    await createAndWait(page);

    // The whole manager list, every name/formula/summary row, both themes.
    const rowParts = page.locator(".ww-cc-list-row-name, .ww-cc-list-row-expr, .ww-cc-list-row-summary");
    await expectWordSpacingPreserved(rowParts, { count: 3 * 9 });
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await expectWordSpacingPreserved(rowParts, { count: 3 * 9 });
    await expectTrueSubscripts(page.locator(".ww-cc-list-row .ww-electrical-symbol"));
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));

    // Plot All menu ("Plot All (VRY, VYB, VBR)").
    const firstRow = page.locator(".ww-cc-list-row").first();
    await firstRow.locator(".ww-cc-menu summary").click();
    const plotAll = firstRow.locator('button[data-action="plot-batch"]');
    await expect(plotAll).toHaveText("Plot All (VRY, VYB, VBR)");
    await expectWordSpacingPreserved(plotAll.locator("> .ww-rich-label"), { count: 1 });
    await expectSpaceBetween(plotAll.locator("> .ww-rich-label"), "All", "(");
    await expectNoFlexWhitespaceLoss(page, "#pageCalculatedChannels");

    // Preview charts: Plotly legend (SVG text) -- rich L-L name, plain stored names.
    await plotAll.click();
    for (const name of ["RMS (KPDN1 VRY)"]) {
      const eye = page.locator(".ww-cc-list-row").filter({ hasText: name }).first().locator('button[data-action="toggle-visibility"]');
      if ((await eye.getAttribute("aria-pressed")) !== "true") await eye.click();
    }
    const legend = page.locator("#wwCcPreviewPanels .legendtext");
    await expect.poll(() => legend.allTextContents()).toEqual(expect.arrayContaining(["RMS (KPDN1 VRY) (kV)"]));
    expect((await legend.allTextContents()).map((t) => t.replace(/\u200b/g, ""))).toEqual(expect.arrayContaining(["KPDN1 VRY (kV)"]));
    await expectWordSpacingPreserved(legend, { count: 4 });

    // Waveform: calculated-channel sidebar entries.
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const sidebar = page.locator('#calculatedChannelsSidebarBody tr[data-channel-name="KPDN1 VRY"] .channel-name-text');
    await expect(sidebar).toHaveText("KPDN1 VRY (kV)");
    await expectWordSpacingPreserved(sidebar, { count: 1 });
    await expectSpaceBetween(sidebar, "KPDN1", "V");
    await expectWordSpacingPreserved(page.locator("#calculatedChannelsSidebarBody .channel-name-text"), { count: 9 });
    await expectNoFlexWhitespaceLoss(page, "#workspaceSidebar");
  });

  test("narrow drawer and list: labels still wrap/ellipsize, never an unbreakable string, and spacing survives", async ({ page }) => {
    await uploadDefaultContext(page);
    await openCalculatedChannels(page);
    await createAllThree(page, "Default Context");
    await page.setViewportSize({ width: 420, height: 900 });
    await expectWordSpacingPreserved(page.locator("#wwCcLlResult li"), { count: 3 });

    // L-L builder at phone width: the planned-names sentence and the formula
    // preview wrap onto several lines instead of overflowing.
    await openOperation(page, "line_to_line_voltage");
    await selectOptionStartingWith(page, "#wwCcLlContextSelect", "Default Context — ");
    await page.locator("#wwCcLlOutput_all_three").check();
    for (const [selector, content] of [["#wwCcLlPlannedNames", "Creates"], ["#wwCcExpressionPreview", " = "]]) {
      const el = page.locator(selector);
      // Readiness re-renders the builder asynchronously: measure only once
      // the label is visible, populated and has painted glyphs.
      await expect(el).toBeVisible();
      await expect(el).toContainText(content);
      const measure = () => el.evaluate((node) => {
        // First and last painted glyph: a wrapped label ends on a lower line.
        const rects = [];
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        let t;
        while ((t = walker.nextNode())) {
          for (let i = 0; i < t.nodeValue.length; i += 1) {
            if (/\s/.test(t.nodeValue[i])) continue;
            const r = document.createRange();
            r.setStart(t, i);
            r.setEnd(t, i + 1);
            const rect = r.getClientRects()[0];
            if (rect && rect.width > 0) rects.push(rect);
          }
        }
        if (rects.length === 0) return { painted: 0 };
        const first = rects[0];
        const last = rects[rects.length - 1];
        return { painted: rects.length, wrapped: last.top >= first.bottom, overflow: node.scrollWidth - node.clientWidth };
      });
      await expect.poll(async () => (await measure()).painted, `${selector} has painted glyphs`).toBeGreaterThan(0);
      const box = await measure();
      expect(box.wrapped, `${selector} wraps`).toBe(true);
      expect(box.overflow, `${selector} does not overflow`).toBeLessThanOrEqual(1);
      await expectWordSpacingPreserved(el, { count: 1 });
    }
    await expectNoFlexWhitespaceLoss(page, "#wwCcDrawer");
    await page.locator("#wwCcCancelBtn, .ww-cc-drawer-close").first().click().catch(() => page.keyboard.press("Escape"));

    // A long list formula ellipsizes inside its row (owning component rule).
    await openUnary(page, "rms", "Default Context VAB");
    await createAndWait(page);
    const expr = page.locator(".ww-cc-list-row").filter({ hasText: "RMS (Default Context VAB)" }).locator(".ww-cc-list-row-expr");
    const clip = await expr.evaluate((node) => ({ overflow: node.scrollWidth - node.clientWidth, style: getComputedStyle(node).textOverflow }));
    expect(clip.style).toBe("ellipsis");
    await expectWordSpacingPreserved(page.locator(".ww-cc-list-row-name"), { count: 4 });
  });

  test("Analysis and Compliance: symbol labels and composed rows keep their spacing (R/Y/B and A/B/C)", async ({ page }) => {
    await uploadMixedConventions(page);
    const contexts = await page.evaluate(async () => {
      const url = apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/engineering-contexts";
      return Object.fromEntries((await (await fetch(url)).json()).map((c) => [c.display_name, c.id]));
    });
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();

    // Phasor values (V<sub>R</sub>) in both bays.
    for (const bay of ["KPDN1", "MCRS"]) {
      await ensureContextSelected(page, page.locator("#wwPhasorContextSelect"), contexts[bay]);
      await expect(page.locator("#wwPhasorValuesList .ww-electrical-symbol")).toHaveCount(6); // 3 V + 3 I
      await expectNoFlexWhitespaceLoss(page, "#pageAnalysis");
    }

    // Sequence: V<sub>2</sub> / V<sub>1</sub> ratios, a " / " between two symbols.
    await page.locator("#wwAnalysisTypeSequenceBtn").click();
    await ensureContextSelected(page, page.locator("#wwSequenceContextSelect"), contexts.KPDN1);
    const ratio = page.locator("#wwSequenceRatiosList .ww-phasor-role-label > .ww-rich-label");
    await expect(ratio.first()).toHaveText("V2 / V1");
    await expectWordSpacingPreserved(ratio);
    await expectTrueSubscripts(page.locator("#wwSequenceValuesList .ww-electrical-symbol"));
    await expectNoFlexWhitespaceLoss(page, "#pageAnalysis");

    // Distance Manual Input: "V<sub>A</sub> magnitude".
    await page.locator("#wwAnalysisTypeDistanceBtn").click();
    await page.locator("#wwDistanceInputSourceManualBtn").click();
    const distanceLabel = page.locator("#wwDistanceManualV1Label");
    await expect(distanceLabel).toHaveText("VA magnitude");
    await expectWordSpacingPreserved(distanceLabel, { count: 1 });
    await expectSpaceBetween(distanceLabel, "A", "m");
    await expectNoFlexWhitespaceLoss(page, "#pageAnalysis");

    // Compliance (DEC-167): the required voltages of the active Reference,
    // "V<sub>R</sub> — fundamental RMS needs preparation".
    const workspaceId = await page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
    const base = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}/api/v1/workspaces/${encodeURIComponent(workspaceId)}`;
    const profile = await page.request.post(`${base}/reference-profiles`, { data: {
      name: "Spacing reference", category: "grid_requirement",
      assessment_definition: { representation: "phase_ground_rms", phase_treatment: "each_phase" },
      unit: "kV", display_start_time: 0, display_end_time: 3, evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
      lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
      upper_boundary: null, metadata: {},
    } });
    await page.request.post(`${base}/reference-layers`, { data: { profile_id: (await profile.json()).id, visible: true } });
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
    const groupLabel = (await page.locator("#wwComplianceGroupSelect option").allTextContents()).find((t) => t.startsWith("KPDN1"));
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: groupLabel });
    const members = page.locator(".ww-compliance-member-list li");
    await expect(members).toHaveCount(3);
    await expect(members.first()).toContainText("VR — ");
    await expectWordSpacingPreserved(members.locator(".ww-rich-label"), { count: 3 });
    await expectNoFlexWhitespaceLoss(page, "#pageCompliance");
  });
});
