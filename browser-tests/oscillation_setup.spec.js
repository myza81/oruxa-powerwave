// Oscillation Analysis -- SETUP / INPUT workflow and the Welch PSD Frequency Spectrum (DEC-174 [PROPOSAL]).
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
    await expect(page.locator("#wwOscillationPanel h3")).toHaveText(["Oscillation Analysis", "Frequency Spectrum (Welch PSD)", "Time-Frequency Spectrogram (STFT)", "Analysis Information", "Data Adequacy"]);
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue("");
    await expect(page.locator("#wwOscStartInput")).toBeDisabled();
    await expect(page.locator("#wwOscMinFreqInput")).toHaveValue("0.1");
    await expect(page.locator("#wwOscMaxFreqInput")).toHaveValue("2");
    await expect(status(page)).toHaveText("Not assessed");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await expect(page.locator("#wwOscInfoSamplingRate")).toHaveText("—");
    // No chart/placeholder surfaces and no result: the spectrum card stays hidden until Analyze.
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
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

  test("Analyze records the validated setup it is tied to and editing the setup invalidates that record", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await setBand(page, 0.5, 2);
    await expect(page.locator("#wwOscAnalyzeNote")).toContainText("Welch power spectral density");
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot .js-plotly-plot, #wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(page.locator("#wwOscillationPanel")).not.toContainText(/dominant/i);
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


// ---------------------------------------------------------------------------
// Frequency Spectrum -- Welch PSD (DEC-174 [PROPOSAL]).
// 20 s / 1 kHz record, FREQ = 0.05 sin(2 pi 0.5 t): with a 0.5-2 Hz band the
// backend picks a 4 s Hann segment (2 / f_min), 50 % overlap, 9 segments,
// 0.25 Hz bin spacing. The tests read the
// returned/plotted arrays directly (candidate detection, DEC-175, is tested separately below).
// ---------------------------------------------------------------------------
const SPECTRUM_URL = "**/oscillation-analysis/spectrum";
const plotData = (page) => page.evaluate(() => {
  const el = document.getElementById("wwOscSpectrumPlot");
  return { traces: el.data.length, x: Array.from(el.data[0].x), y: Array.from(el.data[0].y), layout: el.layout,
           annotations: (el.layout.annotations || []).length, shapes: (el.layout.shapes || []).length };
});
const specDetail = (page, label) => page.locator("#wwOscSpectrumDetails > div", {
  has: page.locator("dt", { hasText: new RegExp("^" + label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$") }),
}).locator("dd");
const axisTitle = (axis) => (typeof axis.title === "string" ? axis.title : axis.title.text);

async function spectrumPage(page, options = {}) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 20, ...options });
  await selectFreq(page);
  await setBand(page, 0.5, 2);
}

test.describe("Oscillation Analysis -- Frequency Spectrum (Welch PSD)", () => {
  test("nothing is computed or drawn until Analyze is pressed", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(r.url()); });
    await spectrumPage(page);
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    expect(requests).toHaveLength(0);
  });

  test("Analyze sends one reference-only request and draws the returned spectrum", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(r.postDataJSON()); });
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumCard")).toBeVisible();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    expect(requests).toHaveLength(1);
    const body = requests[0];
    expect(body.input).toMatchObject({ kind: "source", channel_name: "FREQ" });
    expect(body).toMatchObject({ representation: "native", window_start_s: 0, window_end_s: 20, frequency_min_hz: 0.5, frequency_max_hz: 2 });
    expect(Object.keys(body).sort()).toEqual(["frequency_max_hz", "frequency_min_hz", "input", "representation", "signal_revision", "window_end_s", "window_start_s"]);
    const d = await plotData(page);
    expect(d.traces).toBe(1);
    expect(d.x[0]).toBeGreaterThanOrEqual(0.5 - 1e-9);
    expect(d.x[d.x.length - 1]).toBeLessThanOrEqual(2 + 1e-9);
    expect(d.x).toHaveLength(7); // 0.5 .. 2 Hz at 0.25 Hz spacing
    const peak = d.x[d.y.indexOf(Math.max(...d.y))];
    expect(Math.abs(peak - 0.5)).toBeLessThanOrEqual(0.25);
    expect(axisTitle(d.layout.xaxis)).toBe("Frequency (Hz)");
    expect(axisTitle(d.layout.yaxis)).toBe("PSD (Hz²/Hz)");
    // The 0.5 Hz sine sits on the lower band edge: no candidate marker, no annotation, no strength or
    // statistical wording (DEC-175 [PROPOSAL]: candidates are measured evidence, never a confidence).
    expect(d.annotations).toBe(0);
    expect(d.shapes).toBe(0);
    const text = (await page.locator("#wwOscSpectrumCard").innerText()).toLowerCase();
    for (const word of ["strong", "moderate", "weak", "oscillation present", "stable", "confidence:", "probability"]) expect(text).not.toContain(word);
    await expect(page.locator("#wwOscSpectrumCard h3")).toHaveText("Frequency Spectrum (Welch PSD)");
  });

  test("shows a loading state while the backend computes", async ({ page }) => {
    await spectrumPage(page);
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.route(SPECTRUM_URL, async (route) => { await gate; await route.continue(); });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("Computing Welch PSD…");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(0);
    release();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(page.locator("#wwOscSpectrumState")).toBeHidden();
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeEnabled();
  });

  test("a long recording filename wraps inside its own Analysis details cell", async ({ page }) => {
    const longName = "PCGP Machines_251015_161233304.ben";
    await page.route(SPECTRUM_URL, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.signal.source_recording = longName.replace(/ /g, "_").repeat(3);
      await route.fulfill({ response, json: body });
    });
    await spectrumPage(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    const cell = page.locator("#wwOscSpectrumDetails > div", { has: page.locator("dt", { hasText: /^Recording$/ }) });
    const next = page.locator("#wwOscSpectrumDetails > div", { has: page.locator("dt", { hasText: /^Analysis representation$/ }) });
    await expect(cell.locator("dd")).toHaveText(longName.replace(/ /g, "_").repeat(3));
    const geo = await page.evaluate(() => {
      const rect = (el) => el.getBoundingClientRect();
      const cells = Array.from(document.querySelectorAll("#wwOscSpectrumDetails > div"));
      const rec = cells.find((c) => c.querySelector("dt").textContent === "Recording");
      const dd = rec.querySelector("dd");
      const nextCell = cells[cells.indexOf(rec) + 1];
      return { cell: rect(rec), dd: rect(dd), next: rect(nextCell), scrollW: dd.scrollWidth, clientW: dd.clientWidth };
    });
    expect(geo.dd.right).toBeLessThanOrEqual(geo.cell.right + 0.5);
    expect(geo.scrollW).toBeLessThanOrEqual(geo.clientW + 1);
    expect(geo.dd.height).toBeGreaterThan(20); // wrapped onto more than one line
    const sameRow = Math.abs(geo.next.top - geo.cell.top) < 2;
    if (sameRow) expect(geo.dd.right).toBeLessThanOrEqual(geo.next.left + 0.5);
    await expect(next).toBeVisible();
  });

  test("states the exact parameters used and keeps the two resolution concepts apart", async ({ page }) => {
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(specDetail(page, "Analysis representation")).toHaveText("Signal as recorded");
    await expect(specDetail(page, "Analysis window")).toHaveText("20 s (20001 samples)");
    await expect(specDetail(page, "Basic window estimate (1/T)")).toHaveText("0.05 Hz");
    await expect(specDetail(page, "Welch segment")).toHaveText("4 s (4000 samples)");
    await expect(specDetail(page, "Welch bin spacing (fs/nperseg)")).toHaveText("0.25 Hz");
    await expect(specDetail(page, "Overlap")).toHaveText("50 % (2000 samples)");
    await expect(specDetail(page, "Segments averaged")).toHaveText("9");
    await expect(specDetail(page, "Window")).toHaveText("Hann");
    await expect(specDetail(page, "Detrend")).toHaveText("Mean removed (constant)");
    await expect(specDetail(page, "Scaling")).toHaveText("Power spectral density (one-sided)");
    await expect(specDetail(page, "Requested range")).toHaveText("0.5 to 2 Hz");
    await expect(specDetail(page, "Returned range")).toHaveText("0.5 to 2 Hz (7 bins)");
    // The setup's own figure is still the basic estimate, unchanged.
    await expect(page.locator("#wwOscInfoResolution")).toHaveText("≈ 0.05 Hz");
    await expect(page.locator("#wwOscSpectrumWarnings li")).toHaveCount(0);
  });

  test("a window too short for the lowest frequency reports a single segment honestly", async ({ page }) => {
    await spectrumPage(page);
    await setBand(page, 0.1, 2); // wants 20 s segments: only the 20 s window itself fits
    await setWindow(page, 0, 5);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(specDetail(page, "Segments averaged")).toHaveText("1");
    const warnings = await page.locator("#wwOscSpectrumWarnings li").evaluateAll((l) => l.map((x) => x.dataset.code));
    expect(warnings).toContain("single_segment");
    expect(warnings).toContain("insufficient_window_for_min_frequency");
    await expect(page.locator("#wwOscSpectrumWarnings")).toContainText("no averaging took place");
  });

  test("the PSD axis can be switched to logarithmic without a new request", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(1); });
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    expect((await plotData(page)).layout.yaxis.type).toBe("linear");
    await page.locator("#wwOscSpectrumScale").selectOption("log");
    await expect.poll(async () => (await plotData(page)).layout.yaxis.type).toBe("log");
    expect(requests).toHaveLength(1);
  });

  test("changing the settings after Analyze marks the spectrum as not current until re-run", async ({ page }) => {
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(page.locator("#wwOscSpectrumState")).toBeHidden();
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("Analysis settings changed — run Analyze again");
    await expect(page.locator("#wwOscSpectrumPlot")).toHaveAttribute("data-stale", "true");
    // Reverting the edit makes the shown spectrum current again; re-running replaces it.
    await page.locator("#wwOscMaxFreqInput").fill("2");
    await expect(page.locator("#wwOscSpectrumState")).toBeHidden();
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumState")).toBeHidden();
    await expect(specDetail(page, "Requested range")).toHaveText("0.5 to 3 Hz");
    // The window changing counts too.
    await setWindow(page, 0, 10);
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("Analysis settings changed — run Analyze again");
  });

  test("selecting another signal discards the spectrum", async ({ page }) => {
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.spectrum.result)).toBeNull();
  });

  test("removing the analysed signal invalidates the spectrum", async ({ page }) => {
    await spectrumPage(page);
    const made = await absOf(page, "ABS FREQ", "FREQ");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "ABS FREQ"));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    await expect(page.locator("#wwOscSelectionNotice")).toContainText("selection cleared");
    expect(await page.evaluate(() => wwOscState.spectrum.result)).toBeNull();
  });

  test("a response arriving after the signal was removed is discarded", async ({ page }) => {
    await spectrumPage(page);
    const made = await absOf(page, "ABS FREQ", "FREQ");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "ABS FREQ"));
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.route(SPECTRUM_URL, async (route) => { await gate; await route.continue(); });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("Computing Welch PSD…");
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    release();
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    await page.waitForTimeout(300);
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.spectrum.phase)).toBe("idle");
  });

  test("a backend error is shown, with no chart and no empty spectrum", async ({ page }) => {
    await spectrumPage(page);
    await page.route(SPECTRUM_URL, (route) => route.fulfill({
      status: 422, contentType: "application/json",
      body: JSON.stringify({ detail: { code: "non_finite_samples", message: "The analysis window contains 3 non-finite sample(s)." } }),
    }));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("The analysis window contains 3 non-finite sample(s).");
    await expect(page.locator("#wwOscSpectrumState")).toHaveAttribute("data-kind", "error");
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(0);
    await expect(page.locator("#wwOscSpectrumDetails > div")).toHaveCount(0);
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeEnabled();
  });

  test("an unreachable backend is reported, not left loading", async ({ page }) => {
    await spectrumPage(page);
    await page.route(SPECTRUM_URL, (route) => route.abort());
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumState")).toContainText("Could not reach the backend");
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(0);
  });

  test("raw V/I is analysed through its RMS magnitude and says so", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 10 });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
    await expect(page.locator("#wwOscInfoDerivedCount")).not.toHaveText("—");
    await setBand(page, 0.5, 2);
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(r.postDataJSON()); });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    expect(requests[0].representation).toBe("rms_magnitude");
    expect(requests[0].window_start_s).toBeCloseTo(0.02, 6); // the representation's usable range
    await expect(specDetail(page, "Analysis representation")).toHaveText("RMS magnitude");
    await expect(specDetail(page, "Nominal frequency")).toHaveText("50 Hz (from the recording)");
    expect(axisTitle((await plotData(page)).layout.yaxis)).toBe("PSD (V²/Hz)");
  });

  test("a band reaching the RMS roll-off carries the backend warning", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 10 });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
    await expect(page.locator("#wwOscInfoDerivedCount")).not.toHaveText("—");
    await setBand(page, 0.5, 30);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(page.locator('#wwOscSpectrumWarnings li[data-code="rms_rolloff"]')).toContainText("not corrected");
  });

  test("the spectrum card survives leaving and returning to the page", async ({ page }) => {
    await spectrumPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await page.locator("#wwAnalysisTypePhasorBtn").click();
    await expect(page.locator("#wwOscillationPanel")).toBeHidden();
    await page.locator("#wwAnalysisTypeOscillationBtn").click();
    await expect(page.locator("#wwOscSpectrumCard")).toBeVisible();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    const box = await page.locator("#wwOscSpectrumPlot").boundingBox();
    expect(box.width).toBeGreaterThan(200);
    expect(box.height).toBeGreaterThan(200);
  });
});


