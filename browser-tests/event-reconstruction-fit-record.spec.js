// Event Reconstruction mixed-duration navigation -- Fit Record: an explicit
// active navigation record (a record identity, distinct from the
// reference), whose backend reconstruction extent becomes the common X
// viewport in Grouped and Combined alike. X only: Y, cursors, timing,
// corrections, reference, membership and channel selection are untouched;
// time is never compressed.

const { test, expect } = require("@playwright/test");
const {
  collectConsoleErrors, uploadRecord, sourceIdFor, memberRow, api,
  addRecords, selectChannel, waitForPlot, plotState, waitForSharedAxis, expectSharedAxis,
} = require("./support/event_reconstruction_helpers");

const VA = (amplitude = 100, frequencyHz = 50) => [{ name: "VA", unit: "V", phase: "A", amplitude, frequencyHz }];
const MIXED = [
  { name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 },
  { name: "P", unit: "MW", amplitude: 80, frequencyHz: 0.5 },
];

// Mixed sampling and duration: 1 Hz / 300 s, 20 Hz / 60 s, 5 kHz / 0.2 s.
async function uploadMixedDurations(page) {
  await uploadRecord(page, { station: "STN_LONG", startClock: "10:00:00.000000", rateHz: 1, durationS: 300, channels: VA(100, 0.01) });
  await uploadRecord(page, { station: "STN_MID", startClock: "10:01:00.000000", rateHz: 20, durationS: 60, channels: VA(200, 0.2) });
  await uploadRecord(page, { station: "STN_FAST", startClock: "10:02:30.000000", rateHz: 5000, durationS: 0.2, channels: VA(300, 50) });
}

const activeState = (page) => page.evaluate(() => ({
  active: wwErState.activeRecordId,
  reference: (wwErState.definition.members.find((m) => m.is_reference) || {}).record_id,
  members: wwErState.definition.members.map((m) => m.record_id),
  selected: Object.keys(wwErState.selectedChannels).sort(),
  rows: Array.from(document.querySelectorAll("#wwErMembersPanel .ww-er-member-row")).map((row) => ({
    recordId: row.dataset.recordId,
    active: row.classList.contains("ww-er-member-row--active"),
    pressed: (row.querySelector("[data-er-activate-record]") || { getAttribute: () => null }).getAttribute("aria-pressed"),
    marker: !row.querySelector(".ww-er-active-marker").hidden,
    reference: !!row.querySelector(".ww-er-badge--reference"),
  })),
  fitDisabled: document.getElementById("wwErFitRecordBtn").disabled,
  fitTitle: document.getElementById("wwErFitRecordBtn").title,
}));

// The backend's own reconstruction extent of a record (member start_s/end_s).
async function memberExtent(page, recordId) {
  const definition = await api(page, "/event-reconstruction/definition");
  const member = definition.members.find((m) => m.record_id === recordId);
  return { start: member.start_s, end: member.end_s };
}

async function activate(page, station) {
  await memberRow(page, station).locator("[data-er-activate-record]").click();
}

async function fitRecord(page, count) {
  await page.locator("#wwErFitRecordBtn").click();
  await waitForSharedAxis(page);
  await waitForPlot(page, count);
}

async function setCorrection(page, station, ms) {
  await memberRow(page, station).locator("input[data-er-correction-input]").fill(String(ms));
  await memberRow(page, station).locator('button[data-er-action="set-correction"]').click();
}

