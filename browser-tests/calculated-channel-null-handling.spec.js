// DEC-084 Calc Slice 3/4: real-browser coverage for the Signal Builder's
// Null Handling controls (Slice 3) and their channel-level traceability
// (Slice 4: the durable, complete configuration detail surfaced on the
// selected-channel preview info strip, and UAT hardening of builder
// reset/operation-switch/method-switch/policy-switch/error-recovery/
// responsive behavior). Same real-backend/real-frontend Playwright
// harness as smoke.spec.js (webServer config in playwright.config.js) --
// no mocks: every test exercises the actual POST/GET .../calculated-
// channels endpoints and the actual live wwCcValidateBuilder()/
// wwCcSyncCreateButtonState()/wwCcRenderPreviewStatusAndInfo() behavior,
// never a second, reimplemented validator or a second metadata source.
//
// Each `test()` below gets its own fresh browser context (Playwright's
// default), which means a fresh, empty localStorage and therefore a
// brand-new random workspace id per test (see currentWorkspaceId()) --
// tests are independent and may run in any order without cross-test
// state leakage, so setup (fixture upload) is repeated per test rather
// than shared.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

async function uploadSynthAscii(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}

// A minimal one-analog-channel ASCII COMTRADE pair with a real NaN
// sample -- for the Require Manual Value rejection path (section
// 15/21). Same field layout as backend/tests/fixtures/comtrade/
// synth_ascii.cfg; `nan` is written as the literal text NumPy's own
// ASCII DAT parser (np.loadtxt) already accepts (confirmed directly in
// the Slice 1 backend work), so this is a real provider-level null
// input, not a UI-only fixture.
function synthNanComtradeFiles() {
  const cfg = [
    "SYNTH_STATION,SYNTH_DEV,1999",
    "1,1A,0D",
    "1,VA,,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
    "50",
    "1",
    "1000.0,3",
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";
  const dat = ["1,0,10.000000", "2,1000,nan", "3,2000,30.000000"].join("\r\n") + "\r\n";
  return { cfg, dat };
}

async function uploadNanFixture(page) {
  const { cfg, dat } = synthNanComtradeFiles();
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "nan.cfg", mimeType: "application/octet-stream", buffer: Buffer.from(cfg, "ascii") });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "nan.dat", mimeType: "application/octet-stream", buffer: Buffer.from(dat, "ascii") });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}

async function openBuilder(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
}

async function chooseUnaryOperationAndInput(page, operation, inputIndex = 1) {
  await page.locator(`#wwCcOperationCards .ww-cc-operation-card[data-operation="${operation}"]`).click();
  await expect(page.locator("#wwCcBuilderPanel")).toBeVisible();
  const inputSelect = page.locator("#wwCcUnaryInputSelect");
  await expect(inputSelect).toBeVisible();
  await inputSelect.selectOption({ index: inputIndex });
}

async function addMultiInput(page, optionIndex) {
  const select = page.locator("#wwCcAddInputSelect");
  await select.selectOption({ index: optionIndex });
  await page.locator("#wwCcAddInputBtn").click();
}

async function setNullPolicy(page, policy) {
  await page.locator("#wwCcNullPolicySelect").selectOption(policy);
}

async function setEstimation(page, { method, maxGap, radius }) {
  await page.locator("#wwCcEstimationMethodSelect").selectOption(method);
  if (maxGap != null) await page.locator("#wwCcMaxGapValueInput").fill(String(maxGap));
  if (method === "local_mean" && radius != null) await page.locator("#wwCcLocalMeanRadiusInput").fill(String(radius));
}

async function setName(page, name) {
  await page.locator("#wwCcNameInput").fill(name);
}

