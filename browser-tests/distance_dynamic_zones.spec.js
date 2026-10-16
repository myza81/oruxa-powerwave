// Slice 10 -- Dynamic Distance Protection zones: zone count is not a special limitation.
//
// An enabled fifth/sixth zone that arrives from an Apply is treated exactly like any other
// supported distance zone: it gets a card (labelled with the source's own name), is plotted by
// the same generic zone loop, is evaluated by the backend, takes part in Fit Zones, and is
// removed again by the next Apply. Runs against LOCAL code.
//
// Most cases feed `wwDistanceApplyImportedSettings()` a payload shaped exactly like the backend's
// `ApplySettingsOut` (the backend suite pins that shape against real canonical models); one case
// drives the whole path against the real backend with the P441 sample.

const { test, expect } = require("@playwright/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

test.beforeEach(async ({ page }) => {
  await routeConfig(page);
});

// ---- payload builders ---------------------------------------------------------------------

const quad = (id, name, o = {}) => ({
  id, display_name: name, enabled: true, direction: "forward", delay_s: 0.5, characteristic_angle_deg: 80,
  reach_ohm: null, reactive_reach_ohm: 10, resistive_reach_forward_ohm: 6, resistive_reach_reverse_ohm: 2, ...o,
});
const disabled = (id, name, direction = "forward") => ({
  id, display_name: name, enabled: false, direction, delay_s: null, characteristic_angle_deg: null,
  reach_ohm: null, reactive_reach_ohm: null, resistive_reach_forward_ohm: null, resistive_reach_reverse_ohm: null,
});
const standard = () => [
  quad("Z1", "Zone 1", { reactive_reach_ohm: 4, resistive_reach_forward_ohm: 3, delay_s: 0 }),
  quad("Z2", "Zone 2", { reactive_reach_ohm: 7, resistive_reach_forward_ohm: 5, delay_s: 0.3 }),
  quad("Z3", "Zone 3", { reactive_reach_ohm: 12, resistive_reach_forward_ohm: 8, delay_s: 3 }),
  disabled("Z4", "Zone 4", "reverse"),
];
const payload = (zones, characteristic = "quadrilateral") => ({ characteristic, impedance_basis: "secondary", zones });
const apply = (page, p) => page.evaluate((x) => wwDistanceApplyImportedSettings(x), p);

// ---- page helpers -------------------------------------------------------------------------

const cards = (page) => page.locator("#wwDistancePanel .ww-dist-zone-card");
const extraCards = (page) => page.locator("#wwDistancePanel [data-zone-dynamic]");
const titles = (page) => cards(page).locator(".ww-dist-zone-card-title").allTextContents();
const boundary = (page, key) => page.locator(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${key}"]`);
const boundaries = (page) => page.locator("#wwDistanceSvg .ww-dist-zone-boundary");
const legendItems = (page) => page.locator("#wwDistanceZoneLegend .ww-dist-zone-legend-item");
const zoneRow = (page, label) => page.locator("#wwDistanceZoneStateList .ww-oc-value-row", { hasText: label });
const points = (page, key) =>
  boundary(page, key).evaluate((el) => el.getAttribute("points").split(" ").map((p) => p.split(",").map(Number)));
const view = (page) => page.evaluate(() => (wwDistanceState.view ? { ...wwDistanceState.view } : null));

async function leg(page, key, magnitude, unit, angleDeg) {
  await page.locator(`#wwDistanceManual${key}UnitSelect`).selectOption(unit);
  await page.locator(`#wwDistanceManual${key}MagnitudeInput`).fill(String(magnitude));
  await page.locator(`#wwDistanceManual${key}MagnitudeInput`).dispatchEvent("change");
  await page.locator(`#wwDistanceManual${key}AngleInput`).fill(String(angleDeg));
  await page.locator(`#wwDistanceManual${key}AngleInput`).dispatchEvent("change");
}
// Zab = 10 /_ 20 deg; adding 180 deg to both currents makes it 10 /_ 200 deg.
async function enterLoop(page, currentOffsetDeg) {
  await page.locator("#wwDistanceManualVoltageBasisSelect").selectOption("secondary");
  await page.locator("#wwDistanceManualCurrentBasisSelect").selectOption("secondary");
  await leg(page, "V1", 100, "V", 0);
  await leg(page, "V2", 100, "V", -120);
  await leg(page, "I1", 10, "A", -20 + currentOffsetDeg);
  await leg(page, "I2", 10, "A", -140 + currentOffsetDeg);
}

const insideSvg = (page, selector) =>
  page.evaluate((sel) => {
    const s = document.getElementById("wwDistanceSvg").getBoundingClientRect();
    const b = document.querySelector(sel).getBoundingClientRect();
    return Math.min(b.left - s.left, s.right - b.right, b.top - s.top, s.bottom - b.bottom);
  }, selector);

// ---- the standard form is unchanged -----------------------------------------------------------

test("the manual form starts with the same standard zone set and no extra zone", async ({ page }) => {
  await openDistance(page);
  await expect(cards(page)).toHaveCount(4);
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Reverse Zone"]);
  await expect(extraCards(page)).toHaveCount(0);
  await expect(page.locator("#wwDistanceZone4Direction")).toHaveText("Direction: Reverse");
  await expect(page.locator("#wwDistanceZoneLegend")).toBeHidden(); // nothing is drawn yet
  await expect(page.locator("#wwDistanceZoneStateList .ww-oc-value-row")).toHaveCount(4);
  const keys = await page.evaluate(() => Object.keys(wwDistanceState.zones));
  expect(keys).toEqual(["zone1", "zone2", "zone3", "zone4"]);
});

test("a normal three-zone Apply is unchanged: four cards, three drawn zones, no extra card", async ({ page }) => {
  await openDistance(page);
  expect(await apply(page, payload([...standard(), disabled("ZP", "Zone P")]))).toBe(true);
  await expect(cards(page)).toHaveCount(4);
  await expect(extraCards(page)).toHaveCount(0);
  await expect(boundaries(page)).toHaveCount(3);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3"]);
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();
  await expect(page.locator("#wwDistanceZone1Enabled")).toBeChecked();
  await expect(page.locator("#wwDistanceZone2DelayInput")).toHaveValue("0.3");
});

// ---- an imported fifth zone -----------------------------------------------------------------

test("an imported enabled fifth zone creates a dynamic card named after the source", async ({ page }) => {
  await openDistance(page);
  expect(await apply(page, payload([...standard(), quad("ZP", "Zone P", { delay_s: 10, reactive_reach_ohm: 30, resistive_reach_forward_ohm: 20 })]))).toBe(true);
  await expect(cards(page)).toHaveCount(5);
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Reverse Zone", "Zone P"]); // not "Zone 5"
  const card = extraCards(page).first();
  await expect(card).toHaveAttribute("data-zone-dynamic", "z_zp");
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toBeChecked();
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toHaveAttribute("aria-label", "Enable Zone P");
  await expect(page.locator("#wwDistanceZ_zpDirection")).toHaveText("Direction: Forward");
  await expect(page.locator("#wwDistanceZ_zpDelayInput")).toHaveValue("10");
  await expect(page.locator("#wwDistanceZ_zpAngleInput")).toHaveValue("80");
  await expect(page.locator("#wwDistanceZ_zpReactiveReachInput")).toHaveValue("30");
  await expect(page.locator("#wwDistanceZ_zpResistiveForwardInput")).toHaveValue("20");
  await expect(page.locator("#wwDistanceZ_zpResistiveReverseInput")).toHaveValue("2");
  // quadrilateral fields are shown, the Mho one is not
  await expect(page.locator("#wwDistanceZ_zpReactiveReachField")).toBeVisible();
  await expect(page.locator("#wwDistanceZ_zpReachField")).toBeHidden();
  await expect(zoneRow(page, "Zone P")).toContainText("Not Operated");
  await expect(zoneRow(page, "Zone P")).toContainText("delay 10.00s");
});

test("the fifth zone is plotted by the generic loop and listed in the legend", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 30, resistive_reach_forward_ohm: 20 })]));
  await expect(boundaries(page)).toHaveCount(4);
  await expect(boundary(page, "z_zp")).toHaveCount(1);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3", "Zone P"]);
  // the standard zones keep their own colour tokens; the extra zone has its own
  await expect(boundary(page, "zone1")).toHaveClass(/ww-dist-zone-boundary--zone1/);
  await expect(boundary(page, "z_zp")).toHaveAttribute("style", /--ww-dist-zone-extra1/);
  // drawn with no further click, and after an edit it follows
  const before = await points(page, "z_zp");
  await page.locator("#wwDistanceZ_zpReactiveReachInput").fill("45");
  await page.locator("#wwDistanceZ_zpReactiveReachInput").dispatchEvent("change");
  expect(await points(page, "z_zp")).not.toEqual(before);
});

