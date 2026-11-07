// PU-005/008: real arrays and rendered cursor values, with controlled request timing.
const { test, expect } = require("./support/test");
const { BACKEND, uploadRecord, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");
const fs = require("node:fs");
const path = require("node:path");
let evidenceIndex = 0;

const NOMINAL_KV = 275;
const PEAK_KV = NOMINAL_KV * Math.sqrt(2 / 3);
const row = (page, source, name = "VA") => page.locator(
  `tr.channel-row--toggle[data-source-id="${source}"][data-channel-name="${name}"]`
);

async function setup(page, { station = "SYNC_PU", sourceDefault = false, extraChannels = [] } = {}) {
  await page.goto("/index.html");
  await uploadRecord(page, {
    station, startClock: "10:00:00.000000", durationS: 0.2,
    channels: [
      { name: "VA", unit: "kV", phase: "A", amplitude: PEAK_KV, frequencyHz: 50 },
      { name: "IA", unit: "kA", phase: "A", amplitude: 4.2, frequencyHz: 50 },
    ].concat(extraChannels),
  });
  const workspace = await workspaceId(page);
  const source = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${workspace}`;
  const groupsUrl = `${base}/sources/${source}/measurement-groups`;
  for (const g of await (await page.request.get(groupsUrl)).json()) {
    expect((await page.request.delete(`${groupsUrl}/${g.id}`)).ok()).toBe(true);
  }
  let voltage;
  if (sourceDefault) {
    expect((await page.request.put(`${base}/per-unit/sources/${source}`, {
      data: { voltage_base_value: NOMINAL_KV },
    })).ok()).toBe(true);
  } else {
    const response = await page.request.post(groupsUrl, { data: {
      kind: "voltage", display_name: "HV", status: "confirmed",
      channel_refs: [{ kind: "source", source_id: source, channel_name: "VA" }],
    } });
    expect(response.ok()).toBe(true);
    voltage = await response.json();
    expect((await page.request.put(`${groupsUrl}/${voltage.id}/voltage-config`, {
      data: { nominal_voltage_ll_kv: NOMINAL_KV },
    })).ok()).toBe(true);
  }
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${source}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await row(page, source).click();
  await expect.poll(() => channelState(page, source)).toMatchObject({ unit: "kV", peak: PEAK_KV });
  // Observe completion of the actual button handlers, including obsolete continuations.
  await page.evaluate(() => {
    window.unitJobs = [];
    const apply = wwApplyUnitMode;
    wwApplyUnitMode = mode => { const job = apply(mode); window.unitJobs.push(job); return job; };
  });
  return { workspace, source, base, groupsUrl, voltage };
}

function channelState(page, source, name = "VA") {
  return page.evaluate(({ source, name }) => {
    const entry = ww.displayed.get(wwChannelKey(source, name));
    return entry && { unit: entry.channel.unit, peak: Math.max(...entry.channel.values.map(Math.abs)) };
  }, { source, name });
}

async function cursors(page, source, { a = true, b = true, times = [0.005, 0.015] } = {}) {
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async ({ source, a, b, times }) => {
    const group = wwTimeGroupIdForDisplaySourceId(source);
    const state = wwTimeGroupCursorState(group);
    state.a.visible = a; state.a.time = times[0];
    state.b.visible = b; state.b.time = times[1];
    wwUpdateAllCursorOverlays();
    await Promise.all(Array.from(wwSourceIdsForTimeGroup(group), id => wwFetchCursorValuesForSource(id)));
  }, { source, a, b, times });
}

async function expectCursors(page, source, value, { a = true, b = true, name = "VA", bValue = -value, times = [0.005, 0.015] } = {}) {
  for (const [kind, visible, expected] of [["a", a, value], ["b", b, bValue]]) {
    const cell = row(page, source, name).locator(`.cur-value--${kind}`);
    if (!visible) await expect(cell).toHaveText("\u2014");
    else await expect.poll(async () => Number(await cell.textContent())).toBeCloseTo(expected, Math.abs(expected) < 1 ? 3 : 1);
  }
  expect(await page.evaluate(source => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(source));
    return [state.a.time, state.b.time];
  }, source)).toEqual(times);
  const group = await page.evaluate(source => wwTimeGroupIdForDisplaySourceId(source), source);
  await expect(page.locator(`.ww-time-group-canvas[data-time-group-id="${group}"] .ww-tg-cursor-readout-value--delta`))
    .toHaveText(a && b ? "10.000 ms" : "\u2014");
  const evidence = await page.evaluate(({ source, name }) => ({
    source, name, mode: ww.unitMode,
    unit: ww.displayed.get(wwChannelKey(source, name)).channel.unit,
    cursor: ww.cursorValues.get(wwChannelKey(source, name)),
  }), { source, name });
  evidence.rendered = await row(page, source, name).locator(".cur-value").allTextContents();
  evidence.expected = { a: a ? value : null, b: b ? bValue : null, times };
  const evidencePath = test.info().outputPath(`cursor-values-${++evidenceIndex}.json`);
  fs.mkdirSync(path.dirname(evidencePath), { recursive: true });
  fs.writeFileSync(evidencePath, JSON.stringify(evidence, null, 2), "utf8");
  await test.info().attach(`${name}-${evidence.mode}-cursor-values`, { path: evidencePath, contentType: "application/json" });
}

async function switchMode(page, mode) {
  await page.locator(mode === "per_unit" ? "#wwUnitPerUnitBtn" : "#wwUnitEngineeringBtn").click();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expect(page.locator(mode === "per_unit" ? "#wwUnitPerUnitBtn" : "#wwUnitEngineeringBtn"))
    .toHaveAttribute("aria-pressed", "true");
}

async function holdResponse(page, pattern, predicate = () => true) {
  let release, entered;
  const blocked = new Promise(resolve => { release = resolve; });
  const reached = new Promise(resolve => { entered = resolve; });
  await page.route(pattern, async route => {
    if (!predicate(route.request())) return route.continue();
    const response = await route.fetch();
    entered();
    await blocked;
    await route.fulfill({ response });
  }, { times: 1 });
  return { reached, release };
}

for (const visibility of [{ a: true, b: true }, { a: true, b: false }, { a: false, b: true }]) {
  test(`cursor values follow repeated ENG/PU transitions without movement (${JSON.stringify(visibility)})`, async ({ page }) => {
    const { source } = await setup(page);
    await cursors(page, source, visibility);
    await expectCursors(page, source, PEAK_KV, visibility);
    for (const mode of ["per_unit", "engineering", "per_unit"]) {
      await switchMode(page, mode);
      await expectCursors(page, source, mode === "per_unit" ? Math.sqrt(2) : PEAK_KV, visibility);
      expect((await channelState(page, source)).unit).toBe(mode === "per_unit" ? "pu" : "kV");
    }
  });
}

test("latest Engineering selection wins over delayed PU metadata", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/per-unit/sources");
  await page.locator("#wwUnitPerUnitBtn").click();
  await held.reached;
  await page.locator("#wwUnitEngineeringBtn").click();
  held.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expect(page.locator("#wwUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
  expect(await channelState(page, source)).toEqual({ unit: "kV", peak: PEAK_KV });
  await expectCursors(page, source, PEAK_KV);
});

test("real Voltage Group save refreshes fixed cursors and rejects an old cursor response", async ({ page }) => {
  const { source, voltage } = await setup(page);
  await cursors(page, source);
  await switchMode(page, "per_unit");
  // Seed a correct PU cursor state so this independently reproduces the
  // base-edit defect even on the old mode-switch implementation.
  await page.evaluate(source => wwFetchCursorValuesForSource(source), source);
  // Position setup is complete; only display changes below may trigger refreshes.
  await expectCursors(page, source, Math.sqrt(2));
  const held = await holdResponse(page, "**/cursor-values");
  await page.evaluate(source => { window.oldCursorJob = wwFetchCursorValuesForSource(source); }, source);
  await held.reached;
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${voltage.id}"]`).click();
  await page.locator("#wwMgVoltageKvInput").fill("132");
  await page.locator("#wwMgDrawerSaveBtn").click();
  await expect.poll(async () => (await channelState(page, source)).peak).toBeCloseTo(Math.sqrt(2) * 275 / 132, 10);
  await expectCursors(page, source, Math.sqrt(2) * 275 / 132);
  held.release();
  await page.evaluate(() => window.oldCursorJob);
  await expectCursors(page, source, Math.sqrt(2) * 275 / 132);
});

