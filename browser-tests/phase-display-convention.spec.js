// DEC-118: context-specific phase display convention -- real backend +
// real frontend, no mocks.
//
// Fixture backend/tests/fixtures/comtrade/phase_convention_mixed: ONE file,
// so all three bays live in the SAME workspace:
//   KPDN1 -- KPDN1_VR/VY/VB (+ IR/IY/IB)  -> R/Y/B: VR VY VB, VRY VYB VBR
//   MCRS  -- MCRS_VA/VB/VC (+ IA/IB/IC)   -> A/B/C: VA VB VC, VAB VBC VCA
//   AMBG  -- AMBG_VB alone                -> undecidable: never guessed,
//                                            canonical A/B/C fallback
//
// Canonical identities never change: phase_member AB/BC/CA, role keys
// Va/Vb/Vc, output values AB/BC/CA, Plotly trace meta. Source channel names
// (KPDN1_VR, MCRS_VB) stay verbatim. Plain fallback is concatenated (VRY),
// never an underscore form.

const { test, expect } = require("@playwright/test");
const path = require("path");
const { expectTrueSubscripts } = require("./support/electrical_notation_helpers");
const { ensureContextSelected } = require("./support/engineering_context_helpers");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "phase_convention_mixed";

const subs = (locator) => locator.locator(".ww-electrical-sub");

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

async function contextsByName(page) {
  return page.evaluate(async () => {
    const url = apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/engineering-contexts";
    const contexts = await (await fetch(url)).json();
    return Object.fromEntries(contexts.map((c) => [c.display_name, c]));
  });
}

async function openLineToLineBuilder(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="line_to_line_voltage"]').click();
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

async function createAllThree(page, bay) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="line_to_line_voltage"]').click();
  await expect(page.locator("#wwCcLlContextSelect")).toBeVisible();
  await selectBay(page, bay);
  await page.locator("#wwCcLlOutput_all_three").check();
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// Expected per-bay spelling, keyed by canonical member.
const RYB = { phases: ["R", "Y", "B"], pairs: ["RY", "YB", "BR"], names: ["VR", "VY", "VB"] };
const ABC = { phases: ["A", "B", "C"], pairs: ["AB", "BC", "CA"], names: ["VA", "VB", "VC"] };

