// Stage 5B: real result-owned configuration, numerical readouts and request races.
const { test, expect } = require("./support/test");
const { BACKEND, uploadRecord, workspaceId, sourceIdFor, addRecords, selectChannel,
  channelRow, waitForPlot, plotState } = require("./support/event_reconstruction_helpers");

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status); return response.json();
}
const row = (page, id) => page.locator(`tr.channel-row--toggle[data-source-id="${id}"]`);
const config = (c, id = c.sum.id) => `${c.base}/calculated-channels/${id}/per-unit-config`;

async function setup(page, equal = false) {
  await page.goto("/index.html");
  const station = "MANUAL_CURRENT";
  await uploadRecord(page, { station, startClock: "10:00:00.000000", durationS: 0.2,
    channels: ["IA", "IB"].map((name, i) => ({ name, phase: i ? "B" : "A", unit: "A", amplitude: 4199, frequencyHz: 50 })) });
  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`, groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const g of await json(await page.request.get(groupsUrl))) {
    expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  }
  for (const [name, amount] of [["IA", 2], ["IB", equal ? 2 : 4]]) {
    const g = await json(await page.request.post(groupsUrl, { data: { kind: "current", display_name: name,
      status: "confirmed", channel_refs: [{ kind: "source", source_id: sid, channel_name: name }] } }), 201);
    await json(await page.request.put(`${groupsUrl}/${g.id}/current-config`, { data: {
      method: "manual", manual_ibase_ka: amount, base_reference_side: "primary" } }));
  }
  await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: { current_base_mode: "direct", direct_current_base_value: 1 } }));
  const sum = await json(await page.request.post(`${base}/calculated-channels`, { data: {
    name: "Physical Current sum", operation: "addition", inputs: ["IA", "IB"].map(channel_name => ({ kind: "source", source_id: sid, channel_name })) } }), 201);
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwFetchCalculatedChannels());
  await row(page, sum.id).click();
  await page.locator("#wwUnitPerUnitBtn").click();
  await page.locator("#layoutModeSeparateBtn").click();
  const physical = await json(await page.request.get(`${base}/calculated-channels/${sum.id}/waveform`));
  return { station, ws, sid, base, groupsUrl, sum, physical };
}

async function open(page, c, id = c.sum.id) {
  await row(page, id).click({ button: "right" });
  await page.locator("#wwChannelMenuPerUnitBtn").click();
  await expect(page.locator("#wwCalculatedPuMode")).toBeVisible();
}

async function save(page, c, { mode = "manual", value = "4", unit = "kA", side = "primary", status = 200, id = c.sum.id } = {}) {
  await page.locator("#wwCalculatedPuMode").selectOption(mode);
  if (mode === "manual") {
    await page.locator("#wwCalculatedPuBase").fill(value);
    await page.locator("#wwCalculatedPuUnit").selectOption(unit);
    await page.locator("#wwCalculatedPuSide").selectOption(side);
  }
  const response = page.waitForResponse(r => r.url() === config(c, id) && r.request().method() === "PUT");
  await page.locator("#wwCalculatedPuSaveBtn").click();
  expect((await response).status()).toBe(status);
  if (status === 200) await expect(page.locator("#wwCalculatedPuSaveBtn")).toBeEnabled();
  else await expect(page.locator("#wwCalculatedPuError")).toBeVisible();
}

async function displayed(page, id) {
  return page.evaluate(id => {
    const e = Array.from(ww.displayed.values()).find(e => e.channel.sourceId === id);
    if (!e) return null;
    const i = e.panel.channels.indexOf(e.channel), trace = e.panel.chartEl.data?.[i];
    const legend = e.panel.legendEl.querySelectorAll(".ww-legend-label")[i];
    if (!trace || !legend) return null; // Layout replacement is still pending.
    return { unit: e.channel.unit, status: e.channel.perUnitStatus, values: e.channel.values,
      plotted: Array.from(trace.y), legend: legend.textContent,
      name: e.channel.channelName, traceName: trace.name, identity: trace.meta };
  }, id);
}

async function scaled(page, c, denominator, id = c.sum.id) {
  await expect.poll(async () => {
    const d = await displayed(page, id);
    return d && { unit: d.unit, status: d.status };
  }).toEqual({ unit: denominator ? "pu" : "A", status: denominator ? "configured" : "base_required" });
  const d = await displayed(page, id);
  expect(Math.max(...d.values)).toBeCloseTo(8398 / (denominator || 1), 10);
  d.values.forEach((v, i) => expect(v).toBeCloseTo(c.physical.values[i] / (denominator || 1), 10));
  expect(d.plotted).toEqual(d.values);
  expect(d.identity).toBe(`${id}::${d.name}`);
  expect(d.traceName).toBe(d.name);
  expect(d.legend).toBe(`${d.name} (${denominator ? "pu" : "A"})`);
  await expect(row(page, id).locator(".channel-name-text")).toHaveText(`${d.name} (${denominator ? "pu" : "A"})`);
  // A display-unit change never rewrites the physical definition or toggle metadata.
  expect(await page.evaluate(id => ww.calculatedChannels.get(id).unit, id)).toBe("A");
  await expect(row(page, id)).toHaveAttribute("data-unit", "A");
}

async function cursorsAndAnnotations(page, c) {
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async ({ id }) => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(id));
    state.a.visible = state.b.visible = true; state.a.time = 0.005; state.b.time = 0.015;
    wwUpdateAllCursorOverlays(); await wwFetchCursorValuesForSource(id);
    const { panel, channel } = Array.from(ww.displayed.values()).find(e => e.channel.sourceId === id);
    await wwCreateCalloutFromClick(panel, channel, 0.005);
    const callout = Array.from(ww.annotations.values()).find(a => a.type === "callout");
    wwEndAnnotationEdit(callout.id, true); await wwCreatePeakFromClick(panel, channel, "max");
  }, { id: c.sum.id });
}

async function readouts(page, c, amount, unit = "pu") {
  await expect.poll(async () => Number(await row(page, c.sum.id).locator(".cur-value--a").textContent())).toBeCloseTo(amount, 1);
  await expect.poll(async () => Number(await row(page, c.sum.id).locator(".cur-value--b").textContent())).toBeCloseTo(-amount, 1);
  const data = await page.evaluate(id => ({
    times: (() => { const s = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(id)); return [s.a.time, s.b.time]; })(),
    annotations: Array.from(ww.annotations.values()).map(a => ({ id: a.id, type: a.type, time: wwAnchoredAnnotationTime(a),
      value: wwAnchoredAnnotationValue(a), unit: a.data.unit, index: a.data.sampleIndex })),
  }), c.sum.id);
  expect(data.times).toEqual([0.005, 0.015]);
  expect(data.annotations.map(a => a.type).sort()).toEqual(["callout", "peak_max"]);
  data.annotations.forEach(a => { expect(a.value).toBeCloseTo(amount, 10); expect(a.unit).toBe(unit); });
  return data.annotations;
}

for (const peakKind of ["max", "min"]) {
  test(`${peakKind} Peak cannot cover Per-unit dialog controls or intercept saves`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    const c = await setup(page);
    await open(page, c); await save(page, c); await scaled(page, c, 4000);
    await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
    await cursorsAndAnnotations(page, c);
    if (peakKind === "min") await page.evaluate(async id => {
      const { panel, channel } = Array.from(ww.displayed.values()).find(e => e.channel.sourceId === id);
      await wwCreatePeakFromClick(panel, channel, "min");
    }, c.sum.id);
    const peak = page.locator(`.ww-annotation--peak_${peakKind}`);
    const anchors = () => page.evaluate(() => Array.from(ww.annotations.values()).map(a => ({
      id: a.id, type: a.type, time: wwAnchoredAnnotationTime(a), value: wwAnchoredAnnotationValue(a),
      unit: a.data.unit, index: a.data.sampleIndex,
    })));
    const initialAnchors = await anchors();
    const groups = await json(await page.request.get(c.groupsUrl));
    const initialConfig = await json(await page.request.get(config(c)));
    const initialWaveform = await json(await page.request.get(`${c.base}/calculated-channels/${c.sum.id}/waveform?unit_mode=per_unit`));
    async function movePeakOver(box) {
      const before = await peak.boundingBox();
      await page.mouse.move(before.x + 65, before.y + 10);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 - before.width / 2 + 65,
        box.y + box.height / 2 - before.height / 2 + 10, { steps: 12 });
      await page.mouse.up();
      const after = await peak.boundingBox();
      // Prove the annotation actually covers the intended coordinates.
      expect(after.x).toBeLessThan(box.x + box.width / 2);
      expect(after.x + after.width).toBeGreaterThan(box.x + box.width / 2);
      expect(after.y).toBeLessThan(box.y + box.height / 2);
      expect(after.y + after.height).toBeGreaterThan(box.y + box.height / 2);
    }
    async function expectReachable(selector) {
      expect(await page.locator(selector).evaluate(el => {
        const box = el.getBoundingClientRect();
        const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return top === el || el.contains(top);
      })).toBe(true);
    }
    // Test hit targets, not just z-index values or DOM visibility. The Peak
    // stays at the overlapping position while the real dialog is open.
    for (const target of ["#wwCalculatedPuSaveBtn", "#wwChannelPerUnitBody", "#wwCalculatedPuBase",
      "#wwCalculatedPuUnit", "#wwCalculatedPuSide", "#wwCalculatedPuAutomaticBtn",
      "#wwChannelPerUnitCloseFooterBtn"]) {
      await open(page, c);
      const box = await page.locator(target).boundingBox();
      await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
      await movePeakOver(box);
      await open(page, c);
      await expectReachable(target);
      await expectReachable("#wwChannelPerUnitCloseBtn");
      await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
    }
    expect(await anchors()).toEqual(initialAnchors);
    expect(await json(await page.request.get(config(c)))).toEqual(initialConfig);
    expect(await json(await page.request.get(`${c.base}/calculated-channels/${c.sum.id}/waveform?unit_mode=per_unit`))).toEqual(initialWaveform);
    await open(page, c);
    const saveBox = await page.locator("#wwCalculatedPuSaveBtn").boundingBox();
    await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
    await movePeakOver(saveBox); await open(page, c);
    await page.screenshot({ path: test.info().outputPath(`peak-${peakKind}-behind-pu-dialog.png`) });
    await save(page, c, { value: "2" }); await scaled(page, c, 2000);
    await expect.poll(anchors).toEqual(initialAnchors.map(a => ({ ...a, value: a.value * 2 })));
    const accepted = await json(await page.request.get(config(c)));
    await save(page, c, { value: "0", status: 400 }); await scaled(page, c, 2000);
    expect(await json(await page.request.get(config(c)))).toEqual(accepted);
    await expectReachable("#wwCalculatedPuSaveBtn");
    await page.keyboard.press("Escape");
    await expect(page.locator("#wwChannelPerUnitOverlay")).toBeHidden();
    await open(page, c); await page.locator("#wwChannelPerUnitCloseBtn").click();
    await expect(page.locator("#wwChannelPerUnitOverlay")).toBeHidden();
    await open(page, c); await page.locator("#wwChannelPerUnitOverlay").click({ position: { x: 5, y: 5 } });
    await expect(page.locator("#wwChannelPerUnitOverlay")).toBeHidden();
    // Ordinary annotation dragging remains available after the modal closes.
    const before = await peak.boundingBox();
    await page.mouse.move(before.x + 65, before.y + 10); await page.mouse.down();
    await page.mouse.move(before.x + 105, before.y + 35, { steps: 8 }); await page.mouse.up();
    const after = await peak.boundingBox();
    expect(after.x).toBeCloseTo(before.x + 40, 0); expect(after.y).toBeCloseTo(before.y + 25, 0);
    expect(await anchors()).toEqual(initialAnchors.map(a => ({ ...a, value: a.value * 2 })));
    expect(await json(await page.request.get(c.groupsUrl))).toEqual(groups);
    expect(await json(await page.request.get(`${c.base}/calculated-channels/${c.sum.id}/waveform`))).toEqual(c.physical);
  });
}

test("manual lifecycle updates arrays, legends, cursors and annotations without changing input authorities", async ({ page }) => {
  const c = await setup(page);
  const groups = await json(await page.request.get(c.groupsUrl));
  const defaults = await json(await page.request.get(`${c.base}/per-unit/sources/${c.sid}`));
  await scaled(page, c, null); await cursorsAndAnnotations(page, c);
  const initial = await readouts(page, c, 8398, "A");
  await open(page, c); await save(page, c); await scaled(page, c, 4000);
  await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Manual calculated Current base");
  await expect(page.locator("#wwChannelPerUnitBody")).toContainText("4.00 kA");
  await page.screenshot({ path: test.info().outputPath("manual-current-editor.png") });
  for (const [mode, value, denominator] of [["manual", "2", 2000], ["unassigned", "", null]]) {
    await save(page, c, { mode, value }); await scaled(page, c, denominator);
  }
  const response = page.waitForResponse(r => r.url() === config(c) && r.request().method() === "PUT");
  await page.locator("#wwCalculatedPuAutomaticBtn").click(); expect((await response).status()).toBe(200);
  await expect(page.locator("#wwCalculatedPuMode")).toHaveValue("automatic");
  await scaled(page, c, null);
  const last = await readouts(page, c, 8398, "A");
  last.forEach((a, i) => expect({ ...a, value: initial[i].value, unit: initial[i].unit }).toEqual(initial[i]));
  expect(await json(await page.request.get(c.groupsUrl))).toEqual(groups);
  expect(await json(await page.request.get(`${c.base}/per-unit/sources/${c.sid}`))).toEqual(defaults);
  expect(await json(await page.request.get(`${c.base}/calculated-channels/${c.sum.id}/waveform`))).toEqual(c.physical);
});

for (const invalid of [{ value: "0", side: "primary" }, { value: "4", side: "secondary" }, { value: "4", side: "unknown" }]) {
  test(`rejected manual configuration preserves accepted state and every PU sample ${JSON.stringify(invalid)}`, async ({ page }) => {
    const c = await setup(page); await open(page, c); await save(page, c); await scaled(page, c, 4000);
    const before = await json(await page.request.get(config(c))), groups = await json(await page.request.get(c.groupsUrl));
    await save(page, c, { ...invalid, status: 400 }); await scaled(page, c, 4000);
    expect(await json(await page.request.get(config(c)))).toEqual(before);
    expect(await json(await page.request.get(c.groupsUrl))).toEqual(groups);
  });
}

test("manual and unassigned modes persist across page reload, with a manager entry and explicit Automatic reset", async ({ page }) => {
  const c = await setup(page, true); await scaled(page, c, 2000);
  await page.locator("#mainNavCalculatedChannelsBtn").click();
  const manager = page.locator(`#wwCcListBody [data-calculated-channel-id="${c.sum.id}"]`);
  await manager.locator(".ww-cc-menu summary").click(); await manager.locator('[data-action="per-unit-config"]').click();
  await expect(page.locator("#wwCalculatedPuMode")).toBeVisible(); await save(page, c);
  const accepted = await json(await page.request.get(config(c)));
  for (const mode of ["manual", "unassigned"]) {
    if (mode === "unassigned") await save(page, c, { mode });
    await page.reload(); await page.locator("#mainNavWaveformBtn").click();
    await page.evaluate(() => wwFetchCalculatedChannels()); await row(page, c.sum.id).click();
    await open(page, c); await expect(page.locator("#wwCalculatedPuMode")).toHaveValue(mode);
    const stored = await json(await page.request.get(config(c)));
    expect(stored.calculated_channel_id).toBe(c.sum.id);
    if (mode === "manual") { expect(stored).toEqual(accepted); await expect(page.locator("#wwCalculatedPuBase")).toHaveValue("4"); await expect(page.locator("#wwCalculatedPuSide")).toHaveValue("primary"); }
    else { expect(stored.current_base_amps).toBeNull(); await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Unassigned"); }
  }
  await page.locator("#wwCalculatedPuAutomaticBtn").click();
  await expect(page.locator("#wwCalculatedPuMode")).toHaveValue("automatic");
  expect((await json(await page.request.get(config(c)))).mode).toBe("automatic");
});