test.describe("Event Reconstruction Fit Record -- the active record", () => {
  test("starts as the reference, is chosen by a record header, and never follows reference, membership or channel selection", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000" });
    const ids = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B") };
    await addRecords(page, ["STN_A", "STN_B"]);
    // Initial: the reference record (STN_A, the first added).
    let state = await activeState(page);
    expect([state.active, state.reference]).toEqual([ids.a, ids.a]);
    expect(state.rows.map((r) => [r.active, r.marker, r.pressed])).toEqual([[true, true, "true"], [false, false, "false"]]);
    // Nothing plotted yet: Fit Record is unavailable and says why.
    expect(state.fitDisabled).toBe(true);
    expect(state.fitTitle).toContain("plot a channel of STN_A first");

    // Clicking STN_B's header makes it active -- not the reference, and the
    // membership and selection stay.
    await activate(page, "STN_B");
    state = await activeState(page);
    expect([state.active, state.reference, state.members]).toEqual([ids.b, ids.a, [ids.a, ids.b]]);
    expect(state.rows.map((r) => [r.active, r.marker, r.reference])).toEqual([[false, false, true], [true, true, false]]);
    expect(state.selected).toEqual([]);
    const definitionBefore = await api(page, "/event-reconstruction/definition");

    // Selecting a channel of STN_A does not move the active record.
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    state = await activeState(page);
    expect(state.active).toBe(ids.b);
    expect(state.fitDisabled).toBe(false);
    expect(state.fitTitle).toBe("Fit selected record — STN_B");
    // Keyboard: Enter on a header activates it too.
    await memberRow(page, "STN_A").locator("[data-er-activate-record]").focus();
    await page.keyboard.press("Enter");
    expect((await activeState(page)).active).toBe(ids.a);
    await activate(page, "STN_B");
    // The definition (reference, corrections, membership) was never written.
    expect(await api(page, "/event-reconstruction/definition")).toEqual(definitionBefore);

    // A reference switch keeps the active record.
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await activeState(page)).reference).toBe(ids.b);
    await memberRow(page, "STN_A").locator("[data-er-activate-record]").click();
    await memberRow(page, "STN_A").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await activeState(page)).reference).toBe(ids.a);
    expect((await activeState(page)).active).toBe(ids.a);

    // Removing the active record clears it -- no other record is chosen.
    await activate(page, "STN_B");
    await memberRow(page, "STN_B").locator('button[data-er-action="remove-member"]').click();
    await expect.poll(async () => (await activeState(page)).members).toEqual([ids.a]);
    state = await activeState(page);
    expect(state.active).toBe(null);
    expect(state.rows.map((r) => r.active)).toEqual([false]);
    expect(state.fitDisabled).toBe(true);
    expect(state.fitTitle).toContain("no active record");
    // Still none after a refresh; an explicit choice restores it.
    await page.evaluate(() => wwErRefresh());
    expect((await activeState(page)).active).toBe(null);
    await activate(page, "STN_A");
    expect((await activeState(page)).active).toBe(ids.a);
    expect(consoleErrors).toEqual([]);
  });

  test("identical-timestamp records stay separate fit targets", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_LONG", startClock: "09:59:58.000000", durationS: 6 });
    const ids = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B") };
    await addRecords(page, ["STN_LONG", "STN_A", "STN_B"]);
    for (const station of ["STN_LONG", "STN_A", "STN_B"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await activate(page, "STN_B");
    await fitRecord(page, 3);
    const state = await plotState(page);
    const extent = await memberExtent(page, ids.b);
    expect(await memberExtent(page, ids.a)).toEqual(extent);
    expect(state.viewport).toEqual(extent);
    expect((await activeState(page)).active).toBe(ids.b);
  });
});

