// LIM-001: real UI edits, arrays, shared warnings and stale-response protection.
// Slice 6C.1 (DEC-212): editGroup() removed — Current PU configuration no longer in
// normal MG UI. Affected tests use direct API calls to exercise backend behaviour.
// New tests cover: MG drawer standard vs legacy, annotation engineering-type storage,
// hidden-channel annotation, legacy-annotation fallback, calculated-Current peak scope.
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
  // fetched in engineering mode. Calculated channels still follow the Voltage Display toggle.

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
  // DEC-212 §2: cursor fetch for raw Current channels uses engineering (not ww.unitMode).
  // 0.5 A peak amplitude → cursor A ≈ 0.5 A; cursor B at t=0.015 (270° of 50 Hz) ≈ −0.5 A.
  await expect.poll(async () => Number(await row(page, c.sid, "IA").locator(".cur-value--a").textContent())).toBeCloseTo(.5, 2);
  await expect.poll(async () => Number(await row(page, c.sid, "IA").locator(".cur-value--b").textContent())).toBeCloseTo(-.5, 2);
  // DEC-212 §2: callout and peak anchor requests also use engineering for raw Current.
  // No PU reference-status badge on callout or peak.
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveCount(0);
  await expect(page.locator(".ww-peak-value-line")).not.toContainText("pu");
  const anchors = await page.evaluate(() => Array.from(ww.annotations.values()).map(a => [a.id, a.data.sampleIndex, wwAnchoredAnnotationTime(a)]));
  await page.screenshot({ path: info.outputPath("unverified-reference.png") });
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect(row(page, c.sid, "IA").locator(".ww-pu-reference-status")).toHaveCount(0);
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveCount(0);
  await page.locator("#wwUnitPerUnitBtn").click(); await verify(page, c, true, "unverified");
  // After PU re-toggle, cursor and callout refresh for raw Current still use engineering.
  await expect(page.locator(".ww-annotation--callout .ww-pu-reference-status")).toHaveCount(0);
  expect(await page.evaluate(() => Array.from(ww.annotations.values()).map(a => [a.id, a.data.sampleIndex, wwAnchoredAnnotationTime(a)]))).toEqual(anchors);
});

// Slice 6C.1: editGroup() removed — Current Base config no longer in the standard MG UI.
// Tests below use direct API calls to the /current-config endpoint, which remains intact.
// The underlying backend rejection and state-preservation assertions are unchanged.

test("accepted reference edits update all shared displays; rejected edit preserves state", async ({ page }) => {
  const c = await setup(page);
  await verify(page, c, true, "compatible");

  // Change to secondary (incompatible with primary Ibase).
  expect((await page.request.put(`${c.groupsUrl}/${c.group.id}/current-config`, {
    data: { method: "manual", manual_ibase_ka: 2, base_reference_side: "secondary" },
  })).status()).toBe(200);
  await page.evaluate(async () => { await wwRefreshWaveformDisplayBasis(); });
  await verify(page, c, false, "incompatible");

  // Change to unknown (unverified compatibility).
  expect((await page.request.put(`${c.groupsUrl}/${c.group.id}/current-config`, {
    data: { method: "manual", manual_ibase_ka: 2, base_reference_side: "unknown" },
  })).status()).toBe(200);
  await page.evaluate(async () => { await wwRefreshWaveformDisplayBasis(); });
  await verify(page, c, true, "unverified");

  const groups = await json(await page.request.get(c.groupsUrl));
  const wave = await json(await page.request.get(`${c.base}/calculated-channels/${c.child.id}/waveform?unit_mode=per_unit`));

  // Backend rejects negative Ibase (invalid value).
  expect((await page.request.put(`${c.groupsUrl}/${c.group.id}/current-config`, {
    data: { method: "manual", manual_ibase_ka: -2, base_reference_side: "secondary" },
  })).status()).toBe(400);

  // State preserved after rejection.
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
  // Change config via API and trigger a fresh refresh (not intercepted — times:1 already used).
  expect((await page.request.put(`${c.groupsUrl}/${c.group.id}/current-config`, {
    data: { method: "manual", manual_ibase_ka: 2, base_reference_side: "secondary" },
  })).status()).toBe(200);
  await page.evaluate(async () => { await wwRefreshWaveformDisplayBasis(); });
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

// ---------------------------------------------------------------------------
// Slice 6C.1 — DEC-212 MG drawer: standard vs legacy Current groups
// ---------------------------------------------------------------------------

test("Current MG drawer shows no PU controls for standard Current group (DEC-212)", async ({ page }) => {
  await page.goto("/index.html");
  const station = "MG_UI_STANDARD";
  const data = syntheticComtrade({ station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.1,
    channels: [{ name: "IA", phase: "A", unit: "A", amplitude: .5, frequencyHz: 50 }] });
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "mgtest.cfg", mimeType: "application/octet-stream", buffer: data.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "mgtest.dat", mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();

  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`, groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  // Delete any auto-created groups.
  for (const g of await json(await page.request.get(groupsUrl))) await page.request.delete(`${groupsUrl}/${g.id}`);
  // Create a Current group without calling /current-config → method stays "none" → hasLegacyConfig = false.
  const group = await json(await page.request.post(groupsUrl, { data: { kind: "current",
    display_name: "Standard Current", status: "confirmed",
    channel_refs: [{ kind: "source", source_id: sid, channel_name: "IA" }] } }), 201);

  await page.locator("#mainNavWaveformBtn").click();
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${group.id}"]`).click();
  await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);

  // Standard DEC-212 Current group: no PU configuration controls.
  await expect(page.locator("#wwMgLegacyCurrentSection")).toHaveCount(0);
  await expect(page.locator("#wwMgManualIbaseInput")).toHaveCount(0);
  await expect(page.locator("#wwMgCurrentMethod")).toHaveCount(0);
  await expect(page.locator("#wwMgDrawerBody")).toContainText("Current channels always display in A/kA");
  await expect(page.locator("#wwMgDrawerBody")).toContainText("DEC-212");
});

