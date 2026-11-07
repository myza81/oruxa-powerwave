// Audit PU-003: real CSV preparation, configuration, Waveform and ER.
// No response mocking: missing units stay absent throughout conversion.
const { test, expect } = require("./support/test");
const {
  BACKEND, workspaceId, addRecords, selectChannel, channelRow, waitForPlot, plotState,
} = require("./support/event_reconstruction_helpers");

async function json(response, expected = 200) {
  expect(response.status(), await response.text()).toBe(expected);
  return response.json();
}

async function setup(page, unit = "") {
  await page.goto("/index.html");
  const ws = await workspaceId(page);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`;
  const source = await json(await page.request.post(`${base}/preparation-sources`, { multipart: {
    csv_file: { name: "Unit-eligibility.csv", mimeType: "text/csv", buffer: Buffer.from(
      "Time,VR\n2026-11-03T10:00:00.000Z,1.32\n2026-11-03T10:00:00.010Z,1.33\n2026-11-03T10:00:00.020Z,1.31\n"
    ) },
  } }), 201);
  const prep = `${base}/preparation-sources/${source.source_id}/working`;
  for (const [suffix, data] of [
    ["header", { row_number: 1 }], ["data-region", { start_row: 2, end_row: 4 }],
    ["columns/0/role", { role: "time_axis" }], ["columns/1/role", { role: "waveform" }],
    ["columns/1/engineering-quantity", { engineering_quantity: "Voltage" }],
    ["time-axis", { column_indices: [0], interpreter_id: "absolute_datetime", confirmed: true }],
  ]) await json(await page.request.put(`${prep}/${suffix}`, { data }));
  if (unit) await json(await page.request.put(`${prep}/columns/1/measured-unit`, { data: { measured_unit: unit } }));
  const converted = await json(await page.request.post(`${base}/preparation-sources/${source.source_id}/convert`));
  const sid = converted.source_id;
  const groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const group of await json(await page.request.get(groupsUrl))) {
    expect((await page.request.delete(`${groupsUrl}/${group.id}`)).status()).toBe(204);
  }
  await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: { voltage_base_value: 132 } }));
  await page.evaluate(() => refreshAllSourceViews());
  return { base, sid, station: converted.station_name };
}

function entry(page, sid) {
  return page.evaluate(sid => {
    const value = ww.displayed.get(wwChannelKey(sid, "VR"));
    return value && { unit: value.channel.unit, values: value.channel.values, status: value.channel.perUnitStatus };
  }, sid);
}

async function showWaveform(page, sid) {
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await details.locator('tr.channel-row--toggle[data-channel-name="VR"]').click();
  await expect.poll(() => entry(page, sid)).toMatchObject({ values: [1.32, 1.33, 1.31] });
}

test("missing unit: coverage, provenance and Waveform fallback agree, including accepted base edits", async ({ page }) => {
  const { base, sid } = await setup(page);
  await showWaveform(page, sid);
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(() => entry(page, sid)).toEqual({ unit: "", values: [1.32, 1.33, 1.31], status: "base_required" });
  const provenance = await json(await page.request.get(`${base}/sources/${sid}/per-unit-resolution?channel_name=VR`));
  expect(provenance).toMatchObject({ status: "base_required", source_kind: "source_default", nominal_base_kv: 132 });
  expect(provenance.reason).toContain("measured unit");
  expect(provenance.effective_base_amount).toBeCloseTo(132 / Math.sqrt(3), 10);
  await page.evaluate(() => wwOpenPerUnitSettingsModal());
  await expect(page.locator("#wwPuCoverageBody")).toContainText("Needs configuration");
  const coverage = await json(await page.request.get(`${base}/per-unit/sources/${sid}/coverage`));
  expect(coverage).toEqual({ source_id: sid, applicable_channel_count: 1, measurement_group_count: 0,
    source_default_count: 0, needs_configuration_count: 1, unverified_reference_count: 0 });
  await page.evaluate(() => wwClosePerUnitSettingsModal());
  // The real accepted save is followed by the same source-scoped display
  // refresh used by the editor. No unit or previous PU value is invented.
  await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: { voltage_base_value: 275 } }));
  await page.evaluate(sid => wwRefreshDisplayedChannelsForPerUnitChange(sid), sid);
  await expect.poll(() => entry(page, sid)).toEqual({ unit: "", values: [1.32, 1.33, 1.31], status: "base_required" });
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect.poll(() => entry(page, sid)).toEqual({ unit: "", values: [1.32, 1.33, 1.31], status: null });
});

test("missing unit: Event Reconstruction keeps selection unavailable and restores engineering values", async ({ page }) => {
  const { station } = await setup(page);
  await addRecords(page, [station]);
  await selectChannel(page, station, "VR");
  await waitForPlot(page, 1);
  const engineering = await plotState(page);
  await page.locator("#wwErUnitPerUnitBtn").click();
  const row = await channelRow(page, station, "VR");
  await expect(row.locator(".ww-er-pu-unavailable")).toHaveText("PU unavailable");
  await expect(row).toHaveAttribute("aria-pressed", "true");
  await waitForPlot(page, 0);
  await expect(page.locator("#wwErUnitNotice")).toContainText("1 selected channel");
  expect((await plotState(page)).panels).toEqual([]);
  await page.locator("#wwErUnitEngineeringBtn").click();
  await waitForPlot(page, 1);
  const restored = await plotState(page);
  expect(restored.panels[0].values).toEqual(engineering.panels[0].values);
  expect(restored.panels[0].r).toEqual(engineering.panels[0].r);
  await expect(row.locator(".ww-er-pu-unavailable")).toHaveCount(0);
});

test("valid measured kV: Source Default auto reference agrees in Waveform and Event Reconstruction", async ({ page }) => {
  const { base, sid, station } = await setup(page, "kV");
  await showWaveform(page, sid);
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(() => entry(page, sid)).toMatchObject({ unit: "pu", status: "configured" });
  const waveform = await entry(page, sid);
  const expected = [1.32, 1.33, 1.31].map(v => v / (132 / Math.sqrt(3)));
  expect(waveform.values).toHaveLength(3);
  waveform.values.forEach((v, i) => expect(v).toBeCloseTo(expected[i], 12));
  const coverage = await json(await page.request.get(`${base}/per-unit/sources/${sid}/coverage`));
  expect(coverage).toMatchObject({ source_default_count: 1, needs_configuration_count: 0 });
  await addRecords(page, [station]);
  await selectChannel(page, station, "VR");
  await page.locator("#wwErUnitPerUnitBtn").click();
  await waitForPlot(page, 1);
  const reconstruction = (await plotState(page)).panels[0];
  expect(reconstruction.unit).toBe("pu");
  expect(reconstruction.values).toEqual(waveform.values);
});