// Presentation refinements (same Welch data; no backend change): title, axis labels/units, Line | Histogram.
test.describe("Oscillation Analysis -- Frequency Spectrum presentation", () => {
  const plotType = (page) => page.evaluate(() => document.getElementById("wwOscSpectrumPlot").data[0].type);
  // What Plotly actually RENDERED (not the layout object): the axis-title SVG text nodes, their visibility and
  // that they lie inside the drawn chart (a clipped or missing title fails here).
  const renderedTitles = (page) => page.evaluate(() => {
    const el = document.getElementById("wwOscSpectrumPlot");
    const svg = el.querySelector("svg.main-svg").getBoundingClientRect();
    const read = (selector) => {
      const node = el.querySelector(selector);
      if (!node) return null;
      const box = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return { text: node.textContent, fontSize: getComputedStyle(node).fontSize, visible: style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0,
               inside: box.left >= svg.left - 1 && box.right <= svg.right + 1 && box.top >= svg.top - 1 && box.bottom <= svg.bottom + 1 };
    };
    return { x: read(".xtitle"), y: read(".ytitle"), svgWidth: svg.width, containerWidth: el.getBoundingClientRect().width };
  });
  async function expectVisibleTitles(page, yText) {
    await expect.poll(async () => (await renderedTitles(page)).x && (await renderedTitles(page)).y).toBeTruthy();
    const t = await renderedTitles(page);
    expect(t.x).toMatchObject({ text: "Frequency (Hz)", fontSize: "11px", visible: true, inside: true });
    expect(t.y).toMatchObject({ text: yText, fontSize: "11px", visible: true, inside: true });
    expect(Math.abs(t.svgWidth - t.containerWidth)).toBeLessThanOrEqual(2); // drawn at the container's real width
  }
  async function analysed(page, options = {}) {
    await spectrumPage(page, options);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
  }

  test("title, axis labels and units; Line is the default", async ({ page }) => {
    await analysed(page);
    await expect(page.locator("#wwOscSpectrumCard h3")).toHaveText("Frequency Spectrum (Welch PSD)");
    await expect(page.locator("#wwOscSpectrumDisplay")).toHaveValue("line");
    expect(await plotType(page)).toBe("scatter");
    const d = await plotData(page);
    expect(axisTitle(d.layout.xaxis)).toBe("Frequency (Hz)");
    expect(axisTitle(d.layout.yaxis)).toBe("PSD (Hz²/Hz)");
    await expectVisibleTitles(page, "PSD (Hz²/Hz)");
  });

  test("the Y title follows the backend unit (MW signal)", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 20 });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await setBand(page, 0.5, 2);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    expect(axisTitle((await plotData(page)).layout.yaxis)).toBe("PSD (MW²/Hz)");
    await expectVisibleTitles(page, "PSD (MW²/Hz)");
  });

  test("an unknown unit falls back to plain PSD", async ({ page }) => {
    await spectrumPage(page);
    await page.route(SPECTRUM_URL, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.signal.unit = null; body.signal.psd_unit = null;
      await route.fulfill({ response, json: body });
    });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    expect(axisTitle((await plotData(page)).layout.yaxis)).toBe("PSD");
    await expectVisibleTitles(page, "PSD");
  });

  test("Histogram draws one bar per returned Welch bin, from the same result, with no new request", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(1); });
    await analysed(page);
    const line = await plotData(page);
    const result = await page.evaluate(() => wwOscState.spectrum.result);
    await page.locator("#wwOscSpectrumDisplay").selectOption("bars");
    await expect.poll(() => plotType(page)).toBe("bar");
    const bars = await plotData(page);
    expect(bars.traces).toBe(1);
    expect(bars.x).toEqual(result.frequencies_hz); // no re-binning
    expect(bars.y).toEqual(result.psd); // values untouched
    expect(bars.x).toHaveLength(result.frequency.bin_count);
    const width = await page.evaluate(() => document.getElementById("wwOscSpectrumPlot").data[0].width);
    expect(width).toBeCloseTo(0.9 * result.welch.bin_spacing_hz, 9);
    expect(width).toBeLessThanOrEqual(result.welch.bin_spacing_hz);
    expect(axisTitle(bars.layout.xaxis)).toBe("Frequency (Hz)");
    expect(axisTitle(bars.layout.yaxis)).toBe("PSD (Hz²/Hz)");
    // Back to Line: same arrays as before.
    await page.locator("#wwOscSpectrumDisplay").selectOption("line");
    await expect.poll(() => plotType(page)).toBe("scatter");
    const again = await plotData(page);
    expect(again.x).toEqual(line.x);
    expect(again.y).toEqual(line.y);
    expect(requests).toHaveLength(1);
  });

  test("all four Display x PSD-axis combinations draw, keep labels and unit, and never re-request", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/spectrum")) requests.push(1); });
    await analysed(page);
    for (const display of ["line", "bars"]) {
      for (const scale of ["linear", "log"]) {
        await page.locator("#wwOscSpectrumDisplay").selectOption(display);
        await page.locator("#wwOscSpectrumScale").selectOption(scale);
        await expect.poll(async () => {
          const d = await plotData(page);
          return `${await plotType(page)}|${d.layout.yaxis.type}`;
        }).toBe(`${display === "bars" ? "bar" : "scatter"}|${scale}`);
        const d = await plotData(page);
        expect(axisTitle(d.layout.xaxis)).toBe("Frequency (Hz)");
        expect(axisTitle(d.layout.yaxis)).toBe("PSD (Hz²/Hz)");
        await expectVisibleTitles(page, "PSD (Hz²/Hz)"); // rendered, visible and unclipped in every combination
      }
    }
    expect(requests).toHaveLength(1);
  });

  test("on a log axis non-positive bins become gaps; the stored result is untouched", async ({ page }) => {
    await spectrumPage(page);
    await page.route(SPECTRUM_URL, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.psd[1] = 0;
      await route.fulfill({ response, json: body });
    });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    for (const display of ["line", "bars"]) {
      await page.locator("#wwOscSpectrumDisplay").selectOption(display);
      await page.locator("#wwOscSpectrumScale").selectOption("log");
      await expect.poll(async () => (await plotData(page)).layout.yaxis.type).toBe("log");
      expect((await plotData(page)).y[1]).toBeNull();
    }
    expect(await page.evaluate(() => wwOscState.spectrum.result.psd[1])).toBe(0);
  });

  test("hover shows frequency, PSD and unit in both modes", async ({ page }) => {
    await analysed(page);
    for (const display of ["line", "bars"]) {
      await page.locator("#wwOscSpectrumDisplay").selectOption(display);
      await expect.poll(() => page.evaluate(() => document.getElementById("wwOscSpectrumPlot").data[0].hovertemplate))
        .toBe("Frequency: %{x:.4g} Hz<br>PSD: %{y:.4g} Hz²/Hz<extra></extra>");
    }
  });

  test("stale-settings behaviour is unchanged in Histogram mode", async ({ page }) => {
    await analysed(page);
    await page.locator("#wwOscSpectrumDisplay").selectOption("bars");
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await expect(page.locator("#wwOscSpectrumState")).toHaveText("Analysis settings changed — run Analyze again");
    await expect(page.locator("#wwOscSpectrumPlot")).toHaveAttribute("data-stale", "true");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
  });
});


// ---------------------------------------------------------------------------
// Candidate detection -- "Detected Oscillation Components" (DEC-175 [PROPOSAL]).
// A 1 Hz sine in a 0.25-3 Hz band (20 s window): an interior spectral peak.
// ---------------------------------------------------------------------------
const CANDIDATE_CHANNELS = [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0 }];
async function candidatePage(page) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 20, channels: CANDIDATE_CHANNELS });
  await selectFreq(page);
  await setBand(page, 0.25, 3);
  await page.locator("#wwOscAnalyzeBtn").click();
  await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
}
const traces = (page) => page.evaluate(() => {
  const el = document.getElementById("wwOscSpectrumPlot");
  return el.data.map((t) => ({ role: t.meta && t.meta.role, type: t.type, x: Array.from(t.x), y: Array.from(t.y) }));
});

