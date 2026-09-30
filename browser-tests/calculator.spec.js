const { test, expect } = require("@playwright/test");

function polarToComplex(magnitude, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { re: magnitude * Math.cos(rad), im: magnitude * Math.sin(rad) };
}

function normalizeAngleDeg(angle) {
  let normalized = ((((angle + 180) % 360) + 360) % 360) - 180;
  if (normalized <= -180) normalized += 360;
  return normalized;
}

function subtractPolar(aMag, aAngle, bMag, bAngle) {
  const a = polarToComplex(aMag, aAngle);
  const b = polarToComplex(bMag, bAngle);
  const re = a.re - b.re;
  const im = a.im - b.im;
  const magnitude = Math.hypot(re, im);
  const angle = magnitude < 1e-12 ? 0 : normalizeAngleDeg((Math.atan2(im, re) * 180) / Math.PI);
  return { magnitude, angle };
}

async function numericText(locator) {
  const text = await locator.textContent();
  return Number((text || "").match(/-?\d+(?:\.\d+)?/)?.[0]);
}

test("Calculator is a first-class page accessible without an event recording", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  const backendPort = process.env.PW_BACKEND_PORT || "8000";
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${backendPort}", environment: "test", buildVersion: "calculator-test" };`,
    })
  );

  await page.goto("/index.html");
  await expect(page.locator("#pageRecordings")).toBeVisible();
  await expect(page.locator("#recordingsTableBody tr[data-source-id]")).toHaveCount(0);

  const complianceNav = page.locator("#mainNavComplianceBtn");
  const calculatorNav = page.locator("#mainNavCalculatorBtn");
  await expect(complianceNav).toBeVisible();
  await expect(calculatorNav).toBeVisible();

  const navOrder = await page.locator("#mainSidebarMenu .shell-nav-list .shell-nav-item").evaluateAll((items) =>
    items.map((item) => item.id)
  );
  expect(navOrder).toEqual([
    "mainNavRecordingsBtn",
    "mainNavWaveformBtn",
    "mainNavTableBtn",
    "mainNavCalculatedChannelsBtn",
    "mainNavAnalysisBtn",
    "mainNavComplianceBtn",
    "mainNavCalculatorBtn",
  ]);

  const analysisNav = page.locator("#mainNavAnalysisBtn");
  await analysisNav.click();
  await expect(page.locator("#pageAnalysis")).toBeVisible();
  const analysisNavStyle = await page.locator("#pageAnalysis .ww-analysis-type-nav").evaluate((el) => {
    const row = el.querySelector(".ww-analysis-type-item.active");
    const icon = el.querySelector(".ww-analysis-type-icon");
    const navStyle = getComputedStyle(el);
    const rowStyle = getComputedStyle(row);
    const iconStyle = getComputedStyle(icon);
    return {
      navWidth: Math.round(el.getBoundingClientRect().width),
      navPadding: navStyle.padding,
      rowMinHeight: rowStyle.minHeight,
      rowPadding: rowStyle.padding,
      rowFontSize: rowStyle.fontSize,
      rowBorderLeftWidth: rowStyle.borderLeftWidth,
      rowBorderLeftColor: rowStyle.borderLeftColor,
      iconWidth: iconStyle.width,
      iconHeight: iconStyle.height,
    };
  });

  await calculatorNav.click();
  await expect(page.locator("#pageCalculator")).toBeVisible();
  await expect(page.locator("#pageCalculator h2")).toHaveText("Calculator");
  await expect(page.locator("#pageCalculator")).toContainText(
    "Quick electrical engineering calculations without requiring an event recording."
  );
  await expect(page.locator("#wwCalcToolLinePhaseBtn")).toBeVisible();
  await expect(page.locator("#wwCalcToolLinePhaseBtn")).toHaveAttribute("aria-current", "true");
  await expect(page.locator("#wwCalcToolLinePhase")).toBeVisible();
  const calculatorNavStyle = await page.locator("#pageCalculator .ww-calculator-tool-nav").evaluate((el) => {
    const row = el.querySelector("#wwCalcToolLinePhaseBtn");
    const icon = el.querySelector(".ww-analysis-type-icon");
    const navStyle = getComputedStyle(el);
    const rowStyle = getComputedStyle(row);
    const iconStyle = getComputedStyle(icon);
    return {
      navWidth: Math.round(el.getBoundingClientRect().width),
      navPadding: navStyle.padding,
      rowMinHeight: rowStyle.minHeight,
      rowPadding: rowStyle.padding,
      rowFontSize: rowStyle.fontSize,
      rowBorderLeftWidth: rowStyle.borderLeftWidth,
      rowBorderLeftColor: rowStyle.borderLeftColor,
      iconWidth: iconStyle.width,
      iconHeight: iconStyle.height,
    };
  });
  expect(calculatorNavStyle).toEqual(analysisNavStyle);
  await expect(page.locator("#wwCalcBalancedPanel .ww-calculator-balanced-top")).toBeVisible();
  await expect(page.locator("#wwCalcBalancedPanel .ww-calculator-support-grid")).toBeVisible();
  await expect(calculatorNav).toHaveAttribute("aria-current", "page");
  await expect(complianceNav).not.toHaveAttribute("aria-current", "page");

  async function expectNoHorizontalOverflow() {
    const overflow = await page.locator("#pageCalculator").evaluate((el) => ({
      page: el.scrollWidth - el.clientWidth,
      body: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    }));
    expect(overflow.page).toBeLessThanOrEqual(1);
    expect(overflow.body).toBeLessThanOrEqual(1);
  }

  await page.setViewportSize({ width: 1366, height: 768 });
  await expectNoHorizontalOverflow();

  await expect(page.locator("#wwCalcBalancedPanel")).toBeVisible();
  await expect(page.locator("#wwCalcBalancedResultValue")).toHaveText("275.00 kV");
  await expect(page.locator("#wwCalcBalancedFormula")).toContainText("√3 × 158.77 kV");
  await expect(page.locator("#wwCalcBalancedFormula")).toContainText("275.00 kV");

  await page.locator("#wwCalcBalancedDirection").selectOption("ll_to_ln");
  await page.locator("#wwCalcBalancedMagnitude").fill("275");
  await expect(page.locator("#wwCalcBalancedResultValue")).toHaveText("158.77 kV");
  await expect(page.locator("#wwCalcBalancedFormula")).toContainText("275.00 kV / √3");

  await page.locator("#wwCalcBalancedUnit").selectOption("V");
  await expect(page.locator("#wwCalcBalancedResultValue")).toHaveText("158.77 V");

  await page.locator("#wwCalcBalancedMagnitude").fill("");
  await expect(page.locator("#wwCalcBalancedResultValue")).toHaveText("--");
  await expect(page.locator("#pageCalculator")).not.toContainText(/NaN|Infinity/);

  await page.locator("#wwCalcBalancedMagnitude").fill("158.77");
  await page.locator("#wwCalcBalancedDirection").selectOption("ln_to_ll");
  await page.locator("#wwCalcBalancedUnit").selectOption("kV");
  await expect(page.locator("#wwCalcBalancedResultValue")).toHaveText("275.00 kV");

  await page.locator("#wwCalcModeIndividualBtn").click();
  await expect(page.locator("#wwCalcIndividualPanel")).toBeVisible();
  await expect(page.locator("#wwCalcModeIndividualBtn")).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#wwCalcIndividualPanel .ww-calculator-individual-top")).toBeVisible();
  await expect(page.locator("#wwCalcIndividualPanel .ww-calculator-support-grid")).toBeVisible();
  await expect(page.locator("#wwCalcIndividualFormula")).toContainText("VRY = VR − VY");
  await expect(page.locator("#wwCalcIndividualFormula")).toContainText("V = |V|(cos θ + j sin θ)");

  const expectedBalanced = Math.sqrt(3) * 158.77;
  expect(await numericText(page.locator("#wwCalcResultRYMag"))).toBeCloseTo(expectedBalanced, 2);
  expect(await numericText(page.locator("#wwCalcResultYBMag"))).toBeCloseTo(expectedBalanced, 2);
  expect(await numericText(page.locator("#wwCalcResultBRMag"))).toBeCloseTo(expectedBalanced, 2);
  expect(await numericText(page.locator("#wwCalcResultRYAngle"))).toBeCloseTo(30, 2);
  expect(await numericText(page.locator("#wwCalcResultYBAngle"))).toBeCloseTo(-90, 2);
  expect(await numericText(page.locator("#wwCalcResultBRAngle"))).toBeCloseTo(150, 2);

  const yVectorBefore = await page.locator("#wwCalcIndividualDiagram .ww-calc-phase-vector-y").getAttribute("y2");
  await page.locator("#wwCalcMagY").fill("140");
  await page.locator("#wwCalcAngleY").fill("-105");
  const yVectorAfter = await page.locator("#wwCalcIndividualDiagram .ww-calc-phase-vector-y").getAttribute("y2");
  expect(yVectorAfter).not.toBe(yVectorBefore);

  const expectedRY = subtractPolar(158.77, 0, 140, -105);
  const expectedYB = subtractPolar(140, -105, 158.77, 120);
  const expectedBR = subtractPolar(158.77, 120, 158.77, 0);
  expect(await numericText(page.locator("#wwCalcResultRYMag"))).toBeCloseTo(expectedRY.magnitude, 2);
  expect(await numericText(page.locator("#wwCalcResultRYAngle"))).toBeCloseTo(expectedRY.angle, 2);
  expect(await numericText(page.locator("#wwCalcResultYBMag"))).toBeCloseTo(expectedYB.magnitude, 2);
  expect(await numericText(page.locator("#wwCalcResultYBAngle"))).toBeCloseTo(expectedYB.angle, 2);
  expect(await numericText(page.locator("#wwCalcResultBRMag"))).toBeCloseTo(expectedBR.magnitude, 2);
  expect(await numericText(page.locator("#wwCalcResultBRAngle"))).toBeCloseTo(expectedBR.angle, 2);

  await page.locator("#wwCalcMagR").fill("0");
  await expect(page.locator("#wwCalcResultBRMag")).toContainText("158.77");
  await page.locator("#wwCalcAngleB").fill("765");
  await expect(page.locator("#pageCalculator")).not.toContainText(/NaN|Infinity/);

  await page.locator("#wwCalcMagB").fill("");
  await expect(page.locator("#wwCalcResultRYMag")).toHaveText("--");
  await expect(page.locator("#pageCalculator")).not.toContainText(/NaN|Infinity/);

  await page.setViewportSize({ width: 820, height: 760 });
  await expect(page.locator("#wwCalcToolLinePhaseBtn")).toBeVisible();
  await expectNoHorizontalOverflow();

  await page.setViewportSize({ width: 390, height: 760 });
  await expect(page.locator("#wwCalcIndividualPanel")).toBeVisible();
  await expect(page.locator("#wwCalcIndividualDiagram svg")).toBeVisible();
  await expectNoHorizontalOverflow();

  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#workspaceRow")).toBeVisible();
  await expect(page.locator("#mainNavWaveformBtn")).toHaveAttribute("aria-current", "page");
  await expect(calculatorNav).not.toHaveAttribute("aria-current", "page");

  expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
});
