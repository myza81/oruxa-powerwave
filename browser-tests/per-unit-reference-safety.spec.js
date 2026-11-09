// LIM-001: real UI edits, arrays, shared warnings and stale-response protection.
const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor, addRecords, selectChannel, channelRow, waitForPlot } = require("./support/event_reconstruction_helpers");

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}
const row = (page, id, name) => page.locator(`tr.channel-row--toggle[data-source-id="${id}"][data-channel-name="${name}"]`);

async function setup(page, { marker = "P", side = "primary", sourceDefault = false } = {}) {
  await page.goto("/index.html");
  const station = "REFERENCE_SAFE";
  const data = syntheticComtrade({ station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.2,
    channels: ["IA", "IB"].map((name, i) => ({ name, phase: i ? "B" : "A", unit: "A", amplitude: .5, frequencyHz: 50 })) });
  const cfg = Buffer.from(data.cfg.toString("latin1").replaceAll(",1.0,1.0,P", `,2000,1,${marker}`), "latin1");
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "reference.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "reference.dat", mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`, groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const g of await json(await page.request.get(groupsUrl))) expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  let group;
  if (sourceDefault) {
    await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: {
      current_base_mode: "direct", direct_current_base_value: 2, current_base_reference_side: side,
    } }));
  } else {
    group = await json(await page.request.post(groupsUrl, { data: { kind: "current", display_name: "Current reference",
      status: "confirmed", channel_refs: ["IA", "IB"].map(channel_name => ({ kind: "source", source_id: sid, channel_name })) } }), 201);
    await json(await page.request.put(`${groupsUrl}/${group.id}/current-config`, { data: {
      method: "manual", manual_ibase_ka: 2, base_reference_side: side,
    } }));
  }
  const sum = await json(await page.request.post(`${base}/calculated-channels`, { data: {
    name: "Reference sum", operation: "addition", inputs: ["IA", "IB"].map(channel_name => ({ kind: "source", source_id: sid, channel_name })),
  } }), 201);
  const child = await json(await page.request.post(`${base}/calculated-channels`, { data: {
    name: "Reference magnitude", operation: "absolute_value", inputs: [{ kind: "calculated", calculated_channel_id: sum.id }],
  } }), 201);
  expect(sum.operation).toBe("addition"); expect(child.operation).toBe("absolute_value");
  expect(sum.inputs.map(input => input.channel_name)).toEqual(["IA", "IB"]);
  expect(child.inputs[0].calculated_channel_id).toBe(sum.id);
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwFetchCalculatedChannels());
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await row(page, sid, "IA").click();
  await row(page, child.id, child.name).click();
  await page.locator("#layoutModeSeparateBtn").click();
  const physical = await json(await page.request.get(`${base}/sources/${sid}/waveform?channel_name=IA`));
  expect(Math.max(...physical.values)).toBeCloseTo(.5, 12);
  await page.locator("#wwUnitPerUnitBtn").click();
  return { base, sid, station, groupsUrl, group, sum, child, physical };
}

function displayed(page, id, name) {
  return page.evaluate(({ id, name }) => {
    const entry = ww.displayed.get(wwChannelKey(id, name));
    if (!entry || !entry.channel.values.length) return null;
    const { channel, panel } = entry, trace = panel.chartEl.data?.[panel.channels.indexOf(channel)];
    return trace && { status: channel.perUnitStatus, compatibility: channel.perUnitReferenceCompatibility,
      unit: channel.unit, values: channel.values, plotted: Array.from(trace.y), identity: trace.meta, hover: trace.hovertemplate };
  }, { id, name });
}