test("Source Default save and clear update fixed cursors through the real editor", async ({ page }) => {
  const { source } = await setup(page, { sourceDefault: true });
  await cursors(page, source);
  await switchMode(page, "per_unit");
  await expectCursors(page, source, Math.sqrt(2));
  const open = async () => {
    await page.locator("#wwOpenPerUnitSettingsBtn").click();
    await page.locator("#wwOpenPerUnitProfilesFromSettingsBtn").click();
    await page.locator("#perUnitSourceSelect").selectOption(source);
  };
  await open();
  await page.locator("#perUnitVoltageBaseValue").fill("132");
  await page.locator("#perUnitProfilesApplyBtn").click();
  await expectCursors(page, source, Math.sqrt(2) * 275 / 132);
  expect((await channelState(page, source)).unit).toBe("pu");
  await open();
  page.once("dialog", dialog => dialog.accept());
  await page.locator("#perUnitDeleteProfileBtn").click();
  await expectCursors(page, source, PEAK_KV);
  await expect.poll(async () => (await channelState(page, source)).unit).toBe("kV");
});

test("fresh cursor values are unavailable while the new basis response is pending", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/cursor-values", request => request.postDataJSON().unit_mode === "per_unit");
  await page.locator("#wwUnitPerUnitBtn").click();
  await held.reached;
  await expect(row(page, source).locator(".cur-value--a")).toHaveText("\u2014");
  await expect(row(page, source).locator(".cur-value--b")).toHaveText("\u2014");
  await expect(page.locator("#wwZoomXInBtn")).toBeEnabled();
  held.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expectCursors(page, source, Math.sqrt(2));
});

