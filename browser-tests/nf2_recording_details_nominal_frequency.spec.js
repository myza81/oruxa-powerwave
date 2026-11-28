// NF-2 -- Recording Details > Recording Info > Nominal frequency (Auto / Manual), release-gated.
//
// The control talks only to the NF-1 API (GET/PUT .../sources/{id}/nominal-frequency). It is OFF unless
// window.POWERWAVE_CONFIG.featureFlags.nominalFrequencyOverride === true, because no engineering calculation reads the
// override until NF-3. Every test below that needs it switches the gate on by serving a modified /config.js.

const fs = require("fs");
const path = require("path");
const { test, expect } = require("./support/test");

// The statement the page shows under the row once the calculations honour the setting (NF-3I); it must match frontend/index.html.
const SCOPE = "Used by this recording's frequency-based calculations and analyses (RMS, power, phasor, overcurrent, compliance, " +
  "event detection and RMS-based oscillation). Not used by automatic per-unit base evidence or by the nominal comparison for " +
  "natively analysed oscillation signals.";
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const DEFAULT_CONFIG = fs.readFileSync(path.join(__dirname, "..", "frontend", "config.js"), "utf8");
const NAMES = ["VA", "VB", "VC", "IA", "IB", "IC"];
const SHOTS = process.env.NF2_SCREENSHOT_DIR || null;

// The synthetic builder writes the nominal-frequency line as `50`; replace the whole line with what the scenario needs.
function recording({ lf = "50", station = "NF2" } = {}) {
  const files = syntheticComtrade({
    station, startClock: "10:00:00.000000", triggerClock: "10:00:00.050000", rateHz: 1000, durationS: 0.2,
    channels: NAMES.map((n) => ({ name: `${station}_${n}`, phase: n[1], unit: n[0] === "V" ? "V" : "A", amplitude: n[0] === "V" ? 100 : 5, frequencyHz: 50 })),
  });
  const text = files.cfg.toString("latin1");
  expect(text).toContain("\r\n50\r\n");
  return { cfg: Buffer.from(text.replace("\r\n50\r\n", `\r\n${lf}\r\n`), "latin1"), dat: files.dat };
}

async function gate(context, flags) {
  await context.route("**/config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: DEFAULT_CONFIG + (flags === undefined ? "" : `\nwindow.POWERWAVE_CONFIG.featureFlags = ${JSON.stringify(flags)};\n`),
  }));
}
const on = (context) => gate(context, { nominalFrequencyOverride: true });

async function upload(page, files, stem) {
  const ids = () => page.locator("#wwRdRecordingList .ww-rd-recording-item").evaluateAll((els) => els.map((e) => e.getAttribute("data-source-id")));
  const known = await ids();
  await page.locator("#wwRdUploadBtn").click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${stem}.cfg`, mimeType: "application/octet-stream", buffer: files.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${stem}.dat`, mimeType: "application/octet-stream", buffer: files.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(known.length + 1, { timeout: 10000 });
  return (await ids()).find((id) => !known.includes(id));
}

async function select(page, sourceId) {
  await page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${sourceId}"]`).click();
  if (page.viewportSize().width <= 692) {
    await page.evaluate(() => { wwRdState.narrowPanel = "details"; wwRdApplyNarrowLayout(); });
  }
}

// Opens the page, uploads one recording and shows its Recording Info. Returns the source id.
async function seed(page, opts, stem = "nf2") {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingDetailsBtn").click();
  const id = await upload(page, recording(opts), stem);
  await select(page, id);
  return id;
}

const row = (page) => page.locator("#wwRdNf");
const value = (page) => page.locator("#wwRdNf [data-ww-nf-value]");
const pill = (page, which) => page.locator(`#wwRdNf [data-ww-nf-action="${which}"]`);
const input = (page) => page.locator("#wwRdNfInput");
const workspaceId = (page) => page.evaluate(() => currentWorkspaceId());
const api = (page, id) => workspaceId(page).then((ws) => `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}/api/v1/workspaces/${ws}/sources/${id}/nominal-frequency`);
const server = async (page, id) => (await page.request.get(await api(page, id))).json();

