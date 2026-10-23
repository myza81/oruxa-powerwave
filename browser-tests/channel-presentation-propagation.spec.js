// Workspace-wide channel presentation (DEC-070 amendment): a rename / colour
// set on the Waveform page is presentation metadata keyed by the stable
// channel identity; every consumer resolves it, and nothing that carries
// identity or provenance changes.
//
// Real backend + real frontend, no mocks. Fixture: one synthetic 1 kHz / 2 s
// COMTRADE with Frequency (FREQ), Active Power (P_MW) and Voltage (VA).

const { test, expect } = require("./support/test");
const { routeConfig } = require("./support/relay_import_helpers");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

const ALIAS = "JMAH GT1 Active Power";
const CALC_ALIAS = "GT1 magnitude";
const ABS_P = "Abs (P_MW)";

async function upload(page) {
  await routeConfig(page);
  await page.goto("/index.html");
  const { cfg, dat } = syntheticComtrade({
    station: "OSC_STN", startClock: "10:00:00.000000", rateHz: 1000, durationS: 2,
    channels: [
      { name: "FREQ", unit: "Hz", amplitude: 0.05, frequencyHz: 0.5 },
      { name: "P_MW", unit: "MW", amplitude: 100, frequencyHz: 0.5 },
      { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
    ],
  });
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "osc.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "osc.dat", mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
}

const rawRow = (page, name) => page.locator(`#channelGroups tr.channel-row--toggle[data-channel-kind="analog"][data-channel-name="${name}"]`);
const calcRow = (page, name) => page.locator(`#calculatedChannelsSidebarBody tr[data-calculated-channel-id][data-channel-name="${name}"]`);

async function openWaveform(page) {
  await page.locator("#mainNavWaveformBtn").click();
  await expect(page.locator("#workspaceRow")).toBeVisible();
}

async function renameVia(page, row, newName) {
  await row.click({ button: "right" });
  await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
  await page.locator("#wwChannelMenuRenameBtn").click();
  await expect(page.locator("#wwChannelRenameOverlay")).toBeVisible();
  await page.locator("#wwChannelRenameInput").fill(newName);
  await page.locator("#wwChannelRenameApplyBtn").click();
  await expect(page.locator("#wwChannelRenameOverlay")).toBeHidden();
}

async function pickOperation(page, operation) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator(`.ww-cc-operation-card[data-operation="${operation}"]`).click();
}

const inputOptions = (page) => page.locator("#wwCcUnaryInputSelect option").evaluateAll(
  (options) => options.filter((o) => o.value).map((o) => ({ value: o.value, text: o.textContent })));

async function chooseInput(page, textPart) {
  const options = await inputOptions(page);
  const found = options.find((o) => o.text.includes(textPart));
  expect(found, `input option containing "${textPart}" in ${JSON.stringify(options.map((o) => o.text))}`).toBeTruthy();
  await page.locator("#wwCcUnaryInputSelect").selectOption(found.value);
}

