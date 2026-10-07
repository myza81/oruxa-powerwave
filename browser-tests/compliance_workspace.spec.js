// Compliance & Capability -- the resizable two-column workspace and the
// measured traces on the Comparison Chart (DEC-169).
//
//   LEFT   Reference Layers / Measurement (incl. Event Alignment)
//          <-> draggable divider <->
//   RIGHT  Comparison Chart (owns the full right-panel height)
//
//   Reference defines. Measurement satisfies. Comparison visualizes the
//   resolved measurement against the Reference.
//
// Fixture `line_to_line_multibay` (50 Hz, kV; uploaded through the real UI):
// KPDN1 VR/VY/VB instantaneous, KPDN2 VR/VY only, MCRS VR/VY/VB already-RMS.
// References are created through the real API; everything Compliance-side is
// driven through the real UI and the real Plotly trace data is inspected.

const { test, expect } = require("@playwright/test");
const path = require("path");

const FIXTURES = path.join(__dirname, "..", "backend", "tests", "fixtures", "comtrade");
const BACKEND_URL = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;
const FIXTURE = "line_to_line_multibay";

async function workspaceIdOf(page) {
  return page.evaluate(() => localStorage.getItem("powerwave.workspaceId"));
}
const wsUrl = async (page, suffix) => `${BACKEND_URL}/api/v1/workspaces/${encodeURIComponent(await workspaceIdOf(page))}${suffix}`;

async function uploadMultibay(page) {
  await page.goto("/index.html");
  await page.locator("#mainNavRecordingsBtn").click();
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles(path.join(FIXTURES, `${FIXTURE}.cfg`));
  await page.locator("#uploadModalFile_1").setInputFiles(path.join(FIXTURES, `${FIXTURE}.dat`));
  await page.locator("#uploadModalSubmitBtn").click();
  await page.locator("#uploadModalOverlay").waitFor({ state: "hidden" });
  await expect(page.locator("#recordingsTableBody tr[data-source-id]").last()).toBeVisible();
}

async function addReference(page, { name = "Reference", representation = "line_line_rms", treatment = "each_phase", member = null, unit = "kV" } = {}) {
  const profile = await page.request.post(await wsUrl(page, "/reference-profiles"), { data: {
    name, category: "grid_requirement",
    assessment_definition: { representation, phase_treatment: treatment, member },
    unit, display_start_time: 0, display_end_time: 3, evaluation_start_time: 0, evaluation_end_time: 3, tolerance: 0,
    lower_boundary: { segments: [{ start_time: 0, end_time: 3, start_value: 0.9, end_value: 0.9, segment_type: "constant" }] },
    upper_boundary: null, metadata: {},
  } });
  expect(profile.ok()).toBeTruthy();
  const layer = await page.request.post(await wsUrl(page, "/reference-layers"), { data: { profile_id: (await profile.json()).id, visible: true } });
  expect(layer.ok()).toBeTruthy();
  return layer.json();
}

async function openComplianceAndSelect(page, bay) {
  await page.locator("#mainNavComplianceBtn").click();
  await expect(page.locator("#pageCompliance")).toBeVisible();
  await expect(page.locator("#wwComplianceGroupSelect option")).not.toHaveCount(1);
  await page.locator("#wwComplianceGroupSelect").selectOption({ label: `${bay} VOLTAGE` });
}

async function calcChannels(page) {
  return (await page.request.get(await wsUrl(page, "/calculated-channels"))).json();
}

// Real Plotly data of the Comparison Chart, split by the explicit trace role.
async function chartTraces(page) {
  return page.evaluate(() => {
    const el = document.getElementById("wwComplianceChartPlot");
    const data = el && el.data ? el.data : [];
    const pack = (t) => ({ role: t.meta && t.meta.role, name: t.name, x: t.x, y: t.y, meta: t.meta });
    return {
      measurement: data.filter((t) => t.meta && t.meta.role === "measurement").map(pack),
      reference: data.filter((t) => t.meta && t.meta.role === "reference").map(pack),
    };
  });
}
async function waitForMeasurement(page, count) {
  await expect.poll(async () => (await chartTraces(page)).measurement.length, { timeout: 15000 }).toBe(count);
}
const status = (page) => page.locator("#wwComplianceReadinessStatus");
const finite = (values) => values.filter((v) => v !== null && Number.isFinite(v));

async function prepareAndWaitReady(page) {
  await expect(status(page)).toHaveText("⚠ Action required");
  await page.locator("#wwCompliancePrepareBtn").click();
  await expect(status(page)).toHaveText("✓ Ready for assessment");
}

const box = (page, selector) => page.locator(selector).boundingBox();

