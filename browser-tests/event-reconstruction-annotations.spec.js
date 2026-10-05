// Event Reconstruction annotations (DEC-136 as amended by DEC-137): the
// SAME four tools as Waveform -- Text Note, Callout, Maximum Peak, Minimum
// Peak -- and an Annotations manager, over Event Reconstruction's OWN
// backend-owned state. Text Notes are reconstruction-level (rebased with
// the reference frame); Callouts and Peaks are attached to one plotted
// channel and follow that record's corrections. Grouped and Combined
// draw them on the right trace and Y axis; Relative / Absolute changes
// only their time text.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, api, addRecords, selectChannel,
  waitForPlot, plotState, zoomTo, openEventReconstruction, channelRow,
} = require("./support/event_reconstruction_helpers");

// P = amplitude * sin(pi t) on a 1 kHz grid (synthetic_comtrade.js), so
// every peak below is known in closed form. STN_B's P has a different
// amplitude, so no two plotted traces ever coincide.
const A_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
];
const B_CHANNELS = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 60, frequencyHz: 0.5 },
];

const erUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/event-reconstruction${path}`;
const definitionAnnotations = async (page) => (await api(page, "/event-reconstruction/definition")).annotations;
const byType = async (page, type) => (await definitionAnnotations(page)).filter((a) => a.type === type);

async function recordIdOf(page, station) {
  const sourceId = await sourceIdFor(page, station);
  const definition = await api(page, "/event-reconstruction/definition");
  return definition.members.find((m) => m.source_ids.includes(sourceId)).record_id;
}

async function createViaApi(page, body) {
  const resp = await page.request.post(await erUrl(page, "/definition/annotations"), { data: body });
  expect(resp.status(), await resp.text()).toBe(201);
  const before = new Set((await page.evaluate(() => wwErAnnotations().map((a) => a.annotation_id))));
  await page.evaluate(() => wwErRefresh().then(() => wwErRender()));
  return (await resp.json()).annotations.find((a) => !before.has(a.annotation_id));
}

async function chooseTool(page, type) {
  await page.locator("#wwErAnnotateBtn").click();
  await expect(page.locator("#wwErAnnotateMenu")).toBeVisible();
  await page.locator(`#wwErAnnotateMenu [data-annotation-type="${type}"]`).click();
  await expect(page.locator("#wwErAnnotateMenu")).toBeHidden();
  await expect(page.locator("#wwErAnnotationGuidance")).toBeVisible();
}

// Page point of the plotted point nearest reconstruction time `r` on one
// trace (station + channel), from Plotly's own axes.
const tracePoint = (page, station, channelName, r) => page.evaluate(({ station, channelName, r }) => {
  const plot = wwErState.plot;
  for (const panel of plot.panels) {
    const index = panel.traces.findIndex((t) => wwErMemberName(t.recordId) === station && t.channelName === channelName);
    if (index === -1) continue;
    const data = panel.chartEl.data[index];
    let best = 0;
    for (let i = 1; i < data.x.length; i++) if (Math.abs(data.x[i] - (r - plot.origin)) < Math.abs(data.x[best] - (r - plot.origin))) best = i;
    const fl = panel.chartEl._fullLayout;
    const ya = fl[!data.yaxis || data.yaxis === "y" ? "yaxis" : "yaxis" + data.yaxis.slice(1)];
    const rect = panel.chartEl.getBoundingClientRect();
    return { x: rect.left + fl.xaxis._offset + fl.xaxis.l2p(data.x[best]), y: rect.top + ya._offset + ya.l2p(data.y[best]), r: data.x[best] + plot.origin };
  }
  return null;
}, { station, channelName, r });

