// Oscillation Analysis -- SETUP / INPUT workflow (no spectral processing).
//
// Real backend + real frontend, no mocks. Fixture: one synthetic 1 kHz /
// 5 s COMTRADE record with a Frequency (Hz), an Active Power (MW) and a raw
// instantaneous Voltage (V) channel. The raw V/I channel is offered through
// its RMS magnitude representation (DEC-173 [APPROVED]). Calculated channels are created through
// the backend API WHILE the Oscillation page stays open, then published to
// the shared live signal catalogue exactly as the app's own create path does
// (wwFetchCalculatedChannels), so no reload or navigation is involved.
//
// Expected metadata for the fixture: fs = 1000 Hz, duration = 5 s,
// 5001 samples, Nyquist = 500 Hz, 1/T = 0.2 Hz.

const { test, expect } = require("@playwright/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

async function openOscillation(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeOscillationBtn").click();
  await expect(page.locator("#wwOscillationPanel")).toBeVisible();
}

const DEFAULT_CHANNELS = [
  { name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 0.5 },
  { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 },
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
];

async function uploadSynthetic(page, options = {}) {
  const { cfg, dat } = syntheticComtrade({
    station: options.station || "OSC_STN", startClock: "10:00:00.000000", rateHz: options.rateHz || 1000, durationS: options.durationS || 5,
    channels: options.channels || DEFAULT_CHANNELS,
  });
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: (options.name || "osc") + ".cfg", mimeType: "text/plain", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: (options.name || "osc") + ".dat", mimeType: "text/plain", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeOscillationBtn").click();
  await expect(page.locator("#wwOscillationPanel")).toBeVisible();
}

const optionLabels = (page) => page.locator("#wwOscSignalSelect option").evaluateAll((o) => o.filter((x) => x.value).map((x) => x.textContent));
const optionValue = (page, text) => page.locator("#wwOscSignalSelect option", { hasText: text }).first().getAttribute("value");
const strip = (page) => page.locator("#wwOscEligibility");
const status = (page) => page.locator("#wwOscAdequacyStatus");
const checks = (page) => page.locator("#wwOscAdequacyList");

async function workspaceUrl(page, suffix) {
  return page.evaluate((s) => apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + s, suffix);
}
async function sourceId(page) {
  return page.evaluate(() => Array.from(ww.sourceChannelsData.keys())[0]);
}
// Creates a calculated channel by API and publishes it like the app does.
async function createCalculated(page, body) {
  const response = await page.request.post(await workspaceUrl(page, "/calculated-channels"), { data: body });
  expect(response.ok(), await response.text()).toBeTruthy();
  await page.evaluate(() => wwFetchCalculatedChannels());
  return response.json();
}
const absOf = async (page, name, channel) => createCalculated(page, {
  name, operation: "absolute_value", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: channel }],
});
const rmsOfVa = async (page, name) => createCalculated(page, {
  name, operation: "rms", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "VA" }],
  parameters: { nominal_frequency_hz: 50 },
});

async function selectFreq(page) {
  await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "FREQ"));
}
async function setWindow(page, start, end) {
  await page.locator("#wwOscWindowMode").selectOption("custom");
  await page.locator("#wwOscStartInput").fill(String(start));
  await page.locator("#wwOscEndInput").fill(String(end));
}
async function setBand(page, min, max) {
  await page.locator("#wwOscMinFreqInput").fill(String(min));
  await page.locator("#wwOscMaxFreqInput").fill(String(max));
}

test.describe("Oscillation Analysis setup -- navigation and empty state", () => {
  test("opens, shows the three sections, nothing is assessed and Analyze is disabled without a signal", async ({ page }) => {
    await openOscillation(page);
    await expect(page.locator("#wwOscillationPanel h3")).toHaveText(["Oscillation Analysis", "Analysis Information", "Data Adequacy"]);
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue("");
    await expect(page.locator("#wwOscStartInput")).toBeDisabled();
    await expect(page.locator("#wwOscMinFreqInput")).toHaveValue("0.1");
    await expect(page.locator("#wwOscMaxFreqInput")).toHaveValue("2");
    await expect(status(page)).toHaveText("Not assessed");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("—");
    // No chart/placeholder surfaces and no result.
    await expect(page.locator("#wwOscillationPanel .js-plotly-plot, #wwOscillationPanel canvas, #wwOscillationPanel svg")).toHaveCount(0);
  });

  test("moving away and back keeps the page working and the other analyzers unchanged", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setBand(page, 0.5, 2);
    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(page.locator("#wwOscillationPanel")).toBeHidden();
    await expect(page.locator("#wwPhasorPanel")).toBeVisible();
    await page.locator("#wwAnalysisTypeOscillationBtn").click();
    await expect(page.locator("#wwOscillationPanel")).toBeVisible();
    // Setup state persists across analyzer switches within the session.
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(/raw:analog:/);
    await expect(page.locator("#wwOscMinFreqInput")).toHaveValue("0.5");
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("1000 Hz");
    // Leaving Analysis entirely and coming back re-reads the live catalogue.
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#mainNavAnalysisBtn").click();
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(/raw:analog:/);
    await expect(page.locator("#wwOscInfoNyquist")).toHaveText("500 Hz");
  });
});

