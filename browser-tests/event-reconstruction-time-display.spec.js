// Event Reconstruction Relative / Absolute time display (DEC-135): labels
// only. Reconstruction seconds stay the internal coordinate; Absolute
// shows absolute(r) = reconstruction_zero_time_utc + r (reference recorded
// start + reference correction), in the display timezone (DEC-122). The
// synthetic COMTRADE records are naive Asia/Kuala_Lumpur wall clock
// (DEC-121), so their displayed digits equal the recorded ones.

const { test, expect } = require("@playwright/test");
const {
  BACKEND, collectConsoleErrors, uploadRecord, workspaceId, sourceIdFor, memberRow, api, addRecords, selectChannel,
  waitForPlot, plotState, zoomTo,
} = require("./support/event_reconstruction_helpers");

const ticks = (page) => page.evaluate(() => wwErState.plot.panels.map((p) => p.chartEl.layout.xaxis.ticktext));
const readout = (page) => page.evaluate(() => ["A", "B", "Delta"].map((k) => document.getElementById("wwErCursorReadout" + k).textContent));
// Hover text of every plotted trace, by trace label.
const hoverTexts = (page) => page.evaluate(() => Object.fromEntries(wwErState.plot.panels.flatMap((p) =>
  p.traces.map((t, k) => [wwErTraceLabelText(t), { text: p.chartEl.data[k].text || null, r: t.reconstructionTime.slice(), template: p.chartEl.data[k].hovertemplate }]))));
// The absolute instant of reconstruction time r, as the page computes it
// (epoch seconds as integer + fraction), for math checks.
const absoluteOf = (page, r) => page.evaluate((r) => {
  const i = wwErAbsoluteInstant(wwErAbsoluteZero(), r);
  return i.epochSecond + i.fraction;
}, r);

async function setAbsolute(page, on) {
  await page.locator(on ? "#wwErTimeAbsoluteBtn" : "#wwErTimeRelativeBtn").click();
  await expect(page.locator("#wwErTimeAbsoluteBtn")).toHaveAttribute("aria-pressed", String(on));
}

function expectCleanLabels(labels) {
  for (const label of labels) {
    expect(label).not.toMatch(/undefined|NaN|Infinity/);
    expect(label).not.toMatch(/^\d{6,}/); // never a raw epoch number
  }
  expect(new Set(labels).size).toBe(labels.length); // never duplicated
}

