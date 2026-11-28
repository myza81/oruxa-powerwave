// NF-3E -- a recording-following calculated channel is flagged stale (marker + one advisory) after a Manual or Auto nominal-frequency change
// made in Recording Details; stored values are never recomputed; an explicit frequency is never flagged; the RMS builder preselects the
// recording's applicable frequency and declares the calculation's intent; a new calculation on a stale input is refused by the backend.
//
// Real backend + real frontend. The Manual control is release-gated in the page (featureFlags.nominalFrequencyOverride) and in the test backend
// (NOMINAL_FREQUENCY_MANUAL_OVERRIDE_ENABLED, set by playwright.config.js). Wording and placement of the advisory are subject to UAT.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const BACKEND_PORT = process.env.PW_BACKEND_PORT || "8000";
const API = `http://127.0.0.1:${BACKEND_PORT}`;
const NAMES = ["VA", "VB", "VC", "IA", "IB", "IC"];

function recording({ lf = "50", station = "NF3E" } = {}) {
  const files = syntheticComtrade({
    station, startClock: "10:00:00.000000", triggerClock: "10:00:00.050000", rateHz: 1000, durationS: 0.2,
    channels: NAMES.map((n) => ({ name: `${station}_${n}`, phase: n[1], unit: n[0] === "V" ? "V" : "A", amplitude: n[0] === "V" ? 100 : 5, frequencyHz: 50 })),
  });
  const text = files.cfg.toString("latin1");
  expect(text).toContain("\r\n50\r\n");
  return { cfg: Buffer.from(text.replace("\r\n50\r\n", `\r\n${lf}\r\n`), "latin1"), dat: files.dat };
}

async function gateOn(context) {
  await context.route("**/config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `window.POWERWAVE_CONFIG = { apiBaseUrl: "${API}", environment: "development", buildVersion: "local", featureFlags: { nominalFrequencyOverride: true } };`,
  }));
}

async function seed(page, opts) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingDetailsBtn").click();
  const files = recording(opts);
  await page.locator("#wwRdUploadBtn").click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "nf3e.cfg", mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "nf3e.dat", mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  const item = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  await expect(item).toBeVisible({ timeout: 10000 });
  const sourceId = await item.getAttribute("data-source-id");
  await item.click();
  if (page.viewportSize().width <= 692) await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  return sourceId;
}

const workspaceId = (page) => page.evaluate(() => currentWorkspaceId());

