// Event Reconstruction Combined Multi-Axis View (DEC-132): every selected
// analog channel in one panel, one Plotly Y axis per backend display axis
// (the Grouped View's own grouping and order), deterministic left/right
// axis placement with Plotly-sized margins, per-axis autoscale, X-only
// navigation, one A/B cursor overlay, and a presentation-only mode switch
// that reuses fetched data.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, openEventReconstruction, api,
  addRecords, channelRow, selectChannel, waitForPlot, plotState, zoomTo, dragOnPanel,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "VKV", unit: "kV", phase: "A", amplitude: 2, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "Q", unit: "Mvar", amplitude: 20, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

const span = (range) => range[1] - range[0];

async function selectAll(page, station, names) {
  for (const name of names) await selectChannel(page, station, name);
}

async function deselect(page, station, name) {
  const row = await channelRow(page, station, name);
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "false");
}

async function setMode(page, mode) {
  await page.locator(mode === "combined" ? "#wwErViewCombinedBtn" : "#wwErViewGroupedBtn").click();
  await expect(page.locator("#wwErViewCombinedBtn")).toHaveAttribute("aria-pressed", String(mode === "combined"));
  await expect(page.locator("#wwErViewGroupedBtn")).toHaveAttribute("aria-pressed", String(mode === "grouped"));
}

// Waits until every Y axis of every panel has been autoscaled (or, with
// no samples, is still legitimately pending) -- `pendingKeys` lists the
// axes expected to stay pending.
async function waitForAxesScaled(page, pendingKeys = []) {
  await expect.poll(async () => (await plotState(page)).groups.flatMap((g) => g.axes)
    .filter((a) => a.pending).map((a) => a.key).sort()).toEqual(pendingKeys.slice().sort());
}

function expectAxisCovers(state, axis) {
  const values = state.panels.filter((c) => c.axisKey === axis.key).flatMap((c) => c.values).filter(Number.isFinite);
  expect(values.length).toBeGreaterThan(0);
  expect(axis.range[0]).toBeLessThanOrEqual(Math.min(...values));
  expect(axis.range[1]).toBeGreaterThanOrEqual(Math.max(...values));
}

async function cursorLines(page) {
  return page.evaluate(() => {
    const plot = wwErState.plot;
    return plot.panels.map((p) => {
      const xa = p.chartEl._fullLayout.xaxis;
      const chartLeft = p.chartEl.getBoundingClientRect().left - p.chartWrapEl.getBoundingClientRect().left;
      const line = (kind) => {
        const el = p.cursorLayerEl.querySelector('[data-er-cursor-line="' + kind + '"]');
        return {
          hidden: p.cursorLayerEl.hidden || el.hidden,
          left: parseFloat(el.style.left),
          plotlyX: chartLeft + xa._offset + xa.l2p(plot.cursors[kind].time - plot.origin),
        };
      };
      return { a: line("a"), b: line("b") };
    });
  });
}

async function treeValues(page) {
  return page.evaluate(() => wwErState.plot.panels.flatMap((p) => p.traces).map((t) => {
    const row = document.querySelector('#wwErMembersPanel tr.ww-er-channel-row[data-er-channel-key="' + CSS.escape(t.key) + '"]');
    return [t.key, row.querySelector(".cur-value--a").textContent, row.querySelector(".cur-value--b").textContent,
      row.querySelector(".cur-value--delta").textContent];
  }).sort());
}

