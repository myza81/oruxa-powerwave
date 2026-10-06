// Compliance & Capability -- the resizable two-column workspace and the
// measured traces on the Comparison Chart (DEC-169).
//
//   LEFT   Reference Layers / Measurement (incl. Event Alignment)
//          <-> draggable divider <->
//   RIGHT  Comparison Chart
//   BELOW  Results
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

  test("Reference + Measurement (+ Event Alignment) on the left, the chart on the right, Results below", async ({ page }) => {
    await page.goto("/index.html");
    await page.locator("#mainNavComplianceBtn").click();
    const left = page.locator("#wwComplianceConfigColumn");
    const right = page.locator("#wwComplianceChartColumn");
    await expect(left.locator("#wwComplianceReferenceLayersCard")).toBeVisible();
    await expect(left.locator("#wwComplianceMeasurementCard")).toBeVisible();
    await expect(left.locator("#wwComplianceMeasurementCard #wwComplianceEventAlignmentSection")).toBeVisible();
    await expect(right.locator("#wwComplianceChartPanel")).toBeVisible();
    await expect(page.locator("#wwComplianceSplit #wwComplianceResultsPanel")).toHaveCount(0); // Results are NOT inside the split

    const split = await box(page, "#wwComplianceSplit");
    const l = await box(page, "#wwComplianceConfigColumn");
    const r = await box(page, "#wwComplianceChartColumn");
    const results = await box(page, "#wwComplianceResultsPanel");
    expect(l.x).toBeLessThan(r.x);
    expect(Math.abs(l.y - r.y)).toBeLessThanOrEqual(1); // side by side
    expect(results.y).toBeGreaterThanOrEqual(split.y + split.height - 1); // Results below the split
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
    const results = await box(page, "#wwComplianceResultsPanel");
    expect(reference.y).toBeLessThan(measurement.y);
    expect(measurement.y).toBeLessThan(chart.y);
    expect(chart.y).toBeLessThan(results.y);
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
    await expect(page.locator("#wwComplianceChartMeasurementNote")).toContainText("Reference envelope ready. Measurement requires configuration before it can be plotted.");

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
    await expect(page.locator("#wwComplianceChartMeasurementNote")).toContainText("No event reference (t0) set");
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
    await expect(page.locator("#wwComplianceChartMeasurementNote")).toContainText("Measurement requires configuration before it can be plotted.");
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
    await expect(page.locator("#wwComplianceChartMeasurementNote")).toContainText("Select a Bay / Measurement Group to plot a measurement against this Reference.");
  });
});

// ============================================================ event alignment
test.describe("DEC-169 -- event alignment of the plotted measurement", () => {
  test("the measured trace follows the workspace t0, like the Reference's event-relative axis", async ({ page }) => {
    await uploadMultibay(page);
    await addReference(page, { representation: "phase_ground_rms", unit: "kV" });
    await openComplianceAndSelect(page, "KPDN1");
    await prepareAndWaitReady(page);
    await waitForMeasurement(page, 3);
    const raw = (await chartTraces(page)).measurement[0];
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toHaveText("No event reference set");
    await expect(page.locator("#wwComplianceEventAlignmentHint")).toContainText("recording's own time axis");

    const groups = await (await page.request.get(await wsUrl(page, "/compliance/voltage/measurement-groups"))).json();
    const kpdn1 = groups.find((g) => g.display_name === "KPDN1 VOLTAGE");
    const t0 = 0.5;
    const put = await page.request.put(await wsUrl(page, "/synchronization/t0"), { data: { source_id: kpdn1.source_id, t0_workspace_time: t0 } });
    expect(put.ok()).toBeTruthy();
    await page.reload();
    await openComplianceAndSelect(page, "KPDN1");
    await waitForMeasurement(page, 3);
    const aligned = (await chartTraces(page)).measurement[0];
    expect(aligned.x[0]).toBeCloseTo(raw.x[0] - t0, 9);
    expect(aligned.x[aligned.x.length - 1]).toBeCloseTo(raw.x[raw.x.length - 1] - t0, 9);
    expect(aligned.y).toEqual(raw.y);
    await expect(page.locator("#wwComplianceEventAlignmentEmptyState")).toContainText("Event reference (t0) = 0.5 s");
    await expect(page.locator("#wwComplianceEventAlignmentHint")).toBeHidden();
    await expect(page.locator("#wwComplianceChartMeasurementNote")).toBeHidden();
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
