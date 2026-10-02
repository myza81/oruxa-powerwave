// Event Reconstruction Grouped Measurement View (DEC-131): one panel per
// display axis (engineering quantity + normalized unit, resolved by the
// backend), shared by every compatible channel across records, native and
// calculated; per-trace fetching, timing and cursor values; the Combined
// Multi-Axis View is not available yet.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, VI, api, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, openEventReconstruction,
  addRecords, channelRow, selectChannel, waitForPlot, plotState, zoomTo,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "VKV", unit: "kV", phase: "A", amplitude: 2, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "Q", unit: "Mvar", amplitude: 20, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

async function selectAll(page, station, names) {
  for (const name of names) await selectChannel(page, station, name);
}

const span = (range) => range[1] - range[0];

test.describe("Event Reconstruction Grouped View -- group formation", () => {
  test("same quantity and unit share a panel; other quantities or units get their own; calculated joins its axis", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    const sourceA = await sourceIdFor(page, "STN_A");
    const calc = await (await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} },
    })).json();
    // The backend's display axis metadata (never a frontend name rule).
    const channels = await api(page, `/sources/${sourceA}/channels`);
    const axes = Object.fromEntries(channels.analog_channels.map((c) => [c.name, c.display_axis_key]));
    expect(axes).toEqual({
      VA: "Voltage|V", VKV: "Voltage|kV", IA: "Current|A", P: "Active Power|MW", Q: "Reactive Power|Mvar", F: "Frequency|Hz",
    });
    expect(calc.display_axis_key).toBe("Voltage|V");

    await addRecords(page, ["STN_A", "STN_B"]);
    await expect(page.locator("#wwErViewGroupedBtn")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#wwErViewCombinedBtn")).toBeDisabled();
    await selectAll(page, "STN_A", ["VA", "VKV", "IA", "P", "Q", "F", "-VA"]);
    await selectAll(page, "STN_B", ["VA", "P", "F"]);
    await waitForPlot(page, 10);
    const state = await plotState(page);
    expect(state.viewMode).toBe("grouped");
    // Panel order: Waveform's engineering-type order (Voltage, Current,
    // Power, Frequency), then first appearance.
    expect(state.groups.map((g) => g.title)).toEqual([
      "Voltage (V)", "Voltage (kV)", "Current (A)", "Active Power (MW)", "Reactive Power (Mvar)", "Frequency (Hz)",
    ]);
    // Inside a panel: record order, then the tree's channel order
    // (native before calculated); both records share compatible panels.
    expect(state.groups.map((g) => g.traces)).toEqual([
      ["STN_A · VA", "STN_A · -VA", "STN_B · VA"],
      ["STN_A · VKV"],
      ["STN_A · IA"],
      ["STN_A · P", "STN_B · P"],
      ["STN_A · Q"],
      ["STN_A · F", "STN_B · F"],
    ]);
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(6);
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("2 records selected · 10 channels in 6 panels");
    // One legend chip per trace with the inherited colour; Y title = unit.
    const voltage = state.groups[0];
    expect(voltage.legend).toEqual(["STN_A · VA", "STN_A · -VA", "STN_B · VA"]);
    // Every trace and legend chip uses exactly the Waveform-owned colour
    // (never an Event Reconstruction override). Note: Waveform's 6-colour
    // palette is assigned first-come per channel, so same-coloured traces
    // can share a grouped panel -- a UAT item, not changed here.
    const owned = await page.evaluate(() => wwErState.plot.panels.flatMap((p) => p.traces).map((t) => wwColorForChannel(t.sourceId, t.channelName)));
    expect(state.panels.map((c) => c.traceColor)).toEqual(owned);
    const toRgb = (hex) => "rgb(" + [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(", ") + ")";
    expect(state.panels.map((c) => c.legendColor)).toEqual(owned.map(toRgb));
    const chartTitles = await page.evaluate(() => wwErState.plot.panels.map((p) => p.chartEl.layout.yaxis.title.text || p.chartEl.layout.yaxis.title));
    expect(chartTitles).toEqual(["V", "kV", "A", "MW", "Mvar", "Hz"]);
    // Each trace keeps its own record timing (B is 0.5 s later).
    const p = state.panels.filter((c) => c.panelTitle === "Active Power (MW)");
    expect(p[0].r[0]).toBeCloseTo(0, 12);
    expect(p[1].r[0]).toBeCloseTo(0.5, 12);
    expect(consoleErrors).toEqual([]);
  });

  test("selection adds a trace, not a panel; a panel disappears with its last trace; order survives re-render and ignores rate", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_SLOWER", startClock: "10:00:00.000000", rateHz: 200 });
    await uploadRecord(page, { station: "STN_FAST", startClock: "10:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_SLOWER", "STN_FAST"]);
    // Clicked fast-first; the panel still lists record order.
    await selectChannel(page, "STN_FAST", "VA");
    await waitForPlot(page, 1);
    await selectChannel(page, "STN_SLOWER", "VA");
    await waitForPlot(page, 2);
    let state = await plotState(page);
    expect(state.groups.map((g) => g.traces)).toEqual([["STN_SLOWER · VA", "STN_FAST · VA"]]);
    const panelKey = state.groups[0].key;
    await page.locator("#mainNavRecordingsBtn").click();
    await openEventReconstruction(page);
    await waitForPlot(page, 2);
    state = await plotState(page);
    expect(state.groups.map((g) => g.traces)).toEqual([["STN_SLOWER · VA", "STN_FAST · VA"]]);
    expect(state.groups[0].key).toBe(panelKey);
    // Removing one trace keeps the panel; removing the last removes it.
    await (await channelRow(page, "STN_FAST", "VA")).click();
    await waitForPlot(page, 1);
    state = await plotState(page);
    expect(state.groups.map((g) => g.traces)).toEqual([["STN_SLOWER · VA"]]);
    expect(state.groups[0].legend).toEqual(["STN_SLOWER · VA"]);
    await selectChannel(page, "STN_SLOWER", "IA");
    await waitForPlot(page, 2);
    expect((await plotState(page)).groups.map((g) => g.title)).toEqual(["Voltage (V)", "Current (A)"]);
    await (await channelRow(page, "STN_SLOWER", "VA")).click();
    await waitForPlot(page, 1);
    expect((await plotState(page)).groups.map((g) => g.title)).toEqual(["Current (A)"]);
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(1);
  });
});

