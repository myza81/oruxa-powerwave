// Event Reconstruction Slice 3D (DEC-129): navigation on the shared
// reconstruction timeline -- X-only Pan (DEC-144: Box Zoom retired),
// staged Zoom In/Out, Autoscale X (Fit All + autoscale Y, also on
// double-click; formerly "Reset Time View"), Autoscale
// Y, viewport rebasing when the reference or a correction moves the
// reconstruction zero, the Fit All span notice, and Waveform isolation.

const { test, expect } = require("@playwright/test");
const {
  api, collectConsoleErrors, uploadRecord, memberRow, openEventReconstruction, addRecords, channelRow, selectChannel,
  waitForPlot, plotState, zoomTo, waitForSharedAxis, expectSharedAxis, dragOnPanel,
} = require("./support/event_reconstruction_helpers");

// Two overlapping 4 s records at 1 kHz: A 10:00:00, B 10:00:02 (Fit All
// [0, 6] with A as reference).
async function twoOverlapping(page, channels = [["STN_A", "VA"], ["STN_A", "IA"], ["STN_B", "VA"]]) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
  await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000", durationS: 4 });
  await addRecords(page, ["STN_A", "STN_B"]);
  for (const [station, channel] of channels) await selectChannel(page, station, channel);
  await waitForPlot(page, channels.length);
}

async function waitForViewport(page, start, end) {
  await expect.poll(async () => {
    const vp = (await plotState(page)).viewport;
    return !!vp && Math.abs(vp.start - start) < 1e-9 && Math.abs(vp.end - end) < 1e-9;
  }).toBe(true);
  await waitForSharedAxis(page);
  await waitForPlot(page, (await plotState(page)).panels.length);
}

async function setCorrection(page, station, ms) {
  await memberRow(page, station).locator("input[data-er-correction-input]").fill(String(ms));
  await memberRow(page, station).locator('button[data-er-action="set-correction"]').click();
}

function captureWaveformRequests(page) {
  const urls = [];
  page.on("request", (request) => {
    if (request.url().includes("/waveform")) urls.push(new URL(request.url()));
  });
  return urls;
}

const span = (range) => range[1] - range[0];

// Drags one Y axis's own scale (DEC-134, same helper as the dedicated
// Y-axis drag-zoom suite): region "nsdrag" (middle, pans/sets a manual
// range), "ndrag"/"sdrag" (an end, zooms) of Plotly subplot "xy", "xy2", ...
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

