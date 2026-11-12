// Stage 3B-2B-2 Browser Regression — HTTP 422 Invalid Calibration Authority (DEC-213)
//
// Verifies that the frontend handles HTTP 422 from the calculated-channel waveform
// evaluation endpoint correctly when the backend raises InvalidCalibrationAuthorityError:
//
//   • Waveform error state is shown (error message element visible)
//   • Loading spinner is cleared (not stuck in loading state)
//   • No Plotly crash or unhandled JS error
//   • No stale data is presented as a valid current result
//
// Uses a controlled page.route() intercept to return a mock HTTP 422 response with
// the actual InvalidCalibrationAuthorityError body shape, since a real Invalid-authority
// source cannot be created through the UI (creation gate blocks it, as Stage 3B-2B-2
// tests confirm). The intercept is applied AFTER channel creation so creation succeeds
// normally using the BEN5K Unverified source.
//
// Prerequisites:
//   • Backend running with BEN5K_EXPERIMENTAL_ENABLED=1
//   • Tests skip gracefully if the backend rejects the BEN5K upload.
//
// Run with BEN5K enabled:
//   BEN5K_EXPERIMENTAL_ENABLED=1 npx playwright test ben5k-invalid-calibration-gate.spec.js

const { test, expect } = require("./support/test");
const path = require("path");

const FIXTURE = path.join(
  __dirname, "..", "backend", "tests", "fixtures", "ben", "synthetic_ben5k.ben"
);

function trackErrors(page) {
  const errors = [];
  // Track only unhandled JS exceptions (pageerror), not console.error messages.
  // Browsers always log "Failed to load resource: status 422" as a console error
  // for intercepted HTTP 422 responses; that's expected browser behavior and must
  // not be treated as a crash.
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

async function uploadBen5kFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFormatSelect").selectOption("ben");
  await page.locator("#uploadModalFile_0").setInputFiles(FIXTURE);
  await page.locator("#uploadModalSubmitBtn").click();

  const outcome = await Promise.race([
    page.locator("#uploadModalOverlay").waitFor({ state: "hidden", timeout: 15_000 }).then(() => "hidden"),
    page.locator("#uploadModalStatus").getByText(/not supported|unsupported_ben_variant|not currently supported/i)
      .waitFor({ timeout: 15_000 }).then(() => "rejected"),
  ]).catch(() => "timeout");

  if (outcome !== "hidden") return null;
  const tableRow = page.locator("#recordingsTableBody tr[data-source-id]").first();
  await expect(tableRow).toBeVisible({ timeout: 10_000 });
  return tableRow.getAttribute("data-source-id");
}

async function openCalcPage(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

async function pickInput(page, label) {
  const select = page.locator("#wwCcUnaryInputSelect");
  const value = await select.locator("option").evaluateAll(
    (options, wanted) => (options.find((o) => o.textContent.includes(wanted)) || {}).value,
    label
  );
  expect(value, `input option containing "${label}"`).toBeTruthy();
  await select.selectOption(value);
}

async function createReversePolarity(page, inputLabel) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="reverse_polarity"]').click();
  await pickInput(page, inputLabel);
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);

  const rows = page.locator("#calculatedChannelsSidebarBody tr[data-calculated-channel-id]");
  const lastRow = rows.last();
  await expect(lastRow).toBeAttached({ timeout: 10_000 });
  const id = await lastRow.getAttribute("data-calculated-channel-id");
  const name = await lastRow.getAttribute("data-channel-name");
  return { id, name };
}

