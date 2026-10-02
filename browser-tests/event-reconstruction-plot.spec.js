// Event Reconstruction Slice 3C (DEC-127, DEC-128): the first plotted
// reconstruction. One panel per selected analog channel on one shared
// relative reconstruction timeline, Fit All, Box Zoom/Pan, the hybrid
// visible-range fetch, the numerical plotting origin, and isolation from
// Waveform.
//
// Records are synthetic COMTRADE files built per test
// (support/synthetic_comtrade.js) so each has the sampling rate, duration
// and start instant the scenario needs.

const { test, expect } = require("@playwright/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");

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
async function uploadRecord(page, { station, startClock, rateHz = 1000, durationS = 1, channels = VI }) {
  const { cfg, dat } = syntheticComtrade({ station, startClock, rateHz, durationS, channels });
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
async function waitForPlot(page, count) {
  await expect.poll(() => page.evaluate(() => {
    const plot = wwErState.plot;
    return plot.panels.length + ":" + plot.panels.every((p) => p.plotlyReady && p.loadedKey !== null && p.loadingEl.hidden);
  })).toBe(count + ":true");
}

// A snapshot of every panel: identity, data and what Plotly holds.
async function plotState(page) {
  return page.evaluate(() => {
    const plot = wwErState.plot;
    return {
      viewport: plot.viewport,
      fitAll: plot.fitAll,
      origin: plot.origin,
      atFitAll: plot.atFitAll,
      panels: plot.panels.map((p) => ({
        key: p.key,
        recordId: p.recordId,
        sourceId: p.sourceId,
        channelName: p.channelName,
        kind: p.kind,
        label: p.labelEl.textContent,
        legend: p.legendEl.textContent,
        legendColor: p.legendEl.querySelector(".ww-legend-dot").style.background,
        r: p.reconstructionTime.slice(),
        values: p.values.slice(),
        representation: p.representation,
        unit: p.unit,
        totalOffsetS: p.timing.totalOffsetS,
        timingStartS: p.timing.startS,
        timingEndS: p.timing.endS,
        x: Array.from(p.chartEl.data[0].x),
        customdata: Array.from(p.chartEl.data[0].customdata || []),
        traceName: p.chartEl.data[0].name,
        traceColor: p.chartEl.data[0].line.color,
        traceMeta: p.chartEl.data[0].meta,
        traceType: p.chartEl.data[0].type,
        xRange: p.chartEl.layout.xaxis.range.slice(),
        tickvals: (p.chartEl.layout.xaxis.tickvals || []).slice(),
        ticktext: (p.chartEl.layout.xaxis.ticktext || []).slice(),
        dragmode: p.chartEl.layout.dragmode,
        note: p.noteEl.hidden ? "" : p.noteEl.textContent,
        error: p.errorEl.hidden ? "" : p.errorEl.textContent,
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

function expectSharedAxis(state) {
  for (const panel of state.panels) {
    expect(panel.xRange).toEqual(state.panels[0].xRange);
    expect(panel.tickvals).toEqual(state.panels[0].tickvals);
    expect(panel.ticktext).toEqual(state.panels[0].ticktext);
    expect(panel.xRange[0] + state.origin).toBeCloseTo(state.viewport.start, 9);
    expect(panel.xRange[1] + state.origin).toBeCloseTo(state.viewport.end, 9);
  }
}

test.describe("Event Reconstruction Slice 3C -- basic plotting", () => {
  test("native and calculated analog channels plot in separate panels with Waveform-owned names and colours", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:10.000000" });
    const sourceA = await sourceIdFor(page, "STN_A");
    const calcResp = await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} },
    });
    expect(calcResp.status()).toBe(201);
    const calc = await calcResp.json();
    // Waveform is the master of presentation.
    await page.evaluate((sid) => {
      wwSetChannelDisplayName(sid, "VA", "Bus VA renamed");
      wwSetChannelColorOverride(sid, "VA", "#123456");
    }, sourceA);

    await addRecords(page, ["STN_A", "STN_B"]);
    await expect(page.locator("#wwErEmptyState")).toBeVisible();
    await expect(page.locator("#wwErEmptyState")).toContainText("select analog channels");
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await expect(page.locator("#wwErEmptyState")).toBeHidden();
    await selectChannel(page, "STN_A", "-VA");
    await selectChannel(page, "STN_B", "IA");
    await waitForPlot(page, 3);

    const state = await plotState(page);
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(3);
    await expect(page.locator("#wwErCanvasMeta")).toHaveText("2 records selected · 3 channels plotted");
    const [va, negVa, ib] = state.panels;
    expect([va.label, negVa.label, ib.label]).toEqual(["STN_A · Bus VA renamed", "STN_A · -VA", "STN_B · IA"]);
    expect(va.kind).toBe("analog");
    expect(negVa.kind).toBe("calculated");
    expect(negVa.sourceId).toBe(calc.id);
    expect(va.traceName).toBe("Bus VA renamed");
    expect(va.traceColor).toBe("#123456");
    expect(va.legendColor).toBe("rgb(18, 52, 86)");
    expect(va.legend).toBe("Bus VA renamed (V)");
    expect(va.traceType).toBe("scattergl");
    expect(va.traceMeta).toBe(va.key);
    // Calculated channel: its parent's timing, its own values.
    expect(negVa.r).toEqual(va.r);
    expect(negVa.values.map((v) => -v)).toEqual(va.values.map((v) => v + 0));
    // Engineering units per panel.
    expect(va.unit).toBe("V");
    expect(ib.unit).toBe("A");
    expect(state.panels.map((p) => p.representation)).toEqual(["full_resolution", "full_resolution", "full_resolution"]);

    // A later Waveform rename/recolour is inherited on the next render.
    await page.evaluate((sid) => {
      wwSetChannelDisplayName(sid, "VA", "Bus VA again");
      wwSetChannelColorOverride(sid, "VA", "#654321");
    }, sourceA);
    await page.locator("#mainNavRecordingsBtn").click();
    await openEventReconstruction(page);
    await expect.poll(async () => (await plotState(page)).panels[0].label).toBe("STN_A · Bus VA again");
    await waitForPlot(page, 3);
    const after = (await plotState(page)).panels[0];
    expect(after.traceName).toBe("Bus VA again");
    expect(after.traceColor).toBe("#654321");

    expect(consoleErrors).toEqual([]);
  });

  test("panels follow the browser order, not the click order", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_LATE", startClock: "10:00:05.000000" });
    await uploadRecord(page, { station: "STN_EARLY", startClock: "10:00:00.000000" });
    await addRecords(page, ["STN_LATE", "STN_EARLY"]);
    // Clicked in reverse: current before voltage, later record first.
    await selectChannel(page, "STN_EARLY", "IA");
    await selectChannel(page, "STN_LATE", "IA");
    await selectChannel(page, "STN_EARLY", "VA");
    await selectChannel(page, "STN_LATE", "VA");
    await waitForPlot(page, 4);
    const labels = (await plotState(page)).panels.map((p) => p.label);
    // Reconstruction record order (STN_LATE was added first), then the
    // tree's engineering-type order (Voltage before Current).
    expect(labels).toEqual(["STN_LATE · VA", "STN_LATE · IA", "STN_EARLY · VA", "STN_EARLY · IA"]);
    await expect(page.locator("#wwErPanels .ww-panel-label")).toHaveText(labels);
  });
});

test.describe("Event Reconstruction Slice 3C -- record independence and time mapping", () => {
  test("identical-timestamp records plot separately and a correction moves only its record", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "BAHS 275kV", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "BTGH", startClock: "10:00:00.000000" });
    const bahs = await sourceIdFor(page, "BAHS 275kV");
    const btgh = await sourceIdFor(page, "BTGH");
    await addRecords(page, ["BAHS 275kV", "BTGH"]);
    await selectChannel(page, "BAHS 275kV", "VA");
    await selectChannel(page, "BTGH", "VA");
    await waitForPlot(page, 2);
    let state = await plotState(page);
    expect(state.panels.map((p) => p.recordId)).toEqual([bahs, btgh]);
    expect(state.panels.map((p) => p.label)).toEqual(["BAHS 275kV · VA", "BTGH · VA"]);
    expect(state.panels[0].r).toEqual(state.panels[1].r);

    // +4 ms on BTGH only.
    const input = memberRow(page, "BTGH").locator("input[data-er-correction-input]");
    await input.fill("4");
    await memberRow(page, "BTGH").locator('button[data-er-action="set-correction"]').click();
    await expect(memberRow(page, "BTGH").locator(".ww-er-correction-value")).toHaveText("+4.000 ms");
    await expect.poll(async () => (await plotState(page)).panels[1].totalOffsetS).toBeCloseTo(0.004, 12);
    await waitForPlot(page, 2);
    state = await plotState(page);
    const [a, b] = state.panels;
    expect(a.r[0]).toBe(0);
    expect(b.r[0]).toBeCloseTo(0.004, 12);
    for (let k = 0; k < a.r.length; k++) expect(b.r[k] - a.r[k]).toBeCloseTo(0.004, 9);
    // Waveform still groups the two records into one Time Group.
    const groups = await api(page, "/synchronization/time-groups");
    expect(groups.find((g) => g.source_ids.includes(bahs)).source_ids.slice().sort()).toEqual([bahs, btgh].sort());
  });

  test("absolute time enters once, a correction once, and a reference switch keeps pairwise alignment", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:10.000000" });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    let [a, b] = (await plotState(page)).panels;
    // Native elapsed 0 of B is 10 s after A: the recorded start
    // difference, counted exactly once.
    expect(a.r[0]).toBe(0);
    expect(b.r[0]).toBeCloseTo(10, 12);
    for (let k = 0; k < 5; k++) expect(b.r[k]).toBeCloseTo(10 + k * 0.001, 9);
    // The plotted x values are the same reconstruction times, origin-relative.
    const state = await plotState(page);
    for (const panel of state.panels) {
      panel.x.forEach((x, k) => expect(x + state.origin).toBeCloseTo(panel.customdata[k], 9));
      expect(panel.customdata).toEqual(panel.r);
    }

    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("2.5");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(async () => (await plotState(page)).panels[1].r[0]).toBeCloseTo(10.0025, 12);
    [a, b] = (await plotState(page)).panels;
    const spacing = b.r[0] - a.r[0];
    expect(spacing).toBeCloseTo(10.0025, 12);

    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-badge--reference")).toBeVisible();
    await expect.poll(async () => (await plotState(page)).panels[1].r[0]).toBeCloseTo(0, 12);
    await waitForPlot(page, 2);
    [a, b] = (await plotState(page)).panels;
    expect(a.r[0]).toBeCloseTo(-10.0025, 12);
    expect(b.r[0] - a.r[0]).toBeCloseTo(spacing, 12);
  });

  test("overlap, containment, separation and a large continuous gap keep physical time", async ({ page }) => {
    await page.goto("/index.html");
    const records = [
      ["STN_REF", "10:00:00.000000", 1.0],
      ["STN_SAME", "10:00:00.000000", 1.0], // full overlap
      ["STN_PART", "10:00:00.500000", 1.0], // partial overlap
      ["STN_INSIDE", "10:00:00.250000", 0.25], // contained
      ["STN_APART", "10:00:05.000000", 1.0], // separate
      ["STN_HOURS", "12:00:00.000000", 1.0], // large gap
    ];
    for (const [station, startClock, durationS] of records) await uploadRecord(page, { station, startClock, durationS });
    await addRecords(page, records.map((r) => r[0]));
    for (const [station] of records) await selectChannel(page, station, "VA");
    await waitForPlot(page, records.length);
    const state = await plotState(page);
    const expectedStart = { STN_REF: 0, STN_SAME: 0, STN_PART: 0.5, STN_INSIDE: 0.25, STN_APART: 5, STN_HOURS: 7200 };
    for (const panel of state.panels) {
      const station = panel.label.split(" · ")[0];
      expect(panel.r[0]).toBeCloseTo(expectedStart[station], 9);
      expect(panel.r[0]).toBeCloseTo(panel.timingStartS, 12);
      expect(panel.r[panel.r.length - 1]).toBeCloseTo(panel.timingEndS, 12);
    }
    // Fit All spans the physical extent: no compression of the 2 h gap.
    expect(state.fitAll.start).toBeCloseTo(0, 12);
    expect(state.fitAll.end).toBeCloseTo(7201, 9);
    expect(state.viewport).toEqual(state.fitAll);
    expectSharedAxis(state);
    await expect(page.locator('#wwErNotices .ww-er-notice--warn', { hasText: "Large time gap" })).toBeVisible();
  });
});

