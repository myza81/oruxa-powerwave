// Event Reconstruction Slice 3E (DEC-130): global A/B cursors on the
// reconstruction timeline -- one time per cursor drawn on every panel,
// nearest-real-sample values with an explicit "No sample", rebasing with
// the reconstruction zero, and isolation from Waveform's cursors.
//
// Since the Grouped Measurement View (DEC-131) per-channel values are
// shown in the left channel tree (Cur A / Cur B / Δ columns, Waveform's
// sidebar pattern); the panels only draw the lines.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, VI, SLOW_VI, api, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, openEventReconstruction,
  addRecords, channelRow, selectChannel, waitForPlot, plotState, zoomTo, waitForSharedAxis,
} = require("./support/event_reconstruction_helpers");

// Synthetic sample value, exactly as support/synthetic_comtrade.js writes
// it and the importer scales it back.
function sampleValue(channel, t) {
  const raw = Math.round(Math.sin(2 * Math.PI * (channel.frequencyHz || 50) * t + (channel.phaseShiftRad || 0)) * 30000);
  return raw * ((channel.amplitude || 1) / 30000);
}

// Cursor state, readout, every panel's drawn lines, and every plotted
// channel's values (data and its tree cells).
async function cursorState(page) {
  return page.evaluate(() => {
    const plot = wwErState.plot;
    const treeCell = (key, kind) => {
      const row = document.querySelector('#wwErMembersPanel tr.ww-er-channel-row[data-er-channel-key="' + CSS.escape(key) + '"]');
      const cell = row ? row.querySelector(".cur-value--" + kind) : null;
      return cell ? cell.textContent : null;
    };
    return {
      enabled: plot.cursors.enabled,
      a: plot.cursors.a.time,
      b: plot.cursors.b.time,
      origin: plot.origin,
      viewport: plot.viewport,
      readout: {
        hidden: document.getElementById("wwErCursorReadout").hidden,
        a: document.getElementById("wwErCursorReadoutA").textContent,
        b: document.getElementById("wwErCursorReadoutB").textContent,
        delta: document.getElementById("wwErCursorReadoutDelta").textContent,
      },
      panels: plot.panels.map((p) => {
        const line = (kind) => {
          const el = p.cursorLayerEl.querySelector('[data-er-cursor-line="' + kind + '"]');
          return { hidden: p.cursorLayerEl.hidden || el.hidden, left: parseFloat(el.style.left) };
        };
        // Where Plotly itself draws reconstruction time r on this panel
        // (origin-relative x through its own axis), relative to the wrap.
        const plotlyX = (r) => {
          const xa = p.chartEl._fullLayout.xaxis;
          const chartLeft = p.chartEl.getBoundingClientRect().left - p.chartWrapEl.getBoundingClientRect().left;
          return chartLeft + xa._offset + xa.l2p(r - plot.origin);
        };
        return {
          title: p.labelEl.textContent,
          lineA: line("a"),
          lineB: line("b"),
          plotlyXA: Number.isFinite(plot.cursors.a.time) ? plotlyX(plot.cursors.a.time) : null,
          plotlyXB: Number.isFinite(plot.cursors.b.time) ? plotlyX(plot.cursors.b.time) : null,
          headerText: p.containerEl.querySelector(".ww-panel-header").textContent,
        };
      }),
      channels: plot.panels.flatMap((p) => p.traces).map((t) => ({
        label: wwErTraceLabelText(t),
        cursorValues: t.cursorValues ? JSON.parse(JSON.stringify(t.cursorValues)) : null,
        tree: { a: treeCell(t.key, "a"), b: treeCell(t.key, "b"), delta: treeCell(t.key, "delta") },
      })),
    };
  });
}

const channel = (state, label) => state.channels.find((c) => c.label === label);