async function hold(page, pattern) {
  let release, entered;
  const pending = new Promise(r => { release = r; }), reached = new Promise(r => { entered = r; });
  await page.route(pattern, async route => { const response = await route.fetch(); entered(); await pending; await route.fulfill({ response }); }, { times: 1 });
  return { release, reached };
}

for (const finalMode of ["manual", "unassigned", "automatic"]) {
test(`obsolete waveform, cursor, callout and peak responses cannot restore a previous base after ${finalMode}`, async ({ page }) => {
  const c = await setup(page); await open(page, c); await save(page, c); await scaled(page, c, 4000);
  await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
  const other = await json(await page.request.post(`${c.base}/calculated-channels`, { data: {
    name: "Unaffected Current", operation: "absolute_value", inputs: [{ kind: "source", source_id: c.sid, channel_name: "IA" }] } }), 201);
  await page.evaluate(() => wwFetchCalculatedChannels()); await row(page, other.id).click();
  await expect.poll(async () => (await displayed(page, other.id))?.unit).toBe("pu");
  const otherBefore = await displayed(page, other.id);
  await cursorsAndAnnotations(page, c);
  const old = await readouts(page, c, 2.0995);
  const held = await Promise.all([hold(page, `**/calculated-channels/${c.sum.id}/waveform?**`),
    hold(page, "**/calculated-channels/cursor-values"), hold(page, `**/calculated-channels/${c.sum.id}/annotation-anchor`),
    hold(page, "**/calculated-channels/peak-values")]);
  await page.evaluate(id => { window.oldManualRefresh = wwRefreshDisplayedChannelsForPerUnitChange(id); }, c.sum.id);
  await Promise.all(held.map(h => h.reached));
  const unrelatedRequests = [];
  page.on("request", request => { if (request.url().includes(`/sources/${c.sid}/waveform`) || request.url().includes(`/calculated-channels/${other.id}/waveform`)) unrelatedRequests.push(request.url()); });
  const denominator = finalMode === "manual" ? 2000 : null, amount = finalMode === "manual" ? 4.199 : 8398, unit = finalMode === "manual" ? "pu" : "A";
  await open(page, c); await save(page, c, { mode: finalMode, value: "2" }); await scaled(page, c, denominator);
  await readouts(page, c, amount, unit); held.forEach(h => h.release()); await page.evaluate(() => window.oldManualRefresh);
  await scaled(page, c, denominator); const next = await readouts(page, c, amount, unit);
  next.forEach((a, i) => expect({ ...a, value: old[i].value, unit: old[i].unit }).toEqual(old[i]));
  expect(unrelatedRequests).toEqual([]);
  expect(await displayed(page, other.id)).toEqual(otherBefore);
});
}