test.describe("Phase display convention (DEC-118)", () => {
  test("shared formatter: a context map changes only the spelling, never identity; no underscore", async ({ page }) => {
    await page.goto("/index.html");
    const out = await page.evaluate(() => {
      const ryb = { convention: "RYB", status: "established", symbols: { A: "R", B: "Y", C: "B", AB: "RY", BC: "YB", CA: "BR" } };
      const bogus = { convention: "XYZ", status: "established", symbols: { A: "<b>", B: "Y", C: "B", AB: "RY", BC: "YB", CA: "BR" } };
      return {
        role: [wwRoleLabelText("Va", ryb), wwRoleLabelHtml("Vc", ryb), wwRoleLabelPlotly("Vb", ryb), wwRoleLabelSvg("Va", ryb)],
        sequence: [wwRoleLabelText("V1", ryb), wwRoleLabelText("I2", ryb), wwRoleLabelText("Ia", ryb)],
        pair: [wwLineToLinePairText("AB", ryb), wwLineToLinePairText("BC", ryb), wwLineToLinePairText("CA", ryb), wwLineToLinePairHtml("AB", ryb)],
        formula: [wwLineToLineFormulaText("AB", ryb), wwLineToLineFormulaText("BC", ryb), wwLineToLineFormulaText("CA", ryb)],
        defaultName: [wwLineToLineDefaultName("KPDN1", "AB", ryb), wwLineToLineDefaultName("MCRS", "AB")],
        canonical: [wwRoleLabelText("Va"), wwLineToLineFormulaText("AB"), wwLineToLinePairText("AB", null)],
        untrusted: [wwRoleLabelText("Va", bogus), wwLineToLinePairText("AB", bogus)],
      };
    });
    expect(out.role).toEqual([
      "VR",
      '<span class="ww-electrical-symbol">V<sub class="ww-electrical-sub">B</sub></span>',
      "V<sub>Y</sub>",
      'V<tspan font-size="0.72em" dy="0.3em">R</tspan>',
    ]);
    expect(out.sequence).toEqual(["V1", "I2", "Ia"]); // sequence + phase current: convention-independent
    expect(out.pair.slice(0, 3)).toEqual(["VRY", "VYB", "VBR"]);
    expect(out.pair[3]).toBe('<span class="ww-electrical-symbol">V<sub class="ww-electrical-sub">RY</sub></span>');
    // Canonical arithmetic AB = A − B, BC = B − C, CA = C − A, spelled R/Y/B.
    expect(out.formula).toEqual(["VRY = VR − VY", "VYB = VY − VB", "VBR = VB − VR"]);
    expect(out.defaultName).toEqual(["KPDN1 VRY", "MCRS VAB"]);
    expect(out.canonical).toEqual(["VA", "VAB = VA − VB", "VAB"]);
    // An unrecognised token set is never subscripted -- canonical fallback.
    expect(out.untrusted).toEqual(["VA", "VAB"]);
    expect(JSON.stringify(out)).not.toMatch(/V_/);
  });

  test("mixed workspace: backend reports R/Y/B, A/B/C and an unguessed lone VB", async ({ page }) => {
    await uploadFixture(page);
    const contexts = await contextsByName(page);
    expect(contexts.KPDN1.phase_display).toMatchObject({ convention: "RYB", status: "established" });
    expect(contexts.MCRS.phase_display).toMatchObject({ convention: "ABC", status: "established" });
    expect(contexts.AMBG.phase_display).toMatchObject({ convention: null, status: "canonical_fallback" });
    // Canonical identities are unchanged: KPDN1_VB is canonical C, MCRS_VB canonical B.
    const phaseOf = (ctx, name) => ctx.members.find((m) => m.channel_ref.channel_name === name).phase;
    expect(phaseOf(contexts.KPDN1, "KPDN1_VB")).toBe("C");
    expect(phaseOf(contexts.MCRS, "MCRS_VB")).toBe("B");
    expect(phaseOf(contexts.AMBG, "AMBG_VB")).toBe("unknown");
  });

  test("Calculated Channels: readiness, outputs, formula and default names follow each bay", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);

    for (const [bay, conv] of [["KPDN1", RYB], ["MCRS", ABC]]) {
      await selectBay(page, bay);
      await page.locator("#wwCcLlOutput_all_three").check();
      const status = page.locator("#wwCcLlStatus");
      await expect(status).toHaveAttribute("data-phase-convention", bay === "KPDN1" ? "RYB" : "ABC");
      // Readiness: symbol in the bay's convention, then the exact source name.
      await expect(subs(status)).toHaveText(conv.phases);
      await expect(status.locator("li strong")).toHaveText(conv.names);
      await expect(status.locator("li")).toContainText([`${bay}_V${bay === "KPDN1" ? "R" : "A"}`]);
      await expectTrueSubscripts(status.locator(".ww-electrical-symbol"), 3);
      // Output choices: display spelling; the radio values stay canonical.
      for (const [i, pair] of ["AB", "BC", "CA"].entries()) {
        await expect(subs(page.locator(`label:has(#wwCcLlOutput_${pair})`))).toHaveText([conv.pairs[i]]);
        await expect(page.locator(`#wwCcLlOutput_${pair}`)).toHaveValue(pair);
      }
      await expectTrueSubscripts(page.locator(".ww-cc-ll-outputs .ww-electrical-symbol"), 3);
      // Default names (plain, editable) and planned-names summary (rich).
      const expectedNames = conv.pairs.map((p) => `${bay} V${p}`);
      for (const [i, pair] of ["AB", "BC", "CA"].entries()) {
        await expect(page.locator(`#wwCcLlName_${pair}`)).toHaveValue(expectedNames[i]);
      }
      await expect(page.locator("#wwCcLlPlannedNames")).toHaveText(`Creates ${expectedNames.join(", ")} as one set — all three or none.`);
      await expect(subs(page.locator("#wwCcLlPlannedNames"))).toHaveText(conv.pairs);
      // Formula preview: every symbol from one context, canonical operands.
      const [a, b, c] = conv.phases;
      const [ab, bc, ca] = conv.pairs;
      await expect(subs(page.locator("#wwCcExpressionPreview"))).toHaveText([ab, a, b, bc, b, c, ca, c, a]);
      await expect(page.locator("#wwCcExpressionPreview .ww-cc-ll-formula").first())
        .toHaveText(`V${ab} = V${a} − V${b} (${bay}_V${bay === "KPDN1" ? "R" : "A"} − ${bay}_V${bay === "KPDN1" ? "Y" : "B"})`);
      await expectTrueSubscripts(page.locator("#wwCcExpressionPreview .ww-electrical-symbol"), 9);
    }
  });

  test("Calculated Channels: created names, list, formulas and Waveform legend per bay; identity canonical", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
    await createAllThree(page, "KPDN1");
    await createAllThree(page, "MCRS");

    await expect(page.locator(".ww-cc-list-row-name")).toHaveText([
      "KPDN1 VRY", "KPDN1 VYB", "KPDN1 VBR", "MCRS VAB", "MCRS VBC", "MCRS VCA",
    ]);
    await expect(subs(page.locator(".ww-cc-list-row-name"))).toHaveText(["RY", "YB", "BR", "AB", "BC", "CA"]);
    const rows = page.locator(".ww-cc-list-row");
    await expect(rows.nth(0).locator(".ww-cc-list-row-expr")).toHaveText("VRY = VR − VY (KPDN1_VR − KPDN1_VY)");
    await expect(rows.nth(2).locator(".ww-cc-list-row-expr")).toHaveText("VBR = VB − VR (KPDN1_VB − KPDN1_VR)");
    await expect(rows.nth(3).locator(".ww-cc-list-row-expr")).toHaveText("VAB = VA − VB (MCRS_VA − MCRS_VB)");
    await expectTrueSubscripts(page.locator(".ww-cc-list-row .ww-electrical-symbol"));

    // The set's row action and its accessible name follow the set's bay.
    await rows.nth(0).locator(".ww-cc-menu summary").click();
    const plotAll = rows.nth(0).locator('button[data-action="plot-batch"]');
    await expect(plotAll).toHaveAttribute("aria-label", "Plot All (VRY, VYB, VBR)");
    await expect(subs(plotAll)).toHaveText(["RY", "YB", "BR"]);

    // Semantic metadata stays canonical: phase_member AB/BC/CA for both bays.
    const members = await page.evaluate(() => Array.from(ww.calculatedChannels.values()).map((c) => [c.name, c.phase_member]));
    expect(members).toEqual([
      ["KPDN1 VRY", "AB"], ["KPDN1 VYB", "BC"], ["KPDN1 VBR", "CA"],
      ["MCRS VAB", "AB"], ["MCRS VBC", "BC"], ["MCRS VCA", "CA"],
    ]);

    // Plot KPDN1's set: legend/trace names rich, identity in meta/uid.
    await plotAll.click();
    await page.locator("#mainNavWaveformBtn").click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    await expect.poll(async () => page.evaluate(() => ww.panels.flatMap((panel) =>
      ((panel.chartEl && panel.chartEl.data) || []).map((t) => t.name)).filter((n) => /^KPDN1 /.test(n || "")).sort()))
      .toEqual(["KPDN1 V<sub>BR</sub>", "KPDN1 V<sub>RY</sub>", "KPDN1 V<sub>YB</sub>"]);
    await expect(subs(page.locator('#calculatedChannelsSidebarBody tr[data-channel-name="KPDN1 VYB"] .channel-name-text'))).toHaveText(["YB"]);
  });

  test("ambiguous lone VB bay: no guess, canonical fallback, source name verbatim", async ({ page }) => {
    await uploadFixture(page);
    await openLineToLineBuilder(page);
    await selectBay(page, "AMBG");
    const status = page.locator("#wwCcLlStatus");
    await expect(status).toHaveAttribute("data-phase-convention", "");
    await expect(subs(status)).toHaveText(["A", "B", "C"]); // canonical, NOT R/Y/B
    await expect(subs(page.locator("label:has(#wwCcLlOutput_AB)"))).toHaveText(["AB"]);
    // AMBG_VB exists but its phase is unresolved -- reported, never assigned.
    await expect(status.locator('li[data-ll-role="Vb"]')).toHaveAttribute("data-ll-role-status", "phase_identity_missing");
    await expect(status.locator('li[data-ll-role="Vc"]')).toHaveAttribute("data-ll-role-status", "phase_identity_missing");
  });

  test("source channel names stay exactly as supplied in the Waveform sidebar", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    const rows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
    await expect(rows.first()).toBeVisible();
    for (const name of ["KPDN1_VR", "KPDN1_VY", "KPDN1_VB", "MCRS_VA", "MCRS_VB", "MCRS_VC", "AMBG_VB"]) {
      await expect(rows.filter({ hasText: name }).locator("td").first()).toContainText(name);
    }
    await expect(page.locator("#channelGroups .ww-electrical-symbol")).toHaveCount(0);
  });

  test("Analysis: Phasor values/diagram and Related Waveforms follow the selected bay", async ({ page }) => {
    await uploadFixture(page);
    const contexts = await contextsByName(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#pageAnalysis")).toBeVisible();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();

    for (const [bay, conv] of [["KPDN1", RYB], ["MCRS", ABC]]) {
      await ensureContextSelected(page, page.locator("#wwPhasorContextSelect"), contexts[bay].id);
      await expect(async () => {
        const text = await page.locator("#wwPhasorValuesList").innerText();
        expect(text).toMatch(/\d+\.\d\s*kV/);
      }).toPass({ timeout: 10000 });
      const voltageRows = ["Va", "Vb", "Vc"].map((k) => page.locator(`#wwPhasorValuesList .ww-phasor-value-row[data-role="${k}"]`));
      for (const [i, row] of voltageRows.entries()) {
        await expect(row.locator(".ww-phasor-role-label .ww-electrical-sub")).toHaveText(conv.phases[i]);
        await expect(row).toHaveAttribute("aria-label", `Hide ${conv.names[i]} vector`); // plain fallback
      }
      await expectTrueSubscripts(page.locator("#wwPhasorValuesList .ww-electrical-symbol"), 3);
      // Diagram vector labels: lowered tspan, same spelling; currents plain.
      await expect(page.locator("#wwPhasorSvg text.ww-phasor-vector-label tspan")).toHaveText(conv.phases);
      await expect(page.locator("#wwPhasorSvg text.ww-phasor-vector-label")).toHaveText([...conv.names, "Ia", "Ib", "Ic"]);
      // Related Waveforms: display names follow the bay; identity is meta.
      await expect.poll(async () => page.evaluate(() => {
        const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
        return v && v.data ? v.data.map((t) => [t.meta, t.name]) : [];
      })).toEqual(["Va", "Vb", "Vc"].map((k, i) => [k, `V<sub>${conv.phases[i]}</sub>`]));
    }
  });

  test("Analysis: Sequence phase-domain inputs follow the bay; sequence symbols never do", async ({ page }) => {
    await uploadFixture(page);
    const contexts = await contextsByName(page);
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeSequenceBtn").click();
    await expect(page.locator("#wwSequencePanel")).toBeVisible();
    await ensureContextSelected(page, page.locator("#wwSequenceContextSelect"), contexts.KPDN1.id);
    await expect.poll(async () => page.evaluate(() => {
      const v = document.getElementById("wwAnalysisRelatedWaveformsVoltageChart");
      return v && v.data ? v.data.map((t) => [t.meta, t.name]) : [];
    })).toEqual([["Va", "V<sub>R</sub>"], ["Vb", "V<sub>Y</sub>"], ["Vc", "V<sub>B</sub>"]]);
    await expect(page.locator("#wwSequenceValuesList .ww-phasor-role-label")).toHaveText(["V1", "V2", "V0", "I1", "I2", "I0"]);
    // Manual input has no bay: its static labels stay canonical.
    await expect(page.locator(".ww-phasor-manual-role-row:has(#wwSequenceManualVaEnabled) .ww-electrical-sub")).toHaveText("A");
  });

  test("Compliance: generic quantity wording, resolved measurement in the group's convention", async ({ page }) => {
    await uploadFixture(page);
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#pageCompliance")).toBeVisible();
    await expect(page.locator("#wwComplianceGroupField")).toBeVisible();
    const input = page.locator("#wwComplianceMeasurementInput");

    const groupLabel = async (prefix) => (await page.locator("#wwComplianceGroupSelect option").allTextContents())
      .find((t) => t.startsWith(prefix));

    await page.locator("#wwComplianceGroupSelect").selectOption({ label: await groupLabel("KPDN1") });
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Phase A Voltage" }); // generic, fixed
    await expect(input).toHaveText("VR — KPDN1_VR");
    await expect(input).toHaveAttribute("data-phase-convention", "RYB");
    await expectTrueSubscripts(input.locator(".ww-electrical-symbol"), 1);
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Line-Line AB Voltage" });
    await expect(input).toHaveText("VR — KPDN1_VR, VY — KPDN1_VY");
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Phase C Voltage" });
    await expect(input).toHaveText("VB — KPDN1_VB"); // canonical C of an R/Y/B group

    await page.locator("#wwComplianceGroupSelect").selectOption({ label: await groupLabel("MCRS") });
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Phase A Voltage" });
    await expect(input).toHaveText("VA — MCRS_VA");
    await expect(input).toHaveAttribute("data-phase-convention", "ABC");
    await page.locator("#wwComplianceMeasurementSelect").selectOption({ label: "Phase C Voltage" });
    await expect(input).toHaveText("VC — MCRS_VC");
    await expect(page.locator("#wwComplianceMeasurementSelect option:checked")).toHaveText("Phase C Voltage");
  });
});
