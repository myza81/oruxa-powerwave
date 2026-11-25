// NF-3C -- how the frontend words a recording's nominal-frequency provenance (owner decisions O-6 and O-11, 2026-11-25).
//
// This file began as the Phase A HISTORICAL characterisation (commit 19d9755: "from the recording" / "assumed default" at the three oscillation
// sites, and "null Hz" on the Technical facts card). NF-3C changed those on purpose; the assertions below are the approved result. The old
// expectations are preserved in git history, and the listed differences are the approved changes:
//   recording_metadata -> "From recording"      (was "from the recording")
//   assumed_default    -> "Assumed default"     (was "assumed default")
//   import_supplied    -> "Supplied at import"  (new; a BEN upload used to read "from the recording")
//   manual             -> "Manual override — Set in Recording Details"  (new)
//   unusable           -> "Unusable declaration" (new)
//   an unknown origin  -> "Origin not recognised" (never a provenance the page has not earned)
//   facts card         -> never "null Hz" / "NaN Hz"; provenance only where it informs; the imported value separate from the effective one
//
// Real backend, real frontend. The test backend opens the server-side Manual gate (playwright.config.js), so Manual is exercised end to end;
// the UI flag is separate and is not needed here (the oscillation labels follow the backend's effective value, not the UI gate).
// Surfaces: site 1 the Setup adequacy sentence; site 2 Analysis Information (#wwOscInfoNominal); site 3 the Spectrum details row; and the
// Technical facts card. FINDING (Phase A): the facts card is DORMANT -- its only caller, renderRecordingsTable(), was removed with the Recording
// Events page (RD-1 UX-3) -- so it is exercised by calling the renderer directly. Whether to bring it to a live screen is an owner decision.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const CHANNELS = [
  { name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 0.5 },
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
];
const MANUAL = "Manual override — Set in Recording Details";

function recording(lf) {
  const { cfg, dat } = syntheticComtrade({ station: "NF3C", startClock: "10:00:00.000000", rateHz: 1000, durationS: 20, channels: CHANNELS });
  const text = cfg.toString("latin1");
  expect(text).toContain("\r\n50\r\n");
  return { cfg: Buffer.from(text.replace("\r\n50\r\n", `\r\n${lf}\r\n`), "latin1"), dat };
}

async function openWith(page, lf) {
  await page.goto("/index.html");
  const { cfg, dat } = recording(lf);
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator("#wwRdUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "nf3c.cfg", mimeType: "text/plain", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "nf3c.dat", mimeType: "text/plain", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item").first()).toBeVisible();
  await page.locator("#mainNavAnalysisBtn").click();
  await page.locator("#wwAnalysisTypeOscillationBtn").click();
  await expect(page.locator("#wwOscillationPanel")).toBeVisible();
}

const optionValue = (page, text) => page.locator("#wwOscSignalSelect option", { hasText: text }).first().getAttribute("value");
const info = (page, id) => page.locator("#" + id);
const checks = (page) => page.locator("#wwOscAdequacyList");
const specDetail = (page, label) => page.locator("#wwOscSpectrumDetails > div", {
  has: page.locator("dt", { hasText: new RegExp("^" + label + "$") }),
}).locator("dd");

async function selectVa(page) {
  await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
  await expect(checks(page)).not.toContainText("Preparing");
  await page.locator("#wwOscMinFreqInput").fill("0.5");
  await page.locator("#wwOscMaxFreqInput").fill("2");
}

const sourceId = (page) => page.evaluate(() => Array.from(ww.sourceChannelsData.keys())[0]);
const nfUrl = (page, id) => page.evaluate((i) => apiBaseUrl() + "/api/v1/workspaces/" + encodeURIComponent(currentWorkspaceId()) + "/sources/" + i + "/nominal-frequency", id);