// Every Event Reconstruction annotation as drawn, with where Plotly itself
// puts its time/value (the trace's own Y axis) -- computed here from the
// definition's timings, independently of the page's annotation code.
const drawn = (page) => page.evaluate(() => {
  const plot = wwErState.plot;
  const wrap = document.getElementById("wwErPanelsWrap").getBoundingClientRect();
  const offsetOf = (sourceId) => {
    const calculated = wwErState.calculatedChannels.find((c) => c.id === sourceId);
    const timingId = calculated ? calculated.reference_source_id : sourceId;
    for (const m of wwErState.definition.members) for (const t of m.source_timings || []) if (t.source_id === timingId) return t.total_reconstruction_offset_s;
    return null;
  };
  return wwErAnnotations().map((a) => {
    const el = document.querySelector(`#wwErAnnotationOverlay .ww-annotation[data-er-annotation-id="${a.annotation_id}"]`);
    const group = document.querySelector(`#wwErCalloutConnectorLayer [data-annotation-id="${a.annotation_id}"]`);
    const markerEl = group && group.style.display !== "none" ? group.querySelector(".ww-callout-anchor-marker") : null;
    const peak = wwErState.annotationUi.peakResults[a.annotation_id] || null;
    let expected = null;
    if (a.type === "text_note") {
      const panel = plot.panels[0].combined ? plot.panels[0] : (plot.panels.find((p) => p.axes[0].key === a.axis_key) || plot.panels[0]);
      const fl = panel.chartEl._fullLayout;
      const rect = panel.chartEl.getBoundingClientRect();
      expected = {
        r: a.reconstruction_time_s,
        x: rect.left - wrap.left + fl.xaxis._offset + fl.xaxis.l2p(a.reconstruction_time_s - plot.origin),
        y: rect.top - wrap.top + fl._size.t + a.y_fraction * fl._size.h,
      };
    } else {
      const sourceElapsed = a.type === "callout" ? a.anchor.source_elapsed_s : (peak && peak.available ? peak.sourceElapsed : null);
      const value = a.type === "callout" ? a.anchor.value : (peak && peak.available ? peak.value : null);
      const offset = offsetOf(a.channel.source_id);
      for (const panel of plot.panels) {
        const index = panel.traces.findIndex((t) => t.recordId === a.channel.record_id && t.sourceId === a.channel.source_id && t.channelName === a.channel.channel_name);
        if (index === -1 || sourceElapsed === null) continue;
        const data = panel.chartEl.data[index];
        const fl = panel.chartEl._fullLayout;
        const ya = fl[!data.yaxis || data.yaxis === "y" ? "yaxis" : "yaxis" + data.yaxis.slice(1)];
        const rect = panel.chartEl.getBoundingClientRect();
        const r = sourceElapsed + offset;
        expected = {
          r, value, yaxis: data.yaxis || "y",
          x: rect.left - wrap.left + fl.xaxis._offset + fl.xaxis.l2p(r - plot.origin),
          y: rect.top - wrap.top + ya._offset + ya.l2p(value),
        };
      }
    }
    return {
      id: a.annotation_id, type: a.type, text: a.text,
      visible: !!el && el.style.display !== "none",
      left: el ? parseFloat(el.style.left) : null, top: el ? parseFloat(el.style.top) : null,
      marker: markerEl ? { x: Number(markerEl.getAttribute("cx")), y: Number(markerEl.getAttribute("cy")) } : null,
      header: el ? el.querySelector(".ww-annotation-header").textContent : null,
      body: el && el.querySelector(".ww-annotation-body") ? el.querySelector(".ww-annotation-body").textContent : null,
      valueLine: el && el.querySelector(".ww-peak-value-line") ? el.querySelector(".ww-peak-value-line").textContent : null,
      timeLine: el && el.querySelector(".ww-peak-time-line") ? el.querySelector(".ww-peak-time-line").textContent : null,
      selected: !!el && el.classList.contains("ww-annotation--selected"),
      boxOffset: a.box_offset, peak, expected,
    };
  });
});

const findDrawn = async (page, id) => (await drawn(page)).find((d) => d.id === id);

// Drawn exactly where Plotly draws the same time (and, for a Callout /
// Peak, the same value on the trace's own Y axis).
async function expectPlaced(page, id) {
  await expect.poll(async () => (await findDrawn(page, id)).visible).toBe(true);
  const d = await findDrawn(page, id);
  if (d.type === "text_note") {
    expect(d.left).toBeCloseTo(d.expected.x, 0);
    expect(d.top).toBeCloseTo(d.expected.y, 0);
  } else {
    expect(Math.abs(d.marker.x - d.expected.x)).toBeLessThan(1);
    expect(Math.abs(d.marker.y - d.expected.y)).toBeLessThan(1);
    expect(d.left).toBeCloseTo(d.marker.x + d.boxOffset.x, 0);
    expect(d.top).toBeCloseTo(d.marker.y + d.boxOffset.y, 0);
  }
  return d;
}

const timeText = (page, id) => page.evaluate((id) => {
  const a = wwErAnnotationById(id);
  return wwErAnnotationTimeText(wwErAnnotationTime(a));
}, id);

async function setup(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: A_CHANNELS });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4, channels: B_CHANNELS });
}

async function plotAB(page) {
  await addRecords(page, ["STN_A", "STN_B"]);
  await selectChannel(page, "STN_A", "VA");
  await selectChannel(page, "STN_A", "P");
  await selectChannel(page, "STN_B", "P");
  await waitForPlot(page, 3);
}