function watch(page) {
  const seen = { get: 0, put: [], other: [] };
  page.on("request", (r) => {
    if (!/\/nominal-frequency(\?|$)/.test(r.url())) return;
    if (r.method() === "GET") seen.get += 1;
    else if (r.method() === "PUT") seen.put.push(JSON.parse(r.postData()));
    else seen.other.push(r.method());
  });
  return seen;
}

// ------------------------------------------------------------------------------------------------ the release gate
test.describe("release gate", () => {
  test("off by default: the original read-only row, no control and no request", async ({ page }) => {
    const seen = watch(page);
    await seed(page, { lf: "50" });
    const metadata = page.locator('#wwRdDetailsBody [data-ww-info="metadata"]');
    await expect(metadata.locator(".ww-rd-config-table").nth(1).locator(".ww-rd-config-label")).toHaveText(
      ["Start time", "Trigger time", "Duration", "Sample rate", "Nominal frequency", "Channels"]);
    await expect(metadata).toContainText("50 Hz");
    await expect(page.locator("#wwRdNf")).toHaveCount(0);
    await expect(page.locator("[data-ww-nf-action]")).toHaveCount(0);
    await expect(page.locator("#wwRdSideSection")).toBeVisible();      // the rest of Recording Info is intact
    expect(seen).toEqual({ get: 0, put: [], other: [] });
  });

  for (const [name, flags] of [
    ["flag false", { nominalFrequencyOverride: false }],
    ["flag the string 'true'", { nominalFrequencyOverride: "true" }],
    ["flag the number 1", { nominalFrequencyOverride: 1 }],
    ["an unrelated flag", { somethingElse: true }],
    ["featureFlags null", null],
  ]) {
    test(`stays off for ${name} (only the boolean true opens it)`, async ({ page, context }) => {
      await gate(context, flags);
      const seen = watch(page);
      await seed(page, { lf: "60" });
      await expect(page.locator("#wwRdDetailsBody")).toContainText("60 Hz");
      await expect(page.locator("#wwRdNf")).toHaveCount(0);
      expect(seen.get).toBe(0);
    });
  }

  test("on: the control appears and states what the setting applies to", async ({ page, context }) => {
    await on(context);
    await seed(page, { lf: "50" });
    await expect(row(page)).toBeVisible();
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="scope"]')).toHaveText(SCOPE);
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="preview"]')).toHaveCount(0);
  });
});

// NF-3I: the calculations honour the setting, so the page says WHAT it applies to (and what it does not: the owner's O-3 exclusion and the NF-3C
// native-oscillation limitation) in every state, and no state still calls the control a preview.
test.describe("the scope statement", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  async function expectScope(page) {
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="scope"]')).toHaveText(SCOPE);
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="preview"]')).toHaveCount(0);
    expect(await row(page).innerText()).not.toMatch(/preview/i);
  }

  test("declared, assumed, unusable, editing and Manual all carry it", async ({ page }) => {
    await seed(page, { lf: "0" });                                      // unusable
    await expectScope(page);
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="unusable"]')).toContainText("choose Manual to enter a value for frequency-based calculations");
    await pill(page, "manual").click();                                 // editing
    await expectScope(page);
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();  // Manual saved
    await expect(value(page)).toHaveText("60 Hz");
    await expectScope(page);
    await expect(page.locator("#wwRdNfLive")).toHaveText("Manual nominal frequency saved: 60 Hz");
    await pill(page, "auto").click();                                   // back to Auto (unusable again)
    await expect(pill(page, "auto")).toHaveAttribute("aria-checked", "true");
    await expectScope(page);
  });

  test("a declared and an assumed recording carry it", async ({ page }) => {
    await seed(page, { lf: "60" });
    await expectScope(page);
    await seed(page, { lf: "abc" }, "nf2b");
    await expect(page.locator('#wwRdNf [data-ww-nf-flag="assumed"]')).toBeVisible();
    await expectScope(page);
  });

  test("it names the automatic per-unit base evidence exclusion", async ({ page }) => {
    await seed(page, { lf: "50" });
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="scope"]')).toContainText("Not used by automatic per-unit base evidence");
  });
});