test("the fifth zone's Operated state comes from the backend, like every other zone", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 30, resistive_reach_forward_ohm: 20, resistive_reach_reverse_ohm: 5, characteristic_angle_deg: 20 })]));
  const request = page.waitForRequest((r) => r.url().includes("distance-protection-manual") && r.url().includes("zones="));
  await enterLoop(page, 0); // Zab = 10 /_ 20 deg
  const sent = JSON.parse(new URL((await request).url()).searchParams.get("zones"));
  expect(sent.map((z) => z.key)).toEqual(["zone1", "zone2", "zone3", "zone4", "z_zp"]); // every zone, none dropped
  await expect(zoneRow(page, "Zone P")).toContainText("Operated");
  await expect(zoneRow(page, "Zone P")).not.toContainText("Not Operated");
  await expect(zoneRow(page, "Zone 1")).toContainText("Not Operated");
});

test("Fit Zones includes the fifth zone, and a disabled zone does not affect it", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 120, resistive_reach_forward_ohm: 80, characteristic_angle_deg: 90 })]));
  await page.locator("#wwDistanceFitZonesBtn").click();
  const withZp = await view(page);
  expect(withZp).not.toBeNull();
  expect(await insideSvg(page, '#wwDistanceSvg [data-zone-key="z_zp"]')).toBeGreaterThanOrEqual(-0.5);
  expect(await insideSvg(page, '#wwDistanceSvg [data-zone-key="zone1"]')).toBeGreaterThanOrEqual(-0.5);
  // disabling the fifth zone removes it from the plot and from the fit
  await page.locator("#wwDistanceZ_zpEnabled").uncheck();
  await expect(boundary(page, "z_zp")).toHaveCount(0);
  await page.locator("#wwDistanceFitZonesBtn").click();
  const withoutZp = await view(page);
  expect(withoutZp.half).toBeLessThan(withZp.half / 3);
  // Reset still returns to the automatic view
  await page.locator("#wwDistanceResetViewBtn").click();
  expect(await view(page)).toBeNull();
});

