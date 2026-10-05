// Calculator -- Power & Current (Current / P-Q-S / Power Factor tabs).
// Frontend-local calculator: no recording and no backend calls are needed.

const { test, expect } = require("@playwright/test");

const { expectTrueSubscripts } = require("./support/electrical_notation_helpers");

const BODY = { pqs: "wwPqsResultBody", pf: "wwPfResultBody" };

async function openPowerCurrent(page) {
  const backendPort = process.env.PW_BACKEND_PORT || "8000";
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${backendPort}", environment: "test", buildVersion: "calculator-pc-test" };`,
    })
  );
  await page.goto("/index.html");
  await page.locator("#mainNavCalculatorBtn").click();
  await expect(page.locator("#pageCalculator")).toBeVisible();
  await page.locator("#wwCalcToolPowerCurrentBtn").click();
  await expect(page.locator("#wwCalcToolPowerCurrent")).toBeVisible();
}

async function openTab(page, tab) {
  const ids = { current: "wwPcTabCurrentBtn", pqs: "wwPcTabPqsBtn", pf: "wwPcTabPfBtn" };
  await page.locator(`#${ids[tab]}`).click();
  await expect(page.locator(`#${ids[tab]}`)).toHaveAttribute("aria-selected", "true");
}

async function set(page, id, value) {
  await page.locator(`#${id}`).fill(String(value));
}

function cell(page, tab, key, part) {
  return page.locator(`#${BODY[tab]} tr[data-pc-row="${key}"] td.ww-pc-${part}`);
}

async function expectNoNaN(page) {
  await expect(page.locator("#pageCalculator")).not.toContainText(/NaN|Infinity/);
}