// ===================================================================== layout
test.describe("DEC-169 -- two-column workspace layout", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Reference + Measurement (+ Event Alignment) on the left, the chart on the right, no Results card", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const left = page.locator("#wwComplianceConfigColumn");
    const right = page.locator("#wwComplianceChartColumn");
    await expect(left.locator("#wwComplianceReferenceLayersCard")).toBeVisible();
    await expect(left.locator("#wwComplianceMeasurementCard")).toBeVisible();
    await expect(left.locator("#wwComplianceMeasurementCard #wwComplianceEventAlignmentSection")).toBeVisible();
    await expect(right.locator("#wwComplianceChartPanel")).toBeVisible();
    await expect(page.locator("#wwComplianceResultsPanel")).toHaveCount(0); // the Results section is removed entirely
    await expect(page.locator("#pageCompliance")).not.toContainText("Results will appear");

    const split = await box(page, "#wwComplianceSplit");
    const l = await box(page, "#wwComplianceConfigColumn");
    const r = await box(page, "#wwComplianceChartColumn");
    expect(l.x).toBeLessThan(r.x);
    expect(Math.abs(l.y - r.y)).toBeLessThanOrEqual(1); // side by side
    expect(r.width).toBeGreaterThan(l.width); // the chart gets more width
    const ratio = l.width / split.width;
    expect(ratio).toBeGreaterThan(0.33);
    expect(ratio).toBeLessThan(0.42);
    // No tabs on desktop.
    await expect(page.locator("#wwComplianceVoltagePanel [role=tab]")).toHaveCount(0);
  });

  test("a drag handle sits between the columns with a resize cursor and separator semantics", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const handle = page.locator("#wwComplianceSplitHandle");
    await expect(handle).toBeVisible();
    await expect(handle).toHaveAttribute("role", "separator");
    await expect(handle).toHaveAttribute("aria-orientation", "vertical");
    expect(await handle.evaluate((el) => getComputedStyle(el).cursor)).toBe("col-resize");
    const l = await box(page, "#wwComplianceConfigColumn");
    const h = await handle.boundingBox();
    const r = await box(page, "#wwComplianceChartColumn");
    expect(h.x).toBeGreaterThanOrEqual(l.x + l.width - 1);
    expect(h.x + h.width).toBeLessThanOrEqual(r.x + 1);
  });

  test("dragging resizes the columns smoothly, without selecting text, and enforces minimum widths", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const handle = page.locator("#wwComplianceSplitHandle");
    const before = { l: await box(page, "#wwComplianceConfigColumn"), r: await box(page, "#wwComplianceChartColumn") };
    const h = await handle.boundingBox();
    const y = h.y + h.height / 2;

    await page.mouse.move(h.x + h.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 90, y, { steps: 6 });
    // While dragging: the split carries the resizing state and text selection is off.
    await expect(page.locator("#wwComplianceSplit")).toHaveClass(/ww-compliance-resizing/);
    expect(await page.locator("#wwComplianceSplit").evaluate((el) => getComputedStyle(el).userSelect)).toBe("none");
    await page.mouse.move(h.x + h.width / 2 + 160, y, { steps: 6 });
    await page.mouse.up();
    await expect(page.locator("#wwComplianceSplit")).not.toHaveClass(/ww-compliance-resizing/);
    const after = { l: await box(page, "#wwComplianceConfigColumn"), r: await box(page, "#wwComplianceChartColumn") };
    expect(after.l.width).toBeGreaterThan(before.l.width + 120);
    expect(after.r.width).toBeLessThan(before.r.width - 120);
    expect(Math.abs((after.l.width + after.r.width) - (before.l.width + before.r.width))).toBeLessThanOrEqual(2);
    expect(await page.evaluate(() => window.getSelection().toString())).toBe("");

    // Far left: the configuration column never collapses below its minimum.
    const h2 = await handle.boundingBox();
    await page.mouse.move(h2.x + h2.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(0, y, { steps: 8 });
    await page.mouse.up();
    const minLeft = await box(page, "#wwComplianceConfigColumn");
    expect(minLeft.width).toBeGreaterThanOrEqual(338);

    // Far right: the chart keeps a usable width.
    const h3 = await handle.boundingBox();
    await page.mouse.move(h3.x + h3.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(1400, y, { steps: 8 });
    await page.mouse.up();
    const minRight = await box(page, "#wwComplianceChartColumn");
    expect(minRight.width).toBeGreaterThanOrEqual(378);
  });

  test("keyboard: arrow keys resize, Home/End jump to the limits", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const handle = page.locator("#wwComplianceSplitHandle");
    await handle.focus();
    const start = (await box(page, "#wwComplianceConfigColumn")).width;
    await page.keyboard.press("ArrowRight");
    const wider = (await box(page, "#wwComplianceConfigColumn")).width;
    expect(wider).toBeGreaterThan(start + 10);
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    expect((await box(page, "#wwComplianceConfigColumn")).width).toBeLessThan(start - 10);
    await page.keyboard.press("Home");
    expect((await box(page, "#wwComplianceConfigColumn")).width).toBeGreaterThanOrEqual(338);
    await page.keyboard.press("End");
    expect((await box(page, "#wwComplianceChartColumn")).width).toBeGreaterThanOrEqual(378);
    expect(Number(await handle.getAttribute("aria-valuenow"))).toBeGreaterThan(30);
  });

  test("the chosen ratio is kept while the page lives (navigate away and back)", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    await page.locator("#wwComplianceSplitHandle").focus();
    for (let i = 0; i < 4; i += 1) await page.keyboard.press("ArrowRight");
    const chosen = (await box(page, "#wwComplianceConfigColumn")).width;
    await page.locator("#mainNavRecordingsBtn").click();
    await page.locator("#mainNavComplianceBtn").click();
    await expect.poll(async () => Math.abs((await box(page, "#wwComplianceConfigColumn")).width - chosen)).toBeLessThanOrEqual(3);
  });

  test("Plotly resizes with the column: its drawn width follows the chart box after a drag", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    await addReference(page);
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const drawn = () => page.evaluate(() => {
      const el = document.getElementById("wwComplianceChartPlot");
      return { layout: el._fullLayout.width, box: el.getBoundingClientRect().width };
    });
    const before = await drawn();
    expect(Math.abs(before.layout - before.box)).toBeLessThanOrEqual(2);
    const handle = page.locator("#wwComplianceSplitHandle");
    const h = await handle.boundingBox();
    const y = h.y + h.height / 2;
    await page.mouse.move(h.x + h.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 140, y, { steps: 6 });
    await page.mouse.up();
    await expect.poll(async () => {
      const now = await drawn();
      return Math.abs(now.layout - now.box) <= 2 && now.box < before.box - 100;
    }).toBe(true);
  });

  test("narrow widths stack the sections in order and remove the handle", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 900 });
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceSplitHandle")).toBeHidden();
    expect(await page.locator("#wwComplianceSplit").evaluate((el) => getComputedStyle(el).flexDirection)).toBe("column");
    const reference = await box(page, "#wwComplianceReferenceLayersCard");
    const measurement = await box(page, "#wwComplianceMeasurementCard");
    const chart = await box(page, "#wwComplianceChartPanel");
    expect(reference.y).toBeLessThan(measurement.y);
    expect(measurement.y).toBeLessThan(chart.y);
    expect(Math.abs(chart.x - measurement.x)).toBeLessThanOrEqual(2); // one column
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});