test.describe("Oscillation Analysis setup -- signal eligibility from the shared catalogue", () => {
  test("eligible raw signals are offered, including raw instantaneous AC voltage via its RMS magnitude", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    const labels = await optionLabels(page);
    expect(labels).toContain("FREQ [Hz]");
    expect(labels).toContain("P_MW [MW]");
    expect(labels).toContain("VA [V]");
    // Raw V/I is no longer "requires preprocessing": nothing is reported as such.
    await expect(strip(page)).not.toContainText("preprocessing");
    await expect(page.locator("#wwOscEligibilityDetails")).toBeHidden();
    await page.locator("#wwOscEligibilityToggle").click();
    const body = page.locator("#wwOscEligibilityBody");
    await expect(body).not.toContainText("preprocessing");
    await expect(body.locator("dt", { hasText: "Eligible signals" }).locator("xpath=following-sibling::dd")).toHaveText("3");
    await expect(body.locator("dt", { hasText: "Eligible via RMS magnitude" }).locator("xpath=following-sibling::dd")).toHaveText("1");
  });

  test("a compatible calculated channel appears live without reload; an RMS voltage becomes eligible", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await page.evaluate(() => { window.__marker = "same-page-load"; });
    const before = await optionLabels(page);
    await absOf(page, "ABS FREQ", "FREQ");
    await expect.poll(() => optionLabels(page)).toContain("ABS FREQ [Hz]");
    await rmsOfVa(page, "RMS VA");
    await expect.poll(() => optionLabels(page)).toContain("RMS VA [V]");
    const after = await optionLabels(page);
    expect(after.length).toBe(before.length + 2);
    // Calculated channels sit under their reference recording and need no Oscillation registration.
    await expect(page.locator('#wwOscSignalSelect optgroup')).toHaveCount(1);
    await expect(page.locator('#wwOscSignalSelect optgroup[label="osc.cfg"] option')).toHaveCount(5);
    expect(await page.evaluate(() => window.__marker)).toBe("same-page-load");
    // A calculated channel is selectable and yields metadata from its reference recording.
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "RMS VA"));
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("1000 Hz");
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("≈ 5001");
  });

  test("selected identity is the catalogue key + revisions, not just the name", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await absOf(page, "ABS FREQ", "FREQ");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "ABS FREQ"));
    const state = await page.evaluate(() => ({
      key: wwOscState.signalKey, revision: wwOscState.signalRevision, catalogueRevision: wwOscState.catalogueRevision,
      current: wwSignalCatalogueIsCurrent(wwOscState.signalKey, wwOscState.signalRevision),
    }));
    expect(state.key).toMatch(/^calculated:calc-/);
    expect(state.revision).toBeTruthy();
    expect(state.catalogueRevision).toBeGreaterThan(0);
    expect(state.current).toBe(true);
  });

  test("removing the selected calculated channel clears the selection and resets dependent state", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    const made = await absOf(page, "ABS FREQ", "FREQ");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "ABS FREQ"));
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("1000 Hz");
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    await expect.poll(() => optionLabels(page)).not.toContain("ABS FREQ [Hz]");
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue("");
    await expect(page.locator("#wwOscSelectionNotice")).toContainText("selection cleared");
    await expect(page.locator("#wwOscStartInput")).toBeDisabled();
    await expect(page.locator("#wwOscStartInput")).toHaveValue("");
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("—");
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("—");
    await expect(status(page)).toHaveText("Not assessed");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
  });

  test("an unrelated catalogue change keeps a valid selection and the edited window", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setWindow(page, 1, 4);
    await setBand(page, 0.5, 2);
    const keyBefore = await page.locator("#wwOscSignalSelect").inputValue();
    const other = await absOf(page, "ABS MW", "P_MW");
    await expect.poll(() => optionLabels(page)).toContain("ABS MW [MW]");
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(keyBefore);
    await expect(page.locator("#wwOscStartInput")).toHaveValue("1");
    await expect(page.locator("#wwOscEndInput")).toHaveValue("4");
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("3 s");
    // Removing an unrelated signal does not reset it either.
    await page.evaluate((id) => wwCcDeleteChannel(id), other.id);
    await expect.poll(() => optionLabels(page)).not.toContain("ABS MW [MW]");
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(keyBefore);
    await expect(page.locator("#wwOscStartInput")).toHaveValue("1");
    await expect(page.locator("#wwOscSelectionNotice")).toBeHidden();
  });
});