function luminance(rgb) {
  const [r, g, b] = rgb.match(/[\d.]+/g).slice(0, 3).map(Number).map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test.describe("Calculator -- Power & Current: navigation and shell", () => {
  test("Power & Current sits directly below Line / Phase Voltage and opens its own panel", async ({ page }) => {
    await openPowerCurrent(page);
    const labels = await page.locator("#pageCalculator .ww-calculator-tool-nav .ww-analysis-type-item .ww-analysis-type-label").allTextContents();
    expect(labels).toEqual(["Line / Phase Voltage", "Power & Current"]);
    await expect(page.locator("#wwCalcToolPowerCurrentBtn")).toHaveAttribute("aria-current", "true");
    await expect(page.locator("#wwCalcToolLinePhaseBtn")).toHaveAttribute("aria-current", "false");
    await expect(page.locator("#wwCalcToolLinePhase")).toBeHidden();
    await expect(page.locator("#wwCalcToolPowerCurrent h3")).toHaveText("Power & Current");
    await expect(page.locator("#wwCalcToolPowerCurrent .ww-calculator-intro")).toHaveText(
      "Power, current, and power-factor calculations for common electrical engineering use cases."
    );
    const tabs = await page.locator("#wwPcTabList [role=tab]").allTextContents();
    expect(tabs).toEqual(["Current", "P-Q-S", "Power Factor"]);
  });

  test("the owner power-triangle icon renders through the registry mask", async ({ page }) => {
    await openPowerCurrent(page);
    const icon = page.locator("#wwCalcToolPowerCurrentBtn .ww-analysis-type-icon");
    const info = await icon.evaluate((el) => {
      const cs = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return { mask: cs.maskImage || cs.webkitMaskImage, w: box.width, h: box.height, ownIcon: el.dataset.wwIcon };
    });
    expect(info.ownIcon).toBe("CALCULATOR_POWER_CURRENT");
    expect(info.mask).toContain("calculator/amparent_square.svg");
    expect(info.w).toBeGreaterThan(8);
    expect(info.h).toBeGreaterThan(8);
    const response = await page.request.get(new URL("/assets/icons/calculator/amparent_square.svg", page.url()).toString());
    expect(response.status()).toBe(200);
  });

  test("Line / Phase Voltage is unchanged after visiting Power & Current", async ({ page }) => {
    await openPowerCurrent(page);
    await page.locator("#wwCalcToolLinePhaseBtn").click();
    await expect(page.locator("#wwCalcToolLinePhase")).toBeVisible();
    await expect(page.locator("#wwCalcToolPowerCurrent")).toBeHidden();
    await expect(page.locator("#wwCalcToolLinePhaseBtn")).toHaveAttribute("aria-current", "true");
    await expect(page.locator("#wwCalcBalancedResultValue")).toContainText("275.00 kV");
    await page.locator("#wwCalcModeIndividualBtn").click();
    await expect(page.locator("#wwCalcIndividualPanel")).toBeVisible();
    await expect(page.locator("#wwCalcBalancedPanel")).toBeHidden();
  });
});

test.describe("Calculator -- Power & Current: Current tab", () => {
  test("defaults reproduce the reference example: 100 MVA at 132 kV 3-phase L-L = 437.4 A", async ({ page }) => {
    await openPowerCurrent(page);
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Line current (3-phase L-L)");
    const lines = await page.locator("#wwPcCurrentFormula .ww-calculator-formula-line").allTextContents();
    expect(lines).toEqual(["I = S / (√3 × VLL)", "= 100 MVA / (√3 × 132 kV)", "= 437.4 A"]);
  });

  test("single-phase: I = S / V", async ({ page }) => {
    await openPowerCurrent(page);
    await page.locator("#wwPcSystemSingleBtn").click();
    await expect(page.locator("#wwPcSystemSingleBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwPcSystemThreeBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("757.6 A");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Current (single-phase)");
    await expect(page.locator("#wwPcVoltageLabel")).toHaveText("Voltage (V)");
    const lines = await page.locator("#wwPcCurrentFormula .ww-calculator-formula-line").allTextContents();
    expect(lines).toEqual(["I = S / V", "= 100 MVA / 132 kV", "= 757.6 A"]);
    await set(page, "wwPcVoltage", "230");
    await page.locator("#wwPcVoltageUnit").selectOption("V");
    await set(page, "wwPcCurrentS", "5");
    await page.locator("#wwPcCurrentSUnit").selectOption("kVA");
    // 5 kVA / 230 V = 21.739 A
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("21.74 A");
  });

  test("three-phase L-L: I = S / (sqrt(3) x V_LL)", async ({ page }) => {
    await openPowerCurrent(page);
    await set(page, "wwPcVoltage", "33");
    await set(page, "wwPcCurrentS", "50");
    // 50e6 / (sqrt(3) * 33e3) = 874.77 A
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("874.8 A");
  });

  test("V / kV and VA / kVA / MVA conversions give the same current", async ({ page }) => {
    await openPowerCurrent(page);
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
    await set(page, "wwPcVoltage", "132000");
    await page.locator("#wwPcVoltageUnit").selectOption("V");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
    await set(page, "wwPcCurrentS", "100000");
    await page.locator("#wwPcCurrentSUnit").selectOption("kVA");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
    await set(page, "wwPcCurrentS", "100000000");
    await page.locator("#wwPcCurrentSUnit").selectOption("VA");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
  });

  test("empty, zero and negative inputs never produce NaN/Infinity or throw", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await openPowerCurrent(page);
    await set(page, "wwPcVoltage", "");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("--");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Enter voltage and apparent power.");
    await expect(page.locator("#wwPcCurrentNote")).not.toHaveClass(/ww-calculator-message--error/);
    await set(page, "wwPcVoltage", "0");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("--");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Voltage must be greater than zero.");
    await expect(page.locator("#wwPcCurrentNote")).toHaveClass(/ww-calculator-message--error/);
    await set(page, "wwPcVoltage", "132");
    await set(page, "wwPcCurrentS", "-5");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("--");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Apparent power cannot be negative.");
    await set(page, "wwPcCurrentS", "0");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("0 A");
    await set(page, "wwPcCurrentS", "1e308");
    await page.locator("#wwPcCurrentSUnit").selectOption("MVA");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("--");
    // A half-typed number ("1e") leaves the field with badInput and no value.
    await set(page, "wwPcCurrentS", "");
    await page.locator("#wwPcCurrentS").pressSequentially("1e");
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("--");
    await expect(page.locator("#wwPcCurrentNote")).toHaveText("Enter valid numbers.");
    await expect(page.locator("#wwPcCurrentNote")).toHaveClass(/ww-calculator-message--error/);
    await expectNoNaN(page);
    expect(errors).toEqual([]);
  });
});

test.describe("Calculator -- Power & Current: P-Q-S tab", () => {
  test("P + Q -> S, with PF", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await expect(cell(page, "pqs", "S", "value")).toHaveText("100 MVA");
    await expect(cell(page, "pqs", "S", "source")).toHaveText("Calculated");
    await expect(cell(page, "pqs", "P", "source")).toHaveText("Input");
    await expect(cell(page, "pqs", "Q", "source")).toHaveText("Input");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("0.800");
    const lines = await page.locator("#wwPqsFormula .ww-calculator-formula-line").allTextContents();
    expect(lines[0]).toBe("S = √(P² + Q²)");
    expect(lines[2]).toBe("= 100 MVA");
    expect(lines[3]).toBe("PF = |P| / S = 80 MW / 100 MVA = 0.800");
  });

  test("P + S -> |Q| (magnitude) and PF", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsQ", "");
    await set(page, "wwPqsS", "100");
    await expect(cell(page, "pqs", "Q", "value")).toHaveText("60 MVAr");
    await expect(cell(page, "pqs", "Q", "source")).toHaveText("Calculated (magnitude)");
    await expect(page.locator('#wwPqsResultBody tr[data-pc-row="Q"] td').first()).toHaveText("Reactive Power |Q|");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("0.800");
  });

  test("Q + S -> |P| and PF", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsP", "");
    await set(page, "wwPqsS", "100");
    await expect(cell(page, "pqs", "P", "value")).toHaveText("80 MW");
    await expect(cell(page, "pqs", "P", "source")).toHaveText("Calculated (magnitude)");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("0.800");
  });

  test("units are normalised: 80000 kW + 60000000 var gives the same S", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsP", "80000");
    await page.locator("#wwPqsPUnit").selectOption("kW");
    await set(page, "wwPqsQ", "60000000");
    await page.locator("#wwPqsQUnit").selectOption("var");
    await page.locator("#wwPqsSUnit").selectOption("kVA");
    await expect(cell(page, "pqs", "S", "value")).toHaveText("100000 kVA");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("0.800");
  });

  test("|P| > S and |Q| > S are rejected", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsQ", "");
    await set(page, "wwPqsP", "100");
    await set(page, "wwPqsS", "80");
    await expect(page.locator("#wwPqsNote")).toHaveText("|P| cannot be greater than S.");
    await expect(page.locator("#wwPqsNote")).toHaveClass(/ww-calculator-message--error/);
    await expect(cell(page, "pqs", "Q", "value")).toHaveText("--");
    await set(page, "wwPqsP", "");
    await set(page, "wwPqsQ", "100");
    await expect(page.locator("#wwPqsNote")).toHaveText("|Q| cannot be greater than S.");
    await expect(cell(page, "pqs", "P", "value")).toHaveText("--");
    await expectNoNaN(page);
  });

  test("negative S, and a negative P or Q that is within S, behave correctly", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsS", "-100");
    await set(page, "wwPqsQ", "");
    await expect(page.locator("#wwPqsNote")).toHaveText("Apparent power cannot be negative.");
    await set(page, "wwPqsS", "100");
    await set(page, "wwPqsP", "-80");
    await expect(cell(page, "pqs", "Q", "value")).toHaveText("60 MVAr");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("0.800");
  });

  test("incomplete input is neutral; all three entered asks for one to be cleared and overwrites nothing", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsQ", "");
    await expect(page.locator("#wwPqsNote")).toHaveText("Enter any two of P, Q and S.");
    await expect(page.locator("#wwPqsNote")).not.toHaveClass(/ww-calculator-message--error/);
    await set(page, "wwPqsQ", "60");
    await set(page, "wwPqsS", "90");
    await expect(page.locator("#wwPqsNote")).toHaveText("P, Q and S are all entered. Clear one field to calculate it.");
    await expect(page.locator("#wwPqsP")).toHaveValue("80");
    await expect(page.locator("#wwPqsQ")).toHaveValue("60");
    await expect(page.locator("#wwPqsS")).toHaveValue("90");
  });

  test("a calculated field is tagged and shown as a placeholder, never written into the input", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await expect(page.locator("#wwPqsSTag")).toBeVisible();
    await expect(page.locator("#wwPqsPTag")).toBeHidden();
    await expect(page.locator("#wwPqsS")).toHaveValue("");
    await expect(page.locator("#wwPqsS")).toHaveAttribute("placeholder", "100");
    await expect(page.locator("#wwPqsS")).toHaveClass(/ww-calculator-field--derived/);
    await set(page, "wwPqsS", "100");
    await set(page, "wwPqsQ", "");
    await expect(page.locator("#wwPqsS")).toHaveValue("100");
    await expect(page.locator("#wwPqsSTag")).toBeHidden();
    await expect(page.locator("#wwPqsQTag")).toBeVisible();
    await expect(page.locator("#wwPqsQ")).toHaveValue("");
  });

  test("S = 0 is handled: Q = 0 and PF is undefined, not NaN", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pqs");
    await set(page, "wwPqsP", "0");
    await set(page, "wwPqsQ", "");
    await set(page, "wwPqsS", "0");
    await expect(cell(page, "pqs", "Q", "value")).toHaveText("0 MVAr");
    await expect(cell(page, "pqs", "PF", "value")).toHaveText("--");
    await expect(page.locator("#wwPqsNote")).toHaveText("PF is undefined when S = 0.");
    await expectNoNaN(page);
  });
});