// --------------------------------------------------------------------------------------------- states and transitions
test.describe("states", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  test("a declared frequency is plain text with Auto selected and no status label", async ({ page }) => {
    const id = await seed(page, { lf: "60" });
    await expect(value(page)).toHaveText("60 Hz");
    await expect(pill(page, "auto")).toHaveAttribute("aria-checked", "true");
    await expect(pill(page, "manual")).toHaveAttribute("aria-checked", "false");
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await expect(row(page)).toHaveAttribute("data-ww-nf-origin", "recording_metadata");
    await expect(page.locator("[data-ww-nf-flag]")).toHaveCount(0);
    await expect(page.locator("[data-ww-nf-detail]")).toHaveCount(0);
    await expect(value(page)).toHaveAttribute("title", "Imported 60.0 Hz · recording metadata");
    expect((await server(page, id)).effective_hz).toBe(60);
  });

  test("an assumed 50 Hz is visibly marked as an assumed default", async ({ page }) => {
    await seed(page, { lf: "abc" });                                    // unparseable lf: the importer assumes 50 Hz
    await expect(value(page)).toHaveText("50 Hz");
    await expect(page.locator('#wwRdNf [data-ww-nf-flag="assumed"]')).toHaveText("Assumed default");
    await expect(row(page)).toHaveAttribute("data-ww-nf-origin", "assumed_default");
    await expect(value(page)).toHaveAttribute("title", "Imported 50.0 Hz · assumed default");
  });

  test("an unusable declared frequency is an explicit unavailable state and viewing still works", async ({ page }) => {
    const id = await seed(page, { lf: "0" });
    await expect(value(page)).toHaveText("—");
    await expect(row(page)).toHaveAttribute("data-ww-nf-effective", "");
    const notice = page.locator('#wwRdNf [data-ww-nf-notice="unusable"]');
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("0.0 Hz");
    await expect(notice).toContainText("Waveform viewing is unaffected");
    await expect(pill(page, "auto")).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("#wwRdSideSection")).toBeVisible();      // the rest of the page is unaffected
    expect((await server(page, id)).usable).toBe(false);
  });

  test("a non-finite declared frequency (nan) is shown unusable with the declared text, never a crash", async ({ page }) => {
    await seed(page, { lf: "nan" });
    await expect(value(page)).toHaveText("—");
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="unusable"]')).toContainText("nan Hz");
  });

  test("Auto -> Manual -> Apply stores the value; the imported value and Auto stay visible", async ({ page }) => {
    const seen = watch(page);
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await expect(input(page)).toBeFocused();
    await expect(input(page)).toHaveValue("50");                       // seeded with the Auto value
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    await expect(pill(page, "manual")).toHaveAttribute("aria-checked", "true");
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    await expect(row(page)).toHaveAttribute("data-ww-nf-origin", "manual");
    await expect(page.locator("[data-ww-nf-detail]")).toHaveText("Auto: 50 Hz · recording metadata. Imported 50.0 Hz.");
    await expect(page.locator('#wwRdNf [data-ww-nf-action="edit"]')).toBeVisible();
    expect(seen.put).toEqual([{ mode: "manual", value_hz: 60 }]);
    const body = await server(page, id);
    expect([body.mode, body.manual_hz, body.imported_hz, body.revision]).toEqual(["manual", 60, 50, 1]);
  });

  test("a Manual value equal to Auto is preserved as Manual, also after a reload", async ({ page }) => {
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();   // 50, the Auto value, unchanged
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    await expect(value(page)).toHaveText("50 Hz");
    expect((await server(page, id)).mode).toBe("manual");
    await page.reload();
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await select(page, id);
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    await expect(pill(page, "manual")).toHaveAttribute("aria-checked", "true");
    await expect(value(page)).toHaveText("50 Hz");
  });

  test("Edit changes an existing Manual value; Auto returns to the automatic value and leaves the originals alone", async ({ page }) => {
    const seen = watch(page);
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    await page.locator('#wwRdNf [data-ww-nf-action="edit"]').click();
    await expect(input(page)).toHaveValue("60");
    await input(page).fill("59.5");
    await input(page).press("Enter");                                  // keyboard apply
    await expect(value(page)).toHaveText("59.5 Hz");
    await pill(page, "auto").click();
    await expect(value(page)).toHaveText("50 Hz");
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await expect(page.locator("[data-ww-nf-detail]")).toHaveCount(0);
    expect(seen.put).toEqual([{ mode: "manual", value_hz: 60 }, { mode: "manual", value_hz: 59.5 }, { mode: "auto" }]);
    const body = await server(page, id);
    expect([body.mode, body.manual_hz, body.imported_hz, body.imported_text, body.effective_hz]).toEqual(["auto", null, 50, "50.0", 50]);
    const ws = await workspaceId(page);
    const summary = await (await page.request.get(`http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}/api/v1/workspaces/${ws}/sources/${id}`)).json();
    expect(summary.nominal_frequency).toBe(50);                       // the imported metadata is untouched
  });

  test("a correction makes an unusable recording usable and Auto makes it unusable again", async ({ page }) => {
    await seed(page, { lf: "0" });
    await pill(page, "manual").click();
    await expect(input(page)).toHaveValue("");                         // nothing usable to seed
    await expect(page.locator('#wwRdNf [data-ww-nf-action="apply"]')).toBeDisabled();
    await input(page).fill("50");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("50 Hz");
    await expect(page.locator("[data-ww-nf-detail]")).toContainText("Auto: unusable (0.0 Hz declared)");
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="unusable"]')).toHaveCount(0);
    await pill(page, "auto").click();
    await expect(value(page)).toHaveText("—");
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="unusable"]')).toBeVisible();
  });

  test("Cancel on a first Manual sends nothing and leaves Auto", async ({ page }) => {
    const seen = watch(page);
    await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await expect(input(page)).toBeVisible();
    await page.locator('#wwRdNf [data-ww-nf-action="cancel"]').click();
    await expect(input(page)).toHaveCount(0);
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await expect(pill(page, "auto")).toHaveAttribute("aria-checked", "true");
    await pill(page, "manual").click();
    await input(page).press("Escape");                                 // keyboard cancel
    await expect(input(page)).toHaveCount(0);
    await pill(page, "manual").click();
    await pill(page, "auto").click();                                  // choosing Auto while editing also leaves it
    await expect(input(page)).toHaveCount(0);
    expect(seen.put).toEqual([]);
  });
});

