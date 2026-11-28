// PU-MIG S5: the user-facing presentation of the side-aware per-unit engine -- every value shown is the backend's own provenance
// (GET .../per-unit-resolution); this spec checks the wording, the states and that the displayed numbers are the engine's.
const fs = require("fs");
const path = require("path");
const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

const SHOTS = process.env.S5_SHOTS || path.join(__dirname, "test-results", "s5-shots");
fs.mkdirSync(SHOTS, { recursive: true });

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}
const row = (page, id, name) => page.locator(`tr.channel-row--toggle[data-source-id="${id}"][data-channel-name="${name}"]`);
const body = (page) => page.locator("#wwChannelPerUnitBody");
// One provenance row by its label. The labels are upper-cased by CSS, so the rows are read from the DOM (textContent), never from
// innerText, which would return the rendered "VT RATIO".
const infoValue = (page, label) => body(page).locator("div", { has: page.locator(".ww-cc-preview-info-label", { hasText: new RegExp(`^${label}$`) }) })
  .locator(".ww-cc-preview-info-value");

// One recording of three Voltage (or Current) channels of the given unit whose P/S marker is `side`, plus a Measurement Group.
async function setup(page, { station, kind = "voltage", unit = "V", side = "P", amplitude = 76210, group, config, sourceDefault } = {}) {
  await page.goto("/index.html");
  const names = kind === "voltage" ? ["VA", "VB", "VC"] : ["IA", "IB", "IC"];
  const data = syntheticComtrade({ station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.2,
    channels: names.map((name, i) => ({ name, phase: "ABC"[i], unit, amplitude, frequencyHz: 50, side })) });
  await page.locator("#wwRdUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "s5.cfg", mimeType: "application/octet-stream", buffer: data.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "s5.dat", mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`, groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const g of await json(await page.request.get(groupsUrl))) expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  if (group !== false) {
    const made = await json(await page.request.post(groupsUrl, { data: { kind, display_name: "Bay 1", status: "confirmed",
      channel_refs: names.map(channel_name => ({ kind: "source", source_id: sid, channel_name })) } }), 201);
    await json(await page.request.put(`${groupsUrl}/${made.id}/${kind}-config`, { data: config }));
  }
  if (sourceDefault) await json(await page.request.put(`${base}/per-unit/sources/${sid}`, { data: sourceDefault }));
  return { base, sid, names, ws };
}

// A provenance sentence is read in full: its value cell must not be clipped (ellipsis) by the grid cell it sits in.
const expectFullyShown = async (locator) => {
  await expect.poll(() => locator.evaluate(el => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight)).toBe(true);
  // ... and it takes the whole row of the info grid (one readable block), not a wrapped sliver of one grid cell.
  await expect.poll(() => locator.evaluate(el => el.parentElement.getBoundingClientRect().width / el.parentElement.parentElement.getBoundingClientRect().width)).toBeGreaterThan(0.95);
};

const peak = (values) => Math.max(...values.map(Math.abs));

async function calculated(page, c, operation, channelName, name) {
  const made = await json(await page.request.post(`${c.base}/calculated-channels`, { data: { name, operation,
    inputs: [{ kind: "source", source_id: c.sid, channel_name: channelName }] } }), 201);
  return made;
}

async function showWaveform(page, c) {
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwFetchCalculatedChannels());
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${c.sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
}

async function openDetails(page, id, name) {
  await row(page, id, name).click({ button: "right" });
  await page.locator("#wwChannelMenuPerUnitBtn").click();
  await expect(page.locator("#wwChannelPerUnitOverlay")).toBeVisible();
}

// Every state is captured in both appearances (DEC-023): <name>-light.png and <name>-dark.png; the page is returned to light.
async function shot(page, file, target = page.locator("#wwChannelPerUnitOverlay .group-editor-box")) {
  for (const theme of ["light", "dark"]) {
    await page.evaluate(t => document.documentElement.setAttribute("data-theme", t), theme);
    await target.screenshot({ path: path.join(SHOTS, file.replace(/\.png$/, `-${theme}.png`)) });
  }
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
}

