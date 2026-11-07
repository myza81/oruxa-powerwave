// PU-006/007: real editor/API rejection, numerical fallback and recovery.
const { test, expect } = require("./support/test");
const {
  BACKEND, uploadRecord, workspaceId, sourceIdFor, addRecords, selectChannel,
  channelRow, waitForPlot, plotState,
} = require("./support/event_reconstruction_helpers");

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

async function setup(page) {
  await page.goto("/index.html");
  const station = "NUMERIC_PU";
  await uploadRecord(page, {
    station, startClock: "10:00:00.000000", durationS: 1,
    channels: [{ name: "VA", unit: "kV", phase: "A", amplitude: 275 * Math.sqrt(2 / 3), frequencyHz: 50 }],
  });
  const ws = await workspaceId(page);
  const sid = await sourceIdFor(page, station);
  const root = `${BACKEND}/api/v1/workspaces/${ws}/sources/${sid}`;
  const group = (await json(await page.request.get(root + "/measurement-groups"))).find(g => g.kind === "voltage");
  const url = root + "/measurement-groups/" + group.id;
  await json(await page.request.put(url + "/voltage-config", { data: { nominal_voltage_ll_kv: 275 } }));
  await json(await page.request.patch(url, { data: { status: "confirmed" } }));
  await page.locator("#mainNavWaveformBtn").click();
  await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${sid}"][data-channel-name="VA"]`).click();
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(() => entry(page, sid)).toMatchObject({ unit: "pu", status: "configured" });
  return { ws, sid, root, group, url, station };
}

function entry(page, sid) {
  return page.evaluate(sid => {
    const c = ww.displayed.get(wwChannelKey(sid, "VA"))?.channel;
    return c && { unit: c.unit, values: c.values, status: c.perUnitStatus };
  }, sid);
}

for (const [label, value, status] of [["true", true, 422], ["false", false, 422], ["overflowing SI base", 1e308, 400]]) {
  test(`voltage editor rejects ${label} atomically, then accepts a practical base`, async ({ page }) => {
    const { sid, root, group, url } = await setup(page);
    const waveformUrl = root + "/waveform?channel_name=VA&unit_mode=per_unit";
    const provenanceUrl = root + "/per-unit-resolution?channel_name=VA";
    const before = await json(await page.request.get(url));
    const waveform = await json(await page.request.get(waveformUrl));
    const provenance = await json(await page.request.get(provenanceUrl));
    const displayed = await entry(page, sid);
    expect(Math.max(...displayed.values.map(Math.abs))).toBeCloseTo(Math.sqrt(2), 10);
    await page.locator("#wwOpenPerUnitSettingsBtn").click();
    await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
    await page.locator(`[id="wwMgEditBtn-${group.id}"]`).click();
    await page.locator("#wwMgVoltageKvInput").fill("132");
    // Alter only the outbound type/value to exercise actual API validation
    // through the real UI error handler. No responses/state are mocked.
    await page.route("**/measurement-groups/*/voltage-config", async route => {
      await route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), nominal_voltage_ll_kv: value }) });
    }, { times: 1 });
    const rejected = page.waitForResponse(r => r.url() === url + "/voltage-config" && r.request().method() === "PUT");
    await page.locator("#wwMgDrawerSaveBtn").click();
    expect((await rejected).status()).toBe(status);
    await expect(page.locator("#wwMgDrawerError")).toBeVisible();
    await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);
    expect(await json(await page.request.get(url))).toEqual(before);
    expect(await json(await page.request.get(waveformUrl))).toEqual(waveform);
    expect(await json(await page.request.get(provenanceUrl))).toEqual(provenance);
    expect(await entry(page, sid)).toEqual(displayed);
    await page.locator("#wwMgDrawerSaveBtn").click();
    await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await expect.poll(async () => Math.max(...(await entry(page, sid)).values.map(Math.abs))).toBeCloseTo(Math.sqrt(2) * 275 / 132, 10);
    expect((await json(await page.request.get(url))).voltage_config.nominal_voltage_ll_kv).toBe(132);
  });
}

test("valid tiny base reports numerical unavailability consistently in Waveform and ER and recovers", async ({ page }) => {
  const { sid, root, url, station, group } = await setup(page);
  const engineering = await json(await page.request.get(root + "/waveform?channel_name=VA"));
  await json(await page.request.put(url + "/voltage-config", { data: { nominal_voltage_ll_kv: 1e-320 } }));
  await page.evaluate(sid => wwRefreshDisplayedChannelsForPerUnitChange(sid), sid);
  await expect.poll(() => entry(page, sid)).toEqual({ unit: "kV", status: "base_required", values: engineering.values });
  const provenance = await json(await page.request.get(root + "/per-unit-resolution?channel_name=VA"));
  expect(provenance.status).toBe("base_required");
  expect(provenance.reason).toContain("cannot be represented");
  expect(provenance.nominal_base_kv).toBe(1e-320);
  await addRecords(page, [station]);
  // Establish ENG before comparing its physical trace with PU fallback.
  await page.locator("#wwErUnitEngineeringBtn").click();
  await selectChannel(page, station, "VA");
  await waitForPlot(page, 1);
  const erEngineering = await plotState(page);
  await page.locator("#wwErUnitPerUnitBtn").click();
  const row = await channelRow(page, station, "VA");
  await expect(row.locator(".ww-er-pu-unavailable")).toHaveText("PU unavailable");
  await expect(row).toHaveAttribute("aria-pressed", "true");
  await waitForPlot(page, 0);
  await expect(page.locator("#wwErUnitNotice")).toContainText("1 selected channel");
  expect((await plotState(page)).panels).toEqual([]);
  await page.locator("#wwErUnitEngineeringBtn").click();
  await waitForPlot(page, 1);
  expect((await plotState(page)).panels[0].values).toEqual(erEngineering.panels[0].values);
  // Configure in the actual editor, then return to ER. ER refreshes its
  // resolution cache on page entry, matching the supported user workflow.
  await page.locator("#mainNavWaveformBtn").click();
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${group.id}"]`).click();
  await page.locator("#wwMgVoltageKvInput").fill("275");
  await page.locator("#wwMgDrawerSaveBtn").click();
  await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
  await page.locator("#measurementGroupsCloseBtn").click();
  await expect(page.locator("#measurementGroupsOverlay")).toBeHidden();
  await page.locator("#mainNavEventReconstructionBtn").click();
  await page.locator("#wwErUnitPerUnitBtn").click();
  await waitForPlot(page, 1);
  await expect(row.locator(".ww-er-pu-unavailable")).toHaveCount(0);
  expect(Math.max(...(await plotState(page)).panels[0].values.map(Math.abs))).toBeCloseTo(Math.sqrt(2), 10);
  expect(await json(await page.request.get(root + "/waveform?channel_name=VA"))).toEqual(engineering);
});
