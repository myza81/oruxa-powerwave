// PULU Auto-Reference Browser Regression Tests
//
// Covers the PULU Auto-Reference Root-Cause Correction (Fixes 1–5):
//
//   PULU-01  275 kV PULU-style channel names (KPDN1 VR/VY/VB) auto-resolve
//            with primary=275.0 kV, secondary=0.110 kV, PS=P. Verifies that
//            after Fix 1 (WRP→neutral) Convention A is selected unambiguously
//            and the per-unit-resolution endpoint reports base_authority=
//            auto_resolved, measurement_side=primary, base_reference_side=
//            primary, reference_compatibility=compatible, status=configured,
//            and effective_base_amount ≈ 275/√3 kV.
//
//   PULU-02  SGT1 HV/LV channel names form SEPARATE Measurement Groups after
//            Fix 2 (geometry) and Fix 3 (identity). Verifies that
//            SGT1 VR_HV/VY_HV/VB_HV and SGT1 VR_LV/VY_LV/VB_LV land in
//            distinct groups so each side can be configured independently.
//
//   PULU-03  A needs_review Voltage group (primary_ratio below the 2 kV
//            minimum gate) shows NO false "Unverified reference" badge in
//            the waveform display (Fix 5 writes base_reference_side=primary;
//            authority gate blocks PU giving status=base_required; frontend
//            never fires the warning for base_required channels).
//
//   PULU-04  Manual 132 kV configuration of a needs_review LV group sets
//            base_authority=manual and resolves the channel to configured/
//            compatible status.
//
// At least one test here (PULU-01) is a real end-to-end browser test: an
// actual COMTRADE CFG/DAT is uploaded through the Recordings UI with the
// precise primary (275.0 kV) and secondary (0.110 kV) metadata fields that
// caused the original PULU "Unverified reference" false alarm, and the full
// per-unit resolution pipeline is exercised from ingest through the API to
// the waveform display layer.

const { test, expect } = require("./support/test");
const { syntheticComtrade } = require("./support/synthetic_comtrade");
const { BACKEND, workspaceId, sourceIdFor } = require("./support/event_reconstruction_helpers");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NOMINAL_KV  = 275;
const LG_BASE_KV  = NOMINAL_KV / Math.sqrt(3);    // ≈ 158.77 kV (the PU denominator)

// IEC/EN PULU-style: primary_ratio = L-L nominal stated directly (Convention A)
const PRIMARY_KV  = "275.0000";                    // used in CFG text
const SECONDARY_KV = "0.1100";                     // 110 V secondary → 0.110 kV in CFG

// Tolerance for effective_base_amount ≈ 275/√3 kV (floating-point round-trip)
const LG_TOLERANCE = 0.01;                         // kV

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function json(response, status = 200) {
  expect(response.status(), await response.text()).toBe(status);
  return response.json();
}

function row(page, id, name) {
  return page.locator(
    `tr.channel-row--toggle[data-source-id="${id}"][data-channel-name="${name}"]`
  );
}