const VOLTAGE_GROUP = (extra = {}) => ({ reference_mode: "manual", reference_override: "line_to_ground", base_reference_side: "primary",
  nominal_voltage_ll_kv: 132, ...extra });

test("same-side Voltage: verified, no conversion, and no status badge on the channel", async ({ page }) => {
  const c = await setup(page, { station: "S5_SAME", side: "P", config: VOLTAGE_GROUP() });
  await showWaveform(page, c);
  await openDetails(page, c.sid, "VA");
  await expect(body(page)).toContainText("Measurement side");
  await expect(body(page).locator("div", { hasText: /^Reference check/ })).toContainText("Verified. The recording and the base are on the same side (primary); no VT conversion was needed. Waveform samples are unchanged.");
  await expect(body(page)).not.toContainText("VT ratio");
  await expect(body(page)).not.toContainText("no CT/VT scaling");
  await expect(row(page, c.sid, "VA").locator(".ww-pu-reference-status")).toHaveCount(0);
  await shot(page, "01-voltage-same-side.png");
});

test("converted Voltage: the base is referred to the secondary side with the VT ratio; samples unchanged", async ({ page }) => {
  const c = await setup(page, { station: "S5_CONV", side: "S", amplitude: 63.5,
    config: VOLTAGE_GROUP({ vt_primary_v: 132000, vt_secondary_v: 110 }) });
  await showWaveform(page, c);
  await openDetails(page, c.sid, "VA");
  await expect(infoValue(page, "Reference check")).toHaveText("Verified, base converted. The per-unit base was referred to the secondary side with the VT ratio 1200 : 1 (entered manually); waveform samples are unchanged.");
  await expectFullyShown(infoValue(page, "Reference check"));
  await expect(infoValue(page, "Effective base")).toHaveText("0.06351 kV L-G");            // the backend's denominator, readable (not "0.06")
  await expect(body(page)).not.toContainText("no CT/VT scaling");
  const resolution = await json(await page.request.get(`${c.base}/sources/${c.sid}/per-unit-resolution?channel_name=VA`));
  expect(resolution.verification_state).toBe("verified_converted");
  expect(resolution.effective_base_amount).toBeCloseTo(76.2102355330306 / 1200, 12);        // shown value = the engine's, unmodified
  await shot(page, "02-voltage-converted.png");
});

test("converted VT derived from the nominal voltage names its authority", async ({ page }) => {
  const c = await setup(page, { station: "S5_AUTO", side: "S", amplitude: 63.5, config: VOLTAGE_GROUP() });
  await showWaveform(page, c);
  await openDetails(page, c.sid, "VA");
  await expect(infoValue(page, "Reference check")).toContainText("with the VT ratio 1200 : 1 (derived from the nominal voltage)");
});