test("an Engineering cursor response cannot overwrite the later PU values", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/cursor-values");
  await page.evaluate(source => { window.oldCursorJob = wwFetchCursorValuesForSource(source); }, source);
  await held.reached;
  await switchMode(page, "per_unit");
  await expectCursors(page, source, Math.sqrt(2));
  held.release();
  await page.evaluate(() => window.oldCursorJob);
  await expectCursors(page, source, Math.sqrt(2));
});

test("delayed PU waveform cannot override a later Engineering selection", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, `**/sources/${source}/waveform?**`, request => new URL(request.url()).searchParams.get("unit_mode") === "per_unit");
  await page.locator("#wwUnitPerUnitBtn").click();
  await held.reached;
  await page.locator("#wwUnitEngineeringBtn").click();
  held.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expect(page.locator("#wwUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
  expect(await channelState(page, source)).toEqual({ unit: "kV", peak: PEAK_KV });
  await expectCursors(page, source, PEAK_KV);
});

test("rapid ENG-PU-ENG-PU intent wins even when the oldest metadata finishes last", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/per-unit/sources");
  await page.locator("#wwUnitPerUnitBtn").click();
  await held.reached;
  await page.locator("#wwUnitEngineeringBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  held.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expect(page.locator("#wwUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
  await expectCursors(page, source, Math.sqrt(2));
  expect((await channelState(page, source)).unit).toBe("pu");
});

test("failed optional metadata cannot prevent the requested PU display", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  await page.route("**/per-unit/sources", route => route.abort("failed"), { times: 1 });
  await switchMode(page, "per_unit");
  await expectCursors(page, source, Math.sqrt(2));
  await switchMode(page, "engineering");
  await expectCursors(page, source, PEAK_KV);
});