test.describe("Oscillation Analysis -- candidate detection", () => {
  test("a spectral peak is reported with its evidence and marked on the chart", async ({ page }) => {
    await candidatePage(page);
    const det = page.locator("#wwOscDetection");
    await expect(det).toBeVisible();
    await expect(det.locator(".ww-osc-detect-title")).toHaveText("Detected Oscillation Components");
    const result = await page.evaluate(() => wwOscState.spectrum.result);
    const c = result.detection.candidates[0];
    expect(result.detection.status).toBe("candidates_found");
    expect(Math.abs(c.frequency_hz - 1.0)).toBeLessThanOrEqual(0.125);
    expect(c.cycles_observed).toBeCloseTo(c.frequency_hz * 20, 1);
    const primary = page.locator("#wwOscDetectionPrimary");
    await expect(primary).toContainText("Frequency");
    await expect(primary).toContainText("Period");
    await expect(primary).toContainText("Prominence");
    await expect(primary).toContainText("Cycles observed");
    // "Why" is the backend's measured evidence, one line per condition.
    const why = await det.locator('li[data-kind="why"]').allInnerTexts();
    expect(why.length).toBeGreaterThanOrEqual(4);
    expect(why.join(" ")).toMatch(/dB above the surrounding spectral level/);
    expect(why.join(" ")).toMatch(/cycles observed/);
    const text = (await det.innerText()).toLowerCase();
    for (const word of ["confidence:", "probability", "strong candidate", "weak candidate", "inter-area", "forced"]) expect(text).not.toContain(word);
    // The marker is an overlay trace; the PSD trace itself is the unchanged returned spectrum.
    const t = await traces(page);
    expect(t.map((x) => x.role)).toEqual(["welch-psd", "oscillation-candidates"]);
    expect(t[0].y).toEqual(result.psd);
    expect(t[1].x).toEqual(result.detection.candidates.map((x) => x.frequency_hz));
    expect(t[1].y).toEqual(result.detection.candidates.map((x) => x.psd));
  });

  test("markers survive every Line/Histogram x Linear/Logarithmic combination without changing the PSD", async ({ page }) => {
    await candidatePage(page);
    const result = await page.evaluate(() => wwOscState.spectrum.result);
    for (const display of ["line", "bars"]) {
      for (const scale of ["linear", "log"]) {
        await page.locator("#wwOscSpectrumDisplay").selectOption(display);
        await page.locator("#wwOscSpectrumScale").selectOption(scale);
        const t = await traces(page);
        expect(t.map((x) => x.role), display + "/" + scale).toEqual(["welch-psd", "oscillation-candidates"]);
        expect(t[0].type).toBe(display === "bars" ? "bar" : "scatter");
        expect(t[0].y.filter((v) => v !== null)).toEqual(result.psd.filter((v) => scale === "linear" || v > 0));
        expect(t[1].y).toEqual(result.detection.candidates.map((x) => x.psd));
        await expect(page.locator("#wwOscDetection")).toBeVisible();
      }
    }
    expect(await page.evaluate(() => document.getElementById("wwOscSpectrumPlot").layout.annotations || [])).toHaveLength(0);
  });

  test("no candidate is a result with an explanation, not an error", async ({ page }) => {
    await spectrumPage(page); // the 0.5 Hz sine lies on the lower edge of the 0.5-2 Hz band
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    const det = page.locator("#wwOscDetection");
    await expect(det.locator(".ww-osc-detect-none")).toHaveText("No significant oscillation candidate detected");
    await expect(det).toContainText("edge");
    await expect(page.locator("#wwOscSpectrumState")).toBeHidden();
    const t = await traces(page);
    expect(t.map((x) => x.role)).toEqual(["welch-psd"]);
  });

  test("candidates follow the spectrum's stale and discard behaviour", async ({ page }) => {
    await candidatePage(page);
    await expect(page.locator("#wwOscDetection")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscMaxFreqInput").fill("4");
    await expect(page.locator("#wwOscDetection")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscSpectrumPlot")).toHaveAttribute("data-stale", "true");
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await expect(page.locator("#wwOscDetection")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscMaxFreqInput").fill("4");
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscDetection")).toHaveAttribute("data-stale", "false");
    expect(await page.evaluate(() => wwOscState.spectrum.result.frequency.requested_max_hz)).toBe(4);
    // A different signal discards the spectrum together with its candidates.
    await page.locator("#wwOscSignalSelect").selectOption("");
    await expect(page.locator("#wwOscSpectrumCard")).toBeHidden();
    await expect(page.locator("#wwOscDetection")).toBeHidden();
    await expect(page.locator("#wwOscDetection")).toBeEmpty();
  });
});


// ---------------------------------------------------------------------------
// Time-Frequency Spectrogram (STFT, DEC-176 [APPROVED]).
// Same Analyze press as the spectrum. Fixture: 40 s / 1 kHz FREQ record with a 1 Hz
// component that only appears after t = 20 s; band 0.25-3 Hz -> an 8 s Hann window,
// 50 % overlap (4 s hop), 9 slices, 0.125 Hz row spacing. Tests read the plotted
// matrix; Plotly internals beyond "a heatmap is rendered" are not asserted.
// ---------------------------------------------------------------------------
const SPECTROGRAM_URL = "**/oscillation-analysis/spectrogram";
const ONSET_CHANNELS = [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 20 },
  { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 }];
const gramPlot = "#wwOscSpectrogramPlot";
const gramData = (page) => page.evaluate(() => {
  const el = document.getElementById("wwOscSpectrogramPlot");
  return { traces: el.data.map((t) => ({ role: t.meta && t.meta.role, type: t.type, x: Array.from(t.x), y: Array.from(t.y),
                                          width: t.line && t.line.width, colorbar: t.colorbar && t.colorbar.title && t.colorbar.title.text })),
           z: el.data[0].z.map((row) => Array.from(row)), zmin: el.data[0].zmin, zmax: el.data[0].zmax, layout: el.layout };
});
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const gramDetail = (page, label) => page.locator("#wwOscSpectrogramDetails > div", {
  has: page.locator("dt", { hasText: new RegExp("^" + escapeRegExp(label) + "$") }),
}).locator("dd");

async function spectrogramPage(page, options = {}) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 40, channels: ONSET_CHANNELS, ...options });
  await selectFreq(page);
  await setBand(page, 0.25, 3);
}
async function spectrogramAnalysed(page, options = {}) {
  await spectrogramPage(page, options);
  await page.locator("#wwOscAnalyzeBtn").click();
  await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(1);
  await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
}