test.describe("Event Reconstruction Combined View -- axes and rendering", () => {
  test("one panel; one Y axis per display axis in Grouped order; the same traces per axis; legend by axis", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    const sourceA = await sourceIdFor(page, "STN_A");
    await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} },
    });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectAll(page, "STN_A", ["VA", "VKV", "IA", "P", "Q", "F", "-VA"]);
    await selectAll(page, "STN_B", ["VA", "P", "F"]);
    await waitForPlot(page, 10);
    const grouped = await plotState(page);
    expect(grouped.groups).toHaveLength(6);

    await setMode(page, "combined");
    await waitForPlot(page, 10);
    await waitForAxesScaled(page);
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(1);
    const state = await plotState(page);
    const panel = state.groups[0];
    expect(state.viewMode).toBe("combined");
    expect(panel.combined).toBe(true);
    expect(panel.title).toBe("All selected channels · 6 Y axes");
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("2 records selected · 10 channels on 6 Y axes");

    // Axes = the Grouped panels, in the same order (ANALOG_GROUP_ORDER,
    // then first appearance), each with exactly the same traces.
    expect(panel.axes.map((a) => a.title)).toEqual(grouped.groups.map((g) => g.title));
    expect(panel.axes.map((a) => a.traceKeys)).toEqual(grouped.groups.map((g) => g.traceKeys));
    // Trace order: axis order, then the browser's record/source/channel order.
    expect(panel.traceKeys).toEqual(grouped.groups.flatMap((g) => g.traceKeys));
    // Every trace is drawn on its own axis; V and kV, MW and Mvar stay apart.
    for (const channel of state.panels) {
      expect(channel.traceYAxis).toBe(panel.axes.find((a) => a.key === channel.axisKey).ref);
    }
    expect(new Set(panel.axes.map((a) => a.key)).size).toBe(6);

    // Placement: left, right, then alternately left/right pushed outward.
    expect(panel.axes.map((a) => a.side)).toEqual(["left", "right", "left", "right", "left", "right"]);
    expect(panel.axes[0].overlaying).toBe(null);
    expect([panel.axes[1].anchor, panel.axes[1].overlaying, panel.axes[1].autoshift]).toEqual(["x", "y", false]);
    for (const axis of panel.axes.slice(2)) expect([axis.anchor, axis.overlaying, axis.autoshift]).toEqual(["free", "y", true]);
    expect(panel.axes[2].shift).toBeLessThan(0);
    expect(panel.axes[4].shift).toBeLessThan(panel.axes[2].shift);
    expect(panel.axes[3].shift).toBeGreaterThan(0);
    expect(panel.axes[5].shift).toBeGreaterThan(panel.axes[3].shift);
    // X-only navigation on every axis; every axis scaled to its own data.
    for (const axis of panel.axes) {
      expect(axis.fixedRange).toBe(true);
      expect(axis.autorange).toBe(false);
      expect(axis.showTickLabels).toBe(true);
      expectAxisCovers(state, axis);
    }

    // Legend: one chip per trace, under its axis's title.
    expect(panel.axisLegend.map((l) => l.title)).toEqual(grouped.groups.map((g) => g.title));
    expect(panel.axisLegend.map((l) => l.chips)).toEqual(grouped.groups.map((g) => g.traces));
    // Waveform-owned name/colour, unchanged by the mode; solid lines only.
    for (const channel of state.panels) {
      const before = grouped.panels.find((c) => c.key === channel.key);
      expect([channel.traceName, channel.traceColor, channel.legendColor]).toEqual([before.traceName, before.traceColor, before.legendColor]);
    }
    expect(await page.evaluate(() => wwErState.plot.panels[0].chartEl.data.every((d) => !d.line.dash))).toBe(true);

    // The larger fixed combined height; still no resize grip.
    expect(panel.height).toBeCloseTo(420, 0);
    await expect(page.locator("#wwErPanels .ww-resize-handle")).toHaveCount(0);
    // Six axes: the advisory readability notice.
    await expect(page.locator("#wwErAxisNotice")).toBeVisible();
    await expect(page.locator("#wwErAxisNotice")).toContainText("6 Y axes in one panel");
    expect(consoleErrors).toEqual([]);
  });

  test("margins follow the axes; selection adds/removes an axis; untouched axes keep their range", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    await addRecords(page, ["STN_A", "STN_B"]);
    await setMode(page, "combined");
    await selectAll(page, "STN_A", ["VA", "IA"]);
    await waitForPlot(page, 2);
    await waitForAxesScaled(page);
    const two = (await plotState(page)).groups[0];
    expect(two.axes.map((a) => [a.title, a.side])).toEqual([["Voltage (V)", "left"], ["Current (A)", "right"]]);
    await expect(page.locator("#wwErAxisNotice")).toBeHidden();

    // A channel of a new quantity adds an axis; the existing axes keep
    // their ranges (X and selection never rescale an untouched axis).
    await selectChannel(page, "STN_A", "P");
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    let panel = (await plotState(page)).groups[0];
    expect(panel.axes.map((a) => a.title)).toEqual(["Voltage (V)", "Current (A)", "Active Power (MW)"]);
    expect(panel.axes[0].range).toEqual(two.axes[0].range);
    expect(panel.axes[1].range).toEqual(two.axes[1].range);

    // A channel joining an existing axis re-autoscales that axis only.
    await uploadRecord(page, { station: "STN_BIG", startClock: "10:00:00.000000",
      channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 300, frequencyHz: 50 }] });
    await openEventReconstruction(page);
    await addRecords(page, ["STN_BIG"]);
    await selectChannel(page, "STN_BIG", "VA");
    await waitForPlot(page, 4);
    await waitForAxesScaled(page);
    const joined = (await plotState(page)).groups[0];
    expect(span(joined.axes[0].range)).toBeGreaterThan(600);
    expect(joined.axes[1].range).toEqual(panel.axes[1].range);
    expect(joined.axes[2].range).toEqual(panel.axes[2].range);

    // Six axes: each extra axis widens the margins (Plotly-sized), the
    // plot area narrows; the notice appears above four.
    await selectAll(page, "STN_A", ["VKV", "Q", "F"]);
    await waitForPlot(page, 7);
    await waitForAxesScaled(page);
    const six = (await plotState(page)).groups[0];
    expect(six.axes).toHaveLength(6);
    expect(six.plotLeft).toBeGreaterThan(two.plotLeft);
    expect(six.plotWidth).toBeLessThan(two.plotWidth);
    await expect(page.locator("#wwErAxisNotice")).toBeVisible();
    // Back to four: no notice (advisory only above four).
    await deselect(page, "STN_A", "Q");
    await deselect(page, "STN_A", "F");
    await waitForPlot(page, 5);
    await expect(page.locator("#wwErAxisNotice")).toBeHidden();
    expect((await plotState(page)).groups[0].axes.map((a) => a.title))
      .toEqual(["Voltage (V)", "Voltage (kV)", "Current (A)", "Active Power (MW)"]);
    // The last channel gone: the panel goes, the empty state returns.
    for (const name of ["VA", "VKV", "IA", "P"]) await deselect(page, "STN_A", name);
    await deselect(page, "STN_BIG", "VA");
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(0);
    await expect(page.locator("#wwErEmptyState")).toBeVisible();
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("3 records selected · 0 channels on 0 Y axes");
  });
});