for (const action of ["source removal", "workspace reset"]) {
  test(`${action} cannot resurrect a delayed cursor result`, async ({ page }) => {
    const { source } = await setup(page);
    await cursors(page, source);
    const held = await holdResponse(page, "**/cursor-values");
    await page.evaluate(source => { window.oldCursorJob = wwFetchCursorValuesForSource(source); }, source);
    await held.reached;
    if (action === "source removal") await page.evaluate(source => performRemoveSource(source), source);
    else await page.evaluate(() => wwClearWorkspace({ resetSourceBounds: true }));
    held.release();
    await page.evaluate(() => window.oldCursorJob);
    expect(await page.evaluate(() => ({ values: ww.cursorValues.size, displayed: ww.displayed.size })))
      .toEqual({ values: 0, displayed: 0 });
  });
}

test("reset during delayed PU metadata cannot restore the old mode or arrays", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/per-unit/sources");
  await page.locator("#wwUnitPerUnitBtn").click();
  await held.reached;
  await page.evaluate(() => wwClearWorkspace({ resetSourceBounds: true }));
  held.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  expect(await page.evaluate(() => ({ mode: ww.unitMode, values: ww.cursorValues.size, displayed: ww.displayed.size, configs: ww.perUnitSourceConfigs.size })))
    .toEqual({ mode: "engineering", values: 0, displayed: 0, configs: 0 });
});

async function addGroup(page, context, kind, names, configuration) {
  const response = await page.request.post(context.groupsUrl, { data: {
    kind, display_name: names.join(" + "), status: "confirmed",
    channel_refs: names.map(channel_name => ({ kind: "source", source_id: context.source, channel_name })),
  } });
  expect(response.ok()).toBe(true);
  const group = await response.json();
  expect((await page.request.put(`${context.groupsUrl}/${group.id}/${kind}-config`, { data: configuration })).ok()).toBe(true);
  return group;
}

test("a Voltage base edit refreshes linked Current while other groups keep their bases", async ({ page }) => {
  const context = await setup(page, { extraChannels: [
    { name: "LOW VA", unit: "kV", phase: "A", amplitude: 132 * Math.sqrt(2 / 3), frequencyHz: 50 },
    { name: "MANUAL IA", unit: "kA", phase: "A", amplitude: 3, frequencyHz: 50 },
  ] });
  const { source, voltage } = context;
  await addGroup(page, context, "current", ["IA"], { method: "equipment_rating", equipment_rating_mva: 1000, linked_voltage_group_id: voltage.id });
  await addGroup(page, context, "voltage", ["LOW VA"], { nominal_voltage_ll_kv: 132 });
  await addGroup(page, context, "current", ["MANUAL IA"], { method: "manual", manual_ibase_ka: 1.5 });
  for (const name of ["IA", "LOW VA", "MANUAL IA"]) await row(page, source, name).click();
  await cursors(page, source);
  await switchMode(page, "per_unit");
  await expectCursors(page, source, 4.2 / (1000 / (Math.sqrt(3) * 275)), { name: "IA" });
  await expectCursors(page, source, Math.sqrt(2), { name: "LOW VA" });
  await expectCursors(page, source, 2, { name: "MANUAL IA" });
  expect((await page.request.put(`${context.groupsUrl}/${voltage.id}/voltage-config`, { data: { nominal_voltage_ll_kv: 132 } })).ok()).toBe(true);
  await page.evaluate(source => wwRefreshDisplayedChannelsForPerUnitChange(source), source);
  await expectCursors(page, source, Math.sqrt(2) * 275 / 132);
  await expectCursors(page, source, 4.2 / (1000 / (Math.sqrt(3) * 132)), { name: "IA" });
  await expectCursors(page, source, Math.sqrt(2), { name: "LOW VA" });
  await expectCursors(page, source, 2, { name: "MANUAL IA" });
});

