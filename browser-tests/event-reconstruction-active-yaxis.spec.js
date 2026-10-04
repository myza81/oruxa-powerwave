// Event Reconstruction active Y-axis target (DEC-142): the explicit axis
// the global Y Zoom In/Out toolbar buttons and a double-click autoscale
// act on. Stored by the display-axis GROUP key -- never a Plotly axis
// number -- so it survives a Grouped <-> Combined switch and, where
// unambiguous, an Engineering <-> Per Unit switch. Set by clicking a
// Grouped panel's header, a Combined axis's legend heading, or any direct
// interaction with a Y axis's own scale; never by hovering or by an
// X-axis gesture.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, addRecords, channelRow, selectChannel, waitForPlot, plotState,
  zoomTo, dragOnPanel, waitForSharedAxis, clickPanelHeader, clickLegendAxis,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
  { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.5 },
];

// Minimal Waveform-owned per-unit configuration (DEC-138's own endpoints,
// same pattern as event-reconstruction-per-unit.spec.js's own configure()):
// a confirmed voltage Measurement Group so VA resolves "configured" in
// Per Unit, not "PU unavailable" -- needed to exercise the active-target
// quantity remap across an Engineering <-> Per Unit switch for real.
const wsUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${path}`;
async function configureVoltageGroup(page, station, channel) {
  const sourceId = await sourceIdFor(page, station);
  const groupsUrl = await wsUrl(page, `/sources/${sourceId}/measurement-groups`);
  // The backend auto-suggests a group for an ungrouped voltage channel;
  // clear it first (same pattern as event-reconstruction-per-unit.spec.js's
  // own configure()) or the explicit create below 409s with
  // "channel_already_grouped".
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

// Drags one Y axis's own scale (same geometry as the DEC-134 drag-zoom
// suite): "nsdrag" (middle, pans), "ndrag"/"sdrag" (an end, zooms).
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

const axisByTitle = (state, title) => state.groups.flatMap((g) => g.axes).find((a) => a.title === title);
const xState = (state) => JSON.stringify({ viewport: state.viewport, origin: state.origin, panels: state.panels.map((c) => c.xRange) });

test.describe("Event Reconstruction active Y-axis target -- Grouped", () => {
  test("exactly one Y axis auto-targets; several stay untargeted until chosen", async ({ page }) => {
    await setup(page, ["VA"]);
    let state = await plotState(page);
    expect(state.groups).toHaveLength(1);
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key);
    expect(state.yZoomInDisabled).toBe(false);
    expect(state.activeAxisReadout).toBe("Y: " + state.groups[0].title);

    await selectChannel(page, "STN_A", "P");
    await waitForPlot(page, 2);
    state = await plotState(page);
    expect(state.groups).toHaveLength(2);
    // A second axis appeared: the single-axis default does not apply
    // retroactively, but the previously (auto-)targeted axis still
    // exists, so it is kept -- never silently retargeted.
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key);
  });

  test("clicking a panel header targets that panel's axis; switching targets never touches X or other axes", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    // VA, P, F selected one at a time -- VA is briefly the only axis, so
    // the single-axis default (section 7) already targets it; it is kept
    // as P and F arrive (section 18: never silently retargeted).
    await setup(page);
    let state = await plotState(page);
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key);
    expect(state.groups[0].headerActive).toBe(true);
    expect(state.yZoomInDisabled).toBe(false);
    const x = xState(state);

    await clickPanelHeader(page, 1);
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(state.groups[1].axes[0].key);
    expect(state.groups[0].headerActive).toBe(false);
    expect(state.groups[1].headerActive).toBe(true);
    expect(xState(state)).toBe(x);

    await clickPanelHeader(page, 0);
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key);
    expect(state.groups[0].headerActive).toBe(true);
    expect(state.groups[1].headerActive).toBe(false);
    expect(state.yZoomInDisabled).toBe(false);
    expect(state.activeAxisReadout).toBe("Y: " + state.groups[0].title);
    expect(xState(state)).toBe(x);
    expect(consoleErrors).toEqual([]);
  });

  test("toolbar Y Zoom In/Out steps only the targeted panel's Y, by Waveform's own +/-20%/25% factors", async ({ page }) => {
    await setup(page);
    await clickPanelHeader(page, 0);
    let state = await plotState(page);
    const before = state.groups.map((g) => g.yRange);
    const x = xState(state);

    await page.locator("#wwErZoomYInBtn").click();
    state = await plotState(page);
    const zoomedIn = state.groups[0].yRange;
    const spanBefore = before[0][1] - before[0][0];
    const spanIn = zoomedIn[1] - zoomedIn[0];
    expect(spanIn).toBeCloseTo(spanBefore * 0.8, 6); // Waveform's WW_ZOOM_STEP_IN_FACTOR
    expect((zoomedIn[0] + zoomedIn[1]) / 2).toBeCloseTo((before[0][0] + before[0][1]) / 2, 6); // midpoint fixed
    expect(state.groups[0].axes[0].manual).toBe(true);
    expect(state.groups.slice(1).map((g) => g.yRange)).toEqual(before.slice(1));
    expect(xState(state)).toBe(x);

    await page.locator("#wwErZoomYOutBtn").click();
    state = await plotState(page);
    const spanOut = state.groups[0].yRange[1] - state.groups[0].yRange[0];
    expect(spanOut).toBeCloseTo(spanIn * 1.25, 6); // Waveform's WW_ZOOM_STEP_OUT_FACTOR
    expect(state.groups.slice(1).map((g) => g.yRange)).toEqual(before.slice(1));
    expect(xState(state)).toBe(x);
  });

  test("direct Y pan/zoom on an axis also makes it the active target", async ({ page }) => {
    await setup(page);
    let state = await plotState(page);
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key); // VA's single-axis default

    await dragAxis(page, 1, "nsdrag", "xy", 30); // pan panel 1's axis, no prior click
    await expect.poll(async () => (await plotState(page)).activeAxisKey).toBe((await plotState(page)).groups[1].axes[0].key);
    state = await plotState(page);
    expect(state.groups[1].headerActive).toBe(true);
    expect(state.groups[0].headerActive).toBe(false);

    await dragAxis(page, 2, "ndrag", "xy", -20); // end-zoom panel 2's axis
    await expect.poll(async () => (await plotState(page)).activeAxisKey).toBe((await plotState(page)).groups[2].axes[0].key);
  });

  test("hovering a Y axis never activates it, and a plain click on an inactive panel's header does not change X", async ({ page }) => {
    await setup(page);
    const before = await plotState(page);
    const activeKey = before.activeAxisKey; // VA's single-axis default
    expect(activeKey).not.toBeNull();
    const x = xState(before);

    const panel = page.locator("#wwErPanels .ww-er-panel").nth(1);
    await panel.locator(".draglayer .nsdrag").hover();
    await page.waitForTimeout(100);
    let state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeKey); // hover never activates panel 1's axis
    expect(xState(state)).toBe(x);

    await clickPanelHeader(page, 1);
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(state.groups[1].axes[0].key); // a real click does
    expect(xState(state)).toBe(x); // never touches X
  });
});

test.describe("Event Reconstruction active Y-axis target -- Combined", () => {
  async function setupCombined(page) {
    await setup(page, ["VA", "IA", "P", "F"]);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 4);
    await waitForScaled(page);
  }

  test("4 axes: click/select each, toolbar label, Y Zoom only that axis, others and X unchanged", async ({ page }) => {
    await setupCombined(page);
    let state = await plotState(page);
    // VA was briefly the only axis while being selected, so its own
    // Voltage axis already carries the single-axis default in here too
    // (the same key, carried over Grouped -> Combined unchanged).
    expect(state.activeAxisKey).toBe(axisByTitle(state, "Voltage (V)").key);
    const titles = state.groups[0].axes.map((a) => a.title);
    expect(titles).toEqual(["Voltage (V)", "Current (A)", "Active Power (MW)", "Frequency (Hz)"]);
    const x = xState(state);

    for (const title of titles) {
      await clickLegendAxis(page, 0, title);
      state = await plotState(page);
      const target = axisByTitle(state, title);
      expect(state.activeAxisKey).toBe(target.key);
      expect(state.activeAxisReadout).toBe("Y: " + title);
      const legendEntry = state.groups[0].axisLegend.find((a) => a.title === title);
      expect(legendEntry.active).toBe(true);
      expect(legendEntry.ariaPressed).toBe("true");
      expect(state.groups[0].axisLegend.filter((a) => a.active)).toHaveLength(1);

      const before = state.groups[0].axes.map((a) => a.range);
      await page.locator("#wwErZoomYInBtn").click();
      state = await plotState(page);
      state.groups[0].axes.forEach((axis, index) => {
        if (axis.title === title) expect(axis.range).not.toEqual(before[index]);
        else expect(axis.range).toEqual(before[index]);
      });
      expect(xState(state)).toBe(x);
    }
  });

  test("direct drag on one of several axes targets exactly that axis", async ({ page }) => {
    await setupCombined(page);
    await page.locator("#wwErPanels .ww-er-panel").first().locator(".draglayer .ndrag[data-subplot=\"xy3\"]")
      .scrollIntoViewIfNeeded();
    const target = page.locator("#wwErPanels .ww-er-panel").first().locator('.draglayer .ndrag[data-subplot="xy3"]');
    const box = await target.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 20, { steps: 5 });
    await page.mouse.up();
    const state = await plotState(page);
    const active = axisByTitle(state, "Active Power (MW)");
    expect(state.activeAxisKey).toBe(active.key);
  });
});

test.describe("Event Reconstruction active Y-axis target -- X navigation independence", () => {
  test("Pan, Zoom X In/Out change X only and never the active target", async ({ page }) => {
    // DEC-144: Box Zoom is retired -- every plot-area drag is Pan (no
    // mode toggle to click). At Fit All itself there is no room to pan
    // (the window already spans the full bounds), so zoomTo() first
    // reaches a narrower window to pan within.
    await setup(page);
    await clickPanelHeader(page, 0);
    await zoomTo(page, 1, 3, 0);
    const before = await plotState(page);
    const activeKey = before.activeAxisKey;
    const yRanges = before.groups.map((g) => g.yRange);

    await dragOnPanel(page, 1, 0.2, 0.5, 0); // Pan (X)
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);
    let state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeKey);
    expect(state.groups.map((g) => g.yRange)).toEqual(yRanges);

    await dragOnPanel(page, 2, 0.6, 0.4, 0); // Pan (X), another panel
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeKey);

    await page.locator("#wwErZoomInBtn").click();
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeKey);
    await page.locator("#wwErZoomOutBtn").click();
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(activeKey);
    expect(state.groups.map((g) => g.yRange)).toEqual(yRanges);
  });
});

test.describe("Event Reconstruction active Y-axis target -- mode switches", () => {
  test("Grouped -> Combined -> Grouped: the same axis stays targeted by its stable key, never a Plotly axis number", async ({ page }) => {
    await setup(page, ["VA", "P", "F"]);
    await clickPanelHeader(page, 1); // Active Power (MW)
    const grouped = await plotState(page);
    const key = grouped.activeAxisKey;
    expect(key).not.toBeNull();

    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    let state = await plotState(page);
    expect(state.activeAxisKey).toBe(key);
    expect(axisByTitle(state, "Active Power (MW)").key).toBe(key);

    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(key);
  });

  test("Engineering -> Per Unit: re-targets the equivalent axis only when unambiguous, else clears", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await addRecords(page, ["STN_A"]);
    await configureVoltageGroup(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);

    let state = await plotState(page);
    expect(state.activeAxisKey).not.toBeNull(); // single axis, auto-targeted
    const engKey = state.activeAxisKey;
    const engQuantity = state.activeAxisQuantity;
    expect(engQuantity).toBeTruthy();

    await page.locator("#wwErUnitPerUnitBtn").click();
    await expect.poll(async () => (await plotState(page)).activeAxisReadout).not.toBe("Y: Select axis");
    state = await plotState(page);
    // The exact key differs (per-unit axes have their own keys), but the
    // same physical quantity is still the one re-targeted -- never the
    // stale Engineering key.
    expect(state.activeAxisKey).not.toBe(engKey);
    expect(state.activeAxisQuantity).toBe(engQuantity);
    expect(state.yZoomInDisabled).toBe(false);

    await page.locator("#wwErUnitEngineeringBtn").click();
    state = await plotState(page);
    expect(state.activeAxisKey).toBe(engKey);
    expect(state.activeAxisQuantity).toBe(engQuantity);
  });
});

test.describe("Event Reconstruction active Y-axis target -- channel removal", () => {
  test("removing the last channel on the active axis clears it; Y Zoom disables; no silent retarget", async ({ page }) => {
    await setup(page, ["VA", "P"]);
    await clickPanelHeader(page, 0); // Voltage
    let state = await plotState(page);
    expect(state.activeAxisKey).not.toBeNull();

    const row = await channelRow(page, "STN_A", "VA");
    await row.click();
    await waitForPlot(page, 1);
    state = await plotState(page);
    expect(state.groups).toHaveLength(1); // only Active Power left
    expect(state.activeAxisKey).toBe(state.groups[0].axes[0].key); // single-axis default re-applies
  });

  test("removing the active axis down to SEVERAL remaining axes clears rather than guessing", async ({ page }) => {
    await setup(page, ["VA", "P", "F"]);
    await clickPanelHeader(page, 0); // Voltage
    let state = await plotState(page);
    expect(state.activeAxisKey).not.toBeNull();

    const row = await channelRow(page, "STN_A", "VA");
    await row.click();
    await waitForPlot(page, 2);
    state = await plotState(page);
    expect(state.groups).toHaveLength(2); // Power, Frequency -- still ambiguous
    expect(state.activeAxisKey).toBeNull();
    expect(state.yZoomInDisabled).toBe(true);
    expect(state.activeAxisReadout).toBe("Y: Select axis");
  });
});