test.describe("Oscillation Analysis setup -- eligibility status strip", () => {
  test("Limited strip is compact: status, reason, duration; details are closed", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    // Default band 0.1-2 Hz over 5 s: below the 2-cycle guideline (0.4 Hz) -> Limited.
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("⚠ Limited");
    await expect(strip(page)).toHaveAttribute("data-status", "limited");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("Slow oscillations below approximately 0.4 Hz");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("Duration 5 s");
    await expect(page.locator("#wwOscEligibilityToggle")).toHaveText("View details");
    await expect(page.locator("#wwOscEligibilityDetails")).toBeHidden();
    const box = await strip(page).boundingBox();
    expect(box.height).toBeLessThan(40);
  });

  test("details disclosure shows concise engineering facts and hides again", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await page.locator("#wwOscEligibilityToggle").click();
    await expect(page.locator("#wwOscEligibilityToggle")).toHaveText("Hide details");
    const details = page.locator("#wwOscEligibilityDetails");
    await expect(details).toBeVisible();
    await expect(details.locator(".ww-osc-rec")).toHaveCount(1);
    await expect(details.locator(".ww-osc-rec-name")).toHaveText("osc.cfg");
    await expect(details).toContainText("Sampling rate");
    await expect(details).toContainText("1000 Hz");
    await expect(details).toContainText("Eligible signals");
    await expect(details).toContainText("Eligible via RMS magnitude");
    await expect(details).not.toContainText("preprocessing");
    await expect(details).toContainText("Recommended minimum");
    await expect(details).toContainText("≈ 0.4 Hz (2-cycle guideline)");
    await expect(details).toContainText("OSC_STN");
    await page.locator("#wwOscEligibilityToggle").click();
    await expect(details).toBeHidden();
  });

  test("a recording holding only raw V/I is NOT reported as having zero eligible signals", async ({ page }) => {
    await openOscillation(page);
    const channels = ["VA", "VB", "VC", "IA", "IB", "IC"].map((name, i) => ({
      name, unit: i < 3 ? "V" : "A", phase: "ABC"[i % 3], amplitude: 100, frequencyHz: 50, phaseShiftRad: (-2 * Math.PI * (i % 3)) / 3,
    }));
    await uploadSynthetic(page, { channels });
    await expect(page.locator("#wwOscSignalSelect")).toBeEnabled();
    expect(await optionLabels(page)).toEqual(["VA [V]", "VB [V]", "VC [V]", "IA [A]", "IB [A]", "IC [A]"]);
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("No directly eligible signals");
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("preprocessing");
    await page.locator("#wwOscEligibilityToggle").click();
    const body = page.locator("#wwOscEligibilityBody");
    await expect(body.locator("dt", { hasText: "Eligible signals" }).locator("xpath=following-sibling::dd")).toHaveText("6");
    await expect(body.locator("dt", { hasText: "Eligible via RMS magnitude" }).locator("xpath=following-sibling::dd")).toHaveText("6");
  });

  test("an empty workspace is Not suitable with an explicit reason", async ({ page }) => {
    await openOscillation(page);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✕ Not suitable");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("No analog signals are available");
    await expect(page.locator("#wwOscSignalSelect")).toBeDisabled();
  });

  test("a short recording is Limited for slow oscillations, not invalid", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 1, channels: [DEFAULT_CHANNELS[0], DEFAULT_CHANNELS[1]] });
    // Default band 0.1-2 Hz, T = 1 s -> recommended minimum ~2 Hz.
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("⚠ Limited");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("Slow oscillations below approximately 2 Hz");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("Duration 1 s");
    await selectFreq(page);
    await setBand(page, 2, 10);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✓ Suitable");
  });

  test("a requested band above Nyquist is Not suitable, with and without a selection", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { channels: [DEFAULT_CHANNELS[0]] });
    await setBand(page, 0.5, 600);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✕ Not suitable");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("exceeds the Nyquist frequency 500 Hz");
    await selectFreq(page);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✕ Not suitable");
    await setBand(page, 0.5, 2);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✓ Suitable");
  });

  test("an invalid selected window makes the strip Not suitable; the strip follows live catalogue changes", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { channels: [DEFAULT_CHANNELS[0], DEFAULT_CHANNELS[2]] });
    await selectFreq(page);
    await setBand(page, 0.5, 2);
    await setWindow(page, 3, 3);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✕ Not suitable");
    await setWindow(page, 0, 5);
    // With a signal selected the strip describes that setup, not the workspace:
    // another signal's preprocessing need does not make it Limited.
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✓ Suitable");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("osc.cfg");
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("preprocessing");
    await rmsOfVa(page, "RMS VA");
    await expect.poll(() => optionLabels(page)).toContain("RMS VA [V]");
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✓ Suitable");
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("preprocessing");
  });
});

test.describe("Oscillation Analysis setup -- analysis window modes", () => {
  test.beforeEach(async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setBand(page, 0.5, 2);
  });

  test("defaults to Full recording with no editable fields; Custom range exposes them", async ({ page }) => {
    await expect(page.locator("#wwOscWindowMode")).toHaveValue("full");
    await expect(page.locator("#wwOscStartInput")).toBeHidden();
    await expect(page.locator("#wwOscEndInput")).toBeHidden();
    await expect(page.locator("#wwOscWindowReadout")).toHaveText("Window: 0 to 5 s");
    await page.locator("#wwOscWindowMode").selectOption("custom");
    await expect(page.locator("#wwOscStartInput")).toBeVisible();
    await expect(page.locator("#wwOscEndInput")).toBeVisible();
    await setWindow(page, 1, 2);
    await page.locator("#wwOscWindowMode").selectOption("full");
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("5 s");
  });

  test("Current visible range uses the Waveform viewport (workspace time) clipped to the signal", async ({ page }) => {
    await page.evaluate(() => { ww.viewport = { start: 1, end: 2.5 }; });
    await page.locator("#wwOscWindowMode").selectOption("current");
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("1.5 s");
    await expect(page.locator("#wwOscWindowReadout")).toHaveText("Window: 1 to 2.5 s");
    await expect(page.locator("#wwOscStartInput")).toBeHidden();
  });
});

test.describe("Oscillation Analysis setup -- time window", () => {
  test.beforeEach(async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setBand(page, 0.5, 2);
  });

  test("defaults to the signal's full range; a valid sub-range is accepted", async ({ page }) => {
    await expect(page.locator("#wwOscStartInput")).toHaveValue("0");
    await expect(page.locator("#wwOscEndInput")).toHaveValue("5");
    await setWindow(page, 0.5, 4.5);
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("4 s");
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("≈ 4001");
    await expect(status(page)).toHaveText("Suitable");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeEnabled();
  });

  test("end <= start is invalid with a visible reason", async ({ page }) => {
    await setWindow(page, 3, 3);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("End time must be greater than start time");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await setWindow(page, 4, 2);
    await expect(checks(page)).toContainText("End time must be greater than start time");
  });

  test("a window outside the available range is invalid and not clamped", async ({ page }) => {
    await setWindow(page, -1, 3);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("available range (0 to 5 s)");
    await expect(page.locator("#wwOscStartInput")).toHaveValue("-1");
    await setWindow(page, 1, 9);
    await expect(checks(page)).toContainText("available range (0 to 5 s)");
    await expect(page.locator("#wwOscEndInput")).toHaveValue("9");
  });

  test("a window with fewer than two samples is invalid", async ({ page }) => {
    await setWindow(page, 1, 1.0005);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("at least 2 are required");
    // The (insufficient) count is still reported honestly.
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("≈ 1");
  });

  test("a cleared time field is incomplete, not silently defaulted", async ({ page }) => {
    await page.locator("#wwOscWindowMode").selectOption("custom");
    await page.locator("#wwOscStartInput").fill("");
    await expect(status(page)).toHaveText("Not assessed");
    await expect(checks(page)).toContainText("Enter a start and end time");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
  });
});