test("calculated Voltage, Current and Power cursors retain eligibility and units", async ({ page }) => {
  const context = await setup(page);
  await addGroup(page, context, "current", ["IA"], { method: "manual", manual_ibase_ka: 2.1 });
  const definitions = [
    { name: "Double VA", operation: "multiply_constant", parameters: { constant: 2 }, names: ["VA"] },
    { name: "Negative IA", operation: "reverse_polarity", parameters: {}, names: ["IA"] },
    { name: "Power", operation: "active_power", parameters: {}, names: ["VA", "IA"] },
  ];
  const calculated = [];
  for (const { names, ...definition } of definitions) {
    const response = await page.request.post(`${context.base}/calculated-channels`, { data: {
      ...definition, inputs: names.map(channel_name => ({ kind: "source", source_id: context.source, channel_name })),
    } });
    expect(response.ok()).toBe(true);
    calculated.push(await response.json());
  }
  await page.evaluate(() => wwFetchCalculatedChannels());
  for (const c of calculated) await row(page, c.id, c.name).click();
  const times = [0.025, 0.035];
  await cursors(page, context.source, { times });
  const [voltage, current, power] = calculated;
  const powerMw = (275 / Math.sqrt(3)) * (4.2 / Math.sqrt(2));
  for (const mode of ["per_unit", "engineering"]) {
    await switchMode(page, mode);
    await expectCursors(page, voltage.id, mode === "per_unit" ? 2 * Math.sqrt(2) : 2 * PEAK_KV, { name: voltage.name, times });
    await expectCursors(page, current.id, mode === "per_unit" ? -2 : -4.2, { name: current.name, times });
    await expectCursors(page, power.id, powerMw, { name: power.name, bValue: powerMw, times });
    expect((await channelState(page, power.id, power.name)).unit).toBe("MW");
    expect((await channelState(page, voltage.id, voltage.name)).unit).toBe(mode === "per_unit" ? "pu" : "kV");
  }
});

test("a base edit keeps another source's values and avoids requests for it", async ({ page }) => {
  const context = await setup(page);
  await uploadRecord(page, { station: "OTHER_PU", startClock: "10:00:00.000000", durationS: 0.2,
    channels: [{ name: "VA", unit: "kV", phase: "A", amplitude: 132 * Math.sqrt(2 / 3), frequencyHz: 50 }] });
  const other = await sourceIdFor(page, "OTHER_PU");
  const otherContext = { ...context, source: other, groupsUrl: `${context.base}/sources/${other}/measurement-groups` };
  for (const g of await (await page.request.get(otherContext.groupsUrl)).json()) await page.request.delete(`${otherContext.groupsUrl}/${g.id}`);
  await addGroup(page, otherContext, "voltage", ["VA"], { nominal_voltage_ll_kv: 132 });
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${other}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await row(page, other).click();
  await cursors(page, context.source);
  await switchMode(page, "per_unit");
  await expectCursors(page, other, Math.sqrt(2));
  const requests = [];
  page.on("request", request => { if (request.url().includes(`/sources/${other}/`) && /waveform|cursor-values/.test(request.url())) requests.push(request.url()); });
  expect((await page.request.put(`${context.groupsUrl}/${context.voltage.id}/voltage-config`, { data: { nominal_voltage_ll_kv: 132 } })).ok()).toBe(true);
  await page.evaluate(source => wwRefreshDisplayedChannelsForPerUnitChange(source), context.source);
  await expectCursors(page, context.source, Math.sqrt(2) * 275 / 132);
  await expectCursors(page, other, Math.sqrt(2));
  expect(requests).toEqual([]);
});

test("a changed cursor position rejects the earlier measurement response", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const held = await holdResponse(page, "**/cursor-values");
  await page.evaluate(source => { window.oldCursorJob = wwFetchCursorValuesForSource(source); }, source);
  await held.reached;
  await page.evaluate(source => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(source));
    state.a.time = 0.015;
    wwClearCursorValuesForChannels(source, ["VA"]);
    wwUpdateCursorValueCellsForChannels(source, ["VA"]);
    wwUpdateAllCursorOverlays();
  }, source);
  held.release();
  await page.evaluate(() => window.oldCursorJob);
  // The response for A=0.005 must not be published under A=0.015.
  expect(await page.evaluate(source => ww.cursorValues.has(wwChannelKey(source, "VA")), source)).toBe(false);
  await page.evaluate(source => wwFetchCursorValuesForSource(source), source);
  await expect(row(page, source).locator(".cur-value--a")).toHaveText((-PEAK_KV).toFixed(1));
});