test.describe("Event Reconstruction Combined View -- navigation and Y", () => {
  test("Box Zoom and Pan are X-only on every axis; Zoom In/Out and Fit All clamp; double-click resets", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4, channels: MIXED });
    await addRecords(page, ["STN_A", "STN_B"]);
    await setMode(page, "combined");
    await selectAll(page, "STN_A", ["VA", "P"]);
    await selectChannel(page, "STN_B", "F");
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    let state = await plotState(page);
    const ranges = state.groups[0].axes.map((a) => a.range);
    expect(state.fitAll.start).toBeCloseTo(0, 9);
    expect(state.fitAll.end).toBeCloseTo(5, 6);

    // Box Zoom with a diagonal drag: X narrows, no Y axis moves.
    await dragOnPanel(page, 0, 0.25, 0.5, 60);
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport.start).toBeGreaterThan(0.5);
    expect(state.viewport.end).toBeLessThan(3);
    expect(state.groups[0].axes.map((a) => a.range)).toEqual(ranges);

    // Pan: X moves, Y does not.
    await page.locator("#wwErDragModePanBtn").click();
    const before = state.viewport;
    await dragOnPanel(page, 0, 0.6, 0.4, 40);
    await expect.poll(async () => (await plotState(page)).viewport.start).toBeGreaterThan(before.start + 1e-6);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(before.end - before.start, 6);
    expect(state.groups[0].axes.map((a) => a.range)).toEqual(ranges);

    // Zoom Out clamps to Fit All, then reads as unavailable; Zoom In works.
    for (let i = 0; i < 8 && !(await plotState(page)).atFitAll; i++) {
      await page.locator("#wwErZoomOutBtn").click();
      await waitForPlot(page, 3);
    }
    expect((await plotState(page)).atFitAll).toBe(true);
    await expect(page.locator("#wwErZoomOutBtn")).toBeDisabled();
    state = await plotState(page);
    expect(state.viewport.start).toBeCloseTo(state.fitAll.start, 9);
    expect(state.viewport.end).toBeCloseTo(state.fitAll.end, 9);
    await page.locator("#wwErZoomInBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);

    // Double-click = Reset Time View (Fit All + every axis autoscaled).
    await page.locator("#wwErPanels .ww-er-panel").nth(0).locator(".nsewdrag").dblclick();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    state = await plotState(page);
    for (const axis of state.groups[0].axes) expectAxisCovers(state, axis);
    expect(state.groups[0].xRange[0] + state.origin).toBeCloseTo(state.fitAll.start, 9);
  });

  test("Autoscale Y is per axis and ignores traces without samples; an empty axis keeps its title but invents no values", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_SMALL", startClock: "10:00:00.000000", durationS: 2,
      channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 }] });
    await uploadRecord(page, { station: "STN_BIG", startClock: "10:00:01.000000", durationS: 2,
      channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 300, frequencyHz: 50 }] });
    await uploadRecord(page, { station: "STN_F", startClock: "10:00:04.000000", durationS: 1,
      channels: [{ name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 }] });
    await addRecords(page, ["STN_SMALL", "STN_BIG", "STN_F"]);
    await setMode(page, "combined");
    await selectChannel(page, "STN_SMALL", "VA");
    await selectChannel(page, "STN_BIG", "VA");
    await selectChannel(page, "STN_F", "F");
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    let state = await plotState(page);
    let [volts, hertz] = state.groups[0].axes;
    expect([volts.title, hertz.title]).toEqual(["Voltage (V)", "Frequency (Hz)"]);
    expect(span(volts.range)).toBeGreaterThan(600); // both VA traces
    const hertzRange = hertz.range;

    // Only STN_SMALL has samples in view: X navigation keeps both ranges.
    await zoomTo(page, 0.2, 0.8);
    state = await plotState(page);
    expect(state.panels.find((c) => c.label === "STN_BIG · VA").r).toEqual([]);
    expect(state.panels.find((c) => c.label === "STN_F · F").r).toEqual([]);
    expect(span(state.groups[0].axes[0].range)).toBeGreaterThan(600);
    expect(state.groups[0].axes[1].range).toEqual(hertzRange);

    // Autoscale Y: the V axis fits STN_SMALL alone (the empty BIG trace
    // adds nothing); the Hz axis has no sample -- it keeps its title, shows
    // no tick values and waits for data.
    await page.locator("#wwErAutoscaleYBtn").click();
    await waitForAxesScaled(page, ["axis:Frequency|Hz"]);
    state = await plotState(page);
    [volts, hertz] = state.groups[0].axes;
    expect(span(volts.range)).toBeLessThan(250);
    expectAxisCovers(state, volts);
    expect(hertz.title).toBe("Frequency (Hz)");
    expect(hertz.showTickLabels).toBe(false);
    expect(hertz.autorange).toBe(true);
    expect(state.groups[0].note).toBe(""); // the panel still has data
    expect(state.groups[0].axisLegend.map((l) => l.title)).toEqual(["Voltage (V)", "Frequency (Hz)"]);

    // Reset: Fit All, every axis rescaled, the Hz axis shows values again.
    await page.locator("#wwErResetViewBtn").click();
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    state = await plotState(page);
    [volts, hertz] = state.groups[0].axes;
    expect(span(volts.range)).toBeGreaterThan(600);
    expect(hertz.showTickLabels).toBe(true);
    expectAxisCovers(state, hertz);
    expect(state.atFitAll).toBe(true);
  });
});