// Build a PULU-like COMTRADE fixture:
//
//   KPDN1 VR/VY/VB   : primary=275 kV, secondary=0.110 kV, PS=P  (auto-resolves)
//   SGT1 VR_HV/...   : primary=275 kV, secondary=0.110 kV, PS=P  (auto-resolves)
//   SGT1 VR_LV/...   : primary=1.0 kV (default — below 2 kV gate), PS=P (needs_review)
//
// The cfgPostProcess callback injects the real primary/secondary metadata for
// KPDN1 and SGT1 HV channels; LV channels keep the synthetic default of 1.0,1.0
// which causes the auto-base service to return needs_review.
function makePuluChannels() {
  const LG_AMP = LG_BASE_KV;  // amplitude ~ L-G nominal so PU ≈ 1.0 pu
  return [
    { name: "KPDN1 VR", phase: "A", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "KPDN1 VY", phase: "B", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "KPDN1 VB", phase: "C", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VR_HV", phase: "A", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VY_HV", phase: "B", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VB_HV", phase: "C", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VR_LV", phase: "A", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VY_LV", phase: "B", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
    { name: "SGT1 VB_LV", phase: "C", unit: "kV", amplitude: LG_AMP, frequencyHz: 50 },
  ];
}

// Apply primary/secondary metadata to the CFG text.
// KPDN1 and SGT1 HV channels: primary=275.0 kV, secondary=0.110 kV.
// SGT1 LV channels: keep synthetic default (1.0,1.0) → needs_review.
function puluCfgPostProcess(cfgText) {
  return cfgText
    .split(/\r\n|\n/)
    .map((line) => {
      // LV channels: keep default (needs_review — primary below 2 kV gate)
      if (/,SGT1 V[RYB]_LV,/.test(line)) return line;
      // KPDN1 and SGT1 HV channels: inject real IEC/EN primary/secondary
      if (/,KPDN1 V[RYB],/.test(line) || /,SGT1 V[RYB]_HV,/.test(line)) {
        return line.replace(",1.0,1.0,P", `,${PRIMARY_KV},${SECONDARY_KV},P`);
      }
      return line;
    })
    .join("\r\n");
}

// Upload the PULU-like COMTRADE through the Recordings UI and return
// {ws, sid, base, groupsUrl} for further API calls.
async function uploadPulu(page, station = "PULU_SGT1") {
  await page.goto("/index.html");
  const data = syntheticComtrade({
    station,
    startClock: "10:00:00.000000",
    rateHz: 1000,
    durationS: 0.1,
    channels: makePuluChannels(),
  });
  const cfg = Buffer.from(
    puluCfgPostProcess(data.cfg.toString("latin1")),
    "latin1",
  );
  await page.locator("#recordingsUploadBtn, #recordingsEmptyUploadBtn").first().click();
  await expect(page.locator("#uploadModalOverlay")).toBeVisible();
  await page.locator("#uploadModalFile_0").setInputFiles({
    name: `${station}.cfg`,
    mimeType: "application/octet-stream",
    buffer: cfg,
  });
  await page.locator("#uploadModalFile_1").setInputFiles({
    name: `${station}.dat`,
    mimeType: "application/octet-stream",
    buffer: data.dat,
  });
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();

  const ws = await workspaceId(page);
  const sid = await sourceIdFor(page, station);
  const base = `${BACKEND}/api/v1/workspaces/${ws}`;
  const groupsUrl = `${base}/sources/${sid}/measurement-groups`;
  return { ws, sid, base, groupsUrl };
}

// Find a measurement group whose channel_refs contain the given channel_name.
function findGroupForChannel(groups, channelName) {
  return groups.find((g) =>
    g.channel_refs.some((r) => r.channel_name === channelName)
  );
}

// Get waveform display state for one channel from the in-page ww map.
function displayedChannel(page, id, name) {
  return page.evaluate(({ id, name }) => {
    const entry = ww.displayed.get(wwChannelKey(id, name));
    if (!entry) return null;
    const { channel } = entry;
    return {
      status: channel.perUnitStatus,
      compatibility: channel.perUnitReferenceCompatibility,
      unit: channel.unit,
    };
  }, { id, name });
}

// ---------------------------------------------------------------------------
// PULU-01: 275 kV PULU-style channels auto-resolve end-to-end
// ---------------------------------------------------------------------------

test("PULU-01: 275 kV channels (primary=275.0, secondary=0.110, PS=P) auto-resolve with correct PU metadata", async ({ page }, info) => {
  const { sid, base, groupsUrl } = await uploadPulu(page, "PULU_01");

  const groups = await json(await page.request.get(groupsUrl));

  // Locate the KPDN1 group (must exist — channels form their own context)
  const kpdnGroup = findGroupForChannel(groups, "KPDN1 VR");
  expect(kpdnGroup, "KPDN1 group missing").not.toBeNull();
  expect(kpdnGroup.kind).toBe("voltage");
  // base_authority is internal and not in VoltageGroupConfigOut; verify via pu_status and
  // nominal_voltage_ll_kv — if the auto-base ran and selected Convention A, nominal=275 and
  // pu_status="configured" (auto_resolved → STATUS_CONFIGURED via voltage_group_config).
  expect(kpdnGroup.pu_status).toBe("configured");
  expect(kpdnGroup.voltage_config.nominal_voltage_ll_kv).toBeCloseTo(NOMINAL_KV, 3);
  expect(kpdnGroup.voltage_config.base_reference_side).toBe("primary");

  // Per-unit resolution API: KPDN1 VR channel
  const resolution = await json(
    await page.request.get(`${base}/sources/${sid}/per-unit-resolution?channel_name=KPDN1 VR`)
  );
  expect(resolution.status).toBe("configured");
  expect(resolution.reference_compatibility).toBe("compatible");
  expect(resolution.measurement_side).toBe("primary");
  expect(resolution.base_reference_side).toBe("primary");
  expect(resolution.effective_base_amount).toBeCloseTo(LG_BASE_KV, 1);

  // Waveform display: open KPDN1 VR in PU mode — no badge
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate((el) => el.open))) {
    await details.locator(":scope > summary").click();
  }
  await row(page, sid, "KPDN1 VR").click();
  await page.locator("#wwUnitPerUnitBtn").click();

  // Channel must be configured (pu), compatible (no badge)
  await expect.poll(() => displayedChannel(page, sid, "KPDN1 VR"), { timeout: 10000 })
    .toMatchObject({ status: "configured", unit: "pu", compatibility: "compatible" });
  await expect(row(page, sid, "KPDN1 VR").locator(".ww-pu-reference-status")).toHaveCount(0);

  await page.screenshot({ path: info.outputPath("pulu-01-kpdn1-pu.png") });
});

