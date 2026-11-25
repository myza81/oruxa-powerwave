// Source Default derived Current base (kV + MVA -> kA): real backend numerics and
// atomic rejection.
//
// P0 remediation (PU-MIG): the Source Default editor (#perUnitProfilesOverlay, its
// live "calculated current base" preview and #perUnitProfileError) was removed from
// the frontend by PU-UI-001 Step B (commit be1e7e0): "Recording Details is now the SSOT
// for per-unit configuration. DEC-049 Source Default backend storage is preserved for
// ungrouped fallback." No Recording Details control edits a Source Default, so this
// spec drives the same real endpoint the retired editor called
// (PUT /per-unit/sources/{source}) with the same request body and keeps every
// engineering assertion about the backend: the accepted derived base (against
// independently computed kA values, including the numeric extremes), the atomic
// rejection of unusable bases with the backend's own message, the unchanged groups
// and engineering samples, and the unchanged nominal L-L current base across
// reference choices. Nothing is mocked.
//
// Retired with the editor (reported in the P0 remediation handover): the
// client-side preview field, the preview-vs-backend comparison, the visible-error
// element, and the retired helper wwPerUnitEditorResolvedCurrentBaseText().
const { test, expect } = require("./support/test");
const { uploadRecord, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

const BACKEND = `http://127.0.0.1:${process.env.PW_BACKEND_PORT || "8000"}`;

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

async function setup(page) {
  await page.goto("/index.html");
  await uploadRecord(page, { station: "PREVIEW_BASE", startClock: "10:00:00.000000", durationS: 0.1 });
  const workspace = await workspaceId(page);
  const source = await sourceIdFor(page, "PREVIEW_BASE");
  const root = `${BACKEND}/api/v1/workspaces/${workspace}`;
  await page.locator("#mainNavWaveformBtn").click();
  return { source, root, config: `${root}/per-unit/sources/${source}` };
}

// The body the retired Source Default editor sent for a derived Current base.
function derived(voltage, rating, reference = {}) {
  return {
    voltage_base_value: voltage,
    voltage_reference_mode: reference.mode || "auto",
    voltage_reference_override: reference.mode === "manual" ? reference.override : null,
    current_base_mode: "derived",
    apparent_power_base_value: rating,
    direct_current_base_value: null,
    current_base_reference_side: "primary",
  };
}

async function save(page, config, body, status = 200) {
  return json(await page.request.put(config, { data: body }), status);
}

for (const [voltage, rating, expectedKa] of [
  [132, 1000, 4.373865675678983],
  [275, 1000, 2.099455524325912],
  [1e300, 1e308, 57735026.91896258],
  [Number.MIN_VALUE, Number.MIN_VALUE, 0.5773502691896258],
  [1, 1e-320, 5.776e-321],
]) {
  test(`derived current base agrees with the independent kA value on the accepted backend: ${rating} MVA / ${voltage} kV`, async ({ page }) => {
    const c = await setup(page);
    const groupsUrl = `${c.root}/sources/${c.source}/measurement-groups`;
    const groupsBefore = await json(await page.request.get(groupsUrl));
    const engineeringUrl = `${c.root}/sources/${c.source}/waveform?channel_name=IA`;
    const engineeringBefore = await json(await page.request.get(engineeringUrl));
    const accepted = await save(page, c.config, derived(voltage, rating));
    expect(accepted.resolved_current_base.unit).toBe("A");
    const backendKa = accepted.resolved_current_base.value / 1000;
    expect(Number.isFinite(backendKa)).toBe(true);
    expect(backendKa).toBeGreaterThan(0);
    expect(Math.abs(backendKa - expectedKa)).toBeLessThanOrEqual(Math.max(Math.abs(expectedKa) * 1e-12, expectedKa < 0.00005 ? Number.MIN_VALUE : 0.00005));
    expect(accepted.voltage_base_value).toBe(voltage);
    expect(accepted.apparent_power_base_value).toBe(rating);
    expect(await json(await page.request.get(groupsUrl))).toEqual(groupsBefore);
    expect(await json(await page.request.get(engineeringUrl))).toEqual(engineeringBefore);
    // The accepted configuration is what the backend now stores, unchanged by reading it back.
    const stored = await json(await page.request.get(c.config));
    expect(stored.voltage_base_value).toBe(voltage);
    expect(stored.apparent_power_base_value).toBe(rating);
    expect(stored.resolved_current_base).toEqual(accepted.resolved_current_base);
  });
}

test("unusable bases are rejected by the backend with its own message and rejected saves preserve configuration", async ({ page }) => {
  const c = await setup(page);
  await save(page, c.config, derived(275, 1000));
  const accepted = await json(await page.request.get(c.config));
  for (const [voltage, rating] of [[275, 1e308], [1e308, 1000], [100, Number.MIN_VALUE], [275, 0], [275, -1]]) {
    const rejected = await json(await page.request.put(c.config, { data: derived(voltage, rating) }), 400);
    // The message the editor used to show in its error element.
    expect(typeof rejected.detail.message).toBe("string");
    expect(rejected.detail.message.length).toBeGreaterThan(0);
    expect(await json(await page.request.get(c.config))).toEqual(accepted);
  }
});

test("auto and manual L-G/L-L references keep the nominal L-L current base", async ({ page }) => {
  const c = await setup(page);
  const initial = await save(page, c.config, derived(275, 1000));
  expect(initial.voltage_reference_mode).toBe("auto");
  expect(initial.resolved_current_base.value).toBeCloseTo(2099.455524325912, 9);
  let accepted;
  for (const reference of ["line_to_line", "line_to_ground"]) {
    accepted = await save(page, c.config, derived(275, 1000, { mode: "manual", override: reference }));
    expect(accepted.voltage_reference_mode).toBe("manual");
    expect(accepted.resolved_current_base.value).toBeCloseTo(2099.455524325912, 9);
    expect(accepted.resolved_current_base).toEqual(initial.resolved_current_base);
  }
  expect(accepted.voltage_reference_mode).toBe("manual");
  const automatic = await save(page, c.config, derived(275, 1000));
  expect(automatic.voltage_reference_mode).toBe("auto");
  expect(automatic.resolved_current_base).toEqual(accepted.resolved_current_base);
});
