// Slice 1: real editor save/rejection against the real local API.
const { test, expect } = require("./support/test");
const { BACKEND, uploadRecord, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

test("a rejected voltage editor save preserves the base and plotted PU; accepted save updates both", async ({ page }) => {
  await page.goto("/index.html");
  await uploadRecord(page, {
    station: "ATOMIC_PU", startClock: "10:00:00.000000", durationS: 1,
    channels: [{ name: "VA", unit: "kV", phase: "A", amplitude: 275 / Math.sqrt(3) * Math.sqrt(2), frequencyHz: 50 }],
  });
  const workspace = await workspaceId(page);
  const source = await sourceIdFor(page, "ATOMIC_PU");
  const root = `${BACKEND}/api/v1/workspaces/${workspace}/sources/${source}`;
  const groups = await (await page.request.get(root + "/measurement-groups")).json();
  const group = groups.find(g => g.kind === "voltage");
  const url = root + "/measurement-groups/" + group.id;
  expect((await page.request.put(url + "/voltage-config", { data: { nominal_voltage_ll_kv: 275 } })).ok()).toBe(true);
  expect((await page.request.patch(url, { data: { status: "confirmed" } })).ok()).toBe(true);
  await page.locator("#mainNavWaveformBtn").click();
  await page.locator(`#channelGroups tr.channel-row--toggle[data-source-id="${source}"][data-channel-name="VA"]`).click();
  await page.locator("#wwUnitPerUnitBtn").click();
  const peak = () => page.evaluate(() => Math.max(...ww.panels.flatMap(p => p.channels.flatMap(c => c.values)).map(Math.abs)));
  await expect.poll(peak).toBeCloseTo(Math.sqrt(2), 10);
  const before = await (await page.request.get(url)).json();
  const waveformUrl = root + "/waveform?channel_name=VA&unit_mode=per_unit";
  const waveformBefore = await (await page.request.get(waveformUrl)).json();
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${group.id}"]`).click();
  await page.locator("#wwMgVoltageKvInput").fill("132");
  // Simulate an incomplete client request while retaining the real UI error
  // handling and real backend validation. No response or state is mocked.
  await page.route("**/measurement-groups/*/voltage-config", async route => {
    const body = route.request().postDataJSON();
    body.reference_mode = "manual";
    delete body.reference_override;
    await route.continue({ postData: JSON.stringify(body) });
  }, { times: 1 });
  const rejected = page.waitForResponse(r => r.url() === url + "/voltage-config" && r.request().method() === "PUT");
  await page.locator("#wwMgDrawerSaveBtn").click();
  expect((await rejected).status()).toBe(400);
  await expect(page.locator("#wwMgDrawerError")).toBeVisible();
  await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);
  expect(await (await page.request.get(url)).json()).toEqual(before);
  expect(await (await page.request.get(waveformUrl)).json()).toEqual(waveformBefore);
  expect(await peak()).toBeCloseTo(Math.sqrt(2), 10);

  // The same open form can then successfully save its actual auto-reference body.
  await page.locator("#wwMgDrawerSaveBtn").click();
  await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
  await expect.poll(peak).toBeCloseTo(Math.sqrt(2) * 275 / 132, 10);
  const accepted = await (await page.request.get(url)).json();
  expect(accepted.voltage_config.nominal_voltage_ll_kv).toBe(132);
  expect(accepted.voltage_config.reference_mode).toBe("auto");
});