test("a disabled fifth zone gets no card, no boundary and no legend entry", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), disabled("ZP", "Zone P")]));
  await expect(cards(page)).toHaveCount(4);
  await expect(boundary(page, "z_zp")).toHaveCount(0);
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toHaveCount(0);
  await expect(legendItems(page).filter({ hasText: "Zone P" })).toHaveCount(0);
  await expect(zoneRow(page, "Zone P")).toHaveCount(0);
  // ... and it needs no geometry: Apply succeeded without any
  await expect(page.locator("#wwDistanceZone1Enabled")).toBeChecked();
});

// ---- direction ----------------------------------------------------------------------------

test("an extra reverse-directed zone is the forward characteristic rotated 180 degrees", async ({ page }) => {
  await openDistance(page);
  const geometry = { reactive_reach_ohm: 20, resistive_reach_forward_ohm: 9, resistive_reach_reverse_ohm: 3, characteristic_angle_deg: 70 };
  await apply(page, payload([...standard(), quad("ZF", "Fwd Backup", geometry), quad("ZR", "Rev Backup", { ...geometry, direction: "reverse" })]));
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Reverse Zone", "Fwd Backup", "Rev Backup"]);
  await expect(page.locator("#wwDistanceZ_zrDirection")).toHaveText("Direction: Reverse");
  await expect(page.locator("#wwDistanceZ_zfDirection")).toHaveText("Direction: Forward");
  const fwd = await points(page, "z_zf");
  const rev = await points(page, "z_zr");
  expect(rev).toHaveLength(4);
  rev.forEach(([x, y], i) => {
    expect(x).toBeCloseTo(-fwd[i][0], 1); // point reflection through the origin (default view)
    expect(y).toBeCloseTo(-fwd[i][1], 1);
  });
  await expect(boundary(page, "z_zr")).toHaveClass(/ww-dist-zone-boundary--reverse/);
  await expect(boundary(page, "z_zf")).not.toHaveClass(/ww-dist-zone-boundary--reverse/);
  await expect(legendItems(page).filter({ hasText: "Rev Backup" })).toHaveText("Rev Backup · Reverse");
  await expect(legendItems(page).filter({ hasText: "Fwd Backup" })).toHaveText("Fwd Backup");
  // and the backend evaluates it by direction, not by name or number
  await enterLoop(page, 180);
  await expect(zoneRow(page, "Rev Backup")).toContainText("Operated");
  await expect(zoneRow(page, "Rev Backup")).not.toContainText("Not Operated");
  await expect(zoneRow(page, "Fwd Backup")).toContainText("Not Operated");
});