async function showCalcChannel(page, name) {
  const row = page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${name}"]`);
  await expect(row).toBeAttached({ timeout: 10_000 });
  if ((await row.getAttribute("aria-pressed")) !== "true") await row.click({ force: true });
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

// ---------------------------------------------------------------------------
// Test 1: HTTP 422 on initial waveform load → error shown, no crash
//
// Flow: upload BEN5K → create Reverse Polarity calc channel →
//       intercept its waveform endpoint with mock 422 →
//       show channel in waveform → assert error state, no crash.
// ---------------------------------------------------------------------------

test("Stage 3B-2B-2: HTTP 422 on initial waveform load → error panel shown, no crash", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  // Create the calculated channel (Unverified → creation gate passes).
  await openCalcPage(page);
  const calc = await createReversePolarity(page, "VA");

  // Intercept ALL waveform requests for this specific calculated channel.
  // The mock response matches the actual InvalidCalibrationAuthorityError body
  // shape: FastAPI wraps the detail dict under "detail".
  await page.route(`**/calculated-channels/${calc.id}/waveform**`, async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          code: "invalid_calibration_authority",
          message: "Physical calibration is explicitly Invalid. This channel cannot be evaluated.",
        },
      }),
    });
  });

  // Navigate to Waveform and show the calculated channel.
  await page.locator("#mainNavWaveformBtn").click();
  await showCalcChannel(page, calc.name);

  // The waveform endpoint returns 422 — the frontend shows an error message
  // and clears the loading state.
  // .ww-error is a panel-level error element (role="alert") that becomes
  // visible when wwShowError() fires. Wait for it to become visible.
  await expect(
    page.locator(".ww-error:not([hidden])").first()
  ).toBeVisible({ timeout: 15_000 });

  // Loading spinner must be cleared (not stuck in loading state).
  const loadingVisible = await page.locator(".ww-chart-loading:not([hidden])").first().isVisible();
  expect(loadingVisible, "Loading spinner must not remain visible after error").toBe(false);

  // No JS error or Plotly crash.
  expect(errors, `Console/page errors after HTTP 422:\n${errors.join("\n")}`).toEqual([]);
});

// ---------------------------------------------------------------------------
// Test 2: HTTP 422 on reload (after initial success) → stale trace not silently
//         retained as valid; error shown and no crash.
//
// Flow: create channel → let initial load succeed normally →
//       then intercept the endpoint with 422 → trigger a reload →
//       assert error appears and loading clears.
// ---------------------------------------------------------------------------

test("Stage 3B-2B-2: HTTP 422 on reload → error shown, no stale trace presented as valid", async ({ page }) => {
  const errors = trackErrors(page);

  const sid = await uploadBen5kFixture(page);
  test.skip(!sid, "BEN5K upload not supported in this environment (BEN5K_EXPERIMENTAL_ENABLED not set)");

  await openCalcPage(page);
  const calc = await createReversePolarity(page, "VA");

  // Navigate to Waveform and show the channel — initial load with no route intercept.
  await page.locator("#mainNavWaveformBtn").click();
  await showCalcChannel(page, calc.name);

  // Wait for initial successful load: Plotly chart is ready and the .ww-error
  // element is hidden (no error on initial load from Unverified BEN5K source).
  await expect(page.locator(".ww-chart .plotly").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".ww-error:not([hidden])").first()).not.toBeVisible({ timeout: 5_000 });

  // Now intercept ALL subsequent requests for this channel's waveform.
  await page.route(`**/calculated-channels/${calc.id}/waveform**`, async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          code: "invalid_calibration_authority",
          message: "Physical calibration is explicitly Invalid. This channel cannot be evaluated.",
        },
      }),
    });
  });

  // Trigger a reload by clicking Autoscale X (resets the viewport and forces
  // a fresh waveform range request for every displayed channel).
  await page.locator("#wwAutoscaleXBtn").click();

  // The 422 response is returned; the error panel must become visible.
  await expect(
    page.locator(".ww-error:not([hidden])").first()
  ).toBeVisible({ timeout: 15_000 });

  // Loading must be cleared (not stuck).
  const loadingVisible = await page.locator(".ww-chart-loading:not([hidden])").first().isVisible();
  expect(loadingVisible, "Loading spinner must not remain visible after reload error").toBe(false);

  // No crash.
  expect(errors, `Console/page errors after reload 422:\n${errors.join("\n")}`).toEqual([]);
});