// ============================================================ measured traces
test.describe("DEC-169 -- measurement traces on the Comparison Chart", () => {
  test("Each Phase (kV): the three line-line traces are plotted over the Reference, named in the bay's own convention", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "LVRT", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    expect((await chartTraces(page)).measurement).toHaveLength(0); // RMS not prepared yet -> nothing plotted, nothing guessed

    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 3);
    const traces = await chartTraces(page);
    expect(traces.reference).toHaveLength(1);
    expect(traces.measurement.map((t) => t.meta.members)).toEqual([["AB"], ["BC"], ["CA"]]);
    // DEC-117/118: R/Y/B bay -> V<sub>RY</sub>, V<sub>YB</sub>, V<sub>BR</sub> in the Plotly names; canonical members stay in meta.
    expect(traces.measurement.map((t) => t.name)).toEqual(["V<sub>RY</sub>", "V<sub>YB</sub>", "V<sub>BR</sub>"]);
    for (const t of traces.measurement) {
      expect(t.meta.unit).toBe("kV");
      expect(t.meta.kind).toBe("member");
      expect(finite(t.y).length).toBeGreaterThan(100);
    }
  });

  test("a pu Reference: no base -> Action Required and NO pu trace; once the base is configured the traces appear in per-unit, matching Waveform's own per-unit values", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "pu ref", unit: "pu" });
    await openComplianceAndSelect(page, "KPDN1");
    await page.locator("#wwCompliancePrepareBtn").click();
    await expect(page.locator('.ww-compliance-reference-readiness[data-status="action_required"]')).toContainText("pu ref");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="unit"]')).toHaveClass(/ww-compliance-critical/);
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    // The Reference is drawn, but no (pu or otherwise) measured trace exists yet.
    expect((await chartTraces(page)).measurement).toHaveLength(0);
    expect((await chartTraces(page)).reference).toHaveLength(1);

    await page.locator("#wwComplianceConfigureBaseBtn").click();
    await expect(page.locator("#wwMgDrawer")).toHaveClass(/ww-cc-drawer--open/);
    await page.locator("#wwMgVoltageKvInput").fill("132");
    await page.locator("#wwMgDrawerSaveBtn").click();
    await page.locator("#measurementGroupsCloseBtn").click();
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await waitForMeasurement(page, 3);
    const traces = (await chartTraces(page)).measurement;
    expect(traces.every((t) => t.meta.unit === "pu")).toBe(true);
    const ab = traces.find((t) => t.meta.members[0] === "AB");
    const puPeak = Math.max(...finite(ab.y));
    expect(puPeak).toBeLessThan(10);

    // Same number the Waveform endpoint gives for the very same shared RMS channel in per-unit.
    const rmsOfAb = (await calcChannels(page)).filter((c) => c.operation === "rms").find((c) => c.name.includes("VRY"));
    expect(rmsOfAb, "RMS of the line-line VRY channel").toBeTruthy();
    const waveform = await (await page.request.get(await wsUrl(page, `/calculated-channels/${rmsOfAb.id}/waveform?unit_mode=per_unit`))).json();
    expect(waveform.unit).toBe("pu");
    expect(puPeak).toBeCloseTo(Math.max(...finite(waveform.values)), 9);
    // And the y axis says per-unit.
    const axisTitle = await page.evaluate(() => {
      const t = document.getElementById("wwComplianceChartPlot").layout.yaxis.title;
      return typeof t === "string" ? t : t.text;
    });
    expect(axisTitle).toBe("Value (pu)");
  });

  test("Single plots only the named voltage", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { treatment: "single", member: "BC", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 1);
    const [trace] = (await chartTraces(page)).measurement;
    expect(trace.meta.members).toEqual(["BC"]);
    expect(trace.name).toBe("V<sub>YB</sub>");
  });

  test("Minimum and Maximum each plot ONE aggregate trace", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "min", treatment: "minimum", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 1);
    let [trace] = (await chartTraces(page)).measurement;
    expect(trace.meta.kind).toBe("minimum");
    expect(trace.meta.members).toEqual(["AB", "BC", "CA"]);
    expect(trace.name).toBe("Minimum of V<sub>RY</sub>, V<sub>YB</sub>, V<sub>BR</sub>");

    await addReference(page, { name: "max", treatment: "maximum", unit: "kV" });
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 2);
    const kinds = (await chartTraces(page)).measurement.map((t) => t.meta.kind).sort();
    expect(kinds).toEqual(["maximum", "minimum"]);
    const traces = (await chartTraces(page)).measurement;
    const minimum = traces.find((t) => t.meta.kind === "minimum");
    const maximum = traces.find((t) => t.meta.kind === "maximum");
    const points = minimum.y.map((v, i) => [v, maximum.y[i]]).filter(([a, b]) => a !== null && b !== null);
    expect(points.length).toBeGreaterThan(100);
    expect(points.every(([lo, hi]) => lo <= hi + 1e-9)).toBe(true);
  });

  test("two References needing the identical product share one set of traces and no RMS is duplicated", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { name: "A", unit: "kV" });
    await addReference(page, { name: "B", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await page.locator("#wwCompliancePrepareBtn").click();
    await waitForMeasurement(page, 3);
    for (const t of (await chartTraces(page)).measurement) expect(t.meta.layer_ids).toHaveLength(2);
    const count = (await calcChannels(page)).length;
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 3);
    expect((await calcChannels(page)).length).toBe(count); // reused, never re-created
  });

  test("an already-RMS source is plotted directly (no calculated channel)", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "MCRS");
    await expect(status(page)).toHaveText("✓ Ready for assessment");
    await waitForMeasurement(page, 3);
    expect((await chartTraces(page)).measurement.map((t) => t.name)).toEqual(["V<sub>R</sub>", "V<sub>Y</sub>", "V<sub>B</sub>"]); // MCRS is an R/Y/B bay
    expect(await calcChannels(page)).toEqual([]);
  });

  test("unsafe line-line (angle-less RMS) is blocked: the Reference is drawn, no measured trace is guessed", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { unit: "kV" });
    await openComplianceAndSelect(page, "MCRS");
    await expect(status(page)).toHaveText("✕ Measurement cannot satisfy this reference");
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const traces = await chartTraces(page);
    expect(traces.reference).toHaveLength(1);
    expect(traces.measurement).toHaveLength(0);
  });

  test("chart empty states say exactly what is missing", async ({ page }) => {
    await uploadMultibay(page);
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartEmptyState")).toContainText("No reference layers to display");
    await expect(page.locator("#wwComplianceGroupSelect option")).not.toHaveCount(1);
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "KPDN1 VOLTAGE" });
    await expect(page.locator("#wwComplianceChartEmptyState")).toHaveText("Select or add a Reference Profile to compare this measurement.");
    await addReference(page, { unit: "kV" });
    await page.reload();
    await page.locator("#mainNavComplianceBtn").click();
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
  });
});

// ============================================================ event alignment
// DEC-170: Compliance-LOCAL alignment. comparison_time = measurement_time - origin.
// It is not Waveform t0: no test below needs, or is affected by, a Waveform t0.
const alignBtn = (page, id) => page.locator(`#wwComplianceAlign${id}Btn`);

