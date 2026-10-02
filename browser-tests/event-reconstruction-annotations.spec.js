// Event Reconstruction annotations (DEC-136): the reconstruction's own
// event markers -- backend-owned, in reconstruction seconds, rebased with
// the reference frame, independent of Waveform annotations. Drawn on every
// panel (label on the top one), Grouped and Combined alike; Relative /
// Absolute changes only their time text.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, api, addRecords, selectChannel,
  waitForPlot, plotState, zoomTo, dragOnPanel, openEventReconstruction,
} = require("./support/event_reconstruction_helpers");

const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
];

const erUrl = async (page, path) => `${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/event-reconstruction${path}`;
async function createViaApi(page, r, text) {
  const resp = await page.request.post(await erUrl(page, "/definition/annotations"), { data: { reconstruction_time_s: r, text } });
  expect(resp.status()).toBe(201);
  await page.evaluate(() => wwErRefresh());
  return (await resp.json()).annotations.find((a) => a.text === text);
}
const definitionAnnotations = async (page) => (await api(page, "/event-reconstruction/definition")).annotations;

// Every drawn marker, per panel, with where Plotly itself draws its time.
const markers = (page) => page.evaluate(() => {
  const plot = wwErState.plot;
  return plot.panels.map((p) => {
    const xa = p.chartEl._fullLayout.xaxis;
    const chartLeft = p.chartEl.getBoundingClientRect().left - p.chartWrapEl.getBoundingClientRect().left;
    return Array.from(p.annotationLayerEl.querySelectorAll(".ww-er-annotation")).map((el) => {
      const annotation = wwErAnnotations().find((a) => a.annotation_id === el.dataset.erAnnotationId);
      const label = el.querySelector(".ww-er-annotation-label");
      return {
        id: el.dataset.erAnnotationId,
        left: parseFloat(el.style.left),
        plotlyX: chartLeft + xa._offset + xa.l2p(annotation.reconstruction_time_s - plot.origin),
        label: label ? label.textContent : null,
        labelTop: label ? parseFloat(label.style.top) : null,
        title: el.querySelector(".ww-cursor-hit").title,
      };
    });
  });
});

async function expectAligned(page) {
  for (const panel of await markers(page)) for (const marker of panel) expect(marker.left).toBeCloseTo(marker.plotlyX, 0);
}

async function placeAt(page, panelIndex, fraction) {
  await page.locator("#wwErAnnotateBtn").click();
  await expect(page.locator("#wwErAnnotationHint")).toBeVisible();
  const capture = page.locator("#wwErPanels .ww-er-panel").nth(panelIndex).locator(".ww-er-annotation-capture");
  const box = await capture.boundingBox();
  const x = box.x + box.width * fraction;
  const expected = await page.evaluate(({ panelIndex, x }) => {
    const plot = wwErState.plot;
    return wwErClampCursorTime(plot.fitAll, wwPageXToTime(plot.viewport, wwPlotMetricsForChart(plot.panels[panelIndex].chartEl), x));
  }, { panelIndex, x });
  await page.mouse.click(x, box.y + box.height / 2);
  await expect(page.locator("#wwErAnnotationEditor")).toBeVisible();
  return expected;
}

async function setup(page, channels = MIXED) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4, channels });
  await addRecords(page, ["STN_A", "STN_B"]);
  await selectChannel(page, "STN_A", "VA");
  await selectChannel(page, "STN_A", "P");
  await selectChannel(page, "STN_B", "VA");
  await waitForPlot(page, 3);
}