test("a standard zone that faces the other way is drawn by its direction, not by its number", async ({ page }) => {
  await openDistance(page);
  const zones = standard();
  zones[2] = { ...zones[2], direction: "reverse" }; // Zone 3 faces reverse
  zones[3] = quad("Z4", "Zone 4", { direction: "forward", reactive_reach_ohm: 15, resistive_reach_forward_ohm: 6 }); // Zone 4 faces forward
  expect(await apply(page, payload(zones))).toBe(true);
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Zone 4", ]); // the fourth card is no longer a "Reverse Zone"
  await expect(page.locator("#wwDistanceZone3Direction")).toHaveText("Direction: Reverse");
  await expect(page.locator("#wwDistanceZone4Direction")).toHaveText("Direction: Forward");
  await expect(boundary(page, "zone3")).toHaveClass(/ww-dist-zone-boundary--reverse/);
  await expect(boundary(page, "zone4")).not.toHaveClass(/ww-dist-zone-boundary--reverse/);
});

// ---- zero Left Resistive Reach ----------------------------------------------------------------

test("an extra zone with a 0 ohm Left Resistive Reach is valid and draws through the origin", async ({ page }) => {
  await openDistance(page);
  expect(await apply(page, payload([...standard(), quad("ZP", "Zone P", { resistive_reach_reverse_ohm: 0 })]))).toBe(true);
  await expect(page.locator("#wwDistanceZ_zpResistiveReverseInput")).toHaveValue("0");
  const pts = await points(page, "z_zp");
  expect(pts).toHaveLength(4);
  expect(Math.abs(pts[0][0])).toBeLessThan(0.01); // corner (r' = -left = 0, x' = 0) is the origin
  expect(Math.abs(pts[0][1])).toBeLessThan(0.01);
});

// ---- refusals -------------------------------------------------------------------------------

test("a refused Apply (unsupported settings) leaves the zones and the plot exactly as they were", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P")]));
  const snapshot = () =>
    page.evaluate(() => ({
      titles: [...document.querySelectorAll("#wwDistancePanel .ww-dist-zone-card-title")].map((e) => e.textContent),
      keys: Object.keys(wwDistanceState.zones), svg: document.getElementById("wwDistanceSvg").innerHTML,
    }));
  const before = await snapshot();
  const malformed = [
    payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: "ten" })]), // a bad value
    payload([...standard(), quad("ZP", "Zone P"), quad("ZP", "Zone P again")]), // a repeated stable id
    payload([...standard(), quad("ZP", "Zone P", { direction: null })]), // an enabled zone with no direction
    payload([]), // no zones at all
    payload([...standard(), { ...quad("ZP", "Zone P"), id: "" }]),
    { ...payload(standard()), characteristic: "lenticular" }, // a characteristic the analysis cannot draw
  ];
  for (const bad of malformed) {
    expect(await apply(page, bad)).toBe(false);
    expect(await snapshot()).toEqual(before);
  }
});

// ---- re-Apply ---------------------------------------------------------------------------------

test("re-Apply replaces the zone collection: a zone that is gone loses its card, boundary and state", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P"), quad("Z5", "Zone 5", { reactive_reach_ohm: 15 })]));
  await expect(cards(page)).toHaveCount(6);
  await expect(boundary(page, "z_zp")).toHaveCount(1);
  await expect(boundary(page, "z_z5")).toHaveCount(1);
  await expect(zoneRow(page, "Zone P")).toHaveCount(1);

  await apply(page, payload(standard()));
  await expect(cards(page)).toHaveCount(4);
  await expect(extraCards(page)).toHaveCount(0);
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toHaveCount(0);
  await expect(boundary(page, "z_zp")).toHaveCount(0);
  await expect(boundary(page, "z_z5")).toHaveCount(0);
  await expect(zoneRow(page, "Zone P")).toHaveCount(0);
  await expect(legendItems(page)).toHaveText(["Zone 1", "Zone 2", "Zone 3"]);
  expect(await page.evaluate(() => Object.keys(wwDistanceState.zones))).toEqual(["zone1", "zone2", "zone3", "zone4"]);
});

