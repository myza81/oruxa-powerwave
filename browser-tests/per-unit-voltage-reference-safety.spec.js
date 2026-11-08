// VLT-REF-001: Voltage PU reference-side safety — real browser coverage.
//
// Verifies that base_reference_side (Voltage Measurement Group) and
// voltage_base_reference_side (Source Default) round-trip correctly through
// the API and that the resulting PU display behaviour (incompatible/unverified/
// compatible) is correctly propagated to the waveform display layer.
//
// Frontend selectors for base_reference_side are deferred to Phase 2 — the
// tests here set the field via API and verify the resulting display state,
// matching the same pattern used by per-unit-reference-safety.spec.js for
// LIM-001 Current channels.
const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

const row = (page, id, name) =>
  page.locator(`tr.channel-row--toggle[data-source-id="${id}"][data-channel-name="${name}"]`);

// Upload a 2-channel Voltage recording (kV) with the given PS marker, then
// set up a Voltage Measurement Group (default) or Source Default profile
// (sourceDefault: true) with the requested base_reference_side.
async function setup(page, { marker = "P", baseSide = "primary", sourceDefault = false } = {}) {
  await page.goto("/index.html");
  const station = "VLT_REF_SAFE";
  const data = syntheticComtrade({
    station, startClock: "10:00:00.000000", rateHz: 1000, durationS: 0.1,
    channels: [
      { name: "VA", phase: "A", unit: "kV", amplitude: 63.5, frequencyHz: 50 },
      { name: "VB", phase: "B", unit: "kV", amplitude: 63.5, frequencyHz: 50 },
    ],
  });
  // Replace the fixed ,1.0,1.0,P suffix that syntheticComtrade emits for every
  // channel with ,1,1,{marker} — same pattern used by LIM-001 Current tests.
  const cfg = Buffer.from(
    data.cfg.toString("latin1").replaceAll(",1.0,1.0,P", `,1,1,${marker}`),
    "latin1",
  );

  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({ name: "vlt.cfg", mimeType: "application/octet-stream", buffer: cfg });
  await page.locator("#uploadModalFile_1").setInputFiles({ name: "vlt.dat", mimeType: "application/octet-stream", buffer: data.dat });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();

  const ws = await workspaceId(page);
  const sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`;
  const groupsUrl = `${base}/sources/${sid}/measurement-groups`;

  for (const g of await json(await page.request.get(groupsUrl))) {
    expect((await page.request.delete(`${groupsUrl}/${g.id}`)).status()).toBe(204);
  }

  let group = null;
  if (sourceDefault) {
    await json(await page.request.put(`${base}/per-unit/sources/${sid}`, {
      data: { voltage_base_reference_side: baseSide },
    }));
  } else {
    group = await json(await page.request.post(groupsUrl, {
      data: {
        kind: "voltage", display_name: "VT reference test", status: "confirmed",
        channel_refs: ["VA", "VB"].map(channel_name => ({ kind: "source", source_id: sid, channel_name })),
      },
    }), 201);
    await json(await page.request.put(`${groupsUrl}/${group.id}/voltage-config`, {
      data: {
        nominal_voltage_ll_kv: 275,
        reference_mode: "manual",
        reference_override: "line_to_line",
        base_reference_side: baseSide,
      },
    }));
  }

  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate(el => el.open))) await details.locator(":scope > summary").click();
  await row(page, sid, "VA").click();
  await page.locator("#layoutModeSeparateBtn").click();

  const physical = await json(await page.request.get(`${base}/sources/${sid}/waveform?channel_name=VA`));

  await page.locator("#wwUnitPerUnitBtn").click();
  return { base, sid, station, groupsUrl, group, physical };
}

function displayed(page, id, name) {
  return page.evaluate(({ id, name }) => {
    const entry = ww.displayed.get(wwChannelKey(id, name));
    if (!entry || !entry.channel.values.length) return null;
    const { channel } = entry;
    return { status: channel.perUnitStatus, compatibility: channel.perUnitReferenceCompatibility, unit: channel.unit };
  }, { id, name });
}

// 3.3.a Voltage group base_reference_side can be set and read back via the
//       measurement-groups API (round-trip from browser test).
test("VLT-REF-001: voltage-config base_reference_side round-trips via API", async ({ page }) => {
  const c = await setup(page, { marker: "P", baseSide: "primary" });
  const groups = await json(await page.request.get(c.groupsUrl));
  expect(groups).toHaveLength(1);
  expect(groups[0].voltage_config.base_reference_side).toBe("primary");

  await json(await page.request.put(`${c.groupsUrl}/${c.group.id}/voltage-config`, {
    data: { nominal_voltage_ll_kv: 275, reference_mode: "manual", reference_override: "line_to_line", base_reference_side: "secondary" },
  }));
  const updated = await json(await page.request.get(c.groupsUrl));
  expect(updated[0].voltage_config.base_reference_side).toBe("secondary");

  await json(await page.request.put(`${c.groupsUrl}/${c.group.id}/voltage-config`, {
    data: { nominal_voltage_ll_kv: 275, reference_mode: "manual", reference_override: "line_to_line", base_reference_side: "unknown" },
  }));
  const reset = await json(await page.request.get(c.groupsUrl));
  expect(reset[0].voltage_config.base_reference_side).toBe("unknown");
});

// 3.3.b Source Default voltage_base_reference_side can be set and read back
//       via the per-unit API.
test("VLT-REF-001: source-default voltage_base_reference_side round-trips via API", async ({ page }) => {
  const c = await setup(page, { marker: "P", baseSide: "primary", sourceDefault: true });
  const cfg = await json(await page.request.get(`${c.base}/per-unit/sources/${c.sid}`));
  expect(cfg.voltage_base_reference_side).toBe("primary");

  await json(await page.request.put(`${c.base}/per-unit/sources/${c.sid}`, {
    data: { voltage_base_reference_side: "secondary" },
  }));
  const updated = await json(await page.request.get(`${c.base}/per-unit/sources/${c.sid}`));
  expect(updated.voltage_base_reference_side).toBe("secondary");
});

// 3.3.c An incompatible Voltage channel (PS=S, base=primary) shows "PU
//       unavailable" badge and returns a raw ENG waveform.
test("VLT-REF-001: incompatible PS=S/base=primary → PU unavailable badge, raw ENG waveform", async ({ page }, info) => {
  const c = await setup(page, { marker: "S", baseSide: "primary" });
  await expect.poll(() => displayed(page, c.sid, "VA")).toMatchObject({
    status: "base_required", unit: "kV", compatibility: "incompatible",
  });
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("PU unavailable");
  await expect(badge).toHaveAttribute("title", /reference sides are incompatible/);
  // Raw waveform endpoint returns unchanged engineering values.
  const rawNow = await json(await page.request.get(`${c.base}/sources/${c.sid}/waveform?channel_name=VA`));
  expect(rawNow.values).toEqual(c.physical.values);
  await page.screenshot({ path: info.outputPath("vlt-incompatible.png") });
});

// 3.3.d An unverified Voltage channel (PS=C, base=primary) shows "Unverified
//       reference" badge but returns a valid PU waveform.
test("VLT-REF-001: unverified PS=C/base=primary → Unverified reference badge, PU waveform", async ({ page }, info) => {
  const c = await setup(page, { marker: "C", baseSide: "primary" });
  await expect.poll(() => displayed(page, c.sid, "VA")).toMatchObject({
    status: "configured", unit: "pu", compatibility: "unverified",
  });
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveText("Unverified reference");
  await page.screenshot({ path: info.outputPath("vlt-unverified.png") });
});

// 3.3.e A compatible Voltage channel (PS=P, base=primary) shows no badge and
//       returns a valid PU waveform.
test("VLT-REF-001: compatible PS=P/base=primary → no badge, PU waveform", async ({ page }) => {
  const c = await setup(page, { marker: "P", baseSide: "primary" });
  await expect.poll(() => displayed(page, c.sid, "VA")).toMatchObject({
    status: "configured", unit: "pu", compatibility: "compatible",
  });
  const badge = row(page, c.sid, "VA").locator(".ww-pu-reference-status");
  await expect(badge).toHaveCount(0);
});

// 3.3.f Switching base_reference_side from "primary" to "secondary" on a PS=S
//       channel turns an incompatible channel into a compatible one.
test("VLT-REF-001: side switch primary→secondary makes PS=S channel compatible", async ({ page }) => {
  const c = await setup(page, { marker: "S", baseSide: "primary" });
  await expect.poll(() => displayed(page, c.sid, "VA")).toMatchObject({ status: "base_required", compatibility: "incompatible" });

  // secondary_voltage_ll_v is required by the strict secondary gate (VLT-REF-001): without it
  // base_reference_side="secondary" returns base_required("secondary_equivalent_not_configured").
  await json(await page.request.put(`${c.groupsUrl}/${c.group.id}/voltage-config`, {
    data: { nominal_voltage_ll_kv: 275, reference_mode: "manual", reference_override: "line_to_line", base_reference_side: "secondary", secondary_voltage_ll_v: 110 },
  }));
  await page.evaluate(() => wwRefreshWaveformDisplayBasis());

  await expect.poll(() => displayed(page, c.sid, "VA")).toMatchObject({ status: "configured", compatibility: "compatible" });
  await expect(row(page, c.sid, "VA").locator(".ww-pu-reference-status")).toHaveCount(0);
});

// 3.3.g The raw waveform endpoint returns unchanged engineering values
//       regardless of incompatibility — across all three compatibility states.
test("VLT-REF-001: raw waveform unchanged for incompatible, unverified, and compatible", async ({ page }) => {
  for (const marker of ["S", "C", "P"]) {
    await page.goto("/index.html");
    const { base, sid, physical } = await setup(page, { marker, baseSide: "primary" });
    const raw = await json(await page.request.get(`${base}/sources/${sid}/waveform?channel_name=VA`));
    expect(raw.values, `marker=${marker}`).toEqual(physical.values);
    expect(raw.unit, `marker=${marker}`).toBe("kV");
  }
});