test.describe("Oscillation Analysis setup -- frequency range", () => {
  test.beforeEach(async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
  });

  test("a valid range is accepted", async ({ page }) => {
    await setBand(page, 0.5, 2);
    await expect(status(page)).toHaveText("Suitable");
    await expect(checks(page)).toContainText("within the Nyquist frequency 500 Hz");
  });

  test("minimum below zero is invalid", async ({ page }) => {
    await setBand(page, -0.1, 2);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("Minimum frequency must not be negative");
    await expect(page.locator("#wwOscMinFreqInput")).toHaveValue("-0.1");
  });

  test("maximum <= minimum is invalid", async ({ page }) => {
    await setBand(page, 2, 2);
    await expect(checks(page)).toContainText("Maximum frequency must be greater than minimum frequency");
    await setBand(page, 3, 1);
    await expect(status(page)).toHaveText("Invalid");
  });

  test("maximum above Nyquist is invalid; exactly Nyquist is allowed", async ({ page }) => {
    await setBand(page, 0.5, 600);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("exceeds the Nyquist frequency 500 Hz");
    await expect(page.locator("#wwOscMaxFreqInput")).toHaveValue("600");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await setBand(page, 0.5, 500);
    await expect(status(page)).toHaveText("Suitable");
  });
});

test.describe("Oscillation Analysis setup -- information and adequacy", () => {
  test.beforeEach(async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
  });

  test("Analysis Information uses fs, T, N, fs/2 and 1/T", async ({ page }) => {
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("1000 Hz");
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("5 s");
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("≈ 5001");
    await expect(page.locator("#wwOscInfoNyquist")).toHaveText("500 Hz");
    await expect(page.locator("#wwOscInfoResolution")).toHaveText("≈ 0.2 Hz");
    await setWindow(page, 0, 2.5);
    await expect(page.locator("#wwOscInfoDuration")).toHaveText("2.5 s");
    await expect(page.locator("#wwOscInfoSampleCount")).toHaveText("≈ 2501");
    await expect(page.locator("#wwOscInfoResolution")).toHaveText("≈ 0.4 Hz");
    await expect(page.locator("#wwOscillationPanel")).toContainText("not a final spectral-estimation segment resolution");
  });

  test("a minimum frequency below 1/T is a Warning that shows the period and cycles", async ({ page }) => {
    // Default band 0.1-2 Hz over 5 s: period 10 s, 0.5 cycle, 1/T = 0.2 Hz.
    await expect(status(page)).toHaveText("Warning");
    await expect(checks(page)).toContainText("period of 10 s");
    await expect(checks(page)).toContainText("0.5 cycle(s)");
    await expect(checks(page)).toContainText("below the window resolution");
    // A warning is not a blocker.
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeEnabled();
  });

  test("fewer than the guideline number of cycles is a Warning labelled as a guideline", async ({ page }) => {
    await setBand(page, 0.3, 2); // 1.5 cycles over 5 s, above 1/T = 0.2 Hz
    await expect(status(page)).toHaveText("Warning");
    await expect(checks(page)).toContainText("fewer than 2 observed cycles");
    await expect(checks(page)).toContainText("not a standard");
  });

  test("0 Hz minimum is accepted and noted as including DC", async ({ page }) => {
    await setBand(page, 0, 2);
    await expect(status(page)).toHaveText("Suitable");
    await expect(checks(page)).toContainText("includes DC");
  });

  test("a band narrower than 1/T is a Warning", async ({ page }) => {
    await setBand(page, 1, 1.1);
    await expect(status(page)).toHaveText("Warning");
    await expect(checks(page)).toContainText("narrower than the window resolution");
  });

  test("wording never claims detection, stability, compliance or safety", async ({ page }) => {
    await setBand(page, 0.5, 2);
    const text = (await page.locator("#wwOscillationPanel").innerText()).toLowerCase();
    for (const word of ["oscillation detected", "stable", "unstable", "compliant", "safe"]) {
      expect(text).not.toContain(word);
    }
  });

  test("Analyze validates only: no result, no dominant frequency, states it is not implemented", async ({ page }) => {
    await setBand(page, 0.5, 2);
    await expect(page.locator("#wwOscAnalyzeNote")).toContainText("not implemented yet");
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscAnalyzeNote")).toContainText("no result was produced");
    await expect(page.locator("#wwOscillationPanel")).not.toContainText(/dominant/i);
    await expect(page.locator("#wwOscillationPanel .js-plotly-plot, #wwOscillationPanel canvas, #wwOscillationPanel svg")).toHaveCount(0);
    const recorded = await page.evaluate(() => wwOscState.validatedSetup);
    expect(recorded.signalKey).toMatch(/^raw:analog:/);
    expect(recorded.catalogueRevision).toBeGreaterThan(0);
    // Editing the setup invalidates that record.
    await page.locator("#wwOscMaxFreqInput").fill("3");
    expect(await page.evaluate(() => wwOscState.validatedSetup)).toBeNull();
  });
});