async function enableCursors(page) {
  await page.locator("#wwErCursorModeBtn").click();
  await expect(page.locator("#wwErCursorModeBtn")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#wwErCursorReadout")).toBeVisible();
}

async function setCursors(page, a, b) {
  await page.evaluate(({ a, b }) => {
    if (a !== undefined) wwErSetCursorTime("a", a);
    if (b !== undefined) wwErSetCursorTime("b", b);
  }, { a, b });
}

// Waits until every plotted channel has values for the current cursors.
async function waitForCursorValues(page) {
  await expect.poll(() => page.evaluate(() => {
    const plot = wwErState.plot;
    const shown = wwErShownCursorTimes();
    return plot.panels.flatMap((p) => p.traces).every((t) => t.cursorValues &&
      ((shown.a === null) === (t.cursorValues.a === null)) && ((shown.b === null) === (t.cursorValues.b === null)) &&
      Object.values(plot.cursorRequests).every((r) => r.done));
  })).toBe(true);
}

async function setCorrection(page, station, ms) {
  await memberRow(page, station).locator("input[data-er-correction-input]").fill(String(ms));
  await memberRow(page, station).locator('button[data-er-action="set-correction"]').click();
}

// A VA + B VA share the Voltage (V) panel; A IA has the Current (A) panel.
async function twoOverlapping(page, channels = [["STN_A", "VA"], ["STN_A", "IA"], ["STN_B", "VA"]]) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000", durationS: 4 });
  await addRecords(page, ["STN_A", "STN_B"]);
  for (const [station, ch] of channels) await selectChannel(page, station, ch);
  await waitForPlot(page, channels.length);
}