test.describe("Event Reconstruction Slice 3D -- X-only Pan", () => {
  test("a plot-area drag pans the shared X range only, preserving its span; every panel keeps its Y range", async ({ page }) => {
    // DEC-144: Box Zoom is retired -- Pan is the only plot-area
    // interaction mode, every panel's own dragmode is permanently "pan"
    // (no toggle to click), so a plot-area drag always translates the
    // viewport (same span, shifted) rather than resizing it. At Fit All
    // itself there is no room to pan (the window already spans the full
    // bounds), so zoomTo() first reaches a narrower window to pan within.
    const consoleErrors = collectConsoleErrors(page);
    await twoOverlapping(page);
    await zoomTo(page, 1, 5, 0);
    const before = await plotState(page);
    // DEC-134: Y axes are draggable on their own scale (not fixedrange);
    // a drag in the plot area is still X-only.
    expect(before.panels.every((p) => p.yFixedRange === false)).toBe(true);
    expect(before.panels.every((p) => p.dragmode === "pan")).toBe(true);
    const beforeSpan = before.viewport.end - before.viewport.start;
    const startBefore = before.viewport.start;

    await dragOnPanel(page, 1, 0.3, 0.5, -80);
    await expect.poll(async () => (await plotState(page)).viewport.start).toBeLessThan(startBefore - 0.05);
    await waitForSharedAxis(page);
    await waitForPlot(page, 3);
    const state = await plotState(page);
    expectSharedAxis(state);
    expect(state.viewport.end - state.viewport.start).toBeCloseTo(beforeSpan, 6); // Pan preserves span
    state.panels.forEach((panel, i) => expect(panel.yRange).toEqual(before.panels[i].yRange));
    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Event Reconstruction Slice 3D -- staged zoom", () => {
  test("Zoom In and Zoom Out keep the centre, stay inside Fit All and refetch the visible ranges", async ({ page }) => {
    await twoOverlapping(page);
    const factors = await page.evaluate(() => ({ zoomIn: WW_ZOOM_STEP_IN_FACTOR, zoomOut: WW_ZOOM_STEP_OUT_FACTOR }));
    let state = await plotState(page);
    expect(state.fitAll).toEqual({ start: 0, end: state.fitAll.end });
    expect(state.fitAll.end).toBeCloseTo(6, 9);

    // At Fit All: Zoom Out is unavailable and a no-op.
    await expect(page.locator("#wwErZoomOutBtn")).toBeDisabled();
    const requests = captureWaveformRequests(page);
    await page.evaluate(() => wwErStepZoomX("out"));
    await page.waitForTimeout(300);
    expect((await plotState(page)).viewport).toEqual(state.fitAll);
    expect(requests).toHaveLength(0);

    // Zoom In, twice: centre 3 kept, span x factor each time.
    await page.locator("#wwErZoomInBtn").click();
    const firstSpan = 6 * factors.zoomIn;
    await waitForViewport(page, 3 - firstSpan / 2, 3 + firstSpan / 2);
    await page.locator("#wwErZoomInBtn").click();
    const secondSpan = firstSpan * factors.zoomIn;
    await waitForViewport(page, 3 - secondSpan / 2, 3 + secondSpan / 2);
    state = await plotState(page);
    expectSharedAxis(state);
    await expect(page.locator("#wwErZoomOutBtn")).toBeEnabled();
    // The latest requests asked for exactly the visible native ranges.
    const latestA = requests.filter((u) => u.searchParams.get("channel_name") === "VA").slice(-2);
    // Window [1.08, 4.92]. A covers r 0..4: start 1.08, end open (past
    // its last sample). B covers r 2..6: start open (before its first
    // sample), end 4.92 - 2.
    const bounds = latestA.map((u) => [u.searchParams.get("start_time"), u.searchParams.get("end_time")]);
    const reqA = bounds.find(([start]) => start !== null);
    const reqB = bounds.find(([start]) => start === null);
    expect(Number(reqA[0])).toBeCloseTo(3 - secondSpan / 2, 9);
    expect(reqA[1]).toBeNull();
    expect(Number(reqB[1])).toBeCloseTo(3 + secondSpan / 2 - 2, 9);
    for (const panel of state.panels) {
      expect(Math.min(...panel.r)).toBeGreaterThanOrEqual(state.viewport.start - 1e-9);
      expect(Math.max(...panel.r)).toBeLessThanOrEqual(state.viewport.end + 1e-9);
    }

    // Zoom Out: centre kept, span / factor.
    await page.locator("#wwErZoomOutBtn").click();
    const outSpan = secondSpan * factors.zoomOut;
    await waitForViewport(page, 3 - outSpan / 2, 3 + outSpan / 2);

    // Near Fit All's start Zoom Out keeps its span and shifts inside.
    await zoomTo(page, 0, 1);
    await page.locator("#wwErZoomOutBtn").click();
    await waitForViewport(page, 0, factors.zoomOut);
    // Repeated Zoom Out ends exactly at Fit All, then is unavailable.
    for (let i = 0; i < 12 && !(await page.locator("#wwErZoomOutBtn").isDisabled()); i++) {
      await page.locator("#wwErZoomOutBtn").click();
      await page.waitForTimeout(200);
    }
    state = await plotState(page);
    expect(state.viewport).toEqual(state.fitAll);
    expect(state.atFitAll).toBe(true);
    await expect(page.locator("#wwErZoomOutBtn")).toBeDisabled();
    expectSharedAxis(state);
  });

  test("zoom, pan and reset stay in reconstruction time across a large plotting-origin shift", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_REF", startClock: "10:00:00.000000", rateHz: 1, durationS: 10, channels: [{ name: "F", unit: "Hz", amplitude: 1, frequencyHz: 0.05 }] });
    await uploadRecord(page, { station: "STN_FAR", startClock: "12:00:00.000000", rateHz: 5000, durationS: 0.2 });
    await addRecords(page, ["STN_REF", "STN_FAR"]);
    await selectChannel(page, "STN_REF", "F");
    await selectChannel(page, "STN_FAR", "VA");
    await waitForPlot(page, 2);
    const factors = await page.evaluate(() => ({ zoomIn: WW_ZOOM_STEP_IN_FACTOR, zoomOut: WW_ZOOM_STEP_OUT_FACTOR }));
    await zoomTo(page, 7200.05, 7200.06);
    let state = await plotState(page);
    expect(state.origin).toBeGreaterThan(7200);
    await page.locator("#wwErZoomOutBtn").click();
    const outSpan = 0.01 * factors.zoomOut;
    await waitForViewport(page, 7200.055 - outSpan / 2, 7200.055 + outSpan / 2);
    await page.locator("#wwErZoomInBtn").click();
    await waitForViewport(page, 7200.055 - (outSpan * factors.zoomIn) / 2, 7200.055 + (outSpan * factors.zoomIn) / 2);
    state = await plotState(page);
    expectSharedAxis(state);
    const far = state.panels.find((p) => p.label === "STN_FAR · VA");
    expect(far.x.length).toBeGreaterThan(10);
    far.ticktext.forEach((text, k) => expect(Number(text)).toBeCloseTo(far.tickvals[k] + state.origin, 6));
    for (let k = 1; k < far.x.length; k++) {
      expect(Math.fround(far.x[k]) - Math.fround(far.x[k - 1])).toBeCloseTo(0.0002, 7);
    }
    // Pan stays inside Fit All even from far out (DEC-144: Pan is the
    // only plot-area interaction mode, no mode switch needed).
    await dragOnPanel(page, 1, 0.1, 0.9);
    await waitForSharedAxis(page);
    state = await plotState(page);
    expect(state.viewport.end).toBeLessThanOrEqual(state.fitAll.end + 1e-9);
    // Reset returns to Fit All in reconstruction time.
    await page.locator("#wwErResetViewBtn").click();
    await waitForViewport(page, 0, state.fitAll.end);
    expectSharedAxis(await plotState(page));
  });
});

test.describe("Event Reconstruction Slice 3D -- Autoscale X and Autoscale Y", () => {
  test("Y keeps its range through X navigation; Autoscale Y rescales, Autoscale X never touches Y; an empty panel's stale range clears when its data returns", async ({ page }) => {
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:10.000000", durationS: 4 });
    await addRecords(page, ["STN_A", "STN_B"]);
    // Different units, so two panels: Voltage (V) [A VA], Current (A) [B IA].
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_B", "IA");
    await waitForPlot(page, 2);
    let state = await plotState(page);
    const full = state.panels.map((p) => p.yRange);
    // First data autoscaled, then fixed (not autorange any more).
    for (const panel of state.panels) expect(panel.yAutorange).toBe(false);
    expect(span(state.panels[0].yRange)).toBeGreaterThan(200);
    expect(span(state.panels[1].yRange)).toBeGreaterThan(10);

    // A 2 ms window on A (values 0..~59); B has no samples there.
    await zoomTo(page, 1, 1.002);
    state = await plotState(page);
    expect(state.panels[1].note).toBe("No samples of this record in the visible time range.");
    state.panels.forEach((panel, i) => expect(panel.yRange).toEqual(full[i])); // no automatic Y change

    const requests = captureWaveformRequests(page);
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => span((await plotState(page)).panels[0].yRange)).toBeLessThan(80);
    state = await plotState(page);
    const visible = state.panels[0].values;
    expect(state.panels[0].yRange[0]).toBeLessThanOrEqual(Math.min(...visible));
    expect(state.panels[0].yRange[1]).toBeGreaterThanOrEqual(Math.max(...visible));
    expect(state.panels[0].yAutorange).toBe(false);
    // The empty panel's stale range is cleared (autorange, still pending).
    expect(state.panels[1].yAutorange).toBe(true);
    expect(state.panels[1].autoscaleYPending).toBe(true);
    // X untouched, nothing refetched.
    expect(state.viewport.start).toBeCloseTo(1, 12);
    expect(state.viewport.end).toBeCloseTo(1.002, 12);
    expect(requests).toHaveLength(0);

    // Autoscale X (DEC-149): Fit All for X only. Panel 0's Y is already
    // scaled (not pending) from the Autoscale Y click above -- Autoscale
    // X leaves it exactly alone. Panel 1's Y was already pending (it had
    // no data in the narrow window above), so it scales once Fit All
    // brings its data back into view -- that is the pre-existing
    // "a pending axis scales when its data lands" rule any X navigation
    // obeys (DEC-134), not something Autoscale X itself does to Y.
    const narrowRange0 = (await plotState(page)).panels[0].yRange;
    await page.locator("#wwErResetViewBtn").click();
    await waitForViewport(page, 0, 14);
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    state = await plotState(page);
    expect(state.panels[0].yRange).toEqual(narrowRange0); // untouched by Autoscale X
    expect(state.panels[0].yAutorange).toBe(false);
    expect(span(state.panels[1].yRange)).toBeGreaterThan(10);
    expect(state.panels[1].yAutorange).toBe(false);

    // Double-click follows the exact same X-only path as the button.
    await zoomTo(page, 1, 1.002);
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => span((await plotState(page)).panels[0].yRange)).toBeLessThan(80);
    const narrowRange0b = (await plotState(page)).panels[0].yRange;
    await page.locator("#wwErPanels .ww-er-panel").nth(0).locator(".nsewdrag").dblclick();
    await waitForViewport(page, 0, 14);
    state = await plotState(page);
    expect(state.panels[0].yRange).toEqual(narrowRange0b);
    expect(span(state.panels[1].yRange)).toBeGreaterThan(10);
  });

  test("Autoscale X restores the full X extent and never touches Y; Autoscale Y rescales Y only and never touches X", async ({ page }) => {
    // DEC-149 (owner decision): the explicit axis-isolation contract --
    // Autoscale X affects X only, Autoscale Y affects Y only, neither
    // ever touches the other axis's viewport/range.
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await addRecords(page, ["STN_A"]);
    await selectChannel(page, "STN_A", "VA");
    await waitForPlot(page, 1);
    const fitAll = (await plotState(page)).fitAll;

    // 1. A narrowed, non-default X viewport.
    await zoomTo(page, 1, 3);
    // 2. A non-default (manual) Y range.
    await dragAxis(page, 0, "nsdrag", "xy", 30);
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(true);
    const manualYBefore = (await plotState(page)).groups[0].yRange;

    // 3. Invoke Autoscale X.
    await page.locator("#wwErResetViewBtn").click();
    // 4. X returns to the full/default relevant time extent.
    await expect.poll(async () => (await plotState(page)).viewport.start).toBeCloseTo(fitAll.start, 9);
    let state = await plotState(page);
    expect(state.viewport.end).toBeCloseTo(fitAll.end, 9);
    expect(state.atFitAll).toBe(true);
    // 5. The Y range (and its manual flag) is unchanged.
    expect(state.groups[0].yRange).toEqual(manualYBefore);
    expect(state.groups[0].axes[0].manual).toBe(true);

    // Complementary rule: Autoscale Y changes Y only, leaves X unchanged.
    await zoomTo(page, 1, 3);
    const xBefore = (await plotState(page)).viewport;
    await page.locator("#wwErAutoscaleYBtn").click();
    await expect.poll(async () => (await plotState(page)).groups[0].axes[0].manual).toBe(false);
    state = await plotState(page);
    expect(state.viewport.start).toBeCloseTo(xBefore.start, 9);
    expect(state.viewport.end).toBeCloseTo(xBefore.end, 9);
    expect(state.atFitAll).toBe(false); // X is still the narrowed window
  });
});