// ----------------------------------------------------------------------------------- validation and rejected saves
test.describe("validation and rejection", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  for (const [text, message] of [
    ["abc", "Enter a number, for example 50 or 60."],
    ["50 Hz", "Enter a number, for example 50 or 60."],
    ["-5", "Enter a number, for example 50 or 60."],
    ["1e999", "Enter a number, for example 50 or 60."],
    ["0", "Enter a frequency between 1 and 1000 Hz."],
    ["0.5", "Enter a frequency between 1 and 1000 Hz."],
    ["1001", "Enter a frequency between 1 and 1000 Hz."],
  ]) {
    test(`'${text}' is refused in the editor and nothing is sent`, async ({ page }) => {
      const seen = watch(page);
      await seed(page, { lf: "50" });
      await pill(page, "manual").click();
      await input(page).fill(text);
      await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
      await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toHaveText(message);
      await expect(input(page)).toHaveAttribute("aria-invalid", "true");
      await expect(input(page)).toHaveValue(text);
      expect(seen.put).toEqual([]);
      await input(page).fill("60");                                    // typing clears the message
      await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toHaveCount(0);
    });
  }

  test("an empty field cannot be applied", async ({ page }) => {
    await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("");
    await expect(page.locator('#wwRdNf [data-ww-nf-action="apply"]')).toBeDisabled();
  });

  test("a rejection from the server keeps the editor open with the message, changes nothing, and a retry works", async ({ page, context }) => {
    const id = await seed(page, { lf: "50" });
    const target = await api(page, id);
    let rejected = 0;
    await context.route(target, (route) => {
      if (route.request().method() !== "PUT") return route.fallback();
      rejected += 1;
      return route.fulfill({ status: 400, contentType: "application/json",
        body: JSON.stringify({ detail: { code: "invalid_nominal_frequency", message: "The nominal frequency must be a finite number from 1 to 1000 Hz." } }) });
    });
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toHaveText("The nominal frequency must be a finite number from 1 to 1000 Hz.");
    await expect(input(page)).toBeVisible();
    await expect(input(page)).toHaveValue("60");
    expect(rejected).toBe(1);
    expect((await server(page, id)).mode).toBe("auto");               // nothing changed on the server
    await context.unroute(target);
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
  });

  test("a server-side release gate that is closed is reported in the editor and nothing is saved", async ({ page, context }) => {
    // NF-3B: the UI flag shows the control; the BACKEND decides whether a Manual value may be stored. With the server gate
    // closed (the default and the only state of a deployed build) PUT mode=manual is 409. The body below is the backend's own
    // (test_nf3b_server_side_release_gate.py asserts the same code and message); the editor shows the server's sentence.
    const id = await seed(page, { lf: "50" });
    const target = await api(page, id);
    await context.route(target, (route) => route.request().method() !== "PUT" ? route.fallback() : route.fulfill({
      status: 409, contentType: "application/json",
      body: JSON.stringify({ detail: { code: "manual_nominal_frequency_disabled",
        message: "A manual nominal frequency cannot be saved: the feature has not been released in this environment." } }) }));
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toHaveText(
      "A manual nominal frequency cannot be saved: the feature has not been released in this environment.");
    await expect(input(page)).toBeVisible();
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await context.unroute(target);
    expect((await server(page, id)).mode).toBe("auto");
  });

  test("a network failure on save is reported and nothing is applied", async ({ page, context }) => {
    const id = await seed(page, { lf: "50" });
    const target = await api(page, id);
    await context.route(target, (route) => route.request().method() === "PUT" ? route.abort("failed") : route.fallback());
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toContainText("could not be saved");
    await expect(input(page)).toBeVisible();
    await context.unroute(target);
    expect((await server(page, id)).mode).toBe("auto");
  });

  test("a failed Auto reverts the display to the server's state with a message", async ({ page, context }) => {
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    const target = await api(page, id);
    await context.route(target, (route) => route.request().method() === "PUT" ? route.fulfill({ status: 500, contentType: "application/json", body: "{}" }) : route.fallback());
    await pill(page, "auto").click();
    await expect(page.locator('#wwRdNf [data-ww-nf-notice="error"]')).toBeVisible();
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    await expect(value(page)).toHaveText("60 Hz");
  });
});