test.describe("oscillation origin labels (approved NF-3C wording)", () => {
  test("declared 50 Hz: 'From recording' at sites 1 and 2, no assumption warning", async ({ page }) => {
    await openWith(page, "50");
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (From recording)");
    await expect(checks(page)).toContainText("one-cycle trailing window at 50 Hz, From recording)");
    await expect(checks(page)).not.toContainText("a default was assumed");
  });

  test("assumed 50 Hz (unparseable lf): 'Assumed default' and the existing warning", async ({ page }) => {
    await openWith(page, "abc");
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (Assumed default)");
    await expect(checks(page)).toContainText("one-cycle trailing window at 50 Hz, Assumed default)");
    await expect(checks(page)).toContainText("The nominal frequency was not declared by the source and a default was assumed.");
  });

  test("unusable declaration (0): the representation is unavailable, with the existing sentence, and no origin is claimed", async ({ page }) => {
    await openWith(page, "0");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
    await expect(checks(page)).toContainText("The recording's nominal frequency is missing or outside a sensible range.");
    await expect(info(page, "wwOscInfoNominal")).not.toContainText("From recording");
    await expect(info(page, "wwOscInfoNominal")).not.toContainText("Assumed default");
  });

  test("site 3: the spectrum row says 'Assumed default' for an assumed recording", async ({ page }) => {
    await openWith(page, "abc");
    await selectVa(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(specDetail(page, "Nominal frequency")).toHaveText("50 Hz (Assumed default)");
  });

  test("Manual override (server gate open): all three sites say so, with the engineer's value, never 'From recording'", async ({ page }) => {
    await openWith(page, "50");
    const id = await sourceId(page);
    const put = await page.request.put(await nfUrl(page, id), { data: { mode: "manual", value_hz: 60 } });
    expect(put.status()).toBe(200);
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("60 Hz (" + MANUAL + ")");
    await expect(checks(page)).toContainText("one-cycle trailing window at 60 Hz, " + MANUAL + ")");
    await expect(checks(page)).not.toContainText("From recording");
    for (const word of ["measured", "verified", "confirmed"]) await expect(info(page, "wwOscInfoNominal")).not.toContainText(word);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(specDetail(page, "Nominal frequency")).toHaveText("60 Hz (" + MANUAL + ")");
  });

  test("Manual corrects an unusable recording: the representation becomes available and says Manual override", async ({ page }) => {
    await openWith(page, "0");
    const id = await sourceId(page);
    expect((await page.request.put(await nfUrl(page, id), { data: { mode: "manual", value_hz: 50 } })).status()).toBe(200);
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (" + MANUAL + ")");
  });

  for (const [origin, label] of [["import_supplied", "Supplied at import"], ["recording_metadata", "From recording"], ["assumed_default", "Assumed default"],
                                  ["manual", MANUAL], ["unusable", "Unusable declaration"], ["something_new", "Origin not recognised"], [null, "Origin not recognised"]]) {
    test(`the shared label function: ${origin} -> ${label}`, async ({ page }) => {
      await page.goto("/index.html");
      expect(await page.evaluate((o) => wwNominalFrequencyOriginLabel(o), origin)).toBe(label);
    });
  }

  test("a backend origin the page does not know is not given a provenance (site 2)", async ({ page }) => {
    await openWith(page, "50");
    await page.route("**/oscillation-analysis/representation", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.nominal_frequency_origin = "something_new";
      await route.fulfill({ response, json: body });
    });
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (Origin not recognised)");
  });
});

// ------------------------------------------------------------------------------------------------ the dormant Technical facts card
const SOURCE = (nominal) => ({
  source_id: "s1", status: "ready", recorder_name: "R", station_name: "S", analog_channel_count: 2, digital_channel_count: 0,
  nominal_frequency: nominal, timing_reference: "absolute", sample_count: 10, duration_seconds: 1, sampling_rates: [1000], samples_per_rate: [10],
  provider_type: "COMTRADE", original_filenames: ["a.cfg", "a.dat"],
});
const INFO = (over) => Object.assign({ mode: "auto", usable: true, effective_hz: 50, origin: "recording_metadata", imported_hz: 50, imported_text: "50.0", auto_hz: 50 }, over);