async function createRms(page, sourceId, name, hz, basis) {
  const ws = await workspaceId(page);
  const parameters = { nominal_frequency_hz: hz, ...(basis ? { nominal_frequency_basis: basis } : {}) };
  const response = await page.request.post(`${API}/api/v1/workspaces/${ws}/calculated-channels`, {
    data: { name, operation: "rms", inputs: [{ kind: "source", source_id: sourceId, channel_name: "NF3E_VA" }], parameters },
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()).id;
}

async function waveform(page, channelId) {
  const ws = await workspaceId(page);
  const body = await (await page.request.get(`${API}/api/v1/workspaces/${ws}/calculated-channels/${channelId}/waveform?point_budget=100000`)).json();
  return JSON.stringify([body.time, body.values]);
}

async function setManual(page, hz) {
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator('#wwRdNf [data-ww-nf-action="manual"]').click();
  await page.locator("#wwRdNfInput").fill(String(hz));
  await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
  await expect(page.locator('#wwRdNf [data-ww-nf-action="manual"]')).toHaveAttribute("aria-checked", "true");
}

async function setAuto(page) {
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await page.locator('#wwRdNf [data-ww-nf-action="auto"]').click();
  await expect(page.locator('#wwRdNf [data-ww-nf-action="auto"]')).toHaveAttribute("aria-checked", "true");
}

async function openCalculatedChannels(page) {
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

const rowOf = (page, name) => page.locator(".ww-cc-list-row").filter({ has: page.locator(".ww-cc-list-row-name", { hasText: name }) });

test.describe("NF-3E stale calculated channels", () => {
  test("a Manual change flags only the recording-following channel, keeps its values, and Auto clears it", async ({ page, context }) => {
    await gateOn(context);
    const source = await seed(page, { lf: "50" });
    const following = await createRms(page, source, "rms_follow", 50, "recording");
    await createRms(page, source, "rms_explicit", 50, "explicit");
    const before = await waveform(page, following);
    await page.evaluate(() => wwFetchCalculatedChannels());
    await openCalculatedChannels(page);
    await expect(page.locator("[data-ww-freq-stale]")).toHaveCount(0);

    const notified = page.evaluate(() => new Promise((resolve) =>
      document.addEventListener("nominal-frequency-changed", (e) => resolve(e.detail), { once: true })));
    await setManual(page, 60);
    const detail = await notified;                                         // the single in-page notification
    expect(detail).toMatchObject({ sourceId: source, effectiveHz: 60, origin: "manual" });

    await openCalculatedChannels(page);
    await expect(rowOf(page, "rms_follow").locator("[data-ww-freq-stale]")).toHaveCount(1);
    await expect(rowOf(page, "rms_follow").locator("[data-ww-freq-advisory]")).toContainText("Calculated at 50 Hz; the recording's nominal frequency is now 60 Hz (Manual)");
    await expect(rowOf(page, "rms_follow").locator("[data-ww-freq-advisory]")).toContainText("Values are unchanged");
    await expect(rowOf(page, "rms_explicit").locator("[data-ww-freq-stale]")).toHaveCount(0);
    expect(await waveform(page, following)).toBe(before);                  // never recomputed

    await setAuto(page);
    await openCalculatedChannels(page);
    await expect(page.locator("[data-ww-freq-stale]")).toHaveCount(0);
    expect(await waveform(page, following)).toBe(before);
  });

  test("a dependant inherits the marker and names the root cause", async ({ page, context }) => {
    await gateOn(context);
    const source = await seed(page, { lf: "50" });
    const rms = await createRms(page, source, "rms_follow", 50, "recording");
    const ws = await workspaceId(page);
    const made = await page.request.post(`${API}/api/v1/workspaces/${ws}/calculated-channels`, {
      data: { name: "doubled", operation: "addition", inputs: [{ kind: "calculated", calculated_channel_id: rms }, { kind: "calculated", calculated_channel_id: rms }] } });
    expect(made.status()).toBe(201);
    await setManual(page, 60);
    await page.evaluate(() => wwFetchCalculatedChannels());
    await openCalculatedChannels(page);
    await expect(rowOf(page, "doubled").locator("[data-ww-freq-advisory]")).toContainText("Depends on 'rms_follow', calculated at 50 Hz");
  });

  test("a new calculation on a stale input is refused with an actionable message", async ({ page, context }) => {
    await gateOn(context);
    const source = await seed(page, { lf: "50" });
    const rms = await createRms(page, source, "rms_follow", 50, "recording");
    await setManual(page, 60);
    const ws = await workspaceId(page);
    const refused = await page.request.post(`${API}/api/v1/workspaces/${ws}/calculated-channels`, {
      data: { name: "doubled", operation: "addition", inputs: [{ kind: "calculated", calculated_channel_id: rms }, { kind: "calculated", calculated_channel_id: rms }] } });
    expect(refused.status()).toBe(409);
    const detail = (await refused.json()).detail;
    expect(detail.code).toBe("stale_calculated_input");
    expect(detail.message).toContain("Create a new RMS channel");
  });

  async function openRmsBuilderOnVa(page) {
    await openCalculatedChannels(page);
    await page.locator("#wwCcNewChannelBtn").click();
    await page.locator('.ww-cc-operation-card[data-operation="rms"]').click();
    const select = page.locator("#wwCcUnaryInputSelect");
    const value = await select.locator("option").evaluateAll((options) => (options.find((o) => o.textContent.includes("NF3E_VA")) || {}).value);
    await select.selectOption(value);
  }

  async function createAndCapture(page, name) {
    await page.locator("#wwCcNameInput").fill(name);
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled({ timeout: 10000 });
    const sent = page.waitForRequest((r) => r.method() === "POST" && /\/calculated-channels$/.test(r.url()));
    await page.locator("#wwCcCreateBtn").click();
    return (await sent).postDataJSON().parameters;
  }

  test("the RMS builder preselects the applicable (Manual) frequency as Recording (60 Hz), and accepting it declares a recording-following calculation", async ({ page, context }) => {
    await gateOn(context);
    await seed(page, { lf: "50" });
    await setManual(page, 60);
    await openRmsBuilderOnVa(page);
    const select = page.locator("#wwCcNominalFrequencySelect");
    await expect(select).toHaveValue("recording");
    await expect(select.locator("option:checked")).toHaveText("Recording (60 Hz)");
    await expect(select.locator("option")).toHaveText(["Recording (60 Hz)", "50 Hz", "60 Hz"]);
    await expect(page.locator("#wwCcBuilderFields")).toContainText("Set in Recording Details");
    expect(await createAndCapture(page, "rms_builder")).toEqual({ nominal_frequency_hz: 60, nominal_frequency_basis: "recording" });
  });

  test("the preselection never prevents a different frequency: a deliberate choice is explicit, even when it equals the recording's", async ({ page, context }) => {
    await gateOn(context);
    await seed(page, { lf: "50" });
    await setManual(page, 60);
    await openRmsBuilderOnVa(page);
    const select = page.locator("#wwCcNominalFrequencySelect");

    await select.selectOption("50");                                        // a different frequency
    await expect(page.locator("#wwCcBuilderFields")).toContainText("Selected explicitly");
    await select.selectOption("60");                                        // the SAME number as the recording's: still a deliberate, explicit choice
    await expect(select).toHaveValue("60");
    await expect(page.locator("#wwCcBuilderFields")).toContainText("Selected explicitly");
    expect(await createAndCapture(page, "rms_explicit_60")).toEqual({ nominal_frequency_hz: 60, nominal_frequency_basis: "explicit" });
  });

  test("returning to the Recording option restores recording-following intent; the layout keeps one dropdown", async ({ page, context }) => {
    await gateOn(context);
    await seed(page, { lf: "50" });
    await openRmsBuilderOnVa(page);
    const select = page.locator("#wwCcNominalFrequencySelect");
    await expect(select).toHaveValue("recording");                          // preselected from the recording (Auto 50 Hz)
    await select.selectOption("60");
    await select.selectOption("recording");
    await expect(page.locator("#wwCcBuilderFields select#wwCcNominalFrequencySelect")).toHaveCount(1);
    expect(await createAndCapture(page, "rms_follow_again")).toEqual({ nominal_frequency_hz: 50, nominal_frequency_basis: "recording" });
  });

  test("a recording with no usable frequency requires an explicit choice and declares an explicit calculation", async ({ page, context }) => {
    await gateOn(context);
    await seed(page, { lf: "0" });
    await openCalculatedChannels(page);
    await page.locator("#wwCcNewChannelBtn").click();
    await page.locator('.ww-cc-operation-card[data-operation="rms"]').click();
    const select = page.locator("#wwCcUnaryInputSelect");
    const value = await select.locator("option").evaluateAll((options) => (options.find((o) => o.textContent.includes("NF3E_VA")) || {}).value);
    await select.selectOption(value);
    await expect(page.locator("#wwCcNominalFrequencySelect")).toHaveValue("");           // nothing preselected
    await expect(page.locator("#wwCcCreateBtn")).toBeDisabled();
    await page.locator("#wwCcNominalFrequencySelect").selectOption("60");
    await page.locator("#wwCcNameInput").fill("rms_explicit_choice");
    await expect(page.locator("#wwCcCreateBtn")).toBeEnabled({ timeout: 10000 });
    const sent = page.waitForRequest((r) => r.method() === "POST" && /\/calculated-channels$/.test(r.url()));
    await page.locator("#wwCcCreateBtn").click();
    expect((await sent).postDataJSON().parameters).toEqual({ nominal_frequency_hz: 60, nominal_frequency_basis: "explicit" });
  });
});
