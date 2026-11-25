// NF-3C Phase A -- HISTORICAL characterisation of how the frontend shows a recording's nominal-frequency provenance (closes gap G-3).
//
// These tests record what the NF-3B tip DOES, not what is desired. Each one that NF-3C changes on purpose is listed in
// `nf3c_origin_labels.spec.js` (the post-migration specification) with the approved wording; this file stays as the evidence of the "before".
// Real backend, real frontend, no mocks. Fixture: one synthetic 1 kHz / 20 s COMTRADE record with a 50 Hz voltage channel VA; the `lf` line
// is replaced to make the recording declared (50), assumed (unparseable) or unusable (0).
//
// Surfaces covered (the three affected oscillation sites plus the Technical facts card):
//   site 1  the Setup adequacy list sentence "Analysis uses the RMS magnitude ... (one-cycle trailing window at X Hz, <origin>)"
//   site 2  Analysis Information, `#wwOscInfoNominal`
//   site 3  the Spectrum details row "Nominal frequency"
//   card    `renderRecordingDetails(source)` -- the Technical facts card. FINDING: it is DORMANT. Its only caller, renderRecordingsTable(),
//           was removed with the Recording Events page (RD-1 UX-3, see rd1-ux3.spec.js), so no live screen renders it. It is characterised by
//           calling the function directly, which is the only way to reach it.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const CHANNELS = [
  { name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 0.5 },
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
];

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

test.describe("HISTORICAL: oscillation origin labels (NF-3B tip)", () => {
  test("declared 50 Hz: site 1 and site 2 say 'from the recording'", async ({ page }) => {
    await openWith(page, "50");
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (from the recording)");
    await expect(checks(page)).toContainText("one-cycle trailing window at 50 Hz, from the recording)");
    await expect(checks(page)).not.toContainText("a default was assumed");
  });

  test("assumed 50 Hz (unparseable lf): site 1 and 2 say 'assumed default' and a warning is shown", async ({ page }) => {
    await openWith(page, "abc");
    await selectVa(page);
    await expect(info(page, "wwOscInfoNominal")).toHaveText("50 Hz (assumed default)");
    await expect(checks(page)).toContainText("one-cycle trailing window at 50 Hz, assumed default)");
    await expect(checks(page)).toContainText("The nominal frequency was not declared by the source and a default was assumed.");
  });

  test("unusable declaration (0): the representation is unavailable and says the nominal frequency is outside a sensible range", async ({ page }) => {
    await openWith(page, "0");
    await page.locator("#wwOscSignalSelect").selectOption(await optionValue(page, "VA"));
    await expect(checks(page)).toContainText("The recording's nominal frequency is missing or outside a sensible range.");
    await expect(info(page, "wwOscInfoNominal")).not.toContainText("from the recording");
    await expect(info(page, "wwOscInfoNominal")).not.toContainText("assumed default");
  });

  test("site 3: the spectrum details row for a declared and for an assumed recording", async ({ page }) => {
    await openWith(page, "abc");
    await selectVa(page);
    await page.locator("#wwOscAnalyzeBtn").click();
    await expect(page.locator("#wwOscSpectrumPlot.js-plotly-plot")).toHaveCount(1);
    await expect(specDetail(page, "Nominal frequency")).toHaveText("50 Hz (assumed default)");
  });
});

// ------------------------------------------------------------------------------------------------ the dormant Technical facts card
const SOURCE = (nominal) => ({
  source_id: "s1", status: "ready", recorder_name: "R", station_name: "S", analog_channel_count: 2, digital_channel_count: 0,
  nominal_frequency: nominal, timing_reference: "absolute", sample_count: 10, duration_seconds: 1, sampling_rates: [1000], samples_per_rate: [10],
  provider_type: "COMTRADE", original_filenames: ["a.cfg", "a.dat"],
});

test.describe("HISTORICAL: the dormant Technical facts card (called directly: no live screen renders it)", () => {
  const card = (page, nominal) => page.evaluate((n) => {
    const holder = document.createElement("div");
    holder.innerHTML = renderRecordingDetails(n);
    const row = Array.from(holder.querySelectorAll(".recording-details-fact")).find((f) => /Nominal frequency/.test(f.textContent));
    return row ? row.textContent.replace(/^\s*Nominal frequency\s*/, "").replace(/\s+/g, " ").trim() : null;
  }, SOURCE(nominal));

  test("it is unreachable: the Recording Events page and table are absent from the live DOM and nothing calls the renderer", async ({ page }) => {
    await page.goto("/index.html");
    await expect(page.locator("#recordingsTableBody")).toHaveCount(0);
    expect(await page.evaluate(() => typeof renderRecordingDetails)).toBe("function");
    expect(await page.evaluate(() => typeof renderRecordingsTable)).toBe("function");
    expect(await page.evaluate(() => document.querySelectorAll(".recording-details-facts").length)).toBe(0);
  });

  for (const [label, nominal, expected] of [["50", 50, "50 Hz"], ["60", 60, "60 Hz"], ["zero", 0, "0 Hz"],
                                            ["negative", -50, "-50 Hz"], ["declared NaN, which reaches the browser as JSON null", null, "null Hz"]]) {
    test(`historical text for a declared ${label}`, async ({ page }) => {
      await page.goto("/index.html");
      expect(await card(page, nominal)).toBe(expected);
    });
  }
});