test.describe("Event Reconstruction Slice 3C -- mixed sampling and precision", () => {
  test("5 kHz, 20 Hz and 1 Hz records plot at their own sample spacing under Fit All", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_SLOW", startClock: "09:58:00.000000", rateHz: 1, durationS: 300, channels: [{ name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.01 }] });
    await uploadRecord(page, { station: "STN_MED", startClock: "10:00:00.000000", rateHz: 20, durationS: 60, channels: SLOW_VI });
    await uploadRecord(page, { station: "STN_FAST", startClock: "10:00:30.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_MED", "STN_SLOW", "STN_FAST"]);
    await selectChannel(page, "STN_MED", "VA");
    await selectChannel(page, "STN_SLOW", "F");
    await selectChannel(page, "STN_FAST", "VA");
    await waitForPlot(page, 3);
    const state = await plotState(page);
    const byStation = Object.fromEntries(state.panels.map((p) => [p.label.split(" · ")[0], p]));
    const expected = { STN_MED: [1201, 0.05], STN_SLOW: [301, 1], STN_FAST: [1001, 0.0002] };
    for (const [station, [count, spacing]] of Object.entries(expected)) {
      const panel = byStation[station];
      expect(panel.representation).toBe("full_resolution");
      expect(panel.r.length).toBe(count);
      for (let k = 1; k < panel.r.length; k++) expect(panel.r[k] - panel.r[k - 1]).toBeCloseTo(spacing, 9);
    }
    // Fit All = earliest start .. latest end, nothing expanded by rate.
    expect(state.fitAll.start).toBeCloseTo(-120, 9);
    expect(state.fitAll.end).toBeCloseTo(180, 9);
    expectSharedAxis(state);
  });

  test("a 5 kHz record two hours from the reference keeps its 0.2 ms spacing through the local plotting origin", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_REF", startClock: "10:00:00.000000", rateHz: 1, durationS: 10, channels: [{ name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.05 }] });
    await uploadRecord(page, { station: "STN_FAR", startClock: "12:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_REF", "STN_FAR"]);
    await memberRow(page, "STN_FAR").locator("input[data-er-correction-input]").fill("0.123");
    await memberRow(page, "STN_FAR").locator('button[data-er-action="set-correction"]').click();
    await expect(memberRow(page, "STN_FAR").locator(".ww-er-correction-value")).toHaveText("+0.123 ms");
    await selectChannel(page, "STN_REF", "F");
    await selectChannel(page, "STN_FAR", "VA");
    await waitForPlot(page, 2);
    let state = await plotState(page);
    const far = state.panels[1];
    expect(far.totalOffsetS).toBeCloseTo(7200.000123, 9);
    // Under Fit All every sample is there, including both boundary samples.
    expect(far.r.length).toBe(1001);
    expect(far.r[0]).toBeCloseTo(7200.000123, 9);
    expect(far.r[1000]).toBeCloseTo(7200.200123, 9);

    // Zoom to a 10 ms window inside the fast record.
    const start = far.timingStartS + 0.05;
    await zoomTo(page, start, start + 0.01);
    state = await plotState(page);
    expectSharedAxis(state);
    const zoomed = state.panels[1];
    // The origin moved next to the window: Plotly sees small numbers.
    expect(Math.abs(state.origin - state.viewport.start)).toBeLessThan(0.01 * 101);
    expect(Math.max(...zoomed.x.map(Math.abs))).toBeLessThan(1);
    // Consecutive samples stay 0.2 ms apart even at float32 precision.
    for (let k = 1; k < zoomed.x.length; k++) {
      expect(Math.fround(zoomed.x[k]) - Math.fround(zoomed.x[k - 1])).toBeCloseTo(0.0002, 7);
      // Without the origin, float32 could not separate them.
      expect(zoomed.r[k] - zoomed.r[k - 1]).toBeCloseTo(0.0002, 9);
    }
    // x <-> reconstruction round trip, hover data and tick labels are true
    // reconstruction time.
    zoomed.x.forEach((x, k) => expect(x + state.origin).toBeCloseTo(zoomed.r[k], 9));
    expect(zoomed.customdata).toEqual(zoomed.r);
    zoomed.ticktext.forEach((text, k) => expect(Number(text)).toBeCloseTo(zoomed.tickvals[k] + state.origin, 6));
    expect(zoomed.ticktext[0].startsWith("7200.")).toBe(true);
    // The pure origin helper round-trips exactly at this magnitude.
    const roundTrip = await page.evaluate((r) => wwErPlotXToReconstruction(wwErReconstructionToPlotX(r, 7200.05), 7200.05), 7200.0501234);
    expect(roundTrip).toBeCloseTo(7200.0501234, 10);
    // The reference record has no sample in this window.
    expect(state.panels[0].note).toBe("No samples of this record in the visible time range.");
    expect(state.panels[0].x).toEqual([]);
  });
});