test.describe("Event Reconstruction Slice 3D -- viewport rebasing", () => {
  test("a reference switch keeps the same physical segment in view", async ({ page }) => {
    await twoOverlapping(page, [["STN_A", "VA"], ["STN_B", "VA"]]);
    await zoomTo(page, 2.5, 3);
    const before = await plotState(page);
    await memberRow(page, "STN_B").locator('button[data-er-action="make-reference"]').click();
    await expect(memberRow(page, "STN_B").locator(".ww-er-badge--reference")).toBeVisible();
    // B's offset was 2 s: the zero moves by 2 s, so does the window.
    await waitForViewport(page, 0.5, 1);
    const after = await plotState(page);
    expect(after.atFitAll).toBe(false);
    after.panels.forEach((panel, i) => {
      // Same native samples in view, numerically 2 s earlier.
      expect(panel.values).toEqual(before.panels[i].values);
      panel.r.forEach((r, k) => expect(r).toBeCloseTo(before.panels[i].r[k] - 2, 9));
    });
    // Pairwise alignment unchanged.
    expect(after.panels[1].r[0] - after.panels[0].r[0]).toBeCloseTo(before.panels[1].r[0] - before.panels[0].r[0], 9);
    expectSharedAxis(after);
  });

  test("corrections and their reset keep the physical view; a window leaving Fit All is clamped", async ({ page }) => {
    await twoOverlapping(page, [["STN_A", "VA"], ["STN_B", "VA"]]);
    await zoomTo(page, 2.5, 3);
    const base = await plotState(page);

    // A correction on a non-reference record: the window stays; B moves.
    await setCorrection(page, "STN_B", 5);
    await expect.poll(async () => (await plotState(page)).panels[1].totalOffsetS).toBeCloseTo(2.005, 12);
    await waitForViewport(page, 2.5, 3);
    let state = await plotState(page);
    expect(state.panels[0].values).toEqual(base.panels[0].values);

    // A correction on the reference: the zero moves by it, and so does
    // the window -- B (unchanged clock) shows the same samples.
    const withB = state;
    await setCorrection(page, "STN_A", 5);
    await waitForViewport(page, 2.495, 2.995);
    state = await plotState(page);
    expect(state.panels[1].values).toEqual(withB.panels[1].values);
    expect(state.panels[1].r[0]).toBeCloseTo(withB.panels[1].r[0] - 0.005, 9);

    // Resetting it moves everything back.
    await memberRow(page, "STN_A").locator('button[data-er-action="reset-correction"]').click();
    await waitForViewport(page, 2.5, 3);
    state = await plotState(page);
    expect(state.panels[1].values).toEqual(withB.panels[1].values);

    // B corrected far earlier: the window over B's end is partly outside
    // the new Fit All [0, 5] and is clamped to what remains.
    await memberRow(page, "STN_B").locator('button[data-er-action="reset-correction"]').click();
    await waitForViewport(page, 2.5, 3);
    await zoomTo(page, 4.5, 5.5);
    await setCorrection(page, "STN_B", -1000);
    await waitForViewport(page, 4.5, 5);
    state = await plotState(page);
    expect(state.fitAll.end).toBeCloseTo(5, 9);
    // Entirely outside -> back to Fit All.
    await zoomTo(page, 4.6, 4.9);
    await setCorrection(page, "STN_B", -3000);
    await expect.poll(async () => (await plotState(page)).atFitAll).toBe(true);
    state = await plotState(page);
    expect(state.viewport).toEqual(state.fitAll);
    expect(state.fitAll.end).toBeCloseTo(4, 9);
  });
});