test("a manual child owns its base independently of its parent, including Event Reconstruction", async ({ page }) => {
  const c = await setup(page); await open(page, c); await save(page, c);
  await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
  const child = await json(await page.request.post(`${c.base}/calculated-channels`, { data: {
    name: "Child current", operation: "absolute_value", inputs: [{ kind: "calculated", calculated_channel_id: c.sum.id }] } }), 201);
  await page.evaluate(() => wwFetchCalculatedChannels()); await row(page, child.id).click();
  const physical = await json(await page.request.get(`${c.base}/calculated-channels/${child.id}/waveform`));
  const childContext = { ...c, physical };
  await scaled(page, childContext, null, child.id);
  await open(page, c, child.id); await save(page, c, { id: child.id, value: "2" }); await scaled(page, childContext, 2000, child.id);
  await page.locator("#wwChannelPerUnitCloseFooterBtn").click();
  await addRecords(page, [c.station]); await page.locator("#wwErUnitPerUnitBtn").click();
  await selectChannel(page, c.station, child.name); await waitForPlot(page, 1);
  const pu = (await plotState(page)).panels[0]; expect(pu.unit).toBe("pu");
  await expect((await channelRow(page, c.station, child.name)).locator(".channel-name-text")).toHaveText(`${child.name} (pu)`);
  pu.values.forEach((v, i) => expect(v).toBeCloseTo(physical.values[i] / 2000, 10));
  await page.locator("#mainNavWaveformBtn").click(); await open(page, c, child.id); await save(page, c, { mode: "automatic", id: child.id });
  await page.locator("#wwChannelPerUnitCloseFooterBtn").click(); await page.locator("#mainNavEventReconstructionBtn").click();
  const selected = await channelRow(page, c.station, child.name); await expect(selected).toHaveAttribute("aria-pressed", "true");
  await expect(selected.locator(".ww-er-pu-unavailable")).toHaveText("PU unavailable"); await waitForPlot(page, 0);
  await expect(selected.locator(".channel-name-text")).toHaveText(`${child.name} (A)`);
  await page.locator("#wwErUnitEngineeringBtn").click(); await waitForPlot(page, 1);
  expect((await plotState(page)).panels[0].values).toEqual(physical.values);
});

