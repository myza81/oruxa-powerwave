// Waveform UX: calculated channels share the raw-channel presentation
// controls (right-click -> Rename / Change colour). User rename and colour
// are presentation metadata only (ww.channelPresentationOverrides, keyed by
// wwChannelKey(calc.id, calc.name)); they never touch the calculated
// channel's identity, operation, inputs or parameters, and they are never
// sent to the backend.
//
// Real backend + real frontend, no mocks. What is plotted is asserted from
// the live Plotly trace arrays of the main Waveform page.
//
// Fixture: a 100 Hz, 1.5 s ASCII COMTRADE with FREQ (Hz) and VA (V) -- same
// shape as calculated-channel-rocof.spec.js.

const { test, expect } = require("@playwright/test");
const { routeConfig } = require("./support/relay_import_helpers");

const SAMPLES = 151;
const ROCOF_500 = "ROCOF (FREQ, 500 ms)";
const ROCOF_100 = "ROCOF (FREQ, 100 ms)";
const NEG_VA = "-VA";

function fixture() {
  const cfg = [
    "SYNTH_STATION,SYNTH_DEV,1999",
    "2,2A,0D",
    "1,FREQ,,,Hz,1.0,0.0,0,-999999,999999,1.0,1.0,P",
    "2,VA,,,V,1.0,0.0,0,-999999,999999,110.0,1.0,P",
    "50",
    "1",
    `100.0,${SAMPLES}`,
    "06/03/2026,10:00:00.000000",
    "06/03/2026,10:00:00.000000",
    "ASCII",
    "1.0",
  ].join("\r\n") + "\r\n";
  const rows = [];
  for (let i = 0; i < SAMPLES; i++) {
    const f = 50 - i / 100;
    rows.push(`${i + 1},${i * 10000},${f.toFixed(6)},${(100 * Math.sin((2 * Math.PI * i) / 20)).toFixed(6)}`);
  }
  return { cfg: Buffer.from(cfg, "latin1"), dat: Buffer.from(rows.join("\r\n") + "\r\n", "latin1") };
}

async function upload(page) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = fixture();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "freq.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "freq.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}

async function pickInput(page, label) {
  const select = page.locator("#wwCcUnaryInputSelect");
  const value = await select.locator("option").evaluateAll(
    (options, wanted) => (options.find((o) => o.textContent.includes(wanted)) || {}).value, label);
  expect(value, `input option ${label}`).toBeTruthy();
  await select.selectOption(value);
}

async function createRocof(page, windowMs) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="rocof"]').click();
  await pickInput(page, "FREQ");
  await page.locator("#wwCcRocofWindowSelect").selectOption(String(windowMs));
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

async function createReversePolarity(page) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="reverse_polarity"]').click();
  await pickInput(page, "VA");
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

// Three calculated channels (two ROCOF + a Reverse Polarity), opened on the Waveform page.
async function setup(page) {
  await upload(page);
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
  await createRocof(page, 500);
  await createRocof(page, 100);
  await createReversePolarity(page);
  await page.locator("#mainNavWaveformBtn").click();
  await expect(calcRow(page, ROCOF_500)).toBeVisible();
}

const calcRow = (page, name) => page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${name}"]`);
const rawRow = (page, name) => page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);

async function show(page, row) {
  if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

// Live main-Waveform traces: identity (meta) is stable, name/colour are presentation.
async function traces(page) {
  return page.evaluate(() => ww.panels.flatMap((p) => ((p.chartEl && p.chartEl.data) || []).map((t) => ({
    meta: t.meta, name: (t.name || "").replace(/<[^>]+>/g, ""), color: t.line && t.line.color,
    n: (t.y || []).length, y: Array.from(t.y || []),
  }))));
}

const traceFor = async (page, canonicalName) => (await traces(page)).find((t) => t.meta.endsWith("::" + canonicalName));

// Everything that defines the calculation itself (as the backend sees it).
function engineeringIdentity(page) {
  return page.evaluate(async () => {
    const list = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId() + "/calculated-channels")).json();
    return list.map((c) => ({ id: c.id, name: c.name, operation: c.operation, inputs: c.inputs, parameters: c.parameters, unit: c.unit }));
  });
}

async function rename(page, row, newName) {
  await row.click({ button: "right" });
  await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
  await page.locator("#wwChannelMenuRenameBtn").click();
  await expect(page.locator("#wwChannelRenameOverlay")).toBeVisible();
  await page.locator("#wwChannelRenameInput").fill(newName);
  await page.locator("#wwChannelRenameApplyBtn").click();
  await expect(page.locator("#wwChannelRenameOverlay")).toBeHidden();
}