async function dragBy(page, locator, dx, dy) {
  const box = await locator.boundingBox();
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 4 });
  await page.mouse.move(x + dx, y + dy, { steps: 4 });
  await page.mouse.up();
}

const box = (page, id) => page.locator(`#wwErAnnotationOverlay .ww-annotation[data-er-annotation-id="${id}"]`);

test.describe("Event Reconstruction annotations -- Waveform's toolset", () => {
  test("Annotate menu, guidance and Annotations manager are Waveform's; ER-specific Fit Record is an icon tool", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await openEventReconstruction(page);
    // Nothing plotted: nothing to annotate.
    await expect(page.locator("#wwErAnnotateBtn")).toBeDisabled();
    await plotAB(page);
    await expect(page.locator("#wwErAnnotateBtn")).toBeEnabled();
    // Compact icon controls with Waveform's names (no text "Annotate").
    for (const id of ["wwErAnnotateBtn", "wwErAnnotationListBtn", "wwErFitRecordBtn"]) {
      expect((await page.locator(`#${id}`).innerText()).trim()).toMatch(/^\d*$/);
    }
    await expect(page.locator("#wwErAnnotateBtn")).toHaveAttribute("title", "Annotate");
    await expect(page.locator("#wwErAnnotationListBtn")).toHaveAttribute("aria-label", "Annotations");
    await expect(page.locator("#wwErFitRecordBtn")).toHaveAttribute("aria-label", "Fit selected record");
    await page.locator("#wwErAnnotateBtn").click();
    await expect(page.locator("#wwErAnnotateMenu .ww-split-menu-item")).toHaveText(["Text Note", "Callout", "Maximum Peak (+Peak)", "Minimum Peak (-Peak)"]);
    await page.keyboard.press("Escape");
    await expect(page.locator("#wwErAnnotateMenu")).toBeHidden();
    // Waveform's own guidance text per tool; Esc cancels.
    for (const type of ["text_note", "callout", "peak_max", "peak_min"]) {
      await chooseTool(page, type);
      const message = await page.evaluate((t) => wwAnnotationPlacementGuidance(t).message, type);
      await expect(page.locator("#wwErAnnotationGuidanceText")).toHaveText(message + " Press Esc to cancel.");
      await expect(page.locator(`#wwErAnnotateMenu [data-annotation-type="${type}"]`)).toHaveAttribute("aria-pressed", "true");
      await page.keyboard.press("Escape");
      await expect(page.locator("#wwErAnnotationGuidance")).toBeHidden();
    }
    // The manager opens and closes like Waveform's.
    await page.locator("#wwErAnnotationListBtn").click();
    await expect(page.locator("#wwErAnnotationDrawer")).toHaveClass(/ww-annotation-drawer--open/);
    await expect(page.locator("#wwErAnnotationListBody")).toHaveText("No annotations yet.");
    await page.keyboard.press("Escape");
    await expect(page.locator("#wwErAnnotationDrawer")).not.toHaveClass(/ww-annotation-drawer--open/);
    // DEC-140/DEC-143: Grouped/Combined, Elapsed/Relative/Absolute and
    // Unit Mode (ENG/PU) are all global icon families now -- Unit Mode's
    // own text-control exception (section 13) was superseded once the
    // owner supplied dedicated engineering_unit.svg/per_unit.svg assets.
    await expect(page.locator("#wwErViewGroupedBtn")).toHaveAttribute("title", "Grouped Measurement View");
    await expect(page.locator("#wwErTimeAbsoluteBtn")).toHaveAttribute("title", "Absolute Time");
    await expect(page.locator("#wwErUnitEngineeringBtn")).toHaveAttribute("title", "Engineering Units");
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction annotations -- each type", () => {
  test("Text Note: placed in a panel, edited in place, moved, Grouped/Combined, Relative/Absolute, persisted, deleted", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await plotAB(page);
    const viewportBefore = (await plotState(page)).viewport;

    // Create on the LOWER panel (Active Power) -> straight into editing.
    await chooseTool(page, "text_note");
    const capture = page.locator("#wwErPanels .ww-er-panel").nth(1).locator(".ww-er-annotation-capture");
    await expect(capture).toBeVisible();
    const cap = await capture.boundingBox();
    const plotRect = await page.evaluate(() => {
      const fl = wwErState.plot.panels[1].chartEl._fullLayout;
      const rect = wwErState.plot.panels[1].chartEl.getBoundingClientRect();
      return { top: rect.top + fl._size.t, height: fl._size.h };
    });
    const clickX = cap.x + cap.width * 0.4;
    const clickY = plotRect.top + plotRect.height * 0.25;
    const expectedR = await page.evaluate((x) => {
      const plot = wwErState.plot;
      return wwPageXToTime(plot.viewport, wwPlotMetricsForChart(plot.panels[1].chartEl), x);
    }, clickX);
    await page.mouse.click(clickX, clickY);
    await expect.poll(async () => (await byType(page, "text_note")).length).toBe(1);
    await expect(page.locator("#wwErAnnotationGuidance")).toBeHidden(); // one placement
    const textarea = page.locator("#wwErAnnotationOverlay .ww-annotation-textarea");
    await expect(textarea).toBeFocused();
    await textarea.fill("Fault inception\nphase A");
    await page.locator("#wwErCanvasMeta").click(); // blur commits (Waveform)
    await expect.poll(async () => (await byType(page, "text_note"))[0].text).toBe("Fault inception\nphase A");
    const [note] = await byType(page, "text_note");
    expect(note.reconstruction_time_s).toBeCloseTo(expectedR, 6);
    expect(note.y_fraction).toBeCloseTo(0.25, 2);
    expect(note.axis_key).toBe("axis:Active Power|MW"); // its Grouped panel's display axis
    let d = await expectPlaced(page, note.annotation_id);
    expect(d.header).toBe("Note");
    expect(d.body).toBe("Fault inception\nphase A");

    // Double-click edits; Esc cancels, blur commits.
    await box(page, note.annotation_id).locator(".ww-annotation-body").dblclick();
    await textarea.fill("discarded");
    await textarea.press("Escape");
    await expect(textarea).toHaveCount(0);
    await box(page, note.annotation_id).locator(".ww-annotation-body").dblclick();
    await textarea.fill("Breaker opened");
    await page.locator("#wwErCanvasMeta").click();
    await expect.poll(async () => (await byType(page, "text_note"))[0].text).toBe("Breaker opened");

    // Move by its header: the stored position follows the box.
    const beforeMove = await findDrawn(page, note.annotation_id);
    await dragBy(page, box(page, note.annotation_id).locator(".ww-annotation-header"), 60, 20);
    await expect.poll(async () => (await byType(page, "text_note"))[0].reconstruction_time_s).not.toBe(note.reconstruction_time_s);
    d = await expectPlaced(page, note.annotation_id);
    expect(d.left).toBeCloseTo(beforeMove.left + 60, 0);
    expect(d.top).toBeCloseTo(beforeMove.top + 20, 0);
    expect((await plotState(page)).viewport).toEqual(viewportBefore);

    // Relative -> Absolute: the manager's time text only.
    await page.locator("#wwErAnnotationListBtn").click();
    const meta = page.locator("#wwErAnnotationListBody .ww-annotation-list-item-meta");
    const moved = (await byType(page, "text_note"))[0].reconstruction_time_s;
    await expect(meta).toHaveText(`t = +${moved.toFixed(6)} s`);
    await page.locator("#wwErTimeAbsoluteBtn").click();
    await expect(meta).toHaveText(/^t = 6 Mar 2026 10:00:0\d\.\d{6}$/);
    expect((await byType(page, "text_note"))[0].reconstruction_time_s).toBe(moved);
    await expectPlaced(page, note.annotation_id);
    await page.locator("#wwErTimeRelativeBtn").click();
    await page.keyboard.press("Escape");

    // Combined: on the one panel, same time; back to Grouped: its panel.
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    await expectPlaced(page, note.annotation_id);
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    await expectPlaced(page, note.annotation_id);

    // Persisted with the reconstruction (backend).
    await page.reload();
    await openEventReconstruction(page);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "P");
    await selectChannel(page, "STN_B", "P");
    await waitForPlot(page, 3);
    d = await expectPlaced(page, note.annotation_id);
    expect(d.body).toBe("Breaker opened");

    // Delete from the manager (Waveform: deletion lives there).
    await page.locator("#wwErAnnotationListBtn").click();
    await page.locator("#wwErAnnotationListBody .ww-annotation-delete-btn").click();
    await expect.poll(async () => (await definitionAnnotations(page)).length).toBe(0);
    await expect(page.locator("#wwErAnnotationOverlay .ww-annotation")).toHaveCount(0);
    expect(consoleErrors).toEqual([]);
  });

  test("Callout: on the clicked trace's real sample and its own Y axis (Grouped, Combined); box and anchor drags", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await plotAB(page);
    const recordB = await recordIdOf(page, "STN_B");
    const sourceB = await sourceIdFor(page, "STN_B");

    // Click STN_B's P (60 sin) where it differs from every other trace.
    await chooseTool(page, "callout");
    const point = await tracePoint(page, "STN_B", "P", 2.3);
    await page.mouse.click(point.x, point.y);
    await expect.poll(async () => (await byType(page, "callout")).length).toBe(1);
    await expect(page.locator("#wwErAnnotationGuidance")).toBeHidden(); // one-shot
    const [callout] = await byType(page, "callout");
    expect(callout.channel).toEqual({ record_id: recordB, source_id: sourceB, channel_name: "P" });
    // The backend's nearest REAL sample of that channel, in its own time.
    expect(callout.anchor.source_elapsed_s).toBeCloseTo(callout.anchor.sample_index / 1000, 9);
    expect(Math.abs(callout.anchor.source_elapsed_s + 1 - point.r)).toBeLessThan(0.02);
    const t = callout.anchor.sample_index / 1000;
    expect(callout.anchor.value).toBeCloseTo(Math.round(Math.sin(Math.PI * t) * 30000) * 60 / 30000, 3);
    expect(callout.anchor.unit).toBe("MW");
    expect(callout.box_offset).toEqual({ x: 80, y: -60 });
    // Opened for text immediately.
    const textarea = page.locator("#wwErAnnotationOverlay .ww-annotation-textarea");
    await expect(textarea).toBeFocused();
    await textarea.fill("Power swing");
    await page.locator("#wwErCanvasMeta").click();
    await expect.poll(async () => (await byType(page, "callout"))[0].text).toBe("Power swing");
    let d = await expectPlaced(page, callout.annotation_id);
    expect(d.header).toBe("Callout");

    // Combined: the same sample on P's own (second) axis.
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    d = await expectPlaced(page, callout.annotation_id);
    expect(d.expected.yaxis).not.toBe("y");
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    d = await expectPlaced(page, callout.annotation_id);
    expect(d.expected.yaxis).toBe("y");

    // Box drag: the offset only; the anchor stays.
    await dragBy(page, box(page, callout.annotation_id).locator(".ww-annotation-header"), 30, 10);
    await expect.poll(async () => (await byType(page, "callout"))[0].box_offset.x).toBeCloseTo(110, 0);
    let stored = (await byType(page, "callout"))[0];
    expect(stored.box_offset.y).toBeCloseTo(-50, 0);
    expect(stored.anchor).toEqual(callout.anchor);
    await expectPlaced(page, callout.annotation_id);

    // Anchor drag: along its OWN channel, re-resolved on release.
    const hit = page.locator(`#wwErCalloutConnectorLayer [data-callout-anchor-hit="${callout.annotation_id}"]`);
    const hitBox = await hit.boundingBox();
    const targetR = await page.evaluate((x) => {
      const plot = wwErState.plot;
      return wwPageXToTime(plot.viewport, wwPlotMetricsForChart(plot.panels[1].chartEl), x);
    }, hitBox.x + hitBox.width / 2 + 100);
    await dragBy(page, hit, 100, -40);
    await expect.poll(async () => (await byType(page, "callout"))[0].anchor.sample_index).not.toBe(callout.anchor.sample_index);
    stored = (await byType(page, "callout"))[0];
    expect(stored.channel).toEqual(callout.channel);
    expect(Math.abs(stored.anchor.source_elapsed_s + 1 - targetR)).toBeLessThan(0.002);
    const t2 = stored.anchor.sample_index / 1000;
    expect(stored.anchor.value).toBeCloseTo(Math.round(Math.sin(Math.PI * t2) * 30000) * 60 / 30000, 3);
    expect(stored.text).toBe("Power swing");
    await expectPlaced(page, callout.annotation_id);

    // Its channel no longer plotted: hidden, kept (listed in the manager).
    const rowB = await channelRow(page, "STN_B", "P");
    await rowB.click();
    await expect(rowB).toHaveAttribute("aria-pressed", "false");
    await waitForPlot(page, 2);
    await expect.poll(async () => (await findDrawn(page, callout.annotation_id)).visible).toBe(false);
    expect((await byType(page, "callout")).length).toBe(1);
    await page.locator("#wwErAnnotationListBtn").click();
    await expect(page.locator("#wwErAnnotationListBody .ww-annotation-list-item-preview")).toHaveText(["Power swing"]);
    expect(consoleErrors).toEqual([]);
  });

  test("Maximum / Minimum Peak: the targeted channel only (native and calculated), over the visible range, live", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    const sourceB = await sourceIdFor(page, "STN_B");
    const calc = await (await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-P", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceB, channel_name: "P" }], parameters: {} },
    })).json();
    await plotAB(page);
    await selectChannel(page, "STN_B", "-P");
    await waitForPlot(page, 4);
    // r 1.2..2.0 = STN_B's own 0.2..1.0 s (it starts 1 s later).
    await zoomTo(page, 1.2, 2.0, 1);

    // +Peak on STN_B P: 60 MW at its 0.5 s sample = r 1.5 (STN_A's P
    // would be 0 at r 2.0 -- the click picks the channel, not the panel).
    // The quantized sine is flat (30000 counts) over samples 499..501; the
    // first maximum wins (the backend's peak rule), so sample 499.
    await chooseTool(page, "peak_max");
    let point = await tracePoint(page, "STN_B", "P", 1.75);
    await page.mouse.click(point.x, point.y);
    await expect.poll(async () => (await byType(page, "peak_max")).length).toBe(1);
    await expect(page.locator("#wwErAnnotationGuidance")).toBeHidden();
    const [max] = await byType(page, "peak_max");
    expect(max.channel.source_id).toBe(sourceB);
    expect(max.channel.channel_name).toBe("P");
    expect(max.text).toBe("");
    let d = await expectPlaced(page, max.annotation_id);
    expect(d.peak).toMatchObject({ available: true, sampleIndex: 499, unit: "MW" });
    expect(d.peak.sourceElapsed).toBeCloseTo(0.499, 9);
    expect(d.peak.value).toBeCloseTo(60, 9);
    expect(d.expected.r).toBeCloseTo(1.499, 9);
    expect(d.header).toBe("+Peak");
    expect(d.valueLine).toBe(await page.evaluate(() => "+Peak: " + wwFormatEngineeringValue(60) + " MW"));
    expect(d.timeLine).toBe("t = +1.499000 s");

    // -Peak on the CALCULATED -P (timing parent STN_B): -60 at r 1.5.
    await chooseTool(page, "peak_min");
    point = await tracePoint(page, "STN_B", "-P", 1.75);
    await page.mouse.click(point.x, point.y);
    await expect.poll(async () => (await byType(page, "peak_min")).length).toBe(1);
    const [min] = await byType(page, "peak_min");
    expect(min.channel.source_id).toBe(calc.id);
    d = await expectPlaced(page, min.annotation_id);
    expect(d.peak.value).toBeCloseTo(-60, 9);
    expect(d.expected.r).toBeCloseTo(1.499, 9);

    // The visible range changes -> recalculated: r 2.2..4.0 = 1.2..3.0 s.
    await zoomTo(page, 2.2, 4.0, 1);
    await expect.poll(async () => (await findDrawn(page, max.annotation_id)).peak.sampleIndex).toBe(2499);
    d = await expectPlaced(page, max.annotation_id);
    expect(d.expected.r).toBeCloseTo(3.499, 9);
    await expect.poll(async () => (await findDrawn(page, min.annotation_id)).peak.sampleIndex).toBe(2499);

    // A range STN_B does not cover: unavailable, hidden, still listed.
    await zoomTo(page, 0.1, 0.8, 1);
    await expect.poll(async () => (await findDrawn(page, max.annotation_id)).peak.available).toBe(false);
    expect((await findDrawn(page, max.annotation_id)).visible).toBe(false);
    await page.locator("#wwErAnnotationListBtn").click();
    await expect(page.locator("#wwErAnnotationListBody .ww-annotation-list-item")).toHaveCount(2);
    await expect(page.locator("#wwErAnnotationListBody .ww-annotation-list-item-category")).toHaveText(["-PEAK", "+PEAK"]); // newest first
    await expect(page.locator("#wwErAnnotationListBody .ww-annotation-list-item-preview").nth(1)).toHaveText("+Peak: Unavailable for current view");
    await expect(page.locator("#wwErAnnotationListBody .ww-annotation-list-item-meta").nth(1)).toContainText("Unavailable for current view");

    // Grouped and Combined: on the trace's own Y axis.
    await page.keyboard.press("Escape");
    await zoomTo(page, 1.2, 2.0, 1);
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 4);
    await expect.poll(async () => (await findDrawn(page, max.annotation_id)).peak.sampleIndex).toBe(499);
    await expectPlaced(page, max.annotation_id);
    await expectPlaced(page, min.annotation_id);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction annotations -- timing model", () => {
  test("Text Notes keep their instant through reference changes; Callouts/Peaks follow their record's corrections", async ({ page }) => {
    await setup(page);
    await plotAB(page);
    const records = { a: await recordIdOf(page, "STN_A"), b: await recordIdOf(page, "STN_B") };
    const sources = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B") };
    await zoomTo(page, 1.2, 2.0);
    const note = await createViaApi(page, { type: "text_note", reconstruction_time_s: 1.8, y_fraction: 0.2, text: "Fault inception" });
    const calloutB = await createViaApi(page, {
      type: "callout", channel: { record_id: records.b, source_id: sources.b, channel_name: "P" },
      anchor: { sample_index: 600, source_elapsed_s: 0.6, value: 57.063, unit: "MW" }, text: "B",
    });
    const calloutA = await createViaApi(page, {
      type: "callout", channel: { record_id: records.a, source_id: sources.a, channel_name: "P" },
      anchor: { sample_index: 1700, source_elapsed_s: 1.7, value: -64.721, unit: "MW" }, text: "A",
    });
    const peak = await createViaApi(page, { type: "peak_max", channel: { record_id: records.b, source_id: sources.b, channel_name: "P" } });
    // (First of the flat 499..501 maximum; see the Peak test.)
    await expect.poll(async () => ((await findDrawn(page, peak.annotation_id)).peak || {}).sampleIndex).toBe(499);
    await page.locator("#wwErTimeAbsoluteBtn").click();
    const absolute = async () => Object.fromEntries(await Promise.all(
      [["note", note], ["b", calloutB], ["a", calloutA], ["peak", peak]].map(async ([k, a]) => [k, await timeText(page, a.annotation_id)])));
    expect(await absolute()).toEqual({
      note: "6 Mar 2026 10:00:01.800000", b: "6 Mar 2026 10:00:01.600000", a: "6 Mar 2026 10:00:01.700000", peak: "6 Mar 2026 10:00:01.499000",
    });
    const all = async () => { for (const a of [note, calloutB, calloutA, peak]) await expectPlaced(page, a.annotation_id); };
    await all();

    // Reference switch to STN_B: every physical instant kept; the note's
    // stored reconstruction time is rebased by the frame shift (-1 s).
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await byType(page, "text_note"))[0].reconstruction_time_s).toBeCloseTo(0.8, 9);
    await waitForPlot(page, 3);
    await expect.poll(absolute).toEqual({
      note: "6 Mar 2026 10:00:01.800000", b: "6 Mar 2026 10:00:01.600000", a: "6 Mar 2026 10:00:01.700000", peak: "6 Mar 2026 10:00:01.499000",
    });
    await all();

    // Reference correction +5 ms (STN_B): the note keeps its instant; STN_B's
    // own Callout/Peak samples are now 5 ms later; STN_A's are not.
    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("5");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(absolute).toEqual({
      note: "6 Mar 2026 10:00:01.800000", b: "6 Mar 2026 10:00:01.605000", a: "6 Mar 2026 10:00:01.700000", peak: "6 Mar 2026 10:00:01.504000",
    });
    await waitForPlot(page, 3);
    await all();

    // Non-reference correction +15 ms (STN_A): the note stays fixed in
    // reconstruction time; STN_A's Callout follows its record.
    const noteR = (await byType(page, "text_note"))[0].reconstruction_time_s;
    await memberRow(page, "STN_A").locator("input[data-er-correction-input]").fill("15");
    await memberRow(page, "STN_A").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(absolute).toEqual({
      note: "6 Mar 2026 10:00:01.800000", b: "6 Mar 2026 10:00:01.605000", a: "6 Mar 2026 10:00:01.715000", peak: "6 Mar 2026 10:00:01.504000",
    });
    expect((await byType(page, "text_note"))[0].reconstruction_time_s).toBe(noteR);
    // Channel-attached annotations store source samples, never a time.
    for (const a of await definitionAnnotations(page)) if (a.type !== "text_note") expect(a.reconstruction_time_s).toBeNull();
    await waitForPlot(page, 3);
    await all();

    // Persisted (backend); the same four after a reload.
    await page.reload();
    await openEventReconstruction(page);
    expect((await definitionAnnotations(page)).map((a) => a.type)).toEqual(["text_note", "callout", "callout", "peak_max"]);
  });
});

