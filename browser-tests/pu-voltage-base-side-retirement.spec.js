// DEC-219: the nominal system voltage is always the PRIMARY Voltage PU base; the separate Voltage Base Reference Side input is retired from
// Recording Details. Real backend, real groups: what the page SENDS is intercepted and what the backend STORED is read back.
// The effective denominator is the backend's; nothing here (or in the page) computes one.
const fs = require("fs");
const path = require("path");
const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

const SHOTS = process.env.VBS_SHOTS || path.join(__dirname, "test-results", "vbs-shots");
fs.mkdirSync(SHOTS, { recursive: true });

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

// One recording of three Voltage (or Current) channels, uploaded through the page, with its groups cleared.
async function upload(page, { station, kind = "voltage", unit = "V", side = "P", amplitude = 76210 }) {
  await page.goto("/index.html");
  const names = kind === "voltage" ? ["VA", "VB", "VC"] : ["IA", "IB", "IC"];
  const data = syntheticComtrade({ station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.2,
    channels: names.map((name, i) => ({ name, phase: "ABC"[i], unit, amplitude, frequencyHz: 50, side })) });
  await page.locator("#wwRdUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "vbs.cfg", mimeType: "application/octet-stream", buffer: data.cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "vbs.dat", mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
  const ws = await workspaceId(page), sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`, groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  for (const g of await json(await page.request.get(groupsUrl))) expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  return { base, sid, names, groupsUrl };
}

async function voltageGroup(page, c, name, config) {
  const made = await json(await page.request.post(c.groupsUrl, { data: { kind: "voltage", display_name: name, status: "confirmed",
    channel_refs: c.names.map(channel_name => ({ kind: "source", source_id: c.sid, channel_name })) } }), 201);
  c.voltageConfigUrl = `${c.groupsUrl}/${made.id}/voltage-config`;
  await json(await page.request.put(c.voltageConfigUrl, { data: config }));
  return made;
}

const storedConfig = async (page, c) => (await json(await page.request.get(c.groupsUrl)))[0].voltage_config;

// Recording Details -> the recording -> the group -> Group Details.
async function openGroup(page, name) {
  await page.locator("#mainNavRecordingDetailsBtn").click();
  await expect(page.locator("#pageRecordingDetails")).toBeVisible();
  const recording = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  await expect(recording).toBeVisible({ timeout: 10000 });
  await recording.click();
  const group = page.locator("#wwRdGroupsBody .ww-rd-group-item", { hasText: name });
  await expect(group).toBeVisible({ timeout: 10000 });
  await group.click();
  const tab = page.locator("#wwRdTabGroupDetails");
  if (await tab.isVisible()) await tab.click();
  await expect(page.locator("#wwRdDetailsBody .ww-rd-section").first()).toBeVisible({ timeout: 8000 });
}

// The PUTs the page sends to the Voltage group configuration, recorded in order.
function recordPuts(page) {
  const puts = [];
  page.on("request", r => { if (r.method() === "PUT" && r.url().endsWith("/voltage-config")) puts.push(r.postDataJSON()); });
  return puts;
}

async function shot(page, file) {
  for (const theme of ["light", "dark"]) {
    await page.evaluate(t => document.documentElement.setAttribute("data-theme", t), theme);
    await page.locator("#wwRdDetailsBody").screenshot({ path: path.join(SHOTS, file.replace(/\.png$/, `-${theme}.png`)) });
  }
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
}

const NOMINAL_ONLY = { reference_mode: "manual", reference_override: "line_to_line" };

test("the Voltage Base Reference Side selector is retired; nominal voltage and the reference controls stay", async ({ page }) => {
  const c = await upload(page, { station: "VBS_NORMAL" });
  await voltageGroup(page, c, "Bay VBS", { ...NOMINAL_ONLY, nominal_voltage_ll_kv: 132, base_reference_side: "primary" });
  await openGroup(page, "Bay VBS");
  await expect(page.locator("#wwRdDetailsBody")).toContainText("Nominal voltage");
  await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
  await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeVisible();                          // nominal voltage control stays
  await expect(page.locator("#wwRdDetailsBody #wwRdVltRefOverride")).toBeVisible();                   // voltage reference (L-L / L-G) stays
  await expect(page.locator("#wwRdDetailsBody #wwRdVltAdvancedToggle")).toHaveCount(0);              // the Advanced container is retired
  await expect(page.locator("#wwRdDetailsBody #wwRdVltRefSide")).toHaveCount(0);
  await expect(page.locator("#wwRdDetailsBody")).not.toContainText("Base reference side");
  await expect(page.locator("#wwRdDetailsBody #wwRdLegacySecondaryBase")).toHaveCount(0);           // a normal group shows no legacy note
  await shot(page, "02-after-normal-voltage-edit.png");
});

test("entering a nominal voltage declares a Primary base explicitly, and nothing else is sent", async ({ page }) => {
  const c = await upload(page, { station: "VBS_NEW" });
  await voltageGroup(page, c, "Bay VBS", { ...NOMINAL_ONLY, base_reference_side: "unknown" });         // no nominal yet, side Unknown
  await openGroup(page, "Bay VBS");
  const puts = recordPuts(page);
  await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
  await page.locator("#wwRdDetailsBody #wwRdVltKv").fill("132");
  await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
  await expect.poll(() => puts.length).toBe(1);
  expect(puts[0]).toMatchObject({ nominal_voltage_ll_kv: 132, base_reference_side: "primary", reference_mode: "manual" });
  const stored = await storedConfig(page, c);
  expect([stored.nominal_voltage_ll_kv, stored.base_reference_side, stored.secondary_voltage_ll_v]).toEqual([132, "primary", null]);
  await expect(page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn")).toBeVisible();                // back in read mode
});

test("an unrelated save leaves a legacy Secondary base exactly as stored and the group stays identifiable", async ({ page }) => {
  const c = await upload(page, { station: "VBS_LEGACY", side: "S", amplitude: 63.5 });
  // the realistic legacy group: a nominal AND a stored Secondary base (re-sending the nominal would clear the secondary value)
  await voltageGroup(page, c, "Bay VBS", { reference_mode: "manual", reference_override: "line_to_ground", nominal_voltage_ll_kv: 132,
    base_reference_side: "secondary", secondary_voltage_ll_v: 110 });
  const resolutionUrl = `${c.base}/sources/${c.sid}/per-unit-resolution?channel_name=VA`;
  const before = await json(await page.request.get(resolutionUrl));
  await openGroup(page, "Bay VBS");
  const legacy = page.locator("#wwRdDetailsBody #wwRdLegacySecondaryBase");                       // one line, no new section
  await expect(legacy).toHaveText("Legacy Secondary base: 110 V (L‑L) — kept as stored.");
  await shot(page, "03-after-legacy-secondary-read.png");
  const puts = recordPuts(page);
  await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
  await expect(legacy).toContainText("the nominal voltage is not editable for this group");
  await expect(page.locator("#wwRdDetailsBody #wwRdVltKv")).toBeDisabled();                         // changing it would be an unapproved transition
  await expect(page.locator("#wwRdDetailsBody #wwRdVoltageRevertBtn")).toHaveCount(0);
  await shot(page, "04-after-legacy-secondary-edit.png");
  await page.locator("#wwRdDetailsBody #wwRdVltRefOverride").selectOption("line_to_line");            // an unrelated (reference) edit
  await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
  await expect.poll(() => puts.length).toBe(1);
  expect(puts[0]).not.toHaveProperty("base_reference_side");                                           // nothing declared
  expect(puts[0]).not.toHaveProperty("nominal_voltage_ll_kv");                                         // the unchanged nominal is not re-sent
  const stored = await storedConfig(page, c);
  expect([stored.base_reference_side, stored.secondary_voltage_ll_v, stored.nominal_voltage_ll_kv]).toEqual(["secondary", 110, 132]);   // untouched
  const after = await json(await page.request.get(resolutionUrl));
  expect(after.verification_state).toBe(before.verification_state);
});

test("a historical Unknown declaration is not rewritten by an unrelated save", async ({ page }) => {
  const c = await upload(page, { station: "VBS_UNKNOWN", side: "" });
  await voltageGroup(page, c, "Bay VBS", { reference_mode: "manual", reference_override: "line_to_line", nominal_voltage_ll_kv: 132, base_reference_side: "unknown" });
  await openGroup(page, "Bay VBS");
  const puts = recordPuts(page);
  await page.locator("#wwRdDetailsBody #wwRdVoltageEditBtn").click();
  await page.locator("#wwRdDetailsBody #wwRdVltRefOverride").selectOption("line_to_ground");
  await page.locator("#wwRdDetailsBody #wwRdVoltageApplyBtn").click();
  await expect.poll(() => puts.length).toBe(1);
  expect(puts[0]).not.toHaveProperty("base_reference_side");
  expect((await storedConfig(page, c)).base_reference_side).toBe("unknown");
});

test("the Calculated Current manual base reference-side control remains available", async ({ page }) => {
  const c = await upload(page, { station: "VBS_CUR", kind: "current", unit: "A", side: "S", amplitude: 5 });
  const group = await json(await page.request.post(c.groupsUrl, { data: { kind: "current", display_name: "Bay I", status: "confirmed",
    channel_refs: c.names.map(channel_name => ({ kind: "source", source_id: c.sid, channel_name })) } }), 201);
  await json(await page.request.put(`${c.groupsUrl}/${group.id}/current-config`, { data: { method: "manual", manual_ibase_ka: 1.2,
    base_reference_side: "primary", ct_primary_a: 1200, ct_secondary_a: 5 } }));
  const calc = await json(await page.request.post(`${c.base}/calculated-channels`, { data: { name: "Reversed IA", operation: "reverse_polarity",
    inputs: [{ kind: "source", source_id: c.sid, channel_name: "IA" }] } }), 201);
  await page.locator("#mainNavWaveformBtn").click();
  await page.evaluate(() => wwFetchCalculatedChannels());
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${c.sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await page.locator(`tr.channel-row--toggle[data-source-id="${calc.id}"][data-channel-name="${calc.name}"]`).click({ button: "right" });
  await page.locator("#wwChannelMenuPerUnitBtn").click();
  await expect(page.locator("#wwChannelPerUnitOverlay")).toBeVisible();
  await page.locator("#wwCalculatedPuMode").selectOption("manual");
  await expect(page.locator("#wwCalculatedPuSide")).toBeVisible();                                    // Stage 5B / D-2: untouched
  await expect(page.locator("#wwCalculatedPuBase")).toBeVisible();
});