test.describe("Event Reconstruction Fit Record -- mixed durations", () => {
  test("each record fills the plot: 5 kHz / 0.2 s, 20 Hz / 60 s, 1 Hz / 300 s; Grouped and Combined alike; X only", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadMixedDurations(page);
    const ids = { long: await sourceIdFor(page, "STN_LONG"), mid: await sourceIdFor(page, "STN_MID"), fast: await sourceIdFor(page, "STN_FAST") };
    await addRecords(page, ["STN_LONG", "STN_MID", "STN_FAST"]);
    // A fourth member whose channel is never plotted.
    await uploadRecord(page, { station: "STN_P", startClock: "10:00:00.000000", rateHz: 1, durationS: 300, channels: MIXED.slice(1) });
    await addRecords(page, ["STN_P"]);
    for (const station of ["STN_LONG", "STN_MID", "STN_FAST"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    let state = await plotState(page);
    expect(state.fitAll.start).toBeCloseTo(0, 9);
    expect(state.fitAll.end).toBeCloseTo(300, 6);
    // At Fit All the 0.2 s record is a sliver of the 300 s plot.
    const fastAtFitAll = state.panels.find((c) => c.label === "STN_FAST · VA");
    expect(fastAtFitAll.timingEndS - fastAtFitAll.timingStartS).toBeLessThan(0.001 * (state.fitAll.end - state.fitAll.start));
    const yBefore = state.groups.map((g) => g.yRange);

    // Cursors placed first; Fit Record never moves them.
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 40); wwErSetCursorTime("b", 150.1); });
    const cursorTimes = () => page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time]);
    const lineHidden = () => page.evaluate(() => ["a", "b"].map((k) =>
      wwErState.plot.panels[0].cursorLayerEl.querySelector('[data-er-cursor-line="' + k + '"]').hidden));

    const requests = [];
    page.on("request", (r) => { if (r.url().includes("/waveform")) requests.push(new URL(r.url())); });

    // 5 kHz / 0.2 s.
    await activate(page, "STN_FAST");
    await fitRecord(page, 3);
    state = await plotState(page);
    const fastExtent = await memberExtent(page, ids.fast);
    expect(state.viewport).toEqual(fastExtent);
    expect(fastExtent.start).toBeCloseTo(150, 6);
    expect(fastExtent.end - fastExtent.start).toBeCloseTo(0.2, 9);
    expect(state.atFitAll).toBe(false);
    expectSharedAxis(state);
    const fast = state.panels.find((c) => c.label === "STN_FAST · VA");
    expect(fast.representation).toBe("full_resolution");
    expect(fast.r.length).toBe(1001);
    for (let k = 1; k < fast.x.length; k++) expect(Math.fround(fast.x[k]) - Math.fround(fast.x[k - 1])).toBeCloseTo(0.0002, 7);
    // X only: Y unchanged; cursor times unchanged, A off-screen (hidden), B shown.
    expect(state.groups.map((g) => g.yRange)).toEqual(yBefore);
    expect(await cursorTimes()).toEqual([40, 150.1]);
    expect(await lineHidden()).toEqual([true, false]);
    // Only the fitted window was fetched: STN_LONG for its slice at
    // r = 150..150.2 (never the whole record); STN_MID (60..120 s) has no
    // sample in view and is not fetched at all.
    const ownRequests = (sourceId) => requests.filter((u) => u.pathname.includes(`/sources/${sourceId}/waveform`));
    expect(ownRequests(ids.long).length).toBeGreaterThan(0);
    for (const u of ownRequests(ids.long)) {
      expect(Number(u.searchParams.get("start_time"))).toBeGreaterThanOrEqual(149.99);
      expect(Number(u.searchParams.get("end_time"))).toBeLessThanOrEqual(150.21);
    }
    expect(ownRequests(ids.mid)).toEqual([]);
    expect(state.panels.find((c) => c.label === "STN_MID · VA").r).toEqual([]);

    // 20 Hz / 60 s.
    await activate(page, "STN_MID");
    await fitRecord(page, 3);
    state = await plotState(page);
    expect(state.viewport).toEqual(await memberExtent(page, ids.mid));
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(60, 9);
    expect(state.panels.find((c) => c.label === "STN_MID · VA").r.length).toBe(1201);
    expect(await cursorTimes()).toEqual([40, 150.1]);
    expect(await lineHidden()).toEqual([true, true]); // 40 and 150.1 lie outside 60..120

    // Combined: the same active record and viewport; Fit Record works the same.
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    state = await plotState(page);
    expect(state.groups).toHaveLength(1);
    expect(state.viewport).toEqual(await memberExtent(page, ids.mid));
    expect((await activeState(page)).active).toBe(ids.mid);
    await activate(page, "STN_FAST");
    await fitRecord(page, 3);
    expect((await plotState(page)).viewport).toEqual(fastExtent);
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);
    expect((await plotState(page)).viewport).toEqual(fastExtent);
    expect((await activeState(page)).active).toBe(ids.fast);

    // 1 Hz / 300 s: its extent is Fit All here.
    await activate(page, "STN_LONG");
    await fitRecord(page, 3);
    state = await plotState(page);
    expect(state.viewport).toEqual(await memberExtent(page, ids.long));
    expect(state.atFitAll).toBe(true);
    expect(await cursorTimes()).toEqual([40, 150.1]);
    expect(await lineHidden()).toEqual([false, false]);

    // A record without a plotted channel is not a target.
    await activate(page, "STN_P");
    expect((await activeState(page)).fitTitle).toContain("plot a channel of STN_P first");
    expect((await activeState(page)).fitDisabled).toBe(true);
    // Autoscale X is still Fit All for X (DEC-149: X only, no longer
    // also autoscales Y).
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    expect(consoleErrors).toEqual([]);
  });

  test("an 87-day outlier: Fit All keeps the real span and its notice; Fit Record gives each side a local view", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_EVENT", date: "27/07/2022", startClock: "12:41:40.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_EVENT_2", date: "27/07/2022", startClock: "12:41:42.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_OUTLIER", date: "22/10/2022", startClock: "17:47:16.000000", durationS: 6 });
    const ids = { event: await sourceIdFor(page, "STN_EVENT"), outlier: await sourceIdFor(page, "STN_OUTLIER") };
    await addRecords(page, ["STN_EVENT", "STN_EVENT_2", "STN_OUTLIER"]);
    for (const station of ["STN_EVENT", "STN_EVENT_2", "STN_OUTLIER"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    let state = await plotState(page);
    const fitAllSpan = state.fitAll.end - state.fitAll.start;
    expect(fitAllSpan).toBeGreaterThan(87 * 86400);
    await expect(page.locator("#wwErSpanNotice")).toBeVisible();

    await activate(page, "STN_EVENT");
    await fitRecord(page, 3);
    state = await plotState(page);
    expect(state.viewport).toEqual(await memberExtent(page, ids.event));
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(4, 9);
    expect(state.panels.find((c) => c.label === "STN_EVENT · VA").r.length).toBe(4001);
    // Fit All is unchanged (no compression, no break) and still warned about.
    expect(state.fitAll.end - state.fitAll.start).toBe(fitAllSpan);
    await expect(page.locator("#wwErSpanNotice")).toBeVisible();

    await activate(page, "STN_OUTLIER");
    await fitRecord(page, 3);
    state = await plotState(page);
    const outlier = await memberExtent(page, ids.outlier);
    expect(state.viewport).toEqual(outlier);
    expect(outlier.start).toBeGreaterThan(87 * 86400);
    expect(state.panels.find((c) => c.label === "STN_OUTLIER · VA").r.length).toBe(6001);
    // The local plotting origin moved with the view (precision), in
    // reconstruction coordinates.
    expect(Math.abs(state.origin - outlier.start)).toBeLessThan(100 * 6);
    expectSharedAxis(state);
  });
});