test.describe("Event Reconstruction annotations -- create, edit, move, delete", () => {
  test("placed in reconstruction time, drawn on every panel, edited, moved and deleted; Relative/Absolute only relabels", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await setup(page);
    await page.locator("#wwErCursorModeBtn").click();
    const cursors = () => page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time]);
    const cursorsBefore = await cursors();
    const viewportBefore = (await plotState(page)).viewport;

    // Create: Annotate -> click -> label -> Enter.
    const placed = await placeAt(page, 0, 0.4);
    await expect(page.locator("#wwErAnnotationEditorTime")).toHaveText(await page.evaluate((r) => wwErAnnotationTimeText(r), placed));
    await page.locator("#wwErAnnotationEditorText").fill("Fault inception");
    await page.keyboard.press("Enter");
    await expect.poll(async () => (await definitionAnnotations(page)).length).toBe(1);
    let [annotation] = await definitionAnnotations(page);
    expect(annotation.text).toBe("Fault inception");
    expect(annotation.reconstruction_time_s).toBeCloseTo(placed, 9);
    await expect(page.locator("#wwErAnnotationHint")).toBeHidden(); // one placement
    // Every panel draws it at the same time; the label on the top panel only.
    let drawn = await markers(page);
    expect(drawn.map((panel) => panel.length)).toEqual([1, 1]);
    expect(drawn.map((panel) => panel[0].label)).toEqual(["Fault inception", null]);
    await expectAligned(page);
    expect(drawn[0][0].title).toBe(`Fault inception — +${annotation.reconstruction_time_s.toFixed(6)} s (drag to move, click to edit)`);

    // Relative -> Absolute: same time, only the text changes.
    await page.locator("#wwErTimeAbsoluteBtn").click();
    drawn = await markers(page);
    const absolute = await page.evaluate((r) => wwErAnnotationTimeText(r), annotation.reconstruction_time_s);
    expect(absolute).toMatch(/^6 Mar 2026 10:00:0\d\.\d{6}$/);
    expect(drawn[0][0].title).toBe(`Fault inception — ${absolute} (drag to move, click to edit)`);
    expect((await definitionAnnotations(page))[0].reconstruction_time_s).toBe(annotation.reconstruction_time_s);
    await expectAligned(page);
    await page.locator("#wwErTimeRelativeBtn").click();
    expect((await markers(page))[0][0].title).toContain(`+${annotation.reconstruction_time_s.toFixed(6)} s`);

    // Edit the label.
    await page.locator("#wwErPanels .ww-er-annotation-label").click();
    await expect(page.locator("#wwErAnnotationEditorTitle")).toHaveText("Event marker");
    await page.locator("#wwErAnnotationEditorText").fill("Breaker opened");
    await page.locator("#wwErAnnotationSaveBtn").click();
    await expect.poll(async () => (await definitionAnnotations(page))[0].text).toBe("Breaker opened");
    expect((await definitionAnnotations(page))[0].reconstruction_time_s).toBe(annotation.reconstruction_time_s);

    // Move: drag its strip on the LOWER panel 80 px right.
    const handle = page.locator("#wwErPanels .ww-er-panel").nth(1).locator("[data-er-annotation-drag]");
    const box = await handle.boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    const expected = await page.evaluate((pageX) => {
      const plot = wwErState.plot;
      return wwPageXToTime(plot.viewport, wwPlotMetricsForChart(plot.panels[1].chartEl), pageX);
    }, x + 80);
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + 40, y, { steps: 4 });
    await page.mouse.move(x + 80, y, { steps: 4 });
    await page.mouse.up();
    await expect.poll(async () => (await definitionAnnotations(page))[0].reconstruction_time_s).toBeCloseTo(expected, 6);
    await expect(page.locator("#wwErAnnotationEditor")).toBeHidden(); // a drag is not a click
    await expectAligned(page);
    // X, cursors untouched by create/edit/move.
    expect((await plotState(page)).viewport).toEqual(viewportBefore);
    expect(await cursors()).toEqual(cursorsBefore);

    // Combined: one marker with its label, same time; back to Grouped.
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    drawn = await markers(page);
    expect(drawn.map((panel) => panel.map((m) => m.label))).toEqual([["Breaker opened"]]);
    await expectAligned(page);
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    expect((await markers(page)).map((panel) => panel.length)).toEqual([1, 1]);

    // Persisted with the reconstruction (backend): after a page reload the
    // marker is still there; the channel selection (frontend) is chosen again.
    await page.reload();
    await openEventReconstruction(page);
    expect((await definitionAnnotations(page)).map((a) => a.text)).toEqual(["Breaker opened"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_A", "P");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 3);
    await expect.poll(async () => (await markers(page))[0].map((m) => m.label)).toEqual(["Breaker opened"]);

    // Delete.
    await page.locator("#wwErPanels .ww-er-annotation-label").click();
    await page.locator("#wwErAnnotationDeleteBtn").click();
    await expect.poll(async () => (await definitionAnnotations(page)).length).toBe(0);
    expect((await markers(page)).map((panel) => panel.length)).toEqual([0, 0]);
    expect(consoleErrors).toEqual([]);
  });

  test("Esc cancels placement; close labels stay visible on separate rows", async ({ page }) => {
    await setup(page);
    await page.locator("#wwErAnnotateBtn").click();
    await expect(page.locator("#wwErAnnotateBtn")).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Escape");
    await expect(page.locator("#wwErAnnotateBtn")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("#wwErPanels .ww-er-annotation-capture").first()).toBeHidden();
    for (const [r, text] of [[2.0, "Fault inception"], [2.01, "Protection operated"], [2.02, "Breaker opened"]]) await createViaApi(page, r, text);
    await expect.poll(async () => (await markers(page))[0].length).toBe(3);
    const labels = (await markers(page))[0];
    expect(labels.map((m) => m.label)).toEqual(["Fault inception", "Protection operated", "Breaker opened"]);
    expect(new Set(labels.map((m) => m.labelTop)).size).toBe(3); // none hidden, none overlapping
  });
});