test.describe("Event Reconstruction Grouped View -- records, timing and Y", () => {
  test("identical-timestamp records share a panel; a correction moves only its own trace", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "BAHS 275kV", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "BTGH", startClock: "10:00:00.000000" });
    await addRecords(page, ["BAHS 275kV", "BTGH"]);
    await selectChannel(page, "BAHS 275kV", "VA");
    await selectChannel(page, "BTGH", "VA");
    await waitForPlot(page, 2);
    let state = await plotState(page);
    expect(state.groups.map((g) => g.traces)).toEqual([["BAHS 275kV · VA", "BTGH · VA"]]);
    await memberRow(page, "BTGH").locator("input[data-er-correction-input]").fill("4");
    await memberRow(page, "BTGH").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(async () => (await plotState(page)).panels[1].totalOffsetS).toBeCloseTo(0.004, 12);
    await waitForPlot(page, 2);
    state = await plotState(page);
    const [bahs, btgh] = state.panels;
    expect(bahs.r[0]).toBe(0);
    expect(btgh.r[0]).toBeCloseTo(0.004, 12);
    // The panel's Plotly traces hold exactly these mapped times.
    expect(bahs.customdata).toEqual(bahs.r);
    expect(btgh.customdata).toEqual(btgh.r);
  });

  test("Autoscale Y and Reset cover every trace in a panel; a trace with no samples in view does not distort it", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_SMALL", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_BIG", startClock: "10:00:01.000000", durationS: 2,
      channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 300, frequencyHz: 50 }] });
    await addRecords(page, ["STN_SMALL", "STN_BIG"]);
    await selectChannel(page, "STN_SMALL", "VA");
    await selectChannel(page, "STN_BIG", "VA");
    await waitForPlot(page, 2);
    // Fit All: the joined panel was re-autoscaled over both traces.
    await expect.poll(async () => span((await plotState(page)).groups[0].yRange)).toBeGreaterThan(600);
    // Zoom to where only STN_SMALL has samples, then Autoscale Y.
    await zoomTo(page, 0.2, 0.8);
    let state = await plotState(page);
    expect(state.panels[1].r).toEqual([]);
    expect(span(state.groups[0].yRange)).toBeGreaterThan(600); // kept through X navigation
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => span((await plotState(page)).groups[0].yRange)).toBeLessThan(250);
    state = await plotState(page);
    expect(state.groups[0].yRange[0]).toBeLessThanOrEqual(Math.min(...state.panels[0].values));
    expect(state.groups[0].yRange[1]).toBeGreaterThanOrEqual(Math.max(...state.panels[0].values));
    // Reset: Fit All and both traces' range again.
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => span((await plotState(page)).groups[0].yRange)).toBeGreaterThan(600);
    expect((await plotState(page)).atFitAll).toBe(true);
  });

  test("each trace fetches independently: one envelope next to full resolution in the same panel", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_LONG", startClock: "10:00:00.000000", rateHz: 5000, durationS: 4 });
    await uploadRecord(page, { station: "STN_SHORT", startClock: "10:00:01.000000", rateHz: 1000, durationS: 1 });
    const ids = { long: await sourceIdFor(page, "STN_LONG"), short: await sourceIdFor(page, "STN_SHORT") };
    await addRecords(page, ["STN_LONG", "STN_SHORT"]);
    const requests = [];
    page.on("request", (r) => { if (r.url().includes("/waveform")) requests.push(new URL(r.url())); });
    await selectChannel(page, "STN_LONG", "VA");
    await selectChannel(page, "STN_SHORT", "VA");
    await waitForPlot(page, 2);
    const state = await plotState(page);
    expect(state.groups).toHaveLength(1);
    const [long, short] = state.panels;
    expect(long.representation).toBe("min_max_envelope");
    expect(short.representation).toBe("full_resolution");
    expect(short.r.length).toBe(1001);
    for (const id of [ids.long, ids.short]) {
      expect(requests.some((u) => u.pathname.includes(`/sources/${id}/waveform`))).toBe(true);
    }
  });
});

