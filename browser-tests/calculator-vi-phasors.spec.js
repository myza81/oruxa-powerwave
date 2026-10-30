// Calculator -- V-I Phasors tab.
// This tab calls the backend (POST /api/v1/calculator/power/single-phase),
// so the full webServer config (backend + frontend) must be running.

const { test, expect } = require("@playwright/test");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const VI_API_PATH = "/api/v1/calculator/power/single-phase";

function viResponsePromise(page, timeout = 8000) {
  return page.waitForResponse(
    (resp) => resp.url().includes(VI_API_PATH) && resp.request().method() === "POST",
    { timeout }
  );
}

async function openViTab(page) {
  const backendPort = process.env.PW_BACKEND_PORT || "8000";
  await page.route("**/config.js", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "http://127.0.0.1:${backendPort}", environment: "test", buildVersion: "calculator-vi-test" };`,
    })
  );
  // Set up response waiter BEFORE navigation so it catches the initial debounce fetch.
  const firstResult = viResponsePromise(page, 10000);
  await page.goto("/index.html");
  await page.locator("#mainNavCalculatorBtn").click();
  await expect(page.locator("#pageCalculator")).toBeVisible();
  await page.locator("#wwCalcToolPowerCurrentBtn").click();
  await expect(page.locator("#wwCalcToolPowerCurrent")).toBeVisible();
  await page.locator("#wwPcTabViBtn").click();
  await expect(page.locator("#wwPcViPanel")).toBeVisible();
  await expect(page.locator("#wwPcTabViBtn")).toHaveAttribute("aria-selected", "true");
  // Wait for the initial API result to arrive.
  await firstResult;
  await expect(page.locator("#wwViResultBody")).not.toContainText("Calculating", { timeout: 3000 });
}

async function setViAndWait(page, opts = {}) {
  // Must set up response waiter BEFORE filling inputs (debounce fires 200ms after).
  const resp = viResponsePromise(page);
  await setVi(page, opts);
  await resp;
  await expect(page.locator("#wwViResultBody")).not.toContainText("Calculating", { timeout: 3000 });
}

async function setVi(page, { vMag, vUnit, vAngle, iMag, iUnit, iAngle } = {}) {
  if (vMag !== undefined) await page.locator("#wwViVMag").fill(String(vMag));
  if (vUnit !== undefined) await page.locator("#wwViVUnit").selectOption(vUnit);
  if (vAngle !== undefined) await page.locator("#wwViVAngle").fill(String(vAngle));
  if (iMag !== undefined) await page.locator("#wwViIMag").fill(String(iMag));
  if (iUnit !== undefined) await page.locator("#wwViIUnit").selectOption(iUnit);
  if (iAngle !== undefined) await page.locator("#wwViIAngle").fill(String(iAngle));
}

function resultRow(page, qty) {
  return page.locator(`#wwViResultBody tr`).filter({ hasText: qty }).first();
}

async function expectNoNaN(page) {
  await expect(page.locator("#wwPcViPanel")).not.toContainText(/NaN|Infinity/);
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: tab navigation", () => {
  test("V-I Phasors tab is the fourth tab and opens its own panel", async ({ page }) => {
    await openViTab(page);
    await expect(page.locator("#wwPcViPanel")).toBeVisible();
    await expect(page.locator("#wwPcCurrentPanel")).toBeHidden();
    await expect(page.locator("#wwPcPqsPanel")).toBeHidden();
    await expect(page.locator("#wwPcPfPanel")).toBeHidden();
  });

  test("switching away from V-I Phasors hides its panel", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwPcTabCurrentBtn").click();
    await expect(page.locator("#wwPcCurrentPanel")).toBeVisible();
    await expect(page.locator("#wwPcViPanel")).toBeHidden();
  });
});