test.describe("Oscillation Analysis -- Time-Frequency Spectrogram (STFT)", () => {
  test("hidden until Analyze; then a heatmap card sits below the spectrum with labelled axes and colour bar", async ({ page }) => {
    await spectrogramPage(page);
    await expect(page.locator("#wwOscSpectrogramCard")).toBeHidden();
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrogramCard")).toBeVisible();
    await expect(page.locator("#wwOscSpectrogramCard h3")).toHaveText("Time-Frequency Spectrogram (STFT)");
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(1);
    // order: Welch spectrum card, then the spectrogram card, then Analysis Information
    const order = await page.evaluate(() => Array.from(document.querySelectorAll("#wwOscillationPanel section.ww-osc-card h3")).map((h) => h.textContent));
    expect(order.indexOf("Frequency Spectrum (Welch PSD)")).toBeLessThan(order.indexOf("Time-Frequency Spectrogram (STFT)"));
    expect(order.indexOf("Time-Frequency Spectrogram (STFT)")).toBeLessThan(order.indexOf("Analysis Information"));
    const d = await gramData(page);
    expect(d.traces[0]).toMatchObject({ role: "stft-spectrogram", type: "heatmap" });
    expect(d.traces[0].colorbar).toBe("PSD (dB re 1 Hz²/Hz)");
    const title = (axis) => (typeof axis.title === "string" ? axis.title : axis.title.text);
    expect(title(d.layout.xaxis)).toBe("Time (s)");
    expect(title(d.layout.yaxis)).toBe("Frequency (Hz)");
    // The heatmap is actually rendered and the axis titles/colour bar are visible, inside the figure.
    const rendered = await page.evaluate(() => {
      const el = document.getElementById("wwOscSpectrogramPlot");
      const svg = el.querySelector("svg.main-svg").getBoundingClientRect();
      const box = (sel) => {
        const n = el.querySelector(sel);
        if (!n) return null;
        const b = n.getBoundingClientRect();
        return { w: b.width, h: b.height, inside: b.left >= svg.left - 1 && b.right <= svg.right + 1 && b.top >= svg.top - 1 && b.bottom <= svg.bottom + 1,
                 text: n.textContent, font: getComputedStyle(n).fontSize };
      };
      return { image: !!el.querySelector(".heatmaplayer image, .heatmaplayer canvas, .hm image"), x: box(".xtitle"), y: box(".ytitle"),
               bar: box(".colorbar"), barTitle: box(".cbtitle") };
    });
    expect(rendered.image).toBe(true);
    expect(rendered.x).toMatchObject({ text: "Time (s)", font: "11px", inside: true });
    expect(rendered.y).toMatchObject({ text: "Frequency (Hz)", font: "11px", inside: true });
    expect(rendered.bar.w).toBeGreaterThan(5);
    expect(rendered.barTitle.text).toBe("PSD (dB re 1 Hz²/Hz)");
  });

  test("one reference-only request, same identity fields as the spectrum; the spectrum is still drawn", async ({ page }) => {
    const gram = [], spec = [];
    page.on("request", (r) => {
      if (r.url().endsWith("/oscillation-analysis/spectrogram")) gram.push(r.postDataJSON());
      if (r.url().endsWith("/oscillation-analysis/spectrum")) spec.push(r.postDataJSON());
    });
    await spectrogramAnalysed(page);
    expect(gram).toHaveLength(1);
    expect(spec).toHaveLength(1);
    expect(gram[0]).toEqual(spec[0]);
    expect(Object.keys(gram[0]).sort()).toEqual(["frequency_max_hz", "frequency_min_hz", "input", "representation", "signal_revision", "window_end_s", "window_start_s"]);
  });

  test("the matrix shows the component only after its onset, on one global dB range", async ({ page }) => {
    await spectrogramAnalysed(page);
    const d = await gramData(page);
    const result = await page.evaluate(() => wwOscState.spectrogram.result);
    expect(result.stft).toMatchObject({ slice_count: 9, time_stamp: "window_centre" });
    // fs is derived from the record's microsecond time stamps, so the figures are exact only to ~1e-6.
    expect(result.stft.window_s).toBeCloseTo(8, 4);
    expect(result.stft.hop_s).toBeCloseTo(4, 4);
    expect(result.stft.bin_spacing_hz).toBeCloseTo(0.125, 5);
    expect(d.z).toHaveLength(result.matrix.rows);
    expect(d.z[0]).toHaveLength(9);
    const ys = d.traces[0].y;
    const row = ys.reduce((best, f, i) => (Math.abs(f - 1.0) < Math.abs(ys[best] - 1.0) ? i : best), 0);
    const x = d.traces[0].x;
    const before = d.z[row].filter((_, i) => x[i] < 16), after = d.z[row].filter((_, i) => x[i] > 28);
    expect(Math.min(...after) - Math.max(...before)).toBeGreaterThan(30); // dB
    // global range: zmax is the matrix maximum, zmin is rangeDb below it (60 by default), no per-slice normalisation
    expect(d.zmax).toBeCloseTo(Math.max(...d.z.flat()), 6);
    expect(d.zmax - d.zmin).toBeCloseTo(60, 6);
    // the backend value is linear PSD and is the thing converted: 10 log10
    expect(d.zmax).toBeCloseTo(10 * Math.log10(Math.max(...result.psd.flat())), 6);
  });

  test("accepted spectrum candidates become guide lines, the primary more prominent", async ({ page }) => {
    await spectrogramAnalysed(page, { channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0 }] });
    const cands = await page.evaluate(() => wwOscState.spectrum.result.detection.candidates);
    expect(cands.length).toBeGreaterThan(0);
    const d = await gramData(page);
    const guides = d.traces.filter((t) => t.role === "spectrogram-candidate");
    expect(guides).toHaveLength(cands.length);
    expect(guides.map((g) => g.y[0])).toEqual(cands.map((c) => c.frequency_hz));
    if (guides.length > 1) expect(guides[0].width).toBeGreaterThan(guides[1].width);
    // no second detector: the spectrogram result carries no detection block
    expect(await page.evaluate(() => "detection" in wwOscState.spectrogram.result)).toBe(false);
  });

  test("a workspace t=0 adds one vertical guide inside the window and shifts the time axis", async ({ page }) => {
    await spectrogramAnalysed(page);
    expect((await gramData(page)).layout.shapes || []).toHaveLength(0);
    const before = (await gramData(page)).traces[0].x[0];
    const groupId = await page.evaluate(() => wwTimeGroupIdForDisplaySourceId(Array.from(ww.sourceChannelsData.keys())[0]));
    await page.evaluate((id) => { ww.timeGroupT0State.set(id, 20); wwOscRender(); }, groupId);
    await expect.poll(async () => ((await gramData(page)).layout.shapes || []).length).toBe(1);
    const d = await gramData(page);
    expect(d.layout.shapes[0]).toMatchObject({ name: "event-origin", x0: 0, x1: 0 });
    expect(d.traces[0].x[0]).toBeCloseTo(before - 20, 9);
    expect(await page.evaluate(() => wwOscState.spectrogram.request.startSource)).toBe(0); // the stored window is unchanged
    await page.evaluate((id) => { ww.timeGroupT0State.delete(id); wwOscRender(); }, groupId);
    await expect.poll(async () => ((await gramData(page)).layout.shapes || []).length).toBe(0);
  });

  test("details state the actual time-frequency resolution", async ({ page }) => {
    await spectrogramAnalysed(page);
    await expect(gramDetail(page, "STFT window")).toHaveText("8 s (8000 samples)");
    await expect(gramDetail(page, "Time step (hop)")).toHaveText("4 s (4000 samples)");
    await expect(gramDetail(page, "Overlap")).toHaveText("50 % (4000 samples)");
    await expect(gramDetail(page, "Time slices")).toHaveText("9");
    await expect(gramDetail(page, "Frequency-row spacing (fs/nperseg)")).toHaveText("0.125 Hz");
    await expect(gramDetail(page, "Column time stamp")).toHaveText("Centre of each STFT window");
    await expect(gramDetail(page, "Time axis")).toHaveText("Workspace elapsed time (seconds)");
    await expect(gramDetail(page, "Requested range")).toHaveText("0.25 to 3 Hz");
  });

  test("the dynamic-range control redraws the stored result with no request", async ({ page }) => {
    const gram = [];
    page.on("request", (r) => { if (r.url().includes("/oscillation-analysis/spectrogram")) gram.push(1); });
    await spectrogramAnalysed(page);
    await page.locator("#wwOscSpectrogramRange").selectOption("100");
    await expect.poll(async () => { const d = await gramData(page); return Math.round(d.zmax - d.zmin); }).toBe(100);
    expect(gram).toHaveLength(1);
  });

  test("changing the settings marks the spectrogram not current until re-run; reverting restores it", async ({ page }) => {
    await spectrogramAnalysed(page);
    await expect(page.locator("#wwOscSpectrogramState")).toBeHidden();
    await page.locator("#wwOscMaxFreqInput").fill("2.5");
    await expect(page.locator("#wwOscSpectrogramState")).toHaveText("Analysis settings changed — run Analyze again");
    await expect(page.locator(gramPlot)).toHaveAttribute("data-stale", "true");
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await expect(page.locator("#wwOscSpectrogramState")).toBeHidden();
    await expect(page.locator(gramPlot)).toHaveAttribute("data-stale", "false");
    await setWindow(page, 0, 30);
    await expect(page.locator("#wwOscSpectrogramState")).toHaveText("Analysis settings changed — run Analyze again");
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrogramState")).toBeHidden();
    await expect(gramDetail(page, "Analysis window")).toHaveText("30 s (30001 samples)");
  });

  test("selecting another signal, or removing the analysed one, discards the spectrogram", async ({ page }) => {
    await spectrogramAnalysed(page);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscSpectrogramCard")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.spectrogram.result)).toBeNull();
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "FREQ"));
    const made = await absOf(page, "ABS FREQ", "FREQ");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "ABS FREQ"));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(1);
    await page.evaluate((id) => wwCcDeleteChannel(id), made.id);
    await expect(page.locator("#wwOscSpectrogramCard")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.spectrogram.result)).toBeNull();
  });

  test("a response arriving after the signal changed is discarded", async ({ page }) => {
    await spectrogramPage(page);
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.route(SPECTROGRAM_URL, async (route) => { await gate; await route.continue(); });
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrogramState")).toHaveText("Computing STFT spectrogram…");
    await expect(page.locator("#wwOscAnalyzeBtn")).toBeDisabled();
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    release();
    await page.waitForTimeout(500);
    await expect(page.locator("#wwOscSpectrogramCard")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.spectrogram.result)).toBeNull();
  });

  test("a window too short is an explained unavailable state; the spectrum and its card stay", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 3, channels: ONSET_CHANNELS });
    await selectFreq(page);
    await setBand(page, 0.5, 2);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    const state = page.locator("#wwOscSpectrogramState");
    await expect(state).toContainText("too short to provide useful time-frequency resolution");
    await expect(state).toContainText("Frequency Spectrum remains available");
    await expect(state).toHaveAttribute("data-kind", "unavailable");
    await expect(page.locator(gramPlot)).toBeHidden();
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(0);
    expect(await page.evaluate(() => wwOscState.spectrogram.result.status)).toBe("unavailable");
    await expect(page.locator("#wwOscSpectrumCard")).toBeVisible();
  });

  test("raw voltage is shown through its RMS magnitude and says so", async ({ page }) => {
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 40, channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 }] });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
    await setBand(page, 0.25, 3);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(1);
    await expect(gramDetail(page, "Analysis representation")).toHaveText("RMS magnitude");
    expect((await gramData(page)).traces[0].colorbar).toBe("PSD (dB re 1 V²/Hz)");
    expect(await page.evaluate(() => wwOscState.spectrogram.request.representation)).toBe("rms_magnitude");
  });

  test("an unknown unit degrades gracefully in the colour-bar title", async ({ page }) => {
    await spectrogramAnalysed(page, { channels: [{ name: "FREQ", unit: "", amplitude: 0.05, frequencyHz: 1.0, onsetS: 20 }] });
    expect((await gramData(page)).traces[0].colorbar).toBe("PSD (dB re 1 (signal unit)²/Hz)");
  });

  test("a backend error is shown with no chart", async ({ page }) => {
    await spectrogramPage(page);
    await page.route(SPECTROGRAM_URL, (route) => route.fulfill({
      status: 422, contentType: "application/json", body: JSON.stringify({ detail: { code: "non_finite_samples", message: "The window contains gaps." } }),
    }));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrogramState")).toHaveText("The window contains gaps.");
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(0);
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
  });

  test("a shortened window states the trade-off and the hint to raise the minimum frequency", async ({ page }) => {
    await spectrogramAnalysed(page, { durationS: 20, channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 10 }] }); // wants 8 s (2 / 0.25 Hz); 8 slices need <= ~4.4 s
    const warning = page.locator('#wwOscSpectrogramWarnings li[data-code="window_shortened_for_time_resolution"]');
    await expect(warning).toContainText("shorter than the 8 s wanted");
    await expect(warning).toContainText("For better time resolution, raise the minimum analysis frequency when lower-frequency components are not required.");
  });

  test("peak-hold row reduction under the payload cap is disclosed in the warnings and the details", async ({ page }) => {
    // 4 kHz x 40 s, band 0.25-1999 Hz: 15 993 rows x 9 slices exceeds 120 000 cells -> reduced 2x.
    await openOscillation(page);
    await uploadSynthetic(page, { rateHz: 4000, durationS: 40, channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 20 }] });
    await selectFreq(page);
    await setBand(page, 0.25, 1999);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator(gramPlot + ".js-plotly-plot")).toHaveCount(1);
    const warning = page.locator('#wwOscSpectrogramWarnings li[data-code="frequency_rows_reduced"]');
    await expect(warning).toContainText("Display frequency rows reduced 2× using peak-hold");
    await expect(warning).toContainText("narrow the frequency band for full resolution");
    await expect(gramDetail(page, "Row reduction")).toContainText("peak-hold of 2 adjacent rows");
    const m = await page.evaluate(() => wwOscState.spectrogram.result.matrix);
    expect(m.cells).toBeLessThanOrEqual(120000);
    expect(m.columns).toBe(9); // the time axis is never reduced
  });

  test("renders at phone width without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await spectrogramAnalysed(page);
    const m = await page.evaluate(() => {
      const el = document.getElementById("wwOscSpectrogramPlot");
      const card = document.getElementById("wwOscSpectrogramCard").getBoundingClientRect();
      const svg = el.querySelector("svg.main-svg").getBoundingClientRect();
      return { svg: svg.width, container: el.getBoundingClientRect().width, cardRight: card.right, viewport: window.innerWidth,
               scroll: document.documentElement.scrollWidth };
    });
    expect(Math.abs(m.svg - m.container)).toBeLessThanOrEqual(2);
    expect(m.cardRight).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});

// ---------------------------------------------------------------------------
// Damping behaviour (DEC-177 [APPROVED]). The BACKEND estimates, for the spectrum's accepted candidates, whether each
// component decays / is approximately sustained / grows (zero-phase band envelope, exponential fit). The page requests it
// once the spectrum is ready and draws the returned values and evidence. Fixture: 60 s at 1 kHz, a 1 Hz ringdown starting at
// 10 s with decay rate alpha = 0.15 1/s (zeta = alpha / sqrt(alpha^2 + (2 pi 1)^2) = 2.39 %).
// ---------------------------------------------------------------------------
const DAMPING_URL = "**/oscillation-analysis/damping";
const ALPHA = 0.15;
const ZETA = ALPHA / Math.hypot(ALPHA, 2 * Math.PI * 1.0);
const RINGDOWN_CHANNELS = [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 10, decayPerS: ALPHA },
  { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 }];
const dampPlot = "#wwOscDampingPlot";
const dampRows = (page) => page.evaluate(() => Object.fromEntries(
  Array.from(document.querySelectorAll("#wwOscDampingRows > div")).map((d) => [d.querySelector("dt").textContent, d.querySelector("dd").textContent])));
const dampData = (page) => page.evaluate(() => {
  const el = document.getElementById("wwOscDampingPlot");
  return { traces: el.data.map((t) => ({ role: t.meta && t.meta.role, x: Array.from(t.x), y: Array.from(t.y) })), layout: el.layout };
});

async function dampingPage(page, options = {}) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 60, channels: RINGDOWN_CHANNELS, ...options });
  await selectFreq(page);
  await setBand(page, 0.25, 3);
}
async function dampingAnalysed(page, options = {}) {
  await dampingPage(page, options);
  await page.locator("#wwOscAnalyzeBtn").click();
  await expect(page.locator("#wwOscDampingRows")).toBeVisible();
}