test("disabled cursors cause no measurement requests during unit switches", async ({ page }) => {
  const { source } = await setup(page);
  const requests = [];
  page.on("request", request => { if (request.url().endsWith("/cursor-values")) requests.push(request.url()); });
  await switchMode(page, "per_unit");
  await switchMode(page, "engineering");
  expect(requests).toEqual([]);
  await expect(row(page, source).locator(".cur-value--a")).toHaveText("\u2014");
});

test("unit round trips preserve all physical samples, cursor positions, t0 and viewport", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const snapshot = () => page.evaluate(source => {
    const { channel } = ww.displayed.get(wwChannelKey(source, "VA"));
    return { values: channel.values, time: channel.time, viewport: ww.viewport,
      t0: Array.from(ww.timeGroupT0State.entries()), cursors: Array.from(ww.timeGroupCursorState.entries()).map(([id, c]) => [id, c.a.time, c.b.time]) };
  }, source);
  const engineering = await snapshot();
  await switchMode(page, "per_unit");
  const normalized = await snapshot();
  expect(normalized.time).toEqual(engineering.time);
  expect(normalized.values).toHaveLength(engineering.values.length);
  expect(Math.max(...normalized.values.map((v, i) => Math.abs(v - engineering.values[i] / (275 / Math.sqrt(3)))))).toBeLessThan(1e-10);
  await expect(page.locator("#wwYAxisReadout")).toHaveText("Y: Voltage (pu)");
  await switchMode(page, "engineering");
  expect(await snapshot()).toEqual(engineering);
  await expect(page.locator("#wwYAxisReadout")).toHaveText("Y: Voltage");
  await expect(row(page, source).locator(".channel-name-text")).toHaveText("VA (kV)");
});

for (const action of ["source removal", "workspace reset"]) {
  test(`${action} discards a pending waveform display response`, async ({ page }) => {
    const { source } = await setup(page);
    const held = await holdResponse(page, `**/sources/${source}/waveform?**`);
    await page.locator("#wwUnitPerUnitBtn").click();
    await held.reached;
    if (action === "source removal") await page.evaluate(source => performRemoveSource(source), source);
    else await page.evaluate(() => wwClearWorkspace({ resetSourceBounds: true }));
    held.release();
    await page.evaluate(() => Promise.all(window.unitJobs));
    expect(await page.evaluate(() => ({ displayed: ww.displayed.size, panels: ww.panels.length })))
      .toEqual({ displayed: 0, panels: 0 });
  });
}

test("callout and peak readouts follow the same basis while their anchors stay fixed", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  await page.evaluate(async source => {
    const { panel, channel } = ww.displayed.get(wwChannelKey(source, "VA"));
    await wwCreateCalloutFromClick(panel, channel, 0.005);
    const callout = Array.from(ww.annotations.values()).find(a => a.type === "callout");
    wwEndAnnotationEdit(callout.id, true);
    await wwCreatePeakFromClick(panel, channel, "max");
  }, source);
  const annotations = () => page.evaluate(() => Array.from(ww.annotations.values()).map(a => ({
    id: a.id, type: a.type, sampleIndex: a.data.sampleIndex,
    time: wwAnchoredAnnotationTime(a), value: wwAnchoredAnnotationValue(a), unit: a.data.unit,
  })));
  const initial = await annotations();
  expect(initial.map(a => a.type).sort()).toEqual(["callout", "peak_max"]);
  for (const a of initial) { expect(a.value).toBeCloseTo(PEAK_KV, 9); expect(a.unit).toBe("kV"); }
  for (const mode of ["per_unit", "engineering"]) {
    await switchMode(page, mode);
    const current = await annotations();
    for (let i = 0; i < current.length; i++) {
      expect({ ...current[i], value: initial[i].value, unit: initial[i].unit }).toEqual(initial[i]);
      expect(current[i].value).toBeCloseTo(mode === "per_unit" ? Math.sqrt(2) : PEAK_KV, 9);
      expect(current[i].unit).toBe(mode === "per_unit" ? "pu" : "kV");
      if (current[i].type === "callout") {
        await page.evaluate(() => wwSetAnnotationDrawerOpen(true));
        const meta = page.locator(`.ww-annotation-list-item[data-annotation-id="${current[i].id}"] .ww-annotation-list-item-meta`);
        await expect(meta).toHaveText(new RegExp(`^VA .* ${(mode === "per_unit" ? Math.sqrt(2) : PEAK_KV).toFixed(3).replace(".", "\\.")} ${mode === "per_unit" ? "pu" : "kV"}$`));
      } else {
        const box = page.locator(`.ww-annotation[data-annotation-id="${current[i].id}"]`);
        await expect(box).toContainText(`+Peak: ${(mode === "per_unit" ? Math.sqrt(2) : PEAK_KV).toFixed(1)} ${mode === "per_unit" ? "pu" : "kV"}`);
      }
    }
  }
});