test.describe("Event Reconstruction Slice 3D -- Fit All span notice", () => {
  test("an 87-day outlier is named, never hidden or compressed; nearby records give no notice", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000" });
    await uploadRecord(page, { station: "STN_B", startClock: "10:01:00.000000" });
    // 87 days later (06/03/2026 + 87 days = 01/06/2026).
    await uploadRecord(page, { station: "STN_FAR", date: "01/06/2026", startClock: "10:00:00.000000" });
    await addRecords(page, ["STN_A", "STN_B", "STN_FAR"]);
    await selectChannel(page, "STN_A", "VA");
    await selectChannel(page, "STN_B", "VA");
    await waitForPlot(page, 2);
    const notice = page.locator("#wwErSpanNotice");
    await expect(notice).toBeHidden(); // records a minute apart

    await selectChannel(page, "STN_FAR", "VA");
    await waitForPlot(page, 3);
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("Fit All is dominated by one time gap");
    await expect(notice).toContainText("Fit All spans 2.86 months because STN_FAR is 2.86 months away from the other plotted records.");
    await expect(notice).toContainText("Nothing is hidden and time is not compressed.");
    const state = await plotState(page);
    // Every record still plotted; physical time kept.
    expect(state.panels.map((p) => p.r.length)).toEqual([1001, 1001, 1001]);
    expect(state.fitAll.end - state.fitAll.start).toBeCloseTo(87 * 86400 + 1, 6);
    // The backend's own large-gap warning is unchanged and separate.
    await expect(page.locator('#wwErNotices .ww-er-notice--warn', { hasText: "Large time gap" })).toBeVisible();

    // Two records only: two groups, both named.
    await (await channelRow(page, "STN_B", "VA")).click();
    await waitForPlot(page, 2);
    await expect(notice).toContainText("because the plotted records are in two groups 2.86 months apart: STN_A and STN_FAR.");
    // Removing the far channel removes the notice.
    await (await channelRow(page, "STN_FAR", "VA")).click();
    await waitForPlot(page, 1);
    await expect(notice).toBeHidden();
    expect(consoleErrors).toEqual([]);
  });

  test("the large-gap notice reads in a human-friendly unit, never raw seconds, across every bucket", async ({ page }) => {
    // The exact worked examples the UX refinement was specified with
    // (style: improve event reconstruction large-gap time formatting),
    // evaluated against the REAL running wwErFormatSpan() -- not a
    // re-implementation here that could silently drift from it.
    await page.goto("/index.html");
    const cases = [
      [45.2, "45.2 seconds"], [1, "1 second"], [59.9, "59.9 seconds"],
      [125, "2.08 minutes"], [60, "1 minute"],
      [7200, "2 hours"], [3600, "1 hour"],
      [90000, "1.04 days"], [7 * 86400 - 1, "7 days"],
      [1500000, "2.48 weeks"], [30 * 86400 - 1, "4.29 weeks"],
      [12275440.073, "4.67 months"], [365 * 86400 - 1, "12 months"],
      [365 * 86400 + 1, "1 year"], [2 * 365 * 86400, "2 years"],
    ];
    const results = await page.evaluate((cases) => cases.map(([seconds]) => wwErFormatSpan(seconds)), cases);
    expect(results).toEqual(cases.map(([, expected]) => expected));
    // The underlying threshold/outlier LOGIC (never shown directly, only
    // through this formatter) is unchanged -- same gap/span SECONDS the
    // backend's own large-gap warning and data-er-gap-s always carried.
    expect(await page.evaluate(() => typeof WW_ER_OUTLIER_GAP_FRACTION)).toBe("number");
  });
});