async function plotMeasuredAndReady(page, { treatment = "each_phase" } = {}) {
  await uploadMultibay(page);
  await addReference(page, { representation: "phase_ground_rms", unit: "kV", treatment });
  await openComplianceAndSelect(page, "KPDN1");
  await prepareAndWaitReady(page);
  await waitForMeasurement(page, treatment === "each_phase" ? 3 : 1);
}

// Alignment is an explicit mode: "Select Event Point" (or "Change Alignment") turns it on.
async function enterSelectionMode(page) {
  const wrap = page.locator("#wwComplianceChartWrap");
  if ((await wrap.getAttribute("data-selecting")) === "true") return;
  await (await alignBtn(page, "Change").isVisible() ? alignBtn(page, "Change") : alignBtn(page, "Select")).click();
  await expect(wrap).toHaveAttribute("data-selecting", "true");
  // The chart is re-laid-out (outline, no size change) -- wait until Plotly's box matches the DOM.
  await expect.poll(() => page.evaluate(() => {
    const el = document.getElementById("wwComplianceChartPlot");
    return Math.abs(el._fullLayout.width - el.getBoundingClientRect().width) <= 2 && Math.abs(el._fullLayout.height - el.getBoundingClientRect().height) <= 2;
  })).toBe(true);
}

// A REAL mouse click on sample `index` of measured trace `traceIndex` (in selection mode).
async function clickMeasuredSample(page, traceIndex, index) {
  await enterSelectionMode(page);
  const point = await page.evaluate(({ traceIndex, index }) => {
    const el = document.getElementById("wwComplianceChartPlot");
    const trace = el.data.filter((t) => t.meta && t.meta.role === "measurement")[traceIndex];
    const full = el._fullLayout;
    const x = full.xaxis._offset + full.xaxis.l2p(trace.x[index]);
    const y = full.yaxis._offset + full.yaxis.l2p(trace.y[index]);
    const r = el.getBoundingClientRect();
    return { x: r.left + x, y: r.top + y, raw: index / 1000 };
  }, { traceIndex, index });
  await page.mouse.move(point.x, point.y);
  await page.mouse.click(point.x, point.y);
  // A real click resolves to the nearest sample (a pixel is coarser than 1 ms): the selected
  // marker is the truth for what was picked.
  const marker = () => page.evaluate(() => {
    const m = document.getElementById("wwComplianceChartPlot").data.find((t) => t.meta && t.meta.role === "alignment-selection");
    return m ? m.meta.measurement_time : null;
  });
  await expect.poll(marker).not.toBeNull();
  const picked = await marker();
  expect(Math.abs(picked - point.raw)).toBeLessThan(0.01);
  return picked;
}
const sec = (v) => `${v.toFixed(3)} s`;
const idx = (v) => Math.round(v * 1000); // 1 kHz fixture: sample index == milliseconds

const xs = async (page) => (await chartTraces(page)).measurement.map((t) => t.x);

test.describe("DEC-170 -- Compliance Event Alignment", () => {
  test("not aligned: traces on the original recording axis, Set disabled, no Waveform wording", async ({ page }) => {
    await plotMeasuredAndReady(page);
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned");
    await expect(page.locator("#wwComplianceEventAlignmentSteps")).toContainText("Select the disturbance event on the Comparison Chart.");
    await expect(page.locator("#wwComplianceEventAlignmentSteps")).toContainText("Set that point as Reference t=0.");
    await expect(alignBtn(page, "Select")).toBeVisible();
    await expect(alignBtn(page, "Select")).toBeEnabled();
    await expect(alignBtn(page, "Set")).toBeHidden();
    await expect(page.locator("#pageCompliance")).not.toContainText("t0 in Waveform");
    const t = (await chartTraces(page)).measurement[0];
    expect(t.x[0]).toBe(0);
  });

  test("selecting a measured point (real click) shows its recording time and a marker; Set aligns it to Reference t=0; the Reference never moves", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const referenceBefore = (await chartTraces(page)).reference.map((t) => t.x);
    const raw = await clickMeasuredSample(page, 0, 550);
    await expect(page.locator("#wwComplianceAlignSelectedValue")).toHaveText(sec(raw));
    await expect(alignBtn(page, "Set")).toBeEnabled();
    const marker = await page.evaluate(() => document.getElementById("wwComplianceChartPlot").data.filter((t) => t.meta && t.meta.role === "alignment-selection"));
    expect(marker.length).toBe(1);
    expect(marker[0].x[0]).toBeCloseTo(raw, 9);
    // Selecting alone changes nothing yet.
    expect((await xs(page))[0][0]).toBe(0);

    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("✓ Event aligned");
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(raw));
    await expect(page.locator("#wwComplianceAlignReferencePosition")).toHaveText("0.000 s");
    await expect(page.locator("#wwComplianceAlignOffset")).toHaveText(`-${sec(raw)}`);
    const after = await chartTraces(page);
    // The picked sample now sits at comparison time 0.
    expect(after.measurement[0].x[idx(raw)]).toBeCloseTo(0, 9);
    expect(after.measurement[0].x[0]).toBeCloseTo(-raw, 9);
    expect(after.reference.map((t) => t.x)).toEqual(referenceBefore); // Reference stays fixed
    // No recalculation: y untouched.
    expect(after.measurement[0].y.length).toBeGreaterThan(100);
  });

  test("Each Phase: every trace shifts by the same offset", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const before = await xs(page);
    const raw = await clickMeasuredSample(page, 0, 600); // clicking a phase trace aligns the measurement as a whole
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceAlignOffset")).toHaveText(`-${sec(raw)}`);
    const after = await xs(page);
    expect(after.length).toBe(3);
    for (let i = 0; i < 3; i++) {
      expect(after[i].length).toBe(before[i].length);
      for (const k of [0, 100, after[i].length - 1]) expect(after[i][k]).toBeCloseTo(before[i][k] - raw, 9);
    }
  });

  test("fine shift: Earlier moves the measurement left by 1 ms, Later right; origin and offset reported exactly", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const raw = await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceAlignmentFineControls")).toBeVisible();
    await expect(page.locator("#wwComplianceAlignStepLabel")).toHaveText("1 ms");
    const base = (await xs(page))[0].slice(0, 5);

    await alignBtn(page, "Earlier").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(raw + 0.001));
    let now = (await xs(page))[0].slice(0, 5);
    for (let i = 0; i < 5; i++) expect(now[i]).toBeCloseTo(base[i] - 0.001, 9); // visibly LEFT (smaller x)

    await alignBtn(page, "Later").click();
    await alignBtn(page, "Later").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(raw - 0.001));
    now = (await xs(page))[0].slice(0, 5);
    for (let i = 0; i < 5; i++) expect(now[i]).toBeCloseTo(base[i] + 0.001, 9); // visibly RIGHT (larger x)
    await expect(page.locator("#wwComplianceAlignOffset")).toHaveText(`-${sec(raw - 0.001)}`);
  });

  test("Change Alignment re-selects (Cancel keeps the old one); Clear returns to the original recording axis", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const first = await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    await alignBtn(page, "Change").click();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Selecting event point...");
    await expect(alignBtn(page, "Set")).toBeDisabled();
    await alignBtn(page, "Cancel").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(first));

    await alignBtn(page, "Change").click();
    const second = await clickMeasuredSample(page, 0, 800);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(second));
    expect((await xs(page))[0][idx(second)]).toBeCloseTo(0, 9);

    await alignBtn(page, "Clear").click();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned");
    const cleared = (await xs(page))[0];
    expect(cleared[0]).toBe(0);
    expect(cleared[idx(second)]).toBeCloseTo(second, 9);
  });

  test("Minimum / Maximum: the single reduced trace shifts", async ({ page }) => {
    await plotMeasuredAndReady(page, { treatment: "minimum" });
    const picked = await clickMeasuredSample(page, 0, 600);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(picked));
    expect((await xs(page))[0][idx(picked)]).toBeCloseTo(0, 9);
  });

  test("a second Reference stays fixed and the same alignment applies against all of them; changing the Reference keeps it", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const picked = await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    const first = (await chartTraces(page)).reference.map((t) => t.x);
    await addReference(page, { name: "Second", representation: "phase_ground_rms", unit: "kV" });
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 3);
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(picked));
    const traces = await chartTraces(page);
    expect(traces.reference.length).toBeGreaterThan(first.length);
    expect(traces.measurement[0].x[idx(picked)]).toBeCloseTo(0, 9);
    for (const r of traces.reference) expect(r.x[0]).toBe(0);
  });

  test("changing the Bay / Measurement Group clears the alignment (documented)", async ({ page }) => {
    await plotMeasuredAndReady(page);
    await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("✓ Event aligned");
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "MCRS VOLTAGE" });
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned");
    await page.locator("#wwComplianceGroupSelect").selectOption({ label: "KPDN1 VOLTAGE" });
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned"); // never silently restored
  });

  test("alignment is not stored in the browser", async ({ page }) => {
    await plotMeasuredAndReady(page);
    await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    const keys = await page.evaluate(() => Object.keys(localStorage).filter((k) => /align/i.test(k)));
    expect(keys).toEqual([]);
  });
});