test.describe("Event Reconstruction annotations -- reconstruction frame", () => {
  test("a reference switch and a reference correction keep the physical instant; a non-reference correction leaves the marker", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:18.425000", durationS: 3 });
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:19.500000", durationS: 2 });
    const ids = { b: await sourceIdFor(page, "STN_B"), c: await sourceIdFor(page, "STN_C") };
    await addRecords(page, ["STN_A", "STN_B", "STN_C"]);
    for (const station of ["STN_A", "STN_B", "STN_C"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await createViaApi(page, 20.0, "Fault inception");
    await page.locator("#wwErTimeAbsoluteBtn").click();
    const absoluteText = async () => page.evaluate(() => wwErAnnotationTimeText(wwErAnnotations()[0].reconstruction_time_s));
    expect(await absoluteText()).toBe("6 Mar 2026 10:00:20.000000");
    const r = async () => (await definitionAnnotations(page))[0].reconstruction_time_s;

    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(r).toBeCloseTo(20.0 - 18.425, 9);
    expect(await absoluteText()).toBe("6 Mar 2026 10:00:20.000000");
    await waitForPlot(page, 3);
    await expectAligned(page);

    // Reference correction +5 ms: rebased with the frame.
    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("5");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(r).toBeCloseTo(20.0 - 18.425 - 0.005, 9);
    // Non-reference correction +15 ms on STN_C: the marker stays; C moves under it.
    const before = await r();
    const cStart = async () => (await api(page, "/event-reconstruction/definition")).members.find((m) => m.record_id === ids.c).start_s;
    const c0 = await cStart();
    await memberRow(page, "STN_C").locator("input[data-er-correction-input]").fill("15");
    await memberRow(page, "STN_C").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(cStart).toBeCloseTo(c0 + 0.015, 9);
    expect(await r()).toBe(before);
    await waitForPlot(page, 3);
    await expectAligned(page);
  });

  test("navigation, Fit Record, Reset and Y-axis drag never move a marker", async ({ page }) => {
    await setup(page);
    const created = await createViaApi(page, 1.5, "Fault inception");
    const stored = async () => (await definitionAnnotations(page))[0].reconstruction_time_s;
    const check = async (what) => {
      expect(await stored(), what).toBe(created.reconstruction_time_s);
      const state = await plotState(page);
      const visible = created.reconstruction_time_s >= state.viewport.start && created.reconstruction_time_s <= state.viewport.end;
      expect((await markers(page))[0].length, what).toBe(visible ? 1 : 0);
      await expectAligned(page);
    };
    await dragOnPanel(page, 0, 0.2, 0.5, 40); // Box Zoom
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(false);
    await waitForPlot(page, 3);
    await check("box zoom");
    await page.locator("#wwErDragModePanBtn").click();
    await dragOnPanel(page, 0, 0.6, 0.3, 0); // Pan
    await waitForPlot(page, 3);
    await check("pan");
    await page.locator("#wwErZoomOutBtn").click();
    await waitForPlot(page, 3);
    await check("zoom out");
    await page.locator("#wwErZoomInBtn").click();
    await waitForPlot(page, 3);
    await check("zoom in");
    await memberRow(page, "STN_B").locator("[data-er-activate-record]").click();
    await page.locator("#wwErFitRecordBtn").click(); // STN_B: 1..5 s
    await waitForPlot(page, 3);
    await check("fit record");
    await zoomTo(page, 3, 4); // marker off-screen: hidden, kept
    await check("off-screen");
    const box = await page.locator('#wwErPanels .ww-er-panel').nth(0).locator('.draglayer .ndrag[data-subplot="xy"]').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 - 30, { steps: 5 });
    await page.mouse.up();
    await check("y-axis drag");
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    await waitForPlot(page, 3);
    await check("reset");
  });

  test("+2 h: the marker stays exact while the local plotting origin moves", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_REF", startClock: "10:00:00.000000", durationS: 1 });
    await uploadRecord(page, { station: "STN_FAR", startClock: "12:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_REF", "STN_FAR"]);
    await selectChannel(page, "STN_REF", "VA");
    await selectChannel(page, "STN_FAR", "VA");
    await waitForPlot(page, 2);
    await createViaApi(page, 7200.1003, "Trip");
    await zoomTo(page, 7200.1, 7200.1006); // 0.6 ms window: the origin moves near 7200 s
    const state = await plotState(page);
    expect(state.origin).toBeGreaterThan(7199);
    expect((await definitionAnnotations(page))[0].reconstruction_time_s).toBe(7200.1003);
    const [marker] = (await markers(page))[0];
    expect(marker.left).toBeCloseTo(marker.plotlyX, 1);
    // Halfway across the 0.6 ms window, to the pixel.
    const halfway = await page.evaluate(() => {
      const p = wwErState.plot.panels[0];
      const metrics = wwPlotMetricsForChart(p.chartEl);
      return metrics.plotLeftPage + metrics.plotWidth * 0.5 - p.chartWrapEl.getBoundingClientRect().left;
    });
    expect(marker.left).toBeCloseTo(halfway, 0);
  });
});