async function verify(page, c, eligible, compatibility, denominator = 2000) {
  // DEC-212: raw source Current channels in Waveform (engineeringType "Current") are always
  // fetched in engineering mode. Calculated channels (engineeringType "Calculated") still
  // follow the Voltage Display toggle and use the original eligible/compatibility logic.

  // Raw IA — always engineering after DEC-212.
  await expect.poll(() => displayed(page, c.sid, "IA"), { timeout: 10000 }).toMatchObject({ status: null, unit: "A" });
  const dIA = await displayed(page, c.sid, "IA");
  expect(dIA.values).toHaveLength(c.physical.values.length); expect(dIA.plotted).toEqual(dIA.values);
  dIA.values.forEach((v, i) => expect(v).toBeCloseTo(c.physical.values[i], 12));
  expect(dIA.identity).toBe(`${c.sid}::IA`);
  await expect(row(page, c.sid, "IA").locator(".ww-pu-reference-status")).toHaveCount(0);

  // Calculated child — DEC-212 does not apply; original PU-mode behaviour.
  await expect.poll(() => displayed(page, c.child.id, c.child.name), { timeout: 10000 }).toMatchObject({
    status: eligible ? "configured" : "base_required", unit: eligible ? "pu" : "A", compatibility });
  const dChild = await displayed(page, c.child.id, c.child.name);
  expect(dChild.values).toHaveLength(c.physical.values.length); expect(dChild.plotted).toEqual(dChild.values);
  dChild.values.forEach((v, i) => expect(v).toBeCloseTo(Math.abs(c.physical.values[i]) * 2 / (eligible ? denominator : 1), 12));
  expect(dChild.identity).toBe(`${c.child.id}::${c.child.name}`);
  const badge = row(page, c.child.id, c.child.name).locator(".ww-pu-reference-status");
  if (compatibility === "unverified" && eligible) {
    await expect(badge).toHaveText("Unverified reference"); await expect(badge).toHaveAttribute("aria-label", /has not been verified/);
    expect(dChild.hover).toContain("Unverified reference");
  } else if (compatibility === "incompatible") {
    await expect(badge).toHaveText("PU unavailable"); await expect(badge).toHaveAttribute("title", /reference sides are incompatible/);
    expect(dChild.hover).toContain("PU unavailable");
  } else await expect(badge).toHaveCount(0);
}

async function editGroup(page, c, side, value = "2", status = 200) {
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${c.group.id}"]`).click();
  await page.locator("#wwMgBaseReferenceSide").selectOption(side);
  await page.locator("#wwMgManualIbaseInput").fill(value);
  const reply = page.waitForResponse(r => r.url().endsWith("/current-config") && r.request().method() === "PUT");
  await page.locator("#wwMgDrawerSaveBtn").click();
  expect((await reply).status()).toBe(status);
  if (status === 200) {
    await expect(page.locator("#wwMgDrawer")).not.toHaveClass(/ww-cc-drawer--open/);
    await page.locator("#measurementGroupsCloseBtn").click();
  }
}

for (const sourceDefault of [false, true]) {
  test(`known Secondary/Primary ${sourceDefault ? "Source Default" : "group"} retains ENG without CT scaling`, async ({ page }, info) => {
    const c = await setup(page, { marker: "S", sourceDefault });
    await verify(page, c, false, "incompatible");
    await row(page, c.sid, "IA").click({ button: "right" }); await page.locator("#wwChannelMenuPerUnitBtn").click();
    await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Known incompatible");
    await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Secondary");
    await expect(page.locator("#wwChannelPerUnitBody")).toContainText("Primary");
    await expect(page.locator("#wwChannelPerUnitBody")).toContainText("incompatible");
    await page.screenshot({ path: info.outputPath("known-mismatch.png") });
    expect(await json(await page.request.get(`${c.base}/sources/${c.sid}/waveform?channel_name=IA`))).toEqual(c.physical);
  });
}

test("known Secondary/Secondary stays eligible under one established authority", async ({ page }) => {
  const c = await setup(page, { marker: "S", side: "secondary" });
  await verify(page, c, true, "compatible");
});