test.describe("DEC-170 -- independent from Waveform t0", () => {
  async function kpdn1Source(page) {
    const groups = await (await page.request.get(await wsUrl(page, "/compliance/voltage/measurement-groups"))).json();
    return groups.find((g) => g.display_name === "KPDN1 VOLTAGE").source_id;
  }

  test("setting, changing and clearing Waveform t0 never moves the Compliance alignment or traces", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const source = await kpdn1Source(page);
    const raw = (await xs(page))[0];
    // Waveform t0 first: the measured traces do not move, no alignment appears.
    expect((await page.request.put(await wsUrl(page, "/synchronization/t0"), { data: { source_id: source, t0_workspace_time: 0.5 } })).ok()).toBeTruthy();
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 3);
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("Not aligned");
    expect((await xs(page))[0]).toEqual(raw);

    // Compliance alignment, then change Waveform t0 again, then clear it.
    const picked = await clickMeasuredSample(page, 0, 700);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(picked));
    const aligned = (await xs(page))[0];
    await page.request.put(await wsUrl(page, "/synchronization/t0"), { data: { source_id: source, t0_workspace_time: 0.2 } });
    await page.request.delete(await wsUrl(page, "/synchronization/t0") + `?source_id=${source}`);
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 3);
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(picked));
    expect((await xs(page))[0]).toEqual(aligned);
  });

  test("changing and clearing the Compliance alignment never touches the Waveform t0", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const source = await kpdn1Source(page);
    await page.request.put(await wsUrl(page, "/synchronization/t0"), { data: { source_id: source, t0_workspace_time: 0.5 } });
    const t0 = async () => (await page.request.get(await wsUrl(page, "/synchronization/t0") + `?source_id=${source}`)).json();
    const before = await t0();
    await clickMeasuredSample(page, 0, 550);
    await alignBtn(page, "Set").click();
    await alignBtn(page, "Earlier").click();
    expect(await t0()).toEqual(before);
    await alignBtn(page, "Clear").click();
    expect(await t0()).toEqual(before);
  });
});

// =========================================================== compact Measurement
test.describe("DEC-169 -- Measurement card density", () => {
  test("a READY reference is a compact summary with channel detail behind 'Details'; blockers stay visible", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    // Action required: nothing hidden.
    await expect(page.locator(".ww-compliance-member-list")).toBeVisible();
    await expect(page.locator(".ww-compliance-details")).toHaveCount(0);
    await page.locator("#wwCompliancePrepareBtn").click();
    await expect(status(page)).toHaveText("✓ Ready for assessment");

    const details = page.locator(".ww-compliance-details");
    await expect(details).toHaveCount(1);
    await expect(details).not.toHaveAttribute("open", "");
    await expect(page.locator(".ww-compliance-member-list")).toBeHidden(); // collapsed
    await expect(page.locator('.ww-compliance-readiness-row[data-row="representation"]')).toBeVisible();
    await expect(page.locator('.ww-compliance-readiness-row[data-row="unit"]')).toBeVisible();
    await details.locator("summary").click();
    await expect(page.locator(".ww-compliance-member-list li")).toHaveCount(3);

    // An incompatible reference keeps its blocker visible with no expansion.
    await openComplianceAndSelect(page, "KPDN2");
    await expect(page.locator('.ww-compliance-readiness-row[data-row="incompatible"]')).toBeVisible();
  });
});