async function createAbs(page, inputTextPart) {
  await pickOperation(page, "absolute_value");
  await chooseInput(page, inputTextPart);
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

function backendCalculated(page) {
  return page.evaluate(async () => {
    const list = await (await fetch(apiBaseUrl() + "/api/v1/workspaces/" + currentWorkspaceId() + "/calculated-channels")).json();
    return list.map((c) => ({ id: c.id, name: c.name, operation: c.operation, inputs: c.inputs, parameters: c.parameters, unit: c.unit, dependency_ids: c.dependency_ids }));
  });
}

const sourceIdOf = (page) => page.evaluate(() => Array.from(ww.sourceChannelsData.keys())[0]);

test.describe("Workspace-wide channel presentation", () => {
  test("Calculated Channels pickers and summaries resolve raw and calculated display names; identity and dependencies are untouched", async ({ page }) => {
    await upload(page);
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await createAbs(page, "P_MW");
    await createAbs(page, "Abs (P_MW)"); // a calculated channel built on a calculated channel
    const before = await backendCalculated(page);
    expect(before.map((c) => c.name).sort()).toEqual(["Abs (Abs (P_MW))", ABS_P]);

    await openWaveform(page);
    await renameVia(page, rawRow(page, "P_MW"), ALIAS);
    await renameVia(page, calcRow(page, ABS_P), CALC_ALIAS);

    // Existing definitions are not rewritten: same names, ids, inputs, dependencies.
    expect(await backendCalculated(page)).toEqual(before);

    await page.locator("#mainNavCalculatedChannelsBtn").click();
    // Manager list: the operation summary shows the CURRENT display names of both input kinds.
    const rows = page.locator(".ww-cc-list-row");
    await expect(rows.filter({ hasText: CALC_ALIAS }).first()).toBeVisible();
    await expect(page.locator(".ww-cc-list-row-summary", { hasText: ALIAS }).first()).toBeVisible();
    await expect(page.locator(".ww-cc-list-row-summary", { hasText: CALC_ALIAS }).first()).toBeVisible();

    // Input picker: raw and calculated candidates both resolve the alias.
    await pickOperation(page, "absolute_value");
    const texts = (await inputOptions(page)).map((o) => o.text);
    expect(texts.some((t) => t.includes(ALIAS))).toBe(true);
    expect(texts.some((t) => t === CALC_ALIAS || t.startsWith(CALC_ALIAS + " "))).toBe(true);
    expect(texts.some((t) => t.includes("P_MW") && !t.includes("Abs (Abs"))).toBe(false);
    // The submitted identity of the chosen candidate is still canonical.
    await chooseInput(page, ALIAS);
    expect(await page.evaluate(() => ({ s: wwCcBuilder.inputs[0].channelName, k: wwCcBuilder.inputs[0].kind }))).toEqual({ s: "P_MW", k: "source" });
  });

  test("a new calculated channel persists the CANONICAL default name, never a user alias", async ({ page }) => {
    await upload(page);
    await openWaveform(page);
    await renameVia(page, rawRow(page, "P_MW"), ALIAS);
    await page.locator("#mainNavCalculatedChannelsBtn").click();

    await pickOperation(page, "absolute_value");
    await chooseInput(page, ALIAS);
    // The shown formula uses the alias; the name that will be persisted does not.
    await expect(page.locator("#wwCcExpressionPreview")).toContainText(ALIAS);
    await expect(page.locator("#wwCcNameInput")).toHaveValue(ABS_P);

    // Renaming the input WHILE the builder holds it (page mounted, drawer open) re-labels
    // the builder through the catalogue event; identity and the persisted name are untouched.
    await page.evaluate(() => wwSetChannelDisplayName(Array.from(ww.sourceChannelsData.keys())[0], "P_MW", "GT1 MW"));
    expect(await page.evaluate(() => ({
      short: wwCcBuilder.inputs[0].shortLabel, canonical: wwCcBuilder.inputs[0].canonicalLabel, channelName: wwCcBuilder.inputs[0].channelName,
    }))).toEqual({ short: "GT1 MW", canonical: "P_MW", channelName: "P_MW" });
    await expect(page.locator("#wwCcExpressionPreview")).toContainText("GT1 MW");
    await expect(page.locator("#wwCcNameInput")).toHaveValue(ABS_P);

    await page.locator("#wwCcCreateBtn").click();
    await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    const created = await backendCalculated(page);
    expect(created).toHaveLength(1);
    expect(created[0].name).toBe(ABS_P);
    expect(created[0].inputs).toEqual([expect.objectContaining({ kind: "source", channel_name: "P_MW", source_id: await sourceIdOf(page) })]);
    // No alias leaked into any persisted field.
    expect(JSON.stringify(created)).not.toContain("GT1 MW");
    expect(JSON.stringify(created)).not.toContain(ALIAS);
  });

  test("Oscillation selector resolves raw and calculated aliases without re-selecting, also while mounted", async ({ page }) => {
    await upload(page);
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await createAbs(page, "P_MW");
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOscillationBtn").click();
    await expect(page.locator("#wwOscillationPanel")).toBeVisible();

    const labels = () => page.locator("#wwOscSignalSelect option").evaluateAll((o) => o.filter((x) => x.value).map((x) => x.textContent));
    const valueOf = (text) => page.locator("#wwOscSignalSelect option", { hasText: text }).first().getAttribute("value");
    const keyBefore = await valueOf("P_MW [MW]");
    expect(keyBefore).toBeTruthy();
    await page.locator("#wwOscSignalSelect").selectOption(keyBefore);
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(keyBefore);

    // Rename while the Oscillation page is mounted and subscribed: no navigation, no re-selection.
    await page.evaluate(([alias, calcAlias]) => {
      const sid = Array.from(ww.sourceChannelsData.keys())[0];
      wwSetChannelDisplayName(sid, "P_MW", alias);
      const calc = Array.from(ww.calculatedChannels.values())[0];
      wwSetChannelDisplayName(calc.id, calc.name, calcAlias);
    }, [ALIAS, CALC_ALIAS]);
    await expect.poll(labels).toEqual(expect.arrayContaining([ALIAS + " [MW]", CALC_ALIAS + " [MW]"]));
    expect((await labels()).some((t) => t.startsWith("P_MW") || t.startsWith(ABS_P))).toBe(false);
    // Same option value (the signal key), still the selected signal; the name fact follows.
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(keyBefore);
    await expect(page.locator("#wwOscillationPanel")).toContainText(ALIAS);
    // Identity: the catalogue still holds the canonical name.
    expect(await page.evaluate((k) => wwSignalCatalogueGet(k).name, keyBefore)).toBe("P_MW");

    // Navigating away and back keeps it; resetting restores the canonical label.
    await page.locator("#mainNavWaveformBtn").click();
    await page.locator("#mainNavAnalysisBtn").click();
    await page.locator("#wwAnalysisTypeOscillationBtn").click();
    expect(await labels()).toEqual(expect.arrayContaining([ALIAS + " [MW]"]));
    await page.evaluate(() => wwResetChannelDisplayName(Array.from(ww.sourceChannelsData.keys())[0], "P_MW"));
    await expect.poll(labels).toEqual(expect.arrayContaining(["P_MW [MW]"]));
    await expect(page.locator("#wwOscSignalSelect")).toHaveValue(keyBefore);
  });

  test("provenance keeps canonical names: rename dialog original, source metadata, Table View", async ({ page }) => {
    await upload(page);
    await page.locator("#mainNavCalculatedChannelsBtn").click();
    await createAbs(page, "P_MW");
    await openWaveform(page);
    await renameVia(page, rawRow(page, "P_MW"), ALIAS);
    await renameVia(page, calcRow(page, ABS_P), CALC_ALIAS);

    // The dialog always shows the canonical name as "Original".
    await rawRow(page, "P_MW").click({ button: "right" });
    await page.locator("#wwChannelMenuRenameBtn").click();
    await expect(page.locator("#wwChannelRenameOriginal")).toHaveText("P_MW");
    await expect(page.locator("#wwChannelRenameInput")).toHaveValue(ALIAS);
    await page.keyboard.press("Escape");
    await calcRow(page, ABS_P).click({ button: "right" });
    await page.locator("#wwChannelMenuRenameBtn").click();
    await expect(page.locator("#wwChannelRenameOriginal")).toHaveText(ABS_P);
    await page.keyboard.press("Escape");

    // The loaded source's channel names are unchanged; rows keep canonical data attributes.
    expect(await page.evaluate(() => Array.from(ww.sourceChannelsData.values())[0].analog_channels.map((c) => c.name))).toEqual(["FREQ", "P_MW", "VA"]);
    await expect(rawRow(page, "P_MW")).toHaveAttribute("data-channel-name", "P_MW");

    // Table View is the canonical record view (DEC-079): canonical column labels, no alias.
    await page.locator("#mainNavTableBtn").click();
    const headers = page.locator("#wwTableEl thead th");
    await expect(headers.filter({ hasText: "P_MW" }).first()).toBeVisible();
    expect(await headers.allTextContents()).not.toContainEqual(expect.stringContaining(ALIAS));
  });
});