// ---------------------------------------------------------------------------
// PULU-02: SGT1 HV and LV channels form separate Measurement Groups
// ---------------------------------------------------------------------------

test("PULU-02: SGT1 _HV and _LV channels form separate Measurement Groups after identity fix", async ({ page }) => {
  const { groupsUrl } = await uploadPulu(page, "PULU_02");

  const groups = await json(await page.request.get(groupsUrl));

  const hvGroup = findGroupForChannel(groups, "SGT1 VR_HV");
  const lvGroup = findGroupForChannel(groups, "SGT1 VR_LV");

  // Both groups must exist and be distinct
  expect(hvGroup, "SGT1 HV group missing").not.toBeNull();
  expect(lvGroup, "SGT1 LV group missing").not.toBeNull();
  expect(hvGroup.id, "HV and LV must be separate groups").not.toBe(lvGroup.id);

  // HV group: auto-resolved at 275 kV (same as KPDN1)
  expect(hvGroup.kind).toBe("voltage");
  expect(hvGroup.pu_status).toBe("configured");
  expect(hvGroup.voltage_config.nominal_voltage_ll_kv).toBeCloseTo(NOMINAL_KV, 3);
  expect(hvGroup.voltage_config.base_reference_side).toBe("primary");

  // HV channels must all be in the HV group, none in the LV group
  const hvNames = hvGroup.channel_refs.map((r) => r.channel_name);
  const lvNames = lvGroup.channel_refs.map((r) => r.channel_name);
  for (const ch of ["SGT1 VR_HV", "SGT1 VY_HV", "SGT1 VB_HV"]) {
    expect(hvNames, `${ch} must be in HV group`).toContain(ch);
    expect(lvNames, `${ch} must NOT be in LV group`).not.toContain(ch);
  }
  for (const ch of ["SGT1 VR_LV", "SGT1 VY_LV", "SGT1 VB_LV"]) {
    expect(lvNames, `${ch} must be in LV group`).toContain(ch);
    expect(hvNames, `${ch} must NOT be in HV group`).not.toContain(ch);
  }
});

// ---------------------------------------------------------------------------
// PULU-03: needs_review group shows no false "Unverified reference" badge
// ---------------------------------------------------------------------------

test("PULU-03: needs_review LV group (below 2 kV gate) shows no Unverified reference badge", async ({ page }, info) => {
  const { sid, base, groupsUrl } = await uploadPulu(page, "PULU_03");

  const groups = await json(await page.request.get(groupsUrl));
  const lvGroup = findGroupForChannel(groups, "SGT1 VR_LV");
  expect(lvGroup, "SGT1 LV group missing").not.toBeNull();

  // LV group must be in needs_review state (primary_ratio=1.0 kV < 2 kV gate):
  // base_authority is internal; verify via pu_status="base_required" (authority gate fires)
  // and nominal_voltage_ll_kv=null (insufficient evidence → not set).
  expect(lvGroup.pu_status).toBe("base_required");
  expect(lvGroup.voltage_config.nominal_voltage_ll_kv).toBeNull();
  // Fix 5: base_reference_side must still be written as "primary" (PS=P declared → side unambiguous)
  expect(lvGroup.voltage_config.base_reference_side).toBe("primary");

  // Per-unit-resolution for a needs_review channel: status=base_required (authority gate blocks)
  const resolution = await json(
    await page.request.get(`${base}/sources/${sid}/per-unit-resolution?channel_name=SGT1 VR_LV`)
  );
  expect(resolution.status).toBe("base_required");

  // Waveform display: open SGT1 VR_LV in PU mode — stays ENG, NO badge
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate((el) => el.open))) {
    await details.locator(":scope > summary").click();
  }
  await row(page, sid, "SGT1 VR_LV").click();
  await page.locator("#wwUnitPerUnitBtn").click();

  // status=base_required: channel stays in kV (ENG), NOT "pu"
  await expect.poll(() => displayedChannel(page, sid, "SGT1 VR_LV"), { timeout: 10000 })
    .toMatchObject({ status: "base_required", unit: "kV" });

  // No badge of any kind — especially not "Unverified reference"
  await expect(row(page, sid, "SGT1 VR_LV").locator(".ww-pu-reference-status")).toHaveCount(0);

  await page.screenshot({ path: info.outputPath("pulu-03-no-badge.png") });
});