test.describe("Oscillation Analysis setup -- performance and time architecture", () => {
  test("changing signal, window and band issues no backend request", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await page.waitForLoadState("networkidle");
    const requests = [];
    page.on("request", (request) => { if (request.url().includes("/api/")) requests.push(request.url()); });
    await selectFreq(page);
    await setWindow(page, 1, 3);
    await setBand(page, 0.5, 2);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    expect(requests).toEqual([]);
  });

  test("the window follows the Time Group display basis: a t0 shifts shown times, not the stored window", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setBand(page, 0.5, 2);
    await setWindow(page, 1, 3);
    const groupId = await page.evaluate(() => wwTimeGroupIdForDisplaySourceId(Array.from(ww.sourceChannelsData.keys())[0]));
    expect(groupId).toBeTruthy();
    // A t0 is set elsewhere (Waveform), so no Oscillation input has focus.
    await page.locator("#wwOscEndInput").blur();
    await page.evaluate((id) => { ww.timeGroupT0State.set(id, 1); wwOscRender(); }, groupId);
    // Event time: source 1..3 s with t0 = 1 s reads 0..2 s; the basis note says so.
    await expect(page.locator("#wwOscStartInput")).toHaveValue("0");
    await expect(page.locator("#wwOscEndInput")).toHaveValue("2");
    await expect(page.locator("#wwOscTimeBasis")).toContainText("event time");
    // Editing in event time maps back to the same source range rules.
    await setWindow(page, 0, 4);
    await expect(status(page)).toHaveText("Suitable");
    await setWindow(page, 0, 4.5);
    await expect(checks(page)).toContainText("available range (-1 to 4 s)");
    await page.evaluate((id) => { ww.timeGroupT0State.delete(id); wwOscRender(); }, groupId);
    await expect(page.locator("#wwOscStartInput")).toHaveValue("1");
    await expect(page.locator("#wwOscTimeBasis")).toContainText("workspace elapsed time");
  });
});

// ---------------------------------------------------------------------------
// Multi-recording eligibility. Band 0.5-40 Hz, 5 s windows:
//   evtA.cfg  1000 Hz, FREQ + P_MW                -> Suitable
//   evtB.cfg  1000 Hz, 1 s, FREQ + raw VA         -> Limited (slow-frequency guideline)
//   evtC.cfg    50 Hz (Nyquist 25 Hz), FREQ       -> Not suitable (band above Nyquist)
// ---------------------------------------------------------------------------
const REC_A = { name: "evtA", station: "STN_A", channels: [DEFAULT_CHANNELS[0], DEFAULT_CHANNELS[1]] };
const REC_B = { name: "evtB", station: "STN_B", durationS: 1, channels: [DEFAULT_CHANNELS[0], DEFAULT_CHANNELS[2]] };
const REC_C = { name: "evtC", station: "STN_C", rateHz: 50, channels: [DEFAULT_CHANNELS[0]] };

async function loadRecordings(page, recordings) {
  await openOscillation(page);
  await setBand(page, 0.5, 40);
  for (const options of recordings) await uploadSynthetic(page, options);
}
const sections = (page) => page.locator("#wwOscEligibilityBody .ww-osc-rec");
const sourceIdByFile = (page, file) => page.evaluate((f) => {
  for (const [id, data] of ww.sourceChannelsData) if (data.source.original_filenames.includes(f + ".cfg")) return id;
  return null;
}, file);
const selectIn = async (page, file, name) => {
  const value = await page.locator('#wwOscSignalSelect optgroup[label="' + file + '.cfg"] option', { hasText: name }).first().getAttribute("value");
  await page.locator("#wwOscSignalSelect").selectOption(value);
};