test.describe("Event Reconstruction annotations -- independence from Waveform", () => {
  test("Waveform and Event Reconstruction annotations never touch each other", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4, channels: MIXED });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    // A Waveform note, through Waveform's own annotation API.
    await page.evaluate(() => wwCreateAnnotation("text_note", "main", { x: 40, y: 40 }, { text: "Waveform note" }));
    const waveform = () => page.evaluate(() => ({
      annotations: JSON.stringify(Array.from(ww.annotations.values()).map((a) => [a.id, a.type, a.data])),
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
      dragMode: ww.dragMode,
      panels: ww.panels.map((p) => p.groupKey),
      presentation: JSON.stringify(Array.from(ww.channelPresentationOverrides.entries())),
    }));
    await page.waitForTimeout(300);
    const before = await waveform();
    const groupsBefore = await api(page, "/synchronization/time-groups");

    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    // The Waveform note is not an Event Reconstruction marker.
    expect(await definitionAnnotations(page)).toEqual([]);
    await placeAt(page, 0, 0.5);
    await page.locator("#wwErAnnotationEditorText").fill("Fault inception");
    await page.locator("#wwErAnnotationSaveBtn").click();
    await expect.poll(async () => (await definitionAnnotations(page)).length).toBe(1);
    await page.locator("#wwErPanels .ww-er-annotation-label").click();
    await page.locator("#wwErAnnotationEditorText").fill("Fault");
    await page.locator("#wwErAnnotationSaveBtn").click();
    await expect.poll(async () => (await definitionAnnotations(page))[0].text).toBe("Fault");
    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);

    // Back in Waveform: only its own note; deleting it leaves the ER marker.
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    await expect(page.locator(".ww-er-annotation-label")).toHaveCount(1); // only on the (hidden) ER page
    await expect(page.locator("#workspaceRow .ww-er-annotation")).toHaveCount(0);
    await page.evaluate(() => { for (const id of Array.from(ww.annotations.keys())) wwDeleteAnnotation(id); });
    expect(await definitionAnnotations(page)).toEqual([expect.objectContaining({ text: "Fault" })]);
    // Clearing the reconstruction removes its markers only.
    await page.evaluate(() => wwCreateAnnotation("text_note", "main", { x: 40, y: 40 }, { text: "Waveform note 2" }));
    const resp = await page.request.delete(await erUrl(page, "/definition"));
    expect(resp.status()).toBe(204);
    expect(await page.evaluate(() => Array.from(ww.annotations.values()).map((a) => a.data.text))).toEqual(["Waveform note 2"]);
    expect(consoleErrors).toEqual([]);
  });
});