test.describe("Event Reconstruction time display -- presentation only", () => {
  test("Relative <-> Absolute changes labels only: same viewport, data, cursors and Y; nothing refetched", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:01.000000", durationS: 4 });
    const sourceA = await sourceIdFor(page, "STN_A");
    await page.request.post(`${BACKEND}/api/v1/workspaces/${await workspaceId(page)}/calculated-channels`, {
      data: { name: "-VA", operation: "reverse_polarity", inputs: [{ kind: "source", source_id: sourceA, channel_name: "VA" }], parameters: {} },
    });
    await addRecords(page, ["STN_A", "STN_B"]);
    await expect(page.locator("#wwErTimeRelativeBtn")).toHaveAttribute("aria-pressed", "true"); // default
    for (const [station, name] of [["STN_A", "VA"], ["STN_B", "VA"], ["STN_A", "-VA"]]) await selectChannel(page, station, name);
    await waitForPlot(page, 3);
    await zoomTo(page, 1.2, 1.6);
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 1.25); wwErSetCursorTime("b", 1.5); });
    await expect.poll(() => page.evaluate(() => wwErPlottedTraces().every((t) => t.cursorValues && t.cursorValues.b))).toBe(true);
    const snapshot = async () => {
      const state = await plotState(page);
      return JSON.stringify({
        viewport: state.viewport, fitAll: state.fitAll, origin: state.origin, atFitAll: state.atFitAll,
        // Every X quantity and all data; tick positions/labels are the
        // presentation that is allowed to change.
        panels: state.panels.map((c) => [c.key, c.x, c.values, c.customdata, c.yRange, c.xRange]),
        cursors: await page.evaluate(() => [wwErState.plot.cursors.a.time, wwErState.plot.cursors.b.time]),
        tree: await page.evaluate(() => Array.from(document.querySelectorAll("#wwErMembersPanel .cur-value")).map((el) => el.textContent)),
        active: await page.evaluate(() => wwErState.activeRecordId), dragMode: await page.evaluate(() => wwErState.dragMode),
      });
    };
    const before = await snapshot();
    const relativeTicks = await ticks(page);
    const relativeReadout = await readout(page);
    expect(relativeReadout).toEqual(["+1.250000 s", "+1.500000 s", "250.000 ms"]);
    const requests = [];
    page.on("request", (r) => { if (/\/waveform|cursor-values/.test(r.url())) requests.push(r.url()); });

    await setAbsolute(page, true);
    await expect.poll(async () => (await ticks(page))[0][0]).toContain("Mar 2026");
    expect(await snapshot()).toBe(before);
    const absoluteTicks = (await ticks(page))[0];
    expect(absoluteTicks).toEqual(["10:00:01.2<br>6 Mar 2026", "10:00:01.3", "10:00:01.4", "10:00:01.5", "10:00:01.6"]);
    expectCleanLabels(absoluteTicks);
    // Cursor points become wall clock (µs); Δt stays a duration.
    expect(await readout(page)).toEqual(["10:00:01.250000", "10:00:01.500000", "250.000 ms"]);
    expect(await page.locator("#wwErCursorReadoutA").getAttribute("title")).toBe("6 Mar 2026 10:00:01.250000 (Asia/Kuala_Lumpur)");
    // Hover: native and calculated alike, the recorded wall clock of each sample.
    const hover = await hoverTexts(page);
    for (const label of ["STN_A · VA", "STN_A · -VA", "STN_B · VA"]) {
      expect(hover[label].template.startsWith("%{text}: %{y}")).toBe(true);
      expect(hover[label].text.length).toBe(hover[label].r.length);
    }
    expect(hover["STN_A · VA"].text[0]).toBe("6 Mar 2026 10:00:01.200000"); // r = 1.2 of STN_A (10:00:00)
    expect(hover["STN_A · -VA"].text).toEqual(hover["STN_A · VA"].text); // calculated = its timing parent
    expect(hover["STN_B · VA"].text[0]).toBe("6 Mar 2026 10:00:01.200000"); // B's elapsed 0.2 s, same instant
    // Combined keeps the time display.
    await page.locator("#wwErViewCombinedBtn").click();
    await waitForPlot(page, 3);
    expect((await ticks(page))[0]).toEqual(absoluteTicks);
    await page.locator("#wwErViewGroupedBtn").click();
    await waitForPlot(page, 3);

    await setAbsolute(page, false);
    expect(await ticks(page)).toEqual(relativeTicks);
    expect(await readout(page)).toEqual(relativeReadout);
    expect((await hoverTexts(page))["STN_A · VA"].template.startsWith("%{customdata:.6f} s")).toBe(true);
    expect(await snapshot()).toBe(before);
    // No waveform or cursor-value request was made by the switches.
    expect(requests).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction time display -- corrected absolute time", () => {
  test("a reference switch never changes absolute time; a correction moves only its record by exactly that amount", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:18.425000", durationS: 2 });
    await uploadRecord(page, { station: "STN_C", startClock: "10:00:05.500000", durationS: 2 });
    const ids = { a: await sourceIdFor(page, "STN_A"), b: await sourceIdFor(page, "STN_B"), c: await sourceIdFor(page, "STN_C") };
    await addRecords(page, ["STN_A", "STN_B", "STN_C"]);
    for (const station of ["STN_A", "STN_B", "STN_C"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await setAbsolute(page, true);
    // A record's own start, as absolute epoch seconds (page math) and as hover text.
    const startOf = async (station) => {
      const definition = await api(page, "/event-reconstruction/definition");
      const member = definition.members.find((m) => m.record_id === ids[station]);
      return { relative: member.start_s, absolute: await absoluteOf(page, member.start_s) };
    };
    const hoverFirst = async (label) => (await hoverTexts(page))[label].text[0];
    await zoomTo(page, 18.4, 18.6);
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 18.45); wwErSetCursorTime("b", 18.5); });
    const b0 = await startOf("b");
    expect(b0.relative).toBeCloseTo(18.425, 9);
    expect(await hoverFirst("STN_B · VA")).toBe("6 Mar 2026 10:00:18.425000");
    const viewAbsolute = await absoluteOf(page, (await plotState(page)).viewport.start);
    const readoutBefore = await readout(page);
    expect(readoutBefore.slice(0, 2)).toEqual(["10:00:18.450000", "10:00:18.500000"]);

    // Reference -> STN_B: B is now at relative 0, its absolute time unchanged;
    // the window and the cursors keep their physical instants and labels.
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect.poll(async () => (await startOf("b")).relative).toBeCloseTo(0, 9);
    await waitForPlot(page, 3);
    expect((await startOf("b")).absolute).toBeCloseTo(b0.absolute, 6);
    expect((await startOf("a")).absolute).toBeCloseTo(await page.evaluate(() => Date.UTC(2026, 2, 6, 2, 0, 0) / 1000), 6);
    expect(await hoverFirst("STN_B · VA")).toBe("6 Mar 2026 10:00:18.425000");
    expect(await absoluteOf(page, (await plotState(page)).viewport.start)).toBeCloseTo(viewAbsolute, 6);
    expect(await readout(page)).toEqual(readoutBefore);

    // Non-reference correction: STN_C +20 ms -> its absolute start +20 ms;
    // A and B unchanged.
    const c0 = await startOf("c");
    const a0 = await startOf("a");
    await memberRow(page, "STN_C").locator("input[data-er-correction-input]").fill("20");
    await memberRow(page, "STN_C").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(async () => (await startOf("c")).absolute - c0.absolute).toBeCloseTo(0.020, 6);
    expect((await startOf("a")).absolute).toBeCloseTo(a0.absolute, 6);
    expect((await startOf("b")).absolute).toBeCloseTo(b0.absolute, 6);

    // Reference correction: STN_B (reference) -0.2 ms -> B's absolute
    // placement -0.2 ms (B stays at relative 0); A and C keep theirs.
    await memberRow(page, "STN_B").locator("input[data-er-correction-input]").fill("-0.2");
    await memberRow(page, "STN_B").locator('button[data-er-action="set-correction"]').click();
    await expect.poll(async () => (await startOf("b")).absolute - b0.absolute).toBeCloseTo(-0.0002, 6);
    expect((await startOf("b")).relative).toBeCloseTo(0, 9);
    expect((await startOf("a")).absolute).toBeCloseTo(a0.absolute, 6);
    expect((await startOf("c")).absolute).toBeCloseTo(c0.absolute + 0.020, 6);
    await waitForPlot(page, 3);
    expect(await hoverFirst("STN_B · VA")).toBe("6 Mar 2026 10:00:18.424800");
  });

  test("5 kHz at +2 h: consecutive 200 µs samples stay distinct in ticks, hover and cursors", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_REF", startClock: "10:00:00.000000", durationS: 1 });
    await uploadRecord(page, { station: "STN_FAST", startClock: "12:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_REF", "STN_FAST"]);
    await selectChannel(page, "STN_REF", "VA");
    await selectChannel(page, "STN_FAST", "VA");
    await waitForPlot(page, 2);
    await setAbsolute(page, true);
    await zoomTo(page, 7200.1, 7200.1012);
    const fast = (await hoverTexts(page))["STN_FAST · VA"];
    expect(fast.r.length).toBeGreaterThanOrEqual(5);
    // Consecutive samples: exactly 200 µs apart in the absolute labels.
    const micros = fast.text.map((text) => {
      const m = /^6 Mar 2026 12:00:00\.(\d{6})$/.exec(text);
      expect(m, text).not.toBeNull();
      return Number(m[1]);
    });
    for (let k = 1; k < micros.length; k++) expect(micros[k] - micros[k - 1]).toBe(200);
    expect(micros[0]).toBeGreaterThanOrEqual(100000);
    expect(micros[0]).toBeLessThanOrEqual(100200);
    const labels = (await ticks(page))[0];
    expectCleanLabels(labels);
    expect(labels[0]).toMatch(/^12:00:00\.1000\d*<br>6 Mar 2026$/);
    // Cursors on two neighbouring samples.
    await page.locator("#wwErCursorModeBtn").click();
    await page.evaluate(() => { wwErSetCursorTime("a", 7200.1002); wwErSetCursorTime("b", 7200.1004); });
    expect(await readout(page)).toEqual(["12:00:00.100200", "12:00:00.100400", "200.0 µs"]);
    await setAbsolute(page, false);
    expect((await readout(page))[2]).toBe("200.0 µs");
  });
});