test.describe("Calculator -- Power & Current: Power Factor tab", () => {
  test("S + PF -> P and Q (lagging: Q positive)", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await expect(cell(page, "pf", "P", "value")).toHaveText("80 MW");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("+60 MVAr");
    await expect(cell(page, "pf", "S", "value")).toHaveText("100 MVA");
    await expect(cell(page, "pf", "P", "source")).toHaveText("Calculated");
    await expect(cell(page, "pf", "Q", "source")).toHaveText("Calculated");
    await expect(cell(page, "pf", "S", "source")).toHaveText("Input");
    await expect(cell(page, "pf", "PF", "value")).toHaveText("0.800 lagging");
  });

  test("P + PF -> S and Q", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfS", "");
    await set(page, "wwPfP", "80");
    await expect(cell(page, "pf", "S", "value")).toHaveText("100 MVA");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("+60 MVAr");
    await expect(cell(page, "pf", "S", "source")).toHaveText("Calculated");
    const lines = await page.locator("#wwPfFormula .ww-calculator-formula-line").allTextContents();
    expect(lines).toContain("|Q| = |P| × tan(arccos(PF))");
  });

  test("Q + PF -> S and P", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfS", "");
    await set(page, "wwPfQ", "60");
    await expect(cell(page, "pf", "S", "value")).toHaveText("100 MVA");
    await expect(cell(page, "pf", "P", "value")).toHaveText("80 MW");
    await expect(page.locator("#wwPfNote")).toHaveText("");
  });

  test("leading / capacitive gives negative Q; lagging gives positive Q", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await page.locator("#wwPfLeadingBtn").click();
    await expect(page.locator("#wwPfLeadingBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwPfLaggingBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("-60 MVAr");
    await expect(cell(page, "pf", "PF", "value")).toHaveText("0.800 leading");
    await page.locator("#wwPfLaggingBtn").click();
    await expect(cell(page, "pf", "Q", "value")).toHaveText("+60 MVAr");
  });

  test("an entered Q whose sign disagrees with the PF type is flagged, not silently flipped", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfS", "");
    await set(page, "wwPfQ", "-60");
    await expect(page.locator("#wwPfNote")).toContainText("Entered Q is negative but the PF type is lagging");
    await expect(page.locator("#wwPfQ")).toHaveValue("-60");
    await expect(cell(page, "pf", "S", "value")).toHaveText("100 MVA");
  });

  test("PF = 1 gives Q = 0 explicitly", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfValue", "1");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("0 MVAr");
    await expect(cell(page, "pf", "P", "value")).toHaveText("100 MW");
    await page.locator("#wwPfLeadingBtn").click();
    await expect(cell(page, "pf", "Q", "value")).toHaveText("0 MVAr");
    await set(page, "wwPfS", "");
    await set(page, "wwPfQ", "5");
    await expect(page.locator("#wwPfNote")).toHaveText("At PF = 1, Q must be zero.");
    await set(page, "wwPfQ", "0");
    await expect(page.locator("#wwPfNote")).toHaveText("At PF = 1 and Q = 0, S cannot be found from Q. Enter P or S.");
    await set(page, "wwPfQ", "");
    await set(page, "wwPfP", "80");
    await expect(cell(page, "pf", "S", "value")).toHaveText("80 MVA");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("0 MVAr");
  });

  test("invalid power factor is rejected; blank is neutral", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    for (const bad of ["0", "-0.5", "1.2", "2"]) {
      await set(page, "wwPfValue", bad);
      await expect(page.locator("#wwPfNote")).toHaveText("Power factor must be greater than 0 and no more than 1.");
      await expect(page.locator("#wwPfNote")).toHaveClass(/ww-calculator-message--error/);
      await expect(cell(page, "pf", "P", "value")).toHaveText("--");
    }
    await set(page, "wwPfValue", "");
    await expect(page.locator("#wwPfNote")).toHaveText("Enter the power factor and one of P, Q or S.");
    await expect(page.locator("#wwPfNote")).not.toHaveClass(/ww-calculator-message--error/);
    await expectNoNaN(page);
  });

  test("more than one power quantity is ambiguous and asks to clear the others", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfP", "80");
    await expect(page.locator("#wwPfNote")).toHaveText("Enter the power factor and only one of P, Q or S. Clear the others.");
    await expect(page.locator("#wwPfS")).toHaveValue("100");
    await expect(page.locator("#wwPfP")).toHaveValue("80");
  });

  test("a small PF stays finite", async ({ page }) => {
    await openPowerCurrent(page);
    await openTab(page, "pf");
    await set(page, "wwPfValue", "0.01");
    await expect(cell(page, "pf", "P", "value")).toHaveText("1 MW");
    await expect(cell(page, "pf", "Q", "value")).toHaveText("+99.99 MVAr");
    await expectNoNaN(page);
  });
});

