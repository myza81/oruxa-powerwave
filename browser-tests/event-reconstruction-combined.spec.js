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
    // Every axis draggable on its own scale (DEC-134); every axis scaled
    // to its own data.
    for (const axis of panel.axes) {
      expect(axis.fixedRange).toBe(false);
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

// Axis-title regression (owner UAT, 2026-10-02): a channel whose quantity
// is unknown (no unit, Undefined type -- as BEN unit code 63 was before it
// was validated) had a Combined axis titled "Undefined". Every axis must be
// titled from its own display-axis metadata, carry its own traces
// (data[k].yaxis), and be scaled to those traces; an unknown-quantity axis
// with one channel is named after it, so several stay distinguishable.
const TITLED = [
  { name: "VKV", unit: "kV", phase: "A", amplitude: 300, frequencyHz: 50 },
  { name: "IKA", unit: "kA", phase: "A", amplitude: 2, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 350, frequencyHz: 0.5 },
  { name: "Q", unit: "Mvar", amplitude: 40, frequencyHz: 0.5 },
  { name: "S", unit: "MVA", amplitude: 400, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
  { name: "CHANNEL X", unit: "", amplitude: 60, frequencyHz: 0.5 },
  { name: "CHANNEL Y", unit: "", amplitude: 150, frequencyHz: 0.5 },
  { name: "ANGLE X", unit: "deg", amplitude: 90, frequencyHz: 0.5 },
];
// The expected title of each channel's axis, from its quantity and unit.
const EXPECTED_TITLE = {
  "VKV": "Voltage (kV)", "-VKV": "Voltage (kV)", "IKA": "Current (kA)", "P": "Active Power (MW)",
  "Q": "Reactive Power (Mvar)", "S": "Apparent Power (MVA)", "F": "Frequency (Hz)",
  "CHANNEL X": "Unknown quantity — CHANNEL X",
  "CHANNEL Y": "Unknown quantity — CHANNEL Y",
  "ANGLE X": "Unknown quantity (deg) — ANGLE X",
};

test.describe("Event Reconstruction Combined View -- axis titles", () => {
  test("title, Plotly axis, scale and traces all refer to the same display axis; unknown quantities are named after their channel", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: TITLED });
    const sourceA = await sourceIdFor(page, "STN_A");
    const calc = await (await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VKV", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VKV" }], parameters: {} },
    })).json();
    // The backend metadata: an unclassified channel has a deliberate title
    // quantity -- never the "Undefined" sentinel; without a unit it shares
    // no axis.
    const meta = Object.fromEntries((await api(page, `/sources/${sourceA}/channels`)).analog_channels
      .map((c) => [c.name, [c.engineering_type, c.display_axis_key, c.display_axis_quantity, c.display_axis_unit]]));
    expect(meta["CHANNEL X"]).toEqual(["Undefined", null, "Unknown quantity", ""]);
    expect(meta["CHANNEL Y"]).toEqual(["Undefined", null, "Unknown quantity", ""]);
    expect(meta["ANGLE X"]).toEqual(["Undefined", "Undefined|raw:deg", "Unknown quantity", "deg"]);
    expect(meta.Q).toEqual(["Power", "Reactive Power|Mvar", "Reactive Power", "Mvar"]);
    expect([calc.display_axis_key, calc.display_axis_quantity]).toEqual(["Voltage|kV", "Voltage"]);

    await addRecords(page, ["STN_A"]);
    await selectAll(page, "STN_A", [...TITLED.map((c) => c.name), "-VKV"]);
    await waitForPlot(page, 10);
    await waitForAxesScaled(page);
    const grouped = await plotState(page);
    const groupedTitles = grouped.groups.map((g) => g.title);
    expect(groupedTitles).toEqual([
      "Voltage (kV)", "Current (kA)", "Active Power (MW)", "Reactive Power (Mvar)", "Apparent Power (MVA)", "Frequency (Hz)",
      "Unknown quantity — CHANNEL X", "Unknown quantity — CHANNEL Y", "Unknown quantity (deg) — ANGLE X",
    ]);
    // Two unknown channels: two axes, two different titles.
    expect(new Set(groupedTitles).size).toBe(groupedTitles.length);
    for (const title of groupedTitles) expect(title.toLowerCase()).not.toContain("undefined");
    // Grouped: every channel sits in the panel its metadata names.
    for (const channel of grouped.panels) expect(channel.panelTitle).toBe(EXPECTED_TITLE[channel.channelName]);

    await setMode(page, "combined");
    await waitForPlot(page, 10);
    await waitForAxesScaled(page);
    const state = await plotState(page);
    const panel = state.groups[0];
    // Grouped panel title == Combined axis title == legend heading, per group.
    expect(panel.axes.map((a) => a.title)).toEqual(groupedTitles);
    expect(panel.axisLegend.map((l) => l.title)).toEqual(groupedTitles);
    expect(panel.axes.map((a) => a.key)).toEqual(grouped.groups.map((g) => g.key));
    // Left/right alternation does not shift a title to a neighbour's axis.
    expect(panel.axes.map((a) => a.side)).toEqual(["left", "right", "left", "right", "left", "right", "left", "right", "left"]);
    const byRef = Object.fromEntries(panel.axes.map((a) => [a.ref, a]));
    for (const channel of state.panels) {
      // Plotly's own trace -> axis reference (data[k].yaxis) lands on the
      // axis titled for this channel's quantity and unit...
      const axis = byRef[channel.traceYAxis];
      expect(axis.title).toBe(EXPECTED_TITLE[channel.channelName]);
      expect(axis.traceKeys).toContain(channel.key);
      // ...and that axis is scaled to its own traces, not a neighbour's.
      const values = state.panels.filter((c) => c.traceYAxis === channel.traceYAxis).flatMap((c) => c.values);
      const dataSpan = Math.max(...values) - Math.min(...values);
      expect(axis.range[0]).toBeLessThanOrEqual(Math.min(...values));
      expect(axis.range[1]).toBeGreaterThanOrEqual(Math.max(...values));
      expect(span(axis.range)).toBeLessThan(1.25 * dataSpan);
    }
    // The calculated channel joins the native Voltage (kV) axis.
    const voltage = panel.axes.find((a) => a.title === "Voltage (kV)");
    expect(voltage.traceKeys).toHaveLength(2);
    expect(state.panels.find((c) => c.channelName === "-VKV").traceYAxis).toBe(voltage.ref);
    // Each unclassified channel has an axis of its own, never merged.
    for (const name of ["CHANNEL X", "CHANNEL Y", "ANGLE X"]) {
      expect(panel.axes.find((a) => a.title === EXPECTED_TITLE[name]).traceKeys)
        .toEqual([state.panels.find((c) => c.channelName === name).key]);
    }

    // The name is Waveform's: a rename there renames the axis (display only;
    // the axis and its trace are unchanged).
    await page.evaluate((sourceId) => {
      ww.channelPresentationOverrides.set(wwChannelKey(sourceId, "CHANNEL X"), { displayName: "GEN X MVAR" });
      wwErRenderPlot();
    }, sourceA);
    await expect.poll(async () => (await plotState(page)).groups[0].axes.map((a) => a.title))
      .toContain("Unknown quantity — GEN X MVAR");
    const renamed = (await plotState(page)).groups[0];
    expect(renamed.axisLegend.map((l) => l.title)).toContain("Unknown quantity — GEN X MVAR");
    expect(renamed.axes.map((a) => a.key)).toEqual(panel.axes.map((a) => a.key));
    await setMode(page, "grouped");
    expect((await plotState(page)).groups.map((g) => g.title)).toContain("Unknown quantity — GEN X MVAR");
    expect(consoleErrors).toEqual([]);
  });

  test("an unknown quantity with a unit shares one axis by its exact unit; a shared axis is not named after one channel", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: [
      { name: "ANGLE X", unit: "deg", amplitude: 90, frequencyHz: 0.5 },
      { name: "ANGLE Y", unit: "deg", amplitude: 45, frequencyHz: 0.5 },
      { name: "CHANNEL X", unit: "", amplitude: 60, frequencyHz: 0.5 },
    ] });
    await addRecords(page, ["STN_A"]);
    await setMode(page, "combined");
    await selectAll(page, "STN_A", ["ANGLE X", "ANGLE Y", "CHANNEL X"]);
    await waitForPlot(page, 3);
    await waitForAxesScaled(page);
    const panel = (await plotState(page)).groups[0];
    expect(panel.axes.map((a) => a.title)).toEqual(["Unknown quantity (deg)", "Unknown quantity — CHANNEL X"]);
    expect(panel.axes[0].traceKeys).toHaveLength(2);
    expect(panel.axisLegend[0].chips).toEqual(["STN_A · ANGLE X", "STN_A · ANGLE Y"]);
    // One deg channel left: the axis is named after it again.
    const row = await channelRow(page, "STN_A", "ANGLE Y");
    await row.click();
    await waitForPlot(page, 2);
    expect((await plotState(page)).groups[0].axes.map((a) => a.title)).toEqual(["Unknown quantity (deg) — ANGLE X", "Unknown quantity — CHANNEL X"]);
  });
});