// ---------------------------------------------------------------------------
// Golden-vector cases (default inputs: V=11 kV @ 0°, I=100 A @ -30°)
// P = 11000 * 100 * cos(30°) = 952627.9 W ≈ 0.9526 MW
// Q = 11000 * 100 * sin(30°) = 550000 var = 0.55 MVAr
// S = 11000 * 100 = 1100000 VA = 1.1 MVA
// PF = cos(30°) ≈ 0.8660  (lagging)
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: lagging load (default inputs)", () => {
  test("shows P, Q, S, PF and angle on page load", async ({ page }) => {
    await openViTab(page);
    await expect(page.locator("#wwViResultBody")).toContainText("P");
    await expect(page.locator("#wwViResultBody")).toContainText("Q");
    await expect(page.locator("#wwViResultBody")).toContainText("S");
    await expect(page.locator("#wwViResultBody")).toContainText("PF");
    await expectNoNaN(page);
  });

  test("P is positive (absorbing active power)", async ({ page }) => {
    await openViTab(page);
    const pRow = resultRow(page, "P");
    const pText = await pRow.locator("td").nth(1).textContent();
    const pVal = parseFloat(pText);
    expect(pVal).toBeGreaterThan(0);
    expect(pVal).toBeCloseTo(0.9526, 2);
  });

  test("Q is positive (lagging / inductive)", async ({ page }) => {
    await openViTab(page);
    const qRow = resultRow(page, "Q");
    const qText = await qRow.locator("td").nth(1).textContent();
    expect(parseFloat(qText)).toBeGreaterThan(0);
  });

  test("PF row shows lagging", async ({ page }) => {
    await openViTab(page);
    const pfRow = resultRow(page, "PF");
    await expect(pfRow).toContainText("lagging");
  });

  test("formula section is populated", async ({ page }) => {
    await openViTab(page);
    await expect(page.locator("#wwViFormula")).not.toBeEmpty();
    await expect(page.locator("#wwViFormula")).toContainText("S = V");
  });
});