async function createChannel(page) {
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// Reads the selected channel's preview info strip as a plain {label:
// value} map -- robust against the extra info-tip icon nested inside
// the "Missing Data Handling" label (an SVG-only button contributes no
// extra text), and reads the TRUE underlying text regardless of the
// cell's own CSS ellipsis truncation (a rendering concern, not a data-
// correctness one).
async function previewInfoMap(page) {
  return page.evaluate(() => {
    const map = {};
    document.querySelectorAll("#wwCcPreviewInfoStrip > div").forEach((row) => {
      const label = row.querySelector(".ww-cc-preview-info-label");
      const value = row.querySelector(".ww-cc-preview-info-value");
      if (label && value) map[label.textContent.trim()] = value.textContent.trim();
    });
    return map;
  });
}

// The manager list sorts oldest-first (wwRenderCalculatedChannelManagerList()),
// so ".first()" is only ever the just-created channel when exactly one
// exists. A just-created channel is always auto-selected
// (wwCcCreateChannel() sets wwCcSelectedCalculatedChannelId = body.id
// before re-rendering), so ".ww-cc-list-row--selected" is the row that
// is actually correct regardless of how many channels already exist.
async function selectedManagerRowSummary(page) {
  return page.locator(".ww-cc-list-row--selected .ww-cc-list-row-summary").textContent();
}

test.describe("Calculated Channel Null Handling", () => {
  test("defaults, conditional controls, validation matrix, create, manager + preview metadata", async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

    await test.step("Setup", async () => {
      await uploadSynthAscii(page);
      await openBuilder(page);
      await chooseUnaryOperationAndInput(page, "reverse_polarity");
    });

    await test.step("Default is Propagate Null, estimation controls hidden, Create allowed", async () => {
      await expect(page.locator("#wwCcNullPolicySelect")).toHaveValue("propagate_null");
      await expect(page.locator("#wwCcNullPolicyHint")).toHaveText(
        "Missing input samples remain missing in the calculated result."
      );
      await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    await test.step("Treat Null as Zero - estimation controls stay hidden, Create still allowed", async () => {
      await setNullPolicy(page, "treat_null_as_zero");
      await expect(page.locator("#wwCcNullPolicyHint")).toContainText("Source data is not changed");
      await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    await test.step("Estimate Missing Data - method + max gap appear, PCHIP absent, Create blocked (no method yet)", async () => {
      await setNullPolicy(page, "estimate_missing_data");
      await expect(page.locator("#wwCcEstimationMethodSelect")).toBeVisible();
      await expect(page.locator("#wwCcMaxGapValueInput")).toBeVisible();
      await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveCount(0);
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

      const methodValues = await page.locator("#wwCcEstimationMethodSelect option").evaluateAll((o) => o.map((x) => x.value));
      expect(methodValues).toEqual(["", "hold_last", "nearest", "linear", "local_mean"]);
      expect(methodValues).not.toContain("pchip");
    });

    await test.step("Hold Last - max gap required (0, then non-integer, then valid)", async () => {
      await page.locator("#wwCcEstimationMethodSelect").selectOption("hold_last");
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
      await page.locator("#wwCcMaxGapValueInput").fill("0");
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
      await page.locator("#wwCcMaxGapValueInput").fill("1.5");
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
      await page.locator("#wwCcMaxGapValueInput").fill("3");
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    await test.step("Nearest - still valid with the same max gap", async () => {
      await page.locator("#wwCcEstimationMethodSelect").selectOption("nearest");
      await expect(page.locator("#wwCcMaxGapValueInput")).toHaveValue("3");
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    await test.step("Local Mean - radius field appears and is required (0, then valid)", async () => {
      await page.locator("#wwCcEstimationMethodSelect").selectOption("local_mean");
      await expect(page.locator("#wwCcLocalMeanRadiusInput")).toBeVisible();
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
      await page.locator("#wwCcLocalMeanRadiusInput").fill("0");
      await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
      await page.locator("#wwCcLocalMeanRadiusInput").fill("2");
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    await test.step("Switch to Linear - radius field disappears, radius is not sent, still valid", async () => {
      await page.locator("#wwCcEstimationMethodSelect").selectOption("linear");
      await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveCount(0);
      await expect(page.locator("#wwCcMaxGapValueInput")).toHaveValue("3");
      await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
    });

    let createdName;
    await test.step("Create the channel", async () => {
      createdName = await page.locator("#wwCcNameInput").inputValue();
      expect(createdName).toBeTruthy();
      await createChannel(page);
    });

    await test.step("Manager row + preview info strip both show the API-backed Linear configuration", async () => {
      const row = page.locator(".ww-cc-list-row[data-calculated-channel-id]").first();
      await expect(row).toBeVisible();
      await expect(row.locator(".ww-cc-list-row-name")).toHaveText(createdName);
      await expect(row.locator(".ww-cc-list-row-summary")).toContainText("Missing data: Linear Interpolation, max 3 samples");
      await expect(row.locator(".ww-cc-list-row-summary")).not.toContainText("radius");

      const info = await previewInfoMap(page);
      expect(info["Missing Data Handling"]).toBe("Estimate Missing Data");
      expect(info["Method"]).toBe("Linear Interpolation");
      expect(info["Maximum Gap"]).toBe("3 samples");
      expect(info["Local Mean Radius"]).toBeUndefined();
    });

    await test.step("No unexpected console/page errors", async () => {
      expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
    });
  });

  test("create and inspect every remaining null-handling path (manager + preview match the API response)", async ({ page }) => {
    await uploadSynthAscii(page);

    // Propagate Null (the default -- created without touching the select).
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setName(page, "Propagate Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Null: Propagate");
    let info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Propagate Null");
    expect(info["Method"]).toBeUndefined();
    expect(info["Maximum Gap"]).toBeUndefined();

    // Treat Null as Zero.
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "absolute_value");
    await setNullPolicy(page, "treat_null_as_zero");
    await setName(page, "Zero Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Null: Treat as Zero");
    info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Treat Null as Zero");
    expect(info["Method"]).toBeUndefined();

    // Estimate + Hold Last.
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "hold_last", maxGap: 2 });
    await setName(page, "Hold Last Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Missing data: Hold Last Value, max 2 samples");
    info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Estimate Missing Data");
    expect(info["Method"]).toBe("Hold Last Value");
    expect(info["Maximum Gap"]).toBe("2 samples");

    // Estimate + Nearest.
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "absolute_value");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "nearest", maxGap: 5 });
    await setName(page, "Nearest Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Missing data: Nearest Value, max 5 samples");
    info = await previewInfoMap(page);
    expect(info["Method"]).toBe("Nearest Value");
    expect(info["Maximum Gap"]).toBe("5 samples");

    // Estimate + Local Mean.
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "local_mean", maxGap: 4, radius: 2 });
    await setName(page, "Local Mean Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Missing data: Local Mean, max 4 samples, radius 2");
    info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Estimate Missing Data");
    expect(info["Method"]).toBe("Local Mean");
    expect(info["Maximum Gap"]).toBe("4 samples");
    expect(info["Local Mean Radius"]).toBe("2 samples each side");

    // Require Manual Value -- a FINITE input, so creation succeeds
    // (section 15's own explicit split: the rejection path is covered
    // separately, in "Require Manual Value: backend rejection then
    // recovery" below).
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "absolute_value");
    await setNullPolicy(page, "require_manual_value");
    await setName(page, "Require Manual Channel");
    await createChannel(page);
    expect(await selectedManagerRowSummary(page)).toContain("Null: Require Manual");
    info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Require Manual Value");
    expect(info["Method"]).toBeUndefined();
  });

  test("builder reset returns to Propagate Null with no leaked estimation state", async ({ page }) => {
    await uploadSynthAscii(page);
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "local_mean", maxGap: 4, radius: 2 });
    await setName(page, "Leak Test Channel");
    await createChannel(page);

    // Reopen the builder for a second, unrelated channel.
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="absolute_value"]').click();
    await expect(page.locator("#wwCcBuilderPanel")).toBeVisible();

    await expect(page.locator("#wwCcNullPolicySelect")).toHaveValue("propagate_null");
    await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
  });

  test("switching operation cards preserves the configured null-handling policy", async ({ page }) => {
    await uploadSynthAscii(page);
    await openBuilder(page);

    await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="addition"]').click();
    await addMultiInput(page, 1); // VA
    await addMultiInput(page, 2); // VB
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "linear", maxGap: 3 });

    // Switching Addition -> Subtraction clears INPUTS (existing,
    // unrelated behavior) but must never clear null-handling state.
    await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="subtraction"]').click();
    await expect(page.locator("#wwCcNullPolicySelect")).toHaveValue("estimate_missing_data");
    await expect(page.locator("#wwCcEstimationMethodSelect")).toHaveValue("linear");
    await expect(page.locator("#wwCcMaxGapValueInput")).toHaveValue("3");

    await addMultiInput(page, 1); // VA
    await addMultiInput(page, 2); // VB
    await setName(page, "Switched Operation Channel");
    await createChannel(page);

    expect(await selectedManagerRowSummary(page)).toContain("Missing data: Linear Interpolation, max 3 samples");
  });

  test("switching estimation method away from Local Mean clears the radius from the created channel", async ({ page }) => {
    await uploadSynthAscii(page);
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "local_mean", maxGap: 3, radius: 2 });
    await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveValue("2");

    await page.locator("#wwCcEstimationMethodSelect").selectOption("linear");
    await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveCount(0);
    await setName(page, "Method Switch Channel");
    await createChannel(page);

    const summary = await selectedManagerRowSummary(page);
    expect(summary).toContain("Missing data: Linear Interpolation, max 3 samples");
    expect(summary).not.toContain("radius");
    const info = await previewInfoMap(page);
    expect(info["Local Mean Radius"]).toBeUndefined();
  });

  test("switching null policy away from Estimate clears estimation metadata from the created channel", async ({ page }) => {
    await uploadSynthAscii(page);
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "linear", maxGap: 3 });

    await setNullPolicy(page, "treat_null_as_zero");
    await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
    await setName(page, "Policy Switch Channel");
    await createChannel(page);

    const summary = await selectedManagerRowSummary(page);
    expect(summary).toContain("Null: Treat as Zero");
    expect(summary).not.toContain("Missing data");
    const info = await previewInfoMap(page);
    expect(info["Missing Data Handling"]).toBe("Treat Null as Zero");
    expect(info["Method"]).toBeUndefined();
    expect(info["Maximum Gap"]).toBeUndefined();
  });

  test("Require Manual Value: backend rejection then recovery via policy switch", async ({ page }) => {
    await uploadNanFixture(page);
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity"); // the only channel, VA, carries one NaN sample

    await setNullPolicy(page, "require_manual_value");
    await setName(page, "Recovery Channel");
    // Section 15: no JS pre-scan -- the Create button is enabled purely
    // from shape validation (operation/inputs/name), never from
    // inspecting the input's own values.
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/); // rejected -- drawer stays open
    await expect(page.locator("#wwCcError")).toBeVisible();
    await expect(page.locator("#wwCcError")).toContainText(/manual|missing|invalid/i);

    // User switches policy (same input, still carrying the NaN) --
    // Propagate Null tolerates it -- and Create now succeeds.
    await setNullPolicy(page, "propagate_null");
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

    // No stale error survives into the next drawer open.
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcError")).toBeHidden();
  });

  test("responsive layout: builder and manager have no horizontal overflow across breakpoints", async ({ page }) => {
    await uploadSynthAscii(page);
    await openBuilder(page);
    await chooseUnaryOperationAndInput(page, "reverse_polarity");
    await setNullPolicy(page, "estimate_missing_data");
    await setEstimation(page, { method: "local_mean", maxGap: 3, radius: 2 });

    for (const width of [1440, 1280, 1024, 820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator("#wwCcDrawer")).toBeVisible();
      await expect(page.locator("#wwCcLocalMeanRadiusInput")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      expect(overflow, `builder horizontal overflow at width ${width}`).toBe(false);
    }

    await setName(page, "Responsive Channel");
    await createChannel(page);

    for (const width of [1440, 1280, 1024, 820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator(".ww-cc-list-row[data-calculated-channel-id]").first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
      expect(overflow, `manager horizontal overflow at width ${width}`).toBe(false);
    }
  });
});