for (const kind of ["callout", "peak"]) {
  test(`an old ${kind} response cannot restore a previous display basis`, async ({ page }) => {
    const { source } = await setup(page);
    const id = await page.evaluate(async ({ source, kind }) => {
      const { panel, channel } = ww.displayed.get(wwChannelKey(source, "VA"));
      if (kind === "callout") {
        await wwCreateCalloutFromClick(panel, channel, 0.005);
        const annotation = Array.from(ww.annotations.values())[0];
        wwEndAnnotationEdit(annotation.id, true);
      } else await wwCreatePeakFromClick(panel, channel, "max");
      return Array.from(ww.annotations.keys())[0];
    }, { source, kind });
    const held = await holdResponse(page, kind === "callout" ? "**/annotation-anchor" : "**/peak-values");
    await page.evaluate(({ source, id, kind }) => {
      window.oldAnnotationJob = kind === "callout"
        ? wwResolveCalloutAnchorMove(id, source, "VA", 0.005, true)
        : wwRecalculatePeakAnnotationsForSource(source, 0, 0.2);
    }, { source, id, kind });
    await held.reached;
    await switchMode(page, "per_unit");
    held.release();
    await page.evaluate(() => window.oldAnnotationJob);
    const value = await page.evaluate(id => {
      const a = ww.annotations.get(id);
      return { value: wwAnchoredAnnotationValue(a), unit: a.data.unit, time: wwAnchoredAnnotationTime(a) };
    }, id);
    expect(value.value).toBeCloseTo(Math.sqrt(2), 9);
    expect(value.unit).toBe("pu");
    expect(value.time).toBe(0.005);
    if (kind === "callout") {
      await page.evaluate(() => wwSetAnnotationDrawerOpen(true));
      await expect(page.locator(`.ww-annotation-list-item[data-annotation-id="${id}"] .ww-annotation-list-item-meta`))
        .toHaveText(/^VA .* 1\.414 pu$/);
    } else await expect(page.locator(`.ww-annotation[data-annotation-id="${id}"]`)).toContainText("+Peak: 1.4 pu");
  });
}

test("zoom remains responsive during a mode refresh and its latest arrays reach the plot", async ({ page }) => {
  const { source } = await setup(page);
  await cursors(page, source);
  const modeResponse = await holdResponse(page, `**/sources/${source}/waveform?**`);
  await page.locator("#wwUnitPerUnitBtn").click();
  await modeResponse.reached;
  const zoomResponse = await holdResponse(page, `**/sources/${source}/waveform?**`);
  await page.locator("#wwZoomXInBtn").click();
  await zoomResponse.reached;
  modeResponse.release();
  zoomResponse.release();
  await page.evaluate(() => Promise.all(window.unitJobs));
  await expectCursors(page, source, Math.sqrt(2));
  await expect.poll(() => page.evaluate(source => {
    const { panel, channel } = ww.displayed.get(wwChannelKey(source, "VA"));
    const trace = panel.chartEl.data[panel.channels.indexOf(channel)];
    return { unit: channel.unit, label: panel.label, count: trace.y.length,
      matches: trace.y.length > 0 && Array.from(trace.y).every((value, i) => value === channel.values[i]) };
  }, source)).toMatchObject({ unit: "pu", label: "Voltage (pu)", matches: true });
});
