// Event Reconstruction individual Y-axis drag zoom (DEC-134): Plotly's
// native drag on one Y axis's own scale -- middle pans that axis, an end
// moves that end, a double-click autoranges it -- changes that axis only.
// A dragged range is the axis's manual range (keyed by display-axis key,
// per view mode), kept through X navigation, Fit Record and channel
// changes until Autoscale Y / Reset. Plot-area Pan (DEC-144: the only
// plot-area mode -- Box Zoom is retired) stays X-only.

const { test, expect } = require("@playwright/test");
const {
  collectConsoleErrors, uploadRecord, memberRow, addRecords, channelRow, selectChannel, waitForPlot, plotState,
  zoomTo, dragOnPanel, waitForSharedAxis,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

async function setup(page, names = ["VA", "P", "F"]) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4, channels: MIXED });
  await addRecords(page, ["STN_A", "STN_B"]);
  for (const name of names) await selectChannel(page, "STN_A", name);
  await waitForPlot(page, names.length);
  await waitForScaled(page);
}

async function waitForScaled(page) {
  await expect.poll(async () => (await plotState(page)).groups.flatMap((g) => g.axes).every((a) => !a.pending)).toBe(true);
}

// Drags one Y axis's own scale: region "nsdrag" (middle), "ndrag" (top
// end) or "sdrag" (bottom end) of Plotly subplot "xy", "xy2", ...
async function dragAxis(page, panelIndex, region, subplot, dy) {
  const target = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator(`.draglayer .${region}[data-subplot="${subplot}"]`);
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + dy / 2, { steps: 5 });
  await page.mouse.move(x, y + dy, { steps: 5 });
  await page.mouse.up();
}

async function dblclickAxis(page, panelIndex, subplot) {
  const target = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator(`.draglayer .nsdrag[data-subplot="${subplot}"]`);
  const box = await target.boundingBox();
  await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2);
}

// Everything X: viewport, origin, every panel's X range/ticks and every
// trace's plotted x.
const xState = (state) => JSON.stringify({
  viewport: state.viewport, origin: state.origin,
  panels: state.panels.map((c) => [c.key, c.xRange, c.tickvals, c.x]),
});
const cursorTimes = (page) => page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time]);
const axisByTitle = (state, title) => state.groups.flatMap((g) => g.axes).find((a) => a.title === title);
const groupByTitle = (state, title) => state.groups.find((g) => g.title === title);

