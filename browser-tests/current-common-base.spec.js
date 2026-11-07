// PC-001 Stage 5A: real existing editors, live Waveform/ER and automatic provenance.
const { test, expect } = require("./support/test");
const {
  BACKEND, uploadRecord, workspaceId, sourceIdFor, addRecords, selectChannel,
  channelRow, waitForPlot, plotState,
} = require("./support/event_reconstruction_helpers");

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

async function setup(page, { side = "unknown", mixed = false } = {}) {
  await page.goto("/index.html");
  const station = "CURRENT_COMMON";
  await uploadRecord(page, { station, startClock: "10:00:00.000000", durationS: 0.2,
    channels: [
      { name: "IA", unit: "A", phase: "A", amplitude: 2000, frequencyHz: 50 },
      { name: "IB", unit: "A", phase: "B", amplitude: 4000, frequencyHz: 50 },
    ],
  });
  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`;
  const groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const g of await json(await page.request.get(groupsUrl))) {
    expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  }
  const groups = [];
  for (const name of mixed ? ["IA"] : ["IA", "IB"]) {
    const g = await json(await page.request.post(groupsUrl, { data: {
      kind: "current", display_name: `Input ${name}`, status: "confirmed",
      channel_refs: [{ kind: "source", source_id: sid, channel_name: name }],
    } }), 201);
    await json(await page.request.put(`${groupsUrl}/${g.id}/current-config`, { data: {
      method: "manual", manual_ibase_ka: 2, base_reference_side: side,
    } }));
    groups.push(g);
  }
  await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: {
    current_base_mode: "direct", direct_current_base_value: mixed ? 2 : 1,
  } }));
  const sum = await json(await page.request.post(`${base}/calculated-channels`, { data: {
    name: "Current sum", operation: "addition", inputs: ["IA", "IB"].map(channel_name => ({
      kind: "source", source_id: sid, channel_name,
    })),
  } }), 201);
  const nested = await json(await page.request.post(`${base}/calculated-channels`, { data: {
    name: "Magnitude sum", operation: "absolute_value", inputs: [{ kind: "calculated", calculated_channel_id: sum.id }],
  } }), 201);
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwFetchCalculatedChannels());
  const row = page.locator(`tr.channel-row--toggle[data-source-id="${nested.id}"]`);
  await row.click();
  const physical = await json(await page.request.get(`${base}/calculated-channels/${nested.id}/waveform`));
  await page.locator("#wwUnitPerUnitBtn").click();
  return { station, sid, base, groupsUrl, groups, nested, row, physical };
}

function displayed(page, cid) {
  return page.evaluate(cid => {
    const c = Array.from(ww.displayed.values()).find(e => e.channel.sourceId === cid)?.channel;
    return c && { unit: c.unit, status: c.perUnitStatus, values: c.values };
  }, cid);
}

async function scaled(page, context, eligible) {
  let data;
  await expect.poll(async () => {
    data = await displayed(page, context.nested.id);
    return data && { status: data.status, unit: data.unit, count: data.values.length };
  }).toEqual({
    status: eligible ? "configured" : "base_required", unit: eligible ? "pu" : "A",
    count: context.physical.values.length,
  });
  // Assert the accepted complete snapshot: a live edit retires arrays while
  // status/unit can legitimately remain unchanged during the pending fetch.
  expect(data.values.length).toBe(context.physical.values.length);
  data.values.forEach((v, i) => expect(v).toBeCloseTo(context.physical.values[i] / (eligible ? 2000 : 1), 10));
}

async function editGroup(page, group) {
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${group.id}"]`).click();
}

async function saveGroup(page) {
  await page.locator("#wwMgDrawerSaveBtn").click();
  await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
  await page.locator("#measurementGroupsCloseBtn").click();
}