test.describe("Event Reconstruction Combined View -- cursors and mode switching", () => {
  test("one A and one B line on the combined panel; values stay in the channel tree", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectAll(page, "STN_A", ["VA", "P"]);
    await selectAll(page, "STN_B", ["P", "F"]);
    await waitForPlot(page, 4);
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 0.25); wwErSetCursorTime("b", 0.9); });
    await expect.poll(() => page.evaluate(() => wwErState.plot.panels.flatMap((p) => p.traces).every((t) => t.cursorValues && t.cursorValues.b))).toBe(true);
    const groupedValues = await treeValues(page);
    const readout = () => page.evaluate(() => ["A", "B", "Delta"].map((k) => document.getElementById("wwErCursorReadout" + k).textContent));
    const groupedReadout = await readout();

    await setMode(page, "combined");
    await waitForPlot(page, 4);
    await waitForAxesScaled(page);
    // One overlay, two lines, exactly where Plotly draws the times -- also
    // after the axes' automargins settled.
    await expect(page.locator("#wwErPanels .ww-er-cursor-layer")).toHaveCount(1);
    let [lines] = await cursorLines(page);
    for (const kind of ["a", "b"]) {
      expect(lines[kind].hidden).toBe(false);
      expect(lines[kind].left).toBeCloseTo(lines[kind].plotlyX, 0);
    }
    // Cursor times, tree values and the toolbar readout are unchanged; no
    // per-channel value is on the panel.
    expect(await page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time])).toEqual([0.25, 0.9]);
    expect(await treeValues(page)).toEqual(groupedValues);
    expect(await readout()).toEqual(groupedReadout);
    await expect(page.locator("#wwErPanels .cur-value")).toHaveCount(0);

    // Drag A on the combined panel: one global move, values follow.
    const handle = page.locator('#wwErPanels [data-er-cursor-drag="a"]');
    const box = await handle.boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 40, y, { steps: 4 });
    await page.mouse.move(x + 80, y, { steps: 4 });
    await page.mouse.up();
    await expect.poll(() => page.evaluate(() => wwErState.plot.cursors.a.time)).toBeGreaterThan(0.3);
    [lines] = await cursorLines(page);
    expect(lines.a.left).toBeCloseTo(lines.a.plotlyX, 0);
    expect(await page.evaluate(() => wwErState.plot.cursors.b.time)).toBe(0.9);
    await expect.poll(async () => (await treeValues(page)).map((row) => row[1])).not.toEqual(groupedValues.map((row) => row[1]));
    expect((await plotState(page)).atFitAll).toBe(true); // the drag did not box-zoom
    expect(consoleErrors).toEqual([]);
  });

  test("switching modes keeps records, channels, definition, cursors, X viewport, Fit All and drag mode; reuses data; autoscales Y on entry", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", channels: MIXED });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectAll(page, "STN_A", ["VA", "P"]);
    await selectAll(page, "STN_B", ["VA", "IA"]);
    await waitForPlot(page, 4);
    await zoomTo(page, 0.55, 0.95);
    await page.locator("#wwErDragModePanBtn").click();
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 0.6); wwErSetCursorTime("b", 0.85); });
    const snapshot = () => page.evaluate(() => ({
      definition: JSON.stringify(wwErState.definition),
      selected: JSON.stringify(wwErState.selectedChannels),
      viewport: wwErState.plot.viewport,
      fitAll: wwErState.plot.fitAll,
      atFitAll: wwErState.plot.atFitAll,
      origin: wwErState.plot.origin,
      cursors: JSON.stringify(wwErState.plot.cursors),
      dragMode: wwErState.dragMode,
      keys: wwErState.plot.panels.flatMap((p) => p.traces).map((t) => t.key),
    }));
    const before = await snapshot();
    const requests = [];
    page.on("request", (r) => { if (r.url().includes("/waveform")) requests.push(r.url()); });

    await setMode(page, "combined");
    await waitForPlot(page, 4);
    await waitForAxesScaled(page);
    expect(await snapshot()).toEqual(before);
    let state = await plotState(page);
    expect(state.groups).toHaveLength(1);
    // Every axis scaled to its traces' visible data on entry.
    for (const axis of state.groups[0].axes) {
      expect(axis.autorange).toBe(false);
      expectAxisCovers(state, axis);
    }
    expect(state.panels.every((c) => c.dragmode === "pan")).toBe(true);
    expect(state.groups[0].xRange[0] + state.origin).toBeCloseTo(0.55, 9);
    expect(state.groups[0].xRange[1] + state.origin).toBeCloseTo(0.95, 9);

    await setMode(page, "grouped");
    await waitForPlot(page, 4);
    await waitForAxesScaled(page);
    expect(await snapshot()).toEqual(before);
    state = await plotState(page);
    expect(state.groups.map((g) => g.title)).toEqual(["Voltage (V)", "Current (A)", "Active Power (MW)"]);
    for (const group of state.groups) expect(group.yAutorange).toBe(false);
    // Full-resolution data was reused both ways: nothing refetched.
    expect(requests).toEqual([]);
    // Switching to the active mode is a no-op.
    await page.locator("#wwErViewGroupedBtn").click();
    expect(await snapshot()).toEqual(before);
  });
});

