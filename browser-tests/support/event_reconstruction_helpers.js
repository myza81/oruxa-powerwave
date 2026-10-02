// Shared helpers for the Event Reconstruction plotting/navigation browser
// specs (Slices 3C/3D): synthetic record upload, record/member/channel
// locators, and snapshots of Event Reconstruction's own plot state
// (wwErState.plot) and of what each Plotly panel holds.

const { expect } = require("@playwright/test");
const { syntheticComtrade } = require("./synthetic_comtrade");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

function collectConsoleErrors(page) {
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

const VI = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "IA", unit: "A", phase: "A", amplitude: 5, frequencyHz: 50 },
];
const SLOW_VI = VI.map((c) => Object.assign({}, c, { frequencyHz: 0.5 }));

// Uploads one synthetic record through the normal Recordings flow.
async function uploadRecord(page, { station, date, startClock, rateHz = 1000, durationS = 1, channels = VI }) {
  const { cfg, dat } = syntheticComtrade({ station, date, startClock, rateHz, durationS, channels });
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: `${station}.cfg`, mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: `${station}.dat`, mimeType: "application/octet-stream", buffer: dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
}

async function workspaceId(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}

async function api(page, pathSuffix) {
  const resp = await page.request.get(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}${pathSuffix}`);
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

async function sourceIdFor(page, station) {
  return (await api(page, "/sources")).find((s) => s.station_name === station).source_id;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const exactName = (page, station) => page.locator(".source-recording-name", { hasText: new RegExp(`^${escapeRegExp(station)}$`) });
const recordRow = (page, station) => page.locator("#wwErRecordsPanel .ww-er-record-row", { has: exactName(page, station) });
const memberRow = (page, station) => page.locator("#wwErMembersPanel .ww-er-member-row", { has: exactName(page, station) });

async function openEventReconstruction(page) {
  await page.locator("#mainNavEventReconstructionBtn").click();
  await expect(page.locator("#pageEventReconstruction")).toBeVisible();
}

async function addRecords(page, stations) {
  await openEventReconstruction(page);
  for (const station of stations) {
    await recordRow(page, station).locator('button[data-er-action="add-record"]').click();
    await expect(recordRow(page, station).getByText("In reconstruction")).toBeVisible();
  }
}

async function channelRow(page, station, channelName) {
  const row = memberRow(page, station);
  const tree = row.locator("details.ww-er-member-tree");
  if (!(await tree.evaluate((el) => el.open))) await tree.locator(":scope > summary").click();
  return row.locator(`tr.ww-er-channel-row[data-er-channel-name="${channelName}"]`);
}

async function selectChannel(page, station, channelName) {
  const row = await channelRow(page, station, channelName);
  await row.click();
  await expect(row).toHaveAttribute("aria-pressed", "true");
}

// Waits until `count` panels exist and every one has finished loading
// for the current viewport.
// Waits until `count` channels (traces) are plotted and every one has
// finished loading for the current viewport.
async function waitForPlot(page, count) {
  await expect.poll(() => page.evaluate(() => {
    const plot = wwErState.plot;
    const traces = plot.panels.flatMap((p) => p.traces);
    return traces.length + ":" + (plot.panels.every((p) => p.plotlyReady) &&
      traces.every((t) => !t.loading && (t.loadedKey !== null || t.error !== null)));
  })).toBe(count + ":true");
}

// A snapshot of the plot. `panels` is CHANNEL-level (one entry per trace,
// in panel order then trace order), each carrying its own data and the
// axis state of the panel it is drawn on; `groups` is panel-level.
async function plotState(page) {
  return page.evaluate(() => {
    const plot = wwErState.plot;
    const channels = [];
    plot.panels.forEach((p, panelIndex) => {
      p.traces.forEach((t, traceIndex) => {
        const data = p.chartEl.data[traceIndex] || { x: [], customdata: [], line: {} };
        // The trace's own Y axis (Grouped: the panel's only one).
        const axis = p.axes[t.axisIndex];
        const layoutKey = axis.placement.layoutKey;
        const chip = p.legendEl.querySelector('[data-er-trace-key="' + CSS.escape(t.key) + '"]');
        channels.push({
          key: t.key,
          recordId: t.recordId,
          sourceId: t.sourceId,
          channelName: t.channelName,
          kind: t.kind,
          label: wwErTraceLabelText(t),
          panelIndex,
          panelTitle: p.labelEl.textContent,
          legend: chip ? chip.textContent : "",
          legendColor: chip ? chip.querySelector(".ww-legend-dot").style.background : "",
          r: t.reconstructionTime.slice(),
          values: t.values.slice(),
          representation: t.representation,
          unit: t.unit,
          totalOffsetS: t.timing.totalOffsetS,
          timingStartS: t.timing.startS,
          timingEndS: t.timing.endS,
          x: Array.from(data.x || []),
          customdata: Array.from(data.customdata || []),
          traceName: data.name,
          traceColor: data.line && data.line.color,
          traceMeta: data.meta,
          traceType: data.type,
          traceYAxis: data.yaxis || "y",
          axisKey: axis.key,
          xRange: p.chartEl.layout.xaxis.range.slice(),
          tickvals: (p.chartEl.layout.xaxis.tickvals || []).slice(),
          ticktext: (p.chartEl.layout.xaxis.ticktext || []).slice(),
          dragmode: p.chartEl.layout.dragmode,
          yRange: p.chartEl._fullLayout[layoutKey].range.slice(),
          yAutorange: p.chartEl.layout[layoutKey].autorange,
          yFixedRange: p.chartEl.layout[layoutKey].fixedrange,
          autoscaleYPending: axis.autoscaleYPending,
          note: t.loadedKey !== null && !t.reconstructionTime.length ? "No samples of this record in the visible time range." : "",
          error: t.error || "",
          panelNote: p.noteEl.hidden ? "" : p.noteEl.textContent,
          panelError: p.errorEl.hidden ? "" : p.errorEl.textContent,
        });
      });
    });
    return {
      viewport: plot.viewport,
      fitAll: plot.fitAll,
      origin: plot.origin,
      atFitAll: plot.atFitAll,
      viewMode: plot.viewMode,
      panels: channels,
      groups: plot.panels.map((p) => ({
        key: p.key,
        title: p.labelEl.textContent,
        traces: p.traces.map((t) => wwErTraceLabelText(t)),
        traceKeys: p.traces.map((t) => t.key),
        xRange: p.chartEl.layout.xaxis.range.slice(),
        combined: p.combined,
        height: p.chartEl.getBoundingClientRect().height,
        // Grouped panels have one axis: these are its values.
        yRange: p.chartEl._fullLayout.yaxis.range.slice(),
        yAutorange: p.chartEl.layout.yaxis.autorange,
        autoscaleYPending: p.axes.some((a) => a.autoscaleYPending),
        axes: p.axes.map((a, index) => {
          const full = p.chartEl._fullLayout[a.placement.layoutKey];
          const own = p.chartEl.layout[a.placement.layoutKey];
          return {
            key: a.key,
            title: full.title && full.title.text,
            ref: a.placement.ref,
            layoutKey: a.placement.layoutKey,
            side: full.side,
            anchor: full.anchor,
            overlaying: full.overlaying || null,
            autoshift: !!own.autoshift,
            shift: full._shift || 0,
            fixedRange: own.fixedrange,
            range: full.range.slice(),
            autorange: own.autorange,
            showTickLabels: full.showticklabels,
            pending: a.autoscaleYPending,
            manual: !!a.manual,
            traceKeys: p.traces.filter((t) => t.axisIndex === index).map((t) => t.key),
          };
        }),
        plotLeft: p.chartEl._fullLayout._size.l,
        plotWidth: p.chartEl._fullLayout._size.w,
        axisLegend: Array.from(p.legendEl.querySelectorAll(".ww-er-legend-axis")).map((el) => ({
          title: el.querySelector(".ww-er-legend-axis-title").textContent,
          chips: Array.from(el.querySelectorAll(".ww-legend-item")).map((chip) => chip.textContent),
        })),
        note: p.noteEl.hidden ? "" : p.noteEl.textContent,
        error: p.errorEl.hidden ? "" : p.errorEl.textContent,
        legend: Array.from(p.legendEl.querySelectorAll(".ww-legend-item")).map((el) => el.textContent),
      })),
    };
  });
}

// Sets the common viewport through a real Plotly relayout on one panel
// (what a box zoom produces), then waits for every panel to reload.
async function zoomTo(page, start, end, panelIndex = 0) {
  await page.evaluate(({ start, end, panelIndex }) => {
    const plot = wwErState.plot;
    const panel = plot.panels[panelIndex];
    Plotly.relayout(panel.chartEl, { "xaxis.range[0]": start - plot.origin, "xaxis.range[1]": end - plot.origin });
  }, { start, end, panelIndex });
  await expect.poll(async () => {
    const vp = (await plotState(page)).viewport;
    return Math.abs(vp.start - start) < 1e-9 && Math.abs(vp.end - end) < 1e-9;
  }).toBe(true);
  await waitForSharedAxis(page);
  const count = (await plotState(page)).panels.length;
  await waitForPlot(page, count);
}

// Waits until every panel's X axis shows the common viewport (a gesture's
// debounced re-apply has reached every panel).
async function waitForSharedAxis(page) {
  await expect.poll(() => page.evaluate(() => {
    const plot = wwErState.plot;
    const span = plot.viewport.end - plot.viewport.start;
    return plot.panels.every((p) => {
      const range = p.chartEl.layout.xaxis.range;
      return Math.abs(range[0] + plot.origin - plot.viewport.start) < span * 1e-9 &&
        Math.abs(range[1] + plot.origin - plot.viewport.end) < span * 1e-9;
    });
  })).toBe(true);
}

// A real mouse drag across one panel's plot area (box zoom or pan,
// whichever drag mode is active), from/to fractions of its width.
async function dragOnPanel(page, panelIndex, fromFraction, toFraction, dy = 0) {
  const target = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator(".nsewdrag");
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width * fromFraction, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * ((fromFraction + toFraction) / 2), y + dy / 2, { steps: 5 });
  await page.mouse.move(box.x + box.width * toFraction, y + dy, { steps: 5 });
  await page.mouse.up();
}

function expectSharedAxis(state) {
  for (const panel of state.panels) {
    expect(panel.xRange).toEqual(state.panels[0].xRange);
    expect(panel.tickvals).toEqual(state.panels[0].tickvals);
    expect(panel.ticktext).toEqual(state.panels[0].ticktext);
    expect(panel.xRange[0] + state.origin).toBeCloseTo(state.viewport.start, 9);
    expect(panel.xRange[1] + state.origin).toBeCloseTo(state.viewport.end, 9);
  }
}

module.exports = {
  BACKEND, VI, SLOW_VI, collectConsoleErrors, uploadRecord, workspaceId, api, sourceIdFor,
  recordRow, memberRow, openEventReconstruction, addRecords, channelRow, selectChannel,
  waitForPlot, plotState, zoomTo, waitForSharedAxis, expectSharedAxis, dragOnPanel,
};
