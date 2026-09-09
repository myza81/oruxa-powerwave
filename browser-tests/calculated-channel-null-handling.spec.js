// DEC-084 Calc Slice 3: real-browser coverage for the Signal Builder's
// Null Handling controls. Same real-backend/real-frontend Playwright
// harness as smoke.spec.js (webServer config in playwright.config.js) --
// no mocks: this exercises the actual POST .../calculated-channels
// endpoint and the actual create_calculated_channel() validation, plus
// the actual live wwCcValidateBuilder()/wwCcSyncCreateButtonState()
// Create-button-disabled behavior (never a second, reimplemented
// validator -- this task's own section 28 closing instruction).
//
// One sequential walkthrough (not independent tests) since later steps
// depend on state earlier steps establish (an uploaded source, an open
// Signal Builder drawer with a chosen operation/input) -- test.step()
// still reports each part individually in output.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");

test("Calculated Channel Null Handling: defaults, conditional controls, validation, create, manager display", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await test.step("Setup - upload synth_ascii fixture", async () => {
    await page.goto("/index.html");
    await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
    await expect(page.locator("#uploadModalOverlay")).toBeVisible();
    await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, "synth_ascii.cfg"));
    await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, "synth_ascii.dat"));
    await page.locator("#uploadModalSubmitBtn").click();
    await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
    await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  });

  await test.step("Open Signal Builder, choose Reverse Polarity + one input", async () => {
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
    await page.locator("#wwCcNewChannelBtn").click();
    await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);

    await page.locator('#wwCcOperationCards .ww-cc-operation-card[data-operation="reverse_polarity"]').click();
    await expect(page.locator("#wwCcBuilderPanel")).toBeVisible();

    const inputSelect = page.locator("#wwCcUnaryInputSelect");
    await expect(inputSelect).toBeVisible();
    await inputSelect.selectOption({ index: 1 }); // first real channel, past the "Choose a channel…" placeholder
  });

  await test.step("Default Null Handling is Propagate Null, estimation controls hidden, Create allowed", async () => {
    await expect(page.locator("#wwCcNullPolicySelect")).toHaveValue("propagate_null");
    await expect(page.locator("#wwCcNullPolicyHint")).toHaveText(
      "Missing input samples remain missing in the calculated result."
    );
    await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  await test.step("Treat Null as Zero - estimation controls stay hidden, Create still allowed", async () => {
    await page.locator("#wwCcNullPolicySelect").selectOption("treat_null_as_zero");
    await expect(page.locator("#wwCcNullPolicyHint")).toContainText("Source data is not changed");
    await expect(page.locator("#wwCcEstimationFields")).toBeEmpty();
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  });

  await test.step("Estimate Missing Data - method + max gap appear, PCHIP is absent, Create blocked (no method yet)", async () => {
    await page.locator("#wwCcNullPolicySelect").selectOption("estimate_missing_data");
    await expect(page.locator("#wwCcEstimationMethodSelect")).toBeVisible();
    await expect(page.locator("#wwCcMaxGapValueInput")).toBeVisible();
    await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveCount(0);
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();

    const methodValues = await page.locator("#wwCcEstimationMethodSelect option").evaluateAll(
      (options) => options.map((o) => o.value)
    );
    expect(methodValues).toEqual(["", "hold_last", "nearest", "linear", "local_mean"]);
    expect(methodValues).not.toContain("pchip");
  });

  await test.step("Hold Last - max gap required (0, then non-integer, then valid)", async () => {
    await page.locator("#wwCcEstimationMethodSelect").selectOption("hold_last");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled(); // max gap still empty

    await page.locator("#wwCcMaxGapValueInput").fill("0");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled(); // max gap must be > 0

    await page.locator("#wwCcMaxGapValueInput").fill("1.5");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled(); // max gap must be a whole number

    await page.locator("#wwCcMaxGapValueInput").fill("3");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled(); // valid Hold Last -> allowed
  });

  await test.step("Nearest - still valid with the same max gap", async () => {
    await page.locator("#wwCcEstimationMethodSelect").selectOption("nearest");
    await expect(page.locator("#wwCcMaxGapValueInput")).toHaveValue("3");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled(); // valid Nearest -> allowed
  });

  await test.step("Local Mean - radius field appears and is required (0, then valid)", async () => {
    await page.locator("#wwCcEstimationMethodSelect").selectOption("local_mean");
    await expect(page.locator("#wwCcLocalMeanRadiusInput")).toBeVisible();
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled(); // Local Mean without radius -> blocked

    await page.locator("#wwCcLocalMeanRadiusInput").fill("0");
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled(); // radius <= 0 -> blocked

    await page.locator("#wwCcLocalMeanRadiusInput").fill("2");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled(); // valid Local Mean -> allowed
  });

  await test.step("Switch to Linear - radius field disappears, radius is not sent, still valid", async () => {
    await page.locator("#wwCcEstimationMethodSelect").selectOption("linear");
    await expect(page.locator("#wwCcLocalMeanRadiusInput")).toHaveCount(0);
    await expect(page.locator("#wwCcMaxGapValueInput")).toHaveValue("3");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled(); // valid Linear -> allowed
  });

  let createdName;
  await test.step("Create the channel", async () => {
    const nameInput = page.locator("#wwCcNameInput");
    createdName = await nameInput.inputValue();
    expect(createdName).toBeTruthy();
    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
  });

  await test.step("Manager entry shows the configured null-handling policy (Linear, radius never sent)", async () => {
    const row = page.locator(`.ww-cc-list-row[data-calculated-channel-id]`).first();
    await expect(row).toBeVisible();
    await expect(row.locator(".ww-cc-list-row-name")).toHaveText(createdName);
    await expect(row.locator(".ww-cc-list-row-summary")).toContainText("Missing data: Linear Interpolation, max 3 samples");
    // Linear never carries a radius -- the compact summary must never
    // mention one (Local Mean is the only method that does, section 18).
    await expect(row.locator(".ww-cc-list-row-summary")).not.toContainText("radius");
  });

  await test.step("No unexpected console/page errors", async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  });
});