test("a representable subnormal ampere base stays positive in provenance and the editor", async ({ page }) => {
  const c = await setup(page);
  const zero = await json(await page.request.post(`${c.base}/calculated-channels`, { data: {
    name: "Zero current", operation: "subtraction", inputs: ["IA", "IB"].map(channel_name => ({
      kind: "source", source_id: c.sid, channel_name })) } }), 201);
  await page.evaluate(() => wwFetchCalculatedChannels()); await row(page, zero.id).click();
  await open(page, c, zero.id);
  for (const amount of ["5e-324", "1.2347e-320"]) {
    await save(page, c, { value: amount, unit: "A", id: zero.id });
    const p = await json(await page.request.get(`${c.base}/calculated-channels/${zero.id}/per-unit-resolution`));
    expect(p).toMatchObject({ status: "configured", effective_base_amount: Number(amount), effective_base_unit: "A", configured_current_base_amps: Number(amount) });
    await expect(page.locator("#wwChannelPerUnitBody")).toContainText(`${amount} A`);
    await expect.poll(async () => (await displayed(page, zero.id))?.unit).toBe("pu");
    expect((await displayed(page, zero.id)).values).toEqual(c.physical.values.map(() => 0));
    await page.locator("#wwChannelPerUnitCloseFooterBtn").click(); await open(page, c, zero.id);
    await expect(page.locator("#wwCalculatedPuBase")).toHaveValue(amount);
    await expect(page.locator("#wwCalculatedPuUnit")).toHaveValue("A");
    const response = page.waitForResponse(r => r.url() === config(c, zero.id) && r.request().method() === "PUT");
    await page.locator("#wwCalculatedPuSaveBtn").click();
    expect((await json(await response)).current_base_amps).toBe(Number(amount));
    await expect(page.locator("#wwCalculatedPuSaveBtn")).toBeEnabled();
  }
});