test.describe("Event Reconstruction Y-axis drag zoom -- Grouped", () => {
  test("dragging one panel's Y scale changes only that panel's Y; X, other panels and cursors stay", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await page.locator("#wwErCursorModeBtn").click();
    let state = await plotState(page);
    const before = { x: xState(state), ranges: state.groups.map((g) => g.yRange), cursors: await cursorTimes(page) };
    expect(state.groups.map((g) => g.title)).toEqual(["Voltage (V)", "Active Power (MW)", "Frequency (Hz)"]);

    // Middle of the Voltage scale, dragged down: Plotly pans that axis.
    await dragAxis(page, 0, "nsdrag", "xy", 40);
    await expect.poll(async () => groupByTitle(await plotState(page), "Voltage (V)").axes[0].manual).toBe(true);
    state = await plotState(page);
    const panned = state.groups[0].yRange;
    expect(panned).not.toEqual(before.ranges[0]);
    expect(panned[1] - panned[0]).toBeCloseTo(before.ranges[0][1] - before.ranges[0][0], 6); // same span
    expect(panned[0]).toBeGreaterThan(before.ranges[0][0]); // dragged down -> higher values come into view
    expect(state.groups.slice(1).map((g) => g.yRange)).toEqual(before.ranges.slice(1));
    expect(state.groups.slice(1).every((g) => g.axes.every((a) => !a.manual))).toBe(true);
    expect(xState(state)).toBe(before.x);
    expect(await cursorTimes(page)).toEqual(before.cursors);

    // Top end dragged up (away from the centre): zoom in at the top.
    await dragAxis(page, 0, "ndrag", "xy", -30);
    await expect.poll(async () => (await plotState(page)).groups[0].yRange[1]).toBeLessThan(panned[1]);
    state = await plotState(page);
    const zoomed = state.groups[0].yRange;
    expect(zoomed[0]).toBeCloseTo(panned[0], 9); // the other end stays
    expect(state.groups.slice(1).map((g) => g.yRange)).toEqual(before.ranges.slice(1));
    expect(xState(state)).toBe(before.x);
    // Bottom end dragged up (towards the centre): zoom out at the bottom.
    await dragAxis(page, 0, "sdrag", "xy", -30);
    await expect.poll(async () => (await plotState(page)).groups[0].yRange[0]).toBeLessThan(zoomed[0]);
    expect((await plotState(page)).groups[0].yRange[1]).toBeCloseTo(zoomed[1], 9);
    expect(consoleErrors).toEqual([]);
  });

  test("a manual range survives Pan, Zoom In/Out and Fit Record; Autoscale Y and Reset clear it", async ({ page }) => {
    // DEC-144: Box Zoom is retired -- every plot-area drag is Pan (no
    // mode toggle to click). At Fit All itself there is no room to pan
    // (the window already spans the full bounds), so zoomTo() first
    // reaches a narrower window to pan within.
    await setup(page);
    await zoomTo(page, 1, 4);
    await dragAxis(page, 0, "ndrag", "xy", -40);
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(true);
    const manual = (await plotState(page)).groups[0].yRange;
    const others = (await plotState(page)).groups.slice(1).map((g) => g.yRange);
    const keeps = async (what) => {
      await waitForSharedAxis(page);
      await waitForPlot(page, 3);
      const state = await plotState(page);
      expect(state.groups[0].yRange, what).toEqual(manual);
      expect(state.groups[0].axes[0].manual, what).toBe(true);
      expect(state.groups.slice(1).map((g) => g.yRange), what).toEqual(others);
    };
    await dragOnPanel(page, 1, 0.2, 0.5, 60); // diagonal Pan
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);
    await keeps("pan");
    await dragOnPanel(page, 2, 0.6, 0.4, 40); // diagonal Pan, another panel
    await keeps("pan again");
    await page.locator("#wwErZoomInBtn").click();
    await keeps("zoom in");
    await page.locator("#wwErZoomOutBtn").click();
    await keeps("zoom out");
    await memberRow(page, "STN_A").locator("[data-er-activate-record]").click();
    await page.locator("#wwErFitRecordBtn").click();
    await keeps("fit record");

    // Autoscale Y: every axis automatic again, scaled to its data.
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(false);
    await waitForScaled(page);
    let state = await plotState(page);
    const values = state.panels.filter((c) => c.panelIndex === 0).flatMap((c) => c.values).filter(Number.isFinite);
    expect(state.groups[0].yRange[1]).toBeGreaterThanOrEqual(Math.max(...values));
    // After Autoscale Y, X navigation keeps the resulting range.
    const auto = state.groups[0].yRange;
    await zoomTo(page, 1.2, 1.6);
    expect((await plotState(page)).groups[0].yRange).toEqual(auto);

    // Reset: Fit All and every manual range cleared.
    await dragAxis(page, 1, "nsdrag", "xy", 30);
    await expect.poll(async () => (await plotState(page)).groups[1].axes[0].manual).toBe(true);
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    await waitForScaled(page);
    state = await plotState(page);
    expect(state.groups.flatMap((g) => g.axes).some((a) => a.manual)).toBe(false);
  });

  test("a double-click on one Y scale autoscales that axis only", async ({ page }) => {
    await setup(page);
    await dragAxis(page, 0, "ndrag", "xy", -40);
    await dragAxis(page, 1, "ndrag", "xy", -40);
    await expect.poll(async () => (await plotState(page)).groups.slice(0, 2).map((g) => g.axes[0].manual)).toEqual([true, true]);
    const power = (await plotState(page)).groups[1].yRange;
    const x = xState(await plotState(page));
    await dblclickAxis(page, 0, "xy");
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(false);
    await waitForScaled(page);
    const state = await plotState(page);
    const values = state.panels.filter((c) => c.panelIndex === 0).flatMap((c) => c.values).filter(Number.isFinite);
    expect(state.groups[0].yRange[1]).toBeGreaterThanOrEqual(Math.max(...values));
    expect(state.groups[1].yRange).toEqual(power);
    expect(state.groups[1].axes[0].manual).toBe(true);
    expect(xState(state)).toBe(x);
    expect(state.atFitAll).toBe(true); // not a time Reset
  });
});