test.describe("Calculator -- Power & Current: tabs, state, accessibility, themes", () => {
  test("internal tabs switch, expose ARIA state and support the arrow / Home / End keys", async ({ page }) => {
    await openPowerCurrent(page);
    await expect(page.locator("#wwPcCurrentPanel")).toBeVisible();
    await expect(page.locator("#wwPcPqsPanel")).toBeHidden();
    await expect(page.locator("#wwPcPfPanel")).toBeHidden();
    await page.locator("#wwPcTabPqsBtn").click();
    await expect(page.locator("#wwPcPqsPanel")).toBeVisible();
    await expect(page.locator("#wwPcCurrentPanel")).toBeHidden();
    await expect(page.locator("#wwPcTabPqsBtn")).toHaveClass(/ww-oc-axis-toggle-btn--active/);
    await expect(page.locator("#wwPcTabCurrentBtn")).not.toHaveClass(/ww-oc-axis-toggle-btn--active/);
    await page.locator("#wwPcTabPqsBtn").focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#wwPcPfPanel")).toBeVisible();
    await expect(page.locator("#wwPcTabPfBtn")).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#wwPcCurrentPanel")).toBeVisible();
    await page.keyboard.press("End");
    await expect(page.locator("#wwPcPfPanel")).toBeVisible();
    await page.keyboard.press("Home");
    await expect(page.locator("#wwPcCurrentPanel")).toBeVisible();
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("#wwPcPfPanel")).toBeVisible();
    for (const [btn, panel] of [["wwPcTabCurrentBtn", "wwPcCurrentPanel"], ["wwPcTabPqsBtn", "wwPcPqsPanel"], ["wwPcTabPfBtn", "wwPcPfPanel"]]) {
      await expect(page.locator(`#${btn}`)).toHaveAttribute("aria-controls", panel);
      await expect(page.locator(`#${panel}`)).toHaveAttribute("aria-labelledby", btn);
    }
  });

  test("entered values and toggles are kept when switching tabs and tools", async ({ page }) => {
    await openPowerCurrent(page);
    await page.locator("#wwPcSystemSingleBtn").click();
    await set(page, "wwPcVoltage", "11");
    await set(page, "wwPcCurrentS", "7.5");
    await page.locator("#wwPcCurrentSUnit").selectOption("kVA");
    await openTab(page, "pqs");
    await set(page, "wwPqsP", "12");
    await page.locator("#wwPqsPUnit").selectOption("kW");
    await openTab(page, "pf");
    await set(page, "wwPfValue", "0.9");
    await page.locator("#wwPfLeadingBtn").click();
    await openTab(page, "current");
    await expect(page.locator("#wwPcVoltage")).toHaveValue("11");
    await expect(page.locator("#wwPcCurrentS")).toHaveValue("7.5");
    await expect(page.locator("#wwPcCurrentSUnit")).toHaveValue("kVA");
    await expect(page.locator("#wwPcSystemSingleBtn")).toHaveAttribute("aria-pressed", "true");
    await openTab(page, "pqs");
    await expect(page.locator("#wwPqsP")).toHaveValue("12");
    await expect(page.locator("#wwPqsPUnit")).toHaveValue("kW");
    await openTab(page, "pf");
    await expect(page.locator("#wwPfValue")).toHaveValue("0.9");
    await expect(page.locator("#wwPfLeadingBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwCalcToolLinePhaseBtn").click();
    await page.locator("#wwCalcToolPowerCurrentBtn").click();
    await expect(page.locator("#wwPcPfPanel")).toBeVisible();
    await expect(page.locator("#wwPfValue")).toHaveValue("0.9");
  });

  test("V_LL uses true visual subscripts, never underscore notation", async ({ page }) => {
    await openPowerCurrent(page);
    await expectTrueSubscripts(page.locator("#wwPcVoltageLabel .ww-electrical-symbol"), 1);
    await expectTrueSubscripts(page.locator("#wwPcCurrentFormula .ww-electrical-symbol"), 1);
    await expectTrueSubscripts(page.locator("#wwCalcToolPowerCurrent .ww-calculator-assumption .ww-electrical-symbol").first());
    await expect(page.locator("#wwPcVoltageLabel")).toHaveText("Voltage (VLL)");
    await page.locator("#wwPcSystemSingleBtn").click();
    await expect(page.locator("#wwPcVoltageLabel .ww-electrical-symbol")).toHaveCount(0);
    const text = await page.locator("#wwCalcToolPowerCurrent").innerText();
    expect(text).not.toMatch(/V_LL|V_/);
  });

  test("light and dark themes keep the result, formula, notes and inputs legible", async ({ page }) => {
    await openPowerCurrent(page);
    for (const theme of ["light", "dark"]) {
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      for (const tab of ["current", "pqs", "pf"]) {
        await openTab(page, tab);
        const checks = await page.evaluate((activeTab) => {
          const panel = { current: "wwPcCurrentPanel", pqs: "wwPcPqsPanel", pf: "wwPcPfPanel" }[activeTab];
          const root = document.getElementById(panel);
          // Composite every translucent ancestor background (outermost
          // first) onto an opaque base, so a tinted card is measured as
          // actually painted.
          const measure = (el) => {
            const layers = [];
            for (let node = el; node; node = node.parentElement) {
              const m = (getComputedStyle(node).backgroundColor.match(/[\d.]+/g) || []).map(Number);
              if (m.length >= 3 && (m.length < 4 || m[3] > 0)) layers.unshift({ rgb: m.slice(0, 3), a: m.length >= 4 ? m[3] : 1 });
            }
            let base = [255, 255, 255];
            for (const layer of layers) base = base.map((c, i) => layer.rgb[i] * layer.a + c * (1 - layer.a));
            return { color: getComputedStyle(el).color, bg: "rgb(" + base.map(Math.round).join(", ") + ")" };
          };
          const targets = [
            root.querySelector(".ww-calculator-section-title"),
            root.querySelector(".ww-calculator-formula-line"),
            root.querySelector(".ww-calculator-assumption"),
            root.querySelector("input[type=number]"),
            root.querySelector(activeTab === "current" ? ".ww-calculator-result-value" : "td.ww-pc-value"),
          ];
          return targets.map(measure);
        }, tab);
        for (const { color, bg } of checks) {
          expect(contrast(color, bg), `${theme}/${tab}: ${color} on ${bg}`).toBeGreaterThan(3);
        }
      }
    }
    await expectNoNaN(page);
  });

  test("the tool does not overflow at 1366px and 1024px, or at phone width", async ({ page }) => {
    await openPowerCurrent(page);
    for (const width of [1366, 1024, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const tab of ["current", "pqs", "pf"]) {
        await openTab(page, tab);
        const overflow = await page.locator("#pageCalculator").evaluate((el) => el.scrollWidth - el.clientWidth);
        expect(overflow, `${width}px ${tab}`).toBeLessThanOrEqual(1);
      }
    }
  });

  test("validation errors are visibly red and the Q-sign note is a distinct warning, in both themes", async ({ page }) => {
    await openPowerCurrent(page);
    const colour = (loc) => loc.evaluate((el) => getComputedStyle(el).color.match(/[\d.]+/g).slice(0, 3).map(Number));
    const isReddish = ([r, g, b]) => r > 150 && r > g + 60 && r > b + 60;
    const isAmber = ([r, g, b]) => r > 150 && g > 90 && r > b + 60 && g < r;
    for (const theme of ["light", "dark"]) {
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      await openTab(page, "current");
      await set(page, "wwPcVoltage", "0");
      const errorColour = await colour(page.locator("#wwPcCurrentNote"));
      expect(isReddish(errorColour), `${theme}: current error ${errorColour}`).toBe(true);
      await set(page, "wwPcVoltage", "132");
      const plainColour = await colour(page.locator("#wwPcCurrentNote"));
      expect(isReddish(plainColour), `${theme}: plain note ${plainColour}`).toBe(false);

      await openTab(page, "pqs");
      await set(page, "wwPqsP", "100");
      await set(page, "wwPqsQ", "");
      await set(page, "wwPqsS", "80");
      expect(isReddish(await colour(page.locator("#wwPqsNote"))), `${theme}: P-Q-S error`).toBe(true);
      await set(page, "wwPqsP", "80");
      await set(page, "wwPqsQ", "60");
      await set(page, "wwPqsS", "");

      await openTab(page, "pf");
      await set(page, "wwPfValue", "1.2");
      expect(isReddish(await colour(page.locator("#wwPfNote"))), `${theme}: PF error`).toBe(true);
      await set(page, "wwPfValue", "0.8");
      await set(page, "wwPfS", "");
      await set(page, "wwPfQ", "-60");
      const warn = await colour(page.locator("#wwPfNote"));
      await expect(page.locator("#wwPfNote")).toHaveClass(/ww-calculator-message--warn/);
      await expect(page.locator("#wwPfNote")).not.toHaveClass(/ww-calculator-message--error/);
      expect(isAmber(warn), `${theme}: warning ${warn}`).toBe(true);
      await set(page, "wwPfQ", "");
      await set(page, "wwPfS", "100");
    }
  });

  test("the calculated tag sits inside its field and rows stay aligned at phone width", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await openPowerCurrent(page);
    for (const [tab, prefix] of [["pqs", "wwPqs"], ["pf", "wwPf"]]) {
      await openTab(page, tab);
      for (const key of ["P", "Q", "S"]) {
        const rects = await page.evaluate(([pfx, k]) => {
          const box = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, h: r.height }; };
          const input = document.getElementById(pfx + k);
          const unit = document.getElementById(pfx + k + "Unit");
          const tag = document.getElementById(pfx + k + "Tag");
          return { input: box(input), unit: box(unit), tag: tag.hidden ? null : box(tag), label: box(input.closest("label").querySelector(".ww-phasor-field-label")) };
        }, [prefix, key]);
        // Input and unit select share top and bottom edges (labels never wrapped apart).
        expect(Math.abs(rects.input.top - rects.unit.top), `${tab} ${key} top`).toBeLessThanOrEqual(1.5);
        expect(Math.abs(rects.input.bottom - rects.unit.bottom), `${tab} ${key} bottom`).toBeLessThanOrEqual(1.5);
        // The label stays on one line (a wrapped label is taller than a line of text).
        expect(rects.label.h, `${tab} ${key} label height`).toBeLessThan(24);
        if (rects.tag) {
          expect(rects.tag.left).toBeGreaterThanOrEqual(rects.input.left);
          expect(rects.tag.right).toBeLessThanOrEqual(rects.input.right);
          expect(rects.tag.top).toBeGreaterThanOrEqual(rects.input.top);
          expect(rects.tag.bottom).toBeLessThanOrEqual(rects.input.bottom);
        }
      }
    }
  });

  test("no console errors across every tab, toggle and an invalid-input sweep", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));
    await openPowerCurrent(page);
    await page.locator("#wwPcSystemSingleBtn").click();
    await set(page, "wwPcVoltage", "");
    await page.locator("#wwPcVoltage").pressSequentially("1e");
    await openTab(page, "pqs");
    await set(page, "wwPqsP", "");
    await page.locator("#wwPqsP").pressSequentially("1e999");
    await openTab(page, "pf");
    await set(page, "wwPfValue", "0");
    await page.locator("#wwPfLeadingBtn").click();
    await set(page, "wwPfValue", "0.5");
    await expectNoNaN(page);
    expect(consoleErrors).toEqual([]);
  });
});