test("independent side declarations enable a common base; a rejected save preserves state and PU", async ({ page }) => {
  const c = await setup(page);
  await scaled(page, c, false);
  for (let i = 0; i < c.groups.length; i++) {
    await editGroup(page, c.groups[i]);
    await expect(page.locator("#wwMgBaseReferenceSide")).toHaveValue("unknown");
    await page.locator("#wwMgBaseReferenceSide").selectOption("primary");
    await saveGroup(page);
    await scaled(page, c, i === 1);
  }
  const beforeGroups = await json(await page.request.get(c.groupsUrl));
  const waveformUrl = `${c.base}/calculated-channels/${c.nested.id}/waveform?unit_mode=per_unit`;
  const beforeWaveform = await json(await page.request.get(waveformUrl));
  await editGroup(page, c.groups[1]);
  await page.locator("#wwMgBaseReferenceSide").selectOption("secondary");
  await page.locator("#wwMgManualIbaseInput").fill("-2");
  const rejected = page.waitForResponse(r => r.url().endsWith("/current-config") && r.request().method() === "PUT");
  await page.locator("#wwMgDrawerSaveBtn").click();
  expect((await rejected).status()).toBe(400);
  await expect(page.locator("#wwMgDrawerError")).toBeVisible();
  expect(await json(await page.request.get(c.groupsUrl))).toEqual(beforeGroups);
  expect(await json(await page.request.get(waveformUrl))).toEqual(beforeWaveform);
  await scaled(page, c, true);
  await page.locator("#wwMgDrawerCancelBtn").click();
  await page.locator("#measurementGroupsCloseBtn").click();
  await c.row.click({ button: "right" });
  await page.locator("#wwChannelMenuPerUnitBtn").click();
  await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Automatic common current base");
  await expect(page.locator("#wwChannelPerUnitBody")).toContainText("2.00 kA");
  const provenance = await json(await page.request.get(`${c.base}/calculated-channels/${c.nested.id}/per-unit-resolution`));
  expect(provenance).toMatchObject({ status: "configured", source_kind: null, measurement_group_id: null,
    resolution_origin: "automatic_common_base", measurement_side: "primary", base_reference_side: "primary", effective_base_amount: 2 });
});

test("direct Source Default side changes refresh a mixed-authority result without changing its group", async ({ page }) => {
  const c = await setup(page, { mixed: true, side: "primary" });
  const groups = await json(await page.request.get(c.groupsUrl));
  await scaled(page, c, false);
  for (const side of ["primary", "unknown"]) {
    await page.locator("#wwOpenPerUnitSettingsBtn").click();
    await page.locator("#wwOpenPerUnitProfilesFromSettingsBtn").click();
    await page.locator("#perUnitSourceSelect").selectOption(c.sid);
    await page.locator("#perUnitCurrentBaseSide").selectOption(side);
    await page.locator("#perUnitProfilesApplyBtn").click();
    await expect(page.locator("#perUnitProfilesOverlay")).toBeHidden();
    await scaled(page, c, side === "primary");
    expect(await json(await page.request.get(c.groupsUrl))).toEqual(groups);
  }
});

test("nested Current common base is consistent in ER and preserves ENG and selection after incompatibility", async ({ page }) => {
  const c = await setup(page, { side: "primary" });
  await scaled(page, c, true);
  await addRecords(page, [c.station]);
  await page.locator("#wwErUnitEngineeringBtn").click();
  await selectChannel(page, c.station, c.nested.name);
  await waitForPlot(page, 1);
  const eng = (await plotState(page)).panels[0];
  await page.locator("#wwErUnitPerUnitBtn").click();
  await waitForPlot(page, 1);
  const pu = (await plotState(page)).panels[0];
  expect(pu.unit).toBe("pu");
  pu.values.forEach((v, i) => expect(v).toBeCloseTo(eng.values[i] / 2000, 10));
  await page.locator("#mainNavWaveformBtn").click();
  await editGroup(page, c.groups[1]);
  await page.locator("#wwMgBaseReferenceSide").selectOption("secondary");
  await saveGroup(page);
  await scaled(page, c, false);
  await page.locator("#mainNavEventReconstructionBtn").click();
  const row = await channelRow(page, c.station, c.nested.name);
  await expect(row).toHaveAttribute("aria-pressed", "true");
  await expect(row.locator(".ww-er-pu-unavailable")).toHaveText("PU unavailable");
  await waitForPlot(page, 0);
  await page.locator("#wwErUnitEngineeringBtn").click();
  await waitForPlot(page, 1);
  expect((await plotState(page)).panels[0].values).toEqual(eng.values);
});