// ---------------------------------------------------------------------------
// PULU-04: Manual 132 kV confirmation of a needs_review LV group
// ---------------------------------------------------------------------------

test("PULU-04: manual 132 kV confirmation of needs_review LV group sets base_authority=manual and resolves to configured", async ({ page }) => {
  const { sid, base, groupsUrl } = await uploadPulu(page, "PULU_04");

  const groups = await json(await page.request.get(groupsUrl));
  const lvGroup = findGroupForChannel(groups, "SGT1 VR_LV");
  expect(lvGroup, "SGT1 LV group missing").not.toBeNull();
  // LV group must be base_required (primary=1.0 kV < 2 kV gate → needs_review → authority gate → base_required)
  expect(lvGroup.pu_status).toBe("base_required");

  // Manual confirmation workflow (canonical: engineer reviews and saves):
  //   Step 1 — promote group status to "confirmed" (required by the status gate in
  //             resolve_voltage_base_for_group: status must be in AUTHORITATIVE_GROUP_STATUSES).
  //             Auto-imported groups start as "suggested"; the PATCH here represents the
  //             engineer clicking "Confirm" in the UI.
  await json(await page.request.patch(`${groupsUrl}/${lvGroup.id}`, {
    data: { status: "confirmed" },
  }));
  //   Step 2 — set nominal_voltage_ll_kv=132 kV (the LV system nominal).
  //             base_authority is NOT a request parameter — it is derived internally
  //             (accepted nominal_voltage_ll_kv → base_authority="manual").
  await json(await page.request.put(`${groupsUrl}/${lvGroup.id}/voltage-config`, {
    data: {
      nominal_voltage_ll_kv: 132,
      reference_mode: "auto",
      base_reference_side: "primary",
    },
  }));

  // After manual confirmation: pu_status should be "configured" and nominal=132
  // (base_authority="manual" is internal; it lifts the authority gate which yields configured)
  const updated = await json(await page.request.get(groupsUrl));
  const updatedLv = findGroupForChannel(updated, "SGT1 VR_LV");
  expect(updatedLv.pu_status).toBe("configured");
  expect(updatedLv.voltage_config.nominal_voltage_ll_kv).toBeCloseTo(132, 3);
  expect(updatedLv.voltage_config.base_reference_side).toBe("primary");

  // Per-unit-resolution must now return configured/compatible
  const resolution = await json(
    await page.request.get(`${base}/sources/${sid}/per-unit-resolution?channel_name=SGT1 VR_LV`)
  );
  expect(resolution.status).toBe("configured");
  expect(resolution.reference_compatibility).toBe("compatible");

  // Waveform display: open SGT1 VR_LV in PU mode — now configured, no badge
  await page.locator("#mainNavWaveformBtn").click();
  const details = page.locator(`#channelGroups details.source-recording[data-source-id="${sid}"]`);
  if (!(await details.evaluate((el) => el.open))) {
    await details.locator(":scope > summary").click();
  }
  await row(page, sid, "SGT1 VR_LV").click();
  await page.locator("#wwUnitPerUnitBtn").click();
  await page.evaluate(() => wwRefreshWaveformDisplayBasis());

  await expect.poll(() => displayedChannel(page, sid, "SGT1 VR_LV"), { timeout: 10000 })
    .toMatchObject({ status: "configured", unit: "pu", compatibility: "compatible" });
  await expect(row(page, sid, "SGT1 VR_LV").locator(".ww-pu-reference-status")).toHaveCount(0);
});