test("re-Apply updates an existing extra zone by its id instead of duplicating it", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 30 })]));
  // a manual edit of the applied zone is ordinary analysis state ...
  await page.locator("#wwDistanceZ_zpReactiveReachInput").fill("99");
  await page.locator("#wwDistanceZ_zpReactiveReachInput").dispatchEvent("change");
  await expect(page.locator("#wwDistanceZ_zpReactiveReachInput")).toHaveValue("99");
  // ... and Apply again overwrites it with the latest reviewed value
  await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 33 })]));
  await expect(extraCards(page)).toHaveCount(1);
  await expect(cards(page)).toHaveCount(5);
  await expect(page.locator("#wwDistanceZ_zpReactiveReachInput")).toHaveValue("33");
  await expect(boundary(page, "z_zp")).toHaveCount(1);
  await expect(zoneRow(page, "Zone P")).toHaveCount(1);
  expect(await page.evaluate(() => Object.keys(wwDistanceState.zones))).toEqual(["zone1", "zone2", "zone3", "zone4", "z_zp"]);
});

test("the order of the payload decides nothing but the order of the cards; identity is the id", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([quad("ZB", "Backup B"), ...standard(), quad("ZA", "Backup A", { reactive_reach_ohm: 14 })]));
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Reverse Zone", "Backup B", "Backup A"]);
  await expect(page.locator("#wwDistanceZone1ReactiveReachInput")).toHaveValue("4"); // Z1 is Zone 1 wherever it sits
});

test("Reset drops every extra zone along with the standard zone values", async ({ page }) => {
  await openDistance(page);
  await apply(page, payload([...standard(), quad("ZP", "Zone P")]));
  await page.evaluate(() => wwDistanceResetState());
  await expect(cards(page)).toHaveCount(4);
  await expect(extraCards(page)).toHaveCount(0);
  await expect(page.locator("#wwDistanceZone1Enabled")).not.toBeChecked();
  await expect(boundaries(page)).toHaveCount(0);
});

// ---- many zones, colours -------------------------------------------------------------------------

test("more extra zones than palette colours rotate deterministically and every zone stays named", async ({ page }) => {
  await openDistance(page);
  const extras = Array.from({ length: 8 }, (_, i) => quad(`X${i + 1}`, `Stage X${i + 1}`, { reactive_reach_ohm: 14 + i, resistive_reach_forward_ohm: 7 + i }));
  expect(await apply(page, payload([...standard(), ...extras]))).toBe(true);
  await expect(cards(page)).toHaveCount(12);
  // colour follows the zone's place among the extra zones (not its draw order, which is reversed)
  const colours = await page.evaluate(() =>
    Array.from({ length: 8 }, (_, i) => /--ww-dist-zone-extra(\d)/.exec(document.querySelector(`#wwDistanceSvg [data-zone-key="z_x${i + 1}"]`).getAttribute("style"))[1]));
  expect(colours).toEqual(["1", "2", "3", "4", "5", "6", "1", "2"]);
  await expect(legendItems(page)).toHaveCount(11); // 3 standard + 8 extras: all named
  await expect(legendItems(page).last()).toHaveText("Stage X8");
  await expect(zoneRow(page, "Stage X8")).toHaveCount(1);
});

// ---- layout ---------------------------------------------------------------------------------------