// ---------------------------------------------------------------------------
// Leading / capacitive
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: leading load", () => {
  test("current angle +30° gives negative Q and leading PF", async ({ page }) => {
    await openViTab(page);
    await setViAndWait(page, { iAngle: 30 });
    const qRow = resultRow(page, "Q");
    const qText = await qRow.locator("td").nth(1).textContent();
    expect(parseFloat(qText)).toBeLessThan(0);
    const pfRow = resultRow(page, "PF");
    await expect(pfRow).toContainText("leading");
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Unity power factor
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: unity PF", () => {
  test("V and I at same angle gives unity PF label", async ({ page }) => {
    await openViTab(page);
    await setViAndWait(page, { iAngle: 0 });
    const pfRow = resultRow(page, "PF");
    await expect(pfRow).toContainText("unity");
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Reverse active power (P < 0)
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: reverse power", () => {
  test("current 180° from voltage gives negative P and negative PF", async ({ page }) => {
    await openViTab(page);
    await setViAndWait(page, { iAngle: 180 });
    const pRow = resultRow(page, "P");
    const pText = await pRow.locator("td").nth(1).textContent();
    expect(parseFloat(pText)).toBeLessThan(0);
    const pfRow = resultRow(page, "PF");
    const pfText = await pfRow.locator("td").nth(1).textContent();
    // Signed PF: negative because P < 0, Q ≈ 0, sign = "unity"
    expect(parseFloat(pfText)).toBeLessThan(0);
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Zero current (open circuit)
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: zero current", () => {
  test("I = 0 A gives PF undefined", async ({ page }) => {
    await openViTab(page);
    await setViAndWait(page, { iMag: 0 });
    const pfRow = resultRow(page, "PF");
    await expect(pfRow).toContainText("undefined");
    await expectNoNaN(page);
  });

  test("I = 0 A gives S = 0", async ({ page }) => {
    await openViTab(page);
    await setViAndWait(page, { iMag: 0 });
    const sRow = resultRow(page, "S");
    const sText = await sRow.locator("td").nth(1).textContent();
    expect(parseFloat(sText)).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Angle wrapping: V @ 370° same as V @ 10°
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: angle wrapping", () => {
  test("V at 370° and V at 10° give identical results with I at 10°", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwViPUnit").selectOption("MW");
    // First: set canonical angle (triggers debounce → API)
    await setViAndWait(page, { vMag: 1, vUnit: "kV", vAngle: 10, iMag: 100, iUnit: "A", iAngle: 10 });
    const pRow1 = resultRow(page, "P");
    const p1 = parseFloat(await pRow1.locator("td").nth(1).textContent());

    // Then: wrapped angle (triggers another API call)
    await setViAndWait(page, { vAngle: 370 });
    const pRow2 = resultRow(page, "P");
    const p2 = parseFloat(await pRow2.locator("td").nth(1).textContent());

    expect(Math.abs(p1 - p2)).toBeLessThan(0.001);
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Engineering unit conversion
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: engineering unit conversion", () => {
  test("11 kV and 11000 V give the same S", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwViSUnit").selectOption("MVA");
    const sRow1 = resultRow(page, "S");
    const s1 = parseFloat(await sRow1.locator("td").nth(1).textContent());

    // Switch to V unit and set 11000 (triggers API)
    await setViAndWait(page, { vMag: 11000, vUnit: "V" });
    const sRow2 = resultRow(page, "S");
    const s2 = parseFloat(await sRow2.locator("td").nth(1).textContent());

    expect(Math.abs(s1 - s2)).toBeLessThan(0.001);
    await expectNoNaN(page);
  });

  test("changing output unit re-renders without a new API call (same result, new scale)", async ({ page }) => {
    const requests = [];
    page.on("request", (req) => {
      if (req.url().includes(VI_API_PATH)) requests.push(req);
    });
    await openViTab(page);
    const countAfterLoad = requests.length;
    expect(countAfterLoad).toBeGreaterThan(0);

    // Changing output unit must NOT trigger a new request
    await page.locator("#wwViSUnit").selectOption("kVA");
    await expect(page.locator("#wwViResultBody")).toContainText("S");
    expect(requests.length).toBe(countAfterLoad);
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Invalid / missing inputs
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: invalid and missing inputs", () => {
  test("blank magnitude shows prompt, not an error", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwViVMag").fill("");
    // Blank input clears the result immediately (debounce fires and detects blank → clears state)
    await expect(page.locator("#wwViResultBody")).toContainText("Enter phasors", { timeout: 3000 });
    await expect(page.locator("#wwViResultBody")).not.toContainText("Check inputs");
    await expectNoNaN(page);
  });

  test("partial (half-typed) number shows an error message", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwViVMag").fill("");
    await page.locator("#wwViVMag").pressSequentially("1e");
    await expect(page.locator("#wwViResultBody")).toContainText("Check inputs", { timeout: 3000 });
    await expectNoNaN(page);
  });
});

// ---------------------------------------------------------------------------
// Existing tab regression: other tabs are unaffected
// ---------------------------------------------------------------------------

test.describe("Calculator -- V-I Phasors: regression on existing tabs", () => {
  test("Current tab still shows 437.4 A after visiting V-I tab", async ({ page }) => {
    await openViTab(page);
    // Switch back to Current tab
    await page.locator("#wwPcTabCurrentBtn").click();
    await expect(page.locator("#wwPcCurrentPanel")).toBeVisible();
    await expect(page.locator("#wwPcCurrentValue")).toHaveText("437.4 A");
  });

  test("P-Q-S tab still computes correctly after visiting V-I tab", async ({ page }) => {
    await openViTab(page);
    await page.locator("#wwPcTabPqsBtn").click();
    await expect(page.locator("#wwPcPqsPanel")).toBeVisible();
    // Default: P=80 MW + Q=60 MVAr → S=100 MVA
    await expect(page.locator('#wwPqsResultBody tr[data-pc-row="S"] td.ww-pc-value')).toHaveText("100 MVA");
  });
});
