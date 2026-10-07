// Shared live workspace signal catalogue (architecture foundation).
//
// Real backend + real frontend, no mocks. Proves that raw and calculated
// channels are one live catalogue that consumers read and observe, with no
// producer-side knowledge of any consumer and no page reload.
//
// Fixture: line_to_line_multibay (see line-to-line-voltage.spec.js).

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const STEM = "line_to_line_multibay";

async function uploadFixture(page) {
  await page.goto("/index.html");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${STEM}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${STEM}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").first()).toBeVisible();
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  await expect(page.locator("#pageCalculatedChannels")).toBeVisible();
}

// Records every catalogue event on window.__signalEvents, from a consumer
// that has no other relationship to the producers.
async function observe(page) {
  await page.evaluate(() => {
    window.__signalEvents = [];
    window.__navigationMarker = "same-page-load";
    wwSignalCatalogueSubscribe((event) => window.__signalEvents.push(event));
  });
}

// RMS of the n-th selectable input (display names vary with phase convention).
async function createRms(page, inputIndex = 0) {
  await page.locator("#wwCcNewChannelBtn").click();
  await expect(page.locator("#wwCcDrawer")).toHaveClass(/ww-cc-drawer--open/);
  await page.locator('.ww-cc-operation-card[data-operation="rms"]').click();
  const select = page.locator("#wwCcUnaryInputSelect");
  const values = await select.locator("option").evaluateAll((options) => options.map((o) => o.value).filter(Boolean));
  expect(values.length, "selectable RMS inputs").toBeGreaterThan(inputIndex);
  await select.selectOption(values[inputIndex]);
  await expect(page.locator("#wwCcCreateBtn")).toBeEnabled();
  await page.locator("#wwCcCreateBtn").click();
  await expect(page.locator("#wwCcDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
}

const calculatedSignals = (page) => page.evaluate(() => wwSignalCatalogueList((s) => s.origin === "calculated")
  .map((s) => ({ key: s.key, name: s.name, revision: s.revision, referenceSourceId: s.referenceSourceId })));

test.describe("Shared live signal catalogue", () => {
  test("raw signals are listed, unique and consumer-filterable", async ({ page }) => {
    await uploadFixture(page);
    const raw = await page.evaluate(() => wwSignalCatalogueList((s) => s.origin === "raw")
      .map((s) => ({ key: s.key, signalType: s.signalType, name: s.name, sourceId: s.sourceId })));
    expect(raw.length).toBeGreaterThan(0);
    expect(new Set(raw.map((s) => s.key)).size).toBe(raw.length);
    // The producer-side authority and the catalogue agree.
    expect(await page.evaluate(() => ww.sourceChannelsData.size)).toBe(1);
    const analog = await page.evaluate(() => wwSignalCatalogueList((s) => s.signalType === "analog").length);
    expect(analog).toBeGreaterThan(0);
    expect(analog).toBeLessThanOrEqual(raw.length);
    // Consumer-specific eligibility is the consumer's predicate, not the catalogue's.
    const voltages = await page.evaluate(() => wwSignalCatalogueList((s) => s.origin === "raw" && s.signalType === "analog" && s.engineeringType === "Voltage").length);
    expect(voltages).toBeGreaterThan(0);
    expect(voltages).toBeLessThan(analog + 1);
  });

  test("a calculated channel appears, an observer is told, and nothing reloads", async ({ page }) => {
    await uploadFixture(page);
    await observe(page);
    const rawBefore = await page.evaluate(() => wwSignalCatalogueList((s) => s.origin === "raw").length);
    const revisionBefore = await page.evaluate(() => wwSignalCatalogue.revision);

    await createRms(page);

    const created = await calculatedSignals(page);
    expect(created).toHaveLength(1);
    expect(created[0].key).toMatch(/^calculated:calc-/);
    const events = await page.evaluate(() => window.__signalEvents);
    expect(events.some((e) => e.type === "added" && e.origin === "calculated" && e.keys.includes(created[0].key))).toBe(true);
    expect(await page.evaluate(() => wwSignalCatalogue.revision)).toBeGreaterThan(revisionBefore);
    // Raw signals are untouched and no reload happened.
    expect(await page.evaluate(() => wwSignalCatalogueList((s) => s.origin === "raw").length)).toBe(rawBefore);
    expect(await page.evaluate(() => window.__navigationMarker)).toBe("same-page-load");
    // The calculated signal carries its timing parent so a consumer can filter on it.
    expect(created[0].referenceSourceId).toBeTruthy();
  });

  test("delete removes it; re-creating the same name is a NEW identity, so an old result is stale", async ({ page }) => {
    await uploadFixture(page);
    await createRms(page);
    const [first] = await calculatedSignals(page);
    await observe(page);

    expect(await page.evaluate(([key, rev]) => wwSignalCatalogueIsCurrent(key, rev), [first.key, first.revision])).toBe(true);

    await page.evaluate((key) => wwCcDeleteChannel(key.replace("calculated:", "")), first.key);
    await expect.poll(async () => (await calculatedSignals(page)).length).toBe(0);
    const afterDelete = await page.evaluate(() => window.__signalEvents);
    expect(afterDelete.some((e) => e.type === "removed" && e.keys.includes(first.key))).toBe(true);
    expect(await page.evaluate(([key, rev]) => wwSignalCatalogueIsCurrent(key, rev), [first.key, first.revision])).toBe(false);

    await createRms(page);
    const [second] = await calculatedSignals(page);
    expect(second.name).toBe(first.name);
    expect(second.key).not.toBe(first.key);
    // The earlier result's key/revision no longer validates.
    expect(await page.evaluate(([key, rev]) => wwSignalCatalogueIsCurrent(key, rev), [first.key, first.revision])).toBe(false);
    expect(await page.evaluate(([key, rev]) => wwSignalCatalogueIsCurrent(key, rev), [second.key, second.revision])).toBe(true);
    expect(await page.evaluate(() => window.__navigationMarker)).toBe("same-page-load");
  });

  test("a backend refetch reports additions and removals without duplicating signals", async ({ page }) => {
    await uploadFixture(page);
    await createRms(page);
    await observe(page);
    const before = await calculatedSignals(page);

    // Unchanged list: replace-all is a no-op for observers, never a duplicate.
    await page.evaluate(() => wwFetchCalculatedChannels());
    expect(await calculatedSignals(page)).toEqual(before);
    expect(await page.evaluate(() => window.__signalEvents.length)).toBe(0);

    // Content change on the same id is an "updated", still one signal.
    await page.evaluate(() => {
      const channel = ww.calculatedChannels.get(Array.from(ww.calculatedChannels.keys())[0]);
      wwCalculatedChannelsUpsert([Object.assign({}, channel, { unit: "changed" })]);
    });
    const afterUpdate = await calculatedSignals(page);
    expect(afterUpdate).toHaveLength(1);
    const events = await page.evaluate(() => window.__signalEvents);
    expect(events.map((e) => e.type)).toEqual(["updated"]);

    // The backend list is authoritative: the refetch restores it and reports the update back.
    await page.evaluate(() => wwFetchCalculatedChannels());
    expect(await page.evaluate(() => Array.from(ww.calculatedChannels.values())[0].unit)).not.toBe("changed");
    expect((await page.evaluate(() => window.__signalEvents)).map((e) => e.type)).toEqual(["updated", "updated"]);
  });

  test("a throwing observer cannot break producers or other observers; unsubscribe works", async ({ page }) => {
    await uploadFixture(page);
    await page.evaluate(() => {
      window.__good = 0;
      wwSignalCatalogueSubscribe(() => { throw new Error("bad consumer"); });
      window.__off = wwSignalCatalogueSubscribe(() => { window.__good += 1; });
    });
    await createRms(page);
    expect((await calculatedSignals(page)).length).toBe(1);
    expect(await page.evaluate(() => window.__good)).toBeGreaterThan(0);
    const seen = await page.evaluate(() => { window.__off(); return window.__good; });
    await createRms(page, 1);
    expect(await page.evaluate(() => window.__good)).toBe(seen);
  });

  test("removing the recording removes its raw and dependent calculated signals", async ({ page }) => {
    await uploadFixture(page);
    await createRms(page);
    await observe(page);
    const sourceId = await page.evaluate(() => Array.from(ww.sourceChannelsData.keys())[0]);
    await page.evaluate((id) => performRemoveSource(id), sourceId);
    await expect.poll(async () => page.evaluate(() => wwSignalCatalogueList().length)).toBe(0);
    const events = await page.evaluate(() => window.__signalEvents);
    expect(events.some((e) => e.type === "removed" && e.origin === "raw")).toBe(true);
    expect(events.some((e) => e.type === "removed" && e.origin === "calculated")).toBe(true);
  });
  test("Calculated Channels builder candidates come from the catalogue: raw unchanged, live create/remove, no duplicates", async ({ page }) => {
    await uploadFixture(page);
    // Raw candidates: every analog channel of every loaded recording, in order, nothing else.
    const rawCandidates = await page.evaluate(() => wwCcAvailableCandidates().filter((c) => c.kind === "source").map((c) => c.sourceId + "::" + c.channelName));
    const expectedRaw = await page.evaluate(() => Array.from(ww.sourceChannelsData.values())
      .flatMap((d) => d.analog_channels.map((c) => d.source.source_id + "::" + c.name)));
    expect(rawCandidates).toEqual(expectedRaw);
    expect(await page.evaluate(() => wwCcAvailableCandidates().filter((c) => c.kind === "calculated").length)).toBe(0);

    await createRms(page);
    const withCalc = await page.evaluate(() => wwCcAvailableCandidates().map((c) => ({ kind: c.kind, id: c.calculatedChannelId, group: c.group })));
    const calcCandidates = withCalc.filter((c) => c.kind === "calculated");
    expect(calcCandidates).toHaveLength(1);
    expect(calcCandidates[0].group).toBe("Calculated Channels");
    // Raw first, calculated last, raw unchanged, no duplicates.
    expect(withCalc[withCalc.length - 1].kind).toBe("calculated");
    expect(withCalc.length).toBe(expectedRaw.length + 1);
    expect(await page.evaluate(() => wwCcAvailableCandidates().filter((c) => c.kind === "source").map((c) => c.sourceId + "::" + c.channelName))).toEqual(expectedRaw);

    // The builder offers the new channel as a picker input without a reload.
    await page.locator("#wwCcNewChannelBtn").click();
    await page.locator('.ww-cc-operation-card[data-operation="rms"]').click();
    const optionCount = await page.locator("#wwCcUnaryInputSelect option").evaluateAll((o) => o.filter((x) => x.value).length);
    expect(optionCount).toBeGreaterThan(0);
    await page.locator("#wwCcDrawerCloseBtn").click();

    await page.evaluate((id) => wwCcDeleteChannel(id), calcCandidates[0].id);
    await expect.poll(() => page.evaluate(() => wwCcAvailableCandidates().filter((c) => c.kind === "calculated").length)).toBe(0);
    expect(await page.evaluate(() => window.__navigationMarker ?? "unset")).toBe("unset");
  });
});