test.describe("Event Reconstruction Slice 3D -- Waveform isolation", () => {
  test("zoom, reset, autoscale and double-click never change Waveform state", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.goto("/index.html");
    await uploadRecord(page, { station: "STN_A", startClock: "10:00:00.000000", durationS: 4 });
    await uploadRecord(page, { station: "STN_B", startClock: "10:00:02.000000", durationS: 4 });
    await page.locator("#recordingsTableBody tr[data-source-id]").first().click();
    await expect(page.locator("#workspaceRow")).toBeVisible();
    const wfRow = page.locator('#channelGroups tr.channel-row--toggle[data-channel-kind="analog"]').first();
    if ((await wfRow.getAttribute("aria-pressed")) !== "true") await wfRow.click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    const waveform = () => page.evaluate(() => ({
      displayed: Array.from(ww.displayed.keys()).sort(),
      dragMode: ww.dragMode,
      viewports: JSON.stringify(Array.from(ww.timeGroupViewports.entries())),
      panels: ww.panels.map((p) => p.id + ":" + JSON.stringify(p.chartEl.layout.xaxis.range) + ":" + JSON.stringify(p.chartEl.layout.yaxis.range) + ":" + p.chartEl.layout.yaxis.fixedrange),
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
    await page.locator("#wwErZoomInBtn").click();
    await page.locator("#wwErZoomInBtn").click();
    await page.locator("#wwErZoomOutBtn").click();
    await page.locator("#wwErAutoscaleYBtn").click();
    await dragOnPanel(page, 0, 0.3, 0.6, 40);
    await page.locator("#wwErPanels .ww-er-panel").nth(0).locator(".nsewdrag").dblclick();
    await page.locator("#wwErResetViewBtn").click();
    await waitForPlot(page, 2);

    expect(await waveform()).toEqual(before);
    expect(await api(page, "/synchronization/time-groups")).toEqual(groupsBefore);
    expect(await api(page, "/synchronization/sources")).toEqual(syncBefore);
    await page.locator("#mainNavWaveformBtn").click();
    await expect(wfRow).toHaveAttribute("aria-pressed", "true");
    expect(await waveform()).toEqual(before);
    expect(consoleErrors).toEqual([]);
  });
});