test.describe("Event Reconstruction time display -- adaptive formats", () => {
  test("midnight, day/year crossings and an 87-day span stay unambiguous; Fit Record returns to time of day", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_NYE", date: "31/12/2025", startClock: "23:59:59.500000", durationS: 1 });
    await uploadRecord(page, { station: "STN_DAY", date: "01/01/2026", startClock: "11:00:00.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_FAR", date: "29/03/2026", startClock: "08:00:00.000000", durationS: 1 });
    await addRecords(page, ["STN_NYE", "STN_DAY", "STN_FAR"]);
    for (const station of ["STN_NYE", "STN_DAY", "STN_FAR"]) await selectChannel(page, station, "VA");
    await waitForPlot(page, 3);
    await setAbsolute(page, true);
    const at = async (start, end) => {
      await zoomTo(page, start, end);
      const labels = (await ticks(page))[0];
      expectCleanLabels(labels);
      return labels;
    };
    // 87-day Fit All: dates only.
    await page.locator("#wwErResetViewBtn").click();
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    let labels = (await ticks(page))[0];
    expectCleanLabels(labels);
    expect(labels.length).toBeGreaterThanOrEqual(3);
    for (const label of labels) expect(label).toMatch(/^\d{1,2} [A-Z][a-z]{2} 202[56]$/);
    // Year/midnight crossing (r = 0 is 31 Dec 23:59:59.5).
    labels = await at(0.3, 0.7);
    expect(labels).toEqual(["23:59:59.8<br>31 Dec 2025", "23:59:59.9", "00:00:00.0<br>1 Jan 2026", "00:00:00.1", "00:00:00.2"]);
    labels = await at(0.4995, 0.5003); // sub-millisecond, across midnight
    expect(labels[0]).toMatch(/<br>31 Dec 2025$/);
    expect(labels.some((label) => label.startsWith("00:00:00.0000") && label.endsWith("<br>1 Jan 2026"))).toBe(true);
    // Several seconds, minutes, a same-day long span (hours).
    expect((await at(0, 4))[0]).toBe("00:00:00<br>1 Jan 2026");
    labels = await at(0, 300);
    expect(labels.every((label) => /^\d{2}:\d{2}(<br>.*)?$/.test(label))).toBe(true);
    labels = await at(0.5, 11 * 3600 + 3);
    expect(labels[0]).toBe("00:00<br>1 Jan 2026");
    expect(labels).toContain("10:00");
    // Fit Record on the far record: back to fine time of day, its own date.
    await memberRow(page, "STN_FAR").locator("[data-er-activate-record]").click();
    await page.locator("#wwErFitRecordBtn").click();
    await expect.poll(async () => (await ticks(page))[0][0]).toBe("08:00:00.0<br>29 Mar 2026");
    expectCleanLabels((await ticks(page))[0]);
  });

  test("the time display never changes Waveform's state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 2 });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const row = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await row.getAttribute("aria-pressed")) !== "true") await row.click();
    const waveform = () => page.evaluate(() => ({
      timeMode: ww.timeMode,
      panels: ww.panels.map((p) => p.groupKey + ":" + JSON.stringify(p.chartEl && p.chartEl.layout && p.chartEl.layout.xaxis && p.chartEl.layout.xaxis.ticktext)),
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      cursors: JSON.stringify(Array.from(ww.timeGroupCursorState.entries())),
      dragMode: ww.dragMode,
    }));
    await page.waitForTimeout(500);
    const before = await waveform();
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    await setAbsolute(page, true);
    await page.locator("#wwErCursorModeBtn").click();
    await setAbsolute(page, false);
    await setAbsolute(page, true);
    expect(await waveform()).toEqual(before);
    await page.locator("#mainNavWaveformBtn").click();
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