test.describe("Event Reconstruction Fit Record -- timing changes and isolation", () => {
  test("a correction of the active record moves its fitted extent; another record's correction leaves the active record; a reference switch rebases it", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:03.000000", durationS: 1 });
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:05.000000", durationS: 1 });
    const ids = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B"), c: await sourceIdFor(page, "STN_C") };
    await addRecords(page, ["STN_A", "STN_B", "STN_C"]);
    for (const station of ["STN_A", "STN_B", "STN_C"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await activate(page, "STN_B");
    await fitRecord(page, 3);
    expect((await plotState(page)).viewport).toEqual({ start: 3, end: 4 });

    // Correct the active record by +500 ms: Fit Record uses the new extent.
    await setCorrection(page, "STN_B", 500);
    await expect.poll(async () => (await memberExtent(page, ids.b)).start).toBeCloseTo(3.5, 9);
    await fitRecord(page, 3);
    let state = await plotState(page);
    expect(state.viewport.start).toBeCloseTo(3.5, 9);
    expect(state.viewport.end).toBeCloseTo(4.5, 9);
    // Another record's correction: the active record stays STN_B.
    await setCorrection(page, "STN_C", -250);
    await expect.poll(async () => (await memberExtent(page, ids.c)).start).toBeCloseTo(4.75, 9);
    expect((await activeState(page)).active).toBe(ids.b);

    // Reference switch to STN_C: still STN_B (same physical record), its
    // numbers rebased; Fit Record uses the rebased extent.
    await memberRow(page, "STN_C").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await activeState(page)).reference).toBe(ids.c);
    expect((await activeState(page)).active).toBe(ids.b);
    const rebased = await memberExtent(page, ids.b);
    expect(rebased.start).toBeCloseTo(3.5 - 4.75, 9);
    await fitRecord(page, 3);
    state = await plotState(page);
    expect(state.viewport.start).toBeCloseTo(rebased.start, 9);
    expect(state.viewport.end).toBeCloseTo(rebased.end, 9);
  });

  test("Fit Record never changes Waveform's layout, panels or state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadMixedDurations(page);
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    const waveform = () => page.evaluate(() => ({
      layoutMode: ww.layoutMode,
      displayed: Array.from(ww.displayed.keys()).sort(),
      panels: ww.panels.map((p) => p.groupKey + ":" + p.channels.map((c) => c.channelName).join(",")),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
    }));
    await page.waitForTimeout(500);
    const before = await waveform();
    await addRecords(page, ["STN_LONG", "STN_MID", "STN_FAST"]);
    for (const station of ["STN_LONG", "STN_MID", "STN_FAST"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await activate(page, "STN_FAST");
    await fitRecord(page, 3);
    await page.locator("#wwErViewCombinedBtn").click();
    await activate(page, "STN_MID");
    await fitRecord(page, 3);
    expect(await waveform()).toEqual(before);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