test("Current MG drawer shows Legacy Current Reference for group with existing Ibase config (DEC-212)", async ({ page }) => {
  // setup() creates a group with method: "manual" (manual_ibase_ka: 2) → hasLegacyConfig = true.
  const c = await setup(page);

  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenMeasurementGroupsFromSettingsBtn").click();
  await page.locator(`[id="wwMgEditBtn-${c.group.id}"]`).click();
  await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);

  // Legacy group: shows the Legacy Current Reference section with its badge and controls.
  await expect(page.locator("#wwMgLegacyCurrentSection")).toBeVisible();
  await expect(page.locator("#wwMgLegacyBadge")).toHaveText("Historical");
  await expect(page.locator("#wwMgManualIbaseInput")).toBeVisible();
  await expect(page.locator("#wwMgBaseReferenceSide")).toBeVisible();
  // The DEC-212 "no PU controls" note is NOT present for legacy groups.
  await expect(page.locator("#wwMgDrawerBody")).not.toContainText("Per-unit normalisation for current is configured through Calculated Channels");
});

// ---------------------------------------------------------------------------
// Slice 6C.1 — DEC-212 annotation engineeringType storage
// ---------------------------------------------------------------------------

test("raw Current callout and peak use engineering even when source channel is hidden (DEC-212)", async ({ page }) => {
  const c = await setup(page, { marker: "C" });

  // Create a callout and peak on raw IA while it is displayed.
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async sid => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(sid));
    state.a.visible = true; state.a.time = .005;
    wwUpdateAllCursorOverlays();
    const { panel, channel } = ww.displayed.get(wwChannelKey(sid, "IA"));
    await wwCreateCalloutFromClick(panel, channel, .005);
    wwEndAnnotationEdit(Array.from(ww.annotations.values()).find(a => a.type === "callout").id, true);
    await wwCreatePeakFromClick(panel, channel, "max");
  }, c.sid);

  // Hide IA: ww.displayed no longer contains IA entry.
  await page.locator("#wwCursorModeBtn").click(); // exit cursor mode
  await row(page, c.sid, "IA").click();           // toggle IA off
  await expect.poll(() => page.evaluate(sid => !ww.displayed.has(wwChannelKey(sid, "IA")), c.sid), { timeout: 5000 }).toBe(true);

  // Toggle ENG → PU: triggers callout + peak refresh for ALL annotations including hidden-channel ones.
  // Old code: ww.displayed lookup fails → falls back to ww.unitMode (PU) → annotation.data.unit = "pu".
  // Slice 6C.1 fix: annotation.data.engineeringType = "Current" → engineering → annotation.data.unit = "A".
  await page.locator("#wwUnitEngineeringBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();

  // Check annotation data units directly (annotation may not render if its panel is hidden).
  // wwRefreshWaveformDisplayBasis clears unit="" synchronously then restores it via async
  // backend requests (wwResolveCalloutAnchorMove / wwRecalculatePeakAnnotationsForSource).
  // Use expect.poll() to wait for the async refresh to complete.
  await expect.poll(async () => page.evaluate(() => {
    for (const a of ww.annotations.values()) {
      if (a.type === "callout") return a.data.unit;
    }
    return null;
  }), { timeout: 10000 }).toBe("A");

  await expect.poll(async () => page.evaluate(() => {
    for (const a of ww.annotations.values()) {
      if (wwIsPeakType(a.type)) return a.data.unit;
    }
    return null;
  }), { timeout: 10000 }).toBe("A");
});