test.describe("Oscillation Analysis -- damping behaviour", () => {
  test("hidden until Analyze; then the decaying component is reported with its evidence", async ({ page }) => {
    await dampingPage(page);
    await expect(page.locator("#wwOscDamping")).toBeHidden();
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscDampingRows")).toBeVisible();
    await expect(page.locator("#wwOscDamping .ww-osc-detect-title")).toHaveText("Damping behaviour");
    const rows = await dampRows(page);
    expect(rows["Damping behaviour"]).toBe("Decaying");
    await expect(page.locator("#wwOscDampingPickWrap")).toBeHidden(); // one candidate: nothing to pick
    const zeta = parseFloat(rows["Estimated damping ratio (ζ)"]);
    expect(rows["Estimated damping ratio (ζ)"]).toMatch(/ %$/);
    expect(Math.abs(zeta / 100 - ZETA) / ZETA).toBeLessThan(0.1); // 10 % tolerance on the injected damping ratio
    expect(rows["Decay rate (α)"]).toMatch(/ s⁻¹$/);
    expect(Math.abs(parseFloat(rows["Decay rate (α)"]) - ALPHA) / ALPHA).toBeLessThan(0.1);
    expect(rows["Fit interval"]).toMatch(/^\d+(\.\d+)? – \d+(\.\d+)? s \(/);
    expect(parseFloat(rows["Cycles used"])).toBeGreaterThanOrEqual(4);
    expect(rows["Fit quality"]).toMatch(/^R² (0\.\d+|1) · envelope scatter/);
    expect(rows["Envelope change"]).toMatch(/^-\d+(\.\d+)? % \(/);
    expect(rows["Spectral candidate"]).toMatch(/ Hz$/);
    const why = await page.locator('#wwOscDamping li[data-kind="why"]').allInnerTexts();
    expect(why.join(" ")).toMatch(/cycles of .* Hz were used/);
    expect(why.join(" ")).toMatch(/Oscillation envelope decreased by \d+ % over/);
    expect(why.join(" ")).toMatch(/Estimated decay rate = .* s⁻¹/);
    // the stored figures are exactly what the backend returned (the page derives nothing)
    const r = await page.evaluate(() => wwOscState.damping.result.results[0]);
    expect(r.status).toBe("available");
    expect(rows["Decay rate (α)"]).toBe(String(Number(r.decay_rate_per_s.toPrecision(3))) + " s⁻¹");
    // no strength / adequacy / oscillation-type wording
    const text = (await page.locator("#wwOscDamping").innerText()).toLowerCase();
    for (const word of ["well damped", "poorly damped", "unstable", "inter-area", "sso", "forced", "confidence"]) expect(text).not.toContain(word);
    await expect(page.locator("#wwOscDampingNote")).toContainText("α > 0 decays");
  });

  test("the Why interval and the Fit interval row are the same interval on the same time basis, with and without a Time Group t=0", async ({ page }) => {
    // Regression (owner UAT): Why said 28.16-42.93 s while the row said 36.36-51.13 s (source time vs event time).
    await dampingAnalysed(page);
    const numbers = (text) => (text.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
    const check = async () => {
      const row = numbers((await dampRows(page))["Fit interval"]).slice(0, 2);
      const why = await page.locator('#wwOscDamping li[data-kind="why"]').allInnerTexts();
      const active = why.find((w) => /above the background noise from/.test(w)), used = why.find((w) => /^Exponential damping fit used/.test(w));
      expect(active, why.join(" | ")).toBeTruthy();
      expect(used).toBeTruthy();
      expect(numbers(active.split(" from ")[1]).slice(0, 2)).toEqual(row);
      expect(numbers(used.replace("Exponential damping fit used", "")).slice(0, 2)).toEqual(row);
      return row;
    };
    const plain = await check();
    const groupId = await page.evaluate(() => wwTimeGroupIdForDisplaySourceId(Array.from(ww.sourceChannelsData.keys())[0]));
    await page.evaluate((id) => { ww.timeGroupT0State.set(id, 8.2); wwOscRender(); }, groupId);
    await expect.poll(async () => (await check())[0]).toBeCloseTo(plain[0] - 8.2, 1);
    const shifted = await check();
    expect(shifted[1]).toBeCloseTo(plain[1] - 8.2, 1);
    // the numbers on the wire are source time and unchanged
    const fit = await page.evaluate(() => wwOscState.damping.result.results[0].fit);
    expect(fit.start_s).toBeCloseTo(plain[0], 1);
  });

  test("the evidence plot shows the envelope, the fitted exponential and the fit interval with labelled axes", async ({ page }) => {
    await dampingAnalysed(page);
    await expect(page.locator(dampPlot + ".js-plotly-plot")).toHaveCount(1);
    const d = await dampData(page);
    expect(d.traces.map((t) => t.role)).toEqual(["damping-envelope", "damping-fit"]);
    const title = (axis) => (typeof axis.title === "string" ? axis.title : axis.title.text);
    expect(title(d.layout.xaxis)).toBe("Time (s)");
    expect(title(d.layout.yaxis)).toBe("Envelope amplitude (Hz)");
    expect(d.layout.yaxis.type).toBe("log");
    const fitted = d.traces[1].y.filter((v) => v !== null);
    expect(fitted.length).toBeGreaterThan(5);
    expect(fitted[0]).toBeGreaterThan(fitted[fitted.length - 1]); // decaying
    const shape = d.layout.shapes.find((s) => s.name === "fit-interval");
    expect(shape).toBeTruthy();
    const fit = await page.evaluate(() => wwOscState.damping.result.results[0].fit);
    expect(shape.x0).toBeCloseTo(fit.start_s, 6);
    expect(shape.x1).toBeCloseTo(fit.end_s, 6);
    expect(fit.start_s).toBeGreaterThan(10); // starts after the onset: not assumed to be t = 0 or the onset
  });

  test("one request, after the spectrum, with the spectrum's identity and its candidate frequencies", async ({ page }) => {
    const damp = [], spec = [];
    page.on("request", (r) => {
      if (r.url().endsWith("/oscillation-analysis/damping")) damp.push(r.postDataJSON());
      if (r.url().endsWith("/oscillation-analysis/spectrum")) spec.push(r.postDataJSON());
    });
    await dampingAnalysed(page);
    expect(spec).toHaveLength(1);
    expect(damp).toHaveLength(1);
    const { candidate_frequencies_hz: freqs, ...identity } = damp[0];
    expect(identity).toEqual(spec[0]);
    const candidates = await page.evaluate(() => wwOscState.spectrum.result.detection.candidates.map((c) => c.frequency_hz));
    expect(freqs).toEqual(candidates);
  });

  test("no candidate means no damping request and no damping section", async ({ page }) => {
    let requests = 0;
    page.on("request", (r) => { if (r.url().endsWith("/oscillation-analysis/damping")) requests += 1; });
    await openOscillation(page);
    await uploadSynthetic(page);
    await selectFreq(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(page.locator("#wwOscDetection .ww-osc-detect-none")).toBeVisible();
    await expect(page.locator("#wwOscDamping")).toBeHidden();
    expect(requests).toBe(0);
  });

  test("a sustained component is reported as approximately sustained with no damping ratio", async ({ page }) => {
    await dampingAnalysed(page, { channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 10 },
      { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 }] });
    const rows = await dampRows(page);
    expect(rows["Damping behaviour"]).toBe("Approximately sustained");
    expect(rows["Damping ratio"]).toBe("Not reported (not a ringdown decay)");
    expect(rows["Estimated damping ratio (ζ)"]).toBeUndefined();
    expect(Math.abs(parseFloat(rows["Decay rate (α)"]))).toBeLessThan(0.02);
  });

  test("a growing component is reported as growing with its growth rate", async ({ page }) => {
    await dampingAnalysed(page, { channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 1.0, onsetS: 5, decayPerS: -0.03 },
      { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 }] });
    const rows = await dampRows(page);
    expect(rows["Damping behaviour"]).toBe("Growing");
    expect(Math.abs(parseFloat(rows["Growth rate"]) - 0.03) / 0.03).toBeLessThan(0.15);
    expect(rows["Damping ratio"]).toBe("Not reported (not a ringdown decay)");
  });

  test("not enough ringdown in the window is an explained unavailable estimate; the candidate stays", async ({ page }) => {
    await dampingPage(page);
    await setWindow(page, 0, 20);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscDampingBody")).toContainText("Damping estimate unavailable");
    await expect(page.locator("#wwOscDampingRows")).toHaveCount(0);
    await expect(page.locator("#wwOscDampingBody")).toContainText("cycles");
    await expect(page.locator("#wwOscDetectionPrimary")).toContainText("Frequency"); // the candidate itself is untouched
    const r = await page.evaluate(() => wwOscState.damping.result.results[0]);
    expect(r.status).toBe("insufficient_evidence");
    expect(r.damping_ratio).toBeNull();
    expect(r.reasons.length).toBeGreaterThan(0);
  });

  test("changing the settings marks the damping not current; reverting restores it", async ({ page }) => {
    await dampingAnalysed(page);
    await expect(page.locator("#wwOscDamping")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscMaxFreqInput").fill("2.5");
    await expect(page.locator("#wwOscDamping")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscDampingState")).toHaveText("Analysis settings changed — run Analyze again");
    await page.locator("#wwOscMaxFreqInput").fill("3");
    await expect(page.locator("#wwOscDamping")).toHaveAttribute("data-stale", "false");
    await expect(page.locator("#wwOscDampingRows")).toBeVisible();
  });

  test("selecting another signal discards the damping result; it is never resurrected", async ({ page }) => {
    await dampingAnalysed(page);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscDamping")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.damping.result)).toBeNull();
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "FREQ"));
    await expect(page.locator("#wwOscDamping")).toBeHidden();
  });

  test("a response arriving after the spectrum was cleared is discarded", async ({ page }) => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    await page.route(DAMPING_URL, async (route) => { await gate; await route.continue(); });
    await dampingPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscDampingState")).toHaveText("Estimating damping behaviour…");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    release();
    await page.waitForTimeout(500);
    await expect(page.locator("#wwOscDamping")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.damping.result)).toBeNull();
  });

  test("a backend error is shown with no figures", async ({ page }) => {
    await page.route(DAMPING_URL, (route) => route.fulfill({ status: 409, contentType: "application/json",
      body: JSON.stringify({ detail: { code: "candidate_mismatch", message: "A candidate no longer matches." } }) }));
    await dampingPage(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscDampingState")).toHaveText("A candidate no longer matches.");
    await expect(page.locator("#wwOscDampingRows")).toHaveCount(0);
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1); // the spectrum is unaffected
  });

  test("two components get independent results and can be inspected one at a time", async ({ page }) => {
    const components = [{ amplitude: 0.05, frequencyHz: 1.0, onsetS: 10, decayPerS: 0.15 },
      { amplitude: 0.025, frequencyHz: 2.6, onsetS: 10, decayPerS: 0.08 }];
    await dampingAnalysed(page, { channels: [{ name: "FREQ", unit: "Hz", amplitude: 0.075, components }, { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 }] });
    const result = await page.evaluate(() => wwOscState.damping.result.results.map((r) => ({
      f: r.candidate_frequency_hz, status: r.status, alpha: r.decay_rate_per_s, fit: r.fit && r.fit.start_s })));
    expect(result).toHaveLength(2);
    expect(result.every((r) => r.status === "available")).toBe(true);
    const low = result.find((r) => Math.abs(r.f - 1.0) < 0.15), high = result.find((r) => Math.abs(r.f - 2.6) < 0.2);
    expect(Math.abs(low.alpha - 0.15) / 0.15).toBeLessThan(0.15);
    expect(Math.abs(high.alpha - 0.08) / 0.08).toBeLessThan(0.2);
    await expect(page.locator("#wwOscDampingAll li")).toHaveCount(2);
    await expect(page.locator("#wwOscDampingPickWrap")).toBeVisible();
    const before = (await dampData(page)).traces[0].y;
    await page.locator("#wwOscDampingPick").selectOption({ index: 1 });
    await expect(page.locator("#wwOscDampingBody .ww-osc-detect-label").first()).toContainText("Candidate 2");
    expect((await dampData(page)).traces[0].y).not.toEqual(before);
  });

  test("renders at phone width without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await dampingAnalysed(page);
    await expect(page.locator(dampPlot + ".js-plotly-plot")).toHaveCount(1);
    const m = await page.evaluate(() => {
      const el = document.getElementById("wwOscDampingPlot");
      const svg = el.querySelector("svg.main-svg").getBoundingClientRect();
      return { svg: svg.width, container: el.getBoundingClientRect().width, right: document.getElementById("wwOscDamping").getBoundingClientRect().right,
               viewport: window.innerWidth, scroll: document.documentElement.scrollWidth };
    });
    expect(Math.abs(m.svg - m.container)).toBeLessThanOrEqual(2);
    expect(m.right).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});