test.describe("Event Reconstruction Slice 3E -- cursor rendering and interaction", () => {
  test("A and B are drawn at one reconstruction time on every panel, drag globally, and give a precise Δt", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await twoOverlapping(page);
    await expect(page.locator("#wwErCursorModeBtn")).toBeEnabled();
    await enableCursors(page);
    let state = await cursorState(page);
    expect(state.panels.map((p) => p.title)).toEqual(["Voltage (V)", "Current (A)"]);
    // First placement: 1/3 and 2/3 of the (Fit All) view [0, 6].
    expect(state.a).toBeCloseTo(2, 12);
    expect(state.b).toBeCloseTo(4, 12);
    expect(state.readout).toMatchObject({ a: "+2.000000 s", b: "+4.000000 s", delta: "2.000000 s" });
    for (const panel of state.panels) {
      expect(panel.lineA.hidden).toBe(false);
      expect(panel.lineB.hidden).toBe(false);
      // Same reconstruction time -> same pixel on every panel, and exactly
      // where Plotly draws r - origin.
      expect(panel.lineA.left).toBeCloseTo(state.panels[0].lineA.left, 1);
      expect(panel.lineA.left).toBeCloseTo(panel.plotlyXA, 0);
      expect(panel.lineB.left).toBeCloseTo(panel.plotlyXB, 0);
      // No per-channel values on the waveform panels any more.
      expect(panel.headerText).toBe(panel.title);
    }

    // Drag A on the LAST panel 100 px to the right: one global move.
    const handle = page.locator("#wwErPanels .ww-er-panel").nth(1).locator('[data-er-cursor-drag="a"]');
    await handle.scrollIntoViewIfNeeded();
    const box = await handle.boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 50, y, { steps: 4 });
    await page.mouse.move(x + 100, y, { steps: 4 });
    await page.mouse.up();
    await expect.poll(async () => (await cursorState(page)).a).toBeGreaterThan(2.1);
    state = await cursorState(page);
    const expectedA = await page.evaluate((pageX) => {
      const plot = wwErState.plot;
      return wwPageXToTime(plot.viewport, wwPlotMetricsForChart(plot.panels[1].chartEl), pageX);
    }, x + 100);
    expect(state.a).toBeCloseTo(expectedA, 9);
    expect(state.b).toBeCloseTo(4, 12); // B untouched
    for (const panel of state.panels) {
      expect(panel.lineA.left).toBeCloseTo(state.panels[0].lineA.left, 1);
      expect(panel.lineA.left).toBeCloseTo(panel.plotlyXA, 0);
    }
    // The drag did not box-zoom.
    expect((await plotState(page)).viewport.start).toBe(0);

    // Sub-millisecond Δt stays visible.
    await setCursors(page, 2.0001234, 2.0002468);
    state = await cursorState(page);
    expect(state.readout).toMatchObject({ a: "+2.000123 s", b: "+2.000247 s", delta: "123.4 µs" });

    // Closing B leaves A only: Δt and the tree's B/Δ are unavailable, not zero.
    await page.locator("#wwErCursorCloseB").click();
    state = await cursorState(page);
    expect(state.readout.delta).toBe("—");
    expect(state.readout.b).toBe("—");
    expect(state.panels.every((p) => p.lineB.hidden && !p.lineA.hidden)).toBe(true);
    await waitForCursorValues(page);
    state = await cursorState(page);
    for (const ch of state.channels) {
      expect(ch.tree.b).toBe("—");
      expect(ch.tree.delta).toBe("—");
      expect(ch.tree.a).not.toBe("—");
    }
    // Turning cursors off and on restores both positions.
    await page.locator("#wwErCursorModeBtn").click();
    await expect(page.locator("#wwErCursorReadout")).toBeHidden();
    state = await cursorState(page);
    expect(state.panels.every((p) => p.lineA.hidden && p.lineB.hidden)).toBe(true);
    expect(state.channels.every((ch) => ch.tree.a === "—")).toBe(true);
    await enableCursors(page);
    state = await cursorState(page);
    expect(state.a).toBeCloseTo(2.0001234, 12);
    expect(state.b).toBeCloseTo(2.0002468, 12);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction Slice 3E -- cursor values", () => {
  test("5 kHz, 20 Hz and 1 Hz records each give their own nearest real sample; outside a record is 'No sample'", async ({ page }) => {
    await page.goto("/index.html");
    const fastCh = VI[0];
    const medCh = SLOW_VI[0];
    const slowCh = { name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.01 };
    await uploadRecord(page, { station: "STN_FAST", startClock: "10:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await uploadRecord(page, { station: "STN_MED", startClock: "10:00:00.000000", rateHz: 20, durationS: 60, channels: SLOW_VI });
    await uploadRecord(page, { station: "STN_SLOW", startClock: "09:59:00.000000", rateHz: 1, durationS: 300, channels: [slowCh] });
    await addRecords(page, ["STN_FAST", "STN_MED", "STN_SLOW"]);
    await selectChannel(page, "STN_FAST", "VA");
    await selectChannel(page, "STN_MED", "VA");
    await selectChannel(page, "STN_SLOW", "F");
    await waitForPlot(page, 3);
    await enableCursors(page);
    // A between samples everywhere; B past the fast record's end.
    await setCursors(page, 0.10013, 0.25);
    await waitForCursorValues(page);
    const state = await cursorState(page);
    const fast = channel(state, "STN_FAST · VA");
    const med = channel(state, "STN_MED · VA");
    const slow = channel(state, "STN_SLOW · F");
    // Nearest REAL samples (no interpolation): 5 kHz -> t = 0.1002 s;
    // 20 Hz -> t = 0.1 s; 1 Hz (starts 60 s earlier) -> native 60 s.
    expect(fast.cursorValues.a.value).toBeCloseTo(sampleValue(fastCh, 0.1002), 9);
    expect(med.cursorValues.a.value).toBeCloseTo(sampleValue(medCh, 0.1), 9);
    expect(slow.cursorValues.a.value).toBeCloseTo(sampleValue(slowCh, 60), 9);
    // B: no 5 kHz sample at 0.25 s; the slow records still answer.
    expect(fast.cursorValues.b.noSample).toBe(true);
    expect(fast.tree.b).toBe("No sample");
    expect(fast.tree.delta).toBe("—");
    expect(med.cursorValues.b.value).toBeCloseTo(sampleValue(medCh, 0.25), 9);
    expect(slow.cursorValues.b.value).toBeCloseTo(sampleValue(slowCh, 60), 9);
    // Tree cells use Waveform's engineering value format (unit in the
    // channel label), and Δ = B - A.
    const formatted = await page.evaluate(({ a, b }) => ({ a: wwFormatEngineeringValue(a), delta: wwFormatEngineeringValue(b - a) }),
      { a: med.cursorValues.a.value, b: med.cursorValues.b.value });
    expect(med.tree.a).toBe(formatted.a);
    expect(med.tree.delta.replace(/^\+/, "")).toBe(formatted.delta);
    // The cursor line is still drawn on every panel (the fast record's too).
    expect(state.panels.every((p) => !p.lineB.hidden)).toBe(true);
  });

  test("a gap shows 'No sample' per record; a calculated channel answers through its timing parent", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 1 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:05.000000", durationS: 1 });
    const sourceA = await sourceIdFor(page, "STN_A");
    const calc = await (await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} },
    })).json();
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "-VA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 3);
    await enableCursors(page);
    await setCursors(page, 0.5003, 5.2507);
    await waitForCursorValues(page);
    const state = await cursorState(page);
    const va = channel(state, "STN_A · VA");
    const negVa = channel(state, "STN_A · -VA");
    const vb = channel(state, "STN_B · VA");
    expect(va.cursorValues.a.value).toBeCloseTo(sampleValue(VI[0], 0.5), 9);
    expect(va.cursorValues.b.noSample).toBe(true);
    expect(negVa.cursorValues.a.value).toBeCloseTo(-va.cursorValues.a.value, 9);
    expect(negVa.cursorValues.b.noSample).toBe(true);
    expect(vb.cursorValues.a.noSample).toBe(true);
    expect(vb.cursorValues.b.value).toBeCloseTo(sampleValue(VI[0], 0.251), 9);
    expect(vb.tree.a).toBe("No sample");
    // Δ is not computed from a missing side.
    expect(va.tree.delta).toBe("—");
    // Both cursors stay drawn on every panel.
    for (const panel of state.panels) expect(panel.lineA.hidden || panel.lineB.hidden).toBe(false);
    expect(calc.reference_source_id).toBe(sourceA);
  });
});