test.describe("Event Reconstruction Grouped View -- cursors and isolation", () => {
  test("cursor values are per trace in the channel tree, not per panel", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "P");
    await selectChannel(page, "STN_B", "P");
    await waitForPlot(page, 2);
    await page.locator("#wwErCursorModeBtn").click();
    // Not symmetric points of the synthetic sine (values must differ).
    await page.evaluate(() => { wwErSetCursorTime("a", 0.25); wwErSetCursorTime("b", 0.9); });
    await expect.poll(() => page.evaluate(() => wwErState.plot.panels[0].traces.every((t) => t.cursorValues && t.cursorValues.b))).toBe(true);
    const rows = await page.evaluate(() => wwErState.plot.panels[0].traces.map((t) => {
      const row = document.querySelector('#wwErMembersPanel tr.ww-er-channel-row[data-er-channel-key="' + CSS.escape(t.key) + '"]');
      return {
        label: wwErTraceLabelText(t),
        a: row.querySelector(".cur-value--a").textContent,
        b: row.querySelector(".cur-value--b").textContent,
        delta: row.querySelector(".cur-value--delta").textContent,
        values: t.cursorValues,
      };
    }));
    expect(rows.map((r) => r.label)).toEqual(["STN_A · P", "STN_B · P"]);
    // STN_B starts at r = 0.5: no sample at A, a value at B.
    expect(rows[0].a).not.toBe("No sample");
    expect(rows[1].a).toBe("No sample");
    expect(rows[1].b).not.toBe("No sample");
    expect(rows[1].delta).toBe("—");
    expect(rows[0].values.b.value).not.toBe(rows[1].values.b.value);
    // The panel itself carries no per-channel values.
    await expect(page.locator("#wwErPanels .ww-er-panel .cur-value")).toHaveCount(0);
    // The Cur A / Cur B / Δ columns fit in the sidebar (no horizontal scroll).
    const fits = await page.evaluate(() => {
      const table = document.querySelector("#wwErMembersPanel table.channels");
      const body = table.closest(".group-body");
      return table.getBoundingClientRect().width <= body.getBoundingClientRect().width + 1;
    });
    expect(fits).toBe(true);
  });

  test("grouping never changes Waveform's layout, panels or state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const wfRows = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]');
    for (let i = 0; i < 3; i++) {
      const row = wfRows.nth(i);
      if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    }
    const waveform = () => page.evaluate(() => ({
      layoutMode: ww.layoutMode,
      displayed: Array.from(ww.displayed.keys()).sort(),
      panels: ww.panels.map((p) => p.groupKey + ":" + p.channels.map((c) => c.channelName).join(",")),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      presentation: JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
    }));
    await page.waitForTimeout(500);
    const before = await waveform();
    const groupsBefore = await api(page, "/synchronization/time-groups");
    await openEventReconstruction(page);
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectAll(page, "STN_A", ["VA", "P", "F"]);
    await selectAll(page, "STN_B", ["VA", "P"]);
    await waitForPlot(page, 5);
    await page.locator("#wwErZoomInBtn").click();
    await page.locator("#wwErAutoscaleYBtn").click();
    await page.locator("#wwErCursorModeBtn").click();
    await page.locator("#wwErResetViewBtn").click();
    await waitForPlot(page, 5);
    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
