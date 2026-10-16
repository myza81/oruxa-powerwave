// Remaining relay families -- interpreted by validated JSON parameter catalogs only, through the unchanged generic
// relay-import UI (no relay-specific control or script).
//
// REL670 (catalog-only, READY FOR OWNER UAT): upload -> identify -> generic review -> accept the 0.00 ohm Left (-R)
// visualization approximation (the real boundary is the ZDRDIR directional element) -> confirm assumptions -> Apply ->
// Distance Protection cards -> R-X plot, Zone 4 enabled in reverse.
// What every relay's review shows is checked by the data-driven relay_import_conformance.spec.js (DEC-199); this spec
// keeps the REL670 UI interactions (Apply, approximation acceptance, reverse-zone legend, note disclosure).
// Synthetic sheets with invented numbers; the owner's real sheets are never committed.
// Runs against LOCAL code.

const { test, expect } = require("@playwright/test");
const { relaySheet, routeConfig, openDistance, pick } = require("./support/relay_import_helpers");

let problems;
test.beforeEach(async ({ page }) => {
  await routeConfig(page);
  problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
});
test.afterEach(() => {
  expect(problems).toEqual([]);
});

const panel = (page) => page.locator("#wwRelayReviewPanel");
const row = (page, key) => page.locator(`#wwRelayReviewPanel li[data-key="${key}"]`);
const zoneGroup = (page, id) => panel(page).locator(`details[data-group="zone-${id}"]`);
const button = (page, label) => page.locator(`#wwRelayReviewPanel button[aria-label="${label}"]`);
const readiness = (page) => page.locator("#wwRelayReviewReadiness");
const applyBtn = (page) => page.locator("#wwRelayReviewApply");
const LEFT = "Left Resistive Reach (−R)";
// The concise explanation under an unsupported Left (-R) reach (owner UAT wording), and fragments of the longer one it replaced.
const LEFT_OFFER = "Relay directional boundary is not yet representable. 0.00 Ω is an optional visualization approximation only and is not a mapped relay setting.";
const OLD_LEFT_OFFER_FRAGMENTS = ["cannot be represented yet", "Suggested for visualization", "directional element that Oruxa cannot represent", "not the relay's geometry"];
const input = (page, n, id) => page.locator(`#wwDistanceZone${n}${id}Input`);
const boundary = (page, key) => page.locator(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${key}"]`);

async function openReview(page, pdf, zones) {
  await openDistance(page);
  await pick(page, "document.pdf", pdf);
  await expect(page.locator("#wwRelayImportSummary")).toContainText(`${zones} zones found`);
  await page.locator("#wwRelayReviewBtn").click();
  await expect(panel(page)).toBeVisible();
}

test("REL670: identified and reviewed through its catalog, with Zone 4 enabled in reverse from its own settings", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  await expect(page.locator("#wwRelayImportIdentity")).toHaveText("Hitachi Energy · REL670");
  await expect(row(page, "zone.Z4.status")).toContainText("Enabled");
  await expect(row(page, "zone.Z4.status")).toContainText("Mapped");
  await expect(row(page, "zone.Z4.direction")).toContainText("Reverse");
  // bare IL1..IL3 channel labels (no ChannelType rows): the phase CTs, never the IN channel
  await expect(row(page, "ct.primary")).toContainText("900 A");
  await row(page, "ct.primary").getByRole("button", { name: /Source/ }).first().click();
  await expect(row(page, "ct.primary")).toContainText("CTprim1");
  await expect(row(page, "ct.primary")).not.toContainText("CTprim4");
  // RFPP is a loop value: halved, with the printed value, the transformation and the catalog in Source
  const pp = row(page, "zone.Z1.rr.pp");
  await expect(pp).toContainText("4 Ω");
  await pp.getByRole("button", { name: /Source/ }).first().click();
  await expect(pp).toContainText("Raw: 8");
  await expect(pp).toContainText("÷ 2");
  await expect(pp).toContainText("hitachi-rel670-catalog");
  // the ZDRDIR left boundary is a capability gap, offered only as a worded approximation
  await expect(row(page, "zone.Z1.rr.reverse")).toContainText("Not yet supported");
  await expect(row(page, "zone.Z1.rr.reverse").locator(".ww-rr-offer")).toHaveText(LEFT_OFFER);
  // the scheme requirement is a document note beside the zone, never the value
  await expect(zoneGroup(page, "Z1").locator("[data-source-notes]")).toContainText("Zone 1 Forward direction timer set to 0.15s");
  await expect(row(page, "zone.Z1.timer.pp")).toContainText("0.15 s");
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("REL670: Ready to apply after the approximation and confirmations; Apply plots all four zones", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  for (const n of ["1", "2", "3", "4"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  await expect(page.locator("#wwDistanceCharacteristicSelect")).toHaveValue("quadrilateral");
  await expect(input(page, 1, "ReactiveReach")).toHaveValue("6");
  await expect(input(page, 1, "ResistiveForward")).toHaveValue("4"); // RFPP 8 ohm/loop / 2, never RFPE = 12
  await expect(input(page, 1, "ResistiveReverse")).toHaveValue("0");
  await expect(page.locator("#wwDistanceZone1Geometry")).toHaveText("Geometry: Explicit R/X");
  for (const key of ["zone1", "zone2", "zone3", "zone4"]) await expect(boundary(page, key)).toHaveCount(1);
  // the reverse Zone 4 lies on the other side of the origin from Zone 1
  const cy = (key) => page.evaluate((k) => { const r = document.querySelector(`#wwDistanceSvg .ww-dist-zone-boundary[data-zone-key="${k}"]`).getBoundingClientRect(); return (r.top + r.bottom) / 2; }, key);
  expect(await cy("zone4")).toBeGreaterThan(await cy("zone1"));
});

test("REL670: the concise Left (-R) explanation -- 0.00 Ω stays optional and never becomes Mapped", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  const left = row(page, "zone.Z1.rr.reverse");
  await expect(left.locator(".ww-rr-offer")).toBeVisible();
  await expect(left.locator(".ww-rr-offer")).toHaveText(LEFT_OFFER);
  for (const fragment of OLD_LEFT_OFFER_FRAGMENTS) await expect(panel(page)).not.toContainText(fragment);
  // optional: offered, not applied -- the row stays Unsupported (blocking) and the review Not ready until the user acts
  await expect(left.locator(".ww-rr-status")).toHaveText("Not yet supported");
  await expect(left).toHaveAttribute("data-blocking", "true");
  await expect(readiness(page)).toContainText("Not ready");
  // accepting it is a visualization resolution only: Resolved · Suggested, still classified Unsupported, never Mapped
  await button(page, `Use 0.00 Ω for Zone 1 ${LEFT}`).click();
  await expect(left.locator(".ww-rr-status")).toHaveText("Resolved · Suggested");
  await expect(left.locator(".ww-rr-status")).toHaveAttribute("data-category", "unsupported");
  await expect(left.locator(".ww-rr-offer")).toBeHidden();
  await left.getByRole("button", { name: /Source/ }).first().click();
  await expect(left).toContainText("Classified as");
  await expect(left).toContainText("the relay's setting, and not mapped from a profile");
  await expect(left.locator(".ww-rr-status")).not.toHaveText("Mapped");
  // readiness is unchanged: the other zones' left reaches still block
  await expect(readiness(page)).toContainText("Not ready");
  await expect(applyBtn(page)).toHaveCount(0);
});

test("REL670: reverse Zone 4 is dashed and labelled 'Zone 4 · Reverse'; forward zones stay solid", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  for (const n of ["1", "2", "3", "4"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
  await page.locator("#wwRelayReviewConfirmAll").click();
  await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
  await applyBtn(page).click();
  await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
  // Apply geometry unchanged: Zone 4 keeps its own X / +R (RFPP 3 / 2) / 0.00 Ω and its reverse direction
  await expect(input(page, 4, "ReactiveReach")).toHaveValue("2");
  await expect(input(page, 4, "ResistiveForward")).toHaveValue("1.5");
  await expect(input(page, 4, "ResistiveReverse")).toHaveValue("0");
  await expect(page.locator("#wwDistanceZone4Direction")).toHaveText("Direction: Reverse");
  // the legend names the direction; the dash convention is stated once, as a display cue only
  const legend = page.locator("#wwDistanceZoneLegend");
  await expect(legend.locator(".ww-dist-zone-legend-item")).toHaveText(["Zone 1", "Zone 2", "Zone 3", "Zone 4 · Reverse"]);
  await expect(legend.locator('[data-zone-key="zone4"]')).toHaveAttribute("data-direction", "reverse");
  await expect(legend.locator('[data-legend-note="reverse-dash"]')).toHaveText("Dashed = reverse zone (display cue only)");
  await expect(legend.locator('[data-legend-note="reverse-dash"]')).toHaveAttribute("title", /direction setting.*display convention only/);
  // dashed is tied to the reverse direction only: boundary and legend swatch
  const dash = (key) => boundary(page, key).evaluate((el) => getComputedStyle(el).strokeDasharray);
  const swatch = (key) => legend.locator(`[data-zone-key="${key}"] .ww-dist-zone-legend-swatch`).evaluate((el) => getComputedStyle(el).borderTopStyle);
  expect(await dash("zone4")).not.toBe("none");
  expect(await swatch("zone4")).toBe("dashed");
  for (const key of ["zone1", "zone2", "zone3"]) {
    await expect(boundary(page, key)).not.toHaveClass(/ww-dist-zone-boundary--reverse/);
    expect(await dash(key)).toBe("none");
    expect(await swatch(key)).toBe("solid");
    await expect(legend.locator(`[data-zone-key="${key}"]`)).toHaveAttribute("data-direction", "forward");
  }
});

// Document notes are audit context, never settings: one collapsed, neutral disclosure under the zone's settings.
const notes = (page, id) => zoneGroup(page, id).locator("details[data-source-notes]");

test("REL670: a zone's document note is a collapsed, secondary disclosure -- never the configured setting", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  const note = notes(page, "Z1");
  const summary = note.locator(":scope > summary");
  const text = note.locator(".ww-rr-source-note-text");
  const disclaimer = note.locator(".ww-rr-source-notes-disclaimer");
  await expect(summary).toBeVisible();
  await expect(note.locator(".ww-rr-source-notes-label")).toHaveText("Document note");
  // collapsed by default: the document's words, the source and the disclaimer stay hidden
  expect(await note.evaluate((d) => d.open)).toBe(false);
  await expect(text).toBeHidden();
  await expect(disclaimer).toBeHidden();
  // neutral and subordinate: dim like a setting's label, smaller than a setting's value, never warning / error styled
  const style = await summary.evaluate((s) => {
    const css = getComputedStyle(s);
    const label = getComputedStyle(document.querySelector('#wwRelayReviewPanel li[data-key="zone.Z1.timer.pp"] .ww-rr-label'));
    const value = getComputedStyle(document.querySelector('#wwRelayReviewPanel li[data-key="zone.Z1.timer.pp"] .ww-rr-value'));
    return { color: css.color, labelColor: label.color, size: parseFloat(css.fontSize), valueSize: parseFloat(value.fontSize), weight: Number(css.fontWeight) };
  });
  expect(style.color).toBe(style.labelColor);
  expect(style.size).toBeLessThan(style.valueSize);
  expect(style.weight).toBeLessThan(600);
  // expand: the document's exact words, page / line provenance and the non-authoritative statement
  await summary.click();
  await expect(text).toBeVisible();
  await expect(text).toHaveText("Zone 1 Forward direction timer set to 0.15s");
  await expect(note.locator(".ww-rr-source-note")).toContainText(/Source: Page \d+ · line \d+/);
  await expect(disclaimer).toBeVisible();
  await expect(disclaimer).toHaveText("Not used as the configured setting.");
  // the zone's configured TAP SETTING is untouched by the note
  await expect(row(page, "zone.Z1.timer.pp")).toContainText("0.15 s");
  // collapse again
  await summary.click();
  await expect(text).toBeHidden();
  expect(await note.evaluate((d) => d.open)).toBe(false);
  // a zone without notes has no disclosure at all
  await expect(zoneGroup(page, "Z2").locator("[data-source-notes]")).toHaveCount(0);
  await expect(zoneGroup(page, "Z2")).not.toContainText("Document note");
});

test("REL670: several notes on one zone are one compact disclosure that expands to all of them", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones", { notes: [["Zone 1 Forward direction timer set to 0.15s"], ["Zone 1 Forward direction delayed for backup scheme"]] }), 4);
  const note = notes(page, "Z1");
  await expect(note).toHaveCount(1);
  await expect(note.locator(".ww-rr-source-notes-label")).toHaveText("2 document notes");
  const texts = note.locator(".ww-rr-source-note-text");
  await expect(texts).toHaveCount(2);
  await expect(texts.first()).toBeHidden();
  await note.locator(":scope > summary").click();
  await expect(texts).toHaveText(["Zone 1 Forward direction timer set to 0.15s", "Zone 1 Forward direction delayed for backup scheme"]);
  await expect(note.locator(".ww-rr-source-note").nth(1)).toContainText(/Source: Page \d+ · line \d+/);
  await expect(note.locator(".ww-rr-source-notes-disclaimer")).toHaveText("Not used as configured settings.");
});

test("REL670: document notes never change readiness or what Apply fills in", async ({ page }) => {
  const run = async (pdf, expandNotes) => {
    await openReview(page, pdf, 4);
    if (expandNotes) await notes(page, "Z1").locator(":scope > summary").click();
    await expect(readiness(page)).toHaveAttribute("data-readiness", "not_ready");
    const before = await readiness(page).textContent();
    for (const n of ["1", "2", "3", "4"]) await button(page, `Use 0.00 Ω for Zone ${n} ${LEFT}`).click();
    await page.locator("#wwRelayReviewConfirmAll").click();
    await expect(readiness(page)).toHaveAttribute("data-readiness", "ready");
    const after = await readiness(page).textContent();
    await applyBtn(page).click();
    await expect(page.locator("#wwRelayReviewApplyStatus")).toHaveText("Relay settings applied to Distance Protection analysis.");
    return { before, after, z1: await input(page, 1, "Delay").inputValue(), z4: await input(page, 4, "Delay").inputValue() };
  };
  const withNotes = await run(relaySheet("rel670-four-zones"), true);
  const withoutNotes = await run(relaySheet("rel670-four-zones", { notes: [] }), false);
  expect(withNotes).toEqual(withoutNotes);
  expect(withNotes.z1).toBe("0.15"); // the configured tPP, not the note
});

test("no relay-family-specific control or script exists in the page", async ({ page }) => {
  await openReview(page, relaySheet("rel670-four-zones"), 4);
  const ids = await page.evaluate(() => [...document.querySelectorAll("[id]")].map((e) => e.id));
  expect(ids.filter((i) => /rel670|rel511|7sl87|7sa613|grz100|grl200|rcs941|lfzp|relz/i.test(i))).toEqual([]);
  expect(await page.locator("script").evaluateAll((s) => s.map((x) => x.textContent).join("\n"))).not.toMatch(/REL670|REL511|7SL87|7SA613|GRZ100|GRL200|RCS-?941|LFZP|RELZ/);
});