test("legacy annotation without stored engineeringType falls back to ww.displayed lookup (DEC-212)", async ({ page }) => {
  const c = await setup(page, { marker: "C" });

  // Create a callout and peak on raw IA.
  await page.locator("#wwCursorModeBtn").click();
  await page.evaluate(async sid => {
    const state = wwTimeGroupCursorState(wwTimeGroupIdForDisplaySourceId(sid));
    state.a.visible = true; state.a.time = .005;
    wwUpdateAllCursorOverlays();
    const { panel, channel } = ww.displayed.get(wwChannelKey(sid, "IA"));
    await wwCreateCalloutFromClick(panel, channel, .005);
    wwEndAnnotationEdit(Array.from(ww.annotations.values()).find(a => a.type === "callout").id, true);
    await wwCreatePeakFromClick(panel, channel, "max");
  }, c.sid);

  // Simulate a pre-Slice-6C.1 annotation: remove engineeringType from annotation data.
  await page.evaluate(() => {
    for (const a of ww.annotations.values()) { delete a.data.engineeringType; }
  });

  // IA is still in ww.displayed with engineeringType: "Current".
  // The fallback ww.displayed lookup should correctly identify it as Current.
  await page.locator("#wwUnitEngineeringBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();

  // wwRefreshWaveformDisplayBasis clears unit="" before the async backend request completes.
  // Use expect.poll() to wait for the refresh; the displayed fallback lookup must resolve "A".
  await expect.poll(async () => page.evaluate(() => {
    for (const a of ww.annotations.values()) {
      if (a.type === "callout") return a.data.unit;
    }
    return null;
  }), { timeout: 10000 }).toBe("A");

  await expect.poll(async () => page.evaluate(() => {
    for (const a of ww.annotations.values()) {
      if (wwIsPeakType(a.type)) return a.data.unit;
    }
    return null;
  }), { timeout: 10000 }).toBe("A");
});

test("calculated Current peak follows ww.unitMode not engineering pending Slice 6D (DEC-212)", async ({ page }) => {
  // Uses Unknown marker so the calculated child shows "Unverified reference" in PU mode.
  const c = await setup(page, { marker: "C" });
  await verify(page, c, true, "unverified");

  // Create a peak annotation on the calculated child (abs(sum(IA, IB))) in PU mode.
  // isCalculated = true for c.child.id; the !isCalculated guard in wwCreatePeakFromClick
  // ensures the peak uses ww.unitMode (per_unit), not "engineering".
  await page.evaluate(async ({ childId, childName }) => {
    const { panel, channel } = ww.displayed.get(wwChannelKey(childId, childName));
    await wwCreatePeakFromClick(panel, channel, "max");
  }, { childId: c.child.id, childName: c.child.name });

  // Calculated Current channel peak: uses ww.unitMode = per_unit → shows "pu" value
  // and "Unverified reference" badge (not engineering — confirming !isCalculated guard scope).
  await expect(page.locator(".ww-peak-value-line")).toContainText("pu");
  await expect(page.locator(".ww-peak-value-line")).toContainText("Unverified reference");

  // Switch to ENG: peak recalculation uses ww.unitMode = engineering → no "pu" text.
  await page.locator("#wwUnitEngineeringBtn").click();
  await expect.poll(async () => await page.locator(".ww-peak-value-line").textContent(), { timeout: 8000 })
    .not.toMatch(/pu/);
});