test.describe("Event Reconstruction Y-axis drag zoom -- Combined", () => {
  test("dragging one of several Y scales changes only that axis; titles, placement and X stay", async ({ page }) => {
    await setup(page, ["VA", "IA", "P", "F"]);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 4);
    await waitForScaled(page);
    await page.locator("#wwErCursorModeBtn").click();
    let state = await plotState(page);
    const axesBefore = state.groups[0].axes;
    expect(axesBefore.map((a) => [a.title, a.ref, a.side])).toEqual([
      ["Voltage (V)", "y", "left"], ["Current (A)", "y2", "right"], ["Active Power (MW)", "y3", "left"], ["Frequency (Hz)", "y4", "right"],
    ]);
    const x = xState(state);
    const cursors = await cursorTimes(page);
    const check = async (title, what) => {
      const now = (await plotState(page)).groups[0].axes;
      for (const [k, axis] of now.entries()) {
        expect([axis.title, axis.ref, axis.side], what).toEqual([axesBefore[k].title, axesBefore[k].ref, axesBefore[k].side]);
        if (axis.title === title) {
          expect(axis.range, what).not.toEqual(axesBefore[k].range);
          expect(axis.manual, what).toBe(true);
        } else {
          expect(axis.range, what).toEqual(axesBefore[k].range);
        }
      }
      expect(xState(await plotState(page)), what).toBe(x);
      expect(await cursorTimes(page), what).toEqual(cursors);
    };
    // Inner left (y): middle drag.
    await dragAxis(page, 0, "nsdrag", "xy", 40);
    await expect.poll(async () => axisByTitle(await plotState(page), "Voltage (V)").manual).toBe(true);
    await check("Voltage (V)", "inner left");
    // Outer right (y4): top end -- only Frequency moves.
    await page.locator("#wwErAutoscaleYBtn").click();
    await waitForScaled(page);
    await expect.poll(async () => axisByTitle(await plotState(page), "Voltage (V)").range).toEqual(axesBefore[0].range);
    await dragAxis(page, 0, "ndrag", "xy4", -30);
    await expect.poll(async () => axisByTitle(await plotState(page), "Frequency (Hz)").manual).toBe(true);
    await check("Frequency (Hz)", "outer right");
    // Outer left (y3): double-click autoranges Active Power only.
    await dragAxis(page, 0, "sdrag", "xy3", -30);
    await expect.poll(async () => axisByTitle(await plotState(page), "Active Power (MW)").manual).toBe(true);
    const frequency = axisByTitle(await plotState(page), "Frequency (Hz)").range;
    await dblclickAxis(page, 0, "xy3");
    await expect.poll(async () => axisByTitle(await plotState(page), "Active Power (MW)").manual).toBe(false);
    await waitForScaled(page);
    expect(axisByTitle(await plotState(page), "Active Power (MW)").range).toEqual(axesBefore[2].range);
    expect(axisByTitle(await plotState(page), "Frequency (Hz)").range).toEqual(frequency);
    expect(xState(await plotState(page))).toBe(x);
  });

  test("Y state is per view mode: never copied across, restored on return", async ({ page }) => {
    await setup(page);
    await dragAxis(page, 0, "ndrag", "xy", -40);
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(true);
    const grouped = (await plotState(page)).groups[0].yRange;

    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    await waitForScaled(page);
    let voltage = axisByTitle(await plotState(page), "Voltage (V)");
    expect(voltage.manual).toBe(false); // not copied from Grouped
    expect(voltage.range).not.toEqual(grouped);
    await dragAxis(page, 0, "nsdrag", "xy", 50);
    await expect.poll(async () => axisByTitle(await plotState(page), "Voltage (V)").manual).toBe(true);
    const combined = axisByTitle(await plotState(page), "Voltage (V)").range;

    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    let state = await plotState(page);
    expect(state.groups[0].yRange).toEqual(grouped);
    expect(state.groups[0].axes[0].manual).toBe(true);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    voltage = axisByTitle(await plotState(page), "Voltage (V)");
    expect([voltage.range, voltage.manual]).toEqual([combined, true]);
    // Reset clears both modes' manual ranges.
    await page.locator("#wwErResetViewBtn").click();
    await waitForScaled(page);
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    await waitForScaled(page);
    state = await plotState(page);
    expect(state.groups.flatMap((g) => g.axes).some((a) => a.manual)).toBe(false);
  });
});

test.describe("Event Reconstruction Y-axis drag zoom -- channels and isolation", () => {
  test("a channel joining a manual axis keeps the range; a removed axis takes its state along", async ({ page }) => {
    await setup(page);
    await dragAxis(page, 0, "ndrag", "xy", -40);
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(true);
    const manual = (await plotState(page)).groups[0].yRange;
    // STN_B · VA joins Voltage (V): no automatic rescale.
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 4);
    let state = await plotState(page);
    expect(state.groups[0].traceKeys).toHaveLength(2);
    expect([state.groups[0].yRange, state.groups[0].axes[0].manual]).toEqual([manual, true]);
    // Every Voltage channel deselected: the axis and its state go.
    for (const station of ["STN_A", "STN_B"]) {
      const row = await channelRow(page, station, "VA");
      await row.click();
      await expect(row).toHaveAttribute("aria-pressed", "false");
    }
    await waitForPlot(page, 2);
    expect((await plotState(page)).groups.map((g) => g.title)).toEqual(["Active Power (MW)", "Frequency (Hz)"]);
    // (Y state per view mode and unit mode, DEC-138.)
    expect(await page.evaluate(() => wwErAxisStore("grouped", "engineering").has("axis:Voltage|V"))).toBe(false);
    // Recreated: autoscaled normally.
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 3);
    await waitForScaled(page);
    state = await plotState(page);
    expect(state.groups[0].axes[0].manual).toBe(false);
    expect(state.groups[0].yRange).not.toEqual(manual);
  });

  test("Y-axis drag zoom never changes Waveform's state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    const waveform = () => page.evaluate(() => ({
      layoutMode: ww.layoutMode,
      displayed: Array.from(ww.displayed.keys()).sort(),
      panels: ww.panels.map((p) => p.groupKey + ":" + JSON.stringify(p.chartEl && p.chartEl.layout && p.chartEl.layout.yaxis && p.chartEl.layout.yaxis.range)),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
      presentation: JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())),
    }));
    await page.waitForTimeout(500);
    const before = await waveform();
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "P");
    await waitForPlot(page, 2);
    await waitForScaled(page);
    await dragAxis(page, 0, "ndrag", "xy", -40);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 2);
    await dragAxis(page, 0, "nsdrag", "xy2", 30);
    await dblclickAxis(page, 0, "xy");
    await page.waitForTimeout(300);
    expect(await waveform()).toEqual(before);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