test.describe("Oscillation Analysis setup -- multi-recording eligibility", () => {
  test("workspace strip summarizes recordings, with no single recording's duration or counts", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B, REC_C]);
    await expect(strip(page)).toHaveAttribute("data-status", "limited");
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("⚠");
    const text = page.locator("#wwOscEligibilityText");
    await expect(text).toHaveText("· 3 recordings · 1 suitable · 1 limited · 1 not suitable");
    await expect(text).not.toContainText("Duration");
    await expect(text).not.toContainText("preprocessing");
    await expect(page.locator("#wwOscEligibilityToggle")).toHaveText("View details");
    await expect(page.locator("#wwOscEligibilityDetails")).toBeHidden();
  });

  test("an all-suitable workspace reads as Suitable; counts omit empty categories", async ({ page }) => {
    await loadRecordings(page, [REC_A, { ...REC_A, name: "evtA2", station: "STN_A2" }]);
    await expect(strip(page)).toHaveAttribute("data-status", "suitable");
    await expect(page.locator("#wwOscEligibilityText")).toHaveText("· 2 recordings · 2 suitable");
  });

  test("View details shows one titled section per recording with visible dividers between them", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B, REC_C]);
    await page.locator("#wwOscEligibilityToggle").click();
    await expect(sections(page)).toHaveCount(3);
    await expect(page.locator("#wwOscEligibilityBody .ww-osc-rec-name")).toHaveText(["evtA.cfg", "evtB.cfg", "evtC.cfg"]);
    await expect(page.locator("#wwOscEligibilityBody .ww-osc-rec-status")).toHaveText(["✓ Suitable", "⚠ Limited", "✕ Not suitable"]);
    const dividers = page.locator("#wwOscEligibilityBody hr.ww-osc-rec-divider");
    await expect(dividers).toHaveCount(2);
    for (let i = 0; i < 2; i += 1) {
      await expect(dividers.nth(i)).toBeVisible();
      const style = await dividers.nth(i).evaluate((el) => getComputedStyle(el).borderTopStyle + "|" + getComputedStyle(el).borderTopWidth);
      expect(style).toBe("solid|1px");
    }
    // A divider sits between consecutive sections, not around them.
    const order = await page.locator("#wwOscEligibilityBody > *").evaluateAll((els) => els.map((e) => e.tagName));
    expect(order).toEqual(["SECTION", "HR", "SECTION", "HR", "SECTION"]);
    await expect(sections(page).nth(0)).toContainText("1000 Hz");
    await expect(sections(page).nth(0)).toContainText("5 s");
    await expect(sections(page).nth(0).locator("dt", { hasText: "Eligible signals" }).locator("xpath=following-sibling::dd")).toHaveText("2");
    await expect(sections(page).nth(1).locator("dt", { hasText: "Eligible via RMS magnitude" }).locator("xpath=following-sibling::dd")).toHaveText("1");
    await expect(sections(page).nth(0).locator("dt", { hasText: "Eligible via RMS magnitude" })).toHaveCount(0);
    await expect(sections(page).nth(2)).toContainText("50 Hz");
    await expect(sections(page).nth(2)).toContainText("exceeds the Nyquist frequency 25 Hz");
  });

  test("raw V/I is selectable only under the recording that owns it; no limit is listed for it", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B]);
    await page.locator("#wwOscEligibilityToggle").click();
    const idA = await sourceIdByFile(page, "evtA");
    const idB = await sourceIdByFile(page, "evtB");
    const a = page.locator('#wwOscEligibilityBody .ww-osc-rec[data-recording-id="' + idA + '"]');
    const b = page.locator('#wwOscEligibilityBody .ww-osc-rec[data-recording-id="' + idB + '"]');
    await expect(page.locator('#wwOscSignalSelect optgroup[label="evtB.cfg"] option')).toHaveText(["FREQ [Hz]", "VA [V]"]);
    await expect(b).not.toContainText("preprocessing");
    await expect(a).not.toContainText("Signal limits");
    await expect(b).not.toContainText("Signal limits");
  });

  test("a long signal-limit list is capped per recording and says so", async ({ page }) => {
    // Undefined-type signals (no recognised unit) are selectable with a warning and listed as limits.
    const many = Array.from({ length: 14 }, (_, i) => ({ name: "U" + i, unit: "u", amplitude: 1, frequencyHz: 0.5 }));
    await loadRecordings(page, [REC_A, { name: "evtMany", station: "STN_M", durationS: 1, channels: many }]);
    await page.locator("#wwOscEligibilityToggle").click();
    const section = sections(page).nth(1);
    await expect(section.locator(".ww-osc-checks li", { hasText: "Showing 12 of 14 affected signals" })).toHaveCount(1);
    await expect(section.locator(".ww-osc-checks li", { hasText: "Available with a warning (Undefined type)" })).toHaveCount(12);
  });

  test("the selector groups signals by recording filename", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B]);
    const groups = await page.locator("#wwOscSignalSelect optgroup").evaluateAll((g) => g.map((x) => x.label));
    expect(groups).toEqual(["evtA.cfg", "evtB.cfg"]);
    await expect(page.locator('#wwOscSignalSelect optgroup[label="evtB.cfg"] option')).toHaveText(["FREQ [Hz]", "VA [V]"]);
  });

  test("selecting a signal switches the strip to its recording; clearing returns to the workspace summary", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B, REC_C]);
    await selectIn(page, "evtA", "P_MW");
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("✓ Suitable");
    await expect(page.locator("#wwOscEligibilityText")).toHaveText("· evtA.cfg · 1000 Hz · Window 5 s");
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("recordings");
    await page.locator("#wwOscEligibilityToggle").click();
    await expect(sections(page)).toHaveCount(1);
    await expect(sections(page).locator(".ww-osc-rec-name")).toHaveText("evtA.cfg");
    await expect(sections(page)).toContainText("P_MW [MW]");
    // A Limited signal setup names its reason; the sibling recordings do not leak in.
    await selectIn(page, "evtB", "FREQ");
    await setBand(page, 0.1, 40);
    await expect(page.locator("#wwOscEligibilityLabel")).toHaveText("⚠ Limited");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("evtB.cfg");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("Slow-frequency limitation");
    await expect(page.locator("#wwOscEligibilityText")).not.toContainText("evtA");
    await expect(sections(page)).toHaveCount(1);
    await expect(sections(page).locator(".ww-osc-rec-name")).toHaveText("evtB.cfg");
    await page.locator("#wwOscSignalSelect").selectOption("");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("3 recordings");
    await expect(sections(page)).toHaveCount(3);
  });

  test("a live calculated channel is added to and removed from the right recording without reload", async ({ page }) => {
    await loadRecordings(page, [REC_A, REC_B]);
    await page.evaluate(() => { window.__marker = "same-page-load"; });
    await page.locator("#wwOscEligibilityToggle").click();
    const idB = await sourceIdByFile(page, "evtB");
    const b = page.locator('#wwOscEligibilityBody .ww-osc-rec[data-recording-id="' + idB + '"]');
    const eligibleOf = (section) => section.locator("dt", { hasText: "Eligible signals" }).locator("xpath=following-sibling::dd");
    await expect(eligibleOf(b)).toHaveText("2");
    const made = await createCalculated(page, {
      name: "RMS VA B", operation: "rms", inputs: [{ kind: "source", source_id: idB, channel_name: "VA" }],
      parameters: { nominal_frequency_hz: 50 },
    });
    await expect(eligibleOf(b)).toHaveText("3");
    await expect(page.locator('#wwOscSignalSelect optgroup[label="evtB.cfg"] option', { hasText: "RMS VA B" })).toHaveCount(1);
    await expect(page.locator('#wwOscSignalSelect optgroup[label="evtA.cfg"] option', { hasText: "RMS VA B" })).toHaveCount(0);
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    await expect(eligibleOf(b)).toHaveText("2");
    await expect(page.locator("#wwOscSignalSelect option", { hasText: "RMS VA B" })).toHaveCount(0);
    expect(await page.evaluate(() => window.__marker)).toBe("same-page-load");
  });
});