test("historical Unknown is explicit beside arrays, cursors, legends and annotations across modes", async ({ page }, info) => {
  const c = await setup(page, { marker: "C" });
  await verify(page, c, true, "unverified");
  // DEC-212: raw IA stays in A (no badge); the calculated child is still in PU mode
  // ("Unverified reference"), so the legend has exactly one PU-reference-status badge.
  await expect(page.locator(".ww-legend-item .ww-pu-reference-status")).toHaveCount(1);
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async sid => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(sid));
    state.a.visible = state.b.visible = true; state.a.time = .005; state.b.time = .015;
    wwUpdateAllCursorOverlays(); await wwFetchCursorValuesForSource(sid);
    const { panel, channel } = ww.displayed.get(wwChannelKey(sid, "IA"));
    await wwCreateCalloutFromClick(panel, channel, .005);
    wwEndAnnotationEdit(Array.from(ww.annotations.values()).find(a => a.type === "callout").id, true);
    await wwCreatePeakFromClick(panel, channel, "max");
  }, c.sid);
  // DEC-212 forces engineering for the waveform TRACE, but the cursor fetch uses ww.unitMode
  // (per_unit here, no DEC-212 override), so cursor cells show PU values: 0.5 A / 2000 = 0.00025 pu.
  await expect.poll(async () => Number(await row(page, c.sid, "IA").locator(".cur-value--a").textContent())).toBeCloseTo(.00025, 5);
  await expect.poll(async () => Number(await row(page, c.sid, "IA").locator(".cur-value--b").textContent())).toBeCloseTo(-.00025, 5);
  // The cursor fetch uses ww.unitMode (per_unit, no DEC-212 override), so it updates
  // channel.perUnitStatus to "unverified". The callout and peak, created after the cursor
  // fetch, reflect that status and show the PU reference badge.
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveText("Unverified reference");
  await expect(page.locator(".ww-peak-value-line")).toContainText("pu · Unverified reference");
  const anchors = await page.evaluate(() => Array.from(ww.annotations.values()).map(a => [a.id, a.data.sampleIndex, wwAnchoredAnnotationTime(a)]));
  await page.screenshot({ path: info.outputPath("unverified-reference.png") });
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect(row(page, c.sid, "IA").locator(".ww-pu-reference-status")).toHaveCount(0);
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveCount(0);
  await page.locator("#wwUnitPerUnitBtn").click(); await verify(page, c, true, "unverified");
  // After PU re-toggle the cursor auto-re-fetches in PU mode, updating channel.perUnitStatus
  // back to "unverified" — the callout badge reappears (DEC-212 applies to the trace, not the cursor).
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveText("Unverified reference");
  expect(await page.evaluate(() => Array.from(ww.annotations.values()).map(a => [a.id, a.data.sampleIndex, wwAnchoredAnnotationTime(a)]))).toEqual(anchors);
});

test("accepted reference edits update all shared displays; rejected edit preserves state", async ({ page }) => {
  const c = await setup(page);
  await verify(page, c, true, "compatible");
  await editGroup(page, c, "secondary"); await verify(page, c, false, "incompatible");
  await editGroup(page, c, "unknown"); await verify(page, c, true, "unverified");
  const groups = await json(await page.request.get(c.groupsUrl));
  const wave = await json(await page.request.get(`${c.base}/calculated-channels/${c.child.id}/waveform?unit_mode=per_unit`));
  await editGroup(page, c, "secondary", "-2", 400);
  expect(await json(await page.request.get(c.groupsUrl))).toEqual(groups);
  expect(await json(await page.request.get(`${c.base}/calculated-channels/${c.child.id}/waveform?unit_mode=per_unit`))).toEqual(wave);
  await verify(page, c, true, "unverified");
});

test("an obsolete compatible waveform cannot restore PU after an incompatible accepted edit", async ({ page }) => {
  const c = await setup(page); await verify(page, c, true, "compatible");
  let release, entered;
  const blocked = new Promise(resolve => { release = resolve; });
  const reached = new Promise(resolve => { entered = resolve; });
  await page.route(`**/sources/${c.sid}/waveform?**`, async route => {
    const response = await route.fetch(); entered(); await blocked; await route.fulfill({ response });
  }, { times: 1 });
  await page.evaluate(() => { window.referenceRefresh = wwRefreshWaveformDisplayBasis(); });
  await reached;
  await editGroup(page, c, "secondary");
  release(); await page.evaluate(() => window.referenceRefresh);
  await verify(page, c, false, "incompatible");
});

test("ER uses its own mode and explicit Unknown-reference status without changing numerical arrays", async ({ page }) => {
  const c = await setup(page, { marker: "C" }); await verify(page, c, true, "unverified");
  await addRecords(page, [c.station]); await page.locator("#wwErUnitEngineeringBtn").click();
  await selectChannel(page, c.station, c.child.name); await waitForPlot(page, 1);
  const erRow = await channelRow(page, c.station, c.child.name);
  await expect(erRow.locator(".ww-pu-reference-status")).toHaveCount(0);
  await page.locator("#wwErUnitPerUnitBtn").click(); await waitForPlot(page, 1);
  await expect(erRow.locator(".ww-pu-reference-status")).toHaveText("Unverified reference");
  await expect(page.locator("#wwErPanelsWrap .ww-legend-item .ww-pu-reference-status")).toHaveText("Unverified reference");
  const proof = await json(await page.request.get(`${c.base}/calculated-channels/${c.child.id}/per-unit-resolution`));
  expect(proof).toMatchObject({ status: "configured", reference_compatibility: "unverified", measurement_side: "unknown", base_reference_side: "primary" });
  const wave = await json(await page.request.get(`${c.base}/calculated-channels/${c.child.id}/waveform?unit_mode=per_unit`));
  wave.values.forEach((v, i) => expect(v).toBeCloseTo(Math.abs(c.physical.values[i]) * 2 / 2000, 12));
});