async function facts(page, nominal, info) {
  return page.evaluate(([n, i]) => {
    const holder = document.createElement("div");
    holder.innerHTML = renderRecordingDetails(n, i === null ? undefined : i);
    const rows = {};
    for (const f of holder.querySelectorAll(".recording-details-fact")) {
      const label = f.querySelector(".recording-details-fact-label");
      const text = f.textContent.replace(/\s+/g, " ").trim();
      if (label && /frequency/i.test(label.textContent)) rows[label.textContent.trim()] = text.replace(label.textContent.trim(), "").trim();
    }
    return rows;
  }, [SOURCE(nominal), info]);
}

test.describe("the Technical facts card (dormant; called directly)", () => {
  test("it is unreachable: the Recording Events page and table are absent from the live DOM", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#recordingsTableBody")).toHaveCount(0);
    expect(await page.evaluate(() => document.querySelectorAll(".recording-details-facts").length)).toBe(0);
  });

  test("an ordinary valid declared value keeps the plain, uncluttered presentation", async ({ page }) => {
    await page.goto("/index.html");
    expect(await facts(page, 50, null)).toEqual({ "Nominal frequency": "50 Hz" });
    expect(await facts(page, 60, null)).toEqual({ "Nominal frequency": "60 Hz" });
    expect(await facts(page, 60, INFO({ effective_hz: 60, imported_hz: 60 }))).toEqual({ "Nominal frequency": "60 Hz" });
  });

  for (const [label, nominal, info] of [
    ["zero", 0, null], ["negative", -50, null], ["out of range", 1001, null], ["a declared NaN that reaches the browser as null", null, null],
    ["unusable by the backend (0)", 0, INFO({ usable: false, effective_hz: null, origin: "unusable", imported_hz: 0, imported_text: "0.0" })],
    ["unusable by the backend (nan)", null, INFO({ usable: false, effective_hz: null, origin: "unusable", imported_hz: null, imported_text: "nan" })],
    ["unusable by the backend (inf)", null, INFO({ usable: false, effective_hz: null, origin: "unusable", imported_hz: null, imported_text: "inf" })],
  ]) {
    test(`an invalid value (${label}) is called an unusable declaration and never printed as null Hz or NaN Hz`, async ({ page }) => {
      await page.goto("/index.html");
      const rows = await facts(page, nominal, info);
      expect(rows["Nominal frequency"]).toBe("Unusable declaration");
      expect(JSON.stringify(rows)).not.toMatch(/null Hz|NaN Hz|undefined|Infinity Hz/);
      expect(rows["Declared nominal frequency"]).toBeTruthy();
    });
  }

  test("provenance appears only where it informs, with the imported value kept separate", async ({ page }) => {
    await page.goto("/index.html");
    expect(await facts(page, 50, INFO({ origin: "assumed_default" }))).toEqual({ "Nominal frequency": "50 Hz (Assumed default)" });
    expect(await facts(page, 60, INFO({ origin: "import_supplied", effective_hz: 60, imported_hz: 60 }))).toEqual({ "Nominal frequency": "60 Hz (Supplied at import)" });
    expect(await facts(page, 50, INFO({ mode: "manual", origin: "manual", effective_hz: 60, manual_hz: 60 }))).toEqual({
      "Nominal frequency": "60 Hz (" + MANUAL + ")", "Imported nominal frequency": "50 Hz",
    });
  });

  test("a Manual value over an unusable declaration shows the declared value separately and never as measured or verified", async ({ page }) => {
    await page.goto("/index.html");
    const rows = await facts(page, 0, INFO({ mode: "manual", origin: "manual", effective_hz: 50, manual_hz: 50, imported_hz: 0, imported_text: "0.0", auto_hz: null }));
    expect(rows["Nominal frequency"]).toBe("50 Hz (" + MANUAL + ")");
    expect(rows["Imported nominal frequency"]).toBe("0 Hz");
    for (const word of ["measured", "verified", "confirmed"]) expect(JSON.stringify(rows)).not.toContain(word);
  });
});