// ---------------------------------------------------------------------------
// Raw instantaneous V/I -> RMS magnitude representation (DEC-173 [APPROVED]).
// Fixture VA: 100 V, 50 Hz sine, 1 kHz, 5 s (5001 samples, 20 samples/cycle).
// The backend reuses the existing one-cycle trailing RMS: the first complete
// window ends at 0.02 s, so 4981 of 5001 samples are usable; nominal frequency
// is the recording's own (50 Hz); -3 dB of the RMS window is 0.443 x 50 Hz.
// ---------------------------------------------------------------------------
const REPRESENTATION_PATH = "/oscillation-analysis/representation";
const info = (page, id) => page.locator("#" + id);

async function selectVa(page) {
  await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
  await expect(status(page)).not.toHaveText("Not assessed");
  await expect(checks(page)).not.toContainText("Preparing");
}

test.describe("Oscillation Analysis setup -- raw V/I RMS magnitude representation", () => {
  test.beforeEach(async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await setBand(page, 0.5, 2);
  });

  test("Analysis Information describes the representation, not the raw 1 kHz waveform", async ({ page }) => {
    await selectVa(page);
    await expect(info(page, "wwOscInfoRepresentation")).toHaveText("RMS / magnitude");
    await expect(info(page, "wwOscInfoSourceForm")).toHaveText("Instantaneous AC waveform");
    await expect(info(page, "wwOscInfoSourceRate")).toHaveText("1000 Hz");
    await expect(info(page, "wwOscInfoSamplingRateLabel")).toHaveText("Representation Rate");
    await expect(info(page, "wwOscInfoSamplingRate")).toHaveText("1000 Hz");
    await expect(info(page, "wwOscInfoSourceDuration")).toHaveText("5 s");
    await expect(info(page, "wwOscInfoUsableDuration")).toHaveText("4.98 s (first 0.02 s lost to the RMS window)");
    await expect(info(page, "wwOscInfoSourceCount")).toHaveText("5001");
    await expect(info(page, "wwOscInfoDerivedCount")).toHaveText("4981");
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (from the recording)");
    await expect(info(page, "wwOscInfoTimeAlignment")).toHaveText("Source time; trailing 20 ms window, magnitude lags by 10 ms");
    await expect(info(page, "wwOscInfoBandwidth")).toContainText("0 to 22.15 Hz (−3 dB)");
    await expect(info(page, "wwOscInfoBandwidth")).toContainText("none at or above 50 Hz");
    // The window is the derived signal's usable range, shown in the same time basis.
    await expect(page.locator("#wwOscWindowReadout")).toHaveText("Window: 0.02 to 5 s");
    await expect(info(page, "wwOscInfoDuration")).toHaveText("4.98 s");
    await expect(status(page)).toHaveText("Suitable");
    await expect(page.locator("#wwOscEligibilityText")).toContainText("RMS magnitude");
    // A native signal shows none of the derived rows.
    await selectFreq(page);
    await expect(page.locator("#wwOscInfoDerivedRows")).toBeHidden();
    await expect(info(page, "wwOscInfoRepresentation")).toHaveText("Signal as recorded");
    await expect(info(page, "wwOscInfoSamplingRateLabel")).toHaveText("Sampling Rate");
  });

  test("the raw 1 kHz Nyquist is not offered as oscillation capability", async ({ page }) => {
    await selectVa(page);
    await expect(info(page, "wwOscInfoNyquistLabel")).toHaveText("Nyquist (derived samples)");
    await setBand(page, 0.5, 30);
    await expect(status(page)).toHaveText("Warning");
    await expect(checks(page)).toContainText("above the −3 dB frequency 22.15 Hz");
    await setBand(page, 0.5, 50);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("reaches the bandwidth limit of the RMS magnitude representation (50 Hz");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await setBand(page, 0.5, 400); // well below the raw 500 Hz Nyquist, still not representable
    await expect(status(page)).toHaveText("Invalid");
    await setBand(page, 0.5, 15);
    await expect(status(page)).toHaveText("Suitable");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeEnabled();
  });

  test("the window must lie inside the derived signal's usable range", async ({ page }) => {
    await selectVa(page);
    await setWindow(page, 0, 3);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText("available range (0.02 to 5 s)");
    await setBand(page, 2, 10); // 2.98 s window: at least 2 cycles of the lowest frequency
    await setWindow(page, 0.02, 3);
    await expect(status(page)).toHaveText("Suitable");
  });

  test("the usable range follows the Time Group display basis (t0)", async ({ page }) => {
    await selectVa(page);
    const groupId = await page.evaluate(() => wwTimeGroupIdForDisplaySourceId(Array.from(ww.sourceChannelsData.keys())[0]));
    await page.evaluate((id) => { ww.timeGroupT0State.set(id, 1); wwOscRender(); }, groupId);
    await expect(page.locator("#wwOscWindowReadout")).toHaveText("Window: -0.98 to 4 s");
    await expect(page.locator("#wwOscTimeBasis")).toContainText("event time");
    const stored = await page.evaluate(() => ({ s: wwOscState.startSource, e: wwOscState.endSource }));
    expect(stored.s).toBeCloseTo(0.02, 9);
    expect(stored.e).toBeCloseTo(5, 9);
  });

  test("nothing is persisted: no calculated channel, no catalogue entry, no extra signal", async ({ page }) => {
    const snapshot = () => page.evaluate(() => ({ cat: wwSignalCatalogueList().map((s) => s.key), calc: ww.calculatedChannels.size, rev: wwSignalCatalogue.revision }));
    const before = await snapshot();
    await selectVa(page);
    await setBand(page, 0.5, 10);
    const after = await snapshot();
    expect(after.cat).toEqual(before.cat);
    expect(after.calc).toBe(0);
    expect(after.rev).toBe(before.rev);
    expect(await optionLabels(page)).toEqual(["FREQ [Hz]", "P_MW [MW]", "VA [V]"]);
    const listed = await page.request.get(await workspaceUrl(page, "/calculated-channels"));
    expect(await listed.json()).toEqual([]);
  });

  test("lazy: no request on page open or native selection; one request on selecting raw V/I; none on edits or reselect", async ({ page }) => {
    await page.waitForLoadState("networkidle");
    const requests = [];
    page.on("request", (request) => { if (request.url().includes(REPRESENTATION_PATH)) requests.push(request.method()); });
    await selectFreq(page);
    await page.locator("#wwOscEligibilityToggle").click();
    expect(requests).toEqual([]);
    await selectVa(page);
    expect(requests).toEqual(["POST"]);
    await setWindow(page, 0.5, 3);
    await setBand(page, 0.5, 10);
    await selectFreq(page);
    await selectVa(page);
    expect(requests).toEqual(["POST"]); // cached by signal key + revision
    // The response is metadata only.
    const body = await page.evaluate(() => {
      const e = Array.from(wwOscState.derivations.values())[0];
      return { state: e.state, keys: Object.keys(e.info) };
    });
    expect(body.state).toBe("ready");
    expect(body.keys).not.toContain("values");
    expect(body.keys).not.toContain("time");
  });

  test("a calculated V/I that is already RMS is analysed as recorded: no representation request", async ({ page }) => {
    await rmsOfVa(page, "RMS VA");
    await expect.poll(() => optionLabels(page)).toContain("RMS VA [V]");
    const requests = [];
    page.on("request", (request) => { if (request.url().includes(REPRESENTATION_PATH)) requests.push(request.url()); });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "RMS VA"));
    await expect(info(page, "wwOscInfoRepresentation")).toHaveText("Signal as recorded");
    expect(requests).toEqual([]);
  });

  test("a calculated instantaneous V/I (reverse polarity) is analysed through RMS magnitude", async ({ page }) => {
    await createCalculated(page, {
      name: "NEG VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "VA" }],
    });
    await expect.poll(() => optionLabels(page)).toContain("NEG VA [V]");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "NEG VA"));
    await expect(info(page, "wwOscInfoRepresentation")).toHaveText("RMS / magnitude");
    await expect(info(page, "wwOscInfoDerivedCount")).toHaveText("4981");
  });

  test("a V/I the backend cannot confirm as instantaneous is refused with the reason, not guessed", async ({ page }) => {
    await uploadSynthetic(page, { name: "slow", station: "SLOW_STN", channels: [{ name: "IA", unit: "A", phase: "A", amplitude: 100, frequencyHz: 0.5 }] });
    const value = await page.locator('#wwOscSignalSelect optgroup[label="slow.cfg"] option').first().getAttribute("value");
    await page.locator("#wwOscSignalSelect").selectOption(value);
    await expect(status(page)).toHaveText("Invalid");
    await expect(checks(page)).toContainText(/RMS or magnitude|could not be confirmed/);
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await expect(page.locator("#wwOscInfoDerivedRows")).toBeHidden();
  });

  test("removing the selected calculated derived signal clears the selection and its cached description", async ({ page }) => {
    const made = await createCalculated(page, {
      name: "NEG VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "VA" }],
    });
    await expect.poll(() => optionLabels(page)).toContain("NEG VA [V]");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "NEG VA"));
    await expect(info(page, "wwOscInfoDerivedCount")).toHaveText("4981");
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue("");
    expect(await page.evaluate(() => wwOscState.derivations.size)).toBe(0);
  });
});