// A calculated Voltage result has no Per-Unit Details dialog: the shared Waveform menu offers it for raw channels and calculated Current
// only (DEC-070 Amendment 1; calculated-channel-presentation.spec.js). S5 is wording only and adds no surface, so a calculated Voltage's
// verified state is read from the engine's own resolution and its Unverified / unavailable state is the badge on the channel.
test("calculated Voltage inherits the converted result from its leaves; no new dialog is offered", async ({ page }) => {
  const c = await setup(page, { station: "S5_CALC", side: "S", amplitude: 63.5,
    config: VOLTAGE_GROUP({ vt_primary_v: 132000, vt_secondary_v: 110 }) });
  const calc = await calculated(page, c, "reverse_polarity", "VA", "Reversed VA");
  await showWaveform(page, c);
  const resolution = await json(await page.request.get(`${c.base}/calculated-channels/${calc.id}/per-unit-resolution`));
  expect(resolution.verification_state).toBe("verified_converted");
  expect(resolution.ratio_applied).toBe(1200);
  expect(resolution.effective_base_amount).toBeCloseTo(76.2102355330306 / 1200, 12);
  await row(page, calc.id, calc.name).click({ button: "right" });
  await expect(page.locator("#wwChannelContextMenu")).toBeVisible();
  await expect(page.locator("#wwChannelMenuPerUnitBtn")).toBeHidden();
  await page.keyboard.press("Escape");
  await row(page, calc.id, calc.name).click();
  await page.locator("#layoutModeSeparateBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect(row(page, calc.id, calc.name).locator(".ww-pu-reference-status")).toHaveCount(0);   // verified: nothing to warn about
});

test("calculated Voltage whose leaves have no established side is labelled Unverified on the channel", async ({ page }) => {
  const c = await setup(page, { station: "S5_CALCU", side: "", config: VOLTAGE_GROUP() });
  const calc = await calculated(page, c, "reverse_polarity", "VA", "Reversed VA");
  await showWaveform(page, c);
  const resolution = await json(await page.request.get(`${c.base}/calculated-channels/${calc.id}/per-unit-resolution`));
  expect(resolution.verification_state).toBe("unverified_historical");
  await row(page, calc.id, calc.name).click();
  await page.locator("#layoutModeSeparateBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  const badge = row(page, calc.id, calc.name).locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("Unverified reference");
  await expect(badge).toHaveAttribute("title", /not checked against a CT\/VT ratio/);
  await shot(page, "03-calculated-voltage-unverified.png", row(page, calc.id, calc.name));
});

test("calculated Current: converted with the CT; raw Current stays engineering under DEC-212", async ({ page }) => {
  const c = await setup(page, { station: "S5_CUR", kind: "current", unit: "A", side: "S", amplitude: 5,
    config: { method: "manual", manual_ibase_ka: 1.2, base_reference_side: "primary", ct_primary_a: 1200, ct_secondary_a: 5 } });
  const calc = await calculated(page, c, "reverse_polarity", "IA", "Reversed IA");
  await showWaveform(page, c);
  await row(page, c.sid, "IA").click();
  await row(page, calc.id, calc.name).click();
  await page.locator("#layoutModeSeparateBtn").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  await expect.poll(() => page.evaluate(({ sid }) => {
    const e = ww.displayed.get(wwChannelKey(sid, "IA")); return e && e.channel.unit;
  }, { sid: c.sid })).toBe("A");                                                                  // DEC-212: raw Current stays ENG
  await openDetails(page, calc.id, calc.name);
  await expect(infoValue(page, "Reference check")).toHaveText("Verified, base converted. The per-unit base was referred to the secondary side with the CT ratio 240 : 1 (entered manually); waveform samples are unchanged.");
  await shot(page, "04-calculated-current-converted.png");
});

test("historical Unverified: the badge and the dialog say the base was not checked, with samples unchanged", async ({ page }) => {
  const c = await setup(page, { station: "S5_UNV", side: "", config: VOLTAGE_GROUP() });
  await showWaveform(page, c);
  await row(page, c.sid, "VA").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("Unverified reference");
  await expect(badge).toHaveAttribute("title", /has not been verified/);
  await expect(badge).toHaveAttribute("title", /not checked against a CT\/VT ratio/);
  await expect(badge).toHaveAttribute("title", /Waveform samples are unchanged/);
  await expect(badge).not.toHaveAttribute("title", /no CT\/VT scaling/);
  await openDetails(page, c.sid, "VA");
  await expect(body(page)).toContainText("Unverified. The base was not placed on the measurement side with a verified denominator, so the historical per-unit value is kept without a VT check. Waveform samples are unchanged.");
  await expectFullyShown(infoValue(page, "Reference check"));
  await shot(page, "05-voltage-unverified.png");
});

test("blocked conversion: an actionable explanation, never the internal code, and engineering values are shown", async ({ page }) => {
  // Secondary recording against the stored Secondary-declared base's opposite: a Primary base, no VT, no nominal to derive one from.
  const c = await setup(page, { station: "S5_BLK", side: "P", amplitude: 76210,
    config: { reference_mode: "manual", reference_override: "line_to_ground", base_reference_side: "secondary", secondary_voltage_ll_v: 110 } });
  await showWaveform(page, c);
  await row(page, c.sid, "VA").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("PU unavailable");
  await expect(badge).toHaveAttribute("title", /reference sides are incompatible/);
  await expect(badge).toHaveAttribute("title", /no authoritative CT\/VT ratio is available/);
  await expect(badge).not.toHaveAttribute("title", /no CT\/VT scaling/);
  await openDetails(page, c.sid, "VA");
  await expect(body(page)).toContainText("Unavailable. No VT ratio is set for this Measurement Group. Enter it in Recording Details so the base can be referred to the measurement side.");
  await expectFullyShown(infoValue(page, "Reference check"));
  await expect(body(page)).not.toContainText("Reason");                                   // the refusal is said once, not twice
  const text = await body(page).textContent();
  expect(text).not.toMatch(/vt_authority_unavailable|ct_authority_unavailable|not_configured|voltage_reference_side_incompatible/);
  await shot(page, "06-voltage-blocked.png");
});

test("stored-versus-derived secondary base is reported, not applied", async ({ page }) => {
  const c = await setup(page, { station: "S5_DIAG", side: "S", amplitude: 66.4,
    config: { reference_mode: "manual", reference_override: "line_to_ground", base_reference_side: "secondary", secondary_voltage_ll_v: 115,
      nominal_voltage_ll_kv: 132, vt_primary_v: 132000, vt_secondary_v: 110 } });
  await showWaveform(page, c);
  await openDetails(page, c.sid, "VA");
  await expect(body(page)).toContainText("Stored base check");
  await expect(body(page)).toContainText("The stored secondary base (115.00 V) differs by 4.55 % from the 110.00 V derived from the nominal voltage and the stored VT. The stored base is used and was not changed.");
  await expectFullyShown(infoValue(page, "Stored base check"));
  await shot(page, "07-voltage-stored-vs-derived.png");
});

test("the provenance dialog fails visibly and recovers; nothing is requested until it is opened", async ({ page }) => {
  const c = await setup(page, { station: "S5_ERR", side: "P", config: VOLTAGE_GROUP() });
  await showWaveform(page, c);
  const requests = [];
  page.on("request", r => { if (r.url().includes("/per-unit-resolution")) requests.push(r.url()); });
  expect(requests).toHaveLength(0);                                                      // no provenance request merely to show the channel
  await page.route("**/per-unit-resolution**", route => route.fulfill({ status: 500, body: "{}" }));
  await openDetails(page, c.sid, "VA");
  await expect(page.locator("#wwChannelPerUnitError")).toContainText("Failed to load per-unit configuration");
  await shot(page, "08-provenance-error.png");
  await page.locator("#wwChannelPerUnitCloseBtn").click();
  await page.unroute("**/per-unit-resolution**");
  await openDetails(page, c.sid, "VA");
  await expect(body(page)).toContainText("Reference check");
  expect(requests.length).toBe(2);                                                       // exactly one request per open
});

test("Source Default counterexample: a 132 kV base labelled Secondary on rated Secondary samples reads 1/1200 pu and is presented as Unverified", async ({ page }) => {
  // The nominal system voltage is a Primary quantity: the stored "secondary" label never made it a Secondary denominator, so the
  // number is 1200x low and the engine never certifies it. The page must not call it verified.
  const c = await setup(page, { station: "S5_SD", side: "S", amplitude: 63.5085, group: false,
    sourceDefault: { voltage_base_value: 132, voltage_reference_mode: "manual", voltage_reference_override: "line_to_ground",
      voltage_base_reference_side: "secondary" } });
  await showWaveform(page, c);
  const resolution = await json(await page.request.get(`${c.base}/sources/${c.sid}/per-unit-resolution?channel_name=VA`));
  expect(resolution.verification_state).toBe("unverified_historical");
  const wave = await json(await page.request.get(`${c.base}/sources/${c.sid}/waveform?channel_name=VA&unit_mode=per_unit`));
  expect(wave.per_unit_status).toBe("configured");
  expect(peak(wave.values)).toBeCloseTo(1 / 1200, 7);                                       // ~0.0008333 pu, unchanged by S5
  await row(page, c.sid, "VA").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("Unverified reference");
  await openDetails(page, c.sid, "VA");
  await expect(infoValue(page, "Reference check")).toHaveText("Unverified. The base was not placed on the measurement side with a verified denominator, so the historical per-unit value is kept without a VT check. Waveform samples are unchanged.");
  await expect(body(page)).not.toContainText(/Verified[,.]/);
  await expect(body(page)).not.toContainText("Verified compatible");                        // Voltage lists no label-compatibility row at all
  await expect(body(page)).not.toContainText("VT ratio");
  await expect(infoValue(page, "Base reference side")).toHaveText("Secondary");               // the stored declaration the gate compared (S6), not "Unknown"
  await expect(infoValue(page, "Measurement side")).toHaveText("Secondary");
  await expectFullyShown(infoValue(page, "Reference check"));
  await shot(page, "09-source-default-counterexample.png");
  await page.locator("#wwChannelPerUnitCloseBtn").click();
  await shot(page, "09b-source-default-counterexample-channel-badge.png", row(page, c.sid, "VA"));
});

test("Manual Current base on the recording's side is Verified without a CT conversion", async ({ page }) => {
  const c = await setup(page, { station: "S5_MAN", kind: "current", unit: "A", side: "P", amplitude: 1200,
    config: { method: "manual", manual_ibase_ka: 1.2, base_reference_side: "primary" } });
  const calc = await calculated(page, c, "reverse_polarity", "IA", "Reversed IA");
  await showWaveform(page, c);
  const resolution = await json(await page.request.get(`${c.base}/calculated-channels/${calc.id}/per-unit-resolution`));
  expect(resolution.verification_state).toBe("verified_direct");
  await openDetails(page, calc.id, calc.name);
  await expect(infoValue(page, "Reference check")).toHaveText("Verified. The recording and the base are on the same side (primary); no CT conversion was needed. Waveform samples are unchanged.");
  await expect(body(page)).not.toContainText("CT ratio");
  await shot(page, "10-current-manual-same-side.png");
});

test("legacy calculated Current pointer (engine state fulfilled from the real response) is presented as Unverified", async ({ page }) => {
  // The legacy profile pointer has no API route (it is set in-process only), so the real automatic resolution is fetched and fulfilled
  // back with the backend's historical-gate fields: verification_state unverified_historical and no denominator side/conversion/ratio.
  const c = await setup(page, { station: "S5_LEG", kind: "current", unit: "A", side: "P", amplitude: 1200,
    config: { method: "manual", manual_ibase_ka: 1.2, base_reference_side: "primary" } });
  const calc = await calculated(page, c, "reverse_polarity", "IA", "Reversed IA");
  await showWaveform(page, c);
  const real = await json(await page.request.get(`${c.base}/calculated-channels/${calc.id}/per-unit-resolution`));
  const legacy = { ...real, verification_state: "unverified_historical", denominator_side: null, side_conversion: null,
    ratio_applied: null, ratio_authority: null, side_refusal_reason: null };
  await page.route(`**/calculated-channels/${calc.id}/per-unit-resolution`, route => route.fulfill({ json: legacy }));
  await openDetails(page, calc.id, calc.name);
  await expect(infoValue(page, "Reference check")).toHaveText("Unverified. The base was not placed on the measurement side with a verified denominator, so the historical per-unit value is kept without a CT check. Waveform samples are unchanged.");
  await expect(infoValue(page, "Reference compatibility")).toHaveText("Side labels match; not verified");   // never "Verified compatible"
  await expect(body(page)).not.toContainText(/Verified[,.]/);
  await expect(body(page)).not.toContainText("Verified compatible");
  await shot(page, "11-legacy-calculated-current-unverified.png");
});
