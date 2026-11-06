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

async function open(page, source) {
  await page.locator("#wwOpenPerUnitSettingsBtn").click();
  await page.locator("#wwOpenPerUnitProfilesFromSettingsBtn").click();
  await page.locator("#perUnitSourceSelect").selectOption(source);
  await page.locator('input[name="perUnitCurrentBaseMode"][value="derived"]').check();
}

async function enter(page, voltage, rating) {
  await page.locator("#perUnitVoltageBaseValue").fill(String(voltage));
  await page.locator("#perUnitApparentPowerBaseValue").fill(String(rating));
}

async function save(page, config, status = 200) {
  const response = page.waitForResponse(r => r.url() === config && r.request().method() === "PUT");
  await page.locator("#perUnitProfilesApplyBtn").click();
  return json(await response, status);
}

for (const [voltage, rating, expectedKa] of [
  [132, 1000, 4.373865675678983],
  [275, 1000, 2.099455524325912],
  [1e300, 1e308, 57735026.91896258],
  [Number.MIN_VALUE, Number.MIN_VALUE, 0.5773502691896258],
  [1, 1e-320, 5.776e-321],
]) {
  test(`derived preview agrees with accepted backend: ${rating} MVA / ${voltage} kV`, async ({ page }) => {
    const c = await setup(page);
    const groupsUrl = `${c.root}/sources/${c.source}/measurement-groups`;
    const groupsBefore = await json(await page.request.get(groupsUrl));
    const engineeringUrl = `${c.root}/sources/${c.source}/waveform?channel_name=IA`;
    const engineeringBefore = await json(await page.request.get(engineeringUrl));
    await open(page, c.source);
    await enter(page, voltage, rating);
    const preview = page.locator("#perUnitCalculatedCurrentBase");
    await expect(preview).toBeVisible();
    const text = await preview.inputValue();
    expect(text).toMatch(/ kA$/);
    const value = Number(text.slice(0, -3));
    expect(Number.isFinite(value)).toBe(true);
    expect(value).toBeGreaterThan(0);
    expect(Math.abs(value - expectedKa)).toBeLessThanOrEqual(Math.max(Math.abs(expectedKa) * 1e-12, expectedKa < 0.00005 ? Number.MIN_VALUE : 0.00005));
    const accepted = await save(page, c.config);
    expect(accepted.resolved_current_base.unit).toBe("A");
    const backendKa = accepted.resolved_current_base.value / 1000;
    expect(Math.abs(value - backendKa)).toBeLessThanOrEqual(Math.max(Math.abs(backendKa) * 1e-12, backendKa < 0.00005 ? Number.MIN_VALUE : 0.00005));
    expect(accepted.voltage_base_value).toBe(voltage);
    expect(accepted.apparent_power_base_value).toBe(rating);
    expect(await json(await page.request.get(groupsUrl))).toEqual(groupsBefore);
    expect(await json(await page.request.get(engineeringUrl))).toEqual(engineeringBefore);
    await expect(page.locator("#perUnitProfilesOverlay")).toBeHidden();
    await open(page, c.source);
    expect(await preview.inputValue()).toBe(text);
    await expect(page.locator("#perUnitVoltageBaseValue")).toHaveValue(String(voltage));
    await expect(page.locator("#perUnitApparentPowerBaseValue")).toHaveValue(String(rating));
  });
}

test("unusable bases show no fabricated preview and rejected saves preserve configuration", async ({ page }) => {
  const c = await setup(page);
  await open(page, c.source); await enter(page, 275, 1000);
  await save(page, c.config);
  const accepted = await json(await page.request.get(c.config));
  await open(page, c.source);
  for (const [voltage, rating] of [[275, 1e308], [1e308, 1000], [100, Number.MIN_VALUE], [275, 0], [275, -1]]) {
    await enter(page, voltage, rating);
    await expect(page.locator("#perUnitCalculatedCurrentBase")).toHaveValue("—");
    await save(page, c.config, 400);
    await expect(page.locator("#perUnitProfileError")).toBeVisible();
    expect(await json(await page.request.get(c.config))).toEqual(accepted);
  }
  await page.locator("#perUnitApparentPowerBaseValue").fill("");
  await expect(page.locator("#perUnitCalculatedCurrentBase")).toHaveValue("—");
  const invalid = await page.evaluate(() => [NaN, Infinity, -Infinity, null, "bad"].map(value =>
    wwPerUnitEditorResolvedCurrentBaseText({ currentBaseMode: "derived", voltageBaseValue: 275,
      apparentPowerBaseValue: value, voltageReferenceMode: "auto", autoDetection: { reference: "line_to_ground" } })));
  expect(invalid).toEqual(Array(5).fill("—"));
});

test("auto and manual L-G/L-L references keep the nominal L-L current base", async ({ page }) => {
  const c = await setup(page);
  await open(page, c.source); await enter(page, 275, 1000);
  const initial = await json(await page.request.get(c.config));
  await expect(page.locator("#perUnitCalculatedCurrentBase")).toHaveValue("2.0995 kA");
  await page.locator("#perUnitOverrideReferenceBtn").click();
  for (const reference of ["line_to_line", "line_to_ground"]) {
    await page.locator("#perUnitVoltageReferenceOverride").selectOption(reference);
    await expect(page.locator("#perUnitCalculatedCurrentBase")).toHaveValue("2.0995 kA");
    expect(await json(await page.request.get(c.config))).toEqual(initial);
  }
  const accepted = await save(page, c.config);
  expect(accepted.voltage_reference_mode).toBe("manual");
  expect(accepted.resolved_current_base.value).toBeCloseTo(2099.455524325912, 9);
  await open(page, c.source);
  await page.locator("#perUnitReturnToAutoBtn").click();
  await expect(page.locator("#perUnitCalculatedCurrentBase")).toHaveValue("2.0995 kA");
  const automatic = await save(page, c.config);
  expect(automatic.voltage_reference_mode).toBe("auto");
  expect(automatic.resolved_current_base).toEqual(accepted.resolved_current_base);
});