test.describe("Event Reconstruction typography", () => {
  test("every Y-axis title is 11 px in Grouped and Combined; ER legend chips are 0.65rem; tick labels unchanged", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", channels: MIXED });
    await addRecords(page, ["STN_A"]);
    await selectAll(page, "STN_A", ["VA", "IA", "P", "F"]);
    await waitForPlot(page, 4);
    const typography = () => page.evaluate(() => {
      const root = parseFloat(getComputedStyle(document.documentElement).fontSize);
      return {
        root,
        titles: wwErState.plot.panels.flatMap((p) => p.axes.map((a) => {
          const full = p.chartEl._fullLayout[a.placement.layoutKey];
          const rendered = p.chartEl.querySelector("." + a.placement.ref + "title");
          return {
            text: full.title.text,
            size: full.title.font.size,
            rendered: rendered ? rendered.textContent : null,
            renderedSize: rendered ? parseFloat(rendered.style.fontSize) : null,
            tickSize: full.tickfont.size,
          };
        })),
        chips: Array.from(document.querySelectorAll("#wwErPanels .ww-legend-item")).map((el) => parseFloat(getComputedStyle(el).fontSize)),
      };
    });
    // Grouped: each panel's unit title, now rendered, at 11 px.
    let t = await typography();
    expect(t.titles.map((x) => [x.text, x.rendered, x.size, x.renderedSize])).toEqual([
      ["V", "V", 11, 11], ["A", "A", 11, 11], ["MW", "MW", 11, 11], ["Hz", "Hz", 11, 11],
    ]);
    expect(t.titles.every((x) => x.tickSize === 11)).toBe(true); // the panel font, unchanged
    expect(t.chips.every((size) => Math.abs(size - 0.65 * t.root) < 0.01)).toBe(true);
    // Combined: every axis title at 11 px.
    await setMode(page, "combined");
    await waitForPlot(page, 4);
    t = await typography();
    expect(t.titles.map((x) => [x.rendered, x.size, x.renderedSize])).toEqual([
      ["Voltage (V)", 11, 11], ["Current (A)", 11, 11], ["Active Power (MW)", 11, 11], ["Frequency (Hz)", 11, 11],
    ]);
    expect(t.chips.every((size) => Math.abs(size - 0.65 * t.root) < 0.01)).toBe(true);
  });
});