// ====================================================== UAT refinement (alignment UX)
// Reference t=0 stays visible INSIDE the plot; Event Alignment is a guided, explicit
// selection mode; the desktop workspace is fixed-height with an independently scrolling
// configuration column. The alignment maths/lifecycle are DEC-170's and are untouched.
async function t0Geometry(page) {
  return page.evaluate(() => {
    const el = document.getElementById("wwComplianceChartPlot");
    const label = [...el.querySelectorAll(".annotation-text")].find((n) => n.textContent.includes("Reference t=0"));
    const area = el.querySelector(".nsewdrag");
    const a = label && label.getBoundingClientRect();
    const p = area.getBoundingClientRect();
    const guide = (el.layout.shapes || []).find((s) => s.name === "reference-t0");
    return {
      hasLabel: !!label,
      label: a && { top: a.top, bottom: a.bottom, left: a.left, right: a.right },
      area: { top: p.top, bottom: p.bottom, left: p.left, right: p.right },
      guideX: guide ? guide.x0 : null,
      anchor: (el.layout.annotations || []).find((n) => n.name === "reference-t0-label"),
    };
  });
}
async function expectT0Inside(page) {
  await expect.poll(async () => {
    const g = await t0Geometry(page);
    if (!g.hasLabel) return "no label";
    const { label, area } = g;
    const inside = label.top >= area.top - 0.5 && label.bottom <= area.bottom + 0.5 && label.left >= area.left - 0.5 && label.right <= area.right + 0.5;
    return inside && g.guideX === 0 ? "inside" : JSON.stringify(g);
  }).toBe("inside");
}

test.describe("UAT refinement -- Reference t=0 label", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("the label sits inside the plotting area (paper-anchored), aligned or not, through resizes", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const g = await t0Geometry(page);
    expect(g.anchor.yref).toBe("paper"); // never tied to a y data value
    expect(g.anchor.yanchor).toBe("top"); // hangs from the top of the plotting area, not above it
    await expectT0Inside(page); // not aligned

    // splitter resize
    const handle = page.locator("#wwComplianceSplitHandle");
    const h = await handle.boundingBox();
    await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 120, h.y + h.height / 2, { steps: 5 });
    await page.mouse.up();
    await expectT0Inside(page);
    // window resize
    await page.setViewportSize({ width: 1280, height: 780 });
    await expectT0Inside(page);

    // aligned (the measurement moves, the Reference t=0 label does not leave the plot)
    await clickMeasuredSample(page, 0, 700);
    await alignBtn(page, "Set").click();
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("✓ Event aligned");
    await expectT0Inside(page);
    // autoscale: a y-range change must not matter
    await page.evaluate(() => Plotly.relayout("wwComplianceChartPlot", { "yaxis.range": [-5000, 90000] }));
    await expectT0Inside(page);
    await page.evaluate(() => Plotly.relayout("wwComplianceChartPlot", { "yaxis.autorange": true }));
    await expectT0Inside(page);
  });
});

test.describe("UAT refinement -- guided Event Alignment", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  const cursorOfDragLayer = (page) => page.evaluate(() => getComputedStyle(document.querySelector("#wwComplianceChartPlot .nsewdrag")).cursor);

  test("Select Event Point -> selecting -> preview -> Set -> Change/Cancel -> Clear", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const status = page.locator("#wwComplianceEventAlignmentEmptyState");
    const wrap = page.locator("#wwComplianceChartWrap");
    const banner = page.locator("#wwComplianceChartSelectBanner");

    // 1. Discoverable idle state.
    await expect(status).toHaveText("Not aligned");
    await expect(page.locator("#wwComplianceEventAlignmentSteps li")).toHaveCount(2);
    await expect(alignBtn(page, "Select")).toHaveText("Select Event Point");
    await expect(banner).toBeHidden();
    await expect(wrap).toHaveAttribute("data-selecting", "false");

    // 2. A plain chart click is NOT a selection.
    const probe = await page.evaluate(() => {
      const el = document.getElementById("wwComplianceChartPlot");
      const trace = el.data.filter((t) => t.meta && t.meta.role === "measurement")[0];
      const full = el._fullLayout;
      const r = el.getBoundingClientRect();
      return { x: r.left + full.xaxis._offset + full.xaxis.l2p(trace.x[600]), y: r.top + full.yaxis._offset + full.yaxis.l2p(trace.y[600]) };
    });
    await page.mouse.click(probe.x, probe.y);
    expect(await page.evaluate(() => document.getElementById("wwComplianceChartPlot").data.some((t) => t.meta && t.meta.role === "alignment-selection"))).toBe(false);
    await expect(status).toHaveText("Not aligned");

    // 3. Selection mode: instruction, banner on the chart, crosshair, Cancel.
    await alignBtn(page, "Select").click();
    await expect(status).toHaveText("Selecting event point...");
    await expect(page.locator("#wwComplianceEventAlignmentHint")).toHaveText("Click a measured trace where the disturbance starts.");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveText("Click a measured trace at the disturbance start");
    await expect(wrap).toHaveAttribute("data-selecting", "true");
    expect(await cursorOfDragLayer(page)).toBe("crosshair");
    await expect(alignBtn(page, "Cancel")).toBeVisible();
    await expect(alignBtn(page, "Set")).toBeDisabled();
    await expect(alignBtn(page, "Cancel")).toBeFocused(); // keyboard continuity, no focus trap

    // 4. A Reference curve can never be selected (explicit trace role, not legend text).
    await page.evaluate(() => {
      const el = document.getElementById("wwComplianceChartPlot");
      const curveNumber = el.data.findIndex((t) => t.meta && t.meta.role === "reference");
      window.wwComplianceOnChartClick({ points: [{ curveNumber, pointNumber: 0 }] });
    });
    expect(await page.evaluate(() => document.getElementById("wwComplianceChartPlot").data.some((t) => t.meta && t.meta.role === "alignment-selection"))).toBe(false);
    await expect(page.locator("#wwComplianceEventAlignmentHint")).toContainText("Reference curve");
    await expect(alignBtn(page, "Set")).toBeDisabled();

    // 5. A measured trace click selects a real sample: marker, preview guide, selected time.
    const raw = await clickMeasuredSample(page, 0, 650);
    await expect(page.locator("#wwComplianceAlignSelectedValue")).toHaveText(sec(raw));
    await expect(alignBtn(page, "Set")).toBeEnabled();
    await expect(alignBtn(page, "Again")).toBeVisible();
    await expect(alignBtn(page, "Cancel")).toBeVisible();
    const preview = await page.evaluate(() => document.getElementById("wwComplianceChartPlot").layout.shapes.filter((s) => s.type === "line" && s.x0 === s.x1 && s.x0 !== 0));
    expect(preview.length).toBe(1);
    expect(preview[0].x0).toBeCloseTo(raw, 9);
    expect((await xs(page))[0][0]).toBe(0); // nothing committed on the first click

    // 6. Choose Again discards the preview but stays in selection mode.
    await alignBtn(page, "Again").click();
    await expect(wrap).toHaveAttribute("data-selecting", "true");
    await expect(page.locator("#wwComplianceAlignmentSelected")).toBeHidden();
    expect(await page.evaluate(() => document.getElementById("wwComplianceChartPlot").data.some((t) => t.meta && t.meta.role === "alignment-selection"))).toBe(false);
    const second = await clickMeasuredSample(page, 0, 550);

    // 7. Commit: the mode ends (no lingering crosshair) and the summary says "Reference t=0".
    await alignBtn(page, "Set").click();
    await expect(status).toHaveText("✓ Event aligned");
    await expect(wrap).toHaveAttribute("data-selecting", "false");
    await expect(banner).toBeHidden();
    await expect(wrap).not.toHaveClass(/ww-compliance-selecting/); // the selection-mode cursor/outline is gone
    await expect(page.locator("#wwComplianceAlignmentSummary")).toContainText("Reference t=0");
    await expect(page.locator("#wwComplianceAlignmentSummary")).not.toContainText("Reference position");
    await expect(page.locator("#wwComplianceAlignReferencePosition")).toHaveText("0.000 s");
    await expect(page.locator("#wwComplianceAlignOffset")).toHaveText(`-${sec(second)}`);
    expect((await xs(page))[0][idx(second)]).toBeCloseTo(0, 9);

    // 8. Change keeps the active alignment until a replacement is confirmed; Cancel retains it.
    const before = (await xs(page))[0];
    await alignBtn(page, "Change").click();
    await expect(status).toHaveText("Selecting event point...");
    expect((await xs(page))[0]).toEqual(before); // still aligned while choosing
    await clickMeasuredSample(page, 0, 900);
    await alignBtn(page, "Cancel").click();
    await expect(status).toHaveText("✓ Event aligned");
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(second));
    expect((await xs(page))[0]).toEqual(before);
    await expect(wrap).toHaveAttribute("data-selecting", "false");

    // Escape leaves the mode too, and keeps the alignment.
    await alignBtn(page, "Change").click();
    await expect(wrap).toHaveAttribute("data-selecting", "true");
    await page.keyboard.press("Escape");
    await expect(wrap).toHaveAttribute("data-selecting", "false");
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(second));

    // 9. Fine shift still works; Clear restores the original axis.
    await alignBtn(page, "Earlier").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(second + 0.001));
    await alignBtn(page, "Later").click();
    await expect(page.locator("#wwComplianceAlignMeasurementEvent")).toHaveText(sec(second));
    await alignBtn(page, "Clear").click();
    await expect(status).toHaveText("Not aligned");
    expect((await xs(page))[0][idx(second)]).toBeCloseTo(second, 9);
    await expect(alignBtn(page, "Select")).toBeVisible();
  });
});