test.describe("Event Reconstruction Slice 3C -- shared viewport and interaction", () => {
  async function threePanels(page) {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", rateHz: 1000, durationS: 4 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000", rateHz: 1000, durationS: 4 });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "IA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 3);
  }

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

  test("Fit All, box zoom on one panel, pan clamped to Fit All, and double-click back to Fit All", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await threePanels(page);
    let state = await plotState(page);
    expect(state.fitAll.start).toBeCloseTo(0, 12);
    expect(state.fitAll.end).toBeCloseTo(6, 9);
    expect(state.viewport).toEqual(state.fitAll);
    expect(state.atFitAll).toBe(true);
    expectSharedAxis(state);

    // Box zoom on the LAST panel: every panel follows.
    await dragOnPanel(page, 2, 0.25, 0.5, 60);
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);
    await waitForSharedAxis(page);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport.start).toBeGreaterThan(1.3);
    expect(state.viewport.end).toBeLessThan(3.2);
    expectSharedAxis(state);
    const zoomSpan = state.viewport.end - state.viewport.start;

    // Pan (ER's own drag mode) on the first panel: every panel follows,
    // and dragging far right is clamped at Fit All's start with the
    // span kept.
    await page.locator("#wwErDragModePanBtn").click();
    await expect.poll(async () => (await plotState(page)).panels.every((p) => p.dragmode === "pan")).toBe(true);
    const before = state.viewport.start;
    await dragOnPanel(page, 0, 0.3, 0.45);
    await expect.poll(async () => (await plotState(page)).viewport.start).toBeLessThan(before - 0.05);
    await waitForSharedAxis(page);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expectSharedAxis(state);
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(zoomSpan, 9);
    await dragOnPanel(page, 0, 0.05, 0.95);
    await dragOnPanel(page, 0, 0.05, 0.95);
    await expect.poll(async () => (await plotState(page)).viewport.start).toBeCloseTo(0, 9);
    await waitForSharedAxis(page);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(zoomSpan, 9);
    expectSharedAxis(state);

    // Double-click any panel: Fit All for every panel.
    await page.locator("#wwErPanels .ww-er-panel").nth(1).locator(".nsewdrag").dblclick();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    await waitForSharedAxis(page);
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport).toEqual(state.fitAll);
    expectSharedAxis(state);

    // Staged zoom, Reset Time View and cursors are still Slice 3D+.
    for (const id of ["#wwErZoomInBtn", "#wwErZoomOutBtn", "#wwErResetViewBtn"]) await expect(page.locator(id)).toBeDisabled();
    expect(consoleErrors).toEqual([]);
  });

  test("selection changes recompute Fit All at Fit All and keep a manual zoom otherwise", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:10.000000", durationS: 2 });
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    let state = await plotState(page);
    expect(state.fitAll.end).toBeCloseTo(2, 9);
    expect(state.viewport).toEqual(state.fitAll);

    // At Fit All: adding a channel of another record re-fits.
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    state = await plotState(page);
    expect(state.fitAll.end).toBeCloseTo(12, 9);
    expect(state.viewport).toEqual(state.fitAll);

    // Manually zoomed: adding/removing channels keeps the window.
    await zoomTo(page, 0.5, 1.5);
    await selectChannel(page, "STN_A", "IA");
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.viewport.start).toBeCloseTo(0.5, 9);
    expect(state.viewport.end).toBeCloseTo(1.5, 9);
    expectSharedAxis(state);
    await (await channelRow(page, "STN_B", "VA")).click();
    await waitForPlot(page, 2);
    state = await plotState(page);
    expect(state.fitAll.end).toBeCloseTo(2, 9);
    expect(state.viewport.start).toBeCloseTo(0.5, 9);
    expect(state.viewport.end).toBeCloseTo(1.5, 9);
  });
});