for (const width of [1280, 420, 320]) {
  test(`the zone cards, legend and plot stay usable with six zones at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await openDistance(page);
    await apply(page, payload([...standard(), quad("ZP", "Zone P", { reactive_reach_ohm: 20 }), quad("ZX", "A rather long backup zone name", { reactive_reach_ohm: 16 })]));
    await expect(cards(page)).toHaveCount(6);
    const layout = await page.evaluate(() => {
      const inner = window.innerWidth;
      const rects = [...document.querySelectorAll("#wwDistancePanel .ww-dist-zone-card")].map((c) => c.getBoundingClientRect());
      const legend = document.getElementById("wwDistanceZoneLegend").getBoundingClientRect();
      return {
        pageOverflow: document.documentElement.scrollWidth - inner,
        cardsInside: rects.every((r) => r.left >= -0.5 && r.right <= inner + 0.5 && r.width > 40),
        legendInside: legend.left >= -0.5 && legend.right <= inner + 0.5,
        columns: new Set(rects.map((r) => Math.round(r.left))).size,
      };
    });
    expect(layout.pageOverflow).toBeLessThanOrEqual(1);
    expect(layout.cardsInside).toBe(true);
    expect(layout.legendInside).toBe(true);
    if (width <= 420) expect(layout.columns).toBe(1); // single column, as for four zones
    await expect(legendItems(page)).toHaveCount(5);
    // controls are still reachable and work
    await page.locator("#wwDistanceZ_zxEnabled").scrollIntoViewIfNeeded();
    await page.locator("#wwDistanceZ_zxEnabled").uncheck();
    await expect(boundary(page, "z_zx")).toHaveCount(0);
    await page.locator("#wwDistanceFitZonesBtn").click();
    expect(await view(page)).not.toBeNull();
  });
}

// ---- end to end against the real backend --------------------------------------------------------------

test("end to end: enabling Zone P in the review makes the real Apply return it as a fifth zone card", async ({ page }) => {
  const LEFT = "Left Resistive Reach (−R)";
  const panel = page.locator("#wwRelayReviewPanel");
  await openDistance(page);
  await pick(page, "document.pdf", relaySheet("p441", { variant: "minimal" }));
  await expect(page.locator("#wwRelayImportSummary")).toContainText("zones found");
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel).toBeVisible();

  const resolve = async (key, label, value) => {
    await panel.locator(`button[aria-label="Resolve ${label}"]`).click();
    const form = panel.locator(`li[data-key="${key}"] form.ww-rr-resolve`);
    await form.locator("input").fill(String(value));
    await form.getByRole("button", { name: "Set value" }).click();
    await expect(form).toBeHidden();
  };
  for (const [z, n] of [["Z1", "Zone 1"], ["Z2", "Zone 2"], ["Z3", "Zone 3"]]) await resolve(`zone.${z}.rr.reverse`, `${n} ${LEFT}`, 0);
  await panel.locator('button[aria-label="Resolve Zone P Status"]').click();
  const status = panel.locator('li[data-key="zone.ZP.status"] form.ww-rr-resolve');
  await status.locator("select").selectOption("enabled");
  await status.getByRole("button", { name: "Set value" }).click();
  await expect(status).toBeHidden();
  // an enabled Zone P is held to the same rules as any zone: the sheet states no phase-phase resistive
  // reach for it and no Left Resistive Reach, so it is blocked for exactly those values -- not for being a fifth zone
  await expect(page.locator("#wwRelayReviewReadiness")).toContainText("Not ready");
  await expect(page.locator("#wwRelayReviewBlocking")).toContainText("Zone P Phase-Phase Resistive Reach");
  await expect(page.locator("#wwRelayReviewBlocking")).not.toContainText("cannot be represented");
  await resolve("zone.ZP.rr.pp", "Zone P Phase-Phase Resistive Reach", 4);
  await resolve("zone.ZP.rr.reverse", `Zone P ${LEFT}`, 0);
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "ready");

  await page.locator("#wwRelayReviewApply").click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  expect(await titles(page)).toEqual(["Zone 1", "Zone 2", "Zone 3", "Reverse Zone", "Zone P"]);
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toBeChecked();
  await expect(page.locator("#wwDistanceZ_zpDirection")).toHaveText("Direction: Forward");
  await expect(page.locator("#wwDistanceZ_zpDelayInput")).toHaveValue("10");
  await expect(page.locator("#wwDistanceZ_zpResistiveForwardInput")).toHaveValue("4");
  await expect(page.locator("#wwDistanceZ_zpResistiveReverseInput")).toHaveValue("0");
  await expect(zoneRow(page, "Zone P")).toHaveCount(1);
  await expect(boundary(page, "z_zp")).toHaveCount(1); // drawn, with the source's own (tiny) Zp reach
  // the defeated Zone 4 stays the disabled Reverse Zone card
  await expect(page.locator("#wwDistanceZone4Enabled")).not.toBeChecked();

  // Back to the review: disabling Zone P and applying again removes the fifth card.
  await panel.locator('button[aria-label="Edit the value of Zone P Status"]').click();
  const again = panel.locator('li[data-key="zone.ZP.status"] form.ww-rr-resolve');
  await again.locator("select").selectOption("disabled");
  await again.getByRole("button", { name: "Set value" }).click();
  await expect(again).toBeHidden();
  await expect(page.locator("#wwRelayReviewReadiness")).toHaveAttribute("data-readiness", "ready");
  await page.locator("#wwRelayReviewApply").click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(cards(page)).toHaveCount(4);
  await expect(page.locator("#wwDistanceZ_zpEnabled")).toHaveCount(0);
});
