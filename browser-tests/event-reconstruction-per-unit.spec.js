// Event Reconstruction Per-Unit Display (DEC-138). Waveform owns per-unit
// configuration; Event Reconstruction consumes the backend's RESOLVED basis
// and only switches its display between Engineering and Per Unit:
// configured channels in pu on quantity-aware axes, base_required channels
// selected but "PU unavailable", not_applicable channels (Power, Frequency)
// in engineering units as Waveform shows them. Display only: timing,
// cursors, annotations, viewport and selection never change; each unit mode
// keeps its own Y state.
//
// The per-unit settings below are made through Waveform's own endpoints
// (Measurement Groups, Source Default) -- never by Event Reconstruction.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, api, addRecords, channelRow, selectChannel,
  waitForPlot, plotState, zoomTo, openEventReconstruction,
} = require("./support/event_reconstruction_helpers");

const LL_BASE_KV = 275;
const LG_BASE_KV = LL_BASE_KV / Math.sqrt(3); // the resolved L-G base, ~158.77 kV
const IBASE_KA = 2;
const STN_A = [
  { name: "VA", unit: "kV", phase: "A", amplitude: 159.5, frequencyHz: 50 },
  { name: "VB", unit: "kV", phase: "B", amplitude: 159.5, frequencyHz: 50, phaseShiftRad: -2 * Math.PI / 3 },
  { name: "IA", unit: "A", phase: "A", amplitude: 1500, frequencyHz: 50, phaseShiftRad: 0.3 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "Q", unit: "Mvar", amplitude: 30, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 0.2, frequencyHz: 0.5 },
];
const STN_B = [
  { name: "VA", unit: "kV", phase: "A", amplitude: 159.5, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 1500, frequencyHz: 50 },
];

const wsUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${path}`;

// Waveform-owned settings, through Waveform's own endpoints. `legacyKv`:
// the source-wide Source Default base that must NOT reach a Measurement
// Group member (the earlier confusion).
async function configure(page, station, { voltage = [], current = [], legacyKv = null } = {}) {
  const sourceId = await sourceIdFor(page, station);
  const groupsUrl = await wsUrl(page, `/sources/${sourceId}/measurement-groups`);
  for (const group of await (await page.request.get(groupsUrl)).json()) await page.request.delete(`${groupsUrl}/${group.id}`);
  if (legacyKv !== null) {
    expect((await page.request.put(await wsUrl(page, `/per-unit/sources/${sourceId}`), { data: { voltage_base_value: legacyKv } })).ok()).toBe(true);
  }
  const refs = (names) => names.map((channel_name) => ({ kind: "source", source_id: sourceId, channel_name }));
  if (voltage.length) {
    const group = await (await page.request.post(groupsUrl, { data: { kind: "voltage", display_name: station + " 275 kV", status: "confirmed", channel_refs: refs(voltage) } })).json();
    expect((await page.request.put(`${groupsUrl}/${group.id}/voltage-config`, { data: { nominal_voltage_ll_kv: LL_BASE_KV } })).ok()).toBe(true);
  }
  if (current.length) {
    const group = await (await page.request.post(groupsUrl, { data: { kind: "current", display_name: station + " current", status: "confirmed", channel_refs: refs(current) } })).json();
    expect((await page.request.put(`${groupsUrl}/${group.id}/current-config`, { data: { method: "manual", manual_ibase_ka: IBASE_KA } })).ok()).toBe(true);
  }
  return sourceId;
}

// Everything Waveform owns about per unit, for "never touched" checks.
async function perUnitSettings(page) {
  const out = {};
  for (const station of ["STN_A", "STN_B"]) {
    const sourceId = await sourceIdFor(page, station);
    out[station] = {
      sourceDefault: await (await page.request.get(await wsUrl(page, `/per-unit/sources/${sourceId}`))).json(),
      groups: await (await page.request.get(await wsUrl(page, `/sources/${sourceId}/measurement-groups`))).json(),
    };
  }
  return JSON.stringify(out);
}

async function setup(page, { configureB = false } = {}) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: STN_A });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4, channels: STN_B });
  await configure(page, "STN_A", { voltage: ["VA", "VB"], current: ["IA"], legacyKv: 132 });
  if (configureB) await configure(page, "STN_B", { voltage: ["VA"] });
  else await configure(page, "STN_B");
  await addRecords(page, ["STN_A", "STN_B"]);
}

async function selectAll(page, pairs) {
  for (const [station, name] of pairs) await selectChannel(page, station, name);
  await waitForPlot(page, (await plotState(page)).panels.length);
}

async function setUnits(page, mode) {
  await page.locator(mode === "per_unit" ? "#wwErUnitPerUnitBtn" : "#wwErUnitEngineeringBtn").click();
  await expect(page.locator(mode === "per_unit" ? "#wwErUnitPerUnitBtn" : "#wwErUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
}

// Waits until the plot shows `count` traces, all loaded, every Y axis
// scaled.
async function settle(page, count) {
  await waitForPlot(page, count);
  await expect.poll(async () => (await plotState(page)).groups.flatMap((g) => g.axes).every((a) => !a.pending)).toBe(true);
}

const traceOf = (state, label) => state.panels.find((c) => c.label === label);
const titles = (state) => state.groups.map((g) => g.title);
const unavailableBadge = async (page, station, name) => (await channelRow(page, station, name)).locator(".ww-er-pu-unavailable");

// The backend's own cursor values -- the endpoint Waveform's cursors use.
async function backendCursorValues(page, sourceId, names, a, b, unitMode) {
  const resp = await page.request.post(await wsUrl(page, `/sources/${sourceId}/cursor-values`), {
    data: { analog_channel_names: names, cursor_a_time: a, cursor_b_time: b, unit_mode: unitMode },
  });
  return Object.fromEntries((await resp.json()).channels.map((c) => [c.channel_name, c]));
}

test.describe("Event Reconstruction Per-Unit Display -- ownership and selector", () => {
  test("Units ENG|PU in Waveform's wording, Engineering by default; no per-unit configuration here; switching never writes a setting", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "IA"]]);
    await expect(page.locator("#wwErUnitModeToggle")).toHaveAttribute("aria-label", "Unit Mode");
    await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveText("ENG");
    await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveAttribute("title", "Engineering Units");
    await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveText("PU");
    await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("title", "Per Unit");
    // Default Engineering, even though bases are configured.
    await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
    expect(titles(await plotState(page))).toEqual(["Voltage (kV)", "Current (A)"]);
    // No per-unit editor of any kind on this page.
    const erPage = page.locator("#pageEventReconstruction");
    for (const text of ["Per-Unit Settings", "Measurement Group", "Voltage Base", "Current Base", "Line-to-Ground"]) {
      await expect(erPage.getByText(text, { exact: false })).toHaveCount(0);
    }
    // (Its only numeric inputs are the records' timing corrections.)
    await expect(erPage.locator('input:not([data-er-correction-input])')).toHaveCount(0);

    const before = await perUnitSettings(page);
    const writes = [];
    page.on("request", (request) => {
      if (request.method() !== "GET" && /per-unit|measurement-groups|voltage-config|current-config/.test(request.url())) writes.push(request.url());
    });
    await setUnits(page, "per_unit");
    await settle(page, 2);
    await setUnits(page, "engineering");
    await settle(page, 2);
    await setUnits(page, "per_unit");
    await settle(page, 2);
    expect(writes).toEqual([]);
    expect(await perUnitSettings(page)).toEqual(before);
    // Waveform's own unit mode is not Event Reconstruction's.
    expect(await page.evaluate(() => ww.unitMode)).toBe("engineering");
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction Per-Unit Display -- values, grouping, unavailable", () => {
  test("L-L/L-G regression: 275 kV L-L group base on an L-G channel -> 275/sqrt(3) kV, as Waveform's endpoints; quantity-aware axes in Grouped and Combined", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    const sourceA = await sourceIdFor(page, "STN_A");
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "VB"], ["STN_A", "IA"], ["STN_A", "P"], ["STN_A", "Q"], ["STN_A", "F"]]);
    await settle(page, 6);
    let state = await plotState(page);
    expect(titles(state)).toEqual(["Voltage (kV)", "Current (A)", "Active Power (MW)", "Reactive Power (Mvar)", "Frequency (Hz)"]);
    const eng = Object.fromEntries(state.panels.map((c) => [c.label, c]));

    await setUnits(page, "per_unit");
    await settle(page, 6);
    state = await plotState(page);
    // Voltage and Current each their own pu panel; Power / Frequency stay
    // engineering (Waveform: not applicable) -- never one "pu" collapse.
    expect(titles(state)).toEqual(["Voltage (pu)", "Current (pu)", "Active Power (MW)", "Reactive Power (Mvar)", "Frequency (Hz)"]);
    expect(state.groups[0].traces).toEqual(["STN_A · VA", "STN_A · VB"]);
    const va = traceOf(state, "STN_A · VA");
    expect(va.unit).toBe("pu");
    expect(traceOf(state, "STN_A · P").unit).toBe("MW");
    // Same samples (x), same colour, values over the ONE resolved base:
    // ~159.5 kV engineering -> ~1.0046 pu (never /275, never the legacy /132).
    expect(va.r).toEqual(eng["STN_A · VA"].r);
    expect(va.traceColor).toBe(eng["STN_A · VA"].traceColor);
    va.values.forEach((value, index) => expect(value).toBeCloseTo(eng["STN_A · VA"].values[index] / LG_BASE_KV, 9));
    const peak = Math.max(...va.values);
    expect(peak).toBeGreaterThan(1.0);
    expect(peak).toBeLessThan(1.01);
    traceOf(state, "STN_A · IA").values.forEach((value, index) => expect(value).toBeCloseTo(eng["STN_A · IA"].values[index] / (IBASE_KA * 1000), 9));
    expect(traceOf(state, "STN_A · P").values).toEqual(eng["STN_A · P"].values);
    // The basis Event Reconstruction consumed is Waveform's resolved one.
    const resolved = await api(page, `/sources/${sourceA}/per-unit-resolution?channel_name=VA`);
    expect(resolved.source_kind).toBe("measurement_group");
    expect(resolved.effective_base_amount).toBeCloseTo(LG_BASE_KV, 9);

    // Combined: one panel, one Y axis per quantity; the unit mode stays.
    await page.locator("#wwErViewCombinedBtn").click();
    await settle(page, 6);
    state = await plotState(page);
    expect(state.groups[0].axes.map((a) => a.title)).toEqual([
      "Voltage (pu)", "Current (pu)", "Active Power (MW)", "Reactive Power (Mvar)", "Frequency (Hz)",
    ]);
    expect(traceOf(state, "STN_A · VA").values).toEqual(va.values);
    await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#wwErViewGroupedBtn").click();
    await settle(page, 6);
    await expect(page.locator("#wwErUnitPerUnitBtn")).toHaveAttribute("aria-pressed", "true");
    expect(titles(await plotState(page))[0]).toBe("Voltage (pu)");
    expect(consoleErrors).toEqual([]);
  });

  test("no per-unit basis: stays selected, PU unavailable in the tree and notice, never plotted or valued; Engineering restores it", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await selectAll(page, [["STN_A", "VA"], ["STN_B", "VA"], ["STN_B", "IA"]]);
    await page.locator("#wwErCursorModeBtn").click();
    await settle(page, 3);
    const viewport = (await plotState(page)).viewport;

    await setUnits(page, "per_unit");
    await settle(page, 1);
    const state = await plotState(page);
    expect(state.panels.map((c) => c.label)).toEqual(["STN_A · VA"]);
    expect(state.viewport).toEqual(viewport); // Fit All still counts STN_B
    for (const name of ["VA", "IA"]) {
      const row = await channelRow(page, "STN_B", name);
      await expect(row).toHaveAttribute("aria-pressed", "true"); // still selected
      await expect(await unavailableBadge(page, "STN_B", name)).toHaveText("PU unavailable");
      await expect(await unavailableBadge(page, "STN_B", name)).toHaveAttribute("title", /Configure it in Waveform/);
      // No fake PU cursor value.
      await expect(row.locator(".cur-value--a")).toHaveText("PU n/a");
      await expect(row.locator(".cur-value--a")).toHaveAttribute("title", /^PU unavailable/);
      await expect(row.locator(".cur-value--b")).toHaveText("PU n/a");
      await expect(row.locator(".cur-value--delta")).toHaveText("—");
    }
    await expect(await unavailableBadge(page, "STN_A", "VA")).toHaveCount(0);
    await expect(page.locator("#wwErUnitNotice")).toBeVisible();
    await expect(page.locator("#wwErUnitNotice")).toContainText("2 selected channels are PU unavailable");
    await expect(page.locator("#wwErUnitNotice")).toContainText("STN_B · VA");
    await expect(page.locator("#wwErCanvasMeta")).toContainText("2 PU unavailable");

    // Engineering: the same channels, plotted again at once, no badge.
    await setUnits(page, "engineering");
    await settle(page, 3);
    expect((await plotState(page)).panels.map((c) => c.label).sort()).toEqual(["STN_A · VA", "STN_B · IA", "STN_B · VA"]);
    await expect(await unavailableBadge(page, "STN_B", "VA")).toHaveCount(0);
    await expect(page.locator("#wwErUnitNotice")).toBeHidden();
    await expect((await channelRow(page, "STN_B", "VA")).locator(".cur-value--a")).not.toHaveText("PU n/a");

    // A setting made in Waveform reaches Event Reconstruction on the next
    // visit -- no new reconstruction needed.
    await setUnits(page, "per_unit");
    await settle(page, 1);
    await configure(page, "STN_B", { voltage: ["VA"] });
    await page.locator("#mainNavWaveformBtn").click();
    await openEventReconstruction(page);
    await settle(page, 2);
    expect((await plotState(page)).groups[0].traces).toEqual(["STN_A · VA", "STN_B · VA"]);
    await expect(await unavailableBadge(page, "STN_B", "VA")).toHaveCount(0);
    await expect(await unavailableBadge(page, "STN_B", "IA")).toHaveText("PU unavailable");
    expect(consoleErrors).toEqual([]);
  });

  test("calculated channels: an inheriting one shares the native pu axis; generic Voltage subtraction is PU unavailable", async ({ page }) => {
    await setup(page);
    const sourceA = await sourceIdFor(page, "STN_A");
    const create = async (data) => (await (await page.request.post(await wsUrl(page, "/calculated-channels"), { data })).json());
    const negated = await create({ name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} });
    await create({ name: "VA-VB", operation: "subtraction", inputs: [
      { kind: "source", source_id: sourceA, channel_name: "VA" }, { kind: "source", source_id: sourceA, channel_name: "VB" }], parameters: {} });
    await page.evaluate(() => wwErRefresh());
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "-VA"], ["STN_A", "VA-VB"]]);
    await settle(page, 3);
    expect(titles(await plotState(page))).toEqual(["Voltage (kV)"]);
    const eng = traceOf(await plotState(page), "STN_A · -VA");

    await setUnits(page, "per_unit");
    await settle(page, 2);
    const state = await plotState(page);
    expect(titles(state)).toEqual(["Voltage (pu)"]);
    expect(state.groups[0].traces).toEqual(["STN_A · VA", "STN_A · -VA"]);
    traceOf(state, "STN_A · -VA").values.forEach((value, index) => expect(value).toBeCloseTo(eng.values[index] / LG_BASE_KV, 9));
    const resolved = await api(page, `/calculated-channels/${negated.id}/per-unit-resolution`);
    expect(resolved.status).toBe("configured");
    await expect(await unavailableBadge(page, "STN_A", "VA-VB")).toHaveText("PU unavailable");
    await expect(await unavailableBadge(page, "STN_A", "-VA")).toHaveCount(0);
  });
});

test.describe("Event Reconstruction Per-Unit Display -- display only", () => {
  test("ENG <-> PU changes no timing, cursor, annotation, viewport, reference, correction, active record, time display or view mode", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "P"], ["STN_B", "VA"]]);
    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("7");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await page.locator("#wwErCursorModeBtn").click();
    await zoomTo(page, 1.2, 2.6);
    await memberRow(page, "STN_B").locator("[data-er-activate-record]").click();
    await page.locator("#wwErTimeAbsoluteBtn").click();
    await page.request.post(await wsUrl(page, "/event-reconstruction/definition/annotations"),
      { data: { type: "text_note", reconstruction_time_s: 1.5, y_fraction: 0.3, text: "Fault" } });
    await page.evaluate(() => wwErRefresh());
    await settle(page, 3);
    const snapshot = async () => {
      const state = await plotState(page);
      return {
        viewport: state.viewport, fitAll: state.fitAll, origin: state.origin, viewMode: state.viewMode,
        x: Object.fromEntries(state.panels.filter((c) => c.label !== "STN_B · VA").map((c) => [c.label, c.r])),
        page: await page.evaluate(() => ({
          cursors: [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time],
          activeRecordId: wwErState.activeRecordId, timeDisplay: wwErState.timeDisplay,
          selected: Object.keys(wwErState.selectedChannels).sort(),
        })),
        definition: await api(page, "/event-reconstruction/definition"),
      };
    };
    const before = await snapshot();
    await setUnits(page, "per_unit");
    await settle(page, 2);
    expect(await snapshot()).toEqual(before);
    await setUnits(page, "engineering");
    await settle(page, 3);
    expect(await snapshot()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });

  test("Y state is unit-mode-local: an Engineering manual range never reaches pu; Y drag works in pu; Autoscale / Reset act on the current unit only", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "P"]]);
    await settle(page, 2);
    const dragAxis = async (panelIndex, dy) => {
      const target = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator('.draglayer .nsdrag[data-subplot="xy"]');
      const box = await target.boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + dy / 2, { steps: 5 });
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + dy, { steps: 5 });
      await page.mouse.up();
    };
    const voltageAxis = async () => (await plotState(page)).groups[0].axes[0];
    await dragAxis(0, 40);
    await expect.poll(async () => (await voltageAxis()).manual).toBe(true);
    const engManual = (await voltageAxis()).range;
    const powerRange = (await plotState(page)).groups[1].yRange;

    await setUnits(page, "per_unit");
    await settle(page, 2);
    let axis = await voltageAxis();
    expect(axis.title).toBe("pu");
    expect(axis.manual).toBe(false); // autoscaled on first entry, not copied
    expect(Math.max(...axis.range.map(Math.abs))).toBeLessThan(2);
    await dragAxis(0, -30);
    await expect.poll(async () => (await voltageAxis()).manual).toBe(true);
    const puManual = (await voltageAxis()).range;

    await setUnits(page, "engineering");
    await settle(page, 2);
    axis = await voltageAxis();
    expect(axis.manual).toBe(true);
    expect(axis.range).toEqual(engManual);
    expect((await plotState(page)).groups[1].yRange).toEqual(powerRange);
    await setUnits(page, "per_unit");
    await settle(page, 2);
    expect((await voltageAxis()).range).toEqual(puManual);

    // Autoscale Y in Per Unit: only pu's manual range goes.
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => (await voltageAxis()).manual).toBe(false);
    await setUnits(page, "engineering");
    await settle(page, 2);
    expect((await voltageAxis()).range).toEqual(engManual);
    // Reset in Engineering keeps the unit mode and clears Engineering's.
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await voltageAxis()).manual).toBe(false);
    await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveAttribute("aria-pressed", "true");
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction Per-Unit Display -- cursors and annotations", () => {
  test("cursor values: the same samples, pu values as Waveform's endpoint gives them, A/B/Δ all in pu", async ({ page }) => {
    await setup(page);
    const sourceA = await sourceIdFor(page, "STN_A");
    await selectAll(page, [["STN_A", "VA"], ["STN_A", "P"]]);
    await page.locator("#wwErCursorModeBtn").click();
    await settle(page, 2);
    const times = await page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time]);
    const row = await channelRow(page, "STN_A", "VA");
    const cells = async () => ({
      a: await row.locator(".cur-value--a").textContent(), b: await row.locator(".cur-value--b").textContent(),
      delta: await row.locator(".cur-value--delta").textContent(),
    });
    const format = (value) => page.evaluate((v) => wwFormatEngineeringValue(v), value);
    const formatDelta = (value) => page.evaluate((v) => (v > 0 ? "+" : "") + wwFormatEngineeringValue(v), value);
    const engValues = (await backendCursorValues(page, sourceA, ["VA", "P"], times[0], times[1], "engineering"));
    await expect.poll(cells).toEqual({ a: await format(engValues.VA.a_value), b: await format(engValues.VA.b_value),
      delta: await formatDelta(engValues.VA.b_value - engValues.VA.a_value) });

    await setUnits(page, "per_unit");
    await settle(page, 2);
    expect(await page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time])).toEqual(times);
    const puValues = await backendCursorValues(page, sourceA, ["VA", "P"], times[0], times[1], "per_unit");
    expect(puValues.VA.per_unit_status).toBe("configured");
    expect(puValues.VA.a_value).toBeCloseTo(engValues.VA.a_value / LG_BASE_KV, 9);
    await expect.poll(cells).toEqual({ a: await format(puValues.VA.a_value), b: await format(puValues.VA.b_value),
      delta: await formatDelta(puValues.VA.b_value - puValues.VA.a_value) });
    // Not applicable: unchanged engineering values.
    await expect((await channelRow(page, "STN_A", "P")).locator(".cur-value--a")).toHaveText(await format(engValues.P.a_value));
  });

  test("Callouts / Peaks: the same sample, the value in the current unit on the pu axis; PU unavailable says so; Text Notes unchanged", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    const sources = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B") };
    await selectAll(page, [["STN_A", "VA"], ["STN_B", "VA"]]);
    await settle(page, 2);
    const definition = await api(page, "/event-reconstruction/definition");
    const recordOf = (sourceId) => definition.members.find((m) => m.source_ids.includes(sourceId)).record_id;
    const post = async (data) => {
      const resp = await page.request.post(await wsUrl(page, "/event-reconstruction/definition/annotations"), { data });
      expect(resp.status()).toBe(201);
    };
    // The engineering anchor, exactly as a Callout placement stores it.
    const anchor = await (await page.request.post(await wsUrl(page, `/sources/${sources.a}/annotation-anchor`),
      { data: { channel_name: "VA", approximate_elapsed_seconds: 1.2052, unit_mode: "engineering" } })).json();
    await post({ type: "callout", channel: { record_id: recordOf(sources.a), source_id: sources.a, channel_name: "VA" },
      anchor: { sample_index: anchor.sample_index, source_elapsed_s: anchor.elapsed_seconds, value: anchor.value, unit: anchor.unit }, text: "A" });
    await post({ type: "peak_max", channel: { record_id: recordOf(sources.a), source_id: sources.a, channel_name: "VA" } });
    await post({ type: "callout", channel: { record_id: recordOf(sources.b), source_id: sources.b, channel_name: "VA" },
      anchor: { sample_index: 100, source_elapsed_s: 0.1, value: 0, unit: "kV" }, text: "B" });
    await post({ type: "text_note", reconstruction_time_s: 1.5, y_fraction: 0.25, text: "Fault" });
    await page.evaluate(() => wwErRefresh());
    const stored = JSON.stringify((await api(page, "/event-reconstruction/definition")).annotations);
    const ann = await page.evaluate(() => wwErAnnotations().map((a) => ({ id: a.annotation_id, type: a.type, text: a.text })));
    const id = (type, text) => ann.find((a) => a.type === type && (text === undefined || a.text === text)).id;
    const look = (annotationId) => page.evaluate((annotationId) => {
      const a = wwErAnnotationById(annotationId);
      const el = document.querySelector(`#wwErAnnotationOverlay .ww-annotation[data-er-annotation-id="${annotationId}"]`);
      const peak = wwErAnnotationPeak(a);
      return {
        visible: !!el && el.style.display !== "none",
        value: wwErAnnotationValue(a), time: wwErAnnotationTime(a), meta: wwErAnnotationMetaLine(a),
        valueLine: el && el.querySelector(".ww-peak-value-line") ? el.querySelector(".ww-peak-value-line").textContent : null,
        sampleIndex: peak ? peak.sampleIndex : null, left: el ? el.style.left : null, top: el ? el.style.top : null,
      };
    }, annotationId);
    await expect.poll(async () => (await look(id("peak_max"))).sampleIndex).not.toBeNull();
    const eng = { callout: await look(id("callout", "A")), peak: await look(id("peak_max")), note: await look(id("text_note")) };
    expect(eng.callout.value).toBe(anchor.value);

    await setUnits(page, "per_unit");
    await settle(page, 1);
    await expect.poll(async () => (await look(id("callout", "A"))).value).toBeCloseTo(anchor.value / LG_BASE_KV, 9);
    const pu = { callout: await look(id("callout", "A")), peak: await look(id("peak_max")) };
    // Same sample, same time; only the value representation changed.
    expect(pu.callout.time).toBe(eng.callout.time);
    expect(pu.callout.meta).toContain(" pu");
    await expect.poll(async () => (await look(id("peak_max"))).sampleIndex).toBe(eng.peak.sampleIndex);
    expect((await look(id("peak_max"))).value).toBeCloseTo(eng.peak.value / LG_BASE_KV, 9);
    expect((await look(id("peak_max"))).valueLine).toMatch(/^\+Peak: .* pu$/);
    // Drawn on the pu axis at that value.
    const placed = await page.evaluate((annotationId) => {
      const a = wwErAnnotationById(annotationId);
      const trace = wwErAnnotationTrace(a);
      const fl = trace.panel.chartEl._fullLayout;
      const wrap = document.getElementById("wwErPanelsWrap").getBoundingClientRect();
      const marker = document.querySelector(`#wwErCalloutConnectorLayer [data-annotation-id="${annotationId}"] .ww-callout-anchor-marker`);
      return { cy: Number(marker.getAttribute("cy")),
        expected: trace.panel.chartEl.getBoundingClientRect().top - wrap.top + fl.yaxis._offset + fl.yaxis.l2p(wwErAnnotationValue(a)),
        axisTitle: trace.panel.labelEl.textContent };
    }, id("callout", "A"));
    expect(placed.axisTitle).toBe("Voltage (pu)");
    expect(Math.abs(placed.cy - placed.expected)).toBeLessThan(1);
    // No basis: PU unavailable, hidden, never a value.
    const unavailable = await look(id("callout", "B"));
    expect(unavailable.visible).toBe(false);
    expect(unavailable.value).toBeNull();
    expect(unavailable.meta).toContain("PU unavailable");
    // Text Note: unaffected.
    const note = await look(id("text_note"));
    expect(note.time).toBe(eng.note.time);
    expect(note.visible).toBe(true);
    // Nothing stored changed.
    expect(JSON.stringify((await api(page, "/event-reconstruction/definition")).annotations)).toBe(stored);

    await setUnits(page, "engineering");
    await settle(page, 2);
    expect((await look(id("callout", "A"))).value).toBe(anchor.value);
    expect((await look(id("callout", "B"))).meta).not.toContain("PU unavailable");
    expect(consoleErrors).toEqual([]);
  });
});