test.describe("Event Reconstruction Combined View -- failures, fetching and isolation", () => {
  test("a failed trace is named on its chip and in the panel; its axis stays", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.000000", channels: MIXED });
    const sourceB = await sourceIdFor(page, "STN_B");
    await page.route(`**/sources/${sourceB}/waveform**`, (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "internal_error", message: "boom" } }) }));
    await addRecords(page, ["STN_A", "STN_B"]);
    await setMode(page, "combined");
    await selectChannel(page, "STN_A", "VA");
    await selectAll(page, "STN_B", ["VA", "P"]);
    await waitForPlot(page, 3);
    await waitForAxesScaled(page, ["axis:Active Power|MW"]);
    const state = await plotState(page);
    const panel = state.groups[0];
    expect(panel.axes.map((a) => a.title)).toEqual(["Voltage (V)", "Active Power (MW)"]);
    expect(panel.axes[1].showTickLabels).toBe(false); // no data -> no invented values
    expect(panel.error).toBe("STN_B · VA: Something went wrong on our end. Please try again.\nSTN_B · P: Something went wrong on our end. Please try again.");
    await expect(page.locator(".ww-er-legend-axis", { hasText: "Active Power (MW)" }).locator(".ww-legend-item")).toContainText("not loaded");
    expect(state.panels.find((c) => c.label === "STN_A · VA").r.length).toBe(1001);
    expectAxisCovers(state, panel.axes[0]);
  });

  test("the point budget comes from the combined panel's plot width; valid data is reused", async ({ page }) => {
    // Wide enough that both modes' budgets are above the shared minimum.
    await page.setViewportSize({ width: 2400, height: 1000 });
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_LONG", startClock: "10:00:00.000000", rateHz: 5000, durationS: 4, channels: MIXED.slice(0, 4) });
    await addRecords(page, ["STN_LONG"]);
    await selectAll(page, "STN_LONG", ["VA", "IA", "P"]);
    await waitForPlot(page, 3);
    const budgets = [];
    page.on("request", (r) => {
      if (r.url().includes("/waveform")) budgets.push(Number(new URL(r.url()).searchParams.get("point_budget")));
    });
    const expectedBudget = () => page.evaluate(() => wwPointBudgetForPlotWidth(wwPlotWidthForChart(wwErState.plot.panels[0].chartEl)));

    // Grouped -> Combined: the combined plot is narrower; the envelopes
    // fetched for the wider grouped panels still serve it.
    await setMode(page, "combined");
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    expect(budgets).toEqual([]);
    // New range: one request per trace, with the combined panel's budget.
    await zoomTo(page, 1, 3);
    await expect.poll(() => budgets.length).toBe(3);
    const combinedBudget = await expectedBudget();
    expect(budgets).toEqual([combinedBudget, combinedBudget, combinedBudget]);
    expect((await plotState(page)).panels.every((c) => c.representation === "min_max_envelope")).toBe(true);
    // Back to Grouped: wider panels need a larger envelope -- refetched.
    budgets.length = 0;
    await setMode(page, "grouped");
    await waitForPlot(page, 3);
    await expect.poll(() => budgets.length).toBe(3);
    const groupedBudget = await expectedBudget();
    expect(groupedBudget).toBeGreaterThan(combinedBudget);
    expect(budgets).toEqual([groupedBudget, groupedBudget, groupedBudget]);
  });

  test("the combined view never changes Waveform's layout, panels or state", async ({ page }) => {
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
      layouts: ww.panels.map((p) => JSON.stringify(Object.keys(p.chartEl && p.chartEl.layout ? p.chartEl.layout : {}).filter((k) => k.startsWith("yaxis")).sort())),
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
    await setMode(page, "combined");
    await selectAll(page, "STN_A", ["VA", "P", "F"]);
    await selectAll(page, "STN_B", ["VA", "IA"]);
    await waitForPlot(page, 5);
    await page.locator("#wwErZoomInBtn").click();
    await page.locator("#wwErAutoscaleYBtn").click();
    await page.locator("#wwErCursorModeBtn").click();
    await page.locator("#wwErDragModePanBtn").click();
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("powerwave:theme-change")));
    await page.locator("#wwErResetViewBtn").click();
    await waitForPlot(page, 5);
    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