test.describe("Event Reconstruction annotations -- manager and independence", () => {
  test("the manager lists, focuses, edits and deletes Event Reconstruction annotations only; Waveform's are untouched", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    // Waveform: a note through Waveform's own annotation API.
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    await page.evaluate(() => wwCreateAnnotation("text_note", "main", { x: 40, y: 40 }, { text: "Waveform note" }));
    const waveform = () => page.evaluate(() => ({
      annotations: JSON.stringify(Array.from(ww.annotations.values()).map((a) => [a.id, a.type, a.data])),
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
      dragMode: ww.dragMode,
      panels: ww.panels.map((p) => p.groupKey),
      placement: ww.annotationPlacementType || null,
      listItems: document.querySelectorAll("#wwAnnotationListBody .ww-annotation-list-item").length,
    }));
    await page.waitForTimeout(300);
    const before = await waveform();
    const groupsBefore = await api(page, "/synchronization/time-groups");

    await plotAB(page);
    expect(await definitionAnnotations(page)).toEqual([]);
    const records = { b: await recordIdOf(page, "STN_B") };
    const sourceB = await sourceIdFor(page, "STN_B");
    const note = await createViaApi(page, { type: "text_note", reconstruction_time_s: 1.0, y_fraction: 0.3, text: "Fault" });
    const callout = await createViaApi(page, {
      type: "callout", channel: { record_id: records.b, source_id: sourceB, channel_name: "P" },
      anchor: { sample_index: 1500, source_elapsed_s: 1.5, value: -60, unit: "MW" }, text: "Swing",
    });
    // ER placement uses its own state; Waveform's is never set.
    await chooseTool(page, "callout");
    expect((await waveform()).placement).toBeNull();
    await page.keyboard.press("Escape");

    // Manager: ER annotations only, newest first, Waveform's row pattern.
    await page.locator("#wwErAnnotationListBtn").click();
    await expect(page.locator("#wwErAnnotationCountBadge")).toHaveText("2");
    const rows = page.locator("#wwErAnnotationListBody .ww-annotation-list-item");
    await expect(rows.locator(".ww-annotation-list-item-category")).toHaveText(["CALLOUT", "NOTE"]);
    await expect(rows.locator(".ww-annotation-list-item-preview")).toHaveText(["Swing", "Fault"]);
    await expect(rows.nth(0).locator(".ww-annotation-list-item-meta")).toHaveText(
      `STN_B · P · +${(1.5 + 1).toFixed(6)} s · ${(-60).toFixed(3)} MW`);
    await expect(rows.nth(1).locator(".ww-annotation-list-item-meta")).toHaveText("t = +1.000000 s");
    // Select / focus.
    await rows.nth(1).click();
    await expect(box(page, note.annotation_id)).toHaveClass(/ww-annotation--selected/);
    await expect(rows.nth(1)).toHaveClass(/ww-annotation-list-item--selected/);
    // Edit in place (the drawer closed: it covers the right of the plot);
    // the list follows.
    await page.locator("#wwErAnnotationDrawerCloseBtn").click();
    await box(page, callout.annotation_id).locator(".ww-annotation-body").dblclick();
    await page.locator("#wwErAnnotationOverlay .ww-annotation-textarea").fill("Power swing");
    await page.locator("#wwErCanvasMeta").click();
    await page.locator("#wwErAnnotationListBtn").click();
    await expect(rows.locator(".ww-annotation-list-item-preview")).toHaveText(["Power swing", "Fault"]);
    // Delete.
    await rows.nth(1).locator(".ww-annotation-delete-btn").click();
    await expect.poll(async () => (await definitionAnnotations(page)).map((a) => a.annotation_id)).toEqual([callout.annotation_id]);
    await expect(box(page, note.annotation_id)).toHaveCount(0);

    // Waveform untouched; never drawn on Waveform's overlay.
    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    await expect(page.locator("#workspaceRow [data-er-annotation-id]")).toHaveCount(0);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    await page.evaluate(() => { for (const id of Array.from(ww.annotations.keys())) wwDeleteAnnotation(id); });
    expect((await definitionAnnotations(page)).map((a) => a.text)).toEqual(["Power swing"]);
    // Clearing the reconstruction removes its annotations only.
    await page.evaluate(() => wwCreateAnnotation("text_note", "main", { x: 40, y: 40 }, { text: "Waveform note 2" }));
    const resp = await page.request.delete(await erUrl(page, "/definition"));
    expect(resp.status()).toBe(204);
    expect(await page.evaluate(() => Array.from(ww.annotations.values()).map((a) => a.data.text))).toEqual(["Waveform note 2"]);
    expect(consoleErrors).toEqual([]);
  });
});