test.describe("Event Reconstruction Slice 3C -- fetch strategy", () => {
  test("viewport maps to each source's native range; non-overlapping sources are skipped; budget and units pass through", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:10.000000", durationS: 2 });
    const ids = { A: await sourceIdFor(page, "STN_A"), B: await sourceIdFor(page, "STN_B"), C: await sourceIdFor(page, "STN_C") };
    await addRecords(page, ["STN_A", "STN_B", "STN_C"]);
    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("3");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-correction-value")).toHaveText("+3.000 ms");
    for (const station of ["STN_A", "STN_B", "STN_C"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);

    const requests = [];
    page.on("request", (request) => {
      if (request.url().includes("/waveform")) requests.push(new URL(request.url()));
    });
    await zoomTo(page, 1.5, 2.5);
    const bySource = (id) => requests.filter((u) => u.pathname.includes(`/sources/${id}/waveform`));
    expect(bySource(ids.C)).toHaveLength(0); // no overlap -> no request
    const [reqA] = bySource(ids.A);
    const [reqB] = bySource(ids.B);
    expect(Number(reqA.searchParams.get("start_time"))).toBeCloseTo(1.5, 9);
    expect(reqA.searchParams.get("end_time")).toBeNull(); // window end beyond A's end -> open bound
    expect(Number(reqB.searchParams.get("start_time"))).toBeCloseTo(1.5 - 1.003, 9);
    expect(Number(reqB.searchParams.get("end_time"))).toBeCloseTo(2.5 - 1.003, 9);
    for (const req of [reqA, reqB]) {
      expect(req.searchParams.get("unit_mode")).toBe("engineering");
      expect(req.searchParams.get("channel_name")).toBe("VA");
    }
    const budget = await page.evaluate(() => wwPointBudgetForPlotWidth(wwPlotWidthForChart(wwErState.plot.panels[0].chartEl)));
    expect(Number(reqA.searchParams.get("point_budget"))).toBe(budget);
    const state = await plotState(page);
    const [a, b, c] = state.panels;
    expect(Math.min(...a.r)).toBeGreaterThanOrEqual(1.5 - 1e-9);
    expect(Math.max(...b.r)).toBeLessThanOrEqual(2.5 + 1e-9);
    expect(c.r).toEqual([]);
    expect(c.note).toBe("No samples of this record in the visible time range.");
  });

  test("a long high-rate record arrives as an envelope and resolves to full samples when zoomed", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_LONG", startClock: "10:00:00.000000", rateHz: 5000, durationS: 4 });
    await addRecords(page, ["STN_LONG"]);
    await selectChannel(page, "STN_LONG", "VA");
    await waitForPlot(page, 1);
    let panel = (await plotState(page)).panels[0];
    const budget = await page.evaluate(() => wwPointBudgetForPlotWidth(wwPlotWidthForChart(wwErState.plot.panels[0].chartEl)));
    expect(panel.representation).toBe("min_max_envelope");
    expect(panel.r.length).toBeLessThanOrEqual(budget);
    expect(Math.max(...panel.values)).toBeGreaterThan(99); // envelope keeps the peaks
    await zoomTo(page, 1, 1.1);
    panel = (await plotState(page)).panels[0];
    expect(panel.representation).toBe("full_resolution");
    expect(panel.r.length).toBe(501);
  });

  test("a superseded response never overwrites the newer view", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    const sourceA = await sourceIdFor(page, "STN_A");
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    // Hold the next request; the one after it answers at once.
    let held = 0;
    await page.route(`**/sources/${sourceA}/waveform**`, async (route) => {
      held += 1;
      if (held === 1) await new Promise((resolve) => setTimeout(resolve, 1500));
      try { await route.continue(); } catch (error) { /* aborted by the newer request */ }
    });
    await page.evaluate(() => {
      const plot = wwErState.plot;
      Plotly.relayout(plot.panels[0].chartEl, { "xaxis.range[0]": 0.5 - plot.origin, "xaxis.range[1]": 1 - plot.origin });
    });
    await expect.poll(() => held).toBe(1);
    await zoomTo(page, 2, 3);
    await page.waitForTimeout(1800);
    const panel = (await plotState(page)).panels[0];
    expect(Math.min(...panel.r)).toBeGreaterThanOrEqual(2 - 1e-9);
    expect(Math.max(...panel.r)).toBeLessThanOrEqual(3 + 1e-9);
  });
});