// ---------------------------------------------------------------------------
// Cross-Signal Oscillation Evidence (DEC-178 [APPROVED]). The owner's real-event pattern on a synthetic record: a 4.95 Hz
// ringdown in BOTH the frequency and the MW signal, and a 1.15 Hz one in MW only. The comparison is requested only by the
// Compare button, for the analysed signal plus the explicitly ticked ones; the page draws the backend's grouping. (Since DEC-179 the
// grouping comes from the interpretation endpoint -- a superset of the evidence; Analyze also requests the analysed signal ALONE.)
// ---------------------------------------------------------------------------
const CROSS_URL = "**/oscillation-analysis/interpretation";
const isInterpretation = (r) => r.url().endsWith("/oscillation-analysis/interpretation");
const CROSS_CHANNELS = [
  { name: "FREQ", unit: "Hz", amplitude: 0.075, components: [{ amplitude: 0.05, frequencyHz: 4.95, onsetS: 10, decayPerS: 0.15 }, { amplitude: 0.025, frequencyHz: 7.3, onsetS: 10, decayPerS: 0.2 }] },
  { name: "P_MW", unit: "MW", amplitude: 150, components: [{ amplitude: 100, frequencyHz: 4.95, onsetS: 10, decayPerS: 0.12 }, { amplitude: 50, frequencyHz: 1.15, onsetS: 10, decayPerS: 0.1 }] },
];

async function crossPage(page, options = {}) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 60, channels: CROSS_CHANNELS, ...options });
  await selectFreq(page);
  await setBand(page, 0.25, 8);
  await page.locator("#wwOscAnalyzeBtn").click();
  await expect(page.locator("#wwOscCross")).toBeVisible();
}
const tick = async (page, name) => {
  await page.locator("#wwOscCrossList label", { hasText: name }).locator("input").check();
};
async function crossCompared(page, options = {}) {
  await crossPage(page, options);
  await tick(page, "P_MW");
  await page.locator("#wwOscCrossBtn").click();
  await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
}
const crossComponents = (page) => page.evaluate(() => wwOscState.cross.result.components.map((c) => ({
  f: c.representative_frequency_hz, n: c.signal_count, types: c.signal_types, codes: c.reasons.map((r) => r.code), warn: c.warnings.map((w) => w.code),
  labels: c.members.map((m) => m.label) })));

test.describe("Oscillation Analysis -- cross-signal evidence", () => {
  test("hidden until Analyze; only the analysed signal is requested until Compare is pressed", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (isInterpretation(r)) requests.push(r.postDataJSON()); });
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 60, channels: CROSS_CHANNELS });
    await selectFreq(page);
    await setBand(page, 0.25, 8);
    await expect(page.locator("#wwOscCross")).toBeHidden();
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await expect(page.locator("#wwOscCross .ww-osc-detect-title")).toHaveText("Cross-Signal Oscillation Evidence");
    await expect(page.locator("#wwOscCrossBtn")).toBeDisabled(); // nothing chosen: no silent whole-workspace analysis
    await expect(page.locator("#wwOscInterp")).toBeVisible();
    await tick(page, "P_MW");
    await expect(page.locator("#wwOscCrossBtn")).toBeEnabled();
    await expect(page.locator("#wwOscInterpBody .ww-osc-interp-component").first()).toBeVisible();
    expect(requests).toHaveLength(1);                         // the reference-only baseline that feeds the interpretation
    expect(requests[0].signals.map((s) => s.input.channel_name)).toEqual(["FREQ"]);
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component")).toHaveCount(0); // nothing is compared yet
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
    expect(requests).toHaveLength(2);
    expect(requests[1].signals).toHaveLength(2); // the analysed signal plus the one ticked
    expect(requests[1].frequency_max_hz).toBe(8);
    expect(requests[1].signals.map((s) => s.input.channel_name)).toEqual(["FREQ", "P_MW"]);
  });

  test("the shared component is grouped across signal types; the separate one stays on its own", async ({ page }) => {
    await crossCompared(page);
    const comps = await crossComponents(page);
    const shared = comps.find((c) => c.n === 2), single = comps.find((c) => c.n === 1 && Math.abs(c.f - 1.15) < 0.2);
    expect(Math.abs(shared.f - 4.95)).toBeLessThan(0.3);
    expect(shared.types).toEqual(["Frequency", "Power"]);
    expect(shared.codes).toEqual(expect.arrayContaining(["observed_in", "frequency_match", "multiple_signal_types", "temporal_overlap"]));
    expect(single.labels).toEqual(["P_MW"]);
    expect(single.codes).toContain("single_signal_only");
    const body = await page.locator("#wwOscCrossBody").innerText();
    expect(body).toContain("Observed in 2 signals across 1 recording.");
    expect(body).toContain("Observed in one signal only");
    expect(body).toMatch(/Frequency — FREQ — \d+(\.\d+)? Hz/);
    expect(body).toMatch(/Power — P_MW — \d+(\.\d+)? Hz/);
    expect(body).toMatch(/decaying, ζ/); // per-signal damping is shown independently
    const text = body.toLowerCase();
    for (const word of ["inter-area", "local mode", "sso", "forced", "independently confirmed", "confidence", "well damped"]) expect(text).not.toContain(word);
    await expect(page.locator("#wwOscCrossNote")).toContainText("No oscillation type is inferred");
  });

  test("a calculated channel created while the page is open appears in the picker and is disclosed as derived", async ({ page }) => {
    await crossPage(page);
    await expect(page.locator("#wwOscCrossList label", { hasText: "NEG_MW" })).toHaveCount(0);
    await createCalculated(page, { name: "NEG_MW", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "P_MW" }] }); // a sign-flipped copy: same measurement, same frequencies
    await expect(page.locator("#wwOscCrossList label", { hasText: "NEG_MW" })).toHaveCount(1); // live: no reload, no restart
    await expect(page.locator("#wwOscCrossList label", { hasText: "NEG_MW" })).toContainText("(calculated)");
    await page.locator("#wwOscCrossList label", { hasText: "P_MW" }).first().locator("input").check();
    await page.locator("#wwOscCrossList label", { hasText: "NEG_MW" }).locator("input").check();
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
    const comps = await crossComponents(page);
    const shared = comps.find((c) => c.n === 3);
    expect(shared.warn).toContain("derived_from_same_source");
    expect(await page.locator("#wwOscCrossBody").innerText()).toContain("2 distinct measurements");
    expect(await page.evaluate(() => wwOscState.cross.result.signals.find((s) => s.label === "NEG_MW").origin)).toBe("calculated");
  });

  test("changing the settings marks the comparison not current; reverting restores; another signal discards it", async ({ page }) => {
    await crossCompared(page);
    await expect(page.locator("#wwOscCross")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscMaxFreqInput").fill("7");
    await expect(page.locator("#wwOscCross")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscCrossState")).toContainText("Analysis settings changed");
    await page.locator("#wwOscMaxFreqInput").fill("8");
    await expect(page.locator("#wwOscCross")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscCross")).toBeHidden();
    expect(await page.evaluate(() => wwOscState.cross.result)).toBeNull();
  });

  test("changing the ticked signals says so without discarding what was compared", async ({ page }) => {
    await crossCompared(page);
    await page.locator("#wwOscCrossList label", { hasText: "P_MW" }).locator("input").uncheck();
    await expect(page.locator("#wwOscCrossState")).toHaveText("Signal selection changed — press Compare to update");
    await expect(page.locator("#wwOscCrossBtn")).toBeDisabled();
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
  });

  test("a response arriving after the spectrum was cleared is discarded; an error is shown", async ({ page }) => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    // only the COMPARISON is held back (the reference-only baseline that Analyze requests is not)
    await page.route(CROSS_URL, async (route) => { if (route.request().postDataJSON().signals.length > 1) await gate; await route.continue(); });
    await crossPage(page);
    await tick(page, "P_MW");
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossState")).toHaveText("Comparing signals…");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    release();
    await page.waitForTimeout(500);
    expect(await page.evaluate(() => wwOscState.cross.result)).toBeNull();
    await page.unroute(CROSS_URL);
    await page.route(CROSS_URL, (route) => route.fulfill({ status: 409, contentType: "application/json",
      body: JSON.stringify({ detail: { code: "x", message: "Comparison refused." } }) }));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await tick(page, "FREQ");
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossState")).toHaveText("Comparison refused.");
  });

  test("renders at phone width without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await crossCompared(page);
    const m = await page.evaluate(() => ({ right: document.getElementById("wwOscCross").getBoundingClientRect().right, viewport: window.innerWidth,
                                           scroll: document.documentElement.scrollWidth }));
    expect(m.right).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});

// ---------------------------------------------------------------------------
// Cross-signal comparison PICKER (owner UAT fix): the selector is always visible after Analyze, lists the OTHER eligible catalogue
// signals grouped by recording, never auto-selects, and gates the Compare button.
// ---------------------------------------------------------------------------
const pickerBoxes = (page) => page.locator("#wwOscCrossList input[type=checkbox]");
const pickerNames = (page) => page.locator("#wwOscCrossList label").evaluateAll((l) => l.map((x) => x.textContent.trim()));
const pickerGroups = (page) => page.locator("#wwOscCrossList .ww-osc-cross-group").evaluateAll((g) => g.map((x) => ({
  recording: x.querySelector(".ww-osc-detect-label").textContent.trim(), items: Array.from(x.querySelectorAll("label")).map((l) => l.textContent.trim()) })));

async function secondRecording(page) {
  await uploadSynthetic(page, { name: "second", station: "SECOND_STN", durationS: 60,
    channels: [{ name: "P2", unit: "MW", amplitude: 100, frequencyHz: 4.95 }, { name: "F2", unit: "Hz", amplitude: 0.05, frequencyHz: 4.95 }] });
}

test.describe("Oscillation Analysis -- cross-signal picker", () => {
  test("the selector is visible without any click, nothing is pre-selected and Compare is disabled", async ({ page }) => {
    await crossPage(page);
    await expect(page.locator("#wwOscCrossList")).toBeVisible();
    await expect(page.locator("#wwOscCross .ww-osc-detect-label", { hasText: "Compare signals" }).first()).toBeVisible();
    await expect(page.locator("#wwOscCrossHint")).toContainText("Reference signal: FREQ");
    await expect(pickerBoxes(page)).toHaveCount(1);
    await expect(pickerBoxes(page).first()).toBeVisible();
    await expect(pickerBoxes(page).first()).not.toBeChecked(); // never silently auto-selected
    await expect(page.locator("#wwOscCrossBtn")).toBeDisabled();
    expect(await page.evaluate(() => wwOscState.cross.chosen.size)).toBe(0);
  });

  test("the analysed signal is the reference and is never offered; eligible signals are listed with their type", async ({ page }) => {
    await crossPage(page);
    const names = await pickerNames(page);
    expect(names).toHaveLength(1);
    expect(names[0]).toContain("P_MW");
    expect(names[0]).toContain("Power");
    expect(names.join(" ")).not.toContain("FREQ");
    // the reference changes with the analysed signal
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    expect((await pickerNames(page)).join(" ")).toContain("FREQ");
    expect((await pickerNames(page)).join(" ")).not.toContain("P_MW");
    await expect(page.locator("#wwOscCrossHint")).toContainText("Reference signal: P_MW");
  });

  test("choices are grouped by recording", async ({ page }) => {
    await crossPage(page);
    await secondRecording(page);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "FREQ"));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    const groups = await pickerGroups(page);
    expect(groups).toHaveLength(2);
    expect(groups[0].recording).toBe("osc.cfg");
    expect(groups[0].items).toHaveLength(1);
    expect(groups[0].items[0]).toContain("P_MW");
    expect(groups[1].recording).toBe("second.cfg");
    expect(groups[1].items).toHaveLength(2);
    expect(groups[1].items.join(" ")).toContain("P2");
    expect(groups[1].items.join(" ")).toContain("F2");
  });

  test("a calculated channel created later appears live under its recording and is marked calculated", async ({ page }) => {
    await crossPage(page);
    await expect(pickerBoxes(page)).toHaveCount(1);
    await createCalculated(page, { name: "NEG_MW", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "P_MW" }] });
    await expect(pickerBoxes(page)).toHaveCount(2);
    const groups = await pickerGroups(page);
    expect(groups).toHaveLength(1); // a calculated channel sits under the recording that owns its timing
    expect(groups[0].items.join(" ")).toContain("NEG_MW");
    expect(groups[0].items.join(" ")).toContain("(calculated)");
  });

  test("Compare is enabled by the first selection and disabled again when everything is deselected or the signal disappears", async ({ page }) => {
    await crossPage(page);
    const created = await createCalculated(page, { name: "NEG_MW", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "P_MW" }] });
    await expect(pickerBoxes(page)).toHaveCount(2);
    await page.locator("#wwOscCrossList label", { hasText: "P_MW" }).first().locator("input").check();
    await expect(page.locator("#wwOscCrossBtn")).toBeEnabled();
    await expect(page.locator("#wwOscCrossCount")).toHaveText("(1 selected)");
    await page.locator("#wwOscCrossList label", { hasText: "P_MW" }).first().locator("input").uncheck();
    await expect(page.locator("#wwOscCrossBtn")).toBeDisabled();
    await expect(page.locator("#wwOscCrossCount")).toHaveText("");
    // a selected comparison signal that is then removed drops out of the selection and Compare follows
    await page.locator("#wwOscCrossList label", { hasText: "NEG_MW" }).locator("input").check();
    await expect(page.locator("#wwOscCrossBtn")).toBeEnabled();
    const del = await page.request.delete(await workspaceUrl(page, "/calculated-channels/" + created.id));
    expect(del.ok(), await del.text()).toBeTruthy();
    await page.evaluate(() => wwFetchCalculatedChannels());
    await expect(pickerBoxes(page)).toHaveCount(1);
    await expect(page.locator("#wwOscCrossBtn")).toBeDisabled();
    expect(await page.evaluate(() => wwOscState.cross.chosen.size)).toBe(0);
  });

  test("no request before Compare; Compare sends exactly the reference plus the ticked identities, once each", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (isInterpretation(r)) requests.push(r.postDataJSON()); });
    await crossPage(page);
    await secondRecording(page);
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "FREQ"));
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    const calc = await createCalculated(page, { name: "NEG_MW", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: await sourceId(page), channel_name: "P_MW" }] });
    await page.locator("#wwOscCrossList label", { hasText: "P2" }).locator("input").check();
    await page.locator("#wwOscCrossList label", { hasText: "NEG_MW" }).locator("input").check();
    await page.waitForTimeout(400);
    expect(requests.filter((q) => q.signals.length > 1)).toHaveLength(0); // ticking never compares; only reference-alone baselines were sent
    expect(requests.every((q) => q.signals.length === 1 && q.signals[0].input.channel_name === "FREQ")).toBe(true);
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
    const compared = requests.filter((q) => q.signals.length > 1);
    expect(compared).toHaveLength(1);
    const ids = compared[0].signals.map((s) => (s.input.kind === "calculated" ? "calc:" + s.input.calculated_channel_id : "src:" + s.input.channel_name));
    expect(ids).toEqual(["src:FREQ", "src:P2", "calc:" + calc.id]);
    expect(new Set(ids).size).toBe(ids.length); // no duplicates, and the reference is not repeated
    expect(compared[0].signals.map((s) => s.signal_revision)).toEqual(await page.evaluate(() => wwOscState.cross.request.entries.map((e) => e.revision)));
  });

  test("the selection is capped so a comparison never exceeds the 8-signal service limit", async ({ page }) => {
    const channels = Array.from({ length: 9 }, (_, i) => ({ name: "C" + i, unit: "MW", amplitude: 100, frequencyHz: 2.0 + 0.5 * i }));
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 60, channels });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "C0"));
    await setBand(page, 0.25, 8);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await expect(pickerBoxes(page)).toHaveCount(8); // the 8 others; C0 (the reference) is not among them
    for (let i = 0; i < 7; i += 1) await pickerBoxes(page).nth(i).check();
    await expect(page.locator("#wwOscCrossCount")).toHaveText("(7 selected)");
    await expect(pickerBoxes(page).nth(7)).toBeDisabled(); // an 8th other would make 9 signals in total
    await expect(pickerBoxes(page).nth(0)).toBeEnabled();  // already-ticked ones can still be unticked
    await pickerBoxes(page).nth(0).uncheck();
    await expect(pickerBoxes(page).nth(7)).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// Oscillation Interpretation (DEC-179 [APPROVED]). The backend interprets every component (behaviour, probable type, Why,