// ------------------------------------------------------------------ lifecycle: reload, deletion, workspace reset
test.describe("lifecycle", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  test("save and reload keeps the Manual value", async ({ page }) => {
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("58.25");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("58.25 Hz");
    await page.reload();
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await select(page, id);
    await expect(value(page)).toHaveText("58.25 Hz");
    await expect(row(page)).toHaveAttribute("data-ww-nf-revision", "1");
  });

  test("removing the recording removes its value; the same file added again starts in Auto", async ({ page }) => {
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    const url = await api(page, id);
    await page.locator(`#wwRdRecordingList .ww-rd-recording-item[data-source-id="${id}"] .ww-rd-recording-item-remove`).click();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0, { timeout: 10000 });
    expect((await page.request.get(url)).status()).toBe(404);
    const again = await upload(page, recording({ lf: "50" }), "again");
    await select(page, again);
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await expect(value(page)).toHaveText("50 Hz");
    expect(again).not.toBe(id);
  });

  test("a workspace reset clears every value", async ({ page }) => {
    const id = await seed(page, { lf: "50" });
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    const ws = await workspaceId(page);
    const base = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}/api/v1/workspaces/${ws}`;
    expect((await page.request.delete(base)).status()).toBe(204);
    expect((await page.request.get(`${base}/sources/${id}/nominal-frequency`)).status()).toBe(404);
    await page.reload();
    await page.locator("#mainNavRecordingDetailsBtn").click();
    await expect(page.locator("#wwRdRecordingList .ww-rd-recording-item")).toHaveCount(0);
    const fresh = await upload(page, recording({ lf: "50" }), "fresh");
    await select(page, fresh);
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
  });

  test("two recordings keep independent values", async ({ page }) => {
    const a = await seed(page, { lf: "50", station: "RECA" }, "reca");
    await pill(page, "manual").click();
    await input(page).fill("60");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("60 Hz");
    const b = await upload(page, recording({ lf: "50", station: "RECB" }), "recb");
    await select(page, b);
    await expect(row(page)).toHaveAttribute("data-ww-nf-source", b);
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
    await expect(value(page)).toHaveText("50 Hz");
    await select(page, a);
    await expect(row(page)).toHaveAttribute("data-ww-nf-source", a);
    await expect(value(page)).toHaveText("60 Hz");
  });
});

// --------------------------------------------------------------- stale responses, revisions and rapid changes
test.describe("stale responses and rapid changes", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  test("a slow answer for the previous recording never lands in the newly selected one", async ({ page, context }) => {
    const a = await seed(page, { lf: "60", station: "SLOWA" }, "slowa");
    const b = await upload(page, recording({ lf: "50", station: "FASTB" }), "fastb");
    await select(page, a);
    await expect(value(page)).toHaveText("60 Hz");
    await select(page, b);
    await expect(value(page)).toHaveText("50 Hz");
    // From now on every read of A is slow; select A, then B before A's answer arrives.
    const urlA = await api(page, a);
    await context.route(urlA, async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.fallback(); });
    await select(page, a);
    await select(page, b);
    await expect(row(page)).toHaveAttribute("data-ww-nf-source", b);
    await page.waitForTimeout(2200);                                   // A's answer has now arrived
    await expect(row(page)).toHaveAttribute("data-ww-nf-source", b);
    await expect(value(page)).toHaveText("50 Hz");
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "auto");
  });

  test("rapid Manual, Auto, Manual changes end on the last one, applied in order", async ({ page, context }) => {
    const seen = watch(page);
    const id = await seed(page, { lf: "50" });
    const target = await api(page, id);
    // The first save is the slowest: a naive client would let its answer overwrite the later ones.
    let n = 0;
    await context.route(target, async (route) => {
      if (route.request().method() === "PUT") { n += 1; await new Promise((r) => setTimeout(r, n === 1 ? 700 : 100)); }
      await route.fallback();
    });
    await pill(page, "manual").click();
    await input(page).fill("55");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();      // queued: manual 55
    await expect(pill(page, "manual")).toHaveAttribute("aria-checked", "true");
    await pill(page, "auto").click();                                       // queued: auto
    await pill(page, "manual").click();
    await input(page).fill("65");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();      // queued: manual 65
    await expect(value(page)).toHaveText("65 Hz", { timeout: 10000 });
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    expect(seen.put).toEqual([{ mode: "manual", value_hz: 55 }, { mode: "auto" }, { mode: "manual", value_hz: 65 }]);
    const body = await server(page, id);
    expect([body.mode, body.manual_hz]).toEqual(["manual", 65]);
    await expect(row(page)).toHaveAttribute("data-ww-nf-revision", String(body.revision));
    expect(body.revision).toBe(3);                                          // set, clear, set: three real changes
  });

  test("a reordered older answer is ignored: the display never goes back to an older revision", async ({ page, context }) => {
    const id = await seed(page, { lf: "50" });
    const target = await api(page, id);
    const older = await server(page, id);                                  // revision 0, Auto
    let served = 0;
    await context.route(target, async (route) => {
      if (route.request().method() === "GET" && served === 0) {           // the re-read after the save returns the OLD body once
        served += 1;
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(older) });
      }
      return route.fallback();
    });
    await pill(page, "manual").click();
    await input(page).fill("62");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("62 Hz");                          // not 50: the old body was refused and re-read
    await expect(row(page)).toHaveAttribute("data-ww-nf-mode", "manual");
    await expect(row(page)).toHaveAttribute("data-ww-nf-revision", "1");
    expect(served).toBe(1);
  });
});

// ------------------------------------------------------------------------------------- regression and accessibility
test.describe("Recording Details regression and accessibility", () => {
  test.beforeEach(async ({ context }) => { await on(context); });

  test("the metadata card, Measurement Side and tab navigation are unchanged with the control on", async ({ page }) => {
    await seed(page, { lf: "50" });
    const tables = page.locator('#wwRdDetailsBody [data-ww-info="metadata"] .ww-rd-config-table');
    await expect(tables).toHaveCount(2);
    await expect(tables.nth(1).locator(".ww-rd-config-label")).toHaveText(["Start time", "Trigger time", "Duration", "Sample rate", "Nominal frequency", "Channels"]);
    await expect(tables.nth(1)).toContainText("6 analog / 0 digital");
    await expect(page.locator("#wwRdSideSection .ww-rd-section-heading")).toHaveText("Measurement Side");
    await page.locator("#wwRdTabGroupDetails").click();
    await page.locator("#wwRdTabRecordingInfo").click();
    await expect(row(page)).toBeVisible();
    await expect(value(page)).toHaveText("50 Hz");
  });

  test("controls are labelled, keyboard-operable and announce changes", async ({ page }) => {
    await seed(page, { lf: "50" });
    await expect(page.getByRole("radiogroup", { name: "Nominal frequency source" })).toBeVisible();
    await expect(page.getByRole("radio", { name: "Auto" })).toBeChecked();
    await page.getByRole("radio", { name: "Manual" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Nominal frequency in hertz")).toBeFocused();
    await page.keyboard.type("60");
    await page.keyboard.press("Enter");
    await expect(value(page)).toHaveText("60 Hz");
    await expect(page.locator("#wwRdNfLive")).toHaveText("Manual nominal frequency saved: 60 Hz");
  });

  test("no console errors across the transitions", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await seed(page, { lf: "0" });
    await pill(page, "manual").click();
    await input(page).fill("50");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("50 Hz");
    await pill(page, "auto").click();
    await expect(value(page)).toHaveText("—");
    expect(errors).toEqual([]);
  });
});

// ---------------------------------------------------------------------------------- screenshots (owner evidence)
test.describe("screenshots", () => {
  test.skip(!SHOTS, "set NF2_SCREENSHOT_DIR to write the owner-review screenshots");
  test.beforeEach(async ({ context }) => { await on(context); });

  async function shot(page, name) {
    fs.mkdirSync(SHOTS, { recursive: true });
    await expect(row(page)).toBeVisible();
    await page.waitForTimeout(300);                                    // let any in-flight re-render settle
    for (let attempt = 0; ; attempt += 1) {
      try {
        await page.locator('#wwRdDetailsBody [data-ww-info="metadata"]').screenshot({ path: path.join(SHOTS, `${name}.png`) });
        return;
      } catch (error) {
        if (attempt >= 3) throw error;
        await page.waitForTimeout(300);
      }
    }
  }

  test("states in light, dark and narrow", async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    const a = await seed(page, { lf: "60", station: "DECL60" }, "decl60");
    await shot(page, "1_auto_declared_60");
    await pill(page, "manual").click();
    await expect(input(page)).toBeFocused();
    await shot(page, "2_manual_editor");
    await input(page).fill("1500");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await shot(page, "3_validation_error");
    await input(page).fill("59.5");
    await page.locator('#wwRdNf [data-ww-nf-action="apply"]').click();
    await expect(value(page)).toHaveText("59.5 Hz");
    await shot(page, "4_manual_applied");
    const b = await upload(page, recording({ lf: "abc", station: "ASSUMED" }), "assumed");
    await select(page, b);
    await expect(value(page)).toHaveText("50 Hz");
    await shot(page, "5_auto_assumed_default");
    const c = await upload(page, recording({ lf: "0", station: "BAD0" }), "bad0");
    await select(page, c);
    await expect(value(page)).toHaveText("—");
    await shot(page, "6_unusable_declared");
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await shot(page, "7_unusable_dark");
    await select(page, a);
    await shot(page, "8_manual_dark");
    await page.evaluate(() => document.documentElement.removeAttribute("data-theme"));
    await page.setViewportSize({ width: 600, height: 900 });
    await select(page, c);
    await shot(page, "9_unusable_narrow");
  });
});