test.describe("Event Reconstruction Slice 3C -- empty, error and removed states", () => {
  test("one failing channel shows its own error; a removed record's panel disappears", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000" });
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:02.000000" });
    const sourceB = await sourceIdFor(page, "STN_B");
    await page.route(`**/sources/${sourceB}/waveform**`, (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "internal_error", message: "boom" } }) }));
    await addRecords(page, ["STN_A", "STN_B", "STN_C"]);
    for (const station of ["STN_A", "STN_B", "STN_C"]) await selectChannel(page, station, "VA");
    await expect(page.locator("#wwErPanels .ww-er-panel").nth(1).locator(".ww-error")).toHaveText("Something went wrong on our end. Please try again.");
    // The healthy panels still load (the failing one never completes).
    await expect.poll(async () => (await plotState(page)).panels.map((p) => p.r.length)).toEqual([1001, 0, 1001]);
    let state = await plotState(page);
    expect(state.panels[0].error).toBe("");
    await page.unroute(`**/sources/${sourceB}/waveform**`);

    // Remove STN_C's recording: its member goes stale, its panel goes.
    const sourceC = await sourceIdFor(page, "STN_C");
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator(`button[data-action="remove"][data-source-id="${sourceC}"]`).click();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator(`#recordingsTableBody tr[data-source-id="${sourceC}"]`)).toHaveCount(0);
    await openEventReconstruction(page);
    await expect(page.locator('#wwErMembersPanel .ww-er-member-row[data-member-status="stale"]')).toHaveCount(1);
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(2);
    state = await plotState(page);
    expect(state.panels.map((p) => p.label)).toEqual(["STN_A · VA", "STN_B · VA"]);
    expect(state.fitAll.end).toBeCloseTo(2, 9);

    // Clear: nothing plotted, the no-records state returns.
    await page.locator("#wwErClearBtn").click();
    await page.locator("#wwErClearConfirmBtn").click();
    await expect(page.locator("#wwErPanels .ww-er-panel")).toHaveCount(0);
    await expect(page.locator("#wwErEmptyState")).toHaveText("No reconstruction records selected. Select records in the left panel to place them on one common timeline.");
    expect((await plotState(page)).viewport).toBeNull();
  });
});