test.describe("Event Reconstruction Slice 3E -- cursor rebasing", () => {
  test("a reference switch and a reference correction keep the physical instant; a non-reference correction moves only its record", async ({ page }) => {
    await twoOverlapping(page, [["STN_A", "VA"], ["STN_B", "VA"]]);
    await enableCursors(page);
    await setCursors(page, 3.0, 3.5);
    await waitForCursorValues(page);
    const base = await cursorState(page);
    const valuesOf = (state) => state.channels.map((c) => [c.cursorValues.a.value, c.cursorValues.b.value]);

    // Reference -> B (offset 2 s): cursors 1.0 / 1.5, same samples.
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await cursorState(page)).a).toBeCloseTo(1, 9);
    await waitForCursorValues(page);
    let state = await cursorState(page);
    expect(state.b).toBeCloseTo(1.5, 9);
    expect(valuesOf(state)).toEqual(valuesOf(base));

    // Correction on the reference (B, +5 ms): the zero moves, so do A/B --
    // they keep the same physical instant. A (clock unchanged) reads the
    // same samples; B's own clock moved, so B now reads 5 ms earlier.
    await setCorrection(page, "STN_B", 5);
    await expect.poll(async () => (await cursorState(page)).a).toBeCloseTo(0.995, 9);
    await waitForCursorValues(page);
    state = await cursorState(page);
    expect(state.b).toBeCloseTo(1.495, 9);
    expect(valuesOf(state)[0]).toEqual(valuesOf(base)[0]);
    expect(state.channels[1].cursorValues.a.value).toBeCloseTo(sampleValue(VI[0], 0.995), 9);
    // ... and its reset moves them back.
    await memberRow(page, "STN_B").locator('button[data-er-action="reset-correction"]').click();
    await expect.poll(async () => (await cursorState(page)).a).toBeCloseTo(1, 9);

    // Correction on a non-reference record (A, +20 ms): the cursors stay;
    // A moves beneath them (its values change), B's do not.
    await setCorrection(page, "STN_A", 20);
    await expect.poll(async () => (await plotState(page)).panels[0].totalOffsetS).toBeCloseTo(-1.98, 9);
    await waitForCursorValues(page);
    state = await cursorState(page);
    expect(state.a).toBeCloseTo(1, 9);
    expect(state.b).toBeCloseTo(1.5, 9);
    expect(state.channels[1].cursorValues.a.value).toBe(base.channels[1].cursorValues.a.value);
    // A at r = 1 is now A's native 2.98 s (20 ms earlier than before).
    expect(state.channels[0].cursorValues.a.value).toBeCloseTo(sampleValue(VI[0], 2.98), 9);
  });
});