// =============================================== fixed-height desktop workspace
test.describe("UAT refinement -- fixed-height desktop workspace", () => {
  test.use({ viewport: { width: 1440, height: 760 } });

  const geometry = (page) => page.evaluate(() => {
    const r = (id) => { const b = document.getElementById(id).getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, height: b.height, width: b.width }; };
    const page_ = document.getElementById("pageCompliance");
    const col = document.getElementById("wwComplianceConfigColumn");
    return {
      split: r("wwComplianceSplit"), left: r("wwComplianceConfigColumn"), right: r("wwComplianceChartColumn"),
      nav: r("wwComplianceTypeNav"), shell: r("wwComplianceShell"), status: r("bottomStatusBar"), chart: r("wwComplianceChartPanel"),
      pageScroll: page_.scrollHeight - page_.clientHeight,
      docScroll: document.documentElement.scrollHeight - document.documentElement.clientHeight,
      docScrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      leftOverflow: col.scrollHeight - col.clientHeight, leftOverflowY: getComputedStyle(col).overflowY, leftTop: col.scrollTop,
    };
  });

  test("the workspace fits the viewport, never overlaps the status bar, and does not scroll as a page", async ({ page }) => {
    await plotMeasuredAndReady(page);
    for (const size of [{ width: 1440, height: 760 }, { width: 1280, height: 900 }, { width: 1600, height: 1000 }]) {
      await page.setViewportSize(size);
      await expect.poll(async () => { const g = await geometry(page); return g.split.bottom <= g.status.top + 1; }).toBe(true);
      const g = await geometry(page);
      expect(g.pageScroll).toBeLessThanOrEqual(1); // the page itself does not grow vertically
      expect(g.docScroll).toBeLessThanOrEqual(1);
      expect(g.docScrollX).toBeLessThanOrEqual(1); // no page-level horizontal scroll
      expect(g.split.bottom).toBeLessThanOrEqual(g.status.top + 1);
      expect(g.right.bottom).toBeLessThanOrEqual(g.status.top + 1);
      expect(g.chart.height).toBeGreaterThan(250);
      // The drawn Plotly chart fills its box and sits above the footer.
      await expect.poll(() => page.evaluate(() => { const el = document.getElementById("wwComplianceChartPlot"); const b = el.getBoundingClientRect(); return Math.abs(el._fullLayout.width - b.width) <= 2 && Math.abs(el._fullLayout.height - b.height) <= 2; })).toBe(true);
      const bottom = await page.evaluate(() => document.getElementById("wwComplianceChartPlot").getBoundingClientRect().bottom);
      expect(bottom).toBeLessThanOrEqual(g.status.top + 1);
      // The Functions/Voltage card shares the workspace's bottom edge.
      expect(Math.abs(g.nav.bottom - g.left.bottom)).toBeLessThanOrEqual(1);
      expect(Math.abs(g.nav.bottom - g.right.bottom)).toBeLessThanOrEqual(1);
    }
  });

  test("Functions/Voltage card shares the workspace bottom edge, and the chart owns the full panel height (no note strip)", async ({ page }) => {
    await plotMeasuredAndReady(page);
    const aligned = async () => {
      const g = await geometry(page);
      expect(Math.abs(g.nav.bottom - g.left.bottom)).toBeLessThanOrEqual(1);
      expect(Math.abs(g.nav.bottom - g.right.bottom)).toBeLessThanOrEqual(1);
      expect(Math.abs(g.nav.bottom - g.shell.bottom)).toBeLessThanOrEqual(1);
      expect(g.nav.bottom).toBeLessThanOrEqual(g.status.top + 1);
    };
    // No notes/legend strip: the Plotly area runs to the panel's bottom padding.
    const chartFill = () => page.evaluate(() => {
      const panel = document.getElementById("wwComplianceChartPanel");
      const wrap = document.getElementById("wwComplianceChartWrap").getBoundingClientRect();
      const plot = document.getElementById("wwComplianceChartPlot");
      const pb = parseFloat(getComputedStyle(panel).paddingBottom) || 0;
      return {
        gap: panel.getBoundingClientRect().bottom - pb - wrap.bottom,
        sizeMatches: Math.abs(plot._fullLayout.height - plot.getBoundingClientRect().height) <= 2 && Math.abs(plot._fullLayout.width - plot.getBoundingClientRect().width) <= 2,
        legendInside: !!plot.querySelector(".legend"), t0Label: [...plot.querySelectorAll(".annotation-text")].some((n) => n.textContent === "Reference t=0"),
        noteStrips: ["wwComplianceChartLegend", "wwComplianceChartMeasurementNote"].filter((id) => document.getElementById(id)).length,
        wrapH: wrap.height,
      };
    });
    await expect(page.locator("#wwComplianceChartPanel")).not.toContainText("Measurement aligned");
    await aligned();
    let f = await chartFill();
    expect(f.gap).toBeLessThanOrEqual(1);
    expect(f.noteStrips).toBe(0);
    expect(f.legendInside && f.t0Label).toBe(true);
    // Window resize.
    for (const size of [{ width: 1280, height: 900 }, { width: 1600, height: 1000 }, { width: 1440, height: 760 }]) {
      await page.setViewportSize(size);
      await expect.poll(async () => (await chartFill()).sizeMatches).toBe(true);
      await aligned();
      f = await chartFill();
      expect(f.gap).toBeLessThanOrEqual(1);
    }
    // Splitter drag.
    const h = await page.locator("#wwComplianceSplitHandle").boundingBox();
    const y = h.y + h.height / 2;
    await page.mouse.move(h.x + h.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 150, y, { steps: 6 });
    await page.mouse.up();
    await expect.poll(async () => (await chartFill()).sizeMatches).toBe(true);
    await aligned();
    expect((await chartFill()).gap).toBeLessThanOrEqual(1);
  });

  test("the left column scrolls on its own while the Comparison Chart stays put; the splitter still works", async ({ page }) => {
    await uploadMultibay(page);
    for (const n of ["Alpha", "Bravo", "Charlie", "Delta"]) await addReference(page, { name: `${n} grid requirement`, representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator("#wwComplianceChartPlot")).toBeVisible();
    const before = await geometry(page);
    expect(before.leftOverflowY).toBe("auto");
    expect(before.leftOverflow).toBeGreaterThan(20); // the configuration really is taller than the column
    expect(before.pageScroll).toBeLessThanOrEqual(1);

    await page.locator("#wwComplianceConfigColumn").hover();
    await page.mouse.wheel(0, 400);
    await expect.poll(async () => (await geometry(page)).leftTop).toBeGreaterThan(50);
    const scrolled = await geometry(page);
    expect(scrolled.pageScroll).toBeLessThanOrEqual(1);
    expect(Math.abs(scrolled.chart.top - before.chart.top)).toBeLessThanOrEqual(1); // the chart did not move
    expect(Math.abs(scrolled.chart.bottom - before.chart.bottom)).toBeLessThanOrEqual(1);
    expect(scrolled.left.top).toBeCloseTo(before.left.top, 0);

    // The handle is reachable while the left column is scrolled, and Plotly follows the drag.
    const handle = page.locator("#wwComplianceSplitHandle");
    const h = await handle.boundingBox();
    const y = h.y + h.height / 2;
    await page.mouse.move(h.x + h.width / 2, y);
    await page.mouse.down();
    await page.mouse.move(h.x + h.width / 2 + 120, y, { steps: 5 });
    await page.mouse.up();
    const dragged = await geometry(page);
    expect(dragged.left.width).toBeGreaterThan(before.left.width + 80);
    expect(dragged.leftTop).toBeGreaterThan(50); // still scrolled
    await expect.poll(() => page.evaluate(() => { const el = document.getElementById("wwComplianceChartPlot"); return Math.abs(el._fullLayout.width - el.getBoundingClientRect().width); })).toBeLessThanOrEqual(2);
    expect(dragged.right.bottom).toBeLessThanOrEqual(dragged.status.top + 1);
  });

  test("keyboard: focusing an off-screen control scrolls it into view inside the column", async ({ page }) => {
    await uploadMultibay(page);
    for (const n of ["Alpha", "Bravo", "Charlie", "Delta"]) await addReference(page, { name: `${n} grid requirement`, representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 3);
    await page.evaluate(() => { document.getElementById("wwComplianceConfigColumn").scrollTop = 0; });
    await alignBtn(page, "Select").focus();
    const inView = await page.evaluate(() => {
      const col = document.getElementById("wwComplianceConfigColumn").getBoundingClientRect();
      const b = document.getElementById("wwComplianceAlignSelectBtn").getBoundingClientRect();
      return b.top >= col.top - 1 && b.bottom <= col.bottom + 1;
    });
    expect(inView).toBe(true);
    expect((await geometry(page)).pageScroll).toBeLessThanOrEqual(1);
  });
});

test.describe("UAT refinement -- small screens stack and scroll normally", () => {
  test.use({ viewport: { width: 900, height: 800 } });

  test("stacked: no resize handle, the left column does not scroll on its own, the page scrolls, the chart stays usable", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await expect(page.locator("#wwComplianceSplitHandle")).toBeHidden();
    const info = await page.evaluate(() => {
      const col = document.getElementById("wwComplianceConfigColumn");
      const p = document.getElementById("pageCompliance");
      const chart = document.getElementById("wwComplianceChartWrap").getBoundingClientRect();
      return { colOverflow: getComputedStyle(col).overflowY, pageOverflow: getComputedStyle(p).overflowY, pageScrolls: p.scrollHeight > p.clientHeight, chartHeight: chart.height, chartWidth: chart.width, scrollX: document.documentElement.scrollWidth - document.documentElement.clientWidth };
    });
    expect(info.colOverflow).toBe("visible");
    expect(info.pageOverflow).toBe("auto");
    expect(info.pageScrolls).toBe(true); // normal page scrolling reaches the chart/results
    expect(info.chartHeight).toBeGreaterThanOrEqual(400);
    expect(info.chartWidth).toBeGreaterThan(400);
    expect(info.scrollX).toBeLessThanOrEqual(1);
    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 3);
    await expectT0Inside(page);
  });
});