test.describe("Oscillation Analysis setup -- source vs usable RMS vs analysis window durations", () => {
  test("5 kHz / 0.648 s raw V: details separate source, usable RMS and window durations", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { rateHz: 5000, durationS: 0.648, channels: [DEFAULT_CHANNELS[2]] });
    await selectVa(page);
    // Compact strip: the figure is the selected window, not the recording.
    const text = page.locator("#wwOscEligibilityText");
    await expect(text).toContainText("Window 0.628 s");
    await expect(text).not.toContainText("Duration");
    await expect(text).not.toContainText("Source duration");
    await expect(text).not.toContainText("Usable");
    await page.locator("#wwOscEligibilityToggle").click();
    const fact = (label) => sections(page).first().locator("dt", { hasText: new RegExp("^" + label + "$") }).locator("xpath=following-sibling::dd");
    await expect(fact("Source duration")).toHaveText("0.648 s");
    await expect(fact("Usable RMS duration")).toHaveText("0.628 s");
    await expect(fact("Analysis window")).toHaveText("0.628 s (Full recording)");
    await expect(fact("Recommended minimum")).toHaveText("≈ 3.2 Hz (2-cycle guideline)");
    await expect(fact("Eligible via RMS magnitude")).toHaveText("1");
    await expect(sections(page).first().locator("dt", { hasText: /^Via RMS magnitude$/ })).toHaveCount(0);
    // A custom sub-window changes only the analysis window.
    await setWindow(page, 0.1, 0.5);
    await expect(fact("Source duration")).toHaveText("0.648 s");
    await expect(fact("Usable RMS duration")).toHaveText("0.628 s");
    await expect(fact("Analysis window")).toHaveText("0.4 s (Custom range)");
  });
});