test.describe("Event Reconstruction Slice 3E -- cursors through navigation, selection and removal", () => {
  test("zoom, pan and reset never move a cursor; selection changes and record removal keep positions", async ({ page }) => {
    await twoOverlapping(page);
    await enableCursors(page);
    await setCursors(page, 1, 3);
    await zoomTo(page, 3.5, 4.5);
    let state = await cursorState(page);
    expect([state.a, state.b]).toEqual([1, 3]);
    expect(state.panels.every((p) => p.lineA.hidden && p.lineB.hidden)).toBe(true); // off-screen
    expect(state.readout.a).toBe("+1.000000 s");
    await zoomTo(page, 2.5, 3.5);
    state = await cursorState(page);
    expect(state.panels.every((p) => p.lineA.hidden && !p.lineB.hidden)).toBe(true);
    for (const panel of state.panels) expect(panel.lineB.left).toBeCloseTo(panel.plotlyXB, 0);
    await page.locator("#wwErResetViewBtn").click();
    await waitForSharedAxis(page);
    state = await cursorState(page);
    expect([state.a, state.b]).toEqual([1, 3]);
    expect(state.panels.every((p) => !p.lineA.hidden && !p.lineB.hidden)).toBe(true);

    // Selection changes: positions kept; a newly plotted channel gets values.
    await selectChannel(page, "STN_B", "IA");
    await waitForPlot(page, 4);
    await waitForCursorValues(page);
    state = await cursorState(page);
    expect([state.a, state.b]).toEqual([1, 3]);
    const ib = channel(state, "STN_B · IA");
    expect(ib.cursorValues.a.noSample).toBe(true); // B starts at r = 2
    expect(ib.cursorValues.b.value).toBeCloseTo(sampleValue(VI[1], 1), 9);
    expect(ib.tree.a).toBe("No sample");
    await (await channelRow(page, "STN_A", "IA")).click();
    await waitForPlot(page, 3);
    expect([(await cursorState(page)).a, (await cursorState(page)).b]).toEqual([1, 3]);

    // Removing STN_B's recording: its channels go, no stale values remain,
    // the cursors stay.
    const sourceB = await sourceIdFor(page, "STN_B");
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator(`button[data-action="remove"][data-source-id="${sourceB}"]`).click();
    await page.locator("#confirmRemoveBtn").click();
    await expect(page.locator(`#recordingsTableBody tr[data-source-id="${sourceB}"]`)).toHaveCount(0);
    await openEventReconstruction(page);
    await waitForPlot(page, 1);
    await waitForCursorValues(page);
    state = await cursorState(page);
    expect([state.a, state.b]).toEqual([1, 3]);
    expect(state.channels.map((c) => c.label)).toEqual(["STN_A · VA"]);
    expect(state.channels[0].cursorValues.a.value).toBeCloseTo(sampleValue(VI[0], 1), 9);
    // The stale member shows no channel tree, so no value cells remain for it.
    await expect(page.locator('#wwErMembersPanel .ww-er-member-row[data-member-status="stale"] .cur-value')).toHaveCount(0);
  });

  test("two hours from the reference, cursors one 5 kHz sample apart stay distinct and exact", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_REF", startClock: "10:00:00.000000", rateHz: 1, durationS: 10, channels: [{ name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.05 }] });
    await uploadRecord(page, { station: "STN_FAR", startClock: "12:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_REF", "STN_FAR"]);
    await selectChannel(page, "STN_REF", "F");
    await selectChannel(page, "STN_FAR", "VA");
    await waitForPlot(page, 2);
    await zoomTo(page, 7200.05, 7200.06);
    await enableCursors(page);
    // Not midway between samples (a tie resolves to the earlier sample).
    await setCursors(page, 7200.05015, 7200.05035);
    await waitForCursorValues(page);
    const state = await cursorState(page);
    expect(state.origin).toBeGreaterThan(7200);
    expect(state.readout).toMatchObject({ a: "+7200.050150 s", b: "+7200.050350 s", delta: "200.0 µs" });
    const far = channel(state, "STN_FAR · VA");
    expect(far.cursorValues.a.value).toBeCloseTo(sampleValue(VI[0], 0.0502), 9);
    expect(far.cursorValues.b.value).toBeCloseTo(sampleValue(VI[0], 0.0504), 9);
    expect(far.cursorValues.a.value).not.toBe(far.cursorValues.b.value);
    // 0.2 ms of a 10 ms window is 2 % of the plot width, on both panels.
    const width = await page.evaluate(() => wwPlotMetricsForChart(wwErState.plot.panels[0].chartEl).plotWidth);
    for (const panel of state.panels) {
      expect(panel.lineB.left - panel.lineA.left).toBeCloseTo(width * 0.02, 0);
      expect(panel.lineA.left).toBeCloseTo(panel.plotlyXA, 0);
    }
    expect(channel(state, "STN_REF · F").cursorValues.a.noSample).toBe(true); // the 10 s reference record
  });
});

