// Event Reconstruction drag-to-resize panels (owner ticket): a vertical
// drag handle at each panel's own bottom edge, in both Grouped and
// Combined mode. Reuses the shared `.ww-resize-handle` markup/CSS
// (frontend/index.html's own `wwPanelMarkupHtml()`) Waveform's own
// wwWireResizeHandle() already proved -- previously always stripped out
// at Event Reconstruction panel creation ("Panel-height dragging is
// still not offered in either mode"), now kept and wired through an
// EXACT structural mirror of that same mechanism
// (wwErSetPanelHeightImmediate/wwErResizePanelPlot/wwErSetPanelHeight/
// wwErWireResizeHandle), adapted only for this page's own panel.key/
// wwErState.plot.panelHeights identity.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, addRecords, selectChannel, waitForPlot, plotState,
  clickPanelHeader, clickLegendAxis,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

// Same pattern as event-reconstruction-active-yaxis.spec.js's own
// configureVoltageGroup() -- a confirmed voltage Measurement Group so VA
// resolves "configured" in Per Unit (not "PU unavailable", which would
// leave zero panels to check a height against).
const wsUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${path}`;
async function configureVoltageGroup(page, station, channel) {
  const sourceId = await sourceIdFor(page, station);
  const groupsUrl = await wsUrl(page, `/sources/${sourceId}/measurement-groups`);
  for (const group of await (await page.request.get(groupsUrl)).json()) await page.request.delete(`${groupsUrl}/${group.id}`);
  const postResp = await page.request.post(groupsUrl, {
    data: { kind: "voltage", display_name: station + " voltage", status: "confirmed", channel_refs: [{ kind: "source", source_id: sourceId, channel_name: channel }] },
  });
  expect(postResp.ok()).toBe(true);
  const group = await postResp.json();
  expect((await page.request.put(`${groupsUrl}/${group.id}/voltage-config`, { data: { nominal_voltage_ll_kv: 275 } })).ok()).toBe(true);
}

async function setup(page, names = ["VA", "P", "F"]) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
  await addRecords(page, ["STN_A"]);
  for (const name of names) await selectChannel(page, "STN_A", name);
  await waitForPlot(page, names.length);
  await waitForScaled(page);
}

async function waitForScaled(page) {
  await expect.poll(async () => (await plotState(page)).groups.flatMap((g) => g.axes).every((a) => !a.pending)).toBe(true);
}

async function dragResizeHandle(page, panelIndex, dy) {
  const handle = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator(".ww-resize-handle");
  await handle.scrollIntoViewIfNeeded();
  const box = await handle.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + dy / 2, { steps: 5 });
  await page.mouse.move(x, y + dy, { steps: 5 });
  await page.mouse.up();
}

test.describe("Event Reconstruction panel resize -- Grouped", () => {
  test("each panel carries its own resize handle, discoverable but subtle", async ({ page }) => {
    await setup(page);
    const handles = page.locator("#wwErPanels .ww-er-panel .ww-resize-handle");
    await expect(handles).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      await expect(handles.nth(i)).toHaveAttribute("role", "separator");
      await expect(handles.nth(i)).toHaveAttribute("aria-orientation", "horizontal");
      const ariaLabel = await handles.nth(i).getAttribute("aria-label");
      expect(ariaLabel).toMatch(/^Resize .+ panel height$/);
      const cursor = await handles.nth(i).evaluate((el) => getComputedStyle(el).cursor);
      expect(cursor).toBe("ns-resize");
    }
  });

  test("dragging down increases height; dragging up decreases it", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    const before = (await plotState(page)).groups[0].height;

    await dragResizeHandle(page, 0, 80);
    const taller = (await plotState(page)).groups[0].height;
    expect(taller).toBeGreaterThan(before + 60);

    await dragResizeHandle(page, 0, -40);
    const shorter = (await plotState(page)).groups[0].height;
    expect(shorter).toBeLessThan(taller);
    expect(shorter).toBeGreaterThan(before); // net still taller than the start
    expect(consoleErrors).toEqual([]);
  });

  test("minimum height is enforced -- a huge upward drag cannot collapse the panel", async ({ page }) => {
    await setup(page);
    await dragResizeHandle(page, 0, -2000);
    const height = (await plotState(page)).groups[0].height;
    expect(height).toBeGreaterThanOrEqual(100); // WW_MIN_PANEL_HEIGHT
  });

  test("a sensible maximum exists but is not restrictively small -- a large downward drag reaches a meaningfully taller panel", async ({ page }) => {
    await setup(page);
    await dragResizeHandle(page, 0, 2000);
    const height = (await plotState(page)).groups[0].height;
    expect(height).toBeGreaterThan(300); // meaningfully taller than the 180 default
    expect(height).toBeLessThanOrEqual(600); // WW_MAX_PANEL_HEIGHT
  });

  test("resizing one panel never resizes the other panels", async ({ page }) => {
    await setup(page); // Voltage, Active Power, Frequency
    const before = await plotState(page);
    const [voltageBefore, powerBefore, freqBefore] = before.groups.map((g) => g.height);

    await dragResizeHandle(page, 1, 90); // resize Active Power only
    const after = await plotState(page);
    expect(after.groups[0].height).toBeCloseTo(voltageBefore, 0);
    expect(after.groups[1].height).toBeGreaterThan(powerBefore + 60);
    expect(after.groups[2].height).toBeCloseTo(freqBefore, 0);
  });

  test("the Plotly chart itself reflows to fill the resized container", async ({ page }) => {
    await setup(page);
    const plotWidthBefore = (await plotState(page)).groups[0].plotWidth;
    await dragResizeHandle(page, 0, 120);
    await page.waitForTimeout(100); // allow the rAF-coalesced Plotly.Plots.resize to flush
    const state = await plotState(page);
    // The chart's own rendered SVG height tracks the container -- compare
    // Plotly's own _fullLayout height to the container's own height.
    const fullLayoutHeight = await page.evaluate(() => wwErState.plot.panels[0].chartEl._fullLayout.height);
    expect(fullLayoutHeight).toBeGreaterThan(250); // grew from the 180 default
    // Width is untouched by a vertical-only resize.
    expect(state.groups[0].plotWidth).toBeCloseTo(plotWidthBefore, 0);
  });

  test("zoom (X viewport and per-axis Y range) survives a resize", async ({ page }) => {
    await setup(page);
    await page.locator("#wwErZoomInBtn").click();
    await page.locator("#wwErZoomInBtn").click();
    const before = await plotState(page);

    await dragResizeHandle(page, 0, 70);
    const after = await plotState(page);
    expect(after.viewport).toEqual(before.viewport);
    expect(after.groups[0].yRange).toEqual(before.groups[0].yRange);
    expect(after.groups[1].yRange).toEqual(before.groups[1].yRange);
  });

  test("A/B cursor state survives a resize", async ({ page }) => {
    await setup(page);
    await page.locator("#wwErCursorModeBtn").click();
    await expect(page.locator("#wwErCursorModeBtn")).toHaveAttribute("aria-pressed", "true");
    const cursorsBefore = await page.evaluate(() => ({ a: wwErState.plot.cursors.a.time, b: wwErState.plot.cursors.b.time }));

    await dragResizeHandle(page, 1, -50);
    await expect(page.locator("#wwErCursorModeBtn")).toHaveAttribute("aria-pressed", "true");
    const cursorsAfter = await page.evaluate(() => ({ a: wwErState.plot.cursors.a.time, b: wwErState.plot.cursors.b.time }));
    expect(cursorsAfter).toEqual(cursorsBefore);
  });

  test("active Y-axis selection and channel membership survive a resize", async ({ page }) => {
    await setup(page);
    await clickPanelHeader(page, 1);
    const activeBefore = (await plotState(page)).activeAxisKey;
    const traceKeysBefore = (await plotState(page)).groups.map((g) => g.traceKeys);

    await dragResizeHandle(page, 1, 60);
    const state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeBefore);
    expect(state.groups.map((g) => g.traceKeys)).toEqual(traceKeysBefore);
  });

  test("switching Unit Mode does not reset a resized panel's height", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await configureVoltageGroup(page, "STN_A", "VA"); // PU-configured, so Per Unit still plots this panel
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await waitForScaled(page);
    await dragResizeHandle(page, 0, 90);
    const resized = (await plotState(page)).groups[0].height;

    await page.locator("#wwErUnitPerUnitBtn").click();
    await expect.poll(async () => (await plotState(page)).groups.length).toBe(1);
    const afterPu = (await plotState(page)).groups[0].height;
    expect(afterPu).toBeCloseTo(resized, 0);

    await page.locator("#wwErUnitEngineeringBtn").click();
    await expect.poll(async () => (await plotState(page)).groups.length).toBe(1);
    const afterEng = (await plotState(page)).groups[0].height;
    expect(afterEng).toBeCloseTo(resized, 0);
  });
});

test.describe("Event Reconstruction panel resize -- Combined", () => {
  async function setupCombined(page, names = ["VA", "IA", "P", "F"]) {
    await setup(page, names);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, names.length);
    await waitForScaled(page);
  }

  test("the combined panel carries the same resize handle, same interaction language as Grouped", async ({ page }) => {
    await setupCombined(page);
    const handle = page.locator("#wwErPanels .ww-er-panel .ww-resize-handle");
    await expect(handle).toHaveCount(1);
    await expect(handle).toHaveAttribute("role", "separator");
    const cursor = await handle.evaluate((el) => getComputedStyle(el).cursor);
    expect(cursor).toBe("ns-resize");
  });

  test("dragging resizes the combined panel while preserving every plotted channel, shared X and current Y configuration", async ({ page }) => {
    await setupCombined(page);
    const before = await plotState(page);
    const axesBefore = before.groups[0].axes.map((a) => [a.title, a.range]);

    await dragResizeHandle(page, 0, 100);
    const after = await plotState(page);
    expect(after.groups[0].height).toBeGreaterThan(before.groups[0].height + 60);
    expect(after.groups[0].traceKeys).toEqual(before.groups[0].traceKeys); // every channel preserved
    expect(after.viewport).toEqual(before.viewport); // shared X unchanged
    expect(after.groups[0].axes.map((a) => [a.title, a.range])).toEqual(axesBefore); // Y config unchanged
  });

  test("cursor and annotation-affecting state survive a combined-panel resize", async ({ page }) => {
    await setupCombined(page);
    await page.locator("#wwErCursorModeBtn").click();
    await clickLegendAxis(page, 0, "Current (A)");
    const activeBefore = (await plotState(page)).activeAxisKey;

    await dragResizeHandle(page, 0, -60);
    const state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeBefore);
    await expect(page.locator("#wwErCursorModeBtn")).toHaveAttribute("aria-pressed", "true");
  });

  test("minimum height is enforced in Combined mode too", async ({ page }) => {
    await setupCombined(page);
    await dragResizeHandle(page, 0, -2000);
    const height = (await plotState(page)).groups[0].height;
    expect(height).toBeGreaterThanOrEqual(100);
  });
});

test.describe("Event Reconstruction panel resize -- interaction safety and state model", () => {
  test("Grouped <-> Combined switching stays functional after a resize; a resized Grouped panel's height is independent of the Combined panel's own", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page, ["VA", "P"]);
    await dragResizeHandle(page, 0, 90);
    const groupedResized = (await plotState(page)).groups[0].height;

    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 2);
    await waitForScaled(page);
    const combinedDefault = (await plotState(page)).groups[0].height;
    expect(combinedDefault).toBeCloseTo(420, 0); // combined's own default, untouched by the Grouped resize

    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 2);
    const groupedAfterReturn = (await plotState(page)).groups[0].height;
    expect(groupedAfterReturn).toBeCloseTo(groupedResized, 0); // Grouped's own resize is kept, per view mode
    expect(consoleErrors).toEqual([]);
  });

  test("Autoscale Y, Autoscale X, drag-zoom and annotations all still function after a resize", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await dragResizeHandle(page, 0, 70);

    // Autoscale Y still works on the resized panel.
    await clickPanelHeader(page, 0);
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].pending).toBe(false);

    // Autoscale X (Fit All) still works.
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);

    // Zoom X In/Out still function.
    await page.locator("#wwErZoomInBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);

    expect(consoleErrors).toEqual([]);
  });

  test("no resize handle renders when there is no plotted panel (empty state)", async ({ page }) => {
    await page.goto("/index.html");
    const { openEventReconstruction } = require("./support/event_reconstruction_helpers");
    await openEventReconstruction(page);
    await expect(page.locator("#wwErPanelsWrap .ww-resize-handle")).toHaveCount(0);
  });

  test("no console errors across a full resize interaction sequence, both themes", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await dragResizeHandle(page, 0, 60);
    await dragResizeHandle(page, 1, -40);
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await dragResizeHandle(page, 2, 50);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction panel resize -- Waveform isolation", () => {
  test("resizing an Event Reconstruction panel never changes Waveform's own panel heights", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    const waveformHeightsBefore = await page.evaluate(() => Array.from(ww.panelHeights.entries()));

    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await dragResizeHandle(page, 0, 90);

    const waveformHeightsAfter = await page.evaluate(() => Array.from(ww.panelHeights.entries()));
    expect(waveformHeightsAfter).toEqual(waveformHeightsBefore);
  });
});