async function recolor(page, row, hex) {
  await row.click({ button: "right" });
  await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
  await page.locator("#wwChannelMenuColorBtn").click();
  await expect(page.locator("#wwChannelColorOverlay")).toBeVisible();
  await page.locator("#wwChannelColorHexInput").fill(hex);
  await page.locator("#wwChannelColorSetBtn").click();
  await page.keyboard.press("Escape");
  await expect(page.locator("#wwChannelColorOverlay")).toBeHidden();
}

test.describe("Calculated channel presentation (Rename / Change colour)", () => {
  test("right-click on a calculated channel opens the shared menu: Rename + Change colour, no raw-only Per-Unit", async ({ page }) => {
    await setup(page);
    await calcRow(page, ROCOF_500).click({ button: "right" });
    await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
    await expect(page.locator("#wwChannelMenuRenameBtn")).toBeVisible();
    await expect(page.locator("#wwChannelMenuColorBtn")).toBeVisible();
    await expect(page.locator("#wwChannelMenuPerUnitBtn")).toBeHidden();
    // The right-click did not toggle the channel's visibility.
    await expect(calcRow(page, ROCOF_500)).toHaveAttribute("aria-pressed", "false");
    await page.keyboard.press("Escape");

    // A raw row on the same menu still offers all three.
    await rawRow(page, "FREQ").click({ button: "right" });
    await expect(page.locator("#wwChannelMenuPerUnitBtn")).toBeVisible();
    await page.keyboard.press("Escape");
  });

  test("rename changes only the displayed name; identity, inputs and parameters are untouched; survives redraw and layout changes", async ({ page }) => {
    await setup(page);
    const before = await engineeringIdentity(page);
    await show(page, calcRow(page, ROCOF_500));
    await show(page, calcRow(page, ROCOF_100));
    await expect.poll(async () => (await traces(page)).length).toBe(2);

    await rename(page, calcRow(page, ROCOF_500), "ROCOF Bus A");

    // Sidebar, trace and (Grouped) hover name show the user name ...
    await expect(calcRow(page, ROCOF_500).locator(".channel-name-text")).toContainText("ROCOF Bus A");
    await expect(calcRow(page, ROCOF_500)).toHaveAttribute("aria-label", "Hide ROCOF Bus A");
    const renamed = await traceFor(page, ROCOF_500);
    expect(renamed.name).toBe("ROCOF Bus A");
    // ... the other calculated channel keeps its generated label ...
    expect((await traceFor(page, ROCOF_100)).name).toBe(ROCOF_100);
    // ... and the engineering identity (trace identity, backend config) is unchanged.
    expect(renamed.meta).toMatch(/^calc-[0-9a-f]+::ROCOF \(FREQ, 500 ms\)$/);
    expect(await engineeringIdentity(page)).toEqual(before);
    // The ROCOF operation type is still known to the app after the rename.
    expect(await page.evaluate(() => Array.from(ww.calculatedChannels.values()).map((c) => c.operation).sort()))
      .toEqual(["reverse_polarity", "rocof", "rocof"]);

    // Redraw / layout changes / zoom keep it. The trace data is regenerated each time.
    await page.evaluate(() => wwSetLayoutMode("separate"));
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).name).toBe("ROCOF Bus A");
    await expect(page.locator(".ww-legend-label", { hasText: "ROCOF Bus A" })).toBeVisible();
    await page.evaluate(() => wwSetLayoutMode("grouped"));
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).name).toBe("ROCOF Bus A");
    await page.evaluate(() => wwRebuildLayout());
    await page.evaluate(() => Plotly.relayout(ww.panels[0].chartEl, { "xaxis.range": [0.4, 0.9] }));
    expect((await traceFor(page, ROCOF_500)).name).toBe("ROCOF Bus A");

    // Hide + show re-creates the trace from scratch; the name is still the user's.
    await calcRow(page, ROCOF_500).click();
    await expect(calcRow(page, ROCOF_500)).toHaveAttribute("aria-pressed", "false");
    await calcRow(page, ROCOF_500).click();
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).name).toBe("ROCOF Bus A");

    // The calculation is still the same one: ROCOF of the -1 Hz/s ramp.
    const t = await traceFor(page, ROCOF_500);
    for (const v of t.y.filter((x) => x !== null && !Number.isNaN(x)).slice(5, -5)) expect(v).toBeCloseTo(-1, 5);

    // Reset to original restores the generated default.
    await calcRow(page, ROCOF_500).click({ button: "right" });
    await page.locator("#wwChannelMenuRenameBtn").click();
    await expect(page.locator("#wwChannelRenameOriginal")).toHaveText(ROCOF_500);
    await page.locator("#wwChannelRenameResetBtn").click();
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).name).toBe(ROCOF_500);
    expect(await engineeringIdentity(page)).toEqual(before);
  });

  test("colour changes the plotted trace, the sidebar dot and the Calculated Channels page; survives redraw and layout changes", async ({ page }) => {
    await setup(page);
    await show(page, calcRow(page, ROCOF_500));
    await show(page, calcRow(page, ROCOF_100));
    await expect.poll(async () => (await traces(page)).length).toBe(2);
    const otherBefore = (await traceFor(page, ROCOF_100)).color;
    const before = await engineeringIdentity(page);
    const dataBefore = (await traceFor(page, ROCOF_500)).y;

    await recolor(page, calcRow(page, ROCOF_500), "#123456");

    expect((await traceFor(page, ROCOF_500)).color).toBe("#123456");
    await expect(calcRow(page, ROCOF_500).locator(".channel-color-dot")).toHaveCSS("background-color", "rgb(18, 52, 86)");
    expect((await traceFor(page, ROCOF_100)).color).toBe(otherBefore);
    // Presentation only: the plotted samples and the backend configuration are the same.
    expect((await traceFor(page, ROCOF_500)).y).toEqual(dataBefore);
    expect(await engineeringIdentity(page)).toEqual(before);

    // Separate layout: trace + legend dot; then back to Grouped; then a full rebuild.
    await page.evaluate(() => wwSetLayoutMode("separate"));
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).color).toBe("#123456");
    await expect(page.locator(".ww-legend-item", { hasText: ROCOF_500 }).locator(".ww-legend-dot")).toHaveCSS("background-color", "rgb(18, 52, 86)");
    await page.evaluate(() => wwSetLayoutMode("grouped"));
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).color).toBe("#123456");
    await page.evaluate(() => wwRebuildLayout());
    expect((await traceFor(page, ROCOF_500)).color).toBe("#123456");

    // Calculated Channels page (manager dot + Preview trace) follows the same colour authority.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    const mgrDot = page.locator(".ww-cc-list-row", { has: page.locator(".ww-cc-list-row-name", { hasText: ROCOF_500 }) }).locator(".channel-color-dot");
    await expect(mgrDot).toHaveCSS("background-color", "rgb(18, 52, 86)");
    await expect.poll(() => page.evaluate(() => Array.from(document.querySelectorAll("#wwCcPreviewPanels .ww-cc-preview-chart"))
      .flatMap((c) => (c.data || []).map((t) => t.line.color)))).toContain("#123456");
    await page.locator("#mainNavWaveformBtn").click();

    // Reset to default restores the exact auto-assigned colour.
    await calcRow(page, ROCOF_500).click({ button: "right" });
    await page.locator("#wwChannelMenuColorBtn").click();
    await page.locator("#wwChannelColorResetBtn").click();
    await page.keyboard.press("Escape");
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).color).not.toBe("#123456");
  });

  test("several calculated channels (ROCOF and others) and a raw channel keep independent names and colours", async ({ page }) => {
    await setup(page);
    await show(page, calcRow(page, ROCOF_500));
    await show(page, calcRow(page, ROCOF_100));
    await show(page, calcRow(page, NEG_VA));
    await show(page, rawRow(page, "VA"));
    await expect.poll(async () => (await traces(page)).length).toBe(4);
    const untouchedBefore = await traceFor(page, ROCOF_100);

    await rename(page, calcRow(page, ROCOF_500), "ROCOF Bus A");
    await recolor(page, calcRow(page, ROCOF_500), "#aa0000");
    await rename(page, calcRow(page, NEG_VA), "Inverted VA");
    await recolor(page, calcRow(page, NEG_VA), "#00aa00");
    // Raw-channel rename / colour still works through the same menu.
    await rename(page, rawRow(page, "VA"), "Bus VA");
    await recolor(page, rawRow(page, "VA"), "#0000aa");

    const expected = {
      [ROCOF_500]: ["ROCOF Bus A", "#aa0000"],
      [NEG_VA]: ["Inverted VA", "#00aa00"],
      VA: ["Bus VA", "#0000aa"],
      [ROCOF_100]: [ROCOF_100, untouchedBefore.color],
    };
    const check = async () => {
      for (const [canonical, [name, color]] of Object.entries(expected)) {
        const t = (await traces(page)).find((x) => x.meta.endsWith("::" + canonical));
        expect(t, canonical).toBeTruthy();
        expect([t.name, t.color], canonical).toEqual([name, color]);
      }
    };
    await check();
    await page.evaluate(() => wwSetLayoutMode("separate"));
    await expect.poll(async () => (await traces(page)).length).toBe(4);
    await check();
    await page.evaluate(() => wwSetLayoutMode("grouped"));
    await expect.poll(async () => (await traces(page)).length).toBe(4);
    await check();
    // Adding another calculated channel does not disturb the others.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await createRocof(page, 200);
    await page.locator("#mainNavWaveformBtn").click();
    await check();
  });

  test("deleting one calculated channel leaves the others' presentation alone; a new channel never inherits it; raw state is untouched", async ({ page }) => {
    await setup(page);
    await show(page, calcRow(page, ROCOF_500));
    await show(page, calcRow(page, NEG_VA));
    await rename(page, calcRow(page, ROCOF_500), "ROCOF Bus A");
    await recolor(page, calcRow(page, ROCOF_500), "#aa0000");
    await rename(page, calcRow(page, NEG_VA), "Inverted VA");
    await rename(page, rawRow(page, "VA"), "Bus VA");
    const oldId = await calcRow(page, ROCOF_500).getAttribute("data-calculated-channel-id");

    // Delete the renamed ROCOF from the Calculated Channels page.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    // The manager list shows the current display name (the user's rename).
    const mgr = page.locator(".ww-cc-list-row", { has: page.locator(".ww-cc-list-row-name", { hasText: /^ROCOF Bus A$/ }) });
    await mgr.locator(".ww-cc-menu summary").click();
    await mgr.locator('button[data-action="delete"]').click();
    await expect(mgr).toHaveCount(0);

    // Its entry is gone, the others are intact.
    const keys = await page.evaluate(() => Array.from(ww.channelPresentationOverrides.keys()));
    expect(keys.some((k) => k.startsWith(oldId + "::"))).toBe(false);
    expect(keys.some((k) => k.endsWith("::" + NEG_VA))).toBe(true);
    expect(keys.some((k) => k.endsWith("::VA"))).toBe(true);

    // Recreating the same calculation yields a NEW identity with the default name / colour.
    await createRocof(page, 500);
    await page.locator("#mainNavWaveformBtn").click();
    const fresh = calcRow(page, ROCOF_500);
    await expect(fresh).toBeVisible();
    expect(await fresh.getAttribute("data-calculated-channel-id")).not.toBe(oldId);
    await expect(fresh.locator(".channel-name-text")).toContainText(ROCOF_500);
    await show(page, fresh);
    await expect.poll(async () => (await traceFor(page, ROCOF_500) || {}).name).toBe(ROCOF_500);
    expect((await traceFor(page, ROCOF_500)).color).not.toBe("#aa0000");
    await expect(calcRow(page, NEG_VA).locator(".channel-name-text")).toContainText("Inverted VA");
    await expect(rawRow(page, "VA").locator(".channel-name-text")).toContainText("Bus VA");
  });
  test("presentation survives navigation, a list refresh and a transient partial list; the manager shows the display name", async ({ page }) => {
    await setup(page);
    await show(page, calcRow(page, ROCOF_500));
    await rename(page, calcRow(page, ROCOF_500), "ROCOF Bus A");
    await recolor(page, calcRow(page, ROCOF_500), "#123456");
    const overrides = () => page.evaluate(() => JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())));
    const before = await overrides();

    // Calculated Channels page: the manager list shows the display name; away and back.
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await expect(page.locator(".ww-cc-list-row-name", { hasText: "ROCOF Bus A" })).toBeVisible();
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#mainNavWaveformBtn").click();
    expect((await traceFor(page, ROCOF_500)).name).toBe("ROCOF Bus A");
    expect((await traceFor(page, ROCOF_500)).color).toBe("#123456");

    // An authoritative refetch keeps it ...
    await page.evaluate(() => wwFetchCalculatedChannels());
    expect(await overrides()).toBe(before);
    // ... and so does a transient / partial list: the wholesale refresh never wipes overrides.
    await page.evaluate(() => {
      const all = Array.from(ww.calculatedChannels.values());
      wwCalculatedChannelsReplaceAll([]);
      wwCalculatedChannelsReplaceAll(all.slice(1));
      wwCalculatedChannelsReplaceAll(all);
    });
    expect(await overrides()).toBe(before);
    await expect(calcRow(page, ROCOF_500).locator(".channel-name-text")).toContainText("ROCOF Bus A");
  });
});