test.describe("Event Reconstruction Slice 3E -- Waveform isolation", () => {
  test("Event Reconstruction cursors never change Waveform cursors, values or state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000", durationS: 4 });
    // Waveform: one displayed channel with its own A/B cursors on.
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const wfRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await wfRow.getAttribute("aria-pressed")) !== "true") await wfRow.click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    // Waveform top-toolbar migration (owner ticket, DEC-158): the A/B
    // Cursors mode toggle is page-level now (#wwCursorModeBtn), not a
    // per-canvas local button -- targets the one Time Group displayed
    // here via its own active/first-valid resolution.
    await page.locator("#wwCursorModeBtn").click();
    await expect(page.locator("#wwTimeGroupCanvases .ww-tg-cursor-readout").first()).toBeVisible();
    await page.waitForTimeout(500);
    const waveform = () => page.evaluate(() => ({
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
      values: JSON.stringify(Array.from(ww.cursorValues.entries())),
      readout: document.querySelector("#wwTimeGroupCanvases .ww-tg-cursor-readout").textContent,
      cells: Array.from(document.querySelectorAll("#channelGroups .cur-value")).map((c) => c.textContent),
      displayed: Array.from(ww.displayed.keys()).sort(),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      presentation: JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())),
    }));
    const before = await waveform();
    const groupsBefore = await api(page, "/synchronization/time-groups");
    const syncBefore = await api(page, "/synchronization/sources");

    await openEventReconstruction(page);
    await addRecords(page, ["STN_A", "STN_B"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    await enableCursors(page);
    await setCursors(page, 1.234, 4.321);
    await waitForCursorValues(page);
    await page.locator("#wwErCursorCloseA").click();
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await waitForCursorValues(page);

    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    expect(await api(page, "/synchronization/sources")).toEqual(syncBefore);
    await page.locator("#mainNavWaveformBtn").click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