// limitations, alternatives) from the evidence it already measured; the page draws what comes back. Analyze requests the analysed
// signal on its own; Compare adds the ticked signals. No probability, no AI.
// ---------------------------------------------------------------------------
const interpCard = (page, index = 0) => page.locator("#wwOscInterpBody .ww-osc-interp-component").nth(index);
const interpCards = (page) => page.evaluate(() => wwOscState.cross.result.components.map((c) => ({
  f: c.representative_frequency_hz, n: c.signal_count, type: c.interpretation.probable_type, level: c.interpretation.classification_level,
  behaviour: c.interpretation.behaviour_classification.code, why: c.interpretation.supporting_evidence.map((e) => e.code),
  limits: c.interpretation.limiting_evidence.map((e) => e.code), alts: c.interpretation.alternatives.map((a) => a.code),
  descriptors: c.interpretation.descriptors.map((d) => d.code) })));

test.describe("Oscillation Analysis -- oscillation interpretation", () => {
  test("Analyze interprets the analysed signal on its own: behaviour, probable type, Why and limitations", async ({ page }) => {
    await crossPage(page);
    await expect(page.locator("#wwOscInterp")).toBeVisible();
    await expect(page.locator("#wwOscInterp .ww-osc-detect-title")).toHaveText("Oscillation Interpretation");
    await expect(interpCard(page)).toBeVisible();
    await expect(interpCard(page).locator('[data-field="behaviour"]')).toContainText("Behaviour");
    await expect(interpCard(page).locator('[data-field="type"]')).toContainText("Probable type");
    await expect(interpCard(page).locator(".ww-osc-detect-label", { hasText: "Why" })).toBeVisible();
    await expect(interpCard(page).locator(".ww-osc-detect-label", { hasText: "Limitations" })).toBeVisible();
    const cards = await interpCards(page);
    expect(cards.length).toBeGreaterThan(0);
    // 4.95 / 7.3 Hz are above the conventional electromechanical range: a single signal never forces a family
    for (const c of cards) {
      expect(c.type.code).toBe("unresolved");
      expect(c.limits).toContain("single_signal_only");
    }
    const text = (await page.locator("#wwOscInterpBody").innerText()).toLowerCase();
    expect(text).toContain("oscillation detected — type unresolved");
    expect(text).toContain("higher-frequency oscillatory component detected at"); // a frequency description, not a mechanism
    expect(text).not.toContain("possible sub-synchronous");
    expect(text).toContain("frequency alone does not establish sub-synchronous oscillation");
    for (const word of ["confidence", "probability", "confirmed", "sso", "definitive"]) expect(text).not.toContain(word);
    await expect(page.locator("#wwOscInterpNote")).toContainText("no phase, mode-shape, coherence or location evidence exists yet");
  });

  test("comparing adds the other signals: the shared component becomes a cross-signal result, the single one stays single", async ({ page }) => {
    await crossCompared(page);
    await expect(page.locator("#wwOscInterpBody .ww-osc-interp-component").first()).toBeVisible();
    const cards = await interpCards(page);
    const shared = cards.find((c) => c.n === 2), single = cards.find((c) => c.n === 1 && Math.abs(c.f - 1.15) < 0.2);
    expect(shared.why).toEqual(expect.arrayContaining(["observed_in", "multiple_signal_types", "temporal_overlap"]));
    expect(shared.type.code).toBe("unresolved");                         // 4.95 Hz is never forced into a control interaction
    expect(shared.descriptors).toEqual(["higher_frequency_oscillatory_component"]);
    expect(single.limits).toContain("single_signal_only");
    expect(["electromechanical", "unresolved"]).toContain(single.type.code);
    const text = await page.locator("#wwOscInterpBody").innerText();
    expect(text).toContain("Observed in 2 signals across 1 recording.");
    expect(text).toContain("Observed in one signal only");
    await expect(page.locator("#wwOscInterpNote")).toContainText("Based on 2 analysed signals (FREQ, P_MW)");
  });

  test("the same component in two recordings: electromechanical family, provisional inter-area subtype, explicit limitations", async ({ page }) => {
    const mw = (name) => ({ name, unit: "MW", amplitude: 150, components: [{ amplitude: 100, frequencyHz: 0.5, onsetS: 10, decayPerS: 0.08 }] });
    await openOscillation(page);
    await uploadSynthetic(page, { name: "recA", station: "STN_A", durationS: 60, channels: [mw("MW_A")] });
    await uploadSynthetic(page, { name: "recB", station: "STN_B", durationS: 60, channels: [mw("MW_B")] });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "MW_A"));
    await setBand(page, 0.2, 3);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await tick(page, "MW_B");
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCrossBody .ww-osc-cross-component").first()).toBeVisible();
    const cards = await interpCards(page);
    const c = cards.find((x) => x.n === 2);
    expect(c.type.code).toBe("electromechanical");
    expect(["probable", "possible"]).toContain(c.level);
    if (c.type.subtype) {
      expect(c.type.subtype.level).toBe("possible");                       // never definitive
      expect(c.type.subtype.label).toBe("Possible inter-area electromechanical mode");
      expect(c.limits).toEqual(expect.arrayContaining(["phase_mode_shape_unavailable", "location_relationship_unknown"]));
      const text = await page.locator("#wwOscInterpBody").innerText();
      expect(text).toContain("Inter-area classification is provisional because relative phase/mode-shape evidence is not yet available.");
      expect(text).toContain("Possible subtype");
    }
    expect(c.why).toEqual(expect.arrayContaining(["observed_in", "multiple_recordings"]));
  });

  test("changing the settings marks the interpretation not current; reverting restores; another signal hides it", async ({ page }) => {
    await crossPage(page);
    await expect(interpCard(page)).toBeVisible();
    await expect(page.locator("#wwOscInterp")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscMaxFreqInput").fill("7");
    await expect(page.locator("#wwOscInterp")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscInterpState")).toHaveText("Analysis settings changed — run Analyze again");
    await page.locator("#wwOscMaxFreqInput").fill("8");
    await expect(page.locator("#wwOscInterp")).toHaveAttribute("data-stale", "false");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_MW"));
    await expect(page.locator("#wwOscInterp")).toBeHidden();
  });

  test("renders at phone width without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await crossCompared(page);
    await expect(interpCard(page)).toBeVisible();
    const m = await page.evaluate(() => ({ right: document.getElementById("wwOscInterp").getBoundingClientRect().right, viewport: window.innerWidth,
                                           scroll: document.documentElement.scrollWidth }));
    expect(m.right).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});

// ---------------------------------------------------------------------------
// Mode Shape / Relative Phase (DEC-180 [PROPOSAL]). Two MW signals of one recording carry the same decaying 1.15 Hz component; the
// backend returns the reference, each member's participation and relative phase, the stability, the Why and the limitations, and the
// page draws them. No alignment offset or phase is ever sent by the browser, and nothing is classified.
// ---------------------------------------------------------------------------
const MODE_CHANNELS = [
  { name: "FREQ", unit: "Hz", amplitude: 0.075, components: [{ amplitude: 0.05, frequencyHz: 4.95, onsetS: 10, decayPerS: 0.15 }] },
  { name: "P_A", unit: "MW", amplitude: 150, components: [{ amplitude: 100, frequencyHz: 1.15, onsetS: 10, decayPerS: 0.06 }] },
  { name: "P_B", unit: "MW", amplitude: 90, components: [{ amplitude: 60, frequencyHz: 1.15, onsetS: 10, decayPerS: 0.06 }] },
];
const isModeShape = (r) => r.url().endsWith("/oscillation-analysis/mode-shape");

async function modeShapeCompared(page) {
  await openOscillation(page);
  await uploadSynthetic(page, { durationS: 90, channels: MODE_CHANNELS });
  await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_A"));
  await setBand(page, 0.25, 8);
  await page.locator("#wwOscAnalyzeBtn").click();
  await expect(page.locator("#wwOscCross")).toBeVisible();
  await tick(page, "P_B");
  await page.locator("#wwOscCrossBtn").click();
  await expect(page.locator("#wwOscModeBody .ww-osc-interp-component").first()).toBeVisible();
}

test.describe("Oscillation Analysis -- mode shape / relative phase", () => {
  test("hidden until a comparison; then draws the reference, participation, phase, Why and limitations", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (isModeShape(r)) requests.push(r.postDataJSON()); });
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 90, channels: MODE_CHANNELS });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_A"));
    await setBand(page, 0.25, 8);
    await expect(page.locator("#wwOscMode")).toBeHidden();
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await expect(page.locator("#wwOscInterpBody .ww-osc-interp-component").first()).toBeVisible();
    await expect(page.locator("#wwOscMode")).toBeHidden();            // the reference-only baseline is not a comparison
    expect(requests).toHaveLength(0);
    await tick(page, "P_B");
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscModeBody .ww-osc-interp-component").first()).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0].signals.map((s) => s.input.channel_name)).toEqual(["P_A", "P_B"]);
    for (const s of requests[0].signals) expect(Object.keys(s)).not.toContain("offset_s");   // alignment comes from the backend
    expect(JSON.stringify(requests[0])).not.toContain("phase");
    await expect(page.locator("#wwOscMode .ww-osc-detect-title")).toHaveText("Mode Shape / Relative Phase");
    const group = page.locator('#wwOscModeBody .ww-osc-mode-group[data-quantity="Power"]');
    await expect(group).toBeVisible();
    await expect(group).toContainText("Reference: P_A");
    await expect(group.locator("table th")).toHaveText(["Signal", "Recording", "Participation", "Relative phase", "Amplitude", "Phase stability"]);
    await expect(group.locator('tr[data-signal="P_A"]')).toContainText("(reference)");
    await expect(group.locator('tr[data-signal="P_A"] td').nth(2)).toHaveText("100 %");
    await expect(group.locator('tr[data-signal="P_A"] td').nth(3)).toHaveText("0°");
    const other = group.locator('tr[data-signal="P_B"] td');
    await expect(other.nth(2)).toHaveText(/^[1-9]\d(\.\d+)? %$/);       // a participation below the reference
    const phase = await other.nth(3).innerText();
    expect(Math.abs(parseFloat(phase))).toBeLessThan(15);                // built with the same phase: in phase
    await expect(group.locator("[data-pattern]")).toHaveText("Approximately in phase");
    await expect(group.locator(".ww-osc-detect-label", { hasText: "Why" })).toBeVisible();
    await expect(group.locator(".ww-osc-detect-label", { hasText: "Limitations" })).toBeVisible();
    const text = await page.locator("#wwOscModeBody").innerText();
    expect(text).toContain("P_A is the phase reference (0°)");
    expect(text).toContain("do not establish that the signals represent different grid areas");
    expect(text).toContain("does not confirm an inter-area mode");
    const lower = text.toLowerCase();
    for (const word of ["probability", "confidence", "local mode", "sso"]) expect(lower).not.toContain(word);
    await expect(page.locator("#wwOscModeNote")).toContainText("positive = the member leads the reference");
    await expect(page.locator("#wwOscModeNote")).toContainText("no oscillation type is inferred");
  });

  test("the interpretation still says that relative phase / mode-shape evidence is unavailable (DEC-179 is unchanged)", async ({ page }) => {
    await modeShapeCompared(page);
    await expect(page.locator("#wwOscInterpNote")).toContainText("no phase, mode-shape, coherence or location evidence exists yet");
    const types = await page.evaluate(() => wwOscState.cross.result.components.map((c) => c.interpretation.probable_type.code));
    expect(types.length).toBeGreaterThan(0);
  });

  test("changing the settings marks the relative phase not current; restoring them restores it", async ({ page }) => {
    await modeShapeCompared(page);
    await expect(page.locator("#wwOscMode")).toHaveAttribute("data-stale", "false");
    await setBand(page, 0.3, 8);
    await expect(page.locator("#wwOscMode")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscModeState")).toHaveText("Analysis settings changed — run Analyze and Compare again");
    await setBand(page, 0.25, 8);
    await expect(page.locator("#wwOscMode")).toHaveAttribute("data-stale", "false");
  });

  test("fits a narrow viewport without horizontal page overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await modeShapeCompared(page);
    const m = await page.evaluate(() => ({ right: document.getElementById("wwOscMode").getBoundingClientRect().right, viewport: window.innerWidth,
      scroll: document.documentElement.scrollWidth }));
    expect(m.right).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});

