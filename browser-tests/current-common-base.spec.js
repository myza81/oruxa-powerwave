// PC-001 Stage 5A: real backend saves, live Waveform/ER and automatic provenance.
//
// P0 remediation (PU-MIG): the editors this spec used -- the Per-Unit Settings Hub, the
// Measurement Group drawer (#wwMgBaseReferenceSide / #wwMgManualIbaseInput) and the
// Source Default dialog (#perUnitCurrentBaseSide) -- were removed from the frontend by
// PU-UI-001 (1c60a1e, 4161a63, be1e7e0); Recording Details edits only the equipment
// rating and CT of a Current group, never its manual Ibase or Base reference side.
// The same saves are therefore made through the real endpoints those editors called
// (PUT .../current-config and PUT /per-unit/sources/{source}, same bodies) and followed by
// the display refresh the editors ran after a successful save
// (wwRefreshDisplayedChannelsForPerUnitChange). Every numerical, provenance and
// atomic-rejection assertion is unchanged. Retired with the editors (reported in the P0
// handover): the drawer's visible-error element and its Cancel/Close controls.
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

// The body the retired Measurement Group drawer sent for a manual Current base.
const manualCurrent = (ibaseKa, side) => ({ method: "manual", manual_ibase_ka: ibaseKa, base_reference_side: side });

async function declaredSide(page, c, group) {
  const groups = await json(await page.request.get(c.groupsUrl));
  return groups.find(g => g.id === group.id).current_config.base_reference_side;
}

async function saveGroup(page, c, group, body, status = 200) {
  const response = await json(await page.request.put(`${c.groupsUrl}/${group.id}/current-config`, { data: body }), status);
  if (status === 200) await page.evaluate(sid => wwRefreshDisplayedChannelsForPerUnitChange(sid), c.sid);
  return response;
}

test("independent side declarations enable a common base; a rejected save preserves state and PU", async ({ page }) => {
  const c = await setup(page);
  await scaled(page, c, false);
  for (let i = 0; i < c.groups.length; i++) {
    expect(await declaredSide(page, c, c.groups[i])).toBe("unknown");
    await saveGroup(page, c, c.groups[i], manualCurrent(2, "primary"));
    await scaled(page, c, i === 1);
  }
  const beforeGroups = await json(await page.request.get(c.groupsUrl));
  const waveformUrl = `${c.base}/calculated-channels/${c.nested.id}/waveform?unit_mode=per_unit`;
  const beforeWaveform = await json(await page.request.get(waveformUrl));
  const rejected = await saveGroup(page, c, c.groups[1], manualCurrent(-2, "secondary"), 400);
  // The message the drawer used to show in its error element.
  expect(typeof rejected.detail.message).toBe("string");
  expect(rejected.detail.message.length).toBeGreaterThan(0);
  expect(await json(await page.request.get(c.groupsUrl))).toEqual(beforeGroups);
  expect(await json(await page.request.get(waveformUrl))).toEqual(beforeWaveform);
  await scaled(page, c, true);
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
    await json(await page.request.put(`${c.base}/per-unit/sources/${c.sid}`, { data: {
      current_base_mode: "direct", direct_current_base_value: 2, current_base_reference_side: side,
    } }));
    await page.evaluate(sid => wwRefreshDisplayedChannelsForPerUnitChange(sid), c.sid);
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
  await saveGroup(page, c, c.groups[1], manualCurrent(2, "secondary"));
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