test.describe("Event Reconstruction Slice 3C -- Waveform isolation", () => {
  test("plotting, zooming, panning and drag mode never change Waveform state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.500000", durationS: 2 });
    const sourceA = await sourceIdFor(page, "STN_A");
    // Waveform: one displayed channel, a zoomed viewport, a rename.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const wfRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await wfRow.getAttribute("aria-pressed")) !== "true") await wfRow.click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    await page.evaluate((sid) => wwSetChannelDisplayName(sid, "IA", "Feeder IA"), sourceA);
    const waveform = () => page.evaluate(() => ({
      displayed: Array.from(ww.displayed.keys()).sort(),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      panels: ww.panels.map((p) => p.id + ":" + JSON.stringify(p.chartEl.layout.xaxis.range)),
      presentation: JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())),
    }));
    const before = await waveform();
    const groupsBefore = await api(page, "/synchronization/time-groups");
    const syncBefore = await api(page, "/synchronization/sources");

    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "IA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    expect((await plotState(page)).panels[0].label).toBe("STN_A · Feeder IA");
    await zoomTo(page, 0.6, 1.2);
    await page.locator("#wwErDragModePanBtn").click();
    await expect.poll(async () => (await plotState(page)).panels.every((p) => p.dragmode === "pan")).toBe(true);
    await zoomTo(page, 0.8, 1.4);

    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    expect(await api(page, "/synchronization/sources")).toEqual(syncBefore);
    await expect(page.locator("#dragModeZoomBtn")).toHaveAttribute("aria-pressed", "true");
    // Waveform's own panels never include Event Reconstruction's.
    expect(await page.evaluate(() => ww.panels.some((p) => p.chartEl.closest("#pageEventReconstruction")))).toBe(false);

    await page.locator("#mainNavWaveformBtn").click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