// ---------------------------------------------------------------------------
// Coherence Evidence (DEC-181 [PROPOSAL]). Two MW signals of one recording carry the same decaying 1.15 Hz component. The backend returns the
// reference, the magnitude-squared coherence at the bin nearest the component frequency, the local band, the chance level, the averaging, the
// common interval, the Why and the limitations, and the page draws them. No offset or result is ever sent by the browser; nothing is classified.
// ---------------------------------------------------------------------------
const isCoherence = (r) => r.url().endsWith("/oscillation-analysis/coherence");

test.describe("Oscillation Analysis -- coherence evidence", () => {
  test("hidden until a comparison; then draws the reference, coherence, bin, chance level, Why and limitations", async ({ page }) => {
    const requests = [];
    page.on("request", (r) => { if (isCoherence(r)) requests.push(r.postDataJSON()); });
    await openOscillation(page);
    await uploadSynthetic(page, { durationS: 90, channels: MODE_CHANNELS });
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "P_A"));
    await setBand(page, 0.25, 8);
    await expect(page.locator("#wwOscCoh")).toBeHidden();
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscCross")).toBeVisible();
    await expect(page.locator("#wwOscInterpBody .ww-osc-interp-component").first()).toBeVisible();
    await expect(page.locator("#wwOscCoh")).toBeHidden();             // the reference-only baseline is not a comparison
    expect(requests).toHaveLength(0);
    await tick(page, "P_B");
    await page.locator("#wwOscCrossBtn").click();
    await expect(page.locator("#wwOscCohBody .ww-osc-interp-component").first()).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0].signals.map((s) => s.input.channel_name)).toEqual(["P_A", "P_B"]);
    for (const s of requests[0].signals) expect(Object.keys(s)).not.toContain("offset_s");
    expect(JSON.stringify(requests[0])).not.toContain("coherence");
    await expect(page.locator("#wwOscCoh .ww-osc-detect-title")).toHaveText("Coherence Evidence");
    const card = page.locator("#wwOscCohBody .ww-osc-interp-component").first();
    await expect(card).toContainText("Reference: P_A (the Mode Shape reference)");
    await expect(card.locator("table th")).toHaveText(["Signal", "Relationship", "Coherence", "At frequency", "Local peak", "Chance level", "Segments", "Common interval"]);
    const row = card.locator('tr[data-signal="P_B"]');
    await expect(row).toHaveAttribute("data-relationship", "same_variable");
    await expect(row.locator("td").nth(1)).toHaveText("same variable");
    const value = parseFloat(await row.locator("td").nth(2).innerText());
    expect(value).toBeGreaterThan(0.9);
    expect(value).toBeLessThanOrEqual(1);
    await expect(row.locator("td").nth(3)).toHaveText(/^\d+(\.\d+)? Hz$/);
    await expect(row.locator("td").nth(5)).toHaveText(/^0\.\d+$/);       // the chance level is shown separately from the measurement
    await expect(row.locator("td").nth(6)).toHaveText(/^\d+ \(bin \d+(\.\d+)? Hz\)$/);
    await expect(card.locator(".ww-osc-detect-label", { hasText: "Why — P_B" })).toBeVisible();
    await expect(card.locator(".ww-osc-detect-label", { hasText: "Limitations" })).toBeVisible();
    const text = await page.locator("#wwOscCohBody").innerText();
    expect(text).toMatch(/P_A and P_B contain the same ~1\.1\d* Hz component/);
    expect(text).toContain("chance level, not the probability that the oscillation is real");
    expect(text).toContain("does not identify causality or direction");
    expect(text).toContain("does not prove an inter-area mode");
    const lower = text.toLowerCase();
    for (const word of ["confidence", "local mode", "strong coherence", "weak coherence"]) expect(lower).not.toContain(word);
    await expect(page.locator("#wwOscCohNote")).toContainText("not a probability or a confidence");
    await expect(page.locator("#wwOscCohNote")).toContainText("no oscillation type, cause or direction is inferred");
  });

  test("the mode shape and the interpretation are unchanged by the coherence evidence", async ({ page }) => {
    await modeShapeCompared(page);
    await expect(page.locator("#wwOscCohBody .ww-osc-interp-component").first()).toBeVisible();
    await expect(page.locator("#wwOscModeBody .ww-osc-mode-group tr[data-signal='P_B'] td").nth(3)).toHaveText(/^[+-]?\d+(\.\d+)?°$|^0°$/);
    await expect(page.locator("#wwOscInterpNote")).toContainText("no phase, mode-shape, coherence or location evidence exists yet");
  });

  test("changing the settings marks the coherence not current", async ({ page }) => {
    await modeShapeCompared(page);
    await expect(page.locator("#wwOscCoh")).toHaveAttribute("data-stale", "false");
    await setBand(page, 0.3, 8);
    await expect(page.locator("#wwOscCoh")).toHaveAttribute("data-stale", "true");
    await expect(page.locator("#wwOscCohState")).toHaveText("Analysis settings changed — run Analyze and Compare again");
    await setBand(page, 0.25, 8);
    await expect(page.locator("#wwOscCoh")).toHaveAttribute("data-stale", "false");
  });

  test("fits a narrow viewport without horizontal page overflow", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await modeShapeCompared(page);
    await expect(page.locator("#wwOscCohBody .ww-osc-interp-component").first()).toBeVisible();
    const m = await page.evaluate(() => ({ right: document.getElementById("wwOscCoh").getBoundingClientRect().right, viewport: window.innerWidth,
      scroll: document.documentElement.scrollWidth }));
    expect(m.right).toBeLessThanOrEqual(m.viewport + 1);
    expect(m.scroll).toBeLessThanOrEqual(m.viewport + 1);
  });
});
